# ---- Stock in Reactor: buying, orders and deliveries (plan 2a) ---------------
# Orders placed with suppliers are kept (flaw 7), each line's on-order always
# what its open orders still await; suppliers keep every detail when edited
# together (flaw 2). Invented suppliers and prices only.

def _stock_buy(path, op, **body):
    r = post("/api/stock/" + path, dict(body, op=op))
    return r, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {})

def _stock_outstanding(item_id):
    return sum(max(0, l["qty"] - l["received"] - l["cleared"])
               for o in stock_store.load_orders()["orders"] for l in o["lines"] if l["item_id"] == item_id)

@test
def t_placing_a_stock_order_keeps_it_and_adds_on_order():
    _stock_live()
    r, d = _stock_buy("orders", "place", supplier="Invented Glass Co", reference="PO-1", currency="GBP",
                      lines=[{"id": 3, "qty": 5, "unit_cost": 1.2}, {"id": 9, "qty": 2}, {"id": 3, "qty": 1}])
    eq(r.status_code, 200, r.text)
    eq((d["ordered"], d["units"]), (2, 8))
    items = stock_store.load_items()["items"]
    eq((items["3"]["on_order"], items["9"]["on_order"]), (6, 2))
    order = stock_store.load_orders()["orders"][0]
    eq([(l["item_id"], l["qty"], l["unit_cost"]) for l in order["lines"]], [(3, 6, 1.2), (9, 2, None)])
    eq((order["supplier"], order["reference"], order["person"]), ("Invented Glass Co", "PO-1", APP_AUTH["master"]))
    eq([h["detail"] for h in stock_store.read_history()],
       ["ordered 6 from Invented Glass Co · ref PO-1", "ordered 2 from Invented Glass Co · ref PO-1"])
    r, d = _stock_buy("orders", "place", supplier="X", lines=[{"id": 3, "qty": 1}] * 301)
    eq(r.status_code, 400, "more than 300 lines")
    r, d = _stock_buy("orders", "place", supplier="X", lines=[{"id": 3, "qty": 0}])
    eq(r.status_code, 400, "a quantity of nothing")

@test
def t_on_order_always_equals_what_stock_orders_still_await():
    _stock_live()
    _stock_buy("orders", "place", supplier="A", lines=[{"id": 3, "qty": 5}])
    _stock_buy("orders", "place", supplier="B", lines=[{"id": 3, "qty": 4}, {"id": 9, "qty": 2}])
    _stock_buy("orders", "clear", id=9)
    _stock_buy("orders", "place", supplier="B", lines=[{"id": 9, "qty": 3}])
    items = stock_store.load_items()["items"]
    eq((items["3"]["on_order"], _stock_outstanding(3)), (9, 9))
    eq((items["9"]["on_order"], _stock_outstanding(9)), (3, 3))

@test
def t_clearing_stock_on_order_closes_its_open_lines():
    _stock_live()
    _stock_buy("orders", "place", supplier="A", lines=[{"id": 3, "qty": 5}])
    r, d = _stock_buy("orders", "clear", id=3)
    eq(r.status_code, 200, r.text)
    eq(stock_store.load_items()["items"]["3"]["on_order"], 0)
    line = stock_store.load_orders()["orders"][0]["lines"][0]
    eq((line["cleared"], line["received"]), (5, 0))
    r, d = _stock_buy("orders", "list", open_only=True)
    eq(d["orders"], [], "no open order left")
    eq(stock_store.read_history()[-1]["detail"], "cleared outstanding order")
    r, d = _stock_buy("orders", "clear", id=3)
    eq(r.status_code, 400, "nothing on order")

@test
def t_the_stock_reorder_list_counts_what_is_on_order():
    _stock_live()
    listed = lambda: [l["key"] for s in _stock_buy("orders", "reorder")[1]["suppliers"] for l in s["items"]]
    eq(listed(), ["Glass|Blue|20|"], "6 on hand, its level 10")
    _stock_buy("orders", "place", supplier="A", lines=[{"id": 3, "qty": 4}])
    eq(listed(), ["Glass|Blue|20|"], "6 and 4 coming is still at its level")
    _stock_buy("orders", "place", supplier="A", lines=[{"id": 3, "qty": 1}])
    eq(listed(), [], "11 is above it")

