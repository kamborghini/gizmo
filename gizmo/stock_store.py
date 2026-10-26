"""The stock sheet's stores: every record the stock app keeps in its database,
held as files at the top of the data folder, where Reactor's backup takes them.

Whole stores (items, periods, alerts, suppliers, settings, the order link's
tables, people) go through the one writer. The history and the snapshots
only ever grow, so they are append-only lines, like the dispatch archive:
a line is added, flushed and synced, and never rewritten. A crash in the
middle of an append leaves at most one torn line, which a read skips and the
next append closes off; nothing pauses the store.

Snapshots are split by kind because the stock app deletes the ones taken on
a change after 30 days and keeps the nightly ones: the nightly ones share one
file, the others go in a file per UTC day, so ageing one out removes a file
rather than rewriting the history.

Ids are the stock app's own, kept exactly; a new record is numbered after
the highest. This module holds no figures and names no route.
"""
import glob
import json
import logging
import os
import shutil
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from gizmo import store as jsonstore

logger = logging.getLogger("shopify_mcp.copilot")

STOCK_ITEMS_PATH = os.environ.get("STOCK_ITEMS_PATH", "/data/stock_items.json")  # the stock sheet's lines, by id
STOCK_HISTORY_PATH = os.environ.get("STOCK_HISTORY_PATH", "/data/stock_history.jsonl")  # every change to the stock sheet, append-only
STOCK_SNAPSHOTS_SCHEDULED_PATH = os.environ.get("STOCK_SNAPSHOTS_SCHEDULED_PATH", "/data/stock_snap_scheduled.jsonl")  # the nightly stock snapshots, append-only
STOCK_SNAPSHOTS_CHANGES_PREFIX = os.environ.get("STOCK_SNAPSHOTS_CHANGES_PREFIX", "/data/stock_snap_changes_")  # the other stock snapshots, a file per UTC day (prefix + YYYY-MM-DD.jsonl)
STOCK_PERIODS_PATH = os.environ.get("STOCK_PERIODS_PATH", "/data/stock_periods.json")  # the stock sheet's quarters, open and closed
STOCK_ALERTS_PATH = os.environ.get("STOCK_ALERTS_PATH", "/data/stock_alerts.json")  # the stock sheet's warnings
STOCK_SUPPLIERS_PATH = os.environ.get("STOCK_SUPPLIERS_PATH", "/data/stock_suppliers.json")  # supplier contacts and order templates (owner-only)
STOCK_SETTINGS_PATH = os.environ.get("STOCK_SETTINGS_PATH", "/data/stock_settings.json")  # the stock sheet's own settings, as the stock app kept them
STOCK_BRIDGE_PATH = os.environ.get("STOCK_BRIDGE_PATH", "/data/stock_bridge.json")  # glass booked from made orders, day sheets, parked lines, aliases
STOCK_BACKUP_PREFIX = os.environ.get("STOCK_BACKUP_PREFIX", "/data/stock_backup_")  # stock sheet backups, a file each (prefix + YYYYmmdd-HHMMSS-id.json)
STOCK_PEOPLE_PATH = os.environ.get("STOCK_PEOPLE_PATH", "/data/stock_people.json")  # the stock app's usernames and the Reactor accounts they became
STOCK_ORDERS_PATH = os.environ.get("STOCK_ORDERS_PATH", "/data/stock_orders.json")  # orders placed with suppliers and what has been received against them
STOCK_JOURNAL_PATH = os.environ.get("STOCK_JOURNAL_PATH", "/data/stock_journal.json")  # a stock change in flight, finished by the next read after a crash
STOCK_ALERTS_ARCHIVE_PATH = os.environ.get("STOCK_ALERTS_ARCHIVE_PATH", "/data/stock_alerts_archive.jsonl")  # stock warnings trimmed from the live list, append-only


def _paths() -> tuple:
    return (STOCK_ITEMS_PATH, STOCK_HISTORY_PATH, STOCK_SNAPSHOTS_SCHEDULED_PATH, STOCK_SNAPSHOTS_CHANGES_PREFIX,
            STOCK_PERIODS_PATH, STOCK_ALERTS_PATH, STOCK_SUPPLIERS_PATH, STOCK_SETTINGS_PATH, STOCK_BRIDGE_PATH,
            STOCK_BACKUP_PREFIX, STOCK_PEOPLE_PATH, STOCK_ORDERS_PATH, STOCK_JOURNAL_PATH, STOCK_ALERTS_ARCHIVE_PATH)


