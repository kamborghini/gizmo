# ---- Stock in Reactor: the screens (plan 3) --------------------------------------
# What the Stock tab's screens need from the server: the tab, opt in and shown
# only once the stock sheet has moved in, and the reads the screens make that
# no route gave before. Invented data only.

@test
def t_the_stock_tab_is_opt_in_and_waits_for_the_move():
    ok("stock" in team.TAB_KEYS and "stock" in team.OPT_IN_TABS, "an opt-in tab")
    ok("stock" not in team.DEFAULT_TABS, "nobody is handed it by having an account")
    ok("stock" in layouts.LAYOUT_VIEWS, "its layout can be kept")
    ensure_auth()
    _stock_live(live=False)
    eq(post("/api/auth/state", {}).json()["me"].get("stock_live"), False, "before the move")
    _stock_live()
    eq(post("/api/auth/state", {}).json()["me"].get("stock_live"), True, "once moved in")

@test
def t_the_stock_list_says_which_glass_is_mono_and_hm():
    _stock_live()
    eq(post("/api/stock/sheet", {"op": "list"}).json().get("glass_families"), {}, "none set before the move writes them")
    doc = stock_store.load_settings()
    doc["glass_families"] = {"mono": "Clear Etch", "hm": "Heavy Matt"}
    stock_store.write_settings(doc)
    eq(post("/api/stock/sheet", {"op": "list"}).json()["glass_families"], {"mono": "Clear Etch", "hm": "Heavy Matt"},
       "the stock list groups its glass by them")

@test
def t_a_stock_order_names_who_placed_it():
    from gizmo import stock_orders
    _stock_live()
    ensure_auth()
    stock_orders.place(APP_AUTH["master"], "Invented Glass Co", "PO-1", "GBP", [{"id": 3, "qty": 5}])
    doc = stock_store.load_orders()
    doc["orders"].append({"id": 99, "supplier": "Invented Glass Co", "reference": "", "currency": "", "at": "2026-09-01T09:00:00+00:00",
                          "by": "someone", "person": None, "before_move": True,
                          "lines": [{"item_id": 7, "qty": 2, "received": 0, "cleared": 0}]})
    stock_store.write_orders(doc)
    shown = {o["reference"] or o["id"]: o for o in post("/api/stock/orders", {"op": "list"}).json()["orders"]}
    eq(shown["PO-1"]["who"], team._team_name(APP_AUTH["master"]), "by the account's name")
    eq(shown[99]["who"], "", "an order from before the move has no account to name")

@test
def t_a_phone_count_of_a_line_that_moved_since_is_refused():
    """Counts are kept on the phone across reloads, so a count begun before a
    delivery would put the shelf back to before it. Each count says what the
    shelf showed when it began; a line someone changed since is refused by
    name, with its figure now, and nothing of that save is written. A count
    that says nothing is taken as before."""
    _stock_live()
    r, d = _stock("counts", counts=[{"id": 3, "current": 5, "seen": 6}, {"id": 9, "current": 10, "seen": 20}])
    eq(r.status_code, 409, r.text)
    ok("Red 30" in d["error"] and "now 12" in d["error"] and "Blue 20" not in d["error"], d["error"])
    eq(stock_store.load_items()["items"]["3"]["current"], 6, "nothing of it written")
    eq(stock_store.read_history(), [], "and nothing recorded")
    r, d = _stock("counts", counts=[{"id": 3, "current": 5, "seen": 6}, {"id": 9, "current": 10, "seen": 12}])
    eq(r.status_code, 200, r.text)
    eq(d["saved"], 2, "counts that began from the shelf as it is are saved")
    r, d = _stock("counts", counts=[{"id": 7, "current": 1}])
    eq((r.status_code, d.get("saved")), (200, 1), "a count that says nothing is taken as before")
