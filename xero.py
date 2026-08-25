"""Xero Accounting API — READ ONLY, deliberately.

This module is the accounts side of the reconciliation engine. It can list
invoices, bills, payments, credit notes, bank transactions, contacts, accounts
and journals; it cannot create, update, allocate, reconcile or delete anything.
There are no write methods to gate, hide or audit, which is the strongest
guarantee available: the tool that checks the books must not be able to bend
them. If write-back is ever wanted, it is a separate capability behind explicit
human approval, not an extension of this client.

Environment:
  XERO_CLIENT_ID       OAuth2 client id from developer.xero.com (Railway env)
  XERO_CLIENT_SECRET   OAuth2 client secret (Railway env, never in the app)
  XERO_TOKEN_PATH      where the rotating refresh token lives (data volume)
  XERO_API_BASE        override for tests only (default https://api.xero.com)
  XERO_IDENTITY_BASE   override for tests only (default https://identity.xero.com)
  XERO_LOGIN_BASE      override for tests only (default https://login.xero.com)

Token mechanics (Xero specifics that bite if forgotten):
  * access tokens last ~30 minutes;
  * refresh tokens are SINGLE USE and rotate on every refresh - the new one
    must be durably written before the old one is considered spent, and two
    concurrent refreshes will kill the connection, so refresh is serialized;
  * a refresh token unused for 60 days dies, hence the scheduler's ping;
  * the tenant id comes from GET /connections after consent and rides on every
    API call in the xero-tenant-id header.

Rate limits: 60 calls/minute, 5000/day per tenant. The client self-paces under
the minute limit and honours 429 Retry-After with a ceiling (the same rule as
the Shopify layer: a sleep must never park the app for an hour).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.parse
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

CLIENT_ID = os.environ.get("XERO_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("XERO_CLIENT_SECRET", "")
TOKEN_PATH = os.environ.get("XERO_TOKEN_PATH", os.path.join(
    os.environ.get("DATA_DIR", "data"), "xero_oauth.json"))
API_BASE = os.environ.get("XERO_API_BASE", "https://api.xero.com")
IDENTITY_BASE = os.environ.get("XERO_IDENTITY_BASE", "https://identity.xero.com")
LOGIN_BASE = os.environ.get("XERO_LOGIN_BASE", "https://login.xero.com")

# Read-only scopes, and offline_access for the refresh token. accounting.reports.read
# covers balances; accounting.attachments.read lets the audit trail show source docs.
SCOPES = ("offline_access accounting.transactions.read accounting.contacts.read "
          "accounting.settings.read accounting.reports.read accounting.attachments.read")

_state: dict = {"access": "", "access_exp": 0.0, "tenant": "", "tenant_name": ""}
_refresh_lock = asyncio.Lock()
# Self-pacing: timestamps of recent calls, kept under the 60/minute ceiling.
_recent_calls: list = []
_MINUTE_BUDGET = 55          # a little headroom under Xero's 60


def client_configured() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET)


def _load_token() -> dict:
    try:
        with open(TOKEN_PATH, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        logger.exception("xero: token file unreadable")
        return {}


def _write_token(d: dict) -> None:
    os.makedirs(os.path.dirname(TOKEN_PATH) or ".", exist_ok=True)
    tmp = TOKEN_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh)
    os.replace(tmp, TOKEN_PATH)


def connected() -> bool:
    d = _load_token()
    return bool(d.get("refresh_token") and d.get("tenant_id"))


def tenant_name() -> str:
    return str(_load_token().get("tenant_name") or "")


def disconnect() -> None:
    """Forget the tokens. The Xero-side grant is revoked from Xero's own UI."""
    try:
        os.remove(TOKEN_PATH)
    except FileNotFoundError:
        pass
    _state.update({"access": "", "access_exp": 0.0, "tenant": "", "tenant_name": ""})


def consent_url(redirect_uri: str, state: str) -> str:
    q = urllib.parse.urlencode({
        "response_type": "code", "client_id": CLIENT_ID,
        "redirect_uri": redirect_uri, "scope": SCOPES, "state": state})
    return f"{LOGIN_BASE}/identity/connect/authorize?{q}"


