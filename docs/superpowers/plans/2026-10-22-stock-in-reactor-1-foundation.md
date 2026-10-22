# Stock in Reactor, plan 1 of 4: the stores, the figures, and the move with its proof

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reactor can hold the stock app's complete data in its own stores, compute every stock figure exactly as the stock app does, and convert a copy of the stock app's database into those stores with a proof that nothing was lost or changed. Nothing is visible to anyone yet.

**Architecture:** Two new modules in the `gizmo` package: `gizmo/stock_store.py` (every stock store, through the one writer) and `gizmo/stock_figures.py` (pure functions, a port of the stock app's `analytics.py` over plain data). Two tools: an exporter that runs with the stock app's own Python and code against a copy of its database, writing one neutral JSON export (every table, plus the stock app's own figures computed at a pinned instant), and a converter in Reactor that turns the export into stores and proves the result.

**Tech Stack:** Python 3.14 standard library in Reactor (no new dependency); the stock app's own Python, SQLAlchemy and code for the exporter only.

**Spec:** `docs/superpowers/specs/2026-10-22-stock-in-reactor-design.md` (approved 22 Oct 2026). The later plans: 2, the server (routes, history pairing, flaw fixes, placed orders with the converter's step that rebuilds the outstanding ones, AI, the link moved in); 3, the screens (the Stock tab, counting and scanning, printing); 4, the switch.

**One departure from the spec's file layout, on purpose:** the spec sketches snapshots in a `stock_snapshots/` folder by month and backups in a `stock_backups/` folder. Reactor's backup takes only files at the top of the data folder, and the spec keeps the stock app's rule that snapshots other than the nightly one are deleted after 30 days. So nightly snapshots share one file, the others go in a file per day (deleted whole when it ages out), and each stock backup is its own top-level file. The intent, small files inside Reactor's backup, is unchanged.

## Global Constraints

- The repository is public: no stock figures, supplier names, prices, colleague names, database copies, exports or proof reports in code, tests, documents, PR bodies or commit messages. Test data is invented.
- Never copy the stock app's git history, tests or fixtures into Reactor (they hold real data). Its code may be read, and ported where a task says so.
- The stock app's reference code is `/Users/cameron/Desktop/claude/stock-copilot` at commit `0310765`. Its data model is `db.py`; its figures are `analytics.py`.
- Every store goes through `gizmo/store.py`: `_load_json_store(path, key, default)` and `_write_json_store(path, key, data, private=False)`. Append-only `.jsonl` files follow the pattern of `_archive_dispatch_rows` (`gizmo/dispatch.py:429`): open with `"a"`, one `json.dumps(row, allow_nan=False)` per line, flush and `os.fsync`.
- Every stock file sits at the top of the data folder (Reactor's backup takes only top-level `.json` and `.jsonl`). Paths are module-level constants with `/data/...` defaults read from the environment, with a line each in `tests/dispatch/harness.py`'s `os.environ.update` pointing at scratch, and `docs/ENVIRONMENT.md` regenerated with `make env-doc`.
- Every id from the stock app is kept exactly; a store's next id continues after the highest.
- Every figure equals the stock app's: the same formulas, Python's own `round`, the same rounding points.
- Timestamps are stored as ISO 8601 with an explicit UTC offset; a naive timestamp from the source is UTC.
- Tests are `@test` functions in a new dispatch-suite section `tests/dispatch/stock-foundation.py`, listed in `SECTIONS` in `tests/test_dispatch.py` just before `'runner.py'`, using the harness's `ok` and `eq`.
- Before any push: `env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_MESSAGING_TOKEN BROWSER_PORT=8957 make check PY=<a venv with requirements.txt and forecast/requirements-prophet.txt>`.
- A release note in `data/changelog.json` dated the merge day (British English, no dashes, no setting names, no hosting names), because the release-notes test counts changes under `gizmo/`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- **A torn last line in the history file** after a crash in the middle of an append: reading must skip that one line, keep every complete line, and not pause the store. Pinned in Task 1.
- **Naive timestamps** (SQLite, and the old Postgres `users.prev_login`) must be read as UTC everywhere, or a British Summer Time row moves by an hour. Pinned in Task 4.
- **Keys with a `|#2` suffix, and items renamed since a history row was written:** ids and keys are kept verbatim, and history rows keep the key they were written with. Pinned in Task 4.
- **Columns added later and NULL on older rows** (`barcode`, `supplier`, `reorder_point`, `unit_cost` and the like): the converter keeps NULL as NULL; the figures treat it exactly as the stock app does. Pinned in Task 2 and Task 4.
- **Money rounding:** Python's `round` rounds half to even on binary floats (`round(2.675, 2) == 2.67`); a port using `Decimal` or `math.floor(x * 100 + 0.5)` drifts by a penny. Pinned in Task 2.

---

### Task 1: The stock stores

**Files:**
- Create: `gizmo/stock_store.py`
- Modify: `tests/dispatch/harness.py` (the `os.environ.update` block), `tests/test_dispatch.py` (`SECTIONS`), `docs/ENVIRONMENT.md` (regenerated)
- Create: `tests/dispatch/stock-foundation.py`

**Interfaces:**
- Produces, in `gizmo/stock_store.py`:
  - Paths (environment name = constant name): `STOCK_ITEMS_PATH` (`/data/stock_items.json`), `STOCK_HISTORY_PATH` (`/data/stock_history.jsonl`), `STOCK_SNAPSHOTS_SCHEDULED_PATH` (`/data/stock_snap_scheduled.jsonl`), `STOCK_SNAPSHOTS_CHANGES_PREFIX` (`/data/stock_snap_changes_`, a file per UTC day: prefix + `YYYY-MM-DD.jsonl`), `STOCK_PERIODS_PATH` (`/data/stock_periods.json`), `STOCK_ALERTS_PATH` (`/data/stock_alerts.json`), `STOCK_SUPPLIERS_PATH` (`/data/stock_suppliers.json`, written private), `STOCK_SETTINGS_PATH` (`/data/stock_settings.json`), `STOCK_BRIDGE_PATH` (`/data/stock_bridge.json`), `STOCK_BACKUP_PREFIX` (`/data/stock_backup_`, a file per backup: prefix + `YYYYmmdd-HHMMSS.json`), `STOCK_PEOPLE_PATH` (`/data/stock_people.json`).
  - `load_items() -> dict` returning `{"items": {str(id): item_dict}, "next_id": int}`; `write_items(doc: dict) -> None`. An item dict holds exactly the stock app's `items` columns: `id, key, category, sub_category, size, notes, written_off, barcode, supplier, currency, unit_cost, unit_cost_gbp, start, received, used, current, reorder_point, reorder_qty, on_order, created_at, updated_at`.
  - `append_history(rows: list[dict]) -> list[int]`: assigns ids continuing after the highest id in the file, writes one line per row, returns the ids. A row holds the stock app's `audit_log` columns `id, at, user, action, item_key, field, old_value, new_value, detail`, plus `person` (a Reactor account id or `None`).
  - `read_history() -> list[dict]`: every complete line in file order; a line that does not parse is skipped and logged once, never fatal.
  - `append_snapshot(snap: dict) -> None` (routes a `reason == "scheduled"` snapshot to the scheduled file, any other to the day file for its `taken_at`'s UTC date) and `read_snapshots() -> list[dict]` (every snapshot from every file, ordered by `id`). A snapshot holds `id, taken_at, reason, by_user, note, totals` (a dict) and `items` (a list of the stock app's `snapshot_items` rows: `id, item_key, category, written_off, current, used, current_value`).
  - `load_periods()/write_periods(doc)`: `{"periods": [period_dict], "next_id": int}`, a period holding `id, label, opened_at, closed_at, closing_value, closing_units, closing_skus, closing_used_value, note, closing_data` (`closing_data` a list of item dicts, or `None`).
  - `load_alerts()/write_alerts(doc)`: `{"alerts": [alert_dict], "next_id": int}` with `id, at, kind, severity, message, item_key, dismissed, dismissed_by`.
  - `load_suppliers()/write_suppliers(doc)`: `{"suppliers": [contact_dict], "next_id": int}` with the stock app's `supplier_contacts` columns. Written with `private=True`.
  - `load_settings()/write_settings(doc)`: `{"meta": {key: value}}`, the stock app's `meta` rows verbatim (values are strings).
  - `load_bridge()/write_bridge(doc)`: `{"bookings": [...], "sheets": [...], "parked": [...], "aliases": [...], "next_ids": {"bookings": int, "sheets": int, "parked": int, "aliases": int}}`, each list holding its stock app table's rows (`gizmo_bookings`, `gizmo_usage_sheets`, `gizmo_parked`, `gizmo_aliases`) with JSON columns (`lines`, `applied`) decoded to lists.
  - `write_backup(backup: dict) -> str` (writes one backup file, returns its path) and `list_backups() -> list[dict]`. A backup holds `id, at, filename, size_bytes, item_count` and either `format: "legacy-fernet", token: str` (the stock app's encrypted blob, base64) or `format: "stock-1", items: [item_dict]`.
  - `load_people()/write_people(doc)`: `{"people": {old_username: reactor_account_id}}`.

- [ ] **Step 1: Write the failing tests** in `tests/dispatch/stock-foundation.py`:
  - `t_stock_stores_round_trip`: write then load each of items, periods, alerts, suppliers, settings, bridge and people with invented content; each loads back equal.
  - `t_stock_history_appends_and_numbers_after_the_highest`: `append_history` of two rows into a file whose highest id is 41 returns `[42, 43]`; `read_history()` returns all three in order.
  - `t_a_torn_history_line_is_skipped_not_fatal`: a file of two good lines and a third cut off mid-object reads as the two good lines; a further `append_history` succeeds and the next read has three rows.
  - `t_snapshots_go_to_their_files`: a `scheduled` snapshot lands in `STOCK_SNAPSHOTS_SCHEDULED_PATH`; an `edit` snapshot taken at `2026-10-22T23:30:00+00:00` lands in the `2026-10-22` day file; `read_snapshots()` returns both, ordered by id.
  - `t_stock_suppliers_are_owner_only`: after `write_suppliers`, `os.stat(path).st_mode & 0o777 == 0o600`.
  - `t_stock_files_sit_at_the_top_of_the_data_folder`: every path constant's directory equals the data folder's (`os.path.dirname(scheduler.SCHEDULE_PATH)` under the harness).
- [ ] **Step 2: Add the section** to `SECTIONS` before `'runner.py'`, and the eleven path lines to the harness's `os.environ.update` (pointing at `SCRATCH + "/stock_items.json"` and so on). Run `ONLY=stock python tests/test_dispatch.py`; expected FAIL: `gizmo.stock_store` cannot be imported.
- [ ] **Step 3: Implement `gizmo/stock_store.py`** with the interface above. One `asyncio`-free module; the append opens with `"a"`, writes, flushes and fsyncs; `read_history` and `read_snapshots` use `json.loads` per line inside `try` and skip a bad line with one `logger.warning` per file per process.
- [ ] **Step 4: Run** `ONLY=stock python tests/test_dispatch.py`. Expected: 6 passed.
- [ ] **Step 5: Regenerate** `docs/ENVIRONMENT.md` with `make env-doc` and check `python tools/env_reference.py --check` passes.
- [ ] **Step 6: Commit** `gizmo/stock_store.py`, the test section, the harness, `tests/test_dispatch.py`, `docs/ENVIRONMENT.md`.

### Task 2: The figures, ported

**Files:**
- Create: `gizmo/stock_figures.py`
- Test: `tests/dispatch/stock-foundation.py`

**Interfaces:**
- Consumes: item dicts, snapshot dicts, period dicts and the meta dict from Task 1.
- Produces, in `gizmo/stock_figures.py`, a port of `/Users/cameron/Desktop/claude/stock-copilot/analytics.py` function by function, each taking plain data instead of a session and returning exactly the dict the stock app's function returns (the same keys, nesting, ordering of lists and values):
  - `compute_current(items: list[dict], meta: dict) -> dict`
  - `reorder_suggestions(items: list[dict]) -> dict`
  - `suggest_reorder_points(items: list[dict], lead_by_supplier: dict[str, int] | None = None) -> dict`
  - `fx_rates(items: list[dict], meta: dict) -> dict`
  - `fx_revaluation(items: list[dict], meta: dict) -> dict`
  - `totals_for_snapshot(items: list[dict]) -> dict`
  - `trends(snapshots: list[dict], limit: int = 365) -> dict`
  - `forecast(items: list[dict], snapshots: list[dict], now: datetime) -> dict` (the stock app reads `now_utc()`; the port takes it)
  - `detect_anomalies(items: list[dict], meta: dict, prev_totals: dict | None) -> list[dict]`
  - `compare(left: dict, right: dict) -> dict`, where each side is the stock app's resolved side (its `_side` result): build it with `side_live(items: list[dict]) -> dict` and `side_period(period: dict) -> dict`.
  - Item-level helpers matching the stock app's computed columns: `item_name(item)`, `current_value(item)`, `used_value(item)`, `start_value(item)`.

- [ ] **Step 1: Write the failing tests**, each with invented items:
  - `t_a_written_off_line_is_worth_nothing`: `current_value({"current": 3, "unit_cost_gbp": 2.5, "written_off": True}) == 0` and `== 7.5` when not written off.
  - `t_money_rounds_as_python_rounds`: `current_value({"current": 1, "unit_cost_gbp": 2.675, "written_off": False}) == 2.67`.
  - `t_sell_through_and_dead_stock`: three active lines (start 10 used 5; start 10 used 0 value above 0; start 0 used 0) and one written off; `compute_current(...)` gives sell-through `25.0` (5 / 20 × 100) and lists exactly the second line as dead stock.
  - `t_a_line_is_reordered_at_its_point`: a line with `reorder_point 10, current 6, on_order 4` is listed; `current 6, on_order 5` is not; with no `reorder_qty` the quantity is `max(2 × 10 − 6, 10) == 14`; supplier `""` is grouped as `"Unknown"`.
  - `t_suggested_levels_cover_the_lead_time`: `used 90` (one a day), supplier lead 7: point `max(1, ceil(1 × 21)) == 21`, quantity `max(21, ceil(1 × 90)) == 90`; no lead time: cover 21 days, point 21; a quantity of 13 rounds up to 20.
  - `t_null_columns_count_as_the_stock_app_counts_them`: an item with `current 6, reorder_point 10, reorder_qty 0, on_order None, unit_cost None, unit_cost_gbp None` is listed by `reorder_suggestions` with `on_order 0`, `suggested_qty 14` and `order_value_gbp 0.0`, and `current_value` of it is `0`.
  - `t_days_to_stockout_by_history_or_run_rate`: two snapshots ten days apart where current falls from 30 to 20: velocity 1.0 a day, 20 days left, basis `"history"`; with one snapshot, velocity `used / 90`.
  - `t_low_stock_alert_uses_the_days_setting`: `meta {"low_stock_days": "21"}`, `current 10, used 90` (one a day, 10 days of cover): one warning; `current 30`: none; `current 0, used 5`: a stock-out warning; `current -1`: a critical anomaly.
- [ ] **Step 2: Run** `ONLY=stock python tests/test_dispatch.py`. Expected: the new tests FAIL (no module).
- [ ] **Step 3: Implement `gizmo/stock_figures.py`** by porting `analytics.py` line for line: replace each `session.scalars(select(Item)...)` with the list given, each `meta_get(session, k, d)` with `meta.get(k, d)`, each `now_utc()` with the `now` argument; keep every rounding call, comparison and ordering as written. Import nothing from the app beyond the standard library.
- [ ] **Step 4: Run** `ONLY=stock python tests/test_dispatch.py`. Expected: all pass.
- [ ] **Step 5: Commit** `gizmo/stock_figures.py` and the tests.

### Task 3: The exporter

**Files:**
- Create: `tools/stock_move/export_from_stock_app.py`, `tools/stock_move/README.md`

**Interfaces:**
- Produces the export file read by Task 4: `{"format": "stock-export-1", "exported_at": iso, "now": iso, "source_head": str, "tables": {table: {"columns": [name], "count": int, "rows": [row], "missing": bool}}, "expected": {...}}`.
  - Tables: `items, snapshots, snapshot_items, audit_log, alerts, backups, meta, periods, users, gizmo_bookings, gizmo_usage_sheets, gizmo_parked, gizmo_aliases, supplier_contacts`. A table absent from an older database is `{"columns": [], "count": 0, "rows": [], "missing": true}`.
  - Rows in primary-key order; every column the database holds; `datetime` as ISO 8601 with offset (a naive value is UTC); `bytes` as base64; JSON-in-text columns left as the text they are; `users.password_hash` omitted (logins are not carried over).
  - `count` from `SELECT COUNT(*)`, independent of the rows written.
  - `expected`: with `analytics.now_utc` pinned to `now`, the stock app's own `compute_current`, `reorder_suggestions`, `suggest_reorder_points` (with the lead times read from `supplier_contacts`, as `app.py` passes them), `fx_rates`, `fx_revaluation`, `totals_for_snapshot`, `trends`, `forecast`, `detect_anomalies` (with the latest snapshot's totals as `prev_totals`), and `compare` for live against every closed period and for each closed period against the one before it.
- CLI: `<stock app python> tools/stock_move/export_from_stock_app.py --stock-app PATH --database-url URL --out FILE [--now ISO]`. It never writes to the database (it opens a session and only reads), and refuses an `--out` inside any git working tree.

- [ ] **Step 1: Write the README**: what the exporter is for, that it runs with the stock app's own Python, that the export holds real data and must never be committed or left inside a repository, and the commands for the rehearsal in Task 5.
- [ ] **Step 2: Implement the exporter** with the interface above, importing the stock app's `db` and `analytics` by putting `--stock-app` on `sys.path`; table columns via SQLAlchemy's inspector; one read-only session.
- [ ] **Step 3: Verify by hand** (no CI: Reactor's environment has no SQLAlchemy): copy the stock app's local `stock.db` into a scratch folder outside every repository, run the exporter against `sqlite:///<that copy>` with the stock app's `.venv`, and check that every present table's `count` equals `len(rows)` and that `missing` is true exactly for the tables the older database lacks. Delete nothing but the scratch copy afterwards.
- [ ] **Step 4: Commit** the exporter and its README (never an export).

### Task 4: The converter and its proof

**Files:**
- Create: `tools/stock_import.py`
- Test: `tests/dispatch/stock-foundation.py`

**Interfaces:**
- Consumes: the export format (Task 3), `gizmo.stock_store` (Task 1), `gizmo.stock_figures` (Task 2).
- Produces:
  - `convert(export: dict, people: dict[str, str], out_dir: str) -> None`: writes every stock store into `out_dir` (the store paths are rebased onto `out_dir` for the call through `stock_store.rooted(out_dir)`, a context manager added to `gizmo/stock_store.py` that points every path constant at `out_dir` and puts them back).
    - Items, periods, alerts, suppliers, meta and the bridge tables as Task 1 describes; `next_id` = highest id + 1.
    - History: every `audit_log` row in id order, `person` = `people.get(user)`; refuses (raises `ValueError` naming the usernames) when a history `user` other than `system`, `gizmo` or `?` has no entry in `people`.
    - Snapshots: each `snapshots` row with its `snapshot_items` rows nested as `items`, through `append_snapshot`.
    - Backups: one file each, `format: "legacy-fernet"`, the blob as base64; no key is needed or read.
    - People: `stock_people.json` from `people`.
  - `prove(export: dict, out_dir: str) -> list[str]`: every difference as a sentence naming the table, the id and the field; an empty list means proven. It checks:
    - each table's `count` equals the number of records written for it;
    - every row's every column equals its record (timestamps compared as instants; NULL against NULL; JSON-in-text columns compared as parsed values);
    - the history's SHA-256 over its rows in id order (each row as `json.dumps(row, sort_keys=True)` of the source columns only) equals the source's;
    - every item resolves by the label code `"CL" + str(id)`, and every non-empty barcode resolves to its item;
    - each of `expected`'s figures equals `gizmo.stock_figures` on the converted stores with `now` = the export's `now`, compared value for value (money exactly, after both sides' own rounding).
  - CLI: `python tools/stock_import.py --export FILE --people FILE --out DIR [--report FILE]`; exit 0 only when `prove` returns nothing; refuses an `--out` or `--report` inside a git working tree.

- [ ] **Step 1: Write the failing tests**, building an invented export in the test (two items, one with key `Glass|Blue|20|` and one `Glass|Blue|20||#2`; an item whose key changed after its history row was written; a naive and an aware timestamp for the same instant; an item with NULL `barcode` and `reorder_point`; two snapshots with items; a closed and an open period with `closing_data`; an alert dismissed; a supplier contact; each of the four bridge tables; a legacy backup blob; `meta` with `low_stock_days`; and `expected` computed for that data by hand for `compute_current`'s headline):
  - `t_the_converter_keeps_every_record`: `convert` then `prove` returns `[]`; item ids, keys (`|#2` included) and history keys are verbatim; the naive and aware timestamps convert to the same instant.
  - `t_the_proof_names_a_changed_field`: after converting, change one item's `on_order` in the written store; `prove` returns exactly one sentence naming `items`, that id and `on_order`.
  - `t_the_proof_notices_a_dropped_history_line`: remove one line from the written history file; `prove` reports the count and the checksum.
  - `t_a_person_without_a_mapping_is_refused`: a history row by a username absent from `people` makes `convert` raise `ValueError` naming it; `system` and `gizmo` need no mapping.
  - `t_the_proof_compares_the_figures`: an `expected` whose headline stock value is off by one penny makes `prove` report that figure.
  - `t_the_converter_never_writes_inside_the_repository`: the CLI with `--out` set to a folder inside the repository exits non-zero and writes nothing.
- [ ] **Step 2: Run** `ONLY=stock python tests/test_dispatch.py`. Expected: the new tests FAIL (no tool).
- [ ] **Step 3: Implement `tools/stock_import.py`** and `stock_store.rooted`.
- [ ] **Step 4: Run** `ONLY=stock python tests/test_dispatch.py`. Expected: all pass.
- [ ] **Step 5: Commit** `tools/stock_import.py`, `gizmo/stock_store.py` and the tests.

### Task 5: The rehearsal on the local copy, and the pull request

**Files:**
- Modify: `data/changelog.json`, `tools/stock_move/README.md` (the rehearsal's outcome, without figures)

- [ ] **Step 1: Run the whole path by hand** on the July copy of the stock app's database (outside every repository): export with the stock app's `.venv`, write a `people` file mapping each history username to a placeholder account id, convert into a scratch folder, and check the CLI exits 0 with an empty proof. Expected: every proof passes, the four Reactor-link tables are `missing` in this older copy, and the figures match the stock app's own to the penny.
- [ ] **Step 2: Fix anything the rehearsal finds** test-first in the task that owns it (a mismatch is a bug in the port or the converter, never a reason to loosen a proof), and rerun Step 1 until it passes.
- [ ] **Step 3: Add the release note** dated the merge day: kind `changed`, tab `null`, title `Behind the scenes`, text `Reactor can now hold the stock sheet's records and work out its figures, ready for the stock sheet to move in. Nothing you see changes yet.`
- [ ] **Step 4: Run `make check`** (Global Constraints). Expected: exit 0.
- [ ] **Step 5: Commit, push the branch, open the pull request** against `main` with Auto-fix and squash auto-merge, its body saying what was proven on the rehearsal without any figure, and that the real proof runs on the production copy in plan 4.
