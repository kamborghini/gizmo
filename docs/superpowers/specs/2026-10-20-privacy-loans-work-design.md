# Customer-data erasure, loans, work sessions, and routes following their areas

**Approved 20 Oct 2026.** Stage 4, piece 7 of the 14 October engineering
audit. Cameron approved all three parts. Nothing anyone sees changes.

## Why

Measured with `tools/move_area.py` dry runs on main 6994854:

- **Customer-data erasure** (the scrubber, the keys and matching that decide
  what belongs to one person, the sweep, shop and customer redaction, the
  requests held for an admin, the privacy log): 66 statements and 2 routes,
  nothing stopping it; the privacy log's loader, the held-request helpers and
  `_PRIVACY_ALERT` showed in what it borrows and join it.
- **Loans** (16 statements, 1 route) and **work sessions** (13, 5 routes),
  each with a copy held in memory and loaders the prefix misses.
- About 15 routes of areas already moved (production, the Size list, the
  order book) still sit in `add_routes`. The two frozen print routes stay
  where they are; their bytes are pinned.

## What changes

1. **Erasure out**: `gizmo/privacy.py` and `gizmo/routes/privacy.py` (the
   privacy route and Shopify's privacy webhook). A proven pure move; the
   redaction and erasure tests run unchanged.
2. **Loans and work sessions out**: `gizmo/loans.py`, `gizmo/work.py` and
   their routes, each with its own memory drop (declared); copilot.py's
   `_let_go_in_memory`, left holding nothing, goes.
3. **The moved areas' routes follow them**: `gizmo/routes/production.py`,
   `gizmo/routes/size_list.py`, `gizmo/routes/orderbook.py`, gathered where
   each group's first route stood. The move tool learns a route group whose
   area moved in an earlier piece (its toy test first).

A release note: "Privacy, loans and work sessions on their own": "Erasing a
customer's data, the loan register and work sessions now each live on their
own, so a change elsewhere cannot upset them. Nothing looks different."

## Not in this piece

The release notes, skills, the page builder, the scheduler, chat, the stock
bridge (the stock merge project works near it), the Xero connector,
reconciliation's routes, the frozen print routes.
