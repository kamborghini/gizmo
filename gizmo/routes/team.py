"""The sign-in and team routes: state, setup, login, two-factor, logout and
password, and the team's me, board and user.

Moved whole out of copilot.add_routes (stage 4 of the 14 October audit).
add_routes calls register() where they stood, so the route table keeps its
order. They read the team as team.NAME and copilot.py as core.NAME.
"""
import logging
from starlette.requests import Request
import time
import hmac
from datetime import datetime, timedelta, timezone
import tokenvault
import totp

import copilot as core
from gizmo import mail
from gizmo import activity
from gizmo import gate
from gizmo import team

# The same logger as copilot.py's, so the routes' log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


def register(mcp, registry):
    """Add the sign-in and team routes to the app."""
    @mcp.custom_route("/api/auth/state", methods=["POST"])
    async def auth_state_route(request: Request):
        err, _body = await core._auth_guard(request)
        if err:
            return err
        if core._team_setup_needed():
            return gate._json({"setup": True, "logged_in": False})
        uid = team._session_uid(request.headers.get("x-app-session"))
        u = team._team_user(uid)
        if not u or not u.get("active", True):
            return gate._json({"setup": False, "logged_in": False})
        return gate._json({"setup": False, "logged_in": True, "me": core._auth_me(uid, u)})

    @mcp.custom_route("/api/auth/setup", methods=["POST"])
    async def auth_setup_route(request: Request):
        # First run only: create the master account. The moment one account
        # exists this door is bricked shut.
        err, body = await core._auth_guard(request)
        if err:
            return err
        if not core._team_setup_needed():
            return gate._json({"error": "The app is already set up."}, 400)
        # The sign-in form's own ceiling applies: the code is a password.
        if len(team._login_hits) > 5000:
            team._login_hits.clear()
        if not gate._window_ok(team._login_hits.setdefault(gate._client_key(request), []),
                          team.LOGIN_MAX_PER_MIN, time.monotonic()):
            return gate._json({"error": "Too many attempts from here. Wait a minute and try again."}, 429)
        if not core.SETUP_CODE:
            return gate._json({"error": "First-time setup is locked. Whoever runs the server sets a one-time setup "
                                   "code first, then you type it here.", "reason": "setup_locked"}, 403)
        if not hmac.compare_digest(str(body.get("setup_code") or "").strip().encode("utf-8"),
                                   core.SETUP_CODE.encode("utf-8")):
            logger.warning("first-run setup refused: wrong setup code")
            return gate._json({"error": "That setup code is not right."}, 403)
        name = str(body.get("name") or "").strip()[:60]
        username = core._clean_username(body.get("username"))
        pw = str(body.get("password") or "")
        if not name or not username:
            return gate._json({"error": "A name and a username are both needed."}, 400)
        if len(pw) < 8:
            return gate._json({"error": "The password needs at least 8 characters."}, 400)
        try:
            d = team._load_users()
            d["seq"] = int(d.get("seq") or 0) + 1
            uid = f"u{d['seq']}"
            d["users"][uid] = {"name": name, "username": username, "pw": team._hash_pw(pw),
                               "role": "master", "active": True, "deleted": False,
                               "must_change": False, "fails": 0, "lock_until": "",
                               "created_at": datetime.now(timezone.utc).isoformat(),
                               "last_login_at": datetime.now(timezone.utc).isoformat()}
            team._write_users(d)
            try:
                state = core._load_watch()
                state["team_established"] = True
                core._save_watch(state)
            except Exception:
                logger.exception("could not record that setup happened")
            token = team._new_session(uid)
            activity._track(uid, "team", "set up the app", f"{name} is the master admin")
            return gate._json({"ok": True, "session": token, "me": core._auth_me(uid, d["users"][uid])})
        except RuntimeError:
            return gate._json({"error": "The account could not be saved. The data volume may be "
                                   "unwritable; check the server's storage."}, 500)

    @mcp.custom_route("/api/auth/login", methods=["POST"])
    async def auth_login_route(request: Request):
        err, body = await core._auth_guard(request)
        if err:
            return err
        # The login form's OWN ceiling. _pre_checks allows 120 requests a
        # minute, which is right for a page listing orders and far too wide for
        # one that checks passwords: the per-account lockout does nothing
        # against someone spraying a single password across many usernames.
        if len(team._login_hits) > 5000:
            team._login_hits.clear()
        if not gate._window_ok(team._login_hits.setdefault(gate._client_key(request), []),
                          team.LOGIN_MAX_PER_MIN, time.monotonic()):
            return gate._json({"error": "Too many sign-in attempts from here. Wait a "
                                   "minute and try again."}, 429)
        username = core._clean_username(body.get("username"))
        pw = str(body.get("password") or "")
        d = team._load_users()
        uid = core._find_username(d, username)
        u = d["users"].get(uid) if uid else None
        now = datetime.now(timezone.utc)
        # One vague answer for every failure: which part was wrong is nobody's
        # business at the door.
        vague = gate._json({"error": "That username and password do not match."}, 401)
        if not u:
            # Spend what an existing account would: three of the four failure
            # paths returned before _check_pw ran, so the response TIME answered
            # the question the vague body refuses to. One dummy verify levels it.
            team._check_pw(pw, team._PW_DUMMY)
            # Coalesced, not one row per attempt. The ledger is a fixed-size
            # FIFO, and this endpoint is reachable by any Shopify staff user of
            # the store with no gizmo account at all - unbounded rows here let
            # a burst of bad logins flush the whole audit history out of it.
            activity._track_login_noise(username)
            return vague
        if str(u.get("lock_until") or "") > now.isoformat():
            # Locked answers exactly like wrong: a different reply would tell
            # a guesser which usernames exist.
            activity._track_login_refusal(uid, "account is paused")
            return vague
        if not u.get("active", True):
            activity._track_login_refusal(uid, "account is switched off")
            return vague
        exp = str(u.get("pw_expires_at") or "")
        if exp and exp < now.isoformat():
            # A break-glass password that was never used in time. Refused
            # exactly like a wrong one, so the reply says nothing about which
            # accounts exist or which are mid-reset.
            activity._track_login_refusal(uid, "the temporary password had expired")
            return vague
        if not team._check_pw(pw, u.get("pw") or ""):
            team._note_wrong_password(d, u, uid, now=now)
            activity._track_login_refusal(uid, "wrong password")
            return vague
        u["fails"] = 0
        u["lock_until"] = ""
        # The escalation goes with them: proving you are the account holder
        # ends the run of locks, so one bad afternoon cannot make every
        # future mistake cost four hours.
        u["locks"] = 0
        u["last_login_at"] = now.isoformat()
        try:
            team._write_users(d)
        except RuntimeError:
            pass
        if u.get("mfa_secret"):
            # The password was right and that is now only half of it. A ticket,
            # not a session: short-lived, single-use, and it carries no
            # authority of its own - it only names who is half way in.
            ticket = team._mfa_ticket(uid)
            activity._track(uid, "auth", "password accepted, waiting on the second factor")
            return gate._json({"ok": True, "mfa": True, "ticket": ticket})
        token = team._new_session(uid)
        activity._track(uid, "auth", "logged in")
        return gate._json({"ok": True, "session": token, "me": core._auth_me(uid, u)})

    @mcp.custom_route("/api/auth/mfa", methods=["POST"])
    async def auth_mfa_route(request: Request):
        """Turn a second factor on, or ask whether it is on. Behind a session:
        you enrol as yourself, from inside."""
        err, body, who = await gate._guard(request)
        if err:
            return err
        op = str(body.get("op") or "status")
        d = team._load_users()
        u = d["users"].get(str(who))
        if not u:
            return gate._json({"error": "That account does not exist."}, 400)
        if op == "status":
            return gate._json({"enabled": bool(u.get("mfa_secret")),
                          "recovery_left": len(u.get("mfa_recovery") or [])})
        if op in ("start", "off"):
            # The password, again, from inside the session. A session is a
            # token in a browser; the second factor exists for the day that
            # token is in the wrong hands, and a change to it that the token
            # alone could make would be a lock whose key hangs on the door.
            if team._locked_now(u):
                return gate._json({"error": "Too many wrong attempts. Try again in a few minutes."}, 429)
            if not team._check_pw(str(body.get("current") or ""), u.get("pw") or ""):
                team._note_wrong_password(d, u, who, " at the second-factor settings")
                activity._track(who, "auth", "refused a second-factor change", "wrong password")
                return gate._json({"error": "Enter your current password to change two-step sign-in."}, 400)
            u["fails"] = 0
        if op == "start":
            # Held UNCONFIRMED until a code proves the app really has it.
            # Enrolling on "I scanned it" is how people lock themselves out.
            secret = totp.new_secret()
            u["mfa_pending"] = tokenvault.seal(secret)
            team._write_users(d)
            activity._track(who, "auth", "started setting up a second factor")
            return gate._json({"secret": secret,
                          "uri": totp.provisioning_uri(secret, u.get("username") or "user")})
        if op == "confirm":
            pending = u.get("mfa_pending")
            if not pending:
                return gate._json({"error": "Start setting up the second factor first."}, 400)
            secret = tokenvault.unseal(str(pending))
            if not totp.verify(secret, body.get("code")):
                return gate._json({"error": "That code did not match. Check the clock on "
                              "your phone and try the current code."}, 400)
            codes = totp.recovery_codes(8)
            u["mfa_secret"] = tokenvault.seal(secret)
            u["mfa_recovery"] = [totp.hash_recovery(c) for c in codes]
            u["mfa_at"] = datetime.now(timezone.utc).isoformat()
            u["mfa_counter"] = totp.verify_counter(secret, body.get("code"))
            u["mfa_fails"] = 0
            u.pop("mfa_pending", None)
            team._write_users(d)
            activity._track(who, "auth", "turned on a second factor")
            # The only time these are readable. They are stored hashed.
            return gate._json({"ok": True, "recovery": codes})
        if op == "off":
            for k in ("mfa_secret", "mfa_recovery", "mfa_pending", "mfa_counter", "mfa_fails"):
                u.pop(k, None)
            team._write_users(d)
            activity._track(who, "auth", "turned off their second factor")
            return gate._json({"ok": True})
        return gate._json({"error": "Unknown operation."}, 400)

    @mcp.custom_route("/api/auth/mfa-verify", methods=["POST"])
    async def auth_mfa_verify_route(request: Request):
        """Finish a login. Anonymous by necessity - there is no session yet -
        so it goes through the same door guard as login, and the ticket is what
        proves the password step already happened."""
        err, body = await core._auth_guard(request)
        if err:
            return err
        uid = team._mfa_ticket_uid(str(body.get("ticket") or ""))
        vague = gate._json({"error": "That code did not match."}, 401)
        if not uid:
            return gate._json({"error": "That sign-in has expired. Start again."}, 401)
        d = team._load_users()
        u = d["users"].get(uid)
        if not u or not u.get("mfa_secret"):
            return vague
        if team._locked_now(u):
            # The password step already passed, so the lock here is the
            # code's own: ten misses across any number of tickets pauses the
            # account, and a pause reads exactly like a wrong code.
            activity._track_login_refusal(uid, "account is paused")
            return vague
        given = str(body.get("code") or "")
        secret = tokenvault.unseal(str(u["mfa_secret"]))
        matched = totp.verify_counter(secret, given, last_counter=u.get("mfa_counter"))
        if matched >= 0:
            u["mfa_counter"] = max(int(u.get("mfa_counter") or 0), matched)
            u["mfa_fails"] = 0
        else:
            idx = totp.check_recovery(given, u.get("mfa_recovery") or [])
            if idx < 0:
                # Coalesced like the password path: a ticket costs one right
                # password, and tickets are minted eight a minute, so one row
                # per wrong code was a ledger-flushing loop for anyone holding
                # a password. Ten misses against the ACCOUNT pauses it, on the
                # same escalating clock as wrong passwords.
                activity._track_login_refusal(uid, "wrong second-factor code")
                u["mfa_fails"] = int(u.get("mfa_fails") or 0) + 1
                if u["mfa_fails"] >= team.MFA_FAIL_LIMIT:
                    u["mfa_fails"] = 0
                    step = min(int(u.get("locks") or 0), len(team.LOGIN_LOCK_STEPS) - 1)
                    u["locks"] = int(u.get("locks") or 0) + 1
                    mins = team.LOGIN_LOCK_STEPS[step]
                    u["lock_until"] = (datetime.now(timezone.utc) + timedelta(minutes=mins)).isoformat()
                    activity._track(uid, "auth", "account paused",
                           "too many wrong second-factor codes; locked for %d minutes" % mins)
                try:
                    team._write_users(d)
                except RuntimeError:
                    pass
                # Wrong codes spend the ticket. Five misses inside one
                # three-minute window is not a person mistyping.
                ticket = str(body.get("ticket") or "")
                team._mfa_tries[ticket] = team._mfa_tries.get(ticket, 0) + 1
                if team._mfa_tries[ticket] >= team.MFA_MAX_TRIES:
                    team._mfa_tickets.pop(ticket, None)
                    team._mfa_tries.pop(ticket, None)
                    activity._track_login_refusal(uid, "too many wrong codes; the sign-in was ended")
                    return gate._json({"error": "Too many wrong codes. Sign in again."}, 401)
                return vague
            # Spent. A recovery code is one journey back in, not a password.
            u["mfa_recovery"] = [h for i, h in enumerate(u["mfa_recovery"]) if i != idx]
            activity._track(uid, "auth", "used a recovery code",
                   f"{len(u['mfa_recovery'])} left")
        u["last_login_at"] = datetime.now(timezone.utc).isoformat()
        try:
            team._write_users(d)
        except RuntimeError:
            pass
        team._mfa_ticket_spend(str(body.get("ticket") or ""))
        token = team._new_session(uid)
        activity._track(uid, "auth", "logged in")
        return gate._json({"ok": True, "session": token, "me": core._auth_me(uid, u)})

    @mcp.custom_route("/api/auth/logout", methods=["POST"])
    async def auth_logout_route(request: Request):
        err, _body = await core._auth_guard(request)
        if err:
            return err
        raw = request.headers.get("x-app-session")
        uid = team._session_uid(raw)
        team._drop_sessions(token=raw)
        if uid:
            activity._track(uid, "auth", "logged out")
        return gate._json({"ok": True})

    @mcp.custom_route("/api/auth/password", methods=["POST"])
    async def auth_password_route(request: Request):
        # Change your OWN password: the current one is always required, so a
        # borrowed open session cannot quietly take over the account.
        err, body = await core._auth_guard(request)
        if err:
            return err
        uid = team._session_uid(request.headers.get("x-app-session"))
        u = team._team_user(uid)
        if not u or not u.get("active", True):
            return gate._json({"error": "Unauthorized"}, 401)
        # A borrowed session gets the same wall the front door has: the login
        # counts failures and locks; without the same rule here, an unattended
        # open session was an unlimited offline-speed guessing oracle for the
        # password itself (which is what unlocks the Finder drive).
        now_dt = datetime.now(timezone.utc)
        if str(u.get("lock_until") or "") > now_dt.isoformat():
            return gate._json({"error": "Too many wrong attempts. Try again in a few minutes."}, 429)
        current, new = str(body.get("current") or ""), str(body.get("new") or "")
        if not team._check_pw(current, u.get("pw") or ""):
            d0 = team._load_users()
            team._note_wrong_password(d0, d0["users"].get(uid) or {}, uid,
                                 " at the password change", now=now_dt)
            activity._track(uid, "auth", "failed password change", "wrong current password")
            return gate._json({"error": "The current password is wrong."}, 400)
        if len(new) < 8:
            return gate._json({"error": "The new password needs at least 8 characters."}, 400)
        try:
            d = team._load_users()
            d["users"][uid]["pw"] = team._hash_pw(new)
            d["users"][uid]["must_change"] = False
            d["users"][uid]["fails"] = 0
            d["users"][uid]["lock_until"] = ""
            d["users"][uid]["locks"] = 0
            # The expiry belonged to the break-glass password, not to this one:
            # left behind, the master's chosen password would stop working half
            # an hour later and lock them out of their own app.
            d["users"][uid].pop("pw_expires_at", None)
            # A new password retires the drive's too: if the old one was known,
            # a drive password may have been made with it.
            d["users"][uid].pop("dav_pw", None)
            d["users"][uid].pop("dav_pw_at", None)
            team._write_users(d)
        except RuntimeError:
            return gate._json({"error": "The change could not be saved. The data volume may be "
                                   "unwritable; check Settings, Connections."}, 500)
        team._drop_sessions(uid=uid)          # every session dies with the old password
        core._dav_drop_cache(uid)             # and so does the drive's cached credential
        token = team._new_session(uid)        # except this one, freshly minted
        activity._track(uid, "auth", "changed their password")
        return gate._json({"ok": True, "session": token})


    @mcp.custom_route("/api/team/me", methods=["POST"])
    async def team_me_route(request: Request):
        err, _body, who = await gate._guard(request, body=False)
        if err:
            return err
        u = team._team_user(who) or {}
        return gate._json({"me": {"sub": who, "id": who, "name": u.get("name") or "",
                             "role": u.get("role") or "member", "grace": False,
                             "tabs": team._user_tabs(who)}})

    @mcp.custom_route("/api/team/board", methods=["POST"])
    async def team_board_route(request: Request):
        err, packed = await core._team_guard(request, team.ROLE_LEVELS["admin"])
        if err:
            return err
        who, _body = packed
        try:
            d = team._load_users()
            events = activity._load_events()
            users = [core._user_public(uid, u) for uid, u in d["users"].items() if not u.get("deleted")]
            users.sort(key=lambda u: (-team.ROLE_LEVELS.get(u["role"], 0), u["name"] or "~"))
            return gate._json({"users": users, "events": events[-600:][::-1],
                          "counts": team._team_counts(events), "names": team._team_names(),
                          "me": who, "my_role": team._team_role(who)})
        except Exception:
            logger.exception("team board failed")
            return gate._json({"error": "Couldn't load the team."}, 500)

    @mcp.custom_route("/api/team/user", methods=["POST"])
    async def team_user_route(request: Request):
        err, packed = await core._team_guard(request, team.ROLE_LEVELS["admin"])
        if err:
            return err
        who, body = packed
        op = str(body.get("op") or "")
        my_level = team._team_level(who)
        try:
            d = team._load_users()
            if op == "create":
                # Admins mint members; only the master mints admins.
                name = str(body.get("name") or "").strip()[:60]
                username = core._clean_username(body.get("username"))
                role = str(body.get("role") or "member")
                if role not in ("admin", "member", "parttime"):
                    return gate._json({"error": "New accounts are admin, member or part-time."}, 400)
                if role == "admin" and my_level < team.ROLE_LEVELS["master"]:
                    return gate._json({"error": "Only the master admin can create admins."}, 403)
                if not name or not username:
                    return gate._json({"error": "A name and a username are both needed."}, 400)
                if core._find_username(d, username):
                    return gate._json({"error": "That username is already taken."}, 400)
                starter = core._starter_password()
                d["seq"] = int(d.get("seq") or 0) + 1
                uid = f"u{d['seq']}"
                d["users"][uid] = {"name": name, "username": username,
                                   "colour": core._next_team_colour(d["users"]),
                                   "pw": team._hash_pw(starter), "role": role, "active": True,
                                   "deleted": False, "must_change": True, "fails": 0,
                                   "lock_until": "",
                                   "created_at": datetime.now(timezone.utc).isoformat(),
                                   "last_login_at": ""}
                team._write_users(d)
                activity._track(who, "team", "created an account", f"{name} ({role})")
                # The one and only showing of the starter password, to the
                # admin who asked for it. It is already marked must-change.
                return gate._json({"ok": True, "id": uid, "starter_password": starter,
                              "users": core._team_public_list(d)})
            target = str(body.get("id") or body.get("sub") or "")
            u = d["users"].get(target)
            if not u or u.get("deleted"):
                return gate._json({"error": "That account does not exist."}, 400)
            their_level = team.ROLE_LEVELS.get(u.get("role"), 1)
            label = u.get("name") or "an unnamed account"
            # The rank rule, once: you must OUTRANK who you manage, and the
            # master outranks everyone but is above being managed at all.
            def may_manage() -> bool:
                if u.get("role") == "master":
                    return False
                if my_level >= team.ROLE_LEVELS["master"]:
                    return True
                return my_level > their_level
            if op == "rename":
                if target != who and not may_manage():
                    return gate._json({"error": "You cannot manage that account."}, 403)
                name = str(body.get("name") or "").strip()[:60]
                if not name:
                    return gate._json({"error": "The name cannot be empty."}, 400)
                u["name"] = name
                team._write_users(d)
                activity._track(who, "team", "renamed an account", f"{label} is now {name}")
            elif op == "username":
                if target != who and not may_manage():
                    return gate._json({"error": "You cannot manage that account."}, 403)
                username = core._clean_username(body.get("username"))
                if not username:
                    return gate._json({"error": "The username cannot be empty."}, 400)
                other = core._find_username(d, username)
                if other and other != target:
                    return gate._json({"error": "That username is already taken."}, 400)
                u["username"] = username
                team._write_users(d)
                activity._track(who, "team", "changed a username", label)
            elif op == "role":
                role = str(body.get("role") or "")
                if my_level < team.ROLE_LEVELS["master"]:
                    return gate._json({"error": "Only the master admin changes roles."}, 403)
                if role not in ("admin", "member", "parttime"):
                    return gate._json({"error": "Roles are admin, member or part-time."}, 400)
                if u.get("role") == "master":
                    return gate._json({"error": "The master admin cannot be demoted."}, 400)
                was_pt = u.get("role") == "parttime"
                u["role"] = role
                team._write_users(d)
                if was_pt and role != "parttime":
                    # No longer monitored, so an open shift cannot just hang:
                    # close it now, recorded as this admin's correction.
                    try:
                        core._work_close_open(target, who, "closed automatically when the role changed",
                                         "closed a session on role change")
                    except Exception:
                        logger.exception("could not close the work session on role change")
                activity._track(who, "team", "changed a role",
                       f"{label} is now " + {"admin": "an admin", "member": "a member",
                                             "parttime": "part-time"}[role])
            elif op == "active":
                on = bool(body.get("active"))
                if u.get("role") == "master":
                    return gate._json({"error": "The master admin cannot be switched off."}, 400)
                if not may_manage():
                    return gate._json({"error": "You cannot manage that account."}, 403)
                if target == who:
                    return gate._json({"error": "You cannot switch off your own access."}, 400)
                u["active"] = on
                team._write_users(d)
                if not on:
                    team._drop_sessions(uid=target)   # off means off, this second
                    core._dav_drop_cache(target)
                    mail._mail_release_owned(target, "account switched off")
                    try:
                        core._work_close_open(target, who, "closed automatically when the account was switched off",
                                         "closed a session when an account was switched off")
                    except Exception:
                        logger.exception("could not close the work session of a switched-off account")
                activity._track(who, "team", "changed access",
                       f"{label}'s access was switched {'on' if on else 'off'}")
            elif op == "colour":
                if not may_manage():
                    return gate._json({"error": "You cannot manage that account."}, 403)
                colour = str(body.get("colour") or "").strip().lower()
                # A NAME from the palette, never a colour value. The CRM learned
                # this when a Pipedrive label coloured url(//evil.co/a) reached
                # style.background and beaconed every render of the board.
                if colour not in core.TEAM_COLOUR_NAMES:
                    return gate._json({"error": "Pick one of the team colours."}, 400)
                u["colour"] = colour
                team._write_users(d)
                activity._track(who, "team", "changed a colour", f"{label} is now {colour}")
            elif op == "sign_off":
                # Somebody who has left, or who never filled it in, still needs
                # a name on outgoing email. Same rank rule as every other
                # account change; the person's own door is /api/mail/settings.
                if not may_manage():
                    return gate._json({"error": "You cannot manage that account."}, 403)
                text, why = mail._mail_clean_sign_off(body.get("text"))
                if why:
                    return gate._json({"error": why}, 400)
                u["sign_off"] = text
                team._write_users(d)
                activity._track(who, "team", "changed an email sign-off",
                       f"{label}: " + (text[:60] if text else "cleared"))
            elif op == "sizes":
                # Who may change what the bench cuts. Admins hold it by rank and
                # cannot be toggled: switching it off would read as a revocation
                # that the permission check would then ignore.
                if not may_manage():
                    return gate._json({"error": "You cannot manage that account."}, 403)
                if team.ROLE_LEVELS.get(u.get("role") or "member", 0) >= team.ROLE_LEVELS["admin"]:
                    return gate._json({"error": "Admins can already edit the size list; "
                                  "the grant is for members and part-timers."}, 400)
                grant = bool(body.get("can_sizes"))
                u["can_sizes"] = grant
                team._write_users(d)
                detail = (f"{label} can edit the size list" if grant
                          else f"{label} can no longer edit the size list")
                activity._track(who, "team", "changed size-list access", detail)
            elif op == "send":
                # Who may send email out of the shared mailbox as the shop.
                # Same shape as the size list, and admins hold it by rank for
                # the same reason: a switch that reads as a revocation the
                # permission check would then ignore is worse than no switch.
                if not may_manage():
                    return gate._json({"error": "You cannot manage that account."}, 403)
                if team.ROLE_LEVELS.get(u.get("role") or "member", 0) >= team.ROLE_LEVELS["admin"]:
                    return gate._json({"error": "Admins can already send email from Reactor; "
                                  "the grant is for members and part-timers."}, 400)
                grant = bool(body.get("can_send"))
                u["can_send"] = grant
                team._write_users(d)
                detail = (f"{label} can send email from Reactor" if grant
                          else f"{label} can no longer send email from Reactor")
                activity._track(who, "team", "changed email-sending access", detail)
            elif op == "tabs":
                if not may_manage():
                    return gate._json({"error": "You cannot manage that account."}, 403)
                raw = body.get("tabs")
                if raw is None:
                    # No list of its own, which is NOT the same as every tab:
                    # _user_tabs resolves that to DEFAULT_TABS, and the opt-in
                    # tabs are not in it. The ledger has to say what actually
                    # happened, or it records a grant that was never made.
                    u.pop("tabs", None)
                    detail = (f"{label} can open the default tabs (not "
                              + ", ".join(team.OPT_IN_TABS) + ")")
                    team._write_users(d)
                else:
                    if not isinstance(raw, list):
                        return gate._json({"error": "Tabs must be a list, or null for everything."}, 400)
                    tabs = [k for k in raw if k in team.TAB_KEYS]
                    u["tabs"] = tabs
                    detail = f"{label} can open: " + (", ".join(tabs) if tabs else "nothing")
                    # Persist the record FIRST: releasing their email is a
                    # CONSEQUENCE of the tab change, and doing it first left the
                    # threads released while the merchant was told the change
                    # had failed.
                    team._write_users(d)
                    if "mail" not in tabs:
                        mail._mail_release_owned(target, "mail tab switched off")
                activity._track(who, "team", "changed tab access", detail)
            elif op == "reset_password":
                if not may_manage():
                    return gate._json({"error": "You cannot manage that account."}, 403)
                starter = core._starter_password()
                u["pw"] = team._hash_pw(starter)
                u["must_change"] = True
                u["fails"], u["lock_until"], u["locks"] = 0, "", 0
                # This one is handed over in person, not written to a log, so
                # it does not expire - and it must not inherit an expiry left
                # behind by an earlier break-glass reset.
                u.pop("pw_expires_at", None)
                u.pop("dav_pw", None)            # and the drive password with them
                u.pop("dav_pw_at", None)
                team._write_users(d)
                team._drop_sessions(uid=target)       # the old password's sessions die
                core._dav_drop_cache(target)
                activity._track(who, "team", "reset a password", label)
                return gate._json({"ok": True, "starter_password": starter,
                              "users": core._team_public_list(d)})
            elif op == "reset_mfa":
                # The phone is gone. Same rank rule as a password reset: the
                # person loses the second factor, keeps the password, and is
                # told in the ledger who did it.
                if not may_manage():
                    return gate._json({"error": "You cannot manage that account."}, 403)
                if not u.get("mfa_secret") and not u.get("mfa_pending"):
                    return gate._json({"error": "That account has no second factor to reset."}, 400)
                for k in ("mfa_secret", "mfa_recovery", "mfa_pending", "mfa_counter",
                          "mfa_fails", "mfa_at"):
                    u.pop(k, None)
                team._write_users(d)
                activity._track(who, "team", "reset a second factor", label)
                return gate._json({"ok": True, "users": core._team_public_list(d)})
            elif op == "delete":
                if my_level < team.ROLE_LEVELS["master"]:
                    return gate._json({"error": "Only the master admin can delete accounts."}, 403)
                if u.get("role") == "master":
                    return gate._json({"error": "The master admin cannot be deleted."}, 400)
                u["deleted"], u["active"] = True, False
                team._write_users(d)
                team._drop_sessions(uid=target)
                core._dav_drop_cache(target)
                mail._mail_release_owned(target, "account deleted")
                try:
                    core._work_close_open(target, who, "closed automatically when the account was deleted",
                                     "closed a session when an account was deleted")
                except Exception:
                    logger.exception("could not close the work session of a deleted account")
                activity._track(who, "team", "deleted an account", label)
            else:
                return gate._json({"error": "Unknown team action."}, 400)
            return gate._json({"ok": True, "users": core._team_public_list(d)})
        except RuntimeError:
            team._users_mem = None   # memory diverged from disk; the next read takes disk truth
            return gate._json({"error": "The change could not be saved. The data volume may be "
                                   "unwritable; check Settings, Connections."}, 500)
        except Exception:
            logger.exception("team user op failed")
            return gate._json({"error": "That change could not be made. Check the server logs."}, 500)
