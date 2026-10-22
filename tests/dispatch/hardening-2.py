@test
def t_a_units_asset_tag_is_minted_once_and_never_changes():
    """The sticker goes on the metal. A tag that could be changed afterwards,
    or minted twice, would make the register lie about the machine in front of
    you, so minting happens once and everything after it is a reprint."""
    ensure_auth()
    unit = post("/api/loans", {"op": "unit_save", "name": "Tagged one",
                               "model": "Optoma UHD38"}).json()["unit"]["id"]
    first = post("/api/loans", {"op": "sticker", "unit_id": unit})
    eq(first.status_code, 200, first.text)
    tag = first.json()["tag"]
    ok(re.match(r"^PI-[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{6}$", tag), "an asset tag: %s" % tag)
    again = post("/api/loans", {"op": "sticker", "unit_id": unit}).json()
    eq(again["tag"], tag, "asking again reprints the same tag, it does not mint a second")
    post("/api/loans", {"op": "unit_save", "unit_id": unit, "name": "Renamed",
                        "asset_tag": "PI-9999"})
    board = post("/api/loans", {"op": "board"}).json()["units"]
    row = [u for u in board if u["id"] == unit][0]
    eq(row["asset_tag"], tag, "an edit cannot overwrite what is printed on the sticker")
    other = post("/api/loans", {"op": "unit_save", "name": "Second one"}).json()["unit"]["id"]
    eq(post("/api/loans", {"op": "sticker", "unit_id": other}).json()["tag"] == tag, False,
       "and the next unit gets its own")


@test
def t_the_sticker_carries_both_codes_and_they_read_back_as_the_tag():
    """Number, barcode and QR. Generated on the server and handed over as data
    URIs because the app's CSP allows no CDN script: a browser QR library
    could not have run at all."""
    import base64
    ensure_auth()
    unit = post("/api/loans", {"op": "unit_save", "name": "Coded"}).json()["unit"]["id"]
    r = post("/api/loans", {"op": "sticker", "unit_id": unit})
    eq(r.status_code, 200, r.text)
    d = r.json()
    ok(d["qr"].startswith("data:image/png;base64,"), "the QR is a data image")
    ok(d["barcode"].startswith("data:image/svg+xml;base64,"), "so is the barcode")
    svg = base64.b64decode(d["barcode"].split(",", 1)[1]).decode("utf-8", "replace")
    ok(d["tag"] in svg, "the barcode was drawn for this tag, not another")
    png = base64.b64decode(d["qr"].split(",", 1)[1])
    ok(png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 100, "and the QR is real image bytes")
    eq(d["unit"]["name"], "Coded", "the sheet knows which unit it belongs to")


@test
def t_only_an_admin_mints_a_tag_but_anyone_can_reprint_one():
    """Assigning the number is a change to the register: it goes on the metal
    and never comes off, so it is an admin's. Reprinting is not a change at
    all, and the person who finds a peeled label is whoever is holding the
    projector. One rule was doing both jobs and left members unable to print."""
    ensure_auth()
    uid, sess, _ = ready_user("Mo", "mo-sticker")
    eq(post("/api/team/user", {"op": "tabs", "id": uid, "tabs": ["loans"]}).status_code, 200)
    unit = post("/api/loans", {"op": "unit_save", "name": "Members hands off"}).json()["unit"]["id"]
    r = post_s(sess, "/api/loans", {"op": "sticker", "unit_id": unit})
    eq(r.status_code, 403, "minting an asset tag is part of keeping the register")
    ok("admin" in r.json()["error"],
       "and the refusal says who can do it, not just no")
    ok(loans._load_loans()["units"][unit].get("asset_tag") in (None, ""),
       "a refused mint leaves the unit untagged rather than half-tagged")

    minted = post("/api/loans", {"op": "sticker", "unit_id": unit})
    eq(minted.status_code, 200, minted.text)
    tag = minted.json()["tag"]

    again = post_s(sess, "/api/loans", {"op": "sticker", "unit_id": unit})
    eq(again.status_code, 200, "once it has a number, a member can reprint it")
    eq(again.json()["tag"], tag, "and gets the SAME number, never a second one")
    ok(again.json()["qr"] and again.json()["barcode"], "with both codes drawn")
    eq(loans._load_loans()["units"][unit]["asset_tag"], tag,
       "and the reprint changed nothing on the register")




@test
def t_an_asset_tag_is_random_unambiguous_and_never_reissued():
    """A running number told anyone who read a sticker roughly how many units
    the shop owns, and let them guess the next one. Random instead, from an
    alphabet with no character that can be misread on a label or over a phone
    (no O or 0, no I, L or 1), and checked against every tag already minted,
    because two projectors carrying one number is the whole failure."""
    d = {"units": {}, "loans": {}, "seq": 0}
    seen = set()
    for i in range(400):
        tag = loans._loan_mint_tag(d)
        ok(re.match(r"^PI-[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{6}$", tag),
           "shape and alphabet: %s" % tag)
        ok(tag not in seen, "the same tag was minted twice: %s" % tag)
        seen.add(tag)
        d["units"]["u%d" % i] = {"asset_tag": tag}
    ok(len({t[3] for t in seen}) > 8, "and it is actually varied, not a counter in disguise")


@test
def t_a_tag_already_on_a_machine_is_never_handed_out_again():
    """Proved deterministically, not by luck. Drawing 400 tags out of 900
    million and finding no duplicate says nothing about the collision check:
    that assertion passes just as happily with the check deleted, which is
    exactly what it did. With a two-letter alphabet there are only two tags
    to be had, so the third mint HAS to notice both are taken."""
    saved = (loans.LOAN_TAG_ALPHABET, loans.LOAN_TAG_LENGTH)
    loans.LOAN_TAG_ALPHABET, loans.LOAN_TAG_LENGTH = "AB", 1
    try:
        d = {"units": {}, "loans": {}, "seq": 0}
        first = loans._loan_mint_tag(d)
        d["units"]["1"] = {"asset_tag": first}
        second = loans._loan_mint_tag(d)
        d["units"]["2"] = {"asset_tag": second}
        ok(first != second, "the second mint avoided the first: %s then %s" % (first, second))
        eq({first, second}, {"PI-A", "PI-B"}, "which are the only two tags that exist")
        third = loans._loan_mint_tag(d)
        ok(third not in (first, second), "with both taken it still does not repeat one")
        eq(len(third), len("PI-") + 3, "it lengthens rather than duplicate: %s" % third)
    finally:
        loans.LOAN_TAG_ALPHABET, loans.LOAN_TAG_LENGTH = saved


@test
def t_a_legacy_alert_record_still_says_what_it_meant():
    """Alerts written before the banner's fields were settled carried kind,
    title and detail. The banner reads tab_label, metric and pct, so those
    records rendered as a dot and a tilde: a row saying something was wrong
    and refusing to say what. They are read as what they meant, at load, so
    every consumer sees the same record."""
    scheduler._write_alerts([
        {"id": "old1", "at": "2026-09-01T00:00:00+00:00", "status": "new",
         "kind": "connector", "title": "Reviewed 21 orders, wrote nothing", "detail": "run aborted"},
        {"id": "old2", "at": "2026-09-01T00:00:00+00:00", "status": "new", "kind": "labels", "detail": "only a detail"},
        {"id": "new1", "at": "2026-09-02T00:00:00+00:00", "status": "new",
         "tab": "seo", "tab_label": "SEO", "metric": "Clicks", "pct": 12},
    ])
    a, b, c = scheduler._load_alerts()
    eq(a["tab"], "connector", "a legacy record's kind becomes its tab")
    eq(a["tab_label"], "Xero sync", "with the label the banner shows for that tab")
    eq(a["metric"], "Reviewed 21 orders, wrote nothing", "and its title becomes the metric")
    eq(b["metric"], "only a detail", "a detail serves when there is no title")
    eq(b["tab_label"], "Labels", "and an unknown kind is still titled rather than blank")
    eq((c["tab_label"], c["metric"], c["pct"]), ("SEO", "Clicks", 12), "a current record is untouched")


