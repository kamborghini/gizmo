# =========================== speed: live timing, compression, the loop ==========
# The first speed pull request after the 2026-10-12 audit. Each test fails on
# the code before it.

def _server_timing(r) -> dict:
    """Server-Timing as {name: milliseconds}."""
    out = {}
    for part in (r.headers.get("server-timing") or "").split(","):
        name, _, dur = part.strip().partition(";dur=")
        if name and dur:
            out[name] = float(dur)
    return out


@test
def t_every_api_answer_says_where_its_time_went():
    """Speed design 4.1. Production's console cannot be read from here, so
    every Shopify and Gmail wait in the 2026-10-12 audit was a model. Every
    API answer now carries its own Server-Timing (the browser's DevTools shows
    it on the Reactor frame), and an admin's Settings shows each route's
    typical and slowest time since the last start."""
    import perf

    def go():
        perf.ROUTES.clear()
        r = post("/api/crm/contact", {"op": "person_add", "name": "Timing Probe",
                                      "emails": ["probe@example.com"]})
        eq(r.status_code, 200, r.text[:200])
        marks = _server_timing(r)
        ok(marks.get("app", 0) > 0, "the whole request is timed: %r" % r.headers.get("server-timing"))
        ok(marks.get("auth", 0) > 0, "and the door: %r" % marks)
        ok(marks.get("store", 0) > 0, "and the save to the store: %r" % marks)
        for i in range(3):
            post("/api/no-such-route-%d" % i, {})
        ok(not [k for k in perf.ROUTES if "no-such-route" in k],
           "a path nobody serves is not remembered, so probing cannot grow the table")
        s = post("/api/status", {})
        eq(s.status_code, 200, s.text[:200])
        rows = {x["route"]: x for x in s.json().get("timing") or []}
        ok("/api/crm/contact" in rows, "an admin's Settings can show it: %s" % sorted(rows)[:6])
        row = rows["/api/crm/contact"]
        ok(row["count"] >= 1 and row["p95"] >= row["p50"] > 0, "typical and slowest: %r" % row)
    with_accounts(go)


@test
def t_time_waiting_on_shopify_is_its_own_mark():
    """The audit's biggest desk wait (X1) is Shopify order sweeps, and how
    long a page waits on Shopify is exactly the number nobody had. Every
    Shopify call goes through server._request, so that is where it is timed."""
    import perf

    class _Resp:
        status_code = 200
        headers = {}

        def json(self):
            return {"shop": {"name": "Test"}}

        def raise_for_status(self):
            pass

    class _Client:
        async def request(self, method, url, **kw):
            await asyncio.sleep(0.02)
            return _Resp()

    async def _hdr():
        return {}

    saved = (server._http, server._headers, server.SHOPIFY_STORE)
    server.SHOPIFY_STORE = server.SHOPIFY_STORE or "test-store"
    server._http, server._headers = (lambda: _Client()), _hdr
    try:
        async def go():
            marks, token = perf.start()
            try:
                await server._request("GET", "shop.json")
            finally:
                perf.stop(token)
            return marks
        marks = run_async(go())
        ok(marks.get("shop", 0) >= 15, "the 20 ms Shopify wait is marked: %r" % marks)
    finally:
        server._http, server._headers, server.SHOPIFY_STORE = saved


