# The stylesheet in layers

**Approved 19 Oct 2026.** Stage 3, piece 6 of the 14 October engineering
audit. Cameron approved all three parts. Nothing on screen changes.

## Why

The stylesheet is 33 files cut by line number in stage 2, in the old page's
order. Inside them concerns alternate every few rules (the real table's rules
sit in four files), and about 33 comments explain a rule that wins because it
weighs more or comes later. A screen's rule can beat a part's, or lose to it,
by accident of weight.

Measured on 19 Oct with a fingerprint of the final style of every element
(its `::before` and `::after` included) on all 108 measured states:

- each file in its own cascade layer, in today's order, changes 3,619
  elements on 87 states: the sheet leans on weight across files, so a full
  sort is a rule by rule rewrite of most of its 6,580 lines. Not in this piece.
- the tokens, the element defaults (17 rules) and the built parts' own rules
  (50) in layers below everything else changes 46 elements on 13 states, from
  about four rules: two input fields' padding, a few button and link widths,
  and the Design page, which lists the tokens by reading the stylesheet's
  top-level `:root` rules and finds none once they sit in a layer.

The script also sets styling directly: 30 top margins, 9 colours, 13 blocks
of `cssText` and more, outside the tokens' guards. And five class names the
parts build are legacy: `btn-sm` (the same button as `btn`), `seclink`,
`linkish`, `link` and `btn-icon`.

## What changes

### Layers under the screens

The sheet opens with `@layer tokens, base, parts;`. The tokens (the `:root`
blocks and their phone values) sit in `tokens`; the element defaults (rules
whose selectors name no class and no id: `html`, `body`, `a`, `button`,
`b`, `:focus-visible`, scroll bars) in `base`; each built part's own rules
(selectors made only of that part's classes) in `parts`, one file per part
under `static/src/css/parts/`: buttons, icon buttons, links, fields,
switches, tick rows and row openers. Everything else, screens and panels,
stays unlayered on top, so a screen's own rule beats a part's whatever their
weights. Print is untouched: no rule under `@media print`, and none of the
frozen print rules, moves. The flips the move causes are settled one by one so
that nothing changes; the Design page reads tokens inside layers. Tables,
rows, windows and panels can move into `parts` the same way later.

### The check: `make css-proof`

A committed tool shoots a fingerprint of the final style of every element on
every measured state, at each size, with its `::before` and `::after`, and
again with hover, and with keyboard focus, forced on every control (the
control, what it holds and its three nearest holders). `make css-proof
BASE=<ref>` shoots the base in a worktree of its own and the branch twice
(the two runs give the noise of clocks and times), compares, and fails on any
difference, naming the state, the element and the property. It runs on its
own ports. Every later stylesheet change is proved with it.

### No styling from the script

Spacing, colour, type, borders and backgrounds the script sets on an element
become classes built from the tokens, with exactly the values they have. The
script keeps only what it works out as it runs: positions and sizes measured
or computed, showing and hiding, and custom properties. A page-suite guard
names any new one.

### The legacy names go

`btn-sm` is dropped (it is the same 32 button) along with the part's `small`
option; `seclink`, `linkish`, `link` and `btn-icon` become `link-inline`,
`link-caption`, `link-go` and `btn-square`. The parts build them, so screens
do not change. The frozen print functions keep the classes they build.

## Guards

- The sheet opens with the layer order; the tokens, base and parts files hold
  only their own selectors; no part's own rule is left outside its file.
- No script sets styling directly outside the allowlist.
- The legacy names appear nowhere outside the frozen print functions.
- `make css-proof` against `refactor/panels`: no difference on any state,
  forced or not.

## Not in this piece

Moving tables, rows, windows, panels and the screens themselves into layers;
retiring the weight tricks the comments explain.
