"""The Google and accounts-mailbox sign-in walks: start and callback for each.
Gathered from add_routes (stage 4 of the 14 October audit) where the first
stood; their paths are literal, so no request changes hands.
"""
import logging
import time
import secrets
import google_data
import google_mail
from starlette.requests import Request
from starlette.responses import PlainTextResponse

import copilot as core
from gizmo import gate
from gizmo import oauth

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


def register(mcp, registry):
    """Add the Google and accounts-mailbox sign-in walks to the app."""

    @mcp.custom_route("/oauth/google/start", methods=["GET"])
    async def google_start(request: Request):
        if not gate._window_ok(gate._rl_hits.setdefault("oauth:" + gate._client_key(request), []), gate.RATE_MAX_CLIENT, time.monotonic()):
            return PlainTextResponse("Too many requests", status_code=429, headers=gate._API_HEADERS)
        if not google_data.oauth_client_configured():
            return oauth._oauth_page("Not configured", "Add Google's client ID and secret in the app's hosting settings first.")
        key = request.query_params.get("key", "")
        if not (google_data.CONNECT_SECRET and key and
                secrets.compare_digest(key, google_data.CONNECT_SECRET)):
            return PlainTextResponse("Forbidden", status_code=403, headers=gate._API_HEADERS)
        now = time.time()
        for s, exp in list(oauth._oauth_states.items()):  # prune expired
            if exp < now:
                oauth._oauth_states.pop(s, None)
        state = secrets.token_urlsafe(24)
        oauth._oauth_states[state] = now + 900  # 15-minute TTL
        from starlette.responses import RedirectResponse
        return RedirectResponse(google_data.consent_url(oauth._redirect_uri(request), state), status_code=302)

    @mcp.custom_route("/oauth/google/callback", methods=["GET"])
    async def google_callback(request: Request):
        qp = request.query_params
        if qp.get("error"):
            return oauth._oauth_page("Connection cancelled", f"Google returned: {qp.get('error')}")
        state = qp.get("state", "")
        exp = oauth._oauth_states.pop(state, None)  # single-use
        if not state or exp is None or exp < time.time():
            return oauth._oauth_page("Link expired", "That connect link expired or was already used. Start again.")
        code = qp.get("code", "")
        if not code:
            return oauth._oauth_page("Connection failed", "No authorization code returned.")
        try:
            got = await google_data.exchange_code(code, oauth._redirect_uri(request))
        except Exception:
            logger.exception("Google OAuth exchange error")
            got = {"ok": False, "granted": {}}
        granted = got.get("granted") or {}
        names = {"gsc": "Search Console", "ga4": "Analytics"}
        left = [names[k] for k in ("gsc", "ga4") if granted.get(k) is False]
        if not got.get("ok"):
            if granted and len(left) == len(names):
                return oauth._oauth_page("Nothing was linked",
                                   "Search Console and Analytics were both left unticked on Google's "
                                   "screen, so Reactor could read neither. Connect again and leave them ticked.")
            return oauth._oauth_page("Connection failed", "Couldn't complete the connection. Please try again.")
        if left:
            kept = [n for k, n in names.items() if granted.get(k)]
            return oauth._oauth_page("✅ Connected to Google, without " + left[0],
                               kept[0] + " is linked. " + left[0] + " was left unticked on Google's screen, "
                               "so Reactor can't read it: connect again and leave it ticked.")
        return oauth._oauth_page("✅ Connected to Google", "Search Console & Analytics are now linked. "
                           "You can close this tab and return to Reactor.")


    @mcp.custom_route("/oauth/gmail-finance/start", methods=["GET"])
    async def gmail_finance_start(request: Request):
        if not gate._window_ok(gate._rl_hits.setdefault("oauth:" + gate._client_key(request), []),
                          gate.RATE_MAX_CLIENT, time.monotonic()):
            return PlainTextResponse("Too many requests", status_code=429, headers=gate._API_HEADERS)
        if not google_mail.client_configured():
            return oauth._oauth_page("Not configured", "Add Google's client ID and secret in the app's hosting settings first.")
        if not google_mail.FINANCE.usable():
            return oauth._oauth_page("Not configured",
                               "The accounts mailbox is set to the same token file as the "
                               "sales inbox. Give it its own token file in the app's "
                               "hosting settings, then try again.")
        # Two ways in, the same as the sales mailbox: a single-use ticket minted
        # for the master through the app (the button), or the standing connect
        # secret, kept so the mailbox is recoverable when nobody can sign in.
        ticket = request.query_params.get("t", "")
        tx = oauth._fin_connect_tickets.pop(ticket, None) if ticket else None
        by_secret = gate._secret_ok(request.query_params.get("key", ""), google_data.CONNECT_SECRET)
        live = isinstance(tx, dict) and tx.get("exp", 0) > time.time()
        if not (live or by_secret):
            return PlainTextResponse("Forbidden", status_code=403, headers=gate._API_HEADERS)
        now = time.time()
        for st, exp in list(oauth._oauth_states.items()):
            if exp < now:
                oauth._oauth_states.pop(st, None)
        state = secrets.token_urlsafe(24)
        oauth._oauth_states["gmfin:" + state] = now + 900
        want = (tx or {}).get("want", "") if live else ""
        if want:
            oauth._fin_expect[state] = want
        for st in [k for k, v in list(oauth._fin_expect.items()) if ("gmfin:" + k) not in oauth._oauth_states]:
            oauth._fin_expect.pop(st, None)          # never outlive their own state
        from starlette.responses import RedirectResponse
        return RedirectResponse(
            google_mail.consent_url(oauth._gmail_fin_redirect_uri(request), state, want),
            status_code=302)

    @mcp.custom_route("/oauth/gmail-finance/callback", methods=["GET"])
    async def gmail_finance_callback(request: Request):
        qp = request.query_params
        if qp.get("error"):
            return oauth._oauth_page("Connection cancelled", f"Google returned: {qp.get('error')}")
        state = qp.get("state", "")
        exp = oauth._oauth_states.pop("gmfin:" + state, None)
        if not state or exp is None or exp < time.time():
            return oauth._oauth_page("Link expired", "That connect link expired or was already used. Start again.")
        code = qp.get("code", "")
        if not code:
            return oauth._oauth_page("Connection failed", "No authorization code returned.")
        try:
            ok = await google_mail.exchange_code(code, oauth._gmail_fin_redirect_uri(request),
                                                 google_mail.FINANCE)
        except Exception:
            logger.exception("Gmail (accounts) OAuth exchange error")
            ok = False
        if not ok:
            # The vague version of this page sent people round the loop with
            # nothing to act on. These are the two causes in practice, in the
            # order they actually happen.
            return oauth._oauth_page(
                "Connection failed",
                "Google would not complete the sign-in. Two things cause this: the callback "
                "URL " + oauth._gmail_fin_redirect_uri(request) + " is not listed in the OAuth "
                "client's authorised redirect URIs, or the sign-in was cancelled part-way. "
                "Add that exact URL in the Google console, then press Connect again.")
        addr = google_mail.address(google_mail.FINANCE) or "the mailbox"
        want = oauth._fin_expect.pop(state, "")
        if want and addr.strip().lower() != want.strip().lower():
            # They named the mailbox; Google connected a different one, which is
            # what happens when the browser is already signed in elsewhere.
            google_mail.disconnect(google_mail.FINANCE)
            return oauth._oauth_page("Wrong mailbox",
                               f"You asked for {want} but the sign-in connected {addr}. "
                               "Nothing was saved. Sign out of Google, or use a private "
                               "window, and try again.")
        sales = google_mail.address()
        if sales and addr.strip().lower() == sales.strip().lower():
            # Consenting as the sales mailbox again would leave reconciliation
            # reading the wrong post. Refuse it rather than quietly agreeing.
            google_mail.disconnect(google_mail.FINANCE)
            return oauth._oauth_page("That is the sales mailbox",
                               f"{addr} is already connected as the Inbox tab's mailbox. "
                               "Sign in as the ACCOUNTS mailbox instead, then try again.")
        return oauth._oauth_page("Accounts mailbox connected",
                           f"{addr} is now linked to Reconciliation only. It does not appear in "
                           "the Inbox tab, and the Inbox tab's mailbox is not read by "
                           "reconciliation. You can close this tab.")
