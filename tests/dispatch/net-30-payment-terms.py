# ---------------------------------------------------------------------------
# NET-30, now that write_payment_terms is actually granted: the paths past the
# permission check have never run against a real store until today.
# ---------------------------------------------------------------------------

def _terms_stub2(current_terms, template_rows=None, errors_on=None, raise_on=None,
                 mutation_errors=None, capture=None, after_write=None):
    """A Shopify that can also answer the ways a real one does when it is
    unhappy: a top-level errors array (which arrives as HTTP 200), a transport
    failure, and a changed order state after a write it never confirmed.

    errors_on / raise_on are keyed by "template" | "read" | "mutate".
    """
    import httpx as _hx
    state = {"wrote": False}

    def _kind(q):
        if "paymentTermsTemplates" in q:
            return "template"
        if q.strip().startswith("query($id"):
            return "read"
        return "mutate"

    async def fake_req(method, path, params=None, body=None, idempotent=None, **kw):
        q = str((body or {}).get("query") or "")
        kind = _kind(q)
        if capture is not None:
            capture.append({"kind": kind, "idempotent": idempotent, "body": body})
        if (raise_on or {}).get(kind):
            if state["wrote"] or kind != "mutate":
                raise (raise_on[kind])
            state["wrote"] = True
            raise (raise_on[kind])
        if (errors_on or {}).get(kind):
            return {"errors": errors_on[kind]}
        if kind == "template":
            rows = template_rows if template_rows is not None else [
                {"id": "gid://shopify/PaymentTermsTemplate/4", "name": "Net 30",
                 "paymentTermsType": "NET", "dueInDays": 30}]
            return {"data": {"paymentTermsTemplates": rows}}
        if kind == "read":
            terms = current_terms
            if state["wrote"] and after_write is not None:
                terms = after_write
            return {"data": {"order": {"createdAt": "2026-08-01T10:00:00Z",
                                       "paymentTerms": terms}}}
        state["wrote"] = True
        key = "paymentTermsUpdate" if "paymentTermsUpdate" in q else "paymentTermsCreate"
        return {"data": {key: {"paymentTerms": {"id": "gid://shopify/PaymentTerms/1"},
                               "userErrors": mutation_errors or []}}}
    return fake_req


@test
def t_a_throttled_answer_is_never_read_as_a_settled_refusal():
    """Shopify answers a throttled GraphQL call with HTTP 200 and an errors
    array, so it never reaches the HTTP retry path. Read as a real answer it
    became "your store has no Net 30 template" - an errand to fix a setting
    that was never wrong - or a bare "Throttled" with no hint to try again."""
    thr = [{"message": "Throttled", "extensions": {"code": "THROTTLED"}}]
    for where in ("template", "read", "mutate"):
        fake = _terms_stub2({"id": "gid://shopify/PaymentTerms/77",
                             "paymentTermsName": "Due on receipt",
                             "paymentTermsType": "RECEIPT", "dueInDays": None},
                            errors_on={where: thr})
        r = _with_terms_stub(fake, lambda _s: run_async(_s.set_order_payment_terms_net30(12345)))
        eq(r.get("reason"), "throttled", "a throttled %s is recognised: %s" % (where, r))
        ok("moment" in r.get("detail", ""), "and says to try again: " + str(r))


@test
def t_a_template_lookup_that_failed_does_not_blame_the_store():
    """paymentTermsTemplates is Shopify's own global list; a merchant cannot
    create or delete Net 30. So "no Net 30 template exists on this store" can
    only ever be reached when it is untrue - and it sent them hunting through
    settings instead of pressing the button again."""
    fake = _terms_stub2(None, errors_on={"template": [
        {"message": "Internal error. Request ID: abc-123"}]})
    r = _with_terms_stub(fake, lambda _s: run_async(_s.set_order_payment_terms_net30(12345)))
    ok(not r["ok"], r)
    ok("abc-123" in r.get("detail", ""), "the real message survives: " + str(r))
    ok("no net 30" not in r.get("detail", "").lower(), "and the store is not blamed: " + str(r))
    # A well-formed answer with no NET/30 row is still reported as such.
    fake2 = _terms_stub2(None, template_rows=[{"id": "gid://shopify/PaymentTermsTemplate/9",
                                               "name": "Due on receipt",
                                               "paymentTermsType": "RECEIPT", "dueInDays": None}])
    r2 = _with_terms_stub(fake2, lambda _s: run_async(_s.set_order_payment_terms_net30(12345)))
    eq(r2.get("reason"), "no_template", "a genuine miss still says so: " + str(r2))


