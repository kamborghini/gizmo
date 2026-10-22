# ---- Custom address dispatch ------------------------------------------------

PASTED = """Sarah Fielding
Northern Stage
Barras Bridge
Newcastle upon Tyne
NE1 7RH
Tel: 0191 230 5151
sarah@northernstage.co.uk"""

CUST_ADDR = {"name": "Sarah Fielding", "company": "Northern Stage", "street": "Barras Bridge",
             "street2": "", "city": "Newcastle upon Tyne", "state": "", "postcode": "NE1 7RH",
             "country": "GB", "phone": "0191 230 5151", "email": "sarah@northernstage.co.uk"}

def custom_body(**over):
    b = {"id": "cs" + "testship01", "option": OPT, "address": dict(CUST_ADDR), "box": dict(BOX),
         "reference": "Replacement gobo", "contents": "Glass gobo", "declared": 85}
    b.update(over)
    return b

@test
def t_a_pasted_address_becomes_courier_fields():
    a = desk._parse_address(PASTED)
    ok(a["confident"], "a normal UK block reads without help")
    d = a["address"]
    eq(d["postcode"], "NE1 7RH", "postcode")
    eq(d["city"], "Newcastle upon Tyne", "city")
    eq(d["country"], "GB", "a UK postcode means GB even when nobody said so")
    eq(d["email"], "sarah@northernstage.co.uk", "email lifted out")
    ok("0191" in d["phone"], "phone lifted out, label stripped: " + d["phone"])
    eq(d["name"], "Sarah Fielding", "the person")
    eq(d["company"], "Northern Stage", "the venue")
    eq(d["street"], "Barras Bridge", "and the street is not lost")

@test
def t_no_address_line_is_ever_silently_dropped():
    # The failure that matters: a line that cannot be classified must still reach
    # the label, because half an address is a lost parcel.
    a = desk._parse_address("Jo Bloggs\nThe Old Dairy\nSomewhere Yard\nBack Passage\nYork\nYO1 7HH")
    d = a["address"]
    joined = " ".join([d["name"], d["company"], d["street"], d["street2"], d["city"]])
    for line in ("Jo Bloggs", "The Old Dairy", "Somewhere Yard", "Back Passage", "York"):
        ok(line in joined, line + " survived the parse")

@test
def t_a_house_number_is_never_read_as_a_postcode():
    # Both are just digits. Reading "1200 Kingston Road" as postcode 1200 shifts
    # every field along, and because the stolen digits fill the last empty
    # required field the mangled parse is the one that scores confident, so
    # nothing asks Claude and nothing warns the merchant.
    eq(desk._find_postcode("1200 Kingston Road", "GB"), ("", "1200 Kingston Road"),
       "a house number leading a street is not a postcode")
    eq(desk._find_postcode("123 Main St 90210", "US")[0], "90210",
       "but a real ZIP after one still is")
    eq(desk._find_postcode("10115 Berlin", "DE")[0], "10115",
       "and Germany writes the postcode before the town")
    r = desk._parse_address("Jane Doe\nRiverside Studios\n1200 Kingston Road\nLondon\nUnited Kingdom")
    a = r["address"]
    eq(a["postcode"], "", "no postcode was invented")
    ok("1200" in a["street"], "the house number stayed on the street line: " + a["street"])
    ok(not r["confident"], "and it does not claim to have read the address")

@test
def t_an_unrecognised_country_is_refused_not_truncated():
    # Cutting a name to two letters always produces something that looks valid:
    # Isle of Man becomes IS, which is Iceland.
    for name, code in [("Isle of Man", "IM"), ("Guernsey", "GG"), ("Bermuda", "BM"),
                       ("Pakistan", "PK"), ("Iraq", "IQ"), ("Costa Rica", "CR")]:
        eq(desk._clean_address({"country": name})["country"], code, name)
    unknown = desk._clean_address({"country": "Republic of Nowhere"})
    eq(unknown["country"], "Republic of Nowhere", "an unknown name is left as typed")
    ok(desk._country_ready(unknown), "and refused rather than guessed at")
    eq(desk._country_ready({"country": "GB"}), "", "a real code passes")

