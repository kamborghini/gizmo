# ---- Stock bridge (gizmo -> zeta) -------------------------------------------

def with_zeta(fn, send=None):
    """Run fn with the bridge configured and a fake transport standing in for
    the stock app. Returns the list of pushes zeta would have received."""
    sent = []
    async def fake_send(op, order_id, order_name, lines):
        if send:
            return await send(op, order_id, order_name, lines, sent)
        sent.append({"op": op, "order_id": str(order_id), "order_name": order_name, "lines": lines})
        return {"ok": True}
    saved = (stock_link.ZETA_URL, stock_link.ZETA_SYNC_TOKEN, stock_link.ZETA_SYNC_PATH, stock_link._zeta_send)
    stock_link.ZETA_URL = "https://zeta.test"
    stock_link.ZETA_SYNC_TOKEN = "tok"
    stock_link.ZETA_SYNC_PATH = SCRATCH + "/zeta_sync.json"
    stock_link._zeta_send = fake_send
    try:
        os.remove(stock_link.ZETA_SYNC_PATH)
    except FileNotFoundError:
        pass
    try:
        fn(sent)
        return sent
    finally:
        (stock_link.ZETA_URL, stock_link.ZETA_SYNC_TOKEN, stock_link.ZETA_SYNC_PATH, stock_link._zeta_send) = saved

@test
def t_marking_made_books_the_glass_at_the_stock_app():
    reset_dispatch(); reset_prod()
    def go(sent):
        r = mark_made(12345, True)
        eq(r.status_code, 200, r.text)
        eq(r.json().get("stock_note"), "", "no note when the push lands")
        eq(len(sent), 1, "one push per made")
        eq(sent[0]["op"], "book")
        eq(sent[0]["order_id"], "12345")
        ok(sent[0]["lines"], "the push carries resolved glass lines")
        r2 = mark_made(12345, False)
        eq(r2.status_code, 200, r2.text)
        eq(sent[1]["op"], "reverse", "un-making pushes the reversal")
        eq(stock_link._load_zeta_pending(), {}, "nothing left queued")
    with_zeta(go)

@test
def t_a_dead_stock_app_queues_the_booking_and_the_drain_retries_it():
    reset_dispatch(); reset_prod()
    state = {"up": False}
    async def send(op, order_id, order_name, lines, sent):
        if not state["up"]:
            raise RuntimeError("connection refused")
        sent.append({"op": op, "order_id": str(order_id)})
        return {"ok": True}
    def go(sent):
        r = mark_made(12345, True)
        eq(r.status_code, 200, "the workbench is never blocked by the bridge")
        ok("retrying" in r.json().get("stock_note", ""), r.json().get("stock_note"))
        pend = stock_link._load_zeta_pending()
        eq(pend.get("12345", {}).get("op"), "book", "the booking is parked")
        state["up"] = True
        run(stock_link._zeta_drain({}))
        eq(len(sent), 1, "the drain delivered it")
        eq(stock_link._load_zeta_pending(), {}, "and the queue emptied")
    with_zeta(go, send=send)

@test
def t_made_then_unmade_while_zeta_is_down_ends_as_a_reversal():
    # The queue records the LATEST intent: replaying a stale book after the
    # merchant already un-made the order would book glass that was never used.
    reset_dispatch(); reset_prod()
    state = {"up": False}
    async def send(op, order_id, order_name, lines, sent):
        if not state["up"]:
            raise RuntimeError("down")
        sent.append({"op": op})
        return {"ok": True}
    def go(sent):
        mark_made(12345, True)
        mark_made(12345, False)
        eq(stock_link._load_zeta_pending().get("12345", {}).get("op"), "reverse",
           "the queue holds the reversal, not the stale booking")
        state["up"] = True
        run(stock_link._zeta_drain({}))
        eq([s["op"] for s in sent], ["reverse"], "only the reversal was sent")
    with_zeta(go, send=send)

@test
def t_an_unconfigured_bridge_stays_silent():
    reset_dispatch(); reset_prod()
    saved = (stock_link.ZETA_URL, stock_link.ZETA_SYNC_TOKEN)
    stock_link.ZETA_URL, stock_link.ZETA_SYNC_TOKEN = "", ""
    try:
        r = mark_made(12345, True)
        eq(r.status_code, 200, r.text)
        eq(r.json().get("stock_note"), "", "no nagging when the bridge is off")
    finally:
        (stock_link.ZETA_URL, stock_link.ZETA_SYNC_TOKEN) = saved

