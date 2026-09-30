# Upsell offers: an Upsell page and a thank-you page extension

Date: 2026-09-30. Status: design agreed section by section with Cameron on
2026-09-30, then checked by three independent reviews (Shopify platform
claims, Reactor code claims, and an adversarial completeness critique) and
revised. For Cameron's review, with four decisions still open (last section),
before the build plan is written.

## Why

Cameron: "we need a page built on the app for upsell, that makes the most of
shopifys available upsell options and lets me tune things like upsell in
checkout etc. for plans that aren't shopify plus". The goals he named:
"Projectors to customers who have poor quality units, and warranties for
people buying projectors".

What a non-Plus store can use from a custom app like Reactor, checked against
shopify.dev and the reference corpus on 2026-09-30:

| Surface | For Reactor on this plan | Notes |
|---|---|---|
| In-checkout steps (information, shipping, payment) | No | Checkout UI extensions there are Plus only |
| Post-purchase page | No | Plus only for custom apps (App Store post-purchase apps work on other plans; Reactor is a custom app) |
| Shopify Functions from a custom app | No | Plus only |
| Thank-you page (`purchase.thank-you.block.render`) | Yes | Basic plan or higher. Read-only: an offer links out to a new checkout |
| Order status page (`customer-account.order-status.block.render`) | Yes, with limits | Basic or higher; a customer account extension, not run on legacy customer accounts; shown to a signed-in customer or from the order email's link while it is live (about 2 to 3 weeks); the public page a stale link opens shows no app blocks |
| Product page and cart (theme app extension) | Yes | Not chosen for now |
| Discount codes (Admin API) | Yes | Needs `write_discounts` |
| Emails from Reactor | Yes | Not chosen for now |

What exists today, measured 2026-09-30:

| Thing | State |
|---|---|
| Customers' fixtures | Most gobo order lines name their fixture in line properties `Manufacturer` and `Model` (or a per-maker `<Maker> Models` dropdown). Reactor reads them with `_item_prop` (~5999), `_item_model` (~6049) and `_strip_price` (~5241, regex `_PRICE_SUFFIX_RE` ~5238), tidied with `_norm_key` (~5461), as `_shape_label_order` does (~6833), and sizes them with `_gobo_lookup` (~5733). Quote Engine stock lines often carry the fixture only as free text in `Item Notes` (not read), and some lines say `Model: other`; neither can match an offer |
| How orders are made | About 80% of orders start as drafts from the Quote Engine and are completed without the buyer passing through checkout; many quoted projector lines are custom lines with no product, only a SKU (for example `P107W-QM`). Such orders never show a thank-you page |
| Projectors | Shopify products of type `Projector` (19, several in draft) |
| Warranty products | None exist |
| App permissions | `read_products`, `read_discounts`, `write_orders`, `write_merchant_managed_fulfillment_orders`; not `write_products`, `write_discounts` or `write_publications`. Publications access was dropped on purpose in the September scope trim, and `t_the_app_asks_for_no_scope_it_cannot_use` pins it |
| Production queues | Unprocessed (the store tags new orders), To make, To ship, Complete, Custom shipments. Every release goes through `_release_tags` (~6433) |
| Scheduled work | `_scheduler_loop` (~11366, every 15 minutes) calls `_x_tick()` jobs spaced by stamps in watch.json. There is no regular order sweep; orders are read on demand, and the orders webhook hands each order to a task run after the reply (`_crm_link_order_soon`) |
| Shopify writes | Injected writers defined in server.py, passed to `copilot.add_routes`, kept out of `COPILOT_TOOLS`; `REQUIRED_WRITE_SCOPES` feeds Settings > Connections |
| Admin extensions | `print-label-order`, `print-label-bulk` (api_version 2026-04, Preact and `s-*`), `dispatch-order` (admin link) |
| Xero | A separate service (shopify-xero-connector) posts every line to one sales account and marks untaxed lines zero-rated |

## Decisions already made

Taken with Cameron on 2026-09-30:

1. **Who gets the upgrade offer:** customers whose gobo orders name a fixture
   Cameron has marked as poor quality on the Upsell page.
2. **Where the upgrade offer appears:** the thank-you page and the order
   status page.
