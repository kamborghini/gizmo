# Environment variables

Generated from the code by `tools/env_reference.py`; do not edit by hand.
`make env-doc` rewrites it, and CI fails when it is stale.

210 variables are read. Every one has a default unless marked **(required)**; the defaults below are the code's own expressions, so a path like `/data/...` means the Railway volume. Set a variable in Railway, never in the code, and never paste a secret into chat or a document. `[shop domain]` stands for the shop's own website domain, which those defaults carry.

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

## copilot.py - Configuration

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `STORE_CONTEXT_CAP` | `"4000"` | copilot |  |

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

## gizmo/activity.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `ACTIVITY_MAX` | `"8000"` | gizmo.activity |  |
| `ACTIVITY_PATH` | `"/data/activity.json"` | gizmo.activity |  |

## gizmo/ai.py - The effort every call asks for, and the chat's thinking mode

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `ANTHROPIC_EFFORT` | `"high"` | gizmo.ai |  |
| `ANTHROPIC_EFFORT_DEEP` | `"max"` | gizmo.ai |  |
| `ANTHROPIC_THINKING` | `"adaptive"` | gizmo.ai |  |

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

## gizmo/backup.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `BACKUP_FILE_MAX` | `str(60 * 1024 * 1024)` | gizmo.backup |  |
| `BACKUP_SNAPSHOT_DIR` | `"/data/snapshots"` | gizmo.backup |  |
| `BACKUP_STATE_PATH` | `"/data/backup_state.json"` | gizmo.backup |  |

## gizmo/chat.py - The chat's limits: how long a conversation, and how large a 

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `MAX_CHAT_CHARS` | `"100000"` | gizmo.chat | total chars in a chat request |
| `MAX_MESSAGES` | `"100"` | gizmo.chat | chat history length |

## gizmo/chat.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `COPILOT_MAX_TOOL_ROUNDS` | `"12"` | gizmo.chat |  |
| `COPILOT_TOOL_RESULT_CAP` | `"50000"` | gizmo.chat |  |

## gizmo/config.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `APP_BASE_URL` | `""` | gizmo.config |  |
| `GOOGLE_CONNECT_SECRET` | `""` | gizmo.config |  |
| `SHOPIFY_API_KEY` | `None` | gizmo.config |  |
| `SHOPIFY_API_SECRET` | `None` | gizmo.config |  |
| `SHOPIFY_CLIENT_ID` | `""` | gizmo.config, server |  |
| `SHOPIFY_CLIENT_SECRET` | `""` | gizmo.config, server |  |
| `SHOPIFY_STORE` | `""` | gizmo.config, server | used to pin session tokens to this shop |

## gizmo/crm.py - CRM: the sales desk, modelled on Pipedrive

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

## gizmo/forecasting.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `FORECAST_INGEST_TOKEN` | `""` | gizmo.forecasting | shared secret the nightly forecasting service presents to /hooks/forecast/*; empty switches the hooks off |
| `FORECAST_PATH` | `"/data/forecast.json"` | gizmo.forecasting | the nightly forecasting service's latest run, and the cash flow workbook an admin uploaded (base64), in one store |

## gizmo/gate.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `MAX_BODY_BYTES` | `str(256 * 1024)` | gizmo.gate | 256 KB |
| `RATE_LIMIT_GLOBAL` | `"150"` | gizmo.gate | AI requests/window (cost ceiling) |
| `RATE_LIMIT_PER_CLIENT` | `"120"` | gizmo.gate | requests/window/client |
| `RATE_LIMIT_WINDOW` | `"60"` | gizmo.gate | seconds |

## gizmo/impact.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `IMPACT_MAX` | `"100"` | gizmo.impact |  |
| `IMPACT_PATH` | `"/data/impact.json"` | gizmo.impact | tracked-action impact log |

## gizmo/knowledge.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `KNOWLEDGE_CAP` | `"8000"` | gizmo.knowledge | max stored knowledge chars |
| `KNOWLEDGE_PATH` | `"/data/store_knowledge.json"` | gizmo.knowledge |  |
| `LEARN_MAX_PAGES` | `"12"` | gizmo.knowledge | pages crawled when learning |
| `LEARN_PAGE_CHARS` | `"3000"` | gizmo.knowledge | text kept per page |

## gizmo/layouts.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `LAYOUTS_PATH` | `"/data/layouts.json"` | gizmo.layouts | each person's arrangement of the cards on a screen |

