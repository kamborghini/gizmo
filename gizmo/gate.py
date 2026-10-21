"""The gate: the one door every route opens with (_guard), its pre-checks,
the rate windows, the body cap, the AI slot, the tab map and the tab gate,
and the answer helpers and headers every reply carries.

Moved out of copilot.py (stage 4 of the 14 October audit). Read as
`gate.NAME` (`door` is a local name in the dispatch desk).
"""
import logging
import os
import json
import time
import perf
from starlette.responses import JSONResponse, Response
from starlette.requests import Request
from typing import Optional
from gizmo.config import _env_num
from gizmo import bodies
import secrets

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")



# Headers applied to every API/page response (defense in depth).
_API_HEADERS = {
    # Authenticated JSON, and the browser's own disk cache and back-forward
    # cache are shared with whoever uses the machine next. The page shell sets
    # its own (it must revalidate, not vanish), so it spreads these FIRST.
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    # The camera is the page's own (camera=(self)) for the camera test in
    # Settings, a throwaway ahead of the stock sheet's label scanning moving
    # in; nothing framed inside the page, and nothing else, gets it.
    "Permissions-Policy": "camera=(self), microphone=(), geolocation=(), payment=()",
}

# --- Abuse / cost controls --------------------------------------------------
RATE_WINDOW      = _env_num(int, os.environ.get("RATE_LIMIT_WINDOW", "60"), "60", "RATE_LIMIT_WINDOW")      # seconds
RATE_MAX_CLIENT  = _env_num(int, os.environ.get("RATE_LIMIT_PER_CLIENT", "120"), "120", "RATE_LIMIT_PER_CLIENT")  # requests/window/client
# 30/min was reachable by one busy operator: a single order costs up to four
# calls (history, quote, book, mark made) before any refresh or tab switch.
RATE_MAX_GLOBAL  = _env_num(int, os.environ.get("RATE_LIMIT_GLOBAL", "150"), "150", "RATE_LIMIT_GLOBAL")     # AI requests/window (cost ceiling)
MAX_BODY_BYTES   = _env_num(int, os.environ.get("MAX_BODY_BYTES", str(256 * 1024)), str(256 * 1024), "MAX_BODY_BYTES")  # 256 KB


def _json(data: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status,
                        headers={**_API_HEADERS, "X-App-Build": rendering._build_id()})


def _json_dumps_like_starlette(data) -> bytes:
    """The bytes JSONResponse would send for `data`, made once so a board that
    has not changed is not serialised again for every reader."""
    return json.dumps(data, ensure_ascii=False, allow_nan=False, indent=None,
                      separators=(",", ":")).encode("utf-8")


def _json_body(raw: bytes, status: int = 200) -> Response:
    """An answer made of bytes _json_dumps_like_starlette made, with the
    headers every _json answer carries."""
    return Response(raw, status_code=status, media_type="application/json",
                    headers={**_API_HEADERS, "X-App-Build": rendering._build_id()})


def _json_spliced(head: dict, field: str, raw: bytes) -> Response:
    """`head` with `raw`, bytes _json_dumps_like_starlette already made,
    spliced in as `field`, so a big object serialised once (to fingerprint
    it) is not serialised again inside the answer that carries it."""
    first = _json_dumps_like_starlette(head)
    return _json_body(first[:-1] + (b"," if len(first) > 2 else b"")
                      + _json_dumps_like_starlette(field) + b":" + raw + b"}")
# Per-process and best-effort (fine at this scale; if the app is ever scaled to
# multiple instances, move this to a shared store like Redis). asyncio is single
# threaded and these helpers never await, so no lock is needed.
_rl_hits: dict[str, list[float]] = {}
_rl_global: list[float] = []


def _client_key(request: Request) -> str:
    # Use the RIGHTMOST X-Forwarded-For entry: proxies append, so the last hop is the
    # one our own edge observed. The leftmost value is client-supplied and trivially
    # spoofed, which would hand every request a fresh rate-limit bucket.
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else "unknown"


def _window_ok(bucket: list[float], limit: int, now: float) -> bool:
    cutoff = now - RATE_WINDOW
    bucket[:] = [t for t in bucket if t >= cutoff]
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


def _window_hits(bucket: list[float], now: float) -> int:
    """How many marks the window holds, without adding one."""
    cutoff = now - RATE_WINDOW
    bucket[:] = [t for t in bucket if t >= cutoff]
    return len(bucket)


