# ---------------------------------------------------------------------------
# The 2026-09-19 bug audit, the lows (B33, B36-B46)
# ---------------------------------------------------------------------------

@test
def t_a_removed_part_timer_is_not_left_clocked_in():
    """B33. Only a role change closed an open shift. Deleting a part-timer who
    forgot to clock out, or switching them off, left them on the work board
    clocked in for good, their hours still climbing into the totals."""
    def go():
        ensure_auth()
        a, _s1, _p1 = ready_user("Ann Bench", "annb", role="parttime")
        b, _s2, _p2 = ready_user("Bo Bench", "bob", role="parttime")
        w = work._load_work()
        for uid in (a, b):
            w["open"][uid] = {"id": "w-" + uid, "uid": uid, "start": "2026-09-19T08:00:00+00:00"}
        work._write_work(w)
        eq(post("/api/team/user", {"op": "delete", "id": a}).status_code, 200)
        eq(post("/api/team/user", {"op": "active", "id": b, "active": False}).status_code, 200)
        w = work._load_work()
        eq(sorted(w["open"]), [], "neither is still clocked in")
        closed = {s["uid"]: s for s in w["sessions"] if s.get("id", "").startswith("w-")}
        eq(sorted(closed), sorted([a, b]), "both shifts were closed into the ledger")
        ok("deleted" in closed[a]["note"] and "switched off" in closed[b]["note"],
           "each says why: " + str([closed[a]["note"], closed[b]["note"]]))
        ok(closed[a]["corrected"] and closed[a]["secs"] > 0, "as a correction, with its hours")
    with_accounts(go)


@test
def t_the_stock_bridge_counts_each_failed_attempt_once():
    """B36. The drain counted an attempt and the push counted it again, so an
    order was parked for a human after ten attempts rather than twenty."""
    reset_dispatch(); reset_prod()
    async def down(op, order_id, order_name, lines, sent):
        raise RuntimeError("zeta is down")
    def go(sent):
        run_async(stock_link._zeta_push_locked({}, 12345, "book"))
        eq(stock_link._load_zeta_pending()["12345"]["tries"], 1, "the first failure counts one")
        for n in (2, 3, 4):
            run_async(stock_link._zeta_drain({}))
            eq(stock_link._load_zeta_pending()["12345"]["tries"], n, "one per retry, not two")
        pend = stock_link._load_zeta_pending()
        pend["12345"]["tries"] = stock_link.ZETA_MAX_TRIES
        stock_link._write_zeta_pending(pend)
        run_async(stock_link._zeta_drain({}))
        entry = stock_link._load_zeta_pending()["12345"]
        ok(entry.get("stuck"), "parked after exactly ZETA_MAX_TRIES failures")
        eq(entry["tries"], stock_link.ZETA_MAX_TRIES, "and not tried again once parked")
    with_zeta(go, send=down)


@test
def t_a_size_that_is_not_a_number_neither_crashes_nor_uploads():
    """B37. The day sheet sorted by float(size), so one cell edited to "TBC"
    in an uploaded sheet took the whole day's stock usage down; the upload
    checked the columns, never the sizes in them."""
    rows = {("TBC", "Mono"): {"size": "TBC", "glass": "Mono", "qty": 1},
            ("37.5", "Mono"): {"size": "37.5", "glass": "Mono", "qty": 2},
            ("64.9", "Colour"): {"size": "64.9", "glass": "Colour", "qty": 1}}
    eq([r["size"] for r in sorted(rows.values(), key=stock_link._usage_row_order)], ["64.9", "37.5", "TBC"],
       "largest first, and a size that is not one goes last instead of raising")
    def go():
        ensure_auth()
        text = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "gobo-sizes.csv"),
                    encoding="utf-8-sig").read()
        import csv as _csv, io as _io
        src = list(_csv.DictReader(_io.StringIO(text)))
        col = "Closest Production Size (mm)"
        at = next(i for i, r in enumerate(src) if (r.get(col) or "").strip())
        src[at][col] = "TBC"
        buf = _io.StringIO()
        wr = _csv.DictWriter(buf, fieldnames=list(src[0].keys()))
        wr.writeheader(); wr.writerows(src)
        before = open(size_list.GOBO_SIZES_LIVE, encoding="utf-8").read() if os.path.exists(size_list.GOBO_SIZES_LIVE) else None
        r = post("/api/gobo-sizes/upload", {"csv": buf.getvalue()})
        eq(r.status_code, 400, r.text)
        ok("not a size" in r.json()["error"] and "TBC" in r.json()["error"] and f"row {at + 2}" in r.json()["error"],
           "the bad cell is named: " + r.json()["error"])
        after = open(size_list.GOBO_SIZES_LIVE, encoding="utf-8").read() if os.path.exists(size_list.GOBO_SIZES_LIVE) else None
        eq(after, before, "and nothing was changed")
    with_accounts(go)