@test
def t_big_answers_go_out_as_zstd_compressed_off_the_loop():
    """The audit's S2. gzip at level 6 ran on the event loop for every big
    answer: half of a CRM click, during which nobody else's request moved.
    Python's own zstd at level 3 does the same job six to twelve times
    cheaper and Chrome, which runs the Shopify admin, asks for it; anything
    that does not still gets gzip. A body over 64 KB is compressed in a
    worker thread, so the loop keeps serving everyone else meanwhile."""
    import threading
    import perf
    from compression import zstd as _z
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse as _JR
    from starlette.routing import Route

    big = {"rows": [{"id": i, "name": "Northern Stage Ltd", "note": "gobo %d" % i} for i in range(3000)]}
    mid = {"rows": [{"id": i, "name": "Northern Stage Ltd"} for i in range(100)]}
    seen = {}

    async def _big(request):
        seen["loop"] = threading.get_ident()
        return _JR(big)

    async def _mid(request):
        seen["loop"] = threading.get_ident()
        return _JR(mid)

    app = Starlette(routes=[Route("/big", _big), Route("/mid", _mid)])
    app.add_middleware(server.CompressionMiddleware)
    c = TestClient(app)
    calls = []
    real = perf.compress

    def spy(body, enc, *a, **k):
        calls.append((enc, threading.get_ident()))
        return real(body, enc, *a, **k)

    def decoded(r):
        raw = r.content
        return json.loads(raw if raw[:1] == b"{" else _z.decompress(raw))

    perf.compress = spy
    try:
        r = c.get("/big", headers={"Accept-Encoding": "gzip, deflate, br, zstd"})
        eq(r.headers.get("content-encoding"), "zstd", "a browser that reads zstd is sent zstd")
        eq(decoded(r), big, "and it is the same data on the other side")
        ok(calls and calls[-1][1] != seen["loop"], "a big body is compressed off the loop thread")
        ok("accept-encoding" in (r.headers.get("vary") or "").lower(), "and says what it varies on")
        calls.clear()
        r = c.get("/mid", headers={"Accept-Encoding": "zstd"})
        eq(r.headers.get("content-encoding"), "zstd")
        ok(calls and calls[-1][1] == seen["loop"], "a small one is cheaper to do in place")
        r = c.get("/big", headers={"Accept-Encoding": "gzip, deflate"})
        eq(r.headers.get("content-encoding"), "gzip", "a browser without zstd still gets gzip")
        eq(r.json(), big)
        r = c.get("/big", headers={"Accept-Encoding": "zstd;q=0, gzip"})
        eq(r.headers.get("content-encoding"), "gzip", "zstd refused by q=0 is not sent")
        r = c.get("/big", headers={"Accept-Encoding": "identity"})
        eq(r.headers.get("content-encoding"), None, "and nothing is forced on a client that asks for none")
    finally:
        perf.compress = real


@test
def t_the_page_assets_are_compressed_once_per_build():
    """The audit's D3. app.js and app.css were gzipped again on every
    uncached request, about 50 ms of the event loop per first open, bunched
    after each update when everyone reloads. Each build's assets are now
    packed once, at the strongest levels, away from any request, and served
    as they are."""
    import gzip as _gz
    import perf
    from compression import zstd as _z

    shell, assets = rendering._page_parts()
    h = rendering._asset_hashes["js"]
    blob = assets["js"][1]
    kicked, calls = [], []
    real_soon, real = rendering._pack_assets_soon, perf.compress

    def spy(body, enc, *a, **k):
        calls.append(enc)
        return real(body, enc, *a, **k)

    rendering._asset_packed.clear()
    rendering._pack_assets_soon = lambda: kicked.append(1)
    perf.compress = spy
    try:
        r1 = client.get("/assets/app.js?v=" + h, headers={"Accept-Encoding": "gzip, zstd"})
        eq(r1.status_code, 200)
        ok(kicked, "the first request starts the packing")
        eq(r1.headers.get("content-encoding"), "zstd", "and is still served compressed meanwhile")
        rendering._pack_assets()          # what the background thread runs
        calls.clear()
        r2 = client.get("/assets/app.js?v=" + h, headers={"Accept-Encoding": "gzip, zstd"})
        eq(r2.headers.get("content-encoding"), "zstd")
        eq(calls, [], "served from the pack: nothing is compressed per request")
        # The test client may already have decoded it; the wire size is the
        # Content-Length either way.
        eq(r2.content if r2.content == blob else _z.decompress(r2.content), blob, "the same bytes")
        wire1, wire2 = int(r1.headers["content-length"]), int(r2.headers["content-length"])
        ok(wire2 < wire1, "and smaller than the quick per-request level: %d against %d" % (wire2, wire1))
        ok("max-age=31536000" in (r2.headers.get("cache-control") or ""), "still cached for a year")
        r3 = client.get("/assets/app.js?v=" + h, headers={"Accept-Encoding": "gzip"})
        eq(r3.headers.get("content-encoding"), "gzip")
        eq(calls, [], "the gzip copy is packed too")
        eq(r3.content, blob, "and arrives as the same bytes")
        r4 = client.get("/assets/app.js?v=" + h, headers={"Accept-Encoding": "identity"})
        eq(r4.headers.get("content-encoding"), None)
        eq(r4.content, blob, "a client that asks for none gets the plain file")
        eq(client.get("/assets/app.js?v=000000000000",
                      headers={"Accept-Encoding": "zstd"}).status_code, 404,
           "the hash still has to match")
    finally:
        rendering._pack_assets_soon, perf.compress = real_soon, real


