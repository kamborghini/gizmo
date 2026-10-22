# ---- Token encryption at rest -----------------------------------------------

@test
def t_without_a_key_the_vault_is_a_no_op():
    """Every existing deployment has plaintext token files and no key set.
    Turning this on must not lock the app out of its own mailbox."""
    import tokenvault
    old = os.environ.pop("TOKEN_ENCRYPTION_KEY", None)
    try:
        tokenvault._key.cache_clear()
        eq(tokenvault.seal("1//refresh-token"), "1//refresh-token", "sealed is the same string")
        eq(tokenvault.unseal("1//refresh-token"), "1//refresh-token", "and comes back out")
    finally:
        if old is not None:
            os.environ["TOKEN_ENCRYPTION_KEY"] = old
        tokenvault._key.cache_clear()


@test
def t_with_a_key_a_token_round_trips_and_is_not_readable_on_disk():
    import tokenvault
    os.environ["TOKEN_ENCRYPTION_KEY"] = "a-long-enough-test-key-for-scrypt-0123456789"
    tokenvault._key.cache_clear()
    try:
        secret = "1//0gRefreshTokenThatWouldReadAMailbox"
        sealed = tokenvault.seal(secret)
        ok(sealed != secret, "what lands on disk is not the token")
        ok(secret not in sealed, "and does not contain it")
        ok(sealed.startswith("v1:"), "it is tagged so a reader can tell")
        eq(tokenvault.unseal(sealed), secret, "and it opens again")
        ok(tokenvault.seal(secret) != sealed, "a second seal differs: the nonce is fresh")
    finally:
        os.environ.pop("TOKEN_ENCRYPTION_KEY", None)
        tokenvault._key.cache_clear()


@test
def t_a_plaintext_token_written_before_the_key_still_opens():
    """The migration case. A file written before encryption was turned on holds
    a bare token; refusing it would take the connection down."""
    import tokenvault
    os.environ["TOKEN_ENCRYPTION_KEY"] = "a-long-enough-test-key-for-scrypt-0123456789"
    tokenvault._key.cache_clear()
    try:
        eq(tokenvault.unseal("1//plain-old-token"), "1//plain-old-token")
    finally:
        os.environ.pop("TOKEN_ENCRYPTION_KEY", None)
        tokenvault._key.cache_clear()


@test
def t_a_tampered_or_wrongly_keyed_envelope_fails_closed():
    """Returning garbage would send a corrupted token to Google and read as a
    revoked connection. It has to raise instead."""
    import tokenvault
    os.environ["TOKEN_ENCRYPTION_KEY"] = "a-long-enough-test-key-for-scrypt-0123456789"
    tokenvault._key.cache_clear()
    sealed = tokenvault.seal("1//real-token")
    try:
        bad = sealed[:-4] + ("AAAA" if not sealed.endswith("AAAA") else "BBBB")
        raised = False
        try:
            tokenvault.unseal(bad)
        except tokenvault.VaultError:
            raised = True
        ok(raised, "a tampered envelope raises rather than returning something")
        os.environ["TOKEN_ENCRYPTION_KEY"] = "a-completely-different-key-987654321-abcdef"
        tokenvault._key.cache_clear()
        raised2 = False
        try:
            tokenvault.unseal(sealed)
        except tokenvault.VaultError:
            raised2 = True
        ok(raised2, "and so does the wrong key")
    finally:
        os.environ.pop("TOKEN_ENCRYPTION_KEY", None)
        tokenvault._key.cache_clear()


@test
def t_every_stored_refresh_token_goes_through_the_vault():
    """Four files hold long-lived credentials. Sealing three of them and
    forgetting the fourth is the whole exposure, so this asserts each module's
    single read and single write both pass through."""
    import inspect as _i, google_mail as _gm2, google_data as _gd2
    import xero as _xr2
    for mod, writer, reader in ((_xr2, "_write_token", "_load_token"),
                                (_gd2, "save_refresh_token", "_load_refresh_token"),
                                (_gm2, "save_connection", "_load_token_file")):
        w = _i.getsource(getattr(mod, writer))
        r = _i.getsource(getattr(mod, reader))
        ok("tokenvault.seal" in w, f"{mod.__name__}.{writer} seals before writing")
        ok("tokenvault.unseal" in r, f"{mod.__name__}.{reader} opens after reading")


@test
def t_a_real_token_file_round_trips_through_the_vault_on_disk():
    """The end-to-end shape: what lands in the file is not the token, and the
    module still hands the token back."""
    import google_mail as _gm2, tokenvault
    os.environ["TOKEN_ENCRYPTION_KEY"] = "a-long-enough-test-key-for-scrypt-0123456789"
    tokenvault._key.cache_clear()
    try:
        secret = "1//0gTheRealRefreshToken"
        _gm2.save_connection(secret, "sales@example.com")
        raw = open(_gm2.SALES.token_path, encoding="utf-8").read()
        ok(secret not in raw, "the token is not sitting in the file")
        ok('"v1:' in raw, "an envelope is")
        eq(_gm2._load_token_file()["refresh_token"], secret, "and it opens again")
        eq(_gm2.connected(), True, "so the connection still reads as live")
    finally:
        os.environ.pop("TOKEN_ENCRYPTION_KEY", None)
        tokenvault._key.cache_clear()
        try:
            os.remove(_gm2.SALES.token_path)
        except OSError:
            pass


