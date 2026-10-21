# Every write route checks its body Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Models on the 70 write routes still reading unchecked fields, in three pull requests, leaving four on the list on purpose.

**Architecture:** Piece 1's `gizmo/bodies.py` and `gate._guard(model=)`; `gate._body_refusal(model, body)` for the door and for a route that reads its own body after a check of its own; `model=` on `team._auth_guard` and `team._team_guard`; models beside each area's routes.

**Tech Stack:** Python 3.14, pydantic 2.13.

**Spec:** `docs/superpowers/specs/2026-10-21-bodies-everywhere-design.md`

## Global Constraints

- A request any caller sends today is answered as before: each model is built from an inventory of every caller (the page, the admin extensions, the forecast worker), field by field; the browser suite runs every screen.
- A wrong kind is a 400 naming the field, in plain words.
- The frozen print route, Shopify's privacy webhook and the stock bridge stay unchecked, each with its reason.
- A release note per pull request, dated the merge day; British English.
- Browser on 8941; branches from main in turn (`stage5/bodies-2`, `-3`, `-4`).

## Review Focus

1. **A model stricter than a caller**: the inventory (three read-only agents, one per area) names every caller and what it sends; a final adversarial reviewer reads the models against the callers again.
2. **A check that raises instead of refusing** (a JSON number past any float): pinned in `t_a_body_model_checks_only_what_it_names`.
3. **The sign-in ceiling**: a field of the wrong kind at a sign-in walk is refused before the ceiling and the password check, so it spends neither.
4. **A route that reads its own body** (`body=False`): the model is checked with `gate._body_refusal` straight after that read, after the route's own rank check.
5. **A test that pinned the old answer to a wrong kind** (the CRM deal's "NaN" value): updated to the door's 400, the store still untouched.

---

### Piece 2 (`stage5/bodies-2`): accounts and the workspace, 27 routes

- [ ] **Step 1: Failing tests**: `t_a_body_model_checks_only_what_it_names` gains a number past any float, `Records` and a field named `from`; `t_the_accounts_routes_refuse_a_wrong_kind` sweeps every field of the 27 (the forecast hook behind its token).
- [ ] **Step 2:** `bodies`: integers compared, never converted; `Records`; `named()` and `sent_names()`; whole-number text to 30 digits. `gate._body_refusal`; the two doors; the models. `UNCHECKED_BODIES` shrinks; `docs/API.md`; release note. **Run**, `make check`, **commit**, push, the pull request.

### Piece 3 (`stage5/bodies-3`): the desks, 26 routes

- [ ] **Step 1: Failing test** `t_the_desks_routes_refuse_a_wrong_kind` (CRM deals, leads, stages, import; every Inbox route; Files). **Step 2:** the models; the "NaN" test's expectation. **Run**, `make check`, **commit**, push, the pull request.

### Piece 4 (`stage5/bodies-4`): shipping and production, 17 routes

- [ ] **Step 1: Failing test** `t_the_shipping_routes_refuse_a_wrong_kind` (the dispatch desk, custom shipments, the EORI check, the Size list's check, models and upload, the production labels feed). **Step 2:** the models; the Size list upload checks after its own read. `UNCHECKED_BODIES` down to the four. **Run**, `make check`, the adversarial review, **commit**, push, the pull request.
