# ---- Stock in Reactor: stock backups and the nightly job (plan 2a) -------------
# A stock backup holds every field of every line, the suppliers and the
# settings (flaw 4); a restore never removes history and keeps the glass
# used since and the orders placed since. The nightly snapshot runs once a
# London day. Invented data only.

from gizmo import stock_backups

def _stock_backup(op, **body):
    r = post("/api/stock/backups", dict(body, op=op))
    return r, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {})

def _stock_with_details():
    _stock_live(items=[_stock_item(3, "Glass|Blue|20|", current=6, used=4, reorder_point=10, reorder_qty=30,
                                   barcode="TEST-CODE-3", supplier="Invented Glass Co", unit_cost_gbp=1.25)])
    post("/api/stock/suppliers", {"op": "save", "supplier": "Invented Glass Co", "email": "orders@example.com",
                                  "lead_days": 7})
    post("/api/stock/overview", {"op": "save_settings", "low_stock_days": 30})

@test
def t_a_stock_backup_holds_every_field_suppliers_and_settings():
    _stock_with_details()
    r, d = _stock_backup("make")
    eq(r.status_code, 200, r.text)
    b = stock_store.list_backups()[-1]
    eq(b["format"], "stock-1")
    line = b["items"][0]
    eq((line["barcode"], line["reorder_point"], line["reorder_qty"]), ("TEST-CODE-3", 10, 30), "every field")
    eq(b["suppliers"][0]["lead_days"], 7)
    eq(b["settings"]["meta"]["low_stock_days"], "30")
    eq([x["id"] for x in _stock_backup("list")[1]["backups"]], [b["id"]])
    ok("items" not in _stock_backup("list")[1]["backups"][0], "the list is light")

@test
def t_restoring_stock_writes_a_line_per_changed_field_and_keeps_history():
    _stock_with_details()
    bid = _stock_backup("make")[1]["id"]
    post("/api/stock/sheet", {"op": "edit", "id": 3, "changes": {"current": 9, "barcode": "NEW", "reorder_point": 2}})
    before = len(stock_store.read_history())
    r, d = _stock_backup("restore", id=bid)
    eq(r.status_code, 200, r.text)
    it = stock_store.load_items()["items"]["3"]
    eq((it["current"], it["barcode"], it["reorder_point"]), (6, "TEST-CODE-3", 10), "everything the backup holds")
    rows = stock_store.read_history()
    ok(len(rows) > before, "the history only grows")
    eq(sorted(h["field"] for h in rows if h["action"] == "restore" and h["field"] in ("current", "barcode", "reorder_point")),
       ["barcode", "current", "reorder_point"], "a line per field put back")
    ok(d["safety_backup_id"] > bid, "a safety backup first")

@test
def t_restoring_stock_reapplies_bookings_made_since():
    _stock_with_details()
    bid = _stock_backup("make")[1]["id"]
    doc = stock_store.load_items()
    doc["items"]["3"]["current"], doc["items"]["3"]["used"] = 4, 6        # glass used for one order since
    stock_store.write_items(doc)
    bridge = stock_store.load_bridge()
    bridge["bookings"].append({"id": 1, "order_id": "1001", "order_name": "#1001", "at": stock.now_iso(),
                               "lines": [{"item_id": 3, "item_key": "Glass|Blue|20|", "qty": 2, "current_delta": 2,
                                          "used_delta": 2}]})
    stock_store.write_bridge(bridge)
    r, d = _stock_backup("restore", id=bid)
    eq(r.status_code, 200, r.text)
    eq(d["reapplied"], 1)
    it = stock_store.load_items()["items"]["3"]
    eq((it["current"], it["used"]), (4, 6), "neither forgotten nor counted twice")

@test
def t_restoring_stock_keeps_orders_placed_since():
    _stock_with_details()
    bid = _stock_backup("make")[1]["id"]
    post("/api/stock/orders", {"op": "place", "supplier": "Invented Glass Co", "lines": [{"id": 3, "qty": 5}]})
    _stock_backup("restore", id=bid)
    eq(stock_store.load_items()["items"]["3"]["on_order"], 5, "the order placed since still awaited")

@test
def t_only_the_master_restores_stock():
    _stock_with_details()
    bid = _stock_backup("make")[1]["id"]
    try:
        stock_backups.restore("u-not-the-master", bid)
        ok(False, "only the master may restore")
    except stock.Refused as e:
        eq(e.status, 403)

