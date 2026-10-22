@test
def t_the_page_csp_does_not_allow_inline_script():
    """The allowance was left over from when the page was one file with its
    script inline. Splitting the JS into /assets/app.js made it dead weight,
    and dead weight in a CSP is the difference between an injected string
    being inert and being executed - which matters here because the session
    token lives in localStorage, readable by any script that runs."""
    import copilot as _c
    class _Req:
        headers = {}
        query_params = {}
        url = type("U", (), {"path": "/"})()
    csp = rendering._frame_headers(_Req())["Content-Security-Policy"]
    script = [d for d in csp.split(";") if d.strip().startswith("script-src")][0]
    ok("'unsafe-inline'" not in script, "script-src forbids inline: " + script.strip())
    ok("'unsafe-eval'" not in script, "and eval")
    ok("https://cdn.shopify.com" in script, "App Bridge still loads")
    # style-src deliberately keeps it: the page sets element.style throughout.
    style = [d for d in csp.split(";") if d.strip().startswith("style-src")][0]
    ok("'unsafe-inline'" in style, "style-src keeps it, deliberately")
    # And the served page must actually have nothing inline to run.
    shell, _assets = rendering._page_parts()
    import re as _re
    inline = _re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", shell, _re.S)
    ok(not [b for b in inline if b.strip()], "the shell carries no inline script block")
    ok(not _re.search(r"\son[a-z]+\s*=\s*[\"']", shell), "and no inline event handler attribute")


@test
def t_only_the_configured_store_can_frame_the_app():
    """frame-ancestors trusted any well-formed ?shop= and fell back to every
    myshopify.com store, so a free development store could frame Reactor
    under decoy buttons and steer a signed-in person's clicks (8 Sept
    second pass, finding 2). With the store configured, the page names that
    store and the admin, whatever the URL says."""
    import copilot as _c
    def ancestors(shop):
        class _Req:
            headers = {}
            query_params = {"shop": shop} if shop is not None else {}
            url = type("U", (), {"path": "/"})()
        csp = rendering._frame_headers(_Req())["Content-Security-Policy"]
        return [d for d in csp.split(";") if d.strip().startswith("frame-ancestors")][0].split()[1:]
    saved = config.SHOPIFY_STORE
    try:
        for store in ("test-store", "test-store.myshopify.com"):
            config.SHOPIFY_STORE = store
            for shop in ("evil-dev.myshopify.com", "test-store.myshopify.com", "not a shop", None):
                eq(ancestors(shop), ["https://test-store.myshopify.com", "https://admin.shopify.com"],
                   "store %r, ?shop=%r: only the store and the admin" % (store, shop))
        # Unconfigured (a local run): the old behaviour, so a developer's
        # own dev store can still embed it.
        config.SHOPIFY_STORE = ""
        eq(ancestors("dev-one.myshopify.com"), ["https://dev-one.myshopify.com", "https://admin.shopify.com"],
           "no store configured: a well-formed ?shop= is used")
        eq(ancestors(None), ["https://admin.shopify.com", "https://*.myshopify.com"],
           "and without one, the admin and any store")
    finally:
        config.SHOPIFY_STORE = saved


@test
def t_the_connector_tab_is_a_guarded_proxy():
    """The Shopify->Xero connector writes to the accounting ledger, so gizmo
    only ever proxies it: its token never reaches a browser, the tab is opt-in
    like the books, and anything that writes is admin-only."""
    import copilot as _c
    # Opt-in, never inherited with an account.
    ok("connector" in team.TAB_KEYS and "connector" in team.OPT_IN_TABS,
       "the tab exists and is handed over deliberately")
    ok(any(p == "/api/connector" for p, _t in gate._TAB_ROUTES),
       "and the route is behind the tab gate")

    # Unconfigured: says so, calls nothing.
    called = []
    real = xerosync._connector_call
    async def fake(method, path, params=None):
        called.append((method, path, dict(params or {})))
        return 200, {"ok": True, "running": False}
    xerosync._connector_call = fake
    old_url = os.environ.pop("CONNECTOR_URL", None)
    try:
        r = post("/api/connector", {"op": "status"}).json()
        eq(r.get("available"), False, "no CONNECTOR_URL means a plain 'not linked yet'")
        eq(called, [], "and the service is never called")

        os.environ["CONNECTOR_URL"] = "http://connector.internal:8899"
        # Reads proxy through.
        r = post("/api/connector", {"op": "status"}).json()
        eq(r.get("available"), True, "configured, the status proxies")
        eq(called[-1][:2], ("GET", "/api/status"), "to the service's own endpoint")
        # A review is the dry run, open to any tab holder.
        r = post("/api/connector", {"op": "review"}).json()
        eq(called[-1], ("POST", "/api/sync", {"dryRun": "1"}),
           "review is the service's dry run, which writes nothing")
        # The master may send; the wire call is the real sync.
        r = post("/api/connector", {"op": "send"}).json()
        eq(called[-1][:2], ("POST", "/api/sync"), "send is the real sync")
        eq(called[-1][2], {}, "with no dryRun flag")
        # Reimport requires naming the order.
        r = post("/api/connector", {"op": "reimport"})
        eq(r.status_code, 400, "a reimport with no order is refused")
        r = post("/api/connector", {"op": "reimport", "order": "#104300"}).json()
        eq(called[-1][2].get("order"), "#104300", "and with one, it passes it through")
        # A tag send names the tag, and its check is the dry run.
        eq(post("/api/connector", {"op": "reimport_tag"}).status_code, 400, "a tag send with no tag is refused")
        post("/api/connector", {"op": "reimport_tag", "tag": "xero-price-check", "dryRun": True})
        eq(called[-1], ("POST", "/api/reimport-tag", {"tag": "xero-price-check", "dryRun": "1"}),
           "the tag and the dry run reach the service as they are")
        post("/api/connector", {"op": "reimport_tag", "tag": "xero-price-check"})
        eq(called[-1][2], {"tag": "xero-price-check"}, "and an admin's send carries no dryRun")
        # Unknown op refused.
        eq(post("/api/connector", {"op": "explode"}).status_code, 400, "unknown ops are refused")
        # The service's token never appears in any reply.
        os.environ["CONNECTOR_TOKEN"] = "super-secret-token"
        raw = post("/api/connector", {"op": "status"}).text
        ok("super-secret-token" not in raw, "the token never leaves the server")
    finally:
        xerosync._connector_call = real
        os.environ.pop("CONNECTOR_TOKEN", None)
        if old_url is None:
            os.environ.pop("CONNECTOR_URL", None)
        else:
            os.environ["CONNECTOR_URL"] = old_url


