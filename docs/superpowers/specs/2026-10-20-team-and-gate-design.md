# Accounts, sign-in and the door

**Approved 20 Oct 2026.** Stage 4, piece 3 of the 14 October engineering
audit. Cameron approved all three parts. Nothing anyone sees changes.

## Why

Every route opens with the one door, `_guard`. Followed through, it reaches
72 names (about 600 lines): the door itself (rate windows, the body cap, the
AI slot, the tab gate, the answer helper), sign-in (the Shopify session
token, passwords, two-factor), the app's own accounts and sessions (roles,
tabs, master reset), the activity log, and work sessions. The sign-in and
team routes (10) sit together in `add_routes`. Tests patch the cluster 20
times.

Two things decide how it moves:

- **`globals()`.** `_drop_memory_stores` clears every whole-store copy held in
  memory through `copilot.py`'s `globals()`. Four of the seven are this
  area's (accounts, sessions, work, activity). Moved naively, restore and
  shop/redact would leave the old accounts and sessions in memory: a deleted
  account still signed in, and no test or proof would notice.
- **The frozen print route** reads seven of these names
  (`_verify_session_token`, `_pre_checks`, `_track`, `_live_uid`,
  `_uid_has_tab`, `_API_HEADERS`, and `SHOPIFY_API_SECRET`, which stays).

## What changes

### 1. Each module lets go of its own memory copies

The store keeps a list of holders (`jsonstore.holds_in_memory(drop)`); each
module that keeps a whole store in memory registers a function that lets go
of its own copies (`drop(paths)` clears each copy whose path is named, or
all when none are, and returns the paths it let go of) and the store forgets
their cached parse. `_drop_memory_stores` moves into the store and
`_memory_stores` goes; no module uses `globals()`. The name-matching test
becomes a behavioural one: every `_..._mem` copy in every module, set, is
gone after a drop, and a drop naming one store lets go of that one only.
Paths are read when the drop runs, as now.

### 2. Accounts and sign-in out: `gizmo/team.py`

The Team section's accounts (users and sessions with their stores and
memory copies, passwords and lockouts, two-factor tickets, roles, tabs per
person, master reset, the team names and counts), the sign-in checks
(`_verify_session_token`, `_authorize`, `AUTH_REFUSALS`) and the sign-in
rate window. The 10 sign-in and team routes move to
`gizmo/routes/team.py` (`register(mcp, registry)` where they stood). Read as
`team.NAME` (`accounts` is a local name in the chase log). Left in
`copilot.py` though they sit among them: the token vault, WebDAV's limits,
payment terms on release, size-rule and mail permissions, page layouts, the
redact retry; and the profile route, registered elsewhere in the table.

### 3. The door and the activity log out: `gizmo/gate.py`, `gizmo/activity.py`

The door (`_guard`, `_pre_checks`, the rate windows, the body cap, the AI
slot, the tab map and gate, the answer helpers, the response headers) and the
activity log (`_track`, the event store, its exit flush, the noise
coalescers). Read as `gate.NAME` (`door` is a local name in the desk) and
`activity.NAME`. Work sessions, the page's build marker and the Shopify
settings stay in `copilot.py`; the new modules read them as `core.NAME`.

The frozen print route keeps its bytes: `copilot.py` takes the six moved
names it reads by name (the guard allows a copy only of a name no test
patches and nothing rebinds), they read bare everywhere in `copilot.py`, and
the new modules import `copilot` last. The desk reads the door, the team and
the activity log directly: its borrowed list drops from 29 to 23.

The route reference reads the tab map from whichever module holds it.

## Proof and guards

- `make move-proof DECLARED=…` shows the intended changes (`_memory_stores`,
  `_drop_memory_stores`, `holds_in_memory`, `_holders`, `_let_go_in_memory`)
  and nothing else.
- `docs/API.md`: only the 10 moved handlers' module changes.
- All of pieces 1 and 2's guards; the security suite's sign-in, session,
  lockout, MFA and tab tests run unchanged.
- A release note: "Sign-in and the door on their own": "Signing in, the
  team's accounts and the check every request passes now each live on their
  own, so a change elsewhere cannot weaken them. Nothing looks different."

## Not in this piece

Orders and production; work sessions, page layouts and the page itself; the
profile route; any change to how sign-in or the checks behave.
