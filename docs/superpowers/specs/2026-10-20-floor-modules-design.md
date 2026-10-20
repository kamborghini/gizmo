# The floor: the store, the error log and the AI client

**Approved 20 Oct 2026.** Stage 4, piece 2 of the 14 October engineering
audit. Cameron approved all three parts. Nothing anyone sees changes.

## Why

The dispatch desk (piece 1, #41) reads 42 names from `copilot.py` through
`core.`. Every area that moves out will lean on the same few things: the
store, the error log and the AI client. While those stay in `copilot.py`,
each area keeps a cycle with it. Measured on main 87eb3d1:

- **The store** is one block of about 180 lines (the loaders, the one writer,
  the cache, the poison guard) plus the private-file writer. It reads nothing
  from the rest but `logger`, the CRM's path and the CRM's kept board (when
  the CRM's file is forgotten, the board built from it goes too). Tests patch
  two of its names, 7 times.
- **The AI client** (model choice and limits, the client, the call and its
  fallbacks, usage records, the daily spend cap, failure notes and the dash
  filter for model text) is 52 names, about 440 lines. Below the store it
  needs only the error log. Tests patch 9 of its names about 45 times.
- **The error log** (`_record_error`, `_recent_errors`) needs only the store.
- One function, `_drop_memory_stores`, clears each area's in-memory copy
  through `globals()`. Moved into another module it would clear that
  module's names instead, and neither the move script nor `make move-proof`
  would notice. The desk moved nothing of the kind.

## What changes

### 1. The store becomes a true floor

`gizmo/store.py` (beside `StoreUnwritable`) takes `_poisoned_stores`,
`_load_json_store`, `_store_writable`, `_json_cache`, `_cached_paths`,
`_stat_key`, `_load_json_cached`, `_forget_store`, `_write_json_store` and
`_write_private_json`. It imports nothing from `copilot.py`.

Staying in `copilot.py`: `_memory_stores` and `_drop_memory_stores` (the list
of each area's in-memory copy, cleared through `copilot.py`'s own
`globals()`), `_store_report` and its threshold (the Settings store sizes),
and production's two settings that sit in the block.

The one change that is not a move: the store stops naming the CRM. It keeps a
list of hooks (`when_forgotten(fn)`), each called with the path whenever a
store's cached copy is forgotten; `copilot.py` registers one that drops the
CRM's kept board when the path is the CRM's (read when called, as now).
Same behaviour; a test pins it.

### 2. The AI client and the error log become floor modules

`gizmo/errors.py`: `ERRORS_PATH`, `ERRORS_MAX`, `_record_error`,
`_recent_errors`. `gizmo/ai.py`: the AI client's 52 names. Each imports only
the store, the error log, `gizmo/config.py` and outside libraries.

Every module reads them through the module's name: `jsonstore.NAME`,
`errors.NAME`, `claude.NAME` (`store` and `ai` are local names in 32 and 3
functions; `errors` is free). Tests that patch a moved name patch it on its
new module, in the same commit. The desk reads them directly, so
`t_what_dispatch_borrows` drops from 42 names to 29.

### 3. The guards and the proof learn

- `t_no_module_looks_itself_up_by_name`: nothing in `gizmo/` uses
  `globals()`, `vars()` or `sys.modules[__name__]`; `make move-proof` names a
  moved statement that does.
- `t_the_floor_imports_nothing_above_it`: `gizmo/config.py`, `gizmo/store.py`,
  `gizmo/errors.py` and `gizmo/ai.py` never reach `copilot.py`, `server.py`
  or an area, directly or through another module.
- `make move-proof BASE=<ref> DECLARED=<names>`: statements named as intended
  changes are shown before and after instead of failing; everything else
  still has to match exactly. Here: `_forget_store`, `when_forgotten`,
  `_forget_hooks` and the CRM's hook.
- `docs/ARCHITECTURE.md`: the floor, and the rule that an area imports the
  floor directly.
- A release note: "The app's foundations on their own": "How the app keeps
  its records, notes its errors and talks to the AI now each live on their
  own, beneath everything else, so later changes cannot disturb them.
  Nothing looks different."

## Guards

The three above, plus every guard from piece 1 (no blind patch, no reading
`copilot.py` by name, both security scans, no unbound name, either module
first, the desk's borrowed list).

## Not in this piece

The request check, accounts and sessions (the next piece); orders and
production; any change to how the store or the AI behave.
