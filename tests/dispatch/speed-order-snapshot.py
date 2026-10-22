# =========================== speed: the order snapshot survives a known change ==
# The second speed pull request (the 2026-10-12 audit, X1). Every write this
# app made, and Shopify's webhook echoing it, retired every cached sweep, so
# one Production Manager action cost two full sweeps of the store. An order
# the app knows has changed is now read again by itself; _bust_orders stays as
# blunt as it was for everything else (Refresh, an unreadable event).

class _FakeShop:
    """Orders as Shopify keeps them, answering shopify_list_orders with its
    real filters: status=any, created_at_min, since_id (ascending, 250 a
    page), ids and fields."""

    def __init__(self, orders, other=None):
        # Deep copies: one order's address is not another's.
        self.orders = {o["id"]: json.loads(json.dumps(o)) for o in orders}
        self.calls = []                    # ("sweep" | "ids", args)
        self.delay = 0.0
        self.fail_ids = False
        self.fail_sweeps = False
        self.on_call = None                # (kind, n) -> None, run as each call arrives
        self.other = other                 # everything that is not an order list

    async def tools(self, registry, name, args):
        if name != "shopify_list_orders":
            return await self.other(registry, name, args) if self.other else {}
        kind = "ids" if args.get("ids") else "sweep"
        self.calls.append((kind, dict(args)))
        if self.on_call:
            self.on_call(kind, len(self.calls))
        fail = (kind == "ids" and self.fail_ids) or (kind == "sweep" and self.fail_sweeps)
        rows = sorted(self.orders.values(), key=lambda o: o["id"])
        if kind == "ids":
            want = {int(x) for x in str(args["ids"]).split(",") if x}
            rows = [o for o in rows if o["id"] in want]
        else:
            lo = args.get("created_at_min") or ""
            rows = [o for o in rows if o["created_at"] >= lo and o["id"] > int(args.get("since_id") or 0)]
        rows = rows[:int(args.get("limit") or 50)]
        keep = [f for f in str(args.get("fields") or "").split(",") if f]
        if keep:
            rows = [{k: v for k, v in o.items() if k in keep or k == "id"} for o in rows]
        # The store as it was when the request arrived: a change made while
        # the answer is on its way is not in it, as with Shopify.
        answer = {"orders": [json.loads(json.dumps(o)) for o in rows]}
        if self.delay:
            await asyncio.sleep(self.delay)
        return {"_failed": True} if fail else answer

    def kinds(self):
        return [k for k, _ in self.calls]


def _ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _shop_orders():
    base = {"line_items": [], "customer": {"first_name": "Jo"}, "shipping_address": {"city": "Leeds"},
            "financial_status": "pending", "cancelled_at": None, "fulfillment_status": None}
    return [dict(base, id=777, order_number=1, name="#1", created_at=_ago(3), tags="IP"),
            dict(base, id=888, order_number=2, name="#2", created_at=_ago(5), tags="PC"),
            dict(base, id=999, order_number=3, name="#3", created_at=_ago(9), tags="Unprocessed"),
            dict(base, id=1000, order_number=4, name="#4", created_at=_ago(400), tags="IP")]


def _with_shop(fn, orders=None):
    saved = shopify._tool_json
    shop = _FakeShop(orders or _shop_orders(), other=saved)
    shopify._tool_json = shop.tools
    try:
        return with_cache(lambda: fn(shop))
    finally:
        shopify._tool_json = saved


@test
def t_one_production_action_reads_one_order_not_the_whole_store():
    """X1. A tag write, then Shopify's own webhook echoing it a moment later:
    each used to retire every snapshot, so the next two loads swept the
    whole store. Each now reads the one order again, by id."""
    def go(shop):
        run(production.run_production_labels({}, tag="IP"))
        eq(shop.kinds(), ["sweep"], "the first load sweeps")
        shop.calls.clear()
        run(orderbook._sync_order_tags({}, 777, add=["PC"], remove=["IP"]))
        shop.orders[777]["tags"] = "PC"                    # what Shopify now holds
        ip = run(production.run_production_labels({}, tag="IP"))
        orderbook._orders_changed([777])                     # the webhook echoing the write
        pc = run(production.run_production_labels({}, tag="PC"))
        eq(shop.kinds(), ["ids", "ids"], "two reads of one order, no sweep: %r" % shop.kinds())
        eq([o["id"] for o in ip["orders"]], [], "the order left To make")
        eq(sorted(o["id"] for o in pc["orders"]), [777, 888], "and is in To ship")
    _with_shop(go)


