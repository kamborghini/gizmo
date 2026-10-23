# =========================== run ===========================================

@test
def t_reply_all_offers_everyone_but_us_and_the_person_we_answer():
    def go():
        ensure_auth(); _gm.save_connection("rt-test", MBOX); _seed_thread("t1", subject="x")
        st = mail._load_mail()
        st["threads"]["t1"]["messages"] = [
            {"id": "m0", "from_email": MBOX, "to": "jo@c.test", "cc": "", "text": "hi"},
            {"id": "m1", "from_name": "Jo", "from_email": "jo@c.test", "reply_to": "",
             "to": f"{MBOX}, pat@c.test", "cc": "Sam <sam@c.test>, jo@c.test", "text": "hi"}]
        mail._write_mail(st)
        j = post("/api/mail/thread", {"id": "t1"}).json()
        eq(j["reply_all_cc"], "pat@c.test, sam@c.test")
    with_mail(go)


@test
def t_the_composer_script_is_served_by_hash_like_the_app_script():
    ensure_auth()
    rendering._page_cache = None
    shell, assets = rendering._page_parts()
    ok("composer" in assets, "the composer is one of the hashed assets")
    h = rendering._asset_hashes["composer"]
    ok(f'<script src="/assets/composer.js?v={h}"></script>' in shell, "and the shell loads it")
    ok(shell.index("/assets/app.js?v=") < shell.index("/assets/composer.js?v="), "after app.js")
    r = client.get(f"/assets/composer.js?v={h}")
    eq(r.status_code, 200); ok(b"mountComposer" in r.content)
    eq(client.get("/assets/composer.js?v=wrong").status_code, 404, "a stale or guessed hash gets nothing")


@test
def t_the_bundled_label_reader_is_served_by_hash_and_only_when_asked():
    """The label reader a phone without one of its own needs (the stock app's
    own, @zxing/library 0.20.0, vendored with its licence): a hashed asset like
    the composer, but never loaded up front: the shell only names its URL, and
    the camera loads it when a phone has no reader. Its bytes are the ones the
    vendor note records, so a changed file cannot slip in unnoticed."""
    import hashlib as _hl
    ensure_auth()
    rendering._page_cache = None
    shell, assets = rendering._page_parts()
    ok("reader" in assets, "the reader is one of the hashed assets")
    h = rendering._asset_hashes["reader"]
    ok(f'<meta name="label-reader" content="/assets/reader.js?v={h}">' in shell, "the shell names its URL")
    ok("<script src=\"/assets/reader.js" not in shell, "and does not load it up front")
    r = client.get(f"/assets/reader.js?v={h}")
    eq(r.status_code, 200)
    ok(r.headers["content-type"].startswith("text/javascript"), r.headers["content-type"])
    ok(b"Code39Reader" in r.content)
    note = open(os.path.join(rendering._STATIC_DIR, "vendor", "zxing", "README.md"), encoding="utf-8").read()
    ok(_hl.sha256(r.content).hexdigest() in note, "the bytes are the ones the vendor note records")
    ok(os.path.exists(os.path.join(rendering._STATIC_DIR, "vendor", "zxing", "LICENSE")), "with its licence")
    eq(client.get("/assets/reader.js?v=wrong").status_code, 404, "a stale or guessed hash gets nothing")


@test
def t_an_api_route_nobody_mapped_is_refused_not_allowed():
    """Deny by default. _TAB_ROUTES says who may open what; a route under /api/
    that is on neither that map nor the short open list is refused for
    everyone, so a forgotten mapping fails loudly in testing instead of
    quietly opening a new surface to every account."""
    class Req:
        def __init__(self, path, sess):
            self.url = type("U", (), {"path": path})(); self.headers = {"x-app-session": sess}
    def go():
        ensure_auth()
        uid, sess, _ = ready_user("Ann", "ann")
        post("/api/team/user", {"op": "tabs", "id": uid, "tabs": ["mail"]})
        r = gate._tab_denied(Req("/api/never-mapped/thing", sess))
        ok(r is not None and r.status_code == 403, "unmapped: refused for a member")
        r = gate._tab_denied(Req("/api/never-mapped/thing", APP_AUTH["session"]))
        ok(r is not None and r.status_code == 403, "unmapped: refused for the master too, so it is noticed")
        ok(gate._tab_denied(Req("/api/team/me", sess)) is None, "the open list stays open")
        r = gate._tab_denied(Req("/api/eori/check", sess))
        ok(r is not None and r.status_code == 403, "the EORI checker belongs to the labels tab")
        post("/api/team/user", {"op": "tabs", "id": uid, "tabs": ["mail", "labels"]})
        ok(gate._tab_denied(Req("/api/eori/check", sess)) is None)
    with_mail(go)


@test
def t_an_xml_answer_with_a_doctype_is_refused_before_it_is_parsed():
    import eori
    bomb = ('<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
            '<S:Envelope xmlns:S="http://schemas.xmlsoap.org/soap/envelope/"><S:Body>&b;</S:Body></S:Envelope>')
    r = eori.parse(bomb)
    eq(r["status"], "unknown", "never a verdict")
    ok("could not be read" in r["reason"])


passed = failed = 0


@test
def t_the_first_bytes_name_the_file_not_the_extension():
    eq(fileserver._sniff_kind(b"\x89PNG\r\n\x1a\n...."), "png")
    eq(fileserver._sniff_kind(b"%PDF-1.7 ..."), "pdf")
    eq(fileserver._sniff_kind(b"MZ\x90\x00"), "exe")
    eq(fileserver._sniff_kind(b"\x7fELF"), "elf")
    eq(fileserver._sniff_kind(b"  <!DOCTYPE html><script>"), "html")
    eq(fileserver._sniff_kind(b"#!/bin/sh\n"), "script")
    eq(fileserver._sniff_kind(b"hello"), "")
    ok(not fileserver._file_verdict("report.pdf", "application/pdf", b"MZ\x90")[0], "a program named .pdf")
    ok(not fileserver._file_verdict("invoice.pdf.exe", "application/pdf", b"%PDF-1.4")[0], "the LAST extension is what runs")
    ok(not fileserver._file_verdict("photo.png", "image/png", b"<html><script>")[0], "markup dressed as a picture")
    ok(not fileserver._file_verdict("photo.png", "image/png", b"\xff\xd8\xff")[0], "a JPEG named .png is a lie too")
    okv, _w, safe = fileserver._file_verdict("photo.png", "image/png", b"\x89PNG\r\n\x1a\n")
    ok(okv and safe == "image/png")
    okv, _w, safe = fileserver._file_verdict("page.htm", "text/html", b"<html>")
    ok(okv and safe == "text/plain", "html is stored, but never served as html")
    okv, _w, safe = fileserver._file_verdict("cut-list.csv", "text/csv", b"a,b,c")
    ok(okv and safe == "text/csv")


@test
def t_an_upload_that_is_not_what_it_says_is_refused_and_removed():
    def go():
        ensure_auth()
        r = post("/api/files/upload-url", {"name": "quote.pdf", "size": 100, "type": "application/pdf", "folder": ""})
        eq(r.status_code, 200, r.text)
        d = fileserver._load_files()
        fid, f = next((k, v) for k, v in d["files"].items() if v.get("name") == "quote.pdf")
        s3.objects[f["r2_key"]] = b"MZ\x90\x00" + b"x" * 96
        r = post("/api/files/complete", {"id": fid})
        eq(r.status_code, 400, r.text); ok("program" in r.json()["error"])
        ok(fid not in fileserver._load_files()["files"], "no phantom record")
        ok(f["r2_key"] not in s3.objects, "and the bytes are gone from the bucket")
        eq(post("/api/files/upload-url", {"name": "setup.exe", "size": 10, "type": "application/octet-stream", "folder": ""}).status_code, 400,
           "a program by name never gets a presigned door")
        r = post("/api/files/upload-url", {"name": "proof.png", "size": 20, "type": "image/png", "folder": ""})
        d = fileserver._load_files(); fid2, f2 = next((k, v) for k, v in d["files"].items() if v.get("name") == "proof.png")
        s3.objects[f2["r2_key"]] = b"\x89PNG\r\n\x1a\n" + b"x" * 12
        eq(post("/api/files/complete", {"id": fid2}).status_code, 200)
        eq(fileserver._load_files()["files"][fid2]["sniffed"], "png", "what it is, recorded from its bytes")
    s3 = FakeS3(); s3.bucket_exists = True
    with_files(lambda _fake: go(), s3=s3)


