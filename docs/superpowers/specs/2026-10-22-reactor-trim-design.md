# Trimming Reactor: the reports, Reconciliation, the Inbox and the CRM

**Draft, 22 Oct 2026, for Cameron's approval.** Line numbers below are from main
bfc25ed and will drift; search by name.

## Why

The Railway security incident of 21 Oct 2026 (environment variables possibly
read, every secret to be rolled, deploys paused) cost Cameron a day of key
rotation. He is staying on Railway but wants a smaller app holding fewer keys
and fewer outside services, so the next incident has less to roll and less
to break. In his words: remove the SEO, Keywords, Products, Customers and
Overview tabs and the Inbox, "this should remove some of the API keys we
use"; replace the CRM with Twenty (twentyhq/twenty), self-hosted; "dont want
any google keys so Reconciliation will need to go too"; "we need the people
and deals"; "Twenty must be live first". He wants it done quickly.

## Goals

1. Remove from Reactor: Overview, SEO, Keywords, Products, Customers,
   Reconciliation, the Inbox and the CRM, with everything that exists only
   for them (routes, scheduled jobs, settings rows, Guide sections, tests,
   environment variables, dependencies).
2. Afterwards Reactor holds **no Google keys, no Xero keys and no Pipedrive
   keys**. What remains: Anthropic, Shopify, Resend (alert emails), Files
   storage (R2), the token-vault key, the connector link.
3. The CRM's people, organisations, deals, leads, activities and notes move
   into a self-hosted Twenty on Railway, and Twenty is live with that data
   **before** the CRM leaves Reactor. No day without a CRM.
4. Every kept page works exactly as before: Chat, Labels (Production Manager
   and Dispatch), Size list, Forecast, Liability (and the chase desk), Loans,
   Xero sync, Files, Memory (Learn my store, Impact), Skills, Team, Settings,
   Guide.

## Non-goals

- No move off Railway.
- No change to the Shopify→Xero connector service. Its own "When a total
  disagrees" / "Tolerance" check is the connector's, not Reconciliation, and
  stays exactly as it is on the Xero sync page.
- No redesign of kept pages beyond the two forced moves below (the alerts
  banner and the opening page).
- No rebuilding of removed features elsewhere, except the CRM into Twenty.
- No Shopify app scope changes (the payouts scope still serves the
  connector's payout notes; read_customers still serves Chat and Labels).

## Anti-goals: a failure even if it "works"

- A kept page broken because a shared helper lived inside a removed file.
  The known ones are listed under each change; the builder hunts for more.
- Alerts (Shopify down, size-list gaps, Xero connector run alerts, lost user
  store, privacy requests) with nowhere to show.
- Any CRM record lost, or a gap with no CRM.
- People erased under GDPR coming back to life in Twenty.
- A refresh token leaking into a backup zip because a backup exclusion was
  deleted with its module while the token file still sits on the volume.
- Shopify's mandatory GDPR webhooks (customers/redact, shop/redact) raising.
- Non-master accounts silently losing something they had: the Labels
  order-history line, or Chat's order lookups.

## Constraints

- The repo's usual path: a branch in a worktree (other sessions use the main
  checkout), PR, CI green, Cameron merges, merge deploys, squash merge.
- Railway deploys are paused; nothing ships until they resume. Building
  continues regardless.
- The changelog test: a new note in data/changelog.json dated on or after
  the last app commit, in plain words (no UPPER_SNAKE names, no developer
  words).
- The meta-tests (for example "no test patches a name nobody reads"), the
  route and environment references (tools/route_reference.py,
  tools/env_reference.py, docs/ENVIRONMENT.md, docs/API.md), the source lists
  (tools/sources.py APP_MODULES, Makefile SAST_FILES, the bandit line in
  .github/workflows/tests.yml) and the browser suite's seeds and records
  must all agree with the smaller app.
- The engineering-audit sessions (stages 4 to 6) have been moving code out of
  copilot.py into gizmo/ modules. Nothing of theirs is open as of 22 Oct, but
  check before starting and again before each PR; a running audit piece that
  touches a removed file must land first or rebase after.

