# =========================== routes: quote/book/label/cancel ================
@test
def t_quote_route():
    r = post("/api/dispatch/quote", {"order_id": 12345, "box": {"width": 20, "length": 15, "depth": 8, "weight": 0.6}})
    eq(r.status_code, 200, r.text)
    body = r.json()
    # three door services, plus the cheaper no-signature price for the one carrier
    # that actually has a no-signature service
    eq(len(body["options"]), 4, "shop services hidden by default")
    eq(len([o for o in body["options"] if o.get("no_signature")]), 1, "one no-signature row")
    eq(body["destination"]["postcode"], "M1 2AB", "dest")

@test
def t_quote_bad_box():
    r = post("/api/dispatch/quote", {"order_id": 12345, "box": {"width": 0, "length": 15, "depth": 8, "weight": 0}})
    eq(r.status_code, 400, "bad box")
    ok("above zero" in r.json()["error"], "message")

@test
def t_book_defers_fulfilment_until_made():
    reset_dispatch(); reset_prod()
    TAG_WRITES.clear(); FULFILLED.clear()
    r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
    eq(r.status_code, 200, r.text)
    body = r.json()
    eq(body["ok"], True, "booked")
    eq(body["shipment"]["tracking_number"], "WO1234567890", "tracking")
    eq(body["awaiting_made"], True, "flagged as waiting on Mark made")
    eq(len(FULFILLED), 0, "booking must NOT fulfil an unmade order")
    joined = " ".join(t[1].lower() for t in TAG_WRITES)
    ok("complete" not in joined.lower(), "not tagged Complete while unmade")
    st = json.load(open(SCRATCH + "/dispatch_state.json"))["orders"]["12345"]
    eq(st["fulfilled"], False, "state says unfulfilled")
    eq(st["notify"], True, "email choice stored for later")
    ok(os.path.isfile(SCRATCH + "/labels/12345.json"), "label saved for reprint")

    # Marking made is what ships it.
    TAG_WRITES.clear()
    r2 = mark_made()
    eq(r2.status_code, 200, r2.text)
    b2 = r2.json()
    eq(b2["fulfilled"], True, "made fulfils when a label is booked")
    eq(b2["notified"], True, "customer emailed at made")
    ok("Fulfilled in Shopify" in (b2.get("ship_note") or ""), "explains what happened")
    eq(len(FULFILLED), 1, "exactly one fulfillment")
    eq(FULFILLED[0]["tracking"], "WO1234567890", "booked tracking used")
    eq(FULFILLED[0]["company"], "UPS", "carrier name mapped for Shopify")
    last = TAG_WRITES[-1][1].lower()
    ok("complete" in last.lower(), "now tagged Complete")
    ok("ip" not in [t.strip() for t in last.split(",")], "IP dropped")
    st = json.load(open(SCRATCH + "/dispatch_state.json"))["orders"]["12345"]
    eq(st["fulfilled"], True, "state records the fulfilment")
    eq(st["fulfillment_id"], 555, "fulfillment id kept for unwinding")

@test
def t_made_is_idempotent():
    # Re-marking made must not fulfil (or email) twice.
    FULFILLED.clear()
    r = mark_made()
    eq(r.status_code, 200, r.text)
    eq(len(FULFILLED), 0, "no second fulfillment")

@test
def t_made_first_then_dispatch_fulfils():
    reset_dispatch(); reset_prod()
    FULFILLED.clear(); TAG_WRITES.clear()
    mark_made()                      # made with no label yet: just IP -> PC
    eq(len(FULFILLED), 0, "nothing to fulfil without a label")
    r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
    eq(r.status_code, 200, r.text)
    eq(r.json()["awaiting_made"], False, "already made, so it ships now")
    eq(len(FULFILLED), 1, "dispatch fulfils an already-made order")
    ok("complete" in TAG_WRITES[-1][1].lower(), "tagged Complete")

@test
def t_untick_made_unwinds_the_fulfilment():
    reset_dispatch(); reset_prod()
    CANCELED_FULFILLMENTS.clear(); TAG_WRITES.clear()
    post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
    mark_made()
    r = mark_made(on=False)
    eq(r.status_code, 200, r.text)
    eq(CANCELED_FULFILLMENTS, [555], "Shopify fulfillment cancelled")
    st = json.load(open(SCRATCH + "/dispatch_state.json"))["orders"]["12345"]
    eq(st["fulfilled"], False, "state reverted")
    ok(st.get("tracking_number"), "label still booked")
    last = TAG_WRITES[-1][1].lower()
    ok("complete" not in last.lower(), "the finished tag is removed")
    ok("ip" in [t.strip() for t in last.split(",")], "back in production")

@test
def t_book_no_option():
    r = post("/api/dispatch/book", {"order_id": 12345, "option": {}, "box": {"width": 20, "length": 15, "depth": 8, "weight": 0.6}})
    eq(r.status_code, 400, "no option -> error")
    ok("selected" in r.json()["error"], "message")

@test
def t_label_reprint():
    r = post("/api/dispatch/label", {"order_id": 12345})
    eq(r.status_code, 200, r.text)
    eq(r.json()["labels"][0]["type"], "base64pdf", "stored label returned")

@test
def t_label_missing():
    r = post("/api/dispatch/label", {"order_id": 99999})
    eq(r.status_code, 404, "no label -> 404")

@test
def t_cancel_route():
    r = post("/api/dispatch/cancel", {"order_id": 12345, "tracking_number": "WO1234567890"})
    eq(r.status_code, 200, r.text)
    st = json.load(open(SCRATCH + "/dispatch_state.json"))["orders"]
    eq(st["12345"]["canceled"], True, "state canceled")

@test
def t_dispatch_state_in_labels():
    res = run(production.run_production_labels({}, order_id=12345))
    ok("dispatch" in res, "dispatch map")
    eq(res["dispatch"]["12345"]["tracking_number"], "WO1234567890", "tracking flows to UI")

@test
def t_status_shipping_row():
    r = post("/api/status", {})
    sh = r.json()["shipping"]
    eq(sh["ok"], True, "connected")
    eq(sh["fulfillment"], True, "fulfillment wired")

@test
def t_settings_names_the_shopify_version_the_server_runs():
    """Settings said "Connected" and never the Shopify version. Production
    starts the app as `python server.py`, which Python files under __main__,
    not "server", so copilot's sys.modules["server"] lookup found nothing and
    the version was dropped. The suite imports `server` by name, which hid it.
    The server now hands the version over, and nothing in copilot may find
    the server by its module name."""
    held = sys.modules.pop("server")          # the app as production runs it
    try:
        r = post("/api/status", {})
    finally:
        sys.modules["server"] = held
    eq(r.status_code, 200, r.text)
    eq(r.json()["shopify"]["api_version"], server.API_VERSION,
       "the version the server talks to Shopify with, with no module named server")
    ok(not re.search(r"sys\.modules(\.get\(|\[)\s*[\'\"]server[\'\"]",
                     copilot_source()),
       "copilot never looks the server up by module name: in production it is __main__")

@test
def t_backup_excludes_secret():
    r = post("/api/backup", {})
    eq(r.status_code, 200, "backup ok")
    import io, zipfile
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    ok(not any("wo_secret" in n for n in names), "WO secret excluded")
    ok(any("shipping.json" in n for n in names), "shipping config backed up")

