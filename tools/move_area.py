#!/usr/bin/env python3
"""Move an area out of copilot.py into the gizmo package, from a description.

    python tools/move_area.py tools/moves/<name>.json [--repo ROOT] [--write]

Stage 4 of the 14 October audit splits copilot.py one area at a time. The
description (tools/moves/README.md) names each area's module, alias and name
prefixes, and each route group's paths. This prints what would move and what
stops it, and with --write, when nothing stops it, writes the move:

- every top-level statement whose names all belong to an area moves whole,
  with the comments above it, in its order; a banner stays unless its whole
  section moves; a module-level call moves with the area whose names it uses;
  a statement binding two areas' names stops the move;
- each global read, found with symtable (annotations included), is written so
  it still reaches the same object: bare in its own module, alias.NAME for
  another area of this move, owner.NAME for a name copilot.py copies from an
  earlier area, core.NAME for what stays in copilot.py (a floor area may not),
  and an imported name brings its import;
- a `global` line in copilot.py naming only moved names goes, and the writes
  go through the module (shown to make move-proof as a declared change);
- a route group's routes, scattered through add_routes, are gathered into one
  register(mcp, registry) where the first stood (make move-proof checks no
  request changes hands), with the helpers named for them; its area is one of
  this move's, or one moved earlier;
- an alias that is a local name where it would be read, in the app or the
  tests, stops the move; so does __file__ unless the area allows it;
- the modules split out earlier, server.py, the tests and the browser seeds
  are re-pointed, and the suite's prelude imports the new modules.

Imports nothing from the app. Its test: t_move_area_moves_a_toy_area.
"""
import argparse
import ast
import builtins
import collections
import glob
import json
import os
import re
import symtable
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources  # noqa: E402  (copilot.py and the modules split out of it)

BANNER = re.compile(r"^# -{20,}\s*$")
DUNDERS = {"__file__", "__name__", "__doc__", "__spec__"}
OWN = {"logger"}


def _is_doc(n):
    """A docstring: a statement that is only a string."""
    return isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)


def _start(n):
    return min([n.lineno] + [d.lineno for d in getattr(n, "decorator_list", [])])


def _binds(n):
    out = set()
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        out.add(n.name)
    elif isinstance(n, (ast.Import, ast.ImportFrom)):
        out |= {(a.asname or a.name).split(".")[0] for a in n.names}
    elif isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
            out |= {x.id for x in ast.walk(t) if isinstance(x, ast.Name)}
    elif isinstance(n, (ast.If, ast.Try)):
        for x in ast.walk(n):
            if isinstance(x, (ast.Import, ast.ImportFrom, ast.Assign, ast.FunctionDef, ast.ClassDef)):
                out |= _binds(x)
    return out


def _route_path(n):
    for d in getattr(n, "decorator_list", []):
        if isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "custom_route":
            return d.args[0].value
    return None


def _col(lines, lineno, col):
    return len(lines[lineno - 1].encode("utf-8")[:col].decode("utf-8"))


def _child_index(t):
    idx = collections.defaultdict(list)
    for c in t.get_children():
        idx[(c.get_name(), c.get_lineno())].append(c)
    return idx


