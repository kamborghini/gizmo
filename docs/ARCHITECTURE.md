# Architecture

How gizmo is put together, where each kind of logic belongs, and how to add
to it without guessing. The assessment this was written from, with the
findings and the trade-offs, is
[architecture/2026-09-07-architecture-audit.md](architecture/2026-09-07-architecture-audit.md).

## The shape

```
browser ──► server.build_app()
              │  CompressionMiddleware ─► MCPAuthMiddleware (only /mcp)
              ▼
            copilot.add_routes(app, tool registry, write capabilities)
              │  hands the capabilities on, registers each area's routes
              ▼
            gizmo/routes/<area>.py   register(mcp, registry): the area's routes
              │
              │  _guard(request)     the one door: rate window, tab gate, session,
              │                      rank, the AI slot, the body, the body's
              │                      fields (model=) - in that order
              ▼
            a domain function       decides; never parses a request, never talks HTTP
              │
              ├─► _load_x() / _write_json_store()   a JSON store on /data
              ├─► registry["shopify_*"]            reads, through the tool registry
              ├─► an injected writer                update_order_tags, create_order_fulfillment ...
              └─► an integration module            worldoptions, xero, google_mail, pipedrive, eori
```

Two background loops start from the first `/healthz`: the scheduler (every
15 minutes: watchdog, weekly snapshot, CRM linking, Xero keepalive,
reconciliation, connector watch, the paid audits when due) and the mail loop
(every minute: Gmail sync). Each isolates its own exceptions and emails at
most once a day when it keeps failing.

### Dependency direction

```
server ──► copilot ──► gizmo/routes/<area> ──► gizmo/<area> ──► the floor
                              integrations (worldoptions, xero, google_mail, google_data,
                                            pipedrive, eori, recon, mailmime)
                              libraries    (tokenvault, totp, logdrain)
```

