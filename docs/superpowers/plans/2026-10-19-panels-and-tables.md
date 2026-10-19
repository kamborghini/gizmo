# Panels and tables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tables name their own cells as they are built (`dataTable()`), the panel rule lives in the stylesheet, the page-wide observer goes, the panel checks stop counting false alarms, and the report Ask panel sits in its panel.

**Architecture:** A new section `static/src/js/part-table.js` (after `js/part-row.js`) holds `dataTable`. `static/src/css/panels.css` opens with the panel selector and nests every rule that read `.panel` under it; the six such rules in other files move into it. `tests/browser/probes.js` reads the selector from the joined page.

**Tech Stack:** as the last four pieces; CSS nesting (Chrome 112+, Safari 16.5+, Firefox 117+, the same era as the `:has()` the stylesheet already relies on).

**Spec:** `docs/superpowers/specs/2026-10-19-panels-and-tables-design.md`

## Global Constraints

- Visible change only in the report pages' Ask panel (its inset, its well, its prompt).
- Frozen areas untouched; the print functions byte for byte (`t_the_printed_sheets_do_not_change`); panels stay screen only.
- The browser records may not rise; the panel record is lowered where findings fall.
- A release note with the first app change; no agents (self-review); branch `refactor/panels` stacked on `refactor/tables-rows`.

## Review Focus

1. **A table whose body is cleared and refilled** (paging, sorting, filters, Show more, Reconciliation's evidence) must name the new rows. Pinned by Task 1's harness test (`add` after `body` is emptied) and the browser check on every measured state.
2. **A cell appended to a row after `t.add(tr)`** would go unnamed. Pinned by the browser check (zero tolerance) on the measured states; every converted site adds its row last.
3. **Customise mode** adds a grip and a hide button to each block, and a pair carries them as children: they must never be panels. Pinned by Task 2's walk-against-selector check on the two Customise states.
4. **A block more than four holders deep** would lose its panel. Pinned by the same check: the probe's walk has no depth limit.
5. **The nested rules' weight**: each nested rule must weigh what it weighed with `.panel` (the selector weighs one class, as `.panel` did). Pinned by the screenshot comparison (Task 4): every state but the Ask panel's identical.

---

### Task 1: `dataTable()`

**Files:** `static/src/js/part-table.js` (create; manifest after `js/part-row.js`), the 26 table builders (alerts, crm ×3, customers ×4, design-page, forecast `fcTable`, keywords ×2, liability, loans ×2, markdown, memory, production-manager ×4, reconciliation, settings, size-list, xero-sync), `static/src/js/page-observers.js`, `data/changelog.json`, `tests/test_frontend.py`, `tests/browser/probes.js`, `tests/browser/pages.spec.js`

**Interfaces:**
- Produces: `dataTable(cols: Array<head | [head, cls]>, opts?: { cls?: string, wrap?: string }) -> { wrap, table, thead, heads: HTMLTableCellElement[], body, add(...rows: HTMLTableRowElement[]) }`; `head` is a string, a Node or null. `add` appends to `body` and names each cell: for a cell spanning one column under a head cell spanning one column, `data-h` = the head's words (whitespace collapsed), unless the cell already has one; `kt-main` when the head has it.

- [ ] **Step 1: Failing tests.** `t_a_table_names_its_cells_as_rows_are_added` (node, `MINIDOM` + `table_part()`): `dataTable(['Sector', ['Revenue', 'num'], ['Name', 'kt-main']], { cls: 'x' })` gives `wrap.className == 'ktable-wrap'`, `table.className == 'ktable x'`, three `th` with classes `''`, `num`, `kt-main`; a row of three `td` added has `data-h` Sector/Revenue/Name and `kt-main` on the third; a cell with `colSpan = 2` is not named; a cell with its own `data-h` keeps it; a null head names nothing; after `body` is emptied, a row added again is named. `t_every_table_is_built_by_the_part`: no `el('table', 'ktable` or `el('thead')` outside `js/part-table.js` (frozen print functions skipped by name); `syncTableHeads` nowhere in `SCRIPT`. Browser: `P.unnamedCells(page)` lists every visible `table.ktable` body cell whose head names it and which lacks that name; `pages.spec.js` expects `[]`.
- [ ] **Step 2: Build.** The part between `/* ---------- the table parts ----------` and `/* ---------- the table parts end ---------- */`; `table_part()` in the page suite; convert each site by hand (heads written as HTML become `cols`; CRM Contacts' selection row is prepended to `thead`; the table with no head gets `cols` of nulls, so nothing is named, as now); delete `syncTableHeads` and its call; the release note ("Panels and tables": "The Ask panel on every report sits in its panel like the rest, and its prompt fits a phone.").
- [ ] **Step 3: Run** the tests, the page suite (load the part into any harness that builds a converted table), the browser suite. **Commit.**

### Task 2: The panel rule in the stylesheet

**Files:** `static/src/css/panels.css`, `static/src/css/{skills,crm-and-updates,widget-grid,charts-and-forecast}.css` (their `.panel` rules move into `panels.css`), `static/src/js/page-observers.js`, `tests/browser/probes.js`, `tests/test_frontend.py`

- [ ] **Step 1: Failing tests.** `t_the_panel_rule_is_the_stylesheets`: `panels.css` holds `/* the panel rule */` followed by a selector naming every former skip and holder class and `.panel`, opened as a nesting block; no `.panel` outside that block anywhere in `CSS`; `syncPanels`, `panelTargets`, `PANEL_SKIP`, `PANEL_HOLD`, `MutationObserver(() =>` with `stampPass` absent from `SCRIPT`; `classList.add('panel')` absent. Browser: `measure` finds panels with the selector; its walk flags any block the walk expects that the selector misses (`bad`).
- [ ] **Step 2: Build.** Write the selector (holders to four deep); nest every rule that read `.panel` with `&`; move the six outside rules in; delete the stamp, its lists and the observer; `probes.js` reads the selector and the two lists from the joined page's CSS.
- [ ] **Step 3: Run** the tests, the page suite (re-point tests that pinned the stamp, ledgered), the browser suite: the panel record must not change. **Commit.**

### Task 3: Honest panel checks and the Ask panel

**Files:** `tests/browser/probes.js`, `static/src/css/panels.css`, `static/src/js/report-tools.js`, `tests/browser/record/panels.json`, `tests/test_frontend.py`

- [ ] **Step 1: Failing test.** `t_the_ask_panel_sits_in_its_panel`: the panel rules give `& > .pchat > .pchat-thread` no inline padding and `& > .pchat > .pchat-input` no padding on its sides, no background and no top rule; the dead `.panel.pchat` rule is gone; the prompt is `'Ask a question…'` and the `aria-label` unchanged.
- [ ] **Step 2: Build.** The two rules; the prompt; in `probes.js`, `ruled` excludes boxes (side borders), and `gaps` skips a pair of panels with a visible non-panel block between them.
- [ ] **Step 3: Run** the page suite and the browser suite: only falls. **Commit**, then `UPDATE_RECORD=1 make test-browser`, **commit** the record.

### Task 4: Proof, `DESIGN.md`, `make check`, push

- [ ] Screenshots (base `refactor/tables-rows`, head twice, noise subtracted), plus element shots of the Ask panel: only the report pages differ, only in the Ask panel.
- [ ] `docs/DESIGN.md`: Tables (`dataTable`, `dtable`), and Panels under Layout (the rule, where it lives); the guard and spec lists in `t_the_design_rules_live_in_one_document`.
- [ ] `make check`; self-review; push. The pull request waits for the five before it.