@test
def t_a_bad_country_cannot_reach_world_options():
    reset_dispatch(); reset_prod()
    bad = dict(CUST_ADDR); bad["country"] = "Republic of Nowhere"
    q = post("/api/custom/quote", {"address": bad, "box": dict(BOX)})
    eq(q.status_code, 400, q.text)
    ok("2-letter" in q.json()["error"], q.json()["error"])
    b = post("/api/custom/book", custom_body(id="csbadcountry", address=bad))
    eq(b.status_code, 400, b.text)
    ok("2-letter" in b.json()["error"], b.json()["error"])

@test
def t_an_unreadable_paste_says_so_rather_than_guessing():
    a = desk._parse_address("give it to dave when you see him")
    ok(not a["confident"], "it does not claim to have read an address")
    ok(desk._addr_ready(a["address"]), "and the address is still incomplete")

@test
def t_a_custom_shipment_can_never_be_keyed_like_an_order():
    # The whole safety argument: a Shopify order id is all digits, so a prefixed
    # key cannot collide with one, whatever the browser sends.
    ok(desk._custom_id("abc123def").startswith("adhoc:"), "always namespaced")
    eq(desk._custom_id("adhoc:abc123def"), "adhoc:abc123def", "already-prefixed is kept")
    eq(desk._custom_id("12345"), "", "an order-shaped id is refused")
    eq(desk._custom_id("../../etc/passwd"), "", "and so is anything with a path in it")
    eq(desk._custom_id(""), "", "and nothing at all")
    ok(desk._is_adhoc("adhoc:x"), "recognised")
    ok(not desk._is_adhoc("12345"), "an order is not ad-hoc")

@test
def t_a_custom_booking_never_touches_shopify():
    reset_dispatch(); reset_prod()
    TAG_WRITES.clear(); FULFILLED.clear()
    r = post("/api/custom/book", custom_body())
    eq(r.status_code, 200, r.text)
    d = r.json()
    ok(d.get("ok"), "it booked")
    ok(d["id"].startswith("adhoc:"), "under an ad-hoc key: " + d["id"])
    eq(TAG_WRITES, [], "no order was tagged")
    eq(FULFILLED, [], "no order was fulfilled, so no customer was emailed")
    entry = desk._load_dispatch()[d["id"]]
    ok(entry["tracking_number"], "the charge is recorded")
    eq(entry["notify"], False, "and nothing is armed to email later")
    eq(entry["fulfilled"], False, "there is nothing to fulfil")
    eq(entry["order_name"], "Replacement gobo", "the manifest reads the typed reference")
    eq(entry["shipping_paid"], "", "nobody paid this app for carriage")

@test
def t_booking_the_same_custom_shipment_twice_is_refused():
    # With no order id, the id the browser minted is the ONLY thing that can tell
    # a second click apart from a second parcel.
    reset_dispatch(); reset_prod()
    first = post("/api/custom/book", custom_body())
    eq(first.status_code, 200, first.text)
    again = post("/api/custom/book", custom_body())
    eq(again.status_code, 400, "the second attempt is refused")
    ok("already booked" in again.json()["error"], again.json()["error"])

@test
def t_the_declared_value_follows_the_insured_amount():
    # Insuring a parcel declared at zero is an argument the insurer wins.
    reset_dispatch(); reset_prod()
    r = post("/api/custom/book", custom_body(id="csvaluetest1", declared=0, insurance=250))
    eq(r.status_code, 200, r.text)
    eq(desk._load_dispatch()[r.json()["id"]]["declared"], 250.0,
       "the declared value fell back to what it was insured for")

