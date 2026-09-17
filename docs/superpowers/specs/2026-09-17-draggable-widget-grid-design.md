# Draggable widget grid, app wide

Date: 2026-09-17. Status: approved 2026-09-17 ("build it") and implemented the
same day in `11ace1f`, `a977fdc`, `8af3da3`, `c9aa216` and `2f73626`. Where the
body and the two Revisions sections at the end disagree, the later revision is
what shipped.

## Why

Cameron supplied a React component, `draggable-widget-grid.tsx`, with a demo,
and asked for its drag behaviour and design across the whole app. gizmo has no
React, Tailwind, TypeScript or bundler, and the standing rule is no framework
changes, so the component cannot be dropped in. What it contains that is worth
having is not React: a tiling algorithm, a drop-target chooser that cannot
oscillate, a touch long-press, keyboard moves and a lift. This spec ports those
to the app's plain JavaScript and applies them to every report screen through
one layer.

What exists today, measured 2026-09-17:

| Thing | State |
|---|---|
| Rearranging | Overview KPI tiles only: HTML5 drag plus arrow buttons, `ovEdit`, `reorderOv`, `toggleHideOv`, `metricsGridCustom` (`static/index.html` ~4582 to ~4960, button at ~6102) |
| Where it saves | `localStorage` key `sc_ov_layout_v1`, `{order, hidden}` by KPI label, this browser only |
| Other drags | CRM board cards between columns (~16455), Files rows (~21079). Both move things between containers, not a page layout |
| Screens | 20 views in `setView` (~22187). 19 render into `.ov-wrap#<view>-content`; Chat has its own log and composer |
| Rhythm | `.ov-wrap > *` bottom margin `--sp-6` (24px), `--sp-4` at 640px and below |
| Motion | `--dur: .15s`, `--ease: cubic-bezier(.4,0,.2,1)`, `REDUCE_MOTION` const. No FLIP, no Web Animations use |
| Per-person storage | None. `/api/profile` prefs are shop wide |
| Identity on the server | `_guard(request)` returns `(err, body, uid)`; `uid` is the signed-in account |

## Decisions already made

Taken with Cameron on 2026-09-17:

1. **Scope: every screen.** Every report screen whose content is a set of
   separate blocks gets it. A screen with one block has nothing to arrange and
   gets no button.
2. **Drag mode: a Customize button.** Nothing moves until you press Customize.
   Outside that mode a drag on a card does what it does today.
3. **Approach A: one central layer** that runs after a view renders. Rejected:
   B, wiring drag into each screen's renderer (twenty copies of one behaviour,
   the thing the house has spent a year removing); C, a React island per screen
   (a framework change, and a second rendering model beside the first).
4. **Card sizes are fixed per card.** People reorder and hide; they do not
   resize.
5. **Layouts are saved per person, on their account.** Rearranging your
   Overview never moves a colleague's cards, and it follows you between
   machines.
6. **The demo's look is not carried over.** No JetBrains Mono, no uppercase
   letterspaced titles, no demo palette. Widgets are the house `.card` and
   `.stat` recipes as they are.

## What a widget is

A widget is one top-level block on a view that carries two attributes:

- `data-widget`: a stable id, unique within the view, matching
  `^[a-z0-9][a-z0-9-]{0,47}$`. It is chosen by meaning, not by position or
  title text: `trend`, `drivers`, `alerts`, never `card-3` or `revenue-12-orders`.
- `data-size`: `sm`, `wide` or `full`. Omitted means `full`.

One helper sets both: `widget(node, id, size)` returns the node. A heading
built by `cardifySections` from a `.section-title` carries the attributes
across to the card it becomes.

The widget's accessible name and the name used in menus and announcements is
its `.card-title` text, or `data-widget-label` when it has no title.

**Fixed blocks.** A top-level child with no `data-widget` is a fixed block. It
never moves and spans every column. Fixed blocks are allowed only before the
first widget (leading) or after the last (trailing). Measured in the rig, the
leading ones are the page header (`.ov-hero`), the Overview alerts banner (which
renders above the header), the changes strip, page tabs and segment bars
(`.page-tabs`, `.lbl-seg`, `.seg-row`), the Files storage meter, the run gate,
the `.thinking` loading row and an error message; the trailing ones are the page
chat panel (`.page-chat`, an input rather than a report card) and the Production
Manager's order preview below 1500px. The layer keeps leading fixed blocks
first and trailing fixed blocks last in the DOM, in their rendered order.

