# The leftovers go home

**Approved 21 Oct 2026.** Stage 4, piece 13 of the 14 October engineering
audit. Cameron approved all three parts. Nothing anyone sees changes.

## Why

Measured on piece 12's branch (copilot.py 2,515 lines): about 675 lines left
in `copilot.py` belong to modules that already moved, and the move tool can
only write new files. By where they belong:

- **privacy**: the shop erasure still owed after an uninstall, the requests
  held for an admin, the backup step that keeps live privacy records on
  restore, the webhook signature check (12 names, 275 lines);
- **team**: team colours, first-run setup and its code, the account as the
  Team screen shows it, who may edit the Size list or send mail, the sign-in
  helpers (15 names, 116 lines);
- **work**: the session length in words, day starts; **mail**: its sign-in
  redirect; **dispatch**: its EORI rate limit (`t_what_dispatch_borrows`
  names two of them);
- **the order book**: the order totals (what counts as a sale, its revenue,
  the month axis, the last 28 days), which it already reads through `core.`;
- **chat**: the tool list, its dispatcher, the AI usage summary, the page
  context (9 names, 114 lines);
- **the floor**: `_ok` (a Shopify read that came back with data) to
  `gizmo/shopify.py`; the London date helpers, read by nine modules, to a new
  floor module `gizmo/clock.py`;
- **gate**: the server secret's check; **status**: the data volume warning
  and the token vault's re-encryption.

## What changes

1. **The tool adds to a module moved earlier**: an area marked `existing`
   writes into its file. The moved statements go in before the module's last
   imports, with the imports they need; inside them, the module's own name is
   dropped (`orderbook._orders_snapshot` becomes `_orders_snapshot`), and the
   module's own `core.NAME` reads of them become bare. Its toy test first.
2. **The leftovers rejoin their areas**: privacy, team, work, mail, dispatch.
3. **The shared helpers go to their owners**: the order book, chat, the
   floor (`shopify`, and the new `clock`), gate, status.

A pure move: nothing declared. A release note, "The last of the leftovers
home": "Code that earlier moves left behind now lives with the rest of its
area, so a change elsewhere cannot upset it. Nothing looks different."

## Not in this piece

The settings block and the AI effort setting, `_spawn_bg` (a frozen print
route reads it), the print routes' font and logo routes, the stock bridge,
the Products tab and customer history, the chat routes.