## The shape: two changes

### Change 1: the reports and Reconciliation (build now)

Change 1 ships on its own, without waiting for Twenty, because it takes
nothing away from the CRM or the Inbox: every check they make keeps
passing for exactly the accounts it passes for today (see "Customer
details" below).

**Remove**

- The five report tabs: gizmo/analytics.py (the overview, customers, reorder
  radar, sector tags, analysis cache and "what changed" digest),
  gizmo/routes/analytics.py, the SEO and keyword parts of gizmo/seo.py,
  gizmo/routes/seo.py, gizmo/routes/products.py and the list half of
  gizmo/products.py, prompts OVERVIEW_SYSTEM, KEYWORD_SYSTEM and
  _report_answer, the scheduled paid audits (scheduler.py
  _run_scheduled_audits, the schedule config, /api/schedule and the Settings
  auto-refresh), the page chat ("ask about this report": report-tools.js,
  chat.py _page_context_to_system and CHAT_CONTEXT_CAP), and the front end
  (overview.js, seo.js, keywords.js, products.js except its formatters,
  customers.js, report-tools.js, the report-only parts of alerts.js,
  charts.js and table-card.js, their CSS and shell.html sections).
- Google data: google_data.py, /oauth/google/start and /callback, the
  Settings rows for Analytics, Search Console and Google Ads (CPC), Chat's
  get_search_console_data / get_ga4_data tools, Impact's sessions and
  clicks rows (impact.py), the google-auth dependency and whatever only it
  pulled into the lock (requests, pyasn1, pyasn1-modules; check boto3 does
  not need requests).
- Reconciliation: recon.py, gizmo/reconciliation.py,
  gizmo/routes/reconciliation.py (which also holds Reactor's own Xero
  connect walk), reconciliation.js, the nightly sweep (scheduler.py
  _recon_nightly), Chat's recon_* tools, its tab on Liability's strip
  (liability.js tabStrip), ANTHROPIC_MODEL_RECON and every RECON_* setting.
- Reactor's own Xero connection: xero.py and the Xero keepalive. Only
  Reconciliation used it; Xero sync talks to the connector, which has its
  own Xero connection.
- The finance (accounts) mailbox: google_mail.py's FINANCE account and the
  helpers only it uses, /oauth/gmail-finance/start and /callback,
  gizmo/oauth.py _gmail_fin_redirect_uri.
- Chat's storefront SEO tools (seo_fetch_page, seo_check_robots_sitemap)
  and its SEO knowledge (seo._is_seo, SEO_KNOWLEDGE in routes/chat.py).
  Cameron was told and did not object.

**Move or keep before deleting** (each of these breaks a kept page if
missed)

- products.js lines 1-57 (moneyFmt, money, fmtMoney, pct1, moneyShort) to a
  kept file such as icons-and-formats.js: Forecast, Liability, Loans, Xero
  sync, charts and alerts call them.
- gizmo/products.py _all_products stays (Loans' unit picker,
  gizmo/loans.py:92).
- analytics._CURRENCY_SIGNS moves to a kept module (gizmo/liability.py:109
  reads it).
- seo.py's guarded fetch (_http_get, _resolve_domains, _domains_cache,
  _host_is_public, _ip_is_public; about 110 lines) moves into knowledge.py or
  a small storefront module: Learn my store uses it.
- The alerts banner: alertsBanner, loadAlerts, alertOp and privacyNotice
  move out of renderOverview to the top of every page in the shell.
- scheduler.SCHEDULE_PATH survives as the /data anchor (backup.py, status.py,
  routes/status.py, privacy.py, routes/backup.py use it), or becomes a
  DATA_DIR in gizmo/config.py with every reader switched.
- The connect secret: google_data.CONNECT_SECRET moves to gizmo/config.py
  (same GOOGLE_CONNECT_SECRET variable for now). After change 1 only the
  Inbox's /oauth/gmail/start reads it; it goes in change 2.
