# =========================== mail: the composer's server half ===============
# Everything the browser sends is a suggestion. What actually leaves the shop
# is what mailmime allows, assembled into one MIME shape every client reads
# the same way.


@test
def t_a_dropped_tag_takes_its_subtree_and_not_the_rest_of_the_email():
    """The sanitiser is the last thing that touches an outgoing message, so a
    bug here is invisible: nobody sees the email that was sent.

    <embed> is void and <svg/> closes itself, so no end tag ever follows them.
    Both were being counted as the START of a dropped subtree, the skip counter
    never came back to zero, and every character after them was discarded. One
    inline SVG in a quoted signature - which is ordinary in marketing mail and
    in half the signatures in circulation - sent a reply that stopped
    mid-sentence, with no error anywhere."""
    import mailmime
    # The shapes that were broken: a void tag, and anything written self-closing.
    # Neither opens a subtree, so neither may consume what follows it.
    shapes = ["<embed>"] + ["<%s/>" % t for t in ("embed", "svg", "math", "template", "object", "iframe")]
    # A properly closed pair must also leave the text after it alone.
    shapes += ["<%s></%s>" % (t, t) for t in ("svg", "math", "template", "object", "iframe")]
    for shape in shapes:
        out = mailmime.sanitize_html("<p>before</p>" + shape + "<p>AFTER</p>")
        ok("AFTER" in out, "%s swallowed the rest of the message: %r" % (shape, out))
        ok("<svg" not in out and "<embed" not in out and "<object" not in out,
           "%s was not dropped: %r" % (shape, out))
    # An UNCLOSED pair is different, and dropping the remainder is correct: the
    # parser cannot know where the subtree ends, and unwrapping it would put the
    # contents of a <script> or an <svg> into the customer's mail client. Safety
    # wins over the text here, and this pins that it is a decision, not a lapse.
    out = mailmime.sanitize_html("<p>before</p><svg><p>AFTER</p>")
    ok("AFTER" not in out, "an unclosed dropped tag must keep swallowing: " + repr(out))
    # And the subtree is still taken, which is the whole reason these are dropped.
    out = mailmime.sanitize_html("<p>a</p><script>alert(1)</script><p>b</p>")
    ok("alert(1)" not in out and "a" in out and "b" in out, out)
    out = mailmime.sanitize_html("<p>a</p><svg><desc>HIDDEN</desc></svg><p>b</p>")
    ok("HIDDEN" not in out and "b" in out, out)


@test
def t_the_sanitiser_strips_every_known_injection_and_keeps_formatting():
    import mailmime
    keep = '<p>Hi <b>Jo</b>, <i>thanks</i> <u>again</u>.</p><ul><li>one</li></ul>' \
           '<a href="https://example.com/x">site</a> <span style="color:#b91c1c">red</span>'
    eq(mailmime.sanitize_html(keep), keep, "allowed markup passes through untouched")
    vectors = [
        '<script>alert(1)</script>', '<img src="https://evil.co/a.png">',
        '<a href="javascript:alert(1)">x</a>', '<p onclick="alert(1)">x</p>',
        '<img src="data:image/png;base64,AAAA">', '<svg onload="alert(1)"></svg>',
        '<span style="background:url(//evil.co/a)">x</span>', '<iframe src="https://x"></iframe>',
        '<style>p{color:red}</style>', '<a href="HTTPS://ok.com" onmouseover="x">ok</a>',
    ]
    for v in vectors:
        out = mailmime.sanitize_html(v)
        for bad in ("script", "onclick", "onload", "onmouseover", "javascript:", "evil.co",
                    "data:", "iframe", "<style", "url("):
            ok(bad not in out, f"{bad!r} survived in {out!r} from {v!r}")
    eq(mailmime.sanitize_html('<a href="HTTPS://ok.com" onmouseover="x">ok</a>'),
       '<a href="https://ok.com">ok</a>', "a good link keeps its href and loses the handler")
    eq(mailmime.sanitize_html('<img src="cid:logo1" alt="logo" width="120">'),
       '<img src="cid:logo1" alt="logo" width="120">', "content-id images are the only images")
    ok("<table" not in mailmime.sanitize_html("<table><tr><td>x</td></tr></table>"),
       "tables are not for customer bodies")
    ok("<table" in mailmime.sanitize_html("<table><tr><td>x</td></tr></table>", footer=True),
       "but the footer renderer may use them")