**A group is built by its renderer.** Where a heading labels more than one
block, or a heading sits bare beside a block `cardifySections` will not fold
(Overview and SEO trends, Keywords paid search, and every heading pair in
Forecast, Memory and Skills, which never call `cardifySections`), the renderer
wraps the heading and its blocks in one `div.widget-group` and puts the id on
that. The layer never wraps anything: `trendsSection` repaints by swapping
nodes it owns, and a wrapper added from outside would break its range switch.
Inside a group the page rhythm holds: 12px under the heading, 24px (16px on a
phone) between blocks.

**A view qualifies** for Customize when, after render, it has two or more
widgets and every top-level child is a widget or a fixed block in a fixed
position. A non-widget child between two widgets makes the view not
customizable, writes `console.warn('[widgets] <view>: block without an id',
node)`, and fails the rig probe. That is how an unlabelled block gets caught: see
Testing. Measured in the rig, CRM, Files, Team, Size list and Guide each render
one block and so get no button.

**Overview KPI tiles become widgets.** Each tile is an `sm` widget with id
`kpi-<slug of its label>`, a direct child of `#ov-content`. The slug drops a
bracketed threshold such as the `(≤5)` in "Low stock (≤5)", so that tile is
`kpi-low-stock` and a change to `LOW_STOCK_THRESHOLD` does not lose it from a
saved layout. The "Key numbers" heading goes: a heading over tiles that can be
scattered across the page labels nothing. The bespoke
Overview code (`ovEdit`, `reorderOv`, `toggleHideOv`, `ovOrderedLabels`,
`metricsGridCustom`, its arrow buttons and HTML5 drag) is deleted; the tiles
keep the `.stat` recipe. Other views' `metricsStrip()` blocks stay one `full`
widget: splitting a joined strip is a design change nobody asked for.

## Layout

### The layout

The component's arithmetic is ported into one block of `static/index.html`
between the markers `/* ---------- widget layout (pure) ---------- */` and
`/* ---------- widget layout end ---------- */`, with no DOM access, so a test
can lift the block out and run it under node: `wgLayout`, `wgMoveTo`,
`wgSameOrder`, `wgChoose`, `wgCandidates`, `wgOverlaps`, `wgContains`,
`wgSpanOf` and `WG_ENTER`, plus gizmo's own `wgMergeOrder`, `wgKeyMove`,
`wgColumns`, `wgSlotFor`, `WG_ID` and `wgKpiId`.

Three changes from the component, each forced by gizmo's content:

- **Sizes are `sm` 1 column, `wide` 2 columns, `full` every column**, all one
  row high. `full` is `{col: Infinity, row: 1}`, which `wgSpanOf` clamps to the
  column count. The component's `tall` and `lg` are dropped: they need rows of a
  known height, and gizmo's rows are sized by content.
- **Rows size to content, not to square cells.** A row is as tall as its
  tallest widget and cards in one row stretch to match. `wgSlotFor` reads column
  edges from the column count and row edges from the rendered widgets; a row
  below the last rendered one takes the last row's height.
- **The layout keeps the order it is given.** Cards go left to right in order
  and a card that does not fit the rest of its row starts the next one, which is
  the browser's own grid auto-placement for the same spans. The component tiled
  instead, seating a later card before an earlier one to close a hole and
  widening cards when it could not. It was ported first and replaced in
  `2f73626`: on gizmo's pages, which read top to bottom and whose cards mostly
  span the row, closing a hole meant moving a whole report. With nine or ten KPI
  tiles the Overview pulled Sales by sector up between them, and a card dropped
  between two reports jumped to the foot of the page.

### The grid

When a view qualifies, `.ov-wrap` gains the class `wgrid`:

```
.ov-wrap.wgrid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
                 gap: var(--wgrid-gap); align-items: stretch; }
.ov-wrap.wgrid[data-cols="2"] { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.ov-wrap.wgrid[data-cols="1"] { grid-template-columns: minmax(0, 1fr); }
.ov-wrap.wgrid > * { margin: 0; }                       /* the gap is the rhythm */
.ov-wrap.wgrid > :not([data-widget]),
.ov-wrap.wgrid > [data-span="full"] { grid-column: 1 / -1; }
.ov-wrap.wgrid > [data-span="2"] { grid-column: span 2; }
.ov-wrap.wgrid > [data-span="3"] { grid-column: span 3; }
```

