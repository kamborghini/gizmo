# ---- Page layouts: each person's own arrangement of a screen's cards --------

def with_layouts(fn):
    """A fresh accounts world with an empty layouts store, wiped again on the
    way out so no later test inherits somebody's arrangement."""
    def wipe():
        try:
            os.remove(layouts.LAYOUTS_PATH)
        except FileNotFoundError:
            pass
        jsonstore._poisoned_stores.discard(layouts.LAYOUTS_PATH)
        jsonstore._forget_store(layouts.LAYOUTS_PATH)
    def go():
        wipe()
        try:
            fn()
        finally:
            wipe()
    with_accounts(go)

@test
def t_a_layout_belongs_to_the_account_that_saved_it():
    """Rearranging your Overview must never move a colleague's cards. The
    account is the session the door returns, never a name in the body, so a
    body that names somebody else still saves to whoever sent it."""
    def go():
        ensure_auth()
        master = APP_AUTH["master"]
        owen, sess, _pw = ready_user("Owen", "owen")
        r = post("/api/layouts", {"view": "overview", "order": ["trend", "alerts"],
                                  "hidden": ["drivers"], "uid": owen, "user": owen})
        eq(r.status_code, 200, r.text)
        eq(r.json()["layouts"], {"overview": {"order": ["trend", "alerts"], "hidden": ["drivers"]}},
           "the save answers with the caller's own map")
        r = post_s(sess, "/api/layouts", {"view": "overview", "order": ["alerts"], "hidden": []})
        eq(r.status_code, 200, r.text)
        eq(post("/api/layouts", {}).json()["layouts"],
           {"overview": {"order": ["trend", "alerts"], "hidden": ["drivers"]}},
           "the master reads back only the master's")
        eq(post_s(sess, "/api/layouts", {}).json()["layouts"],
           {"overview": {"order": ["alerts"], "hidden": []}},
           "and Owen only Owen's, although the master's body named him")
        on_disk = json.load(open(layouts.LAYOUTS_PATH))["layouts"]
        eq(sorted(on_disk), sorted([master, owen]), "one entry per account, keyed by the session's account")
    with_layouts(go)

@test
def t_layouts_are_closed_without_a_session():
    """A layout is a person's own, so with nobody signed in there is nobody
    whose layout to read or change."""
    def go():
        ensure_auth()
        eq(bare("/api/layouts", {}).status_code, 401, "no session, no read")
        r = bare("/api/layouts", {"view": "overview", "order": ["trend"], "hidden": []})
        eq(r.status_code, 401, "no session, no save")
        ok(not os.path.exists(layouts.LAYOUTS_PATH), "and nothing reached the disk")
    with_layouts(go)

@test
def t_a_layout_the_page_could_not_have_made_is_refused_and_nothing_is_written():
    """The page only ever sends card ids it rendered, so anything else is a
    fault or a probe, and each is told plainly rather than half saved. The
    store starts empty here, so any write at all would leave a file behind."""
    def go():
        ensure_auth()
        good = {"view": "overview", "order": ["trend"], "hidden": []}
        bad = [
            ({**good, "view": "nowhere"}, "an unknown view"),
            ({**good, "view": "chat"}, "chat, which has no cards to arrange"),
            ({"order": ["trend"], "hidden": []}, "no view at all"),
            ({**good, "order": "trend"}, "an order that is not a list"),
            ({"view": "overview", "order": ["trend"]}, "a missing hidden list"),
            ({**good, "order": ["c%d" % i for i in range(65)]}, "65 ids"),
            ({**good, "hidden": ["c%d" % i for i in range(65)]}, "65 hidden ids"),
            ({**good, "order": ["two words"]}, "an id with a space"),
            ({**good, "order": ["Trend"]}, "an id in upper case"),
            ({**good, "order": ["trend\n"]}, "an id with a trailing newline"),
            ({**good, "order": ["-trend"]}, "an id that starts with a hyphen"),
            ({**good, "order": ["x" * 49]}, "an id longer than 48 characters"),
            ({**good, "order": [7]}, "an id that is not a string"),
            ({"view": "overview", "reset": "yes"}, "reset that is not exactly true"),
            ({"view": "overview", "reset": False}, "reset false"),
        ]
        for body, why in bad:
            r = post("/api/layouts", body)
            eq(r.status_code, 400, why + ": " + r.text)
            ok(r.json().get("error"), why + " says what was wrong")
        ok(not os.path.exists(layouts.LAYOUTS_PATH), "none of those wrote a thing")
        eq(post("/api/layouts", {**good, "order": ["c%d" % i for i in range(64)]}).status_code, 200,
           "64 ids is the limit, not past it")
        os.remove(layouts.LAYOUTS_PATH)
        jsonstore._forget_store(layouts.LAYOUTS_PATH)
        big = {**good, "order": ["x" * 48] * 200}
        eq(post("/api/layouts", big).status_code, 413, "a body past 8KB is refused before it is read")
        # The door hands a handler {} for a body that is not a JSON object, so
        # a list arrives as a read of the caller's own layouts, never a write.
        r = post("/api/layouts", ["overview", "trend"])
        eq(r.status_code, 200, r.text)
        eq(r.json()["layouts"], {}, "a body that is not an object reads, it does not save")
        ok(not os.path.exists(layouts.LAYOUTS_PATH), "and neither of those wrote a thing")
    with_layouts(go)

@test
def t_resetting_a_screen_forgets_only_that_screen_for_that_person():
    """Reset then Done removes one person's layout for one screen. It must not
    take their other screens with it, or anyone else's Overview."""
    def go():
        ensure_auth()
        _owen, sess, _pw = ready_user("Owen", "owen")
        post("/api/layouts", {"view": "overview", "order": ["trend"], "hidden": []})
        post("/api/layouts", {"view": "crm", "order": ["board", "stats"], "hidden": []})
        post_s(sess, "/api/layouts", {"view": "overview", "order": ["alerts"], "hidden": ["trend"]})
        r = post("/api/layouts", {"view": "overview", "reset": True})
        eq(r.status_code, 200, r.text)
        eq(r.json()["layouts"], {"crm": {"order": ["board", "stats"], "hidden": []}},
           "the caller's other screen stays")
        eq(post_s(sess, "/api/layouts", {}).json()["layouts"],
           {"overview": {"order": ["alerts"], "hidden": ["trend"]}},
           "and the other account's Overview is untouched")
        r = post("/api/layouts", {"view": "overview", "reset": True})
        eq(r.status_code, 200, "resetting a screen with nothing saved is not an error")
        eq(r.json()["layouts"], {"crm": {"order": ["board", "stats"], "hidden": []}})
        post("/api/layouts", {"view": "crm", "reset": True})
        on_disk = json.load(open(layouts.LAYOUTS_PATH))["layouts"]
        ok(APP_AUTH["master"] not in on_disk, "an account with nothing saved leaves no empty entry")
    with_layouts(go)

@test
def t_a_new_account_has_no_layouts_to_read():
    """Nothing saved reads as an empty map, so the page renders every screen
    in its default order instead of treating a newcomer as an error."""
    def go():
        ensure_auth()
        post("/api/layouts", {"view": "overview", "order": ["trend"], "hidden": []})
        _uid, sess, _pw = ready_user("Nia", "nia")
        r = post_s(sess, "/api/layouts", {})
        eq(r.status_code, 200, r.text)
        eq(r.json(), {"layouts": {}}, "a newcomer reads nothing, not the master's layout")
    with_layouts(go)

@test
def t_a_card_named_twice_keeps_its_first_place():
    """A card sits in one place. A repeat in the list is collapsed rather than
    refused, keeping the place it was first given."""
    def go():
        ensure_auth()
        r = post("/api/layouts", {"view": "seo", "order": ["trend", "alerts", "trend", "drivers", "alerts"],
                                  "hidden": ["kpi-score", "kpi-score"]})
        eq(r.status_code, 200, r.text)
        eq(r.json()["layouts"]["seo"], {"order": ["trend", "alerts", "drivers"], "hidden": ["kpi-score"]})
    with_layouts(go)