## gizmo/liability.py - Chase desk: the weekly session of asking credit customers fo

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `CHASE_LOG_PATH` | `"/data/chase_log.json"` | gizmo.liability |  |

## gizmo/liability.py - Unpaid orders on credit terms: the tags that mark them, the 

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `LIABILITY_DEFAULT_TERMS` | `"30"` | gizmo.liability |  |
| `LIABILITY_DUE_SOON_DAYS` | `"7"` | gizmo.liability |  |
| `LIABILITY_TAGS` | `"Purchase order unpaid, Bank transfer unpaid, Procurement...` | gizmo.liability |  |

## gizmo/loans.py - Loan units: the projectors that go out to customers, and whe

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `LOANS_PATH` | `"/data/loans.json"` | gizmo.loans |  |

## gizmo/mail.py - Attachments on the way OUT. They live in the bucket under ma

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `ENQUIRY_SENDERS` | `"shopifyemail.com,shopify.com,[shop domain]"` | gizmo.mail |  |
| `MAIL_BOARD_DONE_DAYS` | `"90"` | gizmo.mail |  |
| `MAIL_BOARD_MAX` | `"1500"` | gizmo.mail |  |

## gizmo/mail.py - Shared inbox: who owns which email. The mailbox itself stays

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `MAILBOX_PATH` | `"/data/mailbox.json"` | gizmo.mail |  |
| `MAIL_ALERT_AFTER_TICKS` | `"30"` | gizmo.mail |  |
| `MAIL_DONE_KEEP_DAYS` | `"730"` | gizmo.mail |  |
| `MAIL_LOOP_SECS` | `"60"` | gizmo.mail |  |
| `MAIL_THREADS_CAP` | `"6000"` | gizmo.mail |  |
| `MAIL_TRACK_DAYS` | `"730"` | gizmo.mail |  |
| `RELEASE_INLINE_MAX` | `"12"` | gizmo.mail |  |

## gizmo/memory.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `MEMORY_INJECT` | `"40"` | gizmo.memory | max of each kind injected into prompts |
| `MEMORY_MAX` | `"500"` | gizmo.memory | max stored memories |
| `MEMORY_PATH` | `"/data/store_memory.json"` | gizmo.memory |  |

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

## gizmo/privacy.py - The pre-redact archive: the undo for an uninstall that was a

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `REDACT_ARCHIVE_DAYS` | `"30"` | gizmo.privacy |  |

## gizmo/privacy.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `PRIVACY_LOG_PATH` | `"/data/privacy_log.json"` | gizmo.privacy |  |

## gizmo/production.py - Production labels: orders carrying the production tag, shape

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `OPTION_CACHE_SECS` | `"21600"` | gizmo.production | 6 hours |
| `PRODUCTION_ARCHIVE_PATH` | `os.path.join(os.path.dirname(PRODUCTION_STATE_PATH) or "....` | gizmo.production |  |
| `PRODUCTION_LABEL_DAYS` | `"180"` | gizmo.production | how far back to look for tagged orders |
| `PRODUCTION_LABEL_TAG` | `"IP"` | gizmo.production | order tag that means "in production" |
| `PRODUCTION_STATE_MAX` | `"1000"` | gizmo.production |  |
| `PRODUCTION_STATE_PATH` | `"/data/production_state.json"` | gizmo.production |  |

## gizmo/profile.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `PROFILE_FIELD_CAP` | `"6000"` | gizmo.profile |  |
| `PROFILE_PATH` | `"/data/store_profile.json"` | gizmo.profile |  |

## gizmo/reconciliation.py - Reconciliation stores + the read-only tools the chat is give

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `ANTHROPIC_MODEL_RECON` | `None` | gizmo.reconciliation |  |
| `RECON_CACHE_PATH` | `"/data/recon_cache.json"` | gizmo.reconciliation |  |
| `RECON_DOCS_PATH` | `"/data/recon_docs.json"` | gizmo.reconciliation |  |
| `RECON_PATH` | `"/data/recon.json"` | gizmo.reconciliation |  |

## gizmo/routes/files.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `DAV_TRACE` | `None` | gizmo.routes.files |  |

## gizmo/routes/status.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `RAILWAY_GIT_COMMIT_SHA` | `None` | gizmo.routes.status, gizmo.updates, server |  |

