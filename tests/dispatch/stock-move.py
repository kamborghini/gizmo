# ---- Stock in Reactor: the switch (plan 4) ------------------------------------------
# The converter's switch-day duties (warnings raised once, orders from before
# the move the oldest, the names that need an account, installing what was
# proven) and moving in from Reactor itself. Invented data only.

def _stock_tool(*args, env=None):
    """Run the converter as Reactor runs it: a child process, the harness's stock paths in its environment."""
    tool = os.path.join(HERE, "tools", "stock_import.py")
    return _subprocess.run([sys.executable, tool] + list(args), capture_output=True, text=True,
                           env=dict(os.environ, **(env or {})))

def _stock_names_in(folder):
    return sorted(n for n in os.listdir(folder) if n.startswith("stock_"))

def _stock_export_files(name, export=None, people=None):
    """The export and the people file written where the converter reads them."""
    folder = _stock_out(name + "-in")
    ef, pf = os.path.join(folder, "export.json"), os.path.join(folder, "people.json")
    json.dump(export or _stock_export(), open(ef, "w", encoding="utf-8"))
    json.dump(people or PEOPLE, open(pf, "w", encoding="utf-8"))
    return ef, pf

@test
def t_converted_stock_warnings_are_raised_once():
    """Section 7: a warning is raised once. The stock app raised its own, and
    they arrive with the move; without a record of them, the first snapshot
    after the switch raised every current warning again. A line already
    warned about in the export stands; a low line the stock app never warned
    about does not, so it is raised."""
    export = _stock_export(low_lines=True)
    out = _stock_out("standing")
    stock_import.convert(export, PEOPLE, out)
    with stock_store.rooted(out):
        alerts = stock_store.load_alerts()
        items = sorted(stock_store.load_items()["items"].values(), key=lambda i: i["id"])
        meta = stock_store.load_settings()["meta"]
    eq(alerts.get("standing"), {"Glass|Blue|20|": "low_stock"}, "the carried warning stands, the other does not")
    eq(stock_import.prove(export, out), [], "and the proof agrees")
    before = len(alerts["alerts"])
    stock._raise_warnings(alerts, sfig.detect_anomalies(items, meta))
    raised = [a["item_key"] for a in alerts["alerts"][before:]]
    eq(raised, ["Glass|Blue|20||#2"], "the next snapshot raises only the line never warned about")

@test
def t_stock_orders_from_before_the_move_are_the_oldest():
    """What no "ordered" line accounts for was ordered before any of them, so
    its order is the oldest: a delivery counts against the oldest open order
    first, and the first deliveries after the switch filled newer orders."""
    items = [dict(_stock_item(3, "Glass|Blue|20|", supplier="Invented Glass Co", on_order=30))]
    export = {"now": "2026-10-22T12:00:00+00:00", "tables": {"audit_log": {"rows": [
        {"id": 1, "at": "2026-10-05T10:00:00+00:00", "user": "someone", "action": "ordered", "item_key": "Glass|Blue|20|",
         "field": "on_order", "old_value": "20", "new_value": "30", "detail": "ordered 10 from Invented Glass Co · ref PO-7"}]}}}
    orders = stock_import.rebuild_orders(export, items, PEOPLE)
    before = [o for o in orders if o["before_move"]]
    rebuilt = [o for o in orders if not o["before_move"]]
    eq((len(before), len(rebuilt)), (1, 1), "the 20 no line accounts for, and the order of 10")
    ok(before[0]["at"] < rebuilt[0]["at"], "ordered before the move is the oldest: %r" % [o["at"] for o in orders])
    export["tables"]["audit_log"]["rows"] = []
    eq(stock_import.rebuild_orders(export, items, PEOPLE)[0]["at"], "2026-10-22T12:00:00+00:00",
       "with no order rebuilt, the export's own time")

@test
def t_the_stock_converter_lists_who_needs_an_account():
    """Reactor asks the owner to match each stock app username to a Reactor
    account before a check: the converter names them, leaving out the app's
    own (system, gizmo, ?)."""
    ef, _pf = _stock_export_files("names")
    r = _stock_tool("--export", ef, "--list-people")
    eq(r.returncode, 0, r.stderr)
    eq(json.loads(r.stdout), {"history": ["someone"], "logins": ["someone"]})

