# Panels: every section in a box

Date: 13 October 2026. Status: approved in conversation; this spec is for review before planning.

## Why

After the blank-space build went live, Cameron said: "a lot of the interface is a mess, you aren't boxing things off, things look floating and unintentional."

The cause is a deliberate earlier choice. Since 5 October a card has no fill, no edge and no padding: the card is the table's frame, and sections are separated by hairlines on one white sheet. On a wide screen, Summary, What changed, the figures, Sales by sector, Store knowledge, Tracked changes and the Files list all sit straight on the same white. They read as loose islands rather than as deliberate groups.

On 13 October Cameron compared three treatments laid over six real pages (Overview, Liability, Reconciliation, Memory, Team's People, Files). He chose **A: panels on a grey page**, and **equal heights for panels side by side**.

## What success looks like

- On every page, every section sits in a visible panel with a clear edge. Nothing a person reads floats on the page ground except the page's own header, its tabs and its notices.
- Panels side by side form one row with one top edge and one bottom edge.
- The pages keep everything the blank-space build gave them: the 1,200 column, pairs, figure groups, headed tables, one-line empty states, two-line rows on a phone and no sideways scroll.
- Measured clean at 390, 1280, 1440, 1920, 2200 and 2560, and approved by Cameron on before-and-after shots before it ships.

## The design

### 1. The page ground and the panel

- **Page ground.** The sheet (`.main`, inside the dark frame) becomes a light grey: a new token `--surface-canvas`. Its value is a neutral grey a shade darker than `--fill` (about `#F1F2F3`), so a panel's white reads clearly against it.
- **Panel.** A panel has:
  - a white ground (`--surface-primary`);
  - a fine edge (`--bw-hairline` in `--border-default`);
  - the card corner (`--radius-card`);
  - a very soft shadow, a new token `--shadow-panel` (about `0 1px 2px` at 6% plus `0 1px 1px` at 3%);
  - padding from a new token `--panel-pad`: 20px top and bottom, 24px each side.
- **Spacing.** Panels sit `--panel-gap` apart: 20px on a desk, 12px on a phone. This replaces the page rhythm between blocks, and the gap inside a pair matches it.
- **Screen only.** All of this sits under `@media screen`. A report printed to PDF keeps its plain white page and its current print rules.
- **Unchanged:** the dark sidebar and frame, the type, the teal, the 1,200 column and the top bar's crumbs and Search, which now sit on the grey.

### 2. What becomes a panel

Every top-level block of a page's content is a panel, except:

- the page header (title, its line or live status, its buttons);
- the page tabs and queue tabs;
- notices: the paid-but-still-tagged strip, alerts, banners and errors, which already carry their own fill.

So these are panels:

- **Cards and lists.** Every card, list and table, including the Production Manager queue (its toolbar and rows), the Inbox list and board, Files, the CRM lists and board, the Size list, Loan units' Out now and register, Team's tables, Memory, Skills, the Guide's sections, What's new and Requests.
- **Figures.** A figure group without sparklines is one panel, with its hairlines between figures. A trend figure with a sparkline (Overview's eight) is a small panel of its own, so Customise can still move and hide each one.
- **Pairs.** Each half of a pair is its own panel.
- **Bands.** Reconciliation's band (counters and sources) and Xero sync's band are one panel each.
- **The rest.** The charts group, the report's question box (Ask about this report) and run gates are panels too.

The Production Manager's counters (Unprocessed, To make, To ship) keep their own tiles on the page ground beside Complete and Custom shipments. They are filters that sit with the tabs, not a section.

### 3. Headings belong inside their panel

A section's heading, its count, its (i) and its buttons sit at the top inside its panel.

Where a heading is a block of its own today, it moves into the panel of the content under it. Examples: Top opportunities, Performance findings, Findings, Details, What's notable, Open follow-ups, Your keywords, Sector comparison, Customer segments, Top customers, Performance over time. The existing pass that gathers a heading and its content into one card (`cardifySections`) does this, so the heading and its content are one panel.

A heading that stands alone with nothing under it does not exist after this change.

### 4. Tables in panels

A table runs to its panel's left and right edges, so its rows read as the panel's list. Its first and last columns keep the panel's inset, so their text lines up with the heading above. This is the existing `.card-bleed` behaviour, used again now that a panel has padding.

The head row keeps its caption type and its rule. A table's last row has no rule under it, because the panel's edge closes it.

### 5. Rows of panels

- **Side by side, equal height.** Two panels in a pair stretch to the taller one, so the row has one top and one bottom edge. A short panel's content stays at its top, with white inside the panel under it.
- **Figure tiles.** Trend figures in a row are equal height for the same reason.
- **Stacked, own height.** When a pair stacks (under 64rem of its own width, and on a phone), each panel is as tall as its content.

### 6. Phones

The grey ground stays. Panels run the full width of the column with 16px padding, 12px apart. Tables keep their two-line phone rows inside the panel. A panel's heading row keeps its one button beside the title, as the blank-space build's phone pass set.

### 7. What does not change

- **Paper.** The printed label, the A4 and courier sheets, the print document, `LABEL_LOGO` and the print CSS. `t_the_printed_sheets_do_not_change` stays as it is.
- **The Production Manager queue.** Its content, columns, statuses, actions and their order. Only the panel goes round it.
- **Windows.** Settings, the order and document windows and every other modal are already boxes and keep their look.
- **Chat.** The conversation keeps its reading column; messages are not panels. Only the start screen's recent conversations sit in a panel.
- **Customise.** Each block keeps its dashed edge while arranging, drawn on the panel's own edge. The hide button and grip stay on the block's first line.
- **The Quote Engine** is not touched.

## How it is built

- **CSS first.**
  - The tokens: `--surface-canvas`, `--shadow-panel`, `--panel-pad`, `--panel-pad-phone` and `--panel-gap`.
  - One panel rule, `.panel` or the equivalent selector set, for a page's top-level blocks and a pair's halves.
  - Equal heights inside a side-by-side pair.
  - The canvas on `.main`.
- **Rules to retire.** Some rules exist only because the page had no panels: hairlines between sections, `--page-rhythm` margins and the bleed resets that cancel `.card-bleed`. They are retired where the panel replaces them, and each retirement is pinned.
- **Headings.** `cardifySections` and the heading widgets are reconciled, so a heading and its content are one widget. A saved Customise layout that names a heading's old id still loads, with the merged panel at its default place (the rule from the blank-space build's final review).
- **Pages with their own layout.** The CRM board, the Inbox board and Team's Activity filters get a panel round the whole board or list. Their lanes and lists keep their look inside it.
- **One teal per screen, no illustrations, British English and no dashes on screen.** These still bind.

## How it is proven

- **Tests (`tests/test_frontend.py`).** One test per decision:
  - the tokens exist and the token guards pass;
  - the panel rule covers top-level blocks and pair halves;
  - pairs are equal height side by side;
  - headings sit inside their panels, with no lone heading block;
  - print is unchanged;
  - an old saved layout naming a merged heading still loads.
- **Rig measure.** Every page in the three clusters at the six widths, with no sideways scroll, clipping or overlaps beyond the known scroll positions.
- **Panel probe.** For every screen, every visible top-level block of the content root is either a panel (white ground, edge, padding) or one of the named exceptions: header, tabs, notices, the Production Manager counters.
- **`make check`** passes.
- **Review page.** For all 31 pages, today beside built at 1,920 and on a phone. Cameron's yes is required before a pull request.
- **Agents.** This is a new task with a budget of five. At most two are used, for the final code and visual reviews.

## Out of scope

- New colours, a new type scale, or a dark mode.
- Redesigning any page's content or order, beyond moving headings into their panels.
- The blank-space build's deferred items (phone toolbars, column spacing and the others on its "Left for you" list).