@test
def t_a_stock_gobo_prints_its_name_not_a_check():
    """Order #104353 printed "2x CHECK No model specified on this item" twice,
    for Electric Smoke and Smoke & Mirrors - stock gobos whose fixture the
    Quote Engine had written as free text in Item Notes. A flagged row drops the
    item's name, so the bench could not even tell the two apart.

    A stock gobo is its own name. One that names its fixture still gets sized;
    a custom product with no spec still flags; an unknown type fails safe."""
    P = lambda **kv: [{"name": k, "value": v} for k, v in kv.items()]
    order = {"id": 1, "name": "#104353", "order_number": 104353, "note": "", "tags": "IP",
             "line_items": [
                 {"title": "Smoke & Mirrors Gobo", "quantity": 2, "sku": "NPC-SK-42", "product_id": 101,
                  "properties": P(**{"Item Notes": "Robe Forte"})},
                 {"title": "Wedding Gobo 10", "quantity": 1, "product_id": 102,
                  "properties": P(**{"Manufacturer": "Robe", "Model": "Forte"})},
                 {"title": "Custom Gobos", "quantity": 1, "product_id": 103, "properties": []},
                 {"title": "Mystery Gobo", "quantity": 1, "product_id": 104, "properties": []},
             ]}
    types = {101: "Gobo", 102: "Gobo", 103: "Custom Gobos"}          # 104 unknown
    shaped = production._shape_label_order(order, {}, cache=size_list._gobo_sizes(), types=types)
    stock, sized, custom, unknown = shaped["items"]
    eq(stock["review_reason"], "", "a stock gobo with no fixture is not a CHECK")
    eq(stock["artwork"], "Smoke & Mirrors Gobo", "it prints its own name")
    ok(stock["stock"] is True and stock["production_size"] == "", "marked stock, and unsized")
    ok(sized["stock"] is True and sized["production_size"] == "30.8",
       "a stock gobo that names its fixture still goes through the lookup")
    eq(custom["review_reason"], "No model specified on this item", "a custom item with no spec still flags")
    eq(unknown["review_reason"], "No model specified on this item", "an unknown product type keeps the CHECK")
    ok(unknown["stock"] is False, "and is not treated as stock")
    # Without types at all (an older caller) nothing changes.
    plain = production._shape_label_order(order, {}, cache=size_list._gobo_sizes())
    eq(plain["items"][0]["review_reason"], "No model specified on this item",
       "no type information is the old behaviour exactly")

    # The consumption lines carry it by name, and the stock app gets the
    # exact row shape it has always had.
    lines = stock_link._usage_lines({"items": [stock]})
    eq(len(lines), 1, "one line")
    eq(lines[0]["note"], "stock gobo: Smoke & Mirrors Gobo", "named, not 'no size resolved'")
    eq(lines[0]["stock"], "Smoke & Mirrors Gobo", "and flagged as stock for this app's screens")
    eq(set(stock_link._zeta_lines(lines)[0]), {"size", "family", "qty", "note"},
       "the stock app never sees a key it did not already accept")
    plain_lines = stock_link._usage_lines({"items": [{"quantity": 1, "glass_type": "Mono - Original",
                                                   "production_size": "26.5"}]})
    eq(stock_link._zeta_lines(plain_lines), plain_lines, "an ordinary line reaches the stock app unchanged")
    import inspect as _insp
    ok("_zeta_lines(_usage_lines(o))" in _insp.getsource(stock_link._zeta_push_locked),
       "and the book push actually goes through the contract, not around it")


