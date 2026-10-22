@test
def t_mail_rules_cannot_assign_to_someone_who_cannot_see_the_inbox():
    def go():
        ensure_auth()
        uid_a, _s, _ = ready_user("Ann", "ann")
        post("/api/team/user", {"op": "tabs", "id": uid_a, "tabs": ["overview"]})
        r = post("/api/mail/rules", {"op": "save", "rule": {
            "name": "Bad target", "assign": uid_a,
            "conditions": [{"field": "subject", "op": "contains", "value": "x"}]}})
        eq(r.status_code, 400, "a filter that would bury email is refused at save time")
    with_mail(go)

@test
def t_mail_bulk_assign_matches_the_single_route_exactly():
    """A handover must not erase how far the work had got: flattening
    'waiting on the customer' back to 'assigned' loses the one signal that
    tells the new owner they are not the blocker."""
    def go():
        ensure_auth()
        uid_a, sess_a, _ = ready_user("Ann", "ann")
        uid_b, _sess_b, _ = ready_user("Bob", "bob")
        _seed_thread("w1"); _seed_thread("w2"); _seed_thread("w3")
        post_s(sess_a, "/api/mail/bulk", {"op": "claim", "ids": ["w1", "w2", "w3"]})
        post_s(sess_a, "/api/mail/state", {"id": "w1", "state": "waiting"})
        post_s(sess_a, "/api/mail/state", {"id": "w2", "state": "progress"})
        post("/api/mail/bulk", {"op": "assign", "uid": uid_b, "ids": ["w1", "w2", "w3"]})
        th = mail._load_mail()["threads"]
        eq(th["w1"]["state"], "waiting", "a handover keeps the waiting signal")
        eq(th["w2"]["state"], "progress", "and keeps work already started")
        eq(th["w3"]["state"], "assigned")
        eq(th["w1"]["owner"], uid_b, "while still changing hands")
        # Staff may release their OWN in bulk, exactly as the single route allows.
        post("/api/mail/bulk", {"op": "assign", "uid": uid_a, "ids": ["w1", "w2"]})
        r = post_s(sess_a, "/api/mail/bulk", {"op": "assign", "uid": "", "ids": ["w1", "w3"]})
        eq(r.status_code, 200, r.text)
        eq(r.json()["changed"], 1, "her own goes back to the room")
        ok(any("not yours" in s["why"] for s in r.json()["skipped"]), r.text)
        eq(mail._load_mail()["threads"]["w1"]["state"], "unassigned")
    with_mail(go)

@test
def t_mail_bulk_counts_each_thread_once():
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        _seed_thread("d1")
        r = post_s(sess, "/api/mail/bulk", {"op": "claim", "ids": ["d1", "d1", "d1"]})
        eq(r.json()["changed"], 1, "the same id three times is one decision")
        eq(len([a for a in mail._load_mail()["threads"]["d1"]["activity"]
                if a["action"] == "claimed"]), 1, "and one line in the history")
    with_mail(go)

@test
def t_mail_reconciler_backs_off_a_thread_that_will_never_sync():
    """One thread whose label can never be written must not camp at the head
    of the queue and starve the real drift behind it."""
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        _gm.save_connection("rt-test", MBOX)
        for i in range(4):
            _seed_thread("s%d" % i)
        tries = []
        async def modify(tid, add=None, remove=None):
            tries.append(tid)
            if tid == "s0":
                raise _gm.GmailError("Invalid label")     # permanently broken
        async def label(name, known):
            known[name] = "L1"
            return "L1"
        async def listing(q, n):
            return {"threads": [], "complete": True}
        saved = (_gm.modify_thread, _gm.ensure_label, _gm.list_threads)
        _gm.modify_thread, _gm.ensure_label, _gm.list_threads = modify, label, listing
        try:
            post_s(sess, "/api/mail/bulk", {"op": "claim",
                                            "ids": ["s0", "s1", "s2", "s3"]})
            mail._load_mail()["synced_at"] = ""
            post("/api/mail/board", {"force": True})
            ok("s0" in tries, "the broken one is tried once")
            eq(sorted(set(tries)), ["s0", "s1", "s2", "s3"], "and everything else lands")
            tries.clear()
            mail._load_mail()["synced_at"] = ""
            post("/api/mail/board", {"force": True})
            eq(tries, [], "the next sync retries nothing: the failure is backed off")
            t0 = mail._load_mail()["threads"]["s0"]
            ok(float(t0.get("label_retry_at") or 0) > time.time(),
               "the broken thread carries its own retry time")
        finally:
            _gm.modify_thread, _gm.ensure_label, _gm.list_threads = saved
    with_mail(go)

