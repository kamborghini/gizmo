# ---------------------------------------------------------------------------
# Reconciliation engine: the auditor must itself be auditable
# ---------------------------------------------------------------------------
import recon as _rc


def _inv(num, total, contact="Northern Stage Ltd", typ="ACCREC", date="2026-08-10",
         tax=None, due_p=None, paid_p=None, ref="", status="AUTHORISED", iid=None):
    return {"id": iid or ("XI-" + num), "number": num, "type": typ, "status": status,
            "contact": contact, "date": date, "due": "2026-09-10",
            "total": total, "tax": tax, "due_pence": due_p, "paid_pence": paid_p,
            "credited_pence": 0, "currency": "GBP", "reference": ref, "updated": ""}


def _ord(oid, name, total, date="2026-08-10", fin="paid", company="Northern Stage Ltd",
         tax=None, refunds=None, cancelled=False, test=False):
    return {"id": oid, "name": name, "created_at": date, "total": total, "tax": tax,
            "currency": "GBP", "financial_status": fin, "cancelled": cancelled,
            "test": test, "customer": "Sarah Fielding", "company": company,
            "gateways": ["manual"], "refunds": refunds or []}


def _bt(tid, pence_, typ="RECEIVE", date="2026-08-11", rec=True, ref="", account="Current"):
    return {"id": tid, "type": typ, "status": "AUTHORISED", "date": date,
            "pence": pence_, "currency": "GBP", "contact": "", "reference": ref,
            "account": account, "is_reconciled": rec}


@test
def t_money_is_pence_and_never_a_float():
    eq(_rc.pence("12.30"), 1230)
    eq(_rc.pence("1,234.56"), 123456)
    eq(_rc.pence("£8,420.00"), 842000)
    eq(_rc.pence(0.1) + _rc.pence(0.2), 30, "0.1 + 0.2 is 30 pence, not 30.000000004")
    eq(_rc.pence(""), None, "unparseable is UNKNOWN, not zero")
    eq(_rc.pence(None), None)
    eq(_rc.money(842000), "£8420.00")
    eq(_rc.norm_ref("INV-00142"), _rc.norm_ref("inv 142"),
       "leading zeros and punctuation are presentation, not identity")
    ok(_rc.norm_ref("INV-142") != _rc.norm_ref("INV-1420"))
    eq(_rc.norm_name("Selecon Lighting GmbH"), _rc.norm_name("SELECON LIGHTING"))
    eq(_rc._day("/Date(1787097600000+0000)/"), "2026-08-19",
       "Xero's /Date()/ form parses to a day")


@test
def t_a_shopify_sale_missing_from_xero_is_flagged_with_its_arithmetic():
    cache = {"shopify": {"orders": {"1": _ord(104275, "#104275", 84200)}},
             "xero": {"invoices": {}}}
    out = _rc.check_orders_vs_invoices(cache)
    eq(len(out), 1, out)
    e = out[0]
    eq(e["kind"], "shopify_sale_missing")
    eq(e["severity"], "critical", "£842 is above the £250 materiality line")
    ok("#104275" in e["title"] and e["amount"] == 84200)
    ok(e["computed"] and "no match" in e["computed"][0], e["computed"])
    ok(e["evidence"][0]["system"] == "shopify")


@test
def t_a_sale_found_by_number_or_by_amount_is_not_flagged():
    cache = {"shopify": {"orders": {
                "1": _ord(104275, "#104275", 84200),
                "2": _ord(104276, "#104276", 12000, company="Roundhouse Trust")}},
             "xero": {"invoices": {
                "a": _inv("INV-104275", 84200),
                "b": _inv("SI-0099", 12000, contact="Roundhouse Trust", ref="")}}}
    out = _rc.check_orders_vs_invoices(cache)
    eq([e for e in out if e["kind"] == "shopify_sale_missing"], [],
       "one matched by number, the other by amount+date+name")
    # And a cancelled or test order never asks for an invoice at all.
    cache["shopify"]["orders"]["3"] = _ord(9, "#9", 5000, cancelled=True)
    cache["shopify"]["orders"]["4"] = _ord(10, "#10", 5000, test=True)
    out2 = _rc.check_orders_vs_invoices(cache)
    eq([e for e in out2 if e["kind"] == "shopify_sale_missing"], [])


@test
def t_amount_and_vat_mismatches_show_both_sides_of_the_subtraction():
    cache = {"shopify": {"orders": {"1": _ord(104275, "#104275", 84200, tax=14033)}},
             "xero": {"invoices": {"a": _inv("INV-104275", 80000, tax=13333)}}}
    out = _rc.check_orders_vs_invoices(cache)
    kinds = sorted(e["kind"] for e in out)
    eq(kinds, ["order_invoice_amount_mismatch", "order_invoice_tax_mismatch"])
    amt = next(e for e in out if e["kind"] == "order_invoice_amount_mismatch")
    eq(amt["amount"], 4200, "the diff is Shopify minus Xero, in pence")
    ok("£842.00" in amt["computed"][0] and "£800.00" in amt["computed"][0], amt["computed"])


@test
def t_a_shopify_refund_needs_a_credit_note_or_a_bank_spend():
    refund = {"id": 77, "created_at": "2026-08-12", "pence": 15000}
    cache = {"shopify": {"orders": {"1": _ord(104275, "#104275", 84200, refunds=[refund])}},
             "xero": {"invoices": {}, "credit_notes": {}, "bank_transactions": {}}}
    out = _rc.check_refunds(cache)
    eq(len(out), 1)
    eq(out[0]["kind"], "shopify_refund_missing")
    # A matching ACCREC credit note within the window settles it.
    cache["xero"]["credit_notes"]["c"] = {
        "id": "c", "number": "CN-1", "type": "ACCRECCREDIT", "status": "AUTHORISED",
        "contact": "Northern Stage Ltd", "date": "2026-08-13", "total": 15000,
        "remaining": 0, "currency": "GBP", "reference": ""}
    eq(_rc.check_refunds(cache), [])


@test
def t_payouts_match_the_bank_once_and_only_once():
    cache = {"shopify": {"payouts": {
                "p1": {"id": "p1", "date": "2026-08-14", "pence": 2348172,
                       "currency": "GBP", "status": "paid"},
                "p2": {"id": "p2", "date": "2026-08-15", "pence": 2348172,
                       "currency": "GBP", "status": "paid"}}},
             "xero": {"bank_transactions": {
                "b1": _bt("b1", 2348172, date="2026-08-15")}}}
    out = _rc.check_payouts_vs_bank(cache)
    eq(len(out), 1, "two identical payouts cannot both claim the one bank line")
    eq(out[0]["kind"], "payout_missing_from_bank")
    # An unreconciled match is its own, lesser, finding.
    cache["shopify"]["payouts"].pop("p2")
    cache["xero"]["bank_transactions"]["b1"]["is_reconciled"] = False
    out2 = _rc.check_payouts_vs_bank(cache)
    eq(out2[0]["kind"], "payout_bank_unreconciled")


