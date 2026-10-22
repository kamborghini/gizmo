# ---- Stock in Reactor: the sheet, served (plan 2a) ---------------------------
# The stock sheet's own work in Reactor: every change lands with its history
# line, under one lock, through a journal a crash cannot split. Invented data
# only: the repository is public.

from gizmo import stock

def _stock_live(items=None, live=True):
    """A stock sheet that has moved in: invented lines, an open quarter."""
    _stock_clean()
    items = items or [_stock_item(3, "Glass|Blue|20|", start=10, used=4, current=6, unit_cost_gbp=1.25,
                                  reorder_point=10, supplier="Invented Glass Co"),
                      _stock_item(7, "Glass|Blue|20||#2", start=5, current=2, unit_cost_gbp=2.0),
                      _stock_item(9, "Glass|Red|30|", current=12, used=30, unit_cost_gbp=0.5)]
    stock_store.write_items({"items": {str(i["id"]): i for i in items}, "next_id": max(i["id"] for i in items) + 1})
    stock_store.write_periods({"periods": [{"id": 1, "label": "Quarter one", "opened_at": "2026-07-01T00:00:00+00:00",
                                            "closed_at": None, "closing_value": 0.0, "closing_units": 0,
                                            "closing_skus": 0, "closing_used_value": 0.0, "note": "",
                                            "closing_data": None}], "next_id": 2})
    settings = {"meta": {"low_stock_days": "21"}}
    if live:
        settings["live_since"] = "2026-10-01T00:00:00+00:00"
    stock_store.write_settings(settings)
    return items

def _stock_change(field, value, item_id="3"):
    """A change to one field of one line, made the way every stock operation makes one."""
    with stock._lock:
        st = stock.state()
        old = st["items"]["items"][item_id][field]
        st["items"]["items"][item_id][field] = value
        row = stock.history_row(stock.actor("u-test"), "update", item_key=st["items"]["items"][item_id]["key"],
                                field=field, old=str(old), new=str(value), detail="manual edit")
        return stock.commit(st, changed={"items"}, history=[row])

def _stock_crash_in(name, fn):
    """Run fn with stock_store.<name> failing once, as if the process died there."""
    real = getattr(stock_store, name)
    def crash(*a, **k):
        raise OSError("the disk went away")
    setattr(stock_store, name, crash)
    try:
        fn()
        ok(False, "the crash should have stopped the change")
    except OSError:
        pass
    finally:
        setattr(stock_store, name, real)

@test
def t_a_stock_change_and_its_history_line_land_together():
    _stock_live()
    _stock_crash_in("write_items", lambda: _stock_change("current", 9))
    eq(stock.state()["items"]["items"]["3"]["current"], 9, "the change is finished by the next read")
    eq([(r["field"], r["new_value"]) for r in stock_store.read_history()], [("current", "9")], "its line, once")
    eq(stock_store.load_journal(), None, "and the journal is gone")

@test
def t_a_stock_crash_before_any_append_is_finished_on_recovery():
    _stock_live()
    _stock_crash_in("append_history", lambda: _stock_change("current", 8))
    eq(stock_store.read_history(), [], "nothing appended yet")
    ok(stock.recover(), "the journal is found and finished")
    eq(stock_store.load_items()["items"]["3"]["current"], 8)
    eq(len(stock_store.read_history()), 1)

@test
def t_a_stock_crash_after_every_write_is_not_applied_twice():
    _stock_live()
    _stock_crash_in("clear_journal", lambda: _stock_change("current", 7))
    ok(stock_store.load_journal(), "the journal was left behind")
    ok(stock.recover(), "and is finished")
    eq(len(stock_store.read_history()), 1, "the line is not appended a second time")
    eq(stock_store.load_items()["items"]["3"]["current"], 7)
    eq(stock_store.load_journal(), None)

@test
def t_two_stock_changes_at_once_both_land():
    import threading as _threading
    _stock_live()
    def run(field):
        for n in range(1, 51):
            _stock_change(field, n)
    threads = [_threading.Thread(target=run, args=(f,)) for f in ("current", "used")]
    [t.start() for t in threads]
    [t.join() for t in threads]
    line = stock.state()["items"]["items"]["3"]
    eq((line["current"], line["used"]), (50, 50), "neither person's last value is lost")
    ids = [r["id"] for r in stock_store.read_history()]
    eq(len(ids), 100)
    eq(ids, sorted(set(ids)), "every line numbered once, in order")