@test
def t_the_text_twin_reads_like_the_email():
    import mailmime
    html = '<p>Hi Jo,</p><p>Two things:</p><ul><li>artwork</li><li>sizes</li></ul>' \
           '<p>See <a href="https://example.com/x">the guide</a>.</p><br>Thanks'
    eq(mailmime.html_to_text(html),
       "Hi Jo,\n\nTwo things:\n\n- artwork\n- sizes\n\nSee the guide (https://example.com/x).\n\nThanks")


@test
def t_the_message_is_a_proper_mime_tree_with_a_text_twin_and_cids():
    import mailmime
    from email import message_from_bytes
    import email.policy as _epol
    raw = mailmime.build_message(
        frm="sales@shop.test", to="jo@customer.test", cc="pat@customer.test", subject="Your gobos",
        html='<p>Hi <b>Jo</b></p><img src="cid:img1" alt="proof">', text="Hi Jo\n[image: proof]",
        inline=[{"cid": "img1", "name": "proof.png", "type": "image/png", "data": b"\x89PNG..."}],
        files=[{"name": "quote.pdf", "type": "application/pdf", "data": b"%PDF-1.4"}],
        in_reply_to="<abc@mail>", references="<zzz@mail>")
    # policy=default so the parsed parts are MIMEParts with get_content(); the
    # compat32 default hands back bare Messages, which cannot decode a part.
    m = message_from_bytes(raw, policy=_epol.default)
    eq(m["Subject"], "Re: Your gobos"); eq(m["Cc"], "pat@customer.test")
    eq(m["In-Reply-To"], "<abc@mail>"); eq(m["References"], "<zzz@mail> <abc@mail>")
    eq(m.get_content_type(), "multipart/mixed")
    related, pdf = m.get_payload()
    eq(related.get_content_type(), "multipart/related")
    alt, img = related.get_payload()
    eq(alt.get_content_type(), "multipart/alternative")
    plain, htmlpart = alt.get_payload()
    eq(plain.get_content_type(), "text/plain"); eq(htmlpart.get_content_type(), "text/html")
    ok("Hi Jo" in plain.get_content(), "the text twin is the first alternative")
    eq(img["Content-ID"], "<img1>"); eq(img.get_content_disposition(), "inline")
    eq(pdf.get_filename(), "quote.pdf"); eq(pdf.get_content_disposition(), "attachment")
    plain_only = message_from_bytes(mailmime.build_message(
        frm="sales@shop.test", to="jo@customer.test", subject="Re: x", html="<p>hi</p>",
        text="hi", reply=False), policy=_epol.default)
    eq(plain_only.get_content_type(), "multipart/alternative", "no attachments, no outer wrappers")
    eq(plain_only["Subject"], "Re: x", "reply=False adds nothing and strips nothing")


@test
def t_the_footer_renders_its_slots_and_nothing_else():
    import mailmime
    html, text = mailmime.render_footer(
        {"company": "Projected Image UK Ltd", "address": "Unit 4, Bristol", "phone": "0117 000 0000",
         "website": "https://projectedimage.co.uk", "legal": "Registered in England 01234567"},
        logo_cid="logo1")
    ok('<img src="cid:logo1"' in html and "<table" in html, "logo by cid, in an email-safe table")
    ok('href="https://projectedimage.co.uk"' in html)
    ok("<script" not in mailmime.render_footer({"company": "<script>x</script>"})[0])
    eq(text, "Projected Image UK Ltd\nUnit 4, Bristol\n0117 000 0000\nhttps://projectedimage.co.uk\n"
             "Registered in England 01234567")
    eq(mailmime.render_footer({}), ("", ""), "no slots, no footer")


