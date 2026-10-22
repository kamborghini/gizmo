# Stock in Reactor, plan 2a of 4: the sheet, served

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reactor's server does everything the stock app does to its own records (the stock list, counts, imports and exports, orders and deliveries, suppliers, quarters, settings, warnings, history, stock backups and the nightly snapshot) with the approved flaw fixes, a change and its history line always landing together. Nothing is visible yet.

**Architecture:** A core module `gizmo/stock.py` owns the one lock, the change journal that makes a change and its history line land together, the history index and the snapshot with its warnings. Four rule modules sit on it (`stock_sheet`, `stock_orders`, `stock_quarters`, `stock_backups`), and `gizmo/routes/stock.py` serves eight POST routes through the one door. Figures come only from `gizmo/stock_figures.py` (plan 1); stores only through `gizmo/stock_store.py` (plan 1).

**Tech Stack:** Python 3.14 standard library; Reactor's door (`gizmo/gate.py`), body kinds (`gizmo/bodies.py`), accounts (`gizmo/team.py`), clock (`gizmo/clock.py`), scheduler loop (`gizmo/scheduler.py`).

**Spec:** `docs/superpowers/specs/2026-10-22-stock-in-reactor-design.md`. Plan 1 (merged as #80) built the stores, the figures and the converter. Plan 2 is split in two for review: this plan, 2a, the sheet; then 2b, the production link moved in, the matching panel, AI and the chat tools. Plan 3 is the screens (mockups first); plan 4 the switch.

**Reference behaviour:** the stock app at `/Users/cameron/Desktop/claude/stock-copilot` commit `0310765`: `app.py` (routes), `jobs.py` (snapshots, close, import rows, backups), `static/app.js` (`rowsFromCSV`, `exportCSV`, `matchItemByCode`). Unless a task says otherwise, each operation keeps that behaviour and that response shape (the same keys), with item ids added.

## Decisions this plan makes where the spec leaves the builder a choice

1. **Two parts of plan 2.** 2a is the sheet; 2b moves the production link in and adds AI and chat. Neither changes the page.
2. **Who can call it until plan 3.** Routes live under `/api/stock/`, mapped to a tab `"stock"` in `gate._TAB_ROUTES`. The key is not added to `team.TAB_KEYS` until plan 3 adds the screens (adding it shows a box on the Team page), so until then only the master account reaches them.
3. **Nothing is written before the move.** Every write refuses with 409 "Stock has not moved into Reactor yet." until `stock_settings.json` carries `live_since` (set by plan 4's import), so nothing in production can be created ahead of the converted data. Reads answer from the empty stores. The nightly job waits for it too.
4. **A change and its history line go together** through a journal: the whole outcome (history rows with their ids, the snapshot, every store document the change touches) is written to `stock_journal.json` through the one writer first, then the history and snapshot lines are appended, then the documents written, then the journal removed. Any read or write first finishes a journal left behind; appends are skipped for ids already present, so nothing lands twice.
5. **Edits name the line by its id** and carry what the person saw: a field whose stored value no longer equals what was seen is refused with 409 and the line as it now is (the anti-goal "an edit silently lost by another person's save"). Counts carry no such check: a count is what is on the shelf now, as today.
6. **Placed orders and on-order.** An item's `on_order` always equals the sum of what is outstanding on its open order lines; placing, receiving, clearing and undoing keep it so. A restore therefore puts back every field the backup holds except `on_order`, which follows the orders kept (as the bookings are kept and re-applied), so an order placed since is not forgotten.
7. **Import parses the sheet on the server**, in the layout the stock sheet itself has, plus one optional trailing "Written off" column that export writes, so export then import changes nothing.
8. **New history wording** follows the house rules (no dashes); the parts that are read back are kept exactly: `· inv <number>` on receipts, the action names, `ordered <qty> from <supplier> · ref <reference>`. Old rows stay word for word.

## Global Constraints

- The repository is public: invented data only in code, tests, documents, PR bodies and commit messages.
- House copy rules for every string a person can read, history details included: British English, no em or en dashes, never `gizmo`, `Railway` or a setting name (`t_no_hosting_or_setting_name_reaches_a_person_from_the_server` refuses any string constant matching `\bgizmo\b`, `\bRailway\b` or an ALL_CAPS_NAME outside docstrings and log calls).
- The one door: every route is `@mcp.custom_route("/api/stock/<name>", methods=["POST"])` calling `gate._guard(request, model=<FlatBody>)` directly (never a wrapper: `tools/route_reference.py` only sees `_guard`), one flat body model per route in `gizmo/routes/stock.py`, dispatching on `op`; errors are `gate._json({"error": "<plain sentence>"}, status)`; an unexpected exception is caught, logged with `logger.exception`, and answered 500 "That could not be saved. Try again, or tell Cameron if it keeps happening."
- Every write takes `stock._lock` and goes through `stock.commit`; nothing else writes a stock store.
- Store paths are read as `stock_store.NAME`, never copied (`rooted()` rebinds them).
- Lines are named by `id` in every request; keys are kept verbatim; figures are computed with items in id order (`stock.items_in_order`).
- Gizmo sibling imports go at the bottom of a module with `# noqa: E402`; no `globals()`, no copied names, no `+ ".tmp"` or `fh.write(json.dumps` in new functions.
- New tests are `@test` functions in new dispatch sections listed in `SECTIONS` after `'stock-foundation.py'`: `'stock-sheet.py'`, `'stock-buying.py'`, `'stock-overview.py'`, `'stock-backups.py'`, each under 1,700 lines; every test name contains `stock`.
- Each new route gets an entry in `tests/caller_payloads.json` whose `source` is the test file and line that sends it, until plan 3's page replaces them; `make api-doc` and `make env-doc` are rerun.
- A release note in `data/changelog.json` dated the merge day; `make check` passes (`env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN BROWSER_PORT=8957 make check PY=<venv>`); the PR gets Auto-fix and squash auto-merge.

## Review Focus

- **Rows written by the stock app, read back.** Duplicate invoices, undoing a delivery and "since you were last here" read old history rows: their timestamps without a zone, `user` names such as the bridge's, dashes in old details, `· inv` tokens. Pinned in Tasks 6 and 7 with rows in the old format.
- **Two saves at once.** Two requests changing the same line within one second must both land or the second be refused, never one silently lost. Pinned in Tasks 1 and 3.
- **A crash between the item change and its history line.** Pinned in Task 1.
- **Lines with `|#2` keys and lines renamed since a history row was written.** Pinned in Tasks 3 and 7.
- **The biggest inputs the stock app allowed** (5,000 import rows, 500 counts, 300 order lines, 200 delivery lines, 1,000 levels): accepted up to the limit, refused with a sentence past it, never a partial write. Pinned in Tasks 3 to 6.

---

### Task 1: The core: three new stores, the lock, the journal

**Files:**
- Modify: `gizmo/stock_store.py`, `tests/dispatch/harness.py`, `tests/dispatch/stock-foundation.py` (the path count), `tests/test_dispatch.py` (`SECTIONS`), `docs/ENVIRONMENT.md`
- Create: `gizmo/stock.py`, `tests/dispatch/stock-sheet.py`

**Interfaces:**
- Consumes: plan 1's `gizmo/stock_store.py` and `gizmo/stock_figures.py`.
- Produces, in `gizmo/stock_store.py`:
  - `STOCK_ORDERS_PATH` (`/data/stock_orders.json`), `STOCK_JOURNAL_PATH` (`/data/stock_journal.json`), `STOCK_ALERTS_ARCHIVE_PATH` (`/data/stock_alerts_archive.jsonl`), each in `_paths()`/`_set_paths()` (14 paths in all).
  - `load_orders()/write_orders(doc)`: `{"orders": [order], "next_id": int}`.
  - `load_journal() -> dict | None`, `write_journal(doc)`, `clear_journal()`.
  - `append_alerts_archive(rows: list) -> None` (append-only lines).
  - `last_snapshot() -> dict | None`: the latest by `taken_at` among each snapshot file's last complete line.
  - `prune_change_snapshots(before: str) -> int`: removes `stock_snap_changes_<date>.jsonl` files whose date is before `before` (`YYYY-MM-DD`); returns how many.
  - `delete_backup(backup_id: int) -> bool`.
- Produces, in `gizmo/stock.py`:
  - `class Refused(Exception)` with `status: int` and `words: str`.
  - `_lock` (a `threading.RLock`).
  - `is_live() -> bool` (`stock_settings.json` has `live_since`).
  - `recover() -> bool`: finishes a journal left behind; True when it did.
  - `state() -> dict`: after `recover()`, `{"items", "periods", "alerts", "suppliers", "settings", "bridge", "orders"}`, each the store's document.
  - `items_in_order(items_doc) -> list[dict]` (by id).
  - `commit(st: dict, *, changed: set[str], history: list[dict] = (), snapshot: dict | None = None) -> list[int]`: assigns ids to new history rows and the snapshot, writes the journal, appends, writes each changed document, clears the journal; returns the history ids. Refuses with `Refused(409, ...)` when not live.
  - `actor(uid: str) -> dict`: `{"user": team._team_name(uid) or "Someone", "person": uid}`.
  - `history_row(actor: dict, action: str, *, item_key="", field="", old="", new="", detail="") -> dict` with `at` now in UTC.
  - `now_iso() -> str`.

- [ ] **Step 1: Write the failing tests** in the new section `tests/dispatch/stock-sheet.py`, with a helper `_stock_live(items=...)` (writes invented items, an open quarter and `live_since`) at its top:
  - `t_a_stock_change_and_its_history_line_land_together`: make `stock_store.write_items` raise once after the history append (a crash); then `stock.state()` holds the change and `read_history()` holds its line exactly once.
  - `t_a_stock_crash_before_any_append_is_finished_on_recovery`: journal written, nothing else; `recover()` is True; both the item and the line are present.
  - `t_a_stock_crash_after_every_write_is_not_applied_twice`: journal left behind after a complete change; `recover()` appends nothing new and the item is unchanged.
  - `t_two_stock_changes_at_once_both_land`: two threads each committing a different field of one line, 50 times; both fields hold their last values and the history has 100 lines with increasing ids.
  - `t_nothing_is_written_to_stock_before_the_move`: without `live_since`, `commit` raises `Refused` with status 409 and nothing is written.
  - In `stock-foundation.py`, `t_stock_files_sit_at_the_top_of_the_data_folder` now expects 14 paths.
- [ ] **Step 2: Run** `ONLY=stock` (as plan 1). Expected: FAIL, `gizmo.stock` cannot be imported.
- [ ] **Step 3: Implement** the store additions, the three harness lines, and `gizmo/stock.py`. Recovery appends a history row or snapshot only when its id is above the file's last id; documents are written whole.
- [ ] **Step 4: Run** `ONLY=stock`. Expected: all pass. Then `make env-doc` and the full dispatch suite.
- [ ] **Step 5: Commit.**

### Task 2: Snapshots, warnings raised once, and the history index

**Files:**
- Modify: `gizmo/stock.py`
- Test: `tests/dispatch/stock-sheet.py`

**Interfaces:**
- Consumes: Task 1; `stock_figures.totals_for_snapshot`, `detect_anomalies`, `current_value`.
- Produces, in `gizmo/stock.py`:
  - `take_snapshot(st: dict, reason: str, actor: dict, note: str) -> dict`: the snapshot `{taken_at, reason, by_user, note, totals, items: [{item_key, category, written_off, current, used, current_value}]}` (new snapshot lines carry no per-line id), and it raises the warnings into `st["alerts"]`. The caller passes it to `commit` with `"alerts"` in `changed`.
  - Warnings: `st["alerts"]["standing"]` maps an item key to the kind last raised for it. An item warning is raised only when its kind differs from the standing one; an item with no warning in this pass leaves `standing` (it recovered), so falling again raises again. A `large_change` warning is raised as today. Past 1,000 alerts, the oldest are appended to the archive first, then trimmed.
  - `history_index() -> object` with `rows` (file order), `by_key: dict[str, list[int]]`, `by_invoice: dict[str, list[int]]` (casefolded `detail_invoice`), `by_action: dict[str, list[int]]` (indexes into `rows`). It is kept in memory, read on from where it stopped while the file only grows, rebuilt when the file is replaced, and registered with `jsonstore.holds_in_memory` so a restore or a redact forgets it.
  - `detail_invoice(detail: str) -> str`: the stock app's `·\s*inv\s+(.*?)(?:\s*·|$)`, stripped.

- [ ] **Step 1: Write the failing tests:**
  - `t_a_stock_warning_is_raised_once_until_it_changes`: line at 10 days' cover, three snapshots: one `low_stock`; it reaches 0: one `stockout`; recovers above its level, then falls: a second `low_stock` (three alerts in all).
  - `t_stock_bookings_alone_never_raise_a_warning_again`: ten snapshots where only `current` falls by one each time, staying low: one alert.
  - `t_stock_alerts_past_the_cap_are_archived_first`: 1,005 alerts then a snapshot: the store holds 1,000 newest and the archive file the 5 (or more) oldest.
  - `t_the_stock_history_index_finds_rows_by_item_invoice_and_action`, with rows in the stock app's old format (naive time, `user` set to the bridge's name, a dash in a detail, `received 5 · inv INV-10 · 2026-05-01`): `by_invoice["inv-10"]` finds it, `by_invoice` has no `inv-1`.
  - `t_the_stock_history_index_reads_on_and_is_forgotten_on_restore`: two appends extend it without rereading the file (count the reads); after `jsonstore._drop_memory_stores()` it is rebuilt.
- [ ] **Step 2–4:** fail, implement, pass, as in Task 1.
- [ ] **Step 5: Commit.**

### Task 3: The stock list: list, edit, counts, new lines, and the route

**Files:**
- Create: `gizmo/stock_sheet.py`, `gizmo/routes/stock.py`
- Modify: `gizmo/stock.py` (field rules), `copilot.py` (import and `routes_stock.register(mcp, registry)` beside the other areas), `gizmo/gate.py` (`("/api/stock/", "stock")` in `_TAB_ROUTES`), `tests/caller_payloads.json`, `docs/API.md` (`make api-doc`)
- Test: `tests/dispatch/stock-sheet.py`

**Interfaces:**
- Produces, in `gizmo/stock.py`: `INT_FIELDS = {"start","received","used","current","reorder_point","reorder_qty"}`, `FLOAT_FIELDS = {"unit_cost","unit_cost_gbp"}`, `TEXT_FIELDS` with the stock app's caps (`category` 80, `sub_category` 120, `size` 60, `notes` 100, `supplier` 120, `currency` 8, `barcode` 64), `BOOL_FIELDS = {"written_off"}`, `EDITABLE` (their union; `on_order` is not editable), `coerce(field, value)` (the stock app's `_coerce`: integers 0 to 2,147,483,647, costs 0 to 1e9 rounded to 4 places, `""` is 0 or None, NaN and infinity refused, text cleaned of control characters and capped), `item_key(category, sub_category, size, notes) -> str`.
- Produces, in `gizmo/stock_sheet.py`:
  - `listing() -> dict`: `{"items": [item_view], "summary": compute_current, "live": bool}`, items ordered by category then sub_category, as the stock app.
  - `edit(uid, item_id: int, changes: dict, seen: dict, as_count: bool) -> dict`: `{"item", "applied", "summary"}`. A field in `changes` whose stored value differs from `seen[field]` refuses the whole edit with 409, naming the field, and returns `"item"`; a field absent from `seen` is not checked. One history line per changed field (`detail` "counted" or "manual edit"); with `as_count`, a fall in `current` adds the drop to `used` with its own line, "counted down N, recorded as usage". The key is recomputed only when category, sub_category, size or notes changed; a key another line holds refuses with 409; a changed key writes a line `field: "key"`, old and new keys, detail "renamed". One `edit` snapshot when anything changed.
  - `counts(uid, counts: list[dict], as_count: bool = True) -> dict`: at most 500 `{id, current}`; one transaction, one snapshot; the stock app's usage rule.
  - `new_item(uid, fields: dict) -> dict`: category required; key clash refused 409; id `next_id`; line `create` "new item <category> <size>"; one snapshot.
