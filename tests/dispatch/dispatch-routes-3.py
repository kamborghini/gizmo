@test
def t_domestic_quotes_do_not_pay_for_customs_lookups():
    reset_dispatch(); reset_prod()
    called = []
    real = shopify._tool_json
    async def spy(registry, name, args):
        called.append(name)
        return await real(registry, name, args)
    shopify._tool_json = spy
    try:
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        eq(r.status_code, 200, r.text)
        eq(r.json().get("customs_items"), [], "no customs payload on a GB order")
        ok("shopify_get_variant" not in called, "no variant reads for a domestic parcel")
    finally:
        shopify._tool_json = real

@test
def t_every_tool_the_customs_lookup_uses_is_registered():
    # _tool_json swallows a missing registry entry into {"_failed": True}, so a
    # tool that exists in server.py but not in COPILOT_TOOLS fails SILENTLY and
    # the customs card quietly falls back to sale prices. Pin the registration.
    for name in ("shopify_get_order", "shopify_get_variant", "shopify_get_inventory_items"):
        ok(name in server.COPILOT_TOOLS, name + " is in the registry copilot actually uses")

@test
def t_projectors_default_to_china_when_shopify_has_no_origin():
    reset_dispatch(); reset_prod()
    order = {"id": 12345, "name": "#12345", "currency": "GBP", "email": "c@x.co",
             "shipping_address": {"first_name": "A", "last_name": "B", "address1": "1 Rue",
                                  "city": "Paris", "zip": "75001", "country_code": "FR",
                                  "phone": "0033", "name": "A B"},
             "line_items": [
                 {"id": 1, "title": "Projected Image 200 Watt LED Gobo Projector", "quantity": 1,
                  "price": "780.00", "variant_id": 111},
                 {"id": 2, "title": "Wedding Gobo 16", "quantity": 1,
                  "price": "45.00", "variant_id": 222},
             ]}
    async def tools(registry, name, args):
        if name == "shopify_get_order":
            return order
        if name == "shopify_get_variant":
            return {"id": args["variant_id"], "inventory_item_id": 9000 + args["variant_id"]}
        if name == "shopify_get_inventory_items":
            # Shopify knows the cost but NOT the origin for either product.
            return {"inventory_items": [
                {"id": 9111, "cost": "425.00", "harmonized_system_code": "9008.50.00"},
                {"id": 9222, "cost": "12.00", "harmonized_system_code": ""},
            ]}
        return {}
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        items = r.json().get("customs_items") or []
        eq(items[0]["origin"], "CN", "a projector with no Shopify origin is China")
        eq(items[1]["origin"], "GB", "a gobo with no Shopify origin is the UK")
        # A stocked product with no cost is the ONLY missing-cost flag.
        eq(items[0]["needs_cost"], False, "projector has a cost, no flag")
        eq(items[1]["needs_cost"], False, "gobo declares sale value by design, no flag")
        eq(items[1]["hs_code"], "9002.20.000", "gobo HS filled even with none in Shopify")
    finally:
        shopify._tool_json = saved

@test
def t_a_source_four_junior_is_a_66mm_gobo_however_it_is_spelled():
    """Order 104275 nearly shipped 53.3 mm glass for a Source 4 Jr. The sheet
    held the same fixture twice: 'Source Four Jr' at 66 and 'Source Four
    Junior - M size' undercut to 53.3 off a 65.5 mm holder measurement - and
    the order's wording matched the wrong twin. The merchant's ruling is 66
    (the M-size glass the GH64 holder takes); the override carries it over
    ANY size sheet, and the aliases catch the spellings the sheet lacks."""
    for model in ("Source Four Jr", "Source Four Junior", "Source Four Junior - M size",
                  "Source 4 Jr", "Source 4 Junior", "S4 Jr", "S4 Junior", "Source Four Jnr",
                  # The Revolution had the identical twin-row disease: 53.3 on
                  # 'Source Four Revolution', 66 on 'Revolution'. Ruled: 66.
                  "Source Four Revolution", "Revolution", "S4 Revolution"):
        hit, review = size_list._gobo_lookup("ETC", model)
        ok(hit is not None and review is None, model + " -> " + repr(review))
        eq(hit["production_size"], "66", model + " must cut at 66 mm, got " + hit["production_size"])

@test
def t_releasing_an_unpaid_purchase_order_starts_its_30_day_clock():
    """Pressing Ready to make on an order tagged 'purchase order unpaid' must
    ALSO attach NET-30 payment terms in Shopify - and say the outcome either
    way, because a purchase order quietly missing its terms is an invoice
    nobody chases. An untagged order gets no terms; a failed attach never
    fails the release itself."""
    reset_dispatch(); reset_prod()
    calls = []
    async def fake_terms(order_id):
        calls.append(int(order_id)); return {"ok": True}
    saved_terms = shopify._payment_terms_writer
    saved_tags = ORDER["tags"]
    shopify._payment_terms_writer = fake_terms
    try:
        # Tag spelled with different case and spacing still counts.
        ORDER["tags"] = "Unprocessed, Purchase Order  Unpaid"
        r = post("/api/production-labels/queue", {"order_id": 12345, "name": "#104239"}).json()
        eq(calls, [12345], "the tagged order gets its terms")
        ok(r["po_unpaid"] and r["terms_ok"], r)
        eq(r["terms_note"], "30-day payment terms added.")
        # Releasing again after Shopify says terms exist stays calm.
        async def already(order_id):
            calls.append(int(order_id)); return {"ok": True, "already": True}
        shopify._payment_terms_writer = already
        r2 = post("/api/production-labels/queue", {"order_id": 12345, "name": "#104239"}).json()
        ok(r2["terms_ok"] and "already" in r2["terms_note"], r2)
        # An order that WAS on other terms says so, rather than claiming the
        # order already had 30-day terms it never had.
        async def moved(order_id):
            return {"ok": True, "updated": True, "was": "Due on receipt"}
        shopify._payment_terms_writer = moved
        r2b = post("/api/production-labels/queue", {"order_id": 12345, "name": "#104239"}).json()
        eq(r2b["terms_note"], "Payment terms changed from Due on receipt to Net 30.")
        # An ordinary order: no terms call at all.
        ORDER["tags"] = "Unprocessed"
        calls.clear()
        post("/api/production-labels/queue", {"order_id": 12345, "name": "#104239"})
        eq(calls, [], "no unpaid tag, no payment terms")
        # A refused attach reports and never fails the release.
        ORDER["tags"] = "Unprocessed, purchase order unpaid"
        async def refused(order_id):
            return {"ok": False, "reason": "permission",
                    "detail": "The access token lacks write_payment_terms."}
        shopify._payment_terms_writer = refused
        r3 = post("/api/production-labels/queue", {"order_id": 12345, "name": "#104239"})
        eq(r3.status_code, 200, "the release still succeeds")
        j3 = r3.json()
        ok(not j3["terms_ok"] and "write_payment_terms" in j3["terms_note"], j3)
    finally:
        shopify._payment_terms_writer = saved_terms
        ORDER["tags"] = saved_tags