3. **The upgrade deal:** a discount code off the recommended projector.
4. **Where the warranty is offered:** the thank-you page (and the order status
   page), to people who have just bought a projector.
5. **Warranty pricing:** a price per projector model.
6. **Warranty lengths:** a choice of lengths (1, 2 or 3 extra years), each
   switched on or off per model.
7. **Approach B, rules in Shopify.** Reactor publishes the rules into the
   shop's app settings and the extension decides on its own, with no call back
   to Reactor. Accepted costs: shared codes, views not counted, and the
   fixture tidy existing a second time in the extension, kept to an exact
   lookup of spellings Reactor has already resolved.

## Design

### 1. Architecture and data flow

```
Upsell page (Reactor)
   |  Publish (Cameron) / automatic refresh of machine-kept fields (hourly)
   v
Shopify: codes and warranty products added, then the rules document
   (shop metafield $app / upsell, json), then anything removed
   |  read at render
   v
"Upsell offers" extension: thank-you page and order status page
   reads the order's lines + the rules, shows at most two cards
   |  button: cart link with code and offer attributes
   v
New checkout -> new order carrying reactor_offer / reactor_after
   |  orders webhook (task after reply) + hourly backfill
   v
Results on the Upsell page, warranty register
```

The extension makes no network calls and writes nothing. If Reactor is down,
the last published rules keep working.

### 2. The rules document

One JSON document, capped by Reactor at 100 KB (Shopify's `json` metafield
limit is 128 KB).

```json
{
  "v": 1,
  "published": "2026-10-01T10:00:00Z",
  "currency": "GBP",
  "prices_include_tax": false,
  "tz": "Europe/London",
  "upgrades": [
    {
      "id": "u1",
      "keys": ["chauvet|gobozap", "chauvet dj|gobo zap"],
      "headline": "Time for a brighter projector?",
      "body": "Your Chauvet GoboZap is an entry-level unit. The 20 Watt LED is brighter and built for daily use.",
      "product": {"id": "8856159682856", "variant": "47481916653864",
                  "title": "Projected Image 20 Watt LED Gobo Projector",
                  "image": "https://cdn.shopify.com/...", "price": "335.00",
                  "price_after": "284.75"},
      "code": "K7Q2M9TX", "off": "15%", "ends": "2026-12-31"
    }
  ],
  "warranties": {
    "8856159682856": {
      "skus": ["P220"],
      "title": "Projected Image 20 Watt LED Gobo Projector",
      "standard_years": 1,
      "lengths": [{"years": 1, "variant": "4812...", "price": "29.00"},
                  {"years": 2, "variant": "4812...", "price": "49.00"}]
    }
  },
  "warranty_window_days": 30,
  "terms_url": "https://..."
}
```

Product ids are the bare digits (the extension strips `gid://shopify/Product/`
before any lookup). A field an older extension does not know is ignored, never
fatal. Keys are made by the tidy in section 6.

### 3. The extension ("Upsell offers")

- **Files.** `extensions/upsell-offers/`, `type = "ui_extension"`,
  api_version the current stable when built (2026-10 from 2026-10-01
  17:00 UTC), Preact and `s-*`. Two targets, each with its own entry file, as
  Shopify requires: `purchase.thank-you.block.render` →
  `./src/ThankYou.jsx`, `customer-account.order-status.block.render` →
  `./src/OrderStatus.jsx`. Each entry reads its page's order data and calls
  `./src/offers.js`, which holds the tidy, the matching, the card choice and
  the cards. `offers.js` has no imports, so the tests load it with bare node.
- **Metafields.** `[[extensions.metafields]]` `$app` / `upsell` (shop) and
  `$app` / `warranty` (order). The order entry exists only on the order status
  page; the thank-you page has no order metafields.
- **Shown to whom.** Nothing renders when: the order's currency
  (`shopify.cost.totalAmount`) differs from `currency`; the buyer is a company
  (`shopify.buyerIdentity.purchasingCompany`); the rules are missing or
  unreadable; on the order status page, the order is cancelled, or its
  processed date or metafields are undefined (the signed-out view).