@test
def t_env_creds_win():
    os.environ["WO_METER_NUMBER"] = "ENV-METER"
    try:
        desk._wo_boot()
        r = post("/api/shipping/config", {"op": "set", "meter_number": "TRY-OVERRIDE"})
        eq(r.status_code, 400, "env creds protect against UI change")
        ok("server" in r.json()["error"], "explains env")
    finally:
        os.environ.pop("WO_METER_NUMBER", None)
        desk._wo_boot()

@test
def t_a_stranger_cannot_write_into_the_crm_by_emailing_the_shop():
    """The enquiry bridge promoted a thread to a CRM deal on its SUBJECT LINE
    alone. The shared inbox is on the website, so anyone could send "New
    customer message" with a body naming a real customer and have it file
    itself into that customer's record, marked "Website form"."""
    def go():
        ensure_auth()
        store = mail._load_mail()
        # The real thing: Shopify's own notification address.
        _seed_thread("real1", "New customer message on 25 Aug",
                     frm=("Projected Image", "no-reply@shopifyemail.com"))
        eq(store["threads"]["real1"].get("enquiry"), "new", "a genuine notification files")
        # The same subject from anyone at all does not.
        _seed_thread("spoof1", "New customer message on 25 Aug",
                     frm=("Someone", "attacker@evil.example"))
        ok(not store["threads"]["spoof1"].get("enquiry"),
           "a stranger's lookalike is just an email, not a CRM write")
        _seed_thread("spoof2", "Contact form submission", frm=("X", "x@shopifyemail.com.evil.co"))
        ok(not store["threads"]["spoof2"].get("enquiry"),
           "and a domain that merely ENDS with the real one is not the real one")
        # The mailbox's own address counts (a forward from the shop itself).
        _seed_thread("own1", "New customer message", frm=("Sales", MBOX))
        eq(store["threads"]["own1"].get("enquiry"), "new")
    with_mail(go)

@test
def t_an_enquiry_email_line_that_is_not_an_address_is_not_used():
    """Keeping the raw text made every unparsable enquiry collapse onto one
    bogus contact, and suppressed the Reply-To rescue meant for exactly it."""
    p1 = mail._mail_parse_enquiry("Name: Dana\nEmail: (not given)\nBody:\nhello")
    eq(p1["email"], "", "a non-address is not stored as one")
    p2 = mail._mail_parse_enquiry("Name: Dana\nEmail: dana@venue.co.uk\nBody:\nhello")
    eq(p2["email"], "dana@venue.co.uk", "a real one still is")

@test
def t_a_partial_customer_crawl_is_never_reported_as_a_clean_sweep():
    """A throttled page read exactly like "no more customers": the crawl
    stopped, reported success, burned the nightly cooldown, and counted every
    contact it never reached as having no Shopify customer."""
    def go():
        ensure_auth()
        crm_wipe()
        post("/api/crm/contact", {"op": "person_add", "name": "A", "emails": ["a@x.com"]})
        calls = []
        async def flaky(registry, name, args):
            if name != "shopify_list_customers":
                return {}
            calls.append(args.get("since_id"))
            if len(calls) == 1:
                return {"customers": [{"id": 1000 + i, "email": f"p{i}@x.com"} for i in range(250)]}
            return {"_failed": True}          # Shopify stops answering
        saved = shopify._tool_json
        shopify._tool_json = flaky
        try:
            rep = run_async(salesdesk._crm_shopify_link_sweep({}))
        finally:
            shopify._tool_json = saved
        ok(not rep["complete"], "a failed page is not the end of the customers")
        ok("again" in rep["problem"].lower(), rep["problem"])
        # A crawl that runs out of PAGES says so too.
        async def endless(registry, name, args):
            if name != "shopify_list_customers":
                return {}
            n = len(calls2)
            calls2.append(1)
            return {"customers": [{"id": 9000 + n * 250 + i, "email": f"q{n}_{i}@x.com"}
                                  for i in range(250)]}
        calls2 = []
        shopify._tool_json = endless
        try:
            rep2 = run_async(salesdesk._crm_shopify_link_sweep({}, max_pages=2))
        finally:
            shopify._tool_json = saved
        ok(not rep2["complete"], "hitting the page ceiling is a partial crawl")
        ok("not linked yet" in rep2["problem"], rep2["problem"])
    with_accounts(go)

@test
def t_only_an_admin_rewrites_the_shared_pipeline():
    """Stages, labels and lost reasons are the desk's settings: one member
    renaming a stage changes the board under everyone. Every sibling that
    rewrites this store is role-gated; this one was open to anyone with the
    CRM tab."""
    def go():
        ensure_auth()
        crm_wipe()
        stages = post("/api/crm/board", {}).json()["crm"]["stages"]
        _uid, sess, _pw = ready_user("Sam", "sam9", role="member")
        r = post_s(sess, "/api/crm/stages", {"stages": stages})
        eq(r.status_code, 403, "a member cannot rewrite the pipeline")
        eq(post_s(sess, "/api/crm/stages", {"labels": [{"name": "X", "color": "red"}]}).status_code,
           403, "nor the label vocabulary")
        eq(post_s(sess, "/api/crm/stages", {"lost_reasons": ["Nope"]}).status_code, 403,
           "nor the lost reasons")
        eq(post("/api/crm/stages", {"stages": stages}).status_code, 200,
           "the master still can")
    with_accounts(go)

@test
def t_a_binned_deal_still_holds_its_contact():
    """A binned deal is restorable for 30 days. Deleting its person meanwhile
    restores a deal nobody can ring back."""
    _org, per, deal = crm_seed()
    post("/api/crm/deal", {"op": "delete", "id": deal})
    r = post("/api/crm/contact", {"op": "person_delete", "id": per})
    eq(r.status_code, 400, "the contact is still spoken for by the binned deal")
    r2 = post("/api/crm/contact", {"op": "bulk_delete", "kind": "person", "ids": [per]})
    eq(r2.status_code, 400, "and bulk delete refuses rather than skipping quietly")
    ok("open deal" in r2.json()["error"], r2.text)
    # Once the deal is really gone, the contact frees up.
    post("/api/crm/deal", {"op": "restore", "id": deal})
    post("/api/crm/deal", {"op": "won", "id": deal})
    post("/api/crm/deal", {"op": "delete", "id": deal})
    d = salesdesk._load_crm()
    d["deals"][deal]["deleted_at"] = "2000-01-01T00:00:00+00:00"
    salesdesk._write_crm(d)
    salesdesk._crm_purge(d); salesdesk._write_crm(d)
    eq(post("/api/crm/contact", {"op": "person_delete", "id": per}).status_code, 200)

