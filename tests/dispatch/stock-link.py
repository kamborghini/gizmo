# ---- Stock in Reactor: the link moved in (plan 2b) -----------------------------
# The glass a Mark made consumes, booked in Reactor's own stock sheet by the
# stock app's own rules: a re-push replaces, a reversal gives back exactly
# what was taken, usage banked in a closed quarter stays there, lines it
# cannot place are parked for a ruling. Invented glass lines only.

from gizmo import stock_bridge

def _stock_glass(families=True):
    """Invented glass lines in the shapes the matching reads, and the glass
    Mono and HM lines are matched to, as the move writes it into the stock
    sheet's settings (the real names stay out of this public repository)."""
    def line(id, cat, sub, size, notes="", current=10):
        return _stock_item(id, "|".join((cat, sub, size, notes)), category=cat, sub_category=sub, size=size,
                           notes=notes, current=current)
    _stock_live(items=[line(21, "Glass", "Clear Etch", "15.9"), line(22, "Glass", "Clear Etch", "64.9"),
                       line(23, "Glass", "Heavy Matt", "20"), line(24, "Rings", "86", "64.9"),
                       line(25, "Glass", "Clear Etch", "20"), line(26, "Glass", "Clear Etch", "20", "Second batch"),
                       line(27, "Glass", "Blue", "20")])
    if families:
        doc = stock_store.load_settings()
        doc["glass_families"] = {"mono": "Clear Etch", "hm": "Heavy Matt"}
        stock_store.write_settings(doc)

def _stock_line(id):
    it = stock_store.load_items()["items"][str(id)]
    return it["current"], it["used"]

def _mono(size, qty, **more):
    return dict({"family": "Mono", "size": size, "qty": qty}, **more)

@test
def t_marking_made_books_stock_like_a_count_down():
    _stock_glass()
    eq(stock_bridge.book("u-test", "1001", "#1001", [_mono("16", 2)]),
       {"ok": True, "booked": 1, "units": 2, "parked": 0}, "16 books the 15.9 line, the only one near")
    eq(_stock_line(21), (8, 2))
    rows = stock_store.read_history()
    eq([(h["action"], h["detail"]) for h in rows],
       [("use", "made #1001 · used 2"), ("use", "made #1001 · 2 blank(s) across 1 item(s)")])
    eq(rows[0]["item_id"], 21)
    eq(len(stock_store.read_snapshots()), 1)

@test
def t_marking_stock_made_again_replaces_the_booking():
    _stock_glass()
    stock_bridge.book("u-test", "1001", "#1001", [_mono("16", 2)])
    stock_bridge.book("u-test", "1001", "#1001", [_mono("16", 3)])
    eq(_stock_line(21), (7, 3), "the latest booking, not both")
    eq([b["lines"][0]["qty"] for b in stock_store.load_bridge()["bookings"]], [3])

@test
def t_unmaking_stock_gives_back_exactly_what_it_took():
    _stock_glass()
    stock_bridge.book("u-test", "1001", "#1001", [_mono("16", 2)])
    eq(stock_bridge.reverse("u-test", "1001"), {"ok": True, "reversed": 2})
    eq(_stock_line(21), (10, 0))
    snaps = len(stock_store.read_snapshots())
    eq(stock_bridge.reverse("u-test", "1001"), {"ok": True, "reversed": 0}, "a second reversal finds nothing")
    eq(len(stock_store.read_snapshots()), snaps, "and writes nothing")

@test
def t_a_stock_booking_never_takes_the_shelf_below_nothing():
    _stock_glass()
    doc = stock_store.load_items(); doc["items"]["23"]["current"] = 1; stock_store.write_items(doc)
    stock_bridge.book("u-test", "1002", "#1002", [{"family": "HM", "size": "20", "qty": 3}])
    eq(_stock_line(23), (0, 3), "the shelf at nothing, the usage in full")
    ok("stock only had 1" in stock_store.read_history()[0]["detail"])