@test
def t_the_mail_loop_says_when_the_inbox_has_stopped():
    """B39. The sync files its own errors under sync_error, so the loop's
    except branch never ran and a dead Gmail grant stopped the inbox, the
    filters and the enquiries without a word to anyone."""
    emails = []
    async def alert(subject, lines):
        emails.append((subject, " ".join(lines)))
        return True
    saved = (scheduler._send_alert_email, mail._mail_fail_ticks)
    scheduler._send_alert_email = alert
    w = scheduler._load_watch(); w.pop("mail_error_email_at", None); scheduler._save_watch(w)
    mail._mail_fail_ticks = 0
    try:
        for _ in range(mail.MAIL_ALERT_AFTER_TICKS - 1):
            eq(run_async(mail._mail_loop_health("invalid_grant")), False)
        eq(emails, [], "a blip is not an outage")
        eq(run_async(mail._mail_loop_health("invalid_grant")), True, "half an hour of failures is")
        ok("stopped syncing" in emails[0][0] and "invalid_grant" in emails[0][1], emails)
        eq(run_async(mail._mail_loop_health("invalid_grant")), False, "once a day, not once a minute")
        eq(run_async(mail._mail_loop_health("")), False)
        eq(mail._mail_fail_ticks, 0, "a good sync starts the count again")
    finally:
        scheduler._send_alert_email, mail._mail_fail_ticks = saved
        mail._mail_alert_sent = 0.0
        w = scheduler._load_watch(); w.pop("mail_error_email_at", None); scheduler._save_watch(w)


@test
def t_a_files_attachment_is_named_whole():
    """B40. The prefix split came off at any dash, so a file from Files called
    gobo-layout-final.pdf was "layout-final.pdf" in every refusal."""
    eq(mail._mail_part_name("f12/gobo-layout-final.pdf"), "gobo-layout-final.pdf")
    eq(mail._mail_part_name("mail/u1/0123456789abcdef-proof-v2.pdf"), "proof-v2.pdf",
       "an upload's own prefix still comes off")
    eq(mail._mail_part_name("mail/u1/not-hex-prefix.pdf"), "not-hex-prefix.pdf")


@test
def t_a_size_cell_is_read_as_the_number_the_bench_uses():
    """Review of B37. The upload accepted "86 mm" and "86.0" (the cleaner can
    read them) but the sheet stored the raw text, and the bezel rule looks up
    "86" exactly: an "86 mm" line booked 86mm glass instead of a 64.9 blank
    and a ring. The sheet is normalised as it is read."""
    for raw, want in (("86 mm", "86"), ("86.0", "86"), ("37.5", "37.5"), (" 64.9 ", "64.9"),
                      ("TBC", "TBC"), ("", "")):
        eq(size_list._sheet_size(raw), want, repr(raw))
    ok(size_list._sheet_size("86 mm") in stock_link._BEZEL_UP, "and it is the key the bezel rule knows")


