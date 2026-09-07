#!/usr/bin/env python3
"""The environment-variable reference, generated from the code that reads it.

Two hundred variables are read across the app; the hand-written example file
documented thirty-nine of them and carried the defaults of the project this
one was forked from. A reference that is typed by hand is a reference that
is wrong within a week. This one is built by walking each module's syntax
tree for `os.environ.get("NAME", default)` and `os.environ["NAME"]`, so the
name, the default and the module are the code's own. The trailing comment on
the line, when there is one, is the description.

    python tools/env_reference.py --write   # regenerate docs/ENVIRONMENT.md
    python tools/env_reference.py --check   # exit 1 when the file is stale (CI)

Zero dependencies on purpose, like tools/sweep_tree.py.
"""
import ast
import os
import re
import sys

MODULES = ["server", "copilot", "eori", "google_data", "google_mail", "logdrain",
           "pipedrive", "recon", "tokenvault", "worldoptions", "xero"]
OUT = os.path.join("docs", "ENVIRONMENT.md")


def _banner_index(lines):
    """Line -> the nearest preceding section banner (copilot.py's `# ---- Title`)."""
    banners = []
    for i, line in enumerate(lines):
        if re.match(r"^# [-=]{20,}", line) and i + 1 < len(lines) \
                and lines[i + 1].startswith("# ") and not re.match(r"^# [-=]{5,}", lines[i + 1]):
            banners.append((i + 1, lines[i + 1][2:].strip().rstrip(".")[:60]))
    return banners


def _section_for(banners, lineno):
    title = ""
    for at, name in banners:
        if at <= lineno:
            title = name
        else:
            break
    return title


def collect(root):
    """[(name, module, section, default, comment, lineno)] for every read."""
    found = []
    for mod in MODULES:
        path = os.path.join(root, mod + ".py")
        if not os.path.isfile(path):
            continue
        src = open(path, encoding="utf-8").read()
        lines = src.splitlines()
        banners = _banner_index(lines) if mod == "copilot" else []
        tree = ast.parse(src)
        for node in ast.walk(tree):
            name = default = None
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == "get" and ast.unparse(node.func.value) == "os.environ" \
                    and node.args and isinstance(node.args[0], ast.Constant):
                name = str(node.args[0].value)
                default = ast.get_source_segment(src, node.args[1]) if len(node.args) > 1 else "None"
            elif isinstance(node, ast.Subscript) and ast.unparse(node.value) == "os.environ" \
                    and isinstance(node.slice, ast.Constant):
                name = str(node.slice.value)
                default = "(required)"
            if not name:
                continue
            line = lines[node.lineno - 1]
            m = re.search(r"#\s*(.+)$", line)
            comment = m.group(1).strip() if m else ""
            default = " ".join(str(default).split())
            found.append((name, mod, _section_for(banners, node.lineno), default, comment, node.lineno))
    return found


def render(root):
    rows = collect(root)
    by_name = {}
    for name, mod, section, default, comment, lineno in sorted(rows, key=lambda r: (r[0], r[1], r[5])):
        e = by_name.setdefault(name, {"modules": [], "default": default, "comment": comment,
                                      "section": section, "module": mod})
        if mod not in e["modules"]:
            e["modules"].append(mod)
        if not e["comment"] and comment:
            e["comment"] = comment
    out = ["# Environment variables", "",
           "Generated from the code by `tools/env_reference.py`; do not edit by hand.",
           "`make env-doc` rewrites it, and CI fails when it is stale.", "",
           f"{len(by_name)} variables are read. Every one has a default unless marked "
           "**(required)**; the defaults below are the code's own expressions, so a "
           "path like `/data/...` means the Railway volume. Set a variable in Railway, "
           "never in the code, and never paste a secret into chat or a document.", ""]
    # Group: server.py first, then copilot.py by section, then the other modules.
    groups = {}
    for name, e in by_name.items():
        if e["module"] == "server":
            key = ("0", "server.py")
        elif e["module"] == "copilot":
            key = ("1", "copilot.py - " + (e["section"] or "top"))
        else:
            key = ("2", e["module"] + ".py")
        groups.setdefault(key, []).append((name, e))
    for (_, title) in sorted(groups):
        items = groups[(_, title)]
        out += [f"## {title}", "", "| Variable | Default | Read by | Notes |", "|---|---|---|---|"]
        for name, e in sorted(items):
            default = e["default"].replace("|", "\\|")
            if len(default) > 60:
                default = default[:57] + "..."
            notes = e["comment"].replace("|", "\\|")
            out.append(f"| `{name}` | `{default}` | {', '.join(e['modules'])} | {notes} |")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    text = render(root)
    target = os.path.join(root, OUT)
    if "--check" in argv:
        current = open(target, encoding="utf-8").read() if os.path.isfile(target) else ""
        if current != text:
            print(f"{OUT} is stale: run `make env-doc` and commit the result")
            return 1
        print(f"{OUT} is current")
        return 0
    os.makedirs(os.path.dirname(target), exist_ok=True)
    open(target, "w", encoding="utf-8").write(text)
    print(f"wrote {OUT}: {text.count(chr(10))} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