@test
def t_a_stock_booking_from_a_closed_quarter_keeps_its_usage_there():
    from gizmo import stock_quarters
    _stock_glass()
    stock_bridge.book("u-test", "1003", "#1003", [_mono("16", 2)])
    stock_quarters.close("u-test", "Quarter two")
    eq(_stock_line(21), (8, 0), "used rolled into the closed quarter")
    stock_bridge.book("u-test", "1003", "#1003", [_mono("16", 3)])
    eq(_stock_line(21), (7, 0), "the shelf moves, the banked usage is not counted again")
    stock_bridge.reverse("u-test", "1003")
    eq(_stock_line(21), (10, 0))

@test
def t_a_stock_glass_line_parks_when_its_glass_is_not_known():
    _stock_glass(families=False)
    r = stock_bridge.book("u-test", "1001", "#1001", [_mono("16", 2), {"family": "HM", "size": "20", "qty": 1},
                                                      {"family": "Ring", "size": "86", "qty": 1}])
    eq((r["booked"], r["parked"]), (1, 2), "Mono and HM wait for a ruling; a ring names its own line")
    eq(_stock_line(21), (10, 0), "nothing guessed")
    eq(stock_bridge.match(stock.state(), "Mono", "16"), None)

@test
def t_a_stock_line_with_a_note_is_parked_not_guessed():
    _stock_glass()
    r = stock_bridge.book("u-test", "1004", "#1004", [_mono("16", 1, note="review: size unclear"), _mono("16", "x"),
                                                      _mono("16", 0)])
    eq((r["booked"], r["parked"]), (0, 3))
    eq(sorted((p["note"], p["qty"]) for p in stock_store.load_bridge()["parked"]),
       [("quantity out of bounds", 0), ("review: size unclear", 1), ("unreadable quantity", 0)])
    eq(_stock_line(21), (10, 0), "nothing guessed")
    eq([b["order_id"] for b in stock_store.load_bridge()["bookings"]], ["1004"], "the booking is still kept")

@test
def t_a_bezelled_stock_order_books_its_glass_and_its_ring():
    _stock_glass()
    stock_bridge.book("u-test", "1005", "#1005", [_mono("64.9", 1), {"family": "Ring", "size": "86", "qty": 1}])
    eq((_stock_line(22), _stock_line(24)), ((9, 1), (9, 1)))

@test
def t_a_stock_ruling_is_remembered_for_mono_not_colour():
    _stock_glass()
    stock_bridge.book("u-test", "1006", "#1006", [{"family": "Colour", "size": "20", "qty": 1}])
    stock_bridge.book("u-test", "1007", "#1007", [_mono("17", 1)])
    eq(len(stock_store.load_bridge()["parked"]), 2, "a colour line and a size with no line park")
    eq(stock_bridge.map_line("u-test", "Mono|17", 25)["booked_units"], 1)
    eq(_stock_line(25), (9, 1))
    stock_bridge.book("u-test", "1008", "#1008", [_mono("17", 2)])
    eq(_stock_line(25), (7, 3), "the ruling is remembered for every Mono 17 after")
    colour = next(p for p in stock_store.load_bridge()["parked"] if p["alias"] == "Colour|20")
    stock_bridge.map_line("u-test", "Colour|20", 27, parked_id=colour["id"])
    eq(_stock_line(27), (9, 1))
    stock_bridge.book("u-test", "1009", "#1009", [{"family": "Colour", "size": "20", "qty": 1}])
    eq(_stock_line(27), (9, 1), "a colour ruling is never remembered")
    eq([a["alias"] for a in stock_store.load_bridge()["aliases"]], ["Mono|17"])
    eq(stock_bridge.reverse("u-test", "1007")["reversed"], 1, "a mapped line is reversed with its order")

@test
def t_a_stock_ruling_follows_its_line_through_a_rename():
    from gizmo import stock_sheet
    _stock_glass()
    stock_bridge.book("u-test", "1010", "#1010", [_mono("17", 1)])
    stock_bridge.map_line("u-test", "Mono|17", 25)
    stock_sheet.edit("u-test", 25, {"size": "20.1"}, {}, False)
    stock_bridge.book("u-test", "1011", "#1011", [_mono("17", 1)])
    eq(_stock_line(25), (8, 2), "the ruling found its line by id")

