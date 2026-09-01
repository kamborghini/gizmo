"""Ship logs and audit events off the box.

Two problems, one fix. Application logs go to stdout and nothing survives a
container restart, so an incident cannot be reconstructed after the fact. And
the audit ledger - who booked what, who changed a size, who was granted access -
is a file on the same volume it audits, so whatever loses the volume loses the
evidence too.

Both streams go to an HTTPS sink here. Everything below exists so that a
logging component can never be the thing that takes the dispatch desk down:

  * No LOG_DRAIN_URL configured and nothing installs. Deployments that have not
    set one behave exactly as before.
  * The queue is BOUNDED and drops the oldest when full. An unbounded buffer in
    front of a slow sink is an out-of-memory kill wearing a helpful hat.
  * The sender runs on its own daemon thread. A slow POST cannot stall a
    request, and it never touches the event loop.
  * Every exception in the sender is swallowed and counted. A sink that is down,
    slow, or returning nonsense must be invisible to the app.
  * Records are scrubbed before they leave. A log line carries whatever was
    interpolated into it, and a credential reaching a third party is a leak
    with extra steps.
"""
import json
import logging
import os
import queue
import re
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger("shopify_mcp.logdrain")

# Anything shaped like a credential. Deliberately broad: a false positive costs
# a redacted log line, a false negative ships a live token to a third party.
_SECRETS = [
    re.compile(r"\b(shpat|shpca|shpss|shppa)_[A-Za-z0-9]{8,}", re.I),   # Shopify
    re.compile(r"\b1//[A-Za-z0-9_\-]{10,}"),                            # Google refresh
    re.compile(r"\bghp_[A-Za-z0-9]{10,}", re.I),                        # GitHub
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}", re.I),                      # API keys
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{16,}", re.I),
    re.compile(r"(?i)(refresh_token|access_token|api[_-]?key|password|secret)"
               r"\s*[=:]\s*\"?([A-Za-z0-9._/\-+]{8,})\"?"),
]

_q: "queue.Queue" = queue.Queue(maxsize=2000)
_state = {"url": "", "token": "", "sender": None, "thread": None,
          "stop": False, "dropped": 0}
_lock = threading.Lock()


def scrub(text: str) -> str:
    """Redact anything credential-shaped, keeping the shape of the message."""
    out = str(text)
    for pat in _SECRETS:
        if pat.groups >= 2:
            out = pat.sub(lambda m: f"{m.group(1)}=[redacted]", out)
        else:
            out = pat.sub("[redacted]", out)
    return out


def dropped() -> int:
    return _state["dropped"]


def pending() -> int:
    return _q.qsize()


def _put(event: dict) -> None:
    """Never blocks. When the queue is full the OLDEST goes, because during an
    incident the newest lines are the ones worth having."""
    if not _state["url"]:
        return
    event = json.loads(scrub(json.dumps(event, default=str)))
    try:
        _q.put_nowait(event)
    except queue.Full:
        with _lock:
            _state["dropped"] += 1
        try:
            _q.get_nowait()
            _q.put_nowait(event)
        except (queue.Empty, queue.Full):
            pass


def audit(event: dict) -> None:
    """One audit event, off the volume it audits."""
    e = dict(event or {})
    e.setdefault("at", datetime.now(timezone.utc).isoformat())
    e["kind"] = "audit"
    _put(e)


class _Handler(logging.Handler):
    def emit(self, record):
        try:
            _put({"kind": "log", "at": datetime.now(timezone.utc).isoformat(),
                  "level": record.levelname, "logger": record.name,
                  "message": record.getMessage()})
        except Exception:
            pass      # a logging handler that raises breaks the caller's logging


def _default_sender(url: str, token: str):
    def send(batch):
        import httpx
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        httpx.post(url, json={"events": batch}, headers=headers, timeout=10)
    return send


def _run():
    """Batch and post. Every failure is counted and forgotten - retrying a dead
    sink forever would just grow the queue until it starts dropping anyway."""
    while not _state["stop"]:
        batch = []
        try:
            batch.append(_q.get(timeout=0.25))
        except queue.Empty:
            continue
        while len(batch) < 100:
            try:
                batch.append(_q.get_nowait())
            except queue.Empty:
                break
        try:
            sender = _state["sender"]
            if sender:
                sender(batch)
        except Exception:
            with _lock:
                _state["dropped"] += len(batch)


def flush(timeout: float = 5.0) -> None:
    """Drain what is queued. For tests and for shutdown."""
    end = time.time() + timeout
    while _q.qsize() and time.time() < end:
        time.sleep(0.02)
    time.sleep(0.05)


def install(url: str = None, token: str = None, sender=None,
            maxsize: int = None, autostart: bool = True) -> bool:
    """Attach to the root logger. Returns False when no drain is configured."""
    global _q
    url = url if url is not None else os.environ.get("LOG_DRAIN_URL", "")
    token = token if token is not None else os.environ.get("LOG_DRAIN_TOKEN", "")
    if not url:
        return False
    if maxsize:
        _q = queue.Queue(maxsize=maxsize)
    _state.update({"url": url, "token": token, "stop": False, "dropped": 0,
                   "sender": sender or _default_sender(url, token)})
    h = _Handler()
    h.setLevel(logging.INFO)
    root = logging.getLogger()
    if not any(isinstance(x, _Handler) for x in root.handlers):
        root.addHandler(h)
    if autostart and not _state["thread"]:
        t = threading.Thread(target=_run, name="logdrain", daemon=True)
        _state["thread"] = t
        t.start()
    return True


def stop() -> None:
    _state["stop"] = True
    t = _state.get("thread")
    if t:
        t.join(timeout=2)
    _state.update({"url": "", "token": "", "sender": None, "thread": None,
                   "dropped": 0})
    root = logging.getLogger()
    for h in [x for x in root.handlers if isinstance(x, _Handler)]:
        root.removeHandler(h)
    while True:
        try:
            _q.get_nowait()
        except queue.Empty:
            break
