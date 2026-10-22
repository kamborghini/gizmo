# ---- Stock in Reactor: the stores, the figures, the move (plan 1 of 4) ------
# The stock sheet's records held in Reactor's own stores, its figures worked
# out exactly as the stock app works them out, and the converter that moves a
# copy of its database across with a proof that nothing was lost. Every name,
# price and supplier here is invented: the repository is public.

from gizmo import stock_store

def _stock_clean():
    """Remove every stock file from the scratch folder, so a test starts empty."""
    for p in glob.glob(SCRATCH + "/stock_*"):
        os.remove(p)

def _stock_item(id, key, **over):
    cat, sub, size, notes = (key.split("|") + ["", "", "", ""])[:4]
    item = {"id": id, "key": key, "category": cat, "sub_category": sub, "size": size, "notes": notes,
            "written_off": False, "barcode": "", "supplier": "", "currency": "", "unit_cost": None,
            "unit_cost_gbp": 0.0, "start": 0, "received": 0, "used": 0, "current": 0,
            "reorder_point": 0, "reorder_qty": 0, "on_order": 0,
            "created_at": "2026-07-01T09:00:00+00:00", "updated_at": "2026-07-01T09:00:00+00:00"}
    item.update(over)
    return item

def _history_row(**over):
    row = {"at": "2026-10-01T10:00:00+00:00", "user": "someone", "action": "update",
           "item_key": "Glass|Blue|20|", "field": "current", "old_value": "5", "new_value": "4",
           "detail": "", "person": None}
    row.update(over)
    return row

@test
def t_stock_stores_round_trip():
    _stock_clean()
    items = {"items": {"3": _stock_item(3, "Glass|Blue|20|", current=4, unit_cost_gbp=1.25),
                       "7": _stock_item(7, "Glass|Blue|20||#2", barcode="CL7")}, "next_id": 8}
    periods = {"periods": [{"id": 1, "label": "Quarter one", "opened_at": "2026-04-01T00:00:00+00:00",
                            "closed_at": "2026-06-30T23:00:00+00:00", "closing_value": 12.5,
                            "closing_units": 10, "closing_skus": 2, "closing_used_value": 3.0,
                            "note": "", "closing_data": [{"key": "Glass|Blue|20|", "current": 4}]},
                           {"id": 2, "label": "Quarter two", "opened_at": "2026-07-01T00:00:00+00:00",
                            "closed_at": None, "closing_value": 0.0, "closing_units": 0, "closing_skus": 0,
                            "closing_used_value": 0.0, "note": "", "closing_data": None}], "next_id": 3}
    alerts = {"alerts": [{"id": 4, "at": "2026-10-01T10:00:00+00:00", "kind": "low_stock", "severity": "warning",
                          "message": "Low stock: Glass / Blue 20", "item_key": "Glass|Blue|20|",
                          "dismissed": True, "dismissed_by": "someone"}], "next_id": 5}
    suppliers = {"suppliers": [{"id": 1, "supplier": "Invented Glass Co", "email": "orders@example.com", "cc": "",
                                "contact_name": "", "subject": "Order", "body": "Please send", "lead_days": 7,
                                "min_order": "", "updated_at": "2026-10-01T10:00:00+00:00"}], "next_id": 2}
    settings = {"meta": {"low_stock_days": "21", "fx_usd_gbp": "0.8"}}
    bridge = {"bookings": [{"id": 1, "order_id": "1001", "order_name": "#1001", "at": "2026-10-01T10:00:00+00:00",
                            "lines": [{"item_key": "Glass|Blue|20|", "qty": 1, "current_delta": -1}]}],
              "sheets": [{"id": 1, "day": "2026-10-01", "at": "2026-10-01T18:00:00+00:00", "lines": [], "applied": []}],
              "parked": [{"id": 2, "order_id": "1002", "order_name": "#1002", "alias": "Colour|20", "qty": 1,
                          "note": "", "at": "2026-10-01T10:00:00+00:00"}],
              "aliases": [{"id": 1, "alias": "Mono|20", "item_id": 3, "item_key": "Glass|Blue|20|",
                           "at": "2026-10-01T10:00:00+00:00"}],
              "next_ids": {"bookings": 2, "sheets": 2, "parked": 3, "aliases": 2}}
    people = {"people": {"someone": "acct-1"}}
    stock_store.write_items(items); eq(stock_store.load_items(), items, "items")
    stock_store.write_periods(periods); eq(stock_store.load_periods(), periods, "periods")
    stock_store.write_alerts(alerts); eq(stock_store.load_alerts(), alerts, "alerts")
    stock_store.write_suppliers(suppliers); eq(stock_store.load_suppliers(), suppliers, "suppliers")
    stock_store.write_settings(settings); eq(stock_store.load_settings(), settings, "settings")
    stock_store.write_bridge(bridge); eq(stock_store.load_bridge(), bridge, "bridge")
    stock_store.write_people(people); eq(stock_store.load_people(), people, "people")
    _stock_clean()
    eq(stock_store.load_items(), {"items": {}, "next_id": 1}, "an empty items store")
    eq(stock_store.load_settings(), {"meta": {}}, "an empty settings store")

@test
def t_stock_history_appends_and_numbers_after_the_highest():
    _stock_clean()
    eq(stock_store.append_history([_history_row(id=41)]), [41], "a given id is kept")
    eq(stock_store.append_history([_history_row(), _history_row(field="used")]), [42, 43])
    rows = stock_store.read_history()
    eq([r["id"] for r in rows], [41, 42, 43], "all three, in order")
    eq(rows[2]["field"], "used")
    eq(stock_store.append_history([_history_row(id=50)]), [50], "a gap in the source's ids is kept")
    try:
        stock_store.append_history([_history_row(id=45)])
        ok(False, "an id below the highest must be refused")
    except ValueError:
        pass
    eq([r["id"] for r in stock_store.read_history()], [41, 42, 43, 50], "the refused row was not written")

