# =========================== speed: the Production Manager's follow-up calls ==
# The sixth speed pull request (the 2026-10-12 audit, X7).

def _meta_products():
    """Products as REST shapes them (what the per-product read returned) and
    as GraphQL shapes them (what the one read returns), from one fixture."""
    fx = {pid: {"names": (["Gobo Size", "Glass"] if pid % 3 else ["Size"]), "type": ("Custom Gobo" if pid % 2 else "Gobo")}
          for pid in range(1, 120)}
    return fx


@test
def t_a_queue_learns_its_products_in_one_read():
    """The 2026-10-12 speed audit, X7. The option names a label prints and the
    product types that tell a stock gobo from a custom one were read one
    product at a time, in two rounds (names, then the types the first round
    had not covered), four at a time through the shop's gate: after each
    deploy and every six hours, ten or more waves before a queue could show.
    One read now answers every product a queue needs, each list keeps its own
    cap of 40 (a line past it keeps the generic text it always had), and a
    product the read did not return is not remembered as empty."""
    fx = _meta_products()
    reads, singles = [], []

    async def reader(ids):
        reads.append(list(ids))
        return {pid: dict(fx[pid]) for pid in ids if pid != 50}      # 50 was deleted

    async def tools(registry, name, args):
        if name == "shopify_get_product":
            singles.append(args["product_id"])
        return {}
    saved = (shopify._product_meta_reader, shopify._tool_json)
    shopify._product_meta_reader, shopify._tool_json = reader, tools
    production._option_names_cache.clear()
    try:
        names_ids = list(range(1, 46))            # 45: the first 40 count
        type_ids = list(range(30, 80))            # 50, overlapping: the first 40 count
        names, types = run(production._product_names_and_types({}, names_ids, type_ids))
        eq(len(reads), 1, "one read for both lists")
        eq(singles, [], "and no product read one at a time")
        eq(sorted(reads[0]), sorted(set(range(1, 41)) | set(range(30, 70))), "for the first 40 of each")
        eq(sorted(names), list(range(1, 41)), "names for the first 40 option-name lines")
        eq(sorted(types), list(range(30, 70)), "types for the first 40 type lines")
        eq(names[7], fx[7]["names"], "with what the product holds")
        eq(types[31], fx[31]["type"])
        eq((types.get(50), 50 in production._option_names_cache), ("", False),
           "a product the read did not return is blank this time and asked for again next time")
        reads.clear()
        names2, types2 = run(production._product_names_and_types({}, names_ids, type_ids))
        eq((names2, {k: v for k, v in types2.items() if k != 50}), (names, {k: v for k, v in types.items() if k != 50}),
           "the same answer again")
        eq(reads, [[50]], "from memory, but for the one it did not have")
    finally:
        shopify._product_meta_reader, shopify._tool_json = saved
        production._option_names_cache.clear()


@test
def t_a_failed_products_read_falls_back_to_reading_them_one_by_one():
    """The one read failing (Shopify busy, a scope missing) must never cost a
    label its option names: the products are then read the way they always
    were, one at a time, and the queue shows what it always showed."""
    fx = _meta_products()
    singles = []

    async def reader(ids):
        raise RuntimeError("Throttled")

    async def tools(registry, name, args):
        if name == "shopify_get_product":
            pid = args["product_id"]
            singles.append(pid)
            return {"id": pid, "product_type": fx[pid]["type"],
                    "options": [{"name": n, "position": i + 1} for i, n in enumerate(fx[pid]["names"])]}
        return {}
    saved = (shopify._product_meta_reader, shopify._tool_json)
    shopify._product_meta_reader, shopify._tool_json = reader, tools
    production._option_names_cache.clear()
    try:
        names, types = run(production._product_names_and_types({}, [1, 2, 3], [3, 4]))
        eq(sorted(singles), [1, 2, 3, 4], "each product read once")
        eq(names, {p: fx[p]["names"] for p in (1, 2, 3)})
        eq(types, {p: fx[p]["type"] for p in (3, 4)})
    finally:
        shopify._product_meta_reader, shopify._tool_json = saved
        production._option_names_cache.clear()


