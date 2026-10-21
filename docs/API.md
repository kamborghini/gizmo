# API routes

Generated from the code by `tools/route_reference.py`; do not edit by hand.
`make api-doc` rewrites it, and CI fails when it is stale.

151 routes. **Tab** is the tab that opens a route (`_TAB_ROUTES`); an `/api/` route no tab claims is refused unless it is on `_OPEN_API`. **Door** is the guard the handler opens with (`_guard` is the one door: rate window, tab, session, rank, AI slot, body); `own check` means the route authenticates itself (a hook, a webhook, OAuth, print, assets). **Checks** are the permission helpers the handler calls itself.

## `/`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/` | GET | outside the tab map | own check |  |  | `copilot.index` |  |

## `/api/alerts`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/alerts` | POST | any account | `_guard` |  |  | `copilot.alerts_route` |  |

## `/api/auth`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/auth/login` | POST | any account | `_auth_guard` |  |  | `gizmo.routes.team.auth_login_route` |  |
| `/api/auth/logout` | POST | any account | `_auth_guard` |  |  | `gizmo.routes.team.auth_logout_route` |  |
| `/api/auth/mfa` | POST | any account | `_guard` |  |  | `gizmo.routes.team.auth_mfa_route` | Turn a second factor on, or ask whether it is on. |
| `/api/auth/mfa-verify` | POST | any account | `_auth_guard` |  |  | `gizmo.routes.team.auth_mfa_verify_route` | Finish a login. |
| `/api/auth/password` | POST | any account | `_auth_guard` |  |  | `gizmo.routes.team.auth_password_route` |  |
| `/api/auth/setup` | POST | any account | `_auth_guard` |  |  | `gizmo.routes.team.auth_setup_route` |  |
| `/api/auth/state` | POST | any account | `_auth_guard` |  |  | `gizmo.routes.team.auth_state_route` |  |

## `/api/backup`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/backup` | POST | any account | `_guard` | reads its own body | `_team_role` | `copilot.backup_route` | Everything the app has learned lives as files on one volume; this hands the merchant a zip of it. |

## `/api/cache`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/cache` | POST | any account | `_guard` | reads its own body | `_user_tabs` | `gizmo.routes.analytics.cache_route` |  |

## `/api/chat`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/chat` | POST | chat | `_guard` | AI slot | `_team_level` | `copilot.chat` |  |
| `/api/chat/stream` | POST | chat | `_guard` | AI slot | `_team_level` | `copilot.chat_stream` | Server-sent-events variant of /api/chat: emits real tool-step progress as the model works, then a final structured result. |

## `/api/connector`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/connector` | POST | connector | `_guard` |  | `_team_level` | `copilot.connector_route` | The Xero connector tab's whole API. |

## `/api/crm`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/crm/activity` | POST | crm | `_crm_guard` |  |  | `gizmo.routes.crm.crm_activity_route` |  |
| `/api/crm/board` | POST | crm | `_crm_guard` |  |  | `gizmo.routes.crm.crm_board_route` |  |
| `/api/crm/contact` | POST | crm | `_crm_guard` |  | `_team_role`, `_user_tabs` | `gizmo.routes.crm.crm_contact_route` |  |
| `/api/crm/deal` | POST | crm | `_crm_guard` |  | `_user_tabs` | `gizmo.routes.crm.crm_deal_route` |  |
| `/api/crm/import` | POST | crm | `_mail_guard` |  | `_team_role` | `gizmo.routes.crm.crm_import_route` | Copy Pipedrive into gizmo's CRM. |
| `/api/crm/lead` | POST | crm | `_crm_guard` |  |  | `gizmo.routes.crm.crm_lead_route` |  |
| `/api/crm/pipedrive` | POST | crm | `_mail_guard` |  | `_team_role` | `gizmo.routes.crm.crm_pipedrive_route` | Look at the Pipedrive account, read-only. |
| `/api/crm/stages` | POST | crm | `_crm_guard` |  | `_team_level` | `gizmo.routes.crm.crm_stages_route` |  |

