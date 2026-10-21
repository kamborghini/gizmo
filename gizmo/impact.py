"""Impact tracking: a snapshot of the store's headline figures when a change is
made, and how they have moved since, for the Impact list and the assistant.
Moved out of copilot.py (stage 4 of the 14 October audit); its route is in
gizmo/routes/impact.py. Read as `impact.NAME`.
"""
import logging
import os
from datetime import datetime, timezone
import google_data
from gizmo.config import _env_num
from gizmo import store as jsonstore

# The same logger as copilot.py's, so these log lines read as before.
logger = logging.getLogger("shopify_mcp.copilot")


IMPACT_PATH        = os.environ.get("IMPACT_PATH", "/data/impact.json")  # tracked-action impact log
IMPACT_MAX         = _env_num(int, os.environ.get("IMPACT_MAX", "100"), "100", "IMPACT_MAX")


# ---------------------------------------------------------------------------
# Impact tracking — "close the loop": snapshot headline metrics when a change is
# made, then measure how they moved since. Proves whether advice worked.
# ---------------------------------------------------------------------------


def _load_impact() -> list[dict]:
    return jsonstore._load_json_store(IMPACT_PATH, "items", [])


def _write_impact(items: list[dict]) -> list[dict]:
    if not jsonstore._store_writable(IMPACT_PATH):
        return items[:IMPACT_MAX]
    jsonstore._write_json_store(IMPACT_PATH, "items", items[:IMPACT_MAX])
    return items[:IMPACT_MAX]


async def _impact_snapshot(registry: dict) -> dict:
    """A light 28-day headline-metric snapshot (revenue, orders, sessions, search
    clicks). Each source degrades to absent on error, so this never raises."""
    snap: dict = {"at": datetime.now(timezone.utc).isoformat()}
    try:
        m28: dict = {}
        orders = [o for o in await orderbook._orders_28d(registry, meta=m28) if orderbook._order_counts(o)]
        if not m28.get("failed"):      # a failed read is absent, never a zero
            snap["revenue_28d"] = round(sum(orderbook._order_revenue(o) for o in orders), 2)
            snap["orders_28d"] = len(orders)
    except Exception:
        pass
    try:
        if google_data.ga4_configured():
            ga = await google_data.ga4_summary(28)
            if ga and not ga.get("error") and ga.get("sessions") is not None:
                snap["sessions_28d"] = ga["sessions"]
    except Exception:
        pass
    try:
        if google_data.gsc_configured():
            g = await google_data.gsc_overview(28)
            if g and not g.get("error") and g.get("clicks") is not None:
                snap["clicks_28d"] = g["clicks"]
    except Exception:
        pass
    return snap


_impact_snap_cache: dict = {}

_IMPACT_METRICS = [("revenue_28d", "Revenue", True), ("orders_28d", "Orders", False),
                   ("sessions_28d", "Sessions", False), ("clicks_28d", "Search clicks", False)]


def _impact_with_deltas(items: list[dict], current: dict) -> list[dict]:
    out = []
    for it in items:
        base = it.get("baseline") or {}
        # A concluded change is measured to the day it was concluded: against
        # today its figures went on moving for ever under 'Concluded'.
        end = it.get("final") if it.get("status") == "concluded" and isinstance(it.get("final"), dict) else current
        deltas = []
        for key, label, _money_flag in _IMPACT_METRICS:
            b, c = base.get(key), end.get(key)
            if isinstance(b, (int, float)) and isinstance(c, (int, float)):
                pct = round((c - b) / b * 100) if b else None
                deltas.append({"key": key, "label": label, "from": b, "to": c, "pct": pct})
        out.append({**it, "deltas": deltas})
    return out


def _impact_learning_text(it: dict, current: dict) -> str:
    """The learning a concluded change leaves in Memory, in the app's own
    formats: '2 Sep 2026' and '£6,420', not an ISO date and a bare number."""
    base = it.get("baseline") or {}
    b, c = base.get("revenue_28d"), current.get("revenue_28d")
    raw = (it.get("started_at") or "")[:10]
    try:
        d = datetime.strptime(raw, "%Y-%m-%d")
        when = f"{d.day} {d:%b %Y}"
    except ValueError:
        when = raw
    if isinstance(b, (int, float)) and isinstance(c, (int, float)) and b:
        pct = round((c - b) / b * 100)
        direction = "up" if pct > 0 else "down" if pct < 0 else "flat"
        return (f"After '{it.get('text', '')}' (tracked from {when}), 28-day revenue was {direction} "
                f"{abs(pct)}%, from £{b:,.0f} to £{c:,.0f}.")
    return f"Tracked the change '{it.get('text', '')}' from {when}."


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as core.NAME and sibling.NAME, never a copied name.
import copilot as core  # noqa: E402
from gizmo import orderbook  # noqa: E402
