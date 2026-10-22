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
