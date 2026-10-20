#!/usr/bin/env python3
"""The proof that a move out of copilot.py moved code and changed nothing.

    python tools/move_proof.py --base <ref>      (make move-proof BASE=<ref>)

copilot.py is split into the gizmo package one area at a time. A move cuts
statements whole and adds module prefixes: the moved code reads copilot.py as
core.NAME, and copilot.py reads the area as, say, desk.NAME. This compares
the head's copilot.py and package with the base's:

- every statement, top-level or nested in add_routes or an area's register(),
  is found once on the other side with the same syntax tree, reading a prefix
  (a name one of these modules gives another) as the plain name;
- a prefix stands only where the plain name was a module global: never where
  a parameter, a local or a closure of that name is in scope;
- the routes are registered in the same order;
- nothing else is added or lost but imports, the package's module docstrings
  and loggers, and the register() shells and calls that carry the routes;
- no moved statement finds its module's names by name (globals(), vars(),
  sys.modules[__name__]) or a path from its own file (__file__): moved, it
  would read the new module's.

Statements changed on purpose are named with --declared (make move-proof
DECLARED=a,b) and printed before and after instead.

Comments are not compared. Exit 0 with "nothing but the move", or exit 1
naming each statement lost, added or changed. Imports nothing from the app.
"""
import argparse
import ast
import collections
import copy
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources  # noqa: E402  (copilot.py and the modules split out of it)

_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_COMPS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _module(path):
    return path[:-3].replace("/", ".")


def _aliases(tree, family):
    """The names a module binds at its top level to another of the family."""
    out = {}
    for n in tree.body:
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name in family:
                    out[a.asname or a.name] = a.name
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            for a in n.names:
                if f"{n.module}.{a.name}" in family:
                    out[a.asname or a.name] = f"{n.module}.{a.name}"
    return out


def _own_names(fn):
    """Names a function (or lambda) binds in its own scope: parameters,
    assignments, loop, with and except targets, imports, nested def and class
    names; less those it declares global or nonlocal."""
    a = fn.args
    names = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
    names |= {x.arg for x in (a.vararg, a.kwarg) if x}
    declared = set()
    todo = list(fn.body) if isinstance(fn.body, list) else [fn.body]
    while todo:
        n = todo.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(n.name)
            todo.extend(n.decorator_list)
            todo.extend(n.bases if isinstance(n, ast.ClassDef)
                        else n.args.defaults + [d for d in n.args.kw_defaults if d])
            continue
        if isinstance(n, ast.Lambda):
            todo.extend(n.args.defaults)
            continue
        if isinstance(n, _COMPS):
            for g in n.generators:
                todo.append(g.iter)
                todo.extend(g.ifs)
            todo.extend(getattr(n, f) for f in ("elt", "key", "value") if getattr(n, f, None) is not None)
            continue
        if isinstance(n, (ast.Global, ast.Nonlocal)):
            declared |= set(n.names)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            names.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            names |= {(x.asname or x.name).split(".")[0] for x in n.names}
        elif isinstance(n, ast.ExceptHandler) and n.name:
            names.add(n.name)
        todo.extend(ast.iter_child_nodes(n))
    return names - declared


def _targets(comp):
    return {x.id for g in comp.generators for x in ast.walk(g.target) if isinstance(x, ast.Name)}


def _norm(node, prefixes, local, problems, label):
    """A copy of node with each prefix.NAME read as NAME, where the prefix is
    the module's and not a local of that name; a prefix put on a name that is
    local where it stands goes to problems."""
    if isinstance(node, list):
        return [_norm(x, prefixes, local, problems, label) for x in node]
    if not isinstance(node, ast.AST):
        return node
    if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
            and node.value.id in prefixes and node.value.id not in local):
        if node.attr in local:
            problems.append(f"{label}: {node.value.id}.{node.attr} where {node.attr} is a parameter, "
                            "a local or a closure, not a module global")
        return ast.Name(id=node.attr, ctx=node.ctx)
    out = copy.copy(node)
    if isinstance(node, _SCOPES):
        inner = local | _own_names(node)
        for f in node._fields:
            setattr(out, f, _norm(getattr(node, f), prefixes, inner if f == "body" else local, problems, label))
        return out
    if isinstance(node, _COMPS):
        inner = local | _targets(node)
        gens = []
        for i, g in enumerate(node.generators):
            g2 = copy.copy(g)
            g2.iter = _norm(g.iter, prefixes, inner if i else local, problems, label)
            g2.target = _norm(g.target, prefixes, inner, problems, label)
            g2.ifs = _norm(g.ifs, prefixes, inner, problems, label)
            gens.append(g2)
        out.generators = gens
        for f in ("elt", "key", "value"):
            if getattr(node, f, None) is not None:
                setattr(out, f, _norm(getattr(node, f), prefixes, inner, problems, label))
        return out
    for f in node._fields:
        setattr(out, f, _norm(getattr(node, f), prefixes, local, problems, label))
    return out