## `/api/custom`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/custom/book` | POST | labels | `_guard` |  | `_team_level` | `gizmo.routes.dispatch.custom_book_route` | Book a courier to a pasted address. |
| `/api/custom/list` | POST | labels | `_guard` |  | `_team_level` | `gizmo.routes.dispatch.custom_list_route` | Pasted-address shipments already booked. |
| `/api/custom/quote` | POST | labels | `_guard` |  |  | `gizmo.routes.dispatch.custom_quote_route` | Price couriers to a pasted address. |
| `/api/custom/visibility` | POST | labels | `_guard` | rank admin |  | `gizmo.routes.dispatch.custom_visibility_route` | Keep one pasted-address shipment to admins, or let it back out. |

## `/api/customer-history`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/customer-history` | POST | customers or crm | `_guard` |  |  | `copilot.customer_history_route` |  |

## `/api/customer-tags`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/customer-tags` | POST | customers | `_guard` | reads its own body |  | `gizmo.routes.analytics.customer_tags_route` |  |

## `/api/customers`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/customers` | POST | customers | `_guard` | AI slot |  | `gizmo.routes.analytics.customers_route` |  |

## `/api/dispatch`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/dispatch/book` | POST | labels | `_guard` |  |  | `gizmo.routes.dispatch.dispatch_book_route` | Book the chosen courier (CHARGES the WO account), fulfill + tag. |
| `/api/dispatch/cancel` | POST | labels | `_guard` |  | `_team_level` | `gizmo.routes.dispatch.dispatch_cancel_route` | Cancel a booked shipment at World Options (best-effort). |
| `/api/dispatch/collections` | POST | labels | `_guard` |  | `_team_level` | `gizmo.routes.dispatch.dispatch_collections_route` | What is coming, and from whom, on a given day. |
| `/api/dispatch/diagnose` | POST | labels | `_guard` |  |  | `gizmo.routes.dispatch.dispatch_diagnose_route` | Why is a courier service missing? |
| `/api/dispatch/label` | POST | labels | `_guard` |  | `_team_level` | `gizmo.routes.dispatch.dispatch_label_route` | Return the stored label(s) for an already-dispatched order (reprint). |
| `/api/dispatch/manifest` | POST | labels | `_guard` |  | `_team_level` | `gizmo.routes.dispatch.dispatch_manifest_route` | Everything booked on one day (Europe/London): the driver handover list and the sheet to check the World Options invoice against. |
| `/api/dispatch/parse-address` | POST | labels | `_guard` |  |  | `gizmo.routes.dispatch.parse_address_route` | Turn a pasted block of text into address fields. |
| `/api/dispatch/quote` | POST | labels | `_guard` |  |  | `gizmo.routes.dispatch.dispatch_quote_route` | Price couriers for one order. |

## `/api/eori`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/eori/check` | POST | labels | `_guard` |  |  | `gizmo.routes.dispatch.eori_check_route` | Check a customer's EORI number against the EU's validation service. |

## `/api/files`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/files/complete` | POST | files | `_files_guard` |  |  | `gizmo.routes.files.files_complete_route` |  |
| `/api/files/download-url` | POST | files | `_files_guard` |  |  | `gizmo.routes.files.files_download_route` |  |
| `/api/files/drive` | POST | files | `_files_guard` |  |  | `gizmo.routes.files.files_drive_route` | The Finder drive's own password: made, replaced and removed here, after a full sign-in (codes included), shown once, kept as a SHA-256. |
| `/api/files/file` | POST | files | `_files_guard` |  | `_team_level` | `gizmo.routes.files.files_file_route` |  |
| `/api/files/folder` | POST | files | `_files_guard` |  |  | `gizmo.routes.files.files_folder_route` |  |
| `/api/files/tree` | POST | files | `_files_guard` |  |  | `gizmo.routes.files.files_tree_route` |  |
| `/api/files/upload-url` | POST | files | `_files_guard` |  |  | `gizmo.routes.files.files_upload_route` |  |

## `/api/forecast`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/forecast` | POST | forecast | `_guard` |  | `_team_level` | `copilot.forecast_route` | What the tab shows: the latest run, the last failure if the latest attempt failed, the recent runs, the workbook on file and whether the hook is configured a... |
| `/api/forecast/workbook` | POST | forecast | `_guard` | max body cap, reads its own body | `_team_level` | `copilot.forecast_workbook_upload_route` | An admin replaces the cash flow workbook. |

