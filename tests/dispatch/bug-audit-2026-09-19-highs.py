# ---------------------------------------------------------------------------
# The 2026-09-19 bug audit (docs/bugs/2026-09-19-bug-audit.md): the highs and
# the pattern fixes, each pinned by the behaviour that was wrong.
# ---------------------------------------------------------------------------

@test
def t_boot_reseal_reads_the_register_as_the_app_writes_it():
    """B3. users.json is {"users_store": {...}}; the re-seal read "users" off
    the top level, found nothing, and reported the vault complete while every
    second-factor secret enrolled before the key was set stayed in plaintext
    on the volume and in every backup zip."""
    import tokenvault as _tv
    def go():
        old_key = os.environ.get("TOKEN_ENCRYPTION_KEY")
        os.environ["TOKEN_ENCRYPTION_KEY"] = "a-long-random-key-for-the-test"
        _tv._key.cache_clear()
        try:
            team._write_users({"version": 2, "users": {
                "u1": {"name": "Ada", "username": "ada", "role": "master",
                       "mfa_secret": "PLAINSECRET"}}})
            eq(json.load(open(team.USERS_PATH))["users_store"]["users"]["u1"]["mfa_secret"],
               "PLAINSECRET", "enrolled before the key: plaintext on disk")
            out = appstatus.reseal_secrets_at_rest()
            eq(out["stores"].get("mfa"), 1, out)
            on_disk = json.load(open(team.USERS_PATH))["users_store"]["users"]["u1"]["mfa_secret"]
            ok(_tv.is_sealed(on_disk), "sealed on disk")
            eq(_tv.unseal(on_disk), "PLAINSECRET", "and still opens, so nobody is locked out")
            eq(appstatus.token_vault_state()["plaintext"], [], "and the settings panel agrees")
        finally:
            if old_key is None:
                os.environ.pop("TOKEN_ENCRYPTION_KEY", None)
            else:
                os.environ["TOKEN_ENCRYPTION_KEY"] = old_key
            _tv._key.cache_clear()
    with_accounts(go)


@test
def t_the_watchdog_clears_the_outage_flag_when_shopify_is_back():
    """B1. The tick popped shopify_down from its snapshot and then merged the
    snapshot over the file, which kept the key: a recovered email every hour,
    the between-hours answer "down", scheduled audits skipped three ticks in
    four, for as long as the volume lasted."""
    emails = []
    up = {"v": False}
    async def probe(registry, name, args):
        return {"name": "Shop"} if up["v"] else {"error": "boom"}
    async def alert(subject, lines):
        # The same tick also checks the team register, which this test does
        # not seed; only the connection emails are the point here.
        if "Shopify" in subject:
            emails.append(subject)
        return True
    async def noop(*a, **k):
        return None
    async def skip(*a, **k):
        return {"error": "skip"}
    saved = (shopify._tool_json, scheduler._send_alert_email, copilot._zeta_drain,
             copilot._zeta_configured, fileserver._files_tick, production.run_label_coverage,
             shopify._webhook_ensurer, scheduler._watch_last_tick)
    shopify._tool_json, scheduler._send_alert_email = probe, alert
    copilot._zeta_drain, copilot._zeta_configured = noop, (lambda: False)
    fileserver._files_tick, production.run_label_coverage, shopify._webhook_ensurer = (lambda: None), skip, None
    def clean():
        w = scheduler._load_watch()
        w.pop("shopify_down", None)
        w["probe_fails"] = 0
        scheduler._save_watch(w)
    def tick():
        scheduler._watch_last_tick = 0.0
        return run_async(scheduler._watchdog_tick({}))
    clean()
    try:
        for _ in range(3):
            tick()
        ok(scheduler._load_watch().get("shopify_down"), "three hourly failures flag the outage")
        eq(emails, ["Reactor: Shopify connection is failing"])
        up["v"] = True
        ok(tick(), "the probe succeeds")
        eq(scheduler._load_watch().get("shopify_down"), None, "and the flag is gone from disk")
        eq(emails[-1], "Reactor: Shopify connection recovered")
        tick()
        eq(emails.count("Reactor: Shopify connection recovered"), 1, "said once, not every hour")
        scheduler._watch_last_tick = time.time()
        ok(run_async(scheduler._watchdog_tick({})), "the between-hours answer is up too")
    finally:
        (shopify._tool_json, scheduler._send_alert_email, copilot._zeta_drain,
         copilot._zeta_configured, fileserver._files_tick, production.run_label_coverage,
         shopify._webhook_ensurer, scheduler._watch_last_tick) = saved
        clean()


