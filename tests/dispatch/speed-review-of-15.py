# ---- review of #15 --------------------------------------------------------

@test
def t_only_a_signed_in_request_sees_or_counts_its_timing():
    """Review of #15 (SERVER1, COMPAT1, COMPAT3). The header went on every
    /api/ answer. A wrong-password sign-in for a real name saves a failure
    count (a store mark) and one for a made-up name saves nothing, so the two
    vague 401s differed: a clean yes or no on whether a username exists,
    undoing the sign-in's levelling. And refused requests were counted, so
    anyone could wash a route's real times out of Settings. Only a request
    that passed the door with a live session now gets the header or counts."""
    import perf

    def go():
        ensure_auth()
        ready_user("Ruth", "ruth")
        perf.ROUTES.clear()
        h = {"Authorization": "Bearer " + tok()}
        for p in (gate._rl_hits, gate._rl_global, team._login_hits):
            p.clear()
        real = client.post("/api/auth/login", json={"username": "ruth", "password": "wrong-password-1"}, headers=h)
        fake = client.post("/api/auth/login", json={"username": "nobody-here", "password": "wrong-password-1"},
                           headers=h)
        eq((real.status_code, fake.status_code), (401, 401))
        eq(real.headers.get("server-timing"), None, "a sign-in answer carries no breakdown")
        eq(fake.headers.get("server-timing"), None)
        names = lambda r: sorted(k for k in r.headers.keys() if k not in ("content-length", "date"))
        eq(names(real), names(fake), "and the two answers carry the same headers")
        for _ in range(5):
            gate._rl_hits.clear(); gate._rl_global.clear()
            r = client.post("/api/crm/board", json={}, headers=h)     # no session
            eq(r.status_code, 401)
            eq(r.headers.get("server-timing"), None, "a refused request learns nothing from the timing")
        ok("/api/crm/board" not in perf.ROUTES, "and is not counted")
        r = post("/api/crm/board", {})
        ok(_server_timing(r).get("app", 0) > 0, "a signed-in request still gets it")
        ok("/api/crm/board" in perf.ROUTES, "and is counted")
        _uid, msess, _ = ready_user("Mo", "mo")
        eq(post_s(msess, "/api/status", {}).status_code, 403)
        ok("/api/status" not in perf.ROUTES, "a refusal, even signed in, is not a time worth counting")
    with_accounts(go)


@test
def t_a_claude_call_is_timed_and_kept_out_of_the_table():
    """Review of #15 (PAGE3, COMPAT4). Answers that call Claude take seconds
    by design; counted, they filled the Response times row and pinned it at
    Slow for the life of the process, pushing out the desk pages it exists to
    name. Every model call goes through _xcreate, which now marks its time as
    "ai" and keeps its request out of the table."""
    import perf, types
    saved = claude._xcreate_once

    async def fake_once(client, kwargs):
        await asyncio.sleep(0.01)
        return types.SimpleNamespace(stop_reason="end_turn", content=[])
    claude._xcreate_once = fake_once
    try:
        async def go():
            marks, token = perf.start()
            try:
                await claude._xcreate(None, model="claude-test", messages=[], max_tokens=10)
            finally:
                perf.stop(token)
            return marks
        marks = run_async(go())
        ok(marks.get("ai", 0) >= 5, "the model's time is its own mark: %r" % marks)
        ok(marks.get("_skip"), "and the request is kept out of the slowest-routes table")
        eq(perf.header(marks).count("_"), 0, "the flags never reach the header")
    finally:
        claude._xcreate_once = saved


@test
def t_the_slowest_twentieth_is_the_slowest_twentieth():
    """Review of #15 (SERVER2). With 20 samples p95 picked the maximum, so
    Settings said '1 in 20 over X ms' when nothing was over X."""
    import perf
    saved = dict(perf.ROUTES)
    perf.ROUTES.clear()
    try:
        for i in range(1, 21):
            perf.record("/api/x", float(i))
        for i in range(1, 101):
            perf.record("/api/y", float(i))
        rows = {r["route"]: r for r in perf.summary()}
        eq(rows["/api/x"]["p95"], 19.0, "one of twenty is over it")
        eq(rows["/api/y"]["p95"], 95.0, "five of a hundred are over it")
        eq(rows["/api/y"]["p50"], 50.0)
    finally:
        perf.ROUTES.clear()
        perf.ROUTES.update(saved)


