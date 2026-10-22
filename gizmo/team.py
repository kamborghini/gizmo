"""The team: the app's own accounts. Users and sessions (their stores and the
copies held in memory), passwords and lockouts, two-factor tickets, roles and
the tabs each person has, master reset, and the sign-in checks (the Shopify
session token, the authorisation every route's door asks for). Shopify has
no authority here.

Moved out of copilot.py (stage 4 of the 14 October audit); its sign-in and
team routes are in gizmo/routes/team.py. Read as `team.NAME` (`accounts` is
a local name in copilot.py).
"""
import logging
import os
import time
import hmac
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from starlette.requests import Request
from urllib.parse import urlparse
import jwt
from gizmo.config import _env_num
from gizmo import store as jsonstore
import re

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")




# ---------------------------------------------------------------------------
# Auth: Shopify session token only (embedded-only; no password fallback)
# ---------------------------------------------------------------------------

def _verify_session_token(token: str) -> dict:
    if not config.SHOPIFY_API_SECRET:
        raise RuntimeError("SHOPIFY_API_SECRET not configured")
    claims = jwt.decode(
        token,
        config.SHOPIFY_API_SECRET,
        algorithms=["HS256"],
        audience=config.SHOPIFY_API_KEY or None,
        leeway=5,
        options={"require": ["exp", "nbf"], "verify_aud": bool(config.SHOPIFY_API_KEY)},
    )
    dest = claims.get("dest") or ""
    # Defense in depth: only accept tokens minted for this store.
    if config.SHOPIFY_STORE:
        expected = f"https://{config.SHOPIFY_STORE}.myshopify.com"
        if dest != expected:
            raise jwt.InvalidTokenError("session token dest mismatch")
    # Shopify guidance: the issuer and destination must reference the same shop host.
    iss = claims.get("iss") or ""
    if iss and dest:
        ih, dh = urlparse(iss).netloc, urlparse(dest).netloc
        if ih and dh and ih != dh:
            raise jwt.InvalidTokenError("session token iss/dest host mismatch")
    return claims


AUTH_REFUSALS = {
    # reason -> what the door says. The reason travels with the 401 so the page
    # can tell a stale embed token (retry with a fresh one, never reload) from
    # a dead app session (sign in again), and the login screen can say which.
    "token": "Shopify rejected this browser's session token. If it keeps happening on one "
             "computer, check that its clock is set automatically: a clock a minute out makes "
             "every token look expired.",
    "session": "Your sign-in has expired. Please log in again.",
    "inactive": "This account is switched off.",
    "must_change": "Choose your own password first.",
}


