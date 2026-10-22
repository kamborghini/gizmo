# ---------------------------------------------------------------------------
# Two mailboxes: the sales inbox and the accounts mailbox must never mix
# ---------------------------------------------------------------------------

@test
def t_the_two_mailboxes_have_separate_tokens_and_caches():
    """They are different Google accounts. Sharing a token file or an access
    cache would mean reconciliation reading the sales inbox, or the Inbox tab
    showing finance mail - both wrong, and both silent."""
    ok(_gm.SALES.token_path != _gm.FINANCE.token_path,
       "different token files: %s vs %s" % (_gm.SALES.token_path, _gm.FINANCE.token_path))
    ok(_gm.SALES.access is not _gm.FINANCE.access, "and different access caches")
    _gm.SALES.access["token"] = "sales-token"
    _gm.FINANCE.access["token"] = "finance-token"
    ok(_gm.SALES.access["token"] == "sales-token"
       and _gm.FINANCE.access["token"] == "finance-token",
       "setting one does not touch the other")
    _gm.SALES.access["token"] = ""
    _gm.FINANCE.access["token"] = ""
    # The path is read live, so a test or a settings change that moves
    # TOKEN_PATH still describes the same account.
    saved = _gm.TOKEN_PATH
    try:
        _gm.TOKEN_PATH = SCRATCH + "/moved.json"
        eq(_gm.SALES.token_path, SCRATCH + "/moved.json",
           "the account follows its module path rather than a stale copy")
    finally:
        _gm.TOKEN_PATH = saved


@test
def t_one_token_file_cannot_serve_two_mailboxes():
    """A shared token file would point reconciliation at the sales inbox while
    the screen says it is reading the accounts mailbox: exactly the failure the
    split exists to prevent, and silent. It is refused instead."""
    saved = _gm.FINANCE_TOKEN_PATH
    try:
        _gm.FINANCE_TOKEN_PATH = _gm.TOKEN_PATH
        ok(not _gm.FINANCE.usable(), "a colliding account is not usable")
        ok(not _gm.connected(_gm.FINANCE), "and never reports itself connected")
        try:
            run_async(_gm._token(_gm.FINANCE))
            ok(False, "minting a token for a colliding account must raise")
        except _gm.GmailError as e:
            ok("its own token file" in str(e), "and says how to fix it: " + str(e))
        ok(_gm.SALES.usable(), "the sales inbox is unaffected")
    finally:
        _gm.FINANCE_TOKEN_PATH = saved
    ok(_gm.FINANCE.usable(), "and it recovers once the paths differ again")


@test
def t_every_gmail_call_goes_to_the_account_it_was_asked_for():
    """The isolation is the routing: if a read defaults to the sales account
    when handed the finance one, reconciliation quietly audits the wrong post."""
    seen = []

    async def fake_call(method, path, params=None, body=None, acct=None):
        seen.append((path.split("/")[0], acct.label if acct else "DEFAULT"))
        if path == "threads":
            return {"threads": [{"id": "t1"}]}
        if path.startswith("threads/"):
            return {"id": "t1", "messages": []}
        return {"data": ""}

    saved = _gm._call
    _gm._call = fake_call
    try:
        run_async(_gm.list_thread_ids("q", acct=_gm.FINANCE))
        run_async(_gm.get_thread("t1", acct=_gm.FINANCE))
        run_async(_gm.attachment_bytes("m1", "a1", acct=_gm.FINANCE))
        ok(all(label == "finance" for _p, label in seen),
           "every finance read reached the finance account: %s" % seen)
        seen.clear()
        run_async(_gm.get_thread("t1"))
        eq(seen[0][1], "sales", "and the default is still the sales inbox")
    finally:
        _gm._call = saved


@test
def t_reconciliation_is_wired_to_the_finance_mailbox_only():
    src = copilot_source()
    seg = src.split("recon_engine.configure(")[1][:400]
    ok("mail_store" not in seg,
       "the engine no longer receives the Inbox tab's store at all")
    wiring = src.split("_fin = google_mail.FINANCE")[1][:700]
    for hook in ("attachment_bytes", "list_thread_ids", "get_thread"):
        call = wiring.split(hook)[1][:120]
        ok("acct=_fin" in call, hook + " is bound to the finance account: " + call[:60])


@test
def t_connecting_the_sales_mailbox_as_accounts_is_refused():
    """The likeliest mistake in the whole walk: whoever clicks the link is
    probably already signed in as the sales mailbox. Agreeing would leave
    reconciliation reading the wrong post and reporting a clean board."""
    src = copilot_source()
    cb = src.split("async def gmail_finance_callback")[1].split("\n    @mcp.custom_route")[0]
    ok("addr.strip().lower() == sales.strip().lower()" in cb,
       "the two addresses are compared, tolerant of case and whitespace")
    ok("disconnect(google_mail.FINANCE)" in cb,
       "and the wrong connection is thrown away rather than kept")
    ok(cb.index("disconnect(google_mail.FINANCE)") < cb.index("That is the sales mailbox"),
       "the token is dropped before the page is returned")


@test
def t_the_finance_token_is_a_credential_not_a_backup_item():
    src = copilot_source()
    eq(src.count('getattr(google_mail, "FINANCE_TOKEN_PATH"'), 2,
       "excluded from the backup AND blocked at restore, like every other token")


