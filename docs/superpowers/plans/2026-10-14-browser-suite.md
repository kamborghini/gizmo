# The browser suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every Reactor screen opens in a real browser on every pull request, at phone, laptop and wide sizes, inside an invented world, and the pull request fails on script errors, failed or outside requests, sideways scroll, spill, writes, and any rise (or unrecorded fall) in panel-rule and accessibility problems; plus a generated `docs/API.md`.

**Architecture:** `tests/browser/serve.py` executes the dispatch suite's setup, runs `tests/browser/seed/` (proven recipes that fill every screen through the app's own code), and serves the real app with uvicorn. Playwright on Node (`tests/browser/*.spec.js`) signs in with a stand-in `window.shopify`, fences the network, reaches each of 36 states, and measures it (zero-tolerance checks, in-page panel probes, axe), comparing the last two with a committed ratchet record. `tools/route_reference.py` writes `docs/API.md` from the route decorators.

**Tech Stack:** Python 3.14 (the app, the dispatch harness, the seed), Node 24, `@playwright/test` 1.63.0, `@axe-core/playwright` 4.13.0, `@fontsource-variable/inter` 5.3.0, node's built-in `node:test`, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-14-browser-suite-design.md` (approved 14 Oct; its Data section corrected the same day after a probe).

## Global Constraints

- No visible change to the app, except fixes for day-one zero-tolerance failures; each such fix gets its own failing test first and a release note in `data/changelog.json` dated the merge day.
- Invented data only: people and companies made up, emails at `example.com` / `example.org`, phones in the 01632 960xxx drama range. The repo is public: never the business's name in docs, PR text or commit messages; never commit `audit/`, `.superpowers/` or `.design-rig/`.
- Frozen areas are measured, never touched: the printed label, print CSS, the Production Manager queue's columns, statuses, actions and order; nothing named Quote Engine.
- The suite never clicks anything that writes (Save, Print, Mark made, Dispatch, Send, Claim, Delete, Won, Lost, Run with AI, a checkbox that completes). Opening a tab, a dialog or a row is fine.
- Exact pins: `@playwright/test` 1.63.0, `@axe-core/playwright` 4.13.0, `@fontsource-variable/inter` 5.3.0, as dev dependencies only (`npm audit --omit=dev` unchanged).
- Chromium is Playwright's own headless build (`npx playwright install chromium`), never the system Chrome, locally and in CI.
- British English in everything a person reads; no em or en dashes in UI copy.
- `make check` stays green; commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; ship as one PR with Auto-fix and auto-merge on.
- Agent budget for the initiative: 5; 3 spent on the data recipes; 1 reserved for this plan's final review.

## Review Focus

