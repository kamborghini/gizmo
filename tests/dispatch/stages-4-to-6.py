# ---- The floor (stage 4, piece 2) -----------------------------------------
# The store, the error log and the AI client sit beneath every area: they
# import nothing from copilot.py, so an area can import them directly.

FLOOR = ["gizmo/config.py", "gizmo/store.py", "gizmo/errors.py", "gizmo/ai.py", "gizmo/shopify.py", "gizmo/prompts.py", "gizmo/clock.py", "gizmo/bodies.py", "gizmo/background.py"]

@test
def t_no_module_looks_itself_up_by_name():
    """A function that finds its module's names through globals() (or vars(),
    or sys.modules[__name__]) changes meaning when it moves: it would read or
    clear the new module's names, and neither the move script nor the proof
    can see it. copilot.py's _drop_memory_stores is the one such function, and
    it stays there."""
    import ast as _ast
    from tools import sources
    bad = []
    for rel in sources.COPILOT_FILES[1:]:
        for x in _ast.walk(_ast.parse(open(os.path.join(sources.ROOT, rel), encoding="utf-8").read())):
            if (isinstance(x, _ast.Call) and isinstance(x.func, _ast.Name)
                    and (x.func.id == "globals" or (x.func.id == "vars" and not x.args))):
                bad.append(f"{rel}:{x.lineno} {x.func.id}()")
            elif isinstance(x, _ast.Subscript) and _ast.unparse(x) == "sys.modules[__name__]":
                bad.append(f"{rel}:{x.lineno} sys.modules[__name__]")
    eq(bad, [], "a module moved out of copilot.py looks its own names up by name")

@test
def t_the_floor_imports_nothing_above_it():
    """The floor never reaches copilot.py, server.py or an area, directly or
    through a module it imports, wherever in it the import is written."""
    import ast as _ast
    from tools import sources
    mods = _app_module_files()
    for rel in FLOOR:
        ok(os.path.exists(os.path.join(sources.ROOT, rel)), rel + " exists")
    floor = {f[:-3].replace("/", ".") for f in FLOOR}
    above = {"copilot", "server"} | {m for m in mods if m.startswith("gizmo.") and m not in floor | {"gizmo.__init__"}}
    def reached(mod):
        tree = _ast.parse(open(os.path.join(sources.ROOT, mods[mod]), encoding="utf-8").read())
        out = set()
        for x in _ast.walk(tree):
            if isinstance(x, _ast.Import):
                out |= {a.name for a in x.names}
            elif isinstance(x, _ast.ImportFrom) and x.module and not x.level:
                out |= {x.module + "." + a.name for a in x.names} | {x.module}
        return {m for m in out if m in mods}
    bad = []
    for start in sorted(floor):
        seen, todo = set(), [(start, start)]
        while todo:
            mod, path = todo.pop()
            if mod in seen:
                continue
            seen.add(mod)
            for nxt in reached(mod):
                if nxt in above:
                    bad.append(path + " -> " + nxt)
                todo.append((nxt, path + " -> " + nxt))
    eq(sorted(set(bad)), [], "the floor reaches above itself")

@test
def t_forgetting_the_crm_store_drops_its_board():
    """The store no longer names the CRM. The CRM registers a hook, called with
    the path whenever a store's cached copy is forgotten, and it drops the
    kept board when the path is the CRM's, read when called: a path set after
    start-up still counts."""
    from gizmo import store as _store
    saved = salesdesk.CRM_PATH
    try:
        salesdesk.CRM_PATH = os.path.join(SCRATCH, "crm-elsewhere.json")
        salesdesk._crm_board_cache.update(key="k", raw=b"x", rev="r")
        _store._forget_store(os.path.join(SCRATCH, "not-the-crm.json"))
        eq(salesdesk._crm_board_cache["raw"], b"x", "another store forgotten keeps the board")
        _store._forget_store(salesdesk.CRM_PATH)
        eq(salesdesk._crm_board_cache["raw"], None, "the CRM's store forgotten drops it")
    finally:
        salesdesk.CRM_PATH = saved
        salesdesk._crm_board_forget()

@test
def t_a_banners_closing_rule_opens_no_section():
    """The settings reference files each setting under the banner above it. A
    banner's closing rule followed by an ordinary comment is not a new banner:
    once the setting that followed the Configuration banner moved out, the
    next comment became a heading of its own."""
    import importlib.util
    from tools import sources
    spec = importlib.util.spec_from_file_location("env_reference", os.path.join(sources.ROOT, "tools", "env_reference.py"))
    env = importlib.util.module_from_spec(spec); spec.loader.exec_module(env)
    rule = "# " + "-" * 40
    lines = [rule, "# Configuration", rule, "# Effort, and why it is high.", "X = 1",
             "", rule, "# Shipping, settings", "# and state.", rule, "Y = 2"]
    eq([t for _, t in env._banner_index(lines)], ["Configuration", "Shipping, settings"], "two banners, two titles")

@test
def t_the_team_routes_register_in_place():
    """The sign-in and team routes are registered by one call in add_routes;
    none is left behind."""
    import inspect
    from gizmo.routes import team as routes_team
    src = inspect.getsource(copilot.add_routes)
    # Where it stands is make move-proof's to check (its neighbours have since
    # moved out too); here, that it is there once.
    eq(src.count("routes_team.register(mcp, registry)"), 1, "one call")
    for path in ('"/api/auth/', '"/api/team/'):
        ok(path not in src, path + " is registered by the team's own routes")
    eq(inspect.getsource(routes_team).count("@mcp.custom_route("), 10, "the 10 sign-in and team routes")

@test
def t_the_printed_labels_do_not_change():
    """Production labels never change by accident: what the bench prints for
    the suite's order, the label data and the document the printer gets at
    each stock size, is pinned to its bytes as they were before the orders and
    production code left copilot.py (20 Oct 2026). The size is applied when it
    prints, so both sizes give one document. A change to a label on purpose
    re-pins these with the reason."""
    import hashlib, json as _json
    h = lambda b: hashlib.sha256(b.encode("utf-8")).hexdigest()[:16]
    def go():
        ensure_auth()
        data = run(production.run_production_labels({}, order_id=12345))
        eq(h(_json.dumps(data, sort_keys=True, indent=1, default=str)), "52682bb6d8726c1a", "the label data is unchanged")
        for size in ("4x6", "4x4"):
            r = client.post("/print/production-labels/sign", json={"ids": "12345", "size": size},
                            headers={"Authorization": "Bearer " + tok()})
            eq(r.status_code, 200, r.text[:200])
            eq(h(client.get(r.json()["path"]).text), "9c58d003359d2683", "the printed document is unchanged at " + size)
    with_accounts(go)

@test
def t_the_size_lists_seed_files_are_the_repos():
    """The Size list's seed rules default to the repository's data folder,
    found from the module's own file. Moved into gizmo/, a path built from
    __file__ would quietly look in gizmo/data instead, and the suite, which
    sets every path, would never notice: so the defaults are read here with
    the settings cleared."""
    import subprocess as _sp
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {k: v for k, v in os.environ.items() if not k.startswith("GOBO_")}
    r = _sp.run([sys.executable, "-c", "import os, copilot\nfrom gizmo import size_list as s\n"
                 "print(os.path.abspath(s.GOBO_SIZES_PATH)); print(os.path.abspath(s.GOBO_ALIASES_PATH)); "
                 "print(os.path.abspath(s.GOBO_OVERRIDES_PATH))"],
                cwd=root, env=env, capture_output=True, text=True, timeout=120)
    eq(r.returncode, 0, r.stderr[-400:])
    eq(r.stdout.split(), [os.path.join(root, "data", f) for f in ("gobo-sizes.csv", "gobo-aliases.csv", "gobo-overrides.csv")],
       "the seeds are the repository's")
    ok(all(os.path.exists(p) for p in r.stdout.split()), "and they exist")

@test
def t_the_crm_and_mail_routes_are_gathered():
    """The CRM's and the inbox's routes, scattered through add_routes, are each
    registered by one call where the area's first route stood. No request
    changes hands: only /dav{sub_path:path} has a pattern, and no two routes
    share a path (make move-proof checks the order)."""
    import inspect
    from gizmo.routes import crm as routes_crm, mail as routes_mail
    src = inspect.getsource(copilot.add_routes)
    eq((src.count("routes_crm.register(mcp, registry)"), src.count("routes_mail.register(mcp, registry)")), (1, 1),
       "one call each")
    for path in ('"/api/crm/', '"/api/mail/', '"/oauth/gmail/'):
        ok(path not in src, path + " is registered by the area's own routes")
    eq((inspect.getsource(routes_crm).count("@mcp.custom_route("), inspect.getsource(routes_mail).count("@mcp.custom_route(")),
       (8, 26), "8 CRM routes; 24 mail routes and the Gmail connect pair")

_TOY_MAIN = "copilot" + ".py"     # a made-up repository's main file, not ours
_TOY_COPILOT = '''"""A made-up app for the move tool's test."""
import logging
import os
from typing import Optional
from gizmo import floor_stub

logger = logging.getLogger("toy")

KEEP = 1
X_PATH = os.environ.get("X_PATH", "/data/x.json")

_x_mem: Optional[dict] = None


def _x_load(path: str = "") -> dict:
    return {"path": path or X_PATH}


def keep() -> dict:
    return _x_load()


def reset() -> None:
    global _x_mem
    _x_mem = None


def _x_note(d: Optional[dict]) -> int:
    return KEEP + len(d or {})


def add_routes(mcp, registry):
    @mcp.custom_route("/api/x/a", methods=["POST"])
    async def x_a(request):
        return _x_load()

    @mcp.custom_route("/api/y", methods=["POST"])
    async def y(request):
        return keep()

    @mcp.custom_route("/api/x/b", methods=["POST"])
    async def x_b(request):
        return _x_note(None)
'''

_TOY_TEST = '''import copilot
from gizmo import floor_stub

EXAMPLE = """
from gizmo import nothing_real
"""


def t_patch():
    copilot._x_load = lambda: {}
    assert callable(getattr(copilot, "_x_load", None))
'''

_TOY_SPEC = {"areas": [{"name": "x", "file": "gizmo/x.py", "alias": "x", "prefix": "^(_x_|X_)",
                        "extra": [], "exclude": [], "floor": False, "doc": "The x area."}],
             "routes": [{"name": "routes_x", "file": "gizmo/routes/x.py", "area": "x", "paths": ["/api/x/"],
                         "helpers": [], "doc": "The x routes.", "register_doc": "Add the x routes."}],
             "note": "the x area"}


def _toy_repo(name, copilot_text=_TOY_COPILOT, spec=None, extra=None):
    """A made-up repository in the scratch folder: copilot.py, a gizmo
    package, one test, and a move description."""
    import json as _json
    root = os.path.join(SCRATCH, name)
    _sh.rmtree(root, ignore_errors=True)
    for d in ("gizmo/routes", "tests", "tools/moves"):
        os.makedirs(os.path.join(root, d), exist_ok=True)
    files = {_TOY_MAIN: copilot_text, "gizmo/__init__.py": "", "gizmo/routes/__init__.py": "",
             "gizmo/floor_stub.py": '"""Stands in for the floor."""\n', "tests/test_dispatch.py": _TOY_TEST,
             "server.py": "def boot():\n    import copilot\n    return copilot._x_load()\n"}
    files.update(extra or {})
    for rel, text in files.items():
        open(os.path.join(root, rel), "w").write(text)
    open(os.path.join(root, "tools/moves/x.json"), "w").write(_json.dumps(spec or _TOY_SPEC))
    return root


