@test
def t_the_forecast_job_reads_the_store_through_four_fixed_reads():
    """R-C1. The forecast job held Reactor's client id and secret to mint its
    own Admin API token, and that secret signs every webhook. It now asks
    Reactor, with the token it already holds, and Reactor runs one of four
    fixed read-only queries: nothing the job sends becomes query text except
    a date, a bulk operation id and a page cursor, each checked first."""
    import ast
    ensure_auth()
    saved = (forecasting.FORECAST_INGEST_TOKEN, server._request)
    sent = []
    reply = {"v": None}

    async def fake_request(method, path, params=None, body=None, _retried=False, idempotent=None):
        sent.append({"path": path, "body": body, "idempotent": idempotent})
        return reply["v"]
    try:
        forecasting.FORECAST_INGEST_TOKEN = ""
        eq(client.post("/hooks/forecast/shopify", json={"op": "products"}).status_code, 503,
           "no secret configured: off")
        forecasting.FORECAST_INGEST_TOKEN = "forecast-secret-for-tests"
        eq(client.post("/hooks/forecast/shopify", json={"op": "products"},
                       headers={"X-Forecast-Token": "wrong"}).status_code, 401, "a wrong token is refused")
        server._request = fake_request
        h = {"X-Forecast-Token": "forecast-secret-for-tests"}

        def ask(body, data=None):
            reply["v"] = data
            sent.clear()
            return client.post("/hooks/forecast/shopify", json=body, headers=h)
        r = ask({"op": "bulk_start", "since": "2024-04-01"},
                {"data": {"bulkOperationRunQuery": {"bulkOperation": {"id": "gid://shopify/BulkOperation/5"},
                                                    "userErrors": []}}})
        eq(r.status_code, 200, r.text)
        eq(r.json()["data"]["bulkOperation"]["id"], "gid://shopify/BulkOperation/5",
           "answered in the shape the job's own store answers in")
        ok("bulkOperationRunQuery" in sent[0]["body"]["query"], sent)
        ok('created_at:>=2024-04-01' in sent[0]["body"]["variables"]["q"], sent)
        eq(sent[0]["idempotent"], False, "a bulk start is not repeated after an ambiguous failure")
        r = ask({"op": "bulk_status", "id": "gid://shopify/BulkOperation/5"},
                {"data": {"node": {"status": "COMPLETED", "url": "https://x/y"}}})
        eq(r.json()["data"]["status"], "COMPLETED")
        eq(sent[0]["idempotent"], True, "a read may be retried")
        r = ask({"op": "refunds", "since": "2024-04-01", "after": "eyJsYXN0X2lkIjoxfQ=="},
                {"data": {"orders": {"nodes": [], "pageInfo": {"hasNextPage": False}}}})
        eq(r.status_code, 200, r.text)
        ok("financial_status:refunded" in sent[0]["body"]["variables"]["q"], sent)
        r = ask({"op": "products"}, {"data": {"products": {"edges": [], "pageInfo": {"hasNextPage": False}}}})
        eq(r.status_code, 200, r.text)
        # Anything else is refused before Shopify is asked.
        for bad in ({"op": "orders_with_addresses"}, {"op": "bulk_start"},
                    {"op": "bulk_start", "since": '2024-01-01") { id } customers { edges { node { email } } } #'},
                    {"op": "bulk_status", "id": "gid://shopify/Customer/1"},
                    {"op": "products", "after": "abc def"},
                    {"op": "products", "after": {"$ne": 1}}):
            r = ask(bad)
            eq(r.status_code, 400, bad)
            eq(sent, [], "and Shopify is never asked: %r" % (bad,))
        r = ask({"op": "products"}, {"errors": [{"message": "Throttled"}]})
        eq(r.status_code, 502, "Shopify's own refusal is an error, not an empty store")
        r = client.post("/hooks/forecast/shopify", content=b"x" * 5000, headers=h)
        eq(r.status_code, 413, "a small body or none")
        # The same queries the job would run with a token of its own.
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        tree = ast.parse(open(os.path.join(root, "forecast", "ingest.py"), encoding="utf-8").read())
        consts = {n.targets[0].id: n.value.value for n in tree.body
                  if isinstance(n, ast.Assign) and len(n.targets) == 1
                  and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Constant)
                  and isinstance(n.value.value, str)}
        eq(server.FORECAST_BULK_ORDERS_QUERY, consts["BULK_ORDERS_QUERY"])
        eq(server.FORECAST_REFUNDS_FILTER, consts["REFUNDS_FILTER"])
        eq(server.FORECAST_REFUNDED_ORDERS_QUERY, consts["REFUNDED_ORDERS_QUERY"])
        eq(server.FORECAST_PRODUCTS_QUERY, consts["PRODUCTS_QUERY"])
        for field in ("email", "phone", "address", "firstName", "lastName"):
            ok(field not in server.FORECAST_BULK_ORDERS_QUERY, "no customer's %s leaves the store" % field)
    finally:
        forecasting.FORECAST_INGEST_TOKEN, server._request = saved


