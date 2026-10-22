# ---- review of #15 --------------------------------------------------------

@test
def t_only_a_signed_in_request_sees_or_counts_its_timing():
    """Review of #15 (SERVER1, COMPAT1, COMPAT3). The header went on every
    /api/ answer. A wrong-password sign-in for a real name saves a failure
    count (a store mark) and one for a made-up name saves nothing, so the two
    vague 401s differed: a clean yes or no on whether a username exists,
    undoing the sign-in's levelling. And refused requests were counted, so
    anyone could wash a route's real times out of Settings. Only a request
    that passed the door with a live session now gets the header or counts."""
    import perf

    def go():
        ensure_auth()
        ready_user("Ruth", "ruth")
        perf.ROUTES.clear()
        h = {"Authorization": "Bearer " + tok()}
        for p in (gate._rl_hits, gate._rl_global, team._login_hits):
            p.clear()
        real = client.post("/api/auth/login", json={"username": "ruth", "password": "wrong-password-1"}, headers=h)
        fake = client.post("/api/auth/login", json={"username": "nobody-here", "password": "wrong-password-1"},
                           headers=h)
        eq((real.status_code, fake.status_code), (401, 401))
        eq(real.headers.get("server-timing"), None, "a sign-in answer carries no breakdown")
        eq(fake.headers.get("server-timing"), None)
        names = lambda r: sorted(k for k in r.headers.keys() if k not in ("content-length", "date"))
        eq(names(real), names(fake), "and the two answers carry the same headers")
        for _ in range(5):
            gate._rl_hits.clear(); gate._rl_global.clear()
            r = client.post("/api/crm/board", json={}, headers=h)     # no session
            eq(r.status_code, 401)
            eq(r.headers.get("server-timing"), None, "a refused request learns nothing from the timing")
        ok("/api/crm/board" not in perf.ROUTES, "and is not counted")
        r = post("/api/crm/board", {})
        ok(_server_timing(r).get("app", 0) > 0, "a signed-in request still gets it")
        ok("/api/crm/board" in perf.ROUTES, "and is counted")
        _uid, msess, _ = ready_user("Mo", "mo")
        eq(post_s(msess, "/api/status", {}).status_code, 403)
        ok("/api/status" not in perf.ROUTES, "a refusal, even signed in, is not a time worth counting")
    with_accounts(go)


@test
def t_a_claude_call_is_timed_and_kept_out_of_the_table():
    """Review of #15 (PAGE3, COMPAT4). Answers that call Claude take seconds
    by design; counted, they filled the Response times row and pinned it at
    Slow for the life of the process, pushing out the desk pages it exists to
    name. Every model call goes through _xcreate, which now marks its time as
    "ai" and keeps its request out of the table."""
    import perf, types
    saved = claude._xcreate_once

    async def fake_once(client, kwargs):
        await asyncio.sleep(0.01)
        return types.SimpleNamespace(stop_reason="end_turn", content=[])
    claude._xcreate_once = fake_once
    try:
        async def go():
            marks, token = perf.start()
            try:
                await claude._xcreate(None, model="claude-test", messages=[], max_tokens=10)
            finally:
                perf.stop(token)
            return marks
        marks = run_async(go())
        ok(marks.get("ai", 0) >= 5, "the model's time is its own mark: %r" % marks)
        ok(marks.get("_skip"), "and the request is kept out of the slowest-routes table")
        eq(perf.header(marks).count("_"), 0, "the flags never reach the header")
    finally:
        claude._xcreate_once = saved


@test
def t_the_slowest_twentieth_is_the_slowest_twentieth():
    """Review of #15 (SERVER2). With 20 samples p95 picked the maximum, so
    Settings said '1 in 20 over X ms' when nothing was over X."""
    import perf
    saved = dict(perf.ROUTES)
    perf.ROUTES.clear()
    try:
        for i in range(1, 21):
            perf.record("/api/x", float(i))
        for i in range(1, 101):
            perf.record("/api/y", float(i))
        rows = {r["route"]: r for r in perf.summary()}
        eq(rows["/api/x"]["p95"], 19.0, "one of twenty is over it")
        eq(rows["/api/y"]["p95"], 95.0, "five of a hundred are over it")
        eq(rows["/api/y"]["p50"], 50.0)
    finally:
        perf.ROUTES.clear()
        perf.ROUTES.update(saved)


