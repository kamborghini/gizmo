# ---------------------------------------------------------------------------
# The 2026-09-22 bug audit, the P3s.
# ---------------------------------------------------------------------------
import copy as _copy
import xml.etree.ElementTree as _ET

def _ship_cfg():
    post("/api/shipping/config", {"op": "set", "meter_number": "METER-9999", "key": "K", "password": "P",
                                   "origin": {"street": "1 Mill St", "postcode": "LS1 1AA", "country": "GB",
                                              "city": "Leeds", "company": "PI", "phone": "0113 555 1111",
                                              "email": "shop@projectedimage.com"}})


@test
def t_a_redact_a_store_refused_is_said_and_retried():
    """A14. A customers/redact whose CRM write failed was logged as erased and
    never tried again; an unreadable CRM was logged as "erased 0"."""
    def go():
        ensure_auth(); crm_wipe()
        d = salesdesk._load_crm()
        d["persons"]["p1"] = {"id": "p1", "name": "Kim Lee", "emails": ["kim@x.com"]}
        salesdesk._write_crm(d)
        good = open(salesdesk.CRM_PATH).read()
        with open(salesdesk.CRM_PATH, "w") as fh:
            fh.write("{ broken")
        jsonstore._json_cache.pop(salesdesk.CRM_PATH, None)
        reset_dispatch()
        desk._record_dispatch(4242, {"email": "kim@x.com", "tracking_number": "T-42"})
        try:
            out = privacy._redact_customer("kim@x.com", "9")
            ok("the CRM" in out["failed"], out)
            asked = desk._load_dispatch()["4242"].get("redacted_request_at")
            ok(asked, "the kept booking records when the request came in")
            last = privacy._load_privacy_log()["events"][-1]["detail"]
            ok("NOT YET ERASED from the CRM" in last, "the record says what was not done: " + last)
            ok(any(p["email"] == "kim@x.com" for p in privacy._load_privacy_log().get("pending") or []),
               "and it is owed")
        finally:
            jsonstore._poisoned_stores.discard(salesdesk.CRM_PATH)
            with open(salesdesk.CRM_PATH, "w") as fh:
                fh.write(good)
            jsonstore._json_cache.pop(salesdesk.CRM_PATH, None)
        # The hourly tick is what runs it (the round-4 review found the test
        # called the retry directly, so dropping it from the tick passed).
        ran = []
        async def probe(registry, name, args):
            return {"name": "Shop"} if name == "shopify_get_shop" else {}
        async def noop(*a, **k):
            return None
        async def skip(*a, **k):
            return {"error": "skip"}
        saved = (shopify._tool_json, scheduler._send_alert_email, copilot._zeta_drain, copilot._zeta_configured,
                 fileserver._files_tick, production.run_label_coverage, shopify._webhook_ensurer,
                 scheduler._watch_last_tick, privacy._redact_retry_pending)
        shopify._tool_json, scheduler._send_alert_email, copilot._zeta_drain = probe, noop, noop
        copilot._zeta_configured, fileserver._files_tick = (lambda: False), (lambda: None)
        production.run_label_coverage, shopify._webhook_ensurer, scheduler._watch_last_tick = skip, None, 0.0
        privacy._redact_retry_pending = lambda: ran.append(1) or saved[-1]()
        try:
            run_async(scheduler._watchdog_tick({}))
        finally:
            (shopify._tool_json, scheduler._send_alert_email, copilot._zeta_drain, copilot._zeta_configured,
             fileserver._files_tick, production.run_label_coverage, shopify._webhook_ensurer,
             scheduler._watch_last_tick, privacy._redact_retry_pending) = saved
        eq(ran, [1], "the hourly tick runs the retry")
        eq(desk._load_dispatch()["4242"].get("redacted_request_at"), asked,
           "and the retry leaves that time alone")
        reset_dispatch()
        ok(not any(p.get("id") == "p1" for p in salesdesk._load_crm()["persons"].values()), "and she is gone")
        eq(privacy._load_privacy_log().get("pending"), [], "nothing is owed any more")
    with_mail(go)


@test
def t_a_redact_that_stops_part_way_through_the_crm_leaves_nothing_half_made_in_memory():
    """An erasure changes the CRM in memory (the tombstone, the sweep, the
    leads) and writes it last. A step that raised before the write left the
    half-made erasure in the cached store: it was served as saved, and the
    next unrelated CRM save wrote it to disk."""
    def go():
        ensure_auth(); crm_wipe()
        addr = "kim@x.com"
        d = salesdesk._load_crm()
        d["persons"]["p1"] = {"id": "p1", "name": "Kim Lee", "emails": [addr]}
        d["leads"]["l1"] = {"id": "l1", "title": "Kim Lee lead", "person_id": "p1"}
        salesdesk._write_crm(d)
        def stops(*a, **k):
            raise RuntimeError("the erasure stopped part way")
        saved = privacy._erase_remember          # the last step before the write
        privacy._erase_remember = stops
        try:
            out = privacy._redact_customer(addr, "9")
        finally:
            privacy._erase_remember = saved
        eq(out["failed"], ["the CRM"], "the CRM is said to have failed")
        d = salesdesk._load_crm()
        ok("p1" in d["persons"] and "l1" in d["leads"],
           "the CRM read next is the one on disk: " + str(sorted(d["persons"])) + str(sorted(d["leads"])))
        eq(post("/api/crm/contact", {"op": "org_add", "name": "Typed by hand"}).status_code, 200)
        on_disk = json.load(open(salesdesk.CRM_PATH))["crm"]
        ok("p1" in on_disk["persons"] and "l1" in on_disk["leads"],
           "and the next save does not write half an erasure")
        eq(privacy._redact_customer(addr, "9", retry=True)["failed"], [], "the hourly retry finishes it")
        d = salesdesk._load_crm()
        ok("p1" not in d["persons"] and "l1" not in d["leads"], "and she is gone")
    with_mail(go)


@test
def t_a_redact_that_stops_part_way_through_the_mailbox_leaves_nothing_half_made_in_memory():
    """The same for the mailbox: their threads came off the board in memory,
    and a scrub that raised before the write left the board showing an
    erasure that was never saved, until the mail loop's next save wrote it."""
    def go():
        ensure_auth(); crm_wipe()
        addr = "kim@x.com"
        _seed_thread("k1", frm=("Kim Lee", addr))
        _seed_thread("b1", frm=("Bob", "bob@venue.com"))
        mail._write_mail(mail._load_mail())
        def stops(*a, **k):
            raise RuntimeError("the scrub stopped part way")
        saved = mail._mail_erased_rx          # runs after their threads are taken off
        mail._mail_erased_rx = stops
        try:
            out = privacy._redact_customer(addr, "9")
        finally:
            mail._mail_erased_rx = saved
        eq(out["failed"], ["the mailbox"], "the mailbox is said to have failed")
        ok("k1" in mail._load_mail()["threads"], "the board read next is the one on disk")
        eq(privacy._redact_customer(addr, "9", retry=True)["failed"], [], "the hourly retry finishes it")
        ok("k1" not in mail._load_mail()["threads"], "and her thread is gone")
    with_mail(go)


