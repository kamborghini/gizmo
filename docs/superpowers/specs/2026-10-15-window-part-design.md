# One window part, and a living design reference

**Approved 15 Oct 2026** (approach A). Stage 3, piece 1 of the 14 October
engineering audit; Cameron chose the six-piece split and this piece first.

Nothing on screen changes in this piece but one thing: the starter-password
window gains the X every other window has. It changes how windows are built, so
that every window behaves the same way because one piece of code builds them
all, rather than because each was copied carefully.

## Why

Reactor opens windows in 24 places:

| Kind | Where | How many |
|---|---|---|
| A window holding work (edit, dispatch, a rule, a preview, two-step sign-in) | CRM, dispatch, Production Manager, Files, loans, Inbox, settings | 16 |
| A question with one field (`uiAskText`, `uiAskPassword`) | settings, the composer | 2 |
| The yes/no question (`uiConfirm`, 64 callers) | everywhere | 1 |
| A small window styled as a question: the folder picker, the starter password | Files, Team | 2 |
| An enlarged view: a chart, a figure's detail | charts, structured responses | 2 |
| The Settings window, written into the page | the shell | 1 |

The 16 are copies of one shape: a dark overlay, a white box (`.modal`, with a
size class such as `disp-modal` or `wide`), a header holding the title and an
X, a body, sometimes a footer. Each copy then differs in small, accidental
ways: some give the X a name ("Close") a screen reader can read and some do
not; some put focus back where it came from and most do not; a few listen
for Escape only to do nothing with it. What makes them behave alike today is a set of fixers
in `js/page-observers.js` that run after a window is drawn: one stamps the
dialog role, one moves focus in and back (added on 14 Oct), one fences Tab.
When a fixer's selector misses, a window quietly loses the behaviour.

## What changes

### `dialog()`, the window part (`static/src/js/part-dialog.js`)

```js
const w = dialog({
  title: 'Edit Loan 1',         // the header's title, and the window's name for a screen reader
  size: 'disp-modal',           // optional: today's classes on the box (disp-modal, wide, cmodal proof-modal, confirm-modal)
  overlayClass: 'chart-modal',  // optional: today's classes on the overlay (chart-modal, confirm-overlay)
  bodyClass: 'fprev-body',      // optional: an extra class on the body, as some windows have today
  onEscape: () => answer(false),// optional: the yes/no question only; every other window ignores Escape
  onClose: () => renderCRM(),   // optional: what the window does after it closes
});
w.head                          // the header, for a window that adds controls beside its title (the X stays last)
w.body.append(...);             // the content
w.foot().append(saveButton);    // the footer, made the first time it is asked for
w.close();                      // closes it: the X calls this too
```

It builds exactly today's markup with today's classes, so the stylesheet is
untouched and every window looks as it does now. It owns everything a window
must do:

- **Its role and name:** `role="dialog"`, `aria-modal="true"`, named by its
  title (`aria-labelledby`).
- **The X:** a button named "Close". Besides the window's own answers (Save,
  Cancel, Done), it is the only way out: a window holding work never closes
  on Escape or on a click outside it, the app's own rule (the Guide's Design
  page), so a slip cannot lose what was typed.
- **Focus in:** as it opens, focus moves inside it: to the field the builder
  focuses, or to the X when the builder focuses nothing.
- **Focus back:** as it closes, focus returns to the control that opened it,
  or to that control's redrawn twin (the CRM board redraws as a deal closes),
  and never to a field left long before (the touch case fixed on 14 Oct).
- **Tab stays inside** while it is open.

### The questions keep their names

`uiConfirm`, `uiAskText` and `uiAskPassword` are already shared, and their
callers (64 for `uiConfirm`) do not change. Only their scaffolding moves onto
`dialog()`. What they do with keys stays exactly as now, which is the app's
rule: a yes/no question answers No to Escape (`dialog({ onEscape })`, used by
`uiConfirm` alone), and Enter answers only a question that can be taken back;
a question you type an answer into closes only by its X or Cancel. When one
window is open over another, only the topmost hears the keys.

### The other windows

The two enlarged views, the folder picker and the starter password are built
with `dialog()` like the rest (`overlayClass` carries today's `chart-modal` and
`confirm-overlay`). The starter-password window, which today closes only by
its Done button, gains the X. The Settings window is written into the page, so
it gets the same behaviour through `dialogShow(overlay)` / `dialogHide(overlay)`.

### What is deleted

From `js/page-observers.js`: `syncDialogs` and its listener, the focus-in and
focus-back observer, and the global Tab fence. The sign-in screen, which is not
a window, keeps a fence of its own beside it. Every window now gets these
things from the part that builds it.

## How it is proven

- **No visible change.** The browser suite runs every screen at three sizes
  against its record: not one count may go up. If accessibility findings go
  down (named windows can only help), the record is lowered in the same pull
  request and the change is listed.
- **Every window by keyboard.** The keyboard journeys grow from three windows
  to every window the seeded world can open without saving anything: focus
  moves in, Escape leaves it open, Tab stays inside, the X closes it, focus
  comes back. A yes/no question over a window: Escape answers No and leaves
  the window under it open.
- **No window built by hand again.** A page-suite guard fails if anything
  outside `part-dialog.js` builds a `modal-overlay`.
- **The fixers stay gone.** A page-suite guard fails if `syncDialogs` or the
  window observers come back.

## `docs/DESIGN.md`, the one current rulebook

The design rules live in four dated specs today (tokens, 7 Sep; the brand
system's section 5, 5 Oct; the mix, 6 Oct; panels, 13 Oct), each amending the
last. `docs/DESIGN.md` states the rules as they stand, once, with a link to
the spec each came from:

- **Principles:** one source per decision; parts own their behaviour; no
  arbitrary values; nothing drawn that the data does not support.
- **Tokens:** the three tiers, where they live (`static/src/css/tokens.css`),
  how they are named, and the guards that hold them.
- **Recipes:** corner roles, one tag, one notice, one link, one change chip,
  selection.
- **Layout:** the grey page and its panels, gaps, equal heights, tables to the
  panel's edges.
- **Parts:** the window part (this piece), with each later piece adding its
  own (buttons and links, switches and fields, tables and rows, panels).
- **Adding a part:** where it goes, what it must own, its guard, its keyboard
  journey, its line in this document.

The dated specs stay where they are, as the record of how each rule came to be.

## Not in this piece

- The browser's native `<dialog>` element. Once every window is built by one
  part, moving to it is a change to one file; it changes how Escape and the
  backdrop behave and look, so it is its own decision.
- Buttons, links, switches, fields, tables and panels: pieces 2 to 5.
- The Production Manager's queue, which is frozen. Its windows (the order edit,
  dispatch, the size rules) are not the queue and move to the part like the
  others; nothing in the queue's rows, columns, statuses or actions changes.

## Release note

One line, dated the merge day: every window is now built by one part, so they
all open, close and hand focus back the same way (and the starter-password
window has an X like the rest).