@test
def t_the_products_read_gives_what_the_product_reads_gave():
    """The label is frozen: the one read must give exactly the option names
    and product type the per-product reads did. REST gave a product's
    options in position order, at most three of them; the GraphQL read asks
    for the first three by position and orders them by it too. A product not
    found is left out; an answer with errors is a failure, not an answer."""
    sent = []

    async def fake_request(method, path, params=None, body=None, idempotent=None, **kw):
        sent.append(body)
        return {"data": {"nodes": [
            {"id": "gid://shopify/Product/11", "productType": " Custom Gobo ",
             "options": [{"name": "Glass ", "position": 2}, {"name": " Gobo Size", "position": 1}]},
            None,
            {"id": "gid://shopify/Product/13", "productType": "", "options": [{"name": "Title", "position": 1}]},
        ]}}
    saved = server._request
    server._request = fake_request
    try:
        got = run(server.shopify_product_meta([11, 12, 13]))
        eq(got, {11: {"names": ["Gobo Size", "Glass"], "type": "Custom Gobo"},
                 13: {"names": ["Title"], "type": ""}}, "names in position order, stripped; the missing one left out")
        q = sent[0]["query"]
        ok("nodes(ids: $ids)" in q and "options(first: 3)" in q and "productType" in q, q)
        eq(sent[0]["variables"]["ids"], ["gid://shopify/Product/11", "gid://shopify/Product/12",
                                         "gid://shopify/Product/13"])

        async def throttled(method, path, params=None, body=None, idempotent=None, **kw):
            return {"errors": [{"message": "Throttled", "extensions": {"code": "THROTTLED"}}]}
        server._request = throttled
        try:
            run(server.shopify_product_meta([11]))
            ok(False, "an answer with errors must raise")
        except RuntimeError:
            pass
    finally:
        server._request = saved


@test
def t_a_release_reads_its_order_once():
    """Releasing an order read it to move its tags, then read it again to see
    whether it is an account order needing 30-day terms: two Shopify reads of
    one order on every Ready to make and every printed label. The terms check
    now uses the read the tag move made; what it decides is unchanged."""
    def go():
        ensure_auth()
        reset_prod(); reset_dispatch()
        reads = []

        async def counting(registry, name, args):
            if name == "shopify_get_order":
                reads.append(args.get("order_id"))
            return await fake_tool_json(registry, name, args)
        saved = (shopify._tool_json, shopify._payment_terms_writer, ORDER["tags"])

        async def writer(order_id):
            return {"ok": True, "updated": True, "was": "Due on receipt"}
        shopify._tool_json, shopify._payment_terms_writer = counting, writer
        ORDER["tags"] = "Unprocessed, purchase order unpaid"
        try:
            r = post("/api/production-labels/queue", {"order_id": 12345, "name": "#104239"}).json()
            ok(r["po_unpaid"] and r["terms_ok"] and "Net 30" in r["terms_note"], r)
            eq(reads, [12345], "the order was read once for the release and its terms")
            reads.clear(); reset_prod()
            ORDER["tags"] = "Unprocessed"
            plain = post("/api/production-labels/queue", {"order_id": 12345}).json()
            ok(not plain["po_unpaid"] and plain["terms_ok"], plain)
            eq(reads, [12345], "an ordinary order too")
        finally:
            shopify._tool_json, shopify._payment_terms_writer, ORDER["tags"] = saved
            reset_prod()
    with_accounts(go)