@test
def t_turning_off_or_rebinding_the_second_factor_takes_the_password():
    """A session is a token in a browser. Without the password, whoever held
    the token could remove the one factor that exists for exactly that day,
    or bind their own phone in its place."""
    def go():
        ensure_auth()
        import totp
        eq(post("/api/auth/mfa", {"op": "start"}).status_code, 400, "no password, no enrolment")
        eq(post("/api/auth/mfa", {"op": "start", "current": "not-it"}).status_code, 400)
        j = post("/api/auth/mfa", {"op": "start", "current": MASTER_PW}).json()
        ok(j.get("secret"), "the right password starts it")
        post("/api/auth/mfa", {"op": "confirm", "code": totp.code(j["secret"])})
        eq(post("/api/auth/mfa", {"op": "off"}).status_code, 400, "no password, no switching it off")
        eq(post("/api/auth/mfa", {"op": "status"}).json()["enabled"], True, "still on")
        eq(post("/api/auth/mfa", {"op": "off", "current": MASTER_PW}).status_code, 200)
        eq(post("/api/auth/mfa", {"op": "status"}).json()["enabled"], False)
        # Wrong passwords here are wrong passwords: the same counter, the
        # same escalating pause as the login.
        for _ in range(team.LOGIN_FAIL_LIMIT):
            post("/api/auth/mfa", {"op": "start", "current": "wrong-wrong"})
        eq(post("/api/auth/mfa", {"op": "start", "current": MASTER_PW}).status_code, 429, "paused")
        team._login_hits.clear()
        eq(login("cameron", MASTER_PW).status_code, 401, "and the front door is paused with it")
    with_accounts(go)


@test
def t_a_code_from_a_phone_a_step_ahead_cannot_be_replayed():
    """The stored counter is the one the code MATCHED, not the current step.
    Storing the current step let a code from a phone thirty seconds ahead be
    accepted now, and again once the clock had caught up with it."""
    def go():
        ensure_auth()
        import totp, time as _t
        j = post("/api/auth/mfa", {"op": "start", "current": MASTER_PW}).json()
        post("/api/auth/mfa", {"op": "confirm", "code": totp.code(j["secret"])})
        ahead = totp.code(j["secret"], at=_t.time() + 30)
        t1 = login("cameron", MASTER_PW).json()["ticket"]
        eq(bare("/api/auth/mfa-verify", {"ticket": t1, "code": ahead}).status_code, 200,
           "a phone one step ahead is within the skew")
        team._login_hits.clear()
        t2 = login("cameron", MASTER_PW).json()["ticket"]
        eq(bare("/api/auth/mfa-verify", {"ticket": t2, "code": ahead}).status_code, 401,
           "and the same code is spent, not good a second time")
    with_accounts(go)


@test
def t_ten_wrong_second_factor_codes_pause_the_account():
    """A ticket costs one right password and five misses end it, so whoever
    held the password used to get a fresh five per ticket, forever, with a
    ledger row for each. The ACCOUNT counts them now, and pauses on the same
    clock as wrong passwords."""
    def go():
        ensure_auth()
        import totp
        j = post("/api/auth/mfa", {"op": "start", "current": MASTER_PW}).json()
        post("/api/auth/mfa", {"op": "confirm", "code": totp.code(j["secret"])})
        for _ in range(3):
            team._login_hits.clear()
            tick = login("cameron", MASTER_PW).json()["ticket"]
            for _ in range(4):
                bare("/api/auth/mfa-verify", {"ticket": tick, "code": "000000"})
        team._login_hits.clear()
        r = login("cameron", MASTER_PW)
        eq(r.status_code, 401, "twelve misses: paused, and the pause reads like a wrong password")
        ok("do not match" in r.json()["error"], r.text)
        rows = [e for e in activity._load_events() if e.get("action") == "account paused"]
        ok(rows and "second-factor" in rows[-1]["detail"], rows[-1:])
        listed = [e for e in activity._load_events() if "second-factor code" in e.get("detail", "")]
        ok(len(listed) <= activity.LOGIN_NOISE_ROWS, "coalesced, not one row per miss: %d" % len(listed))
    with_accounts(go)


@test
def t_an_admin_can_reset_a_lost_second_factor():
    def go():
        ensure_auth()
        import totp
        owen, sess, pw = ready_user("Owen", "owen")
        j = post_s(sess, "/api/auth/mfa", {"op": "start", "current": pw}).json()
        eq(post_s(sess, "/api/auth/mfa", {"op": "confirm", "code": totp.code(j["secret"])}).status_code, 200)
        team._login_hits.clear()
        eq(login("owen", pw).json().get("mfa"), True, "the password alone is now half a login")
        res = post("/api/team/user", {"op": "reset_mfa", "id": owen})
        eq(res.status_code, 200, res.text)
        eq([u for u in res.json()["users"] if u["id"] == owen][0]["mfa"], False, "the list says it is gone")
        team._login_hits.clear()
        ok(login("owen", pw).json().get("session"), "and the password signs them in again")
        eq(post("/api/team/user", {"op": "reset_mfa", "id": owen}).status_code, 400, "nothing left to reset")
        ian, ian_sess, ian_pw = ready_user("Ian", "ian", role="admin")
        j2 = post_s(ian_sess, "/api/auth/mfa", {"op": "start", "current": ian_pw}).json()
        post_s(ian_sess, "/api/auth/mfa", {"op": "confirm", "code": totp.code(j2["secret"])})
        eq(post_s(sess, "/api/team/user", {"op": "reset_mfa", "id": ian}).status_code, 403,
           "a member cannot reset an admin's")
        eq(post("/api/team/user", {"op": "reset_mfa", "id": ian}).status_code, 200, "the master can")
        ok(any(e.get("action") == "reset a second factor" for e in activity._load_events()), "and it is in the ledger")
    with_accounts(go)


@test
def t_only_an_admin_can_delete_files_for_good():
    """The trash is the undo. Skipping it - destroy, empty the trash - is the
    one file operation with no way back, so it is an admin's call."""
    def go(fake):
        ensure_auth()
        up = post("/api/files/upload-url", {"name": "a.pdf", "size": 10}).json()
        key = up["url"].split("?")[0].replace("https://fake-r2.test/", "")
        fake.objects[key] = 10
        post("/api/files/complete", {"id": up["id"]})
        eq(post("/api/files/file", {"op": "trash", "id": up["id"]}).status_code, 200)
        _owen, sess, _pw = ready_user("Owen", "owen")
        r = post_s(sess, "/api/files/file", {"op": "destroy", "id": up["id"]})
        eq(r.status_code, 403, r.text)
        eq(post_s(sess, "/api/files/file", {"op": "empty_trash"}).status_code, 403, "nor empty the trash")
        eq(post_s(sess, "/api/files/file", {"op": "restore", "id": up["id"]}).status_code, 200,
           "the undo is still theirs")
        eq(post_s(sess, "/api/files/file", {"op": "trash", "id": up["id"]}).status_code, 200)
        eq(post("/api/files/file", {"op": "destroy", "id": up["id"]}).status_code, 200, "an admin's call")
    with_accounts(lambda: with_files(go))