@test
def t_the_quoted_original_carries_its_formatting_and_a_header_line():
    import mailmime
    html, text = mailmime.quote_original({
        "from_name": "Sarah Parker", "from_email": "sarah@northlight.test",
        "at": "2026-09-02T09:15:00+00:00",
        "html": '<p>Can you <b>rush</b> it?</p><script>x</script>', "text": "Can you rush it?"})
    ok(html.startswith('<div class="gizmo-quote"><p>On 2 Sep 2026, Sarah Parker &lt;sarah@northlight.test&gt; wrote:</p><blockquote'))
    ok("<b>rush</b>" in html and "<script" not in html)
    eq(text, "On 2 Sep 2026, Sarah Parker <sarah@northlight.test> wrote:\n> Can you rush it?")
    h2, t2 = mailmime.quote_original({"from_name": "", "from_email": "x@y.test", "at": "", "html": "", "text": "plain only"})
    ok("<blockquote>plain only</blockquote>" in h2 and "x@y.test wrote:" in h2, "text-only originals quote as text")


def _run(coro):
    """The suite's asyncio runner, under its own loop."""
    return run_async(coro)


def _b64url(s):
    import base64
    return base64.urlsafe_b64encode(s.encode()).decode()


@test
def t_a_built_message_goes_through_gmails_upload_door_with_its_thread():
    captured = {}
    async def fake_post(url, headers, body):
        captured.update(url=url, headers=headers, body=body)
        return 200, {"id": "m9", "threadId": "t1"}
    async def fake_token(acct=None):
        return "tok"
    saved = (_gm._upload_post, _gm._token)
    _gm._upload_post, _gm._token = fake_post, fake_token
    try:
        out = _run(_gm.send_message("t1", "jo@c.test", "Hi", "", raw_bytes=b"From: a\r\n\r\nbody"))
        eq(out, {"id": "m9", "thread_id": "t1"})
        ok(captured["url"].endswith("/upload/gmail/v1/users/me/messages/send?uploadType=multipart"))
        ok(captured["headers"]["Content-Type"].startswith("multipart/related; boundary="))
        ok(b'{"threadId": "t1"}' in captured["body"] and b"message/rfc822" in captured["body"]
           and b"From: a\r\n\r\nbody" in captured["body"], "metadata then the raw message")
        _run(_gm.send_message("", "jo@c.test", "Hi", "", raw_bytes=b"x", new=True))
        ok(b"threadId" not in captured["body"], "a new message names no thread")
        _run(_gm.create_draft("t1", "jo@c.test", "Hi", "", raw_bytes=b"x"))
        ok(captured["url"].endswith("/upload/gmail/v1/users/me/drafts?uploadType=multipart"))
        ok(b'{"message": {"threadId": "t1"}}' in captured["body"], "a draft wraps the thread in message")
    finally:
        _gm._upload_post, _gm._token = saved


@test
def t_read_thread_keeps_the_html_of_a_message_for_quoting():
    # read_thread reads the RAW thread through _call (get_thread hands back the
    # board's normalised shape, not the part tree), so that is the seam faked.
    async def fake_call(method, path, *, params=None, body=None, acct=None):
        return {"id": "t1", "messages": [{"id": "m1", "payload": {"headers": [
            {"name": "From", "value": "Jo <jo@c.test>"}, {"name": "Subject", "value": "x"}],
            "mimeType": "text/html", "body": {"data": _b64url("<p>Hi <b>there</b></p>")}},
            "internalDate": "1756800000000"}]}
    saved = _gm._call; _gm._call = fake_call
    try:
        msgs = _run(_gm.read_thread("t1"))["messages"]
        eq(msgs[0]["html"], "<p>Hi <b>there</b></p>")
        eq(msgs[0]["text"], "Hi there")
    finally:
        _gm._call = saved


