# =========================== accounts: the app's own auth ===================
def with_accounts(fn):
    """Run fn against a fresh, empty accounts world. On exit everything is
    wiped again so the harness's lazy master is recreated for later tests."""
    def wipe():
        team._users_mem = None
        team._sessions_mem = None
        work._work_mem = None
        activity._events_mem = None
        activity._events_dirty = False
        APP_AUTH["session"] = APP_AUTH["master"] = ""
        for p in (team.USERS_PATH, team.SESSIONS_PATH, activity.ACTIVITY_PATH,
                  work.WORK_PATH):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
            jsonstore._poisoned_stores.discard(p)
    wipe()
    try:
        fn()
    finally:
        wipe()

def bare(path, body):
    gate._rl_hits.clear(); gate._rl_global.clear()
    return client.post(path, json=body, headers={"Authorization": "Bearer " + tok()})

def make_user(name, username, role="member"):
    r = post("/api/team/user", {"op": "create", "name": name, "username": username, "role": role})
    eq(r.status_code, 200, r.text)
    j = r.json()
    uid = [u["id"] for u in j["users"] if u["username"] == username][0]
    return uid, j["starter_password"]

def login(username, pw):
    """One sign-in. The per-client ceiling is cleared once per TEST by the
    runner, not per call: clearing it here made it impossible for any test to
    observe the ceiling at all, which is how it came to be asserted and never
    actually exercised."""
    return bare("/api/auth/login", {"username": username, "password": pw})

def drive_pw(session):
    """Make the account's Finder drive password and return it (audit R-007:
    the account password no longer opens /dav)."""
    r = post_s(session, "/api/files/drive", {"op": "create"})
    eq(r.status_code, 200, r.text)
    return r.json()["password"]

def ready_user(name, username, role="member", pw="chosen-pw-123456"):
    """Create an account and take it THROUGH the forced first-password change,
    returning (uid, session, pw) ready for normal use."""
    uid, starter = make_user(name, username, role=role)
    # Account SETUP, not a sign-in burst: a test that builds eight accounts is
    # not one browser making sixteen attempts in a minute. Cleared here rather
    # than in login(), which would make the ceiling unobservable everywhere.
    team._login_hits.clear()
    s0 = login(username, starter).json()["session"]
    post_s(s0, "/api/auth/password", {"current": starter, "new": pw})
    team._login_hits.clear()
    return uid, login(username, pw).json()["session"], pw

@test
def t_auth_first_run_creates_the_master_and_bricks_the_door():
    def go():
        st = bare("/api/auth/state", {}).json()
        ok(st["setup"], "an empty app asks to be set up")
        code = os.environ["SETUP_CODE"]
        eq(bare("/api/auth/setup", {"name": "C", "username": "c", "password": "short", "setup_code": code}).status_code,
           400, "8 characters minimum")
        r = bare("/api/auth/setup", {"name": "Cameron", "username": "cameron",
                                     "password": MASTER_PW, "setup_code": code})
        eq(r.status_code, 200, r.text)
        eq(r.json()["me"]["role"], "master")
        eq(bare("/api/auth/setup", {"name": "X", "username": "x", "password": "longenough1",
                                    "setup_code": code}).status_code,
           400, "setup runs exactly once")
        st2 = bare("/api/auth/state", {}).json()
        ok(not st2["setup"] and not st2["logged_in"], "a session cookie is not implied")
    with_accounts(go)

@test
def t_auth_no_session_means_no_entry_anywhere():
    def go():
        ensure_auth()
        eq(bare("/api/files/tree", {}).status_code, 401,
           "a valid Shopify embed token alone opens nothing")
        eq(post("/api/files/tree", {}).status_code, 200, "a session does")
    with_accounts(go)

