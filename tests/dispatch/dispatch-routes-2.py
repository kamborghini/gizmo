@test
def t_plugin_code_whitelist():
    r = post("/api/shipping/config", {"op": "set", "plugin_code": "Shopify"})
    eq(r.status_code, 200, "valid plugin accepted")
    eq(r.json()["config"]["plugin_code"], "Shopify", "persisted")
    ok("Web_Service" in r.json()["config"]["plugin_codes"], "list exposed")
    r = post("/api/shipping/config", {"op": "set", "plugin_code": "web service"})
    eq(r.status_code, 400, "typo rejected")
    post("/api/shipping/config", {"op": "set", "plugin_code": "Web_Service"})

@test
def t_intl_customs_total_drives_boxes():
    global ORDER
    saved = ORDER
    ORDER = {**ORDER, "shipping_address": {**ORDER["shipping_address"], "country_code": "DE"},
             "line_items": [{"title": "Custom Gobo", "quantity": 2, "price": "62.50"}]}
    reset_dispatch()
    post("/api/shipping/config", {"op": "set", "eori": "GB123456789000"})
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(BOOK_XML)
    saved_soap = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        r = post("/api/dispatch/book", {"order_id": 12345,
            "option": {"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
            "boxes": [{"width": 20, "length": 15, "depth": 8, "weight": 0.6},
                      {"width": 20, "length": 15, "depth": 8, "weight": 0.6}],
            "customs": {"lines": [{"description": "Gobo", "quantity": 2, "unit_price": 90, "hs": "70200080"}]}})
        eq(r.status_code, 200, r.text)
        xml = holder["xml"]
        ok("<ad:TotalCustomValue>180</ad:TotalCustomValue>" in xml, "dossier total from lines")
        # two boxes, declared values sum to 180 (90 each)
        import re as _re
        cvals = [float(x) for x in _re.findall(r"<sd:CustomValue>([\d.]+)</sd:CustomValue>", xml)]
        eq(round(sum(cvals), 2), 180.0, "box declared values sum to the customs total, not the order price")
        ok("<ad:Wt>" in xml, "goods line carries a weight, not implicit 0")
    finally:
        worldoptions._soap_call = saved_soap
        ORDER = saved
        post("/api/shipping/config", {"op": "set", "eori": ""})

@test
def t_dispatched_tag_survives_fulfilment():
    """Regression: tagging must happen BEFORE the fulfilment, or _sync_order_tags
    sees a now-fulfilled order, treats it as dead and silently skips the write -
    leaving the order out of the Dispatched queue forever."""
    global ORDER
    saved = ORDER
    reset_dispatch(); reset_prod(); TAG_WRITES.clear(); FULFILLED.clear()
    # A fulfilment writer that flips the order to fulfilled, like Shopify does.
    async def flipping_fulfillment(order_id, tracking_number=None, tracking_company=None,
                                   tracking_url=None, notify_customer=True):
        global ORDER
        FULFILLED.append({"order_id": order_id, "tracking": tracking_number,
                          "company": tracking_company, "notify": notify_customer})
        ORDER = {**ORDER, "fulfillment_status": "fulfilled"}
        return {"ok": True, "fulfillment_id": 555, "status": "success"}
    saved_writer = shopify._fulfillment_writer
    shopify._fulfillment_writer = flipping_fulfillment
    try:
        post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        TAG_WRITES.clear()
        r = mark_made()
        eq(r.status_code, 200, r.text)
        eq(r.json()["fulfilled"], True, "fulfilled")
        ok(TAG_WRITES, "a tag write happened at all")
        ok(any("complete" in t[1].lower() for t in TAG_WRITES),
           "Complete tag actually written: " + str(TAG_WRITES))
    finally:
        shopify._fulfillment_writer = saved_writer
        ORDER = saved

@test
def t_failed_fulfilment_reverts_the_tag():
    reset_dispatch(); reset_prod(); TAG_WRITES.clear()
    async def refusing(order_id, **kw):
        return {"ok": False, "reason": "permission", "detail": "needs write_fulfillments"}
    saved_writer = shopify._fulfillment_writer
    shopify._fulfillment_writer = refusing
    try:
        post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        TAG_WRITES.clear()
        r = mark_made()
        eq(r.status_code, 200, r.text)
        eq(r.json()["fulfilled"], False, "not fulfilled")
        last = TAG_WRITES[-1][1].lower()
        ok("complete" not in last.lower(), "the finished tag is reverted after the failure: " + last)
        ok("pc" in [t.strip() for t in last.split(",")], "left as made")
    finally:
        shopify._fulfillment_writer = saved_writer

@test
def t_live_data_shapes_are_cleaned():
    """World Options puts display HTML and product codes inside data fields."""
    eq(worldoptions._wo_lines("Wed, 12 Aug 2026<br/>End of business day"),
       ["Wed, 12 Aug 2026", "End of business day"], "html split")
    eq(worldoptions._wo_lines("A&amp;B<br>C"), ["A&B", "C"], "entities + bare br")
    eq(worldoptions._tidy_time("15:00 PM"), "15:00", "bogus meridiem dropped")
    eq(worldoptions._tidy_time("9:30 AM"), "9:30 AM", "genuine am/pm kept")
    import datetime as _dt
    yr = _dt.datetime.now(_dt.timezone.utc).year
    eq(worldoptions._tidy_date("Wed, 12 Aug %d" % yr), "Wed 12 Aug", "this year's year dropped")
    eq(worldoptions._tidy_date("Wed, 12 Aug %d" % (yr + 1)), "Wed 12 Aug %d" % (yr + 1), "other year kept")
    # carrier hidden inside the service name is found; the chip word is not repeated
    eq(worldoptions.carrier_from_text("03 DHL Domestic Express"), "DHL", "carrier from name")
    eq(worldoptions._split_service_name("03 DHL Domestic Express", "DHL"), ("03", "Domestic Express"), "code + name split")
    eq(worldoptions._split_service_name("65 Express Saver", ""), ("65", "Express Saver"), "unknown carrier keeps name")
    eq(worldoptions.carrier_from_text("Groups pickups"), "", "no false UPS match inside words")
    eq(worldoptions.carrier_display("EVRISEND"), "Evri", "display name")

@test
def t_quote_options_expose_clean_fields():
    worldoptions.set_credentials(meter="M1")
    res = run(worldoptions.quote({"postcode": "LS1 1AA", "country": "GB"},
                                 {"postcode": "M1 2AB", "country": "GB"},
                                 [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}]))
    rm = [o for o in res["options"] if "Tracked" in o["service_name"]][0]
    eq(rm["carrier_name"], "ROYALMAIL", "carrier resolved from the name")
    eq(rm["carrier_label"], "Royal Mail", "friendly label")
    eq(rm["service_name"], "Tracked 24", "code and carrier word stripped")
    eq(rm["product_code"], "03", "product code kept separately")
    eq(rm["delivery_date"], "Wed 12 Aug", "delivery date cleaned")
    eq(rm["delivery_time"], "End of business day", "delivery time split out")
    eq(rm["pickup_time"], "15:00", "pickup time de-meridiemed")
    ok("<br" not in json.dumps(res), "no HTML anywhere in the payload")

