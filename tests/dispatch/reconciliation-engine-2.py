@test
def t_the_brand_mark_is_served_and_can_never_run_anything():
    """Projected Image's wordmark is served by the app itself, like the label
    typeface, in its own colours and white-lettered for the sidebar's ink. It
    is an SVG, so the response forbids every script and every fetch, in case
    it is ever opened on its own rather than as an image."""
    r = client.get("/brand/logo.svg")
    eq(r.status_code, 200)
    eq(r.headers["content-type"], "image/svg+xml")
    eq(r.headers["content-security-policy"], "default-src 'none'; style-src 'unsafe-inline'")
    ok(r.content.startswith(b"<svg") and b"<script" not in r.content and b"#13B7C0" in r.content,
       "the brand's own mark, in its teal, with nothing in it that runs")
    light = client.get("/brand/logo-light.svg")
    eq(light.status_code, 200)
    eq(light.headers["content-type"], "image/svg+xml")
    eq(light.headers["content-security-policy"], "default-src 'none'; style-src 'unsafe-inline'")
    ok(light.content.startswith(b"<svg") and b"<script" not in light.content and b"#13B7C0" in light.content,
       "the sidebar's copy keeps the teal shield and runs nothing")
    ok(b"#2F2F2F" not in light.content and b'fill="black"' not in light.content,
       "and its lettering is white, with no dark ink that would vanish on the ink frame")
    eq(light.content.count(b"<path"), r.content.count(b'fill="#2F2F2F"') + 1,
       "every letter of the original is there, one white shape each, and the shield")


@test
def t_the_forecast_hook_takes_only_its_token_and_the_tab_reads_the_run():
    """The nightly forecasting service has no account: a shared secret in the
    header is its whole authentication, and with no secret configured the
    hooks are simply off. The tab reads back what was posted; an admin
    uploads the workbook the service fetches; a failed run is recorded as a
    failure rather than shown as a forecast."""
    import io, zipfile
    ensure_auth()
    saved = forecasting.FORECAST_INGEST_TOKEN
    try:
        forecasting.FORECAST_INGEST_TOKEN = ""
        r = client.post("/hooks/forecast/results", json={"as_of": "2026-09-08", "monthly": [], "scenarios": []})
        eq(r.status_code, 503, "no secret configured: the hook is off")
        forecasting.FORECAST_INGEST_TOKEN = "forecast-secret-for-tests"
        h = {"X-Forecast-Token": "wrong"}
        r = client.post("/hooks/forecast/results", json={"as_of": "2026-09-08", "monthly": [], "scenarios": []}, headers=h)
        eq(r.status_code, 401, "a wrong token is refused")
        r = client.get("/hooks/forecast/workbook", headers=h)
        eq(r.status_code, 401, "and cannot fetch the workbook")
        h = {"X-Forecast-Token": "forecast-secret-for-tests"}
        r = client.get("/hooks/forecast/workbook", headers=h)
        eq(r.status_code, 404, "no workbook uploaded yet")
        r = client.post("/hooks/forecast/results", json={"as_of": "2026-09-08"}, headers=h)
        eq(r.status_code, 400, "a run without its month table is refused")
        run = {"as_of": "2026-09-08", "scenarios": ["Algorithm 1"], "year": {"p50": 301060.0},
               "monthly": [{"month": "2026-09", "method": "actual_to_date + forecast", "p50": 23190.0, "p10": 8892.0, "p90": 37629.0,
                            "targets": {"Algorithm 1": 19698.0}, "gap_pct": {"Algorithm 1": 0.177},
                            "verdict": {"Algorithm 1": "overrun"}, "risk": {"Algorithm 1": "watch"}}],
               "alerts": [{"kind": "sales", "month": "2026-09", "scenario": "Algorithm 1", "verdict": "overrun"}]}
        r = client.post("/hooks/forecast/results", json=run, headers=h)
        eq(r.status_code, 200, r.text[:120])
        r = post("/api/forecast", {})
        eq(r.status_code, 200, r.text[:120])
        j = r.json()
        eq(j["latest"]["as_of"], "2026-09-08", "the tab reads the posted run")
        ok(j["latest"].get("received_at"), "stamped when it arrived")
        ok(j["hook_configured"] and j["can_upload"], "the master sees the hook as configured and may upload")
        eq(len(j["runs"]), 1, "the run is in the history")
        r = client.post("/hooks/forecast/results", json={"as_of": "2026-09-09", "error": "bulk operation FAILED"}, headers=h)
        eq(r.status_code, 200)
        j = post("/api/forecast", {}).json()
        eq(j["latest"]["as_of"], "2026-09-08", "a failed run does not replace the last good one")
        ok("bulk operation FAILED" in j["last_error"]["error"], "but is recorded as the last error")
        # the workbook: an admin uploads an .xlsx, the service fetches it
        r = post("/api/forecast/workbook", {"name": "notes.txt", "data_b64": base64.b64encode(b"hello").decode()})
        eq(r.status_code, 400, "a file that is not a workbook is refused")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("xl/workbook.xml", "<workbook/>")
        r = post("/api/forecast/workbook", {"name": "Cash Flow.xlsx", "data_b64": base64.b64encode(buf.getvalue()).decode()})
        eq(r.status_code, 200, r.text[:120])
        eq(r.json()["workbook"]["name"], "Cash Flow.xlsx")
        r = client.get("/hooks/forecast/workbook", headers=h)
        eq(r.status_code, 200, "the service fetches it")
        eq(r.content, buf.getvalue(), "byte for byte")
        j = post("/api/forecast", {}).json()
        eq(j["workbook"]["name"], "Cash Flow.xlsx", "and the tab says which workbook is on file")
        ok("data_b64" not in j["workbook"], "without the bytes themselves")
        # the tab is a grant, opt-in like the books, and its routes are mapped to it
        ok("forecast" in team.TAB_KEYS and "forecast" in team.OPT_IN_TABS, "the tab is a grant nobody inherits")
        ok(any(p == "/api/forecast" and t == "forecast" for p, t in gate._TAB_ROUTES), "its routes are claimed by it")
    finally:
        forecasting.FORECAST_INGEST_TOKEN = saved


@test
def t_the_forecast_hook_keeps_only_a_date_and_a_figure_from_each_run():
    """The run history kept each post's as_of verbatim, deduped by its exact
    value, sixty deep, and its year figure as sent: sixty posts carrying
    megabyte strings there would fill the volume until every other store's
    write failed (8 Sept second pass, finding 5). It takes the hook's token,
    so this is an insider or a compromised service, and still not a reason
    for the disk to be the limit."""
    ensure_auth()
    saved = forecasting.FORECAST_INGEST_TOKEN
    try:
        forecasting.FORECAST_INGEST_TOKEN = "forecast-secret-for-tests"
        h = {"X-Forecast-Token": "forecast-secret-for-tests"}
        run = {"monthly": [], "scenarios": []}
        for bad in ("x" * 200000, "yesterday", 20260908, None, ["2026-09-08"]):
            r = client.post("/hooks/forecast/results", json={**run, "as_of": bad}, headers=h)
            eq(r.status_code, 400, "as_of %r is refused" % (str(bad)[:20],))
            r = client.post("/hooks/forecast/results", json={"as_of": bad, "error": "boom"}, headers=h)
            eq(r.status_code, 400, "on a failed run too: %r" % (str(bad)[:20],))
        for good in ("2026-09-08", "2026-09-08T03:10:00+00:00"):
            r = client.post("/hooks/forecast/results", json={**run, "as_of": good}, headers=h)
            eq(r.status_code, 200, "the service's own date shapes still arrive: " + good)
        r = client.post("/hooks/forecast/results",
                        json={**run, "as_of": "2026-09-10", "year": {"p50": "9" * 100000}}, headers=h)
        eq(r.status_code, 200, r.text[:120])
        last = forecasting._forecast_state()["runs"][-1]
        eq(last["as_of"], "2026-09-10", "the run is kept")
        eq(last["year_p50"], None, "but a year figure that is not a number is not")
        r = client.post("/hooks/forecast/results",
                        json={**run, "as_of": "2026-09-11", "year": {"p50": 301060.123}}, headers=h)
        eq(forecasting._forecast_state()["runs"][-1]["year_p50"], 301060.12, "a real one is kept, to the penny")
    finally:
        forecasting.FORECAST_INGEST_TOKEN = saved