`--wgrid-gap` is `var(--sp-6)`, and `var(--sp-4)` at 640px and below, so the
24px and 16px rhythm and the single left edge are unchanged. The layer writes
the column count to `data-cols` on the wrap and each widget's placed width to
`data-span` (`1`, `2`, `3` or `full`; `3` only arises when `pack` widens a
widget to close a four column row). It writes attributes, never inline styles,
so the print stylesheet and the existing inline-size guard both still hold. The
DOM order is set to the layout's reading order, so auto-placement lands every
widget where the tiler put it. The component instead kept DOM order fixed and
placed widgets by coordinates, because moving React nodes restarted its mount animation; plain
DOM has no such problem, and reading order in the DOM keeps tab order and
screen reader order the same as what you see.

### Columns

The layer sets `data-cols` from the width of the content column:

| Width | Columns |
|---|---|
| viewport 640px or below (the query `.ov-wrap` already uses for its phone padding) | 1 |
| content column narrower than `4 × --wgrid-cell` | 2 |
| otherwise | 4 |

`--wgrid-cell` is 240px. At 280, the content column at a 1440px window with the
sidebar open (1109px) fell short of four cells and got two columns. Three columns are not used: at three, `wide` is two
thirds and `sm` beside it is a third, a proportion no screen in the app has.
A `ResizeObserver` on `.ov-wrap` recomputes it, and the sidebar folding counts
as a resize.

### Merging a saved layout with what rendered

A saved layout is `{order: [ids], hidden: [ids]}`. The default order is the
order the renderer appended widgets in. Applying a saved layout:

1. Drop every saved id that did not render, and any duplicate after its first.
2. Start from the saved order.
3. For each rendered id the saved order does not mention, in ascending default
   index, insert it at `min(defaultIndex, length)`.
4. Remove hidden ids from the page.

A card added in a later release therefore appears where it would for someone
who never customized. The Overview migration relies on this: an old saved
order of KPI tiles puts the tiles in that order and every other block at its
default index.

This is `mergeOrder(defaultIds, saved)` in the pure block.

### When the layer runs

One `MutationObserver` per content root, watching `childList` only, runs the
layer after a renderer changes the root. The layer is idempotent: it compares
the current DOM order with the merged order and does nothing when they match,
and it disconnects its observer while it moves nodes. A renderer that builds a
page in several steps (header, await, then cards) gets several cheap passes.
Nothing in a renderer calls the layer, so a screen added next year is covered
without anyone remembering to wire it.

If a render lands during a drag, the drag is cancelled and the draft order is
applied to the new nodes.

## Customize mode

### Entering and leaving

The button is a `btn btn-sm` with the settings icon, labelled Customize, in the
page header's action group (`heroAct`) beside Refresh, where the Overview's is
today. A qualifying view that has no page header gets one from `heroAct` in its
build batch. It
carries `aria-pressed`. It is absent on a view that does not qualify, and
absent while that view shows its run gate.

Pressing it turns the page into a draft. The header's action group then shows,
in this order: **Show hidden (n)** when anything is hidden, **Reset**, and
**Done** as the primary button.

- **Show hidden** opens the existing `dropMenu` listing hidden widgets by name.
  Choosing one puts it back at its default index.
- **Reset** sets the draft to the default order with nothing hidden.
- **Done** saves the draft. When the draft equals the default it deletes the
  saved layout instead of saving a copy of the default.

Leaving the view while customizing counts as Done. Customize mode is per view
and ends on Done.

### What the page looks like in the mode

- Each widget shows a dashed outline, `--bw-hairline` wide in
  `--border-emphasis`, just outside its own border, and a `grab` cursor (`grabbing` while held).
- Each widget shows a hide button (`I.x` in an `icon-btn`, label
  "Hide <name>") in its top right corner. On the last visible widget it is
  disabled.
- Links, buttons, inputs and chart hovers inside widgets are inert: clicks are
  swallowed at capture, as the component does for links. The CRM board's card
  drag and the Files row drag are inert too.
- The grid takes `role="list"`, each widget `role="listitem"` with
  `aria-posinset` and `aria-setsize`, and the component's hint is present as
  visually hidden text, reworded for gizmo: "Drag to rearrange. On a touch
  screen, press and hold first. With a keyboard, hold Alt and press the arrow
  keys." Outside the mode none of these roles are set: a report page is a
  document with headings, not a list.

### Dragging

Pointer events, not HTML5 drag and drop: HTML5 drag does not work on touch
and draws a ghost image instead of moving the card.