@test
def t_a_snapshot_patched_by_id_is_exactly_a_full_sweep():
    """The Production Manager queue's content and order are frozen, and the
    ledger must never say a paid invoice is owed. After every kind of change
    the patched snapshot is compared with a fresh full sweep of the store,
    order by order, and the queue built from each is compared too."""
    fields = ("id,order_number,name,created_at,tags,email,customer,billing_address,"
              "shipping_address,line_items,note,cancelled_at,fulfillment_status,"
              "financial_status,shipping_lines,taxes_included")

    def go(shop):
        def full():
            return run(orderbook._paginate_orders({}, days=180, fields=fields))
        changes = [
            ("a tag moved", lambda: shop.orders[777].update(tags="PC"), [777]),
            ("paid", lambda: shop.orders[888].update(financial_status="paid"), [888]),
            ("cancelled", lambda: shop.orders[999].update(cancelled_at=_ago(0)), [999]),
            ("an address edited", lambda: shop.orders[888]["shipping_address"].update(city="York"), [888]),
            ("a new order", lambda: shop.orders.update({1001: dict(shop.orders[777], id=1001, name="#5",
                                                                   created_at=_ago(0), tags="IP")}), [1001]),
            ("an old order touched", lambda: shop.orders[1000].update(tags="PC"), [1000]),
            ("deleted", lambda: shop.orders.pop(999), [999]),
            ("two at once", lambda: (shop.orders[777].update(tags="IP"), shop.orders[888].update(tags="IP")), [777, 888]),
        ]
        run(orderbook._orders_snapshot({}, days=180, fields=fields))
        for what, change, ids in changes:
            change()
            orderbook._orders_changed(ids)
            shop.calls.clear()
            got = run(orderbook._orders_snapshot({}, days=180, fields=fields))
            eq(shop.kinds(), ["ids"], what + ": read by id only: %r" % shop.kinds())
            eq(got, full(), what + ": the patched snapshot is the full sweep, order for order")
            for tag in ("IP", "PC", desk.DISPATCHED_TAG):
                cached = run(production.run_production_labels({}, tag=tag))
                orderbook._bust_orders()
                fresh = run(production.run_production_labels({}, tag=tag))
                eq((cached["orders"], cached.get("counts")), (fresh["orders"], fresh.get("counts")),
                   what + ": the %s queue is the same either way" % tag)
    _with_shop(go)


@test
def t_a_change_during_a_sweep_is_caught_not_thrown_away():
    """X1's second sweep: the reload after a write was still sweeping when the
    webhook landed, so its result was thrown away and the next load swept
    again. The sweep is now kept and the changed order read again by id, and
    nobody, however early they joined it, is answered with the old order."""
    def go(shop):
        shop.delay = 0.05

        async def scenario():
            early = asyncio.ensure_future(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags"))
            await asyncio.sleep(0.01)                  # the sweep is in flight
            shop.orders[777]["tags"] = "PC"
            orderbook._orders_changed([777])
            late = asyncio.ensure_future(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags"))
            return await early, await late
        early, late = run(scenario())
        for who, got in (("an early caller", early), ("a late one", late)):
            eq({o["id"]: o["tags"] for o in got}[777], "PC", who + " sees the change")
        eq(shop.kinds(), ["sweep", "ids"], "one sweep, kept, then one order: %r" % shop.kinds())
        shop.calls.clear()
        run(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags"))
        eq(shop.kinds(), [], "and the next load costs nothing")
    _with_shop(go)


@test
def t_a_failed_read_by_id_falls_back_to_a_full_sweep():
    """A read of one order that fails must not leave the old one in place:
    the snapshot is dropped and the store swept, as before."""
    def go(shop):
        run(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags"))
        shop.orders[777]["tags"] = "PC"
        shop.fail_ids = True
        orderbook._orders_changed([777])
        shop.calls.clear()
        meta = {}
        got = run(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags", meta=meta))
        eq(shop.kinds(), ["ids", "sweep"], "tried the order, then swept: %r" % shop.kinds())
        eq({o["id"]: o["tags"] for o in got}[777], "PC", "and the answer is current")
        ok(not meta.get("failed"), "and complete")
    _with_shop(go)


@test
def t_an_order_event_names_its_order_and_a_garbled_one_retires_everything():
    """Shopify's order webhook carries the order's id; that order is read
    again on the next load. An event whose body cannot be read retires every
    snapshot, as every event used to."""
    def go(shop):
        run(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags"))
        orderbook._webhook_seen.clear()
        raw = json.dumps({"id": 777, "tags": "ignored: the payload is never state"}).encode()
        r = client.post("/webhooks/orders", content=raw, headers=wh_headers(raw, delivery="x1-a"))
        eq(r.status_code, 200, r.text)
        shop.calls.clear()
        run(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags"))
        eq(shop.kinds(), ["ids"], "the event's order is read by id: %r" % shop.kinds())
        eq(shop.calls[0][1]["ids"], "777")
        raw = b"not json"
        r = client.post("/webhooks/orders", content=raw, headers=wh_headers(raw, delivery="x1-b"))
        eq(r.status_code, 200, r.text)
        shop.calls.clear()
        run(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags"))
        eq(shop.kinds(), ["sweep"], "an unreadable event still retires everything: %r" % shop.kinds())
    _with_shop(go)


@test
def t_adding_payment_terms_rereads_the_order():
    """The ledger reads payment_terms. Attaching 30-day terms retired nothing,
    so for up to the cache's three minutes the ledger could show the order
    without them; the order is now read again on the next load."""
    def go(shop):
        run(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags"))
        saved = (shopify._payment_terms_writer, ORDER.get("tags"))

        async def writer(oid):
            return {"ok": True}
        shopify._payment_terms_writer, ORDER["tags"] = writer, orderbook.PO_UNPAID_TAG
        try:
            run(production._net30_on_release({}, 777))
        finally:
            shopify._payment_terms_writer, ORDER["tags"] = saved
        shop.calls.clear()
        run(orderbook._orders_snapshot({}, days=180, fields="id,created_at,tags"))
        ok(("ids" in shop.kinds()) and "777" in [c[1].get("ids") for c in shop.calls],
           "the order with new terms is read again: %r" % shop.calls)
    try:
        _with_shop(go)
    finally:
        reset_prod()


