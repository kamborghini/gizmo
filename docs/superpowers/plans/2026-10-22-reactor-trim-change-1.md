# Reactor trim, change 1: the reports and Reconciliation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Overview, SEO, Keywords, Products, Customers, Reconciliation, Reactor's own Xero link, the Google data connection and the finance mailbox, with every kept page working exactly as before.

**Architecture:** Move the shared pieces that live inside doomed files to kept homes first (each move proven by a test), then delete the areas backend-first, then the front end, then the references, docs and locks. Every task leaves both suites green.

**Tech Stack:** Python 3.14 (Starlette via FastMCP), vanilla JS bundle (static/src, manifest.json), the repo's own suites: `tests/test_dispatch.py` (t_ functions), `tests/test_frontend.py`, the Playwright browser suite.

**Spec:** docs/superpowers/specs/2026-10-22-reactor-trim-design.md (change 1 only)

## Global Constraints

- Worktree `~/Desktop/claude/gizmo/.claude/worktrees/reactor-trim`, branch `trim/reports-and-reconciliation`; python is `~/Desktop/claude/gizmo/.venv/bin/python` (PY below).
- Nothing about the Inbox or the CRM changes in this change: every check they make passes for exactly the accounts it passes for today.
- No Shopify app scope changes; no change to the connector service or its "When a total disagrees" / "Tolerance" settings.
- UI copy: no em or en dashes (CI greps static/src).
- New changelog note in data/changelog.json dated 2026-10-22, plain words, no UPPER_SNAKE names, no developer words.
- The "no test patches a name nobody reads" meta-test: never patch a module attribute that the code under test does not read.

## Review Focus

1. A non-master account with the default tabs opens Labels: the order-history line still loads (customer-history still accepts `customers`).
2. A non-master account asks Chat for an order: still answered (gate still `customers`); asks for payouts: answered only with Xero sync granted.
3. A user record whose saved tab list still names `overview`, `seo`, `keywords`, `products` or `recon` loads and signs in cleanly.
4. A backup taken after deploy, while the old token files are still on the volume, contains none of them; restoring an old backup does not write analysis_cache.json, schedule.json or recon*.json.
5. Every kept page that formats money (Forecast, Liability, Loans, Xero sync, Dispatch, Labels queues, charts) renders without a ReferenceError.

---

### Task 1: Move the shared pieces to kept homes

**Files:**
- Create: `gizmo/storefront.py` (the guarded fetch: `_domains_cache`, `async _resolve_domains(registry) -> tuple[str, set]`, `async _http_get(url, allowed_hosts=None) -> tuple[Optional[int], str]`, moved verbatim from gizmo/seo.py)
- Modify: `gizmo/knowledge.py` (read `storefront.` instead of `seo.`), `gizmo/liability.py` (own `_CURRENCY_SIGNS = {"GBP": "£", "USD": "$", "EUR": "€"}`), `gizmo/config.py` (`CONNECT_SECRET = os.environ.get("GOOGLE_CONNECT_SECRET", "")`), `gizmo/routes/mail.py` (read `config.CONNECT_SECRET`), `static/src/js/icons-and-formats.js` (gains `_moneyFmts`, `moneyFmt`, `money`, `fmtMoney`, `_moneyShortFmts`, `moneyShort` verbatim from products.js lines 14-57; `pct1` stays behind, only Keywords uses it)
- Test: `tests/test_dispatch.py`, `tests/test_frontend.py`

- [ ] Step 1: dispatch test `t_learn_my_store_fetches_through_the_storefront_guard`: `knowledge` reads `storefront._http_get`/`_resolve_domains` (patch `storefront._http_get`, run `knowledge._discover_content_urls`, assert the fake was called); `t_the_connect_secret_lives_in_config`: `config.CONNECT_SECRET == os.environ.get("GOOGLE_CONNECT_SECRET", "")` and routes/mail.py source names `config.CONNECT_SECRET`. Frontend test `t_the_money_formatters_live_with_the_formats`: icons-and-formats.js defines `function money(`, `function moneyShort(`, `const fmtMoney`; products.js does not.
- [ ] Step 2: run both suites, the three tests fail.
- [ ] Step 3: make the moves; repoint existing SSRF tests from `seo._http_get` to `storefront._http_get`.
- [ ] Step 4: both suites green.
- [ ] Step 5: commit "The shared helpers move out of the report files".

