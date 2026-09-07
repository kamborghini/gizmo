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
              │
              │  _guard(request)     the one door: rate window, tab gate, session,
              │                      rank, the AI slot, the body - in that order
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
server ──► copilot ──► integrations (worldoptions, xero, google_mail, google_data,
                                     pipedrive, eori, recon, mailmime)
                   ──► libraries    (tokenvault, totp, logdrain)
```

Acyclic, and it stays that way. An integration never imports the app: it
takes what it needs as arguments and returns plain data. `server.py` hands
its Shopify *write* capabilities into `copilot.add_routes` as arguments
rather than `copilot` importing `server`; the assistant's tool registry
travels the same way, which is why the AI is read-only by construction.

## Where does this logic belong?

| It... | It goes in | It never |
|---|---|---|
| parses a request, checks who is asking, answers JSON | a **route**, inside `add_routes`, behind `_guard` | decides anything a domain function could |
| decides what should happen to an order, a person, a thread, a file | a **domain function** at module level, in its section | reads `request`, returns a `JSONResponse`, or calls `_json` |
| reads or writes a store | the store's **`_load_x` / `_write_x` pair**, over `_load_json_store` and `_write_json_store` | opens a file anywhere else |
| talks to Shopify | the **tool registry** for reads; an **injected writer** for writes | reaches `server.py` directly |
| talks to Google, Xero, the courier, Pipedrive, HMRC | that system's **integration module** | knows the app's stores or routes exist |
| runs on a timer | a **tick** called from `_scheduler_loop` or `_mail_loop` | starts its own thread or loop |
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
  Static guards on the page live in `tests/test_frontend.py`.

## How to add

**A route.** Register it inside `add_routes` under the prefix's section, add
the prefix to `_TAB_ROUTES` (unmapped `/api/` routes are refused by design),
open with `err, body, who = await _guard(request)`, call a domain function,
return `_json`. Write the test first; `post()` and `post_s()` in the suite
are the two ways to call it.

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
with its own `try`/`except`, self-throttled by a stamp in `watch.json` if it
must not run every tick.

**A tab.** A key in `TAB_KEYS`, its routes in `_TAB_ROUTES`, and — if the
assistant gets tools for it — those tools in `_TOOL_TABS`.

## What is deliberately the way it is

- **`copilot.py` is one file.** The split into a package is designed (audit
  §6) and deferred (§7): the test suite reaches module state by name, and the
  deploy pipeline has no gate yet. Do it one section at a time, dispatch
  first, after the gate.
- **JSON stores, not a database.** The trade-off is written down in the
  audit (§4). The trigger to revisit is a measured slow save.
- **The page is one file.** No build step; the guards depend on it. The
  split into assets happens at serve time.
- **The container runs as root.** A written risk acceptance in the
  Dockerfile; the fix needs a scratch volume to prove.
- **The test runner is our own.** Seven hundred tests in a minute through
  the real app; pytest would change nothing but the spelling.
