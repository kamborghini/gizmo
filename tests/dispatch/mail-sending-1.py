# ---- Sending, not just drafting -------------------------------------------
# A draft is inert and a state change is undoable; a sent email is gone the
# second Gmail says yes. These drive the send route with a faked connector:
# who is allowed to send at all, the durable stamp that has to be on disk
# BEFORE the network call, and every way a send is refused before it happens.

def _one_from_customer(subject="Where is my order?"):
    """A conversation with one customer message on it, as read_thread hands
    it over: the shape the reply headers are derived from."""
    async def fake_read(tid, per_msg_chars=4000):
        return {"id": tid, "messages": [
            {"id": "m1", "from_name": "Jo", "from_email": "jo@customer.com",
             "reply_to": "", "subject": subject, "message_id": "<abc@mail>",
             "references": "", "at": "2026-08-19T01:00:00+00:00",
             "text": "Any news on my gobos?"}]}
    return fake_read

@test
def t_gmail_send_threads_a_reply_and_leaves_a_new_message_alone():
    """One message builder behind the draft and the send. If they drift, the
    path nobody proofreads is the one that goes out with the wrong headers."""
    def go():
        _gm.save_connection("rt-test", MBOX)
        import base64
        seen = {}
        async def fake_call(method, path, params=None, body=None, **kw):
            seen.update({"method": method, "path": path, "body": body})
            return {"id": "sent1", "threadId": (body or {}).get("threadId") or "T-NEW"}
        saved = _gm._call
        _gm._call = fake_call
        try:
            out = run_async(_gm.send_message("t1", "jo@customer.com", "Gobo order",
                                             "They ship Friday.",
                                             in_reply_to="<abc@mail>", references="<old@mail>"))
            eq(seen["path"], "messages/send", "the SEND endpoint, not drafts")
            eq(seen["body"]["threadId"], "t1", "posted onto the conversation it answers")
            raw = base64.urlsafe_b64decode(seen["body"]["raw"]).decode()
            ok("Subject: Re: Gobo order" in raw, raw[:400])
            ok("In-Reply-To: <abc@mail>" in raw, raw[:400])
            ok("<old@mail> <abc@mail>" in raw, "the parent joins the References chain")
            eq(out["id"], "sent1")
            # A NEW conversation is pinned to nothing and prefixed with nothing.
            out2 = run_async(_gm.send_message("", "jo@customer.com", "Your quote",
                                              "Here it is.", new=True))
            ok("threadId" not in seen["body"], "a new conversation is not attached to a thread")
            raw2 = base64.urlsafe_b64decode(seen["body"]["raw"]).decode()
            ok("Subject: Your quote" in raw2, raw2[:300])
            ok("Re:" not in raw2.split("\n\n")[0], "nothing is being replied to")
            eq(out2["thread_id"], "T-NEW")
        finally:
            _gm._call = saved
    with_mail(go)

@test
def t_gmail_admits_the_reply_went_even_when_it_lands_on_the_wrong_thread():
    """The draft version of this can honestly say nothing was sent. This one
    cannot: the customer already has the email. It used to raise, which read
    to the route like a refusal (stamp cleared, nothing recorded as sent, the
    thread still unanswered on the board); it is a SEND with a note on it,
    and the route records it and tells the person where it went."""
    def go():
        _gm.save_connection("rt-test", MBOX)
        async def fake_call(method, path, params=None, body=None, **kw):
            return {"id": "sent1", "threadId": "SOMEWHERE-ELSE"}
        saved = _gm._call
        _gm._call = fake_call
        try:
            out = run_async(_gm.send_message("t1", "jo@customer.com", "S", "hello"))
            eq(out["id"], "sent1", "the send is reported as the send it was")
            eq(out["thread_id"], "SOMEWHERE-ELSE", "with where Gmail actually put it")
            ok(out.get("misfiled"), "and the note that it missed its conversation")
        finally:
            _gm._call = saved
    with_mail(go)

@test
def t_sending_email_from_gizmo_needs_the_grant():
    """Seeing the Inbox is not the same as being able to write to a customer
    over the shop's own address."""
    def go():
        ensure_auth()
        uid, sess, _ = ready_user("Ann", "ann")
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        _seed_thread("t2")
        calls = []
        async def fake_send(thread_id, to_addr, subject, body_text, **kw):
            calls.append(to_addr)
            return {"id": "sent-1", "thread_id": thread_id}
        saved = (_gm.read_thread, _gm.send_message)
        _gm.read_thread, _gm.send_message = _one_from_customer(), fake_send
        try:
            r = post_s(sess, "/api/mail/send", {"id": "t1", "text": "Hello Jo."})
            eq(r.status_code, 403, r.text)
            ok("not set up to send" in r.json()["error"], r.text)
            eq(calls, [], "a refused send never reaches Gmail")
            eq(post("/api/team/user", {"op": "send", "id": uid, "can_send": True}
                    ).status_code, 200)
            eq(post_s(sess, "/api/mail/send", {"id": "t1", "text": "Hello Jo."}).status_code,
               200, "granted, she can")
            # The master holds it by rank, like the size list.
            eq(post("/api/mail/send", {"id": "t2", "text": "Hello Jo."}).status_code, 200)
            eq(len(calls), 2)
        finally:
            _gm.read_thread, _gm.send_message = saved
    with_mail(go)