@test
def t_a_stock_day_sheet_books_only_the_difference():
    _stock_glass()
    stock_bridge.book("u-test", "1012", "#1012", [_mono("16", 3)])
    r = stock_bridge.usage_sheet("u-test", "2026-10-22", ["1012"], [
        {"family": "Mono", "size": "16", "estimated": 3, "final": 5},
        {"family": "Colour", "size": "20", "estimated": 1, "final": 1},
        {"family": "HM", "size": "20", "estimated": 1, "final": "x"}])
    eq([(x["status"], x.get("delta")) for x in r["results"]], [("adjusted", 2), ("no_item", None), ("bad_quantity", None)])
    eq(_stock_line(21), (5, 5))
    r = stock_bridge.usage_sheet("u-test", "2026-10-22", ["1012"], [{"family": "Mono", "size": "16", "final": 2}])
    eq(r["replaced"], True)
    eq(_stock_line(21), (8, 2), "the first sheet undone, then 2 against the 3 booked")
    try:
        stock_bridge.usage_sheet("u-test", "22/10/2026", [], [{"family": "Mono", "size": "16", "final": 1}])
        ok(False, "a day must be a date")
    except stock.Refused as e:
        eq(e.status, 400)

@test
def t_a_stock_day_sheet_sent_again_after_a_re_make_counts_the_day_once():
    _stock_glass()
    stock_bridge.book("u-test", "1014", "#1014", [_mono("16", 3)])
    stock_bridge.usage_sheet("u-test", "2026-10-22", ["1014"], [{"family": "Mono", "size": "16", "final": 5}])
    eq(_stock_line(21), (5, 5))
    stock_bridge.book("u-test", "1014", "#1014", [_mono("16", 4)])      # marked made again, with 4
    eq(_stock_line(21), (4, 6), "the re-make replaced its booking; the sheet's 2 still stands")
    r = stock_bridge.usage_sheet("u-test", "2026-10-22", ["1014"], [{"family": "Mono", "size": "16", "final": 5}])
    eq([(x["status"], x.get("delta")) for x in r["results"]], [("adjusted", 1)], "measured against the 4 booked now")
    eq(_stock_line(21), (5, 5), "the day's 5, once")

@test
def t_the_stock_mapping_shows_every_line_and_its_status():
    _stock_glass()
    real = stock_link._zeta_catalog_combos
    stock_link._zeta_catalog_combos = lambda: [{"family": f, "size": s} for f, s in
                                              (("Mono", "16"), ("Mono", "17"), ("HM", "20"), ("Colour", "20"), ("Ring", "86"))]
    try:
        stock_bridge.book("u-test", "1013", "#1013", [_mono("33", 1)])
        rows = {r["alias"]: r for r in stock_bridge.mapping()["rows"]}
        eq({a: r["status"] for a, r in rows.items()},
           {"Mono|16": "auto", "Mono|17": "unmapped", "HM|20": "auto", "Colour|20": "per_order", "Ring|86": "auto",
            "Mono|33": "unmapped"}, "the catalogue, and a parked line not in it")
        eq(rows["Mono|16"]["target"]["id"], 21)
        eq(rows["Mono|33"]["parked"], 1)
        stock_bridge.map_line("u-test", "Mono|17", 25)
        eq({r["alias"]: r["status"] for r in stock_bridge.mapping()["rows"]}["Mono|17"], "ruled")
        ok(any(o["id"] == 24 for o in stock_bridge.mapping()["options"]), "rings are offered with the glass")
    finally:
        stock_link._zeta_catalog_combos = real

# ---- the link sends in-process once the stock sheet has moved in ----------------

def _stock_link_world(live=True, app=False):
    """The glass lines, the stock app configured or not, the queue empty,
    and every order resolving to two Mono 16 blanks."""
    reset_dispatch(); reset_prod(); ensure_auth()
    _stock_glass()
    if not live:
        doc = stock_store.load_settings(); doc.pop("live_since", None); stock_store.write_settings(doc)
    saved = (stock_link.ZETA_URL, stock_link.ZETA_SYNC_TOKEN, stock_link._usage_lines, stock_link._zeta_send)
    stock_link.ZETA_URL, stock_link.ZETA_SYNC_TOKEN = ("https://zeta.test", "tok") if app else ("", "")
    stock_link._usage_lines = lambda o: [{"family": "Mono", "size": "16", "qty": 2}]
    try:
        os.remove(stock_link.ZETA_SYNC_PATH)
    except FileNotFoundError:
        pass
    def restore():
        (stock_link.ZETA_URL, stock_link.ZETA_SYNC_TOKEN, stock_link._usage_lines, stock_link._zeta_send) = saved
    return restore

