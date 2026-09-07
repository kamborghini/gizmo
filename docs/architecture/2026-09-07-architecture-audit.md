# Architecture audit — 2026-09-07

The whole system, read before anything was changed: gizmo (the Python app, the
single-file SPA, the JSON stores on the Railway volume, the two background
loops, the CI) and the shopify-xero-connector (the Node service beside it).
Every number below comes from a script run over the code as it stands today,
not from memory of it.

The one-sentence verdict: **the dependency direction is right and the pieces
are individually well made; the app is one 22,000-line file with a single
8,893-line function in it, and two of its data-ownership rules are wrong.**

---

## 1. What is here

| Piece | Size | Role |
|---|---|---|
| `server.py` | 1,922 lines | Entrypoint. Shopify GraphQL client, token manager, the 31 MCP tools, the two ASGI middlewares, app assembly, and the eight Shopify *write* capabilities it hands to the app |
| `copilot.py` | 21,991 lines | The app. 46 sections, 493 top-level definitions, 44 store paths, and `add_routes` — one function of 8,893 lines holding all 136 HTTP routes and 63 nested helpers |
| Integrations | 5,800 lines | `worldoptions` (courier SOAP), `recon` (Xero/Gmail reconciliation), `google_mail`, `google_data`, `xero`, `pipedrive`, `eori`, `mailmime` |
| Library | 540 lines | `tokenvault`, `totp`, `logdrain` |
| SPA | 20,618 lines | `static/index.html`: 3,179 CSS + 17,182 JS + 257 HTML, split into hashed assets at serve time. 441 functions, 185 API call sites. `composer.js` beside it |
| Tests | 22,340 lines | `tests/test_dispatch.py` (704 tests, 61 s) and `tests/test_frontend.py` (282 static guards, 2 s). Bespoke runner |
| Data on the volume | 44 stores | JSON files under `/data`, one per concern, plus `dispatch_labels/` and `snapshots/` |
| Connector | 5,237 lines TS | Separate repo, `src/{shopify,xero,mappers,sync,failsafe}`, 16 test files. Cleanly layered already |

### How a request flows

```
browser ──► server.build_app()
              │ CompressionMiddleware ─► MCPAuthMiddleware (only /mcp)
              ▼
            copilot.add_routes(...)         136 routes, all inside one function
              │ _pre_checks   rate window, body cap, _tab_denied (deny-by-default)
              │ _authorize    Shopify session JWT + X-App-Session
              │ _read_json_capped
              ▼
            domain function  (e.g. _dispatch_book_locked, _crm_import_apply)
              │
              ├─► _load_x() / _write_x()   JSON store on /data, atomic replace
              ├─► registry["shopify_*"]    read tools (server.py) via _tool_json
              ├─► injected writers         update_order_tags, create_order_fulfillment … (server.py)
              └─► integrations             worldoptions / xero / google_mail / pipedrive / eori
```

Two background loops start lazily from the first `/healthz`:
`_scheduler_loop` (every 15 min: watchdog, weekly snapshot, CRM link,
Xero keepalive, recon, connector watch, paid audits when due) and
`_mail_loop` (every 60 s: Gmail sync). Both isolate exceptions and email at
most once a day on failure.

### Dependency direction — correct

```
server ──► copilot ──► {worldoptions, recon, xero, google_mail, google_data,
                        pipedrive, eori, mailmime, tokenvault, totp, logdrain}
                                  │
       {xero, google_mail, google_data} ──► tokenvault
```

Acyclic. No integration imports the app. `server.py` injects Shopify write
capabilities into `copilot.add_routes` rather than `copilot` importing
`server`. This is the single most important structural property here and it
already holds.

---

## 2. Findings

Classified as the brief asks. *Where* is a line in `copilot.py` unless noted.

### Critical

None. Nothing found that is losing data or money today.

### High

