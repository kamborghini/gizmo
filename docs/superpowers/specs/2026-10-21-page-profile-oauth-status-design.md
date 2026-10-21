# The page and its assets, the store profile and layouts, the sign-in walks and the status page

**Approved 21 Oct 2026.** Stage 4, piece 12 of the 14 October engineering
audit. Cameron approved all three parts. Nothing anyone sees changes.

## Why

Measured with `tools/move_area.py` dry runs on piece 11's branch (copilot.py
3,430 lines):

- **The page** (splitting it, rendering it, its ETags, the packed assets, the
  frame headers, the build id): 19 statements, 269 lines, the page's own
  route `/` and the three `/assets/` routes. Its static folder (where
  `composer.js` lives) is built from `__file__`; the test that the composer is
  served by hash fails when that path points one folder down (checked), so it
  pins the rewrite.
- The tool gathers routes by path prefix, and every path starts with `/`: the
  page's own route cannot be named. Nor can `/api/product` without taking
  `/api/products`.
- **The store profile** (6 statements, 54 lines, `/api/profile`): `profile` is
  a local name in the overview, so it is read as `store_profile`. **Page
  layouts** (10 statements, 63 lines, `/api/layouts`).
- **The Google and accounts-mailbox sign-in walks** (the one-time states, the
  redirect address and the page they answer with, which the inbox's and Xero's
  walks already read; the accounts mailbox's tickets): 6 statements, 30
  lines, 4 routes (133 lines).
- **The status page** (the store report, the last error alert, the token
  vault's state): 4 statements, `/api/status` and `/healthz`.
- The frozen print routes read nothing that moves (checked: `APP_BASE_URL`
  only, which stays).

## What changes

1. **The page out**: `gizmo/rendering.py` and `gizmo/routes/rendering.py`
   (`/` and `/assets/`). The static folder is built from the repository
   (`_REPO`), a declared change. The tool learns exact paths: `"=/"` in a
   route group's paths names that path alone (its toy test first).
2. **The profile and layouts out**: `gizmo/profile.py` (read as
   `store_profile`) with `/api/profile`; `gizmo/layouts.py` with
   `/api/layouts`.
3. **The sign-in walks and the status page out**: `gizmo/oauth.py` with the
   Google and accounts-mailbox walks' routes; `gizmo/status.py` (read as
   `appstatus`) with `/api/status` and `/healthz`.

A release note, "The page, profile, sign-ins and status on their own": "How
the page is served, the store profile and card layouts, the Google and
accounts mailbox connections, and the status page now each live on their
own, so a change elsewhere cannot upset them. Nothing looks different."

## Not in this piece

The products routes, the chat routes, the stock bridge and its routes, the
frozen print routes and their font and logo routes, privacy's and the team's
leftovers, the AI tool list and usage, the shared order and money helpers.
