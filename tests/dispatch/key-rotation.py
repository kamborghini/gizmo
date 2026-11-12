# =========================== key rotation: nothing locks out mid-swap ===================
_OLD_APP_SECRET = "the-old-app-secret-long-enough-for-hmac-32b"


def _token_signed_with(secret, **over):
    now = int(time.time())
    claims = {"iss": "https://test-store.myshopify.com/admin",
              "dest": "https://test-store.myshopify.com", "aud": "a",
              "exp": now + 120, "nbf": now - 5}
    claims.update(over)
    return jwt.encode(claims, secret, algorithm="HS256")


def raised(fn, msg):
    try:
        fn()
    except Exception:
        return
    raise AssertionError("FAIL: expected a refusal: " + msg)


def _with_previous_secret(value, fn):
    saved = getattr(config, "SHOPIFY_API_SECRET_PREVIOUS", "")
    config.SHOPIFY_API_SECRET_PREVIOUS = value
    try:
        fn()
    finally:
        config.SHOPIFY_API_SECRET_PREVIOUS = saved


@test
def t_a_session_token_signed_with_the_previous_secret_signs_in_while_the_app_secret_is_rotated():
    """Rotating the app's client secret is two steps at Shopify: make a new
    secret (both stay valid), then revoke the old one. Reactor holds one secret,
    and while two are live Shopify may still sign App Bridge's session tokens
    with the old one, so the moment Reactor ran on the new secret every page
    could refuse everyone until the old one was revoked. The previous secret,
    set only for the swap, is accepted for checking a token; anything else
    still fails as it did."""
    old_token = _token_signed_with(_OLD_APP_SECRET)
    raised(lambda: team._verify_session_token(old_token), "with no previous secret set, a token signed with another secret is refused")

    def during_the_swap():
        ok(team._verify_session_token(old_token).get("dest") == "https://test-store.myshopify.com",
           "a token signed with the previous secret is accepted")
        ok(team._verify_session_token(tok()).get("dest"), "and one signed with the current secret still is")
        raised(lambda: team._verify_session_token(_token_signed_with("a-secret-that-was-never-the-apps-at-all-32b")),
               "a token signed with neither is refused")
        raised(lambda: team._verify_session_token(_token_signed_with(_OLD_APP_SECRET, exp=int(time.time()) - 600, nbf=int(time.time()) - 900)),
               "and an expired one signed with the previous secret is refused for being expired")
        h = {"Authorization": "Bearer " + old_token, "X-App-Session": ensure_auth()}
        r = client.post("/api/team/me", json={}, headers=h)
        ok(r.status_code != 401, "a page request carrying it gets through the door: %s %s" % (r.status_code, r.text[:200]))
    _with_previous_secret(_OLD_APP_SECRET, during_the_swap)


@test
def t_order_and_privacy_webhooks_signed_with_the_previous_secret_are_taken_during_the_swap():
    """Shopify keeps signing webhooks with the oldest secret it has not been
    told to revoke, for up to an hour after the revoke. With one secret in
    Reactor, every order update and privacy request in that window was refused
    401, Shopify retried, and enough failures delete a subscription. During the
    swap both secrets are taken; outside it only the app's own."""
    raw = json.dumps({"id": 991001, "name": "#991001"}).encode()
    old_signed = wh_headers(raw, secret=_OLD_APP_SECRET, delivery="rotation-1")
    eq(client.post("/webhooks/orders", content=raw, headers=old_signed).status_code, 401,
       "outside a swap, an order webhook signed with another secret is refused")

    def during_the_swap():
        r = client.post("/webhooks/orders", content=raw, headers=wh_headers(raw, secret=_OLD_APP_SECRET, delivery="rotation-2"))
        ok(r.status_code != 401, "an order webhook signed with the previous secret is taken: %s" % r.status_code)
        r = client.post("/webhooks/orders", content=raw,
                        headers=wh_headers(raw, secret="a-secret-that-was-never-the-apps-at-all-32b", delivery="rotation-3"))
        eq(r.status_code, 401, "one signed with neither is still refused")
        praw = json.dumps({"shop_id": 1, "shop_domain": "test-store.myshopify.com",
                           "customer": {"id": 1}, "orders_requested": []}).encode()
        r = client.post("/webhooks/privacy", content=praw,
                        headers=wh_headers(praw, secret=_OLD_APP_SECRET, topic="customers/data_request", delivery="rotation-4"))
        ok(r.status_code != 401, "a privacy webhook signed with the previous secret is taken: %s" % r.status_code)
    _with_previous_secret(_OLD_APP_SECRET, during_the_swap)