@test
def t_an_email_attachment_is_judged_by_its_bytes_before_it_can_be_sent():
    def go():
        ensure_auth(); _gm.save_connection("rt-test", MBOX)
        uid, sess, _ = ready_user("Ann", "ann"); post("/api/team/user", {"op": "send", "id": uid, "can_send": True})
        eq(post_s(sess, "/api/mail/attach-url", {"name": "run.bat", "size": 10, "type": "text/plain"}).status_code, 400)
        r = post_s(sess, "/api/mail/attach-url", {"name": "quote.pdf", "size": 100, "type": "application/pdf"})
        key = r.json()["key"]; s3.objects[key] = b"<html><script>alert(1)</script>" + b"x" * 70
        r = post_s(sess, "/api/mail/attach-done", {"key": key})
        eq(r.status_code, 400, r.text); ok(key not in s3.objects, "refused bytes are removed")
        r = post_s(sess, "/api/mail/attach-url", {"name": "logo.png", "size": 20, "type": "image/png", "inline": True})
        key = r.json()["key"]; s3.objects[key] = b"%PDF-1.4" + b"x" * 12
        eq(post_s(sess, "/api/mail/attach-done", {"key": key, "inline": True}).status_code, 400, "inline must be a real image")
        r = post_s(sess, "/api/mail/attach-url", {"name": "logo.png", "size": 20, "type": "image/png", "inline": True})
        key = r.json()["key"]; s3.objects[key] = b"\x89PNG\r\n\x1a\n" + b"x" * 12
        eq(post_s(sess, "/api/mail/attach-done", {"key": key, "inline": True}).status_code, 200)
    s3 = FakeS3(); s3.bucket_exists = True
    with_files(lambda _fake: with_mail(go), s3=s3)


@test
def t_sends_are_capped_per_person_and_per_shop():
    def go():
        ensure_auth(); _gm.save_connection("rt-test", MBOX)
        async def fake_send(*a, **k):
            return {"id": "m", "thread_id": "t9"}
        async def fake_get(tid, acct=None):
            return {"id": tid, "messages": []}
        saved = (_gm.send_message, _gm.get_thread, mail.MAIL_SEND_MAX_PER_HOUR)
        _gm.send_message, _gm.get_thread, mail.MAIL_SEND_MAX_PER_HOUR = fake_send, fake_get, 2
        mail._send_hits_user.clear(); mail._send_hits_shop.clear()
        try:
            body = {"to": "jo@c.test", "subject": "x", "html": "<p>hi</p>"}
            eq(post("/api/mail/send", body).status_code, 200)
            eq(post("/api/mail/send", body).status_code, 200)
            r = post("/api/mail/send", body)
            eq(r.status_code, 429, r.text); ok("last hour" in r.json()["error"])
            eq(post("/api/mail/send", dict(body, dry=True)).status_code, 200, "a dry run is not a send")
        finally:
            _gm.send_message, _gm.get_thread, mail.MAIL_SEND_MAX_PER_HOUR = saved
            mail._send_hits_user.clear(); mail._send_hits_shop.clear()
    with_mail(go)


@test
def t_five_wrong_codes_end_the_sign_in():
    ensure_auth()
    uid, sess, pw = ready_user("Ann", "ann")
    import totp as _totp
    secret = _totp.new_secret()
    d = team._load_users(); d["users"][uid]["mfa_secret"] = secret; team._write_users(d)
    r = post("/api/auth/login", {"username": "ann", "password": pw})
    ticket = r.json().get("ticket"); ok(ticket, r.text)
    for _ in range(4):
        eq(post("/api/auth/mfa-verify", {"ticket": ticket, "code": "000000"}).status_code, 401)
    r = post("/api/auth/mfa-verify", {"ticket": ticket, "code": "000000"})
    eq(r.status_code, 401); ok("Too many" in r.json()["error"], r.text)
    good = _totp.code(secret)
    r = post("/api/auth/mfa-verify", {"ticket": ticket, "code": good})
    ok(r.status_code == 401 and "expired" in r.json()["error"], "the ticket is dead even for the right code")




@test
def t_each_label_printer_keeps_its_own_stock_size():
    """Two printers, two stocks: production labels are cut on one, courier
    labels on the other. The sizes live on the server, not in one browser's
    local storage, or every machine at the bench starts on the wrong stock."""
    ensure_auth()
    cfg = post("/api/shipping/config", {"op": "get"}).json()["config"]
    eq(cfg["label_size_production"], "4x4", "the production printer's stock")
    eq(cfg["label_size_shipping"], "4x6", "the courier printer's stock")
    ok("4x4" in cfg["label_stock"] and "4x6" in cfg["label_stock"],
       "and the server publishes the sizes it will accept")
    r = post("/api/shipping/config", {"op": "set", "label_size_production": "4x3",
                                      "label_size_shipping": "4x6"})
    eq(r.status_code, 200, r.text)
    eq(post("/api/shipping/config", {"op": "get"}).json()["config"]["label_size_production"], "4x3")
    r = post("/api/shipping/config", {"op": "set", "label_size_production": "5x5"})
    eq(r.status_code, 400, "a stock size the app cannot print is refused, not stored")
    eq(post("/api/shipping/config", {"op": "get"}).json()["config"]["label_size_production"], "4x3",
       "and the refusal leaves the working size alone")
    _uid, sess, _ = ready_user("Lee", "lee-labels")
    eq(post_s(sess, "/api/shipping/config", {"op": "set", "label_size_shipping": "4x4"}).status_code, 403,
       "changing what the bench prints on is an admin act")




@test
def t_the_password_register_is_as_private_as_the_tokens_beside_it():
    """The users register holds the scrypt password hashes, the TOTP secrets
    and the recovery-code hashes; the session store holds live sessions. Both
    were written with whatever the container umask gives while the recon store
    and every token file next to them were owner-only."""
    import stat
    ensure_auth()
    team._write_users(team._load_users())
    team._write_sessions(team._load_sessions())
    for path, what in ((team.USERS_PATH, "the users register"),
                       (team.SESSIONS_PATH, "the session store")):
        mode = stat.S_IMODE(os.stat(path).st_mode)
        eq(mode & 0o077, 0, "%s is owner-only: %o" % (what, mode))


@test
def t_the_drive_door_does_not_answer_whether_a_username_exists():
    """An unknown username returned before the password was ever hashed while
    a real one paid for scrypt, and that difference answers the question the
    401 refuses to. Since audit R-007 the drive takes its own random password,
    checked with one SHA-256, so it runs scrypt for nobody: known, unknown and
    switched-off accounts all cost the same, and a flood of guesses cannot
    hold the event loop on password hashing (chain R-C4). Counted, not timed."""
    import base64
    ensure_auth()
    uid, _sess, _pw = ready_user("Dee", "dee-dav")
    eq(post("/api/team/user", {"op": "tabs", "id": uid, "tabs": ["files"]}).status_code, 200)
    spent, real = [], team._check_pw
    team._check_pw = lambda pw, stored: (spent.append(1), real(pw, stored))[1]
    try:
        def knock(user, password):
            spent.clear()
            webdav._dav_check_auth("Basic " + base64.b64encode(
                (user + ":" + password).encode()).decode())
            return len(spent)
        known = knock("dee-dav", "not-the-password")
        unknown = knock("no-such-person-at-all", "not-the-password")
        eq(known, 0, "a real username runs no scrypt at the drive")
        eq(unknown, known, "and an unknown one costs exactly the same work")
        off = team._load_users()
        off["users"][uid]["active"] = False
        team._write_users(off)
        eq(knock("dee-dav", "not-the-password"), known,
           "so does a real account that has been switched off")
    finally:
        team._check_pw = real