@test
def t_an_attachment_is_measured_off_the_event_loop():
    """The audit's S8. Drafting or sending with an attachment asked storage
    for its size with a blocking call on the event loop, so every other
    request in the app waited for the round trip, and for up to about 45 s
    when storage was slow."""
    import threading
    seen = {}

    class _Body:
        def read(self):
            seen["read"] = threading.get_ident()
            return b"%PDF-1.4 a quote"

    class _S3:
        def get_object(self, Bucket, Key):
            seen["get"] = threading.get_ident()
            return {"Body": _Body()}

    def head(key):
        seen["head"] = threading.get_ident()
        return 16

    def s3():
        seen.setdefault("client", threading.get_ident())
        return _S3()

    saved = (fileserver._files_head, fileserver._files_s3, mail._mail_attachment_ok)
    fileserver._files_head, fileserver._files_s3 = head, s3
    mail._mail_attachment_ok = lambda key, uid: True
    try:
        async def go():
            seen["loop"] = threading.get_ident()
            return await mail._mail_fetch_parts([{"key": "files/u1/quote.pdf", "name": "quote.pdf",
                                                     "type": "application/pdf"}], "u1")
        files, _inline, _total = run_async(go())
        eq(files[0]["data"], b"%PDF-1.4 a quote")
        for k in ("head", "client", "get", "read"):
            ok(seen[k] != seen["loop"], "the %s call ran off the event loop" % k)
    finally:
        fileserver._files_head, fileserver._files_s3, mail._mail_attachment_ok = saved


def _capture_spawn():
    """Swap background.spawn for a recorder. Returns (coroutines, restore)."""
    got, saved = [], background.spawn

    def spawn(coro):
        got.append(coro)
        return True
    background.spawn = spawn

    def restore():
        background.spawn = saved
        for c in got:
            c.close()
    return got, restore


@test
def t_the_inbox_answers_from_memory_and_syncs_behind():
    """The audit's X10. A board read synced Gmail inline whenever the
    picture was over two minutes old: after every deploy, and on every open
    and 60 s poll while Gmail was failing, each waiting up to 25 s per call
    before the board it already held was shown. It now answers from what it
    holds and starts one sync behind, at most once a minute. Refresh still
    syncs while the person waits."""
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        mail._load_mail()["synced_at"] = "2026-01-01T00:00:00+00:00"
        inline = []

        async def fake_sync(force=False):
            inline.append(force)
            return ""
        saved_sync = mail._mail_sync_now
        mail._mail_sync_now = fake_sync
        mail._mail_bg_sync["t"] = 0.0
        mail._mail_last_force["t"] = 0.0
        got, restore = _capture_spawn()
        try:
            r = post("/api/mail/board", {})
            eq(r.status_code, 200, r.text[:200])
            eq(inline, [], "the answer did not wait for Gmail")
            eq([c.cr_code.co_name for c in got], ["fake_sync"], "one sync was started behind it")
            ok(any(t["id"] == "t1" for t in r.json()["threads"]), "and the board it holds was shown")
            post("/api/mail/board", {})
            eq(len(got), 1, "a second read within the minute starts no second sync")
            r = post("/api/mail/board", {"force": True})
            eq(r.status_code, 200)
            eq(inline, [True], "Refresh still syncs while the person waits")
        finally:
            restore()
            mail._mail_sync_now = saved_sync
    with_mail(go)