@test
def t_duplicate_bills_are_caught_by_number_and_by_shape():
    cache = {"xero": {"invoices": {
        "a": _inv("INV-0042", 50000, typ="ACCPAY", contact="Glass Supplies Ltd", iid="a"),
        "b": _inv("INV 42", 50000, typ="ACCPAY", contact="Glass Supplies Ltd",
                  date="2026-08-12", iid="b"),
        "c": _inv("GS-771", 32000, typ="ACCPAY", contact="Glass Supplies Ltd",
                  date="2026-08-01", iid="c"),
        "d": _inv("GS-778", 32000, typ="ACCPAY", contact="Glass Supplies Limited",
                  date="2026-08-04", iid="d")}}}
    out = _rc.check_duplicates(cache)
    kinds = sorted(e["kind"] for e in out)
    eq(kinds, ["duplicate_bill_number", "possible_duplicate_bill"], out)
    dup = next(e for e in out if e["kind"] == "duplicate_bill_number")
    ok("INV-0042" in dup["title"] and len(dup["evidence"]) == 2)


@test
def t_an_overpaid_invoice_shows_the_sum_that_proves_it():
    cache = {"xero": {
        "invoices": {"a": _inv("INV-9", 50000, iid="a")},
        "payments": {
            "p1": {"id": "p1", "date": "2026-08-11", "pence": 50000, "reference": "",
                   "status": "AUTHORISED", "invoice_id": "a", "invoice_number": "INV-9",
                   "contact": "N", "account": "090", "is_reconciled": True},
            "p2": {"id": "p2", "date": "2026-08-18", "pence": 50000, "reference": "",
                   "status": "AUTHORISED", "invoice_id": "a", "invoice_number": "INV-9",
                   "contact": "N", "account": "090", "is_reconciled": True}}}}
    out = _rc.check_overpayments(cache)
    eq(len(out), 1)
    eq(out[0]["amount"], 50000, "over by exactly one duplicated payment")
    ok("£500.00" in out[0]["computed"][0] and "over" in out[0]["computed"][0])


@test
def t_a_remittance_is_taken_apart_line_by_line():
    doc = {"source_key": "m1:a1", "doc_type": "remittance", "from": "ap@customer.com",
           "counterparty": "Customer A", "date": "2026-08-19", "currency": "GBP",
           "total_pence": 842000, "filename": "remit.pdf", "subject": "Remittance",
           "extracted_by": "text",
           "invoice_numbers": ["INV-201", "INV-202", "INV-999"],
           "invoice_lines": [{"number": "INV-201", "pence": 500000},
                             {"number": "INV-202", "pence": 342000},
                             {"number": "INV-999", "pence": 100}]}
    cache = {"xero": {"invoices": {
        "a": _inv("INV-201", 500000, iid="a", due_p=0, paid_p=500000),
        "b": _inv("INV-202", 400000, iid="b", due_p=400000, paid_p=0)},
        "payments": {}}}
    out = _rc.check_gmail_docs(cache, {"m1:a1": doc})
    kinds = sorted(e["kind"] for e in out)
    eq(kinds, ["remittance_amount_mismatch", "remittance_payment_missing",
               "remittance_unknown_invoice"], kinds)
    mm = next(e for e in out if e["kind"] == "remittance_amount_mismatch")
    ok("INV-202" in mm["title"], "the short-paid line is named")
    # When every line is individually settled, a split payment is NOT flagged.
    cache["xero"]["payments"] = {
        "p1": {"id": "p1", "date": "2026-08-20", "pence": 500000, "reference": "",
               "status": "AUTHORISED", "invoice_id": "a", "invoice_number": "INV-201",
               "contact": "", "account": "090", "is_reconciled": True},
        "p2": {"id": "p2", "date": "2026-08-20", "pence": 342000, "reference": "",
               "status": "AUTHORISED", "invoice_id": "b", "invoice_number": "INV-202",
               "contact": "", "account": "090", "is_reconciled": True}}
    doc2 = dict(doc, invoice_numbers=["INV-201", "INV-202"],
                invoice_lines=[{"number": "INV-201", "pence": 500000},
                               {"number": "INV-202", "pence": 342000}])
    out2 = _rc.check_gmail_docs(cache, {"m1:a1": doc2})
    ok(not any(e["kind"] == "remittance_payment_missing" for e in out2),
       "split settlement is the normal case, not a finding: %s" % [e["kind"] for e in out2])


@test
def t_document_text_parses_deterministically():
    text = ("REMITTANCE ADVICE\nFrom: Customer A Ltd\n"
            "Invoice INV-201  500,000.00\nInvoice INV-202  3,420.00\n"
            "Total paid: £503,420.00\nRef: BACS-88121")
    d = _rc.parse_doc_text(text, "Remittance advice", "ap@customer.com")
    eq(d["doc_type"], "remittance")
    ok("INV-201" in d["invoice_numbers"] and "INV-202" in d["invoice_numbers"])
    eq(d["total_pence"], 50342000, "the largest amount is the document total")
    eq(d["extracted_by"], "text")


@test
def t_ai_extraction_cannot_invent_what_the_text_layer_disproves():
    """THE safety property for documents: an amount or invoice number the AI
    reports that does not appear in the text is dropped, recorded, and never
    reaches the books comparison."""
    text = "Invoice INV-201 for £500.00 from Glass Supplies"
    parsed = _rc.parse_doc_text(text)
    ai = {"doc_type": "supplier_invoice", "counterparty": "Glass Supplies",
          "total": "9999.99", "invoice_numbers": ["INV-201", "INV-777"],
          "invoice_lines": [{"number": "INV-201", "amount": "500.00"},
                            {"number": "INV-777", "amount": "9999.99"}]}
    out = _rc._merge_extractions(parsed, ai, text)
    eq([l["number"] for l in out["invoice_lines"]], ["INV-201"],
       "the invented INV-777 line is dropped")
    eq(out["invoice_numbers"], ["INV-201"], "and the invented number too")
    eq(out["total_pence"], 50000, "the invented total is refused; the text's stands")
    ok("INV-777" in " ".join(out.get("ai_dropped", [])), "the drop is recorded")


class _FakeAIResp:
    def __init__(self, verdict):
        class B:  # a tool_use block
            type = "tool_use"
        b = B(); b.input = verdict
        self.content = [b]
        self.model = "claude-test"


@test
def t_an_uncited_ai_verdict_is_downgraded_not_believed():
    exc = _rc.make_exc("shopify_sale_missing", "high", "t", ["1"], amount=1000,
                       evidence=[_rc.ev("shopify", "order", "Order #1", {"id": 1}, 1)])
    async def confident_but_baseless(system, messages, tools, tool_choice):
        return _FakeAIResp({"classification": "explained", "confidence": 95,
                            "explanation": "It is fine.", "cites": ["E99"]})
    _rc.configure(ai_call=confident_but_baseless)
    try:
        v = run_async(_rc.investigate(exc, {}))
    finally:
        _rc.configure(ai_call=None)
    eq(v["classification"], "insufficient_evidence",
       "confidence without valid citations is worth nothing")
    eq(v["confidence"], 0)
    ok("human review" in v["explanation"].lower())