@test
def t_mail_sync_abandons_a_restore_that_lands_during_the_reconciler():
    """The reconciler is a SECOND network window: the guard before it is not
    enough on its own."""
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("k1")
        post_s(sess, "/api/mail/claim", {"id": "k1"})
        async def listing(q, n):
            return {"threads": [], "complete": True}
        async def label(name, known):
            mail._mail_mem = None      # a restore lands mid-reconcile
            known[name] = "L1"
            return "L1"
        async def modify(tid, add=None, remove=None):
            return None
        saved = (_gm.list_threads, _gm.ensure_label, _gm.modify_thread)
        _gm.list_threads, _gm.ensure_label, _gm.modify_thread = listing, label, modify
        try:
            # Stamp the DISK with a world the abandoned sync must not overwrite,
            # exactly as a restore would.
            store = mail._load_mail()
            store["synced_at"] = ""
            store["threads"]["k1"]["subject"] = "RESTORED"
            mail._write_mail(store)
            r = post("/api/mail/board", {"force": True})
            eq(r.status_code, 200, r.text)
            disk = json.load(open(mail.MAILBOX_PATH))["mailbox"]
            eq(disk["threads"]["k1"]["subject"], "RESTORED",
               "the orphaned sync wrote nothing over the restored world")
            eq(disk["synced_at"], "", "and did not even stamp its own clock")
        finally:
            _gm.list_threads, _gm.ensure_label, _gm.modify_thread = saved
    with_mail(go)

@test
def t_mail_unread_backfills_for_threads_that_predate_the_field():
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        # A thread already in the store from an older build: no unread key.
        _seed_thread("old1")
        mail._load_mail()["threads"]["old1"].pop("unread", None)
        mail._load_mail()["threads"]["old1"]["history_id"] = "h1"
        fetched = []
        async def listing(q, n):
            return {"threads": [{"id": "old1", "snippet": "s", "historyId": "h1"}],
                    "complete": True}
        async def get_thread(tid):
            fetched.append(tid)
            return {"id": tid, "historyId": "h1", "subject": "Old",
                    "messages": [{"id": "m1", "from_name": "Jo",
                                  "from_email": "jo@customer.com",
                                  "at": "2026-08-19T01:00:00+00:00",
                                  "labels": ["INBOX", "UNREAD"], "snippet": "hi"}]}
        saved = (_gm.list_threads, _gm.get_thread)
        _gm.list_threads, _gm.get_thread = listing, get_thread
        try:
            mail._load_mail()["synced_at"] = ""
            post("/api/mail/board", {"force": True})
            eq(fetched, ["old1"], "an unchanged thread is refetched ONCE to fill the gap")
            ok(mail._load_mail()["threads"]["old1"]["unread"],
               "so old mail does not read as already-read forever")
            fetched.clear()
            mail._load_mail()["synced_at"] = ""
            post("/api/mail/board", {"force": True})
            eq(fetched, [], "and never again after that")
        finally:
            _gm.list_threads, _gm.get_thread = saved
    with_mail(go)

@test
def t_mail_unread_comes_from_gmail_not_from_our_own_stale_copy():
    """Marking an email unread in Gmail changes almost nothing else about the
    thread, so a sync that only refetches CHANGED threads would never notice.
    The sync asks Gmail which threads are unread, every time."""
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("u1", subject="One")
        _seed_thread("u2", subject="Two")
        mail._load_mail()["threads"]["u1"]["history_id"] = "h1"
        mail._load_mail()["threads"]["u2"]["history_id"] = "h1"
        queries = []
        unread = {"ids": set()}
        async def listing(q, n):
            queries.append(q)
            return {"threads": [{"id": "u1", "snippet": "s", "historyId": "h1"},
                                {"id": "u2", "snippet": "s", "historyId": "h1"}],
                    "complete": True}
        async def ids(q, max_results=500, pages=8, out_complete=None):
            if out_complete is not None:
                out_complete.append(True)   # the walk saw the whole result set
            queries.append(q)
            return set(unread["ids"])
        saved = (_gm.list_threads, _gm.list_thread_ids)
        _gm.list_threads, _gm.list_thread_ids = listing, ids
        try:
            mail._load_mail()["synced_at"] = ""
            post("/api/mail/board", {"force": True})
            ok(any("is:unread" in q for q in queries), "Gmail is asked outright")
            eq(mail._load_mail()["threads"]["u1"]["unread"], False)
            # Now it is marked unread in Gmail. Nothing else about the thread
            # changes: same historyId, no new message.
            unread["ids"] = {"u2"}
            mail._load_mail()["synced_at"] = ""
            post("/api/mail/board", {"force": True})
            eq(mail._load_mail()["threads"]["u2"]["unread"], True,
               "the app notices without the thread having changed at all")
            eq(mail._load_mail()["threads"]["u1"]["unread"], False)
            # And reading it in Gmail clears it again.
            unread["ids"] = set()
            mail._load_mail()["synced_at"] = ""
            post("/api/mail/board", {"force": True})
            eq(mail._load_mail()["threads"]["u2"]["unread"], False)
        finally:
            _gm.list_threads, _gm.list_thread_ids = saved
    with_mail(go)