@test
def t_shop_redact_erases_what_memory_holds_too():
    """B2. The files went and the memory copies stayed: _load_mail() kept
    serving the erased threads and the mail loop's next write put the whole
    mailbox back on disk inside a minute, Files likewise on its next tick."""
    def go():
        _gm.save_connection("rt-test", MBOX)
        m = mail._load_mail()
        m["threads"]["t1"] = {"from_email": "someone@example.com", "subject": "private"}
        mail._write_mail(m)
        f = fileserver._load_files()
        f["files"]["f1"] = {"name": "secret.pdf", "status": "active"}
        fileserver._write_files(f)
        r = privacy._redact_shop()
        ok(r["wiped"] >= 2, r)
        eq(mail._load_mail()["threads"], {}, "the erased threads are not served from memory")
        eq(fileserver._load_files()["files"], {}, "nor the erased files")
        ok(not _gm.connected(), "and the mailbox grant is gone, so the sync cannot rebuild the store from Gmail")
        mail._write_mail(mail._load_mail())       # what the mail loop does every minute
        fileserver._write_files(fileserver._load_files())
        eq(json.load(open(mail.MAILBOX_PATH))["mailbox"]["threads"], {},
           "and a write cannot bring them back")
        eq(json.load(open(fileserver.FILES_PATH))["files_store"]["files"], {})
    with_files(lambda fake: with_mail(go))


@test
def t_every_memory_copy_of_a_store_is_let_go():
    """Restore and shop/redact let go of every whole-store copy held in memory
    (a copy that outlives its file puts the old contents straight back: the
    mailbox and Files after a redact, the loan register after a restore). Each
    module registers with the store how to let go of its own, so nothing
    reaches into another module's names, and a `_mem` copy nobody lets go of
    fails here. Paths are read when the drop runs."""
    import importlib
    held = []
    for rel in COPILOT_FILES:
        mod = importlib.import_module(rel[:-3].replace("/", "."))
        text = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), rel), encoding="utf-8").read()
        held += [(mod, n) for n in re.findall(r"^(_[a-z_]+_mem)\b", text, re.M)]
    ok(len(held) >= 7, "the scan finds the copies (%d)" % len(held))
    saved = [(m, n, getattr(m, n)) for m, n in held]
    path = team.USERS_PATH
    mark = object()
    try:
        for m, n in held:
            setattr(m, n, mark)
        jsonstore._drop_memory_stores()
        eq(["%s.%s" % (m.__name__, n) for m, n in held if getattr(m, n) is not None], [], "every copy let go")
        for m, n in held:
            setattr(m, n, mark)
        team.USERS_PATH = os.path.join(SCRATCH, "users-elsewhere.json")
        jsonstore._drop_memory_stores({team.USERS_PATH})
        eq(["%s.%s" % (m.__name__, n) for m, n in held if getattr(m, n) is None], ["gizmo.team._users_mem"],
           "a drop naming one store lets go of that one only, at the path it has now")
    finally:
        team.USERS_PATH = path
        for m, n, v in saved:
            setattr(m, n, v)


@test
def t_restore_reaches_the_loan_register():
    """B9. Restore dropped every memory copy but the loan register's, so the
    Loans tab kept showing the pre-restore units and the next loan wrote
    them over the restored file."""
    def go():
        ensure_auth()
        import base64 as b64
        d = loans._load_loans()
        d["units"]["u1"] = {"name": "Loan 1", "created_at": "2026-09-01T00:00:00+00:00"}
        loans._write_loans(d)
        buf, _added = backup._build_backup_zip()
        blob = b64.b64encode(buf.getvalue()).decode()
        d = loans._load_loans()
        d["units"].pop("u1")
        d["units"]["u2"] = {"name": "Loan 2", "created_at": "2026-09-02T00:00:00+00:00"}
        loans._write_loans(d)
        rr = post("/api/restore", {"zip": blob})
        eq(rr.status_code, 200, rr.text)
        li = login("cameron", MASTER_PW)          # every session died with the restore
        APP_AUTH["session"], APP_AUTH["master"] = li.json()["session"], li.json()["me"]["id"]
        eq(sorted(loans._load_loans()["units"]), ["u1"], "the restored register is what is served")
        loans._write_loans(loans._load_loans())
        eq(sorted(json.load(open(loans.LOANS_PATH))["loans_store"]["units"]), ["u1"],
           "and the next write keeps it")
    def outer():
        loans._loans_mem = None
        try:
            os.remove(loans.LOANS_PATH)
        except FileNotFoundError:
            pass
        try:
            go()
        finally:
            loans._loans_mem = None
            try:
                os.remove(loans.LOANS_PATH)
            except FileNotFoundError:
                pass
    with_accounts(outer)


@test
def t_a_pipedrive_preview_leaves_the_live_crm_alone():
    """B6. The preview ran the import on the cached store itself, updating
    every existing deal in place; over a partial export that blanked the
    contact off each one, and the next unrelated CRM write put it on disk."""
    def go():
        ensure_auth()
        crm_wipe()
        async def full(progress=None):
            return dict(PD_EXPORT)
        async def partial(progress=None):
            bad = dict(PD_EXPORT)
            bad["persons"] = []
            bad["complete"] = dict(PD_EXPORT["complete"], persons=False)
            return bad
        saved = (pipedrive.export, pipedrive.API_TOKEN)
        pipedrive.export, pipedrive.API_TOKEN = full, "t"
        try:
            eq(post("/api/crm/import", {"go": True}).status_code, 200)
            def links():
                return {k: (v.get("person_id"), v.get("org_id"), v.get("stage_id"))
                        for k, v in salesdesk._load_crm()["deals"].items()}
            before = links()
            ok(all(p for p, _o, _s in before.values()), "the imported deals have their people")
            pipedrive.export = partial
            r = post("/api/crm/import", {})
            eq(r.status_code, 200, r.text)
            ok(r.json()["dry_run"])
            eq(links(), before, "a preview changes nothing the board reads")
            post("/api/crm/contact", {"op": "org_add", "name": "Unrelated write"})
            disk = json.load(open(salesdesk.CRM_PATH))["crm"]["deals"]
            eq({k: (v.get("person_id"), v.get("org_id"), v.get("stage_id")) for k, v in disk.items()},
               before, "and the write that followed carried the real links, not the preview's")
        finally:
            pipedrive.export, pipedrive.API_TOKEN = saved
    with_accounts(go)