- **Upgrade card.** The first upgrade, in the order the Upsell page lists
  them, whose key equals any line's tidied `maker|model`, while today
  (Europe/London) is on or before its `ends`. No upgrade card when the order
  already contains the recommended product or any product in `warranties`.
  Shows the price before and after the code.
- **Warranty card.** The eligible line (product id or SKU in `warranties`)
  with the highest unit price, ties to the first line; the link quantity is
  that line's quantity. Shown while the order is inside
  `warranty_window_days` and, on the order status page, while that product id
  is not in the order's `$app` / `warranty` list. Lengths are an
  `s-choice-list` labelled "Warranty length" with nothing chosen; the button
  says "Choose a length first" until one is.
- **Button.** `https://<shop>/cart/<variant>:<qty>?discount=<code>&attributes[reactor_offer]=<id>&attributes[reactor_after]=<covered order id>`
  (warranty links carry no discount). The covered order id is the digits of
  `shopify.orderConfirmation.order.id` on the thank-you page and of
  `shopify.order.id` on the order status page (the thank-you page has no order
  name). Every value is `encodeURIComponent`-encoded. Opens a new checkout in
  a new tab.
- **Shopify's offer rules.** Title, image and price as the storefront shows
  them (with "+ VAT" when `prices_include_tax` is false); no timers; nothing
  pre-ticked; at most two cards.
- **Accessibility.** Each card is an `s-section` with a heading; buttons carry
  an accessibility label naming the product, length and price and that they
  open a new checkout; images use the product title as alt text; checked with
  keyboard only and at 200% zoom.
- **Size.** Target about 10 KB against the 64 KB compressed limit.

### 4. The Upsell page

Admins only, as the Team page is: routes under `/api/upsell` on `_OPEN_API`,
each opening with `_guard(request, min_level=ROLE_LEVELS['admin'])`, every
change recorded with `_track`; the nav button hidden below admin; view
`upsell` added to `APP_VIEWS` with a `view-upsell` section and an
`upsell-content` root, and to `LAYOUT_VIEWS`; an admin-only section in the
guide.

- **Upgrade offers.** "Your customers' fixtures": fixtures named on gobo
  orders that resolve to a size-list row, ranked by customers, with the last
  order date. "Mark as poor quality" marks a size-list row (every model in a
  multi-model cell with it) and adds an offer; refused for a model that is one
  of the shop's own projectors with warranties on. A size list search adds a
  model nobody has ordered for yet. Each offer row: recommended projector
  (only active Projector products on sale on the Online Store; drafts listed
  greyed with the reason), percentage or pounds off, optional end date, code
  (suggested as a random 8-character code, editable, with "Replace code"),
  headline and one line of copy, on or off, customers reached (orders placed
  through the online checkout; orders on account or marked paid by staff
  counted apart, as reachable only on the order status page), and an
  expandable "spellings matched" list. A mark whose row disappears after a
  size-list upload is flagged.
- **Warranties.** One row per projector model: its standard guarantee in
  years; 1, 2 and 3 year lengths, each on or off with a price; the SKUs its
  quoted lines use; a terms link; the offer window in days.
- **Preview and publish.** A preview of each card drawn like the thank-you
  page. "Publish to Shopify" lists exactly what it will do, then does it on
  confirmation. The header says whether Shopify has the latest rules;
  unpublished edits are marked. Until Shopify has granted every permission the
  page needs, Publish is replaced by "Waiting for Shopify permission".
- **Results.** Per offer: sales through the card (`reactor_offer` present) and
  sales with the code typed by hand (shown apart, as a possible leak), each
  order counted once, revenue after refunds, last sale. Warranties: projector
  orders that went on to buy one, revenue after refunds, and "Needs a look"
  (section 7). A note that views are not counted.

UI copy follows the house rules: British English, no em or en dashes, never
setting or environment variable names, never the words Railway or gizmo.

### 5. The Shopify side

- **Discount codes.** One per upgrade offer (`discountCodeBasicCreate` /
  `discountCodeBasicUpdate`): only the recommended projector, percentage or
  fixed amount, once per customer, optional end date, combines with nothing.
  Turning an offer off ends its code. Needs `write_discounts`.
