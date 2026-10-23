# Stock in Reactor, 3 of 4: the screens. Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Stock tab's screens in Reactor (Overview, Inventory, Reorder, Suppliers, Trends, Activity and every window they open), built test first from the approved mockups, shown to nobody until the stock sheet has moved in.

**Architecture:** One page section per tab area (`static/src/js/stock*.js`, `static/src/css/stock*.css`) on the routes plans 2a and 2b built. `stock.js` holds the shared reads, names, words and rules; each area file draws its tab and owns its windows. The Stock nav item shows only for an account with the stock tab once `stock.is_live()`, so nothing changes for anyone until plan 4's switch. The browser world gains an invented stock sheet, and every Stock screen becomes a measured state of the browser suite.

**Tech Stack:** Plain JS page sections joined by `pagesource.py`, Reactor's parts (`docs/DESIGN.md`), Python/Starlette routes, the dispatch suite, `tests/test_frontend.py`, the Playwright browser suite.

**Spec:** `docs/superpowers/specs/2026-10-22-stock-in-reactor-design.md` (sections 1, 3, 4, 5, 6, 10).

**The reference implementation:** the mockup prototype Cameron was shown on 23 Oct (the local branch `mock/stock-screens` at 418134f, never pushed), drawn by four builders and fixed after a fresh review. Each screen task ports that area's file, removes its mockup-only parts (`window.__stockInvMock`, `window.__stockDel`, the icon shim, the MOCKUP notes) and adds what the tests below ask for.

## Global Constraints

- Copy: British English; no em or en dashes in anything a person reads; never setting, hosting or environment variable names; never "Railway", "gizmo" or the stock app's own name ("the shop" if the business must be named).
- The repository is public: invented data only in code, tests, seeds and docs; no glass, supplier or person from the stock data.
- "The figures, lists, actions and the order of things on each screen stay as they are today" (spec 5), drawn with Reactor's parts and design rules (`docs/DESIGN.md`): panels on a grey page, one teal primary per screen, parts not hand-built controls, tables to their panels' edges, no pills, no illustrations, 40 px phone targets, no styling from the script.
- Paper: the production labels and every existing print function stay byte for byte (`t_the_printed_sheets_do_not_change`); the new sheets add their own print rules, and the print-rule count rises by exactly theirs (spec 10).
- Every write goes through its existing route; a refused write says why in the route's own words.
- A release note dated the merge day.

## The calls (taken at the review page's recommendations, 23 Oct)

Cameron saw the mockups (review page "Stock Tab Review") and said to keep going. These stand unless he changes them:

