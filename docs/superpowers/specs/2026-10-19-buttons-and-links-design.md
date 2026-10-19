# Buttons, icon buttons and links as parts

**Approved 19 Oct 2026.** Stage 3, piece 2 of the 14 October engineering audit.
Cameron skipped the questions and asked for a proposal; he approved all three
parts below after seeing the before-and-after sheet, including the sign-in
card's link becoming the house link.

## Why

Reactor builds 475 buttons by hand in 93 class strings. The ordinary buttons
are already consistent: plain, primary, danger and quiet each have one look,
and "small" (`btn-sm`) is defined as the same 32 button. The drift is in the
small controls around them:

- **Icon-only buttons** come in five recipes. Measured in Chromium: `icon-btn`
  32, `mem-btn` 24 (32 on touch and beside Skills' "Use in chat"),
  `alert-x` 22 with no minimum size, `toast-x` 24 with no hover fill and a
  square corner, `sk-chip-x` 20 with the tag corner and a smaller icon. Some
  carry a name a screen reader can read; some do not.
- **Text links** come in four: `linkish` (12, the house link), `seclink`
  (the house link at the size of its sentence), `link` (stand-alone, with a
  chevron) and `auth-link` on the sign-in card (black, underlined only on
  hover).

## What changes

One new section, `static/src/js/part-button.js`, holds three parts. (Built as `textButton()` and `textLink()`: plain `button` and `link` were already local names in several functions, where a part of that name would be shadowed.) Each
builds markup the stylesheet already styles, so only the changes approved
below are visible.

### `textButton(text, opts)`, the ordinary button

`textButton('Save', { kind: 'primary' })` builds `<button class="btn btn-primary">Save</button>`.
Options: `kind` (`primary`, `danger`, `ghost`), `small` (today's `btn-sm`,
kept until the stylesheet is put in layers in piece 6, since it is the same
button), `square` (today's `btn-icon`, a bordered square holding one icon),
`cls` (extra classes a screen uses as layout hooks), `icon` (an icon before the
words), `title`. With no text, it builds the empty button and the caller fills
it, as the call sites do today. About 340 call sites move to it with **no
visible change**: the classes it builds are the classes they had.

### `iconButton(icon, label, opts)`, the icon-only button

`iconButton(I.trash, 'Delete note', { size: 'small', tone: 'danger' })`. One
recipe: the grey icon colour, the same hover fill (the tertiary surface and
primary ink), the control corner, and a name (`aria-label` and `title`)
always. Three sizes from the tokens:

| Size | Box | Icon | For |
|---|---|---|---|
| `regular` (default) | 32 (`--control-h`) | 16 | toolbars, headers, window X, rows with 32 controls |
| `small` | 24 (`--control-h-sm`) | 14 | crosses on toasts and alerts, actions in dense rows (Memory, chat) |
| `tag` | 20 (`--box-sm`), tag corner | 12 | the cross inside a chip |

Tones: `danger` (hover red, today's `.mem-btn.del`) and `ok` (hover green,
today's `.mem-btn.ok`). On a phone, a regular icon button is 40 wide as today;
small and tag keep their size and get a 40 invisible target (today's rule for
the crosses).

It builds `icon-btn` (regular), `icon-btn icon-btn-sm`, `icon-btn icon-btn-tag`,
plus `del` / `ok` for a tone. The `mem-btn`, `alert-x`, `toast-x` and
`sk-chip-x` recipes are retired, their contextual rules moved onto the new
classes. The window part's X is built by `iconButton`. **Visible change**: the
toast and alert crosses, the chip cross and the 24 row actions take the one
recipe (sizes nearly unchanged; the toast cross gains the hover fill and
corner, the alert cross gains its 24 box, the row actions' icon goes from 16 to
14). Skills' row actions stay 32 beside "Use in chat".

Not in this piece: the sidebar's conversation delete (`.convo .del`, a sidebar
part with its own muted ink), a chart's expand button, a figure's open button
and the chat send button, each part of a component with its own look.

### `textLink(text, opts)`, the text link

One link: teal, underlined in a quiet line that turns teal on hover. Sizes:
`caption` (12, today's `linkish`), `inline` (the size of its sentence, today's
`seclink`), and `go` (stand-alone, the chevron after the words, today's `link`).
It builds those classes. `auth-link` is retired: the sign-in card's link
becomes a caption link. **Visible change**: that link only.

## Guards

- A page-suite guard fails when any section other than `part-button.js` builds
  a button with `btn`, `icon-btn`, `mem-btn`, `alert-x`, `toast-x`, `sk-chip-x`,
  `linkish`, `seclink`, `link` or `auth-link` by hand.
- The retired recipes' classes appear nowhere in the stylesheet or the script.
- The parts run for real in the page suite's node harness: classes, name,
  sizes, tones.
- The browser suite runs every screen against its record: no count may go up.
  Icon buttons all named can only lower accessibility findings; if they go
  down the record is lowered in the pull request and the change listed.
- Before-and-after screenshots of the 108 states: only the states that show
  a changed control may differ; the list goes in the pull request.

## Documentation and release note

`docs/DESIGN.md` gains Buttons, Icon buttons and Links under Parts. One
release note, dated the merge day: the small buttons that close and act on
things now look and behave the same everywhere, and every one has a name a
screen reader reads out.

## Not in this piece

The names in CRM tables that open a record (`dt-link`, plain text on purpose)
belong with tables and rows (piece 4). Renaming the legacy classes the parts
build (`btn-sm`, `seclink`) waits for the stylesheet in layers (piece 6).