class _Resolver(ast.NodeVisitor):
    """Calls on_global(node, table) for every Name that resolves to a module
    global, annotations included; on_global_stmt for each `global`; on_free
    for a name taken from an enclosing function."""

    def __init__(self, st, on_global, on_global_stmt, on_free, problems):
        self.st, self.on_global, self.on_global_stmt, self.on_free = st, on_global, on_global_stmt, on_free
        self.problems = problems
        self.stack, self.idx, self.comp = [st], [_child_index(st)], [set()]

    def _enter(self, key):
        lst = self.idx[-1].get(key)
        return lst.pop(0) if lst else None

    def _kind(self, name):
        if any(name in c for c in self.comp):
            return "local"
        t = self.stack[-1]
        if t is self.st:
            return "global"
        try:
            s = t.lookup(name)
        except KeyError:
            return "global"
        return "global" if s.is_global() else ("free" if s.is_free() else "local")

    def visit_Name(self, node):
        k = self._kind(node.id)
        if k == "global":
            # read as the module loads: at the top level, in a top-level class
            # body, or a comprehension there (a default value counts: it is
            # visited in the enclosing scope)
            loading = all(s is self.st or s.get_type() == "class"
                          or s.get_name() in ("listcomp", "setcomp", "dictcomp", "genexpr") for s in self.stack)
            self.on_global(node, self.stack[-1], loading)
        elif k == "free":
            self.on_free(node)

    def visit_Global(self, node):
        self.on_global_stmt(node)

    def _ann(self, a):
        for x in ast.walk(a):
            if isinstance(x, ast.Name):
                self.on_global(x, None, False)

    def _func(self, node, name):
        for d in getattr(node, "decorator_list", []):
            self.visit(d)
        args = node.args
        for d in args.defaults + [x for x in args.kw_defaults if x is not None]:
            self.visit(d)
        for a in args.args + args.posonlyargs + args.kwonlyargs + [x for x in (args.vararg, args.kwarg) if x]:
            if a.annotation is not None:
                self._ann(a.annotation)
        if getattr(node, "returns", None) is not None:
            self._ann(node.returns)
        t = self._enter((name, node.lineno))
        if t is None:
            self.problems.append(f"no symtable for {name} at {node.lineno}")
            return
        self.stack.append(t); self.idx.append(_child_index(t)); self.comp.append(set())
        for s in (node.body if isinstance(node.body, list) else [node.body]):
            self.visit(s)
        self.stack.pop(); self.idx.pop(); self.comp.pop()

    def visit_FunctionDef(self, node):
        self._func(node, node.name)
    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node):
        self._func(node, "lambda")

    def visit_AnnAssign(self, node):
        if self.stack[-1] is self.st:
            self._ann(node.annotation)
        if node.value is not None:
            self.visit(node.value)
        self.visit(node.target)

    def visit_ClassDef(self, node):
        for d in node.decorator_list + node.bases + [k.value for k in node.keywords]:
            self.visit(d)
        t = self._enter((node.name, node.lineno))
        if t is None:
            self.problems.append(f"no symtable for class {node.name}")
            return
        self.stack.append(t); self.idx.append(_child_index(t)); self.comp.append(set())
        for s in node.body:
            if isinstance(s, ast.AnnAssign):
                self._ann(s.annotation)
                if s.value is not None:
                    self.visit(s.value)
            else:
                self.visit(s)
        self.stack.pop(); self.idx.pop(); self.comp.pop()

    def _comp(self, node, kind):
        gens = node.generators
        self.visit(gens[0].iter)
        t = self._enter((kind, node.lineno))
        targets = {x.id for g in gens for x in ast.walk(g.target) if isinstance(x, ast.Name)}
        if t is not None:
            self.stack.append(t); self.idx.append(_child_index(t))
        self.comp.append(targets)
        for i, g in enumerate(gens):
            if i:
                self.visit(g.iter)
            for c in g.ifs:
                self.visit(c)
        for f in ("elt", "key", "value"):
            if getattr(node, f, None) is not None:
                self.visit(getattr(node, f))
        self.comp.pop()
        if t is not None:
            self.stack.pop(); self.idx.pop()

    def visit_ListComp(self, node): self._comp(node, "listcomp")
    def visit_SetComp(self, node): self._comp(node, "setcomp")
    def visit_DictComp(self, node): self._comp(node, "dictcomp")
    def visit_GeneratorExp(self, node): self._comp(node, "genexpr")


def _locals_named(st, name):
    """(function, line) of every function scope where `name` is a local."""
    out = []
    def walk(t):
        try:
            if t is not st and t.lookup(name).is_local():
                out.append((t.get_name(), t.get_lineno()))
        except KeyError:
            pass
        for c in t.get_children():
            walk(c)
    walk(st)
    return out


def _is_floor(root, rel):
    """A split module is floor when nothing in it imports copilot."""
    tree = ast.parse(open(os.path.join(root, rel), encoding="utf-8").read())
    return not any(isinstance(x, ast.Import) and any(a.name == "copilot" for a in x.names) for x in ast.walk(tree))


