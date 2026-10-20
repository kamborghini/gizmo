# Orders and production

**Approved 20 Oct 2026.** Stage 4, piece 4 of the 14 October engineering
audit. Cameron approved all three parts. Nothing anyone sees changes; above
all, no production label changes.

## Why

The dispatch desk still borrows 23 names from `copilot.py`, 16 of them orders
and Shopify. Orders and production are one tangle: from the label builder
and the order reads, 130 names (about 1,700 lines) follow, half of the orders
code sits in the "Production labels" section, and the label builder reads
the Size list's rules. Every area reaches Shopify the same way: `_tool_json`
reads through the tool registry (it reads nothing but the logger) and
`add_routes` stores the 13 capabilities `server.py` hands in through three
`global` lines. Tests patch this group about 180 times (`_tool_json` 117).

The production routes sit in four places in the route table, the frozen print
route among them, which reads four production names and `_release_bg`; no
test patches them. `_spawn_bg`, which tests patch, is the general background
helper and stays.

## What changes

### 1. The way to Shopify: `gizmo/shopify.py` (floor)

`_tool_json`, `_shopify_gone` and the 13 capabilities (`_order_tag_writer`,
`_fulfillment_writer`, `_fulfillment_canceler`, `_webhook_ensurer`,
`_payment_terms_writer`, `_order_writer`, `_scope_reader`, `_tax_id_reader`,
`_forecast_reader`, `_install_checker`, `_customer_checker`, `_api_version`,
`_product_meta_reader`). It imports nothing above it. `add_routes` stores
them on the module (its `global` lines go; declared). Read as `shopify.NAME`.

### 2. Orders, production and the size list

- `gizmo/orders.py`: the order sweep and its cache and epochs, the webhook
  bookkeeping, reading orders, their tags and tag locks, the per-order lock,
  order edits and address checks, due dates, status, country, address,
  lines and weight, the shop record and origin, fulfilment and its undoing.
- `gizmo/production.py`: production's settings and state store, mark printed
  and made, the label's product, option and item readers, projectors, the
  label shape and builder (`run_production_labels`), release and the tag
  moves, missing production, payment terms on release, the label logo.
- `gizmo/sizes.py`: the Size list's rules and lookup, which the label builder
  reads (its own tab; a ruling, recorded in the plan's ledger).

Read as `orders.`, `production.` and `sizes.`; they borrow from `copilot.py`
as `core.` and import it last. The routes stay in `add_routes` this piece.
The frozen print route keeps its bytes: `copilot.py` takes the five moved
names it reads by name (none patched). The desk's borrowed list drops to
about 6.

### 3. The labels proven unchanged by what they print

`t_the_printed_labels_do_not_change`, added first on today's code: the label
data `run_production_labels` gives for the suite's fixture orders, and the
printed label document for them at 4x6 and 4x4, byte for byte (dates
masked), pinned to hashes computed on main. Plus `make move-proof` (declared:
the capability `global` lines) and the print freeze.

A release note: "Orders and production on their own": "How the app reads
orders and builds production labels now each live on their own, so a change
elsewhere cannot alter a label. Nothing looks different."

## Not in this piece

The production and order routes; customers, the CRM, mail and files; any
change to a label, the queue, the size list or how orders are read.