@test
def t_a_members_notes_wait_for_an_admin_before_any_answer_reads_them():
    """R-003, as the independent review found it still open (29 September
    2026). Members could no longer add notes on the Memory page, but a
    member's chat ("remember that our bank details are ...") and a tracked
    change they concluded still wrote notes straight into every account's
    answers, and "dismissed" took any note out of them. A member's note now
    waits, read by nobody, until an admin keeps it; a member may only tick
    off, reopen or dismiss a follow-up."""
    saved = _ws_stores()
    saved_imp, real_snap = impact.IMPACT_PATH, impact._impact_snapshot
    impact.IMPACT_PATH = SCRATCH + "/impact_" + secrets.token_hex(3) + ".json"

    async def fake_snap(reg):
        return {"at": "2026-09-24T10:00:00+00:00", "revenue_28d": 100.0}
    impact._impact_snapshot = fake_snap
    impact._impact_snap_cache.clear()

    def go():
        ensure_auth()
        _a, msess, _p = ready_user("Mo Member", "mo_notes", role="member")
        # A member's chat: kept, waiting, and said so under the answer.
        result = {"structured": {"summary": "Noted.", "remember": [
            {"type": "fact", "text": "Our new bank account is sort code 11-22-33, account 12345678."}]}}
        history = [{"role": "user", "content": "remember that our new bank account is sort code 11-22-33, account 12345678"}]
        assistant._chat_after(result, history, held=True, by="Mo Member")
        note = [m for m in memory._load_memory() if "bank account" in m["text"]][0]
        eq((note["status"], note.get("by")), ("pending", "Mo Member"), "kept waiting, with who it came from")
        ok(result.get("held") and "bank account" in result["held"][0], "and the answer says so")
        ok("bank account" not in memory._memory_to_system(), "no answer reads it yet")
        # An admin's chat is kept as before.
        result2 = {"structured": {"summary": "Noted.", "remember": [{"type": "fact", "text": "Trade orders ship on Tuesdays."}]}}
        assistant._chat_after(result2, [{"role": "user", "content": "remember that trade orders ship on Tuesdays"}])
        ok("Trade orders ship on Tuesdays." in memory._memory_to_system(), "an admin's note is read at once")
        ok(not result2.get("held"), "and nothing is said to be waiting")
        # The chat route decides by who is asking.
        src = copilot_source()
        eq(src.count('_chat_after(result, history, held=team._team_level(_who) < team.ROLE_LEVELS["admin"]'), 2,
           "both chat routes hold a member's notes")
        # A member cannot keep it, nor dismiss someone else's fact.
        pid = note["id"]
        fact = [m for m in memory._load_memory() if m["text"] == "Trade orders ship on Tuesdays."][0]
        eq(post_s(msess, "/api/memory", {"op": "set_status", "id": pid, "status": "open"}).status_code, 403,
           "a member cannot keep their own waiting note")
        eq(post_s(msess, "/api/memory", {"op": "set_status", "id": fact["id"], "status": "dismissed"}).status_code, 403,
           "nor take an admin's note out of every answer")
        ok("Trade orders ship on Tuesdays." in memory._memory_to_system(), "which is still read")
        # A follow-up is theirs to tick off, reopen or dismiss.
        memory._add_memories([{"type": "followup", "text": "Call Stage Co about the loan unit"}])
        fu = [m for m in memory._load_memory() if m["type"] == "followup"][0]
        for st in ("done", "open", "dismissed"):
            eq(post_s(msess, "/api/memory", {"op": "set_status", "id": fu["id"], "status": st}).status_code, 200, st)
        # An admin keeps the waiting note, and from then on it is read.
        r = post("/api/memory", {"op": "set_status", "id": pid, "status": "open"})
        eq(r.status_code, 200, r.text)
        ok("bank account" in memory._memory_to_system(), "kept by an admin, it is read")
        ok(any(e.get("action") == "kept a note waiting for an admin" for e in activity._load_events()[-5:]),
           "and the ledger says who kept it")
        # A tracked change a member concludes leaves a waiting learning.
        item = post_s(msess, "/api/impact", {"op": "add", "text": "Raise the gobo holder price"}).json()["item"]
        eq(post_s(msess, "/api/impact", {"op": "conclude", "id": item["id"]}).status_code, 200)
        learn = [m for m in memory._load_memory() if "gobo holder" in m["text"]]
        eq([(m["type"], m["status"]) for m in learn], [("insight", "pending")], "a member's learning waits too")
        ok("gobo holder" not in memory._memory_to_system(), "and is not read")
        item2 = post("/api/impact", {"op": "add", "text": "Free delivery over 100"}).json()["item"]
        post("/api/impact", {"op": "conclude", "id": item2["id"]})
        ok("Free delivery over 100" in memory._memory_to_system(), "an admin's is read at once")

        # --- What the second, adversarial check found ---
        # An admin concluding a member's change: the learning quotes the
        # member's words, so it waits too, whoever pressed Conclude.
        item3 = post_s(msess, "/api/impact", {"op": "add", "text": "Pay suppliers to sort code 99-88-77"}).json()["item"]
        eq(item3.get("by"), "Mo Member", "a tracked change says who tracked it")
        r = post("/api/impact", {"op": "conclude", "id": item3["id"]})
        eq(r.status_code, 200, r.text)
        ok(r.json().get("held"), "and the page is told it waits")
        ok("99-88-77" not in memory._memory_to_system(), "a member's words wait, even concluded by an admin")
        # A member cannot settle an admin's change, either way.
        item4 = post("/api/impact", {"op": "add", "text": "Raised the trade price list"}).json()["item"]
        for op in ("conclude", "delete"):
            eq(post_s(msess, "/api/impact", {"op": op, "id": item4["id"]}).status_code, 403, op)
        ok(any(x["id"] == item4["id"] and x.get("status") != "concluded" for x in impact._load_impact()),
           "the admin's change is untouched")
        # A member cannot reopen a dismissed follow-up, nor one of their own
        # that an admin never kept.
        memory._add_memories([{"type": "followup", "text": "Chase the Acme invoice"}])
        fu2 = [m for m in memory._load_memory() if m["text"] == "Chase the Acme invoice"][0]
        post("/api/memory", {"op": "set_status", "id": fu2["id"], "status": "dismissed"})
        eq(post_s(msess, "/api/memory", {"op": "set_status", "id": fu2["id"], "status": "open"}).status_code, 403,
           "an admin's dismissal stands")
        memory._add_memories([{"type": "followup", "text": "Pay the new account"}], held=True, by="Mo Member")
        fu3 = [m for m in memory._load_memory() if m["text"] == "Pay the new account"][0]
        post("/api/memory", {"op": "set_status", "id": fu3["id"], "status": "done"})
        eq(post_s(msess, "/api/memory", {"op": "set_status", "id": fu3["id"], "status": "open"}).status_code, 403,
           "a member's note an admin closed without keeping stays closed")
        ok("Pay the new account" not in memory._memory_to_system())
        # An admin saying what a waiting note says keeps it.
        memory._add_memories([{"type": "fact", "text": "Trade orders ship on Mondays."}], held=True, by="Mo Member")
        kept_now: list = []
        memory._add_memories([{"type": "fact", "text": "Trade orders ship on Mondays."}], kept=kept_now)
        eq(kept_now, ["Trade orders ship on Mondays."], "said by an admin, it is kept")
        ok("Trade orders ship on Mondays." in memory._memory_to_system(), "and read")
        # A skill's reading is an admin's to run.
        sk = post("/api/skills", {"op": "add", "title": "Quoting glass", "content": "Glass takes four days."}).json()
        sid = [x for x in sk["skills"] if x["title"] == "Quoting glass"][0]["id"]
        eq(post_s(msess, "/api/skills/read", {"id": sid}).status_code, 403, "a member cannot re-run a skill's reading")
        # The real chat route, as a member: its notes wait.
        async def answer(history, dispatch, tools, model, extra, emit=None, effort=None, deep=False):
            return {"structured": {"summary": "Noted.", "remember": [
                {"type": "fact", "text": "Samples go out second class."}]}}
        real_chat = assistant.run_chat
        assistant.run_chat = answer
        gate._rl_global.clear()
        try:
            r = post_s(msess, "/api/chat", {"message": "remember that samples go out second class"})
            eq(r.status_code, 200, r.text[:200])
            eq(r.json().get("held"), ["Samples go out second class."], "the chat route holds a member's note")
            r = post_s(msess, "/api/chat/stream", {"message": "remember that samples go out second class"})
            ok(r.status_code == 200, r.text[:200])
        finally:
            assistant.run_chat = real_chat
        ok("Samples go out second class." not in memory._memory_to_system(), "and no answer reads it")
    try:
        with_accounts(go)
    finally:
        _ws_restore(saved)
        impact.IMPACT_PATH, impact._impact_snapshot = saved_imp, real_snap
        impact._impact_snap_cache.clear()


