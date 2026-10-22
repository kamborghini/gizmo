"""The sign-in walk's one-time states and the page it answers with (the
Inbox's mailbox walk reads them from here). Moved out of copilot.py (stage 4
of the 14 October audit); the Google data, accounts mailbox and Xero walks
went on 22 Oct 2026. Read as `oauth.NAME`.
"""
import logging
import html
from starlette.responses import HTMLResponse

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


_oauth_states: dict[str, float] = {}


# ---------------------------------------------------------------------------
# The page every walk answers with.
# ---------------------------------------------------------------------------

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

# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as sibling.NAME, never a copied name.
from gizmo import gate  # noqa: E402
