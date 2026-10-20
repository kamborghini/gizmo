# Environment variables

Generated from the code by `tools/env_reference.py`; do not edit by hand.
`make env-doc` rewrites it, and CI fails when it is stale.

222 variables are read. Every one has a default unless marked **(required)**; the defaults below are the code's own expressions, so a path like `/data/...` means the Railway volume. Set a variable in Railway, never in the code, and never paste a secret into chat or a document. `[shop domain]` stands for the shop's own website domain, which those defaults carry.

## server.py

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `GZIP_LEVEL` | `"6"` | server |  |
| `GZIP_MIN_BYTES` | `"1024"` | server |  |
| `MCP_BEARER_TOKEN` | `""` | server |  |
| `MCP_TRANSPORT` | `"streamable-http"` | server |  |
| `PORT` | `"8000"` | server |  |
| `SHOPIFY_ACCESS_TOKEN` | `""` | server | Static token (shpat_...) |
| `SHOPIFY_API_VERSION` | `"2026-10"` | server |  |
| `SHOPIFY_MAX_CONCURRENCY` | `"4"` | server |  |
| `TOKEN_REFRESH_BUFFER` | `"1800"` | server |  |
| `WEBHOOK_ALLOWED_HOSTS` | `""` | server | comma-separated host names or addresses (a staging copy of Reactor) whose webhooks the hourly repair keeps |

## copilot.py - Chase desk: the weekly session of asking credit customers fo

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `CHASE_LOG_PATH` | `"/data/chase_log.json"` | copilot |  |

