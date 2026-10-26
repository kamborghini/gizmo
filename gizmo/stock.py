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
import math
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
    """A stock request that cannot be done, with the words to say why and
    anything the page needs to put it right (the line as it now is)."""

    def __init__(self, status: int, words: str, extra: dict = None):
        super().__init__(words)
        self.status = status
        self.words = words
        self.extra = extra or {}


# ---- the fields of a line, and the checks on them (the stock app's own) -------

INT_MAX = 2_147_483_647
COST_MAX = 1e9
INT_FIELDS = {"start", "received", "used", "current", "reorder_point", "reorder_qty"}
FLOAT_FIELDS = {"unit_cost", "unit_cost_gbp"}
TEXT_FIELDS = {"category": 80, "sub_category": 120, "size": 60, "notes": 100, "supplier": 120,
               "currency": 8, "barcode": 64}
BOOL_FIELDS = {"written_off"}
EDITABLE = INT_FIELDS | FLOAT_FIELDS | set(TEXT_FIELDS) | BOOL_FIELDS
IDENTITY = ("category", "sub_category", "size", "notes")
FIELD_WORDS = {"start": "Start", "received": "Received", "used": "Used", "current": "Current",
               "reorder_point": "Reorder level", "reorder_qty": "Order quantity", "unit_cost": "Unit cost",
               "unit_cost_gbp": "Unit cost in pounds", "category": "Category", "sub_category": "Colour or type",
               "size": "Size", "notes": "Notes", "supplier": "Supplier", "currency": "Currency",
               "barcode": "Barcode", "written_off": "Written off"}
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value, cap: int = 120) -> str:
    """Control characters out, trimmed, capped to the column's width."""
    return _CONTROL.sub("", str("" if value is None else value)).strip()[:cap]


def to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on", "y", "t")


def coerce(field: str, value):
    """A field's value as it is stored, or ValueError saying what is wrong.
    An empty box is 0 (or no cost); anything that is not a plain number is
    refused rather than read as 0, which once zeroed real stock."""
    words = FIELD_WORDS.get(field, field)
    if field in INT_FIELDS or field in FLOAT_FIELDS:
        if value == "":
            return 0 if field in INT_FIELDS else None
        if value is None or isinstance(value, bool):
            raise ValueError(f"{words} must be a number.")
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{words} must be a number.") from None
        if not math.isfinite(v):
            raise ValueError(f"{words} must be a number.")
        if v < 0:
            raise ValueError(f"{words} cannot be below 0.")
        if field in INT_FIELDS:
            n = int(round(v))
            if n > INT_MAX:
                raise ValueError(f"{words} is too large.")
            return n
        if abs(v) > COST_MAX:
            raise ValueError(f"{words} is too large.")
        return round(v, 4)
    if field in BOOL_FIELDS:
        return to_bool(value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{words} is not valid.")
    return clean_text(value, TEXT_FIELDS.get(field, 120))


def item_key(category: str, sub_category: str, size: str, notes: str) -> str:
    """The line's name in the history: category|colour|size|notes."""
    return "|".join((part or "").strip() for part in (category, sub_category, size, notes))


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
    for snap in journal.get("snapshots") or []:
        if snap["id"] > stock_store.last_snapshot_id():
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


def forget_memory() -> None:
    """Forget what memory holds of the stock stores (the history's and the
    snapshots' indexes, each store's cached copy), so the next read reads
    the files: the move puts new ones in place under a running server."""
    with _lock:
        _mem.clear()
        for path in stock_store._paths() + tuple(stock_store._live_files()):
            jsonstore._forget_store(path)


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
                detail: str = "", item_id: int = None) -> dict:
    """A history line in the stock app's own shape, with the person beside it
    and, for a line of stock, that line's id: its name can change, its id
    cannot, so the invoice check, undoing a delivery and a line's own history
    find it by id."""
    row = {"at": now_iso(), "user": who["user"], "action": action, "item_key": item_key, "field": field,
           "old_value": str(old)[:300], "new_value": str(new)[:300], "detail": str(detail)[:500],
           "person": who["person"]}
    if item_id is not None:
        row["item_id"] = item_id
    return row


def _instant(iso):
    """A stored time as a moment; one written without a zone is UTC."""
    try:
        t = datetime.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def line_finder(items_doc: dict):
    """A function from a history line to the id of the stock line it is
    about, or None. A line written here carries its id. An older one names
    the line as it was then: each name is read against the time it was the
    line's own, through the renames recorded here, so a name reused by a
    new line never takes an old line's history, and a renamed line keeps
    its own."""
    renames = {}
    for r in history_index().rows:
        if r.get("field") == "key" and r.get("item_id") is not None:
            renames.setdefault(r["item_id"], []).append((_instant(r.get("at")), r.get("old_value"), r.get("new_value")))
    windows = {}            # name -> [(from, until, line id)]; None is open-ended
    for it in (items_doc.get("items") or {}).values():
        start = None
        for at, old, _new in sorted(renames.get(it["id"], []), key=lambda s: (s[0] is not None, s[0])):
            windows.setdefault(old, []).append((start, at, it["id"]))
            start = at
        windows.setdefault(it["key"], []).append((start, None, it["id"]))

    def find(row: dict):
        if row.get("item_id") is not None:
            return row["item_id"]
        key = row.get("item_key")
        if not key:
            return None
        at = _instant(row.get("at"))
        for start, until, line in windows.get(key, []):
            if (start is None or (at is not None and at >= start)) and (until is None or (at is not None and at < until)):
                return line
        return None
    return find


