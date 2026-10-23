        /* ---------- Stock: the stock sheet, moved into Reactor ----------
           One page with six tabs, in the stock app's own order: Overview
           (its Dashboard), Inventory, Reorder, Suppliers, Trends (with
           Compare) and Activity. Each tab's screen lives in its own section:
           stock-overview.js, stock-inventory.js, stock-deliveries.js (Reorder,
           Suppliers, receiving), stock-records.js (Trends, Activity, the stock
           settings). This section holds what they share: the tab, the reads
           and their one cache, and the stock app's naming, sizing and grouping
           rules, ported from its app.js. The tab shows only once the stock
           sheet has moved in (stockNavShown). */
        let stockSeg = 'overview';
        /* What Inventory's search opens with: the item sheet's Correct count
           sends a person there searching for that line, as the stock app does. */
        let stockInvQuery = '';
        function stockShowInventory(q) { stockInvQuery = q || ''; stockSeg = 'inventory'; renderStock(); }
        /* Every read the tabs share, kept until a write says otherwise. */
        const stockCache = {};
        /* What those reads answered, once they have, for what draws at once (the tab counts). */
        const stockSeen = {};
        async function stockRead(route, op, body) {
            return api('/api/stock/' + route, Object.assign({ op: op }, body || {}));
        }
        /* A read kept by name: the tabs ask for what they need and draw once
           it has come, and a write clears the names it changed. */
        function stockGet(name, route, op, body) {
            // The promise is kept, so two tabs asking at once make one read;
            // a read that fails is forgotten, so the next ask tries again.
            if (!stockCache[name]) {
                stockCache[name] = stockRead(route, op, body);
                stockCache[name].then(v => { stockSeen[name] = v; }, () => { delete stockCache[name]; });
            }
            return stockCache[name];
        }
        function stockForget() { [].slice.call(arguments).forEach(n => { delete stockCache[n]; delete stockSeen[n]; }); }
        function stockForgetAll() { Object.keys(stockCache).forEach(k => { delete stockCache[k]; delete stockSeen[k]; }); }
        /* The shared reads: the sheet (its lines and the quarter's figures),
           the quarters, the warnings, the reorder list and the settings. */
        const stockSheet = () => stockGet('sheet', 'sheet', 'list');
        const stockQuarters = () => stockGet('quarters', 'quarters', 'list');
        const stockAlerts = () => stockGet('alerts', 'overview', 'alerts');
        const stockReorderList = () => stockGet('reorder', 'orders', 'reorder');
        const stockSettings = () => stockGet('settings', 'overview', 'settings');

        async function showStockView() {
            renderStock();
            try { await Promise.all([stockQuarters(), stockAlerts(), stockReorderList()]); }
            catch (e) { /* each tab says for itself what could not be read */ }
            if (document.querySelector('#view-stock.active')) renderStockHead();
        }
        const STOCK_TABS = [['overview', 'Overview'], ['inventory', 'Inventory'], ['reorder', 'Reorder'],
                            ['suppliers', 'Suppliers'], ['trends', 'Trends'], ['activity', 'Activity']];
        /* The open quarter's name under the title, as the stock app shows it
           under its brand, and the counts its tab bar carries. */
        function stockQuarterName() {
            const q = stockSeen.quarters;
            return q && q.current ? (q.current.label || '') : '';
        }
        function stockTabItems() {
            const due = stockSeen.reorder ? stockSeen.reorder.total_lines : null;
            const live = stockSeen.alerts ? (stockSeen.alerts.alerts || []).length : null;
            return STOCK_TABS.map(([k, label]) => ({ key: k, label: label,
                n: k === 'reorder' && due ? due : k === 'activity' && live ? live : null }));
        }
        let stockHeadHost = null, stockTabHost = null;
        function renderStockHead() {
            if (!stockHeadHost || !stockHeadHost.isConnected) return;
            const q = stockQuarterName();
            stockHeadHost.replaceWith(stockHeadHost = pageHead({ view: 'stock', title: 'Stock',
                status: q ? [q] : null, line: q ? null : 'The glass stock, counted, ordered and received.' }));
            stockTabHost.replaceWith(stockTabHost = stockTabStrip());
        }
        function stockTabStrip() {
            return tabStrip(stockTabItems(), stockSeg, (k) => { stockSeg = k; renderStock(); }, { label: 'Stock sections' });
        }
        function renderStock() {
            const box = $('stock-content'); box.innerHTML = '';
            const q = stockQuarterName();
            stockHeadHost = pageHead({ view: 'stock', title: 'Stock', status: q ? [q] : null,
                line: q ? null : 'The glass stock, counted, ordered and received.' });
            stockTabHost = stockTabStrip();
            box.append(stockHeadHost, stockTabHost);
            const host = el('div'); box.append(host);
            /* Each tab's section draws it; a section not yet on the page leaves the tab saying so. */
            const draw = stockSeg === 'overview' ? (typeof renderStockOverview === 'function' ? renderStockOverview : null)
                : stockSeg === 'inventory' ? (typeof renderStockInventory === 'function' ? renderStockInventory : null)
                : stockSeg === 'reorder' ? (typeof renderStockReorder === 'function' ? renderStockReorder : null)
                : stockSeg === 'suppliers' ? (typeof renderStockSuppliers === 'function' ? renderStockSuppliers : null)
                : stockSeg === 'trends' ? (typeof renderStockTrends === 'function' ? renderStockTrends : null)
                : (typeof renderStockActivity === 'function' ? renderStockActivity : null);
            if (draw) draw(host);
            else host.append(emptyState({ icon: I.box, text: 'This part of the stock sheet is not here yet.' }));
        }
        /* A stock sheet printed on its own (the shelf labels, a purchase
           order): a frame holding that sheet alone, with the page's
           stylesheets (a linked file, and any inline) and its own @page, so
           nothing behind it prints and no print rule of the page's is added
           or changed. It prints once the sheets, images and fonts are in. */
        function stockPrintFrame(node, title, pageRule) {
            const fr = el('iframe', 'stk-print-frame');
            fr.title = title;
            fr.srcdoc = '<!doctype html><html><head><meta charset="utf-8"></head><body class="stk-print-doc"></body></html>';
            fr.onload = () => {
                const d = fr.contentDocument;
                const waits = [];
                document.querySelectorAll('link[rel="stylesheet"], style').forEach(s => {
                    const c = d.importNode(s, true);
                    if (c.tagName === 'LINK') {
                        c.href = s.href;   // as the page resolved it
                        waits.push(new Promise(r => { c.onload = r; c.onerror = r; }));
                    }
                    d.head.append(c);
                });
                const page = d.createElement('style');
                page.textContent = pageRule;
                d.head.append(page);
                d.body.append(d.importNode(node, true));
                [...d.images].forEach(im => { if (!im.complete) waits.push(new Promise(r => { im.onload = r; im.onerror = r; })); });
                const ready = Promise.all(waits).then(() => (d.fonts ? d.fonts.ready : null));
                Promise.race([ready, new Promise(r => setTimeout(r, 5000))]).then(() => {
                    try { fr.contentWindow.focus(); fr.contentWindow.print(); }
                    catch (e) { toastError('The print window did not open.'); }
                    setTimeout(() => fr.remove(), 60000);
                });
            };
            document.body.append(fr);
        }
        /* A tab's reads, then its drawing, with Reactor's own failure when a
           read did not come: names the reads, draws when they are all in. */
        async function stockLoad(host, reads, draw) {
            host.append(el('div', 'setting-sub', 'Loading…'));
            let got;
            try { got = await Promise.all(reads.map(r => r())); }
            catch (e) {
                host.innerHTML = '';
                host.append(loadFailure('The stock sheet could not be read. ' + (e.message || ''), () => { stockForgetAll(); renderStock(); }));
                return;
            }
            if (!host.isConnected) return;
            host.innerHTML = '';
            draw.apply(null, got);
        }

        /* ---------- stock rules ----------
           The stock app's own rules, ported from its app.js, and the one way
           every tab names a line, a person, a history entry and a change. */
        const stockGbp = (n, dp) => money(n, 'GBP', dp == null ? 2 : dp);
        const stockNum = (v) => { const m = String(v == null ? '' : v).match(/-?\d+(?:\.\d+)?/); return m ? parseFloat(m[0]) : null; };
        /* A projector's wattage, from its LEDxx model. */
        function stockWatt(it) { const m = String(it.sub_category || '').match(/LED\s*0*(\d+)/i); return m ? parseInt(m[1], 10) : null; }
        /* Sizing is the category's own: glass by its diameter, a ring by the
           largest bezel it holds (with the glass it fits under it), a
           projector by its model and finish, anything else as written. */
        function stockSize(it) {
            const sz = String(it.size || '').trim();
            if (it.category === 'Glass') { const n = stockNum(sz); return { main: n != null ? n + ' mm' : (sz || '') }; }
            if (it.category === 'Rings') {
                const b = stockNum(it.sub_category), g = stockNum(sz);
                return { main: b != null ? b + ' mm' : (it.sub_category || ''), sub: g != null ? 'fits ' + g + ' mm glass' : '' };
            }
            if (it.category === 'Projector') return { main: [it.sub_category, sz].filter(Boolean).join(' · ') };
            return { main: sz };
        }
        function stockSizeText(it) { const c = stockSize(it); return c.main + (c.sub ? ' (' + c.sub + ')' : ''); }
        /* The line's name as a person says it: "Opal 9 20", "86 mm ring". */
        function stockName(it) {
            if (it.category === 'Rings') return stockSize(it).main + ' ring';
            return [it.sub_category, it.size].filter(Boolean).join(' ') + (it.notes ? ' (' + it.notes + ')' : '');
        }
        /* The label a shelf carries: its own barcode, or CL and its id. */
        const stockCode = (it) => (it.barcode && it.barcode.trim()) ? it.barcode.trim() : ('CL' + it.id);
        function stockByCode(items, code) {
            const u = String(code || '').trim().toUpperCase();
            if (!u) return null;
            return (items || []).find(i => (i.barcode || '').trim().toUpperCase() === u || 'CL' + i.id === u) || null;
        }
        /* Quarters of cover (this quarter's rate of use), as the stock app
           shows it: "1.2q", under 1.5 red, under 3 amber. */
        const stockCover = (it) => it.used > 0 ? it.current / it.used : Infinity;
        function stockCoverTone(q) { return q < 1.5 ? 'bad' : q < 3 ? 'warn' : ''; }
        /* Lines grouped the stock app's way: glass by colour or type (the
           Mono glass first, then HM, then the colours by name), projectors by
           wattage (largest first), rings together, anything else by its kind.
           Which glass is Mono and which HM is the stock sheet's own setting. */
        function stockGroups(items, families) {
            const fam = families || {};
            const rank = (s) => s === fam.mono ? 0 : s === fam.hm ? 1 : 2;
            const key = (r) => r.category === 'Glass' ? 'Glass|' + (r.sub_category || '')
                : r.category === 'Projector' ? 'Projector|' + (stockWatt(r) != null ? stockWatt(r) : '?')
                : r.category === 'Rings' ? 'Rings|' : r.category + '|' + (r.sub_category || '');
            const label = (r) => r.category === 'Projector' ? (stockWatt(r) != null ? stockWatt(r) + 'W' : (r.sub_category || 'Projector'))
                : r.category === 'Rings' ? 'Gobo rings' : (r.sub_category || r.category);
            const groups = new Map();
            (items || []).forEach(r => { const k = key(r); if (!groups.has(k)) groups.set(k, []); groups.get(k).push(r); });
            return [...groups.keys()].sort((a, b) => {
                const ia = groups.get(a)[0], ib = groups.get(b)[0];
                if (ia.category !== ib.category) return ia.category.localeCompare(ib.category);
                if (ia.category === 'Glass') return (rank(ia.sub_category) - rank(ib.sub_category)) || (ia.sub_category || '').localeCompare(ib.sub_category || '');
                if (ia.category === 'Projector') return (stockWatt(ib) || 0) - (stockWatt(ia) || 0);
                return (ia.sub_category || '').localeCompare(ib.sub_category || '');
            }).map(k => {
                const rows = groups.get(k).slice().sort((x, y) => {
                    const a = stockSortSize(x), b = stockSortSize(y);
                    return (a == null ? -Infinity : a) - (b == null ? -Infinity : b);
                });
                return { key: k, items: rows, category: rows[0].category, label: label(rows[0]) };
            });
        }
        function stockSortSize(it) {
            if (it.category === 'Glass') return stockNum(it.size);
            if (it.category === 'Rings') return stockNum(it.sub_category);
            if (it.category === 'Projector') return stockWatt(it);
            return stockNum(it.size);
        }
        /* The colour dot beside a line: its category's, or the glass's own
           colour family where the name says one. */
        function stockDot(it) {
            const d = el('span', 'stock-dot');
            d.setAttribute('aria-hidden', 'true');
            const s = String(it.sub_category || '').toLowerCase();
            const fam = ['blue', 'red', 'green', 'amber', 'purple', 'yellow', 'orange', 'pink'].find(c => s.indexOf(c) >= 0);
            d.dataset.tone = it.category === 'Glass' ? (fam || 'clear') : String(it.category || '').toLowerCase();
            return d;
        }

        /* ---- one way to say a line, a person, a history entry and a change, on every tab ---- */
        /* A line by its key, from the sheet when it is read: its name as the
           sheet says it, or, for a line since renamed or deleted, the key's
           own words as the stock app wrote them. */
        function stockLineByKey(key) {
            const sheet = stockSeen.sheet;
            return sheet ? (sheet.items || []).find(i => i.key === key) || null : null;
        }
        function stockKeyName(key) {
            const it = stockLineByKey(key);
            if (it) return stockName(it);
            const p = String(key || '').split('|');
            return p[0] === 'Rings' && p[1] ? p[1] + ' mm ring' : [p[1], p[2]].filter(Boolean).join(' ') + (p[3] ? ' (' + p[3] + ')' : '');
        }
        /* A line's name with its category as the grey caption under it. */
        function stockLineCell(it) {
            const f = document.createDocumentFragment();
            f.append(el('span', 'stock-line-name', stockName(it)));
            if (it.category) f.append(el('span', 'stock-line-cat', it.category));
            return f;
        }
        /* Who made a history entry: the Reactor account's name, with the stock
           app's own username beside it in grey where it was another (design,
           People). The old link's entries read as Production. */
        function stockWho(row) {
            const linked = (s) => /^gizmo$/i.test(String(s || ''));
            const name = linked(row.who) || (linked(row.user) && !row.person) ? 'Production' : (row.who || row.user || '');
            const was = row.user && !linked(row.user) && row.user.toLowerCase() !== name.toLowerCase() ? row.user : '';
            return { name: name, was: was };
        }
        function stockWhoNode(row) {
            const w = stockWho(row), f = document.createDocumentFragment();
            f.append(document.createTextNode(w.name));
            if (w.was) f.append(el('span', 'stock-was', w.was));
            return f;
        }
        /* The history's words: actions in the past tense, fields by the stock
           list's own column names, warnings by their kind. */
        const STOCK_ACTIONS = { update: 'Edited', receive: 'Received', receive_undo: 'Delivery undone', use: 'Used',
            use_undo: 'Use undone', sheet: 'Day sheet', sheet_undo: 'Day sheet undone', ordered: 'Ordered',
            create: 'Added', delete: 'Removed', period: 'Quarter closed', backup: 'Backed up', restore: 'Restored',
            import: 'Imported', login: 'Signed in' };
        const STOCK_FIELDS = { current: 'Current', used: 'Used', received: 'Received', start: 'Start',
            reorder_point: 'Reorder level', reorder_qty: 'Order qty', on_order: 'On order', unit_cost: 'Unit cost',
            unit_cost_gbp: 'Unit £', supplier: 'Supplier', currency: 'Currency', barcode: 'Barcode',
            written_off: 'Written off', notes: 'Notes', category: 'Category', sub_category: 'Colour or type', size: 'Size',
            suppliers: 'Suppliers', settings: 'Settings', key: 'Name', gizmo_alias: 'Production line', order: 'Order',
            supplier_contact: 'Supplier contact', summary: 'Order' };
        const STOCK_KINDS = { anomaly: 'Anomaly', stockout: 'Stockout', low_stock: 'Low stock',
            large_change: 'Large change', job_fail: 'Job fail' };
        function stockWords(code, map) {
            const s = String(code || '');
            if (map[s]) return map[s];
            const w = s.replace(/_/g, ' ');
            return w.charAt(0).toUpperCase() + w.slice(1);
        }
        /* A warning's message without the kind the server repeats at its start
           ("Low stock: ..."), since its kind is shown beside it. */
        function stockWarningText(a) {
            const kind = STOCK_KINDS[a.kind] || '';
            let m = String(a.message || '');
            if (kind && m.toLowerCase().indexOf(kind.toLowerCase() + ':') === 0) m = m.slice(kind.length + 1).trim();
            /* The server names the line "Glass / Opal 9 37.5"; the page says it as every tab does. */
            const it = stockLineByKey(a.item_key);
            if (it) m = m.replace(it.category + ' / ' + [it.sub_category, it.size].filter(Boolean).join(' '), stockName(it));
            return m;
        }
        /* A change: the house chip with a signed amount and, where there is a
           base, its percentage. tone 'good' or 'bad' where the meaning is
           known, else neutral. */
        function stockChange(delta, base, fmt, tone) {
            const d = Number(delta) || 0;
            return changeChip(d > 0 ? 'up' : d < 0 ? 'down' : 'flat', stockSigned(d, base, fmt), tone || 'flat');
        }
        /* A change's words: its sign, the amount and, where there is a base, the percentage ("-£1,426 (12%)"). */
        function stockSigned(delta, base, fmt) {
            const d = Number(delta) || 0;
            const pct = base ? Math.round(Math.abs(d) / Math.abs(base) * 100) : null;
            return (d > 0 ? '+' : d < 0 ? '-' : '') + fmt(Math.abs(d)) + (pct != null ? ' (' + pct + '%)' : '');
        }
        /* ---------- stock rules end ---------- */
