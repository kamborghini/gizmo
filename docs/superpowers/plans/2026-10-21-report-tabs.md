# The AI's instructions, SEO and keywords, and the overview and customer reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The AI's instructions onto the floor; SEO and keywords, and the overview and customer reports, out of `copilot.py` with their routes. Nothing anyone sees changes.

**Architecture:** `tools/move_area.py` with one description (`tools/moves/report-tabs.json`); its dry run first learns to list names left behind for the moving code.

**Tech Stack:** Python 3.14; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-21-report-tabs-design.md`

## Global Constraints

- Nothing anyone sees changes; every request answered by the same handler; the frozen print routes untouched.
- A pure move: nothing declared.
- A release note dated the merge day; British English; no dashes in UI copy.
- Browser on 8941; no agents; branch `refactor/report-tabs` from main 7c01dc7.

## Review Focus

1. **A report asking without its instructions or the writing style** after the prompts move: pinned by `t_the_reports_ask_with_their_instructions`, written before the move.
2. **An outside page fetched without the guard** after the keyword scan moves: pinned by the guard's tests (unchanged).
3. **The floor reaching above itself** (`prompts` importing an area): pinned by `t_the_floor_imports_nothing_above_it` with `gizmo/prompts.py` in its list.
4. **The scheduled audits and the chat's tools** reaching the moved runs and tool builders: pinned by `t_the_scheduled_audits_carry_memory_knowledge_and_skills` and the boot of `add_routes` in every route test.
5. **Store knowledge reading the site** through `seo.`: pinned by the store knowledge tests and `t_the_split_modules_read_no_unbound_name`.

---

### Task 1: The dry run lists names left behind for the moving code

- [ ] **Step 1: Failing test**: in `t_move_area_moves_a_toy_area`, a toy helper read only by a moving statement shows in the dry run's report as left behind; a staying name another staying statement reads does not.
- [ ] **Step 2: Build**: a note per staying top-level name whose every reader (top-level statements, routes, other files) moves.
- [ ] **Step 3: Run** the toy tests. **Commit.**

### Task 2: The instructions, SEO and keywords, the overview and customer reports

- [ ] **Step 1: The pin first** (passes now): `t_the_reports_ask_with_their_instructions` (the overview's and keywords' model calls, faked, each carry their prompt's wording, the writing style and the context handed in). **Failing tests**: `t_the_report_routes_are_gathered` (one register call each; no `/api/seo`, `/api/keyword`, `/api/overview`, `/api/cache`, `/api/reorder-radar`, `/api/customers` or `/api/customer-tags` route left in `add_routes`; 3 and 5 routes in the modules; `/api/product` still there); `t_either_module_imports_first` gains the five modules; `FLOOR` gains `gizmo/prompts.py`.
- [ ] **Step 2:** The description; dry run; settle what it reports and lists; `--write`. Text checks; references; release note.
- [ ] **Step 3: Run** every guard, the label pin, the suites. **Commit.**

### Task 3: Proof, recipe, check, push

- [ ] `make move-proof` (nothing declared); `docs/ARCHITECTURE.md`; `make check` on 8941; self-review; push; the pull request.