@test
def t_a_sent_reply_goes_to_the_customer_and_lands_waiting():
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1", subject="Where is my order?")
        captured, gone = {}, []
        async def fake_send(thread_id, to_addr, subject, body_text, **kw):
            captured.update({"thread_id": thread_id, "to": to_addr, "subject": subject,
                             "text": body_text, "irt": kw.get("in_reply_to"),
                             "new": kw.get("new")})
            return {"id": "sent-1", "thread_id": thread_id}
        async def still_ours(draft_id):
            return "Hello Jo, they ship Friday."
        async def fake_delete(draft_id):
            gone.append(draft_id)
        saved = (_gm.read_thread, _gm.send_message, _gm.draft_body, _gm.delete_draft)
        _gm.read_thread, _gm.send_message = _one_from_customer(), fake_send
        _gm.draft_body, _gm.delete_draft = still_ours, fake_delete
        try:
            t = mail._load_mail()["threads"]["t1"]
            t.update({"draft_id": "d1", "draft_at": mail._mail_now(),
                      "draft_to": "jo@customer.com",
                      "draft_text": "Hello Jo, they ship Friday."})
            r = post("/api/mail/send", {"id": "t1", "text": "Hello Jo, they ship Friday."})
            eq(r.status_code, 200, r.text)
            j = r.json()
            eq(j["to"], "jo@customer.com", "the reply goes to the CUSTOMER, not our mailbox")
            eq(j["state"], "waiting")
            eq(j["kind"], "reply")
            eq(j["message_id"], "sent-1")
            eq(captured["irt"], "<abc@mail>", "and threads onto their message")
            eq(captured["thread_id"], "t1")
            ok(not captured["new"], "a reply is not a new conversation")
            t = mail._load_mail()["threads"]["t1"]
            eq(t["state"], "waiting", "the shop is now waiting on them")
            eq(t["sent_to"], "jo@customer.com")
            eq(t["sent_msg_id"], "sent-1")
            eq(t["sent_by"], APP_AUTH["master"])
            ok(t["sent_at"], "with a time on it")
            eq(t.get("send_pending"), None, "the stamp comes off once it has gone")
            eq(t.get("draft_id"), None, "and the draft it replaced is forgotten")
            eq(t.get("draft_text"), None)
            eq(gone, ["d1"], "the leftover Gmail draft is cleaned up")
            eq(t["unread"], False)
            ok(any(a["action"] == "sent a reply from Reactor" for a in t["activity"]),
               str(t["activity"]))
        finally:
            _gm.read_thread, _gm.send_message, _gm.draft_body, _gm.delete_draft = saved
    with_mail(go)

@test
def t_a_draft_rewritten_in_gmail_survives_the_send():
    """Same rule the draft route already follows: only a draft we can prove is
    still ours is deleted. Somebody's edited words are not ours to bin."""
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        gone = []
        async def fake_send(thread_id, to_addr, subject, body_text, **kw):
            return {"id": "sent-1", "thread_id": thread_id}
        async def edited(draft_id):
            return "I rewrote this myself in Gmail."
        async def fake_delete(draft_id):
            gone.append(draft_id)
        saved = (_gm.read_thread, _gm.send_message, _gm.draft_body, _gm.delete_draft)
        _gm.read_thread, _gm.send_message = _one_from_customer(), fake_send
        _gm.draft_body, _gm.delete_draft = edited, fake_delete
        try:
            t = mail._load_mail()["threads"]["t1"]
            t.update({"draft_id": "d1", "draft_text": "Hello Jo, they ship Friday."})
            eq(post("/api/mail/send", {"id": "t1", "text": "Different words."}
                    ).status_code, 200)
            eq(gone, [], "their version is left where they can find it")
        finally:
            _gm.read_thread, _gm.send_message, _gm.draft_body, _gm.delete_draft = saved
    with_mail(go)

@test
def t_a_send_is_stamped_to_disk_before_gmail_is_asked():
    """The crash-mid-send case. If the process dies inside the call, the board
    has to be able to say a reply may already have gone out - so the stamp is
    read back FROM DISK, by the fake sender, at the moment Gmail is asked."""
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        seen = {}
        async def fake_send(thread_id, to_addr, subject, body_text, **kw):
            disk = json.load(open(mail.MAILBOX_PATH))["mailbox"]
            seen["pending"] = disk["threads"]["t1"].get("send_pending") or {}
            return {"id": "sent-1", "thread_id": thread_id}
        saved = (_gm.read_thread, _gm.send_message)
        _gm.read_thread, _gm.send_message = _one_from_customer(), fake_send
        try:
            eq(post("/api/mail/send", {"id": "t1", "text": "Hello Jo."}).status_code, 200)
            eq(seen["pending"].get("to"), "jo@customer.com",
               "the intention was durable before the message left")
            eq(seen["pending"].get("by"), APP_AUTH["master"], "with a name against it")
            ok(seen["pending"].get("at"), "and a time")
        finally:
            _gm.read_thread, _gm.send_message = saved
    with_mail(go)

@test
def t_a_failed_send_marks_nothing_sent_and_leaves_no_stamp():
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        async def boom(thread_id, to_addr, subject, body_text, **kw):
            raise _gm.GmailError("Gmail refused this message.")
        saved = (_gm.read_thread, _gm.send_message)
        _gm.read_thread, _gm.send_message = _one_from_customer(), boom
        try:
            r = post("/api/mail/send", {"id": "t1", "text": "Hello Jo."})
            eq(r.status_code, 502, r.text)
            ok("Gmail refused this message." in r.json()["error"], r.text)
            t = mail._load_mail()["threads"]["t1"]
            eq(t.get("sent_at"), None, "nothing is marked sent")
            eq(t.get("send_pending"), None, "and no stamp is left to haunt the board")
            eq(t["state"], "unassigned", "the conversation did not move either")
            disk = json.load(open(mail.MAILBOX_PATH))["mailbox"]
            eq(disk["threads"]["t1"].get("send_pending"), None, "cleared on DISK, not just here")
            ok(any("did not complete" in a["action"] for a in t["activity"]),
               "and the thread says a send was attempted: " + str(t["activity"]))
        finally:
            _gm.read_thread, _gm.send_message = saved
    with_mail(go)

