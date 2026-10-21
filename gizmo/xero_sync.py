"""The Xero sync settings: which of the connector's settings may be read and
set, and how, and the connector's address and the call to it. Moved out of
copilot.py (stage 4 of the 14 October audit); its route is in
gizmo/routes/xero_sync.py. Read as `xerosync.NAME` (`connector` is a local
name in a test).
"""
import logging
import os
from typing import Optional
from urllib.parse import urlparse
import httpx

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")




def _connector_url() -> str:
    """Where the shopify-xero-connector service lives (Railway private network).
    Read per request so tests and redeploys never need a restart dance."""
    return (os.environ.get("CONNECTOR_URL") or "").rstrip("/")


def _connector_url_safe(url: str) -> bool:
    """The bearer token rides on every call. Railway's private network is
    encrypted and its names end .railway.internal; anything else has to be
    https. A typo'd public http:// host would put the token on the wire in
    the clear on every poll, with no symptom at all."""
    u = urlparse(url or "")
    return bool(u.scheme == "https"
                or (u.hostname or "").endswith(".railway.internal")
                or (u.hostname or "") in ("localhost", "127.0.0.1", "::1"))


async def _connector_call(method: str, path: str, params: Optional[dict] = None,
                          json_body: Optional[dict] = None):
    """One call to the connector service. The service's own token rides in the
    Authorization header and NEVER leaves this process; X-Connector is its CSRF
    header for anything mutating. Transport failure raises, so the route can
    say plainly that the service is unreachable, as opposed to the service
    answering with an error of its own (returned as-is).

    params go in the query string, which is where most of the service's doors
    read them. json_body goes as a JSON body, for a door that reads only its
    body: POST /api/settings does, and a save sent as params was answered ok
    and kept nothing, from the day the page was built to 12 Oct 2026."""
    headers = {}
    token = os.environ.get("CONNECTOR_TOKEN") or ""
    if token and not _connector_url_safe(_connector_url()):
        raise RuntimeError("The connector's address is neither https nor on the hosting's private network, "
                           "so the connector token will not be sent to it.")
    if token:
        headers["Authorization"] = "Bearer " + token
    if method == "POST":
        headers["X-Connector"] = "1"
    async with httpx.AsyncClient(timeout=25.0) as cx:
        r = await cx.request(method, _connector_url() + path, params=params, json=json_body,
                             headers=headers)
    try:
        body = r.json()
    except Exception:
        body = {"error": ("The connector answered with something that is not JSON "
                          "(status " + str(r.status_code) + ").")}
    return r.status_code, body


# ---------------------------------------------------------------------------
# Shopify -> Xero connector: a separate, audited Node service that turns
# orders into Xero invoices (and refunds into credit notes). It writes to
# the accounting ledger, so gizmo only ever PROXIES it: the browser talks
# to this route, this route talks to the service on the private network,
# and the service's token never leaves the server. Reviews are dry runs
# (the service persists nothing on them); anything that writes is admin.
# ---------------------------------------------------------------------------
_CONNECTOR_READS = {
    "status": ("GET", "/api/status"),
    "runs": ("GET", "/api/runs"),
    "quarantine": ("GET", "/api/quarantine"),
    "ledger": ("GET", "/api/ledger"),
    "health": ("GET", "/api/health"),
    "autorun": ("GET", "/api/autorun"),
    # Reading settings is safe: the service returns secrets as presence
    # flags and never their values, which a test here checks.
    "settings": ("GET", "/api/settings"),
}
# The settings the Xero sync page may change. Deliberately a short list of
# OPERATIONAL knobs: nothing here can point the service at a different shop,
# a different Xero organisation, or a different set of credentials.
# SHOP_TIMEZONE is not here: the connector neither accepts nor returns it (it
# is not in its SETTING_FIELDS), so offering it made Save say "Saved" over
# nothing. It is set on the connector service itself.
# AUTO_RUN_INTERVAL_MINUTES is how often Auto Run looks, 5 to 1440 minutes:
# operational like the rest, and the connector applies a change at once.
_CONNECTOR_SETTABLE = {
    "RECONCILE_MODE", "RECONCILE_TOLERANCE", "MAX_DOCS_PER_RUN", "RUNAWAY_ABORT_ABOVE",
    "ORDERS_SINCE", "XERO_SALES_ACCOUNT_CODE",
    "XERO_TAX_TYPE_STANDARD", "XERO_TAX_TYPE_ZERO",
    "CUSTOMER_REF_METAFIELD_NAMESPACE", "CUSTOMER_REF_METAFIELD_KEY",
    "AUTO_RUN_INTERVAL_MINUTES",
}
# Kept as numbers by the connector, so 0.50 comes back as 0.5.
_CONNECTOR_NUMERIC = {"RECONCILE_TOLERANCE", "MAX_DOCS_PER_RUN", "RUNAWAY_ABORT_ABOVE", "AUTO_RUN_INTERVAL_MINUTES"}


def _connector_settings_unapplied(sent: dict, now: dict) -> list:
    """The fields a save sent that the connector's settings, read straight
    after, do not show. The page said "Saved" for as long as the connector
    answered ok, and that answer came for a save that kept nothing, so a save
    is now judged by what the connector holds afterwards.

    A value is kept when it reads back the same (numbers by value, as the
    connector stores them in their own form). A blank clears a saved choice,
    so it is kept when the field no longer comes from a saved choice; a
    connector too old to say where values come from cannot show that, and a
    blank is taken on trust there."""
    sources = now.get("sources") if isinstance(now.get("sources"), dict) else None
    missed = []
    for k in sorted(sent):
        v = str(sent[k] or "").strip()
        if not v:
            if sources is not None and sources.get(k) == "settings":
                missed.append(k)
            continue
        got = str(now.get(k) if now.get(k) is not None else "").strip()
        if got == v:
            continue
        if k in _CONNECTOR_NUMERIC:
            try:
                if float(got) == float(v):
                    continue
            except ValueError:
                pass
        missed.append(k)
    return missed


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
import copilot as core  # noqa: E402
