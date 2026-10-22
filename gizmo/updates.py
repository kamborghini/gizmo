"""What's new: the release notes that ship with the release (the repository's
data/changelog.json), the app's version and start time, and the desk's own
feature requests. Moved out of copilot.py (stage 4 of the 14 October audit);
its route is in gizmo/routes/updates.py. Read as `updates.NAME`.
"""
import logging
import os
import json
from datetime import datetime, timezone
from gizmo import store as jsonstore

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


# The repository, where data/ ships with the code. This module is one
# folder down from where copilot.py built this path from its own file.
_REPO = os.path.dirname(os.path.dirname(__file__))


# ---------------------------------------------------------------------------
# What's new: the release notes that ship WITH the release, and the desk's own
# feature requests. The changelog is a repo file, so the running build always
# carries exactly the notes for the code that is running - a changelog kept on
# the volume would drift from the deploy the moment either changed alone.
# ---------------------------------------------------------------------------


FEEDBACK_PATH      = os.environ.get("FEEDBACK_PATH", "/data/feedback.json")  # feature requests from the desk
CHANGELOG_PATH     = os.environ.get("CHANGELOG_PATH",
                                    os.path.join(_REPO, "data", "changelog.json"))
# Keyed on (path, mtime), not mtime alone: keyed on time only, a cache built
# from one file can be served for another that happens to share a timestamp.
_changelog_cache: dict = {"mtime": None, "releases": []}


def _load_changelog() -> list:
    """Releases newest first. A malformed or missing file costs the What's new
    panel, never the app: it is notes, not data."""
    try:
        key = (CHANGELOG_PATH, os.path.getmtime(CHANGELOG_PATH))
    except OSError:
        return []
    if _changelog_cache["mtime"] == key:
        return _changelog_cache["releases"]
    rows = []
    try:
        with open(CHANGELOG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for r in (data.get("releases") if isinstance(data, dict) else data) or []:
            if not isinstance(r, dict) or not r.get("date"):
                continue
            items = [{"kind": str(i.get("kind") or "improved")[:12],
                      # Whole notes: twelve of them ran past 400 characters
                      # and were cut mid-word on the Guide with no ellipsis.
                      "text": str(i.get("text") or "")[:4000],
                      "tab": str(i.get("tab") or "")[:20]}
                     for i in (r.get("items") or []) if isinstance(i, dict) and i.get("text")]
            if items:
                rows.append({"date": str(r["date"])[:10],
                             "title": str(r.get("title") or "")[:120], "items": items})
        rows.sort(key=lambda r: r["date"], reverse=True)
    except Exception:
        logger.exception("changelog: could not read %s", CHANGELOG_PATH)
        # Last good notes for THIS file, or nothing - never another file's.
        return (_changelog_cache["releases"]
                if (_changelog_cache["mtime"] or ("", 0))[0] == CHANGELOG_PATH else [])
    _changelog_cache["mtime"], _changelog_cache["releases"] = key, rows
    return rows


_boot_at = datetime.now(timezone.utc).isoformat()


def _app_version() -> dict:
    """What the running build IS: the deployed commit, when this instance
    started, and the newest release the notes describe."""
    rel = _load_changelog()
    return {"sha": (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "")[:12],
            "started_at": _boot_at,
            "latest": (rel[0]["date"] if rel else ""),
            "releases": len(rel)}


def _load_feedback() -> dict:
    d = jsonstore._load_json_store(FEEDBACK_PATH, "feedback", None)
    if not isinstance(d, dict) or "items" not in d:
        d = {"seq": 0, "items": []}
    return d


def _write_feedback(d: dict) -> None:
    if not jsonstore._store_writable(FEEDBACK_PATH):
        raise RuntimeError("feedback store is not writable")
    jsonstore._write_json_store(FEEDBACK_PATH, "feedback", d)


FEEDBACK_STATES = ("open", "planned", "shipped", "declined")


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as sibling.NAME, never a copied name.