@test
def t_the_old_footer_moves_into_the_legal_slot_and_leads_edit_the_slots():
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        st = mail._load_mail(); st["email"] = {"footer": "Reg 01234567", "saved_replies": []}
        mail._write_mail(st)
        j = post("/api/mail/board", {}).json()
        eq(j["email"]["footer_slots"]["legal"], "Reg 01234567", "the free-text footer is not lost")
        ok("footer" not in mail._load_mail()["email"], "and the old key is gone")
        r = post("/api/mail/settings", {"op": "footer_slots", "slots": {"company": "PI Ltd", "website": "projectedimage.co.uk", "phone": "x" * 300}})
        eq(r.status_code, 400, "a slot over 200 chars is refused, not truncated silently")
        r = post("/api/mail/settings", {"op": "footer_slots", "slots": {"company": "PI Ltd", "website": "projectedimage.co.uk"}})
        eq(r.status_code, 200)
        j = post("/api/mail/board", {}).json()["email"]
        eq(j["footer_slots"]["company"], "PI Ltd")
        ok("<b>PI Ltd</b>" in j["footer_html"] and "PI Ltd" in j["footer_text"], "the board carries the rendered preview")
        _uid, sess, _ = ready_user("Ann", "ann")
        eq(post_s(sess, "/api/mail/settings", {"op": "footer_slots", "slots": {"company": "x"}}).status_code, 403)
    with_mail(go)


@test
def t_the_logo_lands_in_its_own_prefix_and_only_as_an_image():
    def go():
        ensure_auth(); _gm.save_connection("rt-test", MBOX)
        r = post("/api/mail/settings", {"op": "logo_url", "name": "logo.exe", "size": 1000, "type": "application/x-msdownload"})
        eq(r.status_code, 400)
        r = post("/api/mail/settings", {"op": "logo_url", "name": "logo.png", "size": 2 * 1024 * 1024, "type": "image/png"})
        eq(r.status_code, 400, "over 1MB is not a logo")
        r = post("/api/mail/settings", {"op": "logo_url", "name": "logo.png", "size": 40000, "type": "image/png"})
        eq(r.status_code, 200, r.text); key = r.json()["key"]
        ok(key.startswith("mail/footer/logo-") and key.endswith(".png"))
        s3.objects[key] = b"\x89PNG\r\n\x1a\n" + b"x" * 39992
        eq(post("/api/mail/settings", {"op": "logo_done", "key": key}).status_code, 200)
        eq(mail._load_mail()["email"]["footer_slots"]["logo_key"], key)
        eq(post("/api/mail/settings", {"op": "logo_done", "key": "files/other.png"}).status_code, 400, "keys outside the footer prefix are refused")
    s3 = FakeS3(); s3.bucket_exists = True
    with_files(lambda _s: with_mail(go), s3=s3)


@test
def t_attachments_upload_into_the_mail_prefix_behind_the_grant_and_within_the_cap():
    def go():
        ensure_auth(); _gm.save_connection("rt-test", MBOX)
        uid, sess, _ = ready_user("Ann", "ann")
        eq(post_s(sess, "/api/mail/attach-url", {"name": "q.pdf", "size": 1000, "type": "application/pdf"}).status_code, 403)
        post("/api/team/user", {"op": "send", "id": uid, "can_send": True})
        r = post_s(sess, "/api/mail/attach-url", {"name": "../../q.pdf", "size": 1000, "type": "application/pdf"})
        eq(r.status_code, 200, r.text); key = r.json()["key"]
        ok(key.startswith(f"mail/{uid}/") and ".." not in key and key.endswith("-q.pdf"))
        eq(post_s(sess, "/api/mail/attach-url", {"name": "big.zip", "size": 26 * 1024 * 1024, "type": "application/zip"}).status_code, 400)
        eq(post_s(sess, "/api/mail/attach-url", {"name": "x.pdf", "size": 1000, "type": "application/pdf", "inline": True}).status_code, 400, "inline must be an image")
        s3.objects[key] = b"%PDF" + b"x" * 996
        r = post_s(sess, "/api/mail/attach-done", {"key": key})
        eq(r.status_code, 200); eq(r.json()["size"], 1000); eq(r.json()["name"], "q.pdf")
        eq(post_s(sess, "/api/mail/attach-done", {"key": key + ".nope"}).status_code, 400, "a key that never landed")
        eq(post_s(sess, "/api/mail/attach-done", {"key": "mail/u-other/abc-x.pdf"}).status_code, 400, "someone else's prefix")
    s3 = FakeS3(); s3.bucket_exists = True
    with_files(lambda _s: with_mail(go), s3=s3)