@test
def t_a_cited_ai_verdict_is_stored_as_interpretation_with_its_evidence():
    exc = _rc.make_exc("payout_missing_from_bank", "high", "t", ["p1"], amount=51376,
                       date="2026-08-14",
                       evidence=[_rc.ev("shopify", "payout", "Payout p1",
                                        {"id": "p1", "pence": 2348172}, 1)])
    async def cites_properly(system, messages, tools, tool_choice):
        ok("record_verdict" in json.dumps(tools), "the verdict rides a forced tool")
        ok("Never invent" in system, "the system prompt carries the safety rules")
        return _FakeAIResp({"classification": "timing_difference", "confidence": 80,
                            "explanation": "The payout landed a day later.",
                            "cites": ["E1"], "recommended_action": "Confirm tomorrow."})
    _rc.configure(ai_call=cites_properly)
    try:
        v = run_async(_rc.investigate(exc, {}))
    finally:
        _rc.configure(ai_call=None)
    eq(v["classification"], "timing_difference")
    eq(v["cites"], ["E1"])
    eq(v["model"], "claude-test")
    ok(v.get("evidence_shown"), "the audit trail records what the model was shown")


class _FakeXero:
    """The accounts, as a module-shaped object the engine cannot tell apart."""
    def __init__(self, invoices=None, payments=None, bank=None, notes_=None):
        self.invoices, self.payments = invoices or [], payments or []
        self.bank, self.notes = bank or [], notes_ or []
    def connected(self): return True
    async def list_invoices(self, since=None, modified_since=None): return list(self.invoices)
    async def list_payments(self, since=None, modified_since=None): return list(self.payments)
    async def list_bank_transactions(self, since=None, modified_since=None): return list(self.bank)
    async def list_credit_notes(self, since=None, modified_since=None): return list(self.notes)


def _recon_world(fx, orders):
    """Wire the engine to fakes end to end; returns the in-memory stores."""
    stores = {"store": {"exceptions": {}, "watermarks": {}}, "cache": {}, "docs": {}}
    async def fake_tool_json(reg, name, args):
        if name == "shopify_list_orders":
            if args.get("since_id"):
                return {"orders": []}
            return {"orders": list(orders)}
        if name in ("shopify_list_payouts", "shopify_list_disputes"):
            # A store not on Shopify Payments refuses both alike.
            return {"available": False, "reason": "not on Shopify Payments"}
        return {"_failed": True}
    import copy as _copy
    # deepcopy on load, like a real store parsing from disk: a fake that hands
    # back the same object makes every lost-update bug invisible, which is
    # exactly how the seen_threads write survived a reload that discarded it.
    _rc.configure(
        xero=fx, registry={}, tool_json=fake_tool_json,
        mail_search=None, mail_thread=None, gmail_bytes=None, ai_call=None,
        load_store=lambda: _copy.deepcopy(stores["store"]),
        write_store=lambda d: stores.update(store=d),
        load_cache=lambda: _copy.deepcopy(stores["cache"]),
        write_cache=lambda d: stores.update(cache=d),
        load_docs=lambda: _copy.deepcopy(stores["docs"]),
        write_docs=lambda d: stores.update(docs=d))
    return stores


def _raw_xinv(num, total, typ="ACCREC", contact="Northern Stage Ltd"):
    return {"InvoiceID": "XR-" + num, "InvoiceNumber": num, "Type": typ,
            "Status": "AUTHORISED", "Contact": {"Name": contact},
            "DateString": "2026-08-10T00:00:00", "DueDateString": "2026-09-10T00:00:00",
            "Total": total, "TotalTax": 0, "AmountDue": total, "AmountPaid": 0,
            "AmountCredited": 0, "CurrencyCode": "GBP", "Reference": "",
            "UpdatedDateUTC": "/Date(1755561600000+0000)/"}


def _raw_order(oid, name, total):
    return {"id": oid, "name": name, "created_at": "2026-08-10T09:00:00Z",
            "total_price": total, "total_tax": "0.00", "currency": "GBP",
            "financial_status": "paid", "cancelled_at": None, "test": False,
            "customer": {"first_name": "Sarah", "last_name": "Fielding",
                         "default_address": {"company": "Northern Stage Ltd"}},
            "payment_gateway_names": ["manual"], "refunds": []}


@test
def t_a_full_sweep_finds_the_missing_sale_and_statuses_survive_resweeps():
    """End to end through sweep(): sync, check, merge. The same facts keep the
    same exception id, a status set by a person survives the next sweep, and a
    discrepancy the data no longer shows is marked, never deleted."""
    fx = _FakeXero(invoices=[_raw_xinv("INV-104275", "842.00")])
    orders = [_raw_order(104275, "#104275", "842.00"),
              _raw_order(104276, "#104276", "120.00")]
    stores = _recon_world(fx, orders)
    try:
        r = run_async(_rc.sweep())
        ok(r["ok"], r)
        exs = stores["store"]["exceptions"]
        missing = [e for e in exs.values() if e["kind"] == "shopify_sale_missing"]
        eq(len(missing), 1, "only #104276 is missing")
        ok("#104276" in missing[0]["title"])
        ok(_did_not_run(r["notes"], "payout") and _did_not_run(r["notes"], "chargeback"),
           "a check that could not run says so instead of reading as clean: %s" % r["notes"])
        xid = missing[0]["id"]
        # A person marks it explained; the next sweep must not undo that.
        exs[xid]["status"] = "explained"
        exs[xid]["status_note"] = "Invoiced under the January consolidation."
        r2 = run_async(_rc.sweep())
        ok(r2["ok"])
        eq(stores["store"]["exceptions"][xid]["status"], "explained",
           "a human's status outlives the sweep")
        # The books catch up: the invoice appears. The exception goes stale,
        # with the disappearance on its history - never silently deleted.
        fx.invoices.append(_raw_xinv("INV-104276", "120.00"))
        r3 = run_async(_rc.sweep())
        ok(r3["ok"])
        e = stores["store"]["exceptions"][xid]
        ok(e["stale"], "no longer detected, and it says so")
        ok(any("No longer detected" in h.get("note", "") for h in e["history"]))
    finally:
        _rc.configure(xero=None, registry=None, tool_json=None, mail_search=None,
                      mail_thread=None, load_store=None, write_store=None,
                      load_cache=None, write_cache=None, load_docs=None, write_docs=None)


def _did_not_run(notes, check):
    """The sweep said this check sat it out ("payout", "chargeback")."""
    return any(check in n and "checks did not run" in n for n in notes)


def _raw_btxn(bid, typ, total, day):
    return {"BankTransactionID": bid, "Type": typ, "Status": "AUTHORISED",
            "DateString": day + "T00:00:00", "Total": total, "CurrencyCode": "GBP",
            "IsReconciled": False, "Contact": {"Name": "Shopify"}, "Reference": "",
            "BankAccount": {"Name": "Current"}}


def _payments_world(fx, answers):
    """_recon_world with Shopify Payments reads that a test switches between
    answering and not. `answers` maps a tool to its reply, or to a callable for
    one that raises; a tool left out answers as a failed read."""
    orders = [_raw_order(104275, "#104275", "842.00")]
    stores = _recon_world(fx, orders)
    async def tool_json(reg, name, args):
        if name == "shopify_list_orders":
            return {"orders": [] if args.get("since_id") else list(orders)}
        a = answers.get(name, {"_failed": True})
        return a() if callable(a) else a
    _rc.configure(tool_json=tool_json)
    return stores