def _label(path, n):
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return f"{path}:{n.lineno} def {n.name}"
    if isinstance(n, ast.ClassDef):
        return f"{path}:{n.lineno} class {n.name}"
    return f"{path}:{n.lineno} {ast.unparse(n).splitlines()[0][:70]}"


def _name(n):
    """What a statement is called, for naming it as an intended change: a def
    or class name, an assignment's first target, or the function an
    expression statement calls."""
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return n.name
    if isinstance(n, (ast.Assign, ast.AnnAssign)):
        t = n.targets[0] if isinstance(n, ast.Assign) else n.target
        return ast.unparse(t)
    if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call):
        f = n.value.func
        return f.attr if isinstance(f, ast.Attribute) else ast.unparse(f)
    if isinstance(n, ast.Global):
        return "global"          # a global line that went, its writes now through the module
    return None


def _looks_itself_up(n):
    """A statement that finds its module's names by name: globals(), vars()
    with nothing given, sys.modules[__name__]. Moved, it reads the new module."""
    for x in ast.walk(n):
        if (isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
                and (x.func.id == "globals" or (x.func.id == "vars" and not x.args))):
            return x.func.id + "()"
        if isinstance(x, ast.Subscript) and ast.unparse(x) == "sys.modules[__name__]":
            return "sys.modules[__name__]"
        if isinstance(x, ast.Name) and x.id in ("__file__", "__name__"):
            return x.id             # a path or name found from the module's own file
    return None


def _is_doc(n):
    return isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)


def _is_register_call(n, prefixes):
    return (isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == "register"
            and isinstance(n.value.func.value, ast.Name) and n.value.func.value.id in prefixes)


def _optional_import(n):
    """try: import x / except: x = None: an import that may be missing."""
    return (isinstance(n, ast.Try) and n.body and all(isinstance(x, (ast.Import, ast.ImportFrom)) for x in n.body)
            and all(isinstance(x, ast.Assign) for h in n.handlers for x in h.body))


def _route_path(n):
    for d in getattr(n, "decorator_list", []):
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "custom_route":
            return ast.unparse(d.args[0])
    return None


def _units(files, problems, declared=frozenset()):
    """(units, route order): every statement to match, keyed by its
    normalized tree, and the route paths in the order they are registered."""
    family = {_module(p) for p in files}
    first = next(iter(files))
    trees = {p: ast.parse(t) for p, t in files.items()}
    units = []
    registers = {}
    for path, tree in trees.items():
        prefixes = set(_aliases(tree, family))
        for i, n in enumerate(tree.body):
            if path != first and i == 0 and _is_doc(n):
                continue                      # a package module's docstring
            if isinstance(n, (ast.Import, ast.ImportFrom)) or _optional_import(n):
                continue                      # imports come and go with a move
            if (path != first and isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == "logger"):
                continue                      # a package module's own logger
            holder = (isinstance(n, ast.FunctionDef) and
                      ((path == first and n.name == "add_routes") or
                       (path.startswith("gizmo/routes/") and n.name == "register")))
            if not holder:
                if path != first and _looks_itself_up(n) and _name(n) not in declared:
                    problems.append(f"{_label(path, n)} uses {_looks_itself_up(n)}: moved, it reads this module's names")
                norm = _norm(n, prefixes, set(), problems, _label(path, n))
                units.append((ast.dump(norm), _label(path, n), path, _name(norm), ast.unparse(norm)))
                continue
            if n.name == "register":
                registers[_module(path)] = n
            else:
                shell = copy.copy(n)
                shell.body = []
                norm = _norm(shell, prefixes, set(), problems, _label(path, n))
                units.append((ast.dump(norm), _label(path, n) + " (its signature)", path, None, ast.unparse(norm)))
            inner = _own_names(n)
            for j, s in enumerate(n.body):
                if n.name == "register" and j == 0 and _is_doc(s):
                    continue
                if _is_register_call(s, prefixes):
                    continue
                lab = _label(path, s)
                if path != first and _looks_itself_up(s) and _name(s) not in declared:
                    problems.append(f"{lab} uses {_looks_itself_up(s)}: moved, it reads this module's names")
                norm = _norm(s, prefixes, inner, problems, lab)
                units.append((ast.dump(norm), lab, path, _name(norm), ast.unparse(norm)))
    order = []
    tree = trees[first]
    aliases = _aliases(tree, family)
    ar = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "add_routes"), None)
    for s in (ar.body if ar else []):
        if _is_register_call(s, set(aliases)):
            reg = registers.get(aliases[s.value.func.value.id])
            order += [p for p in map(_route_path, reg.body if reg else []) if p]
        elif _route_path(s):
            order.append(_route_path(s))
    return units, order


