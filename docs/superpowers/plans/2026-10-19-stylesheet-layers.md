# The stylesheet in layers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A committed proof that a stylesheet change changed nothing (`make css-proof`), the tokens, element defaults and built parts in cascade layers under the screens, no styling set by the script, and the legacy class names gone; nothing on screen changes.

**Architecture:** `tests/browser/computed.js` fingerprints final styles (plain, hover forced, focus forced) through the page and CDP; `tests/browser/css-proof.spec.js` writes them only when `CSS_PROOF_OUT` is set; `tests/browser/css_proof.py` builds the base worktree, runs base once and head twice on their own ports, and compares. The layers live in `static/src/css/tokens.css` (the order and the tokens), `static/src/css/base.css` and `static/src/css/parts/*.css`, listed after `tokens.css` in the manifest.

**Tech Stack:** as the last pieces; CSS cascade layers (`@layer`), the same browser era as the nesting and `:has()` the sheet already uses; Playwright's CDP session for forced states.

**Spec:** `docs/superpowers/specs/2026-10-19-stylesheet-layers-design.md`

## Global Constraints

- No visible change: `make css-proof BASE=refactor/panels` reports no difference on any state, plain or forced.
- Frozen: print CSS and print functions byte for byte (`t_the_printed_sheets_do_not_change`); no rule under `@media print` moves.
- Browser runs on ports 8941 (main checkout) and 8942 to 8945 (worktrees); never 8930.
- A release note with the first app change; no agents (self-review); branch `refactor/stylesheet-layers` stacked on `refactor/panels`.

## Review Focus

1. **A part's hover or focus look** that a screen rule used to lose to by weight and would now win against. Pinned by the tool's forced states (Task 1) in every proof run.
2. **A rule under `@media print` or a frozen print rule moved into a layer** would change paper. Pinned by the print hash test and Task 2's guard that no layered file holds `print`.
3. **The Design page's tokens** read from the sheet: inside a layer they vanished in the spike. Pinned by Task 2's harness test of its reader and the proof (its 1,895 elements return).
4. **An inline style that beat a rule by being inline**: as a class it may lose. Pinned by the proof (Task 3) on every state; where it loses, the class takes the weight it needs.
5. **A window or state the suite does not open** (a hover inside a window, a tab no screen opens): the proof sees only measured states. Ledgered as the known limit; the moved rules are part-only selectors, so a screen's DOM cannot match them differently there.

---

### Task 1: The proof

**Files:** `tests/browser/computed.js` (create), `tests/browser/css-proof.spec.js` (create), `tests/browser/css_proof.py` (create), `tests/browser/unit/css-proof.test.js` (create), `Makefile` (`css-proof`), `tests/test_frontend.py`

**Interfaces:**
- Produces: `fingerprint(page, cdp) -> { [path: string]: string }` (path = tag and index chain from `body`; keys `path`, `path#hover`, `path#focus`; value = sorted `property:value` pairs, pseudo-elements appended); `css_proof.py --base <ref> [--keep]` exit 0 when no state differs beyond the head's own run-to-run noise, else 1 with a report.

- [ ] **Step 1: Failing tests.** Node unit test `the proof tells a real change from noise`: `compare(base, head1, head2)` on hand-made maps returns only keys where `base != head1` and `head1 == head2`, and names the differing properties; `t_css_proof_is_wired`: the spec skips unless `CSS_PROOF_OUT` is set, the Makefile has `css-proof`, the script uses ports 8941 and 8942.
- [ ] **Step 2: Build** the probe (plain pass over the active view, open windows, sidebar and top bar; forced `hover` and `focus`, `focus-visible` through `CSS.forcePseudoState` on every `button, a[href], [role=button], [role=tab], input, select, textarea, summary, [tabindex="0"]` in them, fingerprinting the control, up to 40 nodes it holds and its three nearest holders), the spec, the compare, the script and the target.
- [ ] **Step 3: Prove the proof.** `css_proof.py --base HEAD`: no difference. A throwaway one-line change to a part's hover rule in the working tree: the report names it. Undo it. **Commit.**

