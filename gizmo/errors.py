"""The app's error log: what went wrong, kept for Settings and the alerts.
Moved out of copilot.py (stage 4 of the 14 October audit); part of the
floor, so it imports nothing above it. Read as `errors.NAME`.
"""
import logging
import os
from datetime import datetime, timedelta, timezone

from gizmo import store as jsonstore

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


ERRORS_PATH = os.environ.get("ERRORS_PATH", "/data/app_errors.json")
ERRORS_MAX = 50


def _record_error(where: str, exc: BaseException) -> None:
    """Keep the last few unhandled failures. Until this existed a 500 in the
    dispatch flow was invisible unless somebody happened to be watching the
    server log, which at a dispatch desk means never."""
    try:
        rows = jsonstore._load_json_store(ERRORS_PATH, "errors", [])
        rows = [{"at": datetime.now(timezone.utc).isoformat(),
                 "where": str(where)[:120],
                 "error": (type(exc).__name__ + ": " + str(exc))[:400]}] + list(rows)
        rows = rows[:ERRORS_MAX]
        if jsonstore._store_writable(ERRORS_PATH):
            jsonstore._write_json_store(ERRORS_PATH, "errors", rows)
    except Exception:
        logger.exception("could not record an app error")


def _recent_errors(hours: int = 24) -> list:
    cut = datetime.now(timezone.utc) - timedelta(hours=hours)
    out = []
    for r in jsonstore._load_json_store(ERRORS_PATH, "errors", []):
        try:
            when = datetime.fromisoformat(str(r.get("at") or ""))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if when >= cut:
            out.append(r)
    return out