@test
def t_a_torn_stock_history_line_is_skipped_not_fatal():
    _stock_clean()
    stock_store.append_history([_history_row(), _history_row()])
    with open(stock_store.STOCK_HISTORY_PATH, "a", encoding="utf-8") as fh:
        fh.write('{"id": 3, "at": "2026-10-01T1')         # a crash in the middle of an append
    eq([r["id"] for r in stock_store.read_history()], [1, 2], "the two complete lines")
    eq(stock_store.append_history([_history_row()]), [3], "numbered after the last complete line")
    eq([r["id"] for r in stock_store.read_history()], [1, 2, 3], "the torn line stays skipped")

@test
def t_stock_snapshots_go_to_their_files():
    _stock_clean()
    stock_store.append_snapshot({"id": 8, "taken_at": "2026-10-22T23:30:00+00:00", "reason": "edit",
                                 "by_user": "someone", "note": "", "totals": {"active_units": 4},
                                 "items": [{"id": 90, "item_key": "Glass|Blue|20|", "category": "Glass",
                                            "written_off": False, "current": 4, "used": 1, "current_value": 5.0}]})
    stock_store.append_snapshot({"id": 9, "taken_at": "2026-10-22T00:05:00+00:00", "reason": "scheduled",
                                 "by_user": "system", "note": "", "totals": {}, "items": []})
    ok(os.path.exists(stock_store.STOCK_SNAPSHOTS_SCHEDULED_PATH), "the nightly file")
    ok(os.path.exists(stock_store.STOCK_SNAPSHOTS_CHANGES_PREFIX + "2026-10-22.jsonl"), "the day file")
    snaps = stock_store.read_snapshots()
    eq([s["id"] for s in snaps], [8, 9], "both, ordered by id (the nightly file is read first)")
    eq(snaps[0]["items"][0]["current_value"], 5.0)

@test
def t_stock_suppliers_are_owner_only():
    _stock_clean()
    stock_store.write_suppliers({"suppliers": [], "next_id": 1})
    eq(os.stat(stock_store.STOCK_SUPPLIERS_PATH).st_mode & 0o777, 0o600)

@test
def t_stock_files_sit_at_the_top_of_the_data_folder():
    """Reactor's backup takes only the files at the top of the data folder."""
    import ast as _ast
    names = [n for n in dir(stock_store) if n.startswith("STOCK_") and (n.endswith("_PATH") or n.endswith("_PREFIX"))]
    eq(len(names), 14, "every stock path")
    data_dir = os.path.dirname(scheduler.SCHEDULE_PATH)
    for n in names:
        eq(os.path.dirname(getattr(stock_store, n)), data_dir, n)
    src = open(stock_store.__file__, encoding="utf-8").read()
    defaults = {}
    for x in _ast.walk(_ast.parse(src)):
        if (isinstance(x, _ast.Call) and _ast.unparse(x.func) == "os.environ.get" and len(x.args) == 2
                and isinstance(x.args[0], _ast.Constant) and isinstance(x.args[1], _ast.Constant)):
            defaults[x.args[0].value] = x.args[1].value
    eq(sorted(defaults), sorted(names), "each read from the setting of its own name")
    for n, d in defaults.items():
        eq(os.path.dirname(d), "/data", n + "'s default")
    _stock_clean()
    stock_store.write_items({"items": {}, "next_id": 1})
    stock_store.append_history([_history_row()])
    stock_store.append_snapshot({"id": 1, "taken_at": "2026-10-22T00:05:00+00:00", "reason": "scheduled",
                                 "by_user": "system", "note": "", "totals": {}, "items": []})
    stock_store.write_backup({"id": 1, "at": "2026-10-22T00:10:00+00:00", "filename": "stock.json.enc",
                              "size_bytes": 3, "item_count": 0, "format": "legacy-fernet", "token": "YWJj"})
    import zipfile as _zip
    buf, _added = backup._build_backup_zip()
    held = set(_zip.ZipFile(buf).namelist())
    for p in glob.glob(SCRATCH + "/stock_*"):
        ok(any(h.endswith("/" + os.path.basename(p)) for h in held), os.path.basename(p) + " is in Reactor's backup")
    _stock_clean()

@test
def t_stock_backups_are_a_file_each():
    _stock_clean()
    a = stock_store.write_backup({"id": 2, "at": "2026-10-22T00:10:00+00:00", "filename": "stock-a.json.enc",
                                  "size_bytes": 3, "item_count": 0, "format": "legacy-fernet", "token": "YWJj"})
    b = stock_store.write_backup({"id": 3, "at": "2026-10-22T00:10:00+00:00", "filename": "stock-a.json.enc",
                                  "size_bytes": 3, "item_count": 1, "format": "stock-1",
                                  "items": [_stock_item(3, "Glass|Blue|20|")]})
    ok(a != b, "two backups in the same second are two files")
    eq(os.path.dirname(a), os.path.dirname(stock_store.STOCK_ITEMS_PATH))
    eq([x["id"] for x in stock_store.list_backups()], [2, 3], "listed by id")
    eq(stock_store.list_backups()[1]["items"][0]["key"], "Glass|Blue|20|")

# ---- the figures, ported from the stock app --------------------------------

from gizmo import stock_figures as sfig