@test
def t_a_send_never_goes_in_a_circle():
    """Both kinds: a conversation whose only address is ours, and a compose
    typed straight at the mailbox. Either would look sent and reach nobody."""
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        calls = []
        async def only_us(tid, per_msg_chars=4000):
            return {"id": tid, "messages": [
                {"id": "m1", "from_name": "Sales", "from_email": MBOX, "subject": "S",
                 "message_id": "<a@b>", "references": "", "reply_to": "",
                 "at": "2026-08-19T01:00:00+00:00", "text": "note to self"}]}
        async def fake_send(*a, **k):
            calls.append(a)
            return {"id": "x", "thread_id": "t1"}
        saved = (_gm.read_thread, _gm.send_message)
        _gm.read_thread, _gm.send_message = only_us, fake_send
        try:
            r = post("/api/mail/send", {"id": "t1", "text": "hello"})
            eq(r.status_code, 400, r.text)
            ok("circle" in r.json()["error"], r.text)
            r2 = post("/api/mail/send", {"to": MBOX.upper(), "subject": "Hi", "text": "hello"})
            eq(r2.status_code, 400, r2.text)
            r3 = post("/api/mail/send", {"to": "jo@customer.com, " + MBOX,
                                        "subject": "Hi", "text": "hello"})
            eq(r3.status_code, 400, "one of ours among five of theirs still counts")
            eq(calls, [], "and Gmail was never asked, any of the three times")
            eq(mail._load_mail().get("outbound_pending") or [], [], "nothing was stamped")
        finally:
            _gm.read_thread, _gm.send_message = saved
    with_mail(go)

@test
def t_a_new_message_refuses_anything_that_is_not_an_address():
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        calls = []
        async def fake_send(*a, **k):
            calls.append(a)
            return {"id": "x", "thread_id": "T1"}
        saved = _gm.send_message
        _gm.send_message = fake_send
        try:
            for bad, why in [("", "neither a conversation nor an address"),
                             ("not-an-address", "a word is not an address"),
                             ("jo@customer", "a bare hostname is not a domain"),
                             ("jo@customer.com\nBcc: sneak@evil.example",
                              "a line break would forge a header of their choosing"),
                             ("jo@customer.com, ", "a trailing comma is not a recipient"),
                             (", ".join("a%d@x.com" % i for i in range(6)),
                              "six is more than a compose will address")]:
                r = post("/api/mail/send", {"to": bad, "subject": "Hi", "text": "hello"})
                eq(r.status_code, 400, why + ": " + r.text)
            # Both of id and to is as unanswerable as neither.
            _seed_thread("t1")
            eq(post("/api/mail/send", {"id": "t1", "to": "jo@x.com", "subject": "Hi",
                                       "text": "hello"}).status_code, 400)
            eq(calls, [], "not one of them reached Gmail")
        finally:
            _gm.send_message = saved
    with_mail(go)

@test
def t_a_new_conversation_starts_owned_waiting_and_addressed_to_them():
    def go():
        ensure_auth()
        uid, sess, _ = ready_user("Ann", "ann")
        eq(post("/api/team/user", {"op": "send", "id": uid, "can_send": True}).status_code, 200)
        _gm.save_connection("rt-test", MBOX)
        captured = {}
        async def fake_send(thread_id, to_addr, subject, body_text, **kw):
            captured.update({"thread_id": thread_id, "to": to_addr, "subject": subject,
                             "new": kw.get("new")})
            return {"id": "sent-9", "thread_id": "T9"}
        async def fake_get(tid, acct=None):
            return {"id": "T9", "historyId": "h9", "subject": "Your quote",
                    "messages": [{"id": "sent-9", "from_name": "Sales", "from_email": MBOX,
                                  "at": "2026-09-02T10:00:00+00:00", "labels": [],
                                  "files": [], "snippet": "Here is the quote"}]}
        saved = (_gm.send_message, _gm.get_thread)
        _gm.send_message, _gm.get_thread = fake_send, fake_get
        try:
            r = post_s(sess, "/api/mail/send",
                       {"to": "Jo <jo@customer.com>, pat@customer.com",
                        "subject": "Your quote", "text": "Here is the quote."})
            eq(r.status_code, 200, r.text)
            j = r.json()
            eq(j["to"], "jo@customer.com, pat@customer.com", "display names are dropped")
            eq(j["kind"], "new")
            eq(j["thread_id"], "T9")
            eq(j["state"], "waiting")
            ok(captured["new"], "Gmail is told this starts a conversation")
            eq(captured["thread_id"], "", "with nothing to attach it to")
            eq(captured["subject"], "Your quote")
            t = mail._load_mail()["threads"]["T9"]
            eq(t["owner"], uid, "whoever wrote it is holding it")
            eq(t["state"], "waiting")
            eq(t["started_to"], "jo@customer.com, pat@customer.com")
            eq(t["sent_by"], uid)
            ok(any("started this conversation" in a["action"] for a in t["activity"]),
               str(t["activity"]))
            row = [x for x in mail._mail_board_shape(mail._load_mail())
                   if x["id"] == "T9"][0]
            eq(row["from_email"], "jo@customer.com",
               "the row shows who it WENT TO, never our own mailbox")
            eq(row["sent_to"], "jo@customer.com, pat@customer.com")
            eq(row["owner_name"], "Ann")
            # The stamp came off; a leftover one from a crash is REPORTED.
            store = mail._load_mail()
            eq(store.get("outbound_pending") or [], [])
            store.setdefault("outbound_pending", []).append(
                {"at": "2026-09-01T09:00:00+00:00", "by": uid, "to": "lost@customer.com",
                 "subject": "Half sent", "text": "..."})
            store["synced_at"] = mail._mail_now()   # no Gmail trip for this read
            mail._write_mail(store)
            board = post_s(sess, "/api/mail/board", {}).json()
            eq(len(board["outbound_pending"]), 1, str(board.get("outbound_pending")))
            eq(board["outbound_pending"][0]["to"], "lost@customer.com")
            eq(board["outbound_pending"][0]["by_name"], "Ann")
            eq(board["outbound_pending"][0]["subject"], "Half sent")
        finally:
            _gm.send_message, _gm.get_thread = saved
    with_mail(go)