@test
def t_only_an_admin_can_write_to_xero():
    """Send, retry and reimport create documents in the accounting system.
    A member with the tab may look and review; writing is a different act."""
    import copilot as _c
    called = []
    real = xerosync._connector_call
    async def fake(method, path, params=None):
        called.append((method, path))
        return 200, {"ok": True}
    xerosync._connector_call = fake
    os.environ["CONNECTOR_URL"] = "http://connector.internal:8899"
    try:
        # A member account holding the connector tab.
        r = post("/api/team/user", {"op": "create", "name": "Clerk", "username": "clerk-conn",
                                    "role": "member"}).json()
        uid, pw = r["id"], r["starter_password"]
        post("/api/team/user", {"op": "tabs", "id": uid,
                                "tabs": ["overview", "connector"]})
        lr = client.post("/api/auth/login", json={"username": "clerk-conn", "password": pw},
                         headers={"Authorization": "Bearer " + tok()}).json()
        sess = lr["session"]
        post_s(sess, "/api/auth/password", {"current": pw, "new": "a-much-longer-password-9"})
        sess = client.post("/api/auth/login",
                           json={"username": "clerk-conn", "password": "a-much-longer-password-9"},
                           headers={"Authorization": "Bearer " + tok()}).json()["session"]
        eq(post_s(sess, "/api/connector", {"op": "status"}).status_code, 200,
           "the clerk can look")
        eq(post_s(sess, "/api/connector", {"op": "review"}).status_code, 200,
           "and review, which writes nothing")
        for op in ("send", "retry", "reimport", "reimport_tag"):
            rr = post_s(sess, "/api/connector", {"op": op, "order": "#1", "tag": "t"})
            eq(rr.status_code, 403, op + " is refused for a member")
        wrote = [c for c in called if c[0] == "POST" and c[1] in ("/api/sync",) ]
        # the clerk's review was a POST /api/sync (dry) - allowed; no other writes
        ok(all(c[1] not in ("/api/retry", "/api/reimport", "/api/reimport-tag") for c in called),
           "no write ever reached the service from the member")
        # And an account WITHOUT the tab cannot even look.
        post("/api/team/user", {"op": "tabs", "id": uid, "tabs": ["overview"]})
        eq(post_s(sess, "/api/connector", {"op": "status"}).status_code, 403,
           "without the tab, the door is shut")
        post("/api/team/user", {"op": "delete", "id": uid})
    finally:
        xerosync._connector_call = real
        os.environ.pop("CONNECTOR_URL", None)


@test
def t_every_reply_says_which_build_answered_it():
    """Shopify admin holds an embedded app open for days, so a tab can outlive
    several deploys and keep running the old page. From the desk that is
    invisible: it looks exactly like a bug that was already fixed. Every reply
    carries the hash of the JavaScript this server serves, and the page compares
    it against the one it was loaded with."""
    got = client.post("/api/dispatch/collections", json={})   # no auth needed: 401 is a reply too
    build = got.headers.get("X-App-Build")
    ok(build, "the header is there whatever the outcome (status %s)" % got.status_code)
    ok(len(build) >= 8, "long enough not to collide between builds")
    # NOT the asset hash. That hash is the token /assets/app.js checks before it
    # serves, and this header rides on unauthenticated replies too - publishing
    # it would hand the app's whole client source to anyone who called an
    # endpoint. Proved by asking for the source with the header's value.
    ok(build != rendering._asset_hashes.get("js"),
       "the header is not the token that unlocks the client source")
    leak = client.get("/assets/app.js?v=" + build)
    eq(leak.status_code, 404, "and it does not open that door")
    shell, _assets = rendering._page_parts()
    ok('content="%s"' % build in shell, "the page carries the same marker to compare against")
    ok('content="%s"' % rendering._asset_hashes.get("js") not in shell,
       "and the page never prints the asset token as a build marker")
    # It follows the file: change the JS and the header changes with it.
    import copy as _copy
    saved = (rendering._page_cache, rendering._page_assets, dict(rendering._asset_hashes))
    try:
        rendering._page_cache = None
        rendering._page_assets = None
        rendering._asset_hashes.clear()
        # The page is joined by pagesource.join, which copilot looks up as it
        # calls it: standing in for it here changes the page the server reads.
        real = pagesource.join
        page = real(HERE)
        moved_page = page.replace("<script>\n    (function ()", "<script>\n    (function () /*moved*/", 1)
        ok(moved_page != page, "the stand-in page really differs")
        pagesource.join = lambda root=None: moved_page
        moved = rendering._build_id()
        ok(moved and moved != build, "a changed page is a changed build id")
    finally:
        pagesource.join = real
        rendering._page_cache, rendering._page_assets = saved[0], saved[1]
        rendering._asset_hashes.clear(); rendering._asset_hashes.update(saved[2])
    eq(rendering._build_id(), build, "and the real one is unchanged afterwards")


@test
def t_a_collection_belongs_to_the_day_the_van_comes():
    """Found auditing this week's work. Every other dispatch date in the app is
    reckoned in Europe/London and the ready window can push a booking to the
    next working day - book after the close on a Friday and the van comes
    Monday. The ledger was writing UTC "today", so Monday would look
    uncollected and the first parcel that morning would book, and pay for, a
    second pickup."""
    eq(desk._dmy_to_iso("31/08/2026"), "2026-08-31", "their dd/MM/yyyy becomes a real date")
    eq(desk._dmy_to_iso("1/9/2026"), "2026-09-01", "single digits too")
    eq(desk._dmy_to_iso("rubbish"), "", "and nonsense is not guessed at")
    # The ready date wins over whatever day it happens to be.
    eq(desk._collection_target("I_Need_To_Book_A_Collection", "31/08/2026"), "2026-08-31",
       "the collection is dated by the day the courier was asked to come")
    # With no ready date it falls back to London's today, not UTC's.
    from zoneinfo import ZoneInfo as _Z
    from datetime import datetime as _dt
    london = _dt.now(_Z("Europe/London")).date().isoformat()
    eq(desk._collection_target("I_Need_To_Book_A_Collection"), london,
       "and today means today where the parcels are")
    eq(desk._dispatch_today(), london, "which is what the panel asks for too")
    # A Friday booking for Monday does not suppress Monday.
    cfg = {"collection_by_carrier": {"DHL": "I_Need_To_Book_A_Collection"}}
    plan = desk._collection_plan(cfg, "DHL", {"DHL": {"date": "2026-08-28"}}, "31/08/2026")
    eq(plan["arrangement"], "I_Need_To_Book_A_Collection",
       "Friday's van does not cover Monday's parcel")
    plan2 = desk._collection_plan(cfg, "DHL", {"DHL": {"date": "2026-08-31"}}, "31/08/2026")
    eq(plan2["arrangement"], "I_Already_Have_Collection_Scheduled",
       "while a second parcel for the same day rides the one already booked")
    # And the record keeps the ready date so the day can be worked out later.
    src = copilot_source()
    eq(src.count('"ready_date": _ready_dmy'), 1,
       "the record stores the day the courier was asked to come, in the one place records are made")
    eq(src.count("await _book_and_record("), 2,
       "and both booking paths make their record there")