@test
def t_a_send_whose_answer_is_lost_keeps_its_stamp():
    """B5. A timeout after the upload left the machine was handled like a
    refusal: stamp cleared, "did not send", Send re-armed, and the retry gave
    the customer the same reply twice. Now the stamp stays and the person is
    told to look before sending again. A reply Gmail filed elsewhere is a
    SENT reply with a note, not a refusal."""
    import httpx as _hx
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        async def lost(thread_id, to_addr, subject, body_text, **kw):
            raise _hx.ReadTimeout("no answer")
        saved = (_gm.read_thread, _gm.send_message)
        _gm.read_thread, _gm.send_message = _one_from_customer(), lost
        try:
            r = post("/api/mail/send", {"id": "t1", "text": "Hello Jo."})
            eq(r.status_code, 502, r.text)
            ok("MAY have been sent" in r.json()["error"], r.text)
            t = mail._load_mail()["threads"]["t1"]
            eq(t.get("sent_at"), None, "not claimed as sent either")
            ok(t.get("send_pending"), "the stamp stays: we do not know")
            disk = json.load(open(mail.MAILBOX_PATH))["mailbox"]
            ok(disk["threads"]["t1"].get("send_pending"), "on disk too")
            ok(any("may not have completed" in a["action"] for a in t["activity"]), str(t["activity"]))
            # The sync then finds our message in Gmail, dated after the stamp:
            # that settles it, without anyone pressing anything.
            store = mail._load_mail()
            mail._mail_apply_thread(store, {"id": "t1", "historyId": "h9", "subject": "Gobo order",
                "messages": [_mk_msg("t1-m1", "Jo Bloggs", "jo@customer.com", "2026-08-19T01:00:00+00:00"),
                             _mk_msg("t1-m2", "Sales", MBOX, mail._mail_now())]}, MBOX)
            t = store["threads"]["t1"]
            eq(t.get("send_pending"), None, "Gmail has the reply, so the stamp is settled")
            ok(t.get("sent_at"), "and it is recorded as sent")
            eq(t["state"], "waiting")
            ok("confirmed from Gmail" in json.dumps(t["activity"]), str(t["activity"]))
            # No connection at all is a definite failure: nothing left the machine.
            async def unreachable(thread_id, to_addr, subject, body_text, **kw):
                raise _hx.ConnectError("down")
            _gm.send_message = unreachable
            r3 = post("/api/mail/send", {"id": "t1", "text": "Hello?"})
            eq(r3.status_code, 502, r3.text)
            ok("nothing was sent" in r3.json()["error"], r3.text)
            eq(mail._load_mail()["threads"]["t1"].get("send_pending"), None, "no connection, no stamp")
            async def misfiled(thread_id, to_addr, subject, body_text, **kw):
                return {"id": "m9", "thread_id": "other", "misfiled": True}
            _gm.send_message = misfiled
            r2 = post("/api/mail/send", {"id": "t1", "text": "Hello again."})
            eq(r2.status_code, 200, r2.text)
            ok("filed it as a new conversation" in r2.json().get("warning", ""), r2.text)
            t = mail._load_mail()["threads"]["t1"]
            ok(t.get("sent_at"), "recorded as sent")
            eq(t.get("send_pending"), None)
        finally:
            _gm.read_thread, _gm.send_message = saved
    with_mail(go)


@test
def t_the_payroll_sheet_and_the_work_board_reckon_days_in_london():
    """B10. Sessions are stamped in UTC and the sheet sliced the stamp, so
    every summer shift read an hour early and one after 23:00 fell on the
    day before; the board's today, week and month began at 01:00."""
    rows = [{"id": "w1", "uid": "u1", "start": "2026-07-01T08:30:00+00:00",
             "end": "2026-07-01T12:00:00+00:00", "secs": 12600},
            {"id": "w2", "uid": "u1", "start": "2026-06-30T23:30:00+00:00",
             "end": "2026-07-01T01:00:00+00:00", "secs": 5400}]
    csv = work._work_csv(rows, {"u1": "Pat"}, {"w1": 2}).split("\n")
    eq(csv[1], "Pat,2026-07-01,09:30,13:00,3.50,2,")
    eq(csv[2], "Pat,2026-07-01,00:30,02:00,1.50,0,", "half past midnight in London, not the 30th")
    eq(clock._london_day("2026-06-30T23:30:00+00:00"), "2026-07-01")
    eq(clock._london_day("2026-01-31T23:30:00+00:00"), "2026-01-31", "and nothing moves in winter")
    today, week, month = work._day_starts()
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _Z
    eq(_dt.fromisoformat(today).astimezone(_Z("Europe/London")).strftime("%H:%M"), "00:00",
       "today starts at London midnight")
    ok(today.endswith("+00:00") and week <= today and month <= today,
       "expressed in UTC, like the sessions it is compared with")


