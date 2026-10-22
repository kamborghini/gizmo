# =========================== speed: the CRM board, built once per version =====
# The third speed pull request (the 2026-10-12 audit, S1). Every board read
# rebuilt, serialised and compressed the whole board on the one event loop
# (about 50 ms at production size, while every other request waited), and
# every open CRM tab read it again every 90 seconds.

@test
def t_the_crm_board_is_built_once_per_version_of_what_it_shows():
    """The board is the CRM store shaped with the team list, today's date and
    the clock (a deal rots N days after it was last touched). It is now built
    once per version of those and reused, and a write warms it for the next
    read. A change to the CRM, the team, the date or the hour builds it
    again, so nobody is shown a board older than what it is built from."""
    def go():
        post("/api/crm/contact", {"op": "person_add", "name": "Board Probe", "emails": ["bp@example.com"]})
        built, real = [], salesdesk._crm_shape

        def spy(d):
            built.append(1)
            return real(d)
        saved_today = salesdesk._crm_today
        salesdesk._crm_shape = spy
        salesdesk._crm_board_cache["key"] = None       # a cold start, as after a deploy
        try:
            a = post("/api/crm/board", {}).json()
            b = post("/api/crm/board", {}).json()
            eq(len(built), 1, "two reads, one build")
            eq(a, b, "and the same board both times")
            ok(a.get("rev"), "with a revision to compare against")
            built.clear()
            w = post("/api/crm/contact", {"op": "person_add", "name": "Second Probe", "emails": ["sp@example.com"]})
            eq(w.status_code, 200, w.text[:200])
            c = post("/api/crm/board", {}).json()
            eq(len(built), 1, "the write built it once, and the read after it reused that")
            ok(any(p.get("name") == "Second Probe" for p in c["crm"]["persons"].values()), "and it shows the write")
            ok(c["rev"] != a["rev"] and c["rev"] == w.json().get("rev"), "under a new revision, which the write answered")
            built.clear()
            ready_user("Board Teammate", "boardmate")
            d = post("/api/crm/board", {}).json()
            eq(len(built), 1, "a change to the team builds it again")
            ok(any(r["name"] == "Board Teammate" for r in d["crm"]["team"]), "and the new name is on it")
            built.clear()
            salesdesk._crm_today = lambda: saved_today() + timedelta(days=1)
            e = post("/api/crm/board", {}).json()
            eq(len(built), 1, "a new day builds it again")
            eq(e["crm"]["today"], (saved_today() + timedelta(days=1)).isoformat())
        finally:
            salesdesk._crm_shape, salesdesk._crm_today = real, saved_today
    with_accounts(go)


@test
def t_an_unchanged_crm_board_is_not_sent_again():
    """Each open CRM tab asks for the board every 90 seconds and on every
    return to the tab: about 400 KB each time at production size, redrawn in
    full. The page now sends the revision it holds and an unchanged board
    answers {same: true}. A page that sends no revision (one still open from
    before this update) gets the whole board as it always has."""
    def go():
        post("/api/crm/contact", {"op": "person_add", "name": "Rev Probe", "emails": ["rp@example.com"]})
        full = post("/api/crm/board", {}).json()
        rev = full["rev"]
        same = post("/api/crm/board", {"rev": rev}).json()
        eq(same, {"same": True, "rev": rev}, "nothing changed, nothing sent")
        old_page = post("/api/crm/board", {}).json()
        ok("crm" in old_page, "an older page that sends no revision still gets the board")
        post("/api/crm/contact", {"op": "person_add", "name": "Rev Probe 2", "emails": ["rp2@example.com"]})
        moved = post("/api/crm/board", {"rev": rev}).json()
        ok("crm" in moved and moved["rev"] != rev, "a board that moved is sent, with its new revision")
        stale = post("/api/crm/board", {"rev": "not-a-revision"}).json()
        ok("crm" in stale, "an unknown revision gets the board")
    with_accounts(go)


@test
def t_forgetting_the_crm_forgets_its_board():
    """The kept board may have been built from the CRM store in memory after
    a change that a failed write then never saved. A write that fails forgets
    the store so the next read comes from disk; the board must go with it,
    all of it, or the unsaved change could be served from the board."""
    def go():
        post("/api/crm/contact", {"op": "person_add", "name": "Forget Probe", "emails": ["fp@example.com"]})
        salesdesk._crm_board()
        ok(salesdesk._crm_board_cache["key"] is not None, "the board is kept")
        jsonstore._forget_store(salesdesk.CRM_PATH)
        eq(salesdesk._crm_board_cache["key"], None, "and forgotten with the store")
        ok(all(not v for v in salesdesk._crm_board_cache.values()),
           "all of it, not only its key: %r" % sorted(k for k, v in salesdesk._crm_board_cache.items() if v))
    with_accounts(go)


