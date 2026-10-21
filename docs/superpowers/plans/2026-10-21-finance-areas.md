# The chase desk, reconciliation and the Xero sync settings, and the forecast hooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Finance tab's backend out of `copilot.py` with its routes. Nothing anyone sees changes.

**Architecture:** `tools/move_area.py` with one description (`tools/moves/finance-areas.json`).

**Tech Stack:** Python 3.14; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-21-finance-areas-design.md`

## Global Constraints

- Nothing anyone sees changes; every request answered by the same handler; the frozen print routes and the stock bridge untouched.
- A pure move: nothing declared.
- A release note dated the merge day; British English; no dashes in UI copy.
- Browser on 8941; no agents; branch `refactor/finance-areas` from piece 10 (dfa6322, #55), brought up to main once #55 merges.

## Review Focus

1. **The Liability tab's route** after it moves: pinned by `t_the_liability_route_answers_with_the_report`, written before it.
2. **A forecast hook taking a request without its token** after it moves: pinned by `t_the_forecast_hook_takes_only_its_token_and_the_tab_reads_the_run` and the hook tests (unchanged).
3. **The chat's reconciliation tools** built in `add_routes` from the moved names: pinned by the reconciliation tool tests and the boot of `add_routes` in every route test.
4. **The connector settings save** (which settings may be set, the numbers) after it moves: pinned by the connector settings tests (unchanged).
5. **The Xero connect walk's one-time state** after it moves: pinned by the Xero connect tests and guard (b).

---

### Task 1: The pin

- [ ] `t_the_liability_route_answers_with_the_report` (two unpaid orders, through `/api/liability`: 200, the account's chase email names both orders and the total). Passes now; fails when the route answers otherwise (mutation checked). **Commit.**

### Task 2: The move

- [ ] **Step 1: Failing tests**: `t_the_finance_routes_are_gathered` (one register call each; no `/api/liability`, `/api/recon/`, `/oauth/xero/`, `/api/connector`, `/hooks/forecast/` or `/api/forecast` route left in `add_routes`; 2, 9, 1, 6 routes in the modules); `t_either_module_imports_first` gains the eight modules.
- [ ] **Step 2:** The description; dry run; `--write`; text checks; references; release note.
- [ ] **Step 3: Run** every guard, the pin, the suites. **Commit.**

### Task 3: Headings, proof, recipe, check, push

- [ ] Stranded headings re-homed (comments only); `make move-proof` (nothing declared); `docs/ARCHITECTURE.md`; `make check` on 8941; self-review; push; the pull request.
