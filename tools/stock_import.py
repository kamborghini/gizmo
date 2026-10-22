#!/usr/bin/env python3
"""Convert the stock app's export into Reactor's stock stores, and prove it.

    python tools/stock_import.py --export FILE --people FILE --out DIR [--report FILE]

The export comes from tools/stock_move/export_from_stock_app.py (see the
README beside it). `--people` maps each username in the stock app's history
to the Reactor account it becomes: {"username": "account id"}. The stores are
written into DIR, never into the live data folder, and then proven against
the export:

- each table's count (taken in the stock app's database) equals the records
  written for it, and every row's every column equals its record:
  timestamps as instants, NULL as NULL, text holding JSON as what it holds;
- the history's checksum over the source's own columns, in id order;
- every line is found by its label code (CL and its id) and its barcode,
  and by nothing else, by the stock app's own matching rule;
- every figure the stock app gave for this data equals Reactor's, value for
  value, money exactly.

Exit 0 only when the proof is empty. The output holds real data, so DIR and
the report are refused anywhere inside a git working tree.
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from gizmo import stock_figures, stock_store  # noqa: E402

FORMAT = "stock-export-1"
NOBODY = {"system", "gizmo", "?"}          # history written by the app itself, not a person
# The stock app's current columns, as each store keeps them.
COLUMNS = {
    "items": ["id", "key", "category", "sub_category", "size", "notes", "written_off", "barcode", "supplier",
              "currency", "unit_cost", "unit_cost_gbp", "start", "received", "used", "current", "reorder_point",
              "reorder_qty", "on_order", "created_at", "updated_at"],
    "snapshots": ["id", "taken_at", "reason", "by_user", "note", "totals"],
    "snapshot_items": ["id", "item_key", "category", "written_off", "current", "used", "current_value"],
    "audit_log": ["id", "at", "user", "action", "item_key", "field", "old_value", "new_value", "detail"],
    "alerts": ["id", "at", "kind", "severity", "message", "item_key", "dismissed", "dismissed_by"],
    "backups": ["id", "at", "filename", "size_bytes", "item_count"],
    "periods": ["id", "label", "opened_at", "closed_at", "closing_value", "closing_units", "closing_skus",
                "closing_used_value", "note", "closing_data"],
    "gizmo_bookings": ["id", "order_id", "order_name", "at", "lines"],
    "gizmo_usage_sheets": ["id", "day", "at", "lines", "applied"],
    "gizmo_parked": ["id", "order_id", "order_name", "alias", "qty", "note", "at"],
    "gizmo_aliases": ["id", "alias", "item_id", "item_key", "at"],
    "supplier_contacts": ["id", "supplier", "email", "cc", "contact_name", "subject", "body", "lead_days",
                          "min_order", "updated_at"],
}
# Columns the stock app added after it first ran, with the value its own
# upgrade gives a row that predates them.
ADDED_LATER = {"items": {"reorder_point": 0, "reorder_qty": 0, "barcode": "", "on_order": 0},
               "supplier_contacts": {"lead_days": 0, "min_order": ""},
               "periods": {"closing_data": ""},
               "gizmo_aliases": {"item_id": None}}
TIMESTAMPS = {"items": {"created_at", "updated_at"}, "snapshots": {"taken_at"}, "audit_log": {"at"},
              "alerts": {"at"}, "backups": {"at"}, "periods": {"opened_at", "closed_at"},
              "gizmo_bookings": {"at"}, "gizmo_usage_sheets": {"at"}, "gizmo_parked": {"at"},
              "gizmo_aliases": {"at"}, "supplier_contacts": {"updated_at"}, "users": {"created_at", "last_login", "prev_login"}}
JSON_TEXT = {"snapshots": {"totals"}, "periods": {"closing_data"}, "gizmo_bookings": {"lines"},
             "gizmo_usage_sheets": {"lines", "applied"}}
BOOLEANS = {"items": {"written_off"}, "snapshot_items": {"written_off"}, "alerts": {"dismissed"}}
BRIDGE = {"bookings": "gizmo_bookings", "sheets": "gizmo_usage_sheets", "parked": "gizmo_parked",
          "aliases": "gizmo_aliases"}
FIGURES = ["compute_current", "reorder_suggestions", "suggest_reorder_points", "lead_by_supplier", "fx_rates",
           "fx_revaluation", "totals_for_snapshot", "trends", "forecast", "detect_anomalies", "compare"]
MOVER_KEYS = {"top_value_movers": "value_delta", "top_unit_movers": "cur_delta"}
_MISSING = object()


# ---- values ----------------------------------------------------------------

def _utc_iso(v):
    """A timestamp as ISO 8601 in UTC; one without a zone is UTC."""
    if not isinstance(v, str) or not v:
        return v
    try:
        t = datetime.fromisoformat(v)
    except ValueError:
        return v
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()


def _decode(v):
    """Text holding JSON as what it holds: empty is None, and text that does
    not parse is kept as it is, so nothing is lost."""
    if v is None or v == "":
        return None
    if not isinstance(v, str):
        return v
    try:
        return json.loads(v)
    except ValueError:
        return v


def _canon(table, column, v):
    if column in TIMESTAMPS.get(table, ()):
        return _utc_iso(v)
    if column in JSON_TEXT.get(table, ()):
        return _decode(v)
    if column in BOOLEANS.get(table, ()) and v is not None:
        return bool(v)
    return v


def _record(table, row, present):
    """A source row as its store keeps it."""
    out = {}
    for c in COLUMNS[table]:
        if c in present:
            out[c] = _canon(table, c, row.get(c))
        else:
            out[c] = ADDED_LATER.get(table, {}).get(c)
    return out


def _rows(export, table):
    t = export["tables"].get(table) or {}
    return sorted(t.get("rows") or [], key=lambda r: r.get("id", r.get("key")))


def _present(export, table):
    return set((export["tables"].get(table) or {}).get("columns") or [])


def inside_git_tree(path: str) -> bool:
    d = os.path.abspath(path) if os.path.isdir(path) else os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return True
        parent = os.path.dirname(d)
        if parent == d:
            return False
        d = parent


# ---- convert ---------------------------------------------------------------

def _next(records) -> int:
    return max((r["id"] for r in records), default=0) + 1


def convert(export: dict, people: dict, out_dir: str) -> None:
    """Write every stock store into out_dir. Refuses, writing nothing, when
    the history names a person with no account, a snapshot line belongs to no
    snapshot, or out_dir already holds stock stores."""
    if export.get("format") != FORMAT:
        raise ValueError(f"not a stock export ({export.get('format')!r}, expected {FORMAT!r})")
    history = _rows(export, "audit_log")
    unmapped = sorted({str(r.get("user")) for r in history} - set(people) - NOBODY)
    if unmapped:
        raise ValueError("the history names people with no Reactor account: " + ", ".join(unmapped))
    snapshots = _rows(export, "snapshots")
    ids = {s["id"] for s in snapshots}
    orphans = [r["id"] for r in _rows(export, "snapshot_items") if r.get("snapshot_id") not in ids]
    if orphans:
        raise ValueError(f"{len(orphans)} snapshot lines belong to no snapshot (ids {orphans[:10]})")
    os.makedirs(out_dir, exist_ok=True)
    if any(n.startswith("stock_") for n in os.listdir(out_dir)):
        raise ValueError(f"{out_dir} already holds stock stores: convert into an empty folder")

    def records(table):
        present = _present(export, table)
        return [_record(table, r, present) for r in _rows(export, table)]

    with stock_store.rooted(out_dir):
        items = records("items")
        stock_store.write_items({"items": {str(i["id"]): i for i in items}, "next_id": _next(items)})
        rows = records("audit_log")
        for r in rows:
            r["person"] = people.get(r["user"])
        stock_store.append_history(rows)
        lines = {}
        present = _present(export, "snapshot_items")
        for r in _rows(export, "snapshot_items"):
            lines.setdefault(r["snapshot_id"], []).append(_record("snapshot_items", r, present))
        for s in records("snapshots"):
            stock_store.append_snapshot(dict(s, items=lines.get(s["id"], [])))
        periods = records("periods")
        stock_store.write_periods({"periods": periods, "next_id": _next(periods)})
        alerts = records("alerts")
        stock_store.write_alerts({"alerts": alerts, "next_id": _next(alerts)})
        suppliers = records("supplier_contacts")
        stock_store.write_suppliers({"suppliers": suppliers, "next_id": _next(suppliers)})
        stock_store.write_settings({"meta": {r["key"]: r["value"] for r in _rows(export, "meta")}})
        bridge = {name: records(table) for name, table in BRIDGE.items()}
        bridge["next_ids"] = {name: _next(bridge[name]) for name in BRIDGE}
        stock_store.write_bridge(bridge)
        present = _present(export, "backups")
        for r in _rows(export, "backups"):
            stock_store.write_backup(dict(_record("backups", r, present), format="legacy-fernet", token=r["blob"]))
        stock_store.write_people({"people": dict(people)})


# ---- prove -----------------------------------------------------------------

def _match_rows(found, export, table, records, key="id", rename=None):
    """Counts, then every column of every row against its record."""
    src = export["tables"].get(table) or {"columns": [], "count": 0, "rows": []}
    rename = rename or {}
    if src["count"] != len(records):
        found.append(f"{table}: {src['count']} rows in the source, {len(records)} in Reactor")
    by_key = {r.get(key): r for r in records}
    source_keys = set()
    for row in src["rows"]:
        k = row.get(key)
        source_keys.add(k)
        rec = by_key.get(k)
        if rec is None:
            found.append(f"{table}: {key} {k} is missing")
            continue
        for c in src["columns"]:
            got = rec.get(rename.get(c, c), _MISSING)
            if got is _MISSING:
                found.append(f"{table}: {key} {k}: {c} is missing")
            elif _canon(table, c, row[c]) != _canon(table, c, got):
                found.append(f"{table}: {key} {k}: {c} is {got!r}, the source has {row[c]!r}")
    for k in by_key:
        if k not in source_keys:
            found.append(f"{table}: {key} {k} is not in the source")


def _checksum(table, columns, rows) -> str:
    h = hashlib.sha256()
    for r in sorted(rows, key=lambda r: r["id"]):
        h.update(json.dumps({c: _canon(table, c, r.get(c)) for c in columns}, sort_keys=True).encode() + b"\n")
    return h.hexdigest()


def _same(a, b) -> bool:
    """One figure's value against the other's: a boolean equals only a
    boolean, and two timestamps are equal when they are the same instant."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if a == b:
        return True
    return isinstance(a, str) and isinstance(b, str) and _utc_iso(a) == _utc_iso(b)


