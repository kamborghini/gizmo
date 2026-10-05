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
| Shape | pills for anything pressed or toggled (`--radius-control`); 8px cards, windows and fields (`--radius-card`, `--radius-field`); 6px for a box inside a card (`--radius-inset`) | the website's buttons and cards; an inner corner never rounder than its frame |
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
| Segmented control (a choice within a card; white pill track, teal-washed selection) | `segmented(items, current, onPick, opts)` | `segControl`'s `.seg`, filter `.lbl-seg` |

Both are one `chooser()` underneath: items are `[key, label]` or
`{key, label, extra, title, disabled}`; `opts.nav` marks a strip that changes
page with `aria-current`, otherwise the chosen one carries `aria-pressed`.
| Page header (title, description, stamp, actions) | `heroAct` + `.ov-hero` (already shared) | per-screen headers |
| Card (title, description, actions, body) | `.card` / `.card-head` (already shared) | |
| Figures strip | `metricsStrip` (already shared) | |
| Table | `.ktable` via one builder | 24 hand-built tables (the look is already shared) |
| Buttons, chips, status pills, fields, windows, empty states | existing shared classes | |

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