def _unconfigure_recon():
    _rc.configure(xero=None, registry=None, tool_json=None, mail_search=None,
                  mail_thread=None, load_store=None, write_store=None,
                  load_cache=None, write_cache=None, load_docs=None, write_docs=None)


@test
def t_a_sweep_that_cannot_read_payouts_leaves_the_payout_findings_alone():
    """The payouts read was refused and the note said the payout checks did not
    run, but the check ran anyway on the payouts cached by earlier sweeps and
    counted as having run. So a sweep that saw no payout at all marked an open
    payout finding "no longer detected": once when the deposit landed in Xero
    while the cached payout was the only copy, and again with no copy left."""
    import copy as _copy
    day = _rc._cutoff_day(10)
    payout = {"id": 7001, "date": day, "amount": "312.40", "currency": "GBP", "status": "paid"}

    def missing_tools():
        raise KeyError("shopify_list_payouts")
    for how, unreadable in (
            ("refused", {"available": False, "reason": "The access token lacks the Shopify "
                                                       "Payments read scopes."}),
            ("failed", {"_failed": True}),
            ("not on this build", missing_tools)):
        fx = _FakeXero(invoices=[_raw_xinv("INV-104275", "842.00")])
        answers = {"shopify_list_payouts": {"payouts": [payout]},
                   "shopify_payout_transactions": {"transactions": []},
                   "shopify_list_disputes": {"disputes": []}}
        stores = _payments_world(fx, answers)
        try:
            run_async(_rc.sweep())
            exs = stores["store"]["exceptions"]
            found = [x for x, e in exs.items() if e["kind"] == "payout_missing_from_bank"]
            eq(len(found), 1, how + ": a paid payout with no deposit is found while payouts read")
            xid = found[0]
            exs[xid]["status"] = "investigating"
            before = _copy.deepcopy(exs[xid])
            # Payouts stop answering, and meanwhile the deposit lands in Xero.
            answers["shopify_list_payouts"] = unreadable
            fx.bank.append(_raw_btxn("BT-7001", "RECEIVE", "312.40", day))
            r2 = run_async(_rc.sweep())
            ok(_did_not_run(r2["notes"], "payout"), (how, r2["notes"]))
            after = stores["store"]["exceptions"][xid]
            ok(not after.get("stale"), how + ": a sweep that read no payouts did not see it go")
            eq(after["status"], "investigating", how)
            eq(after["history"], before["history"], how + ": and wrote nothing on its history")
            payout_kinds = _rc.CHECK_KINDS["check_payouts_vs_bank"]
            eq([x for x, e in stores["store"]["exceptions"].items() if e["kind"] in payout_kinds],
               [xid], how + ": nor raised anything new from the old copy")
            ok("7001" in stores["cache"]["shopify"]["payouts"],
               how + ": and the payout it was built from is still held")
            # Months on and still unreadable: the cached payout is now older
            # than the window the check matches in, and than the cache keeps.
            stores["cache"]["shopify"]["payouts"]["7001"]["date"] = _rc._cutoff_day(_rc.CACHE_KEEP_DAYS + 5)
            run_async(_rc.sweep())
            ok(not stores["store"]["exceptions"][xid].get("stale"),
               how + ": an aged copy of payouts that could not be read settles nothing")
            ok("7001" in stores["cache"]["shopify"]["payouts"],
               how + ": nor is the record an open finding rests on pruned")
            # With no cached copy left either, it is still not a reason.
            stores["cache"]["shopify"]["payouts"] = {}
            run_async(_rc.sweep())
            ok(not stores["store"]["exceptions"][xid].get("stale"),
               how + ": an empty copy of payouts that could not be read settles nothing")
            # Readable again: the check runs, finds the deposit and settles it.
            answers["shopify_list_payouts"] = {"payouts": [payout]}
            r4 = run_async(_rc.sweep())
            ok(not _did_not_run(r4["notes"], "payout"), (how, r4["notes"]))
            ok(stores["store"]["exceptions"][xid]["stale"],
               how + ": a sweep that did read payouts settles it as before")
        finally:
            _unconfigure_recon()


@test
def t_a_sweep_that_cannot_read_disputes_leaves_the_chargeback_findings_alone():
    """The disputes read failed with no word at all, and the chargeback check
    ran on the disputes cached by earlier sweeps, so a sweep that saw no
    dispute could settle an open chargeback finding."""
    import copy as _copy
    day = _rc._cutoff_day(10)
    dispute = {"id": 8001, "order_id": 104275, "type": "chargeback", "amount": "95.00",
               "currency": "GBP", "reason": "fraudulent", "status": "lost", "initiated_at": day}
    for how, unreadable in (
            ("refused", {"available": False, "reason": "The access token lacks the Shopify "
                                                       "Payments read scopes."}),
            ("failed", {"_failed": True})):
        fx = _FakeXero(invoices=[_raw_xinv("INV-104275", "842.00")])
        answers = {"shopify_list_payouts": {"payouts": []},
                   "shopify_list_disputes": {"disputes": [dispute]}}
        stores = _payments_world(fx, answers)
        try:
            run_async(_rc.sweep())
            exs = stores["store"]["exceptions"]
            found = [x for x, e in exs.items() if e["kind"] == "chargeback_missing_from_xero"]
            eq(len(found), 1, how + ": a chargeback with no Xero record is found while disputes read")
            xid = found[0]
            before = _copy.deepcopy(exs[xid])
            answers["shopify_list_disputes"] = unreadable
            fx.bank.append(_raw_btxn("BT-8001", "SPEND", "95.00", day))
            r2 = run_async(_rc.sweep())
            after = stores["store"]["exceptions"][xid]
            ok(not after.get("stale"), how + ": a sweep that read no disputes did not see it go")
            eq(after["history"], before["history"], how)
            ok(_did_not_run(r2["notes"], "chargeback"), (how, r2["notes"]))
            answers["shopify_list_disputes"] = {"disputes": [dispute]}
            r3 = run_async(_rc.sweep())
            ok(not _did_not_run(r3["notes"], "chargeback"), (how, r3["notes"]))
            ok(stores["store"]["exceptions"][xid]["stale"],
               how + ": a sweep that did read disputes settles it as before")
        finally:
            _unconfigure_recon()


@test
def t_payout_fees_that_cannot_be_read_are_said_so():
    """A fee lookup that failed stopped the fee reads with no word, and a
    deposit short of its payout by the fees then read as a missing deposit."""
    day = _rc._cutoff_day(10)
    payout = {"id": 7002, "date": day, "amount": "100.00", "currency": "GBP", "status": "paid"}
    fx = _FakeXero(invoices=[_raw_xinv("INV-104275", "842.00")])
    answers = {"shopify_list_payouts": {"payouts": [payout]},
               "shopify_payout_transactions": {"_failed": True},
               "shopify_list_disputes": {"disputes": []}}
    _payments_world(fx, answers)
    try:
        r = run_async(_rc.sweep())
        ok(any("fees could not be read" in n for n in r["notes"]), r["notes"])
        answers["shopify_payout_transactions"] = {"transactions": [{"fee": "2.50"}]}
        r2 = run_async(_rc.sweep())
        ok(not any("fees could not be read" in n for n in r2["notes"]),
           "fees read on a later sweep say nothing: %s" % r2["notes"])
    finally:
        _unconfigure_recon()


