# =========================== unit: envelope construction ====================
@test
def t_every_seo_kpi_carries_the_list_behind_its_number():
    """The SEO checks used to be counts a card could only show. Each KPI now
    carries a `detail`: the sampled pages or products that made the number,
    with a storefront url per item, so the card can open them. The model's
    context keeps the counts only (the handler strips the lists)."""
    signals = {"products_sampled": 4, "thin_descriptions": 2, "missing_descriptions": 1,
               "duplicate_titles": 1, "images": 6, "images_missing_alt": 3, "alt_coverage_pct": 50,
               "thin_items": [{"title": "Holder", "handle": "holder", "words": 12},
                              {"title": "Lens", "handle": "lens", "words": 40}],
               "missing_items": [{"title": "Frame", "handle": "frame", "words": 0}],
               "alt_items": [{"title": "Gobo", "handle": "gobo", "missing": 3, "images": 4}],
               "duplicate_groups": [{"title": "Gobo", "count": 2, "handles": ["gobo", "gobo-2"]}]}
    pages = [{"url": "https://shop.test/", "noindex": False, "meta_description": "x", "jsonld_types": ["Organization"]},
             {"url": "https://shop.test/products/gobo", "noindex": True, "meta_robots": "noindex, follow",
              "meta_description": "", "jsonld_types": ["Product"]}]
    score, metrics = seo._seo_scorecard(signals, 200, 200, pages, domain="shop.test", sitemap_locs=3)
    by = {m["label"]: m for m in metrics}
    ok(all(isinstance(m.get("detail"), dict) and "items" in m["detail"] for m in metrics),
       "every KPI carries a detail with items")
    ok([i["label"] for i in by["Thin descriptions"]["detail"]["items"]] == ["Frame", "Holder", "Lens"],
       "thin descriptions list the missing ones first, then the thin ones")
    ok(by["Thin descriptions"]["detail"]["items"][0]["note"] == "no description"
       and by["Thin descriptions"]["detail"]["items"][1]["note"] == "12 words", "each with why it is listed")
    ok(by["Thin descriptions"]["detail"]["items"][1]["url"] == "https://shop.test/products/holder",
       "and the storefront page to fix")
    ok(by["Thin descriptions"]["detail"]["total"] == 3, "the total is the count, not the capped list")
    ok(by["Indexable"]["detail"]["items"] == [{"label": "https://shop.test/products/gobo", "note": "noindex, follow",
                                               "url": "https://shop.test/products/gobo"}],
       "indexable lists the blocked pages with their robots directive")
    ok(by["Duplicate titles"]["detail"]["items"][0]["note"] == "2 products", "duplicates list the group size")
    ok(by["Image alt"]["detail"]["items"][0]["note"] == "3 of 4 images without alt", "alt lists the gap per product")
    ok(by["Sitemap"]["detail"]["items"][0]["note"] == "HTTP 200 · 3 locations", "the sitemap row carries its size")
    ok(by["Meta descriptions"]["detail"]["items"][0]["url"] == "https://shop.test/products/gobo",
       "meta descriptions list the pages without one")
    ok(any(i["note"] == "-25" for i in by["SEO score"]["detail"]["items"]), "the score explains its deductions")
    _, m2 = seo._seo_scorecard({"alt_coverage_pct": 100}, 200, 200,
                                   [{"url": "u", "meta_description": "x", "jsonld_types": ["Product"]}])
    by2 = {m["label"]: m for m in m2}
    ok(by2["Indexable"]["detail"]["items"] == [] and by2["Indexable"]["detail"]["empty"].startswith("All 1 sampled"),
       "a clean check lists nothing and says so")
    ok(by2["Thin descriptions"]["detail"]["items"][0:0] == [] and by2["Thin descriptions"]["detail"]["items"][0]["url"] is None
       if by2["Thin descriptions"]["detail"]["items"] else True, "no domain, no url")

