# ---- Second factor ----------------------------------------------------------

@test
def t_totp_matches_the_rfc_vectors():
    """Codes are checked against RFC 6238's own test vectors rather than
    against this implementation's output, which would only prove it agrees
    with itself. An authenticator app has to accept these."""
    import totp, base64
    secret = base64.b32encode(b"12345678901234567890").decode()   # RFC 6238 seed
    for at, want in ((59, "287082"), (1111111109, "081804"),
                     (1234567890, "005924"), (2000000000, "279037")):
        eq(totp.code(secret, at=at), want, f"the code at t={at}")


@test
def t_a_code_is_accepted_across_a_little_clock_skew_and_no_more():
    """Phones drift. One step either side is the usual allowance; two is a
    minute of extra guessing room for no real gain."""
    import totp, base64
    secret = base64.b32encode(b"12345678901234567890").decode()
    now = 1234567890
    eq(totp.verify(secret, totp.code(secret, at=now), at=now), True, "the current code")
    eq(totp.verify(secret, totp.code(secret, at=now - 30), at=now), True, "one step behind")
    eq(totp.verify(secret, totp.code(secret, at=now + 30), at=now), True, "one step ahead")
    eq(totp.verify(secret, totp.code(secret, at=now - 90), at=now), False, "three steps behind")
    eq(totp.verify(secret, "000000", at=now), False, "and a wrong code")


@test
def t_a_used_code_cannot_be_used_again():
    """Without this a code shoulder-surfed or read off a proxy log stays valid
    for its whole window."""
    import totp, base64
    secret = base64.b32encode(b"12345678901234567890").decode()
    now = 1234567890
    c = totp.code(secret, at=now)
    used = totp.verify(secret, c, at=now, last_counter=None)
    eq(used, True, "first use is fine")
    eq(totp.verify(secret, c, at=now, last_counter=now // 30), False,
       "the same code inside the same window is refused")


@test
def t_a_recovery_code_works_once_and_then_does_not():
    """The way back in when the phone is gone. Stored hashed, so the file does
    not hand someone the codes."""
    import totp
    codes = totp.recovery_codes(8)
    eq(len(codes), 8, "a handful, not one")
    ok(all(len(c) >= 10 for c in codes), "long enough not to be guessed")
    hashes = [totp.hash_recovery(c) for c in codes]
    ok(all(codes[0] not in h for h in hashes), "the plaintext is not in the stored form")
    idx = totp.check_recovery(codes[3], hashes)
    eq(idx, 3, "the right one matches")
    hashes.pop(idx)
    eq(totp.check_recovery(codes[3], hashes), -1, "and once spent it is gone")


@test
def t_login_is_unchanged_for_an_account_with_no_second_factor():
    """Nobody has MFA on the day it ships. It must not stand between anyone and
    their work until they choose to turn it on."""
    def go():
        ensure_auth()
        _uid, sess, _pw = ready_user("Plain Person", "plainperson")
        ok(sess, "a password alone still returns a session")
    with_accounts(go)


@test
def t_turning_on_a_second_factor_takes_a_code_to_confirm():
    """Enrolling on the strength of "I scanned it" is how people lock
    themselves out. It is not on until a code from the app proves it works."""
    def go():
        ensure_auth()
        r = post("/api/auth/mfa", {"op": "start", "current": MASTER_PW})
        eq(r.status_code, 200, r.text)
        j = r.json()
        ok(j.get("secret"), "a secret to scan")
        ok(str(j.get("uri", "")).startswith("otpauth://totp/"), "and the URI behind the QR")
        eq(post("/api/auth/mfa", {"op": "status"}).json().get("enabled"), False,
           "not on yet")
        import totp
        bad = post("/api/auth/mfa", {"op": "confirm", "code": "000000"})
        eq(bad.status_code, 400, "a wrong code does not enable it")
        good = post("/api/auth/mfa", {"op": "confirm", "code": totp.code(j["secret"])})
        eq(good.status_code, 200, good.text)
        ok(len(good.json().get("recovery") or []) >= 8, "recovery codes, shown once")
        eq(post("/api/auth/mfa", {"op": "status"}).json().get("enabled"), True, "now on")
    with_accounts(go)


@test
def t_with_a_second_factor_a_password_alone_is_not_a_session():
    def go():
        ensure_auth()
        import totp
        j = post("/api/auth/mfa", {"op": "start", "current": MASTER_PW}).json()
        post("/api/auth/mfa", {"op": "confirm", "code": totp.code(j["secret"])})
        r = bare("/api/auth/login", {"username": "cameron", "password": MASTER_PW})
        eq(r.status_code, 200, r.text)
        body = r.json()
        eq(body.get("session"), None, "no session from the password")
        eq(body.get("mfa"), True, "it asks for the second factor")
        ok(body.get("ticket"), "with a ticket to finish on")

        eq(bare("/api/auth/mfa-verify", {"ticket": body["ticket"], "code": "000000"}
                ).status_code, 401, "a wrong code gets nothing")
        # The NEXT window's code, not the one enrolment just consumed. Spending
        # a code on confirm is correct - it was used - so a real phone shows a
        # fresh one by the time anybody signs in.
        import time as _t
        done = bare("/api/auth/mfa-verify",
                    {"ticket": body["ticket"],
                     "code": totp.code(j["secret"], at=_t.time() + 30)})
        eq(done.status_code, 200, done.text)
        ok(done.json().get("session"), "and the right one finishes the login")
    with_accounts(go)


@test
def t_a_recovery_code_gets_you_in_when_the_phone_is_gone():
    def go():
        ensure_auth()
        import totp
        j = post("/api/auth/mfa", {"op": "start", "current": MASTER_PW}).json()
        codes = post("/api/auth/mfa",
                     {"op": "confirm", "code": totp.code(j["secret"])}).json()["recovery"]
        tick = bare("/api/auth/login",
                    {"username": "cameron", "password": MASTER_PW}).json()["ticket"]
        r = bare("/api/auth/mfa-verify", {"ticket": tick, "code": codes[0]})
        eq(r.status_code, 200, r.text)
        ok(r.json().get("session"), "the recovery code let them in")
        tick2 = bare("/api/auth/login",
                     {"username": "cameron", "password": MASTER_PW}).json()["ticket"]
        eq(bare("/api/auth/mfa-verify", {"ticket": tick2, "code": codes[0]}).status_code,
           401, "and it is spent")
    with_accounts(go)


@test
def t_the_totp_secret_is_not_stored_in_the_clear():
    """It is a credential like any other: whoever reads it can mint codes."""
    def go():
        ensure_auth()
        import totp, tokenvault
        os.environ["TOKEN_ENCRYPTION_KEY"] = "a-long-enough-test-key-for-scrypt-0123456789"
        tokenvault._key.cache_clear()
        try:
            j = post("/api/auth/mfa", {"op": "start", "current": MASTER_PW}).json()
            post("/api/auth/mfa", {"op": "confirm", "code": totp.code(j["secret"])})
            raw = open(team.USERS_PATH, encoding="utf-8").read()
            ok(j["secret"] not in raw, "the secret is not sitting in the users file")
        finally:
            os.environ.pop("TOKEN_ENCRYPTION_KEY", None)
            tokenvault._key.cache_clear()
    with_accounts(go)