1. **A screen measured in its empty state.** If a seed stops filling a screen (a store's shape changes, a fake falls out of step), the screen would still load cleanly and every check would pass on the empty state. Expected: the run fails, naming the screen. Pinned by Task 6's `screens.test.js` (every screen's `go` waits for seeded content) and by Task 2's `test_world.py` (each read route answers with a seeded text).
2. **A screen that writes during the run.** Screens share one server across parallel workers; a write would change what the next screen sees and make the run order-dependent. Expected: the run fails, naming the request. Pinned by Task 3's `support.test.js` (`isWrite`) and the `writes` assertion in Task 6's `pages.spec.js`.
3. **A record left with slack after a fix.** A fixed problem that is not taken off the record leaves room for a later regression to hide. Expected: the run fails with "lower the record". Pinned by Task 4's `record.test.js`.
4. **A request to a new outside host.** A feature that starts loading from a new host would pass silently if the fence only aborted. Expected: the screen fails, naming the host. Pinned by Task 3's `fence.spec.js`.
5. **The dispatch setup changing shape.** `serve.py` borrows the dispatch suite's setup by its `@test` marker; if that marker moves, a half-built world would serve. Expected: the server refuses to start, naming the marker. Pinned by Task 2's `t_the_setup_is_found_or_the_server_refuses_to_start`.

---

## File Structure

| File | Responsibility |
|---|---|
| `tools/route_reference.py` | Walks `copilot.py` / `server.py` for `@*.custom_route(...)`, writes `docs/API.md`; `--check` for CI |
| `docs/API.md` | Generated route list |
| `tests/browser/serve.py` | `build_world()`: the dispatch setup + the seed; `main()`: writes `.run/auth.json` and serves |
| `tests/browser/seed/__init__.py` | `seed(world)`: runs the three recipes in order, then joins their Shopify stores |
| `tests/browser/seed/dashboards.py`, `operations.py`, `workspace.py` | The proven recipes, brought in from the plan workspace |
| `tests/browser/test_world.py` | Proves the seeded world without a browser (Python, the repo's runner style) |
| `tests/browser/playwright.config.js` | Three projects, the web server, outputs under `tests/browser/.run/` |
| `tests/browser/support.js` | `prepare`, `watch`, `settle`, `open`, `helpers`, `isWrite` |
| `tests/browser/record.js` | The ratchet: `counts`, `compare`, `check`, `merge` |
| `tests/browser/probes.js` | In-page measures: sideways, spill, panel rules |
| `tests/browser/screens.js` | The 36 states |
| `tests/browser/pages.spec.js` | Every state at every size |
| `tests/browser/keyboard.spec.js` | Three dialog journeys |
| `tests/browser/fence.spec.js`, `probes.spec.js` | The fence and the probes against synthetic pages |
| `tests/browser/unit/*.test.js` | `node:test` units: record, support, screens |
| `tests/browser/teardown.js` | Merges observed counts; rewrites the record under `UPDATE_RECORD=1` |
| `tests/browser/record/a11y.json`, `record/panels.json` | The committed ratchet records |
| `tests/browser/README.md` | Running, reading a failure, updating the record, adding a screen |

The plan workspace `.superpowers/sdd/2026-10-14-browser-suite/recipes/` (git-ignored, on this machine) holds the proven recipes and their proofs: `dashboards/seed_dashboards.py` (1,064 lines), `operations/seed_operations.py` (653), `workspace/seed_workspace.py` (398), the three proof scripts and their outputs, and `journal.jsonl` (the agents' full findings, including every screen's navigation and its risks).

---

### Task 1: The API route list

**Files:**
- Create: `tools/route_reference.py`, `docs/API.md` (generated)
- Modify: `tests/test_dispatch.py` (after `t_the_environment_reference_does_not_name_the_shop`), `Makefile`, `.github/workflows/tests.yml`
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Produces: `collect(root) -> list[dict]` with keys `path, methods, handler, module, tab, door, terms, checks, about`; `render(root) -> str`; `main(argv) -> int`; `MODULES = ["server", "copilot"]`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_dispatch.py` after `t_the_environment_reference_does_not_name_the_shop`:

```python
@test
def t_the_api_reference_is_generated_from_the_code():
    """A hundred and fifty routes and nothing listed them: the page and the
    server agreed because each side's tests happened to. docs/API.md is built
    from the route decorators themselves, and this fails when it is stale."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("route_reference", os.path.join(HERE, "tools", "route_reference.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = mod.collect(HERE)
    src = "".join(open(os.path.join(HERE, m + ".py"), encoding="utf-8").read() for m in mod.MODULES)
    eq(len(rows), len(re.findall(r"@\w+\.custom_route\(", src)), "every route decorator is a row")
    by = {r["path"]: r for r in rows}
    eq(by["/api/backup"]["door"], "_guard", "the backup route opens with the one door")
    ok("_team_role" in by["/api/backup"]["checks"], "and its own master check is named")
    eq(by["/api/crm/deal"]["tab"], "crm", "a CRM route is opened by the CRM tab")
    eq(by["/api/alerts"]["tab"], "any account", "an open route says so")
    eq(by["/api/team/user"]["door"], "_team_guard", "a guard helper is named as the door")
    eq(by["/api/team/user"]["terms"], "rank admin", "with the rank it asks for")
    eq(by["/hooks/forecast/results"]["door"], "own check", "a hook has no session door")
    ok("_forecast_token_ok" in by["/hooks/forecast/results"]["checks"], "and names the check it makes")
    eq(mod.render(HERE), open(os.path.join(HERE, "docs", "API.md"), encoding="utf-8").read(),
       "docs/API.md is stale: run `make api-doc`")


@test
def t_the_api_reference_does_not_name_the_shop():
    """The repository is public. The route list carries the handlers'
    docstrings, so it is checked for the shop's domain exactly as the
    environment reference is, the domain read off the quote site's default."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("env_reference", os.path.join(HERE, "tools", "env_reference.py"))
    env = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(env)
    host = next(r[3] for r in env.collect(HERE) if r[0] == "PROPOSAL_HOST").strip("\"'")
    domain = host.split(".", 1)[1]
    text = open(os.path.join(HERE, "docs", "API.md"), encoding="utf-8").read()
    ok(domain not in text, "docs/API.md names the shop's domain")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `ONLY=t_the_api_reference env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>/dev/null | grep -E "PASS|FAIL"`
Expected: both FAIL (`No such file` for `tools/route_reference.py`, and for `docs/API.md`).

- [ ] **Step 3: Write `tools/route_reference.py`**

```python
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

MODULES = ["server", "copilot"]
OUT = os.path.join("docs", "API.md")
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
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in DOORS:
            terms = []
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            if node.func.id == "_team_guard" and len(node.args) > 1:
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
            return node.func.id, ", ".join(terms)
    return "own check", ""


def _checks(fn):
    names = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            n = node.func.id
            if n in CHECKS or re.search(r"verify|hmac", n, re.I):
                names.add(n)
    return sorted(names)


def _about(fn):
    doc = ast.get_docstring(fn) or ""
    first = re.split(r"(?<=[.!?])\s|\n\s*\n", doc.strip(), maxsplit=1)[0] if doc else ""
    first = re.sub(r"\s+", " ", first).strip()
    return first if len(first) <= 160 else first[:157] + "..."


def collect(root):
    copilot_tree = ast.parse(open(os.path.join(root, "copilot.py"), encoding="utf-8").read())
    tab_routes = _literal(copilot_tree, "_TAB_ROUTES") or ()
    open_api = _literal(copilot_tree, "_OPEN_API") or ()
    rows = []
    for mod in MODULES:
        path = os.path.join(root, mod + ".py")
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
```

- [ ] **Step 4: Generate the file and run the tests**

Run: `.venv/bin/python tools/route_reference.py --write && ONLY=t_the_api_reference env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/test_dispatch.py 2>/dev/null | grep -E "PASS|FAIL"`
Expected: `wrote docs/API.md: N lines`, then both PASS. Read `docs/API.md` once end to end: every row has a tab, a door and a handler; no docstring sentence names the business.

- [ ] **Step 5: Wire the commands**

`Makefile`: add `api-doc` to `.PHONY`, add to the help block `#   make api-doc        regenerate docs/API.md from the route decorators`, add the target, and add the check to `check`:

```make
api-doc:
	$(PY) tools/route_reference.py --write
```

and in `check:` after the env reference line: `$(PY) tools/route_reference.py --check`. Widen the `help` sed range by one line to cover the new help line.

`.github/workflows/tests.yml`, in the `test` job after "The environment reference is current":

```yaml
      - name: The API route reference is current
        run: python tools/route_reference.py --check
```

- [ ] **Step 6: Commit**

```bash
git add tools/route_reference.py docs/API.md tests/test_dispatch.py Makefile .github/workflows/tests.yml
git commit -m "API route list generated from the route decorators, kept current by CI

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The seeded world

**Files:**
- Create: `tests/browser/serve.py`, `tests/browser/seed/__init__.py`, `tests/browser/seed/dashboards.py`, `tests/browser/seed/operations.py`, `tests/browser/seed/workspace.py`, `tests/browser/test_world.py`
- Modify: `.gitignore` (add `tests/browser/.run/`), `tests/test_frontend.py` (the fixture privacy guard)
- Test: `tests/browser/test_world.py`, `tests/test_frontend.py`

**Interfaces:**
- Consumes: the dispatch setup (every line of `tests/test_dispatch.py` before the first `"\n@test\n"`), whose globals include `post`, `ensure_auth`, `APP_AUTH`, `SECRET`, `SCRATCH`, `copilot`, `server`.
- Produces: `serve.prelude_source_from(text: str) -> str` (raises `SystemExit` naming the marker); `serve.build_world() -> dict` (the setup's globals after seeding, plus `world["SEEDED"]`); `serve.main()`; `seed.seed(world: dict) -> dict` returning `{"localStorage": {...}, "orders": int, "ops_orders": int}`; the file `tests/browser/.run/auth.json` = `{"base", "token", "session", "master", "localStorage"}`.

- [ ] **Step 1: Write the failing world test**

Create `tests/browser/test_world.py`:

```python
"""The browser suite's world, proven without a browser: the dispatch setup,
then the seed, then the read routes the screens call, each answering with
seeded content. `make test-browser` and CI's browser job run this first, so a
screen the seed stopped filling is named here rather than measured empty."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import serve  # noqa: E402

TESTS = []
def test(fn): TESTS.append(fn); return fn
def ok(c, msg=""):
    if not c: raise AssertionError("FAIL: " + msg)

_W = {}
def world():
    if not _W:
        _W.update(serve.build_world())
    return _W

def read(path, body=None):
    r = world()["post"](path, body or {})
    ok(r.status_code == 200, "%s answered %s: %s" % (path, r.status_code, r.text[:200]))
    return r.json()

def has(path, body, *texts):
    blob = json.dumps(read(path, body), ensure_ascii=False)
    for t in texts:
        ok(t in blob, "%s %s does not carry %r" % (path, json.dumps(body), t))


@test
def t_the_setup_is_found_or_the_server_refuses_to_start():
    try:
        serve.prelude_source_from("import os\nprint('no tests here')\n")
    except SystemExit as e:
        ok("@test" in str(e), "the refusal names the marker it looked for: %s" % e)
    else:
        raise AssertionError("a setup with no @test marker was served")


@test
def t_the_dashboards_are_filled():
    has("/api/cache", {}, "Revenue is up on last week", "The store is indexable", "custom gobo", "Champions")
    has("/api/products", {"months": 24, "fresh": True}, "Walkway Safety Sign Gobo")
    has("/api/liability", {"fresh": True}, "Kestrel Logistics Ltd")
    has("/api/recon/exceptions", {}, "Kilnworth Glass Supplies Ltd")
    has("/api/forecast", {}, "Algorithm 1", "Cash Flow plan.xlsx")
    has("/api/connector", {"op": "status"}, "test-store.myshopify.com")


@test
def t_the_operations_screens_are_filled():
    has("/api/production-labels", {"tag": "IP", "fresh": False}, "#210388", "Hartwell Events Ltd")
    has("/api/custom/list", {"limit": 200}, "Replacement gobo")
    has("/api/crm/board", {}, "Fernhill walkway safety signs", "Marcus Bell", "Rental stock enquiry")
    has("/api/loans", {"op": "board"}, "Quayside Exhibitions")
    has("/api/mail/board", {}, "Artwork for the autumn tour gobos")
    has("/api/files/tree", {}, "Artwork")


@test
def t_the_workspace_screens_are_filled():
    has("/api/team/board", {}, "Hattie Brennan", "Jonah Featherstone")
    has("/api/work/board", {}, "Jonah Featherstone")
    has("/api/memory", {}, "Chase the B-size glass blank reorder")
    has("/api/skills", {}, "Quoting custom gobos")
    has("/api/updates", {}, "Hattie Brennan")
    ok("sc_convos_v1" in world()["SEEDED"]["localStorage"], "chat's conversations are handed to the browser")


@test
def t_the_two_shopify_stores_are_one():
    s = world()["SEEDED"]
    ok(s["ops_orders"] == 12, "the Production Manager's twelve orders are in the store: %s" % s["ops_orders"])
    ok(s["orders"] > 1000, "beside the dashboards' history: %s" % s["orders"])
    has("/api/production-labels", {"tag": "IP", "fresh": False}, "#210388")
    has("/api/liability", {"fresh": True}, "Kestrel Logistics Ltd")


@test
def t_nothing_in_the_world_reached_the_network():
    reached = world().get("NET_REACHED") or []
    ok(not reached, "the seed reached the network: %s" % reached[:5])


if __name__ == "__main__":
    passed = failed = 0
    for fn in [t for t in TESTS if os.environ.get("ONLY", "") in t.__name__]:
        try:
            fn(); passed += 1; print("  PASS ", fn.__name__)
        except Exception as e:
            failed += 1; print("  FAIL ", fn.__name__, "-", e)
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/browser/test_world.py`
Expected: an import error, `No module named 'serve'`.

- [ ] **Step 3: Write `tests/browser/serve.py`**

```python
"""Serve the real app for the browser suite, inside the dispatch suite's own world.

The dispatch suite's setup (every line of tests/test_dispatch.py before its
first test) gives the app scratch stores, a fake Shopify, invented accounts
and a network block. The seed then fills every screen through the app's own
code (tests/browser/seed/). The app is then served exactly as `make run`
serves it: server.build_app() under uvicorn.

    python tests/browser/serve.py      # PORT (8930); writes tests/browser/.run/auth.json

The local design rig has run the app this way since September.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
RUN = os.environ.get("BROWSER_RUN") or os.path.join(HERE, ".run")
MARK = "\n@test\n"


def prelude_source_from(text):
    """The setup part of the dispatch suite, or a refusal naming the marker."""
    if MARK not in text:
        raise SystemExit("serve.py: tests/test_dispatch.py has no line '@test' after its setup, so the "
                         "setup cannot be found; the world would be half built, so nothing is served")
    src = text[:text.index(MARK)]
    tests = os.path.join(ROOT, "tests")
    src = src.replace("os.path.dirname(os.path.dirname(os.path.abspath(__file__)))", repr(ROOT))
    src = src.replace("os.path.dirname(os.path.abspath(__file__))", repr(tests))
    src = src.replace("os.path.dirname(__file__)", repr(tests))
    # No App Bridge in a plain browser: the page takes window.shopify from the suite.
    src = src.replace("\nimport jwt\n", "\nos.environ.pop('SHOPIFY_API_KEY', None)\nimport jwt\n", 1)
    return src


def build_world():
    os.chdir(ROOT)
    sys.path.insert(0, ROOT)
    sys.path.insert(0, HERE)
    os.environ["RATE_LIMIT_PER_CLIENT"] = "100000"
    os.environ["FORECAST_INGEST_TOKEN"] = "browser-suite-forecast-token-0123456789"
    text = open(os.path.join(ROOT, "tests", "test_dispatch.py"), encoding="utf-8").read()
    g = {"__name__": "browser_world", "__file__": os.path.join(ROOT, "tests", "test_dispatch.py")}
    exec(compile(prelude_source_from(text), "tests/test_dispatch.py (setup)", "exec"), g)
    g["ensure_auth"]()
    from seed import seed
    g["SEEDED"] = seed(g)
    return g


def main():
    import jwt
    import uvicorn
    port = int(os.environ.get("PORT", "8930"))
    g = build_world()
    now = int(time.time())
    token = jwt.encode({"iss": "https://test-store.myshopify.com/admin", "dest": "https://test-store.myshopify.com",
                        "aud": "a", "exp": now + 6 * 3600, "nbf": now - 5}, g["SECRET"], algorithm="HS256")
    os.makedirs(RUN, exist_ok=True)
    auth = {"base": f"http://127.0.0.1:{port}", "token": token, "session": g["APP_AUTH"]["session"],
            "master": g["APP_AUTH"]["master"], "localStorage": g["SEEDED"]["localStorage"]}
    with open(os.path.join(RUN, "auth.json"), "w", encoding="utf-8") as fh:
        json.dump(auth, fh)
    print(f"browser world ready on {auth['base']}", flush=True)
    uvicorn.run(g["server"].build_app(), host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Bring in the recipes**

Copy, unchanged at first:

```bash
mkdir -p tests/browser/seed
W=.superpowers/sdd/2026-10-14-browser-suite/recipes
cp $W/dashboards/seed_dashboards.py tests/browser/seed/dashboards.py
cp $W/operations/seed_operations.py tests/browser/seed/operations.py
cp $W/workspace/seed_workspace.py  tests/browser/seed/workspace.py
```

Each recipe is written to run inside the setup's globals (it uses `copilot`, `post`, `SCRATCH`, `APP_AUTH` as globals) and was proven that way. Keep that model: they are executed into the world, not imported. Edit each file's header comment to say so and to name its proof (the plan workspace path is not committed; say "proven 14 Oct 2026 against the dispatch setup").

Then the joining edits, which no recipe made because each was proven alone:

1. In `operations.py`, the Shopify stand-in answered `shopify_list_orders` and `shopify_get_order` from its own twelve orders, hiding the dashboards' thousand. Replace those two branches of `ops_shopify` so the orders live in one store:

```python
# The Production Manager's orders join the dashboards' store, so every screen
# reads one shop: list and get go to it; the rest is this stand-in's own.
DASH["orders"].extend(OPS_ORDERS.values())
DASH["orders"].sort(key=lambda o: int(o["id"]))
```

placed before `_OPS_PREV_TOOL_JSON = copilot._tool_json`, and delete the `if name == "shopify_list_orders":` and `if name == "shopify_get_order":` branches from `ops_shopify` (they now fall through to `dash_tool_json`, which pages `DASH["orders"]`). The same dict objects are shared, so the tag writer's changes are seen by both.

2. `workspace.py` creates `priya` (Priya Nandakumar) and `owen` (Owen Castellano); `operations.py` reuses an existing username. Run workspace before operations (step 5) and leave both files' names as they are.

- [ ] **Step 5: Write `tests/browser/seed/__init__.py`**

```python
"""Fill every screen of the browser suite's world with invented data.

Three recipes, each proven on 14 Oct 2026 against the dispatch setup, run in
this order: dashboards (the fake Shopify store, the saved reports,
reconciliation, the forecast, the Xero connector), workspace (accounts, the
work clock, the activity ledger, memory, skills, requests, chat), operations
(the Production Manager's orders joined to the same store, custom shipments,
the CRM, loan units, the Inbox, Files). They are executed into the world's own
globals, the way they were proven, rather than imported.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ORDER = ("dashboards", "workspace", "operations")


def _run(world, name):
    path = os.path.join(HERE, name + ".py")
    exec(compile(open(path, encoding="utf-8").read(), path, "exec"), world)


def seed(world):
    _run(world, "dashboards")
    world["seed_dashboards"]()          # dashboards.py defines it; the other two run as they load
    _run(world, "workspace")
    _run(world, "operations")
    import json
    with open(os.path.join(world["SCRATCH"], "workspace_browser_seed.json"), encoding="utf-8") as fh:
        browser = json.load(fh)
    return {"localStorage": browser["localStorage"], "orders": len(world["DASH"]["orders"]),
            "ops_orders": len(world["OPS_ORDERS"])}
```

- [ ] **Step 6: Run the world test**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/browser/test_world.py`
Expected: `6 passed, 0 failed`. If a `has(...)` fails, read that recipe's proof output in the plan workspace for the text it actually printed and the route body it used, fix the seed (not the test's text unless the proof shows the test's text was never seeded), and rerun. Two expected trouble spots, from the agents' risks: (a) the operations seed's mail guard asserts the board holds exactly its ten threads; if workspace seeded any mail, loosen it to "at least ten"; (b) the forecast seed imports pandas and statsforecast: `make install` puts `forecast/requirements-service.txt` in `.venv`, so it runs locally; CI installs it in Task 8.

- [ ] **Step 7: Write the fixture privacy guard (failing first)**

Add to `tests/test_frontend.py`:

```python
@test
def t_the_browser_suites_world_is_invented():
    """The repository is public and the browser suite commits a whole world
    of invented people, orders and mail. Every address in it is at an
    example domain, and every phone number is in the range Ofcom keeps for
    drama, so nothing in it can be a real person's."""
    base = os.path.join(ROOT, "tests", "browser")
    bad_mail, bad_phone = [], []
    for dirpath, _dirs, files in os.walk(base):
        if ".run" in dirpath or "node_modules" in dirpath:
            continue
        for f in files:
            if not f.endswith((".py", ".js", ".json")):
                continue
            text = open(os.path.join(dirpath, f), encoding="utf-8").read()
            for m in re.findall(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)", text):
                if m.lower() not in ("example.com", "example.org", "example.net") and not m.lower().endswith(".example"):
                    bad_mail.append(f + ": @" + m)
            for m in re.findall(r"(?<!\d)(?:\+44\s?|0)(\d{4}\s?\d{6})(?!\d)", text):
                if not re.sub(r"\s", "", m).startswith("1632960"):
                    bad_phone.append(f + ": " + m)
    # The shop's own domain, read off the quote site's default so this test
    # does not carry it either (as the environment reference's test does).
    host = re.search(r'PROPOSAL_HOST = os\.environ\.get\("PROPOSAL_HOST", "([^"]+)"\)',
                     open(os.path.join(ROOT, "copilot.py"), encoding="utf-8").read()).group(1)
    domain = host.split(".", 1)[1]
    named = []
    for dirpath, _dirs, files in os.walk(base):
        if ".run" in dirpath or "node_modules" in dirpath:
            continue
        named += [f for f in files if f.endswith((".py", ".js", ".json", ".md"))
                  and domain.split(".")[0].lower() in open(os.path.join(dirpath, f), encoding="utf-8").read().lower()]
    ok(not named, "the browser suite names the shop: %s" % named)
    ok(not bad_mail, "addresses outside the example domains: %s" % bad_mail[:5])
    ok(not bad_phone, "phone numbers outside 01632 960xxx: %s" % bad_phone[:5])
```

Run: `python3 tests/test_frontend.py 2>/dev/null | grep -E "invented|passed"`
Expected: it runs over the copied recipes. If it FAILS, the failure lists the files that name the shop, or the addresses or numbers a recipe used: replace each with an `example.com` address or a `01632 960xxx` number in the seed (keeping names), rerun the world test, then this guard: PASS. If it passes at once, prove it can fail: add `"nobody@gmail.com"` to `seed/__init__.py`'s docstring, run, see FAIL, remove it.

- [ ] **Step 8: Prove the server starts and serves the seeded world**

Run: `PORT=8930 env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python tests/browser/serve.py` in the background; when it prints `browser world ready on http://127.0.0.1:8930`, run `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8930/` and `python3 -c "import json;print(sorted(json.load(open('tests/browser/.run/auth.json'))))"`; then stop the server (`lsof -ti :8930 | xargs kill`).
Expected: `200`, and `['base', 'localStorage', 'master', 'session', 'token']`.

- [ ] **Step 9: Commit**

```bash
printf 'tests/browser/.run/\n' >> .gitignore
git add .gitignore tests/browser/serve.py tests/browser/seed tests/browser/test_world.py tests/test_frontend.py
git commit -m "Browser suite: the seeded world, every screen filled through the app's own code, proven without a browser

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Playwright, the fence and signing in

**Files:**
- Modify: `package.json`, `package-lock.json`
- Create: `tests/browser/playwright.config.js`, `tests/browser/support.js`, `tests/browser/fence.spec.js`, `tests/browser/unit/support.test.js`
- Test: `tests/browser/fence.spec.js`, `tests/browser/unit/support.test.js`

**Interfaces:**
- Consumes: `tests/browser/.run/auth.json` (Task 2).
- Produces (from `support.js`): `prepare(context, baseURL) -> Promise<{outside: string[]}>`; `watch(page, baseURL) -> {inflight, errors[], failed[], writes[]}`; `settle(page, w) -> Promise`; `open(page, w) -> Promise`; `helpers(page, w, project) -> {phone, settle, nav, tab, queue, click, clickText, waitText, waitFor, evaluate}`; `isWrite(url, method, body) -> boolean`; `RUN` (the run directory).

- [ ] **Step 1: Install the pinned packages and Chromium**

```bash
npm install --save-dev --save-exact @playwright/test@1.63.0 @axe-core/playwright@4.13.0 @fontsource-variable/inter@5.3.0
npx playwright install chromium
ls node_modules/@fontsource-variable/inter/files/ | grep -E '^inter-latin-wght-normal\.woff2$'
```
Expected: the three appear under `devDependencies` with exact versions; the font file is listed. If the file is named differently in 5.3.0, use the `latin` `wght` `normal` file that exists and change `INTER` in step 4 to match.

- [ ] **Step 2: Write the failing unit test for `isWrite`**

`tests/browser/unit/support.test.js`:

```js
// node --test tests/browser/unit/
const test = require('node:test');
const assert = require('node:assert');
const { isWrite } = require('../support');

test('a POST whose op names a change is a write', () => {
  for (const op of ['add', 'save', 'delete', 'done', 'claim', 'send', 'book', 'mark_made', 'queue', 'won', 'state', 'request'])
    assert.ok(isWrite('/api/x', 'POST', JSON.stringify({ op })), op);
});
test('reads are not writes', () => {
  for (const body of [{}, { op: 'board' }, { op: 'detail', id: 'd1' }, { op: 'history' }, { months: 24, fresh: true }, { op: 'version' }])
    assert.ok(!isWrite('/api/x', 'POST', JSON.stringify(body)), JSON.stringify(body));
  assert.ok(!isWrite('/api/x', 'GET', null));
});
test('the two writes a screen makes by being looked at are swallowed, not counted', () => {
  assert.ok(!isWrite('/api/updates', 'POST', JSON.stringify({ op: 'seen', releases: 3 })));
  assert.ok(!isWrite('/api/layouts', 'POST', JSON.stringify({ view: 'overview', order: [] })));
  assert.ok(isWrite('/api/updates', 'POST', JSON.stringify({ op: 'request', text: 'x' })));
});
```

Run: `node --test tests/browser/unit/`
Expected: FAIL, `Cannot find module '../support'`.

- [ ] **Step 3: Write the failing fence spec**

`tests/browser/fence.spec.js`:

```js
const { test, expect } = require('@playwright/test');
const S = require('./support');

test('a request to any other host is caught and named', async ({ page, context, baseURL }, info) => {
  test.skip(info.project.name !== 'laptop', 'the fence is checked once');
  const seen = await S.prepare(context, baseURL);
  const w = S.watch(page, baseURL);
  await S.open(page, w);
  // A host the page's CSP allows (img-src names cdn.shopify.com), so it is the
  // fence that catches it: a host the CSP refuses never reaches the network.
  await page.evaluate(() => { const i = new Image(); i.src = 'https://cdn.shopify.com/s/files/suite-proof.png'; document.body.append(i); });
  await page.waitForTimeout(500);
  await S.settle(page, w);
  expect(seen.outside).toEqual(['https://cdn.shopify.com/s/files/suite-proof.png']);
});

test('the page signs in and its fonts load without the internet', async ({ page, context, baseURL }, info) => {
  test.skip(info.project.name !== 'laptop', 'checked once');
  const seen = await S.prepare(context, baseURL);
  const w = S.watch(page, baseURL);
  await S.open(page, w);
  await expect(page.locator('#nav-overview')).toBeAttached();
  expect(await page.evaluate(() => document.fonts.check('16px Inter'))).toBe(true);
  expect(seen.outside).toEqual([]);
  expect(w.errors).toEqual([]);
  expect(w.failed).toEqual([]);
});
```

- [ ] **Step 4: Write `tests/browser/support.js`**

```js
// Shared by every browser spec: signing in, the network fence, the writes a
// screen makes just by being looked at, reaching a state, and settling.
const fs = require('fs');
const path = require('path');

const RUN = process.env.BROWSER_RUN || path.join(__dirname, '.run');
const INTER = require.resolve('@fontsource-variable/inter/files/inter-latin-wght-normal.woff2');
const FONT_URL = 'https://fonts.gstatic.com/reactor-suite/inter.woff2';

// A POST whose op names a change. The suite looks and never writes; the two
// writes the page makes by itself are swallowed in prepare() and skipped here.
const WRITE_OP = /^(add|save|create|update|delete|remove|set|done|undone|claim|release|send|book|cancel|print|mark|queue|archive|won|lost|move|merge|link|unlink|upload|reset|active|tabs|reply|state|request|seen|assign|snooze|dismiss|clear)/i;

function auth() {
  return JSON.parse(fs.readFileSync(path.join(RUN, 'auth.json'), 'utf8'));
}

function isWrite(url, method, body) {
  if (method !== 'POST' || !body) return false;
  let b;
  try { b = JSON.parse(body); } catch (e) { return false; }
  if (/\/api\/updates$/.test(url) && b.op === 'seen') return false;
  if (/\/api\/layouts$/.test(url)) return false;
  return typeof b.op === 'string' && WRITE_OP.test(b.op);
}

async function prepare(context, baseURL) {
  const a = auth();
  const app = new URL(baseURL).host;
  const seen = { outside: [] };
  await context.addInitScript(([t, s, store]) => {
    window.shopify = { idToken: async () => t };
    try {
      localStorage.setItem('sc_app_session', s);
      for (const k of Object.keys(store)) localStorage.setItem(k, store[k]);
    } catch (e) {}
  }, [a.token, a.session, a.localStorage || {}]);
  // The fence: every other host is answered here or refused and named.
  await context.route(u => u.host !== app, async route => {
    const url = route.request().url();
    if (url.startsWith('https://fonts.googleapis.com/css2')) {
      return route.fulfill({ status: 200, contentType: 'text/css',
        body: `@font-face{font-family:'Inter';font-style:normal;font-weight:100 900;font-display:block;src:url(${FONT_URL}) format('woff2');}` });
    }
    if (url === FONT_URL) {
      return route.fulfill({ status: 200, contentType: 'font/woff2', body: fs.readFileSync(INTER), headers: { 'Access-Control-Allow-Origin': '*' } });
    }
    seen.outside.push(url.slice(0, 160));
    return route.abort();
  });
  // The writes a screen makes by being looked at: What's new and Requests
  // mark themselves seen; Customise saves a layout as it closes.
  await context.route(/\/api\/updates$/, async route => {
    if (/"op"\s*:\s*"seen"/.test(route.request().postData() || '')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true,"seen":{}}' });
    }
    return route.fallback();
  });
  await context.route(/\/api\/layouts$/, async route => {
    let b = {};
    try { b = JSON.parse(route.request().postData() || '{}'); } catch (e) {}
    if (['view', 'order', 'hidden', 'reset'].some(k => k in b)) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{"layouts":{}}' });
    }
    return route.fallback();
  });
  return seen;
}

function watch(page, baseURL) {
  const w = { inflight: 0, errors: [], failed: [], writes: [] };
  const mine = u => u.startsWith(baseURL);
  const rel = u => u.slice(baseURL.length);
  page.on('request', r => {
    if (!mine(r.url())) return;
    w.inflight++;
    if (isWrite(r.url(), r.method(), r.postData())) w.writes.push(rel(r.url()) + ' ' + (r.postData() || '').slice(0, 100));
  });
  const done = r => { if (mine(r.url())) w.inflight = Math.max(0, w.inflight - 1); };
  page.on('requestfinished', done);
  page.on('requestfailed', r => { done(r); if (mine(r.url())) w.failed.push('failed ' + rel(r.url())); });
  page.on('response', r => { if (mine(r.url()) && r.status() >= 400) w.failed.push(r.status() + ' ' + rel(r.url())); });
  page.on('pageerror', e => w.errors.push(String((e && e.message) || e).slice(0, 300)));
  page.on('console', m => {
    if (m.type() !== 'error') return;
    const at = (m.location() && m.location().url) || '';
    if (at && !mine(at)) return;                         // a fenced request: counted by the fence
    if (/^Failed to load resource/.test(m.text())) return; // the response itself is counted above
    w.errors.push(m.text().slice(0, 300));
  });
  return w;
}

async function settle(page, w) {
  await page.waitForFunction(() => document.fonts.status === 'loaded', null, { timeout: 15000 });
  const t0 = Date.now();
  for (let quiet = 0; quiet < 4 && Date.now() - t0 < 20000;) {
    await page.waitForTimeout(100);
    const busy = await page.evaluate(() => !![...document.querySelectorAll(
      '.view.active .thinking, .view.active .loader, .view.active .skeleton, [aria-busy="true"]')].find(e => e.offsetParent));
    quiet = w.inflight === 0 && !busy ? quiet + 1 : 0;
  }
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
}

async function open(page, w) {
  await page.goto('/');
  await page.waitForSelector('#nav-overview', { state: 'attached', timeout: 60000 });
  await settle(page, w);
}

// Ported from the local rig's helpers (Oct 2026), each followed by settle().
function helpers(page, w, project) {
  const s = () => settle(page, w);
  return {
    phone: project === 'phone',
    settle: s,
    evaluate: (fn, arg) => page.evaluate(fn, arg),
    nav: async v => {
      await page.evaluate(v => { if (typeof closeDrawer === 'function') closeDrawer(); document.getElementById('nav-' + v).click(); if (typeof closeDrawer === 'function') closeDrawer(); }, v);
      await s();
    },
    tab: async k => {
      await page.evaluate(k => {
        const strip = [...document.querySelectorAll('.view.active .tabs')].find(t => t.offsetParent && !t.querySelector('[aria-current]') && !t.closest('#guide-host'));
        const b = strip && [...strip.querySelectorAll('.tab')].find(t => t.dataset.k === k);
        if (!b) throw new Error('no tab ' + k);
        if (!b.classList.contains('on')) b.click();
      }, k);
      await s();
    },
    queue: async q => {
      await page.evaluate(q => { const b = document.querySelector('#view-labels nav.queues button[data-k="' + q + '"]'); if (!b) throw new Error('no queue ' + q); if (!b.classList.contains('on')) b.click(); }, q);
      await s();
    },
    click: async sel => {
      await page.evaluate(sel => { const e = [...document.querySelectorAll(sel)].find(x => x.offsetParent || x.getClientRects().length); if (!e) throw new Error('nothing visible matches ' + sel); e.click(); }, sel);
      await s();
    },
    clickText: async (scope, text) => {
      await page.evaluate(([scope, text]) => {
        const els = [...document.querySelectorAll((scope || 'body') + ' :is(button, a, [role="button"], [role="tab"], summary, .lbl-row, tr, li)')].filter(e => e.offsetParent || e.getClientRects().length);
        const e = els.find(x => (x.innerText || x.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').startsWith(text));
        if (!e) throw new Error('no "' + text + '" in ' + scope);
        e.click();
      }, [scope, text]);
      await s();
    },
    waitText: async (scope, text, ms) => {
      await page.waitForFunction(([scope, text]) => { const e = document.querySelector(scope); return e && e.innerText.includes(text); }, [scope, text], { timeout: ms || 20000, polling: 200 });
      await s();
    },
    waitFor: async (fn, arg, ms) => {
      await page.waitForFunction(fn, arg, { timeout: ms || 20000, polling: 200 });
      await s();
    },
  };
}

module.exports = { RUN, auth, isWrite, prepare, watch, settle, open, helpers };
```

- [ ] **Step 5: Write `tests/browser/playwright.config.js`**

```js
// The browser suite: every screen of Reactor in Chromium, at three sizes, in
// an invented world. Spec: docs/superpowers/specs/2026-10-14-browser-suite-design.md
const fs = require('fs');
const path = require('path');
const { defineConfig } = require('@playwright/test');

const ROOT = path.join(__dirname, '..', '..');
const PORT = Number(process.env.BROWSER_PORT || 8930);
const PY = process.env.PY || (fs.existsSync(path.join(ROOT, '.venv/bin/python')) ? '.venv/bin/python' : 'python');
const RUN = process.env.BROWSER_RUN || path.join(__dirname, '.run');

module.exports = defineConfig({
  testDir: __dirname,
  testMatch: /\.spec\.js$/,
  outputDir: path.join(RUN, 'results'),
  globalTeardown: path.join(__dirname, 'teardown.js'),
  timeout: 90000,
  expect: { timeout: 20000 },
  fullyParallel: true,
  workers: 4,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { outputFolder: path.join(RUN, 'report'), open: 'never' }]],
  use: { baseURL: `http://127.0.0.1:${PORT}`, trace: 'on-first-retry', reducedMotion: 'reduce', deviceScaleFactor: 1 },
  projects: [
    { name: 'phone', use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
    { name: 'laptop', use: { viewport: { width: 1280, height: 800 } } },
    { name: 'wide', use: { viewport: { width: 1920, height: 1080 } } },
  ],
  webServer: {
    command: `${PY} tests/browser/serve.py`,
    cwd: ROOT,
    url: `http://127.0.0.1:${PORT}/`,
    timeout: 180000,
    reuseExistingServer: !process.env.CI,
    env: { PORT: String(PORT), BROWSER_RUN: RUN },
    stdout: 'ignore',
    stderr: 'pipe',
  },
});
```

Create `tests/browser/teardown.js` as a stub for now (Task 4 fills it):

```js
module.exports = async () => {};
```

- [ ] **Step 6: Run the unit and the fence specs**

Run: `node --test tests/browser/unit/ && npx playwright test -c tests/browser/playwright.config.js fence.spec.js`
Expected: the unit tests pass (3), then `2 passed` (laptop) and `4 skipped`. If the font check fails, the fence did not answer Google Fonts: read `seen.outside` in the failure.

- [ ] **Step 7: Commit**

```bash
git add package.json package-lock.json tests/browser/playwright.config.js tests/browser/support.js tests/browser/teardown.js tests/browser/fence.spec.js tests/browser/unit/support.test.js
git commit -m "Browser suite: Playwright, the network fence, signing in, and what counts as a write

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The ratchet record

**Files:**
- Create: `tests/browser/record.js`, `tests/browser/unit/record.test.js`
- Modify: `tests/browser/teardown.js`
- Test: `tests/browser/unit/record.test.js`

**Interfaces:**
- Produces: `counts(pairs: [string, number][]) -> {[rule]: number}` (zeros dropped); `compare(recorded, observed) -> {worse: string[], better: string[]}`; `check(kind: 'a11y'|'panels', key: string, observed) -> {worse, better}` (writes `RUN/observed/<kind>/<key>.json`; reads `record/<kind>.json`); `merge(kind) -> object` (all observed, sorted); `write(kind, obj)`; `UPDATE` (boolean).

- [ ] **Step 1: Write the failing tests**

`tests/browser/unit/record.test.js`:

```js
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'record-'));
process.env.BROWSER_RUN = path.join(tmp, 'run');
process.env.BROWSER_RECORD = path.join(tmp, 'record');
fs.mkdirSync(process.env.BROWSER_RECORD, { recursive: true });
const R = require('../record');

test('counts adds up by rule and drops zeros', () => {
  assert.deepStrictEqual(R.counts([['color-contrast', 3], ['label', 0], ['color-contrast', 2], ['region', 1]]), { 'color-contrast': 5, region: 1 });
});
test('a count above the record is worse', () => {
  assert.deepStrictEqual(R.compare({ label: 1 }, { label: 2 }), { worse: ['label: 1 -> 2'], better: [] });
  assert.deepStrictEqual(R.compare({}, { region: 1 }), { worse: ['region: 0 -> 1'], better: [] });
});
test('a count below the record is better, and must be taken off the record', () => {
  assert.deepStrictEqual(R.compare({ label: 2, region: 1 }, { label: 1 }), { worse: [], better: ['label: 2 -> 1', 'region: 1 -> 0'] });
});
test('an equal count passes', () => {
  assert.deepStrictEqual(R.compare({ label: 2 }, { label: 2 }), { worse: [], better: [] });
});
test('check reads the committed record and leaves what it saw for the teardown', () => {
  fs.writeFileSync(path.join(process.env.BROWSER_RECORD, 'a11y.json'), JSON.stringify({ 'overview@laptop': { label: 1 } }));
  assert.deepStrictEqual(R.check('a11y', 'overview@laptop', { label: 1 }), { worse: [], better: [] });
  assert.deepStrictEqual(R.check('a11y', 'seo@laptop', { region: 2 }), { worse: ['region: 0 -> 2'], better: [] });
  assert.deepStrictEqual(R.merge('a11y'), { 'overview@laptop': { label: 1 }, 'seo@laptop': { region: 2 } });
});
test('the record is written sorted, so its diff in a pull request reads', () => {
  R.write('panels', { 'b@wide': { z: 1, a: 2 }, 'a@phone': {} });
  assert.strictEqual(fs.readFileSync(path.join(process.env.BROWSER_RECORD, 'panels.json'), 'utf8'),
    '{\n  "a@phone": {},\n  "b@wide": {\n    "a": 2,\n    "z": 1\n  }\n}\n');
});
```

Run: `node --test tests/browser/unit/`
Expected: record tests FAIL, `Cannot find module '../record'`.

- [ ] **Step 2: Write `tests/browser/record.js`**

```js
// The ratchet. A record is {"<screen>@<size>": {"<rule>": count}}. A count
// above the record is a new problem; a count below it is a fixed one the
// record still allows, which would let a later regression hide in the slack.
// Both fail. UPDATE_RECORD=1 rewrites the record from the run (teardown.js),
// and the diff of record/*.json in the pull request shows what changed.
const fs = require('fs');
const path = require('path');

const RUN = process.env.BROWSER_RUN || path.join(__dirname, '.run');
const RECORD = process.env.BROWSER_RECORD || path.join(__dirname, 'record');
const UPDATE = process.env.UPDATE_RECORD === '1';

function counts(pairs) {
  const out = {};
  for (const [rule, n] of pairs) if (n) out[rule] = (out[rule] || 0) + n;
  return out;
}

function compare(recorded, observed) {
  const a = recorded || {}, b = observed || {};
  const worse = [], better = [];
  for (const r of [...new Set([...Object.keys(a), ...Object.keys(b)])].sort()) {
    const x = a[r] || 0, y = b[r] || 0;
    if (y > x) worse.push(`${r}: ${x} -> ${y}`);
    else if (y < x) better.push(`${r}: ${x} -> ${y}`);
  }
  return { worse, better };
}

function load(kind) {
  try { return JSON.parse(fs.readFileSync(path.join(RECORD, kind + '.json'), 'utf8')); }
  catch (e) { if (e.code === 'ENOENT') return {}; throw e; }
}

function check(kind, key, observed) {
  const dir = path.join(RUN, 'observed', kind);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, encodeURIComponent(key) + '.json'), JSON.stringify(observed));
  return compare(load(kind)[key], observed);
}

function merge(kind) {
  const dir = path.join(RUN, 'observed', kind);
  const out = {};
  if (!fs.existsSync(dir)) return out;
  for (const f of fs.readdirSync(dir).sort()) out[decodeURIComponent(f.replace(/\.json$/, ''))] = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
  return out;
}

function sorted(v) {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return v;
  return Object.fromEntries(Object.keys(v).sort().map(k => [k, sorted(v[k])]));
}

function write(kind, obj) {
  fs.mkdirSync(RECORD, { recursive: true });
  fs.writeFileSync(path.join(RECORD, kind + '.json'), JSON.stringify(sorted(obj), null, 2) + '\n');
}

module.exports = { RUN, RECORD, UPDATE, counts, compare, check, merge, write, load };
```

- [ ] **Step 3: Write `tests/browser/teardown.js`**

```js
// After a run: keep what was seen (CI uploads it), and rewrite the record
// when UPDATE_RECORD=1. A partial run (a filtered or failed one) never
// rewrites: a record built from part of the screens would drop the rest.
const fs = require('fs');
const path = require('path');
const R = require('./record');

module.exports = async () => {
  for (const kind of ['a11y', 'panels']) {
    const seen = R.merge(kind);
    fs.mkdirSync(R.RUN, { recursive: true });
    fs.writeFileSync(path.join(R.RUN, `observed-${kind}.json`), JSON.stringify(seen, null, 2) + '\n');
    if (!R.UPDATE) continue;
    const expected = Number(process.env.BROWSER_EXPECTED_STATES || 0);
    if (expected && Object.keys(seen).length !== expected) {
      console.log(`record/${kind}.json NOT rewritten: the run saw ${Object.keys(seen).length} of ${expected} states`);
      continue;
    }
    R.write(kind, seen);
    console.log(`record/${kind}.json rewritten from ${Object.keys(seen).length} states`);
  }
};
```

- [ ] **Step 4: Run the unit tests**

Run: `node --test tests/browser/unit/`
Expected: all pass (3 support + 6 record).

- [ ] **Step 5: Commit**

```bash
git add tests/browser/record.js tests/browser/teardown.js tests/browser/unit/record.test.js
git commit -m "Browser suite: the ratchet record, which fails on a new problem and on a fixed one left on the record

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The in-page measures

**Files:**
- Create: `tests/browser/probes.js`, `tests/browser/probes.spec.js`
- Test: `tests/browser/probes.spec.js`

**Interfaces:**
- Produces: `measure(page) -> Promise<{sideways: string[], spill: string[], panels: {bad, loose, nested, gaps, heights, vanish, lone, inset, short}}>` (each a list of described elements); `panelCounts(m) -> {[rule]: number}` (zeros dropped); `SKIP`, `HOLD` (the page's own `PANEL_SKIP` / `PANEL_HOLD`, read from `static/index.html`).

- [ ] **Step 1: Write the failing spec against synthetic pages**

`tests/browser/probes.spec.js`:

```js
const { test, expect } = require('@playwright/test');
const P = require('./probes');

const shell = body => `<!doctype html><html><head><style>
  body { margin: 0; font: 14px sans-serif; } .ov-wrap { display: grid; gap: 20px; padding: 20px; }
  .panel { background: #fff; border: 1px solid #ddd; padding: 20px 24px; }
  .pair { display: flex; gap: 20px; align-items: flex-start; }
</style></head><body><main class="view active"><div class="ov-wrap">${body}</div></main></body></html>`;

test.describe('the probes', () => {
  test.beforeEach(({}, info) => test.skip(info.project.name !== 'laptop', 'synthetic pages are measured once'));

  test('a clean page has nothing to report', async ({ page }) => {
    await page.setContent(shell('<section class="panel"><h2>Sales</h2><p>Text</p></section>'));
    const m = await P.measure(page);
    expect(m.sideways).toEqual([]);
    expect(m.spill).toEqual([]);
    expect(P.panelCounts(m)).toEqual({});
  });

  test('content wider than its panel spills, unless a scroller holds it', async ({ page }) => {
    await page.setContent(shell('<section class="panel" id="a"><div style="width:2000px">wide</div></section>'
      + '<section class="panel" id="b"><div style="overflow-x:auto"><div style="width:2000px">wide</div></div></section>'));
    const m = await P.measure(page);
    expect(m.spill.length).toBe(1);
    expect(m.spill[0]).toContain('div');
    expect(m.sideways.length).toBe(1);
  });

  test('a section that is not a panel, a panel in a panel, and unequal neighbours are counted', async ({ page }) => {
    await page.setContent(shell('<section class="loose"><p>floating</p></section>'
      + '<section class="panel"><div class="panel">inner</div></section>'
      + '<div class="pair-holder" style="display:flex;gap:20px"><section class="panel" style="flex:1;height:100px">a</section><section class="panel" style="flex:1;height:160px">b</section></div>'));
    const c = P.panelCounts(await P.measure(page));
    expect(c.bad).toBeGreaterThanOrEqual(1);
    expect(c.nested).toBe(1);
    expect(c.heights).toBe(1);
  });
});
```

Run: `npx playwright test -c tests/browser/playwright.config.js probes.spec.js`
Expected: FAIL, `Cannot find module './probes'`.

- [ ] **Step 2: Write `tests/browser/probes.js`**

Port of the 13 Oct panels probe (the rig's `clusters/probe-panels.js`, uncommitted), plus sideways scroll and spill. The panel lists are read from the page source so the probe never drifts from them.

```js
// What is measured in the page after a screen settles. Two checks must be
// zero on every screen (sideways scroll, content spilling out of its panel);
// the panel rules are counted per rule and held by the ratchet (record.js).
const fs = require('fs');
const path = require('path');

const APP = fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'index.html'), 'utf8');
const list = name => JSON.parse(new RegExp(`const ${name} = (\\[[^\\]]*\\])`).exec(APP)[1].replace(/'/g, '"'));
const SKIP = list('PANEL_SKIP');
const HOLD = list('PANEL_HOLD');

async function measure(page) {
  return page.evaluate(([SKIP, HOLD]) => {
    const vis = n => n.getClientRects().length && getComputedStyle(n).display !== 'none' && getComputedStyle(n).visibility !== 'hidden';
    const desc = n => (n.tagName.toLowerCase() + (n.id ? '#' + n.id : '') + ([...n.classList].length ? '.' + [...n.classList].join('.') : '')).slice(0, 80);
    const clips = s => /(auto|scroll|hidden|clip)/.test(s.overflowX);

    // Sideways scroll: the document, or the app's own scrolling column.
    const sideways = [document.scrollingElement, document.querySelector('.main')].filter(Boolean)
      .filter(e => e.scrollWidth > e.clientWidth + 1 && !(e !== document.scrollingElement && clips(getComputedStyle(e))))
      .map(e => desc(e) + ' ' + (e.scrollWidth - e.clientWidth) + 'px');

    const roots = [...document.querySelectorAll('.view.active .ov-wrap')];
    const panels = [...document.querySelectorAll('.view.active .ov-wrap .panel, .view.active .panel')].filter(vis)
      .filter((n, i, a) => a.indexOf(n) === i && !n.parentElement.closest('.panel'));
    const R = panels.map(n => ({ n, r: n.getBoundingClientRect() }));

    // Spill: a visible element wider than its panel, not held by a scroller or a clip.
    const spill = [], spilt = [];
    for (const { n: pn, r: pr } of R) {
      if (clips(getComputedStyle(pn))) continue;
      for (const e of pn.querySelectorAll('*')) {
        if (!vis(e)) continue;
        const r = e.getBoundingClientRect();
        if (!r.width || !r.height || (r.right <= pr.right + 1 && r.left >= pr.left - 1)) continue;
        let a = e.parentElement, held = false;
        while (a && a !== pn) { if (clips(getComputedStyle(a))) { held = true; break; } a = a.parentElement; }
        // One line per overflowing block, not one per element inside it.
        if (!held && !spilt.some(x => x.contains(e))) { spilt.push(e); spill.push(desc(e) + ' ' + Math.round(Math.max(r.right - pr.right, pr.left - r.left)) + 'px past ' + desc(pn)); }
      }
    }

    // The panel rules (13 Oct).
    const bad = [];
    const walk = n => {
      if (!vis(n) || SKIP.some(c => n.classList.contains(c))) return;
      if (!n.className || HOLD.some(c => n.classList.contains(c))) { [...n.children].forEach(walk); return; }
      const cs = getComputedStyle(n);
      const painted = cs.backgroundColor !== 'rgba(0, 0, 0, 0)' && (cs.borderTopWidth !== '0px' || cs.boxShadow !== 'none' || cs.outlineStyle !== 'none');
      if (!n.classList.contains('panel') || !painted) bad.push(desc(n));
    };
    roots.forEach(r => [...r.children].forEach(walk));
    const loose = [...document.querySelectorAll('.view.active .ov-wrap :is(.section-title, .card-title, h2, h3)')].filter(vis)
      .filter(h => !h.closest('.panel') && !h.closest('.ov-hero, .fband, .miss-strip, .modal')).map(desc);
    const nested = [...document.querySelectorAll('.view.active .panel .panel')].filter(vis).map(desc);
    const gap = innerWidth <= 640 ? 12 : 20;
    const gaps = [], heights = [];
    for (const a of R) {
      const below = R.filter(b => b !== a && b.r.top >= a.r.bottom - 1 && Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left) > 8).sort((x, y) => x.r.top - y.r.top)[0];
      if (below && Math.abs(below.r.top - a.r.bottom - gap) > 1) gaps.push('v ' + Math.round(below.r.top - a.r.bottom) + ': ' + desc(a.n));
      const right = R.filter(b => b !== a && b.r.left >= a.r.right - 1 && Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top) > 8).sort((x, y) => x.r.left - y.r.left)[0];
      if (right && Math.abs(right.r.left - a.r.right - gap) > 1) gaps.push('h ' + Math.round(right.r.left - a.r.right) + ': ' + desc(a.n));
      if (right && Math.abs(right.r.top - a.r.top) <= 1 && Math.abs(right.r.bottom - a.r.bottom) > 1 && getComputedStyle(a.n.parentElement).columnCount === 'auto') heights.push(desc(a.n) + ' | ' + desc(right.n));
    }
    const greyish = c => { const m = c.match(/\d+/g); if (!m || (c.startsWith('rgba') && +m[3] === 0)) return false; const [r, g, b] = m.map(Number); return r >= 236 && r <= 246 && Math.abs(r - g) <= 3 && Math.abs(g - b) <= 3; };
    const vanish = [...document.querySelectorAll('.view.active :is(.segmented, input, select, textarea, .btn, .tabs)')].filter(vis)
      .filter(n => !n.closest('.panel, .modal, .fband, .miss-strip')).filter(n => greyish(getComputedStyle(n).backgroundColor) && getComputedStyle(n).boxShadow === 'none' && getComputedStyle(n).borderTopWidth === '0px').map(desc);
    const lone = panels.filter(n => n.matches('.section-title, .card-title, h2, h3') || ([...n.children].filter(vis).length === 1 && [...n.children].filter(vis)[0].matches('.section-title, .card-title, h2, h3'))).map(desc);
    const inset = [], short = [];
    for (const { n: pn, r: pr } of R) {
      if (pn.classList.contains('metrics')) continue;
      const cs = getComputedStyle(pn);
      const padL = parseFloat(cs.paddingLeft) + parseFloat(cs.borderLeftWidth), padR = parseFloat(cs.paddingRight) + parseFloat(cs.borderRightWidth);
      const cw = pr.width - padL - padR;
      for (const e of pn.querySelectorAll('*')) {
        if (!vis(e)) continue;
        const es = getComputedStyle(e);
        const ruled = (parseFloat(es.borderBottomWidth) >= 1 && es.borderBottomStyle !== 'none' && !es.borderBottomColor.endsWith(', 0)'))
          || (parseFloat(es.borderTopWidth) >= 1 && es.borderTopStyle !== 'none' && !es.borderTopColor.endsWith(', 0)'));
        if (!ruled) continue;
        const r = e.getBoundingClientRect();
        if (r.width >= cw * 0.9 && Math.abs(r.left - (pr.left + padL)) <= 2 && Math.abs(r.right - (pr.right - padR)) <= 2) inset.push(desc(e));
        const c = e.parentElement, cr = c.getBoundingClientRect();
        if (cr.width >= cw * 0.9 && r.width < cr.width * 0.85 && r.width >= 40 && Math.abs(r.left - cr.left) <= 2
          && ![...c.children].some(s => s !== e && vis(s) && Math.abs(s.getBoundingClientRect().top - r.top) < 3 && s.getBoundingClientRect().left >= r.right - 1)) short.push(desc(e));
      }
    }
    return { sideways, spill, panels: { bad, loose, nested, gaps, heights, vanish, lone, inset: [...new Set(inset)], short: [...new Set(short)] } };
  }, [SKIP, HOLD]);
}