@test
def t_nothing_is_written_to_stock_before_the_move():
    _stock_live(live=False)
    try:
        _stock_change("current", 1)
        ok(False, "a write before the move must be refused")
    except stock.Refused as e:
        eq(e.status, 409)
        ok("not moved" in e.words, e.words)
    eq(stock_store.read_history(), [])
    eq(stock_store.load_items()["items"]["3"]["current"], 6)

# ---- snapshots, warnings raised once, the history index ------------------------

def _stock_snap(**line):
    """Set fields on line 3, then take a snapshot the way every change does."""
    with stock._lock:
        st = stock.state()
        st["items"]["items"]["3"].update(line)
        snap = stock.take_snapshot(st, "edit", stock.actor("u-test"), "a test change")
        stock.commit(st, changed={"items", "alerts"}, snapshot=snap)
    # The warnings about lines: a swing in the whole stock's value is raised as before.
    return [(a["kind"], a["item_key"]) for a in stock_store.load_alerts()["alerts"] if a["item_key"]]

@test
def t_a_stock_warning_is_raised_once_until_it_changes():
    _stock_live()
    for _ in range(3):
        kinds = _stock_snap(current=10, used=90)            # ten days of cover, three times
    eq(kinds, [("low_stock", "Glass|Blue|20|")], "once, however many snapshots")
    kinds = _stock_snap(current=0)
    eq([k for k, _ in kinds], ["low_stock", "stockout"], "a different warning is raised")
    _stock_snap(current=50)                                  # recovered above its level
    kinds = _stock_snap(current=10)
    eq([k for k, _ in kinds], ["low_stock", "stockout", "low_stock"], "and falling again raises it again")

@test
def t_stock_bookings_alone_never_raise_a_warning_again():
    _stock_live()
    for current in range(15, 5, -1):                         # a booking a day, still low
        kinds = _stock_snap(current=current, used=90)
    eq(len(kinds), 1, "one warning, not ten")
    eq(len(stock_store.read_snapshots()), 10, "but a snapshot every time")

@test
def t_stock_alerts_past_the_cap_are_archived_first():
    _stock_live()
    old = [{"id": n, "at": "2026-09-01T00:00:00+00:00", "kind": "low_stock", "severity": "warning",
            "message": "old", "item_key": "Old|%d|" % n, "dismissed": True, "dismissed_by": "Someone"}
           for n in range(1, 1006)]
    stock_store.write_alerts({"alerts": old, "next_id": 1006})
    _stock_snap(current=10, used=90)
    doc = stock_store.load_alerts()
    eq(len(doc["alerts"]), 1000)
    eq(doc["alerts"][-1]["id"], 1006, "the new warning is kept")
    archived = stock_store._read_lines(stock_store.STOCK_ALERTS_ARCHIVE_PATH)
    eq([a["id"] for a in archived], [1, 2, 3, 4, 5, 6], "the oldest, kept before they left")

def _stock_old_rows():
    """History rows as the stock app wrote them: no zone on the time, its own
    names, its own dashes."""
    return [
        {"at": "2026-05-01T10:00:00", "user": "gizmo", "action": "use", "item_key": "Glass|Blue|20|",
         "field": "current", "old_value": "8", "new_value": "7", "detail": "made #1001 · used 1", "person": None},
        {"at": "2026-05-01T11:00:00", "user": "someone", "action": "update", "item_key": "Glass|Blue|20|",
         "field": "used", "old_value": "4", "new_value": "6", "detail": "counted down 2 — recorded as usage",
         "person": "acct-1"},
        {"at": "2026-05-02T09:00:00+00:00", "user": "someone", "action": "receive", "item_key": "Glass|Red|30|",
         "field": "current", "old_value": "7", "new_value": "12", "detail": "received 5 · inv INV-10 · 2026-05-01",
         "person": "acct-1"},
    ]

@test
def t_the_stock_history_index_finds_rows_by_item_invoice_and_action():
    _stock_live()
    stock_store.append_history(_stock_old_rows())
    idx = stock.history_index()
    eq(len(idx.by_key["Glass|Blue|20|"]), 2)
    eq([idx.rows[i]["action"] for i in idx.by_invoice["inv-10"]], ["receive"], "found by its invoice, any case")
    ok("inv-1" not in idx.by_invoice, "INV-1 is not INV-10")
    eq(len(idx.by_action["use"]), 1)
    eq(stock.detail_invoice("received 5 · inv INV-10 · 2026-05-01"), "INV-10")
    eq(stock.detail_invoice("accepted delivery · 2 lines · 9 units · inv A 7"), "A 7")