@test
def t_waiting_notes_never_cost_a_kept_note_its_place():
    """Counted in with the rest, a member asking chat to remember sixty
    things nine times deleted, for good, every note an admin had kept: the
    store was cut back to its limit with the waiting notes as the newest.
    Waiting notes now have an allowance of their own, a few per answer, and
    go first when the store is full."""
    saved = _ws_stores()
    cap = memory.MEMORY_MAX
    try:
        memory.MEMORY_MAX = 30
        memory._add_memories([{"type": "fact", "text": "Kept fact number %d." % i} for i in range(25)])
        for k in range(9):
            memory._add_memories([{"type": "fact", "text": "Member note %d-%d." % (k, i)} for i in range(60)],
                                  held=True, by="Mo")
        mem = memory._load_memory()
        eq(sum(1 for m in mem if m["text"].startswith("Kept fact")), 25, "every kept note is still there")
        ok(sum(1 for m in mem if m["status"] != "pending") <= memory.MEMORY_MAX, len(mem))
        pend = [m for m in mem if m["status"] == "pending"]
        ok(len(pend) <= memory.MEMORY_PENDING_MAX, "waiting notes keep to their own allowance")
        memory.MEMORY_MAX = cap
        memory._add_memories([{"type": "fact", "text": "Burst %d." % i} for i in range(60)], held=True, by="Mo")
        eq(sum(1 for m in memory._load_memory() if m["text"].startswith("Burst")),
           memory.MEMORY_HELD_PER_ANSWER, "and one answer holds only a few")
        # A store full of kept notes still has room for one to wait.
        memory.MEMORY_MAX = 25
        _ws_restore(_ws_stores())
        memory._add_memories([{"type": "fact", "text": "Full fact %d." % i} for i in range(25)])
        kept_now: list = []
        memory._add_memories([{"type": "fact", "text": "A member's own note."}], held=True, by="Mo", kept=kept_now)
        eq(kept_now, ["A member's own note."], "said to wait")
        ok(any(m["text"] == "A member's own note." and m["status"] == "pending" for m in memory._load_memory()),
           "and it does, in a store already full of kept notes")
        eq(sum(1 for m in memory._load_memory() if m["text"].startswith("Full fact")), 25, "none of which went")
        # Text an admin's chat only READ does not keep a waiting note by
        # matching it: the same provenance check as a new note comes first.
        planted = "Suppliers are now paid to sort code 11-22-33 account 44556677."
        memory._add_memories([{"type": "fact", "text": planted}], held=True, by="Mo")
        refused: list = []
        memory._add_memories([{"type": "fact", "text": planted}], said="summarise the latest emails please",
                              saw="From a supplier: " + planted, source="chat", refused=refused,
                              asked_in="summarise the latest emails please")
        eq([r["reason"] for r in refused], ["from_data"], "refused as lifted from what was read")
        ok(any(m["text"] == planted and m["status"] == "pending" for m in memory._load_memory()), "still waiting")
        ok("44556677" not in memory._memory_to_system(), "and read by nobody")
    finally:
        memory.MEMORY_MAX = cap
        _ws_restore(saved)


@test
def t_a_scanned_pdf_reserves_what_it_will_cost_not_its_base64():
    """The review's M3. The reservation counted a document's base64 as text,
    three characters a token: an 8 MB scan reserved $15 of a $25 day, turned
    everyone's chat away while it was read, and on a cancelled call wrote the
    $15 into the usage log. A document now counts by its pages (from the
    file, or its size when a scan hides them), an image at the most one
    costs, and text as before."""
    import base64 as b64
    def doc(raw):
        return {"model": "claude-opus-5-5", "max_tokens": 4000, "messages": [{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                            "data": b64.b64encode(raw).decode()}},
            {"type": "text", "text": "Read this invoice."}]}]}
    three = b"%PDF-1.4\n" + b"1 0 obj << /Type /Pages >> endobj\n" + b"".join(
        b"%d 0 obj << /Type /Page /Parent 1 0 R >> endobj\n" % i for i in range(2, 5)) + b"x" * 7_000_000
    inp, cost = claude._call_estimate(doc(three))
    eq(inp // claude.PDF_PAGE_TOKENS, 3, "three pages, read from the file, whatever its size")
    scan = b"%PDF-1.5\n" + b"\x00" * 8_000_000
    inp, cost = claude._call_estimate(doc(scan))
    ok(inp <= claude.PDF_MAX_PAGES * claude.PDF_PAGE_TOKENS + 100, "a scan with hidden pages is capped at the page limit")
    ok(cost < 3.0, "an 8 MB scan reserves %.2f, not 15" % cost)
    img = {"model": "claude-opus-5-5", "max_tokens": 100, "messages": [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "A" * 4_000_000}}]}]}
    ok(abs(claude._call_estimate(img)[0] - claude.IMAGE_TOKENS) < 20, "an image at the most one costs, plus its framing")
    text = {"model": "claude-opus-5-5", "max_tokens": 100, "system": "s" * 3000,
            "messages": [{"role": "user", "content": "q" * 3000}]}
    ok(abs(claude._call_estimate(text)[0] - 2000) < 50, "text is three characters a token, as before")


