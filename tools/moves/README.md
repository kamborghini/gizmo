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
  `alias` is how every other module reads it; check it is no local name
  where it would be read (the tool refuses if it is). `floor` areas may not
  borrow from `copilot.py`. `allow_file` lets a statement build a path from
  `__file__`, which the move then has to fix by hand (and declare).
- **routes**: the routes whose path starts with one of `paths`, and the
  nested `helpers` only they use, gathered into `register(mcp, registry)`
  where the first stood.
- **copies**: moved names `copilot.py` keeps reading bare, for a frozen
  function that must keep its bytes; the guard allows a copy only of a name
  no test patches and nothing rebinds.

Run it without `--write` first: it lists what moves, what each area borrows
from `copilot.py`, and anything that stops the move. Then the guards, the
suites and `make move-proof`, as in `docs/ARCHITECTURE.md`.