@test
def t_a_truncated_inbox_listing_does_not_hide_unread_mail():
    """The unread sweep only wrote to threads it had just seen in the inbox
    LISTING. That listing is capped at MAIL_LIST_MAX and says so - a shared
    mailbox past the cap truncates. A thread that Gmail reports as unread, but
    which fell off the end of that listing, was skipped: the board went on
    showing a customer email as read while Gmail had it bold.

    The incomplete-walk branch below it already promoted every id it saw,
    regardless of the listing, so the SAFE path was more thorough than the
    confident one."""
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("keep", subject="In the listing")
        _seed_thread("fell", subject="Fell off the end")
        m = mail._load_mail()["threads"]
        m["keep"]["history_id"] = "h1"; m["keep"]["unread"] = False
        m["fell"]["history_id"] = "h1"; m["fell"]["unread"] = False
        async def listing(q, n):
            # Truncated: "fell" is genuinely in the Gmail inbox, but past the cap.
            return {"threads": [{"id": "keep", "snippet": "s", "historyId": "h1"}],
                    "complete": False}
        async def ids(q, max_results=500, pages=8, out_complete=None):
            if out_complete is not None:
                out_complete.append(True)      # the unread walk DID see everything
            return {"keep", "fell"}
        saved = (_gm.list_threads, _gm.list_thread_ids)
        _gm.list_threads, _gm.list_thread_ids = listing, ids
        try:
            mail._load_mail()["synced_at"] = ""
            post("/api/mail/board", {"force": True})
            t = mail._load_mail()["threads"]
            eq(t["keep"]["unread"], True, "the thread inside the listing is right")
            eq(t["fell"]["unread"], True,
               "and so is the one Gmail reported unread from outside it")
        finally:
            _gm.list_threads, _gm.list_thread_ids = saved
    with_mail(go)

@test
def t_a_thread_read_in_gmail_after_archiving_stops_showing_unread():
    """The authoritative query was scoped "in:inbox is:unread", so an ARCHIVED
    thread appeared in neither the listing nor the unread set and kept whatever
    flag it last had. Archive an unread email, then read it in Gmail, and the
    board went on calling it unread forever - and the Inbox tells the merchant
    "N unread emails are not in this view", so it is a standing false alarm."""
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("arch", subject="Archived then read")
        m = mail._load_mail()["threads"]
        m["arch"]["history_id"] = "h1"; m["arch"]["unread"] = True
        m["arch"]["in_inbox"] = False; m["arch"]["state"] = "done"
        async def listing(q, n):
            return {"threads": [], "complete": True}      # archived: not in the inbox
        async def ids(q, max_results=500, pages=8, out_complete=None):
            if out_complete is not None:
                out_complete.append(True)
            return set()                                   # Gmail: nothing is unread
        saved = (_gm.list_threads, _gm.list_thread_ids)
        _gm.list_threads, _gm.list_thread_ids = listing, ids
        try:
            mail._load_mail()["synced_at"] = ""
            post("/api/mail/board", {"force": True})
            eq(mail._load_mail()["threads"]["arch"]["unread"], False,
               "Gmail says nothing is unread, so the board must not still claim it is")
        finally:
            _gm.list_threads, _gm.list_thread_ids = saved
    with_mail(go)

@test
def t_a_thread_older_than_the_window_is_never_demoted_on_silence():
    """The authoritative query is windowed (newer_than:MAIL_TRACK_DAYS). Prune
    only drops DONE threads, so a live one can outlive that window - and the
    query never looked at it. Absence from a search that did not cover it is
    not evidence it was read."""
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("ancient", subject="Older than the window")
        t = mail._load_mail()["threads"]["ancient"]
        t["history_id"] = "h1"; t["unread"] = True; t["in_inbox"] = False
        t["last_at"] = "2019-01-01T00:00:00+00:00"      # far outside the window
        async def listing(q, n):
            return {"threads": [], "complete": True}
        async def ids(q, max_results=500, pages=8, out_complete=None):
            if out_complete is not None:
                out_complete.append(True)
            return set()          # the windowed query simply never saw it
        saved = (_gm.list_threads, _gm.list_thread_ids)
        _gm.list_threads, _gm.list_thread_ids = listing, ids
        try:
            mail._load_mail()["synced_at"] = ""
            post("/api/mail/board", {"force": True})
            eq(mail._load_mail()["threads"]["ancient"]["unread"], True,
               "silence from a query that did not cover it is not proof it was read")
        finally:
            _gm.list_threads, _gm.list_thread_ids = saved
    with_mail(go)

@test
def t_mail_bulk_can_be_undone():
    """One mis-click moves 150 emails. That has to be recoverable."""
    def go():
        ensure_auth()
        uid_a, sess_a, _ = ready_user("Ann", "ann")
        _uid_b, sess_b, _ = ready_user("Bob", "bob")
        for i in range(3):
            _seed_thread("u%d" % i)
        post_s(sess_a, "/api/mail/bulk", {"op": "claim", "ids": ["u0", "u1", "u2"]})
        post_s(sess_a, "/api/mail/state", {"id": "u0", "state": "waiting"})
        r = post_s(sess_a, "/api/mail/bulk", {"op": "state", "state": "done",
                                              "ids": ["u0", "u1", "u2"]})
        eq(r.status_code, 200, r.text)
        token = r.json()["undo"]
        ok(token, "an undo is offered")
        eq(mail._load_mail()["threads"]["u0"]["state"], "done")
        eq(post_s(sess_b, "/api/mail/undo", {"token": token}).status_code, 403,
           "somebody else's mis-click is not theirs to undo")
        u = post_s(sess_a, "/api/mail/undo", {"token": token})
        eq(u.status_code, 200, u.text)
        eq(u.json()["restored"], 3)
        th = mail._load_mail()["threads"]
        eq(th["u0"]["state"], "waiting", "the exact state before, not a guess at it")
        eq(th["u0"]["owner"], uid_a)
        eq(th["u1"]["state"], "assigned", "and the ones she had just claimed are back to that")
        eq(post_s(sess_a, "/api/mail/undo", {"token": token}).status_code, 404,
           "an undo is a second chance, not a version history")
    with_mail(go)

