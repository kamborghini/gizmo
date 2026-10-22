# =========================== shared inbox ==================================
# The Gmail connector is a seam: these tests drive the store, the ownership
# rules and the sync pipeline with a faked google_mail, never the network.

import google_mail as _gm

def with_mail(fn):
    """Fresh mail store + fresh accounts world; the Gmail module's token file
    is wiped too so connected() answers honestly."""
    def go():
        mail._mail_mem = None
        mail._mail_viewers.clear()
        for p in (mail.MAILBOX_PATH, _gm.TOKEN_PATH):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
            jsonstore._poisoned_stores.discard(p)
        try:
            fn()
        finally:
            mail._mail_mem = None
            mail._mail_viewers.clear()
    with_accounts(go)

def _mk_msg(mid, frm_name, frm_email, at, snippet="hello"):
    return {"id": mid, "from_name": frm_name, "from_email": frm_email,
            "at": at, "snippet": snippet}

MBOX = "sales@test-store.co.uk"

def _seed_thread(tid="t1", subject="Gobo order", n=1, frm=("Jo Bloggs", "jo@customer.com")):
    msgs = [_mk_msg(f"{tid}-m{i}", frm[0], frm[1], f"2026-08-19T0{i}:00:00+00:00")
            for i in range(1, n + 1)]
    mail._mail_apply_thread(mail._load_mail(), {
        "id": tid, "historyId": "h1", "subject": subject, "messages": msgs}, MBOX)

@test
def t_mail_arrival_and_message_transitions():
    def go():
        ensure_auth()
        store = mail._load_mail()
        _seed_thread("t1", "Gobo order", n=2)
        t = store["threads"]["t1"]
        eq(t["state"], "unassigned", "a new thread belongs to nobody")
        eq(t["from_email"], "jo@customer.com")
        eq(t["msg_count"], 2)
        # Our own reply from Gmail is logged but moves nothing.
        t["state"] = "waiting"
        mail._mail_apply_thread(store, {"id": "t1", "historyId": "h2", "subject": "Gobo order",
            "messages": [_mk_msg("t1-m1", "Jo Bloggs", "jo@customer.com", "2026-08-19T01:00:00+00:00"),
                         _mk_msg("t1-m2", "Jo Bloggs", "jo@customer.com", "2026-08-19T02:00:00+00:00"),
                         _mk_msg("t1-m3", "Sales", MBOX, "2026-08-19T03:00:00+00:00")]}, MBOX)
        eq(t["state"], "waiting", "our reply does not move the state")
        ok(any(a["action"] == "replied from Gmail" for a in t["activity"]))
        # The customer replying flips waiting back to progress.
        mail._mail_apply_thread(store, {"id": "t1", "historyId": "h3", "subject": "Gobo order",
            "messages": [_mk_msg("t1-m3", "Sales", MBOX, "2026-08-19T03:00:00+00:00"),
                         _mk_msg("t1-m4", "Jo Bloggs", "jo@customer.com", "2026-08-19T04:00:00+00:00")]}, MBOX)
        eq(t["state"], "progress", "a customer reply wakes a waiting thread")
        # The sender stays the customer even though our address appears.
        eq(t["from_email"], "jo@customer.com")
    with_mail(go)

@test
def t_mail_reopen_goes_to_the_previous_owner_if_still_active():
    def go():
        ensure_auth()
        uid, _sess, _pw = ready_user("Dan", "dan")
        store = mail._load_mail()
        _seed_thread("t1")
        t = store["threads"]["t1"]
        t["owner"], t["state"], t["done_at"] = uid, "done", "2026-08-01T00:00:00+00:00"
        mail._mail_apply_thread(store, {"id": "t1", "historyId": "h9", "subject": "Gobo order",
            "messages": [_mk_msg("t1-m1", "Jo", "jo@customer.com", "2026-08-19T01:00:00+00:00"),
                         _mk_msg("t1-m9", "Jo", "jo@customer.com", "2026-08-19T09:00:00+00:00")]}, MBOX)
        eq(t["state"], "assigned", "a reopened thread returns to its owner")
        eq(t["owner"], uid)
        eq(t["done_at"], "")
        # Same again with the owner switched off: back to the room instead.
        post("/api/team/user", {"op": "active", "id": uid, "active": False})
        t["state"], t["done_at"] = "done", "2026-08-01T00:00:00+00:00"
        mail._mail_apply_thread(store, {"id": "t1", "historyId": "ha", "subject": "Gobo order",
            "messages": [_mk_msg("t1-m1", "Jo", "jo@customer.com", "2026-08-19T01:00:00+00:00"),
                         _mk_msg("t1-m9", "Jo", "jo@customer.com", "2026-08-19T09:00:00+00:00"),
                         _mk_msg("t1-mb", "Jo", "jo@customer.com", "2026-08-19T10:00:00+00:00")]}, MBOX)
        eq(t["state"], "unassigned", "a dead owner never buries email")
        eq(t["owner"], "")
    with_mail(go)