@test
def t_the_mail_loop_itself_raises_the_alarm_and_never_floods():
    """Review of B39. Driven through the loop's own tick, from the sync's
    sync_error, and with watch.json unwritable: the stamp there was the only
    brake, so a store that could not be written sent an email every minute."""
    emails = []
    async def alert(subject, lines):
        emails.append(subject)
        return True
    async def failing_sync(force=False):
        st = mail._load_mail()
        st["sync_error"] = "invalid_grant"
        mail._write_mail(st)
        return "invalid_grant"
    saved = (scheduler._send_alert_email, mail._mail_fail_ticks, mail._mail_alert_sent,
             mail._mail_sync_now, _gm.connected)
    scheduler._send_alert_email, mail._mail_sync_now = alert, failing_sync
    _gm.connected = lambda *a, **k: True
    mail._mail_fail_ticks, mail._mail_alert_sent = 0, 0.0
    w = scheduler._load_watch(); w.pop("mail_error_email_at", None); scheduler._save_watch(w)
    def go():
        jsonstore._poisoned_stores.add(scheduler.WATCH_PATH)      # watch.json cannot be written
        for _ in range(mail.MAIL_ALERT_AFTER_TICKS + 10):
            run_async(mail._mail_loop_tick())
        eq(emails, ["Reactor: the shared inbox has stopped syncing"],
           "one email from the real loop, and one only, though nothing could be stamped on disk")
    try:
        with_mail(go)
    finally:
        jsonstore._poisoned_stores.discard(scheduler.WATCH_PATH)
        (scheduler._send_alert_email, mail._mail_fail_ticks, mail._mail_alert_sent,
         mail._mail_sync_now, _gm.connected) = saved
        mail._mail_alert_sent = 0.0
        w = scheduler._load_watch(); w.pop("mail_error_email_at", None); scheduler._save_watch(w)


@test
def t_every_product_reader_reads_the_whole_catalogue_or_says_it_could_not():
    """Review of B38. Four readers took a single page of 250; the loan-unit
    picker is the one left (the Products tab, the SEO audit and the Overview
    went on 22 Oct 2026)."""
    def catalogue(n, fail_after=None):
        calls = []
        async def tools(registry, name, args):
            if name != "shopify_list_products":
                return {}
            calls.append(args.get("since_id"))
            if fail_after is not None and len(calls) > fail_after:
                return {"_failed": True}
            start = int(args.get("since_id") or 0)
            left = max(0, n - start)
            return {"products": [{"id": start + i + 1, "title": f"P{start + i + 1}", "handle": f"p{start + i + 1}",
                                  "body_html": "", "images": [], "variants": [{"id": 1, "inventory_quantity": 1}]}
                                 for i in range(min(int(args.get("limit") or 250), left))]}
        return tools, calls
    saved = shopify._tool_json
    try:
        shopify._tool_json, calls = catalogue(260)
        prods, okd, cut = run_async(catalog._all_products({}, "id"))
        eq((len(prods), okd, cut), (260, True, False))
        shopify._tool_json, _c = catalogue(600, fail_after=1)
        eq(run_async(catalog._all_products({}, "id"))[1], False, "a failed page is a failed read")
        loans._loan_products.update({"at": 0.0, "rows": []})
        raised = False
        try:
            run_async(loans._loan_product_rows({}))
        except RuntimeError:
            raised = True
        ok(raised, "the loan picker's failed read is an error the route reports, not 'no matches'")
        shopify._tool_json, _c = catalogue(300)
        loans._loan_products.update({"at": 0.0, "rows": []})
        eq(len(run_async(loans._loan_product_rows({}))), 300, "the loan picker reaches every product")
    finally:
        shopify._tool_json = saved
        loans._loan_products.update({"at": 0.0, "rows": []})


@test
def t_an_open_shift_left_by_a_removed_account_is_swept_up():
    """Review of B33. The fix closes a shift when an account is removed now;
    one left open by an account removed before that sat on the board for good."""
    def go():
        ensure_auth()
        a, _s, _p = ready_user("Cy Bench", "cyb", role="parttime")
        d = team._load_users()
        d["users"][a]["deleted"], d["users"][a]["active"] = True, False
        team._write_users(d)
        w = work._load_work()
        w["open"][a] = {"id": "w-old", "uid": a, "start": "2026-09-01T08:00:00+00:00"}
        w["open"]["ghost"] = {"id": "w-ghost", "uid": "ghost", "start": "2026-09-01T08:00:00+00:00"}
        work._write_work(w)
        eq(work._work_close_orphans(), [a], "the removed account's shift is closed")
        eq(list(work._load_work()["open"]), ["ghost"],
           "and one the register has never heard of is left alone: delete is a soft delete, "
           "so a missing account means a lost register, not a removal")
        eq(work._work_close_orphans(), [], "and a second pass finds nothing")
    with_accounts(go)


