# Reactor in Projected Image's brand: one source of truth

Cameron, 5 October 2026: "we need to make app wide design improvements",
"uniformity is key, all of the screens need to be cohesive and feel part of the
same app and family", "one source of truth is also vitally important". They
chose a refreshed look drawn from Projected Image's brand, kept inside Reactor,
built as shared parts first and every screen rebuilt on them, pilot first. They
approved the brand section below and said "build it".

## 1. The brand, defined once (approved)

Every value lives in the one `:root` block at the top of `static/index.html`
(three tiers: primitives, semantic, component). No screen defines a colour, font,
size, corner or shadow of its own; `tests/test_frontend.py` refuses raw values
outside `:root`.

| Role | Value | Why |
|---|---|---|
| Primary action | teal `#13B7C0` fill, ink `#121212` text | the website's buttons; ink on teal 7.64:1 |
| Hover / pressed | `#11A6AF` / `#0F9097` | ink stays 6.33:1 / 4.87:1 |
| Teal text, links, focus outline | `#0B6B71` | 6.26:1; the bright teal is 2.45:1, never text |
| Selected border, marks (dots, bars, tab underline, switch) | `#0F9097` | 3.85:1, seen against white |
| Selected wash (nav item, selected segment) | `#F1FBFB` | teal 6% on white |
| Text | ink `#121212`; secondary/tertiary neutrals unchanged | |
| Page / card | off-white `#F7F7F7` page, white cards with a hairline | |
| Information | brand blue `#334FB4` | 7.2:1 |
| Charts | teal, dark teal `#08484C`, blue, grey `#737373`, amber | the grey is 4.7:1; the lighter grey was 2.6:1, under the 3:1 a line needs |
| Titles | Bricolage Grotesque (self-hosted) | the brand's heading face |
| Everything else, every figure | Inter, tabular numbers | |
| Shape | 6px for every control and field (`--radius-control`, `--radius-field`); 8px cards, windows and menus (`--radius-card`); 6px for a box inside a card (`--radius-inset`); 4px for tags and badges (`--radius-tag`); round only where the shape means something (switch, progress bars, dots, avatars, the tab underline) | Cameron, 5 Oct: "Do not use pill-shaped UI unnecessarily", reversing the pilot's website pills; an inner corner is never rounder than its frame |
| Shadows | none under what sits on the page; menus, dialogs, drawers keep theirs | |
| Density | 32px controls, 14px body, compact tables | a working tool, not the airy website |
| Identity | Projected Image wordmark, then "Reactor", top of the sidebar | |

What counts as a title is ONE list, the `:is(...)` rule after `:root`.

## 2. The shared parts

A screen is composed only of these. Each is one builder in the page script and
one block of CSS. A screen may pass content and options; it may not restyle.

| Part | Builder | Replaces |
|---|---|---|
| Tabs (move between sections; underline) | `tabStrip(items, current, onPick, opts)` | `financeTabs`'s `.ptabs`, `filterTabs`'s `.ftab`, section-switching `.lbl-seg` (Production Manager, CRM), the Guide's own |
| Segmented control (a choice within a card; white track, teal-washed selection) | `segmented(items, current, onPick, opts)` | `segControl`'s `.seg`, filter `.lbl-seg` |

Both are one `chooser()` underneath: items are `[key, label]` or
`{key, label, extra, title, disabled}`; `opts.nav` marks a strip that changes
page with `aria-current`, otherwise the chosen one carries `aria-pressed`.
| Page header (title, description, stamp, actions) | `heroAct` + `.ov-hero` (already shared) | per-screen headers |
| Card (title, description, actions, body) | `.card` / `.card-head` (already shared) | |
| Figures strip | `metricsStrip` (already shared) | |
| Table | `.ktable` via one builder | 24 hand-built tables (the look is already shared) |
| Buttons, chips, status tags, fields, windows, empty states | existing shared classes | |

## 3. Enforcement

- A test refuses a new CSS rule whose selector is screen-specific unless it is on
  an allow-list that only shrinks (printed sheets and labels keep theirs: they
  are physical output with their own paper values).
- Tests pin that every tab strip is built by `tabStrip()` and every segmented
  control by `segmented()` (`t_two_choosers_and_nothing_else`).