@test
def t_gobo_projectors_are_projectors_not_gobos():
    # The regression the merchant caught live: projector products are NAMED
    # "Projected Image ... Gobo Projector", so a naive "contains gobo" rule
    # declared every projector at sale value. Projector wins the classification.
    reset_dispatch(); reset_prod()
    order = {"id": 12345, "name": "#12345", "currency": "GBP", "email": "c@x.co",
             "shipping_address": {"first_name": "A", "last_name": "B", "address1": "1 Rue",
                                  "city": "Paris", "zip": "75001", "country_code": "FR",
                                  "phone": "0033", "name": "A B"},
             "line_items": [
                 {"id": 1, "title": "Projected Image 200 Watt Gobo Projector",
                  "quantity": 1, "price": "780.00", "variant_id": 111},
             ]}
    async def tools(registry, name, args):
        if name == "shopify_get_order":
            return order
        if name == "shopify_get_variant":
            return {"id": 111, "inventory_item_id": 9111}
        if name == "shopify_get_inventory_items":
            return {"inventory_items": [{"id": 9111, "cost": "425.00",
                                         "harmonized_system_code": "9008.50.00"}]}
        return {}
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        it = (r.json().get("customs_items") or [])[0]
        eq(it["unit_value"], "425.00", "COST, despite the word Gobo in the name")
        eq(it["value_basis"], "cost", "classified as a stocked product")
        eq(it["hs_code"], "9008.50.00", "its own HS code, not the gobo blanket")
        eq(it["origin"], "CN", "projector origin rule still applies")
    finally:
        shopify._tool_json = saved

