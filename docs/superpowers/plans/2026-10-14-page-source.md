# The page's source in sections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `static/index.html` into `static/src/` (a shell, 33 stylesheet sections, 46 script sections, a manifest), joined at start-up by `pagesource.py` into exactly today's page, with every reader switched to the join and guards that keep the layout honest.

**Architecture:** A one-off cut slices today's file at the line numbers in this plan into section files; `pagesource.join()` concatenates them back in manifest order and replaces two marker lines in the shell. The server, both Python suites (through `pagesource.join`) and the browser suite (through its JavaScript twin `tests/browser/page-source.js`) read the joined page; nothing opens a page file. Proof of no change: the join's sha256 equals `main`'s `static/index.html`, and the server's split yields the same asset hashes.

**Tech Stack:** Python 3.14 (standard library only), Node 24 (`node:test`), the existing suites and CI.

**Spec:** `docs/superpowers/specs/2026-10-14-page-source-design.md` (approved 14 Oct).

## Global Constraints

- The served bytes do not change: the joined page equals `main`'s `static/index.html` byte for byte; the server's shell, stylesheet and script, and their `?v=` hashes, are unchanged.
- No reordering, renaming or moving code between sections; cuts are at line boundaries of today's file only.
- Frozen areas (printed labels, print CSS, the Production Manager queue, the Quote Engine) move with their sections byte for byte and are otherwise untouched.
- Every app change carries a release note dated the merge day; the repo is public (no business name in docs, PR text or commits; never commit `audit/`, `.superpowers/`, `.design-rig/`).
- `make check` stays green, the browser suite included; ship as one PR with Auto-fix and auto-merge (the `browser` check is required since 14 Oct).
- Agents: the initiative's five are spent. No agent at all, the final review included: it is a self-review and is reported as one.

## Review Focus

1. **A section saved without its final newline** (an editor setting): the join would glue its last line to the next file's first. Expected: the page suite fails naming the file. Pinned by Task 2's `t_every_page_section_is_whole_lines`.
2. **A new section file not added to the manifest** (or an entry whose file was deleted): the file would silently not be served. Expected: the page suite fails naming it. Pinned by Task 2's `t_the_manifest_and_the_sections_agree`.
3. **Windows line endings or a byte-order mark in a section** from an editor: the served bytes change. Expected: the same whole-lines test fails, naming the file.
4. **A marker line in the shell edited** (indentation, a typo): the join cannot place a section. Expected: `pagesource.join` raises naming `static/src/shell.html`, and every suite fails at import. Pinned by Task 1's `t_a_shell_without_its_markers_is_refused`.
5. **The image built without `static/src/`** (a `.dockerignore` change): `/healthz` answers but the page cannot be served. Expected: CI's image job fails. Pinned by Task 4's image-job step that fetches `/` and the script it names.

---

## The cut

Line numbers are today's `static/index.html` on `main` at `435b4dd` (33,761 lines; `    <style>` on 12, `    </style>` on 6559, `    <script>` on 6846, `    </script>` on 33758). A section runs from its start line to the line before the next start; the last of each list runs to the line before the closing tag. Each start line is a banner (or, for `reconciliation.js`, `production-manager.js` and `page-observers.js`, the first line of an area's code inside another banner's region; see Ruling 1).

**Stylesheet** (body lines 13 to 6558), into `static/src/css/`:

| Start | File | Start | File |
|---|---|---|---|
| 13 | `tokens.css` | 4688 | `keywords-and-tables.css` |
| 456 | `sidebar.css` | 4818 | `table-card.css` |
| 643 | `main.css` | 4968 | `menu.css` |
| 781 | `page.css` | 5051 | `choosers.css` |
| 1485 | `widget-grid.css` | 5233 | `impact.css` |
| 1705 | `memory-and-products.css` | 5262 | `customer-segments.css` |
| 1882 | `structured-response.css` | 5279 | `charts-and-forecast.css` |
| 2120 | `forms.css` | 5515 | `chat.css` |
| 2308 | `skills.css` | 5557 | `composer.css` |
| 2471 | `tables-and-production-manager.css` | 5618 | `chat-conversation.css` |
| 3430 | `dispatch.css` | 5691 | `responsive.css` |
| 3513 | `crm-and-updates.css` | 5725 | `modals.css` |
| 3784 | `inbox.css` | 5744 | `files-preview.css` |
| 4594 | `print-sheets-and-run-gate.css` | 5797 | `sign-in.css` |
| | | 5853 | `files.css` |
| | | 6004 | `team-toasts-and-motion.css` |
| | | 6207 | `windows-and-phone.css` |
| | | 6339 | `recipes.css` |
| | | 6392 | `panels.css` |