@test
def t_mail_claim_is_first_come_single_owner():
    def go():
        ensure_auth()
        _uid_a, sess_a, _ = ready_user("Ann", "ann")
        uid_b, sess_b, _ = ready_user("Bob", "bob")
        _seed_thread("t1")
        r = post_s(sess_a, "/api/mail/claim", {"id": "t1"})
        eq(r.status_code, 200, r.text)
        t = mail._load_mail()["threads"]["t1"]
        eq(t["state"], "assigned")
        r2 = post_s(sess_b, "/api/mail/claim", {"id": "t1"})
        eq(r2.status_code, 409, "one owner per thread is the whole point")
        ok("Ann" in r2.json()["error"], "the refusal names the current owner")
        # A member cannot assign to someone else...
        r3 = post_s(sess_b, "/api/mail/assign", {"id": "t1", "uid": uid_b})
        eq(r3.status_code, 403, "staff do not take work off each other")
        # ...but a lead can, and the handover note travels with it.
        r4 = post("/api/mail/assign", {"id": "t1", "uid": uid_b,
                                       "note": "Bob knows this customer"})
        eq(r4.status_code, 200, r4.text)
        t = mail._load_mail()["threads"]["t1"]
        eq(t["owner"], uid_b)
        ok(any(n["text"] == "Bob knows this customer" for n in t["notes"]))
        ok(any("assigned to Bob" in a["action"] for a in t["activity"]))
    with_mail(go)

@test
def t_mail_state_moves_are_owner_or_lead_only():
    def go():
        ensure_auth()
        uid_a, sess_a, _ = ready_user("Ann", "ann")
        _uid_b, sess_b, _ = ready_user("Bob", "bob")
        _seed_thread("t1")
        post_s(sess_a, "/api/mail/claim", {"id": "t1"})
        eq(post_s(sess_b, "/api/mail/state", {"id": "t1", "state": "progress"}).status_code,
           403, "not Bob's thread")
        eq(post_s(sess_a, "/api/mail/state", {"id": "t1", "state": "progress"}).status_code, 200)
        eq(post_s(sess_a, "/api/mail/state", {"id": "t1", "state": "nonsense"}).status_code, 400)
        r = post("/api/mail/state", {"id": "t1", "state": "done"})    # the master is a lead
        eq(r.status_code, 200, "a lead can close anyone's thread")
        t = mail._load_mail()["threads"]["t1"]
        eq(t["state"], "done")
        ok(t["done_at"], "done stamps its time")
        # An unowned thread cannot be moved by a member, but a lead can bin it.
        _seed_thread("t2", subject="Spam")
        eq(post_s(sess_a, "/api/mail/state", {"id": "t2", "state": "done"}).status_code,
           403, "members close their own, not the room's")
        eq(post("/api/mail/state", {"id": "t2", "state": "done"}).status_code,
           200, "a lead can close junk without claiming it")
        # Release: Ann hands her own back, nobody else's.
        _seed_thread("t3")
        post_s(sess_a, "/api/mail/claim", {"id": "t3"})
        eq(post_s(sess_b, "/api/mail/assign", {"id": "t3", "uid": ""}).status_code, 403)
        eq(post_s(sess_a, "/api/mail/assign", {"id": "t3", "uid": ""}).status_code, 200)
        eq(mail._load_mail()["threads"]["t3"]["state"], "unassigned")
        # Assigning to a switched-off account is refused.
        post("/api/team/user", {"op": "active", "id": uid_a, "active": False})
        eq(post("/api/mail/assign", {"id": "t3", "uid": uid_a}).status_code, 400)
    with_mail(go)