| ID | Finding | Evidence |
|---|---|---|
| **H1** | **One module, one function.** `copilot.py` holds every layer — config, persistence, domain logic, HTTP, background jobs — and `add_routes` is a single function of 8,893 lines containing all 136 routes and 63 helpers that exist only as closures inside it. Nothing inside it can be imported, tested in isolation, or found without grep. | `add_routes` L13099–21991. 42 `global` statements over 25 names; 7 in-memory caches reached as `copilot._users_mem` from 17,000 lines of tests |
| **H2** | **Dispatch records are silently dropped past 2,000**, while the app's own redaction code retains them "under a legal obligation … HMRC can ask for within six years". `_write_dispatch` trims the oldest with no archive. Production state, by contrast, archives evicted rows to a `.jsonl` before trimming. | `_write_dispatch` L1398 vs `_write_prod_state` L1552; the retention claim at L11622 |
| **H3** | **Size-rule edits default to the container's own filesystem.** `GOBO_OVERRIDES_PATH` and `GOBO_ALIASES_PATH` default to the repo's `data/` directory, and the in-app "Size rules" editor writes there. The size *sheet* already has the right pattern — a live copy on the volume that wins over the repo seed — but the two rule files do not. Unless both variables are set on Railway (neither is documented anywhere), every rule saved in the app is lost at the next deploy, and there were 362 deploys since 1 August. | L3423–3427, `_write_gobo_rule_rows` L3453, `_sizes_path` L3508 |
| **H4** | **The three busiest stores are re-read and re-parsed from disk on every call.** `_load_crm()` has 18 call sites, `_load_dispatch()` 22, `_load_prod_state()` 15 — none cached. The backup code notes a CRM "holding an imported sales history will pass 10 MB". Parsing that on the event loop on every CRM request stalls every other request for the duration. Seven other stores already use an in-memory cache. | loader table below |

### Medium

| ID | Finding | Evidence |
|---|---|---|
| M1 | **35 hand-rolled atomic writers, four safety properties, applied inconsistently.** `allow_nan=False` (a NaN poisons the store on the next read) on 4 of 35; owner-only `0600` on 3; the poison guard on 31; raise-on-unwritable on 12. Today's security pass fixed exactly this class of drift in the courier credential file. | table of writers below |
| M2 | **70 copies of the route preamble** (`_pre_checks` → `_authorize` → `_read_json_capped`) alongside five hand-written guard helpers (`_mail_guard`, `_crm_guard`, `_files_guard`, `_team_guard`, `_auth_guard`) that each return a *different* tuple shape. | 20 distinct preamble shapes across 136 routes |
| M3 | **Configuration is read consistently but documented nowhere.** 203 environment variables are read; `env.example` documents 39 and is the upstream fork's file (it says the API default is `2024-10`; the code says `2026-07`). There is no boot-time check, so a mistyped variable name is a silent default. `SHOPIFY_STORE` is read independently in two modules. | `env.example`; `server.py:31`, `copilot.py` |
| M4 | **The README describes a different product** — the generic "Shopify MCP Server" this repo was forked from. It does not mention dispatch, the CRM, the inbox, the drive, the team, the connector, or how to run the tests. It tells a developer to `cp env.example .env`; nothing loads a `.env` file. | `README.md`, `requirements.txt` (no dotenv) |
| M5 | **No developer entry points.** No `Makefile`, no `scripts/`, no `.claude/launch.json`. The two test commands and the `.venv` requirement exist only in memory. | repo root |
| M6 | **Whole-file rewrite per save.** Every change to the CRM or mailbox serialises and replaces the entire file. Inherent to one-JSON-file-per-store; fine at today's size, the first thing to hurt as the CRM grows. | `_write_crm`, `_write_mail` |
| M7 | **Two booking flows.** `_dispatch_book_locked` (297 lines) and `_custom_book_locked` (251) share 16 helpers and differ in 10; the shared spine is duplicated rather than extracted. | L6306, L5767 |
| M8 | **Timestamp field names vary by store**: `created_at`/`updated_at` (CRM, files), `at` (privacy log, alerts), `t` (audit ledger), `state_at`/`printed_at`/`made_at`/`dispatched_at` (domain stamps). | grep counts 57 / 80 / 12 / 19 |
| M9 | **`requirements.txt` carries two packages nothing imports** (`requests`, `pillow`) and three transitive packages pinned with no note saying why (`pyasn1`, `python-multipart`, `pydantic-settings`). | import scan vs requirements |