**Script** (body lines 6847 to 33757), into `static/src/js/`:

| Start | File | Start | File |
|---|---|---|---|
| 6847 | `start-and-tokens.js` | 14632 | `production-queues.js` |
| 6868 | `icons-and-formats.js` | 14797 | `xero-sync.js` |
| 7181 | `clock.js` | 15693 | `loans.js` |
| 7259 | `state.js` | 17229 | `forecast.js` |
| 7412 | `auth.js` | 18416 | `size-list.js` |
| 7569 | `structured-response.js` | 19192 | `reconciliation.js` |
| 8000 | `widget-grid.js` | 20165 | `production-manager.js` |
| 9032 | `menu.js` | 22128 | `dispatch.js` |
| 9159 | `choosers.js` | 24628 | `guide.js` |
| 9247 | `table-card.js` | 24909 | `design-page.js` |
| 9598 | `markdown.js` | 25492 | `crm.js` |
| 9832 | `charts.js` | 28111 | `inbox.js` |
| 10553 | `chat.js` | 29045 | `inbox-filters-and-sending.js` |
| 11035 | `report-tools.js` | 30445 | `files.js` |
| 11204 | `conversations.js` | 31491 | `team-and-sign-in.js` |
| 11288 | `overview.js` | 32383 | `sidebar-groups.js` |
| 11342 | `alerts.js` | 32504 | `component-states.js` |
| 11533 | `seo.js` | 32516 | `sidebar-responsive.js` |
| 11617 | `keywords.js` | 32565 | `account-menu-and-search.js` |
| 11836 | `customers.js` | 32678 | `page-observers.js` |
| 12149 | `products.js` | 32888 | `settings.js` |
| 12542 | `memory.js` | 33655 | `wire-up.js` |
| 13187 | `skills.js` | | |
| 14094 | `liability.js` | | |