- **Mouse and pen:** a primary-button press on a widget lifts it immediately.
- **Touch:** a press lifts after `350ms`; moving more than `8px` first cancels
  the lift and lets the page scroll. While lifted, `touchmove` is prevented so
  the finger moves the card, not the page. `navigator.vibrate(10)` on lift
  where it exists.
- **While held:** the card follows the pointer by `transform`. Move and up
  listeners are on `window`, because moving the held card in the DOM would
  release a pointer capture set on the card itself. At most once per animation
  frame, and no sooner than `40ms` after the last reorder, `choose` picks among
  `candidatesFor`; when it returns an order, the siblings move to their new
  places.
- **Esc while held** returns every card to where it was when the drag began.
- **Release:** the card travels from under the pointer to its slot, and it
  shows `--focus-outline` for `--dur-landed`, then the outline fades.
- The click that follows a release is swallowed for `300ms`.

### Keyboard

A widget is focusable (`tabindex="0"`) only in Customize mode. Alt with Right
or Down moves it one place later in the order; Alt with Left or Up, one place
earlier. Focus stays on the moved widget. Each move is announced as "<name> moved to <position> of
<count>"; hiding as "<name> hidden", showing as "<name> shown". These go to a
new visually hidden `role="status"` region, created at start-up for the reason
the toast host's comment gives (a region created with its first message is
announced unreliably). They do not go through `toast-host`: a toast on every
Alt+Arrow would be seen, not just heard.

## Motion

All motion values are tokens in the one top-level `:root`:

| Token | Value | Used for |
|---|---|---|
| `--dur-layout` | `.38s` | siblings moving to new slots; the card settling on release |
| `--ease-layout` | a `linear()` spring curve, bounce .16 | the same |
| `--dur-landed` | `.62s` | how long the landed outline stays |
| `--lift-scale` | `1.02` | the held card |
| `--wgrid-cell` | `240px` | column count |
| `--wgrid-gap` | `var(--sp-6)`, `var(--sp-4)` at 640px and below | grid gap |

The lift uses `--shadow-lg` and the existing `--dur` and `--ease`. The spring
values are the component's `SPRING`; its lift scale of 1.06 and its bouncier
lift spring are not carried over (see Choices made while writing).

Siblings move by FLIP: record each widget's rectangle, apply the new order,
then animate each from its old offset to none with `Element.animate`, reading
duration and easing from the tokens. The component's entrance stagger (cards
rising in on mount) is not carried over: views re-render on every refresh, and
a back-office page that animates in each time it refreshes is not calm.

With `REDUCE_MOTION`, nothing animates: no FLIP, no lift scale, no settling
travel, no landed fade. The held card still follows the pointer, because that
is the manipulation itself, not decoration.

## Saving

### Store

`LAYOUTS_PATH = os.environ.get("LAYOUTS_PATH", "/data/layouts.json")`, written
only through `_write_json_store(LAYOUTS_PATH, "layouts", data, private=True)`
and read with `_load_json_store`. Shape:

```
{"layouts": {"<uid>": {"<view>": {"order": ["trend", "alerts"], "hidden": ["drivers"]}}}}
```

An `asyncio.Lock` serialises the read, change and write, so two people saving
at the same moment cannot drop each other's layout. The file sits in the data
directory, so the backup archive includes it with no change: it holds card ids,
not credentials. `docs/ENVIRONMENT.md` gains `LAYOUTS_PATH` by running
`make env-doc` (`tools/env_reference.py`), which the existing test compares
against the code; the scratch path table at the top of `tests/test_dispatch.py`
gains it too.

A departed account's entry is left in place; it is a list of card ids.

### Routes

Every app call is a POST with a JSON body (the page's `api()` helper only
POSTs, and the server has no PUT or DELETE route), so there is one route,
`POST /api/layouts`, shaped like `/api/profile`. It goes through `_guard` and
uses only the `uid` it returns. No body field names an account, so no one can
read or write another person's layout.

| Body | Does |
|---|---|
| `{}` | returns `{"layouts": ...}`, the caller's layouts for every view, `{}` when none |
| `{"view", "order", "hidden"}` | replaces the caller's layout for that view, returns the map |
| `{"view", "reset": true}` | removes it (Reset then Done), returns the map |

Validation, each a 400 with a plain message: `view` is one of the 19 content
views; `order` and `hidden` are lists; each list at most 64 ids; each id matches
the widget id pattern; `reset` is exactly `true`. The body is capped at 8KB on
the bytes read, not only the declared length. The
server does not know which ids a view renders and does not try to: the client
drops unknown ids when it merges.

