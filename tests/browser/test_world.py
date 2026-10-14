"""The browser suite's world, proven without a browser: the dispatch setup,
then the seed, then the read routes the screens call, each answering with
seeded content. `make test-browser` and CI's browser job run this first, so a
screen the seed stopped filling is named here rather than measured empty."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import serve  # noqa: E402

TESTS = []
def test(fn): TESTS.append(fn); return fn
def ok(c, msg=""):
    if not c: raise AssertionError("FAIL: " + msg)

_W = {}
def world():
    if not _W:
        _W.update(serve.build_world())
    return _W

def read(path, body=None):
    r = world()["post"](path, body or {})
    ok(r.status_code == 200, "%s answered %s: %s" % (path, r.status_code, r.text[:200]))
    return r.json()

def has(path, body, *texts):
    blob = json.dumps(read(path, body), ensure_ascii=False)
    for t in texts:
        ok(t in blob, "%s %s does not carry %r" % (path, json.dumps(body), t))


@test
def t_the_setup_is_found_or_the_server_refuses_to_start():
    try:
        serve.prelude_source_from("import os\nprint('no tests here')\n")
    except SystemExit as e:
        ok("@test" in str(e), "the refusal names the marker it looked for: %s" % e)
    else:
        raise AssertionError("a setup with no @test marker was served")


@test
def t_the_dashboards_are_filled():
    has("/api/cache", {}, "Revenue is up on last week", "The store is indexable", "custom gobo", "Champions",
        "Custom gobo terms lead")
    has("/api/products", {"months": 24, "fresh": True}, "Walkway Safety Sign Gobo")
    has("/api/liability", {"fresh": True}, "Kestrel Logistics Ltd")
    has("/api/recon/exceptions", {}, "Kilnworth Glass Supplies Ltd")
    has("/api/forecast", {}, "Algorithm 1", "Algorithm 2", "Cash Flow plan.xlsx")
    has("/api/connector", {"op": "status"}, "test-store.myshopify.com")


@test
def t_the_operations_screens_are_filled():
    has("/api/production-labels", {"tag": "IP", "fresh": False}, "#210388", "Hartwell Events Ltd")
    has("/api/custom/list", {"limit": 200}, "Replacement gobo", "Loan projector return label")
    has("/api/customer-history", {"customer_id": 502}, "#210351")
    has("/api/production-labels/coverage", {"orders": 200}, "Moonbeam Profile 300")
    has("/api/crm/board", {}, "Fernhill walkway safety signs", "Marcus Bell", "Rental stock enquiry",
        "Site visit for window throw", "Too expensive")
    has("/api/loans", {"op": "board"}, "Quayside Exhibitions", "Loan 1")
    has("/api/mail/board", {}, "Artwork for the autumn tour gobos")
    has("/api/files/tree", {}, "Artwork", "price-list-2026.pdf")


@test
def t_the_workspace_screens_are_filled():
    has("/api/team/board", {}, "Hattie Brennan", "Jonah Featherstone", "price-list-2026.pdf")
    has("/api/work/board", {}, "Jonah Featherstone", "left the bench without clocking out")
    has("/api/memory", {}, "Chase the B-size glass blank reorder")
    has("/api/skills", {}, "Quoting custom gobos", "Replying to trade accounts")
    has("/api/updates", {}, "Hattie Brennan", "Warn when a loan unit is overdue by a week")
    convos = world()["SEEDED"]["localStorage"].get("sc_convos_v1") or ""
    for t in ("How did September sales compare with August?", "September was up on August"):
        ok(t in convos, "chat's conversations are handed to the browser with %r" % t)


@test
def t_the_two_shopify_stores_are_one():
    s = world()["SEEDED"]
    ok(s["ops_orders"] == 12, "the Production Manager's twelve orders are in the store: %s" % s["ops_orders"])
    ok(s["orders"] > 1000, "beside the dashboards' history: %s" % s["orders"])
    has("/api/production-labels", {"tag": "IP", "fresh": False}, "#210388")
    has("/api/liability", {"fresh": True}, "Kestrel Logistics Ltd")


@test
def t_nothing_in_the_world_reached_the_network():
    reached = world().get("NET_REACHED") or []
    ok(not reached, "the seed reached the network: %s" % reached[:5])


if __name__ == "__main__":
    passed = failed = 0
    for fn in [t for t in TESTS if os.environ.get("ONLY", "") in t.__name__]:
        try:
            fn(); passed += 1; print("  PASS ", fn.__name__)
        except Exception as e:
            failed += 1; print("  FAIL ", fn.__name__, "-", e)
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