@test
def t_mail_notes_presence_and_team_panel():
    def go():
        ensure_auth()
        uid, sess, _ = ready_user("Ann", "ann")
        _seed_thread("t1")
        eq(post_s(sess, "/api/mail/note", {"id": "t1", "text": ""}).status_code, 400)
        r = post_s(sess, "/api/mail/note", {"id": "t1", "text": "chasing the courier"})
        eq(r.status_code, 200, r.text)
        eq(post_s(sess, "/api/mail/presence", {"presence": "beach"}).status_code, 400)
        eq(post_s(sess, "/api/mail/presence", {"presence": "home"}).status_code, 200)
        post_s(sess, "/api/mail/claim", {"id": "t1"})
        board = post_s(sess, "/api/mail/board", {}).json()
        me = [m for m in board["team"] if m["uid"] == uid][0]
        eq(me["presence"], "home")
        eq(me["assigned"], 1, "the panel counts what Ann holds")
        ok(not board["connected"], "no token file means not connected")
        row = [t for t in board["threads"] if t["id"] == "t1"][0]
        eq(row["notes"], 1)
        eq(row["owner_name"], "Ann")
    with_mail(go)

@test
def t_mail_viewing_collision_and_thread_view():
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        _seed_thread("t1")
        # Master opens the thread, then Ann does: Ann is told about the master.
        post("/api/mail/thread", {"id": "t1"})
        r = post_s(sess, "/api/mail/thread", {"id": "t1"})
        eq(r.status_code, 200, r.text)
        ok(len(r.json()["viewers"]) == 1, "the other viewer is named")
        v = post("/api/mail/viewing", {"id": "t1"}).json()
        ok(any("Ann" in x for x in v["viewers"]), "and symmetric the other way")
        eq(post_s(sess, "/api/mail/thread", {"id": "missing"}).status_code, 404)
    with_mail(go)

@test
def t_mail_tab_gate_and_auth():
    def go():
        ensure_auth()
        eq(bare("/api/mail/board", {}).status_code, 401, "no session, no board")
        uid, sess, _ = ready_user("Ann", "ann")
        post("/api/team/user", {"op": "tabs", "id": uid, "tabs": ["overview"]})
        eq(post_s(sess, "/api/mail/board", {}).status_code, 403,
           "the mail tab is enforced by the server, not the menu")
    with_mail(go)

@test
def t_mail_label_failure_never_blocks_the_claim():
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        _seed_thread("t1")
        # Pretend the mailbox is connected but Gmail is having a day.
        _gm.save_connection("rt-test", MBOX)
        async def boom(*a, **k):
            raise _gm.GmailError("backend error")
        saved = (_gm.ensure_label, _gm.modify_thread)
        _gm.ensure_label = boom
        _gm.modify_thread = boom
        try:
            r = post_s(sess, "/api/mail/claim", {"id": "t1"})
            eq(r.status_code, 200, "ownership is ours to grant, not Gmail's")
            t = mail._load_mail()["threads"]["t1"]
            eq(t["owner"] != "", True)
            ok(t["label_error"], "but the failed label is recorded")
        finally:
            _gm.ensure_label, _gm.modify_thread = saved
    with_mail(go)