@test
def t_a_redact_that_stops_part_way_through_the_bookings_leaves_nothing_half_made_in_memory():
    """And the bookings kept by law: each is stamped in memory with when the
    request came in, and written last. A record the stamping could not read
    stopped it part way, and the bookings already stamped stayed stamped in
    the cached store, for the next booking saved to write."""
    def go():
        ensure_auth(); crm_wipe(); reset_dispatch()
        addr = "kim@x.com"
        with open(desk.DISPATCH_STATE_PATH, "w", encoding="utf-8") as fh:
            json.dump({"orders": {"4242": {"email": addr, "tracking_number": "T-42"},
                                  "4243": "not a booking"}}, fh)
        try:
            privacy._redact_customer(addr, "9")
            ok(not desk._load_dispatch()["4242"].get("redacted_request_at"),
               "the bookings read next are the ones on disk")
        finally:
            reset_dispatch()
    with_mail(go)


def _open_order(i, tags=""):
    return {"id": i, "name": "#%d" % i, "order_number": i, "created_at": "2026-09-%02dT10:00:00Z" % (1 + i % 20),
            "tags": tags, "cancelled_at": None, "fulfillment_status": None, "financial_status": "paid",
            "customer": {"first_name": "A", "last_name": "B"}, "shipping_address": {"company": "Venue"},
            "line_items": [{"title": "Custom Gobo", "quantity": 1,
                            "properties": [{"name": "Manufacturer", "value": "ETC"},
                                           {"name": "Model", "value": "Source Four"}]}]}


@test
def t_the_missing_check_reads_every_open_order():
    """A15. It read one page of 100 open orders; the oldest, most at risk of
    never reaching the bench, were the ones past it."""
    orders = [_open_order(i, tags="IP") for i in range(2, 262)] + [_open_order(1)]
    async def tools(registry, name, args):
        if name == "shopify_list_orders":
            sid = int(args.get("since_id") or 0)
            rows = sorted((o for o in orders if o["id"] > sid), key=lambda o: o["id"])
            return {"orders": [dict(o) for o in rows[:int(args.get("limit") or 50)]]}
        return {}
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        res = run_async(production.run_missing_production({}))
        eq(res["checked"], 261, "every open order is read")
        eq([m["name"] for m in res["missing"]], ["#1"], "and the oldest untagged one is found")
        eq(res["truncated"], False)
    finally:
        shopify._tool_json = saved


@test
def t_a_projector_wattage_is_settled_by_any_size_rule():
    """The review of the #104453 change: the size check offers "Projected Image
    | 300 Watt" for a projector the size list has no row for, and only one of
    its three answers cleared the CHECK. A size, an alias to a row, and a size
    for one customer must each settle it; and a row named for the wattage
    itself wins over a range that includes it, so ruling "40 Watt" decides."""
    def order(watts, email="buyer@acme.co.uk"):
        return {"id": 1, "name": "#104999", "order_number": 104999, "note": "", "email": email, "line_items": [
            {"title": "Custom Gobos", "quantity": 1, "product_id": 900, "properties": [], "sku": "SCGOWPIH",
             "variant_title": "Single Colour Glass Original With Projector (Quote) / IH"},
            {"title": "Projected Image %d Watt LED Weatherproof Gobo Projector" % watts, "quantity": 1,
             "product_id": 901, "properties": [], "sku": "P%d" % watts}]}
    def gobo_of(o):
        return production._shape_label_order(o, {}, cache=size_list._gobo_sizes(),
                                          types={900: "Custom Gobos", 901: "Projector"})["items"][0]
    paths = {k: size_list.GOBO_RULE_FILES[k][1] for k in ("override", "alias")}
    seeds = {k: open(size_list.GOBO_RULE_FILES[k][0], encoding="utf-8").read() for k in paths}
    saved = {k: (open(p_, encoding="utf-8").read() if os.path.exists(p_) else None) for k, p_ in paths.items()}
    def put(kind, line):
        os.makedirs(os.path.dirname(paths[kind]), exist_ok=True)
        with open(paths[kind], "w", encoding="utf-8") as fh:
            fh.write(seeds[kind].rstrip("\n") + "\n" + line + "\n")
        os.utime(paths[kind], (time.time() + 5, time.time() + 5))
    def clear():
        for kind, p_ in paths.items():
            if os.path.exists(p_):
                os.remove(p_)
    try:
        clear()
        eq(gobo_of(order(300))["review_reason"], "No size list row for the 300 Watt projector on this order")
        put("override", "Projected Image,300 Watt,,72")
        g = gobo_of(order(300))
        eq((g["production_size"], g["review_reason"]), ("72", ""), "a size settles it")
        clear()
        put("alias", "Projected Image,300 Watt,150/200 Watt Range")
        g = gobo_of(order(300))
        eq((g["production_size"], g["review_reason"]), ("66", ""), "so does pointing it at a row")
        clear()
        put("override", "Projected Image,300 Watt,acme.co.uk,70")
        g = gobo_of(order(300))
        eq((g["production_size"], g["size_note"]), ("70", "Size for this customer"),
           "and a size for one customer settles it for that customer")
        eq(gobo_of(order(300, email="someone@else.test"))["review_reason"],
           "No size list row for the 300 Watt projector on this order", "but for nobody else")
        clear()
        put("override", "Projected Image,40 Watt,,50")
        g = gobo_of(order(40))
        eq((g["production_size"], g["review_reason"]), ("50", ""),
           "a rule for the wattage itself wins over the range that includes it")
        eq(gobo_of(order(80))["production_size"], "53.3", "and leaves the rest of the range alone")
        # Two rows naming the same wattage at different sizes is the size
        # list's own clash: the size check offers a rule on the wattage.
        row = lambda model, size: ("projected image", tuple(size_list._loose_key(model).split()),
                                   {"manufacturer": "Projected Image", "model": model,
                                    "production_size": size, "review": ""})
        clash = {"rows": [row("40/80 Watt Range", "53.3"), row("40 Watt Range Weatherproof", "50")],
                 "domain_rules": [], "excludes": set()}
        eq(production._projector_size(order(40), clash),
           {"reason": "The size list gives the 40 Watt projector two sizes", "fix": ("Projected Image", "40 Watt")},
           "a clash in the size list carries the rule that settles it")
    finally:
        clear()
        for kind, text in saved.items():
            if text is not None:
                with open(paths[kind], "w", encoding="utf-8") as fh:
                    fh.write(text)


