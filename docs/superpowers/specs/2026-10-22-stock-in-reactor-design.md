# Stock in Reactor: the stock app folded in, with nothing lost

**Draft for approval, 22 Oct 2026.** Nothing is built until Cameron approves
this document. It covers folding the separate stock app (repository `zeta`)
into Reactor as a Stock tab, moving every record across, and switching the
stock app off.

## Why

In Cameron's words: going from two apps rather than just having one "seems
stupid". Two people (Cameron and one colleague) use the stock app to track
glass stock and place orders with suppliers. A great deal is in it, and it
"needs to remain the same and migrate over without data loss".

Reactor already talks to the stock app: each production day, the glass that
was used is sent across and booked against stock. Once stock lives in Reactor,
that becomes an ordinary call inside one app.

## Goals

1. **One app.** Everything the stock app does is done in a Stock tab in
   Reactor, by the same two people, and the stock app is switched off.
2. **Nothing lost.** Every record in the stock app's database arrives intact:
   every item with its own number, every change ever recorded and who made it,
   every count history snapshot, every closed quarter, every alert and its
   dismissed state, every supplier's contact details, and every booking and
   ruling Reactor's link has made. The move is proven, not assumed.
3. **Everything still works.** Every capability in the checklist below works
   after the move, on desktop and on a phone.