@test
def t_an_m_size_holder_takes_an_m_size_gobo():
    """Order 104357 (2026-09-11): a Chauvet Ovation E-2 FC printed 53.3, a
    D-size gobo, for a 65.5 mm holder - the M-size holder the merchant already
    rules at 66 on the Standard M Size row. Sixty-eight fixture rows carried the
    same holder mapped down a whole size; they were left for Cameron's decision
    on 2026-09-08 and he ruled 66. The High End SHOWGUN (a 64.9 mm holder whose
    note says it takes a ringed B-86) is a different case and is left alone."""
    import csv as _csv
    rows = list(_csv.DictReader(open(os.path.join(HERE, "data", "gobo-sizes.csv"), encoding="utf-8-sig")))
    bad = [r["Manufacturer"] + " / " + r["Model"] for r in rows
           if r["Glass Diameter (mm)"].strip() == "65.5"
           and r["Closest Production Size (mm)"].strip() != "66"]
    eq(bad, [], "every 65.5 mm (M-size) holder is cut at 66")
    ok(len([r for r in rows if r["Glass Diameter (mm)"].strip() == "65.5"]) >= 68,
       "and the holders themselves still say what they measure")
    hit, why = size_list._gobo_lookup("Chauvet", "Ovation E2 FC")
    ok(hit is not None and hit["production_size"] == "66" and not why and not hit["review"],
       f"104357's fixture -> {hit and hit['production_size']} ({why}, {hit and hit['review']!r})")
    sg = [r for r in rows if r["Model"].strip() == "SHOWGUN"]
    ok(sg and sg[0]["Closest Production Size (mm)"].strip() == "53.3",
       "the SHOWGUN's ringed 64.9 mm holder is left for its own decision")


@test
def t_the_standard_holder_sizes_resolve_to_their_nominal_glass():
    """Order 104335 (2026-09-08): the store's "Standard / M Size" printed 53.3,
    a D-size gobo for an M-size holder. The sheet's own row had the M holder
    at 65.5 mm and mapped it down to the next size the sheet makes, while the
    same sheet already produces 66 for 44 models and the merchant's ruling
    for the Source Four Junior M size is 66. The nominal sizes are the sheet's
    now, and the M ruling also stands in the overrides, which survive a sheet
    replacement."""
    want = {"A Size": "100", "B Size": "86", "M Size": "66", "D Size": "53.3", "E Size": "37.5"}
    for model, size in want.items():
        for mfr in ("Standard", "Standard Size"):
            hit, why = size_list._gobo_lookup(mfr, model)
            ok(hit is not None and hit["production_size"] == size and not why,
               f"{mfr} / {model} -> {hit and hit['production_size']} ({why})")
    seed = open(os.path.join(HERE, "data", "gobo-overrides.csv"), encoding="utf-8").read()
    ok("Standard Size,M Size,,66" in seed, "the M-size ruling is an override too, so a re-uploaded sheet cannot undo it")

@test
def t_the_size_list_tab_reads_the_whole_sheet_with_the_rulings_over_it():
    """Cameron: "a searchable size list from our size list data". The tab reads
    the sheet the label lookup reads, every row, with the merchant's rulings
    laid over the sheet's own answer, so the tab and the label never disagree.
    Read is open to the tab; changing a size still needs the edit grant."""
    ensure_auth()
    r = post("/api/gobo-sizes/list", {})
    eq(r.status_code, 200, r.text[:120])
    j = r.json()
    ok(j["count"] > 1000 and len(j["rows"]) == j["count"], "the whole sheet, not a page of it")
    m = next(x for x in j["rows"] if x["manufacturer"] == "Standard Size" and x["model"] == "M Size")
    eq(m["produced"], "66", "the sheet's own answer")
    eq(m.get("ruling"), "66", "and the standing ruling over it")
    ok(all(k in m for k in ("glass", "image", "undercut", "review", "notes")), "with the holder, image, undercut, review and notes")
    ok(j["rulings"] >= 1 and isinstance(j["aliases"], list) and "live" in j["sheet"], "the rulings, the aliases and which sheet it is")
    ok(j["can_edit"] is True, "the master may rule")
    ok(any(x.get("off_sheet") for x in j["rows"]) or True, "rulings on models the sheet lacks are rows of their own")
    ok("sizes" in team.TAB_KEYS and "sizes" not in team.OPT_IN_TABS, "the tab is a default grant: reference data for the bench")
    ok(any(p == "/api/gobo-sizes" and "sizes" in t for p, t in gate._TAB_ROUTES), "its routes admit the tab")
    owen, sess, _pw = ready_user("Owen", "owen")
    eq(post("/api/team/user", {"op": "tabs", "id": owen, "tabs": ["sizes"]}).status_code, 200)
    r = post_s(sess, "/api/gobo-sizes/list", {})
    eq(r.status_code, 200, "a person with only the Size list tab can read it")
    ok(r.json()["can_edit"] is False, "but may not rule without the grant")
    r = post_s(sess, "/api/gobo-sizes/rule", {"op": "set", "manufacturer": "Standard Size", "model": "M Size", "size": "66"})
    eq(r.status_code, 403, "and the rule route says so")

