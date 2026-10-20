"""The Finder drive: the Files store as a native WebDAV drive, the way macOS
mounts it. Its path walking, its sign-in and failure caches, and the XML it
answers with. Moved out of copilot.py (stage 4 of the 14 October audit); its
route is with the Files routes. Read as `webdav.NAME`.
"""
import logging
import re
import html
import time
import hmac
import base64
import hashlib
from datetime import datetime, timezone
from typing import Optional

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


DAV_FAIL_PER_MIN = 20      # wrong drive passwords per client per minute before 429


def _dav_drop_cache(uid: str) -> None:
    """A password change or revocation must also forget the drive's cached
    credential, or the OLD password could mount for up to ten more minutes."""
    for k, v in list(_dav_auth_cache.items()):
        if isinstance(v, tuple) and v and v[0] == uid:
            _dav_auth_cache.pop(k, None)
_dav_auth_cache: dict = {}


_dav_fail_cache: dict = {}    # ("davwhy", uid, reason) -> when that refusal was last put in the ledger


def _dav_check_auth(header: str):
    """(uid, error_code). The cache stores only that a PASSWORD matched (scrypt
    is expensive and Finder asks constantly); the live account state -- active,
    deleted, locked, files-tab, must-change -- is re-checked on EVERY request,
    so revoking access or resetting a password takes effect at once, not after
    the cache expires.

    Wrong drive passwords never lock anything by username, the drive's or the
    web login's: a drive password is random and 24 characters long, so a lock
    by name guarded nothing and let anyone who knew a username keep that
    person's Finder shut (audit R-C4). Guessing is slowed per client address
    by the route instead (DAV_FAIL_PER_MIN)."""
    if not header.startswith("Basic "):
        return None, 401
    try:
        raw = base64.b64decode(header[6:]).decode("utf-8")
        username, _, pw = raw.partition(":")
    except Exception:
        return None, 401
    username = username.strip().lower()
    now = time.time()
    d = team._load_users()
    uid = next((k for k, u in d["users"].items()
                if not u.get("deleted") and u.get("username") == username), None)
    u = d["users"].get(uid) if uid else None
    def refused(reason):
        # One admin-readable line per reason per few minutes: Finder retries in
        # storms, and the ledger should explain the refusal, not drown in it.
        mark = ("davwhy", uid, reason)
        last = _dav_fail_cache.get(mark)
        if not last or last < now - 300:
            if len(_dav_fail_cache) > 500:
                _dav_fail_cache.clear()
            _dav_fail_cache[mark] = now
            activity._track(uid, "auth", "drive refused", reason)
    def level(code):
        """Refuse having spent what a real check costs: one SHA-256, the same
        whether or not the account exists, so the timing says nothing."""
        hmac.compare_digest(hashlib.sha256(pw.encode("utf-8")).hexdigest(), "0" * 64)
        return None, code
    # Every live gate, checked every time -- the cache below only vouches for
    # the password, nothing else.
    if not u or not u.get("active", True):
        if u is not None:
            refused("their access is switched off")
        return level(401)
    # The web sign-in's lock after wrong passwords is not checked here: it
    # guards the account password, which the drive no longer takes, and
    # checking it let anyone who knew a username shut that person's Finder
    # with five wrong web passwords (audit R-C4).
    if team._user_tabs(uid) is not None and "files" not in (team._user_tabs(uid) or []):
        refused("the Files tab is switched off for their account")
        return level(403)
    if u.get("must_change"):
        # A starter password is for the first web sign-in only; it never mounts
        # the drive. Once they have chosen their own, the drive opens.
        refused("they have not chosen their own password in the app yet")
        return level(401)
    # The drive takes its own password, never the account's (audit R-007,
    # chains R-C4 and R-C6). /dav sits outside the Shopify login, so the
    # account password alone opened Files from anywhere, skipped sign-in
    # codes, and paid scrypt on the event loop for every guess. A drive
    # password is made on the Files page after a full sign-in, is random and
    # long, so a SHA-256 of it is enough to check, in microseconds, every
    # request, with nothing cached.
    if not u.get("dav_pw"):
        refused("they have not made a drive password on the Files page")
        return level(401)
    if not hmac.compare_digest(hashlib.sha256(pw.encode("utf-8")).hexdigest(), str(u.get("dav_pw"))):
        activity._track_login_refusal(uid, "wrong drive password at the file drive")
        return None, 401
    return uid, None