@test
def t_a_deleted_deal_is_not_resurrected_by_the_next_import():
    """Notes, activities and contacts all leave tombstones; deals did not, so
    a deal deleted five weeks ago reappeared on the board with no
    explanation."""
    def go():
        ensure_auth()
        crm_wipe()
        async def fake_export(progress=None):
            return dict(PD_EXPORT)
        saved = (pipedrive.export, pipedrive.API_TOKEN)
        pipedrive.export, pipedrive.API_TOKEN = fake_export, "t"
        try:
            post("/api/crm/import", {"go": True})
            d = salesdesk._load_crm()
            doomed = [x for x in d["deals"].values() if x["pd_id"] == "31"][0]["id"]
            post("/api/crm/deal", {"op": "delete", "id": doomed})
            # The bin empties: that is the moment the tombstone must exist.
            d = salesdesk._load_crm()
            d["deals"][doomed]["deleted_at"] = "2000-01-01T00:00:00+00:00"
            salesdesk._write_crm(d)
            d = salesdesk._load_crm()
            salesdesk._crm_purge(d)
            salesdesk._write_crm(d)
            ok("31" in (salesdesk._load_crm().get("pd_deleted_deals") or []),
               "the deal leaves a tombstone as it goes")
            post("/api/crm/import", {"go": True})
            back = [x for x in salesdesk._load_crm()["deals"].values() if x.get("pd_id") == "31"]
            eq(back, [], "and the import does not bring it back")
        finally:
            pipedrive.export, pipedrive.API_TOKEN = saved
    with_accounts(go)

@test
def t_a_session_less_label_url_can_read_but_not_release():
    """Shopify's print-action extension cannot carry an app session, so one
    cannot be required - but a URL minted without a gizmo account behind it
    must not stamp orders printed or release them into production, which is a
    real workflow change that was reachable by anyone denied the tab."""
    src = copilot_source()
    i = src.index('mode = "rw" if signer else "ro"')
    ok('f"{raw_ids}|{exp}|{mode}"' in src[i:i + 400],
       "the mode is inside the signature, so it cannot be edited into the URL")
    j = src.index("may_write = (not authed) or mode ==")
    ok('printed_ids = [o["id"] for o in orders if o.get("id")] if may_write else []' in src[j:j + 6000],
       "a read-only URL stamps nothing and releases nothing")

@test
def t_a_successful_net30_update_is_not_reported_as_a_failure():
    """Success was decided by reading the note's first words. The commonest
    outcome of all - terms UPDATED from due-on-receipt to Net 30 - starts
    differently, so the normal path showed the merchant a red failure toast
    for a job that worked."""
    def go():
        ensure_auth()
        saved_w, saved_tags = shopify._payment_terms_writer, ORDER["tags"]
        ORDER["tags"] = "Unprocessed, purchase order unpaid"
        try:
            async def updated(order_id):
                return {"ok": True, "updated": True, "was": "Due on receipt"}
            shopify._payment_terms_writer = updated
            r = post("/api/production-labels/queue", {"order_id": 12345, "name": "#104239"}).json()
            ok(r["po_unpaid"], r)
            ok(r["terms_ok"], "an UPDATE is a success, whatever its sentence looks like")
            ok("Net 30" in r["terms_note"], r["terms_note"])
            async def created(order_id):
                return {"ok": True}
            shopify._payment_terms_writer = created
            ok(post("/api/production-labels/queue", {"order_id": 12345}).json()["terms_ok"])
            async def already(order_id):
                return {"ok": True, "already": True}
            shopify._payment_terms_writer = already
            ok(post("/api/production-labels/queue", {"order_id": 12345}).json()["terms_ok"])
            async def refused(order_id):
                return {"ok": False, "detail": "The access token lacks write_payment_terms."}
            shopify._payment_terms_writer = refused
            bad = post("/api/production-labels/queue", {"order_id": 12345}).json()
            ok(not bad["terms_ok"] and "write_payment_terms" in bad["terms_note"], bad)
            # An ordinary order is not an account order at all.
            ORDER["tags"] = "Unprocessed"
            plain = post("/api/production-labels/queue", {"order_id": 12345}).json()
            ok(not plain["po_unpaid"] and plain["terms_ok"] and not plain["terms_note"], plain)
        finally:
            shopify._payment_terms_writer, ORDER["tags"] = saved_w, saved_tags
    with_accounts(go)

@test
def t_printing_an_account_order_reports_its_payment_terms_too():
    """Printing IS a release, so it starts the 30-day clock - but the note was
    computed and thrown away, so a purchase order could enter production with
    no due date and nobody was told."""
    def go():
        ensure_auth()
        reset_prod(); reset_dispatch()    # a fulfilled record left by another test would make this a reprint
        saved_w, saved_tags = shopify._payment_terms_writer, ORDER["tags"]
        ORDER["tags"] = "Unprocessed, purchase order unpaid"
        try:
            async def refused(order_id):
                return {"ok": False, "detail": "no Net 30 template on this store"}
            shopify._payment_terms_writer = refused
            r = post("/api/production-state", {"op": "printed", "ids": [12345]}).json()
            ok("terms_ok" in r, "the print path reports the outcome at all")
            ok(not r["terms_ok"], r)
            ok("could not be added" in r["terms_note"], r["terms_note"])
            async def okw(order_id):
                return {"ok": True, "updated": True, "was": "Due on receipt"}
            shopify._payment_terms_writer = okw
            r2 = post("/api/production-state", {"op": "printed", "ids": [12345]}).json()
            ok(r2["terms_ok"], r2)
        finally:
            shopify._payment_terms_writer, ORDER["tags"] = saved_w, saved_tags
    with_accounts(go)

@test
def t_a_break_glass_password_stops_working():
    """MASTER_RESET writes a live password into a deploy log that is retained
    and readable by anyone with project access. It has to die quickly, and the
    password chosen afterwards must NOT inherit the expiry."""
    def go():
        import copy as _copy
        ensure_auth()                      # with_accounts starts with no users at all
        d = team._load_users()
        uid = next(k for k, u in d["users"].items() if u.get("role") == "master")
        before = _copy.deepcopy(d["users"][uid])
        try:
            os.environ["MASTER_RESET"] = "yes"
            team._master_reset_done = False
            team._master_reset_check(d)
            u = team._load_users()["users"][uid]
            ok(u.get("pw_expires_at"), "the logged password carries an expiry")
            ok(u.get("must_change"), "and still forces a new one at sign-in")
            # Aged past its window, it is refused exactly like a wrong password.
            d2 = team._load_users()
            d2["users"][uid]["pw_expires_at"] = "2000-01-01T00:00:00+00:00"
            team._write_users(d2)
            r = bare("/api/auth/login", {"username": before.get("username"), "password": "anything"})
            eq(r.status_code, 401, "an expired break-glass password is dead")
            # Choosing a real password clears the expiry, or the master would
            # be locked out of their own app half an hour later.
            d3 = team._load_users()
            d3["users"][uid]["pw_expires_at"] = ""
            team._write_users(d3)
            ok(not team._load_users()["users"][uid].get("pw_expires_at"))
        finally:
            os.environ.pop("MASTER_RESET", None)
            team._master_reset_done = False
            dd = team._load_users()
            dd["users"][uid] = before
            team._write_users(dd)
    with_accounts(go)

