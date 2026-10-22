# ---------------------------------------------------------------------------
# Audit batch 5: ambiguous writes, a long print run, and two unbounded reads
# ---------------------------------------------------------------------------

@test
def t_a_post_is_not_replayed_after_an_ambiguous_failure():
    """A create that succeeds and then loses its response has already happened.
    Re-posting it is how one shipment becomes two."""
    import httpx as _hx
    calls = []

    class _Resp:
        status_code = 503
        headers = {}
        text = "gateway"

        def json(self):
            return {}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def request(self, method, url, **kw):
            calls.append(method)
            if method == "GET":
                return _Resp()
            raise _hx.TimeoutException("lost")

    saved_client, saved_hdr = server._http, server._headers
    saved_store = server.SHOPIFY_STORE
    server.SHOPIFY_STORE = server.SHOPIFY_STORE or "test-store"

    async def _hdr():
        return {}

    # Patch the pooled-client seam, not httpx itself: the client is built once
    # and held, so replacing the class after that changes nothing.
    server._http, server._headers = (lambda: _Client()), _hdr
    try:
        try:
            run_async(server._request("POST", "fulfillments.json", body={"x": 1}))
        except _hx.TimeoutException:
            pass
        eq(len([c for c in calls if c == "POST"]), 1, "the POST was tried exactly once")
        calls.clear()
        try:
            run_async(server._request("GET", "orders.json"))
        except Exception:
            pass
        ok(len(calls) > 1, "while a GET still retries: %d attempts" % len(calls))
    finally:
        server._http, server._headers = saved_client, saved_hdr
        server.SHOPIFY_STORE = saved_store


@test
def t_a_lost_fulfillment_response_is_checked_not_guessed():
    """If the write landed, the customer already has their tracking email.
    Reporting failure reverts the tag and leaves the order in the queue - the
    worse of the two wrong answers."""
    src = open(os.path.join(HERE, "server.py"), encoding="utf-8").read()
    fn = src.split("async def create_order_fulfillment")[1].split("\nasync def ")[0]
    ok("_already_landed" in fn, "an ambiguous failure asks Shopify what happened")
    ok("httpx.TimeoutException" in fn, "including a timeout, not just an HTTP status")
    ok(fn.index("fulfillment_orders.json") < fn.index("_already_landed"),
       "and it compares against the fulfillment orders it tried")


@test
def t_a_long_print_run_answers_the_browser_and_paces_the_rest():
    """Each release is a tag GET+PUT plus up to three GraphQL calls. Sixty of
    them inline outlives the browser, which then rolls back its printed stamps
    while the server keeps releasing - the team's view and Shopify disagree."""
    def go():
        ensure_auth()
        reset_prod()
        ids = list(range(12345, 12345 + 20))
        r = post("/api/production-state", {"op": "printed", "ids": ids})
        eq(r.status_code, 200, r.text[:140])
        j = r.json()
        eq(j["queued"], len(ids) - mail.RELEASE_INLINE_MAX,
           "the tail is handed to a background pass")
        ok(mail.RELEASE_INLINE_MAX < 100, "and the inline part is bounded")
    with_accounts(go)


@test
def t_a_deal_only_shows_its_own_correspondence():
    """Gmail groups a forward or a cc into whatever thread it lands in, so
    matching any sender in a thread put another customer's whole conversation
    into this deal's history."""
    def go():
        store = mail._load_mail()
        store["threads"] = {
            "ours": {"id": "ours", "subject": "Your gobo order", "from_email": "sarah@venue.com",
                     "state": "done", "last_at": "2026-08-01T10:00:00+00:00", "messages": []},
            "theirs": {"id": "theirs", "subject": "Unrelated quote", "from_email": "bob@other.com",
                       "state": "done", "last_at": "2026-08-02T10:00:00+00:00",
                       "messages": [{"id": "m1", "from_email": "bob@other.com"},
                                    {"id": "m2", "from_email": "sarah@venue.com"}]},
        }
        d = {"persons": {"p1": {"id": "p1", "emails": ["sarah@venue.com"]}}}
        rows = salesdesk._crm_deal_threads(d, {"person_id": "p1"})
        eq([r["id"] for r in rows], ["ours"],
           "only the thread whose correspondent is this person")
    with_mail(go)


@test
def t_the_mail_board_does_not_ship_two_years_of_finished_mail():
    """The board is polled every 60 seconds by every open client, and the
    store holds up to 6,000 threads."""
    def go():
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        store = mail._load_mail()
        old = (_dt.now(_tz.utc) - _td(days=400)).isoformat()
        new = _dt.now(_tz.utc).isoformat()
        store["threads"] = {
            "old": {"id": "old", "state": "done", "done_at": old, "last_at": old, "messages": []},
            "new": {"id": "new", "state": "done", "done_at": new, "last_at": new, "messages": []},
            "live": {"id": "live", "state": "waiting", "last_at": old, "messages": []},
        }
        ids = {r["id"] for r in mail._mail_board_shape(store, window=True)}
        ok("old" not in ids, "a thread closed 400 days ago is not on the board")
        ok("new" in ids and "live" in ids,
           "recent work and anything still open both stay: %s" % ids)
        allids = {r["id"] for r in mail._mail_board_shape(store)}
        eq(allids, {"old", "new", "live"}, "search still sees everything")
    with_mail(go)


@test
def t_the_pre_import_snapshot_does_not_block_the_event_loop():
    """It deflates the whole data volume. Inline, the process stops serving -
    including the order webhook, which Shopify gives 5 seconds."""
    src = copilot_source()
    seg = src.split("The one irreversible moment gets a snapshot")[1][:400]
    ok("to_thread" in seg, "the pre-import snapshot runs off the loop: " + seg[:160])