@test
def t_a_relabel_steps_aside_for_a_running_sync():
    """Review of #15 (SERVER3). Each click's relabel queued on _mail_lock, so a
    burst of claims during a slow Gmail held the mail loop and anyone's
    Refresh behind every one of them. A relabel now waits briefly for the
    lock and otherwise leaves the thread to the sync's own label catch-up,
    which already runs under the lock and compares the label it wants with
    the one it has."""
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        calls = []

        async def modify(tid, add=None, remove=None):
            calls.append(tid)

        async def ensure(name, known):
            known[name] = "L-" + name
            return known[name]
        saved = (_gm.modify_thread, _gm.ensure_label, mail._mail_lock, mail.MAIL_LABEL_LOCK_WAIT)
        _gm.modify_thread, _gm.ensure_label = modify, ensure
        mail.MAIL_LABEL_LOCK_WAIT = 0.05
        got, restore = _capture_spawn()
        try:
            eq(post_s(sess, "/api/mail/claim", {"id": "t1"}).status_code, 200)
            mail._mail_lock = asyncio.Lock()

            async def busy_sync():
                await mail._mail_lock.acquire()
                try:
                    await got.pop()          # the relabel, while a sync holds the lock
                finally:
                    mail._mail_lock.release()
            t = mail._load_mail()["threads"]["t1"]
            t["label_retry_at"] = time.time() + 400     # an earlier failure's back-off
            t["label_tried_at"] = time.time()
            run_async(busy_sync())
            eq(calls, [], "it did not wait out the sync")
            ok(mail._mail_want_label(t) != (t.get("gmail_label") or ""),
               "so the sync's catch-up sees the label is owed: %r" % t.get("gmail_label"))
            ok("label_retry_at" not in t and t.get("label_tried_at") == 0,
               "and takes it first, back-off or not: %r" % {k: t.get(k) for k in ("label_retry_at", "label_tried_at")})
        finally:
            restore()
            _gm.modify_thread, _gm.ensure_label, mail._mail_lock, mail.MAIL_LABEL_LOCK_WAIT = saved
    with_mail(go)


@test
def t_an_opened_email_reads_as_read_at_once_unless_gmail_refuses():
    """Review of #15 (PAGE4). The board followed only once Gmail confirmed the
    read, so a poll landing between the window opening and Gmail answering
    showed the email unread again after the person had read it. It now reads
    as read at once, and goes back to unread if Gmail refuses."""
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        mail._load_mail()["threads"]["t1"]["unread"] = True

        async def refuse(tid, add=None, remove=None):
            raise _gm.GmailError("backend error")
        saved = _gm.modify_thread
        _gm.modify_thread = refuse
        got, restore = _capture_spawn()
        try:
            eq(post_s(sess, "/api/mail/thread", {"id": "t1"}).status_code, 200)
            rows = {t["id"]: t for t in post_s(sess, "/api/mail/board", {}).json()["threads"]}
            eq(rows["t1"]["unread"], False, "read as soon as it is opened")
            run_async(got.pop(0))
            eq(mail._load_mail()["threads"]["t1"]["unread"], True, "and unread again when Gmail refuses")
        finally:
            restore()
            _gm.modify_thread = saved
    with_mail(go)