@test
def t_a_custom_shipment_stays_out_of_the_order_margin_report():
    # It has no revenue and no goods cost, so it has no margin. It must not show
    # up as "the order could not be loaded from Shopify", which is how the app
    # says real data is missing.
    reset_dispatch(); reset_prod()
    post("/api/custom/book", custom_body(id="csmargintest"))
    async def tools(registry, name, args):
        if name == "shopify_list_orders":
            return {"orders": []}
        return {}
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        res = run(desk.run_margin_report({}, days=30))
        eq(res["rows"], [], "no row at all")
        ok("incomplete" not in json.dumps(res), "and nothing reported as missing data")
    finally:
        shopify._tool_json = saved

@test
def t_a_custom_shipment_appears_on_the_days_manifest():
    # The courier collects it with everything else, so it belongs on the sheet.
    reset_dispatch(); reset_prod()
    r = post("/api/custom/book", custom_body(id="csmanifest01"))
    eq(r.status_code, 200, r.text)
    from datetime import datetime as dt
    from zoneinfo import ZoneInfo
    today = dt.now(ZoneInfo("Europe/London")).date().isoformat()
    rows = post("/api/dispatch/manifest", {"date": today}).json()["rows"]
    row = next((x for x in rows if x["order_id"].startswith("adhoc:")), None)
    ok(row, "it is on the manifest")
    eq(row["order_name"], "Replacement gobo", "named by its reference, not its key")
    eq(row["customer"], "Northern Stage", "and by who it is going to")

@test
def t_a_custom_label_can_be_reprinted():
    reset_dispatch(); reset_prod()
    r = post("/api/custom/book", custom_body(id="cslabeltest1"))
    eq(r.status_code, 200, r.text)
    sid = r.json()["id"]
    again = post("/api/dispatch/label", {"id": sid})
    eq(again.status_code, 200, again.text)
    ok(again.json().get("labels"), "the stored label comes back")
    listed = post("/api/custom/list", {}).json()["shipments"]
    ok(any(s["id"] == sid for s in listed), "and it is findable after the window closes")

@test
def t_cancelling_a_custom_shipment_skips_the_shopify_repair():
    reset_dispatch(); reset_prod()
    CANCELED_FULFILLMENTS.clear(); TAG_WRITES.clear()
    r = post("/api/custom/book", custom_body(id="cscanceltest"))
    sid = r.json()["id"]
    tn = r.json()["dispatch"]["tracking_number"]
    c = post("/api/dispatch/cancel", {"id": sid, "tracking_number": tn})
    eq(c.status_code, 200, c.text)
    ok(desk._load_dispatch()[sid]["canceled"], "the record says cancelled")
    eq(CANCELED_FULFILLMENTS, [], "no Shopify fulfilment was cancelled")
    eq(TAG_WRITES, [], "and no order was re-tagged")
    # Cancelled means it can be booked again.
    again = post("/api/custom/book", custom_body(id="cscanceltest"))
    eq(again.status_code, 200, "rebooking after a cancel is allowed")

@test
def t_an_international_custom_shipment_refuses_to_go_without_a_declaration():
    # With no order behind it nothing can be prefilled, so an empty dossier is
    # the likely mistake. It must be refused, not sent.
    reset_dispatch(); reset_prod()
    de = dict(CUST_ADDR); de.update({"country": "DE", "postcode": "10115", "city": "Berlin"})
    # No EORI is the first refusal, before anything reaches World Options.
    no_eori = post("/api/custom/book", custom_body(id="csintl00001", address=de))
    eq(no_eori.status_code, 400, no_eori.text)
    ok("EORI" in no_eori.json()["error"], no_eori.json()["error"])
    cfgp = SCRATCH + "/shipping.json"
    saved_cfg = open(cfgp).read() if os.path.exists(cfgp) else None
    cur = json.loads(saved_cfg) if saved_cfg else {}
    cur["eori"] = "GB123456789000"
    json.dump(cur, open(cfgp, "w"))
    try:
        r = post("/api/custom/book", custom_body(id="csintl00001", address=de))
        eq(r.status_code, 400, r.text)
        ok("customs" in r.json()["error"].lower(), r.json()["error"])
    # With a goods line it books, and the record says it went abroad.
        r2 = post("/api/custom/book", custom_body(
            id="csintl00001", address=de,
            customs={"lines": [{"description": "Glass gobo", "quantity": 1, "unit_price": 85,
                                "hs": "70200080", "country": "GB"}]}))
        eq(r2.status_code, 200, r2.text)
        eq(desk._load_dispatch()[r2.json()["id"]]["international"], True, "recorded as international")
    finally:
        if saved_cfg is None:
            os.remove(cfgp)
        else:
            open(cfgp, "w").write(saved_cfg)

