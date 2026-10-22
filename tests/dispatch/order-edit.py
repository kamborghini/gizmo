# =========================== order edit =====================================
ORDER_WRITES = []


async def fake_order_writer(order_id, fields):
    ORDER_WRITES.append((int(order_id), fields))
    return {"ok": True}


shopify._order_writer = fake_order_writer


def _edit(body):
    ORDER_WRITES.clear()
    b = {"order_id": 12345}
    b.update(body)
    return post("/api/order/edit", b)


@test
def t_order_edit_reads_live_rather_than_trusting_the_queue():
    """The panel prefills from THIS, not from the order object the Production
    Manager already holds: that one's note has had the proposal URL cut out of
    it and the remainder truncated, and its address may be a whole sweep old."""
    r = _edit({"op": "read"})
    ok(r.status_code == 200, "read op answers 200, got %s %s" % (r.status_code, r.text[:120]))
    d = r.json()
    ok(d["name"] == "#104239", "it names the order it read")
    ok(d["ship_to"]["postcode"] == "M1 2AB", "and returns the live address")
    ok("status" in d and "booked" in d,
       "plus what the panel has to warn about before anyone types")


@test
def t_an_edit_carries_over_every_field_the_form_did_not_send():
    """Shopify REPLACES the shipping address rather than merging it, so a form
    that posted only what it showed would blank the rest."""
    r = _edit({"ship_to": {"postcode": "M1 3CD"}})
    ok(r.status_code == 200, "accepted, got %s: %s" % (r.status_code, r.text[:140]))
    ok(r.json()["changed"] == ["postcode"], "only the postcode is reported changed")
    ok(len(ORDER_WRITES) == 1, "exactly one write")
    sent = ORDER_WRITES[0][1]["ship_to"]
    ok(sent["postcode"] == "M1 3CD", "the new postcode goes")
    ok(sent["street"] == "24 Liberty Ave" and sent["city"] == "Manchester",
       "and the untouched fields go with it")


@test
def t_a_no_op_edit_writes_nothing_and_busts_nothing():
    """A Shopify order sweep is 180 days. A save that changed nothing must not
    cost one."""
    r = _edit({"ship_to": {"postcode": "M1 2AB"}})
    ok(r.status_code == 200, "still fine")
    ok(r.json()["changed"] == [], "nothing reported changed")
    ok(not ORDER_WRITES, "and nothing was sent to Shopify")


@test
def t_an_edit_meets_the_same_address_test_the_courier_does():
    """An address the panel accepts has to survive the dispatch window minutes
    later, so both go through _addr_ready / _country_ready."""
    r = _edit({"ship_to": {"street": ""}})
    ok(r.status_code == 400, "an address with no street is refused")
    ok("street" in r.text, "and says which part is missing: " + r.text[:110])
    r = _edit({"ship_to": {"country": "Wakanda"}})
    ok(r.status_code == 400, "so is a country that is not a country")
    ok(not ORDER_WRITES, "nothing was written on either")


@test
def t_a_country_name_becomes_the_code_a_courier_needs():
    """_clean_address already knows United Kingdom is GB. Truncating it to two
    letters would give IS, which is Iceland."""
    r = _edit({"ship_to": {"country": "United Kingdom", "postcode": "M1 4EF"}})
    ok(r.status_code == 200, "accepted, got %s" % r.text[:140])
    ok(ORDER_WRITES[0][1]["ship_to"]["country"] == "GB", "stored as GB")


@test
def t_the_recipient_is_first_and_last_not_a_name_field():
    """Shopify derives an address's name from first + last, so a panel offering
    "name" would report a save and change nothing."""
    ok("name" not in orderbook._EDIT_ADDR_KEYS, "name is not in the editable set")
    r = _edit({"ship_to": {"firstname": "Joanne"}})
    ok(r.status_code == 200 and r.json()["changed"] == ["firstname"],
       "but the first name is editable: %s" % r.text[:120])


@test
def t_a_long_address_line_saves_but_says_it_will_not_print():
    r = _edit({"ship_to": {"street": "Flat 12, The Old Bonded Warehouse, Waterside Quarter"}})
    ok(r.status_code == 200, "a long line still saves - this is Shopify's record, not the label")
    ok(any("courier" in w for w in r.json()["warnings"]),
       "but the person typing is told: %s" % r.json()["warnings"])


@test
def t_tags_never_reach_shopify_from_here():
    """orderUpdate REPLACES the tag list, and this app's production queues AND
    its accounts-receivable chase list are both tag-driven. An order that is
    unpaid and untagged has no bucket anywhere, so nobody would chase it."""
    r = _edit({"tags": "whatever", "ship_to": {"postcode": "M1 9ZZ"}})
    ok(r.status_code == 200, "the request is accepted")
    sent = ORDER_WRITES[0][1]
    ok("tags" not in sent, "but the tags are not sent: %s" % sorted(sent))
    ok("tags" not in r.json()["changed"], "and they are not reported as changed")