def _set_paths(paths: tuple) -> None:
    global STOCK_ITEMS_PATH, STOCK_HISTORY_PATH, STOCK_SNAPSHOTS_SCHEDULED_PATH, STOCK_SNAPSHOTS_CHANGES_PREFIX
    global STOCK_PERIODS_PATH, STOCK_ALERTS_PATH, STOCK_SUPPLIERS_PATH, STOCK_SETTINGS_PATH, STOCK_BRIDGE_PATH
    global STOCK_BACKUP_PREFIX, STOCK_PEOPLE_PATH, STOCK_ORDERS_PATH, STOCK_JOURNAL_PATH, STOCK_ALERTS_ARCHIVE_PATH
    (STOCK_ITEMS_PATH, STOCK_HISTORY_PATH, STOCK_SNAPSHOTS_SCHEDULED_PATH, STOCK_SNAPSHOTS_CHANGES_PREFIX,
     STOCK_PERIODS_PATH, STOCK_ALERTS_PATH, STOCK_SUPPLIERS_PATH, STOCK_SETTINGS_PATH, STOCK_BRIDGE_PATH,
     STOCK_BACKUP_PREFIX, STOCK_PEOPLE_PATH, STOCK_ORDERS_PATH, STOCK_JOURNAL_PATH, STOCK_ALERTS_ARCHIVE_PATH) = paths


@contextmanager
def rooted(folder: str):
    """Every stock store in `folder` for the length of the block (the
    converter writes and proves a move there), then back where they were."""
    saved = _paths()
    _set_paths(tuple(os.path.join(folder, os.path.basename(p)) for p in saved))
    try:
        yield
    finally:
        _set_paths(saved)


# ---- moving in ------------------------------------------------------------

def _prefixes() -> tuple:
    return (STOCK_SNAPSHOTS_CHANGES_PREFIX, STOCK_BACKUP_PREFIX)


def _live_files() -> list:
    """Every stock store file where the stock sheet reads it."""
    found = []
    for p in _paths():
        if p in _prefixes():
            found += sorted(glob.glob(p + "*"))
        elif os.path.exists(p):
            found.append(p)
    return found