@test
def t_stock_install_puts_the_proven_stores_in_place():
    """--install puts exactly what was proven where the stock sheet reads it,
    setting aside any stock store already there (never deleting it), and
    leaves the moment of going live to Reactor: no live_since."""
    _stock_clean()
    stock_store.write_settings({"meta": {"left": "from a rehearsal"}})
    ef, pf = _stock_export_files("install")
    out = _stock_out("install")
    report = os.path.join(out + "-in", "report.json")
    r = _stock_tool("--export", ef, "--people", pf, "--out", out, "--json-report", report, "--install")
    eq(r.returncode, 0, r.stdout + r.stderr)
    got = json.load(open(report, encoding="utf-8"))
    ok(got["proven"] and got["differences"] == [] and got["counts"]["items"] == 4, got)
    for name in _stock_names_in(out):
        eq(open(os.path.join(SCRATCH, name), "rb").read(), open(os.path.join(out, name), "rb").read(), name + " installed as proven")
    eq(stock_store.load_settings().get("live_since"), None, "not live: Reactor sets that last")
    aside = [d for d in os.listdir(out) if d.startswith("set-aside-")]
    eq(len(aside), 1, "what was there is set aside")
    eq(json.load(open(os.path.join(out, aside[0], "stock_settings.json")))["meta"], {"left": "from a rehearsal"})
    eq(os.stat(stock_store.STOCK_SUPPLIERS_PATH).st_mode & 0o777, 0o600, "a private store stays private")
    _stock_clean()

@test
def t_stock_install_refuses_when_live_or_unproven():
    _stock_clean()
    ef, pf = _stock_export_files("refuse")
    stock_store.write_settings({"meta": {}, "live_since": "2026-10-20T18:00:00+00:00"})
    r = _stock_tool("--export", ef, "--people", pf, "--out", _stock_out("refuse"), "--install")
    eq(r.returncode, 3, r.stdout + r.stderr)
    eq(_stock_names_in(SCRATCH), ["stock_settings.json"], "nothing installed over a live stock sheet")
    _stock_clean()
    export = _stock_export()
    export["expected"]["compute_current"]["headline"]["active_units"] += 1     # a figure the stores will not give
    ef, pf = _stock_export_files("unproven", export=export)
    r = _stock_tool("--export", ef, "--people", pf, "--out", _stock_out("unproven"), "--install")
    eq(r.returncode, 1, r.stdout + r.stderr)
    eq(_stock_names_in(SCRATCH), [], "an unproven move installs nothing")

# ---- moving in from Reactor (Settings, the owner's) -------------------------------
import hashlib as _hashlib
import time as _time

def _move(op, session=None, **body):
    r = post_s(session, "/api/stock/move", dict(body, op=op)) if session else post("/api/stock/move", dict(body, op=op))
    return r, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {})

def _move_fresh():
    """A stock sheet not yet moved in, no move started, nothing queued for the stock app."""
    from gizmo import stock_move, stock_link
    _stock_clean()
    shutil.rmtree(stock_move.move_dir(), ignore_errors=True)
    stock_move._worker = None
    stock_link._write_zeta_pending({})
    stock.forget_memory()