@test
def t_fetching_parts_refuses_the_whole_set_when_one_is_missing_or_too_big():
    def go():
        ensure_auth()
        uid, _sess, _ = ready_user("Ann", "ann")
        # Keys in the shape the upload route mints: mail/<uid>/<16 hex>-<name>.
        # The fixture used "aa-" prefixes, which only passed while the name
        # was cut at ANY dash, and that is what named Files attachments wrong.
        hx = "0123456789abcdef"
        k1, k2 = f"mail/{uid}/{hx}-a.pdf", f"mail/{uid}/{hx[::-1]}-b.png"
        s3.objects[k1] = b"%PDF"; s3.objects[k2] = b"\x89PNG"
        files, inline, total = _run(mail._mail_fetch_parts([{"key": k1}], uid, inline_keys=[{"key": k2, "cid": "img1"}]))
        eq([f["name"] for f in files], ["a.pdf"]); eq(inline[0]["cid"], "img1"); eq(total, 8)
        try:
            _run(mail._mail_fetch_parts([{"key": k1}, {"key": f"mail/{uid}/{hx}-gone.pdf"}], uid))
            ok(False, "a missing part must refuse the set")
        except ValueError as e:
            ok("gone.pdf" in str(e))
        s3.objects[f"mail/{uid}/{hx}-huge.bin"] = b"x" * (mail.MAIL_ATTACH_MAX + 1)
        try:
            _run(mail._mail_fetch_parts([{"key": f"mail/{uid}/{hx}-huge.bin"}], uid)); ok(False)
        except ValueError as e:
            ok("25MB" in str(e))
        try:
            _run(mail._mail_fetch_parts([{"key": "files/other/x.pdf"}], uid)); ok(False)
        except ValueError as e:
            ok("not one of your" in str(e).lower() or "allowed" in str(e).lower())
    s3 = FakeS3(); s3.bucket_exists = True
    with_files(lambda _s: with_mail(go), s3=s3)


@test
def t_a_rich_reply_goes_out_sanitised_with_its_twin_footer_and_quote():
    def go():
        ensure_auth(); _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1", subject="Rush job")
        uid, sess, _ = ready_user("Ann", "ann"); post("/api/team/user", {"op": "send", "id": uid, "can_send": True})
        post("/api/team/user", {"op": "sign_off", "id": uid, "text": "Ann\nSales desk"})
        post("/api/mail/settings", {"op": "footer_slots", "slots": {"company": "PI Ltd", "legal": "Reg 1"}})
        async def fake_read(tid, per_msg_chars=4000):
            return {"id": tid, "messages": [{"id": "m1", "from_name": "Jo", "from_email": "jo@c.test", "reply_to": "", "to": MBOX, "cc": "pat@c.test",
                     "subject": "Rush job", "message_id": "<abc@mail>", "references": "", "at": "2026-09-01T10:00:00+00:00",
                     "text": "Can you rush it?", "html": "<p>Can you <b>rush</b> it?</p>"}]}
        captured = {}
        async def fake_send(thread_id, to_addr, subject, body_text, in_reply_to="", references="", cc="", new=False, raw_bytes=None):
            captured.update(thread_id=thread_id, to=to_addr, raw=raw_bytes); return {"id": "m2", "thread_id": thread_id}
        saved = (_gm.read_thread, _gm.send_message); _gm.read_thread, _gm.send_message = fake_read, fake_send
        try:
            k = f"mail/{uid}/0123456789abcdef-quote.pdf"; s3.objects[k] = b"%PDF-1.4"   # the minted shape
            body = {"id": "t1", "html": '<p>Hi <b>Jo</b></p><script>x</script>', "cc": "pat@c.test",
                    "attachments": [{"key": k, "name": "quote.pdf", "type": "application/pdf"}]}
            d = post_s(sess, "/api/mail/send", dict(body, dry=True)).json()
            eq(d["to"], "jo@c.test"); eq(d["cc_count"], 1); eq(d["attachment_count"], 1)
            ok("raw" not in captured, "a dry run sends nothing")
            r = post_s(sess, "/api/mail/send", body); eq(r.status_code, 200, r.text)
            from email import message_from_bytes
            import email.policy as _epol
            m = message_from_bytes(captured["raw"], policy=_epol.default)
            eq(m["Cc"], "pat@c.test"); eq(m["In-Reply-To"], "<abc@mail>")
            html = next(p for p in m.walk() if p.get_content_type() == "text/html").get_content()
            ok("<script" not in html and "<b>Jo</b>" in html)
            ok("Ann<br>Sales desk" in html or "<p>Ann<br>Sales desk</p>" in html, "sign-off as lines")
            ok("<b>PI Ltd</b>" in html and "Reg 1" in html, "footer slots rendered")
            ok('class="gizmo-quote"' in html and "<b>rush</b>" in html and html.index("PI Ltd") < html.index("gizmo-quote"), "quote last")
            text = next(p for p in m.walk() if p.get_content_type() == "text/plain").get_content()
            ok("Hi Jo" in text and "Ann\nSales desk" in text and "PI Ltd" in text and "> Can you rush it?" in text)
            eq([p.get_filename() for p in m.walk() if p.get_content_disposition() == "attachment"], ["quote.pdf"])
            t = mail._load_mail()["threads"]["t1"]
            eq(t["sent_attachments"], [{"name": "quote.pdf", "size": 8}])
            r = post_s(sess, "/api/mail/send", dict(body, attachments=[{"key": f"mail/{uid}/fedcba9876543210-gone.pdf"}]))
            eq(r.status_code, 400); ok("gone.pdf is missing" in r.json()["error"], r.json()["error"]); eq(t.get("send_pending"), None)
            r = post_s(sess, "/api/mail/send", dict(body, quote=False)); m = message_from_bytes(captured["raw"], policy=_epol.default)
            ok("gizmo-quote" not in next(p for p in m.walk() if p.get_content_type() == "text/html").get_content())
        finally:
            _gm.read_thread, _gm.send_message = saved
    s3 = FakeS3(); s3.bucket_exists = True
    with_files(lambda _s: with_mail(go), s3=s3)