@test
def t_mail_attachments_are_listed_without_touching_the_bytes():
    """A 20MB artwork file has no business in a board refresh: the listing
    reads names and sizes from the part tree, never the bytes."""
    import base64 as _b64
    enc = lambda x: _b64.urlsafe_b64encode(x.encode()).decode().rstrip("=")
    payload = {"mimeType": "multipart/mixed", "headers": [
        {"name": "From", "value": "Jo <jo@customer.com>"},
        {"name": "Subject", "value": "Artwork attached"}], "parts": [
        {"mimeType": "text/plain", "body": {"data": enc("here is the logo")}},
        {"mimeType": "application/postscript", "filename": "logo.eps",
         "body": {"attachmentId": "att1", "size": 240000}},
        {"mimeType": "message/rfc822", "filename": "forwarded.eml", "parts": [
            {"mimeType": "image/png", "filename": "inner.png",
             "body": {"attachmentId": "att9", "size": 10}}]}]}
    files = []
    _gm._walk_files(payload, files)
    names = [f["name"] for f in files]
    eq(names, ["logo.eps", "forwarded.eml"],
       "the attached email is one file, not a door into its contents")
    eq(files[0]["size"], 240000)
    ok(all("data" not in f for f in files), "no bytes are carried")

@test
def t_mail_attachment_save_lands_in_the_files_store():
    def go():
        ensure_auth()
        def inner(fake):
            _seed_thread("t1")
            mail._load_mail()["threads"]["t1"]["files"] = [
                {"name": "logo.eps", "size": 12, "mime": "application/postscript",
                 "id": "att1", "msg": "m1"}]
            async def bytes_for(msg_id, att_id, cap=None):
                eq((msg_id, att_id), ("m1", "att1"))
                return b"EPS-BYTES"
            saved = _gm.attachment_bytes
            _gm.attachment_bytes = bytes_for
            try:
                r = post("/api/mail/attachment", {"id": "t1", "msg": "m1", "att": "att1",
                                                  "name": "logo.eps", "folder": "Artwork/#1201"})
                eq(r.status_code, 200, r.text)
                eq(r.json()["where"], "Artwork/#1201")
                d = fileserver._load_files()
                rec = [f for f in d["files"].values() if f["name"] == "logo.eps"]
                eq(len(rec), 1, "one file record")
                eq(rec[0]["status"], "active")
                # The folders were made on the way, so nobody has to first.
                names = [f["name"] for f in d["folders"].values()]
                ok("Artwork" in names and "#1201" in names, names)
                t = mail._load_mail()["threads"]["t1"]
                ok(any(x["name"] == "logo.eps" for x in t.get("saved_files") or []),
                   "the thread records that it was filed")
                ok(any("logo.eps" in a["action"] for a in t["activity"]))
            finally:
                _gm.attachment_bytes = saved
        with_files(inner)
    with_mail(go)

@test
def t_mail_order_context_matches_only_the_exact_sender():
    """Showing one customer another customer's address and tracking is the
    failure that matters here, so the match is the exact address or nothing."""
    def go():
        ensure_auth()
        _seed_thread("t1", frm=("Jo Bloggs", "jo@customer.com"))
        calls = []
        async def fake_tool(reg, name, args):
            calls.append((name, args))
            if name == "shopify_search_customers":
                # Shopify search is fuzzy and returns near misses: the route
                # must throw those away rather than trust the first row.
                return {"customers": [
                    {"id": 9, "email": "jo@customer.com.evil.net", "first_name": "Not", "last_name": "Them"},
                    {"id": 1, "email": "Jo@Customer.com", "first_name": "Jo", "last_name": "Bloggs",
                     "orders_count": 3, "total_spent": "740.00"}]}
            return {"orders": [
                {"id": 501, "name": "#1201", "created_at": "2026-08-10T09:00:00Z",
                 "total_price": "248.00", "currency": "GBP"},
                {"id": 502, "name": "#1188", "created_at": "2026-07-02T09:00:00Z",
                 "total_price": "96.00", "currency": "GBP"}]}
        saved = shopify._tool_json
        shopify._tool_json = fake_tool
        prod = production._load_prod_state()
        disp = desk._load_dispatch()
        try:
            prod["501"] = {"made_at": "2026-08-12T10:00:00Z", "printed_at": "2026-08-11T10:00:00Z"}
            disp["501"] = {"tracking_number": "4512339981", "carrier_label": "DPD",
                           "dispatched_at": "2026-08-13T10:00:00Z", "fulfilled": True}
            production._write_prod_state(prod)
            desk._write_dispatch(disp)
            r = post("/api/mail/orders", {"id": "t1"})
            eq(r.status_code, 200, r.text)
            j = r.json()
            eq(j["customer"]["name"], "Jo Bloggs", "the lookalike address was discarded")
            eq(len(j["orders"]), 2)
            top = j["orders"][0]
            eq(top["name"], "#1201")
            eq(top["tracking"], "4512339981", "what WE know, not just what Shopify knows")
            ok("shipped" in top["sentence"] and "DPD" in top["sentence"], top["sentence"])
            ok("not yet shipped" in j["orders"][1]["sentence"], j["orders"][1]["sentence"])
            # A sender we have never traded with produces nothing, not a guess.
            _seed_thread("t2", frm=("Stranger", "nobody@elsewhere.com"))
            eq(post("/api/mail/orders", {"id": "t2"}).json()["orders"], [])
        finally:
            shopify._tool_json = saved
    with_mail(go)