def run(spec_path, root, write):
    """Plan the move, and write it when nothing stops it. -> (exit code, report lines)."""
    spec = json.load(open(spec_path, encoding="utf-8"))
    report, problems, notes = [], [], []
    P = lambda rel: os.path.join(root, rel)
    MAIN = sources.copilot_files(root)[0]     # copilot.py, named in one place
    src = open(P(MAIN), encoding="utf-8").read()
    LINES = src.splitlines(keepends=True)
    tree = ast.parse(src)
    st = symtable.symtable(src, MAIN, "exec")
    areas = {a["name"]: a for a in spec["areas"]}
    AL = {n: a.get("alias", n) for n, a in areas.items()}
    groups = {g["name"]: g for g in spec.get("routes", [])}
    keep_copies = set(spec.get("copies", []))

    # copilot's imports: what an imported name needs, the split modules it
    # binds (alias -> module), and the names it copies from an area
    IMPORTS, mod_alias, copy_owner = {}, {}, {}
    split_files = sources.copilot_files(root)[1:]
    floor_mods = {f[:-3].replace("/", ".") for f in split_files if _is_floor(root, f)}
    for n in tree.body:
        nodes = [n] if isinstance(n, (ast.Import, ast.ImportFrom)) else \
            [x for x in ast.walk(n) if isinstance(x, (ast.Import, ast.ImportFrom))] if isinstance(n, ast.Try) else []
        for x in nodes:
            for al in x.names:
                IMPORTS[(al.asname or al.name).split(".")[0]] = (n, x)
            if isinstance(x, ast.ImportFrom) and x.module and x.module.startswith("gizmo"):
                for al in x.names:
                    full = f"{x.module}.{al.name}"
                    if os.path.exists(P(full.replace(".", "/") + ".py")):
                        mod_alias[al.asname or al.name] = full
    for n in tree.body:
        if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith("gizmo.") and n.module not in floor_mods:
            owner = next((a for a, m in mod_alias.items() if m == n.module), None)
            for al in n.names:
                if f"{n.module}.{al.name}" in mod_alias.values():
                    continue
                if owner is None:
                    problems.append(f"copilot.py copies {al.name} from {n.module} but binds no name for the module")
                else:
                    copy_owner[al.asname or al.name] = owner
    area_aliases = {a for a, m in mod_alias.items() if m not in floor_mods}
    # an area marked existing moved in an earlier piece: what moves here is
    # added to its file, which copilot.py already binds by the same name
    EXISTING = {d for d, a in areas.items() if a.get("existing")}
    BIND = set()                      # existing areas copilot.py does not bind by name yet
    for d in sorted(EXISTING):
        mod = areas[d]["file"][:-3].replace("/", ".")
        if not os.path.exists(P(areas[d]["file"])):
            problems.append(f"existing area {d}: no file {areas[d]['file']}")
        elif mod_alias.get(AL[d]) != mod:
            if AL[d] in IMPORTS or AL[d] in {b for n in tree.body for b in _binds(n)}:
                problems.append(f"existing area {d}: copilot.py binds {AL[d]} to something else")
            else:
                BIND.add(d)           # bound by this move, in copilot.py and the suite
        if mod in floor_mods:
            areas[d]["floor"] = True
    imports = set(IMPORTS)
    for g, gd in groups.items():
        # a group's area is one of this move's, or one moved earlier that copilot.py binds
        if gd["area"] not in areas and gd["area"] not in mod_alias:
            problems.append(f"route group {g}: no area {gd['area']} in this move or bound in copilot.py")
        # an existing group adds to a route module moved earlier, which copilot.py binds as g
        if gd.get("existing") and mod_alias.get(g) != gd["file"][:-3].replace("/", "."):
            problems.append(f"existing route group {g}: copilot.py binds no {g} for {gd['file']}")

    # what moves where
    DEST = {}
    for n in tree.body:
        for b in _binds(n) - imports:
            for name, a in areas.items():
                if (re.match(a.get("prefix", "(?!)"), b) or b in a.get("extra", [])) and b not in a.get("exclude", []):
                    DEST.setdefault(b, name)
    stmts, prev = [], 0
    for n in tree.body:
        b = _binds(n) - imports if not isinstance(n, (ast.Import, ast.ImportFrom)) else set()
        kind = "stay"
        if b:
            ds = {DEST.get(x) for x in b}
            if None not in ds and len(ds) == 1:
                kind = ds.pop()
            elif ds - {None}:
                problems.append(f"the statement at {n.lineno} binds {sorted(b)} across areas {sorted(map(str, ds))}")
        elif isinstance(n, ast.Expr):
            used = {y.id for y in ast.walk(n) if isinstance(y, ast.Name)} - imports
            ds = {DEST.get(x) for x in used}
            if used and None not in ds and len(ds) == 1:
                kind = ds.pop()
                notes.append(f"the call at {n.lineno} moves with {kind}: {ast.unparse(n)[:60]}")
        stmts.append([n, prev + 1, n.end_lineno, kind])
        prev = n.end_lineno
    moved = set(DEST)
    staying = {x for n, a, b, k in stmts if k == "stay" for x in _binds(n)} - imports

    # route groups
    AR = next((n for n, a, b, k in stmts if isinstance(n, ast.FunctionDef) and n.name == "add_routes"), None)
    group_spans = {g: [] for g in groups}
    route_line = {}
    if AR is not None:
        prev_s = None
        for s_ in AR.body:
            a_ = (prev_s.end_lineno + 1) if prev_s is not None else _start(s_)
            p_ = _route_path(s_)
            for g, gd in groups.items():
                # a path is a prefix, or with "=" before it that path alone
                # (the page's own "/" is the prefix of every route)
                hit = p_ and any(p_ == x[1:] if x.startswith("=") else p_.startswith(x) for x in gd["paths"])
                helper = isinstance(s_, (ast.FunctionDef, ast.AsyncFunctionDef)) and s_.name in gd.get("helpers", [])
                if hit or helper:
                    group_spans[g].append((a_, s_.end_lineno, s_))
            prev_s = s_
        for g, spans in group_spans.items():
            for a_, b_, _ in spans:
                route_line.update({ln: g for ln in range(a_, b_ + 1)})
    # every name add_routes binds as it runs (its parameters, nested
    # functions and the values it assigns): a route moved out cannot read one
    ar_table = next((c for c in st.get_children() if c.get_name() == "add_routes" and c.get_type() == "function"), None)
    ar_locals = {s.get_name() for s in ar_table.get_symbols() if s.is_local()} if ar_table else set()

    def where(line):
        if line in route_line:
            return route_line[line]
        for n, a, b, k in stmts:
            if a <= line <= b:
                return k
        return "stay"

    def owner_area(w):
        return groups[w]["area"] if w in groups else w

    edits = collections.defaultdict(list)
    # who reads each staying name: what stays, or what moves (to list a name
    # left behind though only what moves reads it, as _add_skill once was)
    stay_binds = {ln: _binds(n) for n, a, b, k in stmts if k == "stay" for ln in range(a, b + 1)}
    stay_readers = collections.defaultdict(set)
    imports_used = collections.defaultdict(set)
    sibs = collections.defaultdict(set)
    early = collections.defaultdict(set)   # what an area reads as it loads: imported at its top
    borrowed = collections.defaultdict(set)
    drop_lines, crossing = set(), set()

    def edit(node, text):
        if node.lineno != node.end_lineno:
            problems.append(f"a name over two lines at {node.lineno}")
        edits[node.lineno].append((_col(LINES, node.lineno, node.col_offset), _col(LINES, node.lineno, node.end_col_offset), text))

    def on_global(node, table, loading=False):
        w, name = where(node.lineno), node.id
        if w == "stay":
            if name in staying and name not in stay_binds.get(node.lineno, ()):
                stay_readers[name] |= {"stay:" + b for b in stay_binds.get(node.lineno, ())} or {"stay:"}
            if name in moved and name not in keep_copies:
                edit(node, AL[DEST[name]] + "." + name)
                if not isinstance(node.ctx, ast.Load) and (node.lineno, name) not in crossing and name not in {n for _, n in crossing}:
                    problems.append(f"{node.lineno}: copilot.py assigns {name}, which moves")
            return
        if name in OWN or name in DUNDERS - {"__file__"}:
            return
        if name == "__file__":
            if areas.get(owner_area(w), {}).get("allow_file"):
                notes.append(f"{node.lineno}: {w} builds a path from __file__ (allowed by the description)")
            else:
                problems.append(f"{node.lineno}: {w} builds a path from __file__, which points into gizmo/ once moved")
            return
        if w in EXISTING and name == AL[w]:
            # the module's own name, inside it: orderbook._orders_snapshot is
            # _orders_snapshot once the code lives in orderbook
            c0, c1 = _col(LINES, node.lineno, node.col_offset), _col(LINES, node.lineno, node.end_col_offset)
            if LINES[node.lineno - 1][c1:c1 + 1] == ".":
                edits[node.lineno].append((c0, c1 + 1, ""))
            else:
                problems.append(f"{node.lineno}: {w} uses its own module {name} as a value")
            return
        if name in moved:
            d = DEST[name]
            if d != w:
                edit(node, AL[d] + "." + name); sibs[w].add(d)
                if loading and w in areas:
                    early[w].add(d)
                if not isinstance(node.ctx, ast.Load):
                    problems.append(f"{node.lineno}: {w} assigns {d}'s {name}")
            return
        if name in copy_owner and w in EXISTING and copy_owner[name] == AL[w]:
            return                    # a name copilot.py copied from the module it now lives in
        if name in copy_owner:
            edit(node, copy_owner[name] + "." + name); sibs[w].add("mod:" + copy_owner[name])
            if loading and w in areas:
                early[w].add("mod:" + copy_owner[name])
            return
        if name in area_aliases:
            sibs[w].add("mod:" + name)
            if loading and w in areas:
                early[w].add("mod:" + name)
            return
        if name in imports:
            imports_used[w].add(name); return
        if name in staying:
            if areas.get(owner_area(w), {}).get("floor"):
                problems.append(f"{node.lineno}: floor area {w} would read copilot.py's {name}")
            edit(node, "core." + name); borrowed[w].add(name); stay_readers[name].add(w)
            if loading and w not in groups:
                problems.append(f"{node.lineno}: {w} reads core.{name} as it loads")
            if not isinstance(node.ctx, ast.Load):
                problems.append(f"{node.lineno}: {w} assigns copilot.py's {name}")
            return
        if not hasattr(builtins, name):
            problems.append(f"{node.lineno}: {w} reads {name}, bound nowhere")

    def on_global_stmt(node):
        w = where(node.lineno)
        cross = [n for n in node.names if (w == "stay" or w in groups) and n in moved
                 or (w in areas and (n not in moved or DEST[n] != w))]
        if not cross:
            return
        if len(cross) == len(node.names) and node.lineno == node.end_lineno and all(n in moved for n in cross) \
                and LINES[node.lineno - 1].strip() == ast.unparse(node):
            drop_lines.add(node.lineno)
            crossing.update((node.lineno, n) for n in cross)
            notes.append(f"{node.lineno}: `global {', '.join(cross)}` goes; the writes go through the module ({w})")
        else:
            problems.append(f"{node.lineno}: `global {', '.join(cross)}` crosses the line ({w})")

    def on_free(node):
        w = where(node.lineno)
        if w in groups and node.id in ar_locals and node.id not in ("mcp", "registry") \
                and node.id not in groups[w].get("helpers", []):
            problems.append(f"{node.lineno}: a {w} route reads add_routes' {node.id}")

    _Resolver(st, on_global, on_global_stmt, on_free, problems).visit(tree)

    # an alias that is a local where it would be read: in copilot.py
    for alias in list(AL.values()) + ["core"]:
        for fn, ln in _locals_named(st, alias):
            node = next((x for x in ast.walk(tree) if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))
                         and x.name == fn and x.lineno == ln), None)
            if node and any(node.lineno <= l <= node.end_lineno and any(t.startswith(alias + ".") for _, _, t in edits[l])
                            for l in edits):
                problems.append(f"{fn} at {ln} has a local `{alias}` and would read a moved name through it")

    # the other files: core.NAME / copilot.NAME for a moved name
    def attr_edits(rel, owners, through=False, own=None):
        text = open(P(rel), encoding="utf-8").read()
        lines = text.splitlines(keepends=True)
        t = ast.parse(text)
        ed = collections.defaultdict(list); used = set()
        for x in ast.walk(t):
            # getattr/setattr/hasattr(copilot, "NAME", ...): the module named by its string
            if (isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id in ("getattr", "setattr", "hasattr")
                    and len(x.args) >= 2 and isinstance(x.args[0], ast.Name) and x.args[0].id in owners
                    and isinstance(x.args[1], ast.Constant) and x.args[1].value in moved and not through):
                if own is not None and DEST[x.args[1].value] == own:
                    problems.append(f"{rel}:{x.lineno} reaches {x.args[1].value} by its string through copilot, and it moves into this module")
                    continue
                a0 = x.args[0]
                ed[a0.lineno].append((_col(lines, a0.lineno, a0.col_offset), _col(lines, a0.lineno, a0.end_col_offset),
                                      AL[DEST[x.args[1].value]]))
                used.add(DEST[x.args[1].value])
            if (isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name) and x.value.id in owners
                    and x.attr in moved and x.attr not in keep_copies):
                if own is not None and DEST[x.attr] == own:
                    # the module's own core.NAME read of a name moving into it: bare
                    ed[x.lineno].append((_col(lines, x.lineno, x.col_offset), _col(lines, x.lineno, x.end_col_offset), x.attr))
                    continue
                new = (x.value.id + "." if through else "") + AL[DEST[x.attr]] + "." + x.attr
                ed[x.lineno].append((_col(lines, x.lineno, x.col_offset), _col(lines, x.lineno, x.end_col_offset), new))
                used.add(DEST[x.attr])
        if ed:
            # a function with a local named like an alias it would now read through
            tst = symtable.symtable(text, rel, "exec")
            for d in used:
                for fn, ln in _locals_named(tst, AL[d]):
                    node = next((x for x in ast.walk(t) if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))
                                 and x.name == fn and x.lineno == ln), None)
                    if node and any(node.lineno <= l <= node.end_lineno for l in ed):
                        problems.append(f"{rel}: {fn} at {ln} has a local `{AL[d]}` and would read a moved name through it")
        out = []
        for i, line in enumerate(lines, 1):
            for c0, c1, txt in sorted(ed.get(i, []), reverse=True):
                line = line[:c0] + txt + line[c1:]
            out.append(line)
        return "".join(out), used, sum(len(v) for v in ed.values())

    others = {}
    own_of = {areas[d]["file"]: d for d in EXISTING}
    for rel in split_files:
        if rel in {a["file"] for a in spec["areas"] if not a.get("existing")} | {g["file"] for g in spec.get("routes", []) if not g.get("existing")}:
            continue
        others[rel] = attr_edits(rel, {"core"}, own=own_of.get(rel))
    if os.path.exists(P("server.py")):
        # server.py imports copilot inside its functions (as _c): it reaches a
        # moved name through copilot.py's own name for the module.
        stree = ast.parse(open(P("server.py"), encoding="utf-8").read())
        server_aliases = {a.asname or a.name for x in ast.walk(stree) if isinstance(x, ast.Import)
                          for a in x.names if a.name == "copilot"}
        others["server.py"] = attr_edits("server.py", server_aliases, through=True)
    for f in sorted(glob.glob(P("tests/**/*.py"), recursive=True)):
        others[os.path.relpath(f, root)] = attr_edits(os.path.relpath(f, root), {"copilot", "_c", "_cp"})

    for d in areas:
        report.append(f"{d}: {sum(1 for s in stmts if s[3] == d)} statements; borrows {sorted(borrowed[d])}")
        for x in sorted(early[d]):
            if not (x.startswith("mod:") and mod_alias[x[4:]] in floor_mods):
                notes.append(f"{d} reads {x.removeprefix('mod:')} as it loads, so imports it at the top")
    for g in groups:
        report.append(f"{g}: {sum(1 for _, _, n in group_spans[g] if _route_path(n))} routes in {len(group_spans[g])} statements")
    report.append("other files: " + str({r: n for r, (_, _, n) in others.items() if n}))
    # a staying name only what moves reads, and no other module or server.py
    elsewhere = "".join(open(P(r), encoding="utf-8").read() for r in list(split_files) + ["server.py"]
                        if os.path.exists(P(r)) and r not in {a["file"] for a in spec["areas"] if not a.get("existing")})
    # ... or only such names: a helper of a helper left behind
    left = set()
    while True:
        more = {name for name in stay_readers if name not in left
                and all(not r.startswith("stay:") or r[5:] in left for r in stay_readers[name])
                and not re.search(r"\b(core|copilot|_c|_cp)\." + re.escape(name) + r"\b", elsewhere)}
        if not more:
            break
        left |= more
    for name in sorted(left):
        notes.append(f"{name} stays, though only what moves reads it "
                     f"({', '.join(sorted(r[5:] if r.startswith('stay:') else r for r in stay_readers[name]))})")
    report += ["note: " + x for x in notes] + ["PROBLEM: " + x for x in problems]
    if problems or not write:
        return (1 if problems else 0), report

    # ---- write
    def apply(lineno):
        if lineno in drop_lines:
            return ""
        line = LINES[lineno - 1]
        for c0, c1, t in sorted(edits.get(lineno, []), reverse=True):
            line = line[:c0] + t + line[c1:]
        return line

    banner_lines = [i + 1 for i, l in enumerate(LINES) if BANNER.match(l)]
    def section_of(line):
        s = [l for l in banner_lines if l <= line]
        return s[-1] if s else 0
    sections = collections.defaultdict(list)
    for s_ in stmts:
        sections[section_of(_start(s_[0]))].append(s_[3])

    moved_text, stay_lines = collections.defaultdict(list), set()
    for s_ in stmts:
        n, a, b, k = s_
        if k == "stay":
            stay_lines.update(range(a, b + 1))
            continue
        gap = list(range(a, _start(n)))
        last = max([l for l in gap if BANNER.match(LINES[l - 1])], default=None)
        if last is not None and not all(x == k for x in sections[section_of(_start(n))]):
            stay_lines.update(l for l in gap if l <= last)
            gap = [l for l in gap if l > last]
        moved_text[k].append("".join(apply(l) for l in gap + list(range(_start(n), b + 1))))

    def import_block(names):
        need = {}
        for name in sorted(names):
            topn, imp = IMPORTS[name]
            need.setdefault(topn.lineno, (topn, set()))[1].add(name)
        out = []
        for _, (topn, ns) in sorted(need.items()):
            if isinstance(topn, ast.Try):
                out.append("".join(LINES[topn.lineno - 1:topn.end_lineno]).rstrip("\n"))
            elif isinstance(topn, ast.Import):
                keep = [a for a in topn.names if (a.asname or a.name).split(".")[0] in ns]
                out.append("import " + ", ".join(a.name + (" as " + a.asname if a.asname else "") for a in keep))
            else:
                keep = [a for a in topn.names if (a.asname or a.name) in ns]
                out.append("from %s import %s" % (topn.module, ", ".join(a.name + (" as " + a.asname if a.asname else "") for a in keep)))
        return "\n".join(out)

    def sib_line(x):
        if x.startswith("mod:"):
            alias = x[4:]
            mod = mod_alias[alias]
            pkg, _, leaf = mod.rpartition(".")
            return f"from {pkg} import {leaf}" + (f" as {alias}" if alias != leaf else "")
        leaf = areas[x]["file"][:-3].replace("/", ".").rpartition(".")[2]
        return f"from gizmo import {leaf}" + (f" as {AL[x]}" if AL[x] != leaf else "")

    def doc(text):
        q = '"' * 3
        return q + "\n".join(textwrap.wrap(text, 76)) + "\n" + q + "\n"

    logger_line = ("\n# The same logger as copilot.py's, so these log lines read as before.\n"
                   + next(("".join(LINES[n.lineno - 1:n.end_lineno]).rstrip("\n") for n, a, b, k in stmts
                           if "logger" in _binds(n)), "logger = None") + "\n\n\n")
    tail_note = ("\n\n# Last, so this module is whole before copilot.py or a sibling runs: copilot.py\n"
                 "# takes names from these modules as it loads, and any of them may be imported\n"
                 "# first. Read as core.NAME and sibling.NAME, never a copied name.\n")
    for d, a in areas.items():
        if d in EXISTING:
            continue                  # added to its own file with the other files, below
        top = [x for x in sibs[d] if x.startswith("mod:") and mod_alias[x[4:]] in floor_mods or x in early[d]]
        bottom = sorted(set(sibs[d]) - set(top) - {d})
        head = doc(a["doc"]) + "import logging\n" + import_block(imports_used[d]) + "\n" + "".join(sib_line(x) + "\n" for x in sorted(top))
        if a.get("floor"):
            tail = "".join(sib_line(x) + "\n" for x in bottom)
        else:
            tail = tail_note + "".join(sib_line(x) + "  # noqa: E402\n" for x in bottom) + "import copilot as core  # noqa: E402\n"
        os.makedirs(os.path.dirname(P(a["file"])), exist_ok=True)
        open(P(a["file"]), "w", encoding="utf-8").write(head + logger_line + "".join(moved_text[d]).rstrip("\n") + "\n" + tail)

    for g, gd in groups.items():
        if gd.get("existing"):
            continue                  # added to its own register(), with the other files, below
        body = "".join("".join(apply(l) for l in range(a_, b_ + 1)) for a_, b_, _ in group_spans[g])
        text = (doc(gd["doc"]) + "import logging\n" + import_block(imports_used[g]) + "\n\nimport copilot as core\n"
                + "".join(sib_line(x) + "\n" for x in sorted(sibs[g])) + logger_line
                + "def register(mcp, registry):\n    " + '"' * 3 + gd["register_doc"] + '"' * 3 + "\n" + body.rstrip("\n") + "\n")
        open(P(gd["file"]), "w", encoding="utf-8").write(text)

    first = {g: spans[0][0] for g, spans in group_spans.items() if spans}
    out = []
    for l in range(1, len(LINES) + 1):
        g = route_line.get(l)
        if g:
            if l == first[g] and not groups[g].get("existing"):
                out.append(f"\n    # {groups[g]['comment'] if 'comment' in groups[g] else 'Gathered where the first stood; their paths are literal, so no request changes hands.'}\n"
                           f"    {g}.register(mcp, registry)\n")
            continue
        if l in stay_lines:
            out.append(apply(l))
    after = "".join(out)
    imp_lines = [n for n in ast.parse(after).body if isinstance(n, (ast.Import, ast.ImportFrom))]
    anchor_node = next((n for n in reversed(imp_lines) if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("gizmo")),
                       imp_lines[-1] if imp_lines else None)
    lines_after = after.splitlines(keepends=True)
    at = anchor_node.end_lineno if anchor_node else 0
    add = [f"# Moved out of this file (stage 4): {spec.get('note', '')}.\n"]
    for d, a in areas.items():
        if d not in EXISTING or d in BIND:   # copilot.py binds an existing area already, unless it does not yet
            add.append(sib_line(d) + "\n")
    for g, gd in groups.items():
        if gd.get("existing"):
            continue                  # copilot.py binds it, and add_routes calls it, already
        leaf = gd["file"][:-3].replace("/", ".").rpartition(".")
        add.append(f"from {leaf[0]} import {leaf[2]} as {g}\n")
    for d, a in areas.items():
        ks = sorted(n for n in keep_copies if DEST.get(n) == d)
        if ks:
            add.append(f"from {a['file'][:-3].replace('/', '.')} import {', '.join(ks)}\n")
    lines_after[at:at] = add
    open(P(MAIN), "w", encoding="utf-8").write("".join(lines_after))

    def bound_in(text):
        """The names a module's top-level imports bind."""
        return {(al.asname or al.name).split(".")[0] for x in ast.parse(text).body
                if isinstance(x, (ast.Import, ast.ImportFrom)) for al in x.names}

    def alias_of(x):
        return x[4:] if x.startswith("mod:") else AL[x]

    def add_to_existing(d, text):
        """An existing area's file with what moves into it: the statements
        before its last imports, the imports they need that it lacks."""
        body = ast.parse(text).body
        bound = bound_in(text)
        lines = text.splitlines(keepends=True)
        code = [x for x in body if not isinstance(x, (ast.Import, ast.ImportFrom))]
        last_code = max((x.end_lineno for x in code), default=0)
        moved = "".join(moved_text[d]).strip("\n")
        out = lines[:last_code] + ["\n\n" + moved + "\n"] + lines[last_code:]
        top = [x for x in sibs[d] if x.startswith("mod:") and mod_alias[x[4:]] in floor_mods or x in early[d]]
        bottom = sorted(set(sibs[d]) - set(top) - {d})
        noqa = "" if areas[d].get("floor") else "  # noqa: E402"
        tail = [sib_line(x) + noqa + "\n" for x in bottom if alias_of(x) not in bound]
        if borrowed[d] and "core" not in bound:
            tail.append("import copilot as core" + noqa + "\n")
        if tail:
            if not out[-1].endswith("\n"):
                out[-1] += "\n"
            out += tail
        head = [import_block(sorted(n for n in imports_used[d] if n not in bound))] if imports_used[d] - bound else []
        head += [sib_line(x) for x in sorted(top) if alias_of(x) not in bound]
        first = next((x for x in code if not _is_doc(x)), None)
        tops = [x for x in body if isinstance(x, (ast.Import, ast.ImportFrom)) and (first is None or x.lineno < first.lineno)]
        at = tops[-1].end_lineno if tops else (code[0].end_lineno if code and _is_doc(code[0]) else 0)
        out[at:at] = ["".join(h + "\n" for h in head if h)]
        return "".join(out)

    def add_routes_to_existing(g, text):
        """An existing route module with what moves into it: the routes at the
        end of register(), after those it holds, and the imports they need."""
        body = ast.parse(text).body
        bound = bound_in(text)
        reg = next(x for x in body if isinstance(x, ast.FunctionDef) and x.name == "register")
        lines = text.splitlines(keepends=True)
        moved = "".join("".join(apply(l) for l in range(a_, b_ + 1)) for a_, b_, _ in group_spans[g]).strip("\n")
        out = lines[:reg.end_lineno] + ["\n" + moved + "\n"] + lines[reg.end_lineno:]
        head = [import_block(sorted(n for n in imports_used[g] if n not in bound))] if imports_used[g] - bound else []
        head += [sib_line(x) for x in sorted(sibs[g]) if alias_of(x) not in bound]
        if "core" not in bound:
            head.append("import copilot as core")
        tops = [x for x in body if isinstance(x, (ast.Import, ast.ImportFrom)) and x.lineno < reg.lineno]
        at = tops[-1].end_lineno if tops else 0
        out[at:at] = ["".join(h + "\n" for h in head if h)]
        return "".join(out)

    new_imports = "".join(sib_line(d) + "\n" for d in areas if d not in EXISTING or d in BIND)
    group_of = {gd["file"]: g for g, gd in groups.items() if gd.get("existing")}
    for rel in [areas[d]["file"] for d in EXISTING] + list(group_of):
        if rel not in others:
            others[rel] = (open(P(rel), encoding="utf-8").read(), set(), 0)
    for rel, (text, used, n) in others.items():
        own = own_of.get(rel)
        if not n and own is None and rel not in group_of:
            continue
        if rel.startswith("gizmo/"):
            m = re.search(r"^import copilot as core.*\n", text, re.M)
            noqa = "  # noqa: E402" if m and "noqa" in m.group(0) else ""
            bound = bound_in(text)
            add = "".join(sib_line(d) + noqa + "\n" for d in sorted(used) if d != own and AL[d] not in bound)
            if add:
                text = text[:m.end()] + add + text[m.end():] if m else add + text
            if own is not None:
                text = add_to_existing(own, text)
            if rel in group_of:
                text = add_routes_to_existing(group_of[rel], text)
        elif rel == "server.py":
            pass                      # it reads the moved names through copilot (above)
        elif rel.endswith("test_dispatch.py") and "seed" not in rel:
            # after the prelude's last top-level gizmo import (or its copilot
            # import): found by the parser, so never inside a string
            ttop = [n for n in ast.parse(text).body if isinstance(n, (ast.Import, ast.ImportFrom))]
            last = next((n for n in reversed(ttop) if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("gizmo")),
                        next((n for n in reversed(ttop) if isinstance(n, ast.Import) and any(a.name == "copilot" for a in n.names)), None))
            tl = text.splitlines(keepends=True)
            tl[last.end_lineno:last.end_lineno] = [new_imports]
            text = "".join(tl)
        open(P(rel), "w", encoding="utf-8").write(text)
    report.append("written")
    return 0, report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("spec", help="tools/moves/<name>.json")
    ap.add_argument("--repo", default=sources.ROOT)
    ap.add_argument("--write", action="store_true", help="write the move when nothing stops it")
    args = ap.parse_args(argv)
    code, report = run(args.spec, args.repo, args.write)
    print("\n".join(report))
    return code


if __name__ == "__main__":
    sys.exit(main())
