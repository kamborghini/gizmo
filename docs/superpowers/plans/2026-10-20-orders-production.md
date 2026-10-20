# Orders and production Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pin the printed labels by output; then move the way to Shopify (floor), orders, production and the size list out of `copilot.py`. Nothing anyone sees changes, no label above all.

**Architecture:** As piece 3: a one-off generator with name inventories for four destinations (`shopify` is floor and may not borrow; the others borrow as `core.` and import it last), the crossing-`global` transform for `add_routes`' capability lines, and copies in `copilot.py` for the frozen print route's moved names.

**Tech Stack:** Python 3.14; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-20-orders-production-design.md`

## Global Constraints

- No label, label document, queue or size answer changes (Task 1's pin).
- A pure move except the declared `global` lines in `add_routes`.
- Frozen: the print route's bytes; print CSS and functions.
- A release note dated the merge day; British English; no dashes in UI copy.
- Browser on 8941; no agents; branch `refactor/orders-production` on `refactor/accounts-door` (#43).

## Review Focus

1. **A label that differs** by a field, a size or an order: pinned by Task 1 (data and document, two sizes).
2. **A capability `server.py` hands in landing on the wrong module**: pinned by the suite's dispatch, release and payment terms tests (they patch and call through `shopify.`) and guard (a).
3. **The order cache's epochs and in-flight state** read from two modules: pinned by guard (b) (they are rebound by `global`, so never copied).
4. **The frozen print route's copies** of names a test patches: pinned by guard (b) and the print freeze.
5. **The Size list's rule files** (live paths on the volume vs the repo's seeds) read from the wrong place: pinned by the size-list tests and the sizes module reading the same settings.

---

### Task 1: The labels pinned by what they print

**Files:** `tests/test_dispatch.py`

- [ ] **Step 1:** `t_the_printed_labels_do_not_change`: `run_production_labels({}, order_id=…)` for the fixture orders as sorted JSON, and the document from a signed `/print/production-labels` URL for them at `4x6` and `4x4`, each with dates and times masked, hashed and compared with hashes computed on today's code. A characterization test: it passes at once by construction, so prove it can fail: a throwaway one-character change to the label builder makes it fail; undo.
- [ ] **Step 2:** **Commit.**

### Task 2: The move

**Files:** `gizmo/shopify.py`, `gizmo/orders.py`, `gizmo/production.py`, `gizmo/sizes.py` (create), `copilot.py`, `gizmo/dispatch.py`, `gizmo/routes/dispatch.py`, `tests/test_dispatch.py`, `tests/test_frontend.py` (text checks), `tests/browser/seed/*.py`, `docs/ENVIRONMENT.md`, `data/changelog.json`

**Inventory** (by name; the generator lists any statement binding names for two destinations):
- shopify: `_tool_json`, `_shopify_gone`, the 13 capabilities.
- orders: `ORDER_PAGE_CAP`, `ORDER_CACHE_SECS` to `ORDER_REFRESH_MAX` and the order-cache state, `WEBHOOK_MAX_BYTES`, `_webhook_state`, `_webhook_seen`, `_webhook_note_delivery`, `_refresh_asked`, `_bust_orders` to `_orders_product_monthly`, `_admin_order_url`, `_order_tags`, `_has_tag`, `UNPROCESSED_TAG`, `MADE_TAG`, `PROPOSAL_HOST`, `_PROPOSAL_RE`, `PO_UNPAID_TAG`, `_tag_locks`, `_dispatch_locks`, `_dispatch_lock`, `_tag_lock`, `_sync_order_tags`, `_EDIT_ADDR_KEYS` to `_edit_order`, `_fulfill_if_ready`, `_unfulfill_dispatch`, `_extract_proposal` to `_origin_address`.
- production: `PRODUCTION_TAG`, `PRODUCTION_DAYS`, `PRODUCTION_STATE_PATH`, `PRODUCTION_STATE_MAX`, `_load_prod_state`, `PRODUCTION_ARCHIVE_PATH`, `ProdStateUnwritable`, `_write_prod_state`, `_archived_made`, `_mark_printed`, `_mark_made`, `_label_party` to `_product_types`, `_LABEL_LOGO_SVG`, `_item_prop` to `_projector_size`, `_release_bg`, `_dispatch_move_tags`, `_release_tags`, `_shape_label_order`, `run_production_labels`, `MISSING_CACHE_SECS`, `_missing_cache`, `run_missing_production`, `_missing_scan`, `_terms_flag`, `_net30_on_release`.
- sizes: `STOCK_GOBO_TYPE`, `GOBO_SIZES_PATH`, `_gobo_cache` to `_gobo_check` (the GOBO_* paths, the rule files and rows, the keys, the lookup, the maker groups).
- copies in `copilot.py`: `_LABEL_LOGO_SVG`, `_load_prod_state`, `_mark_printed`, `run_production_labels`, `_release_bg`.

- [ ] **Step 1: Failing tests:** `t_what_dispatch_borrows` without the orders names now read from `orders.`, `production.` and `shopify.`; `t_the_floor_imports_nothing_above_it` gains `gizmo/shopify.py`; `t_either_module_imports_first` gains the three areas. Run: they fail.
- [ ] **Step 2: Generate**; re-point tests and seeds; fix the text checks that quote prefixed names; regenerate the settings reference; release note.
- [ ] **Step 3: Run** Task 1's pin, every guard, the three suites, both `--check`s. **Commit.**

### Task 3: Proof, recipe, check, push

- [ ] `make move-proof BASE=<accounts head> DECLARED=global,…`; `docs/ARCHITECTURE.md`; merge main once #43 lands; `make check` on 8941; self-review; push; the pull request.