@test
def t_a_thread_still_queued_for_reading_is_not_marked_seen():
    """The seen list is what stops a sweep refetching a year of mail. A thread
    whose documents did not get read this time must come back, or its invoice
    is dropped and nothing says so."""
    stores = {"store": {"exceptions": {}, "watermarks": {}}, "cache": {}, "docs": {}}
    threads = {("t%d" % i): {"id": "t%d" % i, "subject": "Invoice %d" % i,
                             "messages": [{"id": "m%d" % i, "at": "2026-08-2%d" % (i % 10),
                                           "from_email": "ap@supplier.com",
                                           "files": [{"id": "a%d" % i, "name": "inv.pdf",
                                                      "size": 100}]}]}
               for i in range(12)}

    async def search(q, mx=200, out_complete=None):
        if out_complete is not None:
            out_complete.append(True)
        return set(threads)

    async def thread(tid):
        return threads[tid]

    async def gbytes(mid, aid):
        return b"%PDF-1.4 tiny"

    fx = _FakeXero(invoices=[_raw_xinv("INV-1", "10.00")])
    async def fake_tool_json(reg, name, args):
        return {"orders": []} if name == "shopify_list_orders" else {"available": False}
    saved_cap = _rc.DOCS_PER_SWEEP
    _rc.DOCS_PER_SWEEP = 4
    import copy as _copy
    _rc.configure(xero=fx, registry={}, tool_json=fake_tool_json,
                  mail_connected=lambda: True,
                  mail_search=search, mail_thread=thread, gmail_bytes=gbytes, ai_call=None,
                  load_store=lambda: _copy.deepcopy(stores["store"]),
                  write_store=lambda d: stores.update(store=d),
                  load_cache=lambda: _copy.deepcopy(stores["cache"]),
                  write_cache=lambda d: stores.update(cache=d),
                  load_docs=lambda: _copy.deepcopy(stores["docs"]),
                  write_docs=lambda d: stores.update(docs=d))
    try:
        r = run_async(_rc.sweep())
        ok(r["ok"], r)
        seen = set(stores["store"].get("seen_threads") or [])
        read = set(stores["docs"].keys())
        eq(len(read), 4, "only the per-sweep budget was read: %d" % len(read))
        ok(len(seen) == 4, "and only those threads are marked seen: %d" % len(seen))
        ok(any("queued for later sweeps" in n for n in r["notes"]),
           "the backlog is stated rather than silently dropped: %s" % r["notes"])
        r2 = run_async(_rc.sweep())
        ok(len(stores["docs"]) > 4, "the next sweep picks up where it stopped: %d"
           % len(stores["docs"]))
    finally:
        _rc.DOCS_PER_SWEEP = saved_cap
        _rc.configure(xero=None, registry=None, tool_json=None, mail_search=None,
                      mail_connected=None, mail_thread=None, gmail_bytes=None,
                      load_store=None, write_store=None,
                      load_cache=None, write_cache=None, load_docs=None, write_docs=None)


@test
def t_no_accounts_mailbox_means_the_sweep_says_so():
    """A sweep with no finance mail connected has checked no documents at all.
    Silence there would read as 'no missing invoices'."""
    fx = _FakeXero(invoices=[_raw_xinv("INV-1", "10.00")])
    stores = _recon_world(fx, [])
    try:
        r = run_async(_rc.sweep())
        ok(any("accounts mailbox is not connected" in n for n in r["notes"]),
           "the gap is reported: %s" % r["notes"])
    finally:
        _rc.configure(xero=None, registry=None, tool_json=None, mail_search=None,
                      mail_thread=None, load_store=None, write_store=None,
                      load_cache=None, write_cache=None, load_docs=None, write_docs=None)


def _mail_world(threads, gbytes=None, search=None, docs_cap=None):
    """A reconciliation world with a working accounts mailbox behind it."""
    import copy as _copy
    stores = {"store": {"exceptions": {}, "watermarks": {}}, "cache": {}, "docs": {}}

    async def default_search(q, mx=200, out_complete=None):
        if out_complete is not None:
            out_complete.append(True)
        return set(threads)

    async def thread(tid):
        return threads[tid]

    async def default_bytes(mid, aid):
        return b"%PDF-1.4 tiny"

    async def tools(reg, name, args):
        return {"orders": []} if name == "shopify_list_orders" else {"available": False}

    _rc.configure(xero=_FakeXero(invoices=[_raw_xinv("INV-1", "10.00")]), registry={},
                  tool_json=tools, mail_connected=lambda: True,
                  mail_search=search or default_search, mail_thread=thread,
                  gmail_bytes=gbytes or default_bytes, ai_call=None,
                  load_store=lambda: _copy.deepcopy(stores["store"]),
                  write_store=lambda d: stores.update(store=d),
                  load_cache=lambda: _copy.deepcopy(stores["cache"]),
                  write_cache=lambda d: stores.update(cache=d),
                  load_docs=lambda: _copy.deepcopy(stores["docs"]),
                  write_docs=lambda d: stores.update(docs=d))
    return stores


def _mail_world_off():
    _rc.configure(xero=None, registry=None, tool_json=None, mail_connected=None,
                  mail_search=None, mail_thread=None, gmail_bytes=None,
                  load_store=None, write_store=None, load_cache=None,
                  write_cache=None, load_docs=None, write_docs=None)


def _thread_with_pdf(i):
    return {"id": "t%d" % i, "subject": "Invoice %d" % i,
            "messages": [{"id": "m%d" % i, "at": "2026-08-20", "from_email": "ap@supplier.com",
                          "files": [{"id": "a%d" % i, "name": "inv.pdf", "size": 100}]}]}


@test
def t_what_the_sweep_learned_survives_its_own_reload():
    """The sweep reloads the store before merging, to avoid clobbering a status
    someone set while it ran. Everything it learned has to cross that reload:
    seen_threads did not, so the mailbox crawl reread its first threads forever
    and never reached the rest of the mailbox."""
    threads = {("t%d" % i): _thread_with_pdf(i) for i in range(3)}
    stores = _mail_world(threads)
    try:
        run_async(_rc.sweep())
        seen = stores["store"].get("seen_threads") or []
        eq(sorted(seen), ["t0", "t1", "t2"],
           "the walked threads persisted past the reload: %s" % seen)
    finally:
        _mail_world_off()


@test
def t_a_mailbox_that_cannot_be_read_is_never_a_clean_sweep():
    """The house rule, on the exact read this feature exists for. A search that
    fails has checked NO documents; silence there reads as 'no missing
    invoices', which is the one thing this tool must never imply."""
    async def broken(q, mx=200, out_complete=None):
        raise RuntimeError("Gmail 503")
    stores = _mail_world({}, search=broken)
    try:
        r = run_async(_rc.sweep())
        ok(any("could not be read" in n for n in r["notes"]),
           "the failure is on the report: %s" % r["notes"])
    finally:
        _mail_world_off()