@test
def t_the_quote_asks_about_the_day_the_van_is_coming():
    """Reported live: "still getting book a collection on a DHL parcel even
    though I have a DHL booked". Two separate reasons, both here.

    The rates list asked whether a van was coming TODAY, while the booking
    records it against the READY date - which after the close is tomorrow. So a
    collection booked at half five was filed for tomorrow and then not found,
    and the next parcel was told to book, and be charged for, a second one.

    And it read only this app's ledger, never the courier's own confirmation on
    the dispatch record - so a collection booked on a custom shipment, which
    never wrote that ledger, was invisible."""
    real_ready = desk._collection_ready
    desk._collection_ready = lambda cfg, now=None: ("31/08/2026", "09:00")
    try:
        cfg = {"collection_by_carrier": {"DHL": "I_Need_To_Book_A_Collection"}}
        opts = lambda: [{"carrier_name": "DHL"}, {"carrier_name": "UPS"}]

        # Booked late today, so the courier comes on the 31st. Filed there, found there.
        desk._write_dispatch({})
        desk._write_collections({"DHL": {"date": "2026-08-31", "at": "2026-08-28T17:31:00+00:00"}})
        o = opts(); desk._collection_plans(cfg, o)
        ok(o[0]["collection_already"], "the second parcel rides the van already booked")
        eq(o[0]["collection_message"], "Collection already booked for today",
           "and is told so rather than asked to book again")

        # The courier's own confirmation, with no ledger entry at all.
        desk._write_collections({})
        desk._write_dispatch({"C1": {"carrier_name": "DHL", "collection_date": "REF-1",
                                        "ready_date": "31/08/2026", "order_name": "custom",
                                        "dispatched_at": "2026-08-28T17:31:00+00:00"}})
        o = opts(); desk._collection_plans(cfg, o)
        ok(o[0]["collection_already"],
           "a collection booked on a custom shipment counts just the same")

        # Cleared: the van has been, so the next parcel books a fresh one.
        desk._write_collections({"DHL": {"date": "2026-08-31", "cleared": True}})
        o = opts(); desk._collection_plans(cfg, o)
        ok(not o[0]["collection_already"], "and once cleared it asks again")
        eq(o[0]["collection_option"], "I_Need_To_Book_A_Collection", "with the courier's own arrangement")

        # A courier nobody configured still answers, and is not confused with DHL.
        eq(o[1]["collection_option"], "", "an unconfigured courier falls back to the standing setting")
    finally:
        desk._collection_ready = real_ready
        desk._write_collections({}); desk._write_dispatch({})


@test
def t_a_custom_shipment_books_the_collection_its_courier_needs():
    """It sent the standing setting whatever the courier was, so a DHL custom
    shipment asked for whatever UPS is set to - and it never recorded the van it
    had just booked, so nothing after it knew."""
    src = copilot_source()
    eq(src.count("collection_option=str(cfg.get(\"collection_option\") or \"\")"), 0,
       "no booking path sends the standing setting regardless of courier")
    eq(src.count("_record_collection("), 2,
       "one writer, called from the one booking spine both paths go through")
    eq(src.count("await _book_and_record("), 2, "which both paths do")
    ok("_record_collection(shipment.get(\"carrier_name\") or option.get(\"carrier_name\")" in src,
       "including the custom one")
    # The writer only files a van when one was actually asked for.
    desk._write_collections({})
    desk._record_collection("DHL", "I_Have_Daily_Collection", "31/08/2026")
    eq(desk._load_collections(), {}, "a standing daily collection is not a booking")
    desk._record_collection("", "I_Need_To_Book_A_Collection", "31/08/2026")
    eq(desk._load_collections(), {}, "and a courier with no name is not filed under one")
    desk._record_collection("dhl", "I_Need_To_Book_A_Collection", "31/08/2026", "#1", "Express")
    eq(desk._load_collections()["DHL"]["date"], "2026-08-31",
       "a real booking is filed against the day the van comes")
    desk._write_collections({})


@test
def t_the_courier_reference_is_never_printed_as_markup():
    """World Options glues three things together with literal tags:
    28/08/2026<br/>12:00:00<br/>PRG260828150481. Printed straight it puts
    "<br/>" on a dispatch screen, which is exactly what it did - on the
    Collections panel, on the booking result and in the manifest column."""
    got = worldoptions.parse_collection("28/08/2026<br/>12:00:00<br/>PRG260828150481")
    eq(got["ref"], "PRG260828150481", "the reference comes out on its own")
    eq(got["date"], "28/08/2026", "and the date")
    eq(got["time"], "12:00:00", "and the time")
    # Whatever shape it arrives in, no markup leaves this function.
    for raw in ("28/08/2026<br/>12:00:00<br/>PRG1", "<b>odd</b>", "A<br>B", "PRG9",
                "", None, "  ", "29/08/2026<BR />09:30<BR />X1"):
        out = worldoptions.parse_collection(raw)
        for k in ("ref", "date", "time"):
            ok("<" not in out[k] and ">" not in out[k],
               "%r left markup in %s: %r" % (raw, k, out[k]))
    eq(worldoptions.parse_collection("PRG9")["ref"], "PRG9",
       "a bare reference is still a reference")
    eq(worldoptions.parse_collection(None)["ref"], "", "and nothing is nothing")
    # Every place it is shown reads it through the parser.
    src = copilot_source()
    eq(src.count("parse_collection("), 2,
       "both the collections view and the manifest column parse it")
    html = pagesource.join(HERE)
    ok("collRefText(s.collection_date)" in html,
       "and the booking result does too, for records stored before this")