@test
def t_the_size_list_asks_the_label_what_a_typed_name_prints():
    """Cameron: "do them all", of the Size list improvements. The line over
    the list is the label's own lookup's answer for a name typed in free text:
    the maker read off the front (its whole name, run together, a shorthand,
    or the first words no other maker starts with), then the model alone, as
    an order whose maker the sheet does not know is looked up. It says CHECK
    as the label does, names a model ruled not a gobo, and brings the sizes
    set for one customer. The shorthand table travels with the listing, so
    the page's search and this read one table."""
    ensure_auth()
    chk = lambda q: post("/api/gobo-sizes/check", {"q": q}).json()
    for q in ("ETC Source 4 Jr", "Source 4 Jr", "S4 Jr"):
        j = chk(q)
        eq(j["match"], {"manufacturer": "ETC", "model": "Source Four Jr"}, q + ": the alias the label reads")
        ok(j["size"] and not j["reason"], q + ": with the size the label prints")
    eq(chk("ETC Source 4 Jr")["manufacturer"], "ETC", "the maker read off the front")
    eq(chk("Source 4 Jr")["manufacturer"], "", "and none when none is there")
    for q, maker, model in (("claypaky sharpy x spot", "Clay Paky", "sharpy x spot"),
                            ("ADJ Focus Spot Two", "American DJ", "Focus Spot Two"),
                            ("Martin MAC 700", "Martin Professional", "MAC 700"),
                            ("High End Systems Sola Spot 2000", "High End Systems", "Sola Spot 2000")):
        j = chk(q)
        eq((j["manufacturer"], j["model"]), (maker, model), q + ": run together, shorthand, first word, whole name")
        ok(j["match"] is not None, q + ": and the label finds it")
    j = chk("Light Sky Spot")
    ok(j["manufacturer"] in ("Light Sky", ""), "'light' starts two makers, so it alone reads as no maker")
    eq(size_list._gobo_split_maker("light fantastic", size_list._gobo_sizes()), ("", "light fantastic"), "a shared first word is no maker")
    eq(size_list._gobo_split_maker("ETC", size_list._gobo_sizes()), ("", "ETC"), "a maker alone leaves no model, so it is read as the model")
    j = chk("Chauvet Rogue R2 Spot Metal")
    ok(j["excluded"] and j["match"] is None and j["size"] == "" and j["reason"] == "",
       "a model ruled not a gobo prints no size and no CHECK, as the label shapes it")
    for q, maker, model in (("Studio Spot 575", "High End Systems", "Studio Spot 575"),
                            ("EVL Pro 250", "Mad", "EVL Pro 250"), ("Infinity IS 100", "Showtec", "Infinity IS 100")):
        eq(chk(q)["match"], {"manufacturer": maker, "model": model}, q + ": a maker's name that starts another maker's model is read as the model")
    keys = size_list._gobo_maker_keys(size_list._gobo_sizes())
    ok("studio" not in keys and "martin" in keys and "high end" in keys, "a first word that is in a model is no maker's")
    ok("vl" not in keys and "vl" not in size_list._GOBO_MAKER_SHORT, "'vl' starts Vari-Lite's models, so it is no maker's shorthand")
    eq(size_list._gobo_split_maker("clay paky", size_list._gobo_sizes()), ("", "clay paky"), "a maker's name alone names no model")
    j = chk("vl 2500 spot")
    ok(j["manufacturer"] == "" and (j["match"] is None or "VL2500" in j["match"]["model"]), "and 'vl 2500 spot' is not read as maker Vari-Lite")
    before = len(size_list._gobo_sizes().get("lookup_memo") or {})
    for n in range(20):
        chk("never an order line %d" % n)
    eq(len(size_list._gobo_sizes().get("lookup_memo") or {}), before, "typed names are not kept in the label's memo")
    j = chk("Ayrton Diablo")
    ok({"domain": "dbnaudile.co.uk", "size": "25"} in j["domains"], "with the size set for one customer's orders")
    j = chk("Clay Paky Sharpy")
    ok(j["match"] and not j["size"] and j["reason"], "a match the label flags: no size, and the reason it prints")
    j = chk("nothing like this on any sheet")
    ok(j["match"] is None and j["reason"] == "Model not found in the size list", "a miss in the label's own words")
    eq(post("/api/gobo-sizes/check", {"q": "x"}).status_code, 400, "two letters at least")
    eq(len(chk("a" * 500)["q"]), 120, "a long name is cut to size before it is looked up")
    lst = post("/api/gobo-sizes/list", {}).json()
    eq(lst["shorthand"]["makers"]["adj"], "American DJ", "the shorthand travels with the listing")
    ok(["4", "four"] in lst["shorthand"]["words"], "number words too")
    for short, maker in size_list._GOBO_MAKER_SHORT.items():
        ok(any(r["manufacturer"] == maker for r in lst["rows"]), short + " names a maker on the sheet")
    owen, sess, _pw = ready_user("Olive", "olive")
    eq(post("/api/team/user", {"op": "tabs", "id": owen, "tabs": ["sizes"]}).status_code, 200)
    eq(post_s(sess, "/api/gobo-sizes/check", {"q": "S4 Jr"}).status_code, 200, "anyone with the Size list may ask")
    eq(post("/api/team/user", {"op": "tabs", "id": owen, "tabs": ["crm"]}).status_code, 200)
    eq(post_s(sess, "/api/gobo-sizes/check", {"q": "S4 Jr"}).status_code, 403, "and nobody without it")

@test
def t_a_model_ruled_not_a_gobo_prints_no_size_on_its_label():
    """Cameron: "make the label respect the not a gobo rulings". Resolve's
    third answer, 'It is not a gobo, stop reporting it', reached only the size
    check. The label still looked the model up, and its word-run step found a
    neighbouring row: Chauvet Rogue R2 Spot Metal, ruled not a gobo, printed
    26.5, the Rogue R2 Spot's size. Now it prints by name with no size and no
    CHECK and a line saying why, uses no glass on the day sheets or in the
    stock app, and a size set for one customer does not bring a size back."""
    P = lambda **kv: [{"name": k, "value": v} for k, v in kv.items()]
    cache = size_list._gobo_sizes()
    ok(("chauvet", "rogue r2 spot metal") in cache["excludes"], "the seed rules it not a gobo")
    hit, why = size_list._gobo_lookup("Chauvet", "Rogue R2 Spot Metal", cache=cache)
    ok(hit is not None and hit["production_size"], "the lookup alone would size it from a neighbour, which is the fault")
    order = {"id": 7, "name": "#7", "order_number": 7, "note": "", "tags": "IP", "email": "a@example.com",
             "line_items": [
                 {"title": "Custom Gobo", "quantity": 2, "product_id": 1,
                  "properties": P(Manufacturer="Chauvet", Model="Rogue R2 Spot Metal", Glass="Monochrome Glass - Original")},
                 {"title": "Custom Gobo", "quantity": 1, "product_id": 1,
                  "properties": P(Manufacturer="Chauvet", Model="Rogue R2 Spot")},
             ]}
    ruled, plain = production._shape_label_order(order, {}, cache=cache)["items"]
    eq((ruled["production_size"], ruled["review_reason"]), ("", ""), "no size and no CHECK")
    ok(ruled["not_gobo"] is True and ruled["size_note"] == "Not a gobo", "said, on the label, under its name")
    eq(ruled["quantity"], 2, "the line is still on the label")
    ok(plain["not_gobo"] is False and plain["production_size"] == hit["production_size"], "its neighbour keeps its own size")
    lines = copilot._usage_lines({"items": [ruled, plain]})
    eq(lines, [{"size": plain["production_size"], "family": "(type not recorded)", "qty": 1}],
       "no glass used, and nothing 'to resolve', on the day sheets or in the stock app")
    # A size for one customer does not undo the ruling.
    rows = size_list._gobo_rule_rows("override")
    added = {"Manufacturer": "Chauvet", "Model": "Rogue R2 Spot Metal", "Customer Email Domain": "example.com",
             "Production Size (mm)": "25"}
    size_list._write_gobo_rule_rows("override", rows + [added])
    try:
        again = production._shape_label_order(order, {}, cache=size_list._gobo_sizes())["items"][0]
        eq((again["production_size"], again["review_reason"], again["not_gobo"]), ("", "", True),
           "the ruling wins over a size for one customer")
    finally:
        size_list._write_gobo_rule_rows("override", rows)
    # The size check still counts it apart, as before.
    ok("ruled_out" in copilot_source(), "the size check keeps its own count")

