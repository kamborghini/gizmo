        /* ---------- Stock: Trends (with Compare), Activity and the stock settings ----------
           The stock app's Trends, Compare and Activity screens, in their own
           order, with the three settings its Settings screen kept for stock
           (the low-stock days and the two exchange rates) as the last panel of
           Activity: Reactor's own Settings and Team pages already do the
           theme, the password and the people.

           Trends: four figures, the value and units over time, and the lines
           soonest to run out. Compare: two quarters side by side, live or
           closed. Activity: the quarter (rename it, close it, download a
           closed one), the warnings, the history searched across everything
           ever recorded, the backups, and the stock settings. */
        let stockRecView = 'trends';            // Trends or Compare, under the Trends tab
        let stockRecLeft = null, stockRecRight = 'current';
        /* The history's filters and what has been read of it so far, newest first. */
        const stockRecHist = { q: '', action: '', person: '', start: '', end: '', rows: [], more: false, people: {}, seq: 0 };
        /* A page of the history: a hundred at a desk, twenty-five on a phone, where each is a card. */
        const stockRecPage = () => (window.matchMedia && window.matchMedia('(max-width: 640px)').matches) ? 25 : 100;
        /* The tab's host lays its panels out a panel gap apart (the host is a
           holder: it carries no class, so its children stay panels). */
        function stockRecHost(host, name) { host.dataset.stockRec = name; return host; }

        /* ---- words the stock app wrote as code, said as words ---- */
        /* The history's words, people and line names are the Stock page's own (stock.js), so every tab says them alike. */
        const STOCK_REC_ACTIONS = Object.keys(STOCK_ACTIONS).map(k => [k, STOCK_ACTIONS[k]]);
        const STOCK_REC_FIELDS = STOCK_FIELDS;
        const STOCK_REC_KINDS = STOCK_KINDS;
        const stockRecWords = (code, map) => Array.isArray(map) ? ((map.find(a => a[0] === String(code || '')) || [])[1] || stockWords(code, {})) : stockWords(code, map);
        const stockRecWho = stockWho;
        const stockRecItem = stockKeyName;
        function stockRecAgo(iso) {
            const m = Math.floor((Date.now() - Date.parse(iso)) / 60000);
            if (isNaN(m)) return '';
            if (m < 1) return 'just now';
            if (m < 60) return m + 'm ago';
            if (m < 24 * 60) return Math.floor(m / 60) + 'h ago';
            const d = Math.floor(m / 1440);
            return d === 1 ? '1 day ago' : d + ' days ago';
        }
        const stockRecWhen = (iso) => iso ? fmtDate(iso) + ', ' + londonHM(iso) : '';
        const stockRecDays = (d) => { const n = Math.round(d); return n === 1 ? '1 day' : n + ' days'; };
        /* A panel's head: its title (with a count, an info button), its tools on the right. */
        function stockRecHead(title, o) {
            o = o || {};
            const head = el('div', 'card-head');
            const t = el('h3', 'card-title', title);
            if (o.n != null) t.append(el('span', 'card-n', String(o.n)));
            head.append(o.info ? titleInfo(t, infoButton(o.info[0], { title: title, body: o.info[1] })) : t);
            if (o.desc) head.append(el('p', 'card-desc', o.desc));
            if (o.act && o.act.length) { const a = el('div', 'card-act'); o.act.filter(Boolean).forEach(b => a.append(b)); head.append(a); }
            return head;
        }
        function stockRecPanel(cls, title, o) {
            const card = el('div', 'card' + (cls ? ' ' + cls : ''));
            if (title) card.append(stockRecHead(title, o));
            return card;
        }
        /* A cell holding a name and its grey second line. */
        function stockRecTwo(name, sub) {
            const f = document.createDocumentFragment();
            f.append(el('span', 'stock-rec-name', name || ''));
            if (sub) f.append(el('span', 'stock-rec-sub', sub));
            return f;
        }
        /* A name with a grey word beside it (the old username beside the person). */
        function stockRecBeside(name, was) {
            const f = document.createDocumentFragment();
            f.append(document.createTextNode(name || ''));
            if (was) f.append(el('span', 'stock-rec-was', was));
            return f;
        }
        const stockRecCell = (content, cls) => { const td = el('td', cls || null); if (content instanceof Node) td.append(content); else if (content != null) td.textContent = String(content); return td; };
        /* A file the route answers with its bytes rather than JSON (a backup). */
        async function stockRecFile(route, body) {
            const hdrs = Object.assign({ 'Content-Type': 'application/json' }, await authHeaders());
            const sess = appSession(); if (sess) hdrs['X-App-Session'] = sess;
            const res = await fetch('/api/stock/' + route, { method: 'POST', headers: hdrs, body: JSON.stringify(body) });
            if (!res.ok) {
                let words = '';
                try { words = (await res.json()).error || ''; } catch (e) { words = ''; }
                throw new Error(words || 'That file could not be read.');
            }
            return res.blob();
        }
        function stockRecGive(blob, name) {
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob); a.download = name;
            document.body.append(a); a.click(); a.remove();
            setTimeout(() => URL.revokeObjectURL(a.href), 5000);
        }

        /* ================= Trends and Compare ================= */
        function renderStockTrends(host) {
            stockRecHost(host, 'trends');
            /* The Trends or Compare choice, with Compare's two quarters beside it. */
            const row = el('div', 'seg-row');
            row.append(segmented([['trends', 'Trends'], ['compare', 'Compare']], stockRecView,
                (k) => { stockRecView = k; renderStock(); }, { label: 'Trends or Compare' }));
            host.append(row);
            const body = el('div'); host.append(body);
            stockRecHost(body, 'body');
            if (stockRecView === 'compare') stockRecCompare(body, row); else stockRecTrends(body);
        }

        function stockRecTrends(body) {
            const reads = [() => stockGet('trends', 'overview', 'trends'), () => stockGet('forecast', 'overview', 'forecast'),
                           () => stockGet('outlook', 'overview', 'outlook'), stockSheet];
            stockLoad(body, reads, (tr, fc, ol, sheet) => {
                const pts = tr.points || [];
                const vals = pts.map(p => p.active_value_gbp || 0), units = pts.map(p => p.active_units || 0);
                const first = vals[0] || 0, last = vals.length ? vals[vals.length - 1] : 0;
                const now = fc.value_now_gbp != null ? fc.value_now_gbp : last;
                const delta = Math.round((now - first) * 100) / 100;
                /* Every line forecast to run out: the stock app counted its list
                   of the soonest, which stops at twenty. */
                const runOut = (fc.items || []).filter(i => i.days_to_stockout != null);
                body.append(metricsStrip([
                    { label: 'Snapshots on record', value: String(pts.length), note: 'history points' },
                    { label: 'Current active value', value: stockGbp(now, 0),
                      delta: pts.length > 1 ? stockSigned(delta, first, (n) => stockGbp(n, 0)) : null, trend: delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat',
                      note: pts.length > 1 ? 'since the first snapshot' : 'no snapshot yet' },
                    ol && ol.projected != null
                        ? { label: '30-day outlook', value: stockGbp(ol.projected, 0), note: 'from the trend' }
                        : { label: '30-day outlook', value: 'Building…', tone: 'unknown', note: 'needs 5 snapshots, a day apart' },
                    { label: 'Lines forecast to run out', value: String(runOut.length), note: 'with usage history' }]));
                /* The value and the units over time, side by side. */
                const since = pts.length > 1 ? pts.length + ' snapshots · oldest ' + stockRecAgo(pts[0].at) : '';
                const labels = pts.map(p => fmtDate(p.at));
                const chart = (title, source, name, values, format) => {
                    if (pts.length < 2) {
                        const c = stockRecPanel('stock-rec-chart', title);
                        c.append(emptyState({ icon: I.trendUp, text: 'No history yet',
                            sub: 'A snapshot is taken every night and at every change, so the line fills in over the coming days.' }));
                        return c;
                    }
                    return trendChart({ title: title, source: source, labels: labels, format: format,
                        series: [{ name: name, values: values }] });
                };
                const valueChart = chart('Active stock value over time', since, 'Stock value', vals, fmtCompactGBP);
                const unitChart = chart('Active units over time', 'Total units on hand', 'Units', units, fmtCompact);
                body.append(valueChart);
                pairNodes(valueChart, unitChart, 'stock-trends', 'Stock over time', { plain: true, even: true });
                body.append(stockRecSoonest(fc, sheet));
            });
        }

        /* Up to twelve lines, soonest first: days to run out (red under 14,
           amber under 45), the line, what is left, the daily use and what it
           is based on, and the value on the shelf. A row opens the line. */
        function stockRecSoonest(fc, sheet) {
            const card = stockRecPanel('stock-rec-soonest', 'Soonest to run out', { info: ['How it is worked out',
                'Days to run out from how fast each line fell across the snapshots, falling back to this quarter’s run rate '
                + '(used over 90 days) until a line has daily history.'] });
            const rows = (fc.soonest_stockouts || []).slice(0, 12);
            if (!rows.length) {
                card.append(emptyState({ icon: I.trendUp, text: 'No usage recorded yet',
                    sub: 'Forecasts appear once lines show what they use.' }));
                return card;
            }
            const byKey = {};
            (sheet.items || []).forEach(it => { byKey[it.key] = it; });
            /* The item sheet is the Overview area's window, called only when it is there. */
            const openItem = typeof openStockItem === 'function' ? openStockItem : null;
            const t = dataTable(['Runs out in', ['Line', 'kt-main'], ['Left', 'num'], ['Daily use', 'num'], 'Based on', ['Value', 'num']],
                { cls: 'stock-rec-table stock-rec-soon' });
            rows.forEach(s => {
                const it = byKey[s.key];
                const parts = String(s.item || '').split(' / ');
                const name = it ? stockName(it) : (parts[1] || s.item), cat = it ? it.category : parts[0];
                const d = s.days_to_stockout;
                const tag = el('span', 'lbl-chip ' + (d < 14 ? 'bad' : d < 45 ? 'warn' : 'note'), stockRecDays(d));
                const line = el('span', 'stock-rec-line');
                if (it) line.append(stockDot(it));
                line.append(stockRecTwo(name, cat));
                const tr = el('tr');
                const main = stockRecCell(line, 'kt-main');
                if (it && openItem) {
                    tr.classList.add('stock-rec-opens');
                    const open = rowOpener('Open ' + name, () => openItem(it, open));
                    main.append(open);
                    opensOnClick(tr, () => openItem(it, open));
                }
                tr.append(stockRecCell(tag), main, stockRecCell(String(s.current), 'num'),
                    stockRecCell(String(s.daily_use), 'num'), stockRecCell(s.basis === 'history' ? 'History' : 'Run rate'),
                    stockRecCell(stockGbp(s.value_gbp, 0), 'num'));
                t.add(tr);
            });
            card.append(t.wrap);
            return card;
        }

        /* Which two quarters Compare shows: the choice kept from before while
           both still exist, otherwise the quarter closed last (the route gives
           the closed ones last closed first) against the live one. */
        function stockRecComparePair(closed, opts, left, right) {
            const has = (v) => opts.some(o => o[0] === v);
            return [left != null && has(left) ? left : String(closed[0].id), has(right) ? right : 'current'];
        }
        /* Two quarters side by side: the live one or any closed one; by
           default the last closed against now. */
        function stockRecCompare(body, row) {
            stockLoad(body, [stockQuarters], (q) => {
                const closed = q.history || [];
                if (!closed.length) {
                    const card = stockRecPanel('stock-rec-empty');
                    const go = textLink('Go to Activity', { size: 'go' });
                    go.onclick = () => { stockSeg = 'activity'; renderStock(); };
                    card.append(emptyState({ icon: I.compare, text: 'Close a quarter first',
                        sub: 'Then you can compare it with the live quarter.', action: go }));
                    body.append(card);
                    return;
                }
                const opts = [['current', (q.current ? q.current.label : 'Current') + ' (live)']]
                    .concat(closed.map(p => [String(p.id), p.label + ' (closed)']));
                [stockRecLeft, stockRecRight] = stockRecComparePair(closed, opts, stockRecLeft, stockRecRight);
                const pick = el('div', 'stock-rec-pick');
                const arrow = ico(I.arrowRight); arrow.setAttribute('aria-hidden', 'true');
                pick.append(choiceSelect(opts, stockRecLeft, (v) => { stockRecLeft = v; renderStock(); }, { label: 'Compare from' }),
                    arrow, choiceSelect(opts, stockRecRight, (v) => { stockRecRight = v; renderStock(); }, { label: 'Compare to' }),
                    infoButton('About comparing', { title: 'Compare', body:
                        'Compare two quarters: the live quarter or any closed one. It opens on the last closed quarter against now.' }));
                row.append(pick);
                const key = 'compare|' + stockRecLeft + '|' + stockRecRight;
                /* Drawn into the same holder: the panel rule reaches four holders deep. */
                stockLoad(body, [() => stockGet(key, 'quarters', 'compare', { left: stockRecLeft, right: stockRecRight })],
                    (d) => stockRecCompared(body, d));
            });
        }
        function stockRecCompared(res, d) {
            const L = d.left.agg, R = d.right.agg, vs = 'vs ' + d.left.label;
            const fig = (label, l, r, fmt, better) => {
                const delta = Math.round((r - l) * 100) / 100;
                return { label: label, value: fmt(r), delta: stockSigned(delta, l, fmt), trend: delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat',
                         better: better, note: vs };
            };
            const gbp = (n) => stockGbp(n, 0), units = (n) => Number(n || 0).toLocaleString('en-GB');
            res.append(metricsStrip([
                fig('Active stock value', L.active_value, R.active_value, gbp, 'up'),
                fig('Active units', L.active_units, R.active_units, units, 'up'),
                fig('Dead capital', L.dead_value, R.dead_value, gbp, 'down'),
                fig('Written-off sunk cost', L.wo_sunk, R.wo_sunk, gbp, 'down'),
                fig('Used value', L.used_value, R.used_value, gbp, 'up')]));
            /* A change in a list: green when it rose, red when it fell, as the stock app colours it. */
            const chip = (delta, fmt) => stockChange(delta, null, fmt, delta > 0 ? 'good' : delta < 0 ? 'bad' : 'flat');
            const lHead = d.left.label, rHead = d.right.label;
            const cats = stockRecPanel('stock-rec-cats', 'Value by category', { desc: lHead + ' to ' + rHead });
            const ct = dataTable([['Category', 'kt-main'], [lHead, 'num'], [rHead, 'num'], ['Change', 'num']], { cls: 'stock-rec-table' });
            (d.by_category || []).forEach(c => {
                const tr = el('tr');
                tr.append(stockRecCell(c.category, 'kt-main'), stockRecCell(gbp(c.left), 'num'), stockRecCell(gbp(c.right), 'num'),
                    stockRecCell(chip(c.delta, gbp), 'num'));
                ct.add(tr);
            });
            cats.append(ct.wrap);
            const movers = (title, desc, list, n, valueOf, fmt, empty) => {
                const card = stockRecPanel('stock-rec-movers', title, { desc: desc });
                const rows = list.filter(m => valueOf(m)[2] !== 0).slice(0, n);
                if (!rows.length) { card.append(el('div', 'empty', empty)); return card; }
                const t = dataTable([['Line', 'kt-main'], [lHead, 'num'], [rHead, 'num'], ['Change', 'num']], { cls: 'stock-rec-table' });
                rows.forEach(m => {
                    const parts = String(m.item || '').split(' / ');
                    const [l, r, dlt] = valueOf(m);
                    const tr = el('tr');
                    tr.append(stockRecCell(stockRecTwo(parts[1] || m.item, parts[1] ? parts[0] : ''), 'kt-main'),
                        stockRecCell(fmt(l), 'num'), stockRecCell(fmt(r), 'num'), stockRecCell(chip(dlt, fmt), 'num'));
                    t.add(tr);
                });
                card.append(t.wrap);
                return card;
            };
            const byValue = movers('Biggest movers by value', 'Largest change in stock value', d.top_value_movers || [], 8,
                (m) => [m.value_left, m.value_right, m.value_delta], gbp, 'No value changes between these quarters.');
            const byUnits = movers('Biggest movers by units', 'Largest change in units on hand', d.top_unit_movers || [], 10,
                (m) => [m.cur_left, m.cur_right, m.cur_delta], units, 'No unit changes between these quarters.');
            res.append(cats);
            pairNodes(cats, byValue, 'stock-compare', 'Value by category and the biggest movers', { plain: true, even: true });
            res.append(byUnits);
        }

        /* ================= Activity ================= */
        function renderStockActivity(host) {
            stockRecHost(host, 'activity');
            stockLoad(host, [stockQuarters, stockAlerts, stockSettings, () => stockGet('backups', 'backups', 'list'), stockSheet], (q, al, set, bk) => {
                host.append(stockRecQuarter(q), stockRecWarnings(al), stockRecHistory(), stockRecBackups(bk), stockRecSettings(set));
            });
        }

        /* ---- the quarter: its name, rename, close, and the closed ones ---- */
        function stockRecQuarter(q) {
            const cur = q.current || null;
            const card = el('div', 'card stock-rec-quarter');
            const head = el('div', 'card-head card-head-stat');
            head.append(el('h3', 'card-title', 'Quarter'), el('div', 'card-desc', cur ? cur.label : 'None open'),
                el('div', 'card-sub', cur ? 'Opened ' + fmtDate(cur.opened_at) : 'Close a quarter to open one.'));
            const act = el('div', 'card-act');
            const ren = textButton('Rename', { icon: I.edit });
            ren.type = 'button'; ren.disabled = !cur;
            ren.onclick = () => stockRecRename(cur, ren);
            const close = textButton('Close quarter and start new');
            close.type = 'button';
            close.onclick = () => stockRecClose(cur, close);
            act.append(ren, close); head.append(act); card.append(head);
            const closed = q.history || [];
            if (closed.length) {
                card.append(el('h4', 'stock-rec-subhead', 'Closed quarters'));
                const t = dataTable(['Closed', ['Quarter', 'kt-main'], ['Closing value', 'num'], ['Units', 'num'], ['Lines', 'num'],
                                     ['Used value', 'num'], ['', 'num']], { cls: 'stock-rec-table stock-rec-closed' });
                closed.forEach(p => {
                    const dl = textButton('Download CSV', { icon: I.download });
                    dl.type = 'button';
                    dl.setAttribute('aria-label', 'Download CSV of ' + p.label);
                    dl.onclick = async () => {
                        setBusy(dl, true);
                        try {
                            const r = await stockRead('quarters', 'csv', { id: p.id });
                            stockRecGive(new Blob([r.csv], { type: 'text/csv' }), r.filename || (p.label + '.csv'));
                        } catch (e) { toastError(e.message); }
                        setBusy(dl, false);
                    };
                    const tr = el('tr');
                    tr.append(stockRecCell(fmtDate(p.closed_at)), stockRecCell(p.label, 'kt-main'),
                        stockRecCell(stockGbp(p.closing_value_gbp), 'num'), stockRecCell(Number(p.closing_units || 0).toLocaleString('en-GB'), 'num'),
                        stockRecCell(String(p.closing_skus || 0), 'num'), stockRecCell(stockGbp(p.closing_used_value_gbp), 'num'),
                        stockRecCell(dl, 'num stock-rec-act'));
                    t.add(tr);
                });
                card.append(t.wrap);
            }
            return card;
        }
        function stockRecRename(cur, opener) {
            const win = dialog({ title: 'Rename the quarter', opener: opener });
            const inp = el('input', 'psel'); inp.type = 'text'; inp.value = cur ? cur.label : ''; inp.maxLength = 120;
            win.body.append(formField('Quarter name', inp));
            const foot = win.foot();
            const cancel = textButton('Cancel'); cancel.type = 'button'; cancel.onclick = () => win.close();
            const go = textButton('Rename', { kind: 'primary' }); go.type = 'button';
            go.onclick = async () => {
                const label = inp.value.trim();
                if (!label) { toastError('Give the quarter a name.'); inp.focus(); return; }
                setBusy(go, true);
                try {
                    await stockRead('quarters', 'rename', { label: label });
                    stockForgetAll();
                    win.close(); toastOk('Renamed to ' + label + '.'); showStockView();
                } catch (e) { setBusy(go, false); toastError(e.message); }
            };
            inp.onkeydown = (e) => { if (e.key === 'Enter') go.click(); };
            foot.append(cancel, go);
            requestAnimationFrame(() => { inp.focus(); inp.select(); });
        }
        /* Closing rolls every line into the next quarter, and cannot be taken
           back: the confirming button is the one-way kind. */
        function stockRecClose(cur, opener) {
            const win = dialog({ title: 'Close the quarter', opener: opener });
            const say = el('p', 'confirm-msg stock-rec-say');
            say.append(document.createTextNode('Closing '), el('b', null, cur ? cur.label : 'the quarter'),
                document.createTextNode(' saves its closing figures and every line as it stands, then rolls every line into the '
                    + 'new quarter: Current becomes Start, and Used and Received go back to 0. Snapshots and the history are kept.'));
            const inp = el('input', 'psel'); inp.type = 'text'; inp.maxLength = 120; inp.placeholder = 'For example Q1 2027';
            win.body.append(say, formField('New quarter name', inp,
                { help: 'A second close within a minute is held back, so a quarter cannot be closed twice by accident.' }));
            const foot = win.foot();
            const cancel = textButton('Cancel'); cancel.type = 'button'; cancel.onclick = () => win.close();
            const go = textButton('Close and start new', { kind: 'danger' }); go.type = 'button';
            go.onclick = async () => {
                const name = inp.value.trim();
                if (!name) { toastError('Name the new quarter.'); inp.focus(); return; }
                setBusy(go, true);
                try {
                    const r = await stockRead('quarters', 'close', { new_label: name });
                    stockForgetAll(); win.close();
                    toastOk('Closed ' + r.closed + ': ' + r.rolled + ' lines rolled into ' + r.opened + '.');
                    showStockView();
                } catch (e) { setBusy(go, false); toastError(e.message); }
            };
            foot.append(cancel, go);
            requestAnimationFrame(() => inp.focus());
        }

        /* ---- warnings: up to 100 not dismissed, each dismissed with its cross ---- */
        function stockRecWarnings(al) {
            const list = (al && al.alerts) || [];
            const card = stockRecPanel('stock-rec-warns', 'Warnings', { n: list.length || null });
            if (!list.length) {
                card.append(emptyState({ icon: I.checkCircle, text: 'No active warnings',
                    sub: 'Stockouts, low stock, large changes and anomalies appear here.' }));
                return card;
            }
            /* One ruled list, edge to edge: the severity icon, the kind, the
               message and how long ago, and its cross. */
            const ul = el('ul', 'stock-rec-warn-list');
            ul.setAttribute('aria-label', 'Warnings');
            list.forEach(a => {
                const sev = a.severity === 'critical' ? 'bad' : a.severity === 'warning' ? 'warn' : 'info';
                const li = el('li', 'stock-rec-warn');
                const icon = ico(sev === 'info' ? I.info : I.warning);
                icon.classList.add('stock-rec-sev'); icon.dataset.sev = sev;
                const text = el('div', 'stock-rec-warn-text');
                text.append(el('span', 'stock-rec-name', stockRecWords(a.kind, STOCK_REC_KINDS)),
                    el('span', 'stock-rec-sub', stockWarningText(a) + ' \u00b7 ' + stockRecAgo(a.at)));
                const x = iconButton(I.x, 'Dismiss: ' + (a.message || 'this warning'), { size: 'small', title: 'Dismiss' });
                x.onclick = async () => {
                    setBusy(x, true);
                    try {
                        await stockRead('overview', 'dismiss', { id: a.id });
                        stockForget('alerts', 'briefing');
                        await stockAlerts();
                        showStockView();
                    } catch (e) { setBusy(x, false); toastError(e.message); }
                };
                li.append(icon, text, x);
                ul.append(li);
            });
            card.append(ul);
            return card;
        }

        /* ---- the history: every change, who made it and what it was before ---- */
        function stockRecHistory() {
            const card = stockRecPanel('stock-rec-history', 'History', { info: ['How to search it',
                'Every change, who made it and what it was before. Search by line, person or action, for example an invoice '
                + 'number to find a delivery you want to undo. The search covers the whole history, not only what is on screen.'],
                act: [(() => { const u = textButton('Undo a delivery', { icon: I.rotate }); u.type = 'button'; u.onclick = () => stockRecUndo(u); return u; })()] });
            const st = stockRecHist;
            const search = tableSearch('Search the history…', st.q, (v) => { st.q = v; stockRecHistLoad(card, false); });
            const acts = choiceSelect([['', 'All actions']].concat(STOCK_REC_ACTIONS), st.action,
                (v) => { st.action = v; stockRecHistLoad(card, false); }, { label: 'Action' });
            const people = Object.keys(st.people).map(p => [p, st.people[p]]).sort((a, b) => a[1].localeCompare(b[1]));
            const who = choiceSelect([['', 'Everyone']].concat(people), st.person,
                (v) => { st.person = v; stockRecHistLoad(card, false); }, { label: 'Who' });
            who.classList.add('stock-rec-who');
            const day = (val, label, set) => {
                const d = el('input', 'field-sm stock-rec-day'); d.type = 'date'; d.value = val; d.setAttribute('aria-label', label);
                d.onchange = () => { set(d.value); stockRecHistLoad(card, false); };
                return d;
            };
            const span = el('span', 'stock-rec-span');
            span.append(el('span', 'stock-rec-cap', 'From'), day(st.start, 'From', (v) => { st.start = v; }),
                el('span', 'stock-rec-cap', 'to'), day(st.end, 'To', (v) => { st.end = v; }));
            card.append(tableTools([search, acts, who, span], []));
            /* A holder with no class, so the table in it runs to the panel's edges as every table does. */
            const out = el('div'); out.dataset.histOut = ''; card.append(out);
            /* Read afresh each time: any area's change writes a history line. */
            stockRecHistLoad(card, false);
            return card;
        }
        /* What to ask the route for: the filters, a page, and for older
           entries those before the last one shown. */
        function stockRecHistBody(st, older) {
            const body = { limit: stockRecPage() };
            if (st.q) body.q = st.q;
            if (st.action) body.action = st.action;
            if (st.person) body.person = st.person;
            if (st.start) body.start = st.start;
            if (st.end) body.end = st.end;
            if (older && st.rows.length) body.before = st.rows[st.rows.length - 1].id;
            return body;
        }
        /* A page the route answered: older ones go below, a new search starts
           again. Kept in the route's order, newest first as it pages them, so
           the next page starts exactly where this one ended. */
        function stockRecHistMerge(st, d, older) {
            st.rows = older ? st.rows.concat(d.rows || []) : (d.rows || []);
            st.more = !!d.more;
        }
        async function stockRecHistLoad(card, older) {
            const st = stockRecHist, seq = ++st.seq;
            const out = card.querySelector('[data-hist-out]');
            if (!older) { out.innerHTML = ''; out.append(el('div', 'setting-sub', 'Loading…')); }
            const body = stockRecHistBody(st, older);
            let d;
            try { d = await stockRead('history', 'search', body); }
            catch (e) {
                if (seq !== st.seq) return;
                out.innerHTML = ''; out.append(loadFailure('The history could not be read. ' + (e.message || ''), () => stockRecHistLoad(card, older)));
                return;
            }
            if (seq !== st.seq || !card.isConnected) return;
            stockRecHistMerge(st, d, older);
            st.rows.forEach(r => { if (r.person && !st.people[r.person]) st.people[r.person] = stockRecWho(r).name; });
            stockRecWhoFill(card);
            stockRecHistDraw(card);
        }
        /* The Who chooser lists the people the history has shown so far. */
        function stockRecWhoFill(card) {
            const sel = card.querySelector('.stock-rec-who'), st = stockRecHist;
            if (!sel) return;
            const have = new Set([...sel.options].map(o => o.value));
            Object.keys(st.people).sort((a, b) => st.people[a].localeCompare(st.people[b])).forEach(p => {
                if (have.has(p)) return;
                const o = document.createElement('option'); o.value = p; o.textContent = st.people[p]; sel.append(o);
            });
        }
        function stockRecHistDraw(card) {
            const st = stockRecHist, out = card.querySelector('[data-hist-out]');
            out.innerHTML = '';
            const filtered = !!(st.q || st.action || st.person || st.start || st.end);
            if (!st.rows.length) {
                out.append(emptyState({ icon: I.history, text: filtered ? 'Nothing in the history matches that' : 'No history yet' }));
                return;
            }
            const t = dataTable(['When', 'Who', 'Action', ['Item', 'kt-main'], 'Field', ['Before', 'num'], ['After', 'num'], 'Detail'],
                { cls: 'stock-rec-table stock-rec-hist' });
            st.rows.forEach(r => {
                const w = stockRecWho(r);
                const tr = el('tr');
                tr.append(stockRecCell(stockRecWhen(r.at), 'stock-rec-nowrap'), stockRecCell(stockRecBeside(w.name, w.was), 'stock-rec-nowrap'),
                    stockRecCell(el('span', 'lbl-chip note', stockRecWords(r.action, STOCK_REC_ACTIONS))),
                    stockRecCell(stockRecItem(r.item_key), 'kt-main'),
                    stockRecCell(r.field ? stockRecWords(r.field, STOCK_REC_FIELDS) : ''),
                    stockRecCell(r.old_value, 'num'), stockRecCell(r.new_value, 'num'), stockRecCell(r.detail || '', 'stock-rec-detail'));
                t.add(tr);
            });
            out.append(t.wrap);
            const foot = el('div', 'tbl-foot');
            const n = st.rows.length, noun = n === 1 ? ' entry' : ' entries';
            foot.append(el('div', 'tbl-count', st.more ? 'The newest ' + n + noun + (filtered ? ' that match' : '')
                : n + noun + (filtered ? ' match' : '')));
            if (st.more) {
                const more = textButton('Show older entries', { icon: I.chevDown }); more.type = 'button';
                more.onclick = () => { setBusy(more, true); stockRecHistLoad(card, true); };
                foot.append(more);
            }
            out.append(foot);
        }
        /* Undo a whole delivery by its invoice number: the deliveries received
           with an invoice number and not undone, newest first, read from the
           whole history rather than the lines on screen. */
        async function stockRecUndo(opener) {
            setBusy(opener, true);
            let got, undone;
            try {
                [got, undone] = await Promise.all([stockRead('history', 'search', { action: 'receive', limit: 300 }),
                                                   stockRead('history', 'search', { action: 'receive_undo', limit: 300 })]);
            } catch (e) { setBusy(opener, false); toastError(e.message); return; }
            setBusy(opener, false);
            const invOf = (d) => { const m = String(d || '').match(/·\s*inv\s+(.*?)(?:\s*·|$)/); return m ? m[1].trim() : ''; };
            const gone = new Set((undone.rows || []).map(r => invOf(r.detail).toLowerCase()).filter(Boolean));
            const open = [], seen = {};
            (got.rows || []).forEach(r => {
                const inv = invOf(r.detail);
                if (!inv || gone.has(inv.toLowerCase())) return;
                if (!seen[inv]) { seen[inv] = { inv: inv, at: r.at, lines: 0 }; open.push(seen[inv]); }
                seen[inv].lines++;
            });
            if (!open.length) { addToast('No deliveries with an invoice number to undo.'); return; }
            const win = dialog({ title: 'Undo a delivery', opener: opener });
            const which = formField('Which delivery?');
            const sel = el('select', 'psel');
            open.forEach(o => { const op = el('option', null, o.inv + ' (' + fmtDate(o.at) + ', ' + o.lines + (o.lines === 1 ? ' line)' : ' lines)')); op.value = o.inv; sel.append(op); });
            which.append(sel);
            win.body.append(which,
                el('p', 'confirm-msg stock-rec-say', 'The quantities from that delivery come back off stock. The original entries stay in '
                    + 'the history, and the undoing is recorded beside them. It cannot be undone when there is now less on the shelf '
                    + 'than the delivery brought.'));
            const foot = win.foot();
            const cancel = textButton('Cancel'); cancel.type = 'button'; cancel.onclick = () => win.close();
            const go = textButton('Undo delivery', { kind: 'primary' }); go.type = 'button';
            go.onclick = async () => {
                setBusy(go, true);
                try {
                    const r = await stockRead('receive', 'undo', { invoice_no: sel.value });
                    stockForgetAll(); stockRecHist.rows = []; win.close();
                    toastOk('Undid ' + r.invoice_no + ': ' + r.units + ' units off ' + r.undone + (r.undone === 1 ? ' line.' : ' lines.'));
                    showStockView();
                } catch (e) { setBusy(go, false); toastError(e.message); }
            };
            foot.append(cancel, go);
        }

        /* ---- backups: made each night or now, downloaded, restored by the master ---- */
        function stockRecBackups(bk) {
            const list = (bk && bk.backups) || [];
            const make = textButton('Back up now', { icon: I.archive }); make.type = 'button';
            make.onclick = async () => {
                setBusy(make, true);
                try {
                    const b = await stockRead('backups', 'make');
                    stockForget('backups'); stockRecHist.rows = [];
                    toastOk('Backed up ' + b.item_count + ' lines.');
                    renderStock();
                } catch (e) { setBusy(make, false); toastError(e.message); }
            };
            const card = stockRecPanel('stock-rec-backups', 'Backups', { n: list.length || null, act: [make], info: ['What a backup holds',
                ['A stock backup is made every night and kept: the newest 30 always, any from the last week, and never more than 200. '
                 + 'Back up now makes one at once.',
                 'Each holds every line with every field, the suppliers and the settings. A restore puts all of it back, makes a '
                 + 'safety backup first and never removes history. Only the master admin can restore.',
                 'Backups from the old stock app are kept as an archive: they can be downloaded, not restored here.']] });
            if (!list.length) {
                card.append(emptyState({ icon: I.archive, text: 'No backups yet', sub: 'One is made every night, or make one now.' }));
                return card;
            }
            const master = !teamMe || teamMe.role === 'master';   // unknown role: shown; the server enforces master-only
            const t = dataTable([['When', 'kt-main'], 'File', ['Lines', 'num'], ['Size', 'num'], ['', 'num']],
                { cls: 'stock-rec-table stock-rec-bk' });
            list.forEach(b => {
                const archive = b.format === 'legacy-fernet';
                const by = archive ? 'From the old stock app' : b.by === 'system' ? 'Nightly' : 'Made by ' + (b.by || 'someone');
                const acts = el('span', 'stock-rec-acts');
                const dl = textButton('Download', { icon: I.download }); dl.type = 'button';
                dl.setAttribute('aria-label', 'Download the backup from ' + stockRecWhen(b.at));
                dl.onclick = async () => {
                    setBusy(dl, true);
                    try { stockRecGive(await stockRecFile('backups', { op: 'download', id: b.id }), b.filename || ('stock-backup-' + b.id + '.json')); }
                    catch (e) { toastError(e.message); }
                    setBusy(dl, false);
                };
                acts.append(dl);
                if (master && !archive) {
                    const rs = textButton('Restore', { icon: I.archiveRestore }); rs.type = 'button';
                    rs.setAttribute('aria-label', 'Restore the backup from ' + stockRecWhen(b.at));
                    rs.onclick = () => stockRecRestore(b, rs);
                    acts.append(rs);
                }
                const tr = el('tr');
                tr.append(stockRecCell(stockRecTwo(stockRecWhen(b.at), by), 'kt-main'), stockRecCell(b.filename || '', 'stock-rec-file'),
                    stockRecCell(String(b.item_count != null ? b.item_count : ''), 'num'),
                    stockRecCell(b.size_bytes != null ? (b.size_bytes / 1024).toFixed(1) + ' KB' : '', 'num'),
                    stockRecCell(acts, 'num stock-rec-act'));
                t.add(tr);
            });
            card.append(t.wrap);
            return card;
        }
        async function stockRecRestore(b, opener) {
            const ok = await uiConfirm('Restore the backup from ' + stockRecWhen(b.at) + '? Every line, the suppliers and the '
                + 'settings go back to how they were then. A safety backup of the stock as it is now is made first, nothing is '
                + 'taken out of the history, and the glass production has used since is booked again.',
                { title: 'Restore a backup', okText: 'Restore', danger: true });
            if (!ok) return;
            setBusy(opener, true);
            try {
                const r = await stockRead('backups', 'restore', { id: b.id });
                stockForgetAll(); stockRecHist.rows = [];
                toastOk('Restored: ' + r.fields + ' figures put back on ' + r.restored + ' lines. A safety backup was made first.');
                showStockView();
            } catch (e) { setBusy(opener, false); toastError(e.message); }
        }

        /* ---- the stock settings: the low-stock warning and the two exchange rates ---- */
        function stockRecSettings(set) {
            const card = stockRecPanel('stock-rec-settings', 'Stock settings', { info: ['What these change',
                ['A line raises a low-stock warning when it has fewer days of cover than this, at this quarter’s rate of use.',
                 'The exchange rates revalue the stock priced in dollars and euros into pounds at today’s prices. '
                 + 'Each change is written in the history.']] });
            const num = (val, min, max, step) => {
                const i = el('input', 'psel'); i.type = 'number'; i.inputMode = 'decimal';
                i.min = min; if (max) i.max = max; i.step = step; i.value = val == null ? '' : String(val);
                return i;
            };
            const days = num(set.low_stock_days, '1', '365', '1');
            days.inputMode = 'numeric';
            const usd = num(set.fx_usd_gbp, '0', '', '0.0001'), eur = num(set.fx_eur_gbp, '0', '', '0.0001');
            const save = textButton('Save', { icon: I.check }); save.type = 'button';
            save.onclick = async () => {
                const d = parseInt(days.value, 10);
                if (!(d >= 1 && d <= 365)) { markInvalid(days, true); toastError('The low-stock warning takes 1 to 365 days.'); days.focus(); return; }
                markInvalid(days, false);
                setBusy(save, true);
                try {
                    await stockRead('overview', 'save_settings', { low_stock_days: d, fx_usd_gbp: usd.value, fx_eur_gbp: eur.value });
                    stockForgetAll(); stockRecHist.rows = [];
                    toastOk('Stock settings saved.');
                    showStockView();
                } catch (e) { setBusy(save, false); toastError(e.message); }
            };
            const fields = el('div', 'stock-rec-fields');
            fields.append(formField('Low-stock warning under', days, { help: 'days of cover, 1 to 365', cls: 'stock-rec-field' }),
                formField('USD to GBP', usd, { help: 'pounds to the dollar', cls: 'stock-rec-field' }),
                formField('EUR to GBP', eur, { help: 'pounds to the euro', cls: 'stock-rec-field' }), save);
            card.append(fields);
            return card;
        }
        /* ---------- Stock: records end ---------- */