@test
def t_a_collection_is_read_from_the_couriers_own_reference():
    """World Options returns a collection reference on the booking reply -
    CollectionDateNumber - and it has been kept on every dispatch record since
    long before any of this was built. That is the courier's own answer to "is a
    van coming", so it is worth more than a ledger this app keeps beside it, and
    it covers shipments booked before the ledger existed."""
    from datetime import datetime as _dt, timezone as _tz
    today = clock._london_today().isoformat()   # the day the code reckons in (London), not the UTC date
    desk._write_dispatch({
        "9001": {"carrier_name": "DHL", "carrier_label": "DHL Express",
                 "collection_date": "CN-8842", "order_name": "#104294",
                 "dispatched_at": today + "T09:12:00+00:00"},
        "9002": {"carrier_name": "UPS", "carrier_label": "UPS",
                 "collection_date": "", "order_name": "#104290",
                 "dispatched_at": today + "T09:20:00+00:00"},
        "9003": {"carrier_name": "DHL", "carrier_label": "DHL Express",
                 "collection_date": "CN-1", "order_name": "#104100",
                 "dispatched_at": "2020-01-01T09:00:00+00:00"},
    })
    got = desk._collections_from_dispatch(today)
    ok("DHL" in got, "the courier that confirmed a collection is there")
    eq(got["DHL"]["ref"], "CN-8842", "with World Options' own reference")
    eq(got["DHL"]["order"], "#104294", "and the order that secured it")
    ok("UPS" not in got, "a booking with no collection reference is not one")
    # Yesterday's van is not today's.
    eq(len([k for k in got if got[k]["date"] == today]), 1, "and only this day counts")
    # And that answer suppresses a second ask.
    cfg = {"collection_by_carrier": {"DHL": "I_Need_To_Book_A_Collection"}}
    plan = desk._collection_plan(cfg, "DHL", got)
    eq(plan["arrangement"], "I_Already_Have_Collection_Scheduled",
       "so the next DHL parcel does not book a second pickup")
    desk._write_dispatch({})


@test
def t_collections_shows_what_this_app_booked_and_says_so():
    """World Options cannot be asked what is scheduled: their service exposes
    exactly three operations - DoShipment, GetAllServicesAndRates and
    VoidShipment. So this is gizmo's own record, and the panel says that rather
    than implying it read the courier's diary."""
    def go():
        r = post("/api/dispatch/collections", {})
        eq(r.status_code, 200, r.text[:160])
        d = r.json()
        ok(d.get("date"), "it answers for a day")
        ok(isinstance(d.get("rows"), list) and d["rows"], "with a row per courier")
        ok("no way to be asked" in (d.get("note") or "").lower()
           or "portal" in (d.get("note") or "").lower(),
           "and says where the record comes from: " + str(d.get("note"))[:90])
        row = d["rows"][0]
        for k in ("carrier", "label", "arrangement", "scheduled", "standing"):
            ok(k in row, "each row carries %s" % k)
        # Clearing is a charge-bearing act: the next parcel books a new pickup.
        rr = post("/api/dispatch/collections", {"op": "clear", "carrier": "DHL"})
        eq(rr.status_code, 200, "an admin may clear one")
    with_accounts(go)


@test
def t_one_collection_a_day_per_courier_not_one_per_parcel():
    """Book a collection with DHL for one shipment and every other DHL parcel
    that day rides the same van. Asking again books - and is charged for - a
    second pickup. So "book a collection" becomes "already scheduled" for the
    rest of that day on its own, per courier, without anyone remembering."""
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    today = clock._london_today().isoformat()   # the day the code reckons in (London), not the UTC date
    tomorrow = (clock._london_today() + _td(days=1)).isoformat()
    cfg = {"collection_by_carrier": {"DHL": "I_Need_To_Book_A_Collection",
                                     "UPS": "I_Have_Daily_Collection"},
           "collection_option": "I_Need_To_Book_A_Collection"}

    first = desk._collection_plan(cfg, "DHL", {})
    eq(first["arrangement"], "I_Need_To_Book_A_Collection", "the first DHL parcel asks")
    eq(first["message"], "Book a collection for this shipment", "and says so")
    ok(not first["already"], "nothing is booked yet")

    second = desk._collection_plan(cfg, "DHL", {"DHL": today})
    eq(second["arrangement"], "I_Already_Have_Collection_Scheduled",
       "the second DHL parcel of the day does NOT ask again")
    ok(second["already"], "and knows why")
    eq(second["message"], "Collection already booked for today", "and says which day")

    # It is per courier: DHL's van does not collect the UPS parcels.
    eq(desk._collection_plan(cfg, "UPS", {"DHL": today})["message"],
       "Daily collection scheduled", "UPS is unaffected by DHL's booking")
    other = desk._collection_plan({"collection_option": "I_Need_To_Book_A_Collection"},
                                     "FEDEX", {"DHL": today})
    eq(other["arrangement"], "I_Need_To_Book_A_Collection",
       "and a courier with nothing booked still asks")

    # Yesterday's van is no help today.
    stale = desk._collection_plan(cfg, "DHL", {"DHL": "2020-01-01"})
    eq(stale["arrangement"], "I_Need_To_Book_A_Collection", "a stale date does not suppress today")

    # A next-day request is held against the day it is FOR.
    nd = dict(cfg, collection_by_carrier={"DHL": "I_Need_To_Book_A_Collection_For_Next_Day"})
    eq(desk._collection_target("I_Need_To_Book_A_Collection_For_Next_Day"), tomorrow,
       "a next-day collection is for tomorrow")
    eq(desk._collection_plan(nd, "DHL", {"DHL": tomorrow})["arrangement"],
       "I_Already_Have_Collection_Scheduled", "and a second one for the same day does not ask")
    eq(desk._collection_plan(nd, "DHL", {"DHL": today})["arrangement"],
       "I_Need_To_Book_A_Collection_For_Next_Day",
       "while today's van does not cover tomorrow's parcel")