@test
def t_payout_tools_belong_to_the_recon_tab():
    src = open(os.path.join(HERE, "server.py"), encoding="utf-8").read()
    for name in ("shopify_list_payouts", "shopify_payout_transactions", "shopify_list_disputes"):
        ok("def " + name in src, name + " is a tool")
        eq(assistant._TOOL_TABS.get(name), "recon", name + " is the books, so it is gated on the recon tab")


@test
def t_a_session_ends_after_thirty_days_however_active():
    """The sliding window alone let a session used once a day live forever,
    and a stolen one with it."""
    def go():
        ensure_auth()
        import hashlib as _h
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        _owen, sess, _pw = ready_user("Owen", "owen")
        eq(post_s(sess, "/api/team/me", {}).status_code, 200)
        s = team._load_sessions()
        s[_h.sha256(sess.encode()).hexdigest()]["created_at"] = (_dt.now(_tz.utc) - _td(days=31)).isoformat()
        team._write_sessions(s)
        eq(post_s(sess, "/api/team/me", {}).status_code, 401, "a month old: gone, however recently used")
    with_accounts(go)


@test
def t_wrong_drive_passwords_stop_costing_a_hash_after_twenty_a_minute():
    """Every miss at the drive costs one scrypt on the event loop, and the
    drive's ceiling is three hundred a minute for Finder's sake. Twenty misses
    a minute from one client is not Finder."""
    def go():
        ensure_auth()
        import base64 as b64
        webdav._dav_auth_cache.clear(); webdav._dav_fail_cache.clear(); gate._rl_hits.clear()
        calls = {"n": 0}
        real = team._check_pw
        def counting(pw, stored):
            calls["n"] += 1
            return real(pw, stored)
        team._check_pw = counting
        try:
            codes = []
            for i in range(25):
                bad = {"Authorization": "Basic " + b64.b64encode(f"nobody{i}:guess".encode()).decode()}
                codes.append(client.request("PROPFIND", "/dav/", headers={**bad, "Depth": "0"}).status_code)
        finally:
            team._check_pw = real
        eq(codes[:20], [401] * 20, "twenty misses are answered like misses")
        eq(codes[20:], [429] * 5, "the rest are refused before anything is hashed")
        ok(calls["n"] <= 20, "at most one hash per miss, none after: %d" % calls["n"])
        eq(client.request("PROPFIND", "/dav/").status_code, 401,
           "a bare challenge (no credentials yet) is neither counted nor refused")
    with_accounts(go)


@test
def t_a_refused_tab_is_in_the_ledger_a_bounded_number_of_times():
    def go():
        ensure_auth()
        owen, sess, _pw = ready_user("Owen", "owen")
        eq(post("/api/team/user", {"op": "tabs", "id": owen, "tabs": ["labels"]}).status_code, 200)
        activity._deny_noise.update({"hour": "", "logged": 0})
        for _ in range(activity.DENY_NOISE_ROWS + 5):
            eq(post_s(sess, "/api/files/tree", {}).status_code, 403)
        rows = [e for e in activity._load_events() if e.get("action") == "refused a closed tab"]
        eq(len(rows), activity.DENY_NOISE_ROWS, "the first twenty are listed")
        eq(rows[0]["sub"], owen, "naming the account")
        ok(rows[0]["detail"].startswith("/api/files/tree"), rows[0]["detail"])
        more = [e for e in activity._load_events() if e.get("action") == "refusals continuing"]
        eq(len(more), 1, "then one line saying the rest are not listed")
    with_accounts(go)


@test
def t_wrong_current_passwords_escalate_like_the_front_door():
    def go():
        ensure_auth()
        owen, sess, pw = ready_user("Owen", "owen")
        for _ in range(team.LOGIN_FAIL_LIMIT):
            post_s(sess, "/api/auth/password", {"current": "nope-nope-nope", "new": "something-new-12"})
        eq(post_s(sess, "/api/auth/password", {"current": pw, "new": "something-new-12"}).status_code,
           429, "paused")
        team._login_hits.clear()
        eq(login("owen", pw).status_code, 401, "the pause is the account's, so the login is paused too")
        eq(team._load_users()["users"][owen].get("locks"), 1, "and it counts toward the escalation")
        rows = [e for e in activity._load_events() if e.get("action") == "account paused"]
        ok("at the password change" in rows[-1]["detail"], rows[-1]["detail"])
    with_accounts(go)


@test
def t_an_erasure_survives_the_next_pipedrive_import():
    """The privacy log said the person was erased. The importer put them back
    within the hour, because the CRM was only popped, not tombstoned - the
    anti-resurrection list every hand-deletion already used."""
    def go():
        ensure_auth()
        crm_wipe()
        orderbook._webhook_seen.clear()
        async def fake_export(progress=None):
            return dict(PD_EXPORT)
        saved = (pipedrive.export, pipedrive.API_TOKEN)
        pipedrive.export, pipedrive.API_TOKEN = fake_export, "t"
        try:
            eq(post("/api/crm/import", {"go": True}).status_code, 200)
            d = salesdesk._load_crm()
            person = [p for p in d["persons"].values() if p["pd_id"] == "20"][0]
            ok("sarah@lumen.co.uk" in person["emails"], "the imported person is there")
            raw = json.dumps({"customer": {"id": 901, "email": "Sarah@Lumen.co.uk"},
                              "shop_domain": "test-store.myshopify.com"}).encode()
            redact_through_the_hold(raw, "res1")
            gone = salesdesk._load_crm()
            eq(any(p.get("pd_id") == "20" for p in gone["persons"].values()), False, "erased")
            ok("20" in (gone.get("pd_deleted_persons") or []), "and tombstoned as it went")
            eq(post("/api/crm/import", {"go": True}).status_code, 200, "the next import runs")
            after = salesdesk._load_crm()
            eq(any(p.get("pd_id") == "20" for p in after["persons"].values()), False,
               "and does NOT put the erased person back")
        finally:
            pipedrive.export, pipedrive.API_TOKEN = saved
    with_accounts(go)


@test
def t_an_erased_persons_email_is_not_re_imported_by_the_next_sync():
    """Gmail still holds the correspondence and the sync looks two years back,
    so a deleted thread was simply 'not in threads' and came straight back."""
    def go():
        ensure_auth()
        orderbook._webhook_seen.clear()
        store = mail._load_mail()
        store.setdefault("threads", {})["tgone"] = {
            "id": "tgone", "from_email": "erase.me@example.com",
            "subject": "Please delete me", "state": "open"}
        mail._write_mail(store)
        raw = json.dumps({"customer": {"id": 902, "email": "erase.me@example.com"},
                          "shop_domain": "test-store.myshopify.com"}).encode()
        redact_through_the_hold(raw, "res2")
        store = mail._load_mail()
        eq("tgone" in store["threads"], False, "gone")
        ok("erase.me@example.com" in (store.get("redacted") or []), "and remembered as erased")
        # Exactly what the next sync does with what Gmail hands back.
        mail._mail_apply_thread(store, {
            "id": "tgone", "messages": [{"id": "m1", "from_email": "erase.me@example.com",
                                         "from_name": "Erase Me", "subject": "Please delete me",
                                         "date": "2026-09-07T09:00:00Z", "snippet": "hello"}]},
            "sales@example.com")
        eq("tgone" in store["threads"], False, "the sync does not bring them back")
        mail._mail_apply_thread(store, {
            "id": "tstay", "messages": [{"id": "m2", "from_email": "other@example.com",
                                         "from_name": "Other", "subject": "Unrelated",
                                         "date": "2026-09-07T09:00:00Z", "snippet": "hi"}]},
            "sales@example.com")
        eq("tstay" in store["threads"], True, "and nobody else is affected")
        store["redacted"] = []
        mail._write_mail(store)
    with_accounts(go)