@test
def t_a_document_that_could_not_be_read_comes_back_next_sweep():
    """A thread is only 'seen' once its documents are actually IN the store. A
    fetch that failed used to mark it seen anyway, so that supplier's
    remittance became permanently invisible, with nothing said."""
    calls = {"n": 0}

    async def flaky(mid, aid):
        calls["n"] += 1
        if calls["n"] <= 1:
            raise RuntimeError("Gmail 500 on the attachment")
        return b"%PDF-1.4 tiny"

    stores = _mail_world({"t1": _thread_with_pdf(1)}, gbytes=flaky)
    try:
        r = run_async(_rc.sweep())
        eq(stores["docs"], {}, "nothing was stored")
        eq(stores["store"].get("seen_threads") or [], [],
           "and the thread is NOT written off as seen")
        ok(any("could not be read" in n and "retried" in n for n in r["notes"]),
           "the sweep says so: %s" % r["notes"])
        run_async(_rc.sweep())
        eq(len(stores["docs"]), 1, "the next sweep picks it up")
        eq(stores["store"].get("seen_threads") or [], ["t1"], "and only then is it seen")
    finally:
        _mail_world_off()


@test
def t_a_disconnected_accounts_mailbox_is_reported_not_assumed():
    """The note used to be keyed on whether a hook was wired, which in the real
    app is always. So a disconnected mailbox produced a silent clean sweep."""
    stores = _mail_world({"t1": _thread_with_pdf(1)})
    try:
        _rc.configure(mail_connected=lambda: False)
        r = run_async(_rc.sweep())
        ok(any("not connected" in n for n in r["notes"]),
           "the sweep says the mailbox is not connected: %s" % r["notes"])
        eq(stores["docs"], {}, "and nothing pretended to be checked")
    finally:
        _mail_world_off()


@test
def t_the_newest_mail_is_read_first():
    """With a per-sweep budget, an unordered set means the newest invoice can
    sit unread behind a year of old post."""
    threads = {("t%03d" % i): _thread_with_pdf(i) for i in range(60)}
    for i in range(60):
        threads["t%03d" % i]["id"] = "t%03d" % i
    saved = _rc.THREADS_PER_SWEEP
    _rc.THREADS_PER_SWEEP = 5
    stores = _mail_world(threads)
    try:
        run_async(_rc.sweep())
        seen = sorted(stores["store"].get("seen_threads") or [])
        eq(seen, ["t055", "t056", "t057", "t058", "t059"],
           "the highest (newest) thread ids were read first: %s" % seen)
    finally:
        _rc.THREADS_PER_SWEEP = saved
        _mail_world_off()


@test
def t_a_shared_token_file_cannot_delete_the_sales_connection():
    """With colliding paths, a finance connect would write over the sales
    token and a finance disconnect would delete it: either takes the Inbox tab
    down with it."""
    saved = _gm.FINANCE_TOKEN_PATH
    try:
        _gm.FINANCE_TOKEN_PATH = _gm.TOKEN_PATH
        try:
            _gm.save_connection("rt", "accounts@example.com", _gm.FINANCE)
            ok(False, "saving a colliding account must raise")
        except _gm.GmailError as e:
            ok("its own token file" in str(e), str(e))
        # And disconnect must not remove the file it would be sharing.
        os.makedirs(os.path.dirname(_gm.TOKEN_PATH) or ".", exist_ok=True)
        with open(_gm.TOKEN_PATH, "w", encoding="utf-8") as fh:
            json.dump({"refresh_token": "sales-rt", "address": "sales@example.com"}, fh)
        _gm.disconnect(_gm.FINANCE)
        ok(os.path.exists(_gm.TOKEN_PATH), "the sales token file survived")
    finally:
        _gm.FINANCE_TOKEN_PATH = saved
        try:
            os.remove(_gm.TOKEN_PATH)
        except FileNotFoundError:
            pass


@test
def t_connecting_the_accounts_mailbox_needs_no_secret_in_a_url():
    """The first attempt handed out /oauth/gmail-finance/start?key=YOUR_CONNECT_SECRET,
    a literal placeholder, and opening it returned Forbidden. The sales mailbox
    already had the better answer: a button that mints a single-use ticket."""
    def go():
        ensure_auth()
        saved = (_gm.OAUTH_CLIENT_ID, _gm.OAUTH_CLIENT_SECRET)
        _gm.OAUTH_CLIENT_ID = _gm.OAUTH_CLIENT_SECRET = "demo"
        try:
            _connect_link_body()
        finally:
            _gm.OAUTH_CLIENT_ID, _gm.OAUTH_CLIENT_SECRET = saved

    def _connect_link_body():
        r = post("/api/recon/connect-link", {"address": "accounts@example.com"})
        eq(r.status_code, 200, r.text[:160])
        url = r.json()["url"]
        ok(url.startswith("/oauth/gmail-finance/start?t="), url)
        ok("YOUR_CONNECT_SECRET" not in url and "key=" not in url,
           "no server secret travels in the URL")
        ticket = url.split("t=")[1]
        ok(ticket in oauth._fin_connect_tickets, "the ticket is live")
        # It opens the walk once, and only once.
        h = {"Authorization": "Bearer " + tok()}
        first = client.get(url, headers=h, follow_redirects=False)
        ok(first.status_code in (302, 307), "the ticket opens the consent walk: %s" % first.status_code)
        again = client.get(url, headers=h, follow_redirects=False)
        eq(again.status_code, 403, "and cannot be replayed")
        # A ticket for the sales mailbox must not open the accounts one.
        mail._mail_connect_tickets["borrowed"] = time.time() + 300
        cross = client.get("/oauth/gmail-finance/start?t=borrowed", headers=h,
                           follow_redirects=False)
        eq(cross.status_code, 403, "the two mailboxes do not share tickets")
    with_accounts(go)