- google_mail.py keeps its SALES account for the Inbox until change 2.
- trendChart and the table-card helpers stay (Forecast, Liability, Loans
  and Chat use them).

**Rewire**

- The opening page and the logo open **Labels** instead of Overview
  (wire-up.js:52, icons-and-formats.js:298).
- **Customer details.** The `customers` key is the lock on customer data,
  not just a tab, and five kept places check it: /api/customer-history
  (gate.py:226-228, the Production Manager's order-history line, with `crm`
  as the alternative), Chat's order and customer tools (chat.py _TOOL_TABS),
  the CRM's Shopify customer search (routes/crm.py:516), the order facts in
  the Inbox's AI reply drafts (routes/mail.py:618) and the Inbox's order
  panel (routes/mail.py:1419). The key stays in TAB_KEYS and DEFAULT_TABS as
  a permission with no tab, shown on the Team page as "Customer details",
  and every one of those checks is left as it is. Nobody gains or loses
  access. (Gating them to `labels` instead would widen customer data to
  label-only accounts; dropping the key would take it from everyone but the
  master.)
- Chat's payouts and disputes tools move from `recon` to `connector`, the
  other opt-in finance tab.
- Team: TAB_KEYS, OPT_IN_TABS, the tab lists in team-and-sign-in.js, the
  empty "Dashboards" group and BETA_TABS lose the removed keys (overview,
  seo, keywords, products, recon; not customers). Saved user tab lists that
  still name a removed tab must load cleanly (unknown keys ignored, not an
  error).
- shop/redact in privacy.py stops disconnecting the FINANCE mailbox (it
  still disconnects SALES until change 2).
- The status page and token-vault list drop the Google data, finance Gmail
  and Xero rows.
- Backups: keep excluding the Google data, finance Gmail and Xero token
  files without importing their modules: backup.py and routes/backup.py
  read the same variables with the same defaults
  (GOOGLE_OAUTH_TOKEN_PATH or google_oauth.json, GMAIL_FINANCE_TOKEN_PATH or
  gmail_finance_oauth.json, XERO_TOKEN_PATH or xero_oauth.json), so a
  leftover token can never reach a zip even if a path was overridden.
- Restore (/api/restore) refuses the removed stores by filename, as it
  already refuses token files: analysis_cache.json, schedule.json,
  recon.json, recon_cache.json, recon_docs.json. Restoring an old backup
  must not bring them back with nothing left to read or scrub them. Old
  weekly snapshots are left to age out (four are kept).
- Guide, design page, sidebar titles, the print button's view list,
  widget-grid layouts (layouts.py LAYOUT_VIEWS, widget-grid.js APP_VIEWS)
  and the server.py scope description lose the removed tabs.
- gate.py: drop the removed tabs' route prefixes and the dead
  /api/google/status entry in _OPEN_API.

**After it deploys** (Cameron, with exact steps from the builder; nothing
here is done by the builder)

- Delete from the volume: analysis_cache.json (it can hold customer details
  privacy redaction never scrubbed), schedule.json, recon.json,
  recon_cache.json, recon_docs.json, and the three token files (the paths
  their variables name on Railway, or the defaults google_oauth.json,
  gmail_finance_oauth.json, xero_oauth.json). The builder reads the actual
  values from Railway's variable list with Cameron before writing the steps.
- Remove the freed Railway variables: GOOGLE_SERVICE_ACCOUNT_JSON,
  GA4_PROPERTY_ID, GSC_SITE_URL, GOOGLE_OAUTH_TOKEN_PATH, XERO_CLIENT_ID,
  XERO_CLIENT_SECRET, XERO_* overrides, GMAIL_FINANCE_TOKEN_PATH,
  ANTHROPIC_MODEL_RECON, every RECON_*, and the report-only settings
  (ANALYSIS_CACHE_*, TREND_MONTHS, PRODUCT_TREND_MONTHS, SEO_SAMPLE_PAGES,
  EXTERNAL_FETCH_MAX, CHAT_CONTEXT_CAP).
- Revoke the finance mailbox's and Search Console/Analytics' Google grants;
  delete the Google service account. The Google OAuth client stays until
  change 2.