- Produces, in `gizmo/routes/stock.py`: `register(mcp, registry)`; `StockSheetBody` (`op`, `id: Id`, `changes: Fields`, `seen: Fields`, `as_count: Flag`, `counts: Records`, `fields: Fields`, `csv: Text`, `ids: Items`); route `/api/stock/sheet` with ops `list`, `edit`, `counts`, `new` (and `export`, `import_preview`, `import_apply` in Task 4), body cap 2 MB. `Refused` answers its own status and words; `ValueError` from `coerce` answers 400 with its words.

- [ ] **Step 1: Write the failing tests** (route level, as the master; a member made with `ready_user` for the gate):
  - `t_stock_edit_writes_a_history_line_per_field`.
  - `t_a_stock_edit_refuses_a_figure_someone_else_changed`: seen `current` 5, stored 4: 409, nothing written, the reply holds the line at 4.
  - `t_a_stock_count_down_is_recorded_as_usage`: as_count, 10 to 7: `used` +3 and the line "counted down 3, recorded as usage".
  - `t_a_stock_line_with_a_duplicate_key_can_be_edited`: `Glass|Blue|20||#2` edited on `current` only: 200, key unchanged.
  - `t_renaming_a_stock_line_writes_its_key_line`: changing `size` writes the `key` line; a clash with another line is 409.
  - `t_stock_counts_save_in_one_go_with_one_snapshot`: 3 counts: one snapshot, three `current` lines; 501 counts: 400, nothing written.
  - `t_a_new_stock_line_takes_the_next_id`.
  - `t_stock_refuses_bad_numbers`: NaN, `-1`, `1e10`, `true` for `current`: 400 naming the field; nothing written.
  - `t_stock_is_closed_to_an_account_without_the_tab`: a member gets 403.