## `/api/gobo-sizes`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/gobo-sizes/check` | POST | labels or sizes | `_guard` |  |  | `gizmo.routes.size_list.gobo_check_route` | What a label prints for a fixture named in free text, for the Size list's search. |
| `/api/gobo-sizes/list` | POST | labels or sizes | `_guard` | reads its own body |  | `gizmo.routes.size_list.gobo_list_route` | The whole sheet with the rulings over it, for the Size list tab. |
| `/api/gobo-sizes/models` | POST | labels or sizes | `_guard` |  |  | `gizmo.routes.size_list.gobo_models_route` | Models already on the sheet, for the picker behind 'this is another name for'. |
| `/api/gobo-sizes/rule` | POST | labels or sizes | `_guard` | reads its own body |  | `gizmo.routes.size_list.gobo_rule_route` | Resolve one flagged model, from inside the app. |
| `/api/gobo-sizes/rules` | POST | labels or sizes | `_guard` | reads its own body |  | `gizmo.routes.size_list.gobo_rules_route` | The merchant's standing rulings on models, and whether this person may change them. |
| `/api/gobo-sizes/upload` | POST | labels or sizes | `_guard` | max body big, reads its own body | `_team_level` | `gizmo.routes.size_list.gobo_sizes_upload_route` | Self-serve size sheet update: validate the CSV hard, keep a .bak of the previous sheet, and report the before/after so a bad file can't quietly wipe the size... |

## `/api/impact`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/impact` | POST | memory | `_guard` |  | `_team_level` | `copilot.impact_route` |  |

## `/api/keyword-scan`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/keyword-scan` | POST | keywords | `_guard` | AI slot |  | `gizmo.routes.seo.keyword_scan_route` |  |

## `/api/keywords`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/keywords` | POST | keywords | `_guard` | AI slot |  | `gizmo.routes.seo.keywords_route` |  |

## `/api/layouts`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/layouts` | POST | any account | `_guard` | max body LAYOUT_MAX_BODY, cap LAYOUT_MAX_BODY |  | `copilot.layouts_route` | The caller's own card layouts: {} reads them all, a view with an order and a hidden list saves that screen's, a view with reset true removes it. |

## `/api/learn`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/learn` | POST | memory | `_guard` |  | `_team_level` | `gizmo.routes.knowledge.learn_route` |  |
| `/api/learn/run` | POST | memory | `_guard` | rank admin, AI slot |  | `gizmo.routes.knowledge.learn_run_route` |  |

## `/api/liability`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/liability` | POST | liability | `_guard` |  |  | `copilot.liability_route` |  |
| `/api/liability/chase` | POST | liability | `_guard` |  |  | `copilot.liability_chase_route` | Stamp an account as chased today. |

## `/api/loans`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/loans` | POST | loans | `_guard` |  | `_team_level` | `gizmo.routes.loans.loans_route` | Loan projectors: the register of what the shop owns, and where each one is. |

