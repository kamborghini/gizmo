#!/usr/bin/env python3
"""
Gmail connector for the shared-inbox board.

A SEPARATE Google connection from google_data (GSC/GA4): the analytics account
is the merchant's own, the mailbox is the shared address (sales@...), so each
keeps its own refresh token. Same OAuth client, different scope, different
token file.

Scope is gmail.modify: read threads, create labels, apply/remove labels
(verified against the users.labels.create and threads.modify references).
The app never sends mail; replies happen in Gmail itself.

Env:
  GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET   shared with google_data
  GMAIL_TOKEN_PATH     refresh-token file (default /data/gmail_oauth.json)
  GMAIL_API_BASE       test override for the API host (like R2_ENDPOINT)
  GMAIL_TOKEN_URL      test override for the token endpoint

Unconfigured -> connected() is False and the Inbox tab shows a connect card.
"""
import os
import json
import time
import logging
from datetime import datetime, timezone
from email.utils import parseaddr, parsedate_to_datetime
from urllib.parse import urlencode

import httpx

logger = logging.getLogger("shopify_mcp.gmail")

OAUTH_CLIENT_ID     = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
TOKEN_PATH          = os.environ.get("GMAIL_TOKEN_PATH", "/data/gmail_oauth.json")
API_BASE            = os.environ.get("GMAIL_API_BASE", "https://gmail.googleapis.com").rstrip("/")
TOKEN_ENDPOINT      = os.environ.get("GMAIL_TOKEN_URL", "https://oauth2.googleapis.com/token")
AUTH_ENDPOINT       = "https://accounts.google.com/o/oauth2/v2/auth"

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

_access: dict = {"token": "", "exp": 0.0}   # cached access token


class GmailError(Exception):
    """Carries Google's own error message so the UI can show the real cause."""


def client_configured() -> bool:
    return bool(OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET)


def _load_token_file() -> dict:
    try:
        with open(TOKEN_PATH, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def connected() -> bool:
    return bool(_load_token_file().get("refresh_token"))


def address() -> str:
    """The connected mailbox address, captured at connect time."""
    return str(_load_token_file().get("address") or "")


def save_connection(refresh_token: str, addr: str) -> None:
    os.makedirs(os.path.dirname(TOKEN_PATH) or ".", exist_ok=True)
    tmp = TOKEN_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"refresh_token": refresh_token, "address": addr,
                   "connected_at": datetime.now(timezone.utc).isoformat()}, fh)
    os.replace(tmp, TOKEN_PATH)
    _access["token"], _access["exp"] = "", 0.0


def disconnect() -> None:
    try:
        os.remove(TOKEN_PATH)
    except OSError:
        pass
    _access["token"], _access["exp"] = "", 0.0


def project_number() -> str:
    """The Cloud project an OAuth client belongs to is the numeric prefix of
    its client id (1234567890-xxxx.apps.googleusercontent.com -> 1234567890).
    That number drops straight into a console URL, which turns "find the
    project your app already uses" from an archaeology exercise into a link."""
    head = OAUTH_CLIENT_ID.split("-", 1)[0].strip()
    return head if head.isdigit() else ""


def status() -> dict:
    return {"client": client_configured(), "connected": connected(),
            "address": address() or None}


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------

def consent_url(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        # consent = a refresh token every time. select_account = Google ALWAYS
        # asks which account: without it, whoever is already signed into that
        # browser gets connected silently, and the likeliest person clicking
        # this is signed in as themselves, not as the shared mailbox.
        "prompt": "consent select_account",
        "state": state,
    }
    return f"{AUTH_ENDPOINT}?{urlencode(params)}"


async def exchange_code(code: str, redirect_uri: str) -> bool:
    """Swap the auth code for tokens, look up whose mailbox this is, persist."""
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.post(TOKEN_ENDPOINT, data={
            "client_id": OAUTH_CLIENT_ID, "client_secret": OAUTH_CLIENT_SECRET,
            "code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri,
        })
        if r.status_code != 200:
            logger.warning(f"Gmail OAuth exchange failed: {r.status_code} {r.text[:200]}")
            return False
        data = r.json()
        rt = data.get("refresh_token")
        at = data.get("access_token", "")
        if not rt:
            logger.warning("Gmail OAuth exchange returned no refresh_token.")
            return False
        addr = ""
        try:
            p = await c.get(f"{API_BASE}/gmail/v1/users/me/profile",
                            headers={"Authorization": f"Bearer {at}"})
            if p.status_code == 200:
                addr = str(p.json().get("emailAddress") or "")
        except Exception:
            pass
    if not addr:
        # Without the mailbox's own address the sync cannot tell the shop's
        # replies from the customer's, which silently breaks the waiting and
        # done states. A connect that cannot learn the address FAILS rather
        # than persisting a half-connection; the person just runs it again.
        logger.warning("Gmail connect: token exchange succeeded but the profile "
                       "lookup failed; refusing the half-connection.")
        return False
    save_connection(rt, addr)
    return True


