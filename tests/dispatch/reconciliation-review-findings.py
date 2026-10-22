# ---------------------------------------------------------------------------
# Reconciliation: the adversarial review's confirmed findings, pinned
# ---------------------------------------------------------------------------

@test
def t_a_voided_invoice_cannot_hide_a_missing_sale():
    """THE review's best find: a voided record is an un-happened one. Letting
    it satisfy a match let an accidentally voided invoice permanently hide the
    missing revenue it was supposed to reveal."""
    cache = {"shopify": {"orders": {"1": _ord(104275, "#104275", 84200)}},
             "xero": {"invoices": {"a": _inv("INV-104275", 84200, status="VOIDED")}}}
    out = _rc.check_orders_vs_invoices(cache)
    eq([e["kind"] for e in out], ["shopify_sale_missing"],
       "the voided invoice explains nothing")
    cache["xero"]["invoices"]["a"]["status"] = "AUTHORISED"
    eq(_rc.check_orders_vs_invoices(cache), [], "the live one does")
    # Same rule for a voided credit note against a refund.
    refund = {"id": 7, "created_at": "2026-08-12", "pence": 15000}
    cache2 = {"shopify": {"orders": {"1": _ord(1, "#1", 84200, refunds=[refund])}},
              "xero": {"invoices": {}, "bank_transactions": {},
                       "credit_notes": {"c": {"id": "c", "number": "CN-1",
                           "type": "ACCRECCREDIT", "status": "VOIDED",
                           "contact": "", "date": "2026-08-13", "total": 15000,
                           "remaining": 0, "currency": "GBP", "reference": ""}}}}
    eq([e["kind"] for e in _rc.check_refunds(cache2)], ["shopify_refund_missing"])


@test
def t_a_crashed_check_does_not_resolve_its_own_findings():
    """'The check did not run' and 'the discrepancy went away' are different
    facts. A crash must not flip open findings to no-longer-detected."""
    fx = _FakeXero(invoices=[
        _raw_xinv("INV-0042", "500.00", typ="ACCPAY"),
        {**_raw_xinv("INV 42", "500.00", typ="ACCPAY"), "InvoiceID": "XR-dup2"}])
    stores = _recon_world(fx, [])
    saved = list(_rc.ALL_CHECKS)
    try:
        r = run_async(_rc.sweep())
        dup = [e for e in stores["store"]["exceptions"].values()
               if e["kind"] == "duplicate_bill_number"]
        eq(len(dup), 1, "the duplicate is found")
        xid = dup[0]["id"]

        def check_duplicates(cache):          # same __name__, always crashes
            raise RuntimeError("malformed record")
        idx = next(i for i, c in enumerate(_rc.ALL_CHECKS)
                   if c.__name__ == "check_duplicates")
        _rc.ALL_CHECKS[idx] = check_duplicates
        r2 = run_async(_rc.sweep())
        ok(any("crashed" in n for n in r2["notes"]), r2["notes"])
        e = stores["store"]["exceptions"][xid]
        ok(not e.get("stale"),
           "the finding survives the crash instead of reading as resolved")
        _rc.ALL_CHECKS[idx] = saved[idx]
        run_async(_rc.sweep())
        ok(not stores["store"]["exceptions"][xid].get("stale"),
           "and it is still there when the check runs again")
    finally:
        _rc.ALL_CHECKS[:] = saved
        _rc.configure(xero=None, registry=None, tool_json=None, mail_search=None,
                      mail_thread=None, load_store=None, write_store=None,
                      load_cache=None, write_cache=None, load_docs=None, write_docs=None)


