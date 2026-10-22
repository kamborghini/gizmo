# =========================== speed: the Inbox, lighter =========================
# The fifth speed pull request (the 2026-10-12 audit, S6 and X9).

@test
def t_an_unchanged_inbox_board_is_not_sent_again():
    """Each open Inbox asks for the whole board every minute: about 940 KB, 140
    KB on the wire, with 3,000 threads, built, compressed and sent to find
    that, most minutes, only the time of the last sync moved. The board now
    comes with a revision, a fingerprint of everything in it except that
    time; the page sends it back and an unchanged board answers {same: true}
    with the new time alone. The fingerprint is of what THIS person is sent,
    and a page with no revision (one open from before this update) gets the
    whole board."""
    def go():
        ensure_auth()
        _seed_thread("t1")
        b = post("/api/mail/board", {}).json()
        ok(b.get("rev") and isinstance(b.get("threads"), list), "the board comes with its revision")
        mail._load_mail()["synced_at"] = "2026-10-12T09:00:00+00:00"     # the minute's sync
        eq(post("/api/mail/board", {"rev": b["rev"]}).json(),
           {"same": True, "rev": b["rev"], "synced_at": "2026-10-12T09:00:00+00:00"},
           "only the time of the sync moved: that is all that is sent")
        ok("threads" in post("/api/mail/board", {}).json(), "an older page still gets the board")
        mail._load_mail()["sync_error"] = "Gmail is having a moment"
        e = post("/api/mail/board", {"rev": b["rev"]}).json()
        ok("threads" in e and e["sync_error"], "a sync error is part of the board, so it is sent")
        mail._load_mail()["sync_error"] = ""
        post("/api/mail/note", {"id": "t1", "text": "chasing the courier"})
        m = post("/api/mail/board", {"rev": b["rev"]}).json()
        ok("threads" in m and m["rev"] != b["rev"], "a board that moved is sent, with its new revision")
        _uid, sess, _ = ready_user("Ann", "ann")
        a = post_s(sess, "/api/mail/board", {"rev": m["rev"]}).json()
        ok("threads" in a and a["rev"] != m["rev"], "a revision is of what this person is sent, not someone else's")
    with_mail(go)


class _CountingHttpx(_RoutedHttpx):
    """A module's httpx that counts the clients it makes."""
    def __init__(self, handler):
        super().__init__(handler)
        self.made = 0

    def AsyncClient(self, *a, **k):
        self.made += 1
        return super().AsyncClient(*a, **k)


def _with_gmail_wire(handler, fn):
    saved = (_gm.httpx, _gm._token)

    async def _tok(acct=_gm.SALES):
        return "test-access-token"
    fake = _CountingHttpx(handler)
    _gm.httpx, _gm._token = fake, _tok
    _gm._pool_drop()
    try:
        fn(fake)
    finally:
        _gm.httpx, _gm._token = saved
        _gm._pool_drop()


@test
def t_gmail_calls_share_one_connection():
    """Every Gmail call built a client of its own: a new connection and TLS
    handshake (Shopify measured 89 ms fresh against 29 ms pooled before its
    calls were pooled) and about 3 ms of the server's one thread for the SSL
    context, 5 to 45 times a minute for the mail loop alone. Gmail calls now
    share one client, made inside the running loop and made again for a new
    one."""
    def go(fake):
        async def three():
            for _ in range(3):
                await _gm._call("GET", "threads")
        run(three())
        eq(fake.made, 1, "three calls, one client")
        other = asyncio.new_event_loop()
        try:
            other.run_until_complete(_gm._call("GET", "threads"))
        finally:
            other.close()
        eq(fake.made, 2, "another loop gets its own")
    _with_gmail_wire(lambda r: _httpx.Response(200, json={"threads": []}), go)


@test
def t_a_dropped_gmail_connection_is_retried_but_an_email_is_never_sent_twice():
    """A pooled connection can be dropped by Google between calls, the one
    failure a fresh connection never had. A call whose connection never
    opened sent nothing, so it is tried again, a send included. A call that
    failed after it may have arrived is tried again only when it changes
    nothing (a read): a send is never sent twice."""
    for method, path, fail, want_calls, raises in (
            ("GET", "threads", "connect", 2, False),
            ("POST", "messages/send", "connect", 2, False),
            ("GET", "threads", "dropped", 2, False),
            ("POST", "messages/send", "dropped", 1, True)):
        seen = []

        def handler(request, fail=fail, seen=seen):
            seen.append(request.method)
            if len(seen) == 1:
                if fail == "connect":
                    raise _httpx.ConnectError("connection refused", request=request)
                raise _httpx.RemoteProtocolError("Server disconnected without sending a response.", request=request)
            return _httpx.Response(200, json={"id": "m1"})

        def go(fake, method=method, path=path, seen=seen, want_calls=want_calls, raises=raises, fail=fail):
            try:
                out = run(_gm._call(method, path, body={} if method == "POST" else None))
                ok(not raises and out == {"id": "m1"}, f"{method} {path} after {fail}: answered")
            except Exception as e:
                ok(raises, f"{method} {path} after {fail} raised {type(e).__name__}: {e}")
            eq(len(seen), want_calls, f"{method} {path} after {fail}: asked {want_calls} time(s)")
        _with_gmail_wire(handler, go)


