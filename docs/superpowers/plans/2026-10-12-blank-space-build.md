# Blank Space Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task by task (Cameron's agent cap leaves two agents, kept for the reviews in Task 11). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the unintentional blank space from every Reactor page, as approved in the 12 October mockups. A 1,200px page column on every page. Figures sit together. Lists become headed tables. Settings sit beside what they control. Short blocks pair up. Empty states are one line.

**Architecture:** Shared causes first.
- The page column and top bar (Task 1).
- Figure groups (Task 2).
- One table recipe (Task 3).
- Empty states (Task 4).

Each page then adopts the shared parts and has its blocks recomposed to its mockup (Tasks 5 to 9). The every-page audit runner re-measures the whole app, and the mockups are the visual reference.

**Tech Stack:** One page, `static/index.html`: tokens, CSS, and vanilla JS renderers. Server: `copilot.py` (Starlette). Tests are custom harnesses: `tests/test_frontend.py` for static CSS, HTML and script assertions, and `tests/test_dispatch.py` for the server. The rig is :8920 with `.design-rig/wide/all/core.js` (playwright).

**Spec:** `.design-rig/wide/mockups2/rules.md` (R1 to R13 and the house rules) and the approved mockups:
- `.design-rig/wide/mockups/src.html` and `notes.md`: Loan units, Reconciliation and Xero sync;
- `.design-rig/wide/mockups2/dashboards-finance/`, `operations/` and `workspace-shell/`: `src.html` and `notes.md` for the other 28 pages.

Each notes.md has, per page, the inventory (live item, where it went), the decisions, the words changed, and the server data needed. The mockups' CSS is the reference for spacing values. The audit registers (`.design-rig/wide/all/run/*/register.md`) give each finding's cause with its line numbers. Those numbers are at 04cf39f, so expect a small drift.

**Cameron's rulings, 12 October 2026 ("go ahead with your recommendations"):**
1. **Production Manager.** An opened order shows its label UNDER its row at every width, as the two-column band. The page stays at 1,200; there is no side pane and no widening.
2. **Additions:**
   - Yes to the Team day line, Activity's filter lists with counts, and the Products Stock column.
   - NO Vendor column.
   - Yes to Reconciliation's short What labels.
3. **Column headings:** on the lists, but not on the Production Manager queue.
4. **One teal per screen:**
   - Print new steps down while an order is open.
   - Reprint label is plain on custom shipments.
   - The report chat's send button is plain.
5. **Menus:** Team's admin actions go in a row ⋯ menu, and Pipedrive import goes in CRM's More menu.
6. **Settings:** "Secrets on the volume" becomes "Stored secrets".
7. **Per-page questions:** keep what the mockups drew (each notes.md, "Open" section). Also:
   - Keywords shows 15 rows with Show all.
   - Loan units has a header teal Loan out with a Unit choice, and an archive icon for Retire.
   - Requests keeps Open as its default filter.
   - Chat keeps used starters hidden.
   - What's new shows the last five releases.

## Global Constraints

**Words**
- British English.
- No em or en dashes in on-screen words or release notes.
- No setting or environment names on screen, and never "Railway" or "gizmo".
- Release notes never say API, webhook, callback URL or JSON.

**Look**
- The mix design system, as live (`docs/superpowers/specs/2026-10-06-reactor-mix-design.md`): tokens only, no literal colours or sizes in rules. New tokens go in the token tiers, and the token guard tests must pass.
- One teal (`.btn-primary`) per screen at most.
- No pills used as decoration, and no illustrations.
- Empty states are an icon tile, one line and the action.

**Frozen**
- The printed label, the A4 and courier sheets, the print document and LABEL_LOGO.
- The Production Manager's queue content, columns, statuses, actions and their order.
- The Quote Engine: never touched.

**Content**
- Customers never collect from a shop.
- Every item on a live page stays, or moves as its notes.md says. Nothing disappears silently.