1. The Dashboard is called **Overview**.
2. On a phone the Overview **shows every section**.
3. Value by category is **a bar list**.
4. Workshop mode is **a switch at every width**.
5. The camera button by the search shows at **phone and tablet widths** (900 and under).
6. Edited rows have **ordinary Save buttons** (no teal).
7. Shelf labels and the purchase order carry **the black mark** (the production label's own logo).
8. Mark as ordered's reference **starts as the printed order number**.
9. The stock mapping window has **tabs by family**, opening on the first with a parked line.
10. Close quarter and start new is **an ordinary button**; its window's confirm stays red.
11. Draft order, a supplier's details, compose and every-supplier-at-once open as **windows**.
12. The stock settings are **a panel at the end of Activity**.
13. The history pages **100 at a desk, 25 on a phone**, with filters for action, person and dates.
14. Lines forecast to run out shows **the true count**.
15. **On order** is a panel at the foot of Reorder.
16. The words are **Warnings, Quarter, Lines, History, Draft order**.

## Review Focus

- **The tab before the move.** An account with the stock tab sees no Stock item until the stock sheet has moved in, and opening `#stock` before then shows nothing new. Pinned in Task 1.
- **Two people at once.** An edit or a count carrying a figure someone else changed since is refused; the row keeps the person's typing and says so. Pinned in Task 5.
- **Counting on a phone that loses signal or reloads.** Unsaved counts survive a reload; a failed save keeps them. Pinned in Task 5.
- **A label code that is a prefix of another.** "CL2" finds line 2 only, by search and by scan; an unknown code says "No line matches". Pinned in Tasks 3 and 6.
- **A phone at 390.** Every Stock screen and window reads as two-line rows with no sideways scroll and every control named. Pinned by the browser suite's measures on every state added in Tasks 4 to 9.

---

### Task 1: The Stock tab, shown only once the stock sheet has moved in

**Files:**
- Modify: `gizmo/team.py` (`TAB_KEYS` gains `"stock"` after `"sizes"`, `OPT_IN_TABS` gains `"stock"`, `_auth_me` gains `stock_live`), `gizmo/layouts.py` (`LAYOUT_VIEWS` gains `"stock"`)
- Modify: `static/src/shell.html` (nav item `nav-stock` after `nav-sizes`; `view-stock` with `stock-content`), `static/src/js/team-and-sign-in.js` (`TAB_KEYS`, `OPT_IN_TABS`, the Team picker's `NAMES` and `GROUPS`, `applyRoleChrome`), `static/src/js/widget-grid.js` (`APP_VIEWS`), `static/src/js/sidebar-groups.js` (title, `showStockView()`), `static/src/js/icons-and-formats.js` (the nav label, `I.box`), `static/src/manifest.json`
- Create: `static/src/js/stock.js` (only `showStockView()` and an empty page for now), `static/src/css/stock.css`
- Test: `tests/dispatch/stock-screens.py` (new section after `stock-ai.py` in `tests/test_dispatch.py`), `tests/test_frontend.py`

**Interfaces:**
- Produces: `me.stock_live: bool` in every `_auth_me` answer; the page's `stockLive()` (reads `teamMe.stock_live`); `showStockView()`.

- [ ] **Step 1: Write the failing tests.**
  - `t_the_stock_tab_is_opt_in_and_waits_for_the_move` (dispatch): `"stock"` in `team.TAB_KEYS` and `team.OPT_IN_TABS`, not in `DEFAULT_TABS`; `/api/team/me` (and the login answer) carry `stock_live` false with no `live_since` and true once it is set; `/api/layouts` accepts `{"view": "stock", ...}`.
  - `t_the_stock_nav_shows_only_once_moved_in` (frontend, run in node with MINIDOM): `applyRoleChrome` with `teamMe = {role: 'master', tabs: null, stock_live: false}` leaves `nav-stock` hidden; with `stock_live: true` shows it; with `tabs: ['labels'], stock_live: true` hides it.
- [ ] **Step 2:** run both; expect FAIL (no key, no element).
- [ ] **Step 3:** implement as listed. `stock_live` is `stock.is_live()` (one small file read per sign-in or state call).
- [ ] **Step 4:** run `ONLY=stock` dispatch and the whole of `tests/test_frontend.py`; the guards that list every tab (the Team picker's names, `APP_VIEWS` against the shell's views, the layouts' views) pass with Stock in them.
- [ ] **Step 5:** commit.

### Task 2: What the screens read that no route gives yet

**Files:**
- Modify: `gizmo/stock_sheet.py` (`listing()` gains `"glass_families"`), `gizmo/stock_orders.py` (`_shown()` gains `"who"`: the Reactor name of the order's `person`)
- Test: `tests/dispatch/stock-screens.py`

- [ ] **Step 1: Write the failing tests.** `t_the_stock_list_says_which_glass_is_mono_and_hm` (`listing()["glass_families"] == {"mono": ..., "hm": ...}` from the settings, `{}` when unset); `t_a_stock_order_names_who_placed_it` (an order placed by an account carries that account's name in `who`; a rebuilt order with no person carries `""`).
- [ ] **Step 2–4:** fail, implement, pass (`ONLY=stock`).
- [ ] **Step 5:** commit.

### Task 3: The browser world's stock sheet

**Files:**
- Create: `tests/browser/seed/stock.py` (run last in `tests/browser/seed/__init__.py`)
- Modify: `tests/browser/test_world.py`, `tests/browser/support.js` (`READS` learns every Stock read: `/api/stock/sheet` list and export, `/api/stock/overview` briefing, alerts, insights, trends, forecast, outlook, settings, fx, `/api/stock/orders` list, reorder and suggest, `/api/stock/quarters` list and compare, `/api/stock/history` search and item, `/api/stock/backups` list, `/api/stock/mapping` mapping and parked, `/api/stock/suppliers` list)

**Interfaces:**
- Produces: an invented, moved-in stock sheet written through `stock_store`: about 30 lines (a Mono glass "Clear Etch" in 7 sizes, an HM glass "Heavy Matt" in 3, five colours in 2 sizes, 3 rings, 4 projectors, 4 accessories, 2 written off), `glass_families` for the first two, 4 invented suppliers with contacts, two closed quarters and an open one, 90 nightly snapshots, about 60 history lines in time order (Production's uses, counts, deliveries with invoice numbers, edits), warnings in the server's own formats, 2 parked production lines and a ruling, 4 lines on order, one backup, a kept insights reading, and `live_since`.

- [ ] **Step 1: Write the failing test** `t_the_stock_sheet_is_filled` in `test_world.py`: `has("/api/stock/sheet", {"op": "list"}, "Clear Etch", "Heavy Matt", "Northbeam Optics")`, `has("/api/stock/mapping", {"op": "parked"}, "Mono|17")`, `has("/api/stock/overview", {"op": "insights"}, "health_score")`, `has("/api/stock/quarters", {"op": "list"}, "Q3 2026")`, `has("/api/stock/orders", {"op": "list"}, "PO-1027")`.
- [ ] **Step 2–4:** fail, write the seed (invented names only), pass (`$(PY) tests/browser/test_world.py`).
- [ ] **Step 5:** commit.

### Task 4: The Stock page and what its tabs share

**Files:**
- Modify: `static/src/js/stock.js`, `static/src/css/stock.css` (ported from the prototype)
- Test: `tests/test_frontend.py`, `tests/browser/screens.js`

**Interfaces:**
- Produces (every later task uses these exact names): `stockRead(route, op, body)`, `stockGet(name, route, op, body)` (keeps the promise), `stockSeen`, `stockForget(...names)`, `stockForgetAll()`, `stockSheet()`, `stockQuarters()`, `stockAlerts()`, `stockReorderList()`, `stockSettings()`, `stockLoad(host, reads, draw)`, `renderStock()`, `stockSeg`, `stockShowInventory(q)`; `stockGbp`, `stockNum`, `stockWatt`, `stockSize`, `stockSizeText`, `stockName`, `stockKeyName`, `stockLineByKey`, `stockLineCell`, `stockCode`, `stockByCode`, `stockCover`, `stockCoverTone`, `stockGroups(items, families)`, `stockSortSize`, `stockDot`; `stockWho`, `stockWhoNode`, `STOCK_ACTIONS`, `STOCK_FIELDS`, `STOCK_KINDS`, `stockWords`, `stockWarningText`, `stockChange(delta, base, fmt, tone)`, `stockSigned(delta, base, fmt)`.

- [ ] **Step 1: Write the failing tests** (frontend, the helpers run in node):
  - `t_a_stock_line_has_one_name_on_every_tab`: `stockName` gives "Clear Etch 20", "86 mm ring" (Rings, sub 86, size 64.9), "LED80 White" (projector), "Lens 30 degree"; `stockKeyName("Rings|86|64.9|")` with no sheet read gives "86 mm ring".
  - `t_stock_groups_put_mono_then_hm_glass_first`: with families `{mono: 'Clear Etch', hm: 'Heavy Matt'}` the glass groups run Clear Etch, Heavy Matt, then colours by name; projectors largest wattage first; rings in one group "Gobo rings".
  - `t_a_whole_label_code_finds_one_line`: `stockByCode(items, 'cl2')` is line 2 when lines 2 and 20 to 29 exist; a barcode matches case-insensitively; an unknown code gives null.
  - `t_a_stock_warning_says_its_line_once`: "Low stock: Glass / Heavy Matt 37.5 ~10 days left (3 on hand)" with its line in the sheet reads "Heavy Matt 37.5 ~10 days left (3 on hand)".
  - `t_a_stock_change_carries_its_sign_and_share`: `stockSigned(-1426, 12350, f)` is "-£1,426 (12%)"; `stockSigned(5, null, String)` is "+5".
  - `t_stock_people_keep_their_old_name`: `stockWho({who: 'Owen Castellano', user: 'sam'})` is `{name: 'Owen Castellano', was: 'sam'}`; `{user: 'gizmo'}` reads "Production".
  - browser state `stock` (page, laptop and phone and wide): the Stock page with its six tabs and the quarter under its title; seeded `Q4 2026`.
- [ ] **Step 2–4:** fail, port `stock.js` and `stock.css`, pass (`tests/test_frontend.py`; `make test-browser` for the state).
- [ ] **Step 5:** commit.

### Task 5: The Overview, a line's sheet and history, the stock mapping

**Files:**
- Create: `static/src/js/stock-overview.js`, `static/src/css/stock-overview.css` (ported)
- Test: `tests/test_frontend.py`, `tests/browser/screens.js`

**Interfaces:**
- Produces: `renderStockOverview(host)`, `openStockItem(item, opener)`, `openStockHistory(item, opener)`.
- Consumes: Task 4's names; `openStockReceiveOne` (Task 8) called guarded until Task 8 lands, then directly.

- [ ] **Step 1: Write the failing tests.**
  - browser states: `stock~overview` (seeded "Insights and recommendations" and the kept headline), `stock~mapping` (window), `stock~item` (window, from a Reorder soon row), `stock~item-history` (window).
  - `t_the_stock_overview_keeps_todays_order` (frontend): `renderStockOverview` appends the news, warnings, gobo production, the quarter's figures, where the value sits, currency exposure, reorder soon with dead capital, insights, in that order (source order of their builder calls).
  - `t_the_stock_mapping_opens_on_the_family_with_a_parked_line` (call 9): the window's family tabs open on the first family (Colour, HM, Mono, Ring) with a parked line.
  - `t_the_overview_shows_its_warnings_and_matching_without_news` (flaw 4.3): with an empty briefing the warnings and the gobo panel still draw.
- [ ] **Step 2–4:** fail, port and add the family tabs, pass.
- [ ] **Step 5:** commit.

### Task 6: Inventory: the list, editing, counting, adding, importing, the stock-take

**Files:**
- Create: `static/src/js/stock-inventory.js`, `static/src/css/stock-inventory.css` (ported; the icon shim becomes `I.minus`, `I.camera` and `I.clipboardCheck` in `icons-and-formats.js`)
- Test: `tests/test_frontend.py`, `tests/browser/screens.js`

**Interfaces:**
- Produces: `renderStockInventory(host)`; reads `stockInvQuery` from `stockShowInventory`.
- Consumes: `openStockReceive`, `openStockReceiveOne` (Task 8), `openStockHistory` (Task 5), `openStockScanner(onCode, opts)` (Task 7).

- [ ] **Step 1: Write the failing tests.**
  - browser states: `stock~inventory` (grouped), `stock~inventory-flat`, `stock~workshop` (workshop mode on), `stock~add-item` (window), `stock~stocktake` (window).
  - `t_saving_one_stock_row_keeps_the_others` (flaw; node with MINIDOM): two rows edited, the first saved (stand-in `api` answers), the second row's typed value and its marking survive the redraw.
  - `t_a_refused_stock_edit_keeps_the_typing` (Review Focus): `api` answers 409 with the route's words; the row keeps its edited values, is still marked, and the toast carries the words.
  - `t_unsaved_stock_counts_survive_a_reload` (Review Focus): counts kept in `localStorage` under one key, restored with "N unsaved counts restored", kept when the save fails, cleared when it succeeds.
  - `t_the_stock_row_save_is_an_ordinary_button` (call 6): the row's Save is `textButton('Save')` with no `kind`.
  - `t_the_stock_search_finds_a_whole_code_exactly`: "CL2" filters to line 2 only.
- [ ] **Step 2–4:** fail, port, pass.
- [ ] **Step 5:** commit.

### Task 7: Scanning shelf labels

**Files:**
- Create: `static/src/js/stock-scan.js` (moves `loadLabelReader`, `readLabelFrame` and `labelBeep` out of `camera-test.js`, which keeps calling them; adds `openStockScanner(onCode, opts)` and the camera help)
- Test: `tests/test_frontend.py` (`t_the_camera_test_tries_the_bundled_reader_the_buzz_and_keeping_awake` now finds the three helpers in `stock-scan.js`), `tests/browser/screens.js`
- Kept: the camera test in Settings stays until both phones' results are in; spec 1 removes it once scanning is proven on them (a later step).

**Interfaces:**
- Produces: `openStockScanner(onCode, { continuous, onClose })`: the camera window; `onCode(code)` returns `{ok, text}` for the strip; one code held still counts once every 1.4 s; the camera, the wake lock and the reader loop all stop when it closes.

- [ ] **Step 1: Write the failing tests.**
  - `t_the_stock_scanner_counts_a_held_label_once_a_beat` (node, fake clock): the same code read at 0, 0.5 and 1.5 s calls `onCode` twice.
  - `t_the_stock_scanner_lets_the_camera_go`: closing stops every track, clears the reader loop and releases the wake lock (source checks, as the camera test's).
  - `t_the_stock_scanner_helps_when_the_camera_is_refused`: the help panel's cases (inside the Shopify app, another app's browser, blocked, allowed but refused, a dismissed prompt) each give their own steps and a Try again.
  - browser state `stock~scanner-help` (phone): the help panel (the suite's Chromium refuses the camera).
- [ ] **Step 2–4:** fail, implement, pass.
- [ ] **Step 5:** commit.

### Task 8: Reorder, Suppliers and receiving

**Files:**
- Create: `static/src/js/stock-deliveries.js`, `static/src/css/stock-deliveries.css` (ported)
- Test: `tests/test_frontend.py`, `tests/browser/screens.js`

**Interfaces:**
- Produces: `renderStockReorder(host)`, `renderStockSuppliers(host)`, `openStockReceive(opener)`, `openStockReceiveOne(item, opener)`, and the `stock-changed` event after a stock-changing write.

- [ ] **Step 1: Write the failing tests.**
  - browser states: `stock~reorder`, `stock~reorder-levels`, `stock~draft-order` (window), `stock~suppliers`, `stock~supplier-edit` (window), `stock~compose` (window), `stock~suppliers-all` (window), `stock~receive` (window, the chooser), `stock~receive-delivery` (window, by hand), `stock~receive-one` (window).
  - `t_mark_as_ordered_starts_with_the_printed_number` (call 8): the reference field's first value is the draft's `PO-YYYYMMDD-HHMM`.
  - `t_a_long_stock_email_warns_before_opening` : over 1800 characters the compose window says so before the mail app opens.
  - `t_a_stock_invoice_received_twice_is_said_in_the_window`: a 409 from `receive` op `delivery` shows the route's words in the window and keeps every line.
- [ ] **Step 2–4:** fail, port, pass.
- [ ] **Step 5:** commit.

### Task 9: Trends, Compare, Activity and the stock settings

**Files:**
- Create: `static/src/js/stock-records.js`, `static/src/css/stock-records.css` (ported)
- Test: `tests/test_frontend.py`, `tests/browser/screens.js`

**Interfaces:**
- Produces: `renderStockTrends(host)`, `renderStockActivity(host)`.

- [ ] **Step 1: Write the failing tests.**
  - browser states: `stock~trends`, `stock~compare`, `stock~activity`, `stock~rename-quarter` (window), `stock~close-quarter` (window), `stock~undo-delivery` (window), `stock~restore` (window, the question unanswered).
  - `t_compare_opens_on_the_last_closed_quarter_against_now`.
  - `t_the_stock_history_pages_back_by_its_last_entry`: Show older entries asks with `before` set to the last row's id and appends.
  - `t_close_quarter_is_an_ordinary_button` (call 10).
- [ ] **Step 2–4:** fail, port, pass.
- [ ] **Step 5:** commit.

### Task 10: Paper: shelf labels and the purchase order

**Files:**
- Modify: `static/src/js/stock-inventory.js` (labels), `static/src/js/stock-deliveries.js` (purchase order), `static/src/css/stock.css` (their print rules)
- Test: `tests/test_frontend.py`

- [ ] **Step 1: Write the failing tests.**
  - `t_stock_labels_fill_an_avery_j8160`: the sheet is A4 with 3 by 7 labels of 63.5 by 38.1 mm; each carries the black mark (call 7), the swatch, the title, the category, a Code 39 barcode of its code and the code as text.
  - `t_a_stock_label_barcode_is_code_39`: `stockCode39('CL12')` draws `*CL12*` from the Code 39 table (bar and space widths of each character).
  - `t_the_purchase_order_prints_on_its_own`: printing the order hides the page and prints only the order page with the black mark.
  - `t_the_printed_sheets_do_not_change`: the existing functions keep their hashes; the print-rule count is 80 plus exactly the stock sheets' own rules, listed by selector.
- [ ] **Step 2–4:** fail, implement, pass.
- [ ] **Step 5:** commit.

### Task 11: The release

- [ ] **Step 1:** release note dated the merge day: kind `changed`, tab `null`, title `The Stock tab, ready to move in`, text `Reactor now has the stock sheet's own screens: the overview, the stock list with counting and scanning on a phone, reordering, suppliers, deliveries, trends and the history. The Stock tab appears once the stock sheet moves in; nothing changes until then.`
- [ ] **Step 2:** `make check`; a whole-branch review; fixes test first; grep the diff for anything from the real stock data; push; PR with Auto-fix and squash auto-merge.
