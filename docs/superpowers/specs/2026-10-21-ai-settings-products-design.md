# The AI settings, the Products tab and customer history

**Approved 21 Oct 2026.** Stage 4, piece 14 of the 14 October engineering
audit, the last movable part of `copilot.py`. Cameron approved all three
parts. Nothing anyone sees changes.

## Why

Measured on piece 13's branch (copilot.py 1,661 lines):

- **The AI's effort settings** (`ANTHROPIC_EFFORT`, `ANTHROPIC_EFFORT_DEEP`,
  the thinking mode and `_effort_for`, which reads only the two efforts) are
  read through `core.` by seven modules; they belong with the AI client on the
  floor. **The chat's message limits** are read only by the chat routes.
- **The Products tab** (the product list, the whole-catalogue read and their
  two settings) and its two routes, which the tool could not name before it
  learned exact paths (`/api/product` is a prefix of `/api/products`). The list
  sat in the stock bridge's section but reads nothing of the bridge's.
  `products` is a local name in several functions, so it is read as `catalog`.
  The currency signs go to the money formatter in analytics.
- **Customer history** (`/api/customer-history`, the "ordered before" look-up
  on a label) is an order book read, but the tool writes route modules new; and
  it has no test of its own.

## What changes

1. **The AI settings to their owners**: the efforts, the thinking mode and
   `_effort_for` to `gizmo/ai.py`; the chat's limits to `gizmo/chat.py`.
2. **The Products tab out**: `gizmo/products.py` (read as `catalog`) with
   `/api/products` and `/api/product` in `gizmo/routes/products.py`; the
   currency signs to `gizmo/analytics.py`.
3. **The tool adds routes to a route module moved earlier**: a route group
   marked `existing` adds its routes to that module's `register()` (its toy
   test first). Customer history joins the order book's routes, pinned first
   by a route test.

A pure move: nothing declared. A release note, "The AI settings and the
Products tab on their own": "The assistant's effort settings, the Products
tab and a label's order history now each live with the rest of their area, so
a change elsewhere cannot upset them. Nothing looks different."

## Not in this piece

The shop settings (tests patch `SHOPIFY_STORE` through `copilot.py`, the frozen
print routes read the secret and the base address), the stock bridge and its
routes, the frozen print routes and their font, logo and CORS helpers,
`_spawn_bg`, the chat and usage routes (they read the tool list `add_routes`
builds), `STORE_CONTEXT_CAP` (read by nothing; stage 6).
