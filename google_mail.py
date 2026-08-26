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
import html as _htm
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
# The accounts mailbox is a DIFFERENT Google account from the sales inbox, so
# it gets its own refresh token and its own access cache. Same OAuth client,
# same scope; nothing else is shared, because the whole point of the split is
# that reconciliation reads the finance mail and the Inbox tab does not.
FINANCE_TOKEN_PATH  = os.environ.get("GMAIL_FINANCE_TOKEN_PATH", "/data/gmail_finance_oauth.json")
API_BASE            = os.environ.get("GMAIL_API_BASE", "https://gmail.googleapis.com").rstrip("/")
TOKEN_ENDPOINT      = os.environ.get("GMAIL_TOKEN_URL", "https://oauth2.googleapis.com/token")
AUTH_ENDPOINT       = "https://accounts.google.com/o/oauth2/v2/auth"

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

_access: dict = {"token": "", "exp": 0.0}   # cached access token (sales)


class Account:
    """One connected mailbox: its own token file and its own access cache.

    The path is read through a callable rather than captured, so a test (or a
    future settings screen) that reassigns the module's TOKEN_PATH is still
    talking about the same account rather than a stale copy of its filename."""

    __slots__ = ("_path_fn", "label", "access")

    def __init__(self, path_fn, label: str, access: dict = None):
        self._path_fn = path_fn
        self.label = label
        self.access = access if access is not None else {"token": "", "exp": 0.0}

    @property
    def token_path(self) -> str:
        return self._path_fn()

    def usable(self) -> bool:
        """False when this account's token file would collide with another's.

        Two accounts sharing one token file is not a small misconfiguration:
        it silently points reconciliation at the sales inbox while the screen
        says it is reading the accounts mailbox, which is the exact failure
        this whole split exists to prevent. Refuse rather than guess."""
        if self is SALES:
            return True
        if os.path.abspath(self.token_path) == os.path.abspath(SALES.token_path):
            logger.error("gmail: the %s mailbox is configured with the same token file as "
                         "the sales inbox (%s). Set GMAIL_FINANCE_TOKEN_PATH to its own "
                         "path; refusing to use it until then.", self.label, self.token_path)
            return False
        return True


# SALES keeps the original module-level access dict, so anything that reached
# in and cleared `_access` directly still clears the right cache.
SALES = Account(lambda: TOKEN_PATH, "sales", _access)
FINANCE = Account(lambda: FINANCE_TOKEN_PATH, "finance")


class GmailError(Exception):
    """Carries Google's own error message so the UI can show the real cause."""


def client_configured() -> bool:
    return bool(OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET)


def _load_token_file(acct: Account = SALES) -> dict:
    try:
        with open(acct.token_path, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def connected(acct: Account = SALES) -> bool:
    return bool(acct.usable() and _load_token_file(acct).get("refresh_token"))


def address(acct: Account = SALES) -> str:
    """The connected mailbox address, captured at connect time."""
    return str(_load_token_file(acct).get("address") or "")


def save_connection(refresh_token: str, addr: str, acct: Account = SALES) -> None:
    if not acct.usable():
        # Writing here would land ON TOP of the sales inbox's token and take
        # that connection down with it. Refuse loudly.
        raise GmailError("The accounts mailbox shares a token file with the sales inbox. "
                         "Set GMAIL_FINANCE_TOKEN_PATH to its own path before connecting.")
    os.makedirs(os.path.dirname(acct.token_path) or ".", exist_ok=True)
    tmp = acct.token_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"refresh_token": refresh_token, "address": addr,
                   "connected_at": datetime.now(timezone.utc).isoformat()}, fh)
    os.replace(tmp, acct.token_path)
    acct.access["token"], acct.access["exp"] = "", 0.0


def disconnect(acct: Account = SALES) -> None:
    if not acct.usable():
        # With colliding paths this would delete the SALES token and take the
        # Inbox tab down with it. Clearing the cache is safe; the file is not.
        acct.access["token"], acct.access["exp"] = "", 0.0
        return
    try:
        os.remove(acct.token_path)
    except OSError:
        pass
    acct.access["token"], acct.access["exp"] = "", 0.0


