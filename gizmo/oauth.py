"""The sign-in walks: the one-time states, the redirect address and the page
every walk answers with (the inbox's and Xero's walks read them from here),
and the accounts mailbox's tickets. Moved out of copilot.py (stage 4 of the
14 October audit); the Google and accounts-mailbox walks' routes are in
gizmo/routes/oauth.py. Read as `oauth.NAME`.
"""
import logging
import html
from starlette.requests import Request
from starlette.responses import HTMLResponse

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


_oauth_states: dict[str, float] = {}


# ---------------------------------------------------------------------------
# The sign-in walks: the accounts mailbox's tickets and states, held in memory,
# the redirect address and the page every walk answers with.
# ---------------------------------------------------------------------------
_fin_connect_tickets: dict = {}      # ticket -> its expiry and the address asked for (the ACCOUNTS mailbox)
_fin_expect: dict = {}               # state nonce -> the address that was asked for

# ----- Google OAuth connect flow (one-time, secret-gated) -------------
def _redirect_uri(request: Request) -> str:
    # Prefer a configured public base URL (must match the URI registered in
    # Google Cloud) over the attacker-controllable Host header.
    if core.APP_BASE_URL:
        return core.APP_BASE_URL.rstrip("/") + "/oauth/google/callback"
    host = request.headers.get("host", "")
    return f"https://{host}/oauth/google/callback"

def _oauth_page(title: str, msg: str) -> HTMLResponse:
    # Escape both inputs (any reflected query value is neutralized) and ship a
    # locked-down CSP: no scripts at all, only inline styles. Defense in depth.
    t, m = html.escape(str(title)), html.escape(str(msg))
    body = (f"<!doctype html><meta charset=utf-8><title>{t}</title>"
            "<style>body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#f7f7f8;"
            "color:#16161a;display:grid;place-items:center;height:100vh;margin:0}"
            ".c{background:#fff;border:1px solid #e7e7ea;border-radius:14px;padding:28px 32px;"
            "max-width:420px;text-align:center;box-shadow:0 6px 24px -6px rgba(20,20,40,.1)}"
            "h1{font-size:17px;margin:0 0 8px}p{color:#5c5f66;font-size:14px;margin:0}</style>"
            f"<div class=c><h1>{t}</h1><p>{m}</p></div>")
    headers = {"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
               "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
               **gate._API_HEADERS}
    return HTMLResponse(body, headers=headers)

# ----- the ACCOUNTS mailbox: a second Google account, for reconciliation -
# Same OAuth client and scope as the sales inbox, its own refresh token,
# its own consent walk, its own state namespace. The two can never
# complete each other's flow, and neither can reach the other's mail.
def _gmail_fin_redirect_uri(request: Request) -> str:
    if core.APP_BASE_URL:
        return core.APP_BASE_URL.rstrip("/") + "/oauth/gmail-finance/callback"
    host = request.headers.get("host", "")
    return f"https://{host}/oauth/gmail-finance/callback"


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
from gizmo import gate  # noqa: E402
import copilot as core  # noqa: E402
