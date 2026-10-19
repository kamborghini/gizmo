# Panels and tables

**Approved 19 Oct 2026.** Stage 3, piece 5 of the 14 October engineering
audit. Cameron approved all three parts, including the shorter prompt in the
report Ask box.

## Why

Two things are still stamped onto the page after it is drawn, by one
page-wide observer (`static/src/js/page-observers.js`):

- **Table heads onto their cells** (`syncTableHeads`). On a phone a table's
  rows become two-line rows that name each value ("Orders 5"); the names are
  copied from the head onto every body cell as `data-h` after the table is
  drawn. 25 tables are built by hand, plus Forecast's `fcTable`.
- **Panels** (`syncPanels`). Every block of a page is a white panel on the
  grey page (the 13 Oct panels spec); the class `.panel` is stamped onto a
  page root's children, and onto the children of holders such as pairs,
  after every redraw. About 60 style rules read it.

Neither is slow (measured: the observer runs about 11 times while Overview
loads and never while a chart is hovered). The case is that nothing should be
stamped on afterwards: a part builds what it builds, and the panel rule lives
with the panel's look.

The browser record's panel findings (72) are almost all false alarms: the
probe counts a search box, a menu, a button, a chip or the aged-debt bar as a
"ruled line", and a notice between two panels as a wrong gap. The one real
fault: on every report page the "Ask about this …" panel shows its grey ask
well as a box inside the panel, and its suggestions start 16 further in than
the title. A rule written on 13 Oct to put the field in the panel itself
(`.panel.pchat > .pchat-input`) never matched, because the panel is
`.page-chat` and `.pchat` is a card inside it. On a phone the box's prompt
("Ask a question about this report…") is cut off mid-line.

## What changes

### `dataTable(cols, opts)`, the real table

A new section `static/src/js/part-table.js` builds the wrapper
(`ktable-wrap`), the table (`ktable`), its head and its body. `cols` are the
columns in order, each a head (a string, a Node, or null for an empty head)
or `[head, cls]` with the head cell's classes (`num`, `kt-main`). Each row
added through the part (`t.add(tr)`) has its cells named from their columns
as it is added: the same names, the same rule for cells across several
columns, the same `kt-main` mark as the stamp gave. Every hand-built table
and `fcTable` moves to it; `syncTableHeads` is deleted. **No visible change.**

### The panel rule in the stylesheet

The rule stays exactly what it is: a page root's children are panels, except
the header, tabs, choosers and notices (the skip list), and a holder (a pair,
a pair's inside, Forecast's pair, CRM's segment and charts, the Guide's host
and grid, the Design page, and any element with no class) passes the rule on
to its children. It becomes one selector in `static/src/css/panels.css`, up
to four holders deep (the deepest on any measured state is four: Team's Work
tab), and the panel rules nest under it. `.chat-recent.panel` keeps its class
(it is built as a panel outside any page root). `syncPanels`, `panelTargets`,
`PANEL_SKIP`, `PANEL_HOLD`, the observer and its batched pass are deleted.
The browser suite reads the selector from the stylesheet, so its checks use
the rule the page uses. **No visible change.** (A spike over the 108 states:
the selector picks 2,410 of the 2,412 stamped panels at three holders deep;
the other two are the four-deep ones.)

### Panel checks that tell the truth, and the Ask panel

- A ruled line is a hairline: an element with a top or bottom border and no
  side borders. A box (a field, a menu, a button, a chip, a bar) is not one.
- Two panels with a notice or another page block between them are not a
  wrong gap.
- The Ask panel: its suggestions and its field sit on the panel's own inset,
  lined up with its title, with no grey well (the 13 Oct rule, aimed at the
  card inside the panel). Its prompt is "Ask a question…" (its name for a
  screen reader stays "Ask a question about this report").

**Visible change**: the Ask panel on every report page, as in the photo.

## Guards

- No section other than the part builds a `ktable` or its head; the browser
  suite checks, with zero tolerance on every measured state, that every body
  cell under a named head carries that name.
- `syncTableHeads`, `syncPanels` and the page-wide observer stay gone; no
  script adds the `panel` class except `.chat-recent`.
- The browser suite's panel walk (its own oracle, unlimited depth) agrees
  with the stylesheet's selector on every measured state.
- The panel record falls to its real findings and is lowered; nothing rises.
- Before-and-after screenshots: only the report pages' Ask panel differs.

## Not in this piece

The stylesheet in layers (piece 6). Xero's document preview tables and the
printed sheets' tables are not `ktable` and are left as they are.