function panelCounts(m) {
  const out = {};
  for (const [rule, items] of Object.entries(m.panels)) if (items.length) out[rule] = items.length;
  return out;
}

module.exports = { measure, panelCounts, SKIP, HOLD };
```

- [ ] **Step 3: Run the probe spec**

Run: `npx playwright test -c tests/browser/playwright.config.js probes.spec.js`
Expected: `3 passed`, `6 skipped`. If "a clean page" reports `bad` for the plain `section.panel` (no class lists in SKIP/HOLD apply), check `painted`: the synthetic panel has a background and a border, so it must pass; fix the probe, not the page.

- [ ] **Step 4: Commit**

```bash
git add tests/browser/probes.js tests/browser/probes.spec.js
git commit -m "Browser suite: the in-page measures, sideways scroll, spill and the panel rules, proven on synthetic pages

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Every screen at every size

**Files:**
- Create: `tests/browser/screens.js`, `tests/browser/pages.spec.js`, `tests/browser/unit/screens.test.js`, `tests/browser/record/a11y.json`, `tests/browser/record/panels.json`
- Modify (only if a day-one zero-tolerance failure needs it): `static/index.html`, `data/changelog.json`, `tests/test_frontend.py`
- Test: `tests/browser/unit/screens.test.js`, `tests/browser/pages.spec.js`