@test
def t_every_exception_kind_is_owned_by_exactly_one_check():
    """The staleness authority: a kind nobody claims would never go stale, and
    a kind claimed twice would go stale when only one of its checks ran."""
    src = open(os.path.join(HERE, "recon.py"), encoding="utf-8").read()
    emitted = set(re.findall(r'make_exc\(\s*\n?\s*"([a-z_]+)"', src))
    claimed = {}
    for owner, kinds in _rc.CHECK_KINDS.items():
        for k in kinds:
            ok(k not in claimed, f"{k} claimed by both {claimed.get(k)} and {owner}")
            claimed[k] = owner
    missing = emitted - set(claimed)
    eq(missing, set(), "every emitted kind has a staleness owner")


@test
def t_scan_extractions_are_marked_capped_and_whitelisted():
    """A scan has no text layer to verify against, so nothing from one may be
    presented as deterministic fact or carry more than MEDIUM."""
    doc = {"source_key": "m9:a9", "doc_type": "remittance", "verified": False,
           "extracted_by": "ai", "from": "x@y.com", "date": "2026-08-19",
           "currency": "GBP", "total_pence": 842000, "filename": "scan.pdf",
           "subject": "payment", "counterparty": "Customer A",
           "invoice_numbers": ["INV-9917"],
           "invoice_lines": [{"number": "INV-9917", "pence": 842000}]}
    out = _rc.check_gmail_docs({"xero": {"invoices": {}, "credit_notes": {},
                                         "payments": {}}}, {"m9:a9": doc})
    ok(out, "the lead is still surfaced")
    for e in out:
        ok(e["severity"] in ("medium", "low"),
           "a scan cannot mint a high: %s is %s" % (e["kind"], e["severity"]))
        eq(e.get("basis"), "ai_extraction", "and it is labelled as AI-read")
        ok("SCANNED" in e["why"], "the why says so in words")
    # The whitelist mapper: model output cannot overwrite provenance keys.
    mapped = _rc._scan_fields({"doc_type": "remittance", "total": "842.00",
                               "source_key": "EVIL", "message_id": "EVIL",
                               "verified": True, "invoice_numbers": ["INV-1"],
                               "invoice_lines": [], "currency": "GBP"})
    ok("source_key" not in mapped and "verified" not in mapped
       and "message_id" not in mapped, "provenance keys cannot be overwritten")
    eq(mapped["total_pence"], 84200, "amounts are parsed into pence, not trusted")


@test
def t_anchored_validation_rejects_a_number_hiding_inside_another():
    text = "Invoice INV-142 for a total of 1,500.00 due now"
    ok(not _rc._text_has_amount(text, 50000), "500.00 is not in '1,500.00'")
    ok(_rc._text_has_amount(text, 150000), "1,500.00 is")
    ok(not _rc._text_has_ref(text, "INV-1"), "INV-1 is not a whole token here")
    ok(_rc._text_has_ref(text, "INV-142"), "INV-142 is")
    ok(_rc._text_has_ref("Ref: INV 142 enclosed", "INV-142"),
       "separators inside the reference are allowed")


@test
def t_a_truncated_xero_crawl_advances_its_watermark():
    """Refetching the same first pages forever means the backlog past the cap
    is never reached: the watermark must walk forward through it."""
    rows = [_raw_xinv("INV-%d" % i, "10.00") for i in range(3)]
    rows[-1]["UpdatedDateUTC"] = "/Date(1787097600000+0000)/"      # 2026-08-19
    fx = _FakeXero(invoices=rows + [{"_truncated": True}])
    stores = _recon_world(fx, [])
    try:
        r = run_async(_rc.sweep())
        ok(any("partial" in n for n in r["notes"]), "the truncation is said out loud")
        mark = stores["store"]["watermarks"].get("invoices", "")
        ok("19 Aug 2026" in mark,
           "the watermark advanced to the last row actually received: " + mark)
    finally:
        _rc.configure(xero=None, registry=None, tool_json=None, mail_search=None,
                      mail_thread=None, load_store=None, write_store=None,
                      load_cache=None, write_cache=None, load_docs=None, write_docs=None)