@test
def t_the_xero_client_is_read_only_by_construction():
    """No POST, PUT or DELETE ever reaches the accounting API. The one POST in
    the module is the OAuth token endpoint, which mints credentials, not
    records."""
    src = open(os.path.join(HERE, "xero.py"), encoding="utf-8").read()
    lines = src.split("\n")
    # POSTs are allowed ONLY to Xero's identity host: minting a token and
    # revoking one are identity operations, not writes to the books. Anything
    # that reaches the accounting API must be a GET.
    # The call and its URL can sit on different lines, so take each POST with
    # the two lines after it.
    posts = [" ".join(x.strip() for x in lines[i:i + 3])
             for i, l in enumerate(lines) if "client.post(" in l]
    ok(posts, "found the POST call sites")
    for l in posts:
        ok("IDENTITY_BASE" in l, "a POST goes somewhere other than the identity host: " + l)
    joined = " ".join(posts)
    ok("/connect/revocation" in joined,
       "revocation exists: a token merely forgotten stays live at Xero for 60 days")
    ok("/connect/token" in joined, "and the token endpoint is the only other POST")
    for l in lines:
        if "client.get(" in l or "client.request(" in l:
            ok("client.post" not in l, "no disguised write: " + l.strip())
    for verb in ("client.put", "client.delete", "client.patch"):
        ok(verb not in src, verb + " must not appear in a read-only client")
    # The accounting API is reached through _get only, which is a GET.
    ok('resp = await client.get(url' in src, "the accounting fetcher is a GET")

@test
def t_the_system_learns_which_source_is_right_from_closed_months():
    """Nobody picks the algorithm. Every run writes down what each source says
    about the months ahead; when a month closes, each of those predictions is
    marked against what actually came in, the closest is recorded, and once
    every method has three closed months of its own the forecast is ranked on
    that record rather than on a backtest. (Counted on the longest record
    alone, a method added later raced on one month against everyone else's
    average, and a lucky month put it in charge of the figures.)

    The distinction matters. A backtest refits a model to a period the code
    already knows the shape of and forgives it accordingly. The record is what
    a source SAID while the month was still ahead. So a prediction is written
    ONCE and never revised: a later run may have a better opinion about
    September, but overwriting September's original entry would turn a forecast
    into a hindcast and make every source look excellent."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    simple = open(os.path.join(root, "forecast", "simple.py"), encoding="utf-8").read()
    nightly = open(os.path.join(root, "forecast", "nightly.py"), encoding="utf-8").read()
    src = copilot_source()

    led = src.split("def _forecast_ledger(", 1)[1].split("\n    @mcp", 1)[0]
    ok("if not math.isfinite(v) or name in slot:" in led,
       "a prediction is written once and never revised, or the record flatters everyone")
    ok('winner = min(by.items(), key=lambda kv: abs(kv[1]["error"]))' in led,
       "the closest source each month is recorded")
    ok("if month in scored or month not in predicted:" in led,
       "a month is marked once, and only if something was predicted for it")
    ok('state["ledger"] = forecasting._forecast_ledger(state, body)' in src, "the hook keeps it")
    ok('"/hooks/forecast/ledger"' in src, "and the service can read it back")

    ok("def track_record(" in simple and "MIN_LIVE_MONTHS = 3" in simple,
       "the record becomes a score per source, after three closed months")
    ok('ranked_on = "record" if on_record else "backtest"' in simple
       and 'all(own(e["name"]) >= MIN_LIVE_MONTHS for e in scored_now)' in simple
       and "closed >= MIN_LIVE_MONTHS and bool(scored_now)" in simple,
       "and outranks the backtest once every scored method has three closed months of its own")
    ok('return (0, m["live"]["mape"])' in simple,
       "ranking prefers what a source did on months it could not see")
    ok('"Weighted by track record"' in simple and "_live_weights(" in simple,
       "and the accumulated pattern becomes a source of its own, weighted by who has been right")

    ok("_fetch_ledger(base + \"/hooks/forecast/ledger\", token)" in nightly, "the run reads it")
    ok("results=record" in nightly, "and forecasts with it")
    ok('"predictions": predictions, "actuals": actuals_by_month' in nightly,
       "then writes down what every source said, and what actually came in")
    # BOTH grains, and the page picks. The month is what the plan is written
    # in and what a month-end verdict is passed at; the day is what somebody
    # asks for when the question is "how is this week going". Shipping only
    # months took a chart away that people were using.
    ok('"months": months_series' in nightly and '"daily":' in nightly,
       "months for the plan and days for the week, so the reader can choose the scale")
    ok("actual_daily.tail(420)" in nightly,
       "with enough daily history behind it for a three-month view")


@test
def t_the_forecast_is_many_sources_ranked_by_what_each_was_worth():
    """The big model forecast October - Projected Image's best month, over 60k
    two years running - at 16,436, because it predicts each product on each
    day and adds them up, and half their revenue is quoted projector work
    where one order is a tenth of the month.

    So the forecast is now many plain sources of the MONTHLY TOTAL, each
    checkable by eye, plus combinations of them, each scored on the shop's own
    history and ranked by it. Nothing leads because of what it is called.

    The series they read is the ORDER TOTAL, not the panel's line-item net,
    because the cash flow plan is written in cash-in terms ("Gross Sales"
    feeding "Total Cash In") and so is Shopify's own forecast."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    nightly = open(os.path.join(root, "forecast", "nightly.py"), encoding="utf-8").read()
    ingest = open(os.path.join(root, "forecast", "ingest.py"), encoding="utf-8").read()
    simple = open(os.path.join(root, "forecast", "simple.py"), encoding="utf-8").read()
    reqs = open(os.path.join(root, "forecast", "requirements-service.txt"), encoding="utf-8").read()

    ok("sanity_forecasts(months, horizon=" in nightly, "the run computes them")
    ok("opinions = pick_opinions(sanity)" in nightly and "primary = opinions[0]" in nightly,
       "and the BEST one drives the forecast, rather than sitting beside a worse one")
    ok("daily_frame(primary, as_of" in nightly and "eng.monthly_view(actual_daily, fdaily)" in nightly,
       "the month table, the cash path and the alerts all come from it")
    ok("DayProfile.fit(actual_daily)" in nightly,
       "spread over the days by the shop's own trading shape, not evenly")
    ok('env.get("FORECAST_M5", "0") == "1"' in nightly,
       "the per-variant model is OFF by default: it forecast October at a quarter of "
       "what October has ever been. Kept behind a switch, not deleted.")
    ok("monthly_cash(orders, as_of, since)" in nightly and "daily_cash(orders, as_of)" in nightly,
       "both the history and the month-to-date are the order total, so they are the same money")
    ok(".replace(day=1)" in nightly and "run_bulk_orders(store, pull_from)" in nightly
       and "min_total=BIG_ORDER" in nightly and "big=big" in nightly,
       "the pull starts on the 1st so every month is whole, and the big orders reach their source")

    mc = ingest.split("def monthly_cash(", 1)[1].split("\ndef ", 1)[0]
    ok('ser.index < pd.Period(as_of, freq="M")' in mc,
       "the month in progress is dropped: half a month reads as a collapse to every model")
    ok('_money(n, "currentTotalPriceSet")' in ingest and '"order_total"' in ingest,
       "cash in per order, the units the plan and Shopify both use")
    ok("currentTotalPriceSet { shopMoney { amount } }" in ingest, "and the bulk query asks for it")

    for fn in ("last_year_times_run_rate", "seasonal_share", "holt_winters_flat",
               "holt_winters_trend", "theta"):
        ok("def " + fn + "(" in simple, fn + " is one of the sources")
    ok("def statsforecast_models(" in simple and "AutoETS" in simple and "AutoARIMA" in simple,
       "the statsforecast family joins as more voices")
    ok("except Exception:\n        return []" in simple,
       "and is OPTIONAL at runtime: an image built without it must still forecast")
    ok("COMBINERS = (" in simple and '"Average of every source"' in simple
       and '"Middle of every source"' in simple and '"Average, extremes removed"' in simple,
       "combinations of the sources are offered, including a plain average")
    ok('"kind": "combination"' in simple and '"kind": "model"' in simple,
       "and a combination is marked as one, so the reader knows what they are reading")
    bt = simple.split("def _backtest_all(", 1)[1].split("\ndef ", 1)[0]
    ok("per_combo[cname] += " in bt,
       "combinations are scored on the SAME folds as the sources, not assumed better: "
       "an average of forecasts that all lean high leans high")
    ok('"about": blurb' in simple,
       "every source carries a plain-English explanation for whoever reads the board pack")
    ok("Last year, adjusted for this year" in simple and "Average, extremes removed" in simple,
       "and is NAMED for what it does, not for the paper it came from")
    # "What does the YEAR come to" is the question a director asks, and it has
    # to be answerable of any source on the page, not only the headline.
    ok("def _year_per_source(" in simple or "def _year_per_source(" in nightly,
       "every source carries a whole-plan-year total")
    yr = nightly.split("def _year_per_source(", 1)[1].split("\ndef ", 1)[0]
    ok('entry["year"] = round(banked + sum(' in yr,
       "the months already banked plus that source's own forecast for the rest")
    ok('entry["year_partial"]' in yr,
       "and a source that does not reach the end of the plan says so rather than "
       "quietly reporting a short year as if it were a whole one")
    ok("_year_per_source(sanity, monthly_view, cf)" in nightly, "the run fills it in")
    ok("horizon_months = int(env.get(\"FORECAST_MONTHS\", \"0\")) or min(_need, 18)" in nightly,
       "and the horizon reaches the end of the plan so there is a year to total")

    for fn in ("last_year_times_run_rate", "seasonal_share", "holt_winters_flat",
               "holt_winters_trend", "theta"):
        ok("def " + fn + "(" in simple, fn + " is one of the five")
    ok("MIN_MONTHS = 24" in simple, "two full years before a seasonal model may speak")
    ok('"score": mscore.get(' in simple and '"score": cscore.get(' in simple,
       "every source AND every combination carries its backtest, so the reader can rank them")
    ok("def pick_opinions(" in simple and "def daily_frame(" in simple,
       "the ranking and the monthly-to-daily spread live beside the models")
    df = simple.split("def daily_frame(", 1)[1].split("\ndef ", 1)[0]
    bw = simple.split("def band_width(", 1)[1].split("\ndef ", 1)[0]
    ok("band_width(model)" in df and 'sc.get("p80")' in bw,
       "the band is the model's OWN measured misses (the one 8 in 10 stayed within), "
       "not a number chosen to look confident")
    ok("statsmodels" in reqs and "statsforecast" in reqs,
       "the service image can actually import them")
    # The gradient boosters serve a model that has been off by default since it
    # forecast October at a quarter of what October has ever been. They were
    # two thirds of the image and were imported on EVERY run for nothing.
    m5 = open(os.path.join(root, "forecast", "requirements-m5.txt"), encoding="utf-8").read()
    for heavy in ("lightgbm", "catboost", "scikit-learn"):
        ok(heavy not in reqs, heavy + " is not in the image every run installs")
        ok(heavy in m5, heavy + " is in the optional list, so the old model can still be run")
    pipe = open(os.path.join(root, "forecast", "pipeline.py"), encoding="utf-8").read()
    head = pipe.split("class ", 1)[0]
    ok("from .models import blend, blend_weights" in head
       and "LightGBMForecaster" not in head and "gbdt_available" not in head,
       "and naming them at module level is what dragged them in, so it does not happen")
    ok("if not any(gbdt_available().values()):" in nightly,
       "switching the old model back on without them fails loudly rather than "
       "posting a seasonal baseline dressed as a forecast")


