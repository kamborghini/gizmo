"""The stock sheet in the chat: four read-only tools that answer from the
store and never write. Each is gated to the stock tab (gizmo/chat.py
_TOOL_TABS), so an account without the stock sheet is refused it in Chat as
it is on the page, and each says the stock sheet has not moved in until it
has. TOOLS is what copilot.add_routes adds to the chat's registry.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from gizmo import stock, stock_figures, stock_orders, stock_quarters

logger = logging.getLogger("shopify_mcp.copilot")

NOT_YET = "The stock sheet has not moved into Reactor yet."
LEVELS_MAX = 60
HISTORY_MAX = 50
MOVEMENTS_MAX = 100
RECEIVED = ("receive", "receive_undo")
USED = ("use", "use_undo", "sheet", "sheet_undo")


class StockLevelsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    query: Optional[str] = Field(default=None, max_length=120,
                                 description="Words to match: a colour, size, category, supplier or barcode. Empty lists every line.")


class StockItemInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    item: str = Field(min_length=1, max_length=120,
                      description="The stock line: its id from stock_levels, or words that match only it")


class StockMovementsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: int = Field(default=30, ge=1, le=366, description="How many days back to sum")


class StockReorderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _read(work) -> str:
    if not stock.is_live():
        return NOT_YET
    try:
        return json.dumps(work(), ensure_ascii=False, default=str)
    except Exception:
        logger.exception("stock: a chat read failed")
        return "The stock sheet could not be read just now."


def _name(it: dict) -> str:
    return f"{it['category']} / {stock_figures.item_name(it)}" + (f" ({it['notes']})" if it.get("notes") else "")


def _matching(query) -> list:
    words = str(query or "").casefold().split()
    out = []
    for it in stock.items_in_order(stock.state()["items"]):
        hay = " ".join(str(it.get(k) or "") for k in
                       ("key", "category", "sub_category", "size", "notes", "supplier", "barcode")).casefold()
        if all(w in hay for w in words):
            out.append(it)
    return out


def _line(it: dict) -> dict:
    # Days of cover at the quarter's rate of use, as the stock sheet's own
    # low stock warning works it out.
    rate = it["used"] / stock_figures.QUARTER_DAYS if it["used"] > 0 else 0
    return {"id": it["id"], "name": _name(it), "supplier": it["supplier"] or "", "current": it["current"],
            "on_order": it["on_order"] or 0, "reorder_point": it["reorder_point"],
            "value_gbp": stock_figures.current_value(it), "used_this_quarter": it["used"],
            "cover_days": round(it["current"] / rate) if rate else None, "written_off": it["written_off"]}


async def stock_levels(params: StockLevelsInput) -> str:
    """The glass stock sheet (gobos, rings and the parts counted by hand,
    not Shopify products): the lines matching some words, each with how many
    are on the shelf, on order, its value in pounds and its days of cover at
    this quarter's rate of use. Read-only."""
    def work():
        lines = _matching(params.query)
        return {"matched": len(lines), "lines": [_line(it) for it in lines[:LEVELS_MAX]]}
    return _read(work)


async def stock_item_history(params: StockItemInput) -> str:
    """One stock sheet line's own history, newest first (at most 50): every
    delivery, use on an order, count and edit, with who made it. Read-only."""
    def work():
        items = stock.state()["items"].get("items") or {}
        it = items.get(params.item) if params.item.isdigit() else None
        if it is None:
            found = _matching(params.item)
            if not found:
                return "No stock line matches that. Find it with stock_levels first."
            if len(found) > 1:
                return {"answer": "Several lines match: ask again with one of these ids.",
                        "lines": [{"id": i["id"], "name": _name(i)} for i in found[:LEVELS_MAX]]}
            it = found[0]
        rows = stock_quarters.history(item_id=it["id"], limit=HISTORY_MAX)["rows"]
        return {"line": _line(it), "rows": [{k: r.get(k) for k in ("at", "who", "action", "field", "old_value",
                                                                     "new_value", "detail")} for r in rows]}
    return _read(work)


async def stock_movements(params: StockMovementsInput) -> str:
    """What moved on the stock sheet over the last N days, summed per line:
    units received from suppliers, used (on orders, on the day's sheet and
    counted down in the workshop), and corrected by edits and counts that
    went up, with the net change. Read-only."""
    def work():
        since = datetime.now(timezone.utc) - timedelta(days=params.days)
        st = stock.state()
        items = st["items"].get("items") or {}
        find = stock.line_finder(st["items"])
        per = {}
        for row in stock.history_index().rows:
            # A count that went down is written twice: the shelf, as a
            # correction, and the drop as usage ("counted down N, recorded as
            # usage"). The second moves the drop from corrected to used.
            counted_down = row.get("field") == "used" and str(row.get("detail") or "").startswith("counted down")
            if row.get("field") != "current" and not counted_down:
                continue
            at = stock._instant(row.get("at"))
            if at is None or at < since:
                continue
            try:
                delta = int(row.get("new_value")) - int(row.get("old_value"))
            except (TypeError, ValueError):
                continue
            line = find(row)
            if line is None:
                continue
            m = per.setdefault(line, {"received": 0, "used": 0, "corrected": 0})
            if counted_down:
                m["used"] += delta
                m["corrected"] += delta
            elif row.get("action") in RECEIVED:
                m["received"] += delta
            elif row.get("action") in USED:
                m["used"] -= delta
            else:
                m["corrected"] += delta
        lines = [{"id": line, "name": _name(items[str(line)]) if str(line) in items else "a line since deleted",
                  **m, "net": m["received"] - m["used"] + m["corrected"]} for line, m in per.items()]
        lines.sort(key=lambda x: (-abs(x["net"]), -x["used"], x["name"]))
        return {"days": params.days, "since": since.date().isoformat(), "lines": lines[:MOVEMENTS_MAX],
                "lines_moved": len(lines)}
    return _read(work)


async def stock_reorder(params: StockReorderInput) -> str:
    """The stock sheet's reorder list: lines at or below their reorder point
    (counting what is already on order), grouped by supplier with a suggested
    quantity and its value in pounds. Read-only."""
    return _read(stock_orders.reorder)


TOOLS = {"stock_levels": (stock_levels, StockLevelsInput),
         "stock_item_history": (stock_item_history, StockItemInput),
         "stock_movements": (stock_movements, StockMovementsInput),
         "stock_reorder": (stock_reorder, StockReorderInput)}