@test
def t_mail_booked_label_is_not_shipped():
    """Booking a courier label happens BEFORE the gobo is made. Telling a
    customer it shipped sends them chasing a courier that has nothing."""
    def go():
        ensure_auth()
        _seed_thread("t1", frm=("Jo", "jo@customer.com"))
        async def fake_tool(reg, name, args):
            if name == "shopify_search_customers":
                return {"customers": [{"id": 1, "email": "jo@customer.com",
                                       "first_name": "Jo", "orders_count": 1}]}
            return {"orders": [{"id": 700, "name": "#1300",
                                "created_at": "2026-08-18T09:00:00Z"}]}
        saved = shopify._tool_json
        shopify._tool_json = fake_tool
        disp = desk._load_dispatch()
        try:
            disp["700"] = {"tracking_number": "TRK1", "carrier_label": "DPD",
                           "dispatched_at": "2026-08-19T09:00:00Z", "fulfilled": False}
            desk._write_dispatch(disp)
            sent = post("/api/mail/orders", {"id": "t1"}).json()["orders"][0]["sentence"]
            ok("not handed over yet" in sent, sent)
            ok("shipped" not in sent.replace("not handed over", ""), sent)
            disp["700"]["fulfilled"] = True
            desk._write_dispatch(disp)
            sent2 = post("/api/mail/orders", {"id": "t1"}).json()["orders"][0]["sentence"]
            ok(sent2.startswith("#1300, shipped"), sent2)
        finally:
            shopify._tool_json = saved
    with_mail(go)

@test
def t_mail_draft_withholds_order_facts_when_the_reply_goes_elsewhere():
    """From and Reply-To are both chosen by whoever sent the email. Looking
    up one and writing to the other is how one customer's tracking number
    reaches somebody else."""
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1", frm=("Jo", "jo@customer.com"))
        async def fake_read(tid, per_msg_chars=4000):
            return {"id": tid, "messages": [
                {"id": "m1", "from_name": "Jo", "from_email": "jo@customer.com",
                 "reply_to": "somebody-else@elsewhere.com", "subject": "Order",
                 "message_id": "<a@b>", "references": "",
                 "at": "2026-08-19T01:00:00+00:00", "text": "where is it?"}]}
        seen = {}
        class _Blk:
            type = "text"
            def __init__(self, t): self.text = t
        class _Resp:
            content = [_Blk("Hi, checking now.")]
            usage = None
        async def fake_create(client, **kw):
            seen.update(kw)
            return _Resp()
        looked_up = []
        async def fake_tool(reg, name, args):
            looked_up.append(args)
            return {"customers": [], "orders": []}
        saved = (_gm.read_thread, claude._xcreate, claude.ANTHROPIC_API_KEY, shopify._tool_json)
        _gm.read_thread, claude._xcreate = fake_read, fake_create
        claude.ANTHROPIC_API_KEY, shopify._tool_json = "x", fake_tool
        try:
            r = post("/api/mail/draft", {"id": "t1", "op": "compose"})
            eq(r.status_code, 200, r.text)
            prompt = seen["messages"][0]["content"]
            ok("Do NOT state any order, delivery or tracking detail" in prompt,
               "the model is told to hold back")
            ok("somebody-else@elsewhere.com" in prompt, prompt[:300])
            eq(looked_up, [], "and no orders were even fetched")
        finally:
            _gm.read_thread, claude._xcreate, claude.ANTHROPIC_API_KEY, shopify._tool_json = saved
    with_mail(go)

@test
def t_mail_sync_only_closes_what_it_can_prove_was_archived():
    """Falling off the end of one Gmail page is not the same as being
    archived. Treating it as archived silently closes live customer email."""
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("keep1"); _seed_thread("keep2")
        import datetime as _dtm
        fresh = _dtm.datetime.now(_dtm.timezone.utc).isoformat()
        for tid in ("keep1", "keep2"):
            mail._load_mail()["threads"][tid]["in_inbox"] = True
            mail._load_mail()["threads"][tid]["last_at"] = fresh
        state = {"complete": False}
        async def listing(q, n):
            # keep2 is missing, but the listing admits it is truncated.
            return {"threads": [{"id": "keep1", "snippet": "s", "historyId": "h1"}],
                    "complete": state["complete"]}
        async def ids(q, max_results=500, pages=8, out_complete=None):
            if out_complete is not None:
                out_complete.append(True)   # the walk saw the whole result set
            return set()
        saved = (_gm.list_threads, _gm.list_thread_ids)
        _gm.list_threads, _gm.list_thread_ids = listing, ids
        try:
            mail._load_mail()["synced_at"] = ""
            post("/api/mail/board", {"force": True})
            eq(mail._load_mail()["threads"]["keep2"]["state"], "unassigned",
               "a truncated listing never closes anything")
            # Now the listing is complete, so absence really does mean archived.
            state["complete"] = True
            mail._load_mail()["synced_at"] = ""
            post("/api/mail/board", {"force": True})
            t = mail._load_mail()["threads"]["keep2"]
            eq(t["state"], "done", "a complete listing is proof")
            eq(t["closed_by"], "archive")
            # And it comes BACK when the thread returns, which is what Gmail's
            # own snooze does with no new message.
            async def listing2(q, n):
                return {"threads": [{"id": "keep1", "snippet": "s", "historyId": "h1"},
                                    {"id": "keep2", "snippet": "s", "historyId": "h1"}],
                        "complete": True}
            _gm.list_threads = listing2
            mail._load_mail()["synced_at"] = ""
            post("/api/mail/board", {"force": True})
            eq(mail._load_mail()["threads"]["keep2"]["state"], "unassigned",
               "a snoozed email is not closed forever")
        finally:
            _gm.list_threads, _gm.list_thread_ids = saved
    with_mail(go)