@test
def t_an_old_encrypted_stock_backup_downloads_but_is_not_restored():
    _stock_with_details()
    stock_store.write_backup({"id": 1, "at": "2026-05-01T00:00:00+00:00", "filename": "stock-20260501-000000.json.enc",
                              "size_bytes": 15, "item_count": 1, "format": "legacy-fernet",
                              "token": base64.b64encode(b"gAAAAA-invented").decode()})
    r = post("/api/stock/backups", {"op": "download", "id": 1})
    eq(r.status_code, 200, r.text)
    eq(r.content, b"gAAAAA-invented", "the encrypted file as it was")
    ok("stock-20260501-000000.json.enc" in r.headers.get("content-disposition", ""))
    r, d = _stock_backup("restore", id=1)
    eq(r.status_code, 400, r.text)
    ok("archive" in d["error"], d["error"])

@test
def t_the_nightly_stock_snapshot_runs_once_a_london_day():
    from datetime import datetime as _dt
    _stock_with_details()
    with open(stock_store.STOCK_SNAPSHOTS_CHANGES_PREFIX + "2026-05-01.jsonl", "w") as fh:
        fh.write("")
    at = lambda s: _dt.fromisoformat(s)
    ok(stock_backups.nightly_tick(at("2026-06-30T23:30:00+00:00")), "half past midnight in London: the first of July")
    ok(not stock_backups.nightly_tick(at("2026-06-30T23:45:00+00:00")), "once")
    ok(not stock_backups.nightly_tick(at("2026-07-01T22:00:00+00:00")), "still the first of July in London")
    ok(stock_backups.nightly_tick(at("2026-07-01T23:30:00+00:00")), "the second")
    eq([s["reason"] for s in stock_store.read_snapshots()].count("scheduled"), 2)
    ok(not os.path.exists(stock_store.STOCK_SNAPSHOTS_CHANGES_PREFIX + "2026-05-01.jsonl"),
       "change snapshots older than 30 days are removed")
    eq(len([b for b in stock_store.list_backups() if b["format"] == "stock-1"]), 2, "a backup each night")

@test
def t_a_missed_stock_night_is_caught_up_once():
    from datetime import datetime as _dt
    _stock_with_details()
    stock_backups.nightly_tick(_dt.fromisoformat("2026-07-01T01:00:00+00:00"))
    stock_backups.nightly_tick(_dt.fromisoformat("2026-07-04T01:00:00+00:00"))
    eq([s["reason"] for s in stock_store.read_snapshots()].count("scheduled"), 2, "one for the days missed, not three")