def project_number() -> str:
    """The Cloud project an OAuth client belongs to is the numeric prefix of
    its client id (1234567890-xxxx.apps.googleusercontent.com -> 1234567890).
    That number drops straight into a console URL, which turns "find the
    project your app already uses" from an archaeology exercise into a link."""
    head = OAUTH_CLIENT_ID.split("-", 1)[0].strip()
    return head if head.isdigit() else ""


def status(acct: Account = SALES) -> dict:
    return {"client": client_configured(), "connected": connected(acct),
            "address": address(acct) or None}


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------

def consent_url(redirect_uri: str, state: str, login_hint: str = "") -> str:
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
    if login_hint:
        # Naming the mailbox we want. select_account shows the chooser, but a
        # browser with one live Google session lands on THAT account anyway,
        # and the person ends up connecting the mailbox they were already in
        # rather than the one they meant. A hint preselects the right one.
        params["login_hint"] = login_hint
    return f"{AUTH_ENDPOINT}?{urlencode(params)}"


async def exchange_code(code: str, redirect_uri: str, acct: Account = SALES) -> bool:
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
    save_connection(rt, addr, acct)
    return True


async def _token(acct: Account = SALES) -> str:
    if not acct.usable():
        raise GmailError("The accounts mailbox shares a token file with the sales inbox. "
                         "Set GMAIL_FINANCE_TOKEN_PATH to its own path.")
    rt = _load_token_file(acct).get("refresh_token", "")
    if not rt:
        raise GmailError("Gmail is not connected."
                         if acct is SALES else
                         "The accounts mailbox is not connected.")
    if acct.access["token"] and time.monotonic() < acct.access["exp"]:
        return acct.access["token"]
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
    acct.access["token"] = data["access_token"]
    acct.access["exp"] = time.monotonic() + int(data.get("expires_in", 3600)) - 60
    return acct.access["token"]


