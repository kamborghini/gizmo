# Dispatch in its own module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Guards that stop a test going blind when code moves, then dispatch moved whole out of `copilot.py` into `gizmo/dispatch.py` and `gizmo/routes/dispatch.py`, proven a pure move by `make move-proof`; nothing anyone sees changes.

**Architecture:** `tools/sources.py` lists `copilot.py` and the modules split out of it, for the suites and the tools. The move is made by a one-off generator (scratch, not committed) that cuts the inventoried statements by line range, keeps their text and order, and prefixes cross-module global reads found with `symtable` (`core.NAME` in the moved code, `dispatch.NAME` in what stays). `tools/move_proof.py` re-parses base and head and compares syntax trees with those prefixes read as plain names.

**Tech Stack:** Python 3.14 (`ast`, `symtable`, `tokenize`), the two suites' own harnesses; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-20-dispatch-module-design.md`

## Global Constraints

- Nothing anyone sees changes: same routes in the same order, same responses, same logs (logger `shopify_mcp.copilot`), same settings.
- A pure move: no statement of dispatch or of what stays is reworded beyond the `core.`/`dispatch.` prefix.
- Frozen: print functions and print CSS byte for byte; the printed labels; the Production Manager queue; the Quote Engine.
- A release note with the first app change, dated the merge day; no dashes in UI copy; British English.
- Browser runs on 8941 (main checkout); no agents (self-review); branch `refactor/dispatch-module` from main 51d62b0.

## Review Focus

1. **A name read across the cycle at import time** (a default argument, a decorator, a module constant built from a `core` name) crashes the app at boot on Railway. Pinned by Task 2's fresh-interpreter test importing `gizmo.dispatch` first and `copilot` first, and the boot check.
2. **A path no test drives** (the AI address reader, the credential boot, the margin backfill) left reading a bare name that moved: a NameError in production only. Pinned by Task 2's `t_the_split_modules_read_no_unbound_name` (every global read in `gizmo/` is bound there, imported, or a builtin).
3. **A local that shares a global's name** (a parameter called `registry` or `logger`) prefixed by mistake. Pinned by Task 3: the proof accepts a `core.`/`dispatch.` prefix only where the base's syntax tree read a module global at that spot.
4. **A `global` rebinding a name the other module now owns** would write to a dead copy. Pinned by the generator turning those into attribute assignments and by Task 3's proof refusing a `global` that names another module's name.
5. **Route order**: an overlapping path answered by a different handler. Pinned by `register` called where the routes stood, the proof's `add_routes` check, and `docs/API.md` keeping its row order.

---

### Task 1: No test can go blind

**Files:** `tools/sources.py` (create), `tests/test_dispatch.py`, `tests/test_frontend.py`, `tools/route_reference.py`, `tools/env_reference.py`, `Makefile`, `.github/workflows/tests.yml`

**Interfaces:**
- Produces: `tools/sources.py`: `ROOT: str`; `COPILOT_FILES: list[str]` (repo-relative: `copilot.py`, then `gizmo/**/*.py` sorted); `APP_MODULES: list[str]` (every app module file: `server.py`, `copilot.py`, the root integration and helper modules the Makefile scans today, then `gizmo/**/*.py`); `copilot_source() -> str` (the `COPILOT_FILES` texts joined with `"\n"`).

- [ ] **Step 1: Failing tests** in the dispatch suite (above its closing run loop):
  - `t_no_test_patches_a_name_nobody_reads`: AST over `tests/**/*.py`. (a) each `M.NAME = …` with `M` an imported app module binds NAME at `M`'s top level or by `global`, and `M` reads NAME; (b) no app module has `from <app module> import NAME` where NAME is patched there by a test or rebound by `global` in its owner; (c) for each patched `M.NAME` where another app module binds and reads its own NAME, the same test function patches that one too, or `(M, NAME, other)` is in `SHARED_COPIES` with a reason. Fails listing each offender with file and line.
  - `t_nothing_reads_copilot_py_by_name`: no file under `tests/` or `tools/` other than `tools/sources.py` holds the literal `"copilot.py"`.
  - `t_the_security_scans_cover_every_app_module`: the Makefile's `SAST_FILES` and CI's bandit line, as sets of paths (a directory covers the files under it), contain every `APP_MODULES` entry.
- [ ] **Step 2: Run** `make test`: the first fails on the two existing cases (`server.SHOPIFY_STORE`, `copilot.httpx`); the second lists the 59 checks, the date test and the two tools.
- [ ] **Step 3: Build** `tools/sources.py`; point every listed check, the release-note date test (`git log` over `COPILOT_FILES` plus what it covers now) and both tools' file reading at it (`route_reference`'s `MODULES` gains the `gizmo` files by path; `env_reference` likewise, banners still from `copilot.py`). Read the tests behind the two existing cases: fix a blind one, else add it to `SHARED_COPIES` with its reason. Generated docs unchanged (`--check` both).
- [ ] **Step 4: Run** the three guards, `make test`, `make test-frontend`, both `--check`s: green, test counts +3. **Commit.**

### Task 2: Dispatch in its own module