## `/api/mail`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/mail/addresses` | POST | mail | `_mail_guard` |  |  | `gizmo.routes.mail.mail_addresses_route` | The To field's address book: everyone in the inbox and the CRM. |
| `/api/mail/assign` | POST | mail | `_mail_guard` |  |  | `gizmo.routes.mail.mail_assign_route` |  |
| `/api/mail/attach-done` | POST | mail | `_mail_guard` |  |  | `gizmo.routes.mail.mail_attach_done_route` | What actually landed. |
| `/api/mail/attach-url` | POST | mail | `_mail_guard` |  |  | `gizmo.routes.mail.mail_attach_url_route` | A presigned PUT for a file about to be attached to an email. |
| `/api/mail/attachment` | POST | mail | `_mail_guard` |  | `_user_tabs` | `gizmo.routes.mail.mail_attachment_route` | Bring an attachment out of Gmail and into the files store. |
| `/api/mail/board` | POST | mail | `_mail_guard` |  | `_team_role` | `gizmo.routes.mail.mail_board_route` |  |
| `/api/mail/body` | POST | mail | `_mail_guard` |  |  | `gizmo.routes.mail.mail_body_route` | The actual text of the conversation, read on demand. |
| `/api/mail/bulk` | POST | mail | `_mail_guard` |  |  | `gizmo.routes.mail.mail_bulk_route` | Many threads, one decision. |
| `/api/mail/claim` | POST | mail | `_mail_guard` |  |  | `gizmo.routes.mail.mail_claim_route` |  |
| `/api/mail/connect-link` | POST | mail | `_mail_guard` |  | `_team_role` | `gizmo.routes.mail.mail_connect_link_route` | Master-only: mint a single-use ticket for the consent walk, so nobody has to copy a server secret into a URL by hand. |
| `/api/mail/disconnect` | POST | mail | `_mail_guard` |  | `_team_role` | `gizmo.routes.mail.mail_disconnect_route` |  |
| `/api/mail/draft` | POST | mail | `_mail_guard` |  | `_user_tabs` | `gizmo.routes.mail.mail_draft_route` | Draft a reply with Claude, then (on a second, explicit call) put it in Gmail as a DRAFT for the person to review and send themselves. |
| `/api/mail/note` | POST | mail | `_mail_guard` |  |  | `gizmo.routes.mail.mail_note_route` |  |
| `/api/mail/orders` | POST | mail | `_mail_guard` |  | `_user_tabs` | `gizmo.routes.mail.mail_orders_route` | What this app knows about the person who sent the email. |
| `/api/mail/presence` | POST | mail | `_mail_guard` |  |  | `gizmo.routes.mail.mail_presence_route` |  |
| `/api/mail/read` | POST | mail | `_mail_guard` |  |  | `gizmo.routes.mail.mail_read_route` | Mark threads read or unread, in Gmail and here at once. |
| `/api/mail/rules` | POST | mail | `_mail_guard` |  |  | `gizmo.routes.mail.mail_rules_route` | Standing decisions about arriving mail. |
| `/api/mail/search` | POST | mail | `_mail_guard` |  |  | `gizmo.routes.mail.mail_search_route` | Search the WHOLE mailbox, by handing the query to Google. |
| `/api/mail/send` | POST | mail | `_mail_guard` |  |  | `gizmo.routes.mail.mail_send_route` | Send an email FROM gizmo: a reply on a conversation, or a new one. |
| `/api/mail/settings` | POST | mail | `_mail_guard` |  |  | `gizmo.routes.mail.mail_settings_route` | The footer, the saved replies and your own sign-off. |
| `/api/mail/state` | POST | mail | `_mail_guard` |  |  | `gizmo.routes.mail.mail_state_route` |  |
| `/api/mail/thread` | POST | mail | `_mail_guard` |  | `_user_tabs` | `gizmo.routes.mail.mail_thread_route` |  |
| `/api/mail/undo` | POST | mail | `_mail_guard` |  |  | `gizmo.routes.mail.mail_undo_route` |  |
| `/api/mail/viewing` | POST | mail | `_mail_guard` |  |  | `gizmo.routes.mail.mail_viewing_route` |  |

## `/api/margin`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/margin` | POST | labels | `_guard` |  |  | `gizmo.routes.dispatch.margin_route` | What dispatched orders actually made. |

## `/api/memory`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/memory` | POST | memory | `_guard` |  | `_team_level` | `gizmo.routes.memory.memory_route` |  |

## `/api/order`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/order/edit` | POST | labels | `_guard` | reads its own body | `_live_uid`, `_team_level` | `gizmo.routes.orderbook.order_edit_route` | Read or change the delivery address and contact details on a placed order. |

## `/api/overview`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/overview` | POST | overview | `_guard` | AI slot |  | `gizmo.routes.analytics.overview` |  |

## `/api/privacy`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/privacy` | POST | any account | `_guard` | rank admin |  | `gizmo.routes.privacy.privacy_requests_route` | Settings, Privacy requests: the customer erasures Shopify asked for, each waiting for an admin to erase or stop (see _redact_hold), and the data requests to ... |

## `/api/product`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/product` | POST | products | `_guard` | AI slot |  | `copilot.product_route` |  |

## `/api/production-labels`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/production-labels` | POST | labels | `_guard` |  |  | `gizmo.routes.production.production_labels_route` |  |
| `/api/production-labels/coverage` | POST | labels | `_guard` |  |  | `gizmo.routes.production.labels_coverage_route` |  |
| `/api/production-labels/missing` | POST | labels | `_guard` |  |  | `gizmo.routes.production.labels_missing_route` |  |
| `/api/production-labels/queue` | POST | labels | `_guard` |  |  | `gizmo.routes.production.labels_queue_route` |  |

## `/api/production-state`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/production-state` | POST | labels | `_guard` |  |  | `gizmo.routes.production.production_state_route` |  |

## `/api/products`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/products` | POST | products | `_guard` |  |  | `copilot.products_route` |  |

## `/api/profile`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/profile` | POST | any account | `_guard` |  | `_team_level` | `copilot.profile_route` |  |

