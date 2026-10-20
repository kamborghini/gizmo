# Files, the Finder drive and the move tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A committed, tested move tool; then Files and the Finder drive moved with it. Nothing anyone sees changes.

**Architecture:** `tools/move_area.py SPEC [--repo ROOT] [--write]` reads `tools/moves/<name>.json`, reports, and writes only when it finds no problem. It imports `sources` like the other tools and nothing from the app.

**Tech Stack:** Python 3.14 (`ast`, `symtable`); no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-20-files-and-move-tool-design.md`

## Global Constraints

- Nothing anyone sees changes; every request answered by the same handler.
- A pure move except Files' declared drop.
- A release note dated the merge day; British English; no dashes in UI copy.
- Browser on 8941; no agents; branch `refactor/files-webdav` from main 5f14564.

## Review Focus

1. **The tool moving a statement whose names span two areas**: pinned by the toy test (a statement binding two areas' names is a problem, nothing written).
2. **An alias that is a test's local**: pinned by the toy test (a test function with a local named like the alias stops the move).
3. **The Files memory copy after a restore or erasure**: pinned by `t_every_memory_copy_of_a_store_is_let_go` and the redact tests.
4. **`server.py`'s boot clean-up call**: pinned by the boot path in the suite (it imports `server`) and the tool re-pointing `server.py`.
5. **The Finder drive's pattern route** answering a request a gathered route used to: pinned by the proof's order rule.

---

### Task 1: The move tool

**Files:** `tools/move_area.py`, `tools/moves/README.md` (the description's fields), `tests/test_dispatch.py`, `Makefile` (`SAST` unchanged: tools are not app modules)

- [ ] **Step 1: Failing test** `t_move_area_moves_a_toy_area`: in a scratch copy of a made-up repository (a `copilot.py` with a settings line, a loader, a reader of it, a `global` reset of a memory copy, an annotation, three routes of which two belong to the area, a test that patches the loader), the tool with `--write`: the area's module holds the loader and the setting, the reader reads `x._x_load()`, the reset writes `x._x_mem = None` with no `global` line, `Optional` is imported, `add_routes` holds one `routes_x.register(mcp, registry)` where the first stood, the test patches `x._x_load`, `prove(base, head, declared=("reset",))` is `[]`, and both modules import first. And: a copilot function with a local `x` that reads a moved name makes the tool report and write nothing; a statement binding two areas' names likewise.
- [ ] **Step 2: Build** the tool from the five scripts.
- [ ] **Step 3: Run** the test. **Commit.**

### Task 2: Files and the Finder drive, moved by the tool

**Files:** `tools/moves/files.json`, `gizmo/files.py`, `gizmo/webdav.py`, `gizmo/routes/files.py` (written by the tool), `copilot.py`, `server.py`, split modules, `tests/test_dispatch.py`, `tests/test_frontend.py` (text checks), seeds, docs, `data/changelog.json`

- [ ] **Step 1: Failing tests:** `t_the_files_routes_are_gathered` (one `routes_files.register`, no `/api/files/` or `/dav` route left in `copilot.py`, 8 in the module); `t_either_module_imports_first` gains the three modules. Run: they fail.
- [ ] **Step 2:** By hand, Files' own drop (declared). Run the tool; settle what it reports in the description, not by hand-editing its output. Regenerate references; release note.
- [ ] **Step 3: Run** every guard, the label pin, the three suites. **Commit.**

### Task 3: Proof, recipe, check, push

- [ ] `make move-proof` (declared: the drop); `docs/ARCHITECTURE.md` (the tool in the recipe); `make check` on 8941; self-review; push; the pull request.