### Task 2: Layers under the screens

**Files:** `static/src/css/tokens.css`, `static/src/css/base.css` (create), `static/src/css/parts/{button,icon-button,link,field,switch,tick-row,row}.css` (create), the files the rules leave, `static/src/manifest.json`, `static/src/js/design-page.js`, `data/changelog.json`, `tests/test_frontend.py`

- [ ] **Step 1: Failing tests.** `t_the_stylesheet_opens_with_its_layers`: the joined `CSS` starts (after comments) with `@layer tokens, base, parts;`; `base.css` and each parts file is one `@layer` block; every selector in `base.css` names no class or id; every selector in `parts/<p>.css` uses only that part's classes; no rule outside them uses only one part's classes; no layered file contains `print`. `t_the_design_page_reads_tokens_inside_layers` (node): its token reader, given rules nested in a layer block, returns the `:root` rule.
- [ ] **Step 2: Move** with a one-off script (scratch), then by hand: the order inside each layer is the order the rules had; a block in `@media` keeps its condition. Settle each flip `make css-proof` reports (four in the spike) and ledger each. Release note ("Behind the scenes": "The app's styles are sorted into layers, so a change to one screen can no longer upset a button or a field elsewhere. Nothing looks different.").
- [ ] **Step 3: Run** the tests, the page suite, `make test-browser` (8941), `css_proof.py --base refactor/panels`: no difference. **Commit.**

### Task 3: No styling from the script

**Files:** the sections that set styling (inventory in Step 1), `static/src/css/` (the classes), `tests/test_frontend.py`

- [ ] **Step 1: Failing guard** `t_the_script_sets_no_styling`: outside the frozen print functions, every `.style.<prop> =` uses a property in the allowlist (`display`, `left`, `top`, `right`, `bottom`, `width`, `height`, `minWidth`, `maxWidth`, `minHeight`, `maxHeight`, `transform`, `translate`, `transition`, `transformOrigin`, `animationDelay`, `gridColumn`, `gridRow`, `flexBasis` when computed), no `style.cssText =`, and `style.setProperty(` only for custom properties. It lists the offenders.
- [ ] **Step 2: Move** each offender's values into a class built from the same tokens (one class per recipe, reused where the values match), named for what it is; keep values exactly. Where a value is computed (a colour from data, a width from a figure), it is a custom property set by the script and read by the class.
- [ ] **Step 3: Run** the guard, the page suite, the browser suite, the proof. **Commit.**

### Task 4: The legacy names

**Files:** `static/src/js/part-button.js`, the callers of `{ small: true }` on `textButton`, `static/src/css/` (the classes), `tests/test_frontend.py`, `docs/DESIGN.md`

- [ ] **Step 1: Failing guard** `t_the_legacy_names_are_gone`: `btn-sm`, `seclink`, `linkish`, `btn-icon` and the class `link` (as a class word) appear in no CSS rule and no script outside the frozen print functions; `textButton` has no `small` option.
- [ ] **Step 2: Rename** (`link-inline`, `link-caption`, `link-go`, `btn-square`); drop `btn-sm` and its rules after confirming each `.btn-sm` rule repeats `.btn`'s values (a rule that does not is a finding, ledgered and kept under a class that says what it is); codemod `small: true` out of `textButton` calls.
- [ ] **Step 3: Run** the guard, the page suite, the browser suite, the proof. **Commit.**

### Task 5: `DESIGN.md`, `make check`, push

- [ ] `docs/DESIGN.md`: Layers (the order, what goes where, how a part moves in), the proof (`make css-proof`), styling stays in the sheet; the renamed classes; the guard and spec lists in `t_the_design_rules_live_in_one_document`.
- [ ] `make check` (browser on 8941); the final proof against `refactor/panels`; self-review; push. The pull request follows #38.
