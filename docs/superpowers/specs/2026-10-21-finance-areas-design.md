# The chase desk, reconciliation and the Xero sync settings, and the forecast hooks

**Approved 21 Oct 2026.** Stage 4, piece 11 of the 14 October engineering
audit. Cameron approved all three parts. Nothing anyone sees changes.

## Why

Measured with a `tools/move_area.py` dry run on piece 10's branch (copilot.py
4,913 lines), the Finance tab's backend:

- **The chase desk and credit terms** (the tags that mark an unpaid order, the
  terms and due date each runs to, the chase log and email, the Liability
  report): 14 statements, 271 lines, `/api/liability` and
  `/api/liability/chase` (29 lines). The report route has no test of its own:
  every test builds the report directly.
- **Reconciliation** (its stores, its AI call, the read-only tools the chat is
  given) with the Xero connect walk (its redirect address and sign-in
  tickets): 24 statements, 162 lines, 9 routes (287 lines).
- **The Xero sync settings** (which connector settings may be read and set,
  the connector's address and call): 7 statements, 92 lines, `/api/connector`
  (204 lines). `connector` is a local name in a test, so it is read as
  `xerosync`.
- **The forecast hooks** (the forecast's store, the hook token, the figure and
  ledger it keeps): 11 statements, 141 lines, the four hooks the nightly
  service calls with `/api/forecast` and the workbook upload (147 lines). Named
  `forecasting`, apart from the `forecast/` service package.
- Nothing stops it, nothing is left behind, nothing is read as a module loads,
  no path is built from `__file__`.

## What changes

1. **The chase desk out**: `gizmo/liability.py` and `gizmo/routes/liability.py`.
2. **Reconciliation and the Xero sync settings out**:
   `gizmo/reconciliation.py` with `gizmo/routes/reconciliation.py` (the seven
   `/api/recon/` routes and `/oauth/xero/start` and its callback);
   `gizmo/xero_sync.py` (read as `xerosync`) with `gizmo/routes/xero_sync.py`.
3. **The forecast hooks out**: `gizmo/forecasting.py` and
   `gizmo/routes/forecasting.py`.

A pin first, passing before the move: the Liability route answers with the
report. A pure move: nothing declared.

A release note, "The Finance tab's workings on their own": "Liability and the
chase desk, reconciliation, the Xero sync settings and the forecast's hooks
now each live on their own, so a change elsewhere cannot upset them. Nothing
looks different."

## Not in this piece

The Gmail and Google connect walks, the store profile, layouts, page rendering,
the status route, the stock bridge, the frozen print routes, the chat routes.