@test
def t_the_missing_check_counts_a_gobo_sold_with_a_projector():
    """An order whose only gobo is a With Projector one (#104375's shape) has a
    gobo on it, so a paid order of that shape that never reached the bench is
    reported like any other."""
    o = _open_order(7)
    o["line_items"] = [{"title": "Custom Gobos", "quantity": 1, "properties": [], "sku": "SCGOWPIH",
                        "variant_title": "Single Colour Glass Original With Projector (Quote) / IH"}]
    async def tools(registry, name, args):
        if name == "shopify_list_orders":
            return {"orders": [dict(o)] if not int(args.get("since_id") or 0) else []}
        return {}
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        res = run_async(production.run_missing_production({}))
        eq([m["name"] for m in res["missing"]], ["#7"], "it is reported as missing from production")
    finally:
        shopify._tool_json = saved


@test
def t_a_stock_sheet_with_unread_orders_is_not_sent_as_final():
    """A16. The day's sheet went as FINAL figures for orders the server could
    not read, un-booking the glass their automatic bookings recorded."""
    from zoneinfo import ZoneInfo
    ensure_auth(); reset_dispatch(); reset_prod()
    production._mark_made(12345, True); production._mark_made(777, True)
    async def tools(registry, name, args):
        if name == "shopify_get_order":
            return {"_failed": True} if int(args["order_id"]) == 777 else _copy.deepcopy(ORDER)
        if name == "shopify_get_shop":
            return dict(SHOP)
        return {}
    sent = []
    async def sheet(payload):
        sent.append(payload); return {"ok": True}
    saved = (shopify._tool_json, copilot._zeta_send_sheet, copilot.ZETA_URL, copilot.ZETA_SYNC_TOKEN)
    shopify._tool_json, copilot._zeta_send_sheet = tools, sheet
    copilot.ZETA_URL, copilot.ZETA_SYNC_TOKEN = "https://zeta.test", "tok"
    try:
        today = datetime.now(ZoneInfo("Europe/London")).date().isoformat()
        r = post("/api/stock-usage/send", {"date": today, "lines": [
            {"family": "Mono", "size": "37.5", "estimated": 0, "final": 0}]})
        eq(r.status_code, 409, r.text)
        eq(sent, [], "nothing reaches the stock app")
        ok("777" in r.json()["error"], "and the order that could not be read is named: " + r.text)
        # An order Shopify no longer has (found by the round-4 review) held
        # the day's sheet for good: a deleted order is not "read just now".
        # It is left out, its booking stands, and the send says so. Both
        # shapes: the real tool's non-JSON text and an error field.
        for gone in ({"_failed": True, "_said": "Resource not found \u2014 double-check the ID."},
                     {"error": "Shopify API 404: Not Found"}):
            async def tools(registry, name, args, gone=gone):
                if name == "shopify_get_order":
                    return dict(gone) if int(args["order_id"]) == 777 else _copy.deepcopy(ORDER)
                return dict(SHOP) if name == "shopify_get_shop" else {}
            shopify._tool_json = tools
            sent.clear()
            r = post("/api/stock-usage/send", {"date": today, "lines": [
                {"family": "Mono", "size": "37.5", "estimated": 0, "final": 0}]})
            eq(r.status_code, 200, r.text)
            eq(sent[0]["order_ids"], ["12345"], "the gone order is not in the FINAL sheet")
            ok("777" in r.json()["note"] and "stays booked" in r.json()["note"], r.text)
    finally:
        shopify._tool_json, copilot._zeta_send_sheet, copilot.ZETA_URL, copilot.ZETA_SYNC_TOKEN = saved
        reset_prod()


@test
def t_the_erased_address_patterns_are_built_once_each():
    """Found by the round-4 review: the one-entry cache made the header and
    body patterns evict each other, so every synced thread rebuilt both."""
    gone = {"jo@x.com", "kim@y.org"}
    mail._erased_rx_cache.clear()
    body, head = mail._mail_erased_rx(gone), mail._mail_erased_rx(gone, header=True)
    # Counted, not compared by identity: re keeps its own cache of compiled
    # patterns, so a rebuilt one can be the very same object.
    eq(sorted(k[1] for k in mail._erased_rx_cache), [False, True], "each form is kept")
    eq(head.sub("[erased]", "Jo Smith <jo@x.com>, ann@z.com"), "[erased], ann@z.com")
    eq(body.sub("[erased]", "write to jo@x.com today"), "write to [erased] today")
    ok(mail._mail_erased_rx(gone | {"new@x.com"}) is not body, "and a longer list is a new pattern")


@test
def t_a_tool_read_keeps_what_shopify_said():
    """What the tool answered is kept on a failed read, so a caller can tell
    an order Shopify no longer has from one it did not answer for."""
    async def _aio_ret(v):
        return v
    reg = {"t": (lambda m: _aio_ret("Resource not found \u2014 double-check the ID."), lambda **k: None),
           "u": (lambda m: _aio_ret("Request timed out \u2014 try again."), lambda **k: None)}
    a = asyncio.run(REAL_TOOL_JSON(reg, "t", {}))
    b = asyncio.run(REAL_TOOL_JSON(reg, "u", {}))
    ok(not shopify._ok(a) and shopify._shopify_gone(a), a)
    ok(not shopify._ok(b) and not shopify._shopify_gone(b), b)


@test
def t_a_channel_islands_postcode_ships_as_its_own_country():
    """A17. An order to 'United Kingdom' with a Jersey or Guernsey postcode was
    quoted domestic and booked with no customs declaration."""
    def to(zip_, cc="GB"):
        o = _copy.deepcopy(ORDER); o["shipping_address"].update({"zip": zip_, "country_code": cc})
        return orderbook._ship_to(o)["country"]
    eq((to("JE2 3AB"), to("GY1 1AA"), to("IM1 1AA"), to("M1 2AB"), to("JE2 3AB", "JE")),
       ("JE", "GG", "GB", "GB", "JE"), "Jersey and Guernsey leave the UK customs area; the Isle of Man does not")