@test
def t_one_order_can_be_checked_by_anyone_and_sent_only_by_an_admin():
    """Testing a connector against real books means sending one order, not the
    whole queue. The check writes nothing, so it is the same act as a review
    and any tab holder may run it; the send writes an invoice into the
    accounts, so it stays an admin's."""
    calls = []
    async def fake(method, path, params=None):
        calls.append((method, path, dict(params or {})))
        return 200, {"order": "#104300", "found": True,
                     "dryRun": bool((params or {}).get("dryRun")),
                     "docs": [{"kind": "invoice", "key": "#104300", "action": "created"}]}
    saved, old_url = xerosync._connector_call, os.environ.get("CONNECTOR_URL", "")
    xerosync._connector_call = fake
    os.environ["CONNECTOR_URL"] = "http://connector.test:8899"
    try:
        ensure_auth()
        uid, sess, _ = ready_user("Ivy", "ivy-conn")
        eq(post("/api/team/user", {"op": "tabs", "id": uid, "tabs": ["connector"]}).status_code, 200)
        r = post_s(sess, "/api/connector", {"op": "reimport", "order": "#104300", "dryRun": True})
        eq(r.status_code, 200, r.text)
        eq(calls[-1][2].get("dryRun"), "1", "the dry run is passed through, not merely implied")
        eq(calls[-1][2].get("order"), "#104300")
        before = len(calls)
        eq(post_s(sess, "/api/connector", {"op": "reimport", "order": "#104300"}).status_code, 403,
           "a member cannot send one either")
        eq(len(calls), before, "and the refusal never troubled the connector")
        r = post("/api/connector", {"op": "reimport", "order": "#104300"})
        eq(r.status_code, 200, r.text)
        ok("dryRun" not in calls[-1][2], "an admin's send is not a dry run")
        eq(post("/api/connector", {"op": "reimport", "order": "   "}).status_code, 400,
           "an order name that is only spaces is refused here, not at the connector")
        eq(len(calls), before + 1, "and that refusal reached nothing either")
    finally:
        xerosync._connector_call = saved
        os.environ["CONNECTOR_URL"] = old_url




def _loan_row(unit_id):
    for r in post("/api/loans", {"op": "board"}).json()["out"]:
        if r["unit"]["id"] == unit_id:
            return r
    return None


@test
def t_a_loan_unit_goes_out_once_and_comes_back():
    """The register has to answer where a projector is. A unit already with
    someone cannot go out again, or the register drifts from the shelf."""
    ensure_auth()
    before = post("/api/loans", {"op": "board"}).json()["counts"]
    r = post("/api/loans", {"op": "unit_save", "name": "Loan 3",
                            "model": "Epson EB-2250U", "serial": "X1234"})
    eq(r.status_code, 200, r.text)
    unit = r.json()["unit"]["id"]
    b = post("/api/loans", {"op": "board"}).json()
    eq(b["counts"]["in"], before["in"] + 1, "a new unit starts on the shelf")
    r = post("/api/loans", {"op": "out", "unit_id": unit,
                            "who_name": "Northlight Studios", "due_at": "2099-01-01"})
    eq(r.status_code, 200, r.text)
    row = _loan_row(unit)
    ok(row, "it is on the out list")
    eq(row["who_name"], "Northlight Studios")
    eq(row["unit"]["name"], "Loan 3")
    ok(row["days_out"] >= 0, "days out are counted from when it left, never typed")
    again = post("/api/loans", {"op": "out", "unit_id": unit, "who_name": "Someone else"})
    eq(again.status_code, 400, "a unit already out cannot be loaned twice")
    eq(post("/api/loans", {"op": "back", "loan_id": row["id"]}).status_code, 200)
    ok(_loan_row(unit) is None, "and booking it back puts it on the shelf")
    eq(post("/api/loans", {"op": "back", "loan_id": row["id"]}).status_code, 400,
       "it cannot come back twice")


@test
def t_a_loan_is_late_by_its_date_and_only_amber_by_its_age():
    """A due date that has passed is late. A loan with no date is not late,
    however old: it goes amber once it is older than the chase threshold, so a
    projector legitimately out for months is not shouted about every day."""
    from datetime import datetime, timezone, timedelta
    ensure_auth()
    u1 = post("/api/loans", {"op": "unit_save", "name": "Past its date"}).json()["unit"]["id"]
    u2 = post("/api/loans", {"op": "unit_save", "name": "Just old"}).json()["unit"]["id"]
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    post("/api/loans", {"op": "out", "unit_id": u1, "who_name": "A", "due_at": yesterday})
    post("/api/loans", {"op": "out", "unit_id": u2, "who_name": "B"})
    d = loans._load_loans()
    for lo in d["loans"].values():
        if lo["unit_id"] == u2:
            lo["out_at"] = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    loans._write_loans(d)
    late, old = _loan_row(u1), _loan_row(u2)
    eq(late["state"], "late", "past its due date")
    eq(old["state"], "due", "no date, but older than the chase threshold")
    ok(old["days_out"] >= 40, "and it says how long: %s" % old["days_out"])
    counts = post("/api/loans", {"op": "board"}).json()["counts"]
    eq(counts["late"], 1, "only a real due date makes something late")


@test
def t_the_bench_lends_and_receives_but_only_an_admin_keeps_the_register():
    """Loaning out and booking back is the daily job. The register of what the
    shop owns is an admin's, and a unit with a customer cannot be retired from
    under them."""
    ensure_auth()
    uid, sess, _ = ready_user("Kit", "kit-loans")
    eq(post("/api/team/user", {"op": "tabs", "id": uid, "tabs": ["loans"]}).status_code, 200)
    unit = post("/api/loans", {"op": "unit_save", "name": "Bench unit"}).json()["unit"]["id"]
    r = post_s(sess, "/api/loans", {"op": "out", "unit_id": unit, "who_name": "Harbour AV"})
    eq(r.status_code, 200, r.text)
    row = _loan_row(unit)
    eq(post("/api/loans", {"op": "unit_retire", "unit_id": unit}).status_code, 400,
       "a unit that is out cannot be retired")
    eq(post_s(sess, "/api/loans", {"op": "back", "loan_id": row["id"]}).status_code, 200)
    eq(post_s(sess, "/api/loans", {"op": "unit_save", "name": "Sneaky"}).status_code, 403,
       "a member does not add to the register")
    eq(post_s(sess, "/api/loans", {"op": "unit_retire", "unit_id": unit}).status_code, 403)
    eq(post("/api/loans", {"op": "unit_retire", "unit_id": unit}).status_code, 200,
       "but an admin retires it once it is home")




