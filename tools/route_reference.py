#!/usr/bin/env python3
"""The API route reference, generated from the code that registers the routes.

Every route the page and the outside world can reach is an `@mcp.custom_route`
in copilot.py or server.py, and nothing listed them: the page and the server
agreed because each side's tests happened to. This walks each module's syntax
tree for those decorators and writes, per route, its methods, its handler, the
tab that opens it, the door it opens with and that door's terms, the checks
the handler makes for itself, and the first sentence of its docstring.

    python tools/route_reference.py --write   # regenerate docs/API.md
    python tools/route_reference.py --check   # exit 1 when the file is stale (CI)

The tab map is read from copilot's own _TAB_ROUTES and _OPEN_API literals, so
this imports nothing from the app. Zero dependencies, like env_reference.py.
"""
import ast
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


def _called(call):
    """The name a call reaches: f(...), or core.f(...) in a module moved out of
    copilot.py, which reads copilot.py as core."""
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "core":
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
                    terms.append(k.replace("_", " ") + " " + ast.unparse(kw[k]))
            if isinstance(kw.get("body"), ast.Constant) and kw["body"].value is False:
                terms.append("reads its own body")
            return _called(node), ", ".join(terms)
    return "own check", ""


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
    tab_routes = _literal(copilot_tree, "_TAB_ROUTES") or ()
    open_api = _literal(copilot_tree, "_OPEN_API") or ()
    rows = []
    for mod, rel in module_files(root):
        path = os.path.join(root, rel)
        tree = copilot_tree if mod == "copilot" else ast.parse(open(path, encoding="utf-8").read())
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
                             "checks": _checks(fn), "about": _about(fn)})
    rows.sort(key=lambda r: (r["path"], r["methods"]))
    return rows


def render(root):
    rows = collect(root)
    out = ["# API routes", "",
           "Generated from the code by `tools/route_reference.py`; do not edit by hand.",
           "`make api-doc` rewrites it, and CI fails when it is stale.", "",
           f"{len(rows)} routes. **Tab** is the tab that opens a route (`_TAB_ROUTES`); "
           "an `/api/` route no tab claims is refused unless it is on `_OPEN_API`. **Door** is the "
           "guard the handler opens with (`_guard` is the one door: rate window, tab, session, rank, "
           "AI slot, body); `own check` means the route authenticates itself (a hook, a webhook, "
           "OAuth, print, assets). **Checks** are the permission helpers the handler calls itself.", ""]
    groups = {}
    for r in rows:
        parts = r["path"].split("/")
        key = "/".join(parts[:3]) if r["path"].startswith("/api/") else "/" + parts[1]
        groups.setdefault(key, []).append(r)
    for key in sorted(groups):
        out += [f"## `{key}`", "", "| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |",
                "|---|---|---|---|---|---|---|---|"]
        for r in groups[key]:
            cells = [f"`{r['path']}`", ", ".join(r["methods"]), r["tab"], f"`{r['door']}`" if r["door"] != "own check" else "own check",
                     r["terms"], ", ".join(f"`{c}`" for c in r["checks"]), f"`{r['module']}.{r['handler']}`", r["about"]]
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