@test
def t_stock_suggested_levels_use_each_suppliers_lead_time():
    _stock_live(items=[_stock_item(3, "Glass|Blue|20|", used=90, current=40, supplier="Invented Glass Co")])
    _stock_buy("suppliers", "save", supplier="Invented Glass Co", lead_days=7)
    s = _stock_buy("orders", "suggest")[1]["suggestions"][0]
    eq((s["lead_days"], s["cover_days"], s["reorder_point"]), (7, 21, 21))

@test
def t_stock_levels_apply_in_bulk_with_a_line_each():
    _stock_live()
    r, d = _stock_buy("orders", "levels", levels=[{"id": 3, "reorder_point": 12, "reorder_qty": 30},
                                                  {"id": 9, "reorder_point": 0, "reorder_qty": 0}])
    eq(r.status_code, 200, r.text)
    eq(d["updated"], 1, "the unchanged line writes nothing")
    eq([(h["field"], h["old_value"], h["new_value"], h["detail"]) for h in stock_store.read_history()],
       [("reorder_point", "10/0", "12/30", "reorder level set")])
    r, d = _stock_buy("orders", "levels", levels=[{"id": 3, "reorder_point": 1, "reorder_qty": 1}] * 1001)
    eq(r.status_code, 400, "more than 1,000 levels")

@test
def t_saving_all_stock_suppliers_keeps_delivery_time_and_minimum_order():
    _stock_live()
    _stock_buy("suppliers", "save", supplier="Invented Glass Co", email="orders@example.com", lead_days=7,
               min_order="100 per size")
    r, d = _stock_buy("suppliers", "save_all", contacts=[{"supplier": "Invented Glass Co", "email": "sales@example.com",
                                                          "subject": "Our order"}])
    eq(r.status_code, 200, r.text)
    c = stock_store.load_suppliers()["suppliers"][0]
    eq((c["email"], c["subject"], c["lead_days"], c["min_order"]), ("sales@example.com", "Our order", 7, "100 per size"))
    rows = _stock_buy("suppliers", "list")[1]["suppliers"]
    eq([(s["supplier"], s["has_contact"]) for s in rows], [("Invented Glass Co", True), ("Unknown", False)])
    r, d = _stock_buy("suppliers", "save", supplier="Invented Glass Co", email="not an address")
    eq(r.status_code, 400)
    r, d = _stock_buy("suppliers", "delete", supplier="Invented Glass Co")
    eq(r.status_code, 200, r.text)
    eq(stock_store.load_suppliers()["suppliers"], [])

@test
def t_a_stock_supplier_address_never_reaches_the_history():
    _stock_live()
    _stock_buy("suppliers", "save", supplier="Invented Glass Co", email="orders@example.com", cc="a@example.com; a@example.com")
    eq(stock_store.load_suppliers()["suppliers"][0]["cc"], "a@example.com", "copies cleaned and kept once")
    ok(not any("example.com" in json.dumps(h) for h in stock_store.read_history()), "no address in the history")
    eq(stock_store.read_history()[0]["detail"], "added email contact for Invented Glass Co")

# ---- receiving, matched to the order it fills ------------------------------------

def _stock_order_lines(item_id):
    return [(o["supplier"], l["received"], [r["qty"] for r in l["receipts"]])
            for o in stock_store.load_orders()["orders"] for l in o["lines"] if l["item_id"] == item_id]

@test
def t_receiving_stock_refuses_an_invoice_received_twice():
    _stock_live()
    stock_store.append_history([{"at": "2026-04-02T10:00:00", "user": "someone", "action": "receive",
                                 "item_key": "Glass|Blue|20|", "field": "current", "old_value": "2", "new_value": "6",
                                 "detail": "received 4 · inv A-7 · 2026-04-02", "person": None}])
    r, d = _stock_buy("receive", "one", id=3, qty=2, invoice_no="a-7")
    eq(r.status_code, 409, "received before the move, in the stock app's own words")
    r, d = _stock_buy("receive", "one", id=3, qty=2, invoice_no="A-8", date="2026-10-20")
    eq(r.status_code, 200, r.text)
    eq((d["item"]["current"], d["item"]["received"]), (8, 2))
    eq(stock_store.read_history()[-1]["detail"], "received 2 · inv A-8 · 2026-10-20")
    r, d = _stock_buy("receive", "one", id=3, qty=2, invoice_no="A-8")
    eq(r.status_code, 409, "and one received here")
    r, d = _stock_buy("receive", "delivery", invoice_no="A-7", lines=[{"id": 9, "qty": 1}, {"id": 3, "qty": 1}])
    eq(r.status_code, 409, "a delivery checks every line")
    ok("Blue" in d["error"], d["error"])

