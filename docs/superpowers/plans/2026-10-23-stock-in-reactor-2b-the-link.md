# Stock in Reactor, plan 2b of 4: the link moved in, matching, AI and chat

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The production link (each order's glass booked when it is marked made, the day sheet, the gobo-line matching) works inside Reactor, and the stock app's AI (insights, reading a PDF invoice, a purchase order note) and read-only chat tools are there, all switching on only when the stock sheet moves in. Until then the link keeps sending to the stock app exactly as today.

**Architecture:** First the link's code moves out of `copilot.py` into `gizmo/stock_link.py` with `tools/move_area.py`, proved unchanged by `make move-proof`. Then the stock app's bridge rules are ported into `gizmo/stock_bridge.py` over the stock stores (through `stock.commit`), and the link's transport sends to them in-process once `stock.is_live()`, keeping the queue's rules. The matching panel, AI and chat tools sit on the same rules.

**Tech Stack:** Python 3.14; Reactor's door, AI client (`gizmo/ai.py`: `_xcreate`, spend cap, forced tools), chat tool registry and gate (`gizmo/chat.py`), the plan 2a stock core.

**Spec:** `docs/superpowers/specs/2026-10-22-stock-in-reactor-design.md`, sections 1 ("the link moves in"), 3 (matching, AI insights, invoice reading, PO note), 7 (the catalogue push goes), 9 (AI and chat). Plan 2a (#83) built the sheet. The read-only survey of Reactor's link, AI, chat and conventions made for plan 2 is what the file and line references below come from.

**Reference behaviour:** the stock app at `/Users/cameron/Desktop/claude/stock-copilot` commit `0310765`: `app.py` `/api/sync/consumption` (1410), `/api/sync/usage-sheet` (1289), `/api/sync/mapping` (1535), `/api/sync/parked` (1592), `/api/sync/map` (1611), `_gizmo_match` (409), `_gizmo_apply` (457), `_gizmo_booked_this_period` (483), `_gizmo_reverse` (496), `_sheet_reverse` (528), `/api/insights` (2300), `/api/receive/parse` (1775), `/api/po/note` (2118).

## Decisions this plan makes

1. **The switch is the stock sheet's own `live_since`.** Before it, the link sends to the stock app as today (its HTTP transport, its queue, its catalogue push). After it, the same queue sends in-process to `stock_bridge`, the catalogue push stops, and the matching panel, AI and chat tools answer. Nothing else decides it, so the switch in plan 4 is one import, and no setting has to change on the server.
2. **Who a booking is recorded under.** The stock app wrote every bridge line as its link user. In Reactor a booking is recorded under the account that pressed Mark made, sent the day sheet or made the ruling; the retry queue keeps that account with the order, so a retried booking is recorded under the same person. A booking with no account (none today) is "Production".
3. **The bridge rules are the stock app's, word for word,** including what it does at a quarter boundary, its 0.001 and single-candidate 0.2 tolerances, parking a line with a note, and remembering only Mono, HM and Ring rulings. Its own detail formats are kept (they hold no dashes).
4. **Chat tools are read-only and the stock tab's.** Each refuses for an account without the tab (all but the master until plan 3) and says the stock sheet has not moved in until it has.

## Global Constraints

- Plan 2a's constraints hold: invented data; house copy rules (no `gizmo`, `Railway` or setting names in strings a person reads; no dashes); the one door with a flat body model per route; every write through `stock.commit` under `stock._lock`; store paths read as `stock_store.NAME`; lines named by id; sibling imports at the bottom.
- The move is proved by `make move-proof BASE=origin/main`, every intended change declared.
- After the move nothing imports `copilot` but `server.py` (`t_only_the_stock_bridge_reads_copilot` becomes a test that nothing does).
- AI calls go through `claude._xcreate(claude._anthropic(), ...)` with `claude._ai_kind` set, structured answers by a forced tool read from the `tool_use` block (Opus 5.5 unforces it; a missing block is an error), `max_tokens` at most 16,000, `RuntimeError` answered 429 with its words and `anthropic.APIError` 502 with `claude._ai_error_words(e)`, model text passed through `claude._strip_dashes`.
- New tests in new dispatch sections `'stock-link.py'` and `'stock-ai.py'` after `'stock-backups.py'`; every test name contains `stock`.
- Caller payloads for each new route (sources: the test lines until plan 3), `make api-doc`, `make env-doc`, a release note, `make check`, a PR with Auto-fix and squash auto-merge.

## Review Focus

- **A booking applied twice across the switch.** An order queued before the switch and drained after it must book once in Reactor and never at the stock app. Pinned in Task 3.
- **Mark made pressed twice, or made then un-made, while the store refuses writes.** The queue keeps the latest intent and the drain applies it once. Pinned in Task 3.
- **A day sheet sent again, or sent after one of its orders was re-made.** Its adjustment is measured against what the bookings hold now, replacing the earlier sheet. Pinned in Task 2.
- **A ruling made for a line renamed since.** Rulings follow the line's id. Pinned in Task 2.
- **A PDF that is not a PDF, too large, or answered with a key not in the list.** Refused or dropped, never booked. Pinned in Task 5.

---

### Task 1: The link moves out of copilot.py, unchanged

**Files:**
- Create: `tools/moves/stock-link.json`; by the tool: `gizmo/stock_link.py`, `gizmo/routes/stock_link.py`
- Modify (by the tool and by hand): `copilot.py`, `gizmo/routes/production.py`, `gizmo/routes/status.py`, `gizmo/scheduler.py`, the tests that patch the moved names, `tests/dispatch/stages-4-to-6.py` (the copilot-readers guard), `docs/ARCHITECTURE.md`, `docs/ENVIRONMENT.md`, `docs/API.md`

**Interfaces:**
- Produces: `gizmo/stock_link.py` holding every name that was `copilot.ZETA_*`, `_zeta_*`, `_ZETA_LINE_KEYS`, `USAGE_SHEETS_PATH`, `_BEZEL_UP`, `_usage_lines`, `_usage_row_order`, `run_stock_usage`; `gizmo/routes/stock_link.py` with the two `/api/stock-usage` routes; the readers call `stock_link.NAME`; the moved code reads `production.run_production_labels`, never `copilot`.

- [ ] **Step 1:** Write `tools/moves/stock-link.json` (area `stock_link`, prefix `^(_zeta|ZETA_|_ZETA|_usage_|USAGE_SHEETS|_BEZEL_UP)`, extra `["run_stock_usage"]`; route group `routes_stock_link`, paths `["/api/stock-usage"]`), run `tools/move_area.py` without `--write`, settle what it reports, then `--write`.
- [ ] **Step 2:** Point the moved code's `core.run_production_labels` at `production.run_production_labels` (declared change). Turn `t_only_the_stock_bridge_reads_copilot` into `t_nothing_but_the_server_reads_copilot`.
- [ ] **Step 3:** `make move-proof BASE=origin/main DECLARED=<the declared changes>` prints nothing but the move; `make env-doc`, `make api-doc`; `docs/ARCHITECTURE.md` says the link lives in the stock area.
- [ ] **Step 4:** The full dispatch suite and the frontend suite pass unchanged in what they assert.
- [ ] **Step 5: Commit.**

### Task 2: The bridge rules, ported into the stock area

**Files:**
- Create: `gizmo/stock_bridge.py`, `tests/dispatch/stock-link.py`

**Interfaces:**
- Produces, in `gizmo/stock_bridge.py`, each under `stock._lock` through `stock.commit` with its history lines and one snapshot (none for a reversal that found nothing, as today):
  - `match(st, family, size) -> dict | None`: the stock app's `_gizmo_match` (ruling first by item id then key, only a live line; else `ring` by `sub_category` among Rings, `mono` and `hm` to their glass (the stock settings' `glass_families`, written by the move from the stock app's own rule) by `size`; exact within 0.001, else the single near one within 0.2; no notes first, then lowest id).
  - `book(uid, order_id, order_name, lines) -> dict` and `reverse(uid, order_id) -> dict`: the stock app's `/api/sync/consumption` (`{"ok", "booked", "units", "parked"}` and `{"ok", "reversed"}`), the booking replacing any earlier one for the order, usage banked in a closed quarter left there, lines with a note or an unreadable or out-of-bounds quantity parked, a booking row written even when every line parked.
  - `usage_sheet(uid, day, order_ids, lines) -> dict`: the stock app's `/api/sync/usage-sheet` (`{"ok", "day", "replaced", "results", "adjustments"}`), with its checks.
  - `catalogue() -> list`: `stock_link._zeta_catalog_combos()`.
  - `mapping() -> dict`, `parked() -> dict`, `map_line(uid, alias, item_id, parked_id=None) -> dict`: the stock app's mapping view (rows with `ruled`, `per_order`, `auto` or `unmapped`), parked lines with the Glass and Rings choices (by id), and its ruling (remembered for mono, hm and ring only; a colour ruling books the one parked line; booked lines appended to their order's booking).

- [ ] **Step 1: Write the failing tests**, the stock app's own bridge checks on invented lines (an invented Mono glass at 15.9 and 64.9, an invented HM glass at 20, `Rings` 86 with size 64.9, two Mono glass 20 lines one with notes):
  - `t_marking_made_books_stock_like_a_count_down`: `book` Mono 16 ×2 books the 15.9 line (near match), `current` −2, `used` +2, a `use` line "made #1001 · used 2", a snapshot.
  - `t_marking_stock_made_again_replaces_the_booking`; `t_unmaking_stock_gives_back_exactly_what_it_took` (a second reverse is `reversed: 0`).
  - `t_a_stock_booking_never_takes_the_shelf_below_nothing`: 1 on the shelf, 3 booked: `current` 0, `used` +3, "stock only had 1".
  - `t_a_stock_booking_from_a_closed_quarter_keeps_its_usage_there` (re-push and reverse across a close).
  - `t_a_stock_line_with_a_note_is_parked_not_guessed` (and unreadable and 0 quantities).
  - `t_a_bezelled_stock_order_books_its_glass_and_its_ring`: 64.9 Mono and Ring 86 book both lines.
  - `t_a_stock_ruling_is_remembered_for_mono_not_colour`: Mono ruling books every parked line with that alias and the next push; a Colour ruling books only the line chosen.
  - `t_a_stock_ruling_follows_its_line_through_a_rename`.
  - `t_a_stock_day_sheet_books_only_the_difference`: bookings 3 for the day, final 5: +2; sent again with final 2: the first adjustment undone, then −1; an unmatched line `no_item`; a bad final `bad_quantity`.
  - `t_the_stock_mapping_shows_every_line_and_its_status`.
- [ ] **Step 2–4:** fail, implement, pass.
- [ ] **Step 5: Commit.**

### Task 3: The link sends in-process once the stock sheet has moved in

**Files:**
- Modify: `gizmo/stock_link.py`, `gizmo/routes/production.py` (the account passed with the push), `gizmo/routes/stock_link.py` (the account with the sheet), `gizmo/scheduler.py` (no catalogue push once live), `gizmo/routes/status.py`
- Test: `tests/dispatch/stock-link.py`

**Interfaces:**
- `stock_link._zeta_configured()` is true when the stock sheet is live or the stock app is configured.
- `_zeta_push(registry, order_id, op, who=None)`; a queued entry keeps `"by": who`; `_zeta_drain` passes it back.
- `_zeta_send(op, order_id, order_name, lines, who=None)`: when `stock.is_live()`, `stock_bridge.book`/`reverse` in a worker thread; else the HTTP post as today. `_zeta_send_sheet(payload, who=None)` likewise with `stock_bridge.usage_sheet`.
- The scheduler sends the catalogue only while not live.

- [ ] **Step 1: Write the failing tests:**
  - `t_marked_made_books_in_reactor_once_the_stock_sheet_has_moved_in`: live, Mark made: the line falls in Reactor's store; nothing is sent over the network; the `use` lines are under the account that pressed it.
  - `t_a_stock_booking_queued_before_the_switch_books_once_after_it`: a booking queued while the stock app was down, the stock sheet then moves in, the drain books it in Reactor once and sends nothing to the stock app.
  - `t_made_then_unmade_while_stock_cannot_be_written_ends_as_a_reversal`: live, the store refusing writes: both queued as the latest intent; once writable, the drain reverses (nothing booked).
  - `t_the_stock_day_sheet_is_applied_in_reactor_once_moved_in`: the send route returns the in-process results and records the day.
  - `t_the_glass_catalogue_is_not_sent_once_stock_has_moved_in`.
  - The existing bridge tests (`stock-bridge.py`, the lows, `page-layouts.py`'s day-sheet tests) pass unchanged before the switch.
- [ ] **Step 2–4:** fail, implement, pass.
- [ ] **Step 5: Commit.**

### Task 4: The matching panel's route

**Files:**
- Modify: `gizmo/routes/stock.py`, `tests/caller_payloads.json`, `docs/API.md`
- Test: `tests/dispatch/stock-link.py`

- [ ] **Step 1: Write the failing test** `t_the_stock_matching_panel_reads_and_rules` through `/api/stock/mapping` (`StockMappingBody`: `alias`, `id`, `parked_id`; ops `mapping`, `parked`, `map`): the mapping and parked lists answer, a ruling books the parked line, an unknown line is 404, a written-off line 400, and writes are refused before the move.
- [ ] **Step 2–4:** fail, implement, pass; caller payloads; `make api-doc`.
- [ ] **Step 5: Commit.**

### Task 5: AI: insights, reading a PDF invoice, a purchase order note

**Files:**
- Create: `gizmo/stock_ai.py`, `tests/dispatch/stock-ai.py`
- Modify: `gizmo/routes/stock.py`

**Interfaces:**
- `insights(uid) -> dict`: the stock app's prompt (the business named as "the shop", never by name), its context (`compute_current`, the ten soonest stock-outs, the projection, the history points), its schema as a forced tool `record_insights`; the result kept in `stock_settings.json` as `insights: {at, by, result}`; `last_insights() -> dict`.
- `read_invoice(pdf_base64) -> dict`: at most 9 MB decoded, starting `%PDF-`; the stock app's prompt as a forced tool `record_delivery`; every line checked as it does (quantities above 0, keys not in the live list dropped to `null`, confidence clamped, at most 200 lines); writes nothing.
- `po_note(fields) -> dict`: the stock app's allow-list and prompt; `{"note"}`.
- Route `/api/stock/ai` (`StockAiBody`: `pdf_base64`, `supplier`, `currency`, `native_total`, `gbp_total`, `lines`; ops `insights`, `last_insights`, `read_invoice`, `po_note`), `ai=True`, body cap 12 MB for the invoice; refused before the move.

- [ ] **Step 1: Write the failing tests** with `claude._xcreate` swapped for a stand-in that records the request and answers a tool call:
  - `t_stock_insights_are_asked_once_and_kept`: the request carries the forced tool and the figures; the result is kept and `last_insights` returns it.
  - `t_a_stock_invoice_is_read_but_nothing_is_booked`: a key not in the list becomes `null`, a quantity of 0 is dropped, nothing in the store changes.
  - `t_a_stock_invoice_that_is_not_a_pdf_is_refused` (and over 9 MB) before any AI call.
  - `t_the_stock_po_note_sends_only_the_allowed_fields`.
  - `t_stock_ai_over_the_days_budget_says_so`: `RuntimeError` from the client: 429 with its words.
- [ ] **Step 2–4:** fail, implement, pass; caller payloads; `make api-doc`.
- [ ] **Step 5: Commit.**

### Task 6: Read-only stock tools in the chat

**Files:**
- Create: `gizmo/stock_chat.py`
- Modify: `copilot.py` (`chat_registry` gains the tools), `gizmo/chat.py` (`_TOOL_TABS`, `_TAB_WORDS`, `_TOOL_LABELS`), `gizmo/profile.py` and `gizmo/prompts.py` (unlimited stock narrowed to Shopify products)
- Test: `tests/dispatch/stock-ai.py`

**Interfaces:**
- Tools (each a pydantic model and an async function with a docstring): `stock_levels(query)` (lines matching a colour, size, supplier or code, with current, on order, value and cover), `stock_item_history(item)` (the newest 50 history lines of one line), `stock_movements(days)` (receipts, usage and corrections over the last N days, summed per line), `stock_reorder()` (the reorder list). Each answers "The stock sheet has not moved into Reactor yet." until live.
- `_TOOL_TABS` maps each to `"stock"`; `_TAB_WORDS["stock"]` is "the stock sheet".
- The profile rule reads: "Our Shopify products carry unlimited stock: give no inventory or restock advice about them. The glass stock sheet is tracked separately and its tools may be used."

- [ ] **Step 1: Write the failing tests:**
  - `t_the_chat_reads_stock_and_never_changes_it`: each tool answers from the store; none writes (the store files are byte for byte the same).
  - `t_the_chat_refuses_stock_without_the_tab`: a member's chat gets the refusal naming the stock sheet.
  - `t_the_unlimited_stock_rule_speaks_only_of_shopify_products`.
- [ ] **Step 2–4:** fail, implement, pass.
- [ ] **Step 5: Commit.**

### Task 7: The release

- [ ] **Step 1:** Release note dated the merge day: kind `changed`, tab `null`, title `The stock link, ready to move in`, text `When the stock sheet moves into Reactor, glass used on each order will be booked here as it is now booked in the stock sheet, and the stock sheet's insights, invoice reading and order notes will come with it. Nothing changes until then.`
- [ ] **Step 2:** `make check`; a fresh reviewer on the whole branch; fixes test-first; push; PR with Auto-fix and squash auto-merge.
