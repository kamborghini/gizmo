# Erasure, loans, work sessions, and routes following their areas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Erasure, loans and work sessions out of `copilot.py` with their routes; the routes of production, the Size list and the order book follow their areas. Nothing anyone sees changes.

**Architecture:** `tools/move_area.py` with two descriptions (`tools/moves/privacy-loans-work.json`, `tools/moves/area-routes.json`); the tool learns route groups whose area moved earlier.

**Tech Stack:** Python 3.14; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-20-privacy-loans-work-design.md`

## Global Constraints

- Nothing anyone sees changes; every request answered by the same handler; the frozen print routes untouched.
- A pure move except the declared memory drops.
- A release note dated the merge day; British English; no dashes in UI copy.
- Browser on 8941; no agents; branch `refactor/privacy-loans-work` from main 6994854.

## Review Focus

1. **A redaction or erasure missing a store** after the move: pinned by the redaction and erasure tests (unchanged) and `t_every_memory_copy_of_a_store_is_let_go`.
2. **Shopify's privacy webhook** answered by a different handler: pinned by the proof's order rule and the webhook tests.
3. **A work session's state read from two modules** (clock in and out): pinned by guard (b) and the work tests.
4. **A route group of an earlier area** reaching its area wrongly: pinned by the toy test's new case and the production, size and order route tests.
5. **The frozen print routes**: pinned by the print freeze and `t_the_printed_labels_do_not_change`.

---

### Task 1: The tool learns route groups whose area moved earlier

- [ ] **Step 1: Failing test**: the toy repository gains an earlier area (`gizmo/old.py`, read as `old`) and a route reading it; a route-only group for it moves that route, which reaches `old.` as before.
- [ ] **Step 2: Build** (an area not in this description but bound in `copilot.py` to a split module is accepted for a route group).
- [ ] **Step 3: Run**. **Commit.**

### Task 2: Erasure, loans and work sessions

- [ ] **Step 1: Failing tests**: `t_the_privacy_loans_and_work_routes_are_gathered`; `t_either_module_imports_first` gains the five modules.
- [ ] **Step 2:** By hand, the loans' and work sessions' drops (declared). The description; dry run; settle in the description; `--write`. Text checks; references; release note.
- [ ] **Step 3: Run** every guard, the label pin, the suites. **Commit.**

### Task 3: The moved areas' routes follow them

- [ ] **Step 1: Failing test** `t_the_moved_areas_routes_follow_them` (three register calls; no `/api/production-labels`, `/api/production-state`, `/api/stock-usage`, `/api/gobo-sizes`, `/api/order/` or `/webhooks/orders` route left in `copilot.py` but the frozen print routes).
- [ ] **Step 2:** The description; dry run; `--write`; references.
- [ ] **Step 3: Run** the label pin, the print freeze, the suites. **Commit.**

### Task 4: Proof, recipe, check, push

- [ ] `make move-proof` (declared: the drops); `docs/ARCHITECTURE.md`; `make check` on 8941; self-review; push; the pull request.