### Client

The layouts are fetched once when the app starts (`api('/api/layouts', {})`), beside `loadProfile()`. Until they
arrive a view renders in default order; when they arrive the current view is
arranged once. If the fetch fails, views stay in default order and the
Customize button is disabled with the title "Layouts are unavailable right now".

Done writes before it leaves the mode. If the write fails, the page stays in
Customize mode with the draft on screen and a toast, "Your layout was not
saved. Try Done again." A failed save is never shown as saved. When leaving the
view is what triggered the save and it fails, the toast says "Your layout was
not saved", and the view shows its last saved layout the next time it opens.

### Overview migration

On the first Overview render after the layouts arrive, if the server has no
Overview layout and `localStorage` holds `sc_ov_layout_v1`, its labels are
mapped to `kpi-<slug>` ids and saved. The key is removed only after
that save succeeds, so a failed migration is retried next time rather than lost.

## Print

Printing uses the arrangement on screen with hidden widgets left out, in one
column: under `@media print`, `.ov-wrap.wgrid` takes one column and every
widget spans it, whatever `data-cols` and `data-span` say. A four column grid on
an A4 page would squeeze every card.

## Testing

### Pure layout, run under node

A new harness in `tests/test_frontend.py`, built like `_CURVE_HARNESS`: lift the
block between the layout markers out of `static/index.html` and run it. Skips
when node is absent, like the existing one.

- An exact tiling leaves no empty cell and places every widget once.
- `pack` closes every row; no placement runs past the column count.
- `full` spans every column at 1, 2 and 4 columns; `wide` is clamped at 1.
- The layout keeps the order given at 1, 2 and 4 columns, and the Overview
  keeps its order with any number of KPI tiles.
- `choose` converges: with the pointer still, each adopted move brings the
  card's slot strictly nearer the pointer, no order repeats, and the chain ends.
  (The stricter "a second choice returns null" is false for this algorithm: in
  341,127 harness picks, 6,366 took a second or third step, each nearer. The
  drag loop therefore expects a still pointer to settle over a few frames.)
- A group swap trades a `wide` with two `sm` widgets that fill its shape.
- `mergeOrder` drops unknown and duplicate ids, puts an unmentioned id at its
  default index, and removes hidden ids.
- A keyboard move clamps at the first and last place.

### Server, in `tests/test_dispatch.py`

- Two accounts save different Overview layouts; each reads back only its own.
- Without a session the route answers 401.
- An unknown view, a non-list, 65 ids, and an id with a space are each 400.
- A reset removes only the caller's entry for that view.
- A new account reads `{}`.
- The store is written through `_write_json_store` with `private=True`.

### Static guards, in `tests/test_frontend.py`

- Every motion and grid token in the table above exists in the top-level
  `:root`, and the widget CSS and JS read them rather than writing a duration,
  scale, cell width or gap as a literal.
- The layer sets `data-cols` and `data-span`, never `style.gridColumn` or a
  custom property on an element.
- The FLIP and lift paths check `REDUCE_MOTION`.
- The layer's list of content roots is the same list `setView` uses.
- Every `data-widget` id literal in the file matches the id pattern, and no id
  is declared twice for one view.
- `role="list"` is only set by the Customize mode code.
- `sc_ov_layout_v1` is read only by the migration, and `metricsGridCustom`,
  `reorderOv` and `toggleHideOv` are gone.
- No em or en dash in any new UI copy (the existing check covers it).

### Rig, before each commit that changes a screen

The probe gains a widget check: on each view, every top-level child of the
content root is a widget or one of the named non-widget kinds, and ids are
unique. This is the check that catches an unlabelled block, because an id can
only be verified on a rendered page. Each qualifying view is swept at 375px
and 1440px with Customize off and on; the existing gutter and concentric
checks must still pass; a drag is driven with synthetic pointer events and a
screenshot of before and after is kept as proof.

## Build order

One feature, delivered in stages that each leave the app working:

1. The pure layout block and its node tests.
2. The store, the three routes and their tests.
3. The layer, Customize mode, motion and saving, switched on for the Overview
   only; the bespoke Overview code removed; the migration.
4. An inventory in the rig of every other view's top-level children, then ids
   and sizes added view by view in small batches, each batch swept in the rig.
5. A final rig sweep of every view at both widths.

## Where this spec differs from the outline approved in chat