def _dav_split(path: str) -> list:
    return [p for p in path.split("/") if p not in ("", ".")]


def _dav_walk_folder(d: dict, segs: list):
    """Resolve folder path segments case-insensitively. Returns folder id
    ('' = root) or None."""
    parent = ""
    for seg in segs:
        nxt = next((fid for fid, f in d["folders"].items()
                    if str(f.get("parent_id") or "") == parent
                    and f.get("name", "").lower() == seg.lower()), None)
        if nxt is None:
            return None
        parent = nxt
    return parent


def _dav_resolve(d: dict, path: str):
    """('folder', id) | ('file', id) | (None, None). Hidden files resolve here
    (Finder wants its metadata files back) but never appear in the app."""
    segs = _dav_split(path)
    fid = _dav_walk_folder(d, segs)
    if fid is not None:
        return "folder", fid
    if not segs:
        return None, None
    parent = _dav_walk_folder(d, segs[:-1])
    if parent is None:
        return None, None
    name = segs[-1].lower()
    for k, f in d["files"].items():
        if f.get("status") == "active" and str(f.get("folder_id") or "") == parent \
                and f.get("name", "").lower() == name:
            return "file", k
    return None, None


def _dav_href(*segs) -> str:
    from urllib.parse import quote
    return "/dav/" + "/".join(quote(s) for s in segs if s)


def _dav_href_dir(*segs) -> str:
    """Collection hrefs end in exactly one slash: macOS's client refuses a
    whole mount over a root href of /dav// instead of /dav/."""
    h = _dav_href(*segs)
    return h if h.endswith("/") else h + "/"


def _dav_path_of_folder(d: dict, fid: str) -> list:
    out, hops = [], 0
    while fid and fid in d["folders"] and hops < 50:
        out.insert(0, d["folders"][fid]["name"])
        fid = str(d["folders"][fid].get("parent_id") or "")
        hops += 1
    return out


# macOS and Windows sidecars, and NOTHING else. The alternation used to be
# `^(\.|_)`, which caught every ordinary filename beginning with an underscore
# - and a junk file here is invisible in the Files tab, absent from the audit
# ledger, exempt from the 30-day trash, and destroyed 30 days after it was
# saved. `_JOB4471-final.eps` saved from Finder worked for a month and then
# disappeared, with nothing anywhere to say why.
_DAV_JUNK = re.compile(r"^\._|^\.DS_Store$|^\.(Trashes|Spotlight-V100|fseventsd|TemporaryItems|apdisk)"
                       r"|^desktop\.ini$|^Thumbs\.db$", re.I)


def _dav_rfc1123(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%a, %d %b %Y %H:%M:%S GMT")
    except Exception:
        return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


def _dav_entry_xml(href: str, name: str, is_dir: bool, size: int = 0, mtime: str = "",
                   etag: str = "", quota: Optional[tuple] = None) -> str:
    rt = "<D:collection/>" if is_dir else ""
    extra = "" if is_dir else (
        f"<D:getcontentlength>{size}</D:getcontentlength>"
        "<D:getcontenttype>application/octet-stream</D:getcontenttype>")
    if etag:
        extra += f'<D:getetag>"{etag}"</D:getetag>'
    if quota:
        used, avail = quota
        extra += (f"<D:quota-used-bytes>{used}</D:quota-used-bytes>"
                  f"<D:quota-available-bytes>{avail}</D:quota-available-bytes>")
    return ("<D:response><D:href>" + html.escape(href) + "</D:href>"
            "<D:propstat><D:prop>"
            "<D:displayname>" + html.escape(name) + "</D:displayname>"
            f"<D:resourcetype>{rt}</D:resourcetype>"
            f"<D:getlastmodified>{_dav_rfc1123(mtime)}</D:getlastmodified>"
            + extra +
            "</D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>")


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
from gizmo import activity  # noqa: E402
from gizmo import team  # noqa: E402
import copilot as core  # noqa: E402