@test
def t_old_shifts_are_archived_and_still_on_the_payroll_report():
    """A18. The shift log kept the newest 2,000 and dropped the rest, so a
    report for an older period came back short without a word."""
    def go():
        ensure_auth()
        saved = (work.WORK_KEEP, work.WORK_ARCHIVE_PATH)
        work.WORK_KEEP = 3
        work.WORK_ARCHIVE_PATH = SCRATCH + "/worklog_archive_a18.jsonl"
        try:
            try:
                os.remove(work.WORK_ARCHIVE_PATH)
            except FileNotFoundError:
                pass
            w = work._load_work()
            w["sessions"] = []
            for i in range(5):
                w["sessions"].append({"id": "w%d" % i, "uid": "u9", "start": "2026-0%d-01T09:00:00+00:00" % (i + 1),
                                      "end": "2026-0%d-01T12:00:00+00:00" % (i + 1), "secs": 10800})
                work._write_work(w)
            eq(len(work._load_work()["sessions"]), 3, "the live log keeps its cap")
            eq(len(work._work_archived()), 2, "what left it is archived")
            r = post("/api/work/report", {"from": "2026-01-01", "to": "2026-12-31"})
            eq(r.json()["count"], 5, "and the report still has every shift")
        finally:
            work.WORK_KEEP, work.WORK_ARCHIVE_PATH = saved
            w = work._load_work(); w["sessions"] = []; work._write_work(w)
    with_accounts(go)


@test
def t_two_uploads_of_one_name_leave_one_active_file():
    """A19. Two uploads of one name whose reservations overlapped both became
    active; Finder could reach only one of them."""
    def go(fake):
        ensure_auth()
        a = post("/api/files/upload-url", {"name": "logo.png", "size": 1000, "type": "image/png", "folder_id": ""}).json()
        b = post("/api/files/upload-url", {"name": "logo.png", "size": 2000, "type": "image/png", "folder_id": ""}).json()
        d = fileserver._load_files()
        fake.objects[d["files"][a["id"]]["r2_key"]] = 1000
        fake.objects[d["files"][b["id"]]["r2_key"]] = 2000
        eq(post("/api/files/complete", {"id": a["id"]}).status_code, 200)
        eq(post("/api/files/complete", {"id": b["id"]}).status_code, 200)
        active = [k for k, v in fileserver._load_files()["files"].items()
                  if v.get("status") == "active" and v.get("name") == "logo.png"]
        eq(active, [b["id"]], "the later one is the file; the earlier is in the bin")
    with_files(go)


@test
def t_a_booking_whose_answer_was_lost_is_not_booked_again_blind():
    """A21. A booking was recorded last, after the label download, and nothing
    marked one in flight: a restart in that window, or a lost answer followed
    by a reload, left the next Book free to pay for a second label."""
    import worldoptions as _wo
    ensure_auth(); _ship_cfg(); reset_dispatch(); reset_prod()
    calls = []
    async def soap(service, action, inner, retryable=True):
        if service == "ShipmentService":
            calls.append(1)
            if len(calls) == 1:
                e = _wo.WorldOptionsError("World Options error (HTTP 504)."); e.ambiguous = True
                raise e
            return _ET.fromstring(BOOK_XML)
        return _ET.fromstring(RATE_XML)
    seen = []
    async def links(labels):
        seen.append((desk._load_dispatch().get("12345") or {}).get("tracking_number"))
        return labels
    saved = (_wo._soap_call, desk._resolve_label_links)
    _wo._soap_call, desk._resolve_label_links = soap, links
    try:
        r1 = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX}).json()
        ok("MAY still" in r1.get("error", ""), r1)
        r2 = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX}).json()
        ok("outcome was never recorded" in r2.get("error", ""), "the next Book is stopped: " + str(r2))
        eq(len(calls), 1, "and nothing was sent")
        r3 = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX,
                                         "confirm_unknown": True}).json()
        ok(r3.get("ok"), "once someone has checked, it books: " + str(r3)[:200])
        ok(seen and seen[0], "and the tracking number was on record before the label was fetched")
    finally:
        _wo._soap_call, desk._resolve_label_links = saved
        reset_dispatch()


@test
def t_a_relayed_gateway_timeout_is_never_booked_twice_by_itself():
    """A22. A FAILED reply relaying "(504) Gateway Timeout" matched the
    transient list and was re-sent, though a timeout is the one outcome a
    retry must never gamble on."""
    import worldoptions as _wo
    ensure_auth(); _ship_cfg(); reset_dispatch(); reset_prod()
    failed = ("<Envelope><Body><DoShipmentResponse><DoShipmentResult>"
              "<Message>The remote server returned an error: (504) Gateway Timeout.</Message>"
              "<NotificationtType>FAILED</NotificationtType></DoShipmentResult></DoShipmentResponse></Body></Envelope>")
    sent = []
    async def soap(service, action, inner, retryable=True):
        if service == "ShipmentService":
            sent.append(1)
            return _ET.fromstring(failed if len(sent) == 1 else BOOK_XML)
        return _ET.fromstring(RATE_XML)
    saved = (_wo._soap_call, desk.WO_RETRY_WAIT_SECS)
    _wo._soap_call, desk.WO_RETRY_WAIT_SECS = soap, 0
    try:
        r1 = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX}).json()
        eq(len(sent), 1, "sent once, not retried")
        # And not read as a refusal either (found by the round-4 review): the
        # guard was cleared, the page's unknown-outcome rule did not match, Book
        # re-armed, and the next press booked and charged a second time.
        ok("MAY still have been booked" in r1.get("error", ""), r1)
        rx = re.search(r"const BOOKING_UNKNOWN = /(.*?)/i;", pagesource.join(HERE)).group(1)
        ok(re.search(rx, r1["error"], re.I), "the page holds Book on it")
        ok(desk._intent_open(12345), "the guard keeps its record")
        r2 = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX}).json()
        ok(r2.get("unknown_booking") and len(sent) == 1, "the next press is stopped, not sent: %r" % r2)
    finally:
        _wo._soap_call, desk.WO_RETRY_WAIT_SECS = saved
        reset_dispatch()