@test
def t_only_the_master_can_connect_the_accounts_mailbox():
    def go():
        r = post("/api/team/user", {"op": "create", "name": "Admin Ann", "username": "ann",
                                    "role": "admin"})
        uid, pw = r.json()["id"], r.json()["starter_password"]
        lg = client.post("/api/auth/login", json={"username": "ann", "password": pw},
                         headers={"Authorization": "Bearer " + tok()}).json()
        sess = lg.get("session")
        ch = post_s(sess, "/api/auth/password", {"current": pw, "new": "ann-pw-55120"})
        sess = ch.json().get("session") or sess
        rr = post_s(sess, "/api/recon/connect-link", {})
        eq(rr.status_code, 403, "an admin cannot connect a mailbox: " + rr.text[:120])
    with_accounts(go)


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
def t_a_mailbox_other_than_the_one_asked_for_is_not_saved():
    """Google can hand back a different account than the one hinted, which is
    exactly what happens when the browser is signed in elsewhere. Accepting it
    would leave reconciliation reading whatever mailbox turned up."""
    def go():
        ensure_auth()
        saved = (_gm.OAUTH_CLIENT_ID, _gm.OAUTH_CLIENT_SECRET, _gm.exchange_code)
        _gm.OAUTH_CLIENT_ID = _gm.OAUTH_CLIENT_SECRET = "demo"
        try:
            blank = post("/api/recon/connect-link", {})
            eq(blank.status_code, 400, "an empty address is refused: " + blank.text[:120])
            ok("already signed into" in blank.text, "and says why it matters")
            r = post("/api/recon/connect-link", {"address": "accounts@example.com"})
            eq(r.status_code, 200, r.text[:140])
            url = r.json()["url"]
            h = {"Authorization": "Bearer " + tok()}
            red = client.get(url, headers=h, follow_redirects=False)
            eq(red.status_code, 302, "the walk starts")
            loc = red.headers["location"]
            ok("AccountChooser" in loc and "Email=accounts%40example.com" in loc,
               "Google is told which account: " + loc[:120])
            from urllib.parse import urlparse, parse_qs
            inner = parse_qs(urlparse(loc).query)["continue"][0]
            state = parse_qs(urlparse(inner).query)["state"][0]

            # Google comes back having connected the WRONG mailbox.
            async def wrong(code, redirect_uri, acct=_gm.SALES):
                _gm.save_connection("rt", "gobo@projectedimage.com", acct)
                return True
            _gm.exchange_code = wrong
            cb = client.get(f"/oauth/gmail-finance/callback?state={state}&code=abc", headers=h)
            ok("Wrong mailbox" in cb.text, "it is refused: " + cb.text[:200])
            ok("accounts@example.com" in cb.text and "gobo@projectedimage.com" in cb.text,
               "and both addresses are named so the mistake is obvious")
            ok(not _gm.connected(_gm.FINANCE), "nothing was saved")
        finally:
            _gm.OAUTH_CLIENT_ID, _gm.OAUTH_CLIENT_SECRET, _gm.exchange_code = saved
            _gm.disconnect(_gm.FINANCE)
    with_accounts(go)


@test
def t_xero_connects_by_button_too():
    """The Xero card had the same placeholder URL the mailbox card did, which
    returns Forbidden when opened exactly as written."""
    def go():
        ensure_auth()
        saved = (xero_api.CLIENT_ID, xero_api.CLIENT_SECRET)
        xero_api.CLIENT_ID = xero_api.CLIENT_SECRET = "demo"
        try:
            src = copilot_source()
            ok("YOUR_CONNECT_SECRET" not in src,
               "no placeholder secret is handed to anyone, for either connection")
            r = post("/api/recon/xero-link", {})
            eq(r.status_code, 200, r.text[:140])
            url = r.json()["url"]
            ok(url.startswith("/oauth/xero/start?t="), url)
            h = {"Authorization": "Bearer " + tok()}
            first = client.get(url, headers=h, follow_redirects=False)
            eq(first.status_code, 302, "the ticket opens the walk")
            ok("xero.com" in first.headers["location"], first.headers["location"][:80])
            again = client.get(url, headers=h, follow_redirects=False)
            eq(again.status_code, 403, "and cannot be replayed")
            # A Gmail ticket must not open the Xero walk.
            oauth._fin_connect_tickets["borrowed"] = {"exp": time.time() + 300, "want": ""}
            cross = client.get("/oauth/xero/start?t=borrowed", headers=h, follow_redirects=False)
            eq(cross.status_code, 403, "tickets are not interchangeable between connections")
        finally:
            xero_api.CLIENT_ID, xero_api.CLIENT_SECRET = saved
    with_accounts(go)