@test
def t_the_courier_credentials_are_sealed_like_every_other_credential():
    """The one long-lived credential the vault did not cover, while its own
    docstring said it covered them all. What it holds books shipments."""
    import tokenvault
    os.environ["TOKEN_ENCRYPTION_KEY"] = "a-long-enough-test-key-for-scrypt-0123456789"
    tokenvault._key.cache_clear()
    try:
        desk._save_wo_creds(meter="METER-5555", key="KEY-super-secret", password="PW-very-secret")
        raw = open(desk.WO_SECRET_PATH, encoding="utf-8").read()
        ok("KEY-super-secret" not in raw, "the key is not sitting in the file")
        ok("PW-very-secret" not in raw, "nor the password")
        creds = desk._load_wo_creds()
        eq(creds["key"], "KEY-super-secret", "and it opens again for the courier call")
        eq(creds["password"], "PW-very-secret")
        eq(oct(os.stat(desk.WO_SECRET_PATH).st_mode & 0o777), "0o600", "0600 from creation")
        src = copilot_source()
        ok('("world_options", desk.WO_SECRET_PATH' in src,
           "and the boot re-seal covers it, so an existing plaintext file is fixed")
    finally:
        os.environ.pop("TOKEN_ENCRYPTION_KEY", None)
        tokenvault._key.cache_clear()
        desk._save_wo_creds(meter="METER-9999", key="KEY-abc", password="PW-xyz")


@test
def t_the_drain_scrubs_the_shapes_a_person_actually_writes():
    """A credential reaching a third-party sink is a leak with extra steps.
    Scrubbing the SERIALISED event could also make it invalid JSON, and the
    audit row was then dropped on the floor rather than shipped."""
    import logdrain
    got = []
    logdrain.stop()
    logdrain.install("https://sink.example/ingest", sender=lambda b: got.extend(b))
    try:
        logdrain.audit({"detail": "World Options key: 0123456789abcdef"})
        logdrain.audit({"note": 'password: hunter2hunter2'})
        logdrain.audit({"who": "u1", "action": "booked a shipment", "n": 3, "ok": True})
        logdrain.flush(timeout=3)
        blob = json.dumps(got)
        ok("0123456789abcdef" not in blob, "a key written as a phrase is redacted")
        ok("hunter2hunter2" not in blob, "and so is a password")
        rows = [e for e in got if e.get("action") == "booked a shipment"]
        eq(len(rows), 1, "an ordinary audit row still arrives - scrubbing must not drop it")
        eq(rows[0]["n"], 3, "with its non-string fields intact")
        eq(rows[0]["ok"], True)
    finally:
        logdrain.stop()


@test
def t_the_break_glass_password_never_leaves_the_operators_console():
    """It is logged on purpose so Railway shows it. That is not a reason to
    ship it to a third-party sink as well."""
    import logdrain, logging as _lg
    got = []
    logdrain.stop()
    logdrain.install("https://sink.example/ingest", sender=lambda b: got.extend(b))
    try:
        _lg.getLogger("shopify_mcp.copilot").error(
            "MASTER RESET: temporary password for %s is: %s", "cameron", "Ab3dEf9hIjKl",
            extra={"no_drain": True})
        logdrain.flush(timeout=3)
        ok("Ab3dEf9hIjKl" not in json.dumps(got), "the starter password did not travel")
    finally:
        logdrain.stop()
    src = copilot_source()
    seg = src.split("MASTER RESET: temporary password")[1][:600]
    ok('"no_drain": True' in seg, "and the real call site carries the flag")


@test
def t_a_drain_url_that_is_not_https_is_not_installed():
    """LOG_DRAIN_TOKEN rides in a header on every batch. A typo'd http:// host
    would put it on the wire in the clear, with logs arriving normally."""
    import logdrain
    logdrain.stop()
    eq(logdrain.install("http://sink.example/ingest"), False, "refused")
    eq(logdrain.pending(), 0, "and nothing is queued for it")
    logdrain.stop()


@test
def t_the_orders_webhook_takes_order_topics_only():
    """Shopify counts a 200 as handled. A privacy topic acknowledged by the
    orders door would be a redaction request that quietly never happened."""
    orderbook._webhook_seen.clear()
    raw = json.dumps({"customer": {"id": 1, "email": "x@example.com"}}).encode()
    r = client.post("/webhooks/orders", content=raw,
                    headers=wh_headers(raw, topic="customers/redact", delivery="wrong1"))
    eq(r.status_code, 422, "not 200: Shopify must retry or alert, not tick it off")
    ok(privacy._load_privacy_log() is not None)
    raw2 = json.dumps({"id": 2}).encode()
    eq(client.post("/webhooks/orders", content=raw2,
                   headers=wh_headers(raw2, topic="orders/updated", delivery="right1")
                   ).status_code, 200, "an order topic is still handled")


@test
def t_the_pre_redact_archive_does_not_live_forever():
    """shop/redact archives everything before erasing it, which is the undo for
    an uninstall that was a mistake. Nothing deleted it, so the erasure was met
    by moving the data into a zip and keeping it indefinitely."""
    import time as _t
    data_dir = os.path.dirname(scheduler.SCHEDULE_PATH) or "/data"
    old = os.path.join(data_dir, "pre-redact-backup-20250101000000.zip")
    new = os.path.join(data_dir, "pre-redact-backup-20260907000000.zip")
    for p in (old, new):
        open(p, "wb").write(b"PK\x03\x04")
    os.utime(old, (_t.time() - 40 * 86400, _t.time() - 40 * 86400))
    try:
        eq(privacy._redact_archive_reap(), 1, "one archive was old enough")
        eq(os.path.exists(old), False, "the 40-day-old copy is gone")
        eq(os.path.exists(new), True, "today's is not")
        ok(any(e.get("topic") == "archive/expire"
               for e in privacy._load_privacy_log()["events"]), "and it is evidenced")
    finally:
        for p in (old, new):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass


@test
def t_authenticated_json_is_not_stored_by_any_cache():
    """A shared dispatch PC: the browser's disk and back-forward caches outlive
    the session that fetched the customer list."""
    eq(gate._API_HEADERS.get("Cache-Control"), "no-store")
    r = post("/api/team/me", {})
    eq(r.headers.get("cache-control"), "no-store", "on a real API answer")
    shell = client.get("/", headers={"Authorization": "Bearer " + tok()})
    eq(shell.headers.get("cache-control"), "private, no-cache",
       "but the page shell still revalidates rather than refetching in full")