@test
def t_a_unit_can_be_deleted_outright_and_takes_only_its_own_history():
    """Retiring keeps a unit in the history; deleting is the other thing the
    register needs, and it has to be the whole thing. What it must NOT do is
    reach past the unit it was given: one delete that emptied the loan book
    would lose where every other projector went."""
    ensure_auth()
    uid, sess, _ = ready_user("Del", "del-loans")
    eq(post("/api/team/user", {"op": "tabs", "id": uid, "tabs": ["loans"]}).status_code, 200)
    doomed = post("/api/loans", {"op": "unit_save", "name": "Doomed unit"}).json()["unit"]["id"]
    keeper_u = post("/api/loans", {"op": "unit_save", "name": "Keeper unit"}).json()["unit"]["id"]
    # Both have been out, so both have history to lose.
    eq(post("/api/loans", {"op": "out", "unit_id": doomed, "who_name": "Harbour AV"}).status_code, 200)
    eq(post("/api/loans", {"op": "back",
                           "loan_id": _loan_row(doomed)["id"]}).status_code, 200)
    eq(post("/api/loans", {"op": "out", "unit_id": keeper_u, "who_name": "Northlight"}).status_code, 200)
    eq(len(post("/api/loans", {"op": "history", "unit_id": doomed}).json()["history"]), 1)

    eq(post_s(sess, "/api/loans", {"op": "unit_delete", "unit_id": doomed}).status_code, 403,
       "a member does not delete from the register")
    eq(post("/api/loans", {"op": "unit_delete", "unit_id": "u-nope"}).status_code, 404)

    r = post("/api/loans", {"op": "unit_delete", "unit_id": doomed})
    eq(r.status_code, 200, r.text)
    eq(r.json()["loans_removed"], 1, "its own loan row went with it")

    board = post("/api/loans", {"op": "board"}).json()
    ok(all(u["id"] != doomed for u in board["units"]), "the unit is off the register")
    ok(any(u["id"] == keeper_u for u in board["units"]), "the other one is untouched")
    eq(len(post("/api/loans", {"op": "history", "unit_id": doomed}).json()["history"]), 0,
       "and its history went with it")
    eq(len(post("/api/loans", {"op": "history", "unit_id": keeper_u}).json()["history"]), 1,
       "while the OTHER unit still knows where it went")
    ok(any(r["unit"]["id"] == keeper_u for r in board["out"]),
       "the loan that was open on the other unit is still open")


@test
def t_deleting_a_unit_that_is_out_is_allowed_but_leaves_a_line_saying_so():
    """Blocking the delete would be us deciding for the person holding the
    paperwork. Letting it go silently would lose the only record that a
    projector is at a customer. So it goes, and the ledger says where it was."""
    ensure_auth()
    unit = post("/api/loans", {"op": "unit_save", "name": "Out and gone"}).json()["unit"]["id"]
    eq(post("/api/loans", {"op": "out", "unit_id": unit,
                           "who_name": "Cathedral Lighting"}).status_code, 200)
    eq(post("/api/loans", {"op": "unit_delete", "unit_id": unit}).status_code, 200,
       "a unit with a customer can still be deleted")
    board = post("/api/loans", {"op": "board"}).json()
    ok(all(r["unit"]["id"] != unit for r in board["out"]), "and it leaves the out list")
    line = next((e for e in reversed(activity._load_events())
                 if e.get("area") == "loans" and "deleted" in e.get("action", "")), None)
    ok(line is not None, "the delete is on the ledger")
    ok("Out and gone" in line["detail"], "with the name of what went")
    ok("Cathedral Lighting" in line["detail"],
       "and who was holding it, which is the part the register can no longer answer")


@test
def t_a_connector_url_with_no_hostname_is_named_as_the_config_fault_it_is():
    """Railway resolves a ${{service.VARIABLE}} reference to an EMPTY STRING
    when it cannot find that service, so a mistyped service name arrives as
    "http://:8899". httpx calls that UnsupportedProtocol, which names the
    symptom and buries the cause; it is a configuration fault and says so."""
    ensure_auth()
    real = xerosync._connector_call
    called = []
    async def fake(method, path, params=None):
        called.append(path)
        return 200, {"ok": True}
    xerosync._connector_call = fake
    old_url = os.environ.get("CONNECTOR_URL")
    try:
        for bad in ("http://:8899", "http://", "https://:443"):
            os.environ["CONNECTOR_URL"] = bad
            r = post("/api/connector", {"op": "status"})
            eq(r.status_code, 502, bad + " -> " + r.text)
            msg = r.json()["error"]
            ok("no hostname" in msg, "it names the fault: " + msg)
            ok("Private Networking" in msg, "and where to get the right value: " + msg)
        eq(called, [], "and it never dials a URL it knows is malformed")
        # A good URL still goes through: the guard must not swallow the tab.
        os.environ["CONNECTOR_URL"] = "http://xero-conn.railway.internal:8899"
        eq(post("/api/connector", {"op": "status"}).json().get("available"), True)
        ok(called, "a well-formed URL is actually called")
    finally:
        xerosync._connector_call = real
        if old_url is None:
            os.environ.pop("CONNECTOR_URL", None)
        else:
            os.environ["CONNECTOR_URL"] = old_url


@test
def t_an_unreachable_connector_says_which_of_the_three_faults_it_is():
    """One sentence covered a name that does not resolve, a name that does with
    nothing behind it, and a service too slow to answer - three faults with
    three different fixes, and the detail went only to a log the person reading
    the tab cannot see. It names the host it tried and what went wrong."""
    import httpx as _hx
    ensure_auth()
    real = xerosync._connector_call
    old_url = os.environ.get("CONNECTOR_URL")
    os.environ["CONNECTOR_URL"] = "http://xero-conn.railway.internal:8899"
    cases = [
        (_hx.ConnectError("[Errno -2] Name or service not known"),
         ["does not resolve", "service name"]),
        (_hx.ConnectError("All connection attempts failed"),
         ["nothing is listening", "IPv6", "listen on every address"]),
        (_hx.ConnectTimeout("timed out"),
         ["did not reply in time"]),
    ]
    try:
        for err, wants in cases:
            async def fake(method, path, params=None, _e=err):
                raise _e
            xerosync._connector_call = fake
            r = post("/api/connector", {"op": "status"})
            eq(r.status_code, 502, r.text)
            msg = r.json()["error"]
            ok("xero-conn.railway.internal:8899" in msg,
               "it names the host it actually tried: " + msg)
            for w in wants:
                ok(w in msg, "expected " + repr(w) + " in: " + msg)
        # The three readings must be distinguishable, not one text three times.
        outs = []
        for err, _w in cases:
            async def fake(method, path, params=None, _e=err):
                raise _e
            xerosync._connector_call = fake
            outs.append(post("/api/connector", {"op": "status"}).json()["error"])
        eq(len(set(outs)), 3, "each fault reads differently")
    finally:
        xerosync._connector_call = real
        if old_url is None:
            os.environ.pop("CONNECTOR_URL", None)
        else:
            os.environ["CONNECTOR_URL"] = old_url


@test
def t_payout_notes_are_looked_at_by_anyone_and_written_by_an_admin():
    """A dry run lists the notes and writes nothing, so anyone holding the tab
    may look. Writing them puts text onto documents that are already in the
    accounts - harmless text, but on real records - so that stays an admin's."""
    ensure_auth()
    uid, sess, _ = ready_user("Pat", "pat-payouts")
    eq(post("/api/team/user", {"op": "tabs", "id": uid,
                               "tabs": ["connector"]}).status_code, 200)
    seen = []
    real = xerosync._connector_call
    async def fake(method, path, params=None):
        seen.append((method, path, dict(params or {})))
        return 200, {"annotated": 0, "dryRun": True, "notes": []}
    xerosync._connector_call = fake
    old_url = os.environ.get("CONNECTOR_URL")
    os.environ["CONNECTOR_URL"] = "http://conn.railway.internal:8899"
    try:
        r = post_s(sess, "/api/connector", {"op": "payouts", "dryRun": 1,
                                            "since": "2026-08-01"})
        eq(r.status_code, 200, r.text)
        eq(seen[-1][1], "/api/payouts")
        eq(seen[-1][2].get("dryRun"), "1", "a member's look is a DRY RUN")
        eq(seen[-1][2].get("since"), "2026-08-01")

        n = len(seen)
        eq(post_s(sess, "/api/connector", {"op": "payouts"}).status_code, 403,
           "a member cannot write notes onto invoices")
        eq(len(seen), n, "and the refusal never reaches the connector")

        eq(post("/api/connector", {"op": "payouts"}).status_code, 200,
           "an admin can")
        ok("dryRun" not in seen[-1][2], "and that one is a real write")

        bad = post("/api/connector", {"op": "payouts", "since": "last August"})
        eq(bad.status_code, 400, "a date that is not a date is refused here")
    finally:
        xerosync._connector_call = real
        if old_url is None:
            os.environ.pop("CONNECTOR_URL", None)
        else:
            os.environ["CONNECTOR_URL"] = old_url


