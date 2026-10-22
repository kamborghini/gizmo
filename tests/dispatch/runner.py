if os.environ.get("SUITE_SELFTEST"):
    @test
    def t_suite_selftest_logs_and_passes():
        logging.getLogger("shopify_mcp.copilot").warning("selftest: a passing test's line")

    @test
    def t_suite_selftest_logs_and_fails():
        logging.getLogger("shopify_mcp.copilot").warning("selftest: a failing test's line")
        raise AssertionError("selftest: this one fails on purpose")

for fn in [t for t in TESTS if os.environ.get("ONLY", "") in t.__name__]:
    # A fresh client per test, for the per-client SIGN-IN ceiling only. The
    # suite makes hundreds of sign-ins from one address; a browser makes a
    # handful, which is what LOGIN_MAX_PER_MIN is sized for. The ceiling has
    # its own test rather than being weakened for everyone else's sake.
    team._login_hits.clear()
    # A missed-orders answer is kept until an order changes, and one test's
    # stubbed shop is not the next test's: nothing changes between them.
    production._missing_cache.clear()
    _TEST_LOG.seek(0); _TEST_LOG.truncate(0)
    reached = len(NET_REACHED)
    try:
        fn()
        if len(NET_REACHED) > reached:
            raise AssertionError("reached the network: " + ", ".join(sorted(set(NET_REACHED[reached:]))))
        passed += 1; print(f"  PASS  {fn.__name__}")
    except Exception as e:
        failed += 1; print(f"  FAIL  {fn.__name__}: {e}")
        held = _TEST_LOG.getvalue().rstrip().split("\n") if _TEST_LOG.getvalue().strip() else []
        if held:
            print("        what it logged" + (f" (the last 80 of {len(held)} lines)" if len(held) > 80 else "") + ":")
            for line in held[-80:]:
                print("        | " + line)
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