@test
def t_a_written_off_stock_line_is_worth_nothing():
    eq(sfig.current_value({"current": 3, "unit_cost_gbp": 2.5, "written_off": True}), 0)
    eq(sfig.current_value({"current": 3, "unit_cost_gbp": 2.5, "written_off": False}), 7.5)

@test
def t_stock_money_rounds_as_python_rounds():
    """2.675 is 2.67499999... as a binary float: Python's round gives 2.67,
    and so must the port, or a value drifts by a penny from the stock app's."""
    eq(sfig.current_value({"current": 1, "unit_cost_gbp": 2.675, "written_off": False}), 2.67)

@test
def t_stock_sell_through_and_dead_stock():
    items = [_stock_item(1, "Glass|Blue|20|", start=10, used=5, current=5, unit_cost_gbp=1.0),
             _stock_item(2, "Glass|Red|20|", start=10, used=0, current=10, unit_cost_gbp=2.0),
             _stock_item(3, "Glass|Green|20|", start=0, used=0, current=0, unit_cost_gbp=2.0),
             _stock_item(4, "Glass|Grey|20|", start=10, used=0, current=3, unit_cost_gbp=4.0, written_off=True)]
    c = sfig.compute_current(items)
    eq(c["headline"]["sell_through_pct"], 25.0, "5 used of 20 started, written-off lines left out")
    eq([d["key"] for d in c["dead_stock"]["top"]], ["Glass|Red|20|"], "only the unused line with a value")
    eq(c["write_offs"]["estimated_sunk_cost_gbp"], 12.0, "a written-off line's cost is reported apart")
    eq(c["headline"]["active_stock_value_gbp"], 25.0)

@test
def t_a_stock_line_is_reordered_at_its_point():
    listed = sfig.reorder_suggestions([_stock_item(1, "Glass|Blue|20|", reorder_point=10, current=6, on_order=4)])
    eq(listed["total_lines"], 1, "6 on hand and 4 coming is still at the point of 10")
    line = listed["suppliers"][0]["items"][0]
    eq(line["suggested_qty"], 14, "with no order quantity: max(2 x 10 - 6, 10)")
    eq(listed["suppliers"][0]["supplier"], "Unknown", "no supplier is grouped as Unknown")
    eq(sfig.reorder_suggestions([_stock_item(1, "Glass|Blue|20|", reorder_point=10, current=6, on_order=5)])["total_lines"],
       0, "6 on hand and 5 coming is above the point")

@test
def t_stock_suggested_levels_cover_the_lead_time():
    one = _stock_item(1, "Glass|Blue|20|", used=90, supplier="Invented Glass Co")
    s = sfig.suggest_reorder_points([one], {"Invented Glass Co": 7})["suggestions"][0]
    eq((s["cover_days"], s["reorder_point"], s["reorder_qty"]), (21, 21, 90), "7 days' lead and 14 of safety")
    s = sfig.suggest_reorder_points([one])["suggestions"][0]
    eq((s["cover_days"], s["reorder_point"]), (21, 21), "no lead time: 21 days' cover")
    s = sfig.suggest_reorder_points([_stock_item(2, "Glass|Red|20|", used=13)])["suggestions"][0]
    eq(s["reorder_qty"], 20, "a quantity of 13 is rounded up to the next ten")

@test
def t_null_stock_columns_count_as_the_stock_app_counts_them():
    item = _stock_item(1, "Glass|Blue|20|", current=6, reorder_point=10, reorder_qty=0, on_order=None,
                       unit_cost=None, unit_cost_gbp=None)
    r = sfig.reorder_suggestions([item])
    eq(r["total_lines"], 1)
    line = r["suppliers"][0]["items"][0]
    eq((line["on_order"], line["suggested_qty"], line["order_value_gbp"]), (0, 14, 0.0))
    eq(sfig.current_value(item), 0)

@test
def t_stock_days_to_stockout_by_history_or_run_rate():
    item = _stock_item(1, "Glass|Blue|20|", current=20, used=45)
    def snap(id, at, current):
        return {"id": id, "taken_at": at, "reason": "scheduled", "by_user": "system", "note": "",
                "totals": {"active_value_gbp": 0}, "items": [{"id": id * 10, "item_key": "Glass|Blue|20|",
                "category": "Glass", "written_off": False, "current": current, "used": 0, "current_value": 0}]}
    f = sfig.forecast([item], [snap(1, "2026-10-01T00:00:00+00:00", 30), snap(2, "2026-10-11T00:00:00+00:00", 20)])
    row = f["items"][0]
    eq((row["daily_use"], row["days_to_stockout"], row["basis"]), (1.0, 20.0, "history"))
    row = sfig.forecast([item], [snap(1, "2026-10-01T00:00:00+00:00", 30)])["items"][0]
    eq((row["daily_use"], row["basis"]), (0.5, "run-rate"), "45 used over a 90-day quarter")
    eq(sfig.forecast([item], [snap(1, "2026-10-01T00:00:00", 30), snap(2, "2026-10-11T00:00:00+00:00", 20)])
       ["items"][0]["daily_use"], 1.0, "a naive timestamp is UTC")

@test
def t_low_stock_alert_uses_the_days_setting():
    meta = {"low_stock_days": "21"}
    def kinds(**over):
        return [(a["kind"], a["severity"]) for a in sfig.detect_anomalies([_stock_item(1, "Glass|Blue|20|", **over)], meta, None)]
    eq(kinds(current=10, used=90), [("low_stock", "warning")], "10 days of cover against 21")
    eq(kinds(current=30, used=90), [], "30 days of cover")
    eq(kinds(current=0, used=5), [("stockout", "warning")])
    eq(kinds(current=-1, used=5), [("anomaly", "critical")])
    eq([a["kind"] for a in sfig.detect_anomalies([_stock_item(1, "Glass|Blue|20|", current=30, used=90)],
                                                 {"low_stock_days": "40"}, None)], ["low_stock"], "the setting is read")