async def _token_request(data: dict) -> Optional[dict]:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{IDENTITY_BASE}/connect/token", data=data,
                auth=(CLIENT_ID, CLIENT_SECRET), timeout=30.0)
        if resp.status_code != 200:
            logger.error("xero token endpoint answered %s: %s",
                         resp.status_code, resp.text[:200])
            return None
        return resp.json()
    except Exception:
        logger.exception("xero token request failed")
        return None


async def exchange_code(code: str, redirect_uri: str) -> bool:
    """Complete the consent walk: code -> tokens -> tenant id, all durably
    written before answering, so a crash mid-walk never strands a half-connect."""
    tok = await _token_request({"grant_type": "authorization_code",
                                "code": code, "redirect_uri": redirect_uri})
    if not tok or not tok.get("refresh_token"):
        return False
    access = str(tok.get("access_token") or "")
    # Which organisation consented: /connections, with the fresh access token.
    tenant_id, tname = "", ""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{API_BASE}/connections", timeout=30.0,
                                 headers={"Authorization": "Bearer " + access})
        rows = r.json() if r.status_code == 200 else []
        if rows:
            tenant_id = str(rows[0].get("tenantId") or "")
            tname = str(rows[0].get("tenantName") or "")
    except Exception:
        logger.exception("xero: connections lookup failed")
    if not tenant_id:
        return False
    _write_token({"refresh_token": str(tok["refresh_token"]),
                  "tenant_id": tenant_id, "tenant_name": tname,
                  "connected_at": time.time(), "last_refresh": time.time()})
    _state.update({"access": access,
                   "access_exp": time.monotonic() + float(tok.get("expires_in") or 1800) - 60,
                   "tenant": tenant_id, "tenant_name": tname})
    return True


async def _access_token() -> str:
    """A live access token, refreshing if needed. Serialized: Xero refresh
    tokens are single-use, and two concurrent refreshes would spend the same
    one twice - the second gets refused and the stored token is already dead,
    which disconnects the whole integration until a human re-consents."""
    if _state["access"] and time.monotonic() < _state["access_exp"]:
        return _state["access"]
    async with _refresh_lock:
        if _state["access"] and time.monotonic() < _state["access_exp"]:
            return _state["access"]              # someone else already refreshed
        d = _load_token()
        rt = d.get("refresh_token")
        if not rt:
            raise RuntimeError("Xero is not connected.")
        tok = await _token_request({"grant_type": "refresh_token", "refresh_token": rt})
        if not tok or not tok.get("access_token"):
            raise RuntimeError("Xero refused the refresh token. Reconnect Xero "
                               "from Settings, Connections.")
        # The ROTATED refresh token is the crown jewels: write it before
        # anything else can fail, or the old (now spent) one is all we have.
        if tok.get("refresh_token"):
            d["refresh_token"] = str(tok["refresh_token"])
            d["last_refresh"] = time.time()
            _write_token(d)
        _state["access"] = str(tok["access_token"])
        _state["access_exp"] = time.monotonic() + float(tok.get("expires_in") or 1800) - 60
        _state["tenant"] = str(d.get("tenant_id") or "")
        _state["tenant_name"] = str(d.get("tenant_name") or "")
        return _state["access"]


async def keepalive() -> None:
    """Refresh tokens die after 60 unused days; the nightly sweep calls this so
    a quiet month cannot silently disconnect the accounts."""
    if not connected():
        return
    try:
        await _access_token()
    except Exception:
        logger.exception("xero keepalive failed")


async def _pace() -> None:
    now = time.monotonic()
    while _recent_calls and now - _recent_calls[0] > 60:
        _recent_calls.pop(0)
    if len(_recent_calls) >= _MINUTE_BUDGET:
        wait = 60 - (now - _recent_calls[0]) + 0.5
        await asyncio.sleep(min(max(wait, 0.5), 15))
    _recent_calls.append(time.monotonic())