@test
def t_the_webhook_repair_reads_hosts_as_hosts():
    """Found verifying R-C2. Hosts were compared as raw text, so our own
    address with a port or a trailing dot read as foreign and was removed
    with a 'your credentials leaked' email, a staging host given as a full
    address never matched, an address with no host (an event bus) was kept
    and never reported, and a removal was not reported at all when a later
    step of the same repair failed."""
    import server
    saved_req, saved_allow = server._request, set(server.WEBHOOK_ALLOWED_HOSTS)
    subs = [{"id": 1, "topic": "orders/create", "address": "https://app.example.test/webhooks/orders"},
            {"id": 2, "topic": "orders/updated", "address": "https://APP.example.test:443/webhooks/orders"},
            {"id": 3, "topic": "orders/paid", "address": "https://app.example.test./other"},
            {"id": 4, "topic": "orders/updated", "address": "https://staging.example.test/webhooks/orders"},
            {"id": 5, "topic": "orders/create", "address": "arn:aws:events:eu-west-2::event-source/aws.partner/x"},
            {"id": 6, "topic": "orders/create", "address": "https:evil.example/x"},
            {"id": 7, "topic": "customers/redact", "address": "https://elsewhere.example/p"}]
    deleted, fail_create = [], {"on": False}

    async def fake_request(method, path, params=None, body=None, **kw):
        if method == "GET":
            return {"webhooks": subs}
        if method == "DELETE":
            deleted.append(path)
            return {}
        if method == "POST":
            if fail_create["on"]:
                raise RuntimeError("Shopify answered 503")
            return {"webhook": {"id": 99, **body["webhook"]}}
        raise AssertionError(method + " " + path)
    server._request = fake_request
    os.environ["APP_URL"] = "https://app.example.test"
    try:
        server.WEBHOOK_ALLOWED_HOSTS.clear()
        server.WEBHOOK_ALLOWED_HOSTS.add(server._webhook_host("https://staging.example.test/webhooks/orders"))
        res = run(server.ensure_order_webhooks())
        eq(sorted(deleted), ["webhooks/5.json", "webhooks/6.json"],
           "our own host however written, and the allowed staging copy, stay; an address with no host goes")
        eq(len(res["foreign_removed"]), 2, res)
        deleted.clear()
        fail_create["on"] = True
        subs[:] = [{"id": 8, "topic": "orders/create", "address": "https://exfil.example/x"}]
        res = run(server.ensure_order_webhooks())
        eq(res.get("ok"), False, "the recreate failed")
        eq(res.get("foreign_removed"), ["orders/create to exfil.example"], "but what was removed is still said")
        eq(server._webhook_host("Staging.Example.Test."), "staging.example.test", "a bare host, any case")
    finally:
        server._request = saved_req
        server.WEBHOOK_ALLOWED_HOSTS.clear(); server.WEBHOOK_ALLOWED_HOSTS.update(saved_allow)


@test
def t_restoring_the_pre_redact_archive_does_not_erase_again():
    """Found verifying R-C1. The pre-redact archive is taken while the
    erasure is owed and the store is out of reach, and restoring it (its
    whole purpose, after a misfire) brought both back: the next hour either
    erased the restored data again or, the app reinstalled, raised a false
    forged-request alarm. What is owed now, and how long the store has been
    out of reach now, are live state: a restore keeps them as they are."""
    import base64 as b64
    from datetime import datetime, timedelta, timezone
    def go():
        ensure_auth()
        old = (datetime.now(timezone.utc) - timedelta(hours=46)).isoformat()
        privacy._shop_owed_set({"since": old, "tries": 0})
        w = scheduler._load_watch(); w["shopify_down"] = old; scheduler._save_watch(w)
        privacy._redact_hold_write(lambda hs: [{"id": "hbefore", "email": "before@example.com", "received": old}])
        buf, _added = backup._build_backup_zip()
        blob = b64.b64encode(buf.getvalue()).decode()
        privacy._shop_owed_set(None)                     # settled since
        w = scheduler._load_watch(); w.pop("shopify_down", None); scheduler._save_watch(w)
        # Since the backup: the waiting one was stopped (as any settlement is,
        # with a decision recorded), and a new one arrived.
        privacy._privacy_decision("before@example.com", "", "stopped", "Ada")
        privacy._redact_hold_write(lambda hs: [{"id": "hafter", "email": "after@example.com", "received": old}])
        r = post("/api/restore", {"zip": blob})
        eq(r.status_code, 200, r.text[:200])
        eq(privacy._load_privacy_log().get("shop_owed"), None, "nothing owed comes back with the archive")
        eq(scheduler._load_watch().get("shopify_down"), None, "nor the old outage")
        eq([h["id"] for h in privacy._held_requests()], ["hafter"],
           "the customer erasures waiting now stay, and a settled one does not come back")
        privacy._redact_hold_write(lambda hs: [])
        # Evidence since the backup is kept, a data request since it stays,
        # and an erasure confirmed since it is owed again.
        li = login("cameron", MASTER_PW)
        APP_AUTH["session"], APP_AUTH["master"] = li.json()["session"], li.json()["me"]["id"]
        buf, _added = backup._build_backup_zip()
        blob = b64.b64encode(buf.getvalue()).decode()
        privacy._privacy_note("customers/redact", "gone.since@example.com", "", "erased: confirmed by Ada")
        privacy._privacy_decision("gone.since@example.com", "", "erased", "Ada")
        privacy._ask_hold("asked.since@example.com", "")
        r = post("/api/restore", {"zip": blob})
        eq(r.status_code, 200, r.text[:200])
        pl = privacy._load_privacy_log()
        ok(any(e.get("email") == "gone.since@example.com" for e in pl["events"]), "the event since is kept")
        ok(any(a.get("email") == "asked.since@example.com" for a in pl.get("asks") or []), "the data request stays")
        ok(any(p.get("email") == "gone.since@example.com" for p in pl.get("pending") or []),
           "and the erasure confirmed since is owed again, as the restore brought them back")
        li = login("cameron", MASTER_PW)
        APP_AUTH["session"], APP_AUTH["master"] = li.json()["session"], li.json()["me"]["id"]
        # Onto a fresh volume (no live log at all), the backup's waiting requests stay.
        privacy._redact_hold_write(lambda hs: [{"id": "hfresh", "email": "fresh@example.com", "received": old}])
        buf, _added = backup._build_backup_zip()
        blob = b64.b64encode(buf.getvalue()).decode()
        os.remove(privacy.PRIVACY_LOG_PATH)
        jsonstore._json_cache.clear()
        r = post("/api/restore", {"zip": blob})
        eq(r.status_code, 200, r.text[:200])
        eq([h["id"] for h in privacy._held_requests()], ["hfresh"], "nothing waiting is wiped by an empty live log")
        li = login("cameron", MASTER_PW)
        APP_AUTH["session"], APP_AUTH["master"] = li.json()["session"], li.json()["me"]["id"]
        # An erasure confirmed BEFORE the backup was built is not owed again.
        for k in ("pending", "decisions"):
            privacy._redact_hold_write(lambda xs: [], key=k)
        privacy._privacy_decision("before.backup@example.com", "", "erased", "Ada")
        buf, _added = backup._build_backup_zip()
        blob = b64.b64encode(buf.getvalue()).decode()
        r = post("/api/restore", {"zip": blob})
        eq(r.status_code, 200, r.text[:200])
        ok(not any(p.get("email") == "before.backup@example.com" for p in privacy._load_privacy_log().get("pending") or []),
           "an erasure the backup already reflects is not run again")
        li = login("cameron", MASTER_PW)
        APP_AUTH["session"], APP_AUTH["master"] = li.json()["session"], li.json()["me"]["id"]
        privacy._redact_hold_write(lambda hs: [])
        # An unreadable live log is what the restore repairs: the backup's lists stay.
        privacy._redact_hold_write(lambda hs: [{"id": "hin", "email": "in.backup@example.com", "received": old}])
        buf, _added = backup._build_backup_zip()
        blob = b64.b64encode(buf.getvalue()).decode()
        open(privacy.PRIVACY_LOG_PATH, "w").write("{not json")
        jsonstore._json_cache.clear()
        r = post("/api/restore", {"zip": blob})
        eq(r.status_code, 200, r.text[:200])
        eq([h["id"] for h in privacy._held_requests()], ["hin"], "the backup's waiting request is not wiped")
        privacy._redact_hold_write(lambda hs: [])
        for k in ("asks", "decisions", "pending"):
            privacy._redact_hold_write(lambda xs: [], key=k)
        li = login("cameron", MASTER_PW)
        APP_AUTH["session"], APP_AUTH["master"] = li.json()["session"], li.json()["me"]["id"]
    with_accounts(go)


