        /* ---------- products ---------- */
        let productList = null;   // full /api/products payload (or demo)
        let productListAt = null; // when it was fetched, for the freshness stamp
        /* One currency formatter for the whole app. There were two, and they
           disagreed: this one printed "12,480 GBP" while the Liability page
           printed "£18,620" from a hand-written symbol map that knew GBP, USD
           and EUR and nothing else - so a yen or krona order read as
           "JPY 1,234.00". Intl knows every code, and where the symbol goes.

           Cached per code+precision because a NumberFormat is expensive to
           build and these run per row. An unknown or malformed code makes the
           constructor THROW, so that is caught once and remembered as null:
           a bad code from an order must not take the page down, it just falls
           back to the plain number and the code beside it. */
        const _moneyFmts = {};
        function moneyFmt(cur, dp) {
            const code = String(cur || '').trim().toUpperCase();
            const key = code + '|' + dp;
            if (!(key in _moneyFmts)) {
                let f = null;
                try {
                    f = new Intl.NumberFormat('en-GB', Object.assign(
                        { minimumFractionDigits: dp, maximumFractionDigits: dp },
                        /^[A-Z]{3}$/.test(code) ? { style: 'currency', currency: code } : {}));
                } catch (e) { f = null; }
                _moneyFmts[key] = f;
            }
            return _moneyFmts[key];
        }
        function money(n, cur, dp) {
            const v = Number(n) || 0;
            dp = dp === 0 ? 0 : (dp == null ? 0 : dp);
            const f = moneyFmt(cur, dp);
            if (f) return f.format(v);
            return v.toLocaleString('en-GB', { minimumFractionDigits: dp, maximumFractionDigits: dp })
                + (cur ? (' ' + cur) : '');
        }
        const fmtMoney = (n, cur) => money(n, cur, 0);
        /* One way to write a percentage that arrives as a number: one decimal,
           and none when it is whole ('100%', '3.9%', never '100.0%' beside '100%'
           or '1.95%' beside '3.9%'). */
        const pct1 = (v) => { const n = Math.round((Number(v) || 0) * 10) / 10; return (Number.isInteger(n) ? String(n) : n.toFixed(1)) + '%'; };
        /* The compact form for a chart's headline: '£29k', from the same rule,
           rather than fmtCompact with the code stuck on the end ('29k GBP'). */
        const _moneyShortFmts = {};
        function moneyShort(n, cur) {
            const code = String(cur || '').trim().toUpperCase();
            const v = Number(n) || 0;
            if (Math.abs(v) < 1000 || !/^[A-Z]{3}$/.test(code)) return Math.abs(v) < 1000 ? money(v, cur, 0) : fmtCompact(v);
            if (!(code in _moneyShortFmts)) {
                try { _moneyShortFmts[code] = new Intl.NumberFormat('en-GB', { style: 'currency', currency: code,
                        notation: 'compact', maximumFractionDigits: 1 }); }
                catch (e) { _moneyShortFmts[code] = null; }
            }
            const f = _moneyShortFmts[code];
            /* Lower-case k, as the axis under it writes thousands. */
            return f ? f.format(v).replace('K', 'k') : fmtCompact(v);
        }
        const P_ROWS_MAX = 300;   // rows drawn at once; the search and filters still cover every product
        const pState = { q: '', status: '', stock: '', vendor: '', type: '', tag: '', priceMin: null, priceMax: null, minRev: null, minUnits: null, createdAfter: '', createdBefore: '', sort: 'revenue_desc', period: 12, customFrom: null, customTo: null, compare: false, showFilters: false };
        async function loadProducts(force) {
            const box = $('products-content');
            if (productList && !force) { renderProductList(); return; }
            box.innerHTML = '';
            const hero = pageHead({ view: 'products', title: 'Products' }); box.append(hero);
            const t = el('div', 'thinking'); t.append(loader(), el('span', null, 'Loading products and up to 24 months of sales.')); box.append(t);
            try { productList = await api('/api/products', { months: 24, fresh: !!force }); productListAt = Date.now(); renderProductList(); }
            catch (e) {
                reportFailed(box, hero, 'The products could not be loaded. ' + (e.message || String(e)),
                    productList ? () => renderProductList() : null, () => loadProducts(true));
            }
        }
        const pMonths = () => (productList && productList.months) || [];
        function pSelectedMonths() {
            const months = pMonths();
            if (pState.period === 'custom' && pState.customFrom != null && pState.customTo != null) {
                const a = Math.min(pState.customFrom, pState.customTo), b = Math.max(pState.customFrom, pState.customTo);
                return months.slice(a, b + 1);
            }
            const n = pState.period === 'all' ? months.length : Math.min(pState.period, months.length);
            return months.slice(months.length - n);
        }
        function pPrevMonths(sel) {
            const months = pMonths(); if (!sel.length) return [];
            const start = months.indexOf(sel[0]); if (start <= 0) return [];
            return months.slice(Math.max(0, start - sel.length), start);
        }
        const pAgg = (p, ms) => { let u = 0, r = 0; (ms || []).forEach(mk => { const m = p.monthly && p.monthly[mk]; if (m) { u += m.units || 0; r += m.revenue || 0; } }); return { units: u, revenue: r }; };
        /* A month with its year, for anywhere a month is picked or named on
           its own: the menus listed Apr twice with nothing to tell them apart. */
        const monthYear = (ym) => { const m = /^(\d{4})-(\d{2})$/.exec(ym || ''); return m ? (MONTH_ABBR[+m[2] - 1] + ' ' + m[1]) : (ym || ''); };
        function pPeriodLabel() {
            if (pState.period === 'all') return 'all time';
            if (pState.period === 'custom') { const s = pSelectedMonths(); return s.length ? (monthYear(s[0]) + ' to ' + monthYear(s[s.length - 1])) : 'custom range'; }
            return 'last ' + pState.period + ' month' + (pState.period > 1 ? 's' : '');
        }
        function pComputeRows() {
            const sel = pSelectedMonths(), prev = pState.compare ? pPrevMonths(sel) : [], F = pState;
            let rows = ((productList && productList.products) || []).map(p => {
                const c = pAgg(p, sel), pr = F.compare ? pAgg(p, prev) : null;
                return { p, units: c.units, revenue: c.revenue, prevRevenue: pr ? pr.revenue : null };
            });
            rows = rows.filter(r => {
                const p = r.p;
                if (F.q && !(p.title || '').toLowerCase().includes(F.q.toLowerCase())) return false;
                if (F.status && p.status !== F.status) return false;
                if (F.stock && p.stock_status !== F.stock) return false;
                if (F.vendor && p.vendor !== F.vendor) return false;
                if (F.type && p.product_type !== F.type) return false;
                if (F.tag && !((p.tags || []).some(t => (t || '').toLowerCase() === F.tag.toLowerCase()))) return false;
                if (F.priceMin != null && !(Number(p.price) >= F.priceMin)) return false;
                if (F.priceMax != null && !(Number(p.price) <= F.priceMax)) return false;
                if (F.minRev != null && !(r.revenue >= F.minRev)) return false;
                if (F.minUnits != null && !(r.units >= F.minUnits)) return false;
                if (F.createdAfter && !((p.created_at || '') >= F.createdAfter)) return false;
                if (F.createdBefore && !((p.created_at || '') <= F.createdBefore + 'T23:59:59')) return false;
                return true;
            });
            const C = {
                revenue_desc: (a, b) => b.revenue - a.revenue, revenue_asc: (a, b) => a.revenue - b.revenue,
                units_desc: (a, b) => b.units - a.units, units_asc: (a, b) => a.units - b.units,
                newest: (a, b) => (b.p.created_at || '').localeCompare(a.p.created_at || ''),
                oldest: (a, b) => (a.p.created_at || '').localeCompare(b.p.created_at || ''),
                updated: (a, b) => (b.p.updated_at || '').localeCompare(a.p.updated_at || ''),
                price_desc: (a, b) => (b.p.price || 0) - (a.p.price || 0), price_asc: (a, b) => (a.p.price || 0) - (b.p.price || 0),
                title: (a, b) => (a.p.title || '').localeCompare(b.p.title || ''),
            }[F.sort] || ((a, b) => b.revenue - a.revenue);
            rows.sort(C);
            return { rows, sel, prev };
        }
        const pctDelta = (cur, prev) => {
            if (!prev) return { txt: cur > 0 ? 'New' : 'Flat', cls: cur > 0 ? 'up' : 'flat' };
            const ch = (cur - prev) / prev * 100;
            return { txt: (ch >= 0 ? '+' : '') + ch.toFixed(0) + '%', cls: ch > 1 ? 'up' : ch < -1 ? 'down' : 'flat' };
        };
        /* What the filters are called on screen: the stored values are codes. */
        const P_STATUS = { active: 'Active', draft: 'Draft', archived: 'Archived' };
        const P_STOCK = { in: 'In stock', low: 'Low stock', out: 'Out of stock', untracked: 'Not tracked' };
        function pActiveChips(rerender) {
            const F = pState, defs = [];
            const pm = (v) => fmtMoney(v, (productList && productList.currency) || 'GBP');
            if (F.status) defs.push(['Status: ' + (P_STATUS[F.status] || F.status), () => F.status = '']);
            if (F.stock) defs.push(['Stock: ' + (P_STOCK[F.stock] || F.stock), () => F.stock = '']);
            if (F.vendor) defs.push(['Vendor: ' + F.vendor, () => F.vendor = '']);
            if (F.type) defs.push(['Type: ' + F.type, () => F.type = '']);
            if (F.tag) defs.push(['Tag: ' + F.tag, () => F.tag = '']);
            if (F.priceMin != null) defs.push(['Min price ' + pm(F.priceMin), () => F.priceMin = null]);
            if (F.priceMax != null) defs.push(['Max price ' + pm(F.priceMax), () => F.priceMax = null]);
            if (F.minRev != null) defs.push(['Revenue at least ' + pm(F.minRev), () => F.minRev = null]);
            if (F.minUnits != null) defs.push(['At least ' + F.minUnits + (F.minUnits === 1 ? ' unit' : ' units'), () => F.minUnits = null]);
            if (F.createdAfter) defs.push(['Created after ' + fmtDate(F.createdAfter), () => F.createdAfter = '']);
            if (F.createdBefore) defs.push(['Created before ' + fmtDate(F.createdBefore), () => F.createdBefore = '']);
            if (!defs.length) return null;
            const wrap = el('div', 'fchips');
            defs.forEach(([label, clear]) => { const c = el('span', 'fchip', label); const b = el('button'); b.title = 'Remove'; b.innerHTML = I.x; b.onclick = () => { clear(); rerender(); }; c.append(b); wrap.append(c); });
            const all = el('span', 'fchip'); all.style.cursor = 'pointer'; all.textContent = 'Clear all';
            all.onclick = () => { Object.assign(F, { status: '', stock: '', vendor: '', type: '', tag: '', priceMin: null, priceMax: null, minRev: null, minUnits: null, createdAfter: '', createdBefore: '' }); rerender(); };
            wrap.append(all);
            return wrap;
        }
        function exportCSV(rows) {
            const head = ['Title', 'Status', 'Vendor', 'Type', 'Price', 'Inventory', 'Units (' + pPeriodLabel() + ')', 'Revenue (' + pPeriodLabel() + ')', 'Created', 'Updated'];
            const esc = (v) => { v = (v == null ? '' : String(v)); if (/^[=+\-@\t\r]/.test(v)) v = "'" + v; return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
            const lines = [head.join(',')];
            rows.forEach(r => { const p = r.p; lines.push([p.title, p.status, p.vendor, p.product_type, p.price, p.inventory, r.units, r.revenue, (p.created_at || '').slice(0, 10), (p.updated_at || '').slice(0, 10)].map(esc).join(',')); });
            const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
            const url = URL.createObjectURL(blob), a = document.createElement('a');
            a.href = url; a.download = 'products-' + pPeriodLabel().replace(/\s+/g, '-') + '.csv'; document.body.append(a); a.click(); a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        }
        /* The plan being built: a run takes up to a minute, and opening
           another product, or the list painted by any route (Back, a tab
           switch, a reload of the catalogue), while one was running let the
           earlier answer land last and replace what was on screen. */
        let productSeq = 0, productPlanRun = false;
        function renderProductList() {
            productSeq++; productPlanRun = false;     // whatever plan was coming is not what is on screen now
            const box = $('products-content'); box.innerHTML = '';
            /* The page's one line, with Refresh among its actions. */
            box.append(pageHead({ view: 'products', title: 'Products', line: 'Open a product for its optimisation plan.',
                actions: [refreshBtn(() => loadProducts(true), 'Refresh products')] }));
            const cur = (productList && productList.currency) || '';
            if (!((productList && productList.products) || []).length) { box.append(el('div', 'empty', 'No products found.')); return; }
            const rerender = renderProductList;

            /* Composed as the reference composes its orders card: a quiet
               title over a counted line, the three actions on the right, the
               search and the period on a toolbar, then the rows edge to edge
               and a "Viewing N of M" line under them. The bar list of top
               earners is a card of its own above it. */
            const pCard = el('div', 'card');
            const pHead = el('div', 'card-head card-head-stat');
            const pDesc = el('p', 'card-desc');
            const pAct = el('div', 'card-act');
            pHead.append(el('h3', 'card-title', 'Products'), pDesc, pAct);
            pCard.append(pHead);
            const tools = el('div', 'ptools');
            const searchWrap = tableSearch('Search products…', pState.q, (v) => { pState.q = v; drawList(); });
            const periodSeg = segmented([{ label: '1M', value: 1 }, { label: '3M', value: 3 }, { label: '6M', value: 6 }, { label: '12M', value: 12 }, { label: 'All', value: 'all' }, { label: 'Custom', value: 'custom' }], pState.period, v => { pState.period = v; rerender(); });
            const sort = el('select', 'psel'); sort.setAttribute('aria-label', 'Sort products');
            [['revenue_desc', 'Revenue: high to low'], ['revenue_asc', 'Revenue: low to high'], ['units_desc', 'Units: high to low'], ['units_asc', 'Units: low to high'], ['newest', 'Newest first'], ['oldest', 'Oldest first'], ['updated', 'Recently updated'], ['price_desc', 'Price: high to low'], ['price_asc', 'Price: low to high'], ['title', 'Title A to Z']].forEach(([v, l]) => { const o = el('option', null, l); o.value = v; if (v === pState.sort) o.selected = true; sort.append(o); });
            sort.onchange = () => { pState.sort = sort.value; drawList(); };
            const fbtn = textButton(null, { small: true, cls: pState.showFilters ? 'on' : '' }); fbtn.append(ico(I.sliders), document.createTextNode('Filters')); fbtn.onclick = () => { pState.showFilters = !pState.showFilters; rerender(); };
            const cbtn = textButton(null, { small: true, cls: pState.compare ? 'on' : '' }); cbtn.textContent = 'Compare periods'; cbtn.onclick = () => { pState.compare = !pState.compare; rerender(); };
            const xbtn = textButton(null, { small: true, cls: 'p-export' }); xbtn.append(ico(I.download), el('span', 'p-export-txt', 'Export CSV')); xbtn.setAttribute('aria-label', 'Export CSV');
            pAct.append(fbtn, cbtn, xbtn);
            pCard.append(tableTools([searchWrap, periodSeg], [sort]));

            if (pState.period === 'custom') {
                const months = pMonths();
                if (pState.customFrom == null) pState.customFrom = Math.max(0, months.length - 6);
                if (pState.customTo == null) pState.customTo = months.length - 1;
                const cr = el('div', 'row1');
                const mkSel = (val, on, label) => { const f = formField(label); const s = el('select', 'psel'); months.forEach((mk, idx) => { const o = el('option', null, monthYear(mk)); o.value = idx; if (idx === val) o.selected = true; s.append(o); }); s.onchange = () => { on(+s.value); drawList(); }; f.append(s); return f; };
                cr.append(mkSel(pState.customFrom, v => pState.customFrom = v, 'From'), mkSel(pState.customTo, v => pState.customTo = v, 'To'));
                tools.append(cr);
            }

            const fp = el('div', 'pfilters' + (pState.showFilters ? ' show' : ''));
            const selField = (label, value, opts, on, words) => { const f = formField(label); const s = el('select', 'psel'); const a = el('option', null, 'Any'); a.value = ''; s.append(a); opts.forEach(o => { const op = el('option', null, (words && words[o]) || o); op.value = o; if (o === value) op.selected = true; s.append(op); }); s.onchange = () => { on(s.value); drawList(); pchips(); }; f.append(s); return f; };
            const numField = (label, value, on) => { const f = formField(label); const i = el('input', 'psel pnum'); i.type = 'number'; i.min = '0'; if (value != null) i.value = value; i.oninput = () => { on(i.value === '' ? null : Number(i.value)); drawList(); pchips(); }; f.append(i); return f; };
            const dateField = (label, value, on) => { const f = formField(label); const i = el('input', 'psel'); i.type = 'date'; if (value) i.value = value; i.onchange = () => { on(i.value); drawList(); pchips(); }; f.append(i); return f; };
            fp.append(selField('Status', pState.status, ['active', 'draft', 'archived'], v => pState.status = v, P_STATUS));
            fp.append(selField('Stock', pState.stock, ['in', 'low', 'out', 'untracked'], v => pState.stock = v, P_STOCK));
            if ((productList.vendors || []).length) fp.append(selField('Vendor', pState.vendor, productList.vendors, v => pState.vendor = v));
            if ((productList.product_types || []).length) fp.append(selField('Type', pState.type, productList.product_types, v => pState.type = v));
            fp.append(numField('Min price', pState.priceMin, v => pState.priceMin = v));
            fp.append(numField('Max price', pState.priceMax, v => pState.priceMax = v));
            fp.append(numField('Min revenue', pState.minRev, v => pState.minRev = v));
            fp.append(numField('Min units', pState.minUnits, v => pState.minUnits = v));
            fp.append(dateField('Created after', pState.createdAfter, v => pState.createdAfter = v));
            fp.append(dateField('Created before', pState.createdBefore, v => pState.createdBefore = v));
            const tf = formField('Tag'); const tagIn = el('input', 'psel'); tagIn.placeholder = 'e.g. trade'; if (pState.tag) tagIn.value = pState.tag; tagIn.oninput = () => { pState.tag = tagIn.value; drawList(); pchips(); }; tf.append(tagIn); fp.append(tf);
            tools.append(fp);
            pCard.append(tools);

            const chipsHost = el('div'); pCard.append(chipsHost);
            function pchips() { chipsHost.innerHTML = ''; const c = pActiveChips(rerender); if (c) chipsHost.append(c); }
            pchips();

            /* Two cards the grid can move, each spanning the row. drawList
               refills Top products on every search and leaves it empty when
               fewer than two products earned; the layer takes an empty card
               out of the arrangement and puts it back when it fills. */
            /* The totals beside Top products by revenue, one band above the
               table (12 Oct 2026, R6); both refill as the search narrows. */
            const topHost = widget(el('div'), 'top-products', 'full', 'Top products by revenue');
            const totalsW = widget(el('div', 'prod-totals'), 'totals', 'full', 'Totals');
            const listWrap = el('div', 'card-bleed'); pCard.append(listWrap);
            const footHost = el('div', 'card-bleed'); pCard.append(footHost);
            box.append(totalsW, widget(pCard, 'catalog'));
            const bandW = pairNodes(totalsW, topHost, 'top-products', 'Totals and top products by revenue', { flip: true });
            xbtn.onclick = () => { const { rows } = pComputeRows(); if (rows.length) exportCSV(rows); };

            function drawList() {
                const { rows } = pComputeRows();
                const totRev = rows.reduce((a, r) => a + r.revenue, 0), totUnits = rows.reduce((a, r) => a + r.units, 0);
                const all = ((productList && productList.products) || []).length;
                pDesc.textContent = rows.length + ' product' + (rows.length === 1 ? '' : 's');
                totalsW.innerHTML = '';
                totalsW.append(metricsStrip([{ label: 'Revenue', value: fmtMoney(totRev, cur), note: pPeriodLabel() },
                                             { label: 'Units', value: totUnits.toLocaleString(), note: pPeriodLabel() }]));
                /* A search that matches nothing hides the band: no empty ranking
                   and no totals of nothing over one line that says so. */
                topHost.hidden = !rows.length;
                if (bandW) bandW.hidden = !rows.length;
                footHost.innerHTML = '';
                const foot = el('div', 'tbl-foot');
                foot.append(el('div', 'tbl-count', (rows.length > P_ROWS_MAX
                        ? 'Showing ' + P_ROWS_MAX + ' of ' + rows.length + '. Search or filter for more.'
                        : 'Showing ' + rows.length + ' of ' + all + ' product' + (all === 1 ? '' : 's'))
                    + (productList && productList.truncated ? ' Some products are missing: the catalogue is too large.' : '')));
                footHost.append(foot);
                topHost.innerHTML = '';
                const top = rows.filter(r => r.revenue > 0).slice(0, 6);
                /* A search or a filter that leaves fewer than two earners keeps
                   the card and says so. Emptied, it left the page one card,
                   the grid stood down, and Customise vanished from the header
                   and came back as the search was typed. With no filter and
                   fewer than two earners there is no such card at all. */
                const narrowed = rows.length < all;
                if (top.length > 1 || narrowed) {
                    const tc = el('div', 'card'), th2 = el('div', 'card-head');
                    th2.append(el('h3', 'card-title', 'Top products by revenue'));
                    /* The title and the period chooser say what it is; only an
                       empty ranking says why (copy plan, Products #4 and #5). */
                    if (top.length < 2) th2.append(el('p', 'card-desc', 'Nothing to rank for this period.'));
                    tc.append(th2);
                    if (top.length > 1) {
                        const bl = el('div', 'barlist'); const max = top[0].revenue || 1;
                        top.forEach(r => { const row = el('div', 'barrow'); row.append(el('div', 'bn', r.p.title || 'Untitled')); const tr = el('div', 'bartrack'); const i = el('i'); i.style.width = Math.max(2, r.revenue / max * 100) + '%'; tr.append(i); row.append(tr, el('div', 'bv', fmtMoney(r.revenue, cur))); bl.append(row); });
                        tc.append(bl);
                    }
                    topHost.append(tc);
                }
                listWrap.innerHTML = '';
                /* One line and the way back when nothing matches (12 Oct 2026). */
                const none = el('div', 'empty-state');
                const clr = textButton(null, { small: true }); clr.type = 'button'; clr.textContent = 'Clear search';
                clr.onclick = () => { pState.q = ''; rerender(); };
                const nt = el('div', 'empty-txt'); nt.append(el('p', 'empty-line', 'No products match these filters.'));
                const ni = el('span', 'empty-ic'); ni.setAttribute('aria-hidden', 'true'); ni.append(ico(I.search));
                none.append(ni, nt); if (pState.q) none.append(clr);
                /* The whole catalogue arrives so search and filters reach every
                   product; the page draws the first P_ROWS_MAX of what matches,
                   in the order chosen, and says when it stopped. The catalogue is
                   a table (12 Oct 2026): every fact in a headed column, the
                   figures straight after the words, the row opening its plan. */
                const cols = [{ head: 'Product' }, { head: 'Type' }, { head: 'Price', cls: 'num', cap: true }, { head: 'Stock' }, { head: 'Status' },
                              { head: 'Units', cls: 'num', cap: true }, { head: 'Revenue', cls: 'num', cap: true }];
                if (pState.compare) cols.push({ head: 'Change', cls: 'num' });
                cols.push({ head: '', cls: 'act go' });   // the chevron: decoration, gone in two-line rows
                const STOCK_DOT = { in: 'ok', low: 'warn', out: 'bad', untracked: 'off' };
                listWrap.append(dtable(cols, rows.slice(0, P_ROWS_MAX).map(r => {
                    const p = r.p;
                    const safeImg = (p.image && /^https:\/\//i.test(p.image)) ? p.image : null;
                    const th = document.createElement(safeImg ? 'img' : 'div'); th.className = 'prod-thumb';
                    if (safeImg) { th.src = safeImg; th.alt = ''; th.loading = 'lazy'; }
                    const open = () => openProduct(p.id, p.title);
                    const nm = el('button', 'dt-link dt-name', p.title || 'Untitled'); nm.type = 'button'; nm.title = p.title || '';
                    nm.onclick = (e) => { e.stopPropagation(); open(); };
                    const main = document.createDocumentFragment(); main.append(th, nm);
                    const st = el('span', 'dt-name');
                    if (p.stock_status) st.append(el('span', 'dt-dot ' + (STOCK_DOT[p.stock_status] || '')), document.createTextNode(P_STOCK[p.stock_status] || cap(p.stock_status)));
                    const status = p.status === 'active' ? (P_STATUS.active) : el('span', 'lbl-chip note', P_STATUS[p.status] || cap(p.status || ''));
                    const cells = [main, p.product_type || '', p.price ? fmtMoney(p.price, cur) : '', st, status,
                                   r.units.toLocaleString(), fmtMoney(r.revenue, cur)];
                    if (pState.compare) {
                        if (r.prevRevenue != null) { const d = pctDelta(r.revenue, r.prevRevenue); cells.push(el('span', 'cmp ' + d.cls, d.txt)); }
                        else cells.push('');
                    }
                    const go = el('span', 'prod-go'); go.innerHTML = I.chevLeft; go.setAttribute('aria-hidden', 'true');
                    cells.push(go);
                    return { cells, onClick: open };
                }), { cls: 'dt-products' + (pState.compare ? ' cmp' : ''), label: 'Products', empty: none }));
            }
            drawList();
            /* The PDF button followed only a tab switch, so after Load
               products it stayed hidden until you left and came back. */
            syncPrintBtn();
        }
        function productBack() { const b = textButton(null, { cls: 'back-btn' }); b.append(ico(I.chevLeft), document.createTextNode('Products')); b.onclick = renderProductList; return b; }
        async function openProduct(id, title) {
            const my = ++productSeq; productPlanRun = true;
            const box = $('products-content'); box.innerHTML = '';
            box.append(productBack());
            box.append(pageHead({ view: 'products', title: title || 'Product' }));
            const t = el('div', 'thinking'); t.append(loader(), el('span', null, 'Reading search, traffic, sales and on-page SEO to build the plan. This can take up to a minute.')); box.append(t);
            try {
                const d = await api('/api/product', { product_id: id });
                if (my !== productSeq) return;          // overtaken: not what is on screen now
                renderProductDetail(d, id, title);
            }
            catch (e) {
                if (my !== productSeq) return;
                t.remove();
                box.append(loadFailure('The plan for this product could not be built. ' + (e.message || String(e)), () => openProduct(id, title)));
            }
            finally { if (my === productSeq) productPlanRun = false; }
        }
        function renderProductDetail(d, id, title) {
            const box = $('products-content'); box.innerHTML = ''; box.append(productBack());
            const s = d.structured || {};
            /* The plan's header, then its summary as a section of its own (the
               mix, spec 8.3). */
            /* Built the way every other report is: a stamp and Refresh in the
               header, the KPIs as the one strip, charts that name their window,
               and the lists folded into titled cards by cardifySections. It was
               bare headings over a stack of loose cards. */
            /* The plan payload carries no product id, so the one it was opened
               with is passed through; without it there was no Refresh at all. */
            const pid = id || (d.product && d.product.id), ptitle = (d.product && d.product.title) || title;
            box.append(pageHead({ view: 'products', title: ptitle || 'Product', live: pid ? Date.now() : null,
                onRefresh: pid ? () => openProduct(pid, ptitle) : null }));
            { const sum = summarySection(s.summary, null); if (sum) box.append(sum); }
            if (Array.isArray(d.metrics) && d.metrics.length) box.append(metricsStrip(d.metrics));
            if (d.trend && ((d.trend.revenue && d.trend.revenue.length) || (d.trend.units && d.trend.units.length))) {
                const perf = el('div', 'widget-group'); perf.append(el('div', 'section-title', 'Performance over time'));
                const grid = el('div', 'charts-grid');
                const mShort = (n) => moneyShort(n, d.currency);
                const win = (a) => rangeLabel(a.length);
                if (d.trend.revenue && d.trend.revenue.length) { const r = d.trend.revenue; grid.append(trendChart({ title: 'Revenue', source: 'Shopify orders', period: win(r), yUnit: (d.currency || 'Revenue'), value: mShort(sumv(r)), labels: r.map(x => monthLabel(x.label)), series: [{ name: 'Revenue', color: CH[0], values: r.map(x => +x.value || 0) }], format: mShort, tickFormat: fmtCompact, height: 230 })); }
                if (d.trend.units && d.trend.units.length) { const u = d.trend.units; grid.append(barChart({ title: 'Units sold', source: 'Shopify orders', period: win(u), yUnit: 'Units', value: fmtCompact(sumv(u)), labels: u.map(x => monthLabel(x.label)), values: u.map(x => +x.value || 0), format: fmtCompact, height: 230 })); }
                perf.append(grid); box.append(perf);
            }
            if (Array.isArray(s.actions) && s.actions.length) { box.append(el('div', 'section-title', 'Top opportunities')); box.append(actionsCard(s.actions)); }
            if (Array.isArray(s.insights) && s.insights.length) { box.append(el('div', 'section-title', 'Findings')); const b = el('div', 'insights'); s.insights.forEach((x, i) => b.append(insightCard(x, i))); box.append(b); }
            if (Array.isArray(s.sections) && s.sections.length) { box.append(el('div', 'section-title', 'Details')); s.sections.forEach(sec => box.append(sectionCard(sec))); }
            cardifySections(box);
            pairNodes(cardTitled(box, 'Top opportunities'), cardTitled(box, 'Findings'), null, null, { plain: true });
            syncPrintBtn();
        }