@test
def t_mail_sync_pipeline_and_history_short_circuit():
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        calls = {"list": 0, "get": 0}
        listing = [{"id": "t1", "snippet": "s", "historyId": "h1"}]
        async def fake_list(q, n):
            calls["list"] += 1
            return {"threads": list(listing), "complete": True}
        async def fake_get(tid):
            calls["get"] += 1
            return {"id": tid, "historyId": listing[0]["historyId"], "subject": "Order query",
                    "messages": [_mk_msg("m1", "Jo", "jo@customer.com",
                                         "2026-08-19T01:00:00+00:00")]}
        saved = (_gm.list_threads, _gm.get_thread)
        _gm.list_threads, _gm.get_thread = fake_list, fake_get
        try:
            r = post("/api/mail/board", {"force": True})
            eq(r.status_code, 200, r.text)
            j = r.json()
            ok(j["connected"], "the token file makes it connected")
            eq(j["address"], MBOX)
            eq(len(j["threads"]), 1)
            eq(j["threads"][0]["subject"], "Order query")
            eq(calls["get"], 1)
            # Same historyId again: the listing is enough, no thread fetch.
            # (A board read no longer syncs inline, so the sync is run here.)
            mail._load_mail()["synced_at"] = ""     # force staleness
            run_async(mail._mail_sync_now())
            eq(calls["list"], 2, "the sync did run")
            eq(calls["get"], 1, "an unchanged thread costs nothing to re-sync")
            # A bumped historyId is fetched again.
            listing[0]["historyId"] = "h2"
            mail._load_mail()["synced_at"] = ""
            run_async(mail._mail_sync_now())
            eq(calls["get"], 2)
        finally:
            _gm.list_threads, _gm.get_thread = saved
    with_mail(go)

@test
def t_mail_sync_failure_keeps_the_last_good_board():
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        async def dead(q, n):
            raise _gm.GmailError("quota exceeded")
        saved = _gm.list_threads
        _gm.list_threads = dead
        try:
            r = post("/api/mail/board", {"force": True})
            eq(r.status_code, 200, "a failed sync is not a failed board")
            j = r.json()
            eq(len(j["threads"]), 1, "the last good picture survives")
            ok("quota" in j["sync_error"], "and the problem is named")
        finally:
            _gm.list_threads = saved
    with_mail(go)

@test
def t_mail_backup_includes_the_board_but_never_the_token():
    def go():
        ensure_auth()
        _seed_thread("t1")
        mail._write_mail(mail._load_mail())
        _gm.save_connection("rt-secret", MBOX)
        import io, zipfile
        buf, _n = backup._build_backup_zip()
        names = [os.path.basename(n) for n in zipfile.ZipFile(buf).namelist()]
        ok("mailbox.json" in names, "who owns which email survives a move")
        ok("gmail_oauth.json" not in names, "the mailbox credential never leaves")
    with_mail(go)

@test
def t_mail_crm_match_links_the_sender():
    def go():
        ensure_auth()
        post("/api/crm/contact", {"op": "person_add", "name": "Jo Bloggs",
                                  "emails": ["jo@customer.com"]})
        _seed_thread("t1")
        r = post("/api/mail/thread", {"id": "t1"})
        eq(r.status_code, 200, r.text)
        crm = r.json()["crm"]
        ok(crm and crm["name"] == "Jo Bloggs", "the sender is recognised from the CRM")
    with_mail(go)

@test
def t_mail_claim_is_durable_before_the_label_trip():
    """The review's finding: ownership must be on DISK before the Gmail
    label round trip, so a restart mid-label never loses a claim."""
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        _seed_thread("t1")
        _gm.save_connection("rt-test", MBOX)
        seen = {}
        async def probe(name, known):
            with open(mail.MAILBOX_PATH, encoding="utf-8") as fh:
                d = json.load(fh)["mailbox"]
            seen["owner_on_disk"] = bool(d["threads"]["t1"].get("owner"))
            raise _gm.GmailError("gmail is down")
        saved = _gm.ensure_label
        _gm.ensure_label = probe
        try:
            r = post_s(sess, "/api/mail/claim", {"id": "t1"})
            eq(r.status_code, 200, r.text)
            ok(seen.get("owner_on_disk"), "the claim was durable before Gmail was asked")
            t = mail._load_mail()["threads"]["t1"]
            ok(t["label_error"], "and the label failure is recorded, not fatal")
        finally:
            _gm.ensure_label = saved
    with_mail(go)