@test
def t_the_missed_orders_check_is_not_scanned_again_until_an_order_changes():
    """Every load of the Make queue walked every open order in the shop, with
    their addresses and lines, to find paid orders that never reached the
    bench, and no answer was ever kept. It is now kept until any order is
    known to have changed (the app's own writes, Shopify's order webhooks and
    Refresh all say so) or two minutes pass, and kept apart per tag."""
    scans = []

    async def tools(registry, name, args):
        if name == "shopify_list_orders" and args.get("status") == "open":
            scans.append(1)
            return {"orders": [{"id": 9, "name": "#9", "created_at": "2026-10-01T10:00:00Z", "tags": "",
                                "financial_status": "paid", "line_items": [{"title": "Gobo", "properties": [
                                    {"name": "Manufacturer", "value": "Martin"}]}]}]}
        return {}
    saved = shopify._tool_json
    shopify._tool_json = tools
    production._missing_cache.clear()
    try:
        a = run(production.run_missing_production({}))
        b = run(production.run_missing_production({}))
        eq(len(scans), 1, "two looks, one scan")
        eq(a, b, "the same answer")
        orderbook._orders_changed([9])
        run(production.run_missing_production({}))
        eq(len(scans), 2, "an order known to have changed scans again")
        orderbook._bust_orders()
        run(production.run_missing_production({}))
        eq(len(scans), 3, "and so does a Refresh")
        run(production.run_missing_production({}, tag="Other"))
        eq(len(scans), 4, "another tag is its own answer")
        saved_ttl = production.MISSING_CACHE_SECS
        production.MISSING_CACHE_SECS = 0
        try:
            run(production.run_missing_production({}))
            eq(len(scans), 5, "and two minutes on, it scans again")
        finally:
            production.MISSING_CACHE_SECS = saved_ttl

        async def failing(registry, name, args):
            scans.append(1)
            return {"_failed": True}
        shopify._tool_json = failing
        production._missing_cache.clear()
        ok(run(production.run_missing_production({})).get("error"), "a failed scan says so")
        ok(run(production.run_missing_production({})).get("error") and len(scans) == 7, "and is not kept")
    finally:
        shopify._tool_json = saved
        production._missing_cache.clear()


@test
def t_adding_a_missed_order_to_the_queue_always_checks_the_strip_again():
    """Review of the sixth speed PR (S1). An order on the missed-orders strip
    that was cancelled, or tagged, in Shopify's admin before the app heard of
    it: Add to queue reads it, finds nothing to move and writes nothing, so no
    order was known to have changed and the kept strip came back with the
    row in it for up to two minutes. Adding from the strip now always has the
    strip checked again."""
    def go():
        ensure_auth()
        reset_prod(); reset_dispatch()
        state = {"cancelled": False}
        scans = []
        order9 = {"id": 9, "name": "#9", "created_at": "2026-10-01T10:00:00Z", "tags": "",
                  "financial_status": "paid", "cancelled_at": None, "fulfillment_status": None,
                  "line_items": [{"title": "Gobo", "properties": [{"name": "Manufacturer", "value": "Martin"}]}]}

        def now9():
            o = dict(order9)
            if state["cancelled"]:
                o["cancelled_at"] = "2026-10-13T08:00:00Z"
            return o

        async def tools(registry, name, args):
            if name == "shopify_list_orders" and args.get("status") == "open":
                scans.append(1)
                return {"orders": [now9()]}
            if name == "shopify_get_order":
                return now9()
            return await fake_tool_json(registry, name, args)
        saved = shopify._tool_json
        shopify._tool_json = tools
        try:
            first = run(production.run_missing_production({}))
            eq([m["name"] for m in first["missing"]], ["#9"], "the strip lists it")
            state["cancelled"] = True                  # cancelled in Shopify; no webhook yet
            r = post("/api/production-labels/queue", {"order_id": 9, "name": "#9"})
            eq(r.status_code, 200, r.text)
            after = run(production.run_missing_production({}))
            eq(len(scans), 2, "the strip was checked again after the click")
            eq(after["missing"], [], "and the cancelled order is gone from it")
        finally:
            shopify._tool_json = saved
            reset_prod()
    with_accounts(go)


@test
def t_a_stale_missed_orders_answer_is_not_kept_in_memory():
    """Review of the sixth speed PR (S2). The kept strip names customers and
    companies; once it can no longer be served (an order changed, two
    minutes passed) it is dropped at once, so a scan that then fails leaves
    nothing of the old answer behind."""
    async def ok_tools(registry, name, args):
        if name == "shopify_list_orders" and args.get("status") == "open":
            return {"orders": [{"id": 9, "name": "#9", "created_at": "2026-10-01T10:00:00Z", "tags": "",
                                "financial_status": "paid", "line_items": [{"title": "Gobo", "properties": [
                                    {"name": "Manufacturer", "value": "Martin"}]}]}]}
        return {}

    async def failing(registry, name, args):
        return {"_failed": True}
    saved = shopify._tool_json
    production._missing_cache.clear()
    try:
        shopify._tool_json = ok_tools
        run(production.run_missing_production({}))
        ok(production._missing_cache, "an answer is kept")
        orderbook._orders_changed([9])
        shopify._tool_json = failing
        ok(run(production.run_missing_production({})).get("error"), "the scan after the change fails")
        eq(production._missing_cache, {}, "and the old answer is not held")
    finally:
        shopify._tool_json = saved
        production._missing_cache.clear()


