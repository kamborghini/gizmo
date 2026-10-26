# Stock in Reactor, plan 4 of 4: the switch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Everything the switch evening needs, built and proven before it: the export read from the production database in one consistent snapshot, the converter's last switch-day duties, and an owner-only Move-in inside Reactor that checks an export (convert and prove, changing nothing) and then moves it in (installs exactly what was proven, puts the stock sheet live, opens the Stock tab for the people mapped).

**Architecture:** The converter stays the one place that shapes and proves the data (`tools/stock_import.py`). Reactor runs it as a child process (it switches the stock store's folders for its whole process, which must never happen inside the running server), from a new rules module `gizmo/stock_move.py` behind `/api/stock/move`. The page is a Settings row and one window (`static/src/js/stock-move.js`). `live_since` is written last, so a run that stops part-way leaves the stock sheet where it was.

**Tech Stack:** Python 3 (Reactor), SQLAlchemy and psycopg2 (the stock app's exporter, run with the stock app's Python), plain JavaScript page sections, Reactor's test suites (dispatch, page, browser).

**Spec:** `docs/superpowers/specs/2026-10-22-stock-in-reactor-design.md`, section 11 (Moving the data, and the switch), with sections 2 (people) and 7 (warnings raised once).

## Global Constraints

- The repository is public: "no stock figures, supplier names or prices, no colleague's name, and no database copy in code, tests, documents or commit messages. Test data is invented." Run the real-name check (every added line and every commit message against the stock app's own names, read locally) before the first push, and squash the branch if a commit ever carried one.
- "The converter (`tools/stock_import.py`, committed; no data ever committed) reads a copy of the stock app's database and writes Reactor's stock stores, then proves the result."
- "The result is loaded through an owner-only import in Reactor, which shows the proof again on arrival."
- Reactor's house rules: the one door (`gate._guard`, a body model for every write, `tests/caller_payloads.json` and `docs/API.md` kept in step), the one writer (stock files only through `gizmo/stock_store.py`), British English, no dashes in anything a person reads, never setting, hosting or environment variable names, never "Railway" or "gizmo" on screen, a release note dated the merge day.
- I cannot reach Railway or the production database: every step that reads production is Cameron's, written out for him to run.

## Review Focus

- **A large export.** Production's history and snapshots may run to tens of megabytes; the upload goes in parts with a progress line, and a check or a move runs in the background with its state on disk, so no single request carries or waits for it all. Pinned in Task 3 (`t_an_export_arrives_in_parts_and_is_checked_whole`).
- **Reactor restarting mid-run** (a deploy on the evening). A run left "running" on disk by a process that is gone says "interrupted, run it again"; a move stopped before `live_since` leaves the stock sheet not live, and running it again works. Pinned in Task 3 (`t_an_interrupted_run_says_so_and_can_run_again`).
- **Orders made during the evening.** Bookings Reactor could not hand the stock app are booked into the stock sheet after the move, including ones parked after twenty tries, and a booking the stock app did take is not counted twice. Pinned in Task 3 (`t_moving_in_puts_the_stock_sheet_live`) and by plan 2b's booking-twice test.
- **Two windows at once.** A second check or move while one runs is refused, and a move is refused for any export or mapping other than the one the last passing check proved. Pinned in Task 3 (`t_moving_in_needs_a_passing_check_of_this_export`).
- **Every warning raised twice.** The first snapshot after the switch must not raise again every warning the stock app already raised. Pinned in Task 2 (`t_converted_warnings_are_raised_once`).

---

### Task 1: The export, read in one moment and proven on Postgres

**Files:**
- Modify: `tools/stock_move/export_from_stock_app.py` (`read_only_engine`)
- Modify: `tools/stock_move/selfcheck.py` (a `--database-url` for an empty Postgres database)
- Modify: `tools/stock_move/README.md` (a throwaway Postgres for the selfcheck; the production export command)
- Test: `tests/dispatch/stock-foundation.py`

**Interfaces:**
- Produces: `read_only_engine(url)` whose Postgres sessions are `REPEATABLE READ, READ ONLY`; `selfcheck.py --database-url URL` building its invented data in that (empty) database.

- [ ] **Step 1: Write the failing test** `t_the_stock_export_reads_one_moment`: the exporter's source sets `SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY`, and `dump_tables` reads every table inside one `engine.connect()` block (assert the text, as the suite cannot run the stock app's code).
- [ ] **Step 2:** run `ONLY=reads_one_moment` on `tests/test_dispatch.py`; expect FAIL.
- [ ] **Step 3:** make the session `REPEATABLE READ, READ ONLY`; give `selfcheck.py` a `--database-url` (default: its SQLite file as now) that creates the stock app's tables in that database with the stock app's own models before filling it.
- [ ] **Step 4:** run the test (PASS); then, outside the suite, start a throwaway Postgres (a scratch venv with `pgserver`, or `postgresql-wheel`), run `selfcheck.py --database-url <it>` with the stock app's Python; expect exit 0. Ledger the result; if no throwaway Postgres can be had on this Mac, ledger that the Postgres path is still unrun and say so in the PR.
- [ ] **Step 5:** README: the selfcheck on Postgres, and the production export as Cameron runs it (the stock app's Postgres public URL in an environment variable, never on the command line; the exporter; the export kept outside every repository). Commit.

### Task 2: The converter's switch-day duties

**Files:**
- Modify: `tools/stock_import.py` (`convert`, `rebuild_orders`, `prove`, `main`)
- Modify: `gizmo/stock_store.py` (`install_from`)
- Create: `tests/dispatch/stock-move.py` (in `SECTIONS` after `stock-screens.py`)

**Interfaces:**
- Consumes: `stock_figures.detect_anomalies(items, meta, prev_totals)`; the test export `_stock_export()` (tests/dispatch/stock-foundation.py).
- Produces:
  - `convert()` writes `stock_alerts.json["standing"]`: `{item_key: kind}` for every per-line warning the snapshot rule gives now whose line already has an alert of that kind in the export; `prove()` checks it.
  - `rebuild_orders()` dates every "ordered before the move" order one second before the oldest rebuilt order (or the export's time when none).
  - `stock_import.py --list-people`: prints `{"history": [usernames], "logins": [usernames]}` (the names needing an account) and exits 0.
  - `stock_import.py --json-report FILE`: writes `{"proven": bool, "differences": [..], "counts": {store: n}}`.
  - `stock_import.py --install`: after a clean proof, `stock_store.install_from(out_dir) -> {"installed": [names], "set_aside": folder or None}`; exit 3 (nothing installed) when the live settings already carry `live_since`.
  - `stock_store.install_from(folder: str) -> dict`: moves any stock store already at the live paths into `<folder>/set-aside-<UTC stamp>/`, then copies each store from `folder` to its live path atomically (temp file, then replace), private where the store is private. Never writes `live_since`.

- [ ] **Step 1: Write the failing tests:**
  - `t_converted_warnings_are_raised_once`: a line below its level with a carried `low_stock` alert is standing; a low line with no carried alert is not; a snapshot taken after `live_since` raises no new alert for the standing line and raises the other.
  - `t_orders_from_before_the_move_are_the_oldest`: the before-move order's `at` is earlier than every rebuilt order's.
  - `t_the_converter_lists_who_needs_an_account`: `--list-people` on the test export prints its history and login usernames, `system`, `gizmo` and `?` left out.
  - `t_install_puts_the_proven_stores_in_place`: `--install` into the harness's live paths: every store present and equal to the converted folder's, the settings without `live_since`, a stock file already there set aside, exit 0.
  - `t_install_refuses_when_live_or_unproven`: live settings already carrying `live_since` → exit 3, nothing changed; a proof with a difference → exit 1, nothing installed.
- [ ] **Step 2:** run `ONLY=` each; expect FAIL.
- [ ] **Step 3:** implement as the Interfaces say.
- [ ] **Step 4:** run the stock sections (`ONLY=stock`) and `tools/stock_move/selfcheck.py` (SQLite); expect PASS and exit 0.
- [ ] **Step 5:** commit.

### Task 3: Move-in, the rules and the route

**Files:**
- Create: `gizmo/stock_move.py`
- Modify: `gizmo/routes/stock.py` (`StockMoveBody`, `/api/stock/move`), `gizmo/stock.py` (`forget_memory()`), `tests/caller_payloads.json`, `docs/API.md` (`make api-doc`)
- Test: `tests/dispatch/stock-move.py`

**Interfaces:**
- Consumes: Task 2's `--list-people`, `--json-report`, `--install`; `stock_backups.make_backup(who)`; `stock_link._load_zeta_pending()` / `_write_zeta_pending()`; `team._load_users()` / `_write_users()`; `activity._track`.
- Produces (`gizmo/stock_move.py`; every op owner only: `team._team_role(uid) == "master"`, else 403 "Only the owner can move the stock sheet in."):
  - `STOCK_MOVE_DIR` (default `/data/stock_move`, private); `EXPORT_CAP = 256 MiB`; `PART_CAP = 4 MiB` of text per part.
  - `status() -> dict`: `{"live", "moved_in", "upload": {"bytes", "sha256", "exported_at", "counts"} | None, "names": {"history": [], "logins": []} | None, "accounts": [{"id", "name"}], "run": {"kind": "check"|"move", "state": "running"|"passed"|"failed"|"refused"|"interrupted"|"done", "at", "differences": [first 50], "words"} | None, "queue": {"pending", "stuck"}}`.
  - `receive_part(uid, upload, index, total, text, sha256) -> dict`: parts in order into one file; the last part checks the SHA-256 of the whole and that it is a `stock-export-1` export, then lists the names (`--list-people`). Out of order, over the cap, a wrong checksum or another format: refused in plain words, the partial file removed.
  - `start(uid, kind, people) -> dict` (async; `kind` "check" or "move"): refused while a run is running, after the move, without an upload, with a name left unmapped or mapped to no account; "move" also refused unless the last run was a passing check of this upload's SHA-256 and this mapping. Runs the converter in the background (`asyncio.create_subprocess_exec(sys.executable, tools/stock_import.py, ...)`, a fresh staging folder each run, a deadline of 30 minutes) and records its state on disk.
  - After a passing move, under `stock._lock`: `live_since` and `moved_in: {"at", "by", "sha256", "people"}` in the settings; the Stock tab granted to each mapped account that is not the owner (`tabs` = its list, or the default set, plus "stock"), tracked as "changed tab access"; every queued booking's `tries` set to 0 and `stuck` cleared; the first stock backup; a history line `moved in`; `stock.forget_memory()`.
  - On startup (or the first `status`), a run left "running" by a process that is gone becomes "interrupted".
- Route: `/api/stock/move`, ops `status`, `part`, `check`, `move`; `StockMoveBody`: `upload: Text, index: Whole, total: Whole, text: Text, sha256: Text, people: Fields`; door `max_body` 6 MiB.

- [ ] **Step 1: Write the failing tests:**
  - `t_only_the_owner_moves_the_stock_sheet_in`: a member and an admin get 403 on every op.
  - `t_an_export_arrives_in_parts_and_is_checked_whole`: the test export in three parts arrives and `status` shows its counts and the names to map; a part out of order, a wrong SHA-256 and a file that is not an export are each refused with its own words and leave no upload.
  - `t_a_check_proves_the_export_and_changes_nothing`: check with the mapping; poll `status` until done; state "passed", no differences; the live stock paths hold no stores and the stock sheet is not live.
  - `t_moving_in_needs_a_passing_check_of_this_export`: move refused with no check, after a failing check, after a new upload, and with a mapping other than the checked one; a second check while one runs refused.
  - `t_moving_in_puts_the_stock_sheet_live`: after a passing check, move; `stock.is_live()`; items equal the export's; a member mapped in the people gains "stock" in their tabs and the others do not; a queued booking parked after twenty tries is unstuck; one stock backup; the newest history line is "moved in"; a second move refused "The stock sheet has already moved in."
  - `t_an_interrupted_run_says_so_and_can_run_again`: a run file saying "running" for a process id that is gone reads "interrupted"; a check then runs.
- [ ] **Step 2:** run each; expect FAIL.
- [ ] **Step 3:** implement as the Interfaces say; add the route's caller payloads (one per op) to `tests/caller_payloads.json` with the page's source lines (Task 4 adds the page; until then the sources point at this task's tests, as plan 2a did); `make api-doc`.
- [ ] **Step 4:** run the stock sections and `stages-4-to-6` / `hardening-2` (the door and the API document); expect PASS.
- [ ] **Step 5:** commit.

### Task 4: Move-in, the page; the stock app's name once live

**Files:**
- Create: `static/src/js/stock-move.js`, `static/src/css/stock-move.css` (in the manifest)
- Modify: `static/src/js/settings.js` (the owner's row; the Connections row once live), `static/src/js/production-manager.js` (`openStockUsage`'s two sentences), `tests/caller_payloads.json` (sources)
- Test: `tests/test_frontend.py`

**Interfaces:**
- Consumes: Task 3's route and `status()` shape; `stockLive()`.
- Produces: `openStockMove(opener)`; `stockMoveParts(text, size) -> [string]`; `stockMoveGuess(name, accounts) -> id or ""`.

- [ ] **Step 1: Write the failing tests:**
  - `t_an_export_is_sent_in_parts_that_join_up`: `stockMoveParts` of a 10,000 character text at 4,096 joins back to the text, every part at most 4,096.
  - `t_a_stock_username_is_matched_to_its_person`: `stockMoveGuess('cameron', [{id:'u1', name:'Cameron'}, {id:'u2', name:'Owen'}])` is `'u1'`; an unknown name gives `''`.
  - `t_move_in_waits_for_a_passing_check_of_this_export`: the window's Move in button is enabled only when the run is a passing check of this upload and this mapping (a node run of the function that decides it).
  - `t_the_stock_app_is_named_only_before_the_move`: the Connections row and `openStockUsage`'s sentences read "the stock app" only when `stockLive()` is false and "the Stock tab" once it is true.
  - `t_moving_in_is_the_owners`: the Settings row is drawn only for the owner and only before the move; after it the row says when and by whom.
- [ ] **Step 2:** run each; expect FAIL.
- [ ] **Step 3:** implement: the window's steps (the export, with its parts' progress; the people, a chooser per name with the guess first; Check, polling `status` every 2 seconds while running, showing "Proven" with the counts or the differences; Move in, the one primary, behind a one-way question naming who gets the Stock tab). On "done": the account is read again so the Stock tab appears.
- [ ] **Step 4:** run the page suite and the browser suite (the browser world is already moved in, so the window is not measured: ledger that); expect PASS.
- [ ] **Step 5:** commit.

### Task 5: The evening, written down; the release

**Files:**
- Modify: `tools/stock_move/README.md` ("The switch": the evening's steps, who does each), `data/changelog.json`

- [ ] **Step 1:** README "The switch": both stop editing and save phone counts; the stock app stopped on Railway by Cameron (its database left running); the export with the command from Task 1; Settings, Move the stock sheet in: the export, the people, Check, Move in; a few labels scanned and the Overview checked against the stock app's last screen; the stock app left off and its database kept until the next quarter close; the camera test removed after the move.
- [ ] **Step 2:** release note dated the merge day: kind `changed`, tab `null`, title `The stock sheet can move in`, text `The owner can now move the stock sheet into Reactor from Settings: Reactor checks the stock app's export line by line first, and changes nothing until it has proven every figure. Until then everything works as before.`
- [ ] **Step 3:** `make check`; the dispatch suite; a whole-branch review by one fresh reviewer; fixes test first; the real-name check; push; PR with Auto-fix and squash auto-merge.
