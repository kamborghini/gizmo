        /* ---------- customers & retention ---------- */
        let customersCache = {};       // segKey -> { data, at }
        let customersSeg = '__all__';  // current sector ('__all__' = comprehensive across sectors)
        let customerTags = null;       // detected sectors [{tag, count}] (null = not yet loaded)
        const SEG_ALL = '__all__';
        function segOptions() {
            const opts = [{ label: 'All customers', value: SEG_ALL }];
            (customerTags || []).forEach(t => opts.push({ label: t.tag, value: t.tag }));
            return opts;
        }
        async function loadCustomerTags() {
            if (customerTags !== null) return;   // load once per session
            /* The load-once guard keys on null, so writing [] in the catch made
               a single failed fetch permanent: the picker offered nothing but
               Comprehensive for the rest of the session and never said why.
               Leave it null so the next call retries. */
            try { const d = await api('/api/customer-tags', {}); customerTags = (d && Array.isArray(d.tags)) ? d.tags : []; }
            catch (e) { customerTags = null; toastError('The customer segments could not be loaded. ' + (e.message || '')); }
            // Never repaint over an analysis that is mid-flight (that would restore the
            // Run gate and make the merchant think their click was ignored).
            if ($('view-customers').classList.contains('active') && !customersRuns.has(customersSeg || SEG_ALL)) renderCustomers(customersSeg);
        }
        function sectorBar() {
            /* A picker with one choice is not a choice: with no sector tags it
               drew a lone 'Comprehensive' segment above the page title. */
            if (!(customerTags || []).length) return document.createDocumentFragment();
            /* A tick, said in words on hover, for a sector already run: it
               was a green dot whose only explanation was 'Loaded'. */
            const tick = () => { const d = el('span', 'cdot'); d.innerHTML = I.check; d.title = 'Already run: opens without a new run'; d.setAttribute('aria-label', 'already run'); return d; };
            return segmented(segOptions().map(o => ({ key: o.value, label: o.label, extra: customersCache[o.value] ? tick() : null })),
                             customersSeg, pickSector, { label: 'Customer sector' });
        }
        function pickSector(seg) { customersSeg = seg; renderCustomers(seg); }
        /* The Customers run gate: the page's header and line, then the empty
           state every run gate is (renderRunGate), with the sector bar between. */
        function customerGateHead(seg) {
            const comp = seg === SEG_ALL;
            const title = comp ? 'Customers' : (seg + ' sector');
            return pageHead({ view: 'customers', title: title, line: comp
                ? 'Customers and sectors by retention, value and revenue.'
                : ('The ' + seg + ' sector on its own, with a ranked plan.'),
                info: infoButton('About this run', { title: title, body: 'Reads Shopify customers and orders.' }) });
        }
        function customerGate(seg) {
            const comp = seg === SEG_ALL;
            const btn = el('button', 'btn btn-primary'); btn.type = 'button';
            btn.textContent = comp ? 'Run comprehensive audit' : ('Run ' + seg + ' audit'); btn.onclick = () => loadCustomers(true, seg);
            return emptyState({ icon: I.users, text: RUN_COST, sub: 'Your customers and 12 months of orders.', action: btn, cls: 'run-gate' });
        }
        function sectorComparisonTable(rows, cur) {
            const wrap = el('div', 'ktable-wrap'); const tbl = el('table', 'ktable');
            const thead = el('thead'); const htr = el('tr');
            ['Sector', 'Customers', 'Repeat rate', 'Average lifetime value', 'Lifetime revenue'].forEach((h, i) => htr.append(el('th', i ? 'num' : null, h)));
            thead.append(htr); tbl.append(thead); const tb = el('tbody');
            rows.forEach(r => {
                const tr = el('tr'); const c0 = el('td', 'kw');
                const sl = textLink(r.sector || '', { size: 'inline' }); sl.onclick = () => pickSector(r.sector);
                c0.append(sl); tr.append(c0);
                tr.append(el('td', 'num', (r.customers || 0).toLocaleString()));
                tr.append(el('td', 'num', (r.repeat_rate != null ? pct1(r.repeat_rate) : '')));
                tr.append(el('td', 'num', fmtMoney(r.avg_ltv || 0, cur)));
                tr.append(el('td', 'num', fmtMoney(r.lifetime_revenue || 0, cur)));
                tb.append(tr);
            });
            tbl.append(tb); wrap.append(tbl); return wrap;
        }
        function showCustomersView() {
            loadCustomerTags();
            loadRadar();
            renderCustomers(customersSeg);
        }
        /* Trade radar: overdue repeat accounts + untagged likely-B2B customers.
           A plain Shopify read (no AI), so it loads itself on tab open. */
        let radarCache = null;   // { data, at } | 'busy' | null
        async function loadRadar() {
            if (radarCache === 'busy') return;
            if (radarCache) { paintRadar(); return; }
            radarCache = 'busy';
            try {
                const data = await api('/api/reorder-radar', {});
                radarCache = { data, at: Date.now() };
            } catch (e) { radarCache = null; return; }
            paintRadar();
        }
        function paintRadar() {
            const slot = $('trade-radar-slot');
            if (!slot || !radarCache || radarCache === 'busy') return;
            slot.innerHTML = '';
            slot.append(radarCard(radarCache.data));
        }
        function radarCard(d) {
            /* Built from the house card parts: a titled head, a quiet label
               for each of the two lists, and tables that meet the card's edges
               like Top customers on the same page. It used to borrow the size
               check's head, so the title was smaller than its own sub-headings,
               its description sat a thousand pixels away at the far edge, and
               the page-level heading margins opened 40px holes around one-line
               sentences. No margin of its own: its slot spaces it. */
            const cur = d.currency || 'GBP';
            const card = el('div', 'card');
            const head = el('div', 'card-head');
            head.append(el('h3', 'card-title', 'Trade radar'));
            /* The cost note is kept (a cost is never dropped): the one fact of the old line that is not in the title. */
            head.append(el('p', 'card-desc', 'No AI credits used.'));
            card.append(head);
            const table = (cols, rows) => {
                const bleed = el('div', 'card-bleed');
                const wrap = el('div', 'ktable-wrap'); const tb = el('table', 'ktable');
                const thead = el('thead'); const htr = el('tr');
                cols.forEach(([h, num]) => htr.append(el('th', num ? 'num' : null, h)));
                thead.append(htr); tb.append(thead);
                const tbody = el('tbody'); rows.forEach(tr => tbody.append(tr)); tb.append(tbody);
                wrap.append(tb); bleed.append(wrap); return bleed;
            };
            const days = (n) => n + (n === 1 ? ' day' : ' days');
            const od = d.overdue || [];
            /* The two lists side by side (12 Oct 2026), each with its long text
               under the name, so each fits half the width. */
            const cols = el('div', 'radar-cols'); card.append(cols);
            const colA = el('div', 'radar-col'), colB = el('div', 'radar-col'); cols.append(colA, colB);
            colA.append(el('div', 'radar-h', 'Overdue repeat accounts (' + od.length + ')'));
            if (!od.length) {
                colA.append(el('p', 'card-sub', 'No repeat accounts overdue.'));
            } else {
                colA.append(table([['Account and last bought'], ['Orders', 1], ['Usually every', 1], ['Last order'], ['Overdue by', 1], ['']],
                    od.map(r => {
                        const tr = el('tr');
                        const nm = el('td', 'kw', r.name);
                        if ((r.last_items || []).length) nm.append(el('div', 'prod-sub', (r.last_items || []).join(', ')));
                        tr.append(nm);
                        tr.append(el('td', 'num', String(r.orders)));
                        tr.append(el('td', 'num', days(r.median_days)));
                        const lo = el('td', null, r.last_order || '');
                        if (r.last_at) lo.append(el('div', 'prod-sub', fmtDate(r.last_at)));
                        tr.append(lo);
                        tr.append(el('td', 'num', days(r.overdue_by)));
                        const tdm = el('td');
                        if (r.email) {
                            const a = el('a', 'miss-open', 'Email');
                            a.href = 'mailto:' + encodeURIComponent(r.email)
                                + '?subject=' + encodeURIComponent('Ready for your next gobos?');
                            tdm.append(a);
                        }
                        tr.append(tdm);
                        return tr;
                    })));
            }
            const bb = d.untagged_b2b || [];
            colB.append(el('div', 'radar-h', 'Untagged likely-trade customers (' + bb.length + ')'));
            if (!bb.length) {
                colB.append(el('p', 'card-sub', 'Every trade customer is tagged.'));
            } else {
                colB.append(table([['Customer and why flagged'], ['Orders', 1], ['Lifetime spend', 1]],
                    bb.map(r => {
                        const tr = el('tr');
                        const nm = el('td', 'kw', r.name);
                        if (r.reason) nm.append(el('div', 'prod-sub', r.reason));
                        tr.append(nm);
                        tr.append(el('td', 'num', String(r.orders)));
                        tr.append(el('td', 'num', fmtMoney(r.spent || 0, cur)));
                        return tr;
                    })));
                colB.append(el('p', 'card-sub', 'Tag these in Shopify to count them as trade.'));
            }
            return card;
        }
        /* The sectors being analysed now, each one paid run. One slot for the
           whole tab let a second sector's run take it, and coming back to the
           first then offered Run over the run still going: paid twice. */
        const customersRuns = new Set();
        function customersBusy(seg) {
            const comp = seg === SEG_ALL;
            const box = $('customers-content'); box.innerHTML = '';
            const hero = pageHead({ view: 'customers', title: comp ? 'Customers' : (seg + ' sector') }); box.append(hero);
            const ht = hero;
            const t = el('div', 'thinking'); t.append(loader(), el('span', null, 'Analysing ' + (comp ? 'your customers and sectors' : ('the ' + seg + ' sector'))
                + ' from 12 months of orders. This can take up to a minute.')); box.append(t);
            return { box, hero, ht };
        }
        async function loadCustomers(force, seg) {
            seg = (typeof seg === 'string' && seg) ? seg : (customersSeg || SEG_ALL);
            customersSeg = seg;
            if (customersRuns.has(seg)) { customersBusy(seg); return; }   // already running: don't start a second paid run
            if (customersCache[seg] && !force) { renderCustomers(seg); return; }
            const comp = seg === SEG_ALL;
            const { box, hero, ht } = customersBusy(seg);
            customersRuns.add(seg);
            try {
                const data = await api('/api/customers', { segment: comp ? '' : seg, fresh: !!force });
                customersCache[seg] = { data, at: Date.now() };
                customersRuns.delete(seg);
                // Only paint if the merchant is still looking at this sector: they may
                // have switched tabs during the run, and clobbering their view looks
                // like the click did nothing (which invites a second paid run).
                if (customersSeg === seg) renderCustomers(seg);
            } catch (e) {
                if (customersSeg !== seg) return;
                customersRuns.delete(seg);
                reportFailed(box, hero, 'The analysis could not be run. ' + (e.message || String(e)),
                    customersCache[seg] ? () => renderCustomers(seg) : null, () => loadCustomers(true, seg));
            } finally {
                customersRuns.delete(seg);
            }
        }
        /* The segments as a table (12 Oct 2026): how many, the segment and what
           it means, and what it is worth, beside the sector comparison. */
        function segTable(segments, cur) {
            const wrap = el('div', 'ktable-wrap'); const tbl = el('table', 'ktable');
            const thead = el('thead'); const htr = el('tr');
            [['Customers', 'num'], ['Segment', 'kt-main'], ['Lifetime revenue', 'num']].forEach(([h, c]) => htr.append(el('th', c, h)));
            thead.append(htr); tbl.append(thead); const tb = el('tbody');
            (segments || []).forEach(s => {
                const tr = el('tr');
                tr.append(el('td', 'num', (s.count || 0).toLocaleString()));
                const nm = el('td', 'kw', s.name || '');
                if (s.desc) nm.append(el('div', 'prod-sub', s.desc));
                tr.append(nm);
                tr.append(el('td', 'num', fmtMoney(s.revenue || 0, cur)));
                tb.append(tr);
            });
            tbl.append(tb); wrap.append(tbl); return wrap;
        }
        /* Top customers as two tables of ten side by side (12 Oct 2026): one
           column of 25 ran the page's length with the row half empty. */
        function customersTable(rows, cur) {
            const duo = el('div', 'duo');
            duo.append(customersHalf(rows.slice(0, 10), cur));
            if (rows.length > 10) duo.append(customersHalf(rows.slice(10, 20), cur));
            return duo;
        }
        function customersHalf(rows, cur) {
            const wrap = el('div', 'ktable-wrap'); const tbl = el('table', 'ktable');
            const thead = el('thead'); const htr = el('tr');
            ['Customer', 'Orders', 'Lifetime spend', 'Last order'].forEach((h, i) => htr.append(el('th', i ? 'num' : null, h)));
            thead.append(htr); tbl.append(thead); const tb = el('tbody');
            rows.forEach(r => {
                const tr = el('tr'); const c0 = el('td', 'kw'); c0.append(document.createTextNode(r.name || 'Customer'));
                if (r.email) c0.append(el('div', 'prod-sub', r.email));
                tr.append(c0);
                tr.append(el('td', 'num', (r.orders || 0).toLocaleString()));
                tr.append(el('td', 'num', fmtMoney(r.spent || 0, cur)));
                tr.append(el('td', 'num', r.days_since == null ? 'over 1y' : (r.days_since + 'd ago')));
                tb.append(tr);
            });
            tbl.append(tb); wrap.append(tbl); return wrap;
        }
        function renderCustomers(seg) {
            seg = (typeof seg === 'string' && seg) ? seg : (customersSeg || SEG_ALL);
            customersSeg = seg;
            if (customersRuns.has(seg)) { customersBusy(seg); return; }   // its run is still going: keep the loading screen
            const box = $('customers-content'); box.innerHTML = '';
            /* Empty until /api/reorder-radar answers, and for good if it fails:
               the layer leaves an empty card out of the arrangement and lays
               the page out again when paintRadar fills it. */
            const rslot = widget(el('div'), 'trade-radar', 'full', 'Trade radar'); rslot.id = 'trade-radar-slot';
            const cached = customersCache[seg];
            /* The Run gate before the radar, so its button is above the fold
               like every other report's; the radar follows it. */
            if (!cached) { box.append(customerGateHead(seg), sectorBar(), customerGate(seg), rslot); paintRadar(); return; }
            const data = cached.data; const s = data.structured || {}; const cur = data.currency || '';
            const comp = seg === SEG_ALL;
            const hero = pageHead({ view: 'customers', title: comp ? 'Customers' : (seg + ' sector'), live: cached.at,
                onRefresh: () => loadCustomers(true), actions: [refreshAllBtn()] });
            /* The header, the sector bar and the changes strip stay fixed at
               the top and the page chat at the foot; from the trade radar to
               Details every block is a card the grid can move, each spanning
               the row. The changes strip used to follow the radar, which would
               leave a fixed block between two cards, so it now comes first. */
            box.append(hero, sectorBar());
            summaryAndChanges(box, data.changes, data.changes_since, s.summary, followedNote(s));
            /* The figures beside the new-customers chart, then the radar, then
               the pairs (12 Oct 2026, R6). */
            const kpisW = Array.isArray(data.metrics) && data.metrics.length ? widget(metricsStrip(data.metrics), 'kpis', 'full', 'Customer figures') : null;
            if (kpisW) box.append(kpisW);
            let ncGroup = null;
            if (data.trends && data.trends.new_customers && data.trends.new_customers.length) {
                const nc = data.trends.new_customers;
                /* The chart is its own titled card in a group, so it can sit
                   beside the figures as one half of a pair (12 Oct 2026). */
                ncGroup = widget(el('div', 'widget-group'), 'new-customers', 'full', 'New customers by month');
                box.append(ncGroup);
                /* The chart names its window, as every other chart does; the KPI
                   beside it counts thirty days and this counts the months drawn. */
                /* Compact beside the figures (12 Oct 2026): at full height it left a hole under them. */
                ncGroup.append(barChart({ title: 'New customers by month', source: 'Shopify customers', height: 120, period: rangeLabel(nc.length), yUnit: 'Customers', value: fmtCompact(sumv(nc)), labels: nc.map(x => monthLabel(x.label)), values: nc.map(x => +x.value || 0), format: fmtCompact }));
                cardifySections(ncGroup);
            }
            pairNodes(kpisW, ncGroup, 'kpis', 'Customer figures and new customers');
            box.append(rslot); paintRadar();
            if (comp && Array.isArray(data.sector_comparison) && data.sector_comparison.length) {
                box.append(widget(el('div', 'section-title', 'Sector comparison'), 'sectors'));
                box.append(sectorComparisonTable(data.sector_comparison, cur));
            }
            if (Array.isArray(data.segments) && data.segments.length) {
                box.append(widget(el('div', 'section-title', 'Customer segments'), 'segments'));
                box.append(segTable(data.segments, cur));
            }
            if (Array.isArray(s.actions) && s.actions.length) { box.append(widget(el('div', 'section-title', 'Retention opportunities'), 'opportunities')); box.append(actionsCard(s.actions, 'customers')); }
            if (Array.isArray(s.insights) && s.insights.length) { box.append(widget(el('div', 'section-title', 'Findings'), 'findings')); const b = el('div', 'insights'); s.insights.forEach((x, i) => b.append(insightCard(x, i))); box.append(b); }
            if (Array.isArray(data.top_customers) && data.top_customers.length) {
                box.append(widget(el('div', 'section-title', 'Top customers by lifetime spend'), 'top-customers'));
                box.append(customersTable(data.top_customers, cur));
            }
            if (Array.isArray(s.sections) && s.sections.length) { box.append(widget(el('div', 'section-title', 'Details'), 'details')); s.sections.forEach(sec => box.append(sectionCard(sec))); }
            const chat = pageChatPanel('customers', data);
            box.append(chat);
            cardifySections(box);
            pairNodes(wgChild(box, 'opportunities'), wgChild(box, 'findings'), 'opportunities', 'Retention opportunities and findings');
            pairNodes(wgChild(box, 'sectors'), wgChild(box, 'segments'), 'sectors', 'Sector comparison and segments', { even: true });
            pairNodes(wgChild(box, 'details'), chat, 'details', 'Details and questions');
            syncPrintBtn();
        }

