# Move descriptions

`tools/move_area.py tools/moves/<name>.json [--write]` moves an area out of
`copilot.py` into the `gizmo` package. A description is JSON:

```json
{
  "note": "what moved, for the comment in copilot.py's imports",
  "areas": [
    {"name": "files", "file": "gizmo/files.py", "alias": "files",
     "prefix": "^(_files|FILES_)", "extra": ["_load_files"], "exclude": [],
     "floor": false, "allow_file": false,
     "doc": "The module's docstring: what it holds and how it is read."}
  ],
  "routes": [
    {"name": "routes_files", "file": "gizmo/routes/files.py", "area": "files",
     "paths": ["/api/files/", "/dav"], "helpers": [],
     "doc": "The route module's docstring.", "register_doc": "Add the routes to the app.",
     "comment": "The line above the register call in add_routes."}
  ],
  "copies": ["names copilot.py keeps reading by their own name (a frozen function)"]
}
```

- **areas**: every top-level statement whose names all match one area's
  `prefix` (a regex) or `extra`, and none of its `exclude`, moves there.
  `existing: true` adds to a module moved in an earlier piece (its `file`,
  bound in `copilot.py` as `alias`): the statements go in before its last
  imports, its own name is dropped inside them, and its own `core.NAME` reads
  of them become bare. If `copilot.py` takes names from that module but does
  not bind it by `alias` yet (`from gizmo.config import _env_num`), the move
  binds it there and in the suite.
  `alias` is how every other module reads it; check it is no local name
  where it would be read (the tool refuses if it is). `floor` areas may not
  borrow from `copilot.py`. `allow_file` lets a statement build a path from
  `__file__`, which the move then has to fix by hand (and declare).
- **routes**: the routes whose path starts with one of `paths` (or is it
  exactly, written `"=/"`: every path starts with `/`), and the
  nested `helpers` only they use, gathered into `register(mcp, registry)`
  where the first stood. A group marked `existing` adds its routes to a route
  module moved earlier (bound in `copilot.py` as the group's `name`), at the
  end of its `register()`.
- **copies**: moved names `copilot.py` keeps reading bare, for a frozen
  function that must keep its bytes; the guard allows a copy only of a name
  no test patches and nothing rebinds.

Run it without `--write` first: it lists what moves, what each area borrows
from `copilot.py`, every name that stays though only what moves reads it
(directly or through another such name: add it to the area, or say why it
stays), and anything that stops the move. Then the guards, the
suites and `make move-proof`, as in `docs/ARCHITECTURE.md`.
