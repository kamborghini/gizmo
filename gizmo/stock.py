"""The stock sheet's core: the one lock, the journal that keeps a change and
its history line together, who did it, and the state every rule reads.

Every stock change is worked out in memory under the lock from `state()`,
then handed to `commit()`, which writes its whole outcome (the history lines
with their numbers, the snapshot, every store document it touched) to the
journal first, then appends the lines, then writes the documents, then
removes the journal. A crash anywhere leaves the journal, and the next read
or write finishes it: a line already appended is never appended again, and
documents are written whole, so finishing twice changes nothing. No line
describes a change that did not happen, and no change lands without its line.

Until the stock sheet has moved in (`live_since` in the settings, set by
the import at the switch), nothing is written: the converted stores must
arrive into empty ones.

The rules live beside this: stock_sheet (the list, counts, import and
export), stock_orders (orders, suppliers, receiving), stock_quarters
(quarters, settings, warnings, history), stock_backups (backups and the
nightly job). Stores only through stock_store; figures only through
stock_figures.
"""
import logging
import threading
from datetime import datetime, timezone

from gizmo import stock_store

logger = logging.getLogger("shopify_mcp.copilot")

# One stock change at a time, read to written. Re-entrant: a rule that calls
# another rule's helper while holding it does not wait on itself.
_lock = threading.RLock()

DOCS = ("items", "periods", "alerts", "suppliers", "settings", "bridge", "orders")


class Refused(Exception):
    """A stock request that cannot be done, with the words to say why."""

    def __init__(self, status: int, words: str):
        super().__init__(words)
        self.status = status
        self.words = words


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_live() -> bool:
    return bool(stock_store.load_settings().get("live_since"))


def _load(name: str) -> dict:
    return {"items": lambda: stock_store.load_items(), "periods": lambda: stock_store.load_periods(),
            "alerts": lambda: stock_store.load_alerts(), "suppliers": lambda: stock_store.load_suppliers(),
            "settings": lambda: stock_store.load_settings(), "bridge": lambda: stock_store.load_bridge(),
            "orders": lambda: stock_store.load_orders()}[name]()


def _write(name: str, doc: dict) -> None:
    {"items": lambda: stock_store.write_items(doc), "periods": lambda: stock_store.write_periods(doc),
     "alerts": lambda: stock_store.write_alerts(doc), "suppliers": lambda: stock_store.write_suppliers(doc),
     "settings": lambda: stock_store.write_settings(doc), "bridge": lambda: stock_store.write_bridge(doc),
     "orders": lambda: stock_store.write_orders(doc)}[name]()


def _finish(journal: dict) -> None:
    """Make the journal's outcome true. Safe to run more than once."""
    rows = [r for r in journal.get("history") or [] if r["id"] > stock_store.last_history_id()]
    if rows:
        stock_store.append_history(rows)
    snap = journal.get("snapshot")
    if snap and snap["id"] > stock_store.last_snapshot_id():
        stock_store.append_snapshot(snap)
    for name, doc in (journal.get("docs") or {}).items():
        _write(name, doc)


def recover() -> bool:
    """Finish a change a crash left in the journal. True when there was one."""
    with _lock:
        journal = stock_store.load_journal()
        if not journal:
            return False
        logger.warning("stock: finishing a change left part-written (%d history line(s))",
                       len(journal.get("history") or []))
        _finish(journal)
        stock_store.clear_journal()
        return True


def state() -> dict:
    """Every stock document, after any half-made change is finished."""
    with _lock:
        recover()
        return {name: _load(name) for name in DOCS}


def items_in_order(items_doc: dict) -> list:
    """The lines in id order: the order the figures are proven in."""
    return sorted((items_doc.get("items") or {}).values(), key=lambda i: i["id"])


def actor(uid: str) -> dict:
    """Who a change is recorded under: the Reactor account and its name."""
    return {"user": team._team_name(uid) or "Someone", "person": str(uid) if uid else None}


def history_row(who: dict, action: str, *, item_key: str = "", field: str = "", old="", new="",
                detail: str = "") -> dict:
    """A history line in the stock app's own shape, with the person beside it."""
    return {"at": now_iso(), "user": who["user"], "action": action, "item_key": item_key, "field": field,
            "old_value": str(old)[:300], "new_value": str(new)[:300], "detail": str(detail)[:500],
            "person": who["person"]}


def commit(st: dict, *, changed: set, history=(), snapshot: dict = None) -> list:
    """Write a change worked out from `st`: its history lines, its snapshot
    and the documents named in `changed`, through the journal. Returns the
    history lines' numbers. The caller holds `_lock` from `state()` to here."""
    with _lock:
        if not (st.get("settings") or {}).get("live_since"):
            raise Refused(409, "Stock has not moved into Reactor yet.")
        if recover():
            # Another change was half made after `st` was read: `st` is stale.
            raise Refused(409, "The stock sheet changed just now. Try again.")
        last = stock_store.last_history_id()
        rows = []
        for row in history:
            last += 1
            rows.append(dict(row, id=last))
        snap = dict(snapshot, id=stock_store.last_snapshot_id() + 1) if snapshot else None
        journal = {"history": rows, "snapshot": snap, "docs": {name: st[name] for name in sorted(changed)}}
        stock_store.write_journal(journal)
        _finish(journal)
        stock_store.clear_journal()
        return [r["id"] for r in rows]


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as sibling.NAME, never a copied name.
from gizmo import team  # noqa: E402
