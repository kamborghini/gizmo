# Accounts, sign-in and the door Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each module lets go of its own memory copies (no `globals()`); accounts and sign-in move to `gizmo/team.py` with their routes in `gizmo/routes/team.py`; the door and the activity log move to `gizmo/gate.py` and `gizmo/activity.py`. Nothing anyone sees changes.

**Architecture:** Task 1 is a hand change on today's code. Task 2 is the move by a third one-off generator (scratch): name inventories for three destinations that may borrow from `copilot.py` (`import copilot as core`, last), a route block, copies in `copilot.py` for the six names the frozen print route reads, and the desk re-pointed from `core.` to the new aliases.

**Tech Stack:** Python 3.14 (`ast`, `symtable`); no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-20-team-and-gate-design.md`

## Global Constraints

- Nothing anyone sees changes: same answers, sign-in behaviour, lockouts, sessions, logs, routes and order.
- A pure move except the declared memory change (`_memory_stores`, `_drop_memory_stores`, `holds_in_memory`, `_holders`, `_let_go_in_memory`).
- Frozen: the print route's bytes (`t_the_printed_sheets_do_not_change`); print CSS and functions.
- A release note dated the merge day; British English; no dashes in UI copy.
- Browser on 8941; no agents (budget spent; self-review); branch `refactor/accounts-door` on `refactor/floor-modules` (#42), main merged in once #42 lands.

## Review Focus

1. **A restore or erasure leaving an account or session in memory** after the move. Pinned by Task 1's behavioural test (every `_..._mem` in every module) and the existing restore and redact tests.
2. **A drop reading a path at registration** (tests repoint `USERS_PATH`): pinned by Task 1's test repointing `USERS_PATH` after import.
3. **The sign-in rate window and lockouts** (module state `_login_hits`, `_locked_now`) read from two places after the move: pinned by the guards (no copy of patched or rebound names) and the lockout tests.
4. **A frozen-route copy of a name a test patches**: pinned by guard (b) and the print freeze.
5. **The route reference's tab map** read from the wrong module: pinned by `docs/API.md` changing only the 10 handlers' module.

---

### Task 1: Each module lets go of its own memory copies

**Files:** `gizmo/store.py`, `copilot.py`, `tests/test_dispatch.py`

**Interfaces:**
- Produces: `jsonstore.holds_in_memory(drop: Callable[[Optional[set]], list]) -> None`; `jsonstore._drop_memory_stores(paths: Optional[set] = None) -> None`; in `copilot.py` `_let_go_in_memory(paths) -> list` (mail, files, users, sessions, work, activity, loans) registered at import.

- [ ] **Step 1: Failing test** `t_every_memory_copy_of_a_store_is_let_go` (replaces `t_every_memory_copy_of_a_store_is_on_the_one_list`): every `^_[a-z_]+_mem` global in every module of `COPILOT_FILES`, set to a sentinel, is `None` after `jsonstore._drop_memory_stores()`; with `copilot.USERS_PATH` repointed after import, `jsonstore._drop_memory_stores({copilot.USERS_PATH})` lets go of the users copy only. Run: fails (`jsonstore` has no `_drop_memory_stores`).
- [ ] **Step 2: Build**: the store's holders and drop; `copilot._let_go_in_memory` with explicit `global` assignments, registered at import; the three callers call `jsonstore._drop_memory_stores`; `_memory_stores` and copilot's `_drop_memory_stores` go.
- [ ] **Step 3: Run** the test, the restore and redact tests, `t_no_module_looks_itself_up_by_name`, the suite. **Commit.**

### Task 2: The move

**Files:** `gizmo/team.py`, `gizmo/gate.py`, `gizmo/activity.py`, `gizmo/routes/team.py` (create), `copilot.py`, `gizmo/dispatch.py`, `gizmo/routes/dispatch.py`, `tools/route_reference.py`, `tests/test_dispatch.py`, `tests/browser/seed/*.py`, `docs/API.md`, `docs/ENVIRONMENT.md`, `data/changelog.json`

**Inventory** (by name; each statement moves whole with its leading comment):
- team: `_verify_session_token`, `AUTH_REFUSALS`, `_authorize`, `USERS_PATH`, `SESSIONS_PATH`, `SESSION_HOURS`, `SESSION_MAX_DAYS`, `MFA_FAIL_LIMIT`, `LOGIN_FAIL_LIMIT`, `_PW_DUMMY` (both), `LOGIN_LOCK_MINUTES`, `LOGIN_LOCK_STEPS`, `LOGIN_MAX_PER_MIN`, `ROLE_LEVELS`, `_users_mem`, `_sessions_mem`, `_hash_pw`, `_check_pw`, `_note_wrong_password`, `_locked_now`, `_users_default`, `_load_users`, `_write_users`, `_load_sessions`, `_write_sessions`, `SESSIONS_PER_USER`, `_mfa_tickets`, `_mfa_tries`, `MFA_TICKET_SECONDS`, `MFA_MAX_TRIES`, `_mfa_ticket`, `_mfa_ticket_uid`, `_mfa_ticket_spend`, `_new_session`, `_session_uid`, `_live_uid`, `_uid_has_tab`, `_drop_sessions`, `_sessions_sweep`, `_team_user`, `_team_role`, `_team_level`, `_team_name`, `_team_names`, `_team_counts`, `MASTER_RESET_MINUTES`, `_master_reset_done`, `_master_reset_check`, `TAB_KEYS`, `OPT_IN_TABS`, `DEFAULT_TABS`, `_user_tabs`, `_login_hits`. Routes: `/api/auth/*` and `/api/team/*` (21669 to 22298).
- gate: `_API_HEADERS`, `RATE_WINDOW`, `RATE_MAX_CLIENT`, `RATE_MAX_GLOBAL`, `MAX_BODY_BYTES`, `_json`, `_json_dumps_like_starlette`, `_json_body`, `_json_spliced`, `_rl_hits`, `_rl_global`, `_client_key`, `_window_ok`, `_window_hits`, `_pre_checks`, `_ai_slot`, `_guard`, `_read_json_capped`, `_OPEN_API`, `_TAB_ROUTES`, `_tab_denied`.
- activity: `ACTIVITY_PATH`, `ACTIVITY_MAX`, `_events_mem`, `_events_dirty`, `_events_flush_pending`, `_load_events`, `_events_flush`, the `atexit.register(_events_flush)` statement, `_login_noise`, `LOGIN_NOISE_ROWS`, `_deny_noise`, `DENY_NOISE_ROWS`, `_track_denied`, `_track_login_refusal`, `_track_login_noise`, `_track`.
- copies in `copilot.py` (read bare there): `_API_HEADERS`, `_pre_checks`, `_verify_session_token`, `_live_uid`, `_uid_has_tab`, `_track`.

- [ ] **Step 1: Failing tests:** `t_what_dispatch_borrows` without `_guard`, `_json`, `_team_level`, `_track`, `_window_ok`, `ROLE_LEVELS` (23 left); `t_the_team_routes_register_in_place` (`routes_team.register(mcp, registry)` between `/api/oauth`-side neighbours of the block, no `/api/auth/` or `/api/team/` route left in `copilot.py`, 10 in the module); `t_either_module_imports_first` gains `gizmo.team`, `gizmo.gate`, `gizmo.activity` first. Run: they fail.
- [ ] **Step 2: Generate**, then by hand: split `_let_go_in_memory` (users and sessions to team, events to activity) as declared; the route reference reads `_TAB_ROUTES` and `_OPEN_API` from the family. Re-point tests and seeds. Regenerate both references; release note.
- [ ] **Step 3: Run** every guard of pieces 1 to 3, the three suites, both `--check`s. **Commit.**

### Task 3: Proof, recipe, check, push

- [ ] `make move-proof BASE=<floor head> DECLARED=…`: nothing but the move and the declared change.
- [ ] `docs/ARCHITECTURE.md`: the team, the gate and the activity log; the memory-copy rule in the recipe.
- [ ] Merge main once #42 lands (`merge -s ours` its squash after checking the trees are equal); `make check` on 8941; self-review; push; the pull request.