4. **The flaws are fixed on the way** (Cameron: "fix the flaws along the
   way"), listed below.

## Non-goals

- No new stock features beyond the flaw fixes. A kept list of placed orders
  is counted as a fix (today an order leaves no record but a number).
- No change to the Quote Engine, which stays hands off, or to the production
  labels and day sheets, which stay frozen.
- No database. Reactor deliberately keeps its data in files on its volume
  (`docs/ARCHITECTURE.md`, "JSON stores, not a database"), and stock follows
  that rule.

## Anti-goals: what would make this a failure even if it worked

- A printed shelf label that no longer scans. Labels carry the item's own
  number ("CL" and the number) where an item has no barcode of its own, so
  every item must keep its exact number.
- A history entry rewritten, merged or dropped. The history of who changed
  what is not only a log: undoing a delivery and refusing an invoice received
  twice both read it back.
- Glass used in production booked twice, or not at all, across the switch.
- A count or edit made by one person silently lost by another person's save.

## What exists today

The stock app is FastAPI with SQLAlchemy, Postgres in production. Its
complete data is only in that production database: the SQLite copy on
Cameron's machine is from July and has no record of Reactor's bookings.

Its screens are Dashboard, Inventory (with a workshop mode for counting on a
phone and a stock-take), Reorder (with purchase orders), Suppliers, Trends
(with Compare), Activity, Settings, and an item sheet with each item's own
history. The read-only survey on 19 Oct 2026 listed every screen, route,
table and behaviour; the capability checklist below is taken from it.

## Decided with Cameron

- **Who and how:** Cameron and one colleague. Both count stock at a desk or on
  a phone, whichever is handier.
- **Scanning:** shelf labels are scanned only on a phone; at a desk the item
  is found in the list by hand.
- **Phone scanning is proven inside the Shopify app.** A test window shipped
  on 20 Oct (Settings, Camera test, PR #40) showed Reactor opening the phone's
  camera itself inside the Shopify app, and the phone reading a shelf label.
  So scanning keeps today's behaviour: the camera stays open and every label
  it sees adds one.
- **Access:** both already have their own Reactor accounts, reached through a
  shared Shopify login. Each person's own Reactor account is what records who
  did what.
- **Flaws:** fixed on the way, not carried over.
- **Timing:** no date is fixed. The switch needs a short pause in stock
  editing, chosen together when the build is ready.
- **No way back by converter** (22 Oct). There is no reverse converter.
  Switching back to the stock app is possible only in the first few days,
  re-entering by hand anything done in Reactor since; after that the old app
  is kept untouched as a read-only archive until the next quarter close.

## The design

### 1. Where it lives

- **A new area**, in the shape every other area now has: the rules in
  `gizmo/stock.py`, the routes in `gizmo/routes/stock.py` behind the one door
  (`_guard`, a body model for every write), and the page in its own sections,
  `static/src/js/stock*.js` and a stylesheet section, through the existing
  parts (windows, buttons, fields, rows, tables, panels).
- **The link moves in.** Reactor's stock bridge, which `copilot.py` still
  holds and which `docs/ARCHITECTURE.md` keeps "until the stock merge project
  moves it", moves into the stock area. Its sends to the stock app become calls
  into the stock area's own functions. The queue's rules are kept: the latest
  intent per order wins, one lock per order, and a booking applied twice
  changes nothing.
- **A Stock tab** in `TAB_KEYS`, **opt-in** like Forecast and Reconciliation,
  granted to Cameron and the colleague at the switch. Its routes go in
  `_TAB_ROUTES`. *(My call: opt-in keeps it out of other people's sidebars.)*
- **The camera test comes out.** Its window, its Settings row, its styles and
  its two tests are deleted when the Stock tab's scanning is in.

### 2. The data

Stores on the volume, each through the one writer, with a test-harness path:

| Today (table) | In Reactor | Notes |
|---|---|---|
| `items` | `stock_items.json` | Every column, every item under its **own id**; the next id carries on from the old sequence. |
| `audit_log` | `stock_history.jsonl` | Append-only, never rewritten. Every old row keeps its time, person, action, item, field, old and new values and detail, word for word. Read through indexes built in memory (by item, by invoice number, by action). |
| `snapshots`, `snapshot_items` | `stock_snapshots/<year>-<month>.jsonl` | One line per snapshot with its items; one file per month keeps each file small for Reactor's backups. |
| `periods` (quarters) | `stock_periods.json` | Closed quarters with their closing figures and full closing list, unchanged. |
| `alerts` | `stock_alerts.json` | With dismissed state and who dismissed; capped, with what is trimmed archived first. |
| `supplier_contacts` | `stock_suppliers.json` | Written owner-only, as it holds contact details. |
| `meta` | `stock_settings.json` | Low-stock days, exchange rates, last snapshot, last quarter close, each person's "since you were last here" acknowledgement. |
| `gizmo_bookings`, `gizmo_usage_sheets`, `gizmo_parked`, `gizmo_aliases` | `stock_bridge.json` | Per-order bookings, per-day sheets, parked lines, and rulings (by item id). |
| `backups` | `stock_backups/` | See section 8. |
| `users` | not carried as logins | See below. |
| (new) placed orders | `stock_orders.json` | The flaw fix: each placed order kept, linked to what is later received. |

- **People.** The stock app's own logins are not carried over: both people
  already have Reactor accounts. At the switch, each old username is mapped to
  a Reactor account. Old history entries keep the old username exactly as
  written, shown beside the mapped person's name; everything new is recorded
  under the Reactor account.
- **A change and its history line go together.** No item changes without its
  history line, and no history line describes a change that did not happen,
  across a crash or a restart. How is left to the builder; the test is a crash
  between the two writes.
- **Exactly the same figures.** Stock value, cost of goods used, sell-through,
  dead capital, written-off sunk cost, days to running out and suggested
  reorder levels are computed by the same rules as today, to the penny.

### 3. What must still work: the checklist

Each line is a test of the finished build against the stock app's own
behaviour, on the same data.

- Sign in (through Reactor), see "since you were last here" news and dismiss
  it until something new happens.
- See the top alerts, open the item behind one, dismiss it, jump to all
  alerts.
- Match Reactor's unmatched gobo lines to a stock item, with rulings
  remembered and colour decided per order; read and override the whole
  mapping.
- See the quarter's stock value, cost of goods used, sell-through, dead
  capital and written-off sunk cost; value by category, supplier exposure,
  top items by value, write-offs by category; value restated at today's
  dollar and euro rates with the drift; least cover and dead stock.
- Generate AI insights (health score, findings, actions) and see the last
  result again later.
- Search the stock list by colour, size, supplier, barcode or label code;
  filter by category, projector wattage and active, all or written off;
  grouped or flat; sort the flat list by any column.
- Edit current, used, reorder level, order quantity, unit cost, supplier,
  currency, barcode and the written-off switch inline, with bad numbers
  flagged and an undo after saving.
- Count on a phone in workshop mode with plus and minus (holding repeats);
  counts survive a reload or lost signal, save in one go, record drops as
  usage, and keep the screen awake.
- Scan shelf labels with the phone's camera to tally counts, with a beep and
  a buzz per label (a phone whose web pages cannot vibrate does not buzz,
  exactly as today), and get help when the camera is refused.
- Add an item, including scanning its barcode.
- Import the stock sheet after previewing every change; export the filtered
  list.
- Print shelf labels (Avery J8160) for the filtered items.
- Run a guided stock-take: pause and resume, mark the rest correct, review
  variances with net units and money impact, apply them as usage or as
  corrections.
- Receive one item with an invoice number and date; receive a whole delivery
  from a PDF invoice read by AI or entered by hand, change matches and
  quantities, add lines, create items mid-delivery, choose to update unit
  prices; be stopped from receiving the same invoice twice; get a receipt;
  undo a whole delivery.
- See what needs reordering by supplier with on-order quantities, run-out
  dates and suggested quantities, and the count on the tab; have reorder
  levels proposed from usage and lead times and apply them in bulk.
- Draft a purchase order with editable quantities and live totals in the
  supplier's currency and in pounds; mark it ordered with a reference; print
  or save it as PDF; copy it as text; download it; have AI draft a cover note.
- Keep each supplier's email, copy addresses, contact name, delivery time,
  minimum order and message template; edit them all in one go; compose a
  reorder email with what is low, edited, then opened in your own email app.
- See stock value and units over time, an outlook, and a soonest-to-run-out
  forecast.
- Compare any two quarters (live or closed) by headline figures, category
  value and the biggest movers.
- See and rename the current quarter, close it, and see and download closed
  quarters.
- Search the full history of who changed what, and see each item's own
  history.
- Make a backup now, see the nightly ones, download one, and restore one with
  a safety backup taken first.
- Set the low-stock warning days and the exchange rates.

### 4. Flaws fixed on the way

1. Saving one row of the stock list no longer throws away unsaved edits in
   other rows.
2. Editing all suppliers in one go keeps each supplier's delivery time and
   minimum order (it erased them).
3. The dashboard always shows its alerts and the production-matching panel,
   not only when the "since you were last here" news has something new.
4. A restore puts back everything the backup holds (it left reorder levels,
   barcodes and on-order quantities as they were).
5. Export writes the same layout import reads, and the import preview shows
   every field it would change (it hid supplier, currency, cost in the
   supplier's currency, notes and written off).
6. Alerts no longer pile up: a warning about an item is raised once, and
   raised again only when the warning itself changes (a different kind, such
   as low stock becoming out of stock) or the item recovered above its level
   and fell back. Daily production bookings alone never raise it again.
   *(My call.)*
7. Placed orders are kept: supplier, lines, quantities, prices, reference,
   who and when, and what has since been received against each. An on-order
   quantity can be cleared from the page. The converter rebuilds the orders
   already outstanding from the "ordered" history lines, grouped by supplier,
   reference and time; on-order quantities it cannot group show as "ordered
   before the move". A delivery is matched to the oldest open order for that
   item automatically, shown on the receipt and changeable there, so receiving
   gains no extra step. *(My call.)*
8. The outlook covers real days, not snapshot steps; the item sheet shows
   fresh forecasts and lead times; the ring rows say what they do; a scan made
   in the full list on a narrow tablet is never lost to a hidden draft.
9. The wording keeps Reactor's house rules (British English, no dashes, no
   hosting or setting names).

Lowering "current" at a desk stays a correction, not usage, as today; usage is
recorded by workshop counts, stock-takes chosen as "sold or used", and
production bookings. *(My call: the distinction is deliberate in the stock
app; it is stated on the page so nobody is surprised.)*

### 5. The look

The screens are rebuilt with Reactor's parts and design rules, so they look
like the rest of Reactor: panels on a grey page, its brand colours, no pill
shapes. The figures, lists, actions and the order of things on each screen
stay as they are today. The stock app's dark mode is dropped, as Reactor has
none. On a phone, the Stock tab uses Reactor's phone layout; the workshop
counting cards and the scanner keep their size and behaviour.

### 6. Scanning on a phone

Proven on 20 Oct inside the Shopify app: the page opens the rear camera
itself and the browser's own barcode reader reads the labels. Where a phone's
browser has no reader of its own, the page brings one, as the stock app does
today. One label held in view counts once every 1.4 seconds, as today. The
camera is released whenever counting stops or the window closes.

**A second camera test comes first.** Before the scanner is built, the camera
test in Settings is extended and tried on both people's phones inside the
Shopify app: the bundled reader (for a phone without one of its own), the
buzz, and keeping the screen awake while counting. What fails there is
reported before the scanner is built around it. *(My call.)*

### 7. Background work

- **Snapshots keep today's rules**: one at every change (a count, a receipt,
  a production booking, a mapping) and one each night, kept for 30 days, so
  the trend chart, the run-out forecast and "since you were last here" keep
  their figures. *(My call.)*
- **The nightly snapshot** is taken by the first tick of Reactor's scheduler
  after midnight London time, stamped with when it was taken, and recorded in
  the stock store so it runs once a day. After downtime there is one catch-up
  snapshot, not one per missed day, because the state on a missed day cannot
  be rebuilt exactly (receipts and bookings change figures without a history
  line per field). *(My call.)*
- The reorder and stock-out alerts are raised by the snapshot (once, see
  flaw 6).
- Reactor's own catalogue push to the stock app goes; the stock area reads
  the gobo catalogue directly.

### 8. Backups

- Reactor's own backup and restore carry every stock store (they take `.json`
  and `.jsonl`; monthly snapshot files keep each well inside the per-file
  limit).
- The Stock tab keeps its own nightly stock-only backups, with the same
  retention as today, downloadable, with a safety backup taken before any
  restore. Restore is for the owner.
- **What a stock backup holds and a restore puts back:** the stock list with
  every field (today's backups drop some; see flaw 4), the suppliers and the
  settings. A restore never removes history: it writes a history line for
  every field it changes. It keeps the production bookings and usage sheets,
  and re-applies the bookings made after the backup was taken, so glass used
  since is neither forgotten nor counted twice. *(My call.)*
- **The stock app's existing backups** hold only the stock list. They are
  kept as the encrypted files they are, as an archive. If Cameron hands over
  their key, each is decrypted and kept as an older restore point for the
  stock list. *(My call, with the key as Cameron's option.)*

### 9. AI

- **Insights, reading a PDF invoice and drafting a purchase order cover
  note** move across, through Reactor's own AI client, under its spend cap.
- **The chat** gains read-only stock tools (levels, an item's history,
  movements, reorder suggestions), refused for anyone without the Stock tab.
  The chat never changes stock.
- The chat's standing instruction that the shop "carries unlimited stock" is
  narrowed to Shopify products, so it no longer contradicts glass stock
  answers.

### 10. Printing

Shelf labels and purchase orders are new print sheets in Reactor. The frozen
production labels and day sheets are untouched; the page-suite guard that
counts print rules is raised by exactly the new sheets' rules, with Cameron's
OK given by approving this document.

### 11. Moving the data, and the switch

**A converter** (`tools/stock_import.py`, committed; no data ever committed)
reads a copy of the stock app's database and writes Reactor's stock stores,
then proves the result:

- the number of rows in every table equals the number of records written;
- every item's every field is equal, ids included, and every label code
  resolves to its item;
- the history, in order, has the same checksum before and after;
- every snapshot's totals, every closed quarter's closing figures, every
  alert and every bridge record are equal;
- the dashboard's figures, the reorder list and a sample of item histories,
  computed by the stock app and by Reactor from the same data, are equal to
  the penny.

**A rehearsal first.** Cameron provides a copy of the production database (a
Postgres dump or a Railway backup); the converter and every proof run against
it until all pass. The copy stays outside every repository.

**The switch**, on an agreed evening:

1. Both stop editing stock; any unsaved phone counts are saved first.
2. Reactor's queue to the stock app is drained to empty.
3. The stock app stops taking changes (its sync answers "unavailable"; then
   it is scaled down), so nothing can change after the final copy.
4. The final copy is taken; the converter runs; every proof passes.
5. The result is loaded through an owner-only import in Reactor, which shows
   the proof again on arrival.
6. Reactor's link switches to the stock area; the Stock tab is granted to
   both; a few labels are scanned and the dashboard checked against the last
   screen of the stock app.

**Fallback.** The stock app and its database stay switched off but intact
until the next quarter close, with the final copy kept encrypted outside
every repository. Switching back is possible only in the first few days,
re-entering by hand anything done in Reactor since; there is no reverse
converter (decided with Cameron). After that the old app is a read-only
archive until the next quarter close.

**What only Cameron can do:** provide the database copies; hand over the old
backups' key if he wants them restorable; agree the evening with the
colleague; stop the stock app on Railway; map the two old usernames to
Reactor accounts; delete the old app and its database after the fallback
period.

## Constraints

- The repository is public: no stock figures, supplier names or prices, no
  colleague's name, and no database copy in code, tests, documents or commit
  messages. Test data is invented.
- Reactor's house rules: the one door, the one writer, stores with caps and a
  backup decision, the parts and panel rules, British English, no dashes, no
  hosting or setting names, a release note for every app change, CI green
  before merge.
- The browser suite's records only go up with a written reason.

## Left to the builder

- The order of the work and how it splits into pull requests.
- How a change and its history line are kept together.
- How the indexes over the history are built and kept.
- The converter's input format (a restored Postgres, or an export from it).
- How the old app's answers are captured for the "equal to the penny" proof.
- Where the Stock tab sits in the sidebar.

## Open questions

None. The one question from the builder check (going back after the switch)
was answered by Cameron on 22 Oct and is recorded under "Decided with
Cameron".