@test
def t_the_same_document_twice_is_one_document():
    docs = {}
    async def bytes_fake(mid, aid):
        return b"%PDF-1.4 same content"
    _rc.configure(gmail_bytes=bytes_fake, ai_call=None,
                  load_docs=lambda: docs, write_docs=lambda d: None)
    try:
        d1 = run_async(_rc.extract_doc({"source_key": "m1:a1", "message_id": "m1",
                                        "attachment_id": "a1", "filename": "x.pdf",
                                        "subject": "Invoice", "from": "a@b.c",
                                        "date": "2026-08-19", "size": 100}))
        docs["m1:a1"] = d1
        d2 = run_async(_rc.extract_doc({"source_key": "m2:a2", "message_id": "m2",
                                        "attachment_id": "a2", "filename": "x.pdf",
                                        "subject": "Fwd: Invoice", "from": "a@b.c",
                                        "date": "2026-08-20", "size": 100}))
        eq(d2.get("duplicate_of"), "m1:a1", "the forward is the same document")
        ok(d2.get("ignored"), "and produces no second set of discrepancies")
    finally:
        _rc.configure(gmail_bytes=None, load_docs=None, write_docs=None)


@test
def t_fees_explain_a_payout_gap_deterministically():
    """The brief's own worked example: payout minus fees equals the deposit.
    That is arithmetic, so the deterministic layer says it - as an explained
    LOW, not a missing-payout alarm."""
    cache = {"shopify": {"payouts": {"p1": {"id": "p1", "date": "2026-08-14",
                                            "pence": 2348172, "currency": "GBP",
                                            "status": "paid", "fees_pence": 51376}}},
             "xero": {"bank_transactions": {"b1": _bt("b1", 2296796, date="2026-08-15")}}}
    out = _rc.check_payouts_vs_bank(cache)
    eq([e["kind"] for e in out], ["payout_explained_by_fees"], out)
    e = out[0]
    eq(e["severity"], "low")
    ok("£513.76" in e["computed"][0] and "£22967.96" in e["computed"][0].replace(",", ""),
       e["computed"])


@test
def t_a_chargeback_needs_a_record_in_the_books():
    cache = {"shopify": {"disputes": {"d1": {"id": "d1", "order_id": "9",
                                             "type": "chargeback", "pence": 84200,
                                             "currency": "GBP", "reason": "fraudulent",
                                             "status": "lost", "date": "2026-08-10"}}},
             "xero": {"bank_transactions": {}, "credit_notes": {}}}
    out = _rc.check_disputes(cache)
    eq([e["kind"] for e in out], ["chargeback_missing_from_xero"])
    cache["xero"]["bank_transactions"]["b"] = _bt("b", 84200, typ="SPEND", date="2026-08-16")
    eq(_rc.check_disputes(cache), [], "a matching SPEND settles it")
    cache["shopify"]["disputes"]["d1"]["status"] = "won"
    cache["xero"]["bank_transactions"] = {}
    eq(_rc.check_disputes(cache), [], "a won dispute takes nothing")


@test
def t_the_other_direction_a_xero_sale_no_shopify_order_explains():
    cache = {"shopify": {"orders": {"1": _ord(104275, "#104275", 84200)}},
             "xero": {"invoices": {
                 "a": _inv("INV-104275", 84200),
                 "b": _inv("Q-2201", 55000, contact="Walk-in customer")}}}
    out = _rc.check_xero_orphan_sales(cache)
    eq([e["kind"] for e in out], ["xero_sale_without_shopify"])
    eq(out[0]["severity"], "low", "off-Shopify sales are legitimate; this is a question, not an alarm")
    # When MOST invoices are unlinked, that is one systemic finding, not noise.
    for i in range(12):
        cache["xero"]["invoices"]["q%d" % i] = _inv("Q-%d" % i, 1000 + i)
    out2 = _rc.check_xero_orphan_sales(cache)
    eq([e["kind"] for e in out2], ["invoice_numbering_unlinked"])