def _diff(found, path, want, got):
    if isinstance(want, dict) and isinstance(got, dict):
        for k in sorted(set(want) | set(got), key=str):
            if k not in got:
                found.append(f"figures: {path}.{k} is missing from Reactor's")
            elif k not in want:
                found.append(f"figures: {path}.{k} is in Reactor's but not the stock app's")
            else:
                _diff(found, f"{path}.{k}", want[k], got[k])
    elif isinstance(want, list) and isinstance(got, list):
        if len(want) != len(got):
            found.append(f"figures: {path} has {len(want)} entries in the stock app's, {len(got)} in Reactor's")
            return
        for n, (a, b) in enumerate(zip(want, got)):
            _diff(found, f"{path}[{n}]", a, b)
    elif not _same(want, got):
        found.append(f"figures: {path} is {got!r} in Reactor's, {want!r} in the stock app's")


def _movers(found, path, want, every, sort_key):
    """The stock app takes its movers out of a set, so lines tied on the
    sort key come out in no fixed order and a tie at the cut can keep either.
    Proven: the same number, the same run of sizes, and each one a line
    Reactor finds moved exactly so."""
    ours = sorted(every, key=lambda m: -abs(m[sort_key]))[:15]
    if len(want) != len(ours):
        found.append(f"figures: {path} has {len(want)} lines in the stock app's, {len(ours)} in Reactor's")
        return
    if [abs(m[sort_key]) for m in want] != [abs(m[sort_key]) for m in ours]:
        found.append(f"figures: {path} moves by different amounts in Reactor's")
        return
    pool = Counter(json.dumps(m, sort_keys=True) for m in every)
    for m in want:
        k = json.dumps(m, sort_keys=True)
        if pool[k] > 0:
            pool[k] -= 1
        else:
            found.append(f"figures: {path}: {m.get('item')!r} did not move so in Reactor's")