@test
def t_an_unknown_fulfilment_or_terms_outcome_is_not_called_a_failure():
    """A23. When the answer to a fulfilment or a Net-30 write was lost and the
    read that settles it also failed, the app reported a definite failure and
    reverted the tags of an order that may have shipped."""
    import server as _srv, httpx as _hx
    ensure_auth(); reset_dispatch(); reset_prod(); TAG_WRITES.clear()
    desk._record_dispatch(12345, {"tracking_number": "T-5", "carrier_name": "UPS", "notify": True,
                                     "dispatched_at": "2026-09-22T09:00:00Z"})
    state = {"fo": 0}
    async def req(method, path, params=None, body=None, **kw):
        if method == "GET" and path.endswith("fulfillment_orders.json"):
            state["fo"] += 1
            if state["fo"] == 1:
                return {"fulfillment_orders": [{"id": 9, "status": "open", "line_items": [{"id": 1, "fulfillable_quantity": 1}]}]}
            raise _hx.ConnectTimeout("")
        if method == "POST" and path == "fulfillments.json":
            raise _hx.ReadTimeout("")
        raise AssertionError(method + path)
    # Shopify's tags as last written, so a revert has something to undo and
    # shows up as a write (with fixed tags it was a no-op the test could not see).
    async def tools(registry, name, args):
        if name == "shopify_get_order":
            o = dict(ORDER)
            if TAG_WRITES:
                o["tags"] = TAG_WRITES[-1][1]
            return o
        return await fake_tool_json(registry, name, args)
    saved = (_srv._request, shopify._fulfillment_writer, shopify._tool_json)
    _srv._request, shopify._fulfillment_writer, shopify._tool_json = req, _srv.create_order_fulfillment, tools
    try:
        r = mark_made().json()
        eq(r["fulfilled"], False)
        ok("may already be fulfilled" in (r.get("ship_note") or ""), r.get("ship_note"))
        ok(TAG_WRITES and desk.DISPATCHED_TAG.lower() in TAG_WRITES[0][1].lower(), TAG_WRITES)
        eq([t for _o, t in TAG_WRITES[1:]], [],
           "and the tags were not put back as if it had not shipped")
    finally:
        _srv._request, shopify._fulfillment_writer, shopify._tool_json = saved
        reset_dispatch(); reset_prod()
    # Net-30: the create's answer lost, and the check afterwards fails too.
    calls = {"n": 0}
    async def gq(method, path, params=None, body=None, **kw):
        q = (body or {}).get("query", "")
        calls["n"] += 1
        if "paymentTermsTemplates" in q:
            return {"data": {"paymentTermsTemplates": [{"id": "T30", "name": "Net 30", "paymentTermsType": "NET", "dueInDays": 30}]}}
        if "paymentTermsCreate" in q:
            raise _hx.ReadTimeout("")
        if "createdAt" in q:
            return {"data": {"order": {"id": "gid://shopify/Order/1", "createdAt": "2026-09-20T10:00:00Z", "paymentTerms": None}}}
        raise _hx.ConnectTimeout("")
    saved2 = (_srv._request, dict(_srv._net30_template))
    _srv._request = gq
    _srv._net30_template["id"] = ""
    try:
        out = run_async(_srv.set_order_payment_terms_net30(1))
        eq(out.get("reason"), "unknown", "not 'the order is not on 30-day terms': " + str(out))
    finally:
        _srv._request = saved2[0]
        _srv._net30_template.clear(); _srv._net30_template.update(saved2[1])
    # And its one caller does not turn "not known" back into "could not be
    # added" (found by the round-4 review).
    saved3 = (shopify._payment_terms_writer, ORDER.get("tags"))
    async def unknown_writer(oid):
        return {"ok": False, "reason": "unknown", "detail": "it is not known whether the order is on 30-day terms."}
    shopify._payment_terms_writer, ORDER["tags"] = unknown_writer, orderbook.PO_UNPAID_TAG
    try:
        v = run_async(production._net30_on_release({}, 12345))
        ok(v.get("unknown") and "could not be added" not in v["note"] and "not known" in v["note"], v)
    finally:
        shopify._payment_terms_writer, ORDER["tags"] = saved3
        reset_prod()


@test
def t_the_log_drain_counts_a_refused_batch_and_ships_the_traceback():
    """A24. A sink that answered 401 (a rotated token) was treated as having
    taken the batch, and logger.exception lines arrived without their cause."""
    import logdrain as _ld, httpx as _hx, logging as _lg
    saved_post = _hx.post
    _hx.post = lambda url, **kw: _hx.Response(401, request=_hx.Request("POST", url))
    try:
        raised = False
        try:
            _ld._default_sender("https://sink.test", "t")([{"kind": "audit"}])
        except Exception:
            raised = True
        ok(raised, "a refused batch is an error the drain counts as dropped")
    finally:
        _hx.post = saved_post
    got = []
    saved_put = _ld._put
    _ld._put = got.append
    try:
        try:
            raise ValueError("the real cause")
        except ValueError:
            import sys as _sys
            rec = _lg.LogRecord("x", _lg.ERROR, __file__, 1, "booking failed", None, _sys.exc_info())
        _ld._Handler().emit(rec)
        ok(got and "the real cause" in got[0].get("exc", ""), "the traceback travels with it: " + str(got)[:200])
    finally:
        _ld._put = saved_put


@test
def t_a_malformed_number_setting_falls_back_instead_of_stopping_the_app():
    """A25. SESSION_HOURS="" or MAIL_LOOP_SECS="60s" crashed boot at import,
    and the log blamed the chat."""
    import subprocess
    eq(copilot._env_num(int, "60s", "60", "MAIL_LOOP_SECS"), 60)
    eq(copilot._env_num(float, "", "24", "SESSION_HOURS"), 24.0)
    r = subprocess.run([sys.executable, "-c", "import copilot; from gizmo import mail, team; print(team.SESSION_HOURS, mail.MAIL_LOOP_SECS)"],
                       env={**os.environ, "SESSION_HOURS": "", "MAIL_LOOP_SECS": "60s"},
                       cwd=HERE, capture_output=True, text=True)
    eq(r.returncode, 0, r.stderr[-400:])
    ok(r.stdout.strip().endswith("24.0 60"), r.stdout)