@test
def t_the_meter_last4_never_shows_the_api_key():
    """The shipping settings promise "connected + last4" of a METER number,
    which is not secret. With no meter set it showed the tail of the API KEY,
    which is."""
    saved = dict(worldoptions._state)
    try:
        worldoptions._state["meter"], worldoptions._state["key"] = "", "SECRETKEY9999"
        eq(worldoptions.meter_last4(), "",
           "no meter means nothing to show, not four characters of the key")
        worldoptions._state["meter"] = "METER-1234"
        eq(worldoptions.meter_last4(), "1234")
        worldoptions._state["meter"], worldoptions._state["key"] = "", ""
        eq(worldoptions.meter_last4(), "")
    finally:
        worldoptions._state.clear(); worldoptions._state.update(saved)

@test
def t_the_queue_only_promises_labels_it_still_has():
    """has_label is stamped once at booking and never cleared, but the label
    FILES are pruned oldest-first - so a months-old order advertises a label
    the volume no longer holds, and a Reprint button counts a stack it cannot
    print. One directory listing tells the truth for every order at once."""
    os.makedirs(desk.DISPATCH_LABELS_DIR, exist_ok=True)
    kept = os.path.join(desk.DISPATCH_LABELS_DIR, "555001.json")
    with open(kept, "w", encoding="utf-8") as fh:
        json.dump({"labels": [{"type": "base64pdf", "value": "x"}]}, fh)
    try:
        out = desk._dispatch_with_live_labels({
            "555001": {"tracking_number": "A", "has_label": True},   # file present
            "555002": {"tracking_number": "B", "has_label": True},   # file pruned away
            "555003": {"tracking_number": "C", "has_label": False},  # never had one
        })
        ok(out["555001"]["has_label"], "a label still on disk is still offered")
        ok(not out["555002"]["has_label"],
           "a pruned label stops being counted, rather than failing at the printer")
        ok(not out["555003"]["has_label"])
        eq(out["555001"]["tracking_number"], "A", "nothing else about the entry is disturbed")
    finally:
        try:
            os.remove(kept)
        except OSError:
            pass

@test
def t_an_international_quote_carries_the_customers_own_tax_id():
    """Shopify keeps a customer's tax id in more than one place and the
    Customer object has no such field at all, so the lookup asks all of them.
    It must fill the box for the operator, SAY where the number came from, and
    never invent one."""
    seen = []
    async def reader(order_id):
        seen.append(int(order_id))
        return {"tax_id": "ESB12345678", "source": "the order's Spanish tax credential"}
    saved = shopify._tax_id_reader
    shopify._tax_id_reader = reader
    try:
        got = run_async(desk._order_tax_id({"id": 12345}))
        eq(got["receiver_tax_id"], "ESB12345678")
        ok("Spanish" in got["receiver_tax_source"], got)
        eq(seen, [12345])
        # No id on file is an empty box, not a failure.
        async def none(order_id):
            return {"tax_id": "", "source": ""}
        shopify._tax_id_reader = none
        eq(run_async(desk._order_tax_id({"id": 1}))["receiver_tax_id"], "")
        # A lookup that BLOWS UP must never stop a dispatch.
        async def boom(order_id):
            raise RuntimeError("Shopify said no")
        shopify._tax_id_reader = boom
        eq(run_async(desk._order_tax_id({"id": 1})),
           {"receiver_tax_id": "", "receiver_tax_source": ""})
        # And with no reader wired at all.
        shopify._tax_id_reader = None
        eq(run_async(desk._order_tax_id({"id": 1}))["receiver_tax_id"], "")
    finally:
        shopify._tax_id_reader = saved

@test
def t_gobos_cross_a_border_as_glass_optical_filters():
    """A customs officer needs the goods, not the shop's product name: "Create
    your own gobo" means nothing at a border. The declaration and the waybill
    must agree, and PROJECTORS - whose names also contain "gobo" - must keep
    their own description."""
    eq(desk._customs_title("Create your own gobo"), "Glass Optical Filter")
    eq(desk._customs_title("CREATE YOUR OWN GOBO"), "Glass Optical Filter",
       "however it is capitalised")
    eq(desk._customs_title("Custom Gobo"), "Glass Optical Filter")
    eq(desk._customs_title("B-size monochrome gobo"), "Glass Optical Filter")
    # The trap the classification exists for.
    eq(desk._customs_title("Projected Image 200 Watt Gobo Projector"),
       "Projected Image 200 Watt Gobo Projector", "a projector is not a filter")
    eq(desk._customs_title("Gobo Projector"), "Gobo Projector")
    eq(desk._customs_title("Glass cleaning cloth"), "Glass cleaning cloth",
       "anything else keeps its own name")
    # The waybill's contents line speaks the same language, and de-duplicates.
    summary = desk._goods_summary({"line_items": [
        {"title": "Create your own gobo"}, {"title": "Custom Gobo"},
        {"title": "Projected Image 200 Watt Gobo Projector"},
        {"title": "Additional shipping charge"}]})
    eq(summary, "Glass Optical Filter; Projected Image 200 Watt Gobo Projector",
       "two gobo lines collapse to one description, the charge is dropped")

@test
def t_a_box_preset_can_be_made_the_dispatch_default():
    """The dispatch panel already opened on cfg.default_box_id; nothing in the
    settings could SET it. And a default must never outlive the box it names,
    or dispatch opens looking for a parcel that is not there."""
    boxes = [{"id": "small", "name": "Small", "width": 20, "length": 15, "depth": 10, "weight": 0.5},
             {"id": "big", "name": "Big", "width": 40, "length": 30, "depth": 20, "weight": 2}]
    r = post("/api/shipping/config", {"op": "set", "boxes": boxes, "default_box_id": "big"})
    eq(r.status_code, 200, r.text)
    eq(r.json()["config"]["default_box_id"], "big", "the chosen preset sticks")
    # A pointer at a box that is not in the config is refused, not stored.
    r2 = post("/api/shipping/config", {"op": "set", "default_box_id": "no-such-box"})
    eq(r2.json()["config"]["default_box_id"], "", "a dangling default is cleared, not kept")
    # Choosing again works, and clearing means "the first one".
    post("/api/shipping/config", {"op": "set", "default_box_id": "small"})
    eq(post("/api/shipping/config", {"op": "get"}).json()["config"]["default_box_id"], "small")
    r3 = post("/api/shipping/config", {"op": "set", "default_box_id": ""})
    eq(r3.json()["config"]["default_box_id"], "", "and it can be turned off again")

@test
def t_collection_window_config():
    r = post("/api/shipping/config", {"op": "set", "ready_time": "14:00", "close_time": "17:30"})
    eq(r.status_code, 200, r.text)
    eq(r.json()["config"]["ready_time"], "14:00", "ready persisted")
    eq(r.json()["config"]["close_time"], "17:30", "close persisted")
    r = post("/api/shipping/config", {"op": "set", "ready_time": "2pm"})
    eq(r.status_code, 400, "bad format rejected")
    ok("HH:MM" in r.json()["error"], "format message")
    r = post("/api/shipping/config", {"op": "set", "ready_time": "18:00", "close_time": "17:30"})
    eq(r.status_code, 400, "ready after close rejected")
    r = post("/api/shipping/config", {"op": "set", "ready_time": "", "close_time": ""})
    eq(r.status_code, 200, "clearing allowed")
    eq(r.json()["config"]["ready_time"], "", "cleared")

