def _thread_with_pdf(i):
    return {"id": "t%d" % i, "subject": "Invoice %d" % i,
            "messages": [{"id": "m%d" % i, "at": "2026-08-20", "from_email": "ap@supplier.com",
                          "files": [{"id": "a%d" % i, "name": "inv.pdf", "size": 100}]}]}


@test
def t_the_consent_walk_names_the_mailbox_it_wants():
    """select_account shows Google's chooser, but a browser with one live
    session lands on THAT account anyway, so the merchant kept being offered
    the sales mailbox. Naming the address preselects the right one."""
    from urllib.parse import urlparse, parse_qs, unquote
    url = _gm.consent_url("https://x/cb", "st8", "accounts@example.com")
    # AccountChooser SWITCHES the session to the named address, then continues
    # to consent. login_hint alone is only a hint, and Google ignores it when
    # another account is signed in, which is how this kept connecting sales.
    ok(url.startswith("https://accounts.google.com/AccountChooser?"), url[:80])
    q = parse_qs(urlparse(url).query)
    eq(q["Email"][0], "accounts@example.com", "the chooser is told the address")
    inner = q["continue"][0]
    ok(inner.startswith(_gm.AUTH_ENDPOINT), "and continues to the consent screen: " + inner[:60])
    iq = parse_qs(urlparse(inner).query)
    eq(iq["login_hint"][0], "accounts@example.com", "which also carries the hint")
    # select_account FORCES the picker, which is exactly what overrides a hint.
    eq(iq["prompt"][0], "consent", "and does not also ask for the picker: %s" % iq["prompt"])
    plain = _gm.consent_url("https://x/cb", "st8")
    ok("AccountChooser" not in plain and "login_hint" not in plain,
       "nothing is forced when no address was given")
    ok("select_account" in plain, "and without an address the chooser is still forced")


@test
def t_token_files_are_not_world_readable():
    """A leaked refresh token would let anyone read the mailbox, so its file
    is owner-only."""
    import stat
    import google_mail as _gm
    _gm.save_connection("rt", "sales@example.com")
    mode = stat.S_IMODE(os.stat(_gm.SALES.token_path).st_mode)
    eq(mode & 0o077, 0, "the mailbox token is owner-only: %o" % mode)
    _gm.disconnect()


@test
def t_the_panel_shows_the_fields_a_courier_actually_rejects():
    """Two fixes were shipped against one captured envelope without anyone -
    including the person who wrote them - being able to tell whether the values
    had changed, because the redaction masked the postcode and the county: the
    exact two fields the courier was complaining about. A diagnostic that hides
    the evidence is not a diagnostic. Identity stays hidden; geography does
    not."""
    xml = ("<wo:RecipientsDetails>"
           "<m:Name>Alexander Robertson</m:Name><m:Address1>Unit A2 Bluebell</m:Address1>"
           "<m:Company>Alexander Robertson</m:Company><m:Email>a@b.c</m:Email>"
           "<m:Phone>0123</m:Phone><m:City>Dublin</m:City>"
           "<m:Postalcode>D12 VC2N</m:Postalcode><m:State_Code>IE</m:State_Code>"
           "</wo:RecipientsDetails>")
    out = worldoptions._redacted(xml)
    for shown in ("D12 VC2N", "IE"):
        ok(shown in out, "%r is visible, because a courier validates it: %s" % (shown, out))
    for hidden in ("Alexander Robertson", "Unit A2 Bluebell", "a@b.c", "0123", "Dublin"):
        ok(hidden not in out, "%r stays hidden" % hidden)
    # Credentials never appear, whatever else changes.
    creds = worldoptions._redacted("<m:Key>secret</m:Key><m:Password>pw</m:Password>"
                                   "<m:MeterNumber>123</m:MeterNumber><ad:ReceiverTaxId>IE99</ad:ReceiverTaxId>")
    for never in ("secret", "pw", "123", "IE99"):
        ok(never not in creds, "%r is never shown" % never)
    # A blank stays visibly blank: which fields were EMPTY is half the evidence.
    eq(worldoptions._redacted("<m:State></m:State>"), "<m:State></m:State>",
       "an empty element is not turned into stars")