## gizmo/scheduler.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `ALERTS_MAX` | `"60"` | gizmo.scheduler |  |
| `ALERTS_PATH` | `"/data/alerts.json"` | gizmo.scheduler | alerts the app raises |
| `ALERT_EMAIL_FROM` | `"Reactor <onboarding@resend.dev>"` | gizmo.scheduler |  |
| `ALERT_EMAIL_TO` | `""` | gizmo.scheduler |  |
| `RESEND_API_KEY` | `""` | gizmo.scheduler |  |
| `SCHEDULE_CHECK_SECS` | `"900"` | gizmo.scheduler | how often the scheduler wakes to check |
| `SCHEDULE_PATH` | `"/data/schedule.json"` | gizmo.scheduler |  |
| `WATCH_PATH` | `"/data/watch.json"` | gizmo.scheduler |  |

## gizmo/size_list.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `GOBO_ALIASES_LIVE` | `"/data/gobo-aliases.csv"` | gizmo.size_list |  |
| `GOBO_ALIASES_PATH` | `os.path.join(_REPO, "data", "gobo-aliases.csv")` | gizmo.size_list |  |
| `GOBO_OVERRIDES_LIVE` | `"/data/gobo-overrides.csv"` | gizmo.size_list |  |
| `GOBO_OVERRIDES_PATH` | `os.path.join(_REPO, "data", "gobo-overrides.csv")` | gizmo.size_list |  |
| `GOBO_SIZES_LIVE` | `"/data/gobo-sizes.csv"` | gizmo.size_list |  |
| `GOBO_SIZES_PATH` | `os.path.join(_REPO, "data", "gobo-sizes.csv")` | gizmo.size_list |  |

## gizmo/skills.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `SKILLS_INJECT_CAP` | `"24000"` | gizmo.skills | max total skill chars injected |
| `SKILLS_MAX` | `"200"` | gizmo.skills | max stored skills |
| `SKILLS_PATH` | `"/data/store_skills.json"` | gizmo.skills | merchant-authored skills |
| `SKILL_BODY_CAP` | `"40000"` | gizmo.skills | chars per skill body |
| `SKILL_TITLE_CAP` | `"120"` | gizmo.skills | chars per skill title |
| `SKILL_UPLOAD_CAP` | `"200000"` | gizmo.skills |  |

## gizmo/status.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `RAILWAY_ENVIRONMENT` | `None` | gizmo.status | set by Railway; the volume check runs only there |
| `RAILWAY_PROJECT_ID` | `None` | gizmo.status | set by Railway; the volume check runs only there |

## gizmo/team.py - Team colours, who may edit the Size list or send mail, first

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `SETUP_CODE` | `""` | gizmo.team | set only while first-run setup is needed, then remove; unset locks setup |

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

## gizmo/updates.py - What's new: the release notes that ship WITH the release, an

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `CHANGELOG_PATH` | `os.path.join(_REPO, "data", "changelog.json")` | gizmo.updates |  |
| `FEEDBACK_PATH` | `"/data/feedback.json"` | gizmo.updates | feature requests from the desk |

## gizmo/work.py - Work sessions: clocking in and out, for part-time accounts o

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `WORK_ARCHIVE_PATH` | `os.path.join(os.path.dirname(WORK_PATH) or ".", "worklog_...` | gizmo.work |  |
| `WORK_KEEP` | `"2000"` | gizmo.work |  |
| `WORK_MIN_SECS` | `"60"` | gizmo.work |  |
| `WORK_PATH` | `"/data/worklog.json"` | gizmo.work |  |

## gizmo/xero_sync.py - top

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `CONNECTOR_TOKEN` | `None` | gizmo.xero_sync |  |
| `CONNECTOR_URL` | `None` | gizmo.xero_sync |  |

## eori.py

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `EORI_CACHE_PATH` | `"/data/eori_cache.json"` | eori |  |

## google_mail.py

| Variable | Default | Read by | Notes |
|---|---|---|---|
| `GMAIL_API_BASE` | `"https://gmail.googleapis.com"` | google_mail |  |
| `GMAIL_FINANCE_TOKEN_PATH` | `"/data/gmail_finance_oauth.json"` | google_mail |  |
| `GMAIL_TOKEN_PATH` | `"/data/gmail_oauth.json"` | google_mail |  |
| `GMAIL_TOKEN_URL` | `"https://oauth2.googleapis.com/token"` | google_mail |  |
| `GOOGLE_OAUTH_CLIENT_ID` | `""` | google_mail |  |
| `GOOGLE_OAUTH_CLIENT_SECRET` | `""` | google_mail |  |

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
