@test
def t_an_erasure_takes_the_deals_leads_and_enquiry_email_too():
    """A7. customers/redact tombstoned the contact and the threads they sent,
    and left their deal, their lead and the storefront enquiry (sent from the
    shop's own address) with their name, message and phone number."""
    def go():
        ensure_auth()
        crm_wipe()
        addr = "jo.smith@example.com"
        store = {"threads": {}}
        enq = {"id": "e1", "historyId": "1", "subject": "New customer message on 20 September", "messages": [
            dict(_mk_msg("e1-m1", "Store", MBOX, "2026-09-20T09:00:00+00:00",
                         snippet="Name: Jo Smith Email: jo.smith@example.com Phone: 07700 900123"),
                 labels=["INBOX"])]}
        mail._mail_apply_thread(store, enq, MBOX)
        mail._write_mail(store)
        d = salesdesk._load_crm()
        d["persons"]["p1"] = {"id": "p1", "name": "Jo Smith", "emails": [addr], "created_at": "", "updated_at": ""}
        d["deals"]["d1"] = {"id": "d1", "title": "Jo Smith - website enquiry", "person_id": "p1",
                            "mail_thread_id": "e1", "stage_id": (d["stages"][0]["id"] if d["stages"] else ""),
                            "notes": [{"id": "n1", "text": "Given on the form: phone 07700 900123"}],
                            "pd_id": "777"}
        d["leads"]["l1"] = {"id": "l1", "title": "Jo Smith lead", "person_id": "p1"}
        d["activities"]["a1"] = {"id": "a1", "subject": "Call Jo", "deal_id": "d1", "pd_id": "888"}
        salesdesk._write_crm(d)
        out = privacy._redact_customer(addr, "555")
        d = salesdesk._load_crm()
        eq((d["deals"].get("d1"), d["leads"].get("l1"), d["activities"].get("a1")), (None, None, None),
           "the deal, the lead and the deal's task are gone")
        ok("777" in (d.get("pd_deleted_deals") or []), "and an import cannot bring the deal back")
        ok("e1" not in mail._load_mail()["threads"], "the storefront enquiry is gone from the board")
        st = mail._load_mail()
        mail._mail_apply_thread(st, enq, MBOX)
        ok("e1" not in st["threads"], "and the sync cannot fetch it back")
        ok(out["erased"] >= 4, out)
        # Nobody else's record goes with them. Bob's thread mentions Jo; an
        # organisation's won deal had Jo as its contact; and erasing
        # sales@firm.co is not erasing sales@firm.co.uk.
        st = mail._load_mail()
        bob = {"id": "b1", "historyId": "1", "subject": "Order", "messages": [
            _mk_msg("b1-m1", "Bob", "bob@venue.com", "2026-09-21T09:00:00+00:00",
                    snippet="please send the invoice to our finance lead jo.smith@example.com")]}
        uk = {"id": "k1", "historyId": "1", "subject": "Hello", "messages": [
            _mk_msg("k1-m1", "Sam", "sales@firm.co.uk", "2026-09-21T09:00:00+00:00", snippet="hi")]}
        mail._mail_apply_thread(st, bob, MBOX); mail._mail_apply_thread(st, uk, MBOX)
        mail._write_mail(st)
        d = salesdesk._load_crm()
        d["persons"]["p2"] = {"id": "p2", "name": "Ann Other", "emails": ["ann@other.com"], "phones": ["07700 900555"]}
        d["deals"]["d2"] = {"id": "d2", "title": "Northern Stage: Ann Other rig", "person_id": "p2",
                            "org_id": "o1", "status": "won", "value": 18000, "pd_id": "999",
                            "notes": [{"id": "n2", "text": "Ann Other on 07700 900555 signed it off"}]}
        salesdesk._write_crm(d)
        privacy._redact_customer("jo.smith@example.com", "555")
        privacy._redact_customer("ann@other.com", "556")
        privacy._redact_customer("sales@firm.co", "557")
        st = mail._load_mail()
        ok("b1" in st["threads"], "Bob's thread stays: he wrote it")
        ok("jo.smith@example.com" not in st["threads"]["b1"]["snippet"], "with Jo's address scrubbed from it")
        mail._mail_apply_thread(st, dict(bob, messages=bob["messages"] + [
            _mk_msg("b1-m2", "Bob", "bob@venue.com", "2026-09-22T09:00:00+00:00", snippet="new order")]), MBOX)
        ok("b1" in st["threads"] and len(st["threads"]["b1"]["messages"]) == 2, "and Bob's next email still arrives")
        ok("k1" in st["threads"], "erasing sales@firm.co leaves sales@firm.co.uk alone")
        d = salesdesk._load_crm()
        deal = d["deals"].get("d2") or {}
        ok(deal.get("status") == "won" and "999" not in (d.get("pd_deleted_deals") or []),
           "the organisation's won deal stays, and is not tombstoned")
        ok(not deal.get("person_id") and "Ann Other" not in deal.get("title", "")
           and "07700 900555" not in deal["notes"][0]["text"], "without Ann in it: " + str(deal))
    with_mail(go)


@test
def t_a_second_import_on_the_same_day_keeps_the_first_restore_point():
    """A8. The pre-import snapshot was named by the day, so a second import that
    day replaced the only copy of the CRM from before the first."""
    import zipfile, pipedrive as _pd
    saved = (backup.BACKUP_STATE_PATH, backup.BACKUP_SNAPSHOT_DIR)
    backup.BACKUP_STATE_PATH = SCRATCH + "/backup_state_a8.json"
    backup.BACKUP_SNAPSHOT_DIR = SCRATCH + "/snapshots_a8"
    def go():
        ensure_auth()
        crm_wipe()
        post("/api/crm/contact", {"op": "org_add", "name": "Typed by hand"})
        async def fake_export(progress=None):
            return dict(PD_EXPORT)
        was = (_pd.export, _pd.API_TOKEN)
        _pd.export, _pd.API_TOKEN = fake_export, "t"
        try:
            eq(post("/api/crm/import", {"go": True}).status_code, 200)
            eq(post("/api/crm/import", {"go": True}).status_code, 200)
        finally:
            _pd.export, _pd.API_TOKEN = was
        snaps = sorted(glob.glob(backup.BACKUP_SNAPSHOT_DIR + "/*.zip"), key=os.path.getmtime)
        eq(len(snaps), 2, "two imports, two restore points: " + str(snaps))
        for _ in range(4):
            backup._weekly_snapshot(True)          # three, four, five and six runs that day
        still = sorted(glob.glob(backup.BACKUP_SNAPSHOT_DIR + "/*.zip"), key=os.path.getmtime)
        ok(snaps[0] in still, "however many runs that day, the one from before the first is kept")
        with zipfile.ZipFile(snaps[0]) as z:
            first = json.loads(z.read("volume/crm.json"))["crm"]
        eq(len(first["deals"]), 0, "the first still holds the CRM from before any import")
        ok(any(o.get("name") == "Typed by hand" and not o.get("pd_id") for o in first["orgs"].values()))
    try:
        with_accounts(go)
    finally:
        backup.BACKUP_STATE_PATH, backup.BACKUP_SNAPSHOT_DIR = saved


