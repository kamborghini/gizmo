# ---- Order sweep snapshot ---------------------------------------------------
# The queue sweeps up to 30 sequential pages of orders. These tests turn the
# snapshot on (it is off for the rest of the suite, see ORDER_CACHE_SECS above)
# and assert on the number of Shopify calls, never on the cache internals.

def with_cache(fn, secs=45):
    """Run fn with the order snapshot enabled and a clean slate."""
    was = orderbook.ORDER_CACHE_SECS
    orderbook.ORDER_CACHE_SECS = secs
    orderbook._bust_orders()
    orderbook._orders_inflight.clear()
    try:
        return fn()
    finally:
        orderbook.ORDER_CACHE_SECS = was
        orderbook._bust_orders()
        orderbook._orders_inflight.clear()

QUEUE_ORDERS = [
    {"id": 777, "order_number": 1, "name": "#1", "created_at": "2026-08-12T09:00:00Z",
     "tags": "IP", "line_items": [], "customer": {}, "shipping_address": {}},
    {"id": 888, "order_number": 2, "name": "#2", "created_at": "2026-08-12T09:00:00Z",
     "tags": "PC", "line_items": [], "customer": {}, "shipping_address": {}},
]

def sweep_counter(orders=None, fail=False):
    """A fake registry that counts order-list pages and can fail on demand."""
    calls = {"n": 0}
    async def tools(registry, name, args):
        if name == "shopify_list_orders":
            calls["n"] += 1
            if fail:
                return {"_failed": True}     # what _tool_json returns for a throttled read
            return {"orders": list(orders if orders is not None else QUEUE_ORDERS)}
        return {}
    return calls, tools

@test
def t_the_three_queues_share_one_sweep_instead_of_three():
    # Flipping To make -> To ship -> Complete asks for the same window and the
    # same fields every time; only the local tag filter differs.
    calls, tools = sweep_counter()
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        def go():
            a = run(production.run_production_labels({}, tag="IP"))
            b = run(production.run_production_labels({}, tag="PC"))
            c = run(production.run_production_labels({}, tag=desk.DISPATCHED_TAG))
            return a, b, c
        a, b, c = with_cache(go)
        eq(calls["n"], 1, "one sweep served all three queues")
        eq([o["id"] for o in a["orders"]], [777], "and To make still filters correctly")
        eq([o["id"] for o in b["orders"]], [888], "and To ship still filters correctly")
        eq([o["id"] for o in c["orders"]], [], "and Complete still filters correctly")
    finally:
        shopify._tool_json = saved

@test
def t_a_tag_write_retires_the_snapshot_immediately():
    # The queues are filtered on tags, so an order that has just been moved must
    # not still be sitting in the queue it left.
    calls, tools = sweep_counter()
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        def go():
            run(production.run_production_labels({}, tag="IP"))
            first = calls["n"]
            run(production.run_production_labels({}, tag="IP"))
            eq(calls["n"], first, "a repeat load costs nothing")
            orderbook._bust_orders()          # Refresh, or a change nobody can name
            run(production.run_production_labels({}, tag="IP"))
            eq(calls["n"], first + 1, "and the write forced a re-read")
        with_cache(go)
    finally:
        shopify._tool_json = saved

@test
def t_the_queue_counts_ride_along_from_the_same_sweep():
    # The mix (2026-10-06): the Production Manager shows the size of every flow
    # queue at once, as counters. They come back with whichever queue was asked
    # for, from the sweep that load already made: no second Shopify call.
    orders = QUEUE_ORDERS + [
        {"id": 999, "order_number": 3, "name": "#3", "created_at": "2026-08-12T09:00:00Z",
         "tags": "Unprocessed", "line_items": [], "customer": {}, "shipping_address": {}},
        {"id": 1000, "order_number": 4, "name": "#4", "created_at": "2026-08-12T09:00:00Z",
         "tags": "IP, Rush", "line_items": [], "customer": {}, "shipping_address": {}},
    ]
    calls, tools = sweep_counter(orders)
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        res = with_cache(lambda: run(production.run_production_labels({}, tag="PC")))
        eq(res.get("counts"), {"unprocessed": 1, "make": 2, "ship": 1}, "every flow queue is counted")
        eq([o["id"] for o in res["orders"]], [888], "the queue asked for is unchanged")
        eq(calls["n"], 1, "from the one sweep")
        one = run(production.run_production_labels({}, order_id=12345))
        ok("counts" not in one, "the one-order deep link swept nothing, so it counts nothing")
    finally:
        shopify._tool_json = saved