@test
def t_a_label_reckons_required_by_where_the_bench_is():
    """B35. due_soon compared the customer's date with the UTC date, which
    is yesterday's for the last hour of every summer day: a wedding three
    days off printed without its urgency box."""
    from datetime import date as _date
    saved = clock._london_today
    clock._london_today = lambda: _date(2026, 9, 19)
    try:
        o = dict(ORDER, line_items=[{"title": "Custom Gobo", "quantity": 1, "product_id": 1,
                                     "properties": [{"name": "Date Required", "value": "21/09/2026"}]}])
        eq(production._shape_label_order(o, {})["due_soon"], True, "two days away is soon")
        o["line_items"][0]["properties"][0]["value"] = "22/09/2026"
        eq(production._shape_label_order(o, {})["due_soon"], False)
        eq(orderbook._fmt_due(_date(2026, 12, 25)), "25 Dec")
        eq(orderbook._fmt_due(_date(2027, 1, 2)), "2 Jan 2027")
        eq(loans._loan_state({"due_at": "2026-09-19"}, 14), "ok", "a loan due today is not late yet")
        eq(loans._loan_state({"due_at": "2026-09-18"}, 14), "late")
    finally:
        clock._london_today = saved


@test
def t_a_refunded_line_is_not_made_weighed_or_declared():
    """B4. quantity is what was ORDERED; a refund or an order edit lowers
    current_quantity and leaves it alone, so the refunded gobo printed, was
    cut, booked its glass and rode on the customs declaration."""
    o = dict(ORDER, line_items=[
        {"title": "Custom Gobo", "quantity": 2, "current_quantity": 1, "price": "127.50",
         "grams": 75, "product_id": 1},
        {"title": "Custom Gobo", "quantity": 1, "current_quantity": 0, "price": "127.50",
         "grams": 75, "product_id": 1},
        {"title": "Custom Gobo", "quantity": 3, "price": "10.00", "grams": 10, "product_id": 1}])
    shaped = production._shape_label_order(o, {})
    eq([it["quantity"] for it in shaped["items"]], [1, 3],
       "the refunded line is gone; a line Shopify never edited keeps its ordered count")
    eq(desk._order_goods_value(o), 157.5, "declared at what is still on the order")
    eq(orderbook._order_weight_kg(o), 0.105)
    eq([c["quantity"] for c in run_async(desk._customs_items({}, o))], [1, 3])
    eq(orderbook._line_qty({"quantity": 2}), 2)
    eq(orderbook._line_qty({}), 1, "a line with no quantity at all counts as one, as before")