@test
def t_a_custom_shipment_is_invisible_to_the_order_queue():
    # It has no order, so it must not appear as a row, and must never attach its
    # tracking to somebody else's order.
    reset_dispatch(); reset_prod()
    post("/api/custom/book", custom_body(id="csqueuetest1"))
    async def tools(registry, name, args):
        if name == "shopify_list_orders":
            return {"orders": [{"id": 12345, "name": "#1", "tags": "IP",
                                "created_at": "2026-08-12T09:00:00Z",
                                "line_items": [], "customer": {}, "shipping_address": {}}]}
        return {}
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        res = run(production.run_production_labels({}, tag="IP"))
        eq(list(res["dispatch"].keys()), [], "the queue carries no ad-hoc dispatch state")
        eq([o["id"] for o in res["orders"]], [12345], "and the real order is untouched")
    finally:
        shopify._tool_json = saved


@test
def t_a_shipment_kept_to_admins_reaches_no_member_by_any_route():
    """Some shipments are nobody else's business. An admin marks one admin
    only, and from then on a member must not be able to reach it by ANY of the
    three doors it was visible through: the Custom shipments queue, the day's
    manifest (a printable sheet any signed-in person can ask for, carrying the
    customer, the reference and the tracking number), and a label reprint,
    whose id is a guessable string rather than something only the queue knows.
    Hiding it from the list alone would have left the other two open."""
    reset_dispatch(); reset_prod()
    r = post("/api/custom/book", custom_body(id="cshidden0001", reference="Private job"))
    eq(r.status_code, 200, r.text)
    sid = r.json()["id"]
    r2 = post("/api/custom/book", custom_body(id="csopen000001", reference="Normal job"))
    eq(r2.status_code, 200, r2.text)
    eq(post("/api/custom/visibility", {"id": sid, "admin_only": True}).status_code, 200,
       "the master marks it")

    _uid, msess, _pw = ready_user("Mel Member", "mel_ship", role="member")
    seen = post_s(msess, "/api/custom/list", {}).json()
    eq([s["reference"] for s in seen["shipments"]], ["Normal job"],
       "a member's queue carries only the shipment that was left open")
    eq(seen.get("can_hide"), False, "and the member is not offered the control")

    from datetime import datetime as dt
    from zoneinfo import ZoneInfo
    today = dt.now(ZoneInfo("Europe/London")).date().isoformat()
    rows = post_s(msess, "/api/dispatch/manifest", {"date": today}).json()["rows"]
    eq([x["order_name"] for x in rows if x["order_id"].startswith("adhoc:")], ["Normal job"],
       "nor does the hidden one reach the handover sheet")
    eq(post_s(msess, "/api/dispatch/label", {"id": sid}).status_code, 404,
       "and its label answers as if there were no such shipment")
    # Both values would have to be guessed to get here, which the three
    # filters above make implausible rather than impossible. A cancel voids a
    # paid label, so it does not rest on that.
    tn = post("/api/custom/list", {}).json()["shipments"]
    tn = next(s for s in tn if s["id"] == sid)["tracking"]
    eq(post_s(msess, "/api/dispatch/cancel", {"id": sid, "tracking_number": tn}).status_code, 400,
       "and a member who knew both its key and its tracking number still cannot void its label")

    # The admin still has all three.
    mine = post("/api/custom/list", {}).json()
    eq(sorted(s["reference"] for s in mine["shipments"]), ["Normal job", "Private job"],
       "the admin sees both")
    ok(next(s for s in mine["shipments"] if s["id"] == sid)["admin_only"],
       "and is told which one is hidden, so the row can say so")
    eq(mine.get("can_hide"), True, "the admin is offered the control")
    eq(post("/api/dispatch/label", {"id": sid}).status_code, 200, "the admin can still reprint it")


