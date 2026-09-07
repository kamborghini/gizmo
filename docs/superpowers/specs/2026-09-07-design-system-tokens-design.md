# Design system tokens for the gizmo SPA

Date: 2026-09-07. Status: approved, in implementation.

## Why

`static/index.html` carries a 3,088-line stylesheet with 62 custom properties
and 1,987 `var()` reads, so the app is mostly tokenised already. What it lacks
is a *system*: names say what a colour is (`--ink`, `--win`, `--opp`) rather
than what it is for; two type steps are duplicates; there are no tokens at all
for line-height, border width or breakpoints; 632 spacing declarations bypass
the scale; and three separate hex palettes live in JavaScript. The measured
state on 2026-09-07:

| Family | Measured |
|---|---|
| Colour | 76 hardcoded uses (34 distinct) in CSS; `CH`, `CRM_COLOR_CSS` and the composer palette in JS; `--warn-ink` and `--mono` read but never defined |
| Typography | `--t-xs` = `--t-sm` = 12px; `--t-body` = `--t-md` = 14px (`--t-body` unread); 71 literal line-heights across 18 values; 3 monospace stacks, 3 Bricolage stacks |
| Spacing | 632 literal declarations, 165 distinct values, 3/5/7/9/13/14/18/34px drift; 61 `style.marginTop = 'Npx'` in JS |
| Border width | none tokenised: 1px x140, 2px x11, 3px x8, 0.5px x2 |
| Shadows | 2 tokens, 22 distinct literals |
| Breakpoints | 49 media queries over 19 distinct widths |
| States | primary hover = pressed; danger hover/pressed hex; icon and nav buttons have no pressed state; 3 disabled recipes; input focus rule copied 9 times; no invalid, loading or cancelled recipe |
| Header | one `.topbar`, 48px at every width and view, collapse at 760 in one block; a long title wraps to 63px inside the 48px bar |

## Token architecture

One `:root` block, three tiers. Hex is legal only in tier 1.

### Tier 1: primitives

Named by the Tailwind step they came from; custom steps carry a comment.

```
--white #ffffff  --black #000000
--neutral-50 #fafafa  --neutral-100 #f5f5f5  --neutral-150 #ebebeb (custom third step)
--neutral-200 #e5e5e5  --neutral-300 #d4d4d4  --neutral-400 #a1a1a1
--neutral-500 #737373  --neutral-550 #696969 (custom: AA on every ground)
--neutral-600 #525252  --neutral-800 #262626  --neutral-900 #171717  --neutral-950 #0a0a0a
--red-50 #fef2f2  --red-300 #fca5a5  --red-500 #ef4444  --red-700 #b91c1c  --red-800 #991b1b  --red-900 #7f1d1d
--orange-700 #c2410c
--amber-50 #fffbeb  --amber-700 #b45309  --amber-800 #92400e  --amber-900 #78350f
--green-50 #f0fdf4  --green-700 #15803d
--blue-50 #eff6ff  --blue-700 #1d4ed8
--purple-50 #faf5ff  --purple-700 #7e22ce
--pink-700 #be185d
```

### Tier 2: semantic (what components read)