### Task 2: Remove the five report tabs and the Google data connection (backend)

**Files:**
- Delete: `google_data.py`, `gizmo/analytics.py`, `gizmo/routes/analytics.py`, `gizmo/seo.py`, `gizmo/routes/seo.py`, `gizmo/routes/products.py`
- Modify: `gizmo/products.py` (keep `_all_products` only; drop `LOW_STOCK_THRESHOLD`, `PRODUCT_TREND_MONTHS`, `run_products_list`), `copilot.py` (imports, registrations, chat registry without seo/google tools), `gizmo/prompts.py` (drop `OVERVIEW_SYSTEM`, `KEYWORD_SYSTEM`, `_report_answer`; SYSTEM_PROMPT stops promising Google Analytics), `gizmo/chat.py` (drop the page-context machinery and `CHAT_CONTEXT_CAP`, the Google tool labels), `gizmo/routes/chat.py` (no SEO knowledge, no page context), `gizmo/impact.py` (no Google rows), `gizmo/scheduler.py` (drop paid audits + schedule config; keep `SCHEDULE_PATH` as the /data anchor), `gizmo/routes/scheduler.py` (drop /api/schedule), `gizmo/routes/oauth.py` + `gizmo/oauth.py` (drop the Google data pair), `gizmo/status.py`, `gizmo/routes/status.py`, `gizmo/backup.py`, `gizmo/routes/backup.py`, `gizmo/gate.py` (drop report prefixes, dead `/api/google/status`), `gizmo/team.py` (TAB_KEYS without overview/seo/keywords/products; `customers` stays), `gizmo/layouts.py`, `gizmo/ai.py` (kind words), `requirements.in` (drop `google-auth[requests]`, and `pyasn1` if only google-auth needed it) then `make lock`
- Test: `tests/test_dispatch.py` (delete tests of removed features, edit shared ones)

- [ ] Step 1: tests `t_a_saved_tab_list_naming_a_removed_tab_still_loads` (a user whose tabs are `["overview","labels","recon"]` gets `_user_tabs == ["labels"]`, no error) and `t_customer_history_still_answers_the_customers_permission` (gate allows /api/customer-history for tabs `["customers"]`, refuses `["labels"]`).
- [ ] Step 2: run; the first passes or fails per current `_user_tabs` (fix if it fails), the second passes and must keep passing.
- [ ] Step 3: delete and edit as listed; remove the report tests; `PY -c "import copilot, server"` imports clean.
- [ ] Step 4: dispatch suite green.
- [ ] Step 5: commit "The report tabs and the Google data connection go".

### Task 3: Remove Reconciliation, Reactor's Xero link and the finance mailbox (backend)

**Files:**
- Delete: `recon.py`, `xero.py`, `gizmo/reconciliation.py`, `gizmo/routes/reconciliation.py`
- Modify: `copilot.py` (no recon_engine.configure, no recon tools), `google_mail.py` (drop FINANCE and helpers only it used; SALES stays), `gizmo/routes/oauth.py` + `gizmo/oauth.py` (drop gmail-finance pair), `gizmo/scheduler.py` (drop `_recon_nightly` and the Xero keepalive), `gizmo/chat.py` (`_TOOL_TABS`: payouts/disputes to `connector`, recon tools gone), `gizmo/privacy.py` (shop/redact disconnects SALES only), `gizmo/status.py`, `gizmo/routes/status.py`, `gizmo/backup.py`, `gizmo/routes/backup.py`, `gizmo/gate.py`, `gizmo/team.py` (no `recon`; OPT_IN_TABS `("connector","forecast")`), `tokenvault.py` (docstring), `server.py` (payouts scope wording: "payout notes on Xero sync when it signs in as Reactor")
- Test: `tests/test_dispatch.py`