- [ ] **Step 2–4:** fail, implement, pass; add the caller payloads; `make api-doc`.
- [ ] **Step 5: Commit.**

### Task 4: Import and export in the sheet's own layout (flaw 5)

**Files:**
- Modify: `gizmo/stock_sheet.py`, `gizmo/routes/stock.py`
- Test: `tests/dispatch/stock-sheet.py`

**Interfaces:**
- Produces, in `gizmo/stock_sheet.py`:
  - `read_csv(text: str) -> list[dict]`: the stock app's `parseCSV` and `rowsFromCSV`. Rows from the fourth on; column 0 empty or `Totals` skipped; columns 0 category, 1 sub_category, 2 size, 3 notes, 4 start, 5 received, 6 used, 7 current, 11 unit_cost, 12 currency, 13 supplier, 14 unit_cost_gbp, with its money, whole-number and number rules. `written_off` is column 19 when that column is present and not empty (`yes`/`no`), else "written off" in the notes. Refuses with 400 when fewer than four rows.
  - `import_preview(rows) -> dict`: a dry run of the stock app's `apply_rows`: `{"rows", "creates": [{category, sub_category, size}], "changes": [{id, name, field, from, to}]}` for every one of the thirteen fields it writes, the `|#n` de-duplication included. At most 5,000 rows.
  - `import_apply(uid, rows) -> dict`: the same changes written, a line per field (action `import`), creates with `create`, one `import` snapshot; all or nothing; `{"created", "updated_fields", "summary"}`.
  - `export_csv(ids: list) -> dict`: `{"csv", "filename": "stock_export.csv"}` for those lines, in id order: row 1 the open quarter's label, row 2 empty, row 3 the sheet's header (`Category, Colour / Type, Size, Notes, Start, Received, Used, Current, Used Value, Start Value, Current Value, Unit Cost, Currency, Supplier, Unit Cost GBP, Stock Purchased, Delivered, Invoice No, Date, Written off`), then a row per line, then a `Totals` row; a cell starting `=`, `+`, `-` or `@` is prefixed with `'`.

