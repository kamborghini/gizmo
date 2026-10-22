"""Work sessions: clocking in and out, for part-time accounts. The sessions
store and its copy in memory, who is monitored, the open session. Moved out
of copilot.py (stage 4 of the 14 October audit); its routes are in
gizmo/routes/work.py. Read as `work.NAME`.
"""
import logging
import os
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional
from gizmo.config import _env_num
from gizmo import store as jsonstore
from datetime import timedelta

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


# ---------------------------------------------------------------------------
# Work sessions: clocking in and out, for part-time accounts only. The clock
# is the SERVER'S: routes take no timestamps from the browser, one session can
# be open per person, and a close computes its own duration. Whether someone
# is monitored follows their ROLE at the moment of each event, never a name.
# Sessions are append-only; an admin resolving a forgotten clock-out closes
# the session with correction stamps beside the original start, on the ledger.
# ---------------------------------------------------------------------------


WORK_PATH = os.environ.get("WORK_PATH", "/data/worklog.json")
WORK_KEEP = _env_num(int, os.environ.get("WORK_KEEP", "2000"), "2000", "WORK_KEEP")
# The part-timers' hours are the payroll record. The live log is capped for
# speed; what leaves it is appended here, one JSON line per shift, and the
# report reads both. The cap used to drop what it trimmed, so a report for an
# older period came back short or empty without a word.
WORK_ARCHIVE_PATH = os.environ.get(
    "WORK_ARCHIVE_PATH", os.path.join(os.path.dirname(WORK_PATH) or ".", "worklog_archive.jsonl"))
# Shorter than this is a mis-tap, not a shift. It also stops the fixed-size
# work log being flushed by anyone willing to clock in and out repeatedly.
WORK_MIN_SECS = _env_num(int, os.environ.get("WORK_MIN_SECS", "60"), "60", "WORK_MIN_SECS")
_work_mem: Optional[dict] = None


def _let_go_of_work_in_memory(paths) -> list:
    """Let go of the work sessions held in memory (see jsonstore.holds_in_memory)."""
    global _work_mem
    if paths is None or WORK_PATH in paths:
        _work_mem = None
        return [WORK_PATH]
    return []


jsonstore.holds_in_memory(_let_go_of_work_in_memory)



def _load_work() -> dict:
    global _work_mem
    if _work_mem is None:
        d = jsonstore._load_json_store(WORK_PATH, "work_store", None)
        _work_mem = d if isinstance(d, dict) and "sessions" in d else {"seq": 0, "open": {}, "sessions": []}
    return _work_mem


def _work_trim(d: dict) -> None:
    """Move shifts past WORK_KEEP into the archive; if the archive cannot be
    written, they stay in the live log rather than be lost."""
    over = len(d.get("sessions") or []) - WORK_KEEP
    if over <= 0:
        return
    gone = d["sessions"][:over]
    try:
        os.makedirs(os.path.dirname(WORK_ARCHIVE_PATH) or ".", exist_ok=True)
        with open(WORK_ARCHIVE_PATH, "a", encoding="utf-8") as fh:
            for ws in gone:
                fh.write(json.dumps(ws, default=str) + "\n")
    except Exception:
        logger.exception("work archive append failed; the shifts stay in the live log")
        return
    d["sessions"] = d["sessions"][over:]