@test
def t_stock_invoice_inv_10_is_not_inv_1():
    _stock_live()
    eq(_stock_buy("receive", "one", id=3, qty=1, invoice_no="INV-1")[0].status_code, 200)
    eq(_stock_buy("receive", "one", id=3, qty=1, invoice_no="INV-10")[0].status_code, 200)

@test
def t_a_stock_delivery_fills_the_oldest_open_order():
    _stock_live()
    _stock_buy("orders", "place", supplier="First", lines=[{"id": 3, "qty": 5}])
    _stock_buy("orders", "place", supplier="Second", lines=[{"id": 3, "qty": 5}])
    r, d = _stock_buy("receive", "delivery", invoice_no="D-1", date="2026-10-21", lines=[{"id": 3, "qty": 7}])
    eq(r.status_code, 200, r.text)
    eq(_stock_order_lines(3), [("First", 5, [5]), ("Second", 2, [2])])
    eq(stock_store.load_items()["items"]["3"]["on_order"], 3)
    eq([(o["qty"]) for o in d["receipt"]["lines"][0]["orders"]], [5, 2], "shown on the receipt")
    eq([h["detail"] for h in stock_store.read_history()][-2:],
       ["received 7 · inv D-1 · 2026-10-21 · delivery", "accepted delivery · 1 lines · 7 units · inv D-1"])

@test
def t_a_stock_delivery_line_can_name_its_order():
    _stock_live()
    _stock_buy("orders", "place", supplier="First", lines=[{"id": 3, "qty": 5}])
    second = _stock_buy("orders", "place", supplier="Second", lines=[{"id": 3, "qty": 5}])[1]["order"]["id"]
    _stock_buy("receive", "delivery", invoice_no="D-2", lines=[{"id": 3, "qty": 4, "order_id": second}])
    eq(_stock_order_lines(3), [("First", 0, []), ("Second", 4, [4])])

@test
def t_a_stock_delivery_can_be_counted_against_another_order():
    _stock_live()
    first = _stock_buy("orders", "place", supplier="First", lines=[{"id": 3, "qty": 5}])[1]["order"]["id"]
    second = _stock_buy("orders", "place", supplier="Second", lines=[{"id": 3, "qty": 5}])[1]["order"]["id"]
    _stock_buy("receive", "delivery", invoice_no="D-3", lines=[{"id": 3, "qty": 3}])
    eq(_stock_order_lines(3), [("First", 3, [3]), ("Second", 0, [])])
    r, d = _stock_buy("receive", "rematch", invoice_no="D-3", id=3, order_id=second)
    eq(r.status_code, 200, r.text)
    eq(_stock_order_lines(3), [("First", 0, []), ("Second", 3, [3])], "changed on the receipt")
    eq(stock_store.load_items()["items"]["3"]["on_order"], 7, "on order is the same either way")
    eq(first + 1, second)

@test
def t_undoing_a_stock_delivery_puts_back_on_order_and_the_order():
    _stock_live()
    _stock_buy("orders", "place", supplier="First", lines=[{"id": 3, "qty": 5}])
    _stock_buy("receive", "delivery", invoice_no="D-4", lines=[{"id": 3, "qty": 3}])
    eq(stock_store.load_items()["items"]["3"]["on_order"], 2)
    r, d = _stock_buy("receive", "undo", invoice_no="d-4")
    eq(r.status_code, 200, r.text)
    it = stock_store.load_items()["items"]["3"]
    eq((it["current"], it["received"], it["on_order"]), (6, 0, 5), "the shelf, received and on order as before")
    eq(_stock_order_lines(3), [("First", 0, [])], "the order awaits it again")
    eq(_stock_buy("receive", "undo", invoice_no="D-4")[0].status_code, 409, "undone once")
    eq(_stock_buy("receive", "undo", invoice_no="D-99")[0].status_code, 404)

@test
def t_a_stock_delivery_is_all_or_nothing():
    _stock_live()
    r, d = _stock_buy("receive", "delivery", invoice_no="D-5", lines=[{"id": 3, "qty": 2}, {"id": 999, "qty": 1}])
    eq(r.status_code, 404, r.text)
    ok("stock line" in d.get("error", ""), d)
    eq(stock_store.load_items()["items"]["3"]["current"], 6, "nothing of it written")
    r, d = _stock_buy("receive", "delivery", invoice_no="D-6", lines=[{"id": 3, "qty": 1}] * 201)
    eq(r.status_code, 400, "more than 200 lines")