@test
def t_a_gateway_error_on_a_booking_says_it_may_have_been_booked():
    """A9. An HTML 504 from World Options' edge was a plain failure, and the
    page re-armed Book, which booked and charged again."""
    import httpx as _hx
    ensure_auth()
    post("/api/shipping/config", {"op": "set", "meter_number": "METER-9999", "key": "KEY-abc",
                                   "password": "PW-xyz",
                                   "origin": {"street": "1 Mill St", "postcode": "LS1 1AA", "country": "GB",
                                              "city": "Leeds", "company": "PI", "phone": "0113 555 1111",
                                              "email": "shop@projectedimage.com"}})
    reset_dispatch(); reset_prod()
    posts = []
    def handler(request):
        if "DoShipment" in request.content.decode():
            posts.append(1)
            return _hx.Response(504, text="<html><body><h1>504 Gateway Time-out</h1></body></html>")
        return _hx.Response(200, text=RATE_XML)
    Real = worldoptions.httpx.AsyncClient
    class Stub(Real):
        def __init__(self, *a, **kw):
            kw["transport"] = _hx.MockTransport(handler)
            super().__init__(*a, **kw)
    saved = (worldoptions._soap_call, worldoptions.httpx.AsyncClient)
    worldoptions._soap_call, worldoptions.httpx.AsyncClient = REAL_SOAP_CALL, Stub
    try:
        r = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX})
        err = r.json().get("error", "")
        ok("MAY still have been booked" in err, "the booking may exist, and the page is told so: " + err)
        eq(len(posts), 1, "and it is never sent a second time by itself")
        page = pagesource.join(HERE)
        rx = re.search(r"const BOOKING_UNKNOWN = /(.*?)/i;", page).group(1)
        ok(re.search(rx, err, re.I), "which is what holds the Book button on the page")
        ok(page.count("BOOKING_UNKNOWN.test(msg)") == 2,
           "on the order panel and the pasted-address panel alike")
        def handler403(request):
            if "DoShipment" in request.content.decode():
                return _hx.Response(403, text="<!DOCTYPE html><html><body>Forbidden</body></html>")
            return _hx.Response(200, text=RATE_XML)
        class Stub403(Real):
            def __init__(self, *a, **kw):
                kw["transport"] = _hx.MockTransport(handler403)
                super().__init__(*a, **kw)
        worldoptions.httpx.AsyncClient = Stub403
        reset_dispatch()
        err2 = post("/api/dispatch/book", {"order_id": 12345, "option": OPT, "box": BOX}).json().get("error", "")
        ok(not re.search(rx, err2, re.I), "a 4xx refusal is a definite failure, not a maybe: " + err2)
    finally:
        worldoptions._soap_call, worldoptions.httpx.AsyncClient = saved
        reset_dispatch()


@test
def t_gmail_and_apple_mail_attachments_are_listed():
    """A10. Any part with a Content-ID or an inline disposition was taken for a
    signature logo: Gmail puts a Content-ID on every attachment and Apple Mail
    sends PDFs inline, so both vanished from the Inbox and from reconciliation."""
    import base64 as _b64
    enc = lambda x: _b64.urlsafe_b64encode(x.encode()).decode().rstrip("=")
    def thread(parts):
        return {"id": "t1", "messages": [{"id": "m1", "labelIds": ["INBOX"], "payload": {
            "mimeType": "multipart/mixed", "headers": [{"name": "From", "value": "Jo <jo@c.com>"}],
            "parts": parts}}]}
    html = {"mimeType": "text/html",
            "body": {"data": enc('<p>Hi</p><img src="cid:image001.png@01D9">')}}
    gmail = {"mimeType": "application/pdf", "filename": "Invoice INV-2291.pdf",
             "headers": [{"name": "Content-Disposition", "value": 'attachment; filename="Invoice INV-2291.pdf"'},
                         {"name": "Content-ID", "value": "<f_lxyz0>"}, {"name": "X-Attachment-Id", "value": "f_lxyz0"}],
             "body": {"attachmentId": "a1", "size": 88000}}
    apple = {"mimeType": "application/pdf", "filename": "artwork.pdf",
             "headers": [{"name": "Content-Disposition", "value": "inline; filename=artwork.pdf"}],
             "body": {"attachmentId": "a2", "size": 400000}}
    logo = {"mimeType": "image/png", "filename": "image001.png",
            "headers": [{"name": "Content-Disposition", "value": 'inline; filename="image001.png"'},
                        {"name": "Content-ID", "value": "<image001.png@01D9>"}],
            "body": {"attachmentId": "a3", "size": 6000}}
    async def fake_call(method, path, params=None, acct=None, **kw):
        return thread([html, gmail, apple, logo])
    saved = _gm._call
    _gm._call = fake_call
    try:
        t = run_async(_gm.get_thread("t1"))
        eq([f["name"] for f in t["messages"][0]["files"]], ["Invoice INV-2291.pdf", "artwork.pdf"],
           "the Gmail and Apple Mail attachments are files; the signature logo the email draws is not")
    finally:
        _gm._call = saved


@test
def t_a_filter_that_assigns_and_archives_does_not_close_the_email():
    """A11. The filter's own "take it out of the inbox" was read back on the
    next sync as somebody archiving it in Gmail, and the owner's email closed."""
    def go():
        ensure_auth()
        _gm.save_connection("rt-test", MBOX)
        ann, _s, _p = ready_user("Ann", "ann", role="member")
        post("/api/mail/rules", {"op": "save", "rule": {
            "name": "Supplier invoices to Ann", "assign": ann, "folder": "Suppliers", "archive": True,
            "conditions": [{"field": "domain", "op": "is", "value": "glassworks.co.uk"}]}})
        in_inbox = {"s1"}
        msg = {"id": "s1-m1", "from_name": "Glassworks", "from_email": "accounts@glassworks.co.uk",
               "at": "2026-09-22T09:00:00+00:00", "snippet": "invoice attached", "labels": ["INBOX", "UNREAD"],
               "files": []}
        async def listing(q, n):
            return {"threads": [{"id": t, "snippet": "", "historyId": "h1"} for t in sorted(in_inbox)],
                    "complete": True}
        async def get_thread(tid, acct=None):
            return {"id": tid, "historyId": "h1", "subject": "Invoice 2291", "messages": [msg]}
        async def modify(tid, add=None, remove=None):
            if remove and "INBOX" in remove:
                in_inbox.discard(tid)
        async def label(name, known):
            known[name] = "L_" + name; return known[name]
        async def ids(q, max_results=500, pages=8, acct=None, out_complete=None):
            if out_complete is not None:
                out_complete.append(True)
            return {"s1"}
        saved = (_gm.list_threads, _gm.get_thread, _gm.modify_thread, _gm.ensure_label, _gm.list_thread_ids)
        _gm.list_threads, _gm.get_thread, _gm.modify_thread, _gm.ensure_label, _gm.list_thread_ids = \
            listing, get_thread, modify, label, ids
        try:
            run_async(mail._mail_sync_now(force=True))
            ok("s1" not in in_inbox, "the filter took it out of the Gmail inbox")
            run_async(mail._mail_sync_now(force=True))
            t = mail._load_mail()["threads"]["s1"]
            eq((t["state"], t["owner"]), ("assigned", ann), "and it is still Ann's, open")
            in_inbox.add("s1")                    # it comes back to the inbox
            run_async(mail._mail_sync_now(force=True))
            in_inbox.discard("s1")                # and then a person archives it in Gmail
            run_async(mail._mail_sync_now(force=True))
            eq(mail._load_mail()["threads"]["s1"].get("closed_by"), "archive",
               "a person's archive still closes it")
        finally:
            _gm.list_threads, _gm.get_thread, _gm.modify_thread, _gm.ensure_label, _gm.list_thread_ids = saved
    with_mail(go)


