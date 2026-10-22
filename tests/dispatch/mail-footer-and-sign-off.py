# =========================== mail: footer, sign-off, saved replies ==========
# What actually leaves the building is the staff member's words, then their
# sign-off, then the shop's footer. The words are theirs; the other two are
# settings, stamped on at the moment of sending so a draft written yesterday
# still goes out under today's footer.




@test
def t_mail_settings_get_reports_the_shop_footer_and_your_own_signoff():
    def go():
        ensure_auth()
        j = post("/api/mail/settings", {"op": "get"}).json()
        eq(j["footer_slots"]["legal"], "", "nothing set yet")
        eq(j["footer_text"], "", "and nothing to stamp on")
        eq(j["saved_replies"], [])
        eq(j["sign_off"], "")
        eq(j["lead"], True, "the master is a lead")
        eq(post("/api/mail/settings", {"op": "footer_slots",
                                       "slots": {"company": "Projected Image Ltd"}}
                ).status_code, 200)
        eq(post("/api/mail/settings", {"op": "sign_off", "text": "Thanks,\nCameron"}
                ).status_code, 200)
        j2 = post("/api/mail/settings", {"op": "get"}).json()
        eq(j2["footer_slots"]["company"], "Projected Image Ltd")
        eq(j2["footer_text"], "Projected Image Ltd")
        eq(j2["sign_off"], "Thanks,\nCameron")
        # The sign-off is PER PERSON: a second account sees the shop footer but
        # its own (empty) sign-off, never the master's name.
        _uid, sess, _pw = ready_user("Ann", "ann")
        j3 = post_s(sess, "/api/mail/settings", {"op": "get"}).json()
        eq(j3["footer_text"], "Projected Image Ltd", "the footer is the shop's")
        eq(j3["sign_off"], "", "the sign-off is not")
        eq(j3["lead"], False, "and a member is not a lead")
    with_mail(go)


@test
def t_mail_footer_is_a_lead_decision_and_the_signoff_is_your_own():
    """The footer goes out on everybody's email, so it is a decision for the
    room. A sign-off is a person's own name, so it is not."""
    def go():
        ensure_auth()
        _uid, sess, _pw = ready_user("Ann", "ann")
        r = post_s(sess, "/api/mail/settings", {"op": "footer_slots",
                                                "slots": {"company": "Ann's shop"}})
        eq(r.status_code, 403, r.text)
        eq(r.json()["error"], "Only a lead can change the footer.")
        eq(post("/api/mail/settings", {"op": "get"}).json()["footer_text"], "",
           "and nothing was written")
        # Her own sign-off needs nobody's permission.
        eq(post_s(sess, "/api/mail/settings", {"op": "sign_off", "text": "Ann"}
                  ).status_code, 200)
        eq(post_s(sess, "/api/mail/settings", {"op": "get"}).json()["sign_off"], "Ann")
        eq(post("/api/mail/settings", {"op": "get"}).json()["sign_off"], "",
           "and it did not land on anybody else")
    with_mail(go)


@test
def t_mail_footer_and_signoff_have_caps_that_are_actually_enforced():
    def go():
        ensure_auth()
        r = post("/api/mail/settings", {"op": "footer_slots", "slots": {"legal": "x" * 201}})
        eq(r.status_code, 400, r.text)
        eq(post("/api/mail/settings", {"op": "footer_slots", "slots": {"legal": "x" * 200}}
                ).status_code, 200, "200 is allowed")
        r = post("/api/mail/settings", {"op": "sign_off", "text": "y" * 201})
        eq(r.status_code, 400, r.text)
        eq(post("/api/mail/settings", {"op": "sign_off", "text": "y" * 200}
                ).status_code, 200, "200 is allowed")
        # Four lines is a sign-off; more is a second footer smuggled in under a
        # per-person setting that no lead approved.
        r = post("/api/mail/settings", {"op": "sign_off", "text": "a\nb\nc\nd\ne"})
        eq(r.status_code, 400, r.text)
        eq(post("/api/mail/settings", {"op": "sign_off", "text": "a\nb\nc\nd"}
                ).status_code, 200, "four lines is allowed")
        eq(post("/api/mail/settings", {"op": "get"}).json()["sign_off"], "a\nb\nc\nd")
    with_mail(go)