@test
def t_a_dry_send_says_where_it_would_go_and_sends_nothing():
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        calls = []
        async def fake_send(*a, **k):
            calls.append(a)
            return {"id": "x", "thread_id": "T1"}
        saved = (_gm.read_thread, _gm.send_message)
        _gm.read_thread, _gm.send_message = _one_from_customer(), fake_send
        try:
            r = post("/api/mail/send", {"id": "t1", "text": "hello", "dry": True})
            eq(r.status_code, 200, r.text)
            eq(r.json()["dry"], True)
            eq(r.json()["to"], "jo@customer.com", "resolved for real, sent for nobody")
            eq(r.json()["kind"], "reply")
            r2 = post("/api/mail/send", {"to": "Jo <jo@customer.com>", "subject": "Hi",
                                         "text": "hello", "dry": True})
            eq(r2.status_code, 200, r2.text)
            eq(r2.json()["to"], "jo@customer.com")
            eq(r2.json()["kind"], "new")
            # Every refusal a real send makes, a dry run makes too.
            for body, why in [({"to": "nonsense", "subject": "Hi", "text": "x"},
                               "a bad address"),
                              ({"to": "jo@x.com", "subject": "", "text": "x"},
                               "a new message with no subject"),
                              ({"to": "jo@x.com", "subject": "Hi", "text": "   "},
                               "an empty message"),
                              ({"to": "jo@x.com", "subject": "Hi", "text": "x" * 20001},
                               "one longer than the store will hold")]:
                body["dry"] = True
                eq(post("/api/mail/send", body).status_code, 400, why + " is still refused")
            eq(calls, [], "a dry run never sends")
            t = mail._load_mail()["threads"]["t1"]
            eq(t.get("send_pending"), None, "and never stamps")
            eq(t["state"], "unassigned", "and never moves the board")
            eq(mail._load_mail().get("outbound_pending") or [], [])
        finally:
            _gm.read_thread, _gm.send_message = saved
    with_mail(go)

@test
def t_the_send_grant_is_handed_over_the_way_the_size_grant_is():
    def go():
        ensure_auth()
        uid, sess, _ = ready_user("Ann", "ann")
        uid_b, sess_b, _ = ready_user("Bob", "bob")
        adm, _s, _ = ready_user("Al", "al", role="admin")
        eq(team._may_send_mail(uid), False, "nobody holds it by having an account")
        # A member cannot hand it to anyone, themselves included.
        eq(post_s(sess_b, "/api/team/user", {"op": "send", "id": uid, "can_send": True}
                  ).status_code, 403)
        eq(post_s(sess_b, "/api/team/user", {"op": "send", "id": uid_b, "can_send": True}
                  ).status_code, 403)
        r = post("/api/team/user", {"op": "send", "id": uid, "can_send": True})
        eq(r.status_code, 200, r.text)
        ann = [u for u in r.json()["users"] if u["id"] == uid][0]
        eq(ann["can_send"], True)
        eq(ann["send_by_rank"], False, "a member holds it only because it was handed over")
        al = [u for u in r.json()["users"] if u["id"] == adm][0]
        eq(al["send_by_rank"], True, "an admin holds it by rank")
        # The browser draws the compose button off the sign-in reply, long
        # before it ever asks Team for a list of people.
        me = login("ann", "chosen-pw-123456").json()["me"]
        eq(me["can_send"], True, "the grant reaches the page at sign-in")
        eq(me["send_by_rank"], False)
        st = post_s(sess, "/api/auth/state", {}).json()["me"]
        eq(st["can_send"], True, "and again on a reload")
        ok(isinstance(st["tabs"], list), "and the tab list is still the resolved one")
        # And is therefore not a switch: pretending to revoke it would lie.
        r2 = post("/api/team/user", {"op": "send", "id": adm, "can_send": False})
        eq(r2.status_code, 400, r2.text)
        ok(team._may_send_mail(adm), "still theirs, whatever the switch said")
        eq(post("/api/team/user", {"op": "send", "id": uid, "can_send": False}
                ).status_code, 200)
        eq(team._may_send_mail(uid), False, "and a member's really does come back off")
    with_accounts(go)

@test
def t_the_address_book_is_behind_the_send_grant():
    """The book exists ONLY to address an email. An account that cannot send
    has no reason to be handed the shop's whole customer list, so it sits
    behind the same grant the send does rather than behind the Inbox tab."""
    def go():
        ensure_auth()
        crm_wipe()
        uid, sess, _ = ready_user("Ann", "ann")
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        r = post_s(sess, "/api/mail/addresses", {})
        eq(r.status_code, 403, r.text)
        ok("not set up to send" in r.json()["error"], r.text)
        ok("addresses" not in r.json(), "and not one row leaks with the refusal")
        eq(post("/api/team/user", {"op": "send", "id": uid, "can_send": True}
                ).status_code, 200)
        r2 = post_s(sess, "/api/mail/addresses", {})
        eq(r2.status_code, 200, r2.text)
        eq([a["email"] for a in r2.json()["addresses"]], ["jo@customer.com"])
        eq(r2.json()["count"], 1)
        # The master holds it by rank, exactly as it holds the send.
        eq(post("/api/mail/addresses", {}).status_code, 200)
    with_mail(go)