@test
def t_the_layouts_file_is_owner_only_and_keyed_by_account():
    """The file is written only through the one writer, as a private store,
    so it is owner-only whether it is new or was left readable by something
    else, and it has the shape the loader expects."""
    def go():
        ensure_auth()
        master = APP_AUTH["master"]
        eq(post("/api/layouts", {"view": "overview", "order": ["trend", "alerts"],
                                 "hidden": ["drivers"]}).status_code, 200)
        eq(os.stat(layouts.LAYOUTS_PATH).st_mode & 0o777, 0o600, "a new file is owner-only")
        eq(json.load(open(layouts.LAYOUTS_PATH)),
           {"layouts": {master: {"overview": {"order": ["trend", "alerts"], "hidden": ["drivers"]}}}})
        os.chmod(layouts.LAYOUTS_PATH, 0o644)
        eq(post("/api/layouts", {"view": "mail", "order": ["inbox"], "hidden": []}).status_code, 200)
        eq(os.stat(layouts.LAYOUTS_PATH).st_mode & 0o777, 0o600, "and a readable one is made owner-only again")
    with_layouts(go)

@test
def t_a_layout_that_could_not_be_saved_is_never_answered_as_saved():
    """The page keeps a person in Customize with their draft on screen when a
    save fails, so the route has to say it failed. A store that will not parse
    is also never overwritten: everyone's layouts in it are kept for repair."""
    def go():
        ensure_auth()
        with open(layouts.LAYOUTS_PATH, "w") as fh:
            fh.write('{"layouts": {"broken')
        r = post("/api/layouts", {"view": "overview", "order": ["trend"], "hidden": []})
        eq(r.status_code, 500, r.text)
        ok("The layout could not be saved" in r.json()["error"], r.text)
        eq(open(layouts.LAYOUTS_PATH).read(), '{"layouts": {"broken', "the unreadable file is left as it was")
    with_layouts(go)

@test
def t_an_account_with_tabs_switched_off_can_still_arrange_its_cards():
    """Layouts belong to no tab: the route is on the open list, so an account
    given only the Labels tab can still keep its own arrangement of it."""
    def go():
        ensure_auth()
        owen, sess, _pw = ready_user("Owen", "owen")
        eq(post("/api/team/user", {"op": "tabs", "id": owen, "tabs": ["labels"]}).status_code, 200)
        eq(post_s(sess, "/api/files/tree", {}).status_code, 403, "the account really is restricted")
        r = post_s(sess, "/api/layouts", {"view": "labels", "order": ["queue", "made"], "hidden": []})
        eq(r.status_code, 200, r.text)
        eq(post_s(sess, "/api/layouts", {}).json()["layouts"],
           {"labels": {"order": ["queue", "made"], "hidden": []}})
    with_layouts(go)

@test
def t_work_the_clock_is_the_servers_and_only_for_parttime():
    def go():
        ensure_auth()
        eq(post("/api/work/clock", {"op": "in"}).status_code, 400,
           "the master does not clock in; monitoring follows the part-time role only")
        pt, sess, pw = ready_user("Poppy", "poppy", role="parttime")
        st = post_s(sess, "/api/work/status", {}).json()
        ok(st["monitored"] and not st["clocked_in"], "logged in is not clocked in")
        r = post_s(sess, "/api/work/clock", {"op": "in", "start": "1999-01-01T00:00:00Z"})
        eq(r.status_code, 200, r.text)
        ok(r.json()["session"]["start"].startswith("20"),
           "the browser's timestamp was ignored; the server minted its own")
        eq(post_s(sess, "/api/work/clock", {"op": "in"}).status_code, 400, "no double clock-in")
        activity._track("SYS-TEST-NOBODY", "production", "marked made", "#x")
        activity._track("", "production", "marked made", "#hook")
        # Backdate the open session so it reads as a real shift: a sub-minute
        # clock cycle is a mis-tap and is deliberately not recorded.
        _w = work._load_work()
        _w["open"][pt]["start"] = "2026-08-01T09:00:00+00:00"
        work._write_work(_w)
        eq(post_s(sess, "/api/work/clock", {"op": "out"}).status_code, 200)
        eq(post_s(sess, "/api/work/clock", {"op": "out"}).status_code, 400,
           "no clock-out when not clocked in")
        b = post("/api/work/board", {}).json()
        eq(len(b["sessions"]), 1, "the session is on the record")
        ok(b["sessions"][0]["secs"] >= 0 and b["sessions"][0]["end"], "with a computed duration")
        eq(post_s(sess, "/api/work/board", {}).status_code, 403,
           "part-time accounts cannot read the monitoring board")
    with_accounts(go)

@test
def t_work_events_are_stamped_only_on_the_clock():
    def go():
        ensure_auth()
        pt, sess, pw = ready_user("Poppy", "poppy", role="parttime")
        activity._track(pt, "production", "marked made", "#off-clock")
        post_s(sess, "/api/work/clock", {"op": "in"})
        activity._track(pt, "production", "marked made", "#on-clock")
        activity._track("", "production", "marked made", "#system")
        post_s(sess, "/api/work/clock", {"op": "out"})
        activity._track(pt, "production", "marked made", "#after")
        ev = post("/api/team/board", {}).json()["events"]
        by_detail = {e["detail"]: e for e in ev if e.get("detail", "").startswith("#")}
        ok("ws" not in by_detail["#off-clock"], "off the clock is not billable")
        ok(by_detail["#on-clock"].get("ws"), "on the clock carries the session")
        eq(by_detail["#system"].get("src"), "system", "automation is never a person")
        ok("ws" not in by_detail["#system"], "and never billable")
        ok("ws" not in by_detail["#after"], "the stamp stops at clock-out")
        # the role drives it: change the role and the monitoring stops by itself
        post_s(login("poppy", pw).json()["session"], "/api/work/clock", {"op": "in"})
        post("/api/team/user", {"op": "role", "id": pt, "role": "member"})
        activity._track(pt, "production", "marked made", "#as-member")
        ev2 = post("/api/team/board", {}).json()["events"]
        row = next(e for e in ev2 if e.get("detail") == "#as-member")
        ok("ws" not in row, "a role change ends the monitoring on its own")
    with_accounts(go)

@test
def t_work_resolve_is_a_recorded_correction_and_reports_add_up():
    def go():
        ensure_auth()
        pt, sess, pw = ready_user("Poppy", "poppy", role="parttime")
        post_s(sess, "/api/work/clock", {"op": "in"})
        r = post("/api/work/resolve", {"uid": pt, "note": "left the bench without clocking out"})
        eq(r.status_code, 200, r.text)
        s = r.json()["session"]
        ok(s["corrected"] and s["corrected_by"] == APP_AUTH["master"] and s["start"],
           "the closure wears its author and the original start stands")
        ev = post("/api/team/board", {}).json()["events"]
        ok(any(e["action"] == "resolved a work session" for e in ev), "and is on the ledger")
        s2 = login("poppy", pw).json()["session"]
        post_s(s2, "/api/work/clock", {"op": "in"})
        _w = work._load_work()          # a real shift, not a sub-minute mis-tap
        _w["open"][pt]["start"] = "2026-08-01T09:00:00+00:00"
        work._write_work(_w)
        post_s(s2, "/api/work/clock", {"op": "out"})
        rep = post("/api/work/report", {"uid": pt}).json()
        eq(rep["count"], 2, "both sessions in the report")
        ok(rep["csv"].startswith("Name,Date,Clock in"), "csv for payroll")
        ok("Poppy" in rep["csv"] and "yes" in rep["csv"], "with the correction marked")
        rep2 = post("/api/work/report", {"uid": pt, "from": "2099-01-01"}).json()
        eq(rep2["count"], 0, "the date range filters")
    with_accounts(go)