@test
def t_a_corrupt_note_or_skill_file_pauses_its_writer_by_itself():
    """B8. The four hand-rolled loaders returned an empty default on any
    error and never marked the path poisoned, so _store_writable said yes and
    the first save after a corruption replaced the merchant's notes, skills,
    profile or knowledge with the default plus the new item."""
    for owner, path_attr, loader, writer, payload in (
            (memory, "MEMORY_PATH", memory._load_memory, memory._write_memory, [{"text": "x"}]),
            (skillbook, "SKILLS_PATH", skillbook._load_skills, skillbook._write_skills, [{"title": "x", "body": "y"}])):
        path = getattr(owner, path_attr)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{ this is not json")
        jsonstore._poisoned_stores.discard(path)
        eq(loader(), [], "an unreadable file reads as empty")
        ok(path in jsonstore._poisoned_stores, path_attr + " is paused by its own loader")
        writer(payload)
        ok("not json" in open(path, encoding="utf-8").read(), "and preserved for repair, not overwritten")
        jsonstore._poisoned_stores.discard(path)
        os.remove(path)
    for owner, path_attr, loader in ((store_profile, "PROFILE_PATH", store_profile._load_profile),
                                     (knowledge, "KNOWLEDGE_PATH", knowledge._load_knowledge)):
        path = getattr(owner, path_attr)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{ nope")
        jsonstore._poisoned_stores.discard(path)
        eq(loader(), {})
        ok(path in jsonstore._poisoned_stores, path_attr + " is paused by its own loader")
        jsonstore._poisoned_stores.discard(path)
        os.remove(path)


@test
def t_a_crown_dependency_postcode_is_not_read_as_great_britain():
    """B12. JE, GY and IM postcodes have the GB shape, and a paste with no
    country line was read as GB, confidently, so a Jersey parcel went
    domestic with no customs declaration."""
    for text, country in (("Jane Doe\n5 Rue de Paris\nSt Helier\nJersey\nJE2 3AB", "JE"),
                          ("A Person\n1 High St\nSt Peter Port\nGY1 1AA", "GG"),
                          ("Bob\nUnit 3\nDouglas\nIM1 1AA", "IM")):
        r = desk._parse_address(text)
        eq(r["address"]["country"], country, text)
        eq(r["confident"], False, "an island address gets a look: customs applies")
    r = desk._parse_address("Some Person, 1200 Kingston Road, Manchester, M1 2AB")
    eq(r["address"]["country"], "GB")
    eq(r["confident"], True, "and the common paste still lands without a round trip")


@test
def t_declared_value_and_customs_prices_are_net_of_discounts():
    """B13. Shopify's line price is before discounts; the discount sits in
    discount_allocations. The declared value, the insurance basis and the
    customs unit prices all read the list price, so a trade customer paid
    duty at the border on money they never spent."""
    o = dict(ORDER, line_items=[
        {"title": "Custom Gobo", "quantity": 2, "price": "100.00", "grams": 75, "product_id": 1,
         "discount_allocations": [{"amount": "40.00"}]},
        {"title": "Custom Gobo", "quantity": 1, "price": "50.00", "product_id": 1}])
    eq(desk._order_goods_value(o), 210.0, "list 250 less the 40 taken off")
    items = run_async(desk._customs_items({}, o))
    eq([i["price"] for i in items], ["80.00", "50.00"], "the unit price the customer paid")
    eq([i["unit_value"] for i in items], ["80.00", "50.00"], "is what a gobo is declared at")
    o["line_items"][0]["current_quantity"] = 1       # one of the two refunded since
    eq(desk._order_goods_value(o), 130.0, "the discount is per unit ordered, times what is left")
    # The per-product memory is for gobos whose base price is zero (priced
    # through options), where the operator typed the value. A gobo with a real
    # sale price is declared at THIS customer's price, never at a value
    # remembered from another order.
    key = desk._customs_key(o["line_items"][1], "Custom Gobo")
    saved = desk._load_customs_memory
    desk._load_customs_memory = lambda: {key: {"unit_value": "37.50", "hs": "", "origin": ""}}
    try:
        items = run_async(desk._customs_items({}, o))
        eq(items[1]["unit_value"], "50.00", "the priced gobo ignores the memory")
        o["line_items"][1]["price"] = "0.00"
        items = run_async(desk._customs_items({}, o))
        eq(items[1]["unit_value"], "37.50", "the option-priced gobo takes what was typed last time")
    finally:
        desk._load_customs_memory = saved


@test
def t_the_margin_report_reaches_an_order_dispatched_weeks_after_it_was_placed():
    """B14. The report picked dispatch records inside the window but only
    fetched orders CREATED within it plus two weeks, so a purchase-order job
    that sat three weeks in proofing was reported as a Shopify load failure
    and dropped from the totals."""
    from datetime import datetime as _dt, timezone as _tz
    reset_dispatch(); reset_prod()
    old = {"id": 777, "name": "#777", "currency": "GBP", "created_at": "2026-05-01T10:00:00Z",
           "taxes_included": False, "total_price": "100.00",
           "line_items": [{"id": 1, "title": "Gobo", "quantity": 1, "price": "100.00", "variant_id": 111}],
           "shipping_lines": []}
    desk._record_dispatch(777, {"tracking_number": "T7", "carrier_name": "UPS", "order_name": "#777",
                                   "amount_ex_vat": 8.0, "amount": 9.6,
                                   "dispatched_at": _dt.now(_tz.utc).isoformat()})
    async def tools(registry, name, args):
        if name == "shopify_list_orders":
            return {"orders": []}                    # placed long before the snapshot's window
        if name == "shopify_get_order" and int(args.get("order_id") or 0) == 777:
            return dict(old)
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
        res = run_async(desk.run_margin_report({}, days=30))
        row = next(r for r in res["rows"] if str(r.get("order_id")) == "777")
        ok("incomplete" not in row, "fetched on its own, not reported as a load failure: " + json.dumps(row)[:200])
        eq(row["revenue"], 100.0)
        eq(row["goods_cost"], 30.0)
    finally:
        shopify._tool_json = saved
        reset_dispatch()


@test
def t_reprinting_a_made_orders_label_is_not_a_release():
    """B15. The printed op moved every id it was sent Unprocessed -> IP and
    re-ran the Net-30 attach, and the page stamps every print, so a damaged
    label reprinted from To ship put a made order back into To make beside
    its PC tag."""
    reset_dispatch(); reset_prod()
    mark_made(12345, True)
    TAG_WRITES.clear()
    r = post("/api/production-state", {"op": "printed", "ids": [12345]})
    eq(r.status_code, 200, r.text)
    eq([w for w in TAG_WRITES if w[0] == 12345], [], "no IP tag goes back on a made order")
    reset_prod()
    async def pc(registry, name, args):
        if name == "shopify_get_order":
            return dict(ORDER, tags="PC, purchase order unpaid")
        return await fake_tool_json(registry, name, args)
    terms_calls = []
    async def terms(order_id):
        terms_calls.append(int(order_id))
        return {"ok": True, "already": True, "name": "Net 30"}
    saved = (shopify._tool_json, shopify._payment_terms_writer)
    shopify._tool_json, shopify._payment_terms_writer = pc, terms
    try:
        r = post("/api/production-state", {"op": "printed", "ids": [12345]})
        eq(r.status_code, 200, r.text)
        eq([w for w in TAG_WRITES if w[0] == 12345], [],
           "nor on one Shopify shows as made with no stamp here")
        eq(terms_calls, [], "and the Net-30 attach does not run again for it either")
        async def fresh(registry, name, args):
            if name == "shopify_get_order":
                return dict(ORDER, tags="Unprocessed, purchase order unpaid")
            return await fake_tool_json(registry, name, args)
        shopify._tool_json = fresh
        TAG_WRITES.clear()
        r = post("/api/production-state", {"op": "printed", "ids": [12345]})
        moved = [t for o, t in TAG_WRITES if o == 12345]
        ok(moved and "IP" in moved[-1] and "Unprocessed" not in moved[-1],
           "an order that is neither is released as before: " + str(TAG_WRITES))
        eq(terms_calls, [12345], "and a real release starts the account order's clock")
    finally:
        shopify._tool_json, shopify._payment_terms_writer = saved
        reset_prod()


@test
def t_reply_all_knows_who_else_was_on_the_message():
    """B16. The sync stored no To or Cc, and reply all read them off the
    stored message, so it never offered anyone and a customer's colleagues
    on Cc were quietly dropped from every reply."""
    payload = {"id": "t1", "historyId": "9", "messages": [
        {"id": "m1", "internalDate": "1758000000000", "labelIds": ["INBOX", "UNREAD"], "snippet": "hi",
         "payload": {"headers": [{"name": "From", "value": "Jo <jo@c.test>"},
                                 {"name": "To", "value": MBOX + ", pat@c.test"},
                                 {"name": "Cc", "value": "Sam <sam@c.test>"},
                                 {"name": "Subject", "value": "Quote"}],
                     "body": {"size": 2, "data": "aGk"}, "mimeType": "text/plain"}}]}
    async def fake_call(method, path, *, params=None, body=None, acct=None):
        return payload
    saved = _gm._call
    _gm._call = fake_call
    try:
        full = run_async(_gm.get_thread("t1"))
    finally:
        _gm._call = saved
    m = full["messages"][0]
    eq((m["to"], m["cc"]), (MBOX + ", pat@c.test", "Sam <sam@c.test>"), "stored with the message")
    store = {"threads": {}}
    mail._mail_apply_thread(store, full, MBOX)
    eq(mail._mail_reply_all_cc(store["threads"]["t1"], MBOX), "pat@c.test, sam@c.test",
       "everyone on it except us and the sender")
    # The stored To header now reaches the sender fallback for a thread every
    # message of which is ours: it is parsed, not split on the comma, and a
    # storefront notification is judged on its own From, not on the To.
    ours = {"id": "t2", "historyId": "9", "subject": "Quote for Jo",
            "messages": [{"id": "m2", "from_name": "Sales", "from_email": MBOX,
                          "to": "Projected Image <info@test-store.co.uk>, Jo <jo@c.test>",
                          "cc": "", "reply_to": "", "files": [], "at": "2026-08-19T01:00:00+00:00",
                          "labels": [], "snippet": "hi"}]}
    mail._mail_apply_thread(store, ours, MBOX)
    t2 = store["threads"]["t2"]
    eq((t2["from_name"], t2["from_email"]), ("Projected Image", "info@test-store.co.uk"),
       "the first address on the To line, as an address")
    notice = dict(ours, id="t3", subject="New customer message",
                  messages=[dict(ours["messages"][0], id="m3")])
    mail._mail_apply_thread(store, notice, MBOX)
    eq(store["threads"]["t3"].get("enquiry"), "new",
       "a storefront notification sent as the store is still an enquiry")


@test
def t_a_conversation_the_shop_starts_is_not_triaged_as_an_arrival():
    """B17. A new message was filed through the arrival path before
    started_to existed, so its sender read as our own mailbox: a rule on our
    domain filed it as internal mail and archived it, and a subject like
    "Contact form follow-up" flagged our own words as a website enquiry."""
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        store = mail._load_mail()
        store["rules"].append({"id": "f1", "name": "Internal mail", "enabled": True, "mode": "all",
                               "conditions": [{"field": "domain", "op": "is", "value": "test-store.co.uk"}],
                               "assign": "", "pool": [], "done": True, "folder": "Internal", "archive": True,
                               "hits": 0, "last_hit_at": "", "_next": 0})
        mail._write_mail(store)
        async def send_new(thread_id, to_addr, subject, body_text, **kw):
            return {"id": "m-new", "thread_id": "tn1"}
        async def no_thread(tid, acct=None):
            raise _gm.GmailError("temporarily unavailable")
        saved = (_gm.send_message, _gm.get_thread)
        _gm.send_message, _gm.get_thread = send_new, no_thread
        try:
            r = post("/api/mail/send", {"to": "jo@customer.com", "subject": "Contact form follow-up",
                                        "text": "Thanks for getting in touch."})
            eq(r.status_code, 200, r.text)
            t = mail._load_mail()["threads"]["tn1"]
            eq(t.get("rule"), None, "no rule ran on our own message")
            eq((t.get("folder"), t.get("folder_archive")), (None, None))
            eq(t.get("enquiry"), None, "and our own words are not a website enquiry")
            eq(mail._load_mail()["rules"][0]["hits"], 0)
            eq((t["state"], t.get("started_to")), ("waiting", "jo@customer.com"))
        finally:
            _gm.send_message, _gm.get_thread = saved
    with_mail(go)


@test
def t_a_folder_with_an_upload_in_flight_is_not_deleted_under_it():
    """B18. Folder delete counted only ACTIVE files, so a folder holding a
    pending upload could go; the finished file then sat in a folder that did
    not exist, counted, invisible and unreachable on the drive."""
    def go(fake):
        folder = post("/api/files/folder", {"op": "add", "name": "Temp"}).json()["id"]
        up = post("/api/files/upload-url", {"name": "big.pdf", "size": 5, "folder_id": folder}).json()
        r = post("/api/files/folder", {"op": "delete", "id": folder})
        eq(r.status_code, 400, "an upload in flight is an occupant: " + r.text)
        ok("still in progress" in r.json()["error"], r.text)
        # An upload abandoned hours ago is not: the folder shows empty, and is.
        d = fileserver._load_files()
        d["files"][up["id"]]["created_at"] = "2026-09-01T00:00:00+00:00"
        fileserver._write_files(d)
        r = post("/api/files/folder", {"op": "delete", "id": folder})
        eq(r.status_code, 200, "an abandoned upload does not hold a folder hostage: " + r.text)
        # And the finished file of an upload whose folder went lands at the
        # top level, not nowhere.
        key = up["url"].split("?")[0].replace("https://fake-r2.test/", "")
        fake.objects[key] = 5
        r2 = post("/api/files/complete", {"id": up["id"]})
        eq(r2.status_code, 200, r2.text)
        eq(r2.json()["store"]["files"][up["id"]]["folder_id"], "", "filed at the top level")
    with_files(go)


@test
def t_a_bulk_move_keeps_one_name_per_folder():
    """B19. The multi-select move skipped the same-name check the single move
    makes, so two active files shared a name in one folder and the drive,
    which resolves by name, could only ever reach the older one."""
    def go(fake):
        art = post("/api/files/folder", {"op": "add", "name": "Artwork"}).json()["id"]
        inbox = post("/api/files/folder", {"op": "add", "name": "Inbox"}).json()["id"]
        made = {}
        for name, fol in (("proof.pdf", art), ("proof.pdf", inbox), ("other.pdf", inbox)):
            up = post("/api/files/upload-url", {"name": name, "size": 10, "folder_id": fol}).json()
            fake.objects[up["url"].split("?")[0].replace("https://fake-r2.test/", "")] = 10
            post("/api/files/complete", {"id": up["id"]})
            made[(name, fol)] = up["id"]
        r = post("/api/files/file", {"op": "move", "ids": [made[("proof.pdf", inbox)]], "folder_id": art})
        eq(r.status_code, 409, "the one file asked for has a namesake there: " + r.text)
        r2 = post("/api/files/file", {"op": "move", "ids": [made[("proof.pdf", inbox)], made[("other.pdf", inbox)]],
                                      "folder_id": art})
        eq(r2.status_code, 200, r2.text)
        eq(r2.json()["skipped"], ["proof.pdf"], "the namesake stays, the other moves")
        files = r2.json()["store"]["files"]
        eq(files[made[("other.pdf", inbox)]]["folder_id"], art)
        eq(files[made[("proof.pdf", inbox)]]["folder_id"], inbox)
    with_files(go)


@test
def t_a_finder_rename_keeps_the_sidecar_a_sidecar():
    """B20. The drive's MOVE cleaned the destination name like an upload from
    the app, stripping the leading dot: Finder's rename of ._proof.pdf became
    a visible "_proof.pdf" that no longer resolved as the sidecar, so the next
    save uploaded a fresh one and the stray sat in the listing."""
    def go(fake):
        ensure_auth()
        import base64 as b64
        owen, _sess, pw = ready_user("Owen", "owen")
        auth = {"Authorization": "Basic " + b64.b64encode(f"owen:{drive_pw(_sess)}".encode()).decode()}
        webdav._dav_auth_cache.clear(); webdav._dav_fail_cache.clear()
        d = fileserver._load_files()
        now = "2026-09-01T00:00:00+00:00"
        d["folders"]["d1"] = {"name": "Artwork", "parent_id": "", "created_at": now}
        d["files"]["f1"] = {"name": "proof.pdf", "folder_id": "d1", "size": 100, "type": "application/pdf",
                            "r2_key": "f1/proof.pdf", "status": "active", "by": owen, "created_at": now}
        d["files"]["f2"] = {"name": "._proof.pdf", "folder_id": "d1", "size": 4, "type": "application/octet-stream",
                            "r2_key": "f2/._proof.pdf", "status": "active", "by": owen, "created_at": now,
                            "hidden": True}
        d["seq"] = 2
        fileserver._write_files(d)
        def dav(method, path, **kw):
            gate._rl_hits.clear(); gate._rl_global.clear()
            return client.request(method, "/dav" + path, headers={**auth, **kw.pop("headers", {})}, **kw)
        eq(dav("MOVE", "/Artwork/proof.pdf", headers={"Destination": "http://testserver/dav/Artwork/final.pdf"}).status_code, 201)
        eq(dav("MOVE", "/Artwork/._proof.pdf", headers={"Destination": "http://testserver/dav/Artwork/._final.pdf"}).status_code, 201)
        d = fileserver._load_files()
        eq((d["files"]["f2"]["name"], d["files"]["f2"].get("hidden")), ("._final.pdf", True),
           "the sidecar keeps its dots and stays hidden")
        eq(webdav._dav_resolve(d, "Artwork/._final.pdf"), ("file", "f2"), "and Finder finds it again")
        eq((d["files"]["f1"]["name"], d["files"]["f1"].get("hidden")), ("final.pdf", False))
        eq([v["name"] for v in fileserver._files_shape(d)["files"].values()], ["final.pdf"],
           "the app lists the real file alone")
    with_files(go)


@test
def t_a_purged_deals_tasks_stay_gone_through_the_next_import():
    """B27. The bin emptying tombstoned the deal but not its activities, so
    the next Pipedrive import refused the deal and recreated every task
    attached to nothing: overdue in the list, counted on the badge."""
    def go():
        ensure_auth()
        crm_wipe()
        async def full(progress=None):
            return dict(PD_EXPORT)
        saved = (pipedrive.export, pipedrive.API_TOKEN)
        pipedrive.export, pipedrive.API_TOKEN = full, "t"
        try:
            eq(post("/api/crm/import", {"go": True}).status_code, 200)
            d = salesdesk._load_crm()
            gid = next(k for k, v in d["deals"].items() if v.get("pd_id") == "31")
            d["deals"][gid]["deleted"], d["deals"][gid]["deleted_at"] = True, "2026-01-01T00:00:00+00:00"
            salesdesk._crm_purge(d)
            salesdesk._write_crm(d)
            ok(gid not in salesdesk._load_crm()["deals"], "the bin emptied")
            ok("41" in (salesdesk._load_crm().get("pd_deleted_activities") or []), "its task has a tombstone too")
            eq(post("/api/crm/import", {"go": True}).status_code, 200)
            d2 = salesdesk._load_crm()
            eq([a for a in d2["activities"].values() if a.get("pd_id") == "41"], [],
               "and it does not come back attached to nothing")
        finally:
            pipedrive.export, pipedrive.API_TOKEN = saved
    with_accounts(go)


@test
def t_a_broken_mailbox_file_still_raises_the_inbox_alarm():
    """Review of B39. The loop read the sync's error back out of the mailbox
    store, so when that store was the thing that broke, the sync's write of
    its error failed, the loop re-read an empty default, and the failure count
    started again every minute: no alarm, ever. Driven through the real sync."""
    emails = []
    async def alert(subject, lines):
        emails.append(subject)
        return True
    async def gmail_down(*a, **k):
        raise RuntimeError("invalid_grant")
    saved = (scheduler._send_alert_email, mail._mail_fail_ticks, mail._mail_alert_sent,
             _gm.connected, _gm.list_threads, _gm.address)
    def go():
        scheduler._send_alert_email = alert
        _gm.connected = lambda *a, **k: True
        _gm.list_threads = gmail_down
        _gm.address = lambda *a, **k: MBOX
        mail._mail_fail_ticks, mail._mail_alert_sent = 0, 0.0
        w = scheduler._load_watch(); w.pop("mail_error_email_at", None); scheduler._save_watch(w)
        with open(mail.MAILBOX_PATH, "w") as fh:
            fh.write("{ truncated")
        mail._mail_mem = None
        for _ in range(mail.MAIL_ALERT_AFTER_TICKS + 2):
            run_async(mail._mail_loop_tick())
        eq(emails, ["Reactor: the shared inbox has stopped syncing"],
           "the alarm is raised although the mailbox file could not hold the error")
    try:
        with_mail(go)
    finally:
        (scheduler._send_alert_email, mail._mail_fail_ticks, mail._mail_alert_sent,
         _gm.connected, _gm.list_threads, _gm.address) = saved
        mail._mail_alert_sent = 0.0
        jsonstore._poisoned_stores.discard(mail.MAILBOX_PATH)
        w = scheduler._load_watch(); w.pop("mail_error_email_at", None); scheduler._save_watch(w)


@test
def t_the_chat_stream_says_it_has_started_before_the_answer():
    """Review of B41. The page may re-ask /api/chat only when the stream
    never spoke, and an answer with no tool steps said nothing until it was
    done: cut off mid-answer, it was run and billed a second time. The
    stream's first event now says the run is under way."""
    started = []
    async def slow_answer(history, dispatch, tools, model, extra, emit=None, effort=None, deep=False):
        started.append(True)
        return {"structured": {"summary": "hi"}}
    def go():
        ensure_auth()
        _a, sess, _p = ready_user("Fay Chat", "fayc", role="admin")
        saved = assistant.run_chat
        assistant.run_chat = slow_answer
        gate._rl_global.clear()
        try:
            r = post_s(sess, "/api/chat/stream", {"message": "hello"})
            events = [json.loads(l[5:]) for l in r.text.split("\n") if l.startswith("data:")]
            eq([e["type"] for e in events], ["start", "done"], "the first thing said is that it started")
        finally:
            assistant.run_chat = saved
    with_accounts(go)


