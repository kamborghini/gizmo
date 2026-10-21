# The page and its assets, the store profile and layouts, the sign-in walks and the status page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The page, the profile and layouts, the sign-in walks and the status page out of `copilot.py` with their routes. Nothing anyone sees changes.

**Architecture:** `tools/move_area.py` with one description (`tools/moves/page-profile-oauth-status.json`); the tool first learns exact route paths (`"=/"`); the static folder rewritten from `_REPO` by hand and declared.

**Tech Stack:** Python 3.14; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-21-page-profile-oauth-status-design.md`

## Global Constraints

- Nothing anyone sees changes; every request answered by the same handler; the frozen print routes and the stock bridge untouched.
- A pure move but the declared static folder rewrite.
- A release note dated the merge day; British English; no dashes in UI copy.
- Browser on 8941; no agents; branch `refactor/piece-12` from piece 11 (460f24f, #56), brought up to main once #56 merges.

## Review Focus

1. **The page answering a different request** once `/` is gathered: pinned by the toy test's exact-path case and `make move-proof`'s route order rule.
2. **The composer missing from the page** after the static folder moves: pinned by `t_the_composer_script_is_served_by_hash_like_the_app_script` (fails with the path one folder down, checked).
3. **The page's ETag and frame headers** after they move: pinned by the ETag and CSP tests (unchanged).
4. **A sign-in walk's one-time state** read from two modules (Xero's and the inbox's walks read it from here): pinned by guard (b) and the connect tests.
5. **The status page and the boot's store report** (`server.py` reads it): pinned by the status tests and the boot in the suite.

---

### Task 1: Exact route paths

- [ ] **Step 1: Failing test**: in `t_move_area_moves_a_toy_area`, a toy route at `/` and one at `/api/y`; a group with paths `["=/"]` gathers only the first.
- [ ] **Step 2: Build**: a path starting with `=` matches that path alone.
- [ ] **Step 3: Run** the toy tests. **Commit.**

### Task 2: The move

- [ ] **Step 1: Failing tests**: `t_the_page_profile_oauth_and_status_routes_are_gathered` (one register call each; no `"/"`, `/assets/`, `/api/profile`, `/api/layouts`, `/oauth/google/`, `/oauth/gmail-finance/`, `/api/status` or `/healthz` route left in `add_routes`; 4, 1, 1, 4, 2 routes in the modules); `t_either_module_imports_first` gains the ten modules.
- [ ] **Step 2:** The description; dry run; `--write`; `_STATIC_DIR` from `_REPO` (declared); text checks; references; release note.
- [ ] **Step 3: Run** every guard, the suites. **Commit.**

### Task 3: Headings, proof, recipe, check, push

- [ ] Stranded headings re-homed (comments only); `make move-proof` (declared: `_REPO`, `_STATIC_DIR`); `docs/ARCHITECTURE.md`; `make check` on 8941; self-review; push; the pull request.