**Process**
- Every app change needs a `data/changelog.json` note dated on or after the merge day.
- `make check` passes before every push. Run it with `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN`.
- Ship only via a PR, after Cameron's explicit yes on before-and-after screenshots of the real app.
- Never commit `.design-rig/`, `.superpowers/` or `audit/`.

**Widths**
- Every layout is checked at 390, 1280, 1440, 1920, 2200 and 2560: `.design-rig/wide/all/core.js` with the three cluster modules.

## Review Focus

1. **Long words in a narrow column.** A 60-character product or customer name, an unbroken email address or a long tracking number in a table column must wrap or end in an ellipsis inside its cell. It must never push the columns out of line or the page sideways. Pinned in Task 3: the recipe's text cells take `min-width: 0` and `overflow-wrap: anywhere` only on email and web cells; tested by a guard and by the `long-names` rig screen.
2. **A list with no rows, or one row.** Every converted list keeps its column heads hidden when it is empty, and shows its one-line empty state (R8). Pinned in Tasks 3 and 4: each renderer's empty branch is tested by a source assertion, and by the rig's empty screens.
3. **Big figures in a group at a laptop width.** £1,657,286 with a change chip, six figures, at 1280 with the sidebar open (container about 1,000) must wrap to a second line without clipping. Pinned in Task 2: `flex-wrap: wrap` and no `overflow: clip` on the group; tested by a guard and the 1280 rig shots.
4. **Middle widths (900 to 1280, sidebar open).** A table whose columns no longer fit becomes two-line rows by its own container width, never by sideways scroll. Pinned in Task 3: the recipe's `@container` stop, the same for every table; tested by a guard and the 1280 rig screens.
5. **Saved Customise layouts.** A person's saved layout that names a widget this build merged (Reconciliation's severity and connection, Xero sync's ledger and connection) or removed (Loan units' chasing) must still load, with the merged widget at its default place. Pinned in Task 5: `wgMergeOrder` drops unknown ids and inserts new ones; tested by a test that loads a saved layout naming the old ids.

---

### Task 1: The page column and the top bar (R1)

**Files:**
- Modify: `static/index.html`
  - the token at :310 (`--wrap: 1536px`);
  - `.topbar` at :644, and its phone override at :5135;
  - `.chat-inner` and the chat top bar.
- Test: `tests/test_frontend.py` (new test `t_one_page_column_with_the_top_bar_on_it`; update the tests that pin `--wrap: 1536px`).

**Interfaces:**
- Produces: `--wrap: 1280px` (a 1,200 column plus two 40 gutters); `--wrap-pad` unchanged.

- [ ] **Step 1: Write the guard.**
  ```python
  @test
  def t_one_page_column_with_the_top_bar_on_it():
      ok("--wrap: 1280px;" in CSS, "1,200 of content and the 40 gutters: the column the mockups drew")
      bar = CSS.split("        .topbar {")[1].split("}")[0]
      ok("padding-inline: max(var(--wrap-pad), calc((100% - var(--wrap)) / 2 + var(--wrap-pad)))" in bar,
         "the breadcrumb starts and Search ends on the page column's edges at every width")
  ```
- [ ] **Step 2: Run it and see it fail.** Run `.venv/bin/python tests/test_frontend.py 2>&1 | grep one_page_column`. Expect FAIL.
- [ ] **Step 3: Implement.**
  - Set `--wrap: 1280px`.
  - In `.topbar`, replace the side padding with `padding-inline: max(var(--wrap-pad), calc((100% - var(--wrap)) / 2 + var(--wrap-pad)))`.
  - Make Chat's top bar use the same rule, keeping its 732 reading column below.
  - Update the tests that pinned 1536.
- [ ] **Step 4: Measure.** From `.design-rig/wide/all`, run `SIZES=2200x1240 ONLY=overview,chat~start,hidden~chat node core.js clusters/<cluster>.js run/build1`. The frame shows content 1,200 and the crumbs 0 from the content edge.
- [ ] **Step 5: Commit.** `git add static/index.html tests/test_frontend.py && git commit`.

### Task 2: Figure groups and counters (R2)

