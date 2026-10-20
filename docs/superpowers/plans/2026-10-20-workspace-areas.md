# Skills, memory, store knowledge and the chat loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Skills, memory, store knowledge and the chat loop out of `copilot.py`, the first three with their routes. Nothing anyone sees changes.

**Architecture:** `tools/move_area.py` with one description (`tools/moves/workspace.json`); the tool first learns to refuse a route that reads a value `add_routes` binds.

**Tech Stack:** Python 3.14; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-20-workspace-areas-design.md`

## Global Constraints

- Nothing anyone sees changes; every request answered by the same handler; the frozen print routes untouched.
- A pure move: nothing declared.
- A release note dated the merge day; British English; no dashes in UI copy.
- Browser on 8941; no agents; branch `refactor/workspace-areas` from e7ec20a (piece 7, #48), brought up to main once #48 merges.

## Review Focus

1. **A chat turn missing its skills, memory or knowledge** in the system text after the move: pinned by the chat and skills tests (unchanged) reaching `skillbook.`, `memory.` and `knowledge.` through the routes that stay.
2. **A route reading a value `add_routes` binds** after it moved: pinned by the toy test's new case and `t_the_split_modules_read_no_unbound_name`.
3. **A setting read at load before `copilot.py` has it** (the system prompt, the skill caps): pinned by the tool's load-time check and `t_either_module_imports_first` with the seven new modules.
4. **The scheduled audits** reading memory and the profile into their prompts: pinned by the schedule tests.
5. **The browser's workspace seed** patching a moved name: pinned by guard (a) and the browser suite.

---

### Task 1: The tool refuses a route reading a value add_routes binds

- [ ] **Step 1: Failing test**: in `t_move_area_moves_routes_after_their_area`, a toy `add_routes` that assigns `built = registry` and a moving route reading `built`: the tool reports `reads add_routes' built` and writes nothing.
- [ ] **Step 2: Build**: the names a moved route may not read are every local of `add_routes` (its symbol table), but `mcp`, `registry` and the group's helpers.
- [ ] **Step 3: Run** both toy tests. **Commit.**

### Task 2: Skills, memory, store knowledge and the chat loop

- [ ] **Step 1: Failing tests**: `t_the_workspace_routes_are_gathered` (one register call each for skills, memory, knowledge; no `/api/skills`, `/api/memory` or `/api/learn` route left in `add_routes`; 2, 1, 2 routes in the modules; `/api/chat` and `/api/chat/stream` still in `add_routes`); `t_either_module_imports_first` gains the seven modules.
- [ ] **Step 2:** The description; dry run; settle in the description; `--write`. Text checks; references; release note.
- [ ] **Step 3: Run** every guard, the label pin, the suites. **Commit.**

### Task 3: Headings, proof, recipe, check, push

- [ ] The five stranded headings rewritten (comments only); `make move-proof` (nothing declared); `docs/ARCHITECTURE.md`; `make check` on 8941; self-review; push; the pull request.