@test
def t_the_address_book_merges_the_inbox_and_the_crm():
    """One row per person, and the CRM's version of who they are wins: a
    thread carries whatever the sender's mail client put in the From line
    that day, the CRM carries what somebody here typed on purpose."""
    store = {"threads": {
        "t1": {"id": "t1", "from_name": "jo b", "from_email": "jo@northlight.test"},
        "t2": {"id": "t2", "from_name": "Sam Stage", "from_email": "sam@elsewhere.test"},
        # The same person again, shouting. One row, not two.
        "t3": {"id": "t3", "from_name": "JO", "from_email": "JO@northlight.test"},
        # Us. Offering the shop its own address is offering a loop.
        "t4": {"id": "t4", "from_name": "Sales", "from_email": MBOX},
        "t5": {"id": "t5", "from_name": "Sales again", "from_email": MBOX.upper()},
        # Nothing anybody could send to.
        "t6": {"id": "t6", "from_name": "Nobody", "from_email": ""},
        "t7": {"id": "t7", "from_name": "Broken", "from_email": "not-an-address"},
        "t8": {"id": "t8", "from_name": "Halfway", "from_email": "half@"},
        # A sender whose client sent no name at all.
        "t9": {"id": "t9", "from_name": "", "from_email": "anon@anywhere.test"},
        # These two cross: by name they are first and last, by address they
        # are last and first. Ordering by the wrong field cannot hide here.
        "t10": {"id": "t10", "from_name": "ada vance", "from_email": "zoe@vance.test"},
        "t11": {"id": "t11", "from_name": "Zed Ash", "from_email": "ada@ash.test"},
    }}
    crm = {"persons": {
        "p1": {"id": "p1", "name": "Jo Bloggs", "org_id": "o1",
               "emails": ["jo@northlight.test", "jo.b@northlight.test"]},
        "p2": {"id": "p2", "name": "Pat Price", "org_id": "", "emails": ["pat@nowhere.test"]},
        "p3": {"id": "p3", "name": "Junk", "org_id": "o1", "emails": ["", "   ", "bad@"]},
    }, "orgs": {"o1": {"id": "o1", "name": "Northlight Studios"}}}
    rows = mail._mail_address_book(store, crm, MBOX)
    eq([r["email"] for r in rows],
       ["anon@anywhere.test", "zoe@vance.test", "jo.b@northlight.test",
        "jo@northlight.test", "pat@nowhere.test", "sam@elsewhere.test", "ada@ash.test"],
       "sorted by name (case ignored) then email, nameless first, nothing unsendable")
    by = {r["email"]: r for r in rows}
    eq((by["jo@northlight.test"]["name"], by["jo@northlight.test"]["sub"]),
       ("Jo Bloggs", "Northlight Studios"), "the CRM's name and firm win over the thread's")
    eq((by["sam@elsewhere.test"]["name"], by["sam@elsewhere.test"]["sub"]),
       ("Sam Stage", ""), "a thread-only sender keeps their From name, with no firm")
    eq(by["pat@nowhere.test"]["sub"], "", "a person with no organisation has no sub-line")
    eq(by["anon@anywhere.test"]["name"], "",
       "a missing name stays missing; it never falls back to the address")
    for r in rows:
        eq(sorted(r), ["email", "name", "sub"], "the book carries nothing else")
    eq(mail._mail_address_book(store, crm, MBOX.upper()),
       rows, "our own address is ours whatever case it is written in")
    eq(mail._mail_address_book({}, {}, MBOX), [], "two empty stores make an empty book")

@test
def t_the_address_book_route_serves_both_stores_and_nothing_else():
    def go():
        ensure_auth()
        crm_wipe()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("m1", "Gobo order", frm=("Jo B", "jo@customer.com"))
        _seed_thread("m2", "Stranger", frm=("Sam Stage", "sam@elsewhere.test"))
        _seed_thread("m3", "Our own", frm=("Sales", MBOX))
        org = post("/api/crm/contact", {"op": "org_add", "name": "Customer Co"}).json()["id"]
        post("/api/crm/contact", {"op": "person_add", "name": "Jo Bloggs", "org_id": org,
                                  "emails": ["jo@customer.com", "jo.b@customer.com"]})
        r = post("/api/mail/addresses", {})
        eq(r.status_code, 200, r.text)
        body = r.json()
        eq(sorted(body), ["addresses", "count"])
        eq([a["email"] for a in body["addresses"]],
           ["jo.b@customer.com", "jo@customer.com", "sam@elsewhere.test"],
           "both stores, deduped, and never the mailbox itself")
        eq(body["count"], len(body["addresses"]))
        jo = [a for a in body["addresses"] if a["email"] == "jo@customer.com"][0]
        eq((jo["name"], jo["sub"]), ("Jo Bloggs", "Customer Co"))
        for a in body["addresses"]:
            eq(sorted(a), ["email", "name", "sub"], "no order history rides along")
    with_mail(go)

@test
def t_sync_does_not_call_a_gizmo_send_a_reply_from_gmail():
    """The send already logged itself, by name. Logging it again when Gmail
    hands the message back would tell the room somebody used Gmail instead."""
    def go():
        ensure_auth()
        store = mail._load_mail()
        _seed_thread("t1")
        t = store["threads"]["t1"]
        t["state"], t["sent_msg_id"] = "waiting", "our-reply"
        mail._mail_apply_thread(store, {"id": "t1", "historyId": "h2", "subject": "Gobo order",
            "messages": [_mk_msg("t1-m1", "Jo Bloggs", "jo@customer.com", "2026-08-19T01:00:00+00:00"),
                         _mk_msg("our-reply", "Sales", MBOX, "2026-08-19T03:00:00+00:00")]}, MBOX)
        eq(any(a["action"] == "replied from Gmail" for a in t["activity"]), False,
           str(t["activity"]))
        eq(t["state"], "waiting")
        # Somebody actually replying in Gmail is still reported.
        mail._mail_apply_thread(store, {"id": "t1", "historyId": "h3", "subject": "Gobo order",
            "messages": [_mk_msg("t1-m9", "Sales", MBOX, "2026-08-19T04:00:00+00:00")]}, MBOX)
        ok(any(a["action"] == "replied from Gmail" for a in t["activity"]), str(t["activity"]))
    with_mail(go)