def _stock_link_set_live():
    doc = stock_store.load_settings(); doc["live_since"] = stock.now_iso(); stock_store.write_settings(doc)

@test
def t_marked_made_books_in_reactor_once_the_stock_sheet_has_moved_in():
    restore = _stock_link_world()
    async def not_sent(*a, **k):
        raise AssertionError("sent to the stock app")
    stock_link._zeta_send = not_sent
    try:
        r = mark_made(12345, True)
        eq(r.status_code, 200, r.text)
        eq(r.json().get("stock_note"), "", "booked, nothing to say")
        eq(_stock_line(21), (8, 2))
        eq({h["person"] for h in stock_store.read_history() if h["action"] == "use"}, {APP_AUTH["master"]},
           "under the account that pressed Mark made")
        mark_made(12345, False)
        eq(_stock_line(21), (10, 0), "un-made, given back")
    finally:
        restore()

@test
def t_a_stock_booking_queued_before_the_switch_books_once_after_it():
    restore = _stock_link_world(live=False, app=True)
    calls = []
    async def down(op, order_id, order_name, lines):
        calls.append(op)
        raise RuntimeError("connection refused")
    stock_link._zeta_send = down
    try:
        ok("retrying" in mark_made(12345, True).json().get("stock_note", ""), "queued while the stock app is down")
        eq(calls, ["book"])
        _stock_link_set_live()                               # the switch
        run(stock_link._zeta_drain({}))
        eq(calls, ["book"], "never sent to the stock app after the switch")
        eq(_stock_line(21), (8, 2), "booked in Reactor, once")
        eq(stock_link._load_zeta_pending(), {}, "and the queue is empty")
        run(stock_link._zeta_drain({}))
        eq(_stock_line(21), (8, 2), "a second drain books nothing")
    finally:
        restore()

@test
def t_made_then_unmade_while_stock_cannot_be_written_ends_as_a_reversal():
    restore = _stock_link_world()
    real = (stock_bridge.book, stock_bridge.reverse)
    def refused(*a, **k):
        raise OSError("the store would not take it")
    stock_bridge.book = stock_bridge.reverse = refused
    try:
        note = mark_made(12345, True).json().get("stock_note", "")
        ok("stock sheet" in note and "retrying" in note, note)
        mark_made(12345, False)
        eq(stock_link._load_zeta_pending().get("12345", {}).get("op"), "reverse", "the latest intent")
    finally:
        stock_bridge.book, stock_bridge.reverse = real
    try:
        run(stock_link._zeta_drain({}))
        eq(_stock_line(21), (10, 0), "nothing booked: it was un-made")
        eq(stock_link._load_zeta_pending(), {})
    finally:
        restore()

@test
def t_the_stock_day_sheet_is_applied_in_reactor_once_moved_in():
    from zoneinfo import ZoneInfo
    import datetime as _dt
    restore = _stock_link_world()
    try:
        try:
            os.remove(stock_link.USAGE_SHEETS_PATH)
        except FileNotFoundError:
            pass
        eq(mark_made(12345, True).status_code, 200)
        today = _dt.datetime.now(ZoneInfo("Europe/London")).date().isoformat()
        day = post("/api/stock-usage", {"date": today}).json()
        ok(day.get("order_ids"), day)
        r = post("/api/stock-usage/send", {"date": today, "lines": [
            {"family": "Mono", "size": "16", "estimated": 2, "final": 3}]})
        eq(r.status_code, 200, r.text)
        eq([(x["status"], x["delta"]) for x in r.json()["result"]["results"]], [("adjusted", 1)])
        eq(_stock_line(21), (7, 3), "the day's figure, as the difference from the booking")
        ok(post("/api/stock-usage", {"date": today}).json().get("sent"), "the day says it was sent")
    finally:
        restore()