@test
def t_mail_release_on_deactivate_tab_removal_and_delete():
    def go():
        ensure_auth()
        uid_a, sess_a, _ = ready_user("Ann", "ann")
        uid_b, sess_b, _ = ready_user("Bob", "bob")
        _seed_thread("t1"); _seed_thread("t2", subject="Second")
        post_s(sess_a, "/api/mail/claim", {"id": "t1"})
        post_s(sess_b, "/api/mail/claim", {"id": "t2"})
        # Switching Ann off releases her thread to the room.
        post("/api/team/user", {"op": "active", "id": uid_a, "active": False})
        t1 = mail._load_mail()["threads"]["t1"]
        eq(t1["state"], "unassigned", "a switched-off account keeps no email")
        eq(t1["owner"], "")
        ok(any("released" in a["action"] for a in t1["activity"]))
        # Taking Bob's mail tab away does the same...
        post("/api/team/user", {"op": "tabs", "id": uid_b, "tabs": ["overview"]})
        t2 = mail._load_mail()["threads"]["t2"]
        eq(t2["state"], "unassigned", "no mail tab, no owned email")
        # ...and a lead cannot assign to him while it is gone.
        eq(post("/api/mail/assign", {"id": "t2", "uid": uid_b}).status_code, 400,
           "assignment respects the mail tab, not just active")
        post("/api/team/user", {"op": "tabs", "id": uid_b, "tabs": None})
        eq(post("/api/mail/assign", {"id": "t2", "uid": uid_b}).status_code, 200)
    with_mail(go)

@test
def t_mail_double_click_state_is_one_move():
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        _seed_thread("t1")
        post_s(sess, "/api/mail/claim", {"id": "t1"})
        eq(post_s(sess, "/api/mail/state", {"id": "t1", "state": "progress"}).status_code, 200)
        eq(post_s(sess, "/api/mail/state", {"id": "t1", "state": "progress"}).status_code, 200)
        t = mail._load_mail()["threads"]["t1"]
        eq(len([a for a in t["activity"] if a["action"] == "started work"]), 1,
           "a double-click is not two moves")
    with_mail(go)

@test
def t_mail_viewing_validates_the_thread_and_sweeps():
    def go():
        ensure_auth()
        eq(post("/api/mail/viewing", {"id": "garbage-id"}).status_code, 404,
           "the viewers register only tracks real threads")
        ok("garbage-id" not in mail._mail_viewers)
    with_mail(go)

@test
def t_mail_crm_chip_respects_the_crm_tab():
    def go():
        ensure_auth()
        post("/api/crm/contact", {"op": "person_add", "name": "Jo Bloggs",
                                  "emails": ["jo@customer.com"]})
        uid, sess, _ = ready_user("Ann", "ann")
        post("/api/team/user", {"op": "tabs", "id": uid, "tabs": ["mail"]})
        _seed_thread("t1")
        r = post_s(sess, "/api/mail/thread", {"id": "t1"})
        eq(r.status_code, 200, r.text)
        ok(r.json()["crm"] is None, "no CRM tab means no CRM knowledge, even sideways")
        r2 = post("/api/mail/thread", {"id": "t1"})
        ok(r2.json()["crm"], "the master still sees the match")
    with_mail(go)

@test
def t_mail_label_cache_evicts_on_failure():
    """A label deleted inside Gmail leaves a dead id in the cache; a failed
    sync must evict it so the next attempt can re-list and heal."""
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        _seed_thread("t1")
        _gm.save_connection("rt-test", MBOX)
        store = mail._load_mail()
        store["labels"]["Copilot/Ann"] = "DEAD_ID"
        async def boom(tid, add=None, remove=None):
            raise _gm.GmailError("Invalid label")
        async def use_cache(name, known):
            return known[name]      # the cache hit path: no create
        saved = (_gm.modify_thread, _gm.ensure_label)
        _gm.modify_thread, _gm.ensure_label = boom, use_cache
        try:
            eq(post_s(sess, "/api/mail/claim", {"id": "t1"}).status_code, 200)
            ok("Copilot/Ann" not in mail._load_mail()["labels"],
               "the dead id is evicted, so the next change re-lists")
        finally:
            _gm.modify_thread, _gm.ensure_label = saved
    with_mail(go)