async def _token() -> str:
    rt = _load_token_file().get("refresh_token", "")
    if not rt:
        raise GmailError("Gmail is not connected.")
    if _access["token"] and time.monotonic() < _access["exp"]:
        return _access["token"]
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.post(TOKEN_ENDPOINT, data={
            "client_id": OAUTH_CLIENT_ID, "client_secret": OAUTH_CLIENT_SECRET,
            "refresh_token": rt, "grant_type": "refresh_token",
        })
    if r.status_code != 200:
        # invalid_grant means the refresh token itself is dead (revoked or
        # expired): reconnecting IS the fix. Anything else is Google having
        # a moment, and telling the merchant to redo the consent walk for a
        # transient 500 would be wrong advice.
        try:
            err = r.json().get("error", "")
            desc = r.json().get("error_description", "")
        except Exception:
            err, desc = "", ""
        if err == "invalid_grant":
            raise GmailError("Gmail token refresh failed. Reconnect the mailbox.")
        raise GmailError(f"Gmail token refresh failed ({err or r.status_code}"
                         + (f": {desc[:120]}" if desc else "") + "). It usually passes; "
                         "reconnect only if this persists.")
    data = r.json()
    if not data.get("access_token"):
        raise GmailError("Gmail token refresh returned no access token.")
    _access["token"] = data["access_token"]
    _access["exp"] = time.monotonic() + int(data.get("expires_in", 3600)) - 60
    return _access["token"]


async def _call(method: str, path: str, *, params: dict = None, body: dict = None) -> dict:
    token = await _token()
    url = f"{API_BASE}/gmail/v1/users/me/{path}"
    async with httpx.AsyncClient(timeout=25.0) as c:
        r = await c.request(method, url, params=params, json=body,
                            headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 401:
            # Google can kill an access token before its stated expiry (the
            # mailbox password changed, a security event). Standard recovery:
            # drop the cache, mint a fresh token, retry exactly once.
            _access["token"], _access["exp"] = "", 0.0
            token = await _token()
            r = await c.request(method, url, params=params, json=body,
                                headers={"Authorization": f"Bearer {token}"})
    if r.status_code >= 400:
        try:
            detail = r.json().get("error", {}).get("message", "") or r.text[:300]
        except Exception:
            detail = r.text[:300]
        logger.warning(f"Gmail API {r.status_code} on {path}: {detail}")
        raise GmailError(str(detail).strip()[:400] or f"HTTP {r.status_code}")
    return r.json() if r.content else {}


# ---------------------------------------------------------------------------
# Threads
# ---------------------------------------------------------------------------

async def list_threads(query: str = "in:inbox", max_results: int = 100) -> list:
    """[{id, snippet, historyId}] newest first. One page is plenty: the board
    tracks the working set, not the whole archive."""
    data = await _call("GET", "threads",
                       params={"q": query, "maxResults": max(1, min(int(max_results), 200))})
    return [{"id": str(t.get("id") or ""), "snippet": str(t.get("snippet") or ""),
             "historyId": str(t.get("historyId") or "")}
            for t in (data.get("threads") or []) if t.get("id")]


def _header(msg: dict, name: str) -> str:
    for h in ((msg.get("payload") or {}).get("headers") or []):
        if str(h.get("name", "")).lower() == name.lower():
            return str(h.get("value") or "")
    return ""


def _msg_time(msg: dict) -> str:
    """ISO timestamp for a message: internalDate (ms epoch) first, Date header
    as fallback. Empty string when neither parses."""
    raw = msg.get("internalDate")
    try:
        return datetime.fromtimestamp(int(raw) / 1000.0, tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        pass
    try:
        return parsedate_to_datetime(_header(msg, "Date")).astimezone(timezone.utc).isoformat()
    except Exception:
        return ""


async def get_thread(thread_id: str) -> dict:
    """Normalized thread: subject + per-message sender/time/snippet. Metadata
    format only; bodies stay in Gmail where replies happen."""
    data = await _call("GET", f"threads/{thread_id}",
                       params={"format": "metadata",
                               "metadataHeaders": ["From", "Subject", "Date"]})
    msgs = []
    subject = ""
    for m in (data.get("messages") or []):
        name, email = parseaddr(_header(m, "From"))
        subject = subject or _header(m, "Subject")
        msgs.append({"id": str(m.get("id") or ""),
                     "from_name": name or email, "from_email": email.lower(),
                     "at": _msg_time(m),
                     # Gmail's own labels ride along so the list can bold what
                     # nobody has opened yet, the way an inbox is read.
                     "labels": [str(x) for x in (m.get("labelIds") or [])],
                     "snippet": str(m.get("snippet") or "")})
    return {"id": str(data.get("id") or thread_id),
            "historyId": str(data.get("historyId") or ""),
            "subject": subject, "messages": msgs}


async def modify_thread(thread_id: str, add: list = None, remove: list = None) -> None:
    body = {}
    if add:
        body["addLabelIds"] = list(add)
    if remove:
        body["removeLabelIds"] = list(remove)
    if body:
        await _call("POST", f"threads/{thread_id}/modify", body=body)


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

async def list_labels() -> dict:
    """name -> id for every label in the mailbox."""
    data = await _call("GET", "labels")
    return {str(l.get("name") or ""): str(l.get("id") or "")
            for l in (data.get("labels") or []) if l.get("id")}


async def ensure_label(name: str, known: dict) -> str:
    """Return the label id for `name`, creating it in Gmail when missing.
    `known` is the caller's cached name->id map; a hit skips the API entirely."""
    if known.get(name):
        return known[name]
    live = await list_labels()
    if name in live:
        known[name] = live[name]
        return live[name]
    try:
        data = await _call("POST", "labels", body={
            "name": name, "labelListVisibility": "labelShow",
            "messageListVisibility": "show"})
    except GmailError:
        # Two state changes can want the same brand-new label at once; the
        # loser's create 409s on the duplicate name. Re-list and take the
        # winner's id instead of reporting a phantom failure.
        live = await list_labels()
        if name in live:
            known[name] = live[name]
            return live[name]
        raise
    lid = str(data.get("id") or "")
    if not lid:
        raise GmailError(f"Label create returned no id for {name!r}")
    known[name] = lid
    return lid
