# The leftovers go home Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The names earlier moves left in `copilot.py` join the modules they belong to. Nothing anyone sees changes.

**Architecture:** `tools/move_area.py` learns `"existing": true` areas; one description (`tools/moves/leftovers-home.json`).

**Tech Stack:** Python 3.14; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-21-leftovers-home-design.md`

## Global Constraints

- Nothing anyone sees changes; the frozen print routes and the stock bridge untouched.
- A pure move: nothing declared.
- A release note dated the merge day; British English; no dashes in UI copy.
- Browser on 8941; no agents; branch `refactor/piece-13` from piece 12 (33aa0b0, #57), brought up to main once #57 merges.

## Review Focus

1. **A moved helper reading its new module through its own name** (`orderbook.X` inside orderbook): pinned by the toy test and `t_no_module_looks_itself_up_by_name`.
2. **A floor module reaching above itself** once it takes a helper: pinned by the toy test's floor case and `t_the_floor_imports_nothing_above_it` (with `gizmo/clock.py` in its list).
3. **The sign-in door and the team helpers** (`_auth_guard`, `_team_guard`) after they move: pinned by the sign-in and team tests (unchanged).
4. **A shop erasure owed after an uninstall** still retried by the scheduler: pinned by the shop-redact tests.
5. **The dispatch desk's borrowed list**: `t_what_dispatch_borrows` shrinks to what it still reads from `copilot.py`.

---

### Task 1: The tool adds to an area moved earlier

- [ ] **Step 1: Failing test** `t_move_area_adds_to_an_area_moved_earlier` (an earlier area takes a helper: before its last imports, its own name dropped inside, its `core._x_helper` read bare; a floor module takes another and imports nothing above it; `prove()` is `[]`; every module first).
- [ ] **Step 2: Build** `"existing": true`.
- [ ] **Step 3: Run** the toy tests. **Commit.**

### Task 2: The move

- [ ] **Step 1: Failing tests**: `t_the_leftovers_are_home` (none of the moved names bound in `copilot.py`; each bound in its module); `t_either_module_imports_first` and `FLOOR` gain `gizmo/clock.py`.
- [ ] **Step 2:** The description; dry run; `--write`; text checks; `t_what_dispatch_borrows`; references; release note.
- [ ] **Step 3: Run** every guard, the suites. **Commit.**

### Task 3: Headings, proof, recipe, check, push

- [ ] Headings re-homed (comments only); `make move-proof` (nothing declared); `docs/ARCHITECTURE.md`; `make check` on 8941; self-review; push; the pull request.