@test
def t_a_read_on_open_never_outlives_what_gmail_says():
    """The re-check of #15's fixes (PAGE4). Three edges of reading on open:
    a mark-read Gmail never answered left the board saying read; the put-back
    after a refusal was never saved, so a store written in between kept the
    read on disk; and Mark unread pressed while the mark-read was still at
    Gmail was undone by it, though that is how somebody undoes an accidental
    open."""
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        mail._load_mail()["threads"]["t1"]["unread"] = True
        calls = []

        async def modify(tid, add=None, remove=None):
            calls.append((tuple(add or ()), tuple(remove or ())))
        saved = (_gm.modify_thread, mail._mail_set_unread)
        got, restore = _capture_spawn()
        try:
            # Gmail never answers: put back, and saved even though another
            # writer saved the optimistic read in between.
            async def silent(store, ids, unread):
                return {"changed": 0, "failed": 0}
            mail._mail_set_unread = silent
            eq(post_s(sess, "/api/mail/thread", {"id": "t1"}).status_code, 200)
            mail._write_mail(mail._load_mail())          # another writer, mid-flight
            run_async(got.pop(0))
            eq(mail._load_mail()["threads"]["t1"]["unread"], True, "unanswered is not confirmed")
            with open(mail.MAILBOX_PATH, encoding="utf-8") as fh:
                eq(json.load(fh)["mailbox"]["threads"]["t1"]["unread"], True, "and the disk says so too")
            # Mark unread pressed while the mark-read is still to run: it wins.
            mail._mail_set_unread = saved[1]
            _gm.modify_thread = modify
            eq(post_s(sess, "/api/mail/thread", {"id": "t1"}).status_code, 200)
            eq(post_s(sess, "/api/mail/read", {"id": "t1", "unread": True}).status_code, 200)
            calls.clear()
            run_async(got.pop(0))
            eq(calls, [], "the late mark-read stands down")
            eq(mail._load_mail()["threads"]["t1"]["unread"], True, "and the email stays unread, as asked")
        finally:
            restore()
            _gm.modify_thread, mail._mail_set_unread = saved
    with_mail(go)


def _written_off(e):
    """The sweep wrote this finding off as gone."""
    return any("No longer detected" in h.get("note", "") for h in e.get("history") or [])


def _left_as_it_was(stores, xid, before, why):
    """An open finding a sweep did not see go: still open, nothing written."""
    e = stores["store"]["exceptions"][xid]
    ok(not e.get("stale") and not _written_off(e), why + ": %s" % e["history"][-1:])
    eq(e["status"], before["status"], why)
    eq(e["history"], before["history"], why + ": and nothing written on its history")


@test
def t_an_open_payout_finding_is_not_settled_by_ageing_past_the_window():
    """Every read answered, and still an open payout finding was marked "No
    longer detected" once its payout aged past the window the check matches
    in. The check leaves out a payout older than the bank lines it holds, and
    the merge read that as the discrepancy going away. It keeps watching the
    payout an open finding rests on instead, so the finding closes only when a
    sweep sees the deposit."""
    import copy as _copy
    payout = {"id": 7101, "date": _rc._cutoff_day(10), "amount": "312.40",
              "currency": "GBP", "status": "paid"}
    fx = _FakeXero(invoices=[_raw_xinv("INV-104275", "842.00")])
    answers = {"shopify_list_payouts": {"payouts": [payout]},
               "shopify_payout_transactions": {"transactions": []},
               "shopify_list_disputes": {"disputes": []}}
    stores = _payments_world(fx, answers)
    try:
        run_async(_rc.sweep())
        exs = stores["store"]["exceptions"]
        found = [x for x, e in exs.items() if e["kind"] == "payout_missing_from_bank"]
        eq(len(found), 1, "a paid payout with no deposit is found")
        xid = found[0]
        exs[xid]["status"] = "investigating"
        before = _copy.deepcopy(exs[xid])
        # Months on, the deposit never found, and Shopify still lists the payout.
        aged = _rc._cutoff_day(_rc.FETCH_DAYS + 5)
        payout["date"] = aged
        for n in (1, 2):
            r = run_async(_rc.sweep())
            ok(not _did_not_run(r["notes"], "payout"), "every read answered: %s" % r["notes"])
            _left_as_it_was(stores, xid, before, "sweep %d: a payout past the window is not a "
                                                  "deposit found" % n)
            ok("7101" in stores["cache"]["shopify"]["payouts"], "the payout it rests on is still held")
        # Still watched: the deposit turns up, and the sweep that sees it settles it.
        fx.bank.append(_raw_btxn("BT-7101", "RECEIVE", "312.40", aged))
        run_async(_rc.sweep())
        e = stores["store"]["exceptions"][xid]
        ok(e["stale"] and _written_off(e), "a sweep that sees the deposit settles it")
    finally:
        _unconfigure_recon()