@test
def t_a_lost_answer_to_an_address_edit_is_settled_by_reading_the_order():
    """A26. A lost answer was reported as "Shopify refused the change"; the
    retry then found nothing to change, so the booked label's new address was
    never marked and Mark made emailed tracking for the old one."""
    import server as _srv, httpx as _hx
    ensure_auth(); reset_dispatch(); reset_prod()
    desk._record_dispatch(12345, {"tracking_number": "T-9", "carrier_name": "DPD",
                                     "dispatched_at": "2026-09-22T09:00:00Z"})
    live = _copy.deepcopy(ORDER)
    async def tools(registry, name, args):
        if name == "shopify_get_order":
            return _copy.deepcopy(live)
        return await fake_tool_json(registry, name, args)
    async def req(method, path, params=None, body=None, **kw):
        live["shipping_address"]["zip"] = body["variables"]["input"]["shippingAddress"]["zip"]
        raise _hx.ReadTimeout("")
    saved = (shopify._tool_json, _srv._request, shopify._order_writer)
    shopify._tool_json, _srv._request, shopify._order_writer = tools, req, _srv.update_order_fields
    try:
        r = post("/api/order/edit", {"order_id": 12345, "ship_to": {"postcode": "M1 6JK"}, "confirm_booked": True})
        eq(r.status_code, 200, "the change landed, and is reported as made: " + r.text)
        ok(desk._load_dispatch()["12345"].get("address_changed_at"), "and the booked label is marked as diverged")
        # A booking that recorded its address is marked even by a no-change retry.
        desk._record_dispatch(12345, {"tracking_number": "T-9", "carrier_name": "DPD",
                                         "dispatched_at": "2026-09-22T09:00:00Z",
                                         "booked_address": {"street": "24 Liberty Ave", "street2": "Unit 3",
                                                            "postcode": "M1 2AB", "city": "Manchester", "country": "GB"}})
        post("/api/order/edit", {"order_id": 12345, "ship_to": {"postcode": "M1 6JK"}, "confirm_booked": True})
        ok(desk._load_dispatch()["12345"].get("address_changed_at"), "whichever edit found it done")
    finally:
        shopify._tool_json, _srv._request, shopify._order_writer = saved
        reset_dispatch()


@test
def t_an_address_edit_that_changes_the_tax_says_so():
    """From Shopify API 2026-10 a new shipping address on an unfulfilled order
    recalculates its tax, so correcting a UK address to an export one (or the
    other way) changes what the customer owes. Shopify makes the change; the
    Edit panel must say so, with the amounts, and the ledger must record it."""
    import server as _srv
    ensure_auth(); reset_dispatch(); reset_prod()
    live = _copy.deepcopy(ORDER)
    live.update({"current_total_tax": "20.00", "current_total_price": "120.00",
                 "total_outstanding": "0.00", "currency": "GBP"})
    sent = []
    # A fully paid £120 order: after the tax drops £20, Shopify's amount
    # outstanding is -£20, which is the customer's to be refunded.
    answer = {"tax": "0.00", "total": "100.00", "outstanding": "-20.00"}
    async def tools(registry, name, args):
        if name == "shopify_get_order":
            return _copy.deepcopy(live)
        return await fake_tool_json(registry, name, args)
    async def req(method, path, params=None, body=None, **kw):
        sent.append(body)
        m = lambda v: {"shopMoney": {"amount": v, "currencyCode": "GBP"}}
        order = {"id": "gid://shopify/Order/12345", "currentTotalTaxSet": m(answer["tax"]),
                 "currentTotalPriceSet": m(answer["total"]), "totalOutstandingSet": m(answer["outstanding"])}
        if body["query"].lstrip().startswith("mutation"):
            # The mutation's own answer is stale here; the read-back is not.
            stale = dict(order, currentTotalTaxSet=m("20.00"))
            return {"data": {"orderUpdate": {"order": stale, "userErrors": []}}}
        return {"data": {"order": order}}
    saved = (shopify._tool_json, _srv._request, shopify._order_writer)
    shopify._tool_json, _srv._request, shopify._order_writer = tools, req, _srv.update_order_fields
    try:
        r = post("/api/order/edit", {"order_id": 12345, "ship_to": {"postcode": "M1 6JK"}})
        eq(r.status_code, 200, r.text)
        mutation, readback = sent[-2], sent[-1]
        ok(mutation["query"].lstrip().startswith("mutation") and "currentTotalTaxSet" in mutation["query"],
           "the totals are asked for with the change")
        ok(readback["query"].lstrip().startswith("query") and "totalOutstandingSet" in readback["query"],
           "and read back after it, as Shopify advises")
        addr = mutation["variables"]["input"]["shippingAddress"]
        ok("country" not in addr and addr.get("countryCode") == "GB", "the country goes as its code only")
        eq(r.json()["warnings"], ["Shopify recalculated the tax for the new address: \u00a320.00 before, "
                                  "\u00a30.00 now, so the order total is \u00a3100.00. "
                                  "\u00a320.00 is due back to them: refund it in Shopify."],
           "a lower tax on a paid order says what is due back, from the read-back, not the stale answer")
        ok("tax recalculated" in r.json()["changed"], "and the ledger records it")
        # Partly paid (£110 of £120): Shopify says £10 is theirs, not the £20 drop.
        answer.update({"outstanding": "-10.00"})
        r = post("/api/order/edit", {"order_id": 12345, "ship_to": {"postcode": "M1 6JJ"}})
        ok(r.json()["warnings"][-1].endswith(" \u00a310.00 is due back to them: refund it in Shopify."),
           r.json()["warnings"])
        answer.update({"outstanding": "0.00"})
        r = post("/api/order/edit", {"order_id": 12345, "ship_to": {"postcode": "M1 6JH"}})
        ok(r.json()["warnings"][-1].endswith("Nothing more is owed either way."), r.json()["warnings"])
        answer.update({"tax": "30.00", "total": "130.00", "outstanding": "10.00"})
        r = post("/api/order/edit", {"order_id": 12345, "ship_to": {"postcode": "M1 7AA"}})
        ok(r.json()["warnings"][-1].endswith("The customer now owes \u00a310.00."), r.json()["warnings"])
        # Read back after a lost answer (REST, no signed amount outstanding):
        # only what the change in total can say, hedged.
        note = orderbook._tax_change_note(
            {"tax": {"amount": "20.00", "currency": "GBP"}, "total": {"amount": "120.00", "currency": "GBP"}},
            orderbook._rest_totals({"current_total_tax": "0.00", "current_total_price": "100.00", "currency": "GBP"}))
        ok(note.endswith("If they had paid in full, \u00a320.00 is due back to them: check the order in Shopify."), note)
        answer.update({"tax": "20.00", "total": "120.00", "outstanding": "0.00"})
        r = post("/api/order/edit", {"order_id": 12345, "ship_to": {"postcode": "M1 8BB"}})
        eq(r.json()["warnings"], [], "nothing is said when the tax did not change (every version before 2026-10)")
        ok("tax recalculated" not in r.json()["changed"], "and nothing is recorded")
    finally:
        shopify._tool_json, _srv._request, shopify._order_writer = saved
        reset_dispatch()