@test
def t_stock_compare_live_against_a_closed_quarter():
    items = [_stock_item(1, "Glass|Blue|20|", current=4, unit_cost_gbp=1.0)]
    closed = {"id": 1, "label": "Quarter one", "closed_at": "2026-06-30T23:00:00+00:00",
              "opened_at": "2026-04-01T00:00:00+00:00",
              "closing_data": [dict(sfig.item_view(_stock_item(1, "Glass|Blue|20|", current=10, unit_cost_gbp=1.0)))]}
    open_ = {"id": 2, "label": "Quarter two", "closed_at": None, "opened_at": "2026-07-01T00:00:00+00:00",
             "closing_data": None}
    c = sfig.compare(sfig.side_period(closed), sfig.side_live(items, [closed, open_]))
    eq((c["left"]["label"], c["right"]["label"]), ("Quarter one (closed)", "Quarter two (live)"))
    eq(c["by_category"], [{"category": "Glass", "left": 10.0, "right": 4.0, "delta": -6.0}])
    eq(c["top_unit_movers"][0]["cur_delta"], -6)
    eq(sfig.side_live(items)["label"], "Current (live)", "no open quarter")

@test
def t_stock_foreign_costs_restated_at_todays_rate():
    items = [_stock_item(1, "Glass|Blue|20|", current=10, currency="USD", unit_cost=1.0, unit_cost_gbp=0.75)]
    eq(sfig.fx_rates(items, {})["USD"], 0.75, "with no rate set, the rate the costs were booked at")
    r = sfig.fx_revaluation(items, {"fx_usd_gbp": "0.8"})
    eq((r["total_booked_gbp"], r["total_today_gbp"], r["total_drift_gbp"]), (7.5, 8.0, 0.5))

@test
def t_stock_trends_read_the_snapshots_oldest_first():
    snaps = [{"id": 2, "taken_at": "2026-10-02T00:00:00+00:00", "reason": "edit", "totals": {"active_units": 3}},
             {"id": 1, "taken_at": "2026-10-01T00:00:00+00:00", "reason": "scheduled", "totals": {"active_units": 5}}]
    t = sfig.trends(snaps)
    eq([p["active_units"] for p in t["points"]], [5, 3])
    eq(t["points"][0]["at"], "2026-10-01T00:00:00+00:00")
    eq(sfig.totals_for_snapshot([_stock_item(1, "Glass|Blue|20|", current=4, unit_cost_gbp=1.0)])["by_category"],
       {"Glass": 4.0})

# ---- the converter and its proof ---------------------------------------------

import subprocess as _subprocess
from tools import stock_import

_STOCK_COLUMNS = {
    "items": ["id", "key", "category", "sub_category", "size", "notes", "written_off", "barcode", "supplier",
              "currency", "unit_cost", "unit_cost_gbp", "start", "received", "used", "current", "reorder_point",
              "reorder_qty", "on_order", "created_at", "updated_at"],
    "snapshots": ["id", "taken_at", "reason", "by_user", "note", "totals"],
    "snapshot_items": ["id", "snapshot_id", "item_key", "category", "written_off", "current", "used", "current_value"],
    "audit_log": ["id", "at", "user", "action", "item_key", "field", "old_value", "new_value", "detail"],
    "alerts": ["id", "at", "kind", "severity", "message", "item_key", "dismissed", "dismissed_by"],
    "backups": ["id", "at", "filename", "size_bytes", "item_count", "blob"],
    "meta": ["key", "value"],
    "periods": ["id", "label", "opened_at", "closed_at", "closing_value", "closing_units", "closing_skus",
                "closing_used_value", "note", "closing_data"],
    "users": ["id", "username", "created_at", "last_login", "prev_login", "session_epoch"],
    "gizmo_bookings": ["id", "order_id", "order_name", "at", "lines"],
    "gizmo_usage_sheets": ["id", "day", "at", "lines", "applied"],
    "gizmo_parked": ["id", "order_id", "order_name", "alias", "qty", "note", "at"],
    "gizmo_aliases": ["id", "alias", "item_id", "item_key", "at"],
    "supplier_contacts": ["id", "supplier", "email", "cc", "contact_name", "subject", "body", "lead_days",
                          "min_order", "updated_at"],
}

