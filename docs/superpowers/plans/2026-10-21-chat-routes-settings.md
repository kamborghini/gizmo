# The chat routes and the shop settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The chat's tools on the chat module, the chat and usage routes out, the shop settings on the floor. Nothing anyone sees changes.

**Architecture:** One hand change (declared): `add_routes` hands the chat module its tools. Then `tools/move_area.py` (learning to bind an existing module) with `tools/moves/chat-routes-settings.json`.

**Tech Stack:** Python 3.14; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-21-chat-routes-settings-design.md`

## Global Constraints

- Nothing anyone sees changes; the frozen print routes keep their bytes; the stock bridge untouched.
- One declared change (the chat's tools on the chat module); the rest a pure move.
- A release note dated the merge day; British English; no dashes in UI copy.
- Browser on 8941; no agents; branch `refactor/piece-15` from piece 14 (a47aca6, #59), brought up to main once #59 merges.

## Review Focus

1. **A chat turn enforcing someone else's tabs** once the tools live on the chat module: pinned by `t_a_chat_turn_runs_the_askers_tools_only`, written first, and `t_chat_cannot_read_customers_a_tab_denies`.
2. **The frozen print routes** reading the moved secret and base address: pinned by the print freeze and guard (b) (copies only of names no test patches).
3. **The frame rule's shop** (tests patch it): pinned by the frame-ancestors test, re-pointed to `config`.
4. **A floor module reaching above itself** once it takes the settings: pinned by `t_the_floor_imports_nothing_above_it`.
5. **The chat stream** after it moves: pinned by the stream tests.

---

### Task 1: The pin

- [ ] `t_a_chat_turn_runs_the_askers_tools_only` (a member without the Customers tab, through `/api/chat`, with the run faked: the tool is refused inside the turn, and the turn is handed the chat's tools). Passes now; fails when the turn is bound to nobody (mutation checked). **Commit.**

### Task 2: The chat's tools on the chat module

- [ ] `add_routes` sets `assistant._chat_registry` and `assistant._chat_tools`; `dispatch_for(uid)` in `gizmo/chat.py`; the chat routes read them. `t_the_chat_tool_gate_is_bound_per_run` and the nested helpers' list updated. Run the pin and the chat tests. **Commit.**

### Task 3: The tool binds an existing module copilot.py does not bind by name

- [ ] **Failing test**: in `t_move_area_adds_to_an_area_moved_earlier`, a toy module copilot.py imports a name from but does not bind; an `existing` area for it adds the module's binding to copilot.py and to the suite's prelude. **Build. Run. Commit.**

### Task 4: The move

- [ ] **Failing tests**: `t_the_chat_routes_and_shop_settings_have_moved`. The description (the settings to `config`, copies of the secret and the base address; the chat and usage routes to `gizmo/routes/chat.py`); dry run; `--write`; `SHARED_COPIES` re-keyed; references; release note. **Run. Commit.**

### Task 5: Headings, proof, recipe, check, push

- [ ] Headings (comments only); `make move-proof` (declared: the hand change's statements); `docs/ARCHITECTURE.md` (stage 4's end); `make check` on 8941; self-review; push; the pull request.