@test
def t_a_gobo_sold_with_a_projector_is_cut_for_that_projector():
    """Order #104453 printed "1x CHECK No model specified on this item" twice:
    once for a "Single Colour Glass Original With Projector" gobo, which the
    Quote Engine sells with no fixture because its fixture is the projector on
    the same order, and once for the projector itself, which is not a gobo. A
    flagged row drops the item's name, so the bench could not tell them apart.

    Cameron's rulings (2026-10-02): a projector or accessory prints by name with
    no CHECK and uses no glass; a With Projector gobo is cut for the projector on
    its order, through the Projected Image row in the size list that names its
    wattage; two projector sizes, or none, is a CHECK that says so; a plain
    fixture-less custom gobo keeps its CHECK."""
    sheet = size_list._gobo_sizes()
    ok(any(r[0] == "projected image" for r in sheet.get("rows") or []),
       "the size list has its Projected Image rows")
    def gobo(**kw):
        li = {"title": "Custom Gobos", "quantity": 1, "product_id": 900, "properties": [],
              "sku": "SCGOWPIH", "variant_title": "Single Colour Glass Original With Projector (Quote) / IH",
              "name": "Custom Gobos - Single Colour Glass Original With Projector (Quote) / IH"}
        li.update(kw)
        return li
    def proj(title, sku, variant=None, qty=1, pid=901):
        return {"title": title, "quantity": qty, "product_id": pid, "properties": [], "sku": sku,
                "variant_title": variant, "name": title + (" - " + variant if variant else "")}
    def shape(*lines, types=None, email="buyer@acme.co.uk"):
        o = {"id": 1, "name": "#104453", "order_number": 104453, "note": "", "tags": "Unprocessed",
             "email": email, "line_items": list(lines)}
        return production._shape_label_order(o, {}, cache=size_list._gobo_sizes(), types=types)["items"]
    types = {900: "Custom Gobos", 901: "Projector", 902: "Projector", 903: "Projector"}

    # #104453 itself: a With Projector gobo and a 40 Watt weatherproof.
    g, p = shape(gobo(), proj("Projected Image 40 Watt LED Weatherproof Gobo Projector", "P102W"), types=types)
    eq((g["production_size"], g["review_reason"], g["glass_type"]), ("53.3", "", "Colour - Original"),
       "the gobo is cut for the 40 Watt on its order (40/80 Watt Range)")
    eq(g["size_note"], "For the 40 Watt projector on this order", "and the label says why that size")
    eq((p["review_reason"], p["production_size"], p["artwork"]),
       ("", "", "Projected Image 40 Watt LED Weatherproof Gobo Projector"),
       "the projector prints by name, with no CHECK and no size")
    ok(p["projector"] is True and p["not_gobo"] is True, "it is marked a projector, and not a gobo")
    eq(stock_link._usage_lines({"items": [g, p]}), [{"size": "53.3", "family": "Colour", "qty": 1}],
       "only the gobo uses glass: the projector is neither a blank nor a CHECK line")

    # #104196: the projector's variant says it comes with a rain hood.
    g, _p = shape(gobo(), proj("Projected Image 40 Watt LED Weatherproof Gobo Projector", "P102W-Unit+RH",
                               "40W with Rain Hood"), types=types)
    eq(g["production_size"], "53.3", "a projector sold with its rain hood is still a 40 Watt")
    # #103962: eight 20 Watt projectors and their gobos.
    g, _p = shape(gobo(quantity=8), proj("Projected Image 20 Watt LED Gobo Projector", "P220", qty=8), types=types)
    eq((g["production_size"], g["quantity"]), ("37.5", 8), "20 Watt Range")
    # #104156: four 200 Watt, an original and three copies.
    o2, c3, _p = shape(gobo(), gobo(quantity=3, sku="SCGCWPIH",
                                    variant_title="Single Colour Glass Copy With Projector (Quote) / IH"),
                       proj("Projected Image 200 Watt LED Weatherproof Gobo Projector", "P107W-200W+RH",
                            "200W with Rain Hood", qty=4), types=types)
    eq((o2["production_size"], c3["production_size"], c3["glass_type"]), ("66", "66", "Colour - Copy"),
       "150/200 Watt Range, originals and copies alike")
    # A 40 and an 80 on one order are both 53.3: nothing to ask.
    g, _a, _b = shape(gobo(), proj("Projected Image 40 Watt LED Weatherproof Gobo Projector", "P102W"),
                      proj("Projected Image 80 Watt LED Weatherproof Gobo Projector", "P103W", pid=902),
                      types=types)
    eq((g["production_size"], g["size_note"]), ("53.3", "For the 40 and 80 Watt projectors on this order"),
       "two wattages cut at the same size agree")

    # #104204: an 80 Watt and a 200 Watt, which are cut at different sizes.
    g, _a, _b = shape(gobo(), proj("Projected Image 200 Watt LED Weatherproof Gobo Projector", "P107W", "200W"),
                      proj("Projected Image 80 Watt LED Weatherproof Gobo Projector", "P103W", "80W", pid=902),
                      types=types)
    eq((g["production_size"], g["review_reason"]),
       ("", "Sold with a projector: this order has 80 and 200 Watt projectors, cut at different sizes"),
       "two sizes on one order is a person's decision, and the CHECK says which two")
    # #104375: the projector was on another order.
    (g,) = shape(gobo(properties=[{"name": "Item Notes", "value": "20 Watt Projector\nOrder #104349"}]), types=types)
    eq(g["review_reason"], "Sold with a projector, but no projector is on this order",
       "no projector on the order is a CHECK that says so")
    # A projector the size list has no row for.
    g, _p = shape(gobo(), proj("Projected Image 300 Watt LED Weatherproof Gobo Projector", "P300", pid=903),
                  types=types)
    eq(g["review_reason"], "No size list row for the 300 Watt projector on this order",
       "a wattage with no row is a CHECK naming it")
    # A refunded projector is not on the order any more.
    (g,) = shape(gobo(), dict(proj("Projected Image 40 Watt LED Weatherproof Gobo Projector", "P102W"),
                              current_quantity=0), types=types)
    eq(g["review_reason"], "Sold with a projector, but no projector is on this order",
       "a projector refunded off the order does not size its gobo")

    # Rain hoods and lenses name wattages but are not projectors.
    g, hood = shape(gobo(), proj("Weatherproof Rain Hood (40W & 80W)", "RH4080", pid=902), types=types)
    eq(g["review_reason"], "Sold with a projector, but no projector is on this order",
       "a rain hood's wattages do not size a gobo")
    eq((hood["review_reason"], hood["projector"], hood["artwork"]), ("", True, "Weatherproof Rain Hood (40W & 80W)"),
       "and the hood, typed Projector, prints by name")

    # Another maker's projector is not sized from our rows: the Evica GP10 is
    # 22.5 in the size list, not the 37.5 of our 10 Watt.
    g, ev = shape(gobo(), proj("Evica GP10 - 10 watt LED Gobo Projector", "P100"), types=types)
    eq((g["production_size"], g["review_reason"]), ("", "Sold with a projector by Evica: check its size"),
       "a projector by another maker is a CHECK naming the maker, never our size")
    eq((ev["review_reason"], ev["projector"]), ("", True), "and the Evica itself prints by name")
    # An upgrade changes which projector the customer gets: an 80 Watt
    # upgraded to a 200 Watt is cut at 66, not 53.3.
    g, _p, up = shape(gobo(), proj("Projected Image 80 Watt LED Weatherproof Gobo Projector", "P103W"),
                      proj("Projector Upgrade", "Projector Upgrade - 80 Watt to 200 Watt", "80 Watt to 200 Watt",
                           pid=902), types=types)
    eq((g["production_size"], g["review_reason"]),
       ("", "Sold with a projector, and this order upgrades one: check which size"),
       "an upgrade on the order is a person's decision")
    eq((up["artwork"], up["size_note"]), ("Projector Upgrade", "80 Watt to 200 Watt"),
       "and the upgrade prints by name, its variant under it")
    # A projector's variant goes under its name, where it can wrap; a bare
    # wattage repeating the title does not.
    _g, hooded = shape(gobo(), proj("Projected Image 40 Watt LED Weatherproof Gobo Projector", "P102W-Unit+RH",
                                    "40W with Rain Hood"), types=types)
    eq((hooded["artwork"], hooded["size_note"]),
       ("Projected Image 40 Watt LED Weatherproof Gobo Projector", "40W with Rain Hood"),
       "a projector sold with its hood says so under its name")
    _g, bare = shape(gobo(), proj("Projected Image 80 Watt LED Weatherproof Gobo Projector", "P103W", "80W"),
                     types=types)
    eq(bare["size_note"], "", "a variant that only repeats the wattage is left off")
    (holder,) = shape(proj("Gobo Holders", "Allholders-B Size Glass Gobo Holder", "B Size Glass Gobo Holder",
                           pid=902), types=types)
    eq((holder["artwork"], holder["size_note"], holder["review_reason"]),
       ("Gobo Holders", "B Size Glass Gobo Holder", ""), "a holder says which holder")

    # A plain custom gobo with no fixture keeps its CHECK (Cameron: only the
    # With Projector variant says it is for that projector).
    plain, _p = shape(gobo(sku="SCGO", variant_title="Single Colour Glass Original (Quote) / IH",
                           name="Custom Gobos - Single Colour Glass Original (Quote) / IH"),
                      proj("Projected Image 40 Watt LED Weatherproof Gobo Projector", "P102W"), types=types)
    eq(plain["review_reason"], "No model specified on this item", "a plain gobo keeps its CHECK")
    # A With Projector gobo that names its own fixture is sized by it.
    own, _p = shape(gobo(properties=[{"name": "Manufacturer", "value": "Robe"}, {"name": "Model", "value": "Forte"}]),
                    proj("Projected Image 40 Watt LED Weatherproof Gobo Projector", "P102W"), types=types)
    eq(own["production_size"], "30.8", "its own fixture wins over the projector")

    # The old quote machine: the projector typed Custom Gobos, named in its variant.
    g, p = shape(gobo(), {"title": "Outdoor Gobo Projectors", "quantity": 1, "product_id": 904, "properties": [],
                          "sku": None, "variant_title": "Projected Image 80 Watt LED Weatherproof Gobo Projector (Quote) / Rolls Royce",
                          "name": "Outdoor Gobo Projectors - Projected Image 80 Watt LED Weatherproof Gobo Projector (Quote) / Rolls Royce"},
                 types={900: "Custom Gobos", 904: "Custom Gobos"})
    eq((g["production_size"], p["review_reason"], p["projector"]), ("53.3", "", True),
       "a projector named in its variant counts, and prints by name")
    eq(p["size_note"], "Projected Image 80 Watt LED Weatherproof Gobo Projector (Quote) / Rolls Royce",
       "with the variant that says which projector, since its title does not")
    # #103894: that machine wrote the gobo's own fixture into a Note nothing
    # reads, and it named a B Size beside a 20 Watt. Not cut against it.
    noted, _p = shape(gobo(properties=[{"name": "Note", "value": "Projection Type: Front\nManufacturer: Standard\n"
                                                                 "Standard Models: B Size"}]),
                      proj("Projected Image 20 Watt LED Gobo Projector", "P220"), types=types)
    eq(noted["review_reason"], "No model specified on this item",
       "a gobo whose old Note names a fixture keeps its CHECK rather than be sized against it")
    # Without types (an older caller) a projector is still read from its name.
    g, p = shape(gobo(), proj("Projected Image 40 Watt LED Weatherproof Gobo Projector", "P102W"))
    eq((g["production_size"], p["review_reason"]), ("53.3", ""), "the name alone is enough")

    # A size for one customer applies through the projector's row too.
    cache = size_list._gobo_sizes()
    saved = list(cache["domain_rules"])
    try:
        cache["domain_rules"].append({"key": ("projected image", "40/80 watt range"), "domain": "acme.co.uk",
                                      "size": "52", "manufacturer": "Projected Image", "model": "40/80 Watt Range"})
        g, _p = shape(gobo(), proj("Projected Image 40 Watt LED Weatherproof Gobo Projector", "P102W"), types=types)
        eq((g["production_size"], g["size_note"]), ("52", "Size for this customer"),
           "a size ruled for this customer's domain wins, as for any gobo")
    finally:
        cache["domain_rules"][:] = saved