def _every_clock(value):
    """Set the clock (the datetime class) in copilot.py and in every module
    split out of it that reads its own, to value: a class, or what an earlier
    call returned, to put each back. Returns what was there. A test that
    calls this patches every clock, and t_no_test_patches_a_name_nobody_reads
    counts it so; naming each module by hand went stale with every move."""
    import importlib, datetime as _dt
    out = []
    for rel in COPILOT_FILES:
        m = importlib.import_module(rel[:-3].replace("/", "."))
        if "datetime" in vars(m):
            out.append((m, m.datetime))
            m.datetime = dict((id(k), v) for k, v in value)[id(m)] if isinstance(value, list) else value
    return [(m, v) for m, v in out]


@test
def t_the_collection_tests_hold_in_the_hour_after_midnight():
    """Two of the collection tests built "today" from the UTC date while the code reckons the day in London, so
    between 00:00 and 01:00 BST they failed on a clean tree. They now use the day the code uses. Proven here by
    running them with the clock at 00:30 BST on the 15th of July (23:30 UTC on the 14th), the hour that broke them: a test
    that took its date from the real UTC clock would now be a day off the code's."""
    import datetime as _real
    class _Frozen(_real.datetime):
        @classmethod
        def now(cls, tz=None):
            base = _real.datetime(2026, 7, 14, 23, 30, tzinfo=_real.timezone.utc)
            return base.astimezone(tz) if tz else base.replace(tzinfo=None)
    saved = _every_clock(_Frozen)
    try:
        eq(clock._london_today().isoformat(), "2026-07-15", "the code's day is London's, a day ahead of UTC in this hour")
        t_a_collection_is_read_from_the_couriers_own_reference()
        t_one_collection_a_day_per_courier_not_one_per_parcel()
    finally:
        _every_clock(saved)

@test
def t_a_booked_collection_is_written_down_before_anything_can_fail():
    """It is recorded straight after the courier is booked and charged, inside
    the stretch that must not raise. If it were not, a crash between booking and
    recording would let the next parcel book a second pickup."""
    src = copilot_source()
    i = src.index("_record_collection(shipment.get(\"carrier_name\") or option.get(\"carrier_name\")")
    charged = src.index("From here the courier is BOOKED and the account is charged")
    ok(charged < i, "it is recorded after the booking is known to have succeeded")
    seg = src[src.index("def _record_collection("):][:1200]
    ok("_write_collections" in seg, "and written to the ledger")
    ok("except Exception" in seg,
       "and cannot itself throw: nothing after a charge may raise")
    # Proved, not just read: a store that will not take a write is swallowed.
    real = desk._write_collections
    desk._write_collections = lambda d: (_ for _ in ()).throw(OSError("disk full"))
    try:
        desk._record_collection("DHL", "I_Need_To_Book_A_Collection", "31/08/2026")
    finally:
        desk._write_collections = real


@test
def t_each_courier_carries_its_own_collection_arrangement():
    """It genuinely differs by courier: a daily UPS collection already calls,
    while DHL has to be asked each time. One global setting made the desk
    remember which was which, and got it wrong in exactly the direction that
    costs money - asking a courier that already collects."""
    cfg = {"collection_option": "I_Need_To_Book_A_Collection",
           "collection_by_carrier": {"UPS": "I_Have_Daily_Collection"}}
    eq(desk._collection_for(cfg, "UPS"), "I_Have_Daily_Collection",
       "UPS is not asked to collect, because it already does")
    eq(desk._collection_for(cfg, "DHL"), "I_Need_To_Book_A_Collection",
       "DHL is asked, because nothing is standing")
    eq(desk.COLLECTION_MESSAGES["I_Have_Daily_Collection"], "Daily collection scheduled",
       "and the desk is told which, in those words")
    ok("Book a collection for this shipment"
       == desk.COLLECTION_MESSAGES["I_Need_To_Book_A_Collection"],
       "and which, for the other")
    # Only real carriers and real arrangements survive a save.
    src = copilot_source()
    i = src.index('if isinstance(body.get("collection_by_carrier"), dict):')
    seg = src[i:i + 800]
    ok("valid_c" in seg and "carrier_choices()" in seg, "the carrier must be one we know")
    ok("valid_a" in seg and "COLLECTION_OPTIONS" in seg,
       "and the arrangement one the courier actually offers")
    # Every quoted option carries its own answer, so it can be shown per row.
    eq(src.count("_collection_plans(cfg, options)"), 2,
       "both quote paths stamp every option with how its courier collects")
    seg = src[src.index("def _collection_plans("):][:1600]
    ok('o["collection_message"]' in seg and 'o["collection_already"]' in seg,
       "each option says how its courier collects, and whether one is already coming")
    html = pagesource.join(HERE)
    ok(html.count("if (op.collection_message)") == 2,
       "and BOTH option lists show it - the order panel and the pasted address one")


@test
def t_asking_for_a_collection_is_spent_once_it_is_used():
    """The mistake that costs money here is asking five times in a morning and
    being charged for five pickups."""
    html = pagesource.join(HERE)
    i = html.index("function renderResult(res)")
    seg = html[i:html.index("function renderResultSafe(", i)]
    ok("collectionForRun === askedCollection" in seg,
       "a booking that carried the arrangement clears it, and only THAT booking")
    # After the panel is on screen, not before it: clearing first and then
    # failing to paint would drop the arrangement without ever saying so.
    ok(seg.index("collectionForRun = null") > seg.index("body.append(out);"),
       "and only once the result is actually up")
    ok("collection_option: askedCollection" in html,
       "the value actually rides on the request")