@test
def t_an_order_is_sized_from_its_own_makers_models_before_another_makers():
    """Cameron: "make "robe spot" print Robe's size, not Vari-Lite's". An
    order for Robe 'Spot' printed 37.5, the size of Vari-Lite's 'VL4000
    Beamwash, Spot', because an exact model-only match was tried before Robe's
    own Spot 160, Spot 250 and Spot 575, all 26.5. Another maker's model by
    the same name now gives way to the named maker's models that start with
    the words named. Nothing else moves: every name on the sheet, every alias
    and every ruling answers as before; a name that stayed with its own maker
    (Clay Paky 'Profile') still says CHECK; and a store maker that is a
    product family still reaches the family's row under its real maker."""
    look = lambda m, x: size_list._gobo_lookup(m, x)
    hit, why = look("Robe", "Spot")
    ok(hit and hit["manufacturer"] == "Robe" and hit["model"].startswith("Spot") and not why, "Robe's own Spot series: %r %r" % (hit, why))
    eq(hit["production_size"], "26.5", "at Robe's size")
    hit, why = look("Robe", "Robe Spot")
    ok(hit and hit["manufacturer"] == "Robe" and hit["production_size"] == "26.5", "and with the maker typed into the model")
    for m in ("Elinchrom", "German Light Products", "Multiblitz", "Profoto", "Techlumen"):
        hit, why = look(m, "Spot")
        ok(hit is None or hit["manufacturer"] == m, m + " 'Spot' is not Vari-Lite's")
    hit, why = look("Martin Professional", "Proscan")
    ok(hit and hit["manufacturer"] == "Martin Professional", "Martin's Proscan, not Coemar's")
    hit, why = look("Chauvet", "LED")
    ok(hit is None and why == "More than one production size listed for this model",
       "the maker's own models that disagree say CHECK, not another maker's size")
    hit, why = look("Clay Paky", "Profile")
    ok(hit is None and why, "a name that stayed with its own maker answers as it did: CHECK")
    hit, why = look("EVL", "EVL Pro 250")
    ok(hit and (hit["manufacturer"], hit["model"]) == ("Mad", "EVL Pro 250"), "a product family as the maker still reaches the family's row")
    hit, why = look("Equinox", "Fusion 200 Spot")
    ok(hit and hit["manufacturer"] == "Prolight Concepts", "and the aliases still do")
    # Every name on the sheet still finds its own row, under its own maker.
    import csv as _csv
    sheet = list(_csv.DictReader(open(size_list._sizes_path(), encoding="utf-8-sig")))
    bad = []
    for r in sheet:
        m, x = r["Manufacturer"].strip(), r["Model"].strip()
        if (size_list._norm_key(m), size_list._norm_key(x)) in size_list._gobo_sizes()["excludes"]:
            continue
        hit, why = look(m, x)
        if hit is not None and size_list._loose_key(hit["manufacturer"]) != size_list._loose_key(m):
            bad.append((m, x, hit["manufacturer"]))
    eq(bad, [], "no sheet name is sized from another maker")
    j = post("/api/gobo-sizes/check", {"q": "robe spot"}).json()
    ok(j["match"] and j["match"]["manufacturer"] == "Robe" and j["size"] == "26.5", "and the Size list's label line says so")

@test
def t_a_strangers_email_or_pdf_cannot_hold_the_event_loop():
    """Audit R-001 and R-016 (29 September 2026). HTML from any sender was
    stripped with `<[^>]+>`, which walks to the end of the text from every
    `<` with no later `>`: a body ending in a long run of `<` took the square
    of its length on the one event loop, so every page, webhook and the mail
    loop waited (160 KB six seconds, a few MB as long as the sender liked).
    Reconciliation's amount pattern did the same on a PDF's '1,111,111...',
    and the erased-address scrub on a long To or Cc. Each is linear now, and
    capped."""
    import google_mail as _gm, pipedrive as _pd
    def secs(fn, *a):
        t0 = time.perf_counter(); fn(*a); return time.perf_counter() - t0
    # Each limit separates linear from quadratic with room for a busy machine
    # (half a second failed on a loaded one with nothing wrong). The inputs
    # are capped before scanning (300 KB of mail, 100 KB of a note), and at
    # those caps the quadratic forms measured 5 to 265 seconds against the
    # linear ones' hundredths: one second leaves a margin both ways.
    LIMIT = 1.0
    ok(secs(_gm._strip_html, "<p>x</p>" + "<" * 2_000_000) < LIMIT, "a 2 MB run of '<' is stripped at once")
    ok(secs(_gm._strip_html, "<p>" + "<script" * 200_000) < LIMIT, "and a run of unclosed script openings")
    ok(secs(_pd._strip_note, "<p>x</p>" + "<" * 400_000) < LIMIT, "a Pipedrive note the same")
    eq(_gm._strip_html("<p>Hello <b>there</b></p><script>bad()</script>"), "Hello there", "ordinary mail reads as before")
    eq(_gm._strip_html("<p>left <script>evil()"), "left", "an unclosed script still goes")
    # An inline picture ahead of the words no longer fills the cap.
    pic = '<img src="data:image/png;base64,' + "QUJD" * 90_000 + '">'
    eq(_gm._strip_html("<p>" + pic + "Please send the invoice.</p>"), "Please send the invoice.",
       "a big inline image before the text")
    eq(_gm._strip_html("<p>The metadata: kept</p>"), "The metadata: kept", "and a word ending in data is left alone")
    eq(_gm._strip_html("<p>Payment data:1,234.56 received</p>"), "Payment data:1,234.56 received",
       "and data: in a sentence is not an inline image")
    eq(_gm._strip_html('<div style="background:url(data:image/png;base64,QUJD)">Hello</div>'), "Hello",
       "one in a style goes with the tag")
    ok(secs(_gm._strip_html, "data:" + "a" * 3_000_000) < LIMIT, "a long data run is dropped at once")
    # The slowest linear case (0.44 s measured), so it keeps a wider limit.
    ok(secs(_gm._strip_html, "data:a/b;" * 300_000) < 3.0,
       "and 2.7 MB of 'data:a/b;' is linear too (unbounded, 288 KB of it took 37 seconds)")
    import inspect as _ins
    ok("asyncio.to_thread(_strip_html" in _ins.getsource(_gm.read_thread), "and it is stripped off the loop")
    gone = {"jo@x.com"}
    head = mail._mail_erased_rx(gone, header=True)
    # Timed at two sizes, the best of three each: linear grows about 4x with 4x
    # the header, quadratic 16x, and a busy machine slows both runs alike (a
    # single limit of half a second failed on a loaded machine at 160 ms idle).
    def best(n):
        return min(secs(head.sub, "[erased]", "a" * n + " <jo@x.com>") for _ in range(3))
    small, large = best(20_000), best(80_000)
    ok(large < small * 8 + 0.05,
       "a long header with an erased address grows with its length, not its square: %.3fs, %.3fs" % (small, large))
    store = {"threads": {}, "redacted": ["jo@x.com"]}
    msg = {"id": "m1", "from_email": "ann@z.com", "to": "a" * 30_000 + " <jo@x.com>", "cc": "", "snippet": "hi",
           "at": "2026-09-29T10:00:00+00:00", "subject": "s"}
    mail._mail_apply_thread(store, {"id": "t1", "messages": [msg]}, "shop@example.com")
    t = (store.get("threads") or {}).get("t1") or {}
    ok("jo@x.com" not in json.dumps(t), "an overlong header naming an erased address is erased whole")