@test
def t_a_new_rich_message_and_a_draft_share_the_same_assembly():
    def go():
        ensure_auth(); _gm.save_connection("rt-test", MBOX)
        captured = {}
        async def fake_send(thread_id, to_addr, subject, body_text, in_reply_to="", references="", cc="", new=False, raw_bytes=None):
            captured["send"] = raw_bytes; return {"id": "m3", "thread_id": "t9"}
        async def fake_draft(thread_id, to_addr, subject, body_text, in_reply_to="", references="", cc="", replaces="", raw_bytes=None):
            captured["draft"] = raw_bytes; return {"id": "d1", "thread_id": thread_id}
        async def fake_get(tid, acct=None):
            return {"id": tid, "messages": []}
        saved = (_gm.send_message, _gm.create_draft, _gm.get_thread); _gm.send_message, _gm.create_draft, _gm.get_thread = fake_send, fake_draft, fake_get
        try:
            r = post("/api/mail/send", {"to": "jo@c.test", "bcc": "me@c.test", "subject": "Hello", "html": "<p><i>Hi</i></p>"})
            eq(r.status_code, 200, r.text)
            from email import message_from_bytes
            import email.policy as _epol
            m = message_from_bytes(captured["send"], policy=_epol.default); eq(m["Subject"], "Hello"); eq(m["Bcc"], "me@c.test")
            _seed_thread("t1", subject="x")
            async def fake_read(tid, per_msg_chars=4000):
                return {"id": tid, "messages": [{"id": "m1", "from_name": "Jo", "from_email": "jo@c.test", "reply_to": "", "subject": "x", "message_id": "<a@m>", "references": "", "at": "", "text": "hi", "html": ""}]}
            _gm.read_thread = fake_read
            r = post("/api/mail/draft", {"id": "t1", "op": "save", "html": "<p>Draft <u>here</u></p>"})
            eq(r.status_code, 200, r.text)
            ok(b"<u>here</u>" in captured["draft"], "a draft carries the formatting too")
        finally:
            _gm.send_message, _gm.create_draft, _gm.get_thread = saved
    with_mail(go)