@test
def t_the_connector_token_only_travels_somewhere_it_is_safe():
    saved = os.environ.get("CONNECTOR_URL"), os.environ.get("CONNECTOR_TOKEN")
    os.environ["CONNECTOR_TOKEN"] = "a-real-token"
    try:
        for url, allowed in (("http://connector.example.com", False),
                             ("https://connector.example.com", True),
                             ("http://gizmo-connector.railway.internal:8080", True),
                             ("http://localhost:8080", True)):
            eq(xerosync._connector_url_safe(url), allowed, url)
        os.environ["CONNECTOR_URL"] = "http://connector.example.com"
        try:
            asyncio.new_event_loop().run_until_complete(
                xerosync._connector_call("GET", "/status"))
            ok(False, "a plain http host should have been refused")
        except RuntimeError as e:
            ok("will not be sent" in str(e), str(e))
    finally:
        for k, v in (("CONNECTOR_URL", saved[0]), ("CONNECTOR_TOKEN", saved[1])):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@test
def t_the_eori_check_does_not_follow_a_redirect():
    """A SOAP endpoint answering 302 has been moved or intercepted. Following
    it posts the envelope somewhere this code has never checked."""
    src = open(os.path.join(HERE, "eori.py"), encoding="utf-8").read()
    ok("follow_redirects=False" in src and "follow_redirects=True" not in src, "pinned")


@test
def t_a_chunked_drive_upload_cannot_spool_past_the_quota():
    """The quota was only checked after the whole body had been written to the
    container's disk. A client that sends no Content-Length could therefore
    fill the disk with bytes that were always going to be refused."""
    def go():
        ensure_auth()
        import base64 as b64
        fake = FakeS3()
        saved = (fileserver.R2_ACCOUNT_ID, fileserver.R2_ACCESS_KEY_ID, fileserver.R2_SECRET_ACCESS_KEY,
                 fileserver._files_s3_client, fileserver.FILES_QUOTA_GB)
        fileserver.R2_ACCOUNT_ID = fileserver.R2_ACCESS_KEY_ID = fileserver.R2_SECRET_ACCESS_KEY = "acct"
        fileserver._files_s3_client = fake
        fileserver.FILES_QUOTA_GB = 4 / (1024 * 1024 * 1024)      # four bytes of room
        fileserver._files_mem = None
        webdav._dav_auth_cache.clear(); webdav._dav_fail_cache.clear()
        try:
            os.remove(fileserver.FILES_PATH)
        except FileNotFoundError:
            pass
        # What reaches the CONTAINER'S DISK is the thing at issue, and the test
        # client buffers the request body before it sends it - so count the
        # bytes the server spools, not the bytes the client produced.
        import tempfile as _tf
        spooled = {"n": 0}
        real_tmp = _tf.TemporaryFile
        class Counting:
            def __init__(self, *a, **k):
                self._f = real_tmp(*a, **k)
            def write(self, b):
                spooled["n"] += len(b)
                return self._f.write(b)
            def __getattr__(self, name):
                return getattr(self._f, name)
        def body():
            for _ in range(200):
                yield b"x" * 1024
        _tf.TemporaryFile = Counting
        try:
            _pt, starter = make_user("Pat", "pat")
            sess = login("pat", starter).json()["session"]
            post_s(sess, "/api/auth/password", {"current": starter, "new": "pats-own-pw-91"})
            sess = login("pat", "pats-own-pw-91").json()["session"]
            auth = {"Authorization": "Basic " + b64.b64encode(("pat:" + drive_pw(sess)).encode()).decode()}
            r = client.put("/dav/big.pdf", headers=auth, content=body())
            eq(r.status_code, 507, "refused for space, not accepted and then refused")
            ok(spooled["n"] <= 16 * 1024,
               "and it stopped writing to disk early: %d bytes spooled" % spooled["n"])
        finally:
            _tf.TemporaryFile = real_tmp
            (fileserver.R2_ACCOUNT_ID, fileserver.R2_ACCESS_KEY_ID, fileserver.R2_SECRET_ACCESS_KEY,
             fileserver._files_s3_client, fileserver.FILES_QUOTA_GB) = saved
            fileserver._files_mem = None
            webdav._dav_auth_cache.clear()
            try:
                os.remove(fileserver.FILES_PATH)
            except FileNotFoundError:
                pass
    with_accounts(go)


@test
def t_the_csp_trusts_one_shopify_script_not_every_shopify_host():
    """cdn.shopify.com is also where Shopify serves every store's uploaded
    Files, and Files accepts .js - so a bare host entry trusted JavaScript
    uploaded by anyone with a free development store. That is the host a
    future markup sink would have loaded a session-stealer from."""
    import copilot as _c
    class _Req:
        headers = {}
        query_params = {}
        url = type("U", (), {"path": "/"})()
    csp = rendering._frame_headers(_Req())["Content-Security-Policy"]
    part = lambda name: [d for d in csp.split(";") if d.strip().startswith(name)][0].strip()
    script = part("script-src")
    ok("https://cdn.shopify.com/shopifycloud/" in script, "App Bridge still loads: " + script)
    ok("https://cdn.shopify.com;" not in script + ";" and not script.endswith("https://cdn.shopify.com"),
       "but not the bare host, which serves merchant uploads: " + script)
    ok("*.shopify.com" not in script, "and no wildcard host in script-src: " + script)
    img = part("img-src")
    ok(" https:" not in img.replace("https://", " "), "img-src is not every host alive: " + img)
    ok("https://cdn.shopify.com" in img, "product images still load")
    connect = part("connect-src")
    ok("*.myshopify.com" not in connect,
       "a *.myshopify.com name costs a free trial signup, so it is not an allowed "
       "destination for anything this page sends: " + connect)


@test
def t_an_oauth_landing_page_cannot_be_framed():
    # A nested helper, so it is read where it is written: the Google and Xero
    # callback results are the only pages the app serves outside the shell, and
    # the shell's frame-ancestors never applied to them.
    src = copilot_source()
    seg = src.split("def _oauth_page(")[1][:1600]
    ok("default-src 'none'" in seg, "no scripts at all on the callback pages")
    ok("frame-ancestors 'none'" in seg, "and they cannot be framed")


@test
def t_the_streaming_chat_route_checks_the_session_before_it_spends_an_ai_slot():
    """The global AI window is the app's most expensive shared resource. An
    unauthenticated caller was taking a slot from it on the way to a 401 -
    and the page never sent the session header at all, so every chat turn
    paid for that round trip before falling back."""
    gate._rl_global.clear()
    r = bare("/api/chat/stream", {"message": "hello"})
    eq(r.status_code, 401, "no app session, no answer")
    eq(len(gate._rl_global), 0, "and no slot was spent getting there")
    src = pagesource.join(HERE)
    seg = src.split("async function streamChat(")[1][:1200]
    ok("X-App-Session" in seg, "and the page now sends the session on the streaming call")