@test
def t_a_logo_drawn_by_a_second_html_part_is_still_a_logo():
    """Review of A10. Apple Mail splits a message into several HTML parts
    around its images; the cids of only the first were read."""
    import base64 as _b64
    enc = lambda x: _b64.urlsafe_b64encode(x.encode()).decode().rstrip("=")
    parts = [{"mimeType": "text/html", "body": {"data": enc("<p>Hello</p>")}},
             {"mimeType": "image/png", "filename": "sig-logo.png",
              "headers": [{"name": "Content-ID", "value": "<sig@apple>"},
                          {"name": "Content-Disposition", "value": "inline; filename=sig-logo.png"}],
              "body": {"attachmentId": "a1", "size": 5000}},
             {"mimeType": "text/html", "body": {"data": enc('<img src="cid:sig@apple"><p>Jo</p>')}},
             {"mimeType": "application/pdf", "filename": "quote.pdf",
              "headers": [{"name": "Content-Disposition", "value": "inline; filename=quote.pdf"}],
              "body": {"attachmentId": "a2", "size": 90000}}]
    async def fake_call(method, path, params=None, acct=None, **kw):
        return {"id": "t1", "messages": [{"id": "m1", "labelIds": ["INBOX"], "payload": {
            "mimeType": "multipart/mixed", "headers": [{"name": "From", "value": "Jo <jo@c.com>"}],
            "parts": parts}}]}
    saved = _gm._call
    _gm._call = fake_call
    try:
        t = run_async(_gm.get_thread("t1"))
        eq([f["name"] for f in t["messages"][0]["files"]], ["quote.pdf"])
    finally:
        _gm._call = saved


@test
def t_an_erasure_stays_erased_and_takes_only_theirs():
    """Review of A7. The next Pipedrive import wrote the person back into a
    kept organisation deal; an enquiry that named a company was kept as an
    organisation's deal, message and all; a one-word name was scrubbed out of
    other words; and a kept thread still named them in its Cc, and the next
    sync put their address back in its snippet."""
    def go():
        ensure_auth()
        crm_wipe()
        d = salesdesk._load_crm()
        d["orgs"]["o1"] = {"id": "o1", "name": "Northern Stage", "pd_id": "501"}
        d["persons"]["p1"] = {"id": "p1", "name": "Sarah Whitfield", "emails": ["sarah@ns.co.uk"],
                              "phones": ["0191 111"], "org_id": "o1", "pd_id": "601"}
        d["deals"]["d1"] = {"id": "d1", "title": "Sarah Whitfield - 12 steel gobos", "person_id": "p1",
                            "org_id": "o1", "status": "won", "pd_id": "701", "notes": [],
                            "changelog": [{"at": "", "field": "created", "from": "",
                                           "to": "Sarah Whitfield - 12 steel gobos"}]}
        # Mentions of her in records that are not hers.
        d["orgs"]["o1"]["notes"] = [{"id": "n9", "text": "Buyer is Sarah Whitfield, 0191 111"}]
        d["activities"]["a9"] = {"id": "a9", "subject": "Ask about Sarah Whitfield's order", "org_id": "o1",
                                 "note": "", "location": ""}
        d["activities"]["a1"] = {"id": "a1", "subject": "Call Sarah Whitfield", "deal_id": "d1",
                                 "person_id": "p1", "note": "Rang Sarah Whitfield on 0191 111", "pd_id": "801"}
        d["orgs"]["o2"] = {"id": "o2", "name": "Jo Smith Photography"}
        d["persons"]["p2"] = {"id": "p2", "name": "Jo Smith", "emails": ["jo@photo.com"], "org_id": "o2"}
        d["deals"]["d2"] = {"id": "d2", "title": "Jo Smith - website enquiry", "person_id": "p2",
                            "org_id": "o2", "source": "Website form", "mail_thread_id": "e9", "notes": []}
        d["persons"]["p3"] = {"id": "p3", "name": "Will", "emails": ["will@ns.co.uk"], "org_id": "o1"}
        d["deals"]["d3"] = {"id": "d3", "title": "Northern Stage - Willow set", "person_id": "p3",
                            "org_id": "o1", "status": "open", "notes": [{"id": "n3", "text": "They will need 40 gobos"}]}
        salesdesk._write_crm(d)
        st = mail._load_mail()
        bob = {"id": "b1", "historyId": "1", "subject": "Order", "messages": [
            dict(_mk_msg("b1-m1", "Bob", "bob@venue.com", "2026-09-21T09:00:00+00:00",
                         snippet="copying in sarah@ns.co.uk from finance"),
                 cc="Sarah Whitfield <sarah@ns.co.uk>, Ann <ann@venue.com>")]}
        mail._mail_apply_thread(st, bob, MBOX)
        mail._write_mail(st)
        for a in ("sarah@ns.co.uk", "jo@photo.com", "will@ns.co.uk"):
            privacy._redact_customer(a, "1")
        d = salesdesk._load_crm()
        deal, act = d["deals"]["d1"], d["activities"]["a1"]
        ok("Sarah" not in deal["title"] and "Sarah" not in act["subject"] and "0191" not in act["note"],
           "the kept deal and its task no longer name her: " + str((deal["title"], act)))
        ok(not deal.get("edited_here") and not act.get("edited_here"),
           "and are not frozen: Pipedrive's later changes to them still import")
        eq(deal["changelog"][0]["to"], "[erased] - 12 steel gobos", "nor in the deal's changelog")
        eq(d["orgs"]["o1"]["notes"][0]["text"], "Buyer is [erased], [erased]", "nor in anybody else's notes")
        eq(d["activities"]["a9"]["subject"], "Ask about [erased]'s order", "nor in their tasks")
        ok("whitfield" not in json.dumps(d).lower(), "nowhere in the CRM")
        ok("d2" not in d["deals"] and "o2" not in d["orgs"],
           "an enquiry is the person's own, and the company typed into it goes with it")
        eq(d["deals"]["d3"]["title"], "Northern Stage - Willow set", "a one-word name is not cut out of words")
        eq(d["deals"]["d3"]["notes"][0]["text"], "They will need 40 gobos")
        st = mail._load_mail()
        m = st["threads"]["b1"]["messages"][0]
        ok("sarah" not in m.get("cc", "").lower() and "ann@venue.com" in m.get("cc", ""),
           "her entry is gone from the Cc, and nobody else's: " + m.get("cc", ""))
        mail._mail_apply_thread(st, dict(bob, messages=bob["messages"] + [
            _mk_msg("b1-m2", "Bob", "bob@venue.com", "2026-09-22T09:00:00+00:00", snippet="thanks")]), MBOX)
        ok("sarah@ns.co.uk" not in json.dumps(st["threads"]["b1"]), "and the next sync does not put her back")
    with_mail(go)