def _move_upload(export=None, parts=3, upload="u1"):
    """The export sent as the page sends it: in parts, with the checksum of the whole."""
    text = json.dumps(export or _stock_export())
    size = max(1, -(-len(text) // parts))
    chunks = [text[i:i + size] for i in range(0, len(text), size)]
    sha = _hashlib.sha256(text.encode("utf-8")).hexdigest()
    for i, part in enumerate(chunks):
        r, d = _move("part", upload=upload, index=i, total=len(chunks), text=part, sha256=sha)
        eq(r.status_code, 200, r.text)
    return text, d

def _move_wait():
    """Status, once the check or move in progress has finished."""
    for _ in range(900):
        r, d = _move("status")
        eq(r.status_code, 200, r.text)
        if (d.get("run") or {}).get("state") != "running":
            return d
        _time.sleep(0.1)
    raise AssertionError("the run never finished")

@test
def t_only_the_owner_moves_the_stock_sheet_in():
    def go():
        _move_fresh()
        ensure_auth()
        for role in ("member", "admin"):
            uid, session, _pw = ready_user("Stock " + role, "stock." + role, role=role)
            r = post("/api/team/user", {"op": "tabs", "id": uid, "tabs": ["stock", "labels"]})
            eq(r.status_code, 200, r.text)
            for op in ("status", "part", "check", "move"):
                r, d = _move(op, session=session)
                eq(r.status_code, 403, op + " by " + role + ": " + r.text)
                eq(d.get("error"), "Only the owner can move the stock sheet in.")
    with_accounts(go)

@test
def t_an_export_arrives_in_parts_and_is_checked_whole_stock():
    _move_fresh()
    ensure_auth()
    text, d = _move_upload()
    up = d["upload"]
    eq((up["bytes"], up["sha256"], up["exported_at"]),
       (len(text.encode("utf-8")), _hashlib.sha256(text.encode("utf-8")).hexdigest(), "2026-10-22T12:00:00+00:00"))
    eq(d["names"], {"history": ["someone"], "logins": ["someone"]}, "the names to match to accounts")
    good = json.dumps(_stock_export())
    sha = _hashlib.sha256(good.encode("utf-8")).hexdigest()
    r, d = _move("part", upload="u2", index=0, total=3, text=good[:10], sha256=sha)
    r, d = _move("part", upload="u2", index=2, total=3, text=good[20:], sha256=sha)
    eq(r.status_code, 409, r.text)
    ok("out of order" in d["error"], d)
    eq(_move("status")[1]["upload"], None, "a broken upload is not kept")
    r, d = _move("part", upload="u3", index=0, total=1, text=good, sha256="0" * 64)
    eq(r.status_code, 400, r.text)
    ok("did not arrive whole" in d["error"], d)
    eq(_move("status")[1]["upload"], None)
    other = json.dumps({"format": "something else"})
    r, d = _move("part", upload="u4", index=0, total=1, text=other,
                 sha256=_hashlib.sha256(other.encode("utf-8")).hexdigest())
    eq(r.status_code, 400, r.text)
    ok("not a stock export" in d["error"], d)
    eq(_move("status")[1]["upload"], None)

@test
def t_a_stock_check_proves_the_export_and_changes_nothing():
    _move_fresh()
    ensure_auth()
    _move_upload()
    r, d = _move("check", people={"someone": APP_AUTH["master"]})
    eq(r.status_code, 200, r.text)
    run = _move_wait()["run"]
    eq((run["kind"], run["state"], run["differences"]), ("check", "passed", []), run)
    eq(run["counts"]["items"], 4)
    eq(_stock_names_in(SCRATCH), [], "nothing where the stock sheet reads")
    ok(not stock.is_live(), "and not live")

@test
def t_moving_in_needs_a_passing_check_of_this_stock_export():
    _move_fresh()
    ensure_auth()
    people = {"someone": APP_AUTH["master"]}
    _move_upload()
    r, d = _move("move", people=people)
    eq(r.status_code, 409, "no check yet: " + r.text)
    r, d = _move("check", people={"someone": "no-such-account"})
    eq(r.status_code, 400, r.text)
    ok("no-such-account" not in d["error"] and "an account that does not exist" in d["error"], d)
    r, d = _move("check", people={})
    eq(r.status_code, 400, r.text)
    ok("someone" in d["error"], "names the stock app name left unmatched: " + d["error"])
    bad = _stock_export()
    bad["expected"]["compute_current"]["headline"]["active_units"] += 1
    _move_upload(export=bad)
    _move("check", people=people)
    eq(_move_wait()["run"]["state"], "failed")
    r, d = _move("move", people=people)
    eq(r.status_code, 409, "a failed check: " + r.text)
    _move_upload()
    r, d = _move("check", people=people)
    eq(r.status_code, 200, r.text)
    r2, d2 = _move("check", people=people)
    eq(r2.status_code, 409, "one run at a time: " + r2.text)
    eq(_move_wait()["run"]["state"], "passed")
    r, d = _move("move", people={"someone": APP_AUTH["master"], "extra": APP_AUTH["master"]})
    eq(r.status_code, 409, "other people than the check's: " + r.text)
    _move_upload(export=_stock_export(low_lines=True))
    r, d = _move("move", people=people)
    eq(r.status_code, 409, "another export than the check's: " + r.text)
    ok("Check this export first" in d["error"], d)
    ok(not stock.is_live())

@test
def t_moving_in_puts_the_stock_sheet_live():
    from gizmo import stock_link
    def go():
        _move_fresh()
        ensure_auth()
        keeper, _s, _p = ready_user("Stock Keeper", "stock.keeper")
        other, _s2, _p2 = ready_user("Not Stock", "not.stock")
        stock_link._write_zeta_pending({"1001": {"op": "book", "at": "2026-10-26T18:00:00+00:00", "by": None,
                                                 "tries": 20, "stuck": True}})
        people = {"someone": keeper}
        _move_upload()
        _move("check", people=people)
        eq(_move_wait()["run"]["state"], "passed")
        r, d = _move("move", people=people)
        eq(r.status_code, 200, r.text)
        d = _move_wait()
        eq(d["run"]["state"], "done", d["run"])
        ok(stock.is_live() and d["live"], "live")
        eq(sorted(stock_store.load_items()["items"]), ["11", "3", "7", "9"], "the export's lines")
        moved = stock_store.load_settings()["moved_in"]
        eq((moved["by"], moved["people"]), (APP_AUTH["master"], people))
        ok("stock" in team._user_tabs(keeper) and "stock" not in team._user_tabs(other), "the Stock tab for who was matched")
        eq(stock_link._load_zeta_pending()["1001"].get("tries"), 0, "a queued booking is tried again, now here")
        ok(not stock_link._load_zeta_pending()["1001"].get("stuck"))
        eq(len([b for b in stock_store.list_backups() if b.get("format") != "legacy-fernet"]), 1, "the first stock backup")
        eq(stock_store.read_history()[-1]["action"], "moved_in")
        r, d = _move("move", people=people)
        eq(r.status_code, 409, r.text)
        eq(d["error"], "The stock sheet has already moved in.")
        _move_fresh()
    with_accounts(go)

@test
def t_an_interrupted_stock_run_says_so_and_can_run_again():
    from gizmo import stock_move
    _move_fresh()
    ensure_auth()
    text, _d = _move_upload()
    people = {"someone": APP_AUTH["master"]}
    stock_move._write_run({"kind": "check", "state": "running", "at": "2026-10-26T18:00:00+00:00",
                           "by": APP_AUTH["master"], "sha256": _hashlib.sha256(text.encode("utf-8")).hexdigest(),
                           "people": people})
    run = _move("status")[1]["run"]
    eq(run["state"], "interrupted", run)
    ok("run it again" in run["words"].lower(), run)
    _move("check", people=people)
    eq(_move_wait()["run"]["state"], "passed")

# ---- the review's fixes (26 Oct 2026) ----------------------------------------------------

@test
def t_a_stock_converter_crash_is_said_not_counted():
    """A converter that crashes on real data is not "0 differences": it says
    it stopped and why, and the move says nothing was moved."""
    from gizmo import stock_move
    broken = {"format": "stock-export-1", "now": "2026-10-22T12:00:00+00:00",
              "tables": {"items": {"columns": ["id"], "count": 1, "rows": [{"id": 1}], "missing": False}}}
    ef, pf = _stock_export_files("crash", export=broken)
    r = _stock_tool("--export", ef, "--people", pf, "--out", _stock_out("crash"))
    eq(r.returncode, 4, r.stdout + r.stderr)
    ok("refused: the converter stopped:" in r.stderr, r.stderr[-300:])
    saved = stock_move._tool
    try:
        stock_move._tool = lambda args, timeout: (1, "", "Traceback (most recent call last):\nKeyError: 'key'")
        run = {"kind": "check", "state": "running", "at": "2026-10-26T18:00:00+00:00", "by": "u", "sha256": "x",
               "people": {}}
        _move_fresh()
        stock_move._execute(run)
    finally:
        stock_move._tool = saved
    eq(run["state"], "stopped", run)
    ok("differences" not in run["words"] and "Nothing was moved" in run["words"], run["words"])

@test
def t_a_finished_stock_run_is_never_called_interrupted():
    """status() asks whether the worker is alive before it reads the run, so a
    run that finishes between the two is never stamped "interrupted"."""
    from gizmo import stock_move
    _move_fresh()
    ensure_auth()
    stock_move._write_run({"kind": "check", "state": "running", "at": "2026-10-26T18:00:00+00:00", "by": "u",
                           "sha256": "x", "people": {}})
    class Finishing:
        def is_alive(self):
            stock_move._write_run({"kind": "check", "state": "passed", "at": "2026-10-26T18:00:00+00:00", "by": "u",
                                   "sha256": "x", "people": {}})
            return False
    stock_move._worker = Finishing()
    eq(stock_move.status(APP_AUTH["master"])["run"]["state"], "passed")
    stock_move._worker = None

def _move_through_install(people):
    """A move that has installed and gone live, its last steps not yet run (as
    if Reactor restarted right after): the state a deploy on the evening can leave."""
    from gizmo import stock_move
    _move_upload()
    _move("check", people=people)
    eq(_move_wait()["run"]["state"], "passed")
    saved = stock_move._finish
    try:
        stock_move._finish = lambda *a, **k: None
        _move("move", people=people)
        stock_move._worker.join(120)
    finally:
        stock_move._finish = saved
    stock_move._worker = None

@test
def t_a_stock_move_finishes_after_a_restart():
    """Live, but stopped before the Stock tab was granted, the queue retried,
    the first backup made and the history line written: the next look at
    where the move stands finishes it, and the window says so."""
    from gizmo import stock_move, stock_link
    def go():
        _move_fresh()
        ensure_auth()
        keeper, _s, _p = ready_user("Stock Keeper", "stock.keeper")
        stock_link._write_zeta_pending({"1001": {"op": "book", "at": "2026-10-26T18:00:00+00:00", "by": None,
                                                 "tries": 20, "stuck": True}})
        _move_through_install({"someone": keeper})
        ok(stock.is_live(), "the stores are in and the sheet is live")
        eq(stock_move._read("run.json")["state"], "finishing")
        ok("stock" not in team._user_tabs(keeper), "not yet granted")
        d = _move("status")[1]
        eq(d["run"]["state"], "done", d["run"])
        ok("stock" in team._user_tabs(keeper), "granted")
        eq(stock_link._load_zeta_pending()["1001"].get("tries"), 0)
        eq(len([b for b in stock_store.list_backups() if b.get("format") != "legacy-fernet"]), 1)
        eq(stock_store.read_history()[-1]["action"], "moved_in")
        eq(sorted(stock_store.load_settings()["moved_in"]["done"]), ["backup", "history", "queue", "tabs"])
        eq(_move("status")[1]["run"]["state"], "done", "and finishing twice changes nothing")
        eq(len([b for b in stock_store.list_backups() if b.get("format") != "legacy-fernet"]), 1)
        _move_fresh()
    with_accounts(go)

@test
def t_a_stock_move_step_that_fails_is_said_and_finished_later():
    from gizmo import stock_move, stock_backups
    _move_fresh()
    ensure_auth()
    _move_through_install({"someone": APP_AUTH["master"]})
    saved = stock_backups.make_backup
    try:
        def no_room(who):
            raise OSError("No space left on device")
        stock_backups.make_backup = no_room
        d = _move("status")[1]
    finally:
        stock_backups.make_backup = saved
    eq(d["run"]["state"], "finishing", d["run"])
    ok("first stock backup" in d["run"]["words"] and "tried again" in d["run"]["words"], d["run"]["words"])
    eq(_move("status")[1]["run"]["state"], "done", "finished on the next look")
    _move_fresh()

@test
def t_a_stock_move_leaves_no_copy_behind():
    """The export and every converted copy are real data: a check leaves no
    copy, and once moved in the export goes too. What was at the live paths
    before is kept, set aside, and the move records where."""
    from gizmo import stock_move
    _move_fresh()
    ensure_auth()
    stock_store.write_settings({"meta": {"left": "from a rehearsal"}})
    people = {"someone": APP_AUTH["master"]}
    _move_upload()
    _move("check", people=people)
    eq(_move_wait()["run"]["state"], "passed")
    eq([n for n in os.listdir(stock_move.move_dir()) if n.startswith("run-")], [], "a check leaves no copy")
    _move("move", people=people)
    eq(_move_wait()["run"]["state"], "done")
    left = sorted(os.listdir(stock_move.move_dir()))
    eq([n for n in left if n.startswith(("run-", "export", "upload"))], [], "the export and the copies are gone: %r" % left)
    aside = stock_store.load_settings()["moved_in"].get("set_aside")
    ok(aside and os.path.isdir(aside) and os.path.dirname(aside) == stock_move.move_dir(), "what was there is kept: %r" % aside)
    eq(json.load(open(os.path.join(aside, "stock_settings.json")))["meta"], {"left": "from a rehearsal"})
    _move_fresh()