@test
def t_a_broken_accounts_file_clocks_nobody_out():
    """Review of the B33 sweep. An unreadable users.json loads as an empty
    register, and against an empty register every open shift belonged to a
    missing account: the hourly check wrote every part-timer's shift closed
    as "the account had been removed", in the hour the watchdog was already
    alerting that the register had emptied."""
    def go():
        ensure_auth()
        b, _s, _p = ready_user("Di Bench", "dib", role="parttime")
        c, _s2, _p2 = ready_user("Ed Bench", "edb", role="parttime")
        w = work._load_work()
        for uid in (b, c):
            w["open"][uid] = {"id": "w-" + uid, "uid": uid, "start": "2026-09-01T08:00:00+00:00"}
        work._write_work(w)
        with open(team.USERS_PATH, "w") as fh:
            fh.write("{ not json")
        team._users_mem = None
        try:
            eq(work._work_close_orphans(), [], "nothing is closed on an unreadable register")
            eq(sorted(work._load_work()["open"]), sorted([b, c]), "both are still clocked in")
        finally:
            jsonstore._poisoned_stores.discard(team.USERS_PATH)
    with_accounts(go)


@test
def t_the_margin_report_counts_only_what_is_still_on_the_order():
    """Note from the B4 review. A refunded unit stayed in the margin report's
    revenue and its goods cost; and an order past the report's back-fill bound
    was called a Shopify load failure."""
    from datetime import datetime as _dt, timezone as _tz
    reset_dispatch(); reset_prod()
    order = {"id": 778, "name": "#778", "currency": "GBP", "created_at": _dt.now(_tz.utc).isoformat(),
             "taxes_included": False, "total_price": "200.00",
             "line_items": [{"id": 1, "title": "Gobo", "quantity": 2, "current_quantity": 1, "price": "100.00",
                             "variant_id": 111, "discount_allocations": [{"amount": "20.00"}]}],
             "shipping_lines": []}
    desk._record_dispatch(778, {"tracking_number": "T8", "carrier_name": "UPS", "order_name": "#778",
                                   "amount_ex_vat": 0.0, "dispatched_at": _dt.now(_tz.utc).isoformat()})
    async def tools(registry, name, args):
        if name == "shopify_list_orders":
            return {"orders": [order]}
        if name == "shopify_get_variant":
            return {"id": 111, "inventory_item_id": 9111}
        if name == "shopify_get_inventory_items":
            return {"inventory_items": [{"id": 9111, "cost": "30.00"}]}
        return {}
    saved = shopify._tool_json; shopify._tool_json = tools
    desk.COST_CACHE_PATH = SCRATCH + "/cost_cache2.json"
    try:
        os.remove(desk.COST_CACHE_PATH)
    except FileNotFoundError:
        pass
    try:
        res = run_async(desk.run_margin_report({}, days=30))
        row = next(r for r in res["rows"] if str(r.get("order_id")) == "778")
        eq(row["revenue"], 90.0, "one of two units left: (200 - 20) / 2")
        eq(row["goods_cost"], 30.0, "and one unit's cost")
    finally:
        shopify._tool_json = saved
        reset_dispatch()
    for oid in (801, 802):
        desk._record_dispatch(oid, {"tracking_number": f"T{oid}", "carrier_name": "UPS", "order_name": f"#{oid}",
                                       "dispatched_at": _dt.now(_tz.utc).isoformat()})
    async def none(registry, name, args):
        return {"orders": []} if name == "shopify_list_orders" else {"_failed": True}
    saved_max = desk.MARGIN_BACKFILL_MAX
    shopify._tool_json, desk.MARGIN_BACKFILL_MAX = none, 1
    try:
        res = run_async(desk.run_margin_report({}, days=30))
        notes = sorted(r["incomplete"] for r in res["rows"] if str(r.get("order_id")) in ("801", "802"))
        eq(len(notes), 2)
        ok(any("could not be loaded from Shopify" in n for n in notes), "the one fetched and refused says so")
        ok(any("reads at most 1 such orders" in n for n in notes), "the one past the bound says why: " + str(notes))
    finally:
        shopify._tool_json, desk.MARGIN_BACKFILL_MAX = saved, saved_max
        reset_dispatch()
    # The list read itself failed: an order missing from it says nothing
    # about its age, and Shopify is refusing, so the back-fill stops asking.
    for oid in range(810, 816):
        desk._record_dispatch(oid, {"tracking_number": f"T{oid}", "carrier_name": "UPS", "order_name": f"#{oid}",
                                       "dispatched_at": _dt.now(_tz.utc).isoformat()})
    singles = []
    async def refusing(registry, name, args):
        if name == "shopify_get_order":
            singles.append(args.get("order_id"))
        return {"_failed": True}
    shopify._tool_json, desk.MARGIN_BACKFILL_MAX = refusing, 1
    orderbook._bust_orders()
    try:
        res = run_async(desk.run_margin_report({}, days=31))
        notes = [r["incomplete"] for r in res["rows"]]
        eq(len(notes), 6)
        ok(all(n == "the order could not be loaded from Shopify" for n in notes),
           "no age reason when the read failed: " + str(notes))
        desk.MARGIN_BACKFILL_MAX = 60
        singles.clear()
        run_async(desk.run_margin_report({}, days=32))
        eq(len(singles), 3, "three refusals in a row and the back-fill stops asking")
    finally:
        shopify._tool_json, desk.MARGIN_BACKFILL_MAX = saved, saved_max
        reset_dispatch()