Beneath every area is the floor, modules that import nothing above them
(`t_the_floor_imports_nothing_above_it`): `gizmo/config.py` (settings, the
shop's own among them), `gizmo/store.py` (every JSON store, the one writer,
the cache, the poison guard), `gizmo/errors.py` (the error log), `gizmo/ai.py`
(the AI client: models, the call and its fallbacks, usage, the spend cap),
`gizmo/shopify.py` (the way to Shopify: reads through the tool registry, and
the write capabilities `server.py` hands in, which `add_routes` stores
there), `gizmo/prompts.py` (the AI's instructions: the writing style, the
chat's and the reports' prompts, and the `present_response` tool every answer
comes back through), `gizmo/clock.py` (today's date and time in London),
`gizmo/bodies.py` (the kinds a request's fields are checked against at the
door: a model names the fields a route reads, and a field of the wrong kind is
a 400 naming it) and `gizmo/background.py` (work that runs after the request
that asked for it, held until it is done). Everything reads them through the
module's name: `jsonstore.NAME`, `errors.NAME`, `claude.NAME`, `shopify.NAME`,
`prompts.NAME`, `clock.NAME`, `bodies.NAME`, `background.spawn`. The store
names no area: an area that keeps something built from a store registers
`jsonstore.when_forgotten(fn)`, and an area that keeps a whole store in memory
registers how to let go of it (`jsonstore.holds_in_memory(drop)`), which
restore and shop/redact call.

Above the floor, the areas, each a module in `gizmo/` with its routes in
`gizmo/routes/`: the dispatch desk (`gizmo/dispatch.py`, read as `desk`), the
team's accounts and sign-in (`gizmo/team.py`), the door every route opens
with (`gizmo/gate.py`), the activity log (`gizmo/activity.py`), the order book
(`gizmo/orderbook.py`), production and its label builder
(`gizmo/production.py`; what the bench prints is pinned by
`t_the_printed_labels_do_not_change`), the Size list (`gizmo/size_list.py`),
the CRM (`gizmo/crm.py`, read as `salesdesk`) and the shared inbox
(`gizmo/mail.py`), Files (`gizmo/files.py`, read as `fileserver`), the Finder
drive (`gizmo/webdav.py`), customer-data erasure (`gizmo/privacy.py`), the
loan register (`gizmo/loans.py`), work sessions (`gizmo/work.py`), skills
(`gizmo/skills.py`, read as `skillbook`), memory (`gizmo/memory.py`), store
knowledge (`gizmo/knowledge.py`) and the chat loop (`gizmo/chat.py`, read as
`assistant`), SEO and keywords (`gizmo/seo.py`), the overview and customer
reports (`gizmo/analytics.py`), the scheduler and its alerts
(`gizmo/scheduler.py`), release notes and requests (`gizmo/updates.py`),
impact tracking (`gizmo/impact.py`), backup and restore (`gizmo/backup.py`),
Liability and the chase desk (`gizmo/liability.py`), reconciliation with the
Xero connect walk (`gizmo/reconciliation.py`), the Xero sync settings
(`gizmo/xero_sync.py`, read as `xerosync`), the forecast's hooks
(`gizmo/forecasting.py`), the page and its assets (`gizmo/rendering.py`), the
store profile (`gizmo/profile.py`, read as `store_profile`), layouts
(`gizmo/layouts.py`), the sign-in walks (`gizmo/oauth.py`), the status page
(`gizmo/status.py`, read as `appstatus`) and the Products tab
(`gizmo/products.py`, read as `catalog`). They read each other through the
module's name, never a copied name, and import another area last, so nothing
is read across as a module loads and any module can be imported first
(`t_any_module_imports_first`).

`copilot.py` (about 1,250 lines) keeps, on purpose: `add_routes`, which hands
the capabilities `server.py` passes in to the modules that use them (the
Shopify writers to `gizmo/shopify.py`, the chat's tools to `gizmo/chat.py`),
sets up reconciliation and registers every area's routes; the frozen print
routes with their font, logo and CORS helpers, which keep their bytes; and the
stock bridge (the stock merge project's, hands off). Nothing reads
`copilot.py` but the stock bridge's readers: the scheduler, production's
routes and the status page (`t_only_the_stock_bridge_reads_copilot`). It
reads the areas as everyone does, except names it takes by their own: `_guard`
and `_json` for its own routes, and what the frozen print route reads (two of
the desk's, the shop secret and the public base address from
`gizmo/config.py`, and `_spawn_bg`, which hands to `background.spawn`).

Acyclic otherwise, and it stays that way. An integration never imports the app: it
takes what it needs as arguments and returns plain data. `server.py` hands
its Shopify *write* capabilities into `copilot.add_routes` as arguments
rather than `copilot` importing `server`; the assistant's tool registry
travels the same way, which is why the AI is read-only by construction.

## Where does this logic belong?

| It... | It goes in | It never |
|---|---|---|
| parses a request, checks who is asking, answers JSON | a **route**, in its area's `gizmo/routes/<area>.py`, behind `_guard` and a body model | decides anything a domain function could |
| decides what should happen to an order, a person, a thread, a file | a **domain function** at module level, in its section | reads `request`, returns a `JSONResponse`, or calls `_json` |
| reads or writes a store | the store's **`_load_x` / `_write_x` pair**, over `_load_json_store` and `_write_json_store` | opens a file anywhere else |
| talks to Shopify | the **tool registry** for reads; an **injected writer** for writes | reaches `server.py` directly |
| talks to Google, Xero, the courier, Pipedrive, HMRC | that system's **integration module** | knows the app's stores or routes exist |
| runs on a timer | a **tick** called from `_scheduler_loop` or `_mail_loop` | starts its own thread or loop |
| runs after the request that asked for it | `background.spawn(coro)` | calls `asyncio.create_task` bare |
| records that a person did something | `_track(uid, area, action, detail)` | logs it to stdout instead |

If a function needs two rows of this table, it is in the wrong file.

## The stores

Every store is one JSON file on the volume, read with `_load_json_store(path,
key, default)` and written with `_write_json_store(path, key, data)`. The
writer is the only way to disk: it refuses a store the poison guard has
paused, refuses NaN, writes a temp file and swaps it in, and creates the file
owner-only when asked. Each store has a two-line `_write_x` wrapper carrying
its own policy — whether it raises, whether it resets a memory cache, whether
it trims to a cap and archives what it trims.

| Rule | Why |
|---|---|
| Every path is a module-level constant with a `/data` default, read from the environment | one config strategy; the test harness points them at scratch |
| A store that can grow has a cap, and a cap that drops legal records archives them first | `dispatch_state` and `production_state` archive to `.jsonl` beside themselves |
| Seven hot stores keep an in-memory copy; the rest are read from disk per request | "memory never outlives a failed write" — the writer resets the cache on refusal |
| Credentials are sealed with `tokenvault` before they are written | the boot re-seal covers what was written before the key existed |
| Cross-store writes are not transactional; the record is written **first** | a crash leaves a bookable record, never a paid-for label with no record |

The three busiest stores (dispatch, production, CRM) cache on the file's
own stat key, so a restore or a hand repair invalidates without anyone
remembering to. Sizes and read costs are in the boot log and Settings →
Connections.

Who owns what, and what happens on delete, is tabulated in the audit (§3).

## Configuration

One strategy: every setting is an environment variable, read once at import
into a module-level constant with a default, next to the section that uses
it. There is no settings object and no `.env` loader in the code. `make run`
sources `.env` in the shell for local work; Railway injects the variables in
production. [ENVIRONMENT.md](ENVIRONMENT.md) is generated from the code and
CI fails when it is stale; `env.example` is the short version.

The boot log names the handful of variables a person would notice missing
and what each turns off. Everything else defaults to "that feature is off".

## Conventions

- **Errors** are `_json({"error": "a sentence a person can act on"}, status)`.
  A domain function raises; the route turns the exception into that shape.
  Anything that must never fail a booking (an audit row, an alert email)
  catches, logs with `logger.exception`, and says so in a comment.
- **Audit**: anything a person does that another person might ask about is
  `_track`ed. Repeated refusals are coalesced (see `_track_login_noise`).
- **Names**: snake_case Python, camelCase JS, kebab-case routes under `/api/`.
  New stores use `created_at` / `updated_at`; old ones keep their names.
- **Comments** say why, not what. The house style is a paragraph on the
  decision above the code that makes it.
- **Tests** are `@test` functions in `tests/test_dispatch.py`, run in file
  order by the runner at the bottom. A test that needs accounts wraps itself
  in `with_accounts(go)`; one that needs the file store in `with_files(go)`.
  A run prints one line per test; what the app logged during a test is shown
  under its FAIL line only. `VERBOSE=1` streams every log line as it comes,
  and `ONLY=part_of_a_name` runs the tests whose names contain it.
  Static guards on the page live in `tests/test_frontend.py`.

## Tests

| Suite | What it sees | What it cannot see |
|---|---|---|
| `tests/test_dispatch.py` | The server through its routes, built as it is served, against scratch stores and stand-ins for every outside system | Anything the page does with an answer |
| `tests/test_frontend.py` | The page's source as text, and its logic run in node | Layout, rendering, a selector that matches nothing |
| `tests/test_forecast.py` | The forecast package | The app |
| `tests/browser/` | Every screen in Chromium at phone, laptop and wide sizes, in a world seeded through the app's own code: script errors, failed or outside requests, writes, sideways scroll, spill, the panel rules, accessibility (axe, WCAG 2.2 AA) and three windows by keyboard | Firefox and Safari; the Shopify admin frame itself |

`make move-proof` (`tools/move_proof.py`) compares the code with a base ref
after a move: see `tools/moves/README.md`.

The browser suite holds panel-rule and accessibility findings in a ratchet
(`tests/browser/record/`): a pull request fails if a count goes up, and if
one goes down without the record being lowered to match.

## How to add

**A route.** In its area's `gizmo/routes/<area>.py`, inside
`register(mcp, registry)` (a new area: a new module there and one `register`
call in `add_routes`). Add the prefix to `_TAB_ROUTES` (unmapped `/api/`
routes are refused by design),
open with `err, body, who = await _guard(request, model=ItsBody)`, where
`ItsBody` is a `bodies.Body` beside the route naming every field it reads
(`t_write_routes_check_their_bodies` fails on a new write route without one),
call a domain function, return `_json`. Write the test first; `post()` and
`post_s()` in the suite are the two ways to call it. Then `make api-doc`: CI
fails while `docs/API.md` does not list it.

**An error you let go.** A broad `except` that passes, skips or returns
without a word says why in a comment on its own lines, or logs;
`t_no_error_is_swallowed_without_a_reason` (with `tools/broad_excepts.py`)
fails on one that does neither.

**A page section.** A file in `static/src/js` or `static/src/css`, whole
lines ending in a newline, and its line in `static/src/manifest.json` where it
belongs in the script's order or the cascade.

**A window.** `dialog()` (`static/src/js/part-dialog.js`); never build or
remove a `.modal-overlay` by hand (a page-suite guard fails). The design rules,
windows included, are in `docs/DESIGN.md`.

**A screen.** One entry in `tests/browser/screens.js` whose steps end by
waiting for content only the seed puts there; if it needs data, add it in
`tests/browser/seed/` through the app's own routes first, and a seeded text
to `tests/browser/test_world.py`.

**A store.** A `_PATH` constant with a `/data` default; a `_load_x` over
`_load_json_store`; a `_write_x` over `_write_json_store` that states its
policy; a cap if it can grow; a line in the test harness's `os.environ.update`
pointing it at scratch; a decision on whether the backup carries it
(`_build_backup_zip` excludes credentials by name).

**An integration.** A new module that imports nothing from the app, takes a
config from the environment at its own top, exposes plain functions that
return plain data, and has a `configured()` / `status()` pair for the
Settings panel. Add it to `MODULES` in `tools/env_reference.py` and to the
bandit list in CI.

**A background job.** A `_x_tick()` function, called from `_scheduler_loop`
with its own `try`/`except`, self-throttled by a stamp in the scheduler's
watch store (`_load_watch`) if it must not run every tick. Work a request owes
after it has answered goes to `background.spawn(coro)`.

**A tab.** A key in `TAB_KEYS`, its routes in `_TAB_ROUTES`, and — if the
assistant gets tools for it — those tools in `_TOOL_TABS`.

## How the backend was split

`copilot.py` held the whole backend until October 2026: 28,623 lines, one
`add_routes` of 8,684 lines and 150 routes. Stage 4 of the 14 October audit
moved it into the `gizmo` package an area at a time, each a pure move proven
by `make move-proof`; stage 6 cut the last reads back. The recipe and the move
tool (`tools/move_area.py`) are in `tools/moves/README.md`, kept for the stock
bridge's move.

## What is deliberately the way it is

- **A package of areas, not services.** One process, one page, the areas
  in `gizmo/` as the September audit designed them (§6). The stock bridge
  stays in `copilot.py` until the stock merge project moves it.
- **JSON stores, not a database.** The trade-off is written down in the
  audit (§4). The trigger to revisit is a measured slow save.
- **The page is one script in sections.** `static/src/` holds the shell, the
  stylesheet's sections and the script's sections, in the order
  `static/src/manifest.json` gives; `pagesource.py` joins them at start-up
  into the one page the server has always served (one function scope, split
  into two hashed assets at serve time). No build step. A screen's code is in
  its own file (`static/src/js/crm.js`, `static/src/js/production-manager.js`); a page-suite guard
  fails until a new file and its manifest line both exist.
- **The container runs as root.** A written risk acceptance in the
  Dockerfile; the fix needs a scratch volume to prove.
- **The test runner is our own.** A thousand tests through the real app,
  one line each; pytest would change nothing but the spelling.
