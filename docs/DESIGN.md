# Design

The rules Reactor's screens follow, as they stand today. Each rule came from a
dated spec, linked beside it; this page is the current word, and the specs are
the record of how each rule came to be. Values are never written here: they
live in `static/src/css/tokens.css`, and the Guide's Design page draws them
live.

## Principles

- **One source per decision.** Every value is a token in `:root`. Outside it,
  rules use `var(--...)` only; the exceptions are 0, 1px hairlines and
  percentages. Markup carries no style attributes.
  ([tokens](superpowers/specs/2026-09-07-design-system-tokens-design.md),
  [the mix](superpowers/specs/2026-10-06-reactor-mix-design.md) §3)
- **Parts own their behaviour.** A window, and from the later pieces of the
  audit's stage 3 a button, a field, a table and a panel, is built by one
  part that gives it its role, name, keys and focus. Nothing is stamped on
  afterwards. ([windows](superpowers/specs/2026-10-15-window-part-design.md))
- **Numbers first, words on request.** A figure is the biggest thing in its
  block, its label two to four words; explanations sit behind an info button
  or in the Guide. ([the mix](superpowers/specs/2026-10-06-reactor-mix-design.md) §3)
- **Teal means chosen.** The chosen tab, chooser or counter, the open row,
  links, the expected series and the one primary action on a screen.
- **Nothing drawn that the data does not support**, and no illustrations.
- **Every target fits a finger on a phone,** and hover effects only on
  devices that hover.

## Tokens

Three tiers in `static/src/css/tokens.css`: primitives (the only place a hex
value may appear), semantic tokens that components read (text, surface, line,
action, status, data, focus, shadow, type, space, corners), and component
tokens (control heights, the sidebar, the panel).
([tokens](superpowers/specs/2026-09-07-design-system-tokens-design.md),
[brand](superpowers/specs/2026-10-05-brand-design-system-design.md) §5)

The guards in `tests/test_frontend.py` hold them: no colour outside the
primitives, every `var(--x)` defined and every token read
(`t_every_defined_token_is_read`), no raw sizes in screen CSS, every `@media`
width on the scale, the script painting from tokens only
(`t_the_script_paints_from_tokens_only`), and every corner a role
(`t_every_corner_is_a_role`).

## Recipes

- **Corners are roles,** never sizes: control, field, row, card, inset, tag,
  swatch, pop, sheet; round only for a switch, a bar, a dot and the tab
  underline. No pill-shaped buttons, inputs or tabs.
- **One tag:** the tag height and corner, caption type, a tint, no border.
- **One notice:** tinted by its tone, no border, the inset corner.
- **One link:** teal, underlined in a quiet line that turns teal on hover.
- **One change chip:** a tag with the arrow and the percentage, green or red,
  and a hidden "up" or "down" for screen readers. Never colour alone.
- **Selection:** one chosen-control look and one selected-row look (the teal
  wash), the segmented thumb white on a grey well.
([brand](superpowers/specs/2026-10-05-brand-design-system-design.md) §5,
[the mix](superpowers/specs/2026-10-06-reactor-mix-design.md) §4 and §6)

## Layout

- **A grey page and white panels.** Every section of a page sits in a panel
  (the canvas, panel edge, corner, shadow, padding and gap are tokens); the
  page's header, its tabs and its notices stay on the grey.
- **Headings belong inside their panel.** A section's heading, count, info
  button and tools sit at the top inside it.
- **Tables run to their panel's edges,** their outer cells on the panel's
  inset; on a phone a row reads as two lines.
- **Panels side by side are one row** with one top and one bottom edge; when
  a pair stacks, each is as tall as its content.
- **Paper is untouched:** printed labels, A4 and courier sheets keep their own
  rules.
([panels](superpowers/specs/2026-10-13-panels-design.md))

## Parts

### Windows

`dialog()` in `static/src/js/part-dialog.js` builds every window
([spec](superpowers/specs/2026-10-15-window-part-design.md)):

- a modal dialog named by its own title;
- a window holding work has an X named Close and, with its own answers (Save,
  Cancel, Done), no other way out: never Escape, never a click outside it. A
  question or notice answered by its own buttons has no X, and the yes/no
  question (`uiConfirm`) alone answers Escape, with No;
- focus moves in as it opens and back to what opened it as it closes (to the
  redrawn control with the same `data-focus-key` when the page was redrawn);
- Tab stays inside the window on top;
- it closes through the part (`win.close()`) and nothing else.

The Settings window, written into the page, opens and closes with
`dialogShow()` and `dialogHide()`. Guards: `t_every_window_is_built_and_closed_by_the_part`,
`t_the_window_part_keeps_one_stack`, `t_the_window_fixers_stay_gone`, and the
browser suite's keyboard journeys (`tests/browser/keyboard.spec.js`).

### Buttons