def _pre_checks(request: Request, max_body: Optional[int] = None) -> Optional[JSONResponse]:
    """The per-client rate window, the body cap, and the tab gate. Anonymous:
    nothing here needs to know who is asking."""
    now = time.monotonic()
    if len(_rl_hits) > 5000:  # guard the dict from unbounded growth
        _rl_hits.clear()
    if not _window_ok(_rl_hits.setdefault(_client_key(request), []), RATE_MAX_CLIENT, now):
        return _json({"error": "Too many requests in the last minute. Wait about a minute "
                               "and try again. Nothing was booked or charged."}, 429)
    cl = request.headers.get("content-length", "")
    if cl.isdigit() and int(cl) > (max_body or MAX_BODY_BYTES):
        return _json({"error": "Request too large."}, 413)
    denied = _tab_denied(request)
    if denied is not None:
        return denied
    return None


def _ai_slot() -> Optional[JSONResponse]:
    """A slot in the global AI window - the app's most expensive shared
    resource. Taken only once the caller is known to be a signed-in account,
    so a request with no session cannot spend one on its way to a 401."""
    if not _window_ok(_rl_global, RATE_MAX_GLOBAL, time.monotonic()):
        return _json({"error": "The assistant is busy right now. Please try again shortly."}, 429)
    return None


@perf.timed("auth")       # Server-Timing: the door, reading the body included
async def _guard(request: Request, *, ai: bool = False, min_level: int = 0,
                 max_body: Optional[int] = None, cap: Optional[int] = None,
                 body: bool = True, model: Optional[bodies.Model] = None):
    """(error_response, body, uid): the one door every signed-in route uses.

    Seventy routes carried their own copy of the same nine lines - rate
    window, session, body - and five helpers wrapped those lines again, each
    returning a different tuple. One of the copies spent an AI slot before it
    had checked the session. The order here is the order: anonymous checks,
    then who is asking, then what rank they hold, then the paid window, then
    the body. `body=False` is for a route that reads its own body later, after
    a check the caller wants to make first. `model` (gizmo/bodies.py) checks
    the fields the route reads, last of all: a field of the wrong kind is a
    400 naming it, heard only by a caller the door has let in."""
    pre = _pre_checks(request, max_body=max_body)
    if pre:
        return pre, None, ""
    ok, who, reason = team._authorize(request)
    if not ok:
        return _json({"error": team.AUTH_REFUSALS.get(reason, "Unauthorized"), "reason": reason or "session"}, 401), None, ""
    uid = str(who or "")
    perf.admit()            # Server-Timing is for people the door let in
    if ai:
        perf.no_record()    # a Claude answer is long by design
    if min_level and team._team_level(uid) < min_level:
        return _json({"error": "Only an admin can do that."}, 403), None, ""
    if ai:
        busy = _ai_slot()
        if busy:
            return busy, None, ""
    if not body:
        return None, {}, uid
    parsed = await _read_json_capped(request, cap=cap)
    if parsed is None:
        return _json({"error": "Request too large."}, 413), None, ""
    if model is not None:
        refused = _body_refusal(model, parsed)
        if refused:
            return refused, None, ""
    return None, parsed, uid


def _body_refusal(model, body) -> Optional[JSONResponse]:
    """The door's field check (gizmo/bodies.py), for the door itself and for
    a route that reads its own body after a check of its own (body=False):
    None, or the 400 naming the first field of the wrong kind. A body that is
    not a set of fields is the route's to answer, as it always was."""
    why = bodies.refusal(model, body) if isinstance(body, dict) else None
    return _json({"error": why}, 400) if why else None


async def _read_json_capped(request: Request, cap: Optional[int] = None) -> Optional[dict]:
    """Read + parse the JSON body, enforcing MAX_BODY_BYTES on the bytes ACTUALLY
    read (not just the Content-Length header). Returns {} for empty/invalid bodies,
    or None if the body exceeds the cap (the caller should answer 413). This bounds
    peak memory even for chunked/unlabeled request bodies."""
    total, chunks = 0, []
    try:
        async for chunk in request.stream():
            total += len(chunk)
            if total > (cap or MAX_BODY_BYTES):
                return None
            chunks.append(chunk)
    except Exception:
        return {}
    raw = b"".join(chunks)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