- Design, an admin-only section of the Guide (not a twenty-first screen),
  draws every part with the builders the screens use and reads each colour
  from the tokens as the browser resolves them, with its contrast
  (`paintDesign`, `t_the_design_page_is_the_source_of_truth_made_visible`).

## 4. Rollout

1. Pilot (branch `design/brand-foundation`): the brand values app-wide,
   `tabStrip()` and `segmented()` across every screen, the corner roles, the
   Design section. Swept on all 20 screens and the Guide's sections at 1440px
   and 375px: no script errors, nothing wider than the screen, no bright teal
   used as text, no old corner left. Cameron approves the look before it
   ships. The one-off-selector guard moves to step 2, where each group's
   one-off CSS is deleted, so it starts from a list that only shrinks.
2. Screens in groups (Finance, Operations, Reports, Workspace), each moved onto
   the shared parts with its own one-off CSS deleted, reviewed at desktop and
   phone widths, shipped through a pull request.

Out of scope: the Quote Engine (hands off), the Shopify print extensions (they
are Shopify's own components), and the printed label and A4 sheets' layout.

## 5. The polish pass: the source of truth (5 October 2026)

Cameron's brief: "beautiful, cohesive, intentional ... Do not use pill-shaped UI
unnecessarily ... a single source of truth ... spacing should feel intentional".
Three designer audits (stylesheet, report and operations screens, workspace and
shell; 86 findings) settled these rules. Every value is a token in `:root`; the
Guide's Design section draws them live; `tests/test_frontend.py` guards them.

**Shape.** `--radius-control` 6 (buttons, fields, choices, chips, pager steps,
icon buttons), `--radius-field` = control, `--radius-row` = control (nav, menu,
conversation rows), `--radius-card` 8 (cards, windows, menus, toasts),
`--radius-inset` 6 (a box inside a card), `--radius-tag` 4 (labels that only
display), `--radius-swatch` 2 (legend keys). Round (`--radius-full`) only for a
switch, a progress bar, a dot and the tab underline. A segmented choice is the
control radius less its 2px inset. `t_every_corner_is_a_role` refuses a raw
size outside `:root` (printed sheets, the scrollbar and the sign-in card are
the named exceptions).

**Size.** Controls 32 in forms, 28 in toolbars, card heads, page and top-bar
actions; tabs 24; a segmented track 28; tags 20 (`--tag-h`). One height per row.
Icon-only buttons are square by token. Control text is 14 everywhere (buttons,
small buttons, chips, choices, fields); 12 only for tags, meta and captions.
Icon to text in a control `--control-gap` 6; icons 16 in regular controls and
rows, 14 in compact ones, 12 in tags; tinted grey, never faded.

**Type.** Ranks: page title 30 regular, section heading over a group of cards
18, card and chart title 16 medium (all Bricolage, one list), a label inside a
card 14 medium, body 14, meta 12. One reading measure, `--measure` 62ch, for all
prose. No tracking below 20px.

**Spacing.** Page blocks 24 (16 on a phone); header to tabs 16; a section
heading 12 above its block; card padding and gaps 16; title to description 4;
fields 16 apart with the label 4 above; rows 12 vertical padding. Tabs are as
wide as their label, 24 apart (16 on a phone), the first on the page's text edge.
A card header's text keeps 18rem and its button rail has the rest (never less
than half). Icons stay on at every size.

**Containers.** A card is one job and the frame for what is in it: a table
inside a card draws no second frame and, placed straight in the card, runs to
its edges like a list with its outer cells on the 16 gutter; an empty list inside a card is a quiet
first line, a notice spans its card. Groups of drawers are one card of divided
rows. One notice recipe (tint by tone, no border, inset corner, 12/16, 14px).
One tag recipe (20 tall, 4px, 12/500, tint, no border).

**Interaction.** One chosen-control look (teal wash, teal text, selected edge),
one selected-row look (the wash, no stripe), the segmented thumb white on a
grey well. Choices: a short fixed set is a segmented track; a long fixed list (Forecast's
seven ranges) is a compact select (`choiceSelect()`). On a phone a track of two or three fills its line, and
four or more wrap into even rows, never scrolling a choice out of sight. One link (teal, underlined in a quiet line). One teal button per
screen. A menu trigger is its name then a caret. Floating layers (menus,
dialogs, the open drawer, toasts) carry the large shadow; nothing on the page
does.
