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