@test
def t_mail_own_unsent_drafts_are_not_part_of_the_conversation():
    """A draft sitting in Gmail must not read as a reply we already sent,
    on the board or in the next prompt."""
    def go():
        ensure_auth()
        thread = {"id": "t1", "historyId": "h1", "messages": [
            {"id": "m1", "labelIds": ["INBOX"], "internalDate": "1787000000000",
             "snippet": "where is it", "payload": {"headers": [
                 {"name": "From", "value": "Jo <jo@customer.com>"},
                 {"name": "Subject", "value": "Order"}]}},
            {"id": "m2", "labelIds": ["DRAFT"], "internalDate": "1787000900000",
             "snippet": "our unsent words", "payload": {"headers": [
                 {"name": "From", "value": "Sales <" + MBOX + ">"},
                 {"name": "Subject", "value": "Re: Order"}]}}]}
        async def fake_call(method, path, params=None, body=None, **kw):
            return thread
        saved = _gm._call
        _gm._call = fake_call
        try:
            got = run_async(_gm.get_thread("t1"))
            eq(len(got["messages"]), 1, "the unsent draft is not a message on the board")
            eq(got["messages"][0]["from_email"], "jo@customer.com")
            read = run_async(_gm.read_thread("t1"))
            eq(len(read["messages"]), 1, "and Claude never reads our own draft back")
        finally:
            _gm._call = saved
    with_mail(go)

@test
def t_mail_rule_is_exactly_means_exactly():
    def go():
        ensure_auth()
        post("/api/mail/rules", {"op": "save", "rule": {
            "name": "Newsletter", "done": True,
            "conditions": [{"field": "subject", "op": "is", "value": "newsletter"}]}})
        _seed_thread("r1", subject="Re: newsletter query, can you quote 40 gobos?")
        eq(mail._load_mail()["threads"]["r1"]["state"], "unassigned",
           "a real enquiry containing the word is NOT the word")
        _seed_thread("r2", subject="Newsletter")
        eq(mail._load_mail()["threads"]["r2"]["state"], "done", "the exact subject still matches")
        # A display name can no longer impersonate an address.
        post("/api/mail/rules", {"op": "save", "rule": {
            "name": "Boss", "done": True,
            "conditions": [{"field": "from", "op": "is", "value": "boss@bigcustomer.com"}]}})
        _seed_thread("r3", subject="hello", frm=("boss@bigcustomer.com", "spoof@spammer.example"))
        eq(mail._load_mail()["threads"]["r3"]["state"], "unassigned",
           "a stranger putting that address in their DISPLAY NAME does not match it")
        _seed_thread("r5", subject="hello", frm=("The Boss", "boss@bigcustomer.com"))
        eq(mail._load_mail()["threads"]["r5"]["state"], "done", "the real address does")
        # A non-address value still matches the name, which is what it is for.
        post("/api/mail/rules", {"op": "save", "rule": {
            "name": "Accounts", "done": True,
            "conditions": [{"field": "from", "op": "is", "value": "Accounts"}]}})
        _seed_thread("r6", subject="hello", frm=("Accounts", "ap@theatre.org"))
        eq(mail._load_mail()["threads"]["r6"]["state"], "done", "names still work")
        _seed_thread("r4", subject="hello", frm=("Someone", "boss@bigcustomer.com.evil.com"))
        eq(mail._load_mail()["threads"]["r4"]["state"], "unassigned",
           "but a lookalike address is not an exact match")
    with_mail(go)

@test
def t_mail_rule_that_cannot_assign_does_not_let_the_next_one_close_it():
    """The critical one: a VIP rule whose owner loses the Inbox tab must not
    fall through to a catch-all that closes the customer's email."""
    def go():
        ensure_auth()
        uid_a, _s, _ = ready_user("Ann", "ann")
        post("/api/mail/rules", {"op": "save", "rule": {
            "name": "VIP", "assign": uid_a,
            "conditions": [{"field": "domain", "op": "is", "value": "bigcustomer.com"}]}})
        post("/api/mail/rules", {"op": "save", "rule": {
            "name": "Bulk", "done": True,
            "conditions": [{"field": "subject", "op": "contains", "value": "order"}]}})
        _seed_thread("v1", subject="order query", frm=("Boss", "boss@bigcustomer.com"))
        eq(mail._load_mail()["threads"]["v1"]["owner"], uid_a, "normally VIP wins")
        post("/api/team/user", {"op": "tabs", "id": uid_a, "tabs": ["overview"]})
        _seed_thread("v2", subject="order query two", frm=("Boss", "boss@bigcustomer.com"))
        t = mail._load_mail()["threads"]["v2"]
        eq(t["state"], "unassigned", "a broken VIP rule leaves it VISIBLE, never closed")
        eq(t["owner"], "")
        rule = [r for r in mail._load_mail()["rules"] if r["name"] == "VIP"][0]
        ok(rule.get("broken"), "and the filter itself reports the fault")
    with_mail(go)

@test
def t_mail_rule_files_into_a_gmail_folder():
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        r = post("/api/mail/rules", {"op": "save", "rule": {
            "name": "Newsletters", "folder": "Newsletters", "archive": True,
            "conditions": [{"field": "domain", "op": "is", "value": "leadgenblast.io"}]}})
        eq(r.status_code, 200, r.text)
        # Filing alone is a real action: it does not also need an owner.
        eq(post("/api/mail/rules", {"op": "save", "rule": {
            "name": "Quotes", "folder": "Quotes",
            "conditions": [{"field": "subject", "op": "contains", "value": "quote"}]}}).status_code,
           200)
        # Archiving with nowhere to file it would just hide the email.
        eq(post("/api/mail/rules", {"op": "save", "rule": {
            "name": "Vanish", "archive": True,
            "conditions": [{"field": "subject", "op": "contains", "value": "x"}]}}).status_code, 400)
        _seed_thread("n1", subject="Grow your business", frm=("Lead Gen", "hi@leadgenblast.io"))
        t = mail._load_mail()["threads"]["n1"]
        eq(t["folder"], "Newsletters", "the intent is recorded on arrival")
        ok(t["folder_archive"], "including taking it out of the inbox")
        ok(not t.get("folder_done"), "and Gmail has not been called yet")
        # The sync carries it out, once.
        calls = []
        async def modify(tid, add=None, remove=None):
            calls.append({"id": tid, "add": add, "remove": remove})
        async def label(name, known):
            known[name] = "L_" + name
            return known[name]
        async def listing(q, n):
            return {"threads": [], "complete": True}
        saved = (_gm.modify_thread, _gm.ensure_label, _gm.list_threads)
        _gm.modify_thread, _gm.ensure_label, _gm.list_threads = modify, label, listing
        try:
            mail._load_mail()["synced_at"] = ""
            post("/api/mail/board", {"force": True})
            filed = [c for c in calls if c["add"] == ["L_Newsletters"]]
            eq(len(filed), 1, "filed exactly once")
            eq(filed[0]["remove"], ["INBOX"], "and taken out of the inbox as asked")
            eq(mail._load_mail()["threads"]["n1"]["folder_done"], "Newsletters")
            calls.clear()
            mail._load_mail()["synced_at"] = ""
            post("/api/mail/board", {"force": True})
            eq([c for c in calls if c["add"] == ["L_Newsletters"]], [],
               "and never filed again on later syncs")
        finally:
            _gm.modify_thread, _gm.ensure_label, _gm.list_threads = saved
    with_mail(go)