@test
def t_the_xero_consent_asks_only_for_what_it_reads():
    """Xero answered the first attempt with invalid_scope. Two things were
    wrong: scopes nothing in the client reads, and spaces encoded as '+',
    which a literal parser sees as one enormous invalid scope."""
    from urllib.parse import urlparse, parse_qs
    saved = xero_api.CLIENT_ID
    xero_api.CLIENT_ID = "demo"
    try:
        url = xero_api.consent_url("https://x/cb", "st")
    finally:
        xero_api.CLIENT_ID = saved
    ok("%20" in url and "scope=offline_access%20" in url,
       "scope separators are %20, not +: " + url[:150])
    scopes = set(parse_qs(urlparse(url).query)["scope"][0].split())
    ok("offline_access" in scopes, "the refresh token needs offline_access")
    # Every scope must correspond to something the client actually calls.
    src = open(os.path.join(HERE, "xero.py"), encoding="utf-8").read()
    # Xero's granular scopes, and the endpoints each one actually covers.
    # The broad accounting.transactions.read is deprecated and is refused
    # outright for apps created since March 2026, which is what invalid_scope
    # was: a documented name that new apps are not issued.
    ok("accounting.transactions" not in " ".join(scopes),
       "the deprecated broad scope is not asked for: %s" % sorted(scopes))
    reads = {
        "accounting.invoices.read": ("Invoices", "CreditNotes"),
        "accounting.payments.read": ("Payments",),
        "accounting.banktransactions.read": ("BankTransactions",),
        "accounting.contacts.read": ("Contacts",),
        "accounting.settings.read": ("Accounts", "TaxRates", "Organisation"),
        "accounting.journals.read": ("Journals",),
    }
    # Everything the SWEEP reads must be covered. Fetchers no check calls are
    # deliberately outside the consent: an app is assigned a set of granular
    # scopes, and asking for one it was not assigned fails the whole
    # authorization, so an unused scope is not a free extra.
    covered = {e for sc, eps in reads.items() if sc in scopes for e in eps}
    for endpoint in ("Invoices", "CreditNotes", "Payments", "BankTransactions"):
        ok(endpoint in covered, endpoint + " is read every sweep but no scope covers it")
    src_recon = open(os.path.join(HERE, "recon.py"), encoding="utf-8").read()
    for scope, endpoints in reads.items():
        if scope in scopes:
            continue
        for fetcher, needed in (("list_contacts", "Contacts"), ("list_accounts", "Accounts"),
                                ("list_tax_rates", "TaxRates"), ("list_journals", "Journals"),
                                ("organisation", "Organisation")):
            if needed in endpoints:
                ok("_xero." + fetcher + "(" not in src_recon,
                   fetcher + " is called but its scope is not requested: add " + scope)
    for scope, endpoints in reads.items():
        if scope in scopes:
            ok(any('"' + e + '"' in src for e in endpoints),
               scope + " is asked for and used")
    extra = scopes - set(reads) - {"openid", "offline_access", "profile", "email"}
    eq(extra, set(), "nothing is asked for that no fetcher uses: %s" % extra)


@test
def t_disconnecting_xero_revokes_rather_than_forgets():
    """A refresh token we merely delete stays valid at Xero for up to 60 days.
    Disconnect has to end the grant at the provider, or it is housekeeping
    dressed as a security control."""
    def go():
        ensure_auth()
        saved = (xero_api.CLIENT_ID, xero_api.CLIENT_SECRET, xero_api.httpx.AsyncClient)
        xero_api.CLIENT_ID = xero_api.CLIENT_SECRET = "demo"
        called = {}

        class _R:
            status_code = 200
            text = ""

        class _C:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, **kw):
                called["url"] = url
                called["token"] = (kw.get("data") or {}).get("token")
                called["auth"] = kw.get("auth")
                return _R()
        xero_api.httpx.AsyncClient = lambda *a, **k: _C()
        try:
            xero_api._write_token({"refresh_token": "rt-live", "tenant_id": "t1",
                                   "tenant_name": "Projected Image"})
            # The cache holds a copy of the books; it must not outlive the consent.
            import copilot as _cp
            reconciliation._write_recon_cache({"xero": {"invoices": {"a": {"id": "a"}}},
                                    "shopify": {"orders": {}}})
            r = post("/api/recon/disconnect", {"what": "xero"})
            eq(r.status_code, 200, r.text[:160])
            ok(called.get("url", "").endswith("/connect/revocation"),
               "Xero's revocation endpoint was called: %s" % called.get("url"))
            eq(called.get("token"), "rt-live", "with the live refresh token")
            ok(called.get("auth"), "authenticated with the client credentials")
            ok(not xero_api.connected(), "and the local copy is gone")
            eq(reconciliation._load_recon_cache().get("xero"), None,
               "the cached accounting records went with it")
            ok("shopify" in reconciliation._load_recon_cache(),
               "while the rest of the cache is untouched")
        finally:
            xero_api.CLIENT_ID, xero_api.CLIENT_SECRET, xero_api.httpx.AsyncClient = saved
            xero_api.disconnect()
    with_accounts(go)


@test
def t_only_the_master_can_disconnect():
    def go():
        r = post("/api/team/user", {"op": "create", "name": "Adam", "username": "adamx",
                                    "role": "admin"})
        uid, pw = r.json()["id"], r.json()["starter_password"]
        lg = client.post("/api/auth/login", json={"username": "adamx", "password": pw},
                         headers={"Authorization": "Bearer " + tok()}).json()
        sess = lg.get("session")
        ch = post_s(sess, "/api/auth/password", {"current": pw, "new": "adam-pw-77120"})
        sess = ch.json().get("session") or sess
        # Hand this admin the tab explicitly, so what the test proves is the
        # master-only check and not the opt-in gate in front of it.
        post("/api/team/user", {"op": "tabs", "id": uid, "tabs": list(team.TAB_KEYS)})
        for what in ("xero", "mailbox"):
            rr = post_s(sess, "/api/recon/disconnect", {"what": what})
            eq(rr.status_code, 403, "an admin cannot disconnect " + what)
    with_accounts(go)


@test
def t_token_files_are_not_world_readable():
    """Xero: a leaked refresh token 'would allow anyone to generate new
    access_tokens for that user with the same permissions'."""
    import stat
    xero_api._write_token({"refresh_token": "rt", "tenant_id": "t"})
    mode = stat.S_IMODE(os.stat(xero_api.TOKEN_PATH).st_mode)
    eq(mode & 0o077, 0, "the Xero token file is owner-only: %o" % mode)
    xero_api.disconnect()
    _gm.save_connection("rt", "accounts@example.com", _gm.FINANCE)
    mode2 = stat.S_IMODE(os.stat(_gm.FINANCE.token_path).st_mode)
    eq(mode2 & 0o077, 0, "and so is the mailbox token: %o" % mode2)
    _gm.disconnect(_gm.FINANCE)
    # The records those tokens fetched are not less sensitive than the tokens:
    # the cache is the books, and the docs store is the contents of bank
    # statements and remittance advices.
    reconciliation._write_recon_cache({"xero": {"invoices": {}}})
    reconciliation._write_recon_docs({"t1": {"kind": "remittance"}})
    reconciliation._write_recon({"exceptions": {}})
    for path, what in ((reconciliation.RECON_CACHE_PATH, "the accounting cache"),
                       (reconciliation.RECON_DOCS_PATH, "the extracted documents"),
                       (reconciliation.RECON_PATH, "the exception list")):
        m = stat.S_IMODE(os.stat(path).st_mode)
        eq(m & 0o077, 0, "%s is owner-only: %o" % (what, m))


