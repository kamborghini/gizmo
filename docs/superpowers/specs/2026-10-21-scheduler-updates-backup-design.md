# The scheduler and alerts, release notes and requests, impact and backup

**Approved 21 Oct 2026.** Stage 4, piece 10 of the 14 October engineering
audit. Cameron approved all three parts. Nothing anyone sees changes.

## Why

Measured with a `tools/move_area.py` dry run on piece 9's branch (copilot.py
6,171 lines):

- **The scheduler and change alerts** (the schedule, the alerts and the email
  that sends them, the watch, the hourly watchdog, the nightly reconciliation
  and connector watch, the loop that runs the paid audits): 27 statements, 482
  lines, 2 routes (35 lines).
- **Release notes and requests** (the changelog that ships with the release,
  the app's version and start time, feature requests): 9 statements, 56
  lines, and the 101-line `/api/updates` route.
- **Impact tracking** (snapshots and the changes since): 9 statements, 71
  lines, `/api/impact` (81). **Backup** (the zip, the weekly snapshots, restore):
  7 statements, 153 lines, `/api/backup` and `/api/restore` (214).
- Two paths are built from `__file__`: the changelog's default, and the
  repository's `data` folder the backup carries. Moved into `gizmo/`, both
  would point one folder down, and both fail quietly: a missing changelog
  shows no notes, a missing folder is skipped. No test checks either.
- The dry run notes what stays though only what moves reads it: the stock
  bridge's drain and catalogue send (the scheduler runs them; the stock bridge
  is the stock merge project's and stays untouched), and two privacy helpers
  (`_shop_redact_retry`, `_keep_live_privacy`; privacy moved in piece 7, and
  the tool writes new modules, not into old ones).

## What changes

1. **The scheduler out**: `gizmo/scheduler.py` and `gizmo/routes/scheduler.py`
   (`/api/schedule`, `/api/alerts`).
2. **Release notes and requests out**: `gizmo/updates.py` and
   `gizmo/routes/updates.py` (`/api/updates`). The changelog's default is built
   from the repository (`_REPO`), a declared change.
3. **Impact and backup out**: `gizmo/impact.py` with `gizmo/routes/impact.py`
   (`/api/impact`); `gizmo/backup.py` with `gizmo/routes/backup.py`
   (`/api/backup`, `/api/restore`). The backup's repository folder is built
   from `_REPO`, a declared change.

Two pins first, passing before the move: the backup carries every file of
the repository's `data` folder, and the release notes are the repository's
own changelog.

A release note, "The scheduler, release notes and backups on their own": "The
scheduled refresh and its alerts, the release notes and requests, impact
tracking and backups now each live on their own, so a change elsewhere cannot
upset them. Nothing looks different."

## Not in this piece

The stock bridge, the two privacy helpers, the store report and the London
clock helpers in the impact section (read across the app), reconciliation, the
Xero connector, the chase desk, page rendering, layouts, the frozen print
routes.