def _stock_export(history_user="someone", reorder_point_9=0):
    """An invented export in the exporter's shape, with the stock app's figures for it."""
    def row(table, **values):
        return {c: values.get(c) for c in _STOCK_COLUMNS[table]}
    def item(id, key, **over):
        base = {k: v for k, v in _stock_item(id, key).items()}
        base.update(over)
        return row("items", **base)
    items = [item(3, "Glass|Blue|20|", start=10, used=4, current=6, unit_cost_gbp=1.25, barcode="TEST-CODE-3",
                  supplier="Invented Glass Co", created_at="2026-07-01T10:00:00"),
             item(7, "Glass|Blue|20||#2", start=5, current=2, unit_cost_gbp=2.0,
                  created_at="2026-07-01T11:00:00+01:00"),
             item(9, "Glass|Red|30|", barcode=None, on_order=None, unit_cost=None, unit_cost_gbp=0.5,
                  reorder_point=reorder_point_9),
             item(11, "Glass|Grey|20|", current=3, unit_cost_gbp=4.0, written_off=True)]
    snap_items = [row("snapshot_items", id=1, snapshot_id=1, item_key="Glass|Blue|20|", category="Glass",
                      written_off=False, current=8, used=2, current_value=10.0),
                  row("snapshot_items", id=2, snapshot_id=1, item_key="Glass|Blue|20||#2", category="Glass",
                      written_off=False, current=2, used=0, current_value=4.0),
                  row("snapshot_items", id=5, snapshot_id=2, item_key="Glass|Blue|20|", category="Glass",
                      written_off=False, current=6, used=4, current_value=7.5)]
    snaps = [row("snapshots", id=1, taken_at="2026-10-01T00:05:00+00:00", reason="scheduled", by_user="system",
                 note="", totals=json.dumps({"active_value_gbp": 14.0})),
             row("snapshots", id=2, taken_at="2026-10-02T09:30:00+00:00", reason="edit", by_user="someone",
                 note="", totals=json.dumps({"active_value_gbp": 11.5}))]
    closing = [sfig.item_view(_stock_item(3, "Glass|Blue|20|", current=12, unit_cost_gbp=1.25))]
    periods = [row("periods", id=1, label="Quarter one", opened_at="2026-04-01T00:00:00+00:00",
                   closed_at="2026-06-30T23:00:00+00:00", closing_value=15.0, closing_units=12, closing_skus=1,
                   closing_used_value=0.0, note="", closing_data=json.dumps(closing)),
               row("periods", id=2, label="Quarter two", opened_at="2026-07-01T00:00:00+00:00", closed_at=None,
                   closing_value=0.0, closing_units=0, closing_skus=0, closing_used_value=0.0, note="",
                   closing_data="")]
    tables = {
        "items": items, "snapshots": snaps, "snapshot_items": snap_items,
        "audit_log": [row("audit_log", id=4, at="2026-10-01T09:00:00+00:00", user=history_user, action="update",
                          item_key="Glass|Navy|20|", field="current", old_value="7", new_value="6", detail=""),
                      row("audit_log", id=6, at="2026-10-01T09:01:00", user="system", action="snapshot",
                          item_key="", field="", old_value="", new_value="", detail="edit snapshot #2"),
                      row("audit_log", id=8, at="2026-10-01T09:02:00+00:00", user="gizmo", action="book",
                          item_key="Glass|Blue|20|", field="current", old_value="6", new_value="5", detail="")],
        "alerts": [row("alerts", id=2, at="2026-10-02T09:30:00+00:00", kind="low_stock", severity="warning",
                       message="Low stock", item_key="Glass|Blue|20|", dismissed=True, dismissed_by="someone")],
        "backups": [row("backups", id=1, at="2026-10-02T02:00:00+00:00", filename="stock-20261002-020000.json.enc",
                        size_bytes=11, item_count=4, blob=base64.b64encode(b"gAAAAABfake").decode())],
        "meta": [row("meta", key="low_stock_days", value="21"), row("meta", key="schema", value="3")],
        "periods": periods,
        "users": [row("users", id=1, username="someone", created_at="2026-06-01T00:00:00+00:00",
                      last_login=None, prev_login="2026-10-01T08:00:00", session_epoch=0)],
        "gizmo_bookings": [row("gizmo_bookings", id=1, order_id="1001", order_name="#1001",
                               at="2026-10-01T09:02:00+00:00",
                               lines=json.dumps([{"item_key": "Glass|Blue|20|", "qty": 1, "current_delta": -1}]))],
        "gizmo_usage_sheets": [row("gizmo_usage_sheets", id=1, day="2026-10-01", at="2026-10-01T18:00:00+00:00",
                                   lines="[]", applied=json.dumps([{"item_key": "Glass|Blue|20|", "delta": 1}]))],
        "gizmo_parked": [row("gizmo_parked", id=3, order_id="1002", order_name="#1002", alias="Colour|20", qty=1,
                             note="", at="2026-10-01T09:03:00+00:00")],
        "gizmo_aliases": [row("gizmo_aliases", id=1, alias="Mono|20", item_id=3, item_key="Glass|Blue|20|",
                              at="2026-10-01T09:04:00+00:00")],
        "supplier_contacts": [row("supplier_contacts", id=1, supplier="Invented Glass Co", email="orders@example.com",
                                  cc="", contact_name="", subject="Order", body="Please send", lead_days=7,
                                  min_order="", updated_at="2026-10-01T09:05:00+00:00")],
    }
    export = {"format": "stock-export-1", "exported_at": "2026-10-22T12:00:00+00:00",
              "now": "2026-10-22T12:00:00+00:00", "source_head": "0000000",
              "tables": {n: {"columns": _STOCK_COLUMNS[n], "count": len(rows), "rows": rows, "missing": False}
                         for n, rows in tables.items()}}
    # The stock app's figures for this data, worked out the way the exporter
    # asks the stock app for them (the port stands in for it here).
    if reorder_point_9 is None:
        return export      # the stock app's reorder page fails on a NULL point, so it has no figures
    live = [dict(i) for i in items]
    snapshots = [dict(s, totals=json.loads(s["totals"]),
                      items=[x for x in snap_items if x["snapshot_id"] == s["id"]]) for s in snaps]
    plain_periods = [dict(p, closing_data=json.loads(p["closing_data"]) if p["closing_data"] else None)
                     for p in periods]
    meta = {"low_stock_days": "21", "schema": "3"}
    leads = {"Invented Glass Co": 7}
    export["expected"] = {
        "compute_current": sfig.compute_current(live), "reorder_suggestions": sfig.reorder_suggestions(live),
        "suggest_reorder_points": sfig.suggest_reorder_points(live, leads), "lead_by_supplier": leads,
        "fx_rates": sfig.fx_rates(live, meta), "fx_revaluation": sfig.fx_revaluation(live, meta),
        "totals_for_snapshot": sfig.totals_for_snapshot(live), "trends": sfig.trends(snapshots),
        "forecast": sfig.forecast(live, snapshots),
        "detect_anomalies": {"prev_snapshot_id": 2, "alerts": sfig.detect_anomalies(live, meta, {"active_value_gbp": 11.5})},
        "compare": [{"left": 1, "right": "current",
                     "result": sfig.compare(sfig.side_period(plain_periods[0]), sfig.side_live(live, plain_periods))}],
    }
    return export