- **Warranty products.** One per projector model, product type `Warranty`,
  a variant per length with SKU prefix `WTY-`, each variant
  `inventoryItem: {requiresShipping: false, tracked: false}`, created and kept
  in step with `productSet`. Status `UNLISTED` (hidden from search,
  collections, recommendations and the sitemap, still sellable by link) and on
  sale on the Online Store channel (`publishablePublish`), which a cart link
  needs. Titles never contain "projector" or "gobo" (for example "Extended
  warranty, 20 Watt LED"), so the forecast's title fallback cannot file them
  as projectors. Kept, never deleted and remade. Taxable or not per the answer
  to decision D below. Needs `write_products`, and `write_publications` unless
  decision A says otherwise.
- **The rules document.** `metafieldsSet` on the shop, `$app` / `upsell`,
  `json`. Before its first write, Publish reads
  `currentAppInstallation { app { apiKey } }` and refuses, with the reason,
  unless it equals the client id in `shopify.app.toml`, so the rules land
  where the extension reads them. Whether the shop metafield needs a scope of
  its own is confirmed while building.
- **Server side.** New writers in server.py (codes create, update and end;
  warranty product create and update, and publish; shop and order
  `metafieldsSet`), handed to `copilot.add_routes` as keywords and never added
  to `COPILOT_TOOLS`. Each returns `{ok, reason, detail}` and checks whether a
  lost create landed before retrying. `REQUIRED_WRITE_SCOPES` gains the new
  scopes with plain descriptions, and the scopes test's must-keep list gains
  them.
- **Release (Cameron's).** `shopify app deploy --no-release`, read the listed
  changes (they include every extension and app setting changed since the last
  deploy, at least the print extensions' 4 x 4 change from 125fcfa, and the
  earlier scope trim, privacy webhooks and rename if those were never
  released), release when the bench is quiet, approve the new permissions on
  the store, then add the "Upsell offers" block in the checkout and accounts
  editor (Settings > Checkout > Customize), once on the Thank you page and
  once on the Order status page. Reactor's server side ships with a normal
  push and waits for the permissions.

### 6. One tidy for fixtures, in two places

The extension reads `CartLine.attributes` (`{key, value}`); Reactor reads REST
`properties` (`{name, value}`). Both must produce the same key:

1. `norm(s)`: trim, lower-case, every run of whitespace to one space
   (`_norm_key`).
2. `prop(n)`: the value of the first attribute whose `norm(key)` equals
   `norm(n)`, trimmed; an empty first match gives '' (`_item_prop`).
3. `stripPrice(v)`: trim, then repeatedly remove
   `[\s\-|,·]*[\(\[]?\s*[+-]?\s*[£$€]\s*\d[\d,]*(?:\.\d+)?\s*[\)\]]?\s*$` and trim
   until nothing changes (`_PRICE_SUFFIX_RE`, `_strip_price`).
4. `maker = stripPrice(prop("Manufacturer"))`.
5. `model = prop("Model")` if non-empty; otherwise, walking attributes in
   order and skipping empty values, the first whose `norm(key)` ends in
   " models" or " model" and starts with `norm(maker)` (maker non-empty), else
   the first such attribute for any maker (`_item_model`). Then `stripPrice`.
6. `key = norm(maker) + "|" + norm(model)`.

Python and JavaScript differ on non-ASCII digits and some whitespace
characters; the parity test covers them.

**Which spellings become keys.** A spelling counts when its
`(norm(maker), norm(model))` is not in the size list's not-a-gobo rulings, and
`_gobo_lookup(maker, model)` resolves it with no review reason to a row marked
poor quality; a value naming several models counts only when every part
resolves to that row. Keys are built at Publish from a full order-history read
(`_paginate_orders`), and kept current by a new `_upsell_tick(registry)`
called from `_scheduler_loop`, at most hourly (a stamp in watch.json) and only
when Shopify is up.

**Automatic versus manual.** The tick republishes only machine-kept fields
(keys, prices, titles, images, availability), taken from the last published
offers. Any change Cameron makes needs Publish.

### 7. How it fits the rest of Reactor

- **Warranty lines are never made or sent.** A line with SKU prefix `WTY-` is
  treated like a shipping charge everywhere, with no product lookup: labels,
  `_usage_lines` (day sheet and stock app), customs lines and goods value
  (`_customs_items`, `_order_goods_value`), weight (`_order_weight_kg`) and
  missing-production checks. An order made only of warranty lines never shows
  in any queue in `run_production_labels`, and `_release_tags` refuses it with
  a plain reason (covering printing, the Add to queue strip and the background
  release). Once paid, Reactor fulfils it through the existing fulfilment
  writer with `notify_customer=False` (fulfillmentCreate on each open
  fulfillment order, under the existing
  `write_merchant_managed_fulfillment_orders`) and moves its tags to Complete.
- **Warranty register.** Filled from the orders webhook in a task run after
  the reply, like `_crm_link_order_soon`, reading `note_attributes` and
  `discount_codes`; the hourly tick backfills anything missed. Before
  recording a sale Reactor checks that `reactor_after` names an order that has
  the same customer email, still has an unrefunded, uncancelled line of the
  covered projector with a unit not yet covered, and was placed no more than
  `warranty_window_days` before. A sale that fails a check or has no
  `reactor_after` is recorded as "Needs a look" with the reason: no cover is
  shown and no metafield set, and an admin refunds or accepts it on the Upsell
  page. Cover starts the day after the standard guarantee ends, counted from
  the covered order's fulfilment date (its order date while unfulfilled), and
  ends the chosen number of years later.
- **Refunds.** A warranty order refunded or cancelled voids its cover and
  removes its product id from the covered order's `$app` / `warranty` list. A
  covered order cancelled, or its covered line refunded to zero, marks the
  cover "Covered item returned" for an admin to refund the warranty.
- **Covered-order flag.** The covered order's `$app` / `warranty` metafield
  holds the list of covered product ids (under the existing `write_orders`),
  so the order status page stops offering each one once bought.
- **Where staff see cover.** `/api/customer-history` (the Customers tab and
  the Shopify card on a linked CRM contact) and beside the covered order in
  the inbox's order list: "Covered by a 2-year warranty until ...".
- **Stores.** `UPSELL_PATH` (offers, warranty prices, the Shopify ids Reactor
  made, a fingerprint of the last published rules) and `WARRANTY_PATH` (the
  register): each with a /data default, a `_load_x`/`_write_x` pair over the
  json store helpers, a test-harness env line, carried by the backup, and
  entered in docs/ENVIRONMENT.md. The register records a contract Reactor must
  honour, so `_redact_customer` keeps it with the erasure note until the cover
  ends and erases it afterwards; `_redact_scope` shows it in the erasure
  preview; both paths join `_redact_shop`'s store list.
- **Accounts.** Not in this build. Warranty sales reach Xero through the
  separate connector, which puts every line on one sales account and marks
  untaxed lines zero-rated. A warranty account code (and an exempt tax type if
  decision D says insurance) needs work in that repo: product type in its
  order read, an account per product type in the invoice and credit-note
  mappers, and a setting Reactor's Xero sync page can set.
- **Forecast.** Warranties are their own product type (and titles avoid
  "projector" and "gobo"), so projector sales are not distorted.

### 8. When things go wrong

- **Publish order.** Additions (codes, products, variants, publication) go
  before the rules document; removals (ending a code, archiving a variant)
  only after the new rules document is written. Any failure leaves the last
  published rules in place and says what failed. Repeating is safe: Reactor
  finds what it made before (ids kept in `UPSELL_PATH`) before making
  anything.
- **Size.** A rules document over 100 KB is refused with the reason; an
  automatic refresh that would go over keeps the last rules and raises an
  alert on the Upsell page and in the alert email.
- **Drift (in the hourly tick).** Each code and warranty product still exists
  and is on sale; each recommended projector is active, on sale on the Online
  Store and available; card prices, titles and images match the store. A
  change to any of those is republished automatically. An offer whose
  projector is unavailable is dropped from the rules and flagged "Projector
  unavailable". An edit made directly in Shopify to a code or warranty product
  is flagged "changed in Shopify" with a choice to keep it or put Reactor's
  back.
- **Before permissions.** Until `shopify_granted_scopes()` shows every new
  scope, the tick, the register and warranty fulfilment do not run, and the
  page says why.
- **Shopper side.** Never an error: anything unexpected renders nothing.
- **Shared codes.** Once per customer, only the recommended projector, combine
  with nothing, until the end date; typed-by-hand uses shown apart; "Replace
  code" ends the old one.

### 9. Tests

- **Reactor.** Fake discount, product and metafield writers injected into
  copilot, as the fulfilment tests do: building the rules document (keys only
  from clean resolutions, excludes, multi-model values, size guard, `v`);
  publish order (additions before, removals after) and repeat safety; drift;
  automatic refresh limited to machine-kept fields; the register's checks and
  "Needs a look"; refunds voiding cover; warranty lines out of labels, day
  sheet, customs, weight and queues, warranty-only orders refused release,
  fulfilled without notice and moved to Complete; results split card and
  typed; the stores in the backup and in erasure; the scopes lists.
- **Extension.** `offers.js` run with bare node from `test_frontend.py`
  (skipping when node is absent, as the other node tests do): card choice
  rules, currency and company guards, GID stripping, the window and `ends`, the
  cancelled and signed-out order status views. A parity test runs a spelling
  list checked into `tests/` (awkward cases written as escapes: prices,
  per-maker dropdowns, prefix matches, empty first properties, spacing, case,
  non-ASCII digits) through both tidies and fails on any difference. The
  bundle-size check (esbuild, 64 KB) runs in `make check` when node_modules is
  present; CI adds `npm ci` if it is to run there. A simulated render of both
  entries, new, like the one used to check the print extensions.
- **Page.** Tests in the style of `tests/test_frontend.py`, and rig
  screenshots at desktop and phone widths.
- **House rules.** Every commit touching copilot.py or index.html adds a
  data/changelog.json note (no dashes; no API, webhook or JSON words;
  `tab: "upsell"`), saying offers appear only once the block is placed.
  `make check` passes before each push.
- **Trial mode.** Publish with `"trial": true` puts only the key
  `reactor trial|trial` and one staff test warranty product in the rules. A
  staff order naming Manufacturer "Reactor trial", Model "trial" checks both
  cards, both pages, the order metafield hiding the card, a rules document
  near the 100 KB cap, and the whole path to Results; both orders are then
  refunded and left out of Results.

## Decisions still open (Cameron)

A. **Publishing warranty products to the Online Store.** A cart link can only
   sell a product on sale in the Online Store. Either the app regains
   `write_publications` (dropped on purpose in the September scope trim) and
   Reactor puts each warranty product on sale itself, or Reactor creates them
   and you put each one on sale by hand in Shopify, with Reactor checking
   before it offers it.

B. **Reach.** About 80% of orders are completed drafts from the Quote Engine
   that never pass through checkout, so their buyers never see a thank-you
   page, and the order status page reaches them only from the order email's
   link while it is live, and only on the new customer accounts. The design
   stands for online orders, but most projector buyers would not see a
   warranty offer. Options: accept this for the first version; or add the
   email channel (a warranty offer sent by Reactor after a projector order)
   now rather than later.

C. **Standard guarantee.** "Extra years" needs each projector model's standard
   guarantee, and when it starts (order, dispatch or delivery). The design
   assumes the fulfilment date.

D. **What the warranty is (not legal advice).** Your own promise to repair or
   replace (a service contract, usually standard-rated for VAT) or backed by
   an insurer (insurance: Financial Conduct Authority rules, VAT-exempt,
   Insurance Premium Tax). For consumer sales of domestic electrical goods,
   the 2005 Extended Warranties Order may also require a warranty's price and
   duration next to the product's price on the product page, which would make
   the product page block a launch requirement, and gives cancellation rights
   the window and register must honour. Publish refuses warranties until this
   answer and a Xero account code are recorded on the Upsell page. For your
   accountant or adviser.

Also to check before launch: the store's customer accounts version
(`shop { customerAccountsV2 { customerAccountsVersion } }`, read only); the
shop metafield scope; the app installation check in section 5.

## Not in this version

Product page and cart offers (unless decision D requires them), emails (unless
decision B brings them in), single-use codes, view counting, the Xero warranty
account, and any in-checkout or post-purchase offer (Plus only for a custom
app). Each can be added later without changing the rules document's shape.