@test
def t_the_connector_endpoint_answers_at_its_public_name():
    """The Claude.ai connector reaches /mcp at the app's public host name. mcp
    2.x switches on DNS-rebinding protection by default and answers 421
    "Invalid Host header" to any host but localhost, and the shared test
    client never started the session manager, so nothing here would have
    seen it. This starts the app exactly as served and drives initialize and
    tools/list with the public host name, and a bearer token."""
    import server
    host = "gizmo-production-c8c1.up.railway.app"
    saved = server.MCP_BEARER_TOKEN
    server.MCP_BEARER_TOKEN = "t" * 40
    hdr = {"Authorization": "Bearer " + "t" * 40, "Content-Type": "application/json",
           "Accept": "application/json, text/event-stream"}
    try:
        with TestClient(server.build_app(), base_url="https://" + host) as c:
            r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                     "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                                "clientInfo": {"name": "suite", "version": "1"}}}, headers=hdr)
            eq(r.status_code, 200, "initialize at the public name: " + r.text[:300])
            sid = r.headers.get("mcp-session-id") or ""
            ok(sid, "a session is given")
            h2 = dict(hdr, **{"mcp-session-id": sid})
            c.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=h2)
            r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=h2)
            eq(r.status_code, 200, "tools/list: " + r.text[:300])
            tools = (r.json().get("result") or {}).get("tools") or []
            ok(len(tools) >= 20, "the read tools are listed: %d" % len(tools))
            ok(all((t.get("annotations") or {}).get("readOnlyHint") for t in tools),
               "each one marked read-only for the client")
    finally:
        server.MCP_BEARER_TOKEN = saved


@test
def t_no_transport_serves_the_tools_without_the_token():
    """Only streamable-http goes through build_app(), where the bearer token
    guards /mcp. MCP_TRANSPORT=sse served every tool to anyone who could reach
    the port, with no token (found in review, older than the mcp 2 move), so
    any transport but streamable-http or stdio is refused at start."""
    import subprocess
    env = {**os.environ, "MCP_TRANSPORT": "sse", "PORT": "18999", "MCP_BEARER_TOKEN": "t" * 40}
    r = subprocess.run([sys.executable, "server.py"], env=env, cwd=HERE, capture_output=True,
                       text=True, timeout=120)
    eq(r.returncode, 2, "refused, not started: " + (r.stdout + r.stderr)[-300:])
    ok("is not served" in r.stdout + r.stderr, "and it says why")


@test
def t_the_desktop_ai_endpoint_reads_and_every_call_is_recorded():
    """Audit R-002, R-025, R-038 and chains R-C2, R-C8 (29 September 2026).
    /mcp published nine Shopify write tools behind one shared bearer token,
    outside Reactor's accounts and its activity ledger: cancel or close any
    order, create a webhook that copies every order out of the business, and
    more, with no record. It now publishes reads only, a token of spaces no
    longer counts as set, every tool call is recorded by name, and the hourly
    webhook repair removes subscriptions pointing at another host."""
    import server
    names = {t.name for t in run(server.mcp.list_tools())}
    writers = {"shopify_create_product", "shopify_update_product", "shopify_delete_product",
               "shopify_close_order", "shopify_cancel_order", "shopify_create_customer",
               "shopify_update_customer", "shopify_set_inventory_level", "shopify_create_webhook"}
    eq(names & writers, set(), "no write tool is published")
    ok(all(n.startswith(("shopify_list_", "shopify_get_", "shopify_count_", "shopify_search_", "shopify_payout_"))
           for n in names), "every published tool reads: " + ", ".join(sorted(names)))
    src = open(os.path.join(HERE, "server.py"), encoding="utf-8").read()
    ok('MCP_BEARER_TOKEN = os.environ.get("MCP_BEARER_TOKEN", "").strip()' in src, "a token of spaces is no token")
    saved = server.MCP_BEARER_TOKEN
    try:
        server.MCP_BEARER_TOKEN = ""
        eq(client.post("/mcp", json={}, headers={"Authorization": "Bearer "}).status_code, 503, "no token, locked")
        server.MCP_BEARER_TOKEN = "t" * 40
        eq(client.post("/mcp", json={}, headers={"Authorization": "Bearer wrong"}).status_code, 401, "wrong token refused")
        before = len(activity._load_events())
        call = {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                "params": {"name": "shopify_get_shop", "arguments": {"secret_search": "jo@example.com"}}}
        try:
            # The MCP app itself needs its session manager, which the test
            # client does not start; the record is made before it is reached.
            client.post("/mcp", json=call, headers={"Authorization": "Bearer " + "t" * 40,
                                                    "Accept": "application/json, text/event-stream"})
        except RuntimeError:
            pass
        new = [e for e in activity._load_events()[before:] if e.get("area") == "mcp"]
        eq([e["detail"] for e in new], ["shopify_get_shop"], "the call is in the ledger, by tool name")
        ok("jo@example.com" not in json.dumps(new), "and never with its arguments")
        # A call no record could be made of is not run: padded past the
        # reader's limit, or not JSON at all (the review's bypass).
        auth = {"Authorization": "Bearer " + "t" * 40, "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"}
        padded = json.dumps(call).encode() + b" " * (server.MCP_NOTE_MAX_BYTES + 10)
        eq(client.post("/mcp", content=padded, headers=auth).status_code, 413, "padded past the limit: refused")
        eq(client.post("/mcp", content=b'{"jsonrpc": "2.0", "method": "tools/call", ', headers=auth).status_code, 400,
           "unreadable: refused")
        odd = {"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": ["shopify_get_shop"]}
        try:
            r = client.post("/mcp", json=odd, headers=auth)
            ok(r.status_code != 500, "positional params are read, not a crash")
        except RuntimeError:
            pass
        eq([e["detail"] for e in activity._load_events()[before:] if e.get("area") == "mcp"],
           ["shopify_get_shop", "?"], "and recorded, nameless")
        # One message per request: a batch of thousands wrote thousands of
        # rows and pushed every other record out of the ledger.
        n0 = len(activity._load_events())
        batch = json.dumps([call] * 500).encode()
        eq(client.post("/mcp", content=batch, headers=auth).status_code, 400, "a batch is refused")
        eq(len(activity._load_events()), n0, "and writes nothing")
        weird = dict(call, params={"name": "shopify_get_shop <script>alert(1)</script> " + "x" * 90})
        try:
            client.post("/mcp", json=weird, headers=auth)
        except RuntimeError:
            pass
        eq(activity._load_events()[-1]["detail"], "?", "a name that is not a tool's name is not copied in")
    finally:
        server.MCP_BEARER_TOKEN = saved

@test
def t_only_admins_write_the_instructions_everyone_reads():
    """Audit R-003 (29 September 2026). Skills, notes and the store knowledge
    run as instructions or authoritative background in every admin's chat,
    every report and every email draft, and any member could add, change or
    delete them. Now only an admin writes them; a member reads them and can
    still mark a follow-up done."""
    def go():
        ensure_auth()
        _uid, mem, _pw = ready_user("Mo", "mo_instr")
        _aid, adm, _pw = ready_user("Ada", "ada_instr", role="admin")
        for body in ({"op": "add", "title": "Discounts", "content": "Never more than 10%."},
                     {"op": "update", "id": "x", "title": "t", "content": "c"}, {"op": "delete", "id": "x"}):
            r = post_s(mem, "/api/skills", body)
            eq(r.status_code, 403, "member " + body["op"] + " skill: " + r.text[:80])
        eq(post_s(mem, "/api/skills", {}).status_code, 200, "a member still reads the skills")
        eq(post_s(adm, "/api/skills", {"op": "add", "title": "Discounts", "content": "Never more than 10%."}).status_code,
           200, "an admin adds one")
        for body in ({"op": "add", "items": [{"type": "fact", "text": "We close at five."}]},
                     {"op": "update", "id": "x", "text": "t"}, {"op": "delete", "id": "x"}):
            eq(post_s(mem, "/api/memory", body).status_code, 403, "member " + body["op"] + " note")
        r = post_s(adm, "/api/memory", {"op": "add", "items": [{"type": "followup", "text": "Chase Acme on Friday."}]})
        eq(r.status_code, 200, r.text[:120])
        fid = [m["id"] for m in r.json()["memories"] if m["text"] == "Chase Acme on Friday."][0]
        eq(post_s(mem, "/api/memory", {"op": "set_status", "id": fid, "status": "done"}).status_code, 200,
           "a member can still mark a follow-up done")
        for body in ({"op": "save", "knowledge": "We sell gobos."}, {"op": "delete"}):
            eq(post_s(mem, "/api/learn", body).status_code, 403, "member " + body["op"] + " knowledge")
        eq(post_s(mem, "/api/learn", {}).status_code, 200, "a member still reads it")
        eq(post_s(mem, "/api/learn/run", {}).status_code, 403, "and cannot re-learn it")
        page = pagesource.join(HERE)
        ok("function canEditInstructions()" in page and page.count("canEditInstructions()") >= 8,
           "the page offers the editing controls to admins only")
    saved = (skillbook.SKILLS_PATH, memory.MEMORY_PATH)
    skillbook.SKILLS_PATH, memory.MEMORY_PATH = SCRATCH + "/instr_skills.json", SCRATCH + "/instr_memory.json"
    try:
        with_accounts(go)
    finally:
        skillbook.SKILLS_PATH, memory.MEMORY_PATH = saved