@test
def t_an_international_postcode_is_alphanumeric_but_a_uk_one_is_untouched():
    """UPS validates the "sold to" party on an INTERNATIONAL shipment, and wants
    its fields alphanumeric. An Eircode is written with a space. Every UPS
    shipment this app has ever booked was GB to GB - domestic, no customs, no
    sold-to party - so no UK postcode has ever been through that validation,
    which is why the domestic path is left exactly as it is rather than tidied
    on a hunch."""
    eq(worldoptions._postcode("D12 VC2N", "IE"), "D12VC2N", "an Eircode loses its space")
    eq(worldoptions._postcode("D02 XK40", "IE"), "D02XK40", "every Eircode does")
    eq(worldoptions._postcode("NE1 5HX", "GB"), "NE1 5HX", "a UK postcode is untouched")
    eq(worldoptions._postcode("CV8 1NP", "GB"), "CV8 1NP", "the working path is byte-identical")
    eq(worldoptions._postcode("01310-100", "BR"), "01310-100",
       "a hyphen stays: Brazil, Poland and Portugal write real postcodes with them")
    eq(worldoptions._postcode("408555", "SG"), "408555", "and one with nothing to strip is left alone")
    eq(worldoptions._postcode("", "IE"), "", "nothing stays nothing")
    eq(worldoptions._postcode("D12 VC2N", ""), "D12 VC2N", "an unknown country is not guessed at")
    # Both the quote and the booking send it through.
    src = open(os.path.join(HERE, "worldoptions.py"), encoding="utf-8").read()
    for field in ("DeliveryPostCode", "Postalcode"):
        m = re.search(r'_ts?\(\s*"m",\s*"' + field + r'"\s*,\s*([^\n]*)', src)
        ok(m and "_postcode(" in m.group(1),
           "%s goes through the normaliser: %s" % (field, m.group(1)[:60] if m else "(absent)"))


@test
def t_every_courier_call_carries_its_envelope_out():
    """The booking attached the envelope it sent; the quote and the cancellation
    did not. That is how a Dublin shipment came to be refused for naming a field
    nobody could see. Their errors name a .NET parameter rather than a field, so
    the request is the only way to tell WHICH address they mean, and a quote is
    what fails first."""
    src = open(os.path.join(HERE, "worldoptions.py"), encoding="utf-8").read()
    # Every _reply_status call sits inside a handler that attaches the envelope.
    for m in re.finditer(r'_reply_status\(reply, "', src):     # calls, not the def
        seg = src[m.start():m.start() + 700]
        ok("e.envelope = _redacted(inner)" in seg,
           "the call at offset %d carries its envelope: %s" % (m.start(), ' '.join(seg.split())[:90]))
    eq(src.count("e.envelope = _redacted(inner)"), 5,
       "rate, booking (both branches) and cancel all attach it")


@test
def t_a_quote_that_will_not_price_hands_over_the_evidence():
    """A courier rejected a Dublin shipment with "Invalid sold to state province
    code" and the operator had nothing to look at, because the QUOTE path threw
    the exception away and kept only str(e). The booking path has handed the
    envelope over since it was written; quoting is what fails FIRST, so it was
    the one failure in the dispatch flow that left the desk empty-handed."""
    class _Boom(worldoptions.WorldOptionsError):
        pass
    e = _Boom("Invalid sold to state province code. Valid length is 0 to 5 alphanumeric")
    e.raw = "<s:Fault>...</s:Fault>"
    e.envelope = "<wo:SenderDetails><m:State></m:State></wo:SenderDetails>"
    tech = desk._wo_tech(e, "104294")
    eq(tech.get("reply"), "<s:Fault>...</s:Fault>", "what they said comes back")
    ok("State" in (tech.get("request") or ""), "and what we sent, blanks visible")
    eq(tech.get("order"), "104294", "tagged with the order it belongs to")
    ok(tech.get("when"), "and when")
    # Nothing to show is not a panel with nothing in it.
    eq(desk._wo_tech(_Boom("no detail")), {}, "an error carrying no evidence makes no panel")
    # One implementation, so the two paths cannot drift apart again.
    src = copilot_source()
    eq(src.count("def _wo_tech("), 1, "there is exactly one of these")
    ok(src.count("_wo_tech(") >= 3, "and both the quote and the booking paths call it")


@test
def t_a_county_nobody_can_abbreviate_is_sent_as_nothing():
    """Order #104294, Dublin, refused with "Invalid sold to state province
    code. Valid length is 0 to 5 alphanumeric". The delivery address was fine -
    Shopify gives Dublin the code "D". The offender was the SENDER's county,
    typed by a person into a free-text "County / state" box the way people
    actually say it. "England" is seven characters; "Tyne and Wear" is
    thirteen. Empty is explicitly valid, and a GB or IE postcode identifies the
    destination on its own, so an unusable county is dropped rather than
    truncated into wrong data."""
    for raw, cc, want, why in [
        # Ireland is the case that started this, and it cost three wrong fixes.
        # UPS refuses an Irish address whether the field carries Shopify's ISO
        # county code ("Dublin" -> "D") or nothing at all: it wants the literal
        # "IE", which is what UPS's own error guidance tells shippers to send.
        ("D", "IE", "IE", "the Irish county code Shopify supplies is replaced"),
        ("Dublin", "IE", "IE", "and so is the county spelled out"),
        ("", "IE", "IE", "and an EMPTY one, which UPS refuses just as firmly"),
        (None, "IE", "IE", "and a missing one"),
        # Britain ships fine today, and sends nothing meaningful either way:
        # "ENG" is not a county and UPS routes GB on the postcode.
        ("England", "GB", "", "nor a UK nation"),
        ("Tyne and Wear", "GB", "", "nor a county with no code"),
        # Where the carrier genuinely requires one, it is sent, and a spelled
        # out name is translated rather than dropped.
        ("CA", "US", "CA", "a US state is sent, because UPS requires one"),
        ("California", "US", "CA", "spelled out, it is translated"),
        ("New York", "US", "NY", "two words and all"),
        ("Ontario", "CA", "ON", "and Canadian provinces too"),
        ("QLD", "AU", "QLD", "an Australian state passes through"),
        ("", "US", "", "nothing stays nothing"),
    ]:
        eq(worldoptions._state_code(raw, cc), want, "%r/%s: %s" % (raw, cc, why))
    for raw, cc in (("England", "GB"), ("Tyne and Wear", "GB"), ("Co. Dublin", "IE"),
                    ("California", "US"), ("South Yorkshire", "GB"), ("", "IE")):
        out = worldoptions._state_code(raw, cc)
        ok(len(out) <= 5 and (out.isalnum() or out == ""),
           "%r/%s produced %r, which the courier would refuse" % (raw, cc, out))