def _authorize(request: Request) -> tuple[bool, Optional[str], str]:
    """Return (ok, who, reason). The only accepted credential is a verified
    Shopify session token (Bearer JWT from App Bridge) — the app is
    embedded-only. `who` is the staff member's own Shopify id, so every action
    is theirs. A verified id still gets refused when an admin has switched
    them off. `reason` names the refusal (a key of AUTH_REFUSALS) so the page
    can answer it correctly instead of treating every 401 as a dead session."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and config.SHOPIFY_API_SECRET:
        try:
            _verify_session_token(auth[7:])
        except Exception as e:
            logger.warning(f"session token rejected: {e}")
            return False, None, "token"
        # The embed token is only the perimeter. WHO you are is the app's own
        # session, minted at its login screen; no session, no entry. The one
        # exception is first-run setup, when no accounts exist yet: the
        # /api/auth routes handle that themselves and never come through here.
        uid = _session_uid(request.headers.get("x-app-session"))
        if not uid:
            return False, None, "session"
        u = _team_user(uid)
        if not u or not u.get("active", True):
            if u is not None:
                logger.warning("switched-off account %s was refused", uid)
            return False, None, "inactive"
        # A starter password unlocks nothing but the choose-your-own screen:
        # until the account owns its password, every other route is closed.
        if u.get("must_change") and not request.url.path.startswith("/api/auth/"):
            return False, None, "must_change"
        return True, uid, ""
    return False, None, "token"
# Sign-in attempts per client, whichever account is being tried.
_login_hits: dict[str, list[float]] = {}   # state nonce -> expiry (Google OAuth connect flow)


# ---------------------------------------------------------------------------
# Team: the app's own accounts. Shopify has no authority here.
#
# The embed token still gates the PERIMETER (a request must come from inside
# the shop's Shopify admin at all), but WHO you are is the app's own business:
# a register of accounts with scrypt-hashed passwords, server-side sessions,
# and a rank order of roles. master (Cameron) outranks admin outranks member;
# every management action is checked as "does the actor outrank the target,
# and is the action within the actor's rank" on the server, per request.
#
# Passwords are never stored, logged, or echoed: the register keeps only
# scrypt hashes, and the one time a password ever appears in a response is
# the single showing of a generated starter password to the admin who asked
# for it, already flagged must_change.
# ---------------------------------------------------------------------------
USERS_PATH = os.environ.get("USERS_PATH", "/data/users.json")
SESSIONS_PATH = os.environ.get("SESSIONS_PATH", "/data/sessions.json")
SESSION_HOURS = _env_num(float, os.environ.get("SESSION_HOURS", "24"), "24", "SESSION_HOURS")
# The sliding window alone let a session used once a day live forever, and a
# stolen one with it. A month is longer than any shift pattern here.
SESSION_MAX_DAYS = _env_num(float, os.environ.get("SESSION_MAX_DAYS", "30"), "30", "SESSION_MAX_DAYS")
MFA_FAIL_LIMIT = 10        # wrong second-factor codes per account before it pauses
LOGIN_FAIL_LIMIT = 5
# A real hash to verify against when the username does not exist, so an unknown
# user costs the same time as a wrong password and the response cannot be used
# to enumerate accounts. Built once at import.
_PW_DUMMY = ""   # filled just below _hash_pw, which is defined further down
LOGIN_LOCK_MINUTES = 15
# Each consecutive lock lasts longer than the last. Without it, serving a lock
# handed the guesser a fresh five attempts every quarter of an hour - twenty an
# hour, for as long as they cared to keep going. A person who has genuinely
# forgotten their password tries a few times and asks for a reset; nobody
# reaches the fourth lock by accident.
LOGIN_LOCK_STEPS = (15, 30, 60, 240)
# The login form's own ceiling, well under the app-wide 120/minute. Guessing
# does not need a wide door, and legitimate sign-in never needs more than a
# handful in a minute.
LOGIN_MAX_PER_MIN = 8
ROLE_LEVELS = {"master": 3, "admin": 2, "member": 1, "parttime": 1}
_users_mem: Optional[dict] = None
_sessions_mem: Optional[dict] = None


def _let_go_of_accounts_in_memory(paths) -> list:
    """Let go of the accounts and sessions held in memory (see
    jsonstore.holds_in_memory): those whose path is in paths, or both."""
    global _users_mem, _sessions_mem
    gone = []
    if paths is None or USERS_PATH in paths:
        _users_mem = None
        gone.append(USERS_PATH)
    if paths is None or SESSIONS_PATH in paths:
        _sessions_mem = None
        gone.append(SESSIONS_PATH)
    return gone


jsonstore.holds_in_memory(_let_go_of_accounts_in_memory)



def _hash_pw(pw: str, salt: Optional[bytes] = None) -> str:
    salt = salt or os.urandom(16)
    h = hashlib.scrypt(pw.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1)
    return salt.hex() + "$" + h.hex()


def _check_pw(pw: str, stored: str) -> bool:
    try:
        salt_hex, h_hex = stored.split("$", 1)
        h = hashlib.scrypt(pw.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=2 ** 14, r=8, p=1)
        return hmac.compare_digest(h.hex(), h_hex)
    except Exception:
        return False


def _note_wrong_password(d: dict, u: dict, uid: str, where: str = "",
                         now: Optional[datetime] = None) -> None:
    """One wrong password, wherever it was typed: the login, the password
    change, or the second-factor settings. They share one counter and one
    escalating lock, because a guesser does not care which form accepts the
    guess. The password change used to keep its own flat fifteen minutes,
    and the second-factor settings had no counter at all."""
    now = now or datetime.now(timezone.utc)
    u["fails"] = int(u.get("fails") or 0) + 1
    if u["fails"] >= LOGIN_FAIL_LIMIT:
        u["fails"] = 0
        step = min(int(u.get("locks") or 0), len(LOGIN_LOCK_STEPS) - 1)
        u["locks"] = int(u.get("locks") or 0) + 1
        mins = LOGIN_LOCK_STEPS[step]
        u["lock_until"] = (now + timedelta(minutes=mins)).isoformat()
        activity._track(uid, "auth", "account paused",
               "too many wrong passwords%s; locked for %d minutes" % (where, mins))
    try:
        _write_users(d)
    except RuntimeError:
        pass


def _locked_now(u: dict) -> bool:
    return str(u.get("lock_until") or "") > datetime.now(timezone.utc).isoformat()



_PW_DUMMY = _hash_pw(secrets.token_urlsafe(16))

def _users_default() -> dict:
    return {"version": 2, "seq": 0, "users": {}}


def _load_users() -> dict:
    global _users_mem
    if _users_mem is None:
        d = jsonstore._load_json_store(USERS_PATH, "users_store", None)
        if isinstance(d, dict) and d.get("version") == 2 and "users" in d:
            _users_mem = d
        else:
            if isinstance(d, dict) and d.get("users"):
                # The short-lived Shopify-identity register: set aside, start clean.
                try:
                    os.replace(USERS_PATH, USERS_PATH + ".v1.bak")
                    logger.info("team: v1 register archived; the app now owns its accounts")
                except OSError:
                    pass
            _users_mem = _users_default()
        _master_reset_check(_users_mem)
    return _users_mem


def _write_users(d: dict) -> None:
    """Raises when the register cannot be made durable, so an account change
    is never reported as done while only the memory copy holds it."""
    global _users_mem
    if not jsonstore._store_writable(USERS_PATH):
        _users_mem = None      # the caller already mutated the shared object
        raise RuntimeError("users register is not writable")
    try:
        # Owner-only, like the token files beside it: this register holds the
        # password hashes, the second-factor secrets and the recovery codes.
        jsonstore._write_json_store(USERS_PATH, "users_store", d, private=True)
    except Exception:
        _users_mem = None
        raise
    _users_mem = d


def _load_sessions() -> dict:
    global _sessions_mem
    if _sessions_mem is None:
        d = jsonstore._load_json_store(SESSIONS_PATH, "sessions", None)
        _sessions_mem = d if isinstance(d, dict) else {}
    return _sessions_mem


def _write_sessions(d: dict) -> None:
    global _sessions_mem
    _sessions_mem = d
    if not jsonstore._store_writable(SESSIONS_PATH):
        return    # sessions are re-creatable; losing them only forces a login
    # A session row is a live credential's hash and who it belongs to; it gets
    # the same mode as the register it authenticates against.
    jsonstore._write_json_store(SESSIONS_PATH, "sessions", d, private=True)


SESSIONS_PER_USER = _env_num(int, os.environ.get("SESSIONS_PER_USER", "12"), "12", "SESSIONS_PER_USER")


# Half-finished logins. In memory only and deliberately so: a ticket is worth
# nothing after a restart, which is the safe direction, and it never belongs in
# a file that gets backed up. Bounded, so a flood of password-only attempts
# cannot grow it without limit.
_mfa_tickets: dict = {}
_mfa_tries: dict = {}            # ticket -> wrong codes so far
MFA_TICKET_SECONDS = 180
MFA_MAX_TRIES = 5                # a six-digit code, guessed five times, is not being guessed


def _mfa_ticket(uid: str) -> str:
    now = time.time()
    for k in [k for k, v in _mfa_tickets.items() if v[1] < now]:
        _mfa_tickets.pop(k, None)
    if len(_mfa_tickets) > 500:
        _mfa_tickets.clear()
    t = secrets.token_urlsafe(32)
    _mfa_tickets[t] = (str(uid), now + MFA_TICKET_SECONDS)
    return t


def _mfa_ticket_uid(ticket: str):
    """Who this half-login belongs to, or None. Expiry is checked here so a
    ticket left lying around stops working on its own."""
    v = _mfa_tickets.get(str(ticket or ""))
    if not v:
        return None
    uid, until = v
    if until < time.time():
        _mfa_tickets.pop(str(ticket), None)
        return None
    return uid


def _mfa_ticket_spend(ticket: str) -> None:
    """One ticket, one session. Leaving it usable would turn a single password
    entry into an unlimited supply of logins for as long as it lived."""
    _mfa_tickets.pop(str(ticket or ""), None)


def _new_session(uid: str) -> str:
    """Mint a session for a user. The raw token goes to the browser once;
    the store keeps only its hash, so the file can never impersonate anyone."""
    raw = secrets.token_urlsafe(32)
    key = hashlib.sha256(raw.encode()).hexdigest()
    s = _load_sessions()
    s[key] = {"uid": uid,
              "exp": (datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)).isoformat(),
              "created_at": datetime.now(timezone.utc).isoformat()}
    # A ceiling per account, oldest first. Every other store in the app has one;
    # without it a scripted login loop grows this file unboundedly and each mint
    # rewrites the whole thing.
    mine = sorted([(v.get("created_at") or "", k) for k, v in s.items() if v.get("uid") == uid])
    for _at, old_key in mine[:max(0, len(mine) - SESSIONS_PER_USER)]:
        s.pop(old_key, None)
    _write_sessions(s)
    return raw


def _session_uid(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = _load_sessions()
    row = s.get(hashlib.sha256(str(raw).encode()).hexdigest())
    if not row:
        return None
    now = datetime.now(timezone.utc)
    if str(row.get("exp") or "") < now.isoformat():
        return None
    try:
        born = datetime.fromisoformat(str(row.get("created_at") or ""))
        if (now - born).total_seconds() > SESSION_MAX_DAYS * 86400:
            s.pop(hashlib.sha256(str(raw).encode()).hexdigest(), None)
            _write_sessions(s)
            return None
    except ValueError:
        pass
    # Sliding window: steady work never logs you out mid-shift. The bump is
    # written at most every few hours, not per request.
    try:
        exp = datetime.fromisoformat(str(row.get("exp")))
        if (exp - now).total_seconds() < (SESSION_HOURS - 4) * 3600:
            row["exp"] = (now + timedelta(hours=SESSION_HOURS)).isoformat()
            _write_sessions(s)
    except Exception:
        pass  # the bump is a nicety: the session stands until its old expiry
    return str(row.get("uid") or "") or None


def _live_uid(request) -> str:
    """The caller's gizmo account id from the app session, but ONLY if that
    account is still real: present, switched on, not deleted, and past the
    forced first-password change. _session_uid alone answers "this token
    parses", which is not the same question - reading it raw let a starter
    password reach a route that _authorize would have refused."""
    uid = _session_uid(request.headers.get("x-app-session")) or ""
    if not uid:
        return ""
    u = _team_user(uid)
    if not u or u.get("deleted") or not u.get("active", True) or u.get("must_change"):
        return ""
    return uid


def _uid_has_tab(uid: str, tab: str) -> bool:
    tabs = _user_tabs(uid)
    return tabs is None or tab in tabs


def _drop_sessions(uid: Optional[str] = None, token: Optional[str] = None) -> None:
    s = _load_sessions()
    if token:
        s.pop(hashlib.sha256(str(token).encode()).hexdigest(), None)
    if uid:
        for k in [k for k, v in s.items() if v.get("uid") == uid]:
            s.pop(k)
    _write_sessions(s)


def _sessions_sweep() -> None:
    s = _load_sessions()
    now = datetime.now(timezone.utc).isoformat()
    dead = [k for k, v in s.items() if str(v.get("exp") or "") < now]
    if dead:
        for k in dead:
            s.pop(k)
        _write_sessions(s)


def _team_user(uid: Optional[str]) -> Optional[dict]:
    if not uid:
        return None
    u = _load_users()["users"].get(str(uid))
    return None if not u or u.get("deleted") else u


def _team_role(uid: Optional[str]) -> str:
    u = _team_user(uid)
    return u.get("role", "member") if u else "member"


def _team_level(uid: Optional[str]) -> int:
    return ROLE_LEVELS.get(_team_role(uid), 0) if _team_user(uid) else 0


def _team_name(uid: str) -> str:
    u = _load_users()["users"].get(str(uid))
    return (u or {}).get("name") or ""


def _team_names() -> dict:
    """uid -> display name, deleted accounts included: history keeps its
    names even after an account is removed."""
    return {uid: (u.get("name") or "") for uid, u in _load_users()["users"].items()}


# How long a break-glass password stays usable. Long enough to redeploy, read
# the log and sign in; short enough that the copy left in the deploy log is
# useless to anyone who reads it later.
MASTER_RESET_MINUTES = _env_num(int, os.environ.get("MASTER_RESET_MINUTES", "30"), "30", "MASTER_RESET_MINUTES")
_master_reset_done = False


def _master_reset_check(d: dict) -> None:
    """Break-glass for a forgotten master password: set MASTER_RESET=yes in
    Railway, redeploy, read the one-time password from the deploy logs, log
    in (forced to choose a new password), then REMOVE the variable."""
    global _master_reset_done
    if _master_reset_done or not os.environ.get("MASTER_RESET"):
        return
    _master_reset_done = True
    for uid, u in d["users"].items():
        if u.get("role") == "master" and not u.get("deleted"):
            starter = secrets.token_urlsafe(9)
            u["pw"] = _hash_pw(starter)
            u["must_change"] = True
            # The password goes into a deploy log that is retained and readable
            # by anyone with project access, so it must not stay usable. It is
            # for the next few minutes and the sign-in that follows; after that
            # the log holds a dead string.
            u["pw_expires_at"] = (datetime.now(timezone.utc)
                                  + timedelta(minutes=MASTER_RESET_MINUTES)).isoformat()
            u["fails"], u["lock_until"], u["locks"] = 0, "", 0
            try:
                _write_users(d)
            except Exception:
                logger.exception("master reset could not be saved")
                return
            logger.error("MASTER RESET: temporary password for %s is: %s  "
                         "It stops working in %d minutes. Sign in with it now, choose a "
                         "new password, and REMOVE the MASTER_RESET variable.",
                         u.get("username"), starter, MASTER_RESET_MINUTES,
                         # Deliberately in the platform's own log, where only the
                         # operator can read it - and deliberately NOT shipped to
                         # the log drain, which is a third party.
                         extra={"no_drain": True})
            activity._track(uid, "auth", "master password reset", "via the break-glass reset")
            return


# Tab access: which parts of the app an account may open. None means all.
# The master is never restricted. Enforcement is central (in _pre_checks) via
# this path map, so hiding a tab in the page is never the only lock.
TAB_KEYS = ("overview", "seo", "keywords", "products", "customers", "liability",
            "crm", "loans", "mail", "files", "labels", "sizes", "memory", "skills", "chat",
            "recon", "forecast", "connector")


# Tabs nobody inherits merely by having an account. Reconciliation holds the
# company's accounting records, its bank line and the finance mailbox, so a new
# stock or dispatch login must not arrive already holding the books: an admin
# hands it over deliberately, or not at all.
# The connector WRITES to the accounting ledger, so like the books it is
# handed over deliberately, never inherited with an account.
# The forecast holds the cash flow plan and where the company stands against
# it, which is the books' own kind of secret, so it is handed over the same way.
OPT_IN_TABS = ("recon", "connector", "forecast")
DEFAULT_TABS = tuple(k for k in TAB_KEYS if k not in OPT_IN_TABS)


def _user_tabs(uid: Optional[str]):
    """None = everything, and only the master gets that. An account with no
    tab list of its own gets the DEFAULT set, which is not the whole set. An
    id that names no live account (unknown, or deleted) gets nothing: this
    check fails closed rather than trusting every caller to have proven the
    account first."""
    u = _team_user(uid)
    if not u:
        return []
    if u.get("role") == "master":
        return None
    t = u.get("tabs")
    if not isinstance(t, list):
        return list(DEFAULT_TABS)
    return [k for k in t if k in TAB_KEYS]


def _team_counts(events: list, days: int = 30) -> dict:
    """Per-person tallies over the window, grouped the way the shop thinks:
    made, dispatched, files, sales desk, everything else."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    out: dict = {}
    for e in events:
        if e.get("t", "") < cutoff:
            continue
        sub = str(e.get("sub") or "")
        c = out.setdefault(sub, {"made": 0, "dispatched": 0, "files": 0, "crm": 0, "other": 0})
        a, area = str(e.get("action") or ""), e.get("area")
        # Tallies mean WORK: undos subtract, and only real completions add.
        if a == "marked made":
            c["made"] += 1
        elif a == "un-marked made":
            c["made"] -= 1
        elif a.startswith("booked a"):
            c["dispatched"] += 1
        elif a == "cancelled a shipment":
            c["dispatched"] -= 1
        elif a == "uploaded a file":
            c["files"] += 1
        elif area == "crm":
            c["crm"] += 1
        else:
            c["other"] += 1
    for c in out.values():
        for k in c:
            c[k] = max(0, c[k])
    return out


