"""Where a request's time goes, measured live, and how answers are compressed.

Shared by server.py and copilot.py, and importing neither.

Timing. Nothing in production could be timed from outside: there is no
console to read, so every Shopify and Gmail wait in the 2026-10-12 speed
audit was a model. Each /api/ request now carries a small dict of marks in a
context variable. The door (auth), store reads and saves (store), Shopify
calls (shop) and compression (zip) add to it, the whole request is "app",
and the lot goes out as a Server-Timing header, which the browser's DevTools
shows on the Reactor frame. Marks are summed, so two Shopify calls running
side by side can add up to more than the request took: it is time spent in,
not a timeline.

Each route also keeps its last 200 times in memory, for the "Response times"
row an admin sees in Settings. Memory only, and gone on restart: what it is
for is the question "what is slow today", not a history.

Compression. zstd at level 3 does what gzip at level 6 did for a sixth to a
twelfth of the CPU, and Chrome, which runs the Shopify admin, asks for it.
Anything that does not still gets gzip.
"""
import collections
import contextvars
import functools
import gzip
import inspect
import math
import time

try:                                    # in the standard library from Python 3.14
    from compression import zstd as _zstd
except ImportError:                     # pragma: no cover - the image is 3.14
    _zstd = None

_marks: contextvars.ContextVar = contextvars.ContextVar("reactor_timing", default=None)

ROUTE_KEEP = 200        # times kept per route
ROUTE_MAX = 400         # routes remembered; the router has about 150


def start():
    """Open the marks for one request. Returns (marks, token for stop)."""
    marks: dict = {}
    return marks, _marks.set(marks)


def stop(token) -> None:
    _marks.reset(token)


def mark(name: str, ms: float) -> None:
    """Add `ms` milliseconds to the current request's `name`, if there is one.
    Free outside a request: a background job simply has nowhere to add to."""
    marks = _marks.get()
    if marks is not None:
        marks[name] = marks.get(name, 0.0) + ms


class span:
    """`with perf.span("store"):` adds the block's wall time to that mark."""

    __slots__ = ("name", "t0")

    def __init__(self, name: str):
        self.name = name

    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        mark(self.name, (time.perf_counter() - self.t0) * 1000)
        return False


def timed(name: str):
    """Decorate a function, plain or async, so each call's wall time adds to
    `name`."""
    def wrap(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def inner(*a, **k):
                with span(name):
                    return await fn(*a, **k)
        else:
            @functools.wraps(fn)
            def inner(*a, **k):
                with span(name):
                    return fn(*a, **k)
        return inner
    return wrap


def admit() -> None:
    """The door let this request in on a live session. Only such a request
    gets the header or is counted: on a refusal or a sign-in the marks would
    say what the vague answer is careful not to (a wrong password for a real
    name saves a failure count, a made-up name saves nothing), and refused
    requests in the table would wash out the real times."""
    marks = _marks.get()
    if marks is not None:
        marks["_door"] = True


def no_record() -> None:
    """Long by design (a Claude call, a backup, a forced Gmail sync): still
    timed in its own header, but kept out of the slowest-routes table, which
    is for the pages that ought to be quick."""
    marks = _marks.get()
    if marks is not None:
        marks["_skip"] = True


def header(marks: dict) -> str:
    """The Server-Timing value: app first, then the rest by name. Flags (a
    leading underscore) are not timings and never leave."""
    names = (["app"] if "app" in marks else []) + sorted(k for k in marks if k != "app" and k[:1] != "_")
    return ", ".join(f"{n};dur={marks[n]:.1f}" for n in names)


ROUTES: dict = {}


def record(route: str, ms: float) -> None:
    times = ROUTES.get(route)
    if times is None:
        if len(ROUTES) >= ROUTE_MAX:
            return
        times = ROUTES[route] = collections.deque(maxlen=ROUTE_KEEP)
    times.append(ms)


def summary(limit: int = 12) -> list:
    """The routes by their slowest twentieth, slowest first."""
    rows = []
    for route, times in list(ROUTES.items()):
        if not times:
            continue
        ordered = sorted(times)
        n = len(ordered)
        # Nearest rank: exactly n/20 of the times are above p95, which is
        # what Settings says ("1 in 20 over").
        rows.append({"route": route, "count": n,
                     "p50": round(ordered[max(0, math.ceil(n * 0.5) - 1)], 1),
                     "p95": round(ordered[max(0, math.ceil(n * 0.95) - 1)], 1)})
    rows.sort(key=lambda r: -r["p95"])
    return rows[:limit]


GZIP_LEVEL = 6
ZSTD_LEVEL = 3
# The packed page assets are made once per build, away from any request, so
# they can afford the strongest levels.
ZSTD_STRONG = 19
GZIP_STRONG = 9


def pick_encoding(accept: str) -> str:
    """"zstd", "gzip" or "" for an Accept-Encoding value. A coding listed with
    q=0 is refused, as the header says."""
    ok = set()
    for part in (accept or "").lower().split(","):
        name, _, params = part.strip().partition(";")
        q = 1.0
        for p in params.split(";"):
            k, _, v = p.strip().partition("=")
            if k == "q":
                try:
                    q = float(v)
                except ValueError:
                    q = 0.0
        if name and q > 0:
            ok.add(name.strip())
    if _zstd is not None and "zstd" in ok:
        return "zstd"
    return "gzip" if "gzip" in ok else ""


def compress(body: bytes, enc: str, strong: bool = False) -> bytes:
    if enc == "zstd" and _zstd is not None:
        return _zstd.compress(body, ZSTD_STRONG if strong else ZSTD_LEVEL)
    if enc == "gzip":
        return gzip.compress(body, GZIP_STRONG if strong else GZIP_LEVEL)
    raise ValueError("unknown encoding: " + repr(enc))