@test
def t_mail_saved_replies_are_a_lead_decision_with_caps():
    def go():
        ensure_auth()
        _uid, sess, _pw = ready_user("Ann", "ann")
        r = post_s(sess, "/api/mail/settings",
                   {"op": "reply_save", "title": "Lead time", "text": "Ten days."})
        eq(r.status_code, 403, r.text)
        r = post("/api/mail/settings",
                 {"op": "reply_save", "title": "Lead time", "text": "Ten days."})
        eq(r.status_code, 200, r.text)
        rid = r.json()["id"]
        ok(rid, "a saved reply gets an id")
        eq(r.json()["ok"], True)
        rows = post("/api/mail/settings", {"op": "get"}).json()["saved_replies"]
        eq(len(rows), 1)
        eq(rows[0], {"id": rid, "title": "Lead time", "text": "Ten days."})
        # Saving onto an existing id edits it rather than making a second copy.
        eq(post("/api/mail/settings", {"op": "reply_save", "id": rid,
                                       "title": "Lead times", "text": "About ten days."}
                ).json()["id"], rid)
        rows = post("/api/mail/settings", {"op": "get"}).json()["saved_replies"]
        eq(len(rows), 1, "edited, not duplicated")
        eq(rows[0]["title"], "Lead times")
        # Caps.
        eq(post("/api/mail/settings", {"op": "reply_save", "title": "", "text": "x"}
                ).status_code, 400, "a saved reply needs a title")
        eq(post("/api/mail/settings", {"op": "reply_save", "title": "t" * 81, "text": "x"}
                ).status_code, 400)
        eq(post("/api/mail/settings", {"op": "reply_save", "title": "ok", "text": ""}
                ).status_code, 400, "and something to say")
        eq(post("/api/mail/settings", {"op": "reply_save", "title": "ok",
                                       "text": "x" * 5001}).status_code, 400)
        # Fifty is the ceiling.
        for i in range(49):
            eq(post("/api/mail/settings", {"op": "reply_save", "title": "t%d" % i,
                                           "text": "x"}).status_code, 200, str(i))
        r = post("/api/mail/settings", {"op": "reply_save", "title": "one too many",
                                        "text": "x"})
        eq(r.status_code, 400, r.text)
        eq(len(post("/api/mail/settings", {"op": "get"}).json()["saved_replies"]), 50)
        # Deleting is a lead's job too.
        eq(post_s(sess, "/api/mail/settings", {"op": "reply_delete", "id": rid}
                  ).status_code, 403)
        eq(post("/api/mail/settings", {"op": "reply_delete", "id": rid}
                ).json()["ok"], True)
        rows = post("/api/mail/settings", {"op": "get"}).json()["saved_replies"]
        eq(len(rows), 49)
        ok(all(x["id"] != rid for x in rows), "the right one went")
    with_mail(go)


@test
def t_mail_an_admin_can_set_somebody_elses_signoff_by_rank():
    """Somebody who has left, or who never filled it in, still needs a name on
    their outgoing email. Same rank rule as every other account change."""
    def go():
        ensure_auth()
        uid, sess, _pw = ready_user("Ann", "ann")
        eq(post("/api/team/user", {"op": "sign_off", "id": uid, "text": "Ann\nSales"}
                ).status_code, 200)
        eq(post_s(sess, "/api/mail/settings", {"op": "get"}).json()["sign_off"],
           "Ann\nSales")
        # A member is refused at the door of the team route entirely.
        r = post_s(sess, "/api/team/user", {"op": "sign_off", "id": uid, "text": "x"})
        eq(r.status_code, 403, r.text)
        # The rank rule proper: an admin may manage a member, but NOT an equal.
        # Two admins are needed to prove that, and only the master mints admins.
        a1, a1s, _ = ready_user("Ada", "ada", role="admin")
        a2, a2s, _ = ready_user("Ivy", "ivy", role="admin")
        eq(post_s(a1s, "/api/team/user", {"op": "sign_off", "id": uid, "text": "Ann"}
                  ).status_code, 200, "an admin may set a member's")
        r = post_s(a1s, "/api/team/user", {"op": "sign_off", "id": a2, "text": "nope"})
        eq(r.status_code, 403, "but not another admin's: " + r.text)
        eq(post_s(a2s, "/api/mail/settings", {"op": "get"}).json()["sign_off"], "",
           "and nothing was written")
        r = post_s(a1s, "/api/team/user", {"op": "sign_off",
                                           "id": APP_AUTH["master"], "text": "nope"})
        eq(r.status_code, 403, "nor the master's: " + r.text)
        # The caps hold on this door too.
        eq(post("/api/team/user", {"op": "sign_off", "id": uid, "text": "y" * 201}
                ).status_code, 400)
        eq(post("/api/team/user", {"op": "sign_off", "id": uid, "text": "a\nb\nc\nd\ne"}
                ).status_code, 400)
    with_mail(go)