def _stock_out(name):
    out = os.path.join(SCRATCH, "stock-move-" + name)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    return out

PEOPLE = {"someone": "acct-1"}

@test
def t_the_stock_converter_keeps_every_record():
    export = _stock_export()
    eq(export["expected"]["compute_current"]["headline"],
       {"active_stock_value_gbp": 11.5, "active_units": 8, "active_skus": 3, "start_units": 15, "used_units": 4,
        "cogs_used_value_gbp": 5.0, "sell_through_pct": 26.67}, "the headline, worked out by hand")
    out = _stock_out("keeps")
    stock_import.convert(export, PEOPLE, out)
    eq(stock_import.prove(export, out), [], "the proof finds nothing")
    with stock_store.rooted(out):
        items = stock_store.load_items()
        eq(sorted(items["items"]), ["11", "3", "7", "9"], "ids kept")
        eq(items["next_id"], 12)
        eq(items["items"]["7"]["key"], "Glass|Blue|20||#2", "a de-duplicated key kept verbatim")
        eq(items["items"]["9"]["barcode"], None, "NULL stays NULL")
        eq(items["items"]["3"]["created_at"], items["items"]["7"]["created_at"], "a naive time is UTC")
        history = stock_store.read_history()
        eq([h["id"] for h in history], [4, 6, 8], "history ids kept, gaps and all")
        eq(history[0]["item_key"], "Glass|Navy|20|", "a row keeps the key it was written with")
        eq([h["person"] for h in history], ["acct-1", None, None], "people mapped; system and gizmo are nobody")
        eq([s["id"] for s in stock_store.read_snapshots()], [1, 2])
        eq(stock_store.load_periods()["periods"][0]["closing_data"][0]["current"], 12)
        eq(stock_store.load_bridge()["bookings"][0]["lines"][0]["qty"], 1, "JSON text decoded")
        eq(stock_store.list_backups()[0]["token"], base64.b64encode(b"gAAAAABfake").decode())
        eq(stock_store.load_people()["people"], PEOPLE)
        eq(stock_store.load_settings(), {"meta": {"low_stock_days": "21", "schema": "3"}})
    out = _stock_out("null-point")
    stock_import.convert(_stock_export(reorder_point_9=None), PEOPLE, out)
    with stock_store.rooted(out):
        eq(stock_store.load_items()["items"]["9"]["reorder_point"], None, "a NULL reorder point is kept as NULL")

@test
def t_the_stock_proof_names_a_changed_field():
    export = _stock_export()
    out = _stock_out("changed")
    stock_import.convert(export, PEOPLE, out)
    with stock_store.rooted(out):
        doc = stock_store.load_items()
        doc["items"]["7"]["barcode"] = "LABEL-7"   # no figure, order or other label moves with it
        stock_store.write_items(doc)
    found = stock_import.prove(export, out)
    eq(len(found), 1, found)
    ok("items" in found[0] and "7" in found[0] and "barcode" in found[0], found[0])

@test
def t_the_stock_proof_notices_a_dropped_history_line():
    export = _stock_export()
    out = _stock_out("dropped")
    stock_import.convert(export, PEOPLE, out)
    with stock_store.rooted(out):
        path = stock_store.STOCK_HISTORY_PATH
    lines = open(path, encoding="utf-8").read().splitlines(True)
    open(path, "w", encoding="utf-8").write("".join(lines[:1] + lines[2:]))
    found = " | ".join(stock_import.prove(export, out))
    ok("audit_log" in found and "3 rows" in found, found)
    ok("checksum" in found, found)

@test
def t_a_stock_person_without_a_mapping_is_refused():
    try:
        stock_import.convert(_stock_export(history_user="stranger"), PEOPLE, _stock_out("stranger"))
        ok(False, "an unmapped person must be refused")
    except ValueError as e:
        ok("stranger" in str(e), str(e))
        ok("system" not in str(e) and "gizmo" not in str(e), "system and gizmo need no mapping")
    eq(glob.glob(os.path.join(SCRATCH, "stock-move-stranger", "*")), [], "nothing written")

@test
def t_the_stock_proof_compares_the_figures():
    export = _stock_export()
    out = _stock_out("figures")
    stock_import.convert(export, PEOPLE, out)
    export["expected"]["compute_current"]["headline"]["active_stock_value_gbp"] = 11.51
    found = stock_import.prove(export, out)
    eq(len(found), 1, found)
    ok("compute_current" in found[0] and "active_stock_value_gbp" in found[0], found[0])