**Interfaces:**
- Consumes: `support.js` (Task 3), `record.js` (Task 4), `probes.js` (Task 5), the seeded world (Task 2).
- Produces: `screens.js` exports an array of `{id, view, kind: 'page'|'dialog', go: async (page, h) => void, opener?: {sel, text?}, before?: async (page, h) => void}`; for dialogs `go` = `before` + open the `opener` + wait for `.modal-overlay.show .modal`.

- [ ] **Step 1: Write the failing screens unit test**

`tests/browser/unit/screens.test.js`:

```js
const test = require('node:test');
const assert = require('node:assert');
const SCREENS = require('../screens');

test('36 states, each named once', () => {
  assert.strictEqual(SCREENS.length, 36);
  assert.strictEqual(new Set(SCREENS.map(s => s.id)).size, 36);
});
test('every screen waits for seeded content before it is measured', () => {
  for (const s of SCREENS) {
    const src = (s.before ? s.before.toString() : '') + s.go.toString();
    assert.ok(/waitText|waitFor|waitForSelector/.test(src), s.id + ' never waits for its content, so its empty state could be measured');
  }
});
test('a dialog names the control that opens it', () => {
  for (const s of SCREENS.filter(x => x.kind === 'dialog')) assert.ok(s.opener && s.opener.sel && s.before, s.id);
});
```

