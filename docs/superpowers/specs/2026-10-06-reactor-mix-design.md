# Reactor, the mix: one look, fewer words

**Status:** Cameron chose the direction and its decisions on 5 October 2026 and asked for this write-up on 6 October. Once he approves it, it is the source of truth for the build.

It supersedes the values in section 5 of `2026-10-05-brand-design-system-design.md`, the polish pass. That spec's architecture stays:
- one token block in three tiers;
- two choosers;
- the guard tests.

Only the values, the parts and the words change.

**Reference:** `docs/design/mix/mix.html` is a working mockup of Forecast and Production Manager on a desktop and a phone, with three details. Open it in a browser. Its `:root` block holds the exact tokens listed in section 4. `label-real.png` beside it is the production label as Reactor printed it from sample orders. It is a picture of the real thing, not a design.

**Appendix:** `2026-10-06-reactor-mix-copy-plan.md` lists every piece of explanatory text in the app, 292 items, each with its proposal.

## 1. Why

After the brand, spacing and polish passes, Cameron's verdict was: "it still all looks very dated and text heavy". The measurements bore it out on 5 October 2026.

- **Most of what a screen says is explanation, not data.**
  - Forecast: 324 of 420 visible words.
  - Production Manager: 102 of 106.
  - Skills: 98 of 105.
  - Memory: 127 of 136.
- **Explanation came in three layers.** A paragraph under every page title, a description under every card title, then a footnote or a long empty-state sentence.
- **Grey on grey.** An off-white page, outlined white cards and grey text. Teal appeared only on buttons, and there was no depth.
- **Data was written as sentences.** "0 orders waiting" was a heading, and a team member was a line of grey meta text.
- **Titles read as a brochure.** They were set in Bricolage at regular weight.

## 2. What Cameron decided

| Decision | Cameron's words |
|---|---|
| The look is a mix of the three directions mocked up: Calm workspace's structure, Data-forward's figures, Brand-bold's focal points | "i think we need a mix of all", then "i like the mix" |
| The dark (ink) sidebar and frame. There is no light variant. | "go with the dark sidebar" |
| Forecast says "method" where it said "source". Range choices are Today, Week, Month, 3 months, 12 months, Months ahead. Worth looking at statuses are Safely ahead, Likely ahead, Likely behind. | "keep the new forecast wording" |
| The open order's Print is the teal main action | "keep ... teal print" |
| The production label, and the queue's content and actions, stay exactly as the app has them | "i dont like how you have changed my production lables" |
| No drawn illustrations. An empty state is an icon tile, one line and its action. | "i hate the stupid projector thing in custom shipments" |
| It has to be exact | "i have severe OCD so it has to be perfect" |

The mockup went through two audits before this spec, each with three reviewers, one writer and an independent verifier:
- **Round 1:** uniformity, spacing, clarity.
- **Round 2:** pixels at 3x, consistency across contexts and states, task walk-throughs.

Final measurements on all seven screens:
- 0 overlaps, clipped text, low-contrast text, mixed-height rows and off-grid values;
- 0 phone targets under 40px;
- 12 text styles on Forecast desktop, down from 24.

## 3. Principles

1. **One source of truth.** Every value comes from the token block. Outside it, rules use `var(--...)` only; the exceptions are 0, 1px hairlines and percentages. Markup carries no style attributes, except data percentages for bar positions.
2. **Numbers first, words on request.**
   - A figure is the biggest thing in its block, and its label is two to four words.
   - Explanations sit behind a small info button or in the Guide.
   - Nothing is deleted that protects someone from a mistake.
3. **One sheet, few boxes.**
   - The page is one white sheet in an ink frame.
   - Inside it, sections are a title and space, and lists are rows split by hairlines.
   - Only four things are boxed: the Forecast feature band, the queue counters, floating layers (menus, popovers, tooltips, dialogs) and the label preview.
4. **Teal means chosen.** Teal marks:
   - the chosen tab, chooser or counter;
   - the open row;
   - links;
   - the expected series;
   - the one primary action on a screen.
5. **One mark, one meaning.** Each measure keeps one colour on every screen (4.1).
6. **Every target fits a finger on a phone.** That means 40px, and hover effects only on devices that hover.
7. **Exact.** Edges sit on the gutter; columns never move between rows; and any button whose label swaps keeps one width.

## 4. The source of truth: tokens

These values are the mockup's `:root` block. The build maps them onto the app's existing three tiers (primitives, semantic, component). It keeps existing names where a role already exists and adds a name only for a new role.