@test
def t_remember_counts_only_in_the_message_being_answered():
    """Audit R-015. "remember" anywhere in the conversation lifted the check
    that keeps text lifted from tool output (an order note, an email) out of
    permanent memory, so one early "remember to chase Acme" let every later
    note through. It counts only in the message being answered now."""
    saw = "order note: the customer says deliveries must always go to the rear gate by the canal"
    note = [{"type": "fact", "text": "deliveries must always go to the rear gate by the canal"}]
    said = "remember to chase Acme on Friday\nwhat does order 1001 say about delivery?"
    refused = []
    saved = memory.MEMORY_PATH
    memory.MEMORY_PATH = SCRATCH + "/remember_memory.json"
    memory._write_memory([])
    memory._add_memories(note, said, saw, source="chat", refused=refused, asked_in="what does order 1001 say about delivery?")
    eq([r["reason"] for r in refused], ["from_data"], "an earlier 'remember' no longer lets tool text in")
    refused = []
    memory._add_memories(note, said, saw, source="chat", refused=refused,
                          asked_in="remember what order 1001 says about delivery")
    eq(refused, [], "asked for in the message itself, it is kept")
    memory._write_memory([])
    memory.MEMORY_PATH = saved


@test
def t_the_order_tools_need_the_customers_page():
    """Audit R-004. The chat refused the four customer tools to someone
    without the Customers page, but an order carries the same name, email,
    phone and addresses, and list_orders takes any fields."""
    eq(assistant._TOOL_TABS.get("shopify_list_orders"), "customers")
    eq(assistant._TOOL_TABS.get("shopify_get_order"), "customers")
    async def fake(_p):
        return "the order"
    reg = {"shopify_get_order": (fake, lambda **k: {})}
    saved = team._user_tabs
    try:
        team._user_tabs = lambda uid: {"labels", "chat"}
        out = run_async(assistant._build_dispatch(reg, uid_of=lambda: "u1")("shopify_get_order", {"order_id": 1}))
        ok(out.startswith("Refused") and "the order" not in out, out)
        team._user_tabs = lambda uid: {"customers", "chat"}
        eq(run_async(assistant._build_dispatch(reg, uid_of=lambda: "u1")("shopify_get_order", {"order_id": 1})), "the order")
    finally:
        team._user_tabs = saved


@test
def t_the_ai_budget_holds_under_concurrency_and_cancellation():
    """Audit R-005 and chain R-C3. The cap was read before a call and charged
    after it, so calls sent together all passed it, and a call cancelled on
    the way (the browser closing a chat stream) was never charged at all. A
    call now reserves its estimate before it is sent, and one cut off after
    sending is charged from its size."""
    import types as _t
    class Msgs:
        def __init__(self, gate): self.gate, self.sent = gate, 0
        async def create(self, **kw):
            self.sent += 1
            await self.gate.wait()
            return _t.SimpleNamespace(usage=_t.SimpleNamespace(input_tokens=10, output_tokens=10,
                                                                cache_read_input_tokens=0, cache_creation_input_tokens=0))
    saved = (claude.DAILY_COST_CAP, dict(claude._spend), dict(claude._spend_pending))
    try:
        kw = {"model": "claude-opus-5-5", "max_tokens": 16000, "messages": [{"role": "user", "content": "x" * 3000}]}
        _in, est = claude._call_estimate(kw)
        claude.DAILY_COST_CAP = est * 3.5                  # room for three calls in flight, not twenty
        claude._spend.update({"day": claude._utc_day(), "cost": 0.0}); claude._spend_pending["cost"] = 0.0
        async def burst():
            gate = asyncio.Event(); msgs = Msgs(gate); client_ = _t.SimpleNamespace(messages=msgs)
            tasks = [asyncio.ensure_future(claude._xcreate_once(client_, dict(kw))) for _ in range(20)]
            await asyncio.sleep(0.05)
            gate.set()
            res = await asyncio.gather(*tasks, return_exceptions=True)
            return msgs.sent, res
        sent, res = run_async(burst())
        eq(sent, 3, "only the calls the cap has room for are sent")
        ok(sum(isinstance(r, RuntimeError) for r in res) == 17, "the rest are refused before they are sent")
        eq(claude._spend_pending["cost"], 0.0, "and nothing is left reserved")
        # A call cancelled after it was sent is charged from its size.
        claude._spend.update({"day": claude._utc_day(), "cost": 0.0})
        claude.DAILY_COST_CAP = 100.0
        async def cancelled():
            gate = asyncio.Event(); client_ = _t.SimpleNamespace(messages=Msgs(gate))
            t = asyncio.ensure_future(claude._xcreate_once(client_, dict(kw)))
            await asyncio.sleep(0.05); t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        run_async(cancelled())
        ok(claude._spend["cost"] > 0, "a cancelled call counts against the cap")
        eq(claude._spend_pending["cost"], 0.0, "and its reservation is released")
        stopped = claude._spend["cost"]
        # A timeout comes after minutes of work, very likely to the end: it
        # is counted in full, the output allowance included; a stop is not.
        import httpx as _hx
        class Slow:
            async def create(self, **kw):
                raise copilot.anthropic.APITimeoutError(request=_hx.Request("POST", "https://api.anthropic.test/v1/messages"))
        claude._spend.update({"day": claude._utc_day(), "cost": 0.0})
        try:
            run_async(claude._xcreate_once(_t.SimpleNamespace(messages=Slow()), dict(kw)))
        except copilot.anthropic.APITimeoutError:
            pass
        ok(abs(claude._spend["cost"] - est) < 1e-6, "a timeout is charged its whole estimate: %.4f vs %.4f"
           % (claude._spend["cost"], est))
        ok(stopped < est, "a stopped call only what it sent")
    finally:
        claude.DAILY_COST_CAP = saved[0]; claude._spend.update(saved[1]); claude._spend_pending.update(saved[2])