@test
def t_the_team_list_shows_the_signoff_an_admin_is_allowed_to_change():
    """The team route lets an admin set somebody else's sign-off. Without the
    current value on the list they would be setting it blind, overwriting a
    name they never saw."""
    def go():
        ensure_auth()
        uid, _sess, _pw = ready_user("Ann", "ann")
        post("/api/team/user", {"op": "sign_off", "id": uid, "text": "Ann\nSales"})
        rows = post("/api/team/board", {}).json()["users"]
        row = next(r for r in rows if r["id"] == uid)
        eq(row["sign_off"], "Ann\nSales")
        me = next(r for r in rows if r["id"] == APP_AUTH["master"])
        eq(me["sign_off"], "", "and an unset one is empty, not missing")
    with_mail(go)


@test
def t_mail_board_carries_the_footer_and_the_callers_own_signoff():
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        post("/api/mail/settings", {"op": "footer_slots",
                                    "slots": {"company": "Projected Image Ltd"}})
        post("/api/mail/settings", {"op": "sign_off", "text": "Cameron"})
        post("/api/mail/settings", {"op": "reply_save", "title": "Lead time",
                                    "text": "Ten days."})
        j = post("/api/mail/board", {}).json()
        eq(j["email"]["footer_text"], "Projected Image Ltd")
        eq(j["email"]["sign_off"], "Cameron")
        eq(len(j["email"]["saved_replies"]), 1)
        eq(j["email"]["saved_replies"][0]["title"], "Lead time")
        _uid, sess, _pw = ready_user("Ann", "ann")
        j2 = post_s(sess, "/api/mail/board", {}).json()
        eq(j2["email"]["sign_off"], "", "the board carries YOUR sign-off, not the master's")
        eq(j2["email"]["footer_text"], "Projected Image Ltd")
    with_mail(go)


@test
def t_a_real_send_appends_the_signoff_and_the_footer():
    """The customer must receive the finished email, and the board must record
    the same words. A footer that only exists in the preview is a footer the
    shop thinks it is sending and is not."""
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1", subject="Where is my order?")
        post("/api/mail/settings", {"op": "footer_slots",
                                    "slots": {"company": "Projected Image Ltd",
                                              "phone": "0113 555 1111"}})
        post("/api/mail/settings", {"op": "sign_off", "text": "Thanks,\nCameron"})
        captured = {}
        async def fake_send(thread_id, to_addr, subject, body_text, **kw):
            captured["text"] = body_text
            # Read the durable stamp while it is still on the thread: it is
            # written before this call and cleared after it.
            captured["pending"] = dict(
                mail._load_mail()["threads"]["t1"].get("send_pending") or {})
            return {"id": "sent-1", "thread_id": thread_id}
        saved = (_gm.read_thread, _gm.send_message)
        _gm.read_thread, _gm.send_message = _one_from_customer(), fake_send
        try:
            r = post("/api/mail/send", {"id": "t1", "text": "They ship Friday."})
            eq(r.status_code, 200, r.text)
            # The quoted original now follows, so the assertion is on the
            # ORDER of what leaves rather than on the whole string: words,
            # then sign-off, then footer. The requirement is unchanged.
            ok(captured["text"].startswith(
               "They ship Friday.\n\nThanks,\nCameron\n\nProjected Image Ltd\n0113 555 1111"),
               "what Gmail was actually handed: " + captured["text"])
            ok("> Any news on my gobos?" in captured["text"], "with the original beneath it")
            eq(captured["pending"]["text"], captured["text"],
               "and the record written before the send says the same")
        finally:
            _gm.read_thread, _gm.send_message = saved
    with_mail(go)


