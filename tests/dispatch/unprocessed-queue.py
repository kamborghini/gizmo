# ---- Unprocessed queue ------------------------------------------------------

@test
def t_the_unprocessed_queue_lists_waiting_orders_and_release_moves_them_to_ip():
    reset_dispatch(); reset_prod()
    TAG_WRITES.clear()
    store = {"orders": [
        {"id": 701, "name": "#701", "tags": "Unprocessed", "created_at": "2026-08-16T09:00:00Z",
         "line_items": [], "customer": {}, "shipping_address": {}, "fulfillment_status": None,
         "cancelled_at": None},
        {"id": 702, "name": "#702", "tags": "IP", "created_at": "2026-08-16T09:00:00Z",
         "line_items": [], "customer": {}, "shipping_address": {}, "fulfillment_status": None,
         "cancelled_at": None}]}
    async def tools(registry, name, args):
        if name == "shopify_list_orders":
            return {"orders": [dict(o) for o in store["orders"]]}
        if name == "shopify_get_order":
            return dict(next(o for o in store["orders"] if o["id"] == args["order_id"]))
        return {}
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        res = run(production.run_production_labels({}, tag="Unprocessed"))
        eq([o["id"] for o in res["orders"]], [701], "only the waiting order shows")
        res2 = run(production.run_production_labels({}, tag="IP"))
        eq([o["id"] for o in res2["orders"]], [702], "and it is not in To make yet")
        # The release: the same tag move the amber strip performs.
        r = post("/api/production-labels/queue", {"order_id": 701})
        eq(r.status_code, 200, r.text)
        ok(TAG_WRITES, "a tag write happened")
        wrote = TAG_WRITES[-1][1]
        ok("IP" in [t.strip() for t in wrote.split(",")], "IP added: " + wrote)
        ok("Unprocessed" not in wrote, "Unprocessed removed: " + wrote)
    finally:
        shopify._tool_json = saved


@test
def t_the_glass_catalogue_covers_every_sheet_size_in_every_family():
    # The stock app's mapping view is only trustworthy if it shows the WHOLE
    # translation, so the catalogue must be the sheet's sizes times the three
    # families, with nothing invented and nothing dropped.
    combos = stock_link._zeta_catalog_combos()
    glass = [c for c in combos if c["family"] != "Ring"]
    rings = [c for c in combos if c["family"] == "Ring"]
    gsizes = {c["size"] for c in glass}
    ok(len(gsizes) >= 20, "the live sheet's sizes are all there: " + str(len(gsizes)))
    eq({c["family"] for c in glass}, {"Mono", "HM", "Colour"}, "three glass families")
    eq(len(glass), len(gsizes) * 3, "every glass size appears once per family")
    eq({c["size"] for c in rings}, set(stock_link._BEZEL_UP), "one ring line per bezelled size")
    ok(all(c["size"] for c in combos), "no blank sizes")
    seen = set()
    for c in combos:
        key = (c["family"], c["size"])
        ok(key not in seen, "no duplicates: " + str(key))
        seen.add(key)


@test
def t_a_bezelled_gobo_consumes_its_blank_and_its_ring():
    # An 86mm or 100mm gobo is a 64.9 blank bezelled up by a ring: the usage
    # lines must say what the bench consumes, or the stock sheet drifts one
    # ring and one mis-sized blank per order.
    shaped = {"items": [
        {"quantity": 2, "glass_type": "Mono - Original", "production_size": "86"},
        {"quantity": 1, "glass_type": "Colour - Original", "production_size": "100"},
        {"quantity": 3, "glass_type": "Mono - Original", "production_size": "26.5"},
    ]}
    lines = stock_link._usage_lines(shaped)
    eq(len(lines), 5, "two bezelled items become four lines, the plain one stays one")
    eq(lines[0], {"size": "64.9", "family": "Mono", "qty": 2}, "the 86 order's glass")
    eq(lines[1], {"size": "86", "family": "Ring", "qty": 2}, "and its ring")
    eq(lines[2], {"size": "64.9", "family": "Colour", "qty": 1}, "colour keeps its family on the glass")
    eq(lines[3], {"size": "100", "family": "Ring", "qty": 1}, "with the 100 ring")
    eq(lines[4], {"size": "26.5", "family": "Mono", "qty": 3}, "plain sizes are untouched")
    # And the published catalogue matches what will actually be sent.
    combos = stock_link._zeta_catalog_combos()
    keys = {(c["family"], c["size"]) for c in combos}
    ok(("Ring", "86") in keys and ("Ring", "100") in keys, "ring lines are in the catalogue")
    ok(("Mono", "86") not in keys and ("Mono", "100") not in keys,
       "86 and 100 glass are not, because they will never be sent")
    ok(("Mono", "64.9") in keys, "the blank they cut from is")