@test
def t_book_envelope_collection_window():
    worldoptions.set_credentials(meter="M1")
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        run(worldoptions.book({"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              {"postcode": "LS1 1AA", "country": "GB"}, {"postcode": "M1 2AB", "country": "GB"},
                              [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}],
                              ready_time="14:00", close_time="17:30"))
        xml = holder["xml"]
        # The block carries more than the window now (TransportationPayor lives here),
        # so the assertion is on the values and their order, not the exact string.
        ok("<wo:CloseTime>17:30</wo:CloseTime>" in xml, "close time sent")
        ok("<wo:ReadyTime>14:00</wo:ReadyTime>" in xml, "ready time sent")
        ok(xml.index("<wo:CloseTime>") < xml.index("<wo:ReadyTime>"),
           "billing block in schema sequence, CloseTime before ReadyTime")
        ok(xml.index("AuthenticationDetail") < xml.index("BillingDetail") < xml.index("RecipientsDetails"),
           "BillingDetail between auth and recipient (alphabetical request order)")
        # Without a window the block is STILL sent: it used to be dropped entirely,
        # but TransportationPayor lives inside it and its enum starts at
        # Bill_To_Receiver, so an absent block invoiced the customer for carriage.
        run(worldoptions.book({"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              {"postcode": "LS1 1AA", "country": "GB"}, {"postcode": "M1 2AB", "country": "GB"},
                              [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}]))
        ok("<wo:TransportationPayor>Bill_To_Sender</wo:TransportationPayor>" in holder["xml"],
           "no window, but the payor is still stated")
        # Learned from their live validator ("Ready date should be in format -
        # dd/MM/yyyy"): format checks run on PRESENT values, so an unset time is
        # OMITTED, never sent as "".
        ok("<wo:CloseTime>" not in holder["xml"], "an unset window is absent, not an empty string")
    finally:
        worldoptions._soap_call = saved

@test
def t_book_route_passes_window():
    reset_dispatch()
    post("/api/shipping/config", {"op": "set", "ready_time": "09:30", "close_time": "17:00"})
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder.setdefault("xmls", []).append(inner); return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        opt = {"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS", "amount": 12.4}
        r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": {"width": 20, "length": 15, "depth": 8, "weight": 0.6}})
        eq(r.status_code, 200, r.text)
        # The window is a preference now, not the literal sent: booking after 09:30
        # must roll the ready-from forward or WO rejects it as being in the past.
        # The route must send exactly what _collection_ready computes for this cfg.
        want_d, want_t = desk._collection_ready({"ready_time": "09:30", "close_time": "17:00"})
        xml = holder["xmls"][-1]
        ok("<wo:ReadyTime>%s</wo:ReadyTime>" % want_t in xml,
           "ready time is the computed future slot (" + want_t + ")")
        ok("<wo:ReadyDate>%s</wo:ReadyDate>" % want_d in xml,
           "ready date matches (" + want_d + ")")
    finally:
        worldoptions._soap_call = saved
        post("/api/shipping/config", {"op": "set", "ready_time": "", "close_time": ""})

@test
def t_shopify_carrier_mapping():
    eq(worldoptions.shopify_carrier("ROYALMAIL"), "Royal Mail", "royal mail")
    eq(worldoptions.shopify_carrier("EVRISEND"), "Evri", "evri")
    eq(worldoptions.shopify_carrier("DHLPARCEL"), "DHL", "dhl parcel")
    eq(worldoptions.shopify_carrier("UPS"), "UPS", "ups")
    # It used to pass an unknown code through. Shopify prints tracking_company
    # verbatim in the customer's shipping email, so a raw enum went to the customer.
    eq(worldoptions.shopify_carrier("SOMETHINGNEW"), "", "an unknown code is not a company name")

@test
def t_collection_option_envelope():
    worldoptions.set_credentials(meter="M1")
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        run(worldoptions.book({"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              {"postcode": "LS1 1AA", "country": "GB"}, {"postcode": "M1 2AB", "country": "GB"},
                              [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}],
                              ready_time="09:00", close_time="17:00",
                              collection_option="I_Have_Daily_Collection"))
        xml = holder["xml"]
        ok("<wo:CollectionOptions>I_Have_Daily_Collection</wo:CollectionOptions>" in xml, "collection option sent")
        ok(xml.index("CloseTime") < xml.index("CollectionOptions") < xml.index("ReadyTime"), "alphabetical in BillingDetail")
        # invalid values are dropped, not sent
        run(worldoptions.book({"service_type_code": "UPS_Standard", "package_type_code": "P", "carrier_name": "UPS"},
                              {"postcode": "a", "country": "GB"}, {"postcode": "b", "country": "GB"},
                              [{"width": 1, "length": 1, "depth": 1, "weight": 1}],
                              collection_option="Bogus_Value"))
        ok("CollectionOptions" not in holder["xml"], "bogus option dropped")
    finally:
        worldoptions._soap_call = saved

@test
def t_collection_option_config():
    r = post("/api/shipping/config", {"op": "set", "collection_option": "I_Have_Daily_Collection"})
    eq(r.status_code, 200, r.text)
    eq(r.json()["config"]["collection_option"], "I_Have_Daily_Collection", "persisted")
    ok("I_Am_Going_To_Drop_Off_My_Packages" in r.json()["config"]["collection_options"], "options listed for UI")
    r = post("/api/shipping/config", {"op": "set", "collection_option": "Nonsense"})
    eq(r.status_code, 400, "whitelist enforced")
    post("/api/shipping/config", {"op": "set", "collection_option": "I_Need_To_Book_A_Collection"})

@test
def t_currency_fallback_and_international():
    global ORDER
    saved_order = ORDER
    ORDER = {**ORDER, "currency": "SEK",
             "shipping_address": {**ORDER["shipping_address"], "country_code": "DE"}}
    try:
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": {"width": 20, "length": 15, "depth": 8, "weight": 0.6}})
        eq(r.status_code, 200, r.text)
        body = r.json()
        eq(body["international"], True, "non-GB flagged international")
        ok("SEK" in body["currency_note"], "currency fallback noted")
        eq(body["currency"], "GBP", "fell back to an accepted currency")
    finally:
        ORDER = saved_order

@test
def t_fulfillment_gets_mapped_carrier():
    reset_dispatch()
    FULFILLED.clear()
    async def cap(service, action, inner, retryable=True):
        return ET.fromstring(BOOK_XML.replace("UPS", "UPS"))
    # book with a Royal Mail option; fulfillment company must be "Royal Mail"
    reset_prod()
    opt = {"service_type_code": "RoyalMail_Tracked_24_Hours", "package_type_code": "RoyalMail_Parcel",
           "carrier_name": "ROYALMAIL", "service_name": "Tracked 24", "amount": 5.2}
    r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": {"width": 20, "length": 15, "depth": 8, "weight": 0.6}})
    eq(r.status_code, 200, r.text)
    mark_made()   # fulfilment happens here now
    eq(FULFILLED[-1]["company"], "Royal Mail", "Shopify-recognizable carrier name")