- [ ] Step 1: tests `t_payouts_in_chat_need_the_xero_sync_permission` (dispatch_for a uid with tabs `["chat"]` refuses `shopify_list_payouts`; with `["chat","connector"]` reaches the tool) and `t_backups_never_carry_the_old_token_files` (write google_oauth.json, gmail_finance_oauth.json, xero_oauth.json into a temp data dir, build the zip, none inside; same with the three `*_TOKEN_PATH` variables pointing elsewhere) and `t_restore_refuses_the_removed_stores` (a zip with volume/analysis_cache.json, schedule.json, recon.json, recon_cache.json, recon_docs.json restores none of them).
- [ ] Step 2: run; payouts and restore tests fail.
- [ ] Step 3: delete and edit as listed; backup exclusions read the env variables with their defaults (no module import).
- [ ] Step 4: dispatch suite green; `PY -c "import copilot, server"` clean.
- [ ] Step 5: commit "Reconciliation, Reactor's own Xero link and the accounts mailbox go".

### Task 4: The front end

**Files:**
- Delete: `static/src/js/overview.js`, `seo.js`, `keywords.js`, `customers.js`, `products.js`, `report-tools.js`, `reconciliation.js`, `static/src/css/customer-segments.css` and report-only rules in the other sheets
- Modify: `static/src/manifest.json`, `static/src/shell.html` (nav and view sections; alerts banner host at the top of the main column), `alerts.js` (banner drawn into the shell host on load and on every view change; renderOverview and its report parts go), `wire-up.js` (boot view `labels`, report cache code gone), `icons-and-formats.js` (logo opens `labels`; nav labels), `sidebar-groups.js`, `clock.js` (print button only for chat), `widget-grid.js`, `charts.js` (trend blocks for reports), `table-card.js` (channelsCard), `settings.js` (Google rows, schedule, Overview re-run, accounts mailbox), `team-and-sign-in.js` (tab lists; "Customer details" label; no Dashboards group), `liability.js` (no Reconciliation tab), `guide.js`, `design-page.js`, `structured-response.js` (Google glossary rows)
- Test: `tests/test_frontend.py`

- [ ] Step 1: frontend tests `t_the_app_opens_on_labels` (wire-up boot view and logo target are `labels`), `t_alerts_have_a_home_on_every_page` (shell has the banner host outside every view section; alerts.js fills it without renderOverview), `t_no_page_calls_a_removed_report` (no kept file names showOverviewView, showSeoView, showKeywordsView, showCustomersView, showProductsView, showReconView, loadOverview, pageChatPanel, refreshAllBtn, customersSeg, seoCache, keywordsCache, productList, paintRadar, renderScanResult).
- [ ] Step 2: run; they fail.
- [ ] Step 3: delete and edit; delete the removed tabs' frontend tests and edit shared ones.
- [ ] Step 4: frontend suite green; the CI dash grep is clean.
- [ ] Step 5: commit "The report and Reconciliation pages leave the app; it opens on Labels with alerts on every page".

### Task 5: References, docs, locks, browser suite, changelog

**Files:**
- Modify: `tools/sources.py`, `tools/env_reference.py`, `tools/route_reference.py` (lists), `Makefile` SAST_FILES and `.github/workflows/tests.yml` bandit line (drop google_data.py, xero.py, recon.py), `env.example`, `docs/ENVIRONMENT.md` (`make env-doc`), `docs/API.md` (`make api-doc`), `tests/browser/**` (seeds, screens, records for removed tabs), `data/changelog.json`
- [ ] Step 1: `PY tools/env_reference.py --check` and `PY tools/route_reference.py --check` fail (stale docs).
- [ ] Step 2: regenerate; edit the lists and seeds.
- [ ] Step 3: `make sweep sast`, both reference checks, `PY tests/browser/test_world.py`, `node --test 'tests/browser/unit/*.test.js'`, the Playwright suite (if Chromium is installed) all pass.
- [ ] Step 4: commit "References, docs and the browser suite follow the smaller app".

### Task 6: Verify in the running app and open the PR

- [ ] Run the app locally, sign in as master and as a default-tab account, open every kept page; no console errors; alerts banner visible; screenshots.
- [ ] Full gate: both suites, browser suite, sast, sweep, reference checks.
- [ ] One whole-branch review (the fifth and last agent).
- [ ] Push, open the PR with the after-deploy checklist from the spec; Cameron merges.
