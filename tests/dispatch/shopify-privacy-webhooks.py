# ---- Shopify privacy webhooks ----------------------------------------------

def _seed_person_and_shipment(email):
    """A customer who exists in BOTH halves of the split: the CRM, which is
    relationship data and must go, and a dispatch record, which HMRC can ask
    for and must not."""
    d = salesdesk._load_crm()
    d["persons"]["p9001"] = {"id": "p9001", "name": "Jo Redact",
                             "emails": [email], "phone": "0161 000 0000"}
    salesdesk._write_crm(d)
    disp = desk._load_dispatch()
    disp["104999"] = {"order_id": "104999", "email": email,
                      "name": "Jo Redact", "address1": "1 Glass Works",
                      "postcode": "M1 1AA", "tracking": "TRK1"}
    desk._write_dispatch(disp)


def redact_through_the_hold(raw, delivery):
    """A customers/redact as Shopify sends it, then erased the only way it
    now can be: by an admin, in Settings (see
    t_a_signed_customer_redact_waits_for_an_admin)."""
    r = client.post("/webhooks/privacy", content=raw,
                    headers=wh_headers(raw, topic="customers/redact", delivery=delivery))
    eq(r.status_code, 200, r.text)
    addr = str(json.loads(raw)["customer"]["email"]).strip().lower()
    h = [x for x in privacy._held_requests() if x["email"] == addr]
    ok(h, "it is held for an admin, not erased on arrival")
    ensure_auth()
    shown = [x for x in post("/api/privacy", {}).json()["held"] if x["id"] == h[0]["id"]][0]
    e = post("/api/privacy", {"op": "erase", "id": h[0]["id"], "reach": shown["scope"].get("key", "")})
    eq(e.status_code, 200, e.text[:200])
    return r

@test
def t_a_redact_request_erases_the_crm_person():
    """Relationship data goes. This is the half of the split with no legal
    obligation to keep it."""
    orderbook._webhook_seen.clear()
    email = "jo.redact@example.com"
    _seed_person_and_shipment(email)
    raw = json.dumps({"customer": {"id": 555, "email": email},
                      "shop_domain": "test-store.myshopify.com"}).encode()
    redact_through_the_hold(raw, "pr1")
    eq("p9001" in salesdesk._load_crm()["persons"], False,
       "the CRM person is gone")


@test
def t_a_redact_request_keeps_the_dispatch_record_and_notes_it():
    """The other half. A customs and export record is retained under a legal
    obligation, so erasing it would trade one exposure for another - but it has
    to carry evidence the request was honoured."""
    orderbook._webhook_seen.clear()
    email = "jo.keep@example.com"
    _seed_person_and_shipment(email)
    raw = json.dumps({"customer": {"id": 556, "email": email},
                      "shop_domain": "test-store.myshopify.com"}).encode()
    redact_through_the_hold(raw, "pr2")
    rec = desk._load_dispatch().get("104999") or {}
    ok(rec, "the shipment record survives")
    eq(rec.get("address1"), "1 Glass Works", "with the address HMRC can ask for")
    ok(rec.get("redacted_request_at"), "and a note that erasure was requested")


@test
def t_a_redact_request_erases_only_that_persons_email_threads():
    """The mailbox is relationship data too. And the blast radius matters more
    than the erasure: wiping one person must not touch anyone else's thread."""
    orderbook._webhook_seen.clear()
    store = mail._load_mail()
    store.setdefault("threads", {})
    store["threads"]["tgone"] = {"id": "tgone", "from_email": "Gone@Example.com",
                                 "subject": "Please delete me", "state": "open"}
    store["threads"]["tstay"] = {"id": "tstay", "from_email": "other@example.com",
                                 "subject": "Unrelated", "state": "open"}
    mail._write_mail(store)
    raw = json.dumps({"customer": {"id": 558, "email": "gone@example.com"},
                      "shop_domain": "test-store.myshopify.com"}).encode()
    redact_through_the_hold(raw, "pr6")
    threads = mail._load_mail()["threads"]
    eq("tgone" in threads, False, "their thread is gone, matched case-insensitively")
    eq("tstay" in threads, True, "and nobody else's was touched")


@test
def t_shop_redact_takes_a_backup_before_it_erases_anything():
    """Shopify fires this 48 hours after an uninstall and expects the shop's
    data erased. For a single-merchant app that is the merchant's own dispatch
    and customs history, so an uninstall during testing would destroy it. The
    erasure is real; the backup is what makes a misfire survivable."""
    from datetime import datetime, timedelta, timezone
    orderbook._webhook_seen.clear()
    calls = []
    real, checker = backup._build_backup_zip, shopify._install_checker
    backup._build_backup_zip = lambda *a, **k: (calls.append(1), real(*a, **k))[1]

    async def gone():
        return "gone"
    shopify._install_checker = gone   # Shopify has confirmed the uninstall
    w = scheduler._load_watch()         # ...and the store has been unreadable for two days
    w["shopify_down"] = (datetime.now(timezone.utc) - timedelta(hours=46)).isoformat()
    scheduler._save_watch(w)
    raw = json.dumps({"shop_domain": "test-store.myshopify.com"}).encode()
    try:
        r = client.post("/webhooks/privacy", content=raw,
                        headers=wh_headers(raw, topic="shop/redact", delivery="pr7"))
        eq(r.status_code, 200, r.text)
        ok(calls, "a backup was taken before anything was erased")
    finally:
        backup._build_backup_zip, shopify._install_checker = real, checker
        w = scheduler._load_watch()
        w.pop("shopify_down", None)
        scheduler._save_watch(w)