@test
def t_the_panel_counts_a_discount_code_as_a_discount():
    """The forecast was learning GROSS sales and calling them net.

    `totalDiscountSet` is a LINE's own discount and nothing else. A discount
    CODE is an ORDER-level discount that Shopify spreads across the lines, and
    it appears ONLY in `discountAllocations`. On #104335 the first line reads
    a total discount of 0.00 beside an allocation of 49.50, and nearly every
    discounted line in this store looks the same.

    The bulk query always asked for the allocations. `_assemble_bulk` dropped
    them, so `orders_to_rows` fell through to the line discount, found zero,
    and billed the customer's discount as revenue. Across nineteen months that
    is 61,694 of discount on 588,292 of gross - a tenth of the business, and
    on a heavily discounted order like #104335 it was 43 percent."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ingest = open(os.path.join(root, "forecast", "ingest.py"), encoding="utf-8").read()
    asm = ingest.split("def _assemble_bulk(", 1)[1].split("\ndef ", 1)[0]
    ok('"discount_allocations":' in asm,
       "the assembler carries the allocations, not just the line's own discount")
    ok('_money(a, "allocatedAmountSet")' in asm, "reading each allocation's amount")
    rows = ingest.split("def orders_to_rows(", 1)[1].split("\ndef ", 1)[0]
    ok('li.get("discount_allocations")' in rows and 'li.get("total_discount")' in rows,
       "and the row builder still prefers the allocations, falling back to the line")
    bulk = ingest.split('BULK_ORDERS_QUERY = """', 1)[1].split('"""', 1)[0]
    ok("discountAllocations" in bulk, "the query asks for them, as it always did")


@test
def t_the_forecast_pins_its_threads_to_the_cpu_it_actually_has():
    """One LightGBM fit took 2318 seconds on the container. The same fit, on
    the same 185,788 training rows, costs 13.7s on eight cores and 22.8s on
    ONE. The work was never the problem: `num_threads=0` starts a thread per
    core the HOST reports, while a container is allowed a slice of one, and
    the threads spend their lives contending for it.

    So the budget is read from the cgroup quota, and every maths library is
    pinned to it before it loads - each reads its variable once, at import, so
    setting them later does nothing. That is why `apply_thread_limits()` has
    to run in `__main__` ahead of the pipeline import, which pulls in numpy.

    The fallback is deliberately timid. The whole span between one thread and
    eight is under 2x; oversubscribing cost 100x. Guess low."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    main_py = open(os.path.join(root, "forecast", "__main__.py"), encoding="utf-8").read()
    gbdt = open(os.path.join(root, "forecast", "models", "gbdt.py"), encoding="utf-8").read()

    ok(main_py.index("apply_thread_limits()") < main_py.index("from .pipeline import main"),
       "the libraries are pinned BEFORE the import that loads numpy")
    ok("num_threads=cpu_budget()" in gbdt and "num_threads=0" not in gbdt,
       "LightGBM asks for the budget, never for every core it can see")
    ok('"thread_count": cpu_budget()' in gbdt and '"thread_count": -1' not in gbdt,
       "and so does CatBoost")

    sys.path.insert(0, root)
    from forecast.cpu import _quota, cpu_budget, FALLBACK_MAX
    import tempfile
    d = tempfile.mkdtemp(dir=SCRATCH)
    with open(os.path.join(d, "cpu.max"), "w") as fh:
        fh.write("50000 100000")
    eq(_quota(d), 0.5, "cgroup v2: half a core is read as half a core")
    with open(os.path.join(d, "cpu.max"), "w") as fh:
        fh.write("max 100000")
    eq(_quota(d), None, "cgroup v2: no limit is no quota, not a number")
    os.remove(os.path.join(d, "cpu.max"))
    os.makedirs(os.path.join(d, "cpu"), exist_ok=True)
    for name, val in (("cpu.cfs_quota_us", "25000"), ("cpu.cfs_period_us", "100000")):
        with open(os.path.join(d, "cpu", name), "w") as fh:
            fh.write(val)
    eq(_quota(d), 0.25, "cgroup v1 is read too")
    eq(_quota(d + "/nope"), None, "and a host with no cgroup files is no quota")

    saved = os.environ.get("FORECAST_THREADS")
    try:
        os.environ["FORECAST_THREADS"] = "3"
        eq(cpu_budget(), 3, "an operator who knows better can say so")
    finally:
        os.environ.pop("FORECAST_THREADS", None)
        if saved is not None:
            os.environ["FORECAST_THREADS"] = saved
    ok(1 <= cpu_budget() <= max(FALLBACK_MAX, 1),
       "and with no quota the answer is capped, never the whole host")