@test
def t_an_order_address_goes_to_shopify_as_codes():
    """MailingAddressInput's free-text country and province are deprecated.
    The country goes only as its code (the Edit panel refuses anything else
    already); a province goes as its code when it is one, and a typed name
    still goes as text rather than be dropped or guessed at."""
    import server as _srv
    eq(_srv._addr_input({"country": "gb", "state": "ON"}), {"countryCode": "GB", "provinceCode": "ON"})
    eq(_srv._addr_input({"country": "CA", "state": "Ontario"}), {"countryCode": "CA", "province": "Ontario"})
    eq(_srv._addr_input({"country": "IE", "state": "D"}), {"countryCode": "IE", "provinceCode": "D"},
       "Dublin's one-letter code is a code")
    eq(_srv._addr_input({"country": "JP", "state": "JP-13"}), {"countryCode": "JP", "provinceCode": "JP-13"})
    eq(_srv._addr_input({"country": "MX", "state": "Q ROO", "state_is_code": True}),
       {"countryCode": "MX", "provinceCode": "Q ROO"}, "and the order's own code goes back as a code, any shape")
    try:
        _srv._addr_input({"country": "United Kingdom"})
        ok(False, "a country name is refused, not sent as deprecated free text")
    except ValueError as e:
        ok("two-letter code" in str(e), str(e))
    r = run_async(_srv.update_order_fields(1, {"ship_to": {"country": "United Kingdom"}}))
    eq((r["ok"], r["reason"]), (False, "user_error"), "and the writer reports it instead of raising")


@test
def t_an_edit_sends_the_orders_own_province_code_back_as_a_code():
    """The order's own province code goes back as a code whatever its shape
    (Dublin is "D"), not as the deprecated free-text province."""
    ensure_auth(); reset_dispatch(); reset_prod()
    live = _copy.deepcopy(ORDER)
    live["shipping_address"].update({"address1": "1 Grafton Street", "address2": "", "city": "Dublin",
                                     "province_code": "D", "zip": "D02 X285", "country_code": "IE"})
    async def tools(registry, name, args):
        if name == "shopify_get_order":
            return _copy.deepcopy(live)
        return await fake_tool_json(registry, name, args)
    saved = shopify._tool_json
    shopify._tool_json = tools
    try:
        r = _edit({"ship_to": {"street2": "Floor 2"}})
        eq(r.status_code, 200, r.text)
        ship = ORDER_WRITES[-1][1]["ship_to"]
        eq((ship.get("state"), ship.get("state_is_code")), ("D", True), "Dublin's code is marked as a code")
        import server as _srv
        eq(_srv._addr_input(ship).get("provinceCode"), "D", "and goes to Shopify as provinceCode")
    finally:
        shopify._tool_json = saved
        reset_dispatch()


@test
def t_the_receivers_tax_id_is_read_from_the_orders_localized_fields():
    """Order.localizationExtensions is deprecated in favour of localizedFields,
    which asks the same thing (the TAX credential a checkout collects)."""
    import server as _srv
    seen = []
    async def req(method, path, params=None, body=None, **kw):
        seen.append(body["query"])
        return {"data": {"order": {"localizedFields": {"nodes": [
            {"key": "TAX_CREDENTIAL_IT", "value": "IT12345678901", "title": "Codice fiscale", "countryCode": "IT"}]},
            "purchasingEntity": None, "customer": None}}}
    saved = _srv._request
    _srv._request = req
    try:
        got = run_async(_srv.shopify_order_tax_id(12345))
    finally:
        _srv._request = saved
    eq(got, {"tax_id": "IT12345678901", "source": "the order's Codice fiscale"})
    ok("localizedFields(" in seen[-1] and "localizationExtensions" not in seen[-1], "through the current field")


@test
def t_an_address_changed_in_the_shopify_admin_stops_mark_made():
    """A26, found by the round-4 review: an address changed in the Shopify
    admin never passes through the app's edit route, and Mark made read no
    live address, so it fulfilled and emailed tracking for a parcel cut to the
    old one. Asked and answered once, it is not asked again."""
    import worldoptions as _wo
    ensure_auth(); _ship_cfg(); reset_dispatch(); reset_prod()
    saved = (_wo._soap_call, dict(ORDER["shipping_address"]))
    async def soap(service, action, inner, retryable=True):
        return _ET.fromstring(BOOK_XML if service == "ShipmentService" else RATE_XML)
    _wo._soap_call = soap
    try:
        ok(post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX}).json().get("ok"), "booked")
        # The same address read back is not a change.
        m = mark_made().json()
        ok(m.get("fulfilled"), "an unchanged address ships as before: %r" % m)
        reset_dispatch(); reset_prod()
        ok(post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX}).json().get("ok"), "booked again")
        ORDER["shipping_address"].update(address1="9 New Street", zip="LS2 9ZZ", city="Leeds")
        m = mark_made().json()
        ok(not m.get("fulfilled") and not m.get("notified") and m.get("needs_ack"),
           "an admin-side change stops it before tracking goes out: %r" % m)
        m = post("/api/production-state", {"op": "made", "id": 12345, "on": True, "ack_address": True}).json()
        ok(m.get("fulfilled"), "answered, it ships: %r" % m)
    finally:
        _wo._soap_call = saved[0]
        ORDER["shipping_address"].clear(); ORDER["shipping_address"].update(saved[1])
        reset_dispatch(); reset_prod()


@test
def t_a_handover_that_failed_once_moves_the_gmail_label_whole():
    """A28. The retry added the new owner's label and never removed the old
    one, whose id the failure had evicted."""
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        ann, _s, _p = ready_user("Ann", "ann"); bob, _s2, _p2 = ready_user("Bob", "bob")
        labels = {"t1": set()}
        ids = {"Copilot/Ann": "L1", "Copilot/Bob": "L2"}
        fail = {"n": 0}
        async def list_labels():
            return dict(ids)
        async def modify(tid, add=None, remove=None):
            if fail["n"]:
                fail["n"] -= 1; raise _gm.GmailError("Backend Error")
            labels[tid] |= set(add or []); labels[tid] -= set(remove or [])
        saved = (_gm.list_labels, _gm.modify_thread)
        _gm.list_labels, _gm.modify_thread = list_labels, modify
        try:
            _seed_thread("t1")
            st = mail._load_mail(); t = st["threads"]["t1"]
            t["owner"], t["state"] = ann, "assigned"
            run_async(mail._mail_sync_labels(t, "Ann"))
            t["owner"] = bob; fail["n"] = 1
            run_async(mail._mail_sync_labels(t, "Bob"))
            run_async(mail._mail_sync_labels(t, "Bob"))
            eq(sorted(labels["t1"]), ["L2"], "only Bob's label is on it in Gmail")
        finally:
            _gm.list_labels, _gm.modify_thread = saved
    with_mail(go)


@test
def t_an_ai_draft_waits_its_turn_in_the_ai_window():
    """A29. Drafting a reply with Claude neither took nor respected a slot in
    the global AI window."""
    src = copilot_source()
    seg = src.split("async def mail_draft_route(")[1].split("resp = await claude._xcreate(claude._anthropic(), model=claude.MODEL_DEEP")[0]
    ok("gate._window_ok(gate._rl_global, gate.RATE_MAX_GLOBAL" in seg, "the compose checks the AI window before the call")