@test
def t_auth_login_is_vague_locked_and_logged():
    def go():
        ensure_auth()
        r = login("cameron", "wrong-password")
        eq(r.status_code, 401)
        ok("do not match" in r.json()["error"], "one vague answer")
        r2 = login("nobody", "whatever12")
        eq(r2.status_code, 401)
        eq(r.json()["error"], r2.json()["error"], "the same vague answer for user and password")
        # Enough wrong passwords to trip the ACCOUNT lock, clearing the
        # per-client ceiling between them: that is a separate control with its
        # own test, and it would answer 429 before this one ever locks.
        for _ in range(team.LOGIN_FAIL_LIMIT + 1):
            team._login_hits.clear()
            login("cameron", "wrong-password")
        team._login_hits.clear()
        r3 = login("cameron", MASTER_PW)
        eq(r3.status_code, 401, "the pause blocks even the right password")
        eq(r3.json()["error"], r.json()["error"],
           "and answers with the same vague line, so a guesser learns nothing")
        ev = post("/api/team/board", {})
        # the pause blocks even the right password, so the board call needs the
        # existing session, which stays valid
        eq(ev.status_code, 200, ev.text)
        ok(any(e["action"] == "failed login" for e in ev.json()["events"]), "failures are on the ledger")
        ok(any(e["action"] == "account paused" for e in ev.json()["events"]), "so is the pause")
    with_accounts(go)

@test
def t_auth_passwords_are_hashed_and_never_echoed():
    def go():
        ensure_auth()
        raw = open(team.USERS_PATH).read()
        ok(MASTER_PW not in raw, "no plain text password on disk")
        b = post("/api/team/board", {}).json()
        ok(all("pw" not in u and "password" not in u for u in b["users"]),
           "no password material in any response")
        uid, starter = make_user("Owen", "owen")
        ok(starter not in open(team.USERS_PATH).read(), "starter passwords are hashed too")
    with_accounts(go)

@test
def t_auth_starter_password_flow_forces_a_change():
    def go():
        ensure_auth()
        uid, starter = make_user("Owen", "owen")
        r = login("owen", starter)
        eq(r.status_code, 200, r.text)
        ok(r.json()["me"]["must_change"], "the starter is only for getting in")
        sess = r.json()["session"]
        r2 = post_s(sess, "/api/auth/password", {"current": "wrong", "new": "owens-own-pw1"})
        eq(r2.status_code, 400, "the current password is always required")
        r3 = post_s(sess, "/api/auth/password", {"current": starter, "new": "owens-own-pw1"})
        eq(r3.status_code, 200, r3.text)
        eq(login("owen", starter).status_code, 401, "the starter is dead")
        eq(login("owen", "owens-own-pw1").status_code, 200, "the chosen password lives")
        eq(post_s(sess, "/api/files/tree", {}).status_code, 401,
           "changing the password killed the old session")
        eq(post_s(r3.json()["session"], "/api/files/tree", {}).status_code, 200,
           "and handed back a fresh one")
    with_accounts(go)

@test
def t_auth_rank_order_is_enforced_on_the_server():
    def go():
        ensure_auth()
        ian, ian_pw = make_user("Ian", "ian", role="admin")
        owen, owen_pw = make_user("Owen", "owen")
        ian_sess = login("ian", ian_pw).json()["session"]
        post_s(ian_sess, "/api/auth/password", {"current": ian_pw, "new": "ians-own-pw12"})
        ian_sess = login("ian", "ians-own-pw12").json()["session"]
        # An admin manages members...
        r = post_s(ian_sess, "/api/team/user", {"op": "create", "name": "Amy", "username": "amy"})
        eq(r.status_code, 200, "an admin can create members")
        eq(post_s(ian_sess, "/api/team/user", {"op": "reset_password", "id": owen}).status_code, 200,
           "an admin can reset a member's password")
        # ...but never upwards.
        eq(post_s(ian_sess, "/api/team/user",
                  {"op": "create", "name": "Bob", "username": "bob", "role": "admin"}).status_code,
           403, "only the master creates admins")
        eq(post_s(ian_sess, "/api/team/user", {"op": "role", "id": ian, "role": "admin"}).status_code,
           403, "an admin cannot touch roles at all")
        master = APP_AUTH["master"]
        eq(post_s(ian_sess, "/api/team/user", {"op": "rename", "id": master, "name": "X"}).status_code,
           403, "the master cannot be managed by an admin")
        eq(post_s(ian_sess, "/api/team/user", {"op": "reset_password", "id": master}).status_code,
           403, "nor their password reset")
        # A member manages nobody.
        _m, owen_sess, _pw = ready_user("Molly", "molly")
        eq(post_s(owen_sess, "/api/team/board", {}).status_code, 403, "members see no register")
        eq(post_s(owen_sess, "/api/backup", {}).status_code, 403, "and no admin doors")
        eq(post_s(owen_sess, "/api/files/tree", {}).status_code, 200, "work tools stay open")
    with_accounts(go)