async def _get(path: str, params: Optional[dict] = None,
               if_modified_since: Optional[str] = None) -> dict:
    """One GET against the accounting API. Retries on 429 with a CAPPED wait
    and once on a transport blip; reads are safe to repeat."""
    token = await _access_token()
    headers = {"Authorization": "Bearer " + token,
               "xero-tenant-id": _state["tenant"],
               "Accept": "application/json"}
    if if_modified_since:
        headers["If-Modified-Since"] = if_modified_since
    url = f"{API_BASE}/api.xro/2.0/{path}"
    for attempt in range(4):
        await _pace()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, params=params, headers=headers, timeout=40.0)
        except (httpx.TimeoutException, httpx.TransportError):
            if attempt >= 3:
                raise
            await asyncio.sleep(min(2 ** attempt, 8))
            continue
        if resp.status_code == 401 and attempt == 0:
            _state["access"] = ""                # expired mid-flight: refresh once
            headers["Authorization"] = "Bearer " + await _access_token()
            continue
        if resp.status_code == 304:
            return {"_not_modified": True}
        if resp.status_code == 429 and attempt < 3:
            try:
                wait = min(float(resp.headers.get("Retry-After", "5")), 20.0)
            except ValueError:
                wait = 5.0
            logger.warning("xero 429 on %s; backing off %.1fs", path, wait)
            await asyncio.sleep(max(wait, 1.0))
            continue
        if resp.status_code >= 500 and attempt < 3:
            await asyncio.sleep(min(2 ** attempt, 8))
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()
    return {}


async def _paged(path: str, key: str, params: Optional[dict] = None,
                 if_modified_since: Optional[str] = None,
                 max_pages: int = 50) -> list:
    """Walk ?page=N until a short page. Reports the truncation instead of
    hiding it: a capped crawl must never read as a complete one (the sweep
    rule this codebase already learned the hard way)."""
    out: list = []
    params = dict(params or {})
    for page in range(1, max_pages + 1):
        params["page"] = page
        d = await _get(path, params=params, if_modified_since=if_modified_since)
        if d.get("_not_modified"):
            break
        rows = d.get(key) or []
        out.extend(rows)
        if len(rows) < 100:
            return out
    logger.warning("xero: %s stopped at the %d-page cap; results are PARTIAL", path, max_pages)
    out.append({"_truncated": True})
    return out


# ---------------------------------------------------------------------------
# Fetchers. Each returns Xero's own field names untouched: the reconciliation
# engine records evidence verbatim, so renaming here would put a translation
# between the audit trail and the system of record.
# ---------------------------------------------------------------------------

async def list_invoices(since: Optional[str] = None, modified_since: Optional[str] = None) -> list:
    """Sales invoices AND bills: Type ACCREC / ACCPAY. `since` filters by
    document date; `modified_since` is the incremental-sync watermark."""
    params: dict = {"order": "UpdatedDateUTC ASC"}
    if since:
        try:
            y, m, d = (int(x) for x in since.split("-"))
            # Built from parsed ints: "DateTime(2026,8,27)" - never a literal
            # with leading zeros, whose acceptance the docs do not promise.
            params["where"] = f"Date >= DateTime({y},{m},{d})"
        except ValueError:
            pass                          # a bad date filters nothing, never crashes
    return await _paged("Invoices", "Invoices", params, modified_since)


async def list_credit_notes(modified_since: Optional[str] = None) -> list:
    return await _paged("CreditNotes", "CreditNotes",
                        {"order": "UpdatedDateUTC ASC"}, modified_since)


async def list_payments(modified_since: Optional[str] = None) -> list:
    return await _paged("Payments", "Payments",
                        {"order": "UpdatedDateUTC ASC"}, modified_since)


async def list_bank_transactions(modified_since: Optional[str] = None) -> list:
    return await _paged("BankTransactions", "BankTransactions",
                        {"order": "UpdatedDateUTC ASC"}, modified_since)


async def list_contacts(modified_since: Optional[str] = None) -> list:
    return await _paged("Contacts", "Contacts",
                        {"order": "UpdatedDateUTC ASC"}, modified_since)


async def list_accounts() -> list:
    d = await _get("Accounts")
    return d.get("Accounts") or []


async def list_tax_rates() -> list:
    d = await _get("TaxRates")
    return d.get("TaxRates") or []


async def list_journals(offset: int = 0) -> list:
    """The journal feed pages by offset (JournalNumber), not by page number."""
    d = await _get("Journals", params={"offset": offset} if offset else None)
    return d.get("Journals") or []


async def organisation() -> dict:
    d = await _get("Organisation")
    rows = d.get("Organisations") or []
    return rows[0] if rows else {}


def status() -> dict:
    d = _load_token()
    return {"configured": client_configured(), "connected": connected(),
            "tenant": str(d.get("tenant_name") or ""),
            "last_refresh": d.get("last_refresh") or 0}