@test
def t_the_stock_history_index_reads_on_and_is_forgotten_on_restore():
    _stock_live()
    stock_store.append_history(_stock_old_rows())
    idx = stock.history_index()
    reads = idx.full_reads
    _stock_change("current", 5)
    _stock_change("current", 4)
    again = stock.history_index()
    ok(again is idx, "the same index, read on")
    eq((len(again.rows), again.full_reads), (5, reads), "two more rows without reading the file again")
    jsonstore._drop_memory_stores()
    ok(stock.history_index() is not idx, "a restore makes it read the file afresh")

# ---- the stock list: list, edit, counts, new lines -------------------------------

def _stock(op, **body):
    r = post("/api/stock/sheet", dict(body, op=op))
    return r, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {})

@test
def t_the_stock_list_comes_with_its_figures():
    _stock_live()
    r, d = _stock("list")
    eq(r.status_code, 200, r.text)
    eq([i["id"] for i in d["items"]], [3, 7, 9], "by category, then colour")
    eq(d["summary"]["headline"]["active_stock_value_gbp"], 17.5)
    ok(d["live"], "and whether the stock sheet has moved in")

@test
def t_stock_edit_writes_a_history_line_per_field():
    _stock_live()
    r, d = _stock("edit", id=3, changes={"current": 8, "reorder_point": 12}, seen={"current": 6, "reorder_point": 10})
    eq(r.status_code, 200, r.text)
    eq(d["applied"], 2)
    rows = stock_store.read_history()
    eq([(h["field"], h["old_value"], h["new_value"], h["detail"]) for h in rows],
       [("current", "6", "8", "manual edit"), ("reorder_point", "10", "12", "manual edit")])
    eq({h["person"] for h in rows}, {APP_AUTH["master"]}, "recorded under the Reactor account")
    eq(len(stock_store.read_snapshots()), 1, "one snapshot for the change")

@test
def t_a_stock_edit_refuses_a_figure_someone_else_changed():
    _stock_live()
    r, d = _stock("edit", id=3, changes={"current": 9}, seen={"current": 5})
    eq(r.status_code, 409, r.text)
    eq(d["item"]["current"], 6, "the line as it now is, to look at again")
    ok("Current" in d["error"], d["error"])
    eq(stock_store.read_history(), [], "nothing written")

@test
def t_a_stock_count_down_is_recorded_as_usage():
    _stock_live()
    r, d = _stock("edit", id=3, changes={"current": 3}, as_count=True)
    eq(r.status_code, 200, r.text)
    eq((d["item"]["current"], d["item"]["used"]), (3, 7))
    eq([(h["field"], h["detail"]) for h in stock_store.read_history()],
       [("current", "counted"), ("used", "counted down 3, recorded as usage")])

@test
def t_a_stock_line_with_a_duplicate_key_can_be_edited():
    _stock_live()
    r, d = _stock("edit", id=7, changes={"current": 1})
    eq(r.status_code, 200, r.text)
    eq(d["item"]["key"], "Glass|Blue|20||#2", "the key is left as it is")

@test
def t_renaming_a_stock_line_writes_its_key_line():
    _stock_live()
    r, d = _stock("edit", id=9, changes={"size": "31"})
    eq(r.status_code, 200, r.text)
    eq(d["item"]["key"], "Glass|Red|31|")
    key_rows = [h for h in stock_store.read_history() if h["field"] == "key"]
    eq([(h["old_value"], h["new_value"], h["detail"]) for h in key_rows], [("Glass|Red|30|", "Glass|Red|31|", "renamed")])
    r, d = _stock("edit", id=9, changes={"sub_category": "Blue", "size": "20"})
    eq(r.status_code, 409, "another line holds that key")
    eq(stock_store.load_items()["items"]["9"]["key"], "Glass|Red|31|")

@test
def t_stock_counts_save_in_one_go_with_one_snapshot():
    _stock_live()
    r, d = _stock("counts", counts=[{"id": 3, "current": 5}, {"id": "7", "current": 1}, {"id": 9, "current": 10}])
    eq(r.status_code, 200, r.text)
    eq(d["saved"], 3)
    eq(len([h for h in stock_store.read_history() if h["field"] == "current"]), 3)
    eq(len(stock_store.read_snapshots()), 1, "one snapshot for the whole count")
    r, d = _stock("counts", counts=[{"id": 3, "current": 1}] * 501)
    eq(r.status_code, 400, "more than 500 counts at once")
    eq(stock_store.load_items()["items"]["3"]["current"], 5, "nothing of it written")