@test
def t_auth_the_master_is_untouchable():
    def go():
        ensure_auth()
        master = APP_AUTH["master"]
        eq(post("/api/team/user", {"op": "role", "id": master, "role": "member"}).status_code, 400,
           "the master cannot be demoted, even by themselves")
        eq(post("/api/team/user", {"op": "delete", "id": master}).status_code, 400,
           "or deleted")
        eq(post("/api/team/user", {"op": "active", "id": master, "active": False}).status_code, 400,
           "or switched off")
    with_accounts(go)

@test
def t_auth_switch_off_and_delete_end_sessions_immediately():
    def go():
        ensure_auth()
        owen, sess, owen_pw = ready_user("Owen", "owen")
        eq(post_s(sess, "/api/team/me", {}).status_code, 200)
        post("/api/team/user", {"op": "active", "id": owen, "active": False})
        eq(post_s(sess, "/api/team/me", {}).status_code, 401, "off means off, this second")
        eq(login("owen", owen_pw).status_code, 401, "and the door stays shut")
        post("/api/team/user", {"op": "active", "id": owen, "active": True})
        amy, amy_sess, amy_pw = ready_user("Amy", "amy")
        post("/api/team/user", {"op": "delete", "id": amy})
        eq(post_s(amy_sess, "/api/team/me", {}).status_code, 401, "deletion ends the session")
        eq(login("amy", amy_pw).status_code, 401, "and the account")
        names = post("/api/team/board", {}).json()["names"]
        ok(any(v == "Amy" for v in names.values()), "history keeps the deleted account's name")
    with_accounts(go)

@test
def t_auth_logout_ends_exactly_that_session():
    def go():
        ensure_auth()
        owen, s1, pw = ready_user("Owen", "owen")
        s2 = login("owen", pw).json()["session"]
        post_s(s1, "/api/auth/logout", {})
        eq(post_s(s1, "/api/team/me", {}).status_code, 401, "the logged-out session is dead")
        eq(post_s(s2, "/api/team/me", {}).status_code, 200, "the other lives on")
    with_accounts(go)

@test
def t_auth_a_lost_register_means_setup_not_a_free_for_all():
    def go():
        ensure_auth()
        with open(team.USERS_PATH, "w") as fh:
            fh.write("{not json")
        team._users_mem = None
        eq(post("/api/files/tree", {}).status_code, 401,
           "with the accounts lost, nobody is silently let in")
        st = bare("/api/auth/state", {}).json()
        ok(st["setup"], "the app asks to be set up again instead")
    with_accounts(go)

@test
def t_auth_the_ledger_attributes_work_to_accounts():
    def go():
        ensure_auth()
        reset_dispatch(); reset_prod()
        def work(sent):
            r = mark_made(12345, True)
            eq(r.status_code, 200, r.text)
        with_zeta(work)
        b = post("/api/team/board", {}).json()
        ev = [e for e in b["events"] if e["action"] == "marked made"]
        ok(ev, "marking made reached the ledger")
        eq(ev[0]["sub"], APP_AUTH["master"], "attributed to the signed-in account")
        ok((b["counts"].get(APP_AUTH["master"]) or {}).get("made", 0) >= 1, "and tallied")
    with_accounts(go)

@test
def t_auth_counts_mean_work_not_events():
    def go():
        ensure_auth()
        boss = APP_AUTH["master"]
        activity._track(boss, "production", "marked made", "#1")
        activity._track(boss, "production", "marked made", "#2")
        activity._track(boss, "production", "un-marked made", "#2")
        activity._track(boss, "dispatch", "booked a courier", "#1")
        activity._track(boss, "dispatch", "cancelled a shipment", "#1")
        c = post("/api/team/board", {}).json()["counts"][boss]
        eq(c["made"], 1, "an undo subtracts a made")
        eq(c["dispatched"], 0, "a cancellation subtracts a booking")
    with_accounts(go)

