# ---- Dispatch in its own module (stage 4, piece 1) -------------------------
# The desk moved whole out of copilot.py into gizmo/dispatch.py and its routes
# into gizmo/routes/dispatch.py. Each side reaches the other through the
# module's name, never a copied name; since stage 6 the desk reads nothing
# from copilot.py at all (t_only_the_stock_bridge_reads_copilot).

@test
def t_the_split_modules_read_no_unbound_name():
    """A name a split module reads is bound in it, imported, or a builtin, so a
    path no test drives cannot meet a NameError in production."""
    import symtable, builtins as _bi
    from tools import sources
    ok("gizmo/dispatch.py" in sources.COPILOT_FILES and "gizmo/routes/dispatch.py" in sources.COPILOT_FILES,
       "the split modules exist")
    bad = []
    for rel in sources.COPILOT_FILES[1:]:
        top = symtable.symtable(open(os.path.join(sources.ROOT, rel), encoding="utf-8").read(), rel, "exec")
        bound = {s.get_name() for s in top.get_symbols() if s.is_assigned() or s.is_imported()}
        def walk(t):
            for s in t.get_symbols():
                n = s.get_name()
                if n.startswith((".", "__conditional")):    # the compiler's own (3.14 annotations)
                    continue
                if n in ("__file__", "__name__", "__doc__", "__spec__"):   # every module has these
                    continue
                if (t is top or s.is_global()) and s.is_referenced() and n not in bound and not hasattr(_bi, n):
                    bad.append(f"{rel}: {t.get_name()} reads {n}")
            for c in t.get_children():
                walk(c)
        walk(top)
    eq(sorted(set(bad)), [], "names read but bound nowhere")

@test
def t_any_module_imports_first():
    """Nothing is read across at import time: any module of the app can be
    imported first, then the rest (copilot.py brings in every area). Each in
    an interpreter of its own, over every module the app has, found rather
    than listed by hand as stage 4 did, side by side (stage 6)."""
    import subprocess as _sp
    from concurrent.futures import ThreadPoolExecutor
    mods = sorted(_app_module_files())
    ok(len(mods) > 70 and "copilot" in mods and "gizmo.background" in mods, "every module: %d" % len(mods))

    def first(m):
        return m, _sp.run([sys.executable, "-c", f"import {m}; import copilot as c, gizmo.dispatch as d; "
                           "assert c.desk is d; print('ok')"],
                          cwd=HERE, env=dict(os.environ), capture_output=True, text=True, timeout=180)
    with ThreadPoolExecutor(max_workers=max(4, (os.cpu_count() or 8) - 2)) as pool:
        bad = ["%s first: %s" % (m, r.stderr[-500:]) for m, r in pool.map(first, mods)
               if (r.returncode, r.stdout.strip()) != (0, "ok")]
    eq(bad, [], "modules that cannot be imported first")

@test
def t_dispatch_routes_register_in_place():
    """The desk's routes are registered by one call where they stood in
    add_routes, so the route table keeps its order; none is left behind."""
    import inspect
    from gizmo.routes import dispatch as routes_dispatch
    src = inspect.getsource(copilot.add_routes)
    # Where it stands is make move-proof's to check (its neighbours have since
    # moved out too); here, that it is there once.
    eq(src.count("routes_dispatch.register(mcp, registry)"), 1, "one call")
    for path in ("/api/dispatch/", "/api/shipping/", "/api/custom/", "/api/eori/", '"/api/margin'):
        ok(path not in src, path + " is registered by the desk's own routes")
    own = inspect.getsource(routes_dispatch)
    eq(own.count("@mcp.custom_route("), 16, "the desk's 16 routes")

@test
def t_the_desks_store_error_is_a_store_error():
    """One StoreUnwritable, in gizmo/store.py: copilot.py's `except
    StoreUnwritable` must still catch the desk's own store error."""
    ok(copilot.StoreUnwritable is jsonstore.StoreUnwritable, "copilot.py has no class of its own")
    ok(issubclass(desk.DispatchStoreUnwritable, copilot.StoreUnwritable), "the desk's is one of them")