@test
def t_a_xero_outage_is_not_reported_as_a_dead_token():
    """A 503 from Xero and a revoked refresh token look nothing alike, and the
    advice differs completely: one says wait, the other says reconnect, and
    reconnecting spends a healthy token on a revocation. Only invalid_grant
    means the credential is gone."""
    saved = (xero_api.httpx.AsyncClient, xero_api.RETRY_WAITS,
             xero_api.CLIENT_ID, xero_api.CLIENT_SECRET)
    xero_api.RETRY_WAITS = (0.0, 0.0)     # the retry policy, without the wait
    xero_api.CLIENT_ID = xero_api.CLIENT_SECRET = "demo"
    tries = {"n": 0}
    body = {"status": 503, "json": {}}

    class _R:
        @property
        def status_code(self): return body["status"]
        text = "upstream"
        def json(self): return body["json"]

    class _C:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, **kw):
            tries["n"] += 1
            return _R()
    xero_api.httpx.AsyncClient = lambda *a, **k: _C()
    try:
        xero_api._write_token({"refresh_token": "rt-healthy", "tenant_id": "t1"})
        xero_api._state["access"] = ""
        xero_api._state["access_exp"] = 0.0

        err = None
        try:
            run(xero_api._access_token())
        except Exception as e:
            err = e
        ok(isinstance(err, xero_api.XeroTransient),
           "a 5xx is a transient, not a dead credential: %r" % (err,))
        eq(tries["n"], 3, "and it was retried rather than given up on at once")
        ok("reconnect" not in str(err).lower() or "only if it persists" in str(err).lower(),
           "the advice does not tell them to reconnect: %s" % err)
        ok(xero_api.connected(), "the healthy refresh token was NOT thrown away")

        # Now Xero actually refuses the credential.
        body["status"], body["json"] = 400, {"error": "invalid_grant"}
        xero_api._state["access_exp"] = 0.0
        err = None
        try:
            run(xero_api._access_token())
        except Exception as e:
            err = e
        ok(not isinstance(err, xero_api.XeroTransient), "invalid_grant is not transient")
        ok("reconnect" in str(err).lower(), "and THAT one says reconnect: %s" % err)
        # Live fault 2026-10-07: the page kept a green Xero tag and offered no
        # Reconnect, because the refusal reached it only as a sentence.
        st = xero_api.status()
        ok(st.get("needs_reconnect") is True, "the status says so as a flag the page can act on: %r" % st)
        # A restart (every deploy) empties memory; the refusal must outlive it,
        # or the page goes back to a green tag over a dead link.
        xero_api._state["token_error"] = ""
        st = xero_api.status()
        ok(st.get("needs_reconnect") is True and "Reconnect" in (st.get("warning") or ""),
           "the refusal outlives a restart, with its warning: %r" % st)
        # A fresh consent writes a fresh token file, which carries no refusal.
        xero_api._write_token({"refresh_token": "rt-fresh", "tenant_id": "t1", "tenant_name": "Projected Image"})
        ok(xero_api.status().get("needs_reconnect") is False, "and a fresh consent clears it")
        xero_api.disconnect()
        ok(xero_api.status().get("needs_reconnect") is False, "as does a disconnect")
    finally:
        (xero_api.httpx.AsyncClient, xero_api.RETRY_WAITS,
         xero_api.CLIENT_ID, xero_api.CLIENT_SECRET) = saved
        xero_api._state["token_error"] = ""
        xero_api.disconnect()


@test
def t_a_token_that_could_not_be_saved_retries_inside_xeros_grace():
    """Xero rotates the refresh token on every use and honours the previous one
    for about 30 minutes. If the new one cannot be written, that grace is the
    whole safety margin: cache the access token for minutes rather than half an
    hour, and put it somewhere a person will see."""
    saved = (xero_api.httpx.AsyncClient, xero_api._write_token,
             xero_api.CLIENT_ID, xero_api.CLIENT_SECRET)
    xero_api.CLIENT_ID = xero_api.CLIENT_SECRET = "demo"

    class _R:
        status_code = 200
        text = ""
        def json(self):
            return {"access_token": "at-new", "refresh_token": "rt-rotated",
                    "expires_in": 1800}

    class _C:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, **kw): return _R()
    try:
        xero_api._write_token({"refresh_token": "rt-old", "tenant_id": "t1",
                               "tenant_name": "Projected Image"})
        xero_api.httpx.AsyncClient = lambda *a, **k: _C()
        def _boom(d):
            raise OSError("read-only file system")
        xero_api._write_token = _boom
        xero_api._state["access"] = ""
        xero_api._state["access_exp"] = 0.0
        at = run(xero_api._access_token())
        eq(at, "at-new", "the call still worked: the token itself is fine")
        left = xero_api._state["access_exp"] - time.monotonic()
        ok(left < 600, "the access token is cached for minutes, not the full 30: %.0fs" % left)
        st = xero_api.status()
        ok(st.get("warning"), "and the failure is on the status the tab reads")
        ok("volume" in st["warning"] or "save" in st["warning"].lower(),
           "in words that name the actual problem: %s" % st["warning"])
        ok(st.get("needs_reconnect") is False, "a token that could not be saved still works, so no reconnect yet")
    finally:
        (xero_api.httpx.AsyncClient, xero_api._write_token,
         xero_api.CLIENT_ID, xero_api.CLIENT_SECRET) = saved
        xero_api._state["save_failed_at"] = 0.0
        xero_api.disconnect()


