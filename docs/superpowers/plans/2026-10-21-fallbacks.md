# Errors that fall back say why Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every broad handler that falls back to a value without a word says why, or logs.

**Architecture:** `tools/broad_excepts.SILENT` gains "falls back" and "other"; reason comments on the `except` lines; three `logger.warning` lines.

**Tech Stack:** Python 3.14; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-21-fallbacks-design.md`

## Global Constraints

- Every fallback value unchanged; nothing anyone sees changes.
- A release note dated the merge day; British English; no hosting names or settings in visible copy.
- Browser on 8942 (8941 is the other branch's); no agents; branch `stage5/fallbacks` from main 90e1120.

## Review Focus

1. **A log line in a hot path**: the spend cap reads the usage log once a day; the vault key once per erasure mark batch; the webhook once per delivery.
2. **The first day's missing usage log** must stay quiet: told apart by `FileNotFoundError`.
3. **A reason that is not true of its code**: each read against the lines below it.

---

### Task 1: The guard and the reasons

- [ ] **Step 1: Failing test**: widen `SILENT`; `t_no_error_is_swallowed_without_a_reason` fails naming the 36.
- [ ] **Step 2:** 33 reasons, three warnings. **Step 3: Run** the guard and the suite. Release note. `make check` on 8942. **Commit**, push, the pull request.
