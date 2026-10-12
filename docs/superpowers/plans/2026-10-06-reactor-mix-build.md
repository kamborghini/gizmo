# Reactor mix: build plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Cameron's standing rule caps sub-agents at 5 for the whole task, reviewers included.** With 47 tasks, a subagent-driven run batches them: at most 4 implementer agents (Phases 1 and 2; Phase 3; Phase 4; Phases 5 and 6 up to the stop in Task 47) plus one reviewer, each implementer working its tasks in order and committing after each. Running inline with superpowers:executing-plans is the other way.

**Goal:** Reactor's new look, "the mix": one white sheet in an ink frame, figures first with explanations behind info buttons, every value from one token block, every screen measured to zero faults, with the production label, the print sheets and the Production Manager queue's content left exactly as they are.

**Architecture:** The spec's section 4 values go into the app's existing three-tier `:root` block first, guarded by tests that pin them and by a byte-for-byte freeze on everything that prints. The shell (ink frame, sheet, sidebar, top bar, page header) and each shared part (buttons, fields, choosers, sections, info buttons, menus, figure row, feature band, tables, lists, tags, empty state, chart, queue counters, states, phone rules) are then rebuilt in place, one base rule and one builder each, each with its guard test. Forecast and Production Manager are matched to the mockup, and every other screen follows the spec's patterns with its words cut from the copy plan.

**Tech Stack:** One-file SPA `static/index.html` (plain CSS and JavaScript, no build step), `static/composer.js`, Python 3 / Starlette (`copilot.py`, `server.py`), the custom page-test harness `tests/test_frontend.py` (`@test`, `ok`, `eq`, `fn_src`, `_body_of`, `_rules`, `_token`, `_token_raw`, `_contrast`, globals `HTML`, `CSS`, `SCRIPT`, `COMPOSER`), the server harness `tests/test_dispatch.py`, node for script harnesses, playwright-core on Chrome for the rig audits.

**Spec:** `docs/superpowers/specs/2026-10-06-reactor-mix-design.md`, with its appendix `docs/superpowers/specs/2026-10-06-reactor-mix-copy-plan.md` (the copy plan; where it and the spec disagree, the spec wins) and the audited reference mockup `docs/design/mix/mix.html` (its `:root` holds the exact target values). Read all three before Task 1. The previous spec, `docs/superpowers/specs/2026-10-05-brand-design-system-design.md`, keeps its architecture (one token block in three tiers, two choosers, the guard tests); its section 5 values are superseded.

## Global Constraints

- **Where:** repo `/Users/cameron/Desktop/claude/gizmo`, branch `design/brand-foundation` (unpushed, starts at 9a8c442). Every path below is relative to the repo. Line numbers are at 9a8c442 and drift as tasks land: anchor every edit on the quoted text, never on the number.
- **Rig and tools:** `S=/Users/cameron/Desktop/claude/gizmo/.design-rig`, a local folder inside the repo that git ignores (`.design-rig/` is listed in `.git/info/exclude`, so it can never be staged; the secret sweep reads only tracked files). It holds the rig launcher and its test token (`rigd/`), the 165-screen audit with its own playwright-core (`spacing/`), the measure tool (`mixaudit/measure.js`), the sample-order harness (`reallabels/`), the gallery builder with its before shots (`gallery/`) and the forecast sample (`fc/smoke_payload.json`). Shell state does not persist between commands, so each command block sets `S`. Files a task creates under `$S` are never committed.
- **Colours (spec 4.1):** ink `#121212`, ink-2 `#3C4043`, ink-3 `#5F6368` (the lightest text allowed), ink-4 `#8A9096` (marks only), line-ctl `#DADCE0`, line `#E6E7EA`, line-soft `#EEEFF1`, fill `#F3F4F5`, sheet `#FFFFFF`; teal `#13B7C0` (a fill only, never text on white), teal-hover `#11A6AF`, teal-line `#0F9097`, teal-text `#0B6B71`, teal-dark `#08484C`, teal-wash `#F1FBFB`, teal-glow `#B8E9EC`, blue `#334FB4`; ok `#15803D`/`#F0FDF4`, warn `#B45309`/`#FFFBEB`, bad `#B91C1C`/`#FEF2F2`; live dot `#22A55A` with a 15% halo; text on a teal fill is ink.
- **One colour per measure:** Taken teal-dark; Still expected teal at 45%; Expected an ink dot (mark) or a teal-line line (series); Likely range a teal-glow bar with a teal-line edge (mark) or teal at 15% with a teal-line 35% key edge (area); Plan blue.
- **The ink frame:** chrome ink; sidebar text white at 72%, muted white at 50%; chrome fill white at 12%, pressed white at 18%; the chosen nav item teal at 18% with white text and a teal icon; the sheet has no edge and no shadow; frame = sheet corner 12 + inset 8 = 20. The feature band is `#D3F1F3` through `#DDF4F5`, `#EBF8F9` to `#F2FBFB`, with rules and empty tracks teal-dark at 12%.
- **Type (spec 4.2):** Inter at micro 11/16, caption 12/16, body 13/20, body-l 14/20, head 15/20 weight 600; weights 400, 500, 600 only; tracking none except titles (-0.02em) and figures (-0.03em). Bricolage Grotesque 600 only for the wordmark (16/20) and page titles (26/32 desktop, 24/32 phone). Figures Inter 600, tabular, line height 1, at 44 (Forecast hero), 36 (queue counters), 28 (side figures and the figure row), 24; a phone figure is one step down.
- **Sizes (spec 4.3):** tag 20, ctl-xs 24 (info and refresh), ctl-in 28 (sidebar icon buttons, feature tiles, a chosen segment), ctl 32 (button, field, search, segmented track, queue tab, nav and menu rows, switch, table head), row 44, row-2 60, order row 64, every phone target 40, empty-state tile 40. Icons 16 at stroke 1.75 in controls, rows, tiles and nav; 14 at stroke 2 only for inline glyphs. Top bar 48, sidebar 236, sheet inset 8. Gutter 40 desktop, 16 phone.
- **Space (spec 4.4):** the 4px scale 4, 8, 12, 16, 20, 24, 32, 40, 48, 64 (2 only for hairline nudges and segments). Icon to label 8; leading row icon 12; control to control 8; group to group 16; figure label to figure and figure to chip 12; the two-column split 64; popover 8 from its trigger, padding 16; tooltip padding 12. Rhythm: header 12 from the top bar, title to its line 4, header to tabs 20, body 32 under the tabs, section to section 48 (32 on a phone), section head to content 12.
- **Corners (spec 4.5):** 2 keys, small marks, the tab underline; 4 chosen segment, keyboard hint, info button, tags, brand mark, text-link focus ring; 6 buttons, fields, search, segmented track, nav and menu rows, queue tabs, feature tiles, the label image; 10 queue counters, popovers, tooltip, menus, dialogs, toasts; 12 the sheet, the feature band; full only for dots, bars, the switch. No pill-shaped buttons, inputs or tabs.
- **States (spec 4.6):** focus a 2px teal-line ring, offset 2; hover a fill, only inside `@media (hover: hover)`; pressed one step darker than hover (line on the sheet, line-ctl on something already filled, teal-line on teal, white at 18% on the chrome); chosen is the segment recipe (white, a teal-line inner ring, ink words).
- **One source of truth (spec principle 1):** every value comes from the `:root` block. Outside it a rule uses `var(--...)` only, the exceptions being 0, 1px hairlines and percentages. Markup carries no style attributes except data percentages for bar positions, set as custom properties (`style.setProperty('--at-lo', p + '%')`).
- **The token block's own rules (tests enforce them):** one top-level `:root`; every token it defines is read as `var(--x)` or `'--x'` by the stylesheet, the script or `static/composer.js` in the same commit; no `rgba(` literal anywhere in `index.html` except `0,0,0`, `255,255,255` and `26,26,26` (translucency is `color-mix(in srgb, var(--x) N%, transparent)`); contrast-tested text, ground and status tokens stay `var()` chains down to a six-digit hex.
- **Breakpoints:** `@media` widths only 640/641, 900/901, 1100/1101, 1500 and 1800, and all five stay in use. Container-query widths are free. `container-type` on an element disables subgrid on it.
- **Cascade:** change a base rule in place; a new rule goes after its base rule. Tests read the FIRST `.x {` block, and `t_two_choosers_and_nothing_else` allows exactly one `\n        .tabs {`, `.tab {`, `.segmented {` and `.segmented > button {` at the stylesheet's 8-space indent.
- **Phone:** `(max-width: 640px)` (the rig audit runs at 390 without touch emulation, so phone rules are keyed on width). Every target 40, control and row-title text 14, gutter 16, section to section 32. Real inputs keep 16px under `(pointer: coarse)` so iOS does not zoom into them.
- **Print is frozen (house rule):** never edit `labelSheet`, `labelPrintCss`, `fitLabel`, `labelFontReady`, `labelDims`, `prodSize`, `carrierDims`, `stickerDims`, `loanStickerSheet`, `loanPrintSticker`, `printLabels`, `printDaySheet`, `printDispatchManifest`, `printStockUsage`, `printShippingLabelsFor`, `printLabelImages`, `printGuide`, `LABEL_SIZES`, `LABEL_LOGO`, `PRINT_LAYS_LABELS`, the `<div id="label-print">`, any CSS rule whose selector or context matches `label-sheet|day-sheet|loan-sticker|guide-print-row|#label-print|printing-label|@media print|@page`, the Bricolage `@font-face`, the `body` rule's `font-size: var(--text-sm); line-height: var(--lh-body);`, the values of the tokens print reads, or `copilot.py`'s `/print/production-labels` route and `_LABEL_LOGO_SVG`. Task 1's `t_the_printed_sheets_do_not_change` fails on any of them. A new shell rule that could reach a report printed to PDF goes inside `@media screen`.
- **The Production Manager queue's content and actions do not change (house rule):** rows and their cells, every chip and its words, Preview/Hide, Edit, Proof, Print, Ready to make, Dispatch/Shipment, Mark made/Made with their titles, the toolbar items and their order (search "Find order, customer or tracking", All / Unprinted / Not made, Print all (n), Print shipping labels (n), Newest first, the label size select), the More menu items and order, and the inline preview wording ("First order from this customer." or the repeat-customer line, "Actual size preview: ...", the shrink and clip sentences). Only the look around them changes.
- **The Quote Engine is out of bounds.** No drawn illustrations: an empty state is a 40 icon tile, one line and its action.
- **Words (spec 7):** a page header has its title and at most one line of 10 words or fewer; card and section titles stand alone; explanations move behind an info button or into the Guide word for word (the build moves existing words, it never writes new explanations); warnings, costs and security notes are never dropped; an empty state is one line of 8 words or fewer plus its action. British English; no em or en dashes and no spaced hyphen used as one; never a setting or environment variable name; never "Railway" or "gizmo". Release notes never say API, webhook, callback URL or JSON.
- **Release note:** the newest entry in `data/changelog.json` (dated 2026-10-05, unshipped, describing this branch) becomes this build's one note. Every commit that touches `static/index.html` or `copilot.py` first runs this, which dates that note today if it is older (the file has a one-space indent and no trailing newline):

  ```bash
  python3 - <<'PY'
  import json, datetime
  p = "data/changelog.json"; d = json.load(open(p, encoding="utf-8"))
  t = datetime.date.today().isoformat()
  if d["releases"][0]["date"] < t: d["releases"][0]["date"] = t
  open(p, "w", encoding="utf-8").write(json.dumps(d, indent=1, ensure_ascii=False))
  PY
  ```
- **A test the task does not name fails:** if it pinned a value the task deliberately changes to the spec's, change that one assertion to the new value (keeping its reason, reworded) in the same commit and name it in the commit message; if it fails for any other reason, the code is wrong: fix the code, not the test.
- **Tests:** one page test: `ONLY=<part of its name> python3 tests/test_frontend.py` (Task 1 adds `ONLY`); the whole page suite: `python3 tests/test_frontend.py` (about two minutes, ends `N passed, 0 failed`); everything: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN make check` (page tests, 22 forecast tests, 930 server tests). New page tests go at the end of `tests/test_frontend.py`, just above `if __name__ == "__main__":`. Every `ok` has its reason; a test checks a function exists before `fn_src` or `.split(...)[1]` on it, because the harness catches only `AssertionError`. For the same reason a test above `def eq(` (tests/test_frontend.py:8532) never calls `eq`: the harness runs each test as it is declared, so there `eq` is a `NameError` that stops the whole suite; it uses `ok(a == b, ...)`.
- **Commits:** stage named files only (never `git add -A`, never the untracked `audit/` folder: the repo is public); every message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Shipping:** only through a pull request after Cameron says yes (main has a no-bypass ruleset); `make check` passes before any push.
- **The rig** (the real app served live from disk on :8920 with the test harness's sample data): start it once per session with `python3 "$S/rigd/launch.py" > "$S/rigd/server.log" 2>&1` run in the background. A restart wipes the posted forecast; re-post it with `curl -s -X POST http://127.0.0.1:8920/hooks/forecast/results -H 'x-forecast-token: rig-forecast-token-local-only-0123456789' -H 'Content-Type: application/json' --data @"$S/fc/smoke_payload.json"`. In a browser, `location.reload()` serves a cached page: navigate to `http://127.0.0.1:8920/?fresh=N` with a new N. Sign in with the harness account `cameron` / `test-password-123`; `window.shopify.idToken` comes from `$S/rigd/long_token.txt`.

---

## Decisions for Cameron

Choices the plan made where the spec, the copy plan or the mockup left room. Task 47 sends these with the gallery; each is one task's edit if Cameron wants it the other way.

1. **Where the spec and the copy plan disagree, the spec wins.** No page keeps a header line once a report has run (the copy plan's fallback lines on Overview, SEO, Keywords and Customers are dropped). Forecast has a status line ("October 2026 · Run as of 1 Oct") instead of the copy plan's intro line.
2. **Production Manager.** The inline preview's wording is unchanged, so copy plan PM #18 and #19 are not applied, and the clip warning keeps its spaced hyphen (" - some rows would be cut off the printed label."): Cameron decides that one. "Print this label" under the preview becomes a plain button, so the open row's Print is the one teal action. Custom shipments keeps its teal Reprint label on every row (a queue action). Print new (n) stays first in the header actions when it shows.
3. **Queue counters need counts from the server.** `run_production_labels` gains an additive `counts` field worked out from the snapshot it already holds, so there is no extra Shopify call (Task 31). Custom shipments shows the last counts it was sent.
4. **Forecast.** Worth looking at and Why are one moveable block (id `worth`), so the 7:5 pair keeps its layout; the old `alerts`, `drivers` and `method` block ids go, so anyone who hid one in Customise sees the new pair. Compare methods is off by default and remembered per person. "How sure this is" and "About this chart" reuse words already on the screen. The forecasting service's own model names and "Best at" lines keep the word "source". The non-admin setup lines are shortened.
5. **Setup steps that name the hosting or a setting** (Xero link, FORECAST_INGEST_TOKEN, R2, XERO_CLIENT_ID, the Inbox's Google sign-in steps) move word for word behind info buttons, not into the Guide: the spec puts setup behind the setup card's info button, and an existing test forbids "Railway" in the Guide. An admin who opens the popover still sees those names, so Cameron may want them rewritten.
6. **Settings connection lines** drop their setting names, as the copy plan says, so admins lose those hints on the screen.
7. **Sign-in card.** It takes the 10 corner and the pop shadow, and keeps the sky tint and 32 padding Cameron approved on 2026-09-22 rather than the generic 16.
8. **Xero document window.** Its method notes (copy plan Other #34) stay visible: each shows only when its condition holds, and several are warnings.
9. **Smaller header choices.** Products shows its line with Refresh as an action, so its "Updated" stamp goes there; the Size list's stamp sits beside Refresh.
10. **New action words** where the copy plan asked for an action: Connect Google, Go to Unprocessed, Add a unit, Deal/Pipeline, Show all. Memory's two note states become tags. The CRM charts' default empty line is shortened.
11. **Dialogs and toasts** float as menus and popovers do: no edge of their own, the 10 corner, the pop shadow, 16 inside (Task 44). A toast keeps its coloured status bar at its left edge.
12. **Tracking goes with the type sweep** (Task 25): only page titles and figures keep any letter-spacing. The report's print-only header (`.print-head`) is paper and keeps its type as it is.

---

## File Structure

| File | What changes and why |
|---|---|
| `static/index.html`, `:root` (lines 32-286) | The spec's section 4 values in the three tiers: the grey ramp, the frame, measure, shadow and rule tokens, the type steps, sizes, space roles and corner roles. Old values that no role keeps (`--off-white`, the `--neutral-*` scale, `--text-lg/xl/3xl`, `--lh-tight/snug`, `--radius-sm/xl`, `--shadow-md`, `--dot-lg`) leave once their readers have moved; the sign-in card's sky tint tokens stay, as Cameron approved them. |
| `static/index.html`, the stylesheet (lines 287-4982) | Each part's base rule rewritten in place: shell (`#app`, `.sidebar`, `.main`, `.topbar`, `.ov-hero`), buttons, fields, `.tabs`/`.tab`/`.segmented`, `.card` and `.section-title` (no box), `.dmenu`, `.metrics-strip`, `.ktable`, ONE TAG, `.empty`, `.chart-*`, `.modal`, `.toast`, the widget grid's editing outline; new parts (`.info`, `.ipop`, `.fband`, `.rlist`, `.queues`, `.qc`, `.qt`, `.empty-state`, `.ph-sub`, `.live-dot`, `.crumbs`, `.cnt`, `.link`, `.swap`, `.lbl-frame`, `.rg`, `.fc-wl`, `.sec-tools`) added after the base rules they relate to; every `:hover` moved into `@media (hover: hover)`; the type sweep. |
| `static/index.html`, markup (lines 4983-5269) | The sidebar's brand row (a teal mark tile, the wordmark, a Hide sidebar button), the top bar's crumbs and search field. |
| `static/index.html`, the script (lines 5270-30383) | New builders `pageHead`, `infoButton`, `howItWorks`, `featureBand`, `rangeBar`, `meter`, `listRows`, `emptyState`, `queueCounters`, `changeChip`; `chooser` learns counts and icon-only choices; `trendChart` learns a headless mode, a legend row, keys and a readout; `MIX_TOKENS` for the Design section; Forecast and Production Manager rebuilt on them; every screen's header, sections and words per the copy plan. |
| `static/composer.js` | Its injected corners and focus move onto the role tokens (Task 43). |
| `copilot.py` | `run_production_labels` adds an additive `counts` field (the three queue counters) from the snapshot it already holds (Task 31). The print route is untouched. |
| `tests/test_frontend.py` | `ONLY=`; the print freeze; a guard per part; the old guards that pinned superseded values rewritten to the spec's, intent kept. |
| `tests/test_dispatch.py` | `ONLY=` for one server test, and the `counts` field's test (Task 31). |
| `data/changelog.json` | The unshipped 2026-10-05 entry rewritten as this build's one release note. |
| `$S/mixaudit/measure-app.js` (scratch, not committed) | The mockup's measure tool pointed at the app (Task 45). |
| `$S/reallabels/shoot-mix.js` (scratch, not committed) | The label and queue capture, finding the To make counter (Task 34). |
| `$S/copy/apply.py` and `$S/copy/t35.py` to `t44.py`, `t43c.py` (scratch, not committed) | Each screen task's exact replacements, applied only if every old string is found exactly as often as it says (Tasks 35 to 44). |

---

## Phase 1: The tokens and the guards

### Task 1: Run one page test by name, and freeze everything that prints

**Files:**
- Modify: `tests/test_frontend.py:23-32` (the `test` decorator)
- Test: `tests/test_frontend.py` (new test at the end, above `if __name__ == "__main__":`)

**Interfaces:**
- Consumes: `_body_of(signature)` (tests/test_frontend.py:1577), `_rules(css)` (5947), `_token_raw(name)` (1095), `eq(a, b, msg)` (8532).
- Produces: `ONLY=<substring> python3 tests/test_frontend.py` runs only the tests whose name contains it (every later task uses it). `t_the_printed_sheets_do_not_change`, which every later task must keep green.

- [ ] **Step 1: Add the ONLY filter**

In `tests/test_frontend.py` replace:

```python
_passed, _failed = 0, []


def test(fn):
    global _passed
    try:
```

with:

```python
_passed, _failed = 0, []
# ONLY=<part of a name> runs just the matching tests: the whole page suite takes
# about two minutes, which is too long to wait for one red test.
_ONLY = os.environ.get("ONLY", "")


def test(fn):
    global _passed
    if _ONLY and _ONLY not in fn.__name__:
        return fn
    try:
```

- [ ] **Step 2: Check it**

Run: `ONLY=t_the_script_parses python3 tests/test_frontend.py`
Expected: `  PASS  t_the_script_parses`, then `1 passed, 0 failed`.

- [ ] **Step 3: Write the freeze guard**

Append above `if __name__ == "__main__":` in `tests/test_frontend.py`:

```python
# ---- The mix, 6 October 2026 -------------------------------------------------

@test
def t_the_printed_sheets_do_not_change():
    """2026-10-05, Cameron: "i dont like how you have changed my production
    lables". The production label, the serial sticker, the courier labels and
    the A4 sheets (day sheet, dispatch manifest, stock usage, the printed Guide)
    are paper. The mix restyles the screen only, so every print function, the
    print CSS, the tokens and body type print inherits, the label face and the
    server's own print document are pinned to their bytes at 9a8c442. A failure
    here is a change to paper: undo it, or ask Cameron first."""
    import hashlib
    h = lambda t: hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]
    funcs = {
        "function prodSize(": "c8b194be336787e3", "function carrierDims(": "560211cb05b49d72",
        "function stickerDims(": "b65799c062e28ec8", "function labelFontReady(": "e90e9106a39a03f4",
        "function labelDims(": "a3e5c994043b70d4", "function labelPrintCss(": "061bc8a8862da9f0",
        "function fitLabel(": "b8bebb1841f753aa", "function loanStickerSheet(": "4e84233802eb448d",
        "async function loanPrintSticker(": "d7705852736415ca", "function labelSheet(": "68217ade25de37e2",
        "function printDispatchManifest(": "7298fb528556d1bb", "function printStockUsage(": "87dcb3552a1cd72e",
        "function printDaySheet(": "59667d1651a03de6", "function printShippingLabelsFor(": "1574f28f689be7a0",
        "function printLabelImages(": "b5f3da205c85e60b", "function printLabels(": "4f2e020a18b82af7",
        "function printGuide(": "d169080c58a6a3f6", "const LABEL_SIZES = {": "aaba502d9fc95f0f",
    }
    for sig, want in funcs.items():
        ok(sig in SCRIPT, "the print code is still there: " + sig)
        eq(h(_body_of(sig)), want, sig + " is byte for byte what prints today")
    for pre, want in (("        const LABEL_LOGO = ", "215e8bea15a6faf4"),
                      ("        const PRINT_LAYS_LABELS = ", "4a6515c3bd7492f9")):
        ok(pre in SCRIPT, "the print constant is still there: " + pre.strip())
        i = SCRIPT.index(pre)
        eq(h(SCRIPT[i:SCRIPT.index("\n", i)]), want, pre.strip() + " is unchanged")
    pr = re.compile(r"label-sheet|day-sheet|loan-sticker|guide-print-row|#label-print|printing-label|@media print|@page")
    rules = [s + "{" + re.sub(r"\s+", " ", b).strip() + "}" for s, b in _rules(CSS) if pr.search(s)]
    eq(len(rules), 80, "the print rules are the same eighty")
    eq(h("\n".join(rules)), "dd6dd5eed001305b", "and each is unchanged, in order")
    ok('<div id="label-print"></div>' in HTML, "the print staging area is still a child of the page")
    ff = re.search(r"@font-face \{ font-family: 'Bricolage Grotesque';[^}]*\}", CSS)
    ok(ff, "the label face is still declared")
    eq(h(ff.group(0)), "b3eb4de40583f995", "and declared exactly as before")
    # What print reads from the token block, and what the A4 sheets inherit from body.
    for tok, want in (("white", "#ffffff"), ("black", "#000000"), ("print-black-1", "#111111"),
                      ("print-black-2", "#222222"), ("print-black-3", "#333333"), ("print-grey-1", "#bbbbbb"),
                      ("print-grey-2", "#dddddd"), ("paper", "var(--white)"), ("paper-ink", "var(--black)"),
                      ("paper-ink-2", "var(--print-black-1)"), ("paper-ink-3", "var(--print-black-2)"),
                      ("paper-ink-4", "var(--print-black-3)"), ("paper-rule", "var(--print-grey-2)"),
                      ("paper-rule-2", "var(--print-grey-1)"), ("paper-rule-strong", "var(--print-black-1)"),
                      ("font-print", "'Bricolage Grotesque', -apple-system, 'Segoe UI', Roboto, Arial, sans-serif"),
                      ("text-xs", "12px"), ("text-sm", "14px"), ("text-md", "16px"), ("weight-medium", "500"),
                      ("weight-semibold", "600"), ("bw-hairline", "1px"), ("bw-strong", "2px"), ("bw-marker", "3px"),
                      ("sp-2", "8px"), ("radius-xs", "6px"), ("lh-body", "1.5")):
        eq(_token_raw(tok), want, "--" + tok + " (print reads it)")
    body = CSS.split("\n        body {")[1].split("}")[0]
    ok("font-size: var(--text-sm); line-height: var(--lh-body);" in body,
       "the A4 sheets still inherit 14px on a 1.5 line from body")
    py = open(os.path.join(ROOT, "copilot.py"), encoding="utf-8").read()
    a = py.index('    @mcp.custom_route("/print/production-labels", methods=["GET", "OPTIONS"])')
    b = py.index("return HTMLResponse(doc, headers=doc_headers)", a)
    eq(h(py[a:b]), "61376908bdf445b7", "the server's print document is unchanged")
    i = py.index("_LABEL_LOGO_SVG = ")
    eq(h(py[i:py.index("\n", i)]), "5cda691da0ce3b1e", "and so is the logo it prints")
```

- [ ] **Step 4: Run it**

Run: `ONLY=t_the_printed_sheets python3 tests/test_frontend.py`
Expected: `  PASS  t_the_printed_sheets_do_not_change`, `1 passed, 0 failed`.

- [ ] **Step 5: Prove it bites**

```bash
S=/Users/cameron/Desktop/claude/gizmo/.design-rig
cp static/index.html "$S/index.freeze.bak"
sed -i '' 's/padding: 5mm 5.5mm; overflow: hidden;/padding: 5mm 5.6mm; overflow: hidden;/' static/index.html
ONLY=t_the_printed_sheets python3 tests/test_frontend.py
cp "$S/index.freeze.bak" static/index.html && git diff --stat static/index.html
```

Expected: `FAIL  t_the_printed_sheets_do_not_change: and each is unchanged, in order: 'dd6dd5eed001305b' != '...'`, `0 passed, 1 failed`; then `git diff --stat` prints nothing (the page is back).

- [ ] **Step 6: Capture the label and queue as they are today**

The rig must be running (Global Constraints). Then:

```bash
S=/Users/cameron/Desktop/claude/gizmo/.design-rig
python3 "$S/reallabels/build.py"
mkdir -p "$S/reallabels/baseline" && cd "$S/reallabels/baseline" && node ../shoot.js
ls "$S/reallabels/baseline"
```

Expected: `6 orders` and six order lines from build.py; `1440 preview opened true label el true` and `390 preview opened true label el true`; the listing shows `label-1440.png label-390.png preview-1440.png preview-390.png queue-1440.png queue-390.png`. Task 34 compares against these.

- [ ] **Step 7: Run the whole page suite**

Run: `python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `427 passed, 0 failed`

- [ ] **Step 8: Commit**

```bash
git add tests/test_frontend.py
git commit -m "Tests: ONLY runs one page test by name, and everything that prints is pinned to its bytes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: One grey ramp

**Files:**
- Modify: `static/index.html:15-31` (the token block's header comment), `:46-68` (tier 1 primitives), `:84-96` and `:102`, `:128`, `:134`, `:146`, `:154` (the tier 2 lines that read the old greys), `:1720` (the select chevron's encoded grey), the script after `const DS_COLOURS = [...]` (22066-22083)
- Modify: `data/changelog.json` (the newest entry)
- Test: `tests/test_frontend.py` (`t_reactor_wears_projected_images_brand_from_one_place` 9339, `t_the_charts_are_drawn_to_the_reference_spec` 1737, `t_every_chart_line_comes_off_the_ramp` 3175, a new test)

**Interfaces:**
- Consumes: nothing new.
- Produces: tier 1 `--ink-2`, `--ink-3`, `--ink-4`, `--line-ctl`, `--line`, `--line-soft`, `--fill`; `--surface-page` is `var(--white)`; `const MIX_TOKENS` in the script (a list of `[group name, [token names]]` that the Design section draws in Task 43 and that later tasks extend).

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_the_mix_greys_are_one_ramp():
    """The mix (spec 2026-10-06, 4.1): one grey ramp, every grey on screen is
    one of its steps, and the semantic tier reads them. Outside the token block
    no rule writes a colour of its own."""
    for tok, v in (("ink", "#121212"), ("ink-2", "#3C4043"), ("ink-3", "#5F6368"), ("ink-4", "#8A9096"),
                   ("line-ctl", "#DADCE0"), ("line", "#E6E7EA"), ("line-soft", "#EEEFF1"), ("fill", "#F3F4F5"),
                   ("white", "#ffffff"), ("teal-500", "#13B7C0"), ("teal-600", "#11A6AF"), ("teal-650", "#0F9097"),
                   ("teal-700", "#0B6B71"), ("teal-900", "#08484C"), ("teal-50", "#F1FBFB"), ("teal-200", "#B8E9EC"),
                   ("brand-blue", "#334FB4"), ("green-700", "#15803D"), ("green-50", "#F0FDF4"),
                   ("amber-700", "#B45309"), ("amber-50", "#FFFBEB"), ("red-700", "#B91C1C"), ("red-50", "#FEF2F2")):
        eq(_token_raw(tok).lower(), v.lower(), "--" + tok)
    for tok, ref in (("text-secondary", "var(--ink-2)"), ("text-tertiary", "var(--ink-3)"),
                     ("text-disabled", "var(--ink-4)"), ("surface-page", "var(--white)"),
                     ("surface-secondary", "var(--fill)"), ("surface-tertiary", "var(--fill)"),
                     ("surface-sunken", "var(--line)"), ("border-default", "var(--line)"),
                     ("border-strong", "var(--line-ctl)"), ("border-emphasis", "var(--ink-4)"),
                     ("action-soft", "var(--fill)"), ("action-line", "var(--line)")):
        eq(_token_raw(tok), ref, "--" + tok)
    ok(not re.search(r"--neutral-\d+\s*:", CSS) and "--off-white" not in CSS,
       "the old neutral scale and the off-white page are gone")
    for ground in ("white", "fill", "line"):
        ok(_contrast(_token("ink-3"), _token(ground)) >= 4.5, "ink-3, the lightest text, reads on --" + ground)
    rest = re.sub(r"/\*.*?\*/", "", CSS[CSS.index("\n        }", CSS.index(":root {")):], flags=re.S)
    ok(not re.search(r"(?<![\w-])#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", rest), "no rule outside the block writes a colour")
    enc = set(m.lower() for m in re.findall(r"%23([0-9a-fA-F]{6})", rest))
    ok(enc <= {"5f6368", "ffffff"}, "a drawn glyph's colour is a ramp step too: %s" % sorted(enc))
    ok("const MIX_TOKENS = [" in SCRIPT, "the Design section's list of the mix's tokens exists")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_the_mix_greys python3 tests/test_frontend.py`
Expected: `FAIL  t_the_mix_greys_are_one_ramp: token --ink-2 not found`

- [ ] **Step 3: Rewrite the block's header comment**

In `static/index.html` replace:

```
           Light, because the app is embedded inside the Shopify admin and a
           dark panel inside a light admin reads as a foreign object.

           The look is Projected Image's own (2026-10-05, Cameron: "uniformity
           is key", "one source of truth"): the brand's teal, ink and off-white,
           Bricolage Grotesque for titles and Inter for everything else, 8px
           cards and no shadows on what sits on the page, taken from
           projectedimage.com's own theme settings; then the polish pass
           (Cameron: "Do not use pill-shaped UI unnecessarily"): 6px controls,
           4px tags, one control height per row, one text size for controls,
           one reading measure. This block is the only place any of it is
           defined, and the Guide's Design section draws it.
```

with:

```
           The look is "the mix" (docs/superpowers/specs/2026-10-06-reactor-
           mix-design.md; Cameron, 2026-10-05: "i like the mix", "go with the
           dark sidebar"): one white sheet in an ink frame, one grey ramp,
           Projected Image's teal for what is chosen and the one primary
           action, Inter in five steps with Bricolage Grotesque for the
           wordmark and page titles only, figures first and words on request.
           This block is the only place any of it is defined, and the Guide's
           Design section draws it.
```

- [ ] **Step 4: Replace the tier 1 greys**

Replace:

```
            /* ---- Tier 1: primitives. Projected Image's brand (teal #13B7C0,
               ink #121212, charcoal #2F2F2F, off-white #F7F7F7, blue #334FB4,
               from projectedimage.com) on the shadcn/ui "neutral" scale and the
               Tailwind status families. The bright teal is 2.45:1 on white, too
               faint for text: it is a FILL with ink on it (7.64:1), and text in
               teal is --teal-700 (6.26:1). Two custom neutral steps are marked. ---- */
            --white: #ffffff; --black: #000000;
            --ink: #121212; --off-white: #F7F7F7; --brand-blue: #334FB4;
            --teal-50: #F1FBFB;    /* 6% teal on white: a selected row or nav item */
            --teal-200: #B8E9EC;   /* 30%: the focus glow */
```

with:

```
            /* ---- Tier 1: primitives. Projected Image's brand (teal #13B7C0,
               ink #121212, blue #334FB4, from projectedimage.com), one grey
               ramp (the mix, 4.1) and the Tailwind status families. The bright
               teal is 2.45:1 on white, too faint for text: it is a FILL with ink
               on it (7.64:1), and text in teal is --teal-700 (6.26:1). ---- */
            --white: #ffffff; --black: #000000;
            /* One grey ramp: ink for words, three lighter inks, three rules and
               one fill. ink-3 is the lightest text there is (6.05:1 on white,
               4.89:1 on --line); ink-4 (3.23:1) is a mark, never words. */
            --ink: #121212; --ink-2: #3C4043; --ink-3: #5F6368; --ink-4: #8A9096;
            --line-ctl: #DADCE0;   /* control borders, the chart axis */
            --line: #E6E7EA;       /* list frames, header rules */
            --line-soft: #EEEFF1;  /* row dividers, the chart grid */
            --fill: #F3F4F5;       /* wells, counters, open and hover states */
            --brand-blue: #334FB4;
            --teal-50: #F1FBFB;    /* the teal wash: the open row */
            --teal-200: #B8E9EC;   /* the teal glow: a likely range drawn as a bar */
```

Then replace:

```
            --teal-700: #0B6B71;   /* teal text and links, the focus outline: 6.26:1 on white */
            --teal-900: #08484C;   /* the brand's dark teal */
            --neutral-50: #fafafa; --neutral-100: #f5f5f5;
            --neutral-150: #ebebeb;   /* custom: a third fill step that still reads as one */
            --neutral-200: #e5e5e5; --neutral-300: #d4d4d4; --neutral-400: #a1a1a1;
            --neutral-500: #737373;
            --neutral-550: #696969;   /* custom: the reference's #737373 is 4.35:1 on --neutral-100.
                                         This clears 4.5:1 on every ground a quiet label sits on;
                                         the binding one is --neutral-150 at 4.61. */
            --neutral-600: #525252; --neutral-900: #171717; --neutral-950: #0a0a0a;
```

with:

```
            --teal-700: #0B6B71;   /* teal text and links: 6.26:1 on white */
            --teal-900: #08484C;   /* the brand's dark teal: money already taken */
```

- [ ] **Step 5: Point the semantic tier at the ramp**

Replace:

```
            --text-primary: var(--ink); --text-secondary: var(--neutral-600);
            --text-tertiary: var(--neutral-550); --text-disabled: var(--neutral-400);
```

with:

```
            --text-primary: var(--ink); --text-secondary: var(--ink-2);
            --text-tertiary: var(--ink-3); --text-disabled: var(--ink-4);
```

Replace:

```
            /* Surfaces. Cards are white on the brand's off-white page, and
               keep their hairline: the brand draws no shadow under anything
               that sits on the page. The sidebar and top bar are white, like
               the website's header. */
            --surface-page: var(--off-white);
            --surface-primary: var(--white); --surface-secondary: var(--neutral-50);
            --surface-tertiary: var(--neutral-100); --surface-sunken: var(--neutral-150);
            --border-default: var(--neutral-200); --border-strong: var(--neutral-300);
            --border-emphasis: var(--neutral-400);
```

with:

```
            /* Surfaces. The page is one white sheet; a well, a counter, a hover
               is the one fill; what is pressed on a fill is a line. Sunken text
               sits on --line, so it is never --line-ctl (ink-3 is 4.41 there). */
            --surface-page: var(--white);
            --surface-primary: var(--white); --surface-secondary: var(--fill);
            --surface-tertiary: var(--fill); --surface-sunken: var(--line);
            --border-default: var(--line); --border-strong: var(--line-ctl);
            --border-emphasis: var(--ink-4);
```

Replace:

```
            --action-soft: var(--neutral-100); --action-line: var(--neutral-200);
```

with:

```
            --action-soft: var(--fill); --action-line: var(--line);
```

Replace:

```
            --chart-4: var(--neutral-500);   /* 4.7:1 on a card; the 400 grey was 2.6:1, under the 3:1 a line needs */ --chart-5: var(--amber-700);
```

with:

```
            --chart-4: var(--ink-3);   /* the ramp's lightest text grey, 6.05:1: a comparison line reads at 3:1 and more */ --chart-5: var(--amber-700);
```

Replace:

```
            --owner-gray: var(--neutral-500); --owner-dark-gray: var(--neutral-600);
```

with:

```
            --owner-gray: var(--ink-3); --owner-dark-gray: var(--ink-2);
```

Replace:

```
            --overlay-scrim: color-mix(in srgb, var(--neutral-900) 32%, transparent);
```

with:

```
            --overlay-scrim: color-mix(in srgb, var(--ink) 32%, transparent);
```

Replace:

```
            --shadow-md: 0 0 0 1px color-mix(in srgb, var(--neutral-950) 10%, transparent),
```

with:

```
            --shadow-md: 0 0 0 1px color-mix(in srgb, var(--ink) 10%, transparent),
```

- [ ] **Step 6: The select chevron's grey is a ramp step**

In the `select { appearance: none; ...` rule replace `stroke='%23616161'` with `stroke='%235F6368'`.

- [ ] **Step 7: The Inter link carries its optical sizes**

The mockup's figures were measured with Inter's display optical size. Replace:

```
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
```

with:

```
    <link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400..700&display=swap" rel="stylesheet" />
```

- [ ] **Step 8: Start the Design section's list of the mix's tokens**

In the script, directly after the line `            ['Charts, in the order lines are drawn', [1, 2, 3, 4, 5].map(n => ['Series ' + n, '--chart-' + n, null, null])],` and its closing `        ];`, add:

```js
        /* The mix's tokens by role (spec 2026-10-06, section 4), for the Design
           section to draw. Each group is a row of samples; each is read from the
           stylesheet as the browser has it, never copied here. Later parts add
           their groups below. */
        const MIX_TOKENS = [
            ['Greys', ['--ink', '--ink-2', '--ink-3', '--ink-4', '--line-ctl', '--line', '--line-soft', '--fill', '--white']],
        ];
```

- [ ] **Step 9: Update the guards that pinned the old greys**

In `t_reactor_wears_projected_images_brand_from_one_place` replace:

```python
    for tok, v in (("teal-500", "#13B7C0"), ("ink", "#121212"), ("off-white", "#F7F7F7"), ("brand-blue", "#334FB4")):
        ok(_token_raw(tok).lower() == v.lower(), "--%s is the brand's %s" % (tok, v))
    for tok, ref in (("action-primary", "var(--teal-500)"), ("text-on-action", "var(--ink)"), ("text-brand", "var(--teal-700)"),
                     ("surface-page", "var(--off-white)"), ("radius-control", "var(--radius-xs)")):
```

with:

```python
    for tok, v in (("teal-500", "#13B7C0"), ("ink", "#121212"), ("brand-blue", "#334FB4")):
        ok(_token_raw(tok).lower() == v.lower(), "--%s is the brand's %s" % (tok, v))
    for tok, ref in (("action-primary", "var(--teal-500)"), ("text-on-action", "var(--ink)"), ("text-brand", "var(--teal-700)"),
                     ("surface-page", "var(--white)"), ("radius-control", "var(--radius-xs)")):
```

and replace:

```python
    ok("family=Inter:wght@400;500;600;700" in HTML and "family=Geist" not in HTML, "the interface face is Inter")
```

with:

```python
    ok("family=Inter:opsz,wght@14..32,400..700" in HTML and "family=Geist" not in HTML,
       "the interface face is Inter, with the optical sizes the figures were measured in")
```

and replace:

```python
    ok("background: var(--surface-page)" in CSS.split("        body {")[1].split("}")[0], "on the brand's off-white page")
```

with:

```python
    ok("background: var(--surface-page)" in CSS.split("        body {")[1].split("}")[0], "on the white page")
```

In `t_the_charts_are_drawn_to_the_reference_spec` replace:

```python
    ok(_token("border-default") == "#e5e5e5", "and that token still resolves to #e5e5e5")
```

with:

```python
    ok(_token("border-default").lower() == "#e6e7ea", "and that token resolves to the ramp's line, #E6E7EA")
```

and replace:

```python
    ok(_token("text-tertiary") == "#696969", "and that token still resolves to a grey (#696969)")
```

with:

```python
    ok(_token("text-tertiary").lower() == "#5f6368", "and that token resolves to ink-3, #5F6368")
```

In `t_every_chart_line_comes_off_the_ramp` replace:

```python
    # The grey is the 500: the 400 was 2.6:1 on a card, under the 3:1 a line needs.
    for i, hexv in enumerate(("#0F9097", "#08484C", "#334FB4", "#737373", "#b45309"), 1):
```

with:

```python
    # The grey is ink-3, the ramp's lightest text grey: a line needs 3:1.
    for i, hexv in enumerate(("#0F9097", "#08484C", "#334FB4", "#5F6368", "#b45309"), 1):
```

- [ ] **Step 10: Open the release note**

Replace the newest entry in `data/changelog.json` (the one titled "Reactor in Projected Image's colours", dated 2026-10-05; every item in it describes this unshipped branch) with this one, dated today:

```json
  {
   "date": "2026-10-06",
   "title": "Reactor's new look",
   "items": [
    {
     "kind": "changed",
     "text": "Reactor has a new look: one white page in a dark frame, one set of greys, and Projected Image's teal for what is chosen and for the one main button on each screen."
    }
   ]
  },
```

Then run the release-note command from Global Constraints.

- [ ] **Step 11: Run the tests**

Run: `ONLY=t_the_mix_greys python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `428 passed, 0 failed`.

- [ ] **Step 12: Commit**

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Tokens: one grey ramp, a white page, and Inter's optical sizes for the figures

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The frame, the measures, the band, shadows, rules and focus as tokens

**Files:**
- Modify: `static/index.html` tier 1 (after `--teal-900`), tier 2 (after `--owner-brown-bg`, the focus lines 144-145, the elevation lines 151-158), the script's `MIX_TOKENS`
- Test: `tests/test_frontend.py` (`t_the_card_elevation_token_actually_paints` 3646, a new test)

**Interfaces:**
- Consumes: the grey ramp (Task 2).
- Produces (tier 1): `--teal-band-1` `#D3F1F3`, `--teal-band-2` `#DDF4F5`, `--teal-band-3` `#EBF8F9`, `--teal-band-4` `#F2FBFB`, `--live-green` `#22A55A`. (tier 2): `--surface-chrome`, `--text-on-chrome`, `--nav-text`, `--nav-muted`, `--chrome-fill`, `--chrome-press`, `--nav-on-bg`, `--nav-on-icon`, `--link-underline`, `--live-dot`, `--live-halo`, `--press`, `--press-fill`, `--c-taken`, `--c-still`, `--c-exp`, `--c-exp-line`, `--c-range`, `--c-range-edge`, `--c-area`, `--c-area-edge`, `--c-plan`, `--band-bg`, `--band-rule`, `--border-soft`, `--shadow-control`, `--shadow-raise`, `--shadow-pop`, `--shadow-focal`, `--shadow-label`, `--ring-chosen`, `--ring-live`, `--ring-selected`, `--rule-t`, `--rule-b`, `--rule-t-soft`, `--rule-b-soft`, `--rule-t-band`. `--focus-ring` becomes a 2px teal-line ring with a 2px white gap; `--focus-outline` is 2px teal-line; `--shadow-md` and `--shadow-lg` read `--shadow-pop`.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_the_ink_frame_the_measures_and_the_shadows_are_tokens():
    """Spec 4.1 and 4.6: the ink frame, one colour per measure on every screen,
    the feature band, five shadows, hairlines drawn as inset shadows, and one
    focus ring. Each is set once here and only read elsewhere."""
    want = {
        "teal-band-1": "#D3F1F3", "teal-band-2": "#DDF4F5", "teal-band-3": "#EBF8F9", "teal-band-4": "#F2FBFB",
        "live-green": "#22A55A",
        "surface-chrome": "var(--ink)", "text-on-chrome": "var(--white)",
        "nav-text": "color-mix(in srgb, var(--white) 72%, transparent)",
        "nav-muted": "color-mix(in srgb, var(--white) 50%, transparent)",
        "chrome-fill": "color-mix(in srgb, var(--white) 12%, transparent)",
        "chrome-press": "color-mix(in srgb, var(--white) 18%, transparent)",
        "nav-on-bg": "color-mix(in srgb, var(--teal-500) 18%, transparent)", "nav-on-icon": "var(--teal-500)",
        "link-underline": "color-mix(in srgb, var(--teal-700) 35%, transparent)",
        "live-dot": "var(--live-green)", "live-halo": "color-mix(in srgb, var(--live-green) 15%, transparent)",
        "press": "var(--line)", "press-fill": "var(--line-ctl)",
        "c-taken": "var(--teal-900)", "c-still": "color-mix(in srgb, var(--teal-500) 45%, transparent)",
        "c-exp": "var(--ink)", "c-exp-line": "var(--teal-650)", "c-range": "var(--teal-200)",
        "c-range-edge": "var(--teal-650)", "c-area": "color-mix(in srgb, var(--teal-500) 15%, transparent)",
        "c-area-edge": "color-mix(in srgb, var(--teal-650) 35%, transparent)", "c-plan": "var(--brand-blue)",
        "band-rule": "color-mix(in srgb, var(--teal-900) 12%, transparent)", "border-soft": "var(--line-soft)",
        "shadow-control": "0 1px 1px color-mix(in srgb, var(--ink) 4%, transparent)",
        "ring-chosen": "var(--shadow-control), inset 0 0 0 var(--bw-hairline) var(--teal-650)",
        "ring-live": "0 0 0 var(--sp-0-5) var(--live-halo)",
        "ring-selected": "inset var(--bw-strong) 0 0 var(--teal-650)",
        "rule-t": "inset 0 var(--bw-hairline) 0 var(--border-default)",
        "rule-b": "inset 0 calc(-1 * var(--bw-hairline)) 0 var(--border-default)",
        "rule-t-soft": "inset 0 var(--bw-hairline) 0 var(--border-soft)",
        "rule-b-soft": "inset 0 calc(-1 * var(--bw-hairline)) 0 var(--border-soft)",
        "rule-t-band": "inset 0 var(--bw-hairline) 0 var(--band-rule)",
        "focus-ring": "0 0 0 var(--bw-strong) var(--white), 0 0 0 calc(2 * var(--bw-strong)) var(--teal-650)",
        "focus-outline": "var(--bw-strong) solid var(--teal-650)",
        "shadow-md": "var(--shadow-pop)", "shadow-lg": "var(--shadow-pop)",
    }
    for tok, v in want.items():
        eq(_token_raw(tok), v, "--" + tok)
    for tok in ("band-bg", "shadow-raise", "shadow-pop", "shadow-focal", "shadow-label"):
        v = _token_raw(tok)
        ok("color-mix" in v or "var(--teal-band-" in v, "--%s is drawn from the palette: %s" % (tok, v[:60]))
    ok(all("var(--teal-band-%d)" % n in _token_raw("band-bg") for n in (1, 2, 3, 4)), "the band runs through its four stops")
    ok(_contrast(_token("ink"), _token("teal-500")) >= 4.5, "ink on the teal fill reads at 4.5:1")
    tokens = SCRIPT.split("const MIX_TOKENS = [")[1].split("];")[0]
    for group in ("'The ink frame'", "'One colour per measure'", "'Shadows and rules'"):
        ok(group in tokens, "the Design section lists " + group)
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_the_ink_frame python3 tests/test_frontend.py`
Expected: `FAIL  t_the_ink_frame_the_measures_and_the_shadows_are_tokens: token --teal-band-1 not found`

- [ ] **Step 3: Add the tier 1 stops**

Replace:

```
            --teal-900: #08484C;   /* the brand's dark teal: money already taken */
```

with:

```
            --teal-900: #08484C;   /* the brand's dark teal: money already taken */
            /* The feature band's four stops, light teal to almost white, and the live dot. */
            --teal-band-1: #D3F1F3; --teal-band-2: #DDF4F5; --teal-band-3: #EBF8F9; --teal-band-4: #F2FBFB;
            --live-green: #22A55A;
```

- [ ] **Step 4: Add the frame, measure, band and rule roles**

Replace:

```
            --owner-brown-bg: color-mix(in srgb, var(--owner-brown) 10%, var(--white));
            /* Focus and overlays. */
            --focus-ring: 0 0 0 3px var(--teal-200);
            --focus-outline: var(--bw-strong) solid var(--teal-700);
```

with:

```
            --owner-brown-bg: color-mix(in srgb, var(--owner-brown) 10%, var(--white));
            /* The ink frame (the mix, 4.1): the sidebar and the edge round the one
               white sheet. Words on it are white at 72%, muted white at 50%; the
               chosen item is teal at 18% with white words and a teal icon. */
            --surface-chrome: var(--ink); --text-on-chrome: var(--white);
            --nav-text: color-mix(in srgb, var(--white) 72%, transparent);
            --nav-muted: color-mix(in srgb, var(--white) 50%, transparent);
            --chrome-fill: color-mix(in srgb, var(--white) 12%, transparent);
            --chrome-press: color-mix(in srgb, var(--white) 18%, transparent);
            --nav-on-bg: color-mix(in srgb, var(--teal-500) 18%, transparent); --nav-on-icon: var(--teal-500);
            /* A link's underline; the live dot and its halo. */
            --link-underline: color-mix(in srgb, var(--teal-700) 35%, transparent);
            --live-dot: var(--live-green); --live-halo: color-mix(in srgb, var(--live-green) 15%, transparent);
            /* Pressed is one step darker than hover: --press on the sheet, --press-fill
               on something already filled, --action-active on teal, --chrome-press on ink. */
            --press: var(--line); --press-fill: var(--line-ctl);
            /* One colour per measure, on every screen: taken, still expected,
               expected (a dot as a mark, a line as a series), the likely range (a
               bar as a mark, an area in a chart), the plan. */
            --c-taken: var(--teal-900); --c-still: color-mix(in srgb, var(--teal-500) 45%, transparent);
            --c-exp: var(--ink); --c-exp-line: var(--teal-650);
            --c-range: var(--teal-200); --c-range-edge: var(--teal-650);
            --c-area: color-mix(in srgb, var(--teal-500) 15%, transparent);
            --c-area-edge: color-mix(in srgb, var(--teal-650) 35%, transparent);
            --c-plan: var(--brand-blue);
            /* The feature band: a soft teal gradient, and its rules and empty tracks. */
            --band-bg: radial-gradient(120% 140% at 0% 0%, var(--teal-band-1) 0%, transparent 60%),
                       linear-gradient(110deg, var(--teal-band-2) 0%, var(--teal-band-3) 55%, var(--teal-band-4) 100%);
            --band-rule: color-mix(in srgb, var(--teal-900) 12%, transparent);
            --border-soft: var(--line-soft);
            /* Focus: a 2px teal-line ring 2px off the edge, drawn as a ring for a
               field and as an outline for everything else. */
            --focus-ring: 0 0 0 var(--bw-strong) var(--white), 0 0 0 calc(2 * var(--bw-strong)) var(--teal-650);
            --focus-outline: var(--bw-strong) solid var(--teal-650);
```

- [ ] **Step 5: Add the five shadows, the rings and the rules**

Replace:

```
            --shadow-md: 0 0 0 1px color-mix(in srgb, var(--ink) 10%, transparent),
                         0 4px 6px -1px color-mix(in srgb, var(--black) 10%, transparent),
                         0 2px 4px -2px color-mix(in srgb, var(--black) 10%, transparent);
            --shadow-lg: 0 10px 15px -3px color-mix(in srgb, var(--black) 10%, transparent),
                         0 4px 6px -4px color-mix(in srgb, var(--black) 10%, transparent);
```

with:

```
            /* The mix's five shadows: a control's 1px lift, a raised knob, what
               floats (menus, popovers, the tooltip, dialogs, toasts, the drawer),
               the chosen counter's teal glow, and the label preview. */
            --shadow-control: 0 1px 1px color-mix(in srgb, var(--ink) 4%, transparent);
            --shadow-raise: 0 1px 2px color-mix(in srgb, var(--ink) 8%, transparent),
                            0 0 0 1px color-mix(in srgb, var(--ink) 5%, transparent);
            --shadow-pop: 0 16px 40px -12px color-mix(in srgb, var(--ink) 22%, transparent),
                          0 4px 10px -4px color-mix(in srgb, var(--ink) 8%, transparent),
                          0 0 0 1px color-mix(in srgb, var(--ink) 7%, transparent);
            --shadow-focal: 0 1px 2px color-mix(in srgb, var(--teal-900) 18%, transparent),
                            0 8px 20px -10px color-mix(in srgb, var(--teal-500) 70%, transparent);
            --shadow-label: 0 2px 6px -2px color-mix(in srgb, var(--ink) 12%, transparent);
            --shadow-md: var(--shadow-pop); --shadow-lg: var(--shadow-pop);
            /* The chosen segment (a lift and a teal hairline), the live dot's
               halo, the open row's 2px teal edge. */
            --ring-chosen: var(--shadow-control), inset 0 0 0 var(--bw-hairline) var(--teal-650);
            --ring-live: 0 0 0 var(--sp-0-5) var(--live-halo);
            --ring-selected: inset var(--bw-strong) 0 0 var(--teal-650);
            /* Hairlines drawn as inset shadows, so a rule never adds height:
               --border-default frames a list, --border-soft divides its rows. */
            --rule-t: inset 0 var(--bw-hairline) 0 var(--border-default); --rule-b: inset 0 calc(-1 * var(--bw-hairline)) 0 var(--border-default);
            --rule-t-soft: inset 0 var(--bw-hairline) 0 var(--border-soft); --rule-b-soft: inset 0 calc(-1 * var(--bw-hairline)) 0 var(--border-soft);
            --rule-t-band: inset 0 var(--bw-hairline) 0 var(--band-rule);
```

- [ ] **Step 6: List them for the Design section**

Replace:

```js
        const MIX_TOKENS = [
            ['Greys', ['--ink', '--ink-2', '--ink-3', '--ink-4', '--line-ctl', '--line', '--line-soft', '--fill', '--white']],
        ];
```

with:

```js
        const MIX_TOKENS = [
            ['Greys', ['--ink', '--ink-2', '--ink-3', '--ink-4', '--line-ctl', '--line', '--line-soft', '--fill', '--white']],
            ['The ink frame', ['--surface-chrome', '--text-on-chrome', '--nav-text', '--nav-muted', '--chrome-fill', '--chrome-press', '--nav-on-bg', '--nav-on-icon']],
            ['One colour per measure', ['--c-taken', '--c-still', '--c-exp', '--c-exp-line', '--c-range', '--c-range-edge', '--c-area', '--c-area-edge', '--c-plan']],
            ['The feature band', ['--band-bg', '--band-rule', '--teal-band-1', '--teal-band-2', '--teal-band-3', '--teal-band-4']],
            ['Shadows and rules', ['--shadow-control', '--shadow-raise', '--shadow-pop', '--shadow-focal', '--shadow-label', '--ring-chosen', '--ring-live', '--ring-selected', '--rule-t', '--rule-b', '--rule-t-soft', '--rule-b-soft', '--rule-t-band']],
            ['States', ['--press', '--press-fill', '--link-underline', '--live-dot', '--live-halo', '--live-green', '--border-soft']],
        ];
```

- [ ] **Step 7: Update the elevation guard**

In `t_the_card_elevation_token_actually_paints` replace:

```python
    for tok in ("--shadow-md", "--shadow-lg"):
        v = re.search(tok + r":\s*([^;]+);", CSS).group(1)
        ok("none" not in v and "color-mix" in v, tok + " still paints: what floats is lifted")
```

with:

```python
    # Since the mix (2026-10-06) everything that floats shares the one pop shadow.
    for tok in ("--shadow-md", "--shadow-lg"):
        v = re.search(tok + r":\s*([^;]+);", CSS).group(1)
        ok(v.strip() == "var(--shadow-pop)", tok + " is the one pop shadow")
    pop = re.search(r"--shadow-pop:\s*([^;]+);", CSS).group(1)
    ok("none" not in pop and "color-mix" in pop, "and it still paints: what floats is lifted")
```

- [ ] **Step 8: Run the tests**

Run: `ONLY=t_the_ink_frame python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `429 passed, 0 failed`.

- [ ] **Step 9: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Tokens: the ink frame, one colour per measure, the feature band, five shadows, inset rules and one focus ring

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Type steps, sizes, space roles and corner roles as tokens

**Files:**
- Modify: `static/index.html` tier 2 type, line-height, spacing, radius, switch and wrap lines (177-233) and tier 3 (236-266), the script's `MIX_TOKENS`
- Test: `tests/test_frontend.py` (`t_the_spacing_pass_holds` 9494, `t_every_corner_is_a_role` end of file, `t_a_table_inside_a_card_has_no_second_frame` 2810, a new test)

**Interfaces:**
- Consumes: Tasks 2 and 3.
- Produces: `--text-micro` 11px, `--text-body` 13px, `--text-head` 15px, `--text-title` 26px, `--fig-xl` 44px, `--fig-l` 36px, `--fig-m` 28px, `--fig-s` (`var(--text-2xl)`, 24), `--tr-title` -0.02em, `--tr-fig` -0.03em, `--lh-caption` 16px, `--lh-title` 32px; `--row-h` 44px, `--row-h-2` 60px, `--order-row-h` 64px, `--icon-stroke` 1.75, `--icon-stroke-s` 2, `--frame-inset` (`var(--sp-2)`); `--sp-9` 48px, `--sp-10` 64px; `--gap-row-icon`, `--gap-cluster`, `--gap-fig`, `--gap-cols`, `--pop-offset`, `--pop-pad`, `--tip-pad`, `--menu-pad`; `--radius-md` 10px, `--radius-lg` 12px; roles `--radius-pop`, `--radius-tile`, `--radius-sheet`, `--radius-band`. Changed: `--control-gap` 8 (`var(--sp-2)`), `--sidebar-w` 236px, `--wrap-pad` 40 (`var(--sp-8)`), `--switch-w` 28px, `--switch-h` 16px, `--segment-h` `calc(var(--control-h) - 2 * var(--sp-0-5))` (a 28 choice in a 32 track), `--radius-card` `var(--radius-pop)`.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_the_mix_type_sizes_space_and_corners_are_tokens():
    """Spec 4.2 to 4.5: five Inter steps with one line height each, Bricolage's
    two sizes, four figure sizes, the control and row heights, the 4px scale's
    roles and one corner per role. Each is set once here."""
    for tok, v in (("text-micro", "11px"), ("text-xs", "12px"), ("text-body", "13px"), ("text-sm", "14px"),
                   ("text-head", "15px"), ("text-md", "16px"), ("text-2xl", "24px"), ("text-title", "26px"),
                   ("fig-xl", "44px"), ("fig-l", "36px"), ("fig-m", "28px"), ("fig-s", "var(--text-2xl)"),
                   ("tr-title", "-0.02em"), ("tr-fig", "-0.03em"), ("lh-caption", "16px"), ("lh-control", "20px"),
                   ("lh-title", "32px"), ("lh-none", "1"),
                   ("tag-h", "20px"), ("control-h-sm", "24px"), ("control-h-md", "28px"), ("control-h", "32px"),
                   ("control-h-lg", "40px"), ("row-h", "44px"), ("row-h-2", "60px"), ("order-row-h", "64px"),
                   ("box-2xl", "40px"), ("icon-md", "16px"), ("icon-sm", "14px"), ("icon-stroke", "1.75"),
                   ("icon-stroke-s", "2"), ("topbar-h", "48px"), ("sidebar-w", "236px"), ("frame-inset", "var(--sp-2)"),
                   ("wrap-pad", "var(--sp-8)"), ("sp-9", "48px"), ("sp-10", "64px"),
                   ("control-gap", "var(--sp-2)"), ("gap-row-icon", "var(--sp-3)"), ("gap-cluster", "var(--sp-4)"),
                   ("gap-fig", "var(--sp-3)"), ("gap-cols", "var(--sp-10)"), ("pop-offset", "var(--sp-2)"),
                   ("pop-pad", "var(--sp-4)"), ("tip-pad", "var(--sp-3)"), ("menu-pad", "var(--sp-1)"),
                   ("radius-3xs", "2px"), ("radius-2xs", "4px"), ("radius-xs", "6px"), ("radius-md", "10px"),
                   ("radius-lg", "12px"), ("radius-pop", "var(--radius-md)"), ("radius-tile", "var(--radius-md)"),
                   ("radius-sheet", "var(--radius-lg)"), ("radius-band", "var(--radius-sheet)"),
                   ("radius-card", "var(--radius-pop)"), ("switch-w", "28px"), ("switch-h", "16px"),
                   ("switch-inset", "2px"), ("segment-h", "calc(var(--control-h) - 2 * var(--sp-0-5))")):
        eq(_token_raw(tok), v, "--" + tok)
    tokens = SCRIPT.split("const MIX_TOKENS = [")[1].split("];")[0]
    for group in ("'Type'", "'Sizes'", "'Space'", "'Corners'"):
        ok(group in tokens, "the Design section lists " + group)
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_the_mix_type_sizes python3 tests/test_frontend.py`
Expected: `FAIL  t_the_mix_type_sizes_space_and_corners_are_tokens: token --text-micro not found`

- [ ] **Step 3: The type steps, figures and line heights**

Replace:

```
            --text-xs: 12px; --text-sm: 14px; --text-md: 16px; --text-lg: 18px; --text-xl: 20px; --text-2xl: 24px; --text-3xl: 30px;
            --weight-regular: 400; --weight-medium: 500; --weight-semibold: 600;
            --lh-none: 1; --lh-tight: 1.15; --lh-snug: 1.35; --lh-body: 1.5; --lh-prose: 1.6; --lh-control: 20px;
```

with:

```
            /* The mix (4.2): five Inter steps, each with one line height: micro
               11/16, caption 12/16 (--text-xs), body 13/20, body-l 14/20
               (--text-sm, for order names, and every control and row title on a
               phone), head 15/20. --text-md is the wordmark's 16, --text-title
               the page title's 26 (24 on a phone, --text-2xl). Figures are Inter
               600 at 44, 36, 28 and 24, tabular, on a line of 1. --text-lg,
               --text-xl and --text-3xl leave in the type sweep (Task 25). */
            --text-micro: 11px; --text-xs: 12px; --text-body: 13px; --text-sm: 14px; --text-head: 15px; --text-md: 16px;
            --text-lg: 18px; --text-xl: 20px; --text-2xl: 24px; --text-title: 26px; --text-3xl: 30px;
            --fig-xl: 44px; --fig-l: 36px; --fig-m: 28px; --fig-s: var(--text-2xl);
            --tr-title: -0.02em; --tr-fig: -0.03em;
            --weight-regular: 400; --weight-medium: 500; --weight-semibold: 600;
            --lh-none: 1; --lh-tight: 1.15; --lh-snug: 1.35; --lh-body: 1.5; --lh-prose: 1.6;
            --lh-caption: 16px; --lh-control: 20px; --lh-title: 32px;
```

- [ ] **Step 4: The two new space steps**

Replace:

```
            --sp-4: 16px; --sp-5: 20px; --sp-6: 24px; --sp-7: 32px; --sp-8: 40px;
```

with:

```
            --sp-4: 16px; --sp-5: 20px; --sp-6: 24px; --sp-7: 32px; --sp-8: 40px; --sp-9: 48px; --sp-10: 64px;
```

- [ ] **Step 5: The two new corner sizes**

Replace:

```
            --radius-3xs: 2px; --radius-2xs: 4px; --radius-xs: 6px; --radius-sm: 8px;
```

with:

```
            --radius-3xs: 2px; --radius-2xs: 4px; --radius-xs: 6px; --radius-sm: 8px; --radius-md: 10px; --radius-lg: 12px;
```

- [ ] **Step 6: The switch**

Replace:

```
            --switch-w: 32px; --switch-h: 18px; --switch-inset: 2px;
```

with:

```
            --switch-w: 28px; --switch-h: 16px; --switch-inset: 2px;   /* a 28 by 16 track, a 12 knob */
```

- [ ] **Step 7: Icon strokes, the gutter**

Replace:

```
            --icon-xs: 12px; --icon-sm: 14px; --icon-md: 16px; --icon-lg: 18px; --icon-xl: 20px;
```

with:

```
            --icon-xs: 12px; --icon-sm: 14px; --icon-md: 16px; --icon-lg: 18px; --icon-xl: 20px;
            /* 16 at 1.75 in every control, row, tile and nav item; 14 at 2 only
               for inline glyphs (crumb, link and list chevrons, chip arrows). */
            --icon-stroke: 1.75; --icon-stroke-s: 2;
```

Replace:

```
            --wrap: 1536px; --wrap-pad: 24px;
```

with:

```
            --wrap: 1536px; --wrap-pad: var(--sp-8);   /* the gutter: 40 on a desktop, 16 on a phone (re-pointed at 640) */
```

- [ ] **Step 8: The component tier**

Replace:

```
            --control-h: 32px; --control-h-sm: 24px; --control-h-lg: 40px;
```

with:

```
            --control-h: 32px; --control-h-sm: 24px; --control-h-lg: 40px;
            /* Rows (the mix, 4.3): a one-line row and the tab strip 44, a
               two-line phone row 60, an order row 64. */
            --row-h: 44px; --row-h-2: 60px; --order-row-h: 64px;
            /* Gaps by role (4.4): icon to label is --control-gap; a leading
               icon in a row 12; group to group 16; figure label to figure and
               figure to chip 12; the page's two-column split 64; a popover 8
               from its trigger with 16 inside; a tooltip 12 inside; a menu 4. */
            --gap-row-icon: var(--sp-3); --gap-cluster: var(--sp-4); --gap-fig: var(--sp-3); --gap-cols: var(--sp-10);
            --pop-offset: var(--sp-2); --pop-pad: var(--sp-4); --tip-pad: var(--sp-3); --menu-pad: var(--sp-1);
```

Replace:

```
            --radius-control: var(--radius-xs); --radius-card: var(--radius-sm); --radius-field: var(--radius-control);
```

with:

```
            --radius-control: var(--radius-xs); --radius-field: var(--radius-control);
            /* The mix (4.5): 10 for what floats and for a queue counter, 12 for
               the sheet and the feature band. A card has no box any more; the
               name stays for the few boxed things that read it, at the pop corner. */
            --radius-pop: var(--radius-md); --radius-tile: var(--radius-md);
            --radius-sheet: var(--radius-lg); --radius-band: var(--radius-sheet);
            --radius-card: var(--radius-pop);
```

Replace:

```
            --control-gap: var(--sp-1-5);           /* icon to text inside any control */
```

with:

```
            --control-gap: var(--sp-2);             /* icon to text inside any control, label to its count */
```

Replace:

```
            --segment-h: calc(var(--control-h-md) - 2 * var(--sp-0-5));
```

with:

```
            --segment-h: calc(var(--control-h) - 2 * var(--sp-0-5));   /* a 28 choice in a 32 track */
```

Replace:

```
            --sidebar-w: 272px; --topbar-h: 48px;
```

with:

```
            --sidebar-w: 236px; --topbar-h: 48px; --frame-inset: var(--sp-2);   /* the sheet sits 8 inside the ink frame */
```

- [ ] **Step 9: List them for the Design section**

In `MIX_TOKENS`, after the `['States', [...]],` line, add:

```js
            ['Type', ['--text-micro', '--text-xs', '--text-body', '--text-sm', '--text-head', '--text-md', '--text-title', '--fig-xl', '--fig-l', '--fig-m', '--fig-s', '--lh-caption', '--lh-control', '--lh-title', '--tr-title', '--tr-fig']],
            ['Sizes', ['--tag-h', '--control-h-sm', '--control-h-md', '--control-h', '--row-h', '--row-h-2', '--order-row-h', '--control-h-lg', '--box-2xl', '--icon-md', '--icon-sm', '--icon-stroke', '--icon-stroke-s', '--topbar-h', '--sidebar-w', '--frame-inset', '--wrap-pad']],
            ['Space', ['--sp-1', '--sp-2', '--sp-3', '--sp-4', '--sp-5', '--sp-6', '--sp-7', '--sp-8', '--sp-9', '--sp-10', '--control-gap', '--gap-row-icon', '--gap-cluster', '--gap-fig', '--gap-cols', '--pop-offset', '--pop-pad', '--tip-pad', '--menu-pad']],
            ['Corners', ['--radius-swatch', '--radius-tag', '--radius-control', '--radius-pop', '--radius-tile', '--radius-sheet', '--radius-band', '--radius-full']],
```

- [ ] **Step 10: Update the guards that pinned the old sizes and corners**

In `t_the_spacing_pass_holds` replace:

```python
    ok("--segment-h: calc(var(--control-h-md) - 2 * var(--sp-0-5));" in CSS
       and "height: var(--segment-h);" in CSS.split("\n        .segmented > button {")[1].split("}")[0],
       "a segmented track is a small control's 28, level with the field beside it")
```

with:

```python
    ok("--segment-h: calc(var(--control-h) - 2 * var(--sp-0-5));" in CSS
       and "height: var(--segment-h);" in CSS.split("\n        .segmented > button {")[1].split("}")[0],
       "a segmented track is a control's 32, level with the field beside it, its choice 28 inside")
```

In `t_every_corner_is_a_role` replace:

```python
    for role, prim in (("control", "var(--radius-xs)"), ("field", "var(--radius-control)"), ("card", "var(--radius-sm)"),
                       ("inset", "var(--radius-xs)"), ("tag", "var(--radius-2xs)"), ("row", "var(--radius-control)")):
```

with:

```python
    for role, prim in (("control", "var(--radius-xs)"), ("field", "var(--radius-control)"), ("card", "var(--radius-pop)"),
                       ("inset", "var(--radius-xs)"), ("tag", "var(--radius-2xs)"), ("row", "var(--radius-control)"),
                       ("pop", "var(--radius-md)"), ("tile", "var(--radius-md)"), ("sheet", "var(--radius-lg)")):
```

In `t_a_table_inside_a_card_has_no_second_frame` replace:

```python
    ok("--radius-inset: var(--radius-xs)" in CSS and "--radius-card: var(--radius-sm)" in CSS,
       "a step under the card's corner, set once")
```

with:

```python
    ok("--radius-inset: var(--radius-xs)" in CSS and "--radius-card: var(--radius-pop)" in CSS,
       "a step under the card's corner, set once")
```

- [ ] **Step 11: Run the tests**

Run: `ONLY=t_the_mix_type_sizes python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `430 passed, 0 failed`.

- [ ] **Step 12: Look at it**

Open `http://127.0.0.1:8920/?fresh=4` in the rig at 1440. Buttons have 8 between icon and word, segmented tracks are 32 tall, the sidebar is 236 wide and the page gutter 40. Nothing overlaps (the parts are rebuilt in Phase 3; this only checks no token broke a screen).

- [ ] **Step 13: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Tokens: five type steps, four figure sizes, the row heights, the gap roles and one corner per role

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
## Phase 2: The shell

### Task 5: The ink frame, the sheet and the sidebar on it

**Files:**
- Modify: `static/index.html:6` (theme-color), `:337-497` (the sidebar block's rules), `:500` (after `.main`), `:2608` (`.nav-new-dot`), `:2632-2637` (Beta), `:4949` (ONE TAG list), `:4991-4994` (the brand row markup), `:5487-5490` (icon wiring), `:29327-29335` (`toggleSidebar`), `:29540` (boot wiring)
- Test: `tests/test_frontend.py` (`t_the_sidebar_does_not_dim_where_you_are_not` 3562, `t_the_sidebar_keeps_one_inset` 2678, `t_the_header_is_one_implementation_with_one_collapse_point` 5919, `t_reactor_wears_projected_images_brand_from_one_place` 9339, a new test)

**Interfaces:**
- Consumes: `--surface-chrome`, `--text-on-chrome`, `--nav-text`, `--nav-muted`, `--chrome-fill`, `--chrome-press`, `--nav-on-bg`, `--nav-on-icon`, `--frame-inset`, `--radius-sheet`, `--gap-row-icon`, `--text-micro`, `--lh-caption`, `--row-h` (Tasks 3 and 4); `toggleSidebar()` (index.html:29327); `I.panelLeft`.
- Produces: the `#side-hide` button (Hide sidebar, the desktop fold); `.brand-mark` is a 24 teal tile span; `.beta-tag` is a micro word (Task 7's `pageHead` puts it by page titles).

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_the_page_is_one_sheet_in_an_ink_frame():
    """Spec 5 (Cameron, 2026-10-05: "go with the dark sidebar"): the chrome is
    ink, the page is one white sheet 8 inside it with a 12 corner and no edge
    or shadow, and the sidebar is the frame itself: its words white at 72%,
    the chosen page teal at 18% with white words and a teal icon."""
    ok("@media screen {\n            #app { background: var(--surface-chrome); }" in CSS, "the frame is ink, on screen only")
    sheet = CSS.split("\n            .main { margin: var(--frame-inset) var(--frame-inset) var(--frame-inset) 0;")
    ok(len(sheet) == 2 and "border-radius: var(--radius-sheet)" in sheet[1].split("}")[0]
       and "background: var(--surface-primary)" in sheet[1].split("}")[0], "the page is one white sheet, 8 in, 12 round")
    ok(CSS.index("@media screen {\n            #app {") > CSS.index("\n        .main {"), "set after the base .main rule")
    side = CSS.split("\n        .sidebar {")[1].split("}")[0]
    ok("background: var(--surface-chrome)" in side and "border-right" not in side, "the sidebar is the ink, with no edge")
    item = CSS.split("\n        .nav-item {")[1].split("}")[0]
    ok("color: var(--nav-text)" in item and "height: var(--control-h)" in item and "gap: var(--gap-row-icon)" in item,
       "a nav row is 32, white at 72%, its icon 12 from its words")
    on = CSS.split('.nav-item:is(.active, [aria-current="page"]) {')[1].split("}")[0]
    ok("background: var(--nav-on-bg)" in on and "color: var(--text-on-chrome)" in on,
       "the chosen one is teal at 18% with white words")
    ok('.nav-item:is(.active, [aria-current="page"]) svg { color: var(--nav-on-icon); }' in CSS, "and a teal icon")
    ok('<span class="brand-mark" aria-hidden="true"></span><span class="brand-name">Reactor</span>' in HTML,
       "the brand row is the teal mark and the wordmark")
    ok('id="side-hide"' in HTML and "$('side-hide').onclick = toggleSidebar;" in SCRIPT, "with Hide sidebar beside it")
    beta = CSS.split("\n        .beta-tag {")[1].split("}")[0]
    ok("font-size: var(--text-micro)" in beta and "background: none" in beta, "Beta is a micro word, not a box")
    ok(".beta-tag" not in CSS.split("ONE TAG.")[1].split("{")[0], "and has left the one tag recipe")
    ok('<meta name="theme-color" content="#121212" />' in HTML, "a phone's own bar is ink too")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_the_page_is_one_sheet python3 tests/test_frontend.py`
Expected: `FAIL  t_the_page_is_one_sheet_in_an_ink_frame: the frame is ink, on screen only`

- [ ] **Step 3: The frame and the sheet**

Replace `    <meta name="theme-color" content="#ffffff" />` with `    <meta name="theme-color" content="#121212" />`.

Directly after the rule `        .main { flex: 1; min-width: 0; display: flex; flex-direction: column; position: relative; }` add:

```css
        /* THE INK FRAME (the mix, spec 5). The chrome is ink; the page is one
           white sheet 8 inside it with a 12 corner, no edge and no shadow.
           Screen only: a report printed to PDF keeps its plain white page. */
        @media screen {
            #app { background: var(--surface-chrome); }
            .main { margin: var(--frame-inset) var(--frame-inset) var(--frame-inset) 0; border-radius: var(--radius-sheet);
                background: var(--surface-primary); overflow: hidden; }
        }
        /* With the sidebar folded away the frame closes round the sheet's left edge too. */
        @media screen and (min-width: 901px) { body.sidebar-collapsed .main { margin-left: var(--frame-inset); } }
```

- [ ] **Step 4: The sidebar is the frame**

Replace:

```css
        .sidebar { width: var(--sidebar-w); flex-shrink: 0; position: relative; z-index: 2;
            /* The reference's sidebar variant: one step darker than the page and
               a hairline on its right edge. Folded away (Cmd+B, or the trigger)
               it slides off by its own width and the page takes the room. */
            background: var(--surface-primary); border-right: var(--bw-hairline) solid var(--border-default);
            display: flex; flex-direction: column; transition: margin-left .2s ease; }
```

with:

```css
        .sidebar { width: var(--sidebar-w); flex-shrink: 0; position: relative; z-index: 2;
            /* The mix: the sidebar is the ink frame itself, its words white at
               72%, no edge. Folded away (Cmd+B, or Hide sidebar) it slides off
               by its own width and the sheet takes the room. */
            background: var(--surface-chrome); color: var(--nav-text);
            display: flex; flex-direction: column; transition: margin-left .2s ease; }
```

Replace `        .side-head { padding: var(--sp-2); flex: none; }` with:

```css
        .side-head { padding: var(--sp-3) var(--sp-3) 0; flex: none; display: flex; align-items: center; gap: var(--control-gap); }
```

Replace `        .side-foot { padding: var(--sp-2); flex: none; display: flex; flex-direction: column; gap: var(--sp-2); }` with:

```css
        .side-foot { padding: 0 var(--sp-3) var(--sp-3); flex: none; display: flex; flex-direction: column; gap: var(--sp-2); }
```

- [ ] **Step 5: The brand row**

Replace:

```css
        .brand { display: flex; align-items: center; gap: var(--sp-2); width: 100%; height: var(--control-h); padding: 0 var(--sp-2);
            border: 0; border-radius: var(--radius-row); background: transparent; color: var(--text-primary); text-align: left;
            font-family: inherit; font-weight: var(--weight-medium); font-size: var(--text-md); letter-spacing: normal; cursor: pointer;
            transition: background var(--dur) var(--ease); }
        .brand:hover { background: var(--surface-tertiary); }
        .brand:active { background: var(--surface-sunken); }
        /* Projected Image's wordmark, then the product's own name after a
           hairline: the company's tool, said once, at the top of every page. */
        .brand .brand-mark { height: var(--box-md); width: auto; flex: none; display: block; }
        .brand .brand-sep { width: var(--bw-hairline); align-self: stretch; margin: var(--sp-1-5) 0; background: var(--border-default); flex: none; }
```

with:

```css
        .brand { display: flex; align-items: center; gap: var(--control-gap); flex: 1; min-width: 0; height: var(--control-h); padding: 0 var(--sp-1);
            border: 0; border-radius: var(--radius-row); background: transparent; color: var(--text-on-chrome); text-align: left;
            font-family: inherit; cursor: pointer; transition: background var(--dur) var(--ease); }
        .brand:hover { background: var(--chrome-fill); }
        .brand:active { background: var(--chrome-press); }
        /* The mix's mark: a 24 teal tile with a 4 corner, then the product's
           name in the wordmark's Bricolage 600 at 16/20, white on the ink. */
        .brand .brand-mark { width: var(--box-md); height: var(--box-md); flex: none; border-radius: var(--radius-tag); background: var(--action-primary); }
        .brand-name { font-size: var(--text-md); line-height: var(--lh-control); font-weight: var(--weight-semibold); letter-spacing: var(--tr-title); }
        /* Hide sidebar: the brand row's 28 ghost square. The top bar's menu
           button brings the sidebar back, and opens the drawer on a phone. */
        .side-hide { flex: none; }
```

In the markup replace:

```html
            <div class="side-head">
                <button class="brand" id="brand-home" type="button" aria-label="Reactor, by Projected Image: go to the Overview"><img class="brand-mark" src="/brand/logo.svg" alt="Projected Image" width="144" height="40" /><span class="brand-sep" aria-hidden="true"></span><span class="brand-name">Reactor</span></button>
            </div>
```

with:

```html
            <div class="side-head">
                <button class="brand" id="brand-home" type="button" aria-label="Reactor, by Projected Image: go to the Overview"><span class="brand-mark" aria-hidden="true"></span><span class="brand-name">Reactor</span></button>
                <button class="icon-btn side-hide" id="side-hide" type="button" title="Hide sidebar" aria-label="Hide sidebar" aria-keyshortcuts="Meta+B" aria-controls="sidebar" aria-expanded="true"></button>
            </div>
```

- [ ] **Step 6: Groups and rows on the ink**

Replace `        .nav { padding: var(--sp-2); display: flex; flex-direction: column; gap: 0; }` with:

```css
        .nav { padding: var(--sp-4) var(--sp-3) 0; display: flex; flex-direction: column; gap: 0; }
```

Replace:

```css
        .nav-group { font-size: var(--text-xs); font-weight: var(--weight-medium); color: var(--text-secondary);
            height: var(--control-h); display: flex; align-items: center; padding: 0 var(--sp-2);
            /* Two groups' 8px paddings meet between them in the reference: 16. */
            margin-top: var(--sp-4);
            /* A toggle, as the reference's collapsible group label is: the
               whole row, the group's own type, a muted pill under the pointer. */
            width: 100%; background: none; border: 0; border-radius: var(--radius-row); text-align: left;
            font-family: inherit; cursor: pointer; transition: background var(--dur) var(--ease), color var(--dur) var(--ease); }
        .nav-group:hover { background: var(--surface-tertiary); color: var(--text-primary); }
        .nav-group:first-child { margin-top: 0; }
        /* The chevron points right when the group is folded and turns to
           point down when it is open, the reference's own cue. */
        .nav-group .nav-caret { margin-left: auto; display: grid; place-items: center; color: var(--text-tertiary);
            transition: transform var(--dur) var(--ease); }
        .nav-group .nav-caret svg { width: var(--sp-4); height: var(--sp-4); display: block; }
```

with:

```css
        /* A group head is a caption in muted white, 16 between groups and 4
           above its first row. It stays the fold toggle Cameron asked for: the
           whole row, a caret that turns, the choice remembered. */
        .nav-group { font-size: var(--text-xs); line-height: var(--lh-caption); font-weight: var(--weight-medium); color: var(--nav-muted);
            height: var(--control-h-sm); display: flex; align-items: center; padding: 0 var(--sp-2);
            margin-top: var(--sp-4); margin-bottom: var(--sp-1);
            width: 100%; background: none; border: 0; border-radius: var(--radius-row); text-align: left;
            font-family: inherit; cursor: pointer; transition: background var(--dur) var(--ease), color var(--dur) var(--ease); }
        .nav-group:hover { background: var(--chrome-fill); color: var(--text-on-chrome); }
        .nav-group:first-child { margin-top: 0; }
        /* The chevron points right when the group is folded and turns to
           point down when it is open: a 14 inline glyph at stroke 2. */
        .nav-group .nav-caret { margin-left: auto; display: grid; place-items: center; color: var(--nav-muted);
            transition: transform var(--dur) var(--ease); }
        .nav-group .nav-caret svg { width: var(--icon-sm); height: var(--icon-sm); display: block; stroke-width: var(--icon-stroke-s); }
```

Replace:

```css
        .nav-item { display: flex; align-items: center; gap: var(--sp-2); height: var(--control-h); padding: 0 var(--sp-2);
            border-radius: var(--radius-row); border: 0; background: transparent; color: var(--text-primary);
            font-size: var(--text-sm); font-weight: var(--weight-regular); width: 100%; text-align: left;
            /* Brought into view clear of the sidebar's fade below. */
            scroll-margin-block: var(--sp-8);
            transition: background var(--dur) var(--ease), color var(--dur) var(--ease); }
        .nav-item:hover { background: var(--surface-tertiary); color: var(--text-primary); }
        .nav-item:active { background: var(--surface-sunken); }
        .nav-item:is(.active, [aria-current="page"]) { background: var(--action-selected); color: var(--text-brand); font-weight: var(--weight-medium); box-shadow: none; }
        .nav-item svg { width: var(--icon-md); height: var(--icon-md); flex-shrink: 0; opacity: 1; }
        .nav-item:is(.active, [aria-current="page"]) svg { color: var(--text-brand); }
```

with:

```css
        .nav-item { display: flex; align-items: center; gap: var(--gap-row-icon); height: var(--control-h); padding: 0 var(--sp-2);
            border-radius: var(--radius-row); border: 0; background: transparent; color: var(--nav-text);
            font-size: var(--text-body); line-height: var(--lh-control); font-weight: var(--weight-medium); width: 100%; text-align: left; white-space: nowrap;
            /* Brought into view clear of the sidebar's fade below. */
            scroll-margin-block: var(--sp-8);
            transition: background var(--dur) var(--ease), color var(--dur) var(--ease); }
        .nav-item:hover { background: var(--chrome-fill); color: var(--text-on-chrome); }
        .nav-item:active { background: var(--chrome-press); }
        /* Where you are: teal at 18% on the ink, white words, a teal icon.
           Every other row keeps its 72% white; nothing else is dimmed. */
        .nav-item:is(.active, [aria-current="page"]) { background: var(--nav-on-bg); color: var(--text-on-chrome); font-weight: var(--weight-medium); box-shadow: none; }
        .nav-item svg { width: var(--icon-md); height: var(--icon-md); flex-shrink: 0; opacity: 1; color: var(--nav-muted); }
        .nav-item:is(.active, [aria-current="page"]) svg { color: var(--nav-on-icon); }
```

- [ ] **Step 7: Conversations, the sidebar's icon buttons and the account row**

Replace:

```css
        .convo-head { display: flex; align-items: center; justify-content: space-between; height: var(--control-h); padding: 0 var(--sp-2); margin: var(--sp-4) var(--sp-2) 0; }
        .convo-head span { font-size: var(--text-xs); font-weight: var(--weight-medium); text-transform: none; letter-spacing: normal; color: var(--text-secondary); }
```

with:

```css
        .convo-head { display: flex; align-items: center; justify-content: space-between; height: var(--control-h); padding: 0 var(--sp-2); margin: var(--sp-4) var(--sp-3) 0; }
        .convo-head span { font-size: var(--text-xs); line-height: var(--lh-caption); font-weight: var(--weight-medium); text-transform: none; letter-spacing: normal; color: var(--nav-muted); }
```

Directly after `        .icon-btn svg { width: var(--icon-md); height: var(--icon-md); }` add:

```css
        /* On the ink a sidebar icon button is a 28 ghost square in muted
           white, white under the pointer. */
        .sidebar .icon-btn { min-width: var(--control-h-md); min-height: var(--control-h-md); color: var(--nav-muted); }
        .sidebar .icon-btn:hover { background: var(--chrome-fill); color: var(--text-on-chrome); }
        .sidebar .icon-btn:active { background: var(--chrome-press); }
```

Replace `        .convos { flex: none; padding: 0 var(--sp-2) var(--sp-2); display: flex; flex-direction: column; gap: 0; }` with:

```css
        .convos { flex: none; padding: 0 var(--sp-3) var(--sp-3); display: flex; flex-direction: column; gap: 0; }
```

Replace `        .convo-band { font-size: var(--text-xs); color: var(--text-tertiary); padding: var(--sp-2) var(--sp-2) var(--sp-1); }` with:

```css
        .convo-band { font-size: var(--text-xs); line-height: var(--lh-caption); color: var(--nav-muted); padding: var(--sp-2) var(--sp-2) var(--sp-1); }
```

In the rule `        .convo-dot { width: var(--sp-2); height: var(--sp-2); border-radius: var(--radius-circle); background: var(--fill-mark); flex: none; }` replace `background: var(--fill-mark);` with `background: var(--nav-on-icon);`.

Replace:

```css
        .convo { display: flex; align-items: center; gap: var(--sp-2); padding: var(--sp-2) var(--sp-2); border-radius: var(--radius-row); color: var(--text-secondary);
            font-size: var(--text-sm); cursor: pointer; border: 0; background: transparent; width: 100%; text-align: left; transition: background var(--dur) var(--ease), color var(--dur) var(--ease), border-color var(--dur) var(--ease), opacity var(--dur) var(--ease); }
        .convo:hover { background: var(--surface-tertiary); color: var(--text-primary); }
        .convo:active { background: var(--surface-sunken); }
        .convo:is(.active, [aria-current="true"]) { background: var(--action-selected); color: var(--text-brand); font-weight: var(--weight-medium); }
```

with:

```css
        .convo { display: flex; align-items: center; gap: var(--sp-2); min-height: var(--control-h); padding: 0 var(--sp-2); border-radius: var(--radius-row); color: var(--nav-text);
            font-size: var(--text-body); line-height: var(--lh-control); cursor: pointer; border: 0; background: transparent; width: 100%; text-align: left; transition: background var(--dur) var(--ease), color var(--dur) var(--ease), border-color var(--dur) var(--ease), opacity var(--dur) var(--ease); }
        .convo:hover { background: var(--chrome-fill); color: var(--text-on-chrome); }
        .convo:active { background: var(--chrome-press); }
        .convo:is(.active, [aria-current="true"]) { background: var(--nav-on-bg); color: var(--text-on-chrome); font-weight: var(--weight-medium); }
```

In the rule that begins `        .convo .del { opacity: 0; color: var(--text-tertiary);` replace `color: var(--text-tertiary);` with `color: var(--nav-muted);`.

Replace `        .convo-empty { color: var(--text-tertiary); font-size: var(--text-xs); padding: var(--sp-2) var(--sp-2); }` with:

```css
        .convo-empty { color: var(--nav-muted); font-size: var(--text-xs); line-height: var(--lh-caption); padding: var(--sp-2) var(--sp-2); }
```

Replace:

```css
        .side-user { display: flex; align-items: center; gap: var(--sp-2); width: 100%; height: 48px; padding: var(--sp-2);
            border: 0; border-radius: var(--radius-row); background: transparent; color: var(--text-primary);
            font: inherit; text-align: left; cursor: pointer; transition: background var(--dur) var(--ease); }
        .side-user:hover, .side-user[aria-expanded="true"] { background: var(--surface-tertiary); }
        .side-user:active { background: var(--surface-sunken); }
        .side-avatar { width: var(--control-h); height: var(--control-h); flex: none; border-radius: var(--radius-circle);
            background: var(--surface-sunken); color: var(--text-secondary); display: grid; place-items: center;
            font-size: var(--text-sm); font-weight: var(--weight-medium); }
        .side-user-text { flex: 1; min-width: 0; display: grid; gap: var(--sp-0-5); line-height: var(--lh-tight); }
        .side-user-name { font-size: var(--text-sm); font-weight: var(--weight-medium); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .side-user-role { font-size: var(--text-xs); color: var(--text-tertiary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .side-user-more { margin-left: auto; color: var(--text-tertiary); display: grid; place-items: center; flex: none; }
```

with:

```css
        /* The account: a 44 row, a 24 round initial on the chrome fill, the
           name in white over the role in muted white, and the menu glyph. */
        .side-user { display: flex; align-items: center; gap: var(--control-gap); width: 100%; height: var(--row-h); padding: 0 var(--sp-0-5) 0 var(--sp-1);
            border: 0; border-radius: var(--radius-row); background: transparent; color: var(--text-on-chrome);
            font: inherit; text-align: left; cursor: pointer; transition: background var(--dur) var(--ease); }
        .side-user:hover, .side-user[aria-expanded="true"] { background: var(--chrome-fill); }
        .side-user:active { background: var(--chrome-press); }
        .side-avatar { width: var(--box-md); height: var(--box-md); flex: none; border-radius: var(--radius-circle);
            background: var(--chrome-fill); color: var(--text-on-chrome); display: grid; place-items: center;
            font-size: var(--text-micro); line-height: var(--lh-caption); font-weight: var(--weight-medium); }
        .side-user-text { flex: 1; min-width: 0; display: grid; gap: 0; }
        .side-user-name { font-size: var(--text-body); line-height: var(--lh-control); font-weight: var(--weight-medium); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .side-user-role { font-size: var(--text-xs); line-height: var(--lh-caption); color: var(--nav-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .side-user-more { margin-left: auto; color: var(--nav-muted); display: grid; place-items: center; flex: none; width: var(--control-h-md); height: var(--control-h-md); }
```

In the rule `        .nav-new-dot { width: var(--dot-md); ...` replace `background: var(--fill-mark);` with `background: var(--nav-on-icon);`.

- [ ] **Step 8: Beta is a word**

Replace:

```css
        .beta-tag { margin-left: auto; flex: none; height: var(--tag-h); display: inline-flex; align-items: center; font-size: var(--text-xs); font-weight: var(--weight-medium);
            letter-spacing: normal; text-transform: none; color: var(--text-secondary); background: var(--surface-sunken);
            border: 0; border-radius: var(--radius-tag); padding: 0 var(--sp-1-5); line-height: var(--lh-none); }
        .nav-item:is(.active, [aria-current="page"]) .beta-tag { color: var(--text-brand); background: var(--surface-primary); }
        /* In a page heading it sits on the baseline of the title, not above it. */
        .ov-hero .beta-tag { margin-left: var(--sp-2); vertical-align: middle; position: relative; top: -2px; }
```

with:

```css
        /* Beta is a word, not a box (the mix, spec 5): micro type after the
           name, muted white in the sidebar, ink-3 beside a page title. */
        .beta-tag { margin-left: auto; flex: none; display: inline; font-family: var(--font-sans); font-size: var(--text-micro); line-height: var(--lh-caption);
            font-weight: var(--weight-medium); letter-spacing: normal; text-transform: none; color: var(--nav-muted); background: none;
            border: 0; padding: 0; }
        .nav-item:is(.active, [aria-current="page"]) .beta-tag { color: var(--nav-text); }
        .ov-hero .beta-tag { margin-left: 0; color: var(--text-tertiary); }
```

Replace `        #view-title .beta-tag { margin-left: var(--sp-2); vertical-align: middle; }` with:

```css
        #view-title .beta-tag { margin-left: var(--sp-2); color: var(--text-tertiary); }
```

In the ONE TAG selector list replace `:is(.pill, .kbadge, .lbl-chip, .beta-tag, .crm-prio,` with `:is(.pill, .kbadge, .lbl-chip, .crm-prio,`.

- [ ] **Step 9: One trigger per state**

Replace `        .menu-btn { display: inline-grid; }` with:

```css
        .menu-btn { display: inline-grid; }
        /* On a desk the sidebar's own Hide sidebar is in view, so the top bar's
           trigger steps aside until the sidebar is folded away. On a phone it
           is the drawer's only door. */
        @media (min-width: 901px) { body:not(.sidebar-collapsed) .menu-btn { display: none; } }
```

In the script replace `        $('menu-btn').innerHTML = I.panelLeft;` with:

```js
        $('menu-btn').innerHTML = I.panelLeft;
        $('side-hide').innerHTML = I.panelLeft;
```

Replace `        $('menu-btn').onclick = toggleSidebar; $('backdrop').onclick = closeSidebar;` with:

```js
        $('menu-btn').onclick = toggleSidebar; $('backdrop').onclick = closeSidebar;
        $('side-hide').onclick = toggleSidebar;
```

In `toggleSidebar` replace:

```js
            const closed = document.body.classList.toggle('sidebar-collapsed');
            $('menu-btn').setAttribute('aria-expanded', String(!closed));
```

with:

```js
            const closed = document.body.classList.toggle('sidebar-collapsed');
            $('menu-btn').setAttribute('aria-expanded', String(!closed));
            $('side-hide').setAttribute('aria-expanded', String(!closed));
            /* The button just pressed leaves the screen: focus follows to the
               one that brings the sidebar back, or to Hide sidebar again. */
            if (closed && document.activeElement === $('side-hide')) $('menu-btn').focus({ preventScroll: true });
            if (!closed && document.activeElement === $('menu-btn')) $('side-hide').focus({ preventScroll: true });
```

- [ ] **Step 10: Update the sidebar and header guards**

Replace the whole body of `t_the_sidebar_does_not_dim_where_you_are_not` (from its docstring through its last `ok`) with:

```python
    """The reference marks position with a fill and a weight, and leaves every
    other label at full strength. Since the mix (2026-10-06) the sidebar is
    the ink frame: every row is white at 72%, and where you are is teal at 18%
    with white words and a teal icon. Nothing else is dimmed."""
    item = CSS.split(".nav-item {")[1].split("}")[0]
    ok("height: var(--control-h)" in item, "nav items are 32px")
    ok("color: var(--nav-text)" in item, "an inactive item is the frame's 72% white")
    ok("font-weight: var(--weight-medium)" in item, "at the nav's one weight")
    act = CSS.split(".nav-item:is(.active, [aria-current=\"page\"]) {")[1].split("}")[0]
    ok("background: var(--nav-on-bg)" in act and "color: var(--text-on-chrome)" in act,
       "the active one is teal at 18% with white words")
    side = CSS.split(".sidebar {")[1].split("}")[0]
    ok("background: var(--surface-chrome)" in side and "border-right" not in side, "the sidebar is the ink frame, with no edge")
    grp = CSS.split(".nav-group {")[1].split("}")[0]
    ok("color: var(--nav-muted)" in grp, "group labels are the frame's muted white")
```

In `t_the_sidebar_keeps_one_inset` replace:

```python
        block = re.search(sel, CSS).group(0)
        ok("var(--sp-2)" in block, why + " shares the 8px inset: " + block[:90])
```

with:

```python
        block = re.search(sel, CSS).group(0)
        ok("var(--sp-3)" in block, why + " shares the sidebar's 12px inset: " + block[:90])
```

In `t_the_header_is_one_implementation_with_one_collapse_point` replace:

```python
    ok(".menu-btn { display: inline-grid; }" in CSS, "the trigger is always shown")
    for m in re.finditer(r"@media[^{]*\{", CSS):
        depth, i = 1, m.end()
        while i < len(CSS) and depth:
            depth += {"{": 1, "}": -1}.get(CSS[i], 0); i += 1
        ok(".menu-btn" not in CSS[m.end():i], "and no breakpoint hides or reveals it: " + m.group(0))
```

with:

```python
    # The mix (2026-10-06): on a desk the brand row's Hide sidebar folds the
    # sidebar and the top bar's trigger brings it back; on a phone that trigger
    # opens the drawer. One rule says which, by whether the sidebar is shown.
    ok(".menu-btn { display: inline-grid; }" in CSS, "the top bar's trigger exists")
    hits = []
    for m in re.finditer(r"@media[^{]*\{", CSS):
        depth, i = 1, m.end()
        while i < len(CSS) and depth:
            depth += {"{": 1, "}": -1}.get(CSS[i], 0); i += 1
        if ".menu-btn" in CSS[m.end():i]:
            hits.append(CSS[m.start():i])
    # (ok, not eq: this test sits above the line that defines eq, and the
    # harness runs each test as it is declared.)
    ok(hits == ["@media (min-width: 901px) { body:not(.sidebar-collapsed) .menu-btn { display: none; } }"],
       "one breakpoint rule shows or hides it, by whether the sidebar is in view: %r" % hits)
    ok("$('side-hide').onclick = toggleSidebar;" in SCRIPT, "and Hide sidebar is the same toggle")
```

In `t_reactor_wears_projected_images_brand_from_one_place` replace:

```python
    ok('<img class="brand-mark" src="/brand/logo.svg" alt="Projected Image"' in HTML, "the wordmark heads the sidebar")
```

with:

```python
    ok('<span class="brand-mark" aria-hidden="true"></span><span class="brand-name">Reactor</span>' in HTML,
       "the teal mark and the wordmark head the sidebar (the mix: the ink logo would vanish on the ink frame)")
```

- [ ] **Step 11: Run the tests**

Run: `ONLY=t_the_page_is_one_sheet python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `431 passed, 0 failed`.

- [ ] **Step 12: Look at it**

In the rig at 1440 (`http://127.0.0.1:8920/?fresh=5`): the sidebar is ink with white words, the chosen page teal at 18%, Beta a small word; the page is a white sheet with an 8 ink edge and rounded corners. Press Hide sidebar: the sidebar folds, the sheet keeps its 8 edge, the top bar's menu button appears; press it: the sidebar returns and focus lands on Hide sidebar.

- [ ] **Step 13: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Shell: one white sheet in an ink frame, the sidebar is the frame, Beta is a word, Hide sidebar in the brand row

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The top bar: crumbs and search, and the phone's ink bar

**Files:**
- Modify: `static/index.html` `:root` tier 3 (a `--find-w` token), `:501-532` (top bar rules), `:4492-4500` (after the drawer block), `:5059-5069` (top bar markup), `:5487-5494` (icon wiring), `:29156` (`setViewTitle`), `:29212-29235` (`setView`)
- Test: `tests/test_frontend.py` (`t_the_beta_tabs_say_so_everywhere_they_are_named` 2645, `t_the_header_is_one_implementation_with_one_collapse_point` 5919, a new test)

**Interfaces:**
- Consumes: Task 5's frame; `I.chev`, `I.search`; `--find-w` (added here).
- Produces: `setViewCrumb(v)`; `document.body.dataset.view` holds the current view (phone rules and later tasks read it); the top bar's `#view-crumb`, `#crumb-chev`, `#view-title`.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_the_top_bar_says_where_you_are_and_finds_anything():
    """Spec 5: the top bar sits inside the sheet with crumbs on the left
    (section, chevron, page) and search on the right (a 32 well, 232 wide, the
    shortcut in a key cap). On a phone or tablet it is the ink frame: the
    menu, the section, search; the sheet rises under it with 12 corners."""
    ok('<div class="crumbs"><span id="view-crumb"></span><span class="crumb-chev" id="crumb-chev" aria-hidden="true"></span><h1 id="view-title">Overview</h1></div>' in HTML,
       "the crumbs are the section, a chevron and the page")
    ok("topbar-sep" not in HTML, "the hairline after the trigger is gone")
    ok("function setViewCrumb(v) {" in SCRIPT, "the section is read from the sidebar's own groups")
    sv = SCRIPT.split("function setView(v) {")[1][:1600]
    ok("setViewCrumb(v);" in sv and "document.body.dataset.view = v;" in sv, "and set with the page on every move")
    ok("$('view-title').append(" not in SCRIPT, "the crumbs carry no Beta: the page title does")
    bar = CSS.split("\n        .topbar {")[1].split("}")[0]
    ok("border-bottom" not in bar and "padding: 0 var(--wrap-pad)" in bar, "no rule under the bar, on the page's gutter")
    find = CSS.split("\n        .topbar-search {")[1].split("}")[0]
    for prop in ("height: var(--control-h)", "width: var(--find-w)", "background: var(--surface-tertiary)",
                 "border-radius: var(--radius-control)"):
        ok(prop in find, "search: " + prop)
    eq(_token_raw("find-w"), "232px", "--find-w")
    kbd = CSS.split("\n        .topbar-search kbd {")[1].split("}")[0]
    ok("height: var(--tag-h)" in kbd and "font-size: var(--text-micro)" in kbd and "box-shadow: var(--ring-default)" in kbd,
       "the shortcut is a 20 key cap in micro type")
    phone = CSS.split("@media screen and (max-width: 900px) {")
    ok(len(phone) > 1 and ".view.active { background: var(--surface-primary); border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;" in phone[1],
       "on a phone the sheet rises under an ink bar")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_the_top_bar_says python3 tests/test_frontend.py`
Expected: `FAIL  t_the_top_bar_says_where_you_are_and_finds_anything: the crumbs are the section, a chevron and the page`

- [ ] **Step 3: The token**

In `:root` replace:

```
            --sidebar-w: 236px; --topbar-h: 48px; --frame-inset: var(--sp-2);   /* the sheet sits 8 inside the ink frame */
```

with:

```
            --sidebar-w: 236px; --topbar-h: 48px; --frame-inset: var(--sp-2);   /* the sheet sits 8 inside the ink frame */
            --find-w: 232px;        /* the top bar's search */
```

- [ ] **Step 4: The markup**

Replace:

```html
            <div class="topbar">
                <!-- The reference's header: a sidebar trigger, a hairline, then the
                     page; on the right the search and the page's own button. -->
                <button class="icon-btn menu-btn" id="menu-btn" title="Toggle sidebar" aria-label="Toggle sidebar" aria-keyshortcuts="Meta+B" aria-controls="sidebar" aria-expanded="true"></button>
                <span class="topbar-sep" aria-hidden="true"></span>
                <h1 id="view-title">Overview</h1>
                <div class="spacer"></div>
```

with:

```html
            <div class="topbar">
                <!-- The mix: where you are (the section, then the page) on the left,
                     search on the right. The menu button opens the phone's drawer,
                     and on a desk brings back a sidebar folded away. -->
                <button class="icon-btn menu-btn" id="menu-btn" title="Toggle sidebar" aria-label="Toggle sidebar" aria-keyshortcuts="Meta+B" aria-controls="sidebar" aria-expanded="true"></button>
                <div class="crumbs"><span id="view-crumb"></span><span class="crumb-chev" id="crumb-chev" aria-hidden="true"></span><h1 id="view-title">Overview</h1></div>
```

- [ ] **Step 5: The rules**

Replace:

```css
        .topbar { height: var(--topbar-h); flex-shrink: 0; border-bottom: var(--bw-hairline) solid var(--border-default); background: var(--surface-primary);
            display: flex; align-items: center; gap: var(--sp-2); padding: 0 var(--wrap-pad); position: relative; z-index: 5; }
```

with:

```css
        .topbar { height: var(--topbar-h); flex-shrink: 0; background: var(--surface-primary);
            display: flex; align-items: center; gap: var(--control-gap); padding: 0 var(--wrap-pad); position: relative; z-index: 5; }
        /* Where you are: the section in ink-3, a 14 chevron, the page in ink. */
        .crumbs { flex: 1; min-width: 0; display: flex; align-items: center; gap: var(--sp-1); color: var(--text-tertiary);
            font-size: var(--text-body); line-height: var(--lh-control); }
        .crumb-chev { display: grid; place-items: center; flex: none; }
        .crumb-chev svg { width: var(--icon-sm); height: var(--icon-sm); stroke-width: var(--icon-stroke-s); }
```

Replace:

```css
        .topbar h1 { font-size: var(--text-sm); font-weight: var(--weight-medium); margin: 0; letter-spacing: normal;
            min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .topbar .spacer { flex: 1; }
```

with:

```css
        .topbar h1 { font-size: var(--text-body); line-height: var(--lh-control); font-weight: var(--weight-medium); color: var(--text-primary); margin: 0; letter-spacing: normal;
            min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
```

Replace:

```css
        .topbar .menu-btn { margin-left: calc(-1 * var(--sp-1-5)); }
        .topbar.search-last .topbar-search { margin-right: calc(-1 * var(--sp-1)); }
        /* The hairline between the trigger and the page, as the reference draws it. */
        .topbar-sep { width: var(--bw-hairline); height: var(--sp-4); background: var(--border-default); margin: 0 var(--sp-2); flex: none; }
        /* The reference's search trigger: muted text, a glyph, and the shortcut
           in a small key cap. It opens a list of every page you can go to. */
        .topbar-search { display: inline-flex; align-items: center; gap: var(--sp-1-5); height: var(--control-h); padding: 0 var(--sp-1);
            border: 0; border-radius: var(--radius-row); background: none; color: var(--text-tertiary); font: inherit; font-size: var(--text-sm);
            cursor: pointer; transition: color var(--dur) var(--ease), background var(--dur) var(--ease); }
        .topbar-search:hover { color: var(--text-primary); }
        .topbar-search:active { background: var(--surface-tertiary); }
        .topbar-search svg { width: var(--icon-md); height: var(--icon-md); }
        .topbar-search kbd { display: inline-flex; align-items: center; height: 20px; padding: 0 var(--sp-1-5);
            border: var(--bw-hairline) solid var(--border-default); border-radius: var(--radius-tag); background: var(--surface-tertiary);
            font-family: inherit; font-size: var(--text-xs); font-weight: var(--weight-medium); color: var(--text-tertiary); }
```

with:

```css
        .topbar .menu-btn { margin-left: calc(-1 * var(--sp-1)); }
        /* Search: a 32 well 232 wide, the glyph 8 from its word, the shortcut
           in a key cap. It opens a list of every page you can go to. */
        .topbar-search { display: inline-flex; align-items: center; gap: var(--control-gap); height: var(--control-h); width: var(--find-w); flex: none;
            padding: 0 var(--sp-2) 0 var(--sp-3); border: 0; border-radius: var(--radius-control); background: var(--surface-tertiary);
            color: var(--text-tertiary); font: inherit; font-size: var(--text-body); line-height: var(--lh-control); text-align: start;
            cursor: pointer; transition: color var(--dur) var(--ease), background var(--dur) var(--ease); }
        .topbar-search:hover { background: var(--surface-sunken); }
        .topbar-search:active { background: var(--press-fill); }
        .topbar-search svg { width: var(--icon-md); height: var(--icon-md); }
        .topbar-search .ts-label { flex: 1; }
        .topbar-search kbd { display: inline-grid; place-items: center; height: var(--tag-h); min-width: var(--tag-h); padding: 0 var(--sp-1);
            border: 0; border-radius: var(--radius-tag); background: var(--surface-primary); box-shadow: var(--ring-default);
            font-family: inherit; font-size: var(--text-micro); line-height: var(--lh-caption); font-weight: var(--weight-medium); color: var(--text-tertiary); }
```

- [ ] **Step 6: The phone's ink bar and rising sheet**

Directly after the drawer block that ends `            .backdrop.show { display: block; position: fixed; inset: 0; background: var(--overlay-scrim); z-index: 20; }` and its closing `        }`, add:

```css
        /* With the sidebar a drawer (900 and under) the frame is the ink top
           bar: the menu, the section, search. The sheet rises under it with its
           12 corners, edge to edge. Chat has no page header, so its bar keeps
           the page's own name. */
        @media screen and (max-width: 900px) {
            .main { margin: 0; border-radius: 0; background: transparent; overflow: visible; }
            .view.active { background: var(--surface-primary); border-radius: var(--radius-sheet) var(--radius-sheet) 0 0; overflow: hidden; }
            .topbar { background: transparent; padding: 0 var(--sp-1); }
            .crumbs { color: var(--nav-text); font-size: var(--text-sm); }
            .topbar h1 { color: var(--nav-text); font-size: var(--text-sm); }
            body:not([data-view="chat"]) :is(#crumb-chev, #view-title) { display: none; }
            body[data-view="chat"] :is(#view-crumb, #crumb-chev) { display: none; }
            .topbar :is(.icon-btn, .topbar-search) { color: var(--nav-text); background: transparent; }
            .topbar-search { width: var(--control-h); padding: 0; justify-content: center; }
            .topbar-search :is(.ts-label, kbd) { display: none; }
            .topbar :is(.icon-btn, .topbar-search):hover { background: var(--chrome-fill); color: var(--text-on-chrome); }
            .topbar :is(.icon-btn, .topbar-search):active { background: var(--chrome-press); }
        }
```

- [ ] **Step 7: The script**

After `        $('side-hide').innerHTML = I.panelLeft;` add:

```js
        $('crumb-chev').innerHTML = I.chev;
```

Replace `        function setViewTitle(text) { const h = $('view-title'); h.textContent = text; h.title = text; }` with:

```js
        function setViewTitle(text) { const h = $('view-title'); h.textContent = text; h.title = text; }
        /* The section a page sits in, as the sidebar groups it: the crumb
           before the page's name. */
        function setViewCrumb(v) {
            const n = $('nav-' + v), sect = n && n.closest('.nav-sect');
            const g = sect && document.querySelector('.nav-group[aria-controls="' + sect.id + '"]');
            $('view-crumb').textContent = g ? g.textContent.trim() : '';
        }
```

In `setView` replace:

```js
            setViewTitle(titles[v] || 'Chat');
            /* Beta rides the topbar title as well: it is the only label still
               on screen once the page is scrolled. */
            if (BETA_TABS.indexOf(v) >= 0) $('view-title').append(el('span', 'beta-tag', 'Beta'));
```

with:

```js
            setViewTitle(titles[v] || 'Chat');
            setViewCrumb(v);
            document.body.dataset.view = v;
```

and remove these lines (the search field's own edge sits on the gutter, so the nudge is gone):

```js
            /* With nothing after the search, its glyph (not its padding) ends on
               the page's text edge, as the menu button starts on it. */
            requestAnimationFrame(() => { const tb = document.querySelector('.topbar');
                if (tb) tb.classList.toggle('search-last', !act.childNodes.length && $('print-btn').style.display === 'none'); });
```

- [ ] **Step 8: Update the Beta and header guards**

In `t_the_beta_tabs_say_so_everywhere_they_are_named` replace:

```python
    ok("BETA_TABS.indexOf(v) >= 0" in SCRIPT, "and the topbar title does too")
```

with:

```python
    # Since the mix (2026-10-06) the top bar is crumbs, which say where you are
    # and nothing else; Beta sits beside the page title (Task 7's pageHead).
    ok("$('view-title').append(" not in SCRIPT, "the crumbs carry no Beta")
```

In `t_the_header_is_one_implementation_with_one_collapse_point` replace:

```python
    ok(HTML.count('class="topbar"') == 1 and CSS.count(".topbar {") == 1, "one header, one rule")
```

with:

```python
    # The mix (2026-10-06): the phone's ink bar restyles the bar inside its own
    # breakpoint, so the one base rule is the one at the stylesheet's indent.
    ok(HTML.count('class="topbar"') == 1 and CSS.count("\n        .topbar {") == 1, "one header, one base rule")
```

- [ ] **Step 9: Run the tests**

Run: `ONLY=t_the_top_bar_says python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `432 passed, 0 failed`.

- [ ] **Step 10: Look at it**

At 1440 the bar reads "Finance › Forecast" on the left and the search well on the right, with no rule under it. At 390 (`?fresh=6` in a 390 wide window) the bar is ink: menu, "Finance", a search glyph; the sheet below has rounded top corners. Chat at 390 shows "Chat" in the bar.

- [ ] **Step 11: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Shell: the top bar says where you are and finds anything; on a phone it is the ink frame over a rising sheet

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The page header: one builder

**Files:**
- Modify: `static/index.html:298-302` (the title-face list and its controls rule), `:619-756` (`.ov-wrap` padding, header rules, the phone header), `:1118-1119` (the widget grid's tab offsets), the script after `refreshBtn` (5455-5461), `:586` (the busy spin)
- Test: `tests/test_frontend.py` (`t_reactor_wears_projected_images_brand_from_one_place` 9339, `t_the_brand_pilot_review_findings_stay_fixed` 9403, `t_the_spacing_pass_holds` 9494, `t_a_header_keeps_its_tabs_at_16_in_the_grid` 7066, `t_focus_is_declared_once_per_kind` 5901, a new test)

**Interfaces:**
- Consumes: `freshLabel(at)` (5435), `heroAct(updated, ...buttons)` (5449), `refreshBtn(onClick, label)` (5455), `BETA_TABS` (29211), `--text-title`, `--lh-title`, `--tr-title`, `--live-dot`, `--ring-live`.
- Produces: `pageHead({ view, title, line, status, live, onRefresh, refreshLabel, actions })` returns `div.ov-hero` > `div.ph-text` (`h2` with a Beta word on the BETA_TABS pages, then one of: `div.ph-sub` holding `span.live-dot`, `span.ov-updated` and a `button.info` refresh; `div.ph-sub` holding the status words split by `span.dot-sep`; or `p` with the one line) and `div.ov-hero-act` (the actions; the widget grid puts Customise there). The `.info` look: a 24 ghost icon button that never grows its line (Task 12 gives it its popover).

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_a_page_header_is_one_builder():
    """Spec 5 and 4.4: a Bricolage title at 26/32 (24 on a phone) with Beta
    beside it where it applies; at most one short line or a status line under
    it (a live dot, the stamp and a 24 Refresh, or words split by a dot); the
    page's actions on the right. 12 from the top bar, 20 above the tabs, 32
    above the body. Bricolage is for the wordmark and page titles only."""
    ok("function pageHead(o) {" in SCRIPT, "the builder exists")
    fn = fn_src("function pageHead(o) {")
    for part in ("el('div', 'ov-hero')", "BETA_TABS.indexOf(o.view) >= 0", "el('span', 'live-dot')", "freshLabel(o.live)",
                 "r.className = 'info'", "el('span', 'dot-sep')", "el('p', null, o.line)", "heroAct('', ...(o.actions || []))"):
        ok(part in fn, "pageHead: " + part)
    h2 = CSS.split("\n        .ov-hero h2 {")[1].split("}")[0]
    for prop in ("font-size: var(--text-title)", "line-height: var(--lh-title)", "font-weight: var(--weight-semibold)",
                 "letter-spacing: var(--tr-title)"):
        ok(prop in h2, "the page title: " + prop)
    ok(":is(.brand-name, .ov-hero h2, .ds-type-page) {" in CSS, "Bricolage is for the wordmark and page titles only")
    sub = CSS.split("\n        .ph-sub {")[1].split("}")[0]
    ok("margin-top: var(--sp-1)" in sub and "color: var(--text-tertiary)" in sub, "the line sits 4 under the title in ink-3")
    dot = CSS.split("\n        .live-dot {")[1].split("}")[0]
    ok("background: var(--live-dot)" in dot and "box-shadow: var(--ring-live)" in dot, "the live dot wears its halo")
    info = CSS.split("\n        .info {")[1].split("}")[0]
    ok("width: var(--control-h-sm)" in info and "height: var(--control-h-sm)" in info, "Refresh is a 24 icon button in the line")
    ok(".ov-wrap > .ov-hero { margin-bottom: var(--sp-7); }" in CSS and ".ov-hero:has(+ .tabs) { margin-bottom: var(--sp-5); }" in CSS,
       "32 above the body, 20 above the tabs")
    ok(re.search(r"\.ov-wrap \{[^}]*padding: var\(--sp-3\) var\(--wrap-pad\) var\(--sp-9\)", CSS), "12 under the top bar")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_a_page_header_is_one python3 tests/test_frontend.py`
Expected: `FAIL  t_a_page_header_is_one_builder: the builder exists`

- [ ] **Step 3: Bricolage for the wordmark and page titles only**

Replace:

```css
        /* Every title is in the brand's heading face, and this is the one list
           of what counts as a title: a page's, a section's and a card's, a run
           gate's, an empty chat's, a window's, the sign-in card's, and the
           product's own name beside the wordmark. Body text,
           labels and every figure stay in the interface face. */
        :is(.brand-name, .ov-hero h2, .ds-type-page, .section-title, .card-title, .chart-head .ct, .run-gate h2, .empty-chat h2, .modal-head h3, .auth-card h2) {
            font-family: var(--font-display); }
        /* A title's controls (a range, a switch and its label) stay in the
           interface face: the buttons inherit their font, so they took the title's. */
        :is(.section-title, .card-title, .ov-hero h2) :is(button, input, select, textarea, label, .segmented, .tabs) { font-family: var(--font-sans); }
```

with:

```css
        /* The brand's heading face sets two things only (the mix, 4.2): the
           wordmark and a page's title, and the Design section's sample of one.
           Section heads, windows, run gates and every figure are Inter. */
        :is(.brand-name, .ov-hero h2, .ds-type-page) {
            font-family: var(--font-display); }
        /* What sits beside a title (Beta, a control) stays in the interface face. */
        .ov-hero h2 :is(button, input, select, textarea, label, .segmented, .tabs, .beta-tag) { font-family: var(--font-sans); }
```

- [ ] **Step 4: The page's rhythm and the header rules**

Replace:

```css
            padding: var(--sp-6) var(--wrap-pad) var(--sp-8);
```

(inside the `.ov-wrap {` rule) with:

```css
            padding: var(--sp-3) var(--wrap-pad) var(--sp-9);
```

Replace `        .ov-wrap > .section-title { margin-bottom: var(--sp-3); }` with:

```css
        .ov-wrap > .section-title { margin-bottom: var(--sp-3); }
        /* The page header sits 32 above the body, or 20 above its tabs (below). */
        .ov-wrap > .ov-hero { margin-bottom: var(--sp-7); }
```

Replace `        .ov-hero { display: flex; align-items: flex-start; gap: var(--sp-4); margin-bottom: var(--sp-6); }` with:

```css
        .ov-hero { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--sp-6); margin-bottom: var(--sp-7); }
```

Replace each of these three lines:

```css
        .ov-hero:has(+ .page-tabs) { margin-bottom: var(--sp-4); }
        .ov-hero:has(+ .tabs) { margin-bottom: var(--sp-4); }
        .ov-hero:has(+ .seg-row) { margin-bottom: var(--sp-4); }
```

with:

```css
        .ov-hero:has(+ .page-tabs) { margin-bottom: var(--sp-5); }
        .ov-hero:has(+ .tabs) { margin-bottom: var(--sp-5); }
        .ov-hero:has(+ .seg-row) { margin-bottom: var(--sp-5); }
```

Delete these two rules (the badge stays hidden by the `display: none` rule after them until every screen stops building it, Task 44):

```css
        .ov-hero .badge { width: var(--box-xl); height: var(--box-xl); border-radius: var(--radius-inset); background: var(--surface-tertiary); color: var(--text-secondary);
            display: grid; place-items: center; flex-shrink: 0; box-shadow: var(--ring-line); }
        .ov-hero .badge svg { width: var(--icon-lg); height: var(--icon-lg); }
```

Replace:

```css
        .ov-hero h2 { font-size: var(--text-3xl); margin: 0 0 var(--sp-1); font-weight: var(--weight-regular);
            letter-spacing: -.025em; line-height: var(--lh-tight); }
        .ov-hero p { margin: 0; color: var(--text-tertiary); font-size: var(--text-sm); line-height: var(--lh-control); max-width: var(--measure); }
```

with:

```css
        /* The title: Bricolage 600 at 26/32, tracked -0.02em; Beta follows on
           its baseline, 8 apart. One short line sits 4 under it. */
        .ov-hero h2 { font-size: var(--text-title); line-height: var(--lh-title); font-weight: var(--weight-semibold); letter-spacing: var(--tr-title); margin: 0;
            display: flex; align-items: baseline; gap: var(--sp-2); white-space: nowrap; }
        .ov-hero p { margin: var(--sp-1) 0 0; color: var(--text-tertiary); font-size: var(--text-body); line-height: var(--lh-control); max-width: var(--measure); }
```

Replace `        .ov-hero-act { margin-left: auto; display: flex; align-items: center; gap: var(--sp-2); flex: none; padding-top: var(--sp-1); }` with:

```css
        .ov-hero-act { margin-left: auto; display: flex; align-items: center; gap: var(--control-gap); flex: none; padding-top: 0; }
```

Directly after `        .ov-hero-act .ov-updated { margin-left: 0; padding-top: 0; }` add:

```css
        /* The status line: words split by a 4 dot, or a live dot with its halo,
           the stamp and a 24 Refresh. */
        .ph-sub { margin-top: var(--sp-1); display: flex; align-items: center; gap: var(--sp-2); color: var(--text-tertiary);
            font-size: var(--text-body); line-height: var(--lh-control); white-space: nowrap; }
        .ph-sub .ov-updated { font-size: inherit; margin: 0; padding: 0; color: inherit; }
        .live-dot { width: var(--dot-md); height: var(--dot-md); margin-left: var(--sp-0-5); border-radius: var(--radius-circle);
            background: var(--live-dot); box-shadow: var(--ring-live); flex: none; }
        .dot-sep { width: var(--sp-1); height: var(--sp-1); border-radius: var(--radius-circle); background: var(--border-emphasis); flex: none; }
        /* A 24 icon button inside a line of text: Refresh here, the info button
           beside a heading (Task 12). It never grows its line: its fill and its
           focus ring are drawn on ::before, so a phone grows the target without
           growing what you see. Pulled 4 toward its words, as a count is. */
        .info { position: relative; isolation: isolate; width: var(--control-h-sm); height: var(--control-h-sm);
            margin-block: calc((var(--lh-control) - var(--control-h-sm)) / 2); margin-left: calc((var(--icon-md) - var(--control-h-sm)) / 2);
            padding: 0; border: 0; background: none; display: inline-grid; place-items: center; color: var(--text-tertiary); flex: none; cursor: pointer; }
        .info::before { content: ""; position: absolute; z-index: -1; inset: 0; border-radius: var(--radius-tag); }
        .info svg { width: var(--icon-md); height: var(--icon-md); }
        .info:hover, .info[aria-expanded="true"] { color: var(--text-primary); }
        .info:hover::before, .info[aria-expanded="true"]::before { background: var(--surface-tertiary); }
        .info:active::before { background: var(--press); }
        .info:focus-visible { outline: 0; }
        .info:focus-visible::before { outline: var(--focus-outline); outline-offset: calc(-1 * var(--bw-strong)); }
```

In the phone block (`@media (max-width: 640px) {` that begins `            /* 32px gutters spend 64px of a 390px screen on nothing. */`) replace:

```css
            .ov-wrap { padding: var(--sp-4) var(--sp-4) calc(var(--sp-8) + var(--sp-4)); --page-rhythm: var(--sp-4); }
            .ov-hero { flex-wrap: wrap; gap: var(--sp-3); }
```

with:

```css
            .ov-wrap { padding: var(--sp-5) var(--sp-4) var(--sp-7); --page-rhythm: var(--sp-4); }
            .ov-hero { flex-wrap: wrap; gap: var(--sp-4); }
            .ov-hero h2 { font-size: var(--text-2xl); }
            /* The actions take a row of their own under the title, sharing it. */
            .ov-hero-act > .btn:not(.btn-icon) { flex: 1 1 auto; }
```

Replace `        :is(.btn, .icon-btn)[aria-busy="true"] svg { animation: navspin 1s linear infinite; }` with:

```css
        :is(.btn, .icon-btn, .info)[aria-busy="true"] svg { animation: navspin 1s linear infinite; }
```

and `        :is(.btn, .icon-btn, .send)[aria-busy="true"] { pointer-events: none; }` with:

```css
        :is(.btn, .icon-btn, .send, .info)[aria-busy="true"] { pointer-events: none; }
```

- [ ] **Step 5: The widget grid keeps 20 above the tabs**

Replace:

```css
        .ov-wrap.wgrid > .ov-hero + .page-tabs { margin-top: calc(var(--sp-4) - var(--page-rhythm)); }
        .ov-wrap.wgrid > .ov-hero + .tabs { margin-top: calc(var(--sp-4) - var(--page-rhythm)); }
```

with:

```css
        .ov-wrap.wgrid > .ov-hero + .page-tabs { margin-top: calc(var(--sp-5) - var(--page-rhythm)); }
        .ov-wrap.wgrid > .ov-hero + .tabs { margin-top: calc(var(--sp-5) - var(--page-rhythm)); }
```

- [ ] **Step 6: The builder**

Directly after the `refreshBtn` function (it ends `            return b;\n        }` before `        // static icon wiring`) add:

```js
        /* The page header (the mix, spec 5): a Bricolage title, Beta beside it
           on the pages BETA_TABS names, at most one short line under it or a
           status line, and the page's actions on the right.
           o: { view, title, line, status: [words, ...], live: a time in ms,
           onRefresh, refreshLabel, actions: [nodes] }. The names .ov-hero and
           .ov-hero-act stay: the widget grid puts Customise in the rail by
           them, and a printed report hides the rail by them. */
        function pageHead(o) {
            const hero = el('div', 'ov-hero');
            const text = el('div', 'ph-text');
            const h = el('h2', null, o.title);
            if (o.view && BETA_TABS.indexOf(o.view) >= 0) h.append(el('span', 'beta-tag', 'Beta'));
            text.append(h);
            if (o.live != null) {
                const sub = el('div', 'ph-sub');
                const dot = el('span', 'live-dot'); dot.setAttribute('aria-hidden', 'true');
                sub.append(dot, el('span', 'ov-updated', freshLabel(o.live)));
                if (o.onRefresh) { const r = refreshBtn(o.onRefresh, o.refreshLabel); r.className = 'info'; sub.append(r); }
                text.append(sub);
            } else if (o.status && o.status.length) {
                const sub = el('div', 'ph-sub');
                o.status.forEach((t, i) => {
                    if (i) { const s = el('span', 'dot-sep'); s.setAttribute('aria-hidden', 'true'); sub.append(s); }
                    sub.append(el('span', null, t));
                });
                text.append(sub);
            } else if (o.line) text.append(el('p', null, o.line));
            hero.append(text, heroAct('', ...(o.actions || [])));
            return hero;
        }
```

- [ ] **Step 7: Update the guards that pinned the old header**

In `t_reactor_wears_projected_images_brand_from_one_place` replace:

```python
    ok(":is(.brand-name, .ov-hero h2, .ds-type-page, .section-title, .card-title, .chart-head .ct, .run-gate h2, .empty-chat h2, .modal-head h3, .auth-card h2) {"
       in CSS and "font-family: var(--font-display)" in CSS.split(".auth-card h2) {")[1][:80], "and every title is in it, chart titles too, from one list")
```

with:

```python
    ok(":is(.brand-name, .ov-hero h2, .ds-type-page) {" in CSS
       and "font-family: var(--font-display)" in CSS.split(".ds-type-page) {")[1][:80],
       "Bricolage sets the wordmark and the page titles, from one list, and nothing else (the mix, 4.2)")
```

In `t_the_brand_pilot_review_findings_stay_fixed` replace:

```python
    ok(":is(.section-title, .card-title, .ov-hero h2) :is(button, input, select, textarea, label, .segmented, .tabs) { font-family: var(--font-sans); }" in CSS,
       "a range or switch in a section title is not set in the title face")
```

with:

```python
    ok(".ov-hero h2 :is(button, input, select, textarea, label, .segmented, .tabs, .beta-tag) { font-family: var(--font-sans); }" in CSS,
       "Beta or a control beside a page title is not set in the title face")
```

In `t_the_spacing_pass_holds` replace:

```python
    ok(".ov-hero:has(+ .tabs) { margin-bottom: var(--sp-4); }" in CSS, "a tab strip sits 16 under its header on every screen")
```

with:

```python
    ok(".ov-hero:has(+ .tabs) { margin-bottom: var(--sp-5); }" in CSS, "a tab strip sits 20 under its header on every screen")
```

In `t_focus_is_declared_once_per_kind` replace:

```python
    ok(CSS.count("outline: var(--focus-outline)") == 4,
       "the outline is read by the control rule and by three deliberate variants (the "
       "custom-drawn checkbox, the menu item which insets it, and a widget card just dropped "
       "in Customize mode, which borrows it for --dur-landed), and nowhere else")
```

with:

```python
    ok(CSS.count("outline: var(--focus-outline)") == 5,
       "the outline is read by the control rule and by four deliberate variants (the "
       "custom-drawn checkbox, the menu item which insets it, a widget card just dropped "
       "in Customize mode, which borrows it for --dur-landed, and the info button, which "
       "draws it on its 24 face so a phone's 40 target never shows), and nowhere else")
```

Replace the body of `t_a_header_keeps_its_tabs_at_16_in_the_grid` (both `ok` calls) with:

```python
    ok(".ov-hero:has(+ .page-tabs) { margin-bottom: var(--sp-5); }" in CSS, "the flow's rule: 20 above the tabs (the mix, 4.4)")
    ok(".ov-wrap.wgrid > .ov-hero + .page-tabs { margin-top: calc(var(--sp-5) - var(--page-rhythm)); }" in CSS,
       "and the grid's reads the same two tokens")
```

- [ ] **Step 8: Run the tests**

Run: `ONLY=t_a_page_header_is_one python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `433 passed, 0 failed`.

- [ ] **Step 9: Look at it**

Every page title is now Bricolage 600 at 26; intros (still there until each screen's task) sit 4 under in ink-3; section and card titles are Inter. Nothing overlaps at 1440 or 390.

- [ ] **Step 10: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Shell: one page header builder, a Bricolage title at 26 with Beta beside it, one line or a live status under it

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Phase 3: The shared parts

Each part's base rule is rewritten in place (Global Constraints, Cascade), so every screen that uses it changes at once. The screens' own structure and words come in Phases 4 and 5.

### Task 8: Buttons

**Files:**
- Modify: `static/index.html:546-561` (`.btn`), `:572-577` (`.btn-primary`), `:449-456` (`.icon-btn`), `:729` (`.btn-sm.btn-icon`), `:1414` (`.btn` on), `:1862` (`.btn.ghost`), `:1808` (`.chip`), `:3048-3065` (the Inbox bulk bar, its buttons and its Assign select), `:1553` (`.act-row > .setup-code`), `:3864-3865` (`.btn-sm`), `:3901-3902` (`.tbl-step`)
- Test: `tests/test_frontend.py` (`t_every_control_is_the_same_height_as_every_other` 3544, `t_the_table_toolbar_and_pager_match_the_reference` 2852, `t_icon_only_buttons_clear_the_minimum` 1190, a new test)

**Interfaces:**
- Consumes: `--border-strong` (line-ctl), `--shadow-control`, `--press`, `--control-gap`, `--text-body` (Tasks 2 to 4).
- Produces: one 32 button in five kinds: `btn`, `btn btn-primary`, `btn ghost`, `btn btn-sm btn-icon` (a 32 square), `icon-btn` (a 32 ghost square; 28 in the sidebar, Task 5). `btn-sm` is kept as a class name and is now the same 32 button, so its 138 call sites need no change.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_a_button_is_the_mix_button():
    """Spec 6: a button is 32 tall with a 6 corner, a line-ctl hairline and a
    1px lift, 13/20 at 500, a 16 icon 8 from its word. Primary is the teal fill
    with ink words. There is no 28 text button any more: btn-sm is the same 32,
    so every control in a row lines up. Pressed is one step darker than hover
    and nothing jumps; an open menu's button keeps the fill."""
    b = CSS.split("\n        .btn {")[1].split("}")[0]
    for prop in ("min-height: var(--control-h)", "padding: 0 var(--sp-3)", "border-radius: var(--radius-control)",
                 "font-size: var(--text-body)", "font-weight: var(--weight-medium)", "gap: var(--control-gap)",
                 "box-shadow: var(--shadow-control)", "solid var(--border-strong)"):
        ok(prop in b, ".btn: " + prop)
    act = CSS.split("\n        .btn:active {")[1].split("}")[0]
    ok("background: var(--press)" in act and "translateY" not in act, "pressed is one step darker and does not move")
    sm = CSS.split(".btn-sm {")[1].split("}")[0]
    ok("min-height: var(--control-h)" in sm and "padding: 0 var(--sp-3)" in sm and "font-size: var(--text-body)" in sm,
       "btn-sm is the same 32 button")
    ok(".btn-sm.btn-icon { width: var(--control-h);" in CSS, "an icon button is a 32 square")
    ok(re.search(r"\.icon-btn \{[^}]*min-width: var\(--control-h\); min-height: var\(--control-h\)", CSS),
       "and so is a ghost icon button")
    p = CSS.split(".btn-primary {")[1].split("}")[0]
    ok("background: var(--action-primary)" in p and "color: var(--text-on-action)" in p, "primary is teal with ink words")
    ok('.btn[aria-expanded="true"] { background: var(--surface-tertiary); }' in CSS, "an open menu's button keeps the fill")
    ok(".btn:not(.btn-sm):has(> .ic:first-child)" not in CSS, "an icon does not pull a button's edge in")
    ghost = CSS.split("\n        .btn.ghost {")[1].split("}")[0]
    ok("border-color: transparent" in ghost and "box-shadow: none" in ghost, "a ghost button has no edge and no lift")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_a_button_is_the_mix python3 tests/test_frontend.py`
Expected: `FAIL  t_a_button_is_the_mix_button: .btn: padding: 0 var(--sp-3)`

- [ ] **Step 3: The button**

Replace:

```css
        .btn { border: var(--bw-hairline) solid var(--border-default); background: var(--surface-primary); color: var(--text-primary); border-radius: var(--radius-control);
            /* 5px, not 6: the 1px border counts toward the box, and 6+20+6+2
               made every button 34 where the reference's is 32. */
            padding: var(--control-pad-y) var(--sp-2-5); font-size: var(--text-sm); font-weight: var(--weight-medium); line-height: var(--lh-control); white-space: nowrap;
            display: inline-flex; align-items: center; justify-content: center; gap: var(--control-gap);
            transition: background var(--dur) var(--ease), border-color var(--dur) var(--ease), color var(--dur) var(--ease); min-height: var(--control-h); }
        /* An icon that leads a label sits 8px in, as the source's inline-start icon does. */
        .btn:not(.btn-sm):has(> .ic:first-child) { padding-left: var(--sp-2); }
        .btn svg { width: var(--icon-md); height: var(--icon-md); }
        .btn:hover { background: var(--surface-tertiary); }
        .btn:active { background: var(--surface-sunken); transform: translateY(var(--sp-px)); }
```

with:

```css
        /* THE BUTTON (the mix, spec 6): 32 tall, 12 in, a 6 corner, a line-ctl
           hairline and a 1px lift; 13/20 at 500; a 16 icon in ink-2, 8 from its
           word. The label is centred in the 32 by the flexbox, so a label that
           wraps grows the button rather than spilling out of it. */
        .btn { border: var(--bw-hairline) solid var(--border-strong); background: var(--surface-primary); color: var(--text-primary); border-radius: var(--radius-control);
            padding: 0 var(--sp-3); font-size: var(--text-body); font-weight: var(--weight-medium); line-height: var(--lh-control); white-space: nowrap;
            display: inline-flex; align-items: center; justify-content: center; gap: var(--control-gap); box-shadow: var(--shadow-control);
            transition: background var(--dur) var(--ease), border-color var(--dur) var(--ease), color var(--dur) var(--ease); min-height: var(--control-h); }
        .btn svg { width: var(--icon-md); height: var(--icon-md); }
        .btn .ic { color: var(--text-secondary); }
        .btn:hover { background: var(--surface-tertiary); }
        .btn:active { background: var(--press); }
        .btn[aria-expanded="true"] { background: var(--surface-tertiary); }
```

- [ ] **Step 4: Primary, the small alias, the icon squares**

Replace `        .btn-primary { background: var(--action-primary); border-color: var(--border-selected); color: var(--text-on-action); }` with:

```css
        .btn-primary { background: var(--action-primary); border-color: var(--border-selected); color: var(--text-on-action); }
        .btn-primary .ic { color: var(--text-on-action); }
```

Replace `        .btn-sm.btn-icon { width: var(--control-h-md); padding: 0; justify-content: center; }` with:

```css
        .btn-sm.btn-icon { width: var(--control-h); padding: 0; justify-content: center; }
```

Replace:

```css
        .btn-sm { min-height: var(--control-h-md); padding: 0 var(--sp-2-5); font-size: var(--text-sm); gap: var(--control-gap); border-radius: var(--radius-control); }
        .btn-sm svg { width: var(--icon-sm); height: var(--icon-sm); }
```

with:

```css
        /* The mix has no 28 text button: btn-sm is the same 32 button, kept as
           a name so its call sites need no change. */
        .btn-sm { min-height: var(--control-h); padding: 0 var(--sp-3); font-size: var(--text-body); gap: var(--control-gap); border-radius: var(--radius-control); }
        .btn-sm svg { width: var(--icon-md); height: var(--icon-md); }
```

In the `.icon-btn` rule (it begins `        .icon-btn { border: 0; background: transparent; color: var(--text-tertiary);`) replace `min-width: var(--control-h-md); min-height: var(--control-h-md);` with `min-width: var(--control-h); min-height: var(--control-h);`.

Replace `        .tbl-step { width: var(--control-h-md); height: var(--control-h-md); min-height: var(--control-h-md); padding: 0; border-radius: var(--radius-control); }` with:

```css
        .tbl-step { width: var(--control-h); height: var(--control-h); min-height: var(--control-h); padding: 0; border-radius: var(--radius-control); }
```

- [ ] **Step 5: The toggled button, the ghost, the chip, the stragglers**

Replace `        .btn:is(.on, [aria-pressed="true"]) { background: var(--action-selected); border-color: var(--border-selected); color: var(--text-brand); font-weight: var(--weight-medium); }` with:

```css
        /* A button that is on (a filter that is set) wears the chosen recipe:
           the teal wash and edge, with ink words. */
        .btn:is(.on, [aria-pressed="true"]) { background: var(--action-selected); border-color: var(--border-selected); color: var(--text-primary); font-weight: var(--weight-medium); }
```

Replace `        .btn.ghost { background: transparent; }` with:

```css
        .btn.ghost { background: transparent; border-color: transparent; box-shadow: none; }
        .btn.ghost .ic { color: var(--text-tertiary); }
```

In the `.chip` rule replace `min-height: var(--control-h-md); padding-block: var(--sp-1); text-align: start; }` with `min-height: var(--control-h); padding-block: var(--sp-1); text-align: start; }` and, in the same rule, `padding: 0 var(--sp-2-5); font-size: var(--text-sm);` with `padding: 0 var(--sp-3); font-size: var(--text-body);`.

Replace `        .mail-bulkbar .btn { min-height: var(--control-h-md); padding: 0 var(--sp-2-5); font-size: var(--text-xs); }` with:

```css
        .mail-bulkbar .btn { min-height: var(--control-h); padding: 0 var(--sp-3); font-size: var(--text-body); }
```

The Inbox bulk bar must measure the same idle and armed (ticking a row must not move the list), and it was sized round a 28 button. Replace:

```css
        /* Idle and armed have to measure the same, or ticking one row drops the
           whole list and the row you just ticked slides out from under the
           pointer. 44 is the armed height: a 28px button, 7px of padding each
           side and the two borders. The buttons take .btn-sm, the scale the
           card's own header and the row controls use, not the 32px default. */
        .mail-bulkbar { display: flex; align-items: center; gap: var(--sp-2); flex-wrap: wrap;
            min-height: 44px;
            padding: var(--sp-2) var(--sp-3); margin-bottom: var(--sp-2); border: var(--bw-hairline) solid var(--border-default);
```

with:

```css
        /* Idle and armed have to measure the same, or ticking one row drops the
           whole list and the row you just ticked slides out from under the
           pointer. 44 (a row) is the armed height: a 32 button, 4 of padding
           each side and the two borders, with room to spare. */
        .mail-bulkbar { display: flex; align-items: center; gap: var(--sp-2); flex-wrap: wrap;
            min-height: var(--row-h);
            padding: var(--sp-1) var(--sp-3); margin-bottom: var(--sp-2); border: var(--bw-hairline) solid var(--border-default);
```

and replace:

```css
        /* The 44 above only holds if everything in the bar is 28. The Assign
           select is built from the base 32px class, so the armed bar came out
           48 and ticking the first row dropped the list 4px - the row under
           the pointer moved as it was clicked. Only a lead sees this select,
           which is why the bar measured 44 idle and 44 armed for everyone
           else. Same 28 / --radius-sm / --border-default / 500 as the buttons beside it. */
        .mail-bulkbar .mail-presence-pick { height: var(--control-h-md); min-height: var(--control-h-md); box-sizing: border-box;
```

with:

```css
        /* The 44 above only holds if everything in the bar is one height: the
           Assign select (only a lead sees it) is the 32 of the buttons beside
           it, with their edge and weight. */
        .mail-bulkbar .mail-presence-pick { height: var(--control-h); min-height: var(--control-h); box-sizing: border-box;
```

Replace `        .act-row > .setup-code { display: inline-flex; align-items: center; min-height: var(--control-h-md); padding-inline: var(--sp-2-5); }` with:

```css
        .act-row > .setup-code { display: inline-flex; align-items: center; min-height: var(--control-h); padding-inline: var(--sp-3); }
```

- [ ] **Step 6: Update the guards that pinned the 28 button**

In `t_every_control_is_the_same_height_as_every_other` replace:

```python
    sm = CSS.split(".btn-sm {")[1].split("}")[0]
    ok("min-height: var(--control-h-md)" in sm and re.search(r"--control-h-md:\s*28px", CSS), "the small button stays 28")
```

with:

```python
    sm = CSS.split(".btn-sm {")[1].split("}")[0]
    ok("min-height: var(--control-h)" in sm, "and the small button is the same 32: the mix has no 28 text button")
```

In `t_the_table_toolbar_and_pager_match_the_reference` replace:

```python
    btn = CSS.split(".btn-sm {")[1].split("}")[0]
    ok("min-height: var(--control-h-md)" in btn and "padding: 0 var(--sp-2-5)" in btn, "small buttons are 28px tall")
    step = CSS.split(".tbl-step {")[1].split("}")[0]
    ok("width: var(--control-h-md)" in step and "height: var(--control-h-md)" in step, "pager steps are the table's 28 square")
```

with:

```python
    btn = CSS.split(".btn-sm {")[1].split("}")[0]
    ok("min-height: var(--control-h)" in btn and "padding: 0 var(--sp-3)" in btn, "toolbar buttons are the one 32 button")
    step = CSS.split(".tbl-step {")[1].split("}")[0]
    ok("width: var(--control-h)" in step and "height: var(--control-h)" in step, "pager steps are 32 squares")
```

In `t_icon_only_buttons_clear_the_minimum` replace:

```python
    ok("min-width: var(--control-h-md)" in rule and "min-height: var(--control-h-md)" in rule,
       "icon buttons carry an explicit floor rather than inheriting one from their glyph")
```

with:

```python
    ok("min-width: var(--control-h)" in rule and "min-height: var(--control-h)" in rule,
       "icon buttons carry an explicit 32 floor rather than inheriting one from their glyph")
```

- [ ] **Step 7: Run the tests**

Run: `ONLY=t_a_button_is_the_mix python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `434 passed, 0 failed`.

- [ ] **Step 8: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Parts: one 32 button with a line-ctl edge and a 1px lift, no 28 text button, pressed one step darker

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Fields and search

**Files:**
- Modify: `static/index.html` `:root` tier 3 (`--search-w`, `--chevron-room`), `:1694-1721` (the field recipe, its focus and invalid rules, the select chevron), `:3809-3845` (`.tbl-search`), `:3853-3854` (`.tbl-tools select`), `:3882-3883` (`.field-sm`), `:3894-3896` (`.tbl-rows select`), `:3963-3964` (`.dpanel` fields), the script's `tableSearch` (7293)
- Test: `tests/test_frontend.py` (`t_focus_is_declared_once_per_kind` 5901, `t_the_table_toolbar_and_pager_match_the_reference` 2852, a new test)

**Interfaces:**
- Consumes: `--focus-ring` (Task 3), `--border-strong`, `--shadow-control`.
- Produces: every field 32 tall (40 on a phone, Task 24) at 13/20 with a line-ctl hairline, a lift and the 2px teal ring 2 off its edge on focus. `.tbl-search` is the search field: one 32 well of `--search-w` (280) holding the 16 glyph, the input and its clear button, ringed as a whole on focus.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_a_field_is_the_mix_field():
    """Spec 6: real inputs, 32 tall, 13/20, a line-ctl hairline, the focus ring
    on the field (a 2px teal-line ring 2 off its edge, not a glow). A search is
    one 280 field with its glyph in flow, ringed as a whole while its input has
    focus; a select's chevron is a 16 glyph 12 from the edge in ink-3."""
    f = CSS.split("input[type=email], input[type=password], input[type=url], input[type=tel], input:not([type]), textarea, select {")[1].split("}")[0]
    for prop in ("solid var(--border-strong)", "font-size: var(--text-body)", "padding: var(--control-pad-y) var(--sp-3)",
                 "min-height: var(--control-h)", "box-shadow: var(--shadow-control)"):
        ok(prop in f, "field: " + prop)
    ok(':is(input, textarea, select, [contenteditable="true"]):focus { outline: none; box-shadow: var(--focus-ring); }' in CSS,
       "a field's focus is the one ring, and its edge does not change colour under it")
    s = CSS.split("\n        .tbl-search {")[1].split("}")[0]
    for prop in ("height: var(--control-h)", "width: var(--search-w)", "gap: var(--control-gap)", "padding: 0 var(--sp-3)",
                 "solid var(--border-strong)"):
        ok(prop in s, "search: " + prop)
    eq(_token_raw("search-w"), "280px", "--search-w")
    ok(".tbl-search:focus-within { box-shadow: var(--focus-ring); }" in CSS and ".tbl-search input:focus { box-shadow: none; }" in CSS,
       "the search is ringed as one field, not its input inside it")
    ok("position: absolute" not in CSS.split("\n        .tbl-search .ic {")[1].split("}")[0], "its glyph sits in flow")
    sel = CSS.split("\n        select { appearance: none;")[1].split("}")[0]
    ok("stroke='%235F6368'" in sel and "stroke-width='1.75'" in sel and "right var(--sp-3) center" in sel,
       "the chevron is a 16 glyph at 1.75 in ink-3, 12 from the edge")
    for rule in (".tbl-tools select {", "input.field-sm, select.field-sm {", ".tbl-rows select {", ".dpanel input, .dpanel select {"):
        ok("var(--control-h)" in CSS.split(rule)[1].split("}")[0] and "28px" not in CSS.split(rule)[1].split("}")[0]
           and "var(--control-h-md)" not in CSS.split(rule)[1].split("}")[0], rule + " is 32")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_a_field_is_the_mix python3 tests/test_frontend.py`
Expected: `FAIL  t_a_field_is_the_mix_field: field: solid var(--border-strong)`

- [ ] **Step 3: Tokens**

In `:root` replace `            --chevron-room: 30px;   /* right padding a select keeps clear for its chevron */` with:

```
            --chevron-room: calc(var(--sp-3) + var(--icon-md) + var(--sp-2));   /* a select's chevron: 12 in, 16 wide, 8 clear */
            --search-w: 280px;      /* a list's search field */
```

- [ ] **Step 4: The field recipe**

Replace:

```css
            background: var(--surface-primary); border: var(--bw-hairline) solid var(--border-default); border-radius: var(--radius-field);
            color: var(--text-primary); font: inherit; font-size: var(--text-sm); line-height: var(--lh-control); padding: var(--control-pad-y) var(--sp-2-5);
            /* 32px like every other control. At 36 an input beside a button did
               not even line up with it, let alone with the reference. */
            min-height: var(--control-h);
            transition: border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease); }
```

with:

```css
            background: var(--surface-primary); border: var(--bw-hairline) solid var(--border-strong); border-radius: var(--radius-field);
            color: var(--text-primary); font: inherit; font-size: var(--text-body); line-height: var(--lh-control); padding: var(--control-pad-y) var(--sp-3);
            /* 32px like every other control (the mix, spec 6), with a control's 1px lift. */
            min-height: var(--control-h); box-shadow: var(--shadow-control);
            transition: border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease); }
```

Replace `        :is(input, textarea, select, [contenteditable="true"]):focus { outline: none; border-color: var(--border-selected); box-shadow: var(--focus-ring); }` with:

```css
        :is(input, textarea, select, [contenteditable="true"]):focus { outline: none; box-shadow: var(--focus-ring); }
```

Replace `        :is(input, textarea, select, [contenteditable="true"])[aria-invalid="true"]:focus { border-color: var(--error); box-shadow: 0 0 0 3px var(--error-bg); }` with:

```css
        :is(input, textarea, select, [contenteditable="true"])[aria-invalid="true"]:focus { border-color: var(--error);
            box-shadow: 0 0 0 var(--bw-strong) var(--white), 0 0 0 calc(2 * var(--bw-strong)) var(--error); }
```

In the `select { appearance: none; ...` rule replace `width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%235F6368' stroke-width='2.2'` with `width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%235F6368' stroke-width='1.75'`, and replace `background-repeat: no-repeat; background-position: right 9px center; }` with `background-repeat: no-repeat; background-position: right var(--sp-3) center; }`.

- [ ] **Step 5: The search field**

Replace:

```css
        .tbl-search { position: relative; display: flex; min-width: 0; max-width: 100%; }
        /* The declared 28 has to beat the 32px min-height every field carries,
           or the search sits 4px proud of the 28px card actions above it. */
        .tbl-search input { height: var(--control-h-md); min-height: var(--control-h-md); width: 320px; max-width: 100%;
            padding: var(--sp-1) var(--sp-2-5) var(--sp-1) var(--sp-7); border-radius: var(--radius-field);
            font-size: var(--text-sm); line-height: var(--lh-control); }
```

with:

```css
        /* THE SEARCH FIELD (the mix, spec 6): one 32 well, 280 wide, its 16
           glyph 12 in and 8 from the words, the clear button at its end. The
           input fills the field and runs under its two hairlines, so the whole
           field is the target; the field is ringed as one while it has focus. */
        .tbl-search { position: relative; display: flex; align-items: center; gap: var(--control-gap); height: var(--control-h); width: var(--search-w);
            min-width: 0; max-width: 100%; padding: 0 var(--sp-3); border: var(--bw-hairline) solid var(--border-strong); border-radius: var(--radius-field);
            background: var(--surface-primary); box-shadow: var(--shadow-control); color: var(--text-tertiary); }
        .tbl-search input { flex: 1; min-width: 0; height: calc(100% + 2 * var(--bw-hairline)); min-height: 0; width: auto; max-width: none;
            padding: 0; border: 0; border-radius: 0; background: none; box-shadow: none;
            font-size: var(--text-body); line-height: var(--lh-control); }
        .tbl-search:focus-within { box-shadow: var(--focus-ring); }
        .tbl-search input:focus { box-shadow: none; }
```

Replace:

```css
        .tbl-search .ic { position: absolute; left: 10px; top: 50%; transform: translateY(-50%);
            color: var(--text-tertiary); pointer-events: none; }
```

with:

```css
        .tbl-search .ic { flex: none; color: var(--text-tertiary); pointer-events: none; }
```

Replace:

```css
        .tbl-search .tbl-clear { position: absolute; right: 4px; top: 50%; transform: translateY(-50%);
            width: var(--box-sm); height: var(--box-sm); min-height: 0; padding: 0; border: 0; background: none;
            border-radius: var(--radius-tag); color: var(--text-tertiary); display: grid; place-items: center; }
```

with:

```css
        .tbl-search .tbl-clear { flex: none; margin-right: calc(-1 * var(--sp-1));
            width: var(--box-sm); height: var(--box-sm); min-height: 0; padding: 0; border: 0; background: none;
            border-radius: var(--radius-tag); color: var(--text-tertiary); display: grid; place-items: center; }
```

Replace `        .tbl-search.has-q input { padding-right: var(--sp-6); }` with nothing (delete the line and the comment above it, `        /* Only while there is something to clear, so the field keeps its full\n           measure the rest of the time. */`).

In the phone block replace:

```css
            .guide-tools > .act-row > .tbl-search input { width: 100%; } }
```

with:

```css
            .guide-tools > .act-row > .tbl-search { width: auto; } }
```

- [ ] **Step 6: The other 28 fields are 32**

Replace:

```css
        .tbl-tools select { font-weight: var(--weight-regular); height: var(--control-h-md); min-height: var(--control-h-md); padding: var(--sp-1) var(--chevron-room) var(--sp-1) var(--sp-2-5);
            border-radius: var(--radius-field); font-size: var(--text-sm); line-height: var(--lh-control); }
```

with:

```css
        .tbl-tools select { font-weight: var(--weight-regular); height: var(--control-h); min-height: var(--control-h); padding: 0 var(--chevron-room) 0 var(--sp-3);
            border-radius: var(--radius-field); font-size: var(--text-body); line-height: var(--lh-control); }
```

Replace:

```css
        input.field-sm, select.field-sm { height: var(--control-h-md); min-height: var(--control-h-md);
            padding-block: var(--sp-1); font-size: var(--text-sm); line-height: var(--lh-control); border-radius: var(--radius-field); }
```

with:

```css
        input.field-sm, select.field-sm { height: var(--control-h); min-height: var(--control-h);
            padding-block: 0; font-size: var(--text-body); line-height: var(--lh-control); border-radius: var(--radius-field); }
```

Replace:

```css
        .tbl-rows select { height: var(--control-h-md); min-height: var(--control-h-md); width: var(--field-w-sm); padding: 0 var(--sp-2) 0 var(--sp-2-5);
            border-radius: var(--radius-field); font-size: var(--text-sm); line-height: var(--lh-control);
            background-position: right 6px center; }
```

with:

```css
        .tbl-rows select { height: var(--control-h); min-height: var(--control-h); width: var(--field-w-sm); padding: 0 var(--chevron-room) 0 var(--sp-3);
            border-radius: var(--radius-field); font-size: var(--text-body); line-height: var(--lh-control); }
```

Replace:

```css
        .dpanel input, .dpanel select { height: 28px; padding: var(--sp-1) var(--sp-2); border-radius: var(--radius-field);
            font-size: var(--text-sm); line-height: var(--lh-control); }
```

with:

```css
        .dpanel input, .dpanel select { height: var(--control-h); padding: 0 var(--sp-3); border-radius: var(--radius-field);
            font-size: var(--text-body); line-height: var(--lh-control); }
```

- [ ] **Step 7: Update the focus and toolbar guards**

In `t_focus_is_declared_once_per_kind` replace:

```python
    ok(CSS.count("box-shadow: var(--focus-ring)") == 3,
       "the ring is read by the field rule and by the two composite fields that "
       "focus as a whole (the radio card, the composer box), and nowhere else")
    ok(':is(input, textarea, select, [contenteditable="true"]):focus { outline: none; border-color: var(--border-selected); box-shadow: var(--focus-ring); }' in CSS,
       "one rule for every field, contenteditable included")
```

with:

```python
    ok(CSS.count("box-shadow: var(--focus-ring)") == 4,
       "the ring is read by the field rule and by the three composite fields that "
       "focus as a whole (the radio card, the composer box, the search field), and nowhere else")
    ok(':is(input, textarea, select, [contenteditable="true"]):focus { outline: none; box-shadow: var(--focus-ring); }' in CSS,
       "one rule for every field, contenteditable included")
```

In `t_the_table_toolbar_and_pager_match_the_reference` replace:

```python
    srch = CSS.split(".tbl-search input {")[1].split("}")[0]
    ok("height: var(--control-h-md)" in srch and "width: 320px" in srch, "the search field is 28 by 320")
    ok(re.search(r"--control-h-md:\s*28px", CSS), "the small control token is the reference's 28")
    ok("padding: var(--sp-1) var(--sp-2-5) var(--sp-1) var(--sp-7)" in srch, "with room for the icon on the left")
```

with:

```python
    srch = CSS.split("\n        .tbl-search {")[1].split("}")[0]
    ok("height: var(--control-h)" in srch and "width: var(--search-w)" in srch, "the search field is 32 by 280 (the mix)")
    ok("padding: 0 var(--sp-3)" in srch and "gap: var(--control-gap)" in srch, "its glyph 12 in and 8 from the words")
```

- [ ] **Step 8: Run the tests**

Run: `ONLY=t_a_field_is_the_mix python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `435 passed, 0 failed`.

- [ ] **Step 9: Look at it**

In the rig: Production Manager's search reads "Find order, customer or tracking" in a 280 well with its glyph; typing shows the clear button inside the field's end; Tab into it shows one teal ring round the whole field. Products, Size list and CRM searches look the same.

- [ ] **Step 10: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Parts: every field 32 at 13/20 with a line-ctl edge and one focus ring; a search is one 280 field

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Tabs and segmented choosers

**Files:**
- Modify: `static/index.html:380-394` (`.page-tabs`), after `.ov-wrap > .ov-hero` (the tab row's place in the rhythm), `:1116-1123` (the widget grid's tab rules), `:3966-4056` (the two choosers), the script's `chooser` (7220-7265)
- Test: `tests/test_frontend.py` (`t_the_menu_and_tabs_are_the_reference_measurements` 2936, `t_the_finance_pages_share_the_reference_tab_strip` 2989, `t_a_tab_strip_that_scrolls_on_a_phone_holds_its_underline` 9391, `t_the_brand_pilot_review_findings_stay_fixed` 9403, `t_the_spacing_pass_holds` 9494, a new test)

**Interfaces:**
- Consumes: `--row-h`, `--rule-b`, `--ring-chosen`, `--press`, `--fill-mark`.
- Produces: a page's tabs row (`.tabs` straight in `.ov-wrap`, or `.page-tabs` holding `.tabs` and `.page-tabs-end`): 44 tall on a full-width hairline, tabs as wide as their words 24 apart, a 2px teal-line underline at the bottom; 20 under the header, 32 over the body. `segmented()`: a 32 fill track, the chosen segment white with the teal-line ring and ink words. `chooser()` items take `n` (a count drawn 8 after the word as `span.cnt`) and `icon` (an icon-only choice that says its label to a screen reader and on hover). `.cnt` is the one count style (caption, 500, ink-3, tabular).

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_tabs_sit_on_a_rule_and_the_chosen_segment_is_white():
    """Spec 5 and 6: tabs that move between sections sit on a full-width rule,
    44 tall, as wide as their words and 24 apart, the live one in ink with a
    2px teal-line underline. A segmented chooser is a 32 fill track whose chosen
    segment is white with a teal-line ring and ink words. A count sits 8 after
    its word; an icon-only choice still says its name."""
    tabs = CSS.split("\n        .tabs {")[1].split("}")[0]
    for prop in ("min-height: var(--row-h)", "box-shadow: var(--rule-b)", "gap: 0 var(--sp-6)", "align-items: stretch"):
        ok(prop in tabs, ".tabs: " + prop)
    tab = CSS.split("\n        .tab {")[1].split("}")[0]
    ok("font-size: var(--text-body)" in tab and "color: var(--text-tertiary)" in tab and "padding: 0" in tab,
       "a tab is its word, 13 at 500 in ink-3")
    rule = CSS.split('.tab:is(.on, [aria-current="page"], [aria-pressed="true"])::after {')[1].split("}")[0]
    ok("bottom: 0" in rule and "height: var(--bw-strong)" in rule and "var(--fill-mark)" in rule
       and "border-radius: var(--radius-swatch) var(--radius-swatch) 0 0" in rule, "the underline sits on the rule, 2px, teal-line")
    ok(".ov-wrap > .tabs { margin-inline: calc(-1 * var(--wrap-pad)); padding-inline: var(--wrap-pad); max-width: none; }" in CSS,
       "a page's own strip runs edge to edge across the sheet")
    ok(".ov-wrap > :is(.tabs, .page-tabs, .seg-row) { margin-bottom: var(--sp-7); }" in CSS, "and sits 32 above the body")
    pt = CSS.split("\n        .page-tabs {")[1].split("}")[0]
    ok("min-height: var(--row-h)" in pt and "box-shadow: var(--rule-b)" in pt, "a tab row with a chooser on its right is the same 44 on a rule")
    seg = CSS.split("\n        .segmented {")[1].split("}")[0]
    ok("background: var(--surface-tertiary)" in seg and "padding: var(--sp-0-5)" in seg, "the track is the fill, 2 in")
    on = CSS.split('.segmented > button:is(.on, [aria-pressed="true"]) {')[1].split("}")[0]
    ok("background: var(--surface-primary)" in on and "color: var(--text-primary)" in on and "box-shadow: var(--ring-chosen)" in on,
       "the chosen segment is white, ink, with the teal-line ring")
    cnt = CSS.split("\n        .cnt {")[1].split("}")[0]
    ok("font-size: var(--text-xs)" in cnt and "color: var(--text-tertiary)" in cnt and "tabular-nums" in cnt, "a count is caption, ink-3, tabular")
    fn = fn_src("function chooser(")
    ok("if (o.n != null) b.append(el('span', 'cnt', String(o.n)));" in fn, "a choice can carry its count")
    ok("if (o.icon) { b.append(ico(o.icon)); b.setAttribute('aria-label', o.label);" in fn, "and an icon-only choice keeps its name")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_tabs_sit_on_a_rule python3 tests/test_frontend.py`
Expected: `FAIL  t_tabs_sit_on_a_rule_and_the_chosen_segment_is_white: .tabs: min-height: var(--row-h)`

- [ ] **Step 3: The tab strip and the tab**

Replace:

```css
        .tabs { display: flex; align-items: center; flex-wrap: wrap; gap: var(--sp-1) var(--sp-6); max-width: 100%; margin-bottom: var(--sp-3); }
        /* In a card the card's own 16 gap spaces it, as it does a toolbar. */
        .card > .tabs { margin-bottom: 0; }
        /* The 28 row the Finance strip sits in, for every page's strip, so the
           underline lands at one distance under every header. */
        .ov-wrap > .tabs { min-height: var(--control-h-md); }
        .tab { position: relative; display: inline-flex; align-items: center; gap: var(--control-gap);
            height: var(--control-h-sm); padding: var(--sp-0-5) 0; border: 0; background: none;
            border-radius: var(--radius-tag); font: inherit; font-size: var(--text-sm); font-weight: var(--weight-medium);
            line-height: var(--lh-control); color: var(--text-tertiary); cursor: pointer; white-space: nowrap;
            transition: color var(--dur) var(--ease); }
        /* Hover is the ink alone: a grey box behind an underlined tab mixed two
           kinds of tab in one control. */
        .tab:hover, .tab:active { color: var(--text-primary); }
        .tab:is(.on, [aria-current="page"], [aria-pressed="true"]) { color: var(--text-primary); }
        .tab:is(.on, [aria-current="page"], [aria-pressed="true"])::after { content: ""; position: absolute; left: 0; right: 0;
            bottom: -3px; height: 2px; border-radius: var(--radius-full); background: var(--fill-mark); }
        .tab .beta-tag { margin-left: 0; }
```

with:

```css
        /* THE TAB STRIP (the mix, spec 5): 44 tall on a full-width hairline, the
           tabs as wide as their words and 24 apart, the live one in ink with a
           2px teal-line underline sitting on the rule. It never wraps: on a
           narrow screen it scrolls sideways, and the underline and the focus
           ring are drawn inside it, so it never scrolls up and down. */
        .tabs { display: flex; align-items: stretch; flex-wrap: nowrap; gap: 0 var(--sp-6); max-width: 100%; min-height: var(--row-h);
            box-shadow: var(--rule-b); overflow-x: auto; overflow-y: hidden; scrollbar-width: none;
            padding-inline: var(--sp-2); margin: 0 calc(-1 * var(--sp-2)) var(--sp-7); }
        .tabs::-webkit-scrollbar { display: none; }
        .card > .tabs { margin-bottom: 0; }
        /* A page's own strip runs edge to edge across the sheet, its first tab on the gutter. */
        .ov-wrap > .tabs { margin-inline: calc(-1 * var(--wrap-pad)); padding-inline: var(--wrap-pad); max-width: none; }
        .tab { position: relative; display: inline-flex; align-items: center; gap: var(--control-gap); flex: none;
            height: auto; padding: 0; border: 0; background: none;
            border-radius: 0; font: inherit; font-size: var(--text-body); font-weight: var(--weight-medium);
            line-height: var(--lh-control); color: var(--text-tertiary); cursor: pointer; white-space: nowrap;
            transition: color var(--dur) var(--ease); }
        /* Hover is the ink alone: a grey box behind an underlined tab mixed two
           kinds of tab in one control. */
        .tab:hover, .tab:active { color: var(--text-primary); }
        .tab:is(.on, [aria-current="page"], [aria-pressed="true"]) { color: var(--text-primary); }
        .tab:is(.on, [aria-current="page"], [aria-pressed="true"])::after { content: ""; position: absolute; left: 0; right: 0;
            bottom: 0; height: var(--bw-strong); border-radius: var(--radius-swatch) var(--radius-swatch) 0 0; background: var(--fill-mark); }
        /* Focus is a rounded box round the word, inside the strip. */
        .tab:focus-visible { outline: 0; }
        .tab:focus-visible::before { content: ""; position: absolute; inset: var(--sp-1) calc(-1 * var(--sp-2)); border-radius: var(--radius-control);
            box-shadow: inset 0 0 0 var(--bw-strong) var(--fill-mark); pointer-events: none; }
        .tab .beta-tag { margin-left: 0; }
        /* A count beside its word (a tab, a segment, a section head, a list row,
           a menu row): caption at 500 in ink-3, tabular, 8 after the word. */
        .cnt { font-size: var(--text-xs); line-height: var(--lh-caption); font-weight: var(--weight-medium); color: var(--text-tertiary);
            font-variant-numeric: tabular-nums; }
```

Replace the phone block and the comment above it, from the line `        /* On a phone a long strip scrolls rather than cutting off its last tab,` through the block's closing `            .page-tabs > .tabs { margin-block: calc(-1 * var(--sp-1)); } }` (the base `.tabs` rule above now scrolls at every width), with:

```css
        /* On a phone the Beta marks go from the tabs: the sidebar still carries them. */
        @media (max-width: 900px) {
            .tab .beta-tag { display: none; } }
```

- [ ] **Step 4: The segmented chooser**

Replace:

```css
        .segmented { display: inline-flex; flex-wrap: wrap; align-items: center; align-self: flex-start; gap: var(--sp-0-5); max-width: 100%;
            padding: var(--sp-0-5); background: var(--surface-sunken); border: 0;
            border-radius: var(--radius-control); }
```

with:

```css
        .segmented { display: inline-flex; flex-wrap: wrap; align-items: center; align-self: flex-start; gap: var(--sp-0-5); max-width: 100%;
            padding: var(--sp-0-5); background: var(--surface-tertiary); border: 0;
            border-radius: var(--radius-control); }
```

Replace:

```css
        .segmented > button { flex: 1 1 auto; justify-content: center; display: inline-flex; align-items: center; gap: var(--control-gap); height: var(--segment-h);
            padding: 0 var(--sp-2-5); border: 0; background: transparent; border-radius: calc(var(--radius-control) - var(--sp-0-5));
            font: inherit; font-size: var(--text-sm); font-weight: var(--weight-medium); line-height: var(--lh-control);
            color: var(--text-secondary); cursor: pointer; white-space: nowrap;
            transition: background var(--dur) var(--ease), color var(--dur) var(--ease); }
        .segmented > button:hover { color: var(--text-primary); }
        .segmented > button:active { background: var(--surface-sunken); }
        .segmented > button:is(.on, [aria-pressed="true"]) { background: var(--surface-primary); color: var(--text-brand); box-shadow: var(--ring-default); }
```

with:

```css
        .segmented > button { flex: 1 1 auto; justify-content: center; display: inline-flex; align-items: center; gap: var(--control-gap); height: var(--segment-h);
            padding: 0 var(--sp-3); border: 0; background: transparent; border-radius: calc(var(--radius-control) - var(--sp-0-5));
            font: inherit; font-size: var(--text-body); font-weight: var(--weight-medium); line-height: var(--lh-control);
            color: var(--text-tertiary); cursor: pointer; white-space: nowrap;
            transition: background var(--dur) var(--ease), color var(--dur) var(--ease); }
        .segmented > button:hover { color: var(--text-primary); }
        .segmented > button:active { background: var(--press); }
        /* Chosen (the mix, 4.6): white with a teal-line ring and ink words. */
        .segmented > button:is(.on, [aria-pressed="true"]) { background: var(--surface-primary); color: var(--text-primary); box-shadow: var(--ring-chosen); }
        .segmented > button svg { width: var(--icon-md); height: var(--icon-md); }
```

- [ ] **Step 5: The tab row with a chooser at its right**

Replace:

```css
        .page-tabs { display: flex; align-items: center; gap: var(--sp-3);
            flex-wrap: wrap; margin-bottom: var(--sp-6);
            /* One height whether or not the row carries a button, so the
               underline and the first block do not jump between tabs. */
            min-height: var(--control-h-md); }
        /* The strip shares its row with the stamp and Refresh, centred: its own
           space below would lift its labels 6px above them. */
        .page-tabs > .tabs { margin-bottom: 0; }
```

with:

```css
        /* A tab row with the page's own chooser at its right (Forecast's Plan):
           one 44 row on one full-width rule, the strip's own rule given up. */
        .page-tabs { display: flex; align-items: center; justify-content: space-between; gap: var(--sp-6);
            min-height: var(--row-h); box-shadow: var(--rule-b);
            margin: 0 calc(-1 * var(--wrap-pad)) var(--sp-7); padding: 0 var(--wrap-pad); }
        .page-tabs > .tabs { margin-bottom: 0; }
        .page-tabs > .tabs { margin: 0; padding: 0; box-shadow: none; align-self: stretch; min-height: 0; }
```

In the rule `        .page-tabs-end { margin-left: auto; display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: var(--sp-2); }` replace `gap: var(--sp-2); }` with `gap: var(--control-gap); }`.

After `        .ov-wrap > .ov-hero { margin-bottom: var(--sp-7); }` add:

```css
        /* A page's tab row sits 32 above the body. */
        .ov-wrap > :is(.tabs, .page-tabs, .seg-row) { margin-bottom: var(--sp-7); }
```

In the widget grid rules replace `        .ov-wrap.wgrid > :is(.tabs, .segmented) { justify-self: start; }` with:

```css
        .ov-wrap.wgrid > .segmented { justify-self: start; }
        /* In the grid a tab row still runs edge to edge, and its 32 to the body
           is taken out of the grid's gap. */
        .ov-wrap.wgrid > :is(.tabs, .page-tabs) { margin-inline: calc(-1 * var(--wrap-pad)); margin-bottom: calc(var(--sp-7) - var(--page-rhythm)); }
```

- [ ] **Step 6: Counts and icon-only choices**

In `chooser` replace:

```js
                const o = Array.isArray(it) ? { key: it[0], label: it[1] }
                    : { key: it.key !== undefined ? it.key : it.value, label: it.label, extra: it.extra, title: it.title, disabled: it.disabled };
                const b = el('button', kind === 'tabs' ? 'tab' : null);
                b.type = 'button'; b.dataset.k = String(o.key);
                b.append(document.createTextNode(o.label));
                if (o.extra) b.append(o.extra);
                if (o.title) b.title = o.title;
```

with:

```js
                const o = Array.isArray(it) ? { key: it[0], label: it[1] }
                    : { key: it.key !== undefined ? it.key : it.value, label: it.label, extra: it.extra, title: it.title, disabled: it.disabled, n: it.n, icon: it.icon };
                const b = el('button', kind === 'tabs' ? 'tab' : null);
                b.type = 'button'; b.dataset.k = String(o.key);
                /* An icon-only choice (Forecast's Custom range) says its name to
                   a screen reader and on hover; a count sits 8 after its word. */
                if (o.icon) { b.append(ico(o.icon)); b.setAttribute('aria-label', o.label); b.title = o.title || o.label; }
                else b.append(document.createTextNode(o.label));
                if (o.n != null) b.append(el('span', 'cnt', String(o.n)));
                if (o.extra) b.append(o.extra);
                if (o.title && !o.icon) b.title = o.title;
```

Update the comment above `function chooser(` so its items line reads:

```js
           items: [key, label] pairs, or {key | value, label, n, icon, extra,
           title, disabled}: n is a count drawn after the label, icon makes the
           choice icon-only (label becomes its name), extra is a node shown after
           the label (a tick, a Beta mark). opts.nav: the tabs are pages, so the
```

(replacing the two lines that begin `           items: [key, label] pairs, or {key | value, label, extra, title,` and `           disabled}, where extra is a node shown after the label (a count, a`, and the line `           tick, a Beta mark). opts.nav: the tabs are pages, so the live one is` becomes `           live one is`).

- [ ] **Step 7: Update the guards that pinned the old strip**

In `t_the_menu_and_tabs_are_the_reference_measurements` replace:

```python
    tab = CSS.split("\n        .tab {")[1].split("}")[0]
    ok("height: var(--control-h-sm)" in tab and "padding: var(--sp-0-5) 0" in tab, "tabs are 24px and as wide as their label")
```

with:

```python
    tab = CSS.split("\n        .tab {")[1].split("}")[0]
    ok("height: auto" in tab and "padding: 0" in tab, "a tab fills its 44 strip and is as wide as its label (the mix)")
```

and replace:

```python
    ok("height: 2px" in rule, "and a 2px rule under it")
```

with:

```python
    ok("height: var(--bw-strong)" in rule and "bottom: 0" in rule, "and a 2px rule under it, on the strip's own rule")
```

In `t_the_finance_pages_share_the_reference_tab_strip` replace:

```python
    ok("height: var(--control-h-sm)" in tab and "padding: var(--sp-0-5) 0" in tab, "the small control height, one size for every tab")
    ok("font-size: var(--text-sm)" in tab, "at 14px, bigger than a filter tab inside a card")
```

with:

```python
    ok("height: auto" in tab and "padding: 0" in tab, "one 44 strip for every tab row (the mix)")
    ok("font-size: var(--text-body)" in tab, "at the body's 13")
```

and replace:

```python
    ok("height: 2px" in rule, "and carries the reference's 2px rule under it")
```

with:

```python
    ok("height: var(--bw-strong)" in rule, "and carries a 2px rule under it")
```

Replace the whole body of `t_a_tab_strip_that_scrolls_on_a_phone_holds_its_underline` (its three `ok` calls and the `phone =` line) with:

```python
    rule = CSS.split(".tab:is(.on, [aria-current=\"page\"], [aria-pressed=\"true\"])::after {")[1][:240]
    ok("bottom: 0; height: var(--bw-strong);" in rule, "the underline sits inside the strip (the mix), so nothing hangs under it")
    tabs = CSS.split("\n        .tabs {")[1].split("}")[0]
    ok("overflow-x: auto" in tabs and "overflow-y: hidden" in tabs, "the strip scrolls sideways only, on every screen")
```

In `t_the_brand_pilot_review_findings_stay_fixed` replace:

```python
    # The Finance strip lines up with the stamp beside it.
    ok(".page-tabs > .tabs { margin-bottom: 0; }" in CSS, "the Finance strip carries no space below it in its row")
    # On a phone a scrolling strip holds the focus outline as well as the underline.
    strip = CSS.split("@media (max-width: 900px) {\n            .tabs {")[1].split("}")[0]
    ok("padding: var(--sp-1);" in strip and "margin: calc(-1 * var(--sp-1)) calc(-1 * var(--sp-1)) var(--sp-1)" in strip,
       "room on every side for the 3px outline, taken back so the tabs do not move")
```

with:

```python
    # The Finance strip lines up with the chooser beside it.
    ok(".page-tabs > .tabs { margin-bottom: 0; }" in CSS, "the Finance strip carries no space below it in its row")
    # A scrolling strip keeps the focus ring inside itself (the mix: drawn on ::before).
    ok(".tab:focus-visible::before {" in CSS and "padding-inline: var(--sp-2); margin: 0 calc(-1 * var(--sp-2)) var(--sp-7);"
       in CSS.split("\n        .tabs {")[1].split("}")[0], "room at each end for the focus ring, taken back so the tabs do not move")
```

In `t_the_spacing_pass_holds` replace:

```python
    ok(".ov-wrap > .tabs { min-height: var(--control-h-md); }" in CSS, "every page's strip sits in Finance's 28 row")
```

with:

```python
    ok("min-height: var(--row-h)" in CSS.split("\n        .tabs {")[1].split("}")[0], "every page's strip is the one 44 row")
```

- [ ] **Step 8: Run the tests**

Run: `ONLY=t_tabs_sit_on_a_rule python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `436 passed, 0 failed`.

- [ ] **Step 9: Look at it**

Liability: the Finance tabs sit on a hairline running the sheet's width, 20 under the header, the live tab underlined in teal-line, the stamp and Refresh at the row's right. Production Manager, Guide, Team and Files tabs the same. A segmented chooser (CRM Board/List) is a grey track with the chosen one white, ringed and in ink. At 390 the strips scroll sideways with no vertical scrollbar.

- [ ] **Step 10: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Parts: tabs on a full-width rule with a teal-line underline, a white chosen segment, counts and icon-only choices

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: A section is a title and space

**Files:**
- Modify: `static/index.html:629` and the phone `.ov-wrap` (the page rhythm), `:1209-1213` (`.section-title`), `:1458-1531` (the card model), `:1606-1639` (the bleed rules), `:1642-1659` (the card head), `:2169` (`#view-connector .card > .lbl-row`), `:3713-3732` (tables in cards), `:4060` (nested corners), `:4114-4115` (`.chart-card`)
- Test: `tests/test_frontend.py` (remove five card-gutter tests; rewrite `t_a_boxed_child_of_a_card_is_inset` 6115, `t_a_table_inside_a_card_has_no_second_frame` 2810, `t_the_dead_elevation_token_is_gone` 1363, `t_one_rhythm_down_the_page` 3901, `t_a_heading_keeps_its_12px_on_a_phone` 3922, `t_the_brand_pilot_review_findings_stay_fixed` 9403; a new test)

**Interfaces:**
- Consumes: `--page-rhythm`, `--text-head`, `--sp-9`.
- Produces: `.card` is an unboxed section (head, then content 12 under it); `.section-title` and `.card-title` are the head step (15/20 at 600, Inter); sections are 48 apart (32 on a phone); `.chart-card` has no frame. Every later task builds a section from these, with the head's count as `span.cnt` (Task 10) and its info button (Task 12) beside the title.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_a_section_is_a_title_and_space():
    """Spec 3 and 6 (Cameron: "it still all looks very dated and text heavy"):
    one sheet, few boxes. A section is a 15/20 600 head, then its content 12
    under it, 48 from the next (32 on a phone); no edge, no fill, no padding,
    so its content runs on the page's own text edge. A chart sits in its
    section without a frame either."""
    card = CSS.split("\n        .card {")[1].split("}")[0]
    for prop in ("background: none", "border: 0", "box-shadow: none", "padding: 0", "gap: var(--sp-3)"):
        ok(prop in card, ".card: " + prop)
    ok("\n        .card > * { padding-left" not in CSS, "children are not handed a gutter any more")
    ok(not re.search(r"\.card > :is\(\.lia-bar, \.lbl-row", CSS), "so nothing has to take one back as a margin")
    for sel in ("\n        .card-title {", "\n        .section-title {"):
        r = CSS.split(sel)[1].split("}")[0]
        ok("font-size: var(--text-head)" in r and "font-weight: var(--weight-semibold)" in r and "line-height: var(--lh-control)" in r,
           sel.strip() + " is the head step, 15/20 at 600")
    ok(re.search(r"\.ov-wrap \{[^}]*--page-rhythm: var\(--sp-9\)", CSS), "48 between sections")
    chart = CSS.split("\n        .chart-card {")[1].split("}")[0]
    ok("border: 0" in chart and "padding: 0" in chart and "background: none" in chart, "a chart has no frame of its own")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_a_section_is_a_title python3 tests/test_frontend.py`
Expected: `FAIL  t_a_section_is_a_title_and_space: .card: background: none`

- [ ] **Step 3: The rhythm**

In the `.ov-wrap {` rule replace `            --page-rhythm: var(--sp-6); }` with `            --page-rhythm: var(--sp-9); }`. In the phone block replace `            .ov-wrap { padding: var(--sp-5) var(--sp-4) var(--sp-7); --page-rhythm: var(--sp-4); }` with:

```css
            .ov-wrap { padding: var(--sp-5) var(--sp-4) var(--sp-7); --page-rhythm: var(--sp-7); }
```

- [ ] **Step 4: The section head**

Replace:

```css
        .section-title { font-size: var(--text-lg); font-weight: var(--weight-medium); text-transform: none; letter-spacing: normal; color: var(--text-primary);
            line-height: var(--lh-snug); margin: var(--sp-6) 0 var(--sp-3); display: flex; align-items: center; gap: var(--sp-2); }
```

with:

```css
        /* THE SECTION HEAD (the mix, spec 6): 15/20 at 600 in Inter, a count and
           an info button after it, tools at the right; 12 above its content and
           a section's own space above it. */
        .section-title { font-size: var(--text-head); font-weight: var(--weight-semibold); text-transform: none; letter-spacing: normal; color: var(--text-primary);
            line-height: var(--lh-control); min-height: var(--control-h); margin: var(--page-rhythm, var(--sp-9)) 0 var(--sp-3);
            display: flex; align-items: center; gap: var(--sp-2); }
```

- [ ] **Step 5: The card is a section**

Replace:

```css
        .card { background: var(--surface-primary); border: var(--bw-hairline) solid var(--border-default);
            border-radius: var(--radius-card); box-shadow: var(--shadow-sm);
            padding: var(--sp-4) 0; display: flex; flex-direction: column; gap: var(--sp-4); }
        /* .card's display beat the browser's [hidden]: an empty Skills page
           drew the hidden 'How they are used' card as a bare 34px box. */
        .card[hidden] { display: none; }
        .card > * { padding-left: var(--sp-4); padding-right: var(--sp-4); }
```

with:

```css
        /* A SECTION, NOT A CARD (the mix, spec 3): one sheet, few boxes. What
           was a card is a head and its content on the sheet: no edge, no fill,
           no padding of its own, its content 12 under its head and on the
           page's text edge, the page rhythm (48) to the next. The class stays,
           so every screen's sections changed at once. */
        .card { background: none; border: 0; border-radius: 0; box-shadow: none;
            padding: 0; display: flex; flex-direction: column; gap: var(--sp-3); }
        /* .card's display beat the browser's [hidden]: an empty Skills page
           drew the hidden 'How they are used' card as a bare 34px box. */
        .card[hidden] { display: none; }
```

Delete these rules with the comments that introduce them, each block as it stands (they handed out and took back a gutter a section no longer has):

```css
        /* ...and the exception to the opt-out. The gutter is handed out as
           PADDING, which is right for the things that should meet the card's
           edge with only their content inset: a table, a list row, the
           composer bar at the foot of a chat. It is wrong for anything that
           draws an edge of its own, because padding sits INSIDE the border
           box - the child still spans the full width and its border lands
           exactly on the card's. Two borders meeting is a seam, not a frame.
           These take the inset as MARGIN and keep their own padding. */
        .card > .lia-bar, .card > .ktable-wrap { padding-left: 0; padding-right: 0; }
```

```css
        /* A scroller takes the gutter as MARGIN: its padding is part of the
           scrollport, so a padded board scrolls its last column right up to
           the card's border. */
        .card > .crm-board { padding-left: 0; padding-right: 0; margin-left: var(--sp-4); margin-right: var(--sp-4); }
```

```css
        /* A card pads its children (the rule above), so a child that paints its
           OWN box would sit flush against the card's border on both sides.
           Those are inset by margin instead. The list is every boxed class the
           script puts straight into a card; the rig sweep finds new ones. */
        .card > :is(.lia-bar, .lbl-row, .ktable-wrap, .empty, .msg, .mail-sendwarn, .disp-warn, .mail-empty,
                    .cx-health, .fc-algo, .fc-alert, .know-body, .fc-drive-tot, .fc-split-bar, .mail-viewwarn,
                    .rel, .req-row, .segmented),
        .card-bleed > .empty {
            margin-left: var(--sp-4); margin-right: var(--sp-4);
            /* The inset is a MARGIN, so the width must not also be 100%:
               .lbl-row carries width:100% to make button rows fill, and
               100% of the card PLUS two 16px margins put every row 32px
               wider than the card, hanging its right border out past the
               frame. Filling is what auto already does for a block. */
            width: auto; }
```

```css
        /* The list's markers sit inside the card's gutter, not over it. */
        .card > .setup-steps { padding-left: calc(var(--sp-4) + var(--sp-5)); }
```

```css
        /* A grid of segment cards inside a bleed keeps the card's 16px gutter: the
           cards draw their own edges, so the wrapper insets them by padding. */
        .card-bleed > .segs { padding: 0 var(--sp-4); }
```

```css
        /* The card's own 16px gap never reaches a table's pager or a selection
           bar, because both are siblings inside a plain host div rather than
           children of the card. They take the gutter as margin so they keep
           their inset once the table beside them bleeds to the edge. */
        .card-bleed > .tbl-foot, .card-bleed > .lbl-toolbar {
            margin-left: var(--sp-4); margin-right: var(--sp-4); }
```

```css
        /* A table straight inside a card runs to the card's edges, the way its
           list rows do: inset by the gutter, its dividers and a chosen row's
           wash stopped 16 short of the frame and the wash touched the first
           word. Its outer cells take the gutter, so the words stay on the
           card's text edge. */
        .card > .ktable-wrap { margin-left: 0; margin-right: 0; }
        .card > .ktable-wrap :is(th, td):first-child { padding-left: var(--sp-4); }
        .card > .ktable-wrap :is(th, td):last-child { padding-right: var(--sp-4); }
```

```css
        /* A 14px box inside a 14px box with 16px of padding reads blocky at
           the inner corner. The tables already step down to the base radius
           inside a card; these were the three shapes that had not. */
        .card .insight, .card .empty, .chart-card .empty { border-radius: var(--radius-inset); }
```

Replace:

```css
        .card-bleed .ktable th:first-child, .card-bleed .ktable td:first-child { padding-left: var(--sp-4); }
        .card-bleed .ktable th:last-child, .card-bleed .ktable td:last-child { padding-right: var(--sp-4); }
```

with:

```css
        .card-bleed .ktable th:first-child, .card-bleed .ktable td:first-child { padding-left: 0; }
        .card-bleed .ktable th:last-child, .card-bleed .ktable td:last-child { padding-right: 0; }
```

Replace `        #view-connector .card > .lbl-row { width: fit-content; max-width: calc(100% - 2 * var(--sp-4)); }` with:

```css
        #view-connector .card > .lbl-row { width: fit-content; max-width: 100%; }
```

- [ ] **Step 6: The section's head row**

Replace:

```css
        .card-head { display: grid; grid-template-columns: 1fr auto; align-items: start;
            gap: var(--sp-1) var(--sp-4); }
        /* leading-none, as the reference sets it: the title's line box is its
           own size, so the header is exactly title + 4 + description and every
           card head in the app lines up at the same height. */
        .card-title { font-size: var(--text-md); font-weight: var(--weight-medium);
            line-height: var(--lh-none); margin: 0; }
        .card-desc { grid-column: 1; font-size: var(--text-sm); color: var(--text-tertiary);
            line-height: var(--lh-control); margin: 0; max-width: var(--measure); }
```

with:

```css
        /* A section's head row: the title (with its count and info button) on
           the left and its tools on the right, 32 tall so a button beside it
           sits on the title's line. */
        .card-head { display: grid; grid-template-columns: 1fr auto; align-items: center;
            gap: var(--sp-1) var(--sp-4); min-height: var(--control-h); }
        .card-title { font-size: var(--text-head); font-weight: var(--weight-semibold);
            line-height: var(--lh-control); margin: 0; display: flex; align-items: center; gap: var(--sp-2); }
        .card-desc { grid-column: 1; font-size: var(--text-body); color: var(--text-tertiary);
            line-height: var(--lh-control); margin: 0; max-width: var(--measure); }
```

Replace `        .card-sub { grid-column: 1; margin: 0; font-size: var(--text-sm); color: var(--text-tertiary); line-height: var(--lh-control); max-width: var(--measure); }` with:

```css
        .card-sub { grid-column: 1; margin: 0; font-size: var(--text-body); color: var(--text-tertiary); line-height: var(--lh-control); max-width: var(--measure); }
```

- [ ] **Step 7: A chart has no frame**

Replace:

```css
        .chart-card { background: var(--surface-primary); border: var(--bw-hairline) solid var(--border-default); border-radius: var(--radius-card);
            box-shadow: var(--shadow-sm); padding: var(--sp-4); margin-bottom: var(--sp-4); position: relative; }
```

with:

```css
        /* A chart sits in its section with no frame (the mix, spec 3). */
        .chart-card { background: none; border: 0; border-radius: 0;
            box-shadow: none; padding: 0; margin-bottom: var(--sp-4); position: relative; }
```

- [ ] **Step 8: Retire the guards of the card gutter and rewrite their neighbours**

Delete these five tests from `tests/test_frontend.py` entirely (the `@test` line, the `def` and its body): `t_nothing_that_draws_an_edge_sits_on_the_cards_edge`, `t_a_table_in_a_card_is_inset_rather_than_welded_to_it`, `t_a_box_painted_inside_a_card_sits_inside_its_gutter`, `t_a_row_inset_by_a_margin_is_not_also_a_full_width_row`, `t_nested_boxes_step_their_radius_down`. Each guarded the 16px gutter a boxed card handed its children; spec 3 retires the box, and `t_a_section_is_a_title_and_space` guards what replaced it.

In `t_a_boxed_child_of_a_card_is_inset` replace the docstring and every line before `    ok(".load-failed > div:first-child { max-width: var(--measure); }"` with:

```python
    """Sweep, 2026-09-07: boxed notices sat flush against their card's border.
    Since the mix (2026-10-06) a section has no border to sit against: its
    content runs on the page's text edge, so a notice spans its section and
    its words keep the reading measure. The sweep's other lessons stay."""
    ok(not re.search(r"\.card > :is\(", CSS), "no list of children taking a gutter back as a margin")
```

and in the same test replace:

```python
    ok("max-width: calc(100% - 2 * var(--sp-4))" in CSS.split("#view-connector .card > .lbl-row {")[1].split("}")[0],
       "a fit-content row counts its own inset, so it cannot hang out of the card at 375")
```

with:

```python
    ok("max-width: 100%" in CSS.split("#view-connector .card > .lbl-row {")[1].split("}")[0],
       "a fit-content row never runs past its section at 375")
```

Replace the body of `t_a_table_inside_a_card_has_no_second_frame` (from `    ok(".card .ktable-wrap { border: 0;` to its last line) with:

```python
    ok(".card .ktable-wrap { border: 0; border-radius: 0; background: transparent; }" in CSS,
       "a table inside a section draws no frame of its own")
    ok(".card .ktable-wrap :is(th, td):first-child { padding-left: 0; }" in CSS
       and ".card .ktable-wrap :is(th, td):last-child { padding-right: 0; }" in CSS,
       "and its outer columns sit on the page's text edge")
    ok(".card > .ktable-wrap :is(th, td):first-child" not in CSS,
       "no table straight in a section is pushed back in by a gutter (the mix: there is none)")
    ok("--radius-inset: var(--radius-xs)" in CSS and "--radius-card: var(--radius-pop)" in CSS, "corners set once")
    bleed = CSS.split("\n        .card-bleed .ktable-wrap {")[1].split("}")[0]
    ok("border: 0" in bleed, "a bleed table is still flat")
```

In `t_the_brand_pilot_review_findings_stay_fixed` replace:

```python
    inset = CSS.split("Those are inset by margin instead.")[1].split("{")[0]
    ok(".segmented" in inset, "and a track put straight into a card is inset like every boxed child")
```

with:

```python
    # Since the mix (2026-10-06) a section has no gutter for a track to be
    # inset from: it sits on the page's text edge like the rest of its section.
    ok("Those are inset by margin instead." not in CSS, "and no list of boxed children takes a gutter back")
```

In `t_the_dead_elevation_token_is_gone` replace:

```python
    for cls in ("card", "lia-card", "auth-card"):
```

with:

```python
    # A card is a section with no box since the mix (2026-10-06); what is still
    # boxed keeps the house elevation.
    for cls in ("lia-card", "auth-card"):
```

In `t_one_rhythm_down_the_page` replace `       and re.search(r"\.ov-wrap \{[^}]*--page-rhythm: var\(--sp-6\)", CSS),` with `       and re.search(r"\.ov-wrap \{[^}]*--page-rhythm: var\(--sp-9\)", CSS),` and replace `       "and it is the reference's 24px")` with `       "and it is the mix's 48 between sections")`.

In `t_a_heading_keeps_its_12px_on_a_phone` replace:

```python
    ok(phone and re.search(r"\.ov-wrap \{[^}]*--page-rhythm: var\(--sp-4\)", phone[0]),
       "the phone gap is the property re-pointed to 16, not a margin rule")
```

with:

```python
    ok(phone and re.search(r"\.ov-wrap \{[^}]*--page-rhythm: var\(--sp-7\)", phone[0]),
       "the phone gap is the property re-pointed to 32, not a margin rule")
```

- [ ] **Step 9: Run the tests**

Run: `ONLY=t_a_section_is_a_title python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `432 passed, 0 failed` (436, less the five retired, plus this one).

- [ ] **Step 10: Look at it**

Overview, Liability and Memory at 1440 and 390: no white boxes; each section's head is 15 at 600 with its content 12 under it and 48 to the next section (32 at 390); tables, rows and notices start on the page's text edge; charts have no frame. Nothing overlaps.

- [ ] **Step 11: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Parts: a section is a title and space: no card boxes, a 15/600 head, 48 between sections

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: The info button and its popover

**Files:**
- Modify: `static/index.html` `:root` tier 2 and 3 (`--text-link-hover`, `--pop-w`), the icon table `const I = {` (5300-5383), the script after `pageHead` (Task 7), `dropMenu` and `dropPanel` (7105-7188), the stylesheet after `.dpanel.drive-panel` (3956)
- Test: `tests/test_frontend.py` (`t_the_menu_and_tabs_are_the_reference_measurements` 2936, `t_the_ink_frame_the_measures_and_the_shadows_are_tokens` and `t_the_card_elevation_token_actually_paints` as Task 3 left them, a new test)

**Interfaces:**
- Consumes: `.info` (Task 7), `dropPanel(anchor, build)` (7168), `closeDMenu()` (7090), `openGuideAt(secId, q)` (22325), `tokenNum(name)` (5282), `pageHead` (Task 7).
- Produces: `I.info`, `I.arrowRight`; `infoButton(label, o)` returns `button.info` (24, aria-label `label`, `aria-haspopup="dialog"`) that opens a popover (`.dmenu` > `.dpanel.ipop`) holding `o.title` (an `h3`), `o.body` (a string or an array of strings and nodes, each a `p`) and, when `o.guide` is `[sectionId, query]`, a "More in the Guide" link that opens the Guide there. `pageHead({ ..., info })` puts an info button beside the title. `.link`: a standalone teal link with a 14 arrow, no underline. Every menu and panel opens 8 from its trigger (`--pop-offset`). `--shadow-md` is retired (the menu was its one reader).

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_an_explanation_waits_behind_an_info_button():
    """Spec 3, 6 and 7: numbers first, words on request. An explanation moves
    word for word behind a 24 info button beside its heading or figure label;
    the button opens a popover (10 corner, the pop shadow, 16 inside, 8 from
    its trigger) with the words and "More in the Guide". It opens on a tap and
    from the keyboard, unlike the old hover-only title text."""
    ok("info: SV(" in SCRIPT and "arrowRight: SV(" in SCRIPT, "the info glyph and the link arrow are icons like the rest")
    ok("function infoButton(label, o) {" in SCRIPT, "the builder exists")
    fn = fn_src("function infoButton(label, o) {")
    for part in ("el('button', 'info')", "b.setAttribute('aria-label', label)", "b.setAttribute('aria-haspopup', 'dialog')",
                 "dropPanel(b, (box) => {", "box.classList.add('ipop')", "'More in the Guide'", "openGuideAt(o.guide[0], o.guide[1] || '')"):
        ok(part in fn, "infoButton: " + part)
    ok("if (o.info) h.append(o.info);" in fn_src("function pageHead(o) {"), "a page title can carry one")
    pop = CSS.split("\n        .dpanel.ipop {")[1].split("}")[0]
    ok("padding: var(--pop-pad)" in pop and "width: var(--pop-w)" in pop, "the popover is 16 inside, one width")
    eq(_token_raw("pop-w"), "360px", "--pop-w")
    menu = CSS.split("\n        .dmenu {")[1].split("}")[0]
    ok("border-radius: var(--radius-pop)" in menu and "box-shadow: var(--shadow-pop)" in menu, "on the floating corner and shadow")
    for fname in ("function dropMenu(", "function dropPanel("):
        f = fn_src(fname)
        ok("tokenNum('--pop-offset')" in f and "r.bottom + 4" not in f, fname + " opens 8 from its trigger")
    link = CSS.split("\n        .link {")[1].split("}")[0]
    ok("color: var(--text-link)" in link and "font-weight: var(--weight-medium)" in link and "text-decoration: none" in link,
       "a standalone link is teal words at 500 with an arrow, not underlined")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_an_explanation_waits python3 tests/test_frontend.py`
Expected: `FAIL  t_an_explanation_waits_behind_an_info_button: the info glyph and the link arrow are icons like the rest`

- [ ] **Step 3: Tokens and icons**

In `:root` replace `            --text-on-action: var(--ink); --text-link: var(--teal-700); --text-brand: var(--teal-700);` with:

```
            --text-on-action: var(--ink); --text-link: var(--teal-700); --text-brand: var(--teal-700);
            --text-link-hover: var(--teal-900);   /* a link under the pointer or pressed: the dark teal */
```

and replace `            --search-w: 280px;      /* a list's search field */` with:

```
            --search-w: 280px;      /* a list's search field */
            --pop-w: 360px;         /* a popover's width (the window's, less 16 a side, on a phone) */
```

In `const I = {`, directly after the line that begins `            helpCircle: SV(`, add:

```js
            info: SV('<circle cx="12" cy="12" r="10"></circle><path d="M12 16v-4"></path><path d="M12 8h.01"></path>'),
            arrowRight: SV('<path d="M5 12h14"></path><path d="m12 5 7 7-7 7"></path>'),
```

- [ ] **Step 4: Menus and panels open 8 from their trigger**

In `dropMenu` replace:

```js
            let top = r.bottom + 4;
            if (top + ph > window.innerHeight - 8) top = Math.max(8, r.top - ph - 4);
```

with:

```js
            const off = tokenNum('--pop-offset');
            let top = r.bottom + off;
            if (top + ph > window.innerHeight - 8) top = Math.max(8, r.top - ph - off);
```

and make the same replacement in `dropPanel` (its two lines read the same).

- [ ] **Step 5: The builder**

Directly after `pageHead` add:

```js
        /* An explanation on request (the mix, spec 6 and 7): a 24 info glyph
           beside a heading or a figure label, opening a popover with the words
           that used to sit under the title, moved word for word, and a link to
           the Guide. A tap and the keyboard open it as well as a click, which
           the old title text on hover never did. o: { title, body: a string or
           [strings and nodes], guide: [section id, search] } */
        function infoButton(label, o) {
            const b = el('button', 'info');
            b.type = 'button'; b.title = label;
            b.setAttribute('aria-label', label);
            b.setAttribute('aria-haspopup', 'dialog');
            b.setAttribute('aria-expanded', 'false');
            b.append(ico(I.info));
            b.onclick = (e) => {
                e.stopPropagation();
                dropPanel(b, (box) => {
                    box.classList.add('ipop');
                    if (o.title) box.append(el('h3', null, o.title));
                    [].concat(o.body || []).filter(Boolean).forEach(t => box.append(typeof t === 'string' ? el('p', null, t) : t));
                    if (o.guide) {
                        const a = el('button', 'link', 'More in the Guide');
                        a.type = 'button'; a.append(ico(I.arrowRight));
                        a.onclick = () => { closeDMenu(); openGuideAt(o.guide[0], o.guide[1] || ''); };
                        box.append(a);
                    }
                });
            };
            return b;
        }
```

In `pageHead` replace:

```js
            if (o.view && BETA_TABS.indexOf(o.view) >= 0) h.append(el('span', 'beta-tag', 'Beta'));
```

with:

```js
            if (o.view && BETA_TABS.indexOf(o.view) >= 0) h.append(el('span', 'beta-tag', 'Beta'));
            if (o.info) h.append(o.info);
```

and add `info` to its comment's option list (`o: { view, title, info: an infoButton, line, ...`).

- [ ] **Step 6: The menu box, the popover and the link**

Replace:

```css
        .dmenu { position: fixed; z-index: 70; min-width: 128px; padding: var(--sp-1);
            background: var(--surface-primary); border-radius: var(--radius-card);
            box-shadow: var(--shadow-md);
            max-height: 70vh; overflow-y: auto; }
```

with:

```css
        /* WHAT FLOATS (the mix, spec 6): a menu, a panel and a popover share a
           10 corner, the pop shadow and 4 inside (a panel 12, a popover 16). */
        .dmenu { position: fixed; z-index: 70; min-width: 128px; padding: var(--menu-pad);
            background: var(--surface-primary); border-radius: var(--radius-pop);
            box-shadow: var(--shadow-pop);
            max-height: 70vh; overflow-y: auto; }
```

Replace:

```css
        .dpanel { display: flex; flex-direction: column; gap: var(--sp-3); padding: var(--sp-3);
            min-width: 240px; }
```

with:

```css
        /* A panel is padded once: the menu box round it gives up its own 4. */
        .dpanel { display: flex; flex-direction: column; gap: var(--sp-3); padding: var(--pop-pad);
            min-width: 240px; }
        .dmenu:has(> .dpanel) { padding: 0; }
```

Directly after `        .dpanel.drive-panel { width: min(360px, calc(100vw - 16px)); }` add:

```css
        /* A popover: the explanation an info button holds, then the Guide link. */
        .dpanel.ipop { width: var(--pop-w); max-width: calc(100vw - 2 * var(--sp-4)); min-width: 0; padding: var(--pop-pad); gap: var(--sp-2); }
        .ipop h3 { margin: 0; font-size: var(--text-body); line-height: var(--lh-control); font-weight: var(--weight-semibold); color: var(--text-primary); }
        .ipop p { margin: 0; font-size: var(--text-body); line-height: var(--lh-control); color: var(--text-secondary); }
        .ipop .link { align-self: flex-start; margin-top: var(--sp-1); }
        /* A standalone link ("Show all", "More in the Guide"): teal words at
           500 with a 14 arrow 2 after them. Not underlined: it stands alone, so
           the arrow carries what an underline does in running text. */
        .link { display: inline-flex; align-items: center; gap: var(--sp-0-5); padding: 0; border: 0; background: none;
            font: inherit; font-weight: var(--weight-medium); color: var(--text-link); text-decoration: none; cursor: pointer; border-radius: var(--radius-tag); }
        .link svg { width: var(--icon-sm); height: var(--icon-sm); stroke-width: var(--icon-stroke-s); }
        .link:hover, .link:active { color: var(--text-link-hover); }
```

- [ ] **Step 7: The menu's old shadow leaves, and the guards that pinned it**

The menu was the one reader of `--shadow-md`; with it on the pop shadow the token would be defined and never read (`t_every_defined_token_is_read`). In `:root` replace `            --shadow-md: var(--shadow-pop); --shadow-lg: var(--shadow-pop);` with `            --shadow-lg: var(--shadow-pop);`.

In `t_the_ink_frame_the_measures_and_the_shadows_are_tokens` replace `        "shadow-md": "var(--shadow-pop)", "shadow-lg": "var(--shadow-pop)",` with `        "shadow-lg": "var(--shadow-pop)",`. In `t_the_card_elevation_token_actually_paints` replace `    for tok in ("--shadow-md", "--shadow-lg"):` with `    for tok in ("--shadow-lg",):` (as Task 3 left it, so a missing token cannot reach `.group(1)` on nothing).

In `t_the_menu_and_tabs_are_the_reference_measurements` replace:

```python
    panel = CSS.split(".dmenu {")[1].split("}")[0]
    ok("border-radius: var(--radius-card)" in panel, "the panel takes the card's corner")
    ok("padding: var(--sp-1)" in panel, "padded 4px")
    ok("var(--shadow-md)" in panel, "its edge is a ring, not a border")
    ok("border:" not in panel, "and it has no border at all")
```

with:

```python
    panel = CSS.split(".dmenu {")[1].split("}")[0]
    ok("border-radius: var(--radius-pop)" in panel, "the panel takes the floating corner (the mix: 10)")
    ok("padding: var(--menu-pad)" in panel, "padded 4px")
    ok("var(--shadow-pop)" in panel, "its edge is the pop shadow's ring, not a border")
    ok("border:" not in panel, "and it has no border at all")
```

- [ ] **Step 8: Run the tests**

Run: `ONLY=t_an_explanation_waits python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `433 passed, 0 failed`.

- [ ] **Step 9: Prove it in the page**

In the rig's console on any page run:

```js
document.querySelector('.view.active .ov-hero h2').append(infoButton('About this page', { title: 'A test', body: ['One.', 'Two.'], guide: ['money', ''] }));
```

Press the new glyph: a white popover with a 10 corner opens 8 under it with "A test", two lines and "More in the Guide"; Escape closes it and focus returns to the glyph; Tab to it and press Enter: it opens again. Reload with `?fresh=12`.

- [ ] **Step 10: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Parts: an info button that opens a popover with the moved words and More in the Guide; menus open 8 from their trigger

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Menus and How it works

**Files:**
- Modify: `static/index.html:3929-3947` (`.dmenu-item`, `.dmenu-sep`, `.dmenu-label`), `dropMenu` (7105), the script after `infoButton` (Task 12)
- Test: `tests/test_frontend.py` (`t_the_menu_and_tabs_are_the_reference_measurements` 2936, `t_a_dropdown_menu_can_always_be_got_out_of` 2911, a new test)

**Interfaces:**
- Consumes: `dropMenu(anchor, items)`, `openGuideAt`, `I.helpCircle`, `I.arrowRight`, `.cnt` (Task 10).
- Produces: a menu row is 32 (40 on a phone, Task 24) with a 6 corner, a 16 icon in ink-3 12 from its words; `dropMenu` items take `n` (a count at the row's end) and `link: true` (a teal row with an arrow, for "... in the Guide"). `howItWorks(items, guide)` returns the header button "How it works" (`btn`, `I.helpCircle`) whose menu lists a screen's method pages: `items` are `{ icon, label, n, onClick }`; `guide` is `{ label, at: [sectionId, query] }` and becomes the final link after a rule.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_a_screens_method_pages_sit_in_one_how_it_works_menu():
    """Spec 6: one header button holds a screen's method pages as a menu; it
    replaces Forecast's "How this forecast works" section. A menu row is 32
    with a 6 corner, a 16 icon 12 from its words and a count at its end; the
    last row, after a rule, is the Guide's link."""
    ok("function howItWorks(items, guide) {" in SCRIPT, "the builder exists")
    fn = fn_src("function howItWorks(items, guide) {")
    for part in ("el('button', 'btn')", "ico(I.helpCircle)", "'How it works'", "dropMenu(b, ", "'-'", "link: true"):
        ok(part in fn, "howItWorks: " + part)
    dm = fn_src("function dropMenu(")
    ok("if (it.n != null) b.append(el('span', 'cnt', String(it.n)));" in dm, "a menu row can carry a count")
    ok("if (it.link) { b.classList.add('dmenu-link'); b.append(ico(I.arrowRight)); }" in dm, "and the Guide's row is a link")
    item = CSS.split("\n        .dmenu-item {")[1].split("}")[0]
    for prop in ("min-height: var(--control-h)", "gap: var(--gap-row-icon)", "border-radius: var(--radius-row)", "font-size: var(--text-body)"):
        ok(prop in item, ".dmenu-item: " + prop)
    ok(".dmenu-item .cnt { margin-left: auto; padding-left: var(--sp-2); }" in CSS, "the count sits at the row's end")
    ok(".dmenu-link { color: var(--text-link); }" in CSS, "the Guide's row is teal words")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_a_screens_method_pages python3 tests/test_frontend.py`
Expected: `FAIL  t_a_screens_method_pages_sit_in_one_how_it_works_menu: the builder exists`

- [ ] **Step 3: The menu row**

Replace:

```css
        .dmenu-item { display: flex; align-items: center; gap: var(--sp-1-5); width: 100%;
            height: 28px; padding: var(--sp-1) var(--sp-7) var(--sp-1) var(--sp-1-5); border: 0; background: none;
            border-radius: calc(var(--radius-card) - var(--sp-1)); font: inherit; font-size: var(--text-sm);
            color: var(--text-primary); text-align: left; cursor: pointer; white-space: nowrap; }
        .dmenu-item:hover { background: var(--surface-tertiary); }
        .dmenu-item:active { background: var(--surface-sunken); }
```

with:

```css
        /* A menu row is a nav row (the mix, spec 6): 32 tall, a 6 corner, a 16
           icon in ink-3 12 from its words, a count at its end; 32 clear on the
           right for a tick, so a list of choices does not jump when one is made. */
        .dmenu-item { display: flex; align-items: center; gap: var(--gap-row-icon); width: 100%;
            min-height: var(--control-h); padding: 0 var(--sp-7) 0 var(--sp-2); border: 0; background: none;
            border-radius: var(--radius-row); font: inherit; font-size: var(--text-body); line-height: var(--lh-control);
            color: var(--text-primary); text-align: left; cursor: pointer; white-space: nowrap; }
        .dmenu-item:hover { background: var(--surface-tertiary); }
        .dmenu-item:active { background: var(--press); }
        .dmenu-item .cnt { margin-left: auto; padding-left: var(--sp-2); }
        .dmenu-link { color: var(--text-link); }
        .dmenu-link .ic { color: inherit; }
        .dmenu-link svg { width: var(--icon-sm); height: var(--icon-sm); stroke-width: var(--icon-stroke-s); }
```

Replace `        .dmenu-sep { height: 1px; background: var(--border-default); margin: var(--sp-1) var(--sp-1-5); }` with:

```css
        .dmenu-sep { height: 1px; background: var(--border-default); margin: var(--sp-1) var(--sp-2); }
```

Replace `        .dmenu-label { padding: var(--sp-1-5) var(--sp-1-5) var(--sp-0-5); font-size: var(--text-xs); color: var(--text-tertiary); }` with:

```css
        .dmenu-label { padding: var(--sp-2) var(--sp-2) var(--sp-1); font-size: var(--text-xs); line-height: var(--lh-caption); color: var(--text-tertiary); }
```

- [ ] **Step 4: Counts and the link row in dropMenu**

In `dropMenu` replace:

```js
                if (it.icon) b.append(ico(it.icon));
                b.append(el('span', null, it.label));
```

with:

```js
                if (it.icon) b.append(ico(it.icon));
                b.append(el('span', null, it.label));
                if (it.n != null) b.append(el('span', 'cnt', String(it.n)));
                if (it.link) { b.classList.add('dmenu-link'); b.append(ico(I.arrowRight)); }
```

and add to the comment above `let dmenuOpen` that items take `n` (a count) and `link` (a teal row with an arrow).

- [ ] **Step 5: The builder**

Directly after `infoButton` add:

```js
        /* How it works (the mix, spec 6): one header button holding a screen's
           method pages as a menu, the Guide's link last after a rule. items:
           [{ icon, label, n, onClick }]; guide: { label, at: [section id, search] }. */
        function howItWorks(items, guide) {
            const b = el('button', 'btn');
            b.type = 'button';
            b.append(ico(I.helpCircle), document.createTextNode('How it works'));
            b.setAttribute('aria-haspopup', 'menu'); b.setAttribute('aria-expanded', 'false');
            b.onclick = () => dropMenu(b, items.concat(guide ? ['-', { label: guide.label, link: true,
                onClick: () => openGuideAt(guide.at[0], guide.at[1] || '') }] : []));
            return b;
        }
```

- [ ] **Step 6: Update the menu guard**

In `t_the_menu_and_tabs_are_the_reference_measurements` (its panel lines are Task 12's) replace:

```python
    item = CSS.split(".dmenu-item {")[1].split("}")[0]
    ok("height: 28px" in item, "items are 28px")
    ok("padding: var(--sp-1) var(--sp-7) var(--sp-1) var(--sp-1-5)" in item, "with room on the right for a tick")
    ok("border-radius: calc(var(--radius-card) - var(--sp-1))" in item, "concentric inside the padded menu")
```

with:

```python
    item = CSS.split(".dmenu-item {")[1].split("}")[0]
    ok("min-height: var(--control-h)" in item, "items are 32px, a nav row")
    ok("padding: 0 var(--sp-7) 0 var(--sp-2)" in item, "with room on the right for a tick")
    ok("border-radius: var(--radius-row)" in item, "at the row corner, 6 inside the 10 with its 4 padding")
```

In `t_a_dropdown_menu_can_always_be_got_out_of` replace `    fn = SCRIPT.split("function dropMenu(anchor, items) {")[1][:3800]` with `    fn = fn_src("function dropMenu(anchor, items) {")` (the whole function: the rows' counts and link lines above push its scroll handler past a fixed 3,800-character window).

- [ ] **Step 7: Run the tests**

Run: `ONLY=t_a_screens_method_pages python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `434 passed, 0 failed`.

- [ ] **Step 8: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Parts: 32 menu rows with counts and a Guide link row, and a How it works button that holds a screen's method pages

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: The figure row and the change chip

**Files:**
- Modify: `static/index.html:765-861` (`.metrics`, `.stat`, the label, figure, note and the old direction tints), `:971-1086` (the strip's tiles inside cards, the picked tile), `:4129-4131` (`.cd`), `:4949-4958` (ONE TAG's list), the icon table, `statCard` (5933), `chartHead` (7867)
- Test: `tests/test_frontend.py` (`t_a_rising_number_is_not_congratulated_in_green` 3669, `t_the_kpi_card_keeps_the_hierarchy_the_reference_measures` 3616, `t_a_kpi_with_a_list_behind_it_opens_it` 2172, a new test)

**Interfaces:**
- Consumes: `--fig-m`, `--fig-s`, `--tr-fig`, `--gap-fig`, `--success`, `--error`.
- Produces: `I.arrowDownRight`; `deltaTone(label, trend, better)` returns `'good'`, `'bad'` or `'flat'` (a rise is bad for the labels in `RISE_IS_BAD`; `better: 'down'` or `'up'` overrides); `changeChip(trend, text, tone)` returns `span.delta.<trend>.<tone>` holding the arrow (`I.arrowUpRight` or `I.arrowDownRight`), a hidden "up " or "down " and the text. Every figure is unboxed: label (13 at 500, ink-2), figure (28 at 600, tabular, -0.03em, 24 on a phone), chip beside it, a note under it; a row of figures is split by hairlines.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_figures_stand_in_a_row_split_by_hairlines():
    """Spec 6 and 4.2: figures in one row split by hairlines, no box: the label
    above (13 at 500 in ink-2), the figure (Inter 600 at 28, tabular, tracked
    -0.03em, on a line of 1), the change chip 12 beside it, a note under it.
    The first figure of each row starts on the text edge."""
    st = CSS.split("\n        .stat {")[1].split("}")[0]
    for prop in ("background: none", "border: 0", "padding: 0", "gap: var(--gap-fig)"):
        ok(prop in st, ".stat: " + prop)
    lab = CSS.split(".stat .label {")[1].split("}")[0]
    ok("font-size: var(--text-body)" in lab and "color: var(--text-secondary)" in lab and "font-weight: var(--weight-medium)" in lab,
       "the label is 13 at 500 in ink-2")
    val = CSS.split(".stat .value {")[1].split("}")[0]
    for prop in ("font-size: var(--fig-m)", "font-weight: var(--weight-semibold)", "letter-spacing: var(--tr-fig)",
                 "line-height: var(--lh-none)", "font-variant-numeric: tabular-nums"):
        ok(prop in val, "the figure: " + prop)
    row = CSS.split("\n        .metrics {")[1].split("}")[0]
    ok("overflow: clip" in row and "column-gap: var(--sp-8)" in row, "a row clips the hairline its first figure draws outside it")
    rule = CSS.split("\n        .metrics > .stat::before {")[1].split("}")[0]
    ok("left: calc(-0.5 * var(--sp-8))" in rule and "background: var(--border-default)" in rule and "width: var(--bw-hairline)" in rule,
       "each figure draws its hairline in the middle of the gap before it")
    ok(".card .metrics-strip > .stat { border-color: transparent;" not in CSS, "no tinted tile inside a section")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_figures_stand_in_a_row python3 tests/test_frontend.py`
Expected: `FAIL  t_figures_stand_in_a_row_split_by_hairlines: .stat: background: none`

- [ ] **Step 3: The row and the figure**

Replace:

```css
        .metrics { display: grid; gap: var(--sp-4); margin-bottom: var(--sp-6);
            grid-template-columns: repeat(4, minmax(0, 1fr)); }
```

with:

```css
        /* THE FIGURE ROW (the mix, spec 6): figures in one row split by
           hairlines, no boxes. Each figure draws its hairline in the middle of
           the gap before it; the first figure of a row draws it outside the
           row, where the row clips it away, so every row starts on the text
           edge however it wraps. The clip margin keeps a focus ring whole. */
        .metrics { display: grid; column-gap: var(--sp-8); row-gap: var(--sp-6); margin-bottom: var(--sp-6);
            grid-template-columns: repeat(4, minmax(0, 1fr)); overflow: clip; overflow-clip-margin: var(--sp-1); }
        .metrics > .stat::before { content: ""; position: absolute; top: 0; bottom: 0; left: calc(-0.5 * var(--sp-8));
            width: var(--bw-hairline); background: var(--border-default); }
```

Replace:

```css
        .stat { position: relative; overflow: hidden; background: var(--surface-primary); border: var(--bw-hairline) solid var(--border-default); border-radius: var(--radius-card);
            padding: var(--sp-4); box-shadow: var(--shadow-sm); animation: fadeUp .4s ease backwards;
            display: flex; flex-direction: column; align-items: stretch; gap: var(--sp-1);
            min-height: 154px; justify-content: flex-start; }
```

with:

```css
        .stat { position: relative; overflow: visible; background: none; border: 0; border-radius: 0;
            padding: 0; box-shadow: none; animation: fadeUp .4s ease backwards;
            display: flex; flex-direction: column; align-items: stretch; gap: var(--gap-fig);
            min-height: 0; justify-content: flex-start; }
        /* A figure the widget grid places on its own (Overview's) leads with
           the hairline it would have drawn in a row. */
        .ov-wrap.wgrid > .stat[data-widget] { box-shadow: inset var(--bw-hairline) 0 0 var(--border-default); padding-left: var(--sp-4); }
```

Replace:

```css
        .stat-ic { width: var(--box-lg); height: var(--box-lg); flex: none; border-radius: var(--radius-inset);
            border: var(--bw-hairline) solid var(--border-default); background: var(--surface-tertiary); color: var(--text-tertiary);
            display: grid; place-items: center; }
```

with:

```css
        /* No icon tile on a figure (the mix): the label names it. */
        .stat-ic { display: none; }
```

Replace `        .stat .label { font-size: var(--text-sm); color: var(--text-tertiary); font-weight: var(--weight-regular); text-transform: none; letter-spacing: normal; margin-bottom: var(--sp-3); position: relative; }` with:

```css
        .stat .label { font-size: var(--text-body); line-height: var(--lh-control); color: var(--text-secondary); font-weight: var(--weight-medium); text-transform: none; letter-spacing: normal; margin-bottom: 0; position: relative; }
```

Replace `        .stat-row { display: flex; align-items: center; gap: var(--sp-2); flex-wrap: wrap; }` with:

```css
        .stat-row { display: flex; align-items: center; gap: var(--gap-fig); flex-wrap: wrap; }
```

Replace:

```css
        .stat .value { font-size: var(--text-3xl); font-weight: var(--weight-medium); letter-spacing: -.025em; line-height: var(--lh-none); position: relative; }
        .stat .delta { display: inline-flex; align-items: center; gap: var(--sp-1); font-size: var(--text-xs); font-weight: var(--weight-medium); margin-top: 0; padding: var(--sp-0-5) var(--sp-2); border-radius: var(--radius-tag); position: relative; flex: none; line-height: var(--lh-snug); }
```

with:

```css
        .stat .value { font-size: var(--fig-m); font-weight: var(--weight-semibold); letter-spacing: var(--tr-fig); line-height: var(--lh-none); font-variant-numeric: tabular-nums; position: relative; }
```

Replace `        .stat-note { margin: var(--sp-2) 0 0; font-size: var(--text-sm); line-height: var(--lh-control); color: var(--text-tertiary); }` with:

```css
        .stat-note { margin: 0; font-size: var(--text-xs); line-height: var(--lh-caption); color: var(--text-tertiary); }
```

Delete `        .stat .delta svg { width: var(--icon-xs); height: var(--icon-xs); }`.

Replace:

```css
        .delta.up { color: var(--text-primary); background: var(--surface-sunken); } .delta.down { color: var(--error); background: var(--error-bg); }
        /* In a tile whose figure is amber, a fall is amber too: an amber
           figure beside a red pill said two different things. */
        .stat.warn .delta.down { color: var(--warning); background: var(--warning-bg); } .delta.flat { color: var(--text-tertiary); background: var(--surface-sunken); }
```

with:

```css
        /* In a tile whose figure is amber, a bad change is amber too: an amber
           figure beside a red chip said two different things. */
        .stat.warn .delta.bad { color: var(--warning); background: var(--warning-bg); }
```

In the strip rules replace:

```css
        .metrics-strip .stat .label { color: var(--text-primary); margin-bottom: var(--sp-4); }
        .metrics-strip .stat .value { font-size: var(--text-2xl); font-weight: var(--weight-regular); }
        .metrics-strip .stat .value.unknown { font-size: var(--text-md); }
        .metrics-strip .stat-note { font-size: var(--text-xs); }
```

with:

```css
        .metrics-strip .stat .value.unknown { font-size: var(--text-body); }
```

Delete `        .card .metrics-strip > .stat { border-color: transparent; background: var(--surface-secondary); }` and the comment line above it.

In the subgrid rule replace `            grid-template-columns: minmax(0, 1fr); row-gap: var(--sp-1); align-content: start; }` with `            grid-template-columns: minmax(0, 1fr); row-gap: var(--gap-fig); align-content: start; }`.

Replace `        .stat .value.unknown { font-size: var(--text-md); font-weight: var(--weight-regular);` with `        .stat .value.unknown { font-size: var(--text-body); font-weight: var(--weight-regular);`.

Replace the picked and opening tile rules:

```css
        .stat.stat-pick:hover { border-color: var(--border-strong); }
        .stat.stat-pick:is(.on, [aria-pressed="true"]) { border-color: var(--border-selected);
            box-shadow: var(--ring-action), var(--shadow-sm); }
```

with:

```css
        /* A figure that filters the list under it is chosen the way a counter
           is: its label and figure in ink, a teal-line bar under the label. */
        .stat.stat-pick:is(.on, [aria-pressed="true"]) .label { color: var(--text-primary); }
        .stat.stat-pick:is(.on, [aria-pressed="true"]) .label::after { content: ""; position: absolute; left: 0; right: 0; bottom: calc(-1 * var(--sp-1));
            height: var(--bw-strong); border-radius: var(--radius-swatch); background: var(--fill-mark); }
```

and replace `        .stat.stat-open:hover, .stat.stat-pick:hover { border-color: var(--border-strong); background: var(--surface-secondary); }` with:

```css
        .stat.stat-open:hover .label, .stat.stat-pick:hover .label { color: var(--text-primary); }
```

and replace `        .metrics-strip .stat.stat-pick:is(.on, [aria-pressed="true"]) { box-shadow: var(--ring-action-2); }` with nothing (delete it).

A phone figure is one step down. The `.metrics` phone block sits above the base `.stat .value` rule, where an equally specific rule would lose the cascade (and the guard above reads the first `.stat .value {` block), so the phone size goes directly after the new base rule instead. Directly after `        .stat .value { font-size: var(--fig-m); font-weight: var(--weight-semibold); letter-spacing: var(--tr-fig); line-height: var(--lh-none); font-variant-numeric: tabular-nums; position: relative; }` add:

```css
        @media (max-width: 640px) { .stat .value { font-size: var(--fig-s); } }
```

- [ ] **Step 4: The change chip**

In `const I = {` after `            arrowRight: SV(` add:

```js
            arrowDownRight: SV('<path d="m7 7 10 10"></path><path d="M17 7v10H7"></path>'),
```

In the ONE TAG list replace `.mcount, .mail-crmchip, .crm-badge, .resp-head .tag, .stat .delta, .prod-chip .cmp, .chart-head .cd) {` with `.mcount, .mail-crmchip, .crm-badge, .resp-head .tag, .delta, .prod-chip .cmp) {`, and in the svg list after it replace `            .stat .delta, .prod-chip .cmp, .chart-head .cd) svg { width: var(--icon-xs); height: var(--icon-xs); }` with `            .delta, .prod-chip .cmp) svg { width: var(--icon-xs); height: var(--icon-xs); }`.

Directly after that svg rule add:

```css
        /* THE CHANGE CHIP (the mix, spec 6): a 20 tag, the arrow and the
           percentage at 600, tinted by what the change means (green good, red
           bad, the fill when flat), "up" or "down" said to a screen reader.
           Never colour alone: the arrow carries the direction. */
        .delta:is(.up, .down, .flat) { gap: var(--sp-0-5); padding: 0 var(--sp-2) 0 var(--sp-1); font-weight: var(--weight-semibold);
            line-height: var(--lh-caption); font-variant-numeric: tabular-nums; }
        .delta:is(.up, .down, .flat) svg { width: var(--icon-sm); height: var(--icon-sm); stroke-width: var(--icon-stroke-s); }
        .delta.flat { padding-left: var(--sp-2); color: var(--text-tertiary); background: var(--surface-tertiary); }
        .delta.good { color: var(--success); background: var(--success-bg); }
        .delta.bad { color: var(--error); background: var(--error-bg); }
        .chart-head .delta { margin-left: var(--sp-2); }
```

Delete the `.chart-head .cd` rules:

```css
        .chart-head .cd { display: inline-flex; align-items: center; gap: var(--sp-1); font-size: var(--text-xs); font-weight: var(--weight-medium); padding: var(--sp-0-5) var(--sp-2); border-radius: var(--radius-tag); margin-left: var(--sp-2); flex: none; line-height: var(--lh-snug); }
        .chart-head .cd > span { display: grid; place-items: center; } .chart-head .cd svg { width: var(--icon-xs); height: var(--icon-xs); display: block; }
        .cd.up { color: var(--text-primary); background: var(--surface-sunken); } .cd.down { color: var(--error); background: var(--error-bg); } .cd.flat { color: var(--text-tertiary); background: var(--surface-sunken); }
```

Directly before `        function statCard(m, i) {` add:

```js
        /* A change is coloured by what it means, not by its direction (the
           mix, spec 6, keeping the 2026-09 rule that a rising number is not
           congratulated by reflex): green when the move is good for the shop,
           red when it is bad. A rise is bad news for these. */
        const RISE_IS_BAD = ['unfulfilled', 'low stock', 'at risk', 'position', 'cpc', 'ad spend', 'overdue', 'failed', 'quarantined', 'owed', 'outstanding'];
        function deltaTone(label, trend, better) {
            if (trend !== 'up' && trend !== 'down') return 'flat';
            const l = String(label || '').toLowerCase();
            const riseBad = better === 'down' || (better !== 'up' && RISE_IS_BAD.some(k => l.includes(k)));
            return (trend === 'up') !== riseBad ? 'good' : 'bad';
        }
        function changeChip(trend, text, tone) {
            const t = trend === 'up' || trend === 'down' ? trend : 'flat';
            const d = el('span', 'delta ' + t + ' ' + (tone || 'flat'));
            if (t === 'up') d.append(ico(I.arrowUpRight)); else if (t === 'down') d.append(ico(I.arrowDownRight));
            if (t !== 'flat') d.append(el('span', 'sr-only', t === 'up' ? 'up ' : 'down '));
            d.append(document.createTextNode(text));
            return d;
        }
```

In `statCard` replace:

```js
            if (m.delta) {
                const d = el('div', 'delta ' + (m.trend || 'flat'));
                if (m.trend === 'up') d.append(ico(I.up)); else if (m.trend === 'down') d.append(ico(I.down));
                d.append(document.createTextNode(m.delta));
                row.append(d);
            }
```

with:

```js
            if (m.delta) row.append(changeChip(m.trend, m.delta, deltaTone(m.label, m.trend, m.better)));
```

In `chartHead` replace:

```js
                if (opts.delta) { const d = el('span', 'cd ' + (opts.trend || 'flat')); if (opts.trend === 'up') d.append(ico(I.up)); else if (opts.trend === 'down') d.append(ico(I.down)); d.append(document.createTextNode(opts.delta)); v.append(d); }
```

with:

```js
                if (opts.delta) v.append(changeChip(opts.trend, opts.delta, deltaTone(opts.title, opts.trend, opts.better)));
```

- [ ] **Step 5: Update the guards**

Replace the whole body of `t_a_rising_number_is_not_congratulated_in_green` (docstring and every line) with:

```python
    """gizmo paints metrics where a rise is bad news - unfulfilled orders,
    at-risk customers - so a green "up" there reads as approval of a number the
    merchant needs to worry about. Since the mix (2026-10-06, spec 6) a change
    chip is green or red, but by what the change MEANS, never by its direction
    alone: the arrow and a hidden word carry the direction."""
    ok("function deltaTone(label, trend, better) {" in SCRIPT, "a change's tone is worked out, not read off its direction")
    bad = SCRIPT.split("const RISE_IS_BAD = [")[1].split("]")[0]
    for k in ("'unfulfilled'", "'at risk'", "'position'", "'overdue'"):
        ok(k in bad, "a rise in " + k + " is bad news, so it is not green")
    ok("changeChip(m.trend, m.delta, deltaTone(m.label, m.trend, m.better))" in SCRIPT, "the KPI chip asks")
    ok(not re.search(r"\.delta\.up \{[^}]*var\(--success\)", CSS), "no rule paints a rise green because it is a rise")
    good = CSS.split("\n        .delta.good {")[1].split("}")[0]
    ok("color: var(--success)" in good and "background: var(--success-bg)" in good, "a good change is the green pair")
    worse = CSS.split("\n        .delta.bad {")[1].split("}")[0]
    ok("color: var(--error)" in worse and "background: var(--error-bg)" in worse, "a bad one the red pair")
    for sel in (r"\.prod-chip \.cmp\.up",):
        rule = re.search(sel + r" \{[^}]*\}", CSS)
        ok(rule and "var(--success)" not in rule.group(0), "the product comparison chip spends no green on direction either")
```

Replace the body of `t_the_kpi_card_keeps_the_hierarchy_the_reference_measures` (its docstring stays; the lines from `    lab = CSS.split(".stat .label {")` to the end) with:

```python
    # The mix (2026-10-06, spec 4.2 and 6): the label is 13 at 500 in ink-2,
    # the figure Inter 600 at 28 on a line of 1, the note a caption.
    lab = CSS.split(".stat .label {")[1].split("}")[0]
    ok("font-size: var(--text-body)" in lab, "the label is the body's 13")
    ok("color: var(--text-secondary)" in lab, "in ink-2, a step under the figure")
    val = CSS.split(".stat .value {")[1].split("}")[0]
    ok("font-size: var(--fig-m)" in val, "the number is the 28 figure")
    ok("font-weight: var(--weight-semibold)" in val, "at 600")
    note = re.search(r"^\s*\.stat-note \{([^}]*)\}", CSS, re.M).group(1)
    ok("font-size: var(--text-xs)" in note, "and the sub-line is a caption")
```

In `t_a_kpi_with_a_list_behind_it_opens_it` replace:

```python
    ok(".stat.stat-open:hover, .stat.stat-pick:hover { border-color: var(--border-strong); background: var(--surface-secondary); }" in CSS,
       "and the reference's row hover")
```

with:

```python
    ok(".stat.stat-open:hover .label, .stat.stat-pick:hover .label { color: var(--text-primary); }" in CSS,
       "and under the pointer its label darkens (the mix: a figure has no box to tint)")
```

- [ ] **Step 6: Run the tests**

Run: `ONLY=t_figures_stand_in_a_row python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `435 passed, 0 failed`.

- [ ] **Step 7: Look at it**

Loan units and Xero sync at 1440: their figures sit in a row with hairlines between them and none before the first; labels in ink-2, figures 28 at 600. Overview (run it): Revenue up shows a green chip with an up-right arrow; Unfulfilled up shows red.

- [ ] **Step 8: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Parts: figures in a row split by hairlines, 28 at 600; a change chip tinted by what the change means, with an arrow

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: The feature band

**Files:**
- Modify: the stylesheet after the figure row rules (after `.metrics-strip .stat-note` area, before `.fc-alert`), the script after `changeChip` (Task 14), the icon table
- Test: `tests/test_frontend.py` (a new test with a node harness)

**Interfaces:**
- Consumes: `--band-bg`, `--band-rule`, `--rule-t-band`, `--radius-band`, the measure tokens (Task 3), `changeChip`, `infoButton`, `I.trendUp`, `I.flag`.
- Produces: `I.wallet`; `bandDomain(values)` returns `{ min, max }`, the round span around the values in steps of the largest power of ten under the top value; `bandPct(v, d)` returns a percentage string with one decimal, clamped 0 to 100; `rangeBar(r)` returns `div.fb-range` for `r = { lo, hi, exp, plan, d, planLabel, loLabel, hiLabel, midLabel }`; `meter(m)` returns `div.fb-meter` for `m = { taken: pct, plan: pct }` (numbers 0 to 100); `featureBand(o)` returns `section.fband` for `o = { main: { icon, label, info, value, chip, note, range }, sides: [{ icon, label, value, chip, note, meter }] }`. Bar positions are custom properties set by `style.setProperty` (percentages only).

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_the_feature_band_draws_the_main_question():
    """Spec 6: one per screen at most, for its main question (Forecast:
    expected this month). A soft teal gradient with a 12 corner: the hero
    figure at 44 with its chip, the likely range as one bar with the plan as a
    blue tick, and side figures stacked, each a 28 tile, a figure and a meter.
    Bar positions are data percentages, the one style the markup carries; the
    domain is the round span around the values (the mockup's 30,000 to 70,000)."""
    for name in ("function bandDomain(vals) {", "function rangeBar(r) {", "function meter(m) {", "function featureBand(o) {"):
        ok(name in SCRIPT, "the builder exists: " + name)
    band = CSS.split("\n        .fband {")[1].split("}")[0]
    ok("background: var(--band-bg)" in band and "border-radius: var(--radius-band)" in band, "the band is the teal gradient, 12 round")
    ok("font-size: var(--fig-xl)" in CSS.split("\n        .fb-hero .fb-fig {")[1].split("}")[0], "the hero figure is 44")
    fill = CSS.split("\n        .fb-fill {")[1].split("}")[0]
    ok("background: var(--c-range)" in fill and "inset 0 0 0 var(--bw-hairline) var(--c-range-edge)" in fill, "the range is teal-glow with a teal-line edge")
    ok("background: var(--c-plan)" in CSS.split("\n        .fb-plan {")[1].split("}")[0], "the plan is a blue tick")
    ok("background: var(--c-exp)" in CSS.split("\n        .fb-exp {")[1].split("}")[0], "the expected point is an ink dot")
    fr = fn_src("function rangeBar(r) {")
    ok("style.setProperty('--at-lo', bandPct(r.lo, r.d))" in fr and ".style.left" not in fr, "positions are percentages in custom properties")
    if not _node_ok():
        print("       (node unavailable, harness skipped)")
        return
    js = "\n".join((SCRIPT[SCRIPT.index("        function bandDomain(vals) {"):SCRIPT.index("        function rangeBar(r) {")],
                    "const d = bandDomain([41327, 66054, 53691, 37566]);",
                    "const m = bandDomain([41327, 66054, 37566, 53691, 24180, 39960, 38750, 34690, 55980, 35860]);",
                    "console.log(JSON.stringify([d, ['lo', 41327, 'hi', 66054, 'exp', 53691, 'plan', 37566].filter((x, i) => i % 2).map(v => bandPct(v, d)), m, bandPct(41327, m), bandPct(-5, d), bandPct(1e9, d)]));"))
    out = _run_node(js)
    eq(out[0], {"min": 30000, "max": 70000}, "the band's domain")
    eq(out[1], ["28.3%", "90.1%", "59.2%", "18.9%"], "where the bar's marks fall (the mockup's own)")
    eq(out[2], {"min": 20000, "max": 70000}, "one scale across the mini bars")
    eq(out[3], "42.7%", "a mini bar's low end")
    eq([out[4], out[5]], ["0.0%", "100.0%"], "a mark never leaves its track")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_the_feature_band python3 tests/test_frontend.py`
Expected: `FAIL  t_the_feature_band_draws_the_main_question: the builder exists: function bandDomain(vals) {`

- [ ] **Step 3: The icon**

In `const I = {` after `            arrowDownRight: SV(` add:

```js
            wallet: SV('<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"></path><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"></path>'),
```

- [ ] **Step 4: The builders**

Directly after `changeChip` add:

```js
        /* A bar's domain: the round span around every value it shows, in steps
           of the largest power of ten under the top value (41,327 to 66,054
           with a plan of 37,566 is drawn on 30,000 to 70,000). */
        function bandDomain(vals) {
            const v = vals.filter(x => x != null && isFinite(x)).map(Number);
            if (!v.length) return { min: 0, max: 1 };
            const top = Math.max.apply(null, v), bot = Math.min.apply(null, v);
            const step = Math.pow(10, Math.floor(Math.log10(Math.max(1, Math.abs(top)))));
            const min = Math.floor(bot / step) * step, max = Math.ceil(top / step) * step;
            return { min, max: max > min ? max : min + step };
        }
        const bandPct = (v, d) => Math.max(0, Math.min(100, (v - d.min) / (d.max - d.min) * 100)).toFixed(1) + '%';
        /* The likely range as one bar (the mix, spec 6): a teal-glow fill with
           a teal-line edge from low to high, an ink dot at the expected figure,
           the plan as a blue tick with its label above, the ends and "Likely
           range" under. r: { lo, hi, exp, plan, d, planLabel, loLabel, hiLabel, midLabel } */
        function rangeBar(r) {
            const w = el('div', 'fb-range');
            w.style.setProperty('--at-lo', bandPct(r.lo, r.d)); w.style.setProperty('--at-hi', bandPct(r.hi, r.d));
            w.style.setProperty('--at-exp', bandPct(r.exp, r.d));
            if (r.plan != null) w.style.setProperty('--at-plan', bandPct(r.plan, r.d));
            const track = el('div', 'fb-track');
            track.append(el('div', 'fb-fill'));
            if (r.plan != null) track.append(el('div', 'fb-plan'));
            track.append(el('div', 'fb-exp'));
            if (r.plan != null && r.planLabel) w.append(el('span', 'fb-rl t', r.planLabel));
            w.append(track);
            [[r.lo, r.loLabel, ''], [r.exp, r.midLabel, ' mid'], [r.hi, r.hiLabel, '']].forEach(([v, t, c]) => {
                if (!t) return;
                const s = el('span', 'fb-rl b' + c, t); s.style.setProperty('--at', bandPct(v, r.d)); w.append(s);
            });
            return w;
        }
        /* A meter: what is taken in the measure's dark teal, what is still
           expected after it at 45%, the plan as a blue tick. m: { taken, plan }
           in percent of the bar. */
        function meter(m) {
            const w = el('div', 'fb-meter');
            const t = Math.max(0, Math.min(100, m.taken || 0)).toFixed(1) + '%';
            w.style.setProperty('--w', t); w.style.setProperty('--at', t);
            w.append(el('i', 'taken'), el('i', 'still'));
            if (m.plan != null) { w.style.setProperty('--at-plan', Math.max(0, Math.min(100, m.plan)).toFixed(1) + '%'); w.append(el('i', 'plan')); }
            w.setAttribute('aria-hidden', 'true');
            return w;
        }
        /* The feature band (the mix, spec 6): one per screen at most, for its
           main question. o: { main: { icon, label, info, value, chip, note,
           range }, sides: [{ icon, label, value, chip, note, meter }] }. */
        function featureBand(o) {
            const band = el('section', 'fband');
            const head = (f) => {
                const h = el('div', 'fb-head');
                const t = el('span', 'fb-tile'); t.setAttribute('aria-hidden', 'true'); t.append(ico(f.icon)); h.append(t);
                h.append(el('span', 'fb-label', f.label));
                if (f.info) h.append(f.info);
                return h;
            };
            const main = el('div', 'fb-main');
            main.append(head(o.main));
            const hero = el('div', 'fb-hero');
            hero.append(el('b', 'fb-fig', o.main.value));
            if (o.main.chip) hero.append(o.main.chip);
            if (o.main.note) hero.append(el('span', 'fb-note', o.main.note));
            main.append(hero);
            if (o.main.range) main.append(o.main.range);
            band.append(main);
            if (o.sides && o.sides.length) {
                const rule = el('div', 'fb-rule'); rule.setAttribute('aria-hidden', 'true'); band.append(rule);
                const sides = el('div', 'fb-sides');
                o.sides.forEach(s => {
                    const box = el('div', 'fb-side');
                    box.append(head(s));
                    const num = el('div', 'fb-num');
                    num.append(el('b', 'fb-fig', s.value));
                    if (s.chip) num.append(s.chip);
                    if (s.note) num.append(el('span', 'fb-note', s.note));
                    box.append(num);
                    if (s.meter) box.append(s.meter);
                    sides.append(box);
                });
                band.append(sides);
            }
            return band;
        }
```

- [ ] **Step 5: The band's rules**

Directly before the rule that begins `        .fc-alert { display: flex; align-items: baseline;` add:

```css
        /* THE FEATURE BAND (the mix, spec 6): one per screen at most, for its
           main question. A soft teal gradient with the band's 12 corner; the
           main figure and its range on the left, a 1px rule, the side figures
           stacked on the right. Bar positions arrive as percentages in custom
           properties (--at-lo, --at-hi, --at-exp, --at-plan, --at, --w). */
        .fband { border-radius: var(--radius-band); background: var(--band-bg); padding: var(--sp-6) var(--sp-7);
            display: grid; grid-template-columns: minmax(0, 1.6fr) var(--bw-hairline) minmax(0, 1fr); gap: var(--sp-7); }
        .fband > .fb-rule { background: var(--band-rule); }
        .fb-main, .fb-sides { display: flex; flex-direction: column; min-width: 0; }
        .fb-sides { justify-content: space-between; }
        .fb-head { display: flex; align-items: center; gap: var(--control-gap); min-height: var(--control-h-md); }
        .fb-tile { width: var(--control-h-md); height: var(--control-h-md); border-radius: var(--radius-control); background: var(--surface-primary);
            color: var(--text-brand); display: grid; place-items: center; flex: none; box-shadow: var(--shadow-control); }
        .fb-tile svg { width: var(--icon-md); height: var(--icon-md); }
        .fb-label { font-weight: var(--weight-medium); color: var(--text-secondary); white-space: nowrap; }
        .fb-note { color: var(--text-secondary); white-space: nowrap; font-variant-numeric: tabular-nums; }
        .fband .delta { background: var(--surface-primary); }
        .fband .info:hover::before { background: var(--surface-primary); }
        .fb-fig { font-weight: var(--weight-semibold); line-height: var(--lh-none); letter-spacing: var(--tr-fig); font-variant-numeric: tabular-nums; }
        .fb-hero { display: flex; align-items: center; flex-wrap: wrap; gap: var(--gap-fig); margin: var(--gap-fig) 0 var(--sp-6); }
        .fb-hero .fb-fig { font-size: var(--fig-xl); }
        .fb-range { margin-top: auto; position: relative; padding: calc(var(--lh-caption) + var(--sp-3)) 0; }
        .fb-track { position: relative; height: var(--sp-3); border-radius: var(--radius-full); background: var(--surface-primary); }
        .fb-fill { position: absolute; top: 0; bottom: 0; left: var(--at-lo); width: calc(var(--at-hi) - var(--at-lo)); border-radius: var(--radius-full);
            background: var(--c-range); box-shadow: inset 0 0 0 var(--bw-hairline) var(--c-range-edge); }
        .fb-exp { position: absolute; top: 50%; left: var(--at-exp); width: var(--box-xs); height: var(--box-xs);
            margin: calc(var(--box-xs) / -2) 0 0 calc(var(--box-xs) / -2); border-radius: var(--radius-circle);
            background: var(--c-exp); box-shadow: 0 0 0 var(--bw-strong) var(--surface-primary); }
        .fb-plan { position: absolute; left: var(--at-plan); top: calc(var(--sp-1) - var(--lh-caption) - var(--sp-3)); bottom: calc(-1 * var(--sp-1));
            width: var(--bw-strong); margin-left: calc(var(--bw-strong) / -2); border-radius: var(--radius-swatch); background: var(--c-plan); }
        .fb-rl { position: absolute; font-size: var(--text-xs); line-height: var(--lh-caption); font-weight: var(--weight-medium); color: var(--text-secondary);
            white-space: nowrap; font-variant-numeric: tabular-nums; }
        .fb-rl.t { top: 0; left: calc(var(--at-plan) + var(--sp-2)); color: var(--text-primary); }
        .fb-rl.b { bottom: 0; left: var(--at); transform: translateX(-50%); }
        .fb-rl.mid { color: var(--text-tertiary); }
        .fb-side + .fb-side { margin-top: var(--sp-4); padding-top: var(--sp-4); box-shadow: var(--rule-t-band); }
        .fb-num { display: flex; align-items: center; gap: var(--gap-fig); margin-top: var(--gap-fig); }
        .fb-num .fb-fig { font-size: var(--fig-m); }
        .fb-num .fb-note { margin-left: auto; }
        .fb-meter { position: relative; height: var(--sp-1); border-radius: var(--radius-full); background: var(--band-rule); margin-top: var(--sp-3); }
        .fb-meter i { position: absolute; top: 0; bottom: 0; border-radius: var(--radius-full); }
        .fb-meter .taken { left: 0; width: var(--w); background: var(--c-taken); }
        .fb-meter .still { left: calc(var(--at) + var(--sp-0-5)); width: calc(100% - var(--at) - var(--sp-0-5)); background: var(--c-still); }
        .fb-meter .plan { left: var(--at-plan); top: calc(-1 * var(--sp-1)); bottom: calc(-1 * var(--sp-1)); width: var(--bw-strong);
            margin-left: calc(var(--bw-strong) / -2); background: var(--c-plan); }
        /* Under 1100 the side figures go under the main one, as on a phone. */
        @media (max-width: 1100px) {
            .fband { grid-template-columns: minmax(0, 1fr); gap: 0; }
            .fband > .fb-rule { display: none; }
            .fb-sides { margin-top: var(--sp-4); padding-top: var(--sp-4); box-shadow: var(--rule-t-band); }
        }
        @media (max-width: 640px) {
            .fband { padding: var(--sp-4); }
            .fb-hero { margin-bottom: var(--sp-4); }
            .fb-hero .fb-fig { font-size: var(--fig-l); }
            .fb-num .fb-fig { font-size: var(--fig-s); }
        }
```

- [ ] **Step 6: Run the tests**

Run: `ONLY=t_the_feature_band python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `436 passed, 0 failed`.

- [ ] **Step 7: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Parts: the feature band, its range bar on a round scale and its meters, built from the measure colours

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: Tables and list rows

**Files:**
- Modify: `static/index.html:3706-3747` (`.ktable-wrap`, `.ktable th`, `.ktable td`), `:3773` (hover), `:1722-1741` (`details.sect`, `.sect-group`), the stylesheet after `.ktable .num`, the script after `featureBand` (Task 15)
- Test: `tests/test_frontend.py` (`t_the_table_is_built_to_the_reference_measurements` 2834, `t_the_app_wide_layout_sweep_holds` 9151, a new test)

**Interfaces:**
- Consumes: `--rule-t`, `--rule-b`, `--border-soft`, `--row-h`, `--gap-row-icon`, `--gap-cols`, `.cnt`, `I.chev`.
- Produces: a table is a 32 head in caption type over 44 rows, framed by `--border-default` hairlines (top, under the head, bottom) and divided by `--border-soft`, no box, its outer columns on the text edge. `listRows(items, opts)` returns `nav.rlist` (two columns read down when `opts.cols === 2`, `aria-label` `opts.label`) of `button.rlist-row`: a 16 icon in ink-3 12 from its label, the label, a count with a hidden unit, a 14 chevron; `items` are `{ icon, label, n, unit, onClick }`. A drawer (`details.sect`) is a hairline row with a 44 summary.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_lists_are_rows_split_by_hairlines():
    """Spec 3 and 6: lists are rows split by hairlines, no box. A table is a 32
    head in caption type and 44 rows, line framing it (top, under the head,
    bottom) and line-soft between rows, numbers right and tabular. A list row
    is 44: a 16 icon 12 from its words, a count and a chevron at its end; two
    columns read down where there is room. A drawer is a row, not a box."""
    wrap = CSS.split("\n        .ktable-wrap {")[1].split("}")[0]
    ok("border: 0" in wrap and "background: none" in wrap and "box-shadow: var(--rule-t), var(--rule-b)" in wrap,
       "a table has no box: a line above and below")
    th = CSS.split(".ktable th {")[1].split("}")[0]
    for prop in ("height: var(--control-h)", "font-size: var(--text-xs)", "color: var(--text-tertiary)", "padding: 0 var(--sp-3)",
                 "box-shadow: var(--rule-b)"):
        ok(prop in th, "th: " + prop)
    td = CSS.split(".ktable td {")[1].split("}")[0]
    ok("height: var(--row-h)" in td and "solid var(--border-soft)" in td and "padding: 0 var(--sp-3)" in td, "a 44 row on a soft divider")
    ok(".ktable :is(th, td):first-child { padding-left: 0; }" in CSS and ".ktable :is(th, td):last-child { padding-right: 0; }" in CSS,
       "the outer columns sit on the text edge")
    ok("function listRows(items, opts) {" in SCRIPT, "the list row builder exists")
    fn = fn_src("function listRows(items, opts) {")
    for part in ("el('nav', 'rlist'", "el('button', 'rlist-row')", "el('span', 'cnt'", "el('span', 'sr-only', ' ' + it.unit)", "ico(I.chev)"):
        ok(part in fn, "listRows: " + part)
    row = CSS.split("\n        .rlist-row {")[1].split("}")[0]
    ok("min-height: var(--row-h)" in row and "gap: var(--gap-row-icon)" in row, "a list row is 44 with its icon 12 from its words")
    ok(".rlist.cols-2 { grid-auto-flow: column;" in CSS, "two columns read down")
    sect = CSS.split("\n        details.sect {")[1].split("}")[0]
    ok("border: 0" in sect and "box-shadow: var(--rule-b-soft)" in sect, "a drawer is a hairline row")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_lists_are_rows python3 tests/test_frontend.py`
Expected: `FAIL  t_lists_are_rows_split_by_hairlines: a table has no box: a line above and below`

- [ ] **Step 3: The table**

Replace:

```css
        .ktable-wrap { overflow-x: auto; border: var(--bw-hairline) solid var(--border-default); border-radius: var(--radius-card);
            box-shadow: var(--shadow-sm); background: var(--surface-primary); margin-bottom: var(--sp-6); }
```

with:

```css
        /* A TABLE (the mix, spec 6): no box. A line above it and below it, one
           under its head, a soft one between rows; it scrolls sideways when it
           must, and its outer columns sit on the text edge. */
        .ktable-wrap { overflow-x: auto; border: 0; border-radius: 0;
            box-shadow: var(--rule-t), var(--rule-b); background: none; margin-bottom: var(--sp-6); }
```

Replace:

```css
        .ktable th { text-align: left; font-size: var(--text-sm); text-transform: none; letter-spacing: normal; color: var(--text-primary); font-weight: var(--weight-medium); padding: var(--sp-3); line-height: var(--lh-control); border-bottom: var(--bw-hairline) solid var(--border-default); white-space: nowrap; height: 44px; }
        .ktable td { padding: var(--sp-3); border-bottom: var(--bw-hairline) solid var(--border-default); color: var(--text-primary); font-size: var(--text-sm); line-height: var(--lh-control); vertical-align: middle; }
```

with:

```css
        .ktable th { text-align: left; font-size: var(--text-xs); text-transform: none; letter-spacing: normal; color: var(--text-tertiary); font-weight: var(--weight-medium); padding: 0 var(--sp-3); line-height: var(--lh-caption); border-bottom: 0; box-shadow: var(--rule-b); white-space: nowrap; height: var(--control-h); }
        .ktable td { padding: 0 var(--sp-3); height: var(--row-h); border-bottom: var(--bw-hairline) solid var(--border-soft); color: var(--text-primary); font-size: var(--text-body); line-height: var(--lh-control); vertical-align: middle; }
        .ktable :is(th, td):first-child { padding-left: 0; }
        .ktable :is(th, td):last-child { padding-right: 0; }
```

In `.ktable { width: 100%; ...` replace `font-size: var(--text-sm); background: var(--surface-primary);` with `font-size: var(--text-body); background: none;`.

- [ ] **Step 4: The drawer is a row**

Replace:

```css
        details.sect { border: var(--bw-hairline) solid var(--border-default); border-radius: var(--radius-card); background: var(--surface-primary); margin-bottom: var(--sp-2); overflow: hidden; box-shadow: var(--shadow-sm); }
        /* A group of drawers is one card with divided rows: nine small cards
           stacked 8px apart read as nine objects, not two lists. */
        .sect-group { background: var(--surface-primary); border: var(--bw-hairline) solid var(--border-default);
            border-radius: var(--radius-card); overflow: hidden; }
        .sect-group > details.sect { border: 0; border-radius: 0; margin: 0; box-shadow: none; }
        .sect-group > details.sect + details.sect { border-top: var(--bw-hairline) solid var(--border-default); }
        details.sect summary { padding: var(--sp-3) var(--sp-4); font-weight: var(--weight-medium); font-size: var(--text-sm); cursor: pointer; list-style: none;
            display: flex; align-items: center; gap: var(--sp-2); }
```

with:

```css
        /* A drawer is a row (the mix): a 44 summary over a soft hairline, its
           body opening under it; a group of them is a list framed by a line. */
        details.sect { border: 0; border-radius: 0; background: none; margin-bottom: 0; overflow: visible; box-shadow: var(--rule-b-soft); }
        .sect-group { background: none; border: 0; border-radius: 0; box-shadow: var(--rule-t), var(--rule-b); }
        .sect-group > details.sect { border: 0; border-radius: 0; margin: 0; }
        details.sect summary { min-height: var(--row-h); padding: 0; font-weight: var(--weight-medium); font-size: var(--text-body); line-height: var(--lh-control); cursor: pointer; list-style: none;
            display: flex; align-items: center; gap: var(--gap-row-icon); }
```

Replace `        details.sect .body { padding: var(--sp-3) var(--sp-4) var(--sp-4); color: var(--text-secondary); font-size: var(--text-sm); line-height: var(--lh-prose); }` with:

```css
        details.sect .body { padding: 0 0 var(--sp-4); color: var(--text-secondary); font-size: var(--text-body); line-height: var(--lh-control); }
```

Replace `        details.sect[open] summary { border-bottom: var(--bw-hairline) solid var(--border-default); }` with nothing (delete it).

- [ ] **Step 5: The list row**

Directly after `        .ktable .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }` add:

```css
        /* A LIST OF ROWS (the mix, spec 6): 44 tall, a 16 icon in ink-3 12 from
           its words, a count and a 14 chevron at the end; a line frames it and
           a soft line divides it. Two columns read down where there is room,
           so a phone's single column keeps the same order. */
        .rlist { display: grid; grid-template-columns: minmax(0, 1fr); column-gap: var(--gap-cols); }
        .rlist.cols-2 { grid-auto-flow: column; grid-template-columns: repeat(2, minmax(0, 1fr)); grid-template-rows: repeat(var(--rows, 2), auto); }
        .rlist-row { position: relative; display: flex; align-items: center; gap: var(--gap-row-icon); min-height: var(--row-h); width: 100%;
            padding: 0; border: 0; background: none; font: inherit; font-size: var(--text-body); line-height: var(--lh-control); color: var(--text-primary);
            text-align: left; cursor: pointer; box-shadow: var(--rule-t-soft); }
        .rlist-row .ic { color: var(--text-tertiary); }
        .rlist-row .lbl { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .rlist-row > .ic:last-child svg { width: var(--icon-sm); height: var(--icon-sm); stroke-width: var(--icon-stroke-s); }
        .rlist-row:hover, .rlist-row:hover :is(.ic, .cnt) { color: var(--text-link); }
        .rlist-row:active, .rlist-row:active :is(.ic, .cnt) { color: var(--text-link-hover); }
        .rlist-row:focus-visible { outline: 0; }
        .rlist-row:focus-visible::before { content: ""; position: absolute; inset: var(--sp-0-5) calc(-1 * var(--sp-2)); border-radius: var(--radius-control);
            box-shadow: inset 0 0 0 var(--bw-strong) var(--fill-mark); pointer-events: none; }
        .rlist > .rlist-row:first-child, .rlist.cols-2 > .rlist-row:nth-child(odd) { box-shadow: var(--rule-t); }
        .rlist { box-shadow: var(--rule-b); }
        @media (max-width: 900px) { .rlist.cols-2 { grid-auto-flow: row; grid-template-columns: minmax(0, 1fr); grid-template-rows: none; } }
```

- [ ] **Step 6: The builder**

Directly after `featureBand` add:

```js
        /* A list of rows (the mix, spec 6). items: [{ icon, label, n, unit,
           onClick }]; opts: { label, cols }. With cols 2 the rows read down the
           first column, then the second, so a phone's one column keeps that order. */
        function listRows(items, opts) {
            opts = opts || {};
            /* A caller may leave a row out by passing null in its place. */
            const list = items.filter(Boolean);
            const nav = el('nav', 'rlist' + (opts.cols === 2 ? ' cols-2' : ''));
            if (opts.label) nav.setAttribute('aria-label', opts.label);
            if (opts.cols === 2) nav.style.setProperty('--rows', String(Math.ceil(list.length / 2)));
            list.forEach(it => {
                const b = el('button', 'rlist-row');
                b.type = 'button';
                if (it.icon) b.append(ico(it.icon));
                b.append(el('span', 'lbl', it.label));
                if (it.n != null) {
                    const c = el('span', 'cnt', String(it.n));
                    if (it.unit) c.append(el('span', 'sr-only', ' ' + it.unit));
                    b.append(c);
                }
                b.append(ico(I.chev));
                b.onclick = it.onClick;
                nav.append(b);
            });
            return nav;
        }
```

- [ ] **Step 7: Update the table guard**

Replace the body of `t_the_table_is_built_to_the_reference_measurements` (from `    th = CSS.split(".ktable th {")` to its end) with:

```python
    # The mix (2026-10-06, spec 6): a 32 head in caption type, 44 rows.
    th = CSS.split(".ktable th {")[1].split("}")[0]
    td = CSS.split(".ktable td {")[1].split("}")[0]
    ok("padding: 0 var(--sp-3)" in th and "padding: 0 var(--sp-3)" in td, "cells are 12 in, header and body alike")
    ok("height: var(--control-h)" in th and "height: var(--row-h)" in td, "the head row is 32, a body row 44")
    ok("line-height: var(--lh-caption)" in th and "line-height: var(--lh-control)" in td, "each on its step's one line height")
    ok("color: var(--text-primary)" in td and "var(--text-secondary)" not in td,
       "body cells are foreground, not a muted grey")
    hover = CSS.split(".ktable tbody tr:hover td {")[1].split("}")[0]
    ok("var(--surface-secondary)" in hover, "the hover is the fill")
```

In `t_the_app_wide_layout_sweep_holds` replace the key `".ktable { width: 100%; border-collapse: collapse; font-size: var(--text-sm); background: var(--surface-primary); min-width: min(460px, 100%); }"` with `".ktable { width: 100%; border-collapse: collapse; font-size: var(--text-body); background: none; min-width: min(460px, 100%); }"` (its reason, "a table fits a narrow card", still holds: the `min-width` is what it pins).

- [ ] **Step 8: Run the tests**

Run: `ONLY=t_lists_are_rows python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `437 passed, 0 failed`.

- [ ] **Step 9: Look at it**

Size list, Liability's customers, CRM contacts and Xero sync's run history at 1440: no table boxes; caption heads 32 tall under a line; 44 rows on soft dividers; the first column starts on the text edge. Overview's Details drawers are rows that open in place.

- [ ] **Step 10: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Parts: tables and drawers are hairline rows with no box, and one list row builder with counts and chevrons

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 17: Tags

**Files:**
- Modify: `static/index.html:4949-4953` (the ONE TAG recipe)
- Test: `tests/test_frontend.py` (a new test)

**Interfaces:**
- Consumes: `--tag-h`, `--lh-caption`.
- Produces: every tag is 20 tall, 8 in, a 4 corner, caption type (12/16 at 500), a tint, no border. The change chip (Task 14) is the one tag at 600.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_a_tag_is_twenty_tall_in_caption_type():
    """Spec 6 and 4.5: a tag is 20 tall with a 4 corner, caption type on its
    one 16 line, 8 in, a tint and no border. Status is shown by colour and
    shape (a dot, a tag, a bar), not a sentence."""
    tags = CSS.split("ONE TAG.")[1].split("}")[0]
    for prop in ("height: var(--tag-h)", "padding: 0 var(--sp-2)", "font-size: var(--text-xs)", "line-height: var(--lh-caption)",
                 "font-weight: var(--weight-medium)", "border: 0", "border-radius: var(--radius-tag)"):
        ok(prop in tags, "a tag: " + prop)
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_a_tag_is_twenty python3 tests/test_frontend.py`
Expected: `FAIL  t_a_tag_is_twenty_tall_in_caption_type: a tag: padding: 0 var(--sp-2)`

- [ ] **Step 3: The recipe**

In the ONE TAG rule replace:

```css
            display: inline-flex; align-items: center; gap: var(--sp-1); height: var(--tag-h); padding: 0 var(--sp-1-5);
            font-size: var(--text-xs); font-weight: var(--weight-medium); line-height: var(--lh-none); letter-spacing: normal;
```

with:

```css
            display: inline-flex; align-items: center; gap: var(--sp-1); height: var(--tag-h); padding: 0 var(--sp-2);
            font-size: var(--text-xs); font-weight: var(--weight-medium); line-height: var(--lh-caption); letter-spacing: normal;
```

and in its comment replace `4px corner, 12px medium text, a tinted fill and no border.` with `4px corner, 12/16 medium text 8 in, a tinted fill and no border (the mix, spec 6).`

- [ ] **Step 4: Run the tests**

Run: `ONLY=t_a_tag_is_twenty python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `438 passed, 0 failed`.

- [ ] **Step 5: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Parts: every tag 20 tall, 8 in, caption type on its one line

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 18: The empty state, and the run gate as one

**Files:**
- Modify: `static/index.html:1827-1838` (`.empty`), `:3681-3699` (`.run-gate`), the script's `renderRunGate` (9186) and after `listRows` (Task 16)
- Test: `tests/test_frontend.py` (a new test)

**Interfaces:**
- Consumes: `pageHead` (Task 7), `ico`, `--box-2xl`, `--text-head`.
- Produces: `emptyState(o)` returns `div.empty-state` (plus `o.cls`): a 40 tile (`span.empty-ic`) with `o.icon` on the fill, `p.empty-line` with `o.text` in the head step, then `o.action`. `renderRunGate(boxId, o)` draws `pageHead({ view: o.view, title: o.title, line: o.desc })` then `emptyState({ icon: o.icon, text: o.note, action: Run, cls: 'run-gate' })`. A `.empty` (a list's one-line "nothing matched") is quiet, centred ink-3 body text.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_an_empty_space_is_a_tile_a_line_and_its_action():
    """Spec 6 and 7 (Cameron: "i hate the stupid projector thing"): an empty
    state is a 40 icon tile with the screen's own icon on the fill, one line of
    8 words or fewer in the head step, and its action, centred in its space.
    No illustration, no box. A report's run gate is one: the page header with
    its one line, then the tile, the cost and Run."""
    ok("function emptyState(o) {" in SCRIPT, "the builder exists")
    fn = fn_src("function emptyState(o) {")
    for part in ("el('div', 'empty-state'", "el('span', 'empty-ic')", "ico(o.icon", "el('p', 'empty-line', o.text)", "if (o.action) box.append(o.action);"):
        ok(part in fn, "emptyState: " + part)
    tile = CSS.split("\n        .empty-ic {")[1].split("}")[0]
    ok("width: var(--box-2xl)" in tile and "height: var(--box-2xl)" in tile and "background: var(--surface-tertiary)" in tile
       and "border-radius: var(--radius-control)" in tile, "a 40 tile on the fill with a 6 corner")
    line = CSS.split("\n        .empty-line {")[1].split("}")[0]
    ok("font-size: var(--text-head)" in line and "font-weight: var(--weight-semibold)" in line, "one line in the head step")
    st = CSS.split("\n        .empty-state {")[1].split("}")[0]
    ok("align-items: center" in st and "text-align: center" in st and "border" not in st and "background" not in st, "centred, no box")
    gate = fn_src("function renderRunGate(boxId, o) {")
    ok("pageHead({ view: o.view, title: o.title, line: o.desc })" in gate and "emptyState({ icon: o.icon, text: o.note, action: btn, cls: 'run-gate' })" in gate,
       "a run gate is the header and an empty state")
    ok("rg-ic" not in gate and "illustration" not in gate, "no drawn tile of its own")
    e = CSS.split("\n        .empty {")[1].split("}")[0]
    ok("text-align: center" in e and "font-size: var(--text-body)" in e and "border: 0" in e, "a list that matched nothing says so quietly")
    ok(".ov-wrap > .empty, .ov-wrap > .widget-group > .empty, .card-grid > .empty { background" not in CSS, "with no box round it")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_an_empty_space python3 tests/test_frontend.py`
Expected: `FAIL  t_an_empty_space_is_a_tile_a_line_and_its_action: the builder exists`

- [ ] **Step 3: The builder and the gate**

Directly after `listRows` add:

```js
        /* The empty state (the mix, spec 6): a 40 tile with the screen's own
           icon on the fill, one line in the head step, then its action, centred
           in its space. No illustration and no box. o: { icon, text, action, cls } */
        function emptyState(o) {
            const box = el('div', 'empty-state' + (o.cls ? ' ' + o.cls : ''));
            const t = el('span', 'empty-ic'); t.setAttribute('aria-hidden', 'true'); t.append(ico(o.icon || I.grid));
            box.append(t, el('p', 'empty-line', o.text));
            if (o.action) box.append(o.action);
            return box;
        }
```

Replace:

```js
        function renderRunGate(boxId, o) {
            const box = $(boxId); box.innerHTML = '';
            const card = el('div', 'run-gate');
            const ic = el('div', 'rg-ic'); ic.innerHTML = o.icon; card.append(ic);
            card.append(el('h2', null, o.title), el('p', null, o.desc));
            const btn = el('button', 'btn btn-primary rg-btn'); btn.textContent = o.cta; btn.onclick = o.onRun;
            card.append(btn);
            if (o.note) card.append(el('div', 'rg-note', o.note));
            box.append(card);
        }
```

with:

```js
        /* A report that has not run yet (the mix, spec 8.3): its page header
           with the one line saying what it is, then an empty state holding the
           cost and Run. Nothing fetches or spends until Run is pressed. */
        function renderRunGate(boxId, o) {
            const box = $(boxId); box.innerHTML = '';
            const btn = el('button', 'btn btn-primary rg-btn'); btn.textContent = o.cta; btn.onclick = o.onRun;
            box.append(pageHead({ view: o.view, title: o.title, line: o.desc }),
                emptyState({ icon: o.icon, text: o.note, action: btn, cls: 'run-gate' }));
        }
```

- [ ] **Step 4: The rules**

Replace:

```css
        .empty { background: transparent; border: 0; border-radius: 0; padding: var(--sp-6) max(var(--sp-4), calc((100% - var(--measure)) / 2));
            color: var(--text-tertiary); font-size: var(--text-sm); line-height: var(--lh-prose); text-align: center; }
        /* ...unless it stands alone on the page or in a grid of cards, where it
           needs the card's own edge or it floats. A widget group is still the
           page: its heading and empty state are the same two blocks, grouped
           so the grid moves them together. */
        .ov-wrap > .empty, .ov-wrap > .widget-group > .empty, .card-grid > .empty { background: var(--surface-primary); border: var(--bw-hairline) solid var(--border-default); border-radius: var(--radius-card); }
        /* Inside a card an empty state is the first line of the list it stands
           in for: left-aligned on the card's gutter and spaced by the card's own
           16 gap. Centred with 24 above and below, it floated 40 to 50px from
           everything around it and 500px from its own title. */
        .card > .empty, .card-bleed > .empty, .card > div > .empty:only-child { text-align: left; padding: 0; max-width: var(--measure); }
```

with:

```css
        /* A list that matched nothing (a search, a filter): one quiet line,
           centred where its rows would be. A space with nothing in it at all is
           the empty state below. */
        .empty { background: transparent; border: 0; border-radius: 0; padding: var(--sp-6) max(var(--sp-4), calc((100% - var(--measure)) / 2));
            color: var(--text-tertiary); font-size: var(--text-body); line-height: var(--lh-control); text-align: center; }
        /* THE EMPTY STATE (the mix, spec 6): a 40 tile with the screen's own
           icon on the fill, one line in the head step, its action; centred in
           its space, 16 apart. No illustration and no box. */
        .empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--sp-4);
            text-align: center; padding: var(--sp-10) 0; }
        .empty-ic { width: var(--box-2xl); height: var(--box-2xl); border-radius: var(--radius-control); background: var(--surface-tertiary);
            color: var(--text-tertiary); display: grid; place-items: center; flex: none; }
        .empty-ic svg { width: var(--icon-md); height: var(--icon-md); }
        .empty-line { margin: 0; font-size: var(--text-head); line-height: var(--lh-control); font-weight: var(--weight-semibold);
            color: var(--text-primary); max-width: var(--measure); }
```

Replace:

```css
        .run-gate { max-width: 480px; margin: 7vh auto 0; text-align: center; display: flex; flex-direction: column; align-items: center; background: var(--surface-primary); border: var(--bw-hairline) solid var(--border-default); border-radius: var(--radius-card); padding: var(--sp-8) var(--sp-7); box-shadow: var(--shadow-sm); animation: fadeUp .4s ease backwards; }
```

with:

```css
        /* A run gate is an empty state under its page's header (renderRunGate).
           Customers builds its own until Task 36 moves it onto the same builder. */
        .run-gate { text-align: center; display: flex; flex-direction: column; align-items: center; gap: var(--sp-4); padding: var(--sp-10) 0; }
```

- [ ] **Step 5: Run the tests**

Run: `ONLY=t_an_empty_space python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `439 passed, 0 failed`.

- [ ] **Step 6: Look at it**

Overview before a run: the page header "Overview" with its line, then a centred 40 tile with the grid icon, "Uses AI credits only when you run it." in 15 at 600 and the teal Run overview. The 165-screen audit (Task 45) still finds the button by `.run-gate .btn-primary`.

- [ ] **Step 7: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Parts: an empty state is a 40 tile, one line and its action; a report's run gate is one under its header

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 19: The chart: a legend row, the day under the pointer, a finger or the keys

**Files:**
- Modify: `static/index.html` `:root` (`--chart-stroke`, `--chart-pt-r`, `--tip-w`), `:4119-4184` and `:4231-4263` (the chart rules), `CHART` (5285), `chartLegend` (7905), `drawFrame` (7924), `trendChart` (7993-8167)
- Test: `tests/test_frontend.py` (`t_the_charts_are_drawn_to_the_reference_spec` 1737, `t_the_chart_legend_belongs_to_the_plot` 3197, `t_focus_is_declared_once_per_kind` 5901, a new test)

**Interfaces:**
- Consumes: the measure tokens (Task 3), `tokenNum`, `--tip-pad`, `--pop-offset`.
- Produces: `trendChart(opts)` takes `headless: true` (no chart head: the section head names the chart), `legend: true` (always key the series), `label` (the chart's name for a screen reader); a series takes `key: 'dot'` (keyed and drawn as a dot where it has a single point). The plot is focusable (`role="group"`, `aria-roledescription="chart"`); the left and right arrow keys, the pointer or a finger dragging show a point; Escape or a tap elsewhere rests it; on a desktop the tooltip sits beside the point, on a phone the legend row reads the point out; a `p.sr-only[role=status]` says it. The grid is `--border-soft`, the floor `--border-strong`, the line 2px.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_a_chart_reads_out_the_day_it_is_on():
    """Spec 6 Chart: the legend on its own row; hover, a finger dragging or the
    arrow keys show the day; on a desktop a tooltip sits beside the point, on a
    phone the legend row reads the day out instead so nothing is covered; a
    status line tells a screen reader when the day changes. The grid is
    line-soft, the floor line-ctl, the series line 2px."""
    tc = SCRIPT.split("function trendChart(", 1)[1].split("\n        function ", 1)[0]
    for part in ("if (!opts.headless) card.append(chartHead(opts, series, 'trend'));",
                 "wrap.setAttribute('role', 'group'); wrap.setAttribute('aria-roledescription', 'chart');",
                 "live.setAttribute('role', 'status');", "wrap.onkeydown = (e) => {", "e.key === 'ArrowLeft' || e.key === 'ArrowRight'",
                 "svg.onpointermove = (e) => at(e.clientX);", "svg.setPointerCapture(e.pointerId)",
                 "window.matchMedia('(max-width: 640px)').matches", "legendEl.classList.add('reading')", "wrap._rest = rest;"):
        ok(part in tc, "trendChart: " + part)
    ok("touchstart" not in tc and "mousemove" not in tc, "one pointer path for a mouse, a pen and a finger")
    ok(".chart-wrap" in SCRIPT.split("function autoPlot(")[0][-1200:] or "document.addEventListener('pointerdown', (e) => document.querySelectorAll('.chart-wrap')" in SCRIPT,
       "a tap anywhere else puts a chart back to rest")
    grid = CSS.split("\n        .chart-wrap .gridline {")[1].split("}")[0]
    ok("stroke: var(--border-soft)" in grid and "opacity" not in grid, "the grid is line-soft, solid")
    ok(".chart-wrap .gridline.axis0 { stroke: var(--border-strong); }" in CSS, "the floor is line-ctl")
    eq(_token_raw("chart-stroke"), "var(--bw-strong)", "--chart-stroke")
    tip = CSS.split("\n        .chart-tip {")[1].split("}")[0]
    for prop in ("width: var(--tip-w)", "padding: var(--tip-pad)", "border-radius: var(--radius-pop)", "box-shadow: var(--shadow-pop)"):
        ok(prop in tip, "the tooltip: " + prop)
    lg = CSS.split("\n        .chart-legend {")[1].split("}")[0]
    ok("justify-content: flex-start" in lg and "margin-bottom: var(--sp-2)" in lg, "the legend is its own row, 8 over the plot")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_a_chart_reads_out python3 tests/test_frontend.py`
Expected: `FAIL  t_a_chart_reads_out_the_day_it_is_on: trendChart: if (!opts.headless) card.append(chartHead(opts, series, 'trend'));`

- [ ] **Step 3: Tokens**

In `:root` replace `            --chart-dot-r: 3.5px; --chart-stroke: 1.4px;` with:

```
            --chart-dot-r: 3.5px; --chart-stroke: var(--bw-strong);   /* the mix: a series is a 2px line */
            --chart-pt-r: 4px;      /* a single point drawn as a dot (8 across, its white ring outside) */
            --tip-w: 232px;         /* the chart's tooltip */
```

Replace:

```js
            dotR: tokenNum('--chart-dot-r'),
        };
```

with:

```js
            dotR: tokenNum('--chart-dot-r'), ptR: tokenNum('--chart-pt-r'),
        };
```

- [ ] **Step 4: The legend and the frame**

In `chartLegend` replace:

```js
            series.filter(sr => (sr.values || []).filter(v => v != null).length > 1)
                .forEach((sr, i) => item(sr.name, sr.color, (sr.dash || (i > 0 && !sr.lead)) ? 'dash' : ''));
```

with:

```js
            series.filter(sr => (sr.values || []).filter(v => v != null).length > 1 || sr.key === 'dot')
                .forEach((sr, i) => item(sr.name, sr.color, sr.key || ((sr.dash || (i > 0 && !sr.lead)) ? 'dash' : '')));
```

In `drawFrame` replace:

```js
                gy.append(svgEl('line', { class: 'gridline', x1: padL, y1: yy, x2: W, y2: yy }));
```

with:

```js
                gy.append(svgEl('line', { class: 'gridline' + (t === ticks && !minV ? ' axis0' : ''), x1: padL, y1: yy, x2: W, y2: yy }));
```

- [ ] **Step 5: trendChart: headless, the legend row, the dot, the plot's name and its status line**

In `trendChart` replace:

```js
            card.append(chartHead(opts, series, 'trend'));
```

with:

```js
            if (!opts.headless) card.append(chartHead(opts, series, 'trend'));
```

replace:

```js
            if ((multi && series.length > 1) || bandOpt || series.some(s => s.dash)) {
```

with:

```js
            if (opts.legend || (multi && series.length > 1) || bandOpt || series.some(s => s.dash)) {
```

replace:

```js
            const wrap = el('div', 'chart-wrap'); card.append(wrap);
```

with:

```js
            const wrap = el('div', 'chart-wrap'); card.append(wrap);
            /* The plot is one stop for the keyboard: the arrow keys read it point
               by point, and a status line says each point to a screen reader. */
            wrap.tabIndex = 0;
            wrap.setAttribute('role', 'group'); wrap.setAttribute('aria-roledescription', 'chart');
            wrap.setAttribute('aria-label', (opts.label || opts.title || 'Chart') + '. Use the left and right arrow keys to read it point by point.');
            const live = el('p', 'sr-only'); live.setAttribute('role', 'status'); card.append(live);
```

Directly after the line that begins `                series.forEach((s, si) => { const p = svgEl('path', { class: 'chart-line'` add:

```js
                /* A series with a single point (money taken on the first of the
                   month) is a dot, ringed in white, rather than a speck. */
                series.forEach(s => runsOf(s.values).filter(r => r.length === 1).forEach(r =>
                    svg.append(svgEl('circle', { class: 'chart-pt', cx: r[0][0], cy: r[0][1], r: CHART.ptR, fill: s.color || CH[0] }))));
```

- [ ] **Step 6: trendChart: the day under the pointer, a finger or the keys**

Replace everything from the line `                const tip = el('div', 'chart-tip'); wrap.append(tip);` through the line `                svg.addEventListener('touchmove', e => { if (e.touches[0]) move(e.touches[0].clientX); }, { passive: true });` with:

```js
                const tip = el('div', 'chart-tip'); tip.setAttribute('aria-hidden', 'true'); wrap.append(tip);
                const overlay = svgEl('rect', { x: padL, y: padT, width: (W - padL - padR), height: (H - padT - padB), fill: 'transparent' }); svg.append(overlay);
                /* The point under the pointer, a finger or the arrow keys (the
                   mix, spec 6). On a desktop the tooltip sits beside the point,
                   its first row level with it; on a phone the legend row reads
                   the point out instead, so nothing covers the chart. */
                const legendEl = card.querySelector('.chart-legend');
                const TIP = { beside: tokenNum('--sp-4'), off: tokenNum('--pop-offset'),
                    lift: tokenNum('--tip-pad') + tokenNum('--lh-caption') + tokenNum('--sp-1') + tokenNum('--lh-control') / 2 };
                const swatch = (cls, color) => { const s = el('span', 'sw' + (cls ? ' ' + cls : '')); if (color) s.style.setProperty('--sw', color); return s; };
                let cur = -1;
                const show = (i) => {
                    i = Math.max(0, Math.min(n - 1, i)); cur = i;
                    hoverLine.setAttribute('x1', X(i)); hoverLine.setAttribute('x2', X(i)); hoverLine.setAttribute('opacity', 1);
                    dots.forEach((c, si) => { const v = series[si].values[i];
                        if (v == null) { c.setAttribute('opacity', 0); return; }
                        c.setAttribute('cx', X(i)); c.setAttribute('cy', Y(v)); c.setAttribute('opacity', 1); });
                    const rows = [];
                    series.forEach(s => { if (s.values[i] != null) rows.push([swatch(s.key === 'dot' ? 'dot' : (s.dash ? 'dash' : ''), s.color || CH[0]), s.name || '', fmt(s.values[i])]); });
                    if (bandOpt && bandOpt.lo[i] != null && bandOpt.hi[i] != null)
                        rows.push([swatch('band', bandOpt.color || CH[2]), bandOpt.name || 'Range', fmt(bandOpt.lo[i]) + ' to ' + fmt(bandOpt.hi[i])]);
                    const said = labels[i] + ', ' + rows.map(r => r[1] + ' ' + r[2]).join(', ');
                    if (live.textContent !== said) live.textContent = said;
                    if (legendEl && window.matchMedia('(max-width: 640px)').matches) {
                        if (!legendEl._rest) legendEl._rest = [].slice.call(legendEl.childNodes);
                        const read = [el('b', null, labels[i])];
                        rows.forEach(r => { const it = el('span', 'lg'); it.append(r[0], document.createTextNode(r[2])); read.push(it); });
                        legendEl.replaceChildren(...read); legendEl.classList.add('reading');
                        return;
                    }
                    tip.replaceChildren(el('div', 'tl', labels[i]));
                    rows.forEach(r => { const row = el('div', 'tr'); row.append(r[0], el('span', null, r[1]), el('b', null, r[2])); tip.append(row); });
                    const rect = svg.getBoundingClientRect(); if (!rect.width) return;
                    const k = rect.width / W, tw = tip.offsetWidth, th = tip.offsetHeight;
                    const ys = series.map(s => s.values[i]).filter(v => v != null).map(v => Y(v));
                    const px = X(i) * k, py = (ys.length ? Math.min.apply(null, ys) : padT) * k;
                    let left = px + TIP.beside, top = py - TIP.lift;
                    if (left + tw > rect.width) left = px - TIP.beside - tw;
                    if (left < 0) { left = Math.max(0, Math.min(px - tw / 2, rect.width - tw)); top = py - TIP.off - th; }
                    else top = Math.max(0, Math.min(top, (H - padB) * k - th));
                    tip.style.left = Math.round(left) + 'px'; tip.style.top = Math.round(top) + 'px'; tip.style.opacity = 1;
                };
                const rest = () => {
                    cur = -1; hoverLine.setAttribute('opacity', 0); dots.forEach(c => c.setAttribute('opacity', 0)); tip.style.opacity = 0;
                    if (legendEl && legendEl._rest) { legendEl.replaceChildren(...legendEl._rest); legendEl.classList.remove('reading'); }
                };
                wrap._rest = rest;
                const at = (clientX) => {
                    const rect = svg.getBoundingClientRect(); if (!rect.width) return;
                    show(Math.round(((clientX - rect.left) / rect.width * W - padL) / (W - padL - padR) * (n - 1)));
                };
                svg.onpointermove = (e) => at(e.clientX);
                /* A finger keeps the chart while it drags across the points. */
                svg.onpointerdown = (e) => { at(e.clientX); if (e.pointerType !== 'mouse' && svg.setPointerCapture) svg.setPointerCapture(e.pointerId); };
                svg.onpointerleave = (e) => { if (e.pointerType === 'mouse') rest(); };
                wrap.onkeydown = (e) => {
                    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); show((cur < 0 ? n - 1 : cur) + (e.key === 'ArrowRight' ? 1 : -1)); }
                    else if (e.key === 'Escape') rest();
                };
```

Directly before `        let _chartSeq = 0;` add:

```js
        /* A tap or click anywhere else puts every chart back to rest. */
        document.addEventListener('pointerdown', (e) => document.querySelectorAll('.chart-wrap').forEach(w => {
            if (!w.contains(e.target) && w._rest) w._rest(); }), { passive: true });
```

- [ ] **Step 7: The chart's rules**

Replace:

```css
        .chart-head .ct { font-size: var(--text-md); font-weight: var(--weight-medium); text-transform: none;
            letter-spacing: normal; color: var(--text-primary); line-height: var(--lh-none); }
```

with:

```css
        .chart-head .ct { font-size: var(--text-head); font-weight: var(--weight-semibold); text-transform: none;
            letter-spacing: normal; color: var(--text-primary); line-height: var(--lh-control); }
```

Replace `        .chart-head .cv { font-size: var(--text-2xl); font-weight: var(--weight-regular); letter-spacing: -.025em; line-height: var(--lh-snug); margin-top: var(--sp-1); display: flex; align-items: center; color: var(--text-primary); }` with:

```css
        .chart-head .cv { font-size: var(--fig-s); font-weight: var(--weight-semibold); letter-spacing: var(--tr-fig); line-height: var(--lh-none); margin-top: var(--sp-2); display: flex; align-items: center; color: var(--text-primary); font-variant-numeric: tabular-nums; }
```

Replace:

```css
        .chart-legend { display: flex; gap: var(--sp-4); align-items: center;
            justify-content: flex-end; flex-wrap: wrap;
            padding-bottom: var(--sp-3); margin-bottom: var(--sp-5); }
        .chart-legend .lg { display: inline-flex; align-items: center; gap: var(--sp-1-5);
            font-size: var(--text-xs); color: var(--text-primary); }
        /* An 8px square with a 2px corner, not a 9px lozenge: at the app's small
           radius a 9px chip reads as a rounded blob rather than a key. */
        .chart-legend .sw { width: var(--dot-md); height: var(--dot-md); border-radius: var(--radius-swatch); flex: none;
            background: var(--sw); }
        /* A line drawn dashed is keyed with a dashed stroke, painted rather
           than bordered: a dashed BORDER is this app's drop-target signal. */
        .chart-legend .sw.dash { width: var(--sp-4); height: var(--bw-strong); border-radius: 0;
            background: repeating-linear-gradient(90deg, var(--sw) 0 var(--sp-1), transparent var(--sp-1) var(--sp-2)); }
        .chart-legend .sw.band { opacity: .16; }
```

with:

```css
        /* THE LEGEND (the mix, spec 6): its own row between the section head
           and the plot, caption in ink-3, 16 between keys and 8 over the plot.
           Each key is drawn the way its mark is: a 12 line, a dashed line, an
           8 dot, or the range's 12 by 8 area with its edge. On a phone it reads
           the held point out (.reading), in the same row. */
        .chart-legend { display: flex; gap: var(--sp-4); align-items: center;
            justify-content: flex-start; flex-wrap: wrap; min-height: var(--lh-caption);
            padding-bottom: 0; margin-bottom: var(--sp-2); }
        .chart-legend .lg { display: inline-flex; align-items: center; gap: var(--control-gap);
            font-size: var(--text-xs); line-height: var(--lh-caption); color: var(--text-tertiary); font-variant-numeric: tabular-nums; }
        .chart-legend .sw, .chart-tip .sw { width: var(--sp-3); height: var(--bw-strong); border-radius: var(--radius-swatch); flex: none;
            background: var(--sw); }
        /* A line drawn dashed is keyed with a dashed stroke, painted rather
           than bordered: a dashed BORDER is this app's drop-target signal. */
        .chart-legend .sw.dash, .chart-tip .sw.dash { width: var(--sp-4); height: var(--bw-strong); border-radius: 0;
            background: repeating-linear-gradient(90deg, var(--sw) 0 var(--sp-1), transparent var(--sp-1) var(--sp-2)); }
        .chart-legend .sw.dot, .chart-tip .sw.dot { width: var(--dot-md); height: var(--dot-md); border-radius: var(--radius-circle); }
        .chart-legend .sw.band, .chart-tip .sw.band { width: var(--sp-3); height: var(--sp-2); background: var(--c-area);
            box-shadow: inset 0 0 0 var(--bw-hairline) var(--c-area-edge); opacity: 1; }
        .chart-legend.reading b { font-weight: var(--weight-medium); color: var(--text-primary); }
        .chart-legend.reading .lg { color: var(--text-primary); }
        .chart-wrap:focus-visible { outline: var(--focus-outline); outline-offset: var(--sp-1); border-radius: var(--radius-control); }
        .chart-pt { stroke: var(--surface-primary); stroke-width: var(--bw-strong); paint-order: stroke; }
```

Replace `        .chart-wrap .gridline { stroke: var(--border-default); stroke-opacity: .5; stroke-width: 1; vector-effect: non-scaling-stroke; }` with:

```css
        .chart-wrap .gridline { stroke: var(--border-soft); stroke-width: 1; vector-effect: non-scaling-stroke; }
        .chart-wrap .gridline.axis0 { stroke: var(--border-strong); }
        .chart-wrap { touch-action: pan-y; }
```

Replace `        .chart-band { stroke: none; opacity: .16; }` with:

```css
        .chart-band { stroke: none; fill: var(--c-area); }
```

Replace:

```css
        .chart-hover-line { stroke: var(--border-emphasis); stroke-width: 1; vector-effect: non-scaling-stroke; }
        .chart-tip { position: absolute; pointer-events: none; background: var(--surface-primary); border: var(--bw-hairline) solid var(--border-strong); border-radius: var(--radius-card); padding: var(--sp-2) var(--sp-2); font-size: var(--text-xs); box-shadow: var(--shadow-lg); transform: translate(-50%, calc(-100% - 12px)); white-space: nowrap; opacity: 0; transition: opacity var(--dur) var(--ease); z-index: 4; }
        .chart-tip .tl { color: var(--text-tertiary); font-size: var(--text-xs); text-transform: none; letter-spacing: normal; margin-bottom: var(--sp-1); }
        .chart-tip .tr { display: flex; align-items: center; gap: var(--sp-2); color: var(--text-secondary); } .chart-tip .tr + .tr { margin-top: var(--sp-1); }
        .chart-tip .sw { width: var(--dot-md); height: var(--dot-md); border-radius: var(--radius-swatch); flex: none; } .chart-tip b { font-weight: var(--weight-semibold); color: var(--text-primary); margin-left: var(--sp-0-5); }
```

with:

```css
        .chart-hover-line { stroke: var(--text-tertiary); stroke-width: 1; stroke-dasharray: 2 3; vector-effect: non-scaling-stroke; }
        /* The tooltip beside the point: 232 wide, 12 inside, the floating corner
           and shadow; the day in ink at 600, then one 20 row per measure. */
        .chart-tip { position: absolute; pointer-events: none; background: var(--surface-primary); border: 0; border-radius: var(--radius-pop);
            padding: var(--tip-pad); width: var(--tip-w); font-size: var(--text-xs); line-height: var(--lh-caption); box-shadow: var(--shadow-pop);
            opacity: 0; transition: opacity var(--dur) var(--ease); z-index: 4; }
        .chart-tip .tl { color: var(--text-primary); font-weight: var(--weight-semibold); margin-bottom: var(--sp-1); }
        .chart-tip .tr { display: flex; align-items: center; gap: var(--control-gap); height: var(--lh-control); color: var(--text-secondary); }
        .chart-tip b { margin-left: auto; font-weight: var(--weight-medium); color: var(--text-primary); font-variant-numeric: tabular-nums; }
```

Replace `        .chart-tip .sw.band { border-radius: var(--radius-swatch); opacity: .45; }` with nothing (delete it).

Replace:

```css
        .chart-expand { position: absolute; top: var(--sp-4); right: var(--sp-4); z-index: 2; border: var(--bw-hairline) solid var(--border-default); background: var(--surface-primary); color: var(--text-primary); width: var(--box-lg); height: var(--box-lg); border-radius: var(--radius-control); display: grid; place-items: center; cursor: pointer; transition: background var(--dur) var(--ease), color var(--dur) var(--ease), border-color var(--dur) var(--ease), opacity var(--dur) var(--ease); opacity: 1; }
        .chart-expand:hover { background: var(--surface-secondary); border-color: var(--border-default); opacity: 1; }
        .chart-expand svg { width: var(--icon-sm); height: var(--icon-sm); display: block; }
```

with:

```css
        /* Expand: a 32 ghost square at the head's right, on the section's own edge. */
        .chart-expand { position: absolute; top: 0; right: 0; z-index: 2; border: 0; background: transparent; color: var(--text-tertiary); width: var(--control-h); height: var(--control-h); border-radius: var(--radius-control); display: grid; place-items: center; cursor: pointer; transition: background var(--dur) var(--ease), color var(--dur) var(--ease); }
        .chart-expand:hover { background: var(--surface-tertiary); color: var(--text-primary); }
        .chart-expand:active { background: var(--press); }
        .chart-expand svg { width: var(--icon-md); height: var(--icon-md); display: block; }
```

Replace `        .chart-card .chart-head { padding-right: var(--sp-7); }` with:

```css
        .chart-card .chart-head { padding-right: var(--sp-8); }
```

- [ ] **Step 8: Update the chart guards**

In `t_the_charts_are_drawn_to_the_reference_spec` replace:

```python
    ok("stroke: var(--border-default)" in grid and "stroke-opacity: .5" in grid,
       "the grid is the border colour at half opacity, one step lighter than "
       "the card's own edge: " + grid)
    ok(_token("border-default").lower() == "#e6e7ea", "and that token resolves to the ramp's line, #E6E7EA")
```

with:

```python
    ok("stroke: var(--border-soft)" in grid and "opacity" not in grid,
       "the grid is line-soft, solid (the mix): " + grid)
    ok(_token("border-soft").lower() == "#eeeff1", "and that token resolves to the ramp's line-soft, #EEEFF1")
```

and replace:

```python
    ok(_token_raw("chart-stroke") == "1.4px", "and that token is still 1.4, not a marker pen")
```

with:

```python
    ok(_token_raw("chart-stroke") == "var(--bw-strong)", "and that token is the mix's 2px series line")
```

In `t_focus_is_declared_once_per_kind` replace (as Task 7 left it):

```python
    ok(CSS.count("outline: var(--focus-outline)") == 5,
       "the outline is read by the control rule and by four deliberate variants (the "
```

with:

```python
    ok(CSS.count("outline: var(--focus-outline)") == 6,
       "the outline is read by the control rule and by five deliberate variants (the "
```

and replace `       "draws it on its 24 face so a phone's 40 target never shows), and nowhere else")` with `       "draws it on its 24 face so a phone's 40 target never shows, and a chart's plot, one stop for the arrow keys), and nowhere else")`.

In `t_the_chart_legend_belongs_to_the_plot` replace:

```python
    ok("if ((multi && series.length > 1) || bandOpt || series.some(s => s.dash)) {" in SCRIPT
```

with:

```python
    ok("if (opts.legend || (multi && series.length > 1) || bandOpt || series.some(s => s.dash)) {" in SCRIPT
```

and replace:

```python
    ok(".chart-legend .sw.dash {" in CSS and "repeating-linear-gradient" in CSS.split(".chart-legend .sw.dash {")[1].split("}")[0],
       "painted as a dashed stroke, not a dashed border (the drop-target signal)")
```

with:

```python
    dash = ".chart-legend .sw.dash, .chart-tip .sw.dash {"
    ok(dash in CSS and "repeating-linear-gradient" in CSS.split(dash)[1].split("}")[0],
       "painted as a dashed stroke, not a dashed border (the drop-target signal), in the legend and the tooltip alike")
```

and replace the lines from `    lg = CSS.split(".chart-legend {")[1].split("}")[0]` to the end of the test with:

```python
    lg = CSS.split(".chart-legend {")[1].split("}")[0]
    ok("justify-content: flex-start" in lg, "on its own row from the left (the mix)")
    ok("gap: var(--sp-4)" in lg, "16px between keys")
    ok("margin-bottom: var(--sp-2)" in lg, "8 before the plot")
    sw = CSS.split(".chart-legend .sw, .chart-tip .sw {")[1].split("}")[0]
    ok("width: var(--sp-3)" in sw and "height: var(--bw-strong)" in sw, "a series is keyed as a 12 line")
    ok("border-radius: var(--radius-swatch)" in sw and _token_raw("radius-swatch") == "var(--radius-3xs)",
       "with the swatch role's 2px corner")
    item = CSS.split(".chart-legend .lg {")[1].split("}")[0]
    ok("gap: var(--control-gap)" in item, "8px between a key and its name")
    ok("color: var(--text-tertiary)" in item, "and the name in ink-3, a caption")
```

- [ ] **Step 9: Run the tests**

Run: `ONLY=t_a_chart_reads_out python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `440 passed, 0 failed`.

- [ ] **Step 10: Look at it**

Overview after a run, Revenue chart at 1440: hover shows the white tooltip beside the point, the day in ink, one row per series; Tab onto the plot and press Left: the point steps back and a screen reader hears the day. At 390, dragging a finger (or the mouse) across it rewrites the legend row with the day and its values; tapping elsewhere restores the keys.

- [ ] **Step 11: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Parts: charts with a legend row, a tooltip beside the point, the arrow keys and a phone readout in the legend

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 20: Queue counters

**Files:**
- Modify: `static/index.html` `:root` (`--qc-w`), the stylesheet after the tab rules (after `.cnt`, Task 10), the page rhythm rules (after `.ov-wrap > :is(.tabs, .page-tabs, .seg-row)`, Task 10), the widget grid tab rules, the script after `emptyState` (Task 18)
- Test: `tests/test_frontend.py` (a new test)

**Interfaces:**
- Consumes: `--radius-tile`, `--fig-l`, `--fig-m`, `--shadow-focal`, `--ring-chosen`, `I.chev`.
- Produces: `queueCounters(flow, rest, current, onPick, label)` returns `nav.queues`: `flow` is `[[key, label, count]]`, drawn as `button.qc` tiles (label `span.qc-l` over a 36 figure `b.qc-n`, 28 on a phone) with `span.qsep` chevrons between; `rest` is `[[key, label, icon]]`, drawn as `button.qt` tabs in `div.qrest`. The chosen one carries `.on` and `aria-current="page"`; pressing another calls `onPick(key)`. It sits 20 under the header and 20 over what follows.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_queue_counters_read_across_the_bench():
    """Spec 6: the queues that make a flow are big tiles in flow order with
    small chevrons between, the label above a 36 figure (28 on a phone), a 10
    corner on the fill; the chosen counter is a teal fill with the focal glow.
    The rest of the queues are tabs beside them on the chosen recipe."""
    ok("function queueCounters(flow, rest, current, onPick, label) {" in SCRIPT, "the builder exists")
    fn = fn_src("function queueCounters(flow, rest, current, onPick, label) {")
    for part in ("el('nav', 'queues')", "el('button', 'qc'", "el('span', 'qc-l', l)", "el('b', 'qc-n'", "el('span', 'qsep')",
                 "el('div', 'qrest')", "el('button', 'qt'", "setAttribute('aria-current', 'page')"):
        ok(part in fn, "queueCounters: " + part)
    qc = CSS.split("\n        .qc {")[1].split("}")[0]
    ok("border-radius: var(--radius-tile)" in qc and "background: var(--surface-tertiary)" in qc and "width: var(--qc-w)" in qc,
       "a counter is a tile on the fill with the 10 corner")
    ok("font-size: var(--fig-l)" in CSS.split("\n        .qc-n {")[1].split("}")[0], "its figure is 36")
    on = CSS.split("\n        .qc.on {")[1].split("}")[0]
    ok("background: var(--action-primary)" in on and "box-shadow: var(--shadow-focal)" in on, "the chosen one is teal with the focal glow")
    qt = CSS.split("\n        .qt.on {")[1].split("}")[0]
    ok("box-shadow: var(--ring-chosen)" in qt and "background: var(--action-selected)" in qt, "a queue tab is chosen on the segment recipe")
    eq(_token_raw("qc-w"), "184px", "--qc-w")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_queue_counters python3 tests/test_frontend.py`
Expected: `FAIL  t_queue_counters_read_across_the_bench: the builder exists`

- [ ] **Step 3: The token**

In `:root` replace `            --pop-w: 360px;         /* a popover's width (the window's, less 16 a side, on a phone) */` with:

```
            --pop-w: 360px;         /* a popover's width (the window's, less 16 a side, on a phone) */
            --qc-w: 184px;          /* a queue counter */
```

- [ ] **Step 4: The builder**

Directly after `emptyState` add:

```js
        /* Queue counters (the mix, spec 6): the queues that make a flow as big
           tiles in flow order, a chevron between, the chosen one a teal fill
           with the focal glow; the other queues as tabs beside them. flow:
           [[key, label, count]]; rest: [[key, label, icon]]. A count not known
           yet keeps its line with a space. */
        function queueCounters(flow, rest, current, onPick, label) {
            const nav = el('nav', 'queues'); nav.setAttribute('aria-label', label || 'Queues');
            const mark = (b, k) => {
                b.type = 'button'; b.dataset.k = k;
                if (k === current) { b.classList.add('on'); b.setAttribute('aria-current', 'page'); }
                b.onclick = () => { if (k !== current) onPick(k); };
            };
            flow.forEach(([k, l, n], i) => {
                if (i) { const s = el('span', 'qsep'); s.setAttribute('aria-hidden', 'true'); s.append(ico(I.chev)); nav.append(s); }
                const b = el('button', 'qc'); mark(b, k);
                b.append(el('span', 'qc-l', l), el('b', 'qc-n', n == null ? ' ' : String(n)));
                nav.append(b);
            });
            const r = el('div', 'qrest');
            rest.forEach(([k, l, icon]) => { const b = el('button', 'qt'); mark(b, k); b.append(ico(icon), document.createTextNode(l)); r.append(b); });
            nav.append(r);
            return nav;
        }
```

- [ ] **Step 5: The rules**

Directly after Task 10's rule `        .cnt { font-size: var(--text-xs); line-height: var(--lh-caption); font-weight: var(--weight-medium); color: var(--text-tertiary);` (it ends `            font-variant-numeric: tabular-nums; }`) add:

```css
        /* QUEUE COUNTERS (the mix, spec 6): the flow's queues as big tiles, the
           label above a 36 figure, a small chevron between; the chosen one a
           teal fill with the focal glow and ink words. The other queues are
           tabs beside them on the chosen recipe: wash, teal ring, ink words. */
        .queues { display: flex; align-items: stretch; gap: var(--control-gap); }
        .qc { width: var(--qc-w); padding: var(--sp-3) var(--sp-4); border: 0; border-radius: var(--radius-tile); background: var(--surface-tertiary);
            display: flex; flex-direction: column; align-items: flex-start; gap: var(--sp-2); font: inherit; color: var(--text-primary); text-align: left; cursor: pointer; }
        .qc-l { font-weight: var(--weight-medium); color: var(--text-secondary); white-space: nowrap; }
        .qc-n { font-size: var(--fig-l); font-weight: var(--weight-semibold); line-height: var(--lh-none); letter-spacing: var(--tr-fig); font-variant-numeric: tabular-nums; }
        .qc.on { background: var(--action-primary); box-shadow: var(--shadow-focal); }
        .qc.on .qc-l { color: var(--text-on-action); }
        .qc:not(.on):hover { background: var(--surface-sunken); }
        .qc:not(.on):active { background: var(--press-fill); }
        .qsep { align-self: center; color: var(--border-emphasis); display: grid; place-items: center; }
        .qsep svg { width: var(--icon-sm); height: var(--icon-sm); stroke-width: var(--icon-stroke-s); }
        .qrest { margin-left: var(--sp-4); align-self: flex-end; display: flex; gap: var(--control-gap); }
        .qt { height: var(--control-h); padding: 0 var(--sp-2); border: 0; border-radius: var(--radius-control); background: none; display: flex; align-items: center;
            gap: var(--control-gap); font: inherit; font-weight: var(--weight-medium); color: var(--text-secondary); white-space: nowrap; cursor: pointer; }
        .qt .ic { color: var(--text-tertiary); }
        .qt.on { background: var(--action-selected); color: var(--text-primary); box-shadow: var(--ring-chosen); }
        .qt.on .ic { color: var(--text-brand); }
        .qt:not(.on):hover { background: var(--surface-tertiary); }
        .qt:not(.on):active { background: var(--press); }
        @media (max-width: 640px) {
            .queues { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); }
            .queues > .qsep { display: none; }
            .qc { width: auto; padding: var(--sp-3); }
            .qc-l { font-size: var(--text-sm); line-height: var(--lh-control); }
            .qc-n { font-size: var(--fig-m); }
            .qrest { grid-column: 1 / -1; margin: 0 calc(-1 * var(--sp-2)); align-self: auto; }
        }
```

After `        .ov-wrap > :is(.tabs, .page-tabs, .seg-row) { margin-bottom: var(--sp-7); }` add:

```css
        /* Queue counters sit 20 under the header and 20 over the list. */
        .ov-hero:has(+ .queues) { margin-bottom: var(--sp-5); }
        .ov-wrap > .queues { margin-bottom: var(--sp-5); }
```

and after Task 10's widget grid rule `        .ov-wrap.wgrid > :is(.tabs, .page-tabs) { margin-inline: calc(-1 * var(--wrap-pad)); margin-bottom: calc(var(--sp-7) - var(--page-rhythm)); }` add:

```css
        .ov-wrap.wgrid > .ov-hero + .queues { margin-top: calc(var(--sp-5) - var(--page-rhythm)); }
        .ov-wrap.wgrid > .queues { margin-bottom: calc(var(--sp-5) - var(--page-rhythm)); }
```

- [ ] **Step 6: Run the tests**

Run: `ONLY=t_queue_counters python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `441 passed, 0 failed`.

- [ ] **Step 7: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Parts: queue counters, big tiles in flow order with the chosen one teal, and the other queues as tabs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 21: The switch

**Files:**
- Modify: `static/index.html:4387-4397` (`.toggle`, `.toggle .sw`, its knob and its on state), the script after `queueCounters` (Task 20)
- Test: `tests/test_frontend.py` (a new test)

**Interfaces:**
- Consumes: `--switch-w` 28, `--switch-h` 16, `--switch-inset` 2 (Task 4), `--shadow-raise`, `--fill-mark`, `syncToggles()` (29459).
- Produces: a switch is a 28 by 16 track, ink-4 when off and teal-line when on, a 12 white knob with the raise shadow, its word beside it at 13 and 500 in ink-2, the whole control 32 tall. `switchBtn(label, on, onToggle)` returns `button.toggle` (`role="switch"`, `aria-checked`) holding `span.sw` and the label; a press flips it and calls `onToggle(now)`.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_a_switch_is_a_track_and_its_word():
    """Spec 6 Switch: a 28 by 16 track, ink-4 when off and teal when on, a 12
    knob, its word beside it; the control 32 tall. Forecast's Compare methods
    is one, built in the script."""
    t = CSS.split("\n        .toggle {")[1].split("}")[0]
    ok("min-height: var(--control-h)" in t and "font-size: var(--text-body)" in t and "font-weight: var(--weight-medium)" in t,
       "the control is 32 and its word 13 at 500")
    sw = CSS.split("\n        .toggle .sw {")[1].split("}")[0]
    ok("background: var(--border-emphasis)" in sw, "off is ink-4")
    knob = CSS.split("\n        .toggle .sw::after {")[1].split("}")[0]
    ok("box-shadow: var(--shadow-raise)" in knob, "the knob is raised")
    ok('.toggle:is(.on, [aria-checked="true"]) .sw { background: var(--fill-mark); }' in CSS, "on is the teal mark")
    ok("function switchBtn(label, on, onToggle) {" in SCRIPT, "a switch can be built in the script")
    fn = fn_src("function switchBtn(label, on, onToggle) {")
    ok("setAttribute('role', 'switch')" in fn and "setAttribute('aria-checked'" in fn and "el('span', 'sw')" in fn, "and says its state")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_a_switch_is_a_track python3 tests/test_frontend.py`
Expected: `FAIL  t_a_switch_is_a_track_and_its_word: the control is 32 and its word 13 at 500`

- [ ] **Step 3: The rules**

Replace `        .toggle { display: inline-flex; align-items: center; gap: var(--sp-2); min-height: var(--control-h-md); font-size: var(--text-xs); color: var(--text-secondary); cursor: pointer; user-select: none; }` with:

```css
        /* THE SWITCH (the mix, spec 6): a 28 by 16 track, ink-4 off and the
           teal mark on, a 12 white knob; its word 8 beside it at 13 and 500 in
           ink-2; the whole control 32 tall. */
        .toggle { display: inline-flex; align-items: center; gap: var(--control-gap); min-height: var(--control-h); font-size: var(--text-body); line-height: var(--lh-control);
            font-weight: var(--weight-medium); color: var(--text-secondary); cursor: pointer; user-select: none; }
```

Replace `        .toggle .sw { width: var(--switch-w); height: var(--switch-h); border-radius: var(--radius-full); background: var(--border-default); position: relative; transition: background var(--dur) var(--ease); }` with:

```css
        .toggle .sw { width: var(--switch-w); height: var(--switch-h); border-radius: var(--radius-full); background: var(--border-emphasis); position: relative; transition: background var(--dur) var(--ease); }
```

In the knob rule replace `            border-radius: var(--radius-circle); background: var(--surface-primary); transition: transform .18s; }` with:

```css
            border-radius: var(--radius-circle); background: var(--surface-primary); box-shadow: var(--shadow-raise); transition: transform .18s; }
```

Replace `        .toggle:is(.on, [aria-checked="true"]) .sw { background: var(--fill-mark); } .toggle:is(.on, [aria-checked="true"]) .sw::after { transform: translateX(calc(var(--switch-w) - var(--switch-h))); background: var(--surface-primary); }` with:

```css
        .toggle:is(.on, [aria-checked="true"]) .sw { background: var(--fill-mark); }
        .toggle:is(.on, [aria-checked="true"]) .sw::after { transform: translateX(calc(var(--switch-w) - var(--switch-h))); background: var(--surface-primary); }
        .toggle:hover .sw { background: var(--text-tertiary); }
        .toggle:is(.on, [aria-checked="true"]):hover .sw { background: var(--text-brand); }
```

Replace `        #deep-toggle { border: 0; background: none; padding: 0; font: inherit; font-size: var(--text-xs); color: var(--text-secondary); }` with:

```css
        #deep-toggle { border: 0; background: none; padding: 0; font: inherit; font-size: var(--text-body); font-weight: var(--weight-medium); color: var(--text-secondary); }
```

- [ ] **Step 4: The builder**

Directly after `queueCounters` add:

```js
        /* A switch built in the script (the static ones in the markup are
           wired by syncToggles). It flips on a press and says its state. */
        function switchBtn(label, on, onToggle) {
            const b = el('button', 'toggle' + (on ? ' on' : ''));
            b.type = 'button'; b.setAttribute('role', 'switch'); b.setAttribute('aria-checked', String(!!on));
            b.append(el('span', 'sw'), document.createTextNode(label));
            b.onclick = () => {
                const now = b.getAttribute('aria-checked') !== 'true';
                b.setAttribute('aria-checked', String(now)); b.classList.toggle('on', now);
                onToggle(now);
            };
            return b;
        }
```

- [ ] **Step 5: Run the tests**

Run: `ONLY=t_a_switch_is_a_track python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `442 passed, 0 failed`.

- [ ] **Step 6: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Parts: the switch, a 28 by 16 track ink-4 off and teal on, and a script builder for one

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 22: States: hover only where there is a pointer, pressed, focus

**Files:**
- Create: `$S/planwork/hover_gate.py` (scratch, not committed)
- Modify: `static/index.html` (every rule whose selector has `:hover`, in place; `:324-326` the global focus rule)
- Test: `tests/test_frontend.py` (`t_the_keyboard_highlight_looks_exactly_like_the_mouse_one` 4850, a new test)

**Interfaces:**
- Consumes: every part above.
- Produces: no `:hover` rule outside `@media (hover: hover)` (a touch screen keeps `:hover` after a tap, which left a tapped row lit); focus is the 2px teal-line outline 2 off the edge everywhere.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_hover_is_only_for_a_pointer_that_hovers():
    """Spec 4.6 and principle 6: a touch screen keeps :hover after a tap, so a
    tapped row or button stayed lit. Every hover rule lives inside
    @media (hover: hover); pressed is one step darker than hover on every
    device; focus is a 2px teal-line ring 2 off the edge."""
    outside = [s for s, b in _rules(CSS) if ":hover" in s and "@media (hover: hover)" not in s]
    ok(not outside, "%d hover rules outside @media (hover: hover): %s" % (len(outside), outside[:5]))
    ok(CSS.count("@media (hover: hover)") >= 80, "and they are all still there, gated")
    g = CSS.split(":is(button, select, input, textarea, summary, [role=\"button\"], .toggle,\n            [tabindex], .convos):focus-visible {")[1].split("}")[0]
    ok("outline: var(--focus-outline); outline-offset: var(--sp-0-5);" in g, "focus sits 2 off the edge")
    for sel, want in ((".btn:active {", "var(--press)"), (".dmenu-item:active {", "var(--press)"), (".nav-item:active {", "var(--chrome-press)"),
                      (".topbar-search:active {", "var(--press-fill)"), (".btn-primary:active {", "var(--action-active)")):
        ok(want in CSS.split(sel)[1].split("}")[0], sel + " presses to " + want)
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_hover_is_only python3 tests/test_frontend.py`
Expected: `FAIL  t_hover_is_only_for_a_pointer_that_hovers: ` then a count of about 100 hover rules outside `@media (hover: hover)`.

- [ ] **Step 3: Write the script**

Create `/Users/cameron/Desktop/claude/gizmo/.design-rig/planwork/hover_gate.py`:

```python
"""Move every :hover rule in the page's stylesheet inside @media (hover: hover),
in place, so the cascade order is unchanged. A rule whose selector list mixes
hover and non-hover selectors is split: the non-hover part stays as it was.
Rules already inside @media (hover: hover) are left alone, so it can run twice."""
import re, sys
P = sys.argv[1] if len(sys.argv) > 1 else "static/index.html"
html = open(P, encoding="utf-8").read()
a = html.index("<style>") + len("<style>"); b = html.index("</style>", a)
css = html[a:b]

def rules(css):
    out, stack, sel_start, i, n = [], [], 0, 0, len(css)
    while i < n:
        if css.startswith("/*", i):
            i = css.index("*/", i) + 2; continue
        ch = css[i]
        if ch == "{":
            stack.append((sel_start, i)); i += 1; continue
        if ch == "}":
            s0, o = stack.pop(); body = css[o + 1:i]
            if "{" not in body:
                ctx = [css[x:y].strip() for x, y in stack]
                out.append((s0, i + 1, css[s0:o], body, ctx))
            sel_start = i + 1; i += 1; continue
        if ch == ";" and not stack: sel_start = i + 1
        i += 1
    return out

def split_sel(sel):
    parts, depth, cur = [], 0, ""
    for ch in sel:
        if ch in "([": depth += 1
        if ch in ")]": depth -= 1
        if ch == "," and depth == 0: parts.append(cur); cur = ""; continue
        cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]

edits = []
for s0, e, sel, body, ctx in rules(css):
    clean = re.sub(r"/\*.*?\*/", "", sel, flags=re.S)
    if ":hover" not in clean or any("hover: hover" in c for c in ctx):
        continue
    m = re.match(r"(\s*(?:/\*.*?\*/\s*)*)", sel, re.S)       # comments and indent before the rule stay put
    comment = m.group(1); real = sel[len(comment):].strip()
    indent = comment.split("\n")[-1]
    sels = split_sel(real)
    hov = [x for x in sels if ":hover" in x]; rest = [x for x in sels if ":hover" not in x]
    rule_text = css[s0:e][len(comment):]
    tail = rule_text[rule_text.index("{"):]
    if rest:
        new = comment + ", ".join(rest) + " " + tail + "\n" + indent + "@media (hover: hover) { " + ", ".join(hov) + " " + tail + " }"
    else:
        new = comment + "@media (hover: hover) { " + rule_text.strip() + " }"
    edits.append((s0, e, new))
for s0, e, new in sorted(edits, reverse=True):
    css = css[:s0] + new + css[e:]
html = html[:a] + css + html[b:]
open(P, "w", encoding="utf-8").write(html)
left = [r for r in rules(css) if ":hover" in re.sub(r"/\*.*?\*/", "", r[2], flags=re.S) and not any("hover: hover" in c for c in r[4])]
print(len(edits), "hover rules gated;", len(left), "left outside @media (hover: hover)")
```

- [ ] **Step 4: Run it**

Run: `python3 /Users/cameron/Desktop/claude/gizmo/.design-rig/planwork/hover_gate.py static/index.html`
Expected: `N hover rules gated; 0 left outside @media (hover: hover)` with N about 100. Then `git diff --stat static/index.html` shows only `static/index.html` changed, and `grep -c "@media (hover: hover)" static/index.html` prints the same N.

- [ ] **Step 5: Focus 2 off the edge**

Replace:

```css
        :is(button, select, input, textarea, summary, [role="button"], .toggle,
            [tabindex], .convos):focus-visible {
            outline: var(--focus-outline); outline-offset: 1px; }
```

with:

```css
        :is(button, select, input, textarea, summary, [role="button"], .toggle,
            [tabindex], .convos):focus-visible {
            outline: var(--focus-outline); outline-offset: var(--sp-0-5); }
```

- [ ] **Step 6: Update the highlight guard**

Replace the body of `t_the_keyboard_highlight_looks_exactly_like_the_mouse_one` (its `ok`) with:

```python
    # Since the mix (2026-10-06) a hover lives in @media (hover: hover), so the
    # two are two rules; they must still paint exactly the same thing.
    on = re.search(r"\.crm-ta-drop button\.hot, \.crm-ta-drop button\.on \{([^}]*)\}", CSS)
    hov = re.search(r"\.crm-ta-drop button:hover \{([^}]*)\}", CSS)
    ok(on and hov and on.group(1).strip() == hov.group(1).strip(),
       "the keyboard highlight paints exactly what the hover paints rather than inventing a colour")
```

- [ ] **Step 7: Run the tests**

Run: `ONLY=t_hover_is_only python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `443 passed, 0 failed`.

- [ ] **Step 8: Look at it**

In the rig at 390 with touch emulation (Chrome DevTools, a phone): tap a nav item, a list row and a button; none stays lit after the finger lifts. With a mouse at 1440 every hover still shows.

- [ ] **Step 9: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "States: hover only where a pointer hovers, pressed one step darker, focus 2 off the edge

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 23: The widget grid's outline only in Customize mode

**Files:**
- Modify: `static/index.html:1156-1184` (Customize mode)
- Test: `tests/test_frontend.py` (a new test)

**Interfaces:**
- Consumes: the unboxed sections (Task 11), `--shadow-pop`.
- Produces: at rest a section draws no edge; in Customize mode each draws a dashed `--border-emphasis` outline 8 outside its content and its hide button is a 24 ghost square on the pop shadow.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_a_section_shows_its_edge_only_while_it_is_being_moved():
    """Spec 8.3 Report: Customize keeps its drag; outlines show only in
    Customize mode. With no boxes at rest, an unboxed section needs room round
    its dashed edge, and its hide button floats on the pop shadow."""
    edit = CSS.split(".ov-wrap.wg-editing > [data-widget]:not(:focus-visible) {")[1].split("}")[0]
    ok("dashed var(--border-emphasis)" in edit and "outline-offset: var(--sp-2)" in edit, "a dashed edge 8 outside the content, in Customize mode")
    rest = [s for s, b in _rules(CSS) if "[data-widget]" in s and "wg-editing" not in s and re.search(r"outline:|border:", b)]
    ok(not rest, "and none at rest: %s" % rest[:3])
    hide = CSS.split(".ov-wrap.wg-editing > [data-widget] > .wg-hide {")[1].split("}")[0]
    ok("box-shadow: var(--shadow-pop)" in hide and "width: var(--control-h-sm)" in hide, "the hide button is a 24 square on the pop shadow")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_a_section_shows_its_edge python3 tests/test_frontend.py`
Expected: `FAIL  t_a_section_shows_its_edge_only_while_it_is_being_moved: a dashed edge 8 outside the content, in Customize mode`

- [ ] **Step 3: The rules**

Replace:

```css
        .ov-wrap.wg-editing > [data-widget]:not(:focus-visible) {
            outline: var(--bw-hairline) dashed var(--border-emphasis); outline-offset: var(--sp-0-5); }
```

with:

```css
        /* A section has no box at rest (the mix), so its dashed edge in
           Customize mode stands 8 clear of its content. */
        .ov-wrap.wg-editing > [data-widget]:not(:focus-visible) {
            outline: var(--bw-hairline) dashed var(--border-emphasis); outline-offset: var(--sp-2); }
```

Replace:

```css
        .ov-wrap.wg-editing > [data-widget] > .wg-hide { position: absolute; top: calc(-1 * var(--sp-3)); right: calc(-1 * var(--sp-3)); z-index: 1;
            margin: 0; padding: var(--sp-1); background: var(--surface-primary); box-shadow: var(--ring-default);
            border-radius: var(--radius-control); cursor: pointer; }
```

with:

```css
        .ov-wrap.wg-editing > [data-widget] > .wg-hide { position: absolute; top: calc(-1 * var(--sp-3)); right: calc(-1 * var(--sp-3)); z-index: 1;
            margin: 0; padding: 0; width: var(--control-h-sm); height: var(--control-h-sm); min-width: 0; min-height: 0;
            background: var(--surface-primary); box-shadow: var(--shadow-pop);
            border-radius: var(--radius-control); cursor: pointer; }
```

- [ ] **Step 4: Run the tests**

Run: `ONLY=t_a_section_shows_its_edge python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `444 passed, 0 failed`.

- [ ] **Step 5: Look at it**

Overview: press Customise. Every section shows a dashed edge 8 outside it and a small floating hide button at its top right; drag one: it lifts on the pop shadow. Press Done: no edges remain.

- [ ] **Step 6: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Parts: a section shows its dashed edge only in Customize mode, 8 clear of its content

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 24: The phone: every target 40, control text 14, a 16 gutter

**Files:**
- Modify: `static/index.html` (a new phone block at the end of the parts, before `/* ONE TAG.`)
- Test: `tests/test_frontend.py` (a new test)

**Interfaces:**
- Consumes: every part; `--control-h-lg` 40, `--text-sm` 14.
- Produces: at 640 and under every button, field, search, segment, menu row, list row, nav row, queue tab and switch is 40 tall (icon buttons 40 square), control and row-title text is 14, an info button keeps its 24 look inside a 40 target that grows away from its words, section heads are 40.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_every_target_on_a_phone_fits_a_finger():
    """Spec principle 6 and 4.3: on a phone every target is 40 and every
    control and row title is 14; the gutter is 16 and sections are 32 apart.
    Keyed on the width (640), which is what the 390 audit measures. An info
    button keeps its 24 look; its 40 target grows away from its words."""
    blocks = [b for p, b in css_blocks(CSS) if p.endswith("@media (max-width: 640px)") and "THE PHONE" in p]
    ok(len(blocks) == 1, "one phone block for the parts")
    b = blocks[0]
    for sel in (".btn", ".icon-btn", ".chip", ".toggle", ".qt", ".dmenu-item", ".rlist-row", ".nav-item", ".tbl-search", "select"):
        ok(sel in b, sel + " is in the 40 rule")
    ok("min-height: var(--control-h-lg)" in b and "font-size: var(--text-sm)" in b, "40 tall, 14 words")
    ok(".segmented > button { height: calc(var(--control-h-lg) - 2 * var(--sp-0-5)); }" in b, "a segment fills a 40 track")
    ok("padding-right: calc(var(--control-h-lg) - var(--control-h-sm))" in b, "an info button's target grows away from its words")
    ok(re.search(r":root \{ --wrap-pad: var\(--sp-4\); \}", CSS), "the gutter is 16")
    ok("@media (pointer: coarse) { input:not([type=checkbox]):not([type=radio]), textarea, select { font-size: var(--text-md); } }" in CSS,
       "and a real field under a finger keeps 16 so iOS does not zoom into it")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_every_target_on_a_phone python3 tests/test_frontend.py`
Expected: `FAIL  t_every_target_on_a_phone_fits_a_finger: one phone block for the parts`

- [ ] **Step 3: The phone block**

Directly before the comment that begins `        /* ONE TAG. Every small label that only displays something` add:

```css
        /* THE PHONE (the mix, spec principle 6 and 4.3): every target is 40 and
           every control and row title 14. The 16 gutter and the 32 between
           sections are set where those live. A real field under a finger keeps
           16 (the pointer: coarse rule), or iOS zooms into it. */
        @media (max-width: 640px) {
            :is(.btn, .btn-sm, .icon-btn, .chip, .toggle, .qt, .dmenu-item, .rlist-row, .nav-item, .nav-group, .convo, .tbl-search, .topbar-search,
                input[type=text], input[type=number], input[type=date], input[type=search], input[type=email], input[type=password],
                input[type=url], input[type=tel], input:not([type]), select, details.sect summary) { min-height: var(--control-h-lg); }
            .tbl-search { height: var(--control-h-lg); }
            .segmented > button { height: calc(var(--control-h-lg) - 2 * var(--sp-0-5)); }
            :is(.btn, .btn-sm, .segmented > button, .tab, .chip, .toggle, .qt, .dmenu-item, .nav-item, .convo, .rlist-row, details.sect summary) { font-size: var(--text-sm); }
            :is(.icon-btn, .btn-sm.btn-icon, .topbar .icon-btn, .topbar-search) { min-width: var(--control-h-lg); }
            .btn-sm.btn-icon { width: var(--control-h-lg); }
            .section-title, .card-head { min-height: var(--control-h-lg); }
            /* An info button keeps its 24 look; its 40 target grows up, down
               and away from its words, so it never covers them. */
            .info { width: var(--control-h-lg); height: var(--control-h-lg); padding-right: calc(var(--control-h-lg) - var(--control-h-sm));
                margin-block: calc((var(--lh-control) - var(--control-h-lg)) / 2); margin-right: calc(var(--control-h-sm) - var(--control-h-lg)); }
            .info::before { inset: auto; left: 0; top: 50%; width: var(--control-h-sm); height: var(--control-h-sm); margin-top: calc(var(--control-h-sm) / -2); }
        }
```

- [ ] **Step 4: Run the tests**

Run: `ONLY=t_every_target_on_a_phone python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `445 passed, 0 failed`.

- [ ] **Step 5: Measure it**

Run the 165-screen audit at the phone size only, with no shots:

```bash
S=/Users/cameron/Desktop/claude/gizmo/.design-rig
cd "$S/spacing" && SIZES=390x844 SHOTS=0 node audit.js "$S/planwork/phone24" && python3 analyse.py "$S/planwork/phone24" > "$S/planwork/phone24/report.md"; head -20 "$S/planwork/phone24/report.md"
```

Expected: `screens 33` (every view and tab at 390), `Script errors: 0`, `Page wider than the screen: ` with nothing after it. The overlaps, escapes and clipping sections are the starting list for Phase 5; any hit on a part changed in this phase is fixed in that part's rule before committing.

- [ ] **Step 6: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Parts: on a phone every target is 40 and every control and row title 14

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 25: The type sweep: every screen rule on the five steps

**Files:**
- Create: `$S/planwork/type_sweep.py` (scratch, not committed)
- Modify: `static/index.html` (every screen rule's `font-size` and `line-height`, in place; `:177-179` the retired type tokens; after `body {` the app's base; a screen-only icon stroke rule)
- Test: `tests/test_frontend.py` (`t_the_app_wide_layout_sweep_holds` 9151, a new test)

**Interfaces:**
- Consumes: the type tokens (Task 4).
- Produces: every screen rule reads `--text-micro`, `--text-xs`, `--text-body`, `--text-sm` (order names and phone rules), `--text-head`, `--text-md` (the wordmark and a phone field), `--text-title`, `--text-2xl` (the phone title) or a figure token, on one of `--lh-caption`, `--lh-control`, `--lh-title`, `--lh-none`, `--lh-prose` (Guide and chat prose). The app's own text is 13/20; `#label-print` keeps body's 14 on 1.5. Tracking is none except the titles' and figures' tokens. The report's print-only header (`.print-head`) is paper and keeps its type. Every interface icon is drawn at 1.75 on screen. `--text-lg`, `--text-xl`, `--text-3xl`, `--lh-tight`, `--lh-snug` are gone.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_text_comes_in_the_five_steps():
    """Spec 4.2: Inter at 11/16, 12/16, 13/20, 14/20 and 15/20; Bricolage at the
    wordmark's 16/20 and a page title's 26/32 (24 on a phone); figures at 44,
    36, 28 and 24 on a line of 1. Every screen rule's size and line height is
    one of them, from the token block. Print keeps its own, untouched."""
    # The print guard's own list, and the report's print-only header, which
    # is paper too: neither is screen type.
    pr = re.compile(r"label-sheet|day-sheet|loan-sticker|guide-print-row|#label-print|printing-label|@media print|@page|print-head")
    sizes = {"var(--text-micro)", "var(--text-xs)", "var(--text-body)", "var(--text-sm)", "var(--text-head)", "var(--text-md)",
             "var(--text-title)", "var(--text-2xl)", "var(--fig-xl)", "var(--fig-l)", "var(--fig-m)", "var(--fig-s)", "inherit"}
    lhs = {"var(--lh-caption)", "var(--lh-control)", "var(--lh-title)", "var(--lh-none)", "var(--lh-prose)", "inherit", "normal"}
    bad = []
    for sel, body in _rules(CSS):
        if pr.search(sel) or sel.strip() == "body":
            continue
        for m in re.finditer(r"(?<![\w-])font-size\s*:\s*([^;}]+)", body):
            if m.group(1).strip() not in sizes: bad.append(sel[:50] + " size " + m.group(1).strip())
        for m in re.finditer(r"(?<![\w-])line-height\s*:\s*([^;}]+)", body):
            if m.group(1).strip() not in lhs: bad.append(sel[:50] + " line " + m.group(1).strip())
    ok(not bad, "%d off the five steps: %s" % (len(bad), bad[:6]))
    track = [sel[:50] + " " + m.group(1).strip() for sel, body in _rules(CSS) if not pr.search(sel)
             for m in re.finditer(r"(?<![\w-])letter-spacing\s*:\s*([^;}]+)", body)
             if m.group(1).strip() not in ("normal", "0", "var(--tr-title)", "var(--tr-fig)")]
    ok(not track, "tracking only on titles and figures, from the token block: %s" % track[:6])
    md = [s for s, b in _rules(CSS) if not pr.search(s) and "font-size: var(--text-md)" in b]
    ok(all(".brand-name" in s or "pointer: coarse" in s for s in md), "16 is the wordmark's, and a phone field's: %s" % md)
    for gone in ("--text-lg", "--text-xl", "--text-3xl", "--lh-tight", "--lh-snug"):
        ok(gone + ":" not in CSS, gone + " has left the token block")
    ok('body > :where(:not([id="label-print"])) { font-size: var(--text-body); line-height: var(--lh-control); }' in CSS,
       "the app's own text is 13/20, and the print staging area keeps body's own")
    ok('@media screen { :where(svg[stroke-width="2"]) { stroke-width: var(--icon-stroke); } }' in CSS, "every interface icon is drawn at 1.75")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_text_comes_in_the_five python3 tests/test_frontend.py`
Expected: `FAIL  t_text_comes_in_the_five_steps: ` followed by a count near 300 and the first six rules still on `--text-sm`, `--text-lg` or `--lh-body`.

- [ ] **Step 3: Write the script**

Create `/Users/cameron/Desktop/claude/gizmo/.design-rig/planwork/type_sweep.py`:

```python
"""Put every screen rule's type on the mix's five steps (spec 4.2), in place.
Print rules, the body rule and :root are left exactly as they are. Prints what
it changed, by mapping."""
import re, sys, collections
P = sys.argv[1] if len(sys.argv) > 1 else "static/index.html"
html = open(P, encoding="utf-8").read()
a = html.index("<style>") + len("<style>"); b = html.index("</style>", a)
css = html[a:b]
# The print guard's list, plus the report's print-only header: paper, not screen type.
PRINT = re.compile(r"label-sheet|day-sheet|loan-sticker|guide-print-row|#label-print|printing-label|@media print|@page|print-head")

def rules(css):
    out, stack, sel_start, i, n = [], [], 0, 0, len(css)
    while i < n:
        if css.startswith("/*", i):
            i = css.index("*/", i) + 2; continue
        ch = css[i]
        if ch == "{":
            stack.append((sel_start, i)); i += 1; continue
        if ch == "}":
            s0, o = stack.pop()
            if "{" not in css[o + 1:i]:
                ctx = " ".join(re.sub(r"\s+", " ", css[x:y]).strip() for x, y in stack)
                sel = re.sub(r"\s+", " ", re.sub(r"/\*.*?\*/", "", css[s0:o], flags=re.S)).strip()
                out.append((o + 1, i, sel, ctx))
            sel_start = i + 1; i += 1; continue
        if ch == ";" and not stack: sel_start = i + 1
        i += 1
    return out

SIZE = {"--text-lg": "--text-head", "--text-xl": "--text-head", "--text-3xl": "--fig-m"}
done = collections.Counter(); edits = []
for b0, b1, sel, ctx in rules(css):
    if PRINT.search(sel + " " + ctx) or sel == "body" or ":root" in sel:
        continue
    body = css[b0:b1]; new = body
    phone = "max-width: 640px" in ctx or "pointer: coarse" in ctx
    page_sample = ".ds-type-page" in sel
    def size(m):
        t = m.group(1)
        if page_sample:
            done["ds-type-page -> text-title"] += 1; return "font-size: var(--text-title)"
        if t == "--text-sm" and not phone and not re.search(r"\.lbl-name\b", sel):
            done["text-sm -> text-body"] += 1; return "font-size: var(--text-body)"
        if t == "--text-md" and ".brand-name" not in sel and "pointer: coarse" not in ctx:
            done["text-md -> text-head"] += 1; return "font-size: var(--text-head)"
        if t == "--text-2xl" and ".ov-hero h2" not in sel:
            done["text-2xl -> fig-s"] += 1; return "font-size: var(--fig-s)"
        if t in SIZE:
            done[t[2:] + " -> " + SIZE[t][2:]] += 1; return "font-size: var(" + SIZE[t] + ")"
        return m.group(0)
    new = re.sub(r"(?<![\w-])font-size: var\((--[\w-]+)\)", size, new)
    fs = re.search(r"(?<![\w-])font-size: var\((--[\w-]+)\)", new)
    small = fs and fs.group(1) in ("--text-xs", "--text-micro")
    def lh(m):
        t = m.group(1)
        if t in ("--lh-tight", "--lh-snug", "--lh-body"):
            to = "--lh-title" if page_sample else ("--lh-caption" if small else "--lh-control")
            done[t[2:] + " -> " + to[2:]] += 1; return "line-height: var(" + to + ")"
        return m.group(0)
    new = re.sub(r"(?<![\w-])line-height: var\((--[\w-]+)\)", lh, new)
    if page_sample:
        new = new.replace("font-weight: var(--weight-regular)", "font-weight: var(--weight-semibold)")
    # Tracking only on titles and figures (spec 4.2): a figure (a figure size
    # or tabular numbers) takes the figures' -0.03em, everything else none.
    def tr(m):
        v = m.group(1).strip()
        if v in ("normal", "0", "var(--tr-title)", "var(--tr-fig)"):
            return m.group(0)
        to = "var(--tr-fig)" if (re.search(r"font-size: var\(--fig-", new) or "tabular-nums" in new) else "normal"
        done["tracking " + v + " -> " + ("tr-fig" if to != "normal" else "normal")] += 1
        return "letter-spacing: " + to
    new = re.sub(r"(?<![\w-])letter-spacing:\s*([^;}]+)", tr, new)
    if new != body: edits.append((b0, b1, new))
for b0, b1, new in sorted(edits, reverse=True):
    css = css[:b0] + new + css[b1:]
html = html[:a] + css + html[b:]
open(P, "w", encoding="utf-8").write(html)
for k, v in sorted(done.items()): print("%4d  %s" % (v, k))
```

- [ ] **Step 4: Run it**

Run: `python3 /Users/cameron/Desktop/claude/gizmo/.design-rig/planwork/type_sweep.py static/index.html`
Expected: a list of mappings, the largest `text-sm -> text-body` at about 160, then `lh-body -> lh-control` about 30, `lh-body -> lh-caption` about 20, about a dozen `tracking ... -> normal` or `-> tr-fig` lines, and small counts for the rest. `grep -c "var(--text-lg)\|var(--text-xl)\|var(--text-3xl)\|var(--lh-tight)\|var(--lh-snug)" static/index.html static/composer.js` prints `static/index.html:0` and `static/composer.js:0`.

- [ ] **Step 5: Retire the old steps, set the app's base, draw icons at 1.75**

In `:root` replace:

```
            --text-micro: 11px; --text-xs: 12px; --text-body: 13px; --text-sm: 14px; --text-head: 15px; --text-md: 16px;
            --text-lg: 18px; --text-xl: 20px; --text-2xl: 24px; --text-title: 26px; --text-3xl: 30px;
```

with:

```
            --text-micro: 11px; --text-xs: 12px; --text-body: 13px; --text-sm: 14px; --text-head: 15px; --text-md: 16px;
            --text-2xl: 24px; --text-title: 26px;
```

and replace `            --lh-none: 1; --lh-tight: 1.15; --lh-snug: 1.35; --lh-body: 1.5; --lh-prose: 1.6;` with:

```
            --lh-none: 1; --lh-body: 1.5; --lh-prose: 1.6;   /* 1.5: what body gives the A4 sheets; 1.6: Guide and chat prose */
```

and in the comment above them replace the two lines `               600 at 44, 36, 28 and 24, tabular, on a line of 1. --text-lg,` and `               --text-xl and --text-3xl leave in the type sweep (Task 25). */` with the one line `               600 at 44, 36, 28 and 24, tabular, on a line of 1. The old 18, 20 and 30 steps went in the type sweep. */`.

Directly after the `body { ... }` rule (it ends `            text-wrap: pretty; }`) add:

```css
        /* The app's own text is the body step, 13/20 (the mix, 4.2), set on
           everything body holds except the print staging area: the A4 sheets
           keep the 14px on 1.5 they inherit from body itself. The area is
           named by its id attribute: this rule styles everything but paper,
           so it stays out of the print freeze's pinned set (Task 1). */
        body > :where(:not([id="label-print"])) { font-size: var(--text-body); line-height: var(--lh-control); }
        /* Every interface icon at 1.75 (the icon table draws them at 2); a 14
           inline glyph sets 2 on its own rule, which outranks this. Screen
           only, so nothing printed changes. */
        @media screen { :where(svg[stroke-width="2"]) { stroke-width: var(--icon-stroke); } }
```

- [ ] **Step 6: Update the layout guard**

In `t_the_app_wide_layout_sweep_holds` replace the key `".lia-name { font-size: var(--text-sm); font-weight: var(--weight-medium); flex: 0 0 clamp(150px, 30%, 320px);"` with `".lia-name { font-size: var(--text-body); font-weight: var(--weight-medium); flex: 0 0 clamp(150px, 30%, 320px);"`.

- [ ] **Step 7: Run the tests**

Run: `ONLY=t_text_comes_in_the_five python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `446 passed, 0 failed`. If another test fails on a rule that pinned `font-size: var(--text-sm)` or a retired line height, change that one assertion to the swept value (the rule and the sweep's mapping table above say which) and say so in the commit message.

- [ ] **Step 8: Measure the text styles**

Run the audit at 1440 for Forecast and Production Manager with no shots and count the distinct text styles the measure tool reports in Task 45; at this point it is enough that `SIZES=1440x900 VIEWS=forecast,labels SHOTS=0 node audit.js "$S/planwork/type25"` (from `$S/spacing`) ends `screens 7` with no script errors.

- [ ] **Step 9: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Type: every screen rule on the five steps with one line height each, the app at 13/20, icons at 1.75; the print sheets untouched

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Phase 4: Forecast and Production Manager, matched to the mockup

Each task here changes one block of the screen; the rig's forecast must be posted (Global Constraints) before looking at Forecast. Compare with `docs/design/mix/mix.html` (01 Forecast, 02 Production Manager, the three details, the two phones) side by side at 1440 and 390.

### Task 26: Forecast's header, tab row and How it works

**Files:**
- Modify: `static/index.html:5606` (`MONTH_ABBR`), the icon table, `:4194-4198` (`.fc-seg-lbl`), `forecastUploadButton` (14695), `renderForecast` (15605-15837: the header block and the "How this forecast works" block), new functions after `fcAlgorithmsCard`
- Test: `tests/test_frontend.py` (`t_the_forecast_tab_exists_and_is_gated` 2210, `t_the_forecast_tab_shows_the_five_plain_models_and_what_they_scored` 4236, `t_every_report_view_with_several_blocks_names_its_cards` 7001, `t_a_page_is_called_what_the_sidebar_calls_it` 8463, `t_the_scenario_label_sits_with_its_control` 8061, a new test)

**Interfaces:**
- Consumes: `pageHead` (Task 7), `howItWorks` (Task 13), `financeTabs(active, updated, actions)` (11909), `sheetModal(title)` (13255), `fcOptimisedCard(latest)`, `fcAlgorithmsCard(latest)`, `fcUntitled(node)`.
- Produces: `MONTH_NAMES`; `fcMonthName('2026-10')` returns `'October'`; `I.compass`, `I.target`, `I.shield`; `fcPage(title, build)` opens a wide window holding `build()`; `fcTrust(latest)` and `fcPlanJudged(c, latest)` return the bodies of "How much to trust it" and "The plan it is judged against"; `fcHowItWorks(c, latest, sc)` returns the header's How it works button. `renderForecast` declares `latest`, `names` and `sc` at its top.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_the_forecast_header_is_the_mix_header():
    """Spec 8.1: Forecast with Beta; a status line saying the month the reader
    is in and which run this is; How it works (the four method pages, each in
    a window) and Upload workbook; the Finance tabs with the Plan chooser at
    the row's right. The intro paragraph and the How this forecast works
    section are gone from the page."""
    fn = SCRIPT.split("function renderForecast()")[1].split("\n        async function showReconView")[0]
    ok("pageHead({ view: 'forecast', title: 'Forecast'," in fn and "'Run as of ' + fmtDate(latest.as_of)" in fn,
       "the header is the one builder, with its status line")
    ok("fcHowItWorks(c, latest, sc)" in fn and "financeTabs('forecast', '', plan)" in fn,
       "How it works is in the header and the Plan chooser on the tab row")
    ok("el('span', 'fc-seg-lbl', 'Plan')" in fn, "the chooser is labelled Plan")
    ok("'How this forecast works'" not in SCRIPT and "never a promise.'" not in fn, "the method section and the intro are gone")
    how = fn_src("function fcHowItWorks(c, latest, sc) {")
    for t in ("'Which method is running, and why'", "'How each one works, and how right it has been'", "'How much to trust it'",
              "'The plan it is judged against'", "'The Forecast in the Guide'"):
        ok(t in how, "How it works holds " + t)
    ok("fcPage(" in how and "function fcPage(title, build) {" in SCRIPT, "each opens in a window")
    ok("'Upload workbook'" in fn_src("function forecastUploadButton()"), "the upload button says Upload workbook")
    ok("const MONTH_NAMES = ['January'," in SCRIPT, "the status line says the month in full")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_the_forecast_header_is python3 tests/test_frontend.py`
Expected: `FAIL  t_the_forecast_header_is_the_mix_header: the header is the one builder, with its status line`

- [ ] **Step 3: Month names and icons**

Replace `        const MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];` with:

```js
        const MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
```

After `        const fcMonth = (m) => m ? (MONTH_ABBR[(+m.slice(5, 7)) - 1] + ' ' + m.slice(0, 4)) : '';` add:

```js
        const fcMonthName = (m) => m ? MONTH_NAMES[(+m.slice(5, 7)) - 1] : '';
```

In `const I = {` after `            wallet: SV(` add:

```js
            compass: SV('<circle cx="12" cy="12" r="10"></circle><path d="m16.24 7.76-2.12 6.36-6.36 2.12 2.12-6.36z"></path>'),
            target: SV('<circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="12" r="6"></circle><circle cx="12" cy="12" r="2"></circle>'),
            shield: SV('<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"></path><path d="m9 12 2 2 4-4"></path>'),
```

- [ ] **Step 4: Upload workbook**

In `forecastUploadButton` replace `            const b = el('button', 'btn btn-sm', 'Upload cash flow workbook'); b.prepend(ico(I.upload));` with:

```js
            const b = el('button', 'btn', 'Upload workbook'); b.prepend(ico(I.upload));
```

- [ ] **Step 5: The header and the tab row**

In `renderForecast` replace everything from the line `            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.insight;` through the line `            if (!latest) { box.append(forecastSetupCard(c)); return; }` with:

```js
            const latest = c && c.latest;
            const names = (latest && latest.scenarios) || [];
            if (!forecastScenario || names.indexOf(forecastScenario) < 0) forecastScenario = names[0] || '';
            const sc = forecastScenario;
            /* The header (the mix, spec 8.1): Forecast with Beta, a status line
               saying the month the reader is in and which run this is, then How
               it works and Upload workbook. No paragraph: the page is money. */
            const cm = latest ? fcCurrentMonth(latest) : '';
            box.append(pageHead({ view: 'forecast', title: 'Forecast',
                status: latest ? [fcMonthName(cm) + ' ' + cm.slice(0, 4), 'Run as of ' + fmtDate(latest.as_of)] : null,
                actions: [latest ? fcHowItWorks(c, latest, sc) : null, c && c.can_upload ? forecastUploadButton() : null] }));
            /* The Finance tabs, with the plan the page is judged against chosen
               at the row's right: it governs everything under it. */
            const plan = latest && names.length > 1 ? [el('span', 'fc-seg-lbl', 'Plan'),
                segmented(names.map(n => ({ label: n, value: n })), sc, (v) => { forecastScenario = v; renderForecast(); }, { label: 'Plan' })] : [];
            box.append(financeTabs('forecast', '', plan));
            if (!c) { box.append(el('div', 'empty', 'Loading…')); return; }
            if (c.error) { box.append(loadFailure('The forecast could not be read. ' + c.error, refreshForecast)); return; }
            if (!latest) { box.append(forecastSetupCard(c)); return; }
```

Then delete these lines further down in `renderForecast` (the rail is pageHead's, and `names` and `sc` are declared above now; `hero.append(heroAct(''));` also appears in `renderConnector`, `renderRecon` and `renderMail`, which keep theirs until Tasks 37, 38 and 41):

```js
            hero.append(heroAct(''));
```

```js
            const names = latest.scenarios || [];
            if (!forecastScenario || names.indexOf(forecastScenario) < 0) forecastScenario = names[0] || '';
            const sc = forecastScenario;
```

and delete the Plan chooser that rode in the overview's title:

```js
            if (names.length > 1) {
                const t0 = ov.querySelector('.section-title');
                if (t0) {
                    t0.append(el('span', 'fc-seg-lbl', 'Plan scenario'));
                    t0.append(segmented(names.map(n => ({ label: n, value: n })), sc,
                        (v) => { forecastScenario = v; renderForecast(); }));
                }
            }
```

The label now sits in the tab row's end group, before its chooser, so it loses the `order: 1` that carried it past a heading's spacer. Replace the comment that begins `        /* Ordered past the heading's spacer WITH its control.` (three lines) and the rule that begins `        .fc-seg-lbl {` (two lines) with:

```css
        /* "Plan" names the chooser after it, at the tab row's right (the mix). */
        .fc-seg-lbl { font-size: var(--text-body); line-height: var(--lh-control); color: var(--text-tertiary);
            font-weight: var(--weight-medium); }
```

- [ ] **Step 6: How it works leaves the page for the header**

Replace everything from the line `            /* 5. HOW IT WORKS. Last, and shut. A director signing off a number` through the end of `renderForecast` (the `        }` on the line before `        /* ---------- Size list tab ----------`) with:

```js
            /* The by-category and by-segment tables came from the per-variant
               model, which no longer runs: it forecast October at a quarter of
               what October has ever been. They stay guarded rather than
               deleted, so an M5 run (FORECAST_M5=1) still draws them. */
            const lv = latest.levels || {};
            ['category', 'segment'].forEach(level => {
                const items = lv[level] || []; if (!items.length) return;
                const months = [...new Set(items.map(x => x.month))].sort().slice(0, 3);
                const byName = {}; items.forEach(x => { (byName[x.name] = byName[x.name] || {})[x.month] = x.p50; });
                const byLevel = level === 'category'
                    ? widget(el('div', 'widget-group'), 'by-category', 'full', 'By category')
                    : widget(el('div', 'widget-group'), 'by-segment', 'full', 'By segment');
                byLevel.append(el('div', 'section-title', 'By ' + level));
                box.append(byLevel);
                const lc = el('div', 'card');
                lc.append(fcTable([level === 'category' ? 'Category' : 'Segment'].concat(months.map(fcMonth)),
                    Object.keys(byName).sort((a, b) => (byName[b][months[0]] || 0) - (byName[a][months[0]] || 0))
                        .map(n => [n].concat(months.map(m => fcMoney(byName[n][m])))), [0, 1, 1, 1]));
                byLevel.append(lc);
            });
        }
```

Directly after `fcAlgorithmsCard` (its closing `        }` before the `/* ---------- the standing record ----------` comment) add:

```js
        /* A method page in a window: wide, for the tables some of them hold. */
        function fcPage(title, build) { const m = sheetModal(title); m.modal.classList.add('wide'); m.body.append(build()); return m; }
        /* How much to trust it: prose when the plain models are running, the
           M5 backtest table when that build is. */
        function fcTrust(latest) {
            const bt = latest.metrics || [];
            const bc = el('div');
            if (!bt.length) {
                bc.append(el('p', 'card-sub', 'Each source was fitted to earlier months and marked against '
                    + 'what actually happened, three times over. Typical error is how far out it usually was; '
                    + 'bias is whether it leaned high or low every month, which matters more, because a model '
                    + 'that leans high quietly turns a plan green. The leading model’s own error is the '
                    + 'band on the chart, so the forecast never claims to be more certain than it has earned.'));
                if (latest.basis) bc.append(el('p', 'card-sub', 'Figures are ' + latest.basis + '.'));
                return bc;
            }
            bc.append(el('p', 'card-sub', 'Five backtests of 28 days each, ending at the run date. WRMSSE is the M5 competition score: under 1 beats a naive forecast scaled to each series, and lower is better. Bias is how far the total ran hot or cold.'));
            const levels = ['total', 'category', 'segment', 'product', 'variant', 'bottom'];
            bc.append(fcTable(['Level', 'Blend', 'Seasonal baseline', 'Bias'],
                levels.map(l => { const b = bt.find(m => (m.model === 'blend+mint' || m.model === 'blend') && m.level === l); const s = bt.find(m => m.model === 'seasonal_level' && m.level === l);
                    return [l === 'bottom' ? 'variant x segment' : l, b ? Number(b.wrmsse).toFixed(2) : 'n/a', s ? Number(s.wrmsse).toFixed(2) : 'n/a', b ? fcPct(b.bias_pct) : 'n/a']; }),
                [0, 1, 1, 1]));
            const w = latest.weights && latest.weights.total;
            if (w) bc.append(el('p', 'card-sub', 'Who earned the top line: ' + Object.keys(w).filter(k => w[k] > 0.005).map(k => k + ' ' + Math.round(w[k] * 100) + '%').join(', ') + '.'));
            return bc;
        }
        /* The plan it is judged against: provenance, for somebody checking the work. */
        function fcPlanJudged(c, latest) {
            const wb = c.workbook || {};
            const names = latest.scenarios || [];
            const rc = el('div');
            rc.append(el('p', 'card-sub', wb.name ? (wb.name + ', uploaded ' + fmtDate(wb.uploaded_at) + (wb.by ? ' by ' + wb.by : '')
                    + '. Every scenario in it is a plan the forecast is measured against; the page opens on '
                    + (latest.scenario_feature || names[0] || 'the first') + '.')
                : 'No workbook on file: the run used what the service had.'));
            if (c.runs && c.runs.length) rc.append(el('p', 'card-sub', 'Recent runs: ' + c.runs.slice(-7).map(r => fmtDate(r.as_of)).join(', ') + '.'));
            return rc;
        }
        /* How it works (the mix, spec 8.1): the four method pages, each in a
           window, then the Forecast in the Guide. They were four drawers at the
           foot of the page. */
        function fcHowItWorks(c, latest, sc) {
            const nsrc = ((latest.sanity || {}).models || []).length;
            return howItWorks([
                { icon: I.compass, label: 'Which method is running, and why',
                  onClick: () => fcPage('Which method is running, and why', () => fcUntitled(fcOptimisedCard(latest))) },
                { icon: I.target, label: 'How each one works, and how right it has been', n: nsrc || null,
                  onClick: () => fcPage('How each one works, and how right it has been', () => fcUntitled(fcAlgorithmsCard(latest))) },
                { icon: I.shield, label: 'How much to trust it', onClick: () => fcPage('How much to trust it', () => fcTrust(latest)) },
                { icon: I.fileSheet, label: 'The plan it is judged against', onClick: () => fcPage('The plan it is judged against', () => fcPlanJudged(c, latest)) },
            ], { label: 'The Forecast in the Guide', at: ['money', 'Forecast'] });
        }
```

- [ ] **Step 7: Update the Forecast guards**

In `t_the_forecast_tab_exists_and_is_gated` replace:

```python
    order = [fn.index("fcOverviewCard(latest, sc)"), fn.index("fcChartCard("),
             fn.index("fcDriversCard(latest, sc)"), fn.index("'The numbers behind it'"),
             fn.index("'How this forecast works'")]
    ok(order == sorted(order),
       "overview, then the picture, then why, then the numbers, then how it works")
    for t in ("Month by month against ", "Every source, side by side",
              "How each one works, and how right it has been"):
        ok("fcDrawer('" + t in fn or 'fcDrawer(\'' + t in fn or ("fcDrawer('" + t) in fn,
           "'" + t + "' is a drawer, not dealt onto the screen")
```

with:

```python
    order = [fn.index("fcOverviewCard(latest, sc)"), fn.index("fcChartCard("),
             fn.index("fcDriversCard(latest, sc)"), fn.index("'The numbers behind it'")]
    ok(order == sorted(order),
       "overview, then the picture, then why, then the numbers")
    for t in ("Month by month against ", "Every source, side by side"):
        ok("fcDrawer('" + t in fn, "'" + t + "' is a drawer, not dealt onto the screen")
    ok("'How each one works, and how right it has been'" in fn_src("function fcHowItWorks(c, latest, sc) {"),
       "and how each method works is a page under How it works (the mix)")
```

In `t_the_forecast_tab_shows_the_five_plain_models_and_what_they_scored` replace:

```python
    ok("fcUntitled(fcOptimisedCard(latest))" in SCRIPT and "fcUntitled(fcAlgorithmsCard(latest))" in SCRIPT,
       "the tab draws both, under How this forecast works")
    ok(SCRIPT.index("'How this forecast works'") > SCRIPT.index("fcDriversCard(latest, sc)"),
       "and it sits below the money, never above it")
```

with:

```python
    ok("fcUntitled(fcOptimisedCard(latest))" in SCRIPT and "fcUntitled(fcAlgorithmsCard(latest))" in SCRIPT,
       "the tab draws both, as pages under How it works")
    ok("fcHowItWorks(c, latest, sc)" in SCRIPT.split("function renderForecast()")[1][:3000],
       "and they wait behind the header's button, never dealt above the money")
```

In `t_every_report_view_with_several_blocks_names_its_cards` (Forecast is the first adopted view to take the one header builder; Production Manager and the reports follow) replace:

```python
        ok("heroAct(" in src or (view == "mail" and "hero.append(heroAct(''))" in src),
           "the %s header has the action slot Customize goes in" % view)
```

with:

```python
        ok("heroAct(" in src or "pageHead({" in src or (view == "mail" and "hero.append(heroAct(''))" in src),
           "the %s header has the action slot Customize goes in (pageHead builds it since the mix)" % view)
```

In `t_a_page_is_called_what_the_sidebar_calls_it` (a page's heading is now `pageHead`'s `title`) replace:

```python
        ok("el('h2', null, '" + name + "')" in SCRIPT, "and so does its page heading: " + name)
```

with:

```python
        ok("el('h2', null, '" + name + "')" in SCRIPT or "title: '" + name + "'" in SCRIPT,
           "and so does its page heading: " + name)
```

In `t_the_scenario_label_sits_with_its_control` replace:

```python
    rule = CSS.split(".fc-seg-lbl {")[1].split("}")[0]
    ok("order: 1" in rule and "margin-left: auto" not in rule, "the label moves with the control")
```

with:

```python
    rule = CSS.split(".fc-seg-lbl {")[1].split("}")[0]
    ok("order" not in rule and "margin-left: auto" not in rule, "the label keeps its place before the control")
    fn = SCRIPT.split("function renderForecast()")[1].split("\n        async function showReconView")[0]
    ok("[el('span', 'fc-seg-lbl', 'Plan'),\n                segmented(" in fn,
       "and both ride in the tab row's end group, label first (the mix)")
```

- [ ] **Step 8: Run the tests**

Run: `ONLY=t_the_forecast_header_is python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `447 passed, 0 failed`.

- [ ] **Step 9: Look at it**

Forecast at 1440: "Forecast Beta", under it "October 2026 · Run as of 1 Oct"; at the right How it works and Upload workbook (and Customise, which the widget grid adds); the Finance tabs on their rule with "Plan" and Algorithm 1 to 3 at the row's right. How it works opens a menu of four rows (the second with "13") and "The Forecast in the Guide"; each row opens its page in a window.

- [ ] **Step 10: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Forecast: the mix header with its status line, the Plan chooser on the tab row, and How it works holding the method pages

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 27: Forecast's feature band

**Files:**
- Modify: `static/index.html` `fcOverviewCard` (14931-14996, replaced by `fcBand`), `renderForecast` (the overview widget), `:769` and `:4199-4200` (the old caveat's rules)
- Test: `tests/test_frontend.py` (`t_the_forecast_tab_exists_and_is_gated` 2210, `t_the_forecast_page_never_dresses_an_estimate_as_a_banked_figure` 4138, `t_the_month_pill_is_worked_out_from_the_figures_beside_it` 8051, `t_the_forecast_explains_itself_once_and_in_plain_lines` 8075, a new test)

**Interfaces:**
- Consumes: `featureBand`, `rangeBar`, `meter`, `bandDomain` (Task 15), `changeChip`, `deltaTone` (Task 14), `infoButton` (Task 12), `fcCurrentRow`, `fcBankedThisMonth`, `fcDaysSoFar`, `fcDaysInMonth`.
- Produces: `fcBand(latest, sc)` returns the band (Expected this month with "How sure this is", the range bar and the plan tick; Taken so far with "Day N of M" and its meter; Year lands at with its chip, "Plan £x" and its meter) or `null`; `fcYearTaken(latest)` returns the plan year's closed months plus this month's takings.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_forecast_leads_with_the_month_in_a_band():
    """Spec 8.1: the feature band answers the screen's main question. Expected
    this month at 44 with its chip and "against plan", its likely range drawn
    as one bar with the plan as a blue tick, "How sure this is" behind an info
    button word for word; beside it Taken so far (Day N of M, a meter) and Year
    lands at (its chip, the plan, a meter)."""
    ok("function fcBand(latest, sc) {" in SCRIPT and "function fcOverviewCard(" not in SCRIPT, "the band replaced the three tiles")
    fb = fn_src("function fcBand(latest, sc) {")
    for part in ("label: 'Expected this month'", "label: 'Taken so far'", "label: 'Year lands at'", "'against plan'",
                 "infoButton('How sure this is'", "8 times out of 10. It is an expectation, not a commitment.",
                 "never a promise.", "rangeBar({", "midLabel: 'Likely range'", "'Day ' + fcDaysSoFar(latest) + ' of ' + fcDaysInMonth(latest)",
                 "'Plan ' + fcMoney(yt)", "meter({"):
        ok(part in fb, "fcBand: " + part)
    fn = SCRIPT.split("function renderForecast()")[1].split("\n        async function showReconView")[0]
    ok("const band = fcBand(latest, sc);" in fn, "the page draws it first")
    ok(".fc-conf" not in CSS, "the old caveat line is gone")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_forecast_leads_with python3 tests/test_frontend.py`
Expected: `FAIL  t_forecast_leads_with_the_month_in_a_band: the band replaced the three tiles`

- [ ] **Step 3: The band replaces the three tiles**

Replace the whole `fcOverviewCard` function (from the comment `        /* ---------- 1. OVERVIEW: understood in about five seconds ----------` through its closing `        }` before `        /* Money already in the till this month.`) with:

```js
        /* ---------- 1. EXPECTED THIS MONTH: the feature band ----------
           The screen's main question (the mix, spec 8.1), answered first: what
           this month is expected to come to against the plan, how sure that is
           (behind the info button, word for word), the likely range as one bar
           with the plan as a tick; beside it what is taken so far and where
           the year lands. */
        function fcBand(latest, sc) {
            const cur = fcCurrentRow(latest);
            if (!cur || cur.p50 == null) return null;
            const banked = fcBankedThisMonth(latest);
            const p50 = cur.p50, p10 = cur.p10, p90 = cur.p90;
            const target = (cur.targets || {})[sc];
            /* Worked out from the two figures printed beside it: the run's
               gap_pct arrives rounded to two places. */
            const gap = (target && p50 != null) ? (p50 - target) / target : null;
            const year = latest.year || {}; const yt = (year.targets || {})[sc];
            const yg = (yt && year.p50 != null) ? (year.p50 - yt) / yt : null;
            /* Within 10% of plan is on track: the chip is the quiet fill. */
            const fcTrend = (g) => g == null ? null : Math.abs(g) <= 0.10 ? 'flat' : (g > 0 ? 'up' : 'down');
            const chip = (g) => g == null ? null : changeChip(fcTrend(g), Math.abs(g * 100).toFixed(1) + '%', deltaTone('expected', fcTrend(g)));
            let sure = null;
            if (p10 != null && p90 != null) {
                const half = Math.round((p90 - p10) / 2);
                sure = infoButton('How sure this is', { title: 'How sure this is', guide: ['money', 'Forecast'], body: [
                    'How certain is that? ' + fcMonth(cur.month) + ' should land within about ' + fcMoney(half)
                        + ' either side of ' + fcMoney(p50) + ', 8 times out of 10. It is an expectation, not a commitment.',
                    'Figures are cash in; what is still to come is a range, never a promise.'] });
            }
            const d = bandDomain([p10, p90, p50, target]);
            const sides = [{ icon: I.wallet, label: 'Taken so far', value: fcMoney(banked),
                note: 'Day ' + fcDaysSoFar(latest) + ' of ' + fcDaysInMonth(latest),
                meter: meter({ taken: p50 ? banked / p50 * 100 : 0, plan: (p50 && target != null) ? target / p50 * 100 : null }) }];
            if (year.p50 != null) sides.push({ icon: I.flag, label: 'Year lands at', value: fcMoney(year.p50), chip: chip(yg),
                note: yt != null ? 'Plan ' + fcMoney(yt) : null,
                meter: meter({ taken: year.p50 ? fcYearTaken(latest) / year.p50 * 100 : 0,
                               plan: (year.p50 && yt != null) ? yt / year.p50 * 100 : null }) });
            return featureBand({ main: { icon: I.trendUp, label: 'Expected this month', info: sure, value: fcMoney(p50),
                chip: chip(gap), note: target != null ? 'against plan' : null,
                range: (p10 != null && p90 != null) ? rangeBar({ lo: p10, hi: p90, exp: p50, plan: target, d,
                    planLabel: target != null ? 'Plan ' + fcMoney(target) : null, loLabel: fcMoney(p10), hiLabel: fcMoney(p90),
                    midLabel: 'Likely range' }) : null }, sides });
        }
        /* What the plan year has taken so far: its closed months as the run
           counts them, and this month's takings. */
        function fcYearTaken(latest) {
            return (Number((latest.sanity || {}).year_banked) || 0) + fcBankedThisMonth(latest);
        }
```

In `renderForecast` replace:

```js
            const ov = fcOverviewCard(latest, sc);
            ov.classList.add('widget-bare');
            box.append(widget(ov, 'standing', 'full', 'Where things stand'));
```

with:

```js
            const band = fcBand(latest, sc);
            if (band) box.append(widget(band, 'standing', 'full', 'Expected this month'));
```

and the three-line comment above it, from `            /* 1. OVERVIEW. The scenario is a FILTER on everything under it, so` through `               middle of the page next to a table it also governs. */`, with the one line `            /* 1. EXPECTED THIS MONTH: the feature band. */` (the scenario chooser it describes moved to the tab row in Task 26).

- [ ] **Step 4: The old caveat's rules go**

Delete `        .metrics:has(+ .fc-conf) { margin-bottom: 0; }` and the comment above it (`        /* The caveat that qualifies a row of figures sits at its own 12 under\n           them, not 24 away and as near the next section as its own. */`), and delete:

```css
        .fc-conf { margin: var(--sp-3) 0 0; font-size: var(--text-body); color: var(--text-secondary); }
        .fc-conf b { font-weight: var(--weight-medium); color: var(--text-primary); }
```

(the first line reads `--text-body` after Task 25).

- [ ] **Step 5: Update the Forecast guards**

In `t_the_forecast_tab_exists_and_is_gated` replace:

```python
    ov = SCRIPT.split("function fcOverviewCard(", 1)[1].split("\n        function ", 1)[0]
    for q in ("'Where I am now'", "'Where I am expected to be'", "'Where the year lands'"):
        ok(q in ov, "the overview asks " + q)
    # Each answer is its OWN block. The joined multi-column frame was retired
    # on purpose and must not come back, here or anywhere.
    ok("metricsStrip(mets)" in ov and "fc-now" not in SCRIPT,
       "each answer is a house KPI block, not three columns welded into one card")
    # Good or bad is the change pill ON the number it judges, which is where
    # the reference puts it, not a fourth abstract box.
    ok("delta:" in ov and "trend:" in ov,
       "the verdict rides on the figure it qualifies")
    ok("8 times out of 10" in ov and "not a commitment" in ov,
       "and says how wide the range is, in money, rather than printing P10 and P90")
    order = [fn.index("fcOverviewCard(latest, sc)"), fn.index("fcChartCard("),
```

with:

```python
    # Since the mix (2026-10-06) the three questions are one feature band, its
    # labels two to four words (spec 4.2 and 8.1).
    ov = fn_src("function fcBand(latest, sc) {")
    for q in ("'Taken so far'", "'Expected this month'", "'Year lands at'"):
        ok(q in ov, "the band answers " + q)
    ok("featureBand({" in ov and "fc-now" not in SCRIPT, "in one band, the screen's one focal point")
    # Good or bad is the change chip ON the number it judges.
    ok("chip: chip(gap)" in ov and "chip: chip(yg)" in ov, "the verdict rides on the figure it qualifies")
    ok("8 times out of 10" in ov and "not a commitment" in ov,
       "and says how wide the range is, in money, rather than printing P10 and P90")
    order = [fn.index("fcBand(latest, sc)"), fn.index("fcChartCard("),
```

In `t_the_forecast_page_never_dresses_an_estimate_as_a_banked_figure` replace:

```python
    ov = SCRIPT.split("function fcOverviewCard(", 1)[1].split("\n        function ", 1)[0]
    ok("taken so far in" in ov, "what is banked is labelled as taken")
```

with:

```python
    ov = fn_src("function fcBand(latest, sc) {")
    ok("'Taken so far'" in ov, "what is banked is labelled as taken")
```

In `t_the_month_pill_is_worked_out_from_the_figures_beside_it` replace `    ov = SCRIPT.split("function fcOverviewCard(", 1)[1].split("\n        function ", 1)[0]` with `    ov = fn_src("function fcBand(latest, sc) {")` and `"the overview works its percentage out from the money it prints")` with `"the band works its percentage out from the money it prints")`.

In `t_the_forecast_explains_itself_once_and_in_plain_lines` replace:

```python
    ov = SCRIPT.split("function fcOverviewCard(", 1)[1].split("\n        function ", 1)[0]
    tail = ov.split("const half = ", 1)[1]
    ok("el('div', 'card')" not in tail and "box.append(conf)" in tail, "the caveat is a line, not a card")
```

with:

```python
    ov = fn_src("function fcBand(latest, sc) {")
    tail = ov.split("const half = ", 1)[1]
    ok("el('div', 'card')" not in tail and "infoButton('How sure this is'" in ov,
       "the caveat waits behind an info button on the figure it qualifies (the mix), not in a card")
```

- [ ] **Step 6: Run the tests**

Run: `ONLY=t_forecast_leads_with python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `448 passed, 0 failed`.

- [ ] **Step 7: Match it to the mockup**

At 1440 with the rig's forecast: the band reads Expected this month £53,691, a green chip "42.9%", "against plan"; "Plan £37,566" above a blue tick at 18.9% of the bar; the bar from £41,327 (28.3%) to £66,054 (90.1%) with the ink dot at 59.2%; Taken so far £5,116, "Day 1 of 31"; Year lands at £372,285, chip 29.9%, "Plan £286,687". Read the positions in the console: `[...document.querySelectorAll('#view-forecast .fb-range, #view-forecast .fb-meter')].map(e => e.getAttribute('style'))`. The info button opens the two sentences.

- [ ] **Step 8: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Forecast: the month leads in a feature band, its likely range one bar with the plan as a tick, how sure behind an info button

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 28: Cash in: the info button, the legend row, Compare methods and the ranges

**Files:**
- Modify: `static/index.html` the section heads (`:1222-1223`), `:1601` (`.fc-cmp`), `:4180` (`.chart-band`), the compare helpers and `FC_RANGES` (14787-14826), `fcChartCard` (15098-15293)
- Test: `tests/test_frontend.py` (`t_a_forecast_is_drawn_as_a_range_not_as_three_competing_lines` 4099, a new test)

**Interfaces:**
- Consumes: `infoButton` (Task 12), `switchBtn` (Task 21), `segmented` with `icon` items (Task 10), `trendChart` with `headless`, `legend`, `label` and `key: 'dot'` (Task 19), `tokenValue(name)` (5278), the measure colours (Task 3).
- Produces: `.sec-tools`, a section head's tool group at its right (every later screen puts a section's controls in one); `fcCompareOn()` and `setFcCompareOn(v)`; `FC_RANGES` labels Today, Week, Month, 3 months, 12 months, Months ahead, Custom range.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_cash_in_is_the_mix_chart_section():
    """Spec 8.1 item 4: Cash in with About this chart beside it, the legend on
    its own row, Compare methods and the range chooser (Today, Week, Month, 3
    months, 12 months, Months ahead, and Custom as a calendar icon). The head's
    old source line moved into the info button word for word."""
    ranges = SCRIPT.split("const FC_RANGES = [")[1].split("];")[0]
    for k, label in (("today", "Today"), ("week", "Week"), ("month", "Month"), ("q", "3 months"),
                     ("year", "12 months"), ("ahead", "Months ahead"), ("custom", "Custom range")):
        ok("['%s', '%s']" % (k, label) in ranges, "the range %s is called %s" % (k, label))
    chart = fn_src("function fcChartCard(")
    for part in ("infoButton('About this chart'", "'Source: Shopify orders and the nightly forecast \\u00b7 ' + period + '.'",
                 "switchBtn('Compare methods', cmpOn, setFcCompareOn)", "segmented(FC_RANGES.map(", "icon: I.cal",
                 "headless: true", "legend: true", "key: 'dot'", "name: 'Likely range'", "tokenValue('--c-taken')",
                 "tokenValue('--c-exp-line')", "tokenValue('--c-area')", "const cmp = cmpOn ? fcCompare() : [];",
                 "'Pick a start and an end date.'", "'Nothing to draw for this range yet.'"):
        ok(part in chart, "Cash in: " + part)
    ok("Compare sources on the chart" not in SCRIPT and "the leading source" not in chart,
       "the compare card's title is the switch's word, and a source is a method")
    ok("const LS_FCCMPON = 'sc_fc_cmp_on_v1';" in SCRIPT and "function setFcCompareOn(v) {" in SCRIPT,
       "the switch is remembered per person")
    tools = CSS.split("\n        .section-title > .sec-tools {")[1].split("}")[0]
    ok("order: 1" in tools and "margin-left: auto" in tools, "a section's tools sit at its right, past the spacer")
    ok(".chart-band { stroke: none; fill: var(--c-area); }" in CSS, "the likely range is the area colour, at full strength")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_cash_in_is python3 tests/test_frontend.py`
Expected: `FAIL  t_cash_in_is_the_mix_chart_section: the range week is called Week`

- [ ] **Step 3: The ranges and the switch's memory**

Replace:

```js
        const FC_RANGES = [['today', 'Today'], ['week', 'This week'], ['month', 'This month'],
                           ['q', 'Last 3 months'], ['year', 'Last 12 months'],
                           ['ahead', 'The months ahead'], ['custom', 'Custom range']];
```

with:

```js
        /* The words Cameron approved for the ranges (the mix, 2026-10-06). */
        const FC_RANGES = [['today', 'Today'], ['week', 'Week'], ['month', 'Month'],
                           ['q', '3 months'], ['year', '12 months'],
                           ['ahead', 'Months ahead'], ['custom', 'Custom range']];
```

After the line `        function clearFcCompare() { try { localStorage.removeItem(LS_FCCMP); } catch (e) {} renderForecast(); }` add:

```js
        /* Compare methods (the mix): a switch, off unless the reader has turned
           it on. The picks above are kept while it is off. */
        const LS_FCCMPON = 'sc_fc_cmp_on_v1';
        function fcCompareOn() { try { return localStorage.getItem(LS_FCCMPON) === '1'; } catch (e) { return false; } }
        function setFcCompareOn(v) {
            try { if (v) localStorage.setItem(LS_FCCMPON, '1'); else localStorage.removeItem(LS_FCCMPON); } catch (e) {}
            renderForecast();
        }
```

- [ ] **Step 4: Cash in**

Replace the whole `fcChartCard` function (from `        function fcChartCard(latest, ledger, sanity) {` to the `        }` before `        /* ---------- which one is in use, and why ----------`) with:

```js
        function fcChartCard(latest, ledger, sanity) {
            const range = fcRange();
            const cmpOn = fcCompareOn();
            const asOf = new Date((latest.as_of || fcISO(new Date())) + 'T00:00:00');
            const days = (latest.daily || {});
            const dayRows = (days.history || []).map(r => ({ date: r.date, actual: r.actual, p50: null, p10: null, p90: null }))
                .concat((days.forecast || []).map(r => ({ date: r.date, actual: null, p50: r.p50, p10: r.p10, p90: r.p90 })));
            const months = latest.months || [];
            const shift = (n) => { const d = new Date(asOf); d.setDate(d.getDate() - n); return fcISO(d); };
            /* "This month" and "The months ahead" start at the month the reader
               is in, not the run's as_of month: the 03:00 run on the 1st is as
               of the last day of the month before, and the default view drew
               September, headed This month, on 1 October. */
            const curMonth = fcCurrentMonth(latest);
            let grain = 'day', from = '', to = '', title = '', period = '';
            const [cf, ct] = fcCustom();
            if (range === 'today') { from = shift(6); to = fcISO(asOf); title = 'Today, and the six days before it'; period = 'the day, against the average of the six before it'; }
            else if (range === 'week') { from = shift(6); to = fcISO(asOf); title = 'The last seven days'; period = 'the last seven days'; }
            else if (range === 'month') { from = curMonth + '-01'; to = ''; title = 'This month, day by day'; period = 'taken so far, then the rest of the month forecast'; }
            else if (range === 'q') { from = shift(91); to = fcISO(asOf); title = 'The last three months'; period = 'day by day'; }
            else if (range === 'year') { grain = 'month'; from = ''; to = ''; title = 'The last twelve months'; period = 'month by month, with what was predicted at the time'; }
            else if (range === 'ahead') { grain = 'month'; from = curMonth; to = ''; title = 'The months ahead'; period = 'the leading method, with its own measured error as the band'; }
            else { from = cf; to = ct; title = 'The range you chose'; period = 'day by day'; }

            let rows;
            if (grain === 'month' || (range === 'custom' && from && to && (new Date(to) - new Date(from)) / 864e5 > 120)) {
                grain = 'month';
                const f = from ? from.slice(0, 7) : '', t = to ? to.slice(0, 7) : '';
                rows = months.filter(m => (!f || m.month >= f) && (!t || m.month <= t));
                if (range === 'year') rows = rows.filter(m => m.actual != null).slice(-12);
                if (range === 'ahead') rows = rows.slice(0, 12);
            } else {
                rows = dayRows.filter(r => (!from || r.date >= from) && (!to || r.date <= to));
                if (range === 'month') rows = rows.filter(r => r.date.slice(0, 7) === curMonth);
            }
            /* Cash in (the mix, spec 8.1): About this chart beside the title,
               Compare methods and the range at its right, the legend on the
               chart's own row. What the head said (its title, the source and
               the period) is the info button's, word for word. */
            const card = el('div', 'fc-cash');
            const head = el('div', 'section-title', 'Cash in');
            head.append(infoButton('About this chart', { title: title, guide: ['money', 'Forecast'],
                body: ['Source: Shopify orders and the nightly forecast \u00b7 ' + period + '.', 'Likely range, 8 times in 10.'] }));
            const tools = el('div', 'sec-tools');
            tools.append(switchBtn('Compare methods', cmpOn, setFcCompareOn));
            tools.append(segmented(FC_RANGES.map(([k, l]) => k === 'custom' ? { key: k, label: l, icon: I.cal } : { key: k, label: l }),
                range, setFcRange, { label: 'Range' }));
            /* A phone has no room for seven segments: the same choice as one
               compact list, which the phone rules show in their place. */
            tools.append(choiceSelect(FC_RANGES, range, setFcRange, { label: 'Range' }));
            head.append(tools);
            card.append(head);
            /* The dates belong under the tab that asked for them, not in a
               third card below the chart and the source list. And until both
               are set there is no range to draw: with neither, every day of
               history was drawn as a picket fence headed "The range you chose". */
            if (range === 'custom') {
                const row = el('div', 'act-row fc-dates');
                const mk = (val, label, on) => {
                    const w = el('label', 'pfield'); w.append(el('span', null, label));
                    const i = document.createElement('input'); i.type = 'date'; i.className = 'field-sm fc-date'; i.value = val;
                    i.onchange = on; w.append(i); return w;
                };
                let a = cf, b = ct;
                row.append(mk(cf, 'From', (e) => { a = e.target.value; setFcCustom(a, b); }));
                row.append(mk(ct, 'To', (e) => { b = e.target.value; setFcCustom(a, b); }));
                card.append(row);
                if (!cf || !ct) { card.append(el('div', 'empty', 'Pick a start and an end date.')); return card; }
            }
            if (!rows.length) { card.append(el('div', 'empty', 'Nothing to draw for this range yet.')); return card; }
            const labels = rows.map(r => grain === 'month' ? fcMonth(r.month) : fcDay(r.date));
            /* ACTUAL -> FORECAST -> UNCERTAINTY, in that visual order.
               The old picture drew four equal lines: taken, forecast, P90, P10.
               Four strokes of the same weight read as four competing answers,
               and nothing on the plot said which part had already happened.
               Now there is ONE line that changes character at today - solid
               where the money arrived, dashed where it is expected - and ONE
               shaded region for the range. The forecast series repeats the last
               actual value so the two halves join rather than floating apart,
               and the band pinches to nothing at that same point, because at
               today there is no uncertainty left: it widens as it goes out. */
            const actualVals = rows.map(r => r.actual);
            let handover = -1;
            actualVals.forEach((v, i) => { if (v != null) handover = i; });
            const joins = (i, v) => (i === handover ? rows[i].actual : v);
            /* The legend says in words what each treatment is, because a
               shaded band explains itself only to somebody who already reads
               forecast charts. One colour per measure (the mix): taken in the
               dark teal, keyed as a dot; expected as the teal line, dashed; the
               likely range as the teal area. */
            const series = [{ name: 'Taken', color: tokenValue('--c-taken'), key: 'dot', values: actualVals },
                            { name: 'Expected', color: tokenValue('--c-exp-line'), dash: true, lead: true,
                              values: rows.map((r, i) => joins(i, r.p50)) }];
            const band = rows.some(r => r.p10 != null && r.p90 != null)
                ? { name: 'Likely range', color: tokenValue('--c-area'),
                    lo: rows.map((r, i) => joins(i, r.p10)),
                    hi: rows.map((r, i) => joins(i, r.p90)) }
                : null;
            if (grain === 'month') {
                /* What the forecast in use said for each closed month, from
                   the first run after the month before had closed, so the
                   gap between what directors were told and what came in is
                   on one picture. It used to plot whichever source turned out
                   closest, chosen after the month closed, which made a 36%
                   miss look like a hit. A month closed before the record kept
                   the source in use draws no point rather than a guess. */
                const said = {};
                ((ledger || {}).results || []).forEach(r => {
                    if (r.in_use && r.in_use.value != null) said[r.month] = r.in_use.value;
                });
                if (Object.keys(said).length) {
                    series.push({ name: 'Was predicted', color: CH[3] || CH[2],
                                  values: rows.map(r => said[r.month] == null ? null : said[r.month]) });
                }
            }
            /* Every method the reader has asked to see, drawn against the
               leader and against what actually came in, while Compare methods
               is on. Monthly grain only: a method forecasts a MONTH, and
               spreading it over days here would be inventing a shape it never
               claimed. */
            const cmp = cmpOn ? fcCompare() : [];
            if (grain === 'month' && cmp.length) {
                const by = {};
                ((sanity || {}).models || []).forEach(m => { if (cmp.indexOf(m.name) >= 0) by[m.name] = m.months || {}; });
                cmp.forEach((n, i) => {
                    if (!by[n]) return;
                    series.push({ name: n.length > 26 ? n.slice(0, 25) + '\u2026' : n,
                                  color: CH[(i + 4) % CH.length],
                                  values: rows.map(r => (by[n][r.month] == null ? null : by[n][r.month])) });
                });
            }
            const chart = trendChart({ headless: true, legend: true, label: 'Cash in, ' + title, title: title,
                source: 'Shopify orders and the nightly forecast', period: period, yUnit: 'GBP', labels: labels, series: series,
                band: band, splitAt: handover > 0 && handover < rows.length - 1 ? handover : null,
                format: (n) => money(n, 'GBP', 0), tickFormat: fmtCompact,
                height: window.matchMedia('(max-width: 640px)').matches ? 200 : 268, annotate: false });
            card.append(chart);
            /* On a phone the switch sits under the chart, where a thumb finds
               it; the head's copy is hidden there. */
            const phoneSw = switchBtn('Compare methods', cmpOn, setFcCompareOn);
            phoneSw.classList.add('fc-cmp-phone');
            card.append(phoneSw);
            /* The methods to draw, while Compare methods is on: a chip per
               method, tap to add its line. Capped at six, because a chart with
               fourteen lines is a chart nobody reads. */
            const srcs = ((sanity || {}).models || []).filter(m => m.months);
            if (cmpOn && srcs.length) {
                const box = el('div', 'fc-cmp-box');
                if (grain !== 'month') {
                    /* A method forecasts a MONTH, so on a daily range the honest
                       thing is one line saying so and the way to a range where
                       it works, not the whole set disabled. */
                    box.append(el('p', 'fc-cmp-note', 'Each method forecasts a month, so they can be compared on a '
                        + 'monthly range rather than day by day.'));
                    const go = el('button', 'btn', 'Show the last twelve months');
                    go.type = 'button'; go.onclick = () => setFcRange('year');
                    box.append(go);
                } else {
                    const chips = el('div', 'fc-cmp');
                    srcs.forEach(m => {
                        const picked = cmp.indexOf(m.name) >= 0;
                        const b = el('button', 'chip' + (picked ? ' on' : ''), m.name);
                        b.type = 'button';
                        b.disabled = !picked && cmp.length >= 6;
                        if (b.disabled) b.title = 'Six lines at most: take one off to add another';
                        b.setAttribute('aria-pressed', picked ? 'true' : 'false');
                        if (m.name === (sanity || {}).best) b.append(document.createTextNode(' '), fcChip('made', 'in use'));
                        b.onclick = () => toggleFcCompare(m.name);
                        chips.append(b);
                    });
                    box.append(chips);
                    if (cmp.length) {
                        const clr = el('button', 'btn ghost', 'Clear');
                        clr.type = 'button'; clr.onclick = clearFcCompare;
                        box.append(clr);
                    }
                }
                card.append(box);
            }
            return card;
        }
```

- [ ] **Step 5: The rules**

After the line `        .section-title > .choice-select { order: 1; letter-spacing: normal; font-weight: var(--weight-regular); }` add:

```css
        /* A section's tools (the mix, spec 6): one group at the head's right,
           past the spacer, wrapping as a group. On a phone the spacer goes and
           the margin keeps them right. */
        .section-title > .sec-tools { order: 1; margin-left: auto; display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end;
            gap: var(--gap-cluster); font-size: var(--text-body); font-weight: var(--weight-regular); letter-spacing: normal; }
```

Replace `        .fc-cmp { display: flex; flex-wrap: wrap; gap: var(--sp-2); margin-top: var(--sp-2-5); }` with:

```css
        .fc-cmp { display: flex; flex-wrap: wrap; gap: var(--sp-2); flex: 1 1 100%; }
        /* Cash in: the methods to compare sit 16 under the chart; on a phone
           the range is one list and the switch moves under the chart. */
        .fc-cmp-box { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-3); margin-top: var(--sp-4); }
        .fc-cmp-note { margin: 0; flex: 1 1 100%; color: var(--text-tertiary); max-width: var(--measure); }
        .fc-cash .sec-tools > .choice-select, .fc-cash > .fc-cmp-phone { display: none; }
        @media (max-width: 640px) {
            .fc-cash .sec-tools > :is(.toggle, .segmented) { display: none; }
            .fc-cash .sec-tools > .choice-select { display: inline-block; }
            .fc-cash > .fc-cmp-phone { display: inline-flex; margin-top: var(--sp-3); }
        }
```

Task 19 already gave the band the area colour. Replace its line `        .chart-band { stroke: none; fill: var(--c-area); }` with the same line under a comment:

```css
        /* The likely range is the area colour (the mix), already a 15% tint. */
        .chart-band { stroke: none; fill: var(--c-area); }
```

- [ ] **Step 6: Update the chart guard**

In `t_a_forecast_is_drawn_as_a_range_not_as_three_competing_lines` replace:

```python
    ok("name: 'Taken'" in fc and "name: 'Expected'" in fc and "'Likely range, 8 times in 10'" in fc,
       "and the legend says in words what its three treatments mean")
```

with:

```python
    ok("name: 'Taken'" in fc and "name: 'Expected'" in fc and "name: 'Likely range'" in fc
       and "'Likely range, 8 times in 10.'" in fc,
       "the legend says in words what its three treatments mean, and About this chart how often the range holds")
```

- [ ] **Step 7: Run the tests**

Run: `ONLY=t_cash_in_is python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `449 passed, 0 failed`.

- [ ] **Step 8: Match it to the mockup**

At 1440: "Cash in" and its info button; at the right the Compare methods switch, then the seven ranges with Month chosen and Custom as a calendar icon; the legend row (a dark dot for Taken, a dashed teal line for Expected, a teal swatch for Likely range); the plot 268 tall. Arrow keys on the plot move the day; on a 390 phone the range is one list beside the title, the legend reads the day out, and Compare methods sits under the chart. Turn Compare methods on with Month chosen: the line and "Show the last twelve months"; press it: the chips, and a chip draws its line.

- [ ] **Step 9: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Forecast: Cash in with About this chart, its legend row, a Compare methods switch and the approved range words

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 29: Worth looking at, beside Why £X

**Files:**
- Modify: `static/index.html` `:root` (after `--tip-w`; `--dot-lg` at 201), `:862-864` (`.fc-alert`), the `.card > .fc-alert` rules (1537-1542, if Task 11 left them), `:4202-4230` (the "what is driving the number" block), `fcAlertRow` (14875-14888, deleted), `fcDriversCard` (15026-15087), new functions after `fcAlertWeight`, `renderForecast` (the alerts block, the WHY block and the Worth looking at drawer)
- Test: `tests/test_frontend.py` (`t_beating_the_plan_is_not_something_worth_looking_at` 1229, `t_the_forecast_page_never_dresses_an_estimate_as_a_banked_figure` 4138, `t_the_forecast_explains_itself_once_and_in_plain_lines` 8075, `t_an_icon_size_comes_from_the_scale_and_not_from_the_rule` 5989, a new test)

**Interfaces:**
- Consumes: `bandDomain`, `bandPct` (Task 15), `changeChip`, `deltaTone` (Task 14), `infoButton` (Task 12), `.cnt` (Task 10), `.sec-tools` (Task 28), `fcPage`, `fcMonthName` (Task 26), `fcAlertText(a)`, `fcAlertWeight(a)`, `FC_VERDICT_WORDS`.
- Produces: `fcOutlook(a)` returns Safely ahead, Likely ahead, Likely behind or the verdict's words; `fcWorthTable(latest, list)` returns the table of those months (`div.fc-wl-wrap` > `div.fc-wl[role=table]`); `fcWorthCard(latest, sc, al)` returns the section; `fcDriversCard(latest, sc)` returns the Why section; `.rg` is a mini range bar (Size list and Liability may reuse it); `--fc-wl-cols`, `--fc-wl-cols-m`, `--rg-h`, `--rg-band`. `--dot-lg` is retired (the old Why key was its one reader).

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_worth_looking_at_sits_beside_why():
    """Spec 8.1 item 5: Worth looking at (a table with mini range bars and the
    approved outlooks: Safely ahead, Likely ahead, Likely behind) beside Why
    £53,691 (a split bar and three rows, the method in a caption under them and
    how it works behind an info button). A cash warning stays a sentence."""
    fn = SCRIPT.split("function renderForecast()")[1].split("\n        async function showReconView")[0]
    ok("const pair = el('div', 'fc-pair');" in fn and "fcWorthCard(latest, sc, al)" in fn, "the two sit in one pair")
    ok("function fcAlertRow(" not in SCRIPT and "fc-alert" not in SCRIPT + CSS, "the old alert rows are gone")
    ol = fn_src("function fcOutlook(a) {")
    for w in ("'Safely ahead'", "'Likely ahead'", "'Likely behind'", "FC_VERDICT_WORDS[a.verdict]"):
        ok(w in ol, "the outlook says " + w)
    ok("'warn'" not in ol, "and nothing that beat its plan arrives in warning amber")
    wt = fn_src("function fcWorthTable(latest, list) {")
    for part in ("t.setAttribute('role', 'table')", "'Against plan'", "'Likely range'", "'Outlook'", "el('span', 'rg')",
                 "changeChip(tr,", "bandDomain([].concat(", "'rg-fill'", "'rg-plan'", "'rg-exp'"):
        ok(part in wt, "the table: " + part)
    wc = fn_src("function fcWorthCard(latest, sc, al) {")
    ok("el('span', 'cnt'" in wc and "'Show all'" in wc and "fcPage('Worth looking at'" in wc, "a count, and Show all opens every month")
    ok("el('div', 'msg error'" in wc and "fcAlertText(a)" in wc, "a cash warning stays a sentence")
    ok(".slice(0, 3)" in wc, "three months on the page")
    dr = fn_src("function fcDriversCard(latest, sc) {")
    for part in ("'Why ' + fcMoney(cur.p50)", "infoButton('How this is worked out'", "'It misleads when'",
                 "'Taken so far'", "'Still expected'", "'Expected this month'", "' method.'"):
        ok(part in dr, "Why: " + part)
    ok("@container fcpair (max-width: 1000px)" in CSS and "@container fcwl (max-width: 560px)" in CSS,
       "side by side while there is room, and the phone's three columns by the table's own width")
    eq(_token_raw("fc-wl-cols"), "76px 72px 72px 84px minmax(96px, 1fr) 96px", "--fc-wl-cols")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_worth_looking_at_sits python3 tests/test_frontend.py`
Expected: `FAIL  t_worth_looking_at_sits_beside_why: the two sit in one pair`

- [ ] **Step 3: Tokens**

In `:root` after the line `            --tip-w: 232px;         /* the chart's tooltip */` add:

```
            /* Worth looking at's columns (month, expected, plan, chip, range,
               outlook), the phone's three (month, range, expected), and a mini
               range bar's height and band. */
            --fc-wl-cols: 76px 72px 72px 84px minmax(96px, 1fr) 96px;
            --fc-wl-cols-m: 84px minmax(0, 1fr) 92px;
            --rg-h: 12px; --rg-band: 6px;
```

- [ ] **Step 4: The table, the outlook and the section**

Delete the whole `fcAlertRow` function and the comment above it (`        /* One alert, said as a fact and then a reason. */`). After the closing `        }` of `fcAlertWeight` add:

```js
        /* ---------- WORTH LOOKING AT ----------
           The months that matter (the mix, spec 8.1 item 5): a table of the
           month, what is expected, the plan, the change chip, the likely range
           drawn small with the plan as a tick, and the outlook in the words
           Cameron approved. Cash alerts stay sentences above it: they are
           warnings, and a warning is never cut to a code. */
        function fcOutlook(a) {
            if (a.risk === 'secure') return 'Safely ahead';
            if (a.risk === 'watch') return (a.projected || 0) >= (a.target || 0) ? 'Likely ahead' : 'Likely behind';
            return FC_VERDICT_WORDS[a.verdict] || fcSentence(a.verdict || '');
        }
        function fcWorthTable(latest, list) {
            const wrap = el('div', 'fc-wl-wrap');
            const t = el('div', 'fc-wl');
            t.setAttribute('role', 'table'); t.setAttribute('aria-label', 'Worth looking at');
            const rowOf = (cells, head) => {
                const r = el('div', head ? 'h' : 'r'); r.setAttribute('role', 'row');
                cells.forEach(([c, cls]) => {
                    const s = el('span', cls); s.setAttribute('role', head ? 'columnheader' : 'cell');
                    if (c instanceof Node) s.append(c); else s.textContent = c == null ? '' : String(c);
                    r.append(s);
                });
                return r;
            };
            t.append(rowOf([['Month', 'c-mo'], ['Expected', 'c-v ra'], ['Plan', 'c-plan ra'], ['Against plan', 'c-chip ra'],
                            ['Likely range', 'c-rg'], ['Outlook', 'c-ol']], true));
            const monthOf = (a) => (latest.monthly || []).find(x => x.month === a.month) || {};
            /* One scale for every row, so the bars can be read against each other. */
            const d = bandDomain([].concat(...list.map(a => { const m = monthOf(a); return [m.p10, m.p90, a.projected, a.target]; })));
            list.forEach(a => {
                const m = monthOf(a);
                const gap = (a.target && a.projected != null) ? (a.projected - a.target) / a.target : null;
                const tr = gap == null ? null : Math.abs(gap) <= 0.10 ? 'flat' : (gap > 0 ? 'up' : 'down');
                const chip = gap == null ? '' : changeChip(tr, Math.abs(gap * 100).toFixed(1) + '%', deltaTone('expected', tr));
                const rg = el('span', 'rg'); rg.setAttribute('role', 'img');
                rg.setAttribute('aria-label', 'Likely ' + fcMoney(m.p10) + ' to ' + fcMoney(m.p90) + ', plan ' + fcMoney(a.target));
                if (m.p10 != null && m.p90 != null) {
                    rg.style.setProperty('--at-lo', bandPct(m.p10, d)); rg.style.setProperty('--at-hi', bandPct(m.p90, d));
                    rg.append(el('i', 'rg-fill'));
                }
                if (a.target != null) { rg.style.setProperty('--at-plan', bandPct(a.target, d)); rg.append(el('i', 'rg-plan')); }
                if (a.projected != null) { rg.style.setProperty('--at-exp', bandPct(a.projected, d)); rg.append(el('i', 'rg-exp')); }
                t.append(rowOf([[fcMonth(a.month), 'c-mo'], [fcMoney(a.projected), 'c-v ra'], [fcMoney(a.target), 'c-plan ra'],
                                [chip, 'c-chip ra'], [rg, 'c-rg'], [fcOutlook(a), 'c-ol']]));
            });
            wrap.append(t);
            return wrap;
        }
        function fcWorthCard(latest, sc, al) {
            const box = el('section', 'fc-worth');
            const sales = al.filter(a => a.kind !== 'cash');
            const cash = al.filter(a => a.kind === 'cash');
            const head = el('div', 'section-title', 'Worth looking at');
            if (sales.length) { const n = el('span', 'cnt', String(sales.length)); n.append(el('span', 'sr-only', sales.length === 1 ? ' month' : ' months')); head.append(n); }
            if (sales.length > 3) {
                const tools = el('div', 'sec-tools');
                const all = el('button', 'link', 'Show all'); all.type = 'button'; all.append(ico(I.arrowRight));
                all.onclick = () => fcPage('Worth looking at', () => fcWorthTable(latest, sales.slice().sort((a, b) => a.month < b.month ? -1 : 1)));
                tools.append(all); head.append(tools);
            }
            box.append(head);
            cash.forEach(a => box.append(el('div', 'msg error', fcMonth(a.month) + ': ' + fcAlertText(a))));
            if (!sales.length) { if (!cash.length) box.append(el('div', 'empty', 'Nothing to flag under ' + sc + '.')); return box; }
            /* The three that matter most (fcAlertWeight), read in month order. */
            const top = sales.slice().sort((a, b) => fcAlertWeight(b) - fcAlertWeight(a)).slice(0, 3)
                .sort((a, b) => a.month < b.month ? -1 : 1);
            box.append(fcWorthTable(latest, top));
            return box;
        }
```

- [ ] **Step 5: Why**

Replace the whole `fcDriversCard` function and the comment above it (from `        /* ---------- 5. WHY: what is driving the number ----------` to the `        }` before `        function fcDaysSoFar(latest) {`) with:

```js
        /* ---------- WHY: what is driving the number ----------
           The honest decomposition (the mix, spec 8.1 item 5): money already
           taken and what is still expected, as one split bar and three rows,
           then which method expects it. How that method works is the info
           button's, in its own words. This model forecasts the shop's own
           takings from the shop's own history: it has no invoice ledger, so it
           never claims invoice-level drivers. */
        function fcDriversCard(latest, sc) {
            const cur = fcCurrentRow(latest);
            if (!cur || cur.p50 == null) return null;
            const banked = fcBankedThisMonth(latest);
            const rest = Math.max(0, cur.p50 - banked);
            const sn = latest.sanity || {};
            const best = (sn.models || []).find(m => m.name === sn.best);
            const box = el('section', 'fc-why');
            const head = el('div', 'section-title', 'Why ' + fcMoney(cur.p50));
            if (best && best.about) {
                const cut = best.about.indexOf('It misleads when');
                head.append(infoButton('How this is worked out', { title: best.name, guide: ['money', 'Forecast'],
                    body: cut > 0 ? [best.about.slice(0, cut).trim(), best.about.slice(cut)] : [best.about] }));
            }
            box.append(head);
            /* ONE split bar: the two parts of one figure, on one scale. */
            const whole = (banked + rest) || 1;
            const bar = el('div', 'fc-split-bar'); bar.setAttribute('aria-hidden', 'true');
            bar.style.setProperty('--w', (banked / whole * 100).toFixed(1) + '%');
            bar.append(el('i', 'taken'), el('i', 'still'));
            box.append(bar);
            /* Read as a statement: each part's key and name, its amount at the
               right of the same measure, and the total under a stronger rule. */
            const list = el('div', 'fc-drive');
            const row = (amt, label, cls) => {
                const r = el('div', 'fc-drive-row' + (cls ? '' : ' fc-drive-tot'));
                if (cls) r.append(el('span', 'fc-drive-key ' + cls));
                r.append(el('span', 'fc-drive-lbl', label));
                r.append(el('span', 'fc-drive-amt', fcMoney(amt)));
                return r;
            };
            list.append(row(banked, 'Taken so far', 'taken'), row(rest, 'Still expected', 'still'), row(cur.p50, 'Expected this month', ''));
            box.append(list);
            if (best) {
                const p = el('p', 'fc-foot');
                p.append(document.createTextNode('Rest of ' + fcMonthName(cur.month) + ' forecast by the '),
                         el('b', null, best.name), document.createTextNode(' method.'));
                box.append(p);
            }
            return box;
        }
```

- [ ] **Step 6: The page draws the pair**

In `renderForecast` delete the alerts block, from the line `            /* Exceptions, and only the ones that are genuinely exceptional. An` through the `            }` that closes `if (al.length) {` (the line after `                alerts.append(ac0);`). Then replace:

```js
            /* 3. WHY. */
            const drv = fcDriversCard(latest, sc);
            if (drv) { drv.classList.add('widget-bare'); box.append(widget(drv, 'drivers', 'full', 'Why the forecast is what it is')); }
```

with:

```js
            /* 3. WORTH LOOKING AT, AND WHY (the mix): the months that matter
               beside what drives this one, 7 to 5, one block in Customize. */
            const pair = el('div', 'fc-pair');
            const cols = el('div', 'fc-cols');
            cols.append(fcWorthCard(latest, sc, al));
            const drv = fcDriversCard(latest, sc);
            if (drv) cols.append(drv);
            pair.append(cols);
            box.append(widget(pair, 'worth', 'full', 'Worth looking at, and why'));
```

and delete the drawer that repeated the alerts (Show all opens every month now):

```js
            detail.append(fcDrawer('Worth looking at' + (al.length ? ' (' + al.length + ')' : ''), function () {
                const ac = el('div');
                if (!al.length) ac.append(el('div', 'empty', 'Nothing to flag under ' + sc + '.'));
                al.forEach(a => ac.append(fcAlertRow(a)));
                return ac;
            }));
```

- [ ] **Step 7: The rules**

Replace:

```css
        .fc-alert { display: flex; align-items: baseline; gap: var(--sp-2); font-size: var(--text-body);
            padding-block: var(--sp-2); padding-inline: 0; }
        .fc-alert + .fc-alert { border-top: var(--bw-hairline) solid var(--border-default); }
```

(as Task 25's type sweep left it: its size was `--text-sm` at 9a8c442) with:

```css
        /* WORTH LOOKING AT, AND WHY (the mix, spec 8.1 item 5): side by side at
           7 to 5 while the pair is wide enough for the table, one under the
           other when it is not. Laid out by the pair's own width. */
        .fc-pair { container: fcpair / inline-size; }
        .fc-cols { display: grid; grid-template-columns: minmax(0, 7fr) minmax(0, 5fr); column-gap: var(--gap-cols);
            row-gap: var(--page-rhythm); align-items: start; }
        .fc-cols > section > .section-title:first-child { margin-top: 0; }
        @container fcpair (max-width: 1000px) { .fc-cols { grid-template-columns: minmax(0, 1fr); } }
        .fc-worth > .msg { margin-bottom: var(--sp-3); }
        .fc-wl-wrap { container: fcwl / inline-size; }
        .fc-wl > [role="row"] { display: grid; grid-template-columns: var(--fc-wl-cols); grid-template-areas: "mo v plan chip rg ol";
            column-gap: var(--sp-4); align-items: center; }
        .fc-wl > .h { height: var(--control-h); box-shadow: var(--rule-b); font-size: var(--text-xs); line-height: var(--lh-caption);
            font-weight: var(--weight-medium); color: var(--text-tertiary); }
        .fc-wl > .r { height: var(--row-h); box-shadow: var(--rule-b-soft); }
        .fc-wl > .r:last-child { box-shadow: var(--rule-b); }
        .fc-wl > [role="row"] > span { display: flex; align-items: center; min-width: 0; white-space: nowrap; font-variant-numeric: tabular-nums; }
        .fc-wl .c-mo { grid-area: mo; } .fc-wl .c-v { grid-area: v; } .fc-wl .c-plan { grid-area: plan; }
        .fc-wl .c-chip { grid-area: chip; } .fc-wl .c-rg { grid-area: rg; } .fc-wl .c-ol { grid-area: ol; }
        .fc-wl .ra { justify-content: flex-end; }
        .fc-wl > .r > :is(.c-mo, .c-v) { font-weight: var(--weight-medium); }
        .fc-wl > .r > :is(.c-plan, .c-ol) { color: var(--text-tertiary); }
        /* The likely range drawn small: a hairline track, the range as a band,
           the plan as a blue tick, the expected figure as an ink dot. */
        .rg { position: relative; width: 100%; height: var(--rg-h); }
        .rg::after { content: ""; position: absolute; left: 0; right: 0; top: 50%; height: var(--bw-strong); margin-top: calc(var(--bw-strong) / -2);
            border-radius: var(--radius-full); background: var(--border-soft); }
        .rg > i { position: absolute; z-index: 1; }
        .rg > .rg-fill { top: calc((var(--rg-h) - var(--rg-band)) / 2); height: var(--rg-band); left: var(--at-lo); width: calc(var(--at-hi) - var(--at-lo));
            border-radius: var(--radius-full); background: var(--c-range); box-shadow: inset 0 0 0 var(--bw-hairline) var(--c-range-edge); }
        .rg > .rg-plan { top: 0; bottom: 0; left: var(--at-plan); width: var(--bw-strong); margin-left: calc(var(--bw-strong) / -2);
            border-radius: var(--radius-swatch); background: var(--c-plan); }
        .rg > .rg-exp { top: 50%; left: var(--at-exp); width: var(--dot-md); height: var(--dot-md); margin: calc(var(--dot-md) / -2) 0 0 calc(var(--dot-md) / -2);
            border-radius: var(--radius-circle); background: var(--c-exp); box-shadow: 0 0 0 var(--bw-strong) var(--surface-primary); }
        /* By the table's own width (a phone, or Show all's window on one):
           month over its outlook, the range, the figure over its chip, in 60 rows. */
        @container fcwl (max-width: 560px) {
            .fc-wl > [role="row"] { grid-template-columns: var(--fc-wl-cols-m); grid-template-areas: "mo rg v" "ol rg chip"; }
            .fc-wl > .h { grid-template-areas: "mo rg v"; }
            .fc-wl > .h > :is(.c-plan, .c-chip, .c-ol), .fc-wl > .r > .c-plan { display: none; }
            .fc-wl > .r { height: var(--row-h-2); row-gap: var(--sp-1); align-content: center; }
        }
```

A count rides in its title on a phone too: in the `@media (max-width: 640px)` block after `.section-title { flex-wrap: wrap; }` replace `            .section-title > span { flex: 1 1 100%; }` with `            .section-title > span:not(.cnt) { flex: 1 1 100%; }`.

Delete every rule left whose selector names `.fc-alert` and its comment: `.card > .fc-alert { padding-block: 0; }`, `.card > .fc-alert + .fc-alert { padding-top: var(--sp-4); }`, and `.card > .fc-alert` out of `.card > .know-body, .card > .fc-alert { padding-inline: 0; }` (keep the `.card > .know-body` rule if Task 11 left it). Then `grep -c "fc-alert" static/index.html` prints `0`.

Replace the block from the comment `        /* ---- what is driving the number ----` through the rule `        .fc-drive-tot .fc-drive-lbl, .fc-drive-tot .fc-drive-amt { color: var(--text-primary); font-weight: var(--weight-medium); }` with:

```css
        /* ---- Why: the split bar and its statement (the mix) ----
           The bar centres on the Worth table's head row beside it; the rows are
           44 on hairlines, the total under the stronger rule, the method in a
           caption under them. */
        .fc-split-bar { display: flex; gap: var(--sp-0-5); height: var(--sp-2); max-width: var(--measure);
            margin-top: calc((var(--control-h) - var(--sp-2)) / 2); }
        .fc-split-bar > i { border-radius: var(--radius-full); }
        .fc-split-bar > .taken { width: var(--w); background: var(--c-taken); }
        .fc-split-bar > .still { flex: 1; background: var(--c-still); }
        .fc-drive { max-width: var(--measure); margin-top: calc((var(--control-h) - var(--sp-2)) / 2); }
        .fc-drive-row { display: flex; align-items: center; gap: var(--control-gap); height: var(--row-h); box-shadow: var(--rule-b-soft); }
        .fc-drive-row:nth-last-child(-n+2) { box-shadow: var(--rule-b); }
        .fc-drive-key { flex: none; width: var(--icon-xs); height: var(--dot-md); border-radius: var(--radius-swatch); }
        .fc-drive-key.taken { background: var(--c-taken); }
        .fc-drive-key.still { background: var(--c-still); }
        .fc-drive-lbl { flex: 1; color: var(--text-secondary); }
        .fc-drive-amt { flex: none; font-variant-numeric: tabular-nums; font-weight: var(--weight-medium); color: var(--text-primary); }
        .fc-drive-tot :is(.fc-drive-lbl, .fc-drive-amt) { color: var(--text-primary); font-weight: var(--weight-semibold); }
        .fc-foot { margin: var(--sp-3) 0 0; font-size: var(--text-xs); line-height: var(--lh-caption); color: var(--text-tertiary); }
        .fc-foot b { font-weight: var(--weight-medium); color: var(--text-secondary); white-space: nowrap; }
```

The old key was `--dot-lg`'s one reader, and an unread token fails `t_every_defined_token_is_read`: in `:root` replace `            --dot-md: 8px; --dot-lg: 10px;` with `            --dot-md: 8px;`.

- [ ] **Step 8: Update the guards**

In `t_an_icon_size_comes_from_the_scale_and_not_from_the_rule` replace:

```python
    for t in ("--box-xs", "--box-sm", "--box-md", "--box-lg", "--box-xl", "--box-2xl",
              "--dot-md", "--dot-lg"):
```

with:

```python
    # The mix (2026-10-06) draws every dot at the one 8px step: --dot-lg left
    # with its last reader, the old Why key.
    for t in ("--box-xs", "--box-sm", "--box-md", "--box-lg", "--box-xl", "--box-2xl",
              "--dot-md"):
```

In `t_beating_the_plan_is_not_something_worth_looking_at` replace:

```python
    row = SCRIPT.split("function fcAlertRow(", 1)[1].split("\n        }", 1)[0]
    ok("FC_VERDICT[a.verdict]" in row,
       "the alert tone comes from the map the month table uses, not a second opinion")
    ok("'warn'" not in row, "so nothing that beat its plan arrives in warning amber")
```

with:

```python
    # Since the mix (2026-10-06) a month's standing is its outlook, worked out
    # from the run's own codes in the words Cameron approved.
    row = fn_src("function fcOutlook(a) {")
    ok("FC_VERDICT_WORDS[a.verdict]" in row,
       "the outlook falls back on the words the month table uses, not a second opinion")
    ok("'warn'" not in row, "so nothing that beat its plan arrives in warning amber")
```

In `t_the_forecast_page_never_dresses_an_estimate_as_a_banked_figure` replace:

```python
    ok("Already taken" in dr and "Still expected" in dr,
       "the driver breakdown splits the month the same way")
```

with:

```python
    ok("'Taken so far'" in dr and "'Still expected'" in dr,
       "the driver breakdown splits the month the same way")
```

In `t_the_forecast_explains_itself_once_and_in_plain_lines` replace:

```python
    ok("The days left come from the source in use, " in dr, "and names the source it quotes")
```

with:

```python
    ok("' forecast by the '" in dr and "' method.'" in dr, "and names the method it quotes, in a caption under the rows")
```

- [ ] **Step 9: Run the tests**

Run: `ONLY=t_worth_looking_at_sits python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `450 passed, 0 failed`.

- [ ] **Step 10: Match it to the mockup**

At 1440 with the rig's forecast: Worth looking at with its count, three rows (Oct 2026 £53,691 £37,566, a green 42.9% chip, the range bar from 42.7% to 92.1% with the plan at 35.1%, "Safely ahead"; Nov "Likely ahead"; Dec "Likely behind"), Show all at the right when there are more than three; beside it "Why £53,691" with its info button (the method's name, its description, "It misleads when..." and More in the Guide), the split bar at 9.5%, Taken so far £5,116, Still expected £48,575, Expected this month £53,691, and "Rest of October forecast by the Big orders counted apart method." At 1024 with the sidebar open the two stack; at 390 the table is three columns in 60 rows. Read the bars: `[...document.querySelectorAll('.fc-wl .rg')].map(e => e.getAttribute('style'))`.

- [ ] **Step 11: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Forecast: Worth looking at as a table with small range bars and the approved outlooks, beside Why with its split bar and method

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 30: The numbers behind it, a method is a method, and the setup lines

**Files:**
- Modify: `static/index.html` the icon table, `fcTable` (14673-14694), `forecastSetupCard` (14733-14745), the dead helpers (14746-14760 and 14829-14858), `FC_ROWS` (14762), `fcOptimisedCard`, `fcAlgorithmsCard`, `fcRecordCard`, `fcSanityCard`, `fcTrust` (Task 26), `renderForecast` (the numbers section)
- Test: `tests/test_frontend.py` (`t_the_forecast_tab_exists_and_is_gated` 2210, `t_the_forecast_tab_shows_the_five_plain_models_and_what_they_scored` 4236, a new test)

**Interfaces:**
- Consumes: `listRows(items, opts)` (Task 16), `fcPage` (Task 26), `infoButton` (Task 12).
- Produces: `I.table`, `I.cash`, `I.columns`, `I.compare`; `fcTable` marks a number column with the `num` class; the Forecast screen says "method" wherever it said "source" (the service's own model names and their "Best at" lines are the service's words and stay).

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_the_numbers_behind_it_are_four_rows_and_a_method_is_a_method():
    """Spec 8.1 item 6 and Cameron's words: the numbers behind the forecast are
    four list rows in two columns, each opening its table in a window, and the
    forecast calls each model a method, never a source."""
    fn = SCRIPT.split("function renderForecast()")[1].split("\n        async function showReconView")[0]
    ok("listRows([" in fn and "{ cols: 2, label: 'The numbers behind it' }" in fn, "four list rows in two columns")
    labels = ["'Month by month against ' + sc", "'Cash under ' + sc", "'Every method, side by side'",
              "'What each method said, and what came in'"]
    at = [fn.find("label: " + l) for l in labels]
    ok(-1 not in at and at == sorted(at), "in the mockup's order: %s" % at)
    ok("fcDrawer(" not in SCRIPT and "LS_FCOPEN" not in SCRIPT and "fcSourceName" not in SCRIPT,
       "the drawers and their memory are gone, and so is the source picker nothing called")
    for name in ("fcOptimisedCard", "fcAlgorithmsCard", "fcRecordCard", "fcSanityCard", "fcTrust", "fcPlanJudged",
                 "fcDriversCard", "fcChartCard", "fcWorthCard", "fcBand", "fcHowItWorks"):
        # Its own strings only: comments go, and so does FC_BEST_AT (the
        # service's own words), which sits after fcOptimisedCard.
        body = re.sub(r"/\*.*?\*/", "", fn_src("function " + name + "(").split("const FC_BEST_AT")[0], flags=re.S)
        words = " ".join(re.findall(r"'((?:[^'\\]|\\.)*)'", body))
        ok(not re.search(r"\b[Ss]ources?\b(?!:)", words), name + " says method, not source: %s"
           % re.findall(r"[^.]*\b[Ss]ources?\b(?!:)[^.]*", words)[:2])
    ok("'Every method'" in SCRIPT and "'Every source'" not in SCRIPT, "the sanity table's chooser says method")
    tb = fn_src("function fcTable(head, rows, right) {")
    ok("th.classList.add('num')" in tb and "style.textAlign" not in tb, "a number column is the table's own class, not an inline style")
    setup = fn_src("function forecastSetupCard(c) {")
    ok("'The first run lands after 03:00.'" in setup and "'No cash flow workbook yet. Upload one above.'" in setup,
       "the setup lines are short")
    ok("infoButton('Setting up the forecast'" in setup, "and the setup steps wait behind an info button")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_the_numbers_behind python3 tests/test_frontend.py`
Expected: `FAIL  t_the_numbers_behind_it_are_four_rows_and_a_method_is_a_method: four list rows in two columns`

- [ ] **Step 3: Four icons**

In `const I = {` after `            shield: SV(` (Task 26) add:

```js
            table: SV('<path d="M12 3v18"></path><rect width="18" height="18" x="3" y="3" rx="2"></rect><path d="M3 9h18"></path><path d="M3 15h18"></path>'),
            cash: SV('<rect width="20" height="12" x="2" y="6" rx="2"></rect><circle cx="12" cy="12" r="2"></circle><path d="M6 12h.01M18 12h.01"></path>'),
            columns: SV('<rect width="18" height="18" x="3" y="3" rx="2"></rect><path d="M9 3v18"></path><path d="M15 3v18"></path>'),
            compare: SV('<circle cx="18" cy="18" r="3"></circle><circle cx="6" cy="6" r="3"></circle><path d="M13 6h3a2 2 0 0 1 2 2v7"></path><path d="M11 18H8a2 2 0 0 1-2-2V9"></path>'),
```

- [ ] **Step 4: The numbers are four list rows**

In `renderForecast` replace everything from the comment `            /* 4. DETAILS ON DEMAND. Tables carry precise money; the chart above` through `            numbers.append(detail);` with:

```js
            /* 4. THE NUMBERS BEHIND IT (the mix, spec 8.1 item 6): four list
               rows in two columns, each opening its table in a window. Tables
               carry precise money; the chart above carries the pattern. */
            const numbers = widget(el('div', 'widget-group'), 'numbers', 'full', 'The numbers behind it');
            numbers.append(el('div', 'section-title', 'The numbers behind it'));
            box.append(numbers);
            const monthTable = () => {
                const mc = el('div');
                /* fc-months: a month and its basis stay on one line each; the
                   table scrolls sideways on a phone rather than stacking
                   'May 2026' over two lines and the basis over three. */
                mc.append(fcTable(['Month', 'Basis', 'Projected', 'Likely low', 'Likely high', 'Plan', 'Gap', 'Verdict', 'Risk'],
                    rows.map(r => {
                        const t = (r.targets || {})[sc], v = (r.verdict || {})[sc], k = (r.risk || {})[sc];
                        return [fcMonth(r.month), FC_BASIS[r.method] || fcSentence((r.method || '').replace(/_/g, ' ')),
                                fcMoney(r.p50), fcMoney(r.p10), fcMoney(r.p90), fcMoney(t),
                                fcPct(t && r.p50 != null ? (r.p50 - t) / t : null),
                                v ? fcChip(FC_VERDICT[v] || 'note', FC_VERDICT_WORDS[v] || fcSentence(v)) : '',
                                k ? fcChip(FC_RISK[k] || 'note', fcSentence(k)) : ''];
                    }),
                    [0, 0, 1, 1, 1, 1, 1, 0, 0]));
                mc.lastChild.classList.add('fc-months');
                return mc;
            };
            const cash = (latest.cash || {})[sc] || [];
            const cashTable = () => {
                const cc = el('div');
                cc.append(el('p', 'card-sub', 'The projected sales pushed through the scenario’s own mechanics: its overheads and cost lines, the Shopify Capital remittance on gross, stopping when the loan is repaid.'));
                cc.append(fcTable(['Month', 'Gross sales', 'Repayment', 'Net cash', 'Working capital', 'Loan left'],
                    cash.map(r => { const wc = el('span'); wc.textContent = fcMoney(r.working_capital);
                        if (r.negative) wc.append(' ', fcChip('bad', 'negative')); else if (r.below_buffer) wc.append(' ', fcChip('warn', 'below buffer'));
                        return [fcMonth(r.month), fcMoney(r.gross_sales), fcMoney(r.repayment), fcMoney(r.net_cash), wc, fcMoney(r.loan_end)]; }),
                    [0, 1, 1, 1, 1, 1]));
                return cc;
            };
            const nsrc = ((latest.sanity || {}).models || []).length;
            numbers.append(listRows([
                { icon: I.table, label: 'Month by month against ' + sc, n: rows.length, unit: 'months',
                  onClick: () => fcPage('Month by month against ' + sc, monthTable) },
                cash.length ? { icon: I.cash, label: 'Cash under ' + sc, n: cash.length, unit: 'months',
                  onClick: () => fcPage('Cash under ' + sc, cashTable) } : null,
                { icon: I.columns, label: 'Every method, side by side', n: nsrc || null, unit: 'methods',
                  onClick: () => fcPage('Every method, side by side', () => fcUntitled(fcSanityCard(latest, sc))) },
                { icon: I.compare, label: 'What each method said, and what came in',
                  onClick: () => fcPage('What each method said, and what came in', () => fcUntitled(fcRecordCard(c))) },
            ], { cols: 2, label: 'The numbers behind it' }));
```

Delete the dead helpers: the two comments that begin `        /* How much of the source table to put on screen.` and `        /* Which source the three headline boxes speak for.` with `LS_FCSRC`, `fcSourceName` and `setFcSourceName` under them; and the comment `        /* Details on demand, remembered per person.` with `LS_FCOPEN`, `fcOpenSet`, `setFcOpen` and `fcDrawer`. Put the first comment's words back above `const LS_FCROWS` with "source" said as "method":

```js
        /* How much of the method table to put on screen. Twelve rows of models
           is a lot to land on someone who opened the page to read one number,
           so the default is the three that are quoted, and the choice is
           remembered per person. "Just the headline" is a single row: the
           method that leads, with the plan beside it. */
```

In `fcUntitled`'s comments replace `inside a drawer whose summary already` with `inside a window whose title already` and `inside a drawer it made three` with `inside a window it made three`, and `nested boxes (drawer, card, table), while the Month by month` with `nested boxes (window, card, table), while the Month by month`, and `and Cash drawers beside it hold their table directly.` with `and Cash windows beside it hold their table directly.`

- [ ] **Step 5: A number column is a class**

In `fcTable` replace `                if (right && right[i]) th.style.textAlign = 'right'; hr.append(th);` with `                if (right && right[i]) th.classList.add('num'); hr.append(th);` and `                    if (right && right[i]) td.style.textAlign = 'right';` with `                    if (right && right[i]) td.classList.add('num');`.

- [ ] **Step 6: Method, not source**

Make each of these replacements once (each old string appears once in the script; the script writes its curly apostrophes as the escape `\u2019`, so the table does too):

| Old | New |
|---|---|
| `['all', 'Every source']` | `['all', 'Every method']` |
| `'No source has been scored yet.'` | `'No method has been scored yet.'` |
| `'what came in. At the end of every month every source is marked again, and if another '` | `'what came in. At the end of every month every method is marked again, and if another '` |
| `'The sources arrive with the next run.'` | `'The methods arrive with the next run.'` |
| `'Every approach the system runs each night. It tries all of them, marks all of them, '` | `'Every method the system runs each night. It tries all of them, marks all of them, '` |
| `'Nothing has closed yet. From the end of this month, every source\u2019s prediction is '` | `'Nothing has closed yet. From the end of this month, every method\u2019s prediction is '` |
| `+ 'the record did not yet keep the source in use.' : '');` | `+ 'the record did not yet keep the method in use.' : '');` |
| `line = ' Which source the page was using is not on record for this month.';` | `line = ' Which method the page was using is not on record for this month.';` |
| `'Below, how far out each source\u2019s first figure for the month was. '` | `'Below, how far out each method\u2019s first figure for the month was. '` |
| `card.append(fcTable(['Source', 'Months', 'Average error', 'Closest'],` | `card.append(fcTable(['Method', 'Months', 'Average error', 'Closest'],` |
| `? 'The source that has been most right on this shop\u2019s own history, with what '` | `? 'The method that has been most right on this shop\u2019s own history, with what '` |
| `card.append(fcTable(['Source'].concat(months.map(fcMonth)).concat([` | `card.append(fcTable(['Method'].concat(months.map(fcMonth)).concat([` |
| `+ 'this source: the months already banked, which are the same whichever source you '` | `+ 'this method: the months already banked, which are the same whichever method you '` |
| `+ 'believe, plus this one\u2019s forecast for the rest. A star means the source does '` | `+ 'believe, plus this one\u2019s forecast for the rest. A star means the method does '` |
| `helpHead('Typical error', 'How far out this source usually was. Each was fitted to '` | `helpHead('Typical error', 'How far out this method usually was. Each was fitted to '` |
| `+ 'This matters more than the error: a source that leans high every single month '` | `+ 'This matters more than the error: a method that leans high every single month '` |
| `bc.append(el('p', 'card-sub', 'Each source was fitted to earlier months and marked against '` | `bc.append(el('p', 'card-sub', 'Each method was fitted to earlier months and marked against '` |

`FC_BEST_AT`'s keys and values are the forecasting service's own model names and lines, so they stay as the service sends them.

- [ ] **Step 7: The method's help is an info button**

In `fcSanityCard` replace:

```js
                /* Directors read this table. Every source carries a sentence
                   saying what it does, what it assumes and when it misleads,
                   on hover and on keyboard focus. */
                if (m.about) { name.title = m.about; name.classList.add('has-help'); name.tabIndex = 0; }
```

with:

```js
                /* Directors read this table. Every method carries a sentence
                   saying what it does, what it assumes and when it misleads,
                   behind an info button a tap and the keyboard open too. */
                if (m.about) name.append(infoButton(m.name, { title: m.name, body: m.about }));
```

and:

```js
            const helpHead = (text, about) => {
                const sp = el('span', 'has-help', text); sp.title = about; sp.tabIndex = 0; return sp;
            };
```

with:

```js
            const helpHead = (text, about) => {
                const sp = el('span', 'fc-th', text); sp.append(infoButton(text, { title: text, body: about })); return sp;
            };
```

After the rule `        .ktable th .fc-th-wrap { display: inline-block; white-space: normal; min-width: calc(var(--sp-8) * 3); max-width: calc(var(--sp-8) * 4); }` add:

```css
        /* A column head with its info button beside it. */
        .fc-th { display: inline-flex; align-items: center; gap: var(--sp-1); }
```

- [ ] **Step 8: The setup lines**

Replace the whole `forecastSetupCard` function with:

```js
        function forecastSetupCard(c) {
            const card = el('div', 'card');
            const head = el('div', 'card-title', 'No forecast yet');
            /* The steps name a setting and a file, so they wait behind the info
               button for the admin who needs them, word for word (the mix, 8.3). */
            if (!c.hook_configured) head.append(infoButton('Setting up the forecast', { title: 'Setting up the forecast',
                body: 'Set FORECAST_INGEST_TOKEN on Reactor and, with the same value, on the forecasting service; the service then posts here each night. The setup is in forecast/README.md.' }));
            card.append(head);
            if (c.hook_configured) card.append(el('p', 'card-sub', 'The first run lands after 03:00.'));
            if (c.last_error) card.append(el('p', 'card-sub', 'The last run, on ' + fmtDate(c.last_error.at)
                + ', did not finish. What the service reported: ' + String(c.last_error.error).slice(0, 300)));
            const wb = c.workbook || {};
            card.append(el('p', 'card-sub', wb.name ? ('Workbook on file: ' + wb.name + ', uploaded ' + fmtDate(wb.uploaded_at) + (wb.by ? ' by ' + wb.by : '') + '.')
                : 'No cash flow workbook yet. Upload one above.'));
            return card;
        }
```

- [ ] **Step 9: Update the Forecast guards**

In `t_the_forecast_tab_exists_and_is_gated` replace (as Task 26 left it):

```python
    for t in ("Month by month against ", "Every source, side by side"):
        ok("fcDrawer('" + t in fn, "'" + t + "' is a drawer, not dealt onto the screen")
```

with:

```python
    for t in ("Month by month against ", "Every method, side by side"):
        ok("label: '" + t in fn, "'" + t + "' is a list row that opens a window, not dealt onto the screen")
```

In `t_the_forecast_tab_shows_the_five_plain_models_and_what_they_scored` replace:

```python
    ok("name.title = m.about" in fn and "has-help" in fn and "name.tabIndex = 0" in fn,
       "every source says on hover what it does, what it assumes and when it misleads")
```

with:

```python
    ok("name.append(infoButton(m.name, { title: m.name, body: m.about }))" in fn,
       "every method says behind an info button what it does, what it assumes and when it misleads")
```

replace `    ok("'Source'" in fn, "the column is what it is: a source, not a model")` with `    ok("'Method'" in fn, "the column is what it is: a method (Cameron's word), not a model")`, replace `"'Every source'" in SCRIPT,` with `"'Every method'" in SCRIPT,`, and replace:

```python
    # It is a sanity CHECK: it belongs above the month table it is checking.
    ok(SCRIPT.index("fcSanityCard(latest, sc)")
       < SCRIPT.index("'Month by month against ' + sc"),
       "the check is read before the thing it checks")
```

with:

```python
    # Since the mix (2026-10-06) the four tables are list rows in the mockup's
    # order, each opening a window; the check sits beside what it checks.
    ok(SCRIPT.index("label: 'Month by month against ' + sc") < SCRIPT.index("label: 'Every method, side by side'"),
       "the month table, then every method beside it")
```

- [ ] **Step 10: Run the tests**

Run: `ONLY=t_the_numbers_behind python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `451 passed, 0 failed`.

- [ ] **Step 11: Look at it, the whole screen**

Forecast at 1440 beside the mockup's 01: header, tabs with Plan, the band, Cash in, Worth looking at beside Why, and the four list rows in two columns (Month by month against Algorithm 1 with 12, Cash under Algorithm 1 with 12, Every method side by side with 13, What each method said with no count), each opening its table in a window with the method names' info buttons in Every method. At 390 against the phone mockup. Search the screen for the word: `document.querySelector('#view-forecast').innerText.match(/\bsources?\b/gi)` is `null` apart from the service's own model names.

- [ ] **Step 12: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Forecast: the numbers behind it as four list rows that open windows, method for source throughout, and short setup lines

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 31: Every flow queue's size, from the sweep the queue already makes

**Files:**
- Modify: `copilot.py:7227-7286` (`run_production_labels`, the swept path's return)
- Modify: `tests/test_dispatch.py:26474` (the runner loop learns `ONLY=`)
- Test: `tests/test_dispatch.py` (a new test after `t_a_tag_write_retires_the_snapshot_immediately`)

**Interfaces:**
- Consumes: `_has_tag(order, tag)` (5309), `UNPROCESSED_TAG`, `PRODUCTION_TAG`, `MADE_TAG`, the `orders` snapshot `run_production_labels` already holds.
- Produces: `/api/production-labels` answers with an additive `counts: {"unprocessed": n, "make": n, "ship": n}` on every swept load (absent on the one-order deep link). Nothing else in the answer changes, and no Shopify call is added. `ONLY=<part of a name> .venv/bin/python tests/test_dispatch.py` runs only the server tests whose name contains it.

- [ ] **Step 1: Let the server suite run one test**

In `tests/test_dispatch.py` replace the runner's first line `for fn in TESTS:` with:

```python
for fn in [t for t in TESTS if os.environ.get("ONLY", "") in t.__name__]:
```

- [ ] **Step 2: Write the failing test**

Directly after the whole `t_a_tag_write_retires_the_snapshot_immediately` test add:

```python
@test
def t_the_queue_counts_ride_along_from_the_same_sweep():
    # The mix (2026-10-06): the Production Manager shows the size of every flow
    # queue at once, as counters. They come back with whichever queue was asked
    # for, from the sweep that load already made: no second Shopify call.
    orders = QUEUE_ORDERS + [
        {"id": 999, "order_number": 3, "name": "#3", "created_at": "2026-08-12T09:00:00Z",
         "tags": "Unprocessed", "line_items": [], "customer": {}, "shipping_address": {}},
        {"id": 1000, "order_number": 4, "name": "#4", "created_at": "2026-08-12T09:00:00Z",
         "tags": "IP, Rush", "line_items": [], "customer": {}, "shipping_address": {}},
    ]
    calls, tools = sweep_counter(orders)
    saved = copilot._tool_json; copilot._tool_json = tools
    try:
        res = with_cache(lambda: run(copilot.run_production_labels({}, tag="PC")))
        eq(res.get("counts"), {"unprocessed": 1, "make": 2, "ship": 1}, "every flow queue is counted")
        eq([o["id"] for o in res["orders"]], [888], "the queue asked for is unchanged")
        eq(calls["n"], 1, "from the one sweep")
        one = run(copilot.run_production_labels({}, order_id=12345))
        ok("counts" not in one, "the one-order deep link swept nothing, so it counts nothing")
    finally:
        copilot._tool_json = saved
```

- [ ] **Step 3: Run it to see it fail**

Run: `ONLY=t_the_queue_counts .venv/bin/python tests/test_dispatch.py`
Expected: `  FAIL  t_the_queue_counts_ride_along_from_the_same_sweep: every flow queue is counted: None != {'unprocessed': 1, 'make': 2, 'ship': 1}`, then `0 passed, 1 failed`.

- [ ] **Step 4: Count from the snapshot**

In `run_production_labels`, after the line `    tagged.sort(key=lambda o: str(o.get("created_at") or ""), reverse=True)` add:

```python
    # The flow's three queues counted from the same snapshot (the mix's queue
    # counters, 2026-10-06), so the bench sees every queue's size at once
    # without another Shopify call.
    counts = {key: sum(1 for o in orders if _has_tag(o, qtag))
              for key, qtag in (("unprocessed", UNPROCESSED_TAG), ("make", PRODUCTION_TAG), ("ship", MADE_TAG))}
```

and in its final `return` replace `            "partial_note": partial,` with:

```python
            "partial_note": partial, "counts": counts,
```

- [ ] **Step 5: Run it, then the queue tests around it**

Run: `ONLY=t_the_queue_counts .venv/bin/python tests/test_dispatch.py && ONLY=queue .venv/bin/python tests/test_dispatch.py | tail -1`
Expected: `1 passed, 0 failed`, then a line ending `passed, 0 failed`.

- [ ] **Step 6: Commit**

Run the release-note command, then:

```bash
git add copilot.py tests/test_dispatch.py data/changelog.json
git commit -m "Production Manager: the queue load also counts the Unprocessed, To make and To ship queues from the sweep it already makes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 32: The Production Manager's header, queue counters and toolbar counts

**Files:**
- Modify: `static/index.html` `queueTag` (12343), `renderCustomQueue` (17780-17880), `loadLabels` (17332-17360), `renderLabels` (17910-18166: the header, the tab strip, the filters, the missing-tag line, the queue card head, the empty lines), the stylesheet after `.lbl-count`
- Test: `tests/test_frontend.py` (`t_the_production_toolbar_is_sorted_not_shortened` 2876, `t_the_custom_shipment_queue_speaks_its_own_tab_s_language` 1596, `t_a_queue_row_keeps_its_buttons_in_the_last_column` 9067, a new test)

**Interfaces:**
- Consumes: `pageHead` with `live`, `onRefresh`, `info`, `actions` (Tasks 7 and 12), `queueCounters` (Task 20), `emptyState` (Task 18), `infoButton` (Task 12), `chooser` items with `n` (Task 10), the server's `counts` (Task 31).
- Produces: `labelsCounts` (the last counts the server sent) and `prodQueues(onPick)`, the counters and tabs both queue renderers draw. The queue card has no head: its actions are the page header's.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_the_production_manager_is_the_mix_page():
    """Spec 8.2: the header with the live line and Refresh, then Collections,
    New shipment and More; counters for Unprocessed, To make and To ship with
    Complete and Custom shipments as tabs beside them; the toolbar exactly as it
    was, its filters counted; the two queue rules worth keeping behind an info
    button; an empty queue one line and the way on (copy plan, Production
    Manager #1 to #16)."""
    ok("function prodQueues(onPick) {" in SCRIPT, "one builder draws the queues for both renderers")
    fn = fn_src("function renderLabels() {")
    for part in ("pageHead({ view: 'labels', title: 'Production Manager', live: labelsCache.at",
                 "infoButton('About this queue'", "box.append(prodQueues(",
                 "[pnBtn, coll, newShip, more].filter(Boolean).forEach(b => heroActs.append(b));",
                 "{ key: 'all', label: 'All', n: orders.length }", "tableTools([findWrap, filtTabs],",
                 "[allBtn, slBtn, oldf, sizeSel].filter(Boolean)", "if (data.counts) labelsCounts = data.counts;",
                 "'Nothing on the bench.'", "'Go to Unprocessed'", "'One order, opened from Shopify. Refresh for all.'",
                 "'First ' + lm.checked + ' open orders checked: none missing the tag.'"):
        ok(part in fn, "renderLabels: " + part)
    ok("tabStrip(QUEUE" not in SCRIPT and "el('div', 'card-head')" not in fn and "'The bench queue, from" not in SCRIPT,
       "no strip of queue tabs, no queue card title, no intro")
    pq = fn_src("function prodQueues(onPick) {")
    ok("queueCounters(QUEUE.slice(0, 3)" in pq and "I.check" in pq and "I.box" in pq, "three counters, two tabs")
    cq = fn_src("async function renderCustomQueue(box) {")
    ok("pageHead({ view: 'labels'" in cq and "prodQueues(" in cq and "'No custom shipments yet.'" in cq,
       "Custom shipments is the same page")
    ld = fn_src("async function loadLabels(force, fresh) {")
    ok("pageHead({ view: 'labels', title: 'Production Manager', line: 'Finding orders tagged" in ld, "and so is the loading state")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_the_production_manager_is python3 tests/test_frontend.py`
Expected: `FAIL  t_the_production_manager_is_the_mix_page: one builder draws the queues for both renderers`

- [ ] **Step 3: The header, the counters, the toolbar counts and the words**

Make each replacement below once (each old block appears once).

In `loadLabels` (the loading state) replace:

```js
            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.printer;
            const ht = el('div'); ht.append(el('h2', null, 'Production Manager'), el('p', null, 'Finding orders tagged "' + queueTag() + '"…'));
            hero.append(badge, ht); box.append(hero);
```

with:

```js
            const hero = pageHead({ view: 'labels', title: 'Production Manager', line: 'Finding orders tagged "' + queueTag() + '"…' });
            box.append(hero);
```

Replace the `queueTag` line:

```js
        function queueTag() { const q = QUEUE.find(x => x[0] === queueMode); return q ? q[2] : LABEL_TAG; }
```

with:

```js
        function queueTag() { const q = QUEUE.find(x => x[0] === queueMode); return q ? q[2] : LABEL_TAG; }
        /* The queues (the mix, spec 8.2): the flow's three as counters with the
           sizes the server last sent, Complete and Custom shipments as tabs
           beside them. Kept here so Custom shipments, which loads no orders,
           still shows the counts. */
        let labelsCounts = null;
        function prodQueues(onPick) {
            const n = labelsCounts || {};
            return queueCounters(QUEUE.slice(0, 3).map(q => [q[0], q[1], n[q[0]]]),
                [[QUEUE[3][0], QUEUE[3][1], I.check], [QUEUE[4][0], QUEUE[4][1], I.box]], queueMode, onPick, 'Queues');
        }
```

In `renderCustomQueue` replace the header, the tab strip and the card head:

```js
            const hero = el('div', 'ov-hero');
            const badge = el('div', 'badge'); badge.innerHTML = I.printer;
            const ht = el('div');
            ht.append(el('h2', null, 'Production Manager'),
                el('p', null, 'The bench queue, from a new order through to a booked courier. '
                    + 'Pick a queue below, then an order to work on.'));
            hero.append(badge, ht, heroAct(freshLabel(Date.now()), refreshBtn(() => renderCustomQueue(box))));
            box.append(hero);
            box.append(tabStrip(QUEUE, queueMode, (k) => { queueMode = k; labelsCache = null; labelSel = null; loadLabels(true); }, { label: 'Queues' }));
            const card = el('div', 'card');
            const head = el('div', 'card-head');
            const title = el('h3', 'card-title', 'Shipments');
            head.append(title, el('p', 'card-desc', 'Booked to an address you pasted in, with no Shopify order behind them. '
                + 'Reprint a label or check a tracking number here.'));
            const act = el('div', 'card-act');
            const newShip = el('button', 'btn btn-sm');
            newShip.append(ico(I.plus), document.createTextNode('New shipment'));
            newShip.onclick = openCustomShip;
            act.append(newShip); head.append(act);
            card.append(head);
```

with:

```js
            const newShip = el('button', 'btn btn-sm');
            newShip.append(ico(I.plus), document.createTextNode('New shipment'));
            newShip.onclick = openCustomShip;
            box.append(pageHead({ view: 'labels', title: 'Production Manager', live: Date.now(),
                onRefresh: () => renderCustomQueue(box), refreshLabel: 'Refresh', actions: [newShip] }));
            box.append(prodQueues((k) => { queueMode = k; labelsCache = null; labelSel = null; loadLabels(true); }));
            const card = el('div', 'card');
```

In its `paint`, replace the title count and the empty line:

```js
                title.textContent = rows.length + (rows.length === 1 ? ' shipment' : ' shipments');
                if (!shown.length) {
                    host.append(el('div', 'empty', rows.length
                        ? 'Nothing matches that.'
                        : 'No shipments booked to a pasted address yet. Press New shipment to book one.'));
                    return;
                }
```

with:

```js
                if (!shown.length) {
                    if (rows.length) { host.append(el('div', 'empty', 'Nothing matches that.')); return; }
                    const again = el('button', 'btn'); again.type = 'button';
                    again.append(ico(I.plus), document.createTextNode('New shipment'));
                    again.onclick = openCustomShip;
                    host.append(emptyState({ icon: I.box, text: 'No custom shipments yet.', action: again }));
                    return;
                }
```

In `renderLabels` replace the header:

```js
            const heroCopy = dispatched ? 'Orders already dispatched. Select one to reprint its label or view tracking.'
                : shipMode ? 'Orders marked made and ready to ship. Select one to dispatch a courier.'
                : unproc ? 'New orders not yet released to the workbench. Press Ready to make when one should join the To make queue.'
                : 'Orders released to the bench (tagged "' + (data.tag || LABEL_TAG) + '" in Shopify). Select one to preview its label, then print.';
            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.printer;
            /* The page says what the page is; the queue card below says what
               THIS queue is. Printing heroCopy in both put the same sentence on
               the screen twice, six lines apart. */
            const ht = el('div'); ht.append(el('h2', null, 'Production Manager'),
                el('p', null, 'The bench queue, from a new order through to a booked courier. '
                    + 'Pick a queue below, then an order to work on.'));
            hero.append(badge, ht);
            /* The stamp and the Refresh that renews it, side by side in the
               header, as heroAct is for: Refresh sat in the queue card's rail
               175px below the stamp it updates. */
            hero.append(heroAct(freshLabel(labelsCache.at), refreshBtn(() => loadLabels(true, true))));
            box.append(hero);
```

with:

```js
            /* The header (the mix, spec 8.2): the live line with Refresh, and the
               page's actions at the right (added below, where they are built).
               The rule of the two queues worth explaining waits behind the info
               button, word for word; the counters say the rest. */
            const queueRule = unproc ? 'New orders not yet released to the workbench. Press Ready to make when one should join the To make queue.'
                : queueMode === 'make' ? 'Orders released to the bench (tagged "' + (data.tag || LABEL_TAG) + '" in Shopify). Select one to preview its label, then print.'
                : '';
            const hero = pageHead({ view: 'labels', title: 'Production Manager', live: labelsCache.at,
                onRefresh: () => loadLabels(true, true), refreshLabel: 'Refresh',
                info: queueRule ? infoButton('About this queue', { title: unproc ? 'Unprocessed' : 'To make', body: queueRule }) : null });
            box.append(hero);
            const heroActs = hero.querySelector('.ov-hero-act');
```

Replace the tab strip:

```js
            // Lifecycle queue: To make -> To ship -> Complete.
            box.append(tabStrip(QUEUE, queueMode, (k) => { queueMode = k; labelsCache = null; labelSel = null; labelsFilter = 'all'; loadLabels(true); }, { label: 'Queues' }));
```

with:

```js
            // Lifecycle queue: Unprocessed -> To make -> To ship, then Complete.
            if (data.counts) labelsCounts = data.counts;
            box.append(prodQueues((k) => { queueMode = k; labelsCache = null; labelSel = null; labelsFilter = 'all'; loadLabels(true); }));
```

Replace the filters (the toolbar keeps its items and order; the counts become the chooser's own):

```js
                filtTabs = segmented([['all', 'All (' + orders.length + ')'],
                                       ['unprinted', 'Unprinted (' + unprinted.length + ')']]
                                      .concat(shipMode ? [] : [['unmade', 'Not made (' + unmade.length + ')']]),
                                      labelsFilter, (k) => { labelsFilter = k; renderLabels(); });
```

with:

```js
                filtTabs = segmented([{ key: 'all', label: 'All', n: orders.length },
                                       { key: 'unprinted', label: 'Unprinted', n: unprinted.length }]
                                      .concat(shipMode ? [] : [{ key: 'unmade', label: 'Not made', n: unmade.length }]),
                                      labelsFilter, (k) => { labelsFilter = k; renderLabels(); }, { label: 'Show' });
```

Replace the missing-tag check's line (copy plan, Production Manager #16):

```js
                ? el('div', 'cov-note', 'Only the first ' + lm.checked + ' open orders could be checked for a missing "'
                    + (lm.tag || LABEL_TAG) + '" tag, and none of those is missing it.') : null;
```

with:

```js
                ? el('div', 'cov-note', 'First ' + lm.checked + ' open orders checked: none missing the tag.') : null;
```

Replace the queue card's head:

```js
            const qCard = el('div', 'card q-card');
            const qHead = el('div', 'card-head');
            qHead.append(el('h3', 'card-title', data.single
                ? 'One order'
                : orders.length + (orders.length === 1 ? ' order' : ' orders')
                  + (dispatched ? ' dispatched' : shipMode ? ' ready to ship'
                     : unproc ? ' waiting' : ' in production')));
            qHead.append(el('p', 'card-desc', data.single
                ? 'Opened from the order page. Refresh shows the full production list.'
                : heroCopy));
            const qAct = el('div', 'card-act');
```

with:

```js
            const qCard = el('div', 'card q-card');
            /* No title: the counters carry the count it gave. One order opened
               from Shopify says so. */
            if (data.single) qCard.append(el('p', 'q-note', 'One order, opened from Shopify. Refresh for all.'));
```

and replace where its actions were placed:

```js
            [pnBtn, coll, newShip, more].filter(Boolean).forEach(b => qAct.append(b));
            qHead.append(qAct);
            qCard.append(qHead);
```

with:

```js
            /* The page's own actions ride in its header (the mix, spec 8.2), in
               the order they always had. */
            [pnBtn, coll, newShip, more].filter(Boolean).forEach(b => heroActs.append(b));
```

Replace the empty queue's line (copy plan #8 to #11):

```js
            if (!orders.length) {
                const emptyCopy = dispatched ? 'No orders have been dispatched yet. Dispatch one from the "To ship" queue.'
                    : queueMode === 'ship' ? 'Nothing is ready to ship. Mark orders made in "To make" to move them here.'
                    : unproc ? 'Nothing is waiting. New orders tagged "Unprocessed" in Shopify will appear here for release.'
                    : 'Nothing is on the bench. Release an order from Unprocessed, or tag one "' + (data.tag || LABEL_TAG) + '" in Shopify and refresh.';
                qCard.append(el('div', 'empty', emptyCopy));
                return;
            }
```

with:

```js
            if (!orders.length) {
                /* One line and the way on (the mix, spec 6 and 7). */
                const goUnproc = el('button', 'btn'); goUnproc.type = 'button';
                goUnproc.append(ico(I.clock), document.createTextNode('Go to Unprocessed'));
                goUnproc.onclick = () => { queueMode = 'unprocessed'; labelsCache = null; labelSel = null; labelsFilter = 'all'; loadLabels(true); };
                qCard.append(emptyState(dispatched ? { icon: I.check, text: 'Nothing dispatched yet.' }
                    : shipMode ? { icon: I.truck, text: 'Nothing ready to ship.' }
                    : unproc ? { icon: I.clock, text: 'Nothing waiting to be released.' }
                    : { icon: I.printer, text: 'Nothing on the bench.', action: goUnproc }));
                return;
            }
```

and the search that matched nothing (#13):

```js
                    ? ('Nothing in this queue matches "' + labelsSearch + '". Clear the search, or check another queue tab.')
```

with:

```js
                    ? ('Nothing in this queue matches \u201c' + labelsSearch + '\u201d.')
```

In `renderCustomQueue` replace the comment that begins `            /* The same page as the other four queue tabs: the same heading and` (five lines) with:

```js
            /* The same page as the other queues (the mix): the same header with
               its live line and Refresh, the same counters and tabs, then the
               house search and the list. */
```

- [ ] **Step 4: The single-order line**

After the rule `        .lbl-count { font-size: var(--text-xs); color: var(--text-tertiary); }` add:

```css
        /* One order opened from Shopify says so over the toolbar. */
        .q-note { margin: 0 0 var(--sp-3); color: var(--text-tertiary); }
```

- [ ] **Step 5: Update the guards**

In `t_the_production_toolbar_is_sorted_not_shortened` replace:

```python
    ok("segmented([['all'" in fn, "the filters are a counted segmented control: a choice of what the card shows")
```

with:

```python
    ok("segmented([{ key: 'all', label: 'All', n: orders.length }" in fn,
       "the filters are a segmented control with counts: a choice of what the list shows")
```

and replace:

```python
    ok("el('p', 'card-desc', data.single" in fn, "which the card carries instead")
```

with:

```python
    ok("infoButton('About this queue'" in fn and "el('p', 'card-desc'" not in fn,
       "the queue's rule waits behind the header's info button (the mix), not under a card title")
```

In `t_the_custom_shipment_queue_speaks_its_own_tab_s_language` replace:

```python
    ok("tableSearch('Search reference, name or tracking'" in fn and "el('div', 'card-head')" in fn
       and "heroAct(" in fn, "the list sits in a card like the order queues' own")
```

with:

```python
    # Since the mix (2026-10-06) its page is the order queues' own: the same
    # header, the same counters and tabs, the house search, no card title.
    ok("tableSearch('Search reference, name or tracking'" in fn and "pageHead({ view: 'labels'" in fn
       and "prodQueues(" in fn, "the list sits on the same page as the order queues' own")
```

In `t_a_queue_row_keeps_its_buttons_in_the_last_column` replace `    i = SCRIPT.index("No shipments booked to a pasted address yet.")` with `    i = SCRIPT.index("'No custom shipments yet.'")`.

- [ ] **Step 6: Run the tests**

Run: `ONLY=t_the_production_manager_is python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `452 passed, 0 failed`.

- [ ] **Step 7: Look at it**

Production Manager at 1440 in the rig: "Production Manager", the green dot, "Updated just now" and Refresh; the info button beside the title on To make; at the right Collections, New shipment, More (and Print new when some are printed and some are not). Under it the three counters with their figures and the chevrons, To make teal, and Complete and Custom shipments as tabs. The toolbar: the search, All 6 / Unprinted 6 / Not made 6, then Print all (6), Newest first and the label size. Custom shipments: the same header with New shipment, the counters, and with nothing booked a box tile, "No custom shipments yet." and New shipment.

- [ ] **Step 8: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Production Manager: the mix header with its live line, queue counters with their sizes, counted filters, and one-line empty queues

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 33: Order rows on hairlines, the open order as one block, and the phone's worded buttons

**Files:**
- Modify: `static/index.html` `:root` (after `--qc-w`), the icon table, the `.lbl-grid` track lists (2340, 2377), the stylesheet after `.lbl-actions` (2382), `renderLabels` (the row's Preview, Print, Ready to make and Dispatch buttons, the preview)
- Test: `tests/test_frontend.py` (a new test)

**Interfaces:**
- Consumes: `--order-row-h` (Task 4), `--action-selected`, `--ring-selected`, `--rule-t`, `--rule-b-soft`, `--shadow-label` (Task 3), `--gap-cluster` (Task 4), `pvOn` (this task), `unproc` and `shipMode` (in `renderLabels`).
- Produces: `I.eyeOff`; `--ono-w` (the order number's column, 100); `.swap` (a button label that holds the width of its longest word); `.grp` (a button that starts a group 16 from the one before); `.lbl-frame` (the label preview's frame). Every row keeps its cells, chips, buttons, titles and handlers; only their look changes.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_an_order_row_is_a_hairline_row_and_the_open_one_is_one_block():
    """Spec 6 and 8.2: order rows are 64 tall with a hairline between them; the
    Preview / Hide toggle keeps one width so no column moves; the open row and
    its preview are one block in the teal wash with the teal bar; the open
    order's Print is the screen's one primary; the label sits in a frame with
    its own shadow; on a phone the buttons keep their words, three then two.
    What the rows hold and do is the queue's own and does not change."""
    fn = fn_src("function renderLabels() {")
    for part in ("const pv = el('button', 'btn btn-sm');", "el('span', 'lbl-btn-txt swap')", "ico(pvOn ? I.eyeOff : I.eye)",
                 "if (pvOn && !unproc && !shipMode) pr.classList.add('btn-primary');", "el('figure', 'lbl-frame')",
                 "const p2 = el('button', 'btn');", "db.classList.add('grp');", "rd.classList.add('grp');"):
        ok(part in fn, "renderLabels: " + part)
    ok("wrap.style.margin" not in fn and "act.style.marginTop" not in fn, "no inline spacing in the preview")
    ok("eyeOff: SV(" in SCRIPT, "Hide has its own glyph")
    row = CSS.split("\n        .lbl-qrow {")[1].split("}")[0]
    ok("min-height: var(--order-row-h)" in row and "box-shadow: var(--rule-b-soft)" in row and "border: 0" in row,
       "a 64 row on a hairline, no box")
    on = CSS.split('\n        .lbl-qrow:is(.on, [aria-selected="true"]) {')[1].split("}")[0]
    ok("background: var(--action-selected)" in on and "var(--ring-selected)" in on, "the open row is the teal wash with the teal bar")
    pv = CSS.split("\n        .lbl-grid > .lbl-preview {")[1].split("}")[0]
    ok("background: var(--action-selected)" in pv and "var(--ring-selected)" in pv, "and its preview carries on the same block")
    ok(".swap > .gone { visibility: hidden; }" in CSS, "the toggle's other word holds its width")
    frame = CSS.split("\n        .lbl-frame {")[1].split("}")[0]
    ok("box-shadow: var(--shadow-label)" in frame and "border-radius: var(--radius-control)" in frame, "the label's frame")
    phone = CSS[CSS.index("/* A list as narrow as a phone's: worded 40 buttons"):][:900]
    ok("grid-template-columns: repeat(6, minmax(0, 1fr))" in phone and ".lbl-qrow .lbl-actions .lbl-btn-txt { display: inline; }" in phone,
       "on a phone the buttons keep their words in a grid, three then two")
    eq(_token_raw("ono-w"), "100px", "--ono-w")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_an_order_row_is python3 tests/test_frontend.py`
Expected: `FAIL  t_an_order_row_is_a_hairline_row_and_the_open_one_is_one_block: renderLabels: el('span', 'lbl-btn-txt swap')`

- [ ] **Step 3: The token and the column it names**

In `:root` replace `            --qc-w: 184px;          /* a queue counter */` with:

```
            --qc-w: 184px;          /* a queue counter */
            --ono-w: 100px;         /* an order row's number column */
```

Replace `            .lbl-grid { display: grid; grid-template-columns: 100px minmax(0, 1fr) max-content max-content;` with `            .lbl-grid { display: grid; grid-template-columns: var(--ono-w) minmax(0, 1fr) max-content max-content;`, and `            .lbl-grid { grid-template-columns: 100px minmax(220px, 1fr) minmax(0, 210px) max-content max-content; }` with `            .lbl-grid { grid-template-columns: var(--ono-w) minmax(220px, 1fr) minmax(0, 210px) max-content max-content; }`.

- [ ] **Step 4: The row's buttons and the preview**

Make each replacement below once.

In `const I = {` replace the `check` line:

```js
            check: SV('<polyline points="20 6 9 17 4 12"></polyline>'),
```

with:

```js
            check: SV('<polyline points="20 6 9 17 4 12"></polyline>'),
            eyeOff: SV('<path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"></path><path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"></path><path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"></path><path d="m2 2 20 20"></path>'),
```

In `renderLabels` replace the Preview button's line:

```js
                const pv = el('button', 'btn btn-sm'); pv.title = labelSel === o.id ? 'Hide label preview' : 'Preview label'; pv.append(ico(I.eye), el('span', 'lbl-btn-txt', labelSel === o.id ? 'Hide' : 'Preview'));
```

with:

```js
                const pv = el('button', 'btn btn-sm'); pv.title = labelSel === o.id ? 'Hide label preview' : 'Preview label';
                /* Preview and Hide hold one width (the mix, spec 6), so no column
                   moves when a row opens: both words lie in one cell and the one
                   not in use is hidden. */
                const pvOn = labelSel === o.id;
                const pvTxt = el('span', 'lbl-btn-txt swap');
                pvTxt.append(el('span', pvOn ? 'gone' : null, 'Preview'), el('span', pvOn ? null : 'gone', 'Hide'));
                pv.append(ico(pvOn ? I.eyeOff : I.eye), pvTxt);
                pv.setAttribute('aria-expanded', pvOn ? 'true' : 'false');
```

Replace the Print button's line:

```js
                const pr = el('button', 'btn btn-sm'); pr.title = 'Print label'; pr.append(ico(I.printer), el('span', 'lbl-btn-txt', 'Print'));
```

with:

```js
                const pr = el('button', 'btn btn-sm'); pr.title = 'Print label'; pr.append(ico(I.printer), el('span', 'lbl-btn-txt', 'Print'));
                /* The open order's Print is the screen's one primary action (the
                   mix, spec 8.2), unless its row has its own: To ship's Dispatch,
                   Unprocessed's Ready to make. */
                if (pvOn && !unproc && !shipMode) pr.classList.add('btn-primary');
```

Replace Ready to make's handler line, so the state change starts its own group:

```js
                        rd.onclick = (e) => { e.stopPropagation(); readyToMake(o, rd); };
```

with:

```js
                        rd.onclick = (e) => { e.stopPropagation(); readyToMake(o, rd); };
                        rd.classList.add('grp');   /* a state change starts its own group */
```

Replace Dispatch's handler line the same way:

```js
                    db.onclick = (e) => { e.stopPropagation(); openDispatch(o); };
```

with:

```js
                    db.onclick = (e) => { e.stopPropagation(); openDispatch(o); };
                    db.classList.add('grp');   /* a state change starts its own group */
```

Replace the preview's opening lines:

```js
                    const wrap = el('div', 'lbl-preview');
                    /* On the page, below the queue card. No top margin: in the
                       flow the card's own 24 swallowed it, and in the widget grid
                       it would add to the gap. */
                    if (!pane) wrap.style.margin = '0 0 var(--sp-4)';
                    if (o.customer_id) wrap.append(histLine(o));
                    const sheet = labelSheet(o);
                    wrap.append(sheet);
                    const note = el('div', 'lbl-preview-note'); wrap.append(note);
                    const act = el('div', 'lbl-toolbar'); act.style.marginTop = 'var(--sp-3)';
                    const p2 = el('button', 'btn btn-primary'); p2.append(ico(I.printer), document.createTextNode('Print this label'));
```

with:

```js
                    const wrap = el('div', 'lbl-preview');
                    /* The open row and its preview are one block (the mix, spec
                       8.2): the teal wash and the teal bar run on under the row. */
                    if (o.customer_id) wrap.append(histLine(o));
                    const sheet = labelSheet(o);
                    /* The label in a frame with its own shadow. The sheet inside
                       is the print's, untouched. */
                    const frame = el('figure', 'lbl-frame'); frame.append(sheet);
                    wrap.append(frame);
                    const note = el('div', 'lbl-preview-note'); wrap.append(note);
                    const act = el('div', 'lbl-toolbar');
                    /* Not a second primary: the open row's Print is the one. */
                    const p2 = el('button', 'btn'); p2.append(ico(I.printer), document.createTextNode('Print this label'));
```

- [ ] **Step 5: The rules**

After the rule `        .lbl-actions { display: flex; gap: var(--sp-2); align-items: center; flex: 0 1 auto; min-width: 0; justify-content: flex-end; }` (its gap reads `var(--control-gap)` if Task 8 moved it) add:

```css
        /* THE ORDER ROW (the mix, spec 6 and 8.2): a hairline between orders
           instead of a box round each, 64 tall; the open row and its preview
           one block in the teal wash with the teal bar; Preview and Hide one
           width; a state change starts its own group. The queue's content and
           actions are its own and do not change. */
        .lbl-grid { box-shadow: var(--rule-t); }
        .lbl-qrow { min-height: var(--order-row-h); padding: var(--sp-2) var(--sp-3); margin-bottom: 0; border: 0; border-radius: 0;
            background: none; box-shadow: var(--rule-b-soft); }
        .lbl-qrow:is(.on, [aria-selected="true"]) { background: var(--action-selected); box-shadow: var(--ring-selected), var(--rule-b-soft); }
        .lbl-qrow .lbl-name { font-size: var(--text-sm); font-weight: var(--weight-medium); }
        .lbl-actions .grp { margin-left: calc(var(--gap-cluster) - var(--control-gap)); }
        .swap { display: inline-grid; }
        .swap > span { grid-area: 1 / 1; }
        .swap > .gone { visibility: hidden; }
        .lbl-grid > .lbl-preview { padding: 0 var(--sp-3) var(--sp-6); background: var(--action-selected);
            box-shadow: var(--ring-selected), var(--rule-b-soft); }
        @container queue (min-width: 560px) {
            .lbl-grid > .lbl-preview { padding-left: calc(var(--sp-3) + var(--ono-w) + var(--sp-2-5)); }
        }
        .lbl-pane > .lbl-preview { padding: var(--sp-4); border-radius: var(--radius-tile); background: var(--action-selected); }
        .lbl-preview > .lbl-hist { margin: 0 0 var(--sp-3); }
        .lbl-preview > .lbl-toolbar { margin: var(--sp-3) 0 0; }
        .lbl-frame { margin: 0; width: fit-content; max-width: 100%; border-radius: var(--radius-control); box-shadow: var(--shadow-label); }
        /* A list as narrow as a phone's: worded 40 buttons in a grid, three on
           the first line and two on the second (the mix, spec 8.2); the label
           is scaled there, so its frame draws no shadow. */
        @container queue (max-width: 559px) {
            .lbl-qrow { padding: var(--sp-3); row-gap: var(--sp-3); }
            .lbl-qrow .lbl-actions { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: var(--control-gap); }
            .lbl-qrow .lbl-actions > .btn { grid-column: span 2; padding: 0 var(--sp-2); justify-content: center; }
            .lbl-qrow .lbl-actions > .btn:nth-child(n+4) { grid-column: span 3; }
            .lbl-qrow .lbl-actions > .grp { margin-left: 0; }
            .lbl-qrow .lbl-actions .lbl-btn-txt { display: inline; }
            .lbl-qrow .lbl-actions .lbl-btn-txt.swap { display: inline-grid; }
            .lbl-frame { box-shadow: none; }
        }
```

- [ ] **Step 6: Run the tests**

Run: `ONLY=t_an_order_row_is python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `453 passed, 0 failed` (the print freeze among them: nothing that prints moved).

- [ ] **Step 7: Look at it**

To make at 1440 in the rig: six rows on hairlines, 64 tall; press Preview on the first: the row and the preview under it turn the teal wash with the teal bar down the left, the button now reads Hide with the crossed eye and the columns do not move, the row's Print is teal and "Print this label" under the label is a plain button; "First order from this customer." (or the history line), the label at actual size in its frame, "Actual size preview: 4 x 4 in (102 x 102 mm)." At 390 each order is a block with the number, the name, the line and the buttons in words: Preview, Edit, Print, then Dispatch, Mark made.

- [ ] **Step 8: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Production Manager: order rows on hairlines, the open order and its label one teal block, Preview and Hide one width, worded buttons on a phone

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 34: Prove the queue and the label did not change

**Files:**
- Create: `$S/reallabels/shoot-mix.js` (scratch, not committed), `$S/reallabels/compare.py` (scratch, not committed)
- Test: `tests/test_frontend.py` (a new guard)

**Interfaces:**
- Consumes: Task 1's baseline captures in `$S/reallabels/baseline`, the sample-order harness `$S/reallabels/build.py` (Reactor's own `run_production_labels` over six fictional To make orders), the rig.
- Produces: `t_the_queue_still_holds_and_does_what_it_did`, which pins the queue's content and actions for every later task; `$S/reallabels/mix/` captures for the gallery (Task 46).

- [ ] **Step 1: Write the guard**

This one pins what Tasks 32 and 33 kept, so it passes as written; Step 2 proves it bites. Append above `if __name__ == "__main__":`:

```python
@test
def t_the_queue_still_holds_and_does_what_it_did():
    """House rule (2026-10-06): the mix changes the look around the Production
    Manager queue, never its content or its actions. The row's cells and chips,
    every button with its title and what it does, the toolbar's items in their
    order, the More menu's items in their order and the preview's wording."""
    fn = fn_src("function renderLabels() {")
    for part in ("orderA(orderNo(o), o.admin_url, 'lbl-num lbl-num-link')", "el('span', 'lbl-name', o.display_name)",
                 "(o.is_company ? 'Company' : 'Customer') + '  ·  '", "el('div', 'lbl-meta', fmtDate(o.created_at))",
                 "'Due ' + (o.due_label || '')", "ageDays(o.created_at) + 'd'", "el('span', 'lbl-chip note', 'Note')",
                 "dsp.canceled ? 'Cancelled' : booked ? 'Booked' : 'Dispatched'", "el('span', 'lbl-chip bad', 'No terms')",
                 "el('span', 'lbl-chip made', 'Made')", "el('span', 'lbl-chip note', 'Printed')"):
        ok(part in fn, "the row still shows: " + part)
    for title, handler in (("'Hide label preview' : 'Preview label'", "labelSel = (labelSel === o.id ? null : o.id); renderLabels();"),
                           ("'Change the delivery address or contact details'", "openOrderEdit(o)"),
                           ("'Preview the proposal proof'", "openProposal(o)"),
                           ("pr.title = 'Print label'", "printLabels([o])"),
                           ("'Remove the Unprocessed tag and add IP, so this order joins To make'", "readyToMake(o, rd)"),
                           ("'View shipment / reprint label' : 'Dispatch a courier for this order'", "openDispatch(o)"),
                           ("'Mark this order as made'", "toggleMade(o)")):
        ok(title in fn and handler in fn, "the row still offers " + title)
    for word in ("'Proof'", "'Print'", "'Ready to make'", "'Shipment' : 'Dispatch'", "'Made' : 'Mark made'", "'Edit'", "'Preview'", "'Hide'"):
        ok(word in fn, "a button still says " + word)
    ok("tableTools([findWrap, filtTabs]," in fn and "[allBtn, slBtn, oldf, sizeSel].filter(Boolean)" in fn
       and "tableSearch('Find order, customer or tracking'" in fn, "the toolbar's items, in their order")
    for t in ("'Print all (' + printable.length + ')'", "'Print shipping labels (' + shipLabels.length + ')'",
              "labelsOldest ? 'Oldest first' : 'Newest first'", "(k === savedSize ? '  (default)' : '')"):
        ok(t in fn, "the toolbar still says " + t)
    menu = fn[fn.index("more.onclick = () => dropMenu(more, ["):]
    at = [menu.index("label: '" + m + "'") for m in ("Size check", "Day sheet", "Dispatch manifest", "Stock usage", "Margins",
                                                       "Size rules", "Update size list", "Shipping settings")]
    ok(at == sorted(at), "More keeps its items in their order")
    for t in ("'Actual size preview: '", "'% so the whole order fits one label.'", "' - some rows would be cut off the printed label. '",
              "'Choose a larger stock size before printing.'", "'Print this label'", "histLine(o)"):
        ok(t in fn, "the preview still says " + t)
```

- [ ] **Step 2: Run it, and prove it bites**

Run: `ONLY=t_the_queue_still python3 tests/test_frontend.py`
Expected: `1 passed, 0 failed`.

Then swap `'Day sheet'` and `'Size check'` in the More menu by hand (do not save the swap to git), run it again and expect `FAIL  t_the_queue_still_holds_and_does_what_it_did: More keeps its items in their order`; undo the swap with `git checkout static/index.html` only if nothing else is uncommitted (else undo by hand) and run it once more: `1 passed, 0 failed`. Then `python3 tests/test_frontend.py 2>&1 | tail -1` prints `454 passed, 0 failed`.

- [ ] **Step 3: The capture script for the mix**

Create `$S/reallabels/shoot-mix.js`:

```js
// The Production Manager after the mix, captured as Task 1's baseline was: the
// To make queue filled with make.json through the page's own renderer.
const S = '/Users/cameron/Desktop/claude/gizmo/.design-rig';
const { chromium } = require(S + '/spacing/node_modules/playwright-core');
const fs = require('fs'), path = require('path');
const TOKEN = fs.readFileSync(path.join(S, 'rigd/long_token.txt'), 'utf8').trim();
const DATA = fs.readFileSync(path.join(__dirname, 'make.json'), 'utf8');
(async () => {
  const r = await fetch('http://127.0.0.1:8920/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + TOKEN }, body: JSON.stringify({ username: 'cameron', password: process.env.RIG_PW || 'test-password-123' }) });
  const ses = (await r.json()).session;
  const b = await chromium.launch({ channel: 'chrome', headless: true });
  for (const [w, h] of [[1440, 900], [390, 844]]) {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 2 });
    await ctx.addInitScript(([t, s]) => { window.shopify = { idToken: async () => t }; localStorage.setItem('sc_app_session', s); }, [TOKEN, ses]);
    await ctx.route(/\/api\/production-labels(\?.*)?$/, route => route.fulfill({ status: 200, contentType: 'application/json', body: DATA }));
    const p = await ctx.newPage();
    await p.goto('http://127.0.0.1:8920/?mix=' + w); await p.waitForSelector('#nav-labels', { state: 'attached' }); await p.waitForTimeout(2000);
    await p.evaluate(() => document.getElementById('nav-labels').click()); await p.waitForTimeout(1500);
    await p.evaluate(() => { const t = [...document.querySelectorAll('#view-labels .qc')].find(x => /To make/.test(x.textContent)); t && t.click(); });
    await p.waitForTimeout(2000);
    await p.screenshot({ path: `queue-${w}.png`, fullPage: false });
    const opened = await p.evaluate(() => { const btn = document.querySelector('#view-labels button[title="Preview label"]'); if (btn) { btn.click(); return true; } return false; });
    await p.waitForTimeout(1500);
    await p.screenshot({ path: `preview-${w}.png`, fullPage: false });
    const lab = await p.$('.label-sheet');
    if (lab) await lab.screenshot({ path: `label-${w}.png` });
    const facts = await p.evaluate(() => ({
      counters: [...document.querySelectorAll('#view-labels .qc')].map(e => e.textContent.trim()),
      tabs: [...document.querySelectorAll('#view-labels .qt')].map(e => e.textContent.trim()),
      toolbar: [...document.querySelectorAll('#view-labels .tbl-tools :is(input, button, select)')].map(e => e.placeholder || e.getAttribute('aria-label') || e.textContent.trim()),
      rowButtons: [...document.querySelectorAll('#view-labels .lbl-qrow')].map(r => r.querySelectorAll('.lbl-actions button').length),
      note: (document.querySelector('.lbl-preview-note') || {}).textContent,
      primary: [...document.querySelectorAll('#view-labels .btn-primary')].map(e => e.textContent.trim()),
    }));
    console.log(w, 'preview opened', opened, 'label el', !!lab, JSON.stringify(facts));
    await ctx.close();
  }
  await b.close();
})();
```

and `$S/reallabels/compare.py`:

```python
"""The label as the bench sees it, before and after the mix: pixel for pixel,
less a 16px margin where the label's rounded corner shows what is behind it."""
import sys
from PIL import Image, ImageChops
S = "/Users/cameron/Desktop/claude/gizmo/.design-rig"
bad = 0
for w in (1440, 390):
    a = Image.open(f"{S}/reallabels/baseline/label-{w}.png").convert("RGB")
    b = Image.open(f"{S}/reallabels/mix/label-{w}.png").convert("RGB")
    if a.size != b.size:
        print(w, "SIZE", a.size, b.size); bad += 1; continue
    box = (16, 16, a.size[0] - 16, a.size[1] - 16)
    d = ImageChops.difference(a.crop(box), b.crop(box)).getbbox()
    print(w, "identical" if d is None else "DIFFERS in %s" % (d,))
    bad += d is not None
sys.exit(1 if bad else 0)
```

- [ ] **Step 4: Capture the mix and compare**

With the rig running:

```bash
S=/Users/cameron/Desktop/claude/gizmo/.design-rig
python3 "$S/reallabels/build.py"
mkdir -p "$S/reallabels/mix" && cd "$S/reallabels/mix" && node ../shoot-mix.js
python3 "$S/reallabels/compare.py"
```

Expected: `6 orders` and the six order lines from build.py (unchanged from Task 1's run); for 1440 and 390 `preview opened true label el true` with counters `["To make6"]`-style text for Unprocessed 0, To make 6, To ship 0, tabs `Complete` and `Custom shipments`, the toolbar `Find order, customer or tracking`, `All6`, `Unprinted6`, `Not made6`, `Print all (6)`, `Newest first` and the size select, six rows of five buttons each, the note starting `Actual size preview: 4 x 4 in`, and `primary` holding only `Print` at 1440 (the open row's); then `1440 identical` and `390 identical`. A difference inside the label means something that prints moved: find it with `git diff 9a8c442 -- static/index.html | grep -n "label-sheet\|labelSheet\|fitLabel"` and undo it.

- [ ] **Step 5: Look at the pair**

Open `$S/reallabels/baseline/preview-1440.png` beside `$S/reallabels/mix/preview-1440.png`, and the 390 pair: the same six orders, the same buttons in the same order, the same label; only the page around them is the mix.

- [ ] **Step 6: Commit**

```bash
git add tests/test_frontend.py
git commit -m "Production Manager: a guard that the queue still holds and does what it did, row by row, button by button

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Phase 5: The remaining screens, by pattern

Each task moves one pattern's screens (spec 8.3) onto the shared parts and cuts their words per the copy plan, quoting every old string exactly. The replacements live in a pairs file each task writes to `$S/copy/` and applies with Task 35's `apply.py`, which refuses to write anything unless every old string is found exactly as often as it says. Where the copy plan and the spec disagree, the spec wins (its section 7 table): no page keeps a line once a report has run, and the Production Manager's inline preview wording does not change.


### Task 35: The report pages: Overview and SEO, the Summary section, and help that a tap reaches

**Files:**
- Create: `$S/copy/apply.py` and `$S/copy/t35.py` (scratch, not committed)
- Modify: `static/index.html` `followedNote` (7559), `chartHead` (7867), `statCard` (5933), `renderPageThread` (9017), `renderTrendsBlock` and `renderSeoTrends` (8350-8440), the run gates (9200-9214), `runOverview` (9218), `renderOverview` (9343), the alerts banner (9269), `runSEO` (9421), `renderSEO` (9438), the stylesheet (`.has-help` 1189-1197, `.ov-hero .followed` 4449, after `.followed-link` 4448)
- Test: `tests/test_frontend.py` (`t_a_paid_report_run_is_one_run_and_stays_on_screen` 7690, a new test)

**Interfaces:**
- Consumes: `pageHead` (Task 7), `infoButton` (Task 12), `emptyState` (Task 18), `widget(node, id, size, label)` (6305), `guideAdmin()` (21918), `openSettings()` (30005).
- Produces: `summarySection(text, followed)` returns the report's Summary section (`section.ai-summary.widget-bare`, its head, the summary at the reading measure and the skills it followed) or `null`; `followedNote(s)` is a small row, "Followed: Brand voice, Trade enquiries"; a chart takes `help` (its title's info button) and its source line no longer starts "Source:"; `POSITION_HELP`; `$S/copy/apply.py <pairs file> [target]` applies a task's exact replacements, each found exactly as often as it says, or writes nothing (Tasks 36 to 44 use it).

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_the_report_pages_wear_the_mix():
    """Spec 8.3 (Report) and the copy plan (Overview, SEO, shared report parts):
    the header is the one builder with its live line and Refresh all; the AI
    summary is a Summary section of its own with the skills it followed as a
    small row; a figure's and a chart's explanation is an info button; the run
    gate says what the report is and what it costs in a few words."""
    for fname, view in (("function renderOverview(cache) {", "overview"), ("function renderSEO(cache) {", "seo")):
        fn = fn_src(fname)
        ok("pageHead({ view: '" + view + "'" in fn and "live: cache.at" in fn and "summarySection(" in fn,
           view + ": the one header, and the Summary section")
        ok("el('div', 'ov-hero')" not in fn and "'badge'" not in fn, view + ": no header built by hand")
    ok("function summarySection(text, followed) {" in SCRIPT, "one Summary builder")
    ok("labelEl.append(infoButton(m.label, { title: m.label, body: help }))" in fn_src("function statCard(m, i) {"),
       "a figure's help is an info button")
    ok("if (opts.help) ct.append(infoButton(" in fn_src("function chartHead(opts, series, kind) {"), "and so is a chart's")
    ok("const POSITION_HELP = 'Lower is better. Position 1 is the top of search results.';" in SCRIPT
       and SCRIPT.count("Lower is better. Position 1") == 1, "said once, for both position charts")
    ok("has-help" not in SCRIPT + CSS, "no help is left that only a pointer can reach")
    for gone in ("Here’s how your store is doing.", "Ask anything about the numbers and recommendations on this page.",
                 "Trends populate after you run", "notable change", "whatever the range above", "optimisation health score",
                 "Followed your skill", "'Source: ' + opts.source", "Compute live KPIs", "Crawl your storefront and fuse"):
        ok(gone not in SCRIPT, "cut: " + gone)
    for new in ("'Live figures and an AI summary of the store.'", "'Crawl the store and rank fixes by revenue.'",
                "'Uses AI credits. Takes up to a minute.'", "'No trends yet. Connect Google to add traffic.'",
                "'Connect Search Console to see search trends.'", "'Suggested questions'", "'Followed: '"):
        ok(new in SCRIPT, "says: " + new)
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_the_report_pages_wear_ python3 tests/test_frontend.py`
Expected: `FAIL  t_the_report_pages_wear_the_mix: overview: the one header, and the Summary`

- [ ] **Step 3: The applier every screen task uses**

Create `$S/copy/apply.py`:

```python
"""Apply one task's exact text replacements to a file. Each PAIRS entry is
(old, new, times): old must be found exactly that many times, after the
entries before it have been applied, or nothing is written at all.
python3 apply.py <pairs.py> [file, default static/index.html]"""
import importlib.util, sys
spec = importlib.util.spec_from_file_location("pairs", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
target = sys.argv[2] if len(sys.argv) > 2 else "static/index.html"
src = open(target, encoding="utf-8").read()
for i, (old, new, times) in enumerate(m.PAIRS):
    found = src.count(old)
    if found != times:
        sys.exit("pair %d: found %d times, expected %d: %r" % (i, found, times, old[:160]))
    src = src.replace(old, new)
open(target, "w", encoding="utf-8").write(src)
print("applied %d replacements to %s" % (len(m.PAIRS), target))
```

- [ ] **Step 4: The headers and the words**

Create `$S/copy/t35.py` with the content below, then run `python3 "$S/copy/apply.py" "$S/copy/t35.py"` from the repo; expect `applied 19 replacements to static/index.html`.

```python
PAIRS = [
# --- shared report parts ---
("""        function followedNote(s) {
            const names = (s && Array.isArray(s.skills_applied)) ? s.skills_applied.filter(Boolean) : [];
            if (!names.length) return null;
            const p = el('p', 'followed');
            p.append(ico(I.book), document.createTextNode(names.length === 1 ? 'Followed your skill ' : 'Followed your skills '));
            names.forEach((n, k) => {
                const a = tabAllowed('skills') ? actionLink('followed-link', n) : el('span', 'followed-name', n);
                if (tabAllowed('skills')) a.onclick = () => setView('skills');
                if (k) p.append(document.createTextNode(k === names.length - 1 ? ' and ' : ', '));
                p.append(a);
            });
            return p;
        }""",
"""        function followedNote(s) {
            const names = (s && Array.isArray(s.skills_applied)) ? s.skills_applied.filter(Boolean) : [];
            if (!names.length) return null;
            /* A small row, not a sentence (copy plan, shared #3). */
            const p = el('p', 'followed');
            p.append(ico(I.book), document.createTextNode('Followed: '));
            names.forEach((n, k) => {
                const a = tabAllowed('skills') ? actionLink('followed-link', n) : el('span', 'followed-name', n);
                if (tabAllowed('skills')) a.onclick = () => setView('skills');
                if (k) p.append(document.createTextNode(', '));
                p.append(a);
            });
            return p;
        }
        /* The AI summary (the mix, spec 8.3): a section of its own at the top
           of a report, out of the header, with the skills it followed under it.
           Nothing when the run gave neither. */
        function summarySection(text, followed) {
            if (!text && !followed) return null;
            const sec = el('section', 'ai-summary widget-bare');
            sec.append(el('div', 'section-title', 'Summary'));
            if (text) sec.append(el('p', 'ai-summary-text', text));
            if (followed) sec.append(followed);
            return sec;
        }""", 1),
("""            if (opts.title) htxt.append(el('div', 'ct', opts.title));""",
"""            /* A chart's explanation is an info button beside its title (the
               mix, spec 7), not a line under the plot. */
            if (opts.title) {
                const ct = el('div', 'ct', opts.title);
                if (opts.help) ct.append(infoButton(opts.title, { title: opts.title, body: opts.help }));
                htxt.append(ct);
            }""", 1),
("""                cs.append(document.createTextNode('Source: ' + opts.source + (opts.period ? ' \\u00b7' : '')));""",
"""                cs.append(document.createTextNode(opts.source + (opts.period ? ' \\u00b7' : '')));""", 1),
("""                if (sugg.length) { thread.append(el('div', 'pchat-hint', 'Suggested questions from this report')); thread.append(followupChips(sugg, q => pageAsk(page, q, data))); }
                else thread.append(el('div', 'pchat-hint', 'Ask anything about the numbers and recommendations on this page.'));""",
"""                if (sugg.length) { thread.append(el('div', 'pchat-hint', 'Suggested questions')); thread.append(followupChips(sugg, q => pageAsk(page, q, data))); }""", 1),
("""            if (help) { labelEl.title = help; labelEl.classList.add('has-help'); labelEl.tabIndex = 0; }""",
"""            /* Its explanation is an info button beside it (the mix, spec 7): a
               tap and the keyboard open it as well as a pointer. */
            if (help) labelEl.append(infoButton(m.label, { title: m.label, body: help }));""", 1),
# --- the position charts: one sentence, said once, behind the info button ---
("""        function renderTrendsBlock(box, trends, currency, range, onRange, intro, id) {""",
"""        /* Said once for both position charts (copy plan, pattern 15). */
        const POSITION_HELP = 'Lower is better. Position 1 is the top of search results.';
        function renderTrendsBlock(box, trends, currency, range, onRange, intro, id) {""", 1),
("""note: 'Lower is better. Position 1 is the top of search results.' }""", """help: POSITION_HELP }""", 2),
("""period: rangeLabel(span) + ', whatever the range above',""", """period: rangeLabel(span),""", 1),
# --- Overview ---
("""desc: 'Compute live KPIs and an AI executive summary from your latest orders, customers and traffic.'""",
 """desc: 'Live figures and an AI summary of the store.'""", 1),
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.grid;
            /* The page's own line from the start, so the header is the same
               height loading, failed or loaded and nothing below it jumps. */
            const htext = el('div'); htext.append(el('h2', null, 'Overview'), el('p', null, 'Here’s how your store is doing.'));
            hero.append(badge, htext); box.append(hero);""",
"""            /* The header alone while it runs: the loader says what is happening. */
            const hero = pageHead({ view: 'overview', title: 'Overview' }); box.append(hero);""", 1),
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.grid;
            const htext = el('div'); htext.append(el('h2', null, 'Overview'), el('p', null, data.structured && data.structured.summary ? data.structured.summary : 'Here’s how your store is doing.'));
            { const f = followedNote(data.structured); if (f) htext.append(f); }
            hero.append(badge, htext);
            hero.append(heroAct(freshLabel(cache.at), refreshBtn(() => loadOverview(true)), refreshAllBtn()));
            box.append(hero);""",
"""            box.append(pageHead({ view: 'overview', title: 'Overview', live: cache.at, onRefresh: () => loadOverview(true),
                actions: [refreshAllBtn()] }));
            /* The AI summary is the page's first section (the mix, spec 8.3). */
            { const sum = summarySection(data.structured && data.structured.summary, followedNote(data.structured));
              if (sum) box.append(widget(sum, 'summary', 'full', 'Summary')); }""", 1),
("""' notable change' + (fresh.length > 1 ? 's' : '') + ' since the last scheduled refresh'""",
 """' change' + (fresh.length > 1 ? 's' : '') + ' since the last refresh'""", 1),
("""                box.append(widget(cardSection('Sales by sector',
                    'Revenue, orders and average order value by the sector each customer trades in.',
                    sectorSalesTable(data.sector_sales, data.currency)), 'sectors'));""",
"""                box.append(widget(cardSection('Sales by sector', null,
                    sectorSalesTable(data.sector_sales, data.currency)), 'sectors'));""", 1),
("""                if (bare) { host.append(el('div', 'empty', 'Trends populate after you run the overview, as orders accrue and Google is connected. Up to 24 months of history are shown here.')); return; }""",
"""                if (bare) {
                    /* One line and the way on (copy plan, Overview #6). */
                    let go = null;
                    if (guideAdmin()) { go = el('button', 'btn'); go.type = 'button'; go.append(ico(I.settings), document.createTextNode('Connect Google')); go.onclick = openSettings; }
                    host.append(emptyState({ icon: I.trendUp, text: 'No trends yet. Connect Google to add traffic.', action: go }));
                    return;
                }""", 1),
# --- SEO ---
("""desc: 'Crawl your storefront and fuse Search Console, Analytics and Shopify sales into a money-ranked plan.', cta: 'Run SEO audit', note: 'Uses AI credits only when you run it. Can take up to a minute.'""",
 """desc: 'Crawl the store and rank fixes by revenue.', cta: 'Run SEO audit', note: 'Uses AI credits. Takes up to a minute.'""", 1),
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.search;
            const htext = el('div'); htext.append(el('h2', null, 'SEO'),
                el('p', null, 'How your store performs across search, traffic and sales, and where to grow revenue.'));
            hero.append(badge, htext); box.append(hero);""",
"""            const hero = pageHead({ view: 'seo', title: 'SEO' }); box.append(hero);""", 1),
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.search;
            const htext = el('div'); htext.append(el('h2', null, 'SEO'),
                el('p', null, s.summary || 'How your store performs across search, traffic and sales, and where to grow revenue.'));
            { const f = followedNote(s); if (f) htext.append(f); }
            hero.append(badge, htext);
            hero.append(heroAct(freshLabel(cache.at), refreshBtn(() => loadSEO(true)), refreshAllBtn()));
            box.append(hero);""",
"""            box.append(pageHead({ view: 'seo', title: 'SEO', live: cache.at, onRefresh: () => loadSEO(true), actions: [refreshAllBtn()] }));
            { const sum = summarySection(s.summary, followedNote(s)); if (sum) box.append(widget(sum, 'summary', 'full', 'Summary')); }""", 1),
("""scored ? 'out of 100, optimisation health score' : data.score_note""", """scored ? 'out of 100' : data.score_note""", 1),
("""                if (bare) { host.append(el('div', 'empty', 'Connect Google Search Console to chart search trends. Google provides up to 16 months of history.')); return; }""",
"""                if (bare) { host.append(el('div', 'empty', 'Connect Search Console to see search trends.')); return; }""", 1),
]
```

- [ ] **Step 5: The rules**

Delete every rule whose selector names `.has-help` (four: `.has-help`, `.has-help:hover, .has-help:focus-visible`, `.stat .label.has-help` and its `:hover, :focus-visible` pair, wherever Task 22 left the hover halves) and the comment above the first (`/* Anywhere a word needs a sentence behind it: a dotted underline that`). Then `grep -c "has-help" static/index.html` prints `0`.

Delete `        .ov-hero .followed { margin-top: var(--sp-2); }` (the row lives in the Summary section now).

After the rule that begins `        .followed-link {` add:

```css
        /* The AI summary, a section of its own (the mix, spec 8.3): body copy at
           the reading measure, the skills it followed 8 under it. */
        .ai-summary-text { margin: 0; color: var(--text-secondary); max-width: var(--measure); }
        .ai-summary .followed { margin-top: var(--sp-2); }
        /* An info button inside a title that is not a flex row sits 8 from its
           words and centred on the line, as it does in one. */
        :is(.card-title, .stat .label, .chart-head .ct, .cx-tile-title, .disp-subhead, .modal-head h3) > .info {
            vertical-align: middle; margin-left: calc(var(--sp-2) + (var(--icon-md) - var(--control-h-sm)) / 2); }
```

- [ ] **Step 6: The run harness meets pageHead**

`runOverview` now draws its header with `pageHead`, which the node harness in `t_a_paid_report_run_is_one_run_and_stays_on_screen` does not load. Give it a stand-in that draws the title, which is all the harness reads. In that test replace:

```python
const I = {}; function loader() { return el('span'); }
const reportRuns = {};
```

with:

```python
const I = {}; function loader() { return el('span'); }
function pageHead(o) { const h = el('div', 'ov-hero'); h.append(el('h2', null, o.title || '')); return h; }
const reportRuns = {};
```

- [ ] **Step 7: Run the tests**

Run: `ONLY=t_the_report_pages_wear_ python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `455 passed, 0 failed`.

- [ ] **Step 8: Look at it, and audit it**

Overview and SEO in the rig, before a run and after: before, the header and its one line, then the tile, "Uses AI credits only when you run it." (Overview) or "Uses AI credits. Takes up to a minute." (SEO) and Run. After a run, the header with the green dot, "Updated just now", Refresh and Refresh all, then a Summary section with the AI summary and "Followed: ..." under it when the run followed skills; each figure's info button opens its help; the Average Google position chart's info button says "Lower is better. Position 1 is the top of search results."; chart source lines read "Shopify orders · last 12 months". With Google unconnected, Performance over time shows the tile, "No trends yet. Connect Google to add traffic." and, for an admin, Connect Google.

Then, with the rig running:

```bash
S=/Users/cameron/Desktop/claude/gizmo/.design-rig
SIZES=1440x900,390x844 VIEWS=overview,seo SHOTS=0 node "$S/spacing/audit.js" "$S/spacing/t35" && python3 "$S/spacing/analyse.py" "$S/spacing/t35" | grep -E "^## (Script errors|Page wider|overlaps|escapes|clipped)"
```

Expected: `## Script errors: 0`, no page wider than the screen, and `0 hits` for overlaps, escapes and clipped on these screens.

- [ ] **Step 9: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Reports: Overview and SEO on the one header, the AI summary as its own section, and every figure's and chart's help behind an info button

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---


### Task 36: Keywords, Products and Customers

**Files:**
- Create: `$S/copy/t36.py` (scratch, not committed)
- Modify: `static/index.html` `showKeywordsView` (9497), `runKeywords` (9510), `renderCPC` (9544), `keywordScanCard` (9602), `renderKeywords` (9630-9680), `customerGate` (9718), `customersBusy` (9843), `renderCustomers` (9907), the trade radar (9780-9830), `showProductsView` (9210), `loadProducts` (10028), `renderProductList` (10147-10262), `openProduct` (10294), `renderProductDetail` (10313)
- Test: `tests/test_frontend.py` (`t_the_products_page_searches_everything_and_draws_a_bounded_list` 7303, `t_a_search_does_not_take_customise_away` 8484, `t_a_paid_report_run_is_one_run_and_stays_on_screen` 7690, `t_a_late_product_plan_does_not_replace_the_one_on_screen` 7812, a new test)

**Interfaces:**
- Consumes: `pageHead`, `infoButton`, `emptyState`, `summarySection` and `followedNote` (Task 35), `$S/copy/apply.py` (Task 35).
- Produces: `customerGateHead(seg)` returns the Customers run gate's header; `customerGate(seg)` returns its empty state (`.run-gate`). Nothing else new.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_keywords_products_and_customers_wear_the_mix():
    """Spec 8.3 (Report) and the copy plan (Keywords, Products, Customers): one
    header builder on every state, the AI summary as a section, setup steps and
    definitions behind info buttons, the Customers run gate the same empty state
    every report's is, and the shorter lines."""
    for fname in ("function renderKeywords(cache) {", "async function runKeywords(box) {", "function renderProductList() {",
                  "async function loadProducts(force) {", "async function openProduct(id, title) {",
                  "function renderProductDetail(d, id, title) {", "function customersBusy(seg) {", "function renderCustomers(seg) {"):
        fn = fn_src(fname)
        ok("pageHead({" in fn or "customerGateHead(seg)" in fn, fname + ": the one header")
        ok("el('div', 'ov-hero')" not in fn, fname + ": none built by hand")
    gate = fn_src("function customerGate(seg) {")
    ok("emptyState({ icon: I.users, text: 'Uses AI credits. Reads Shopify customers and orders.', action: btn, cls: 'run-gate' })" in gate,
       "the Customers gate is the run gate's empty state")
    ok("'rg-ic'" not in SCRIPT and "'rg-note'" not in SCRIPT, "no run gate draws its own tile or note")
    ok("infoButton('The two Google sources'" in SCRIPT and "infoButton('Linking Google Ads'" in SCRIPT, "the Google steps wait behind info buttons")
    ok("inp.placeholder = 'A competitor or blog post address'" in SCRIPT, "what to scan is the field's own hint")
    for gone in ("Pull the keywords you rank for", "Paste any public page", "Two Google sources fill", "No paid search data yet. Link",
                 "Load your catalogue with up to", "Pulls live Shopify data. No AI", "Filter, sort and compare your catalogue",
                 "The plan for this product.", "that earned most, ", "Analyse all customers", "From your orders and customer list",
                 "Who your best customers are", "Nobody with a reorder rhythm"):
        ok(gone not in SCRIPT, "cut: " + gone)
    for new in ("'Your keywords and ad spend, with a ranked plan.'", "'Your catalogue with up to 24 months of sales.'",
                "'Open a product for its optimisation plan.'", "'Nothing to rank for this period.'",
                "'Customers and sectors by retention, value and revenue.'", "'No repeat accounts overdue.'",
                "'Tag these in Shopify to count them as trade.'", "' Some products are missing: the catalogue is too large.'"):
        ok(new in SCRIPT, "says: " + new)
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_keywords_products_and_ python3 tests/test_frontend.py`
Expected: `FAIL  t_keywords_products_and_customers_wear_the_mix: function renderKeywords(cache) {: the one header`

- [ ] **Step 3: The headers and the words**

Create `$S/copy/t36.py` with the content below, then run `python3 "$S/copy/apply.py" "$S/copy/t36.py"` from the repo; expect `applied 25 replacements to static/index.html`.

```python
PAIRS = [
# --- Keywords ---
("""                desc: 'Pull the keywords you rank for from Search Console and your paid spend, CPC and ROAS from Google Ads (via GA4), then get a money-ranked plan. You can also scan any public URL for the keywords it targets.',
                cta: 'Run keyword analysis', note: 'Uses AI credits only when you run it. Reads Search Console and GA4.',""",
"""                desc: 'Your keywords and ad spend, with a ranked plan.',
                cta: 'Run keyword analysis', note: 'Uses AI credits. Reads Search Console and Analytics.',""", 1),
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.tag;
            const ht = el('div'); ht.append(el('h2', null, 'Keywords'),
                el('p', null, 'Your ranking keywords, paid performance, and where to win more profitable search traffic.'));
            hero.append(badge, ht); box.append(hero);""",
"""            const hero = pageHead({ view: 'keywords', title: 'Keywords' }); box.append(hero);""", 1),
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.tag;
            const ht = el('div'); ht.append(el('h2', null, 'Keywords'),
                el('p', null, s.summary || 'Your ranking keywords, paid performance, and where to win more profitable search traffic.'));
            { const f = followedNote(s); if (f) ht.append(f); }
            hero.append(badge, ht);
            hero.append(heroAct(freshLabel(cache.at), refreshBtn(() => loadKeywords(true)), refreshAllBtn()));
            box.append(hero);""",
"""            box.append(pageHead({ view: 'keywords', title: 'Keywords', live: cache.at, onRefresh: () => loadKeywords(true), actions: [refreshAllBtn()] }));
            { const sum = summarySection(s.summary, followedNote(s)); if (sum) box.append(widget(sum, 'summary', 'full', 'Summary')); }""", 1),
("""                return el('div', 'empty', 'No paid search data yet. Link Google Ads to your GA4 property (GA4 Admin, then Product links, then Google Ads links), and your spend, CPC, conversions and ROAS will appear here.');""",
"""                return el('div', 'empty', 'No paid search data yet.');""", 1),
("""            head.append(el('p', 'card-desc', 'Paste any public page (a competitor, a blog post) to extract the keywords and topics it targets, with ideas to compete.'));
            card.append(head);
            const row = el('div', 'act-row');
            const inp = el('input', 'scan-url'); inp.placeholder = 'https://example.com/page'; inp.type = 'url';""",
"""            card.append(head);
            const row = el('div', 'act-row');
            /* What to paste is the field's own hint (copy plan, Keywords #4). */
            const inp = el('input', 'scan-url'); inp.placeholder = 'A competitor or blog post address'; inp.type = 'url';
            inp.setAttribute('aria-label', 'A competitor or blog post address');""", 1),
("""                nh.append(el('h3', 'card-title', 'Search data is not connected yet'));
                nh.append(el('p', 'card-desc', 'Two Google sources fill the rest of this page.'));
                const na = el('div', 'card-act');
                const go = el('button', 'btn btn-sm'); go.append(ico(I.settings), document.createTextNode('Open connections'));
                go.onclick = () => openSettings(); na.append(go); nh.append(na);
                n.append(nh);
                const ul = el('ul', 'setup-steps');
                ul.append(el('li', null, 'Google Search Console, for the keywords you rank for and the clicks they bring.'));
                ul.append(el('li', null, 'Google Ads, linked to your GA4 property (GA4 Admin, then Product links, then Google Ads links), '
                    + 'for your spend, cost per click, conversions and ROAS.'));
                n.append(ul);""",
"""                /* The two sources, word for word, behind the title's info button
                   (the mix, spec 8.3: setup steps wait there, with the action). */
                const ul = el('ol', 'setup-steps');
                ul.append(el('li', null, 'Google Search Console, for the keywords you rank for and the clicks they bring.'));
                ul.append(el('li', null, 'Google Ads, linked to your GA4 property (GA4 Admin, then Product links, then Google Ads links), '
                    + 'for your spend, cost per click, conversions and ROAS.'));
                const nt = el('h3', 'card-title', 'Search data is not connected yet');
                nt.append(infoButton('The two Google sources', { title: 'Search data', body: [ul] }));
                nh.append(nt);
                const na = el('div', 'card-act');
                const go = el('button', 'btn btn-sm'); go.append(ico(I.settings), document.createTextNode('Open connections'));
                go.onclick = () => openSettings(); na.append(go); nh.append(na);
                n.append(nh);""", 1),
("""                    : el('div', 'empty', data.gsc_connected ? 'No Search Console queries in this range yet.' : 'Connect Google Search Console to see the keywords you rank for.'));""",
"""                    : el('div', 'empty', data.gsc_connected ? 'No Search Console queries in this range yet.' : 'Connect Search Console to see your keywords.'));""", 1),
("""                paid.append(el('div', 'section-title', 'Paid search (cost per click)'), renderCPC(data.ads, cur));""",
"""                const paidHead = el('div', 'section-title', 'Paid search (cost per click)');
                /* How to link Google Ads, word for word, behind the title's info
                   button while there is nothing to show (copy plan, Keywords #8). */
                if (noAds) paidHead.append(infoButton('Linking Google Ads', { title: 'Paid search',
                    body: 'Link Google Ads to your GA4 property (GA4 Admin, then Product links, then Google Ads links), and your spend, CPC, conversions and ROAS will appear here.' }));
                paid.append(paidHead, renderCPC(data.ads, cur));""", 1),
# --- Products ---
("""desc: 'Load your catalogue with up to 24 months of sales so you can filter, sort, compare periods and export.', cta: 'Load products', note: 'Pulls live Shopify data. No AI credits used.'""",
 """desc: 'Your catalogue with up to 24 months of sales.', cta: 'Load products', note: 'Pulls live Shopify data.'""", 1),
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.box;
            const ht = el('div'); ht.append(el('h2', null, 'Products'));
            hero.append(badge, ht); box.append(hero);""",
"""            const hero = pageHead({ view: 'products', title: 'Products' }); box.append(hero);""", 1),
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.box;
            const ht = el('div'); ht.append(el('h2', null, 'Products'),
                el('p', null, 'Filter, sort and compare your catalogue by revenue, sales, stock and more. Open a product for a full optimisation plan.'));
            hero.append(badge, ht);
            hero.append(heroAct(productListAt ? freshLabel(productListAt) : '', refreshBtn(() => loadProducts(true))));
            box.append(hero);""",
"""            /* The page's one line, with Refresh among its actions. */
            box.append(pageHead({ view: 'products', title: 'Products', line: 'Open a product for its optimisation plan.',
                actions: [refreshBtn(() => loadProducts(true), 'Refresh products')] }));""", 1),
("""                foot.append(el('div', 'tbl-count', 'Viewing ' + rows.length + ' of ' + all + ' product' + (all === 1 ? '' : 's')
                    + (rows.length > P_ROWS_MAX ? '. The first ' + P_ROWS_MAX + ' are drawn: search or filter to reach the rest' : '')
                    + (productList && productList.truncated ? '. The catalogue is larger than one read carries, so some products are not listed' : '')));""",
"""                foot.append(el('div', 'tbl-count', (rows.length > P_ROWS_MAX
                        ? 'Showing ' + P_ROWS_MAX + ' of ' + rows.length + '. Search or filter for more.'
                        : 'Showing ' + rows.length + ' of ' + all + ' product' + (all === 1 ? '' : 's'))
                    + (productList && productList.truncated ? ' Some products are missing: the catalogue is too large.' : '')));""", 1),
("""                    const nWords = ['', 'one', 'two', 'three', 'four', 'five', 'six'];
                    th2.append(el('h3', 'card-title', 'Top products by revenue'), el('p', 'card-desc', top.length > 1
                        ? 'The ' + (nWords[top.length] || top.length) + ' that earned most, ' + pPeriodLabel() + '.'
                        : 'Fewer than two of these products earned anything (' + pPeriodLabel() + '), so there is nothing to rank.'));""",
"""                    th2.append(el('h3', 'card-title', 'Top products by revenue'));
                    /* The title and the period chooser say what it is; only an
                       empty ranking says why (copy plan, Products #4 and #5). */
                    if (top.length < 2) th2.append(el('p', 'card-desc', 'Nothing to rank for this period.'));""", 1),
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.box;
            const ht = el('div'); ht.append(el('h2', null, title || 'Product'));
            hero.append(badge, ht); box.append(hero);""",
"""            box.append(pageHead({ view: 'products', title: title || 'Product' }));""", 1),
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.box;
            const ht = el('div'); ht.append(el('h2', null, (d.product && d.product.title) || 'Product'),
                el('p', null, s.summary || 'The plan for this product.'));
            hero.append(badge, ht);""",
"""            /* The plan's header, then its summary as a section of its own (the
               mix, spec 8.3). */""", 1),
("""            if (pid) hero.append(heroAct(freshLabel(Date.now()), refreshBtn(() => openProduct(pid, ptitle))));
            box.append(hero);""",
"""            box.append(pageHead({ view: 'products', title: ptitle || 'Product', live: pid ? Date.now() : null,
                onRefresh: pid ? () => openProduct(pid, ptitle) : null }));
            { const sum = summarySection(s.summary, null); if (sum) box.append(sum); }""", 1),
# --- Customers ---
("""        function customerGate(seg) {
            const comp = seg === SEG_ALL;
            const card = el('div', 'run-gate');
            const ic = el('div', 'rg-ic'); ic.innerHTML = I.users; card.append(ic);
            card.append(el('h2', null, comp ? 'Customers' : (seg + ' sector')),
                el('p', null, comp
                    ? 'Analyse all customers and compare your sectors by retention, lifetime value and revenue, with a money-ranked plan.'
                    : ('Analyse the ' + seg + ' sector on its own: retention, lifetime value, segments, and a money-ranked plan for these customers.')));
            const btn = el('button', 'btn btn-primary rg-btn'); btn.textContent = comp ? 'Run comprehensive audit' : ('Run ' + seg + ' audit'); btn.onclick = () => loadCustomers(true, seg);
            card.append(btn);
            card.append(el('div', 'rg-note', 'Uses AI credits only when you run it. Reads your Shopify customers and orders.'));
            return card;
        }""",
"""        /* The Customers run gate: the page's header and line, then the empty
           state every run gate is (renderRunGate), with the sector bar between. */
        function customerGateHead(seg) {
            const comp = seg === SEG_ALL;
            return pageHead({ view: 'customers', title: comp ? 'Customers' : (seg + ' sector'), line: comp
                ? 'Customers and sectors by retention, value and revenue.'
                : ('The ' + seg + ' sector on its own, with a ranked plan.') });
        }
        function customerGate(seg) {
            const comp = seg === SEG_ALL;
            const btn = el('button', 'btn btn-primary'); btn.type = 'button';
            btn.textContent = comp ? 'Run comprehensive audit' : ('Run ' + seg + ' audit'); btn.onclick = () => loadCustomers(true, seg);
            return emptyState({ icon: I.users, text: 'Uses AI credits. Reads Shopify customers and orders.', action: btn, cls: 'run-gate' });
        }""", 1),
("""            if (!cached) { box.append(sectorBar(), customerGate(seg), rslot); paintRadar(); return; }""",
"""            if (!cached) { box.append(customerGateHead(seg), sectorBar(), customerGate(seg), rslot); paintRadar(); return; }""", 1),
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.users;
            const ht = el('div'); ht.append(el('h2', null, comp ? 'Customers' : (seg + ' sector')),
                el('p', null, comp ? 'Who your best customers are, how well you retain them, and where to grow lifetime value.' : ('Retention and lifetime value for your ' + seg + ' customers.')));
            hero.append(badge, ht); box.append(hero);""",
"""            const hero = pageHead({ view: 'customers', title: comp ? 'Customers' : (seg + ' sector') }); box.append(hero);
            const ht = hero;""", 1),
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.users;
            const ht = el('div'); ht.append(el('h2', null, comp ? 'Customers' : (seg + ' sector')),
                el('p', null, s.summary || (comp ? 'Who your best customers are, how well you retain them, and where to grow lifetime value.' : ('Retention and lifetime value for your ' + seg + ' customers.'))));
            { const f = followedNote(s); if (f) ht.append(f); }
            hero.append(badge, ht);
            hero.append(heroAct(freshLabel(cached.at), refreshBtn(() => loadCustomers(true)), refreshAllBtn()));""",
"""            const hero = pageHead({ view: 'customers', title: comp ? 'Customers' : (seg + ' sector'), live: cached.at,
                onRefresh: () => loadCustomers(true), actions: [refreshAllBtn()] });""", 1),
("""            box.append(hero, sectorBar());
            { const cs = changesStrip(data.changes, data.changes_since); if (cs) box.append(cs); }""",
"""            box.append(hero, sectorBar());
            { const cs = changesStrip(data.changes, data.changes_since); if (cs) box.append(cs); }
            { const sum = summarySection(s.summary, followedNote(s)); if (sum) box.append(widget(sum, 'summary', 'full', 'Summary')); }""", 1),
("""            head.append(el('h3', 'card-title', 'Trade radar'));
            head.append(el('p', 'card-desc', 'From your orders and customer list. No AI credits used.'));""",
"""            head.append(el('h3', 'card-title', 'Trade radar'));""", 1),
("""'Nobody with a reorder rhythm is overdue right now.'""", """'No repeat accounts overdue.'""", 1),
("""'Every likely-trade customer already carries a sector tag.'""", """'Every trade customer is tagged.'""", 1),
("""'Tag these in Shopify and the sector analytics will see the whole trade side.'""", """'Tag these in Shopify to count them as trade.'""", 1),
]
```


- [ ] **Step 4: Update the guards that pinned the old words**

In `t_the_products_page_searches_everything_and_draws_a_bounded_list` replace:

```python
    ok("rows.length > P_ROWS_MAX ? '. The first ' + P_ROWS_MAX" in SCRIPT, "and says when it stopped")
```

with:

```python
    ok("'Showing ' + P_ROWS_MAX + ' of ' + rows.length + '. Search or filter for more.'" in SCRIPT,
       "and says when it stopped, in a line (the mix's copy plan, Products #6)")
```

In `t_a_search_does_not_take_customise_away` replace:

```python
    ok("so there is nothing to rank." in fn, "and the card says why it has no bars")
```

with:

```python
    ok("'Nothing to rank for this period.'" in fn, "and the card says why it has no bars")
```

- [ ] **Step 5: The harnesses meet pageHead**

`customersBusy` and `openProduct` now draw their headers with `pageHead`, which two node harnesses do not load. Give each a stand-in that draws the title, which is all they read. In `t_a_paid_report_run_is_one_run_and_stays_on_screen` replace `const I = {}; function loader() { return el('span'); } function sectorBar() { return el('div'); }` with `const I = {}; function loader() { return el('span'); } function sectorBar() { return el('div'); } function pageHead(o) { const h = el('div', 'ov-hero'); h.append(el('h2', null, o.title || '')); return h; }`, and in `t_a_late_product_plan_does_not_replace_the_one_on_screen` replace `const I = {}; function loader() { return el('span'); } function ico() { return el('span'); }` with `const I = {}; function loader() { return el('span'); } function ico() { return el('span'); } function pageHead(o) { const h = el('div', 'ov-hero'); h.append(el('h2', null, o.title || '')); return h; }`.

- [ ] **Step 6: Run the tests**

Run: `ONLY=t_keywords_products_and_ python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `456 passed, 0 failed`.

- [ ] **Step 7: Look at it, and audit it**

Keywords, Products and Customers in the rig, before a run and after. Keywords before: "Your keywords and ad spend, with a ranked plan." over the tile, "Uses AI credits. Reads Search Console and Analytics." and Run. After: the header with its live line, the Summary section, the scan card with "A competitor or blog post address" in its field, and with Google unconnected the Search data card whose info button lists the two sources. Products: "Open a product for its optimisation plan." with Refresh in the actions, the table foot "Showing 6 of 6 products", Top products by revenue with no line under it. Customers before a run: the header and its line, the sector chooser, then the tile, "Uses AI credits. Reads Shopify customers and orders." and Run comprehensive audit.

Then, with the rig running:

```bash
S=/Users/cameron/Desktop/claude/gizmo/.design-rig
SIZES=1440x900,390x844 VIEWS=keywords,products,customers SHOTS=0 node "$S/spacing/audit.js" "$S/spacing/t36" && python3 "$S/spacing/analyse.py" "$S/spacing/t36" | grep -E "^## (Script errors|Page wider|overlaps|escapes|clipped)"
```

Expected: `## Script errors: 0`, no page wider than the screen, and `0 hits` for overlaps, escapes and clipped on these screens.

- [ ] **Step 8: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Reports: Keywords, Products and Customers on the one header, their setup and rules behind info buttons, and shorter lines

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---


### Task 37: Liability and Reconciliation

**Files:**
- Create: `$S/copy/t37.py` (scratch, not committed)
- Modify: `static/index.html` `loadLiability` (11846), `renderLiability` (11952-12210), `renderRecon` (16682-17050)
- Test: `tests/test_frontend.py` (a new test)

**Interfaces:**
- Consumes: `pageHead` with `info`, `infoButton`, `$S/copy/apply.py` (Task 35).
- Produces: Nothing new: the two Finance pages on the shared parts.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_liability_and_reconciliation_wear_the_mix():
    """Spec 8.3 (Finance) and the copy plan (Liability, Reconciliation): the one
    header with a short line, the rule and the setup behind info buttons beside
    their titles, the address to copy and the Connect action kept on the card,
    "Read only" kept as the safety point, and the shorter empty lines."""
    for fname in ("function renderLiability() {", "async function loadLiability(force, fresh) {", "function renderRecon() {"):
        fn = fn_src(fname)
        ok("pageHead({" in fn and "el('div', 'ov-hero')" not in fn, fname + ": the one header")
    ok("line: 'What customers owe on unpaid orders.'" in SCRIPT and "infoButton('About Liability'" in SCRIPT, "Liability's line and its rule")
    rc = fn_src("function renderRecon() {")
    ok("line: 'Checks Shopify, Xero and the inbox agree. Read only.'" in rc, "Reconciliation's line keeps Read only")
    ok("infoButton('Connecting the accounts mailbox'" in rc and "infoButton('Setting up Xero'" in rc, "both setups wait behind info buttons")
    ok("'Read only: Reactor cannot change your books.'" in rc and "ucp.append(ico(I.copy)" in rc, "the security line and the address to copy stay")
    for gone in ("Every unpaid order by how late it is", "Open one to see the orders behind the figure", "No orders currently carry an unpaid tag",
                 "Where Shopify, Xero and the inbox disagree", "That is the goal state."):
        ok(gone not in SCRIPT, "cut: " + gone)
    ok(SCRIPT.count("'Nothing is owed.'") == 2 and "'Nothing needs attention.'" in SCRIPT, "the empty lines are short")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_liability_and_reconcil python3 tests/test_frontend.py`
Expected: `FAIL  t_liability_and_reconciliation_wear_the_mix: function renderLiability() {: the one header`

- [ ] **Step 3: The headers and the words**

Create `$S/copy/t37.py` with the content below, then run `python3 "$S/copy/apply.py" "$S/copy/t37.py"` from the repo; expect `applied 16 replacements to static/index.html`.

```python
PAIRS = [
# --- Liability ---
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.spark;
            const ht = el('div'); ht.append(el('h2', null, 'Liability'),
                el('p', null, 'Credit extended to customers, from their unpaid orders.'));
            hero.append(badge, ht); box.append(hero);""",
"""            const hero = pageHead({ view: 'liability', title: 'Liability', line: 'What customers owe on unpaid orders.' });
            box.append(hero);""", 1),
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.spark;
            /* Each page is called what the sidebar and the topbar call it: all
               four Finance pages were headed 'Finance', so one page had two
               names. The Finance tabs under the heading say which group. */
            const ht = el('div'); ht.append(el('h2', null, 'Liability'),
                el('p', null, 'Credit extended to customers, from orders tagged '
                    + (d.tags || []).map(t => '"' + t + '"').join(', ')
                    + '. Terms come from the order itself, then a Net tag on the customer, otherwise Net '
                    + d.default_terms + ' is assumed and marked.'));
            /* The stamp and Refresh live on the tabs; the header's own action
               slot is where the widget grid puts Customize. */
            hero.append(badge, ht, heroAct(''));
            box.append(hero);""",
"""            /* Each page is called what the sidebar and the topbar call it. The
               one line says what the page is; which tags count and how terms are
               worked out wait behind the title's info button, word for word
               (copy plan, Liability #1). The stamp and Refresh live on the tabs. */
            box.append(pageHead({ view: 'liability', title: 'Liability', line: 'What customers owe on unpaid orders.',
                info: infoButton('About Liability', { title: 'Liability', body: 'Credit extended to customers, from orders tagged '
                    + (d.tags || []).map(t => '"' + t + '"').join(', ')
                    + '. Terms come from the order itself, then a Net tag on the customer, otherwise Net '
                    + d.default_terms + ' is assumed and marked.' }) }));""", 1),
("""                bhead.append(el('h3', 'card-title', 'Aged debt'));
                bhead.append(el('p', 'card-desc', 'Every unpaid order by how late it is, as a share of '
                    + liaMoney(d.total, cur, 0) + ' outstanding.'));""",
"""                bhead.append(el('h3', 'card-title', 'Aged debt'));""", 1),
("""                lCard.append(lHead, el('div', 'empty', 'No orders currently carry an unpaid tag. Nothing is owed.'));""",
"""                lCard.append(lHead, el('div', 'empty', 'Nothing is owed.'));""", 1),
("""            lHead.append(el('p', 'card-desc', 'Open one to see the orders behind the figure, '
                + 'when each is due, and what has been paid against it.'));
""", "", 1),
("""                        : 'No orders currently carry an unpaid tag. Nothing is owed.'));""",
"""                        : 'Nothing is owed.'));""", 1),
# --- Reconciliation ---
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.check;
            const ht = el('div');
            const rTitle = el('h2', null, 'Reconciliation');
            ht.append(rTitle,
                el('p', null, 'Checks that Shopify, Xero and the inbox agree: every sale in the books, every '
                    + 'payout in the bank, every document accounted for. It reads all three and changes none.'));
            hero.append(badge, ht); box.append(hero);""",
"""            /* "Read only" is the safety point and stays in the line (copy plan,
               Reconciliation #1). */
            box.append(pageHead({ view: 'recon', title: 'Reconciliation', line: 'Checks Shopify, Xero and the inbox agree. Read only.' }));""", 1),
("""            hero.append(heroAct(''));
            const st = reconCache.st || {};""",
"""            const st = reconCache.st || {};""", 1),
("""                mh.append(el('h3', 'card-title', 'Connect the accounts mailbox'));
                mh.append(el('p', 'card-desc',
                    'Reconciliation reads remittances, supplier invoices and statements from '
                    + 'the accounts mailbox. That is a different Google account from the one '
                    + 'behind the Inbox tab'
                    + (mb.sales_address ? ' (' + mb.sales_address + ')' : '')
                    + ', and it will not appear there.'));
                mc.append(mh);""",
"""                /* The setup, word for word, behind the title's info button (the
                   mix, spec 8.3); the address to copy and the Connect action
                   stay on the card. */
                const mt = el('h3', 'card-title', 'Connect the accounts mailbox');
                mt.append(infoButton('Connecting the accounts mailbox', { title: 'Connect the accounts mailbox', body: [
                    'Reconciliation reads remittances, supplier invoices and statements from '
                    + 'the accounts mailbox. That is a different Google account from the one '
                    + 'behind the Inbox tab'
                    + (mb.sales_address ? ' (' + mb.sales_address + ')' : '')
                    + ', and it will not appear there.',
                    'Add this callback URL to your Google OAuth client, beside the one the Inbox tab '
                    + 'already uses (APIs and Services, Credentials, your OAuth client, Authorised '
                    + 'redirect URIs). Until it is there Google refuses the sign-in with "Access '
                    + 'blocked: this app\\u2019s request is invalid".',
                    'The address is required: it is what makes Google open the right account '
                    + 'rather than the one this browser is already signed into.',
                    'If a different mailbox is connected anyway, nothing is saved and the page '
                    + 'says which one it got, so try again in a private window.'] }));
                mh.append(mt);
                mc.append(mh);""", 1),
("""                s1.append(document.createTextNode(
                    'Add this callback URL to your Google OAuth client, beside the one the Inbox tab '
                    + 'already uses (APIs and Services, Credentials, your OAuth client, Authorised '
                    + 'redirect URIs). Until it is there Google refuses the sign-in with "Access '
                    + 'blocked: this app\\u2019s request is invalid".'));""",
"""                s1.append(document.createTextNode('Add this callback URL to your Google OAuth client.'));""", 1),
("""                    s2.append(document.createTextNode('Type the accounts mailbox address and connect it. '
                        + 'The address is required: it is what makes Google open the right account '
                        + 'rather than the one this browser is already signed into.'));""",
"""                    s2.append(document.createTextNode('Type the accounts mailbox address, then connect.'));""", 1),
("""                    mc.append(el('p', 'card-sub',
                        'If a different mailbox is connected anyway, nothing is saved and the page '
                        + 'says which one it got, so try again in a private window.'));
""", "", 1),
("""                sh.append(el('h3', 'card-title', 'Connect Xero'));
                sh.append(el('p', 'card-desc', 'A one-time setup of about five minutes. Xero is connected '
                    + 'read-only: the app can read the books and has no way to change them.'));
                su.append(sh);""",
"""                /* The security point stays as the card's line; the setup is the
                   title's info button, word for word (copy plan, Reconciliation #8). */
                const xt = el('h3', 'card-title', 'Connect Xero');
                sh.append(xt);
                sh.append(el('p', 'card-desc', 'Read only: Reactor cannot change your books.'));
                su.append(sh);""", 1),
("""                if (!st.setup.configured) s3.append(document.createTextNode(
                    ' The Connect button appears here once the server has them.'));
                su.append(steps);""",
"""                if (!st.setup.configured) s3.append(document.createTextNode(
                    ' The Connect button appears here once the server has them.'));
                xt.append(infoButton('Setting up Xero', { title: 'Connect Xero', body: ['A one-time setup of about five minutes. Xero is connected '
                    + 'read-only: the app can read the books and has no way to change them.', steps] }));
                /* The address to type in Xero stays on the card, beside a Copy. */
                if (st.setup.redirect_uri) {
                    const ur = el('div', 'act-row');
                    ur.append(el('code', 'setup-code', st.setup.redirect_uri));
                    const ucp = el('button', 'btn btn-sm'); ucp.type = 'button';
                    ucp.append(ico(I.copy), document.createTextNode('Copy'));
                    ucp.onclick = async () => {
                        try { await navigator.clipboard.writeText(st.setup.redirect_uri); toastOk('Redirect URI copied.'); }
                        catch (e) { toastError('Select the address above and copy it.'); }
                    };
                    ur.append(ucp); su.append(ur);
                }""", 1),
("""            rHead.append(el('p', 'card-desc', 'Where Shopify, Xero and the inbox disagree. '
                + 'Open one to see both sides and say what it was.'));
""", "", 1),
("""                    ? 'Nothing needs attention with these filters. That is the goal state.'""",
"""                    ? 'Nothing needs attention.'""", 1),
]
```

- [ ] **Step 4: Run the tests**

Run: `ONLY=t_liability_and_reconcil python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `457 passed, 0 failed`.

- [ ] **Step 5: Look at it, and audit it**

Liability: "Liability", "What customers owe on unpaid orders." and an info button holding the unpaid tags and the terms rule; the Finance tabs with the stamp and Refresh; Aged debt with no line under it; with no debts "Nothing is owed.". Reconciliation: "Checks Shopify, Xero and the inbox agree. Read only."; unconnected, the accounts mailbox card with its info button (the four sentences), the callback address with Copy and the console link, then "Type the accounts mailbox address, then connect." and the field; the Connect Xero card with "Read only: Reactor cannot change your books.", the redirect address with Copy, and its info button holding the three steps.

Then, with the rig running:

```bash
S=/Users/cameron/Desktop/claude/gizmo/.design-rig
SIZES=1440x900,390x844 VIEWS=liability,recon SHOTS=0 node "$S/spacing/audit.js" "$S/spacing/t37" && python3 "$S/spacing/analyse.py" "$S/spacing/t37" | grep -E "^## (Script errors|Page wider|overlaps|escapes|clipped)"
```

Expected: `## Script errors: 0`, no page wider than the screen, and `0 hits` for overlaps, escapes and clipped on these screens.

- [ ] **Step 6: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Finance: Liability and Reconciliation on the one header, their rules and setup behind info buttons, the address to copy kept on the card

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---


### Task 38: Xero sync

**Files:**
- Create: `$S/copy/t38.py` (scratch, not committed)
- Modify: `static/index.html` `renderConnector` (13689-14600), the stylesheet (`.cx-tile-hint` 2024)
- Test: `tests/test_frontend.py` (`t_auto_run_shows_the_services_state_not_what_this_tab_last_clicked` 5744, `t_the_xero_page_keeps_the_details_the_last_check_found` 8413, `t_the_xero_page_uses_one_set_of_outcome_words` 8507, a new test)

**Interfaces:**
- Consumes: `pageHead`, `infoButton`, `$S/copy/apply.py` (Task 35).
- Produces: `cxTile(title, hint, row)` puts `hint` behind the tile title's info button.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_xero_sync_wears_the_mix():
    """Spec 8.3 (Finance) and the copy plan (Xero sync): one line under the
    title; the link steps and the security note behind the setup card's info
    button; Xero linked as a tag; the review rule, each tile's how-to and the
    settings note behind their titles' info buttons; the shorter lines."""
    fn = fn_src("function renderConnector() {")
    ok("pageHead({ view: 'connector', title: 'Xero sync', line: 'Shopify orders, refunds and customers, sent into Xero.' })" in fn,
       "the one header and its line")
    ok("el('div', 'ov-hero')" not in fn and "hero.append(heroAct(''))" not in fn, "nothing built by hand")
    for part in ("infoButton('Linking the connector'", "infoButton('About review and send'", "infoButton('About these settings'",
                 "if (hint) t.append(infoButton(title, { title: title, body: hint }))", "'An admin needs to link this.'",
                 "el('span', 'lbl-chip ' + (cfg.dryOnly ? 'note' : cfg.shop ? 'made' : 'warn')", "'Nothing has run yet.'",
                 "'No review yet.'", "'Held back for bad data. Fix the cause, then retry.'", "'Empty now. Refresh to update the count.'"):
        ok(part in fn, "Xero sync: " + part)
    for gone in ("invoices, credit notes and contacts in Xero", "did not write; retry once", "held back rather than written",
                 "Reviews and sends alike", "An admin links it in Railway.", "'cx-tile-hint'", "Nothing runs on its own"):
        ok(gone not in SCRIPT, "cut: " + gone)
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_xero_sync_wears_the_mi python3 tests/test_frontend.py`
Expected: `FAIL  t_xero_sync_wears_the_mix: the one header and its line`

- [ ] **Step 3: The headers and the words**

Create `$S/copy/t38.py` with the content below, then run `python3 "$S/copy/apply.py" "$S/copy/t38.py"` from the repo; expect `applied 15 replacements to static/index.html`.

```python
PAIRS = [
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.send;
            const ht = el('div');
            const hTitle = el('h2', null, 'Xero sync');
            /* The promise follows Auto Run: with it on, new orders go without
               a review, and the header said the opposite. */
            ht.append(hTitle, el('p', null,
                'Sends Shopify orders into Xero as invoices, refunds as credit notes, and new '
                + 'customers as contacts. ' + (!connAuto ? ''
                    : connAuto.enabled
                    ? 'Auto Run is on, so new orders go every ' + (connAuto.intervalMinutes || 10) + ' minutes without a review.'
                    : 'Nothing is written until a review has shown you exactly what will be sent.')));
            hero.append(badge, ht); box.append(hero);""",
"""            /* One line (copy plan, Xero sync #1). Whether Auto Run is on is the
               Connection card's tag, and with it on that tag says so. */
            box.append(pageHead({ view: 'connector', title: 'Xero sync', line: 'Shopify orders, refunds and customers, sent into Xero.' }));""", 1),
("""                head.append(el('h3', 'card-title', 'Link the connector service'));
                head.append(el('p', 'card-desc', 'Reactor is not linked to the Xero connector yet, so nothing can be reviewed or sent from here.'));
                card.append(head);""",
"""                /* The steps and the security note, word for word, behind the
                   title's info button (the mix, spec 8.3). They name the hosting
                   and its settings, so an admin sees them only on asking. */
                const lt = el('h3', 'card-title', 'Link the connector service');
                const linkHelp = [];
                head.append(lt);
                head.append(el('p', 'card-desc', 'Not linked to the Xero connector yet.'));
                card.append(head);""", 1),
("""                    card.append(steps);
                } else {
                    card.append(el('p', 'card-sub', 'An admin links it in Railway.'));
                }
                card.append(el('p', 'card-sub',
                    'The connector runs as its own service (shopify-xero-connector) with its own '
                    + 'ledger and failsafes. Reactor only drives it: credentials stay on that '
                    + 'service, and its token stays on this server.'));
                box.append(card); return;""",
"""                    linkHelp.push(steps);
                } else {
                    card.append(el('p', 'card-sub', 'An admin needs to link this.'));
                }
                linkHelp.push('The connector runs as its own service (shopify-xero-connector) with its own '
                    + 'ledger and failsafes. Reactor only drives it: credentials stay on that '
                    + 'service, and its token stays on this server.');
                lt.append(infoButton('Linking the connector', { title: 'Link the connector service', body: linkHelp }));
                box.append(card); return;""", 1),
("""            /* Past the loading, unlinked and failure states the page is cards
               the grid can move, each spanning the row, so the header gets the
               action slot Customize goes in; the states above keep their
               header as it was. */
            hero.append(heroAct(''));
""", "", 1),
("""            kpi('Synced', 'synced', 'invoices, credit notes and contacts in Xero');
            kpi('Failed', 'failed', 'did not write; retry once the cause is fixed', true);
            kpi('Quarantined', 'quarantined', 'held back rather than written with bad data', true);""",
"""            /* The labels say it; the notes that repeated them went (copy plan,
               Xero sync #6 to #8). */
            kpi('Synced', 'synced', null);
            kpi('Failed', 'failed', null, true);
            kpi('Quarantined', 'quarantined', null, true);""", 1),
("""            sHead.append(el('div', 'card-desc', cfg.dryOnly ? 'Reviews only' : (cfg.shop ? 'Xero linked' : 'Not configured')));""",
"""            /* A state, so a tag (copy plan, Xero sync #9). */
            sHead.append(el('span', 'lbl-chip ' + (cfg.dryOnly ? 'note' : cfg.shop ? 'made' : 'warn'),
                cfg.dryOnly ? 'Reviews only' : (cfg.shop ? 'Xero linked' : 'Not configured')));""", 1),
("""                    : 'Nothing runs on its own. Orders go to Xero only when ' + (connIsAdmin() ? 'you send' : 'an admin sends') + ' them.')));""",
"""                    : 'Orders go only when ' + (connIsAdmin() ? 'you send' : 'an admin sends') + ' them.')));""", 1),
("""                sCard.append(el('p', 'card-sub', 'Nothing has run yet: no review and no send.'));""",
"""                sCard.append(el('p', 'card-sub', 'Nothing has run yet.'));""", 1),
("""            rHead.append(el('h3', 'card-title', 'Review and send'));
            rHead.append(el('p', 'card-desc',
                'A review is a dry run: the service maps every eligible order and writes '
                + 'nothing. ' + (connIsAdmin() ? 'Send does exactly what the review showed.' : 'An admin sends exactly what it showed.')));""",
"""            const rTitle = el('h3', 'card-title', 'Review and send');
            rTitle.append(infoButton('About review and send', { title: 'Review and send', body:
                'A review is a dry run: the service maps every eligible order and writes '
                + 'nothing. ' + (connIsAdmin() ? 'Send does exactly what the review showed.' : 'An admin sends exactly what it showed.') }));
            rHead.append(rTitle);""", 1),
("""            const cxTile = (title, hint, row) => {
                const tile = el('div', 'cx-tile');
                tile.append(el('div', 'cx-tile-title', title), el('p', 'cx-tile-hint', hint), row);
                return tile;
            };""",
"""            /* A tile's how-to is its title's info button (copy plan, Xero sync
               #15 to #17): the Check then Send buttons carry the sequence. */
            const cxTile = (title, hint, row) => {
                const tile = el('div', 'cx-tile');
                const t = el('div', 'cx-tile-title', title);
                if (hint) t.append(infoButton(title, { title: title, body: hint }));
                tile.append(t, row);
                return tile;
            };""", 1),
("""            cxSection(rCard, 'review', 'Latest review', 'None yet. Run a review to see what would be sent.');""",
"""            cxSection(rCard, 'review', 'Latest review', 'No review yet.');""", 1),
("""                xHead.append(el('h3', 'card-title', 'Settings'));
                xHead.append(el('p', 'card-desc',
                    'How it behaves. Credentials are not on this form: they stay on the '
                    + 'service, and the server will not accept them from here.'));""",
"""                /* The security note, word for word, behind the title (copy plan,
                   Xero sync #19). */
                const xt = el('h3', 'card-title', 'Settings');
                xt.append(infoButton('About these settings', { title: 'Settings', body:
                    'How it behaves. Credentials are not on this form: they stay on the '
                    + 'service, and the server will not accept them from here.' }));
                xHead.append(xt);""", 1),
("""                hHead.append(el('p', 'card-desc', 'Reviews and sends alike, newest first.'));
""", "", 1),
("""                    'Held back rather than pushed with bad data. Fix the cause, then retry.'));""",
"""                    'Held back for bad data. Fix the cause, then retry.'));""", 1),
("""'The list is empty now. Refresh to update the count.'""", """'Empty now. Refresh to update the count.'""", 1),
]
```

- [ ] **Step 4: The rules**

Delete the rule that begins `        .cx-tile-hint {` (no tile prints its how-to any more).

- [ ] **Step 5: Update the guards that pinned the old words**

In `t_auto_run_shows_the_services_state_not_what_this_tab_last_clicked` replace:

```python
    ok("Nothing runs on its own" in seg,
       "and OFF says what off means, rather than only being unlit")
```

with:

```python
    ok("'Orders go only when '" in seg,
       "and OFF says what off means, rather than only being unlit (one line since the mix)")
```

In `t_the_xero_page_keeps_the_details_the_last_check_found` replace `    ok("'Nothing has run yet: no review and no send.'" in fn, "no run is not a green box")` with `    ok("'Nothing has run yet.'" in fn, "no run is not a green box")`.

In `t_the_xero_page_uses_one_set_of_outcome_words` replace:

```python
    ok("An admin links it in Railway." in fn and "el('ol', 'setup-steps')" in fn,
       "the unlinked page gives an admin the steps and a member the one fact")
```

with:

```python
    ok("'An admin needs to link this.'" in fn and "el('ol', 'setup-steps')" in fn and "linkHelp.push(steps)" in fn,
       "the unlinked page gives an admin the steps, behind the card's info button, and a member the one fact")
```

and replace:

```python
    ok("(!connAuto ? ''" in fn, "and the header makes no promise when Auto Run's state is unknown")
```

with:

```python
    ok("Auto Run is on, so new orders go" not in fn and "Nothing is written until a review" not in fn,
       "and the header makes no promise about Auto Run at all: its one line says what the page does (the mix)")
```

- [ ] **Step 6: Run the tests**

Run: `ONLY=t_xero_sync_wears_the_mi python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `458 passed, 0 failed`.

- [ ] **Step 7: Look at it, and audit it**

Xero sync in the rig, unlinked and linked (the harness can show both by toggling the connector stub): unlinked, "Link the connector service" with its info button (the four steps for an admin, and the note on credentials) and "Not linked to the Xero connector yet."; linked, the three tiles with labels only, the Connection card's state as a tag, Review and send's info button, each check tile's how-to behind its title, and Settings' credentials note behind its title.

Then, with the rig running:

```bash
S=/Users/cameron/Desktop/claude/gizmo/.design-rig
SIZES=1440x900,390x844 VIEWS=connector SHOTS=0 node "$S/spacing/audit.js" "$S/spacing/t38" && python3 "$S/spacing/analyse.py" "$S/spacing/t38" | grep -E "^## (Script errors|Page wider|overlaps|escapes|clipped)"
```

Expected: `## Script errors: 0`, no page wider than the screen, and `0 hits` for overlaps, escapes and clipped on these screens.

- [ ] **Step 8: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Finance: Xero sync with one line, its setup, rules and how-tos behind info buttons, and its link state as a tag

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---


### Task 39: The Size list and Loan units

**Files:**
- Create: `$S/copy/t39.py` (scratch, not committed)
- Modify: `static/index.html` `renderSizes` (16359), `sizesNone` (16427), `renderLoans` (13514-13670)
- Test: `tests/test_frontend.py` (`t_the_size_list_finds_a_fixture_however_it_is_written` 2358, a new test)

**Interfaces:**
- Consumes: `pageHead` with `info` and `actions`, `infoButton`, `emptyState`, `$S/copy/apply.py` (Task 35).
- Produces: Nothing new.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_the_size_list_and_loan_units_wear_the_mix():
    """Spec 8.3 (Queue) and the copy plan (Size list, Loan units): one line under
    each title, the ruling rule behind the Size list's info button, figures
    whose labels say it all, and the shorter empty and status lines."""
    for fname, line in (("function renderSizes() {", "line: 'The glass size the bench cuts for every fixture.'"),
                        ("function renderLoans() {", "line: 'Projectors out on loan, and for how long.'")):
        fn = fn_src(fname)
        ok(line in fn and "el('div', 'ov-hero')" not in fn, fname + ": the one header and its line")
    ok("infoButton('About the size list'" in SCRIPT and "' · built-in copy'" in SCRIPT, "the ruling rule and the short stamp")
    for gone in ("Every fixture on the size sheet", "the copy that came with the app", "and no holder takes", "'with customers'",
                 "'ready to go'", "nothing past its date", "Longest out first.", "Every loan unit the shop owns.",
                 "start tracking it", "worth a chase", "A loan with no due date turns amber"):
        ok(gone not in SCRIPT, "cut: " + gone)
    for new in ("'Nothing is out.'", "'No loan units yet.'", "'No due date'", "'Turns amber after this many days without a due date.'"):
        ok(new in SCRIPT, "says: " + new)
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_the_size_list_and_loan python3 tests/test_frontend.py`
Expected: `FAIL  t_the_size_list_and_loan_units_wear_the_mix: function renderSizes() {: the one header and its line`

- [ ] **Step 3: The headers and the words**

Create `$S/copy/t39.py` with the content below, then run `python3 "$S/copy/apply.py" "$S/copy/t39.py"` from the repo; expect `applied 10 replacements to static/index.html`.

```python
PAIRS = [
# --- Size list ---
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.check;
            const ht = el('div');
            ht.append(el('h2', null, 'Size list'),
                el('p', null, 'Every fixture on the size sheet with the glass it takes: the holder, the image, and the size the bench cuts. '
                    + 'A ruling made in the app shows over the sheet’s own answer, and the label reads the same list.'));
            hero.append(badge, ht);
            const sheet = (c && c.sheet) || {};
            const stamp = sheet.updated ? ('Sheet updated ' + fmtDate(sheet.updated) + (sheet.live ? '' : ' · the copy that came with the app')) : '';
            hero.append(heroAct(stamp, refreshBtn(refreshSizes)));
            box.append(hero);""",
"""            const sheet = (c && c.sheet) || {};
            const stamp = sheet.updated ? ('Sheet updated ' + fmtDate(sheet.updated) + (sheet.live ? '' : ' · built-in copy')) : '';
            /* One line; that a ruling wins over the sheet waits behind the
               title's info button, word for word (copy plan, Size list #1). */
            box.append(pageHead({ view: 'sizes', title: 'Size list', line: 'The glass size the bench cuts for every fixture.',
                info: infoButton('About the size list', { title: 'Size list',
                    body: 'A ruling made in the app shows over the sheet’s own answer, and the label reads the same list.' }),
                actions: [stamp ? el('span', 'ov-updated', stamp) : null, refreshBtn(refreshSizes)] }));""", 1),
("""            box.append('Nothing is cut at ' + n + ' mm, and no holder takes ' + n + ' mm glass.');""",
"""            box.append('Nothing is cut at ' + n + ' mm.');""", 1),
# --- Loan units ---
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.box;
            const htext = el('div');
            htext.append(el('h2', null, 'Loan units'),
                el('p', null, 'The projectors that go out to customers, where each one is, '
                    + 'and how long it has been gone.'));
            /* Under the header every block is a card the grid can move, each
               spanning the row; the empty action slot is where Customize goes. */
            hero.append(badge, htext, heroAct('')); box.append(hero);""",
"""            /* Under the header every block is a card the grid can move, each
               spanning the row; the header's action slot is where Customize goes. */
            box.append(pageHead({ view: 'loans', title: 'Loan units', line: 'Projectors out on loan, and for how long.' }));""", 1),
("""                { label: 'Out now', value: String(counts.out), note: 'with customers' },
                { label: 'On the shelf', value: String(counts.in), note: 'ready to go' },
                { label: 'Overdue', value: String(counts.late),
                  note: counts.late ? 'past the date agreed' : 'nothing past its date',""",
"""                { label: 'Out now', value: String(counts.out) },
                { label: 'On the shelf', value: String(counts.in) },
                { label: 'Overdue', value: String(counts.late),
                  note: counts.late ? 'past the date agreed' : null,""", 1),
("""            oHead.append(el('p', 'card-desc', 'Longest out first.'));
""", "", 1),
("""                    ? 'Everything is on the shelf.' : 'Nothing is out: no units are in the register yet.'));""",
"""                    ? 'Everything is on the shelf.' : 'Nothing is out.'));""", 1),
("""                        : (r.state === 'due' ? 'no date set, worth a chase' : 'no date set')));""",
"""                        : 'No due date'));""", 1),
("""            rHead.append(el('p', 'card-desc', 'Every loan unit the shop owns.'));
""", "", 1),
("""                rCard.append(el('div', 'empty', d.can_manage
                    ? 'No units yet. Add the first projector to start tracking it.'
                    : 'No units in the register yet.'));""",
"""                if (d.can_manage) {
                    const first = el('button', 'btn'); first.type = 'button';
                    first.append(ico(I.plus), document.createTextNode('Add a unit'));
                    first.onclick = () => loanUnitModal(null);
                    rCard.append(emptyState({ icon: I.box, text: 'No loan units yet.', action: first }));
                } else rCard.append(el('div', 'empty', 'No units in the register yet.'));""", 1),
("""                sHead.append(el('p', 'card-desc',
                    'A loan with no due date turns amber once it has been out this long.'));""",
"""                sHead.append(el('p', 'card-desc', 'Turns amber after this many days without a due date.'));""", 1),
]
```


- [ ] **Step 4: Update the guard that pinned the old words**

In `t_the_size_list_finds_a_fixture_however_it_is_written` replace:

```python
    ok("'Nothing is cut at ' + n + ' mm, and no holder takes ' + n + ' mm glass.'" in none and "st.q = v + 'mm';" in none,
       "a size the bench does not cut names the nearest it does, each a search")
```

with:

```python
    ok("'Nothing is cut at ' + n + ' mm.'" in none and "st.q = v + 'mm';" in none,
       "a size the bench does not cut names the nearest it does, each a search")
```

- [ ] **Step 5: Run the tests**

Run: `ONLY=t_the_size_list_and_loan python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `459 passed, 0 failed`.

- [ ] **Step 6: Look at it, and audit it**

Size list: "The glass size the bench cuts for every fixture." and an info button holding the ruling sentence; at the right "Sheet updated 11 Sep · built-in copy" and Refresh; search "25mm": "Nothing is cut at 25 mm." and the nearest sizes. Loan units: "Projectors out on loan, and for how long."; Out now, On the shelf and Overdue with no notes under them unless something is overdue; with no units, "Nothing is out." and the register's tile, "No loan units yet." and Add a unit.

Then, with the rig running:

```bash
S=/Users/cameron/Desktop/claude/gizmo/.design-rig
SIZES=1440x900,390x844 VIEWS=sizes,loans SHOTS=0 node "$S/spacing/audit.js" "$S/spacing/t39" && python3 "$S/spacing/analyse.py" "$S/spacing/t39" | grep -E "^## (Script errors|Page wider|overlaps|escapes|clipped)"
```

Expected: `## Script errors: 0`, no page wider than the screen, and `0 hits` for overlaps, escapes and clipped on these screens.

- [ ] **Step 7: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Queues: the Size list and Loan units on the one header, the ruling rule behind an info button, and shorter lines

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---


### Task 40: The CRM

**Files:**
- Create: `$S/copy/t40.py` (scratch, not committed)
- Modify: `static/index.html` `renderCRM` (22726), the leads card (24740), the deals card (23068), the onboarding (23210-23224), the activities card (24088), the contacts card (24230-24280), the insights `bars` (25073-25150), the stylesheet (`.crm-onboard` 3318-3320, `.crm-selbar-hint` 3325)
- Test: `tests/test_frontend.py` (`t_the_beta_tabs_say_so_everywhere_they_are_named` 2645, the CRM Insights lines in `t_the_reviewers_last_findings_stay_closed` 8117, a new test)

**Interfaces:**
- Consumes: `pageHead` (Beta comes from `BETA_TABS`), `infoButton`, `emptyState`, `$S/copy/apply.py` (Task 35).
- Produces: `bars(title, desc, rows, fmt, empty)` puts `desc` behind the title's info button and is passed `null` where the description only restated the title.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_the_crm_wears_the_mix():
    """Spec 8.3 (Desk) and the copy plan (CRM): the one header with Beta and one
    line, the amber and red key behind its info button, what a lead is and the
    funnel's counting rule behind theirs, descriptions that restated a title
    gone, and one-line empty states."""
    fn = fn_src("function renderCRM() {")
    ok("pageHead({ view: 'crm', title: 'CRM', line: 'Deals, activities and contacts for the sales desk.'" in fn
       and "el('div', 'ov-hero')" not in fn, "the one header and its line")
    ok("infoButton('About the CRM'" in fn and "infoButton('What a lead is'" in SCRIPT, "the key and the definition wait behind info buttons")
    ok("if (desc) bt.append(infoButton(title, { title: title, body: desc }))" in SCRIPT, "an Insights rule is its title's info button")
    ok("emptyState({ icon: I.briefcase, text: 'No deals yet.', action: acts })" in SCRIPT, "an empty pipeline is one line and its two ways on")
    for gone in ("Everything the desk is working on", "An empty pipeline is a fresh start", "The calls, emails and meetings the desk owes",
                 "Everyone the desk deals with", "Tick rows to delete", "What closed, summed into the month", "This fills in",
                 "they are expected to land", "What the desk actually got done", "cannot be forecast"):
        ok(gone not in SCRIPT, "cut: " + gone)
    for new in ("'No deals won yet.'", "'No expected close dates ahead.'", "'No pipeline stages yet.'", "'Nothing done in the last 30 days.'"):
        ok(new in SCRIPT, "says: " + new)
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_the_crm_wears_the_mix python3 tests/test_frontend.py`
Expected: `FAIL  t_the_crm_wears_the_mix: the one header and its line`

- [ ] **Step 3: The headers and the words**

Create `$S/copy/t40.py` with the content below, then run `python3 "$S/copy/apply.py" "$S/copy/t40.py"` from the repo; expect `applied 18 replacements to static/index.html`.

```python
PAIRS = [
("""            const hero = el('div', 'ov-hero');
            const badge = el('div', 'badge'); badge.innerHTML = I.briefcase;
            const ht = el('div');
            const cTitle = el('h2', null, 'CRM');
            cTitle.append(el('span', 'beta-tag', 'Beta'));
            ht.append(cTitle,
                el('p', null, 'Deals, activities and contacts for the sales desk. Every open deal '
                    + 'should carry a next activity; cards wearing the amber warning are the ones '
                    + 'with nothing scheduled, and a red edge means a deal has sat untouched too long.'));
            hero.append(badge, ht);
            box.append(hero);""",
"""            /* One line; the amber and red key waits behind the title's info
               button, word for word (copy plan, CRM #1). pageHead puts Beta by
               the title, as for every tab in BETA_TABS. */
            box.append(pageHead({ view: 'crm', title: 'CRM', line: 'Deals, activities and contacts for the sales desk.',
                info: infoButton('About the CRM', { title: 'CRM', body: 'Every open deal '
                    + 'should carry a next activity; cards wearing the amber warning are the ones '
                    + 'with nothing scheduled, and a red edge means a deal has sat untouched too long.' }) }));""", 1),
("""            head.append(el('h3', 'card-title',
                total.toLocaleString() + (total === 1 ? ' lead' : ' leads')));
            head.append(el('p', 'card-desc', 'A lead is an enquiry that is not yet a deal: it waits '
                + 'here so the pipeline holds only real, qualified work. Convert it when it firms up.'));""",
"""            /* A definition, so the title's info button (copy plan, CRM #2). */
            const lt = el('h3', 'card-title', total.toLocaleString() + (total === 1 ? ' lead' : ' leads'));
            lt.append(infoButton('What a lead is', { title: 'Leads', body: 'A lead is an enquiry that is not yet a deal: it waits '
                + 'here so the pipeline holds only real, qualified work. Convert it when it firms up.' }));
            head.append(lt);""", 1),
("""            head.append(el('p', 'card-desc', 'Everything the desk is working on. The board groups '
                + 'the open ones by stage; the list ranks them by what moved last.'));
""", "", 1),
("""                const ob = el('div', 'crm-onboard');
                ob.append(el('h3', null, 'An empty pipeline is a fresh start'));
                const p = el('p');
                p.append(document.createTextNode('Add your first deal, convert an enquiry from the '
                    + 'Leads inbox, or rename the stages to your own process under '));
                const pl = actionLink('miss-open', 'Pipeline');
                pl.onclick = crmStageEditor;
                p.append(pl, document.createTextNode('.'));
                ob.append(p);
                /* No second 'add' button: the card head's '+ Deal' is the one primary. */
                host.append(ob);""",
"""                /* One line and the two ways on (copy plan, CRM #5). Neither is a
                   second primary: the card head's '+ Deal' is the one. */
                const acts = el('div', 'act-row');
                const nd = el('button', 'btn'); nd.type = 'button'; nd.append(ico(I.plus), document.createTextNode('Deal'));
                nd.onclick = () => crmDealForm();
                const pl = el('button', 'btn'); pl.type = 'button'; pl.append(ico(I.settings), document.createTextNode('Pipeline'));
                pl.onclick = crmStageEditor;
                acts.append(nd, pl);
                host.append(emptyState({ icon: I.briefcase, text: 'No deals yet.', action: acts }));""", 1),
("""            head.append(el('p', 'card-desc', 'The calls, emails and meetings the desk owes. '
                + 'Overdue first; ticking one off takes it out of the list and into Done.'));
""", "", 1),
("""            head.append(el('p', 'card-desc', people
                ? 'Everyone the desk deals with: their organisation, how to reach them, and how much is open.'
                : 'The companies behind the people, with where they are and how much is open.'));
""", "", 1),
("""                if (bar2 && !crmContactSel.size) {
                    bar2.append(el('span', 'crm-selbar-hint',
                        'Tick rows to delete ' + (people ? 'people' : 'organisations')
                        + ' together.'));
                }
""", "", 1),
("""                bh.append(el('h3', 'card-title', title));
                bh.append(el('p', 'card-desc', desc));""",
"""                /* A counting rule is the title's info button; descriptions that
                   restated the title went (copy plan, CRM #11 to #15). */
                const bt = el('h3', 'card-title', title);
                if (desc) bt.append(infoButton(title, { title: title, body: desc }));
                bh.append(bt);""", 1),
("""            bars('Won by month', 'What closed, summed into the month it was won.',""", """            bars('Won by month', null,""", 1),
("""                'Nothing won yet. This fills in as deals are marked won.');""", """                'No deals won yet.');""", 1),
("""            const fcBox = bars('Expected to close', 'Open deals, in the month they are expected to land.',""", """            const fcBox = bars('Expected to close', null,""", 1),
("""                'No open deal has an expected close date from this month on.');""", """                'No expected close dates ahead.');""", 1),
("""                + ' no expected close date, so ' + (noDate === 1 ? 'it' : 'they') + ' cannot be forecast.'));""",
"""                + ' no close date.'));""", 1),
("""                null, 'No pipeline stages yet. This fills in once the pipeline has stages.');""", """                null, 'No pipeline stages yet.');""", 1),
("""            bars('Why deals are lost', 'The reason recorded when each deal was marked lost.',""", """            bars('Why deals are lost', null,""", 1),
("""            bars('Activities completed, last 30 days', 'What the desk actually got done, by kind.',""", """            bars('Activities completed, last 30 days', null,""", 1),
("""                'No activity was marked done in the last 30 days.');""", """                'Nothing done in the last 30 days.');""", 1),
("""empty || 'Nothing to chart yet. This fills in as deals are won and lost.'""", """empty || 'Nothing to chart yet.'""", 1),
]
```

- [ ] **Step 4: The rules**

Delete the three rules that begin `        .crm-onboard {`, `        .crm-onboard h3 {` and `        .crm-onboard p {`, and the rule that begins `        .crm-selbar-hint {` (nothing draws them now).

- [ ] **Step 5: Update the guards that pinned the old header and words**

In `t_the_beta_tabs_say_so_everywhere_they_are_named` replace:

```python
    ok("cTitle.append(el('span', 'beta-tag'" in SCRIPT, "the CRM heading carries it")
```

with:

```python
    ok("pageHead({ view: 'crm'" in SCRIPT and "BETA_TABS.indexOf(o.view) >= 0" in fn_src("function pageHead(o) {"),
       "the CRM heading carries it, from the one header builder")
```

In `t_the_reviewers_last_findings_stay_closed` replace:

```python
       and "'No activity was marked done in the last 30 days.'" in SCRIPT
       and "'No open deal has an expected close date from this month on.'" in SCRIPT,
```

with:

```python
       and "'Nothing done in the last 30 days.'" in SCRIPT
       and "'No expected close dates ahead.'" in SCRIPT,
```

- [ ] **Step 6: Run the tests**

Run: `ONLY=t_the_crm_wears_the_mix python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `460 passed, 0 failed`.

- [ ] **Step 7: Look at it, and audit it**

CRM: "CRM Beta", "Deals, activities and contacts for the sales desk." and the info button holding the amber and red key; Leads' title with its info button; Deals with no line under its title; an empty pipeline as the tile, "No deals yet.", Deal and Pipeline; Insights' How far deals get with its counting rule behind the info button, the other four titles alone, and their one-line empty states.

Then, with the rig running:

```bash
S=/Users/cameron/Desktop/claude/gizmo/.design-rig
SIZES=1440x900,390x844 VIEWS=crm SHOTS=0 node "$S/spacing/audit.js" "$S/spacing/t40" && python3 "$S/spacing/analyse.py" "$S/spacing/t40" | grep -E "^## (Script errors|Page wider|overlaps|escapes|clipped)"
```

Expected: `## Script errors: 0`, no page wider than the screen, and `0 hits` for overlaps, escapes and clipped on these screens.

- [ ] **Step 8: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Desk: the CRM on the one header, its key and definitions behind info buttons, and descriptions that restated a title gone

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---


### Task 41: The Inbox and Files

**Files:**
- Create: `$S/copy/t41.py` (scratch, not committed)
- Modify: `static/index.html` `mailHero` (25268), `renderMail` (25280-25560), `renderFiles` (27531-27580), `renderFilesTrash` (27583), `renderFilesBrowser` (27751-28130)
- Test: `tests/test_frontend.py` (`t_every_report_view_with_several_blocks_names_its_cards` 7001, `t_the_files_card_counts_what_is_actually_there` 3140, a new test)

**Interfaces:**
- Consumes: `pageHead` with `info`, `infoButton`, `emptyState`, `$S/copy/apply.py` (Task 35).
- Produces: `mailHero(box)` returns `pageHead`'s header; the Files title's words live in `fTitleText`.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_the_inbox_and_files_wear_the_mix():
    """Spec 8.3 (Desk) and the copy plan (Inbox, Files): one line under each
    title, the amber and red rule and the setup behind info buttons, the
    warning that matters kept as the setup card's line, the address to copy on
    the card, counts in the card's line, and one-line empty states."""
    ok("pageHead({ view: 'mail', title: 'Inbox', line: 'The shared mailbox, with an owner on every email.'" in fn_src("function mailHero(box) {"),
       "the Inbox header")
    ok("pageHead({ view: 'files', title: 'Files', line: 'The office file server, from anywhere.' })" in fn_src("function renderFiles() {"),
       "the Files header")
    m = fn_src("function renderMail() {")
    ok("infoButton('Connecting the mailbox'" in m and "'Choose the shared mailbox, not your own account.'" in m and "card.append(r2);" in m,
       "the setup waits behind its info button, the warning and the address stay")
    ok("hero.append(heroAct(''))" not in m, "pageHead gave the header its slot")
    for gone in ("Where each person is working", "Tick a few to claim", "'Every email has an owner. Good.'",
                 "reachable from anywhere", "Uploads may fail until the R2 keys", "Drag files in to store them, or onto",
                 "Searching every folder for", "Dragging files in needs a folder", "Nothing here yet. Drag files in",
                 "Nothing deleted in the last 30 days", "Ask an admin to connect the shared mailbox."):
        ok(gone not in SCRIPT, "cut: " + gone.strip())
    for new in ("'An admin needs to connect the shared mailbox.'", "'Results from every folder.'", "'Clear the search to upload here.'",
                "'No files here yet.'", "'Deleted for good after 30 days.'", "'Storage is not set up yet.'"):
        ok(new in SCRIPT, "says: " + new)
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_the_inbox_and_files_we python3 tests/test_frontend.py`
Expected: `FAIL  t_the_inbox_and_files_wear_the_mix: the Inbox header`

- [ ] **Step 3: The headers and the words**

Create `$S/copy/t41.py` with the content below, then run `python3 "$S/copy/apply.py" "$S/copy/t41.py"` from the repo; expect `applied 19 replacements to static/index.html`.

```python
PAIRS = [
# --- Inbox ---
("""        function mailHero(box) {
            const hero = el('div', 'ov-hero');
            const badge = el('div', 'badge'); badge.innerHTML = I.mail;
            const ht = el('div');
            ht.append(el('h2', null, 'Inbox'),
                el('p', null, 'The shared mailbox with an owner on every email. Claim what you are '
                    + 'dealing with, and reply from Gmail as usual. Unclaimed emails go amber, '
                    + 'then red.'));
            hero.append(badge, ht);
            box.append(hero);
            return hero;
        }""",
"""        /* One line; claiming and amber then red wait behind the title's info
           button, word for word (copy plan, Inbox #1). */
        function mailHero(box) {
            const hero = pageHead({ view: 'mail', title: 'Inbox', line: 'The shared mailbox, with an owner on every email.',
                info: infoButton('About the Inbox', { title: 'Inbox', body: 'Claim what you are '
                    + 'dealing with, and reply from Gmail as usual. Unclaimed emails go amber, '
                    + 'then red.' }) });
            box.append(hero);
            return hero;
        }""", 1),
("""                head.append(el('h3', 'card-title', 'Connect the shared mailbox'));
                card.append(head);""",
"""                /* The setup, word for word, behind the title's info button; the
                   warning that matters stays as the line, and the address to
                   copy stays on the card (the mix, spec 8.3). */
                const mct = el('h3', 'card-title', 'Connect the shared mailbox');
                const mHelp = [];
                head.append(mct);
                card.append(head);""", 1),
("""                    head.append(el('p', 'card-desc', d.client
                        ? 'Connect the mailbox whose email the team answers. Google will ask which '
                          + 'account to use: choose the shared mailbox, not your own account. Whichever '
                          + 'account you pick is the one this board reads. Google opens in a new tab, '
                          + 'and nothing is stored until you approve it there.'
                        : 'The server needs GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET set first, '
                          + 'with the Gmail API enabled in the same Google Cloud project.'));""",
"""                    head.append(el('p', 'card-desc', d.client
                        ? 'Choose the shared mailbox, not your own account.' : 'Google sign-in needs setting up first.'));
                    mHelp.push(d.client
                        ? 'Connect the mailbox whose email the team answers. Google will ask which '
                          + 'account to use: choose the shared mailbox, not your own account. Whichever '
                          + 'account you pick is the one this board reads. Google opens in a new tab, '
                          + 'and nothing is stored until you approve it there.'
                        : 'The server needs GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET set first, '
                          + 'with the Gmail API enabled in the same Google Cloud project.');""", 1),
("""                        card.append(el('div', 'radar-h', 'First time? Two switches in Google'));
                        card.append(el('p', 'card-sub', su.project
                            ? 'These open the Google project this app already uses (project '
                              + su.project + '), so nothing you have already set up changes.'
                            : 'Do these in the Google project this app already uses, so nothing '
                              + 'you have already set up changes.'));""",
"""                        mHelp.push('First time? Two switches in Google.', su.project
                            ? 'These open the Google project this app already uses (project '
                              + su.project + '), so nothing you have already set up changes.'
                            : 'Do these in the Google project this app already uses, so nothing '
                              + 'you have already set up changes.');""", 1),
("""                        r2.append(cp, link('https://console.cloud.google.com/auth/clients' + proj, 'Open your clients'));
                        s2.append(r2);
                        steps.append(s1, s2);
                        card.append(steps);
                    }""",
"""                        r2.append(cp, link('https://console.cloud.google.com/auth/clients' + proj, 'Open your clients'));
                        steps.append(s1, s2);
                        mHelp.push(steps);
                        /* The address and its Copy stay on the card. */
                        card.append(r2);
                    }
                    mct.append(infoButton('Connecting the mailbox', { title: 'Connect the shared mailbox', body: mHelp }));""", 1),
("""                    head.append(el('p', 'card-desc', 'Ask an admin to connect the shared mailbox. '
                        + 'Once it is linked, every email shows up here with an owner.'));""",
"""                    head.append(el('p', 'card-desc', 'An admin needs to connect the shared mailbox.'));""", 1),
("""            /* Connected, the page is cards the grid can move, each spanning the
               row, so the header gets the action slot Customize goes in. */
            hero.append(heroAct(''));
""",
"""            /* Connected, the page is cards the grid can move, each spanning the
               row; pageHead gave the header the action slot Customize goes in. */
""", 1),
("""                whead.append(el('p', 'card-desc', 'Where each person is working, and how much they are carrying.'));
""", "", 1),
("""                    rows.length + (rows.length === 1 ? ' email' : ' emails')
                    + '. Tick a few to claim or close them together.'));""",
"""                    rows.length + (rows.length === 1 ? ' email' : ' emails')));""", 1),
("""'Every email has an owner. Good.'""", """'Every email has an owner.'""", 1),
# --- Files ---
("""            const hero = el('div', 'ov-hero');
            const badge = el('div', 'badge'); badge.innerHTML = I.folder;
            const ht = el('div');
            ht.append(el('h2', null, 'Files'),
                el('p', null, 'The office file server, reachable from anywhere. Drag files in to '
                    + 'store them; click a picture or PDF to preview it right here, anything else '
                    + 'to download. Everything deleted waits in the trash for 30 days before it '
                    + 'is gone.'));
            hero.append(badge, ht);
            /* The two things that change the folder sit on the right of the
               page header, as the reference's file manager puts them; the
               browser fills the slot when it builds them. */
            filesHeroAct = heroAct('');
            hero.append(filesHeroAct);
            box.append(hero);""",
"""            /* One line (copy plan, Files #1); the trash keeps its 30 days on the
               Trash tab. The actions that change the folder sit in the header's
               slot, which the browser fills when it builds them. */
            const hero = pageHead({ view: 'files', title: 'Files', line: 'The office file server, from anywhere.' });
            filesHeroAct = hero.querySelector('.ov-hero-act');
            box.append(hero);""", 1),
("""                head.append(el('h3', 'card-title', 'Connect the storage'));
                head.append(el('p', 'card-desc', 'Files keeps its storage in a Cloudflare R2 bucket: durable, '
                    + 'priced in pennies, and the app signs every transfer so nothing is public. '
                    + 'Three keys in Railway switch it on; the Guide tab has the exact steps.'));""",
"""                const st = el('h3', 'card-title', 'Connect the storage');
                st.append(infoButton('About the storage', { title: 'Connect the storage', guide: ['files', ''],
                    body: 'Files keeps its storage in a Cloudflare R2 bucket: durable, '
                    + 'priced in pennies, and the app signs every transfer so nothing is public. '
                    + 'Three keys in Railway switch it on; the Guide tab has the exact steps.' }));
                head.append(st);
                head.append(el('p', 'card-desc', 'Storage is not set up yet.'));""", 1),
("""            if (d.setup_error) box.append(el('div', 'msg error', 'Storage answered with an error: ' + d.setup_error
                + '. Uploads may fail until the R2 keys in Railway are right.'));""",
"""            if (d.setup_error) box.append(el('div', 'msg error', 'Storage error: ' + d.setup_error
                + '. Uploads may fail until it is fixed.'));""", 1),
("""            tHead.append(el('h3', 'card-title', 'Trash'));
            tHead.append(el('p', 'card-desc', rows.length
                ? (rows.length === 1 ? '1 file' : rows.length + ' files') + ' (' + fmtBytes(total)
                    + ') waiting here. Everything is emptied for good 30 days after it was '
                    + 'deleted; put a file back to keep it, or delete it now to free its space.'
                : 'Nothing deleted in the last 30 days. Files deleted from the browser wait '
                    + 'here for that long, so a mistake can be undone.'));""",
"""            /* The consequence stays as the line; the rest is the title's info
               button, word for word (copy plan, Files #10 and #11). */
            const tt = el('h3', 'card-title', 'Trash');
            if (rows.length) tt.append(infoButton('About the trash', { title: 'Trash',
                body: (rows.length === 1 ? '1 file' : rows.length + ' files') + ' (' + fmtBytes(total)
                    + ') waiting here. Everything is emptied for good 30 days after it was '
                    + 'deleted; put a file back to keep it, or delete it now to free its space.' }));
            tHead.append(tt);
            if (rows.length) tHead.append(el('p', 'card-desc', 'Deleted for good after 30 days.'));""", 1),
("""            const fTitleEl = el('h3', 'card-title', 'Files');
            const fDescEl = el('p', 'card-desc', '');
            fHead.append(fTitleEl, fDescEl);""",
"""            /* The title's words change with the folder and the search; its info
               button holds how dragging works (copy plan, Files #5). */
            const fTitleEl = el('h3', 'card-title');
            const fTitleText = el('span', null, 'Files');
            fTitleEl.append(fTitleText, infoButton('Moving and uploading files', { title: 'Files', guide: ['files', ''],
                body: 'Drag files, or whole folders, anywhere on the list to upload them here. '
                    + 'Drag a file onto a folder, or onto a step of the path above, to move it.' }));
            const fDescEl = el('p', 'card-desc', '');
            fHead.append(fTitleEl, fDescEl);""", 1),
("""                    fTitleEl.textContent = n + (n === 1 ? ' file matches' : ' files match');
                    fDescEl.textContent = 'Searching every folder for \\u201c' + filesQ + '\\u201d. '
                        + 'Clear the search to go back to browsing.';""",
"""                    fTitleText.textContent = n + (n === 1 ? ' file matches' : ' files match');
                    fDescEl.textContent = 'Results from every folder.';""", 1),
("""                    fTitleEl.textContent = name;
                    fDescEl.textContent = (here === 1 ? '1 file' : here + ' files')
                        + (subs ? ' and ' + (subs === 1 ? '1 folder' : subs + ' folders') : '')
                        + ' here. Drag files in to store them, or onto a folder to move them.';""",
"""                    fTitleText.textContent = name;
                    fDescEl.textContent = (here === 1 ? '1 file' : here + ' files')
                        + (subs ? ', ' + (subs === 1 ? '1 folder' : subs + ' folders') : '');""", 1),
("""                const dropTargets = [];
                if (subs) dropTargets.push('onto a folder');
                if (filesFolder) dropTargets.push('onto a step of the path above');
                hintEl.textContent = filesQ
                    ? 'Dragging files in needs a folder to land in: clear the search to upload here.'
                    : 'Drag files, or whole folders, anywhere on the list to upload them here.'
                        + (dropTargets.length ? ' Drag a file ' + dropTargets.join(', or ') + ' to move it.' : '');""",
"""                /* Only a search needs a line: there is no folder for a drop to
                   land in. How dragging works is the title's info button. */
                hintEl.textContent = filesQ ? 'Clear the search to upload here.' : '';
                hintEl.hidden = !filesQ;""", 1),
("""                    list.append(el('div', 'files-empty', 'Nothing here yet. Drag files in, or press Upload.'));""",
"""                    list.append(emptyState({ icon: I.folder, text: 'No files here yet.', action: (() => {
                        const u = el('button', 'btn'); u.type = 'button'; u.append(ico(I.upload), document.createTextNode('Upload'));
                        u.onclick = () => fi.click(); return u; })() }));""", 1),
]
```


- [ ] **Step 4: Update the guards**

In `t_every_report_view_with_several_blocks_names_its_cards` replace (as Task 26 left it):

```python
        ok("heroAct(" in src or "pageHead({" in src or (view == "mail" and "hero.append(heroAct(''))" in src),
```

with:

```python
        ok("heroAct(" in src or "pageHead({" in src or (view == "mail" and "mailHero(box)" in src),
```

In `t_the_files_card_counts_what_is_actually_there` replace `    ok("Searching every folder" in seg, "and says that is what it is doing")` with `    ok("'Results from every folder.'" in seg, "and says that is what it is doing")`.

- [ ] **Step 5: Run the tests**

Run: `ONLY=t_the_inbox_and_files_we python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `461 passed, 0 failed`.

- [ ] **Step 6: Look at it, and audit it**

Inbox: "The shared mailbox, with an owner on every email." and the info button with claiming and amber then red; unconnected (the rig's default), Connect the shared mailbox with "Choose the shared mailbox, not your own account.", the redirect address with Copy and Open your clients, and its info button holding the steps. Files: "The office file server, from anywhere."; unconnected, Connect the storage with "Storage is not set up yet." and its info button; connected (if the rig has storage), the title's info button on dragging, the count line "12 files, 3 folders", an empty folder's tile, "No files here yet." and Upload, and Trash's "Deleted for good after 30 days.".

Then, with the rig running:

```bash
S=/Users/cameron/Desktop/claude/gizmo/.design-rig
SIZES=1440x900,390x844 VIEWS=mail,files SHOTS=0 node "$S/spacing/audit.js" "$S/spacing/t41" && python3 "$S/spacing/analyse.py" "$S/spacing/t41" | grep -E "^## (Script errors|Page wider|overlaps|escapes|clipped)"
```

Expected: `## Script errors: 0`, no page wider than the screen, and `0 hits` for overlaps, escapes and clipped on these screens.

- [ ] **Step 7: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Desk: the Inbox and Files on the one header, their rules and setup behind info buttons, counts in the line, one-line empty states

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---


### Task 42: Team, Memory and Skills

**Files:**
- Create: `$S/copy/t42.py` (scratch, not committed)
- Modify: `static/index.html` `loadTeam` (28603), `renderTeam` (28625), the People card (28678-28998), the Work cards (29016-29080), the Activity card (29117), `renderMemory` (10930), `paintImpact` (10532), `knowledgeParts` (10631-10670), `paintNotes` (10750-10836), `renderSkills` (11155), the usage card (11186-11205), `paintSkills` (11218-11256), the stylesheet (`.tm-foot` 4804)
- Test: `tests/test_frontend.py` (the Team assertion in `t_one_component_per_role_across_tabs` 1396, a new test)

**Interfaces:**
- Consumes: `pageHead`, `infoButton`, `emptyState`, `$S/copy/apply.py` (Task 35).
- Produces: Team's `cardOf(title, desc, act)` puts `desc` behind the title's info button.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_team_memory_and_skills_wear_the_mix():
    """Spec 8.3 (Workspace) and the copy plan (Team, Memory, Skills): one line
    under each title; security notes, retention rules and how things are read
    behind info buttons beside their titles, word for word; the cost warning
    kept as a short line; statuses as tags; one-line empty states."""
    for fname, line in (("function renderTeam() {", "'Who can sign in, and what everyone has done.'"),
                        ("function renderMemory() {", "'What Reactor remembers with every answer.'"),
                        ("function renderSkills() {", "'Playbooks Reactor follows in chat, reports and email drafts.'")):
        fn = fn_src(fname)
        ok("line: " + line in fn and "el('div', 'ov-hero')" not in fn, fname + ": the one header and its line")
    for part in ("infoButton('About accounts'", "infoButton('How much is kept'", "infoButton('About store knowledge'",
                 "infoButton('About notes'", "infoButton('About tracked changes'", "infoButton('How skills are used'",
                 "infoButton('About skills'", "'Uses AI credits. Reads up to 12 pages, once.'",
                 "el('span', 'lbl-chip warn', 'Waiting for an admin')", "el('span', 'lbl-chip note', 'Not read with answers')",
                 "emptyState({ icon: I.bookmark, text: 'No notes yet.', action: first })", "emptyState({ icon: I.book, text: 'No skills yet.' })"):
        ok(part in SCRIPT, "says: " + part)
    for gone in ("'tm-foot'", "Who can sign in, what each may open", "No part-time accounts yet. Set", "keeps in mind with every answer",
                 "Learning the store is an AI run", "Reactor keeps a note when something", "Reactor does not read it yet",
                 "older than the newest", "Instructions and playbooks Reactor follows", "None yet: answers name", "Ideas: a brand voice"):
        ok(gone not in SCRIPT, "cut: " + gone)
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_team_memory_and_skills python3 tests/test_frontend.py`
Expected: `FAIL  t_team_memory_and_skills_wear_the_mix: function renderTeam() {: the one header and its line`

- [ ] **Step 3: The headers and the words**

Create `$S/copy/t42.py` with the content below, then run `python3 "$S/copy/apply.py" "$S/copy/t42.py"` from the repo; expect `applied 21 replacements to static/index.html`.

```python
PAIRS = [
# --- Team ---
("""                const hero = el('div', 'ov-hero'); const ht = el('div'); ht.append(el('h2', null, 'Team')); hero.append(ht);
                box.append(hero, loadFailure('The team could not be read. ' + (e.message || ''), loadTeam));""",
"""                box.append(pageHead({ view: 'team', title: 'Team' }), loadFailure('The team could not be read. ' + (e.message || ''), loadTeam));""", 1),
("""            const hero = el('div', 'ov-hero');
            const badge = el('div', 'badge'); badge.innerHTML = I.userCheck;
            const ht = el('div');
            ht.append(el('h2', null, 'Team'),
                el('p', null, 'The app\\'s own accounts, and what everyone has been doing. Each '
                    + 'person signs in with their own username and password; their actions are '
                    + 'recorded under their name.'));
            hero.append(badge, ht);
            box.append(hero);""",
"""            box.append(pageHead({ view: 'team', title: 'Team', line: 'Who can sign in, and what everyone has done.' }));""", 1),
("""            head.append(el('h3', 'card-title', 'People (' + d.users.length + ')'));
            head.append(el('p', 'card-desc', 'Who can sign in, what each may open, and what they have been doing.'));""",
"""            /* The security note, word for word, behind the title (copy plan,
               Team #2 and #3). */
            const pt = el('h3', 'card-title', 'People (' + d.users.length + ')');
            pt.append(infoButton('About accounts', { title: 'People', body:
                'Accounts belong to the app, not Shopify. New accounts get a starter password '
                + 'shown once; everyone chooses their own on first sign-in. Tabs controls which '
                + 'parts of the app an account can open; it is enforced by the server, not '
                + 'just hidden.' }));
            head.append(pt);""", 1),
("""            /* The note belongs to the card, under its list and at the prose
               measure: outside it ran as one 1,300px line of 12px text. */
            card.append(el('p', 'card-sub tm-foot',
                'Accounts belong to the app, not Shopify. New accounts get a starter password '
                + 'shown once; everyone chooses their own on first sign-in. Tabs controls which '
                + 'parts of the app an account can open; it is enforced by the server, not '
                + 'just hidden.'));
""", "", 1),
("""                const cardOf = (title, desc, act) => {
                    const c = el('div', 'card');
                    const h = el('div', 'card-head');
                    h.append(el('h3', 'card-title', title));
                    if (desc) h.append(el('p', 'card-desc', desc));""",
"""                /* A card's rule is its title's info button (copy plan, Team #6). */
                const cardOf = (title, desc, act) => {
                    const c = el('div', 'card');
                    const h = el('div', 'card-head');
                    const ct = el('h3', 'card-title', title);
                    if (desc) ct.append(infoButton(title, { title: title, body: desc }));
                    h.append(ct);""", 1),
("""                if (!uids.length) c2.append(el('div', 'empty',
                    'No part-time accounts yet. Set someone\\'s role to Part-time and the clock '
                    + 'appears for them the next time they open the app.'));""",
"""                if (!uids.length) c2.append(el('div', 'empty', 'No part-time accounts yet.'));""", 1),
("""                const c2 = cardOf('Hours per person');""",
"""                const c2 = cardOf('Hours per person', 'Set someone\\'s role to Part-time and the clock '
                    + 'appears for them the next time they open the app.');""", 1),
("""            head.append(el('h3', 'card-title', 'Activity'));
            head.append(el('p', 'card-desc', 'Newest first. The feed shows the last 600 actions; the full ledger keeps 8,000 and is in every backup.'));""",
"""            const at = el('h3', 'card-title', 'Activity');
            at.append(infoButton('How much is kept', { title: 'Activity', body: 'Newest first. The feed shows the last 600 actions; the full ledger keeps 8,000 and is in every backup.' }));
            head.append(at);""", 1),
# --- Memory ---
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.bookmark;
            const htext = el('div'); htext.append(el('h2', null, 'Memory'),
                el('p', null, 'What Reactor keeps in mind with every answer: what it learned from your website, and the notes it keeps from chat or that '
                    + (canEditInstructions() ? 'you add here. Correct or remove anything.' : 'an admin adds here.')));
            /* Under the header every block is a card the grid can move, each
               spanning the row; the empty action slot is where Customize goes. */
            hero.append(badge, htext, heroAct('')); box.append(hero);""",
"""            /* Under the header every block is a card the grid can move, each
               spanning the row; the header's action slot is where Customize goes. */
            box.append(pageHead({ view: 'memory', title: 'Memory', line: 'What Reactor remembers with every answer.' }));""", 1),
("""            head.append(el('h3', 'card-title', 'Tracked changes'),
                el('p', 'card-desc', 'Actions you pressed Track on in an answer, measured by your headline figures from that day.'));""",
"""            const tt = el('h3', 'card-title', 'Tracked changes');
            tt.append(infoButton('About tracked changes', { title: 'Tracked changes', body: 'Actions you pressed Track on in an answer, measured by your headline figures from that day.' }));
            head.append(tt);""", 1),
("""                desc = 'Learned' + (knowledge.learned_at ? ' on ' + fmtDate(knowledge.learned_at) : '')
                    + (n ? ' from ' + n + ' page' + (n > 1 ? 's' : '') + ' of your website' : '')
                    + (knowledge.edited_at ? ', corrected' + (knowledge.edited_by ? ' by ' + knowledge.edited_by : '') + ' on ' + fmtDate(knowledge.edited_at) : '')
                    + '. Reactor reads it with every answer.';
            } else desc = 'Reactor can read your homepage, pages and blog and keep what it learns about the business. It reads it with every answer until you delete it.';
            if (!canEditInstructions()) desc += ' Only an admin can change it.';
            head.append(el('p', 'card-desc', desc));""",
"""                desc = 'Learned' + (knowledge.learned_at ? ' ' + fmtDate(knowledge.learned_at) : '')
                    + (n ? ' from ' + n + ' page' + (n > 1 ? 's' : '') : '')
                    + (knowledge.edited_at ? ', corrected' + (knowledge.edited_by ? ' by ' + knowledge.edited_by : '') + ' on ' + fmtDate(knowledge.edited_at) : '')
                    + '.';
            } else desc = '';
            /* What learning the store is, word for word, behind the title's
               info button (copy plan, Memory #2). */
            const kt = head.querySelector('.card-title');
            if (kt) kt.append(infoButton('About store knowledge', { title: 'Store knowledge',
                body: 'Reactor can read your homepage, pages and blog and keep what it learns about the business. It reads it with every answer until you delete it.' }));
            if (!canEditInstructions()) desc += (desc ? ' ' : '') + 'Only an admin can change it.';
            if (desc) head.append(el('p', 'card-desc', desc));""", 1),
("""            if (!learned && !learning && !knowledgeErr && knowledgeRead) out.push(el('p', 'card-sub', 'Learning the store is an AI run: it reads up to 12 pages of your website once, and uses AI credits.'));""",
"""            if (!learned && !learning && !knowledgeErr && knowledgeRead) out.push(el('p', 'card-sub', 'Uses AI credits. Reads up to 12 pages, once.'));""", 1),
("""            head.append(el('h3', 'card-title', 'Notes' + (memories.length ? ' (' + memories.length + ')' : '')),
                el('p', 'card-desc', 'What Reactor keeps from chat, and what ' + (canEditInstructions() ? 'you add' : 'an admin adds') + ' here. It reads the newest ' + memInject
                    + ' of each kind with every answer. Rules for how to work belong in Skills.'
                    + (canEditInstructions()
                        ? (waitingN ? ' ' + (waitingN === 1 ? 'One note from a member waits' : waitingN + ' notes from members wait') + ' under Waiting until you keep ' + (waitingN === 1 ? 'it.' : 'them.') : '')
                        : ' Only an admin can add, correct or delete a note, and a note from your chats or tracked changes waits for an admin to keep it.')));""",
"""            /* What notes are and who keeps them, word for word, behind the
               title's info button (copy plan, Memory #6). */
            const nt = el('h3', 'card-title', 'Notes' + (memories.length ? ' (' + memories.length + ')' : ''));
            nt.append(infoButton('About notes', { title: 'Notes', body: 'What Reactor keeps from chat, and what ' + (canEditInstructions() ? 'you add' : 'an admin adds') + ' here. It reads the newest ' + memInject
                    + ' of each kind with every answer. Rules for how to work belong in Skills.'
                    + (canEditInstructions()
                        ? (waitingN ? ' ' + (waitingN === 1 ? 'One note from a member waits' : waitingN + ' notes from members wait') + ' under Waiting until you keep ' + (waitingN === 1 ? 'it.' : 'them.') : '')
                        : ' Only an admin can add, correct or delete a note, and a note from your chats or tracked changes waits for an admin to keep it.') }));
            head.append(nt);""", 1),
("""                if (!memView.adding) host.append(el('div', 'empty', 'No notes yet. Reactor keeps a note when something in a chat is worth remembering'
                    + (canEditInstructions() ? ', and you can add one here.' : '.')));""",
"""                if (!memView.adding) {
                    let first = null;
                    if (canEditInstructions()) {
                        first = el('button', 'btn'); first.type = 'button'; first.append(ico(I.plus), document.createTextNode('Add a note'));
                        first.onclick = () => { memView.adding = true; memView.editId = null; paintNotes(); };
                    }
                    host.append(emptyState({ icon: I.bookmark, text: 'No notes yet.', action: first }));
                }""", 1),
("""            if (waiting) bits.push('Waiting for an admin to keep it' + (m.by ? ', from ' + m.by : '') + '. Reactor does not read it yet');""",
"""            /* Two states as tags, not sentences (copy plan, Memory #10 and #11). */
            if (waiting) k.append(el('span', 'lbl-chip warn', 'Waiting for an admin'));""", 1),
("""            if (!waiting && !sent.has(m.id) && !(m.type === 'followup' && m.status !== 'open')) bits.push('not read with answers: older than the newest ' + memInject + ' of its kind');""",
"""            if (!waiting && !sent.has(m.id) && !(m.type === 'followup' && m.status !== 'open')) k.append(el('span', 'lbl-chip note', 'Not read with answers'));""", 1),
# --- Skills ---
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.book;
            const ht = el('div'); ht.append(el('h2', null, 'Skills'),
                el('p', null, 'Instructions and playbooks Reactor follows: a brand voice, a discount policy, how to answer a trade enquiry. ' + (canEditInstructions() ? 'Write one here' + (skillCaps.upload ? ' or upload a Markdown file' : '') + '. ' : 'An admin writes them here. ') + 'Reactor picks the ones that fit each question, in chat, in reports and in email drafts, and says under each answer which it followed.'));
            /* The empty action slot is where Customize goes. */
            hero.append(badge, ht, heroAct('')); box.append(hero);""",
"""            /* The header's action slot is where Customize goes. */
            box.append(pageHead({ view: 'skills', title: 'Skills', line: 'Playbooks Reactor follows in chat, reports and email drafts.' }));""", 1),
("""            head.append(el('h3', 'card-title', 'How they are used'),
                el('p', 'card-desc', 'With each question Reactor reads in full the skills that fit it best, up to ' + nf(skillCaps.inject)
                    + ' characters in all, and any marked for every answer. A skill too long for that is given as what it asks, its headings and the parts that fit: in chat Reactor reads the section it needs, and reports and email drafts get the parts that match. The titles of the rest are there for chat to open when one fits. Yours come to ' + nf(chars) + ' characters.'));""",
"""            /* How skills are read, and the two lines of advice, word for word
               behind the title's info button (copy plan, Skills #4, #6, #7). */
            const ut = el('h3', 'card-title', 'How they are used');
            const uHelp = ['With each question Reactor reads in full the skills that fit it best, up to ' + nf(skillCaps.inject)
                    + ' characters in all, and any marked for every answer. A skill too long for that is given as what it asks, its headings and the parts that fit: in chat Reactor reads the section it needs, and reports and email drafts get the parts that match. The titles of the rest are there for chat to open when one fits. Yours come to ' + nf(chars) + ' characters.'];
            head.append(ut);""", 1),
("""            fact('Followed most', used.length ? used.slice(0, 3).map(x => x.title + ' (' + x.used + ')').join(', ') : 'None yet: answers name the skills they follow from now on.');
            if (never.length && used.length) fact('Not followed yet', never.slice(0, 5).map(x => x.title).join(', ') + (never.length > 5 ? ' and ' + (never.length - 5) + ' more' : '')
                + '. A clear note of when each applies helps Reactor see where one fits, or pick it with Skills when you ask.');
            if (unread.length) fact('Not read by Reactor', unread.slice(0, 5).map(x => x.title).join(', ') + (unread.length > 5 ? ' and ' + (unread.length - 5) + ' more' : '')
                + '. Having it read shows you what Reactor will do with each, and gives it a short version to use when a skill is too long to show in full.');
            card.append(facts);""",
"""            fact('Followed most', used.length ? used.slice(0, 3).map(x => x.title + ' (' + x.used + ')').join(', ') : 'None yet');
            if (never.length && used.length) {
                fact('Not followed yet', never.slice(0, 5).map(x => x.title).join(', ') + (never.length > 5 ? ' and ' + (never.length - 5) + ' more' : ''));
                uHelp.push('A clear note of when each applies helps Reactor see where one fits, or pick it with Skills when you ask.');
            }
            if (unread.length) {
                fact('Not read by Reactor', unread.slice(0, 5).map(x => x.title).join(', ') + (unread.length > 5 ? ' and ' + (unread.length - 5) + ' more' : ''));
                uHelp.push('Having it read shows you what Reactor will do with each, and gives it a short version to use when a skill is too long to show in full.');
            }
            ut.append(infoButton('How skills are used', { title: 'How they are used', body: uHelp }));
            card.append(facts);""", 1),
("""            head.append(el('h3', 'card-title', 'Your skills' + (skills.length ? ' (' + skills.length + ')' : '')),
                el('p', 'card-desc', 'Rules and playbooks, each with a title and a note of when it applies.'
                    + (skillCaps.upload ? ' Drop Markdown files here to add them.' : '')
                    + (canEditInstructions() ? '' : ' Only an admin can add, change or delete a skill.')));""",
"""            const yt = el('h3', 'card-title', 'Your skills' + (skills.length ? ' (' + skills.length + ')' : ''));
            yt.append(infoButton('About skills', { title: 'Your skills', body: 'Rules and playbooks, each with a title and a note of when it applies.'
                    + (skillCaps.upload ? ' Drop Markdown files here to add them.' : '')
                    + (canEditInstructions() ? '' : ' Only an admin can add, change or delete a skill.') }));
            head.append(yt);""", 1),
("""                if (!skView.adding && !skView.uploads) card.append(el('div', 'empty', canEditInstructions()
                    ? 'No skills yet. Write one' + (skillCaps.upload ? ', or upload a Markdown file' : '') + '. Ideas: a brand voice guide, a discounting policy, an SEO checklist, or how to answer a trade enquiry.'
                    : 'No skills yet. An admin can write one: a brand voice guide, a discounting policy, or how to answer a trade enquiry.'));""",
"""                /* One line; New skill and Upload are the card head's (copy plan, Skills #3). */
                if (!skView.adding && !skView.uploads) card.append(emptyState({ icon: I.book, text: 'No skills yet.' }));""", 1),
]
```

- [ ] **Step 4: The rules**

Delete `        .tm-foot { max-width: var(--measure); }` (the note is an info button now).

- [ ] **Step 5: Update the guard that pinned the old card call**

In `t_one_component_per_role_across_tabs` replace `       and "cardOf('Hours per person')" in SCRIPT, "and all three of its headings moved together")` with `       and "cardOf('Hours per person'" in SCRIPT, "and all three of its headings moved together")`.

- [ ] **Step 6: Run the tests**

Run: `ONLY=t_team_memory_and_skills python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `462 passed, 0 failed`.

- [ ] **Step 7: Look at it, and audit it**

Team: "Who can sign in, and what everyone has done."; People's title with its info button (the account and Tabs note); Work's Hours per person with its info button and, with no part-timers, "No part-time accounts yet."; Activity's title with its info button. Memory: "What Reactor remembers with every answer."; Store knowledge's info button; unlearned, "Uses AI credits. Reads up to 12 pages, once."; Notes with its info button, a waiting note's Waiting for an admin tag; with no notes, the tile, "No notes yet." and Add a note. Skills: "Playbooks Reactor follows in chat, reports and email drafts."; with none, the tile and "No skills yet."; How they are used with the facts only and its info button.

Then, with the rig running:

```bash
S=/Users/cameron/Desktop/claude/gizmo/.design-rig
SIZES=1440x900,390x844 VIEWS=team,memory,skills SHOTS=0 node "$S/spacing/audit.js" "$S/spacing/t42" && python3 "$S/spacing/analyse.py" "$S/spacing/t42" | grep -E "^## (Script errors|Page wider|overlaps|escapes|clipped)"
```

Expected: `## Script errors: 0`, no page wider than the screen, and `0 hits` for overlaps, escapes and clipped on these screens.

- [ ] **Step 8: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Workspace: Team, Memory and Skills on the one header, their notes and rules behind info buttons, statuses as tags

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---


### Task 43: Chat, the Guide and Design, and the composer on the same roles

**Files:**
- Create: `$S/copy/t43.py` and `$S/copy/t43c.py` (scratch, not committed)
- Modify: `static/index.html` the composer markup (5165-5172), `renderEmptyChat` (8659), `renderGuide` (22014), `paintRequests` (22380), the Guide search (22320), `askFeature` (22503), `dsCard` (22125), `paintDesign` (22136-22262), the stylesheet (`.composer .hint` 4380 and 4399); `static/composer.js` (its injected rules, 52-108)
- Test: `tests/test_frontend.py` (`t_the_brand_pilot_review_findings_stay_fixed` 9403, a new test)

**Interfaces:**
- Consumes: `pageHead`, `infoButton`, `MIX_TOKENS` (Tasks 2 to 4), the role tokens `--radius-field`, `--radius-pop`, `--radius-swatch`, `--radius-tag`, `--shadow-pop`, `--lh-prose`, `$S/copy/apply.py` (Task 35).
- Produces: `dsCard(title, desc, ...kids)` puts `desc` behind the title's info button; the Design page's Tokens section draws every `MIX_TOKENS` group.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_chat_the_guide_and_design_wear_the_mix():
    """Spec 8.3 (Workspace) and the copy plan (Chat, Guide, Design): the empty
    chat's one line, Enter and Shift+Enter on Send's own tooltip, the Guide's
    header with no line (its tabs say it), each Design section's explanation
    behind its title, the mix's tokens drawn on the Design page, and the
    composer on the same corners, type and focus as the page."""
    ok("'Ask about products, orders, customers and stock.'" in SCRIPT, "the empty chat's line")
    ok('title="Enter to send · Shift+Enter for a new line"' in HTML and '<span class="hint">' not in HTML, "the keys are Send's tooltip")
    ok("pageHead({ view: 'guide', title: 'Guide' })" in fn_src("function renderGuide() {"), "the Guide's header")
    ok("if (desc) t.append(infoButton(title, { title: title, body: desc }))" in fn_src("function dsCard(title, desc, ...kids) {"),
       "a Design section's explanation is its title's info button")
    ok("MIX_TOKENS.forEach(([group, names]) =>" in fn_src("function paintDesign(host) {"), "the Design page draws the mix's tokens")
    for gone in ("How the desk runs, what changed", "Short and specific beats polished", "Ask for a feature if something is missing",
                 "It goes on Guide, Requests", "The strip of headline figures", "What a screen says when there is nothing",
                 "When there is, it shows here.", "Reactor reads your live figures and answers"):
        ok(gone not in SCRIPT, "cut: " + gone)
    for bad in ("var(--radius-sm)", "var(--radius-xs)", "outline-offset: 1px", "line-height: 20px", "line-height: 1.5"):
        ok(bad not in COMPOSER, "the composer reads the roles: " + bad)
    ok("@media (hover: hover) { .cmp-b:hover" in COMPOSER, "and hovers only where there is a pointer")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_chat_the_guide_and_des python3 tests/test_frontend.py`
Expected: `FAIL  t_chat_the_guide_and_design_wear_the_mix: the empty chat's line`

- [ ] **Step 3: The headers and the words**

Create `$S/copy/t43.py` with the content below, then run `python3 "$S/copy/apply.py" "$S/copy/t43.py"` from the repo; expect `applied 13 replacements to static/index.html`.

```python
PAIRS = [
# --- Chat ---
("""                el('p', null, 'Ask about your products, orders, customers and stock. Reactor reads your live figures and answers with findings and next steps, following your skills where they fit.'));""",
"""                el('p', null, 'Ask about products, orders, customers and stock.'));""", 1),
("""                            <button class="send" id="send" title="Send" aria-label="Send" disabled></button>""",
"""                            <button class="send" id="send" title="Enter to send · Shift+Enter for a new line" aria-label="Send" disabled></button>""", 1),
("""                            <span class="hint">Enter to send · Shift+Enter for a new line</span>
""", "", 1),
("""        @media (hover: none) { .composer .hint { display: none; } }
""", "", 1),
# --- Guide ---
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.book;
            const ht = el('div');
            /* One header for the whole set, the same on every tab: a sentence
               swapped per tab (one line on some, two on Design) and a Print
               button shown on one tab only moved the strip under the pointer
               on every click. Print sits with the Guide's own search. */
            ht.append(el('h2', null, 'Guide'), el('p', 'guide-desc',
                'How the desk runs, what changed in Reactor, and what the team has asked for.'));
            hero.append(badge, ht);
            box.append(hero);""",
"""            /* One header for the whole set, the same on every tab, and no line:
               the tabs under it say what the Guide holds (copy plan, Guide #1).
               Print sits with the Guide's own search. */
            box.append(pageHead({ view: 'guide', title: 'Guide' }));""", 1),
("""            head.append(el('h3', 'card-title', 'Feature requests'));
            head.append(el('p', 'card-desc', u.can_triage
                ? 'What the team has asked for. Set each one Planned, Shipped or Declined with a reply, and the person who asked sees it here.'
                : 'Anything the app cannot do yet, or does awkwardly. Short and specific beats polished. An admin answers each one here.'));""",
"""            /* An admin's how-to is the title's info button; a member keeps one
               line (copy plan, Guide #3 and #4). */
            const ft = el('h3', 'card-title', 'Feature requests');
            if (u.can_triage) ft.append(infoButton('About requests', { title: 'Feature requests',
                body: 'What the team has asked for. Set each one Planned, Shipped or Declined with a reply, and the person who asked sees it here.' }));
            head.append(ft);
            if (!u.can_triage) head.append(el('p', 'card-desc', 'Ask for what the app cannot do yet.'));""", 1),
("""                none.textContent = 'Nothing in the guide mentions "' + guideView.q + '". Ask for a feature if something is missing.';""",
"""                none.textContent = 'Nothing in the guide mentions \\u201c' + guideView.q + '\\u201d.';""", 1),
("""            form.append(el('p', 'card-sub', 'What should the app do that it does not do yet, or what gets in the way? '
                + 'It goes on Guide, Requests, where an admin answers it.'));""",
"""            form.append(el('p', 'card-sub', 'What should the app do that it cannot yet?'));""", 1),
# --- Design ---
("""        function dsCard(title, desc, ...kids) {
            const c = el('section', 'card');
            const h = el('div', 'card-head');
            h.append(el('h3', 'card-title', title));
            if (desc) h.append(el('p', 'card-desc', desc));""",
"""        /* Each section's explanation is its title's info button (copy plan,
           Design #1 to #8): the samples under it show the rest. */
        function dsCard(title, desc, ...kids) {
            const c = el('section', 'card');
            const h = el('div', 'card-head');
            const t = el('h3', 'card-title', title);
            if (desc) t.append(infoButton(title, { title: title, body: desc }));
            h.append(t);""", 1),
("""            page.append(colours);""",
"""            page.append(colours);
            /* The mix's own tokens (spec 4), each with the value the browser
               reads for it now: a swatch for a colour, the figure for the rest. */
            const mix = dsCard('Tokens', null);
            MIX_TOKENS.forEach(([group, names]) => {
                const grid = el('div', 'ds-swatches');
                names.forEach(t => {
                    const v = getComputedStyle(document.documentElement).getPropertyValue(t).trim();
                    const sw = el('div', 'ds-swatch');
                    if (v && CSS.supports('color', v)) {
                        const chip = el('span', 'ds-chip'); chip.style.background = 'var(' + t + ')';
                        chip.setAttribute('aria-hidden', 'true'); sw.append(chip);
                    }
                    const facts = el('div', 'ds-facts');
                    facts.append(el('div', 'ds-name', t), el('div', 'ds-val', v));
                    sw.append(facts); grid.append(sw);
                });
                mix.append(dsLabel(group), grid);
            });
            page.append(mix);""", 1),
("""            page.append(dsCard('Figures', 'The strip of headline figures at the top of a report.',""",
"""            page.append(dsCard('Figures', null,""", 1),
("""            page.append(dsCard('Messages', 'What a screen says when there is nothing to show, when something failed, and when something happened.',""",
"""            page.append(dsCard('Messages', null,""", 1),
("""                el('div', 'empty', 'Nothing to list yet. When there is, it shows here.'),""",
"""                el('div', 'empty', 'Nothing here yet.'),""", 1),
]
```

- [ ] **Step 4: The rules and the composer**

Delete the rule that begins `        .composer .hint {` (the keys are Send's tooltip now).

Create `$S/copy/t43c.py` with the content below and run `python3 "$S/copy/apply.py" "$S/copy/t43c.py" static/composer.js`; expect `applied 11 replacements to static/composer.js`.

```python
PAIRS = [
("""        '    border-radius: var(--radius-sm) var(--radius-sm) 0 0; background: var(--surface-tertiary); position: relative; }',""",
 """        '    border-radius: var(--radius-field) var(--radius-field) 0 0; background: var(--surface-tertiary); position: relative; }',""", 1),
("""        '    border-radius: var(--radius-xs); min-height: 32px; min-width: 32px; padding: 4px 8px;',
        '    font-size: var(--text-sm); font-weight: var(--weight-medium); line-height: 20px;',""",
 """        '    border-radius: var(--radius-control); min-height: var(--control-h); min-width: var(--control-h); padding: var(--sp-1) var(--sp-2);',
        '    font-size: var(--text-body); font-weight: var(--weight-medium); line-height: var(--lh-control);',""", 1),
("""        '.cmp-b:hover { background: var(--surface-primary); border-color: var(--border-default); }',
        '.cmp-b:focus-visible { outline: var(--focus-outline); outline-offset: 1px; }',""",
 """        '@media (hover: hover) { .cmp-b:hover { background: var(--surface-primary); border-color: var(--border-default); } }',
        '.cmp-b:focus-visible { outline: var(--focus-outline); outline-offset: var(--sp-0-5); }',""", 1),
("""        '    color: var(--text-primary); border-radius: var(--radius-xs); font: inherit; font-size: var(--text-xs);',""",
 """        '    color: var(--text-primary); border-radius: var(--radius-field); font: inherit; font-size: var(--text-body);',""", 1),
("""        '    border-radius: var(--radius-sm); box-shadow: var(--shadow-lg); }',""",
 """        '    border-radius: var(--radius-pop); box-shadow: var(--shadow-pop); }',""", 1),
("""        '.cmp-sw { width: 28px; height: 28px; border-radius: var(--radius-xs); border: 1px solid var(--border-strong);',""",
 """        '.cmp-sw { width: 28px; height: 28px; border-radius: var(--radius-swatch); border: 1px solid var(--border-strong);',""", 1),
("""        '.cmp-area { border: 1px solid var(--border-default); border-radius: 0 0 var(--radius-sm) var(--radius-sm);',
        '    background: var(--surface-primary); color: var(--text-primary); font-size: var(--text-sm); line-height: 1.5;',""",
 """        '.cmp-area { border: 1px solid var(--border-default); border-radius: 0 0 var(--radius-field) var(--radius-field);',
        '    background: var(--surface-primary); color: var(--text-primary); font-size: var(--text-body); line-height: var(--lh-prose);',""", 1),
("""        '.cmp-area img { max-width: 100%; height: auto; border-radius: var(--radius-xs); }',""",
 """        '.cmp-area img { max-width: 100%; height: auto; border-radius: var(--radius-control); }',""", 1),
("""        '    padding: var(--sp-1) var(--sp-2); border: 1px solid var(--border-default); border-radius: var(--radius-sm);',""",
 """        '    padding: var(--sp-1) var(--sp-2); border: 1px solid var(--border-default); border-radius: var(--radius-tag);',""", 1),
("""        '    min-width: 24px; min-height: 24px; border-radius: var(--radius-xs); font-size: var(--text-sm);',""",
 """        '    min-width: var(--control-h-sm); min-height: var(--control-h-sm); border-radius: var(--radius-tag); font-size: var(--text-body);',""", 1),
("""        '.cmp-x:hover { color: var(--text-primary); background: var(--surface-tertiary); }',""",
 """        '@media (hover: hover) { .cmp-x:hover { color: var(--text-primary); background: var(--surface-tertiary); } }',""", 1),
]
```

- [ ] **Step 5: The composer's focus guard**

In `t_the_brand_pilot_review_findings_stay_fixed` replace `    ok("'.cmp-b:focus-visible { outline: var(--focus-outline); outline-offset: 1px; }'" in COMPOSER,` with `    ok("'.cmp-b:focus-visible { outline: var(--focus-outline); outline-offset: var(--sp-0-5); }'" in COMPOSER,` (its reason stays: the app's own outline, now 2 off the edge as everywhere since Task 22).

- [ ] **Step 6: Run the tests**

Run: `ONLY=t_chat_the_guide_and_des python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `463 passed, 0 failed`.

- [ ] **Step 7: Look at it, and audit it**

Chat: the empty chat says "Ask about products, orders, customers and stock."; hovering Send shows "Enter to send · Shift+Enter for a new line"; no hint line under the composer. Guide: "Guide" with no line, then its tabs; Requests (as an admin) with its info button; a search for "zzz" says "Nothing in the guide mentions “zzz”.". Design: each section title with its info button, Figures and Messages with none, the Tokens section listing the mix's groups with a swatch for each colour. Open Inbox compose (if the rig can) and see the composer's 6 corners and its 2 off focus ring.

Then, with the rig running:

```bash
S=/Users/cameron/Desktop/claude/gizmo/.design-rig
SIZES=1440x900,390x844 VIEWS=chat,guide SHOTS=0 node "$S/spacing/audit.js" "$S/spacing/t43" && python3 "$S/spacing/analyse.py" "$S/spacing/t43" | grep -E "^## (Script errors|Page wider|overlaps|escapes|clipped)"
```

Expected: `## Script errors: 0`, no page wider than the screen, and `0 hits` for overlaps, escapes and clipped on these screens.

- [ ] **Step 8: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json static/composer.js
git commit -m "Workspace: Chat, the Guide and Design wear the mix, Design draws its tokens, and the composer reads the same corner, type and focus roles

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---


### Task 44: Windows, sign-in and settings, and the last old rules

**Files:**
- Create: `$S/copy/t44.py` (scratch, not committed)
- Modify: `static/index.html` the settings markup (5186-5252), `:root` (`--radius-sm`, `--radius-xl`), the scrollbar thumb (332), the badge rules (694-698), `.auth-card` (4574-4580), `.modal` and `.modal-head h3` (4506-4511), `.toast` (4851-4853), the sign-in steps (28420-28530), the connections (29595-29735), the two-step window (29966-29993), `paintPrivacy` (30062), the dispatch and shipping windows (19849-21600), the order, size rule, loan, CRM and Inbox windows, `printFromAdminLink` and `dispatchFromAdminLink` (21696-21725)
- Test: `tests/test_frontend.py` (`t_the_sign_in_card_is_the_clean_minimal_design` 7182, `t_the_card_elevation_token_actually_paints` 3646, `t_the_dead_elevation_token_is_gone` 1363, `t_the_login_screen_knows_a_password_is_not_always_enough` 4460, a new test)

**Interfaces:**
- Consumes: `pageHead`, `infoButton`, `--radius-pop`, `--shadow-pop`, `$S/copy/apply.py` (Task 35).
- Produces: No page header anywhere is built by hand; `--radius-sm` and `--radius-xl` are gone.

- [ ] **Step 1: Write the failing test**

Append above `if __name__ == "__main__":`:

```python
@test
def t_windows_sign_in_and_settings_wear_the_mix():
    """Spec 8.3 (Floating) and the copy plan (Sign-in, Settings window, Other
    dialogs): the sign-in card on the floating corner and shadow; every window's
    help one short line or its title's info button, warnings kept; no setting
    or hosting name on a connection line; no header anywhere built by hand; the
    old corner and badge rules gone."""
    for new in ("'Your own account, not Shopify’s. No account? Ask an admin.'", "'Code from your authenticator app, or a recovery code.'",
                "'Create the master admin account. You need the setup code.'", "'Set your own password before carrying on.'",
                "'Not encrypted: secrets are stored in plain text.'", "'Not set up yet. Steps in the Guide.'",
                "'Weigh the packed box: couriers re-weigh and bill it.'", "'Collections booked in their portal do not show.'",
                "'Its labels print no size from now on.'", "Keep these recovery codes somewhere safe: '"):
        ok(new in SCRIPT, "says: " + new)
    for gone in ("TOKEN_ENCRYPTION_KEY", "set APP_URL in Railway", "GA4_PROPERTY_ID", "GSC_SITE_URL", "RESEND_API_KEY", "ZETA_URL and ZETA",
                 "GOOGLE_OAUTH_CLIENT_ID / SECRET", "Add your API key to start dispatching", "insurer wins",
                 "somewhere safe - ", "applied to every chat and every report as authoritative"):
        ok(gone not in SCRIPT + HTML, "cut: " + gone)
    ok(SCRIPT.count("el('div', 'ov-hero')") == 1 and "el('div', 'ov-hero')" in fn_src("function pageHead(o) {")
       and "el('div', 'badge')" not in SCRIPT, "every page header is pageHead's, the one place that builds one")
    ok(".ov-hero .badge" not in CSS, "so the badge's rules are gone")
    card = re.search(r"\.auth-card \{[^}]*\}", CSS, re.S).group(0)
    ok("border-radius: var(--radius-pop)" in card and "box-shadow: var(--shadow-pop)" in card, "the sign-in card floats like every window")
    modal = CSS.split("\n        .modal {")[1].split("}")[0]
    ok("border: 0" in modal and "border-radius: var(--radius-pop)" in modal and "box-shadow: var(--shadow-pop)" in modal,
       "a dialog floats like every window: the 10 corner and the pop shadow, its edge the shadow's own ring")
    h3 = CSS.split("\n        .modal-head h3 {")[1].split("}")[0]
    ok("font-weight: var(--weight-semibold)" in h3 and "line-height: var(--lh-control)" in h3, "and its title is the head step")
    toast = CSS.split("\n        .toast {")[1].split("}")[0]
    ok("border: 0" in toast and "padding: var(--pop-pad)" in toast and "box-shadow: var(--shadow-pop)" in toast,
       "a toast floats the same way, 16 inside, its status still the bar at its left")
    ok(not re.search(r"--radius-(sm|xl)\s*:", CSS) and "var(--radius-sm)" not in SCRIPT + CSS + COMPOSER, "the old corners are gone")
```

- [ ] **Step 2: Run it to see it fail**

Run: `ONLY=t_windows_sign_in_and_se python3 tests/test_frontend.py`
Expected: `FAIL  t_windows_sign_in_and_settings_wear_the_mix: says: 'Your own account, not Shopify’s. No account? Ask an admin.'`

- [ ] **Step 3: The headers and the words**

Create `$S/copy/t44.py` with the content below, then run `python3 "$S/copy/apply.py" "$S/copy/t44.py"` from the repo; expect `applied 49 replacements to static/index.html`.

```python
PAIRS = [
# --- sign-in (copy plan, Sign-in #1 to #4) ---
("""                    el('p', 'auth-sub', 'Your own account, not Shopify\\'s. Ask an admin if you '
                        + 'do not have one yet.'));""",
"""                    el('p', 'auth-sub', 'Your own account, not Shopify’s. No account? Ask an admin.'));""", 1),
("""                    el('p', 'auth-sub', 'Type the six-digit code from your authenticator app. '
                        + 'If you have lost your phone, one of your recovery codes works here too.'));""",
"""                    el('p', 'auth-sub', 'Code from your authenticator app, or a recovery code.'));""", 1),
("""                    el('p', 'auth-sub', 'The app keeps its own accounts. Create the master '
                        + 'admin account first: it controls everything, including the other accounts. '
                        + 'You need the one-time setup code from whoever runs the server.'));""",
"""                    el('p', 'auth-sub', 'Create the master admin account. You need the setup code.'));""", 1),
("""                    el('p', 'auth-sub', 'The starter password was only for getting in. Set your '
                        + 'own before carrying on; nobody else ever sees it.'));""",
"""                    el('p', 'auth-sub', 'Set your own password before carrying on.'));""", 1),
# --- the settings window (copy plan, Settings window) ---
("""<p class="field-help" style="margin-top:0">Saved to your store and applied to every chat and every report as authoritative context.</p>""",
 """<p class="field-help" style="margin-top:0">Reactor reads this with every chat and report.</p>""", 1),
("""<p class="field-help" style="margin-top:0">Put on the end of email you send from the Inbox, above the shop footer. Up to four lines: your name, and whatever you want under it.</p>""",
 """<p class="field-help" style="margin-top:0">Ends every email you send from the Inbox.</p>""", 1),
("""<div class="setting-sub">Re-run your audits on a schedule so they stay fresh, and flag big changes as alerts. Off by default; uses AI credits on each run.</div>""",
 """<div class="setting-sub">Re-run audits on a schedule. Uses AI credits each run.</div>""", 1),
("""<div><div class="setting-title">Frequency</div><div class="setting-sub">How often to refresh and check for notable changes.</div></div>""",
 """<div><div class="setting-title">Frequency</div></div>""", 1),
("""            box.append(el('div', 'setting-sub', 'When you erase a customer in Shopify, Shopify asks Reactor to erase what it holds about them too. '
                + 'Each request waits here for an admin to erase it, or to stop one nobody here asked for. Shopify allows thirty days from when it arrives.'));""",
"""            /* How the requests work, word for word, behind the section title's
               info button (copy plan, Settings #8). */
            const pt = box.previousElementSibling;
            if (pt && pt.classList.contains('section-title') && !pt.querySelector('.info'))
                pt.append(infoButton('About privacy requests', { title: 'Privacy requests', body: 'When you erase a customer in Shopify, Shopify asks Reactor to erase what it holds about them too. '
                    + 'Each request waits here for an admin to erase it, or to stop one nobody here asked for. Shopify allows thirty days from when it arrives.' }));""", 1),
("""                    'Not encrypted. The refresh tokens and sign-in code secrets are stored '
                    + 'in plain text. Set TOKEN_ENCRYPTION_KEY in Railway.', CR_SEAL));""",
"""                    'Not encrypted: secrets are stored in plain text.', CR_SEAL));""", 1),
("""                      : ('Not receiving order events yet'
                         + (wh.detail ? (/unset/i.test(wh.detail) ? ': the app does not know its own public address (set APP_URL in Railway).' : ': ' + wh.detail + '.') : '.')
                         + ' The app falls back to refreshing on a short timer, which still works.'), ['Receiving', 'Not yet', 'Off']));""",
"""                      : ('No live order events' + (wh.detail && !/unset/i.test(wh.detail) ? ': ' + wh.detail : '')
                         + '. Refreshing on a timer instead.'), ['Receiving', 'Not yet', 'Off']));""", 1),
("""                : 'Set GOOGLE_OAUTH_CLIENT_ID / SECRET and enable the Gmail API to use the Inbox tab.'));""",
"""                : 'Not set up yet. Steps in the Guide.'));""", 1),
("""!sb.configured ? 'ZETA_URL and ZETA_SYNC_TOKEN are not set, so made glass is not booked against stock.'""",
 """!sb.configured ? 'Not set up: made glass is not booked against stock.'""", 1),
("""g.connected ? 'Connected, but set GA4_PROPERTY_ID to pull traffic data.' :""",
 """g.connected ? 'Connected, but no Analytics property is chosen.' :""", 1),
("""g.connected ? 'Connected, but set GSC_SITE_URL to pull search data.' :""",
 """g.connected ? 'Connected, but no Search Console site is chosen.' :""", 1),
(""": 'Only shown inside the app. Set RESEND_API_KEY and ALERT_EMAIL_TO on Railway to get them by email.', ['On', 'In app only', 'Off']));""",
 """: 'Only shown inside the app.', ['On', 'In app only', 'Off']));""", 1),
# --- dispatch and shipping windows (copy plan, Other dialogs) ---
("""'World Options is not connected yet. Add your API key to start dispatching couriers.'""",
 """'World Options is not connected yet.'""", 1),
("""'Sizes in cm, weight in kg. Weigh the packed box: couriers re-weigh on collection and bill the difference.'""",
 """'Weigh the packed box: couriers re-weigh and bill it.'""", 2),
("""'What is in the parcel, for the customs paperwork. World Options generates the commercial invoice from these lines.'""",
 """'What is in the parcel, for customs.'""", 1),
("""            body.append(el('p', 'field-help', 'The value is declared to the courier. Insuring a parcel '
                + 'declared at zero is an argument the insurer wins, so it is worth getting right.'));""",
"""            body.append(el('p', 'field-help', 'Declared to the courier. A zero value cannot be insured.'));""", 1),
("""                card.append(el('p', 'field-help', 'Going outside the UK, so the courier needs to know '
                    + 'what is in the parcel and what it is worth. This travels with the shipment.'));""",
"""                card.append(el('p', 'field-help', 'Outside the UK: list what is in the parcel.'));""", 1),
("""            body.append(el('p', 'field-help',
                'What is coming today, and from whom, by World Options\\u2019 own collection '
                + 'reference from the booking. Their service cannot be asked what is scheduled, so '
                + 'a collection booked in their portal rather than here will not show.'));""",
"""            /* The gap stays as the line; the rest is its info button (copy
               plan, Other dialogs #7). */
            const ch = el('p', 'field-help', 'Collections booked in their portal do not show.');
            ch.append(infoButton('About collections', { title: 'Collections', body:
                'What is coming today, and from whom, by World Options\\u2019 own collection '
                + 'reference from the booking. Their service cannot be asked what is scheduled, so '
                + 'a collection booked in their portal rather than here will not show.' }));
            body.append(ch);""", 1),
("""'From your World Options web service setup. The Meter Number is required; add the Key and Password if you were given them.'""",
 """'The Meter Number is required; Key and Password optional.'""", 1),
("""'Where parcels ship from. Left blank, your Shopify store address is used.'""",
 """'Left blank, your Shopify store address is used.'""", 1),
("""'Collection window: when the courier can pick up from you. Sent with every booking.'""",
 """'When the courier can collect. Sent with every booking.'""", 1),
("""            body.append(el('div', 'section-title', 'Label printers'));
            body.append(el('p', 'field-help', 'What each printer is loaded with. '
                + 'Production labels are the gobo labels from the Production Manager; '
                + 'courier labels are the shipping labels that come back from a booking.'));""",
"""            const lpT = el('div', 'section-title', 'Label printers');
            lpT.append(infoButton('About the label printers', { title: 'Label printers', body: 'What each printer is loaded with. '
                + 'Production labels are the gobo labels from the Production Manager; '
                + 'courier labels are the shipping labels that come back from a booking.' }));
            body.append(lpT);""", 1),
("""'Used automatically when an order ships outside the UK. Your EORI number is required for exports; get one at gov.uk if you do not have one.'""",
 """'Required for exports. Get one at gov.uk.'""", 1),
("""            body.append(el('p', 'field-help',
                'Ask the EU database whether a business customer’s EORI number is real before '
                + 'you put it on an export. Nothing here is saved: it is a lookup.'));""",
"""            body.append(el('p', 'field-help', 'Checks a customer’s EORI number. Nothing is saved.'));""", 1),
("""            body.append(el('div', 'section-title', 'Collections by courier'));
            body.append(el('p', 'field-help',
                'A collection is arranged with the parcel, so this is what each courier is asked '
                + 'for when you book with them. Set the ones you have an arrangement with; the '
                + 'rest use the setting above.'));""",
"""            const cbT = el('div', 'section-title', 'Collections by courier');
            cbT.append(infoButton('About collections by courier', { title: 'Collections by courier', body:
                'A collection is arranged with the parcel, so this is what each courier is asked '
                + 'for when you book with them. Set the ones you have an arrangement with; the '
                + 'rest use the setting above.' }));
            body.append(cbT);""", 1),
("""            body.append(el('p', 'field-help', 'The parcel sizes you offer when dispatching. Dimensions in cm, '
                + 'weight in kg. Tick one to have the dispatch panel open on it; leave them all '
                + 'unticked and it opens on the first.'));""",
"""            body.append(el('p', 'field-help', 'Parcel sizes in cm and kg. Tick the default.'));""", 1),
# --- order, size rules, loans, CRM and Inbox windows ---
("""            body.append(el('div', 'section-title', 'Order note'));""",
"""            const onT = el('div', 'section-title', 'Order note');
            body.append(onT);""", 1),
("""            body.append(el('div', 'cov-note', 'This is the order note exactly as Shopify holds it, '
                + 'including the proposal link if there is one. The order tags are not editable '
                + 'here: the production queues and the chase list are both driven by them, so they '
                + 'are changed by the queue buttons instead.'));""",
"""            onT.append(infoButton('About the order note', { title: 'Order note', body: 'This is the order note exactly as Shopify holds it, '
                + 'including the proposal link if there is one. The order tags are not editable '
                + 'here: the production queues and the chase list are both driven by them, so they '
                + 'are changed by the queue buttons instead.' }));""", 1),
("""            head.append(el('h3', null, 'Size rules'));""",
"""            const srT = el('h3', null, 'Size rules');
            head.append(srT);""", 1),
("""                body.append(el('p', 'field-help',
                    'These sit on top of the size list and survive replacing it. '
                    + (canEdit ? 'Removing one puts the model back to whatever the sheet says.'
                               : 'An admin can grant you access to change them on the Team tab.')));""",
"""                if (!srT.querySelector('.info')) srT.append(infoButton('About size rules', { title: 'Size rules', body:
                    'These sit on top of the size list and survive replacing it. '
                    + (canEdit ? 'Removing one puts the model back to whatever the sheet says.'
                               : 'An admin can grant you access to change them on the Team tab.') }));""", 1),
("""                pane.append(el('div', 'field-help',
                    'Leave the customer blank and this size applies to every order. '
                    + 'Fill it in and it applies only to that customer, with the general '
                    + 'size still used for everyone else.'));""",
"""                pane.append(el('div', 'field-help', 'Leave the customer blank to apply it to every order.'));""", 1),
("""                pane.append(el('div', 'field-help',
                    'Items on this model stop counting towards size-list coverage, so it '
                    + 'will not be reported again, and their labels print no size and no CHECK. '
                    + 'It does not change anything already printed.'));""",
"""                /* The consequence stays as the line (copy plan, Other dialogs #20). */
                const ng = el('div', 'field-help', 'Its labels print no size from now on.');
                ng.append(infoButton('What this changes', { title: 'Not a gobo', body:
                    'Items on this model stop counting towards size-list coverage, so it '
                    + 'will not be reported again, and their labels print no size and no CHECK. '
                    + 'It does not change anything already printed.' }));
                pane.append(ng);""", 1),
("""            m.body.append(el('p', 'field-help',
                'A due date is optional. Without one this loan is never called late; '
                + 'it turns amber once it has been out longer than the chase threshold.'));""",
"""            m.body.append(el('p', 'field-help', 'Optional. Without one, it turns amber at the chase limit.'));""", 1),
("""            m.body.append(el('p', 'field-help', 'Lost is an outcome, not a deletion: the deal keeps its '
                + 'history and the reason feeds the Insights view.'));""",
"""            m.body.append(el('p', 'field-help', 'The deal keeps its history; the reason feeds Insights.'));""", 1),
("""            if (preset.followup) m.body.append(el('p', 'field-help',
                'That was the last open activity on this deal. A deal without a next step goes quiet, '
                + 'so schedule the next one now, or close this window if the deal is done with.'));""",
"""            if (preset.followup) m.body.append(el('p', 'field-help', 'That was the last open activity. Schedule the next one?'));""", 1),
("""            sb.append(el('div', 'disp-subhead', 'Stages'));
            sb.append(el('p', 'field-help', 'Rename the stages to your own process. Probability '
                + 'weights the pipeline value; rotting turns a deal red after sitting untouched that many days.'));""",
"""            const stT = el('div', 'disp-subhead', 'Stages');
            stT.append(infoButton('About stages', { title: 'Stages', body: 'Rename the stages to your own process. Probability '
                + 'weights the pipeline value; rotting turns a deal red after sitting untouched that many days.' }));
            sb.append(stT);""", 1),
("""            m.body.append(el('div', 'setting-sub',
                'Filters act on email as it arrives. A conversation someone is already '
                + 'holding is never re-filed underneath them. The first filter that '
                + 'matches wins, so the order here is the order they are tried.'));""",
"""            /* How filters work, word for word, behind the window title's info
               button (copy plan, Other dialogs #27). */
            const fh = m.overlay.querySelector('.modal-head h3');
            if (fh && !fh.querySelector('.info')) fh.append(infoButton('How filters work', { title: 'Filters', body:
                'Filters act on email as it arrives. A conversation someone is already '
                + 'holding is never re-filed underneath them. The first filter that '
                + 'matches wins, so the order here is the order they are tried.' }));""", 1),
("""            host.append(el('div', 'section-title', 'Email'));
            host.append(el('p', 'field-help',
                'The footer goes on the end of every email sent from here, under the sender’s '
                + 'own sign-off. Fill in the lines this shop wants on it and leave the rest '
                + 'empty; each one takes up to 200 characters. Saved replies are the '
                + 'paragraphs this shop types over and over.'));""",
"""            const emT = el('div', 'section-title', 'Email');
            emT.append(infoButton('About the footer and saved replies', { title: 'Email', body:
                'The footer goes on the end of every email sent from here, under the sender’s '
                + 'own sign-off. Fill in the lines this shop wants on it and leave the rest '
                + 'empty; each one takes up to 200 characters. Saved replies are the '
                + 'paragraphs this shop types over and over.' }));
            host.append(emT);""", 1),
("""            m.body.append(el('div', 'setting-sub',
                'A folder is a Gmail label, so it appears down the side in Gmail like any '
                + 'other. Use a slash for a folder inside a folder.'));""",
"""            m.body.append(el('div', 'setting-sub', 'A folder is a Gmail label. Use / to nest.'));""", 1),
("""            bodyL.append(el('span', 'field-help', 'Formatting, files and pictures go out as they look here, '
                + 'with your sign-off and the shop footer under them.'));""",
"""            bodyL.append(el('span', 'field-help', 'Sent as shown, with your sign-off and the footer.'));""", 1),
("""                        'Two-step sign-in is on. Keep these recovery codes somewhere safe - '
                        + 'each one gets you in once if you lose your phone, and this is the '""",
"""                        'Two-step sign-in is on. Keep these recovery codes somewhere safe: '
                        + 'each one gets you in once if you lose your phone, and this is the '""", 1),
# --- the last hand-built headers: the pages a Shopify order link opens ---
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.printer;
            const ht = el('div'); ht.append(el('h2', null, 'Production Manager'), el('p', null, 'Preparing the label for this order\\u2026'));
            hero.append(badge, ht); box.append(hero);""",
"""            const hero = pageHead({ view: 'labels', title: 'Production Manager', line: 'Preparing the label for this order\\u2026' });
            box.append(hero);""", 1),
("""            const hero = el('div', 'ov-hero'); const badge = el('div', 'badge'); badge.innerHTML = I.printer;
            const ht = el('div'); ht.append(el('h2', null, 'Production Manager'), el('p', null, 'Opening dispatch for this order\\u2026'));
            hero.append(badge, ht); box.append(hero);""",
"""            const hero = pageHead({ view: 'labels', title: 'Production Manager', line: 'Opening dispatch for this order\\u2026' });
            box.append(hero);""", 1),
("""                    + 'background:var(--surface-tertiary);border-radius:var(--radius-sm);word-break:break-all';""",
 """                    + 'background:var(--surface-tertiary);border-radius:var(--radius-control);word-break:break-all';""", 1),
("""                        + 'padding:10px 12px;background:var(--surface-tertiary);border-radius:var(--radius-sm)';""",
 """                        + 'padding:var(--sp-2-5) var(--sp-3);background:var(--surface-tertiary);border-radius:var(--radius-control)';""", 1),
]
```

- [ ] **Step 4: The rules and the last old tokens**

In the `.auth-card` rule replace `border-radius: var(--radius-xl);` with `border-radius: var(--radius-pop);` and `            box-shadow: var(--shadow-sm), var(--shadow-lg); }` with `            box-shadow: var(--shadow-pop); }` (the sign-in card floats like every window, spec 8.3; its sky tint and padding stay, as Cameron approved them on 2026-09-22).

In the rule `        ::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: var(--radius-sm); border: var(--bw-marker) solid transparent; background-clip: padding-box; }` replace `border-radius: var(--radius-sm);` with `border-radius: var(--radius-full);` (a bar's round ends).

Dialogs and toasts float as menus and popovers do (spec 8.3, Floating: the 10 corner, the pop shadow, 16 inside). Replace `        .modal { background: var(--surface-primary); border: var(--bw-hairline) solid var(--border-default); border-radius: var(--radius-card); box-shadow: var(--shadow-lg); width: 100%; max-width: 520px;` with `        .modal { background: var(--surface-primary); border: 0; border-radius: var(--radius-pop); box-shadow: var(--shadow-pop); width: 100%; max-width: 520px;`. Replace `        .modal-head h3 { margin: 0; font-size: var(--text-head); font-weight: var(--weight-medium); line-height: var(--lh-none); flex: 1; letter-spacing: normal; }` (as Task 25's sweep left it) with `        .modal-head h3 { margin: 0; font-size: var(--text-head); font-weight: var(--weight-semibold); line-height: var(--lh-control); flex: 1; letter-spacing: normal; }`. Replace:

```css
        .toast { display: flex; gap: var(--sp-2); align-items: flex-start; background: var(--surface-primary);
            border: var(--bw-hairline) solid var(--border-default); border-left: var(--bw-marker) solid var(--border-selected); border-radius: var(--radius-card);
            padding: var(--sp-3) var(--sp-3); box-shadow: var(--shadow-lg); font-size: var(--text-body); color: var(--text-primary);
```

(as Task 25's sweep left it) with:

```css
        .toast { display: flex; gap: var(--sp-2); align-items: flex-start; background: var(--surface-primary);
            border: 0; border-left: var(--bw-marker) solid var(--border-selected); border-radius: var(--radius-pop);
            padding: var(--pop-pad); box-shadow: var(--shadow-pop); font-size: var(--text-body); color: var(--text-primary);
```

Delete the comment that begins `        /* No icon beside a page title. The reference does not have one on any` (four lines) and `        .ov-hero .badge { display: none; }`, and the two-line comment `        /* No icon beside a page title: the reference does not have one on any` that Task 7 left above the rules it deleted (no screen builds a badge now).

In `:root` delete the line `            --radius-xl: 24px;   /* a surface standing alone on an empty page: the sign-in card */` and, from the primitive line Task 4 wrote, ` --radius-sm: 8px;`. Then `grep -n "radius-sm\|radius-xl" static/index.html static/composer.js` prints nothing.

- [ ] **Step 5: Update the sign-in guards**

In `t_the_sign_in_card_is_the_clean_minimal_design` replace:

```python
    for want in ("linear-gradient(to bottom, var(--auth-card-top), var(--surface-primary))",
                 "border-radius: var(--radius-xl)", "var(--shadow-lg)", "var(--auth-card-line)"):
```

with:

```python
    # Since the mix (2026-10-06) it floats like every window: the 10 corner and
    # the pop shadow, its sky tint kept.
    for want in ("linear-gradient(to bottom, var(--auth-card-top), var(--surface-primary))",
                 "border-radius: var(--radius-pop)", "var(--shadow-pop)", "var(--auth-card-line)"):
```

and in `t_the_card_elevation_token_actually_paints` replace:

```python
    ok("box-shadow: var(--shadow-sm), var(--shadow-lg);" in CSS.split(".auth-card {")[1].split("}")[0],
       "so the sign-in card keeps its float")
```

with:

```python
    ok("box-shadow: var(--shadow-pop);" in CSS.split(".auth-card {")[1].split("}")[0],
       "so the sign-in card keeps its float, the pop shadow every window wears")
```

- [ ] **Step 6: Two more guards that pinned the old sign-in**

In `t_the_dead_elevation_token_is_gone` replace `    for cls in ("lia-card", "auth-card"):` (as Task 11 left it) with `    for cls in ("lia-card",):`, and directly after that loop's `ok(...)` (it ends `".%s carries the house card elevation like every other card" % cls)`) add:

```python
    # The sign-in card floats like every window since the mix (2026-10-06).
    auth = re.search(r"\.auth-card \{[^}]*\}", HTML, re.S)
    ok(auth and "box-shadow: var(--shadow-pop)" in auth.group(0), ".auth-card carries the pop shadow, a live elevation")
```

In `t_the_login_screen_knows_a_password_is_not_always_enough` replace `    ok("recovery codes" in step, "and says what to do with a lost phone")` with `    ok("recovery code" in step, "and says what to do with a lost phone: a recovery code works too")` (copy plan, Sign-in #2 shortened the line to "Code from your authenticator app, or a recovery code.").

- [ ] **Step 7: Run the tests**

Run: `ONLY=t_windows_sign_in_and_se python3 tests/test_frontend.py && python3 tests/test_frontend.py 2>&1 | tail -1`
Expected: `1 passed, 0 failed`, then `464 passed, 0 failed`.

- [ ] **Step 8: Look at it, and audit it**

Sign out and in on the rig: the card with its 10 corner and the pop shadow, "Your own account, not Shopify’s. No account? Ask an admin.". Settings: Store profile's "Reactor reads this with every chat and report.", Auto-refresh's short line, Frequency alone, Privacy requests' info button (as an admin), the connection lines with no setting or hosting name. Dispatch an order and open New shipment, Shipping settings and Collections: each short line, the section titles' info buttons, and the warnings still there. Open a Shopify order link to the Production Manager: the one header with "Preparing the label for this order…".

Then, with the rig running:

```bash
S=/Users/cameron/Desktop/claude/gizmo/.design-rig
SIZES=1440x900,390x844 VIEWS=labels SHOTS=0 node "$S/spacing/audit.js" "$S/spacing/t44" && python3 "$S/spacing/analyse.py" "$S/spacing/t44" | grep -E "^## (Script errors|Page wider|overlaps|escapes|clipped)"
```

Expected: `## Script errors: 0`, no page wider than the screen, and `0 hits` for overlaps, escapes and clipped on these screens.

- [ ] **Step 9: Commit**

Run the release-note command, then:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Windows, sign-in and settings: short lines and info buttons, no setting or hosting names on a connection line, the last hand-built headers and old corners gone

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---

## Phase 6: Measure and ship

### Task 45: Measure every screen to zero

**Files:**
- Create: `$S/mixaudit/measure-app.js` (scratch, not committed)
- Modify: whatever the two tools find, each fix in `static/index.html` by token or base rule, with the guard test that names it
- Test: `tests/test_frontend.py` (one assertion per fix, in the guard of the part it touches)

**Interfaces:**
- Consumes: `$S/spacing/audit.js` and `$S/spacing/analyse.py` (the 165-screen audit: 33 screens at five sizes), the rig, every task before this one.
- Produces: `$S/spacing/final/` (the audit run, with shots, that Task 46's gallery is built from) and `$S/mixaudit/app/report.md`, both at zero.

- [ ] **Step 1: The measure tool, pointed at the app**

Create `$S/mixaudit/measure-app.js`:

```js
// The mix's measure tool pointed at the app (spec 10 step 5): every view in the
// rig at 1440 and 390, each run gate pressed once, checking what the 165-screen
// audit does not: text styles only from spec 4.2, text contrast, and phone
// targets under 40. node measure-app.js <outDir>
const S = '/Users/cameron/Desktop/claude/gizmo/.design-rig';
const { chromium } = require(S + '/spacing/node_modules/playwright-core');
const fs = require('fs'), path = require('path');
const BASE = 'http://127.0.0.1:8920';
const TOKEN = fs.readFileSync(path.join(S, 'rigd/long_token.txt'), 'utf8').trim();
const OUT = process.argv[2] || path.join(S, 'mixaudit', 'app');
const VIEWS = (process.env.VIEWS || 'overview,seo,keywords,products,customers,liability,recon,forecast,connector,crm,loans,mail,files,team,labels,sizes,memory,skills,chat,guide').split(',');
fs.mkdirSync(OUT, { recursive: true });
// Spec 4.2: family, size and line box. Prose (Guide articles and chat answers)
// is the one 1.6 line; a figure's line is its own size.
const ALLOWED = new Set(['Inter 11px/16px', 'Inter 12px/16px', 'Inter 13px/20px', 'Inter 14px/20px', 'Inter 15px/20px',
  'Inter 13px/20.8px', 'Inter 14px/22.4px', 'Inter 44px/44px', 'Inter 36px/36px', 'Inter 28px/28px', 'Inter 24px/24px',
  'Bricolage Grotesque 16px/20px', 'Bricolage Grotesque 26px/32px', 'Bricolage Grotesque 24px/32px']);
function measure(viewId, phone, allowed) {
  const R = document.getElementById(viewId);
  const out = { styles: {}, offStyle: [], lowc: [], small: [] };
  const vis = (e) => { const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden' || +s.opacity === 0) return false;
    const r = e.getBoundingClientRect(); return r.width > 0.5 && r.height > 0.5; };
  const own = (e) => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const txt = (e) => (e.innerText || e.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 40);
  const nm = (e) => { const p = []; for (let x = e, i = 0; x && x !== R && i < 4; x = x.parentElement, i++) { let s = x.tagName.toLowerCase(); const c = [...x.classList].slice(0, 2); if (c.length) s += '.' + c.join('.'); p.unshift(s); } return p.join(' > '); };
  const rgb = (s) => { const m = s.match(/rgba?\(([^)]+)\)/); if (!m) return null; const v = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { r: v[0], g: v[1], b: v[2], a: v.length > 3 ? v[3] : 1 }; };
  const lum = (c) => { const f = (x) => { x /= 255; return x <= .03928 ? x / 12.92 : Math.pow((x + .055) / 1.055, 2.4); }; return .2126 * f(c.r) + .7152 * f(c.g) + .0722 * f(c.b); };
  const bgOf = (el) => { const st = []; for (let e = el; e; e = e.parentElement) { const c = rgb(getComputedStyle(e).backgroundColor); if (c && c.a > 0) { st.push(c); if (c.a >= 1) break; } }
    let b = { r: 255, g: 255, b: 255 }; for (let i = st.length - 1; i >= 0; i--) { const c = st[i]; b = { r: c.r * c.a + b.r * (1 - c.a), g: c.g * c.a + b.g * (1 - c.a), b: c.b * c.a + b.b * (1 - c.a) }; } return b; };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
  for (const el of R.querySelectorAll('*')) {
    if (!vis(el)) continue;
    /* The printed label is the print's, measured by Task 34, and a chart's
       axis text is drawn in SVG at its own size. */
    if (el.closest('.label-sheet, svg, code, pre, .setup-code')) continue;
    if (own(el)) {
      const s = getComputedStyle(el);
      const k = s.fontFamily.split(',')[0].replace(/["']/g, '') + ' ' + s.fontSize + '/' + s.lineHeight;
      (out.styles[k] = out.styles[k] || []).push(txt(el));
      if (!allowed.includes(k) || ![400, 500, 600].includes(+s.fontWeight)) out.offStyle.push({ k: k + ' w' + s.fontWeight, t: txt(el), el: nm(el) });
      const c = rgb(s.color);
      if (c && el.closest('button:disabled, [aria-disabled="true"]') == null) {
        const cr = ratio(c, bgOf(el)), need = parseFloat(s.fontSize) >= 24 ? 3 : 4.5;
        if (cr < need) out.lowc.push({ t: txt(el), el: nm(el), ratio: +cr.toFixed(2), need });
      }
    }
    if (phone && el.matches('button, a[href], select, input:not([type=hidden]), [role="button"], [role="switch"], summary')) {
      const r = el.getBoundingClientRect();
      /* A link inside running text is the line's own height (WCAG 2.5.8's inline
         exception); everything else a finger presses is 40. */
      const inline = getComputedStyle(el).display === 'inline';
      if (!inline && (r.height < 39.5 || r.width < 39.5)) out.small.push({ t: txt(el), el: nm(el), w: Math.round(r.width), h: Math.round(r.height) });
    }
  }
  return out;
}
async function settle(page) {
  for (let i = 0; i < 40; i++) {
    const busy = await page.evaluate(() => !![...document.querySelectorAll('.view.active .thinking, .view.active .loader, .view.active [aria-busy="true"]')].find(e => e.offsetParent));
    if (!busy) break; await page.waitForTimeout(250);
  }
  await page.waitForTimeout(500);
}
(async () => {
  const r = await fetch(BASE + '/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + TOKEN },
    body: JSON.stringify({ username: 'cameron', password: process.env.RIG_PW || 'test-password-123' }) });
  const ses = (await r.json()).session;
  const b = await chromium.launch({ channel: 'chrome', headless: true });
  const res = [];
  for (const [w, h] of [[1440, 900], [390, 844]]) {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, reducedMotion: 'reduce' });
    await ctx.addInitScript(([t, s]) => { window.shopify = { idToken: async () => t }; try { localStorage.setItem('sc_app_session', s); } catch (e) {} }, [TOKEN, ses]);
    const p = await ctx.newPage();
    const errs = []; p.on('pageerror', e => errs.push(String(e.message).slice(0, 200)));
    await p.goto(BASE + '/?measure=' + w); await p.waitForSelector('#nav-overview', { state: 'attached' }); await p.waitForTimeout(2500);
    /* The checks run in the page as a plain function it is handed once. */
    await p.addScriptTag({ content: 'window.__mixMeasure = ' + measure.toString() + ';' });
    for (const v of VIEWS) {
      await p.evaluate((v) => document.getElementById('nav-' + v).click(), v);
      await settle(p);
      const gated = await p.evaluate(() => { const g = document.querySelector('.view.active .run-gate .btn-primary'); if (g) { g.click(); return true; } return false; });
      if (gated) await settle(p);
      const m = await p.evaluate(([id, phone, allowed]) => window.__mixMeasure(id, phone, allowed), ['view-' + v, w < 641, [...ALLOWED]])
        .catch(e => ({ error: String(e).slice(0, 200) }));
      m.view = v; m.size = w; m.errors = errs.splice(0);
      res.push(m);
    }
    await ctx.close();
  }
  await b.close();
  fs.writeFileSync(path.join(OUT, 'measure.json'), JSON.stringify(res, null, 1));
  const L = ['# The app, measured against the mix\n'];
  const tot = { off: 0, lowc: 0, small: 0, err: 0 };
  for (const m of res) {
    tot.off += (m.offStyle || []).length; tot.lowc += (m.lowc || []).length; tot.small += (m.small || []).length; tot.err += (m.errors || []).length + (m.error ? 1 : 0);
    if (!(m.offStyle || []).length && !(m.lowc || []).length && !(m.small || []).length && !(m.errors || []).length && !m.error) continue;
    L.push(`\n## ${m.view} at ${m.size}`);
    if (m.error) L.push('- measure failed: ' + m.error);
    (m.errors || []).forEach(e => L.push('- script error: ' + e));
    (m.offStyle || []).slice(0, 20).forEach(x => L.push(`- text style \`${x.k}\` "${x.t}" ${x.el}`));
    (m.lowc || []).slice(0, 20).forEach(x => L.push(`- contrast ${x.ratio}:1 (needs ${x.need}) "${x.t}" ${x.el}`));
    (m.small || []).slice(0, 20).forEach(x => L.push(`- target ${x.w}x${x.h} "${x.t}" ${x.el}`));
  }
  L.splice(1, 0, `\nScreens ${res.length}. Text styles off the list ${tot.off}; low contrast ${tot.lowc}; phone targets under 40 ${tot.small}; script errors ${tot.err}.\n`);
  fs.writeFileSync(path.join(OUT, 'report.md'), L.join('\n'));
  console.log('screens', res.length, 'off-style', tot.off, 'lowc', tot.lowc, 'small', tot.small, 'errors', tot.err);
})();
```

- [ ] **Step 2: Run both tools on the whole app**

With the rig running and the forecast posted:

```bash
S=/Users/cameron/Desktop/claude/gizmo/.design-rig
node "$S/spacing/audit.js" "$S/spacing/final" > "$S/spacing/final.log" 2>&1
python3 "$S/spacing/analyse.py" "$S/spacing/final" > "$S/spacing/final/report.md"
grep -E "^(# |[0-9]+ screens|## )" "$S/spacing/final/report.md"
node "$S/mixaudit/measure-app.js" "$S/mixaudit/app"
```

Expected from the audit: `165 screens`, `## Script errors: 0`, nothing wider than the screen, and `0 hits` under overlaps, escapes, clipped, squeezed, offgrid and rows. Expected from the measure tool: `screens 40 off-style 0 lowc 0 small 0 errors 0`.

- [ ] **Step 3: Fix what they find, one cause at a time**

For each finding, fix the cause where the value comes from, never on the one screen: a text style off the list is a rule still reading an old step (move it to `--text-body`, `--text-xs`, `--text-head` or a figure token, and its line height to the step's own); low contrast is a colour reading below ink-3 (move it to `--text-tertiary` or darker); a phone target under 40 is a control missing from Task 24's phone block (add its selector there); an overlap, escape or clip is a container that does not shrink (a `min-width: 0` on its flex child, or a wrap). Add the one assertion that pins the fix to the guard test of the part it touches (for example a selector added to the phone block is asserted in `t_every_target_on_a_phone_fits_a_finger` from Task 24), run `python3 tests/test_frontend.py 2>&1 | tail -1`, run the release-note command, and commit with the part's name and what it fixes:

```bash
git add static/index.html tests/test_frontend.py data/changelog.json
git commit -m "Measured: the phone block now covers the Inbox filter chips, found by the 165-screen audit

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(That message is the shape, for a fix of that kind: name the part, what it now does, and which tool found it.)

Run Step 2 again after each fix until both tools report zero.

- [ ] **Step 4: Compare the two mocked screens with the mockup's own numbers**

```bash
S=/Users/cameron/Desktop/claude/gizmo/.design-rig
node "$S/mixaudit/measure.js" docs/design/mix/mix.html "$S/mixaudit/mock-final"
grep -A3 "### Text styles in use" "$S/mixaudit/mock-final/report.md" | head -20
```

Open `$S/spacing/final/shots/1440-forecast.png` beside `$S/mixaudit/mock-final/forecast-desktop.png`, and `1440-labels.png` beside `production-desktop.png`, and the 390 pairs beside the phone crops: the same blocks in the same order at the same sizes, the same words, the label untouched. Every difference is either fixed (Step 3) or written down for Cameron with its reason in Task 47's message.

---

### Task 46: make check, the gallery and the release note

**Files:**
- Modify: `data/changelog.json` (the newest entry, written in full)
- Modify (scratch): `$S/gallery/reactor-screens.html` and `$S/gallery/shots/` (rebuilt from `$S/spacing/final`)
- Publish: the gallery artifact `https://claude.ai/artifact/PiCudNPLDHyUF5T8Ut4ygi`

**Interfaces:**
- Consumes: Task 45's `$S/spacing/final` run, `$S/gallery/build.py`, `$S/gallery/files3.json` (the 99 shot paths the page serves).
- Produces: a green `make check`; the gallery showing every screen before and after; the release note Cameron reads.

- [ ] **Step 1: Write the release note**

Replace the newest entry in `data/changelog.json` (the one titled "Reactor's new look" that Task 2 opened) with this, then run the release-note command so it carries today's date:

```json
  {
   "date": "2026-10-06",
   "title": "Reactor's new look",
   "items": [
    {
     "kind": "changed",
     "text": "Reactor has a new look: one white page in a dark frame, with Projected Image's teal for what is chosen and for the one main button on each screen. The sidebar is part of the dark frame, and Hide sidebar folds it away."
    },
    {
     "kind": "changed",
     "text": "Every page opens the same way: its title, at most one short line or a live status, and its actions. The explanations that used to fill the top of a page now sit behind a small info button beside the title or figure they explain, word for word, and open with a tap or the keyboard as well as a pointer."
    },
    {
     "kind": "changed",
     "text": "Forecast leads with the month: what it is expected to come to against the plan, its likely range drawn as one bar, then what has been taken and where the year lands. Cash in has a Compare methods switch and simpler ranges; Worth looking at shows each month's likely range and whether it is safely ahead, likely ahead or likely behind; the method pages sit under How it works. The forecast now calls each of its models a method."
    },
    {
     "kind": "changed",
     "text": "Production Manager shows how many orders wait in Unprocessed, To make and To ship at the top, with Complete and Custom shipments beside them. The queue, its buttons and the label print exactly as they did; an open order and its label now read as one block, and on a phone each order's buttons keep their words."
    },
    {
     "kind": "changed",
     "text": "Fewer words on every screen: about seven in ten words of explanation have gone or moved behind info buttons, an empty list says one line and offers the next step, and every warning and cost is kept."
    },
    {
     "kind": "changed",
     "text": "Charts show the day under the pointer or your finger, and the arrow keys move along them; on a phone the legend reads the day out instead of a tooltip covering the chart."
    }
   ]
  },
```

Check the words: `python3 -c "import json,re; t=json.dumps(json.load(open('data/changelog.json'))['releases'][0]); print([w for w in ('API','webhook','callback URL','JSON','Railway','gizmo','—','–') if w in t])"` prints `[]`.

- [ ] **Step 2: make check**

Run: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN make check`
Expected: the page suite ends `464 passed, 0 failed` (plus any assertions Task 45 added inside existing tests), the forecast suite passes, the sweep, SAST, extension and environment-reference checks pass, and the server suite ends `passed, 0 failed` with one more test than before Task 31.

- [ ] **Step 3: Commit the note**

```bash
git add data/changelog.json
git commit -m "Release note: Reactor's new look, the mix

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Rebuild the gallery from the final run**

```bash
S=/Users/cameron/Desktop/claude/gizmo/.design-rig
python3 "$S/gallery/build.py" "$S/spacing/final"
```

Expected: a line `N images` with N at least 90 (every screen in META.now at desktop, tablet and phone that the run shot). The page's before images stay as they are, so the gallery shows each screen before and after.

- [ ] **Step 5: Publish it to the same link**

Read the artifact first (`Artifact` with `action: "read"` and `url: "https://claude.ai/artifact/PiCudNPLDHyUF5T8Ut4ygi"`), then publish with `url` set to that link, `file_path` set to `$S/gallery/reactor-screens.html`, and `files` set to the map in `$S/gallery/files3.json` (each published path to itself, relative to `$S/gallery`, with `root` set to `$S/gallery`). Expected: the publish result names the same URL. Open it and look at Forecast and Production Manager before and after at each size.

---

### Task 47: Stop for Cameron's yes, then ship through a pull request

**Files:**
- None changed. The branch `design/brand-foundation` goes to `main` through a pull request.

**Interfaces:**
- Consumes: the green `make check` and the gallery from Task 46.
- Produces: the mix live in production.

- [ ] **Step 1: Stop and ask**

Send Cameron, in chat: the gallery link `https://claude.ai/artifact/PiCudNPLDHyUF5T8Ut4ygi`, the two zero lines from Task 45 (the audit's and the measure tool's), the label comparison from Task 34 (`1440 identical`, `390 identical`), any difference from the mockup written down in Task 45 Step 4, and the Decisions for Cameron listed near the top of this plan. Ask whether to ship. Do nothing further until Cameron says yes in chat. A no, or changes, goes back to the task that owns the part.

- [ ] **Step 2: Push the branch and open the pull request**

Only after Cameron's yes. First run the release-note command from Global Constraints: if the yes came on a later day it moves the note's date to today, which the merge day must not precede, so commit that (`git add data/changelog.json && git commit -m "Release note: dated the day it ships" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`) and run `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN make check` again. Then, with `make check` green on the branch's head:

```bash
git status --short            # nothing staged, the audit/ folder untracked and left alone
git push -u origin design/brand-foundation
gh pr create --base main --head design/brand-foundation --title "Reactor's new look: the mix" --body "$(cat <<'BODY'
Reactor's new look, as Cameron approved it in the gallery: one white sheet in an ink frame, every value from one token block, figures first with explanations behind info buttons, Forecast and Production Manager matched to the mockup, and every screen's words cut per the copy plan.

The production label, the A4 and courier sheets and the Production Manager queue's content and actions are unchanged: a guard test pins every print path, and the label was compared pixel for pixel before and after.

Measured: the 165-screen audit and the mix's measure tool both at zero; make check green.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
BODY
)"
```

Expected: a pull request URL.

- [ ] **Step 3: Bind it and let CI report**

Bind the pull request to this session with the pull request tools (`bind_pr` with its URL) and let the app's monitor report the `test`, `images` and `forecast` checks; do not poll with `gh`. If a check fails, read its log with `gh run view --log-failed`, fix the cause on the branch with its own commit, run `make check`, and push again.

- [ ] **Step 4: Merge when clean**

When the monitor reports all three checks green and `gh pr view --json mergeStateStatus -q .mergeStateStatus` prints `CLEAN`, run `gh pr merge --rebase`. The merge deploys production.

- [ ] **Step 5: Confirm the deploy**

The app's public address is the `application_url` in `shopify.app.toml` (the address the Shopify admin opens Reactor at), and `/healthz` answers `ok ` and the first twelve characters of the deployed commit:

```bash
git fetch origin && git rev-parse --short=12 origin/main
APP=$(sed -n 's|^application_url = "\(.*\)/"$|\1|p' shopify.app.toml)
curl -s "$APP/healthz"
```

Expected: `ok` followed by the same twelve characters as the first line, within a few minutes of the merge (until the deploy lands it shows the previous commit; run the `curl` again). Then tell Cameron it is live, with the commit.
