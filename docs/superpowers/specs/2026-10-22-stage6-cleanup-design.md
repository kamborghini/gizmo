# Stage 6: the last ties to copilot.py, docs as the code is, the suite in sections

**Approved 22 Oct 2026** ("go ahead with all three"). Stage 6 of the 14 October
engineering audit (cleanup and docs). Three pull requests, in this order.

## 1. The last ties to copilot.py

Measured on main bfc25ed: 57 modules import `copilot` and never use it (left
from stage 4's "read as core.NAME"); the real reads back are `_spawn_bg` (12
calls in 7 modules), `run_label_coverage` (2) and the stock bridge's (hands
off). `_spawn_bg` keeps its tasks in the CRM's own set. The 65-pair import
check (one interpreter per pair, written out by hand during stage 4) takes 88
of the dispatch suite's seconds.

- `gizmo/background.py`, on the floor: `spawn(coro)` with its own task set.
  The frozen print route keeps calling `copilot._spawn_bg`, which hands to it.
- `run_label_coverage` moves to `gizmo/production.py` (nothing but the move:
  `make move-proof`).
- Every module that reads nothing from `copilot` stops importing it; only the
  stock bridge's readers keep the import. A test says so
  (`t_only_the_stock_bridge_reads_copilot`).
- The import check stays (any module can be imported first), over every app
  module found, not a list typed by hand, run side by side.
- Names nothing reads are removed after reading each; test seams and an
  integration's API stay. `BORROWED` and its test (empty since stage 4) go.

Nothing anyone sees changes. A release note dated the merge day.

## 2. Docs as the code is now

`docs/ARCHITECTURE.md` still says `copilot.py` "is being split one area at a
time" and that a route is registered "inside `add_routes`"; its "Moving an area
out" how-to describes a finished job. Rewrite to the shape after part 1: the
floor, the areas and their routes in `gizmo/routes/<area>.py`, the door and
body models, the stock bridge's place, tests. The how-to moves to
`tools/moves/README.md` beside the tool (kept for the stock bridge's move). The
README's tour follows. `docs/README.md` indexes the living references
(ARCHITECTURE, DESIGN, API, ENVIRONMENT) apart from the dated records (audits,
bug registers, specs and plans). No business name in any of it.

## 3. The dispatch suite in sections

`tests/test_dispatch.py` is 31,759 lines: 1,069 tests behind a 444-line
harness. It becomes `tests/dispatch/`: the harness, then one file per area,
loaded in the same order by the same runner, with `tests/test_dispatch.py` the
one command that runs them (CI, `make check` and the docs keep calling it).
What reads the file by name follows (the browser rig's prelude, the move tool,
guards that read test source). Proof: the same tests, by name and in order, and
each test function's text unchanged.

## Not in this stage

The visible layout faults (D4); stage 5's deferred minors; the long business
functions (A5).