@test
def t_the_stock_converter_never_writes_inside_the_repository():
    root = os.path.dirname(os.path.dirname(os.path.abspath(stock_store.__file__)))
    export_file, people_file = os.path.join(SCRATCH, "stock-export.json"), os.path.join(SCRATCH, "stock-people.json")
    json.dump(_stock_export(), open(export_file, "w"))
    json.dump(PEOPLE, open(people_file, "w"))
    inside = os.path.join(root, "stock-move-test-out")
    tool = os.path.join(root, "tools", "stock_import.py")
    r = _subprocess.run([sys.executable, tool, "--export", export_file, "--people", people_file, "--out", inside],
                        capture_output=True, text=True)
    ok(r.returncode != 0, "refused")
    ok(not os.path.exists(inside), "nothing written inside the repository")
    r = _subprocess.run([sys.executable, tool, "--export", export_file, "--people", people_file,
                         "--out", _stock_out("cli"), "--report", os.path.join(root, "stock-proof.txt")],
                        capture_output=True, text=True)
    ok(r.returncode != 0 and not os.path.exists(os.path.join(root, "stock-proof.txt")), "a report inside is refused too")
    r = _subprocess.run([sys.executable, tool, "--export", export_file, "--people", people_file,
                         "--out", _stock_out("cli")], capture_output=True, text=True)
    eq(r.returncode, 0, r.stdout + r.stderr)

@test
def t_stock_movers_tied_on_size_prove_in_either_order():
    """The stock app takes a comparison's movers out of a set: lines tied on
    the size of their move come out in no fixed order."""
    export = _stock_export()
    out = _stock_out("movers")
    stock_import.convert(export, PEOPLE, out)
    movers = export["expected"]["compare"][0]["result"]["top_value_movers"]
    eq([abs(m["value_delta"]) for m in movers][-2:], [0, 0], "the last two are tied")
    movers[-2], movers[-1] = movers[-1], movers[-2]
    eq(stock_import.prove(export, out), [], "either order of a tie proves")
    movers[-1] = dict(movers[-1], item="Glass / Nowhere 99")
    found = stock_import.prove(export, out)
    eq(len(found), 1, found)
    ok("Nowhere" in found[0], found[0])

# ---- the final review's findings, pinned --------------------------------------

@test
def t_a_refused_stock_history_batch_writes_nothing():
    """A row that cannot be written (NaN is not JSON) refuses the whole batch:
    nothing of it reaches the file, so a retry cannot write a line twice."""
    _stock_clean()
    try:
        stock_store.append_history([_history_row(), _history_row(new_value=float("nan"))])
        ok(False, "a NaN must be refused")
    except ValueError:
        pass
    eq(stock_store.read_history(), [], "nothing of the refused batch is on disk")
    eq(stock_store.append_history([_history_row()]), [1], "the retry is numbered from the start")

@test
def t_a_long_stock_snapshot_line_does_not_make_appends_read_whole_files():
    """A snapshot of several hundred lines is one long line; the next number
    is still read from the end of the file, never by reading all of it."""
    _stock_clean()
    big = [{"id": n, "item_key": "Glass|Blue|%d|" % n, "category": "Glass", "written_off": False,
            "current": n, "used": 1, "current_value": 1.25} for n in range(1, 2500)]
    stock_store.append_snapshot({"taken_at": "2026-10-22T00:05:00+00:00", "reason": "scheduled",
                                 "by_user": "system", "note": "", "totals": {}, "items": big})
    ok(os.path.getsize(stock_store.STOCK_SNAPSHOTS_SCHEDULED_PATH) > 3 * 65536, "a line longer than the tail read")
    stock_store.append_history([_history_row(detail="x" * 200000)])
    real = stock_store._read_lines
    def whole(path):
        raise AssertionError("read the whole of " + os.path.basename(path))
    stock_store._read_lines = whole
    try:
        stock_store.append_snapshot({"taken_at": "2026-10-22T09:00:00+00:00", "reason": "scheduled",
                                     "by_user": "system", "note": "", "totals": {}, "items": []})
        eq(stock_store.append_history([_history_row()]), [2])
    finally:
        stock_store._read_lines = real
    eq([s["id"] for s in stock_store.read_snapshots()], [1, 2])

@test
def t_the_stock_proof_notices_a_history_out_of_order():
    """The next history number is read from the last line, so the order of
    the lines is part of what must be proven, not only their content."""
    export = _stock_export()
    out = _stock_out("order")
    stock_import.convert(export, PEOPLE, out)
    with stock_store.rooted(out):
        path = stock_store.STOCK_HISTORY_PATH
    lines = open(path, encoding="utf-8").read().splitlines(True)
    open(path, "w", encoding="utf-8").write("".join([lines[-1]] + lines[1:-1] + [lines[0]]))
    found = " | ".join(stock_import.prove(export, out))
    ok("out of order" in found, found)
    ok("checksum" in found, found)

@test
def t_every_stock_login_needs_an_account():
    """Someone who can sign in to the stock app but has never changed
    anything still needs their Reactor account named."""
    export = _stock_export()
    export["tables"]["users"]["rows"].append({"id": 2, "username": "colleague", "created_at": "2026-06-02T00:00:00+00:00",
                                              "last_login": None, "prev_login": None, "session_epoch": 1})
    export["tables"]["users"]["count"] = 2
    try:
        stock_import.convert(export, PEOPLE, _stock_out("colleague"))
        ok(False, "an unmapped login must be refused")
    except ValueError as e:
        ok("colleague" in str(e), str(e))
    out = _stock_out("colleague-mapped")
    stock_import.convert(export, dict(PEOPLE, colleague="acct-2"), out)
    eq(stock_import.prove(export, out), [])

@test
def t_stock_logins_are_carried_and_proven():
    """The sign-in times stay with each person (a time without a zone is
    UTC); the password and the stock app's session counter stay behind."""
    export = _stock_export()
    out = _stock_out("logins")
    stock_import.convert(export, PEOPLE, out)
    with stock_store.rooted(out):
        doc = stock_store.load_people()
        eq(doc["logins"]["someone"], {"id": 1, "created_at": "2026-06-01T00:00:00+00:00", "last_login": None,
                                      "prev_login": "2026-10-01T08:00:00+00:00"})
        doc["logins"]["someone"]["prev_login"] = "2026-09-01T08:00:00+00:00"
        stock_store.write_people(doc)
    found = stock_import.prove(export, out)
    eq(len(found), 1, found)
    ok("users" in found[0] and "prev_login" in found[0], found[0])

