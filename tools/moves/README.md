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
suites and `make move-proof`, as in the recipe below.

## The recipe

Stage 4 of the 14 October audit split `copilot.py` into the `gizmo` package
with this, in fifteen pieces (20 and 21 Oct 2026). It stays for the stock
bridge's move. The tests reach module state by name (`copilot.X = stub`), so
code that moves can leave a test testing nothing; the guards below make that
a failure, and `make move-proof` proves a move moved code and changed nothing.

1. **Inventory.** The area's top-level statements by line, and its routes in
   `add_routes`; say what stays though it sits among them.
2. **Move with `tools/move_area.py`.** Describe the area in
   `tools/moves/<name>.json` (its module, alias, name prefixes and extras,
   its route groups; see `tools/moves/README.md`), run the tool without
   `--write` and settle in the description whatever it reports (a name the
   prefix missed shows in what the area borrows; an alias that is a local
   somewhere stops it), then `--write`. The dry run also notes every name
   that stays though only what moves reads it, directly or through another
   such name (`_add_skill` once stayed without a word): move it, or know why
   it stays. A statement that reads another area as the module loads (a
   default value, a decorator, a class body) gets that area imported at the
   top of the new module, and the dry run notes it. A route that reads a value `add_routes`
   binds as it runs cannot move, and the tool refuses it. A heading whose
   whole section moves goes with it; one left over code that is not the
   area's is rewritten to say what is under it, and its text, when it
   explains the area, goes into the area's module. A heading with a rule
   above and none below loses its rule to the old file and arrives without
   one: look for a lone rule after a move. A description with no areas moves
   only routes, for an area that moved earlier; an area marked `existing`
   adds to a module that moved earlier (what an earlier piece left behind):
   the statements go in before its last imports, and its own name and its
   own `core.NAME` reads of them are dropped; a route group marked `existing`
   adds its routes to a route module that moved earlier. What it does: cut statements whole, keeping their text and order,
   into `gizmo/<area>.py`, and the routes into `gizmo/routes/<area>.py`
   inside `register(mcp, registry)`, which `add_routes` calls where the
   area's first route stood. A group's paths are prefixes; `"=/"` names one path
   exactly, since every path starts with `/`. Routes scattered through the table may be
   gathered there: only `/dav{sub_path:path}` has a pattern and no two routes
   share a path, so no request changes hands, and `make move-proof` checks
   exactly that. Find each global read with
   `symtable`: in the area a name that stays becomes `core.NAME` (`import
   copilot as core`), in `copilot.py` a moved name becomes `<alias>.NAME`. A
   `global` across the line becomes an attribute assignment. Keep the logger
   name `shopify_mcp.copilot`.
3. **Nothing across at import time.** What an area needs as it loads moves
   first, into the floor. A function that finds its module's names by name
   (`globals()`, `vars()`, `sys.modules[__name__]`) cannot move: moved, it
   reads the new module's names (`t_no_module_looks_itself_up_by_name`).
   A path built from `__file__` points one folder down once moved into
   `gizmo/`: rewrite it from the repository (`_REPO`) as a declared change,
   and pin what it reaches before the move, since a missing file or folder
   often fails without a word (`t_the_size_lists_seed_files_are_the_repos`,
   `t_the_release_notes_are_the_repos_own`,
   `t_the_backup_carries_the_repos_data`). An area imports
   another area, and `copilot`, last; only the floor goes at the top, and
   an area a statement reads as the module loads (its settings are defined
   before its own last imports run, so any module may still go first).
   None is left. A function that resets another module's state with a
   `global` statement writes through the module instead (`team._users_mem =
   None`), and a module that keeps a store in memory lets go of its own
   (`t_every_memory_copy_of_a_store_is_let_go`).
4. **Re-point the tests** that patch or read a moved name to the area's
   module. The tool follows a name it can read, a string in `getattr`
   included; a test that reaches one through a variable
   (`setattr(copilot, path_attr, path)`) is re-pointed by hand, and fails
   loudly until it is. `t_no_test_patches_a_name_nobody_reads` fails on a patch that
   would land on nothing, on a copied name a patch would miss, and on a
   module keeping its own copy (a clock, a client) the test does not patch.
5. **The guards.** `tools/sources.py` lists `copilot.py` and every module
   split out of it; every check that reads the code reads it through there
   (`t_nothing_reads_copilot_py_by_name`), and both security scans cover the
   package. `t_the_split_modules_read_no_unbound_name` catches a name left
   behind on a path no test drives; `t_any_module_imports_first` the
   import order; `t_only_the_stock_bridge_reads_copilot` that nothing but
   the stock bridge's readers still reads `copilot.py`. A check that walks
   module names (the backup's reach,
   `t_backup_is_exhaustive_by_construction`; the clocks, `_every_clock`)
   walks every module in `tools/sources.py`, or each move quietly takes
   names out of it.
6. **The proof.** `make move-proof BASE=origin/main` prints "nothing but the
   move", or names each statement lost, added or changed, each prefix put on
   a local and each moved statement that looks its module up by name. A
   change made on purpose is named with `DECLARED=a,b` and printed before
   and after; everything else must still match. `make api-doc` changes only
   the moved handlers' module; `make env-doc` only the moved settings'
   headings.
7. **Frozen code keeps its bytes.** If a frozen function (the printed
   labels' route) reads a moved name, `copilot.py` takes that name from the
   area by name, which the guard allows only for a name no test patches and
   nothing rebinds, and the area imports `copilot` last. The same holds for
   a name every route uses (`_guard`, `_json`), so the idiom reads as before.
8. **Check the names first.** An alias must not be a local name where the
   moved names are read: `store`, `ai`, `accounts` and `door` all were
   somewhere, which is why the modules read as `jsonstore`, `claude`, `team`
   and `gate`. The move script refuses a clash in the app; in the tests, it
   fails loudly.