def commit(st: dict, *, changed: set, history=(), snapshot: dict = None, snapshots=()) -> list:
    """Write a change worked out from `st`: its history lines, its snapshot
    (or snapshots, in order: a quarter's close takes two) and the documents
    named in `changed`, through the journal. Returns the history lines'
    numbers. The caller holds `_lock` from `state()` to here."""
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
        last_snap = stock_store.last_snapshot_id()
        snaps = [dict(s, id=last_snap + n) for n, s in enumerate(([snapshot] if snapshot else []) + list(snapshots), 1)]
        journal = {"history": rows, "snapshots": snaps, "docs": {name: st[name] for name in sorted(changed)}}
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


def take_snapshot(st: dict, reason: str, who: dict, note: str, prev: dict = None) -> dict:
    """The snapshot of the lines as `st` holds them, its warnings raised into
    `st["alerts"]`. Pass it to commit() with "alerts" among the changes. The
    value is compared with `prev` when given (a snapshot taken earlier in the
    same change), else with the latest one written."""
    items = items_in_order(st["items"])
    snap = {"taken_at": now_iso(), "reason": reason, "by_user": who["user"], "note": str(note)[:300],
            "totals": stock_figures.totals_for_snapshot(items),
            "items": [{"item_key": i["key"], "category": i["category"], "written_off": i["written_off"],
                       "current": i["current"], "used": i["used"], "current_value": stock_figures.current_value(i)}
                      for i in items]}
    prev = prev if prev is not None else stock_store.last_snapshot()
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


_mem: dict = {}              # "history": the HistoryIndex; "snapshots": the SnapshotSummary


def _complete_lines(path: str, offset: int) -> tuple:
    """The records on the complete lines after `offset`, and where they end."""
    with open(path, "rb") as fh:
        fh.seek(offset)
        chunk = fh.read()
    end = chunk.rfind(b"\n") + 1
    rows = []
    for raw in chunk[:end].split(b"\n"):
        if raw.strip():
            try:
                row = json.loads(raw)
            except ValueError:
                continue                               # stock_store.read_snapshots says so once
            if isinstance(row, dict):
                rows.append(row)
    return rows, offset + end


class SnapshotSummary:
    """What the figures over time read of every snapshot, and no more: each
    snapshot's time, reason and totals in time order, and for each line its
    first and last count (stock_figures.note_point). A year of snapshots of
    every line is tens of megabytes; this is a few hundred kilobytes."""

    def __init__(self):
        self.heads, self.series, self.files, self.full_reads = [], {}, {}, 0
        self._last = None

    def take(self, snap: dict) -> bool:
        """Add a snapshot taken no earlier than the last; False when it was."""
        at = _instant(snap.get("taken_at"))
        if at is None or (self._last is not None and at < self._last):
            return False
        self._last = at
        self.heads.append({k: snap.get(k) for k in ("id", "taken_at", "reason", "by_user", "note", "totals")})
        for si in snap.get("items") or []:
            stock_figures.note_point(self.series, si.get("item_key"), at, si.get("current"))
        return True

    def values(self) -> list:
        return [(h.get("totals") if isinstance(h.get("totals"), dict) else {}).get("active_value_gbp", 0)
                for h in self.heads]


def _read_snapshots_afresh(files: dict) -> SnapshotSummary:
    summary = SnapshotSummary()
    rows = []
    for path, ino in files.items():
        got, end = _complete_lines(path, 0)
        rows.extend(got)
        summary.files[path] = (ino, end)
    rows.sort(key=lambda s: s.get("id", 0))
    rows.sort(key=lambda s: _instant(s.get("taken_at")) or datetime.min.replace(tzinfo=timezone.utc))
    for row in rows:
        summary.take(row)
    summary.full_reads = (_mem.get("snapshot_reads") or 0) + 1
    _mem["snapshot_reads"] = summary.full_reads
    return summary


def snapshot_summary() -> SnapshotSummary:
    """The snapshots as the figures need them, read on from where the last
    read stopped; read afresh only when a file went or was replaced, or a
    snapshot arrived out of time order."""
    with _lock:
        files = {}
        for path in stock_store._snapshot_files():
            try:
                files[path] = os.stat(path).st_ino
            except FileNotFoundError:
                continue
        kept = _mem.get("snapshots")
        if (kept is None or set(kept.files) - set(files)
                or any(path in kept.files and kept.files[path][0] != ino for path, ino in files.items())
                or any(os.path.getsize(p) < kept.files[p][1] for p in kept.files if p in files)):
            kept = _read_snapshots_afresh(files)
        else:
            new = []
            for path, ino in files.items():
                got, end = _complete_lines(path, kept.files.get(path, (ino, 0))[1])
                new.extend(got)
                kept.files[path] = (ino, end)
            new.sort(key=lambda s: s.get("id", 0))
            new.sort(key=lambda s: _instant(s.get("taken_at")) or datetime.min.replace(tzinfo=timezone.utc))
            if not all(kept.take(row) for row in new):
                kept = _read_snapshots_afresh(files)
        _mem["snapshots"] = kept
        return kept


def snapshots() -> list:
    """Every snapshot's time, reason and totals, oldest first (no lines)."""
    return snapshot_summary().heads


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
    """A restore or a redact replaced files under us: read them afresh."""
    gone = []
    idx = _mem.get("history")
    if idx is not None and (paths is None or idx.path in paths):
        _mem.pop("history", None)
        gone.append(idx.path)
    kept = _mem.get("snapshots")
    if kept is not None:
        held = list(kept.files)
        if paths is None or any(p in paths for p in held):
            _mem.pop("snapshots", None)
            gone.extend(held)
    return gone


jsonstore.holds_in_memory(_let_go_of_stock_in_memory)


# Last, so this module is whole before copilot.py or a sibling runs: copilot.py
# takes names from these modules as it loads, and any of them may be imported
# first. Read as sibling.NAME, never a copied name.
from gizmo import team  # noqa: E402