@test
def t_booking_never_retries():
    import httpx as _hx
    calls = {"n": 0}
    MODE = {"err": "connect"}
    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k):
            calls["n"] += 1
            if MODE["err"] == "connect": raise _hx.ConnectError("down")
            raise _hx.ReadTimeout("slow")   # request left the machine, reply lost
    saved_client = worldoptions.httpx.AsyncClient
    saved_soap = worldoptions._soap_call
    worldoptions.httpx.AsyncClient = FakeClient
    try:
        worldoptions._soap_call = REAL_SOAP_CALL
        worldoptions.set_credentials(meter="M1")
        # Connect error on a booking: nothing was sent, ONE attempt, safe message.
        MODE["err"] = "connect"; calls["n"] = 0
        try:
            run(worldoptions._soap_call("ShipmentService", "act", "<x/>", retryable=False))
            ok(False, "should raise")
        except worldoptions.WorldOptionsError as e:
            ok("nothing was booked" in str(e), "connect error -> nothing booked: " + str(e))
        eq(calls["n"], 1, "booking connect error: ONE attempt")
        # Post-send timeout on a booking: MAY have gone through, still ONE attempt, warn.
        MODE["err"] = "timeout"; calls["n"] = 0
        try:
            run(worldoptions._soap_call("ShipmentService", "act", "<x/>", retryable=False))
            ok(False, "should raise")
        except worldoptions.WorldOptionsError as e:
            ok("MAY still have gone through" in str(e), "read timeout -> double-charge warning")
        eq(calls["n"], 1, "booking timeout: ONE attempt")
        # A quote retries three times.
        MODE["err"] = "timeout"; calls["n"] = 0
        try:
            run(worldoptions._soap_call("RateService", "act", "<x/>", retryable=True))
        except worldoptions.WorldOptionsError:
            pass
        eq(calls["n"], 3, "quote: three attempts")
    finally:
        worldoptions.httpx.AsyncClient = saved_client
        worldoptions._soap_call = saved_soap

@test
def t_already_dispatched_guard():
    reset_dispatch()
    opt = {"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS", "amount": 12.4}
    box = {"width": 20, "length": 15, "depth": 8, "weight": 0.6}
    r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": box})
    eq(r.status_code, 200, "first booking ok")
    r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": box})
    eq(r.status_code, 400, "second booking refused")
    ok("already dispatched" in r.json()["error"], "explains")
    # force does NOT override a live dispatch record
    r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": box, "force": True})
    eq(r.status_code, 400, "force cannot override a live shipment")
    # after cancel, rebooking is allowed
    post("/api/dispatch/cancel", {"order_id": 12345, "tracking_number": "WO1234567890"})
    r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": box})
    eq(r.status_code, 200, "rebook after cancel allowed")

@test
def t_refunded_blocked():
    global ORDER
    saved = ORDER
    ORDER = {**ORDER, "financial_status": "refunded"}
    reset_dispatch()
    try:
        r = post("/api/dispatch/quote", {"order_id": 12345, "box": {"width": 20, "length": 15, "depth": 8, "weight": 0.6}})
        eq(r.status_code, 400, "quote refused")
        ok("refunded" in r.json()["error"], "quote message")
        r = post("/api/dispatch/book", {"order_id": 12345, "option": {"service_type_code": "UPS_Standard", "package_type_code": "P", "carrier_name": "UPS"}, "box": {"width": 20, "length": 15, "depth": 8, "weight": 0.6}})
        eq(r.status_code, 400, "book refused")
        ok("refunded" in r.json()["error"], "book message")
    finally:
        ORDER = saved

@test
def t_fulfilled_needs_force():
    global ORDER
    saved = ORDER
    ORDER = {**ORDER, "fulfillment_status": "fulfilled"}
    reset_dispatch()
    opt = {"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"}
    box = {"width": 20, "length": 15, "depth": 8, "weight": 0.6}
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": box})
        eq(r.status_code, 400, "fulfilled refused without force")
        eq(r.json().get("needs_force"), True, "needs_force flag")
        r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": box, "force": True})
        eq(r.status_code, 200, "force books")
    finally:
        ORDER = saved

@test
def t_cancel_unwinds_shopify():
    reset_dispatch()
    CANCELED_FULFILLMENTS.clear(); TAG_WRITES.clear()
    opt = {"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS", "amount": 12.4}
    box = {"width": 20, "length": 15, "depth": 8, "weight": 0.6}
    reset_prod()
    r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": box})
    eq(r.status_code, 200, "booked")
    mark_made()   # this is what fulfils
    st = json.load(open(SCRATCH + "/dispatch_state.json"))["orders"]["12345"]
    eq(st["fulfillment_id"], 555, "fulfillment id stored")
    TAG_WRITES.clear()
    global ORDER
    saved = ORDER
    ORDER = {**ORDER, "tags": "Dispatched"}   # what the order looks like after a real dispatch
    try:
        r = post("/api/dispatch/cancel", {"order_id": 12345, "tracking_number": "WO1234567890"})
    finally:
        ORDER = saved
    eq(r.status_code, 200, "cancel ok")
    eq(CANCELED_FULFILLMENTS, [555], "Shopify fulfillment cancelled")
    ok("re-dispatch" in (r.json().get("note") or ""), "note explains re-dispatch")
    ok(TAG_WRITES, "tags reverted")
    last = TAG_WRITES[-1][1].lower()
    ok("pc" in [t.strip() for t in last.split(",")], "back in To ship (PC)")
    ok("complete" not in last.lower(), "the finished tag is removed")

@test
def t_shipping_paid_in_shape():
    global ORDER
    saved = ORDER
    ORDER = {**ORDER, "shipping_lines": [{"title": "Standard Delivery", "price": "4.95"}]}
    try:
        res = run(production.run_production_labels({}, order_id=12345))
        sp = res["orders"][0].get("shipping_paid")
        eq(sp["title"], "Standard Delivery", "title")
        eq(sp["price"], "4.95", "price")
    finally:
        ORDER = saved

@test
def t_next_day_collection_enum():
    r = post("/api/shipping/config", {"op": "set", "collection_option": "I_Need_To_Book_A_Collection_For_Next_Day"})
    eq(r.status_code, 200, "next-day accepted")
    post("/api/shipping/config", {"op": "set", "collection_option": "I_Need_To_Book_A_Collection"})

@test
def t_breakdown_and_shops_parsed():
    worldoptions.set_credentials(meter="M1")
    res = run(worldoptions.quote({"postcode": "LS1 1AA", "country": "GB"},
                                 {"postcode": "M1 2AB", "country": "GB"},
                                 [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}]))
    op0 = res["options"][0]
    labels = [b["label"] for b in op0["breakdown"]]
    ok("Base charge" in labels, "base charge in breakdown: " + str(labels))
    ok("Fuel surcharge" in labels, "fuel in breakdown")
    ok(all(b["label"] != "Total net charge" for b in op0["breakdown"]), "total excluded")
    eq(op0["shops"][0]["id"], "PO123", "shop id")
    eq(op0["shops"][0]["street"], "12 High St", "houseno + street")
    ok("0.4" in op0["shops"][0]["distance"], "distance")