**Rulings made writing this plan** (carried into the ledger at setup):
1. The spec cuts at the file's own banners. Three areas start inside another banner's region with no banner of their own: reconciliation (line 19192, inside "Size list search"), the Production Manager (20165, inside the same region), and the page's after-render observers (32678, inside "the account menu and the page search"). They get their own files at those lines: each is still a cut at a line boundary, so the bytes are unchanged, and a file named for the wrong area would defeat the point of the move. The 11-line reconciliation note at 14797, which sits before the Xero sync code, stays at the head of `xero-sync.js`; moving it is stage 3's.
2. The stylesheet's regions mix areas more than the script's (for example `crm-and-updates.css` holds the release-notes box between the CRM's banner and its board). It is cut only at its major banners and named for what each holds; stage 3 reorders the stylesheet into layers, so hand-tuning these cuts now would be thrown away.

---

### Task 1: `pagesource.py`, the join

**Files:**
- Create: `pagesource.py`
- Test: `tests/test_frontend.py` (append)

**Interfaces:**
- Produces: `pagesource.SRC = os.path.join("static", "src")`; `pagesource.CSS_MARK = "<!-- @css -->\n"`; `pagesource.JS_MARK = "<!-- @js -->\n"`; `pagesource.manifest(root) -> dict`; `pagesource.join(root=ROOT) -> str` (raises `ValueError` naming `static/src/shell.html` when a marker is not there exactly once); `pagesource.sha256(root=ROOT) -> str`; CLI `python pagesource.py --sha256`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_frontend.py`, before the line that prints the totals)

```python
def _page_root(shell, css, js):
    """A throwaway static/src with the given shell and one section of each kind."""
    root = tempfile.mkdtemp(prefix="pagesource-")
    src = os.path.join(root, "static", "src")
    os.makedirs(os.path.join(src, "css")); os.makedirs(os.path.join(src, "js"))
    open(os.path.join(src, "shell.html"), "w", encoding="utf-8").write(shell)
    open(os.path.join(src, "css", "a.css"), "w", encoding="utf-8").write(css)
    open(os.path.join(src, "js", "a.js"), "w", encoding="utf-8").write(js)
    json.dump({"shell": "shell.html", "css": ["css/a.css"], "js": ["js/a.js"]},
              open(os.path.join(src, "manifest.json"), "w", encoding="utf-8"))
    return root


@test
def t_the_page_is_its_shell_with_its_sections_in_place():
    """pagesource.join puts the stylesheet's sections where the shell's css
    marker line is and the script's where its js marker line is, end to end,
    and nothing else: the server serves exactly what it joins."""
    sys.path.insert(0, ROOT)
    import pagesource
    root = _page_root("<style>\n<!-- @css -->\n</style><script>\n<!-- @js -->\n</script>\n", "a{}\n", "x();\n")
    ok(pagesource.join(root) == "<style>\na{}\n</style><script>\nx();\n</script>\n", pagesource.join(root))
    ok(len(pagesource.sha256(root)) == 64, "and it has a fingerprint")


@test
def t_a_shell_without_its_markers_is_refused():
    """A marker line edited by hand (indented, misspelt, doubled) would leave
    a section with nowhere to go. The join refuses and names the file, so the
    suites fail at once rather than the page being served without its script."""
    sys.path.insert(0, ROOT)
    import pagesource
    for shell in ("<!-- @css -->\n  <!-- @js -->\n", "<!-- @css -->\n", "<!-- @css -->\n<!-- @css -->\n<!-- @js -->\n"):
        try:
            pagesource.join(_page_root(shell, "a{}\n", "x();\n"))
        except ValueError as e:
            ok("static/src/shell.html" in str(e), "the refusal names the shell: %s" % e)
        else:
            raise AssertionError("a shell without exactly one of each marker was joined: %r" % shell)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `ONLY=t_the_page_is_its_shell python3 tests/test_frontend.py 2>&1 | grep -E "PASS|FAIL|Error"; ONLY=t_a_shell_without python3 tests/test_frontend.py 2>&1 | grep -E "PASS|FAIL|Error"`
Expected: both error with `No module named 'pagesource'`.

- [ ] **Step 3: Write `pagesource.py`**

```python
"""The page, joined from its sections.

static/src/ holds the page as a shell and its stylesheet's and script's
sections, in the order static/src/manifest.json gives. The server joins them
at start-up into the one page it has always served (copilot._page_parts), and
the test suites read the page from here too, so nothing opens a page file of
its own. tests/browser/page-source.js is the same join in JavaScript.

    python pagesource.py --sha256   # the joined page's fingerprint
    python pagesource.py            # the joined page itself

Zero dependencies, like tokenvault.py.
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join("static", "src")
CSS_MARK = "<!-- @css -->\n"
JS_MARK = "<!-- @js -->\n"


def manifest(root=ROOT):
    with open(os.path.join(root, SRC, "manifest.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _read(root, rel):
    # newline="" keeps every byte as written: the join must be the file it replaced.
    with open(os.path.join(root, SRC, rel), encoding="utf-8", newline="") as fh:
        return fh.read()


def join(root=ROOT):
    m = manifest(root)
    shell = _read(root, m["shell"])
    if shell.count(CSS_MARK) != 1 or shell.count(JS_MARK) != 1 or shell.index(CSS_MARK) > shell.index(JS_MARK):
        raise ValueError("static/src/shell.html must hold the line %r and then the line %r, once each"
                         % (CSS_MARK.strip(), JS_MARK.strip()))
    head, rest = shell.split(CSS_MARK)
    middle, tail = rest.split(JS_MARK)
    return (head + "".join(_read(root, p) for p in m["css"]) + middle
            + "".join(_read(root, p) for p in m["js"]) + tail)


def sha256(root=ROOT):
    return hashlib.sha256(join(root).encode("utf-8")).hexdigest()


if __name__ == "__main__":
    if "--sha256" in sys.argv[1:]:
        print(sha256())
    else:
        sys.stdout.write(join())
```

- [ ] **Step 4: Run the tests**

Run: the two commands from Step 2.
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add pagesource.py tests/test_frontend.py
git commit -m "pagesource.py: the page joined from its shell and sections

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The cut, the switch and the guards

**Files:**
- Create: `static/src/shell.html`, `static/src/manifest.json`, `static/src/css/*.css` (33), `static/src/js/*.js` (46)
- Delete: `static/index.html`
- Modify: `copilot.py` (`_PAGE_PATH`, `_page_parts`), `tests/test_frontend.py` (`HTML`, four node calls, the release-note date path), `tests/test_dispatch.py` (15 page reads)
- Test: `tests/test_frontend.py`, `tests/test_dispatch.py`

**Interfaces:**
- Consumes: `pagesource.join`, `pagesource.manifest`, `pagesource.SRC`, the markers (Task 1).
- Produces: the `static/src/` layout; `copilot._page_parts()` reading `pagesource.join()`; `tests/test_frontend.py` `PAGE_FILE` (a temporary file holding the joined page, for node helpers that take a path).

- [ ] **Step 1: Write the failing guards** (append to `tests/test_frontend.py`)

```python
@test
def t_the_manifest_and_the_sections_agree():
    """A section file the manifest does not list is never served; an entry
    whose file is gone takes the page down. Each is caught here, by name."""
    sys.path.insert(0, ROOT)
    import pagesource
    m = pagesource.manifest(ROOT)
    src = os.path.join(ROOT, pagesource.SRC)
    for kind, ext in (("css", ".css"), ("js", ".js")):
        on_disk = sorted(kind + "/" + f for f in os.listdir(os.path.join(src, kind)) if f.endswith(ext))
        ok(sorted(m[kind]) == on_disk, "%s: in the folder, not the manifest: %s; in the manifest, not the folder: %s"
           % (kind, sorted(set(on_disk) - set(m[kind])), sorted(set(m[kind]) - set(on_disk))))
        ok(len(set(m[kind])) == len(m[kind]), "%s: a section listed twice" % kind)
    stray = [f for f in os.listdir(src) if f not in ("css", "js", "manifest.json", m["shell"])]
    ok(not stray, "static/src holds files nothing joins: %s" % stray)
    ok(not os.path.exists(os.path.join(ROOT, "static", "index.html")), "the old single file is gone")


@test
def t_every_page_section_is_whole_lines():
    """A section saved without its last newline glues its last line to the
    next file's first; a Windows line ending or a byte-order mark changes the
    served bytes. Every section is plain UTF-8 lines ending in a newline."""
    sys.path.insert(0, ROOT)
    import pagesource
    m = pagesource.manifest(ROOT)
    for rel in m["css"] + m["js"] + [m["shell"]]:
        raw = open(os.path.join(ROOT, pagesource.SRC, rel), "rb").read()
        ok(raw.endswith(b"\n") and raw.strip(), "%s is empty or does not end with a newline" % rel)
        ok(b"\r" not in raw, "%s has a Windows line ending" % rel)
        ok(not raw.startswith(b"\xef\xbb\xbf"), "%s starts with a byte-order mark" % rel)


@test
def t_nothing_opens_a_page_file_but_the_reader():
    """The page is read in one place (pagesource.py, and its JavaScript twin).
    A tool still opening static/index.html would fail on a missing file; this
    names it first."""
    out = subprocess.run(["git", "ls-files", "*.py", "*.js", "*.yml", "Makefile", "Dockerfile"],
                         cwd=ROOT, capture_output=True, text=True).stdout.split()
    bad = []
    for f in out:
        if f.startswith(("docs/", "node_modules/")) or not os.path.isfile(os.path.join(ROOT, f)):
            continue
        text = open(os.path.join(ROOT, f), encoding="utf-8", errors="replace").read()
        if re.search(r"""["']static/index\.html["']|["']static["']\s*,\s*["']index\.html["']""", text):
            bad.append(f)
    ok(not bad, "these still open the page file: %s" % bad)
```

Run: `for t in t_the_manifest_and t_every_page_section t_nothing_opens; do ONLY=$t python3 tests/test_frontend.py 2>&1 | grep -E "PASS|FAIL|Error" | head -2; done`
Expected: all three FAIL (no manifest; the old file still open in many places).

- [ ] **Step 2: The cut** (a one-off script, run from the plan workspace, not committed)

Write `.superpowers/sdd/2026-10-14-page-source/cut.py`:

```python
"""Cut static/index.html into static/src/ at the plan's line numbers, then prove the join."""
import hashlib, json, os, sys
ROOT = "/Users/cameron/Desktop/claude/gizmo"
CSS = [(13, "tokens"), (456, "sidebar"), (643, "main"), (781, "page"), (1485, "widget-grid"),
       (1705, "memory-and-products"), (1882, "structured-response"), (2120, "forms"), (2308, "skills"),
       (2471, "tables-and-production-manager"), (3430, "dispatch"), (3513, "crm-and-updates"), (3784, "inbox"),
       (4594, "print-sheets-and-run-gate"), (4688, "keywords-and-tables"), (4818, "table-card"), (4968, "menu"),
       (5051, "choosers"), (5233, "impact"), (5262, "customer-segments"), (5279, "charts-and-forecast"),
       (5515, "chat"), (5557, "composer"), (5618, "chat-conversation"), (5691, "responsive"), (5725, "modals"),
       (5744, "files-preview"), (5797, "sign-in"), (5853, "files"), (6004, "team-toasts-and-motion"),
       (6207, "windows-and-phone"), (6339, "recipes"), (6392, "panels")]
JS = [(6847, "start-and-tokens"), (6868, "icons-and-formats"), (7181, "clock"), (7259, "state"), (7412, "auth"),
      (7569, "structured-response"), (8000, "widget-grid"), (9032, "menu"), (9159, "choosers"), (9247, "table-card"),
      (9598, "markdown"), (9832, "charts"), (10553, "chat"), (11035, "report-tools"), (11204, "conversations"),
      (11288, "overview"), (11342, "alerts"), (11533, "seo"), (11617, "keywords"), (11836, "customers"),
      (12149, "products"), (12542, "memory"), (13187, "skills"), (14094, "liability"), (14632, "production-queues"),
      (14797, "xero-sync"), (15693, "loans"), (17229, "forecast"), (18416, "size-list"), (19192, "reconciliation"),
      (20165, "production-manager"), (22128, "dispatch"), (24628, "guide"), (24909, "design-page"), (25492, "crm"),
      (28111, "inbox"), (29045, "inbox-filters-and-sending"), (30445, "files"), (31491, "team-and-sign-in"),
      (32383, "sidebar-groups"), (32504, "component-states"), (32516, "sidebar-responsive"),
      (32565, "account-menu-and-search"), (32678, "page-observers"), (32888, "settings"), (33655, "wire-up")]
page_path = os.path.join(ROOT, "static", "index.html")
raw = open(page_path, encoding="utf-8", newline="").read()
before = hashlib.sha256(raw.encode("utf-8")).hexdigest()
lines = raw.splitlines(keepends=True)
assert lines[11] == "    <style>\n" and lines[6558] == "    </style>\n", (lines[11], lines[6558])
assert lines[6845] == "    <script>\n" and lines[33757] == "    </script>\n", (lines[6845], lines[33757])
src = os.path.join(ROOT, "static", "src")
os.makedirs(os.path.join(src, "css")); os.makedirs(os.path.join(src, "js"))

def cut(table, end, kind, ext):
    names = []
    for k, (start, name) in enumerate(table):
        stop = table[k + 1][0] if k + 1 < len(table) else end
        body = "".join(lines[start - 1:stop - 1])
        assert body.strip(), name
        rel = f"{kind}/{name}{ext}"
        open(os.path.join(src, rel), "w", encoding="utf-8", newline="").write(body)
        names.append(rel)
    return names

css = cut(CSS, 6559, "css", ".css")
js = cut(JS, 33758, "js", ".js")
shell = "".join(lines[:12]) + "<!-- @css -->\n" + "".join(lines[6558:6846]) + "<!-- @js -->\n" + "".join(lines[33757:])
open(os.path.join(src, "shell.html"), "w", encoding="utf-8", newline="").write(shell)
json.dump({"shell": "shell.html", "css": css, "js": js}, open(os.path.join(src, "manifest.json"), "w", encoding="utf-8"), indent=1)
open(os.path.join(src, "manifest.json"), "a", encoding="utf-8").write("\n")
sys.path.insert(0, ROOT)
import pagesource
after = pagesource.sha256(ROOT)
print("before", before); print("after ", after)
assert before == after, "the join is not the page"
print(len(css), "css,", len(js), "js sections; the join equals the page")
```

Run: `python3 .superpowers/sdd/2026-10-14-page-source/cut.py`
Expected: `33 css, 46 js sections; the join equals the page`, with `before` and `after` the same hash. Record the hash in the ledger. Then `git rm -q static/index.html`.

- [ ] **Step 3: The server reads the join**

In `copilot.py`: add `import pagesource` on the line after `import perf` (51), and replace the `_PAGE_PATH` line (224) with

```python
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")   # composer.js; the page itself is joined by pagesource.py from static/src
```

In `_page_parts()`, replace

```python
        with open(_PAGE_PATH, "r", encoding="utf-8") as fh:
            raw = fh.read()
```

with

```python
        # The page is joined from its sections (static/src), byte for byte the
        # single file it was: the split below and its hashed URLs are unchanged.
        raw = pagesource.join()
```

and in the composer read replace `os.path.dirname(_PAGE_PATH)` with `_STATIC_DIR`. Then `grep -n "_PAGE_PATH" copilot.py` must print nothing.

- [ ] **Step 4: The suites read the join**

`tests/test_frontend.py`, top of file: replace the `HTML = open(...)` line with

```python
sys.path.insert(0, ROOT)
import pagesource
HTML = pagesource.join(ROOT)
# Node helpers that take a page file get the joined page in a temporary file.
_PAGE_TMP = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8")
_PAGE_TMP.write(HTML); _PAGE_TMP.close()
PAGE_FILE = _PAGE_TMP.name
import atexit
atexit.register(lambda: os.path.exists(PAGE_FILE) and os.remove(PAGE_FILE))
```

and replace each `os.path.join(ROOT, "static", "index.html")` passed to `node` (four sites) with `PAGE_FILE`. In `t_the_release_notes_are_ui_copy_and_keep_up_with_the_app`, replace `"static/index.html", "copilot.py"` in the `git log` call with `"static/src", "pagesource.py", "copilot.py"`.

`tests/test_dispatch.py`: add `import pagesource` after `import server, copilot, worldoptions, pipedrive`, then replace every read of the page file with `pagesource.join(HERE)` (15 sites; three span two lines). Do it with a script and check the count:

```bash
python3 - <<'EOF'
import re
p = "tests/test_dispatch.py"; s = open(p).read()
pat = re.compile(r'open\(os\.path\.join\((?:HERE|os\.path\.dirname\(os\.path\.dirname\(os\.path\.abspath\(__file__\)\)\)|os\.path\.dirname\(os\.path\.abspath\(__file__\)\),\s*"\.\.")\s*,\s*"static",\s*"index\.html"\),\s*encoding="utf-8"\)\.read\(\)', re.S)
s, n = pat.subn("pagesource.join(HERE)", s)
print(n); open(p, "w").write(s)
EOF
grep -c "index.html" tests/test_dispatch.py
```
Expected: `15`, then a count of only comment or message mentions (read each remaining line; none may open the file). `HERE` is defined before the first test in the setup, so it is in scope at every site.

- [ ] **Step 5: Run every suite**

Run: `python3 tests/test_frontend.py > /tmp/ps-front.log 2>&1; tail -1 /tmp/ps-front.log` then `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN make test > /tmp/ps-disp.log 2>&1; tail -1 /tmp/ps-disp.log`
Expected: the page suite at its previous count plus the five new tests, 0 failed; the dispatch suite 1,012 passed, 0 failed. Any failure is a reader that was missed or a cut off by a line: fix the reader, never a section's bytes.

- [ ] **Step 6: Prove the served parts did not change** (scratch)

```bash
git show main:static/index.html > /tmp/ps-main.html
env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN .venv/bin/python - <<'EOF'
import hashlib, os, sys
sys.path.insert(0, "."); os.environ.setdefault("SHOPIFY_STORE", "proof")
import copilot, pagesource
old = open("/tmp/ps-main.html", encoding="utf-8").read()
h = lambda t: hashlib.sha256(t.encode()).hexdigest()
a = copilot._split_page(old); old_hashes = dict(copilot._asset_hashes)
b = copilot._split_page(pagesource.join()); new_hashes = dict(copilot._asset_hashes)
print("join == main:", pagesource.join() == old)
print("shell/css/js equal:", [h(x) == h(y) for x, y in zip(a, b)])
print("asset hashes:", old_hashes, "->", new_hashes, "equal:", old_hashes == new_hashes)
EOF
```
Expected: `join == main: True`, `[True, True, True]`, and equal hashes. Copy the three lines into the ledger for the PR.

- [ ] **Step 7: Commit**

```bash
git add static/src pagesource.py copilot.py tests/test_frontend.py tests/test_dispatch.py
git commit -m "The page's source in sections: static/src joined by pagesource.py, byte for byte the page it was

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
(`static/index.html` is already staged as deleted by `git rm`.)

---

### Task 3: The browser suite reads the join

**Files:**
- Create: `tests/browser/page-source.js`, `tests/browser/unit/page-source.test.js`
- Modify: `tests/browser/probes.js` (the page read), `tests/browser/unit/screens.test.js` (the page read)

**Interfaces:**
- Consumes: `python pagesource.py --sha256` (Task 1), the layout (Task 2).
- Produces: `require('./page-source').join(root?) -> string`.

- [ ] **Step 1: Write the failing test** — `tests/browser/unit/page-source.test.js`

```js
// The browser suite's join is the server's join: one page, read two ways.
const test = require('node:test');
const assert = require('node:assert');
const crypto = require('crypto');
const path = require('path');
const { spawnSync } = require('child_process');
const { join } = require('../page-source');

test('the JavaScript join gives the page pagesource.py gives', () => {
  const root = path.join(__dirname, '..', '..', '..');
  const py = spawnSync(process.env.PY || 'python3', [path.join(root, 'pagesource.py'), '--sha256'], { encoding: 'utf8', cwd: root });
  assert.strictEqual(py.status, 0, py.stderr);
  const mine = crypto.createHash('sha256').update(join(root), 'utf8').digest('hex');
  assert.strictEqual(mine, py.stdout.trim());
});
```

Run: `node --test 'tests/browser/unit/*.test.js' 2>&1 | grep -E "^✖|^ℹ (pass|fail)|Cannot find"`
Expected: FAIL, `Cannot find module '../page-source'`.

- [ ] **Step 2: Write `tests/browser/page-source.js`**

```js
// The page, joined from static/src exactly as pagesource.py joins it: the
// shell with its two marker lines replaced by the sections, in manifest order.
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..', '..');
const CSS_MARK = '<!-- @css -->\n';
const JS_MARK = '<!-- @js -->\n';

function join(root = ROOT) {
  const src = path.join(root, 'static', 'src');
  const m = JSON.parse(fs.readFileSync(path.join(src, 'manifest.json'), 'utf8'));
  const read = rel => fs.readFileSync(path.join(src, rel), 'utf8');
  const shell = read(m.shell);
  const [head, rest] = shell.split(CSS_MARK);
  const [middle, tail] = rest.split(JS_MARK);
  return head + m.css.map(read).join('') + middle + m.js.map(read).join('') + tail;
}

module.exports = { join };
```

- [ ] **Step 3: Switch the two readers**

`tests/browser/probes.js`: replace `const APP = fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'index.html'), 'utf8');` with `const APP = require('./page-source').join();` (drop `fs`/`path` requires if nothing else uses them). `tests/browser/unit/screens.test.js`: replace its `APP` read the same way (`require('../page-source').join()`).

- [ ] **Step 4: Run the units and the probes**

Run: `node --test 'tests/browser/unit/*.test.js' 2>&1 | grep -E "^ℹ (pass|fail)"; npx playwright test -c tests/browser/playwright.config.js probes.spec.js --reporter=line 2>&1 | tail -1`
Expected: units 17 passed 0 failed; `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/browser/page-source.js tests/browser/unit/page-source.test.js tests/browser/probes.js tests/browser/unit/screens.test.js
git commit -m "Browser suite: the page read through the same join, held to pagesource.py's fingerprint

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: CI, documents and the release note

