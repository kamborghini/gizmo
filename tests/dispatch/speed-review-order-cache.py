# ---- review of the order-cache change ---------------------------------------

@test
def t_a_load_during_a_read_by_id_waits_for_it():
    """Review CONC1 (high). The changed order was taken off the to-read list
    before Shopify answered, so a second load arriving during the read found a
    clean-looking snapshot and was answered with the old order: on the ledger,
    a paid invoice still owed."""
    def go(shop):
        run(orderbook._orders_snapshot({}, days=180, fields="id,created_at,financial_status"))
        shop.orders[888]["financial_status"] = "paid"
        orderbook._orders_changed([888])
        shop.delay = 0.05

        async def two():
            a = asyncio.ensure_future(orderbook._orders_snapshot({}, days=180, fields="id,created_at,financial_status"))
            await asyncio.sleep(0.01)              # the read by id is in flight
            b = await orderbook._orders_snapshot({}, days=180, fields="id,created_at,financial_status")
            return await a, b
        a, b = run(two())
        for who, got in (("the first load", a), ("a load during its read", b)):
            eq({o["id"]: o["financial_status"] for o in got}[888], "paid", who + " sees it paid")
        eq(shop.kinds().count("ids"), 1, "one read, shared")
    _with_shop(go)


@test
def t_with_the_cache_off_a_named_change_detaches_the_sweep():
    """Review CONC2. With the cache switched off, a sweep in flight is still
    shared; a write used to detach it, so the reload after the write swept
    afresh. A named change does the same again."""
    shop = _FakeShop(_shop_orders())
    saved, was = shopify._tool_json, orderbook.ORDER_CACHE_SECS
    shopify._tool_json, orderbook.ORDER_CACHE_SECS = shop.tools, 0
    orderbook._bust_orders()
    try:
        shop.delay = 0.05

        async def scenario():
            early = asyncio.ensure_future(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags"))
            await asyncio.sleep(0.01)
            shop.orders[777]["tags"] = "PC"
            orderbook._orders_changed([777])
            late = await orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags")  # early still sweeping
            return await early, late
        _early, late = run(scenario())
        eq({o["id"]: o["tags"] for o in late}[777], "PC", "the reload after the write sees it")
        eq(shop.kinds(), ["sweep", "sweep"], "because it swept afresh, as before")
    finally:
        shopify._tool_json, orderbook.ORDER_CACHE_SECS = saved, was
        orderbook._bust_orders()


@test
def t_a_late_joiner_is_never_answered_from_a_sweep_that_was_not_kept():
    """Review CONC3/EQUIV1. A load that joined a sweep after a named change was
    answered with that sweep's list when it was not kept (Refresh pressed
    elsewhere meanwhile, or a page failed), so the changed order showed as it
    was. It now sweeps again instead."""
    def go(shop):
        shop.delay = 0.05

        async def scenario():
            first = asyncio.ensure_future(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags"))
            await asyncio.sleep(0.01)
            shop.orders[777]["tags"] = "PC"
            orderbook._orders_changed([777])
            late = asyncio.ensure_future(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags"))
            await asyncio.sleep(0.01)
            orderbook._bust_orders()                 # Refresh pressed on another page
            return await first, await late
        _first, late = run(scenario())
        eq({o["id"]: o["tags"] for o in late}[777], "PC", "the late load sees the change")
    _with_shop(go)


@test
def t_a_snapshot_made_current_is_not_thrown_away():
    """Review COMPAT3. After its third read by id the loop dropped a snapshot
    it had just made current and swept the whole store anyway."""
    def go(shop):
        def hook(kind, n):
            if n in (1, 2):
                orderbook._orders_changed([777])     # the write during the sweep, its echo during the read
        shop.on_call = hook
        run(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags"))
        eq(shop.kinds(), ["sweep", "ids", "ids"], "no sweep after it is current: %r" % shop.kinds())
    _with_shop(go)


@test
def t_a_storm_of_changes_costs_one_sweep_not_two():
    """Review CONC4. More changes than can be read by id at once, arriving
    while a sweep ran, made one load sweep twice."""
    def go(shop):
        saved = orderbook.ORDER_REFRESH_MAX
        orderbook.ORDER_REFRESH_MAX = 2
        try:
            shop.on_call = lambda kind, n: orderbook._orders_changed([777, 888, 999])
            run(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags"))
            eq(shop.kinds().count("sweep"), 1, "one sweep: %r" % shop.kinds())
        finally:
            orderbook.ORDER_REFRESH_MAX = saved
    _with_shop(go)


@test
def t_a_cut_short_sweep_is_swept_again_not_added_to():
    """Review EQUIV2. A sweep stopped by the page cap holds the oldest orders;
    adding a newer one an event named made a list no sweep would return."""
    orders = [dict(_shop_orders()[0], id=10000 + i, name="#%d" % i, created_at=_ago(2)) for i in range(260)]

    def go(shop):
        saved = orderbook._paginate_orders
        orderbook._paginate_orders = lambda *a, **k: saved(*a, **{**k, "max_pages": 1})
        try:
            meta = {}
            got = run(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags", meta=meta))
            ok(meta.get("truncated") and len(got) == 250, "the sweep was cut short")
            orderbook._orders_changed([10259])       # an order past the cut
            shop.calls.clear()
            got = run(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags"))
            eq(shop.kinds(), ["sweep"], "swept again: %r" % shop.kinds())
            ok(10259 not in {o["id"] for o in got}, "and nothing a sweep would not return")
        finally:
            orderbook._paginate_orders = saved
    _with_shop(go, orders)


@test
def t_an_order_event_with_a_number_too_big_still_retires_everything():
    """Review COMPAT1. An id like 1e400 raised out of the webhook after the
    delivery was recorded, so Shopify's retry was taken as handled and
    nothing was retired."""
    def go(shop):
        run(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags"))
        orderbook._webhook_seen.clear()
        raw = b'{"id": 1e400}'
        r = client.post("/webhooks/orders", content=raw, headers=wh_headers(raw, delivery="big-1"))
        eq(r.status_code, 200, r.text)
        shop.calls.clear()
        run(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags"))
        eq(shop.kinds(), ["sweep"], "every snapshot was retired: %r" % shop.kinds())
    _with_shop(go)