def _pd_export_with(**changes):
    out = _copy.deepcopy(PD_EXPORT)
    for k, v in changes.items():
        out[k] = v
    return out


@test
def t_an_erased_persons_organisation_deals_keep_updating_without_them():
    """Cameron's call on the A7 review note: an organisation's deal kept after
    one of its contacts was erased was frozen against the import, so later
    Pipedrive changes (stage, value, won) never arrived. It keeps updating, and
    every import takes the person out again: by the keyed hashes the erasure
    left when Pipedrive still has them, and when it has dropped them too."""
    import pipedrive as _pd
    def go():
        ensure_auth(); crm_wipe()
        v1 = _pd_export_with(
            deals=[dict(PD_EXPORT["deals"][0], title="Sarah Whitfield - 12 steel gobos"),
                   dict(PD_EXPORT["deals"][1], title="Glass sample for Sarah Whitfield")],
            activities=[dict(PD_EXPORT["activities"][0], subject="Chase Sarah Whitfield",
                             note="Rang Sarah Whitfield on 0191 111, no answer")],
            notes=[dict(PD_EXPORT["notes"][0], text="Sarah Whitfield wants them before the show")])
        feed = {"x": v1}
        async def fake_export(progress=None):
            return _copy.deepcopy(feed["x"])
        saved = (_pd.export, _pd.API_TOKEN)
        _pd.export, _pd.API_TOKEN = fake_export, "t"
        try:
            eq(post("/api/crm/import", {"go": True}).status_code, 200)
            privacy._redact_customer("sarah@lumen.co.uk", "901")
            d = salesdesk._load_crm()
            raw = json.dumps(d).lower()
            for bit in ("whitfield", "sarah@lumen.co.uk", "s.whitfield@lumen.co.uk", "0191 111", "0191111"):
                ok(bit not in raw, "the CRM file keeps nothing that names her, not even to scrub her: " + bit)
            ok(d.get("erased_marks") and re.fullmatch(r"[0-9a-f]{32}", d.get("erased_salt") or ""),
               "only keyed hashes")
            won = [v for v in d["deals"].values() if v.get("pd_id") == "30"][0]
            ok(not won.get("edited_here"), "the kept deal is not frozen")
            # Pipedrive moves on: the lost deal is re-opened and won for more,
            # a note and a task arrive, all naming her.
            v2 = _copy.deepcopy(v1)
            v2["deals"][1].update(status="won", value=90.0, won_at="2026-09-20T09:00:00Z", lost_at="",
                                  lost_reason="", updated_at="2026-09-20T09:00:00Z",
                                  title="Glass sample for Sarah  Whitfield (reorder)")
            v2["notes"].append({"pd_id": "51", "deal_pd_id": "31", "person_pd_id": "", "org_pd_id": "",
                                "text": "Approved by S. Whitfield? No: by Sarah Whitfield, +44 191 111 0000 is not hers",
                                "at": "2026-09-20T09:00:00Z"})
            v2["activities"][0]["subject"] = "Chase sarah whitfield again"
            feed["x"] = v2
            pre = post("/api/crm/import", {}).json()
            ok(pre["report"]["erased"]["people"] == 1 and pre["report"]["erased"]["scrubbed"] >= 3,
               "the preview counts her, without naming her: %r" % pre["report"].get("erased"))
            eq(post("/api/crm/import", {"go": True}).status_code, 200)
            d = salesdesk._load_crm()
            g = [v for v in d["deals"].values() if v.get("pd_id") == "31"][0]
            eq((g["status"], g["value"]), ("won", 90.0), "Pipedrive's change arrived")
            eq(g["title"], "Glass sample for [erased] (reorder)")
            ok(not g.get("person_id"), "without her as its contact")
            ok(not any(p.get("pd_id") == "20" for p in d["persons"].values()), "and she is not brought back")
            note = [n for n in g["notes"] if n.get("pd_id") == "51"][0]["text"]
            eq(note, "Approved by S. Whitfield? No: by [erased], +44 191 111 0000 is not hers",
               "her full name goes; one initial and a surname alone, and somebody else's number, stay")
            act = [a for a in d["activities"].values() if a.get("pd_id") == "40"][0]
            eq(act["subject"], "Chase [erased] again")
            # Pipedrive drops her contact too, and a deal still carries her
            # name, surname first this time: the hashes still know it.
            v3 = _copy.deepcopy(v2)
            v3["persons"] = []
            v3["deals"][0]["title"] = "Whitfield, Sarah: 12 steel gobos"
            v3["deals"][0]["person_pd_id"] = ""
            feed["x"] = v3
            eq(post("/api/crm/import", {"go": True}).status_code, 200)
            d = salesdesk._load_crm()
            eq([v for v in d["deals"].values() if v.get("pd_id") == "30"][0]["title"], "[erased]: 12 steel gobos")
            ok("whitfield" not in json.dumps(d).lower().replace("s. whitfield", ""), "nowhere else either")
        finally:
            _pd.export, _pd.API_TOKEN = saved
    with_mail(go)


@test
def t_an_erased_address_keeps_its_person_out_of_every_import():
    """A person erased before the CRM ever held them, and one erased before the
    keyed hashes existed (the mailbox's list of erased addresses is all that
    remembers them), are still recognised by their address: not brought back,
    and their name and number taken out of the deals they were on. A contact
    deleted by hand is not an erasure, and their name is left alone."""
    import pipedrive as _pd
    def go():
        ensure_auth(); crm_wipe()
        privacy._redact_customer("nina@lumen.co.uk", "902")          # never in the CRM
        st = mail._load_mail()
        st["redacted"] = list(st.get("redacted") or []) + ["olga@lumen.co.uk"]   # an erasure from before
        mail._write_mail(st)
        d = salesdesk._load_crm()
        d["pd_deleted_persons"] = list(d.get("pd_deleted_persons") or []) + ["24"]   # deleted by hand
        salesdesk._write_crm(d)
        people = [dict(PD_EXPORT["persons"][0]),
                  {"pd_id": "22", "name": "Nina Patel", "org_pd_id": "10", "emails": ["Nina@Lumen.co.uk"],
                   "phones": ["07700 900222"], "created_at": "", "updated_at": ""},
                  {"pd_id": "23", "name": "Olga Ivanova", "org_pd_id": "10", "emails": ["olga@lumen.co.uk"],
                   "phones": [], "created_at": "", "updated_at": ""},
                  {"pd_id": "24", "name": "Tom Baker", "org_pd_id": "10", "emails": ["tom@lumen.co.uk"],
                   "phones": [], "created_at": "", "updated_at": ""}]
        base = dict(PD_EXPORT["deals"][0])
        deals = [dict(base, pd_id="32", title="Nina Patel spares, call 07700900222", person_pd_id="22"),
                 dict(base, pd_id="33", title="Olga Ivanova touring rig", person_pd_id="23"),
                 dict(base, pd_id="34", title="Tom Baker rig", person_pd_id="24")]
        async def fake_export(progress=None):
            return _pd_export_with(persons=people, deals=deals, activities=[], notes=[])
        saved = (_pd.export, _pd.API_TOKEN)
        _pd.export, _pd.API_TOKEN = fake_export, "t"
        try:
            r = post("/api/crm/import", {"go": True}).json()
            eq(r["report"]["erased"]["people"], 2, r["report"].get("erased"))
            d = salesdesk._load_crm()
            names = {p.get("name") for p in d["persons"].values()}
            eq(names, {"Sarah Whitfield"}, "neither erased person is brought back, and the deleted one stays deleted")
            titles = {v["pd_id"]: v["title"] for v in d["deals"].values()}
            eq(titles["32"], "[erased] spares, call [erased]")
            eq(titles["33"], "[erased] touring rig")
            eq(titles["34"], "Tom Baker rig", "a hand-deleted contact was not erased: his name stays")
            ok("22" in d["pd_deleted_persons"] and "23" in d["pd_deleted_persons"], "known by id from now on")
            ok("nina" not in json.dumps(d).lower() and "olga" not in json.dumps(d).lower(), "and never in the clear")
            # Pipedrive drops Olga's contact; her deal keeps her name. The
            # first import left her keyed hashes, so the second still knows it.
            people[:] = [p for p in people if p["pd_id"] != "23"]
            deals[1]["person_pd_id"] = ""
            st = mail._load_mail(); st["redacted"] = [a for a in st["redacted"] if a != "olga@lumen.co.uk"]
            mail._write_mail(st)
            post("/api/crm/import", {"go": True})
            eq({v["pd_id"]: v["title"] for v in salesdesk._load_crm()["deals"].values()}["33"], "[erased] touring rig")
        finally:
            _pd.export, _pd.API_TOKEN = saved
    with_mail(go)