### Low

| ID | Finding | Evidence |
|---|---|---|
| L1 | 5 dead functions (`_context_block`, `_orders_monthly_revenue`, `_mail_footer_text`; `_load_wo_failures` and `_mail_outgoing_text` referenced only by tests) and 3 routes the SPA never calls (`/api/team/me`, `/api/google/status`, `/api/mail/disconnect`). | reference scan |
| L2 | 19 `except Exception: pass`. Most guard "must never raise" paths (audit rows, alert emails) and say so; a few do not. | grep |
| L3 | The SPA is 441 functions in one file with 51 comment banners as its only module boundary. Deliberate (no build step; the 282 guards depend on it being one file), and it works — but it is the same shape as H1 and will meet the same limit. | `static/index.html` |
| L4 | `add_routes` takes eight injected capabilities as keyword arguments. Fine at eight; a small dataclass the day it is twelve. | `server.py:1894` |

### Acceptable — leave alone

- **The dependency direction** (§1). Do not "improve" it.
- **JSON files as the database.** One process, one merchant, one volume, an
  event loop that serialises writes, atomic replace, a poison guard, per-store
  caps, weekly snapshots, a tested backup/restore. For this scale that is the
  boring, proven answer. See §4 for the trade-off against SQLite.
- **The bespoke test runner.** 704 tests in 61 seconds through the real app
  (`build_app()`, real middleware). Moving to pytest is churn with no behaviour
  change; the runner's per-test rate-limit reset is a feature.
- **The single-file SPA split at serve time.** A build step would cost more
  than it saves and the guards are written against one file.
- **The integration modules.** Each is focused, holds one or two module-level
  values, and reaches no other layer. `worldoptions.py` at 1,658 lines is
  large because SOAP is verbose, not because it does two jobs.
- **The two background loops.** Simple, exception-isolated, self-throttling.
- **The MCP server and tool registry seam.** `server.py` builds the registry;
  `copilot.py` derives the Anthropic tool schemas from it; the AI is read-only
  by construction.
- **The root container.** Written risk acceptance in the Dockerfile; the fix
  needs a scratch volume to prove.
- **The security controls** audited earlier today.

---

## 3. The stores, and who owns what

Forty-four files. The ones that hold relationships:

| Store | Key | Refers to | Owned by | On delete |
|---|---|---|---|---|
| `users.json` | uid | — | Team | Soft: `deleted`, `active=False`; sessions dropped, drive cache dropped, owned mail released. Rows in every other store keep the uid as history |
| `sessions.json` | sha256(token) | users.uid | Auth | Hard, by expiry or logout |
| `dispatch_state.json` | Shopify order id | users.uid (`by`), courier refs, `email` | Dispatch | **Never** (retained; annotated on redaction) — but see H2 |
| `production_state.json` | Shopify order id | users.uid | Production | Evicted past 1,000, archived to `.jsonl` first |
| `crm.json` | local ids (`p…`, `o…`, `d…`) | persons→orgs, deals→persons/orgs, activities→deals; `pd_id` to Pipedrive; `shopify_customer_id` | CRM | Org delete refused while open deals exist; person/org delete tombstones the Pipedrive id; redaction tombstones (fixed today) |
| `mailbox.json` | Gmail thread id | users.uid (`owner`), crm person id, `from_email` | Inbox | Threads age out at 730 days; redaction removes and records the address |
| `files.json` | fid / folder id | users.uid (`by`), folder→parent, R2 key | Files | Trash → 30 days → doomed list → bucket reap. Folder delete refused while it holds live files |
| `loans.json` | unit id | customer email, order id | Loans | Hard |
| `worklog.json` | session id | users.uid | Work | Append-only |
| `activity.json` | — | users.uid (`sub`) | Audit | FIFO at 8,000 (a loss the register calls out; drain when set) |
| `recon*.json`, `collections.json`, `chase_log.json`, `customs_memory.json` | order / invoice ids | Xero, Shopify | Recon / Chase / Customs | Windowed by days |