### 4.1 Colour

**Greys**, one ramp:

| Token | Value | Role |
|---|---|---|
| ink | #121212 | text; the Expected marker on a range |
| ink-2 | #3C4043 | secondary text; figure labels |
| ink-3 | #5F6368 | tertiary text, icons, counts (the lightest text allowed) |
| ink-4 | #8A9096 | decorative marks; a switch when off (3.2:1) |
| line-ctl | #DADCE0 | control borders, chart axis |
| line | #E6E7EA | list frames, header rules |
| line-soft | #EEEFF1 | row dividers, chart grid |
| fill | #F3F4F5 | wells, counters, open and hover states |
| sheet | #FFFFFF | the page sheet |

**Brand:**

| Token | Value | Role |
|---|---|---|
| teal | #13B7C0 | a fill only, never text on white |
| teal-hover | #11A6AF | hover |
| teal-line | #0F9097 | lines, the focus ring, the selected-row edge |
| teal-text | #0B6B71 | teal words and links |
| teal-dark | #08484C | money already taken |
| teal-wash | #F1FBFB | the open row |
| teal-glow | #B8E9EC | the likely range as a bar |
| blue | #334FB4 | the plan |

Text on a teal fill is ink.

**Status** pairs 700 text with a 50 tint:

| Status | Text | Tint |
|---|---|---|
| ok | #15803D | #F0FDF4 |
| warn | #B45309 | #FFFBEB |
| bad | #B91C1C | #FEF2F2 |

A live dot is #22A55A with a 15% halo.

**One colour per measure, on every screen:**

| Measure | As a mark | As a series or area |
|---|---|---|
| Taken | teal-dark | teal-dark |
| Still expected | teal at 45% | teal at 45% |
| Expected | ink dot | teal-line line |
| Likely range | teal-glow bar with a teal-line edge | teal at 15% area, with a teal-line 35% key edge |
| Plan | blue tick | blue |

**The ink frame.**
- The chrome is ink.
- Sidebar text is white at 72%, and muted text white at 50%.
- The chrome's fill is white at 12%, and pressed white at 18%.
- The chosen nav item is teal at 18%, with white text and a teal icon.
- The sheet has no edge and no shadow.

**The feature band.** A soft teal gradient, from #D3F1F3 through #DDF4F5 and #EBF8F9 to #F2FBFB. Rules and empty tracks on it are teal-dark at 12%.

### 4.2 Type

Inter, with five steps, each with one line height:

| Step | Size / line | Use |
|---|---|---|
| micro | 11/16 | Beta, keyboard hints, avatar initials |
| caption | 12/16 | legend, chart ticks, table heads, counts, tags, captions |
| body | 13/20 | everything else on a desktop |
| body-l | 14/20 | order names; on a phone, every control and row title |
| head | 15/20 weight 600 | section heads, the empty-state line |

- **Weights:** 400, 500 and 600 only.
- **Tracking:** none, except titles and figures.
- **Display.** Bricolage Grotesque 600, tracking -0.02em, for two things only:
  - the wordmark (16/20);
  - page titles (26/32 desktop, 24/32 phone).
- **Figures.** Inter 600, tabular numbers, line height 1, tracking -0.03em. Four steps: 44, 36, 28, 24. A phone figure is one step down.
  - 44: the Forecast hero.
  - 36: queue counters.
  - 28: side figures.

### 4.3 Sizes

| Token | px | What |
|---|---|---|
| tag | 20 | chips, age tags, keyboard hints |
| ctl-xs | 24 | info and refresh icon buttons |
| ctl-in | 28 | sidebar icon buttons, feature tiles, a chosen segment |
| ctl | 32 | button, field, search, segmented track, queue tab, nav and menu rows, switch, table head |
| row | 44 | one-line rows, the tab strip |
| row-2 | 60 | two-line phone rows |
| orow | 64 | an order row |
| ctl-m | 40 | every target on a phone |
| tile-l | 40 | the empty-state icon tile |

Other sizes:
- **Icons:** 16 at stroke 1.75 in every control, row, tile and nav item. 14 at stroke 2 only for inline glyphs (crumb chevrons, link arrows, list chevrons, chip arrows).
- **Frame:** top bar 48, sidebar 236, sheet inset 8.
- **Gutter:** 40 on a desktop, 16 on a phone.

### 4.4 Space