@test
def t_a_relabel_steps_aside_for_a_running_sync():
    """Review of #15 (SERVER3). Each click's relabel queued on _mail_lock, so a
    burst of claims during a slow Gmail held the mail loop and anyone's
    Refresh behind every one of them. A relabel now waits briefly for the
    lock and otherwise leaves the thread to the sync's own label catch-up,
    which already runs under the lock and compares the label it wants with
    the one it has."""
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        calls = []

        async def modify(tid, add=None, remove=None):
            calls.append(tid)

        async def ensure(name, known):
            known[name] = "L-" + name
            return known[name]
        saved = (_gm.modify_thread, _gm.ensure_label, mail._mail_lock, mail.MAIL_LABEL_LOCK_WAIT)
        _gm.modify_thread, _gm.ensure_label = modify, ensure
        mail.MAIL_LABEL_LOCK_WAIT = 0.05
        got, restore = _capture_spawn()
        try:
            eq(post_s(sess, "/api/mail/claim", {"id": "t1"}).status_code, 200)
            mail._mail_lock = asyncio.Lock()

            async def busy_sync():
                await mail._mail_lock.acquire()
                try:
                    await got.pop()          # the relabel, while a sync holds the lock
                finally:
                    mail._mail_lock.release()
            t = mail._load_mail()["threads"]["t1"]
            t["label_retry_at"] = time.time() + 400     # an earlier failure's back-off
            t["label_tried_at"] = time.time()
            run_async(busy_sync())
            eq(calls, [], "it did not wait out the sync")
            ok(mail._mail_want_label(t) != (t.get("gmail_label") or ""),
               "so the sync's catch-up sees the label is owed: %r" % t.get("gmail_label"))
            ok("label_retry_at" not in t and t.get("label_tried_at") == 0,
               "and takes it first, back-off or not: %r" % {k: t.get(k) for k in ("label_retry_at", "label_tried_at")})
        finally:
            restore()
            _gm.modify_thread, _gm.ensure_label, mail._mail_lock, mail.MAIL_LABEL_LOCK_WAIT = saved
    with_mail(go)


@test
def t_an_opened_email_reads_as_read_at_once_unless_gmail_refuses():
    """Review of #15 (PAGE4). The board followed only once Gmail confirmed the
    read, so a poll landing between the window opening and Gmail answering
    showed the email unread again after the person had read it. It now reads
    as read at once, and goes back to unread if Gmail refuses."""
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        mail._load_mail()["threads"]["t1"]["unread"] = True

        async def refuse(tid, add=None, remove=None):
            raise _gm.GmailError("backend error")
        saved = _gm.modify_thread
        _gm.modify_thread = refuse
        got, restore = _capture_spawn()
        try:
            eq(post_s(sess, "/api/mail/thread", {"id": "t1"}).status_code, 200)
            rows = {t["id"]: t for t in post_s(sess, "/api/mail/board", {}).json()["threads"]}
            eq(rows["t1"]["unread"], False, "read as soon as it is opened")
            run_async(got.pop(0))
            eq(mail._load_mail()["threads"]["t1"]["unread"], True, "and unread again when Gmail refuses")
        finally:
            restore()
            _gm.modify_thread = saved
    with_mail(go)


@test
def t_a_read_on_open_never_outlives_what_gmail_says():
    """The re-check of #15's fixes (PAGE4). Three edges of reading on open:
    a mark-read Gmail never answered left the board saying read; the put-back
    after a refusal was never saved, so a store written in between kept the
    read on disk; and Mark unread pressed while the mark-read was still at
    Gmail was undone by it, though that is how somebody undoes an accidental
    open."""
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        mail._load_mail()["threads"]["t1"]["unread"] = True
        calls = []

        async def modify(tid, add=None, remove=None):
            calls.append((tuple(add or ()), tuple(remove or ())))
        saved = (_gm.modify_thread, mail._mail_set_unread)
        got, restore = _capture_spawn()
        try:
            # Gmail never answers: put back, and saved even though another
            # writer saved the optimistic read in between.
            async def silent(store, ids, unread):
                return {"changed": 0, "failed": 0}
            mail._mail_set_unread = silent
            eq(post_s(sess, "/api/mail/thread", {"id": "t1"}).status_code, 200)
            mail._write_mail(mail._load_mail())          # another writer, mid-flight
            run_async(got.pop(0))
            eq(mail._load_mail()["threads"]["t1"]["unread"], True, "unanswered is not confirmed")
            with open(mail.MAILBOX_PATH, encoding="utf-8") as fh:
                eq(json.load(fh)["mailbox"]["threads"]["t1"]["unread"], True, "and the disk says so too")
            # Mark unread pressed while the mark-read is still to run: it wins.
            mail._mail_set_unread = saved[1]
            _gm.modify_thread = modify
            eq(post_s(sess, "/api/mail/thread", {"id": "t1"}).status_code, 200)
            eq(post_s(sess, "/api/mail/read", {"id": "t1", "unread": True}).status_code, 200)
            calls.clear()
            run_async(got.pop(0))
            eq(calls, [], "the late mark-read stands down")
            eq(mail._load_mail()["threads"]["t1"]["unread"], True, "and the email stays unread, as asked")
        finally:
            restore()
            _gm.modify_thread, mail._mail_set_unread = saved
    with_mail(go)


def _written_off(e):
    """The sweep wrote this finding off as gone."""
    return any("No longer detected" in h.get("note", "") for h in e.get("history") or [])


def _left_as_it_was(stores, xid, before, why):
    """An open finding a sweep did not see go: still open, nothing written."""
    e = stores["store"]["exceptions"][xid]
    ok(not e.get("stale") and not _written_off(e), why + ": %s" % e["history"][-1:])
    eq(e["status"], before["status"], why)
    eq(e["history"], before["history"], why + ": and nothing written on its history")