@test
def t_a_conversation_started_in_gmail_is_not_triaged_as_an_arrival():
    """Note from the B17 review. A conversation the shop started from Gmail
    itself reached the board through the sync, and the inbox rules ran on its
    first message, which is ours. Gmail labels such a message SENT; a
    storefront notification, also from the shop's address, carries no SENT
    and is still judged as the enquiry it may be."""
    store = {"threads": {}, "rules": [{"id": "f1", "name": "Internal mail", "enabled": True, "mode": "all",
             "conditions": [{"field": "domain", "op": "is", "value": "test-store.co.uk"}],
             "assign": "", "pool": [], "done": True, "folder": "Internal", "archive": True,
             "hits": 0, "last_hit_at": "", "_next": 0}]}
    ours = {"id": "g1", "historyId": "1", "subject": "Contact form follow-up",
            "messages": [dict(_mk_msg("g1-m1", "Sales", MBOX, "2026-09-20T09:00:00+00:00"),
                              to="jo@customer.com", labels=["SENT"])]}
    mail._mail_apply_thread(store, ours, MBOX)
    t = store["threads"]["g1"]
    eq((t.get("rule"), t.get("folder"), t.get("enquiry")), (None, None, None),
       "no rule and no enquiry on our own message")
    eq(store["rules"][0]["hits"], 0)
    notice = {"id": "g2", "historyId": "1", "subject": "New customer message",
              "messages": [dict(_mk_msg("g2-m1", "Store", MBOX, "2026-09-20T09:00:00+00:00"), labels=["INBOX"])]}
    mail._mail_apply_thread(store, notice, MBOX)
    eq(store["threads"]["g2"].get("enquiry"), "new", "the storefront notification is still an enquiry")
    # Who started it is read before the store keeps only the latest messages:
    # a customer's long thread whose kept window happens to open on one of
    # our replies is still the customer's, and still triaged.
    rule = {"id": "f2", "name": "Customer", "enabled": True, "mode": "all",
            "conditions": [{"field": "domain", "op": "is", "value": "customer.com"}],
            "assign": "", "pool": [], "done": False, "folder": "Customers", "archive": False,
            "hits": 0, "last_hit_at": "", "_next": 0}
    store2 = {"threads": {}, "rules": [rule]}
    n = mail.MAIL_MSGS_PER_THREAD
    msgs = [dict(_mk_msg("g3-m0", "Jo", "jo@customer.com", "2026-09-01T09:00:00+00:00"), labels=["INBOX"])]
    for i in range(1, n + 1):
        ours_turn = i % 2 == 1
        msgs.append(dict(_mk_msg(f"g3-m{i}", "Sales" if ours_turn else "Jo",
                                 MBOX if ours_turn else "jo@customer.com",
                                 "2026-09-%02dT09:%02d:00+00:00" % (2 + i // 60, i % 60)),
                         labels=["SENT"] if ours_turn else ["INBOX"]))
    mail._mail_apply_thread(store2, {"id": "g3", "historyId": "1", "subject": "Long job", "messages": msgs}, MBOX)
    eq(store2["threads"]["g3"].get("folder"), "Customers",
       "a customer's thread is triaged however the kept window happens to begin")