A 4px scale: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 96. 2 is allowed only for hairline nudges and segments.

| Gap | px |
|---|---|
| icon to label; label to count | 8 |
| leading icon in a nav, list or menu row | 12 |
| between two controls | 8 |
| between two groups of controls | 16 |
| figure label to figure; figure to chip | 12 |
| the page's two-column split | 64 |
| popover offset from its trigger | 8 |
| popover padding | 16 |
| tooltip padding | 12 |

**Rhythm:**
- Page header: 12 from the top bar.
- Title to its one line: 4.
- Header to tabs: 20.
- Body: 32 under the tabs.
- Section to section: 48.
- Section head to content: 12.
- On a phone, section to section is 32.

### 4.5 Corners

One per role:

| px | Role |
|---|---|
| 2 | keys, small marks, the tab underline |
| 4 | chosen segment, keyboard hint, info button, tags, brand mark, text-link focus ring |
| 6 | buttons, fields, search, segmented track, nav and menu rows, queue tabs, feature tiles, the label image |
| 10 | queue counters, popovers, tooltip, menus |
| 12 | the sheet, the feature band |
| full | dots, bars, the switch |

The frame is sheet plus inset, which is 20. No pill-shaped buttons, inputs or tabs.

### 4.6 Shadows, rules, focus, states

**Shadows:**

| Name | Use |
|---|---|
| control | 0 1px 1px at 4% |
| raise | the chosen segment |
| pop | menus, popovers, tooltip, dialogs |
| focal | the chosen counter: a soft teal glow |
| label | the label preview |

**Rules.** Hairlines are drawn as inset shadows, so they never add height:
- `line` for frames;
- `line-soft` between rows;
- band-rule on the band.

**States:**
- **Focus:** a 2px teal-line outline, offset 2. It is drawn inside rows and strips.
- **Hover:** fill on the sheet, only under `@media (hover:hover)`.
- **Pressed:** one step darker than hover. That is line on the sheet, line-ctl on something already filled, teal-line on teal, and white at 18% on the chrome.
- **Chosen:** the segment recipe, which is white with a teal-line inner ring and ink words.

## 5. The shell and the page

**The frame.**
- The ink chrome holds the sidebar and one white sheet inset 8 with a 12 corner.
- The sidebar:
  - is grouped Dashboards, Finance, Operations, Workspace;
  - marks Beta as a micro word, not a box;
  - ends with the account (initial, name, role).
- On a phone, the sidebar becomes a drawer behind a menu button in an ink top bar, and the sheet rises with a 12 corner.

**The top bar** sits inside the sheet: crumbs (section, chevron, page) on the left, and search with its keyboard hint on the right.

**The page header.**
- A Bricolage title, with Beta beside it where it applies.
- At most one short line under it (10 words or fewer), or a status line such as "Updated just now" with a live dot and refresh.
- The page's actions are on the right.
- There is no paragraph.

**Tabs** that move between sections of a page:
- they sit on a full-width rule;
- they are as wide as their words, 24 apart;
- they have a teal-line underline.

The page's own chooser (for example the Forecast plan) sits on the tab row's right.

## 6. The parts