@test
def t_dav_speaks_finder_with_the_apps_own_accounts():
    def go():
        ensure_auth()
        def fake_upload(fileobj, bucket, key):
            fake_s3.objects[key] = len(fileobj.read())
        fake_s3 = FakeS3()
        fake_s3.upload_fileobj = fake_upload
        fake_s3.copy_object = lambda **kw: fake_s3.objects.__setitem__(
            kw["Key"], fake_s3.objects.get(kw["CopySource"]["Key"], 0))
        saved = (fileserver.R2_ACCOUNT_ID, fileserver.R2_ACCESS_KEY_ID, fileserver.R2_SECRET_ACCESS_KEY,
                 fileserver._files_s3_client)
        fileserver.R2_ACCOUNT_ID = fileserver.R2_ACCESS_KEY_ID = fileserver.R2_SECRET_ACCESS_KEY = "acct"
        fileserver._files_s3_client = fake_s3
        webdav._dav_auth_cache.clear()
        fileserver._files_mem = None
        try:
            os.remove(fileserver.FILES_PATH)
        except FileNotFoundError:
            pass
        jsonstore._poisoned_stores.discard(fileserver.FILES_PATH)
        try:
            import base64 as b64
            _, _sess, ppw = ready_user("Poppy", "poppy", role="parttime")
            auth = {"Authorization": "Basic " + b64.b64encode(f"poppy:{drive_pw(_sess)}".encode()).decode()}
            bad = {"Authorization": "Basic " + b64.b64encode(b"poppy:wrong-password").decode()}
            r = client.request("PROPFIND", "/dav/", headers={"Depth": "1"})
            eq(r.status_code, 401, "no credentials, no listing")
            ok("WWW-Authenticate" in r.headers, "and Finder is told to ask")
            eq(client.request("PROPFIND", "/dav/", headers={**bad, "Depth": "1"}).status_code, 401)
            r2 = client.request("PROPFIND", "/dav/", headers={**auth, "Depth": "1"})
            eq(r2.status_code, 207, r2.text[:200])
            eq(client.request("MKCOL", "/dav/Proofs", headers=auth).status_code, 201)
            # A real Finder save of a PDF carries PDF bytes; the intake now reads them.
            r3 = client.put("/dav/Proofs/0538 proof.pdf", headers=auth, content=b"%PDF-1.4\n" + b"x" * 491)
            eq(r3.status_code, 201, "a save from Finder lands")
            st = fileserver._load_files()
            rec = next(v for v in st["files"].values() if v["name"] == "0538 proof.pdf")
            eq(rec["size"], 500, "with the true size")
            ok(rec["by"], "and the person's account on it")
            listing = client.request("PROPFIND", "/dav/Proofs", headers={**auth, "Depth": "1"}).text
            ok("0538 proof.pdf" in listing, "and it lists")
            # junk is accepted but invisible in the app
            eq(client.put("/dav/Proofs/.DS_Store", headers=auth, content=b"j").status_code, 201)
            tree = post("/api/files/tree", {}).json()["store"]
            ok(all(f["name"] != ".DS_Store" for f in tree["files"].values()),
               "Finder droppings never reach the page")
            # move, then delete = the same 30-day trash as the page
            eq(client.request("MOVE", "/dav/Proofs/0538 proof.pdf", headers={**auth,
               "Destination": "/dav/Proofs/0538 proof v2.pdf"}).status_code, 201)
            eq(client.request("DELETE", "/dav/Proofs/0538 proof v2.pdf", headers=auth).status_code, 204)
            st2 = fileserver._load_files()
            rec2 = next(v for v in st2["files"].values() if v["name"] == "0538 proof v2.pdf")
            eq(rec2["status"], "trashed", "a Finder delete is a trash, never a destruction")
            ev = post("/api/team/board", {}).json()["events"]
            ok(any(e["action"] == "added a file from Finder" for e in ev), "saves hit the ledger")
            lk = client.request("LOCK", "/dav/Proofs", headers=auth)
            eq(lk.status_code, 200, "class 2 for a read-write mount")
        finally:
            (fileserver.R2_ACCOUNT_ID, fileserver.R2_ACCESS_KEY_ID, fileserver.R2_SECRET_ACCESS_KEY,
             fileserver._files_s3_client) = saved
            webdav._dav_auth_cache.clear()
            try:
                os.remove(fileserver.FILES_PATH)
            except FileNotFoundError:
                pass
    with_accounts(go)

@test
def t_audit_tab_gate_covers_cache_print_and_shipping():
    def go():
        ensure_auth()
        owen, starter = make_user("Owen", "owen")
        sess = login("owen", starter).json()["session"]
        post_s(sess, "/api/auth/password", {"current": starter, "new": "owens-own-pw-1"})
        sess = login("owen", "owens-own-pw-1").json()["session"]
        post("/api/team/user", {"op": "tabs", "id": owen, "tabs": ["files"]})
        # /api/cache filters to allowed tabs
        r = post_s(sess, "/api/cache", {})
        eq(r.status_code, 200)
        ok(all(k not in r.json() for k in ("overview", "seo", "keywords", "customers_segments")),
           "cache leaks nothing for a files-only account")
        # shipping is labels-gated now
        eq(post_s(sess, "/api/shipping/config", {}).status_code, 403, "shipping read is labels-gated")
        # print doc refuses a labels-denied app session
        r2 = client.get("/print/production-labels?ids=12345&id_token=" + tok(),
                        headers={"X-App-Session": sess})
        ok("switched off" in r2.text or "Unauthorized" in r2.text, "print refused for labels-denied")
    with_accounts(go)

@test
def t_audit_dav_cache_respects_revocation_and_own_lockout():
    def go():
        ensure_auth()
        fake = FakeS3()
        saved = (fileserver.R2_ACCOUNT_ID, fileserver.R2_ACCESS_KEY_ID, fileserver.R2_SECRET_ACCESS_KEY,
                 fileserver._files_s3_client)
        fileserver.R2_ACCOUNT_ID = fileserver.R2_ACCESS_KEY_ID = fileserver.R2_SECRET_ACCESS_KEY = "acct"
        fileserver._files_s3_client = fake
        webdav._dav_auth_cache.clear(); webdav._dav_fail_cache.clear()
        fileserver._files_mem = None
        try:
            os.remove(fileserver.FILES_PATH)
        except FileNotFoundError:
            pass
        try:
            import base64 as b64
            pt, starter = make_user("Poppy", "poppy", role="parttime")
            # a starter password never mounts the drive
            auth0 = {"Authorization": "Basic " + b64.b64encode(f"poppy:{starter}".encode()).decode()}
            eq(client.request("PROPFIND", "/dav/", headers={**auth0, "Depth": "0"}).status_code, 401,
               "must-change accounts cannot open the drive")
            sess = login("poppy", starter).json()["session"]
            post_s(sess, "/api/auth/password", {"current": starter, "new": "poppys-own-pw-9"})
            own = {"Authorization": "Basic " + b64.b64encode(b"poppy:poppys-own-pw-9").decode()}
            eq(client.request("PROPFIND", "/dav/", headers={**own, "Depth": "0"}).status_code, 401,
               "the account password no longer opens the drive (audit R-007)")
            sess = login("poppy", "poppys-own-pw-9").json()["session"]
            auth = {"Authorization": "Basic " + b64.b64encode(("poppy:" + drive_pw(sess)).encode()).decode()}
            eq(client.request("PROPFIND", "/dav/", headers={**auth, "Depth": "0"}).status_code, 207,
               "the drive password mounts it")
            # cache is warm; now switch the account off -> next request refused AT ONCE
            post("/api/team/user", {"op": "active", "id": pt, "active": False})
            eq(client.request("PROPFIND", "/dav/", headers={**auth, "Depth": "0"}).status_code, 401,
               "a warm cache does not outlive deactivation")
            post("/api/team/user", {"op": "active", "id": pt, "active": True})
            # wrong DAV passwords lock only the DRIVE, never the web login
            bad = {"Authorization": "Basic " + b64.b64encode(b"poppy:nope").decode()}
            for _ in range(9):
                client.request("PROPFIND", "/dav/", headers={**bad, "Depth": "0"})
            eq(login("poppy", "poppys-own-pw-9").status_code, 200,
               "a stale Finder mount cannot lock the person out of the app")
        finally:
            (fileserver.R2_ACCOUNT_ID, fileserver.R2_ACCESS_KEY_ID, fileserver.R2_SECRET_ACCESS_KEY,
             fileserver._files_s3_client) = saved
            webdav._dav_auth_cache.clear(); webdav._dav_fail_cache.clear()
            fileserver._files_mem = None
            try:
                os.remove(fileserver.FILES_PATH)
            except FileNotFoundError:
                pass
    with_accounts(go)