@test
def t_a_new_conversation_gets_the_signoff_and_footer_too():
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        post("/api/mail/settings", {"op": "footer_slots",
                                    "slots": {"company": "Projected Image Ltd"}})
        post("/api/mail/settings", {"op": "sign_off", "text": "Cameron"})
        captured = {}
        async def fake_send(thread_id, to_addr, subject, body_text, **kw):
            captured["text"] = body_text
            captured["stamps"] = [dict(p) for p in
                                  (mail._load_mail().get("outbound_pending") or [])]
            return {"id": "sent-1", "thread_id": "T-NEW"}
        async def fake_get_thread(tid):
            return {"id": tid, "historyId": "h", "subject": "Your quote", "messages": []}
        saved = (_gm.send_message, _gm.get_thread)
        _gm.send_message, _gm.get_thread = fake_send, fake_get_thread
        try:
            r = post("/api/mail/send", {"to": "jo@customer.com", "subject": "Your quote",
                                        "text": "Here it is."})
            eq(r.status_code, 200, r.text)
            eq(captured["text"], "Here it is.\n\nCameron\n\nProjected Image Ltd")
            eq(captured["stamps"][0]["text"], captured["text"],
               "the outbound stamp holds the final text")
        finally:
            _gm.send_message, _gm.get_thread = saved
    with_mail(go)


@test
def t_the_dry_run_is_untouched_and_still_only_names_the_recipient():
    """The dry run exists to show the address before anybody commits. It must
    not start doing work, and it must still not reach Gmail or the store."""
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        post("/api/mail/settings", {"op": "footer_slots",
                                    "slots": {"company": "Projected Image Ltd"}})
        post("/api/mail/settings", {"op": "sign_off", "text": "Cameron"})
        sent = []
        async def fake_send(*a, **kw):
            sent.append(a)
            return {"id": "x", "thread_id": "t1"}
        saved = (_gm.read_thread, _gm.send_message)
        _gm.read_thread, _gm.send_message = _one_from_customer(), fake_send
        try:
            r = post("/api/mail/send", {"id": "t1", "text": "They ship Friday.", "dry": True})
            eq(r.status_code, 200, r.text)
            eq(r.json(), {"ok": True, "dry": True, "to": "jo@customer.com", "cc_count": 0,
                          "bcc_count": 0, "attachment_count": 0, "kind": "reply"},
               "the dry run reply names the recipient and counts, and nothing else")
            eq(sent, [], "and nothing was sent")
            eq(mail._load_mail()["threads"]["t1"].get("send_pending"), None,
               "and nothing was stamped")
        finally:
            _gm.read_thread, _gm.send_message = saved
    with_mail(go)


@test
def t_a_saved_draft_carries_the_signoff_and_footer_into_gmail():
    """The draft is what the person will read and send from Gmail. If the
    footer were only added on our own send path, every draft finished in Gmail
    would go out without one."""
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        post("/api/mail/settings", {"op": "footer_slots",
                                    "slots": {"company": "Projected Image Ltd"}})
        post("/api/mail/settings", {"op": "sign_off", "text": "Cameron"})
        captured = {}
        async def fake_create(thread_id, to_addr, subject, text, **kw):
            captured["text"] = text
            return {"id": "d1"}
        saved = (_gm.read_thread, _gm.create_draft)
        _gm.read_thread, _gm.create_draft = _one_from_customer(), fake_create
        try:
            r = post("/api/mail/draft", {"id": "t1", "op": "save",
                                         "text": "They ship Friday."})
            eq(r.status_code, 200, r.text)
            ok(captured["text"].startswith("They ship Friday.\n\nCameron\n\nProjected Image Ltd"),
               captured["text"])
            ok("> Any news on my gobos?" in captured["text"], "the original is quoted too")
            eq(mail._load_mail()["threads"]["t1"]["draft_text"], captured["text"],
               "and the board records what is actually in Gmail")
        finally:
            _gm.read_thread, _gm.create_draft = saved
    with_mail(go)


@test
def t_claude_is_told_not_to_sign_off_because_the_send_does_it():
    """Two sign-offs on one email is what happens if the model keeps writing
    one and the send appends another. The prompt has to give the job up."""
    # The prompt itself, not a slice of the file between two landmarks. That
    # slice only held while the constant sat directly above the route; it is a
    # module constant now, so the test can read the value it is about.
    prompt = mail.MAIL_DRAFT_SYSTEM
    ok("appended automatically" in prompt, "the prompt says the send adds them")
    ok("no sign-off, name or signature" in prompt, prompt[-900:])
    ok("Sign off with the staff member's first name" not in prompt,
       "and the old instruction to sign off is GONE, not merely contradicted")