- The outline said a guard "fails the build" when a block has no id. A block's
  id can only be checked on a rendered page, so that check lives in the rig
  probe, with a console warning in the app. The CI guards cover what can be
  checked from the source: id syntax, id uniqueness, and that every content
  root is wired.
- The outline said "the component's exact tiler". The algorithm is ported as
  written, but with `tall` and `lg` removed and `full` added, because gizmo's
  rows size to content.

## Revisions after stage 1 (2026-09-17)

Stage 1 built the engine, the route and the rig, and measured every screen.
What it changed here:

- **One POST route** instead of GET, PUT and DELETE, to match the rest of the app.
- **Fixed blocks** replace the short list of non-widget kinds: the rig found
  tabs, segment bars, a storage meter, the alerts banner, the changes strip, the
  page chat and a preview pane at the top or bottom of screens, none of which
  the first list named.
- **Renderers build groups**, not the layer, because some groups hold two or
  three blocks and one of them repaints its own nodes.
- **`--wgrid-cell` is 240px**, not 280, so a 1440px window with the sidebar open
  gets four columns.
- **KPI ids ignore the low-stock threshold**, and the "Key numbers" heading goes.
- **A group swap must fill its area.** Ported line for line, the component let
  a swap reach into the empty end of a short last row; that order put the card
  somewhere other than the slot it claimed, and the chooser picked it every
  frame. The component's own comment says the area is filled entirely.
- **The chooser converges rather than stopping at once**; the test says so.

## Revisions after stages 2 and 3 (2026-09-17)

What building and measuring every screen changed:

- **The layout keeps order** (see The layout). `wgTile`, `wgPack` and
  `wgCanonical` are gone, and a keyboard move is one place in the order.
- **Every adopted card is full width** except the Overview's twelve KPI tiles
  (`sm`). A half-width Open follow-ups or Sales by sector left a hole whenever
  follow-ups were absent. The rule for a new card: full unless it genuinely
  pairs.
- **14 screens qualify**: Overview, SEO, Keywords, Products, Customers,
  Liability, Reconciliation, Forecast, Xero sync, Loan units, Inbox, Production
  Manager, Memory and Skills. CRM, Files, Team, Size list and Guide draw one
  block each and are unchanged.
- **A card whose holder is empty** (`:empty`, or `display: none` set by
  something other than the person's layout) is left out of the arrangement,
  the Customize list and the Show hidden count, and comes back when it fills.
- **Auto-scroll while dragging**, so a phone can carry a card past the fold.
  It runs from pointer moves plus a timer, not animation frames, and stops at
  either end, on release and on Esc. Scroll anchoring is off in the mode.
- **Customize and Done are two buttons**, because the house pressed style would
  have repainted a pressed Done over its primary fill. Liability, Loan units,
  Memory and Skills gained an empty `heroAct` slot for the button, and
  Reconciliation, Forecast, Xero sync and Inbox gained one only after their
  loading, setup and failure states, which look as they did.
- **Layouts are read when the app learns who is signed in** (`claimLocalCache`),
  not at start-up: a sign-in from the login screen does not reload the page, so
  a read made before it would have left Customize off for the whole session.
- **Nothing is saved for a screen that is not showing its cards.** A product
  opened from the list, a run gate or a half-drawn refresh would otherwise lay
  the draft against no cards, read it as the default and delete the layout.
- **KPI tile rows are 24px apart**, not the 16 the old tile grid used: the
  grid has one gap and it is the page rhythm.
- **Not verified on a real device**: the FLIP and landing motion, the
  `linear()` spring, touch long press and vibrate, the reduced-motion paths,
  and whether Alt with an arrow is taken by a browser before the page sees it
  (on Windows and Linux, Alt+Left is Back; the page cancels the key, but no
  browser was tried).

## Choices made while writing this spec

Each is Cameron's to overrule before the plan is written:

1. **Two or four columns, never three.** Keeps `wide` at half the width.
2. **Lift scale 1.02, not the component's 1.06**, and the house `--dur`/`--ease`
   for the lift instead of a bouncier spring. The app's motion is quiet
   everywhere else.
3. **No entrance animation** when a view renders.
4. **List roles only in Customize mode.**
5. **Leaving a view while customizing saves**, rather than discarding.
6. **Overview KPI tiles become individual widgets** in the page grid, since
   they are individually arrangeable today; other screens' metric strips stay
   one widget each.
7. **The last visible widget cannot be hidden.**