The relationships are enforced in code, consistently and with tests; there is
no database to enforce them, and no foreign key is left dangling silently —
the one exception found today (H2) is a cap, not a cascade. Cross-store
writes are not transactional: a booking writes dispatch state, then labels,
then the ledger. Each write is atomic on its own and the booking is recorded
*first*, so a crash leaves a bookable record rather than a paid-for label with
no record. That ordering is the right design for this storage and should be
stated where it lives (§5, stage 6).

---

## 4. Should the database be a database?

The honest trade-off, so it is written down once.

**Keep JSON-per-store** (recommended now): zero migration risk on a live
dispatch desk with a deploy-on-push pipeline and no staging; the hard parts
(atomicity, poison, caps, backup, restore) are done and tested; every store is
readable with `cat`. Costs: no cross-store transactions, whole-file rewrites,
no indexes, integrity lives in code.

**Move to SQLite** (later, if ever): transactions across stores, indexes, real
constraints, cheap partial writes. Costs: 44 stores × loader/writer pairs to
migrate, every test fixture that writes JSON directly, the backup/restore and
snapshot code, and a migration that must run once against the real volume with
no rehearsal environment. Weeks of work; a mistake is the CRM.

The trigger to revisit is concrete: when a CRM or mailbox save is measurably
slow (§2 M6), or when a second process ever needs the data. Until then, the
two real integrity defects (H2, H3) are fixed in place and the persistence
primitive is made single (M1), which is most of what a database would have
bought.

---

## 5. What changes, in stages

Each stage is one commit, verified by both suites before the next. The order
is by risk-adjusted value: integrity first, then the two primitives that
remove the most duplication, then the surfaces a developer meets first.

| Stage | Change | Benefit | Risk |
|---|---|---|---|
| **1. Integrity** | Archive evicted dispatch rows before trimming (H2). Size-rule files get a live volume path with the repo file as seed, exactly as the sheet does (H3). Remove the 5 dead functions and 3 dead routes (L1). Drop `requests` and `pillow`; annotate the transitive pins (M9). | Two data-loss paths closed; nothing dead left to maintain | Low — additive, tested |
| **2. One writer** | `_write_json_store(path, key, data, *, private=False)` with poison guard, `allow_nan=False`, `0600` when private, atomic replace, and a `RuntimeError` on refusal. The 35 writers become two-line wrappers. | Every store gets every safety property; the next store cannot forget one | Low — mechanical, every store has tests |
| **3. One guard** | `_guard(request, *, ai=False, min_level=0, max_body=None, cap=None) → (error, body, uid)`. The 70 inline preambles and 5 guard helpers use it. | ~600 lines gone; one place to change the door | Low–medium — 75 edits in one function, each identical in shape |
| **4. Config** | A boot-time check that logs unknown-but-similar names and required-but-missing values; a stdlib `.env` loader (12 lines, only when the file exists and the variable is unset); `env.example` regenerated from the code with every variable, its default and its module; `SHOPIFY_STORE` read once. | The README's own instructions work; 164 undocumented knobs become documented; typos surface at boot | Low |
| **5. Caching** | `_load_crm`, `_load_dispatch`, `_load_prod_state` cache on `(mtime, size)` — the pattern the size-rule loader already uses — so a `stat()` replaces a parse, and an external write (restore, a test removing the file) invalidates without anyone remembering to. | Event-loop stalls proportional to CRM size disappear from every CRM route | Low–medium — cache invalidation, but keyed on the file itself |
| **6. Ergonomics** | `Makefile` (`run`, `test`, `test-frontend`, `check`, `sweep`), `.claude/launch.json`, a README that describes gizmo, and `docs/ARCHITECTURE.md` carrying the map in §1 and §3 plus "where does X belong". | A developer can answer every question in the brief's *Daily usability* list from the repo | None |
| **7. Split** | `copilot.py` → a package (§6). **Proposed, not done in this pass.** | Findability, ownership, diffs, review | **High** — see §7 |