@test
def t_the_bulk_query_carries_no_connection_inside_a_list():
    """The first run that got as far as Shopify died on this, immediately:

        Queries that contain a connection field within a list field are not
        currently supported.

    `Order.refunds` is a LIST and `Refund.refundLineItems` is a CONNECTION, and
    a bulk operation refuses that shape outright. An ordinary query allows it,
    so refunds are fetched separately, searched by financial status so the
    second pass reads the few orders that have one rather than the history
    again: 31 of the last 3,255 orders carry a refund, one page.

    They cannot simply be dropped. A refund is a negative row on the day it was
    raised, keyed to the line it came off, which is how the model sees a return
    as demand going away rather than a sale that never happened."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ingest = open(os.path.join(root, "forecast", "ingest.py"), encoding="utf-8").read()
    bulk = ingest.split('BULK_ORDERS_QUERY = """', 1)[1].split('"""', 1)[0]
    ok("refund" not in bulk.lower(),
       "the bulk query asks for no refunds at all, which is the only shape it may take")
    ok("lineItems { edges { node {" in bulk,
       "line items stay: a connection on a NODE is what bulk is for")
    ok("REFUNDED_ORDERS_QUERY" in ingest and "def fetch_refunds(" in ingest,
       "refunds have their own ordinary query")
    ref = ingest.split('REFUNDED_ORDERS_QUERY = """', 1)[1].split('"""', 1)[0]
    ok("refundLineItems(first:" in ref, "which does carry the nesting bulk refused")
    ok("financial_status:refunded" in ingest and "financial_status:partially_refunded" in ingest,
       "and reads only the orders that have a refund")
    run = ingest.split("def run_bulk_orders(", 1)[1].split("\ndef ", 1)[0]
    ok("fetch_refunds(store, since)" in run,
       "a run stitches the two halves together before anyone sees the orders")
    ok('o["refunds"] = refunds.get(o["id"], [])' in run,
       "every order ends up with the refunds field the panel builder reads")


@test
def t_a_nightly_run_can_be_watched_and_cannot_hang():
    """Cameron ran the cron by hand and had to ask how to kill it, because a
    run that is working and a run that is wedged look identical: the order
    pull said nothing for up to thirty minutes and the training had no ceiling
    at all.

    Two things follow. The poll reports every tick, so the log is a progress
    bar. And the whole run carries a wall-clock ceiling that raises in the main
    thread, so the failure travels the ordinary path and reaches the tab
    instead of a container still going at lunchtime.

    The poll also watches the operation it STARTED. Shopify has allowed five
    concurrent bulk queries per app since the 2026-01 version, so
    `currentBulkOperation` is both deprecated and ambiguous: a run whose
    container was killed leaves its operation running, and the next run
    polling "current" could download a different date range believing it was
    its own."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ingest = open(os.path.join(root, "forecast", "ingest.py"), encoding="utf-8").read()
    nightly = open(os.path.join(root, "forecast", "nightly.py"), encoding="utf-8").read()

    bulk = ingest.split("def run_bulk_orders(", 1)[1].split("\ndef ", 1)[0]
    # Comments stripped: the function explains in prose WHY it does not use the
    # deprecated field, and that explanation must not read as a use of it.
    code = "\n".join(l for l in bulk.splitlines() if not l.strip().startswith("#"))
    ok("currentBulkOperation" not in code,
       "the deprecated, ambiguous field is not how a run watches its own operation")
    ok("currentBulkOperation" in bulk, "and the comment says why, so nobody puts it back")
    ok('op_id = started["bulkOperation"]["id"]' in bulk,
       "the id of the operation this run started is captured")
    ok("store.bulk_status(op_id)" in bulk, "and it is what the poll asks about")
    ok('{"id": op_id}' in ingest.split("def bulk_status(", 1)[1].split("\n    def ", 1)[0],
       "by id, when the job reads the store with a token of its own")
    ok(bulk.count("log.info(") >= 3,
       "the poll speaks each tick, so silence means stopped rather than working")

    ok('env.get("FORECAST_MAX_MINUTES", "120")' in nightly, "the run has a ceiling, defaulting to two hours")
    # A fold is minutes long. It used to report only when it ENDED, so "still
    # running" was the only thing anyone could say about it for ten minutes at
    # a time. Every feature build and every fit now reports its own seconds.
    root2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pipe = open(os.path.join(root2, "forecast", "pipeline.py"), encoding="utf-8").read()
    ok('log.info("fold %d, days %d-%d: features in %.0fs (%d rows)"' in pipe,
       "each feature build says how long it took")
    ok('log.info("fold %d, days %d-%d: %s in %.0fs"' in pipe,
       "and so does each set of model fits, naming the models")
    ok('env.get("FORECAST_CATBOOST", "1") != "0"' in nightly,
       "and if the per-variant model is ever switched back on, CatBoost can still be "
       "switched off within it: forty fits of up to 1200 rounds is the long pole there")
    ok('use_catboost=' in nightly, "and the switch actually reaches the config")
    ok("signal.alarm(budget_min * 60)" in nightly, "the ceiling is armed before the work starts")
    ok("raise TimeoutError(" in nightly, "reaching it raises, so the except posts it to the tab")
    run_then_post = nightly.split("runner.run()", 1)[1].split("_post(results_url", 1)[0]
    ok("signal.alarm(0)" in run_then_post,
       "and it is cancelled once the work is done, so posting the result is never cut short")