@test
def t_a_signed_customer_redact_waits_for_an_admin():
    """The audit's R-C1, point 2, left open on 29 September and fixed on the
    30th (Cameron: "fix the forged customer redact too"). A customers/redact is
    signed with the app's secret, like every forgery by whoever holds it, and
    one post erased any customer's CRM records and email threads on the spot.
    Nothing checkable tells a forgery from Shopify's own request, and an
    erasure cannot be undone, so each now waits for an admin in Settings,
    Privacy requests, beside what Reactor can tell them: what Shopify says
    about every address the erasure would take (refreshed hourly), how far it
    reaches (worked out when shown, and checked again at the click), and
    whether the same one was stopped before. The master is told at once, in
    the app and by email naming nobody, and reminded daily as the thirty days
    run out. Nothing is erased without an admin."""
    from datetime import datetime, timedelta, timezone
    orderbook._webhook_seen.clear()
    saved = (shopify._customer_checker, background.spawn, scheduler._send_alert_email)
    spawned, sent_mail, queued = [], {"ok": True}, []

    def spawn(coro):
        spawned.append((coro.cr_code.co_name, dict(coro.cr_frame.f_locals)))
        if coro.cr_code.co_name == "_privacy_mail_send":
            queued.append(coro)      # run after the step, so 'mailed' follows what was sent
        else:
            coro.close()
        return True

    def ra(coro):
        out = run_async(coro)
        while queued:
            run_async(queued.pop(0))
        return out

    async def _send_alert_email(subject, lines):
        # Named as the real one, so one spawned directly is counted too.
        spawned.append(("_send_alert_email", {"subject": subject, "lines": lines}))
        return sent_mail["ok"]
    send = _send_alert_email
    live_for = {"addrs": set()}

    async def checker(cid, email):
        return "live" if email in live_for["addrs"] else ("unknown" if email == "unsure@example.com" else "gone")
    background.spawn, shopify._customer_checker, scheduler._send_alert_email = spawn, checker, send
    privacy._redact_hold_said.clear()

    def held():
        return privacy._held_requests()

    def ask(email, cid, delivery):
        raw = json.dumps({"customer": {"id": cid, "email": email},
                          "shop_domain": "test-store.myshopify.com"}).encode()
        return client.post("/webhooks/privacy", content=raw,
                           headers=wh_headers(raw, topic="customers/redact", delivery=delivery))

    def still_there(email):
        return any(email in [str(e).lower() for e in (p.get("emails") or [])]
                   for p in salesdesk._load_crm()["persons"].values())

    def mails():
        return [a for n, a in spawned if n == "_send_alert_email"]

    def go():
        ensure_auth()
        for k in ("held", "stopped", "asks", "decisions"):
            privacy._redact_hold_write(lambda xs: [], key=k)
        jsonstore._write_json_store(scheduler.ALERTS_PATH, None, [])
        _a, msess, _p = ready_user("Mo Member", "mo_priv", role="member")
        _b, asess, _q = ready_user("Ada Admin", "ada_priv", role="admin")
        d = salesdesk._load_crm()
        d["persons"]["pz0"] = {"id": "pz0", "name": "Fay Forged", "emails": ["forged@example.com"]}
        d["persons"]["pz1"] = {"id": "pz1", "name": "Rae Real", "emails": ["real@example.com", "rae@old.example.com"],
                               "phones": ["07700 900123"]}
        d["persons"]["pz2"] = {"id": "pz2", "name": "Rae Real", "emails": ["rae.real@work.example.com"],
                               "phones": ["07700 900123"]}
        d["persons"]["pz3"] = {"id": "pz3", "name": "Val Two", "emails": ["val.old@example.com", "val@example.com"]}
        salesdesk._write_crm(d)
        # Signed, and held: nothing erased, the master told without a name.
        eq(ask("forged@example.com", 991, "cr-1").status_code, 200)
        ok(still_there("forged@example.com"), "nothing is erased on the signature alone")
        eq([h["email"] for h in held()], ["forged@example.com"], "it waits for an admin")
        eq(sum(1 for n, _ in spawned if n == "_redact_hold_check"), 1, "Shopify is asked about the customer")
        ok(any(a.get("metric") == privacy._PRIVACY_ALERT for a in scheduler._load_alerts() if isinstance(a, dict)),
           "the app says so")
        ra(privacy._redact_hold_check(held()[0]["id"]))
        eq(held()[0]["shopify"], "gone", "what Shopify said is kept for the admin")
        ok(mails() and "waiting" in mails()[-1]["subject"], mails())
        ok(not any("forged@example.com" in l for l in mails()[-1]["lines"]), "and the email names nobody")
        ok(held()[0]["mailed"], "marked mailed, as it went")
        eq(ask("forged@example.com", 991, "cr-1b").status_code, 200)
        eq(len(held()), 1, "the same person asked again is one request")
        eq(sum(1 for n, _ in spawned if n == "_redact_hold_check"), 1, "and is not checked again for it")
        # Nothing erases it but an admin, however long it waits.
        old = (datetime.now(timezone.utc) - timedelta(days=29)).isoformat()
        privacy._redact_hold_write(lambda hs: [{**h, "received": old} for h in hs])
        ra(privacy._redact_hold_due())
        ok(still_there("forged@example.com"), "twenty-nine days on, still there")
        # Only an admin sees or settles them.
        eq(post_s(msess, "/api/privacy", {}).status_code, 403, "a member cannot")
        lst = post_s(asess, "/api/privacy", {}).json()
        eq([h["email"] for h in lst["held"]], ["forged@example.com"], "an admin sees it")
        # Stopped: nothing erased, said, remembered.
        spawned.clear()
        r = post_s(asess, "/api/privacy", {"op": "stop", "id": lst["held"][0]["id"]})
        eq(r.status_code, 200, r.text)
        eq((r.json()["held"], r.json()["notice"]), ([], "Stopped. Nothing was erased."), "no longer waiting")
        ok(still_there("forged@example.com"), "and nothing was erased")
        ok(any("stopped" in a["subject"] for a in mails()), mails())
        eq(post_s(asess, "/api/privacy", {"op": "stop", "id": lst["held"][0]["id"]}).status_code, 404,
           "a second admin acting on it finds it gone")
        ok(any(x.get("action") == "stopped" for x in privacy._load_privacy_log().get("decisions") or []),
           "the decision is kept apart from the event log")
        ask("forged@example.com", 991, "cr-1c")
        lst = post_s(asess, "/api/privacy", {}).json()
        ok(lst["held"][0]["stopped_before"], "sent again, it says it was stopped before")
        post_s(asess, "/api/privacy", {"op": "stop", "id": lst["held"][0]["id"]})
        # The advice covers every address the erasure would take.
        live_for["addrs"] = {"val@example.com"}
        ask("val.old@example.com", 0, "cr-v")
        ra(privacy._redact_hold_check(held()[0]["id"]))
        eq(held()[0]["shopify"], "live", "Shopify still has the contact's other address: said")
        post_s(asess, "/api/privacy", {"op": "stop", "id": held()[0]["id"]})
        # How far it reaches is worked out when shown, and checked at the click.
        live_for["addrs"] = set()
        ask("real@example.com", 992, "cr-2")
        h = post_s(asess, "/api/privacy", {}).json()["held"][0]
        eq({k: h["scope"][k] for k in ("contacts", "likely_duplicates", "other_addresses")},
           {"contacts": 2, "likely_duplicates": 1, "other_addresses": 2},
           "two contacts, one only as a likely duplicate, holding two other addresses")
        d = salesdesk._load_crm()
        d["persons"]["pz4"] = {"id": "pz4", "name": "Rae Real", "emails": ["rae3@example.com"], "phones": ["07700 900123"]}
        salesdesk._write_crm(d)
        r = post_s(asess, "/api/privacy", {"op": "erase", "id": h["id"], "reach": h["scope"]["key"]})
        eq(r.status_code, 409, "the CRM changed since it was shown: look again")
        eq(post_s(asess, "/api/privacy", {"op": "erase", "id": h["id"]}).status_code, 409,
           "and without what was shown, nothing is erased")
        ok(still_there("real@example.com"), "and nothing went")
        h = post_s(asess, "/api/privacy", {}).json()["held"][0]
        eq(h["scope"]["contacts"], 3, "shown as it is now")
        r = post_s(asess, "/api/privacy", {"op": "erase", "id": h["id"], "reach": h["scope"]["key"]})
        eq((r.status_code, r.json()["notice"]), (200, "Erased."), r.text[:200])
        ok(not still_there("real@example.com") and not still_there("rae3@example.com"),
           "exactly what was shown went")
        ok(any(x.get("action") == "erased" for x in privacy._load_privacy_log().get("decisions") or []))
        # Shopify cannot be asked: the last answer stands; not asked while it is down.
        ask("unsure@example.com", 993, "cr-3")
        hid = held()[0]["id"]
        privacy._redact_hold_set(hid, shopify="gone", checked_at="2026-09-01T00:00:00+00:00")
        ra(privacy._redact_hold_due())
        eq(held()[0]["shopify"], "gone", "a failed check keeps the last answer")
        calls = []
        async def counting(cid, email):
            calls.append(email)
            return "gone"
        shopify._customer_checker = counting
        ra(privacy._redact_hold_due(check=False))
        eq(calls, [], "Shopify is not asked while it is down")
        shopify._customer_checker = checker
        # Reminded as the thirty days run out, once a day, in the app too.
        privacy._redact_hold_write(lambda hs: [{**x, "received": (datetime.now(timezone.utc) - timedelta(days=22)).isoformat()} for x in hs])
        privacy._redact_hold_said.clear()
        jsonstore._write_json_store(scheduler.ALERTS_PATH, None, [])     # dismissed by someone
        spawned.clear()
        ra(privacy._redact_hold_due())
        ra(privacy._redact_hold_due())
        eq(sum(1 for a in mails() if "still waiting" in a["subject"]), 1, "a reminder, once a day")
        ok(any(a.get("metric") == privacy._PRIVACY_ALERT for a in scheduler._load_alerts() if isinstance(a, dict)),
           "and the notice is back in the app")
        # An email that did not go is not counted as gone.
        post_s(asess, "/api/privacy", {"op": "stop", "id": held()[0]["id"]})
        sent_mail["ok"] = False
        privacy._redact_hold_said.clear()
        ask("nomail@example.com", 994, "cr-4")
        ra(privacy._redact_hold_check(held()[0]["id"]))
        eq(held()[0]["mailed"], False, "no email configured: still to be mailed")
        sent_mail["ok"] = True
        privacy._redact_hold_said.clear()
        ra(privacy._redact_hold_due())
        eq(held()[0]["mailed"], True, "and it goes the next hour")
        post_s(asess, "/api/privacy", {"op": "stop", "id": held()[0]["id"]})
        # The CRM unreadable: its reach is not known, so it is not erased.
        ask("crmdown@example.com", 995, "cr-5")
        jsonstore._poisoned_stores.add(salesdesk.CRM_PATH)
        try:
            h = post_s(asess, "/api/privacy", {}).json()["held"][0]
            ok(h["scope"].get("unreadable"), h)
            eq(post_s(asess, "/api/privacy", {"op": "erase", "id": h["id"], "reach": ""}).status_code, 503)
        finally:
            jsonstore._poisoned_stores.discard(salesdesk.CRM_PATH)
        post_s(asess, "/api/privacy", {"op": "stop", "id": held()[0]["id"]})
        # A request that cannot be recorded is sent back, and the master told.
        good = open(privacy.PRIVACY_LOG_PATH, "rb").read()
        open(privacy.PRIVACY_LOG_PATH, "w").write("{not json")
        jsonstore._json_cache.clear()
        spawned.clear()
        try:
            eq(ask("late2@example.com", 996, "cr-6").status_code, 503, "not recorded: sent again")
            ok("cr-6" not in orderbook._webhook_seen, "and the retry is not taken for a duplicate")
            ok(any("could not record" in a["subject"] for a in mails()), mails())
        finally:
            open(privacy.PRIVACY_LOG_PATH, "wb").write(good)
            jsonstore._json_cache.clear()
            jsonstore._poisoned_stores.discard(privacy.PRIVACY_LOG_PATH)
        # A log whose events are broken keeps what waits.
        ask("kept@example.com", 997, "cr-7")
        pl = privacy._load_privacy_log()
        pl["events"] = "broken"
        jsonstore._write_json_store(privacy.PRIVACY_LOG_PATH, None, pl)
        ok(privacy._held_requests(), "the waiting requests survive a broken event list")
        # A flood past the cap is sent back, and noted.
        cap = privacy.REDACT_HELD_MAX
        privacy.REDACT_HELD_MAX = len(held())
        try:
            eq(ask("one-too-many@example.com", 998, "cr-8").status_code, 503, "past the cap: sent back")
            ok(any(e.get("email") == "one-too-many@example.com" and "not held" in e.get("detail", "")
                   for e in privacy._load_privacy_log()["events"]), "and noted")
        finally:
            privacy.REDACT_HELD_MAX = cap
        # Data requests: their own list, until answered, however old.
        raw = json.dumps({"customer": {"id": 777, "email": "asks@example.com"}}).encode()
        client.post("/webhooks/privacy", content=raw,
                    headers=wh_headers(raw, topic="customers/data_request", delivery="cr-dr"))
        while queued:
            run_async(queued.pop(0))
        privacy._redact_hold_write(lambda xs: [{**a, "received": (datetime.now(timezone.utc) - timedelta(days=61)).isoformat()}
                                               for a in xs], key="asks")
        asks = post_s(asess, "/api/privacy", {}).json()["data_requests"]
        mine = [a for a in asks if a["email"] == "asks@example.com"]
        ok(mine and mine[0]["overdue"] and mine[0]["id"], "sixty-one days on: still listed, and overdue")
        r = post_s(asess, "/api/privacy", {"op": "answered", "id": mine[0]["id"], "email": "asks@example.com"}).json()
        ok(not any(a["email"] == "asks@example.com" for a in r["data_requests"]), "answered, it leaves the list")
        # A long list: the oldest shown, the rest counted; Stop all settles a flood.
        for k in range(3):
            ask("flood%d@example.com" % k, 1100 + k, "cr-fl%d" % k)
        lim = privacy.REDACT_LIST_MAX
        privacy.REDACT_LIST_MAX = 2
        try:
            lst = post_s(asess, "/api/privacy", {}).json()
            eq((len(lst["held"]), lst["held_more"]), (2, len(held()) - 2), "shown in part, the rest counted")
        finally:
            privacy.REDACT_LIST_MAX = lim
        r = post_s(asess, "/api/privacy", {"op": "stop_all"}).json()
        eq(r["held"], [], "every one stopped")
        ok(r["notice"].startswith("Stopped ") and "Nothing was erased" in r["notice"], r["notice"])
        # Data requests past their cap: the newest is sent back, no older one dropped.
        cap = privacy.REDACT_ASKS_MAX
        privacy.REDACT_ASKS_MAX = len(privacy._open_asks()) + 1
        try:
            for k, dl in ((1, 200), (2, 503)):
                raw = json.dumps({"customer": {"id": 800 + k, "email": "ask%d@example.com" % k}}).encode()
                eq(client.post("/webhooks/privacy", content=raw,
                               headers=wh_headers(raw, topic="customers/data_request", delivery="cr-da%d" % k)).status_code,
                   dl, "past the cap, the newest is refused")
        finally:
            privacy.REDACT_ASKS_MAX = cap
        # Damaged records do not lose a request or break the list.
        privacy._redact_hold_write(lambda xs: [{"id": "tz", "email": "naive@example.com",
                                                "received": "2026-09-01T10:00:00"}])
        eq(post_s(asess, "/api/privacy", {}).status_code, 200, "a date with no timezone")
        pl = privacy._load_privacy_log()
        pl["held"], pl["stopped"] = {"not": "a list"}, 7
        jsonstore._write_json_store(privacy.PRIVACY_LOG_PATH, None, pl)
        eq(ask("damaged@example.com", 1200, "cr-dm").status_code, 200)
        eq([h["email"] for h in held()], ["damaged@example.com"], "damaged lists are replaced, the request kept")
        # The hourly tick runs it first, before anything that can fail.
        src = copilot_source()
        tick = src.split("async def _watchdog_tick", 1)[1]
        ok(tick.index("await privacy._redact_hold_due(check=up)") < tick.index("run_label_coverage")
           and tick.index("privacy._redact_retry_pending()") < tick.index("run_label_coverage"),
           "before the size-list check, which failed every hour once")
    try:
        with_accounts(go)
    finally:
        for c in queued:
            c.close()
        shopify._customer_checker, background.spawn, scheduler._send_alert_email = saved
        for k in ("held", "stopped", "asks"):
            privacy._redact_hold_write(lambda xs: [], key=k)
        privacy._redact_hold_said.clear()
        orderbook._webhook_seen.clear()