@test
def t_mail_sync_abandons_when_the_store_is_replaced_under_it():
    """The restore race: a sync in flight across a restore must never write
    its pre-restore snapshot over the restored board."""
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        async def swapping_list(q, n):
            mail._mail_mem = None    # what a restore does mid-await
            return {"threads": [{"id": "tX", "snippet": "s", "historyId": "h1"}],
                    "complete": True}
        async def fake_get(tid):
            return {"id": tid, "historyId": "h1", "subject": "S",
                    "messages": [_mk_msg("m1", "Jo", "jo@customer.com",
                                         "2026-08-19T01:00:00+00:00")]}
        saved = (_gm.list_threads, _gm.get_thread)
        _gm.list_threads, _gm.get_thread = swapping_list, fake_get
        try:
            r = post("/api/mail/board", {"force": True})
            eq(r.status_code, 200, r.text)
            ok("tX" not in mail._load_mail()["threads"],
               "the orphaned sync walked away instead of writing")
        finally:
            _gm.list_threads, _gm.get_thread = saved
    with_mail(go)

@test
def t_mail_connect_ticket_is_master_only_and_single_use():
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        saved = (_gm.OAUTH_CLIENT_ID, _gm.OAUTH_CLIENT_SECRET)
        _gm.OAUTH_CLIENT_ID = _gm.OAUTH_CLIENT_SECRET = "demo"
        try:
            eq(post_s(sess, "/api/mail/connect-link", {}).status_code, 403,
               "only the master connects the mailbox")
            r = post("/api/mail/connect-link", {})
            eq(r.status_code, 200, r.text)
            url = r.json()["url"]
            ok(url.startswith("/oauth/gmail/start?t="), url)
            ticket = url.split("t=", 1)[1]
            # The ticket opens the consent walk exactly once.
            first = client.get("/oauth/gmail/start", params={"t": ticket},
                               follow_redirects=False)
            eq(first.status_code, 302, "the ticket starts the consent walk")
            ok("select_account" in first.headers["location"],
               "Google is forced to ask WHICH account, so the wrong one cannot slip through")
            again = client.get("/oauth/gmail/start", params={"t": ticket},
                               follow_redirects=False)
            eq(again.status_code, 403, "a spent ticket is dead")
            eq(client.get("/oauth/gmail/start", params={"t": "made-up"},
                          follow_redirects=False).status_code, 403)
            eq(client.get("/oauth/gmail/start", follow_redirects=False).status_code, 403,
               "and no ticket at all is still forbidden")
        finally:
            _gm.OAUTH_CLIENT_ID, _gm.OAUTH_CLIENT_SECRET = saved
            mail._mail_connect_tickets.clear()
    with_mail(go)

@test
def t_mail_bulk_clears_a_backlog_and_reports_what_it_could_not_do():
    """A sixty-day first import lands as a wall of unowned email. Triaging it
    one row at a time is not a real option, so many-at-once has to work."""
    def go():
        ensure_auth()
        uid_a, sess_a, _ = ready_user("Ann", "ann")
        _uid_b, sess_b, _ = ready_user("Bob", "bob")
        for i in range(5):
            _seed_thread("b%d" % i, subject="Old enquiry %d" % i)
        # Ann claims the lot in one gesture.
        r = post_s(sess_a, "/api/mail/bulk", {"op": "claim", "ids": ["b0", "b1", "b2"]})
        eq(r.status_code, 200, r.text)
        eq(r.json()["changed"], 3)
        threads = mail._load_mail()["threads"]
        eq(threads["b0"]["owner"], uid_a)
        eq(threads["b0"]["state"], "assigned")
        # Bob claiming the same ones is told why, per thread, not just refused.
        r2 = post_s(sess_b, "/api/mail/bulk", {"op": "claim", "ids": ["b0", "b3"]})
        eq(r2.json()["changed"], 1, "the free one still gets claimed")
        ok(any("Ann" in s["why"] for s in r2.json()["skipped"]), r2.text)
        # Bob cannot move Ann's threads, and is told so per thread.
        r3 = post_s(sess_b, "/api/mail/bulk", {"op": "state", "state": "done",
                                               "ids": ["b0", "b3"]})
        eq(r3.json()["changed"], 1, "his own, yes; hers, no")
        ok(any("not yours" in s["why"] for s in r3.json()["skipped"]), r3.text)
        # A lead closes the whole backlog: this is the clean-slate gesture.
        r4 = post("/api/mail/bulk", {"op": "state", "state": "done",
                                     "ids": ["b0", "b1", "b2", "b4", "gone"]})
        eq(r4.json()["changed"], 4)
        ok(any(s["id"] == "gone" for s in r4.json()["skipped"]), "a vanished id is named")
        eq(mail._load_mail()["threads"]["b1"]["state"], "done")
        # Staff cannot mass-assign to other people.
        eq(post_s(sess_a, "/api/mail/bulk", {"op": "assign", "uid": uid_a,
                                             "ids": ["b0"]}).status_code, 403)
        eq(post("/api/mail/bulk", {"op": "claim", "ids": []}).status_code, 400)
        eq(post("/api/mail/bulk", {"op": "nonsense", "ids": ["b0"]}).status_code, 400)
        eq(post("/api/mail/bulk", {"op": "claim", "ids": ["x"] * 201}).status_code, 400)
    with_mail(go)