@test
def t_audit_must_change_blocks_the_app_until_chosen():
    def go():
        ensure_auth()
        owen, starter = make_user("Owen", "owen")
        sess = login("owen", starter).json()["session"]
        eq(post_s(sess, "/api/files/tree", {}).status_code, 401,
           "a starter password opens nothing but the password screen")
        eq(post_s(sess, "/api/auth/password", {"current": starter, "new": "owens-own-pw-1"}).status_code,
           200, "except the change-password route")
        sess2 = login("owen", "owens-own-pw-1").json()["session"]
        eq(post_s(sess2, "/api/files/tree", {}).status_code, 200, "then everything opens")
    with_accounts(go)

@test
def t_audit_demoting_a_clocked_in_parttime_closes_the_shift():
    def go():
        ensure_auth()
        pt, starter = make_user("Poppy", "poppy", role="parttime")
        sess = login("poppy", starter).json()["session"]
        post_s(sess, "/api/auth/password", {"current": starter, "new": "poppys-own-pw-9"})
        sess = login("poppy", "poppys-own-pw-9").json()["session"]
        post_s(sess, "/api/work/clock", {"op": "in"})
        post("/api/team/user", {"op": "role", "id": pt, "role": "member"})
        b = post("/api/work/board", {}).json()
        eq(len(b["open"]), 0, "no open session hangs after the demotion")
        ok(any(s.get("corrected") for s in b["sessions"]), "it was closed as a correction")
    with_accounts(go)

@test
def t_files_preview_is_inline_typed_and_only_for_safe_types():
    def go(fake):
        up = post("/api/files/upload-url", {"name": "proof.png", "size": 10}).json()
        key = up["url"].split("?")[0].replace("https://fake-r2.test/", "")
        fake.objects[key] = 10
        post("/api/files/complete", {"id": up["id"]})
        r = post("/api/files/download-url", {"id": up["id"], "preview": True})
        eq(r.status_code, 200, r.text)
        eq(r.json()["type"], "image/png")
        p = fake.presigns[-1]
        ok(p["ResponseContentDisposition"].startswith("inline"), "served inline for the preview")
        eq(p["ResponseContentType"], "image/png", "with the extension's type, not the claim")
        up2 = post("/api/files/upload-url", {"name": "notes.txt", "size": 5}).json()
        k2 = up2["url"].split("?")[0].replace("https://fake-r2.test/", "")
        fake.objects[k2] = 5
        post("/api/files/complete", {"id": up2["id"]})
        eq(post("/api/files/download-url", {"id": up2["id"], "preview": True}).status_code, 400,
           "unsafe types never serve inline")
        r3 = post("/api/files/download-url", {"id": up2["id"]})
        ok(fake.presigns[-1]["ResponseContentDisposition"].startswith("attachment"),
           "plain downloads stay attachments")
        eq(r3.status_code, 200)
    with_files(go)

@test
def t_files_same_name_upload_replaces_never_duplicates():
    def go(fake):
        a = post("/api/files/upload-url", {"name": "proof.pdf", "size": 10}).json()
        ka = a["url"].split("?")[0].replace("https://fake-r2.test/", "")
        fake.objects[ka] = 10
        post("/api/files/complete", {"id": a["id"]})
        b = post("/api/files/upload-url", {"name": "Proof.PDF", "size": 12}).json()
        ok(b["replaces"], "the second upload knows it is a replacement")
        kb = b["url"].split("?")[0].replace("https://fake-r2.test/", "")
        fake.objects[kb] = 12
        st = post("/api/files/complete", {"id": b["id"]}).json()["store"]
        active = [v for v in st["files"].values() if v["name"].lower() == "proof.pdf"]
        eq(len(active), 1, "one live file with that name, never two")
        eq(active[0]["size"], 12, "and it is the new one")
        eq(len(st["trash"]), 1, "the old version waits in the trash")
    with_files(go)

@test
def t_files_bulk_ops_and_empty_trash():
    def go(fake):
        folder = post("/api/files/folder", {"op": "add", "name": "Jobs"}).json()["id"]
        ids = []
        for n in ("a.pdf", "b.pdf", "c.pdf"):
            up = post("/api/files/upload-url", {"name": n, "size": 5}).json()
            k = up["url"].split("?")[0].replace("https://fake-r2.test/", "")
            fake.objects[k] = 5
            post("/api/files/complete", {"id": up["id"]})
            ids.append(up["id"])
        r = post("/api/files/file", {"op": "move", "ids": ids[:2], "folder_id": folder})
        eq(r.status_code, 200, r.text)
        st = r.json()["store"]
        eq(sum(1 for v in st["files"].values() if v["folder_id"] == folder), 2, "two moved together")
        r2 = post("/api/files/file", {"op": "trash", "ids": ids})
        eq(r2.status_code, 200, r2.text)
        eq(len(r2.json()["store"]["trash"]), 3, "all three in the trash at once")
        r3 = post("/api/files/file", {"op": "empty_trash"})
        eq(r3.status_code, 200, r3.text)
        st3 = r3.json()["store"]
        eq(st3["trash"], [], "the trash is empty")
        eq(st3["used"], 0, "and the space is free")
        d = fileserver._load_files()
        eq(len(d["doomed"]), 3, "the bytes wait for the reaper, never a route")
        eq(post("/api/files/file", {"op": "empty_trash"}).status_code, 400,
           "emptying an empty trash says so")
    with_files(go)

@test
def t_files_preview_host_is_allowed_to_frame():
    def go(fake):
        csp = client.get("/?shop=test-store.myshopify.com").headers.get("content-security-policy", "")
        frame = csp.split("frame-src", 1)[1].split(";")[0]
        ok("https://acct.r2.cloudflarestorage.com" in frame,
           "the bucket may render in the preview frame: " + frame)
    with_files(go)

@test
def t_dav_refusals_explain_themselves_and_caches_die_with_the_password():
    def go():
        ensure_auth()
        fake = FakeS3()
        saved = (fileserver.R2_ACCOUNT_ID, fileserver.R2_ACCESS_KEY_ID, fileserver.R2_SECRET_ACCESS_KEY,
                 fileserver._files_s3_client)
        fileserver.R2_ACCOUNT_ID = fileserver.R2_ACCESS_KEY_ID = fileserver.R2_SECRET_ACCESS_KEY = "acct"
        fileserver._files_s3_client = fake
        webdav._dav_auth_cache.clear(); webdav._dav_fail_cache.clear()
        fileserver._files_mem = None
        try:
            os.remove(fileserver.FILES_PATH)
        except FileNotFoundError:
            pass
        try:
            import base64 as b64
            owen, starter = make_user("Owen", "owen")
            # a starter-password mount attempt leaves an admin-readable reason
            a0 = {"Authorization": "Basic " + b64.b64encode(f"owen:{starter}".encode()).decode()}
            eq(client.request("PROPFIND", "/dav/", headers={**a0, "Depth": "0"}).status_code, 401)
            ev = post("/api/team/board", {}).json()["events"]
            ok(any(e["action"] == "drive refused" and "not chosen their own password" in e["detail"]
                   for e in ev), "the refusal reason reaches the ledger")
            # ...and the Finder retry storm writes one line, not hundreds
            for _ in range(4):
                client.request("PROPFIND", "/dav/", headers={**a0, "Depth": "0"})
            ev2 = post("/api/team/board", {}).json()["events"]
            eq(sum(1 for e in ev2 if e["action"] == "drive refused"), 1, "throttled to one line")
            # choose a real password; the drive opens and caches the credential
            s0 = login("owen", starter).json()["session"]
            post_s(s0, "/api/auth/password", {"current": starter, "new": "owens-own-pw-1"})
            s1 = login("owen", "owens-own-pw-1").json()["session"]
            a1 = {"Authorization": "Basic " + b64.b64encode(("owen:" + drive_pw(s1)).encode()).decode()}
            eq(client.request("PROPFIND", "/dav/", headers={**a1, "Depth": "0"}).status_code, 207)
            # change the password again: the OLD credential must die at once
            post_s(s1, "/api/auth/password", {"current": "owens-own-pw-1", "new": "owens-own-pw-2"})
            eq(client.request("PROPFIND", "/dav/", headers={**a1, "Depth": "0"}).status_code, 401,
               "the drive's cached credential dies with the password")
            s2 = login("owen", "owens-own-pw-2").json()["session"]
            a2 = {"Authorization": "Basic " + b64.b64encode(("owen:" + drive_pw(s2)).encode()).decode()}
            eq(client.request("PROPFIND", "/dav/", headers={**a2, "Depth": "0"}).status_code, 207,
               "and the new one mounts")
        finally:
            (fileserver.R2_ACCOUNT_ID, fileserver.R2_ACCESS_KEY_ID, fileserver.R2_SECRET_ACCESS_KEY,
             fileserver._files_s3_client) = saved
            webdav._dav_auth_cache.clear(); webdav._dav_fail_cache.clear()
            fileserver._files_mem = None
            try:
                os.remove(fileserver.FILES_PATH)
            except FileNotFoundError:
                pass
    with_accounts(go)