@test
def t_the_customer_check_calls_only_an_answer_that_found_nobody_gone():
    """What lets a held erasure go ahead. 'gone' is only Shopify answering
    and finding no customer with that id (with an address) or that address;
    an error, a refusal or nothing to ask with is 'unknown', which erases
    nothing."""
    saved = server._request
    answers = []

    async def fake(method, path, params=None, body=None, _retried=False, idempotent=None):
        answers.append(body)
        a = replies.pop(0)
        if isinstance(a, Exception):
            raise a
        return a
    server._request = fake
    try:
        def state(cid, email, *seq):
            replies[:] = list(seq)
            return run_async(server.shopify_customer_state(cid, email))
        replies = []
        def c(addr):
            return {"id": "g", "defaultEmailAddress": {"emailAddress": addr} if addr else None}
        eq(state("555", "jo@example.com", {"data": {"customer": c("jo@example.com"),
                                                     "customers": {"nodes": []}}}), "live", "by id")
        eq(state("555", "jo@example.com", {"data": {"customer": c("else@example.com"),
                                                     "customers": {"nodes": []}}}), "live",
           "an id with someone else's address is for an admin")
        eq(state("555", "jo@example.com", {"data": {"customer": c(None),
                                                     "customers": {"nodes": []}}}), "gone",
           "a record with no address left says nothing")
        eq(state("", "Jo@Example.com", {"data": {"customers": {"nodes": [c("jo@example.com")]}}}),
           "live", "by address, any case")
        eq(state("555", "jo@example.com", {"data": {"customer": None, "customers": {"nodes": [
            c("jo@example.com.au")]}}}), "gone", "a longer address is someone else")
        eq(state("424242", "josé@example.es", {"data": {"customer": None}}), "unknown",
           "an address that cannot be asked about is never called gone")
        eq(state("555", "jo@example.com", {"data": {"customer": None, "customers": {"nodes": [c("jo@example.com")]}},
                                           "errors": [{"message": "Throttled"}]}), "live",
           "a customer found is found, whatever else the reply says")
        eq(state("\u00b2", "jo@example.com", {"data": {"customers": {"nodes": [c("jo@example.com")]}}}), "live",
           "a customer number that is not plain digits does not hide the address check")
        ok("defaultEmailAddress" in json.dumps(answers[-1]), "the field that is not deprecated")
        eq(state("555", "jo@example.com", {"errors": [{"message": "Access denied"}]}), "unknown", "refused: unknown")
        eq(state("555", "jo@example.com", RuntimeError("down")), "unknown", "an outage: unknown")
        eq(state("", "", ), "unknown", "nothing to ask with")
        eq(state("abc", 'x"y@example.com'), "unknown", "nothing safe to ask with")
        ok('email:\"jo@example.com\"' in json.dumps(answers[0]) or "email:\\\"jo@example.com\\\"" in json.dumps(answers[0]),
           answers[0])
    finally:
        server._request = saved