## `/api/recon`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/recon/connect-link` | POST | recon | `_guard` | reads its own body | `_team_role` | `copilot.recon_connect_link_route` | Master-only: mint a single-use ticket for the accounts-mailbox consent walk, so nobody has to paste a server secret into a URL. |
| `/api/recon/disconnect` | POST | recon | `_guard` | reads its own body | `_team_role` | `copilot.recon_disconnect_route` | Disconnect Xero or the accounts mailbox, and mean it. |
| `/api/recon/exception` | POST | recon | `_guard` |  |  | `copilot.recon_exception_route` |  |
| `/api/recon/exceptions` | POST | recon | `_guard` |  |  | `copilot.recon_exceptions_route` |  |
| `/api/recon/status` | POST | recon | `_guard` |  | `_team_role` | `copilot.recon_status_route` |  |
| `/api/recon/sweep` | POST | recon | `_guard` | rank admin, AI slot |  | `copilot.recon_sweep_route` |  |
| `/api/recon/xero-link` | POST | recon | `_guard` | reads its own body | `_team_role` | `copilot.recon_xero_link_route` | Master-only: a single-use ticket for the Xero consent walk. |

## `/api/reorder-radar`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/reorder-radar` | POST | customers | `_guard` |  |  | `gizmo.routes.analytics.reorder_radar_route` |  |

## `/api/restore`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/restore` | POST | any account | `_guard` | max body big, reads its own body | `_team_role` | `copilot.restore_route` | Master-only: put a downloaded backup zip back onto the volume. |

## `/api/schedule`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/schedule` | POST | any account | `_guard` |  | `_team_level` | `copilot.schedule_route` |  |

## `/api/seo`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/seo` | POST | seo | `_guard` | AI slot |  | `gizmo.routes.seo.seo_route` |  |

## `/api/shipping`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/shipping/config` | POST | labels | `_guard` |  | `_team_level` | `gizmo.routes.dispatch.shipping_config_route` | Get or set shipping settings. |
| `/api/shipping/validate` | POST | labels | `_guard` |  |  | `gizmo.routes.dispatch.shipping_validate_route` | Confirm the World Options credentials work by pricing a tiny test parcel (read-only; never charges). |

## `/api/skills`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/skills` | POST | skills | `_guard` | max body SKILLS_BODY_MAX, cap SKILLS_BODY_MAX | `_team_level`, `_team_role` | `gizmo.routes.skills.skills_route` |  |
| `/api/skills/read` | POST | skills | `_guard` | rank admin, AI slot |  | `gizmo.routes.skills.skills_read_route` |  |

## `/api/status`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/status` | POST | any account | `_guard` | reads its own body | `_team_role` | `copilot.status_route` | Connection-health summary for the Settings panel: Shopify, AI, and Google. |

## `/api/stock-usage`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/stock-usage` | POST | labels | `_guard` |  |  | `copilot.stock_usage_route` |  |
| `/api/stock-usage/send` | POST | labels | `_guard` |  |  | `copilot.stock_usage_send_route` | The reviewed day sheet goes to the stock app as FINAL figures. |

## `/api/team`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/team/board` | POST | any account | `_team_guard` | rank admin | `_team_role` | `gizmo.routes.team.team_board_route` |  |
| `/api/team/me` | POST | any account | `_guard` | reads its own body | `_user_tabs` | `gizmo.routes.team.team_me_route` |  |
| `/api/team/user` | POST | any account | `_team_guard` | rank admin | `_team_level` | `gizmo.routes.team.team_user_route` |  |

## `/api/updates`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/updates` | POST | any account | `_guard` |  | `_team_level` | `copilot.updates_route` | What's new + the desk's feature requests. |

## `/api/usage`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/usage` | POST | any account | `_guard` | reads its own body |  | `copilot.usage_route` |  |

## `/api/work`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/api/work/board` | POST | any account | `_team_guard` | rank admin |  | `gizmo.routes.work.work_board_route` |  |
| `/api/work/clock` | POST | any account | `_guard` |  |  | `gizmo.routes.work.work_clock_route` |  |
| `/api/work/report` | POST | any account | `_team_guard` | rank admin |  | `gizmo.routes.work.work_report_route` |  |
| `/api/work/resolve` | POST | any account | `_team_guard` | rank admin |  | `gizmo.routes.work.work_resolve_route` |  |
| `/api/work/status` | POST | any account | `_guard` | reads its own body |  | `gizmo.routes.work.work_status_route` |  |