@test
def t_move_proof_is_wired():
    """make move-proof BASE=<ref> proves a move out of copilot.py moved and
    changed nothing: every statement found again with the same syntax tree
    once module prefixes are read as plain names, a prefix only where the name
    was a module global, and the routes in the same order."""
    import importlib.util
    from tools import sources
    make = open(os.path.join(sources.ROOT, "Makefile"), encoding="utf-8").read()
    ok(re.search(r"^move-proof:", make, re.M) and "BASE ?= origin/main" in make, "the Makefile has move-proof")
    spec = importlib.util.spec_from_file_location("move_proof", os.path.join(sources.ROOT, "tools", "move_proof.py"))
    mp = importlib.util.module_from_spec(spec); spec.loader.exec_module(mp)
    first = sources.COPILOT_FILES[0]
    base = {first: ("import os\n\n\ndef a():\n    return b() + 1\n\n\ndef b():\n    x = 2\n    return x\n\n\n"
                    "def add_routes(mcp, registry):\n"
                    "    @mcp.custom_route('/one')\n    async def one(request):\n        return a()\n\n"
                    "    @mcp.custom_route('/two')\n    async def two(request):\n        return b()\n\n"
                    "    @mcp.custom_route('/three')\n    async def three(request):\n        return 3\n")}
    head = {first: ("import os\nfrom gizmo import dispatch as desk\nfrom gizmo.routes import dispatch as routes_dispatch\n\n\n"
                    "def a():\n    return desk.b() + 1\n\n\n"
                    "def add_routes(mcp, registry):\n"
                    "    @mcp.custom_route('/one')\n    async def one(request):\n        return a()\n\n"
                    "    routes_dispatch.register(mcp, registry)\n\n"
                    "    @mcp.custom_route('/three')\n    async def three(request):\n        return 3\n"),
            "gizmo/dispatch.py": '"""The desk."""\nimport copilot as core\n\n\ndef b():\n    x = 2\n    return x\n',
            "gizmo/routes/dispatch.py": ('"""Its routes."""\nimport copilot as core\nfrom gizmo import dispatch as desk\n\n\n'
                                         'def register(mcp, registry):\n    """Add them."""\n'
                                         "    @mcp.custom_route('/two')\n    async def two(request):\n        return desk.b()\n")}
    eq(mp.prove(base, head), [], "a function moved, read through a prefix: nothing but the move")
    optional = "try:\n    import worldoptions\nexcept Exception:\n    worldoptions = None\n"
    both = dict(head, **{"gizmo/dispatch.py": head["gizmo/dispatch.py"] + optional})
    eq(mp.prove(base, both), [], "an optional import is an import: it may come with the move")
    changed = dict(head, **{"gizmo/dispatch.py": head["gizmo/dispatch.py"].replace("x = 2", "x = 3")})
    got = mp.prove(base, changed)
    ok(any("def b" in g for g in got), "a moved function with one changed value is named: %s" % got)
    local = dict(head, **{"gizmo/dispatch.py": head["gizmo/dispatch.py"].replace("return x", "return core.x")})
    ok(any("core.x" in g for g in mp.prove(base, local)), "a local read through a prefix is named")
    declared = dict(head, **{"gizmo/dispatch.py": head["gizmo/dispatch.py"].replace("x = 2\n", "x = 2\n    x = x * 1\n")})
    st = {}
    eq(mp.prove(base, declared, st, declared=("b",)), [], "a change named as intended is not a difference")
    eq([d[0] for d in st["declared"]], ["b"], "it is shown instead")
    twice = dict(declared, **{first: declared[first].replace("def a():", "b(7)\n\n\ndef a():")})
    st = {}
    mp.prove(base, twice, st, declared=("b",))
    ok("b(7)" in st["declared"][0][2] and "x = x * 1" in st["declared"][0][2],
       "every statement under a declared name is shown, a call to it as well as its def")
    looks = {k: v.replace("x = 2", "x = len(globals())") for k, v in base.items()}
    looks_head = {k: v.replace("x = 2", "x = len(globals())") for k, v in head.items()}
    ok(any("globals()" in g for g in mp.prove(looks, looks_head)),
       "a moved function that looks its module up by name is named")
    here = {k: v.replace("x = 2", "x = __file__") for k, v in base.items()}
    here_head = {k: v.replace("x = 2", "x = __file__") for k, v in head.items()}
    ok(any("__file__" in g for g in mp.prove(here, here_head)),
       "a moved statement that finds a path from its module's own file is named")
    eq(mp.prove(here, here_head, declared=("b",)), [], "unless it is declared, and so shown")
    eq(mp.prove(here_head, here_head), [], "a statement already in its package module did not move: not named")
    glob_base = {first: base[first].replace("def add_routes(mcp, registry):\n",
                                            "def add_routes(mcp, registry):\n    global w\n    w = mcp\n")}
    glob_head = dict(head, **{first: head[first].replace("def add_routes(mcp, registry):\n",
                                                          "def add_routes(mcp, registry):\n    desk.w = mcp\n"),
                              "gizmo/dispatch.py": head["gizmo/dispatch.py"] + "w = None\n"})
    glob_base[first] = glob_base[first].replace("import os\n", "import os\nw = None\n")
    ok(any("global w" in g for g in mp.prove(glob_base, glob_head)), "a global line that went is named")
    eq(mp.prove(glob_base, glob_head, declared=("global",)), [], "and declared as global, shown")
    order = dict(head, **{first: head[first].replace("    routes_dispatch.register(mcp, registry)\n\n", "")
                          .replace("        return 3\n", "        return 3\n\n    routes_dispatch.register(mcp, registry)\n")})
    eq(mp.prove(base, order), [], "a literal route gathered past another literal route: no request changes hands")
    pat = lambda files: {k: v.replace("'/three'", "'/t{rest:path}'") for k, v in files.items()}
    eq(mp.prove(pat(base), pat(head)), [], "a pattern route left where it stood: still nothing but the move")
    ok(any("order" in g for g in mp.prove(pat(base), pat(order))),
       "but /two moved behind /t{rest:path}, which would answer it, is named")