- Disconnect Reactor in Xero. If the connector uses the same Xero app, keep
  the app; otherwise delete it.

### Change 2: Twenty, then the Inbox and the CRM

Three steps, in this order. The Inbox and CRM leave together because each
imports the other (mail.py files enquiries into the CRM; the CRM reads mail
threads and borrows mail._mail_guard).

**A. Twenty on Railway.** Server, worker, Postgres and Redis; at least 2 GB
of memory; ENCRYPTION_KEY kept safe off Railway (losing it loses Twenty's
stored secrets); PG_DATABASE_PASSWORD without special characters;
SERVER_URL on HTTPS. File storage on S3-compatible storage, not a Railway
volume: Railway volumes cannot be shared between services, and the server
and worker both need the files. A new R2 bucket of its own, with a token
limited to that bucket, keeps it apart from Reactor's Files. Pin the Twenty
image to a version, never `latest`; community Railway templates exist but
are unofficial, so check one against Twenty's own self-hosting guide before
using it. Cameron does the dashboard work; the builder writes the steps and
verifies each against Twenty's and Railway's current docs before handing
them over. Each team member gets their own Twenty login.

**B. Copy the CRM into Twenty.** A script (in tools/) that reads crm.json
from a Reactor backup zip (Settings already offers the download; the zip
includes crm.json) and writes to Twenty through its API with a key Cameron
creates. Source of truth is crm.json, never Pipedrive: crm.json holds
everything typed in Reactor since the Pipedrive import, and the tombstones
that keep erased people out.

| Reactor | Twenty |
|---|---|
| orgs | Companies (name, address, website as domain, label, custom fields) |
| persons | People (name split first/last, first email and phone primary, the rest additional, job title, company, label, custom fields, Shopify customer id as a custom field) |
| deals (not deleted) | Opportunities (title, amount and currency, stage, point of contact, company, expected close; status, lost reason, probability, label, source, archived, owner, won/lost/created dates as custom fields where Twenty has none) |
| stages | Opportunity stage options (Reactor's custom stages added) |
| leads | Opportunities in an early "Lead" stage (Cameron did not object) |
| notes on deals, people, organisations, leads | Notes attached to the matching record; a deal's changelog flattened into one note |
| activities | Tasks (subject, note, type, due date and time, done, assignee) linked to their deal, person and organisation |

Email history comes too. For each deal, lead and person with linked
threads in mailbox.json (also in the backup zip), the script adds one
Twenty note listing each thread's subject, date and a link to it in Gmail,
plus the Inbox's internal notes on that thread. The emails themselves stay
in Gmail.

Every record carries its Reactor id in a custom field. A dry run prints
counts and anything it cannot map before anything is written. Erased
people are already gone from crm.json (tombstoned), so the script simply
never reads tombstones or erased_marks; it does not try to match live
records against the marks. Owners map from Reactor accounts to Twenty
members; Pipedrive-imported deals have no owner and stay unowned.

**Reruns only add.** After the first full run, the team works in Twenty
and Twenty's copy wins: a rerun creates records whose Reactor id is not in
Twenty yet and never changes a record that is. It lists Reactor-side
changes to records already copied (for example a Shopify link the nightly
sweep added) instead of applying them. This matters because Reactor keeps
writing to crm.json until change 2 deploys, which may be days while deploys
are paused: the Inbox files website enquiries as new deals, the orders
webhook links orders, the nightly sweep links customers.

Cut-over:
1. No privacy request may be held or pending (Settings shows none). The
   script reads privacy_log.json from the zip and refuses to run while any
   are, so nobody awaiting erasure is copied into Twenty.
2. The team stops editing the CRM; Cameron downloads a fresh backup; the
   first full run; counts checked against the dry run.
3. Until change 2 deploys, Cameron reruns from a fresh backup whenever he
   likes (daily is enough) to pick up new enquiries.
4. Change 2 deploys. crm.json and mailbox.json are still on the volume
   (removing code never deletes data), so one last rerun from a backup
   taken after the deploy catches everything. Then Cameron keeps that
   backup offline and the files are deleted.

**C. Remove the Inbox and the CRM** (one PR, after B is verified):
gizmo/mail.py, gizmo/routes/mail.py, mailmime.py, static/composer.js,
inbox.js, inbox-filters-and-sending.js, inbox.css, gizmo/crm.py,
gizmo/routes/crm.py, pipedrive.py, crm.js, crm-and-updates.css (the CRM
half), google_mail.py entirely, the mail loop and the nightly CRM Shopify
link sweep in the scheduler, the orders-webhook CRM hook, the Settings
shared-mailbox row and sign-off editor, the Team page's Inbox fieldset and
CRM column, and the CRM half of privacy.py's erasure machinery (about 650
lines).

