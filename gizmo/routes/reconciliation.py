"""The reconciliation routes and the Xero connect pair. Gathered from
add_routes (stage 4 of the 14 October audit) where the first stood; their
paths are literal, so no request changes hands.
"""
import logging
import time
import secrets
from datetime import datetime, timezone
import google_data
import google_mail
import recon as recon_engine
import xero as xero_api
from starlette.requests import Request
from starlette.responses import PlainTextResponse

import copilot as core
from gizmo import oauth
from gizmo import activity
from gizmo import gate
from gizmo import mail
from gizmo import orderbook
from gizmo import team
from gizmo import reconciliation

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


def register(mcp, registry):
    """Add the reconciliation routes and the Xero connect pair to the app."""





    @mcp.custom_route("/oauth/xero/start", methods=["GET"])
    async def xero_start(request: Request):
        if not gate._window_ok(gate._rl_hits.setdefault("oauth:" + gate._client_key(request), []), gate.RATE_MAX_CLIENT, time.monotonic()):
            return PlainTextResponse("Too many requests", status_code=429, headers=gate._API_HEADERS)
        if not xero_api.client_configured():
            return oauth._oauth_page("Not configured", "Add Xero's client ID and secret in the app's hosting settings first.")
        # A single-use ticket from the app's own button, or the standing secret
        # as the recovery path. Handing someone a link with a placeholder where
        # the secret goes is not a way in, and asking them to paste a server
        # secret into a browser bar never was either.
        ticket = request.query_params.get("t", "")
        tx = reconciliation._xero_connect_tickets.pop(ticket, None) if ticket else None
        by_secret = gate._secret_ok(request.query_params.get("key", ""), google_data.CONNECT_SECRET)
        if not ((tx is not None and tx > time.time()) or by_secret):
            return PlainTextResponse("Forbidden", status_code=403, headers=gate._API_HEADERS)
        now = time.time()
        for st, exp in list(reconciliation._xero_oauth_states.items()):
            if exp < now:
                reconciliation._xero_oauth_states.pop(st, None)
        state = secrets.token_urlsafe(24)
        reconciliation._xero_oauth_states[state] = now + 900
        from starlette.responses import RedirectResponse
        return RedirectResponse(xero_api.consent_url(reconciliation._xero_redirect_uri(request), state),
                                status_code=302)

    @mcp.custom_route("/oauth/xero/callback", methods=["GET"])
    async def xero_callback(request: Request):
        qp = request.query_params
        if qp.get("error"):
            return oauth._oauth_page("Connection cancelled", f"Xero returned: {qp.get('error')}")
        state = qp.get("state", "")
        exp = reconciliation._xero_oauth_states.pop(state, None)
        if not state or exp is None or exp < time.time():
            return oauth._oauth_page("Link expired", "That connect link expired or was already used. Start again.")
        code = qp.get("code", "")
        if not code:
            return oauth._oauth_page("Connection failed", "No authorization code returned.")
        try:
            ok = await xero_api.exchange_code(code, reconciliation._xero_redirect_uri(request))
        except Exception:
            logger.exception("Xero OAuth exchange error")
            ok = False
        if not ok:
            return oauth._oauth_page("Connection failed", "Couldn't complete the Xero connection. Please try again.")
        return oauth._oauth_page("Connected to Xero",
                           "The reconciliation engine can now read your accounts (read-only). "
                           "Close this tab and return to Reactor.")

    @mcp.custom_route("/api/recon/status", methods=["POST"])
    async def recon_status_route(request: Request):
        err, body, who = await gate._guard(request)
        if err:
            return err
        d = reconciliation._load_recon()
        docs = reconciliation._load_recon_docs()
        xs = xero_api.status()
        setup = {}
        if team._team_role(who) == "master" and not xs["connected"]:
            # The setup aids, like Gmail's: the EXACT redirect URI and the env
            # var names, so the developer-app walk cannot go wrong by a
            # character. The secret itself never appears anywhere.
            setup = {"redirect_uri": reconciliation._xero_redirect_uri(request),
                     "can_connect": True,
                     # What the app will ask Xero for. Shown because a scope
                     # the app was not ASSIGNED fails the whole authorization
                     # with invalid_scope, and the only way to see the
                     # mismatch is to compare this against the app's page.
                     "scopes": xero_api.SCOPES.split(),
                     "env_needed": ["XERO_CLIENT_ID", "XERO_CLIENT_SECRET"],
                     "configured": xs["configured"]}
        fin = google_mail.status(google_mail.FINANCE)
        open_counts, open_amounts = reconciliation._recon_open_summary(d)
        return gate._json({"xero": xs, "setup": setup,
                      "gmail": fin["connected"],
                      "mailbox": {"connected": fin["connected"],
                                  "address": fin["address"],
                                  "client": fin["client"],
                                  "can_connect": team._team_role(who) == "master",
                                  "redirect_uri": oauth._gmail_fin_redirect_uri(request),
                                  # The Cloud project is the numeric prefix of the
                                  # client id, so the console link can go straight
                                  # to the right project instead of whichever one
                                  # the browser last had open.
                                  "project": google_mail.project_number(),
                                  # Named so a wrong-account consent is obvious.
                                  "sales_address": google_mail.address()},
                      "model": reconciliation.MODEL_RECON,
                      "last_sync": d.get("last_sync") or "",
                      "sweep_notes": d.get("last_notes") or [],
                      "open_counts": open_counts,
                      "open_amounts": open_amounts,
                      "docs": len(docs),
                      "sweeping": recon_engine._sweeping["on"]})

    @mcp.custom_route("/api/recon/xero-link", methods=["POST"])
    async def recon_xero_link_route(request: Request):
        """Master-only: a single-use ticket for the Xero consent walk."""
        err, _body, who = await gate._guard(request, body=False)
        if err:
            return err
        if team._team_role(who) != "master":
            return gate._json({"error": "Only the master account can connect Xero."}, 403)
        if not xero_api.client_configured():
            return gate._json({"error": "The server has no Xero credentials yet. Add Xero's client ID "
                                   "and secret in the app's hosting settings, then redeploy."}, 400)
        now = time.time()
        for t, exp in list(reconciliation._xero_connect_tickets.items()):
            if exp < now:
                reconciliation._xero_connect_tickets.pop(t, None)
        ticket = secrets.token_urlsafe(24)
        reconciliation._xero_connect_tickets[ticket] = now + mail.MAIL_TICKET_SECONDS
        activity._track(who, "recon", "started connecting Xero")
        return gate._json({"url": f"/oauth/xero/start?t={ticket}",
                      "expires_in": mail.MAIL_TICKET_SECONDS})

    @mcp.custom_route("/api/recon/connect-link", methods=["POST"])
    async def recon_connect_link_route(request: Request):
        """Master-only: mint a single-use ticket for the accounts-mailbox
        consent walk, so nobody has to paste a server secret into a URL."""
        err, _body, who = await gate._guard(request, body=False)
        if err:
            return err
        if team._team_role(who) != "master":
            return gate._json({"error": "Only the master account can connect the accounts mailbox."}, 403)
        body = await gate._read_json_capped(request)
        if body is None:
            return gate._json({"error": "Request too large."}, 413)
        if not google_mail.client_configured():
            return gate._json({"error": "The server has no Google client configured yet. "
                                   "Add Google's client ID and secret in the app's hosting settings."}, 400)
        if not google_mail.FINANCE.usable():
            return gate._json({"error": "The accounts mailbox is set to the same token file as the "
                                   "sales inbox. Give it its own token file in the app's hosting settings."}, 400)
        now = time.time()
        for t, exp in list(oauth._fin_connect_tickets.items()):
            if exp < now:
                oauth._fin_connect_tickets.pop(t, None)
        # The address they mean, so Google opens THAT account rather than
        # whichever one this browser is already signed into.
        want = str((body or {}).get("address") or "").strip()[:200]
        if not want:
            return gate._json({"error": "Type the accounts mailbox address first. Without it "
                                   "Google opens whichever account this browser is already "
                                   "signed into."}, 400)
        if not orderbook._EDIT_EMAIL.match(want):
            return gate._json({"error": "That does not look like an email address."}, 400)
        if want.strip().lower() == (google_mail.address() or "").strip().lower():
            return gate._json({"error": "That is the Inbox tab's mailbox. Reconciliation needs the "
                                   "ACCOUNTS mailbox, which is a different Google account."}, 400)
        ticket = secrets.token_urlsafe(24)
        oauth._fin_connect_tickets[ticket] = {"exp": now + mail.MAIL_TICKET_SECONDS, "want": want}
        activity._track(who, "recon", "started connecting the accounts mailbox", want)
        return gate._json({"url": f"/oauth/gmail-finance/start?t={ticket}",
                      "expires_in": mail.MAIL_TICKET_SECONDS})

    @mcp.custom_route("/api/recon/disconnect", methods=["POST"])
    async def recon_disconnect_route(request: Request):
        """Disconnect Xero or the accounts mailbox, and mean it.

        Revoking at the provider is the point: a refresh token we merely
        forget stays valid at Xero for up to 60 days and at Google until
        someone notices. The Xero-derived cache goes with it, because keeping
        a copy of the books after the merchant said stop is not defensible."""
        err, _body, who = await gate._guard(request, body=False)
        if err:
            return err
        if team._team_role(who) != "master":
            return gate._json({"error": "Only the master account can disconnect."}, 403)
        body = await gate._read_json_capped(request)
        if body is None:
            return gate._json({"error": "Request too large."}, 413)
        what = str(body.get("what") or "")
        force = bool(body.get("force"))
        if recon_engine is not None and recon_engine._sweeping["on"]:
            # A sweep loads the books and the documents at its start and
            # writes them back whole at its end, minutes later. Disconnecting
            # in between deleted them and then watched the sweep's tail put
            # every invoice and the old watermarks straight back.
            return gate._json({"error": "A reconciliation sweep is running. Wait for it to "
                                   "finish, then disconnect."}, 409)
        notes = []
        if what == "xero":
            r = await xero_api.revoke(force=force)
            if r.get("kept"):
                # Xero would not accept the revocation, so the token is still
                # ours and still live. Deleting the books now would leave a
                # connected app with nothing to show for it: stop, say so, and
                # let them retry or force it.
                return gate._json({"ok": False, "kept": True, "error": r.get("note") or
                              "Xero would not accept the revocation.",
                              "can_force": True}, 502)
            if r.get("note"):
                notes.append(r["note"])
            # The books go too. The exception list stays: it is the audit
            # trail of what was found, and it is the merchant's own record.
            cache = reconciliation._load_recon_cache()
            if cache.pop("xero", None) is not None:
                reconciliation._write_recon_cache(cache)
                notes.append("The cached copy of the Xero records was deleted.")
            d = reconciliation._load_recon()
            d.pop("watermarks", None)
            reconciliation._write_recon(d)
            activity._track(who, "recon", "disconnected Xero", " ".join(notes)[:120])
        elif what == "mailbox":
            google_mail.disconnect(google_mail.FINANCE)
            docs = reconciliation._load_recon_docs()
            if docs:
                reconciliation._write_recon_docs({})
                notes.append(f"{len(docs)} extracted documents were deleted.")
            d = reconciliation._load_recon()
            for k in ("seen_threads", "seen_history", "doc_tries", "recheck_threads"):
                d.pop(k, None)      # what was read from that mailbox goes with it
            reconciliation._write_recon(d)
            activity._track(who, "recon", "disconnected the accounts mailbox", " ".join(notes)[:120])
            notes.append("Google keeps its own record of the grant: remove this app's access at "
                         "myaccount.google.com/permissions to be certain it is gone.")
        else:
            return gate._json({"error": "Say what to disconnect: xero or mailbox."}, 400)
        return gate._json({"ok": True, "notes": notes})

    @mcp.custom_route("/api/recon/sweep", methods=["POST"])
    async def recon_sweep_route(request: Request):
        # ai=True: a sweep can read documents with the model. The rank is
        # checked before the AI slot is spent, so a member cannot burn one.
        err, body, who = await gate._guard(request, ai=True, min_level=team.ROLE_LEVELS["admin"])
        if err:
            return err
        if not xero_api.connected():
            return gate._json({"error": "Connect Xero first: without the accounts there is "
                                   "nothing to reconcile against."}, 400)
        try:
            r = await recon_engine.sweep()
        except Exception:
            logger.exception("recon sweep failed")
            return gate._json({"error": "The sweep failed part-way. Check the server logs."}, 502)
        activity._track(who, "recon", "ran a reconciliation sweep",
               str(r.get("exceptions", 0)) + " open items")
        return gate._json(r)

    @mcp.custom_route("/api/recon/exceptions", methods=["POST"])
    async def recon_exceptions_route(request: Request):
        err, body, who = await gate._guard(request)
        if err:
            return err
        d = reconciliation._load_recon()
        rows = reconciliation._recon_filter(d.get("exceptions", {}),
                             severity=str(body.get("severity") or ""),
                             status=str(body.get("status") or ""),
                             q=str(body.get("q") or "")[:120],
                             min_pence=int(body.get("min_pence") or 0),
                             include_stale=bool(body.get("include_stale")))
        # The CSV export asks for everything; the browser list stays modest.
        cap = min(int(body.get("limit") or 400), 5000)
        return gate._json({"count": len(rows),
                      "exceptions": [reconciliation._recon_exc_public(e) for e in rows[:cap]]})

    @mcp.custom_route("/api/recon/exception", methods=["POST"])
    async def recon_exception_route(request: Request):
        err, body, who = await gate._guard(request)
        if err:
            return err
        d = reconciliation._load_recon()
        e = d.get("exceptions", {}).get(str(body.get("id") or ""))
        if not e:
            return gate._json({"error": "That discrepancy no longer exists."}, 404)
        op = str(body.get("op") or "")
        if not op:
            return gate._json({"exception": reconciliation._recon_exc_public(e, full=True)})
        if op == "status":
            new = str(body.get("status") or "")
            if new not in recon_engine.STATUSES:
                return gate._json({"error": "Unknown status."}, 400)
            note = str(body.get("note") or "").strip()[:400]
            if new == "ignored" and not note:
                # An unexplained ignore is how a real discrepancy disappears.
                return gate._json({"error": "Ignoring a discrepancy needs a reason."}, 400)
            e["history"] = (e.get("history") or []) + [{
                "at": datetime.now(timezone.utc).isoformat(),
                "by": team._team_name(who) or who, "from": e["status"], "to": new, "note": note}]
            e["status"], e["status_note"] = new, note
            e["updated"] = datetime.now(timezone.utc).isoformat()
            reconciliation._write_recon(d)
            activity._track(who, "recon", "set a discrepancy to " + new, e["title"][:60])
            return gate._json({"ok": True, "exception": reconciliation._recon_exc_public(e, full=True)})
        if op == "investigate":
            # The same global AI budget as chat: an investigation is a model
            # call, and the limiter exists so one tab cannot starve the rest.
            if not gate._window_ok(gate._rl_global, gate.RATE_MAX_GLOBAL, time.monotonic()):
                return gate._json({"error": "The assistant is busy right now. Try again shortly."}, 429)
            verdict = await recon_engine.investigate(e, reconciliation._load_recon_cache())
            # RELOAD before writing: the AI call awaited for seconds, and a
            # sweep may have rewritten the store underneath. Writing the copy
            # from before the await would clobber the sweep - the lost-update
            # this codebase's single-writer rule exists to prevent.
            d = reconciliation._load_recon()
            e = d.get("exceptions", {}).get(str(body.get("id") or ""))
            if not e:
                return gate._json({"error": "That discrepancy disappeared while the AI was reading it."}, 409)
            e["ai"] = verdict
            e["updated"] = datetime.now(timezone.utc).isoformat()
            reconciliation._write_recon(d)
            activity._track(who, "recon", "asked the AI to investigate", e["title"][:60])
            return gate._json({"ok": True, "exception": reconciliation._recon_exc_public(e, full=True)})
        return gate._json({"error": "Unknown op."}, 400)