@test
def t_evicted_dispatch_records_are_archived_whole_not_dropped():
    """A dispatch record is the customs declaration and the courier booking
    HMRC can ask for within six years - the app says so where it refuses to
    erase them. The live store is capped for speed; what leaves it must not
    vanish, and if it cannot be archived it must not leave."""
    saved_max, saved_arch = desk.DISPATCH_STATE_MAX, desk.DISPATCH_ARCHIVE_PATH
    desk.DISPATCH_STATE_MAX = 3
    try:
        for p in (desk.DISPATCH_STATE_PATH, desk.DISPATCH_ARCHIVE_PATH):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
        rows = {str(100 + i): {"dispatched_at": f"2026-09-0{i}T10:00:00+00:00",
                               "name": f"Customer {i}", "address1": f"{i} Glass Works",
                               "tracking": f"TRK{i}"} for i in range(1, 6)}
        kept = desk._write_dispatch(dict(rows))
        eq(sorted(kept), ["103", "104", "105"], "the three newest stay live")
        arch = [json.loads(l) for l in open(desk.DISPATCH_ARCHIVE_PATH, encoding="utf-8")]
        eq([a["order_id"] for a in arch], ["101", "102"], "the two oldest were archived first")
        eq(arch[0]["address1"], "1 Glass Works", "whole - the record, not just an id")
        eq(arch[0]["tracking"], "TRK1")
        # An archive that cannot be written means nothing is trimmed.
        desk.DISPATCH_ARCHIVE_PATH = os.path.join(desk.DISPATCH_STATE_PATH, "not-a-dir", "x.jsonl")
        kept2 = desk._write_dispatch(dict(rows))
        eq(len(kept2), 5, "the live store keeps every row rather than lose one")
    finally:
        desk.DISPATCH_STATE_MAX, desk.DISPATCH_ARCHIVE_PATH = saved_max, saved_arch
        for p in (desk.DISPATCH_STATE_PATH, desk.DISPATCH_ARCHIVE_PATH):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass


@test
def t_a_size_rule_saved_in_the_app_lands_on_the_volume_not_in_the_image():
    """The seed rule files ship with the code, inside the container. A rule the
    bench saves has to outlive the container that saved it, so it goes to the
    volume - and the volume copy is what the lookup reads from then on."""
    def go():
        ensure_auth()
        live, seed = size_list.GOBO_OVERRIDES_LIVE, size_list.GOBO_OVERRIDES_PATH
        try:
            os.remove(live)
        except FileNotFoundError:
            pass
        size_list._gobo_cache["mtime"] = None
        try:
            eq(size_list._rule_path("override"), seed, "with no volume copy, the seed is read")
            before = len(size_list._gobo_rule_rows("override"))
            r = post("/api/gobo-sizes/rule",
                     {"op": "set", "manufacturer": "Showtec", "model": "Volume", "size": "37.5"})
            eq(r.status_code, 200, r.text)
            ok(os.path.isfile(live), "the save created the volume copy")
            eq(size_list._rule_path("override"), live, "which is read from now on")
            rows = size_list._gobo_rule_rows("override")
            ok(any(x["Model"] == "Volume" for x in rows), "with the new rule in it")
            eq(len(rows), before + 1, "and every seed rule carried across with it")
            ok("Volume" not in open(seed, encoding="utf-8").read(),
               "the seed inside the image is untouched")
            sheet = size_list._gobo_sizes()
            hits = [e for k, es in sheet["by_mm"].items() if k == ("showtec", "volume") for e in es]
            ok(hits and hits[0].get("production_size") == "37.5",
               "and the size lookup answers from the volume copy: %r" % hits[:1])
        finally:
            try:
                os.remove(live)
            except FileNotFoundError:
                pass
            size_list._gobo_cache["mtime"] = None
    with_accounts(go)


@test
def t_every_json_store_reaches_disk_through_the_one_writer():
    """Thirty-five hand-written copies of the write loop had four safety
    properties between them, applied to different subsets. The primitive is
    what makes every store get every property; this is what keeps the next
    store from writing its own loop."""
    import ast as _ast
    src = copilot_source()
    tree = _ast.parse(src)
    def owners(needle):
        out = set()
        for n in _ast.walk(tree):
            # add_routes and each area's register() only hold the routes
            if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef)) and n.name not in ("add_routes", "register"):
                if needle in _ast.get_source_segment(src, n):
                    out.add(n.name)
        return out
    # Text written as a temp file and swapped in: JSON goes through the primitive;
    # the rest is CSV, a zip, or the raw bytes of a restore.
    eq(owners('+ ".tmp"'), {"_write_json_store", "_write_gobo_rule_rows", "_weekly_snapshot",
                             "gobo_sizes_upload_route", "restore_route"},
       "a new temp-and-replace writer appeared; use _write_json_store")
    # JSON serialised straight into a file handle: only the primitive and the
    # append-only logs, which are lines added to a log, not a store rewritten
    # (the stock history and snapshots are the third).
    eq(owners("fh.write(json.dumps"), {"_archive_dispatch_rows", "_write_prod_state", "_work_trim",
                                       "_append_stock_lines"},
       "JSON is being written to disk outside the primitive")
    ok("allow_nan=False" in src.split("def _write_json_store")[1][:1500], "NaN is refused for every store")


@test
def t_the_one_writer_refuses_nan_a_poisoned_store_and_keeps_secrets_private():
    p = os.path.join(SCRATCH, "one-writer.json")
    for f in (p, p + ".tmp"):
        try:
            os.remove(f)
        except FileNotFoundError:
            pass
    jsonstore._write_json_store(p, "things", {"a": 1})
    eq(json.load(open(p))["things"], {"a": 1}, "keyed, the shape every loader reads")
    try:
        jsonstore._write_json_store(p, "things", {"a": float("nan")})
        ok(False, "NaN should have been refused")
    except ValueError:
        pass
    eq(json.load(open(p))["things"], {"a": 1}, "and the store is exactly as it was")
    ok(not os.path.exists(p + ".tmp"), "with no half-written temp file left beside it")
    jsonstore._poisoned_stores.add(p)
    try:
        try:
            jsonstore._write_json_store(p, "things", {"a": 2})
            ok(False, "a poisoned store must not be overwritten")
        except copilot.StoreUnwritable:
            pass
        eq(json.load(open(p))["things"], {"a": 1}, "untouched")
    finally:
        jsonstore._poisoned_stores.discard(p)
    os.chmod(p, 0o644)
    jsonstore._write_json_store(p, None, {"secret": "x"}, private=True)
    eq(oct(os.stat(p).st_mode & 0o777), "0o600", "a private write leaves the file owner-only, "
       "even one that existed at 0644")
    eq(json.load(open(p)), {"secret": "x"}, "None writes the object itself")
    os.remove(p)