@test
def t_a_tag_write_through_the_real_path_busts_the_snapshot():
    # Not the helper: the actual writer call site inside _sync_order_tags.
    calls, tools = sweep_counter()
    async def both(registry, name, args):
        if name == "shopify_get_order":
            return {"id": 777, "tags": "Unprocessed", "fulfillment_status": None, "cancelled_at": None}
        return await tools(registry, name, args)
    saved = shopify._tool_json; shopify._tool_json = both
    try:
        def go():
            run(production.run_production_labels({}, tag="IP"))
            first = calls["n"]
            TAG_WRITES.clear()
            run(orderbook._sync_order_tags({}, 777, add=["IP"], remove=["Unprocessed"]))
            ok(TAG_WRITES, "the tag write happened")
            run(production.run_production_labels({}, tag="IP"))
            eq(calls["n"], first + 1, "and it re-read the store afterwards")
        with_cache(go)
    finally:
        shopify._tool_json = saved

@test
def t_refresh_re_reads_shopify_even_inside_the_window():
    # The merchant tagged something in the Shopify admin; there are no webhooks,
    # so Refresh is the only way to see it before the TTL runs out.
    calls, tools = sweep_counter()
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        def go():
            run(production.run_production_labels({}, tag="IP"))
            first = calls["n"]
            run(production.run_production_labels({}, tag="IP", fresh=True))
            eq(calls["n"], first + 1, "Refresh went back to Shopify")
        with_cache(go)
    finally:
        shopify._tool_json = saved

@test
def t_refresh_on_the_money_views_also_re_reads_shopify():
    # Liability answers "who owes me". A customer paying is invisible to this app
    # (no webhooks), so Refresh there has to reach Shopify, not a 45-second-old
    # sweep, or the merchant chases someone who has already paid.
    calls, tools = sweep_counter()
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        def go():
            run(orderbook._orders_snapshot({}, days=730, fields="id,tags"))
            first = calls["n"]
            eq(orderbook._refresh_asked({}), False, "an ordinary load keeps the snapshot")
            run(orderbook._orders_snapshot({}, days=730, fields="id,tags"))
            eq(calls["n"], first, "and costs nothing")
            eq(orderbook._refresh_asked({"fresh": True}), True, "Refresh discards it")
            run(orderbook._orders_snapshot({}, days=730, fields="id,tags"))
            eq(calls["n"], first + 1, "so the next read goes to Shopify")
        with_cache(go)
    finally:
        shopify._tool_json = saved

@test
def t_refresh_never_joins_a_sweep_that_started_before_it():
    # The ledger reads two years of orders, which takes long enough for the
    # merchant to mark an invoice paid in Shopify and press Refresh while it is
    # still running. If Refresh joined that sweep it would answer with the
    # picture from before the payment, and they would chase a paid invoice.
    state = {"paid": False}
    pages = {"n": 0}
    async def tools(registry, name, args):
        if name == "shopify_list_orders":
            pages["n"] += 1
            await asyncio.sleep(0.05)          # the sweep is slow, that is the point
            return {"orders": [{"id": 9, "tags": "Purchase order unpaid",
                                "financial_status": "paid" if state["paid"] else "pending"}]}
        return {}
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        def go():
            async def scenario():
                slow = asyncio.ensure_future(
                    orderbook._orders_snapshot({}, days=730, fields="id,tags,financial_status"))
                await asyncio.sleep(0.01)      # the sweep is now in flight
                state["paid"] = True           # they mark it paid in the Shopify admin
                orderbook._refresh_asked({"fresh": True})   # and press Refresh
                after = await orderbook._orders_snapshot({}, days=730,
                                                       fields="id,tags,financial_status")
                await slow
                return after
            after = run(scenario())
            eq(after[0]["financial_status"], "paid", "Refresh saw the payment")
            eq(pages["n"], 2, "because it swept again rather than joining the one in flight")
        with_cache(go)
    finally:
        shopify._tool_json = saved

