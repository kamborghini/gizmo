# The CRM and mail

**Approved 20 Oct 2026.** Stage 4, piece 5 of the 14 October engineering
audit. Cameron approved all three parts. Nothing anyone sees changes.

## Why

The CRM and the shared inbox are woven together (website enquiries arrive by
mail and are filed as CRM leads, a deal shows its threads, incoming mail is
matched to contacts) and share a 3,600-line stretch of `copilot.py` with
Files and customer-data erasure, areas of their own. The CRM is 52 names and
8 routes; mail is 126 names (the inbox and its sync, owners, rules, sending
and its limits, attachments, sign-offs, the address book, the mail loop), 24
routes and the Gmail connect pair. Tests patch the CRM 13 times and mail 37.
`_mail_orders_for`, nested in `add_routes`, is used only by two mail routes.

Their routes are scattered through the route table, which is why
production's stayed put. Only one route has a pattern (`/dav{sub_path:path}`,
which answers only paths starting `/dav`) and no two routes share a path, so
which route answers a request cannot depend on where any other route stands.

## What changes

### 1. The proof learns when route order cannot matter

`make move-proof` accepts routes in another order when no two routes whose
order changed could answer the same request: each such route's path is
literal and no other route has it, and no pattern route that changed order
with it matches it. Otherwise the order must be exact, as now. An area's
routes can then be gathered into one `register` call where its first route
stood.

### 2. The CRM out: `gizmo/crm.py`, `gizmo/routes/crm.py`

Every `_crm`, `CRM_` and `_CRM` name: the store and its kept board (with the
store hook), deals, contacts, leads, activities, stages, labels, the enquiry
filing, a deal's threads, tombstones, the Shopify link sweep, the import, the
CRM's part of an erasure and its door. The 8 routes, gathered. Team colours
stay (they are the team's). Read as `crm.NAME`.

### 3. Mail out: `gizmo/mail.py`, `gizmo/routes/mail.py`

Every `_mail`, `MAIL_` and `_MAIL` name, with the enquiry spotting, the send
limits' counters and the erased-address cache: the mailbox store and its
memory copy (its own drop, as the accounts have), sync and labels, owners and
viewers, rules, sending, attachments, sign-offs, the address book, the mail
loop and its alerts, and the routes' helpers. The 24 mail routes and the
Gmail connect pair, gathered, with `_mail_orders_for` in their `register`.
The finance mailbox's tickets stay with reconciliation. Read as `mail.NAME`.

Both borrow from `copilot.py` as `core.` and import it last. `copilot.py`
reads them through the module's name.

A release note: "The CRM and mail on their own": "The CRM and the shared
inbox now each live on their own, so a change elsewhere cannot upset a deal
or a reply. Nothing looks different."

## Proof and guards

`make move-proof` (routes gathered as above, the drop for mail declared);
every guard of pieces 1 to 4; the suite's mail and CRM tests unchanged.

## Not in this piece

Files; customer-data erasure (beyond the CRM's own part); the finance
mailbox; the production routes; any change to how mail is synced or sent or
how the CRM works.