@test
def t_mail_rule_needs_something_positive_to_match_on():
    def go():
        ensure_auth()
        r = post("/api/mail/rules", {"op": "save", "rule": {
            "name": "Catch all", "done": True,
            "conditions": [{"field": "subject", "op": "not_contains", "value": "zzzz"}]}})
        eq(r.status_code, 400, "a lone 'does not contain' would swallow the inbox")
        eq(post("/api/mail/rules", {"op": "save", "rule": {
            "name": "Round with nobody", "assign": "_round", "pool": [],
            "conditions": [{"field": "subject", "op": "contains", "value": "x"}]}}).status_code,
           400, "sharing between nobody is not an action")
        # A narrowing not_contains alongside a positive match is fine.
        eq(post("/api/mail/rules", {"op": "save", "rule": {
            "name": "Quotes but not spam", "done": True, "mode": "all",
            "conditions": [{"field": "subject", "op": "contains", "value": "quote"},
                           {"field": "subject", "op": "not_contains", "value": "seo"}]}}).status_code,
           200, "as a narrowing clause it is exactly right")
    with_mail(go)

@test
def t_mail_body_charset_and_entities_survive():
    import base64 as _b64
    raw = "Budget is £450 for Dave O’Brien".encode("cp1252")
    part = {"mimeType": "text/plain",
            "headers": [{"name": "Content-Type", "value": 'text/plain; charset="windows-1252"'}],
            "body": {"data": _b64.urlsafe_b64encode(raw).decode().rstrip("=")}}
    out = {}
    _gm._walk_body(part, out)
    ok("£450" in out.get("plain", ""), "a pound sign is not mangled: " + repr(out.get("plain")))
    txt = _gm._strip_html("<div>20 gobos for &pound;12.50</div><div>Total &#163;250 &mdash; ok?</div>")
    ok("£12.50" in txt and "£250" in txt, "entities are decoded, not shown raw: " + txt)
    ok("script" not in _gm._strip_html("<script>alert(1)").lower(),
       "an unterminated script does not survive as text")
    # An attached .eml must not be read as the sender's own words.
    out = {}
    _gm._walk_body({"mimeType": "message/rfc822", "filename": "forwarded.eml", "parts": [
        {"mimeType": "text/plain", "body": {"data": _b64.urlsafe_b64encode(
            b"words from a different email").decode().rstrip("=")}}]}, out)
    eq(out.get("plain"), None, "an attachment is not the message")

@test
def t_mail_draft_compose_asks_claude_with_the_conversation():
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1", subject="Quote please")
        async def fake_read(tid, per_msg_chars=4000):
            return {"id": tid, "messages": [
                {"id": "m1", "from_name": "Jo", "from_email": "jo@customer.com",
                 "subject": "Quote please", "message_id": "<a@b>", "references": "",
                 "reply_to": "", "at": "2026-08-19T01:00:00+00:00",
                 "text": "How much for six B-size steel gobos?"}]}
        seen = {}
        class _Blk:
            type = "text"
            def __init__(self, t): self.text = t
        class _Resp:
            content = [_Blk("Hi Jo, six B-size steel gobos come to ____ including artwork.")]
            usage = None
        async def fake_create(client, **kw):
            seen.update(kw)
            return _Resp()
        saved = (_gm.read_thread, claude._xcreate, claude.ANTHROPIC_API_KEY)
        _gm.read_thread = fake_read
        claude._xcreate = fake_create
        claude.ANTHROPIC_API_KEY = "x"
        try:
            r = post_s(sess, "/api/mail/draft", {"id": "t1", "op": "compose",
                                                 "guidance": "mention the 3 week lead time"})
            eq(r.status_code, 200, r.text)
            ok("____" in r.json()["draft"], "gaps rather than invented facts")
            prompt = seen["messages"][0]["content"]
            ok("six B-size steel gobos" in prompt, "the real conversation is in the prompt")
            ok("mention the 3 week lead time" in prompt, "and so is the steer")
            ok("Ann" in prompt, "it writes as the person handling it")
            ok("NEVER invent a fact" in seen["system"], "the no-invention rule is enforced")
        finally:
            _gm.read_thread, claude._xcreate, claude.ANTHROPIC_API_KEY = saved
    with_mail(go)