**Files:**
- Modify: `.github/workflows/tests.yml`, `Makefile` (`SAST_FILES`), `docs/ARCHITECTURE.md`, `README.md`, `tests/browser/README.md`, `data/changelog.json`, `.gitignore` (the icon-library comment that names `static/index.html`)

- [ ] **Step 1: CI**

Add `pagesource.py` to the bandit file list in `tests.yml`'s SAST step and to `SAST_FILES` in the `Makefile` (every first-party module is on both).

In `tests.yml`'s `test` job, the no-dashes step: `grep -qE '—|–|\\u201[34]|&[mn]dash;' static/index.html static/composer.js` becomes `grep -rqE '—|–|\\u201[34]|&[mn]dash;' static/src static/composer.js`.

In the `images` job's step that runs the app container and waits for `/healthz`, after the `/healthz` loop succeeds, also fetch the page and its script (Review Focus 5):

```bash
          page=$(curl -sf http://127.0.0.1:8000/) || { docker logs app; exit 1; }
          js=$(printf '%s' "$page" | grep -o '/assets/app\.js?v=[0-9a-f]*' | head -1)
          [ -n "$js" ] && curl -sf "http://127.0.0.1:8000$js" > /dev/null || { echo "the page or its script did not load"; docker logs app; exit 1; }
```
Read the job before editing: keep its `exit 0` / `exit 1` shape, so the page check runs after the health loop and before the step ends.

