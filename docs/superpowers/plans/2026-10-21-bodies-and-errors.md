# Request bodies checked at the door, and errors that say why they are quiet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The 24 silent broad handlers say why; a body check at the door; models on the 16 routes that break or keep junk on a wrong type; the rest counted.

**Architecture:** `tools/broad_excepts.py` and a guard; `gizmo/bodies.py` on the floor; `gate._guard(model=...)`; models beside each area's routes; `tools/route_reference.py` names them.

**Tech Stack:** Python 3.14, pydantic 2.13 (already a dependency).

**Spec:** `docs/superpowers/specs/2026-10-21-bodies-and-errors-design.md`

## Global Constraints

- A request the page sends today is answered exactly as before (the browser suite proves every screen); the route reads its body as before.
- A wrong type is a 400 naming the field, in plain words, no dashes.
- The frozen print routes, the PM queue and the Quote Engine untouched.
- A release note dated the merge day; British English.
- Browser on 8941; no agents; branch `stage5/bodies-and-errors` from main 4cb6e6f.

## Review Focus

1. **A model stricter than what the page sends** (a number where the page sends text, a missing optional field): pinned by the browser suite (every screen) and every route test unchanged.
2. **An `op` the model does not know** reaching the route as before: pinned by `t_a_body_model_checks_only_what_it_names`.
3. **A silent handler made loud** where silence was the point (a log line in a hot loop): each of the 24 read, the choice written in the ledger.
4. **The ratchet** when a route gains a model: `t_write_routes_check_their_bodies` fails until it leaves the list.
5. **The door's other answers** (401, 403, the AI window) unchanged when `model=` is given: pinned by the door tests and the body check running last.

---

### Task 1: Silent errors say why

- [ ] **Step 1: Failing test** `t_no_error_is_swallowed_without_a_reason` (via `tools/broad_excepts.py`: every silent broad handler carries a comment): fails naming the 24.
- [ ] **Step 2:** Read each; a reason, a log line or a narrower exception. **Step 3: Run.** **Commit.**

### Task 2: The body check at the door

- [ ] **Step 1: Failing tests** `t_a_body_model_checks_only_what_it_names` (the kinds accept what the page sends and refuse an object or a list where a scalar belongs; other fields pass; per-op models check only their op; the refusal names the field) and `t_the_door_refuses_a_wrong_type_last` (through a route: no session is still a 401).
- [ ] **Step 2:** `gizmo/bodies.py`; `gate._guard(model=)`. **Step 3: Run.** **Commit.**

### Task 3: The seven routes that broke

- [ ] **Step 1: Failing test** `t_a_wrong_type_is_refused_by_name_not_a_server_error` (each of the seven: 400 naming the field). **Step 2:** Their models. **Step 3: Run** with their route tests. **Commit.**

### Task 4: The routes that kept junk

- [ ] **Step 1: Failing test** `t_a_wrong_type_is_refused_before_anything_is_kept` (each of the ten: 400, and the store unchanged). **Step 2:** Their models. **Step 3: Run.** **Commit.**

### Task 5: The count, the reference, the check

- [ ] `t_write_routes_check_their_bodies` (the list of routes without a model, exact); `docs/API.md` Body column; `docs/ARCHITECTURE.md`; release note; `make check` on 8941; self-review; push; the pull request.