@test
def t_stock_invoice_prices_update_costs_through_the_rate():
    _stock_live(items=[_stock_item(7, "Glass|Blue|20||#2", currency="USD", unit_cost=9.0, unit_cost_gbp=7.0),
                       _stock_item(9, "Glass|Red|30|", currency="JPY", unit_cost=9.0, unit_cost_gbp=7.0)])
    doc = stock_store.load_settings()
    doc["meta"]["fx_usd_gbp"] = "0.8"
    stock_store.write_settings(doc)
    r, d = _stock_buy("receive", "delivery", invoice_no="D-7", lines=[
        {"id": 7, "qty": 1, "unit_cost": 10, "update_cost": True},
        {"id": 9, "qty": 1, "unit_cost": 10, "update_cost": True}])
    eq(r.status_code, 200, r.text)
    eq(d["repriced"], 2)
    items = stock_store.load_items()["items"]
    eq((items["7"]["unit_cost"], items["7"]["unit_cost_gbp"]), (10.0, 8.0), "dollars at the rate set")
    eq(items["9"]["unit_cost_gbp"], 10.0, "a currency with no rate is taken at 1, as the stock app took it")

# ---- the final review's findings, pinned ---------------------------------------------

@test
def t_a_stock_rematch_never_records_a_move_that_did_not_happen():
    _stock_live()
    _stock_buy("orders", "place", supplier="First", lines=[{"id": 3, "qty": 5}])
    other = _stock_buy("orders", "place", supplier="Other", lines=[{"id": 9, "qty": 5}])[1]["order"]["id"]
    _stock_buy("receive", "delivery", invoice_no="D-8", lines=[{"id": 3, "qty": 2}])
    rows = len(stock_store.read_history())
    r, d = _stock_buy("receive", "rematch", invoice_no="D-8", id=3, order_id=other)
    eq(r.status_code, 400, "that order has no line for it")
    r, d = _stock_buy("receive", "rematch", invoice_no="", id=3, order_id=other)
    eq(r.status_code, 400, "which delivery?")
    eq(len(stock_store.read_history()), rows, "no history line for a move that did not happen")
    eq(_stock_order_lines(3), [("First", 2, [2])], "the receipt stays where it was")

@test
def t_a_renamed_stock_line_keeps_its_invoices_and_its_undo():
    _stock_live()
    stock_store.append_history([{"at": "2026-10-01T09:00:00", "user": "someone", "action": "receive",
                                 "item_key": "Glass|Blue|20|", "field": "current", "old_value": "2", "new_value": "6",
                                 "detail": "received 4 · inv OLD-1 · 2026-10-01", "person": None}])
    eq(_stock_buy("receive", "one", id=3, qty=4, invoice_no="INV-7")[0].status_code, 200)
    post("/api/stock/sheet", {"op": "edit", "id": 3, "changes": {"size": "21"}})        # renamed
    eq(_stock_buy("receive", "one", id=3, qty=4, invoice_no="INV-7")[0].status_code, 409, "received here, renamed or not")
    eq(_stock_buy("receive", "one", id=3, qty=4, invoice_no="old-1")[0].status_code, 409,
       "received before the move under its old name")
    post("/api/stock/sheet", {"op": "new", "fields": {"category": "Glass", "sub_category": "Blue", "size": "20",
                                                      "current": 10}})                     # its old name, reused
    r, d = _stock_buy("receive", "undo", invoice_no="INV-7")
    eq(r.status_code, 200, r.text)
    items = stock_store.load_items()["items"]
    eq((items["3"]["current"], items["10"]["current"]), (6, 10), "the renamed line gives it back, not the new one")

@test
def t_a_reused_stock_name_does_not_take_another_lines_history():
    _stock_live()
    post("/api/stock/sheet", {"op": "edit", "id": 9, "changes": {"current": 11}})
    post("/api/stock/sheet", {"op": "edit", "id": 9, "changes": {"size": "31"}})
    post("/api/stock/sheet", {"op": "new", "fields": {"category": "Glass", "sub_category": "Red", "size": "30"}})
    post("/api/stock/sheet", {"op": "edit", "id": 10, "changes": {"current": 3}})
    d = post("/api/stock/history", {"op": "item", "id": 10}).json()
    eq([(h["action"], h["field"]) for h in d["history"]], [("update", "current"), ("create", "")],
       "only its own lines, though line 9 once had its name")
    d = post("/api/stock/history", {"op": "item", "id": 9}).json()
    eq([h["field"] for h in d["history"]], ["key", "size", "current"], "and line 9 keeps its own")