@test
def t_the_nightly_service_holds_no_shopify_secret():
    """Reactor holds no static Shopify token, so the forecast service was once
    given Reactor's own SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET to mint
    one. That secret also signs every webhook Reactor trusts, so a copy on a
    second service, running its own dependencies, could forge a shop/redact
    (the audit's R-C1). The service now reads the store through Reactor's
    /hooks/forecast/shopify with the token it already holds, or with a
    read-only token of its own; the secret is never read, and a service that
    still has it is told to remove it. This lives in the CI suite rather than
    beside the other forecast guards because those need pandas and skip
    themselves."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    nightly = open(os.path.join(root, "forecast", "nightly.py"), encoding="utf-8").read()
    ingest = open(os.path.join(root, "forecast", "ingest.py"), encoding="utf-8").read()
    ok("client_credentials" not in ingest and "def access_token(" not in ingest,
       "no path mints a token from the app's secret")
    ok('env.get("SHOPIFY_CLIENT_SECRET"' not in nightly and 'env.get("SHOPIFY_CLIENT_ID"' not in nightly,
       "the pair is not read for use")
    ok('held = [k for k in ("SHOPIFY_CLIENT_SECRET", "SHOPIFY_API_SECRET", "SHOPIFY_CLIENT_ID") if env.get(k)]'
       in nightly and "rotate the app's" in nightly,
       "a service that still holds it is told to remove it and rotate")
    body = nightly.split("try:", 1)[1]
    ok("ShopifyStore(shop, stoken) if stoken else ReactorStore(base, token)" in body,
       "the store is chosen inside the try, so a refused read reaches the tab as a failed run")
    ok("run_bulk_orders(store, pull_from)" in nightly and "fetch_products(store)" in nightly,
       "both Shopify reads go through the store chosen")
    ok('"/hooks/forecast/shopify"' in ingest and '"/hooks/forecast/shopify"' in
       copilot_source(),
       "the job and Reactor name the same hook")
    ok("def shop_host(" in ingest and 'shop if "." in shop else shop + ".myshopify.com"' in ingest,
       "either spelling of the shop reaches Shopify at the same address")

@test
def t_the_record_keeps_what_the_forecast_in_use_said():
    """A closed month is shown as what directors were told: the source in
    use, its figure and likely range, and when, from the first run that had
    seen every whole month before it. It is written once. September 2026 was
    scored before this was kept, so its source in use (rebuilt from the
    forecast's own code) is filled in from the source's own first figure and
    marked as worked out afterwards."""
    L = forecasting._forecast_ledger
    state = {}
    sep9 = {"as_of": "2026-09-09", "seen_through": "2026-08",
            "predictions": {"2026-09": {"Last year, adjusted for this year": 24677.35, "Trend": 39197.55},
                            "2026-10": {"Last year, adjusted for this year": 41933.0}},
            "in_use": {"source": "Last year, adjusted for this year",
                       "months": {"2026-09": {"value": 24677.35, "p10": 17595.0, "p90": 31759.7, "shown": 30781.0},
                                  "2026-10": {"value": 41933.0, "p10": 29898.0, "p90": 53967.0}}}}
    state["ledger"] = L(state, sep9)
    iu = state["ledger"]["in_use"]
    eq(set(iu), {"2026-09"}, "only the month after the last whole one seen is kept: October is two months on")
    eq((iu["2026-09"]["value"], iu["2026-09"]["made"], iu["2026-09"]["seen_through"]), (24677.35, "2026-09-09", "2026-08"))
    eq(iu["2026-09"]["shown"], 30781.0, "with what the page showed, money already taken included")
    again = json.loads(json.dumps(sep9)); again["as_of"] = "2026-09-20"
    again["in_use"]["months"]["2026-09"]["value"] = 33000.0
    state["ledger"] = L(state, again)
    eq(state["ledger"]["in_use"]["2026-09"]["value"], 24677.35, "written once, never revised")
    oct2 = {"as_of": "2026-10-01", "seen_through": "2026-09", "actuals": {"2026-09": 38740.89},
            "predictions": {"2026-10": {"Big orders counted apart": 50568.0}},
            "in_use": {"source": "Big orders counted apart",
                       "months": {"2026-10": {"value": 50568.0, "p10": 36207.0, "p90": 64929.0, "shown": 50600.0}}}}
    state["ledger"] = L(state, oct2)
    led = state["ledger"]
    sep = [r for r in led["results"] if r["month"] == "2026-09"][0]
    eq(sep["in_use"]["source"], "Last year, adjusted for this year")
    eq(sep["in_use"]["error"], round((24677.35 - 38740.89) / 38740.89, 4))
    eq(sep["in_use"]["inside"], False, "38,741 was above its likely range")
    ok(not sep["in_use"].get("reconstructed"), "recorded at the time, not worked out afterwards")
    eq(sep["winner"], "Trend", "the closest source is still recorded beside it")
    eq(led["in_use"]["2026-10"]["source"], "Big orders counted apart", "October's is kept from the 1 Oct run")
    json.loads(json.dumps(led, allow_nan=False))
    # September as it stands in the live ledger: scored, with no source in use.
    live = {"ledger": {"predicted": {}, "results": [{
        "month": "2026-09", "actual": 38740.89, "winner": "Trend and smoothing, averaged",
        "by_source": {"Last year, adjusted for this year": {"predicted": 24677.35, "error": -0.363, "made": "2026-09-09"},
                      "Trend and smoothing, averaged": {"predicted": 39197.55, "error": 0.0118, "made": "2026-09-09"}}}]}}
    got = L(live, {"as_of": "2026-10-02"})["results"][0]["in_use"]
    eq((got["source"], got["value"], got["made"], got["seen_through"]),
       ("Last year, adjusted for this year", 24677.35, "2026-09-09", "2026-08"))
    ok(got["reconstructed"] is True and got["inside"] is False and abs(got["p90"] - 24677.35 * 1.287) < 0.01, got)
    later = L({"ledger": {"predicted": {}, "results": [{"month": "2026-10", "actual": 50000.0,
                                                        "winner": "x", "by_source": {"x": {"predicted": 1.0, "error": 0.0}}}]}},
              {"as_of": "2026-11-02"})["results"][0]
    ok("in_use" not in later, "only the month it names is filled in; anything else stays not on record")