def _labels(found, items):
    """The stock app's scanner: a code, trimmed and upper-cased, finds the
    line whose barcode is that code or whose code is CL and its id."""
    def finds(code):
        u = str(code or "").strip().upper()
        return [i["id"] for i in items
                if u and (str(i.get("barcode") or "").strip().upper() == u or "CL" + str(i["id"]) == u)]
    for i in items:
        for code in sorted({"CL" + str(i["id"]), str(i.get("barcode") or "").strip()} - {""}):
            ids = finds(code)
            if ids != [i["id"]]:
                found.append(f"labels: {code} finds {', '.join(map(str, ids)) or 'nothing'}, "
                             f"not line {i['id']} alone")


def _figures(found, export, items, meta, snapshots, periods, suppliers):
    want = export.get("expected") or {}
    for name in FIGURES:
        if name not in want:
            found.append(f"figures: {name} is not in the export")
    leads = {s["supplier"]: (s.get("lead_days") or 0) for s in suppliers}
    ours = {
        "compute_current": lambda: stock_figures.compute_current(items),
        "reorder_suggestions": lambda: stock_figures.reorder_suggestions(items),
        "suggest_reorder_points": lambda: stock_figures.suggest_reorder_points(items, leads),
        "lead_by_supplier": lambda: leads,
        "fx_rates": lambda: stock_figures.fx_rates(items, meta),
        "fx_revaluation": lambda: stock_figures.fx_revaluation(items, meta),
        "totals_for_snapshot": lambda: stock_figures.totals_for_snapshot(items),
        "trends": lambda: stock_figures.trends(snapshots),
        "forecast": lambda: stock_figures.forecast(items, snapshots),
    }
    for name, work in ours.items():
        if name in want:
            _diff(found, name, want[name], work())
    if "detect_anomalies" in want:
        prev_id = want["detect_anomalies"].get("prev_snapshot_id")
        prev = next((s for s in snapshots if s["id"] == prev_id), None)
        if prev_id is not None and prev is None:
            found.append(f"figures: detect_anomalies: snapshot {prev_id} is missing")
        totals = prev.get("totals") if prev else None
        _diff(found, "detect_anomalies.alerts", want["detect_anomalies"].get("alerts"),
              stock_figures.detect_anomalies(items, meta, (totals if isinstance(totals, dict) else {}) if prev else None))
    by_id = {p["id"]: p for p in periods}

    def side(ref):
        if ref == "current":
            return stock_figures.side_live(items, periods)
        return stock_figures.side_period(by_id[ref]) if ref in by_id else None

    for n, entry in enumerate(want.get("compare") or []):
        left, right = side(entry["left"]), side(entry["right"])
        path = f"compare[{n}] ({entry['left']} against {entry['right']})"
        result, theirs = stock_figures.compare(left, right), dict(entry["result"])
        if left and right:
            every = stock_figures._movers(left["items"], right["items"])
            for key, sort_key in MOVER_KEYS.items():
                _movers(found, f"{path}.{key}", theirs.pop(key, []), every, sort_key)
                result.pop(key, None)
        _diff(found, path, theirs, result)


