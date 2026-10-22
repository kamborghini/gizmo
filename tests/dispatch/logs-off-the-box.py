# ---- Shipping logs off the box ----------------------------------------------

@test
def t_without_a_drain_url_nothing_is_installed():
    """Every deployment today has no drain. Adding one must not change how the
    app behaves for anyone who has not configured it."""
    import logdrain
    logdrain.stop()
    eq(logdrain.install(""), False, "no URL, no handler")
    eq(logdrain.pending(), 0, "and nothing queued")


@test
def t_a_log_line_and_an_audit_event_both_reach_the_drain():
    """The audit ledger lives on the volume it audits, so a lost volume takes
    the evidence with it. Both streams go off the box."""
    import logdrain, logging as _lg
    got = []
    logdrain.stop()
    logdrain.install("https://sink.example/ingest", sender=lambda batch: got.extend(batch))
    try:
        _lg.getLogger("shopify_mcp.copilot").warning("a thing happened")
        logdrain.audit({"who": "u1", "action": "booked a shipment"})
        logdrain.flush(timeout=3)
        ok(any("a thing happened" in str(e.get("message", "")) for e in got),
           "the log line arrived")
        ok(any(e.get("kind") == "audit" for e in got), "and so did the audit event")
    finally:
        logdrain.stop()


@test
def t_a_drain_that_is_down_never_reaches_the_caller():
    """A logging sink must not be able to take the dispatch desk with it."""
    import logdrain, logging as _lg
    logdrain.stop()
    def explode(batch):
        raise RuntimeError("sink is on fire")
    logdrain.install("https://sink.example/ingest", sender=explode)
    try:
        _lg.getLogger("shopify_mcp.copilot").error("this must not raise")
        logdrain.audit({"who": "u1", "action": "still fine"})
        logdrain.flush(timeout=3)
        ok(True, "logging through a broken drain did not raise")
    finally:
        logdrain.stop()


@test
def t_a_backed_up_drain_drops_rather_than_blocking():
    """Unbounded buffering turns a slow sink into an out-of-memory kill. The
    queue is bounded and the drops are counted, not silent."""
    import logdrain
    logdrain.stop()
    logdrain.install("https://sink.example/ingest", sender=lambda b: None, maxsize=10, autostart=False)
    try:
        for i in range(200):
            logdrain.audit({"n": i})
        ok(logdrain.pending() <= 10, f"the queue stayed bounded ({logdrain.pending()})")
        ok(logdrain.dropped() > 0, "and the drops were counted")
    finally:
        logdrain.stop()


@test
def t_the_drain_does_not_ship_secrets():
    """Log lines carry whatever was interpolated into them. A token reaching a
    third-party sink is a leak with extra steps."""
    import logdrain
    got = []
    logdrain.stop()
    logdrain.install("https://sink.example/ingest", sender=lambda b: got.extend(b))
    try:
        logdrain.audit({"msg": "refresh_token=1//0gSecretValueHere and shpat_abcdef123456"})
        logdrain.flush(timeout=3)
        blob = json.dumps(got)
        ok("1//0gSecretValueHere" not in blob, "the refresh token was scrubbed")
        ok("shpat_abcdef123456" not in blob, "and so was the Shopify token")
        ok("[redacted]" in blob, "leaving a mark that something was removed")
    finally:
        logdrain.stop()


@test
def t_the_audit_ledger_is_mirrored_off_the_volume_it_audits():
    """A file on the volume it audits is evidence that disappears with whatever
    took the volume. Every _track line also goes to the drain."""
    import logdrain, inspect as _i
    got = []
    logdrain.stop()
    logdrain.install("https://sink.example/ingest", sender=lambda b: got.extend(b))
    try:
        activity._track("u1", "sizes", "changed a size rule", "Showtec EagleStrike set to 37.5 mm")
        logdrain.flush(timeout=3)
        ok(any(e.get("kind") == "audit" and "size rule" in str(e.get("action", ""))
               for e in got), "the ledger line left the box")
    finally:
        logdrain.stop()
    src = _i.getsource(activity._track)
    ok("except Exception" in src.split("logdrain.audit")[1][:120],
       "and a drain failure can never fail the thing being audited")