@test
def t_auth_the_print_document_needs_only_the_perimeter():
    """The admin print action lives on the Shopify order page, outside the
    app's login, and App Bridge can only give it an embed token - so the
    embed token alone must keep BOTH halves working: signing the URL and
    rendering the document. This assertion is deliberately positive: an
    earlier version only checked that the word "Unauthorized" was absent,
    which stayed green while a refusal worded differently killed the whole
    feature."""
    def go():
        ensure_auth()
        # 1. The extension signs a URL with the embed token and NO app session.
        r = client.post("/print/production-labels/sign",
                        json={"ids": "12345", "size": "4x6"},
                        headers={"Authorization": "Bearer " + tok()})
        eq(r.status_code, 200, "the print-action extension can sign: " + r.text[:200])
        url = r.json().get("path") or ""
        ok(url.startswith("/print/production-labels?ids="), url)
        ok("sig=" in url and "exp=" in url, "and gets a signed, expiring url")
        # 2. That signed URL renders the document with no session at all.
        r2 = client.get(url)
        eq(r2.status_code, 200, r2.text[:200])
        ok("<html" in r2.text.lower(), "a real document, not a refusal")
        # 3. A forged signature is refused outright.
        bad = client.get(url[:-4] + "dead")
        ok(bad.status_code in (401, 403), "a tampered signature is refused: " + str(bad.status_code))
    with_accounts(go)

@test
def t_a_row_printed_by_name_starts_after_its_count_and_wraps():
    """#104453's projector printed in Shopify's label as `1x` then a gap, then
    "Projected Image 40 Watt LED Weather...": the count's column is held wide
    so sizes line up, and a row's text is cut to one line. A row with no size
    (a projector, an accessory, a stock gobo) has nothing to line up with, so
    its name starts after the count and wraps; a sized row is unchanged."""
    o = _copy.deepcopy(ORDER)
    o["line_items"] = [
        {"id": 1, "title": "Custom Gobos", "quantity": 1, "product_id": 900, "properties": [], "sku": "SCGOWPIH",
         "variant_title": "Single Colour Glass Original With Projector (Quote) / IH"},
        {"id": 2, "title": "Projected Image 40 Watt LED Weatherproof Gobo Projector", "quantity": 1,
         "product_id": 901, "properties": [], "sku": "P102W"}]
    async def tj(registry, name, args):
        if name == "shopify_get_order":
            return _copy.deepcopy(o)
        return await fake_tool_json(registry, name, args)
    def go():
        ensure_auth()
        r = client.post("/print/production-labels/sign", json={"ids": str(o["id"]), "size": "4x4"},
                        headers={"Authorization": "Bearer " + tok()})
        eq(r.status_code, 200, r.text[:200])
        doc = client.get(r.json()["path"]).text
        ok("<div class='it named wrap'><span class='iqs'>1x</span><span class='desc'>&quot;Projected Image 40 Watt "
           "LED Weatherproof Gobo Projector&quot;</span>" in doc, "the projector's row starts after its count and wraps")
        ok("<div class='it'><span class='iqs'>1x 53.3mm</span>" in doc, "the sized gobo's row is as it was")
        ok(".it.named .iqs { min-width: 0; }" in doc, "and the count's column is not held wide for it")
    shopify._tool_json = tj
    try:
        with_accounts(go)
    finally:
        shopify._tool_json = fake_tool_json