@test
def t_the_proposal_proof_link_survives_an_untouched_note():
    """The killer: the queue's copy of the note has the proposal URL surgically
    removed and the rest cut to 500 characters. Prefilling a form from THAT and
    saving would delete the artwork proof link from Shopify for good. The panel
    reads the raw note instead, so an untouched note round-trips byte for byte."""
    saved = shopify._tool_json
    raw = ("Rush job for the Friday get-in.\n\nProposal link: "
           "https://quote.projectedimage.co.uk/p/abc123\n\n" + ("x" * 700))

    async def noted(registry, name, args):
        if name == "shopify_get_order":
            o = dict(ORDER); o["note"] = raw; return o
        return await saved(registry, name, args)
    shopify._tool_json = noted
    try:
        r = _edit({"op": "read"})
        ok(r.json()["note"] == raw, "the read hands back the note exactly as Shopify holds it")
        ok(len(r.json()["note"]) > 500, "including past the 500 chars the queue copy stops at")
        ok("quote.projectedimage.co.uk" in r.json()["note"], "proposal link and all")
        # Saving that value back unchanged must not be treated as an edit at all.
        r = _edit({"note": raw, "ship_to": {"postcode": "M1 2AB"}})
        ok(r.status_code == 200, "saving it back is fine")
        ok(r.json()["changed"] == [], "and counts as no change: %s" % r.json()["changed"])
        ok(not ORDER_WRITES, "so nothing is written and the link cannot be lost")
        # A genuine note edit does go, with the link still in it.
        r = _edit({"note": raw + "\nCollect at 8am."})
        ok(r.status_code == 200, "a real note edit is accepted")
        ok("quote.projectedimage.co.uk" in ORDER_WRITES[0][1]["note"],
           "and the proposal link is still in what goes to Shopify")
    finally:
        shopify._tool_json = saved


@test
def t_a_cancelled_order_is_a_closed_record():
    saved = shopify._tool_json

    async def dead(registry, name, args):
        if name == "shopify_get_order":
            o = dict(ORDER); o["cancelled_at"] = "2026-08-02T00:00:00Z"; return o
        return await saved(registry, name, args)
    shopify._tool_json = dead
    try:
        r = _edit({"ship_to": {"postcode": "M1 5GH"}})
        ok(r.status_code == 400, "refused, got %s" % r.status_code)
        ok("cancelled" in r.text, "and says why: " + r.text[:130])
        ok(not ORDER_WRITES, "nothing written")
    finally:
        shopify._tool_json = saved


@test
def t_changing_a_booked_parcels_address_has_to_be_said_out_loud():
    """The label is printed and the parcel is moving. Changing Shopify changes
    neither of them."""
    reset_dispatch()
    desk._record_dispatch(12345, {"tracking_number": "T-1", "carrier": "DPD",
                                     "dispatched_at": "2026-08-20T09:00:00Z"})
    try:
        r = _edit({"ship_to": {"postcode": "M1 6JK"}})
        ok(r.status_code == 400, "refused without a confirmation, got %s" % r.status_code)
        ok("already booked" in r.text and "T-1" in r.text,
           "and names the booking: " + r.text[:170])
        ok(not ORDER_WRITES, "nothing written yet")
        r = _edit({"ship_to": {"postcode": "M1 6JK"}, "confirm_booked": True})
        ok(r.status_code == 200, "confirmed, it goes through: " + r.text[:120])
        ok(len(ORDER_WRITES) == 1, "one write")
        ok(desk._load_dispatch()["12345"].get("address_changed_at"),
           "and the divergence is recorded against the shipment")
    finally:
        reset_dispatch()


@test
def t_a_diverged_parcel_is_not_silently_fulfilled_and_emailed():
    """The whole point of that flag: Mark made would otherwise email the customer
    tracking for a parcel travelling to the address the label was cut from."""
    reset_dispatch(); reset_prod()
    desk._record_dispatch(12345, {"tracking_number": "T-2", "carrier": "DPD",
                                     "address_changed_at": "2026-08-21T09:00:00Z"})
    production._mark_made(12345, True)
    try:
        FULFILLED.clear()
        r = run(orderbook._fulfill_if_ready({}, 12345))
        ok(not r["fulfilled"], "it stops")
        ok(r["reason"] == "address_changed", "for the right reason: %s" % r["reason"])
        ok(not FULFILLED, "and nothing was fulfilled or emailed")
        r2 = run(orderbook._fulfill_if_ready({}, 12345, ack_address=True))
        ok(r2["fulfilled"], "acknowledged, it proceeds: %s" % r2.get("reason"))
        ok(not desk._load_dispatch()["12345"].get("address_changed_at"),
           "and the flag clears, so the same order is not stopped twice")
    finally:
        reset_dispatch(); reset_prod()


@test
def t_only_an_admin_can_change_an_order():
    """The labels tab is the tab part-time workshop staff are given so they can
    print and dispatch, and a brand new account has EVERY tab until somebody
    sets its permissions - so the tab alone cannot be the gate for rewriting
    where a paid order ships."""
    r = post("/api/team/user", {"op": "create", "name": "Parttime", "username": "ptedit",
                                "role": "parttime"})
    ok(r.status_code == 200, "made a part-time account: " + r.text[:140])
    pw = r.json().get("starter_password")
    ok(pw, "with a starter password: " + r.text[:160])
    lg = client.post("/api/auth/login", json={"username": "ptedit", "password": pw},
                     headers={"Authorization": "Bearer " + tok()}).json()
    sess = lg.get("session")
    ok(sess, "and it can sign in: " + str(lg)[:150])
    # A starter password has to be changed before the account is live, so this
    # tests a settled part-timer rather than one still mid-setup.
    ch = post_s(sess, "/api/auth/password", {"current": pw, "new": "workshop-pw-9271"})
    ok(ch.status_code == 200, "and set its own password: " + ch.text[:140])
    sess = ch.json().get("session") or sess
    ORDER_WRITES.clear()
    r = post_s(sess, "/api/order/edit", {"order_id": 12345, "ship_to": {"postcode": "M1 7LM"}})
    ok(r.status_code == 403, "but it cannot edit an order, got %s" % r.status_code)
    ok(not ORDER_WRITES, "and nothing was written")


@test
def t_the_edit_route_is_mapped_to_a_tab():
    """_tab_denied fails open for any path it does not recognise, so a route
    that is not mapped is not gated at all."""
    paths = [p for p, _t in gate._TAB_ROUTES]
    ok(any("/api/order/edit".startswith(p) for p in paths),
       "/api/order/edit resolves to a tab")