@test
def t_auto_run_is_off_by_default_and_only_an_admin_moves_it():
    """The automation writes into the accounts unattended, so turning it on is
    a deliberate act by someone who could have sent the batch by hand."""
    ensure_auth()
    uid, sess, _ = ready_user("Ada", "ada-autorun")
    eq(post("/api/team/user", {"op": "tabs", "id": uid, "tabs": ["connector"]}).status_code, 200)
    seen = []
    real = xerosync._connector_call
    async def fake(method, path, params=None):
        seen.append((method, path, dict(params or {})))
        return 200, {"enabled": False, "intervalMinutes": 10, "ticks": 0}
    xerosync._connector_call = fake
    old_url = os.environ.get("CONNECTOR_URL")
    os.environ["CONNECTOR_URL"] = "http://conn.railway.internal:8899"
    try:
        eq(post_s(sess, "/api/connector", {"op": "autorun"}).status_code, 200,
           "anyone with the tab can SEE whether it is on")
        n = len(seen)
        eq(post_s(sess, "/api/connector",
                  {"op": "autorun_set", "enabled": True}).status_code, 403,
           "but only an admin turns it on")
        eq(len(seen), n, "and the refusal never reaches the connector")
        eq(post("/api/connector", {"op": "autorun_set", "enabled": True}).status_code, 200)
        eq(seen[-1][2].get("enabled"), "true")
        eq(post("/api/connector", {"op": "autorun_set", "enabled": False}).status_code, 200)
        eq(seen[-1][2].get("enabled"), "false", "and off again")
    finally:
        xerosync._connector_call = real
        if old_url is None:
            os.environ.pop("CONNECTOR_URL", None)
        else:
            os.environ["CONNECTOR_URL"] = old_url


@test
def t_only_operational_settings_can_be_changed_from_the_page():
    """Saving settings from a browser must not be a pass-through into the
    service's configuration. Reconcile mode and a document cap are operational;
    the shop, the Xero organisation and every credential are not."""
    ensure_auth()
    seen = []
    real = xerosync._connector_call
    async def fake(method, path, params=None, json_body=None):
        seen.append((method, path, dict(json_body or params or {})))
        return 200, {"ok": True}
    xerosync._connector_call = fake
    old_url = os.environ.get("CONNECTOR_URL")
    os.environ["CONNECTOR_URL"] = "http://conn.railway.internal:8899"
    try:
        r = post("/api/connector", {"op": "settings_save", "fields": {
            "RECONCILE_MODE": "strict",
            "XERO_CLIENT_SECRET": "hunter2",
            "SHOPIFY_SHOP": "someone-elses.myshopify.com",
            "DASHBOARD_TOKEN": "nope"}})
        eq(r.status_code, 200, r.text)
        sent = [s for s in seen if s[0] == "POST"][-1][2]
        eq(sent.get("RECONCILE_MODE"), "strict", "the operational one goes through")
        for blocked in ("XERO_CLIENT_SECRET", "SHOPIFY_SHOP", "DASHBOARD_TOKEN"):
            ok(blocked not in sent, blocked + " must not be settable from a browser")
        eq(post("/api/connector", {"op": "settings_save",
                                   "fields": {"DASHBOARD_TOKEN": "x"}}).status_code, 400,
           "a save of nothing settable is refused rather than sent as empty")
    finally:
        xerosync._connector_call = real
        if old_url is None:
            os.environ.pop("CONNECTOR_URL", None)
        else:
            os.environ["CONNECTOR_URL"] = old_url


@test
def t_a_settings_save_reaches_the_connector_as_a_body_of_only_what_changed():
    """Live fault, found 2026-10-12: the Settings card on the Xero sync page
    had never saved anything. The save went as a query string with no body,
    the connector reads POST /api/settings from its body only, so it answered
    ok, kept nothing, and the page said "Saved". The test above swaps
    _connector_call out, so it never saw the wire. This one answers where the
    connector does, at the transport: a body is read, a query string is not.
    What goes is only what the page changed, nothing filled in beside it, and
    a save the settings read straight after do not show is reported, so the
    page cannot say Saved over nothing again."""
    ensure_auth()
    defaults = {"RECONCILE_MODE": "warn", "RECONCILE_TOLERANCE": "0.02", "ORDERS_SINCE": ""}
    saved = {"RECONCILE_MODE": "strict"}
    wire = []
    keeps = {"on": True}
    def connector(request):
        if request.url.host != "conn.railway.internal" or request.url.path != "/api/settings":
            raise _httpx.ConnectError("the test suite does not reach " + request.url.host, request=request)
        if request.method == "GET":
            return _httpx.Response(200, json={
                **{k: saved.get(k) or v for k, v in defaults.items()},
                "sources": {k: "settings" if k in saved else "default" for k in defaults}})
        body = json.loads(request.content) if request.content else {}
        wire.append({"query": dict(request.url.params), "type": request.headers.get("content-type", ""),
                     "csrf": request.headers.get("x-connector"), "body": body})
        if keeps["on"]:
            for k, v in body.items():
                if v == "":
                    saved.pop(k, None)
                else:   # stored in its rule's form, as the connector does: 0.50 is kept as 0.5
                    saved[k] = str(float(v)) if k == "RECONCILE_TOLERANCE" else v
        return _httpx.Response(200, json={"ok": True})
    real_httpx = xerosync.httpx
    xerosync.httpx = _RoutedHttpx(connector)
    old_url = os.environ.get("CONNECTOR_URL")
    os.environ["CONNECTOR_URL"] = "http://conn.railway.internal:8899"
    save = lambda fields: post("/api/connector", {"op": "settings_save", "fields": fields})
    try:
        r = save({"RECONCILE_TOLERANCE": "0.50", "SHOPIFY_SHOP": "someone-elses.myshopify.com"})
        eq(r.status_code, 200, r.text)
        eq(len(wire), 1, "one save, one request")
        eq(wire[0]["query"], {}, "nothing in the query string, which the connector does not read")
        ok("application/json" in wire[0]["type"], "the fields go as a JSON body: " + wire[0]["type"])
        eq(wire[0]["csrf"], "1", "with the connector's CSRF header")
        eq(wire[0]["body"], {"RECONCILE_TOLERANCE": "0.50"},
           "exactly the field the page changed: no other field filled in, and none off the list")
        eq(saved.get("RECONCILE_TOLERANCE"), "0.5", "and the connector kept it")
        eq(r.json().get("unapplied"), [], "kept in its own form (0.5 for 0.50) is still kept")
        eq(saved.get("RECONCILE_MODE"), "strict", "a choice the page did not touch is left alone")

        r = save({"RECONCILE_MODE": ""})
        eq(wire[-1]["body"], {"RECONCILE_MODE": ""}, "a blank goes too: it clears a saved choice")
        ok("RECONCILE_MODE" not in saved and r.json().get("unapplied") == [], r.text)

        keeps["on"] = False   # a connector that answers ok and keeps nothing, as before this fix
        r = save({"ORDERS_SINCE": "2026-09-01", "RECONCILE_TOLERANCE": "0.5"})
        eq(r.json().get("unapplied"), ["ORDERS_SINCE"],
           "a value the connector does not show back is named, so the page does not say Saved")
        saved["RECONCILE_MODE"] = "strict"
        r = save({"RECONCILE_MODE": ""})
        eq(r.json().get("unapplied"), ["RECONCILE_MODE"], "and a clear that left the choice in place is named too")
    finally:
        xerosync.httpx = real_httpx
        if old_url is None:
            os.environ.pop("CONNECTOR_URL", None)
        else:
            os.environ["CONNECTOR_URL"] = old_url