@test
def t_nothing_in_the_page_can_add_to_or_cut_the_shopify_label_print():
    """The page's label print was changed on 30 September after a bench
    browser put 66px of its own into the page and every label printed with a
    blank after it: in print the labels are laid against the top of the page,
    over anything else, and nothing beside body prints, so nothing in the page
    can add a page (unless it is taller than the run), push a label down or
    cut one off. The document Shopify's print action opens is the same labels
    in another page, open to the same intrusion, so it gets the same rules:
    all its labels in one box, laid when the document's own script marks the
    page, which it does except in WebKit (laid, WebKit's A4 runs crept up the
    page a little more on every label). Nothing is cut: a first fix that cut
    the page to N labels tall took the last label off whenever anything sat
    above the labels."""
    def go():
        ensure_auth()
        r = client.post("/print/production-labels/sign", json={"ids": "12345,12346"},
                        headers={"Authorization": "Bearer " + tok()})
        eq(r.status_code, 200, r.text[:200])
        path = r.json()["path"]
        for size, orient, page_w, page_h in (("4x6", "", 101.6, 152.4), ("4x4", "", 101.6, 101.6),
                                             ("4x2", "", 101.6, 50.8), ("a4", "", 210, 297),
                                             ("4x6", "portrait", 152.4, 101.6), ("2x4", "", 50.8, 101.6)):
            doc = client.get(path + "&size=" + size + ("&orient=" + orient if orient else "")).text
            where = size + (" " + orient if orient else "") + ": "
            head, _, body = doc.partition("</style>")
            ok(re.search(r"@page \{ size: %smm %smm; margin: 0; \}" % (re.escape(str(page_w)), re.escape(str(page_h))), head),
               where + "the printer's page is the stock asked for: " + head[head.find("@page"):][:80])
            n = body.count("<div class='sheet'>")
            ok(n >= 1, where + "the document has labels: " + doc[:200])
            # The box's own closing tag, found by depth, so a label left
            # outside it (and so not laid) is seen.
            i = body.index("<div id='labels'>")
            depth = 0
            for m in re.finditer(r"<div\b|</div>", body[i:]):
                depth += 1 if m.group(0) == "<div" else -1
                if depth == 0:
                    break
            box, after = body[i:i + m.end()], body[i + m.end():]
            eq(box.count("<div class='sheet'>"), n, where + "every label is in the one box that is laid")
            ok("class='sheet'" not in after, where + "and none is left after it")
            if orient:
                eq(box.count("<div class='pw'>"), n, where + "one page wrapper per label")
            i = head.index("@media print {")
            depth, j = 0, i
            for j in range(i, len(head)):
                depth += head[j] == "{"
                depth -= head[j] == "}"
                if depth == 0 and head[j] == "}":
                    break
            block = head[i + len("@media print {"):j].strip()
            ok("html > :not(head):not(body) { display: none !important; }" in block, where + "nothing beside body prints")
            ok("html.lay, html.lay body { position: static !important; }" in block
               and "html.lay #labels { position: absolute !important; top: 0 !important; left: 0 !important; "
                   "z-index: 2147483647 !important; }" in block,
               where + "the labels' box is laid against the top of the page, in front of anything else: " + block[:260])
            ok("background: #fff; -webkit-print-color-adjust: exact; print-color-adjust: exact;"
               in head[head.index(".sheet {"):head.index("}", head.index(".sheet {"))],
               where + "and each label is white, printed as such, so nothing laid under it shows through")
            ok("overflow" not in block and "height" not in block,
               where + "nothing is cut: a cut takes the last label off when anything sits above the labels")
            ok("<script>(function(){if(navigator.vendor!=='Apple Computer, Inc.')"
               "document.documentElement.classList.add('lay');" in body,
               where + "the laying is switched on first thing, except in WebKit")
    with_accounts(go)

@test
def t_the_shopify_print_knows_every_stock_and_starts_on_the_production_size():
    """Cameron, 30 September: "add 4x4 to the shopify print too". The
    document the print action opens knew five sizes and fell back to 4 x 6
    for anything else, so the 4 x 4 the production printer is loaded with
    could not come off it. It now prints every size the shop can choose, and
    the signing call hands back the production printer's saved size so the
    action opens on it: the stock is a shop setting, not a choice made at the
    print button."""
    def go():
        ensure_auth()
        eq(set(desk.LABEL_STOCK_MM), set(desk.LABEL_STOCK),
           "the document can print every stock size the shop can choose")
        eq(desk.LABEL_STOCK_MM["4x4"], (101.6, 101.6), "4 x 4 is square, in millimetres")
        before = post("/api/shipping/config", {"op": "get"}).json()["config"]["label_size_production"]
        try:
            for saved in ("4x4", "4x3", "a4"):
                eq(post("/api/shipping/config", {"op": "set", "label_size_production": saved}).status_code, 200)
                r = client.post("/print/production-labels/sign", json={"ids": "12345"},
                                headers={"Authorization": "Bearer " + tok()})
                eq(r.status_code, 200, r.text[:200])
                eq(r.json().get("size"), saved, "the action opens on the production printer's size")
            # A saved value the document cannot print is never handed on.
            cfg = desk._load_shipping()
            cfg["label_size_production"] = "9x9"
            desk._save_shipping(cfg)
            r = client.post("/print/production-labels/sign", json={"ids": "12345"},
                            headers={"Authorization": "Bearer " + tok()})
            eq(r.json().get("size"), "4x4", "an unknown saved size falls back to the production default")
            path = r.json()["path"]
            doc = client.get(path + "&size=4x4").text
            ok("@page { size: 101.6mm 101.6mm; margin: 0; }" in doc, "a 4 x 4 print is on 4 x 4 paper")
            ok(".sheet { width: 101.6mm; height: 101.6mm;" in doc, "with 4 x 4 labels")
            doc = client.get(path + "&size=5x5").text
            ok("@page { size: 101.6mm 152.4mm; margin: 0; }" in doc, "a size it does not know still prints, on 4 x 6")
        finally:
            eq(post("/api/shipping/config", {"op": "set", "label_size_production": before}).status_code, 200)
    with_accounts(go)

