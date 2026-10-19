# Rows that open, tick rows, and two small fixes

**Approved 19 Oct 2026.** Stage 3, piece 4 of the 14 October engineering
audit. Cameron approved all three parts, including the change to the
Production Manager queue's rows (their make-up underneath only: content,
columns, statuses, actions and look unchanged).

## Why

The browser record's remaining accessibility findings come from one pattern: a
whole row built as a pretend button (`role="button"`) that opens something,
holding other real controls. A screen reader cannot present a button inside a
button, and the tick or link inside counts as too small a target. Measured:

| Row | Holds | Findings |
|---|---|---|
| Inbox (`.mrow`) | a select tick, a Claim button | nested-interactive, target-size |
| Production Manager queue (`.lbl-qrow`) | the order link, the row's actions | nested-interactive, target-size |
| CRM Contacts (`tr.crm-list-row`) | a select tick | nested-interactive, target-size |

CRM's deals list (`tr.crm-list-row`) is built the same way (a table row
pretending to be a button, which also hides the table's own row semantics).
Memory's "Pages it read" links are too small to tap; Customise mode marks its
grid a list without marking the blocks as items. The tick-and-words rows
(`tm-tabpick`, `disp-notify`, `disp-insure`, `crm-cline`, `sr-opt`) have two
text looks: dispatch's notify and insurance ticks are 12 grey, the others the
body text.

## What changes

### `rowOpener(label, onOpen)` and `opensOnClick(row, onOpen)`

A row that opens something stops being a button. `rowOpener` builds a real
button, visually hidden, named for the row ("Open: Invoice copy please, from
Accounts Team"), that opens it; its Enter and Space stop at the button, so a
page-wide shortcut never acts on them too. The row draws its existing focus
ring whenever that button has focus, so it looks as it does now.
`opensOnClick` keeps a click anywhere on the row opening it, except on a
control of its own (a tick, a link, a button). Used by the Inbox rows, CRM
Contacts and the CRM deals list. **No visible change.**

The **queue** needs no new button: each row already has a Preview button that
does exactly what the row does. Its rows stop claiming to be buttons (no role,
no tab stop, no key handler); a click on a row still opens its preview.
Nothing in the queue's content, columns, statuses, actions or look changes.

### `tickRow(cls)`, the tick-and-words row

Builds the `<label>` that holds a tick (or a radio) and its words, class
`tick-row` plus the screen's own layout class. One rule gives every tick row
the body text (14, primary ink); the family classes keep only their spacing.
**Visible change**: dispatch's notify and insurance ticks' words become the
body text, as in the photo.

### Two small fixes

Memory's "Pages it read" links get a finger-sized line (the target size from
the tokens); Customise mode marks each block of its grid a list item. **No
visible change** beyond the links' line height. (Built as a group, not a list:
the grid also holds the page's header and chooser, and a list may hold only
list items, so the grid is a group and each block a group named with its place,
"Top customers, 3 of 7".)

## Guards

- No row is built as a pretend button: no section sets `role="button"` on a
  `.mrow`, `.lbl-qrow` or `.crm-list-row`; `rowOpener` and `opensOnClick` are
  used where they were.
- No tick row is built by hand (`el('label', 'tm-tabpick' | 'disp-notify' |
  'disp-insure' | 'crm-cline' | 'sr-opt')` outside the part).
- The browser record's `nested-interactive`, `target-size` and
  `aria-required-children` findings go down (to zero where these rows were the
  cause) and the record is lowered; the keyboard journeys still pass.
- Before-and-after screenshots: the queue and the Inbox render identically;
  only Memory's link lines and screens with a converted tick row may differ.

## Not in this piece

Tables labelling their own cells for phones (retiring `syncTableHeads`) goes
with panels, which retires the last fixer of the same kind.