@test
def t_xeros_daily_limit_is_said_at_once_not_retried():
    """Xero allows 1,000 calls a day per organisation on its Starter tier and
    5,000 above it. A daily 429 asks for a wait of hours: the client spent
    three retries on it and then showed a bare 429 in the reconciliation notes.
    It now says what happened, and when it clears, on the first answer."""
    calls, answers = [], []
    class _R:
        def __init__(self, status, headers):
            self.status_code, self.headers, self.content = status, headers, b"{}"
        def json(self):
            return {"Invoices": []}
        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(self.status_code)
    class _C:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, **kw):
            calls.append(url)
            return answers.pop(0)
    async def _tok():
        return "at"
    async def _no_pace():
        return None
    saved = (xero_api.httpx.AsyncClient, xero_api._access_token, xero_api._pace)
    xero_api.httpx.AsyncClient = lambda *a, **k: _C()
    xero_api._access_token, xero_api._pace = _tok, _no_pace
    try:
        answers[:] = [_R(429, {"X-Rate-Limit-Problem": "day", "Retry-After": "18000"})]
        try:
            run(xero_api._get("Invoices"))
            ok(False, "a daily 429 must raise")
        except xero_api.XeroDailyLimit as e:
            ok("daily limit" in str(e) and "about 5 hours" in str(e), str(e))
            ok(len(str(e)) <= 120, "and fits the line the reconciliation notes show")
        eq(len(calls), 1, "asked once, not retried")
        # A long wait marks the daily limit even if the header's wording changes.
        calls.clear(); answers[:] = [_R(429, {"Retry-After": "7200"})]
        try:
            run(xero_api._get("Invoices"))
            ok(False, "a two-hour wait must raise")
        except xero_api.XeroDailyLimit as e:
            ok("about 2 hours" in str(e), str(e))
        eq(xero_api._wait_words(600), "10 minutes")
        # The minute limit is still waited out and retried.
        calls.clear()
        answers[:] = [_R(429, {"X-Rate-Limit-Problem": "minute", "Retry-After": "1"}), _R(200, {})]
        eq(run(xero_api._get("Invoices")), {"Invoices": []})
        eq(len(calls), 2, "one wait, then the answer")
    finally:
        xero_api.httpx.AsyncClient, xero_api._access_token, xero_api._pace = saved


@test
def t_a_failed_revocation_keeps_the_token_rather_than_stranding_it():
    """Deleting our only copy of a token Xero would not revoke leaves a live
    credential in their hands with nothing left to kill it with. Keep it, say
    so, and let the merchant insist."""
    def go():
        ensure_auth()
        saved = (xero_api.CLIENT_ID, xero_api.CLIENT_SECRET, xero_api.httpx.AsyncClient)
        xero_api.CLIENT_ID = xero_api.CLIENT_SECRET = "demo"

        class _R:
            status_code = 500
            text = "boom"

        class _C:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, **kw): return _R()
        xero_api.httpx.AsyncClient = lambda *a, **k: _C()
        try:
            xero_api._write_token({"refresh_token": "rt-live", "tenant_id": "t1"})
            reconciliation._write_recon_cache({"xero": {"invoices": {"a": {"id": "a"}}}})
            r = post("/api/recon/disconnect", {"what": "xero"})
            eq(r.status_code, 502, r.text[:200])
            ok(r.json().get("can_force"), "the merchant is offered the way out")
            ok(xero_api.connected(), "the token is still here, so revoking can be retried")
            ok(reconciliation._load_recon_cache().get("xero"),
               "and the books were not deleted for a disconnect that did not happen")
            # Insisting forgets it anyway.
            r2 = post("/api/recon/disconnect", {"what": "xero", "force": 1})
            eq(r2.status_code, 200, r2.text[:200])
            ok(not xero_api.connected(), "forced, it is gone")
            eq(reconciliation._load_recon_cache().get("xero"), None, "and so are the books")
        finally:
            xero_api.CLIENT_ID, xero_api.CLIENT_SECRET, xero_api.httpx.AsyncClient = saved
            xero_api.disconnect()
    with_accounts(go)


@test
def t_the_books_are_not_handed_out_with_the_account():
    """Reconciliation reads the company's accounting records, its bank line and
    the accounts mailbox. A new dispatch login must not arrive already holding
    all three: it is granted deliberately, or not at all."""
    def go():
        r = post("/api/team/user", {"op": "create", "name": "Nia", "username": "niax",
                                    "role": "member"})
        uid, pw = r.json()["id"], r.json()["starter_password"]
        tabs = team._user_tabs(uid)
        ok(isinstance(tabs, list), "a member is not given the unrestricted None")
        ok("recon" not in tabs, "and reconciliation is not in the default grant")
        ok("labels" in tabs and "mail" in tabs,
           "while the everyday tabs still are: %r" % (tabs,))

        lg = client.post("/api/auth/login", json={"username": "niax", "password": pw},
                         headers={"Authorization": "Bearer " + tok()}).json()
        sess = lg.get("session")
        ch = post_s(sess, "/api/auth/password", {"current": pw, "new": "nia-pw-88231"})
        sess = ch.json().get("session") or sess
        rr = post_s(sess, "/api/recon/status", {})
        eq(rr.status_code, 403, "and the door is shut, not merely hidden")

        post("/api/team/user", {"op": "tabs", "id": uid, "tabs": ["labels", "recon"]})
        rr2 = post_s(sess, "/api/recon/status", {})
        eq(rr2.status_code, 200, "granted explicitly, it opens")
    with_accounts(go)


@test
def t_the_xero_double_cannot_drift_from_the_real_client():
    """This double once fell a parameter behind the real client. Three of the
    four reads raised TypeError, the sweep's per-source try/except turned each
    into a note, and the suite went on passing green over a sweep that had read
    a quarter of the accounts. A fake that no longer matches is not a test."""
    import inspect
    for name in ("list_invoices", "list_payments", "list_bank_transactions",
                 "list_credit_notes"):
        real = set(inspect.signature(getattr(xero_api, name)).parameters)
        fake = set(inspect.signature(getattr(_FakeXero, name)).parameters) - {"self"}
        eq(fake, real, name + ": the double has drifted from the real client")


