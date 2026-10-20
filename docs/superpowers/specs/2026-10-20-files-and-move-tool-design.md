# Files, the Finder drive and the move tool

**Approved 20 Oct 2026.** Stage 4, piece 6 of the 14 October engineering
audit. Cameron approved all three parts. Nothing anyone sees changes.

## Why

Files (the office file server on the R2 bucket) is 62 names plus helpers
without the prefix (its loaders, the file-kind checks, the boot clean-up
`server.py` calls), 7 routes scattered through `add_routes`, and a copy held
in memory. Tests patch it 57 times. The Finder drive (WebDAV) is 14 names
and the one route with a pattern, `/dav{sub_path:path}`; no other route's
path starts with `/dav`, so it can be gathered with the Files routes.

Each of the five moves so far was made by a one-off script, and each needed
the same hand fixes: imports used only in annotations, an area's loaders the
name prefix missed, alias names that are locals somewhere (in the tests too),
copies read through their owner and imported last. The guards caught every
one. About seven areas remain.

## What changes

### 1. The move tool: `tools/move_area.py`

One committed tool, driven by a short JSON description of a move
(`tools/moves/<name>.json`): each area's file, alias, name prefixes, extras
and exclusions and whether it is floor; each route group's file, the paths
it gathers and the helpers that go with it. It does what the five scripts
did, with every lesson built in:

- statements move whole with their leading comments; a banner stays unless
  its whole section moves; a module-level call moves with the area whose
  names it uses;
- global reads found with `symtable` are prefixed (`core.` for what stays,
  the alias for another area, the owner for a name `copilot.py` copies from
  an earlier area); annotation names count, so their imports come along;
- a `global` line naming only moved names goes and the writes go through
  the module; a floor area may not borrow; `__file__` stops the move unless
  the description allows it;
- route groups gather where the first route stood;
- an alias that is a local name in any function that would read through it,
  in the app or the tests, stops the move;
- the split modules, `server.py`, the tests and the seeds are re-pointed, and
  the suite's prelude imports the new modules.

It writes nothing while it finds a problem. A test runs it on a small made-up
repository and checks the result with `make move-proof`'s `prove()`.

### 2. Files out: `gizmo/files.py`, `gizmo/routes/files.py`

The bucket client and its setup, the store and its copy in memory (its own
drop, declared), names, kinds and previews, uploads in flight, quota and
usage, the reaper, supersede and purge, signed links, and the boot clean-up
(`server.py` re-pointed). The 7 routes, gathered. Read as `files`.

### 3. The Finder drive out: `gizmo/webdav.py`

The drive's path walking, its auth and failure caches and its XML. Its route
joins the Files routes. Read as `webdav`.

A release note: "Files on their own": "The shared files and the Finder drive
now live on their own, so a change elsewhere cannot upset an upload or a
download. Nothing looks different."

## Not in this piece

Customer-data erasure, the release notes, skills, the scheduler, loans, the
stock bridge, the Xero connector, the production and order routes; any
change to how files are stored, uploaded or served.
