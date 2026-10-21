# A test run that shows the failure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The dispatch suite prints one line per test, and a failing test's log lines under it.

**Architecture:** A root `StreamHandler` on a `StringIO`, set before `import server`; the runner clears it per test and prints it under FAIL.

**Tech Stack:** Python 3.14 standard library.

**Spec:** `docs/superpowers/specs/2026-10-21-quiet-suite-design.md`

## Global Constraints

- Every test's outcome unchanged; `VERBOSE=1` gives the old output.
- Browser on 8942; no agents; branch `stage6/quiet-suite` from main 90e1120.

## Review Focus

1. **A failure whose cause was only in the logs** must still show it: pinned by the toy failing test's line appearing under its FAIL line.
2. **A test that reads what the app logs**: none adds a handler or reads stderr (checked); the level stays INFO.

---

### Task 1: The held log

- [ ] **Step 1: Failing test** `t_a_passing_test_prints_its_name_and_nothing_else` (a child run of two toy tests under `SUITE_SELFTEST=1`: the passing one's line absent, the failing one's under its FAIL line, `VERBOSE=1` streams). **Step 2:** the handler and the runner. **Step 3:** the raw strings; docs. **Run**, `make check` on 8942, **commit**, push, the pull request.
