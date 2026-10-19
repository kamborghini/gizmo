        /* ---------- charts (hand-rolled inline SVG, no deps, CSP-safe) ---------- */
        const REDUCE_MOTION = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
        const SVGNS = 'http://www.w3.org/2000/svg';
        const svgEl = (tag, attrs) => { const e = document.createElementNS(SVGNS, tag); for (const k in (attrs || {})) e.setAttribute(k, attrs[k]); return e; };
        /* A 1-2-5-10 ladder can only ever land on four rungs per decade, so a
           12.0k peak was rounded to a 20k axis and 40% of the plot was empty.
           The fine ladder closes that. Two 33% gaps were left in it, 3 to 4 and
           6 to 8, and a 251 peak climbed the second one to a 320 top with a
           fifth of the plot empty; the 7 rung tops it at 280 instead, and its
           rules land on 70, 140, 210, 280, every one of which the axis can
           print exactly. There is deliberately no 3.5 rung, which would suit
           the 12.0k peak: its rules fall on 3.5k, 7k, 10.5k, 14k, and a compact
           axis prints that 10 500 rule as "11k" - a number the chart does not
           draw. An empty tenth of a plot is cheaper than a false label. */
        const NICE = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 10];
        const niceMax = (v) => { v = Number(v) || 0; if (v <= 0) return 1; const p = Math.pow(10, Math.floor(Math.log10(v))); const u = v / p; const m = NICE.find(x => u <= x + 1e-9) || 10; return m * p; };
        /* A plot is four bands, so the top has to be four round STEPS rather
           than one round number quartered: a 15k top over a 12.0k peak labels
           its rules 3.8k, 7.5k, 11k, 15k. Same ladder, applied to the step. */
        /* ints: every value is a whole count (orders, units, customers). Its
           rules then fall on whole numbers: a peak of 3 put rules at 0.8,
           1.6, 2.4 and 3.2, which the axis printed as 0, 1, 2, 2, 3. */
        const axisTop = (v, ints) => {
            const step = niceMax((Number(v) || 0) / 4);
            return 4 * (ints ? Math.max(1, Math.ceil(step)) : step);
        };
        const allWhole = (vals) => vals.every(x => x == null || Number.isInteger(Number(x)));
        /* A rate or a rank is read as a MOVEMENT, not as a share of zero: on a
           6.0 to 6.4% click-through series a zero floor spends 95% of the plot
           on nothing. Four bands of a round step, floated to sit under the data.
           Money and counts keep their zero floor, where the HEIGHT of the line
           is the quantity and a floated one would overstate every change. */
        function fitDomain(mn, mx) {
            const span = (mx - mn) || Math.abs(mx) * 0.2 || 1;
            let step = niceMax(span / 3), lo = Math.floor((mn - span * 0.1) / step) * step, guard = 0;
            while (lo + 4 * step < mx && guard++ < 8) { step = niceMax(step * 1.5); lo = Math.floor((mn - span * 0.1) / step) * step; }
            return { lo: lo, hi: lo + 4 * step };
        }
        /* The plot is drawn at 1:1, as the reference draws its own: the viewBox
           width IS the wrap's pixel width, so a 12px date is 12px on screen at
           every viewport instead of the 19.5px a 1.625x upscale made of it.
           That width only exists once the wrap is in the document, which is why
           the plot is built from a ResizeObserver rather than at build time -
           and rebuilt when the column changes width. */
        function autoPlot(wrap, draw) {
            let last = 0, drawn = false;
            const run = () => {
                // The fractional width, not clientWidth: a half-width grid cell
                // measures 594.5, and rounding it to 595 puts the scale back off 1.
                const w = Math.round((wrap.getBoundingClientRect().width || 0) * 10) / 10;
                if (!w || w === last) return;
                last = w; wrap.innerHTML = ''; draw(Math.max(240, w), drawn); drawn = true;
            };
            if (window.ResizeObserver) new ResizeObserver(run).observe(wrap);
            else { let t; window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(run, 120); }); }
            requestAnimationFrame(run);
        }
        /* Pounds on a chart's axis: £0, £1.5k, £6k. */
        const fmtCompactGBP = (n) => (Number(n) < 0 ? '-\u00a3' : '\u00a3') + fmtCompact(Math.abs(Number(n) || 0));
        const fmtCompact = (n) => { n = Number(n) || 0; const a = Math.abs(n); if (a >= 1e6) return (n / 1e6).toFixed(a >= 1e7 ? 0 : 1).replace(/\.0$/, '') + 'M'; if (a >= 1e3) return (n / 1e3).toFixed(a >= 1e4 ? 0 : 1).replace(/\.0$/, '') + 'k'; return String(Math.round(n)); };
        /* A tap or click anywhere else puts every chart back to rest. */
        document.addEventListener('pointerdown', (e) => document.querySelectorAll('.chart-wrap').forEach(w => {
            if (!w.contains(e.target) && w._rest) w._rest(); }), { passive: true });
        let _chartSeq = 0;

        // opts: {title, value, delta, trend, labels:[], series:[{name,color,values:[]}], format, height, area}
        function chartHead(opts, series, kind) {
            const head = el('div', 'chart-head'); const htxt = el('div');
            /* Title, then the card's own number, then where it came from. The
               source line used to sit between them, so the figure ranked below
               its own provenance and read as an orphan under a caption. */
            /* A chart's explanation is an info button beside its title (the
               mix, spec 7), not a line under the plot. */
            if (opts.title) {
                const ct = el('div', 'ct', opts.title);
                if (opts.help) ct.append(infoButton(opts.title, { title: opts.title, body: opts.help }));
                htxt.append(ct);
            }
            if (opts.value != null) {
                const v = el('div', 'cv'); v.append(document.createTextNode(opts.value));
                if (opts.delta) v.append(changeChip(opts.trend, opts.delta, deltaTone(opts.title, opts.trend, opts.better)));
                htxt.append(v);
            }
            /* The window belongs next to the number, not 44px away on a control.
               "Average position 8.6" on a chart card sat 235px under a KPI
               reading "Average position 8.2", both unlabelled, because one is
               the range's mean and the other is the latest figure. The range
               control changes exactly this, so the card says which span it is
               showing. */
            /* No coloured dot in front of it. It was painted in the first
               series' colour, so it read as a key; on a chart with a legend it
               was a third swatch beside the legend's own, and on the forecast
               it was the same black as both lines. */
            if (opts.source) {
                const cs = el('div', 'cs');
                cs.append(document.createTextNode(opts.source + (opts.period ? ' \u00b7' : '')));
                if (opts.period) cs.append(el('span', 'cs-period', opts.period));
                htxt.append(cs);
            }
            head.append(htxt);
            if (kind && !opts.noExpand) { const ex = el('button', 'chart-expand'); ex.title = 'Expand'; ex.innerHTML = I.maximize; ex.onclick = () => openChartModal(kind, opts); head.append(ex); }
            return head;
        }
        /* One key per series, above the plot and right-aligned. Only drawn when
           there is something to tell apart (two lines, a dashed line or a
           shaded range): a legend for one plain line names something nothing
           else on the card contradicts. */
        /* Each swatch is drawn the way its mark is: a dashed series gets a
           dashed stroke and a band a soft block. Two solid squares in one
           colour told a solid line from a dashed one by nothing at all. */
        function chartLegend(series, band) {
            const lg = el('div', 'chart-legend');
            const item = (name, color, kind) => {
                const it = el('span', 'lg');
                const sw = el('span', 'sw' + (kind ? ' ' + kind : ''));
                sw.style.setProperty('--sw', color || 'var(--action-primary)');
                it.append(sw, document.createTextNode(name || ''));
                lg.append(it);
            };
            /* A comparison line is drawn dashed too (.chart-line.compare), so
               it is keyed dashed. And only what is actually drawn gets a key:
               a series with fewer than two points draws nothing, and the
               forecast's twelve-month range listed a Forecast it never drew. */
            series.filter(sr => (sr.values || []).filter(v => v != null).length > 1 || sr.key === 'dot')
                .forEach((sr, i) => item(sr.name, sr.color, sr.key || ((sr.dash || (i > 0 && !sr.lead)) ? 'dash' : '')));
            if (band && band.lo.some((v, i) => v != null && band.hi[i] != null && band.hi[i] !== v)) item(band.name || 'Range', band.color, 'band');
            return lg;
        }
        // Draws gridlines, y-tick labels, x-tick labels, and rotated axis titles. Returns {X, Y}.
        function drawFrame(svg, c) {
            const { W, H, padL, padR, padT, padB, n, labels, maxV, fmt } = c;
            // Bars use a band scale (each bar centered in its own slot, inset from the axes);
            // lines/areas use an endpoint scale (the series touches both axes).
            const X = c.band
                ? (i) => padL + ((i + 0.5) / Math.max(1, n)) * (W - padL - padR)
                : (i) => padL + (n <= 1 ? 0 : (i / (n - 1)) * (W - padL - padR));
            const minV = c.minV || 0;
            const Y = (v) => padT + (1 - (((Number(v) || 0) - minV) / ((maxV - minV) || 1))) * (H - padT - padB);
            /* Four steps, and two (three ticks) on a plot under 520 wide, as the mockup's phone chart has them. */
            const ticks = W < 520 ? 2 : 4, gy = svgEl('g', { class: 'axis-y' });
            for (let t = 0; t <= ticks; t++) {
                const yy = padT + t / ticks * (H - padT - padB);
                // The rule starts at the axis and runs to the card edge; it used
                // to start at 0 and pass under its own numbers.
                gy.append(svgEl('line', { class: 'gridline' + (t === ticks && !minV ? ' axis0' : ''), x1: padL, y1: yy, x2: W, y2: yy }));
                if (c.yTicks) {
                    const tx = svgEl('text', { x: padL - 8, y: yy + 3.5, 'text-anchor': 'end' });
                    tx.textContent = (c.tickFmt || fmt)(minV + (maxV - minV) * (1 - t / ticks)); gy.append(tx);
                }
            }
            svg.append(gy);
            /* As many dates as the plot has room for, up to six. A fixed six
               on a phone put the last date, flush right, on top of the one
               before it ("25 Se30 Sep"): the end-anchored label reaches a whole
               label-width back, so each needs half as much room again. */
            const labW = labels.reduce((m, l) => Math.max(m, String(l || '').length), 0) * 6.2;
            const room = Math.max(2, Math.floor((W - padL - padR) / (labW * 1.5 + 8)));
            const gx = svgEl('g', { class: 'axis-x' }), step = Math.max(1, Math.ceil(n / Math.min(c.xEvery || 6, room)));
            /* Counted BACK from the last point, so the axis ends on the newest
               date at the same spacing as every other gap. Counting forward and
               then forcing the last one in left a final gap of up to three
               steps - 1.5x its neighbours on all four charts - and the guard
               that popped a crowded tick only fired when the two landed inside
               0.6 of a step of each other. */
            const idxs = [];
            /* A month drawn day by day has its dates weekly from the 1st (1, 8, 15, 22, 29), the same at every width. */
            if (c.xWeekly) { for (let i = 0; i < n; i += 7) idxs.push(i); }
            else for (let i = n - 1; i >= 0; i -= step) idxs.unshift(i);
            /* Keep every date inside the plot AND clear of the y numbers. On an
               endpoint scale the first point sits exactly on padL, so a centred
               date there straddled the axis and printed its own left half on
               top of the "0" ending at padL - 8. Anchoring it at the axis moves
               it right by half a label. The reference does the same at the far
               end: its last label ends FLUSH with the right edge rather than
               straddling it. An estimate of half the label's width is enough to
               decide - it only has to be right near the two edges. */
            idxs.forEach(i => {
                const x = X(i), halfish = String(labels[i] || '').length * 3.1;
                const anchor = x - halfish < padL ? 'start' : (x + halfish > W - 2 ? 'end' : 'middle');
                const tx = svgEl('text', { x: x, y: H - padB + 15, 'text-anchor': anchor });
                tx.textContent = labels[i]; gx.append(tx);
            });
            svg.append(gx);
            /* No axis titles. The reference names a chart in its card header
               and puts nothing down the side of the plot. */
            return { X, Y };
        }
        // Average reference line + peak marker on a single series.
        function annotate(svg, vals, X, Y, color, fmt, W, padR, padL, padT) {
            const top = (padT || 0) + 9;
            const avg = vals.reduce((a, b) => a + b, 0) / (vals.length || 1), ya = Y(avg);
            svg.append(svgEl('line', { class: 'chart-avg', x1: padL, y1: ya, x2: W - padR, y2: ya }));
            // keep the label inside the plot: below the line when the line is near the top
            const aly = (ya - 5 < top) ? ya + 14 : ya - 5;
            const al = svgEl('text', { class: 'chart-avg-label', x: W - padR, y: aly, 'text-anchor': 'end' }); al.textContent = 'Avg ' + fmt(avg); svg.append(al);
            let pi = 0; vals.forEach((v, i) => { if (v > vals[pi]) pi = i; });
            svg.append(svgEl('circle', { cx: X(pi), cy: Y(vals[pi]), r: 3, fill: color }));
            // peak label: clamp so it never clips into the header; drop below the dot when near the top
            const ply = (Y(vals[pi]) - 8 < top) ? Y(vals[pi]) + 17 : Y(vals[pi]) - 8;
            const anchor = X(pi) > W * 0.85 ? 'end' : X(pi) < W * 0.12 ? 'start' : 'middle';
            const pl = svgEl('text', { class: 'chart-peak-label', x: X(pi), y: ply, 'text-anchor': anchor }); pl.textContent = 'Peak ' + fmt(vals[pi]); svg.append(pl);
        }
        function trendChart(opts) {
            opts = opts || {};
            const H = opts.height || CHART.h;
            const multi = (opts.series || []).filter(function (x) { return x && x.values && x.values.filter(v => v != null).length > 1; }).length > 1;
            /* 40 at the left for the y-axis numbers and nothing at the right, so
               the line still reaches the card edge; 14 at the top for the
               topmost point's stroke, and 30 at the foot for the dates. This
               used to reserve 48 for a legend that was drawn in the card header
               instead, so a multi-series chart carried a band of nothing across
               the top of its own plot. */
            const padL = CHART.padL, padR = CHART.padR, padT = CHART.padT, padB = CHART.padB;
            const labels = opts.labels || [];
            const series = (opts.series || []).filter(s => s && Array.isArray(s.values) && s.values.length);
            const fmt = opts.format || fmtCompact;
            /* noIntro: this card is a REPAINT of one already on screen - a range
               switch, a refresh, a return to the tab - so it appears where the
               old one was instead of fading up from nothing under the reader's
               eye. */
            const card = el('div', 'chart-card' + (REDUCE_MOTION || opts.noIntro ? '' : ' chart-anim'));
            if (!opts.headless) card.append(chartHead(opts, series, 'trend'));
            const bandOpt = opts.band && Array.isArray(opts.band.lo) && Array.isArray(opts.band.hi) ? opts.band : null;
            /* A key whenever the reader has to tell marks apart: two or more
               lines, a dashed line (which reads as its own kind of thing), or a
               shaded range, which otherwise looks like part of the frame. */
            if (opts.legend || (multi && series.length > 1) || bandOpt || series.some(s => s.dash)) {
                const lg = chartLegend(series, bandOpt);
                if (lg.children.length > 1 || lg.querySelector('.dash, .band')) card.append(lg);
            }
            const wrap = el('div', 'chart-wrap'); card.append(wrap);
            /* The plot is one stop for the keyboard: the arrow keys read it point
               by point, and a status line says each point to a screen reader. */
            wrap.tabIndex = 0;
            wrap.setAttribute('role', 'group'); wrap.setAttribute('aria-roledescription', 'chart');
            wrap.setAttribute('aria-label', (opts.label || opts.title || 'Chart') + '. Use the left and right arrow keys to read it point by point.');
            const live = el('p', 'sr-only'); live.setAttribute('role', 'status'); card.append(live);
            if (!series.length || labels.length < 2) { wrap.append(el('div', 'empty', 'Not enough data in this range yet.')); return card; }
            const n = labels.length;
            /* An uncertainty band is DATA: p90 is routinely the highest thing
               on the plot, so its values set the domain alongside the lines.
               Left out, the band is drawn and then clipped by the frame. */
            const all = series.flatMap(s => s.values)
                .concat(bandOpt ? bandOpt.lo.concat(bandOpt.hi) : [])
                .filter(v => v != null).map(v => Number(v) || 0);
            const fit = opts.fitY ? fitDomain(Math.min.apply(null, all), Math.max.apply(null, all)) : null;
            const minV = fit ? fit.lo : 0;
            const maxV = fit ? fit.hi : axisTop(Math.max.apply(null, all.concat([0])), allWhole(all));
            const draw = (W, redraw) => {
                const svg = svgEl('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H });
                const { X, Y } = drawFrame(svg, { W, H, padL, padR, padT, padB, n, labels, minV, maxV, fmt, tickFmt: opts.tickFormat || fmt, yTicks: true, xWeekly: !!opts.xWeekly });
                const uid = 'cg' + (++_chartSeq);
                const defs = svgEl('defs'); const grad = svgEl('linearGradient', { id: uid, x1: 0, y1: 0, x2: 0, y2: 1 });
                /* The wash under a single line is that line's own colour, faded from
                   15% (the strength of --c-area, the mix's area tint) to 2% down
                   the plot: a hint of the measure, not a block. It was the ramp's
                   fifth step, which is amber since the ramp became the brand's,
                   and put amber under every teal trend line. */
                const washColor = (series[0] && series[0].color) || CH[0];
                grad.append(svgEl('stop', { offset: '5%', 'stop-color': washColor, 'stop-opacity': '0.15' }));
                grad.append(svgEl('stop', { offset: '95%', 'stop-color': washColor, 'stop-opacity': '0.02' }));
                defs.append(grad); svg.append(defs);
                /* A gap in a series is a GAP, not a zero. Y(null) is Y(0), so
                   every series used to be drawn down to the floor wherever it
                   had no value - which on a forecast chart meant the actual
                   line ran along the bottom through the whole forecast and the
                   forecast line ran along the bottom through the whole of
                   history, crossing in a V that means nothing. Contiguous runs
                   are drawn as separate subpaths and the gaps stay empty. */
                const runsOf = (vals) => {
                    const out = []; let run = [];
                    for (let i = 0; i <= vals.length; i++) {
                        const v = i < vals.length ? vals[i] : null;
                        if (v != null && isFinite(v)) { run.push([X(i), Y(v)]); continue; }
                        if (run.length) out.push(run);
                        run = [];
                    }
                    return out;
                };
                const line = (vals) => runsOf(vals).map(r => r.length > 1 ? smoothPath(r)
                    : 'M' + r[0][0].toFixed(1) + ' ' + r[0][1].toFixed(1) + ' l0 0').join(' ');
                // The wash closes on the FLOOR of the domain, not on zero: with a
                // floated floor, zero is off the plot and the fill would spill out
                // of the card, which draws nothing an overflow:visible svg would clip.
                if (opts.area !== false) {
                    runsOf(series[0].values).forEach(r => {
                        if (r.length < 2) return;
                        const head = smoothPath(r);
                        const a = head + ' L ' + r[r.length - 1][0].toFixed(1) + ' ' + Y(minV).toFixed(1)
                            + ' L ' + r[0][0].toFixed(1) + ' ' + Y(minV).toFixed(1) + ' Z';
                        svg.append(svgEl('path', { d: a, fill: 'url(#' + uid + ')' }));
                    });
                }
                let drawPath = null;
                /* The uncertainty band, under the lines. Two p10 and p90 LINES
                   is the wrong picture: three strokes read as three competing
                   predictions, and the reader has to work out which one is the
                   answer. One shaded region reads as what it is - a range the
                   outcome is expected to fall in. Drawn as contiguous runs, so
                   the band starts where the forecast starts and does not reach
                   back across the months that already happened. */
                if (bandOpt) {
                    const run = [];
                    for (let i = 0; i <= n; i++) {
                        const ok = i < n && bandOpt.lo[i] != null && bandOpt.hi[i] != null;
                        if (ok) { run.push(i); continue; }
                        if (run.length > 1) {
                            const hi = smoothPath(run.map(k => [X(k), Y(bandOpt.hi[k])]));
                            const lo = smoothPath(run.slice().reverse().map(k => [X(k), Y(bandOpt.lo[k])]));
                            svg.append(svgEl('path', { class: 'chart-band', d: hi + ' L' + lo.slice(1) + ' Z',
                                fill: bandOpt.color || CH[2] }));
                        }
                        run.length = 0;
                    }
                }
                /* Where what happened stops and what is expected begins. The
                   single most important line on a forecast chart: without it a
                   reader cannot tell which part of the curve is money that
                   arrived and which part is an estimate. */
                if (opts.splitAt != null && opts.splitAt >= 0 && opts.splitAt < n) {
                    svg.append(svgEl('line', { class: 'chart-split', x1: X(opts.splitAt), x2: X(opts.splitAt),
                        y1: padT, y2: H - padB }));
                }
                series.forEach((s, si) => { const p = svgEl('path', { class: 'chart-line' + (si > 0 && !s.lead ? ' compare' : '') + (s.dash ? ' dash' : '') + (s.full ? ' full' : ''), d: line(s.values), stroke: s.color || (si ? CH[3] : CH[0]) }); if (!REDUCE_MOTION && si === 0) drawPath = p; svg.append(p); });
                /* A series with a single point (money taken on the first of the
                   month) is a dot, ringed in white, rather than a speck. */
                series.forEach(s => runsOf(s.values).filter(r => r.length === 1).forEach(r =>
                    svg.append(svgEl('circle', { class: 'chart-pt', cx: r[0][0], cy: r[0][1], r: CHART.ptR, fill: s.color || CH[0] }))));
                /* No average rule, no peak label, no dot at the end of the line.
                   The reference chart has none of them: its <svg> contains zero
                   circles at rest and every text node in it is an x-axis date. The
                   numbers live in the tooltip, on hover. */
                /* The last point that happened carries its figure beside it (the mockup's £5,116 on Cash in): the
                   first series' last value, in the caption weight, on the right of the dot or the left of it at the edge. */
                if (opts.lastLabel) {
                    const vs = series[0].values; let li = -1;
                    vs.forEach((v, i) => { if (v != null && isFinite(v)) li = i; });
                    if (li >= 0) {
                        const txt = fmt(vs[li]), tw = String(txt).length * 6.4, lx = X(li), flip = lx + 10 + tw > W;
                        const lt = svgEl('text', { class: 'chart-last', x: flip ? lx - 10 : lx + 10, y: Y(vs[li]) - 6, 'text-anchor': flip ? 'end' : 'start' });
                        lt.textContent = txt; svg.append(lt);
                    }
                }
                const hoverLine = svgEl('line', { class: 'chart-hover-line', x1: 0, y1: padT, x2: 0, y2: H - padB, opacity: 0 }); svg.append(hoverLine);
                const dots = series.map(s => { const c = svgEl('circle', { class: 'chart-dot', r: CHART.dotR, fill: s.color || CH[0], opacity: 0 }); svg.append(c); return c; });
                const tip = el('div', 'chart-tip'); tip.setAttribute('aria-hidden', 'true'); wrap.append(tip);
                const overlay = svgEl('rect', { x: padL, y: padT, width: (W - padL - padR), height: (H - padT - padB), fill: 'transparent' }); svg.append(overlay);
                /* The point under the pointer, a finger or the arrow keys (the
                   mix, spec 6). On a desktop the tooltip sits beside the point,
                   its first row level with it; on a phone the legend row reads
                   the point out instead, so nothing covers the chart. */
                const legendEl = card.querySelector('.chart-legend');
                const TIP = { beside: tokenNum('--sp-4'), off: tokenNum('--pop-offset'),
                    lift: tokenNum('--tip-pad') + tokenNum('--lh-caption') + tokenNum('--sp-1') + tokenNum('--lh-control') / 2 };
                const swatch = (cls, color) => { const s = el('span', 'sw' + (cls ? ' ' + cls : '')); if (color) s.style.setProperty('--sw', color); return s; };
                let cur = -1, liveT = 0;
                /* The status line speaks on an arrow-key step at once, and for a pointer only once it has rested on one point
                   (about 600ms): updating on every move made a screen reader read each point the pointer crossed. */
                const say = (text, now) => {
                    clearTimeout(liveT);
                    if (now) { if (live.textContent !== text) live.textContent = text; return; }
                    liveT = setTimeout(() => { if (live.textContent !== text) live.textContent = text; }, 600);
                };
                const show = (i, announce) => {
                    i = Math.max(0, Math.min(n - 1, i)); cur = i;
                    hoverLine.setAttribute('x1', X(i)); hoverLine.setAttribute('x2', X(i)); hoverLine.setAttribute('opacity', 1);
                    dots.forEach((c, si) => { const v = series[si].values[i];
                        if (v == null) { c.setAttribute('opacity', 0); return; }
                        c.setAttribute('cx', X(i)); c.setAttribute('cy', Y(v)); c.setAttribute('opacity', 1); });
                    const rows = [];
                    series.forEach(s => { if (s.values[i] != null) rows.push([swatch(s.key === 'dot' ? 'dot' : (s.dash ? 'dash' : ''), s.color || CH[0]), s.name || '', fmt(s.values[i])]); });
                    if (bandOpt && bandOpt.lo[i] != null && bandOpt.hi[i] != null)
                        rows.push([swatch('band', bandOpt.color || CH[2]), bandOpt.name || 'Range', fmt(bandOpt.lo[i]) + ' to ' + fmt(bandOpt.hi[i])]);
                    const said = labels[i] + ', ' + rows.map(r => r[1] + ' ' + r[2]).join(', ');
                    say(said, announce);
                    if (legendEl && window.matchMedia('(max-width: 640px)').matches) {
                        if (!legendEl._rest) legendEl._rest = [].slice.call(legendEl.childNodes);
                        const read = [el('b', null, labels[i])];
                        rows.forEach(r => { const it = el('span', 'lg'); it.append(r[0], document.createTextNode(r[2])); read.push(it); });
                        legendEl.replaceChildren(...read); legendEl.classList.add('reading');
                        return;
                    }
                    tip.replaceChildren(el('div', 'tl', labels[i]));
                    rows.forEach(r => { const row = el('div', 'tr'); row.append(r[0], el('span', null, r[1]), el('b', null, r[2])); tip.append(row); });
                    const rect = svg.getBoundingClientRect(); if (!rect.width) return;
                    const k = rect.width / W, tw = tip.offsetWidth, th = tip.offsetHeight;
                    const ys = series.map(s => s.values[i]).filter(v => v != null).map(v => Y(v));
                    const px = X(i) * k, py = (ys.length ? Math.min.apply(null, ys) : padT) * k;
                    let left = px + TIP.beside, top = py - TIP.lift;
                    if (left + tw > rect.width) left = px - TIP.beside - tw;
                    if (left < 0) { left = Math.max(0, Math.min(px - tw / 2, rect.width - tw)); top = py - TIP.off - th; }
                    else top = Math.max(0, Math.min(top, (H - padB) * k - th));
                    tip.style.left = Math.round(left) + 'px'; tip.style.top = Math.round(top) + 'px'; tip.style.opacity = 1;
                };
                const rest = () => {
                    cur = -1; clearTimeout(liveT); hoverLine.setAttribute('opacity', 0); dots.forEach(c => c.setAttribute('opacity', 0)); tip.style.opacity = 0;
                    if (legendEl && legendEl._rest) { legendEl.replaceChildren(...legendEl._rest); legendEl.classList.remove('reading'); }
                };
                wrap._rest = rest;
                const at = (clientX) => {
                    const rect = svg.getBoundingClientRect(); if (!rect.width) return;
                    show(Math.round(((clientX - rect.left) / rect.width * W - padL) / (W - padL - padR) * (n - 1)));
                };
                svg.onpointermove = (e) => at(e.clientX);
                /* A finger keeps the chart while it drags across the points. */
                svg.onpointerdown = (e) => { at(e.clientX); if (e.pointerType !== 'mouse' && svg.setPointerCapture) svg.setPointerCapture(e.pointerId); };
                svg.onpointerleave = (e) => { if (e.pointerType === 'mouse') rest(); };
                wrap.onkeydown = (e) => {
                    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); show((cur < 0 ? n - 1 : cur) + (e.key === 'ArrowRight' ? 1 : -1), true); }
                    else if (e.key === 'Escape') rest();
                };
                wrap.append(svg);
                /* The reveal length is MEASURED, not guessed. It was a hardcoded
                   1600 user units, and a curved line across a jagged 24-month
                   range runs longer than that - which starts the animation with
                   part of the line already painted and finishes it early. The plot
                   is drawn at 1:1, so a user unit IS a screen pixel and the
                   non-scaling-stroke dash pattern resolves to the same number.
                   Neither a redraw after a resize nor a repaint of a card that
                   was already on screen re-runs the reveal. */
                if (drawPath && !redraw && !opts.noIntro) {
                    const len = Math.ceil(drawPath.getTotalLength && drawPath.getTotalLength() || 0) || 1600;
                    drawPath.style.strokeDasharray = len + 'px';
                    drawPath.style.strokeDashoffset = len + 'px';
                    drawPath.style.animation = 'chartDraw .9s ease forwards';
                }
            };
            autoPlot(wrap, draw);
            if (opts.note) card.append(el('div', 'chart-note', opts.note));
            return card;
        }
        function barChart(opts) {
            opts = opts || {};
            const H = opts.height || CHART.h, padL = CHART.padL, padR = CHART.padR,
                  padT = CHART.padT, padB = CHART.padB;
            const labels = opts.labels || [], vals = (opts.values || []).map(v => +v || 0);
            const fmt = opts.format || fmtCompact;
            /* Bars sit one step lighter than a line does, which is how the
               reference paints its own single-series bar set: 62% of the slot
               filled carries far more ink than a 1.4px stroke through the same
               points, and at CH[0] a 24-month set reads as a black fence. */
            const color = opts.color || CH[2];
            const card = el('div', 'chart-card' + (REDUCE_MOTION || opts.noIntro ? '' : ' chart-anim'));
            card.append(chartHead(opts, [{ color }], 'bar'));
            const wrap = el('div', 'chart-wrap'); card.append(wrap);
            if (vals.length < 1) { wrap.append(el('div', 'empty', 'Not enough data in this range yet.')); return card; }
            const n = vals.length, maxV = axisTop(Math.max.apply(null, vals.concat([0])), allWhole(vals));
            const draw = (W) => {
                const svg = svgEl('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H });
                const { X, Y } = drawFrame(svg, { W, H, padL, padR, padT, padB, n, labels, maxV, fmt, tickFmt: opts.tickFormat || fmt, yTicks: true, band: true });
                const bw = Math.max(2, (W - padL - padR) / n * 0.62), tip = el('div', 'chart-tip'); wrap.append(tip);
                const bars = vals.map((v, i) => { const y = Y(v), r = svgEl('rect', { class: 'chart-bar', x: (X(i) - bw / 2).toFixed(1), y: y.toFixed(1), width: bw.toFixed(1), height: Math.max(0, Y(0) - y).toFixed(1), rx: 3, fill: color }); svg.append(r); return r; });
                /* No average rule on a bar chart either: the reference's bars carry
                   nothing but the bars. */
                bars.forEach((r, i) => r.addEventListener('mouseenter', () => { bars.forEach(b => b.style.opacity = .38); r.style.opacity = 1; tip.innerHTML = ''; tip.append(el('div', 'tl', labels[i])); const tr = el('div', 'tr'); const sw = el('span', 'sw'); sw.style.setProperty('--sw', color); tr.append(sw, el('b', null, fmt(vals[i]))); tip.append(tr); const rect = svg.getBoundingClientRect(); const tw = tip.offsetWidth, th = tip.offsetHeight; tip.style.left = Math.max(tw / 2, Math.min(rect.width - tw / 2, X(i) / W * rect.width)) + 'px'; tip.style.top = Math.max(th + 12, Y(vals[i]) / H * rect.height) + 'px'; tip.style.opacity = 1; }));
                svg.addEventListener('mouseleave', () => { bars.forEach(b => b.style.opacity = 1); tip.style.opacity = 0; });
                wrap.append(svg);
            };
            autoPlot(wrap, draw);
            if (opts.note) card.append(el('div', 'chart-note', opts.note));
            return card;
        }
        function catBars(opts) {
            opts = opts || {};
            const items = (opts.items || []).filter(d => d && d.label).slice(0, 8);
            const fmt = opts.format || fmtCompact, color = opts.color || CH[0];
            const card = el('div', 'chart-card' + (REDUCE_MOTION || opts.noIntro ? '' : ' chart-anim'));
            card.append(chartHead(opts, [{ color }], 'cat'));
            const wrap = el('div', 'chart-wrap'); card.append(wrap);
            if (!items.length) { wrap.append(el('div', 'empty', 'No breakdown available for this range.')); return card; }
            const max = Math.max.apply(null, items.map(d => +d.value || 0).concat([1]));
            const bl = el('div', 'barlist'); bl.classList.add('space-above-1');
            items.forEach(d => { const row = el('div', 'barrow'); row.append(el('div', 'bn', d.label)); const tr = el('div', 'bartrack'); const i = el('i'); i.style.width = Math.max(2, (+d.value || 0) / max * 100) + '%'; i.style.setProperty('--bar', color); tr.append(i); row.append(tr, el('div', 'bv', fmt(d.value))); bl.append(row); });
            wrap.append(bl);
            if (opts.note) card.append(el('div', 'chart-note', opts.note));
            return card;
        }

        const CHART_BUILDERS = { trend: (o) => trendChart(o), bar: (o) => barChart(o), cat: (o) => catBars(o) };
        function openChartModal(kind, opts) {
            const builder = CHART_BUILDERS[kind] || CHART_BUILDERS.trend;
            const win = dialog({ title: opts.title || 'Chart', size: 'cmodal', overlayClass: 'chart-modal' });
            /* The modal head already names the chart. Letting the rebuilt card
               print its own title too gave the same word twice, 43px apart, at
               two different weights. The value and the source line stay: the
               head carries neither. */
            win.body.append(builder(Object.assign({}, opts, { height: 360, noExpand: true, title: null })));
        }

        /* The chart ramp is monochrome, like the reference. A series is told
           apart by its position in a grey ramp and by its label, never by hue,
           which is also the one palette that survives being printed or read by
           somebody who does not separate red from green. The two exceptions are
           deliberate and match the reference's own KPI deltas: a rise is green
           and a fall is red, because that is a JUDGEMENT about the number
           rather than a way of telling two series apart. */
        /* The chart ramp, and the ONLY colours a chart may use. Three charts
           were still painting in a purple, a blue and a green from before this
           app went monochrome, so a page of grey lines had three coloured ones
           in it for no reason a reader could work out. */
        const CH = ['--chart-1', '--chart-2', '--chart-3', '--chart-4', '--chart-5'].map(tokenValue);

        /* Monotone cubic (Fritsch-Carlson), which is the rounded shape the
           reference draws - with one deliberate difference. The reference uses a
           NATURAL cubic spline: measured on its own dashboard, 157 of 179
           segments put a control point outside the two data points they join,
           overshooting by as much as 29px. On a demo full of invented numbers
           that is only a look. On a revenue line it draws figures that never
           happened, and between two positive months it can bow below zero.
           Monotone rounds just as much and cannot leave the range of the values
           it was handed: at every peak the tangent is forced flat, and the
           Fritsch-Carlson clamp holds each segment inside its own endpoints. */
        function smoothPath(pts) {
            const n = pts.length;
            if (n < 2) return '';
            const P = (i) => pts[i][0].toFixed(1) + ' ' + pts[i][1].toFixed(1);
            if (n === 2) return 'M' + P(0) + ' L' + P(1);
            const dx = [], d = [];
            for (let i = 0; i < n - 1; i++) {
                dx[i] = pts[i + 1][0] - pts[i][0];
                d[i] = dx[i] ? (pts[i + 1][1] - pts[i][1]) / dx[i] : 0;
            }
            // A sign change between neighbouring secants is a peak or a trough;
            // a zero tangent there is what stops the curve sailing past it.
            const m = [d[0]];
            for (let i = 1; i < n - 1; i++) m[i] = (d[i - 1] * d[i] <= 0) ? 0 : (d[i - 1] + d[i]) / 2;
            m[n - 1] = d[n - 2];
            for (let i = 0; i < n - 1; i++) {
                if (d[i] === 0) { m[i] = 0; m[i + 1] = 0; continue; }
                const a = m[i] / d[i], b = m[i + 1] / d[i], q = a * a + b * b;
                if (q > 9) { const t = 3 / Math.sqrt(q); m[i] = t * a * d[i]; m[i + 1] = t * b * d[i]; }
            }
            let out = 'M' + P(0);
            for (let i = 0; i < n - 1; i++) {
                const h = dx[i] / 3;
                out += ' C' + (pts[i][0] + h).toFixed(1) + ' ' + (pts[i][1] + m[i] * h).toFixed(1)
                     + ' ' + (pts[i + 1][0] - h).toFixed(1) + ' ' + (pts[i + 1][1] - m[i + 1] * h).toFixed(1)
                     + ' ' + P(i + 1);
            }
            return out;
        }

        function sparkline(values, color) {
            const W = 120, H = 32, p = 3; const vals = (values || []).map(Number);
            /* Fills its slot instead of being letterboxed into the middle of it:
               the default xMidYMid meet drew a 120-unit curve 112px wide in a
               271px card, so the line read as a doodle floating in white. The
               stroke is non-scaling, so stretching x does not thicken it. */
            const svg = svgEl('svg', { class: 'spark', viewBox: '0 0 ' + W + ' ' + H, preserveAspectRatio: 'none' });
            if (vals.length < 2) return svg;
            const mn = Math.min.apply(null, vals), mx = Math.max.apply(null, vals), rng = (mx - mn) || 1;
            const X = i => p + i / (vals.length - 1) * (W - 2 * p), Y = v => p + (1 - (v - mn) / rng) * (H - 2 * p);
            const d = smoothPath(vals.map((v, i) => [X(i), Y(v)]));
            svg.append(svgEl('path', { d, fill: 'none', stroke: color || CH[0], 'stroke-width': 2, 'vector-effect': 'non-scaling-stroke', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
            return svg;
        }

        const tail = (arr, k) => (arr || []).slice(Math.max(0, (arr || []).length - k));
        const sumv = (arr) => (arr || []).reduce((a, b) => a + (+(b && b.value) || 0), 0);
        function trendsHeader(title, control) {
            const row = el('div', 'section-title');
            row.append(el('span', null, title));
            if (control) row.append(control);
            return row;
        }
        /* Both trend blocks are one heading carrying the range control and a set
           of chart cards under it. Switching the range used to re-render the
           whole VIEW: the page snapped back to the top, the button the user had
           just pressed jumped 200px up the screen, every ticked opportunity and
           open disclosure was thrown away, and four cards plus their lines
           replayed a second of entrance. Only the cards are rebuilt now - the
           heading, the control under the cursor and the scroll offset all stay
           exactly where they are, and a repaint never re-runs an entrance.
           The new cards go in BEFORE the old ones come out, so the column never
           collapses to nothing in between and no scroll offset gets clamped. */
        function trendsSection(box, title, range, setRange, paint, intro, bare) {
            const seg = segmented(RANGE_OPTS, range, (v) => { range = v; setRange(v); repaint(false); }, { label: 'Range' });
            /* No range control over a section with no charts: it switched
               nothing, and read as working. */
            box.append(trendsHeader(title, bare ? null : seg));
            /* Tracked as nodes rather than from a marker, because cardifySections
               may move the whole block into a card wrapper after this runs: the
               charts go back wherever the last one ended up. */
            let owned = [];
            function repaint(first) {
                const frag = document.createDocumentFragment();
                paint(frag, range, !first);
                const next = [].slice.call(frag.childNodes);
                const tailNode = owned[owned.length - 1];
                if (tailNode && tailNode.parentNode) tailNode.parentNode.insertBefore(frag, tailNode.nextSibling);
                else box.append(frag);
                owned.forEach(n => n.remove());
                owned = next;
            }
            repaint(!!intro);
        }
        const _avg = (a) => a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0;
        /* The window the card's own number covers. The range control sits 44px
           away and governs exactly this, so each card names the span it is
           showing rather than leaving two different unlabelled figures for the
           same metric on one screen. */
        const rangeLabel = (r) => 'last ' + r + ' months';
        /* Said once for both position charts (copy plan, pattern 15). */
        const POSITION_HELP = 'Lower is better. Position 1 is the top of search results.';
        function renderTrendsBlock(box, trends, currency, range, onRange, intro, id, o) {
            o = o || {};
            const has = (k) => trends && trends[k] && trends[k].length;
            const bare = !trends || !(has('revenue') || has('orders') || has('sessions') || has('clicks'));
            const money = (n) => moneyShort(n, currency);
            const pct = (n) => (Math.round((+n || 0) * 10) / 10) + '%';
            const num1 = (n) => String(Math.round((+n || 0) * 10) / 10);
            const cur = currency || 'Revenue';
            const L = (a) => a.map(p => monthLabel(p.label)), V = (a) => a.map(p => +p.value || 0);
            /* A month with no orders has no average: a gap, not a zero. */
            const Vgap = (a) => a.map(p => (p.value == null ? null : +p.value));
            const paint = (host, months, noIntro) => {
                if (bare) {
                    /* One line and the way on (copy plan, Overview #6). */
                    let go = null;
                    if (guideAdmin()) { go = textButton(); go.type = 'button'; go.append(ico(I.settings), document.createTextNode('Connect Google')); go.onclick = openSettings; }
                    host.append(emptyState({ icon: I.trendUp, text: 'No trends yet. Connect Google to add traffic.', action: go }));
                    return;
                }
                const S = (k) => tail(trends[k], months);
                /* 320 under the full-width hero and 280 in the grid, the depth the
                   reference draws its own plot at. At 220 the WIDEST card on the
                   page held the SHALLOWEST plot: a 6.8:1 band that flattened
                   every move in the series it was drawing. */
                const base = { period: rangeLabel(months), noIntro: noIntro, height: 280 };
                const sho = (o) => Object.assign({ source: 'Shopify orders' }, base, o);
                const ga = (o) => Object.assign({ source: 'Google Analytics 4' }, base, o);
                const gsc = (o) => Object.assign({ source: 'Google Search Console' }, base, o);

                // --- Shopify: revenue, orders, AOV ---
                if (has('revenue')) { const a = S('revenue'); host.append(trendChart(sho({ title: 'Revenue', yUnit: cur, value: money(sumv(a)), labels: L(a), series: [{ name: 'Revenue', color: CH[0], values: V(a) }], format: money, tickFormat: fmtCompact, height: 320 }))); }
                /* Revenue leads at full width; every other chart shares ONE grid.
                   A grid per source held a single card whenever a source was thin,
                   and :only-child then stretched each one to full width, so the
                   page read as a column of four identical cards instead of pairs. */
                const g = el('div', 'charts-grid');
                if (has('orders')) { const a = S('orders'); g.append(barChart(sho({ title: 'Orders', yUnit: 'Orders', value: fmtCompact(sumv(a)), labels: L(a), values: V(a), format: fmtCompact }))); }
                /* The card's figure is the range's revenue over its orders. The
                   mean of twelve monthly ratios weighted a one-order month like
                   a forty-order one and counted empty months as zero. */
                if (has('aov')) {
                    const a = S('aov');
                    const r = has('revenue') ? sumv(S('revenue')) : 0, o = has('orders') ? sumv(S('orders')) : 0;
                    const avg = o ? r / o : _avg(Vgap(a).filter(v => v != null));
                    g.append(trendChart(sho({ title: 'Average order value', yUnit: cur, value: money(avg), labels: L(a), series: [{ name: 'Average order value', color: CH[0], values: Vgap(a) }], format: money, tickFormat: fmtCompact })));
                }

                // --- Google Analytics 4: sessions, pageviews, channels ---
                if (has('sessions')) { const a = S('sessions'); g.append(trendChart(ga({ title: 'Sessions', yUnit: 'Sessions', value: fmtCompact(sumv(a)), labels: L(a), series: [{ name: 'Sessions', color: CH[0], values: V(a) }], format: fmtCompact }))); }
                if (has('pageviews')) { const a = S('pageviews'); g.append(trendChart(ga({ title: 'Pageviews', yUnit: 'Views', value: fmtCompact(sumv(a)), labels: L(a), series: [{ name: 'Views', color: CH[0], values: V(a) }], format: fmtCompact }))); }
                /* The channel totals are not sliced by the range control: they
                   cover every month fetched, so the card says that span rather
                   than borrowing the control's. It keeps its own height beside
                   a taller neighbour instead of stretching to 237px of white. */
                if (has('channels') && !o.noChannels) {
                    const span = Math.min(24, Math.max(1, ...['sessions', 'revenue', 'orders'].map(k => (trends[k] || []).length)));
                    const cb = catBars(ga({ title: 'Traffic by channel', source: 'Google Analytics 4', period: rangeLabel(span), color: CH[0], items: trends.channels, format: fmtCompact }));
                    cb.classList.add('chart-top'); g.append(cb);
                }

                // --- Search Console: clicks, impressions, CTR, position ---
                if (has('clicks')) { const a = S('clicks'); g.append(trendChart(gsc({ title: 'Search clicks', yUnit: 'Clicks', value: fmtCompact(sumv(a)), labels: L(a), series: [{ name: 'Clicks', color: CH[0], values: V(a) }], format: fmtCompact }))); }
                if (has('impressions')) { const a = S('impressions'); g.append(trendChart(gsc({ title: 'Impressions', yUnit: 'Impressions', value: fmtCompact(sumv(a)), labels: L(a), series: [{ name: 'Impressions', color: CH[0], values: V(a) }], format: fmtCompact }))); }
                if (has('ctr')) { const a = S('ctr'); g.append(trendChart(gsc({ title: 'Search click-through rate', yUnit: 'CTR %', value: pct(_avg(V(a))), labels: L(a), series: [{ name: 'CTR', color: CH[0], values: V(a) }], format: pct, fitY: true, annotate: false }))); }
                if (has('position')) { const a = S('position'); g.append(trendChart(gsc({ title: 'Average Google position', yUnit: 'Position', value: num1(_avg(V(a))), labels: L(a), series: [{ name: 'Position', color: CH[0], values: V(a) }], format: num1, fitY: true, area: false, annotate: false, help: POSITION_HELP }))); }
                if (g.children.length) host.append(g);
            };
            /* The heading and every chart under it are one block on the page,
               built here because trendsSection's repaint swaps nodes it owns
               and a wrapper put round them from outside would break the range
               switch. The heading is folded or marked here too, since the
               page's own cardifySections only walks the page's top level. */
            const group = el('div', 'widget-group');
            if (id) widget(group, id, 'full', 'Performance over time');
            box.append(group);
            trendsSection(group, 'Performance over time', range, onRange, paint, intro, bare);
            cardifySections(group);
        }
        function renderSeoTrends(box, trends, range, onRange, intro, id) {
            const has = (k) => trends && trends[k] && trends[k].length;
            const bare = !trends || !(has('clicks') || has('impressions'));
            const pct = (n) => (Math.round((+n || 0) * 10) / 10) + '%', num1 = (n) => String(Math.round((+n || 0) * 10) / 10);
            const L = (a) => a.map(p => monthLabel(p.label)), V = (a) => a.map(p => +p.value || 0);
            const paint = (host, months, noIntro) => {
                if (bare) { host.append(el('div', 'empty', 'Connect Search Console to see search trends.')); return; }
                const S = (k) => tail(trends[k], months);
                const gsc = (o) => Object.assign({ source: 'Google Search Console', period: rangeLabel(months), noIntro: noIntro, height: 280 }, o);
                const g1 = el('div', 'charts-grid');
                if (has('clicks')) { const a = S('clicks'); g1.append(trendChart(gsc({ title: 'Clicks', yUnit: 'Clicks', value: fmtCompact(sumv(a)), labels: L(a), series: [{ name: 'Clicks', color: CH[0], values: V(a) }], format: fmtCompact }))); }
                if (has('impressions')) { const a = S('impressions'); g1.append(trendChart(gsc({ title: 'Impressions', yUnit: 'Impressions', value: fmtCompact(sumv(a)), labels: L(a), series: [{ name: 'Impressions', color: CH[0], values: V(a) }], format: fmtCompact }))); }
                host.append(g1);
                const g2 = el('div', 'charts-grid');
                if (has('ctr')) { const a = S('ctr'); g2.append(trendChart(gsc({ title: 'Click-through rate', yUnit: 'CTR %', value: pct(_avg(V(a))), labels: L(a), series: [{ name: 'CTR', color: CH[0], values: V(a) }], format: pct, fitY: true, annotate: false }))); }
                if (has('position')) { const a = S('position'); g2.append(trendChart(gsc({ title: 'Average position', yUnit: 'Position', value: num1(_avg(V(a))), labels: L(a), series: [{ name: 'Position', color: CH[0], values: V(a) }], format: num1, fitY: true, area: false, annotate: false, help: POSITION_HELP }))); }
                if (g2.children.length) host.append(g2);
            };
            /* One block on the page, heading and both chart grids, built here
               for the reason renderTrendsBlock gives: trendsSection repaints by
               swapping the nodes it owns, so nothing outside may wrap them. */
            const group = el('div', 'widget-group');
            if (id) widget(group, id, 'full', 'Search performance over time');
            box.append(group);
            trendsSection(group, 'Search performance over time', range, onRange, paint, intro, bare);
            cardifySections(group);
        }