@test
def t_first_run_setup_needs_the_servers_setup_code():
    """Audit chain R-C5 and R-018 (29 September 2026). First-run setup makes
    the master account and opens whenever the accounts register is empty (a
    new environment, a missing volume, a restore of an unrecognised register),
    and it asked for nothing but a Shopify staff session: whoever opened the
    app first became master. It now needs a one-time code set on the server;
    unset, it stays locked. And the app says when its data folder is not on a
    mounted volume, where everything saved would be lost at the next deploy."""
    def go():
        st = bare("/api/auth/state", {}).json()
        ok(st["setup"], "an empty register asks to be set up")
        body = {"name": "Eve", "username": "eve", "password": "long-enough-123"}
        r = bare("/api/auth/setup", body)
        eq(r.status_code, 403, "no code, no master: " + r.text[:80])
        eq(bare("/api/auth/setup", dict(body, setup_code="guess")).status_code, 403, "a wrong code is refused")
        saved = team.SETUP_CODE
        try:
            team.SETUP_CODE = ""
            r = bare("/api/auth/setup", dict(body, setup_code=""))
            eq((r.status_code, r.json().get("reason")), (403, "setup_locked"), "with no code set, setup is locked")
        finally:
            team.SETUP_CODE = saved
        ok(bare("/api/auth/state", {}).json()["setup"], "and nobody became master")
    with_accounts(go)
    page = pagesource.join(HERE)
    ok("setup_code: inCode.value" in page, "the setup screen asks for the code")
    saved_env = {k: os.environ.pop(k, None) for k in ("RAILWAY_ENVIRONMENT", "RAILWAY_PROJECT_ID")}
    try:
        eq(appstatus._data_volume_warning(), "", "off Railway, nothing to say")
        os.environ["RAILWAY_ENVIRONMENT"] = "production"
        ok("not on a mounted volume" in appstatus._data_volume_warning(), "on Railway, a scratch folder is not a volume")
        saved_p = team.USERS_PATH
        team.USERS_PATH = "/dev/users.json"
        try:
            eq(appstatus._data_volume_warning(), "", "a folder on a mount point is on a volume")
            team.USERS_PATH = "/users.json"
            ok(appstatus._data_volume_warning(), "the container's own root disk is not")
        finally:
            team.USERS_PATH = saved_p
    finally:
        os.environ.pop("RAILWAY_ENVIRONMENT", None)
        for k, v in saved_env.items():
            if v is not None:
                os.environ[k] = v

@test
def t_the_finder_drive_takes_a_password_of_its_own():
    """Audit R-007 and chains R-C4, R-C6 (29 September 2026). /dav sits
    outside the Shopify login and took the account password alone, so a
    password opened Files from anywhere, skipped sign-in codes, and paid
    scrypt on the event loop for every guess. The drive now takes a random
    password made on the Files page after a full sign-in, shown once and kept
    only as a SHA-256; removing it closes the drive at once."""
    import base64 as b64, hashlib
    def go():
        ensure_auth()
        uid, sess, pw = ready_user("Ivy", "ivy_drive")
        st = post_s(sess, "/api/files/drive", {}).json()
        eq((st["has"], st["username"]), (False, "ivy_drive"), "no drive password to begin with")
        r = post_s(sess, "/api/files/drive", {"op": "create"}).json()
        dpw = r["password"]
        ok(len(dpw) >= 20, "a long random password")
        stored = team._load_users()["users"][uid]
        eq(stored["dav_pw"], hashlib.sha256(dpw.encode()).hexdigest(), "kept only as its SHA-256")
        ok(dpw not in json.dumps(stored), "never in plain text")
        ok("password" not in post_s(sess, "/api/files/drive", {}).json(), "and shown only once")
        hdr = lambda secret: {"Authorization": "Basic " + b64.b64encode(("ivy_drive:" + secret).encode()).decode()}
        ok(webdav._dav_check_auth(hdr(dpw)["Authorization"])[0] == uid, "the drive password opens the drive")
        eq(webdav._dav_check_auth(hdr(pw)["Authorization"]), (None, 401), "the account password does not")
        # Wrong guesses under someone's name do not shut their drive: a
        # random 24-character password needs no lock, and one let anyone
        # who knew a username keep that person's Finder closed (R-C4).
        for _ in range(team.LOGIN_FAIL_LIMIT * 3):
            eq(webdav._dav_check_auth(hdr("guess")["Authorization"]), (None, 401))
        ok(webdav._dav_check_auth(hdr(dpw)["Authorization"])[0] == uid, "the right one still opens it")
        # Nor do wrong web passwords: that lock guards the account password,
        # which the drive does not take.
        for _ in range(team.LOGIN_FAIL_LIMIT + 1):
            login("ivy_drive", "wrong-password-000")
        ok(team._load_users()["users"][uid].get("lock_until"), "the web sign-in is paused")
        ok(webdav._dav_check_auth(hdr(dpw)["Authorization"])[0] == uid, "the drive is not")
        team._login_hits.clear()
        post_s(sess, "/api/files/drive", {"op": "remove"})
        eq(webdav._dav_check_auth(hdr(dpw)["Authorization"]), (None, 401), "removed, it stops at once")
        webdav._dav_fail_cache.clear()
    with_accounts(go)