## `/assets`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/assets/app.css` | GET | outside the tab map | own check |  |  | `copilot.app_css` |  |
| `/assets/app.js` | GET | outside the tab map | own check |  |  | `copilot.app_js` |  |
| `/assets/composer.js` | GET | outside the tab map | own check |  |  | `copilot.composer_js` |  |

## `/brand`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/brand/logo-light.svg` | GET | outside the tab map | own check |  |  | `copilot.brand_logo_light` |  |
| `/brand/logo.svg` | GET | outside the tab map | own check |  |  | `copilot.brand_logo` |  |

## `/dav{sub_path:path}`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/dav{sub_path:path}` | OPTIONS, PROPFIND, GET, HEAD, PUT, MKCOL, DELETE, MOVE, COPY, LOCK, UNLOCK | outside the tab map | own check |  |  | `gizmo.routes.files.dav_route` |  |

## `/fonts`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/fonts/bricolage.woff2` | GET | outside the tab map | own check |  |  | `copilot.label_font` |  |

## `/healthz`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/healthz` | GET | outside the tab map | own check |  |  | `copilot.healthz` |  |

## `/hooks`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/hooks/forecast/ledger` | GET | outside the tab map | own check |  | `_forecast_token_ok` | `copilot.forecast_ledger_hook` | The service reads back who has actually been right, so a run can weigh its sources on their record rather than only on a backtest it computed itself a moment... |
| `/hooks/forecast/results` | POST | outside the tab map | own check |  | `_forecast_token_ok` | `copilot.forecast_results_hook` | The nightly forecasting service (a second Railway service on this repo, `python -m forecast nightly`) posts each run here. |
| `/hooks/forecast/shopify` | POST | outside the tab map | own check |  | `_forecast_token_ok` | `copilot.forecast_shopify_hook` | The service's reads of the store, made here with the app's own credential, so the service holds no Shopify credential at all. |
| `/hooks/forecast/workbook` | GET | outside the tab map | own check |  | `_forecast_token_ok` | `copilot.forecast_workbook_hook` | The service fetches the workbook an admin uploaded in the tab, so the plan lives in one place and a revised sheet reaches the next run. |

## `/oauth`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/oauth/gmail-finance/callback` | GET | outside the tab map | own check |  |  | `copilot.gmail_finance_callback` |  |
| `/oauth/gmail-finance/start` | GET | outside the tab map | own check |  | `_secret_ok` | `copilot.gmail_finance_start` |  |
| `/oauth/gmail/callback` | GET | outside the tab map | own check |  |  | `gizmo.routes.mail.gmail_callback` |  |
| `/oauth/gmail/start` | GET | outside the tab map | own check |  |  | `gizmo.routes.mail.gmail_start` |  |
| `/oauth/google/callback` | GET | outside the tab map | own check |  |  | `copilot.google_callback` |  |
| `/oauth/google/start` | GET | outside the tab map | own check |  |  | `copilot.google_start` |  |
| `/oauth/xero/callback` | GET | outside the tab map | own check |  |  | `copilot.xero_callback` |  |
| `/oauth/xero/start` | GET | outside the tab map | own check |  | `_secret_ok` | `copilot.xero_start` |  |

## `/print`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/print/production-labels` | GET, OPTIONS | labels | own check |  | `_live_uid`, `_uid_has_tab`, `_verify_session_token` | `copilot.print_labels_doc` | Printable label document for the admin print-action extensions. |
| `/print/production-labels/sign` | POST, OPTIONS | labels | own check |  | `_live_uid`, `_uid_has_tab`, `_verify_session_token` | `copilot.sign_label_doc` | The print-action extension calls this with the merchant's id token and gets back a short-lived signed URL for the label document, which the admin's print pre... |

## `/webhooks`

| Route | Methods | Tab | Door | Terms | Checks | Handler | What it does |
|---|---|---|---|---|---|---|---|
| `/webhooks/orders` | POST | outside the tab map | own check |  |  | `gizmo.routes.orderbook.order_webhook` | Shopify's order events. |
| `/webhooks/privacy` | POST | outside the tab map | own check |  |  | `gizmo.routes.privacy.privacy_webhook` | Shopify's three mandatory compliance topics, on one receiver. |