# ---------------------------------------------------------------------------
# Team colours, who may edit the Size list or send mail, first-run setup and
# its code, the account as the Team screen shows it, and the sign-in helpers.
# ---------------------------------------------------------------------------
# Who owns what, at a glance. The same names the CRM already uses, minus the two
# greys: as a row tint on an app that is already grey they would read as no
# colour at all.
TEAM_COLOUR_NAMES = ("blue", "green", "purple", "orange", "pink", "red",
                     "brown", "yellow")


def _next_team_colour(users: dict) -> str:
    """The first colour nobody is using. Two people sharing one defeats the
    point of glancing at a row and knowing whose it is, so it only repeats once
    the palette is genuinely exhausted - and then it repeats in a stable order
    rather than at random."""
    taken = {u.get("colour") for u in (users or {}).values() if not u.get("deleted")}
    for c in TEAM_COLOUR_NAMES:
        if c not in taken:
            return c
    return TEAM_COLOUR_NAMES[len(taken) % len(TEAM_COLOUR_NAMES)]


def _may_edit_sizes(uid: Optional[str]) -> bool:
    """Who may change what the bench actually cuts.

    Seeing the Labels tab is not enough. A size rule decides the glass a real
    order is made from, so it is a grant an admin makes deliberately per person,
    the same way a tab is - not something inherited by having an account. Admins
    hold it by rank; everyone else only if it was handed to them."""
    u = _team_user(uid)
    if not u:
        return False
    if ROLE_LEVELS.get(u.get("role"), 0) >= ROLE_LEVELS["admin"]:
        return True
    return bool(u.get("can_sizes"))


