# gizmo

The back office for Projected Image UK's Shopify store: the dispatch desk,
production labels, the sales records, the shared inbox, the file drive, the
team, loan units, reconciliation against Xero, and an assistant that can read
the store and never write to it. It runs embedded inside Shopify admin and as
its own page on Railway, and it also serves a Model Context Protocol endpoint
so Claude can be pointed at the store directly.

Two services: this one (Python, Starlette, one process, JSON stores on a
volume) and the [shopify-xero-connector](../shopify-xero-connector) beside
it (Node, posts invoices into Xero). The map of how the pieces fit is
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Run it locally

```bash
make install            # a .venv with the pinned requirements
cp env.example .env     # then fill in the values you have
make run                # http://localhost:8000, .env is loaded by the shell
```

`env.example` is the short list, grouped by what each variable turns on. The
complete reference, generated from the code and kept current by CI, is
[docs/ENVIRONMENT.md](docs/ENVIRONMENT.md). Every variable has a default, so
the app runs with none of them set — each feature is simply off, and the boot
log says which ones.

Nothing loads `.env` inside the app. `make run` sources it in the shell, so a
developer's local file can never leak into the test suite, and production —
where Railway injects the variables — never has one.

## Test it

```bash
make test            # the dispatch suite: 700-odd tests through the real app, about a minute
make test-frontend   # the static guards on the single-page app, a few seconds
make check           # everything CI runs that needs no network
```

`tests/test_dispatch.py` builds the app exactly as it is served
(`server.build_app()`, real middleware) and drives it with a test client
against scratch stores; nothing touches `/data` or the network.
`tests/test_frontend.py` reads `static/index.html` and asserts the rules the
page has to keep — every one of them a regression that once reached the
merchant. Both run on every push.

## Where things are

| Path | What it is |
|---|---|
| `server.py` | The entrypoint: Shopify client, the MCP tools, app assembly, and the write capabilities it hands to the app |
| `copilot.py` | The app: every route, every domain, every store. Large; sectioned; the architecture note says where to look |
| `worldoptions.py` `xero.py` `google_mail.py` `google_data.py` `pipedrive.py` `eori.py` `recon.py` | One module per external system. None of them knows about the app |
| `tokenvault.py` `totp.py` `logdrain.py` `mailmime.py` | Small libraries: secrets at rest, one-time codes, off-box logging, mail parsing |
| `static/index.html` `static/composer.js` | The single-page app, authored as one file and split into hashed assets at serve time |
| `data/` | Seed files that ship with the code: the size sheet, the rule files, the changelog, a font |
| `extensions/` | The three Shopify admin actions (print label, print labels, dispatch) |
| `tests/` `tools/` | The two suites; the credential sweep and the environment-reference generator |
| `docs/` | The architecture note, the security registers, the audits, the courier API notes |

## Deploy

Railway builds the `Dockerfile` and deploys every push to `main`. There is no
staging service, so a push is a deploy: run `make check` first, and keep the
branch protected so a red build cannot reach the desk (this is the open item
in the security register). The data volume mounts at `/data`; everything the
app keeps lives there and is covered by the in-app backup.

The Shopify app configuration is `shopify.app.toml`; changing scopes or the
compliance webhooks needs `npx @shopify/cli@latest app deploy`, which forces a
reinstall on the store.

## The MCP endpoint

`/mcp` exposes the Shopify tools to Claude.ai, including writes. It answers
503 until `MCP_BEARER_TOKEN` is set; use the same value in the Claude.ai
integration. The in-app assistant is a different thing: it uses a curated,
read-only subset of the same tools, gated per account by tab.

## Security

The current posture, what was fixed and what remains open is in
[docs/security/2026-09-07-appsec-audit.md](docs/security/2026-09-07-appsec-audit.md);
the two earlier hardening registers sit beside it. Secrets live in Railway's
variables and nowhere else — never in the code, never pasted into a chat or a
document. The only credential the app should ever show you is a starter
password, once.

## Troubleshooting

**The boot log says `config: ... is not set`.** That feature is off. The line
says which one and what it turns off.

**Reads from Shopify fail (401 / 403).** The access token is wrong, expired, or
missing a scope. Settings → Connections shows the scopes the install actually
has, read from Shopify rather than from the config file.

**A store is "unreadable" in the log and nothing saves to it.** The poison
guard found a file that does not parse and refuses to overwrite it, so the
broken file is preserved for repair. Fix or restore the file; the guard clears
itself on the next successful read.

**The embedded app opens blank.** Only served when loaded from Shopify admin
(the URL carries `shop`/`host`/`embedded`). A direct visit to the Railway URL
shows the sign-in page instead.