Run: `node --test tests/browser/unit/`
Expected: FAIL, `Cannot find module '../screens'`.

- [ ] **Step 2: Write `tests/browser/screens.js`**

The navigation and seeded texts come from the recipes' proofs (`journal.jsonl` in the plan workspace, each screen's `reach`).

```js
// The states the suite measures. Each `go` ends by waiting for content only
// the seed puts there, so an empty state is never measured by mistake.
// Never click anything that writes: open tabs, rows and dialogs only.
const dialog = (id, view, before, opener) => ({
  id, view, kind: 'dialog', before, opener,
  go: async (page, h) => {
    await before(page, h);
    await page.evaluate(({ sel, text }) => {
      const e = [...document.querySelectorAll(sel)].filter(x => x.offsetParent || x.getClientRects().length)
        .find(x => !text || (x.innerText || '').trim().startsWith(text));
      if (!e) throw new Error('no opener ' + sel + ' ' + (text || ''));
      e.setAttribute('data-suite-opener', '');
      e.click();
    }, opener);
    await page.waitForSelector('.modal-overlay.show .modal');
    await h.settle();
  },
});
const page = (id, view, go) => ({ id, view, kind: 'page', go });

const crmBefore = async (p, h) => { await h.nav('crm'); await p.waitForSelector('#crm-content .tabs'); };
const labelsBefore = async (p, h) => { await h.nav('labels'); await h.waitText('#labels-content', '#210388'); };

module.exports = [
  page('overview', 'overview', async (p, h) => { await h.nav('overview'); await h.waitText('#ov-content', 'Revenue is up on last week'); }),
  page('seo', 'seo', async (p, h) => { await h.nav('seo'); await h.waitText('#seo-content', 'The store is indexable'); }),
  page('keywords', 'keywords', async (p, h) => { await h.nav('keywords'); await h.waitText('#keywords-content', 'custom gobo'); }),
  // 'Load products' is a read: POST /api/products {months, fresh}, no AI, no store write.
  page('products', 'products', async (p, h) => { await h.nav('products'); await h.click('#products-content .run-gate .btn-primary'); await h.waitText('#products-content', 'Walkway Safety Sign Gobo', 40000); }),
  page('customers', 'customers', async (p, h) => {
    await h.nav('customers'); await h.waitText('#customers-content', 'Champions');
    await h.waitFor(() => { const s = document.querySelector('#trade-radar-slot'); return s && s.innerText.trim().length > 20; });
  }),
  page('liability', 'liability', async (p, h) => { await h.nav('liability'); await h.waitFor(() => !!document.querySelector('#liability-content [data-widget="owing"] .dt-row'), null, 30000); }),
  page('recon', 'recon', async (p, h) => { await h.nav('recon'); await h.waitFor(() => !!document.querySelector('#recon-content .dt-row.click')); }),
  page('forecast', 'forecast', async (p, h) => { await h.nav('forecast'); await h.waitFor(() => { const c = document.querySelector('#forecast-content'); return c && !c.innerText.includes('Loading') && c.innerText.includes('Expected this month'); }); }),
  page('connector', 'connector', async (p, h) => { await h.nav('connector'); await h.waitFor(() => { const c = document.querySelector('#connector-content'); return c && c.innerText.includes('Xero linked') && c.innerText.includes('Runs'); }); }),
  page('labels', 'labels', labelsBefore),
  page('labels~make-open', 'labels', async (p, h) => { await labelsBefore(p, h); await h.click('#labels-content .lbl-qrow'); await p.waitForSelector('#labels-content .lbl-preview'); await h.settle(); }),
  page('labels~shipments', 'labels', async (p, h) => { await h.nav('labels'); await h.queue('shipments'); await h.waitText('#labels-content', 'Replacement gobo'); }),
  page('sizes', 'sizes', async (p, h) => { await h.nav('sizes'); await p.waitForSelector('#sizes-content tr.sizes-row'); await h.settle(); }),
  page('crm~leads', 'crm', async (p, h) => { await crmBefore(p, h); await h.tab('leads'); await h.waitText('#crm-content', 'Rental stock enquiry'); }),
  page('crm~activities', 'crm', async (p, h) => { await crmBefore(p, h); await h.tab('activities'); await h.waitText('#crm-content', 'Site visit for window throw'); }),
  page('crm~insights', 'crm', async (p, h) => { await crmBefore(p, h); await h.tab('insights'); await h.waitText('#crm-content', 'Won by month'); }),
  page('crm~contacts', 'crm', async (p, h) => { await crmBefore(p, h); await h.tab('contacts'); await h.waitText('#crm-content', 'Marcus Bell'); }),
  page('loans', 'loans', async (p, h) => { await h.nav('loans'); await h.waitText('#loans-content', 'Quayside Exhibitions'); }),
  // Never open a thread here: opening one marks it read, a Gmail write.
  page('mail', 'mail', async (p, h) => { await h.nav('mail'); await h.waitText('#mail-content', 'Artwork for the autumn tour gobos'); }),
  page('files', 'files', async (p, h) => { await h.nav('files'); await h.waitText('#files-content', 'Artwork'); }),
  page('team~people', 'team', async (p, h) => { await h.nav('team'); await h.tab('people'); await h.waitText('#team-content', 'Hattie Brennan'); }),
  page('team~work', 'team', async (p, h) => { await h.nav('team'); await h.tab('work'); await h.waitText('#team-content', 'Recent sessions'); await h.waitText('#team-content', 'Jonah Featherstone'); }),
  page('team~activity', 'team', async (p, h) => { await h.nav('team'); await h.tab('activity'); await h.waitText('#team-content', 'Jonah Featherstone'); }),
  page('memory', 'memory', async (p, h) => { await h.nav('memory'); await h.waitText('#memory-content', 'Tracked changes'); }),
  page('skills', 'skills', async (p, h) => { await h.nav('skills'); await h.waitText('#skills-content', 'Quoting custom gobos'); }),
  // Conversations come from localStorage (the seed hands them over in auth.json).
  page('chat', 'chat', async (p, h) => { await h.nav('chat'); await h.waitText('#convos', 'How did September'); await h.evaluate(() => document.getElementById('new-convo').click()); await h.settle(); }),
  page('chat~convo', 'chat', async (p, h) => {
    await h.nav('chat'); await h.waitText('#convos', 'How did September');
    await h.evaluate(t => [...document.querySelectorAll('#convos .convo .title')].find(x => x.textContent.trim().startsWith(t)).click(), 'How did September');
    await h.waitText('#view-chat', 'September was up on August');
  }),
  page('guide', 'guide', async (p, h) => { await h.nav('guide'); await h.tab('guide'); await h.waitText('#guide-content', 'Your first day'); }),
  page('guide~new', 'guide', async (p, h) => { await h.nav('guide'); await h.tab('new'); await h.waitText('#guide-content', 'Show older releases'); }),
  page('guide~requests', 'guide', async (p, h) => {
    await h.nav('guide'); await h.tab('requests'); await h.waitText('#guide-content', 'Hattie Brennan');
    await h.evaluate(() => [...document.querySelectorAll('#guide-content .segmented button')].find(b => b.textContent.trim().startsWith('All')).click());
    await h.settle();
  }),
  page('guide~design', 'guide', async (p, h) => { await h.nav('guide'); await h.tab('design'); await h.waitFor(() => !!document.querySelector('#guide-content .ds-page')); }),
  // Customise saves a layout as it closes; prepare() swallows that write.
  page('customers~customise', 'customers', async (p, h) => {
    await h.nav('customers'); await h.waitText('#customers-content', 'Champions');
    await h.waitFor(() => { const b = document.querySelector('#view-customers [data-wg-customize]'); return b && !b.disabled; });
    await h.click('#view-customers [data-wg-customize]'); await h.waitFor(() => !!document.querySelector('#customers-content.wg-editing'));
  }),
  page('overview~customise', 'overview', async (p, h) => {
    await h.nav('overview'); await h.waitText('#ov-content', 'Revenue is up on last week');
    await h.waitFor(() => { const b = document.querySelector('#view-overview [data-wg-customize]'); return b && !b.disabled; });
    await h.click('#view-overview [data-wg-customize]'); await h.waitFor(() => !!document.querySelector('#ov-content.wg-editing'));
  }),
  dialog('crm~deal', 'crm', async (p, h) => { await crmBefore(p, h); await h.tab('deals'); await h.waitText('#crm-content', 'Fernhill walkway safety signs'); }, { sel: '#crm-content .crm-card' }),
  dialog('loans~unit', 'loans', async (p, h) => { await h.nav('loans'); await h.waitText('#loans-content', 'Quayside Exhibitions'); }, { sel: '#loans-content [title="Edit this unit"]' }),
  // The size rule window opens only from the Production Manager's Size check.
  dialog('sizes~rule', 'labels', async (p, h) => {
    await labelsBefore(p, h); await h.queue('make'); await h.click('#labels-content .more-btn');
    await h.clickText('.dmenu', 'Size check'); await h.waitText('#labels-content', 'Moonbeam Profile 300');
  }, { sel: '#labels-content button', text: 'Resolve' }),
];
```

