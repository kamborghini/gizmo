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