@test
def t_coverage_counts_gobos_sold_with_a_projector():
    """The coverage report counted a With Projector gobo as an accessory, so its
    CHECK never showed there. It is a gobo: sized when the projector on its order
    sizes it, flagged with the label's own reason when not, and only a missing
    size list row can be settled with a size rule."""
    gobo = {"title": "Custom Gobos", "quantity": 1, "product_id": 900, "properties": [], "sku": "SCGOWPIH",
            "variant_title": "Single Colour Glass Original With Projector (Quote) / IH"}
    p40 = {"title": "Projected Image 40 Watt LED Weatherproof Gobo Projector", "quantity": 1, "product_id": 901,
           "properties": [], "sku": "P102W", "variant_title": None}
    p300 = dict(p40, title="Projected Image 300 Watt LED Weatherproof Gobo Projector", sku="P300")
    orders = [{"id": 1, "name": "#104453", "line_items": [gobo, p40]},
              {"id": 2, "name": "#104375", "line_items": [gobo]},
              {"id": 3, "name": "#104999", "line_items": [gobo, p300]}]
    async def tj(registry, name, args):
        if name == "shopify_list_orders":
            return {"orders": orders}
        return await fake_tool_json(registry, name, args)
    shopify._tool_json = tj
    try:
        r = run_async(production.run_label_coverage({}, 10))
    finally:
        shopify._tool_json = fake_tool_json
    eq((r["gobo_items"], r["sized"], r["skipped_no_model"]), (3, 1, 2),
       "three gobos, one sized by its projector; the two projectors are accessories")
    by = {f["orders"][0]["name"]: f for f in r["flagged"]}
    eq((by["#104375"]["model"], by["#104375"]["reason"], by["#104375"].get("order_problem")),
       ("Sold with a projector", "Sold with a projector, but no projector is on this order", True),
       "an order with no projector is flagged as the order's problem, not the size list's")
    eq((by["#104999"]["manufacturer"], by["#104999"]["model"], by["#104999"].get("order_problem", False)),
       ("Projected Image", "300 Watt", False),
       "a wattage with no row is the size list's gap, settled with a size rule like any model")


