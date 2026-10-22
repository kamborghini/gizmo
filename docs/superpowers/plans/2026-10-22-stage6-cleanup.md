# Stage 6 cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Areas stop importing copilot.py; the docs describe the code as it is; the dispatch suite is in sections.

**Architecture:** `gizmo/background.py` on the floor; `run_label_coverage` to `gizmo/production.py`; an import-order check over every module; ARCHITECTURE.md rewritten, the move how-to beside its tool, `docs/README.md`; `tests/dispatch/` loaded by `tests/test_dispatch.py`.

**Tech Stack:** Python 3.14; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-22-stage6-cleanup-design.md`

## Global Constraints

- Nothing anyone sees changes; the frozen print routes keep their source and bytes; the stock bridge and the Quote Engine untouched.
- A release note dated the merge day for an app change; British English; no business name in committed docs.
- Browser on 8941; no agents; branches from main in turn.

## Review Focus

1. **A module that read copilot at load time** once its import goes: pinned by the import check over every module.
2. **A test patching `copilot._spawn_bg`** that no longer reaches the work it watched: re-pointed to `background.spawn`; the shared-copies guard.
3. **Docs that name a path or test that does not exist**: every backticked path in ARCHITECTURE.md checked by a test.
4. **A test lost or reordered in the split**: names and order compared with the file before; each function's text compared.
5. **The browser rig's prelude** after the split: the browser suite in `make check`.

---

### Part 1 (`stage6/copilot-ties`): the last ties

- [ ] **Failing tests**: `t_only_the_stock_bridge_reads_copilot` (AST over every app module); `t_background_work_has_its_own_home` (spawn holds a reference, answers False with no loop, the CRM's set is gone). **Build**: background.py; callers; run_label_coverage moved (`make move-proof`); imports removed; dead names; the import check generated and parallel; BORROWED gone. **Run**, release note, `make check`, PR.

### Part 2 (`stage6/docs`): docs as the code is

- [ ] **Failing test** `t_the_architecture_names_only_what_exists` (every backticked repo path in ARCHITECTURE.md and README exists; no "being split"). **Build**: the rewrite; `tools/moves/README.md`; `docs/README.md`. **Run**, PR.

### Part 3 (`stage6/suite-sections`): the suite in sections

- [ ] **Failing test** `t_the_suite_is_in_sections` (the runner loads `tests/dispatch/*.py`; no section over a size). **Build**: a split script driven by the test names' order; re-point what reads the file. **Proof**: names and order identical; each function's text identical. **Run**, `make check`, PR.