Run: `node --test tests/browser/unit/`
Expected: all pass.

- [ ] **Step 3: Write `tests/browser/pages.spec.js`**

```js
// Every state, at every size: no script error, no failed or outside request,
// no write, no sideways scroll, nothing spilling out of its panel; and the
// panel rules and accessibility (WCAG 2.2 A and AA) held by the ratchet.
const path = require('path');
const fs = require('fs');
const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const S = require('./support');
const P = require('./probes');
const R = require('./record');
const SCREENS = require('./screens');

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

for (const s of SCREENS) {
  test(s.id, async ({ page, context, baseURL }, info) => {
    const seen = await S.prepare(context, baseURL);
    const w = S.watch(page, baseURL);
    await S.open(page, w);
    const h = S.helpers(page, w, info.project.name);
    await s.go(page, h);
    await S.settle(page, w);
    const key = `${s.id}@${info.project.name}`;
    const shots = path.join(S.RUN, 'shots');
    fs.mkdirSync(shots, { recursive: true });
    await page.screenshot({ path: path.join(shots, `${info.project.name}-${s.id.replace(/~/g, '-')}.png`), fullPage: true });

    expect(w.errors, 'script errors').toEqual([]);
    expect(w.failed, 'failed requests to the app').toEqual([]);
    expect(seen.outside, 'requests to other hosts').toEqual([]);
    expect(w.writes, 'the screen wrote something').toEqual([]);
    const m = await P.measure(page);
    expect(m.sideways, 'sideways scroll').toEqual([]);
    expect(m.spill, 'content spilling out of its panel').toEqual([]);

    const ax = await new AxeBuilder({ page }).withTags(TAGS).analyze();
    const a11y = R.check('a11y', key, R.counts(ax.violations.map(v => [v.id, v.nodes.length])));
    const panels = R.check('panels', key, P.panelCounts(m));
    if (!R.UPDATE) {
      expect(a11y.worse, 'new accessibility problems').toEqual([]);
      expect(panels.worse, 'new panel-rule problems').toEqual([]);
      expect(a11y.better, 'fixed: lower the record with UPDATE_RECORD=1 make test-browser').toEqual([]);
      expect(panels.better, 'fixed: lower the record with UPDATE_RECORD=1 make test-browser').toEqual([]);
    }
  });
}
```