def prove(base, head, stats=None, declared=()):
    """base, head: {repo path: text}, copilot.py first. -> the problems found;
    [] when the head is the base moved and nothing else. A statement named in
    `declared` is an intended change: it is left out of the match and given
    back in stats["declared"] as (name, before, after), either side None when
    it is new or gone."""
    problems = []
    declared = set(declared)
    bu, border = _units(base, problems, declared)
    hu, horder = _units(head, problems, declared)
    shown = collections.OrderedDict()
    for side, units in ((0, bu), (1, hu)):
        for u in units:
            if u[3] in declared:
                pair = shown.setdefault(u[3], [None, None])
                pair[side] = u[4] if pair[side] is None else pair[side] + "\n" + u[4]
    bu = [u for u in bu if u[3] not in declared]
    hu = [u for u in hu if u[3] not in declared]
    b, h = collections.Counter(u[0] for u in bu), collections.Counter(u[0] for u in hu)
    lost, added = b - h, h - b
    for key, lab, *_ in bu:
        if lost[key]:
            problems.append(f"lost or changed in the head: {lab}")
            lost[key] -= 1
    for key, lab, *_ in hu:
        if added[key]:
            problems.append(f"added or changed in the head: {lab}")
            added[key] -= 1
    for name in declared - set(shown):
        problems.append(f"declared as an intended change, but nothing is called {name}")
    if border != horder:
        problems.append("the routes are registered in another order: "
                        + next((f"{x} where the base had {y}" for x, y in zip(horder, border) if x != y),
                               f"{len(horder)} routes where the base had {len(border)}"))
    if stats is not None:
        where_b = collections.defaultdict(set)
        for k, _, p, *_ in bu:
            where_b[k].add(p)
        stats.update(statements=len(bu), moved=sum(1 for k, _, p, *_ in hu if p not in where_b.get(k, {p})),
                     routes=len(horder), declared=[(n, a, b) for n, (a, b) in shown.items()])
    return problems


def _git(*args):
    return subprocess.run(["git", *args], cwd=sources.ROOT, capture_output=True, text=True, check=True).stdout


def _base_files(ref):
    first = sources.COPILOT_FILES[0]
    package = sorted(p for p in _git("ls-tree", "-r", "--name-only", ref, "--", "gizmo").split() if p.endswith(".py"))
    return {p: _git("show", f"{ref}:{p}") for p in [first] + package}


def _head_files():
    out = {}
    for p in sources.copilot_files(sources.ROOT):
        with open(os.path.join(sources.ROOT, p), encoding="utf-8") as fh:
            out[p] = fh.read()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", default="origin/main", help="the ref to compare with (default origin/main)")
    ap.add_argument("--declared", default="", help="names of statements changed on purpose, comma-separated")
    args = ap.parse_args(argv)
    stats = {}
    declared = [d.strip() for d in args.declared.split(",") if d.strip()]
    problems = prove(_base_files(args.base), _head_files(), stats, declared)
    import difflib
    for name, before, after in stats.get("declared", []):
        print(f"intended change: {name}")
        for line in difflib.unified_diff((before or "").splitlines(), (after or "").splitlines(),
                                         "before", "after", lineterm="", n=1):
            print("    " + line)
    for p in problems:
        print(p)
    if problems:
        print(f"{len(problems)} differences from {args.base} beyond the move")
        return 1
    print(f"nothing but the move: {stats['statements']} statements found again, {stats['moved']} of them "
          f"in another file, {stats['routes']} routes in the same order ({args.base})"
          + (f", and {len(stats['declared'])} intended changes shown above" if stats["declared"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