@test
def t_an_open_chargeback_finding_is_not_settled_by_ageing_past_the_window():
    """The chargeback check leaves out disputes older than the books it holds,
    by the same rule as payouts, with the same result for an open finding."""
    import copy as _copy
    dispute = {"id": 8101, "order_id": 104275, "type": "chargeback", "amount": "95.00",
               "currency": "GBP", "reason": "fraudulent", "status": "lost",
               "initiated_at": _rc._cutoff_day(10)}
    fx = _FakeXero(invoices=[_raw_xinv("INV-104275", "842.00")])
    answers = {"shopify_list_payouts": {"payouts": []},
               "shopify_list_disputes": {"disputes": [dispute]}}
    stores = _payments_world(fx, answers)
    try:
        run_async(_rc.sweep())
        exs = stores["store"]["exceptions"]
        found = [x for x, e in exs.items() if e["kind"] == "chargeback_missing_from_xero"]
        eq(len(found), 1, "a chargeback with no Xero record is found")
        xid = found[0]
        exs[xid]["status"] = "investigating"
        before = _copy.deepcopy(exs[xid])
        aged = _rc._cutoff_day(_rc.FETCH_DAYS + 5)
        dispute["initiated_at"] = aged
        for n in (1, 2):
            r = run_async(_rc.sweep())
            ok(not _did_not_run(r["notes"], "chargeback"), "every read answered: %s" % r["notes"])
            _left_as_it_was(stores, xid, before, "sweep %d: a dispute past the window is not one "
                                                  "recorded" % n)
            ok("8101" in stores["cache"]["shopify"]["disputes"], "the dispute it rests on is still held")
        fx.bank.append(_raw_btxn("BT-8101", "SPEND", "95.00", aged))
        run_async(_rc.sweep())
        e = stores["store"]["exceptions"][xid]
        ok(e["stale"] and _written_off(e), "a sweep that sees it recorded settles it")
    finally:
        _unconfigure_recon()


@test
def t_an_open_xero_sale_finding_is_not_settled_by_ageing_past_the_window():
    """The check for Xero sales with no Shopify order looks only at the last
    WINDOW_DAYS of invoices, a shorter horizon than the cache keeps, so an
    open finding went "no longer detected" two months before retention could
    even have touched its invoice."""
    import copy as _copy
    stray = dict(_raw_xinv("INV-9001", "77.00", contact="Walk-in Trade"),
                 DateString=_rc._cutoff_day(10) + "T00:00:00")
    fx = _FakeXero(invoices=[_raw_xinv("INV-104275", "842.00"), stray])
    stores = _payments_world(fx, {})
    try:
        run_async(_rc.sweep())
        exs = stores["store"]["exceptions"]
        found = [x for x, e in exs.items() if e["kind"] == "xero_sale_without_shopify"]
        eq(len(found), 1, "an invoice no order explains is found")
        xid = found[0]
        exs[xid]["status"] = "investigating"
        before = _copy.deepcopy(exs[xid])
        stray["DateString"] = _rc._cutoff_day(_rc.WINDOW_DAYS + 5) + "T00:00:00"
        for n in (1, 2):
            run_async(_rc.sweep())
            _left_as_it_was(stores, xid, before, "sweep %d: an invoice past the window is not "
                                                  "one explained" % n)
            ok("XR-INV-9001" in stores["cache"]["xero"]["invoices"], "the invoice it rests on is still held")
        stray["Status"] = "VOIDED"
        run_async(_rc.sweep())
        e = stores["store"]["exceptions"][xid]
        ok(e["stale"] and _written_off(e), "a sweep that sees it voided settles it")
    finally:
        _unconfigure_recon()


@test
def t_an_open_xero_sale_past_the_window_does_not_tip_the_numbering_finding():
    """An invoice watched past the window only for its own open finding is not
    one of the recent invoices the numbering finding is a share of: eleven old
    ones must not turn one recent, properly referenced invoice into "most
    invoices reference no Shopify order"."""
    orders = {"1": _ord(104275, "#104275", 84200, date=_rc._cutoff_day(10))}
    xinv = {"XI-INV-104275": _inv("INV-104275", 84200, date=_rc._cutoff_day(10))}
    old = _rc._cutoff_day(_rc.WINDOW_DAYS + 5)
    for i in range(11):
        v = _inv("INV-90%02d" % i, 7700 + i, contact="Walk-in Trade", date=old)
        xinv[v["id"]] = v
    cache = {"shopify": {"orders": orders}, "xero": {"invoices": xinv}}
    eq(_rc.check_xero_orphan_sales(cache), [], "past the window and watched by nothing: not looked at")
    watched = frozenset(v["id"] for v in xinv.values() if v["contact"] == "Walk-in Trade")
    kinds = [e["kind"] for e in _rc.check_xero_orphan_sales(cache, open_refs=watched)]
    eq(kinds, ["xero_sale_without_shopify"] * 11, "each watched invoice is its own finding still")