@test
def t_ledger_is_write_behind_but_never_loses_reads():
    def go():
        ensure_auth()
        activity._track(APP_AUTH["master"], "production", "marked made", "#wb-test")
        ev = post("/api/team/board", {}).json()["events"]
        ok(any(e.get("detail") == "#wb-test" for e in ev),
           "an event reads back instantly from memory")
        activity._events_flush()
        rows = json.load(open(activity.ACTIVITY_PATH))["events"]
        ok(any(e.get("detail") == "#wb-test" for e in rows), "and the flush lands it on disk")
    with_accounts(go)

@test
def t_restore_is_master_only_and_round_trips_the_volume():
    def go():
        ensure_auth()
        import base64 as b64
        owen, osess, opw = ready_user("Owen", "owen")
        activity._track(APP_AUTH["master"], "team", "marker", "#before-backup")
        activity._events_flush()
        buf, added = backup._build_backup_zip()
        ok(added > 0, "the backup holds files")
        blob = b64.b64encode(buf.getvalue()).decode()
        eq(post_s(osess, "/api/restore", {"zip": blob}).status_code, 403,
           "an admin below master cannot restore")
        # simulate the fresh-volume world: wipe accounts and ledger
        for p in (team.USERS_PATH, activity.ACTIVITY_PATH):
            os.remove(p)
        team._users_mem = None
        activity._events_mem = None
        activity._events_dirty = False
        APP_AUTH["session"] = APP_AUTH["master"] = ""
        # first-run setup on the "new region", then restore
        r = bare("/api/auth/setup", {"name": "Temp", "username": "temp", "password": "temporary-123",
                                     "setup_code": os.environ["SETUP_CODE"]})
        eq(r.status_code, 200, r.text)
        temp_sess = r.json()["session"]
        rr = post_s(temp_sess, "/api/restore", {"zip": blob})
        eq(rr.status_code, 200, rr.text)
        ok(rr.json()["restored"] >= 2, "the volume files came back")
        eq(post_s(temp_sess, "/api/team/me", {}).status_code, 401,
           "every session died with the restore")
        # the RESTORED register answers, not the temp one
        li = login("cameron", MASTER_PW)
        eq(li.status_code, 200, "the original master signs back in")
        APP_AUTH["session"], APP_AUTH["master"] = li.json()["session"], li.json()["me"]["id"]
        eq(login("owen", opw).status_code, 200, "and so does the team")
        ev = post("/api/team/board", {}).json()["events"]
        ok(any(e.get("detail") == "#before-backup" for e in ev), "history survived the move")
        eq(post("/api/restore", {"zip": "not-base64!!"}).status_code, 400,
           "junk is refused")
    with_accounts(go)

@test
def t_dav_refusals_explain_themselves_and_caches_die_with_the_password():
    def go():
        ensure_auth()
        fake = FakeS3()
        saved = (fileserver.R2_ACCOUNT_ID, fileserver.R2_ACCESS_KEY_ID, fileserver.R2_SECRET_ACCESS_KEY,
                 fileserver._files_s3_client)
        fileserver.R2_ACCOUNT_ID = fileserver.R2_ACCESS_KEY_ID = fileserver.R2_SECRET_ACCESS_KEY = "acct"
        fileserver._files_s3_client = fake
        webdav._dav_auth_cache.clear(); webdav._dav_fail_cache.clear()
        fileserver._files_mem = None
        try:
            os.remove(fileserver.FILES_PATH)
        except FileNotFoundError:
            pass
        try:
            import base64 as b64
            owen, starter = make_user("Owen", "owen")
            a0 = {"Authorization": "Basic " + b64.b64encode(f"owen:{starter}".encode()).decode()}
            eq(client.request("PROPFIND", "/dav/", headers={**a0, "Depth": "0"}).status_code, 401,
               "a starter password never mounts the drive")
            for _ in range(4):
                client.request("PROPFIND", "/dav/", headers={**a0, "Depth": "0"})
            ev = post("/api/team/board", {}).json()["events"]
            reasons = [e for e in ev if e["action"] == "drive refused"]
            eq(len(reasons), 1, "a Finder retry storm writes ONE admin-readable line")
            ok("not chosen their own password" in reasons[0]["detail"], reasons[0]["detail"])
            s0 = login("owen", starter).json()["session"]
            post_s(s0, "/api/auth/password", {"current": starter, "new": "owens-own-pw-1"})
            s1 = login("owen", "owens-own-pw-1").json()["session"]
            a1 = {"Authorization": "Basic " + b64.b64encode(("owen:" + drive_pw(s1)).encode()).decode()}
            eq(client.request("PROPFIND", "/dav/", headers={**a1, "Depth": "0"}).status_code, 207,
               "a chosen password mounts")
            post_s(s1, "/api/auth/password", {"current": "owens-own-pw-1", "new": "owens-own-pw-2"})
            eq(client.request("PROPFIND", "/dav/", headers={**a1, "Depth": "0"}).status_code, 401,
               "the drive's cached credential dies with the password")
            s2 = login("owen", "owens-own-pw-2").json()["session"]
            a2 = {"Authorization": "Basic " + b64.b64encode(("owen:" + drive_pw(s2)).encode()).decode()}
            eq(client.request("PROPFIND", "/dav/", headers={**a2, "Depth": "0"}).status_code, 207,
               "and the new one mounts at once")
        finally:
            (fileserver.R2_ACCOUNT_ID, fileserver.R2_ACCESS_KEY_ID, fileserver.R2_SECRET_ACCESS_KEY,
             fileserver._files_s3_client) = saved
            webdav._dav_auth_cache.clear(); webdav._dav_fail_cache.clear()
            fileserver._files_mem = None
            try:
                os.remove(fileserver.FILES_PATH)
            except FileNotFoundError:
                pass
    with_accounts(go)

@test
def t_restore_never_silently_drops_the_store_it_exists_to_protect():
    """The backup packs files up to BACKUP_FILE_MAX; the restore used its own
    hardcoded 10MB and skipped anything bigger PER FILE, non-fatally - so a CRM
    holding an imported sales history was carried into the zip and thrown away
    on the way out, under a green success toast. The two ceilings are now one,
    and a file over it fails the WHOLE restore rather than part of it."""
    import zipfile as zz, io as iio, base64 as b64
    def zip_of(payload):
        buf = iio.BytesIO()
        with zz.ZipFile(buf, "w", zz.ZIP_DEFLATED) as z:
            z.writestr("volume/crm.json", payload)
        return b64.b64encode(buf.getvalue()).decode()
    def go():
        ensure_auth()
        # Over the OLD ceiling, inside what the backup carries: must restore.
        big = '{"crm": {"deals": {}, "pad": "' + "x" * (11 * 1024 * 1024) + '"}}'
        ok(len(big) > 10 * 1024 * 1024 and len(big) < backup.BACKUP_FILE_MAX)
        r = post("/api/restore", {"zip": zip_of(big)})
        eq(r.status_code, 200, r.text)
        eq(r.json()["restored"], 1, "the store the backup exists for comes BACK")
        eq(r.json().get("skipped") or [], [], "and nothing was quietly dropped")
        # Over the shared ceiling: the whole restore refuses, nothing written.
        saved = backup.BACKUP_FILE_MAX
        backup.BACKUP_FILE_MAX = 1024
        try:
            r2 = post("/api/restore", {"zip": zip_of('{"crm": {"pad": "' + "y" * 5000 + '"}}')})
            eq(r2.status_code, 400, r2.text)
            ok("Nothing has been changed" in r2.json()["error"], r2.text)
        finally:
            backup.BACKUP_FILE_MAX = saved