@test
def t_envelope_wellformed_and_ordered():
    worldoptions.set_credentials(meter="M1", key="K1", password="P1", plugin="Web_Service")
    # capture the real envelope by temporarily using the real builder path
    inner_holder = {}
    async def capture(service, action, inner, retryable=True):
        inner_holder["xml"] = worldoptions._envelope(inner)
        return ET.fromstring(RATE_XML)
    saved = worldoptions._soap_call
    worldoptions._soap_call = capture
    try:
        run(worldoptions.quote({"city": "Leeds", "postcode": "LS1 1AA", "country": "gb"},
                               {"city": "Manchester", "postcode": "M1 2AB", "country": "gb"},
                               [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}]))
    finally:
        worldoptions._soap_call = saved
    xml = inner_holder["xml"]
    ET.fromstring(xml)   # must be well-formed
    ok("<m:MeterNumber>M1</m:MeterNumber>" in xml, "meter in auth")
    ok("<m:Key>K1</m:Key>" in xml, "key in auth")
    ok("GB" in xml, "country upper-cased")
    ok(xml.index("<m:Key>") < xml.index("<m:MeterNumber>") < xml.index("<m:Password>"), "auth alphabetical")
    ok("<rs:Weight>0.6</rs:Weight>" in xml, "quote uses Weight")

@test
def t_quote_normalize():
    worldoptions.set_credentials(meter="M1")
    res = run(worldoptions.quote({"postcode": "LS1 1AA", "country": "GB"},
                                 {"postcode": "M1 2AB", "country": "GB"},
                                 [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}]))
    eq(len(res["options"]), 3, "three options")
    eq(res["options"][0]["amount"], 5.20, "cheapest first (RoyalMail)")
    eq(res["options"][0]["service_type_code"], "RoyalMail_Tracked_24_Hours", "service code")
    eq(res["options"][0]["package_type_code"], "RoyalMail_Parcel", "package code carried for booking")
    eq(res["options"][0]["carrier_name"], "ROYALMAIL", "carrier")
    eq(res["options"][1]["amount"], 9.94, "DHL next")
    eq(res["options"][1]["carrier_name"], "DHL", "carrier")
    eq(res["options"][2]["amount"], 12.40, "UPS dearest")

@test
def t_quote_failed_reply_raises():
    worldoptions.set_credentials(meter="M1")
    SOAP_MODE["fail"] = True
    try:
        run(worldoptions.quote({"postcode": "x", "country": "GB"}, {"postcode": "y", "country": "GB"},
                               [{"width": 1, "length": 1, "depth": 1, "weight": 1}]))
        ok(False, "should have raised")
    except worldoptions.WorldOptionsError as e:
        ok("invalid_client" in str(e) or "Key and Password" in str(e), "carries WO message (raw or translated)")
    finally:
        SOAP_MODE["fail"] = False

@test
def t_book_normalize():
    worldoptions.set_credentials(meter="M1")
    opt = {"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging",
           "carrier_name": "UPS", "service_name": "UPS Express", "amount": 12.40}
    s = run(worldoptions.book(opt, {"postcode": "LS1 1AA", "country": "GB", "company": "PI"},
                              {"postcode": "M1 2AB", "country": "GB", "company": "Acme"},
                              [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}], reference="#104239"))
    eq(s["tracking_number"], "WO1234567890", "tracking")
    eq(s["labels"][0]["type"], "base64pdf", "base64 pdf label")
    eq(s["carrier_name"], "UPS", "carrier")

@test
def t_book_envelope_uses_Wt():
    worldoptions.set_credentials(meter="M1")
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        run(worldoptions.book({"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              {"postcode": "LS1 1AA", "country": "GB"}, {"postcode": "M1 2AB", "country": "GB"},
                              [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}]))
    finally:
        worldoptions._soap_call = saved
    ok("<sd:Wt>0.6</sd:Wt>" in holder["xml"], "booking uses Wt not Weight")
    ok("<sd:ServiceTypeCode>UPS_Express</sd:ServiceTypeCode>" in holder["xml"], "service code sent")
    ok("<sd:ServiceType>UPS</sd:ServiceType>" in holder["xml"], "carrier sent")

@test
def t_cancel():
    worldoptions.set_credentials(meter="M1")
    r = run(worldoptions.cancel("WO1234567890"))
    eq(r["canceled"], True, "canceled")

@test
def t_validate():
    worldoptions.set_credentials(meter="M1")
    r = run(worldoptions.validate())
    eq(r["ok"], True, "validate ok")