@test
def t_the_erasure_takes_exactly_whom_it_always_took():
    """The duplicate rule now works each contact's words out once (a list of
    waiting requests took minutes); who an erasure takes must not change.
    Checked against the rule as it was, on a CRM built to have namesakes,
    shared numbers, shared switchboards and chains of duplicates."""
    import random
    rnd = random.Random(30)
    names = ["Jo Bloggs", "Sam Hart", "Alex Reed", "Priya Shah"]
    phones = ["07700 900%03d" % i for i in range(6)]
    persons = {}
    for i in range(160):
        persons["p%d" % i] = {"id": "p%d" % i, "name": rnd.choice(names),
                              "emails": ["u%d@example.com" % rnd.randrange(40)] + (["x%d@example.com" % i] if i % 3 else []),
                              "phones": rnd.sample(phones, rnd.randrange(0, 2))}
    d = {"persons": persons}

    def old(addr):
        mine = [k for k, v in persons.items()
                if addr in {str(e).strip().lower() for e in (v.get("emails") or [])}
                or str(v.get("email") or "").strip().lower() == addr]
        for k, v in persons.items():
            if k not in mine and any(privacy._erase_same_person(privacy._erase_words_of(v),
                                                                privacy._erase_words_of(persons[m])) for m in mine):
                mine.append(k)
        return mine
    index = privacy._redact_index(d)
    for n in range(40):
        addr = "u%d@example.com" % n
        eq(privacy._redact_people(d, addr, index)[0], old(addr), addr)
        eq(privacy._redact_people(d, addr)[0], old(addr), addr + " without an index")