@test
def t_a_new_stock_line_takes_the_next_id():
    _stock_live()
    r, d = _stock("new", fields={"category": "Glass", "sub_category": "Amber", "size": "25", "current": 4,
                                  "unit_cost_gbp": 1.5})
    eq(r.status_code, 200, r.text)
    eq(d["item"]["id"], 10)
    eq(stock_store.load_items()["next_id"], 11)
    eq([h["action"] for h in stock_store.read_history()], ["create"])
    r, d = _stock("new", fields={"category": "Glass", "sub_category": "Amber", "size": "25"})
    eq(r.status_code, 409, "the same line twice")
    r, d = _stock("new", fields={"size": "25"})
    eq(r.status_code, 400, "a line needs a category")

@test
def t_stock_refuses_bad_numbers():
    _stock_live()
    for bad in (None, -1, 1e10, True, "lots"):
        r, d = _stock("edit", id=3, changes={"current": bad})
        eq(r.status_code, 400, repr(bad))
        ok("Current" in d.get("error", ""), d)
    eq(stock_store.read_history(), [], "nothing written")

@test
def t_stock_is_closed_to_an_account_without_the_tab():
    def go():
        _stock_live()
        _uid, session, _pw = ready_user("Stock Member", "stock.member")
        r = post_s(session, "/api/stock/sheet", {"op": "list"})
        eq(r.status_code, 403, r.text)
    with_accounts(go)

# ---- import and export in the sheet's own layout (flaw 5) ---------------------------

def _stock_sheet_lines():
    return [_stock_item(3, "Glass|Blue|20|", start=10, used=4, current=6, unit_cost_gbp=1.25, supplier="Invented Glass Co",
                        currency="GBP"),
            _stock_item(7, "Glass|Blue|20||#2", start=5, current=2, unit_cost_gbp=0.7865, currency="USD", unit_cost=1.01),
            _stock_item(9, "Glass|Red|30|=SUM(A1)", current=12, used=30, unit_cost_gbp=0.5, notes="=SUM(A1)"),
            _stock_item(11, "Glass|Grey|20|", current=3, unit_cost_gbp=4.0, written_off=True)]

def _stock_sheet_csv(rows):
    """A stock sheet as the shop's spreadsheet lays it out: a quarter label,
    a blank row, a header, then lines (19 columns, no written-off column)."""
    head = "Quarter one\n\nCategory,Colour,Size,Notes,Start,Received,Used,Current,UV,SV,CV,Unit Cost,Currency,Supplier,Unit GBP,P,D,I,Date\n"
    return head + "\n".join(",".join(str(c) for c in r) for r in rows) + "\nTotals,,,,1,1,1,1\n"

@test
def t_stock_export_then_import_changes_nothing():
    _stock_live(items=_stock_sheet_lines())
    r, d = _stock("export")
    eq(r.status_code, 200, r.text)
    eq(d["filename"], "stock_export.csv")
    r, d = _stock("import_preview", csv=d["csv"])
    eq(r.status_code, 200, r.text)
    eq((d["rows"], d["creates"], d["changes"]), (4, [], []), "export then import changes nothing")

@test
def t_the_stock_import_preview_names_every_field():
    _stock_live(items=_stock_sheet_lines())
    csv = _stock("export")[1]["csv"]
    lines = csv.split("\n")
    i = next(n for n, l in enumerate(lines) if l.startswith("Glass,Blue,20,,10"))
    cells = lines[i].split(",")
    cells[11], cells[12], cells[13], cells[19] = "2.5", "EUR", "Made Up Metals", "yes"
    lines[i] = ",".join(cells)
    r, d = _stock("import_preview", csv="\n".join(lines))
    eq(r.status_code, 200, r.text)
    eq(sorted(c["field"] for c in d["changes"] if c["id"] == 3), ["currency", "supplier", "unit_cost", "written_off"])