@test
def t_mail_gmail_body_parsing_handles_the_shapes_gmail_actually_sends():
    """A simple email keeps its whole body on the ROOT part with no `parts`
    at all, so a walker that only looks at `parts` reads nothing for exactly
    the plainest mail. Attachments must never be pulled into the request."""
    import base64 as _b64
    enc = lambda s: _b64.urlsafe_b64encode(s.encode()).decode().rstrip("=")
    # (a) flat text/plain, no parts
    out = {}
    _gm._walk_body({"mimeType": "text/plain",
                    "body": {"data": enc("just a plain note")}}, out)
    eq(out.get("plain"), "just a plain note", "the flat shape is read")
    # (b) nested mixed > related > alternative, with an attachment alongside
    out = {}
    _gm._walk_body({"mimeType": "multipart/mixed", "parts": [
        {"mimeType": "multipart/related", "parts": [
            {"mimeType": "multipart/alternative", "parts": [
                {"mimeType": "text/plain", "body": {"data": enc("the real words")}},
                {"mimeType": "text/html", "body": {"data": enc("<p>the real words</p>")}}]}]},
        {"mimeType": "application/pdf", "filename": "invoice.pdf",
         "body": {"attachmentId": "att1", "size": 20000000}}]}, out)
    eq(out.get("plain"), "the real words", "three levels deep is still found")
    # (c) html only: tags stripped rather than fed to the model raw
    out = {}
    _gm._walk_body({"mimeType": "text/html",
                    "body": {"data": enc("<p>Hello<br>there</p><script>x()</script>")}}, out)
    txt = _gm._strip_html(out.get("html") or "")
    ok("Hello" in txt and "there" in txt and "script" not in txt and "<" not in txt, txt)
    # (d) unpadded base64url with the URL-safe alphabet
    raw = _b64.urlsafe_b64encode("café — test?>".encode()).decode().rstrip("=")
    ok("café" in _gm._b64url(raw), "unpadded base64url decodes")