Prove the dash check still bites, locally: `printf '\xe2\x80\x94\n' >> static/src/js/wire-up.js; grep -rqE '—|–' static/src static/composer.js && echo caught; git checkout static/src/js/wire-up.js`
Expected: `caught`.

- [ ] **Step 2: Documents**

`docs/ARCHITECTURE.md`, "What is deliberately the way it is": the bullet "**The page is one file.** No build step; the guards depend on it. The split into assets happens at serve time." becomes "**The page is one script in sections.** `static/src/` holds the shell, the stylesheet's sections and the script's sections, in the order `static/src/manifest.json` gives; `pagesource.py` joins them at start-up into the one page the server has always served (one function scope, split into two hashed assets at serve time). No build step. A screen's code is in its own file (`js/crm.js`, `js/production-manager.js`); a new section is a file and a manifest line, and a page-suite guard fails until both exist." Under "How to add", add "**A page section.** A file in `static/src/js` or `static/src/css`, whole lines ending in a newline, and its line in `manifest.json` where it belongs in the cascade or the script's order."

`README.md`, "Where things are": replace the `static/index.html` entry with `static/src/` (the page in sections, joined by `pagesource.py`).

`tests/browser/README.md`: wherever it names `static/index.html`, say the page (`static/src`, joined by `page-source.js`).