@test
def t_a_missed_orders_scan_that_saw_an_order_change_is_not_kept():
    """Re-check of the sixth speed PR. A scan reads every open order from
    Shopify over a few seconds; an order known to have changed meanwhile (a
    click on the strip, a webhook) made its answer stale before it landed,
    yet it was kept and served, names and all. It is now kept only when no
    order changed while it ran."""
    gate = {"ev": None}

    async def slow(registry, name, args):
        if name == "shopify_list_orders" and args.get("status") == "open":
            await gate["ev"].wait()
            return {"orders": [{"id": 9, "name": "#9", "created_at": "2026-10-01T10:00:00Z", "tags": "",
                                "financial_status": "paid", "line_items": [{"title": "Gobo", "properties": [
                                    {"name": "Manufacturer", "value": "Martin"}]}]}]}
        return {}
    saved = shopify._tool_json
    shopify._tool_json = slow
    production._missing_cache.clear()
    try:
        async def scenario():
            gate["ev"] = asyncio.Event()
            scan = asyncio.ensure_future(production.run_missing_production({}))
            await asyncio.sleep(0.01)                  # the scan is reading Shopify
            orderbook._orders_changed([9])               # #9 changed meanwhile
            gate["ev"].set()
            return await scan
        res = run(scenario())
        eq([m["name"] for m in res["missing"]], ["#9"], "the scan still answers the look that asked")
        eq(production._missing_cache, {}, "but its answer is not kept")
    finally:
        shopify._tool_json = saved
        production._missing_cache.clear()


@test
def t_a_release_that_finds_shopify_ahead_of_the_app_says_the_order_changed():
    """Re-check of the sixth speed PR. A release reads the order and may find
    it cancelled, fulfilled, or already past the bench in Shopify's admin
    before the app heard: nothing is written, so nothing said the order had
    changed, and the kept strip and the queues went on showing what the app
    had last seen (up to two and three minutes). Such a read now says so. An
    order simply already where it was asked to go (every reprint) says
    nothing, as before."""
    def go():
        ensure_auth()
        reset_prod(); reset_dispatch()
        saved = (shopify._tool_json, ORDER["tags"], ORDER.get("cancelled_at"))
        try:
            # cancelled in Shopify, the app not told
            ORDER["tags"], ORDER["cancelled_at"] = "Unprocessed", "2026-10-13T08:00:00Z"
            e0 = orderbook._orders_epoch
            ok_, note, released = run(production._release_tags({}, 12345))
            ok(orderbook._orders_epoch > e0, "a dead order found on release is an order that changed")
            # tagged PC in Shopify's admin, the app not told
            ORDER["tags"], ORDER["cancelled_at"] = "PC", None
            e1 = orderbook._orders_epoch
            run(production._release_tags({}, 12345))
            ok(orderbook._orders_epoch > e1, "and so is one already past the bench")
            # already in To make: an ordinary reprint
            ORDER["tags"] = "IP"
            e2 = orderbook._orders_epoch
            run(production._release_tags({}, 12345))
            eq(orderbook._orders_epoch, e2, "an order already where it was asked to go says nothing")
            # and a click on the strip always does
            e3 = orderbook._orders_epoch
            r = post("/api/production-labels/queue", {"order_id": 12345, "name": "#104239"})
            eq(r.status_code, 200, r.text)
            ok(orderbook._orders_epoch > e3, "a click on the strip says the order changed")
        finally:
            shopify._tool_json = saved[0]
            ORDER["tags"], ORDER["cancelled_at"] = saved[1], saved[2]
            reset_prod()
    with_accounts(go)

