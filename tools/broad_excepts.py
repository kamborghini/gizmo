"""Every broad error handler in the app, and what it does with the error.

`except Exception:` (or a bare `except:`) catches whatever went wrong. Most
handlers log it, answer the request, raise it on, or fall back to a value. A
few let it go without a word: a `pass`, a `continue` or `break`, a bare
`return`. Silence is sometimes right (a best-effort clean-up, a value that
may be missing), but only with a reason, so a silent handler says why in a
comment on its own lines; tests/test_dispatch.py fails on one that does not.

    python tools/broad_excepts.py      the counts, and every silent handler

Imports nothing from the app, like the other tools.
"""
import ast
import collections
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sources  # noqa: E402  (every module of the app)

SILENT = ("pass", "skips", "returns")
_LOGS = re.compile(r"\b(logger|logging|log|errors)\.")


def _broad(h):
    t = h.type
    if t is None:
        return True
    names = t.elts if isinstance(t, ast.Tuple) else [t]
    return any(isinstance(n, ast.Name) and n.id in ("Exception", "BaseException") for n in names)


def _kind(h):
    """What the handler does, from its first three statements."""
    first = h.body[:3]
    if any(isinstance(x, ast.Raise) for s in first for x in ast.walk(s)):
        return "raises"
    if _LOGS.search("\n".join(ast.unparse(s) for s in first)):
        return "logs"
    if any(isinstance(s, ast.Return) and s.value is not None for s in first):
        return "answers"
    if any(isinstance(s, (ast.Assign, ast.AugAssign, ast.AnnAssign)) or
           (isinstance(s, ast.Expr) and isinstance(s.value, ast.Call)) for s in first):
        return "falls back"
    if len(h.body) == 1:
        s = h.body[0]
        if isinstance(s, ast.Pass):
            return "pass"
        if isinstance(s, (ast.Continue, ast.Break)):
            return "skips"
        if isinstance(s, ast.Return):
            return "returns"
    return "other"


def scan(root=sources.ROOT):
    """[{file, line, kind, reason}] for every broad handler in the app."""
    out = []
    for rel in sources.APP_MODULES if root == sources.ROOT else _modules(root):
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8").read()
        lines = text.splitlines()
        for h in ast.walk(ast.parse(text)):
            if isinstance(h, ast.ExceptHandler) and _broad(h):
                span = lines[h.lineno - 1:h.body[-1].end_lineno]
                reason = " ".join(l.split("#", 1)[1].strip() for l in span if "#" in l)
                out.append({"file": rel, "line": h.lineno, "kind": _kind(h), "reason": reason})
    return out


def _modules(root):
    return [os.path.relpath(p, root) for p in sorted(sources.glob.glob(os.path.join(root, "*.py")))]


def main():
    found = scan()
    counts = collections.Counter(h["kind"] for h in found)
    print(f"{len(found)} broad handlers: " + ", ".join(f"{k} {v}" for k, v in counts.most_common()))
    for h in found:
        if h["kind"] in SILENT:
            print(f"  {h['file']}:{h['line']} {h['kind']}: {h['reason'] or '(no reason given)'}")


if __name__ == "__main__":
    main()