@test
def t_add_routes_holds_routes_and_nothing_it_could_have_shared():
    """add_routes was 8,700 lines because forty-two ordinary helpers had been
    written inside it. None of them touched anything the function builds, so
    none of them had to be there - and being there meant no test could call
    them, nothing else in the file could reuse them, and finding one meant
    reading the route table.

    This recomputes the question rather than pinning a list: any nested
    function whose free names all resolve at module level could be a module
    function, so it should be one. The exceptions are the handful that close
    over the tool registry add_routes is handed, which genuinely cannot."""
    import ast as _ast, builtins as _bi
    src = copilot_source()
    tree = _ast.parse(src)
    ar = next(n for n in tree.body if getattr(n, "name", "") == "add_routes")

    module_names = set()
    for n in tree.body:
        if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
            module_names.add(n.name)
        elif isinstance(n, (_ast.Import, _ast.ImportFrom)):
            for a in n.names: module_names.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, _ast.Assign):
            for t in _ast.walk(n):
                if isinstance(t, _ast.Name) and isinstance(t.ctx, _ast.Store): module_names.add(t.id)
        elif isinstance(n, _ast.AnnAssign) and isinstance(n.target, _ast.Name):
            module_names.add(n.target.id)

    local_names = {a.arg for a in ar.args.args}
    for n in ar.body:
        if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
            local_names.add(n.name)
        elif isinstance(n, (_ast.Assign, _ast.AnnAssign, _ast.For, _ast.With)):
            for t in _ast.walk(n):
                if isinstance(t, _ast.Name) and isinstance(t.ctx, _ast.Store): local_names.add(t.id)

    builtin = set(dir(_bi))
    def free(fn):
        bound, used = set(), set()
        for a in _ast.walk(fn):
            if isinstance(a, _ast.arg): bound.add(a.arg)
            elif isinstance(a, _ast.Name):
                (bound if isinstance(a.ctx, _ast.Store) else used).add(a.id)
            elif isinstance(a, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)): bound.add(a.name)
            elif isinstance(a, (_ast.Import, _ast.ImportFrom)):
                for al in a.names: bound.add((al.asname or al.name).split(".")[0])
        return used - bound - builtin

    helpers = [n for n in ar.body if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))
               and not any("route" in _ast.unparse(d) for d in n.decorator_list)]
    liftable, changed = set(), True
    while changed:
        changed = False
        for h in helpers:
            if h.name in liftable: continue
            if not ((free(h) & local_names) - module_names - liftable):
                liftable.add(h.name); changed = True
    eq(liftable, set(), "these need nothing from add_routes, so they belong at module level")

    # The ones that stay say why: each closes over the registry add_routes is
    # handed, or over a value built from it. Two moved with their routes into
    # an area's register(mcp, registry): the desk's _finish_cancel and the
    # inbox's _mail_orders_for; dispatch_for became the chat module's own, the
    # registry handed to it once (piece 15).
    eq({h.name for h in helpers}, {"_fin_search", "_fin_thread", "_fin_bytes"},
       "a nested helper appeared that is not one of the registry-bound three")
    regs = [n for n in tree.body if getattr(n, "name", "") == "register"]
    eq({h.name for r in regs for h in r.body if isinstance(h, (_ast.FunctionDef, _ast.AsyncFunctionDef))
        and not any("route" in _ast.unparse(d) for d in h.decorator_list)},
       {"_finish_cancel", "_mail_orders_for"}, "the areas' routes hold the other two")

    # And it is a route table, not a module in disguise.
    ok(len(helpers) < 10, "add_routes is holding helpers again")


@test
def t_a_handler_uses_the_caller_it_was_handed_not_one_left_in_a_box():
    """Who is asking is request state, so it travels with the request. The CRM
    doors stashed the caller in one dict shared by every CRM route and read it
    back further down the handler; that is only correct while no `await` ever
    lands between the two, which nothing enforced, and the last route to be
    written was reading it 101 lines after its guard. Every door here returns
    (err, body, who) instead."""
    src = copilot_source()
    ok("_crm_actor" not in src, "no shared dict holds the current caller")
    ok("return None, body, who" in src.split("async def _crm_guard", 1)[1][:900],
       "the CRM door hands the caller back, the same shape as _guard")
    for line in src.splitlines():
        t = line.strip()
        if t.startswith("err, ") and "_crm_guard(request)" in t:
            ok(t.count(",") == 2, "a CRM route unpacks three values from its door: " + t)


@test
def t_every_signed_in_route_goes_through_the_one_door():
    """Seventy routes carried their own copy of the nine-line preamble, and one
    copy spent an AI slot before it had checked the session. The session is
    checked in one place now; this keeps it there."""
    import ast as _ast
    src = copilot_source()
    tree = _ast.parse(src)
    spans = [(n.lineno, n.end_lineno, n.name) for n in _ast.walk(tree)
             if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef)) and n.name != "add_routes"]
    def owner(lineno):
        inner = min((s for s in spans if s[0] <= lineno <= s[1]), key=lambda s: s[1] - s[0], default=None)
        return inner[2] if inner else "(module)"
    lines = src.splitlines()
    def owners(needle):
        return {owner(i) for i, l in enumerate(lines, 1)
                if needle in l and not l.strip().startswith(("#", "def ", "async def "))}
    eq(owners("_authorize(request"), {"_guard"}, "the session is checked in exactly one place")
    eq(owners("_pre_checks(request"), {"_guard", "_auth_guard", "sign_label_doc", "print_labels_doc"},
       "the anonymous checks run from the door, the anonymous auth guard, and the two print pages")
    eq(owners("_ai_slot()"), {"_guard"}, "the paid window is only ever spent by the door, after the session")
    ok(not any("_pre_checks(request, ai" in l for l in lines), "no route spends an AI slot before it knows who is asking")


@test
def t_the_door_checks_rank_before_it_spends_an_ai_slot():
    def go():
        ensure_auth()
        owen, sess, _pw = ready_user("Owen", "owen")
        eq(post("/api/team/user", {"op": "tabs", "id": owen, "tabs": ["recon"]}).status_code, 200)
        r = post_s(sess, "/api/recon/sweep", {})
        eq(r.status_code, 403, r.text)
        ok("admin" in r.json()["error"], r.text)
        eq(len(gate._rl_global), 0, "a member's refused sweep did not spend an AI slot")
    with_accounts(go)


@test
def t_the_environment_reference_is_generated_from_the_code():
    """Two hundred variables are read; the hand-written example documented
    thirty-nine and carried another project's defaults. The reference is
    built from the syntax tree, and this fails when it has not been rebuilt."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("env_reference", os.path.join(HERE, "tools", "env_reference.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = mod.collect(HERE)
    names = {r[0] for r in rows}
    ok(len(names) >= 200, "every variable the code reads is collected: %d" % len(names))
    ok({"SHOPIFY_STORE", "TOKEN_ENCRYPTION_KEY", "GOBO_OVERRIDES_LIVE", "DISPATCH_ARCHIVE_PATH"} <= names)
    eq(mod.render(HERE), open(os.path.join(HERE, "docs", "ENVIRONMENT.md"), encoding="utf-8").read(),
       "docs/ENVIRONMENT.md is stale: run `make env-doc`")
    # And the short example file names nothing the code does not read.
    ex = set(re.findall(r"^\s*#?\s*([A-Z][A-Z0-9_]+)=", open(os.path.join(HERE, "env.example"), encoding="utf-8").read(), re.M))
    eq(sorted(ex - names), [], "env.example names a variable nothing reads")


@test
def t_the_environment_reference_does_not_name_the_shop():
    """The repository is public, and the reference printed two of the code's
    defaults with the shop's own domain in them. It writes [shop domain] in
    its place. The domain is read off the quote site's default here too, so
    this test does not carry it either."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("env_reference", os.path.join(HERE, "tools", "env_reference.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    host = next(r[3] for r in mod.collect(HERE) if r[0] == "PROPOSAL_HOST").strip("\"'")
    domain = host.split(".", 1)[1]
    ok(domain.count(".") >= 1, "the quote site's default is a host on the shop's domain: " + host)
    for text, where in ((mod.render(HERE), "the generated reference"),
                        (open(os.path.join(HERE, "docs", "ENVIRONMENT.md"), encoding="utf-8").read(),
                         "docs/ENVIRONMENT.md")):
        ok(domain not in text, where + " names the shop's domain")
        ok('| `PROPOSAL_HOST` | `"quote.[shop domain]"` |' in text, where + ": the row says what stands there")


