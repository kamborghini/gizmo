# ---- Chase desk -------------------------------------------------------------

def lia_order(num, days_ago, outstanding, email="accounts@acme.co.uk", company="Acme Events Ltd", oid=None):
    from datetime import datetime as dt, timedelta as td, timezone as tz
    created = (dt.now(tz.utc) - td(days=days_ago)).isoformat()
    return {"id": oid or (9000 + num), "order_number": num, "name": "#" + str(num),
            "created_at": created, "tags": "Purchase order unpaid", "cancelled_at": None,
            "customer": {"id": 55, "first_name": "Amy", "last_name": "Lee", "email": email},
            "email": email, "total_price": str(outstanding), "total_outstanding": str(outstanding),
            "financial_status": "pending", "currency": "GBP", "payment_terms": None,
            "billing_address": {"company": company}, "shipping_address": {"company": company}}

def with_liability(orders_list, fn):
    async def tools(registry, name, args):
        if name == "shopify_list_orders":
            return {"orders": list(orders_list)}
        return {}
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        os.remove(liability.CHASE_LOG_PATH)
    except FileNotFoundError:
        pass
    try:
        return fn()
    finally:
        shopify._tool_json = saved

@test
def t_the_chase_email_says_what_is_owed_and_by_which_orders():
    def go():
        res = run(liability.run_liability({}))
        c = res["customers"][0]
        ok(c["chase"], "an email is composed for the account")
        body = c["chase"]["body"]
        ok("Hello Acme Events Ltd" in body, "addressed to the account")
        ok("#104300" in body and "#104301" in body, "every unpaid order is listed")
        ok("£450.00" in body, "the older order's amount is there")
        ok("£120.00" in body, "and the newer one's")
        ok("Total outstanding: £570.00" in body, "the total is the sum of both")
        ok("payment reference" in body, "it asks for the order number as reference")
        eq(c["email"], "accounts@acme.co.uk", "the account's email rides along")
        ok("—" not in body and "–" not in body, "no em or en dashes in the email")
    # Net 30 assumed: 75 days old is ~45 days overdue, 40 days old is ~10 over.
    with_liability([lia_order(104300, 75, 450), lia_order(104301, 40, 120)], go)

@test
def t_the_liability_route_answers_with_the_report():
    """The Liability tab reads /api/liability, the report run_liability builds.
    Every other test built the report directly; pinned through its route
    before the route moved out of add_routes."""
    def go():
        ensure_auth()
        r = post("/api/liability", {})
        eq(r.status_code, 200, r.text)
        body = r.json()["customers"][0]["chase"]["body"]
        ok("#104300" in body and "#104301" in body and "Total outstanding: £570.00" in body,
           "the account's chase email, through the route: " + body[:200])
    with_liability([lia_order(104300, 75, 450), lia_order(104301, 40, 120)], go)

@test
def t_the_tone_steps_with_how_late_the_oldest_debt_is():
    def tone_for(days_ago):
        def go():
            res = run(liability.run_liability({}))
            return res["customers"][0]["chase"]["tone"]
        return with_liability([lia_order(104310, days_ago, 200)], go)
    eq(tone_for(20), "statement", "inside Net 30 nothing is overdue, so it is a statement")
    eq(tone_for(33), "gentle", "a few days over is a gentle reminder")
    eq(tone_for(50), "firm", "twenty days over is firmer")
    eq(tone_for(75), "final", "six weeks over is a final reminder")
    # And the wording never threatens: even final offers a way through.
    def go2():
        res = run(liability.run_liability({}))
        body = res["customers"][0]["chase"]["body"]
        ok("talk to me" in body or "way through" in body, "final stays human")
        for word in ("legal", "solicitor", "court", "debt collect"):
            ok(word not in body.lower(), "never threatens: " + word)
    with_liability([lia_order(104311, 80, 900)], go2)

@test
def t_marking_an_account_chased_is_remembered_and_shown():
    def go():
        res = run(liability.run_liability({}))
        c = res["customers"][0]
        eq(c["last_chased"], None, "never chased yet")
        r = post("/api/liability/chase", {"key": c["key"]})
        eq(r.status_code, 200, r.text)
        ok(r.json()["chased"]["at"], "the stamp has a time")
        res2 = run(liability.run_liability({}))
        ok(res2["customers"][0]["last_chased"], "and the next load shows it")
    with_liability([lia_order(104320, 60, 300)], go)

@test
def t_a_chase_stamp_that_cannot_be_saved_says_so():
    # A silently lost stamp re-creates the double-chasing this exists to stop.
    # A corrupt log is the realistic failure: the loader refuses to overwrite a
    # store it could not parse, so the stamp must fail loudly, not quietly.
    saved_path = liability.CHASE_LOG_PATH
    liability.CHASE_LOG_PATH = SCRATCH + "/chase_corrupt.json"
    with open(liability.CHASE_LOG_PATH, "w") as fh:
        fh.write("{not json")
    try:
        r = post("/api/liability/chase", {"key": "55"})
        eq(r.status_code, 500, r.text)
        ok("could not be recorded" in r.json()["error"], r.json()["error"])
        eq(open(liability.CHASE_LOG_PATH).read(), "{not json", "and the corrupt file was preserved")
    finally:
        jsonstore._poisoned_stores.discard(liability.CHASE_LOG_PATH)
        os.remove(liability.CHASE_LOG_PATH)
        liability.CHASE_LOG_PATH = saved_path


@test
def t_a_mixed_account_is_never_told_its_fresh_orders_are_overdue():
    # An account often owes one late invoice AND has a big new order inside
    # terms. Calling the whole balance overdue is the dispute a chasing email
    # must not start: every "overdue" claim covers exactly the overdue subset.
    def go():
        res = run(liability.run_liability({}))
        c = res["customers"][0]
        subj, body = c["chase"]["subject"], c["chase"]["body"]
        ok("£50.00 overdue" in subj, "the subject claims only the overdue amount: " + subj)
        ok("£5,050" not in subj, "and never the whole balance")
        ok("not yet due" in body, "the fresh order is marked not yet due")
        ok("Of that, overdue: £50.00" in body, "the totals separate overdue from outstanding")
        ok("Total outstanding: £5,050.00" in body, "while the full balance is still stated")
    with_liability([lia_order(104330, 70, 50), lia_order(104331, 1, 5000)], go)