@test
def t_an_open_mailbox_finding_is_not_settled_by_its_document_ageing_out():
    """Retention keeps the Xero and Shopify records an open finding rests on,
    but not the mailbox document behind one: the document was dropped, and the
    next sweep, finding nothing, wrote the finding off as no longer detected."""
    import copy as _copy
    fx = _FakeXero(invoices=[_raw_xinv("INV-104275", "842.00")])
    stores = _recon_world(fx, [_raw_order(104275, "#104275", "842.00")])
    stores["docs"]["m9:a9"] = {
        "doc_type": "supplier_invoice", "invoice_numbers": ["SUP-4410"], "total_pence": 48000,
        "amounts": [48000], "currency": "GBP", "invoice_lines": [], "counterparty": "Acme Glass",
        "extracted_by": "text", "verified": True, "source_key": "m9:a9", "filename": "sup.pdf",
        "from": "accounts@acmeglass.example", "date": _rc._cutoff_day(10)}
    stores["docs"]["m8:a8"] = dict(stores["docs"]["m9:a9"], source_key="m8:a8",
                                   invoice_numbers=["INV-104275"])
    try:
        run_async(_rc.sweep())
        exs = stores["store"]["exceptions"]
        found = [x for x, e in exs.items() if e["kind"] == "gmail_doc_missing_from_xero"]
        eq(len(found), 1, "a bill in the mailbox and not in Xero is found")
        xid = found[0]
        exs[xid]["status"] = "investigating"
        before = _copy.deepcopy(exs[xid])
        for k in ("m9:a9", "m8:a8"):
            stores["docs"][k]["date"] = _rc._cutoff_day(_rc.DOCS_KEEP_DAYS + 5)
        for n in (1, 2, 3):
            run_async(_rc.sweep())
            _left_as_it_was(stores, xid, before, "sweep %d: a document past retention is not a "
                                                  "bill entered" % n)
            ok("m9:a9" in stores["docs"], "the document it rests on is still held")
        ok("m8:a8" not in stores["docs"], "one no open finding rests on is dropped as before")
        fx.invoices.append(_raw_xinv("SUP-4410", "480.00", typ="ACCPAY", contact="Acme Glass"))
        run_async(_rc.sweep())
        e = stores["store"]["exceptions"][xid]
        ok(e["stale"] and _written_off(e), "a sweep that sees the bill in Xero settles it")
    finally:
        _unconfigure_recon()


@test
def t_an_open_sale_or_refund_finding_outlives_the_window():
    """The sale and refund checks have no date horizon of their own, and
    retention keeps the order an open finding rests on, so an order older than
    the window Shopify is read for is still checked from the copy held."""
    refunded = dict(_raw_order(104275, "#104275", "842.00"),
                    refunds=[{"id": 5501, "created_at": _rc._cutoff_day(10),
                              "transactions": [{"kind": "refund", "status": "success",
                                                "amount": "20.00"}]}])
    orders = [refunded, _raw_order(104276, "#104276", "120.00")]
    fx = _FakeXero(invoices=[_raw_xinv("INV-104275", "842.00")])
    stores = _recon_world(fx, orders)
    try:
        run_async(_rc.sweep())
        exs = stores["store"]["exceptions"]
        kinds = ("shopify_sale_missing", "shopify_refund_missing")
        found = sorted(x for x, e in exs.items() if e["kind"] in kinds)
        eq(len(found), 2, "the missing sale and the unrecorded refund are both found")
        for xid in found:
            exs[xid]["status"] = "investigating"
        # Both orders pass the window: Shopify no longer lists them, the cache
        # still holds them.
        old = _rc._cutoff_day(_rc.FETCH_DAYS + 5)
        for o in stores["cache"]["shopify"]["orders"].values():
            o["created_at"] = old
        orders.clear()
        run_async(_rc.sweep())
        for xid in found:
            e = stores["store"]["exceptions"][xid]
            ok(not e.get("stale") and not _written_off(e), e["kind"] + " stays open")
        ok({"104275", "104276"} <= set(stores["cache"]["shopify"]["orders"]), "both orders are held")
    finally:
        _unconfigure_recon()