### Deliberately not changed

- **The module split is designed but not executed** (§7).
- **The two booking flows** (M7). The shared spine could be extracted, but
  the two differ in exactly the places a wrong merge would send a parcel to
  the wrong address. Consolidate the day either is next changed for a reason
  of its own, with the diff in front of you.
- **Timestamp naming** (M8). Renaming fields in stores that are on the volume
  is a data migration for a cosmetic gain. New stores use `created_at` /
  `updated_at`; old ones keep their names, documented.
- **The SPA's structure** (L3). Same reasoning as H1 applied to a file the
  guards depend on; revisit when the backend split has proven the approach.
- **The bespoke runner, the JSON stores, the root container, the single-file
  SPA** — the Acceptable list above.
- **Anything in the security controls** audited this morning.

---

## 6. The target structure

Where things go once H1 is addressed. The layering is the one the brief
proposes, because it is the one the code already follows implicitly.

```
server.py                 entrypoint: build_app(), Shopify client, MCP tools, capability injection
gizmo/
  config.py               every environment variable, one place, checked at boot         (stage 4)
  store.py                _load_json_store / _write_json_store, caches, locks, poison      (stage 2)
  http.py                 _json, _guard, _pre_checks, rate windows, _tab_denied          (stage 3)
  auth.py                 users, sessions, passwords, MFA, drive auth
  audit.py                _track, the ledger, coalescers
  domains/
    dispatch.py  production.py  crm.py  mail.py  files.py  recon.py  loans.py
    team.py      chat.py        overview.py  seo.py  customers.py  stock.py
  routes/
    dispatch.py  …  one module per prefix; each exports register(app, deps)
  jobs.py                 the scheduler loop, the mail loop, the ticks
integrations/             worldoptions  xero  google_mail  google_data  pipedrive  eori  mailmime
lib/                      tokenvault  totp  logdrain
static/                   index.html  composer.js
tests/
tools/
```

**Where does this logic belong?** — the rule a developer applies without
guessing: *a route parses and answers; a domain module decides; a store module
reads and writes; an integration talks to one external system and knows
nothing about the app.* If a function needs two of those, it is in the wrong
file.

---

## 7. The split, and why not today

The split is the right end state and the wrong next step.

What makes it expensive is not the 22,000 lines; it is the 42 `global`
statements and the seven module-level caches that 17,000 lines of tests reach
as `copilot._users_mem = None`, `copilot.R2_ACCOUNT_ID = "acct"`,
`copilot._check_pw = counting`. Moving a cache into another module silently
breaks every such assignment: the test sets a name on `copilot` that nothing
reads any more, and the suite passes while testing nothing. Each moved
section therefore needs its state turned into an object the tests can patch
by reference, and every fixture that touches it updated in the same commit.

That is a week of careful work per few sections, on a desk that deploys on
every push to `main` with no gate (the security audit's H3) and no staging
service. Stages 1–6 above deliver most of the daily benefit — one persistence
contract, one door, documented config, a map — at a small fraction of the
risk, and they make the split *easier* afterwards: a section whose stores go
through one primitive and whose routes go through one guard moves with far
fewer edges.

**The recommended order:** close the deploy gate, land stages 1–6, then split
one section at a time — dispatch first, because it has the best tests and the
clearest boundary — each as its own reviewed change.