Move first: RELEASE_INLINE_MAX to gizmo/production.py (Labels print runs);
_crm_bg_tasks to copilot's own set (_spawn_bg runs label release and
privacy alert emails); _crm_now to the clock module (the stock-bridge retry
queue); crmModal, crmField, crmText, crmTypeahead and friends to a kept
file (Dispatch's print modal, Loans and the Xero sync page use them); the
crm-badge, crm-group, crm-input and crm-ta CSS the kept pages use; keep
privacy._redact_archive_reap in the Files daily block when the mail
attachment sweep leaves it.

Privacy after change 2: Reactor no longer holds CRM or mailbox data, so a
Shopify customers/redact request cannot reach Twenty. The request log, the
alert email and the Settings list of requests stay (requests still arrive,
and dispatch records are still erased); the CRM scope preview and
likely-duplicate matching go with the CRM. The alert email gains a line
telling Cameron to erase the person in Twenty by hand. Restore refuses
crm.json and mailbox.json by filename from then on.

Loans: the borrower field is already free text that merely suggests CRM
contacts. It stays free text and suggests borrowers from earlier loans
instead. Old loans keep their stored CRM ids as inert data; nothing links
to them.

Freed then: GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET,
GOOGLE_CONNECT_SECRET, GMAIL_*, MAIL_*, MAILBOX_PATH, PIPEDRIVE_*, CRM_*.
After deploy, Cameron deletes mailbox.json, gmail_oauth.json and crm.json
(after keeping a final backup offline), the R2 objects under `mail/`,
revokes the sales mailbox's Google grant, deletes the Google OAuth client,
and revokes the Pipedrive token.

## Website enquiries after change 2

Decided by Cameron: **the team enters enquiries into Twenty by hand** from
the sales mailbox in Gmail. Twenty gets no mailbox connection and no
Google key. The automatic filing stops when change 2 deploys; until then
the add-only reruns carry new enquiries across. The Guide's CRM rows go;
the changelog note for change 2 says enquiries are now added in Twenty.

If Railway's pause also blocks creating new services, step A waits for it;
check status.railway.com when starting.

## Left to the builder

- Exact file splits, where moved helpers land, test rewrites, the order of
  commits.
- Whether SCHEDULE_PATH stays or becomes DATA_DIR.
- The Twenty API calls (REST or GraphQL), checked against the Twenty version
  actually deployed; custom field names.
- Copy for the changelog note and the Guide edits.

## Calls made without Cameron (he can overturn any)

- Opening page and logo go to Labels.
- The alerts banner sits at the top of every page.
- "Customer details" stays as a permission with no tab, so nobody gains or
  loses access to customer data; Chat's payouts and disputes move to the
  Xero sync permission.
- Chat loses its storefront SEO tools.
- Backups keep excluding the old token files forever; restore refuses the
  removed stores.
- Change 1 ships without waiting for Twenty.
- Leads become early-stage opportunities in Twenty.
- Email history goes into Twenty as notes with Gmail links and the Inbox's
  internal notes.
- Script reruns only add; Twenty's copy wins once the team works there.
- Loans' borrower field suggests earlier borrowers instead of CRM contacts.
- Twenty's files in a bucket of their own on R2, not a Railway volume.
- The Inter font keeps loading from Google Fonts (no key, no account).