## copilot.py - Configuration

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `ALERTS_MAX` | `"60"` | copilot |  |
| `ALERTS_PATH` | `"/data/alerts.json"` | copilot | change alerts from scheduled runs |
| `ANALYSIS_CACHE_MAX_BYTES` | `"800000"` | copilot | per-entry size guard |
| `ANALYSIS_CACHE_PATH` | `"/data/analysis_cache.json"` | copilot | last result per AI tab |
| `ANTHROPIC_EFFORT` | `"high"` | copilot |  |
| `ANTHROPIC_EFFORT_DEEP` | `"max"` | copilot |  |
| `ANTHROPIC_THINKING` | `"adaptive"` | copilot |  |
| `APP_BASE_URL` | `""` | copilot |  |
| `CHANGELOG_PATH` | `os.path.join(os.path.dirname(__file__), "data", "changelo...` | copilot |  |
| `CHAT_CONTEXT_CAP` | `"12000"` | copilot | max chars of page-report context injected into chat |
| `COPILOT_MAX_TOOL_ROUNDS` | `"12"` | copilot |  |
| `COPILOT_TOOL_RESULT_CAP` | `"50000"` | copilot |  |
| `FEEDBACK_PATH` | `"/data/feedback.json"` | copilot | feature requests from the desk |
| `FORECAST_INGEST_TOKEN` | `""` | copilot | shared secret the nightly forecasting service presents to /hooks/forecast/*; empty switches the hooks off |
| `FORECAST_PATH` | `"/data/forecast.json"` | copilot | the nightly forecasting service's latest run, and the cash flow workbook an admin uploaded (base64), in one store |
| `IMPACT_MAX` | `"100"` | copilot |  |
| `IMPACT_PATH` | `"/data/impact.json"` | copilot | tracked-action impact log |
| `KNOWLEDGE_CAP` | `"8000"` | copilot | max stored knowledge chars |
| `KNOWLEDGE_PATH` | `"/data/store_knowledge.json"` | copilot |  |
| `LAYOUTS_PATH` | `"/data/layouts.json"` | copilot | each person's arrangement of the cards on a screen |
| `LEARN_MAX_PAGES` | `"12"` | copilot | pages crawled when learning |
| `LEARN_PAGE_CHARS` | `"3000"` | copilot | text kept per page |
| `LOW_STOCK_THRESHOLD` | `"5"` | copilot |  |
| `MAX_CHAT_CHARS` | `"100000"` | copilot | total chars in a chat request |
| `MAX_MESSAGES` | `"100"` | copilot | chat history length |
| `MEMORY_INJECT` | `"40"` | copilot | max of each kind injected into prompts |
| `MEMORY_MAX` | `"500"` | copilot | max stored memories |
| `MEMORY_PATH` | `"/data/store_memory.json"` | copilot |  |
| `PRODUCT_TREND_MONTHS` | `"12"` | copilot |  |
| `PROFILE_FIELD_CAP` | `"6000"` | copilot |  |
| `PROFILE_PATH` | `"/data/store_profile.json"` | copilot |  |
| `RECON_CACHE_PATH` | `"/data/recon_cache.json"` | copilot |  |
| `RECON_DOCS_PATH` | `"/data/recon_docs.json"` | copilot |  |
| `RECON_PATH` | `"/data/recon.json"` | copilot |  |
| `SCHEDULE_CHECK_SECS` | `"900"` | copilot | how often the scheduler wakes to check |
| `SCHEDULE_PATH` | `"/data/schedule.json"` | copilot | auto-refresh config (off by default) |
| `SHOPIFY_API_KEY` | `None` | copilot |  |
| `SHOPIFY_API_SECRET` | `None` | copilot |  |
| `SHOPIFY_CLIENT_ID` | `""` | copilot, server |  |
| `SHOPIFY_CLIENT_SECRET` | `""` | copilot, server |  |
| `SHOPIFY_STORE` | `""` | copilot, server | used to pin session tokens to this shop |
| `SKILLS_INJECT_CAP` | `"24000"` | copilot | max total skill chars injected |
| `SKILLS_MAX` | `"200"` | copilot | max stored skills |
| `SKILLS_PATH` | `"/data/store_skills.json"` | copilot | merchant-authored skills |
| `SKILL_BODY_CAP` | `"40000"` | copilot | chars per skill body |
| `SKILL_TITLE_CAP` | `"120"` | copilot | chars per skill title |
| `SKILL_UPLOAD_CAP` | `"200000"` | copilot |  |
| `STORE_CONTEXT_CAP` | `"4000"` | copilot |  |
| `TREND_MONTHS` | `"24"` | copilot |  |

## copilot.py - Impact tracking — "close the loop": snapshot headline metric

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `BACKUP_FILE_MAX` | `str(60 * 1024 * 1024)` | copilot |  |
| `BACKUP_SNAPSHOT_DIR` | `"/data/snapshots"` | copilot |  |
| `BACKUP_STATE_PATH` | `"/data/backup_state.json"` | copilot |  |

## copilot.py - Keyword scraper for arbitrary external URLs (SSRF-guarded) +

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `EXTERNAL_FETCH_MAX` | `str(600 * 1024)` | copilot | bytes of text kept |

## copilot.py - Loan units: the projectors that go out to customers, and whe

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `RAILWAY_ENVIRONMENT` | `None` | copilot | set by Railway; the volume check runs only there |
| `RAILWAY_PROJECT_ID` | `None` | copilot | set by Railway; the volume check runs only there |
| `SETUP_CODE` | `""` | copilot | set only while first-run setup is needed, then remove; unset locks setup |

## copilot.py - Page rendering

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `CONNECTOR_TOKEN` | `None` | copilot |  |
| `CONNECTOR_URL` | `None` | copilot |  |

## copilot.py - Production labels: orders carrying the production tag, shape

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `LIABILITY_DEFAULT_TERMS` | `"30"` | copilot |  |
| `LIABILITY_DUE_SOON_DAYS` | `"7"` | copilot |  |
| `LIABILITY_TAGS` | `"Purchase order unpaid, Bank transfer unpaid, Procurement...` | copilot |  |

## copilot.py - Reconciliation stores + the read-only tools the chat is give

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `ANTHROPIC_MODEL_RECON` | `None` | copilot |  |

## copilot.py - SEO — knowledge layer + live technical audit

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `SEO_SAMPLE_PAGES` | `"5"` | copilot |  |

## copilot.py - Scheduled refresh + change alerts. Off by default (automatic

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `ALERT_EMAIL_FROM` | `"Reactor <onboarding@resend.dev>"` | copilot |  |
| `ALERT_EMAIL_TO` | `""` | copilot |  |
| `RESEND_API_KEY` | `""` | copilot |  |
| `WATCH_PATH` | `"/data/watch.json"` | copilot |  |

## copilot.py - Stock bridge: the glass a Mark made consumes flows into the 

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `USAGE_SHEETS_PATH` | `"/data/usage_sheets.json"` | copilot |  |
| `ZETA_DRAIN_MAX` | `"40"` | copilot | retries per tick |
| `ZETA_DRAIN_SECONDS` | `"45"` | copilot | and its deadline |
| `ZETA_MAX_TRIES` | `"20"` | copilot | then park for a human |
| `ZETA_SYNC_PATH` | `"/data/zeta_sync.json"` | copilot |  |
| `ZETA_SYNC_TOKEN` | `""` | copilot |  |
| `ZETA_URL` | `""` | copilot |  |

## copilot.py - What's new: the release notes that ship WITH the release, an

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `RAILWAY_GIT_COMMIT_SHA` | `None` | copilot, server |  |

## gizmo/activity.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `ACTIVITY_MAX` | `"8000"` | gizmo.activity |  |
| `ACTIVITY_PATH` | `"/data/activity.json"` | gizmo.activity |  |

## gizmo/ai.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | `""` | gizmo.ai |  |
| `ANTHROPIC_MODEL` | `None` | gizmo.ai |  |
| `ANTHROPIC_MODEL_DEEP` | `"claude-opus-5-5"` | gizmo.ai |  |
| `ANTHROPIC_MODEL_FALLBACK` | `"claude-opus-4-8"` | gizmo.ai |  |
| `ANTHROPIC_MODEL_FAST` | `None` | gizmo.ai |  |
| `COPILOT_MAX_TOKENS` | `"16000"` | gizmo.ai | headroom for rich output at high effort (non-streaming-safe) |
| `DAILY_COST_CAP` | `"25"` | gizmo.ai | hard $/day AI ceiling (0 disables) |
| `USAGE_MAX` | `"5000"` | gizmo.ai | max usage events retained |
| `USAGE_PATH` | `"/data/usage.json"` | gizmo.ai | AI token-usage + cost log (measurement) |

## gizmo/crm.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `CRM_ACTIVITIES_MAX` | `"200000"` | gizmo.crm |  |
| `CRM_DEALS_MAX` | `"60000"` | gizmo.crm |  |
| `CRM_ENQUIRY_DAILY_CAP` | `"50"` | gizmo.crm |  |
| `CRM_PATH` | `"/data/crm.json"` | gizmo.crm |  |

## gizmo/dispatch.py - Custom address dispatch

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `WO_RETRY_WAIT_SECS` | `"15"` | gizmo.dispatch |  |

## gizmo/dispatch.py - Pasted addresses

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `COST_CACHE_PATH` | `"/data/cost_cache.json"` | gizmo.dispatch |  |
| `CUSTOMS_GOBO_DESCRIPTION` | `"Glass Optical Filter"` | gizmo.dispatch |  |
| `CUSTOMS_MEMORY_PATH` | `"/data/customs_memory.json"` | gizmo.dispatch |  |
| `MARGIN_BACKFILL_MAX` | `"60"` | gizmo.dispatch | older orders fetched one by one |

## gizmo/dispatch.py - Shipping / dispatch (World Options SOAP web service) — setti

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `BOOKING_INTENT_PATH` | `os.path.join(os.path.dirname(DISPATCH_STATE_PATH) or ".",...` | gizmo.dispatch |  |
| `COLLECTIONS_PATH` | `"/data/collections.json"` | gizmo.dispatch |  |
| `DISPATCHED_TAG` | `"Complete"` | gizmo.dispatch |  |
| `DISPATCH_ARCHIVE_PATH` | `os.path.join(os.path.dirname(DISPATCH_STATE_PATH) or ".",...` | gizmo.dispatch |  |
| `DISPATCH_LABELS_DIR` | `os.path.join(os.path.dirname(DISPATCH_STATE_PATH) or ".",...` | gizmo.dispatch |  |
| `DISPATCH_LABELS_MAX` | `"400"` | gizmo.dispatch |  |
| `DISPATCH_STATE_MAX` | `"2000"` | gizmo.dispatch |  |
| `DISPATCH_STATE_PATH` | `"/data/dispatch_state.json"` | gizmo.dispatch |  |
| `SHIPPING_PATH` | `"/data/shipping.json"` | gizmo.dispatch |  |
| `WO_FAILURES_PATH` | `"/data/wo_failures.json"` | gizmo.dispatch |  |
| `WO_SECRET_PATH` | `"/data/wo_secret.json"` | gizmo.dispatch |  |

## gizmo/errors.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `ERRORS_PATH` | `"/data/app_errors.json"` | gizmo.errors |  |

## gizmo/files.py - Files: the office file server, without the office

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `APP_URL` | `None` | gizmo.files, server |  |
| `FILES_PATH` | `"/data/files.json"` | gizmo.files |  |
| `FILES_QUOTA_GB` | `"50"` | gizmo.files |  |
| `FILES_REAP_MAX` | `"4000"` | gizmo.files | keys per reaper tick |
| `FILES_REAP_SECONDS` | `"20"` | gizmo.files | and its deadline |
| `R2_ACCESS_KEY_ID` | `""` | gizmo.files |  |
| `R2_ACCOUNT_ID` | `""` | gizmo.files |  |
| `R2_BUCKET` | `"gizmo-files"` | gizmo.files |  |
| `R2_ENDPOINT` | `None` | gizmo.files |  |
| `R2_SECRET_ACCESS_KEY` | `""` | gizmo.files |  |
| `RAILWAY_PUBLIC_DOMAIN` | `None` | gizmo.files, server |  |

## gizmo/gate.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `MAX_BODY_BYTES` | `str(256 * 1024)` | gizmo.gate | 256 KB |
| `RATE_LIMIT_GLOBAL` | `"150"` | gizmo.gate | AI requests/window (cost ceiling) |
| `RATE_LIMIT_PER_CLIENT` | `"120"` | gizmo.gate | requests/window/client |
| `RATE_LIMIT_WINDOW` | `"60"` | gizmo.gate | seconds |

## gizmo/loans.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `LOANS_PATH` | `"/data/loans.json"` | gizmo.loans |  |

## gizmo/mail.py - Attachments on the way OUT. They live in the bucket under ma

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `ENQUIRY_SENDERS` | `"shopifyemail.com,shopify.com,[shop domain]"` | gizmo.mail |  |
| `MAIL_BOARD_DONE_DAYS` | `"90"` | gizmo.mail |  |
| `MAIL_BOARD_MAX` | `"1500"` | gizmo.mail |  |

## gizmo/mail.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `MAILBOX_PATH` | `"/data/mailbox.json"` | gizmo.mail |  |
| `MAIL_ALERT_AFTER_TICKS` | `"30"` | gizmo.mail |  |
| `MAIL_DONE_KEEP_DAYS` | `"730"` | gizmo.mail |  |
| `MAIL_LOOP_SECS` | `"60"` | gizmo.mail |  |
| `MAIL_THREADS_CAP` | `"6000"` | gizmo.mail |  |
| `MAIL_TRACK_DAYS` | `"730"` | gizmo.mail |  |
| `RELEASE_INLINE_MAX` | `"12"` | gizmo.mail |  |

## gizmo/orderbook.py - Order sweep snapshot

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `ORDER_CACHE_SECS` | `"180"` | gizmo.orderbook |  |

## gizmo/orderbook.py - Webhooks: how the desk stays live

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `MADE_TAG` | `"PC"` | gizmo.orderbook |  |
| `PO_UNPAID_TAG` | `"purchase order unpaid"` | gizmo.orderbook |  |
| `PROPOSAL_HOST` | `"quote.[shop domain]"` | gizmo.orderbook |  |
| `SHOP_CACHE_SECS` | `"900"` | gizmo.orderbook |  |
| `UNPROCESSED_TAG` | `"Unprocessed"` | gizmo.orderbook |  |

## gizmo/orderbook.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `ORDER_PAGE_CAP` | `"30"` | gizmo.orderbook |  |

## gizmo/privacy.py - WebDAV: the Files store as a native Finder drive. macOS moun

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `REDACT_ARCHIVE_DAYS` | `"30"` | gizmo.privacy |  |

## gizmo/privacy.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `PRIVACY_LOG_PATH` | `"/data/privacy_log.json"` | gizmo.privacy |  |

## gizmo/production.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `OPTION_CACHE_SECS` | `"21600"` | gizmo.production | 6 hours |
| `PRODUCTION_ARCHIVE_PATH` | `os.path.join(os.path.dirname(PRODUCTION_STATE_PATH) or "....` | gizmo.production |  |
| `PRODUCTION_LABEL_DAYS` | `"180"` | gizmo.production | how far back to look for tagged orders |
| `PRODUCTION_LABEL_TAG` | `"IP"` | gizmo.production | order tag that means "in production" |
| `PRODUCTION_STATE_MAX` | `"1000"` | gizmo.production |  |
| `PRODUCTION_STATE_PATH` | `"/data/production_state.json"` | gizmo.production |  |

## gizmo/routes/files.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `DAV_TRACE` | `None` | gizmo.routes.files |  |

## gizmo/size_list.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `GOBO_ALIASES_LIVE` | `"/data/gobo-aliases.csv"` | gizmo.size_list |  |
| `GOBO_ALIASES_PATH` | `os.path.join(_REPO, "data", "gobo-aliases.csv")` | gizmo.size_list |  |
| `GOBO_OVERRIDES_LIVE` | `"/data/gobo-overrides.csv"` | gizmo.size_list |  |
| `GOBO_OVERRIDES_PATH` | `os.path.join(_REPO, "data", "gobo-overrides.csv")` | gizmo.size_list |  |
| `GOBO_SIZES_LIVE` | `"/data/gobo-sizes.csv"` | gizmo.size_list |  |
| `GOBO_SIZES_PATH` | `os.path.join(_REPO, "data", "gobo-sizes.csv")` | gizmo.size_list |  |

## gizmo/team.py - Team: the app's own accounts. Shopify has no authority here

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `MASTER_RESET` | `None` | gizmo.team |  |
| `MASTER_RESET_MINUTES` | `"30"` | gizmo.team |  |
| `SESSIONS_PATH` | `"/data/sessions.json"` | gizmo.team |  |
| `SESSIONS_PER_USER` | `"12"` | gizmo.team |  |
| `SESSION_HOURS` | `"24"` | gizmo.team |  |
| `SESSION_MAX_DAYS` | `"30"` | gizmo.team |  |
| `USERS_PATH` | `"/data/users.json"` | gizmo.team |  |

## gizmo/work.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `WORK_ARCHIVE_PATH` | `os.path.join(os.path.dirname(WORK_PATH) or ".", "worklog_...` | gizmo.work |  |
| `WORK_KEEP` | `"2000"` | gizmo.work |  |
| `WORK_MIN_SECS` | `"60"` | gizmo.work |  |
| `WORK_PATH` | `"/data/worklog.json"` | gizmo.work |  |

## eori.py

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `EORI_CACHE_PATH` | `"/data/eori_cache.json"` | eori |  |

## google_data.py

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `GA4_PROPERTY_ID` | `""` | google_data |  |
| `GOOGLE_CONNECT_SECRET` | `""` | google_data |  |
| `GOOGLE_OAUTH_CLIENT_ID` | `""` | google_data, google_mail |  |
| `GOOGLE_OAUTH_CLIENT_SECRET` | `""` | google_data, google_mail |  |
| `GOOGLE_OAUTH_TOKEN_PATH` | `"/data/google_oauth.json"` | google_data |  |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | `""` | google_data |  |
| `GSC_SITE_URL` | `""` | google_data |  |

## google_mail.py

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `GMAIL_API_BASE` | `"https://gmail.googleapis.com"` | google_mail |  |
| `GMAIL_FINANCE_TOKEN_PATH` | `"/data/gmail_finance_oauth.json"` | google_mail |  |
| `GMAIL_TOKEN_PATH` | `"/data/gmail_oauth.json"` | google_mail |  |
| `GMAIL_TOKEN_URL` | `"https://oauth2.googleapis.com/token"` | google_mail |  |

## logdrain.py

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `LOG_DRAIN_TOKEN` | `""` | logdrain |  |
| `LOG_DRAIN_URL` | `""` | logdrain |  |

## pipedrive.py

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `PIPEDRIVE_API_BASE` | `""` | pipedrive |  |
| `PIPEDRIVE_API_TOKEN` | `""` | pipedrive |  |
| `PIPEDRIVE_DOMAIN` | `""` | pipedrive |  |

## recon.py

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `RECON_CACHE_KEEP_DAYS` | `str(WINDOW_DAYS + 60)` | recon |  |
| `RECON_CLOSED_KEEP_DAYS` | `"365"` | recon |  |
| `RECON_DOCS_KEEP_DAYS` | `str(WINDOW_DAYS + 60)` | recon |  |
| `RECON_DOCS_PER_SWEEP` | `"8"` | recon |  |
| `RECON_DOC_BYTES_MAX` | `str(8 * 1024 * 1024)` | recon |  |
| `RECON_DOC_READ_TRIES` | `"5"` | recon |  |
| `RECON_GMAIL_QUERY` | `"(has:attachment OR remittance OR invoice OR statement OR...` | recon |  |
| `RECON_MATERIAL_PENCE` | `"25000"` | recon | 250.00 |
| `RECON_ORDER_CAP` | `"1500"` | recon |  |
| `RECON_SEEN_CAP` | `"4000"` | recon |  |
| `RECON_STALE_DAYS` | `"21"` | recon |  |
| `RECON_THREADS_PER_SWEEP` | `"40"` | recon |  |
| `RECON_TOLERANCE_PENCE` | `"100"` | recon | 1.00 |
| `RECON_WINDOW_DAYS` | `"120"` | recon |  |

## tokenvault.py

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `TOKEN_ENCRYPTION_KEY` | `None` | tokenvault |  |

## worldoptions.py

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `WO_BASE_URL` | `DEFAULT_BASE` | worldoptions |  |
| `WO_KEY` | `""` | worldoptions |  |
| `WO_LABEL_DELIVERY` | `""` | worldoptions |  |
| `WO_METER_NUMBER` | `""` | worldoptions |  |
| `WO_PASSWORD` | `""` | worldoptions |  |
| `WO_PLUGIN_CODE` | `"Web_Service"` | worldoptions |  |

## xero.py

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `XERO_API_BASE` | `"https://api.xero.com"` | xero |  |
| `XERO_CLIENT_ID` | `""` | xero |  |
| `XERO_CLIENT_SECRET` | `""` | xero |  |
| `XERO_IDENTITY_BASE` | `"https://identity.xero.com"` | xero |  |
| `XERO_LOGIN_BASE` | `"https://login.xero.com"` | xero |  |
| `XERO_SCOPES` | `"offline_access accounting.invoices.read " "accounting.pa...` | xero |  |
| `XERO_TOKEN_PATH` | `"/data/xero_oauth.json"` | xero |  |