@test
def t_the_erasure_matcher_takes_whole_names_and_numbers_only():
    """The one matcher an erasure and every later import use: whole addresses,
    numbers whatever their spelling, names of two words or more in order,
    surname first only with a comma, ordinary words only with a capital, and
    never across a new line, a sentence, an address or a link."""
    sc = privacy._erase_scrubber(words=["Sarah Whitfield", "sarah@ns.co.uk", "0191 111 2222", "Will",
                                         "Anne-Marie O’Neill", "Mob: 07700 900123 (mobile)",
                                         "sean.o'brien@lumen.co.uk", "Dr Sarah Jane Whitfield",
                                         "Sarah & Tom Whitfield", "Will Price", "Stage Door",
                                         "José Núñez"])
    cases = [
        ("Call Sarah Whitfield today", "Call [erased] today"),
        ("SARAH   WHITFIELD.", "[erased]."),
        ("Whitfield, Sarah - reorder", "[erased] - reorder"),
        ("Whitfield Sarah rang", "Whitfield Sarah rang"),
        ("Cc: Tom Whitfield, Sarah Whitfield", "Cc: Tom Whitfield, [erased]"),
        ("Sarah\nWhitfield", "Sarah\nWhitfield"),
        ("see Sarah. Whitfield said no", "see Sarah. Whitfield said no"),
        ("S. Whitfield, not Sarah Jane Whitfield", "S. Whitfield, not [erased]"),
        ("Dr Sarah Jane Whitfield signed", "Dr [erased] signed"),
        ("Sarah & Tom Whitfield wedding gobos", "[erased] wedding gobos"),
        ("Sarah Whitfield (Lumen) - 12 gobos", "[erased] (Lumen) - 12 gobos"),
        ("Sarah Whitfield's order", "[erased]'s order"),
        ("sarah.whitfield is a handle, sarah.whitfield@other.com an address", "sarah.whitfield is a handle, sarah.whitfield@other.com an address"),
        ("https://example.com/sarah-whitfield/profile", "https://example.com/sarah-whitfield/profile"),
        ("write to sarah@ns.co.uk or sarah@ns.co.uk.au", "write to [erased] or sarah@ns.co.uk.au"),
        ("to 'sean.o'brien@lumen.co.uk'", "to '[erased]'"),
        ("ring +44 (0)191 111 2222 or 01911112222 or 0044 191 111 2222", "ring [erased] or [erased] or [erased]"),
        ("order 104239 0191 111 2222 x2", "order 104239 [erased] x2"),
        ("mob 0044 7700 900123", "mob [erased]"),
        ("0191 111 22223", "0191 111 22223"),
        ("Will they order the Willow set", "Will they order the Willow set"),
        ("The price will include delivery, will price it Monday", "The price will include delivery, will price it Monday"),
        ("Will Price rang", "[erased] rang"),
        ("Deliver to the stage door after 2pm", "Deliver to the stage door after 2pm"),
        ("Sarah Whitfields", "Sarah Whitfields"),
        ("Anne-Marie O'Neill and anne-marie o’neill", "[erased] and [erased]"),
        ("<p>Rang Sarah&nbsp;Whitfield</p><p>Mob: 07700&nbsp;900123</p>", "<p>Rang [erased]</p><p>Mob: [erased]</p>"),
        ("José Núñez rig", "[erased] rig"),
        ("From: Sarah Whitfield <sarah@ns.co.uk>", "From: [erased] <[erased]>"),
        ('<p>Email <a href="mailto:sarah@ns.co.uk">her</a> or <a href="tel:01911112222">ring</a></p>',
         '<p>Email <a href="mailto:[erased]">her</a> or <a href="tel:[erased]">ring</a></p>'),
        ("<p>Cheers, Will</p><p>Price agreed at 400</p>", "<p>Cheers, Will</p><p>Price agreed at 400</p>"),
        ("Cc: Tom Whitfield, Sarah Jones", "Cc: Tom Whitfield, Sarah Jones"),
        ("Guests: Amy Whitfield, Sarah Kaur and Raj", "Guests: Amy Whitfield, Sarah Kaur and Raj"),
        ("ring 0191/111/2222", "ring [erased]"),
        ("", ""),
    ]
    for text, want in cases:
        eq(sc(text), want, text)
    eq(privacy._erase_scrubber(words=["Will", "12"]), None, "nothing that could be matched safely: no scrubber")
    # Stored names with a nickname, letters after them, a digit, a slash.
    for stored, verbatim in (("Sarah 'Sal' Whitfield", "Deal: [erased] - 12 gobos"),
                             ("Sarah Whitfield, LD", "Deal: [erased], LD - 12 gobos"),
                             ("Sarah Whitfield (Panto 2024)", "Deal: [erased] - 12 gobos"),
                             ("Sarah Whitfield 2", "Deal: [erased] - 12 gobos"),
                             ("Sarah Whitfield / Lumen", "Deal: [erased] - 12 gobos")):
        one = privacy._erase_scrubber(words=[stored])
        eq(one("Deal: " + stored + " - 12 gobos"), verbatim, stored)
        eq(one("Sarah Whitfield rang"), "[erased] rang", stored)
    ok(not any(c[1] in ("sarah panto", "panto sarah") for c in privacy._erase_canon("Sarah Whitfield (Panto 2024)")),
       "no first-and-last made of a bracketed note")
    # Somebody live holds the same number, address or name: it is theirs too.
    alive = privacy._erase_alive([{"name": "Tom Baker", "emails": ["sales@ns.co.uk"], "phones": ["0191 111 2222"]},
                                  {"name": "Sarah Whitfield", "emails": ["sw@crucible.co.uk"]}])
    sa = privacy._erase_scrubber(words=["Sarah Whitfield", "sales@ns.co.uk", "0191 111 2222", "07700 900123"], alive=alive)
    eq(sa("Office 0191 111 2222, sales@ns.co.uk, Sarah Whitfield, mob 07700 900123"),
       "Office 0191 111 2222, sales@ns.co.uk, Sarah Whitfield, mob [erased]")
    eq(sa("Sarah Whitfield's deal", True), "[erased]'s deal", "but in her own former records her name is hers")
    # The same from the keyed hashes alone.
    d = {}
    privacy._erase_remember(d, ["Sarah Whitfield", "0191 111 2222"], ["20"], request="sarah@ns.co.uk")
    hs = privacy._erase_scrubber(d)
    eq(hs("Whitfield, Sarah on 0191 111 2222 via sarah@ns.co.uk"), "[erased] on [erased] via [erased]")
    ok(hs.knows("req", "Sarah@NS.co.uk") and hs.knows("phone", "01911112222")
       and not hs.knows("req", "0191 111 2222"), "an exact test, and only the asked-for address recognises")
    eq(d["erased_pd_persons"], ["20"])
    raw = json.dumps(d).lower()
    # The whole number, not a piece of it: the store holds random-salted hex
    # hashes, and about 1 in 250 of them contains "0191" by chance.
    ok("sarah" not in raw and "0191 111 2222" not in raw and "01911112222" not in raw, "nothing in the clear")
    old = d["erased_salt"]
    d["erased_salt"] = "not hex"
    privacy._erase_remember(d, ["Jo Smith"])
    ok(d["erased_salt"] != old and all(m["kid"] == "none" for m in d["erased_marks"]),
       "a damaged salt starts the marks again under a new one")