@test
def t_every_address_block_normalises_its_state():
    """Four places a state crosses the wire: the quote's delivery and
    collection, and the booking's recipient and sender. One of them being
    unguarded is all it takes to lose a booking."""
    src = open(os.path.join(HERE, "worldoptions.py"), encoding="utf-8").read()
    emits = re.findall(r'_ts?\(\s*"m",\s*"(DeliveryState|CollectionCountryState|State_Code|State)"\s*,\s*(_state_code\([^)]*\)[^)]*)\)', src)
    eq(len(emits), 4, "all four wire sites are present: %r" % (emits,))
    for field, arg in emits:
        ok("_state_code(" in arg,
           "%s goes through the normaliser, not raw: %s" % (field, arg.strip()[:60]))
        ok("country" in arg,
           "%s passes the COUNTRY too, since whether to send one depends on it: %s"
           % (field, arg.strip()[:70]))


@test
def t_a_real_route_comes_back_compressed():
    """The unit test above proves the middleware. This proves it is actually IN
    the stack the merchant's requests go through, which is a different claim and
    the one that was silently false while the suite built its own bare app."""
    def go():
        # Enough people to clear the 1 KB floor comfortably. `person_add`: the
        # route has no "create", and asking for it only ever passed on whatever
        # earlier tests had left in the store.
        for i in range(60):
            r = post("/api/crm/contact", {"op": "person_add",
                                          "name": "Contact %d, repeat customer for gobo orders" % i,
                                          "emails": ["c%d@example.com" % i],
                                          "job_title": "Lighting designer, touring and theatre"})
            eq(r.status_code, 200, r.text[:120])
        gate._rl_hits.clear(); gate._rl_global.clear()
        r = client.post("/api/crm/board", json={},
                        headers={"Authorization": "Bearer " + tok(),
                                 "X-App-Session": ensure_auth(),
                                 "Accept-Encoding": "gzip"})
        eq(r.status_code, 200, r.text[:160])
        eq(r.headers.get("content-encoding"), "gzip",
           "the board came back compressed through the real stack")
        ok("accept-encoding" in (r.headers.get("vary") or "").lower(), "and varies on it")
        wire = int(r.headers["content-length"])
        plain = len(json.dumps(r.json()).encode())
        ok(wire < plain / 2, "%d bytes on the wire for %d of JSON" % (wire, plain))
        body = r.json()
        ok(isinstance(body, dict) and not body.get("error"),
           "and the data survived the trip: %s" % str(body)[:120])
    with_accounts(go)


@test
def t_an_inbox_click_writes_the_mailbox_once_not_twice():
    """Measured at 3,000 threads: claiming an email cost 225 ms, 223 ms of it
    inside two full serialisations of a 6 MB store, on the event loop. The
    second one exists to persist whatever the Gmail label trip recorded, which
    most of the time is nothing at all. The durable-write-before-Gmail ordering
    is unchanged: the first write still happens first."""
    writes = []
    saved = mail._write_mail

    def counting(d):
        writes.append(1)
        return saved(d)
    mail._write_mail = counting
    try:
        # Gmail not connected: the label trip has nothing to record.
        t = {"id": "t1", "state": "assigned", "owner": "u1"}
        changed = run_async(mail._mail_sync_labels(t, "Ruth"))
        eq(changed, False, "a disconnected mailbox changes nothing")
        eq(writes, [], "and asks for no write of its own")

        # Nothing to do, because the label already says what it should.
        t2 = {"id": "t2", "state": "done", "gmail_label": "Copilot/Done"}
        eq(run_async(mail._mail_sync_labels(t2, "Ruth")), False,
           "a label already correct is not rewritten")
    finally:
        mail._write_mail = saved
    # Since 2026-10-12 the label trip runs after the answer, in one place
    # (_mail_labels_later), and that is where the follow-up write is guarded.
    src = copilot_source()
    eq(src.count("if await _mail_sync_labels("), 1,
       "the one follow-up write is guarded on there being something to write")
    eq(src.count('_mail_labels_soon(t["id"])'), 3,
       "and claim, assign and state all hand the label to it")
    ok("await _mail_sync_labels(t, _team_name(who))\n        _write_mail" not in src,
       "and none of them writes unconditionally any more")


@test
def t_a_gobo_miss_is_only_paid_once_per_sheet():
    """A miss falls through every index into a word-run scan of all 2,155 sheet
    rows: measured at 0.63 ms against 0.008 ms for a hit. The same fixtures come
    back order after order, so without a memo the same scan is repeated for
    every line item in the queue."""
    cache = size_list._gobo_sizes()
    cache.setdefault("lookup_memo", {}).clear()
    miss = ("Nonesuch Lighting", "Fixture That Does Not Exist 9000")
    r1 = size_list._gobo_lookup(*miss, cache=cache)
    eq(r1[0], None, "it is genuinely a miss")
    ok(len(cache["lookup_memo"]) == 1, "and the answer was remembered")
    t0 = time.perf_counter()
    for _ in range(200):
        rn = size_list._gobo_lookup(*miss, cache=cache)
    per = (time.perf_counter() - t0) / 200
    eq(rn, r1, "the remembered answer is the same answer")
    ok(per < 0.0001, "and costs almost nothing to repeat: %.4f ms" % (per * 1000))

    # A hit is remembered too, and by reference to the same sheet row.
    size_list._gobo_lookup("Robe", "Robin Viva", cache=cache)
    before = len(cache["lookup_memo"])
    ok(before >= 1, "hits are remembered as well")

    # And a new sheet must never be answered out of the old one's memo.
    size_list._gobo_cache["mtime"] = -1
    fresh = size_list._gobo_sizes()
    eq(fresh.get("lookup_memo"), {},
       "reloading the sheet throws the memo away with it")


