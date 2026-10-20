# Dispatch in its own module

**Approved 20 Oct 2026.** Stage 4, piece 1 of the 14 October engineering
audit (the backend split, one area per pull request, dispatch first).
Cameron approved all three parts. Nothing anyone sees changes.

## Why

`copilot.py` is 28,623 lines. All 150 routes are closures inside one
function, `add_routes` (8,690 lines); its helpers were already lifted out
(6 remain). Every change to any area edits the same file, and a change to one
area can upset another without either side's code saying so.

The 7 September and 14 October audits deferred the split for one reason:
tests patch module state by name, and moving code makes those patches test
nothing. Measured on main 51d62b0:

- Tests assign 126 distinct names on `copilot` and `server`, 614 times. Every
  one lands today on a name its module defines and reads.
- Moving dispatch would move 10 of those names (28 assignments) out from
  under their tests. One test (`copilot.datetime` frozen around two collection
  tests) would keep passing with the collection half unfrozen.
- 59 checks in the two suites read `copilot.py`'s text, and so do the route
  reference, the environment reference, the security scan's file list (the
  Makefile's and CI's) and the release-note date test. A check about moved
  code would pass with nothing to look at.
- Two cases exist already: tests set `server.SHOPIFY_STORE` while `copilot`
  holds its own, and set `copilot.httpx` while `server` holds its own.

Dispatch (quotes, booking, labels, the manifest, cancelling, collections,
customs, pasted and one-off addresses, shipping settings and the margin
report built on courier charges) is about 3,300 lines in four stretches:
lines 2028 to 2797 (interleaved with the error log, backups, production state
and impact snapshots), 7567 to 9620, 19787 to 19878, and its 15 routes at
26620 to 27289. The routes borrow only `mcp` and `registry` from
`add_routes`. Dispatch reads 63 names from the rest of the file; the rest
reads about 25 of dispatch's.

## What changes

### 1. No test can go blind (lands first, on today's code)

A guard in the dispatch suite, `t_no_test_patches_a_name_nobody_reads`:

- every `module.NAME = …` in the tests targets an app module that binds NAME
  at its top level (or by `global`) and reads it;
- no app module copies a name from another app module (`from m import NAME`)
  when tests patch it there or the owner rebinds it with `global`;
- when a test patches `m.NAME` and another app module binds and reads its own
  NAME, the same test function patches that one too, or the pair is listed
  with its reason.

One helper, `tools/sources.py` (shared by the suites and the tools), gives the text of `copilot.py` and every
module split out of it (`copilot_source()`, `COPILOT_FILES`). The 59 checks,
the release-note date test and both references use it; a guard
(`t_nothing_reads_copilot_py_by_name`) fails on any other test or tool that
opens `copilot.py` by name. The Makefile's and CI's security scans cover the
`gizmo/` package, and a test pins that both lists name every app module.

The two existing cases are looked at and either fixed or listed with a reason.

### 2. Dispatch in its own module

- `gizmo/__init__.py` (empty), `gizmo/config.py`: the setting reader
  (`_env_num`) the modules need at start-up, imported by `copilot.py` too.
- `gizmo/dispatch.py`: the desk, its stores and its settings, moved whole and
  in their original order.
- `gizmo/routes/dispatch.py`: its 15 routes and `_finish_cancel`, inside
  `register(mcp, registry)`, called from `add_routes` where the routes stood,
  so the route table keeps its order.

The rest of `copilot.py` reaches dispatch as `dispatch.NAME`; dispatch
reaches what it still needs as `core.NAME` (`import copilot as core`), never
by copying names. Nothing is read across at import time, so either module can
be imported first. `t_what_dispatch_borrows` pins the exact set of `core`
names the two modules read: each later area that moves out (the store, the
request check, orders, the AI client) shrinks it. Logs keep the logger name
`shopify_mcp.copilot`. Tests that patch a moved name patch it on `dispatch`,
in the same commit.

Stays put, though it sits among the dispatch lines: the London date helpers,
the error log, backups, the weekly snapshot, production state, impact
snapshots, memory, missing production, liability and `_print_cors`.

### 3. Proof, and the recipe

- `make move-proof BASE=<ref>` (`tools/move_proof.py`): every function, class
  and statement in the base's `copilot.py` is found again, in the head's
  `copilot.py` or `gizmo/`, with an identical syntax tree once `core.` and
  `dispatch.` prefixes are read as plain names; `add_routes` differs only by
  the routes replaced with the `register` call. It fails naming anything
  added, lost or changed.
- `docs/API.md` regenerated: the same 150 routes with the same tabs, doors,
  terms and checks; only the 15 handlers' module changes. `docs/ENVIRONMENT.md`
  lists the same variables.
- `make check` green with the same test count plus the new guards; the app
  starts and answers `/healthz`, and `gizmo.dispatch` imports first in a
  fresh interpreter.
- `docs/ARCHITECTURE.md`: where the package is and how an area moves out (the
  inventory, the move, the prefixes, the guards, the proof), so production,
  the CRM, mail and files follow the same steps.
- A release note: "The dispatch desk on its own": "The dispatch desk's code
  now lives on its own, so a change elsewhere in the app can no longer upset
  booking, labels or collections. Nothing looks different."

### As built

- `copilot.py` reads the desk as `desk.NAME` (`from gizmo import dispatch as
  desk`), not `dispatch.NAME`: `run_chat` and the frozen
  `run_production_labels` take a parameter called `dispatch`.
- `StoreUnwritable` moved to `gizmo/store.py`: the desk's own store error
  subclasses it as it loads. `make move-proof` caught the first cut leaving a
  second class of that name in `copilot.py`, so its `except StoreUnwritable`
  missed the desk's error; `t_the_desks_store_error_is_a_store_error` pins it.
- The printed labels' route keeps its bytes: `copilot.py` takes
  `LABEL_STOCK_MM` and `_load_dispatch` from the desk by name, and the desk
  imports `copilot` last.
- 140 statements and 16 route functions moved; the desk borrows 42 names;
  `copilot.py` went from 28,623 to 25,272 lines. The source guard also
  catches `inspect.getsource(copilot)`, which two checks used.

## Guards

- No test patches a name its module does not read, and no module keeps a copy
  a test could miss (`t_no_test_patches_a_name_nobody_reads`).
- No test or tool reads `copilot.py` by name except `tools/sources.py`.
- Both security scans cover every app module.
- `t_what_dispatch_borrows`: the `core` names dispatch reads, exactly.
- `make move-proof`: nothing but the move.

## Not in this piece

Any change to how dispatch works (a pure move); the store, the request check
and orders as modules of their own (the next piece); request models (stage
5); renaming the dispatch suite, which tests the whole app.