@test
def t_erasure_marks_take_their_key_from_the_token_vault():
    """Round-5 review: the key sat beside the hashes, so a copy of the CRM file
    alone gave up an erased phone number in minutes. With TOKEN_ENCRYPTION_KEY
    set the key comes from it; marks made under a key the app no longer has
    stop the import rather than letting erased people back."""
    import tokenvault as _tv
    saved = os.environ.get("TOKEN_ENCRYPTION_KEY")
    try:
        os.environ["TOKEN_ENCRYPTION_KEY"] = "a-long-enough-test-key-for-scrypt-0123456789"
        _tv._key.cache_clear()
        d = {}
        privacy._erase_remember(d, ["07700 954321"], [], request="x@y.com")
        salt = d["erased_salt"]
        guess = privacy._erase_hash(bytes.fromhex(salt), "phone", "07700954321")
        ok(all(m["h"] != guess for m in d["erased_marks"]), "the file's salt alone does not reproduce a mark")
        ok(privacy._erase_scrubber(d)("ring 07700 954321") == "ring [erased]", "the app still matches")
        eq(privacy._erase_stale_marks(d), 0)
        # Marks made before any key existed are still readable once one is set.
        os.environ.pop("TOKEN_ENCRYPTION_KEY", None); _tv._key.cache_clear()
        early = {}
        privacy._erase_remember(early, ["07700 111222"], [], request="early@y.com")
        os.environ["TOKEN_ENCRYPTION_KEY"] = "a-long-enough-test-key-for-scrypt-0123456789"; _tv._key.cache_clear()
        eq(privacy._erase_stale_marks(early), 0, "setting a key for the first time blocks nothing")
        eq(privacy._erase_scrubber(early)("ring 07700 111222"), "ring [erased]", "and the early marks still match")
        os.environ["TOKEN_ENCRYPTION_KEY"] = "a-different-key-for-scrypt-9876543210-abcdef"
        _tv._key.cache_clear()
        ok(privacy._erase_stale_marks(d) and "encryption key" in privacy._erase_import_blocker(d),
           "a changed key is said, and blocks the import")
    finally:
        if saved is None:
            os.environ.pop("TOKEN_ENCRYPTION_KEY", None)
        else:
            os.environ["TOKEN_ENCRYPTION_KEY"] = saved
        _tv._key.cache_clear()


@test
def t_a_colleague_who_shares_an_erased_persons_number_is_not_erased():
    """Round-5 review, the high one: every address and number on the erased
    record recognised a person, so a colleague on the same switchboard or the
    same sales@ address became an erased person on the next import, lost their
    name from their own deals, and could not be put back."""
    import pipedrive as _pd
    def go():
        ensure_auth(); crm_wipe()
        sarah = dict(PD_EXPORT["persons"][0], emails=["sarah@lumen.co.uk", "sales@lumen.co.uk"],
                     phones=["0191 496 0000", "07700 900123"])
        tom = {"pd_id": "24", "name": "Tom Baker", "org_pd_id": "10", "emails": ["sales@lumen.co.uk", "tom@lumen.co.uk"],
               "phones": ["0191 496 0000"], "created_at": "", "updated_at": ""}
        deals = [dict(PD_EXPORT["deals"][0], title="Sarah Whitfield - 12 steel gobos"),
                 dict(PD_EXPORT["deals"][1], pd_id="39", title="Tom Baker - lighting rig", person_pd_id="24")]
        notes = [{"pd_id": "59", "deal_pd_id": "39", "person_pd_id": "", "org_pd_id": "",
                  "text": "Tom Baker says ring the office on 0191 496 0000 or sales@lumen.co.uk; Sarah Whitfield on 07700 900123",
                  "at": "2026-09-01T09:00:00Z"}]
        feed = {"x": _pd_export_with(persons=[sarah, tom], deals=deals, activities=[], notes=notes)}
        async def fake_export(progress=None):
            return _copy.deepcopy(feed["x"])
        saved = (_pd.export, _pd.API_TOKEN)
        _pd.export, _pd.API_TOKEN = fake_export, "t"
        try:
            post("/api/crm/import", {"go": True})
            privacy._redact_customer("sarah@lumen.co.uk", "905")
            for _ in range(2):
                r = post("/api/crm/import", {"go": True}).json()
                eq(r["report"]["erased"]["people"], 1, "only Sarah is recognised: %r" % r["report"]["erased"])
            d = salesdesk._load_crm()
            people = {p["pd_id"]: p for p in d["persons"].values()}
            ok("24" in people and "20" not in people, "Tom stays, Sarah does not come back")
            ok("24" not in (d.get("pd_deleted_persons") or []), "and Tom is not tombstoned")
            titles = {v["pd_id"]: v for v in d["deals"].values()}
            eq(titles["39"]["title"], "Tom Baker - lighting rig")
            ok(titles["39"]["person_id"] == people["24"]["id"], "and still his")
            eq(titles["30"]["title"], "[erased] - 12 steel gobos")
            eq(titles["39"]["notes"][0]["text"],
               "Tom Baker says ring the office on 0191 496 0000 or sales@lumen.co.uk; [erased] on [erased]",
               "the shared number and address are Tom's too; hers alone go")
        finally:
            _pd.export, _pd.API_TOKEN = saved
    with_mail(go)