- [ ] **Step 1: Write the failing tests:**
  - `t_stock_export_then_import_changes_nothing`: export every line (one written off without "written off" in its notes, one `|#2`), preview the text: no creates, no changes.
  - `t_the_stock_import_preview_names_every_field`: a sheet changing supplier, currency, unit_cost and written_off on one line lists those four.
  - `t_the_original_stock_sheet_still_imports`: no column 19: written off read from the notes.
  - `t_a_stock_import_is_all_or_nothing`: one bad row: 400, nothing written; 5,001 rows: 400.
  - `t_stock_export_guards_against_spreadsheet_formulas`: a note `=SUM(A1)` exports as `'=SUM(A1)`.
- [ ] **Step 2–4:** fail, implement, pass; caller payloads.
- [ ] **Step 5: Commit.**

### Task 5: Placed orders, reordering and suppliers (flaws 2 and 7)

**Files:**
- Create: `gizmo/stock_orders.py`, `tests/dispatch/stock-buying.py`
- Modify: `gizmo/routes/stock.py`

**Interfaces:**
- Produces: an order is `{id, supplier, reference, currency, at, by, person, before_move: false, lines: [{item_id, item_key, qty, unit_cost, unit_cost_gbp, received: 0, cleared: 0, receipts: []}]}`; a line's outstanding is `qty − received − cleared`, never below 0; an order is open while any line is outstanding.
- Produces, in `gizmo/stock_orders.py`:
  - `place(uid, supplier, reference, currency, lines: list[dict]) -> dict`: at most 300 `{id, qty, unit_cost?}`, merged per line; `on_order += qty`; a line `ordered` per item, "ordered <qty> from <supplier> · ref <reference>"; one order kept; no snapshot (as today). `{"order", "ordered", "units", "items", "summary"}`.
  - `clear(uid, item_id) -> dict`: `on_order` to 0 with a line `ordered` "cleared outstanding order", every open line for the item cleared of what is outstanding.
  - `orders(open_only: bool) -> dict`: open orders first by age, then the latest 50 done.
  - `reorder() -> dict` (the port), `suggest() -> dict` (the port, with each supplier's `lead_days`), `set_levels(uid, levels)`: at most 1,000 `{id, reorder_point, reorder_qty}`, a line each "reorder level set", old and new as `point/qty`.
  - `suppliers() -> dict` (the stock app's list with `has_contact`, `due`, orphans), `save_supplier(uid, contact) -> dict` and `save_suppliers(uid, contacts) -> dict`: a field absent from the request keeps its stored value (flaw 2); email checked by the stock app's pattern, copy addresses cleaned and de-duplicated, `lead_days` 0 to 365; the history line never holds an address. `delete_supplier(uid, supplier)`.
- Routes: `/api/stock/orders` (`StockOrdersBody`: ops `place`, `clear`, `list`, `reorder`, `suggest`, `levels`) and `/api/stock/suppliers` (`StockSuppliersBody`: ops `list`, `save`, `save_all`, `delete`).

- [ ] **Step 1: Write the failing tests** in the new section `tests/dispatch/stock-buying.py`:
  - `t_placing_a_stock_order_keeps_it_and_adds_on_order`.
  - `t_on_order_always_equals_what_stock_orders_still_await`: after placing twice, clearing one line and placing again, each item's `on_order` equals its outstanding sum.
  - `t_clearing_stock_on_order_closes_its_open_lines`.
  - `t_the_stock_reorder_list_counts_what_is_on_order`.
  - `t_stock_levels_apply_in_bulk_with_a_line_each`: 1,001 levels: 400.
  - `t_saving_all_stock_suppliers_keeps_delivery_time_and_minimum_order`: save_all without `lead_days`/`min_order` keeps 7 and "100 per size".
  - `t_a_stock_supplier_address_never_reaches_the_history`.
- [ ] **Step 2–4:** fail, implement, pass; caller payloads.
- [ ] **Step 5: Commit.**

### Task 6: Receiving, matched to the order it fills

**Files:**
- Modify: `gizmo/stock_orders.py`, `gizmo/routes/stock.py`
- Test: `tests/dispatch/stock-buying.py`

**Interfaces:**
- Produces, in `gizmo/stock_orders.py`:
  - `receive_one(uid, item_id, qty, invoice_no, date, order_id=None) -> dict` and `receive_delivery(uid, lines, invoice_no, date) -> dict` (at most 200 `{id, qty, unit_cost?, update_cost?, order_id?}`): the stock app's arithmetic (current and received up, on_order down to no less than 0), its duplicate refusal through `history_index().by_invoice` (per line for one item, across the delivery's lines for a delivery, old rows included), its price rule (`unit_cost_gbp` = the price when the currency is GBP or blank, else price × `fx_rates`, with 1.0 for an unknown currency, as today), its detail formats, one snapshot; all or nothing.
  - Matching: each received quantity fills the oldest open line for that item, then the next, unless the line names `order_id` (that order first). Each fill is a receipt `{invoice, qty, at}` on the order line. The reply carries a receipt: `{received_at, by, invoice_no, lines: [{id, name, qty, orders: [{order_id, qty}]}], repriced}`.
  - `undo_delivery(uid, invoice_no) -> dict`: the stock app's rules and refusals (already undone 409, unknown 404, not enough left 409); it also puts back each line's `on_order` by what the delivery took off it and removes the delivery's receipts from the orders, so the order is outstanding again.
- Route: `/api/stock/receive` (`StockReceiveBody`: ops `one`, `delivery`, `undo`).

- [ ] **Step 1: Write the failing tests:**
  - `t_receiving_stock_refuses_an_invoice_received_twice`, including against an old stock-app history row `received 4 · inv A-7 · 2026-04-02` with a naive time.
  - `t_stock_invoice_inv_10_is_not_inv_1`.
  - `t_a_stock_delivery_fills_the_oldest_open_order`: two orders of 5 and a delivery of 7: the older filled, the newer 2.
  - `t_a_stock_delivery_line_can_name_its_order`.
  - `t_undoing_a_stock_delivery_puts_back_on_order_and_the_order`.
  - `t_a_stock_delivery_is_all_or_nothing`: one unknown line id: 404, nothing written; 201 lines: 400.
  - `t_stock_invoice_prices_update_costs_through_the_rate`: USD line at 10 with `fx_usd_gbp` 0.8: `unit_cost_gbp` 8.0; an unknown currency: 10.0.
- [ ] **Step 2–4:** fail, implement, pass; caller payloads.
- [ ] **Step 5: Commit.**

### Task 7: Quarters, settings, warnings, history, the item sheet and the outlook

**Files:**
- Create: `gizmo/stock_quarters.py`, `tests/dispatch/stock-overview.py`
- Modify: `gizmo/stock_figures.py` (the outlook), `gizmo/routes/stock.py`

**Interfaces:**
- Produces, in `gizmo/stock_figures.py`: `outlook(snapshots: list, days: int = 30) -> dict | None`: least squares of `active_value_gbp` against days since the first snapshot (from `taken_at`), `{"value_now", "per_day", "projected", "days"}`; None with fewer than 5 snapshots or under a day between first and last (flaw 8: real days, not snapshot steps). `forecast` stays the port.
- Produces, in `gizmo/stock_quarters.py`:
  - `quarters()` (open plus the last 40 closed), `rename(uid, label)`, `close(uid, new_label)` (the stock app's `close_period`: closing figures and `closing_data`, a `period_close` snapshot, every line rolled, a new quarter, the `period` line, a `period_open` snapshot; refused 409 within 60 seconds of the last close, kept in `settings.meta.last_period_close_at`), `quarter_csv(period_id) -> dict` (`{"csv", "filename"}` with the stock app's columns from `closing_data`; a quarter without a closing list is 404 "This quarter has no closing list to download."), `compare(left, right)` (`"current"` or a quarter id; `left` defaults to the last closed).
  - `settings()`, `save_settings(uid, low_stock_days, fx_usd_gbp, fx_eur_gbp)` (the stock app's clamps and its `settings: ...` line), `fx()`.
  - `alerts()` (latest 100 not dismissed), `dismiss(uid, alert_id)` (`dismissed_by` the person's name, `dismissed_person` their id).
  - `briefing(uid) -> dict` and `acknowledge(uid)`: since = the later of the person's own acknowledgement (`settings.acks[uid]`) and, for the usernames `stock_people.json` maps to them, their carried `prev_login` and the old `briefing_ack_<username>`; then the stock app's counts, value then and now, and reorder lines.
  - `history(q, action, person, item_id, start, end, before, limit) -> dict`: newest first, at most 300 a page, `before` the last id seen; each row with `who` (the account's name when `person` is set, else `user`).
  - `item_sheet(item_id) -> dict`: the line, its forecast row, its supplier's `lead_days`, and its history following its renames through `key` lines (newest 200).
  - `trends()`, `forecast()`, `outlook()`, read through a snapshot cache kept per file version and registered with `holds_in_memory`.
- Routes: `/api/stock/quarters` (`StockQuartersBody`: `list`, `rename`, `close`, `csv`, `compare`), `/api/stock/overview` (`StockOverviewBody`: `briefing`, `ack`, `alerts`, `dismiss`, `trends`, `forecast`, `outlook`, `settings`, `save_settings`, `fx`), `/api/stock/history` (`StockHistoryBody`: `search`, `item`).

- [ ] **Step 1: Write the failing tests** in the new section `tests/dispatch/stock-overview.py`:
  - `t_closing_a_stock_quarter_rolls_every_line_and_keeps_its_closing_list`; `t_a_stock_quarter_cannot_be_closed_twice_in_a_minute`.
  - `t_a_closed_stock_quarter_downloads_as_its_closing_list` (and 404 without one).
  - `t_stock_compare_any_two_quarters`.
  - `t_stock_settings_are_clamped_and_logged`: `low_stock_days` 0 gives 1, 999 gives 365; `fx_usd_gbp` 0: 400.
  - `t_since_you_were_last_here_in_stock_is_per_person_and_carries_on`: a mapped username's old acknowledgement is the start; after `ack`, the next briefing starts there.
  - `t_dismissing_a_stock_alert_records_who`.
  - `t_stock_history_search_filters_and_pages`.
  - `t_a_stock_line_history_follows_its_renames`.
  - `t_the_stock_outlook_counts_real_days`: five snapshots two days apart rising £10 a day: `per_day` 10.0, `projected` = last + 300.
- [ ] **Step 2–4:** fail, implement, pass; caller payloads.
- [ ] **Step 5: Commit.**

### Task 8: Stock backups, restore, and the nightly job (flaw 4, section 8)

**Files:**
- Create: `gizmo/stock_backups.py`, `tests/dispatch/stock-backups.py`
- Modify: `gizmo/scheduler.py` (`_scheduler_loop` calls `stock_backups.nightly_tick()` in its own `try`/`except`), `gizmo/routes/stock.py`

**Interfaces:**
- Produces, in `gizmo/stock_backups.py`:
  - `make_backup(actor: dict) -> dict`: `format: "stock-1"`, `items` (every field of every line), `suppliers`, `settings` (`meta`), `item_count`, `size_bytes`, `by`; filename `stock-YYYYmmdd-HHMMSS.json`; then retention: past the 30 newest and older than 7 days, or past 200, removed; `legacy-fernet` backups are never removed.
  - `backups()` (latest 60, without their contents), `download(backup_id) -> tuple[bytes, str]` (a `stock-1` backup as its JSON; a legacy one as its token's bytes, `.json.enc`).
  - `restore(uid, backup_id) -> dict`, master only (403 "Only the master admin can restore stock."); a `legacy-fernet` backup is refused 400 "This older backup is kept as an archive and cannot be restored here."; a safety backup first; then every field the backup holds put back on each line it holds (lines added since are left as they are), a history line per changed field (action `restore`), the suppliers and settings put back, `on_order` set to each line's outstanding on the kept orders; then each booking and day sheet in `stock_bridge.json` made after the backup's time applied again by the changes it recorded (`current_delta`/`used_delta`, `current_change`/`used_change`), each with a line; one `restore` snapshot; `{"restored", "fields", "reapplied", "safety_backup_id"}`.
  - `nightly_tick(now: datetime | None = None) -> bool`: when live and London's date differs from `settings.nightly.date`, one `scheduled` snapshot (warnings raised), one backup, change snapshots older than 30 days removed, `settings.nightly` stamped; True when it ran. After downtime it runs once, not once per missed day.
- Route: `/api/stock/backups` (`StockBackupsBody`: `list`, `make`, `download`, `restore`); download answers the file as `Response` bytes with `Content-Disposition`, as `gizmo/routes/backup.py` does.

- [ ] **Step 1: Write the failing tests:**
  - `t_a_stock_backup_holds_every_field_suppliers_and_settings`.
  - `t_restoring_stock_writes_a_line_per_changed_field_and_keeps_history`: history only grows.
  - `t_restoring_stock_reapplies_bookings_made_since`: a booking after the backup took 2: after restore `current` is the backup's minus 2.
  - `t_restoring_stock_keeps_orders_placed_since`: `on_order` follows the open order placed after the backup.
  - `t_only_the_master_restores_stock`; `t_an_old_encrypted_stock_backup_downloads_but_is_not_restored`.
  - `t_the_nightly_stock_snapshot_runs_once_a_london_day`: two ticks the same London day: one snapshot; 23:30 UTC on 30 June is the next London day.
  - `t_a_missed_stock_night_is_caught_up_once`: three days down: one snapshot.
  - `t_stock_backups_are_kept_by_count_and_age`.
  - `t_the_nightly_stock_job_waits_for_the_move`.
- [ ] **Step 2–4:** fail, implement, pass; caller payloads.
- [ ] **Step 5: Commit.**

### Task 9: The converter rebuilds the outstanding orders; the release

**Files:**
- Modify: `tools/stock_import.py`, `tools/stock_move/README.md`, `data/changelog.json`
- Test: `tests/dispatch/stock-foundation.py`

**Interfaces:**
- Produces, in `tools/stock_import.py`: `convert` writes `stock_orders.json`:
  - Reads every `ordered` history line in id order: `ordered <qty>( from <supplier>)?( · ref <reference>)?` adds an order line; `cleared outstanding order` ends what was outstanding for that item.
  - Groups lines into orders by person, supplier and reference, a line joining the group whose first line is within 60 seconds.
  - For each item, outstanding is its `on_order`, attributed to its order lines newest first (the oldest were received first); lines left with nothing outstanding are marked received.
  - What no line accounts for becomes one order per supplier with `before_move: true` (shown as "ordered before the move").
  - `prove` adds: each item's outstanding sum equals its `on_order`.

- [ ] **Step 1: Write the failing tests:**
  - `t_the_stock_converter_rebuilds_outstanding_orders_from_ordered_lines`: two lines from one request a second apart form one order; a later order for the same item partly received.
  - `t_stock_on_order_without_an_ordered_line_becomes_ordered_before_the_move`.
  - `t_the_stock_proof_checks_outstanding_orders_match_on_order`.
- [ ] **Step 2–4:** fail, implement, pass; rerun `tools/stock_move/selfcheck.py` with the stock app's Python (add `ordered` lines to its invented history first) and the July rehearsal; both exit 0.
- [ ] **Step 5: Release note** dated the merge day: kind `changed`, tab `null`, title `Behind the scenes`, text `Reactor can now keep the stock sheet itself, ready for the move: counting, orders, deliveries, quarters and stock backups, with every change recorded beside who made it. Nothing you see changes yet.`
- [ ] **Step 6:** `make check`; commit; push; PR with Auto-fix and squash auto-merge, its body without figures.
