# The scheduler and alerts, release notes and requests, impact and backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The scheduler, release notes and requests, impact tracking and backup out of `copilot.py` with their routes. Nothing anyone sees changes.

**Architecture:** `tools/move_area.py` with one description (`tools/moves/scheduler-updates-backup.json`, `allow_file` for updates and backup); the two `__file__` paths rewritten from `_REPO` by hand and declared.

**Tech Stack:** Python 3.14; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-21-scheduler-updates-backup-design.md`

## Global Constraints

- Nothing anyone sees changes; every request answered by the same handler; the frozen print routes and the stock bridge untouched.
- A pure move but the two declared path rewrites.
- A release note dated the merge day; British English; no dashes in UI copy.
- Browser on 8941; no agents; branch `refactor/scheduler-updates-backup` from piece 9 (e3a6b64, #54), brought up to main once #54 merges.

## Review Focus

1. **A backup without the repository's data files** after the move: pinned by `t_the_backup_carries_the_repos_data`, written before it.
2. **No release notes** because the changelog's default moved: pinned by `t_the_release_notes_are_the_repos_own`, written before it.
3. **A restore that misses a store** after it moves: pinned by the restore tests (unchanged) and `t_every_memory_copy_of_a_store_is_let_go`.
4. **The scheduler started twice, or not at all** (its started flag is a `global` in the module that moves): pinned by guard (b) and the route tests that boot `add_routes`.
5. **An alert email not sent** (privacy and the watchdog call it): pinned by the alert and privacy tests and guard (a).

---

### Task 1: The pins

- [ ] **Step 1:** `t_the_backup_carries_the_repos_data` (every `.json`, `.jsonl`, `.csv` or `.bak` in the repository's `data` folder is in the zip under `repo-data/`) and `t_the_release_notes_are_the_repos_own` (the default path is the repository's `data/changelog.json`, and the notes loaded are its releases). Both pass now; each fails when its path points one folder down (mutation checked). **Commit.**

### Task 2: The move

- [ ] **Step 1: Failing tests**: `t_the_scheduler_updates_and_backup_routes_are_gathered` (one register call each; no `/api/schedule`, `/api/alerts`, `/api/updates`, `/api/impact`, `/api/backup` or `/api/restore` route left in `add_routes`; 2, 1, 1, 2 routes in the modules); `t_either_module_imports_first` gains the eight modules.
- [ ] **Step 2:** The description; dry run; `--write`; the two paths from `_REPO` (declared); text checks; references; release note.
- [ ] **Step 3: Run** every guard, the pins, the suites. **Commit.**

### Task 3: Headings, proof, recipe, check, push

- [ ] Stranded headings re-homed (comments only); `make move-proof` (declared: `_REPO`, `CHANGELOG_PATH`, `_build_backup_zip`); `docs/ARCHITECTURE.md`; `make check` on 8941; self-review; push; the pull request.
