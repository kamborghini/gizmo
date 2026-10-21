        /* ---------- structured response components ---------- */
        const METRIC_HELP = [
            ['repeat rate', 'The share of your purchasing customers who have ordered more than once. Higher means stronger retention.'],
            ['lifetime value', 'Average total a purchasing customer has spent with you across all their orders.'],
            ['order value', 'Average amount spent per order (revenue divided by orders).'],
            ['conversion', 'Share of sessions that resulted in an order.'],
            ['sessions', 'Visits to your store, from Google Analytics.'],
            ['pageview', 'Pages viewed across all sessions, from Google Analytics.'],
            ['impression', 'How many times your store appeared in Google search results.'],
            ['ctr', 'Click-through rate: clicks divided by impressions in search.'],
            ['position', 'Your average ranking position in Google search. Lower is better.'],
            ['clicks', 'Clicks to your store from Google search results.'],
            ['ad spend', 'Total spent on Google Ads in the period.'],
            ['cpc', 'Average cost per click on your paid ads.'],
            ['roas', 'Return on ad spend: revenue divided by ad cost. Above 1 covers the ad cost.'],
            ['revenue', 'Total sales in the period, from Shopify orders.'],
            ['orders', 'Number of orders placed in the period.'],
            ['unfulfilled', 'Orders that still need to be shipped.'],
            ['low stock', 'Variants at or below your low-stock threshold.'],
            ['new customers', 'Customers who created their account in the period.'],
            ['new (', 'Customers who created their account in the last 30 days.'],
            ['at risk', 'Repeat customers who have not ordered recently and may be churning.'],
            ['customers', 'Total customers on record.'],
        ];
        const metricHelp = (label) => { const l = (label || '').toLowerCase(); for (const [k, v] of METRIC_HELP) if (l.includes(k)) return v; return null; };
        /* The glyph on the card's icon tile. Matched on the label the same way
           the help text is, and in the same order, so "order value" is money
           and "orders" is a box rather than both landing on whichever entry
           came first. Nothing new is drawn: every icon here is already in I. */
        /* Every KPI names its own glyph. The fallback was the bolt that is
           also the app's logo, so Products, Units sold and all three Loans
           tiles wore the logo, and Orders shared its box with Low stock. */
        const METRIC_ICON = [
            ['repeat rate', 'rotate'], ['lifetime value', 'card'], ['order value', 'card'],
            ['conversion', 'trendUp'], ['sessions', 'users'], ['pageview', 'eye'],
            ['impression', 'eye'], ['ctr', 'trendUp'], ['position', 'bookmark'],
            ['clicks', 'search'], ['ad spend', 'card'], ['cpc', 'card'], ['roas', 'trendUp'],
            ['revenue', 'card'], ['orders', 'box'], ['unfulfilled', 'truck'],
            ['low stock', 'warning'], ['new customers', 'userCheck'], ['new (', 'userCheck'],
            ['at risk', 'warning'], ['customers', 'users'], ['products', 'tag'], ['units', 'tag'],
            ['out now', 'truck'], ['on the shelf', 'projector'], ['overdue', 'clock'],
        ];
        const metricIconKey = (label) => {
            const l = (label || '').toLowerCase();
            for (const [k, v] of METRIC_ICON) if (l.includes(k)) return v;
            return 'grid';
        };
        /* A change is coloured by what it MEANS, and only when the label's
           meaning is known (the mix, spec 6, keeping the 2026-09 rule that a
           rising number is not congratulated by reflex): green when the move is
           good for the shop, red when it is bad, and the neutral chip, still with
           its arrow and its hidden "up" or "down", for a label on neither list.
           A report's or an answer's metrics can be labelled anything, so an
           unknown label is never green. The three lists are read in this order:
           the phrases that contain a bad word but are good ("Returning customers",
           "Return on ad spend"), then what is bad when it rises, then what is good. */
        const RISE_IS_GOOD_FIRST = ['returning', 'return on', 'roas', 'repeat'];
        const RISE_IS_BAD = ['unfulfilled', 'low stock', 'at risk', 'position', 'cpc', 'ad spend', 'overdue', 'failed', 'quarantined', 'owed', 'outstanding',
            'refund', 'return', 'cancel', 'churn', 'bounce', 'abandon', 'cost', 'complaint', 'chargeback', 'dispute', 'unpaid', 'debt', 'backlog', 'delay',
            'waiting', 'pending', 'error', 'loss', 'lost', 'discrepanc', 'unmatched', 'missed', 'late order', 'late deliver', 'late payment', 'slow',
            'out of stock', 'stockout', 'unread', 'unassigned', 'spam', 'fraud', 'declined', 'damaged', 'defect'];
        const RISE_IS_GOOD = ['revenue', 'sales', 'orders', 'sessions', 'visitors', 'traffic', 'conversion', 'customers', 'profit', 'margin', 'average order',
            'aov', 'basket', 'clicks', 'impressions', 'ctr', 'lifetime value', 'ltv', 'units sold', 'subscribers', 'leads', 'taken', 'expected'];
        function deltaTone(label, trend, better) {
            if (trend !== 'up' && trend !== 'down') return 'flat';
            const l = String(label || '').toLowerCase();
            let riseBad = null;
            if (better === 'down') riseBad = true;
            else if (better === 'up') riseBad = false;
            else if (RISE_IS_GOOD_FIRST.some(k => l.includes(k))) riseBad = false;
            else if (RISE_IS_BAD.some(k => l.includes(k))) riseBad = true;
            else if (RISE_IS_GOOD.some(k => l.includes(k))) riseBad = false;
            if (riseBad === null) return 'flat';
            return (trend === 'up') !== riseBad ? 'good' : 'bad';
        }
        function changeChip(trend, text, tone) {
            const t = trend === 'up' || trend === 'down' ? trend : 'flat';
            const d = el('span', 'delta ' + t + ' ' + (tone || 'flat'));
            if (t === 'up') d.append(ico(I.arrowUpRight)); else if (t === 'down') d.append(ico(I.arrowDownRight));
            if (t !== 'flat') d.append(el('span', 'sr-only', t === 'up' ? 'up ' : 'down '));
            d.append(document.createTextNode(text));
            return d;
        }
        /* A bar's domain: the round span around every value it shows, in steps
           of the largest power of ten under the top value (41,327 to 66,054
           with a plan of 37,566 is drawn on 30,000 to 70,000). */
        function bandDomain(vals) {
            const v = vals.filter(x => x != null && isFinite(x)).map(Number);
            if (!v.length) return { min: 0, max: 1 };
            const top = Math.max.apply(null, v), bot = Math.min.apply(null, v);
            const step = Math.pow(10, Math.floor(Math.log10(Math.max(1, Math.abs(top)))));
            const min = Math.floor(bot / step) * step, max = Math.ceil(top / step) * step;
            return { min, max: max > min ? max : min + step };
        }
        const bandPct = (v, d) => Math.max(0, Math.min(100, (v - d.min) / (d.max - d.min) * 100)).toFixed(1) + '%';
        /* The likely range as one bar (the mix, spec 6): a teal-glow fill with
           a teal-line edge from low to high, an ink dot at the expected figure,
           the plan as a blue tick with its label above, the ends and "Likely
           range" under. r: { lo, hi, exp, plan, d, planLabel, loLabel, hiLabel, midLabel } */
        function rangeBar(r) {
            const w = el('div', 'fb-range');
            w.style.setProperty('--at-lo', bandPct(r.lo, r.d)); w.style.setProperty('--at-hi', bandPct(r.hi, r.d));
            w.style.setProperty('--at-exp', bandPct(r.exp, r.d));
            if (r.plan != null) w.style.setProperty('--at-plan', bandPct(r.plan, r.d));
            const track = el('div', 'fb-track');
            track.append(el('div', 'fb-fill'));
            if (r.plan != null) track.append(el('div', 'fb-plan'));
            track.append(el('div', 'fb-exp'));
            // Past the middle the label ends at its tick, so a plan near the top
            // of the range keeps its label on the bar.
            if (r.plan != null && r.planLabel) w.append(el('span', 'fb-rl t' + (parseFloat(bandPct(r.plan, r.d)) > 50 ? ' end' : ''), r.planLabel));
            w.append(track);
            [[r.lo, r.loLabel, ''], [r.exp, r.midLabel, ' mid'], [r.hi, r.hiLabel, '']].forEach(([v, t, c]) => {
                if (!t) return;
                const s = el('span', 'fb-rl b' + c, t); s.style.setProperty('--at', bandPct(v, r.d)); w.append(s);
            });
            return w;
        }
        /* A meter: what is taken in the measure's dark teal, what is still
           expected after it at 45%, the plan as a blue tick. m: { taken, plan,
           end } in percent of the track; the light part runs to end (the track's
           own end when there is none). */
        function meter(m) {
            const w = el('div', 'fb-meter');
            const t = Math.max(0, Math.min(100, m.taken || 0)).toFixed(1) + '%';
            w.style.setProperty('--w', t); w.style.setProperty('--at', t);
            if (m.end != null) w.style.setProperty('--end', Math.max(0, Math.min(100, m.end)).toFixed(1) + '%');
            w.append(el('i', 'taken'), el('i', 'still'));
            if (m.plan != null) { w.style.setProperty('--at-plan', Math.max(0, Math.min(100, m.plan)).toFixed(1) + '%'); w.append(el('i', 'plan')); }
            w.setAttribute('aria-hidden', 'true');
            return w;
        }
        /* The feature band (the mix, spec 6): one per screen at most, for its
           main question. o: { main: { icon, label, info, value, chip, note,
           range }, sides: [{ icon, label, value, chip, note, meter }] }. */
        function featureBand(o) {
            const band = el('section', 'fband');
            const head = (f) => {
                const h = el('div', 'fb-head');
                const t = el('span', 'fb-tile'); t.setAttribute('aria-hidden', 'true'); t.append(ico(f.icon)); h.append(t);
                h.append(el('span', 'fb-label', f.label));
                if (f.info) h.append(f.info);
                return h;
            };
            const main = el('div', 'fb-main');
            main.append(head(o.main));
            const hero = el('div', 'fb-hero');
            hero.append(el('b', 'fb-fig', o.main.value));
            if (o.main.chip) hero.append(o.main.chip);
            if (o.main.note) hero.append(el('span', 'fb-note', o.main.note));
            main.append(hero);
            if (o.main.range) main.append(o.main.range);
            band.append(main);
            if (o.sides && o.sides.length) {
                const rule = el('div', 'fb-rule'); rule.setAttribute('aria-hidden', 'true'); band.append(rule);
                const sides = el('div', 'fb-sides');
                o.sides.forEach(s => {
                    const box = el('div', 'fb-side');
                    box.append(head(s));
                    const num = el('div', 'fb-num');
                    num.append(el('b', 'fb-fig', s.value));
                    if (s.chip) num.append(s.chip);
                    if (s.note) num.append(el('span', 'fb-note', s.note));
                    box.append(num);
                    if (s.meter) box.append(s.meter);
                    sides.append(box);
                });
                band.append(sides);
            }
            return band;
        }
        /* A list of rows (the mix, spec 6). items: [{ icon, label, n, unit,
           onClick }]; opts: { label, cols }. With cols 2 the rows read down the
           first column, then the second, so a phone's one column keeps that order. */
        function listRows(items, opts) {
            opts = opts || {};
            /* A caller may leave a row out by passing null in its place. */
            const list = items.filter(Boolean);
            const nav = el('nav', 'rlist' + (opts.cols === 2 ? ' cols-2' : ''));
            if (opts.label) nav.setAttribute('aria-label', opts.label);
            if (opts.cols === 2) nav.style.setProperty('--rows', String(Math.ceil(list.length / 2)));
            list.forEach(it => {
                const b = el('button', 'rlist-row');
                b.type = 'button';
                if (it.icon) b.append(ico(it.icon));
                b.append(el('span', 'lbl', it.label));
                if (it.n != null) {
                    const c = el('span', 'cnt', String(it.n));
                    if (it.unit) c.append(el('span', 'sr-only', ' ' + it.unit));
                    b.append(c);
                }
                b.append(ico(I.chev));
                b.onclick = it.onClick;
                nav.append(b);
            });
            return nav;
        }
        /* The empty state (the mix, spec 6): a 40 tile with the screen's own
           icon on the fill, one line in the head step, then its action, centred
           in its space. No illustration and no box. o: { icon, text, action, cls } */
        function emptyState(o) {
            const box = el('div', 'empty-state' + (o.cls ? ' ' + o.cls : ''));
            const t = el('span', 'empty-ic'); t.setAttribute('aria-hidden', 'true'); t.append(ico(o.icon || I.grid));
            const txt = el('div', 'empty-txt');
            txt.append(el('p', 'empty-line', o.text));
            if (o.sub) txt.append(el('p', 'empty-sub', o.sub));
            box.append(t, txt);
            if (o.action) box.append(o.action);
            return box;
        }
        /* Queue counters (the mix, spec 6): the queues that make a flow as big
           tiles in flow order, a chevron between, the chosen one a teal fill
           with the focal glow; the other queues as tabs beside them. flow:
           [[key, label, count]]; rest: [[key, label, icon]]. A count not known
           yet keeps its line with a space. */
        function queueCounters(flow, rest, current, onPick, label) {
            const nav = el('nav', 'queues'); nav.setAttribute('aria-label', label || 'Queues');
            const mark = (b, k) => {
                b.type = 'button'; b.dataset.k = k;
                if (k === current) { b.classList.add('on'); b.setAttribute('aria-current', 'page'); }
                b.onclick = () => { if (k !== current) onPick(k); };
            };
            flow.forEach(([k, l, n], i) => {
                if (i) { const s = el('span', 'qsep'); s.setAttribute('aria-hidden', 'true'); s.append(ico(I.chev)); nav.append(s); }
                const b = el('button', 'qc'); mark(b, k);
                b.append(el('span', 'qc-l', l), el('b', 'qc-n', n == null ? ' ' : String(n)));
                nav.append(b);
            });
            const r = el('div', 'qrest');
            rest.forEach(([k, l, icon, n, unit]) => {
                const b = el('button', 'qt'); mark(b, k); b.append(ico(icon), document.createTextNode(l));
                if (n != null) { const c = el('span', 'cnt', String(n)); if (unit) c.append(el('span', 'sr-only', ' ' + unit)); b.append(c); }
                r.append(b);
            });
            nav.append(r);
            return nav;
        }
        /* A switch built in the script (the static ones in the markup are
           wired by syncToggles). It flips on a press and says its state. */
        function switchBtn(label, on, onToggle) {
            const b = el('button', 'toggle' + (on ? ' on' : ''));
            b.type = 'button'; b.setAttribute('role', 'switch'); b.setAttribute('aria-checked', String(!!on));
            b.append(el('span', 'sw'), document.createTextNode(label));
            b.onclick = () => {
                const now = b.getAttribute('aria-checked') !== 'true';
                b.setAttribute('aria-checked', String(now)); b.classList.toggle('on', now);
                onToggle(now);
            };
            return b;
        }
        function statCard(m, i) {
            const c = el('div', 'stat' + (m.tone === 'warn' ? ' warn' : m.tone === 'bad' ? ' bad' : ''));
            c.style.animationDelay = (i * 40) + 'ms';
            /* Decoration, and the label right under it already names the metric,
               so it is hidden from the reader that would otherwise announce a
               second name for the same card. */
            const icEl = el('div', 'stat-ic'); icEl.innerHTML = I[metricIconKey(m.label)];
            icEl.setAttribute('aria-hidden', 'true');
            c.append(icEl);
            const labelEl = el('div', 'label', m.label);
            const help = metricHelp(m.label);
            /* A title on a div is a pointer-only affordance: focusable, it is
               read as the label's description and the hover cue can answer a
               keyboard as well. */
            /* Its explanation is an info button beside it (the mix, spec 7): a
               tap and the keyboard open it as well as a pointer. */
            if (help) labelEl.append(infoButton(m.label, { title: m.label, body: help }));
            c.append(labelEl);
            /* Number and change on ONE line, as the reference has them: the
               change is a small pill beside the figure, not a tinted bar
               spanning the card, which is what it became when it was a block
               of its own. */
            const row = el('div', 'stat-row');
            /* A figure the server could not work out says so in words, at the
               body size, not as a headline figure. */
            row.append(el('div', 'value' + (m.tone === 'unknown' ? ' unknown' : ''), m.value));
            if (m.delta) row.append(changeChip(m.trend, m.delta, deltaTone(m.label, m.trend, m.better)));
            c.append(row);
            /* The quiet line under the number, saying what it is OF. The
               reference gives every KPI one. */
            if (m.note) c.append(el('p', 'stat-note', m.note));
            if (Array.isArray(m.spark) && m.spark.length > 1) {
                const sw = el('div', 'stat-spark');
                /* Off the ramp, not the semantic pair. The delta badge beside the
                   number already carries the colour and the sign; a green or red
                   line under it says the same thing a second time, louder, and
                   left saturated strokes as the only strong colour on a page the
                   reference keeps monochrome apart from that one badge. */
                sw.append(sparkline(m.spark, CH[2]));
                c.append(sw);
            }
            if (m.detail && typeof m.detail === 'object') statOpens(c, m);
            return c;
        }
        /* A KPI with the list behind its number is a button that opens it. The
           corner arrow is the reference's CardAction cue (ArrowUpRight on its
           Store Traffic and Top Products cards): the one mark that says a card
           goes somewhere. A card that filters the list under it (Finance,
           Reconciliation) carries a ring instead, which fills with a tick when
           it is the filter that is set. */
        function statAct(svg) { const a = el('span', 'stat-act'); a.innerHTML = svg || ''; a.setAttribute('aria-hidden', 'true'); return a; }
        /* A figure that opens the list behind it. The tile is not itself a button: its label holds an info
           button, and a button cannot hold one (a screen reader could not reach it). A real button in the
           tile's corner is the keyboard and screen-reader way in, with the tile's old name; a click anywhere on
           the tile still opens it, as before (an info button's own click stops short of the tile, and this
           button's bubbles to it, so the list opens once). Focus returns to the button. */
        function statOpens(c, m) {
            c.classList.add('stat-open');
            const b = el('button', 'stat-act stat-open-btn'); b.type = 'button'; b.innerHTML = I.arrowUpRight;
            b.setAttribute('aria-haspopup', 'dialog');
            b.setAttribute('aria-label', m.label + ': ' + m.value + '. Open the list behind it');
            c.append(b);
            c.addEventListener('click', () => openStatDetail(m, b));
        }
        function openStatDetail(m, opener) {
            const d = m.detail || {};
            /* .smodal, not .cmodal: the chart modal's 980px cap would win on source order. */
            const win = dialog({ title: m.label, size: 'smodal', overlayClass: 'chart-modal', opener: opener });
            const { body } = win;
            const sum = el('div', 'stat-detail-sum' + (m.tone === 'warn' ? ' warn' : ''));
            sum.append(el('div', 'value', m.value));
            if (d.title) sum.append(el('div', 'stat-detail-title', d.title));
            body.append(sum);
            const items = Array.isArray(d.items) ? d.items : [];
            if (!items.length) body.append(el('div', 'empty', d.empty || 'Nothing to list.'));
            else {
                const rows = el('div', 'drill-rows');
                items.forEach(it => {
                    const r = el('div', 'drill-row');
                    const name = it.url ? el('a', null, it.label || it.url) : el('span', 'drill-name', it.label || '');
                    if (it.url) { name.href = it.url; name.target = '_blank'; name.rel = 'noopener'; name.title = it.url; }
                    r.append(name);
                    if (it.note) r.append(el('span', 'note', it.note));
                    rows.append(r);
                });
                body.append(rows);
                if (d.total > items.length) body.append(el('p', 'drill-more', 'Showing the first ' + items.length + ' of ' + d.total + '.'));
            }
        }
        // Attach a 12-point sparkline to each KPI by matching its label to a trend series.
        function sparkFor(label, trends) {
            if (!trends) return null;
            const l = (label || '').toLowerCase();
            const pick = (k) => (trends[k] && trends[k].length) ? tail(trends[k], 12).map(p => +p.value || 0) : null;
            if (l.includes('order value') || l.includes('aov')) return pick('aov');
            if (l.includes('revenue')) return pick('revenue');
            if (l.includes('order')) return pick('orders');
            if (l.includes('session')) return pick('sessions');
            if (l.includes('pageview')) return pick('pageviews');
            if (l.includes('impression')) return pick('impressions');
            if (l.includes('click')) return pick('clicks');
            if (l.includes('ctr')) return pick('ctr');
            if (l.includes('position')) return pick('position');
            return null;
        }
        const withSparks = (metrics, trends) => (metrics || []).map(m => {
            const s = sparkFor(m.label, trends);
            return (s && s.length > 1) ? Object.assign({}, m, { spark: s }) : m;
        });
        function metricsGrid(metrics) {
            const g = el('div', 'metrics');
            metrics.forEach((m, i) => g.append(statCard(m, i)));
            return g;
        }
        /* The reference's Analytics strip: the same cards in ONE frame, divided
           by hairlines, with the figure a step smaller. Finance's box is the
           same idea at the Finance page's larger sizes. */
        function metricsStrip(metrics, finance) {
            const g = metricsGrid(metrics);
            g.classList.add('metrics-strip');
            if (finance) g.classList.add('metrics-finance');
            return g;
        }
        /* ONE TABLE (see .dtable). cols: [{ head, cls }] in order, cls one of
           stack, num, act, sort, email, ind; the tracks come from opts.cls in
           CSS (.dt-<name> { --dt-cols }). rows: [{ cells, cls }] with the cells
           in column order, each a Node or a string. opts.empty is what an empty
           list shows instead: its one line, no head over nothing. opts.stop is
           the width its rows turn two-line at: xs, s, m (the default) or l.
           opts.main is the column whose cell leads a two-line row (the first
           unless said). A column with cap (true, or its own word) names its
           value in a two-line row, where the head is gone: "Orders 5", not "5". */
        function dtable(cols, rows, opts) {
            opts = opts || {};
            if (!rows.length) return opts.empty || el('div', 'empty', 'Nothing here yet.');
            const wrap = el('div', 'dt dt-' + (opts.stop || 'm'));
            const t = el('div', 'dtable ' + (opts.cls || ''));
            t.setAttribute('role', 'table');
            if (opts.label) t.setAttribute('aria-label', opts.label);
            const h = el('div', 'dt-head'); h.setAttribute('role', 'row');
            cols.forEach(c => {
                const x = el('div', 'dt-c' + (c.cls ? ' ' + c.cls : '')); x.setAttribute('role', 'columnheader');
                if (c.head) x.append(c.head); h.append(x);
            });
            t.append(h);
            rows.forEach(r => {
                const row = el('div', 'dt-row' + (r.cls ? ' ' + r.cls : '')); row.setAttribute('role', 'row');
                /* A row that opens what it lists: the whole row answers a pointer,
                   and its main cell carries the button a keyboard reaches. */
                if (r.onClick) { row.classList.add('click'); row.onclick = r.onClick; }
                if (r.open) row.classList.add('open');
                r.cells.forEach((c, i) => {
                    const cell = el('div', 'dt-c' + (i === (opts.main || 0) ? ' dt-main' : '') + (cols[i] && cols[i].cls ? ' ' + cols[i].cls : ''));
                    cell.setAttribute('role', 'cell');
                    if (cols[i] && cols[i].cap) cell.dataset.h = cols[i].cap === true ? cols[i].head : cols[i].cap;
                    if (c !== null && c !== undefined && c !== '') cell.append(c);
                    row.append(cell);
                });
                t.append(row);
                /* An opened row's detail sits under it across every column. */
                if (r.after) { const det = el('div', 'dt-detail'); det.append(r.after); t.append(det); }
            });
            wrap.append(t);
            return wrap;
        }
        /* A table's main cell: a dot when the row has a state, the name, and its
           grey second line. */
        function dtMain(name, sub, dot) {
            const f = document.createDocumentFragment();
            const n = el('span', 'dt-name');
            if (dot !== undefined) n.append(el('span', 'dt-dot' + (dot ? ' ' + dot : '')));
            n.append(document.createTextNode(name || ''));
            f.append(n);
            if (sub) f.append(el('span', 'dt-sub', sub));
            return f;
        }