@test
def t_tabs_are_locked_on_the_server_not_just_hidden():
    def go():
        ensure_auth()
        owen, sess, pw = ready_user("Owen", "owen")
        r = post("/api/team/user", {"op": "tabs", "id": owen, "tabs": ["labels"]})
        eq(r.status_code, 200, r.text)
        eq(post_s(sess, "/api/files/tree", {}).status_code, 403, "a blocked tab answers 403")
        blocked = post_s(sess, "/api/files/tree", {}).json()["error"]
        ok("switched off for your account" in blocked, blocked)
        eq(post_s(sess, "/api/production-labels", {}).status_code, 200,
           "the allowed tab still works")
        eq(post_s(sess, "/api/team/me", {}).status_code, 200,
           "and a 403 never killed the session")
        me = post_s(sess, "/api/team/me", {}).json()["me"]
        eq(me["tabs"], ["labels"], "the account knows its own doors")
        eq(login("owen", pw).json()["me"]["tabs"], ["labels"],
           "and the login answer carries the doors, so the page hides them at once")
        eq(post("/api/team/user", {"op": "tabs", "id": owen, "tabs": None}).status_code, 200)
        eq(post_s(sess, "/api/files/tree", {}).status_code, 200, "null restores everything")
    with_accounts(go)

@test
def t_tabs_cannot_touch_the_master_and_follow_rank():
    def go():
        ensure_auth()
        master = APP_AUTH["master"]
        eq(post("/api/team/user", {"op": "tabs", "id": master, "tabs": ["labels"]}).status_code,
           403, "the master cannot be restricted")
        eq(post("/api/files/tree", {}).status_code, 200, "and opens everything regardless")
        ian, ian_pw = make_user("Ian", "ian", role="admin")
        owen, owen_pw = make_user("Owen", "owen")
        ian_sess = login("ian", ian_pw).json()["session"]
        post_s(ian_sess, "/api/auth/password", {"current": ian_pw, "new": "ians-own-pw12"})
        ian_sess = login("ian", "ians-own-pw12").json()["session"]
        eq(post_s(ian_sess, "/api/team/user",
                  {"op": "tabs", "id": owen, "tabs": ["files"]}).status_code, 200,
           "an admin sets a member's tabs")
        eq(post_s(ian_sess, "/api/team/user",
                  {"op": "tabs", "id": ian, "tabs": ["files"]}).status_code, 403,
           "but cannot set an admin's, including their own")
    with_accounts(go)