`.gitignore`: the comment "icons are inlined into static/index.html" becomes "icons are inlined into the page (static/src)".

- [ ] **Step 3: The release note**

Insert at the top of `data/changelog.json`'s `releases` (dated the merge day; today is 2026-10-14):

```json
{"date": "2026-10-14", "title": "Behind the scenes", "items": [
 {"kind": "changed", "tab": null, "text": "The app's page is now kept in sections, so a change to one screen is quicker and safer to make. Nothing you see changes."}]}
```

Run: `ONLY=t_the_release_notes python3 tests/test_frontend.py 2>&1 | grep -E "PASS|FAIL"`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/tests.yml Makefile docs/ARCHITECTURE.md README.md tests/browser/README.md data/changelog.json .gitignore
git commit -m "The page's sections in CI, the docs and What's new

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Full checks, self-review and the PR

- [ ] **Step 1: `make check`**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN make check > /tmp/ps-check.log 2>&1; echo $?`
Expected: `0`; page suite, forecast 24, dispatch 1,012, browser units 17, world 6, browser 119 (the same record: nothing on screen changed, so not one count may move).

- [ ] **Step 2: Self-review**

No agent is left in the budget. Review the whole diff (`git diff main --stat`, then each non-section file in full; for `static/src`, the cut proof stands for the bytes) against `requesting-code-review/code-reviewer.md`'s checklist and this plan's Review Focus, and write `Final review: self-review (no agent left in the budget)` in the ledger with what was checked.

- [ ] **Step 3: The PR**

Push, open "The page's source in sections, served byte for byte as before", bind it, switch on Auto-fix and auto-merge. The body states: the layout and how to find a screen's code; the three proof lines from Task 2 Step 6; the counts of every suite and that the browser record did not move; the guards; the rulings; and that the review was a self-review.