@test
def t_quote_declares_package_and_shipment_type():
    """WCF gives an omitted enum its FIRST member: without these, every quote went
    out as a Fedex_Box on an Export shipment, hiding domestic services."""
    worldoptions.set_credentials(meter="M1")
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        run(worldoptions.quote({"postcode": "LS1 1AA", "country": "GB"},
                               {"postcode": "M1 2AB", "country": "GB"},
                               [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}],
                               shipment_mode="Domestic"))
        xml = holder["xml"]
        ok("<rs:PackageType>Any_NonDocument</rs:PackageType>" in xml, "generic parcel type sent")
        ok("<rs:ShipmentType>Domestic</rs:ShipmentType>" in xml, "domestic mode sent")
        # XSD sequence order inside wsShippingDetails
        ok(xml.index("<rs:PackageDetails>") < xml.index("<rs:PackageType>")
           < xml.index("<rs:ServiceName>") < xml.index("<rs:ServiceTypeName>")
           < xml.index("<rs:ShipmentType>"), "fields in XSD sequence order")
    finally:
        worldoptions._soap_call = saved

@test
def t_shipment_mode_follows_the_countries():
    global ORDER
    saved = ORDER
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder.setdefault("xmls", []).append(inner); return ET.fromstring(RATE_XML)
    saved_soap = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        ok("<rs:ShipmentType>Domestic</rs:ShipmentType>" in holder["xmls"][-1], "GB->GB is Domestic")
        ORDER = {**ORDER, "shipping_address": {**ORDER["shipping_address"], "country_code": "DE"}}
        post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        ok("<rs:ShipmentType>Export</rs:ShipmentType>" in holder["xmls"][-1], "GB->DE is Export")
    finally:
        worldoptions._soap_call = saved_soap
        ORDER = saved

@test
def t_options_carry_vat_split():
    worldoptions.set_credentials(meter="M1")
    res = run(worldoptions.quote({"postcode": "LS1 1AA", "country": "GB"},
                                 {"postcode": "M1 2AB", "country": "GB"},
                                 [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}]))
    op = res["options"][0]
    ok(op["vat"] is not None, "VAT captured")
    eq(round(op["amount_ex_vat"] + op["vat"], 2), op["amount"], "ex VAT + VAT == total")
    # every option's split must reconcile, including any without a VAT line
    for o in res["options"]:
        if o["amount"] is None:
            continue
        eq(round(o["amount_ex_vat"] + (o["vat"] or 0), 2), o["amount"], "split reconciles: " + o["service_name"])

@test
def t_unprint_undoes_a_print():
    # An order in production and not made: the case Undo exists for. (The
    # shared fixture carries PC, a made order, which Undo now leaves alone.)
    reset_prod(); TAG_WRITES.clear()
    saved_tags = ORDER["tags"]; ORDER["tags"] = "IP"
    try:
        _t_unprint_undoes_a_print()
    finally:
        ORDER["tags"] = saved_tags

def _t_unprint_undoes_a_print():
    r = post("/api/production-state", {"op": "printed", "ids": [12345]})
    eq(r.status_code, 200, r.text)
    st = json.load(open(SCRATCH + "/production_state.json"))["orders"]
    ok(st.get("12345", {}).get("printed_at"), "printed stamped")
    r = post("/api/production-state", {"op": "unprinted", "ids": [12345]})
    eq(r.status_code, 200, r.text)
    st = json.load(open(SCRATCH + "/production_state.json"))["orders"]
    ok(not (st.get("12345") or {}).get("printed_at"), "stamp cleared")
    last = TAG_WRITES[-1][1].lower()
    ok("unprocessed" in last, "back to Unprocessed: " + last)
    r = post("/api/production-state", {"op": "unprinted", "ids": []})
    eq(r.status_code, 400, "no ids rejected")

@test
def t_failed_dispatched_tag_is_reported():
    reset_dispatch(); reset_prod()
    async def refusing_tags(order_id, tags):
        raise RuntimeError("shopify said no")
    saved = shopify._order_tag_writer
    try:
        post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        shopify._order_tag_writer = refusing_tags
        r = mark_made()
        eq(r.status_code, 200, r.text)
        b = r.json()
        eq(b["fulfilled"], True, "still fulfilled")
        ok("Dispatched tag did not save" in (b.get("ship_note") or ""),
           "operator is told the tag failed: " + str(b.get("ship_note")))
        ok(b.get("tag_note"), "tag_note surfaced rather than discarded")
    finally:
        shopify._order_tag_writer = saved

@test
def t_shop_delivery_is_never_offered():
    """Business rule (Cameron, 2026-10-09): "our customers should never collect
    from shop". No pickup-point quote is asked for, no Access Point or ParcelShop
    service is offered, and the old setting that switched them on is ignored,
    even when it is still saved as on."""
    reset_dispatch(); reset_prod(); _ship_cfg()
    cfg = desk._load_shipping(); cfg["show_parcelshop"] = True; desk._save_shipping(cfg)
    r = post("/api/shipping/config", {"op": "set", "show_parcelshop": True})
    eq(r.status_code, 200, r.text)
    holder = {"xmls": []}
    async def cap(service, action, inner, retryable=True):
        holder["xmls"].append(inner)
        return ET.fromstring(AP_XML if "IsDeliveryDropoffRequired" in inner else RATE_XML.replace(
            "</wsRateService>", AP_XML.split("<wsRateService>", 1)[1].split("</wsRateService>", 1)[0] + "</wsRateService>"))
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        eq(r.status_code, 200, r.text)
        body = r.json()
        codes = [o["service_type_code"] for o in body["options"]]
        ok(not any("IsDeliveryDropoffRequired" in x for x in holder["xmls"]), "no pickup-point quote is asked for")
        ok("UPS_Express_Saver_AP" not in codes, "an Access Point service that arrives anyway is not offered: " + str(codes))
        ok("UPS_Express_Saver" in codes, "while its door service is")
        ok(not any(o.get("delivery_dropoff") for o in body["options"]), "nothing is collect-from-shop")
        eq(body["show_parcelshop"], False, "and the window is told shop services are off")
        c = post("/api/custom/quote", {"address": dict(CUST_ADDR), "box": dict(BOX)})
        eq(c.status_code, 200, c.text)
        ok("UPS_Express_Saver_AP" not in [o["service_type_code"] for o in c.json()["options"]], "a custom shipment's quote neither")
    finally:
        worldoptions._soap_call = saved
    got = post("/api/shipping/config", {"op": "get"}).json()["config"]
    ok(not got.get("show_parcelshop"), "the setting cannot be switched on")