@test
def t_shopify_address_lines_stay_separate_and_within_the_courier_cap():
    # Order 104240: "Momentum Logistics Park" and "Unit 1 Ash Drive" arrived as
    # separate Shopify lines and were being merged into one over-long Address1.
    # Couriers cap each line at 35 characters.
    eq(worldoptions._address_lines("Momentum Logistics Park", "Unit 1 Ash Drive"),
       ("Momentum Logistics Park", "Unit 1 Ash Drive", ""),
       "two clean lines pass through untouched")
    a1, a2, a3 = worldoptions._address_lines("Unit 1 Ash Drive Momentum Logistics Park", "")
    ok(all(len(x) <= 35 for x in (a1, a2, a3)), "an over-long single line wraps within the cap")
    eq((a1 + " " + a2).strip(), "Unit 1 Ash Drive Momentum Logistics Park", "no words lost")
    # And it reaches the envelope as three real elements.
    holder = {}
    async def cap_call(service, action, inner, retryable=True):
        holder["xml"] = inner
        return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap_call
    try:
        d = {"name": "A", "street": "Momentum Logistics Park", "street2": "Unit 1 Ash Drive",
             "city": "Washington", "postcode": "NE38 0LT", "country": "GB",
             "phone": "1", "email": "a@b.c"}
        run(worldoptions.book({"service_type_code": "UPS_Standard",
                               "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              d, d, [{"width": 1, "length": 1, "depth": 1, "weight": 1}]))
        x = holder["xml"]
        ok("<m:Address1>Momentum Logistics Park</m:Address1>" in x, "line one intact")
        ok("<m:Address2>Unit 1 Ash Drive</m:Address2>" in x, "line two intact, NOT merged")
    finally:
        worldoptions._soap_call = saved

@test
def t_ship_to_carries_both_shopify_lines():
    shaped = orderbook._ship_to({"shipping_address": {
        "address1": "Momentum Logistics Park", "address2": "Unit 1 Ash Drive",
        "city": "Washington", "zip": "NE38 0LT", "country_code": "GB", "name": "A B"}})
    eq(shaped["street"], "Momentum Logistics Park", "line one")
    eq(shaped["street2"], "Unit 1 Ash Drive", "line two, separate")

@test
def t_a_failed_reply_still_carries_the_envelope():
    # "Could not create SSL/TLS secure channel" came back as a FAILED reply, and
    # the panel claimed the request was never sent. It was: their server answered.
    reset_dispatch(); reset_prod()
    FAILED_BOOK = """<Envelope><Body><DoShipmentResponse><DoShipmentResult>
     <Message>The request was aborted: Could not create SSL/TLS secure channel.*|**|*1</Message>
     <NotificationtType>FAILED</NotificationtType>
    </DoShipmentResult></DoShipmentResponse></Body></Envelope>"""
    async def failing(service, action, inner, retryable=True):
        return ET.fromstring(FAILED_BOOK if service == "ShipmentService" else RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = failing
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        body = r.json()
        ok(body.get("error"), "the failure is reported")
        tech = body.get("tech") or {}
        ok("SSL/TLS" in (tech.get("reply") or ""), "their words verbatim")
        ok(tech.get("request"), "the envelope IS captured for an answered failure")
        eq(tech.get("sent"), True, "and it says the request was sent")
    finally:
        worldoptions._soap_call = saved

@test
def t_a_transient_failed_reply_is_retried_exactly_once():
    reset_dispatch(); reset_prod()
    desk.WO_RETRY_WAIT_SECS = 0          # no real sleeping in tests
    SSL_FAIL = """<Envelope><Body><DoShipmentResponse><DoShipmentResult>
     <Message>The request was aborted: Could not create SSL/TLS secure channel.*|**|*1</Message>
     <NotificationtType>FAILED</NotificationtType>
    </DoShipmentResult></DoShipmentResponse></Body></Envelope>"""
    calls = {"n": 0}
    async def flaky(service, action, inner, retryable=True):
        if service != "ShipmentService":
            return ET.fromstring(RATE_XML)
        calls["n"] += 1
        return ET.fromstring(SSL_FAIL if calls["n"] == 1 else BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = flaky
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        eq(r.status_code, 200, r.text)
        ok(r.json().get("dispatch", {}).get("tracking_number") or r.json().get("tracking_number"),
           "second attempt booked: " + r.text[:120])
        eq(calls["n"], 2, "exactly one retry")
    finally:
        worldoptions._soap_call = saved

@test
def t_a_validation_failure_is_never_retried():
    reset_dispatch(); reset_prod()
    desk.WO_RETRY_WAIT_SECS = 0
    VAL_FAIL = """<Envelope><Body><DoShipmentResponse><DoShipmentResult>
     <Message>Ready date should be in format - dd/MM/yyyy.</Message>
     <NotificationtType>FAILED</NotificationtType>
    </DoShipmentResult></DoShipmentResponse></Body></Envelope>"""
    calls = {"n": 0}
    async def refusing(service, action, inner, retryable=True):
        if service != "ShipmentService":
            return ET.fromstring(RATE_XML)
        calls["n"] += 1
        return ET.fromstring(VAL_FAIL)
    saved = worldoptions._soap_call; worldoptions._soap_call = refusing
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        ok(r.json().get("error"), "reported")
        eq(calls["n"], 1, "a deterministic refusal is not retried")
    finally:
        worldoptions._soap_call = saved

@test
def t_a_post_send_silence_is_never_retried():
    # The first attempt may have booked and charged; a retry could double-book.
    reset_dispatch(); reset_prod()
    desk.WO_RETRY_WAIT_SECS = 0
    calls = {"n": 0}
    async def silent(service, action, inner, retryable=True):
        if service != "ShipmentService":
            return ET.fromstring(RATE_XML)
        calls["n"] += 1
        raise worldoptions.WorldOptionsError(
            "World Options did not reply in time. The shipment MAY still have been "
            "booked; check your World Options portal before trying again.")
    saved = worldoptions._soap_call; worldoptions._soap_call = silent
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        ok(r.json().get("error"), "reported")
        eq(calls["n"], 1, "NEVER retried when the outcome is unknown")
    finally:
        worldoptions._soap_call = saved

@test
def t_manifest_lists_the_days_bookings_with_margin():
    reset_dispatch(); reset_prod()
    # Book one (the mock order carries Standard Delivery shipping paid).
    r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
    eq(r.status_code, 200, r.text)
    from datetime import datetime as dt
    from zoneinfo import ZoneInfo
    today = dt.now(ZoneInfo("Europe/London")).date().isoformat()
    m = post("/api/dispatch/manifest", {"date": today}).json()
    eq(len(m["rows"]), 1, "one booking today")
    row = m["rows"][0]
    ok(row["order_name"].startswith("#"), "order name stored with the entry: " + row["order_name"])
    ok(row["tracking"], "tracking present")
    eq(row["amount_ex_vat"], OPT.get("amount_ex_vat"), "ex VAT carried" if OPT.get("amount_ex_vat") else "no ex VAT on this option")
    eq(m["totals"]["shipments"], 1, "counted")
    # An empty day is an empty manifest, not an error.
    e = post("/api/dispatch/manifest", {"date": "2001-01-01"}).json()
    eq(e["rows"], [], "empty day")
    b = post("/api/dispatch/manifest", {"date": "nonsense"})
    eq(b.status_code, 400, "bad date refused plainly")

@test
def t_label_fetching_cannot_be_pointed_at_anything_but_world_options():
    # A URL that arrives in THEIR reply must never send this server fetching an
    # arbitrary address, including on a redirect.
    worldoptions.set_credentials(meter="1", key="k", password="p")
    for bad, why in [
        ("https://evil.example.com/x.pdf", "a foreign host"),
        ("https://service.worldoptions.co.uk@evil.com/x.pdf", "a userinfo trick"),
        ("http://169.254.169.254/latest/meta-data/", "cloud metadata"),
        ("https://127.0.0.1/x.pdf", "loopback"),
        ("file:///etc/passwd", "a file url"),
        ("https://10.0.0.5/x.pdf", "a private range"),
    ]:
        eq(worldoptions._label_url(bad), "", why + " is refused")
    ok(worldoptions._label_url("https://service.worldoptions.co.uk/a.pdf"), "their own host is allowed")
    eq(worldoptions._label_url("http://service.worldoptions.co.uk/a.pdf"),
       "https://service.worldoptions.co.uk/a.pdf", "http is upgraded, not trusted")
    ok(worldoptions._label_url("/x.pdf").startswith("https://service.worldoptions.co.uk/"),
       "a relative link resolves to their service host")

@test
def t_a_redirect_off_their_hosts_is_not_followed():
    # httpx's own follow_redirects would jump anywhere; every hop is re-validated.
    hops = []
    class FakeResp:
        def __init__(self, status, headers=None, content=b""):
            self.status_code = status; self.headers = headers or {}; self.content = content
    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url):
            hops.append(url)
            if "worldoptions" in url:
                return FakeResp(302, {"location": "http://169.254.169.254/latest/meta-data/"})
            return FakeResp(200, {}, b"SHOULD NEVER BE FETCHED")
    saved = worldoptions.httpx.AsyncClient
    worldoptions.httpx.AsyncClient = FakeClient
    try:
        status, body, final = run(worldoptions._get_label_bytes(
            "https://service.worldoptions.co.uk/a.pdf", 5.0))
        eq(body, b"", "nothing was fetched from the redirect target")
        eq(len(hops), 1, "the off-allowlist hop was never requested")
        ok("169.254" not in " ".join(hops), "metadata was never contacted")
    finally:
        worldoptions.httpx.AsyncClient = saved

@test
def t_an_oversized_label_is_refused_rather_than_rendered():
    eq(desk._pdf_print_images("A" * 24_000_001), [], "a huge base64 blob is not decoded")

@test
def t_print_cors_credentials_go_only_to_this_shop():
    # Every Shopify merchant owns a *.myshopify.com origin, so a wildcard on that
    # suffix handed credentialed CORS to every store on Shopify.
    src = copilot_source()
    ok('origin.endswith(".myshopify.com")' not in src,
       "no bare *.myshopify.com origin match remains")
    ok("own_shop and origin == own_shop" in src, "only this shop's own domain matches")

@test
def t_dependencies_are_pinned_and_the_mcp_fix_is_in():
    reqs = open(os.path.join(HERE, "requirements.in"), encoding="utf-8").read()
    for line in reqs.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        ok("==" in line, "pinned exactly: " + line)
    m = re.search(r"^mcp(?:\[[a-z,]+\])?==(\d+)\.(\d+)\.(\d+)$", reqs, re.M)
    ok(m and tuple(int(x) for x in m.groups()) >= (1, 28, 1),
       "mcp is on or after the release that fixes session hijacking (PYSEC-2026-3481/2/3)")


@test
def t_connector_sessions_expire_by_our_choice():
    """mcp 1.30 started closing idle sessions after 30 minutes by default. It
    is stated in server.py so a library update cannot change it unseen."""
    import server as srv
    eq(srv.MCP_SESSION_IDLE_SECS, 1800, "thirty minutes")
    eq(srv.MCP_HTTP["session_idle_timeout"], srv.MCP_SESSION_IDLE_SECS, "and it is what the endpoint is built with")
    import inspect as _ins
    ok("mcp.streamable_http_app(**MCP_HTTP)" in _ins.getsource(srv.build_app), "by the app exactly as served")


def _lock_packages(text: str) -> dict:
    """name -> (version, hashes) from a hashed lock written by `make lock`."""
    out, cur = {}, None
    for raw in text.splitlines():
        line = raw.strip()
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?==([^\s;\\]+)", raw)
        if m:
            cur = m.group(1).lower().replace("_", "-")
            out[cur] = [m.group(2), 0]
        elif line.startswith("--hash=sha256:") and cur:
            out[cur][1] += 1
    return out


@test
def t_the_locks_match_their_pins_and_carry_hashes():
    """requirements.in and forecast/requirements-service.in hold the exact
    pins; `make lock` compiles each into the hashed lock beside it, which is
    what the images and CI install. A pin raised without recompiling, or a
    package in the lock without a hash, fails here rather than in a build."""
    for pins_path, lock_path in (("requirements.in", "requirements.txt"),
                                 ("forecast/requirements-service.in", "forecast/requirements-service.txt"),
                                 ("forecast/requirements-m5.in", "forecast/requirements-m5.txt"),
                                 ("forecast/requirements-prophet.in", "forecast/requirements-prophet.txt")):
        pins = open(os.path.join(HERE, pins_path), encoding="utf-8").read()
        lock_text = open(os.path.join(HERE, lock_path), encoding="utf-8").read()
        ok("pip-compile --generate-hashes" in lock_text.split("\n", 3)[1], lock_path + " says how it is rebuilt")
        lock = _lock_packages(lock_text)
        ok(len(lock) >= 10, lock_path + " lists every package, not just the direct ones")
        for name, (ver, hashes) in lock.items():
            ok(hashes >= 1, lock_path + ": " + name + " has a hash")
        for line in pins.splitlines():
            m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?==(\S+)", line.strip())
            if not m:
                continue
            name = m.group(1).lower().replace("_", "-")
            ok(name in lock, lock_path + " has " + name)
            eq(lock[name][0], m.group(2), lock_path + ": " + name + " is the version " + pins_path + " pins")
    m5 = _lock_packages(open(os.path.join(HERE, "forecast", "requirements-m5.txt"), encoding="utf-8").read())
    service = _lock_packages(open(os.path.join(HERE, "forecast", "requirements-service.txt"), encoding="utf-8").read())
    prophet = _lock_packages(open(os.path.join(HERE, "forecast", "requirements-prophet.txt"), encoding="utf-8").read())
    for name, (ver, _h) in service.items():
        eq(m5.get(name, [None])[0], ver, "the M5 lock carries the whole service at its versions: " + name)
        eq(prophet.get(name, [None])[0], ver, "the Prophet lock carries the whole service at its versions: " + name)
    for name in set(m5) & set(prophet):
        eq(prophet[name][0], m5[name][0], "the two optional locks agree where they overlap: " + name)
    for extra in ("forecast/requirements.txt",):
        for line in open(os.path.join(HERE, extra), encoding="utf-8").read().splitlines():
            line = line.split("#")[0].strip()
            if line:
                ok(re.match(r"^[A-Za-z0-9._-]+==\S+$", line), extra + " pins exactly: " + line)


@test
def t_only_the_page_itself_may_use_the_camera():
    """The camera test in Settings needs the page's own camera; nothing framed
    inside the page gets it, and the microphone, location and payment stay
    shut to everyone."""
    pp = gate._API_HEADERS["Permissions-Policy"]
    ok("camera=(self)" in pp, pp)
    for shut in ("microphone=()", "geolocation=()", "payment=()"):
        ok(shut in pp, pp)


@test
def t_the_suite_cannot_reach_the_network():
    """The guard itself: a name, an address given as numbers (which skips the
    name lookup on the async path) and a name that merely starts like a
    loopback address are all refused, and loopback still works. The attempts
    are taken back off the record so the run loop does not charge this test."""
    import httpx as _hx
    before = len(NET_REACHED)
    try:
        for url in ("https://example.com/", "http://192.0.2.1/", "http://127.0.0.1.nip.io/"):
            for how in ("sync", "async"):
                try:
                    if how == "sync":
                        _hx.get(url, timeout=2)
                    else:
                        run(_hx.AsyncClient(timeout=2).get(url))
                    ok(False, how + " " + url + " reached the network")
                except (_hx.ConnectError, OSError):
                    pass
        hosts = set(NET_REACHED[before:])
        ok({"example.com", "192.0.2.1", "127.0.0.1.nip.io"} <= hosts, hosts)
        ok(_is_local("127.0.0.1") and _is_local("::1") and not _is_local("127.0.0.1.nip.io"))
        ok(not any(v in os.environ for v in ("HTTPS_PROXY", "https_proxy", "ANTHROPIC_BASE_URL")),
           "no proxy or alternative service address is inherited")
    finally:
        del NET_REACHED[before:]


@test
def t_a_run_leaves_no_scratch_folder_behind():
    """Each run made a gizmo-dispatch-tests-* folder in the system temp dir and
    nothing removed it, until 1,744 of them filled the disk (12 October 2026).
    Three children, each pointed at an empty temp dir of its own: one quick
    test, the same with KEEP_SCRATCH=1, and the part above the first test as
    a design rig runs it, which keeps its folder while it is up and drops it
    when it is killed."""
    import subprocess
    here = os.path.abspath(__file__)
    env = {k: v for k, v in os.environ.items() if k != "KEEP_SCRATCH"}
    rig = ("import sys\nsrc = open(sys.argv[1], encoding='utf-8').read()\n"
           "g = {'__name__': 'rig', '__file__': sys.argv[2]}\n"
           "exec(compile(src, 'harness', 'exec'), g)\n"
           "print(g['SCRATCH'], flush=True)\nsys.stdin.readline()\n")
    def child(argv, **extra):
        tmp = tempfile.mkdtemp(dir=SCRATCH)
        return tmp, subprocess.Popen([sys.executable] + argv, env=dict(env, TMPDIR=tmp, **extra),
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
    runs = [child([here], ONLY="t_config_creds_write_only"),
            child([here], ONLY="t_config_creds_write_only", KEEP_SCRATCH="1"),
            child(["-c", rig, os.path.join(os.path.dirname(here), "dispatch", "harness.py"), here])]
    try:
        tmp, p = runs[2]
        held = p.stdout.readline().strip()
        ok(held.startswith(tmp) and os.path.isdir(held),
           "a rig still serving keeps its folder: %r %s" % (held, "" if held else p.communicate(timeout=60)[1][-800:]))
        p.send_signal(signal.SIGTERM)
        p.wait(timeout=60)
        eq(p.returncode, 128 + signal.SIGTERM, "a kill ends it as an exit, so the cleanup runs")
        eq(os.listdir(tmp), [], "and the killed rig's folder is gone")

        tmp, p = runs[0]
        out, err = p.communicate(timeout=120)
        ok("1 passed, 0 failed" in out, out[-500:] + err[-800:])
        eq(os.listdir(tmp), [], "a run leaves nothing in the temp dir")

        tmp, p = runs[1]
        out, err = p.communicate(timeout=120)
        ok("1 passed, 0 failed" in out, out[-500:] + err[-800:])
        kept = os.listdir(tmp)
        ok(len(kept) == 1 and kept[0].startswith("gizmo-dispatch-tests-"), "KEEP_SCRATCH=1 keeps it: %r" % kept)
        ok("scratch kept: " + os.path.join(tmp, kept[0]) in err, "and says where")
    finally:
        for _tmp, p in runs:
            if p.poll() is None:
                p.kill()
                p.communicate()
    # The folders single tests make for themselves sit inside the scratch, so
    # they go with it; one made anywhere else is never removed.
    for args in re.findall(r"mkdtemp\(([^)]*)\)", open(here, encoding="utf-8").read()):
        ok(args in ('prefix="gizmo-dispatch-tests-"', "dir=SCRATCH"),
           "a temp folder made outside the scratch, with %s" % (args or "no arguments"))


@test
def t_the_permissions_settings_shows_are_read_from_shopify():
    """The suite gives the routes a refusing stand-in for this reader, so the
    real one is held here: it asks Shopify what the installation may do, names
    each write the app needs that is missing, keeps a good answer for a while,
    and reports a failed read as unknown, never as permissions missing."""
    seen = []
    answer = {}
    async def fake_request(method, path, **kw):
        seen.append((method, path, kw.get("body", {}).get("query", "")))
        if isinstance(answer.get("raise"), Exception):
            raise answer["raise"]
        return answer["data"]
    saved = (server._request, dict(server._granted_scopes))
    server._request = fake_request
    try:
        server._granted_scopes.update({"at": 0.0, "scopes": None, "error": ""})
        answer["data"] = {"data": {"currentAppInstallation": {"accessScopes": [
            {"handle": "read_orders"}, {"handle": "write_orders"}, {"handle": "write_fulfillments"}]}}}
        got = run(server.shopify_granted_scopes())
        ok("currentAppInstallation" in seen[0][2] and seen[0][:2] == ("POST", "graphql.json"), seen)
        eq(got["error"], "")
        eq(set(got["missing"]), {"write_merchant_managed_fulfillment_orders", "write_payment_terms",
                                 "read_shopify_payments_payouts", "read_shopify_payments_accounts"},
           "each missing write is named, and each read a feature needs")
        ok(all(got["missing"].values()), "with what it is for")
        ok("Xero sync" in got["missing"]["read_shopify_payments_accounts"],
           "the accounts scope is named for the payout note it holds up")
        run(server.shopify_granted_scopes())
        eq(len(seen), 1, "a good answer is kept rather than asked again")
        server._granted_scopes.update({"at": 0.0, "scopes": None, "error": ""})
        answer["raise"] = RuntimeError("Shopify refused the token")
        got = run(server.shopify_granted_scopes())
        eq((got["scopes"], got["missing"]), ([], {}), "a failed read claims nothing is missing")
        ok("refused" in got["error"], got)
    finally:
        server._request = saved[0]
        server._granted_scopes.clear(); server._granted_scopes.update(saved[1])


@test
def t_node_is_chosen_in_one_place():
    """CI ran whatever Node the runner image carried until the workflows named
    one, and then each named it for itself. .nvmrc holds it now: every
    setup-node step reads that file, and package.json's floor is the same."""
    major = open(os.path.join(HERE, ".nvmrc")).read().strip()
    ok(re.fullmatch(r"\d+", major), ".nvmrc holds a major version: %r" % major)
    steps = 0
    for wf in sorted(glob.glob(os.path.join(HERE, ".github", "workflows", "*.yml"))):
        text = open(wf, encoding="utf-8").read()
        name = os.path.basename(wf)
        ok("node-version:" not in text, name + " names a Node version of its own")
        eq(text.count("actions/setup-node@"), text.count("node-version-file: .nvmrc"),
           name + ": every setup-node step reads .nvmrc")
        steps += text.count("node-version-file: .nvmrc")
    ok(steps >= 2, "the test job and the weekly audit both set Node up")
    eq(json.load(open(os.path.join(HERE, "package.json")))["engines"]["node"], ">=" + major)


@test
def t_shopify_deploys_use_a_pinned_tool():
    """A deploy sends the app's permissions, extensions and webhook version to
    the store at once. Run as @latest, a new release of Shopify's tool could
    change what it sends with nothing here changing, so the Makefile names
    the version and its deploy only stages; releasing is its own step."""
    mk = open(os.path.join(HERE, "Makefile"), encoding="utf-8").read()
    ok(re.search(r"^SHOPIFY = npx --yes @shopify/cli@\d+\.\d+\.\d+$", mk, re.M),
       "the Makefile pins an exact version of Shopify's tool")
    deploy = mk.split("\nshopify-deploy:\n", 1)[1].split("\n", 1)[0]
    ok("app deploy --no-release" in deploy, "and its deploy stages without releasing: " + deploy)
    for f in ("README.md", "Makefile", "forecast/README.md"):
        ok("@shopify/cli@latest" not in open(os.path.join(HERE, f), encoding="utf-8").read(),
           f + " deploys with whatever version is newest")


@test
def t_every_image_is_pinned_by_digest_and_runs_the_tested_python():
    """A build must get exactly the image that was tested: a tag alone moves
    whenever the image is rebuilt. And the images run the Python the suites
    ran on in CI."""
    ci = open(os.path.join(HERE, ".github", "workflows", "tests.yml"), encoding="utf-8").read()
    tested = set(re.findall(r"python-version: '(\d+\.\d+)'", ci))
    eq(len(tested), 1, "CI tests one Python")
    for path in ("Dockerfile", os.path.join("forecast", "Dockerfile")):
        froms = re.findall(r"^FROM\s+(\S+)", open(os.path.join(HERE, path), encoding="utf-8").read(), re.M)
        ok(froms, path + " has a base image")
        for ref in froms:
            ok(re.search(r"@sha256:[0-9a-f]{64}$", ref), path + " pins " + ref + " by digest")
            m = re.match(r"python:(\d+\.\d+)", ref)
            ok(m and m.group(1) in tested, path + " runs the Python CI tests: " + ref)


@test
def t_app_errors_are_recorded_and_surfaced():
    # A 500 in the dispatch flow used to be invisible unless somebody was watching
    # the server log, which at a dispatch desk means never.
    errors.ERRORS_PATH = SCRATCH + "/app_errors.json"
    try:
        os.remove(errors.ERRORS_PATH)
    except FileNotFoundError:
        pass
    errors._record_error("booking a courier", ValueError("boom"))
    rows = errors._recent_errors(24)
    eq(len(rows), 1, "recorded")
    eq(rows[0]["where"], "booking a courier", "says where")
    ok("ValueError: boom" in rows[0]["error"], "and what")
    # It must never itself raise inside an error path.
    errors.ERRORS_PATH = "/nonexistent-dir-xyz/errors.json"
    errors._record_error("somewhere", RuntimeError("x"))   # must not raise
    errors.ERRORS_PATH = SCRATCH + "/app_errors.json"

@test
def t_weekly_snapshot_writes_once_a_week_and_excludes_credentials():
    backup.BACKUP_STATE_PATH = SCRATCH + "/backup_state.json"
    backup.BACKUP_SNAPSHOT_DIR = SCRATCH + "/snapshots"
    for f in glob.glob(backup.BACKUP_SNAPSHOT_DIR + "/*.zip"):
        os.remove(f)
    try:
        os.remove(backup.BACKUP_STATE_PATH)
    except FileNotFoundError:
        pass
    ok(backup._weekly_snapshot(), "writes the first time")
    made = glob.glob(backup.BACKUP_SNAPSHOT_DIR + "/*.zip")
    eq(len(made), 1, "one snapshot on disk")
    eq(backup._weekly_snapshot(), False, "and not again within the week")
    import zipfile
    names = zipfile.ZipFile(made[0]).namelist()
    ok(names, "the zip has contents")
    for n in names:
        ok("wo_secret" not in n and "google_oauth" not in n,
           "no credential file in a snapshot: " + n)

def _oldest_accessible_shopify_version(now=None) -> str:
    """Shopify's rule: a version is released on the 1st of its quarter at
    17:00 UTC and stays accessible until the 16th of the same month a year
    later at 15:00 UTC (2025-10 until 2026-10-16), then is silently served
    from the oldest one still accessible."""
    from datetime import datetime as _dt, timezone as _tz
    now = now or _dt.now(_tz.utc)
    live = []
    for y in range(now.year - 2, now.year + 1):
        for m in (1, 4, 7, 10):
            released = _dt(y, m, 1, 17, tzinfo=_tz.utc)
            gone = _dt(y + 1, m, 16, 15, tzinfo=_tz.utc)
            if released <= now < gone:
                live.append("%d-%02d" % (y, m))
    return min(live)


@test
def t_the_shopify_api_version_is_supported():
    """2024-10 fell out of Shopify's support window, and an unsupported version
    is silently served from the oldest supported one. The floor is worked out
    from today's date, not written down, so a pin that ages out fails here
    rather than months later (a written "2025-10" would have passed after
    2026-10-16, when 2025-10 stopped being served)."""
    from datetime import datetime as _dt, timezone as _tz
    eq(_oldest_accessible_shopify_version(_dt(2026, 10, 2, tzinfo=_tz.utc)), "2025-10", "the rule, checked")
    eq(_oldest_accessible_shopify_version(_dt(2026, 10, 17, tzinfo=_tz.utc)), "2026-01", "2025-10 goes on the 16th")
    floor = _oldest_accessible_shopify_version()
    import server as srv
    ok(srv.API_VERSION >= floor, "the Admin API on a served version, not " + srv.API_VERSION)
    pins = {"shopify.app.toml": open(os.path.join(HERE, "shopify.app.toml"), encoding="utf-8").read()}
    for ext in sorted(glob.glob(os.path.join(HERE, "extensions", "*", "shopify.extension.toml"))):
        pins[os.path.relpath(ext, HERE)] = open(ext, encoding="utf-8").read()
    found = []
    for name, text in pins.items():
        for v in re.findall(r'^\s*api_version\s*=\s*["\'](\d{4}-\d{2})["\']', text, re.M):
            found.append(name)
            ok(v >= floor, name + " pins " + v + ", older than the oldest served version " + floor)
    ok({"shopify.app.toml", os.path.join("extensions", "print-label-order", "shopify.extension.toml"),
        os.path.join("extensions", "print-label-bulk", "shopify.extension.toml")} <= set(found),
       "every known pin was read, so none is skipped unchecked: " + ", ".join(sorted(found)))
    fc = re.search(r'^API_VERSION = os\.environ\.get\("SHOPIFY_API_VERSION", "(\d{4}-\d{2})"\)',
                   open(os.path.join(HERE, "forecast", "ingest.py"), encoding="utf-8").read(), re.M)
    ok(fc and fc.group(1) >= floor, "and the forecast's own reads")
    eq(fc and fc.group(1), re.search(r'"SHOPIFY_API_VERSION", "(\d{4}-\d{2})"',
                                     open(os.path.join(HERE, "server.py"), encoding="utf-8").read()).group(1),
       "the forecast's default is the app's, so one move moves both")

@test
def t_customs_values_are_remembered_per_product():
    # The store prices custom gobos through option dropdowns, so their base price
    # is zero and every international order needed the real value typed in again.
    desk.CUSTOMS_MEMORY_PATH = SCRATCH + "/customs_memory.json"
    try:
        os.remove(desk.CUSTOMS_MEMORY_PATH)
    except FileNotFoundError:
        pass
    desk._remember_customs([
        {"key": "v111", "unit_price": 425.0, "hs": "9008.50.00", "country": "CN",
         "description": "Projector"},
        {"key": "t create your own gobo", "unit_price": 38.5, "hs": "9002.20.000",
         "country": "GB", "description": "Custom gobo"},
        {"key": "v999", "unit_price": 0, "hs": "", "country": "GB"},   # zero: not worth remembering
        {"key": "", "unit_price": 12.0},                                # no key: nothing to file under
    ])
    mem = desk._load_customs_memory()
    eq(sorted(mem), ["t create your own gobo", "v111"], "only real values, only keyed ones")
    eq(mem["v111"]["unit_value"], "425.00", "stored to the penny")
    eq(mem["t create your own gobo"]["hs"], "9002.20.000", "and its HS code")

@test
def t_a_remembered_value_beats_the_derived_one():
    desk.CUSTOMS_MEMORY_PATH = SCRATCH + "/customs_memory.json"
    desk._remember_customs([{"key": "v111", "unit_price": 500.0, "hs": "9008.50.00",
                                "country": "CN", "description": "Projector"}])
    order = {"id": 12345, "name": "#12345", "currency": "GBP", "email": "c@x.co",
             "shipping_address": {"first_name": "A", "last_name": "B", "address1": "1 Rue",
                                  "city": "Paris", "zip": "75001", "country_code": "FR",
                                  "phone": "0033", "name": "A B"},
             "line_items": [{"id": 1, "title": "Projected Image 200 Watt Gobo Projector",
                             "quantity": 1, "price": "780.00", "variant_id": 111}]}
    async def tools(registry, name, args):
        if name == "shopify_get_order":
            return order
        if name == "shopify_get_variant":
            return {"id": 111, "inventory_item_id": 9111}
        if name == "shopify_get_inventory_items":
            return {"inventory_items": [{"id": 9111, "cost": "425.00",
                                         "harmonized_system_code": "9008.50.00"}]}
        return {}
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        it = (r.json().get("customs_items") or [])[0]
        eq(it["unit_value"], "500.00", "what was typed last time, not the 425.00 cost")
        eq(it["value_basis"], "remembered", "and it says so, so it can be corrected knowingly")
        eq(it["key"], "v111", "keyed to the variant so the next order finds it")
    finally:
        shopify._tool_json = saved
        try:
            os.remove(desk.CUSTOMS_MEMORY_PATH)
        except FileNotFoundError:
            pass

@test
def t_a_booking_records_which_staff_member_made_it():
    reset_dispatch(); reset_prod()
    r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
    eq(r.status_code, 200, r.text)
    entry = desk._load_dispatch()["12345"]
    # The test token's `sub` claim is the staff user id Shopify sends.
    ok("by" in entry, "the record has a by field")
    from datetime import datetime as dt
    from zoneinfo import ZoneInfo
    today = dt.now(ZoneInfo("Europe/London")).date().isoformat()
    row = post("/api/dispatch/manifest", {"date": today}).json()["rows"][0]
    ok("by" in row, "and the manifest carries it")

@test
def t_margin_is_net_of_vat_discounts_goods_and_carriage():
    # UK prices are tax inclusive, so the gross figure is not revenue: the VAT
    # belongs to HMRC while the cost price it is compared against is already net.
    reset_dispatch(); reset_prod()
    r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
    eq(r.status_code, 200, r.text)
    # 120.00 inc VAT (20.00 of it tax) less a 10.00 discount, plus 9.00 shipping
    # inc 1.50 tax. Goods cost 30.00 each. Courier 12.40 ex VAT (from OPT).
    order = {"id": 12345, "name": "#104300", "currency": "GBP",
             "created_at": "2026-08-12T09:00:00Z", "taxes_included": True,
             "line_items": [{"id": 1, "title": "Gobo", "quantity": 2, "price": "60.00",
                             "variant_id": 111,
                             "tax_lines": [{"price": "20.00"}],
                             "discount_allocations": [{"amount": "10.00"}]}],
             "shipping_lines": [{"price": "9.00", "tax_lines": [{"price": "1.50"}]}]}
    async def tools(registry, name, args):
        if name == "shopify_list_orders":
            return {"orders": [order]}
        if name == "shopify_get_order":
            return order
        if name == "shopify_get_variant":
            return {"id": 111, "inventory_item_id": 9111}
        if name == "shopify_get_inventory_items":
            return {"inventory_items": [{"id": 9111, "cost": "30.00"}]}
        return {}
    saved = shopify._tool_json; shopify._tool_json = tools
    desk.COST_CACHE_PATH = SCRATCH + "/cost_cache.json"
    try:
        os.remove(desk.COST_CACHE_PATH)
    except FileNotFoundError:
        pass
    try:
        res = run(desk.run_margin_report({}, days=30))
        eq(len(res["rows"]), 1, "the dispatched order is there: " + json.dumps(res)[:200])
        row = res["rows"][0]
        eq(row["revenue"], 90.0, "120 gross less 20 VAT less 10 discount")
        eq(row["shipping_charged"], 7.5, "9.00 less its 1.50 of VAT")
        eq(row["goods_cost"], 60.0, "2 x 30.00")
        # OPT has no ex VAT figure, as records written before today do not, so the
        # gross charge is used and the row says so.
        eq(row["courier_cost"], 12.4, "falls back to the gross charge")
        eq(row["courier_inc_vat"], True, "and flags that it includes VAT")
        eq(row["margin"], 25.1, "90 + 7.5 - 60 - 12.4")
        eq(res["totals"]["margin"], 25.1, "and it totals")
        eq(res["totals"]["courier_inc_vat_rows"], 1, "counted so the UI can say so")
    finally:
        shopify._tool_json = saved

@test
def t_an_item_without_a_cost_is_flagged_not_counted_as_profit():
    # A missing cost silently reads as pure profit, which is the one wrong answer
    # worth avoiding in a margin report.
    reset_dispatch(); reset_prod()
    post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
    order = {"id": 12345, "name": "#104301", "currency": "GBP", "taxes_included": True,
             "created_at": "2026-08-12T09:00:00Z",
             "line_items": [{"id": 1, "title": "Mystery Item", "quantity": 1,
                             "price": "50.00", "variant_id": 222}],
             "shipping_lines": []}
    async def tools(registry, name, args):
        if name == "shopify_list_orders":
            return {"orders": [order]}
        if name == "shopify_get_variant":
            return {"id": 222, "inventory_item_id": 9222}
        if name == "shopify_get_inventory_items":
            return {"inventory_items": [{"id": 9222, "cost": ""}]}   # no cost set
        return {}
    saved = shopify._tool_json; shopify._tool_json = tools
    desk.COST_CACHE_PATH = SCRATCH + "/cost_cache2.json"
    try:
        res = run(desk.run_margin_report({}, days=30))
        row = res["rows"][0]
        ok("margin" not in row, "no margin is claimed for it")
        ok("Mystery Item" in row.get("incomplete", ""), "and it names what is missing")
        eq(res["totals"]["counted"], 0, "excluded from the totals")
        eq(res["orders_incomplete"], 1, "and counted as incomplete")
    finally:
        shopify._tool_json = saved

@test
def t_variant_costs_are_cached_so_a_report_is_not_hundreds_of_calls():
    desk.COST_CACHE_PATH = SCRATCH + "/cost_cache3.json"
    try:
        os.remove(desk.COST_CACHE_PATH)
    except FileNotFoundError:
        pass
    calls = {"n": 0}
    async def tools(registry, name, args):
        calls["n"] += 1
        if name == "shopify_get_variant":
            return {"id": args["variant_id"], "inventory_item_id": 9000 + args["variant_id"]}
        if name == "shopify_get_inventory_items":
            return {"inventory_items": [{"id": int(i), "cost": "5.00"}
                                        for i in args["ids"].split(",")]}
        return {}
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        first = run(desk._variant_costs({}, [1, 2, 3]))
        eq(first, {1: "5.00", 2: "5.00", 3: "5.00"}, "costs resolved")
        used = calls["n"]
        ok(used <= 4, "three variants plus one batched inventory call: " + str(used))
        again = run(desk._variant_costs({}, [1, 2, 3]))
        eq(again, first, "same answer from cache")
        eq(calls["n"], used, "and no further calls at all")
    finally:
        shopify._tool_json = saved

@test
def t_unfulfilling_one_order_cannot_erase_another_booking():
    # _unfulfill_dispatch held a whole-store snapshot across an await on Shopify.
    # A booking that completed inside that window was wiped when the snapshot was
    # written back, taking the tracking number of a CHARGED label with it and
    # re-arming the double-book guard.
    reset_dispatch(); reset_prod()
    desk._record_dispatch(111, {"tracking_number": "T111", "fulfilled": True,
                                   "fulfillment_id": 555, "dispatched_at": "2026-08-13T09:00:00+00:00"})
    async def slow_cancel(fid):
        # A second operator books an order while Shopify is still thinking.
        desk._record_dispatch(222, {"tracking_number": "T222", "fulfilled": False,
                                       "dispatched_at": "2026-08-13T09:00:05+00:00"})
        return {"ok": True}
    saved = shopify._fulfillment_canceler
    shopify._fulfillment_canceler = slow_cancel
    try:
        run(orderbook._unfulfill_dispatch({}, 111))
        store = desk._load_dispatch()
        ok("222" in store, "the booking made during the await SURVIVES: " + str(sorted(store)))
        eq(store["222"]["tracking_number"], "T222", "with its tracking intact")
        eq(store["111"].get("fulfilled"), False, "and the un-fulfil still applied")
    finally:
        shopify._fulfillment_canceler = saved

@test
def t_a_cancelled_shipment_stops_claiming_it_is_fulfilled():
    reset_dispatch(); reset_prod()
    desk._record_dispatch(12345, {"tracking_number": "T1", "fulfilled": True,
                                     "fulfillment_id": 777, "carrier_name": "UPS",
                                     "dispatched_at": "2026-08-13T09:00:00+00:00"})
    async def canceler(fid):
        return {"ok": True}
    savedc = shopify._fulfillment_canceler; shopify._fulfillment_canceler = canceler
    async def voider(service, action, inner, retryable=True):
        return ET.fromstring(VOID_XML)
    saveds = worldoptions._soap_call; worldoptions._soap_call = voider
    try:
        r = post("/api/dispatch/cancel", {"order_id": 12345, "tracking_number": "T1"})
        eq(r.status_code, 200, r.text)
        e = desk._load_dispatch()["12345"]
        eq(e.get("canceled"), True, "marked cancelled")
        eq(e.get("fulfilled"), False, "and no longer claims to be fulfilled")
        ok("fulfillment_id" not in e, "the dead fulfilment id is dropped")
    finally:
        shopify._fulfillment_canceler = savedc
        worldoptions._soap_call = saveds

@test
def t_rebooking_still_asks_when_shopify_never_undid_the_fulfilment():
    # The confirmation was waived for ANY cancelled entry, including one whose
    # Shopify fulfilment could not be undone: the re-book then went through
    # silently and the new tracking never reached the customer.
    reset_dispatch(); reset_prod()
    desk._record_dispatch(12345, {"tracking_number": "T1", "canceled": True,
                                     "fulfilled": True, "fulfillment_id": 777,
                                     "dispatched_at": "2026-08-13T09:00:00+00:00"})
    saved_status = orderbook._order_status
    orderbook._order_status = lambda o: "fulfilled"
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        body = r.json()
        ok(body.get("needs_force"), "still asks before spending: " + json.dumps(body)[:160])
    finally:
        orderbook._order_status = saved_status

@test
def t_a_timeout_wording_is_never_treated_as_transient():
    # A timeout is the unknown-outcome case: the shipment may exist. Only clearly
    # infrastructural refusals may be retried.
    ok(desk._WO_TRANSIENT_RE.search("Could not create SSL/TLS secure channel"), "ssl is transient")
    ok(desk._WO_TRANSIENT_RE.search("Service Unavailable"), "503 wording is transient")
    for never in ("The request timed out", "Operation timeout", "Ready date should be in format",
                  "Customer authentication failed"):
        eq(bool(desk._WO_TRANSIENT_RE.search(never)), False, never + " is NOT retried")

@test
def t_an_order_already_fulfilled_in_shopify_stops_being_retried_forever():
    # A retried fulfilment POST can succeed on a hop whose reply is lost. The next
    # pass got nothing_to_fulfill and left fulfilled=False, so the app re-attempted
    # for ever and showed a dispatched order as unfulfilled.
    reset_dispatch(); reset_prod()
    desk._record_dispatch(12345, {"tracking_number": "T1", "fulfilled": False,
                                     "carrier_name": "UPS", "notify": True,
                                     "dispatched_at": "2026-08-13T09:00:00+00:00"})
    mark_made(12345, True)
    async def already(oid, **kw):
        return {"ok": False, "reason": "nothing_to_fulfill", "detail": "no open fulfillment orders"}
    savedw = shopify._fulfillment_writer; shopify._fulfillment_writer = already
    saveds = orderbook._order_status; orderbook._order_status = lambda o: "fulfilled"
    TAG_WRITES.clear()
    try:
        res = run(orderbook._fulfill_if_ready({}, 12345))
        eq(res["fulfilled"], True, "treated as done: " + json.dumps(res)[:140])
        eq(desk._load_dispatch()["12345"]["fulfilled"], True, "and recorded, so it stops retrying")
    finally:
        shopify._fulfillment_writer = savedw
        orderbook._order_status = saveds
    # B11 in the 2026-09-19 bug audit: nothing was created here, so nobody was
    # emailed from here, and the order still has to leave To ship. Straight
    # through the gate this time, with the stamps set by hand, so the made
    # route's own fulfilment pass does not get there first.
    reset_dispatch(); reset_prod()
    desk._record_dispatch(12345, {"tracking_number": "T1", "fulfilled": False, "carrier_name": "UPS",
                                     "notify": True, "dispatched_at": "2026-08-13T09:00:00+00:00"})
    production._mark_made(12345, True)
    shopify._fulfillment_writer = already
    orderbook._order_status = lambda o: "fulfilled"
    TAG_WRITES.clear()
    try:
        res = run(orderbook._fulfill_if_ready({}, 12345))
        eq(res["reason"], "already_fulfilled", json.dumps(res)[:200])
        eq(res["notified"], False, "no tracking email went from here")
        eq(desk._load_dispatch()["12345"]["notified"], False, "and the record says so")
        moved = [t for o, t in TAG_WRITES if o == 12345]
        ok(moved and "Complete" in moved[-1] and "PC" not in moved[-1],
           "filed as complete although Shopify reads it as fulfilled: " + str(TAG_WRITES))
    finally:
        shopify._fulfillment_writer = savedw
        orderbook._order_status = saveds
        reset_dispatch(); reset_prod()

@test
def t_a_corrupt_merchant_store_is_preserved_not_overwritten():
    # Skills and memory are hand-written. A corrupt file must be kept for repair,
    # not replaced by whatever loaded as the empty default.
    for owner, path_attr, writer, payload in ((skillbook, "SKILLS_PATH", skillbook._write_skills, [{"title": "x", "body": "y"}]),
                                              (memory, "MEMORY_PATH", memory._write_memory, [{"text": "x"}])):
        path = SCRATCH + "/" + path_attr.lower() + ".json"
        setattr(owner, path_attr, path)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{ this is not json")
        jsonstore._poisoned_stores.discard(path)
        jsonstore._load_json_store(path, "x", [])        # marks it poisoned
        writer(payload)
        kept = open(path, encoding="utf-8").read()
        ok("not json" in kept, path_attr + " was preserved for repair, not overwritten")
        jsonstore._poisoned_stores.discard(path)
        # The corrupt file used to be left behind, and the loaders read it as
        # empty and overwrote it for the next test; now they pause the writer
        # instead, so the wreck has to be cleared away here.
        os.remove(path)

@test
def t_an_unreadable_booking_reply_warns_about_a_possible_charge():
    async def garbled(service, action, inner, retryable=True):
        if service == "ShipmentService":
            return ET.fromstring("<Envelope><Body><Nonsense/></Body></Envelope>")
        return ET.fromstring(RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = garbled
    try:
        reset_dispatch(); reset_prod()
        r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        msg = r.json().get("error", "")
        ok("MAY still have been booked" in msg, "warns rather than inviting a retry: " + msg[:120])
    finally:
        worldoptions._soap_call = saved

@test
def t_orders_tagged_before_the_rename_still_show_in_the_finished_queue():
    # The finished tag was renamed from Dispatched to Complete. Anything finished
    # before that still carries the old word and must not vanish from the app.
    old_order = {**ORDER, "id": 777, "name": "#777", "tags": "Dispatched"}
    new_order = {**ORDER, "id": 888, "name": "#888", "tags": "Complete"}
    async def tools(registry, name, args):
        if name == "shopify_list_orders":
            return {"orders": [old_order, new_order]}
        return {}
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        res = run(production.run_production_labels({}, tag=desk.DISPATCHED_TAG))
        ids = sorted(o["id"] for o in res["orders"])
        eq(ids, [777, 888], "both the old and the new tag appear: " + str(ids))
        # A different queue must NOT pick up the legacy word.
        res2 = run(production.run_production_labels({}, tag=orderbook.MADE_TAG))
        eq([o["id"] for o in res2["orders"]], [], "the legacy tag only widens the finished queue")
    finally:
        shopify._tool_json = saved


