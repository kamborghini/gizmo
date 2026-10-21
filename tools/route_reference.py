#!/usr/bin/env python3
"""The API route reference, generated from the code that registers the routes.

Every route the page and the outside world can reach is an `@mcp.custom_route`
in copilot.py or server.py, and nothing listed them: the page and the server
agreed because each side's tests happened to. This walks each module's syntax
tree for those decorators and writes, per route, its methods, its handler, the
tab that opens it, the door it opens with and that door's terms, the model
that checks its body (gizmo/bodies.py), the checks the handler makes for
itself, and the first sentence of its docstring.

    python tools/route_reference.py --write   # regenerate docs/API.md
    python tools/route_reference.py --check   # exit 1 when the file is stale (CI)

The tab map is read from the _TAB_ROUTES and _OPEN_API literals, wherever in
copilot.py or the modules split out of it they stand, so this imports nothing
from the app. Zero dependencies, like env_reference.py.
"""
import ast
import copy
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources  # noqa: E402  (copilot.py and the modules split out of it)

OUT = os.path.join("docs", "API.md")


def module_files(root):
    """(module, file) for each module that registers routes: server.py, then
    copilot.py and the modules split out of it."""
    return [("server", "server.py")] + [(f[:-3].replace("/", "."), f) for f in sources.copilot_files(root)]


# The names a module gives copilot.py and the modules split out of it
# (core, team, gate, desk ...), set for each module as it is read.
_ALIASES: set = set()


def _family_aliases(tree, family):
    out = set()
    for n in tree.body:
        if isinstance(n, ast.Import):
            out |= {a.asname or a.name for a in n.names if a.name in family}
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            out |= {a.asname or a.name for a in n.names if f"{n.module}.{a.name}" in family}
    return out


class _Bare(ast.NodeTransformer):
    def visit_Attribute(self, x):
        if isinstance(x.value, ast.Name) and x.value.id in _ALIASES:
            return ast.Name(x.attr)
        return self.generic_visit(x)


def _bare(node) -> str:
    """A limit as the code names it: SKILLS_BODY_MAX, whether the route reads
    it bare or through the module that holds it (skillbook.SKILLS_BODY_MAX)."""
    return ast.unparse(_Bare().visit(copy.deepcopy(node)))


def _called(call):
    """The name a call reaches: f(...), or m.f(...) where m is copilot.py or a
    module split out of it (core.f, team.f, gate.f)."""
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in _ALIASES:
        return f.attr
    return None


DOORS = {"_guard", "_mail_guard", "_crm_guard", "_files_guard", "_auth_guard", "_team_guard"}
CHECKS = {"_team_level", "_team_role", "_user_tabs", "_uid_has_tab", "_live_uid", "_secret_ok",
          "_forecast_token_ok", "_verify_session_token", "_shop_gate", "_can_force_tool"}
RANKS = {0: "any account", 1: "any account", 2: "admin", 3: "master"}


def _literal(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    return None


def _tab(path, tab_routes, open_api):
    best, tab = 0, None
    for p, t in tab_routes:
        if path.startswith(p) and len(p) > best:
            best, tab = len(p), t
    if tab:
        return " or ".join(tab) if isinstance(tab, (tuple, list)) else tab
    if path.startswith("/api/"):
        return "any account" if any(path.startswith(p) for p in open_api) else "refused: no tab claims it"
    return "outside the tab map"


def _rank(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return RANKS.get(node.value, str(node.value))
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        return str(node.slice.value)
    return ast.unparse(node)


def _door(fn):
    """(door, terms) from the first call to a door in the handler's body."""
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and _called(node) in DOORS:
            terms = []
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            if _called(node) == "_team_guard" and len(node.args) > 1:
                terms.append("rank " + _rank(node.args[1]))
            if "min_level" in kw:
                terms.append("rank " + _rank(kw["min_level"]))
            if isinstance(kw.get("ai"), ast.Constant) and kw["ai"].value:
                terms.append("AI slot")
            for k in ("max_body", "cap"):
                if k in kw:
                    terms.append(k.replace("_", " ") + " " + _bare(kw[k]))
            if isinstance(kw.get("body"), ast.Constant) and kw["body"].value is False:
                terms.append("reads its own body")
            return _called(node), ", ".join(terms)
    return "own check", ""


def _model_names(node) -> str:
    if isinstance(node, ast.Dict):
        return ", ".join(_model_names(v) for v in node.values)
    if isinstance(node, ast.Attribute):
        return node.attr
    return node.id if isinstance(node, ast.Name) else ast.unparse(node)


def _body_model(fn) -> str:
    """The model that checks the route's body (gizmo/bodies.py): handed to the
    door, or checked by the handler once it has read its own body."""
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        if _called(node) in DOORS:
            for k in node.keywords:
                if k.arg == "model":
                    return _model_names(k.value)
        f = node.func
        if (isinstance(f, ast.Attribute) and f.attr == "refusal" and isinstance(f.value, ast.Name)
                and f.value.id == "bodies" and node.args):
            return _model_names(node.args[0])
    return ""


def _fields(fn) -> list:
    """The fields the handler reads from its body: body.get("x"), body["x"]
    and "x" in body, where the body is named `body`, as every door hands it."""
    out = set()
    for node in ast.walk(fn):
        key = None
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get"
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "body" and node.args):
            key = node.args[0]
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "body":
            key = node.slice
        elif (isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.In)
              and isinstance(node.comparators[0], ast.Name) and node.comparators[0].id == "body"):
            key = node.left
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            out.add(key.value)
    return sorted(out - {"op"})