@test
def t_multibox_and_value_envelope():
    worldoptions.set_credentials(meter="M1")
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        run(worldoptions.book({"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              {"postcode": "LS1 1AA", "country": "GB"}, {"postcode": "M1 2AB", "country": "GB"},
                              [{"width": 20, "length": 15, "depth": 8, "weight": 0.6, "custom_value": 62.5},
                               {"width": 30, "length": 22, "depth": 15, "weight": 1.2, "custom_value": 62.5}]))
        xml = holder["xml"]
        eq(xml.count("<sd:wsShippingDetail.PackageDetail>"), 2, "two parcels")
        ok("<sd:ItemNumber>1</sd:ItemNumber>" in xml and "<sd:ItemNumber>2</sd:ItemNumber>" in xml, "item numbers")
        eq(xml.count("<sd:CustomValue>62.5</sd:CustomValue>"), 2, "declared value on both")
    finally:
        worldoptions._soap_call = saved

@test
def t_customs_envelope():
    worldoptions.set_credentials(meter="M1")
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    customs = {"eori": "GB123456789000", "vat": "GB999", "export_reason": "Sale",
               "duties_payor": "Duties_To_Be_Paid_By_Receiver", "trade_term": "DAP",
               "invoice_number": "#104239", "receiver_tax_id": "DE-TAX-1",
               "goods": [{"description": "Glass projection gobo", "quantity": 2, "unit_price": 62.5,
                          "hs": "70200080", "country": "GB"}],
               "total_value": 125.0}
    try:
        run(worldoptions.book({"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              {"postcode": "LS1 1AA", "country": "GB"}, {"postcode": "10115", "country": "DE", "city": "Berlin"},
                              [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}],
                              customs=customs, insurance="125.00", signature="UPS_Adult"))
        xml = holder["xml"]
        ok(xml.index("<wo:AdditionalShipmentDetail>") < xml.index("<wo:AuthenticationDetail>"), "customs FIRST in request")
        ok("<ad:EORINumber>GB123456789000</ad:EORINumber>" in xml, "EORI")
        ok("<ad:CommercialInvoiceType>Help_Me_Generate</ad:CommercialInvoiceType>" in xml, "invoice type default")
        ok("<ad:ExportReason>Sale</ad:ExportReason>" in xml, "export reason")
        ok("<ad:wsAddlShipmentDetail.GoodsDetail>" in xml, "goods line")
        g = xml[xml.index("<ad:wsAddlShipmentDetail.GoodsDetail>"):]
        ok(g.index("CountryCode") < g.index("Description") < g.index("HTSNumber") < g.index("ItemNumber")
           < g.index("Quantity") < g.index("UnitPrice") < g.index("<ad:Wt>") if "<ad:Wt>" in g else True, "goods field order")
        ok("<ad:TotalCustomValue>125</ad:TotalCustomValue>" in xml, "total value")
        ok("<wo:DutiesPayor>Duties_To_Be_Paid_By_Receiver</wo:DutiesPayor>" in xml, "duties in billing")
        ok("<wo:DeliverySignatureType>UPS_Adult</wo:DeliverySignatureType>" in xml, "signature in billing")
        ok("<sd:Insurance>125.00</sd:Insurance>" in xml, "insurance in shipping")
        ok("<sd:SenderVatNo>GB999</sd:SenderVatNo>" in xml, "sender VAT")
        ok("<ad:ReceiverTaxId>DE-TAX-1</ad:ReceiverTaxId>" in xml, "receiver tax id")
    finally:
        worldoptions._soap_call = saved

@test
def t_dropoff_envelope():
    worldoptions.set_credentials(meter="M1")
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        run(worldoptions.book({"service_type_code": "Evri_DI_Ship_to_Shop_UK", "package_type_code": "Evri_Parcel", "carrier_name": "EVRISEND"},
                              {"postcode": "LS1 1AA", "country": "GB"}, {"postcode": "M1 2AB", "country": "GB"},
                              [{"width": 20, "length": 15, "depth": 8, "weight": 0.6}],
                              dropoff_shop={"id": "PO123", "name": "Post Office Central", "street": "12 High St",
                                            "city": "Leeds", "postcode": "LS1 2AB"}))
        xml = holder["xml"]
        ok("<sd:CollectionDropOffInfo>" in xml, "dropoff info block")
        ok("<sd:DropOffId>PO123</sd:DropOffId>" in xml, "shop id")
        ok("<sd:IsCollectionDropoffRequired>true</sd:IsCollectionDropoffRequired>" in xml, "dropoff flag")
        ok(xml.index("CollectionDropOffInfo") < xml.index("<sd:CollectionType>"), "XSD order: dropoff first")
        # bogus signature is dropped silently
        run(worldoptions.book({"service_type_code": "UPS_Standard", "package_type_code": "P", "carrier_name": "UPS"},
                              {"postcode": "a", "country": "GB"}, {"postcode": "b", "country": "GB"},
                              [{"width": 1, "length": 1, "depth": 1, "weight": 1}], signature="Bogus_Sig"))
        ok("DeliverySignatureType" not in holder["xml"], "bogus signature dropped")
    finally:
        worldoptions._soap_call = saved

@test
def t_quote_insurance_dropoff_envelope():
    worldoptions.set_credentials(meter="M1")
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(RATE_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        run(worldoptions.quote({"postcode": "LS1 1AA", "country": "GB"}, {"postcode": "M1 2AB", "country": "GB"},
                               [{"width": 20, "length": 15, "depth": 8, "weight": 0.6, "custom_value": 100}],
                               insurance="150.00", collection_dropoff=True))
        xml = holder["xml"]
        ok("<rs:Insurance>150.00</rs:Insurance>" in xml, "insurance in quote")
        ok("<rs:IsCollectionDropoffRequired>true</rs:IsCollectionDropoffRequired>" in xml, "dropoff flag in quote")
        ok(xml.index("<rs:Insurance>") < xml.index("<rs:IsCollectionDropoffRequired>") < xml.index("<rs:PackageDetails>"), "quote XSD order")
        ok("<rs:CustomValue>100</rs:CustomValue>" in xml, "quote declared value")
    finally:
        worldoptions._soap_call = saved

@test
def t_multibox_route():
    reset_dispatch()
    r = post("/api/dispatch/quote", {"order_id": 12345, "boxes": [
        {"width": 20, "length": 15, "depth": 8, "weight": 0.6},
        {"width": 30, "length": 22, "depth": 15, "weight": 1.2}]})
    eq(r.status_code, 200, r.text)
    eq(r.json()["boxes"], 2, "two boxes quoted")
    eq(r.json()["weight"], 1.8, "summed weight")
    r = post("/api/dispatch/quote", {"order_id": 12345, "boxes": [{"width": 0, "length": 1, "depth": 1, "weight": 1}, {"width": 1, "length": 1, "depth": 1, "weight": 1}]})
    eq(r.status_code, 400, "bad box in list rejected")
    ok("Box 1" in r.json()["error"], "names the bad box")

@test
def t_intl_booking_requires_customs():
    global ORDER
    saved = ORDER
    ORDER = {**ORDER, "shipping_address": {**ORDER["shipping_address"], "country_code": "DE"},
             "line_items": [{"title": "Custom Gobo", "quantity": 2, "grams": 250, "product_id": 1,
                             "variant_title": "", "price": "62.50"}]}
    reset_dispatch()
    post("/api/shipping/config", {"op": "set", "eori": ""})
    opt = {"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"}
    box = {"width": 20, "length": 15, "depth": 8, "weight": 0.6}
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": box})
        eq(r.status_code, 400, "no EORI -> refused")
        ok("EORI" in r.json()["error"], "explains EORI")
        post("/api/shipping/config", {"op": "set", "eori": "GB123456789000"})
        r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": box})
        eq(r.status_code, 400, "no goods lines -> refused")
        ok("customs" in r.json()["error"].lower(), "explains goods")
        holder = {}
        async def cap(service, action, inner, retryable=True):
            holder["xml"] = inner; return ET.fromstring(BOOK_XML)
        saved_soap = worldoptions._soap_call; worldoptions._soap_call = cap
        try:
            r = post("/api/dispatch/book", {"order_id": 12345, "option": opt, "box": box,
                "customs": {"lines": [{"description": "Glass gobo", "quantity": 2, "unit_price": 62.5, "hs": "70200080"}]}})
            eq(r.status_code, 200, r.text)
            eq(r.json()["international"], True, "flagged international")
            ok("<ad:EORINumber>GB123456789000</ad:EORINumber>" in holder["xml"], "EORI from settings")
            ok("<ad:TotalCustomValue>125</ad:TotalCustomValue>" in holder["xml"], "total from lines")
            ok("<sd:CustomValue>125</sd:CustomValue>" in holder["xml"], "declared value from order items")
        finally:
            worldoptions._soap_call = saved_soap
    finally:
        ORDER = saved
        post("/api/shipping/config", {"op": "set", "eori": ""})

@test
def t_config_intl_fields():
    r = post("/api/shipping/config", {"op": "set", "eori": "GB1", "vat_number": "GB2", "default_hs_code": "700200",
                                      "export_reason": "Sale", "duties_payor": "Duties_To_Be_Paid_By_Sender", "trade_term": "DAP"})
    eq(r.status_code, 200, r.text)
    cfgj = r.json()["config"]
    eq(cfgj["eori"], "GB1", "eori")
    eq(cfgj["duties_payor"], "Duties_To_Be_Paid_By_Sender", "duties")
    ok("UPS" in cfgj["signature_options"], "signature groups exposed")
    r = post("/api/shipping/config", {"op": "set", "export_reason": "Nonsense"})
    eq(r.status_code, 400, "bad export reason rejected")
    post("/api/shipping/config", {"op": "set", "eori": "", "duties_payor": "Duties_To_Be_Paid_By_Receiver"})

@test
def t_carrier_enum_canonical():
    eq(worldoptions.canonical_carrier("palletways"), "Palletways", "case-normalized")
    eq(worldoptions.canonical_carrier("EXFREIGHT"), "EXFreight", "exfreight casing")
    eq(worldoptions.canonical_carrier("evri"), "", "bare Evri is not a member")
    eq(worldoptions.canonical_carrier("EVRISEND"), "EVRISEND", "evrisend ok")
    # _carrier_from maps an Evri_* service code to EVRISEND
    eq(worldoptions._carrier_from("Evri_DI_Ship_to_Shop_UK", ""), "EVRISEND", "evri prefix -> EVRISEND")
    eq(worldoptions._carrier_from("PALLETWAYS_Std", ""), "Palletways", "palletways prefix canonical")

@test
def t_book_omits_invalid_enums():
    worldoptions.set_credentials(meter="M1")
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        # rate-only package type + carrier that only prefix-resolves
        run(worldoptions.book({"service_type_code": "Evri_DI_Ship_to_Shop_UK", "package_type_code": "Any_NonDocument", "carrier_name": "EVRI"},
                              {"postcode": "a", "country": "GB"}, {"postcode": "b", "country": "GB"},
                              [{"width": 1, "length": 1, "depth": 1, "weight": 1}]))
        xml = holder["xml"]
        ok("<sd:ServiceType>EVRISEND</sd:ServiceType>" in xml, "carrier canonicalized to EVRISEND")
        # It used to be omitted. PackageTypeCode is a NON-NILLABLE enum, so omitting
        # it does not send nothing: WCF substitutes the first member, Fedex_Box, on
        # an Evri booking. The carrier's own packaging is sent instead.
        ok("<sd:PackageTypeCode>Evri_Parcel</sd:PackageTypeCode>" in xml,
           "rate-only package type replaced with the carrier's own, not left to default")
        # a valid package type IS sent
        run(worldoptions.book({"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                              {"postcode": "a", "country": "GB"}, {"postcode": "b", "country": "GB"},
                              [{"width": 1, "length": 1, "depth": 1, "weight": 1}]))
        ok("<sd:PackageTypeCode>UPS_My_Packaging</sd:PackageTypeCode>" in holder["xml"], "valid package type kept")
    finally:
        worldoptions._soap_call = saved

@test
def t_export_type_from_reason():
    worldoptions.set_credentials(meter="M1")
    holder = {}
    async def cap(service, action, inner, retryable=True):
        holder["xml"] = inner; return ET.fromstring(BOOK_XML)
    saved = worldoptions._soap_call; worldoptions._soap_call = cap
    try:
        for reason, want in [("Repair", "Temporary"), ("Return", "Re_export"), ("Sale", "Permanent")]:
            run(worldoptions.book({"service_type_code": "UPS_Express", "package_type_code": "UPS_My_Packaging", "carrier_name": "UPS"},
                                  {"postcode": "a", "country": "GB"}, {"postcode": "b", "country": "DE"},
                                  [{"width": 1, "length": 1, "depth": 1, "weight": 1}],
                                  customs={"eori": "GB1", "export_reason": reason,
                                           "goods": [{"description": "x", "quantity": 1, "unit_price": 5}], "total_value": 5}))
            ok("<ad:ExportType>" + want + "</ad:ExportType>" in holder["xml"], f"{reason}->{want}")
    finally:
        worldoptions._soap_call = saved

@test
def t_label_types_png_and_unknown():
    def cls(lt):
        return worldoptions._classify_label(ET.fromstring(
            "<ShippingLabel><Image>QUJD</Image><LabelType>" + lt + "</LabelType></ShippingLabel>"))
    eq(cls("PNG")["type"], "base64png", "png")
    eq(cls("PDF")["type"], "base64pdf", "pdf")
    eq(cls("ZPL")["type"], "base64bin", "zpl -> bin, not fake pdf")
    eq(cls("")["type"], "base64pdf", "empty -> pdf default")

@test
def t_spread_value_remainder():
    boxes = desk._spread_value([{}, {}, {}], 100.0)
    vals = [b["custom_value"] for b in boxes]
    eq(round(sum(vals), 2), 100.0, "spread sums to total")
    eq(vals[-1], round(100.0 - round(100/3, 2) * 2, 2), "remainder on last box")

@test
def t_one_bad_price_does_not_zero_order():
    o = {"line_items": [{"title": "A", "quantity": 2, "price": "62.50"},
                        {"title": "B", "quantity": 1, "price": "not-a-number"},
                        {"title": "C", "quantity": 3, "price": "10.00"}]}
    eq(desk._order_goods_value(o), 155.0, "bad line skipped, others counted")

