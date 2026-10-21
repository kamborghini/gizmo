# Every write route checks its body

**Approved 21 Oct 2026** under Cameron's standing yes for the evening ("assume
I approve anything you need"). Stage 5, pieces 2 to 4 of the 14 October
engineering audit (B1: request models on write routes). Builds on piece 1
(`docs/superpowers/specs/2026-10-21-bodies-and-errors-design.md`, #61), which
added `gizmo/bodies.py`, `gate._guard(model=...)` and models on 16 routes.

## Why

After piece 1, `t_write_routes_check_their_bodies` lists 74 POST routes that
read fields from their body with no model. Each still checks its own fields by
hand, and a field of the wrong kind can still break the route or be kept as
nonsense. The page never sends one; a stray script, an old tab or a typo in the
browser's console could.

## What changes

Each of 70 routes names every field it reads in a model beside it, in three
pull requests, one area each:

1. **Accounts and the workspace** (27 routes): sign-in and its codes, the team
   register, the profile, the work clock's report, alerts and the schedule, the
   chat, its stream and the usage panel, the reports' reads (customers,
   customer history, the keyword scan, products), reconciliation's discrepancy
   and disconnect, the Xero connector, restore, the forecast workbook and the
   forecast's results hook, and order edits.
2. **The desks** (26 routes): the CRM's deals, leads, stages and import; every
   Inbox route; Files.
3. **Shipping and production** (17 routes): the dispatch desk, custom
   shipments, the EORI check, the Size list's check, models and upload, and the
   production labels feed.

The kinds are piece 1's, with one more: a list of sets of fields (the chat's
messages, where an item that is not one broke the route). The inventory found
that a JSON number past any float made the number kinds raise rather than
refuse, which would turn that request into a server error at the door; such a
number is now refused. A model accepts every value every caller sends today,
proven from the callers themselves (the page's `static/src/js`, the admin
extensions, the forecast worker), and refuses an object or a list where a
scalar belongs, and the like. Where no kind fits what callers send, the field
is left out of the model and the reason is written beside it. The doors that
do not yet pass a model on learn to: `team._auth_guard` (it reads the body
itself, before any session exists) and `team._team_guard`. The forecast's
results hook checks after its own token check, as the Size list rule does.

`UNCHECKED_BODIES` shrinks to the four routes deliberately left alone, each
with its reason in the test: the signed print route (frozen), Shopify's privacy
webhook (Shopify shapes that body, and refusing it would break the compliance
path), and the stock bridge's two routes (hands off).

One release note per pull request, dated the merge day: "More requests checked
at the door" (the area named). Nothing looks different.

## Not in this piece

What a route does with a body it accepts; the contents of lists and sets of
fields; the four routes above; the error triage's next step (the 41 handlers
that fall back to a value without a word), which is its own piece.