@test
def t_a_run_that_needs_attention_is_reported_once_and_only_once():
    """A quarantined order is silent - not an error anywhere, it simply never
    reaches the accounts. With Auto Run on nobody has a reason to open the tab,
    which is what makes telling them necessary. And telling them about the same
    run every scheduler tick would teach them to filter it."""
    ensure_auth()
    sent = []
    real_call, real_mail = xerosync._connector_call, scheduler._send_alert_email
    async def fake_mail(subject, lines):
        sent.append((subject, list(lines)))
        return True
    health = {"lastRunId": "run-1", "needsAttention": True,
              "line": "8 orders checked, 1 needing attention",
              "problems": ["1 invoice quarantined"], "autoRun": {"enabled": True}}
    async def fake(method, path, params=None):
        return 200, health
    xerosync._connector_call = fake
    scheduler._send_alert_email = fake_mail
    old_url = os.environ.get("CONNECTOR_URL")
    os.environ["CONNECTOR_URL"] = "http://conn.railway.internal:8899"
    st = scheduler._load_watch()
    try:
        _run(scheduler._connector_watch())
        eq(len(sent), 1, "the first tick reports it")
        ok("quarantined" in "\n".join(sent[0][1]), "and says what is wrong")
        ok("Auto Run is ON" in "\n".join(sent[0][1]),
           "and whether anything will retry it")
        _run(scheduler._connector_watch())
        eq(len(sent), 1, "the same run is not reported again")

        health["lastRunId"] = "run-2"
        _run(scheduler._connector_watch())
        eq(len(sent), 2, "but the NEXT bad run is")

        health["needsAttention"] = False
        health["lastRunId"] = "run-3"
        _run(scheduler._connector_watch())
        eq(len(sent), 2, "and a clean run says nothing at all")
        # The banner draws tab_label, metric and pct and reads nothing else.
        # An alert built from other keys renders as a dot and a tilde: a row
        # saying something is wrong and refusing to say what.
        a = scheduler._load_alerts()[0]
        for field in ("tab", "tab_label", "metric"):
            ok(a.get(field), "the alert carries " + field + ", or the banner is blank")
        ok("quarantined" in a["metric"], "and the metric says what is actually wrong")
    finally:
        xerosync._connector_call = real_call
        scheduler._send_alert_email = real_mail
        scheduler._save_watch(st)
        if old_url is None:
            os.environ.pop("CONNECTOR_URL", None)
        else:
            os.environ["CONNECTOR_URL"] = old_url


@test
def t_setting_the_key_encrypts_what_is_already_on_the_volume():
    """Turning the key on only affects what is written NEXT. A Xero refresh
    token not due to rotate, or an MFA secret that never rotates, would sit in
    plaintext indefinitely while the key made it look solved - which is worse
    than knowing it is unencrypted, because nobody goes back to check."""
    import tokenvault as _tv
    d = tempfile.mkdtemp(dir=SCRATCH)
    tok = os.path.join(d, "xero_oauth.json")
    with open(tok, "w", encoding="utf-8") as fh:
        json.dump({"refresh_token": "plain-refresh-abc", "tenant": "t1"}, fh)

    old_key = os.environ.get("TOKEN_ENCRYPTION_KEY")
    try:
        # No key: a re-seal must change nothing at all.
        os.environ.pop("TOKEN_ENCRYPTION_KEY", None)
        _tv._key.cache_clear()
        eq(_tv.reseal_file(tok, ("refresh_token",)), 0)
        eq(json.load(open(tok))["refresh_token"], "plain-refresh-abc",
           "without a key the file is left exactly as it was")

        os.environ["TOKEN_ENCRYPTION_KEY"] = "a-long-random-key-for-the-test"
        _tv._key.cache_clear()
        eq(_tv.reseal_file(tok, ("refresh_token",)), 1, "one secret sealed")
        raw = json.load(open(tok))
        ok(_tv.is_sealed(raw["refresh_token"]), "the file now holds an envelope")
        ok("plain-refresh-abc" not in open(tok).read(),
           "and the plaintext is GONE from the file, not merely alongside it")
        eq(_tv.unseal(raw["refresh_token"]), "plain-refresh-abc",
           "and it still opens to the same token")
        eq(raw["tenant"], "t1", "other fields are untouched")
        eq(oct(os.stat(tok).st_mode & 0o777), oct(0o600), "and it stays private")

        eq(_tv.reseal_file(tok, ("refresh_token",)), 0,
           "running again seals nothing: safe on every boot")
    finally:
        if old_key is None:
            os.environ.pop("TOKEN_ENCRYPTION_KEY", None)
        else:
            os.environ["TOKEN_ENCRYPTION_KEY"] = old_key
        _tv._key.cache_clear()


@test
def t_a_reseal_never_destroys_a_secret_it_cannot_handle():
    """This pass rewrites files holding the only copy of a credential. Every
    way it can fail must leave the file alone: a missing file, a corrupt one,
    an empty value. Losing a refresh token means reconnecting Xero by hand."""
    import tokenvault as _tv
    d = tempfile.mkdtemp(dir=SCRATCH)
    old_key = os.environ.get("TOKEN_ENCRYPTION_KEY")
    os.environ["TOKEN_ENCRYPTION_KEY"] = "a-long-random-key-for-the-test"
    _tv._key.cache_clear()
    try:
        eq(_tv.reseal_file(os.path.join(d, "nope.json"), ("refresh_token",)), 0,
           "a missing file is not an error")

        bad = os.path.join(d, "bad.json")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write("{not json at all")
        eq(_tv.reseal_file(bad, ("refresh_token",)), 0)
        eq(open(bad).read(), "{not json at all",
           "an unreadable file is left exactly as found, never replaced")

        empty = os.path.join(d, "empty.json")
        with open(empty, "w", encoding="utf-8") as fh:
            json.dump({"refresh_token": ""}, fh)
        eq(_tv.reseal_file(empty, ("refresh_token",)), 0,
           "an empty value is not sealed into something that looks like a token")

        # The shape the app WRITES (_write_users wraps the register under
        # users_store). The fixture used to be the bare register, which the
        # function read happily and production never produced: it passed
        # while the boot re-seal sealed nothing on the live volume.
        users = os.path.join(d, "users.json")
        with open(users, "w", encoding="utf-8") as fh:
            json.dump({"users_store": {"version": 2, "users": {
                "u1": {"mfa_secret": "SECRETA", "name": "Ada"},
                "u2": {"name": "Bo"},
                "u3": "not-a-record"}}}, fh)
        eq(_tv.reseal_users(users, ("mfa_secret", "mfa_pending")), 1)
        back = json.load(open(users))["users_store"]
        eq(_tv.unseal(back["users"]["u1"]["mfa_secret"]), "SECRETA",
           "the secret still opens, so nobody is locked out of their account")
        eq(back["users"]["u1"]["name"], "Ada")
        eq(back["users"]["u2"], {"name": "Bo"}, "a user with no secret is untouched")
        eq(back["users"]["u3"], "not-a-record", "and a record of the wrong shape survives")
    finally:
        if old_key is None:
            os.environ.pop("TOKEN_ENCRYPTION_KEY", None)
        else:
            os.environ["TOKEN_ENCRYPTION_KEY"] = old_key
        _tv._key.cache_clear()


