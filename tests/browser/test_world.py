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
    has("/api/liability", {"fresh": True}, "Kestrel Logistics Ltd")
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


@test
def t_the_server_playwright_stops_leaves_no_scratch_folder():
    """Playwright ends its web server with SIGKILL unless the config names a
    signal to stop it with, and nothing survives SIGKILL to tidy up, so every
    browser run left its world's gizmo-dispatch-tests-* folder in the temp dir
    (191 of the 893 there on 20 October 2026). The server is started here with
    the config's own command, in a process group as Playwright starts it, and
    stopped with the config's own signal inside its own grace period, in a
    temp dir of its own that must be empty once the server has gone."""
    import shutil, signal, socket, subprocess, tempfile, threading
    base = tempfile.mkdtemp(prefix="browser-serve-test-")
    tmp, run = os.path.join(base, "tmp"), os.path.join(base, "run")
    os.makedirs(tmp)
    p = None
    try:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        cfg = subprocess.run(["node", "-e", "process.stdout.write(JSON.stringify(require(process.argv[1]).webServer))",
                              os.path.join(HERE, "playwright.config.js")],
                             env=dict(os.environ, PY=sys.executable, BROWSER_PORT=str(port), BROWSER_RUN=run),
                             capture_output=True, text=True, timeout=60)
        ok(cfg.returncode == 0, "the config would not load: " + cfg.stderr[-400:])
        web = json.loads(cfg.stdout)
        stop = web.get("gracefulShutdown")
        ok(stop, "webServer names no gracefulShutdown, so Playwright stops the server with SIGKILL "
                 "and its scratch folder is never removed")
        p = subprocess.Popen(web["command"], shell=True, cwd=web["cwd"], start_new_session=True,
                             env=dict(os.environ, TMPDIR=tmp, **web["env"]),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        lines, ready = [], threading.Event()
        def read():
            for line in p.stdout:
                lines.append(line)
                if "browser world ready" in line:
                    ready.set()
        threading.Thread(target=read, daemon=True).start()
        ok(ready.wait(web.get("timeout", 180000) / 1000), "the server never came up: " + "".join(lines)[-800:])
        os.killpg(p.pid, getattr(signal, stop["signal"]))
        grace = (stop.get("timeout") or 60000) / 1000
        try:
            p.wait(grace)
        except subprocess.TimeoutExpired:
            raise AssertionError("the server was still up %ss after %s, when Playwright gives up and sends SIGKILL"
                                 % (grace, stop["signal"]))
        ok(os.listdir(tmp) == [], "the stopped server left %r in its temp dir (exit %s)" % (os.listdir(tmp), p.returncode))
    finally:
        if p is not None and p.poll() is None:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    passed = failed = 0
    for fn in [t for t in TESTS if os.environ.get("ONLY", "") in t.__name__]:
        try:
            fn(); passed += 1; print("  PASS ", fn.__name__)
        except Exception as e:
            failed += 1; print("  FAIL ", fn.__name__, "-", e)
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