@test
def t_a_failed_sweep_is_never_cached():
    # "Nothing owed" must never be an artefact of a throttled fetch.
    calls, tools = sweep_counter(fail=True)
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        def go():
            meta = {}
            run(orderbook._orders_snapshot({}, days=180, fields="id,tags", meta=meta))
            ok(meta.get("failed"), "the failure is reported to the caller")
            run(orderbook._orders_snapshot({}, days=180, fields="id,tags"))
            eq(calls["n"], 2, "and the next caller retries rather than reading a cached failure")
        with_cache(go)
    finally:
        shopify._tool_json = saved

@test
def t_concurrent_queue_loads_share_one_sweep():
    # Three tabs opening at once must not fire three 30-page sweeps at a REST
    # bucket that leaks about two calls a second.
    calls = {"n": 0}
    async def tools(registry, name, args):
        if name == "shopify_list_orders":
            calls["n"] += 1
            await asyncio.sleep(0.01)      # long enough for the others to arrive
            return {"orders": list(QUEUE_ORDERS)}
        return {}
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        def go():
            async def three():
                return await asyncio.gather(*[production.run_production_labels({}, tag="IP")
                                              for _ in range(3)])
            res = run(three())
            eq(calls["n"], 1, "one sweep, three callers")
            eq([len(r["orders"]) for r in res], [1, 1, 1], "and every caller got the answer")
        with_cache(go)
    finally:
        shopify._tool_json = saved

@test
def t_different_windows_do_not_borrow_each_others_orders():
    # A 28-day sector total must never be served from a 730-day ledger sweep.
    seen = []
    async def tools(registry, name, args):
        if name == "shopify_list_orders":
            seen.append(args.get("created_at_min"))
            return {"orders": []}
        return {}
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        def go():
            run(orderbook._orders_snapshot({}, days=28, fields="id"))
            run(orderbook._orders_snapshot({}, days=730, fields="id"))
            eq(len(seen), 2, "two windows, two sweeps")
            ok(seen[0] != seen[1], "and each asked Shopify for its own window")
        with_cache(go)
    finally:
        shopify._tool_json = saved

@test
def t_product_options_are_learned_once_not_per_queue_load():
    # Uncached this was up to 40 calls on every queue load, re-learning that a
    # gobo has a "Gobo Size" option.
    calls = {"n": 0}
    async def tools(registry, name, args):
        if name == "shopify_get_product":
            calls["n"] += 1
            return {"id": args["product_id"], "options": [{"name": "Gobo Size"}]}
        return {}
    saved = shopify._tool_json; shopify._tool_json = tools
    production._option_names_cache.clear()
    try:
        first = run(production._product_option_names({}, [11, 12]))
        eq(first, {11: ["Gobo Size"], 12: ["Gobo Size"]}, "options resolved")
        eq(calls["n"], 2, "one call per product")
        again = run(production._product_option_names({}, [11, 12]))
        eq(again, first, "same answer from cache")
        eq(calls["n"], 2, "and no further calls at all")
    finally:
        shopify._tool_json = saved
        production._option_names_cache.clear()

@test
def t_a_product_that_could_not_be_read_is_not_remembered_as_empty():
    calls = {"n": 0}
    state = {"ok": False}
    async def tools(registry, name, args):
        if name == "shopify_get_product":
            calls["n"] += 1
            if not state["ok"]:
                return {"_failed": True}
            return {"id": args["product_id"], "options": [{"name": "Gobo Size"}]}
        return {}
    saved = shopify._tool_json; shopify._tool_json = tools
    production._option_names_cache.clear()
    try:
        eq(run(production._product_option_names({}, [11])), {11: []}, "a failed read yields nothing")
        state["ok"] = True
        eq(run(production._product_option_names({}, [11])), {11: ["Gobo Size"]}, "and is retried later")
        eq(calls["n"], 2, "so the failure was not cached")
    finally:
        shopify._tool_json = saved
        production._option_names_cache.clear()