**Files:**
- Modify: `static/index.html`:
  - the `.metrics`, `.stat` and `.metrics-strip` rules at about 979 to 1358;
  - `metricsStrip()` at :7110;
  - `statAct` and `.stat-act` at about 1376 to 1384;
  - `financeStat`.
- Test: `tests/test_frontend.py`: replace the 12-track pins with `t_figures_sit_together_at_their_own_width` and `t_a_filter_figure_is_a_counter_not_a_circle`.

**Interfaces:**
- Produces:
  - `.metrics.metrics-strip` is a wrapping flex group at its natural width;
  - `.stat` is `flex: none; min-width: var(--fig-min)`, with `--fig-min: 96px` added to the component tier;
  - a new `counterStat(label, value, {sev, money, on})` returns a counter button (dot, word, figure, the money beside it), the chosen one with `aria-pressed="true"` and the teal fill.

- [ ] **Step 1: Write the guards.**
  - The strip: no `repeat(12` and no `span 4` rules.
  - `.metrics.metrics-strip { display: flex; flex-wrap: wrap; ...; width: fit-content }`.
  - `.metrics-strip .stat-row` has no `container-type`.
  - On a phone (≤640), the three-figure rule is `flex: 1 1 0`.
  - Counters: no `.stat-act` circle inside a counter, and a chosen counter uses `--action-primary` as its fill with `--text-primary` words.
- [ ] **Step 2: See them fail.**
- [ ] **Step 3: Implement** to the mockup CSS: `.design-rig/wide/mockups/src.html` "figures" block, and `dashboards-finance/src.html` (figure group and counters).
  - Keep the hairline between figures (an inset `::before` on every figure but the first).
  - Phones: three short figures in one row; five as three, then two; never one figure alone.
- [ ] **Step 4: Measure** with the cluster runs for loans, connector~cameron, recon~live, seo, keywords, customers and crm~insights at 1280, 2200 and 390. Measure (a) shows no figure cell more than about 2× its content, and no flags.
- [ ] **Step 5: Commit.**

### Task 3: One table recipe (R3, R4, Review Focus 1, 2 and 4)

**Files:**
- Modify: `static/index.html`, adding a `.dtable` recipe next to `.ktable`.
- Test: `tests/test_frontend.py`: `t_lists_are_tables_whose_rows_share_columns`.

