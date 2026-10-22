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
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone

from gizmo import stock_figures, stock_store
from gizmo import store as jsonstore

logger = logging.getLogger("shopify_mcp.copilot")

# One stock change at a time, read to written. Re-entrant: a rule that calls
# another rule's helper while holding it does not wait on itself.
_lock = threading.RLock()

DOCS = ("items", "periods", "alerts", "suppliers", "settings", "bridge", "orders")
ALERTS_CAP = 1000          # warnings kept in the live list; older ones are archived first
# The invoice number on a receipt's history line, as the stock app writes and
# reads it: compared whole, so INV-1 is never mistaken for INV-10.
_INVOICE = re.compile(r"·\s*inv\s+(.*?)(?:\s*·|$)")


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


# ---- snapshots and warnings ------------------------------------------------

def _add_alert(alerts: dict, alert: dict) -> None:
    alerts.setdefault("alerts", []).append({
        "id": alerts.get("next_id") or 1, "at": now_iso(), "kind": alert["kind"],
        "severity": alert["severity"], "message": alert["message"], "item_key": alert.get("item_key") or "",
        "dismissed": False, "dismissed_by": ""})
    alerts["next_id"] = (alerts.get("next_id") or 1) + 1


def _raise_warnings(alerts: dict, raised: list) -> None:
    """A warning about a line is raised once: again only when it becomes a
    different warning, or after the line recovered (no warning in a pass)
    and fell back. A swing in the whole stock's value is raised as before."""
    standing = alerts.setdefault("standing", {})
    warned = set()
    for alert in raised:
        key = alert.get("item_key") or ""
        if key:
            warned.add(key)
            if standing.get(key) == alert["kind"]:
                continue
            standing[key] = alert["kind"]
        _add_alert(alerts, alert)
    for key in [k for k in standing if k not in warned]:
        del standing[key]
    rows = sorted(alerts.get("alerts") or [], key=lambda a: a["id"])
    if len(rows) > ALERTS_CAP:
        over = rows[:len(rows) - ALERTS_CAP]
        stock_store.append_alerts_archive(over)       # kept first, then trimmed
        rows = rows[len(over):]
    alerts["alerts"] = rows


def take_snapshot(st: dict, reason: str, who: dict, note: str) -> dict:
    """The snapshot of the lines as `st` holds them, its warnings raised into
    `st["alerts"]`. Pass it to commit() with "alerts" among the changes."""
    items = items_in_order(st["items"])
    snap = {"taken_at": now_iso(), "reason": reason, "by_user": who["user"], "note": str(note)[:300],
            "totals": stock_figures.totals_for_snapshot(items),
            "items": [{"item_key": i["key"], "category": i["category"], "written_off": i["written_off"],
                       "current": i["current"], "used": i["used"], "current_value": stock_figures.current_value(i)}
                      for i in items]}
    prev = stock_store.last_snapshot()
    prev_totals = (prev.get("totals") if isinstance(prev.get("totals"), dict) else {}) if prev else None
    meta = (st.get("settings") or {}).get("meta") or {}
    _raise_warnings(st["alerts"], stock_figures.detect_anomalies(items, meta, prev_totals))
    return snap


# ---- the history, indexed ----------------------------------------------------

def detail_invoice(detail: str) -> str:
    m = _INVOICE.search(detail or "")
    return m.group(1).strip() if m else ""


class HistoryIndex:
    """Every history line in file order, and where to find them: by the line
    of stock they name, by invoice number (any case) and by action."""

    def __init__(self, path: str, ino: int):
        self.path, self.ino, self.offset, self.full_reads = path, ino, 0, 0
        self.rows, self.by_key, self.by_invoice, self.by_action = [], {}, {}, {}

    def _take(self, row: dict) -> None:
        n = len(self.rows)
        self.rows.append(row)
        if row.get("item_key"):
            self.by_key.setdefault(row["item_key"], []).append(n)
        inv = detail_invoice(row.get("detail") or "").casefold()
        if inv:
            self.by_invoice.setdefault(inv, []).append(n)
        self.by_action.setdefault(row.get("action") or "", []).append(n)

    def read_on(self) -> None:
        """Read the lines added since the last read, up to the last complete one."""
        with open(self.path, "rb") as fh:
            fh.seek(self.offset)
            chunk = fh.read()
        end = chunk.rfind(b"\n") + 1                 # a torn last line waits until it is closed off
        for raw in chunk[:end].split(b"\n"):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except ValueError:
                continue                               # stock_store.read_history says so once
            if isinstance(row, dict):
                self._take(row)
        self.offset += end


_mem: dict = {}              # "history": the HistoryIndex, while its file is the one it read


def history_index() -> HistoryIndex:
    with _lock:
        path = stock_store.STOCK_HISTORY_PATH
        try:
            st = os.stat(path)
        except FileNotFoundError:
            idx = HistoryIndex(path, 0)
            _mem["history"] = idx
            return idx
        idx = _mem.get("history")
        if idx is None or idx.path != path or idx.ino != st.st_ino or st.st_size < idx.offset:
            idx = HistoryIndex(path, st.st_ino)       # a new or replaced file: read it whole
            idx.full_reads += 1
            _mem["history"] = idx
        if st.st_size > idx.offset:
            idx.read_on()
        return idx


def _let_go_of_stock_in_memory(paths):
    """A restore or a redact replaced the history under us: read it afresh."""
    idx = _mem.get("history")
    if idx is not None and (paths is None or idx.path in paths):
        _mem.pop("history", None)
        return [idx.path]
    return []


jsonstore.holds_in_memory(_let_go_of_stock_in_memory)


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as sibling.NAME, never a copied name.
from gizmo import team  # noqa: E402
