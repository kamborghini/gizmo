# The AI's instructions, SEO and keywords, and the overview and customer reports

**Approved 21 Oct 2026.** Stage 4, piece 9 of the 14 October engineering
audit. Cameron approved all three parts. Nothing anyone sees changes.

## Why

Measured with `tools/move_area.py` dry runs on main 7c01dc7 (copilot.py
7,993 lines):

- **The AI's instructions** (the writing style, the chat's system prompt, the
  report prompt, the keyword prompt, the `present_response` tool): 5
  statements, 190 lines, reading nothing but the writing style. Three of them
  are built from the writing style as `copilot.py` loads, which is why the
  chat's system prompt could not leave in piece 8 and why no report could.
- **SEO and keywords** (the SEO knowledge, reading the store's own site, the
  guarded fetch of outside pages and their keywords, the SEO and Google data
  tools the chat is given, the SEO audit, keywords, the keyword scan, the
  product audit): 27 statements, 718 lines, 3 routes. Store knowledge already
  reads the site through `core.`.
- **The overview and customer reports** (the analysis cache and the changes
  since a report's last run, the overview's figures and trends, customers and
  retention, the reorder radar, sector tags): 21 statements, 626 lines, 5
  routes. `reports` is a local name in a dispatch route, so the module is read
  as `analytics`.
- A hand check found three names that would stay though only the moving code
  reads them: `_money`, `_ret` and `_report_answer`. The dry run lists what an
  area borrows, not what is left behind for it (how `_add_skill` was missed in
  piece 8).

## What changes

1. **The instructions on the floor**: `gizmo/prompts.py` (floor: it imports
   nothing above it) holds the five and `_report_answer`, which reads only the
   tool's name. The chat loop and every report read `prompts.NAME`.
2. **SEO and keywords out**: `gizmo/seo.py` and `gizmo/routes/seo.py`
   (`/api/seo`, `/api/keywords`, `/api/keyword-scan`). The product page's
   route stays: the tool gathers routes by path prefix, and `/api/product`
   would take `/api/products` with it.
3. **The overview and customer reports out**: `gizmo/analytics.py` (read as
   `analytics`) with `_money` and `_ret`, and `gizmo/routes/analytics.py`
   (`/api/overview`, `/api/cache`, `/api/reorder-radar`, `/api/customers`,
   `/api/customer-tags`).

And the move tool's dry run lists every name that stays though only what
moves reads it (its toy test first).

A pure move: nothing declared. A release note, "Reports on their own": "The
overview, customer, SEO and keyword reports, and the instructions the
assistant works from, now each live on their own, so a change elsewhere cannot
upset them. Nothing looks different."

## Not in this piece

The product page's route and the products list, the shared answer helper
`_coerce_structured` (it reads skills), the order sums (`_order_counts` and
the rest, read by the order book too), impact tracking, backup, the
scheduler, the release notes, reconciliation, the Xero connector, the chase
desk, page rendering, the stock bridge, the frozen print routes.