@test
def t_mail_draft_is_saved_never_sent_and_threaded_to_the_customer():
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1", subject="Where is my order?")
        captured = {}
        async def fake_read(tid, per_msg_chars=4000):
            return {"id": tid, "messages": [
                {"id": "m1", "from_name": "Jo", "from_email": "jo@customer.com",
                 "reply_to": "", "subject": "Where is my order?",
                 "message_id": "<abc@mail>", "references": "", "at": "2026-08-19T01:00:00+00:00",
                 "text": "Any news on my gobos?"},
                {"id": "m2", "from_name": "Sales", "from_email": MBOX,
                 "reply_to": "", "subject": "Re: Where is my order?",
                 "message_id": "<def@mail>", "references": "<abc@mail>",
                 "at": "2026-08-19T02:00:00+00:00", "text": "Checking now."}]}
        async def fake_draft(thread_id, to_addr, subject, body_text,
                             in_reply_to="", references="", cc="", replaces="",
                             raw_bytes=None):
            captured.update({"thread_id": thread_id, "to": to_addr, "subject": subject,
                             "body": body_text, "irt": in_reply_to, "replaces": replaces})
            return {"id": "d%d" % (len(captured.get("ids", [])) + 1), "thread_id": thread_id}
        saved = (_gm.read_thread, _gm.create_draft, _gm.draft_body)
        _gm.read_thread, _gm.create_draft = fake_read, fake_draft
        try:
            r = post_s(sess, "/api/mail/draft", {"id": "t1", "op": "save",
                                                 "text": "Hello Jo, they ship Friday."})
            eq(r.status_code, 200, r.text)
            eq(captured["to"], "jo@customer.com",
               "the reply goes to the CUSTOMER, not back to our own mailbox")
            eq(captured["irt"], "<abc@mail>", "and threads onto their message")
            eq(captured["thread_id"], "t1")
            t = mail._load_mail()["threads"]["t1"]
            ok(t.get("draft_at"), "the thread records that a draft exists")
            ok(any("draft" in a["action"] for a in t["activity"]))
            eq(post_s(sess, "/api/mail/draft", {"id": "t1", "op": "save", "text": ""}).status_code,
               400, "an empty draft is not saved")
            # Saving again REPLACES: one draft per conversation, not a pile.
            async def unchanged(draft_id):
                # What we actually put in Gmail, quoted original and all:
                # still exactly ours, so the save may replace it.
                return mail._load_mail()["threads"]["t1"]["draft_text"]
            _gm.draft_body = unchanged
            r2 = post_s(sess, "/api/mail/draft", {"id": "t1", "op": "save", "text": "Second go."})
            eq(captured["replaces"], "d1", "the previous draft is cleared up")
            ok(not r2.json().get("kept_previous"))
            # But a draft the person rewrote IN GMAIL is never deleted.
            async def edited(draft_id):
                return "I rewrote this myself in Gmail."
            _gm.draft_body = edited
            r3 = post_s(sess, "/api/mail/draft", {"id": "t1", "op": "save", "text": "Third go."})
            eq(captured["replaces"], "", "their edited version is left alone")
            ok(r3.json()["kept_previous"], "and the app says so rather than pretending")
        finally:
            _gm.read_thread, _gm.create_draft, _gm.draft_body = saved
    with_mail(go)

@test
def t_mail_draft_refuses_to_write_into_someone_elses_conversation():
    def go():
        ensure_auth()
        _uid_a, sess_a, _ = ready_user("Ann", "ann")
        _uid_b, sess_b, _ = ready_user("Bob", "bob")
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        post_s(sess_a, "/api/mail/claim", {"id": "t1"})
        r = post_s(sess_b, "/api/mail/draft", {"id": "t1", "op": "compose"})
        eq(r.status_code, 403, "a reply is at least as big a move as a state change")
        ok("Ann" in r.json()["error"], r.text)
        # A lead may still step in, and so may the owner.
        async def fake_read(tid, per_msg_chars=4000):
            return {"id": tid, "messages": [
                {"id": "m1", "from_name": "Jo", "from_email": "jo@customer.com",
                 "subject": "S", "message_id": "<a@b>", "references": "", "reply_to": "",
                 "at": "2026-08-19T01:00:00+00:00", "text": "hello"}]}
        captured = {}
        async def fake_draft(thread_id, to_addr, subject, body_text, in_reply_to="",
                             references="", cc="", replaces="", raw_bytes=None):
            captured["to"] = to_addr
            return {"id": "d1", "thread_id": thread_id}
        saved = (_gm.read_thread, _gm.create_draft)
        _gm.read_thread, _gm.create_draft = fake_read, fake_draft
        try:
            eq(post("/api/mail/draft", {"id": "t1", "op": "save", "text": "x"}).status_code, 200,
               "a lead can")
        finally:
            _gm.read_thread, _gm.create_draft = saved
    with_mail(go)

@test
def t_mail_draft_refuses_a_reply_that_would_go_nowhere():
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        async def only_us(tid, per_msg_chars=4000):
            return {"id": tid, "messages": [
                {"id": "m1", "from_name": "Sales", "from_email": MBOX, "subject": "S",
                 "message_id": "<a@b>", "references": "", "reply_to": "",
                 "at": "2026-08-19T01:00:00+00:00", "text": "note to self"}]}
        saved = _gm.read_thread
        _gm.read_thread = only_us
        try:
            r = post("/api/mail/draft", {"id": "t1", "op": "save", "text": "hello"})
            eq(r.status_code, 400, "a reply addressed to our own mailbox is refused")
            ok("circle" in r.json()["error"], r.text)
        finally:
            _gm.read_thread = saved
    with_mail(go)