@test
def t_a_refusal_from_the_xero_sync_service_is_an_error_on_the_page_not_a_sign_out():
    """The page treats a 401 as Reactor refusing the person: it clears their
    sign-in and reloads. The Xero sync service answers 401 when it refuses
    Reactor's own key (the two copies out of step, as during a key rotation),
    and Reactor passed that status straight on, so anyone who opened Xero sync
    was signed out. The service checks no person's permissions (Reactor does,
    before it calls), so its 401 or 403 can only be about the key: it reaches
    the page as a 502 that says so."""
    import httpx as _hx
    answers = {"status": 401}
    def handler(request):
        if answers["status"] == 401:
            return _hx.Response(401, json={"error": "Unauthorized: send the token as an Authorization: Bearer header."})
        return _hx.Response(answers["status"], json={"error": "the service's own words"})
    saved = (xerosync.httpx, os.environ.get("CONNECTOR_URL"), os.environ.get("CONNECTOR_TOKEN"))
    xerosync.httpx = _RoutedHttpx(handler)
    os.environ["CONNECTOR_URL"] = "https://connector.example.test"
    os.environ["CONNECTOR_TOKEN"] = "reactors-copy-of-the-key"
    try:
        answers["status"] = 401
        r = post("/api/connector", {"op": "status"})
        eq(r.status_code, 502, "the service's 401 is not passed on as a refusal of the person")
        ok(re.search(r"refused Reactor's key", r.json().get("error", "")), "and the error says it is about the key: " + r.text[:200])
        ok("no longer matches" in r.json().get("error", ""), "the two copies are out of step")
        ok(not re.search(r"Railway|CONNECTOR_TOKEN|DASHBOARD_TOKEN", r.json().get("error", "")),
           "in words, not hosting or setting names")
        os.environ["CONNECTOR_TOKEN"] = ""
        r = post("/api/connector", {"op": "status"})
        eq(r.status_code, 502)
        ok("holds no key" in r.json().get("error", ""), "with no key at all, it says so rather than a mismatch: " + r.text[:200])
        os.environ["CONNECTOR_TOKEN"] = "reactors-copy-of-the-key"
        for status in (403, 500):
            answers["status"] = status
            r = post("/api/connector", {"op": "status"})
            eq(r.status_code, status, "a %d (the 403 is the service's own forgery guard, never the key) comes through as it was" % status)
    finally:
        xerosync.httpx = saved[0]
        for k, v in (("CONNECTOR_URL", saved[1]), ("CONNECTOR_TOKEN", saved[2])):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v



@test
def t_a_webhook_signature_with_a_stray_byte_is_refused_not_a_server_error():
    """Anyone can send a webhook, and the signature header is compared as
    text: a header holding a byte outside ASCII made the comparison raise, so
    the door answered 500 rather than 401. Shopify retries a 500, and a
    stranger's probe should read as what it is."""
    raw = json.dumps({"id": 991002}).encode()
    headers = wh_headers(raw, delivery="rotation-5")
    headers["X-Shopify-Hmac-Sha256"] = b"\xff" * 44   # raw bytes, as a stranger can send them
    eq(client.post("/webhooks/orders", content=raw, headers=headers).status_code, 401, "the orders door refuses it")
    eq(client.post("/webhooks/privacy", content=raw, headers=headers).status_code, 401, "and so does the privacy door")


@test
def t_the_previous_secret_left_set_is_said_at_every_start():
    """Revoking the old secret at Shopify does not stop Reactor accepting it:
    Reactor checks the signature itself. Left set after the swap, it would be
    accepted for as long as nobody looked, so every start says it is set."""
    import logging as _lg
    seen = []
    class Grab(_lg.Handler):
        def emit(self, record):
            seen.append(record.getMessage())
    h = Grab()
    _lg.getLogger().addHandler(h)
    try:
        _with_previous_secret(_OLD_APP_SECRET, lambda: server._boot_report())
        ok(any("previous app secret" in m for m in seen), "a start with it set says so: " + " | ".join(seen)[:300])
        seen.clear()
        server._boot_report()
        ok(not any("previous app secret" in m for m in seen), "and a start without it says nothing about it")
    finally:
        _lg.getLogger().removeHandler(h)