@test
def t_a_refused_request_says_why_so_the_page_can_answer_it():
    """A colleague saw a flashing login screen and "asked for too much": a
    stale Shopify embed token (his PC clock) drew a bare 401, the page took
    every 401 as a dead session and reloaded, and the reloads tripped the rate
    window. The door now names the refusal, so the page can fetch a fresh
    token and retry once for a bad token, and only sign out for a dead session."""
    ensure_auth()
    gate._rl_hits.clear(); gate._rl_global.clear()
    r = client.post("/api/status", json={}, headers={"Authorization": "Bearer not-a-token",
                                                      "X-App-Session": APP_AUTH["session"]})
    eq(r.status_code, 401)
    eq(r.json()["reason"], "token", "a rejected embed token says so")
    ok("clock" in r.json()["error"], "and points at the one cause a person can fix at the desk")
    gate._rl_hits.clear(); gate._rl_global.clear()
    r = client.post("/api/status", json={}, headers={"Authorization": "Bearer " + tok()})
    eq(r.status_code, 401)
    eq(r.json()["reason"], "session", "a good token with no app session is a sign-in")
    gate._rl_hits.clear(); gate._rl_global.clear()
    r = client.post("/api/status", json={}, headers={"Authorization": "Bearer " + tok(), "X-App-Session": "stale-session"})
    eq(r.json()["reason"], "session", "and so is a session the app no longer holds")
    ok(set(team.AUTH_REFUSALS) == {"token", "session", "inactive", "must_change"}, "four reasons, each with its own words")