# API routes that belong to no tab and are open to every signed-in account:
# the sign-in flow, a person's own clock, profile and card layouts, and the admin routes,
# which refuse non-admins themselves. Anything else under /api/ that is not in
# _TAB_ROUTES is refused (see _tab_denied).
_OPEN_API = ("/api/auth/", "/api/team/", "/api/work/", "/api/google/status", "/api/alerts",
             "/api/usage", "/api/cache", "/api/profile", "/api/layouts", "/api/status", "/api/updates",
             "/api/schedule", "/api/backup", "/api/restore", "/api/privacy")

_TAB_ROUTES = (
    ("/api/overview", "overview"), ("/api/seo", "seo"), ("/api/keyword", "keywords"),
    ("/api/recon", "recon"),
    ("/api/forecast", "forecast"),
    ("/api/eori/", "labels"),
    ("/api/connector", "connector"),
    ("/api/products", "products"), ("/api/product", "products"),
    # customer-history also serves the CRM's deal modal (the Shopify card on a
    # linked person), so either tab opens it.
    ("/api/customers", "customers"), ("/api/customer-history", ("customers", "crm")),
    ("/api/customer-tags", "customers"), ("/api/reorder-radar", "customers"),
    ("/api/liability", "liability"),
    ("/api/crm/", "crm"), ("/api/loans", "loans"),
    ("/api/mail/", "mail"), ("/api/files/", "files"),
    ("/api/production-labels", "labels"), ("/api/production-state", "labels"),
    ("/api/order/", "labels"),
    ("/api/dispatch/", "labels"), ("/api/custom/", "labels"),
    ("/api/stock-usage", "labels"), ("/api/margin", "labels"),
    # The size sheet and its rulings serve the Production Manager's size check
    # and the Size list tab alike; the rule route keeps its own edit grant.
    ("/api/gobo-sizes", ("labels", "sizes")),
    # The EORI checker is part of preparing a customs invoice, so it lives
    # behind the same tab as the dispatch panel that prints one.
    ("/api/eori", "labels"),
    ("/api/memory", "memory"), ("/api/learn", "memory"), ("/api/impact", "memory"),
    ("/api/skills", "skills"), ("/api/chat", "chat"),
    ("/api/shipping", "labels"),
    ("/print/production-labels", "labels"),
)


def _tab_denied(request: Request) -> Optional[JSONResponse]:
    """The central lock. Only ever a 403: a 401 here would read as a dead
    session and bounce the person to the login screen in a loop."""
    path = request.url.path
    # Longest prefix wins: /api/production-labels must map to labels, not
    # fall to the shorter /api/product entry.
    tab, best = None, 0
    for p, t in _TAB_ROUTES:
        if path.startswith(p) and len(p) > best:
            tab, best = t, len(p)
    uid = team._session_uid(request.headers.get("x-app-session"))
    if not uid or not team._team_user(uid):
        # Not our concern here; _authorize answers 401. A session whose
        # account is gone (deleted, or the register lost) must reach that 401,
        # which sends the page to sign in or set up, not this gate's 403.
        return None
    if not tab:
        # Deny by default. A route under /api/ that no tab claims is either on
        # the short list below (self-service and admin routes that carry their
        # own role checks) or it is a route somebody added without deciding who
        # may call it, and the honest answer to that is no, loudly, in testing.
        if path.startswith("/api/") and not any(path.startswith(p) for p in _OPEN_API):
            logger.warning("route %s has no tab mapping and is not on _OPEN_API; refused", path)
            return _json({"error": "That part of the app is not open to your account."}, 403)
        return None
    tabs = team._user_tabs(uid)
    allowed = (tab,) if isinstance(tab, str) else tab
    if tabs is None or any(t in tabs for t in allowed):
        return None
    activity._track_denied(uid, path)
    return _json({"error": "That part of the app is switched off for your account. "
                           "Ask an admin if you need it."}, 403)


# ---------------------------------------------------------------------------
# The server secret's check: compared in constant time, and a mistyped key is a
# plain no, never an error.
# ---------------------------------------------------------------------------

def _secret_ok(given: str, expected: str) -> bool:
    """Constant-time compare that cannot raise. compare_digest throws
    TypeError on a non-ASCII str, so a mistyped key returned a 500 where a
    plain 403 belongs - and a stack trace is a worse answer than "no"."""
    if not expected or not given:
        return False
    try:
        return secrets.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))
    except (AttributeError, TypeError):
        return False


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
from gizmo import activity  # noqa: E402
from gizmo import team  # noqa: E402
import copilot as core  # noqa: E402
from gizmo import rendering  # noqa: E402