def _may_send_mail(uid: Optional[str]) -> bool:
    """Who may send email OUT of the shared mailbox, as the shop.

    The twin of _may_edit_sizes, and for the same reason. A draft is inert and
    a state change is undoable; an email that has gone is neither, and it goes
    over the shop's own address, so it is a grant an admin makes deliberately
    per person rather than something inherited by having an Inbox tab. Admins
    hold it by rank; everyone else only if it was handed to them."""
    u = _team_user(uid)
    if not u:
        return False
    if ROLE_LEVELS.get(u.get("role"), 0) >= ROLE_LEVELS["admin"]:
        return True
    return bool(u.get("can_send"))


def _team_setup_needed() -> bool:
    return not any(not u.get("deleted") for u in _load_users()["users"].values())


# First-run setup makes the master account, and it opens whenever the accounts
# register holds no live account: a new environment, a volume that is missing
# or replaced, a restore of an unrecognised register. It asked for nothing but
# a Shopify staff session, so whichever staff member opened the app first in
# that window became master: the backup, every role, the mailboxes (audit
# chain R-C5). It now also needs this code, set on the server by whoever runs
# it and removed after setup. Unset, setup stays locked.
SETUP_CODE = os.environ.get("SETUP_CODE", "").strip()  # set only while first-run setup is needed, then remove; unset locks setup