**Files:** `gizmo/__init__.py`, `gizmo/config.py`, `gizmo/dispatch.py`, `gizmo/routes/__init__.py`, `gizmo/routes/dispatch.py` (create), `copilot.py`, `tests/test_dispatch.py`, `tests/browser/seed/*.py` (if they name moved names), `server.py` (if it names moved names), `Makefile`, `.github/workflows/tests.yml`, `docs/API.md`, `docs/ENVIRONMENT.md`, `data/changelog.json`

**Interfaces:**
- Consumes: `tools/sources.py` (Task 1).
- Produces: `gizmo.config._env_num` (moved as is); `gizmo.dispatch` (the inventory below, names unchanged; `import copilot as core`; logger `logging.getLogger("shopify_mcp.copilot")`); `gizmo.routes.dispatch.register(mcp, registry) -> None`; `copilot` binds `dispatch` and `routes_dispatch` by `from gizmo import dispatch` and `from gizmo.routes import dispatch as routes_dispatch`.

**Inventory** (top-level statements of base `copilot.py`, with their leading comments): 2028 to 2397; 2601 to 2730 and 2764 to 2797 (the London helpers 2731 to 2761 stay); 7567 to 9620; 19787 to 19864 (`_print_cors` stays); the shipping section's banner. The error log, backups and weekly snapshot (2398 to 2600), production state, impact and memory (2798 to 3010), missing production and liability (9621 to 9757) stay. Routes: the 15 handlers and `_finish_cancel` at 26620 to 27289. `_env_num` to `gizmo/config.py`.

- [ ] **Step 1: Failing tests:**
  - `t_what_dispatch_borrows`: the set of `core.NAME` attributes read in `gizmo/dispatch.py` and `gizmo/routes/dispatch.py` equals `BORROWED` (written from the generator's output, sorted).
  - `t_the_split_modules_read_no_unbound_name`: with `symtable`, every global read in each `gizmo/` module is bound at its top level, imported, or a builtin.
  - `t_either_module_imports_first`: fresh interpreters (`subprocess`, the suite's env) run `import gizmo.dispatch` and `import copilot`, each first: exit 0.
  - `t_dispatch_routes_register_in_place`: `copilot.add_routes` source holds `routes_dispatch.register(mcp, registry)` between the route before 26620 and the route after 27289, and no `/api/dispatch`, `/api/shipping`, `/api/custom`, `/api/eori` or margin route remains in `copilot.py`.
- [ ] **Step 2: Run** `make test`: the four fail (no `gizmo` package).
- [ ] **Step 3: Generate** with the scratch script, then by hand: move the inventory text in order; prefix with `symtable` (a moved statement's global read of a name that stays becomes `core.NAME`; a staying statement's global read of a moved name becomes `dispatch.NAME`; `global X` plus assignment across the line becomes an attribute assignment); copy the imports each module reads; route handlers keep their decorators inside `register`. Re-point the tests that patch or read moved names (`copilot.X` to `dispatch.X`; the frozen-clock test also freezes `dispatch.datetime`). Add `gizmo` to `SAST_FILES` and CI's bandit list. Regenerate `docs/API.md` (only the 15 handlers' module changes) and `docs/ENVIRONMENT.md` (same variables). Release note "The dispatch desk on its own" (copy in the spec).
- [ ] **Step 4: Run** the four tests, Task 1's guards, `make test`, `make test-frontend`, `make test-forecast`, both `--check`s; start the app (`make run` env, a spare port) and read `/healthz`. **Commit.**

### Task 3: The proof, the recipe, check and push

**Files:** `tools/move_proof.py` (create), `Makefile` (`move-proof`, `BASE ?= origin/main`), `tests/test_dispatch.py`, `docs/ARCHITECTURE.md`

**Interfaces:**
- Produces: `python tools/move_proof.py --base <ref>`: exit 0 and "nothing but the move" when every base top-level statement of `copilot.py` appears once in the head's `copilot.py` or `gizmo/**/*.py` with an identical `ast.dump` (no attributes) after reading `core.NAME`/`dispatch.NAME`/`routes_dispatch.NAME` as `NAME` wherever the base read NAME as a module global at that spot, and `add_routes` differs only by the moved handlers giving way to the one `register` call; else exit 1 naming each statement added, lost or changed.

- [ ] **Step 1: Failing test** `t_move_proof_is_wired`: the Makefile has `move-proof` with `BASE ?= origin/main`; the tool exists and, run on a hand-made base/head pair in a scratch git repo (a function moved with a prefix: pass; a moved function with one changed constant: fail naming it; a local wrongly prefixed: fail), answers as specified.
- [ ] **Step 2: Build** the tool and target; run `make move-proof BASE=origin/main`: "nothing but the move". A throwaway one-character change in moved code: the report names it. Undo.
- [ ] **Step 3:** `docs/ARCHITECTURE.md`: the `gizmo/` package, the two directions (`core.` and `dispatch.`), and "Moving an area out" (inventory, generator, prefixes, re-pointed patches, the guards, `make move-proof`, `t_what_dispatch_borrows` shrinking).
- [ ] **Step 4:** `make check` (browser on 8941); self-review against the Review Focus; push. The pull request follows (Auto-fix, squash auto-merge).