@test
def t_a_shop_delivery_is_never_booked():
    """The rule's backstop: an option that would deliver to a pickup shop is
    refused before anything reaches World Options, from the Dispatch window and
    from a custom shipment alike."""
    reset_dispatch(); reset_prod(); _ship_cfg()
    sent = []
    async def cap(service, action, inner, retryable=True):
        sent.append(service)
        return ET.fromstring(BOOK_XML if service == "ShipmentService" else RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    shop = [{"id": "UPS991", "name": "Corner Shop", "street": "7 Market St", "city": "Manchester", "postcode": "M1 3AA"}]
    try:
        for opt in ({"service_type_code": "UPS_Express_Saver_AP", "package_type_code": "UPS_My_Packaging",
                     "carrier_name": "UPS", "service_name": "Express Saver Access Point", "amount": 7.44,
                     "delivery_dropoff": True, "delivery_shops": shop},
                    {"service_type_code": "UPS_Express_Saver_AP", "package_type_code": "UPS_My_Packaging",
                     "carrier_name": "UPS", "amount": 7.44, "delivery_dropoff": False, "delivery_shops": []},
                    {"service_type_code": "EVRI_PARCELSHOP", "service_full": "Evri ParcelShop Next Day",
                     "carrier_name": "EVRISEND", "amount": 3.10}):
            r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": BOX})
            eq(r.status_code, 400, "refused: " + r.text)
            ok("pickup shop" in r.json().get("error", ""), "and says why: " + r.text)
            c = post("/api/custom/book", custom_body(id="csnoshop" + str(len(sent)), option=opt))
            eq(c.status_code, 400, "a custom shipment is refused too: " + c.text)
        eq([x for x in sent if x == "ShipmentService"], [], "nothing was booked at World Options")
    finally:
        worldoptions._soap_call = saved


@test
def t_one_failed_quote_does_not_lose_the_other():
    reset_dispatch(); reset_prod()
    async def half(service, action, inner, retryable=True):
        if service == "RateService" and "IsDeliveryDropoffRequired" in inner:
            raise worldoptions.WorldOptionsError("pickup points unavailable")
        return ET.fromstring(RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = half
    try:
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        eq(r.status_code, 200, "door quote still returned")
        ok(len(r.json()["options"]) >= 1, "options present")
    finally:
        worldoptions._soap_call = saved

@test
def t_parcelshop_services_are_hidden_by_default():
    reset_dispatch(); reset_prod()
    SOAP_MODE["calls"].clear()          # only judge the calls this test makes
    r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
    eq(r.status_code, 200, r.text)
    body = r.json()
    eq(body["show_parcelshop"], False, "hidden by default")
    codes = [o["service_type_code"] for o in body["options"]]
    ok(not any(x.endswith("_AP") for x in codes), "no Access Point services: " + str(codes))
    ok(not any("ParcelShop" in (o.get("service_full") or "") for o in body["options"]),
       "no ParcelShop services by name")
    # the second (pickup-point) quote is not even requested when hidden
    rate_calls = [i for (s, i) in SOAP_MODE["calls"] if s == "RateService"]
    ok(not any("IsDeliveryDropoffRequired" in i for i in rate_calls),
       "no pickup-point request is made when the setting is off")

@test
def t_diagnose_reports_what_each_setting_returns():
    r = post("/api/dispatch/diagnose", {"order_id": 12345, "box": BOX})
    eq(r.status_code, 200, r.text)
    d = r.json()
    labels = [row["label"] for row in d["rows"]]
    ok("As the app quotes now" in labels, "baseline row present")
    ok(any("signature" in l.lower() for l in labels), "signature variants tried")
    ok(any("UPS only" in l for l in labels), "per-carrier variant tried")
    # Customers never collect from a shop, so no pickup-shop variant is tried and
    # no shop service is ever suggested as missing.
    ok(not any("pickup shop" in l.lower() for l in labels), "no pickup-shop variant: " + str(labels))
    codes = [x["code"] for x in d["extra_found"]] + [s["code"] for row in d["rows"] for s in row["services"]]
    ok(not any(c.upper().endswith("_AP") for c in codes), "no Access Point service is reported: " + str(codes))
    ok(all(x["name"].strip() for x in d["extra_found"]), "every reported service is named, not a bare code")
    base = d["rows"][0]["services"]
    ok(base and all(not s.get("new") for s in base), "baseline rows are never marked new")

@test
def t_diagnose_sends_the_signature_flag():
    holder = {"xmls": []}
    async def cap(service, action, inner, retryable=True):
        if service == "RateService":
            holder["xmls"].append(inner)
            return ET.fromstring(AP_XML if "IsDeliveryDropoffRequired" in inner else RATE_XML)
        return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        post("/api/dispatch/diagnose", {"order_id": 12345, "box": BOX})
        joined = " ".join(holder["xmls"])
        ok("<rs:SignatureType>Fedex_No_Signature_Required</rs:SignatureType>" in joined, "signature variant sent")
        ok("<rs:ServiceName>UPS</rs:ServiceName>" in joined, "UPS-only variant sent")
        ok("<rs:PackageType>UPS_My_Packaging</rs:PackageType>" in joined, "packaging variant sent")
        # SignatureType must come last in the XSD sequence
        one = [x for x in holder["xmls"] if "SignatureType" in x][0]
        ok(one.index("<rs:ShipmentType>") < one.index("<rs:SignatureType>"), "XSD order kept")
    finally:
        worldoptions._soap_call = saved

@test
def t_cheaper_no_signature_option_is_offered():
    reset_dispatch(); reset_prod()
    r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
    eq(r.status_code, 200, r.text)
    opts = r.json()["options"]
    ns = [o for o in opts if o.get("no_signature")]
    eq(len(ns), 1, "one cheaper no-signature row: " + str([(o["service_name"], o["amount"]) for o in opts]))
    eq(ns[0]["amount"], 9.10, "the cheaper price")
    eq(ns[0]["saves_vs_signed"], 0.84, "saving shown")
    eq(ns[0]["carrier_name"], "DHL", "only a carrier with a no-signature service is offered")
    eq(ns[0]["signature_type"], "DHL_No_Signature_Required",
       "carries THAT CARRIER's own literal, not the one the sweep was quoted with")
    # the signed version is still there, and cheapest-first still holds
    ok(any(o["service_type_code"] == ns[0]["service_type_code"] and not o.get("no_signature") for o in opts),
       "the normal priced version is kept too")
    amounts = [o["amount"] for o in opts if o["amount"] is not None]
    eq(amounts, sorted(amounts), "still cheapest first")

@test
def t_no_signature_is_not_offered_when_it_is_not_cheaper():
    global NOSIG_XML
    saved = NOSIG_XML
    try:
        globals()["NOSIG_XML"] = RATE_XML       # identical prices
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        opts = r.json()["options"]
        eq([o for o in opts if o.get("no_signature")], [], "no pointless duplicate rows")
    finally:
        globals()["NOSIG_XML"] = saved

@test
def t_booking_reproduces_the_quoted_signature():
    reset_dispatch(); reset_prod()
    holder = {}
    async def cap(service, action, inner, retryable=True):
        if service == "ShipmentService":
            holder["xml"] = inner; return ET.fromstring(BOOK_XML)
        return ET.fromstring(RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        opt = {"service_type_code": "DHL_DOMESTIC_EXPRESS", "package_type_code": "DHL_NonDocument",
               "carrier_name": "DHL", "service_name": "Domestic Express", "amount": 9.10,
               "no_signature": True, "signature_type": "DHL_No_Signature_Required"}
        r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": BOX})
        eq(r.status_code, 200, r.text)
        ok("<wo:DeliverySignatureType>DHL_No_Signature_Required</wo:DeliverySignatureType>" in holder["xml"],
           "the quoted signature setting is sent back so the charge matches")
    finally:
        worldoptions._soap_call = saved

@test
def t_carrier_is_resolved_from_every_signal_world_options_gives():
    # Their own carrier field wins outright.
    eq(worldoptions._carrier_from("UPS_Standard", "DHL"), "DHL", "explicit ServiceType wins")
    # Then the service code prefix.
    eq(worldoptions._carrier_from("UPS_Express_Saver", ""), "UPS", "service code prefix")
    # Then the package type, which names the carrier on every real option.
    eq(worldoptions._carrier_from("", "", "UPS_My_Packaging", "11 Standard"), "UPS", "package type")
    eq(worldoptions._carrier_from("", "", "DHL_NonDocument", "03 Domestic Express"), "DHL", "package type")
    eq(worldoptions._carrier_from("", "", "Fedex_Your_Packaging", "13 First"), "FEDEX", "package type")
    eq(worldoptions._carrier_from("", "", "RoyalMail_Parcel", "Tracked 24"), "ROYALMAIL", "package type")
    # Last, a carrier word inside the service text.
    eq(worldoptions._carrier_from("", "", "", "03 DHL Domestic Express"), "DHL", "carrier named in the text")

@test
def t_underscored_codes_no_longer_defeat_the_text_search():
    # \b does not match between a letter and an underscore, so every one of these
    # used to come back empty and the option showed no carrier at all.
    for text, want in [("UPS_Standard", "UPS"), ("DHL_DOMESTIC_EXPRESS_1200", "DHL"),
                       ("Evri_Next_Day", "EVRISEND"), ("DX_Express", "DXEXPRESS"),
                       ("TNT_Express", "TNT"), ("DPD_Next_Day", "DPD"),
                       ("DSV_LTL", "DSV"), ("UKMAIL_NonDocument", "UKMAIL")]:
        eq(worldoptions.carrier_from_text(text), want, "carrier found in " + text)

@test
def t_every_resolvable_carrier_has_a_readable_name():
    seen = set()
    for code in (worldoptions._CARRIERS + worldoptions.SERVICE_COMPANY_ENUM
                 + list(worldoptions._PREFIX_TO_ENUM.values())):
        cr = worldoptions._prefix_carrier(code) or worldoptions.canonical_carrier(code) or code
        if cr in ("ALL", "") or cr in seen:
            continue
        seen.add(cr)
        shown = worldoptions.carrier_display(cr)
        ok(shown and shown != cr.upper() or cr in ("UPS", "DHL", "TNT", "DPD", "DSV"),
           "carrier " + cr + " reads as " + repr(shown) + ", not a raw enum")

@test
def t_quote_names_the_carrier_for_every_live_option():
    reset_dispatch(); reset_prod()
    r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
    eq(r.status_code, 200, r.text)
    for o in r.json()["options"]:
        ok(o["carrier_label"], "option " + repr(o["service_name"]) + " names its carrier")

@test
def t_the_page_can_name_every_carrier_the_server_can_resolve():
    # The page keeps its own map for booked orders. A carrier the server resolves
    # but the page cannot name would show the merchant a raw enum like EVRICORPORATE.
    html = pagesource.join(HERE)
    block = re.search(r"const CARRIER_LABELS = \{(.*?)\};", html, re.S)
    ok(block, "found CARRIER_LABELS on the page")
    page = dict(re.findall(r"(\w+): '([^']+)'", block.group(1)))
    for code, name in worldoptions.CARRIER_DISPLAY.items():
        eq(page.get(code), name, "page names " + code + " the same way the server does")


# A quote reply shaped the way this account has NEVER been proven to answer: no
# wsQuoteDetails/ServiceType, no carrier prefix on the code, names like "11 Standard".
# The fixtures elsewhere assume the friendly shape; this one asserts what happens
# when that assumption is wrong, which is the case nobody would notice until it hit.
BLIND_XML = """<Envelope><Body><GetAllServicesAndRatesResponse>
<GetAllServicesAndRatesResult><Message/><NotificationtType>SUCCESS</NotificationtType><wsRateService>
 <wsAvailableServicesAndRates>
   <wsPackageTypeCode>Any_NonDocument</wsPackageTypeCode><wsServiceCode>11</wsServiceCode>
   <wsServiceTypeCode>11</wsServiceTypeCode><wsServiceTypeName>11 Standard</wsServiceTypeName>
   <wsDeliveryDateTime>Thu, 13 Aug 2026&lt;br/&gt;End of business day</wsDeliveryDateTime>
   <wsQuoteDetails><TotalNetCharge>7.31</TotalNetCharge><VATCharge>1.22</VATCharge></wsQuoteDetails>
 </wsAvailableServicesAndRates>
 <wsAvailableServicesAndRates>
   <wsPackageTypeCode>Any_NonDocument</wsPackageTypeCode><wsServiceCode>03</wsServiceCode>
   <wsServiceTypeCode>03</wsServiceTypeCode><wsServiceTypeName>03 DHL Domestic Express</wsServiceTypeName>
   <wsDeliveryDateTime>Thu, 13 Aug 2026&lt;br/&gt;End of business day</wsDeliveryDateTime>
   <wsQuoteDetails><TotalNetCharge>9.94</TotalNetCharge><VATCharge>1.66</VATCharge></wsQuoteDetails>
 </wsAvailableServicesAndRates>
</wsRateService></GetAllServicesAndRatesResult></GetAllServicesAndRatesResponse></Body></Envelope>"""

@test
def t_an_account_that_names_no_carrier_degrades_honestly():
    async def blind(service, action, inner, retryable=True):
        return ET.fromstring(BLIND_XML if service == "RateService" else BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = blind
    try:
        reset_dispatch(); reset_prod()
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        eq(r.status_code, 200, r.text)
        opts = {o["service_name"]: o for o in r.json()["options"]}
        # The name spells DHL out, so that one is still known.
        eq(opts["Domestic Express"]["carrier_label"], "DHL", "carrier read from the name")
        # Nothing anywhere names the carrier of "11 Standard". It must come back
        # EMPTY rather than guessed, so the page can say so instead of inventing one.
        eq(opts["Standard"]["carrier_label"], "", "no carrier is admitted, not invented")
        eq(opts["Standard"]["product_code"], "11", "their code survives for the operator")
    finally:
        worldoptions._soap_call = saved

@test
def t_a_service_code_outside_the_enum_is_refused_before_the_charge():
    # Booking's ServiceTypeCode is typed to wsServiceTypes. A code outside it cannot
    # be booked, and finding that out from WCF costs a round trip against real money.
    reset_dispatch(); reset_prod()
    called = {"n": 0}
    async def counting(service, action, inner, retryable=True):
        called["n"] += 1
        return ET.fromstring(BOOK_XML if service == "ShipmentService" else RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = counting
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "box": BOX,
                                        "option": {"service_type_code": "11", "amount": 7.31,
                                                   "carrier_name": "UPS", "service_name": "Standard"}})
        eq(r.status_code, 400, r.text)
        ok(r.json().get("error"), "refused: " + json.dumps(r.json())[:200])
        ok("does not recognise" in r.json()["error"], "says why")
        eq(called["n"], 0, "nothing was sent to World Options")
    finally:
        worldoptions._soap_call = saved

@test
def t_every_bookable_service_maps_to_a_carrier_with_a_readable_name():
    # 145 of the 146 wsServiceTypes members carry their carrier as a prefix; ALL is
    # the exception and means "any carrier", never an answer to who is carrying it.
    eq(len(worldoptions.SERVICE_TYPES_ENUM), 146, "the whole enum is present")
    for code in worldoptions.SERVICE_TYPES_ENUM:
        if code == "ALL":
            continue
        cr = worldoptions.SERVICE_CARRIER[worldoptions._squash(code)]
        ok(cr, code + " resolves to a carrier")
        shown = worldoptions.carrier_display(cr)
        ok(shown and shown != cr.upper() or cr in ("UPS", "DHL", "TNT", "DPD", "DSV"),
           code + " reads as " + repr(shown) + ", not the raw enum " + cr)
    eq(worldoptions.canonical_carrier("ALL"), "", "ALL is never a carrier answer")

@test
def t_a_broken_dispatch_store_stops_the_booking_rather_than_double_charging():
    reset_dispatch(); reset_prod()
    with open(os.environ["DISPATCH_STATE_PATH"], "w", encoding="utf-8") as fh:
        fh.write("{not json at all")
    jsonstore._poisoned_stores.discard(os.environ["DISPATCH_STATE_PATH"])
    called = {"n": 0}
    async def counting(service, action, inner, retryable=True):
        called["n"] += 1
        return ET.fromstring(BOOK_XML if service == "ShipmentService" else RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = counting
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "box": BOX, "option": OPT})
        eq(r.status_code, 400, r.text)
        ok(r.json().get("error"), "refused rather than risk a second charge")
        eq(called["n"], 0, "nothing was booked")
    finally:
        worldoptions._soap_call = saved
        jsonstore._poisoned_stores.discard(os.environ["DISPATCH_STATE_PATH"])
        reset_dispatch()

@test
def t_a_carrier_that_cannot_be_booked_by_name_is_still_named():
    # UKMail runs 13 services but is not a wsServiceCompanyTypes member, so the
    # request may never name it. That must not mean the merchant and the customer
    # are told nothing about who has the parcel.
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner
        return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        addr = {"name": "A", "street": "1 St", "city": "M", "postcode": "M1 1AA",
                "country": "GB", "phone": "1", "email": "a@b.c"}
        r = run(worldoptions.book({"service_type_code": "UKMail_Express_UK"}, addr, addr,
                                  [{"width": 10, "length": 10, "depth": 10, "weight": 1}]))
        ok("<sd:ServiceType>" not in holder["xml"], "an unbookable carrier is not sent")
        eq(r["carrier_name"], "", "nothing invalid is claimed as the booking carrier")
        eq(r["carrier_known"], "UKMAIL", "but we still know who has it")
        eq(r["carrier_label"], "UKMail", "and the merchant reads a real name")
        eq(worldoptions.shopify_carrier(r["carrier_known"]), "UK Mail",
           "and the customer's email names a real company")
    finally:
        worldoptions._soap_call = saved

@test
def t_a_company_name_is_never_invented_for_a_customer_email():
    eq(worldoptions.shopify_carrier(""), "", "no carrier, no company")
    eq(worldoptions.shopify_carrier("SOMETHING_NEW"), "", "an unknown code is not a company")
    eq(worldoptions.shopify_carrier("GLOBALTRANZ"), "GlobalTranz", "a known one is spelled properly")

# The saved WSDL is the contract's ground truth: two tests walk it directly so a
# schema change surfaces as a failing test, not a failed booking.
XSD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "wsdl") + os.sep

def _xsd_sequence(tname):
    import glob
    for f in glob.glob(XSD_DIR + "wo_xsd*.xml"):
        s = open(f, encoding="utf-8").read()
        m = re.search(r'<xs:complexType name="%s">(.*?)</xs:complexType>' % re.escape(tname), s, re.S)
        if m:
            return [re.search(r'name="([^"]+)"', e).group(1)
                    for e in re.findall(r"<xs:element[^>]*/>", m.group(1))]
    return []

@test
def t_booking_envelope_matches_the_schema_sequence():
    # WCF's DataContractSerializer requires the declared order. This walks the real
    # XSDs rather than a copy of them, so a hand-edited envelope cannot drift.
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner
        return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        addr = {"name": "A", "company": "C", "street": "1 St", "city": "M",
                "postcode": "M1 1AA", "country": "GB", "phone": "1", "email": "a@b.c"}
        run(worldoptions.book({"service_type_code": "UPS_Standard",
                               "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              addr, addr, [{"width": 20, "length": 15, "depth": 8, "weight": 0.5}]))
        x = holder["xml"]
        for block, prefix, tname in [("RecipientsDetails", "m", "wsRecipient"),
                                     ("SendersDetails", "m", "wsSender"),
                                     ("ShippingDetail", "sd", "wsShippingDetail")]:
            order = _xsd_sequence(tname)
            ok(order, "found " + tname + " in the XSDs")
            body = re.search(r"<wo:%s>(.*?)</wo:%s>" % (block, block), x, re.S)
            ok(body, "envelope carries " + block)
            # Flatten out nested types (each parcel, each drop-off shop): their
            # children belong to their own complexType, not this sequence.
            flat = re.sub(r"<sd:wsShippingDetail\.\w+>.*?</sd:wsShippingDetail\.\w+>", "",
                          body.group(1), flags=re.S)
            flat = re.sub(r"<sd:(CollectionDropOffInfo|DeliveryDropOffInfo)>.*?</sd:\1>", "",
                          flat, flags=re.S)
            got = re.findall(r"<%s:(\w+)>" % prefix, flat)
            unknown = [g for g in got if g not in order]
            eq(unknown, [], block + " sends only elements the schema declares")
            idx = [order.index(g) for g in got if g in order]
            eq(idx, sorted(idx), block + " is in schema sequence order")
    finally:
        worldoptions._soap_call = saved

@test
def t_nothing_the_service_reads_as_text_arrives_null():
    # "Value cannot be null. Parameter name: input" is what .NET throws when a null
    # string reaches a parse or regex helper. A UK consumer address has no county
    # and no company, so those fields were absent and therefore null.
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner
        return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        bare = {"name": "Jo", "street": "10 Nethercote Ave", "city": "Manchester",
                "postcode": "M23 1LL", "country": "GB", "phone": "07000", "email": "jo@x.co"}
        run(worldoptions.book({"service_type_code": "UPS_Standard",
                               "package_type_code": "Any_NonDocument", "carrier_name": "UPS"},
                              bare, bare, [{"width": 20, "length": 15, "depth": 8, "weight": 0.5}]))
        x = holder["xml"]
        for el in ("Company", "State_Code", "State", "CustomerReference", "Description",
                   "LabelDeliveryMethod", "NumberOfPiecesOnAllPallets", "SenderVatNo"):
            ok(re.search(r"<(?:m|sd):%s>" % el, x), el + " is sent, not omitted into a null")
        # A rate-only package type must not fall through to the enum's first member.
        eq(re.findall(r"<sd:PackageTypeCode>([^<]*)<", x), ["UPS_My_Packaging"],
           "the carrier's own packaging, not Fedex_Box by default")
    finally:
        worldoptions._soap_call = saved

@test
def t_a_rejected_booking_logs_its_envelope_without_credentials():
    x = ("<m:Key>secret-key</m:Key><m:Password>hunter2</m:Password>"
         "<m:MeterNumber>1239999</m:MeterNumber><sd:City>Leeds</sd:City>")
    red = worldoptions._redacted(x)
    for bad in ("secret-key", "hunter2", "1239999"):
        ok(bad not in red, bad + " is not in the log")
    # City is redacted too now: with the address lines it completes a customer's
    # location in a file that outlives the failure. The SHAPE survives, which is
    # what the panel is read for.
    ok("<sd:City>" in red, "the element survives so the shape can be read")
    ok("Leeds" not in red, "but the value does not")

def _xsd_nillable_strings(tname):
    import glob
    for f in glob.glob(XSD_DIR + "wo_xsd*.xml"):
        s = open(f, encoding="utf-8").read()
        m = re.search(r'<xs:complexType name="%s">(.*?)</xs:complexType>' % re.escape(tname), s, re.S)
        if m:
            return [re.search(r'name="([^"]+)"', e).group(1)
                    for e in re.findall(r"<xs:element[^>]*/>", m.group(1))
                    if 'nillable="true"' in e and "xs:string" in e]
    return []

@test
def t_no_nillable_string_reaches_the_service_as_null():
    # In WCF an omitted nillable string deserializes to null, and their code runs
    # string work on it: that is what "Value cannot be null. Parameter name: input"
    # was. Driven off the real XSDs so a new field in a future WSDL shows up here
    # rather than as a failed booking. Date and account-number fields are listed as
    # deliberate exceptions: "" would fail a parse that a null is likelier to skip.
    # ReadyDate proved the rule live: "" fails their dd/MM/yyyy format check while
    # an absent optional member passes. Format-shaped fields are real or absent.
    OMIT_ON_PURPOSE = {"ReadyDate", "DutiesAccNumber", "TransportationAccNumber"}
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner
        return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        # The shape that produced the live failure: a UK consumer, no county,
        # no company, no insurance, with a collection window set.
        bare = {"name": "Jo", "street": "10 Nethercote Ave", "city": "Manchester",
                "postcode": "M23 1LL", "country": "GB", "phone": "07000", "email": "jo@x.co"}
        run(worldoptions.book({"service_type_code": "UPS_Standard",
                               "package_type_code": "Any_NonDocument", "carrier_name": "UPS"},
                              bare, bare, [{"width": 20, "length": 15, "depth": 8, "weight": 0.5}],
                              ready_time="14:00", close_time="17:30"))
        x = holder["xml"]
        for block, prefix, tname in [("RecipientsDetails", "m", "wsRecipient"),
                                     ("SendersDetails", "m", "wsSender"),
                                     ("ShippingDetail", "sd", "wsShippingDetail"),
                                     ("BillingDetail", "wo", "wsBillingDetail")]:
            body = re.search(r"<wo:%s>(.*?)</wo:%s>" % (block, block), x, re.S)
            ok(body, block + " is in the envelope")
            for el in _xsd_nillable_strings(tname):
                if el in OMIT_ON_PURPOSE:
                    continue
                ok(re.search(r"<%s:%s>" % (prefix, el), body.group(1)),
                   block + "." + el + " is sent, so it cannot arrive as null")
    finally:
        worldoptions._soap_call = saved

@test
def t_a_new_field_in_the_customs_blocks_shows_up_here():
    """The test above walks the address, shipping and billing blocks against
    the saved schema. The customs blocks, sent on international bookings only,
    were not walked, and by October 2026 World Options had added four optional
    strings to them (the receiver's EORI number, and three product ids on each
    goods line) that no test noticed. Every field in them is now sent or named
    below as not sent, so the next new field of any kind fails here, not on a
    booking. Whether the new four should be sent is a question for World Options."""
    NOT_SENT = {
        "wsAddlShipmentDetail": {"DeliveryType", "TotalCalculatedValue", "ReceiverEORINumber",
                                 "TradeDocuments"},
        "wsAddlShipmentDetail.GoodsDetail": {"ManufacturerProductID", "MerchantProductID",
                                             "StandardisedProductID"},
    }
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner
        return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        customs = {"eori": "GB123456789000", "export_reason": "Sale", "trade_term": "DAP",
                   "invoice_number": "#104239", "receiver_tax_id": "DE-TAX-1",
                   "goods": [{"description": "Glass projection gobo", "quantity": 2,
                              "unit_price": 62.5, "hs": "70200080", "country": "GB", "weight": 0.1}],
                   "total_value": 125.0}
        run(worldoptions.book({"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging",
                               "carrier_name": "UPS"},
                              {"postcode": "LS1 1AA", "country": "GB"},
                              {"postcode": "10115", "country": "DE", "city": "Berlin"},
                              [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}], customs=customs))
        x = holder["xml"]
        blocks = {"wsAddlShipmentDetail": r"<wo:AdditionalShipmentDetail>(.*?)</wo:AdditionalShipmentDetail>",
                  "wsAddlShipmentDetail.GoodsDetail":
                      r"<ad:wsAddlShipmentDetail\.GoodsDetail>(.*?)</ad:wsAddlShipmentDetail\.GoodsDetail>"}
        for tname, pattern in blocks.items():
            body = re.search(pattern, x, re.S)
            ok(body, tname + " is in the envelope")
            fields = _xsd_sequence(tname)
            ok(fields and set(_xsd_nillable_strings(tname)) <= set(fields), tname + " is in the saved schema")
            for el in fields:
                if el not in NOT_SENT[tname]:
                    ok(re.search(r"<ad:%s>" % el, body.group(1)),
                       tname + "." + el + " is neither sent nor named as deliberately not sent")
            eq(NOT_SENT[tname] - set(fields), set(), tname + ": a name listed as not sent is in the schema")
    finally:
        worldoptions._soap_call = saved

@test
def t_the_merchant_pays_for_the_carriage_not_the_customer():
    # TransportationPayorTypes begins with Bill_To_Receiver, so saying nothing bills
    # the CUSTOMER for the shipping. It is stated explicitly on every booking.
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner
        return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        a = {"name": "A", "street": "1 St", "city": "M", "postcode": "M1 1AA",
             "country": "GB", "phone": "1", "email": "a@b.c"}
        for kw in ({}, {"ready_time": "14:00", "close_time": "17:30"}):
            run(worldoptions.book({"service_type_code": "UPS_Standard",
                                   "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                                  a, a, [{"width": 1, "length": 1, "depth": 1, "weight": 1}], **kw))
            ok("<wo:TransportationPayor>Bill_To_Sender</wo:TransportationPayor>" in holder["xml"],
               "the merchant's account pays, collection window set: " + str(bool(kw)))
    finally:
        worldoptions._soap_call = saved

@test
def t_a_booking_without_a_service_or_packaging_is_refused():
    called = {"n": 0}
    async def counting(service, action, inner, retryable=True):
        called["n"] += 1
        return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = counting
    try:
        a = {"name": "A", "street": "1 St", "city": "M", "postcode": "M1 1AA",
             "country": "GB", "phone": "1", "email": "a@b.c"}
        box = [{"width": 1, "length": 1, "depth": 1, "weight": 1}]
        # No service at all: WCF would have taken the enum's first member.
        try:
            run(worldoptions.book({}, a, a, box)); ok(False, "empty service code refused")
        except worldoptions.WorldOptionsError as e:
            ok("No courier service was chosen" in str(e), "says what is wrong: " + str(e)[:60])
        eq(called["n"], 0, "nothing reached World Options")
    finally:
        worldoptions._soap_call = saved

@test
def t_every_bookable_carrier_has_packaging_we_can_name():
    # PackageTypeCode is a non-nillable enum whose first member is Fedex_Box, so an
    # unnamed packaging is not "unset", it is FedEx packaging on someone else's
    # booking. book() refuses rather than let that happen; this proves the refusal
    # is a backstop and not something the merchant can actually hit.
    carriers = {worldoptions.SERVICE_CARRIER[worldoptions._squash(s)]
                for s in worldoptions.SERVICE_TYPES_ENUM if s != "ALL"}
    for cr in sorted(carriers):
        pkg = worldoptions.CARRIER_PACKAGE_TYPE.get(cr.upper())
        ok(pkg, cr + " has packaging mapped")
        ok(pkg in worldoptions.PACKAGE_TYPES_ENUM, cr + " maps to a real wsPackageTypes member: " + str(pkg))

@test
def t_the_failure_log_hides_the_customer_not_the_shape():
    x = ('<m:Email>jo@x.co</m:Email><m:Phone>07000</m:Phone><m:Address1>10 Nethercote</m:Address1>'
         '<m:Company></m:Company><m:Key>k</m:Key><sd:City>Manchester</sd:City>')
    red = worldoptions._redacted(x)
    for bad in ("jo@x.co", "07000", "10 Nethercote", ">k<"):
        ok(bad not in red, repr(bad) + " is not in the log")
    ok("<m:Company></m:Company>" in red, "an EMPTY field still reads as empty, which is the point")
    ok("<m:Email>***</m:Email>" in red, "a filled field reads as filled")

@test
def t_a_rejected_booking_hands_back_the_evidence():
    # The whole point: a failure must be readable at the dispatch desk, not only in
    # a server log somebody else has to go and find.
    reset_dispatch(); reset_prod()
    async def refuse(service, action, inner, retryable=True):
        if service == "ShipmentService":
            raise worldoptions.WorldOptionsError(
                "Value cannot be null.\r\nParameter name: input",
                raw="Value cannot be null.\r\nParameter name: input")
        return ET.fromstring(RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = refuse
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        body = r.json()
        ok(body.get("error"), "the failure is reported")
        tech = body.get("tech") or {}
        ok(tech.get("reply"), "their exact words come back, for World Options support")
        ok("Parameter name: input" in tech["reply"], "verbatim, not paraphrased")
        ok(tech.get("request"), "and the request that caused it")
        ok("<sd:ServiceTypeCode>" in tech["request"], "the request is the real envelope")
        eq(tech.get("order"), "12345", "tied to the order")
        ok(tech.get("when"), "and timestamped")
        # Nothing private in what we hand over.
        for bad in ("testsecret", "shpat_"):
            ok(bad not in json.dumps(tech), bad + " is not in the detail")
        # And it survives the window being closed.
        rows = desk._load_wo_failures()
        eq(len(rows), 1, "kept on disk")
        eq(rows[0]["order"], "12345", "the stored copy is the same failure")
    finally:
        worldoptions._soap_call = saved

@test
def t_the_booking_auth_block_sends_its_optional_strings_but_the_quote_is_untouched():
    # Quoting demonstrably works, so its envelope is left exactly as it is.
    # ShipmentService is different code and may read fields RateService never does.
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder[service] = inner
        return ET.fromstring(BOOK_XML if service == "ShipmentService" else RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        a = {"name": "A", "street": "1 St", "city": "M", "postcode": "M1 1AA",
             "country": "GB", "phone": "1", "email": "a@b.c"}
        box = [{"width": 1, "length": 1, "depth": 1, "weight": 1}]
        run(worldoptions.quote(a, a, box))
        run(worldoptions.book({"service_type_code": "UPS_Standard",
                               "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              a, a, box))
        for el in ("SubUserKey", "WebLeadCompanyName", "WebLeadPostalCode"):
            ok("<m:%s>" % el in holder["ShipmentService"], el + " is sent when booking")
            ok("<m:%s>" % el not in holder["RateService"], el + " is NOT added to the quote")
    finally:
        worldoptions._soap_call = saved

@test
def t_a_signature_literal_never_crosses_carriers():
    # wsSignatureTypes has no no-signature member for UPS at all. Sending FedEx's on
    # a UPS booking is what produced "Value cannot be null. Parameter name: input":
    # their service looks up its own mapping, finds nothing, and throws.
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner
        return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        a = {"name": "A", "street": "1 St", "city": "M", "postcode": "M1 1AA",
             "country": "GB", "phone": "1", "email": "a@b.c"}
        box = [{"width": 1, "length": 1, "depth": 1, "weight": 1}]
        # UPS has no equivalent: the setting is dropped, not translated.
        run(worldoptions.book({"service_type_code": "UPS_Standard",
                               "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              a, a, box, signature="Fedex_No_Signature_Required"))
        ok("Fedex_" not in holder["xml"], "no FedEx literal rides on a UPS booking")
        ok("<wo:DeliverySignatureType>" not in holder["xml"], "and nothing invalid is invented")
        # DHL does have one: the intent survives in DHL's own wording.
        run(worldoptions.book({"service_type_code": "DHL_DOMESTIC_EXPRESS",
                               "package_type_code": "DHL_NonDocument", "carrier_name": "DHL"},
                              a, a, box, signature="Fedex_No_Signature_Required"))
        ok("<wo:DeliverySignatureType>DHL_No_Signature_Required</wo:DeliverySignatureType>"
           in holder["xml"], "translated into the booked carrier's own literal")
    finally:
        worldoptions._soap_call = saved

@test
def t_no_signature_is_only_offered_where_it_can_be_bought():
    # Every carrier gets cheaper prices in the no-signature sweep, but only FedEx
    # and DHL can actually be booked without one. Offering the rest is a saving
    # that vanishes at the till, or a booking that fails.
    for code in worldoptions.NO_SIGNATURE_BY_CARRIER:
        ok(worldoptions.NO_SIGNATURE_BY_CARRIER[code] in worldoptions.SIGNATURE_OPTIONS[code],
           code + "'s no-signature literal is one of its own options")
    eq(worldoptions.NO_SIGNATURE_BY_CARRIER.get("UPS"), None, "UPS has none, and none is invented")
    reset_dispatch(); reset_prod()
    r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
    for o in r.json()["options"]:
        if o.get("no_signature"):
            ok(o["carrier_name"] in worldoptions.NO_SIGNATURE_BY_CARRIER,
               "offered only for " + o["carrier_name"] + ", which can be booked that way")

@test
def t_ready_from_is_never_in_the_past():
    # "Invalid Date, Parcel Ready From": the settings window is a preference, not
    # the answer. Booking after the window opens must roll the time forward, and
    # booking after close (or on a weekend) must roll to the next working day.
    from datetime import datetime as dt
    from zoneinfo import ZoneInfo
    L = ZoneInfo("Europe/London")
    cfg = {"ready_time": "14:00", "close_time": "17:30"}
    eq(desk._collection_ready(cfg, dt(2026, 8, 12, 10, 0, tzinfo=L)),
       ("12/08/2026", "14:00"), "before the window: the window stands")
    eq(desk._collection_ready(cfg, dt(2026, 8, 12, 15, 20, tzinfo=L)),
       ("12/08/2026", "16:00"), "past the window start: rolled forward, still today")
    eq(desk._collection_ready(cfg, dt(2026, 8, 12, 18, 0, tzinfo=L)),
       ("13/08/2026", "14:00"), "after close: next day")
    eq(desk._collection_ready(cfg, dt(2026, 8, 14, 17, 45, tzinfo=L)),
       ("17/08/2026", "14:00"), "friday evening: monday, not saturday")
    eq(desk._collection_ready(cfg, dt(2026, 8, 15, 11, 0, tzinfo=L)),
       ("17/08/2026", "14:00"), "saturday: monday")
    d, t = desk._collection_ready({}, dt(2026, 8, 12, 15, 20, tzinfo=L))
    eq((d, t), ("12/08/2026", "16:00"), "no window configured still yields a sane future slot")

BOOK_URL_XML = BOOK_XML.replace(
    "<ShippingLabel><Image>JVBERi0xLjQK</Image><ImageLength>10</ImageLength><IsThermalPrint>false</IsThermalPrint><LabelType>PDF</LabelType><LabelURL/></ShippingLabel>",
    "<ShippingLabel><Image/><ImageLength>0</ImageLength><IsThermalPrint>false</IsThermalPrint><LabelType/><LabelURL>/GetLabel.ashx?id=42</LabelURL></ShippingLabel>")

@test
def t_a_label_link_is_downloaded_into_a_file_at_booking():
    # Their LabelURL can be relative. Opened from inside the admin it resolves
    # against THIS app and shows our 404 ("Not Found"), so the server downloads
    # the file once and stores the bytes instead of the link.
    reset_dispatch(); reset_prod()
    async def cap(service, action, inner, retryable=True):
        return ET.fromstring(BOOK_URL_XML if service == "ShipmentService" else RATE_XML)
    async def fake_fetch(url):
        eq(url, "/GetLabel.ashx?id=42", "handed the link as WO sent it")
        return {"type": "base64pdf", "value": "JVBERi0xLjQK", "label_type": "PDF",
                "source_url": "https://service.worldoptions.co.uk/GetLabel.ashx?id=42"}
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    saved_fetch = worldoptions.fetch_label; worldoptions.fetch_label = fake_fetch
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        eq(r.status_code, 200, r.text)
        lbls = r.json()["dispatch"].get("labels") or r.json().get("labels") or []
        stored = desk._load_dispatch_labels(12345)
        eq(stored[0]["type"], "base64pdf", "stored as the FILE, not the link: " + str(stored[0].get("type")))
    finally:
        worldoptions._soap_call = saved; worldoptions.fetch_label = saved_fetch

@test
def t_a_stored_link_label_heals_itself_on_reprint():
    # The order booked BEFORE this fix has a dead link on disk. Opening its label
    # downloads the real file and saves it back.
    reset_dispatch(); reset_prod()
    desk._save_dispatch_labels(777, [{"type": "url", "value": "/GetLabel.ashx?id=9"}])
    async def fake_fetch(url):
        return {"type": "base64pdf", "value": "JVBERi0xLjQK", "label_type": "PDF"}
    saved_fetch = worldoptions.fetch_label; worldoptions.fetch_label = fake_fetch
    try:
        r = post("/api/dispatch/label", {"order_id": 777})
        eq(r.status_code, 200, r.text)
        eq(r.json()["labels"][0]["type"], "base64pdf", "served as a file")
        eq(desk._load_dispatch_labels(777)[0]["type"], "base64pdf", "and healed on disk")
    finally:
        worldoptions.fetch_label = saved_fetch

@test
def t_an_unfetchable_link_is_kept_not_lost():
    reset_dispatch(); reset_prod()
    desk._save_dispatch_labels(778, [{"type": "url", "value": "/GetLabel.ashx?id=9"}])
    async def dead_fetch(url):
        return {}
    # The evidence panel asks the link what it answers; a dead link answers 404.
    async def dead_link(url, timeout):
        return 404, b"<html>Not Found</html>", url
    saved = (worldoptions.fetch_label, worldoptions._get_label_bytes)
    worldoptions.fetch_label, worldoptions._get_label_bytes = dead_fetch, dead_link
    try:
        r = post("/api/dispatch/label", {"order_id": 778})
        eq(r.json()["labels"][0]["type"], "url", "the link survives when the download fails")
    finally:
        worldoptions.fetch_label, worldoptions._get_label_bytes = saved

@test
def t_label_urls_only_fetch_from_world_options():
    eq(worldoptions._label_url("https://evil.example.com/a.pdf"), "", "foreign hosts refused")
    ok(worldoptions._label_url("/x.pdf").startswith("https://service.worldoptions.co.uk/"),
       "relative links resolve against their service host")
    eq(worldoptions._label_from_bytes(b"<html>Not Found</html>"), {},
       "an HTML error page is never saved as a label")

@test
def t_pdf_labels_gain_print_images():
    # A REAL one-page PDF made on the spot: the truncated fixture bytes would only
    # prove the failure path.
    import base64 as b64, io
    import pypdfium2
    doc = pypdfium2.PdfDocument.new(); doc.new_page(288, 432)
    buf = io.BytesIO(); doc.save(buf)
    real_pdf = b64.b64encode(buf.getvalue()).decode()
    out = desk._with_print_images([{"type": "base64pdf", "value": real_pdf}])
    imgs = out[0].get("print_images") or []
    eq(len(imgs), 1, "one page, one image")
    ok(b64.b64decode(imgs[0]).startswith(b"\x89PNG"), "a real PNG")
    # Broken bytes degrade to no images, never an error: Download still works.
    out2 = desk._with_print_images([{"type": "base64pdf", "value": "JVBERi0xLjQK"}])
    eq(out2[0].get("print_images"), None, "unrenderable PDF stays downloadable")

@test
def t_reprint_attaches_print_images_and_saves_them():
    import base64 as b64, io
    import pypdfium2
    doc = pypdfium2.PdfDocument.new(); doc.new_page(288, 432)
    buf = io.BytesIO(); doc.save(buf)
    real_pdf = b64.b64encode(buf.getvalue()).decode()
    reset_dispatch(); reset_prod()
    desk._save_dispatch_labels(779, [{"type": "base64pdf", "value": real_pdf}])
    r = post("/api/dispatch/label", {"order_id": 779})
    eq(r.status_code, 200, r.text)
    ok(r.json()["labels"][0].get("print_images"), "images served for printing")
    ok(desk._load_dispatch_labels(779)[0].get("print_images"), "and saved back")

@test
def t_customs_lines_carry_the_cost_price_and_the_products_own_hs_code():
    # The user's example: a 200 watt projector, cost 425.00, HS 9008.50.00. Both
    # live on the variant's INVENTORY ITEM in Shopify, and customs declares what
    # the goods are worth to the merchant, not what the customer paid.
    reset_dispatch(); reset_prod()
    order = {"id": 12345, "name": "#12345", "currency": "GBP", "email": "c@x.co",
             "total_price": "780.00",
             "shipping_address": {"first_name": "A", "last_name": "B", "address1": "1 Rue",
                                  "city": "Paris", "zip": "75001", "country_code": "FR",
                                  "phone": "0033", "name": "A B"},
             "line_items": [
                 {"id": 1, "title": "Projected Image 200 Watt Gobo Projector", "quantity": 1, "price": "780.00",
                  "variant_id": 111},
                 {"id": 2, "title": "Custom Gobo", "quantity": 2, "price": "45.00",
                  "variant_id": None},
             ]}
    async def tools(registry, name, args):
        if name == "shopify_get_order":
            return order
        if name == "shopify_get_variant":
            eq(args["variant_id"], 111, "only the real variant is looked up")
            return {"id": 111, "inventory_item_id": 9001}
        if name == "shopify_get_inventory_items":
            eq(args["ids"], "9001", "batched by inventory item id")
            return {"inventory_items": [{"id": 9001, "cost": "425.00",
                                         "harmonized_system_code": "9008.50.00",
                                         "country_code_of_origin": "GB"}]}
        return {}
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": BOX})
        eq(r.status_code, 200, r.text)
        body = r.json()
        ok(body.get("international"), "France is international")
        items = body.get("customs_items") or []
        eq(len(items), 2, "every real line is present")
        proj = items[0]
        eq(proj["cost"], "425.00", "the COST price, not the 780.00 sale price")
        eq(proj["hs_code"], "9008.50.00", "the product's own HS code")
        eq(proj["origin"], "GB", "origin from Shopify")
        gobo = items[1]
        eq(gobo["cost"], "", "no variant -> no cost")
        # The house value rules: gobos are custom work declared at SALE value
        # (no missing-cost warning for them); stocked goods at COST.
        eq(gobo["unit_value"], "45.00", "a gobo is declared at its sale price")
        eq(gobo["value_basis"], "sale", "and that is by design")
        eq(gobo["needs_cost"], False, "so no missing-cost nag for a gobo")
        eq(gobo["hs_code"], "9002.20.000", "every gobo is 9002.20.000")
        eq(proj["unit_value"], "425.00", "a projector is declared at cost")
        eq(proj["value_basis"], "cost", "explicitly")
        # Origin rules: Shopify's own value wins (the projector's inventory item
        # says GB here); with nothing in Shopify, the merchant's blanket rule
        # applies: projectors are made in China, gobos (everything else) in the UK.
        eq(proj["origin"], "GB", "Shopify origin wins when set")
        eq(gobo["origin"], "GB", "a gobo with no Shopify origin is UK")
    finally:
        shopify._tool_json = saved