def _user_public(uid: str, u: dict) -> dict:
    """Everything about an account EXCEPT anything derived from its password."""
    return {"id": uid, "name": u.get("name") or "", "username": u.get("username") or "",
            "role": u.get("role") or "member", "active": u.get("active", True),
            "deleted": bool(u.get("deleted")), "must_change": bool(u.get("must_change")),
            "created_at": u.get("created_at") or "", "last_login_at": u.get("last_login_at") or "",
            "mfa": bool(u.get("mfa_secret")),
            "tabs": (None if u.get("role") == "master" or not isinstance(u.get("tabs"), list)
                     else u.get("tabs")),
            # Reported separately from the raw flag: an admin holds it by rank,
            # so the UI must not show a switch that looks revocable when it is not.
            "colour": u.get("colour") or "",
            "can_sizes": bool(u.get("can_sizes")),
            "sizes_by_rank": ROLE_LEVELS.get(u.get("role") or "member", 0) >= ROLE_LEVELS["admin"],
            # Sending email out as the shop reads the same way: the raw grant
            # and the by-rank one are reported apart, so the Team screen never
            # shows an admin a switch that would not actually revoke anything.
            "can_send": bool(u.get("can_send")),
            "send_by_rank": ROLE_LEVELS.get(u.get("role") or "member", 0) >= ROLE_LEVELS["admin"],
            # The current value travels with the list so an admin editing it
            # sees what they are overwriting rather than setting it blind.
            "sign_off": str(u.get("sign_off") or "")}