def install_from(folder: str) -> dict:
    """Put a converted, proven set of stores (the converter wrote them into
    `folder`) where the stock sheet reads them. Whatever stock store is
    already there is set aside inside `folder`, never deleted; each store is
    copied in whole and replaces its file in one step, keeping its
    permissions (the suppliers and the backups stay owner-only). The moment
    of going live (`live_since`) is not written here: the move sets it last."""
    live = _live_files()
    aside = None
    if live:
        aside = os.path.join(folder, "set-aside-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
        os.makedirs(aside, exist_ok=True)
        for p in live:
            shutil.move(p, os.path.join(aside, os.path.basename(p)))
            jsonstore._forget_store(p)
    installed = []
    for p in _paths():
        if p == STOCK_JOURNAL_PATH:
            continue
        name = os.path.basename(p)
        if p in _prefixes():
            pairs = [(src, os.path.join(os.path.dirname(p), os.path.basename(src)))
                     for src in sorted(glob.glob(os.path.join(folder, name + "*")))]
        else:
            src = os.path.join(folder, name)
            pairs = [(src, p)] if os.path.exists(src) else []
        for src, dst in pairs:
            tmp = dst + ".installing"
            shutil.copy2(src, tmp)
            os.replace(tmp, dst)
            jsonstore._forget_store(dst)
            installed.append(os.path.basename(dst))
    return {"installed": installed, "set_aside": aside}


# One append at a time: the highest id is read and the new lines written
# under it, so two appends can never number a line the same.
_append_lock = threading.Lock()
_warned_torn: set = set()     # files whose unreadable lines were logged this process


# ---- whole stores ---------------------------------------------------------

def _load(path: str, default: dict) -> dict:
    doc = jsonstore._load_json_store(path, None, None)
    return doc if isinstance(doc, dict) else json.loads(json.dumps(default))


def load_items() -> dict:
    return _load(STOCK_ITEMS_PATH, {"items": {}, "next_id": 1})


def write_items(doc: dict) -> None:
    jsonstore._write_json_store(STOCK_ITEMS_PATH, None, doc)


def load_periods() -> dict:
    return _load(STOCK_PERIODS_PATH, {"periods": [], "next_id": 1})


def write_periods(doc: dict) -> None:
    jsonstore._write_json_store(STOCK_PERIODS_PATH, None, doc)


def load_alerts() -> dict:
    return _load(STOCK_ALERTS_PATH, {"alerts": [], "next_id": 1})


def write_alerts(doc: dict) -> None:
    jsonstore._write_json_store(STOCK_ALERTS_PATH, None, doc)


def load_suppliers() -> dict:
    return _load(STOCK_SUPPLIERS_PATH, {"suppliers": [], "next_id": 1})


def write_suppliers(doc: dict) -> None:
    jsonstore._write_json_store(STOCK_SUPPLIERS_PATH, None, doc, private=True)


def load_settings() -> dict:
    return _load(STOCK_SETTINGS_PATH, {"meta": {}})


def write_settings(doc: dict) -> None:
    jsonstore._write_json_store(STOCK_SETTINGS_PATH, None, doc)


def load_bridge() -> dict:
    return _load(STOCK_BRIDGE_PATH, {"bookings": [], "sheets": [], "parked": [], "aliases": [],
                                     "next_ids": {"bookings": 1, "sheets": 1, "parked": 1, "aliases": 1}})


def write_bridge(doc: dict) -> None:
    jsonstore._write_json_store(STOCK_BRIDGE_PATH, None, doc)


def load_people() -> dict:
    return _load(STOCK_PEOPLE_PATH, {"people": {}})


def write_people(doc: dict) -> None:
    jsonstore._write_json_store(STOCK_PEOPLE_PATH, None, doc)


def load_orders() -> dict:
    return _load(STOCK_ORDERS_PATH, {"orders": [], "next_id": 1})


def write_orders(doc: dict) -> None:
    jsonstore._write_json_store(STOCK_ORDERS_PATH, None, doc)


def load_journal():
    """The change in flight, or None when there is none."""
    doc = jsonstore._load_json_store(STOCK_JOURNAL_PATH, None, None)
    return doc if isinstance(doc, dict) else None


def write_journal(doc: dict) -> None:
    jsonstore._write_json_store(STOCK_JOURNAL_PATH, None, doc)


def clear_journal() -> None:
    try:
        os.remove(STOCK_JOURNAL_PATH)
    except FileNotFoundError:
        pass
    jsonstore._forget_store(STOCK_JOURNAL_PATH)


# ---- append-only lines ----------------------------------------------------

def _read_lines(path: str) -> list:
    """Every complete record in the file, in file order. A line that does not
    parse (the torn end of an interrupted append) is skipped and logged once."""
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return []
    out, bad = [], 0
    with fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                bad += 1
                continue
            if isinstance(row, dict):
                out.append(row)
            else:
                bad += 1
    if bad and path not in _warned_torn:
        _warned_torn.add(path)
        logger.warning("stock: %d unreadable line(s) in %s skipped; every complete line was read", bad, path)
    return out


def _last_row(path: str):
    """The file's last complete line: lines are only ever appended in id
    order, so it holds the highest id. Read backwards from the end a block at
    a time, so a long line (a snapshot of hundreds of lines) or a torn end
    costs a few blocks, never the whole file."""
    try:
        fh = open(path, "rb")
    except FileNotFoundError:
        return None
    with fh:
        pos = fh.seek(0, os.SEEK_END)
        head = b""                 # the start of a line whose beginning is further back
        while pos > 0:
            step = min(65536, pos)
            pos -= step
            fh.seek(pos)
            lines = (fh.read(step) + head).split(b"\n")
            head = lines.pop(0) if pos > 0 else b""
            for raw in reversed(lines):
                try:
                    row = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(row, dict) and isinstance(row.get("id"), int):
                    return row
    return None


def _last_id(path: str) -> int:
    return (_last_row(path) or {}).get("id", 0)


def _number(rows: list, last: int) -> list:
    """Each row with its id: a given id is kept (it must come after the
    highest), a missing one is the next. Checked in full before anything is
    written, so a refused batch writes nothing."""
    out = []
    for row in rows:
        rid = row.get("id")
        if rid is None:
            rid = last + 1
        elif not isinstance(rid, int) or isinstance(rid, bool) or rid <= last:
            raise ValueError(f"stock: id {rid!r} does not come after {last}")
        out.append(dict(row, id=rid))
        last = rid
    return out


def _append_stock_lines(path: str, rows: list) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    torn = False
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            if fh.tell():
                fh.seek(-1, os.SEEK_END)
                torn = fh.read(1) != b"\n"
    except FileNotFoundError:
        pass
    # Every row is made into text before the file is opened: a row that
    # cannot be (NaN is not JSON) refuses the batch with nothing written.
    payload = ("\n" if torn else "") + "".join(json.dumps(row, allow_nan=False) + "\n" for row in rows)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(payload)      # a torn line is closed off first, so the new rows stand on their own
        fh.flush()
        os.fsync(fh.fileno())


def append_history(rows: list) -> list:
    """Add history rows; returns their ids."""
    with _append_lock:
        numbered = _number(rows, _last_id(STOCK_HISTORY_PATH))
        if numbered:
            _append_stock_lines(STOCK_HISTORY_PATH, numbered)
        return [r["id"] for r in numbered]


def read_history() -> list:
    return _read_lines(STOCK_HISTORY_PATH)


def last_history_id() -> int:
    return _last_id(STOCK_HISTORY_PATH)


def _instant(iso: str) -> datetime:
    t = datetime.fromisoformat(iso)
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _snapshot_files() -> list:
    return [STOCK_SNAPSHOTS_SCHEDULED_PATH] + sorted(glob.glob(STOCK_SNAPSHOTS_CHANGES_PREFIX + "*.jsonl"))


def append_snapshot(snap: dict) -> None:
    """The nightly snapshot to its file, any other to the file for its UTC day."""
    with _append_lock:
        last = max((_last_id(p) for p in _snapshot_files()), default=0)
        (snap,) = _number([snap], last)
        if snap.get("reason") == "scheduled":
            path = STOCK_SNAPSHOTS_SCHEDULED_PATH
        else:
            path = STOCK_SNAPSHOTS_CHANGES_PREFIX + _instant(snap["taken_at"]).date().isoformat() + ".jsonl"
        _append_stock_lines(path, [snap])


def read_snapshots() -> list:
    out = []
    for path in _snapshot_files():
        out.extend(_read_lines(path))
    return sorted(out, key=lambda s: s.get("id", 0))


def last_snapshot_id() -> int:
    return max((_last_id(p) for p in _snapshot_files()), default=0)


def last_snapshot():
    """The latest snapshot by when it was taken, or None."""
    rows = [r for r in (_last_row(p) for p in _snapshot_files()) if r and r.get("taken_at")]
    return max(rows, key=lambda r: (_instant(r["taken_at"]), r["id"])) if rows else None


def prune_change_snapshots(before: str) -> int:
    """Remove the files of snapshots taken on a change before the UTC day
    `before` (YYYY-MM-DD), whole; the nightly ones are never removed."""
    gone = 0
    for path in glob.glob(STOCK_SNAPSHOTS_CHANGES_PREFIX + "*.jsonl"):
        day = path[len(STOCK_SNAPSHOTS_CHANGES_PREFIX):-len(".jsonl")]
        if day < before:
            os.remove(path)
            gone += 1
    return gone


def append_alerts_archive(rows: list) -> None:
    """Warnings trimmed from the live list, kept: appended before the trim."""
    with _append_lock:
        if rows:
            _append_stock_lines(STOCK_ALERTS_ARCHIVE_PATH, rows)


# ---- backups --------------------------------------------------------------

def write_backup(backup: dict) -> str:
    """One backup, one file; returns its path."""
    stamp = _instant(backup["at"]).strftime("%Y%m%d-%H%M%S")
    path = f"{STOCK_BACKUP_PREFIX}{stamp}-{backup['id']}.json"
    # Owner-only: a backup holds the supplier contacts, which are kept so.
    jsonstore._write_json_store(path, None, backup, private=True)
    return path


def delete_backup(backup_id: int) -> bool:
    gone = False
    for path in glob.glob(f"{STOCK_BACKUP_PREFIX}*-{int(backup_id)}.json"):
        os.remove(path)
        jsonstore._forget_store(path)
        gone = True
    return gone


def list_backups() -> list:
    found = (jsonstore._load_json_store(p, None, None) for p in glob.glob(STOCK_BACKUP_PREFIX + "*.json"))
    return sorted((b for b in found if isinstance(b, dict)), key=lambda b: b.get("id", 0))