| Group | Tokens |
|---|---|
| Text | `--text-primary` 950, `--text-secondary` 600, `--text-tertiary` 550, `--text-disabled` 400, `--text-on-action` white, `--text-link` 900 |
| Surface | `--surface-primary` white (page and card), `--surface-secondary` 50 (sidebar, row hover), `--surface-tertiary` 100 (muted fills, control hover), `--surface-sunken` 150 |
| Border | `--border-default` 200, `--border-strong` 300, `--border-emphasis` 400 |
| Action | `--action-primary` 900, `--action-hover` 800, `--action-active` black, `--action-soft` 100, `--action-line` 200, `--action-danger` red-700, `--action-danger-hover` red-800, `--action-danger-active` red-900 |
| Status | `--success`/`--success-bg` green, `--warning`/`--warning-bg` amber-700/50, `--warning-text` amber-800, `--error`/`--error-bg` red-700/50, `--info`/`--info-bg` blue, `--opportunity`/`--opportunity-bg` purple |
| Data | `--chart-1..5` = neutral 900/600/500/400/300; `--ageing-1..4` = red 300/500/700/900; `--owner-red/orange/yellow/green/blue/purple/pink/brown/gray/dark-gray` and `--owner-*-bg: color-mix(in srgb, var(--owner-*) 10%, var(--white))` (the eight existing tints are exactly that mix) |
| Focus and overlay | `--focus-ring: 0 0 0 3px color-mix(in srgb, var(--neutral-950) 18%, transparent)`, `--focus-outline: var(--bw-strong) solid var(--action-primary)`, `--overlay-scrim: color-mix(in srgb, var(--neutral-900) 32%, transparent)`, `--overlay-edge` (the .45 ink ring on the ageing bar) |
| Shadow and ring | `--shadow-sm` (card), `--shadow-md` (menus), `--shadow-lg` (sheets, open sidebar), `--shadow-knob`; `--ring-default`, `--ring-strong`, `--ring-emphasis`, `--ring-action`, `--ring-action-2` (inset hairlines for things that cannot carry a border) |
| Paper (print sheets) | `--paper` white, `--paper-ink` black, `--paper-ink-2` #333, `--paper-ink-3` #222, `--paper-rule` #ddd, `--paper-rule-2` #bbb, `--paper-rule-strong` #111 |
| Typography | `--font-sans`, `--font-mono`, `--font-print`; `--text-xs` 12, `--text-sm` 14, `--text-md` 16, `--text-lg` 18, `--text-xl` 20, `--text-2xl` 30; `--weight-regular` 400, `--weight-medium` 500, `--weight-semibold` 600; `--lh-none` 1, `--lh-tight` 1.15, `--lh-snug` 1.35, `--lh-body` 1.5, `--lh-prose` 1.6, `--lh-control` 20px |
| Spacing | `--sp-0-5` 2, `--sp-1` 4, `--sp-1-5` 6, `--sp-2` 8, `--sp-2-5` 10, `--sp-3` 12, `--sp-4` 16, `--sp-5` 20, `--sp-6` 24, `--sp-7` 32, `--sp-8` 40 |
| Radius | `--radius-2xs` 4, `--radius-xs` 6, `--radius-sm` 8, `--radius-md` 10, `--radius-lg` 14, `--radius-full` 999px (pills), `--radius-circle` 50% (dots and avatars) |
| Border width | `--bw-hairline` 1px, `--bw-strong` 2px, `--bw-marker` 3px |
| Motion | `--dur` .15s, `--ease` |
| Layout | `--wrap`, `--wrap-pad` (unchanged) |

### Tier 3: component

`--control-h` 32px, `--control-h-sm` 24px, `--control-pad-y` 5px (documented as
(32 - 20 line - 2 border) / 2), `--sidebar-w` 272px, `--topbar-h` 48px.

### Breakpoints

Custom properties cannot be read inside `@media`, so the scale is a comment in
`:root` and a test. Seven stops: **640** phone, **760** sidebar collapses,
**900** tablet, **1100** KPI row goes to four columns, **1200** dispatch row
goes single-line, **1500** wide, **1800** ultra-wide. Folds: 560/600/620 to
640; 700/720 to 760; 960 to 900; 2100 to 1800. Complements (641, 761, 901,
1101, 1201) are the same stop.

### Name migration

Old names are deleted, not aliased. Every read is rewritten mechanically:

```
--bg,--surface        -> --surface-primary      --bg-2               -> --surface-secondary
--surface-2           -> --surface-tertiary     --surface-3          -> --surface-sunken
--border,--line       -> --border-default       --border-2           -> --border-strong
--border-3            -> --border-emphasis      --ink                -> --text-primary
--ink-2               -> --text-secondary       --ink-3              -> --text-tertiary
--accent,--accent-ink -> --action-primary       --accent-2           -> --action-hover
--accent-soft         -> --action-soft          --accent-line        -> --action-line
--win/-bg             -> --success/-bg          --warn/-bg           -> --warning/-bg
--info/-bg            -> --info/-bg             --opp/-bg            -> --opportunity/-bg
--danger/-bg          -> --error/-bg            --r                  -> --radius-lg
--r-md/-sm/-xs        -> --radius-md/-sm/-xs    --r-pill             -> --radius-full
--sh-1/--sh-2         -> --shadow-sm/--shadow-lg --focus             -> --focus-ring
--t-xs,--t-sm         -> --text-xs              --t-md,--t-body      -> --text-sm
--t-lg                -> --text-md              --t-head             -> --text-lg
--t-xl/--t-2xl        -> --text-xl/--text-2xl   --w-normal/medium/bold -> --weight-regular/medium/semibold
--font                -> --font-sans
```

