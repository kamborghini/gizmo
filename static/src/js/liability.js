        /* ---------- liability / accounts receivable ---------- */
        let liabilityCache = null;   // { data, at }
        let liaOpen = null;          // expanded customer key
        const liaF = { q: '', status: 'all', terms: 'all', channel: 'all', from: '', to: '', dateField: 'created_at', min: '', sort: 'overdue' };
        /* Was a three-entry symbol map and a hardcoded en-GB grouping. Now the
           same shared formatter as everywhere else, so a non-GBP order reads
           the way that currency is actually written. */
        function liaMoney(n, cur, dp) { return money(n, cur, dp === 0 ? 0 : 2); }
        /* Days in words, everywhere on the tab: it wrote '44D', '3d', '74d'
           and '74 days' for the one unit. */
        const liaDays = (n) => n + (n === 1 ? ' day' : ' days');
        function showLiabilityView() {
            if (liabilityCache) { renderLiability(); return; }
            loadLiability(true);
        }
        // As in Production Manager: force skips the copy held in this page,
        // fresh also makes the server re-read Shopify. Opening the tab does the
        // first, Refresh does both, so a plain look does not throw away every
        // order the server has already read.
        async function loadLiability(force, fresh) {
            const box = $('liability-content');
            if (liabilityCache && !force) { renderLiability(); return; }
            box.innerHTML = '';
            /* The same heading and tabs the loaded page has, so the page does
               not change its name and grow a tab strip when the data lands, as
               Reconciliation and Forecast already do. */
            const hero = pageHead({ view: 'liability', title: 'Liability', line: 'What customers owe on unpaid orders.' });
            box.append(hero);
            box.append(financeTabs('liability', ''));
            const t = el('div', 'thinking');
            t.append(loader(), el('span', null, 'Reading up to two years of unpaid orders. No AI credits used.'));
            box.append(t);
            try {
                const data = await api('/api/liability', { fresh: !!fresh });
                liabilityCache = { data, at: Date.now() };
                renderLiability();
            } catch (e) {
                /* A failed refresh keeps the last good book on screen and says
                   so; with nothing to show, it offers Try again. */
                if (liabilityCache) { renderLiability(); toastError('The liability view could not be refreshed. ' + (e.message || '')); return; }
                t.remove();
                box.append(loadFailure('The liability view could not be read. ' + (e.message || String(e)), () => loadLiability(true)));
            }
        }
        function liaChip(r) {
            if (r.status === 'overdue') {
                const c = el('span', 'lbl-chip bad' + (r.bucket === '60+' || r.bucket === '31-60' ? ' deep' : ''),
                    liaDays(r.days_over) + ' overdue');
                c.title = 'Due ' + fmtDate(r.due);
                return c;
            }
            if (r.status === 'due_soon') return el('span', 'lbl-chip warn', 'Due in ' + liaDays(r.days_to_due));
            return el('span', 'lbl-chip made', 'Within terms');
        }
        function liaOrderPasses(r) {
            if (liaF.status !== 'all') {
                if (liaF.status === 'overdue' && r.status !== 'overdue') return false;
                if (liaF.status === 'within' && r.status !== 'within') return false;
                if (liaF.status === 'due_soon' && r.status !== 'due_soon') return false;
                if (['1-7', '8-30', '31-60', '60+'].indexOf(liaF.status) >= 0 && r.bucket !== liaF.status) return false;
            }
            if (liaF.terms !== 'all') {
                if (liaF.terms === 'assumed' && r.terms_source !== 'assumed') return false;
                if (liaF.terms !== 'assumed' && r.terms !== liaF.terms) return false;
            }
            if (liaF.channel !== 'all' && (r.channels || [r.channel]).indexOf(liaF.channel) < 0) return false;
            if (liaF.min && !(r.outstanding >= parseFloat(liaF.min))) return false;
            const dv = liaF.dateField === 'due' ? r.due : r.created_at;
            if (liaF.from && dv && dv < liaF.from) return false;
            if (liaF.to && dv && dv > liaF.to) return false;
            if (liaF.q) {
                const q = liaF.q.toLowerCase();
                if (r.customer.toLowerCase().indexOf(q) < 0 && r.name.toLowerCase().indexOf(q) < 0) return false;
            }
            return true;
        }
        /* The strip that makes Liability and Reconciliation one area rather
           than two destinations, built exactly like the reference's Finance
           tabs: a segmented control on the left, a muted "updated" line and
           any actions on the right. Reconciliation is only offered to an
           account that may open it, so the tab cannot become a door round the
           permission. */
        function financeTabs(active, updated, actions) {
            const row = el('div', 'page-tabs');
            /* The reference's page strip: ink alone marks where you are. The
               filled pill this used to wear read as a control you press rather
               than a place you are. */
            /* Beta marks the tab that is in beta, as the sidebar marks it,
               not the page heading above: when all four pages shared the
               heading 'Finance' it gained and lost the tag as you moved
               between them, and the tab is where the reader compares. */
            /* No Beta on the tabs: the sidebar and the top-bar title say it, and
               a Finance screen carried it seven times at once. */
            const tab = (key, label) => ({ key, label });
            const seg = tabStrip([tab('liability', 'Liability'), tabAllowed('recon') && tab('recon', 'Reconciliation'),
                                  tabAllowed('forecast') && tab('forecast', 'Forecast'), tabAllowed('connector') && tab('connector', 'Xero sync')],
                                 active, (k) => setView(k), { nav: true, label: 'Finance pages' });
            row.append(seg);
            /* The stamp and the page's buttons on the right of the strip, as
               the reference's Finance page puts "Updated 5 min ago" and its
               Settings and Export there: one group, so they wrap together and
               stay at the right. Apart, Upload wrapped alone to the far left
               while its stamp stayed at the right. */
            const end = el('div', 'page-tabs-end');
            if (updated) end.append(el('div', 'updated', updated));
            (actions || []).filter(Boolean).forEach(b => end.append(b));
            if (end.childNodes.length) row.append(end);
            return row;
        }
        /* ONE summary card for both finance pages, and it is the app's own
           .stat - the card Overview and SEO already draw. The two pages used
           to introduce themselves with two different metric systems a single
           tab click apart, and Reconciliation's half was built from .stat-l
           and .stat-v, two class names that were never styled at all.
           Not statCard(): its label-to-help matcher reads "Overdue orders" as
           the Overview's order count and hangs the wrong sentence on it. */
        /* A counter: a figure that filters the list under it (see .fc). o.dot is
           its severity colour (bad, warn, ok, or none for grey), o.money what it
           is worth, o.on whether it is the filter that is set. */
        function counterTile(label, value, o) {
            o = o || {};
            const b = el('button', 'fc' + (o.on ? ' on' : ''));
            b.type = 'button';
            b.setAttribute('aria-pressed', o.on ? 'true' : 'false');
            const l = el('span', 'fc-l');
            l.append(el('span', 'fc-dot' + (o.dot ? ' ' + o.dot : '')), document.createTextNode(label));
            const v = el('span', 'fc-v');
            v.append(el('b', '', value));
            if (o.money) v.append(el('span', '', o.money));
            b.append(l, v);
            if (o.onClick) b.onclick = o.onClick;
            return b;
        }
        function financeStat(label, value, tone, unknown, note) {
            const c = el('div', 'stat' + (tone ? ' ' + tone : ''));
            c.append(el('div', 'label', label));
            const row = el('div', 'stat-row');
            row.append(el('div', 'value' + (unknown ? ' unknown' : ''), value));
            c.append(row);
            if (note) c.append(el('p', 'stat-note', note));
            return c;
        }
        function renderLiability() {
            const box = $('liability-content'); box.innerHTML = '';
            /* Set BEFORE anything is appended, so a filter click, a row expand
               or a Refresh redraws in place rather than fading six tiles the
               reader is already reading back in from nothing. The tiles are
               server totals that a filter does not change, so the band flashed
               while saying exactly the same thing. */
            box.classList.toggle('no-intro', !firstPaint('liability'));
            const d = liabilityCache.data;
            const cur = d.currency;
            /* Each page is called what the sidebar and the topbar call it. The
               one line says what the page is; which tags count and how terms are
               worked out wait behind the title's info button, word for word
               (copy plan, Liability #1). The stamp and Refresh live on the tabs. */
            /* Refresh is worded in the header, as on Xero sync; the stamp stays on
               the tab row (12 Oct 2026). */
            const liaRefresh = el('button', 'btn btn-sm'); liaRefresh.type = 'button';
            liaRefresh.append(ico(I.refresh), document.createTextNode('Refresh'));
            liaRefresh.onclick = () => loadLiability(true, true);
            box.append(pageHead({ view: 'liability', title: 'Liability', line: 'What customers owe on unpaid orders.', actions: [liaRefresh],
                info: infoButton('About Liability', { title: 'Liability', body: 'Credit extended to customers, from orders tagged '
                    + (d.tags || []).map(t => '"' + t + '"').join(', ')
                    + '. Terms come from the order itself, then a Net tag on the customer, otherwise Net '
                    + d.default_terms + ' is assumed and marked.' }) }));
            box.append(financeTabs('liability', freshLabel(liabilityCache.at), []));
            /* Nothing owed is one line, not six £0 tiles over a card that says
               so (12 Oct 2026, DF-20). */
            /* Paid but still tagged is made first: the day nothing is owed is the
               likeliest day every tagged order is paid and still tagged, and
               the empty line below must not drop it (final review I-3). */
            const staleW = (d.stale_tagged || []).length ? (() => {
                const s = el('div', 'miss-strip inline');
                const head = el('div', 'miss-head');
                const nst = d.stale_tagged.length;
                head.append(ico(I.warning), el('b', null, 'Paid but still tagged'),
                    el('span', 'miss-sub', nst + (nst === 1 ? ' settled order still carries' : ' settled orders still carry')
                        + ' an unpaid tag and ' + (nst === 1 ? 'is' : 'are') + ' left out of the totals. Untag '
                        + (nst === 1 ? 'it' : 'them') + ' in Shopify.'));
                s.append(head);
                d.stale_tagged.forEach(m => {
                    const row = el('div', 'miss-row');
                    row.append(orderA(m.name, m.admin_url, 'miss-open'));
                    s.append(row);
                });
                return widget(s, 'stale-tags', 'full', 'Paid but still tagged');
            })() : null;
            /* A total the server did not send is not a zero: then the line says
               only that nothing is listed. The tab row says when it was read. */
            if (!(d.customers || []).length && !(d.total > 0)) {
                box.append(emptyState({ icon: I.wallet, text: typeof d.total === 'number' ? 'Nothing is owed.' : 'No unpaid orders are listed.' }));
                if (staleW) box.append(staleW);
                return;
            }
            /* Under the header and its tabs every block is a card the grid can
               move, each spanning the row. */

            // Summary cards.
            /* A figure the server did not send is not zero. liaMoney reads a
               missing number as 0, which on this page says the book is clear;
               the two count cards said "undefined" and "undefined days"
               instead. Neither is an answer, so both now say so. */
            const liaNum = (v, fmt) => (typeof v === 'number' && isFinite(v)) ? fmt(v) : 'not reported';
            /* And a figure that did not arrive does not get a tone either. The
               tone was picked from a hardcoded string or from `undefined > 0`,
               so "not reported" was painted green on three tiles - the page
               said the count of overdue orders was fine while the tile beside
               it said £12,430 was overdue. */
            const liaKnown = (v) => typeof v === 'number' && isFinite(v);
            /* Every tile that names a status is also the filter for that
               status, exactly as the Reconciliation severity tiles are. The two
               tabs draw the SAME card, so it cannot be a control on one and
               inert on the other with no difference at rest. Total outstanding
               and Oldest debt name no status, so they stay plain. */
            /* 'Overdue orders' is the same filter as 'Overdue', so it is a plain
               tile: one click ticked both. */
            const LIA_PICK = { 'Within terms': 'within', 'Due soon': 'due_soon', 'Overdue': 'overdue' };
            /* Within terms is the bucket the legend and the tile's own filter
               show. The server's d.within also counts what is due soon, so the
               tile said 2,119 while the legend under it and the filtered list
               both said 1,200. */
            const within = (d.buckets && typeof d.buckets.within === 'number') ? d.buckets.within : d.within;
            /* Colour is a judgement, so only a figure that is one gets it: due
               soon and overdue when there is some. 'Due soon £0' was amber
               while 'Overdue £0' was green. */
            const grid = el('div', 'metrics metrics-flat metrics-3 metrics-strip');
            /* The three buckets that filter the list are one group of counters,
               in their place in the row (12 Oct 2026). */
            const LIA_DOT = { within: 'ok', due_soon: 'warn', overdue: 'bad' };
            let liaCounters = null;
            [['Total outstanding', d.total, liaNum(d.total, v => liaMoney(v, cur, 0)), ''],
             ['Within terms', within, liaNum(within, v => liaMoney(v, cur, 0)), ''],
             ['Due soon', d.due_soon, liaNum(d.due_soon, v => liaMoney(v, cur, 0)), d.due_soon > 0 ? 'warn' : ''],
             ['Overdue', d.overdue, liaNum(d.overdue, v => liaMoney(v, cur, 0)), d.overdue > 0 ? 'bad' : ''],
             ['Overdue orders', d.overdue_orders, liaNum(d.overdue_orders, v => String(v)), d.overdue_orders > 0 ? 'bad' : ''],
             ['Oldest debt', d.oldest_days, liaNum(d.oldest_days, v => v ? liaDays(v) : 'None'), '']].forEach(([k, raw, v, tone]) => {
                const known = liaKnown(raw);
                const pick = LIA_PICK[k];
                if (pick) {
                    if (!liaCounters) { liaCounters = el('div', 'fcs fcs-money'); grid.append(liaCounters); }
                    liaCounters.append(counterTile(k, v, { dot: known && raw > 0 ? LIA_DOT[pick] : '', on: liaF.status === pick,
                        onClick: () => { liaF.status = liaF.status === pick ? 'all' : pick; renderLiability(); } }));
                    return;
                }
                grid.append(financeStat(k, v, known ? tone : '', !known));
            });
            box.append(widget(grid, 'summary', 'full', 'Summary'));

            // Aged-debt bar: one glance says whether the book is healthy.
            if (d.total > 0) {
                const seq = [['within', 'Within terms', d.buckets['within']],
                             ['soon', 'Due soon', d.buckets['due_soon']],
                             ['o1', '1 to 7 days over', d.buckets['1-7']],
                             ['o2', '8 to 30 days over', d.buckets['8-30']],
                             ['o3', '31 to 60 days over', d.buckets['31-60']],
                             ['o4', 'Over 60 days', d.buckets['60+']]];
                const bar = el('div', 'lia-bar');
                const leg = el('div', 'lia-legend');
                seq.forEach(([cls, lab, amt]) => {
                    if (amt <= 0) return;
                    const seg = el('div', 'lia-seg ' + cls);
                    seg.style.width = (amt / d.total * 100) + '%';
                    seg.title = lab + ': ' + liaMoney(amt, cur, 0);
                    bar.append(seg);
                    const li = el('span', 'lia-leg-item');
                    li.append(el('span', 'lia-dot ' + cls), document.createTextNode(lab + ' ' + liaMoney(amt, cur, 0)));
                    leg.append(li);
                });
                /* In a card with a title, like every other block the reference
                   puts on a finance page. Bare on the background it read as a
                   loading state rather than the answer to "is the book sound". */
                const bcard = el('div', 'card');
                const bhead = el('div', 'card-head');
                bhead.append(el('h3', 'card-title', 'Aged debt'));
                bcard.append(bhead, bar, leg);
                box.append(widget(bcard, 'aged-debt'));
            }

            if (staleW) box.append(staleW);

            /* The filters, sorted the way the reference sorts them: the search
               and the few that get changed daily on the bar, the date range and
               the minimum behind a panel. It was eleven controls in one row,
               which nobody reads as eleven separate questions. */
            const STATUS_OPTS = [['all', 'All statuses'], ['within', 'Within terms'],
                ['due_soon', 'Due soon'], ['overdue', 'All overdue'], ['1-7', '1 to 7 days overdue'],
                ['8-30', '8 to 30 days overdue'], ['31-60', '31 to 60 days overdue'], ['60+', 'Over 60 days overdue']];
            const SORT_OPTS = [['overdue', 'Most overdue'], ['total', 'Total owed'],
                ['oldest', 'Oldest debt'], ['name', 'Name']];
            const tset = {};
            d.customers.forEach(c => c.orders.forEach(r => { tset[r.terms] = 1; }));
            if (liaF.terms !== 'all' && liaF.terms !== 'assumed' && !tset[liaF.terms]) liaF.terms = 'all';
            const TERM_OPTS = [['all', 'All terms']]
                .concat(Object.keys(tset).sort().map(t2 => [t2, t2]))
                .concat([['assumed', 'Assumed terms only']]);
            const chans = Object.keys(d.channels || {}).sort();
            // A stale selection whose option no longer exists would filter invisibly.
            if (liaF.channel !== 'all' && chans.indexOf(liaF.channel) < 0) liaF.channel = 'all';
            const CHAN_OPTS = [['all', 'All channels']].concat(chans.map(c2 => [c2, c2]));

            const qWrap = tableSearch('Search customer or order…', liaF.q, (v) => { liaF.q = v; paint(); });
            const left = [qWrap,
                filterChip('Status', STATUS_OPTS, liaF.status, (v) => { liaF.status = v; renderLiability(); }),
                filterChip('Terms', TERM_OPTS, liaF.terms, (v) => { liaF.terms = v; renderLiability(); })];
            if (chans.length > 1) left.push(filterChip('Channel', CHAN_OPTS, liaF.channel,
                (v) => { liaF.channel = v; renderLiability(); }));

            const rangeSet = !!(liaF.from || liaF.to || liaF.min);
            const rangeBtn = el('button', 'btn btn-sm' + (rangeSet ? ' on' : ''));
            rangeBtn.append(ico(I.cal), document.createTextNode(rangeSet ? 'Dates and amount: set' : 'Dates and amount'));
            rangeBtn.onclick = () => dropPanel(rangeBtn, (body, close) => {
                const fieldRow = el('label', 'dpanel-row');
                fieldRow.append(el('span', null, 'Filter by'));
                const dfield = document.createElement('select');
                [['created_at', 'Ordered'], ['due', 'Due']].forEach(([v2, l2]) => {
                    const o2 = el('option', null, l2); o2.value = v2;
                    if (liaF.dateField === v2) o2.selected = true; dfield.append(o2);
                });
                dfield.onchange = () => { liaF.dateField = dfield.value; paint(); };
                fieldRow.append(dfield);
                const fromRow = el('label', 'dpanel-row');
                fromRow.append(el('span', null, 'On or after'));
                const df = document.createElement('input'); df.type = 'date'; df.value = liaF.from || '';
                df.onchange = () => { liaF.from = df.value; paint(); };
                fromRow.append(df);
                const toRow = el('label', 'dpanel-row');
                toRow.append(el('span', null, 'On or before'));
                const dt2 = document.createElement('input'); dt2.type = 'date'; dt2.value = liaF.to || '';
                dt2.onchange = () => { liaF.to = dt2.value; paint(); };
                toRow.append(dt2);
                const minRow = el('label', 'dpanel-row');
                minRow.append(el('span', null, 'Owing at least'));
                const minIn = document.createElement('input');
                minIn.type = 'number'; minIn.min = '0'; minIn.step = '50'; minIn.style.width = 'var(--field-w-sm)';
                minIn.value = liaF.min;
                minIn.oninput = () => { liaF.min = minIn.value; paint(); };
                minRow.append(minIn);
                const done = el('button', 'btn btn-sm', 'Done');
                done.onclick = () => { close(); renderLiability(); };
                body.append(fieldRow, fromRow, toRow, minRow, done);
            });
            /* Built once and hidden, not built conditionally: the search box
               repaints only the rows, so a search-only filter used to leave no
               way to clear it on the bar at all. paint() shows it from the same
               expression the coverage line is written from, so the chip and the
               line can never disagree. */
            const clr = el('button', 'btn btn-sm');
            clr.append(ico(I.x), document.createTextNode('Clear'));
            clr.title = 'Reset every filter';
            clr.onclick = () => {
                Object.assign(liaF, { q: '', status: 'all', terms: 'all', channel: 'all',
                                      from: '', to: '', min: '' });
                renderLiability();
            };
            const right = [filterChip('Sort', SORT_OPTS, liaF.sort, (v) => { liaF.sort = v; renderLiability(); }),
                           rangeBtn, clr];
            /* The ledger in a card, the way the reference builds a list page. */
            const lCard = el('div', 'card');
            const lHead = el('div', 'card-head');
            /* Filled inside paint(), from the filtered set. Built once from the
               whole cache it read "12 customers owing" over ten rows, and over
               none at all when a search matched nothing. */
            const hTitle = el('h3', 'card-title', '');
            lHead.append(hTitle);
            box.append(widget(lCard, 'owing', 'full', 'Customers owing'));
            /* With nobody owing, a search box, four filters and a line about
               opening rows sat over a list that could never have a row. The
               card says the one true thing instead. */
            if (!(d.customers || []).length) {
                hTitle.textContent = 'Customers owing';
                lCard.append(lHead, el('div', 'empty', 'Nothing is owed.'));
                return;
            }
            lCard.append(lHead);
            lCard.append(tableTools(left, right));
            const host = el('div', 'card-bleed'); lCard.append(host);
            function paint() {
                host.innerHTML = '';
                let custs = d.customers
                    .map(c => ({ c, rows: c.orders.filter(liaOrderPasses) }))
                    .filter(x => x.rows.length);
                const sorters = {
                    overdue: (a, b) => b.c.overdue - a.c.overdue || b.c.total - a.c.total,
                    total: (a, b) => b.c.total - a.c.total,
                    oldest: (a, b) => b.c.oldest_days - a.c.oldest_days,
                    name: (a, b) => a.c.name.localeCompare(b.c.name),
                };
                custs.sort(sorters[liaF.sort] || sorters.overdue);
                hTitle.textContent = custs.length
                    + (custs.length === 1 ? ' customer owing' : ' customers owing');
                const active = liaF.q || liaF.status !== 'all' || liaF.terms !== 'all'
                    || liaF.channel !== 'all' || liaF.from || liaF.to || liaF.min;
                clr.style.display = active ? '' : 'none';
                if (active) {
                    const frows = custs.reduce((a2, x) => a2.concat(x.rows), []);
                    const fsum = frows.reduce((s2, r2) => s2 + r2.outstanding, 0);
                    host.append(el('div', 'cov-line', 'Filtered: ' + frows.length
                        + (frows.length === 1 ? ' order' : ' orders') + ' · ' + liaMoney(fsum, cur, 0)
                        + ' outstanding · ' + custs.length + (custs.length === 1 ? ' customer' : ' customers')));
                }
                /* Every customer owing in one table (12 Oct 2026, DF-18): Owed
                   straight after the name, every fact under its own head, and
                   an opened account under its own row. */
                const clearAll = el('button', 'btn btn-sm'); clearAll.type = 'button'; clearAll.textContent = 'Clear filters';
                clearAll.onclick = () => clr.click();
                const none = d.total > 0 ? emptyState({ icon: I.search, text: 'Nothing matches these filters.', action: clearAll })
                    : el('div', 'empty', 'Nothing is owed.');
                host.append(dtable([{ head: 'Customer' }, { head: 'Owed', cls: 'num', cap: true }, { head: 'Overdue', cls: 'num', cap: true }, { head: 'Status' },
                                    { head: 'Orders', cls: 'num', cap: true }, { head: 'Oldest', cls: 'num', cap: true }, { head: 'Terms' }, { head: 'Last chased', cap: 'Chased' },
                                    { head: '', cls: 'act go' }],
                    custs.map(({ c, rows }) => {
                        const key = c.name;
                        const toggle = () => { liaOpen = (liaOpen === key ? null : key); renderLiability(); };
                        /* Under a filter the row speaks for the orders the filter
                           kept, as its count already did. */
                        const part = rows.length < (c.orders || []).length;
                        const cOver = part ? rows.filter(r => r.status === 'overdue').reduce((a, r) => a + (r.outstanding || 0), 0) : c.overdue;
                        const cOld = part ? rows.reduce((a, r) => Math.max(a, r.age_days || 0), 0) : c.oldest_days;
                        const cTotal = part ? rows.reduce((a, r) => a + (r.outstanding || 0), 0) : c.total;
                        const nm = el('button', 'dt-link dt-name', c.name); nm.type = 'button'; nm.title = c.name;
                        nm.setAttribute('aria-expanded', String(liaOpen === key));
                        nm.onclick = (e) => { e.stopPropagation(); toggle(); };
                        const st = el('span', 'dt-name');
                        st.append(el('span', 'dt-dot ' + (cOver > 0 ? 'bad' : 'ok')), document.createTextNode(cOver > 0 ? 'Overdue' : 'Within terms'));
                        let chased = '';
                        if (c.last_chased && c.last_chased.at) {
                            const days = Math.max(0, Math.floor((Date.now() - Date.parse(c.last_chased.at)) / 86400000));
                            chased = days === 0 ? 'Today' : liaDays(days) + ' ago';
                        }
                        const go = el('span', 'prod-go'); go.innerHTML = liaOpen === key ? I.chevDown : I.chevLeft; go.setAttribute('aria-hidden', 'true');
                        return { open: liaOpen === key, onClick: toggle,
                                 cells: [nm, liaMoney(cTotal, cur), cOver > 0 ? el('span', 'dt-bad', liaMoney(cOver, cur)) : '', st,
                                         String(rows.length), liaDays(cOld), c.terms + (c.assumed ? ' (assumed)' : ''), chased, go],
                                 after: liaOpen === key ? liaDetail(c, rows) : null };
                    }),
                    { cls: 'dt-owing', label: 'Customers owing', empty: none }));
            }
            /* An opened account (12 Oct 2026, R9): its orders and the chase email
               side by side, the X beside its name. Two-line cells (value over
               paid, terms over channel) so both fit at a laptop's width. */
            function liaDetail(c, rows) {
                const det = el('div', 'lia-detail');
                const h = el('div', 'lia-detail-head');
                const tot = rows.reduce((a, r) => a + (r.outstanding || 0), 0);
                h.append(el('b', null, c.name), el('span', 'lbl-meta', rows.length + (rows.length === 1 ? ' order' : ' orders')
                    + ' \u00b7 ' + liaMoney(tot, cur) + ' outstanding'));
                const x = el('button', 'icon-btn'); x.type = 'button'; x.innerHTML = I.x;
                x.setAttribute('aria-label', 'Close ' + c.name);
                x.onclick = (e) => { e.stopPropagation(); liaOpen = null; renderLiability(); };
                h.append(x); det.append(h);
                const duo = el('div', 'duo');
                const wrap = el('div', 'ktable-wrap'); const tb = el('table', 'ktable');
                const thead = el('thead'); const htr = el('tr');
                [['Order'], ['Due'], ['Value and paid', 1], ['Outstanding', 1], ['Terms and channel'], ['Status']].forEach(([hd, num]) => htr.append(el('th', num ? 'num' : null, hd)));
                thead.append(htr); tb.append(thead);
                const tbody = el('tbody');
                rows.forEach(r => {
                    const tr = el('tr');
                    const onc = el('td', 'kw'); onc.append(orderA(r.name, r.admin_url), el('div', 'prod-sub', 'ordered ' + fmtDate(r.created_at)));
                    tr.append(onc);
                    tr.append(el('td', null, r.due ? fmtDate(r.due) : 'unknown'));
                    const val = el('td', 'num', liaMoney(r.value, cur)); val.append(el('div', 'prod-sub', liaMoney(r.paid, cur) + ' paid'));
                    tr.append(val);
                    tr.append(el('td', 'num strong', liaMoney(r.outstanding, cur)));
                    const tc = el('td', null, r.terms + (r.terms_source === 'assumed' ? ' (assumed)' : r.terms_source === 'customer' ? ' (tag)' : ''));
                    tc.append(el('div', 'prod-sub', (r.channels || [r.channel]).join(', ')));
                    tr.append(tc);
                    const tds = el('td'); tds.append(liaChip(r)); tr.append(tds);
                    tbody.append(tr);
                });
                tb.append(tbody); wrap.append(tb);
                duo.append(wrap, chasePanel(c, cur));
                det.append(duo);
                return det;
            }
            paint();

            /* The chase email, composed server-side from the same numbers the
               table shows. The merchant copies it into their own mail client
               and stays the sender: nothing here sends anything or writes to
               Shopify. Mark as chased is a local stamp so next week's session
               knows who was already asked. */
            function chasePanel(c, cur2) {
                const panel = el('div', 'lia-chase');
                const head = el('div', 'lia-chase-head');
                head.append(el('b', null, 'Chase email'));
                const tone = (c.chase && c.chase.tone) || 'statement';
                head.append(el('span', 'lbl-chip' + (tone === 'final' ? ' bad' : tone === 'firm' ? ' warn' : ''),
                    cap(tone)));
                head.append(el('span', 'sub', c.email ? 'Send to ' + c.email
                    : 'No email on file for this account. Find one before sending.'));
                panel.append(head);
                if (!c.chase) { panel.append(el('div', 'sub', 'Nothing to chase.')); return panel; }
                const subj = document.createElement('input');
                subj.type = 'text'; subj.className = 'disp-text'; subj.value = c.chase.subject;
                subj.title = 'Subject line';
                panel.append(subj);
                const ta = document.createElement('textarea');
                ta.className = 'lia-chase-body'; ta.value = c.chase.body; ta.rows = 12;
                ta.spellcheck = false;
                panel.append(ta);
                const bar = el('div', 'disp-actions');
                function copyBtn(label, field) {
                    const b = el('button', 'btn');
                    b.append(ico(I.copy), document.createTextNode(label));
                    b.onclick = async () => {
                        try {
                            await navigator.clipboard.writeText(field.value);
                            b.textContent = 'Copied'; setTimeout(() => { b.innerHTML = ''; b.append(ico(I.copy), document.createTextNode(label)); }, 2000);
                        } catch (e) {
                            // Clipboard can be blocked in embedded frames: select the
                            // text being copied so a hand copy is one keystroke away.
                            field.focus(); field.select();
                            b.textContent = 'Press Cmd+C';
                        }
                    };
                    return b;
                }
                bar.append(copyBtn('Copy body', ta));
                bar.append(copyBtn('Copy subject', subj));
                const mark = el('button', 'btn btn-primary');
                mark.append(ico(I.check), document.createTextNode('Mark as chased'));
                mark.onclick = async () => {
                    mark.disabled = true;
                    try {
                        const r = await api('/api/liability/chase', { key: c.key });
                        c.last_chased = r.chased;   // mutate the cache so the chip shows without a reload
                        renderLiability();
                    } catch (e) { mark.disabled = false; toastError(e.message || 'Could not record the chase'); }
                };
                bar.append(mark);
                panel.append(bar);
                return panel;
            }
            cardifySections(box);
        }