@test
def t_mail_rules_sort_arriving_mail_and_never_steal_live_work():
    def go():
        ensure_auth()
        uid_a, sess_a, _ = ready_user("Ann", "ann")
        # Leads only.
        eq(post_s(sess_a, "/api/mail/rules", {"op": "save", "rule": {}}).status_code, 403)
        eq(post_s(sess_a, "/api/mail/rules", {"op": "list"}).status_code, 200,
           "but anyone may see what the standing decisions are")
        # A rule has to match something and do something.
        eq(post("/api/mail/rules", {"op": "save", "rule": {"name": "Empty"}}).status_code, 400)
        eq(post("/api/mail/rules", {"op": "save", "rule": {
            "name": "No action", "conditions": [{"field": "from", "op": "contains",
                                                 "value": "x"}]}}).status_code, 400)
        r = post("/api/mail/rules", {"op": "save", "rule": {
            "name": "Newsletters", "done": True,
            "conditions": [{"field": "domain", "op": "is", "value": "leadgenblast.io"}]}})
        eq(r.status_code, 200, r.text)
        post("/api/mail/rules", {"op": "save", "rule": {
            "name": "Invoices", "assign": uid_a,
            "conditions": [{"field": "subject", "op": "contains", "value": "invoice"}]}})
        store = mail._load_mail()
        # Junk closes itself on arrival.
        _seed_thread("j1", subject="Grow your business", frm=("Lead Gen", "hi@leadgenblast.io"))
        eq(store["threads"]["j1"]["state"], "done", "junk never becomes somebody's job")
        # A subject rule hands the thread to the right person.
        _seed_thread("i1", subject="Copy invoice INV-2291 please")
        eq(store["threads"]["i1"]["owner"], uid_a)
        eq(store["threads"]["i1"]["state"], "assigned")
        ok(any("Invoices" in a["action"] for a in store["threads"]["i1"]["activity"]))
        # Ordinary mail is untouched.
        _seed_thread("o1", subject="Quote for 6 gobos")
        eq(store["threads"]["o1"]["state"], "unassigned")
        # A LATER message must never re-file a live conversation.
        store["threads"]["o1"]["subject"] = "Quote, now about the invoice"
        mail._mail_apply_thread(store, {
            "id": "o1", "historyId": "h9", "subject": "Re: invoice attached",
            "messages": [_mk_msg("o1-m1", "Jo", "jo@customer.com", "2026-08-19T01:00:00+00:00"),
                         _mk_msg("o1-m2", "Jo", "jo@customer.com", "2026-08-19T05:00:00+00:00")]}, MBOX)
        eq(store["threads"]["o1"]["owner"], "", "a reply does not re-triage the thread")
    with_mail(go)

@test
def t_mail_rules_run_over_existing_leaves_owned_mail_alone():
    def go():
        ensure_auth()
        uid_a, sess_a, _ = ready_user("Ann", "ann")
        _seed_thread("e1", subject="Invoice query")
        _seed_thread("e2", subject="Invoice chase")
        _seed_thread("e3", subject="Artwork")
        post_s(sess_a, "/api/mail/claim", {"id": "e2"})     # Ann is working this one
        post("/api/mail/rules", {"op": "save", "rule": {
            "name": "Invoices", "assign": uid_a,
            "conditions": [{"field": "subject", "op": "contains", "value": "invoice"}]}})
        r = post("/api/mail/rules", {"op": "run"})
        eq(r.status_code, 200, r.text)
        eq(r.json()["changed"], 1, "only the untouched one is sorted")
        th = mail._load_mail()["threads"]
        eq(th["e1"]["owner"], uid_a)
        eq(th["e3"]["state"], "unassigned", "and unrelated mail is left alone")
    with_mail(go)

@test
def t_mail_rules_round_robin_shares_the_load():
    def go():
        ensure_auth()
        uid_a, _sa, _ = ready_user("Ann", "ann")
        uid_b, _sb, _ = ready_user("Bob", "bob")
        post("/api/mail/rules", {"op": "save", "rule": {
            "name": "Share the quotes", "assign": "_round", "pool": [uid_a, uid_b],
            "conditions": [{"field": "subject", "op": "contains", "value": "quote"}]}})
        for i in range(4):
            _seed_thread("q%d" % i, subject="Quote request %d" % i)
        owners = [mail._load_mail()["threads"]["q%d" % i]["owner"] for i in range(4)]
        eq(owners, [uid_a, uid_b, uid_a, uid_b], "the work alternates between them")
    with_mail(go)

@test
def t_mail_rules_edit_toggle_reorder_and_delete():
    def go():
        ensure_auth()
        uid_a, _s, _ = ready_user("Ann", "ann")
        a = post("/api/mail/rules", {"op": "save", "rule": {
            "name": "First", "done": True,
            "conditions": [{"field": "subject", "op": "contains", "value": "spam"}]}}).json()["id"]
        b = post("/api/mail/rules", {"op": "save", "rule": {
            "name": "Second", "assign": uid_a,
            "conditions": [{"field": "subject", "op": "contains", "value": "spam"}]}}).json()["id"]
        # First match wins, so order is priority.
        _seed_thread("s1", subject="spam thing")
        eq(mail._load_mail()["threads"]["s1"]["state"], "done")
        post("/api/mail/rules", {"op": "move", "id": b})     # promote Second
        _seed_thread("s2", subject="spam thing two")
        eq(mail._load_mail()["threads"]["s2"]["owner"], uid_a, "order decides")
        # Switching one off takes it out of the running, keeping its history.
        post("/api/mail/rules", {"op": "toggle", "id": b})
        _seed_thread("s3", subject="spam thing three")
        eq(mail._load_mail()["threads"]["s3"]["state"], "done")
        # Editing keeps the id and the hit count.
        before = [r for r in mail._load_mail()["rules"] if r["id"] == a][0]["hits"]
        ok(before > 0)
        post("/api/mail/rules", {"op": "save", "rule": {
            "id": a, "name": "Renamed", "done": True,
            "conditions": [{"field": "subject", "op": "contains", "value": "spam"}]}})
        after = [r for r in mail._load_mail()["rules"] if r["id"] == a][0]
        eq(after["name"], "Renamed")
        eq(after["hits"], before, "an edit does not reset what the filter has done")
        eq(post("/api/mail/rules", {"op": "delete", "id": a}).status_code, 200)
        eq(len(post("/api/mail/rules", {"op": "list"}).json()["rules"]), 1)
        eq(post("/api/mail/rules", {"op": "delete", "id": "nope"}).status_code, 404)
    with_mail(go)