@test
def t_mail_attachment_supersedes_the_same_name():
    def go():
        ensure_auth()
        def inner(fake):
            _seed_thread("t1")
            mail._load_mail()["threads"]["t1"]["files"] = [
                {"name": "proof.pdf", "size": 9, "id": "att1", "msg": "m1"}]
            async def bytes_for(msg_id, att_id, cap=None):
                return b"%PDF-1.4 PDF-BYTES"
            saved = _gm.attachment_bytes
            _gm.attachment_bytes = bytes_for
            try:
                for _ in range(2):
                    r = post("/api/mail/attachment", {"id": "t1", "msg": "m1", "att": "att1",
                                                      "name": "proof.pdf", "folder": "Artwork"})
                    eq(r.status_code, 200, r.text)
                d = fileserver._load_files()
                live = [f for f in d["files"].values()
                        if f["name"] == "proof.pdf" and f["status"] == "active"]
                eq(len(live), 1, "one live proof.pdf, so the drive can reach it")
                gone = [f for f in d["files"].values()
                        if f["name"] == "proof.pdf" and f["status"] == "trashed"]
                eq(len(gone), 1, "and the earlier one is in the 30-day trash, not deleted")
            finally:
                _gm.attachment_bytes = saved
        with_files(inner)
    with_mail(go)

@test
def t_mail_undo_never_restores_an_owner_who_cannot_hold_email():
    def go():
        ensure_auth()
        uid_a, sess_a, _ = ready_user("Ann", "ann")
        _seed_thread("u1")
        post_s(sess_a, "/api/mail/claim", {"id": "u1"})
        r = post("/api/mail/bulk", {"op": "assign", "uid": "", "ids": ["u1"]})
        token = r.json()["undo"]
        post("/api/team/user", {"op": "active", "id": uid_a, "active": False})
        u = post("/api/mail/undo", {"token": token})
        eq(u.status_code, 200, u.text)
        t = mail._load_mail()["threads"]["u1"]
        eq(t["owner"], "", "the email is not buried on a switched-off account")
        eq(t["state"], "unassigned")
    with_mail(go)

@test
def t_mail_order_context_honours_the_customers_tab():
    def go():
        ensure_auth()
        uid, sess, _ = ready_user("Ann", "ann")
        post("/api/team/user", {"op": "tabs", "id": uid, "tabs": ["mail"]})
        _seed_thread("t1")
        eq(post_s(sess, "/api/mail/orders", {"id": "t1"}).json()["orders"], [],
           "no customers tab, no order history through the side door")
    with_mail(go)

@test
def t_mail_read_state_is_bidirectional_with_gmail():
    """Reading here marks it read THERE, and back again. Read state belongs
    to the mailbox, so the Gmail call is what counts and the board follows."""
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        mail._load_mail()["threads"]["t1"]["unread"] = True
        calls = []
        async def modify(tid, add=None, remove=None):
            calls.append({"id": tid, "add": add, "remove": remove})
        saved = _gm.modify_thread
        _gm.modify_thread = modify
        try:
            # Opening the thread in the app marks it read in Gmail.
            r = post_s(sess, "/api/mail/thread", {"id": "t1"})
            eq(r.status_code, 200, r.text)
            eq(calls, [{"id": "t1", "add": None, "remove": ["UNREAD"]}],
               "Gmail is told, the same as opening it there")
            eq(mail._load_mail()["threads"]["t1"]["unread"], False)
            # Opening it again does not nag Gmail a second time.
            calls.clear()
            post_s(sess, "/api/mail/thread", {"id": "t1"})
            eq(calls, [], "an already-read thread is left alone")
            # And it can be put back, which is how an accidental open is undone.
            r2 = post_s(sess, "/api/mail/read", {"id": "t1", "unread": True})
            eq(r2.status_code, 200, r2.text)
            eq(calls, [{"id": "t1", "add": ["UNREAD"], "remove": None}])
            ok(mail._load_mail()["threads"]["t1"]["unread"])
        finally:
            _gm.modify_thread = saved
    with_mail(go)