@test
def t_opening_and_claiming_email_do_not_wait_for_gmail():
    """The audit's X10 and S4. Opening an unread email waited for Gmail to
    mark it read and a whole-mailbox save before the window could open, and
    every claim, assign and state change waited for Gmail to relabel the
    thread over a fresh connection. Both now happen after the answer: the
    ownership is still on disk first, Gmail second, and the relabel waits
    for any sync that is running so two passes never interleave on one
    thread."""
    def go():
        ensure_auth()
        _uid, sess, _ = ready_user("Ann", "ann")
        _gm.save_connection("rt-test", MBOX)
        _seed_thread("t1")
        mail._load_mail()["threads"]["t1"]["unread"] = True
        calls = []

        async def modify(tid, add=None, remove=None):
            calls.append(("modify", tid, tuple(add or ()), tuple(remove or ())))

        async def ensure(name, known):
            calls.append(("ensure", name))
            known[name] = "L-" + name
            return known[name]
        saved = (_gm.modify_thread, _gm.ensure_label, mail._mail_lock)
        _gm.modify_thread, _gm.ensure_label = modify, ensure
        got, restore = _capture_spawn()
        try:
            r = post_s(sess, "/api/mail/thread", {"id": "t1"})
            eq(r.status_code, 200, r.text[:200])
            eq(calls, [], "the email opened without waiting for Gmail")
            eq(len(got), 1, "marking it read was started behind")
            run_async(got.pop())
            eq(calls, [("modify", "t1", (), ("UNREAD",))], "Gmail is told it was read")
            ok(not mail._load_mail()["threads"]["t1"]["unread"], "and the board follows")
            with open(mail.MAILBOX_PATH, encoding="utf-8") as fh:
                ok(not json.load(fh)["mailbox"]["threads"]["t1"]["unread"], "on disk too")
            calls.clear()
            r = post_s(sess, "/api/mail/claim", {"id": "t1"})
            eq(r.status_code, 200, r.text[:200])
            eq(calls, [], "the claim answered before Gmail was asked")
            with open(mail.MAILBOX_PATH, encoding="utf-8") as fh:
                ok(json.load(fh)["mailbox"]["threads"]["t1"].get("owner"), "and was on disk first")
            eq(len(got), 1, "the relabel was started behind")
            mail._mail_lock = asyncio.Lock()     # a fresh lock for this test's own loop

            async def held():
                await mail._mail_lock.acquire()
                job = asyncio.ensure_future(got.pop())
                await asyncio.sleep(0.05)
                waited = not calls
                mail._mail_lock.release()
                await job
                return waited
            ok(run_async(held()), "the relabel waits for a sync that is running")
            ok(("ensure", "Copilot/Ann") in calls, "and then labels the thread: %r" % calls)
            t = mail._load_mail()["threads"]["t1"]
            eq(t.get("gmail_label"), "Copilot/Ann")
            with open(mail.MAILBOX_PATH, encoding="utf-8") as fh:
                eq(json.load(fh)["mailbox"]["threads"]["t1"].get("gmail_label"), "Copilot/Ann",
                   "and the label reached the disk")
        finally:
            restore()
            _gm.modify_thread, _gm.ensure_label, mail._mail_lock = saved
    with_mail(go)