- [ ] **Step 4: First run, recording the ratchet**

Run: `BROWSER_EXPECTED_STATES=108 UPDATE_RECORD=1 npx playwright test -c tests/browser/playwright.config.js pages.spec.js`
Expected: 108 tests. Under `UPDATE_RECORD=1` the ratchet does not fail, so every failure here is a zero-tolerance one or a screen that never reached its content. The teardown writes `record/a11y.json` and `record/panels.json` only if all 108 were seen.

- [ ] **Step 5: Fix every day-one zero-tolerance failure**

For each failing test, read its message, its screenshot in `tests/browser/.run/shots/` and its trace (`npx playwright show-trace tests/browser/.run/results/<test>/trace.zip` on a retry). Classify:
- **A screen that never reached its content** (a `waitText` timed out): the seed or the step is wrong, not the app. Check the recipe's proof for that screen in `journal.jsonl`; fix `screens.js` or the seed; `test_world.py` must stay green.
- **A script error, a failed app request, sideways scroll or spill in the app itself:** use superpowers:systematic-debugging. Write a failing test first in the repo's existing style (a `tests/test_frontend.py` guard or node-harness test for page logic, a `tests/test_dispatch.py` test for a route), fix `static/index.html` or `copilot.py` at the cause, never the measure. Each fix gets a `data/changelog.json` item under one release dated the merge day, in plain words (no developer words, no dashes).
- **An outside request or a write:** if the app makes it by itself on load, it is either expected (add it to the fence or the swallowed writes only with a comment saying why) or a fault (fix it as above).
Rerun `UPDATE_RECORD=1 ... pages.spec.js` until all 108 pass and the records are written.