@test
def t_the_order_webhook_never_writes_the_crm_from_a_thread():
    """The CRM store's whole safety story is one writer at a time: every route
    loads, mutates and writes with no await in between. A worker thread runs
    in genuine parallel and can install a stale snapshot over a won deal, or
    truncate the store through the shared .tmp path."""
    src = copilot_source()
    hook = src[src.index("async def order_webhook"):]
    hook = hook[:hook.index("@mcp.custom_route", 10)]
    ok("run_in_executor" not in hook,
       "the order webhook does not push CRM work onto a thread")
    ok("_crm_link_order_soon" in hook, "it defers onto the event loop instead")
    ok("background.spawn(_crm_link_order_later(" in src,
       "and hands it to background.spawn, which holds a reference so it cannot be collected")

@test
def t_the_bare_token_print_route_demands_a_live_account():
    """With no x-app-session the tab check short-circuited, so a Shopify admin
    denied Production Manager (or switched off entirely) could hand-drive the
    URL, read every order on it and release them to production."""
    src = copilot_source()
    i = src.index("doc_who = _live_uid(request)")
    seg = src[i:i + 400]
    ok("if not doc_who:" in seg, "no session is a refusal, not a skipped check")
    ok("if not _uid_has_tab(doc_who" in seg, "and the tab is checked on its own line")

@test
def t_status_reports_a_write_the_install_cannot_actually_do():
    """Net 30 failed on every account order for days because the app asked
    Shopify for read_payment_terms and never write_payment_terms, and nothing
    anywhere said so. The Connections panel now reads what the INSTALL may do
    and names any write it cannot - and never claims a scope is missing just
    because the lookup itself failed."""
    def go():
        ensure_auth()
        saved = shopify._scope_reader
        try:
            async def missing():
                return {"scopes": ["read_orders", "write_orders"], "error": "",
                        "missing": {"write_payment_terms": "putting an unpaid purchase "
                                                           "order on 30-day terms"}}
            shopify._scope_reader = missing
            sc = post("/api/status", {}).json()["shopify"]["scopes"]
            ok(sc["checked"], sc)
            ok("write_payment_terms" in sc["missing"], sc)
            async def granted():
                return {"scopes": ["write_payment_terms"], "error": "", "missing": {}}
            shopify._scope_reader = granted
            sc2 = post("/api/status", {}).json()["shopify"]["scopes"]
            eq(sc2["missing"], {}, "a granted install reports nothing missing")
            ok(sc2["checked"])
            async def broken():
                return {"scopes": [], "error": "Shopify answered 503", "missing": {}}
            shopify._scope_reader = broken
            sc3 = post("/api/status", {}).json()["shopify"]["scopes"]
            eq(sc3["missing"], {}, "a failed lookup is UNKNOWN, never 'missing'")
            ok(not sc3["checked"] and sc3["error"], sc3)
        finally:
            shopify._scope_reader = saved
    with_accounts(go)

@test
def t_updates_show_the_running_release_and_take_requests():
    """Release notes ship WITH the release (a repo file), so the panel always
    describes the code that is running. Requests are open to everyone signed
    in - a part-timer notices gaps the master never sees - but triage is
    admin-only."""
    def go():
        ensure_auth()
        import json as _j
        # A changelog exactly as the repo ships one.
        cl = SCRATCH + "/changelog.json"
        with open(cl, "w", encoding="utf-8") as fh:
            _j.dump({"releases": [
                {"date": "2026-08-24", "title": "CRM week", "items": [
                    {"kind": "added", "text": "Deals carry their email history."},
                    {"kind": "fixed", "text": "Apostrophes read as apostrophes."}]},
                {"date": "2026-08-01", "items": [{"kind": "improved", "text": "Faster board."}]},
                {"date": "bad", "items": []}]}, fh)
        saved = updates.CHANGELOG_PATH
        updates.CHANGELOG_PATH = cl
        updates._changelog_cache["mtime"] = None
        try:
            r = post("/api/updates", {}).json()
            eq([x["date"] for x in r["releases"]], ["2026-08-24", "2026-08-01"],
               "newest first, and a malformed entry is skipped rather than fatal")
            eq(r["version"]["latest"], "2026-08-24", "the version line names the running release")
            eq(len(r["releases"][0]["items"]), 2)
            # Anyone signed in may ask; the ask lands and is attributed.
            uid, sess, _pw = ready_user("Poppy", "poppy9", role="parttime")
            a = post_s(sess, "/api/updates", {"op": "request", "title": "Bigger print button",
                                              "detail": "hard to hit on the tablet"})
            eq(a.status_code, 200, a.text)
            listed = post("/api/updates", {}).json()["requests"]
            eq(listed[0]["title"], "Bigger print button")
            eq(listed[0]["by"], uid, "attributed to whoever asked")
            eq(listed[0]["state"], "open")
            eq(post_s(sess, "/api/updates", {"op": "request", "title": ""}).status_code, 400,
               "a request needs a one-line title")
            # Triage is admin+; a part-timer cannot move it.
            rid = listed[0]["id"]
            eq(post_s(sess, "/api/updates", {"op": "state", "id": rid, "state": "shipped"}).status_code,
               403, "triage is not everyone's")
            eq(post("/api/updates", {"op": "state", "id": rid, "state": "nonsense"}).status_code, 400)
            post("/api/updates", {"op": "state", "id": rid, "state": "planned", "note": "next week"})
            after = post("/api/updates", {}).json()["requests"][0]
            eq(after["state"], "planned")
            eq(after["note"], "next week")
        finally:
            updates.CHANGELOG_PATH = saved
            updates._changelog_cache["mtime"] = None
    with_accounts(go)

@test
def t_the_release_notes_are_the_repos_own():
    """The release notes ship with the code: by default they are the
    repository's data/changelog.json. A default built one folder down (as a
    path from __file__ is once its code moves into gizmo/) finds no file, and
    a missing changelog is shown as no notes at all, without a word."""
    import json as _j
    ok(os.environ.get("CHANGELOG_PATH") is None, "the default is what is read here")
    repo = os.path.join(HERE, "data", "changelog.json")
    ok(os.path.exists(updates.CHANGELOG_PATH) and os.path.samefile(updates.CHANGELOG_PATH, repo),
       "the default is the repository's changelog: " + updates.CHANGELOG_PATH)
    updates._changelog_cache["mtime"] = None
    notes = updates._load_changelog()
    eq([r.get("title") for r in notes], [r.get("title") for r in _j.load(open(repo, encoding="utf-8"))["releases"]],
       "and the notes loaded are its releases")

@test
def t_the_backup_carries_the_repos_data():
    """The backup carries the repository's data folder (the size sheets, the
    rulings, the changelog) under repo-data/, beside the volume. A folder
    built one level down (as a path from __file__ is once its code moves into
    gizmo/) does not exist, and the backup skips a missing folder without a
    word."""
    import io as _io, zipfile as _zf
    repo = os.path.join(HERE, "data")
    want = sorted("repo-data/" + n for n in os.listdir(repo)
                  if os.path.isfile(os.path.join(repo, n)) and n.lower().endswith((".json", ".jsonl", ".csv", ".bak")))
    ok(len(want) >= 4, "the repository has data files to carry: " + str(want))
    buf, _added = backup._build_backup_zip()
    names = _zf.ZipFile(_io.BytesIO(buf.getvalue()) if hasattr(buf, "getvalue") else buf).namelist()
    eq([n for n in want if n not in names], [], "every one of them is in the backup")

