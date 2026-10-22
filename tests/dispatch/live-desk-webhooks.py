# ---- Live desk webhooks -----------------------------------------------------

def wh_headers(raw, secret=SECRET, topic="orders/updated", delivery="d1",
               shop="test-store.myshopify.com"):
    import hashlib as _h, hmac as _m, base64 as _b
    mac = _b.b64encode(_m.new(secret.encode(), raw, _h.sha256).digest()).decode()
    return {"X-Shopify-Hmac-Sha256": mac, "X-Shopify-Topic": topic,
            "X-Shopify-Webhook-Id": delivery, "X-Shopify-Shop-Domain": shop,
            "Content-Type": "application/json"}

@test
def t_a_signed_order_event_retires_the_order_snapshot():
    # Since 2026-10-12 a named order is read again rather than every snapshot
    # retired (_orders_changed); the event must still reach it.
    orderbook._webhook_seen.clear()
    raw = json.dumps({"id": 1}).encode()
    named, saved = [], orderbook._orders_changed
    orderbook._orders_changed = lambda ids: (named.append(list(ids)), saved(ids))
    try:
        r = client.post("/webhooks/orders", content=raw, headers=wh_headers(raw, delivery="ev1"))
    finally:
        orderbook._orders_changed = saved
    eq(r.status_code, 200, r.text)
    eq(named, [[1]], "the event's order is named, so every snapshot reads it again")
    ok(orderbook._webhook_state["count"] >= 1, "and the event was counted")

@test
def t_settings_names_the_version_shopify_sends_order_events_in():
    """The order subscriptions keep the Shopify version they were made with,
    and nothing showed which: an old one only moves forward, silently, when
    Shopify retires it. Each event says its version in a header; the last one
    is kept and Settings shows it beside the time of the last event."""
    orderbook._webhook_seen.clear()
    raw = json.dumps({"id": 3}).encode()
    h = dict(wh_headers(raw, delivery="ev-version"), **{"X-Shopify-API-Version": "2026-10"})
    eq(client.post("/webhooks/orders", content=raw, headers=h).status_code, 200)
    eq(post("/api/status", {}).json()["webhooks"]["version"], "2026-10")
    page = pagesource.join(HERE)
    ok("', Shopify version ' + wh.version" in page, "and the Live updates row says it")

@test
def t_an_unsigned_or_missigned_event_is_refused():
    raw = json.dumps({"id": 2}).encode()
    r = client.post("/webhooks/orders", content=raw,
                    headers={"Content-Type": "application/json"})
    eq(r.status_code, 401, "no signature, no entry")
    bad = wh_headers(raw, secret="wrong-secret-entirely-1234567890ab", delivery="ev2")
    r2 = client.post("/webhooks/orders", content=raw, headers=bad)
    eq(r2.status_code, 401, "a wrong signature is refused")
    other = wh_headers(raw, delivery="ev3", shop="someone-else.myshopify.com")
    r3 = client.post("/webhooks/orders", content=raw, headers=other)
    eq(r3.status_code, 401, "signed but for another store is refused")