- [ ] **Step 6: Run strictly**

Run: `npx playwright test -c tests/browser/playwright.config.js pages.spec.js`
Expected: `108 passed`. Then run it a second time: still 108 passed (the record is stable run to run; if a count flips between runs, find the timing cause in `settle` or the screen's `go`, never widen the record).

- [ ] **Step 7: Commit**

```bash
git add tests/browser/screens.js tests/browser/pages.spec.js tests/browser/unit/screens.test.js tests/browser/record
git commit -m "Browser suite: 36 states at three sizes, zero script errors, failed requests, writes, sideways scroll or spill; panel rules and accessibility recorded

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
(If Step 5 changed the app, commit each fix separately first, with its test and its release note.)

---

### Task 7: The keyboard journeys

**Files:**
- Create: `tests/browser/keyboard.spec.js`
- Modify (only if a journey fails on day one): `static/index.html`, `tests/test_frontend.py`, `data/changelog.json`
- Test: `tests/browser/keyboard.spec.js`

**Interfaces:**
- Consumes: `screens.js` dialog entries (`before`, `opener`), `support.js`.

- [ ] **Step 1: Write the spec**

```js
// Three dialogs, by keyboard: focus moves into the dialog when it opens,
// Escape closes it, and focus goes back to what opened it. Nothing is saved.
const { test, expect } = require('@playwright/test');
const S = require('./support');
const SCREENS = require('./screens');

for (const s of SCREENS.filter(x => x.kind === 'dialog')) {
  test(`keyboard: ${s.id}`, async ({ page, context, baseURL }, info) => {
    test.skip(info.project.name !== 'laptop', 'the journeys run once, at laptop size');
    await S.prepare(context, baseURL);
    const w = S.watch(page, baseURL);
    await S.open(page, w);
    await s.go(page, S.helpers(page, w, info.project.name));
    expect(await page.evaluate(() => !!document.activeElement.closest('.modal-overlay.show .modal')), 'focus moved into the dialog').toBe(true);
    await page.keyboard.press('Escape');
    await expect(page.locator('.modal-overlay.show')).toHaveCount(0);
    expect(await page.evaluate(() => { const o = document.querySelector('[data-suite-opener]'); return !!o && (document.activeElement === o || o.contains(document.activeElement)); }),
      'focus went back to what opened the dialog').toBe(true);
    expect(w.writes).toEqual([]);
  });
}
```

- [ ] **Step 2: Run it**

Run: `npx playwright test -c tests/browser/playwright.config.js keyboard.spec.js`
Expected: `3 passed`. A journey that fails is a day-one fault in the app: write the failing test in the page suite first (the dialog code is `syncDialogs()` and the modal open/close functions in `static/index.html`), fix it for every dialog at the cause, add a release note, rerun this spec and the whole `pages.spec.js` (a focus fix can change the accessibility counts: lower the record if so).

- [ ] **Step 3: Commit**

```bash
git add tests/browser/keyboard.spec.js
git commit -m "Browser suite: three dialogs by keyboard, focus in, Escape out, focus back

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Commands, CI and documents

**Files:**
- Modify: `Makefile`, `.github/workflows/tests.yml`, `docs/ARCHITECTURE.md`, `README.md`
- Create: `tests/browser/README.md`

- [ ] **Step 1: `make test-browser` and `make check`**

Add `test-browser` to `.PHONY` and the help block (`#   make test-browser   every screen in a real browser (needs npm ci and npx playwright install chromium)`), widen the help range, and add:

```make
test-browser:
	@node -e "require.resolve('@playwright/test')" 2>/dev/null || { echo "browser suite skipped: run npm ci, then npx playwright install chromium"; exit 0; }; \
	node -e "process.exit(require('fs').existsSync(require('@playwright/test').chromium.executablePath()) ? 0 : 3)" || { echo "browser suite skipped: run npx playwright install chromium"; exit 0; }; \
	node --test tests/browser/unit/ && \
	$(PY) tests/browser/test_world.py && \
	PY=$(PY) npx playwright test -c tests/browser/playwright.config.js
```

and add `test-browser` to the prerequisites of `check` (after `ext-check`).

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN make test-browser`
Expected: the unit tests, `6 passed` from the world, then every spec green (108 pages + 3 keyboard + 2 fence + 3 probes, the rest skipped). Note the wall time for the PR.

- [ ] **Step 2: The CI job**

Add to `.github/workflows/tests.yml`, beside `test`:

```yaml
  # Every screen in Chromium, at three sizes, in an invented world (tests/browser).
  browser:
    runs-on: ubuntu-latest
    timeout-minutes: 25
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: '3.14'
          cache: pip
      - uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0
        with:
          node-version-file: .nvmrc
      # The forecast's seeded run is produced by the forecast package itself.
      - run: pip install --require-hashes -r requirements.txt
      - run: pip install --require-hashes -r forecast/requirements-service.txt
      - run: npm ci --no-audit --no-fund
      - run: npx playwright install --with-deps chromium
      - name: The browser suite's own units
        run: node --test tests/browser/unit/
      - name: The seeded world, without a browser
        run: python tests/browser/test_world.py
      - name: Every screen in a real browser
        run: npx playwright test -c tests/browser/playwright.config.js
        env:
          CI: '1'
          PY: python
      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        if: always()
        with:
          name: browser-run
          path: tests/browser/.run/
          retention-days: 14
```

- [ ] **Step 3: The documents**

`tests/browser/README.md`: what the suite does and cannot see; `make test-browser` and the one-time `npm ci && npx playwright install chromium`; reading a failure (the message, `tests/browser/.run/shots/`, the HTML report at `tests/browser/.run/report/index.html`, `npx playwright show-trace` on a CI retry from the `browser-run` artefact); updating the record (`BROWSER_EXPECTED_STATES=108 UPDATE_RECORD=1 make test-browser`, and that a record only goes down in a normal PR; going up needs the reason in the PR text); the CI record differs from a Mac's (fonts render differently): when they disagree, CI's `observed-*.json` in the artefact is the truth, copied into `record/`; adding a screen (one entry in `screens.js`, ending in a wait for seeded content; a seeded text in `test_world.py` if it needs new data); adding data (the app's own routes first, a store's writer second, an outside system's stand-in last, invented people, `example.com`, `01632 960xxx`); never click a writing control.

`docs/ARCHITECTURE.md`: a "Tests" section naming the three suites and the new fourth (dispatch: the server through its routes; page: the page's source and its logic in node; forecast; browser: every screen rendered, measured and checked for accessibility) and what each cannot see; under "How to add", "A screen" (one entry in `tests/browser/screens.js`) and, under "A route", `make api-doc`.

`README.md`: add `make test-browser` and `make api-doc` to the developer commands.

- [ ] **Step 4: Commit**

```bash
git add Makefile .github/workflows/tests.yml tests/browser/README.md docs/ARCHITECTURE.md README.md
git commit -m "Browser suite in CI and make check; how to run it, read it and add a screen

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Acceptance proofs, the PR and the required check

**Files:** none committed beyond what is listed; the mutations are scratch-only.

- [ ] **Step 1: The suite catches the 13 Oct bug**

On a scratch branch from this one: in `static/index.html`, change the table bleed selector list back to the `:is()` form that matched nothing (`X > :is(.ktable-wrap, .dt > .dtable) { margin-inline: ... }` in place of the two-selector list `T.ktable-wrap, T.dt > .dtable`). Run `npx playwright test -c tests/browser/playwright.config.js pages.spec.js -g "liability|recon|crm~contacts"`.
Expected: FAIL on `panels` (`inset` count up) for the screens whose tables stop running to their panel's edges. Record which screens and rules failed. Delete the scratch branch.

- [ ] **Step 2: A thrown error and a wide panel are each caught**

On a scratch branch: add `throw new Error('suite proof')` as the first line of `renderLiability`; run `-g liability`; expected FAIL `script errors` at all three sizes. Revert; add `#liability-content .panel { min-width: 2000px; }` to the stylesheet; run `-g liability`; expected FAIL `sideways scroll` and/or `content spilling out of its panel`. Delete the scratch branch.

- [ ] **Step 3: Without the seed, the screens refuse to be measured empty**

Run the world without the seed (scratch only: make `seed()` return early after writing an empty `localStorage`), then `pages.spec.js -g "overview|crm~leads|mail"`.
Expected: each FAILS in its `waitText`, not in a measure.

- [ ] **Step 4: Full checks**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN make check`
Expected: every suite green, including `test-browser`; note `make check`'s wall time before (2 min 56 s on 14 Oct) and after.

- [ ] **Step 5: The final review**

Use the one reserved agent for a whole-branch review per superpowers:executing-plans (the package, the plan, the spec, this Review Focus, the ledger's rulings). Fix Critical and Important findings test-first; ledger the minors.

- [ ] **Step 6: The PR**

Push, open the PR (title: "Every screen in a real browser on every pull request"), bind it, switch on Auto-fix and auto-merge. Its body lists: what the suite checks, the 108 states, the day-one fixes made (if any), the record's totals by rule, the three scratch proofs and their results, the run time in CI and locally, and that the `browser` check must be added to the "Protect main" ruleset's required checks to block merges.

- [ ] **Step 7: The required check**

Once the `browser` job has passed on the PR, ask Cameron for a yes to add it to the ruleset's required checks, or for Cameron to add it in the repository's settings. With a yes:

```bash
gh api repos/kamborghini/gizmo/rulesets/24364778 --jq '.rules[] | select(.type=="required_status_checks")'
```
then PUT the ruleset back with `{"context": "browser"}` appended to `required_status_checks`, and read it again to confirm all four contexts are listed.