@test
def t_a_crm_write_never_leaves_the_board_from_before_it():
    """The kept board is found again by its key, and a CRM file is known by
    its time, size and inode. Written twice inside the clock's tick at the
    same size, with the inode handed back, the file has the same key after a
    write as before it, so a write that did not build the board itself (the
    Shopify link sweep) left the old one to be served. Writing the CRM now
    lets the board go first."""
    def go():
        post("/api/crm/contact", {"op": "person_add", "name": "Tick Probe", "emails": ["tick@example.com"]})
        real_stat = jsonstore._stat_key
        jsonstore._stat_key = lambda p: ("same", 1, 1) if p == salesdesk.CRM_PATH else real_stat(p)
        try:
            salesdesk._crm_board_cache["key"] = None
            post("/api/crm/board", {})
            d = salesdesk._load_crm()
            for p in d["persons"].values():
                if p.get("name") == "Tick Probe":
                    p["name"] = "Tock Probe"          # the same size on disk
            salesdesk._write_crm(d)
            after = post("/api/crm/board", {}).json()
        finally:
            jsonstore._stat_key = real_stat
        names = {p.get("name") for p in after["crm"]["persons"].values()}
        ok("Tock Probe" in names and "Tick Probe" not in names, "the board after the write is built from it: %r" % names)
    with_accounts(go)


@test
def t_a_crm_read_that_failed_is_not_kept_as_the_board():
    """A read of the CRM that fails hands back an empty CRM (the poison guard
    keeps the file for repair). The board built from it must not be kept: the
    file has not changed, so a kept empty board was served to everyone until
    the next write, long after the file read again."""
    def go():
        post("/api/crm/contact", {"op": "person_add", "name": "Flaky Probe", "emails": ["flaky@example.com"]})
        real = jsonstore._load_json_store

        def once(path, key, default):
            if path == salesdesk.CRM_PATH:
                jsonstore._load_json_store = real
                jsonstore._poisoned_stores.add(path)
                return default
            return real(path, key, default)
        jsonstore._forget_store(salesdesk.CRM_PATH)       # the next read comes from disk
        jsonstore._load_json_store = once
        try:
            bad = post("/api/crm/board", {}).json()
        finally:
            jsonstore._load_json_store = real
        named = lambda r: any(p.get("name") == "Flaky Probe" for p in r["crm"]["persons"].values())
        ok(not named(bad), "the failed read gave an empty CRM")
        good = post("/api/crm/board", {}).json()
        ok(named(good), "and the next read, with the file readable again, shows what it holds")
        ok(good["rev"] != bad["rev"], "under its own revision")
    with_accounts(go)


@test
def t_a_crm_write_keeps_its_board_under_the_day_it_was_built_for():
    """A write builds the board and keeps it. The key it is kept under is
    taken before the board is built: taken after, a write at the turn of the
    hour or the day kept a board built for the old one under the new one, and
    it was served all through the new hour."""
    def go():
        saved, real = salesdesk._crm_today, salesdesk._crm_shape
        turned = []

        def shape(d):
            out = real(d)
            if not turned:
                turned.append(1)
                salesdesk._crm_today = lambda: saved() + timedelta(days=1)   # midnight, while it is built
            return out
        salesdesk._crm_shape = shape
        try:
            w = post("/api/crm/contact", {"op": "person_add", "name": "Midnight Probe", "emails": ["mp@example.com"]})
            eq(w.status_code, 200, w.text[:200])
            salesdesk._crm_shape = real
            b = post("/api/crm/board", {}).json()
            eq(b["crm"]["today"], (saved() + timedelta(days=1)).isoformat(),
               "the read after midnight is built for the new day")
        finally:
            salesdesk._crm_shape, salesdesk._crm_today = real, saved
    with_accounts(go)


@test
def t_the_crm_revision_is_the_board_itself():
    """The revision the page compares against is a fingerprint of the board
    as sent, not of the files it is built from. Made from the files, it did
    not change when a new version of the app shaped the same files another
    way, so a page open across the update was told nothing had changed and
    kept the old board; and it changed on every sign-in and every wrong
    password (both write the team's file), sending the whole board to every
    open CRM for nothing and telling each of them someone had tried to sign
    in."""
    def go():
        _uid, _s, pw = ready_user("Print Probe", "printprobe")
        post("/api/crm/contact", {"op": "person_add", "name": "Print Probe", "emails": ["pp@example.com"]})
        rev = post("/api/crm/board", {}).json()["rev"]
        before = jsonstore._stat_key(team.USERS_PATH)
        eq(login("printprobe", "not-the-password-1").status_code, 401, "a wrong password")
        eq(login("printprobe", pw).status_code, 200, "and a sign-in")
        ok(jsonstore._stat_key(team.USERS_PATH) != before, "both written to the team's file")
        eq(post("/api/crm/board", {"rev": rev}).json(), {"same": True, "rev": rev},
           "and the board, which neither changed, is not sent again")
        real = salesdesk._crm_shape
        salesdesk._crm_shape = lambda d: {**real(d), "shaped_by": "the next version"}
        salesdesk._crm_board_cache["key"] = None        # a restart into the next version
        try:
            moved = post("/api/crm/board", {"rev": rev}).json()
        finally:
            salesdesk._crm_shape = real
        ok("crm" in moved and moved["rev"] != rev and moved["crm"].get("shaped_by"),
           "a board shaped another way from the same files is sent: %r" % {k: moved[k] for k in moved if k != "crm"})
    with_accounts(go)