# ---- What the sign-in and Team routes share (gizmo/routes/team.py) ----------
# The app's own front door. Every one of those routes still demands the
# Shopify embed token first (the perimeter: requests must come from inside
# the shop's admin), and then deals in the app's own accounts and sessions.
def _shop_gate(request: Request) -> bool:
    auth = request.headers.get("authorization", "")
    if not (auth.startswith("Bearer ") and config.SHOPIFY_API_SECRET):
        return False
    try:
        _verify_session_token(auth[7:])
        return True
    except Exception:
        return False

async def _auth_guard(request: Request, model=None):
    pre = gate._pre_checks(request)
    if pre:
        return pre, None
    if not _shop_gate(request):
        return gate._json({"error": "Unauthorized"}, 401), None
    body = await gate._read_json_capped(request)
    if body is None:
        return gate._json({"error": "Request too large."}, 413), None
    # Before the sign-in ceiling and the password check: a field of the wrong
    # kind is no guess at a password, so it spends neither (gizmo/bodies.py).
    refused = gate._body_refusal(model, body) if model is not None else None
    if refused:
        return refused, None
    return None, body

def _clean_username(v) -> str:
    return re.sub(r"[^a-z0-9@._-]", "", str(v or "").strip().lower())[:80]

def _find_username(d: dict, username: str) -> Optional[str]:
    for uid, u in d["users"].items():
        if not u.get("deleted") and u.get("username") == username:
            return uid
    return None