**Interfaces:**
- Produces:
  - `dtable(cols, rows, {empty, cls})`, where cols is `[{k, head, w}]` and w is a grid track such as `'minmax(12rem, 2fr)'`, `'7rem'` or `'max-content'`;
  - it returns a `div.dtable` whose `--dt-cols` is the joined tracks, with a `div.dt-head` row and `div.dt-row` rows as `grid-template-columns: subgrid`;
  - cell classes `.dt-c` (main text: name over line), `.dt-num` (right-aligned figures) and `.dt-act` (actions, fixed);
  - the empty branch returns `empty` (Task 4's line) and no head.
- Rows are hairline rows inside one list. A row's state is a leading dot, or the teal edge of an open row, never its own border (R4).
- `@container dtable (max-width: <stop>)` turns rows into two-line rows: the main cell on line 1, the rest under it. The stop is per table, passed as `--dt-stop`. Phones always use two-line rows (R13).

- [ ] **Step 1: Write the guards**:
  - the recipe exists;
  - `.dt-row` uses `subgrid`;
  - no `.dtable` rule sets `flex: 1` on a cell;
  - text cells have `min-width: 0`;
  - email and web cells alone take `overflow-wrap: anywhere`;
  - the empty branch has no head.
- [ ] **Step 2: See them fail.**
- [ ] **Step 3: Implement the recipe.** Model it on the mockups' `.tbl` (`.design-rig/wide/mockups/src.html`, "tables: one grid, rows share its columns"), using the app's own tokens.
- [ ] **Step 4: Adopt it on Loan units first**, as the proof:
  - Out now becomes Unit, With, Out, Due back, and the action.
  - The register becomes Unit, Asset tag, Status, and the actions.
  - Both follow the Loan units mockup.
- [ ] **Step 5: Measure.** Run the operations cluster's loans, loans~big and the long-names screen at all six sizes. Measure (b) shows the widest run inside a row as a headed column only; there is no sideways scroll at 1280 or 390.
- [ ] **Step 6: Commit.**

### Task 4: Empty states and run gates (R8)

**Files:**
- Modify: `static/index.html`:
  - `.empty-state` and its helpers;
  - `renderRunGate` (:10349), including its anchor line;
  - every empty branch named in the registers (Memory, Skills, Requests, Liability nothing owed, Team Work, Products no match, Reconciliation and Xero not connected).
- Modify: `copilot.py`, so the report routes return `last_run` (the time of the last completed run, from the cache that already stores it) for the gate's anchor line.
- Test: `tests/test_frontend.py` `t_an_empty_state_is_one_line_under_its_heading`; `tests/test_dispatch.py` `t_a_report_gate_knows_when_it_last_ran`.

- [ ] **Step 1: Write the guards.**
  - `.empty-state` is left-aligned, has no min-height and is not centred.
  - The action appears once.
  - The gate prints "Last run {date, time} · {coverage}" when `last_run` is set, and the coverage words alone when it is not.
- [ ] **Step 2: See them fail.**
- [ ] **Step 3: Implement**, following each page's details row in the mockups.
- [ ] **Step 4: Measure** the empty screens: no sparse-block flag.
- [ ] **Step 5: Commit.**

### Task 5: Reports and Finance pages (R6, R7, R12, Review Focus 5)

**Files:** `static/index.html`:
- `renderOverview` (10501), `renderSEO` (10591), `renderKeywords` (10779), `renderCustomers` (11061), `renderProductList` and `renderProductDetail` (11295, 11457);
- the shared cards `actionsCard` (8573), `insightCard` (8529) and `summarySection` (8644);
- the widget grid (`wgLayout`, `wgMergeOrder`);
- `renderLiability` (13115), `renderRecon` (17908), `renderConnector` (14911) and `renderForecast` (16931).

Also `copilot.py`:
- Reconciliation `open_amounts` by severity, beside `open_counts`;
- each discrepancy's `record` and `counterparty` fields, taken from what builds its title;
- the Xero document preview's contact name;
- run times, which are already sent as `finishedAt` and only need printing.

Tests: in `test_frontend.py`, one per page for its composition, as the mockups' notes list. In `test_dispatch.py`, `t_recon_reports_money_at_stake_by_severity` and `t_a_discrepancy_names_its_record_and_who_it_is_with`. Plus `t_a_saved_layout_naming_merged_widgets_still_loads`.

- [ ] **Step 1: Overview, SEO, Keywords and Customers.**
  - Summary beside What changed.
  - Actions beside the notable or findings card, with Action and Priority heads, and the rail after the text (DF-02).
  - Figures as groups.
  - Charts composed: twelve months across, then two by two, `align-items: start`.
  - Overview's four plain counts stacked beside the eight sparkline figures.
  - Traffic by channel beside Sales by sector.
  - Keywords: 15 rows with Show all; the ad spend shown once.
  - Customers: the trade radar's two tables side by side, segments as a table, and top customers as two tables of ten.
  - The report chat's send button is plain.
- [ ] **Step 2: Products.**
  - Totals beside Top products by revenue.
  - The list as a `dtable`: Product, Type, Price, Stock, Status, Units, Revenue, Change. NO Vendor.
  - Filters six by two.
  - A no-match search shows one line with Clear search and hides the empty ranking.
- [ ] **Step 3: Liability.**
  - One band: total outstanding, three counters and two figures.
  - Customers owing as a `dtable` (Customer, Owed, Overdue, Status, Orders, Oldest, Terms, Last chased).
  - The opened account in two columns: orders, and the chase email.
  - Nothing owed as one line.
- [ ] **Step 4: Reconciliation.**
  - One widget for the severity counters, with the money at stake and the sources beside them (merged in `wgMergeOrder`).
  - The sweep status line, with its time, on the tab row, and Notes (n) as a popover.
  - Discrepancies as a `dtable`: Severity, What (the 18 labels from `kind`), Record, Date, Status, Amount.
  - The opened discrepancy in two columns, with Close as an X beside its heading.
- [ ] **Step 5: Xero sync.**
  - Figures beside Connection and Auto Run (one widget).
  - Review and send: the status line, the matrix at its natural width, and Needs attention beside it.
  - The three checks on one line.
  - Runs beside the quarantine log.
  - Settings in two columns.
  - Send to Xero is the one teal.
- [ ] **Step 6: Forecast.** Why £… takes its column, and the prose windows lose `.wide`.
- [ ] **Step 7: Server fields, with their tests.**
- [ ] **Step 8: Measure** the dashboards-finance cluster at all six sizes. Compare each page to its mockup at 2200 and 390.
- [ ] **Step 9: Commit**, one commit per step group.

### Task 6: Operations pages (R3, R5, R9, R10, R13)

**Files:** `static/index.html`:
- `renderLabels` (19264), `renderCustomQueue` (19145) and `openShippingSettings`;
- `renderSizes` (17587) and `sizesDetail`;
- `renderCRM` and its tabs (24122 to 26566);
- `renderLoans` (14739) and the loan windows (14490 to 14728);
- `renderMail` (26657);
- `renderFiles` and `renderFilesBrowser` (28924, 29139).

Tests: one per page in `test_frontend.py`. The queue guards must keep passing, along with the print freeze (`LABEL_LOGO`, the print document) and the label compare.

- [ ] **Step 1: Production Manager.**
  - The queue's grid tracks give the spare width to the item line, with the name at `minmax(220px, max-content)` (OPS-10); the tracking line takes the flexible track (OPS-11).
  - Counter tiles are 128.
  - The opened order is the two-column band under its row at every width: the real label left, the repeat-customer line, size note and Print this label beside it. Remove the side pane, and let `pmPane` and its width rules go.
  - The open order's Print is the teal and Print new steps down.
  - Custom shipments' Reprint label is plain.
  - The windows lose the blank band above their first heading (OPS-15).
  - Content, columns, statuses, actions and order stay unchanged.
- [ ] **Step 2: Size list.**
  - The opened model is one compact band (OPS-16).
  - On a phone the cells are `height: auto`, so a model's details never print over the next rows. This is the OPS-17 bug; add a test first.
- [ ] **Step 3: CRM.**
  - Leads and Activities as `dtable`s.
  - Insights' figures as a group, and its charts: twelve months across, then two by two.
  - Pipedrive import as a window from the header's More menu.
  - Contacts: no empty band; selection in the head row.
- [ ] **Step 4: Loan units.**
  - Done in Task 3, plus the chase limit in Out now's head ("No due date: amber after [28] days Save").
  - The header's teal Loan out opens the Loan out window with a Unit choice, filled from the shelf units.
  - Retire uses the archive icon (unretire: archive-restore).
  - Out now's empty line, and the History window as a small table.
- [ ] **Step 5: Inbox.** The list's top bar is a head row, and Who is on today sits on one line.
- [ ] **Step 6: Files.**
  - A `dtable` (Name, Owner, Modified, Size, actions in a fixed column).
  - The storage meter on the tab row.
  - On the phone, a ••• menu for the actions.
- [ ] **Step 7: Measure** the operations cluster at all six sizes, then the print freeze and queue guards.
- [ ] **Step 8: Commit.**

### Task 7: Workspace pages and the shell (R5, R7, R9, R11, R13)

**Files:** `static/index.html`:
- `renderTeam`, `renderTeamPeople`, `renderTeamWork` and `renderTeamFeed` (30012 to 30533);
- `renderMemory` (12093) and `renderSkills` (12316);
- `renderEmptyChat` (9816);
- `renderGuide` (23376), `paintReleases` and `reqRow`;
- the Settings window (5935);
- the Customise mode parts.

- [ ] **Step 1: Team.**
  - People as a `dtable` with a two-line name cell; admin actions in a row ⋯ menu.
  - The Tabs panel's three groups side by side, with one Save.
  - Work: On the clock now and Hours per person side by side; sessions as a `dtable` with the day line (07:00 to 17:00).
  - Activity as a `dtable` (Time, Area, Who, What) with the Who and Area filter lists and their counts. Fix the person filter: it must filter on the account id `/api/team/board` sends, not `u.sub`. Add a test first.
  - The area "auth" reads Sign-in.
- [ ] **Step 2: Memory.**
  - Store knowledge as a three-column preview.
  - Tracked changes three across, each with its actions under its figures.
  - The Notes `dtable`: one kind tag, with the state tags under the note.
  - The Add a note editor capped at the note measure.
  - The empty state as one line.
- [ ] **Step 3: Skills.**
  - Two-column items: the body at its measure; the actions, use, and How Reactor reads it beside it, with no box.
  - How they are used as a band of three at the top.
  - Forms capped at 720, and uploads two across.
  - The empty state as one line.
  - A body's first heading hidden when it repeats the title.
- [ ] **Step 4: Chat.** The start screen sits in the optical middle above the box and shows six recent conversations; used starters stay hidden.
- [ ] **Step 5: Guide.**
  - Two columns from 1,000, with the print icon beside each title.
  - What's new shows the last five releases on a date rail, with New on the unread ones.
  - Requests as a `dtable` (Request, Asked by, Page, State), with Open as the default filter and a one-line empty state.
- [ ] **Step 6: The Settings window.**
  - 552 wide, with one spacing rhythm.
  - "Secrets on the volume" becomes "Stored secrets".
  - The phone's Store profile text boxes grow to fit their text (the bug).
- [ ] **Step 7: Customise mode.** The hide control on the block's first line, with no reserved band, and a grip to drag.
- [ ] **Step 8: Card and header actions (R7).** They follow the title when the content does not reach the edge.
- [ ] **Step 9: Measure** the workspace-shell cluster at all six sizes.
- [ ] **Step 10: Commit.**

### Task 8: Phones (R13)

- [ ] **Step 1.** Walk every page's 390 shot against its mockup's 390. Fix anything alone on a line it could share, targets under 40, clipped text and sideways scroll.
- [ ] **Step 2: Commit.**

### Task 9: The release note

- [ ] **Step 1.** Add a `data/changelog.json` release dated the merge day: one "changed" item per area (in plain words, no dashes) and one "fixed" item each for the Size list overlap, the Activity person filter and the Settings text boxes.

### Task 10: Prove it

- [ ] **Step 1: Run `make check`** (`env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN make check`). Page, forecast and server must all pass.
- [ ] **Step 2: Re-run the every-page audit.** Run the three clusters at all six sizes into `.design-rig/wide/all/run/after-<cluster>`, then `python3 ../audit/analyse-wide.py`. Compare against the 95 findings: each one is gone, or explained.
- [ ] **Step 3: Shoot the real pages** at 2200 and 390 beside their mockups, and update the review page (scratchpad `gallery-bs-build.py`, a third column "Built").

### Task 11: Reviews (the two agents left)

- [ ] **Step 1: One workflow, two agents in parallel.**
  - (a) A visual reviewer compares the built pages against the mockups and the rules at 2200, 1440 and 390, and lists differences.
  - (b) A code reviewer reviews the branch diff for correctness: renderer logic, empty and error branches, the Review Focus inputs, and the server fields.
- [ ] **Step 2.** Fix every confirmed finding. Re-run `make check` and the affected cluster screens.

### Task 12: Ship

- [ ] **Step 1.** Show Cameron the built pages: the review page's Built column, live beside built at 2200 and 390. Wait for his explicit yes.
- [ ] **Step 2.** On yes, push the branch and open a PR. Bind it, merge when green and CLEAN, and check that `/healthz` matches main.
