"""The London clock: today's date, a day's start and the time of day in London,
which the whole app reads. On the floor: it imports nothing above it. Moved
out of copilot.py (stage 4 of the 14 October audit). Read as `clock.NAME`.
"""
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")




# ---------------------------------------------------------------------------
# Today's date and time in London, which the whole app reads.
# ---------------------------------------------------------------------------


def _london_today():
    """Today's date where the business is. The server clock is UTC, so a date
    taken from it is yesterday's for the hour after midnight all summer; a
    label printed at half past eleven read a wedding three days off as not
    urgent, and the payroll sheet started every day at 01:00."""
    return datetime.now(ZoneInfo("Europe/London")).date()


def _london_day(iso: str) -> str:
    """The London calendar day of a UTC stamp, as YYYY-MM-DD; a stamp that
    cannot be read gives its first ten characters back, which is what the
    callers used to slice off unconverted."""
    try:
        when = datetime.fromisoformat(str(iso or ""))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return when.astimezone(ZoneInfo("Europe/London")).date().isoformat()
    except ValueError:
        return str(iso or "")[:10]


def _london_hm(iso) -> str:
    """"14:05 on 22 Sep", London time, from a UTC stamp; the stamp itself when
    it cannot be read."""
    try:
        when = datetime.fromisoformat(str(iso or ""))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return when.astimezone(ZoneInfo("Europe/London")).strftime("%H:%M on %d %b")
    except ValueError:
        return str(iso or "")