@test
def t_updates_survive_a_missing_or_broken_changelog():
    """Notes are notes: a missing or corrupt file costs the panel, never the app."""
    saved = updates.CHANGELOG_PATH
    updates._changelog_cache["mtime"] = None
    try:
        updates.CHANGELOG_PATH = SCRATCH + "/no-such-changelog.json"
        eq(updates._load_changelog(), [])
        bad = SCRATCH + "/broken-changelog.json"
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        updates.CHANGELOG_PATH = bad
        updates._changelog_cache["mtime"] = None
        eq(updates._load_changelog(), [], "a corrupt file is empty notes, not a 500")
    finally:
        updates.CHANGELOG_PATH = saved
        updates._changelog_cache["mtime"] = None

@test
def t_backup_is_exhaustive_by_construction():
    """Every store path the app defines must be reachable by the backup, or
    stand on the deliberate exclusion list. A new store added outside the
    backup's reach fails HERE, not during a migration. The paths are read from
    copilot.py and every module split out of it: walking copilot.py alone, a
    store stopped being checked the moment its area moved."""
    import importlib
    data_dir = os.path.dirname(scheduler.SCHEDULE_PATH)
    excluded = {os.path.basename(desk.WO_SECRET_PATH),
                os.path.basename(team.SESSIONS_PATH)}
    misses, checked, seen = [], set(), set()
    repo_data = os.path.join(os.path.dirname(copilot.__file__), "data")
    for rel in COPILOT_FILES:
        mod = importlib.import_module(rel[:-3].replace("/", "."))
        for name, val in sorted(vars(mod).items()):
            if not name.endswith("_PATH") or name.startswith("_"):
                continue
            checked.add(name)
            if not isinstance(val, str) or not val or (name, val) in seen:
                continue
            seen.add((name, val))
            base = os.path.basename(val)
            if base in excluded:
                continue
            in_data_top = os.path.dirname(val) == data_dir
            in_labels = os.path.dirname(val) == desk.DISPATCH_LABELS_DIR
            in_repo = os.path.dirname(val) == repo_data   # ships with the code AND in the zip
            good_ext = base.lower().endswith((".json", ".jsonl", ".csv", ".bak"))
            if not ((in_data_top or in_labels or in_repo) and good_ext):
                misses.append(f"{name} -> {val}")
    ok(size_list.GOBO_SIZES_LIVE.lower().endswith(".csv")
       and os.path.dirname(size_list.GOBO_SIZES_LIVE) == data_dir,
       "the live size sheet is inside the backup's reach")
    eq(misses, [], "stores the backup would MISS: " + "; ".join(misses))
    moved = {"DISPATCH_STATE_PATH", "USERS_PATH", "CRM_PATH", "MAILBOX_PATH", "FILES_PATH", "PRIVACY_LOG_PATH",
             "LOANS_PATH", "WORK_PATH", "PRODUCTION_STATE_PATH", "MEMORY_PATH", "SKILLS_PATH", "KNOWLEDGE_PATH"}
    eq(sorted(moved - checked), [], "the stores of the areas moved out of copilot.py are checked too")

@test
def t_backup_carries_labels_and_restore_returns_them():
    def go():
        ensure_auth()
        os.makedirs(desk.DISPATCH_LABELS_DIR, exist_ok=True)
        lp = os.path.join(desk.DISPATCH_LABELS_DIR, "104239.json")
        with open(lp, "w") as fh:
            json.dump({"label": "keep-me"}, fh)
        try:
            import base64 as b64
            import zipfile as zz
            import io as iio
            buf, added = backup._build_backup_zip()
            names = zz.ZipFile(iio.BytesIO(buf.getvalue())).namelist()
            ok("volume-labels/104239.json" in names, "dispatch labels ride in the backup")
            blob = b64.b64encode(buf.getvalue()).decode()
            chk = post("/api/restore", {"zip": blob, "check": True})
            eq(chk.status_code, 200, chk.text)
            j = chk.json()
            ok(j.get("check") and "104239.json" in j["would_restore"],
               "the dry run names the label file")
            ok("users.json" in j["would_restore"], "and the register")
            os.remove(lp)
            r = post("/api/restore", {"zip": blob})
            eq(r.status_code, 200, r.text)
            ok("104239.json" in r.json()["files"], "the real restore lists it")
            eq(json.load(open(lp))["label"], "keep-me", "and the label file is back")
        finally:
            try:
                os.remove(lp)
            except FileNotFoundError:
                pass
    with_accounts(go)

@test
def t_backup_manifest_and_restore_clock_normalisation():
    def go():
        ensure_auth()
        fake = FakeS3()
        saved = (fileserver.R2_ACCOUNT_ID, fileserver.R2_ACCESS_KEY_ID, fileserver.R2_SECRET_ACCESS_KEY,
                 fileserver._files_s3_client)
        fileserver.R2_ACCOUNT_ID = fileserver.R2_ACCESS_KEY_ID = fileserver.R2_SECRET_ACCESS_KEY = "acct"
        fileserver._files_s3_client = fake
        fileserver._files_mem = None
        try:
            os.remove(fileserver.FILES_PATH)
        except FileNotFoundError:
            pass
        jsonstore._poisoned_stores.discard(fileserver.FILES_PATH)
        try:
            import base64 as b64
            import zipfile as zz
            import io as iio
            # a mid-flight upload and an old trash entry, photographed by a backup
            up = post("/api/files/upload-url", {"name": "mid-flight.pdf", "size": 10}).json()
            k1 = up["url"].split("?")[0].replace("https://fake-r2.test/", "")
            fake.objects[k1] = 10
            done = post("/api/files/upload-url", {"name": "old-trash.pdf", "size": 5}).json()
            k2 = done["url"].split("?")[0].replace("https://fake-r2.test/", "")
            fake.objects[k2] = 5
            post("/api/files/complete", {"id": done["id"]})
            post("/api/files/file", {"op": "trash", "id": done["id"]})
            d = fileserver._load_files()
            d["files"][up["id"]]["created_at"] = "2026-08-01T00:00:00+00:00"   # "days old" pending
            d["files"][done["id"]]["trashed_at"] = "2026-07-01T00:00:00+00:00" # "expired" trash
            d["doomed"] = ["ghost/stale-key.pdf"]
            fileserver._write_files(d)
            buf, _ = backup._build_backup_zip()
            man = json.loads(zz.ZipFile(iio.BytesIO(buf.getvalue())).read("manifest.json"))
            ok(man.get("built_at", "").startswith("20"), "the backup names its build time")
            ok(any(i["name"] == "volume/files.json" for i in man["included"]),
               "and lists what it holds")
            blob = b64.b64encode(buf.getvalue()).decode()
            chk = post("/api/restore", {"zip": blob, "check": True}).json()
            ok(chk.get("backup_built_at", "").startswith("20"),
               "the dry run shows the backup's age before anything is written")
            ok(all(n != "manifest.json" for n in chk["would_restore"]),
               "the manifest itself is never restored")
            r = post("/api/restore", {"zip": blob})
            eq(r.status_code, 200, r.text)
            # sign back in (restore drops sessions) and check the clocks
            APP_AUTH["session"] = ""
            fd = fileserver._load_files()
            mid = fd["files"][up["id"]]
            eq(mid["status"], "trashed", "a photographed mid-flight upload lands in the trash")
            ok(mid["trashed_at"].startswith("2026-08-19") or mid["trashed_at"] > "2026-08-19",
               "with a fresh 30-day clock, so the sweep cannot eat its bytes")
            old = fd["files"][done["id"]]
            ok(old["trashed_at"] > "2026-08-01", "expired trash gets a fresh clock too")
            eq(fd["doomed"], [], "and a restored doomed list never deletes anything")
            fileserver._files_tick()
            ok(k1 in fake.objects and k2 in fake.objects,
               "the reaper touched nothing after the restore")
        finally:
            (fileserver.R2_ACCOUNT_ID, fileserver.R2_ACCESS_KEY_ID, fileserver.R2_SECRET_ACCESS_KEY,
             fileserver._files_s3_client) = saved
            fileserver._files_mem = None
            try:
                os.remove(fileserver.FILES_PATH)
            except FileNotFoundError:
                pass
    with_accounts(go)