@test
def t_only_an_admin_can_hide_a_shipment_or_bring_one_back():
    """Both directions are admin rank. A member who could clear the mark would
    read everything it was set for, and a member who could set one could hide a
    shipment from the people who have to pack and send it. The mark also means
    nothing on an order: an order's dispatch record is read by the queues, the
    margin report and Shopify, so hiding one would hide the order itself."""
    reset_dispatch(); reset_prod()
    sid = post("/api/custom/book", custom_body(id="csrank000001")).json()["id"]
    _uid, msess, _pw = ready_user("Mo Member", "mo_ship", role="member")
    eq(post_s(msess, "/api/custom/visibility", {"id": sid, "admin_only": True}).status_code, 403,
       "a member cannot hide one")
    eq(post("/api/custom/list", {}).json()["shipments"][0]["admin_only"], False,
       "and nothing was written")
    eq(post("/api/custom/visibility", {"id": sid, "admin_only": True}).status_code, 200, "the master can")
    eq(post_s(msess, "/api/custom/visibility", {"id": sid, "admin_only": False}).status_code, 403,
       "and a member cannot undo it either")
    ok(post("/api/custom/list", {}).json()["shipments"][0]["admin_only"], "it is still hidden")
    # A REAL order, on the dispatch record, so the refusal can only come from
    # the ad-hoc check. Asking about an order that was never dispatched would
    # be refused for not existing and would prove nothing.
    eq(post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX}).status_code, 200,
       "an order is dispatched")
    ok("12345" in desk._load_dispatch(), "and is on the record")
    eq(post("/api/custom/visibility", {"id": "12345", "admin_only": True}).status_code, 400,
       "an order is refused: hiding one would hide it from the queues, the margin "
       "report and Shopify, which all have to see it")
    ok(not desk._is_private(desk._load_dispatch()["12345"]), "and nothing was written to it")
    eq(post("/api/custom/visibility", {"id": "adhoc:nosuchthing", "admin_only": True}).status_code, 400,
       "so is a shipment that was never booked")


@test
def t_a_member_cannot_book_a_shipment_the_desk_will_never_see():
    """The booking window offers the tick to an admin only, but the field rides
    in the request body, where anyone can put it. A member's booking is not
    refused for asking - the shipment is real and the money is spent - it
    simply books the way a member's booking always has: visible."""
    reset_dispatch(); reset_prod()
    _uid, msess, _pw = ready_user("Mia Member", "mia_ship", role="member")
    r = post_s(msess, "/api/custom/book", custom_body(id="csmember0001", admin_only=True))
    eq(r.status_code, 200, r.text)
    rows = post("/api/custom/list", {}).json()["shipments"]
    eq(rows[0]["admin_only"], False, "the member's shipment is on the desk's queue like any other")
    r2 = post("/api/custom/book", custom_body(id="csadmin00001", admin_only=True))
    eq(r2.status_code, 200, r2.text)
    hidden = [s for s in post("/api/custom/list", {}).json()["shipments"] if s["admin_only"]]
    eq([s["id"] for s in hidden], [r2.json()["id"]],
       "an admin's booking is hidden from the moment it exists, with no second step")