@test
def t_a_stock_day_sheet_refused_in_reactor_says_why():
    from zoneinfo import ZoneInfo
    import datetime as _dt
    restore = _stock_link_world()
    real = stock_bridge.usage_sheet
    try:
        try:
            os.remove(stock_link.USAGE_SHEETS_PATH)
        except FileNotFoundError:
            pass
        eq(mark_made(12345, True).status_code, 200)
        today = _dt.datetime.now(ZoneInfo("Europe/London")).date().isoformat()
        sheet = {"date": today, "lines": [{"family": "Mono", "size": "16", "estimated": 2, "final": 3}]}
        def changed(*a, **k):
            raise stock.Refused(409, "The stock sheet changed just now. Try again.")
        stock_bridge.usage_sheet = changed
        r = post("/api/stock-usage/send", sheet)
        eq((r.status_code, r.json().get("error")), (409, "The stock sheet changed just now. Try again."))
        def broken(*a, **k):
            raise OSError("the disk went away")
        stock_bridge.usage_sheet = broken
        r = post("/api/stock-usage/send", sheet)
        err = r.json().get("error", "")
        ok(r.status_code >= 500 and "stock sheet" in err and "stock app" not in err, (r.status_code, err))
        ok(not post("/api/stock-usage", {"date": today}).json().get("sent"), "nothing recorded as sent")
    finally:
        stock_bridge.usage_sheet = real
        restore()

@test
def t_the_glass_catalogue_is_not_sent_once_stock_has_moved_in():
    restore = _stock_link_world(app=True)
    try:
        run(stock_link._zeta_send_catalog())                # the suite refuses the network: a send would fail here
    finally:
        restore()

# ---- the matching panel's route ----------------------------------------------------

@test
def t_the_stock_matching_panel_reads_and_rules():
    _stock_glass()
    stock_bridge.book("u-test", "1020", "#1020", [_mono("17", 1)])
    r = post("/api/stock/mapping", {"op": "mapping"})
    eq(r.status_code, 200, r.text)
    ok(any(row["alias"] == "Mono|17" and row["parked"] == 1 for row in r.json()["rows"]), "the parked line is shown")
    parked = post("/api/stock/mapping", {"op": "parked"}).json()["parked"]
    eq([p["alias"] for p in parked], ["Mono|17"])
    r = post("/api/stock/mapping", {"op": "map", "alias": "Mono|17", "id": 25})
    eq((r.status_code, r.json().get("booked_units")), (200, 1), r.text)
    eq(post("/api/stock/mapping", {"op": "map", "alias": "Mono|18", "id": 999}).status_code, 404)
    stock_bridge.book("u-test", "1021", "#1021", [{"family": "Colour", "size": "20", "qty": 1}])
    stock_bridge.book("u-test", "1022", "#1022", [{"family": "Colour", "size": "20", "qty": 2}])
    r = post("/api/stock/mapping", {"op": "map", "alias": "Colour|20", "id": 27})
    eq(r.status_code, 400, "a colour ruling names its one parked line")
    eq(post("/api/stock/mapping", {"op": "map", "alias": "Colour|20", "id": 27, "parked_id": 999}).status_code, 400,
       "a parked line that is not there")
    eq(_stock_line(27), (10, 0), "nothing booked by either")
    first = next(p for p in post("/api/stock/mapping", {"op": "parked"}).json()["parked"] if p["order_name"] == "#1021")
    r = post("/api/stock/mapping", {"op": "map", "alias": "Colour|20", "id": 27, "parked_id": first["id"]})
    eq((r.status_code, r.json().get("booked_units")), (200, 1), r.text)
    eq([p["order_name"] for p in post("/api/stock/mapping", {"op": "parked"}).json()["parked"]], ["#1022"],
       "the other order's line still waits")
    doc = stock_store.load_items(); doc["items"]["26"]["written_off"] = True; stock_store.write_items(doc)
    eq(post("/api/stock/mapping", {"op": "map", "alias": "Mono|18", "id": 26}).status_code, 400, "a written-off line")
    doc = stock_store.load_settings(); doc.pop("live_since"); stock_store.write_settings(doc)
    eq(post("/api/stock/mapping", {"op": "map", "alias": "Mono|18", "id": 25}).status_code, 409, "nothing before the move")
