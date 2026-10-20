# The floor modules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The store, the error log and the AI client move out of `copilot.py` into `gizmo/store.py`, `gizmo/errors.py` and `gizmo/ai.py`, modules that import nothing above them; the store stops naming the CRM; the guards and `make move-proof` learn about `globals()` and declared changes. Nothing anyone sees changes.

**Architecture:** As piece 1: a one-off generator (scratch) cuts the inventoried statements whole and prefixes cross-module global reads found with `symtable`, now with three destinations and the desk's modules as inputs too (their `core.NAME` for a moved name becomes the new module's alias). Aliases: `jsonstore`, `errors`, `claude`.

**Tech Stack:** Python 3.14 (`ast`, `symtable`); no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-20-floor-modules-design.md`

## Global Constraints

- Nothing anyone sees changes: same responses, logs (`shopify_mcp.copilot`), settings, routes and order.
- A pure move except the declared CRM hook (`_forget_store`, `when_forgotten`, `_forget_hooks`, `_crm_store_forgotten` and its registration).
- Frozen: print functions and print CSS byte for byte (the print route reads none of the moved names).
- A release note dated the merge day; no dashes in UI copy; British English.
- Browser on 8941; no agents (budget spent, self-review); branch `refactor/floor-modules` from main 87eb3d1.

## Review Focus

1. **A floor module that imports `copilot.py` at call time** (a lazy import inside a function) would hide the cycle from an import-graph check. Pinned by Task 1's guard reading every import statement in the module, not only top-level ones.
2. **The CRM hook reading `CRM_PATH` once at registration**: a test or a restore that repoints the CRM's path would stop dropping the board. Pinned by Task 2's hook test, which repoints `CRM_PATH` after import.
3. **A moved `global` (`_client`, `_spend`, `_AI_LAST_FAIL`) rebound from `copilot.py`** would write a dead copy. Pinned by the generator's report (a `global` across the line is a problem) and guard (b).
4. **`_drop_memory_stores` still clearing `copilot.py`'s caches**: pinned by the existing redact/restore tests and by it staying in `copilot.py` (the new guard fails if it moves).
5. **A test patching a moved AI name on `copilot`** (45 assignments) left behind: pinned by `t_no_test_patches_a_name_nobody_reads` (a).

---

### Task 1: The guards and the proof learn

**Files:** `tests/test_dispatch.py`, `tools/move_proof.py`, `Makefile`

**Interfaces:**
- Produces: `prove(base, head, stats=None, declared=())`: statements whose name (def or class name, assignment target, or the called function of an expression statement) is in `declared` are left out of the match and returned in `stats["declared"]` as `(name, before_src, after_src)`; a statement in a package module that calls `globals()`, `vars()` (no arguments) or reads `sys.modules[__name__]` is a problem. CLI `--declared a,b` prints each declared change as a unified diff. `make move-proof BASE=… DECLARED=…`.

- [ ] **Step 1: Failing tests.**
  - `t_no_module_looks_itself_up_by_name`: no file in `gizmo/` calls `globals()`, `vars()` without arguments, or names `sys.modules[__name__]`.
  - `t_the_floor_imports_nothing_above_it`: `FLOOR = ["gizmo/config.py", "gizmo/store.py", "gizmo/errors.py", "gizmo/ai.py"]` all exist; for each, every import statement anywhere in it, followed through the app modules it reaches, never reaches `copilot`, `server`, `gizmo.dispatch` or `gizmo.routes.*`.
  - `t_move_proof_is_wired` gains: a declared change passes and comes back in `stats["declared"]`; a moved function calling `globals()` fails naming it.
- [ ] **Step 2: Run:** the floor test fails (no `gizmo/errors.py`, `gizmo/ai.py`); the proof cases fail; the `globals()` guard passes (nothing in `gizmo/` uses it today).
- [ ] **Step 3: Build** `declared` and the `globals()` check in `tools/move_proof.py`; `DECLARED ?=` in the Makefile.
- [ ] **Step 4: Run** the proof test: passes. **Commit.**

### Task 2: The move

**Files:** `gizmo/store.py`, `gizmo/errors.py`, `gizmo/ai.py` (create the last two), `copilot.py`, `gizmo/dispatch.py`, `gizmo/routes/dispatch.py`, `tests/test_dispatch.py`, `tests/browser/seed/*.py` (if they name moved names), `docs/API.md`, `docs/ENVIRONMENT.md`, `data/changelog.json`

**Interfaces:**
- Consumes: Task 1's guards.
- Produces: `gizmo.store.when_forgotten(fn: Callable[[str], None]) -> None`; `copilot._crm_store_forgotten(path: str) -> None` registered at import; aliases `from gizmo import store as jsonstore`, `from gizmo import errors`, `from gizmo import ai as claude` in every module that reads them.

**Inventory:** store: `_poisoned_stores`, `_load_json_store`, `_store_writable`, `_json_cache`, `_cached_paths`, `_stat_key`, `_load_json_cached`, `_forget_store`, `_write_json_store`, `_write_private_json`. errors: `ERRORS_PATH`, `ERRORS_MAX`, `_record_error`, `_recent_errors`. ai: the 52 names of the AI client's closure less the store and the error log (listed by the generator; every top-level statement binding one of them moves whole, and a statement binding names for two destinations is a problem to settle by hand).

- [ ] **Step 1: Failing tests.**
  - `t_forgetting_the_crm_store_drops_its_board`: with `copilot.CRM_PATH` pointed at a scratch path after import, a kept board is dropped by `jsonstore._forget_store(copilot.CRM_PATH)` and kept by forgetting another path.
  - `t_what_dispatch_borrows`: `BORROWED` loses the 13 names now read from the floor (29 remain).
  - Run: both fail (`jsonstore` unknown; the desk still reads them from `core`).
- [ ] **Step 2: Generate** with the scratch script, then by hand the declared hook. Re-point tests (`copilot.X` to `jsonstore.X`, `errors.X`, `claude.X` for moved names, aliases included). Regenerate `docs/API.md` (expected unchanged) and `docs/ENVIRONMENT.md` (moved settings' headings only). Release note.
- [ ] **Step 3: Run** all of piece 1's and Task 1's guards, the three suites, both `--check`s. **Commit.**

### Task 3: Proof, recipe, check, push

**Files:** `docs/ARCHITECTURE.md`

- [ ] `make move-proof BASE=origin/main DECLARED=_forget_store,when_forgotten,_forget_hooks,_crm_store_forgotten`: nothing but the move, the declared changes shown.
- [ ] `docs/ARCHITECTURE.md`: the floor (`gizmo/config.py`, `store.py`, `errors.py`, `ai.py`), imported directly by every area; the recipe's step on `globals()` and declared changes.
- [ ] `make check` (browser on 8941); self-review against the Review Focus; push; the pull request (Auto-fix, squash auto-merge).