@test
def t_the_terms_reads_are_retried_and_the_writes_are_not():
    """GraphQL travels by POST, which the transport now treats as a write and
    will not repeat after an ambiguous failure. That is right for the mutations
    and wrong for the two queries: repeating a read costs nothing, and losing
    one to a blip failed a release for no reason."""
    seen = []
    fake = _terms_stub2(None, capture=seen)
    _with_terms_stub(fake, lambda _s: run_async(_s.set_order_payment_terms_net30(12345)))
    by_kind = {c["kind"]: c["idempotent"] for c in seen}
    eq(by_kind.get("template"), True, "the template lookup is retryable: %s" % by_kind)
    eq(by_kind.get("read"), True, "so is the order read: %s" % by_kind)
    eq(by_kind.get("mutate"), False, "the mutation is not: %s" % by_kind)


@test
def t_a_lost_answer_after_a_successful_attach_is_not_called_a_failure():
    """The write may well have landed. Reporting a red failure over an order
    that is correctly on 30-day terms is the wrong half of the two wrong
    answers - and the merchant chases an invoice that was never broken."""
    import httpx as _hx
    net30 = {"id": "gid://shopify/PaymentTerms/1", "paymentTermsName": "Net 30",
             "paymentTermsType": "NET", "dueInDays": 30}
    fake = _terms_stub2(None, raise_on={"mutate": _hx.TimeoutException("lost")},
                        after_write=net30)
    r = _with_terms_stub(fake, lambda _s: run_async(_s.set_order_payment_terms_net30(12345)))
    ok(r["ok"] and r.get("verified"), "the order is checked, not guessed: " + str(r))
    # And when the write genuinely did not land, it is still a failure.
    fake2 = _terms_stub2(None, raise_on={"mutate": _hx.TimeoutException("lost")},
                         after_write=None)
    r2 = _with_terms_stub(fake2, lambda _s: run_async(_s.set_order_payment_terms_net30(12345)))
    ok(not r2["ok"] and r2.get("reason") == "timeout", "an honest failure survives: " + str(r2))


@test
def t_a_refused_token_is_not_reported_as_a_missing_scope():
    """A 401 is the token being refused, not a permission the merchant forgot
    to grant. Sending them to add write_payment_terms - which they have - is
    the wrong errand."""
    import httpx as _hx

    class _R:
        status_code = 401
        headers = {}
        text = ""

        def json(self):
            return {}

    err = _hx.HTTPStatusError("401", request=None, response=_R())
    fake = _terms_stub2(None, raise_on={"mutate": err})
    r = _with_terms_stub(fake, lambda _s: run_async(_s.set_order_payment_terms_net30(12345)))
    ok(not r["ok"], r)
    ok("write_payment_terms" not in r.get("detail", ""),
       "it does not blame the scope: " + str(r))
    ok("token" in r.get("detail", "").lower(), "it names the real problem: " + str(r))


@test
def t_a_cancelled_order_is_not_put_on_thirty_day_terms():
    """_sync_order_tags leaves dead orders alone and still answers ok, so the
    release carried on and attached terms to an order that will never be
    invoiced - then reported it as released."""
    def go():
        ensure_auth(); reset_prod()
        saved_w, saved_tags, saved_status = (shopify._payment_terms_writer, ORDER["tags"],
                                             ORDER.get("cancelled_at"))
        calls = []

        async def writer(order_id):
            calls.append(order_id)
            return {"ok": True, "created": True}
        try:
            shopify._payment_terms_writer = writer
            ORDER["tags"] = "Unprocessed, purchase order unpaid"
            ORDER["cancelled_at"] = "2026-08-02T09:00:00Z"
            r = post("/api/production-labels/queue", {"order_id": 12345}).json()
            ok(not calls, "no terms were written to a cancelled order: %s" % calls)
            ok(r.get("terms_ok"), "and it is not reported as a failure: %s" % r)
            ok("cancel" in (r.get("terms_note") or "").lower(),
               "the note says why: %s" % r.get("terms_note"))
        finally:
            shopify._payment_terms_writer, ORDER["tags"] = saved_w, saved_tags
            if saved_status is None:
                ORDER.pop("cancelled_at", None)
            else:
                ORDER["cancelled_at"] = saved_status
    with_accounts(go)


@test
def t_a_batch_names_the_orders_whose_terms_failed():
    """Flattened to one boolean and the first three notes, a print run could
    show a red toast whose text was three success sentences while the order
    that actually failed was never named."""
    def go():
        ensure_auth(); reset_prod()
        saved_w, saved_tags = shopify._payment_terms_writer, ORDER["tags"]
        try:
            ORDER["tags"] = "Unprocessed, purchase order unpaid"

            async def writer(order_id):
                if int(order_id) == 12347:
                    return {"ok": False, "detail": "Shopify refused the terms."}
                return {"ok": True, "created": True}
            shopify._payment_terms_writer = writer
            r = post("/api/production-state",
                     {"op": "printed", "ids": [12345, 12346, 12347]}).json()
            per = {t["order"]: t["ok"] for t in (r.get("terms") or [])}
            eq(len(per), 3, "every account order is reported: %s" % r.get("terms"))
            ok(per.get(12347) is False and per.get(12345) is True, "per order: %s" % per)
            ok(not r["terms_ok"], "the batch is a failure overall")
            ok("refused" in r["terms_note"].lower(),
               "and the summary carries the FAILURE, not three successes: " + r["terms_note"])
        finally:
            shopify._payment_terms_writer, ORDER["tags"] = saved_w, saved_tags
    with_accounts(go)