@test
def t_mail_read_reports_when_gmail_refuses():
    """The board must never claim a read state Gmail did not accept: the two
    would disagree the moment anybody opened Gmail."""
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        mail._load_mail()["threads"]["t1"]["unread"] = True
        async def boom(tid, add=None, remove=None):
            raise _gm.GmailError("backend error")
        saved = _gm.modify_thread
        _gm.modify_thread = boom
        try:
            r = post("/api/mail/read", {"id": "t1", "unread": False})
            eq(r.status_code, 502, "a refusal is reported, not swallowed")
            ok(mail._load_mail()["threads"]["t1"]["unread"],
               "and the board keeps the state Gmail still holds")
            # Bulk: some succeed, some do not, and the answer says so.
            _seed_thread("t2")
            mail._load_mail()["threads"]["t2"]["unread"] = True
            async def half(tid, add=None, remove=None):
                if tid == "t1":
                    raise _gm.GmailError("nope")
            _gm.modify_thread = half
            r2 = post("/api/mail/read", {"ids": ["t1", "t2"], "unread": False})
            eq(r2.status_code, 200, r2.text)
            eq(r2.json()["changed"], 1)
            eq(r2.json()["failed"], 1)
            ok(mail._load_mail()["threads"]["t1"]["unread"], "the failed one is untouched")
            ok(not mail._load_mail()["threads"]["t2"]["unread"], "the other one moved")
        finally:
            _gm.modify_thread = saved
    with_mail(go)

@test
def t_mail_unread_survives_being_marked_done():
    """The backlog-clearing gesture marks everything done. An email marked
    unread in Gmail afterwards must still be findable, or it is invisible."""
    def go():
        ensure_auth()
        _seed_thread("d1", subject="Cleared then reopened by the customer")
        post("/api/mail/bulk", {"op": "state", "state": "done", "ids": ["d1"]})
        mail._load_mail()["threads"]["d1"]["unread"] = True
        row = [t for t in post("/api/mail/board", {}).json()["threads"]
               if t["id"] == "d1"][0]
        eq(row["state"], "done")
        ok(row["unread"], "the board still reports it as unread")
    with_mail(go)

@test
def t_mail_unread_rides_along_from_gmail():
    def go():
        ensure_auth()
        store = mail._load_mail()
        msgs = [{"id": "m1", "from_name": "Jo", "from_email": "jo@customer.com",
                 "at": "2026-08-19T01:00:00+00:00", "snippet": "hi",
                 "labels": ["INBOX", "UNREAD"]}]
        mail._mail_apply_thread(store, {"id": "t1", "historyId": "h1",
                                           "subject": "New one", "messages": msgs}, MBOX)
        ok(store["threads"]["t1"]["unread"], "an unopened thread is marked unread")
        ok(post("/api/mail/board", {}).json()["threads"][0]["unread"], "and reaches the list")
        msgs[0]["labels"] = ["INBOX"]
        mail._mail_apply_thread(store, {"id": "t1", "historyId": "h2",
                                           "subject": "New one", "messages": msgs}, MBOX)
        ok(not store["threads"]["t1"]["unread"], "reading it in Gmail clears the bold")
    with_mail(go)

@test
def t_mail_label_reconciler_catches_gmail_up_after_bulk():
    """Bulk does not call Gmail: three hundred threads must not become three
    hundred blocking calls. The sync walks the drift away instead."""
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        _gm.save_connection("rt-test", MBOX)
        for i in range(3):
            _seed_thread("r%d" % i)
        calls = []
        async def fake_modify(tid, add=None, remove=None):
            calls.append(tid)
        async def fake_label(name, known):
            known[name] = "L1"
            return "L1"
        async def fake_list(q, n):
            return {"threads": [], "complete": True}
        saved = (_gm.modify_thread, _gm.ensure_label, _gm.list_threads)
        _gm.modify_thread, _gm.ensure_label, _gm.list_threads = fake_modify, fake_label, fake_list
        try:
            post_s(sess, "/api/mail/bulk", {"op": "claim", "ids": ["r0", "r1", "r2"]})
            eq(calls, [], "bulk never touches Gmail")
            mail._load_mail()["synced_at"] = ""
            post("/api/mail/board", {"force": True})
            eq(sorted(calls), ["r0", "r1", "r2"], "the next sync catches Gmail up")
            calls.clear()
            mail._load_mail()["synced_at"] = ""
            post("/api/mail/board", {"force": True})
            eq(calls, [], "and stops once there is no drift left")
        finally:
            _gm.modify_thread, _gm.ensure_label, _gm.list_threads = saved
    with_mail(go)

@test
def t_mail_setup_aids_name_the_existing_project_master_only():
    """The merchant could not find which Cloud project his app already uses.
    The app knows: the client id's numeric prefix IS the project number."""
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        saved = _gm.OAUTH_CLIENT_ID
        _gm.OAUTH_CLIENT_ID = "123456789012-abcdefg.apps.googleusercontent.com"
        try:
            j = post("/api/mail/board", {}).json()
            eq(j["setup"]["project"], "123456789012", "the project number is derived, not asked for")
            ok(j["setup"]["redirect_uri"].endswith("/oauth/gmail/callback"),
               "and the EXACT callback is handed over, never retyped")
            eq(post_s(sess, "/api/mail/board", {}).json()["setup"], {},
               "setup aids are the master's business only")
            # A connected mailbox has no setup left to do.
            _gm.save_connection("rt-test", MBOX)
            eq(post("/api/mail/board", {}).json()["setup"], {},
               "and they disappear once it is connected")
        finally:
            _gm.OAUTH_CLIENT_ID = saved
    with_mail(go)