`textButton(text, opts)` in `static/src/js/part-button.js` builds every
ordinary button ([spec](superpowers/specs/2026-10-19-buttons-and-links-design.md)):
`kind` is `primary` (the one teal per screen), `danger` (a one-way door, the
confirming button of a destructive question) or `ghost`; `square` is the
bordered square that holds one icon; `cls` carries a screen's layout hooks.
`small` builds `btn-sm`, which is the same 32 button: the name is kept until
the stylesheet is put in layers. A button inside a frozen print function keeps
its hand-built form. Guard: `t_every_ordinary_button_is_built_by_the_part`.

### Icon buttons

`iconButton(icon, label, opts)` builds every icon-only button: the grey icon,
one hover (the tertiary surface and primary ink), the control corner, and a
name always (`aria-label`; `title` is the same, or a short form given as
`opts.title`). Three sizes:

| Size | Box | Icon | For |
|---|---|---|---|
| `regular` | 32 | 16 | toolbars, headers, a window's X, rows of 32 controls |
| `small` | 24 (32 under a finger) | 14 | crosses on toasts and alerts, dense rows (Memory, chat) |
| `tag` | 20, tag corner | 12 | the cross inside a chip |

Tones: `danger` hovers red, `ok` green. On a phone a regular one is 40 wide; a
small or tag one keeps its size and gets an invisible 40 target. Guards:
`t_every_icon_button_is_built_by_the_part`, `t_the_retired_button_recipes_are_gone`,
`t_small_icon_buttons_keep_their_size_on_a_phone`.

### Links

`textLink(text, opts)` builds the one text link (teal, underlined in a quiet
line that turns teal on hover): `caption` (12, the default), `inline` (the size
of its sentence) or `go` (standing alone, a chevron after the words, or the
icon given). It builds the legacy classes `linkish`, `seclink` and `link`. The
sign-in card's links are caption links. Guards:
`t_every_text_link_is_built_by_the_part`, `t_the_sign_in_card_uses_the_house_link`.

### Switches

A switch is a button with the switch role that says its own state.
`switchBtn(label, on, onToggle)` (with the structured-response parts) builds
one in the script; the Settings switches are written into the page as
switches, named by the title beside them (`aria-labelledby`, the line under it
as `aria-describedby`). `setSwitch(sw, on)` in `static/src/js/part-field.js`
turns a switch's look and its spoken state together, so nothing stamps a state
on afterwards ([spec](superpowers/specs/2026-10-19-switches-and-fields-design.md)).
Guards: `t_settings_switches_are_named_switches`, `t_the_switch_fixers_stay_gone`.

### Fields

`formField(caption, control, opts)` builds every captioned field: the house
label (14 medium, primary ink) above its control, a help line under it
(`opts.help`), a screen's layout hook (`opts.cls`). The control may be added
afterwards. The look of the field itself is one recipe applied to the element.
Guard: `t_every_captioned_field_is_built_by_the_part`.

### Names

Every control has a name a screen reader reads out: a caption built round it,
an `aria-label`, an `aria-labelledby` or a title. A placeholder is not a name:
it goes as soon as someone types. A box in a list is named for its row
("Select Marcus Bell"). The browser suite checks every visible control on every
measured screen and in every window the keyboard journeys open, with zero
tolerance. Guards: `t_no_field_is_named_only_by_its_placeholder` and the
browser suite's "controls with no name".

### Rows

A row that opens something is not a button: a screen reader cannot present a
button inside a button, and a row's own tick, link or Claim would be one.
`rowOpener(label, onOpen)` in `static/src/js/part-row.js` builds a real button,
visually hidden, named for the row ("Open: Invoice copy please, from Accounts
Team"); its Enter and Space stop at it, so a page-wide shortcut never acts on
them too. The row draws its focus ring while that button has focus
(`:has(.row-open:focus-visible)`). `opensOnClick(row, onOpen)` keeps a click
anywhere on the row opening it, except on a control of its own. The Inbox, CRM
Contacts and the deals list use both. A row that already holds a button doing
the same thing needs no opener: the Production Manager queue opens an order
from its Preview button
([spec](superpowers/specs/2026-10-19-rows-design.md)).
Guard: `t_no_row_is_a_pretend_button`, and the keyboard journeys.

### Tick rows

A tick (or a radio) and its words are one `<label>`: `tickRow(cls)` builds it,
with the body text in primary ink, and `cls` a screen's spacing hook.
Guard: `t_every_tick_row_is_built_by_the_part`.

## Adding a part

A part lives in its own section, `static/src/js/part-<name>.js`, listed in
`static/src/manifest.json`. It must:

1. build today's markup and classes, so the stylesheet does not change when
   screens move onto it;
2. own its role, name, keys and focus, so nothing is stamped on afterwards;
3. come with a page-suite guard that fails when the thing it builds is built
   by hand anywhere else;
4. come with a keyboard journey in the browser suite when it can be operated;
5. get its section under Parts here.