def _checks(fn):
    names = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and _called(node):
            n = _called(node)
            if n in CHECKS or re.search(r"verify|hmac", n, re.I):
                names.add(n)
    return sorted(names)


def _about(fn):
    doc = ast.get_docstring(fn) or ""
    first = re.split(r"(?<=[.!?])\s|\n\s*\n", doc.strip(), maxsplit=1)[0] if doc else ""
    first = re.sub(r"\s+", " ", first).strip()
    return first if len(first) <= 160 else first[:157] + "..."


def collect(root):
    copilot_tree = ast.parse(open(os.path.join(root, sources.copilot_files(root)[0]), encoding="utf-8").read())
    # The tab map lives with the door: in copilot.py once, in gizmo/gate.py now.
    family = [ast.parse(open(os.path.join(root, f), encoding="utf-8").read()) for f in sources.copilot_files(root)]
    tab_routes = next((v for v in (_literal(t, "_TAB_ROUTES") for t in family) if v), ())
    open_api = next((v for v in (_literal(t, "_OPEN_API") for t in family) if v), ())
    rows = []
    family_mods = {f[:-3].replace("/", ".") for f in sources.copilot_files(root)}
    for mod, rel in module_files(root):
        path = os.path.join(root, rel)
        tree = copilot_tree if mod == "copilot" else ast.parse(open(path, encoding="utf-8").read())
        _ALIASES.clear()
        _ALIASES.update(_family_aliases(tree, family_mods))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in fn.decorator_list:
                if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "custom_route"):
                    continue
                route = ast.literal_eval(dec.args[0])
                methods = ["GET"]
                for k in dec.keywords:
                    if k.arg == "methods":
                        methods = list(ast.literal_eval(k.value))
                door, terms = _door(fn)
                rows.append({"path": route, "methods": methods, "handler": fn.name, "module": mod,
                             "tab": _tab(route, tab_routes, open_api), "door": door, "terms": terms,
                             "body": _body_model(fn), "fields": _fields(fn),
                             "checks": _checks(fn), "about": _about(fn)})
    rows.sort(key=lambda r: (r["path"], r["methods"]))
    return rows


def _body_cell(r) -> str:
    if r["body"]:
        return f"`{r['body']}`"
    return "unchecked" if r["fields"] and "POST" in r["methods"] else ""


def render(root):
    rows = collect(root)
    out = ["# API routes", "",
           "Generated from the code by `tools/route_reference.py`; do not edit by hand.",
           "`make api-doc` rewrites it, and CI fails when it is stale.", "",
           f"{len(rows)} routes. **Tab** is the tab that opens a route (`_TAB_ROUTES`); "
           "an `/api/` route no tab claims is refused unless it is on `_OPEN_API`. **Door** is the "
           "guard the handler opens with (`_guard` is the one door: rate window, tab, session, rank, "
           "AI slot, body); `own check` means the route authenticates itself (a hook, a webhook, "
           "OAuth, print, assets). **Body** is the model that checks the fields the route reads "
           "(`gizmo/bodies.py`); `unchecked` means it reads fields no model checks yet. **Checks** are "
           "the permission helpers the handler calls itself.", ""]
    groups = {}
    for r in rows:
        parts = r["path"].split("/")
        key = "/".join(parts[:3]) if r["path"].startswith("/api/") else "/" + parts[1]
        groups.setdefault(key, []).append(r)
    for key in sorted(groups):
        out += [f"## `{key}`", "", "| Route | Methods | Tab | Door | Terms | Body | Checks | Handler | What it does |",
                "|---|---|---|---|---|---|---|---|---|"]
        for r in groups[key]:
            cells = [f"`{r['path']}`", ", ".join(r["methods"]), r["tab"], f"`{r['door']}`" if r["door"] != "own check" else "own check",
                     r["terms"], _body_cell(r), ", ".join(f"`{c}`" for c in r["checks"]),
                     f"`{r['module']}.{r['handler']}`", r["about"]]
            out.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    text = render(root)
    target = os.path.join(root, OUT)
    if "--check" in argv:
        current = open(target, encoding="utf-8").read() if os.path.isfile(target) else ""
        if current != text:
            print(f"{OUT} is stale: run `make api-doc` and commit the result")
            return 1
        print(f"{OUT} is current")
        return 0
    os.makedirs(os.path.dirname(target), exist_ok=True)
    open(target, "w", encoding="utf-8").write(text)
    print(f"wrote {OUT}: {text.count(chr(10))} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