@test
def t_the_original_stock_sheet_still_imports():
    _stock_live(items=_stock_sheet_lines())
    sheet = _stock_sheet_csv([["Glass", "Blue", "20", "", 10, 0, 4, 6, "", "", "", "", "GBP", "Invented Glass Co", '"£1,062.72"'],
                              ["Film", "Clear", "A4", "Written off 2025", 2, 0, 0, 2, "", "", "", "", "", "", "3"]])
    r, d = _stock("import_preview", csv=sheet)
    eq(r.status_code, 200, r.text)
    eq([c["field"] for c in d["changes"] if c["id"] == 3], ["unit_cost_gbp"], "money read as the sheet writes it")
    eq(d["changes"][0]["to"], 1062.72)
    eq(d["creates"], [{"category": "Film", "sub_category": "Clear", "size": "A4", "written_off": True}],
       "written off read from the notes when the sheet has no column for it")
    r, d = _stock("import_apply", csv=sheet)
    eq(r.status_code, 200, r.text)
    eq((d["created"], d["updated_fields"]), (1, 1))
    eq(stock_store.load_items()["items"]["12"]["key"], "Film|Clear|A4|Written off 2025")

@test
def t_a_stock_import_is_all_or_nothing():
    _stock_live(items=_stock_sheet_lines())
    sheet = _stock_sheet_csv([["Glass", "Blue", "20", "", 10, 0, 4, 9],
                              ["Glass", "Red", "30", "=SUM(A1)", 1, 0, 0, -5]])
    r, d = _stock("import_apply", csv=sheet)
    eq(r.status_code, 400, r.text)
    ok("Current" in d["error"], d["error"])
    eq(stock_store.load_items()["items"]["3"]["current"], 6, "the good row was not written either")
    eq(stock_store.read_history(), [])
    r, d = _stock("import_preview", csv=_stock_sheet_csv([["Glass", "Pink", str(n), "", 0, 0, 0, 1] for n in range(5001)]))
    eq(r.status_code, 400, "more than 5,000 lines")
    ok("5,000" in d["error"], d["error"])
    r, d = _stock("import_preview", csv="Category,Size\nGlass,20\n")
    eq(r.status_code, 400, "not the stock sheet")
    ok("stock sheet" in d["error"], d["error"])

@test
def t_stock_export_guards_against_spreadsheet_formulas():
    _stock_live(items=_stock_sheet_lines())
    csv = _stock("export", ids=[9])[1]["csv"]
    ok(",'=SUM(A1)," in csv, csv)
    eq(len([l for l in csv.split("\n") if l.startswith("Glass")]), 1, "only the lines asked for")

# ---- the final review's findings, pinned ---------------------------------------------

@test
def t_a_stock_edit_carrying_its_unchanged_size_is_not_refused():
    """A page that sends the whole row sends the size unchanged; a line whose
    key carries "|#2" must still save."""
    _stock_live()
    r, d = _stock("edit", id=7, changes={"current": 1, "size": "20", "category": "Glass"})
    eq(r.status_code, 200, r.text)
    eq((d["item"]["current"], d["item"]["key"]), (1, "Glass|Blue|20||#2"))

@test
def t_importing_a_filtered_stock_export_writes_only_its_own_lines():
    """Two lines share a name ("|#2"); an export of the second, imported back,
    must never touch the first."""
    _stock_live(items=_stock_sheet_lines())
    csv = _stock("export", ids=[7])[1]["csv"]
    eq((_stock("import_preview", csv=csv)[1]["changes"]), [], "unchanged, it changes nothing")
    lines = csv.split("\n")
    i = next(n for n, l in enumerate(lines) if l.startswith("Glass,Blue,20,"))
    cells = lines[i].split(",")
    cells[7] = "5"                                    # its count
    lines[i] = ",".join(cells)
    d = _stock("import_preview", csv="\n".join(lines))[1]
    eq([(c["id"], c["field"], c["to"]) for c in d["changes"]], [(7, "current", 5)], "the line it came from")
    eq(_stock("import_apply", csv="\n".join(lines))[0].status_code, 200)
    items = stock_store.load_items()["items"]
    eq((items["7"]["current"], items["3"]["current"]), (5, 6), "and nothing else")

@test
def t_stock_import_reads_written_off_only_from_its_own_column():
    _stock_live(items=_stock_sheet_lines())
    sheet = ("Quarter one\n\nCategory,Colour,Size,Notes,Start,Received,Used,Current,UV,SV,CV,Unit Cost,Currency,"
             "Supplier,Unit GBP,P,D,I,Date,Comment\n"
             "Glass,Blue,20,,10,0,4,6,,,,,GBP,Invented Glass Co,1.25,,,,,yes\n")
    d = _stock("import_preview", csv=sheet)[1]
    eq([c["field"] for c in d["changes"] if c["id"] == 3], [], "a column headed Comment is not the written-off flag")