@test
def t_an_import_erases_a_contact_it_recognises_that_the_crm_still_holds():
    """Round-5 review: an erased person the CRM still held (brought back by an
    import that ran while the mailbox could not be read, or a duplicate
    Pipedrive merged into theirs) was skipped by later imports but left in the
    CRM in the clear. It is erased in place; and while the mailbox cannot be
    read the import does not run at all."""
    import pipedrive as _pd
    def go():
        ensure_auth(); crm_wipe()
        st = mail._load_mail(); st["redacted"] = ["olga@lumen.co.uk"]; mail._write_mail(st)
        olga = {"pd_id": "23", "name": "Olga Ivanova", "org_pd_id": "10", "emails": ["olga@lumen.co.uk"],
                "phones": ["07700 900555"], "created_at": "", "updated_at": ""}
        base = dict(PD_EXPORT["deals"][0])
        data = _pd_export_with(persons=[olga], deals=[dict(base, pd_id="33", title="Olga Ivanova touring rig",
                                                           person_pd_id="23")], activities=[], notes=[])
        async def fake_export(progress=None):
            return _copy.deepcopy(data)
        saved = (_pd.export, _pd.API_TOKEN)
        _pd.export, _pd.API_TOKEN = fake_export, "t"
        try:
            # As if an older import had brought her back, and a duplicate of
            # her had been kept under another id (Pipedrive merged it away).
            d = salesdesk._load_crm()
            d["persons"]["p_pd23"] = {"id": "p_pd23", "name": "Olga Ivanova", "emails": ["olga@lumen.co.uk"],
                                      "phones": ["07700 900555"], "pd_id": "23", "notes": []}
            d["persons"]["p_pd26"] = {"id": "p_pd26", "name": "Olga Ivanova", "emails": ["o.ivanova@gmail.com"],
                                      "phones": ["07700 900555"], "pd_id": "26", "notes": []}
            d["persons"]["p_pd27"] = {"id": "p_pd27", "name": "Olga Ivanova", "emails": ["olga@crucible.co.uk"],
                                      "phones": [], "pd_id": "27", "notes": []}
            d["deals"]["dx"] = {"id": "dx", "title": "Desk-typed: Olga Ivanova reorder", "person_id": "p_pd23",
                                "org_id": "o_pd10", "status": "open", "notes": [], "edited_here": True}
            salesdesk._write_crm(d)
            # The mailbox cannot be read: the list of erased addresses is not
            # known, so the import does not run.
            with open(mail.MAILBOX_PATH, "w") as fh:
                fh.write("{ broken")
            mail._mail_mem = None
            jsonstore._json_cache.pop(mail.MAILBOX_PATH, None)
            r = post("/api/crm/import", {"go": True})
            eq(r.status_code, 503, r.text)
            ok("mailbox" in r.json()["error"], r.text)
            pre = post("/api/crm/import", {}).json()
            ok(any("mailbox" in x for x in pre["report"]["problems"]), "the preview says so too")
            jsonstore._poisoned_stores.discard(mail.MAILBOX_PATH)
            mail._write_mail({"threads": {}, "redacted": ["olga@lumen.co.uk"]})
            mail._mail_mem = None
            r = post("/api/crm/import", {"go": True}).json()
            eq(r["report"]["erased"]["removed"], 2, r["report"]["erased"])
            d = salesdesk._load_crm()
            names = sorted((p["pd_id"], p["name"]) for p in d["persons"].values())
            eq(names, [("27", "Olga Ivanova")], "her record and her duplicate go; a namesake elsewhere stays")
            dx = d["deals"]["dx"]
            eq((dx["title"], dx["person_id"]), ("Desk-typed: [erased] reorder", ""), "and a desk-edited deal is cleaned")
            raw = json.dumps(d)
            ok("900555" not in raw and "o.ivanova" not in raw and "olga@lumen" not in raw, "nothing of hers in the clear")
        finally:
            _pd.export, _pd.API_TOKEN = saved
            jsonstore._poisoned_stores.discard(mail.MAILBOX_PATH)
    with_mail(go)