@test
def t_backup_caps_labels_to_the_newest_sixty():
    def go():
        ensure_auth()
        import zipfile as zz
        import io as iio
        os.makedirs(desk.DISPATCH_LABELS_DIR, exist_ok=True)
        made = []
        try:
            for i in range(65):
                p = os.path.join(desk.DISPATCH_LABELS_DIR, f"ord{i:03d}.json")
                with open(p, "w") as fh:
                    fh.write("{}")
                os.utime(p, (1700000000 + i, 1700000000 + i))
                made.append(p)
            buf, _ = backup._build_backup_zip()
            z = zz.ZipFile(iio.BytesIO(buf.getvalue()))
            labels = [n for n in z.namelist() if n.startswith("volume-labels/")]
            eq(len(labels), 60, "newest sixty ride along")
            ok("volume-labels/ord064.json" in labels, "the newest is kept")
            ok("volume-labels/ord000.json" not in labels, "the oldest is named, not silently lost:")
            man = json.loads(z.read("manifest.json"))
            ok(any(s["name"] == "ord000.json" for s in man["skipped"]),
               "the manifest names what stayed behind")
        finally:
            for p in made:
                try:
                    os.remove(p)
                except FileNotFoundError:
                    pass
    with_accounts(go)

@test
def t_stock_sheet_sends_finals_and_records_the_day():
    def go():
        ensure_auth()
        reset_dispatch(); reset_prod()
        try:
            os.remove(copilot.USAGE_SHEETS_PATH)
        except FileNotFoundError:
            pass
        sent_payloads = []
        async def fake_sheet(payload):
            sent_payloads.append(payload)
            return {"ok": True, "day": payload["day"], "replaced": len(sent_payloads) > 1,
                    "adjustments": 1,
                    "results": [{"family": "Mono", "size": "37.5", "final": 12,
                                 "already_booked": 10, "delta": 2, "status": "adjusted"}]}
        saved = (copilot._zeta_send_sheet, copilot.ZETA_URL, copilot.ZETA_SYNC_TOKEN)
        copilot._zeta_send_sheet = fake_sheet
        copilot.ZETA_URL, copilot.ZETA_SYNC_TOKEN = "https://zeta.test", "tok"
        try:
            def work(sent):
                eq(mark_made(12345, True).status_code, 200)
            with_zeta(work)
            from zoneinfo import ZoneInfo
            import datetime as _dt
            today = _dt.datetime.now(ZoneInfo("Europe/London")).date().isoformat()
            day = post("/api/stock-usage", {"date": today}).json()
            ok(day.get("order_ids"), "the day sheet names its covered orders")
            ok("sent" not in day, "an unsent day carries no sent flag")
            r = post("/api/stock-usage/send", {"date": today, "lines": [
                {"family": "Mono", "size": "37.5", "estimated": 10, "final": 12}]})
            eq(r.status_code, 200, r.text)
            j = r.json()
            ok(j["sent"]["sent_at"], "the send is stamped")
            eq(j["result"]["results"][0]["status"], "adjusted", "per-line statuses come back")
            eq(sent_payloads[0]["order_ids"], [str(i) for i in day["order_ids"]],
               "the covered orders are recomputed server-side, never trusted from the page")
            day2 = post("/api/stock-usage", {"date": today}).json()
            ok(day2.get("sent", {}).get("sent_at"), "the day now says it was sent")
            r2 = post("/api/stock-usage/send", {"date": today, "lines": [
                {"family": "Mono", "size": "37.5", "estimated": 10, "final": 11}]})
            ok(r2.json()["sent"]["replaced"], "a re-send is flagged as a replacement")
            ev = post("/api/team/board", {}).json()["events"]
            ok(any(e["action"] == "sent a stock sheet" for e in ev), "and lands on the ledger")
            bad = post("/api/stock-usage/send", {"date": today, "lines": [
                {"family": "Mono", "size": "37.5", "estimated": 10, "final": "loads"}]})
            eq(bad.status_code, 400, "a non-number final is refused before anything is sent")
        finally:
            (copilot._zeta_send_sheet, copilot.ZETA_URL, copilot.ZETA_SYNC_TOKEN) = saved
            try:
                os.remove(copilot.USAGE_SHEETS_PATH)
            except FileNotFoundError:
                pass
    with_accounts(go)

@test
def t_stock_sheet_failure_records_nothing():
    def go():
        ensure_auth()
        reset_dispatch(); reset_prod()
        async def dead_sheet(payload):
            raise RuntimeError("connection refused")
        saved = (copilot._zeta_send_sheet, copilot.ZETA_URL, copilot.ZETA_SYNC_TOKEN)
        copilot._zeta_send_sheet = dead_sheet
        copilot.ZETA_URL, copilot.ZETA_SYNC_TOKEN = "https://zeta.test", "tok"
        try:
            from zoneinfo import ZoneInfo
            import datetime as _dt
            today = _dt.datetime.now(ZoneInfo("Europe/London")).date().isoformat()
            r = post("/api/stock-usage/send", {"date": today, "lines": [
                {"family": "Mono", "size": "37.5", "estimated": 10, "final": 12}]})
            eq(r.status_code, 502, "a dead stock app is a plain answer")
            ok("Nothing was recorded" in r.json()["error"], r.text)
            day = post("/api/stock-usage", {"date": today}).json()
            ok("sent" not in day, "and no phantom send is recorded")
        finally:
            (copilot._zeta_send_sheet, copilot.ZETA_URL, copilot.ZETA_SYNC_TOKEN) = saved
    with_accounts(go)

@test
def t_custom_shipments_are_findable_and_reprintable_later():
    """A pasted-address shipment has no order to be a row of. Without a list
    of its own the only way back to its label was to reopen the booking
    window, which reads like spending money again."""
    def go():
        ensure_auth()
        orders = desk._load_dispatch()
        orders["adhoc:shipone01"] = {
            "tracking_number": "TRK-AAA", "carrier_label": "DPD",
            "service_name": "Next day", "order_name": "Trade show stand",
            "customer": "Lumen Events", "amount": 12.4, "currency": "GBP",
            "dispatched_at": "2026-08-19T10:00:00Z", "contents": "2 gobos",
        }
        orders["adhoc:shiptwo02"] = {
            "tracking_number": "TRK-BBB", "carrier_label": "UPS",
            "order_name": "Replacement glass", "customer": "Theatre Royal",
            "dispatched_at": "2026-08-18T10:00:00Z",
        }
        orders["991144"] = {"tracking_number": "ORDER-ONE", "order_name": "#1201"}
        desk._write_dispatch(orders)
        desk._save_dispatch_labels("adhoc:shipone01", [{"type": "png", "data": "AAA"}])
        r = post("/api/custom/list", {})
        eq(r.status_code, 200, r.text)
        rows = r.json()["shipments"]
        ids = [x["id"] for x in rows]
        ok("adhoc:shipone01" in ids and "adhoc:shiptwo02" in ids, str(ids))
        ok("991144" not in ids, "a real order is not a pasted-address shipment")
        one = [x for x in rows if x["id"] == "adhoc:shipone01"][0]
        eq(one["reference"], "Trade show stand")
        eq(one["tracking"], "TRK-AAA")
        ok(one["has_label"], "and the desk knows the label is still there")
        two = [x for x in rows if x["id"] == "adhoc:shiptwo02"][0]
        ok(not two["has_label"], "and knows when it is not, before the button fails")
        eq([x["id"] for x in post("/api/custom/list", {"q": "theatre"}).json()["shipments"]],
           ["adhoc:shiptwo02"], "searchable by whoever it went to")
        eq([x["id"] for x in post("/api/custom/list", {"q": "TRK-AAA"}).json()["shipments"]],
           ["adhoc:shipone01"], "or by the tracking number")
        lab = post("/api/dispatch/label", {"id": "adhoc:shipone01"})
        eq(lab.status_code, 200, lab.text)
        eq(lab.json()["labels"][0]["data"], "AAA", "and the label really comes back")
        eq(post("/api/dispatch/label", {"id": "adhoc:shiptwo02"}).status_code, 404,
           "a shipment with no stored label says so plainly")
    with_accounts(go)