@test
def t_a_terms_failure_stays_on_the_order_until_it_is_fixed():
    """A toast is gone when the page moves on, and the background half of a big
    print run has no toast at all. The queue row has to carry it."""
    def go():
        ensure_auth(); reset_prod()
        saved_w, saved_tags = shopify._payment_terms_writer, ORDER["tags"]
        try:
            ORDER["tags"] = "Unprocessed, purchase order unpaid"

            async def bad(order_id):
                return {"ok": False, "detail": "Shopify refused the terms."}
            shopify._payment_terms_writer = bad
            post("/api/production-labels/queue", {"order_id": 12345})
            st = production._load_prod_state().get("12345") or {}
            ok(st.get("terms_error"), "the order carries the problem: %s" % st)

            async def good(order_id):
                return {"ok": True, "created": True}
            shopify._payment_terms_writer = good
            post("/api/production-labels/queue", {"order_id": 12345})
            st2 = production._load_prod_state().get("12345") or {}
            ok(not st2.get("terms_error"), "and it clears when the terms attach: %s" % st2)
        finally:
            shopify._payment_terms_writer, ORDER["tags"] = saved_w, saved_tags
    with_accounts(go)


@test
def t_the_background_tail_of_a_print_run_attaches_terms_too():
    """The first orders are released while the browser waits and the rest are
    paced behind it. The tail is a release like any other."""
    def go():
        ensure_auth(); reset_prod()
        saved_w, saved_tags = shopify._payment_terms_writer, ORDER["tags"]
        seen = []
        try:
            ORDER["tags"] = "Unprocessed, purchase order unpaid"

            async def writer(order_id):
                seen.append(int(order_id))
                return {"ok": True, "created": True}
            shopify._payment_terms_writer = writer
            saved_sleep = copilot.asyncio.sleep

            async def no_wait(_s):
                return None
            copilot.asyncio.sleep = no_wait
            try:
                # The registry is only ever handed to _tool_json, which this
                # harness replaces wholesale, so an empty one is honest here.
                run_async(production._release_bg({}, [12345, 12346]))
            finally:
                copilot.asyncio.sleep = saved_sleep
            eq(sorted(seen), [12345, 12346], "every tail order got its terms: %s" % seen)
        finally:
            shopify._payment_terms_writer, ORDER["tags"] = saved_w, saved_tags
    with_accounts(go)


@test
def t_the_real_writer_meets_the_release_route():
    """Every other test stubs the writer at the seam, so the contract between
    what server.py returns and what the release route says about it was only
    ever asserted against dictionaries this suite invented."""
    def go():
        ensure_auth(); reset_prod()
        import server as _srv
        saved_req, saved_w, saved_tags = _srv._request, shopify._payment_terms_writer, ORDER["tags"]
        _srv._net30_template["id"] = ""
        try:
            ORDER["tags"] = "Unprocessed, purchase order unpaid"
            _srv._request = _terms_stub2({"id": "gid://shopify/PaymentTerms/77",
                                          "paymentTermsName": "Due on receipt",
                                          "paymentTermsType": "RECEIPT", "dueInDays": None})
            shopify._payment_terms_writer = _srv.set_order_payment_terms_net30
            r = post("/api/production-labels/queue", {"order_id": 12345}).json()
            ok(r["terms_ok"], "the real writer's UPDATE reads as success: %s" % r)
            ok("Due on receipt" in r["terms_note"] and "Net 30" in r["terms_note"],
               "and the note says what changed: %s" % r.get("terms_note"))
        finally:
            _srv._request, shopify._payment_terms_writer = saved_req, saved_w
            ORDER["tags"] = saved_tags
            _srv._net30_template["id"] = ""
    with_accounts(go)


@test
def t_the_admin_print_document_never_half_releases():
    """It cannot carry a gizmo session, so its URL is read-only and it changes
    nothing. If it ever does write, it must do a WHOLE release - tags and
    terms - not the half that leaves an invoice with no due date."""
    src = copilot_source()
    ok("_sync_tags_bg" not in src, "the tag-only background release is gone")
    seg = src.split("printed_ids = [o[\"id\"]")[1][:900]
    ok("_release_bg" in seg, "the print document releases in full when it may write")
    for f in ("print-label-order", "print-label-bulk"):
        jsx = open(os.path.join(HERE, "extensions", f, "src", "PrintActionExtension.jsx"),
                   encoding="utf-8").read()
        ok("Ready to make" in jsx,
           f + " tells the merchant the order still needs releasing in gizmo")