def _work_archived() -> list:
    """Every archived shift; a line that does not parse is skipped, not fatal."""
    out = []
    try:
        with open(WORK_ARCHIVE_PATH, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except FileNotFoundError:
        pass
    except Exception:
        logger.exception("work archive read failed")
    return out


def _write_work(d: dict) -> None:
    """Memory never outlives a failed write. Handlers mutate the object the
    loader handed them, so by the time a refusal happens the cache already
    holds the change - it has to be dropped, or a shift that was never saved
    keeps being served until the process restarts."""
    global _work_mem
    if not jsonstore._store_writable(WORK_PATH):
        _work_mem = None
        raise RuntimeError("work log is not writable")
    _work_trim(d)
    try:
        jsonstore._write_json_store(WORK_PATH, "work_store", d)
    except Exception:
        _work_mem = None
        raise
    _work_mem = d


def _work_monitored(uid: Optional[str]) -> bool:
    """Role-driven, checked at the moment it matters: change the role and the
    monitoring follows by itself."""
    return team._team_role(uid) == "parttime"


def _work_open_session(uid: Optional[str]) -> Optional[dict]:
    if not uid:
        return None
    return _load_work()["open"].get(str(uid))


def _work_close_open(uid: str, by: str, note: str, action: str) -> Optional[dict]:
    """Close an account's open shift now, as `by`'s correction, and return
    it; None when nothing was open. For the three ways an account stops being
    watched: its role changes, it is switched off, or it is deleted. Only the
    role change used to do this, so a deleted part-timer who forgot to clock
    out sat on the work board clocked in for good, their hours still climbing."""
    w = _load_work()
    ws = w["open"].pop(uid, None)
    if not ws:
        return None
    nowu = datetime.now(timezone.utc)
    ws["end"] = nowu.isoformat()
    try:
        ws["secs"] = max(0, int((nowu - datetime.fromisoformat(ws["start"])).total_seconds()))
    except Exception:  # an unreadable start counts no time
        ws["secs"] = 0
    ws.update({"corrected": True, "corrected_by": by, "corrected_at": nowu.isoformat(), "note": note})
    w["sessions"].append(ws)
    _write_work(w)
    activity._track(by, "work", action, team._team_name(uid) or uid)
    return ws


def _work_close_orphans() -> list:
    """Close any open shift whose account is gone or switched off; the ids
    closed. Deleting or switching off an account closes its shift now, but a
    shift left open by an account removed before that did sits on the board
    for good, so the hourly team check sweeps them up."""
    # An unreadable or empty register reads as nobody, and nobody would mean
    # every shift on the board: the watchdog alerts on that, this does nothing.
    if team.USERS_PATH in jsonstore._poisoned_stores or team._team_setup_needed():
        return []
    users = (team._load_users() or {}).get("users") or {}
    closed = []
    for uid in list((_load_work().get("open") or {}).keys()):
        u = users.get(uid)
        # Delete is a soft delete, so an account the register does not hold at
        # all means the register was lost or rolled back, not that it was removed.
        if u is not None and (u.get("deleted") or not u.get("active", True)):
            if _work_close_open(uid, "", "closed automatically: the account had been removed or "
                                         "switched off", "closed a session left by a removed account"):
                closed.append(uid)
    return closed


def _work_secs(uid: str, day_from: str) -> int:
    """Seconds worked since day_from (ISO), open session counted to now."""
    d = _load_work()
    now = datetime.now(timezone.utc)
    total = 0
    for s in d["sessions"]:
        if s.get("uid") == uid and str(s.get("start") or "") >= day_from:
            total += int(s.get("secs") or 0)
    o = d["open"].get(uid)
    if o and str(o.get("start") or "") >= day_from:
        try:
            total += max(0, int((now - datetime.fromisoformat(o["start"])).total_seconds()))
        except Exception:
            pass  # an unreadable start adds no time, never an error in the total
    return total


def _work_csv(rows: list, names: dict, counts: dict) -> str:
    """The payroll sheet: one line per session, times as the clock on the
    wall showed them. Sessions are stamped in UTC; slicing the stamp put the
    whole of summer an hour early and a shift that started after eleven at
    night on the day before."""
    def _csv_cell(v) -> str:
        # A team display name is free text and unsanitised; without the
        # armour a name like =HYPERLINK(...) runs as a formula in Excel,
        # and an embedded quote breaks the row. Matches the client crmCSV.
        v = str(v if v is not None else "")
        if v[:1] in ("=", "+", "-", "@", "\t", "\r"):
            v = "'" + v
        return '"' + v.replace('"', '""') + '"' if any(c in v for c in ',"\n\r') else v

    def _hhmm(iso: str) -> str:
        try:
            when = datetime.fromisoformat(str(iso or ""))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return when.astimezone(ZoneInfo("Europe/London")).strftime("%H:%M")
        except ValueError:
            return str(iso or "")[11:16]

    lines = ["Name,Date,Clock in,Clock out,Hours,Actions,Corrected"]
    for s in rows:
        st, en = str(s.get("start") or ""), str(s.get("end") or "")
        lines.append(",".join([
            _csv_cell(names.get(s.get("uid")) or s.get("uid") or ""),
            clock._london_day(st), _hhmm(st), _hhmm(en) if en else "",
            f"{int(s.get('secs') or 0) / 3600:.2f}",
            str(counts.get(s.get("id"), 0)),
            "yes" if s.get("corrected") else ""]))
    return "\n".join(lines)


def _fmt_secs(secs: int) -> str:
    h, m = int(secs) // 3600, (int(secs) % 3600) // 60
    return (f"{h}h {m:02d}m" if h else f"{m}m")

def _day_starts():
    """When today, this week and this month began, as UTC stamps that compare
    with the sessions' own: the boundaries are London midnights, because the
    people clocking in are in London and a day that starts at 01:00 all summer
    put a late shift in the wrong day, week and month."""
    now = datetime.now(ZoneInfo("Europe/London"))
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = today - timedelta(days=today.weekday())
    month = today.replace(day=1)
    return tuple(x.astimezone(timezone.utc).isoformat() for x in (today, week, month))


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as sibling.NAME, never a copied name.
from gizmo import activity  # noqa: E402
from gizmo import team  # noqa: E402
from gizmo import clock  # noqa: E402
