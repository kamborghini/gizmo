# Data displays standardised on Bklit's patterns

Date: 2026-09-03. Status: approved in conversation; awaiting spec review.

## Goal

Every graph, chart and data display in gizmo follows Bklit UI's documented
components and patterns (https://bklit.com/docs/components), and any new
data display is built the same way. Bklit is a React library (shadcn/ui
registry, visx, D3, motion; charts MIT). gizmo is plain JavaScript with no
build step, zero front-end dependencies and a script policy of self only, so
the decision (made in conversation) is: Bklit's look, behaviour, API shape and
tokens, in our own code. Not Bklit's React source.

## Not in this build

Dark mode (gizmo is light-only by policy; the token layer carries the dark
values so it costs nothing later). Candlestick, choropleth, radar, sankey,
scatter, sunburst, live line and profit/loss line: no current use; they are
built the same way when a feature needs one. Rebuilding tables or cards as
Bklit components: Bklit has none; they follow shadcn/ui, which the app already
matches.

## What Bklit documents (measured 2026-09-03 from the live docs)

Anatomy: aspect ratio 2 / 1 (CSS aspect-ratio); horizontal-only grid, dashed
`4,4`, 1px, colour `--chart-grid`, 5 rows by default; x-axis only by default,
`numTicks` 6, ticks snap to data rows (`tickMode "data"`), tick label 11px
weight 600 in `--chart-foreground-muted`; YAxis opt-in; Line `strokeWidth`
2.5, round caps, `curveNatural`, stroke gradient fading in over the first and
last 10% of width; Area `fillOpacity` 0.4, `strokeWidth` 2, `curveMonotoneX`,
fill draining to transparent (`gradientToOpacity` 0); Bar `lineCap` "round",
`barGap` 0.2, `orientation` vertical or horizontal, `stacked`, `fadedOpacity`
0.3 on hover of a sibling, `animationType` "grow" with an automatic stagger
that finishes within about 1.2s; `showMarkers` ring markers; ChartTooltip
with `showDatePill`, `showCrosshair` (vertical, fading at both ends over 10%
of height), `showDots`, swatch rows, spring follow (`damping` 20); Legend
click-to-toggle; Brush range selection; Gauge (`value` 0 to 100, `orientation`
arc or linear, `totalNotches` 40, `spacing` 25, `startAngle` 135, `endAngle`
405, `centerValue`, `defaultLabel`); RingChart (`strokeWidth` 12, `ringGap` 6,
`baseInnerRadius` 60, rings with `value`/`maxValue`, `RingCenter`); Composed
Chart mixing Area, Line and SeriesBar on one time axis.

Motion: `animationDuration` 1100ms clip-path reveal with
`cubic-bezier(0.85, 0, 0.15, 1)`; on data change `yDomainTween` (500ms) morphs
the y-scale with no replay; `status "loading"` shows a pulse or sweep shimmer
with a centred label; then domain tween; then reveal.

Tokens (names as Bklit): `--chart-1` to `--chart-5`, `--chart-background`,
`--chart-foreground`, `--chart-foreground-muted`, `--chart-grid`,
`--chart-line-primary`, `--chart-line-secondary`, `--chart-crosshair`,
`--chart-tooltip-background`, `--chart-tooltip-foreground`,
`--chart-tooltip-muted`, `--chart-marker-background`, `--chart-marker-border`,
`--chart-marker-foreground`, `--chart-brush-border`, `--chart-label`.

## Mapping

| Pattern | Bklit component |
|---|---|
| Overview and SEO trend cards | AreaChart (one series), LineChart (several) |
| Orders per month, category bars | BarChart (vertical; horizontal for categories) |
| SEO CTR and position | LineChart with YAxis and a floated domain |
| Stat-card sparklines | LineChart with no Grid, no XAxis, no tooltip |
| SEO score band | Gauge, linear |
| Aged-debt share | PieChart as a donut, centre total, Legend (see Behaviour details) |
| Range switches 3M/6M/12M/24M | y-domain tween; Brush available |
| Loading and gated cards | status "loading" pulse |
| Tables and row lists | shadcn Table pattern (unchanged); lists aligned |
| Planned: revenue vs orders | ComposedChart |
| Planned: pipeline stages, weekday heat | FunnelChart, HeatmapChart, built the same way when needed |

## Components

### static/charts.js (new)

Served at `/assets/charts.js` by a hashed, gated route exactly like
`composer.js`, loaded before `app.js` (the page calls into it). Exposes
`window.bk` with one function per Bklit component, same names, same props,
same defaults:

    bk.LineChart({ data, xDataKey: "date", aspectRatio: "2 / 1",
                   animationDuration: 1100, yDomainTween: true, status: "ready",
                   margin }, [children]) -> HTMLElement
    bk.AreaChart(...)   bk.BarChart({ xDataKey: "name", barGap: 0.2, orientation,
                   stacked, stackGap, maxBarSize }, [...])   bk.ComposedChart(...)
    bk.Gauge({ value, orientation: "arc", totalNotches: 40, spacing: 25,
               startAngle: 135, endAngle: 405, centerValue, defaultLabel,
               formatOptions })
    bk.RingChart({ data, size, strokeWidth: 12, ringGap: 6, baseInnerRadius: 60 },
                 [bk.Ring({ index }), bk.RingCenter({ defaultLabel })])
    children: bk.Grid({ horizontal: true, numTicksRows: 5 }),
              bk.XAxis({ numTicks: 6, tickMode: "data", tickFormatter }),
              bk.YAxis({ numTicks, tickFormatter }),
              bk.Line({ dataKey, stroke, strokeWidth: 2.5, curve: "natural",
                        showMarkers: false, dashFromIndex }),
              bk.Area({ dataKey, fill, fillOpacity: 0.4, strokeWidth: 2,
                        curve: "monotone", showLine: true, gradientToOpacity: 0 }),
              bk.Bar({ dataKey, fill, lineCap: "round", animate: true,
                       animationType: "grow", fadedOpacity: 0.3, minBarHeight: 0 }),
              bk.SeriesBar (ComposedChart), bk.ChartTooltip({ showDatePill: true,
                       showCrosshair: true, showDots: true, rows }),
              bk.Legend({ toggle: true }), bk.Brush({ onChange })

A chart element carries `update(data)` (runs the y-domain tween, never the
reveal) and `setStatus("loading" | "ready")`. Rendering is SVG at 1:1 scale
with a ResizeObserver, as today. The tooltip is one DOM panel per chart,
clamped to the card, with the date pill and swatch rows. Curves: natural and
monotone are implemented in the module (Catmull-Rom and monotone cubic).

### Tokens (static/index.html, :root)

The Bklit names above, mapped once: `--chart-1..5` to the CH greys,
`--chart-grid` to `--border`, `--chart-foreground` to `--ink`,
`--chart-foreground-muted` to `--ink-3` (deviation: Bklit's own value fails
4.5:1 on white and the contrast guard is law), tooltip tokens to the surface
and ink set, `--chart-crosshair` to `--ink-3`. The module reads only these.

### Migration (static/index.html)

Every call site is rewritten to `bk.*` and the old builders are deleted:
trendChart (15 sites), barChart (5), catBars (3), sparkline (2), the SEO
score band, the aged-debt bar, chartHead/trendsHeader/drawFrame/autoPlot and
the chart CSS that only they used. `renderTrendsBlock`, `renderSeoTrends`,
`renderCustomers`, `renderProductDetail`, `renderKeywords`, `renderCPC`,
`statCard`, `renderSEO` (score), `renderLiability` (aged debt) are the
functions touched. Range switches call `update(data)`.

### copilot.py

One route, `/assets/charts.js`, mirroring `/assets/composer.js`; the shell
tag goes before `app.js`.

## Behaviour details

- First paint of a view: the reveal. Repaints (range switch, refresh,
  returning to the tab): `update`, which tweens the domain and never replays.
- Bars: grow with the automatic stagger; hovering one bar fades its siblings
  to 0.3.
- Tooltip: crosshair fades at both ends; dots sit on each series at the
  hovered x; the date pill follows with the documented spring; the panel is
  clamped inside the card padding box.
- Legend: clicking an entry toggles that series; the y-domain tweens.
- Gauge (linear) for the SEO score: 40 notches, 25% spacing, active in
  `--chart-1`, inactive at `--border`.
- Aged-debt share: Bklit's RingChart draws one ring per entry, and six
  concentric rings of one total read badly at card widths, so the share of
  outstanding uses Bklit's PieChart pattern as a donut (inner radius, one
  segment per bucket, centre total, Legend beside it). The mapping table's
  RingChart entry is superseded by this line. Recorded here so it is not
  re-litigated.
- Reduced motion: no reveal, no stagger, no tween.

## Testing

Frontend guards: `bk` exposes every component listed with the documented
defaults (a table in the test, one row per prop); no old builder name
survives in index.html; tokens exist and `--chart-foreground-muted` resolves
to `--ink-3`; the chart script is served by hash before app.js; dash ban on
charts.js. Rig measurement: for each chart kind, the rendered SVG matches
Bklit's numbers (dash `4,4`, 5 grid rows, 2.5px round-capped line, 0.4 area,
round bars with 0.2 gap, 2:1 aspect, 6 x ticks), and a range switch produces
no opacity dip and no dasharray reset. Both suites green; the border and
contrast guards untouched.

## Rollout

One release. The chart script is hashed, so no cache trouble. Memory records
the API and the two deviations (tick colour, donut for aged debt).
