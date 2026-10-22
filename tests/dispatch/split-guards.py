# ---- Moving code out of copilot.py without a test going blind --------------
# Stage 4 of the 14 October audit moves areas out of copilot.py into the gizmo
# package. A test that sets `copilot.NAME = stub` tests nothing once the code
# reading NAME lives elsewhere, and a check that reads copilot.py's text passes
# with nothing to look at. These three guards make either a failure instead.

def _app_module_files():
    """Module name -> repo-relative file, for every module of the app."""
    from tools import sources
    return {f[:-3].replace("/", "."): f for f in sources.APP_MODULES}

def _module_facts(rel):
    """What a module binds at its top level, declares global, reads, copies.

    binds: names a top-level statement binds (inside a top-level if or try
    too); rebound: names a `global` statement lets a function rebind; reads:
    every name read anywhere; copies: (from-module, name, line) for each
    `from <module> import name`."""
    import ast as _ast
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tree = _ast.parse(open(os.path.join(root, rel), encoding="utf-8").read())
    binds, rebound, reads, copies = set(), set(), set(), []
    def bind_stmt(n):
        if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
            binds.add(n.name)
        elif isinstance(n, (_ast.Import, _ast.ImportFrom)):
            for a in n.names:
                binds.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, (_ast.Assign, _ast.AnnAssign, _ast.AugAssign)):
            for t in (n.targets if isinstance(n, _ast.Assign) else [n.target]):
                for x in _ast.walk(t):
                    if isinstance(x, _ast.Name):
                        binds.add(x.id)
        elif isinstance(n, (_ast.If, _ast.Try, _ast.With)):
            for part in ("body", "orelse", "finalbody", "handlers"):
                for c in getattr(n, part, []) or []:
                    for s in (c.body if isinstance(c, _ast.ExceptHandler) else [c]):
                        bind_stmt(s)
    for n in tree.body:
        bind_stmt(n)
    via = {}    # alias -> module, for `import m`, `import m as a`, `from p import m`
    for x in _ast.walk(tree):
        if isinstance(x, _ast.Global):
            rebound.update(x.names)
        elif isinstance(x, _ast.Name) and isinstance(x.ctx, _ast.Load):
            reads.add(x.id)
        elif isinstance(x, _ast.Import):
            for a in x.names:
                via[a.asname or a.name.split(".")[0]] = a.name
        elif isinstance(x, _ast.ImportFrom) and x.module and not x.level:
            for a in x.names:
                copies.append((x.module, a.name, x.lineno))
                via[a.asname or a.name] = x.module + "." + a.name
    # names this module reads on another through its name: `google_mail.send_message`
    elsewhere = {(via[x.value.id], x.attr) for x in _ast.walk(tree)
                 if isinstance(x, _ast.Attribute) and isinstance(x.ctx, _ast.Load)
                 and isinstance(x.value, _ast.Name) and x.value.id in via}
    return {"binds": binds | rebound, "rebound": rebound, "reads": reads, "copies": copies,
            "elsewhere": elsewhere}