@test
def t_the_app_can_say_whether_its_secrets_are_encrypted():
    """Every connection behaves identically whether or not its token is
    encrypted, so this is the one thing about the volume nobody can infer from
    something else working. Read from the FILES: a key that is set while a
    token still sits in plaintext looks fine from the environment alone, and
    that is exactly the failure worth catching."""
    import tokenvault as _tv
    d = tempfile.mkdtemp(dir=SCRATCH)
    tok = os.path.join(d, "gmail_oauth.json")
    old_key = os.environ.get("TOKEN_ENCRYPTION_KEY")
    import google_mail as _gmv
    old_path = _gmv.TOKEN_PATH
    try:
        _gmv.TOKEN_PATH = tok
        with open(tok, "w", encoding="utf-8") as fh:
            json.dump({"refresh_token": "plain-abc"}, fh)

        os.environ.pop("TOKEN_ENCRYPTION_KEY", None)
        _tv._key.cache_clear()
        st = appstatus.token_vault_state()
        eq(st["enabled"], False)
        ok("Gmail, sales" in st["plaintext"], "it names what is exposed, not just a count")

        # A key set is NOT the same as the files being encrypted.
        os.environ["TOKEN_ENCRYPTION_KEY"] = "a-long-random-key-for-the-test"
        _tv._key.cache_clear()
        st = appstatus.token_vault_state()
        eq(st["enabled"], True, "the key is set")
        ok("Gmail, sales" in st["plaintext"],
           "but the file is still plaintext, and saying otherwise would be the lie")

        eq(_tv.reseal_file(tok, ("refresh_token",)), 1)
        st = appstatus.token_vault_state()
        # Scoped to the store this test owns: the suite's scratch volume holds
        # other stores from other tests, and asserting the whole list is empty
        # would be asserting something this test never arranged.
        ok("Gmail, sales" not in st["plaintext"], "the sealed one drops off the exposed list")
        ok(st["sealed"] >= 1, "and counts as sealed")
    finally:
        _gmv.TOKEN_PATH = old_path
        if old_key is None:
            os.environ.pop("TOKEN_ENCRYPTION_KEY", None)
        else:
            os.environ["TOKEN_ENCRYPTION_KEY"] = old_key
        _tv._key.cache_clear()


@test
def t_the_audit_ledger_cannot_be_flushed_through_the_login_form():
    """The ledger is a fixed-size FIFO of 8000 rows. Failed sign-ins for an
    account that EXISTS were written one row per attempt with no coalescing,
    and the paused and switched-off branches have no lockout of their own - so
    anyone who knew one username could push every record of who booked a
    courier label or changed team access out of the far end."""
    before = dict(activity._login_noise)
    start = len(activity._load_events())
    try:
        activity._login_noise.update({"hour": "", "count": 0, "logged": 0})
        for _ in range(200):
            activity._track_login_refusal("u-ghost", "account is switched off")
        added = len(activity._load_events()) - start
        ok(added <= activity.LOGIN_NOISE_ROWS + 1,
           "200 attempts wrote %d rows; the budget is %d"
           % (added, activity.LOGIN_NOISE_ROWS + 1))
        ok(added >= 1, "but the first ones ARE recorded, or an attack is invisible")
        rows = activity._load_events()[-added:]
        ok(any("switched off" in str(r.get("detail") or "") for r in rows),
           "and they say why the sign-in was refused")
        ok(any(r.get("sub") == "u-ghost" for r in rows),
           "and which account was being tried")
        # The helper coalescing proves nothing if a route still writes directly.
        # EVERY refusal path must go through it, so none is left unbounded.
        import inspect
        src = copilot_source()
        noise = inspect.getsource(activity._track_login_noise)
        marker = '_track(uid, "auth", "failed login"'
        # Exactly one such write may exist, and it must be the coalescer's own
        # - that one is bounded by the hourly budget. A second is a route
        # writing a row per attempt, which is the whole finding.
        eq(src.count(marker), 1,
           "every refusal path goes through the coalescer, not around it")
        ok(marker in noise, "and the one that remains is the coalescer's")
    finally:
        activity._login_noise.update(before)


@test
def t_five_wrong_passwords_pause_the_account_and_each_lock_lasts_longer():
    """Five, not eight. And serving a lock used to hand the guesser a fresh
    five every quarter of an hour - twenty an hour, indefinitely. Each
    consecutive lock is longer, so the channel closes instead of throttling.
    Somebody who has genuinely forgotten asks for a reset; nobody reaches the
    fourth lock by accident."""
    ensure_auth()
    eq(team.LOGIN_FAIL_LIMIT, 5, "five attempts, as asked")
    uid, sess, pw = ready_user("Lock", "lock-test")
    for i in range(team.LOGIN_FAIL_LIMIT - 1):
        # The per-client ceiling is a different control with its own test; it
        # would otherwise answer 429 before the account ever locks.
        team._login_hits.clear()
        eq(login("lock-test", "wrong-" + str(i)).status_code, 401,
           "attempt %d is refused but does not lock" % (i + 1))
        ok(not (team._load_users()["users"][uid].get("lock_until") or ""),
           "still open after %d" % (i + 1))
    team._login_hits.clear()
    eq(login("lock-test", "wrong-last").status_code, 401)
    u = team._load_users()["users"][uid]
    ok(u.get("lock_until"), "the fifth locks it")
    eq(int(u.get("locks") or 0), 1)

    def lock_minutes(rec):
        from datetime import datetime as _dt, timezone as _tz
        return round((_dt.fromisoformat(rec["lock_until"])
                      - _dt.now(_tz.utc)).total_seconds() / 60)

    first = lock_minutes(u)
    ok(abs(first - team.LOGIN_LOCK_STEPS[0]) <= 1,
       "the first lock is %d minutes" % team.LOGIN_LOCK_STEPS[0])

    # Serve the lock, then fail five more: the second lock must be longer.
    d = team._load_users()
    d["users"][uid]["lock_until"] = ""
    team._write_users(d)
    for i in range(team.LOGIN_FAIL_LIMIT):
        team._login_hits.clear()
        login("lock-test", "again-" + str(i))
    u2 = team._load_users()["users"][uid]
    second = lock_minutes(u2)
    ok(second > first,
       "the second lock (%d min) must outlast the first (%d min), or serving one "
       "just buys another five attempts" % (second, first))
    eq(int(u2.get("locks") or 0), 2)

    # Getting in clears the run of locks.
    d = team._load_users()
    d["users"][uid]["lock_until"] = ""
    team._write_users(d)
    team._login_hits.clear()
    eq(login("lock-test", pw).status_code, 200, "the right password still works")
    u3 = team._load_users()["users"][uid]
    eq(int(u3.get("locks") or 0), 0,
       "and proving who you are ends the escalation, so one bad afternoon does "
       "not make every later mistake cost four hours")


@test
def t_the_sign_in_form_has_a_tighter_ceiling_than_the_rest_of_the_app():
    """The per-account lockout does nothing against one password sprayed
    across many usernames. The app-wide limit is 120 a minute, which is right
    for a page listing orders and far too wide for one checking passwords."""
    ok(team.LOGIN_MAX_PER_MIN < gate.RATE_MAX_CLIENT,
       "the sign-in ceiling is tighter than the app's")
    team._login_hits.clear()
    codes = [login("nobody-at-all", "x").status_code
             for _ in range(team.LOGIN_MAX_PER_MIN + 3)]
    ok(429 in codes, "spraying usernames is stopped by the client ceiling")
    eq(codes.count(429), 3, "and it stops exactly at the limit")
    team._login_hits.clear()