@test
def t_a_sweep_that_could_not_read_an_account_says_so_out_loud():
    """The swallow-and-note handler is right, but it is also how a broken read
    hides. Any sweep in this suite that cannot read one of the four Xero
    endpoints must fail here rather than quietly check three of them."""
    fx = _FakeXero(invoices=[_raw_xinv("INV-104275", "842.00")],
                   payments=[], bank=[], notes_=[])
    st = _recon_world(fx, [_raw_order(1, "#104275", "842.00")])
    r = run(_rc.sweep())
    ok(r.get("ok"), "the sweep ran: %r" % (r,))
    bad = [n for n in (r.get("notes") or []) if "could not be read" in n]
    eq(bad, [], "no account went unread")
    for bucket in ("invoices", "payments", "bank_transactions", "credit_notes"):
        ok(bucket in (st["cache"].get("xero") or {}),
           "every Xero bucket was actually populated, including %s" % bucket)


@test
def t_every_xero_read_is_windowed():
    """Only invoices were filtered by date, so a first sync pulled the whole
    history of payments, bank lines and credit notes to reconcile four months
    of them. The safest copy of a record is the one never made."""
    sent = []

    async def fake_paged(path, key, params=None, ims=None, max_pages=50):
        sent.append((path, dict(params or {})))
        return []

    saved = xero_api._paged
    xero_api._paged = fake_paged
    try:
        run_async(xero_api.list_invoices(since="2026-05-01"))
        run_async(xero_api.list_payments(since="2026-05-01"))
        run_async(xero_api.list_bank_transactions(since="2026-05-01"))
        run_async(xero_api.list_credit_notes(since="2026-05-01"))
    finally:
        xero_api._paged = saved
    eq(len(sent), 4, sent)
    for path, params in sent:
        ok("where" in params, path + " is read without a date window")
        eq(params["where"], "Date >= DateTime(2026,5,1)",
           path + " uses the shared window: " + params["where"])


@test
def t_the_sweep_asks_for_one_window_not_all_history():
    """Watch what the sweep actually SENDS. Only invoices were windowed, so a
    first sync pulled every payment, bank line and credit note the business had
    ever recorded in order to check four months of them."""
    asked = {}

    class _Recorder(_FakeXero):
        async def list_invoices(self, since=None, modified_since=None):
            asked["invoices"] = since; return []
        async def list_payments(self, since=None, modified_since=None):
            asked["payments"] = since; return []
        async def list_bank_transactions(self, since=None, modified_since=None):
            asked["bank_transactions"] = since; return []
        async def list_credit_notes(self, since=None, modified_since=None):
            asked["credit_notes"] = since; return []

    _recon_world(_Recorder(), [])
    r = run(_rc.sweep())
    ok(r.get("ok"), "the sweep ran: %r" % (r,))
    eq(sorted(asked), ["bank_transactions", "credit_notes", "invoices", "payments"],
       "all four reads happened")
    eq(len(set(asked.values())), 1, "and all four asked for the SAME window: %r" % (asked,))
    # The horizon must be the one we KEEP records to, not the shorter window
    # the checks use, or a record still in the cache can never be refreshed.
    eq(list(asked.values())[0], _rc._cutoff_day(_rc.FETCH_DAYS),
       "the window is the retention horizon")
    eq(_rc.FETCH_DAYS, _rc.CACHE_KEEP_DAYS,
       "which is the same number we prune at, by construction")


@test
def t_reconciliation_stores_do_not_keep_records_for_ever():
    """Every other store in this app prunes. These held third parties'
    financial records and document text with no expiry at all."""
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    old = (_dt.now(_tz.utc) - _td(days=400)).strftime("%Y-%m-%d")
    recent = _dt.now(_tz.utc).strftime("%Y-%m-%d")
    cache = {"xero": {"invoices": {"old": {"id": "old", "date": old},
                                   "new": {"id": "new", "date": recent}},
                      "payments": {"po": {"id": "po", "date": old}}},
             "shopify": {"orders": {"oo": {"id": "oo", "created_at": old},
                                    "on": {"id": "on", "created_at": recent}}}}
    docs = {"d_old": {"date": old + "T09:00:00Z", "doc_type": "remittance"},
            "d_new": {"date": recent + "T09:00:00Z", "doc_type": "remittance"}}
    settled = _rc.make_exc("duplicate_bill_number", "high", "Settled long ago", ["s1"],
                           evidence=[_rc.ev("xero", "bill", "Bill 1", {"id": "b"}, 1)])
    settled["status"] = "explained"
    settled["updated"] = (_dt.now(_tz.utc) - _td(days=400)).isoformat()
    live = _rc.make_exc("overpaid_invoice", "high", "Still open", ["s2"],
                        evidence=[_rc.ev("xero", "invoice", "Invoice 2", {"id": "i"}, 1)])
    live["updated"] = (_dt.now(_tz.utc) - _td(days=400)).isoformat()
    store = {"exceptions": {settled["id"]: settled, live["id"]: live}}

    notes = _rc.prune(cache, docs, store)
    eq(set(cache["xero"]["invoices"]), {"new"}, "records past the window are dropped")
    eq(cache["xero"]["payments"], {}, "including payments, not just invoices")
    eq(set(cache["shopify"]["orders"]), {"on"}, "and the Shopify side too")
    eq(set(docs), {"d_new"}, "old documents go with them")
    eq(settled["evidence"], [], "a settled discrepancy sheds its copied records")
    ok(settled.get("evidence_dropped"), "and says that it did")
    ok(settled["title"] and settled["status"] == "explained",
       "while keeping what was decided: the audit trail is the point")
    ok(live["evidence"], "an OPEN discrepancy keeps its evidence however old it is")
    ok(any("dropped" in n for n in notes), "and the sweep reports the deletions: %s" % notes)


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


