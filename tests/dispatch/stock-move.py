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