@test
def t_a_privacy_webhook_without_a_valid_signature_is_refused():
    raw = json.dumps({"customer": {"id": 1, "email": "x@y.com"}}).encode()
    r = client.post("/webhooks/privacy", content=raw,
                    headers={"Content-Type": "application/json"})
    eq(r.status_code, 401, "no signature, no entry")
    bad = wh_headers(raw, secret="wrong-secret-entirely-1234567890ab",
                     topic="customers/redact", delivery="pr3")
    eq(client.post("/webhooks/privacy", content=raw, headers=bad).status_code, 401,
       "a wrong signature is refused")
    other = wh_headers(raw, topic="customers/redact", delivery="pr4",
                       shop="someone-else.myshopify.com")
    eq(client.post("/webhooks/privacy", content=raw, headers=other).status_code, 401,
       "signed but for another store is refused")


@test
def t_a_data_request_is_recorded_rather_than_answered_automatically():
    """Supplying the data is a human step with a 30-day clock. The app's job is
    to receive the request and make sure it is not lost."""
    orderbook._webhook_seen.clear()
    raw = json.dumps({"customer": {"id": 777, "email": "asks@example.com"},
                      "shop_domain": "test-store.myshopify.com"}).encode()
    r = client.post("/webhooks/privacy", content=raw,
                    headers=wh_headers(raw, topic="customers/data_request", delivery="pr5"))
    eq(r.status_code, 200, r.text)
    log = privacy._load_privacy_log()
    ok(any(e.get("topic") == "customers/data_request"
           and e.get("email") == "asks@example.com" for e in log.get("events", [])),
       "the request is on the ledger with who asked")


@test
def t_an_oversized_chunked_body_is_cut_off_not_buffered():
    # The signature can only be checked after the body is read, so the read
    # happens for anyone. A chunked upload carries no Content-Length; the read
    # must stop at the cap, not buffer whatever arrives and check afterwards.
    def big_chunks():
        piece = b"x" * 65536
        for _ in range(40):        # ~2.5MB, over the 1MB cap
            yield piece
    r = client.post("/webhooks/orders", content=big_chunks(),
                    headers={"Content-Type": "application/json"})
    eq(r.status_code, 413, r.text)

@test
def t_a_redelivered_event_does_not_count_twice():
    orderbook._webhook_seen.clear()
    raw = json.dumps({"id": 3}).encode()
    h = wh_headers(raw, delivery="same-delivery-id")
    client.post("/webhooks/orders", content=raw, headers=h)
    epoch_after_first = orderbook._orders_epoch
    count_after_first = orderbook._webhook_state["count"]
    client.post("/webhooks/orders", content=raw, headers=h)
    eq(orderbook._orders_epoch, epoch_after_first, "a redelivery does not retire the snapshot again")
    eq(orderbook._webhook_state["count"], count_after_first, "or count as a second event")

@test
def t_webhook_registration_is_a_standing_repair():
    import server, hmac, hashlib
    calls = {"listed": 0, "made": []}
    async def fake_request(method, path, params=None, body=None):
        if method == "GET" and path == "webhooks.json":
            calls["listed"] += 1
            # One topic already registered at our address, one at a stale address.
            return {"webhooks": [
                {"id": 1, "topic": "orders/create",
                 "address": "https://app.example.test/webhooks/orders"},
                {"id": 2, "topic": "orders/updated",
                 "address": "https://old.example.test/webhooks/orders"},
                {"id": 3, "topic": "refunds/create",
                 "address": "https://app.example.test/webhooks/orders"}]}
        if method == "POST" and path == "webhooks.json":
            calls["made"].append(body["webhook"]["topic"])
            return {"webhook": {"id": 99, **body["webhook"]}}
        if method == "DELETE":
            calls.setdefault("deleted", []).append(path)
            return {}
        raise AssertionError("unexpected " + method + " " + path)
    saved_req = server._request; server._request = fake_request
    os.environ["APP_URL"] = "https://app.example.test"
    try:
        res = run(server.ensure_order_webhooks())
        ok(res["ok"], str(res))
        eq(sorted(calls["made"]), ["orders/updated"],
           "only the missing topics were created, at the current address")
        eq(sorted(calls.get("deleted") or []), ["webhooks/2.json", "webhooks/3.json"],
           "a topic the endpoint refuses (A20: refunds/create, 422 on every delivery) is removed, and so is "
           "the subscription at another host (audit R-C2: made with this app's credentials, it copies orders out)")
        eq(res.get("foreign_removed"), ["orders/updated to old.example.test"], "and the removal is reported")
        # Every topic registered here is one the receiver accepts.
        for topic in server.WEBHOOK_TOPICS:
            raw = json.dumps({"id": 1}).encode()
            sig = base64.b64encode(hmac.new(SECRET.encode(), raw, hashlib.sha256).digest()).decode()
            r = client.post("/webhooks/orders", content=raw, headers={
                "x-shopify-hmac-sha256": sig, "x-shopify-topic": topic,
                "x-shopify-shop-domain": "test-store.myshopify.com",
                "x-shopify-webhook-id": "reg-" + topic, "content-type": "application/json"})
            ok(r.status_code != 422, topic + " is accepted by the endpoint it is registered at")
    finally:
        server._request = saved_req
        os.environ.pop("APP_URL", None)


