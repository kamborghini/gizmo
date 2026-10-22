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
    eq(len(names), 11, "every stock path")
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