@test
def t_every_refused_sign_in_costs_exactly_one_password_check():
    """Every refusal at the door is the same 401, and a made-up username pays
    one dummy password check so it costs what a wrong password costs. But a
    real account that was locked, switched off or holding an expired
    break-glass password was refused before any check ran, so it answered in
    a fraction of the time. Five wrong guesses lock any real account, and from
    then on the clock said which usernames exist. Counted, not timed, so a
    loaded machine cannot flake it; and the lock, the switch and the expiry
    still refuse the right password, without counting a single wrong one."""
    def go():
        ensure_auth()
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        locked_until = (_dt.now(_tz.utc) + _td(minutes=15)).isoformat()
        _w, _s, _ = ready_user("Wren", "wren-wrong")
        lock_uid, _s, lock_pw = ready_user("Lark", "lark-locked")
        off_uid, _s, off_pw = ready_user("Otto", "otto-off")
        exp_uid, _s, exp_pw = ready_user("Ezra", "ezra-expired")
        d = team._load_users()
        d["users"][lock_uid]["lock_until"] = locked_until
        d["users"][lock_uid]["locks"] = 1
        d["users"][off_uid]["active"] = False
        d["users"][exp_uid]["pw_expires_at"] = "2000-01-01T00:00:00+00:00"
        team._write_users(d)

        def held(uid):
            u = team._load_users()["users"][uid]
            return (int(u.get("fails") or 0), int(u.get("locks") or 0),
                    u.get("lock_until") or "", u.get("active", True), u.get("pw_expires_at") or "")
        before = {uid: held(uid) for uid in (lock_uid, off_uid, exp_uid)}

        spent, real = [], team._check_pw
        team._check_pw = lambda pw, stored: (spent.append(1), real(pw, stored))[1]
        try:
            def knock(username, password):
                team._login_hits.clear()
                spent.clear()
                r = login(username, password)
                return len(spent), r
            guess = "a-guess-that-is-wrong"
            tried = {
                "a made-up username": knock("nobody-by-this-name", guess),
                "a wrong password": knock("wren-wrong", guess),
                "a locked account": knock("lark-locked", guess),
                "a locked account's right password": knock("lark-locked", lock_pw),
                "a switched-off account": knock("otto-off", guess),
                "a switched-off account's right password": knock("otto-off", off_pw),
                "an expired password, wrongly typed": knock("ezra-expired", guess),
                "an expired password, rightly typed": knock("ezra-expired", exp_pw),
            }
        finally:
            team._check_pw = real

        # Headers that differ between any two requests by nature, not by path.
        per_request = {"date", "server-timing"}
        def shape(r):
            return sorted((k.lower(), v) for k, v in r.headers.items()
                          if k.lower() not in per_request)
        _n, first = tried["a made-up username"]
        for what, (n, r) in tried.items():
            eq(n, 1, "%s runs exactly one password check, not %d" % (what, n))
            eq(r.status_code, 401, "%s is refused: %s" % (what, r.text))
            eq(r.content, first.content, "%s reads exactly like a made-up name" % what)
            eq(shape(r), shape(first), "%s carries the same headers as a made-up name" % what)

        eq(held(lock_uid), before[lock_uid],
           "the locked account stays locked, its right password clears nothing and "
           "a guess at it adds nothing to the count")
        eq(held(off_uid), before[off_uid], "the switched-off account is untouched")
        eq(held(exp_uid), before[exp_uid], "the expired password is untouched")
        wren = team._load_users()["users"][_w]
        eq(int(wren.get("fails") or 0), 1, "a wrong password on an open account still counts")
    with_accounts(go)

@test
def t_a_wrong_password_is_written_down_after_the_answer():
    """A wrong password on a real account adds one to its count, and the
    count is kept in the register on disk. That write ran before the 401 went
    out, and it is the one thing at the door a made-up name never pays for:
    a made-up name, a locked account and a switched-off one all answer from
    memory. So a wrong password took one disk write longer than a made-up
    name, and the clock said which usernames exist although both read the
    same and both cost one password check. The count still reaches the disk,
    only once the answer has gone. Ordered, not timed, so a loaded machine
    cannot flake it."""
    def go():
        ensure_auth()
        uid, _s, _pw = ready_user("Wren", "wren-wrong")
        events, real_write = [], team._write_users
        def write(d):
            events.append("written")
            real_write(d)
        inner = client.app
        async def watching(scope, receive, send):
            async def sent(msg):
                await send(msg)
                if msg["type"] == "http.response.body" and not msg.get("more_body"):
                    events.append("answered")
            await inner(scope, receive, sent)
        watcher = TestClient(watching)
        def knock(username):
            team._login_hits.clear(); gate._rl_hits.clear(); gate._rl_global.clear()
            events.clear()
            r = watcher.post("/api/auth/login",
                             json={"username": username, "password": "a-guess-that-is-wrong"},
                             headers={"Authorization": "Bearer " + tok()})
            eq(r.status_code, 401, "%s is refused: %s" % (username, r.text))
            return list(events)
        team._write_users = write
        try:
            eq(knock("nobody-by-this-name"), ["answered"],
               "a made-up name answers without touching the register")
            eq(knock("wren-wrong"), ["answered", "written"],
               "a wrong password is answered first and written down after")
        finally:
            team._write_users = real_write
        team._users_mem = None
        eq(int(team._load_users()["users"][uid].get("fails") or 0), 1,
           "the wrong guess reached the register on disk")
    with_accounts(go)