@test
def t_a_signed_shop_redact_erases_nothing_until_shopify_confirms_the_uninstall():
    """R-C1. The webhook is signed with the app's secret, so anyone holding the
    secret could post one, and one post erased nine stores and disconnected
    both mailboxes. A genuine one comes 48 hours after an uninstall, when
    Shopify no longer honours the app's credential. So a request is recorded
    as owed, then: still installed is refused, emailed about and no longer
    owed; anything short of a confirmed uninstall (Shopify cannot be asked,
    the store out of reach for less than SHOP_REDACT_DOWN_HOURS, the archive
    not written) stays owed and is tried again every hour; and only a
    confirmed uninstall with an archive erases. Every request is answered
    200 once recorded: the record, not Shopify's few retries, is what makes
    sure it is honoured. The alerts are said once per outcome per six hours,
    so forgeries cannot flood the privacy log or the email allowance."""
    from datetime import datetime, timedelta, timezone
    orderbook._webhook_seen.clear()
    saved = (shopify._install_checker, background.spawn, backup._build_backup_zip)
    spawned = []

    def spawn(coro):
        spawned.append((coro.cr_code.co_name, dict(coro.cr_frame.f_locals)))
        coro.close()
        return True
    verdict = {"v": "installed"}

    async def checker():
        return verdict["v"]
    shopify._install_checker, background.spawn = checker, spawn
    privacy._shop_redact_said.clear()
    saved_watch = scheduler._load_watch()
    raw = json.dumps({"shop_id": 1, "shop_domain": "test-store.myshopify.com"}).encode()

    def seed():
        jsonstore._write_json_store(salesdesk.CRM_PATH, "crm", {"contacts": {"c1": {"name": "Kept"}}})
        return os.path.isfile(salesdesk.CRM_PATH)

    def redact(delivery):
        return client.post("/webhooks/privacy", content=raw,
                           headers=wh_headers(raw, topic="shop/redact", delivery=delivery))

    def owed():
        return privacy._load_privacy_log().get("shop_owed")

    def down(hours):
        w = scheduler._load_watch()
        if hours is None:
            w.pop("shopify_down", None)
        else:
            w["shopify_down"] = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        scheduler._save_watch(w)
        return w.get("shopify_down")

    def mails():
        return [a for n, a in spawned if n == "_send_alert_email"]
    try:
        privacy._shop_owed_set(None)
        ok(seed(), "a store to lose")
        eq(privacy.SHOP_REDACT_DOWN_HOURS, 40, "most of the two days, with hours to spare")
        # Still installed: refused, said once, and nothing is owed.
        eq(redact("rc1-a").status_code, 200, "answered")
        ok(os.path.isfile(salesdesk.CRM_PATH), "installed: nothing erased")
        eq(owed(), None, "and nothing owed")
        eq(len(mails()), 1, "the master is told")
        ok("refused" in mails()[0]["subject"] and "Change the app's secret" in " ".join(mails()[0]["lines"]), mails()[0])
        for k in range(20):
            redact("rc1-flood-%d" % k)
        eq(len(mails()), 1, "twenty more forgeries: not twenty more emails")
        eq(sum(1 for e in privacy._load_privacy_log()["events"] if e.get("detail", "").startswith("refused")), 1,
           "nor twenty more privacy records")
        # Cannot tell: owed, and tried again every hour.
        verdict["v"] = "unknown"
        eq(redact("rc1-b").status_code, 200)
        ok(os.path.isfile(salesdesk.CRM_PATH), "cannot tell: nothing erased")
        ok(isinstance(owed(), dict), "but it is owed, and kept where a restart cannot lose it")
        eq(run(privacy._shop_redact_retry(None)), "unknown", "the hourly attempt still cannot tell")
        eq(owed().get("tries"), 1, "and counts its tries")
        # Refused, but not yet for long enough: still owed.
        verdict["v"] = "gone"
        eq(run(privacy._shop_redact_retry(down(None))), "recent", "no outage on record: not an uninstall")
        eq(run(privacy._shop_redact_retry(down(30))), "recent", "thirty hours: not yet")
        ok(os.path.isfile(salesdesk.CRM_PATH), "the stores are all there")
        ok(any("holding" in a["subject"] for a in mails()), mails())
        # The app is reinstalled: whatever was owed is dropped.
        verdict["v"] = "installed"
        eq(run(privacy._shop_redact_retry(None)), "installed")
        eq(owed(), None, "an app still installed owes nothing")
        # A genuine request, two days on: owed, then the archive fails, then it erases.
        verdict["v"] = "gone"
        down(46)

        def no_disk(*a, **k):
            raise OSError("volume full")
        backup._build_backup_zip = no_disk
        spawned.clear()
        eq(redact("rc1-c").status_code, 200)
        ok(os.path.isfile(salesdesk.CRM_PATH), "no archive, no erasure")
        ok(isinstance(owed(), dict), "still owed")
        ok(any("not erased" in a["subject"] for a in mails()), mails())
        backup._build_backup_zip = saved[2]
        eq(run(privacy._shop_redact_retry(scheduler._load_watch().get("shopify_down"))), "erased",
           "the next hour, with the disk back, it erases")
        ok(not os.path.isfile(salesdesk.CRM_PATH), "a confirmed uninstall with an archive erases")
        eq(owed(), None, "and nothing is owed")
        ok(any(e.get("topic") == "shop/redact" and "erased" in e.get("detail", "")
               for e in privacy._load_privacy_log()["events"]), "and says so")
        eq(run(privacy._shop_redact_retry(None)), None, "nothing owed, nothing tried")
        # No way to ask Shopify is no confirmation; a broken watch record is
        # not an erasure either.
        shopify._install_checker = None
        ok(seed(), "reseeded")
        eq(redact("rc1-d").status_code, 200)
        ok(os.path.isfile(salesdesk.CRM_PATH) and isinstance(owed(), dict), "not erased, owed")
        shopify._install_checker = checker
        scheduler._save_watch(["not", "an", "object"])
        eq(redact("rc1-e").status_code, 200, "answered, not a crash")
        ok(os.path.isfile(salesdesk.CRM_PATH), "and not erased")
        # The watchdog tries it every hour, against its own record of the outage.
        src = copilot_source()
        ok('await privacy._shop_redact_retry(state.get("shopify_down"))' in src, "the hourly tick tries what is owed")
        ok("_ensure_scheduler(registry)" in src.split("async def privacy_webhook", 1)[1][:1500],
           "and a privacy request starts the scheduler, as an uninstalled app is never opened")
        # A request that cannot be recorded is sent back for Shopify to retry.
        privacy._shop_owed_set(None)
        scheduler._save_watch({})
        verdict["v"] = "unknown"
        good = open(privacy.PRIVACY_LOG_PATH, "rb").read()
        open(privacy.PRIVACY_LOG_PATH, "w").write("{not json")     # a log that no longer parses
        jsonstore._json_cache.clear()
        try:
            eq(redact("rc1-f").status_code, 503, "not recorded: Shopify is asked to send it again")
            ok("rc1-f" not in orderbook._webhook_seen, "and the retry is not taken for a duplicate")
        finally:
            open(privacy.PRIVACY_LOG_PATH, "wb").write(good)
            jsonstore._json_cache.clear()
            jsonstore._poisoned_stores.discard(privacy.PRIVACY_LOG_PATH)
    finally:
        shopify._install_checker, background.spawn, backup._build_backup_zip = saved
        orderbook._webhook_seen.clear()
        privacy._shop_redact_said.clear()
        privacy._shop_owed_set(None)
        scheduler._save_watch(saved_watch if isinstance(saved_watch, dict) else {})
        try:
            os.remove(salesdesk.CRM_PATH)
        except FileNotFoundError:
            pass
        jsonstore._forget_store(salesdesk.CRM_PATH)

@test
def t_the_install_check_calls_only_an_outright_refusal_gone():
    """What decides an erasure. Only Shopify refusing the app's credential
    (401, 403, 404, or the token grant refused) reads as uninstalled; a
    throttle, an outage, a timeout or a missing setting is unknown, and
    unknown erases nothing."""
    import httpx as _hx
    saved = (server._http, server._headers, server.token_manager._use_client_credentials,
             server.token_manager.force_refresh)
    answers = []

    class _Resp:
        def __init__(self, code, body):
            self.status_code, self._b = code, body

        def json(self):
            return self._b

    class _Client:
        async def post(self, url, headers=None, json=None, timeout=None):
            a = answers.pop(0)
            if isinstance(a, Exception):
                raise a
            return a
    hdr = {"raise": None}

    async def headers():
        if hdr["raise"]:
            raise hdr["raise"]
        return {}
    server._http, server._headers = (lambda: _Client()), headers
    server.token_manager._use_client_credentials = False
    try:
        def state(*seq):
            answers[:] = list(seq)
            return run_async(server.shopify_install_state(timeout=1.0))
        eq(state(_Resp(200, {"data": {"shop": {"id": "gid://shopify/Shop/1"}}})), "installed")
        eq(state(_Resp(200, {"data": {"shop": None}})), "unknown", "a 200 that names no shop proves nothing")
        for code in (401, 403, 404):
            eq(state(_Resp(code, {})), "gone", code)
        for code in (402, 423, 429, 500, 503):
            eq(state(_Resp(code, {})), "unknown", code)
        eq(state(_hx.ConnectError("down")), "unknown", "an outage")
        for msg, want in (("Token refresh failed (401). Check it.", "gone"),
                          ("Token refresh failed (400). Check it.", "gone"),
                          ("Token refresh failed (500). Check it.", "unknown"),
                          ("No valid token available. Set it.", "unknown")):
            hdr["raise"] = RuntimeError(msg)
            eq(state(), want, msg)
        hdr["raise"] = None
        # A token minted before the uninstall: one fresh grant decides it.
        server.token_manager._use_client_credentials = True

        async def refused():
            raise RuntimeError("Token refresh failed (401). Check it.")
        server.token_manager.force_refresh = refused
        eq(state(_Resp(401, {})), "gone", "the fresh grant is refused too")

        async def fine():
            return "tok"
        server.token_manager.force_refresh = fine
        eq(state(_Resp(401, {}), _Resp(200, {"data": {"shop": {"id": "x"}}})), "installed",
           "a stale token after a rotation is not an uninstall")
    finally:
        (server._http, server._headers, server.token_manager._use_client_credentials,
         server.token_manager.force_refresh) = saved