@test
def t_a_reaped_connection_is_retried_but_an_ambiguous_one_is_not():
    """Pooling adds exactly one failure mode a fresh connection never had: the
    far end reaps an idle keep-alive between our requests. That failure happens
    BEFORE anything is sent, so it is the one transport error a POST may be
    replayed after. Everything else stays unreplayable."""
    import httpx as _hx
    tries = []

    class _Resp:
        status_code = 200
        headers: dict = {}
        text = "{}"
        def json(self): return {"ok": True}
        def raise_for_status(self): return None

    class _Client:
        def __init__(self, boom, fail_times):
            self.boom, self.left = boom, fail_times
        async def request(self, method, url, **kw):
            tries.append(method)
            if self.left > 0:
                self.left -= 1
                raise self.boom
            return _Resp()

    saved = (server._http, server._headers, server.SHOPIFY_STORE, server.asyncio.sleep)
    server.SHOPIFY_STORE = server.SHOPIFY_STORE or "test-store"

    async def _hdr(): return {}
    async def _nosleep(_s): return None
    server._headers, server.asyncio.sleep = _hdr, _nosleep
    try:
        # Connection never established: nothing was sent, so retry the POST.
        c = _Client(_hx.ConnectError("connection reset"), 1)
        server._http = lambda: c
        tries.clear()
        r = run_async(server._request("POST", "fulfillments.json", body={"x": 1}))
        eq(r, {"ok": True}, "the write went through on the retry")
        eq(len(tries), 2, "which took exactly one retry")

        # Ambiguous: it may have arrived and been acted on. Do not replay.
        c2 = _Client(_hx.ReadTimeout("lost the answer"), 1)
        server._http = lambda: c2
        tries.clear()
        raised = None
        try:
            run_async(server._request("POST", "fulfillments.json", body={"x": 1}))
        except Exception as e:
            raised = e
        ok(isinstance(raised, _hx.TimeoutException), "it surfaced: %r" % (raised,))
        eq(len(tries), 1, "and the POST was tried exactly once")
    finally:
        server._http, server._headers, server.SHOPIFY_STORE, server.asyncio.sleep = saved


@test
def t_one_pooled_client_is_reused_across_calls():
    """The measured cost of not doing this: 89 ms per Shopify call instead of
    29 ms, paid 8 times on a cold production queue and 30 on the Liability tab."""
    server._pool = None
    a = server._http()
    b = server._http()
    ok(a is b, "the same client answers every call")
    ok(a.is_closed is False, "and it is live")
    lim = getattr(a, "_limits", None) or getattr(a, "limits", None)
    if lim is not None:
        ok((lim.max_keepalive_connections or 0) > 0, "with keep-alive actually enabled")
        ok(lim.keepalive_expiry and lim.keepalive_expiry <= 60,
           "and a short idle life, so the far end does not reap it under us")


@test
def t_big_answers_are_compressed_and_streams_are_left_alone():
    """The measured reason: the Complete production queue is 1,117 KB of JSON
    and the CRM board 1,162 KB, sent raw, on every tab switch. The measured
    danger: Starlette's own GZipMiddleware would buffer the chat SSE route to
    compress it, turning a live stream into one late lump. Compression keys on
    Content-Length, which a streaming response never sets."""
    import gzip as _gz
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse as _JR, StreamingResponse, Response as _Rsp
    from starlette.routing import Route

    big = {"rows": [{"id": i, "name": "Northern Stage Ltd", "note": "x" * 40}
                    for i in range(400)]}
    ticks = []

    async def _big(request): return _JR(big)
    async def _small(request): return _JR({"ok": True})
    async def _img(request): return _Rsp(b"\x89PNG" + b"y" * 40000, media_type="image/png")

    async def _stream(request):
        async def gen():
            for i in range(3):
                ticks.append(i)
                yield ("data: chunk %d\n\n" % i).encode()
        return StreamingResponse(gen(), media_type="text/event-stream")

    app = Starlette(routes=[Route("/big", _big), Route("/small", _small),
                            Route("/img", _img), Route("/stream", _stream)])
    app.add_middleware(server.CompressionMiddleware)
    c = TestClient(app)

    r = c.get("/big", headers={"Accept-Encoding": "gzip"})
    eq(r.headers.get("content-encoding"), "gzip", "a big JSON answer is compressed")
    ok("accept-encoding" in (r.headers.get("vary") or "").lower(), "and says what it varies on")
    raw = json.dumps(big).encode()
    sent = int(r.headers["content-length"])
    ok(sent < len(raw) / 4, "meaningfully smaller: %d -> %d bytes" % (len(raw), sent))
    eq(r.json(), big, "and it is the same data on the other side")

    # The one that matters. A stream has no Content-Length, so it is never held.
    rs = c.get("/stream", headers={"Accept-Encoding": "gzip"})
    eq(rs.headers.get("content-encoding"), None, "a stream is NOT compressed")
    eq(rs.text.count("data:"), 3, "and arrives whole")

    eq(c.get("/small", headers={"Accept-Encoding": "gzip"}).headers.get("content-encoding"),
       None, "a small answer is not worth the CPU")
    eq(c.get("/img", headers={"Accept-Encoding": "gzip"}).headers.get("content-encoding"),
       None, "already-compressed bytes are left alone")
    r2 = c.get("/big", headers={"Accept-Encoding": "identity"})
    eq(r2.headers.get("content-encoding"), None, "a client that cannot read gzip is not sent it")
    eq(r2.json(), big, "and still gets its data")


@test
def t_granting_every_tab_grants_every_tab():
    """The picker used to send null for a fully ticked panel, meaning 'no list
    of its own'. Once that resolved to the DEFAULT tabs, ticking every box and
    saving WITHHELD the books, and the ledger recorded 'can open
    everything'. The obvious action did the opposite of its label and said so
    in the permanent record."""
    def go():
        r = post("/api/team/user", {"op": "create", "name": "Ruth", "username": "ruthx",
                                    "role": "member"})
        uid, pw = r.json()["id"], r.json()["starter_password"]
        # What the tab panel sends when every box is ticked.
        post("/api/team/user", {"op": "tabs", "id": uid, "tabs": list(team.TAB_KEYS)})
        ok("connector" in (team._user_tabs(uid) or []),
           "an explicitly complete grant includes the books")

        lg = client.post("/api/auth/login", json={"username": "ruthx", "password": pw},
                         headers={"Authorization": "Bearer " + tok()}).json()
        sess = lg.get("session")
        ch = post_s(sess, "/api/auth/password", {"current": pw, "new": "ruth-pw-40217"})
        sess = ch.json().get("session") or sess
        ok(gate._tab_denied(_GateReq("/api/connector", sess)) is None,
           "and the door actually opens")

        # And the null form, which means "no list of its own", must not be
        # written into the record as a grant of everything.
        post("/api/team/user", {"op": "tabs", "id": uid, "tabs": None})
        ok("connector" not in (team._user_tabs(uid) or []), "null falls back to the default set")
        ev = [e for e in activity._load_events()[-12:] if "access" in json.dumps(e).lower()
              or "open" in json.dumps(e).lower()]
        said = json.dumps(ev)
        ok("can open everything" not in said,
           "and the ledger does not claim a grant that was not made: " + said[-260:])
    with_accounts(go)

