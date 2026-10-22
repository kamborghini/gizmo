# ---- re-check of the review fixes ---------------------------------------------

@test
def t_a_load_that_joined_a_cut_short_sweep_after_a_payment_sees_it_paid():
    """Re-check of #20 (high). The ledger's two-year sweep can be cut short by
    the page cap. A load that joined such a sweep after a payment was named
    was answered from it, so the paid invoice showed as owed; before this
    change the event detached the sweep and the load swept afresh. Only the
    load that STARTED a sweep, whose request predates every change named
    while it ran, is answered from it."""
    orders = [dict(_shop_orders()[0], id=10000 + i, name="#%d" % i, created_at=_ago(2),
                   financial_status="pending") for i in range(260)]

    def go(shop):
        saved = orderbook._paginate_orders
        orderbook._paginate_orders = lambda *a, **k: saved(*a, **{**k, "max_pages": 1})
        shop.delay = 0.05
        try:
            async def scenario():
                first = asyncio.ensure_future(
                    orderbook._orders_snapshot({}, days=730, fields="id,created_at,financial_status"))
                await asyncio.sleep(0.01)                   # the long sweep is under way
                shop.orders[10005]["financial_status"] = "paid"
                orderbook._orders_changed([10005])            # Shopify says it was paid
                joined = await orderbook._orders_snapshot({}, days=730, fields="id,created_at,financial_status")
                await first
                return joined
            joined = run(scenario())
            eq({o["id"]: o["financial_status"] for o in joined}[10005], "paid",
               "a load joining after the payment sees it paid")
        finally:
            orderbook._paginate_orders = saved
    _with_shop(go, orders)


@test
def t_the_reload_after_a_write_is_never_answered_from_before_it():
    """Re-check of #20 (medium). During a burst of order events too big to read
    one by one, the Production Manager's reload after its own tag write joined
    a sweep that started before the write and was answered from it: the order
    stayed in the queue it had just left."""
    def go(shop):
        saved = orderbook.ORDER_REFRESH_MAX
        orderbook.ORDER_REFRESH_MAX = 2
        shop.delay = 0.05
        try:
            async def scenario():
                other = asyncio.ensure_future(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags"))
                await asyncio.sleep(0.01)                   # another tab's sweep is under way
                shop.orders[777]["tags"] = "PC"
                orderbook._orders_changed([777, 888, 999])    # the write, and a burst of events
                reload = await orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags")
                await other
                return reload
            reload = run(scenario())
            eq({o["id"]: o["tags"] for o in reload}[777], "PC", "the reload sees its own write")
        finally:
            orderbook.ORDER_REFRESH_MAX = saved
    _with_shop(go)


@test
def t_a_failing_shopify_is_not_asked_again_by_the_load_that_started_the_sweep():
    """Re-check of #20 (low). With Shopify failing and an order event during
    each sweep, one load swept three or four times into a throttled store.
    The load that started a sweep is answered from it (failed, so the ledger
    says it cannot read), as it always was."""
    def go(shop):
        shop.fail_sweeps = True
        shop.on_call = lambda kind, n: orderbook._orders_changed([777])
        meta = {}
        run(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags", meta=meta))
        eq(shop.kinds(), ["sweep"], "one sweep: %r" % shop.kinds())
        ok(meta.get("failed"), "and the failure is said")
    _with_shop(go)