@test
def t_an_ordinary_filename_is_not_treated_as_macos_junk():
    """A "junk" file is invisible in the Files tab, absent from the ledger,
    exempt from the 30-day trash, and DESTROYED thirty days after it was saved.
    The pattern matched any name starting with an underscore, so a real working
    file saved from Finder had all four of those properties by accident."""
    for real in ("_JOB4471-final.eps", "_notes.txt", "_2026 pricing.xlsx",
                 "Quote 4471.pdf", ".hidden-but-mine.txt"):
        ok(not webdav._DAV_JUNK.match(real), real + " is somebody's work, not junk")
    for junk in ("._sidecar", ".DS_Store", "desktop.ini", "Thumbs.db", ".Trashes"):
        ok(webdav._DAV_JUNK.match(junk), junk + " really is a sidecar")


@test
def t_files_wrongly_marked_as_junk_are_rescued_before_the_reaper_gets_them():
    """Correcting the pattern only helps files saved afterwards. A record
    already marked hidden stays hidden and stays on course to be deleted with
    no trash copy, so the records have to be corrected too."""
    d = fileserver._load_files()
    d["files"]["f-rescue-1"] = {"name": "_JOB4471-final.eps", "hidden": True,
                                "status": "active", "uploaded_at": "2020-01-01T00:00:00+00:00"}
    d["files"]["f-rescue-2"] = {"name": "._sidecar", "hidden": True,
                                "status": "active", "uploaded_at": "2020-01-01T00:00:00+00:00"}
    fileserver._write_files(d)
    try:
        out = fileserver.rescue_misfiled_junk()
        ok(out["rescued"] >= 1, "it rescued something")
        d2 = fileserver._load_files()
        eq(d2["files"]["f-rescue-1"].get("hidden"), False,
           "a real file is visible again, and out of the reaper's path")
        eq(d2["files"]["f-rescue-2"].get("hidden"), True,
           "a genuine sidecar stays hidden")
        eq(fileserver.rescue_misfiled_junk()["rescued"], 0, "and running again does nothing")
    finally:
        d3 = fileserver._load_files()
        d3["files"].pop("f-rescue-1", None)
        d3["files"].pop("f-rescue-2", None)
        fileserver._write_files(d3)


@test
def t_the_name_an_attachment_is_SENT_under_gets_the_same_gate_as_the_upload():
    """The program-extension check ran when the file was uploaded, and the name
    that actually goes out was then re-read from the send request. A file
    accepted as notes.txt could leave as invoice.hta - from the shop's own
    address, with its SPF and DKIM behind it."""
    import inspect
    src = inspect.getsource(mail._mail_fetch_parts)
    ok("_DANGEROUS_EXT" in src,
       "the outgoing name is checked, not only the uploaded one")
    ok("_file_ext(nm)" in src, "by its extension")
    ok("asyncio.to_thread(fileserver._files_head, key)" in src
       and src.index("_files_head") < src.index('"get_object"'),
       "and the object is measured before it is read (off the event loop since 2026-10-12)")


@test
def t_an_oversized_attachment_is_refused_before_its_bytes_are_read():
    """Files holds objects up to 4GB and any active one is attachable. Reading
    first and measuring after put the whole object in memory to discover it was
    too big - on a single worker, which takes dispatch, labels and the CRM down
    with the inbox. Source ORDER is not the property; not fetching is."""
    calls = {"head": 0, "get": 0}
    real = (fileserver._files_head, mail._mail_attachment_ok, fileserver._files_s3)

    def fake_head(key):
        calls["head"] += 1
        return 900 * 1024 * 1024

    class _S3:
        def get_object(self, **kw):
            calls["get"] += 1
            raise AssertionError("the bytes must never be fetched")

    fileserver._files_head = fake_head
    mail._mail_attachment_ok = lambda k, u: True
    fileserver._files_s3 = lambda: _S3()
    try:
        raised = ""
        try:
            _run(mail._mail_fetch_parts([{"key": "mail/u1/0123456789abcdef-big.pdf",
                                             "name": "big.pdf"}], "u1"))
        except ValueError as e:
            raised = str(e)
        ok(raised, "a 900MB attachment is refused")
        eq(calls["get"], 0, "and refused WITHOUT pulling it into memory")
        ok(calls["head"] >= 1, "having been measured first")
    finally:
        fileserver._files_head, mail._mail_attachment_ok, fileserver._files_s3 = real


@test
def t_a_mime_type_from_the_browser_cannot_carry_a_newline():
    """It reaches an email header. A carriage return in it raised inside
    build_message - which runs AFTER the thread is stamped send_pending - so
    the request 500'd and the board said a message may have gone out to a
    customer, forever, with nothing to clear it but checking Gmail by hand."""
    keep = ["image/png", "application/pdf", "application/vnd.ms-excel"]
    for good in keep:
        eq(mail._mail_part_type(good, "application/octet-stream"), good)
    for bad in ["image/png\r\nBcc: evil@x.com", "image/png\nX: 1", "", None,
                "../etc", "text/plain; charset=utf8", "image", "a" * 200 + "/b"]:
        eq(mail._mail_part_type(bad, "application/octet-stream"),
           "application/octet-stream", repr(bad) + " must not reach a header")


@test
def t_the_register_finds_a_projector_in_the_shop():
    """Adding a unit should not mean retyping what the shop already knows.
    Variants are listed separately, because the SKU is what tells two
    otherwise identical projectors apart."""
    catalogue = {"products": [
        {"id": 11, "title": "Optoma UHD38 Projector", "status": "active", "vendor": "Optoma",
         "variants": [{"id": 111, "title": "Default Title", "sku": "OPT-UHD38"}]},
        {"id": 12, "title": "Epson EB-2250U", "status": "active", "vendor": "Epson",
         "variants": [{"id": 121, "title": "White", "sku": "EPS-2250-W"},
                      {"id": 122, "title": "Black", "sku": "EPS-2250-B"}]},
        {"id": 13, "title": "Glass gobo 37.5mm", "status": "active", "vendor": "Projected Image",
         "variants": [{"id": 131, "title": "Default Title", "sku": "GOBO-375"}]}]}
    hits, saved = [], shopify._tool_json
    async def fake(registry, name, args):
        if name == "shopify_list_products":
            hits.append(args)
            return catalogue
        return await saved(registry, name, args)
    shopify._tool_json = fake
    loans._loan_products.update({"at": 0.0, "rows": []})
    try:
        ensure_auth()
        r = post("/api/loans", {"op": "products", "q": "epson"})
        eq(r.status_code, 200, r.text)
        rows = r.json()["products"]
        eq(len(rows), 2, "both variants, because a SKU is what tells them apart")
        eq(rows[0]["title"], "Epson EB-2250U \u00b7 White")
        eq(rows[0]["sku"], "EPS-2250-W")
        eq(rows[0]["product_id"], "12")
        eq(rows[0]["variant_id"], "121")
        one = post("/api/loans", {"op": "products", "q": "OPT-UHD38"}).json()["products"]
        eq(len(one), 1, "a SKU finds its own product")
        eq(one[0]["title"], "Optoma UHD38 Projector",
           "and a single-variant product is not dressed up as 'Default Title'")
        eq(len(hits), 1, "the catalogue is read once and kept, not on every keystroke")
        u = post("/api/loans", {"op": "unit_save", "name": "Loan 9",
                                "model": "Epson EB-2250U \u00b7 White", "product_id": "12",
                                "variant_id": "121", "sku": "EPS-2250-W"})
        eq(u.status_code, 200, u.text)
        unit = [x for x in post("/api/loans", {"op": "board"}).json()["units"]
                if x["name"] == "Loan 9"][0]
        eq(unit["sku"], "EPS-2250-W", "the unit remembers what it was picked from")
        eq(unit["product_id"], "12")
    finally:
        shopify._tool_json = saved
        loans._loan_products.update({"at": 0.0, "rows": []})