@test
def t_stock_backups_are_kept_by_count_and_age():
    _stock_with_details()
    for n in range(1, 36):
        stock_store.write_backup({"id": n, "at": "2026-09-%02dT00:00:00+00:00" % (1 + n // 2), "filename": "f",
                                  "size_bytes": 1, "item_count": 0, "format": "stock-1", "items": []})
    stock_store.write_backup({"id": 36, "at": "2026-01-01T00:00:00+00:00", "filename": "old.json.enc", "size_bytes": 1,
                              "item_count": 0, "format": "legacy-fernet", "token": "YQ=="})
    _stock_backup("make")
    kept = stock_store.list_backups()
    eq(len([b for b in kept if b["format"] == "stock-1"]), 30, "thirty newest kept once older than a week")
    ok(any(b["format"] == "legacy-fernet" for b in kept), "the stock app's own backups are kept as an archive")
    ok(not any(b["id"] in (1, 2, 3, 4, 5, 6) for b in kept), "the oldest went")

@test
def t_the_nightly_stock_job_waits_for_the_move():
    from datetime import datetime as _dt
    _stock_live(live=False)
    ok(not stock_backups.nightly_tick(_dt.fromisoformat("2026-07-01T01:00:00+00:00")))
    eq(stock_store.read_snapshots(), [])

# ---- the final review's findings, pinned ---------------------------------------------

@test
def t_no_stock_backup_is_made_before_the_move():
    _stock_live(live=False)
    r, d = _stock_backup("make")
    eq(r.status_code, 409, r.text)
    eq(glob.glob(SCRATCH + "/stock_backup_*"), [], "nothing written that could meet the converted backups")

@test
def t_stock_backups_are_owner_only():
    """They hold the supplier contacts, which are kept owner-only."""
    _stock_with_details()
    _stock_backup("make")
    paths = glob.glob(SCRATCH + "/stock_backup_*")
    ok(paths, "a backup was written")
    eq({os.stat(p).st_mode & 0o777 for p in paths}, {0o600})

def _stock_booked(order_id, take, line=3):
    """A production booking as the link records it, and its glass taken."""
    bridge = stock_store.load_bridge()
    bridge["bookings"] = [b for b in bridge["bookings"] if b["order_id"] != order_id]
    if take:
        bridge["bookings"].append({"id": len(bridge["bookings"]) + 1, "order_id": order_id, "order_name": "#" + order_id,
                                   "at": stock.now_iso(), "lines": [{"item_id": line, "item_key": "Glass|Blue|20|",
                                                                     "qty": take, "current_delta": take, "used_delta": take}]})
    stock_store.write_bridge(bridge)

def _stock_figures_now(line="3"):
    it = stock_store.load_items()["items"][line]
    return it["current"], it["used"]

@test
def t_restoring_stock_counts_a_rebooked_order_once():
    _stock_live(items=[_stock_item(3, "Glass|Blue|20|", current=10, used=0)])
    _stock_booked("1001", 2)
    doc = stock_store.load_items(); doc["items"]["3"].update(current=8, used=2); stock_store.write_items(doc)
    bid = _stock_backup("make")[1]["id"]
    _stock_booked("1001", 3)                                  # marked made again: 3, replacing the 2
    doc = stock_store.load_items(); doc["items"]["3"].update(current=7, used=3); stock_store.write_items(doc)
    eq(_stock_backup("restore", id=bid)[0].status_code, 200)
    eq(_stock_figures_now(), (7, 3), "the order's glass counted once, at its latest")

@test
def t_restoring_stock_takes_back_an_order_unmade_since():
    _stock_live(items=[_stock_item(3, "Glass|Blue|20|", current=10, used=0)])
    _stock_booked("1002", 2)
    doc = stock_store.load_items(); doc["items"]["3"].update(current=8, used=2); stock_store.write_items(doc)
    bid = _stock_backup("make")[1]["id"]
    _stock_booked("1002", 0)                                  # un-made since: its glass went back
    doc = stock_store.load_items(); doc["items"]["3"].update(current=10, used=0); stock_store.write_items(doc)
    eq(_stock_backup("restore", id=bid)[0].status_code, 200)
    eq(_stock_figures_now(), (10, 0), "not counted as used")

@test
def t_a_refused_stock_restore_writes_nothing():
    _stock_with_details()
    bid = _stock_backup("make")[1]["id"]
    post("/api/stock/sheet", {"op": "edit", "id": 3, "changes": {"size": "21"}})
    post("/api/stock/sheet", {"op": "new", "fields": {"category": "Glass", "sub_category": "Blue", "size": "20"}})
    backups, rows = len(stock_store.list_backups()), len(stock_store.read_history())
    r, d = _stock_backup("restore", id=bid)
    eq(r.status_code, 409, r.text)
    eq((len(stock_store.list_backups()), len(stock_store.read_history())), (backups, rows),
       "no safety backup, no history line: nothing")

@test
def t_a_failed_nightly_stock_backup_is_retried_and_reported():
    from datetime import datetime as _dt
    _stock_with_details()
    real = stock_backups.make_backup
    def broken(who):
        raise OSError("the disk is full")
    stock_backups.make_backup = broken
    try:
        stock_backups.nightly_tick(_dt.fromisoformat("2026-07-01T01:00:00+00:00"))
    finally:
        stock_backups.make_backup = real
    failed = [a for a in stock_store.load_alerts()["alerts"] if a["kind"] == "job_fail"]
    eq([a["severity"] for a in failed], ["critical"], "the failure is said, on the warnings")
    ok(stock_backups.nightly_tick(_dt.fromisoformat("2026-07-01T01:15:00+00:00")), "the next tick tries the backup again")
    eq(len([b for b in stock_store.list_backups() if b["format"] == "stock-1"]), 1, "and it is made")
    eq([s["reason"] for s in stock_store.read_snapshots()].count("scheduled"), 1, "the snapshot is not taken twice")