@test
def t_mail_connect_ticket_expires():
    def go():
        ensure_auth()
        saved = (_gm.OAUTH_CLIENT_ID, _gm.OAUTH_CLIENT_SECRET)
        _gm.OAUTH_CLIENT_ID = _gm.OAUTH_CLIENT_SECRET = "demo"
        try:
            url = post("/api/mail/connect-link", {}).json()["url"]
            ticket = url.split("t=", 1)[1]
            mail._mail_connect_tickets[ticket] = time.time() - 1   # age it
            eq(client.get("/oauth/gmail/start", params={"t": ticket},
                          follow_redirects=False).status_code, 403,
               "a stale ticket is refused")
        finally:
            _gm.OAUTH_CLIENT_ID, _gm.OAUTH_CLIENT_SECRET = saved
            mail._mail_connect_tickets.clear()
    with_mail(go)

@test
def t_gmail_snippets_lose_their_html_entities_at_the_boundary_and_in_the_store():
    """Gmail HTML-escapes snippets, so the board said &#39; where an
    apostrophe belonged - in the list, on cards, and in a deal's Email panel.
    Unescaped once at the connector; and snippets stored escaped by earlier
    builds are cleaned as the store loads, because a thread whose historyId
    never changes again would keep the &#39; forever."""
    def go():
        async def fake_call(method, path, params=None, **kw):
            if path == "threads":
                return {"threads": [{"id": "t1", "historyId": "h",
                                     "snippet": "It&#39;s Jo &amp; Co&#39;s order"}]}
            return {"id": "t1", "historyId": "h", "messages": [
                {"id": "m1", "snippet": "We&#39;d like a quote", "labelIds": [],
                 "payload": {"headers": [{"name": "From", "value": "Jo <jo@x.com>"},
                                         {"name": "Subject", "value": "Quote"}]}}]}
        saved = _gm._call
        _gm._call = fake_call
        try:
            lst = run_async(_gm.list_threads("in:inbox", 10))
            eq(lst["threads"][0]["snippet"], "It's Jo & Co's order")
            th = run_async(_gm.get_thread("t1"))
            eq(th["messages"][0]["snippet"], "We'd like a quote")
        finally:
            _gm._call = saved
        # The migration: a store written by an earlier build heals on load.
        mail._mail_mem = None
        os.makedirs(os.path.dirname(mail.MAILBOX_PATH) or ".", exist_ok=True)
        with open(mail.MAILBOX_PATH, "w", encoding="utf-8") as fh:
            json.dump({"mailbox": {"version": 1, "labels": {}, "rules": [], "seq": 0,
                       "threads": {"old1": {"id": "old1", "snippet": "Jo&#39;s gobos",
                                            "messages": [{"id": "m", "snippet": "it&#39;s fine"}]}}}}, fh)
        store = mail._load_mail()
        eq(store["threads"]["old1"]["snippet"], "Jo's gobos")
        eq(store["threads"]["old1"]["messages"][0]["snippet"], "it's fine")
    with_mail(go)

@test
def t_the_inbox_window_reaches_two_years_and_the_walk_can_get_there():
    """60 days was a triage window; with deals carrying their correspondence
    the inbox is the shop's email HISTORY. The window, the done-keep and the
    cap must all agree, and the Gmail walk must actually be able to fetch a
    two-year listing - the old fixed six-page walk silently clipped at 3000."""
    ok(mail.MAIL_TRACK_DAYS >= 730, f"window is {mail.MAIL_TRACK_DAYS} days")
    ok(mail.MAIL_DONE_KEEP_DAYS >= mail.MAIL_TRACK_DAYS,
       "done threads survive as long as the window reaches")
    ok(mail.MAIL_THREADS_CAP > mail.MAIL_LIST_MAX * 0.8,
       "the store cap does not quietly undo the listing size")
    pages = []
    async def fake_call(method, path, params=None, **kw):
        pages.append(dict(params or {}))
        start = len(pages[:-1]) * 500
        return {"threads": [{"id": f"t{start + i}", "historyId": "h"} for i in range(500)],
                "nextPageToken": "more"}
    saved = _gm._call
    _gm._call = fake_call
    try:
        got = run_async(_gm.list_threads("in:inbox newer_than:730d", 4000))
    finally:
        _gm._call = saved
    eq(len(got["threads"]), 4000, "the walk reaches what it was asked for")
    ok(not got["complete"], "and says honestly that the mailbox holds more")

@test
def t_every_release_path_starts_the_30_day_clock():
    """Printing the labels IS a release - it is the ordinary way an order
    reaches the workbench - so an account order's payment clock must start
    there too, not only on the Ready-to-make button."""
    reset_dispatch(); reset_prod()
    calls = []
    async def fake_terms(order_id):
        calls.append(int(order_id)); return {"ok": True}
    saved_terms, saved_tags = shopify._payment_terms_writer, ORDER["tags"]
    shopify._payment_terms_writer = fake_terms
    try:
        ORDER["tags"] = "Unprocessed, purchase order unpaid"
        r = post("/api/production-state", {"op": "printed", "ids": [12345]}).json()
        eq(calls, [12345], "printing an unpaid PO attaches its terms")
        ok("30-day" in r.get("terms_note", ""), r)
        # An ordinary order still gets nothing.
        calls.clear(); ORDER["tags"] = "Unprocessed"
        post("/api/production-state", {"op": "printed", "ids": [12345]})
        eq(calls, [], "no unpaid tag, no terms")
    finally:
        shopify._payment_terms_writer, ORDER["tags"] = saved_terms, saved_tags