async def _call(method: str, path: str, *, params: dict = None, body: dict = None,
                acct: Account = SALES) -> dict:
    token = await _token(acct)
    url = f"{API_BASE}/gmail/v1/users/me/{path}"
    async with httpx.AsyncClient(timeout=25.0) as c:
        r = await c.request(method, url, params=params, json=body,
                            headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 401:
            # Google can kill an access token before its stated expiry (the
            # mailbox password changed, a security event). Standard recovery:
            # drop the cache, mint a fresh token, retry exactly once.
            acct.access["token"], acct.access["exp"] = "", 0.0
            token = await _token(acct)
            r = await c.request(method, url, params=params, json=body,
                                headers={"Authorization": f"Bearer {token}"})
    if r.status_code >= 400:
        try:
            detail = r.json().get("error", {}).get("message", "") or r.text[:300]
        except Exception:
            detail = r.text[:300]
        logger.warning(f"Gmail API {r.status_code} on {path} ({acct.label}): {detail}")
        raise GmailError(str(detail).strip()[:400] or f"HTTP {r.status_code}")
    return r.json() if r.content else {}


# ---------------------------------------------------------------------------
# Threads
# ---------------------------------------------------------------------------

async def list_threads(query: str = "in:inbox", max_results: int = 100) -> dict:
    """{"threads": [...], "complete": bool}.

    Paginated, and it SAYS whether it saw everything. That flag is
    load-bearing: the caller treats "not in this listing" as "archived in
    Gmail", and on a truncated page that would mean silently closing live
    customer email that merely fell off the end."""
    out, token, pages, complete = [], None, 0, True
    want = max(1, int(max_results))
    # Enough pages to actually reach max_results (plus one for ragged pages):
    # the old fixed six-page walk silently clipped a two-year window at 3000.
    max_pages = max(6, -(-want // 500) + 1)
    while True:
        params = {"q": query, "maxResults": min(want - len(out), 500)}
        if token:
            params["pageToken"] = token
        data = await _call("GET", "threads", params=params)
        for t in (data.get("threads") or []):
            if t.get("id"):
                out.append({"id": str(t["id"]), "snippet": _htm.unescape(str(t.get("snippet") or "")),
                            "historyId": str(t.get("historyId") or "")})
        token = data.get("nextPageToken")
        pages += 1
        if not token:
            break
        if pages >= max_pages or len(out) >= want:
            complete = False       # a mailbox bigger than we will walk
            break
    return {"threads": out, "complete": complete}


async def list_thread_ids(query: str, max_results: int = 500, pages: int = 8, acct: Account = SALES,
                          out_complete=None) -> set:
    """Just the ids matching a query.

    Used to ask Gmail point blank which threads are unread, rather than
    inferring it from a label on a thread we may not have refetched. Reading
    or unreading an email in Gmail changes almost nothing else about the
    thread, so inference is exactly where staleness hides."""
    out, token, done = set(), None, 0
    while done < max(1, pages):
        params = {"q": query, "maxResults": max(1, min(int(max_results), 500))}
        if token:
            params["pageToken"] = token
        data = await _call("GET", "threads", params=params, acct=acct)
        for t in (data.get("threads") or []):
            if t.get("id"):
                out.add(str(t["id"]))
        token = data.get("nextPageToken")
        done += 1
        if not token:
            break
    # Say whether the walk saw everything. The unread sweep uses this set to
    # decide what is READ, so a silently truncated answer marks live unread
    # email as read on the board - the caller must be able to tell.
    if out_complete is not None:
        out_complete.append(not token)
    return out


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


async def get_thread(thread_id: str, acct: Account = SALES) -> dict:
    """Normalized thread: subject + per-message sender/time/snippet. Gmail
    HTML-escapes snippets (&#39; for an apostrophe), so they are unescaped
    HERE, once, at the boundary - the app renders text, never HTML. Metadata
    format only; bodies stay in Gmail where replies happen."""
    # format=full rather than metadata: metadata omits the part tree, so the
    # app could not tell an email with artwork attached from one without.
    # Bodies are ignored here; only names and sizes are read, and attachment
    # bytes stay behind their attachmentId either way.
    data = await _call("GET", f"threads/{thread_id}", params={"format": "full"}, acct=acct)
    msgs = []
    subject = ""
    for m in (data.get("messages") or []):
        # An UNSENT draft is a message on the thread with the DRAFT label.
        # Counting it would make the board report that the shop had replied,
        # move the conversation on, and later feed our own unsent words back
        # to the model as though the customer had already received them.
        if "DRAFT" in (m.get("labelIds") or []):
            continue
        name, email = parseaddr(_header(m, "From"))
        subject = subject or _header(m, "Subject")
        files: list = []
        _walk_files(m.get("payload") or {}, files)
        for f in files:
            f["msg"] = str(m.get("id") or "")
        msgs.append({"id": str(m.get("id") or ""),
                     "from_name": name or email, "from_email": email.lower(),
                     "files": [f for f in files if f["id"]][:20],
                     "at": _msg_time(m),
                     # Gmail's own labels ride along so the list can bold what
                     # nobody has opened yet, the way an inbox is read.
                     "labels": [str(x) for x in (m.get("labelIds") or [])],
                     "snippet": _htm.unescape(str(m.get("snippet") or ""))})
    return {"id": str(data.get("id") or thread_id),
            "historyId": str(data.get("historyId") or ""),
            "subject": subject, "messages": msgs}


def _part_charset(part: dict) -> str:
    """The charset Gmail declares for this part. Assuming UTF-8 turns a
    Windows-1252 pound sign into a replacement character, and this shop's
    inbound mail is quotes and prices: a mangled currency symbol beside a
    number is worse than no body at all."""
    for h in (part.get("headers") or []):
        if str(h.get("name", "")).lower() == "content-type":
            v = str(h.get("value") or "")
            if "charset=" in v.lower():
                cs = v.lower().split("charset=", 1)[1].split(";")[0]
                return cs.strip().strip('"').strip("'")
    return ""


def _b64url(data: str, charset: str = "") -> str:
    """Gmail hands body bytes back base64URL encoded and unpadded. Plain
    b64decode mangles any part whose alphabet happens to contain - or _,
    which is data-dependent: it passes every test and then fails on one
    real customer's email."""
    import base64
    s = str(data or "")
    try:
        raw = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    except Exception:
        return ""
    for enc in ([charset] if charset else []) + ["utf-8", "cp1252", "latin-1"]:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


def _walk_files(part: dict, out: list) -> None:
    """Attachment names and sizes from the part tree. The BYTES are never
    touched here: an attachmentId is a pointer, and fetching it is a separate,
    deliberate act (a 20MB artwork file has no business in a board refresh)."""
    name = str(part.get("filename") or "").strip()
    body = part.get("body") or {}
    if name:
        # A corporate signature ships its logo as an inline part WITH a
        # filename, so counting those puts a paperclip on half the inbox and
        # offers image001.png as if it were artwork. Inline parts carry a
        # Content-ID and say "inline" in their disposition.
        hdrs = {str(h.get("name", "")).lower(): str(h.get("value") or "")
                for h in (part.get("headers") or [])}
        if "content-id" in hdrs or "inline" in hdrs.get("content-disposition", "").lower():
            return
        out.append({"name": name[:200],
                    "size": int(body.get("size") or 0),
                    "mime": str(part.get("mimeType") or "").split(";")[0].strip(),
                    "id": str(body.get("attachmentId") or ""),
                    "msg": ""})
        return                       # do not descend into an attached .eml
    for k in (part.get("parts") or []):
        _walk_files(k, out)


def _walk_body(part: dict, out: dict) -> None:
    """Depth-first for the readable text. A simple message keeps its whole
    body on the root part with no `parts` at all, so a walker that only ever
    looks at `parts` reads nothing for exactly the plainest emails."""
    mime = str(part.get("mimeType") or "").split(";")[0].strip().lower()
    # The filename check comes FIRST: an attached .eml is a container with a
    # filename, and descending into it reads the forwarded mail as if the
    # sender had written it themselves.
    if part.get("filename"):
        return
    kids = part.get("parts") or []
    if kids:
        for k in kids:
            _walk_body(k, out)
        return
    body = part.get("body") or {}
    if body.get("attachmentId") or not body.get("data"):
        return                       # bytes live elsewhere: never pull them in
    text = _b64url(body["data"], _part_charset(part))
    if mime == "text/plain" and not (out.get("plain") or "").strip():
        out["plain"] = text          # a whitespace-only stub must not win
    elif mime == "text/html" and not (out.get("html") or "").strip():
        out["html"] = text


def _strip_html(html: str) -> str:
    import re as _re
    import html as _html
    txt = html or ""
    # Unterminated script/style must not survive as readable text, so drop
    # from the opening tag to the end when there is no closing tag.
    txt = _re.sub(r"(?is)<(script|style)[^>]*>.*?(</\1>|$)", " ", txt)
    txt = _re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", txt)
    txt = _re.sub(r"<[^>]+>", " ", txt)
    # unescape AFTER tags are gone, and handle every entity rather than six:
    # &pound; and &#163; are the ones that matter on a quote.
    txt = _html.unescape(txt)
    return _re.sub(r"[ \t]{2,}", " ", _re.sub(r"\n{3,}", "\n\n", txt)).strip()


async def read_thread(thread_id: str, per_msg_chars: int = 4000) -> dict:
    """The conversation as READABLE TEXT, for drafting a reply against.

    format=full parses the body into `payload` and leaves attachment bytes
    behind an attachmentId; format=raw would inline a 20MB attachment into
    this request, which is why it is not used."""
    data = await _call("GET", f"threads/{thread_id}", params={"format": "full"})
    msgs = []
    for m in (data.get("messages") or []):
        if "DRAFT" in (m.get("labelIds") or []):
            continue      # our own unsent words are not part of the conversation
        payload = m.get("payload") or {}
        found: dict = {}
        _walk_body(payload, found)
        text = found.get("plain") or _strip_html(found.get("html") or "")
        name, email = parseaddr(_header(m, "From"))
        msgs.append({
            "id": str(m.get("id") or ""),
            "from_name": name or email, "from_email": email.lower(),
            "to": _header(m, "To"), "cc": _header(m, "Cc"),
            "reply_to": _header(m, "Reply-To"),
            "subject": _header(m, "Subject"),
            "message_id": _header(m, "Message-ID") or _header(m, "Message-Id"),
            "references": _header(m, "References"),
            "at": _msg_time(m),
            "text": (text or _htm.unescape(str(m.get("snippet") or "")))[:per_msg_chars],
        })
    return {"id": str(data.get("id") or thread_id), "messages": msgs}


async def draft_body(draft_id: str) -> str:
    """The current text of a draft, so a replace can tell whether the person
    rewrote it in Gmail first. Deleting somebody's edited reply because they
    pressed Save twice is not a trade worth making."""
    data = await _call("GET", f"drafts/{draft_id}", params={"format": "full"})
    payload = ((data.get("message") or {}).get("payload")) or {}
    found: dict = {}
    _walk_body(payload, found)
    return (found.get("plain") or _strip_html(found.get("html") or "") or "").strip()


async def delete_draft(draft_id: str) -> None:
    """Best effort: a leftover draft is clutter, not a crisis."""
    try:
        await _call("DELETE", f"drafts/{draft_id}")
    except Exception as e:
        logger.warning("Gmail: could not remove the previous draft %s: %s", draft_id, e)


async def create_draft(thread_id: str, to_addr: str, subject: str, body_text: str,
                       in_reply_to: str = "", references: str = "",
                       cc: str = "", replaces: str = "") -> dict:
    """Put a reply in the mailbox as a DRAFT. A draft is inert: nothing is
    sent, nobody is notified, and the merchant reviews and sends it in Gmail.
    This app never sends mail itself.

    Gmail only threads the draft when the Subject and the reply headers line
    up with the parent, so every header here is derived from the parent in
    code. The model writes the body and nothing else."""
    import base64
    from email.message import EmailMessage
    me = address()
    # Every header value below is derived from Gmail data, i.e. ultimately
    # from whoever sent the email. A newline inside one would start a new
    # header line, so strip line breaks before they get near a header.
    clean = lambda v: " ".join(str(v or "").split())[:998]
    to_addr, cc, subject = clean(to_addr), clean(cc), clean(subject)
    in_reply_to, references = clean(in_reply_to), clean(references)
    msg = EmailMessage()
    if me:
        msg["From"] = me
    msg["To"] = to_addr
    if cc:
        msg["Cc"] = cc
    s = (subject or "").strip()
    msg["Subject"] = s if s[:3].lower() == "re:" else ("Re: " + s if s else "Re:")
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        refs = (references or "").split()
        if in_reply_to not in refs:
            refs.append(in_reply_to)
        msg["References"] = " ".join(refs)
    msg.set_content(body_text or "")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    out = await _call("POST", "drafts", body={"message": {"raw": raw, "threadId": thread_id}})
    landed = str(((out.get("message") or {}).get("threadId")) or "")
    if landed and landed != str(thread_id):
        # Documented threading rules were not met, so Gmail started a NEW
        # conversation. Say so rather than let a stray draft go unnoticed.
        logger.warning("Gmail put the draft on thread %s, not %s", landed, thread_id)
        raise GmailError("Gmail saved the draft but could not attach it to this "
                         "conversation. Check your drafts folder.")
    if replaces:
        # Saving twice must leave ONE draft on the conversation, not a pile of
        # near-identical ones that all look ready to send.
        await delete_draft(replaces)
    return {"id": str(out.get("id") or ""), "thread_id": landed or str(thread_id)}


async def attachment_bytes(message_id: str, attachment_id: str, cap: int = 25 * 1024 * 1024,
                           acct: Account = SALES) -> bytes:
    """One attachment's bytes, fetched deliberately and capped."""
    import base64
    data = await _call("GET", f"messages/{message_id}/attachments/{attachment_id}", acct=acct)
    size = int(data.get("size") or 0)
    if size > cap:
        raise GmailError("That file is " + str(round(size / 1048576, 1))
                         + "MB, which is too big to bring across. Save it from Gmail.")
    raw = str(data.get("data") or "")
    out = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    if len(out) > cap:
        raise GmailError("That file is too big to bring across.")
    return out


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