def _starter_password() -> str:
    return secrets.token_urlsafe(9)

def _auth_me(uid: str, u: dict) -> dict:
    """The account as the BROWSER needs it the moment somebody is in: who
    they are, what they may open, and the grants the UI must not draw a
    button for without. One shape, written once - three hand-copied
    versions of it is exactly how the login reply and the state reply come
    to disagree about what a person is allowed to do."""
    return {"id": uid, "name": u.get("name"), "role": u.get("role"),
            "must_change": bool(u.get("must_change")),
            "tabs": _user_tabs(uid),
            # Sending email out as the shop is a per-person grant, and an
            # admin holds it by rank. Both, separately, because the page
            # must not offer a switch that would revoke nothing.
            "can_send": bool(u.get("can_send")),
            "send_by_rank": (ROLE_LEVELS.get(u.get("role") or "member", 0)
                             >= ROLE_LEVELS["admin"])}

# ---- Team management --------------------------------------------------
async def _team_guard(request: Request, min_level: int, model=None):
    err, body, who = await gate._guard(request, min_level=min_level, model=model)
    if err:
        return err, None
    return None, (who, body)

def _team_public_list(d: dict) -> list:
    users = [_user_public(uid, u) for uid, u in d["users"].items() if not u.get("deleted")]
    users.sort(key=lambda u: (-ROLE_LEVELS.get(u["role"], 0), u["name"] or "~"))
    return users


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as sibling.NAME, never a copied name.
from gizmo import activity  # noqa: E402
from gizmo import config  # noqa: E402
from gizmo import gate  # noqa: E402