@test
def t_the_push_lines_match_the_day_sheet_resolution():
    # One resolver feeds both, so the stock app and the printed day sheet can
    # never disagree about what a day's making consumed.
    shaped = {"items": [
        {"quantity": 2, "glass_type": "Mono - Original", "production_size": "26.5"},
        {"quantity": 1, "glass_type": "Mono - Copy", "production_size": "26.5"},
        {"quantity": 1, "glass_type": "Colour - Original", "production_size": "48"},
        {"quantity": 3, "glass_type": "", "production_size": "", "review_reason": "no model matched"},
    ]}
    lines = stock_link._usage_lines(shaped)
    eq(len(lines), 4, "every item becomes a line")
    eq(lines[0]["family"], "Mono", "Original and Copy share a family")
    ok("note" in lines[3] and lines[3]["note"] == "no model matched",
       "unresolvable glass is carried with its reason, never dropped")


@test
def t_the_drain_pushes_the_current_intent_not_its_snapshot():
    # While a retry is in flight the merchant can change their mind; the queue's
    # CURRENT op is the only one that may run, or a stale book would land after
    # a newer reverse and the stock app would hold glass for an un-made order.
    reset_dispatch(); reset_prod()
    def go(sent):
        pend = {"12345": {"op": "book", "at": "2026-08-17T10:00:00+00:00", "tries": 1}}
        stock_link._write_zeta_pending(pend)
        # The intent changes before the drain gets to it.
        pend["12345"]["op"] = "reverse"
        stock_link._write_zeta_pending(pend)
        run(stock_link._zeta_drain({}))
        eq([s["op"] for s in sent], ["reverse"], "the drain read the store, not a snapshot")
    with_zeta(go)

@test
def t_a_booking_that_cannot_even_be_queued_says_so_honestly():
    # A corrupt pending store means the retry promise would be a lie: the note
    # must tell the operator to act, never to relax.
    reset_dispatch(); reset_prod()
    async def send(op, order_id, order_name, lines, sent):
        raise RuntimeError("zeta down")
    def go(sent):
        with open(stock_link.ZETA_SYNC_PATH, "w") as fh:
            fh.write("{corrupt")
        stock_link._load_zeta_pending()      # poisons the store, as in production
        r = mark_made(12345, True)
        eq(r.status_code, 200, "the workbench still works")
        note = r.json().get("stock_note", "")
        ok("by hand" in note or "could not be saved" in note.lower() or "again later" in note,
           "the note admits the retry was not saved: " + note)
        ok("keep retrying" not in note, "and never promises a retry that will not happen")
    try:
        with_zeta(go, send=send)
    finally:
        jsonstore._poisoned_stores.discard(SCRATCH + "/zeta_sync.json")