def _test_patches():
    """Every `module.NAME = …` (and setattr) in the tests on a module of the app.

    -> list of (module, NAME, file, line, top-level function or None)."""
    import ast as _ast, glob as _glob
    mods = _app_module_files()
    here = os.path.dirname(os.path.abspath(__file__))
    out = []
    def aliases(tree):
        alias = {}
        for x in _ast.walk(tree):
            if isinstance(x, _ast.Import):
                for a in x.names:
                    if a.name in mods:
                        alias[a.asname or a.name.split(".")[0]] = a.name
            elif isinstance(x, _ast.ImportFrom) and x.module and not x.level:
                for a in x.names:
                    full = x.module + "." + a.name
                    if full in mods:
                        alias[a.asname or a.name] = full
        return alias
    # The browser seeds are run inside this suite's prelude, and the suite's
    # sections (tests/dispatch/) in one namespace after its harness, so each
    # sees the modules the harness imports without importing them.
    prelude = aliases(_ast.parse(suite_source()))
    for path in sorted(_glob.glob(os.path.join(here, "**", "*.py"), recursive=True)):
        tree = _ast.parse(open(path, encoding="utf-8").read())
        alias = aliases(tree)
        if os.sep + "seed" + os.sep in path or os.sep + "dispatch" + os.sep in path:
            alias = {**prelude, **alias}
        rel = os.path.relpath(path, os.path.dirname(here))
        def visit(node, top):
            for c in _ast.iter_child_nodes(node):
                t = top
                if top is None and isinstance(c, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    t = c.name
                targets = []
                if isinstance(c, (_ast.Assign, _ast.AugAssign, _ast.AnnAssign)):
                    for tg in (c.targets if isinstance(c, _ast.Assign) else [c.target]):
                        targets += [y for y in _ast.walk(tg) if isinstance(y, _ast.Attribute)]
                    for y in targets:
                        if isinstance(y.ctx, _ast.Store) and isinstance(y.value, _ast.Name) and y.value.id in alias:
                            out.append((alias[y.value.id], y.attr, rel, c.lineno, t))
                if (isinstance(c, _ast.Call) and isinstance(c.func, _ast.Name) and c.func.id == "setattr"
                        and len(c.args) >= 2 and isinstance(c.args[0], _ast.Name) and c.args[0].id in alias
                        and isinstance(c.args[1], _ast.Constant) and isinstance(c.args[1].value, str)):
                    out.append((alias[c.args[0].id], c.args[1].value, rel, c.lineno, t))
                # a helper handed a module and a dict of stand-ins: _swap(copilot, {"_xcreate": fake})
                if (isinstance(c, _ast.Call) and len(c.args) >= 2 and isinstance(c.args[0], _ast.Name)
                        and c.args[0].id in alias and isinstance(c.args[1], _ast.Dict)):
                    for k in c.args[1].keys:
                        if isinstance(k, _ast.Constant) and isinstance(k.value, str):
                            out.append((alias[c.args[0].id], k.value, rel, c.lineno, t))
                visit(c, t)
        visit(tree, None)
    return out

# A test that patches one module's copy of a name another module also keeps,
# where the other copy is not part of what the test means to change. Each is
# (patched module, name, the module with its own copy): the reason.
SHARED_COPIES = {
    # The shop's setting lives in gizmo/config.py (piece 15); server.py keeps its
    # own to build the Shopify client's address.
    ("gizmo.config", "SHOPIFY_STORE", "server"):
        "the frame-ancestors test reads rendering._frame_headers alone, which reads config's; "
        "server's own builds the Shopify client's address, which that test never reaches",
    # The connector settings test routes the connector call's client
    # (gizmo.xero_sync's httpx) to a fake connector; every other module's own
    # client is one that test never reaches.
    ("gizmo.xero_sync", "httpx", "server"):
        "server's client talks to Shopify, which the connector settings test never reaches",
    ("gizmo.xero_sync", "httpx", "copilot"):
        "copilot.py's own client is the stock bridge's, which the connector settings test never reaches",
    ("gizmo.xero_sync", "httpx", "gizmo.routes.xero_sync"):
        "the connector route uses httpx only to name the errors it catches (HTTPError, the timeouts, "
        "ConnectError); the routed client raises the real ones",
    ("gizmo.xero_sync", "httpx", "gizmo.orderbook"):
        "the order book uses httpx only to name an error it catches (HTTPStatusError); "
        "the connector settings test reads no order",
    ("gizmo.xero_sync", "httpx", "gizmo.routes.mail"):
        "the inbox's routes use httpx only to name an error they catch (ConnectError); "
        "the connector settings test sends no mail",
    ("gizmo.xero_sync", "httpx", "gizmo.routes.files"):
        "the Finder drive streams downloads from the bucket with its own client; "
        "the connector settings test reaches no file route",
    ("gizmo.xero_sync", "httpx", "gizmo.storefront"):
        "the storefront fetch reads the store's own site with its own client; "
        "the connector settings test reads no page",
    ("gizmo.xero_sync", "httpx", "gizmo.scheduler"):
        "the scheduler sends alert email and watches the connector with its own client; "
        "the connector settings test runs no tick",
}

@test
def t_no_test_patches_a_name_nobody_reads():
    """Three ways a patch in a test can test nothing, each a failure here.

    (a) the module patched does not bind or does not read the name (it moved);
    (b) another module copied the name with `from m import name`, so the patch
        never reaches the copy (a copy is allowed only of a name no test
        patches and no `global` rebinds);
    (c) another of the server's own modules (server, copilot, gizmo.*) keeps a
        copy of its own and reads it, and the test does not patch that one
        too (or SHARED_COPIES says why it need not).
    A name counts as read when its module reads it, or another module reads
    it through the module's name (`google_mail.send_message`)."""
    mods = _app_module_files()
    facts = {m: _module_facts(f) for m, f in mods.items()}
    read_through = {pair for fx in facts.values() for pair in fx["elsewhere"]}
    patches = _test_patches()
    ok(len(patches) > 500, f"the scan finds the suite's patches ({len(patches)})")
    patched = {(m, n) for m, n, *_ in patches}
    bad = []
    for m, n, f, line, top in patches:
        if n not in facts[m]["binds"]:
            bad.append(f"{f}:{line} sets {m}.{n}, which {m} does not bind")
        elif n not in facts[m]["reads"] and (m, n) not in read_through:
            bad.append(f"{f}:{line} sets {m}.{n}, which nothing reads")
    for m, fx in facts.items():
        for frm, n, line in fx["copies"]:
            if frm in mods and ((frm, n) in patched or n in facts[frm]["rebound"]):
                bad.append(f"{mods[m]}:{line} copies {n} from {frm}, which a test patches or a global rebinds there")
    by_top = {}
    for m, n, f, line, top in patches:
        by_top.setdefault((f, top), set()).add((m, n))
    # (c) among the server's own modules, where code moves between files:
    # server.py, copilot.py and the modules split out of copilot.py. The
    # integration modules each keep their own client (httpx) by design.
    own = {"server", "copilot"} | {m for m in mods if m.startswith("gizmo.")}
    for m, n, f, line, top in patches:
        if m not in own:
            continue
        for o, fx in facts.items():
            if o == m or o not in own or n not in fx["binds"] or n not in fx["reads"]:
                continue
            if (o, n) in by_top.get((f, top), set()) or (m, n, o) in SHARED_COPIES:
                continue
            bad.append(f"{f}:{line} sets {m}.{n} but {o} reads its own {n}")
    eq(sorted(set(bad)), [], "patches that would test nothing")

@test
def t_nothing_reads_copilot_py_by_name():
    """Only tools/sources.py names copilot.py's file: the rest read the code
    through it, so a check still sees code that moved out into gizmo/."""
    import ast as _ast, glob as _glob
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    name = "copilot" + ".py"
    found = []
    for path in sorted(_glob.glob(os.path.join(root, "tests", "**", "*.py"), recursive=True)
                       + _glob.glob(os.path.join(root, "tools", "*.py"))):
        rel = os.path.relpath(path, root)
        if rel == os.path.join("tools", "sources.py"):
            continue
        for x in _ast.walk(_ast.parse(open(path, encoding="utf-8").read())):
            if (isinstance(x, _ast.Constant) and isinstance(x.value, str)
                    and re.fullmatch(r"[\w./-]*" + re.escape(name), x.value)):
                found.append(f"{rel}:{x.lineno}")
            # inspect.getsource(copilot): the module's file, read by another road
            if (isinstance(x, _ast.Call) and _ast.unparse(x.func).endswith("getsource") and x.args
                    and isinstance(x.args[0], _ast.Name) and x.args[0].id in ("copilot", "_c", "_cp")):
                found.append(f"{rel}:{x.lineno}")
            # open(copilot.__file__): the same file opened by its path (its folder is fine)
            if (isinstance(x, _ast.Call) and _ast.unparse(x.func).endswith("open") and x.args
                    and isinstance(x.args[0], _ast.Attribute) and x.args[0].attr == "__file__"
                    and isinstance(x.args[0].value, _ast.Name) and x.args[0].value.id in ("copilot", "_c", "_cp")):
                found.append(f"{rel}:{x.lineno}")
    eq(found, [], "reads " + name + " by name; use tools/sources.py")

@test
def t_the_security_scans_cover_every_app_module():
    """The Makefile's and CI's bandit runs name every module of the app, so a
    module split out of copilot.py is scanned like the rest."""
    from tools import sources
    root = sources.ROOT
    make = open(os.path.join(root, "Makefile"), encoding="utf-8").read()
    ci = open(os.path.join(root, ".github", "workflows", "tests.yml"), encoding="utf-8").read()
    lists = {"Makefile": re.search(r"^SAST_FILES\s*=\s*(.+)$", make, re.M).group(1).split(),
             "CI": [w for w in re.search(r"bandit -q[^\n]*", ci).group(0).split()[1:] if not w.startswith("-")]}
    for where, paths in lists.items():
        missing = [m for m in sources.APP_MODULES
                   if not any(m == p or m.startswith(p.rstrip("/") + "/") for p in paths)]
        eq(missing, [], where + "'s security scan leaves out")

