# The AI settings, the Products tab and customer history Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The AI settings, the Products tab and customer history out of `copilot.py`. Nothing anyone sees changes.

**Architecture:** `tools/move_area.py` learns `existing` route groups; one description (`tools/moves/ai-settings-products.json`).

**Tech Stack:** Python 3.14; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-21-ai-settings-products-design.md`

## Global Constraints

- Nothing anyone sees changes; the frozen print routes and the stock bridge untouched.
- A pure move: nothing declared.
- A release note dated the merge day; British English; no dashes in UI copy.
- Browser on 8941; no agents; branch `refactor/piece-14` from piece 13 (6b2cf44, #58), brought up to main once #58 merges.

## Review Focus

1. **The order book's routes** after a route is added to their `register()`: pinned by the toy test and the order route tests.
2. **Customer history** after it moves: pinned by `t_the_customer_history_route_counts_the_orders`, written before it.
3. **Effort on every AI call** once `_effort_for` lives on the floor: pinned by the effort tests (unchanged) and `t_the_floor_imports_nothing_above_it`.
4. **The Products tab and a product's page** after their routes move: pinned by the products tests and `make move-proof`'s route order rule (two exact paths).
5. **The chat's limits** read by the chat routes that stay: pinned by the chat route tests.

---

### Task 1: The tool adds routes to a route module moved earlier

- [ ] **Step 1: Failing test**: in `t_move_area_moves_routes_after_their_area`, a toy `gizmo/routes/old.py` with one route in `register()`; an `existing` group adds a second route to it, after the first, and `add_routes` keeps no call for it.
- [ ] **Step 2: Build** `existing` route groups.
- [ ] **Step 3: Run** the toy tests. **Commit.**

### Task 2: The move

- [ ] **Step 1: The pin** (passes now): `t_the_customer_history_route_counts_the_orders`. **Failing tests**: `t_the_ai_settings_products_and_history_have_moved` (the names bound in their modules, not in `copilot.py`; one `routes_products.register` call; no `/api/products`, `/api/product` or `/api/customer-history` route left in `add_routes`; 2 routes in `gizmo/routes/products.py`, 3 in `gizmo/routes/orderbook.py`); `t_either_module_imports_first` gains the two modules.
- [ ] **Step 2:** The description; dry run; `--write`; text checks; references; release note.
- [ ] **Step 3: Run** every guard, the suites. **Commit.**

### Task 3: Headings, proof, recipe, check, push

- [ ] Headings (comments only); `make move-proof` (nothing declared); `docs/ARCHITECTURE.md`; `make check` on 8941; self-review; push; the pull request.