Two mappings change a value on purpose: `--accent-2` read as a *hover* colour
becomes `--action-hover` (#262626, lighter, as shadcn's `primary/90`) and as a
*pressed* colour becomes `--action-active` (black). Every other mapping resolves
to the identical value.

## Component state contract

Defined once, applied to every control family (`.btn`, `.btn-primary`,
`.btn-danger`, `.icon-btn`, inputs/select/textarea, `.nav-item`, rows, `.chip`,
`.toggle`, `.lbl-segbtn`, `.send`, `.mail-claim`):

| State | Recipe |
|---|---|
| Hover | secondary and ghost: `--surface-tertiary`; primary: `--action-hover`; danger: `--action-danger-hover` |
| Focus | one rule: `:focus-visible` outline `--focus-outline` for buttons, links and rows; `--focus-ring` box-shadow for fields. The nine copied field rules and the one outline variant are removed |
| Pressed | `:active`: secondary `--surface-sunken`; primary `--action-active`; danger `--action-danger-active`; icon and nav `--surface-sunken` |
| Selected | existing `.on` / `.selected` / `.active` keep working; `[aria-pressed="true"]`, `[aria-selected="true"]`, `[aria-current]` are added to the same rules |
| Disabled | `:disabled, [aria-disabled="true"]`: filled controls get `--surface-tertiary` fill, `--text-disabled`, `--border-default`, `cursor: not-allowed`; ghost/icon controls get `--text-disabled` and no fill. Opacity recipes (.35/.4/.75) go |
| Loading | `[aria-busy="true"]`: `cursor: progress; pointer-events: none`, leading svg spins; `.spin` and `.thinking` stay as the existing loaders |
| Invalid | fields `[aria-invalid="true"]`: `--error` border, `0 0 0 3px var(--error-bg)` ring |
| Success / completed | `--success` on `--success-bg`; `.done` keeps its strike-through |
| Error | `--error` on `--error-bg` |
| Cancelled | `.is-cancelled, [data-status="cancelled"]`: `--text-tertiary` + `line-through` |

## Header

`.topbar h1` gains `min-width: 0; overflow: hidden; text-overflow: ellipsis;
white-space: nowrap` and `setView` writes the full title into `title=`. Nothing
else changes: one header, one collapse point (760), heights already constant.

## JavaScript sources

A `tokenValue(name)` helper reads a token from the root computed style. `CH`,
`CRM_COLOR_CSS` and the composer's `COLOURS` are built from it, so a colour that
ends up inside an email or an SVG still has a single source. `style.marginTop =
'Npx'` sites move to `.mt-1 .. .mt-4` utilities; the five inline monospace
strings move to `.mono`. `--warn-ink` becomes `--warning-text`.

## Print sheets

`.label-sheet`, `.day-sheet` and `.loan-sticker` are physical artefacts sized in
mm and em so a 4x4 and a 4x6 label scale together. They read the `--paper-*`
tokens and `--font-print` and keep em sizing. This is the documented exception
to the px rule.

## Enforcement (tests in `tests/test_frontend.py`)

1. No hex/rgb/hsl outside the primitives block, except the mask-image gradient
   and the select chevron data URI, both listed.
2. Every `var(--x)` names a defined token; every defined token is read at least
   once (scale members excepted).
3. Screen CSS carries no px literal in font-size, line-height, padding, margin,
   gap, border-radius, box-shadow or border-width; `0` and `auto` allowed; the
   print sheets allowed.
4. Every `@media` width is on the seven-stop scale.
5. No legacy token name remains anywhere in `static/` or `tests/`.
6. The script contains no `style.marginTop = 'Npx'` and no hex in `CH` or
   `CRM_COLOR_CSS`; the composer builds its palette from tokens.
7. Each control family declares hover, focus-visible, active and disabled;
   fields declare `[aria-invalid]`; buttons declare `[aria-busy]`.

## Verification

A computed-style snapshot (colour, background, borders, radius, shadow, font,
line-height, letter-spacing, padding, margin, gap, outline, opacity, box) of
every element on every view at 375, 760 and 1200, saved through the rig before
and after each commit and diffed in Python.

## Staged commits

1. Tokens and mechanical migration. Snapshot diff must be **zero**.
2. State contract. Default-state snapshot diff zero; state rules verified by
   reading the CSS and by focusing, disabling and busying controls in the rig.
3. Header truncation. Verified at 375 with a 60-character title.
4. Off-grid snaps, breakpoint folds, primary hover/active. Diff must be exactly
   the listed rules.
5. JS sources, utilities, `--warning-text`. Diff zero apart from the amber.
6. Enforcement tests land with the commit that makes each pass.

## Decisions taken

Old names deleted (no alias layer). Off-grid values snapped and breakpoints
folded. `color-mix()` used for derived tints (Safari 16.2+, Chrome 111+,
Firefox 113+). Dark theme stays out of scope; the tiers make it a later
drop-in.
