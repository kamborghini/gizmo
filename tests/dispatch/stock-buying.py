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