@test
def t_booked_labels_are_not_held_in_memory():
    """A41. Every label written stayed in the store cache until a restart,
    about a megabyte a booking, pruned from disk or not."""
    desk._save_dispatch_labels("990001", [{"type": "pdf", "value": "x" * 1000}])
    ok(not any(str(p).startswith(desk.DISPATCH_LABELS_DIR) for p in jsonstore._json_cache),
       "a label file is written, not cached")


@test
def t_the_backup_download_is_built_off_the_event_loop():
    """A42. Deflating the whole volume inline stalled every request and webhook."""
    src = copilot_source()
    seg = src.split('@mcp.custom_route("/api/backup"')[1][:2500]
    ok("await asyncio.to_thread(backup._build_backup_zip)" in seg, "off the loop, as the pre-import snapshot is")


@test
def t_a_folder_holding_only_finders_sidecars_can_be_deleted():
    """A43. A hidden .DS_Store counted as content while the tab showed the
    folder empty, and nothing in the tab could remove it."""
    import base64 as _b64
    def go():
        def inner(fake):
            ensure_auth()
            webdav._dav_auth_cache.clear()
            _u, _s, pw = ready_user("Poppy", "poppy", role="member")
            auth = {"Authorization": "Basic " + _b64.b64encode(("poppy:" + drive_pw(_s)).encode()).decode()}
            client.request("MKCOL", "/dav/Old job", headers=auth)
            client.put("/dav/Old job/.DS_Store", headers=auth, content=b"\x00\x00\x00\x01Bud1" + b"\x00" * 60)
            tree = post("/api/files/tree", {}).json()["store"]
            fid = next(k for k, v in tree["folders"].items() if v["name"] == "Old job")
            eq(post("/api/files/folder", {"op": "delete", "id": fid}).status_code, 200)
            ok(not any(str(v.get("folder_id") or "") == fid for v in fileserver._load_files()["files"].values()),
               "and the sidecar went with it")
        with_files(inner)
    with_accounts(go)


@test
def t_what_the_customer_paid_for_delivery_is_what_they_paid():
    """A44. The shipping line's list price: a free-shipping code still read as
    the full charge, and VAT was set against the courier's ex VAT cost."""
    o = _copy.deepcopy(ORDER)
    o["taxes_included"] = True
    o["shipping_lines"] = [{"title": "Tracked 24", "price": "12.00", "discount_allocations": [],
                            "tax_lines": [{"price": "2.00"}]}]
    eq(desk._shipping_paid(o, ex_vat=False), 12.0, "what they paid, VAT in")
    eq(desk._shipping_paid(o, ex_vat=True), 10.0, "and ex VAT, for the courier comparison")
    o["shipping_lines"][0]["discount_allocations"] = [{"amount": "12.00"}]
    o["shipping_lines"][0]["tax_lines"] = []
    eq(desk._shipping_paid(o, ex_vat=False), 0.0, "a free-shipping code is a free delivery")
    # And the booking records that, not the list price (the round-4 review
    # found the test passed with the record put back to the list price).
    import worldoptions as _wo
    ensure_auth(); _ship_cfg(); reset_dispatch(); reset_prod()
    saved = (_wo._soap_call, ORDER.get("shipping_lines"), ORDER.get("taxes_included"))
    async def soap(service, action, inner, retryable=True):
        return _ET.fromstring(BOOK_XML if service == "ShipmentService" else RATE_XML)
    _wo._soap_call = soap
    ORDER["taxes_included"] = True
    ORDER["shipping_lines"] = [{"title": "Tracked 24", "price": "12.00", "tax_lines": [],
                                "discount_allocations": [{"amount": "12.00"}]}]
    try:
        ok(post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX}).json().get("ok"), "booked")
        eq(desk._load_dispatch()["12345"].get("shipping_paid"), "0.00", "the record says they paid nothing")
    finally:
        _wo._soap_call = saved[0]
        for k, v in (("shipping_lines", saved[1]), ("taxes_included", saved[2])):
            if v is None:
                ORDER.pop(k, None)
            else:
                ORDER[k] = v
        reset_dispatch(); reset_prod()


@test
def t_a_long_thread_lists_its_newest_attachments():
    """A45. A thread kept its OLDEST twenty attachments, so the newest proofs
    in a long artwork thread could not be saved."""
    store = {"threads": {}}
    msgs = [{"id": "m%d" % i, "from_name": "Jo", "from_email": "jo@c.com", "at": "2026-09-%02dT10:00:00+00:00" % i,
             "snippet": "proof", "files": [{"name": "proof-v%d-%d.pdf" % (i, k), "size": 1, "mime": "application/pdf",
                                             "id": "a%d%d" % (i, k), "msg": "m%d" % i} for k in range(1, 5)]}
            for i in range(1, 7)]
    mail._mail_apply_thread(store, {"id": "t2", "historyId": "1", "subject": "Artwork", "messages": msgs}, MBOX)
    names = [f["name"] for f in store["threads"]["t2"]["files"]]
    eq(len(names), 20)
    ok("proof-v6-4.pdf" in names and "proof-v1-1.pdf" not in names, names[-3:])




@test
def t_a_capped_page_read_closes_what_it_left():
    """A read that stops at its cap leaves the loop over a stream's chunks; the
    running loop closes what is left. The suite's run_async closed its own loop
    without doing so (asyncio.run does), so that close was dropped and every
    suite run warned of a coroutine never awaited: the last line of noise the
    quiet suite left. run_async now closes the loop's async generators first,
    as asyncio.run does. The keyword scan that first showed it went with the
    report tabs (22 Oct 2026), so a stream of the same shape stands in."""
    import gc, warnings
    closed = []

    async def chunks():
        try:
            for _ in range(8):
                yield b"x" * 1024
        finally:
            await asyncio.sleep(0)      # a close that needs the loop, as a response's does
            closed.append(True)

    async def read_capped(cap):
        got = b""
        async for c in chunks():
            got += c
            if len(got) >= cap:
                break                   # the cap: what is left is the loop's to close
        return got

    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        text = run_async(read_capped(2048))
        eq(closed, [True], "the stream's close ran before run_async gave its loop up")
        gc.collect()
        run_async(asyncio.sleep(0))
        gc.collect()
    eq(len(text), 2048)
    eq([str(w.message) for w in seen if "never awaited" in str(w.message)], [],
       "nothing is left for the loop to finalise")
