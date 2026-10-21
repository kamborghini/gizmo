"""The activity log: who did what, kept for the Team tab and the alerts, with
its store held in memory, flushed in batches and at exit, and the noise
coalescers that keep refused sign-ins and denied requests to a row each.

Moved out of copilot.py (stage 4 of the 14 October audit). Read as
`activity.NAME`.
"""
import logging
import os
import atexit
import asyncio
from datetime import datetime, timezone
from typing import Optional
import logdrain
from gizmo.config import _env_num
from gizmo import store as jsonstore

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")




ACTIVITY_PATH = os.environ.get("ACTIVITY_PATH", "/data/activity.json")


ACTIVITY_MAX = _env_num(int, os.environ.get("ACTIVITY_MAX", "8000"), "8000", "ACTIVITY_MAX")


_events_mem: Optional[list] = None
_events_dirty = False
_events_flush_pending = False


def _let_go_of_events_in_memory(paths) -> list:
    """Let go of the activity log held in memory (see jsonstore.holds_in_memory)."""
    global _events_mem
    if paths is None or ACTIVITY_PATH in paths:
        _events_mem = None
        return [ACTIVITY_PATH]
    return []


jsonstore.holds_in_memory(_let_go_of_events_in_memory)


def _load_events() -> list:
    global _events_mem
    if _events_mem is None:
        d = jsonstore._load_json_store(ACTIVITY_PATH, "events", [])
        _events_mem = d if isinstance(d, list) else []
    return _events_mem


def _events_flush() -> None:
    """Write the ledger to disk. Called a few seconds after activity (never
    inline with a request), hourly from the watchdog, and at shutdown; a hard
    crash can lose at most those few seconds of metrics, never work."""
    global _events_dirty, _events_flush_pending
    _events_flush_pending = False
    if not _events_dirty:
        return
    try:
        rows = _load_events()
        if jsonstore._store_writable(ACTIVITY_PATH):
            jsonstore._write_json_store(ACTIVITY_PATH, "events", rows)
        _events_dirty = False
    except Exception:
        logger.exception("activity ledger write failed")


atexit.register(_events_flush)


_login_noise = {"hour": "", "count": 0, "logged": 0}
LOGIN_NOISE_ROWS = 10      # ledger rows per hour for unknown-username failures
_deny_noise = {"hour": "", "logged": 0}
DENY_NOISE_ROWS = 20       # ledger rows per hour for closed-tab refusals


def _track_denied(uid: str, path: str) -> None:
    """A signed-in account asking for a tab it does not have. One is a stale
    browser; a run of them is somebody probing. Listed the first few an hour,
    then not - the ledger must not be flushable from a member account."""
    hour = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    if _deny_noise["hour"] != hour:
        _deny_noise.update({"hour": hour, "logged": 0})
    if _deny_noise["logged"] < DENY_NOISE_ROWS:
        _deny_noise["logged"] += 1
        _track(uid, "auth", "refused a closed tab", path[:120])
    elif _deny_noise["logged"] == DENY_NOISE_ROWS:
        _deny_noise["logged"] += 1
        _track("", "auth", "refusals continuing",
               "further closed-tab refusals this hour are not being listed")


def _track_login_refusal(uid: str, reason: str, username: str = "") -> None:
    """A failed login for an account that EXISTS but cannot sign in.

    These were written one row per attempt, unthrottled. The ledger is a
    fixed-size FIFO of 8000 rows, so anyone who could reach the login form and
    knew one username - a switched-off ex-employee's, say - could push every
    record of who booked a courier label, who marked orders made and who
    changed team access out of the far end. The paused and switched-off
    branches have no lockout of their own, so nothing else bounded them.

    Coalesced on the same hourly budget as the unknown-username path: the first
    few in full, then counted and said once.
    """
    _track_login_noise(username or "(known account)", uid=uid, reason=reason)


def _track_login_noise(username: str, uid: str = "", reason: str = "") -> None:
    """Failed logins for usernames that do not exist are the one ledger write
    an unauthenticated caller can drive. Log the first few an hour in full,
    then count silently and say so once - the audit history must not be
    evictable by anyone who can reach the login form."""
    hour = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    if _login_noise["hour"] != hour:
        _login_noise.update({"hour": hour, "count": 0, "logged": 0})
    _login_noise["count"] += 1
    if _login_noise["logged"] < LOGIN_NOISE_ROWS:
        _login_noise["logged"] += 1
        _track(uid, "auth", "failed login",
               reason or f"unknown username {username[:40]}")
    elif _login_noise["logged"] == LOGIN_NOISE_ROWS:
        _login_noise["logged"] += 1
        _track("", "auth", "failed logins continuing",
               "further failed sign-ins this hour are not being listed")


def _track(sub: Optional[str], area: str, action: str, detail: str = "") -> None:
    """One line in the ledger. Appends in memory and lets a debounced flush
    carry it to disk, so no request pays for a full-file rewrite."""
    global _events_dirty, _events_flush_pending
    try:
        rows = _load_events()
        e = {"t": datetime.now(timezone.utc).isoformat(),
             "sub": str(sub or ""), "area": area,
             "action": str(action)[:80], "detail": str(detail)[:200]}
        if not sub:
            e["src"] = "system"    # webhooks, schedulers, integrations: never a person
        elif work._work_monitored(sub):
            ws = work._work_open_session(sub)
            if ws:
                e["ws"] = ws.get("id")   # billable: on the clock
        rows.append(e)
        # Also off the box. The ledger is a file on the volume it audits, so
        # whatever loses the volume loses the evidence with it. Never allowed
        # to raise: an audit trail must not be able to fail a booking.
        try:
            logdrain.audit(e)
        except Exception:
            pass  # never raises: an audit trail must not be able to fail a booking (above)
        if len(rows) > ACTIVITY_MAX:
            del rows[:len(rows) - ACTIVITY_MAX]
        _events_dirty = True
        try:
            loop = asyncio.get_running_loop()
            if not _events_flush_pending:
                _events_flush_pending = True
                loop.call_later(3, _events_flush)
        except RuntimeError:
            _events_flush()    # no loop here (boot, threads): write now
    except Exception:
        logger.exception("activity ledger write failed")


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
import copilot as core  # noqa: E402
from gizmo import work  # noqa: E402