@test
def t_a_booking_can_carry_its_own_collection_arrangement():
    """World Options has no endpoint for booking a collection on its own - their
    service exposes Rate, Shipment and Void and nothing else - so a collection
    is asked for ALONGSIDE a parcel. The arrangement was buried in Settings and
    applied to every booking; it can now be chosen for one job, because a
    different job may go out with a different carrier."""
    src = copilot_source()
    ok("collection_option: str = \"\"" in src, "the booking takes one")
    i = src.index("_asked_collection = str(collection_option")
    seg = ' '.join(src[i:i + 160].split())
    ok('_plan["arrangement"]' in seg,
       "and otherwise asks for what the plan says for THIS courier: " + seg[:90])
    # Per carrier first, the standing setting for anyone unconfigured.
    eq(desk._collection_for({"collection_by_carrier": {"UPS": "I_Have_Daily_Collection"},
                                "collection_option": "I_Need_To_Book_A_Collection"}, "UPS"),
       "I_Have_Daily_Collection", "a configured courier uses its own arrangement")
    eq(desk._collection_for({"collection_by_carrier": {"UPS": "I_Have_Daily_Collection"},
                                "collection_option": "I_Need_To_Book_A_Collection"}, "DHL"),
       "I_Need_To_Book_A_Collection", "an unconfigured one falls back to the standing setting")
    eq(desk._collection_for({"collection_option": "I_Have_Daily_Collection"}, "ups"),
       "I_Have_Daily_Collection", "the carrier code is matched however it is cased")
    eq(desk._collection_for({"collection_by_carrier": "not a dict",
                                "collection_option": "I_Have_Daily_Collection"}, "UPS"),
       "I_Have_Daily_Collection", "and a corrupt map does not take the booking down")
    # It must not accept anything the courier does not offer.
    ok("not in worldoptions.COLLECTION_OPTIONS" in src,
       "the route validates it against the courier's own list")
    for v in ("I_Need_To_Book_A_Collection", "I_Have_Daily_Collection",
              "I_Already_Have_Collection_Scheduled"):
        ok(v in worldoptions.COLLECTION_OPTIONS, "%s is a real arrangement" % v)


@test
def t_clearing_a_collection_actually_clears_it():
    """Found auditing this week's work, and it made the button a lie. Clearing
    popped the ledger entry, but the booking that secured the collection is
    still on the dispatch record, so the very next read re-derived it. "The van
    has been, book another" did nothing at all."""
    from datetime import datetime as _dt, timezone as _tz
    today = clock._london_today().isoformat()   # the day the code reckons in (London), not the UTC date
    desk._write_dispatch({"9001": {"carrier_name": "DHL", "carrier_label": "DHL Express",
                                      "collection_date": "CN-1", "order_name": "#1",
                                      "ready_date": "", "dispatched_at": today + "T09:00:00+00:00"}})
    desk._write_collections({})
    ok("DHL" in desk._collections_for(today), "the courier's booking shows a van coming")
    # Clear it the way the route does.
    desk._write_collections({"DHL": {"date": today, "cleared": True}})
    ok("DHL" not in desk._collections_for(today),
       "and once cleared it stays cleared, though the booking is still on record")
    # Which means the next parcel asks again, as intended.
    cfg = {"collection_by_carrier": {"DHL": "I_Need_To_Book_A_Collection"}}
    eq(desk._collection_plan(cfg, "DHL", desk._collections_for(today))["arrangement"],
       "I_Need_To_Book_A_Collection", "so the next DHL parcel books a fresh one")
    # A clear for a DIFFERENT day does not silence today.
    desk._write_collections({"DHL": {"date": "2020-01-01", "cleared": True}})
    ok("DHL" in desk._collections_for(today), "yesterday's clear is not today's")
    desk._write_collections({}); desk._write_dispatch({})


@test
def t_the_latest_booking_of_the_day_is_the_one_that_counts():
    """Dict order is insertion order, so "first one found" meant the OLDEST
    booking of the day. After a clear and a re-book that is the stale one, and
    its reference is the one that would be read out to the courier."""
    from datetime import datetime as _dt, timezone as _tz
    today = clock._london_today().isoformat()   # the day the code reckons in (London), not the UTC date
    desk._write_dispatch({
        "1": {"carrier_name": "DHL", "collection_date": "OLD-1", "order_name": "#1",
              "dispatched_at": today + "T08:00:00+00:00"},
        "2": {"carrier_name": "DHL", "collection_date": "NEW-2", "order_name": "#2",
              "dispatched_at": today + "T15:00:00+00:00"},
    })
    got = desk._collections_from_dispatch(today)
    eq(got["DHL"]["ref"], "NEW-2", "the most recent collection of the day is the live one")
    desk._write_dispatch({})