def _run_move(root, write=True):
    import subprocess as _sp
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return _sp.run([sys.executable, os.path.join(here, "tools", "move_area.py"), os.path.join(root, "tools/moves/x.json"),
                    "--repo", root] + (["--write"] if write else []), capture_output=True, text=True, timeout=120)


@test
def t_move_area_moves_a_toy_area():
    """tools/move_area.py, the committed move tool, run on a made-up
    repository: what it writes is nothing but the move (prove() agrees), with
    every lesson of the first five moves built in."""
    import importlib.util, subprocess as _sp
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec_ = importlib.util.spec_from_file_location("move_proof", os.path.join(here, "tools", "move_proof.py"))
    mp = importlib.util.module_from_spec(spec_); spec_.loader.exec_module(mp)
    root = _toy_repo("toy-move")
    r = _run_move(root)
    eq(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
    read = lambda rel: open(os.path.join(root, rel)).read()
    area, cop, routes, test_ = read("gizmo/x.py"), read(_TOY_MAIN), read("gizmo/routes/x.py"), read("tests/test_dispatch.py")
    ok("def _x_load(" in area and "X_PATH = " in area and "_x_mem: Optional[dict] = None" in area, "the area's names moved")
    ok("from typing import Optional" in area, "with the import an annotation needs")
    ok("core.KEEP" in area and area.rstrip().endswith("import copilot as core  # noqa: E402"), "borrowing through core, imported last")
    ok("return x._x_load()" in cop, "copilot reads the area through its name")
    ok("global _x_mem" not in cop and "x._x_mem = None" in cop, "a global line for a moved name goes; the write goes through the module")
    eq(cop.count("routes_x.register(mcp, registry)"), 1, "the routes are gathered")
    ok(cop.index("routes_x.register(mcp, registry)") < cop.index('"/api/y"'), "where the first stood")
    eq(routes.count("@mcp.custom_route("), 2, "both of the area's routes")
    ok("x._x_load = lambda" in test_, "the test patches the area")
    ok('getattr(x, "_x_load", None)' in test_, "and a getattr by the name's string follows it too")
    ok("from gizmo import floor_stub\nfrom gizmo import x\n" in test_ and '"""\nfrom gizmo import nothing_real\n"""' in test_,
       "the suite's prelude imports the area after its own imports, not inside a string")
    ok("return copilot.x._x_load()" in read("server.py"),
       "server.py, which imports copilot inside its functions, reaches the area through copilot's name for it")
    base = {_TOY_MAIN: _TOY_COPILOT, "gizmo/__init__.py": "", "gizmo/floor_stub.py": '"""Stands in for the floor."""\n',
            "gizmo/routes/__init__.py": ""}
    head = {_TOY_MAIN: cop, "gizmo/__init__.py": "", "gizmo/floor_stub.py": '"""Stands in for the floor."""\n',
            "gizmo/routes/__init__.py": "", "gizmo/routes/x.py": routes, "gizmo/x.py": area}
    eq(mp.prove(base, head, declared=("reset",)), [], "prove(): nothing but the move")
    for first in ("gizmo.x", "copilot", "gizmo.routes.x"):
        rr = _sp.run([sys.executable, "-c", f"import {first}, copilot, gizmo.x"], cwd=root, capture_output=True, text=True)
        eq(rr.returncode, 0, f"{first} first: " + rr.stderr[-400:])
    # an alias that is a local where it would be read: nothing written
    clash = _toy_repo("toy-clash", _TOY_COPILOT + "\n\ndef clash():\n    x = 1\n    return x + len(_x_load())\n")
    r = _run_move(clash)
    ok(r.returncode != 0 and "local" in r.stdout, "a local named like the alias stops the move: " + r.stdout[-300:])
    ok(not os.path.exists(os.path.join(clash, "gizmo/x.py")), "and nothing is written")
    # a statement binding two areas' names: nothing written
    two = dict(_TOY_SPEC, areas=_TOY_SPEC["areas"] + [{"name": "y", "file": "gizmo/y.py", "alias": "yy", "prefix": "^KEEP$",
                                                       "extra": [], "exclude": [], "floor": False, "doc": "y"}])
    both = _toy_repo("toy-two", _TOY_COPILOT.replace("KEEP = 1\nX_PATH =", "KEEP, X_PATH = 1, "), two)
    r = _run_move(both)
    ok(r.returncode != 0 and "across" in r.stdout, "a statement binding two areas' names stops the move: " + r.stdout[-300:])
    # a name that stays though only what moves reads it: the dry run names it
    left = _toy_repo("toy-left", _TOY_COPILOT.replace(
        "def _x_note(d: Optional[dict]) -> int:\n    return KEEP + len(d or {})",
        "def _deeper() -> int:\n    return 2\n\n\ndef _shared() -> int:\n    return _deeper()\n\n\n"
        "def _x_note(d: Optional[dict]) -> int:\n    return KEEP + _shared() + len(d or {})"))
    r = _run_move(left, write=False)
    eq(r.returncode, 0, r.stdout[-500:] + r.stderr[-500:])
    named = [l for l in r.stdout.splitlines() if "only what moves reads it" in l]
    ok(any(l.startswith("note: _shared stays") for l in named), "a helper left behind for the area is named: " + r.stdout[-500:])
    ok(any(l.startswith("note: _deeper stays") for l in named), "and one only that helper reads: " + r.stdout[-500:])
    ok(not any(l.startswith("note: keep stays") for l in named), "a name staying code reads is not: " + r.stdout[-500:])
    # a moving statement that reads an earlier area as the module loads (a
    # default value): that area is imported at the top, and any module may go first
    old = '"""An earlier area."""\n\nLIMIT = 3\n\n\nimport copilot as core  # noqa: E402\n'
    early = _toy_repo("toy-early", _TOY_COPILOT.replace("from gizmo import floor_stub\n", "from gizmo import floor_stub\nfrom gizmo import old\n", 1)
                      + "\n\ndef _x_cap(n: int = old.LIMIT) -> int:\n    return n\n", extra={"gizmo/old.py": old})
    r = _run_move(early)
    eq(r.returncode, 0, r.stdout[-600:] + r.stderr[-600:])
    area = open(os.path.join(early, "gizmo/x.py")).read()
    ok(area.index("from gizmo import old") < area.index("def _x_cap("),
       "the earlier area is imported above the statement that reads it as the module loads: " + area[-300:])
    for first in ("gizmo.x", "copilot", "gizmo.old"):
        rr = _sp.run([sys.executable, "-c", f"import {first}, copilot, gizmo.x as m; assert m._x_cap() == 3"],
                     cwd=early, capture_output=True, text=True)
        eq(rr.returncode, 0, f"{first} first: " + rr.stderr[-400:])

    # "=/" names the page's own route alone: every path starts with "/"
    page = _TOY_COPILOT.replace("def add_routes(mcp, registry):\n",
                                "def add_routes(mcp, registry):\n    @mcp.custom_route(\"/\", methods=[\"GET\"])\n"
                                "    async def index(request):\n        return _x_load()\n\n")
    exact = _toy_repo("toy-exact", page, dict(_TOY_SPEC, routes=[dict(_TOY_SPEC["routes"][0], paths=["=/", "/api/x/"])]))
    r = _run_move(exact)
    eq(r.returncode, 0, r.stdout[-600:] + r.stderr[-600:])
    routes, cop = (open(os.path.join(exact, f)).read() for f in ("gizmo/routes/x.py", _TOY_MAIN))
    eq(routes.count("@mcp.custom_route("), 3, "the page's own route and the area's two: " + routes[-400:])
    ok('"/api/y"' in cop and '"/"' not in cop, "the rest stay where they are")

@test
def t_the_files_routes_are_gathered():
    """The Files routes and the Finder drive's, scattered through add_routes,
    are registered by one call where the first stood. The drive's route is
    the one with a pattern, and no other path starts with /dav, so no request
    changes hands (make move-proof checks the order)."""
    import inspect
    from gizmo.routes import files as routes_files
    src = inspect.getsource(copilot.add_routes)
    eq(src.count("routes_files.register(mcp, registry)"), 1, "one call")
    for path in ('"/api/files/', '"/dav'):
        ok(path not in src, path + " is registered by the Files routes")
    eq(inspect.getsource(routes_files).count("@mcp.custom_route("), 8, "the 7 Files routes and the drive's")

@test
def t_move_area_moves_routes_after_their_area():
    """A route group whose area moved in an earlier piece: its routes follow,
    gathered where the first stood, still reaching the area through its name."""
    import importlib.util, subprocess as _sp
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec_ = importlib.util.spec_from_file_location("move_proof", os.path.join(here, "tools", "move_proof.py"))
    mp = importlib.util.module_from_spec(spec_); spec_.loader.exec_module(mp)
    old = '"""An area moved in an earlier piece."""\n\n\ndef f():\n    return core.KEEP\n\n\nimport copilot as core  # noqa: E402\n'
    cop = _TOY_COPILOT.replace("from gizmo import floor_stub\n", "from gizmo import floor_stub\nfrom gizmo import old\n") + (
        '\n    @mcp.custom_route("/api/old/c", methods=["POST"])\n    async def old_c(request):\n        return old.f() + KEEP\n')
    spec = {"note": "the old area's routes", "areas": [],
            "routes": [{"name": "routes_old", "file": "gizmo/routes/old.py", "area": "old", "paths": ["/api/old/"],
                        "helpers": [], "doc": "The old area's routes.", "register_doc": "Add them."}]}
    root = _toy_repo("toy-routes", cop, spec, {"gizmo/old.py": old})
    r = _run_move(root)
    eq(r.returncode, 0, r.stdout[-600:] + r.stderr[-600:])
    read = lambda rel: open(os.path.join(root, rel)).read()
    routes, head_cop = read("gizmo/routes/old.py"), read(_TOY_MAIN)
    ok("return old.f() + core.KEEP" in routes and "from gizmo import old" in routes,
       "the route reaches the area through its name, and copilot.py through core")
    eq(head_cop.count("routes_old.register(mcp, registry)"), 1, "gathered into one call")
    ok('"/api/old/c"' not in head_cop, "and gone from add_routes")
    base = {_TOY_MAIN: cop, "gizmo/__init__.py": "", "gizmo/floor_stub.py": '"""Stands in for the floor."""\n',
            "gizmo/old.py": old, "gizmo/routes/__init__.py": ""}
    head = dict(base, **{_TOY_MAIN: head_cop, "gizmo/routes/old.py": routes})
    eq(mp.prove(base, head), [], "prove(): nothing but the move")
    rr = _sp.run([sys.executable, "-c", "import gizmo.routes.old, copilot"], cwd=root, capture_output=True, text=True)
    eq(rr.returncode, 0, rr.stderr[-400:])
    # a route module moved earlier takes a route left behind: added to its
    # register(), after the routes it holds, and add_routes gains no call
    held = ('"""The routes of the old area."""\nimport logging\n\nimport copilot as core\nfrom gizmo import old\n\n'
            'logger = logging.getLogger("toy")\n\n\ndef register(mcp, registry):\n    """Add them."""\n\n'
            '    @mcp.custom_route("/api/old/a", methods=["POST"])\n    async def old_a(request):\n        return old.f()\n')
    cop2 = cop.replace("from gizmo import old\n", "from gizmo import old\nfrom gizmo.routes import old as routes_old\n", 1) \
              .replace("def add_routes(mcp, registry):\n", "def add_routes(mcp, registry):\n    routes_old.register(mcp, registry)\n\n", 1)
    spec2 = dict(spec, routes=[dict(spec["routes"][0], existing=True)])
    root2 = _toy_repo("toy-routes-existing", cop2, spec2, {"gizmo/old.py": old, "gizmo/routes/old.py": held})
    r = _run_move(root2)
    eq(r.returncode, 0, r.stdout[-600:] + r.stderr[-600:])
    routes2, cop2_after = (open(os.path.join(root2, f)).read() for f in ("gizmo/routes/old.py", _TOY_MAIN))
    eq(routes2.count("@mcp.custom_route("), 2, "the module holds both routes: " + routes2[-400:])
    ok(routes2.index('"/api/old/a"') < routes2.index('"/api/old/c"') and "return old.f() + core.KEEP" in routes2,
       "the added one after the one it held, reaching the area by its name and copilot.py through core")
    ok('"/api/old/c"' not in cop2_after and cop2_after.count("routes_old.register(mcp, registry)") == 1,
       "gone from add_routes, which keeps its one call")
    base2 = dict(base, **{_TOY_MAIN: cop2, "gizmo/routes/old.py": held})
    eq(mp.prove(base2, dict(base2, **{_TOY_MAIN: cop2_after, "gizmo/routes/old.py": routes2})), [], "prove(): nothing but the move")
    rr = _sp.run([sys.executable, "-c", "import gizmo.routes.old, copilot"], cwd=root2, capture_output=True, text=True)
    eq(rr.returncode, 0, rr.stderr[-400:])
    # a route reading a value add_routes builds as it runs: moved, it would
    # fail only when a request came in, so nothing is written
    built = cop.replace("def add_routes(mcp, registry):\n", "def add_routes(mcp, registry):\n    built = dict(registry)\n") \
               .replace("return old.f() + KEEP", "return old.f() + len(built)")
    root2 = _toy_repo("toy-built", built, spec, {"gizmo/old.py": old})
    r = _run_move(root2)
    ok(r.returncode != 0 and "reads add_routes' built" in r.stdout, "a route reading add_routes' own value stops the move: " + r.stdout[-300:])
    ok(not os.path.exists(os.path.join(root2, "gizmo/routes/old.py")), "and nothing is written")

@test
def t_move_area_adds_to_an_area_moved_earlier():
    """An area that moved in an earlier piece takes the names left behind for
    it: they go in before its last imports, read their new module's names
    bare, and the module's own core.NAME reads of them become bare too. A
    floor module takes a helper the same way and still imports nothing above
    it."""
    import importlib.util, subprocess as _sp
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec_ = importlib.util.spec_from_file_location("move_proof", os.path.join(here, "tools", "move_proof.py"))
    mp = importlib.util.module_from_spec(spec_); spec_.loader.exec_module(mp)
    old = ('"""An area moved in an earlier piece."""\nimport logging\n\nlogger = logging.getLogger("toy")\n\n\n'
           'def f():\n    return 1\n\n\ndef g():\n    return core._x_helper() + 1\n\n\n'
           '# Last, so this module is whole before copilot.py runs.\nimport copilot as core  # noqa: E402\n')
    floor = '"""Stands in for the floor."""\n\n\ndef base() -> int:\n    return 0\n'
    cop = _TOY_COPILOT.replace("from gizmo import floor_stub\n", "from gizmo import floor_stub\nfrom gizmo import old\n", 1) + (
        "\n\ndef _x_helper() -> int:\n    return old.f() + KEEP\n\n\n"
        "def _x_ok(d) -> bool:\n    return isinstance(d, dict)\n\n\n"
        "def uses() -> int:\n    return _x_helper() + int(_x_ok({}))\n")
    spec = {"note": "the leftovers home", "routes": [], "areas": [
        {"name": "old", "file": "gizmo/old.py", "alias": "old", "existing": True, "prefix": "^$",
         "extra": ["_x_helper"], "exclude": [], "floor": False, "doc": ""},
        {"name": "floor_stub", "file": "gizmo/floor_stub.py", "alias": "floor_stub", "existing": True, "prefix": "^$",
         "extra": ["_x_ok"], "exclude": [], "floor": True, "doc": ""}]}
    root = _toy_repo("toy-existing", cop, spec, {"gizmo/old.py": old, "gizmo/floor_stub.py": floor})
    r = _run_move(root)
    eq(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
    read = lambda rel: open(os.path.join(root, rel)).read()
    o, fl, c = read("gizmo/old.py"), read("gizmo/floor_stub.py"), read(_TOY_MAIN)
    ok("def _x_helper() -> int:\n    return f() + core.KEEP" in o, "the helper reads its new module bare, copilot.py through core: " + o[-500:])
    ok(o.index("def _x_helper(") < o.index("import copilot as core"), "before the module's last imports")
    ok("return _x_helper() + 1" in o and "core._x_helper" not in o, "the module's own reads of it are bare")
    ok("def _x_ok(d) -> bool:" in fl and "import copilot" not in fl, "the floor takes its helper and imports nothing above it")
    ok("return old._x_helper() + int(floor_stub._x_ok({}))" in c, "copilot.py reads both through their modules: " + c[-300:])
    eq((c.count("from gizmo import old\n"), c.count("from gizmo import floor_stub\n")), (1, 1), "and binds each module once")
    base = {_TOY_MAIN: cop, "gizmo/__init__.py": "", "gizmo/floor_stub.py": floor, "gizmo/old.py": old, "gizmo/routes/__init__.py": ""}
    head = dict(base, **{_TOY_MAIN: c, "gizmo/floor_stub.py": fl, "gizmo/old.py": o})
    eq(mp.prove(base, head), [], "prove(): nothing but the move")
    for first in ("gizmo.old", "copilot", "gizmo.floor_stub"):
        rr = _sp.run([sys.executable, "-c", f"import {first}, copilot; assert copilot.uses() == 3"], cwd=root, capture_output=True, text=True)
        eq(rr.returncode, 0, f"{first} first: " + rr.stderr[-400:])
    # a floor module copilot.py takes a name from but does not bind by its own
    # name: taking a setting into it binds it, in copilot.py and the suite
    cfg = '"""Stands in for the settings."""\n\n\ndef helper() -> int:\n    return 1\n'
    cop3 = _TOY_COPILOT.replace("from gizmo import floor_stub\n", "from gizmo import floor_stub\nfrom gizmo.cfg import helper\n", 1) + (
        "\n\nSETTING = 3\n\n\ndef reads() -> int:\n    return SETTING + helper()\n")
    spec3 = {"note": "a setting to the floor", "routes": [], "areas": [
        {"name": "cfg", "file": "gizmo/cfg.py", "alias": "cfg", "existing": True, "prefix": "^$",
         "extra": ["SETTING"], "exclude": [], "floor": True, "doc": ""}]}
    root3 = _toy_repo("toy-bind", cop3, spec3, {"gizmo/cfg.py": cfg,
                      "tests/test_dispatch.py": _TOY_TEST + "\n\ndef t_setting():\n    assert copilot.SETTING == 3\n"})
    r = _run_move(root3)
    eq(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
    c3, cf3, t3 = (open(os.path.join(root3, f)).read() for f in (_TOY_MAIN, "gizmo/cfg.py", "tests/test_dispatch.py"))
    ok("from gizmo import cfg\n" in c3 and "return cfg.SETTING + helper()" in c3, "copilot.py binds the module and reads it: " + c3[-300:])
    ok("SETTING = 3" in cf3 and "import copilot" not in cf3, "the floor holds the setting and imports nothing above it")
    ok("from gizmo import cfg" in t3 and "assert cfg.SETTING == 3" in t3, "and the suite, which reads it, binds it too")
    rr = _sp.run([sys.executable, "-c", "import gizmo.cfg, copilot; assert copilot.reads() == 4"], cwd=root3, capture_output=True, text=True)
    eq(rr.returncode, 0, rr.stderr[-400:])
    # a name copilot.py keeps as a copy (a frozen function reads it bare): it
    # stays bare there, and every other module reads it from its new home
    cop4 = cop3 + "\n\nOTHER = 5\n\n\ndef keeps() -> int:\n    return OTHER\n"
    user = '"""Reads the other setting."""\n\n\ndef f():\n    return core.OTHER\n\n\nimport copilot as core  # noqa: E402\n'
    spec4 = dict(spec3, areas=[dict(spec3["areas"][0], extra=["SETTING", "OTHER"])], copies=["OTHER"])
    root4 = _toy_repo("toy-copy", cop4, spec4, {"gizmo/cfg.py": cfg, "gizmo/user.py": user})
    r = _run_move(root4)
    eq(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
    c4, u4 = (open(os.path.join(root4, f)).read() for f in (_TOY_MAIN, "gizmo/user.py"))
    ok("from gizmo.cfg import OTHER" in c4 and "    return OTHER\n" in c4, "copilot.py keeps reading the copy bare: " + c4[-300:])
    ok("return cfg.OTHER" in u4 and "from gizmo import cfg" in u4, "another module reads it from its home: " + u4)
    rr = _sp.run([sys.executable, "-c", "import gizmo.user, copilot; assert copilot.keeps() == 5 and gizmo.user.f() == 5"],
                 cwd=root4, capture_output=True, text=True)
    eq(rr.returncode, 0, rr.stderr[-400:])

@test
def t_the_privacy_loans_and_work_routes_are_gathered():
    """The privacy route and Shopify's privacy webhook, the loan register's and
    the work sessions' routes, each registered by one call in add_routes."""
    import inspect
    from gizmo.routes import loans as routes_loans, privacy as routes_privacy, work as routes_work
    src = inspect.getsource(copilot.add_routes)
    for call in ("routes_privacy.register(mcp, registry)", "routes_loans.register(mcp, registry)",
                 "routes_work.register(mcp, registry)"):
        eq(src.count(call), 1, call)
    for path in ('"/api/privacy', '"/webhooks/privacy', '"/api/loans', '"/api/work'):
        ok(path not in src, path + " is registered by its area's routes")
    eq([inspect.getsource(m).count("@mcp.custom_route(") for m in (routes_privacy, routes_loans, routes_work)],
       [2, 1, 5], "2 privacy routes, 1 loans route, 5 work routes")

@test
def t_the_workspace_routes_are_gathered():
    """The skills', memory's and store knowledge's routes, each registered by
    one call in add_routes. The chat's two routes stay: they read the tool
    list add_routes builds from the registry it is handed."""
    import inspect
    from gizmo.routes import knowledge as routes_knowledge, memory as routes_memory, skills as routes_skills
    src = inspect.getsource(copilot.add_routes)
    for call in ("routes_skills.register(mcp, registry)", "routes_memory.register(mcp, registry)",
                 "routes_knowledge.register(mcp, registry)"):
        eq(src.count(call), 1, call)
    for path in ('"/api/skills', '"/api/memory', '"/api/learn'):
        ok(path not in src, path + " is registered by its area's routes")
    eq([inspect.getsource(m).count("@mcp.custom_route(") for m in (routes_skills, routes_memory, routes_knowledge)],
       [2, 1, 2], "2 skills routes, 1 memory route, 2 learn routes")
    ok('"/api/chat' not in src, "the chat routes went too, once add_routes handed the chat module its tools (piece 15)")

@test
def t_the_scheduler_updates_and_backup_routes_are_gathered():
    """The scheduler's, the release notes', impact's and the backup's routes,
    each group registered by one call in add_routes."""
    import inspect
    from gizmo.routes import backup as routes_backup, impact as routes_impact
    from gizmo.routes import scheduler as routes_scheduler, updates as routes_updates
    src = inspect.getsource(copilot.add_routes)
    for call in ("routes_scheduler.register(mcp, registry)", "routes_updates.register(mcp, registry)",
                 "routes_impact.register(mcp, registry)", "routes_backup.register(mcp, registry)"):
        eq(src.count(call), 1, call)
    for path in ('"/api/alerts"', '"/api/updates"', '"/api/impact"', '"/api/backup"', '"/api/restore"'):
        ok(path not in src, path + " is registered by its area's routes")
    eq([inspect.getsource(m).count("@mcp.custom_route(") for m in (routes_scheduler, routes_updates, routes_impact, routes_backup)],
       [1, 1, 1, 2], "the alerts route, the updates route, the impact route, backup and restore")

@test
def t_the_finance_routes_are_gathered():
    """Liability's, the Xero sync settings' and the forecast hooks' routes,
    each group registered by one call in add_routes (Reconciliation's went
    on 22 Oct 2026)."""
    import inspect
    from gizmo.routes import forecasting as routes_forecasting, liability as routes_liability
    from gizmo.routes import xero_sync as routes_xero_sync
    src = inspect.getsource(copilot.add_routes)
    for call in ("routes_liability.register(mcp, registry)",
                 "routes_xero_sync.register(mcp, registry)", "routes_forecasting.register(mcp, registry)"):
        eq(src.count(call), 1, call)
    for path in ('"/api/liability', '"/api/connector"', '"/hooks/forecast/', '"/api/forecast'):
        ok(path not in src, path + " is registered by its area's routes")
    eq([inspect.getsource(m).count("@mcp.custom_route(")
        for m in (routes_liability, routes_xero_sync, routes_forecasting)], [2, 1, 6],
       "2 liability routes, the connector route, 6 forecast routes")

@test
def t_the_page_profile_oauth_and_status_routes_are_gathered():
    """The page's own route and its assets, the profile's, the layouts' and
    the status page's routes, each group registered by one call in
    add_routes (the sign-in walks' went on 22 Oct 2026)."""
    import inspect
    from gizmo.routes import layouts as routes_layouts, profile as routes_profile
    from gizmo.routes import rendering as routes_rendering, status as routes_status
    src = inspect.getsource(copilot.add_routes)
    for call in ("routes_rendering.register(mcp, registry)", "routes_profile.register(mcp, registry)",
                 "routes_layouts.register(mcp, registry)", "routes_status.register(mcp, registry)"):
        eq(src.count(call), 1, call)
    for path in ('custom_route("/",', '"/assets/', '"/api/profile"', '"/api/layouts"',
                 '"/api/status"', '"/healthz"'):
        ok(path not in src, path + " is registered by its area's routes")
    eq([inspect.getsource(m).count("@mcp.custom_route(")
        for m in (routes_rendering, routes_profile, routes_layouts, routes_status)], [4, 1, 1, 2],
       "the page and its 3 assets, the profile, the layouts, status and healthz")

@test
def t_the_leftovers_are_home():
    """What earlier pieces left in copilot.py lives with the rest of its area
    (piece 13): copilot.py binds none of it, its module binds all of it."""
    import importlib
    homes = {
        "gizmo.privacy": "SHOP_REDACT_DOWN_HOURS SHOP_REDACT_MAIL_HOURS _shop_redact_said _shop_owed_set _shop_redact_attempt "
                         "_SHOP_REDACT_WORDS _shop_redact_settle _shop_redact_checked _shop_redact_retry _ask_hold "
                         "_keep_live_privacy _webhook_body",
        "gizmo.team": "TEAM_COLOUR_NAMES _next_team_colour _team_setup_needed SETUP_CODE _user_public _may_edit_sizes "
                      "_may_send_mail _shop_gate _auth_guard _clean_username _find_username _starter_password _auth_me "
                      "_team_guard _team_public_list",
        "gizmo.work": "_fmt_secs _day_starts",
        "gizmo.mail": "_gmail_redirect_uri",
        "gizmo.dispatch": "_eori_hits EORI_MAX_PER_MIN",
        "gizmo.orderbook": "_orders_28d _month_key _order_counts _order_revenue _month_axis",
        "gizmo.chat": "_build_tools _TOOL_TABS _build_dispatch TOOL_RESULT_CAP _usage_summary _coerce_structured",
        "gizmo.shopify": "_ok",
        "gizmo.clock": "_london_today _london_day _london_hm",
        "gizmo.gate": "_secret_ok",
        "gizmo.status": "_data_volume_warning reseal_secrets_at_rest",
    }
    for mod, names in homes.items():
        m = importlib.import_module(mod)
        for n in names.split():
            ok(n not in vars(copilot), n + " is no longer in copilot.py")
            ok(n in vars(m), n + " lives in " + mod)

@test
def t_the_customer_history_route_counts_the_orders():
    """A label's "ordered before": /api/customer-history counts the customer's
    orders and links the newest three. It had no test of its own; pinned
    through its route before it moved to the order book's routes."""
    ensure_auth()
    orders = [{"id": 7001 + i, "name": "#10%d" % i, "created_at": "2026-0%d-01T10:00:00Z" % (i + 1)} for i in range(5)]

    async def tools(registry, name, args):
        if name == "shopify_get_customer_orders" and args.get("customer_id") == 55:
            return {"orders": list(orders)}
        return {"_failed": True}
    saved = shopify._tool_json; shopify._tool_json = tools
    try:
        r = post("/api/customer-history", {"customer_id": 55})
        eq(r.status_code, 200, r.text)
        eq(r.json()["count"], 5, "every order counted")
        eq([o["name"] for o in r.json()["recent"]], ["#104", "#103", "#102"], "the newest three")
        ok(r.json()["recent"][0]["admin_url"].endswith("/orders/7005"), "each a door to its order")
        eq(post("/api/customer-history", {}).status_code, 400, "no customer id is said")
        eq(post("/api/customer-history", {"customer_id": 9}).status_code, 502, "and an unreadable answer")
    finally:
        shopify._tool_json = saved

@test
def t_the_ai_settings_products_and_history_have_moved():
    """The AI's effort settings live with the AI client, the chat's limits with
    the chat, the catalogue reader in gizmo/products.py, and a label's order
    history with the order book's routes (piece 14; the Products tab and its
    two routes went on 22 Oct 2026)."""
    import importlib, inspect
    from gizmo.routes import orderbook as routes_orderbook
    homes = {"gizmo.ai": "ANTHROPIC_EFFORT ANTHROPIC_EFFORT_DEEP THINKING_MODE _effort_for",
             "gizmo.chat": "MAX_MESSAGES MAX_CHAT_CHARS",
             "gizmo.products": "_all_products",
             "gizmo.liability": "_CURRENCY_SIGNS"}
    for mod, names in homes.items():
        m = importlib.import_module(mod)
        for n in names.split():
            ok(n not in vars(copilot), n + " is no longer in copilot.py")
            ok(n in vars(m), n + " lives in " + mod)
    src = inspect.getsource(copilot.add_routes)
    ok('"/api/customer-history"' not in src, "customer history is registered by its area's routes")
    eq(inspect.getsource(routes_orderbook).count("@mcp.custom_route("), 3,
       "the order book's two routes and customer history")

@test
def t_the_chat_routes_and_shop_settings_have_moved():
    """The shop's own settings live with the rest of the settings on the floor;
    copilot.py keeps the secret and the base address only as copies of
    config's, for the frozen print routes. The chat's, the stream's and the
    usage panel's routes live in gizmo/routes/chat.py (piece 15)."""
    import importlib, inspect
    from gizmo.routes import chat as routes_chat
    settings, here = vars(importlib.import_module("gizmo.config")), vars(copilot)
    for n in ("SHOPIFY_API_KEY", "SHOPIFY_API_SECRET", "SHOPIFY_STORE", "APP_BASE_URL"):
        ok(n in settings, n + " lives in gizmo/config.py")
    ok("SHOPIFY_API_KEY" not in here and "SHOPIFY_STORE" not in here, "copilot.py binds neither")
    ok(here["SHOPIFY_API_SECRET"] is settings["SHOPIFY_API_SECRET"] and here["APP_BASE_URL"] is settings["APP_BASE_URL"],
       "and keeps the secret and the base address as copies of config's, for the frozen print routes")
    src = inspect.getsource(copilot.add_routes)
    eq(src.count("routes_chat.register(mcp, registry)"), 1, "the chat's routes, one call")
    for path in ('"/api/chat', '"/api/usage"'):
        ok(path not in src, path + " is registered by the chat's routes")
    eq(inspect.getsource(routes_chat).count("@mcp.custom_route("), 3, "the chat, its stream and the usage panel")

@test
def t_no_error_is_swallowed_without_a_reason():
    """A broad handler that lets an error go without a word (a pass, a
    continue or break, a bare return) says why in a comment on its own lines:
    silence is sometimes right, but only for a reason a reader can check.
    tools/broad_excepts.py finds them across the app (stage 5, A4)."""
    import importlib.util
    spec_ = importlib.util.spec_from_file_location("broad_excepts", os.path.join(HERE, "tools", "broad_excepts.py"))
    be = importlib.util.module_from_spec(spec_); spec_.loader.exec_module(be)
    found = be.scan()
    ok(len(found) > 300, "the scan finds the app's broad handlers (%d)" % len(found))
    quiet = [f"{h['file']}:{h['line']} {h['kind']}" for h in found if h["kind"] in be.SILENT and not h["reason"]]
    eq(quiet, [], "silent handlers that do not say why")

@test
def t_a_body_model_checks_only_what_it_names():
    """gizmo/bodies.py: a model names the fields it checks and the kind each
    must be; every other field passes, and the route reads the body as before.
    The kinds take what the page sends (text, numbers as the page sends them,
    yes or no, a list, a set of fields) and refuse an object or a list where a
    scalar belongs; the refusal names the field in plain words (stage 5)."""
    from gizmo import bodies as bd

    class M(bd.Body):
        title: bd.Text = None
        id: bd.Id = None
        count: bd.Whole = None
        amount: bd.Number = None
        on: bd.Flag = None
        ids: bd.Items = None
        origin: bd.Fields = None
        min_pence: bd.Whole = None

    good = {"title": "A note", "id": 6123456789, "count": 3, "amount": 12.5, "on": True,
            "ids": [1, "2"], "origin": {"city": "Leeds"}, "min_pence": "", "other": {"any": ["thing"]}}
    before = json.dumps(good, sort_keys=True)
    eq(bd.refusal(M, good), None, "what the page sends is taken")
    eq(json.dumps(good, sort_keys=True), before, "and the body is left exactly as it came")
    eq(bd.refusal(M, {}), None, "a field left out is the route's to decide")
    eq(bd.refusal(M, {k: None for k in good}), None, "and so is a null")
    for k, v in (("id", "a1b2"), ("count", "12"), ("count", 4.0), ("amount", "12.50"), ("amount", 3),
                 ("on", False), ("on", 1), ("ids", []), ("origin", {})):
        eq(bd.refusal(M, {k: v}), None, "%s may be %r" % (k, v))
    words = {"title": "text", "id": "text or a number", "count": "a whole number", "amount": "a number",
             "on": "yes or no", "ids": "a list", "origin": "a set of fields"}
    for k, w in words.items():
        for junk in ({"wrong": ["type"]}, ["wrong"]):
            if (k, type(junk)) in (("ids", list), ("origin", dict)):
                continue
            eq(bd.refusal(M, {k: junk}), "The %s sent must be %s." % (k, w), "%s refuses %r" % (k, junk))
    for k, v in (("title", 5), ("count", "12.5"), ("count", " "), ("count", True), ("count", float("inf")),
                 ("amount", "lots"), ("amount", float("nan")), ("on", "no"), ("id", True)):
        ok(bd.refusal(M, {k: v}), "%s refuses %r" % (k, v))
    eq(bd.refusal(M, {"min_pence": []}), "The min pence sent must be a whole number.",
       "a field's name is read as words")
    eq(bd.refusal(M, {"title": {}, "count": {}}), "The title sent must be text.", "one refusal, the first field")

    for k in ("id", "count", "amount"):
        eq(bd.refusal(M, {k: 10 ** 400}), "The %s sent must be %s." % (k, words[k]),
           "a number past any float is refused, not raised as a server error")
    eq(bd.refusal(M, {"amount": "1" * 400}), "The amount sent must be a number.", "and so is its text")
    for v in (2 ** 53 + 1, -(2 ** 53) - 1, 1e300, "9" * 17):
        eq(bd.refusal(M, {"count": v}), "The count sent must be a whole number.",
           "a whole number past what a browser can send exactly is refused: %r" % (v,))
    for v in (2 ** 53, 6123456789012, "9007199254740992", 7.5):
        eq(bd.refusal(M, {"count": v}), None, "and one it can send is taken: %r" % (v,))

    class R(bd.Body):
        messages: bd.Records = None
        frm: bd.Text = bd.named("from")
    eq(bd.refusal(R, {"messages": [{"role": "user", "content": "hi"}], "from": "2026-10-01"}), None,
       "a list of sets of fields, and a field named for a word Python keeps")
    for junk in (["hi"], [{"a": 1}, 2], {"role": "user"}):
        eq(bd.refusal(R, {"messages": junk}), "The messages sent must be a list of sets of fields.", repr(junk))
    eq(bd.refusal(R, {"from": {"wrong": 1}}), "The from sent must be text.", "named as it is sent")
    eq(bd.sent_names(R), ["messages", "from"], "the names a body uses")

    per_op = {"add": M}
    eq(bd.refusal(per_op, {"op": "add", "title": {}}), "The title sent must be text.", "an op's own model")
    for b in ({"op": "list", "title": {}}, {"title": {}}, {"op": {"add": 1}, "title": {}}, {"op": ["add"]}):
        eq(bd.refusal(per_op, b), None, "an op the models do not name reaches the route as before: %r" % (b,))

@test
def t_the_door_refuses_a_wrong_type_last():
    """gate._guard(model=...) checks the body after everything else the door
    checks: no session is still a 401, a rank too low still a 403, and only a
    caller the door lets in hears that a field is of the wrong kind (a 400
    naming it). A body that passes reaches the route as it was sent."""
    from gizmo import bodies as bd
    from starlette.applications import Starlette
    from starlette.routing import Route

    class M(bd.Body):
        title: bd.Text = None

    seen = []

    async def _route(request):
        err, body, who = await gate._guard(request, min_level=int(request.query_params.get("level") or 0), model=M)
        if err:
            return err
        seen.append(body)
        return gate._json({"ok": True})

    c = TestClient(Starlette(routes=[Route("/door-check", _route, methods=["POST"])]))

    def send(body, session=None, level=0):
        gate._rl_hits.clear(); gate._rl_global.clear()
        h = {"Authorization": "Bearer " + tok()}
        if session:
            h["X-App-Session"] = session
        return c.post("/door-check" + ("?level=%d" % level if level else ""), json=body, headers=h)

    eq(send({"title": {"wrong": 1}}).status_code, 401, "no session: a 401, whatever the body")
    _uid, member, _pw = ready_user("Door Check", "doorcheck")
    eq(send({"title": {"wrong": 1}}, member, level=team.ROLE_LEVELS["admin"]).status_code, 403,
       "a rank too low: a 403, whatever the body")
    r = send({"title": {"wrong": 1}}, member)
    eq(r.status_code, 400, r.text)
    eq(r.json().get("error"), "The title sent must be text.")
    eq(seen, [], "the route never saw it")
    r = send({"title": "Fine", "extra": [1, {"a": 2}]}, member)
    eq(r.status_code, 200, r.text)
    eq(seen, [{"title": "Fine", "extra": [1, {"a": 2}]}], "a body that passes reaches the route as sent")

def _wrong_kinds_refused(cases, send=None):
    """Each (path, op, model): every field the model names, sent as an object
    and as a list, is a 400 in the model's own words wherever the model refuses
    that value. Returns how many requests were refused. `send(path, body)`
    stands in for post() where a route has its own door."""
    from gizmo import bodies as bd
    n = 0
    for path, op, model in cases:
        m = bd.model_for(model, {"op": op})
        ok(m is not None and m.model_fields, "%s %s has a model naming its fields" % (path, op))
        for field in bd.sent_names(m):
            for junk in ({"wrong": ["type"]}, ["wrong"]):
                body = {field: junk, **({"op": op} if op else {})}
                want = bd.refusal(model, body)
                if want is None:
                    continue          # the kind takes it (a list where a list belongs)
                r = (send or post)(path, body)
                eq((r.status_code, r.json().get("error")), (400, want), "%s %s %s=%r" % (path, op, field, junk))
                n += 1
    return n

@test
def t_a_wrong_type_is_refused_by_name_not_a_server_error():
    """The routes a stray script could break with a field of the wrong
    kind (an object where an id or a number belongs) refuse it at the door
    with a 400 naming the field, before the route reads it (stage 5)."""
    from gizmo.routes import memory as r_memory, dispatch as r_dispatch
    from gizmo.routes import impact as r_impact, production as r_production, skills as r_skills
    from gizmo.routes import updates as r_updates
    for path, body, words in (
            ("/api/memory", {"op": "delete", "id": {"wrong": 1}}, "The id sent must be text or a number."),
            ("/api/memory", {"op": "set_status", "id": {"wrong": 1}}, "The id sent must be text or a number."),
            ("/api/shipping/config", {"op": "set", "boxes": {"wrong": 1}}, "The boxes sent must be a list."),
            ("/api/impact", {"op": "add", "text": {"wrong": 1}}, "The text sent must be text."),
            ("/api/production-state", {"op": "made", "id": {"wrong": 1}}, "The id sent must be a whole number."),
            ("/api/skills", {"op": "delete", "id": {"wrong": 1}}, "The id sent must be text or a number."),
            ("/api/updates", {"op": "seen", "releases": {"wrong": 1}}, "The releases sent must be a whole number.")):
        r = post(path, body)
        eq((r.status_code, r.json().get("error")), (400, words), "%s %r" % (path, body))
    n = _wrong_kinds_refused([
        ("/api/memory", "delete", r_memory.MemoryBody),
        ("/api/shipping/config", "set", r_dispatch.ShippingBody),
        ("/api/impact", "add", r_impact.ImpactBody),
        ("/api/production-state", "made", r_production.ProductionStateBody),
        ("/api/production-state", "printed", r_production.ProductionStateBody),
        ("/api/skills", "update", r_skills.SkillBody),
        ("/api/updates", "request", r_updates.UpdatesBody)])
    ok(n > 60, "every field each model names was tried (%d refusals)" % n)

def _scratch_files():
    """Every file the suite's stores keep, by path, with its bytes' digest."""
    import hashlib
    out = {}
    for dirpath, _dirs, names in os.walk(SCRATCH):
        for nm in names:
            p = os.path.join(dirpath, nm)
            try:
                with open(p, "rb") as fh:
                    out[os.path.relpath(p, SCRATCH)] = hashlib.sha256(fh.read()).hexdigest()
            except OSError:
                pass
    return out

@test
def t_a_wrong_type_is_refused_before_anything_is_kept():
    """The ten routes that took a field of the wrong kind and kept it as text
    (the CRM, the Files tree, the live size overrides, the store knowledge, the
    chase log, the loan register, the accounts file, the privacy log and the
    feature requests) refuse it at the door, and nothing is written (stage 5)."""
    from gizmo.routes import crm as r_crm, files as r_files, size_list as r_sizes, knowledge as r_know
    from gizmo.routes import liability as r_liab, loans as r_loans, mail as r_mail, privacy as r_priv
    from gizmo.routes import updates as r_updates
    ensure_auth()
    before = _scratch_files()
    for path, body, words in (
            ("/api/crm/activity", {"op": "add", "subject": {"wrong": 1}}, "The subject sent must be text."),
            ("/api/crm/contact", {"op": "org_add", "name": {"wrong": 1}}, "The name sent must be text."),
            ("/api/crm/contact", {"op": "person_add", "name": {"wrong": 1}}, "The name sent must be text."),
            ("/api/files/folder", {"op": "add", "name": {"wrong": 1}}, "The name sent must be text."),
            ("/api/gobo-sizes/rule", {"op": "exclude", "model": {"wrong": 1}}, "The model sent must be text."),
            ("/api/learn", {"op": "save", "knowledge": {"wrong": 1}}, "The knowledge sent must be text."),
            ("/api/liability/chase", {"key": {"wrong": 1}}, "The key sent must be text."),
            ("/api/loans", {"op": "unit_save", "name": {"wrong": 1}}, "The name sent must be text."),
            ("/api/mail/settings", {"op": "sign_off", "text": {"wrong": 1}}, "The text sent must be text."),
            ("/api/privacy", {"op": "answered", "at": "2026-10-21T09:00:00", "email": {"wrong": 1}},
             "The email sent must be text."),
            ("/api/updates", {"op": "request", "title": {"wrong": 1}}, "The title sent must be text.")):
        r = post(path, body)
        eq((r.status_code, r.json().get("error")), (400, words), "%s %r" % (path, body))
    n = _wrong_kinds_refused([
        ("/api/crm/activity", "add", r_crm.CrmActivityBody),
        ("/api/crm/contact", "person_update", r_crm.CrmContactBody),
        ("/api/files/folder", "add", r_files.FolderBody),
        ("/api/gobo-sizes/rule", "set", r_sizes.SizeRuleBody),
        ("/api/learn", "save", r_know.KnowledgeBody),
        ("/api/liability/chase", None, r_liab.ChaseBody),
        ("/api/loans", "unit_save", r_loans.LoansBody),
        ("/api/mail/settings", "sign_off", r_mail.MailSettingsBody),
        ("/api/privacy", "answered", r_priv.PrivacyBody),
        ("/api/updates", "request", r_updates.UpdatesBody)])
    ok(n > 100, "every field each model names was tried (%d refusals)" % n)
    after = _scratch_files()
    eq(sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k)), [], "nothing was written")

@test
def t_the_accounts_routes_refuse_a_wrong_kind():
    """Stage 5, piece 2: the sign-in walks, the team register, the workspace's
    own routes (alerts, the schedule, the profile, the chat and its usage, the
    work clock's report), the reports' reads, reconciliation's, the Xero
    connector's, restore, the forecast's workbook and results hook, and order
    edits each name the fields they read. Every one, sent as an object and as a
    list, is a 400 in the model's words before the route reads it."""
    from gizmo.routes import scheduler as r_sched, team as r_team, chat as r_chat, xero_sync as r_xs
    from gizmo.routes import orderbook as r_ob
    from gizmo.routes import profile as r_prof, backup as r_bk, skills as r_sk
    from gizmo.routes import work as r_work, forecasting as r_fc
    n = _wrong_kinds_refused([
        ("/api/alerts", "dismiss", r_sched.AlertBody),
        ("/api/auth/login", None, r_team.LoginBody),
        ("/api/auth/mfa", "status", r_team.MfaBody),
        ("/api/auth/mfa-verify", None, r_team.MfaVerifyBody),
        ("/api/auth/password", None, r_team.PasswordBody),
        ("/api/auth/setup", None, r_team.SetupBody),
        ("/api/team/user", "rename", r_team.TeamUserBody),
        ("/api/chat", None, r_chat.ChatBody),
        ("/api/chat/stream", None, r_chat.ChatBody),
        ("/api/usage", None, r_chat.UsageBody),
        ("/api/connector", "status", r_xs.ConnectorBody),
        ("/api/customer-history", None, r_ob.CustomerHistoryBody),
        ("/api/order/edit", "read", r_ob.OrderEditBody),
        ("/api/profile", None, r_prof.ProfileBody),
        ("/api/restore", None, r_bk.RestoreBody),
        ("/api/skills/read", None, r_sk.SkillReadBody),
        ("/api/work/report", None, r_work.WorkReportBody),
        ("/api/work/resolve", None, r_work.WorkResolveBody),
        ("/api/forecast/workbook", None, r_fc.WorkbookBody)])
    ok(n > 100, "every field each model names was tried (%d refusals)" % n)
    saved = forecasting.FORECAST_INGEST_TOKEN
    try:
        forecasting.FORECAST_INGEST_TOKEN = "forecast-secret-for-tests"
        hook = lambda path, body: client.post(path, json=body, headers={"X-Forecast-Token": "forecast-secret-for-tests"})
        ok(_wrong_kinds_refused([("/hooks/forecast/results", None, r_fc.ForecastResultsBody)], send=hook) > 10,
           "the forecast's results hook, behind its own token")
    finally:
        forecasting.FORECAST_INGEST_TOKEN = saved

@test
def t_the_desks_routes_refuse_a_wrong_kind():
    """Stage 5, piece 3: the CRM's deals, leads, stages and import, every
    Inbox route and Files name the fields they read. Every one, sent as an
    object and as a list, is a 400 in the model's words before the route reads
    it. Each op chosen is one that changes nothing when it is let through."""
    from gizmo.routes import crm as r_crm, mail as r_mail, files as r_files
    n = _wrong_kinds_refused([
        ("/api/crm/deal", "detail", r_crm.CrmDealBody),
        ("/api/crm/import", None, r_crm.CrmImportBody),
        ("/api/crm/lead", "seen", r_crm.CrmLeadBody),
        ("/api/crm/stages", None, r_crm.CrmStagesBody),
        ("/api/mail/assign", None, r_mail.MailAssignBody),
        ("/api/mail/attach-done", None, r_mail.MailAttachDoneBody),
        ("/api/mail/attach-url", None, r_mail.MailAttachUrlBody),
        ("/api/mail/attachment", None, r_mail.MailAttachmentBody),
        ("/api/mail/board", None, r_mail.MailBoardBody),
        ("/api/mail/body", None, r_mail.MailMessageBody),
        ("/api/mail/bulk", "state", r_mail.MailBulkBody),
        ("/api/mail/draft", "save", r_mail.MailDraftBody),
        ("/api/mail/note", None, r_mail.MailNoteBody),
        ("/api/mail/presence", None, r_mail.MailPresenceBody),
        ("/api/mail/read", None, r_mail.MailReadBody),
        ("/api/mail/rules", "list", r_mail.MailRulesBody),
        ("/api/mail/search", None, r_mail.MailSearchBody),
        ("/api/mail/send", None, r_mail.MailSendBody),
        ("/api/mail/state", None, r_mail.MailStateBody),
        ("/api/mail/thread", None, r_mail.MailThreadBody),
        ("/api/mail/undo", None, r_mail.MailUndoBody),
        ("/api/mail/viewing", None, r_mail.MailViewingBody),
        ("/api/files/complete", None, r_files.FileCompleteBody),
        ("/api/files/download-url", None, r_files.FileDownloadBody),
        ("/api/files/file", "rename", r_files.FileBody),
        ("/api/files/upload-url", None, r_files.FileUploadBody)])
    ok(n > 100, "every field each model names was tried (%d refusals)" % n)
    for items in (["a"], [{"name": "Hot"}, "Cold"]):
        r = post("/api/crm/stages", {"labels": items})
        eq((r.status_code, r.json().get("error")), (400, "The labels sent must be a list of sets of fields."), repr(items))

@test
def t_the_shipping_routes_refuse_a_wrong_kind():
    """Stage 5, piece 4: the dispatch desk (quotes, bookings, cancellations,
    collections, the diagnosis, address parsing), custom shipments, the EORI
    check, the Size list's check, models and upload, and the production labels
    feed name the fields they read. Every one, sent as an object and as a list,
    is a 400 in the model's words before the route reads it: nothing is quoted,
    booked, voided or queued on a field of the wrong kind."""
    from gizmo.routes import dispatch as r_disp, size_list as r_sizes, production as r_prod
    n = _wrong_kinds_refused([
        ("/api/custom/quote", None, r_disp.CustomQuoteBody),
        ("/api/custom/book", None, r_disp.CustomBookBody),
        ("/api/custom/list", None, r_disp.CustomListBody),
        ("/api/custom/visibility", None, r_disp.CustomVisibilityBody),
        ("/api/dispatch/quote", None, r_disp.DispatchQuoteBody),
        ("/api/dispatch/book", None, r_disp.DispatchBookBody),
        ("/api/dispatch/cancel", None, r_disp.DispatchCancelBody),
        ("/api/dispatch/collections", None, r_disp.DispatchCollectionsBody),
        ("/api/dispatch/diagnose", None, r_disp.DispatchDiagnoseBody),
        ("/api/dispatch/parse-address", None, r_disp.ParseAddressBody),
        ("/api/eori/check", None, r_disp.EoriCheckBody),
        ("/api/gobo-sizes/check", None, r_sizes.SizeCheckBody),
        ("/api/gobo-sizes/models", None, r_sizes.SizeModelsBody),
        ("/api/gobo-sizes/upload", None, r_sizes.SizeUploadBody),
        ("/api/production-labels", None, r_prod.ProductionLabelsBody),
        ("/api/production-labels/coverage", None, r_prod.LabelCoverageBody),
        ("/api/production-labels/queue", None, r_prod.LabelQueueBody)])
    ok(n > 60, "every field each model names was tried (%d refusals)" % n)
    r = post("/api/dispatch/quote", {"order_id": 1001, "boxes": [{"width": 10}, "big"]})
    eq((r.status_code, r.json().get("error")), (400, "The boxes sent must be a list of sets of fields."))

@test
def t_the_routes_the_first_count_missed_refuse_a_wrong_kind():
    """The count of unchecked routes saw only body.get("x") with the key
    written out; a review found twelve more that read fields through a helper,
    a computed key or (body or {}).get(...): the CRM board's and Files tree's
    poll, a label's download, the day's manifest, the margin report, the
    overview's and liability's refresh, claiming a conversation and its
    orders, the accounts mailbox link, card layouts and the forecast's store
    reads. Each now names its fields, and the count sees them all."""
    from gizmo.routes import crm as r_crm, files as r_files, dispatch as r_disp, liability as r_liab
    from gizmo.routes import mail as r_mail, layouts as r_lay
    from gizmo.routes import forecasting as r_fc
    n = _wrong_kinds_refused([
        ("/api/crm/board", None, r_crm.CrmBoardBody),
        ("/api/files/tree", None, r_files.FilesTreeBody),
        ("/api/dispatch/label", None, r_disp.DispatchLabelBody),
        ("/api/dispatch/manifest", None, r_disp.DispatchManifestBody),
        ("/api/margin", None, r_disp.MarginBody),
        ("/api/liability", None, r_liab.LiabilityBody),
        ("/api/mail/claim", None, r_mail.MailClaimBody),
        ("/api/mail/orders", None, r_mail.MailOrdersBody),
        ("/api/layouts", None, r_lay.LayoutBody)])
    ok(n > 20, "every field each model names was tried (%d refusals)" % n)
    gate._rl_hits.clear(); gate._rl_global.clear()
    r = client.post("/api/margin", content=b'{"days": Infinity}',
                    headers={"Authorization": "Bearer " + tok(), "X-App-Session": ensure_auth(),
                             "Content-Type": "application/json"})
    eq((r.status_code, r.json().get("error")), (400, "The days sent must be a whole number."),
       "an infinite number of days was a server error inside the route")
    saved = forecasting.FORECAST_INGEST_TOKEN
    try:
        forecasting.FORECAST_INGEST_TOKEN = "forecast-secret-for-tests"
        hook = lambda path, body: client.post(path, json=body, headers={"X-Forecast-Token": "forecast-secret-for-tests"})
        ok(_wrong_kinds_refused([("/hooks/forecast/shopify", "products", r_fc.ForecastShopifyBody)], send=hook) >= 3,
           "the forecast's store reads, behind their token")
    finally:
        forecasting.FORECAST_INGEST_TOKEN = saved

@test
def t_what_callers_send_passes_every_model():
    """The sweeps above prove each model is wired to its door; this proves each
    one fits. tests/caller_payloads.json holds what the callers send today:
    bodies rebuilt from the page's code, the forecast worker's and the admin
    extensions', each with its file and line, at least one for every route
    with a model (stage 5's final review built most of them). Every one passes
    its model, so a model stricter than its callers fails here first. Add a
    caller's body here when a route gains a model or a caller changes."""
    import importlib, importlib.util
    from gizmo import bodies as bd
    spec = importlib.util.spec_from_file_location("route_reference", os.path.join(HERE, "tools", "route_reference.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = {r["path"]: r for r in mod.collect(HERE)}
    payloads = json.load(open(os.path.join(HERE, "tests", "caller_payloads.json"), encoding="utf-8"))
    modelled = {p for p, r in rows.items() if r["body"]}
    eq(sorted(modelled - {p["path"] for p in payloads}), [], "every route with a model has what its callers send")
    refused = []
    for p in payloads:
        r = rows[p["path"]]
        model = getattr(importlib.import_module(r["module"]), r["body"])
        why = bd.refusal(model, json.loads(json.dumps(p["body"])))
        if why:
            refused.append("%s from %s: %s" % (p["path"], p["source"], why))
    eq(refused, [], "what a caller sends today is refused")

    class TooStrict(bd.Body):
        id: bd.Text = None
    ok(bd.refusal(TooStrict, next(p["body"] for p in payloads if p["path"] == "/api/production-state" and "id" in p["body"])),
       "a model stricter than its callers is caught (Shopify's order ids arrive as numbers)")

# The write routes that read fields from their body with no model checking
# them (gizmo/bodies.py), each left so on purpose. Every other one has a model
# (stage 5, pieces 1 to 4). A new write route comes with its model.
UNCHECKED_BODIES = [
    "/api/stock-usage", "/api/stock-usage/send",   # the stock bridge: hands off
    "/print/production-labels/sign",                # the signed print route: frozen
    "/webhooks/privacy",                            # Shopify shapes this body; refusing it would break the compliance path
]

@test
def t_write_routes_check_their_bodies():
    """Every route that takes a POST and reads fields from its body names them
    in a model, or is on UNCHECKED_BODIES; docs/API.md's Body column names the
    model, or says the fields are unchecked (stage 5)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("route_reference", os.path.join(HERE, "tools", "route_reference.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = mod.collect(HERE)
    by = {r["path"]: r for r in rows}
    eq(by["/api/memory"]["body"], "MemoryBody", "a model handed to the door is named")
    eq(by["/api/crm/activity"]["body"], "CrmActivityBody", "and one handed through an area's door")
    eq(by["/api/gobo-sizes/rule"]["body"], "SizeRuleBody", "and one a route checks after reading its own body")
    ok({"subject", "deal_id", "done"} <= set(by["/api/crm/activity"]["fields"]), "the fields a route reads are listed")
    eq(by["/api/margin"]["fields"], ["days"], "and one read as (body or {}).get(...)")
    ok("*" in by["/api/mail/claim"]["fields"], "a body handed to a helper counts as read, as *: " + repr(by["/api/mail/claim"]["fields"]))
    eq(by["/webhooks/privacy"]["body"], "", "a route with no model has none")
    first = ["/api/crm/activity", "/api/crm/contact", "/api/files/folder", "/api/gobo-sizes/rule", "/api/impact",
        "/api/learn", "/api/liability/chase", "/api/loans", "/api/mail/settings", "/api/memory", "/api/privacy",
        "/api/production-state", "/api/shipping/config", "/api/skills", "/api/updates"]
    eq([p for p in first if not by[p]["body"]], [], "the routes given a model first (piece 1) keep it")
    unchecked = sorted(r["path"] for r in rows if "POST" in r["methods"] and r["fields"] and not r["body"])
    eq([p for p in unchecked if p not in UNCHECKED_BODIES], [],
       "a new write route reads fields with no model: give it one (gizmo/bodies.py)")
    eq([p for p in UNCHECKED_BODIES if p not in unchecked], [],
       "these now have a model: take them off UNCHECKED_BODIES")

@test
def t_only_the_stock_bridge_reads_copilot():
    """Stage 4 left every area importing copilot.py, to read it as core.NAME;
    by its end almost none did. Only the stock bridge's readers import it now
    (the bridge stays in copilot.py, hands off), and they read nothing else
    from it (stage 6)."""
    import ast as _ast
    importers = {}
    for mod, rel in _app_module_files().items():
        if mod in ("copilot", "server"):
            continue
        t = _ast.parse(open(os.path.join(HERE, rel), encoding="utf-8").read())
        if any((isinstance(n, _ast.Import) and any(a.name == "copilot" for a in n.names))
               or (isinstance(n, _ast.ImportFrom) and n.module == "copilot") for n in _ast.walk(t)):
            importers[rel] = sorted({n.attr for n in _ast.walk(t) if isinstance(n, _ast.Attribute)
                                     and isinstance(n.value, _ast.Name) and n.value.id == "core"})
    eq(sorted(importers), ["gizmo/routes/production.py", "gizmo/routes/status.py", "gizmo/scheduler.py"],
       "the modules that import copilot.py")
    for rel, reads in importers.items():
        eq([r for r in reads if "zeta" not in r], [], rel + " reads only the stock bridge from it")

@test
def t_background_work_has_its_own_home():
    """gizmo/background.py, on the floor: spawn(coro) runs a coroutine after
    the request and holds a reference until it is done (a bare create_task can
    be collected before it runs); with no loop it answers False and closes the
    coroutine, so the caller can do the work inline. Until stage 6 it lived in
    copilot.py and kept its tasks in the CRM's own set."""
    from gizmo import background
    ran = []

    async def job():
        ran.append(1)

    async def go():
        ok(background.spawn(job()), "spawned")
        eq(len(background._tasks), 1, "held while it waits to run")
        for _ in range(3):
            await asyncio.sleep(0)
    run(go())
    eq((ran, len(background._tasks)), ([1], 0), "it ran, and was let go")
    c = job()
    eq(background.spawn(c), False, "no loop: the caller does the work inline")
    eq(c.cr_frame, None, "and the coroutine is closed, never left unawaited")
    ok(not hasattr(salesdesk, "_crm_bg_tasks"), "the CRM no longer keeps everyone's tasks")
    ok("gizmo/background.py" in FLOOR, "on the floor")

@test
def t_the_docs_name_only_what_exists():
    """The living docs describe the code as it is (stage 6): every file or
    folder they name in backticks exists, every test they name is a test, and
    none says the backend is still being split. A rename that leaves a doc
    pointing at nothing fails here, not in a reader's hands."""
    import glob as _glob
    docs = ["docs/ARCHITECTURE.md", "README.md", "docs/README.md", "tools/moves/README.md", "docs/DESIGN.md"]
    tests = set()
    for suite in _glob.glob(os.path.join(HERE, "tests", "**", "*.py"), recursive=True):
        tests |= set(re.findall(r"^def (t_\w+)\(", open(suite, encoding="utf-8").read(), re.M))
    missing, unknown, stale = [], [], []
    for doc in docs:
        text = open(os.path.join(HERE, doc), encoding="utf-8").read()
        for tick in re.findall(r"`([^`\n]+)`", text):
            word = tick.split(":")[0].strip()
            if re.fullmatch(r"t_\w+", word):
                if word not in tests:
                    unknown.append(f"{doc}: {word}")
            elif re.fullmatch(r"[\w.-]+(/[\w.*<>-]+)+/?|[\w-]+\.(py|md|json|js|css|html|toml|txt)", word) \
                    and "<" not in word and "*" not in word:
                if not os.path.exists(os.path.join(HERE, word)) and not os.path.exists(os.path.join(HERE, "docs", word)):
                    missing.append(f"{doc}: {word}")
        if re.search(r"being split|is split one area at a time|moved out so far", text):
            stale.append(doc)
    eq(missing, [], "paths the docs name that do not exist")
    eq(unknown, [], "tests the docs name that do not exist")
    eq(stale, [], "docs that still describe the split as under way")

@test
def t_the_suite_is_in_sections():
    """The dispatch suite is a file per stretch of it under tests/dispatch/,
    run in the order tests/test_dispatch.py lists them, in one namespace: the
    one file it was until stage 6, cut where its banners stood and nowhere
    else but between tests. Every file there is listed once, the harness
    comes first and holds no test, the runner comes last, each stands alone as
    Python and none is over 1,700 lines, so a reader can open one; and every
    test in them is one the runner runs."""
    import ast as _ast, importlib.util
    spec_ = importlib.util.spec_from_file_location("dispatch_suite", os.path.join(HERE, "tests", "test_dispatch.py"))
    suite = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(suite)
    files = sorted(f for f in os.listdir(suite.DIR) if f.endswith(".py"))
    eq(sorted(suite.SECTIONS), files, "every file in tests/dispatch/ listed, and only those")
    eq(len(set(suite.SECTIONS)), len(suite.SECTIONS), "no file listed twice")
    eq((suite.SECTIONS[0], suite.SECTIONS[-1]), ("harness.py", "runner.py"), "the harness first, the runner last")
    for name in suite.SECTIONS:
        text = open(os.path.join(suite.DIR, name), encoding="utf-8").read()
        ok(text.count("\n") <= 1700, "%s is %d lines" % (name, text.count("\n")))
        _ast.parse(text, name)
    ok("\n@test\n" not in "\n" + open(os.path.join(suite.DIR, "harness.py"), encoding="utf-8").read(),
       "the harness holds no test")
    whole = suite.source()
    eq(whole, suite_source(), "what the runner ran is what the sections say")
    eq(len([t for t in TESTS if not t.__name__.startswith("t_suite_selftest_")]), whole.count("\n@test\n"),
       "every test in the sections is one the runner runs")

@test
def t_the_moved_areas_routes_follow_them():
    """Production's, the Size list's and the order book's routes follow their
    areas into gizmo/routes/, each group registered by one call. The two
    printed-label routes stay in add_routes: their bytes are pinned."""
    import inspect
    from gizmo.routes import orderbook as routes_orderbook, production as routes_production, size_list as routes_size_list
    src = inspect.getsource(copilot.add_routes)
    for call in ("routes_production.register(mcp, registry)", "routes_size_list.register(mcp, registry)",
                 "routes_orderbook.register(mcp, registry)"):
        eq(src.count(call), 1, call)
    for path in ('"/api/production-labels', '"/api/production-state', '"/api/gobo-sizes', '"/api/order/', '"/webhooks/orders'):
        ok(path not in src, path + " follows its area")
    ok('@mcp.custom_route("/print/production-labels", methods=["GET", "OPTIONS"])' in src
       and '"/print/production-labels/sign"' in src, "the printed-label routes stay where they are")
    eq([inspect.getsource(m).count("@mcp.custom_route(") for m in (routes_production, routes_size_list, routes_orderbook)],
       [5, 6, 3], "5 production routes, 6 Size list routes, 2 order routes and customer history (piece 14)")

@test
def t_a_passing_test_prints_its_name_and_nothing_else():
    """The suite printed about 7,000 lines, nearly all of them what the app
    logs on the paths the tests take on purpose, so a real failure was hard to
    find in CI's output (audit A6). Each test's log lines are held, and printed
    only under its FAIL line; VERBOSE=1 streams them as they come, as before.
    Two toy tests, there only when SUITE_SELFTEST is set, are run in a child."""
    import subprocess
    here = os.path.abspath(__file__)
    env = {k: v for k, v in os.environ.items() if k not in ("VERBOSE", "KEEP_SCRATCH", "ONLY")}

    def child(**extra):
        tmp = tempfile.mkdtemp(dir=SCRATCH)
        return subprocess.run([sys.executable, here], capture_output=True, text=True, timeout=300,
                              env=dict(env, TMPDIR=tmp, ONLY="t_suite_selftest_", SUITE_SELFTEST="1", **extra))

    p = child()
    eq(p.returncode, 1, "a failing test still fails the run")
    ok("PASS  t_suite_selftest_logs_and_passes" in p.stdout and "FAIL  t_suite_selftest_logs_and_fails" in p.stdout
       and "1 passed, 1 failed" in p.stdout, p.stdout[-800:] + p.stderr[-800:])
    ok("a passing test's line" not in p.stdout + p.stderr, "a passing test's log lines are not printed")
    after = p.stdout.split("FAIL  t_suite_selftest_logs_and_fails", 1)[1]
    ok("a failing test's line" in after, "a failing test's are, under its FAIL line: " + after[:400])
    v = child(VERBOSE="1")
    ok("a passing test's line" in v.stdout + v.stderr, "VERBOSE=1 streams them as they come")

# ---------------------------------------------------------------------------
# The trim (22 Oct 2026): the report tabs and Reconciliation leave, and what
# kept pages borrowed from their files moves to kept homes first.
# ---------------------------------------------------------------------------

@test
def t_learn_my_store_fetches_through_the_storefront_guard():
    """Learn my store reads the shop's own site through the guarded fetch,
    which lived in the SEO report's file. It lives in gizmo/storefront.py now,
    so removing the SEO tab cannot take Memory's crawler with it."""
    seen = []
    async def fake_get(url, allowed_hosts=None):
        seen.append((url, allowed_hosts))
        return 200, "<urlset></urlset>"
    saved = storefront._http_get
    storefront._http_get = fake_get
    try:
        run_async(knowledge._discover_content_urls("shop.example", {"shop.example"}, 3))
    finally:
        storefront._http_get = saved
    ok(seen and seen[0] == ("https://shop.example/sitemap.xml", {"shop.example"}),
       "the sitemap is read through storefront._http_get: %r" % (seen,))


@test
def t_the_connect_secret_lives_in_config():
    """The recovery key for the sign-in walks was defined in the Google data
    module, which goes. The Inbox's mailbox connect still needs it until the
    Inbox goes, so it reads it from gizmo/config.py."""
    eq(config.CONNECT_SECRET, os.environ.get("GOOGLE_CONNECT_SECRET", ""))
    src = open(os.path.join(HERE, "gizmo", "routes", "mail.py"), encoding="utf-8").read()
    ok("config.CONNECT_SECRET" in src and "google_data" not in src,
       "the Inbox's connect walk reads config.CONNECT_SECRET, not google_data")


@test
def t_liability_keeps_its_own_currency_signs():
    """The chase emails write amounts with a currency sign the Liability page
    borrowed from the report module, which goes. Liability keeps its own."""
    eq(liability._CURRENCY_SIGNS, {"GBP": "\u00a3", "USD": "$", "EUR": "\u20ac"})
    src = open(os.path.join(HERE, "gizmo", "liability.py"), encoding="utf-8").read()
    ok("analytics" not in src, "liability.py no longer reads the report module")


class _GateReq:
    """Just enough of a request for gate._tab_denied: a path and a session."""
    def __init__(self, path, sess):
        self.url = type("U", (), {"path": path})(); self.headers = {"x-app-session": sess}


@test
def t_a_saved_tab_list_naming_a_removed_report_tab_still_loads():
    """Accounts saved before the trim may still list overview, seo, keywords
    or products. Those keys are dropped as the list is read, never an error,
    and the tabs that remain still open."""
    ensure_auth()
    uid, sess, _ = ready_user("Rae", "rae")
    d = team._load_users()
    d["users"][uid]["tabs"] = ["overview", "seo", "keywords", "products", "labels", "customers"]
    team._write_users(d)
    eq(team._user_tabs(uid), ["labels", "customers"])
    ok(gate._tab_denied(_GateReq("/api/production-state", sess)) is None, "Labels still opens")
    eq(login("rae", "chosen-pw-123456").status_code, 200, "and the account still signs in")


@test
def t_customer_history_still_answers_the_customers_permission():
    """Labels' order-history line reads /api/customer-history. The Customers
    tab goes but its permission stays (Customer details on the Team page), so
    the line opens for exactly the accounts it opened for before: those with
    customers or crm, never labels alone."""
    ensure_auth()
    ok("customers" in team.TAB_KEYS and "customers" in team.DEFAULT_TABS,
       "the customers permission stays and is still given by default")
    uid, sess, _ = ready_user("Cy", "cy")
    for tabs, allowed in ((["labels"], False), (["labels", "customers"], True), (["crm"], True)):
        post("/api/team/user", {"op": "tabs", "id": uid, "tabs": tabs})
        r = gate._tab_denied(_GateReq("/api/customer-history", sess))
        eq(r is None, allowed, "customer history for %s" % tabs)


def _retired_files_round_trip(planted):
    """Plant files on the volume, build a backup, then restore a zip holding
    them: (names in the backup, names the restore wrote back). A store the
    restore keeps rides in the zip beside them and must come back, so the
    restore really ran: a zip of refused names alone is turned away whole,
    which would prove nothing about any one of them."""
    import zipfile as zz, io as iio, base64 as b64
    data_dir = os.path.dirname(scheduler.SCHEDULE_PATH)
    for n, body in planted.items():
        with open(os.path.join(data_dir, n), "w", encoding="utf-8") as fh:
            fh.write(body)
    try:
        buf, _ = backup._build_backup_zip()
        in_backup = {os.path.basename(n) for n in zz.ZipFile(buf).namelist()} & set(planted)
    finally:
        for n in planted:
            os.remove(os.path.join(data_dir, n))
    kept = os.path.basename(liability.CHASE_LOG_PATH)
    z = iio.BytesIO()
    with zz.ZipFile(z, "w") as w:
        for n, body in planted.items():
            w.writestr("volume/" + n, body)
        w.writestr("volume/" + kept, '{"accounts": {}}')
    r = post("/api/restore", {"zip": b64.b64encode(z.getvalue()).decode()})
    eq(r.status_code, 200, r.text[:300])
    ok(kept in (r.json().get("files") or []), "the kept store came back, so the restore ran: " + r.text[:300])
    written = {n for n in planted if os.path.exists(os.path.join(data_dir, n))}
    for n in written:
        os.remove(os.path.join(data_dir, n))
    return in_backup, written


@test
def t_backups_never_carry_the_google_data_token_or_the_report_stores():
    """The Google data sign-in and the report caches leave with the report
    tabs, but their files stay on the volume until somebody deletes them. A
    backup never carries the old refresh token, and neither a backup nor a
    restore carries the report stores, which nothing reads or scrubs any more
    (the customer report cache can hold customer details)."""
    def go():
        ensure_auth()
        planted = {
            os.path.basename(os.environ.get("GOOGLE_OAUTH_TOKEN_PATH", "/data/google_oauth.json")): '{"refresh_token": "old"}',
            os.path.basename(os.environ.get("ANALYSIS_CACHE_PATH", "/data/analysis_cache.json")): '{"customers_segments": {}}',
            os.path.basename(scheduler.SCHEDULE_PATH): '{"enabled": true}',
        }
        in_backup, written = _retired_files_round_trip(planted)
        eq(in_backup, set(), "none of them is in the backup")
        eq(written, set(), "and a restore writes none of them back")
    with_accounts(go)


@test
def t_payouts_in_chat_need_the_xero_sync_permission():
    """Payouts and disputes are the books. They were gated on Reconciliation's
    tab, which goes; they move to Xero sync's, the other opt-in finance tab,
    so they are never handed to an account by default."""
    for name in ("shopify_list_payouts", "shopify_payout_transactions", "shopify_list_disputes"):
        eq(assistant._TOOL_TABS.get(name), "connector", name + " is gated on the Xero sync tab")
    ok("connector" in team.OPT_IN_TABS and "connector" not in team.DEFAULT_TABS, "which is opt-in")
    calls = []

    async def _reg(payload):
        calls.append(payload)
        return "the payouts"

    who = {"uid": ""}
    dispatch = assistant._build_dispatch({"shopify_list_payouts": (_reg, dict)}, lambda: who["uid"])

    def go():
        ensure_auth()
        uid, _sess, _ = ready_user("Pia", "pia")
        who["uid"] = uid
        post("/api/team/user", {"op": "tabs", "id": uid, "tabs": ["chat"]})
        out = run_async(dispatch("shopify_list_payouts", {}))
        ok(not calls and "Refused" in out and "Xero sync" in out and "connector" not in out,
           "without Xero sync: refused, in the Team page's words, " + out[:120])
        post("/api/team/user", {"op": "tabs", "id": uid, "tabs": ["chat", "connector"]})
        eq(run_async(dispatch("shopify_list_payouts", {})), "the payouts", "with Xero sync: answered")
    with_accounts(go)


@test
def t_a_saved_tab_list_naming_reconciliation_still_loads():
    """An account handed Reconciliation before the trim keeps signing in;
    the key is dropped as its list is read."""
    ensure_auth()
    uid, _sess, _ = ready_user("Rex", "rex")
    d = team._load_users()
    d["users"][uid]["tabs"] = ["recon", "labels"]
    team._write_users(d)
    eq(team._user_tabs(uid), ["labels"])


@test
def t_the_door_checks_rank_before_it_spends_an_ai_slot():
    """The door checks who is asking, then their rank, then the paid window,
    so a member refused an admin's AI run never uses up a slot the next real
    run needs. It was pinned on Reconciliation's sweep, which went on 22 Oct
    2026; Learn my store is an admin's AI run behind the same door."""
    def go():
        ensure_auth()
        owen, sess, _pw = ready_user("Owen", "owen")
        eq(post("/api/team/user", {"op": "tabs", "id": owen, "tabs": ["memory"]}).status_code, 200)
        gate._rl_global.clear()
        r = post_s(sess, "/api/learn/run", {})
        eq(r.status_code, 403, r.text)
        ok("admin" in r.json()["error"], r.text)
        eq(len(gate._rl_global), 0, "a member's refused run did not spend an AI slot")
    with_accounts(go)


@test
def t_the_skill_reader_promises_only_what_reactor_still_does():
    """Final review, 22 Oct 2026: the skill reader still told the model it
    writes the reports and reads search and analytics data, both gone with
    the report tabs, so a skill could be read as steering work nobody does."""
    s = skillbook.SKILL_READING_SYSTEM
    for gone in ("write the reports", "analytics", "search and"):
        ok(gone not in s, "the skill reader no longer says %r" % gone)
    ok("answer questions in chat" in s and "draft email replies" in s, "and still names what is left")


@test
def t_a_retired_file_is_refused_by_its_default_name_and_its_set_one():
    """Final review, 22 Oct 2026: the retired files were named only by the
    path their setting gave, so while a setting was overridden the default
    name was let through, and once the after-deploy steps remove the setting,
    the overridden name would be. Both names are refused, whatever the
    settings say on the day."""
    for k, d in (("ANALYSIS_CACHE_PATH", "/data/analysis_cache.json"), ("GOOGLE_OAUTH_TOKEN_PATH", "/data/google_oauth.json"),
                 ("XERO_TOKEN_PATH", "/data/xero_oauth.json"), ("GMAIL_FINANCE_TOKEN_PATH", "/data/gmail_finance_oauth.json"),
                 ("RECON_PATH", "/data/recon.json"), ("RECON_CACHE_PATH", "/data/recon_cache.json"),
                 ("RECON_DOCS_PATH", "/data/recon_docs.json"), ("SCHEDULE_PATH", "/data/schedule.json")):
        ok(os.path.basename(d) in backup._RETIRED_FILES, "%s's default name %s is refused" % (k, os.path.basename(d)))
        ok(os.path.basename(os.environ.get(k, d)) in backup._RETIRED_FILES, "and the name %s gives it" % k)
    ok(os.environ.get("ANALYSIS_CACHE_PATH", "").endswith("/analysis.json"),
       "the suite overrides one, so the two names differ here: " + os.environ.get("ANALYSIS_CACHE_PATH", ""))


@test
def t_backups_never_carry_the_xero_or_accounts_mailbox_token_or_the_reconciliation_stores():
    """Reconciliation, Reactor's own Xero sign-in and the accounts mailbox go,
    but their files stay on the volume until somebody deletes them: a backup
    never carries the two refresh tokens, and neither a backup nor a restore
    carries the reconciliation stores, which nothing reads or scrubs any more."""
    def go():
        ensure_auth()
        planted = {os.path.basename(os.environ.get(k, d)): '{"refresh_token": "old"}' for k, d in (
            ("XERO_TOKEN_PATH", "/data/xero_oauth.json"),
            ("GMAIL_FINANCE_TOKEN_PATH", "/data/gmail_finance_oauth.json"),
            ("RECON_PATH", "/data/recon.json"),
            ("RECON_CACHE_PATH", "/data/recon_cache.json"),
            ("RECON_DOCS_PATH", "/data/recon_docs.json"))}
        in_backup, written = _retired_files_round_trip(planted)
        eq(in_backup, set(), "none of them is in the backup")
        eq(written, set(), "and a restore writes none of them back")
    with_accounts(go)


@test
def t_a_body_the_door_refuses_spends_no_ai_slot():
    """The AI window is the app's dearest shared resource, and the door takes a
    slot only for a request that will run. It took one before reading the body,
    so a request refused for a field of the wrong kind still spent a slot
    (stage 5's review): enough of them would keep the assistant busy for
    everyone. The body is now read and checked first."""
    h = {"Authorization": "Bearer " + tok(), "X-App-Session": ensure_auth()}
    gate._rl_hits.clear(); gate._rl_global.clear()
    for _ in range(3):
        r = client.post("/api/chat", json={"messages": "not a list"}, headers=h)
        eq(r.status_code, 400, r.text)
    eq(len(gate._rl_global), 0, "no AI slot spent on a body the door refused")
    r = client.post("/api/skills/read", json={"id": {"wrong": 1}}, headers=h)
    eq((r.status_code, len(gate._rl_global)), (400, 0), "nor on reading a skill")