def prove(export: dict, out_dir: str) -> list:
    """Every difference between the export and the stores in out_dir, as a
    sentence naming the table, the record and the field. Empty: proven."""
    found = []
    with stock_store.rooted(out_dir):
        items_doc = stock_store.load_items()
        history = stock_store.read_history()
        snapshots = stock_store.read_snapshots()
        periods = stock_store.load_periods()
        alerts = stock_store.load_alerts()
        suppliers = stock_store.load_suppliers()
        settings = stock_store.load_settings()
        bridge = stock_store.load_bridge()
        backups = stock_store.list_backups()
        people = stock_store.load_people().get("people", {})
    items = sorted(items_doc.get("items", {}).values(), key=lambda i: i["id"])
    _match_rows(found, export, "items", items)
    _match_rows(found, export, "audit_log", history)
    src_history = (export["tables"].get("audit_log") or {})
    columns = src_history.get("columns") or []
    if _checksum("audit_log", columns, src_history.get("rows") or []) != _checksum("audit_log", columns, history):
        found.append("audit_log: the history's checksum differs from the source's")
    for row in history:
        if row.get("person") != people.get(row.get("user")):
            found.append(f"audit_log: id {row.get('id')}: person is {row.get('person')!r}, "
                         f"the people file says {people.get(row.get('user'))!r}")
    _match_rows(found, export, "snapshots", snapshots)
    _match_rows(found, export, "snapshot_items",
                [dict(line, snapshot_id=s["id"]) for s in snapshots for line in s.get("items") or []])
    _match_rows(found, export, "periods", periods.get("periods", []))
    _match_rows(found, export, "alerts", alerts.get("alerts", []))
    _match_rows(found, export, "supplier_contacts", suppliers.get("suppliers", []))
    _match_rows(found, export, "meta", [{"key": k, "value": v} for k, v in settings.get("meta", {}).items()], key="key")
    for name, table in BRIDGE.items():
        _match_rows(found, export, table, bridge.get(name, []))
    _match_rows(found, export, "backups", backups, rename={"blob": "token"})
    for name, doc, records in (("items", items_doc, items), ("periods", periods, periods.get("periods", [])),
                               ("alerts", alerts, alerts.get("alerts", [])),
                               ("suppliers", suppliers, suppliers.get("suppliers", []))):
        if doc.get("next_id", 0) <= max((r["id"] for r in records), default=0):
            found.append(f"{name}: the next id {doc.get('next_id')} would reuse one")
    for name in BRIDGE:
        if bridge.get("next_ids", {}).get(name, 0) <= max((r["id"] for r in bridge.get(name, [])), default=0):
            found.append(f"{BRIDGE[name]}: the next id would reuse one")
    _labels(found, items)
    _figures(found, export, items, settings.get("meta", {}), snapshots, periods.get("periods", []),
             suppliers.get("suppliers", []))
    return found


# ---- the command -----------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--export", required=True)
    ap.add_argument("--people", required=True, help='{"stock app username": "Reactor account id"}')
    ap.add_argument("--out", required=True, help="an empty folder outside every repository")
    ap.add_argument("--report", help="write the proof here as well (outside every repository)")
    args = ap.parse_args(argv)
    for p in (args.out, args.report):
        if p and inside_git_tree(p):
            print(f"refused: {p} is inside a git working tree; the stores hold real data", file=sys.stderr)
            return 2
    with open(args.export, encoding="utf-8") as fh:
        export = json.load(fh)
    with open(args.people, encoding="utf-8") as fh:
        people = json.load(fh)
    try:
        convert(export, people, args.out)
    except ValueError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    found = prove(export, args.out)
    text = "\n".join(found) if found else "proven: every record, field, label and figure matches the export"
    if args.report:
        fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text if not found else f"{len(found)} differences:\n{text}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