@test
def t_the_api_reference_is_generated_from_the_code():
    """A hundred and fifty routes and nothing listed them: the page and the
    server agreed because each side's tests happened to. docs/API.md is built
    from the route decorators themselves, and this fails when it is stale."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("route_reference", os.path.join(HERE, "tools", "route_reference.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = mod.collect(HERE)
    src = "".join(open(os.path.join(HERE, f), encoding="utf-8").read() for _, f in mod.module_files(HERE))
    eq(len(rows), len(re.findall(r"@\w+\.custom_route\(", src)), "every route decorator is a row")
    by = {r["path"]: r for r in rows}
    eq(by["/api/backup"]["door"], "_guard", "the backup route opens with the one door")
    ok("_team_role" in by["/api/backup"]["checks"], "and its own master check is named")
    eq(by["/api/crm/deal"]["tab"], "crm", "a CRM route is opened by the CRM tab")
    eq(by["/api/alerts"]["tab"], "any account", "an open route says so")
    eq(by["/api/team/user"]["door"], "_team_guard", "a guard helper is named as the door")
    eq(by["/api/dispatch/book"]["door"], "_guard", "a door reached as core._guard is still the door")
    eq((by["/api/dispatch/book"]["module"], by["/api/dispatch/book"]["handler"]),
       ("gizmo.routes.dispatch", "dispatch_book_route"), "and the handler is named where it lives")
    ok("_team_level" in by["/api/shipping/config"]["checks"], "a check reached as core._team_level is named")
    eq(by["/api/team/user"]["terms"], "rank admin", "with the rank it asks for")
    eq(by["/api/skills"]["terms"], "max body SKILLS_BODY_MAX, cap SKILLS_BODY_MAX",
       "a limit read through its area's name is named as the limit itself")
    eq(by["/hooks/forecast/results"]["door"], "own check", "a hook has no session door")
    ok("_forecast_token_ok" in by["/hooks/forecast/results"]["checks"], "and names the check it makes")
    eq(mod.render(HERE), open(os.path.join(HERE, "docs", "API.md"), encoding="utf-8").read(),
       "docs/API.md is stale: run `make api-doc`")


@test
def t_the_api_reference_does_not_name_the_shop():
    """The repository is public. The route list carries the handlers'
    docstrings, so it is checked for the shop's domain exactly as the
    environment reference is, the domain read off the quote site's default."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("env_reference", os.path.join(HERE, "tools", "env_reference.py"))
    env = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(env)
    host = next(r[3] for r in env.collect(HERE) if r[0] == "PROPOSAL_HOST").strip("\"'")
    domain = host.split(".", 1)[1]
    text = open(os.path.join(HERE, "docs", "API.md"), encoding="utf-8").read()
    ok(domain not in text, "docs/API.md names the shop's domain")


@test
def t_the_stores_are_measured_not_guessed():
    """Most stores are parsed from disk on every request that needs them. The
    audit could not say whether that costs anything, because the volume is
    not visible from the code. Now the app says it: sizes at boot and in
    Settings, with the read cost of anything over a megabyte."""
    data_dir = os.path.dirname(scheduler.SCHEDULE_PATH)
    big = os.path.join(data_dir, "measured_big.json")
    open(big, "w", encoding="utf-8").write(json.dumps({"rows": [{"i": i, "pad": "x" * 40} for i in range(25000)]}))
    try:
        rep = appstatus._store_report()
        row = next(r for r in rep if r["name"] == "measured_big.json")
        ok(row["bytes"] >= 1024 * 1024, "a store over a megabyte is listed with its size: %d" % row["bytes"])
        ok(isinstance(row.get("parse_ms"), float) and row["parse_ms"] >= 0, "and its read cost was measured")
        eq(rep[0]["bytes"], max(r["bytes"] for r in rep), "largest first")
        ok(all("parse_ms" not in r for r in rep if r["bytes"] < 1024 * 1024), "small stores are not parsed for it")
        s = post("/api/status", {}).json()
        ok(any(r["name"] == "measured_big.json" for r in s["volume"]["stores"]), "and Settings can see it")
    finally:
        os.remove(big)


@test
def t_a_hot_store_is_read_from_disk_once_until_the_file_changes():
    """The dispatch state, the production state and the CRM were parsed from
    disk on every request that needed them. The cache is keyed on the file -
    mtime, size, inode - so a restore, a repair by hand or a test writing the
    file directly is a miss without anyone remembering to invalidate."""
    p = desk.DISPATCH_STATE_PATH
    try:
        os.remove(p)
    except FileNotFoundError:
        pass
    jsonstore._forget_store(p)
    calls = {"n": 0}
    real = jsonstore._load_json_store
    def counting(path, key, default):
        if path == p:
            calls["n"] += 1
        return real(path, key, default)
    jsonstore._load_json_store = counting
    try:
        desk._write_dispatch({"1": {"tracking_number": "A", "dispatched_at": "2026-09-01T00:00:00+00:00"}})
        a = desk._load_dispatch(); b = desk._load_dispatch(); desk._load_dispatch()
        eq(calls["n"], 0, "after a write the store is what was written; nothing is re-parsed")
        ok(a is b, "and every reader in the process sees one object")
        # Somebody else replaces the file: the next read notices.
        json.dump({"orders": {"1": {"tracking_number": "B", "dispatched_at": "2026-09-01T00:00:00+00:00"}}},
                  open(p, "w", encoding="utf-8"))
        eq(desk._load_dispatch()["1"]["tracking_number"], "B", "a file written behind the cache is read fresh")
        eq(calls["n"], 1)
        desk._load_dispatch()
        eq(calls["n"], 1, "and then served from memory again")
        os.remove(p)
        eq(desk._load_dispatch(), {}, "a store that is gone is empty, not remembered")
    finally:
        jsonstore._load_json_store = real
        jsonstore._forget_store(p)


@test
def t_a_failed_write_forgets_the_cached_store():
    """Callers mutate the object the loader hands them and then write. If the
    write is refused, the memory copy already carries a change that never
    reached disk - and every later reader would trust it. Memory never
    outlives a failed write."""
    p = production.PRODUCTION_STATE_PATH
    try:
        os.remove(p)
    except FileNotFoundError:
        pass
    jsonstore._forget_store(p)
    production._write_prod_state({"7": {"printed_at": "2026-09-01T00:00:00+00:00"}})
    state = production._load_prod_state()
    state["7"]["made_at"] = "2026-09-07T00:00:00+00:00"       # mutated in memory...
    jsonstore._poisoned_stores.add(p)
    try:
        try:
            production._write_prod_state(state)                       # ...and the write is refused
            ok(False, "should have raised")
        except production.ProdStateUnwritable:
            pass
    finally:
        jsonstore._poisoned_stores.discard(p)
    eq(production._load_prod_state()["7"].get("made_at"), None,
       "the unsaved change is gone: the next read came from the disk that never had it")
    # The CRM's per-read normalisation now runs once per file version.
    crm_wipe()
    jsonstore._forget_store(salesdesk.CRM_PATH)
    d = salesdesk._load_crm()
    d["persons"]["p1"] = {"id": "p1", "name": "Cached"}
    salesdesk._write_crm(d)
    ok(salesdesk._load_crm() is d, "the CRM is one object across reads once written")
    crm_wipe()
    jsonstore._forget_store(salesdesk.CRM_PATH)
    eq(salesdesk._load_crm()["persons"], {}, "and a wiped store is empty again")


