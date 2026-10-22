#!/usr/bin/env python3
"""Check the whole move on an invented database, end to end, with both apps' code.

    <stock app>/.venv/bin/python tools/stock_move/selfcheck.py \\
        --stock-app <stock app folder> --reactor-python <Reactor's python>

The suite cannot run the exporter (it needs the stock app's Python and
SQLAlchemy), and the suite's own test export has its figures worked out by
Reactor's port, so neither notices the port drifting from the stock app.
This does both: it builds a database with the stock app's own tables, laid
out as its upgrades leave a long-running one (every column added later is
nullable, and some rows hold NULL there), fills it with invented lines,
history, snapshots tied on their time, closed quarters (one with closing
data that is not JSON), alerts of every kind, foreign costs, the order link's
rows, a login with no history and a table the move does not know; exports it
with the stock app's analytics; and converts and proves it with Reactor's.
Exit 0 when the proof is empty. Everything is made up and written to a
temporary folder outside every repository, which is removed afterwards.
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
EXPORTER = os.path.join(HERE, "export_from_stock_app.py")
CONVERTER = os.path.join(ROOT, "tools", "stock_import.py")


def build(db, url: str) -> None:
    """The invented database, at the stock app's schema with added columns nullable."""
    from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine
    rng = random.Random(7)
    md = MetaData()
    tables = {}
    for t in db.Base.metadata.sorted_tables:
        copy = t.to_metadata(md)
        for c in copy.columns:
            if not c.primary_key:
                c.nullable = True
        tables[t.name] = copy
    Table("extra_notes", md, Column("id", Integer, primary_key=True), Column("text", String(40)))
    engine = create_engine(url)
    md.create_all(engine)
    t0 = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    items, keys = [], {}
    item_id = 0
    for n in range(40):
        item_id += rng.choice((1, 1, 2))                      # gaps in the ids
        cat = rng.choice(("Glass", "Glass", "Metal", "Film"))
        sub = rng.choice(("Blue", "Red", "Clear", "Amber"))
        size = str(rng.choice((20, 25, 30, 37.5)))
        key = "|".join((cat, sub, size, ""))
        if key in keys:                                      # the stock app's import keeps duplicates as |#2, |#3...
            dup = 2
            while f"{key}|#{dup}" in keys:
                dup += 1
            key = f"{key}|#{dup}"
        keys[key] = item_id
        currency = rng.choice(("GBP", "USD", "EUR", None))
        cost = round(rng.uniform(0.4, 9.0), 2)
        rate = {"USD": 0.78, "EUR": 0.85}.get(currency)
        start = rng.randint(0, 120)
        used = rng.choice((0, 0, rng.randint(1, 90)))
        items.append({
            "id": item_id, "key": key, "category": cat, "sub_category": sub, "size": size, "notes": "",
            "written_off": n % 13 == 5, "barcode": None if n % 4 == 0 else ("" if n % 4 == 1 else f"50{n:011d}"),
            "supplier": rng.choice(("Invented Glass Co", "Made Up Metals", "", None)), "currency": currency,
            "unit_cost": round(cost / rate, 3) if rate else None, "unit_cost_gbp": None if n == 7 else cost,
            "start": start, "received": rng.randint(0, 40), "used": used,
            "current": -1 if n == 11 else (0 if n == 12 else max(start - used, rng.randint(0, 30))),
            "reorder_point": rng.choice((0, 0, 10, 25)), "reorder_qty": rng.choice((0, None, 50)),
            "on_order": rng.choice((0, None, 20)),
            "created_at": t0, "updated_at": t0 + timedelta(days=n)})
    for i in items:                                           # the stock app reads reorder_qty only when it is due
        if i["reorder_point"] and i["reorder_qty"] is None:
            i["reorder_qty"] = 0
    snaps, snap_items, sid = [], [], 0
    for day in range(12):
        for reason in (("scheduled", "edit") if day % 3 == 0 else ("scheduled",)):
            sid += 1
            at = t0 + timedelta(days=day)                    # an edit tied on time with the nightly one
            lines = [{"id": sid * 1000 + i["id"], "snapshot_id": sid, "item_key": i["key"], "category": i["category"],
                      "written_off": i["written_off"], "current": i["current"] + (12 - day) * (i["used"] > 0),
                      "used": i["used"], "current_value": 0.0} for i in items]
            snaps.append({"id": sid, "taken_at": at, "reason": reason, "by_user": "system", "note": "",
                          "totals": json.dumps({"active_value_gbp": 1000.0 - day * 7.5})})
            snap_items.extend(lines)
    closing = [dict(i, name=i["sub_category"], current_value=round(i["current"] * (i["unit_cost_gbp"] or 0), 2),
                    created_at=None, updated_at=None) for i in items[:25]]
    periods = [{"id": 1, "label": "Quarter one", "opened_at": t0 - timedelta(days=180),
                "closed_at": t0 - timedelta(days=90), "closing_data": json.dumps(closing[:20])},
               {"id": 2, "label": "Quarter two", "opened_at": t0 - timedelta(days=90),
                "closed_at": t0 - timedelta(days=1), "closing_data": json.dumps(closing)},
               {"id": 3, "label": "Quarter broken", "opened_at": t0 - timedelta(days=1),
                "closed_at": t0, "closing_data": "{not json"},
               {"id": 5, "label": "Quarter now", "opened_at": t0, "closed_at": None, "closing_data": None}]
    history = [{"id": n * 2 + 1, "at": t0 + timedelta(hours=n), "user": rng.choice(("alice", "system", "gizmo", "?")),
                "action": "update", "item_key": rng.choice(list(keys)), "field": "current",
                "old_value": str(n), "new_value": str(n - 1), "detail": ""} for n in range(60)]
    # Orders as the stock app recorded them: an "ordered" line per item, some
    # placed together, one cleared later, and on-order figures to match or not.
    hid = max(h["id"] for h in history)
    for n, i in enumerate(i for i in items if i["on_order"]):
        for k, (qty, ref, minutes) in enumerate(((15, f"PO-{n}", 0), (10, f"PO-{n + 100}", 60 * 24 * 3))):
            hid += 1
            history.append({"id": hid, "at": t0 + timedelta(minutes=minutes, seconds=n), "user": "alice",
                            "action": "ordered", "item_key": i["key"], "field": "on_order", "old_value": "0",
                            "new_value": str(qty), "detail": f"ordered {qty} from Invented Glass Co · ref {ref}"})
    first_ordered = next((h for h in history if h["action"] == "ordered"), None)
    if first_ordered:
        hid += 1
        history.append({"id": hid, "at": t0 + timedelta(days=5), "user": "alice", "action": "ordered",
                        "item_key": first_ordered["item_key"], "field": "on_order", "old_value": "25",
                        "new_value": "0", "detail": "cleared outstanding order"})
    alerts = [{"id": 1, "at": t0, "kind": "stockout", "severity": "warning", "message": "Out", "item_key": items[0]["key"],
               "dismissed": True, "dismissed_by": "alice"},
              {"id": 2, "at": t0, "kind": "low_stock", "severity": "warning", "message": "Low", "item_key": "",
               "dismissed": False, "dismissed_by": None}]
    with engine.begin() as conn:
        conn.execute(tables["items"].insert(), items)
        conn.execute(tables["snapshots"].insert(), snaps)
        conn.execute(tables["snapshot_items"].insert(), snap_items)
        conn.execute(tables["periods"].insert(), periods)
        conn.execute(tables["audit_log"].insert(), history)
        conn.execute(tables["alerts"].insert(), alerts)
        conn.execute(tables["meta"].insert(), [{"key": "low_stock_days", "value": "30"},
                                               {"key": "fx_usd_gbp", "value": "0.8"}])
        conn.execute(tables["users"].insert(), [
            {"id": 1, "username": "alice", "password_hash": b"x", "created_at": t0, "last_login": t0,
             "prev_login": datetime(2026, 7, 1, 8, 0), "session_epoch": 3},
            {"id": 2, "username": "bob", "password_hash": b"y", "created_at": t0, "last_login": None,
             "prev_login": None, "session_epoch": None}])
        conn.execute(tables["supplier_contacts"].insert(), [
            {"id": 1, "supplier": "Invented Glass Co", "email": "orders@example.com", "lead_days": 7},
            {"id": 3, "supplier": "Made Up Metals", "email": "", "lead_days": None}])
        conn.execute(tables["gizmo_bookings"].insert(), [
            {"id": 2, "order_id": "1001", "order_name": "#1001", "at": t0,
             "lines": json.dumps([{"item_key": items[0]["key"], "qty": 1, "current_delta": -1}])}])
        conn.execute(tables["gizmo_usage_sheets"].insert(), [{"id": 1, "day": "2026-07-01", "at": t0,
                                                              "lines": "[]", "applied": None}])
        conn.execute(tables["gizmo_parked"].insert(), [{"id": 4, "order_id": "1002", "alias": "Colour|20", "qty": 0,
                                                        "at": t0}])
        conn.execute(tables["gizmo_aliases"].insert(), [{"id": 1, "alias": "Mono|20", "item_id": None,
                                                         "item_key": items[1]["key"], "at": t0}])
        conn.execute(tables["backups"].insert(), [{"id": 6, "at": t0, "filename": "stock-a.json.enc",
                                                   "size_bytes": 3, "item_count": 40, "blob": b"gAAAA-invented"}])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stock-app", required=True)
    ap.add_argument("--reactor-python", required=True)
    ap.add_argument("--keep", action="store_true", help="leave the temporary folder behind and print it")
    args = ap.parse_args(argv)
    os.environ["DATABASE_URL"] = "sqlite://"
    sys.path.insert(0, os.path.abspath(args.stock_app))
    import db
    tmp = tempfile.mkdtemp(prefix="stock-selfcheck-")
    try:
        source = os.path.join(tmp, "invented.db")
        build(db, "sqlite:///" + source)
        export = os.path.join(tmp, "export.json")
        r = subprocess.run([sys.executable, EXPORTER, "--stock-app", args.stock_app, "--database-url",
                            "sqlite:///" + source, "--out", export, "--now", "2026-07-20T12:00:00+00:00"],
                           capture_output=True, text=True)
        if r.returncode:
            print("the export failed:\n" + r.stdout + r.stderr)
            return 1
        with open(export, encoding="utf-8") as fh:
            unknown = json.load(fh).get("unknown_tables")
        if unknown != {"extra_notes": 0}:
            print(f"the export did not record the table it does not know: {unknown!r}")
            return 1
        people = os.path.join(tmp, "people.json")
        with open(people, "w", encoding="utf-8") as fh:
            json.dump({"alice": "acct-a", "bob": "acct-b"}, fh)
        r = subprocess.run([args.reactor_python, CONVERTER, "--export", export, "--people", people,
                            "--out", os.path.join(tmp, "stores")], capture_output=True, text=True)
        print((r.stdout + r.stderr).strip())
        return r.returncode
    finally:
        if args.keep:
            print("kept: " + tmp)
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