@test
def t_a_table_the_stock_move_does_not_know_is_reported():
    export = _stock_export()
    export["unknown_tables"] = {"purchase_orders": 3, "scratch": 0}
    out = _stock_out("unknown")
    stock_import.convert(export, PEOPLE, out)
    found = stock_import.prove(export, out)
    eq(len(found), 1, found)
    ok("purchase_orders" in found[0] and "3" in found[0], found[0])

@test
def t_stock_ids_carry_on_from_the_old_sequence():
    """A supplier contact or a link row deleted at the top leaves the stock
    app's sequence ahead of the highest id left; its number is never reused."""
    export = _stock_export()
    export["sequences"] = {"supplier_contacts": 5, "gizmo_parked": 9, "items": 11, "alerts": 1}
    out = _stock_out("sequence")
    stock_import.convert(export, PEOPLE, out)
    with stock_store.rooted(out):
        eq(stock_store.load_suppliers()["next_id"], 6, "after the sequence")
        eq(stock_store.load_bridge()["next_ids"]["parked"], 10)
        eq(stock_store.load_items()["next_id"], 12, "the sequence and the highest agree")
        eq(stock_store.load_alerts()["next_id"], 3, "after the highest when the sequence is behind it")
    eq(stock_import.prove(export, out), [])
    with stock_store.rooted(out):
        doc = stock_store.load_suppliers()
        doc["next_id"] = 2
        stock_store.write_suppliers(doc)
    found = stock_import.prove(export, out)
    eq(len(found), 1, found)
    ok("suppliers" in found[0] and "next id" in found[0], found[0])

# ---- the converter rebuilds the orders still outstanding (plan 2a) --------------

def _stock_export_with_orders(on_order, ordered):
    """The invented export, with on-order figures and "ordered" history lines
    as the stock app wrote them."""
    export = _stock_export()
    for row in export["tables"]["items"]["rows"]:
        row["on_order"] = on_order.get(row["id"], 0)
    hist = export["tables"]["audit_log"]
    next_id = max(r["id"] for r in hist["rows"]) + 1
    for n, (at, key, detail) in enumerate(ordered):
        hist["rows"].append({"id": next_id + n, "at": at, "user": "someone", "action": "ordered", "item_key": key,
                             "field": "on_order", "old_value": "0", "new_value": "0", "detail": detail})
    hist["count"] = len(hist["rows"])
    return export

@test
def t_the_stock_converter_rebuilds_outstanding_orders_from_ordered_lines():
    export = _stock_export_with_orders({3: 8, 7: 0}, [
        ("2026-09-01T10:00:00", "Glass|Blue|20|", "ordered 5 from Invented Glass Co · ref PO-1"),
        ("2026-09-01T10:00:01", "Glass|Blue|20||#2", "ordered 2 from Invented Glass Co · ref PO-1"),
        ("2026-09-08T10:00:00", "Glass|Blue|20|", "ordered 6 from Invented Glass Co · ref PO-2")])
    out = _stock_out("orders")
    stock_import.convert(export, PEOPLE, out)
    eq(stock_import.prove(export, out), [])
    with stock_store.rooted(out):
        orders = stock_store.load_orders()["orders"]
    eq([(o["reference"], o["person"]) for o in orders], [("PO-1", "acct-1"), ("PO-2", "acct-1")],
       "lines placed together a second apart are one order")
    eq([(l["item_id"], l["qty"], l["received"]) for l in orders[0]["lines"]], [(3, 5, 3), (7, 2, 2)],
       "the newest order awaits first; what the older one is not awaiting was received")
    eq([(l["item_id"], l["qty"], l["received"]) for l in orders[1]["lines"]], [(3, 6, 0)])

@test
def t_stock_on_order_without_an_ordered_line_becomes_ordered_before_the_move():
    export = _stock_export_with_orders({3: 4}, [
        ("2026-09-01T10:00:00", "Glass|Blue|20|", "ordered 5 from Invented Glass Co · ref PO-1"),
        ("2026-09-02T10:00:00", "Glass|Blue|20|", "cleared outstanding order")])
    out = _stock_out("before-move")
    stock_import.convert(export, PEOPLE, out)
    eq(stock_import.prove(export, out), [])
    with stock_store.rooted(out):
        orders = stock_store.load_orders()["orders"]
    eq([(o["before_move"], o["supplier"], [(l["item_id"], l["qty"], l["received"]) for l in o["lines"]])
        for o in orders], [(True, "Invented Glass Co", [(3, 4, 0)])],
       "a cleared order awaits nothing; what is on order with no line left is ordered before the move")

@test
def t_the_stock_proof_checks_outstanding_orders_match_on_order():
    export = _stock_export_with_orders({3: 6}, [
        ("2026-09-08T10:00:00", "Glass|Blue|20|", "ordered 6 from Invented Glass Co · ref PO-2")])
    out = _stock_out("orders-proof")
    stock_import.convert(export, PEOPLE, out)
    with stock_store.rooted(out):
        doc = stock_store.load_orders()
        doc["orders"][0]["lines"][0]["received"] = 1
        stock_store.write_orders(doc)
    found = stock_import.prove(export, out)
    eq(len(found), 1, found)
    ok("orders" in found[0] and "6" in found[0] and "5" in found[0], found[0])