| Part | The rule |
|---|---|
| Button | 32 tall, 6 corner, hairline edge, 13/20 weight 500, icon 16, 8 to its word. Primary is a teal fill with ink words. One primary per screen. |
| Segmented chooser | A fill track 32 tall; the chosen segment is white with a teal-line ring and ink words. Counts sit 8 after their word. |
| Queue counters | Big tiles, 10 corner, fill, 36px figures (28 on a phone), the label above, in flow order with small chevrons between. The chosen counter is a teal fill with the focal shadow. The rest of the queues are tabs beside them. |
| Feature band | One per screen at most, for the screen's main question (Forecast: expected this month). Hero figure, change chip, and the likely range drawn as one bar with the plan as a dashed blue tick. Side figures are stacked, each with a 28 icon tile, a figure and a meter. |
| Figure row | For screens with several equal figures: figures in one row split by hairlines, label above, change chip beside, a meter or short note below. |
| Change chip | A 20 tag, the arrow glyph and the percentage, a green or red tint, and a hidden "up" or "down" word for screen readers. Never colour alone. |
| Section | A 15/20 weight 600 head, optional count, optional info button and optional tools on the right, then content. No box. |
| Info button | 24, 4 corner, the info glyph about 9px from its words; on a phone a 40 target that never covers the label. It opens a popover with the moved explanation and "More in the Guide". |
| How it works | One header button holding a screen's method pages as a menu. On Forecast it replaces "How this forecast works". |
| List rows | 44 tall, a leading icon 12 from the words, a count and a chevron at the end, hairline-divided. Two columns read down. |
| Tables | A 32 head in caption type, 44 rows, hairlines only, numbers right-aligned and tabular. |
| Order rows | 64 tall: order link, customer and meta, date, then the actions. The Preview / Hide toggle keeps one width, so no column moves. The open row is the teal wash with a teal-line edge. |
| Chart | The legend on its own row. Hover, touch drag or arrow keys show the day. On a desktop a tooltip sits beside the point; on a phone the legend row reads the day out instead, so nothing is covered. A status line tells screen readers when the day changes. |
| Fields | Real inputs, 32 tall (40 on a phone), a search icon, a focus ring on the field. |
| Switch | 28 by 16 track, ink-4 when off, teal when on, its word beside it. |
| Tags | 20 tall, 4 corner, caption type, a tint and no border. |
| Popovers, menus, tooltip | 10 corner, the pop shadow, 16 padding (12 for the tooltip), 8 from the trigger. Menu rows are 32. |
| Empty state | A 40 icon tile (the screen's own icon on fill), one line in the head step, and the action. Centred in its space. No illustration. |
| Live status | A green dot with a halo, then "Updated just now" and refresh. |

## 7. The words

**Rules:**
- **Page header:** the title, and at most one line of 10 words or fewer.
- **Card and section titles:** they stand alone, with no description under them.
- **Explanations:** they move behind an info button beside the title, or into the Guide, word for word.
- **Warnings, costs and security notes:** they are never dropped. Where one must stay visible, it keeps one short line.
- **Empty states:** one line of 8 words or fewer, plus the action.
- **Statuses:** shown by colour and shape (a dot, a tag, a bar), not a sentence.
- **Style:** British English. No em or en dashes. Never a setting or environment name. Never the words "Railway" or "gizmo".

**The plan, in numbers:**
- 211 pieces of explanation are on screens by default, about 3,400 words.
- The plan leaves 965 (72% fewer).
- Of all 292 items, including setup and dialogs: 38 drop, 135 shorten, 64 move behind an info button, 55 keep.

**What stays under each title:**

| Screen | Line under the title | Info buttons hold |
|---|---|---|
| Overview | none; the AI summary moves to a Summary section at the top | Average Google position |
| SEO | none once run; the run gate's line before | Average position |
| Keywords | none once run | Paid search; Search data |
| Products | "Open a product for its optimisation plan." | |
| Customers | none once run | |
| Liability | "What customers owe on unpaid orders." | the unpaid tags and terms rule |
| Reconciliation | "Checks Shopify, Xero and the inbox agree. Read only." | the mailbox and Xero setup |
| Forecast | none; the status line says the month and the run date | Expected this month (how sure), Cash in, Why the figure |
| Xero sync | "Shopify orders, refunds and customers, sent into Xero." | Review and send; each tile; settings |
| Production Manager | none; the status line and the counters say it | the Unprocessed and To make queues |
| Size list | "The glass size the bench cuts for every fixture." | a ruling made here wins over the sheet |
| CRM | "Deals, activities and contacts for the sales desk." | the amber and red key; Leads; How far deals get |
| Loan units | "Projectors out on loan, and for how long." | |
| Inbox | "The shared mailbox, with an owner on every email." | amber then red; connecting the mailbox |
| Files | "The office file server, from anywhere." | Files (drag to upload and move); Trash (30 days) |
| Team | "Who can sign in, and what everyone has done." | People; Recent sessions; Activity |
| Memory | "What Reactor remembers with every answer." | Store knowledge; Notes; Tracked changes |
| Skills | "Playbooks Reactor follows in chat, reports and email drafts." | Your skills; How they are used |
| Chat | none; the empty chat says "Ask about products, orders, customers and stock." | |
| Guide | none (the tabs say it) | Requests |
| Design | none | each section |

Every item, with its current and new text, is in the appendix.

## 8. The screens

### 8.1 Forecast (mocked)

In order:
1. Header: title with Beta, status line "October 2026 · Run as of 1 Oct", and How it works and Upload workbook.
2. Finance tabs, with the Plan chooser (Algorithm 1 to 3) on the tab row.
3. The feature band:
   - **Main figure:** Expected this month, with its chip and "against plan", and the likely range as one bar with the plan tick;
   - **Side figures:** Taken so far with day progress, and Year lands at with its chip and plan.
4. Cash in: the info button, the legend row, Compare methods, and the range chooser (Today, Week, Month, 3 months, 12 months, Months ahead, Custom).
5. Worth looking at (table with mini range bars and statuses) beside Why £53,691 (a split bar and three rows).
6. The numbers behind it: four list rows in two columns.

The four method pages move into How it works.

### 8.2 Production Manager (mocked)

1. Header: title, the live status line with refresh, and Collections, New shipment and More.
2. Counters for Unprocessed, To make and To ship, with Complete and Custom shipments as tabs beside them.
3. Toolbar, exactly as today:
   - search "Find order, customer or tracking";
   - All / Unprinted / Not made with counts;
   - Print all (6);
   - Newest first;
   - 4 × 4 in (102 × 102 mm) (default).
4. Order rows. The open row shows the inline preview:
   - "First order from this customer.";
   - the label image at actual size;
   - "Actual size preview: 4 × 4 in (102 × 102 mm).".

The open order's Print is teal. On a phone each order is a hairline-divided block with worded 40px buttons: Preview or Hide, Edit and Print on the first row, Dispatch and Mark made on the second.

### 8.3 Every other screen, by pattern

| Pattern | Screens | How it lands |
|---|---|---|
| Report | Overview, SEO, Keywords, Products, Customers | Header; a figure row; charts as Cash in; tables as section 6; the AI summary as a Summary section. The run gate becomes an empty state: tile, one line with the cost, Run. Customize keeps its drag; outlines show only in Customize mode. |
| Finance | Liability, Reconciliation, Xero sync | The Finance tabs and header as Forecast. Figure rows, then hairline tables and lists. Setup steps become a numbered list behind the setup card's info button, with the Connect action. |
| Queue | Production Manager queues, Size list, Loan units | Counters where there is a flow (Production Manager only); otherwise the toolbar and rows. The Size list keeps its table, search and filters. |
| Desk | CRM, Inbox, Files | Tabs and choosers as 6. CRM board lanes are tinted, with no outline. Lists are hairline rows. |
| Workspace | Team, Memory, Skills, Chat, Guide, Design | Lists of hairline rows with initials where there are people; empty states as 6. Guide articles keep their text, as documentation. The Design page shows these tokens and parts. |
| Floating | Dialogs, menus, toasts, sign-in | 10 corner, the pop shadow, 16 padding, 32 controls (40 on a phone). |

## 9. What does not change

- **Every function, route and action.** This is a look and words change only.
- **The production label.** Its layout, content and the print paths, including the A4 and courier sheets, stay exactly as they are. So do the queue's rows, actions, toolbar items and their order, and the inline preview wording.
- **The Quote Engine.** It is out of bounds: Reactor reads paid orders only.
- **Data, forecasts, sizes and the stock-gobo name rule.**
- **The guard tests' intent.** One token block, two choosers, corner roles. Their values move to this spec.

## 10. How it is built and proven

1. **Tokens first.** Write section 4 into the app's token block and map the old names. Update the guard tests to the new values: corner roles, control text, the type list.
2. **The shell and the parts.** The ink frame, the sheet, the page header, tabs, choosers, buttons, fields, sections, lists, tables, chips, tags, info buttons, popovers, the empty state and states. Each part gets a guard test.
3. **Production Manager and Forecast,** matched to the mockup. Production Manager is checked against the live label and queue, captured with the sample-order harness.
4. **The remaining screens,** by pattern (8.3), with each screen's words cut per the appendix.
5. **Measured, every screen.**
   - The 165-screen audit (five sizes) and the mockup's measure tool must both show: 0 overlaps, clipping, low contrast, mixed-height rows, off-grid values and phone targets under 40; text styles only from 4.2.
   - `make check` passes.
   - The gallery shows before and after.
6. **Ship.** Cameron sees it and says yes, then a pull request, with release notes in the changelog dated on the merge day.

The detail of each step belongs in the implementation plan that follows this spec.

## 11. Open

- **The toolbar order.** A reviewer suggested moving Print all and Newest first. It stays as it is unless Cameron asks, because it is part of the queue.
- **Info button text.** Two info buttons ("How sure this is", "About this chart") need their text taken from what the screen says today. The build moves the existing words; it does not write new ones.
- **Chart geometry.** In the mockup the chart's geometry is written in its script. The app's chart builder reads tokens.