@test
def t_the_second_review_of_the_erasure_scrub_holds():
    """The re-verification of the reworked scrub: a successor on the erased
    person's Pipedrive id is not erased through the firm's shared address; a
    new Pipedrive duplicate of them is recognised; a contact stored under the
    firm's name does not erase the firm's name; a shared number is left in
    colleagues' records even once nobody lists it; their own organisation is
    cleaned though a namesake exists elsewhere; their own note does not land
    on the organisation; and a refused import takes no snapshot."""
    import pipedrive as _pd
    def go():
        ensure_auth(); crm_wipe()
        sarah = dict(PD_EXPORT["persons"][0], emails=["sarah@lumen.co.uk", "office@lumen.co.uk"],
                     phones=["0191 496 0000", "07700 900123"])
        namesake = {"pd_id": "26", "name": "Sarah Whitfield", "org_pd_id": "11", "emails": ["sw@crucible.co.uk"],
                    "phones": [], "created_at": "", "updated_at": ""}
        tom = {"pd_id": "24", "name": "Tom Baker", "org_pd_id": "10", "emails": ["tom@lumen.co.uk", "office@lumen.co.uk"],
               "phones": ["0191 496 0000"], "created_at": "", "updated_at": ""}
        box = {"pd_id": "27", "name": "Lumen Events", "org_pd_id": "10", "emails": ["boxoffice@lumen.co.uk"],
               "phones": [], "created_at": "", "updated_at": ""}
        orgs = [dict(PD_EXPORT["orgs"][0], custom={"Key contact": "Sarah Whitfield"}),
                {"pd_id": "11", "name": "Crucible", "address": "Sheffield", "created_at": "", "updated_at": ""}]
        base = dict(PD_EXPORT["deals"][0])
        deals = [dict(base, title="Sarah Whitfield - 12 steel gobos"),
                 dict(base, pd_id="36", title="Lumen Events panto rig, ring 0191 496 0000", person_pd_id="24"),
                 dict(base, pd_id="37", title="Sarah Whitfield - Crucible panto", person_pd_id="26", org_pd_id="11")]
        notes = [{"pd_id": "52", "deal_pd_id": "", "person_pd_id": "20", "org_pd_id": "10",
                  "text": "Only ring her after 5pm", "at": ""},
                 {"pd_id": "53", "deal_pd_id": "36", "person_pd_id": "", "org_pd_id": "",
                  "text": "Invoices to office@lumen.co.uk, calls to 0191 496 0000", "at": ""}]
        feed = {"x": _pd_export_with(orgs=orgs, persons=[sarah, namesake, tom, box], deals=deals,
                                     activities=[], notes=notes)}
        async def fake_export(progress=None):
            return _copy.deepcopy(feed["x"])
        saved = (_pd.export, _pd.API_TOKEN, backup._weekly_snapshot)
        snaps = []
        def snap(*a, **k):
            snaps.append(1)
        _pd.export, _pd.API_TOKEN, backup._weekly_snapshot = fake_export, "t", snap
        def titles():
            return {v["pd_id"]: v["title"] for v in salesdesk._load_crm()["deals"].values()}
        try:
            post("/api/crm/import", {"go": True})
            privacy._redact_customer("sarah@lumen.co.uk", "907")
            lumen = [o for o in salesdesk._load_crm()["orgs"].values() if o.get("pd_id") == "10"][0]
            eq(lumen["custom"], {"Key contact": "[erased]"}, "her organisation is cleaned at once, whatever the namesake")
            # Tom leaves, here and in Pipedrive. Nobody live lists the
            # switchboard now; it was shared when she was erased, so it is
            # still the firm's. A new duplicate of her turns up in Pipedrive.
            d = salesdesk._load_crm()
            salesdesk._crm_tombstone_contact(d, "persons", [p for p in d["persons"].values() if p.get("pd_id") == "24"][0])
            salesdesk._write_crm(d)
            x = _copy.deepcopy(feed["x"])
            x["persons"] = [p for p in x["persons"] if p["pd_id"] != "24"] + [
                {"pd_id": "28", "name": "Sarah Whitfield", "org_pd_id": "10", "emails": ["sarah.whitfield@hotmail.com"],
                 "phones": ["07700 900123"], "created_at": "", "updated_at": ""}]
            x["notes"].append({"pd_id": "54", "deal_pd_id": "36", "person_pd_id": "", "org_pd_id": "",
                               "text": "Her new address is sarah.whitfield@hotmail.com", "at": ""})
            feed["x"] = x
            for _ in range(2):
                r = post("/api/crm/import", {"go": True}).json()
            d = salesdesk._load_crm()
            eq(titles()["36"], "Lumen Events panto rig, ring 0191 496 0000",
               "the firm's name and switchboard stay, with nobody live listing the number any more")
            notes36 = {n["pd_id"]: n["text"] for n in [v for v in d["deals"].values() if v["pd_id"] == "36"][0]["notes"]}
            eq(notes36["53"], "Invoices to office@lumen.co.uk, calls to 0191 496 0000")
            eq(notes36["54"], "Her new address is [erased]", "the new duplicate is recognised: same name, her number")
            ok(not any(p.get("pd_id") == "28" for p in d["persons"].values()), "and not brought in")
            eq(titles()["30"], "[erased] - 12 steel gobos")
            eq(titles()["37"], "Sarah Whitfield - Crucible panto", "a namesake's own deal is hers")
            ok("Only ring her after 5pm" not in json.dumps(d), "her own note does not land on the organisation")
            # Pipedrive gives her contact to her successor, who keeps the
            # office address and switchboard.
            x = _copy.deepcopy(feed["x"])
            x["persons"] = [dict(p, name="Priya Kumar", emails=["priya@lumen.co.uk", "office@lumen.co.uk"])
                            if p["pd_id"] == "20" else p for p in x["persons"]]
            x["deals"].append(dict(base, pd_id="38", title="Priya Kumar - new venue rig", person_pd_id="20"))
            feed["x"] = x
            post("/api/crm/import", {"go": True})
            eq(titles()["38"], "Priya Kumar - new venue rig", "the successor is not erased through the shared address")
            # The box office contact, stored under the firm's own name, asks
            # to be erased: the firm's name is not a person's.
            privacy._redact_customer("boxoffice@lumen.co.uk", "908")
            post("/api/crm/import", {"go": True})
            eq(titles()["36"], "Lumen Events panto rig, ring 0191 496 0000", "the firm keeps its name")
            ok(not any(p.get("pd_id") == "27" for p in salesdesk._load_crm()["persons"].values()), "the contact itself goes")
            # A refused import takes no snapshot.
            with open(mail.MAILBOX_PATH, "w") as fh:
                fh.write("{ broken")
            mail._mail_mem = None
            jsonstore._json_cache.pop(mail.MAILBOX_PATH, None)
            before = len(snaps)
            eq(post("/api/crm/import", {"go": True}).status_code, 503)
            eq(len(snaps), before, "no snapshot for an import that does not run")
        finally:
            _pd.export, _pd.API_TOKEN, backup._weekly_snapshot = saved
            jsonstore._poisoned_stores.discard(mail.MAILBOX_PATH)
    with_mail(go)

@test
def t_an_erasure_and_every_import_clean_every_field_that_can_name_them():
    """Round-5 review: organisation addresses and custom fields, contacts' job
    titles and custom fields, a deal's lost reason and comment, and the lost
    reason pick-list were never cleaned, at the erasure or on any import. The
    preview's count is of records, and is the run's."""
    import pipedrive as _pd
    def go():
        ensure_auth(); crm_wipe()
        org = dict(PD_EXPORT["orgs"][0], address="c/o Sarah Whitfield, 1 High St, Newcastle",
                   custom={"Main contact": "Sarah Whitfield, 07700 900123", "Seats": 450})
        tom = {"pd_id": "21", "name": "Tom Baker", "org_pd_id": "10", "emails": ["tom@lumen.co.uk"], "phones": [],
               "job_title": "Assistant to Sarah Whitfield", "custom": {"Cover": "Sarah Whitfield 07700 900123"},
               "created_at": "", "updated_at": ""}
        sarah = dict(PD_EXPORT["persons"][0], phones=["07700 900123"])
        lost = dict(PD_EXPORT["deals"][1], lost_reason="Sarah Whitfield went elsewhere")
        data = _pd_export_with(orgs=[org], persons=[sarah, tom], deals=[PD_EXPORT["deals"][0], lost],
                               activities=[], notes=[])
        async def fake_export(progress=None):
            return _copy.deepcopy(data)
        saved = (_pd.export, _pd.API_TOKEN)
        _pd.export, _pd.API_TOKEN = fake_export, "t"
        try:
            post("/api/crm/import", {"go": True})
            d = salesdesk._load_crm()
            won = [k for k, v in d["deals"].items() if v["pd_id"] == "30"][0]
            d["deals"][won]["lost_comment"] = "Ring Sarah Whitfield on 07700 900123 in the spring"
            d["deals"][won]["edited_here"] = True
            salesdesk._write_crm(d)
            privacy._redact_customer("sarah@lumen.co.uk", "906")
            for label in ("after the erasure", "after an import"):
                d = salesdesk._load_crm()
                o = [v for v in d["orgs"].values() if v.get("pd_id") == "10"][0]
                t = [v for v in d["persons"].values() if v.get("pd_id") == "21"][0]
                eq(o["address"], "c/o [erased], 1 High St, Newcastle", label)
                eq(o["custom"], {"Main contact": "[erased], [erased]", "Seats": 450}, label)
                eq((t["job_title"], t["custom"]["Cover"]), ("Assistant to [erased]", "[erased] [erased]"), label)
                deals = {v["pd_id"]: v for v in d["deals"].values()}
                eq(deals["30"]["lost_comment"], "Ring [erased] on [erased] in the spring", label)
                eq(deals["31"]["lost_reason"], "[erased] went elsewhere", label)
                ok(not any("Whitfield" in r or "[erased]" in r for r in d.get("lost_reasons") or []),
                   label + ": the pick-list too, with no [erased] reason offered")
                ok("whitfield" not in json.dumps(d).lower() and "900123" not in json.dumps(d), label)
                if label == "after the erasure":
                    pre = post("/api/crm/import", {}).json()["report"]["erased"]
                    run = post("/api/crm/import", {"go": True}).json()["report"]["erased"]
                    eq(pre, run, "the preview counts what the run does")
                    eq(run["scrubbed"], 3, "the organisation, Tom and the lost deal: records, not fields")
        finally:
            _pd.export, _pd.API_TOKEN = saved
    with_mail(go)


