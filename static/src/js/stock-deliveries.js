        /* ---------- Stock: Reorder, Suppliers and receiving ----------
           The stock app's Reorder and Suppliers screens and its receiving
           windows, drawn with Reactor's parts on the routes plans 2a and 2b
           built: what needs ordering by supplier, levels proposed from usage,
           a purchase order drafted, marked as ordered and printed; each
           supplier's contact and reorder email; and stock taken in, one line
           or a whole delivery, with its receipt. The other areas open the two
           receiving windows by name: openStockReceive(opener) and
           openStockReceiveOne(item, opener). */

        /* The reads this area adds to the shared cache: the run-out forecast,
           the suppliers, the levels proposed from usage, and the orders still
           awaited. The forecast is a nicety: without it the run-out column
           says so and the rest still draws, as the stock app did. */
        const stockDelForecast = () => stockGet('forecast', 'overview', 'forecast');
        const stockDelForecastSafe = () => stockDelForecast().catch(() => null);
        const stockDelSuppliers = () => stockGet('suppliers', 'suppliers', 'list');
        const stockDelOpenOrders = () => stockGet('openorders', 'orders', 'list', { open_only: true });

        /* After a write that moved stock: everything read is forgotten, the
           open tab is drawn again (the Inventory keeps its unsaved edits and
           counts by line, so a redraw loses none), and anything else that
           shows stock hears of it. */
        function stockDelAfterWrite() {
            stockForgetAll();
            if (document.querySelector('#view-stock.active')) showStockView();
            document.dispatchEvent(new CustomEvent('stock-changed'));
        }
        /* Lines by key and by id, the sheet's own view of each. */
        function stockDelIndex(sheet) {
            const byKey = {}, byId = {};
            ((sheet && sheet.items) || []).forEach(i => { byKey[i.key] = i; byId[i.id] = i; });
            return { byKey: byKey, byId: byId };
        }
        /* The forecast's days to running out, by line. */
        function stockDelRunMap(fc) {
            const run = {};
            ((fc && fc.items) || []).forEach(o => { if (o.days_to_stockout != null) run[o.key] = o.days_to_stockout; });
            return run;
        }
        /* "~12d · 3 Nov", red under 14 days and amber under 45, as the stock app
           shows it; "now" when it has run out. */
        function stockDelRun(days, short) {
            if (days == null) return { txt: 'not known', tone: '', d: Infinity };
            const when = fmtDate(new Date(Date.now() + days * 86400000).toISOString());
            const lead = days < 1 ? 'now' : '~' + Math.round(days) + 'd';
            return { txt: short ? lead : lead + ' · ' + when, tone: days < 14 ? 'bad' : days < 45 ? 'warn' : '', d: days };
        }
        function stockDelRunCell(days, short) {
            const r = stockDelRun(days, short);
            return el('span', 'sd-run' + (r.tone ? ' ' + r.tone : ''), r.txt);
        }
        /* A line's name with its category beside it, quiet. */
        function stockDelItemCell(it, cat) {
            const f = document.createDocumentFragment();
            f.append(el('span', 'sd-name', it ? stockName(it) : ''));
            if (cat) f.append(el('span', 'sd-sub', cat));
            return f;
        }
        /* The currency most of a supplier's lines are bought in. */
        function stockDelCurrency(items) {
            const n = {};
            items.forEach(i => { const c = i.currency || ''; n[c] = (n[c] || 0) + 1; });
            return Object.keys(n).sort((a, b) => n[b] - n[a])[0] || '';
        }
        const stockDelQty = (v) => { const n = parseInt(v, 10); return isFinite(n) && n > 0 ? n : 0; };
        const stockDelPlural = (n, one, many) => n + ' ' + (n === 1 ? one : (many || one + 's'));
        /* A figure in a group: its words and its number, no help of its own.
           Not statCard(): its label matcher reads "order value" as the Overview's
           average order and hangs that sentence on this figure. */
        function stockDelStat(label, value, tone) {
            const c = el('div', 'stat' + (tone ? ' ' + tone : ''));
            c.append(el('div', 'label', label));
            const row = el('div', 'stat-row');
            row.append(el('div', 'value', value));
            c.append(row);
            return c;
        }
        function stockDelFigures(list) {
            const g = el('div', 'metrics metrics-strip');
            list.forEach(f => g.append(stockDelStat(f[0], f[1], f[2])));
            return g;
        }
        /* A panel's head: the title (a count beside it), its info button, and
           its tools on the right. */
        function stockDelHead(card, title, n, info, acts) {
            const head = el('div', 'card-head');
            const h = el('h3', 'card-title', title);
            if (n) h.append(el('span', 'card-n', n));
            head.append(info ? titleInfo(h, info) : h);
            if (acts && acts.length) {
                const a = el('div', 'card-act');
                acts.filter(Boolean).forEach(b => a.append(b));
                head.append(a);
            }
            card.append(head);
            return head;
        }
        function stockDelInput(type, value, label, placeholder, cls) {
            const i = document.createElement(type === 'textarea' ? 'textarea' : 'input');
            if (type !== 'textarea') i.type = type;
            if (cls) i.className = cls;
            if (value != null) i.value = String(value);
            if (label) i.setAttribute('aria-label', label);
            if (placeholder) i.placeholder = placeholder;
            if (type === 'number') { i.min = '0'; i.inputMode = 'numeric'; }
            return i;
        }
        /* The browser's clipboard, which an embedded page may be refused. */
        async function stockDelCopy(text, done) {
            try { await navigator.clipboard.writeText(text); toastOk(done); }
            catch (e) { toastError('The browser would not copy here. Select the text and copy it yourself.'); }
        }
        function stockDelCsv(name, header, rows) {
            const esc = v => {
                v = String(v == null ? '' : v);
                if (/^[=+\-@\t\r]/.test(v)) v = "'" + v;
                return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
            };
            const txt = [header].concat(rows).map(r => r.map(esc).join(',')).join('\r\n');
            const a = document.createElement('a');
            a.href = URL.createObjectURL(new Blob(['\uFEFF' + txt], { type: 'text/csv' }));
            a.download = name; document.body.append(a); a.click(); a.remove();
            setTimeout(() => URL.revokeObjectURL(a.href), 5000);
        }

        /* ================= REORDER ================= */
        let stockDelLevelsOpen = false;
        function renderStockReorder(host) {
            stockLoad(host, [stockReorderList, stockSheet, stockDelForecastSafe, () => stockDelOpenOrders().catch(() => null)],
                (ro, sheet, fc, orders) => stockDelDrawReorder(host, ro, sheet, fc, orders));
        }
        function stockDelDrawReorder(host, ro, sheet, fc, orders) {
            const idx = stockDelIndex(sheet), run = stockDelRunMap(fc);
            const sups = ro.suppliers || [];
            const urgent = sups.reduce((a, s) => a + s.items.filter(it => run[it.key] != null && run[it.key] <= 21).length, 0);

            /* What needs ordering, in four figures, with the stock app's hint
               behind the info button and its two actions on the rail. */
            const top = el('div', 'card sd-top');
            const levelsBtn = textButton('Set reorder levels from usage', { icon: I.sliders });
            levelsBtn.type = 'button';
            levelsBtn.setAttribute('aria-expanded', stockDelLevelsOpen ? 'true' : 'false');
            levelsBtn.dataset.focusKey = 'stock-levels';
            const refresh = refreshBtn(() => { stockForgetAll(); showStockView(); }, 'Refresh the reorder list');
            stockDelHead(top, 'To reorder', null, infoButton('About Reorder', { title: 'Reorder',
                body: ['Lines at or below their reorder point, counting what is already on order, grouped by supplier.',
                       'Set a reorder point on any line in the Inventory tab (the "Reorder at or below" column), or have them set from usage here. Use Receive when a delivery arrives.'] }),
                [levelsBtn, refresh]);
            const figs = [['Lines to order', String(ro.total_lines || 0)],
                          ['Estimated order value', stockGbp(ro.total_order_value_gbp || 0, 0)],
                          ['Suppliers', String(sups.length)]];
            if (fc) figs.push(['Runs out within 3 weeks', String(urgent), urgent ? 'bad' : '']);
            top.append(stockDelFigures(figs));
            if (!sups.length) {
                const go = textButton('Set reorder levels from usage');
                go.onclick = () => levelsBtn.click();
                top.append(emptyState({ icon: I.box, text: 'Nothing to reorder.',
                    sub: 'Set a reorder level on a line and it appears here when its stock runs low.', action: go }));
            }
            host.append(top);

            /* The proposed levels open under the figures, as the stock app opens them. */
            const levelsHost = el('div');
            host.append(levelsHost);
            levelsBtn.onclick = () => {
                stockDelLevelsOpen = !stockDelLevelsOpen;
                levelsBtn.setAttribute('aria-expanded', stockDelLevelsOpen ? 'true' : 'false');
                levelsHost.innerHTML = '';
                if (stockDelLevelsOpen) stockDelLevels(levelsHost, idx, () => levelsBtn.click());
            };
            if (stockDelLevelsOpen) stockDelLevels(levelsHost, idx, () => levelsBtn.click());

            /* A panel per supplier, soonest to run out first. */
            sups.forEach(s => host.append(stockDelSupplierOrder(s, idx, run)));

            /* Placed orders, kept (flaw 7): what is still to come, cleared from here. */
            const onOrder = stockDelOnOrder(orders, idx);
            if (onOrder) host.append(onOrder);
        }
        function stockDelSupplierOrder(s, idx, run) {
            const card = el('div', 'card sd-supplier');
            const draft = textButton('Draft order', { icon: I.fileDoc });
            draft.type = 'button';
            draft.dataset.focusKey = 'stock-draft-' + s.supplier;
            stockDelHead(card, s.supplier, stockDelPlural(s.lines, 'line') + ' · ' + stockGbp(s.order_value_gbp, 0) + ' to order', null, [draft]);
            draft.onclick = () => stockDelDraftOrder(s, idx, draft);
            const t = dataTable([['Line', 'kt-main'], ['On hand', 'num'], ['On order', 'num'], ['Runs out', 'num'],
                                 ['Reorder at or below', 'num'], ['Suggested', 'num'], ['Order value', 'num'], null], { cls: 'sd-ro-table' });
            const items = s.items.slice().sort((a, b) => stockDelRun(run[a.key]).d - stockDelRun(run[b.key]).d);
            items.forEach(it => {
                const line = idx.byKey[it.key];
                const tr = el('tr');
                const name = el('td'); name.append(stockDelItemCell(line || { category: it.category, sub_category: it.item }, it.category));
                const runTd = el('td', 'num'); runTd.append(stockDelRunCell(run[it.key]));
                const recv = el('td', 'num sd-act');
                const b = textButton('Receive'); b.type = 'button';
                b.onclick = () => { if (line) openStockReceiveOne(Object.assign({}, line, { suggested_qty: it.suggested_qty }), b); };
                recv.append(b);
                tr.append(name, el('td', 'num', String(it.current)), el('td', 'num', String(it.on_order || 0)), runTd,
                          el('td', 'num', String(it.reorder_point)), el('td', 'num', String(it.suggested_qty)),
                          el('td', 'num', stockGbp(it.order_value_gbp)), recv);
                t.add(tr);
            });
            card.append(t.wrap);
            return card;
        }

        /* Levels proposed from usage: a tick per line, both figures editable,
           applied in one go. */
        async function stockDelLevels(host, idx, close) {
            const card = el('div', 'card sd-levels');
            host.append(card);
            const loading = el('p', 'setting-sub', 'Working out levels from this quarter’s usage…');
            card.append(loading);
            let d;
            try { d = await stockRead('orders', 'suggest'); }
            catch (e) { card.innerHTML = ''; card.append(loadFailure('The levels could not be worked out. ' + (e.message || ''), () => { host.innerHTML = ''; stockDelLevels(host, idx, close); })); return; }
            if (!card.isConnected) return;
            card.innerHTML = '';
            const sug = d.suggestions || [];
            stockDelHead(card, 'Proposed reorder levels', sug.length ? stockDelPlural(sug.length, 'line') : null,
                infoButton('How these levels are worked out', { title: 'Proposed reorder levels',
                    body: 'Based on units used this quarter: enough cover for the supplier’s delivery time plus ' + (d.safety_days || 14)
                        + ' days (21 days when no delivery time is set), reordering about a quarter’s worth at a time. Untick anything you would rather set yourself.' }));
            if (!sug.length) {
                card.append(emptyState({ icon: I.sliders, text: 'Nothing to propose.',
                    sub: 'Either the levels already match usage, or no line has recorded usage yet. Counting stock down on a phone records usage.' }));
                return;
            }
            const t = dataTable([null, ['Line', 'kt-main'], ['In stock', 'num'], ['Used', 'num'], ['Reorder at or below', 'num'], ['Order qty', 'num']], { cls: 'sd-lv-table' });
            const rows = [];
            sug.forEach(s => {
                const line = idx.byKey[s.key];
                const name = line ? stockName(line) : String(s.item || '').split(' / ').slice(1).join(' / ');
                const tr = el('tr');
                const tick = tickRow('sd-tick');
                const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = true;
                tick.append(cb, el('span', 'sr-only', 'Include ' + name));
                const tTd = el('td', 'sd-tick-cell'); tTd.dataset.h = ''; tTd.append(tick);
                const nTd = el('td');
                nTd.append(el('span', 'sd-name', name), el('span', 'sd-sub', s.supplier + (s.lead_days ? ' · ' + s.lead_days + 'd delivery' : '')));
                const p = stockDelInput('number', s.reorder_point, 'Reorder at or below for ' + name, null, 'sd-num-in');
                const q = stockDelInput('number', s.reorder_qty, 'Order quantity for ' + name, null, 'sd-num-in');
                const pTd = el('td', 'num'); pTd.append(p);
                const qTd = el('td', 'num'); qTd.append(q);
                tr.append(tTd, nTd, el('td', 'num', String(s.current)), el('td', 'num', String(s.used)), pTd, qTd);
                t.add(tr);
                rows.push({ s: s, line: line, cb: cb, p: p, q: q });
            });
            card.append(t.wrap);
            const bar = el('div', 'sd-actions');
            const apply = textButton('Apply to selected', { kind: 'primary' }); apply.type = 'button';
            const none = textButton('Untick all'); none.type = 'button';
            const shut = textButton('Close'); shut.type = 'button';
            none.onclick = () => rows.forEach(r => { r.cb.checked = false; });
            shut.onclick = close;
            apply.onclick = async () => {
                const levels = rows.filter(r => r.cb.checked && r.line).map(r => ({ id: r.line.id,
                    reorder_point: parseInt(r.p.value, 10) || 0, reorder_qty: parseInt(r.q.value, 10) || 0 }));
                if (!levels.length) { toastError('Nothing is ticked.'); return; }
                setBusy(apply, true);
                try {
                    const r = await stockRead('orders', 'levels', { levels: levels });
                    stockDelLevelsOpen = false;
                    toastOk('Reorder levels set on ' + stockDelPlural(r.updated, 'line') + '.');
                    stockDelAfterWrite();
                } catch (e) { setBusy(apply, false); toastError('The levels were not set. ' + (e.message || '')); }
            };
            bar.append(apply, none, shut);
            card.append(bar);
        }

        /* Orders marked as ordered and not yet all here (flaw 7): each line
           with what has arrived, and a way to clear what will never come. */
        function stockDelOnOrder(orders, idx) {
            const open = ((orders && orders.orders) || []).filter(o => o.open);
            if (!open.length) return null;
            const card = el('div', 'card sd-onorder');
            stockDelHead(card, 'On order', stockDelPlural(open.length, 'order'), infoButton('About On order', { title: 'On order',
                body: ['Orders marked as ordered, kept with what has arrived against each. A line leaves the reorder list while it is on order, and a delivery counts against its oldest open order.',
                       'Clear a line when its order will never come or was logged in error.'] }));
            const t = dataTable([['Line', 'kt-main'], 'Order', ['Ordered', 'num'], ['Arrived', 'num'], ['Still to come', 'num'], null], { cls: 'sd-oo-table' });
            open.forEach(o => o.lines.filter(l => l.outstanding > 0).forEach(l => {
                const line = idx.byId[l.item_id];
                const tr = el('tr');
                const name = el('td'); name.append(stockDelItemCell(line, line ? line.category : String(l.item_key || '').split('|')[0]));
                const ord = el('td');
                ord.append(el('span', 'sd-name', o.reference || (o.before_move ? 'Ordered before the move' : 'No reference')),
                           el('span', 'sd-sub', [o.supplier, fmtDate(o.at), stockWho({ who: o.who, user: o.by, person: o.person }).name].filter(Boolean).join(' · ')));
                const act = el('td', 'num sd-act');
                const clear = textButton('Clear'); clear.type = 'button';
                clear.onclick = async () => {
                    const what = line ? stockName(line) : 'this line';
                    const yes = await uiConfirm('Clear the ' + (line ? line.on_order : l.outstanding) + ' of ' + what + ' still on order? Use this when an order will never come or was logged in error. It clears what is on order for this line on every order.',
                        { title: 'Clear what is on order', okText: 'Clear it', danger: true });
                    if (!yes) return;
                    setBusy(clear, true);
                    try { await stockRead('orders', 'clear', { id: l.item_id }); toastOk('Nothing is on order for ' + what + ' now.'); stockDelAfterWrite(); }
                    catch (e) { setBusy(clear, false); toastError(e.message); }
                };
                act.append(clear);
                tr.append(name, ord, el('td', 'num', String(l.qty)), el('td', 'num', String(l.received || 0)),
                          el('td', 'num', String(l.outstanding)), act);
                t.add(tr);
            }));
            card.append(t.wrap);
            return card;
        }

        /* ---- the draft purchase order ---- */
        /* A purchase order's number, PO-YYYYMMDD-HHMM from the time it is
           drafted, as the stock app numbered them. Never saved: it is printed
           on the order and offered as its reference when it is placed. */
        function stockDelPoNumber(now) {
            const pad = (n) => String(n).padStart(2, '0');
            return 'PO-' + now.getFullYear() + pad(now.getMonth() + 1) + pad(now.getDate()) + '-' + pad(now.getHours()) + pad(now.getMinutes());
        }
        function stockDelDraftOrder(s, idx, opener) {
            const cur = stockDelCurrency(s.items);
            const number = stockDelPoNumber(new Date());   // one number, so the print and the order agree
            const win = dialog({ title: 'Draft order: ' + s.supplier, size: 'wide sd-po-win', opener: opener });
            titleInfo(win.heading, infoButton('About drafting an order', { title: 'Draft order',
                body: ['Edit quantities, then copy or download. Totals update live.',
                       '"Mark as ordered" records these quantities as on their way, so they drop off the reorder list until the delivery arrives.'] }));
            const t = dataTable([['Item', 'kt-main'], ['Qty', 'num'], ['Unit (' + (cur || 'own currency') + ')', 'num'], ['Line', 'num'], ['Line £', 'num']], { cls: 'sd-po-table' });
            const rows = s.items.map(it => {
                const line = idx.byKey[it.key];
                const tr = el('tr');
                const name = el('td'); name.append(stockDelItemCell(line || { category: it.category, sub_category: it.item }));
                const q = stockDelInput('number', it.suggested_qty, 'Quantity of ' + (line ? stockName(line) : it.item), null, 'sd-num-in');
                const qTd = el('td', 'num'); qTd.append(q);
                const lineN = el('td', 'num'), lineG = el('td', 'num');
                tr.append(name, qTd, el('td', 'num', it.unit_cost != null ? money(it.unit_cost, cur, 2) : 'not set'), lineN, lineG);
                t.add(tr);
                const r = { it: it, line: line, q: q, lineN: lineN, lineG: lineG };
                q.addEventListener('input', recalc);
                return r;
            });
            const total = el('tr', 'sd-total');
            const totN = el('td', 'num'), totG = el('td', 'num');
            const tl = el('td', null, 'Total'); tl.dataset.h = '';
            const e1 = el('td'), e2 = el('td');
            totN.dataset.h = 'In ' + (cur || 'its own currency'); totG.dataset.h = 'In pounds';
            total.append(tl, e1, e2, totN, totG);
            t.add(total);
            win.body.append(t.wrap);
            function collect() {
                return rows.map(r => ({ r: r, qty: stockDelQty(r.q.value) })).filter(x => x.qty > 0);
            }
            function sums() {
                let n = 0, g = 0;
                collect().forEach(x => { if (x.r.it.unit_cost != null) n += x.qty * x.r.it.unit_cost; g += x.qty * (x.r.it.unit_cost_gbp || 0); });
                return { native: Math.round(n * 100) / 100, gbp: Math.round(g * 100) / 100 };
            }
            function recalc() {
                rows.forEach(r => {
                    const q = stockDelQty(r.q.value);
                    r.lineN.textContent = r.it.unit_cost != null ? money(q * r.it.unit_cost, cur, 2) : 'not set';
                    r.lineG.textContent = stockGbp(q * (r.it.unit_cost_gbp || 0));
                });
                const s2 = sums();
                totN.textContent = money(s2.native, cur, 2);
                totG.textContent = stockGbp(s2.gbp);
            }
            recalc();
            const note = el('div', 'sd-po-note');
            win.body.append(note);
            const foot = win.foot();
            foot.classList.add('sd-wrap-foot');
            const print = textButton('Print or save as PDF', { icon: I.printer });
            const copy = textButton('Copy text', { icon: I.copy });
            const csv = textButton('Download CSV', { icon: I.download });
            const ai = textButton('Draft cover note', { icon: I.spark });
            const placed = textButton('Mark as ordered', { kind: 'primary' });
            [print, copy, csv, ai, placed].forEach(b => { b.type = 'button'; foot.append(b); });
            const lines = () => collect().map(x => ({ id: x.r.line ? x.r.line.id : null, name: x.r.line ? stockName(x.r.line) : x.r.it.item,
                category: x.r.it.category, qty: x.qty, unit_cost: x.r.it.unit_cost, unit_cost_gbp: x.r.it.unit_cost_gbp || 0 }));
            print.onclick = () => { const l = lines(); if (!l.length) { toastError('Set some order quantities first.'); return; } stockDelPoSheet(s.supplier, cur, l, sums(), print, number); };
            copy.onclick = () => {
                const l = lines(); if (!l.length) { toastError('Set some order quantities first.'); return; }
                const L = ['Purchase order for ' + s.supplier, ''];
                l.forEach(x => L.push(x.qty + ' x ' + x.name + (x.unit_cost != null ? '  at ' + money(x.unit_cost, cur, 2) : '')));
                const s2 = sums(); L.push('', 'Total ' + money(s2.native, cur, 2) + ' (' + stockGbp(s2.gbp) + ')');
                stockDelCopy(L.join('\n'), 'The order is copied.');
            };
            csv.onclick = () => {
                const l = lines(); if (!l.length) { toastError('Set some order quantities first.'); return; }
                stockDelCsv('PO_' + s.supplier.replace(/[^A-Za-z0-9]+/g, '_') + '.csv', ['Item', 'Qty', 'Unit cost', 'Currency', 'Line total'],
                    l.map(x => [x.name, x.qty, x.unit_cost == null ? '' : x.unit_cost, cur, x.unit_cost == null ? '' : Math.round(x.qty * x.unit_cost * 100) / 100]));
                toastOk('The order is downloaded.');
            };
            ai.onclick = async () => {
                const l = lines(); if (!l.length) { toastError('Set some order quantities first.'); return; }
                const s2 = sums();
                note.innerHTML = '';
                const wait = el('p', 'sd-wait'); wait.append(loader(), document.createTextNode('Drafting a cover note…'));
                note.append(wait);
                setBusy(ai, true);
                try {
                    const d = await stockRead('ai', 'po_note', { supplier: s.supplier, currency: cur, native_total: s2.native, gbp_total: s2.gbp,
                        lines: l.map(x => ({ item: x.name, qty: x.qty, unit_cost: x.unit_cost })) });
                    note.innerHTML = '';
                    const box = el('div', 'sd-note-box');
                    box.append(el('h4', 'card-title', 'Cover note'), el('p', 'sd-note-text', d.note));
                    const c = textButton('Copy note', { icon: I.copy }); c.type = 'button';
                    c.onclick = () => stockDelCopy(d.note, 'The note is copied.');
                    box.append(c);
                    note.append(box);
                } catch (e) {
                    note.innerHTML = '';
                    note.append(loadFailure('The cover note could not be drafted. ' + (e.message || ''), () => ai.click()));
                }
                setBusy(ai, false);
            };
            placed.onclick = () => {
                const l = lines(); if (!l.length) { toastError('Set some order quantities first.'); return; }
                stockDelPlace(s.supplier, cur, l, win, placed, number);
            };
        }
        /* Mark as ordered: the reference starts as the order's own number and
           may be changed or cleared, then the quantities go on order. */
        function stockDelPlace(supplier, cur, lines, poWin, opener, number) {
            const win = dialog({ title: 'Mark as ordered', opener: opener });
            win.body.append(el('p', 'sd-lead', stockDelPlural(lines.reduce((a, x) => a + x.qty, 0), 'unit') + ' across ' + stockDelPlural(lines.length, 'line')
                + ' go on order from ' + supplier + '. They leave the reorder list until they arrive.'));
            const ref = stockDelInput('text', number || '', null, 'For example the supplier’s quote number');
            win.body.append(formField('Order reference (optional)', ref, { help: 'The number printed on this order. Type over it to use the supplier’s own.' }));
            const foot = win.foot();
            const no = textButton('Cancel'); no.type = 'button'; no.onclick = () => win.close();
            const go = textButton('Mark as ordered', { kind: 'primary' }); go.type = 'button';
            foot.append(no, go);
            go.onclick = async () => {
                setBusy(go, true);
                try {
                    const d = await stockRead('orders', 'place', { supplier: supplier, reference: ref.value.trim(), currency: cur,
                        lines: lines.map(x => ({ id: x.id, qty: x.qty, unit_cost: x.unit_cost })) });
                    win.close(); poWin.close();
                    toastOk(stockDelPlural(d.units, 'unit') + ' marked as on order from ' + supplier + '.');
                    stockDelAfterWrite();
                } catch (e) { setBusy(go, false); toastError('The order was not recorded. ' + (e.message || '')); }
            };
            ref.focus(); ref.select();
        }
        /* The purchase order as a white page, to print or save as a PDF, with
           the draft's own number. */
        function stockDelPoSheet(supplier, cur, lines, sums, opener, number) {
            const now = new Date();
            const dated = now.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
            const win = dialog({ title: 'Purchase order ' + number, size: 'wide sd-poprint-win', opener: opener });
            const page = el('div', 'sd-po-page');
            const top = el('div', 'sd-po-top');
            const logo = el('div', 'sd-po-logo');
            logo.innerHTML = LABEL_LOGO;      /* our own static markup, as the labels use it */
            const meta = el('div', 'sd-po-meta');
            meta.append(el('div', 'sd-po-h', 'Purchase order'), el('div', null, number), el('div', null, dated));
            top.append(logo, meta);
            const to = el('div', 'sd-po-to');
            to.append(el('div', 'sd-po-cap', 'Supplier'), el('div', 'sd-po-sup', supplier));
            const t = dataTable([['Item', 'kt-main'], ['Qty', 'num'], ['Unit (' + (cur || 'own currency') + ')', 'num'], ['Line', 'num'], ['Line (GBP)', 'num']], { cls: 'sd-po-doc' });
            lines.forEach(x => {
                const tr = el('tr');
                const n = el('td'); n.append(el('span', 'sd-name', x.name), el('span', 'sd-sub', x.category || ''));
                tr.append(n, el('td', 'num', String(x.qty)), el('td', 'num', x.unit_cost != null ? money(x.unit_cost, cur, 2) : 'not set'),
                          el('td', 'num', x.unit_cost != null ? money(x.qty * x.unit_cost, cur, 2) : 'not set'), el('td', 'num', stockGbp(x.qty * x.unit_cost_gbp)));
                t.add(tr);
            });
            const tot = el('tr', 'sd-total');
            const tl = el('td', null, 'Total'); tl.dataset.h = '';
            tot.append(tl, el('td'), el('td'), el('td', 'num', money(sums.native, cur, 2)), el('td', 'num', stockGbp(sums.gbp)));
            t.add(tot);
            page.append(top, to, t.wrap, el('div', 'sd-po-foot', 'Projected Image · purchase order ' + number + ' · ' + dated));
            win.body.append(page);
            const foot = win.foot();
            const close = textButton('Close'); close.type = 'button'; close.onclick = () => win.close();
            const pr = textButton('Print or save as PDF', { kind: 'primary', icon: I.printer }); pr.type = 'button';
            pr.onclick = () => stockPrintFrame(page, 'Purchase order ' + number, '@page { size: A4; margin: 14mm; }');
            foot.append(close, pr);
        }

        /* ================= SUPPLIERS ================= */
        const STOCK_DEL_TEMPLATE = { subject: 'Reorder: {{supplier}}',
            body: 'Hi {{contact}},\n\nWe would like to place a reorder for the following:\n\n{{items}}\n\nPlease confirm availability, current pricing and delivery time.\n\nMany thanks' };
        /* An email app may open a mailto link this long blank: said while the
           message is that long, before it is opened (the stock app's toast
           came as the email app took the screen). */
        function stockDelLongMail(text) {
            return String(text || '').length > 1800 ? 'A long message: if your email app opens it blank, use Copy email instead.' : '';
        }
        function stockDelFill(t, ctx) { return String(t == null ? '' : t).replace(/\{\{(\w+)\}\}/g, (m, k) => (k in ctx ? ctx[k] : m)); }
        function renderStockSuppliers(host) {
            stockLoad(host, [stockDelSuppliers], (d) => stockDelDrawSuppliers(host, d));
        }
        function stockDelDrawSuppliers(host, d) {
            const list = d.suppliers || [];
            const top = el('div', 'card sd-top');
            const bulk = textButton('Add or edit all at once', { icon: I.table }); bulk.type = 'button';
            bulk.dataset.focusKey = 'stock-sup-bulk';
            bulk.onclick = () => stockDelBulk(list, bulk);
            const refresh = refreshBtn(() => { stockForget('suppliers', 'reorder', 'forecast'); showStockView(); }, 'Refresh the suppliers');
            stockDelHead(top, 'Suppliers', list.length ? String(list.length) : null, infoButton('About Suppliers', { title: 'Suppliers',
                body: ['Save each supplier’s email address and a reorder message. When something is due to reorder, Compose fills the message with the low stock and opens it in your own email app to send.',
                       'Stored privately on the server, never in the code or on a public page. Emails are only drafted here: your own email app sends them, and no email password is ever kept.'] }),
                [bulk, refresh]);
            if (!list.length) top.append(emptyState({ icon: I.truck, text: 'No suppliers yet.', sub: 'They appear here once lines in Inventory have a supplier set.' }));
            host.append(top);
            list.forEach(s => host.append(stockDelSupplierCard(s)));
        }
        function stockDelSupplierCard(s) {
            const card = el('div', 'card sd-supcard');
            const head = el('div', 'card-head');
            const h = el('h3', 'card-title', s.supplier);
            const due = (s.due && s.due.lines) || 0;
            h.append(due ? el('span', 'pill sd-tag-warn', due + ' to reorder') : el('span', 'card-n', s.orphan ? 'no stock lines now' : 'nothing due'));
            head.append(h);
            const sub = el('p', 'card-sub');
            if (s.contact_name) sub.append(document.createTextNode(s.contact_name + ' · '));
            sub.append(s.email ? el('span', 'sd-mono', s.email) : el('span', null, 'no email saved yet'));
            head.append(sub);
            const act = el('div', 'card-act');
            const compose = textButton('Compose reorder email', { icon: I.mail }); compose.type = 'button';
            compose.dataset.focusKey = 'stock-compose-' + s.supplier;
            compose.onclick = () => stockDelCompose(s, compose);
            const edit = textButton(s.has_contact ? 'Edit details' : 'Add email', { icon: I.edit }); edit.type = 'button';
            edit.dataset.focusKey = 'stock-edit-' + s.supplier;
            edit.onclick = () => stockDelEditSupplier(s, edit);
            act.append(compose, edit);
            head.append(act);
            card.append(head);
            return card;
        }
        /* One supplier's details, every field the stock app keeps. */
        function stockDelEditSupplier(s, opener) {
            const win = dialog({ title: (s.has_contact ? 'Edit ' : 'Add email for ') + s.supplier, size: 'disp-modal sd-edit-win', opener: opener });
            const email = stockDelInput('email', s.email || '', null, 'orders@supplier.com');
            email.autocomplete = 'off'; email.spellcheck = false;
            const cc = stockDelInput('text', s.cc || '', null, 'you@yourbusiness.com');
            const who = stockDelInput('text', s.contact_name || '', null, 'For example Sarah');
            const lead = stockDelInput('number', s.lead_days ? s.lead_days : '', null, 'For example 30');
            lead.max = '365';
            const min = stockDelInput('text', s.min_order || '', null, 'For example 100 pieces per size');
            const subj = stockDelInput('text', s.subject || STOCK_DEL_TEMPLATE.subject);
            const body = stockDelInput('textarea', s.body || STOCK_DEL_TEMPLATE.body, null, null, 'sd-template');
            body.rows = 9;
            const grid = el('div', 'sd-form');
            grid.append(formField('Supplier email', email),
                formField('Copy to yourself or others (optional)', cc, { help: 'Separate addresses with commas.' }),
                formField('Contact name (optional)', who),
                formField('Typical delivery time (days)', lead, { help: 'Used to work out how early to reorder: a 30 day supplier needs flagging much sooner than a 3 day one.' }),
                formField('Minimum order (optional)', min),
                formField('Subject', subj, { cls: 'sd-wide' }),
                formField('Message template', body, { cls: 'sd-wide', help: 'Filled in when you compose: {{supplier}}, {{contact}}, {{items}}, {{count}} and {{date}}.' }));
            win.body.append(grid);
            const foot = win.foot();
            if (s.has_contact) {
                const del = textButton('Remove', { icon: I.trash, cls: 'sd-foot-start' }); del.type = 'button';
                del.onclick = async () => {
                    const yes = await uiConfirm('Remove the saved email and template for ' + s.supplier + '?', { title: 'Remove ' + s.supplier + '’s details', okText: 'Remove' });
                    if (!yes) return;
                    try { await stockRead('suppliers', 'delete', { supplier: s.supplier }); win.close(); toastOk('Removed.'); stockForget('suppliers'); showStockView(); }
                    catch (e) { toastError(e.message); }
                };
                foot.append(del);
            }
            const no = textButton('Cancel'); no.type = 'button'; no.onclick = () => win.close();
            const save = textButton('Save', { kind: 'primary' }); save.type = 'button';
            foot.append(no, save);
            save.onclick = async () => {
                setBusy(save, true);
                try {
                    await stockRead('suppliers', 'save', { supplier: s.supplier, email: email.value.trim(), cc: cc.value.trim(),
                        contact_name: who.value.trim(), subject: subj.value, body: body.value,
                        lead_days: parseInt(lead.value, 10) || 0, min_order: min.value.trim() });
                    win.close(); toastOk('Saved ' + s.supplier + '.');
                    stockForget('suppliers', 'suggest'); showStockView();
                } catch (e) { setBusy(save, false); toastError(e.message); }
            };
        }
        /* The reorder email, filled from what is low, edited, then opened in
           the person's own email app, which is what sends it. */
        async function stockDelCompose(s, opener) {
            let ro, sheet;
            try { [ro, sheet] = await Promise.all([stockReorderList(), stockSheet()]); }
            catch (e) { toastError('The stock sheet could not be read. ' + (e.message || '')); return; }
            const fc = await stockDelForecastSafe();
            const run = stockDelRunMap(fc), idx = stockDelIndex(sheet);
            const sugQty = (i) => {
                if (i.reorder_qty > 0) return i.reorder_qty;
                if (i.reorder_point > 0) return Math.max(2 * i.reorder_point - i.current, i.reorder_point);
                const u = i.used || 0; return u > 0 ? Math.max(10, Math.ceil(u / 10) * 10) : 10;
            };
            const roLines = (((ro && ro.suppliers) || []).find(x => x.supplier === s.supplier) || {}).items || [];
            const have = new Set(roLines.map(l => l.key));
            const supItems = () => (sheet.items || []).filter(i => !i.written_off && (i.supplier || 'Unknown') === s.supplier);
            const lines = roLines.filter(l => idx.byKey[l.key]).map(l => ({ it: idx.byKey[l.key], qty: l.suggested_qty }))
                .concat(supItems().filter(i => !have.has(i.key) && run[i.key] != null && run[i.key] <= 45).map(i => ({ it: i, qty: sugQty(i) })));
            const win = dialog({ title: 'Reorder email to ' + s.supplier, size: 'disp-modal sd-compose-win', opener: opener });
            titleInfo(win.heading, infoButton('About the reorder email', { title: 'Reorder email',
                body: ['Filled from what is at its reorder point and what is forecast to run out within 45 days. Edit anything.',
                       'Changing the items rewrites the message, so make wording tweaks last. It opens in your own email app, which is what sends it.'] }));
            win.body.append(el('h4', 'card-title', 'Suggested order'));
            const tHost = el('div', 'sd-compose-lines');
            win.body.append(tHost);
            const pick = el('select', 'sd-pick'); pick.setAttribute('aria-label', 'Another line from ' + s.supplier);
            const add = textButton('Add item', { icon: I.plus }); add.type = 'button';
            const addRow = el('div', 'sd-addrow'); addRow.append(pick, add);
            win.body.append(addRow);
            const to = stockDelInput('email', s.email || '', null, 'Add the supplier’s email in Edit details');
            to.spellcheck = false;
            const subj = stockDelInput('text', '');
            const body = stockDelInput('textarea', '', null, null, 'sd-message');
            body.rows = 12;
            const form = el('div', 'sd-form sd-form-one');
            form.append(formField('To', to, s.cc ? { help: 'Copied to ' + s.cc } : null), formField('Subject', subj), formField('Message', body));
            const long = el('p', 'sd-long');
            long.setAttribute('role', 'status');
            const sayLong = () => { long.textContent = stockDelLongMail(body.value); long.hidden = !long.textContent; };
            body.addEventListener('input', sayLong);
            win.body.append(form, long);
            const linesText = () => {
                const v = lines.filter(l => l.qty > 0);
                return v.length ? v.map(l => '- ' + l.qty + ' x ' + stockName(l.it)).join('\n') : '(nothing chosen yet: add lines from the list above)';
            };
            const regen = () => {
                const ctx = { supplier: s.supplier, contact: s.contact_name || 'there', items: linesText(), count: String(lines.filter(l => l.qty > 0).length),
                              date: new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) };
                subj.value = stockDelFill(s.subject || STOCK_DEL_TEMPLATE.subject, ctx);
                body.value = stockDelFill(s.body || STOCK_DEL_TEMPLATE.body, ctx);
                sayLong();
            };
            const rebuildPick = () => {
                const inList = new Set(lines.map(l => l.it.key));
                const opts = supItems().filter(i => !inList.has(i.key));
                pick.innerHTML = '';
                if (!opts.length) pick.append(new Option('Every line is already listed', ''));
                opts.forEach(i => pick.append(new Option(stockName(i) + ' · ' + i.current + ' in stock', String(i.id))));
                add.disabled = !opts.length; pick.disabled = !opts.length;
            };
            const redraw = () => {
                tHost.innerHTML = '';
                if (!lines.length) { tHost.append(el('div', 'empty', 'Nothing looks low right now: add lines from the list below.')); return; }
                const t = dataTable([['Line', 'kt-main'], ['In stock', 'num'], ['Runs out', 'num'], ['Order qty', 'num'], null], { cls: 'sd-compose-table' });
                lines.forEach((l, ix) => {
                    const tr = el('tr');
                    const n = el('td'); n.append(stockDelItemCell(l.it, l.it.category));
                    const r = el('td', 'num'); r.append(stockDelRunCell(run[l.it.key], true));
                    const q = stockDelInput('number', l.qty, 'Order quantity of ' + stockName(l.it), null, 'sd-num-in');
                    q.oninput = () => { l.qty = parseInt(q.value, 10) || 0; regen(); };
                    const qTd = el('td', 'num'); qTd.append(q);
                    const x = iconButton(I.x, 'Remove ' + stockName(l.it), { size: 'small', tone: 'danger' });
                    x.onclick = () => { lines.splice(ix, 1); redraw(); regen(); rebuildPick(); };
                    const xTd = el('td', 'num sd-x'); xTd.append(x);
                    tr.append(n, el('td', 'num', String(l.it.current)), r, qTd, xTd);
                    t.add(tr);
                });
                tHost.append(t.wrap);
            };
            add.onclick = () => {
                const i = idx.byId[pick.value]; if (!i) return;
                lines.push({ it: i, qty: sugQty(i) }); redraw(); regen(); rebuildPick();
            };
            redraw(); regen(); rebuildPick();
            const foot = win.foot();
            const copy = textButton('Copy email', { icon: I.copy }); copy.type = 'button';
            const open = textButton('Open in email app', { kind: 'primary', icon: I.mail }); open.type = 'button';
            foot.append(copy, open);
            copy.onclick = () => stockDelCopy((to.value.trim() ? 'To: ' + to.value.trim() + '\n' : '') + (s.cc ? 'CC: ' + s.cc + '\n' : '')
                + 'Subject: ' + subj.value + '\n\n' + body.value, 'The email is copied: paste it into your email app.');
            open.onclick = () => {
                const q = [];
                if (s.cc) q.push('cc=' + encodeURIComponent(s.cc));
                q.push('subject=' + encodeURIComponent(subj.value), 'body=' + encodeURIComponent(body.value));
                window.location.href = 'mailto:' + encodeURIComponent(to.value.trim()).replace(/%40/g, '@') + '?' + q.join('&');
            };
        }
        /* Every supplier in one text box. Flaw 2 fixed: each block carries the
           delivery time and the minimum order, and a line a block leaves out
           leaves that detail as it is (only the fields a block names are sent,
           and the server keeps the rest). */
        function stockDelBlock(s) {
            return ['Supplier: ' + (s.supplier || ''), 'Email: ' + (s.email || ''), 'CC: ' + (s.cc || ''),
                    'Contact: ' + (s.contact_name || ''), 'Delivery days: ' + (s.lead_days || ''), 'Minimum order: ' + (s.min_order || ''),
                    'Subject: ' + (s.subject || STOCK_DEL_TEMPLATE.subject), 'Message:', (s.body || STOCK_DEL_TEMPLATE.body)].join('\n');
        }
        function stockDelParseBlocks(text) {
            const recs = [];
            let skipped = 0;
            const keys = { supplier: 'supplier', email: 'email', cc: 'cc', contact: 'contact_name', 'contact name': 'contact_name',
                           'delivery days': 'lead_days', 'delivery time': 'lead_days', 'lead days': 'lead_days',
                           'minimum order': 'min_order', 'min order': 'min_order', subject: 'subject' };
            String(text || '').split(/^\s*---+\s*$/m).forEach(bl => {
                if (!bl.trim()) return;
                const rec = {};
                let inMsg = false; const msg = [];
                bl.split(/\r?\n/).forEach(line => {
                    if (inMsg) { msg.push(line); return; }
                    const m = line.match(/^\s*([A-Za-z][A-Za-z ]*?)\s*:\s?(.*)$/);
                    if (!m) return;
                    const k = m[1].trim().toLowerCase(), v = m[2];
                    if (k === 'message' || k === 'body') { inMsg = true; if (v.trim()) msg.push(v); return; }
                    if (keys[k]) rec[keys[k]] = keys[k] === 'lead_days' ? (parseInt(v, 10) || 0) : v.trim();
                });
                if (inMsg) rec.body = msg.join('\n').replace(/^\n+/, '').replace(/\n+$/, '');
                if (!rec.supplier) { skipped++; return; }
                recs.push(rec);
            });
            return { recs: recs, skipped: skipped };
        }
        function stockDelBulk(list, opener) {
            const win = dialog({ title: 'Add or edit all at once', size: 'disp-modal sd-bulk-win', opener: opener });
            titleInfo(win.heading, infoButton('How the blocks are written', { title: 'Add or edit all at once',
                body: ['One block per supplier, separated by a line of three dashes (---). Put the wording under "Message:".',
                       'A blank Email is fine: you can add it later. A line you leave out of a block leaves that detail as it was.'] }));
            const ta = stockDelInput('textarea', (list.length ? list : [{ supplier: 'Supplier name' }]).map(stockDelBlock).join('\n---\n') + '\n', null, null, 'sd-bulk-ta');
            ta.spellcheck = false; ta.rows = 18;
            win.body.append(formField('Every supplier, one block each', ta));
            const status = el('p', 'sd-bulk-status'); status.setAttribute('role', 'status');
            win.body.append(status);
            const foot = win.foot();
            const close = textButton('Close'); close.type = 'button'; close.onclick = () => win.close();
            const go = textButton('Import all', { kind: 'primary' }); go.type = 'button';
            foot.append(close, go);
            go.onclick = async () => {
                const p = stockDelParseBlocks(ta.value);
                status.classList.remove('bad');
                if (!p.recs.length) { status.textContent = 'No supplier blocks were found: each needs a "Supplier:" line.'; status.classList.add('bad'); return; }
                setBusy(go, true);
                status.textContent = 'Saving ' + stockDelPlural(p.recs.length, 'supplier') + '…';
                try {
                    const r = await stockRead('suppliers', 'save_all', { contacts: p.recs });
                    status.textContent = 'Saved ' + stockDelPlural(r.saved, 'supplier') + '.'
                        + (p.skipped ? ' Skipped ' + stockDelPlural(p.skipped, 'block') + ' with no supplier name.' : '');
                    toastOk('Saved ' + stockDelPlural(r.saved, 'supplier') + '.');
                    stockForget('suppliers', 'suggest'); showStockView();
                } catch (e) {
                    status.textContent = 'Nothing was saved: ' + (e.message || 'the server refused it.') + ' Correct that block and import again.';
                    status.classList.add('bad');
                }
                setBusy(go, false);
            };
        }

        /* ================= RECEIVING ================= */
        /* How the delivery came: a PDF to read, or by hand. */
        function openStockReceive(opener) {
            const win = dialog({ title: 'Receive stock', opener: opener, size: 'sd-choose-win' });
            win.body.append(el('p', 'sd-lead', 'How did the delivery arrive?'));
            const pdf = textButton('Read a PDF invoice or delivery note', { kind: 'primary', icon: I.filePdf, cls: 'sd-choice' }); pdf.type = 'button';
            const hand = textButton('Enter it by hand', { icon: I.edit, cls: 'sd-choice' }); hand.type = 'button';
            const file = document.createElement('input');
            file.type = 'file'; file.accept = 'application/pdf,.pdf'; file.hidden = true;
            file.setAttribute('aria-label', 'The invoice or delivery note, as a PDF');
            pdf.onclick = () => file.click();
            file.onchange = () => {
                const f = file.files && file.files[0];
                if (!f) return;
                win.close();
                stockDelReadPdf(f, opener);
            };
            hand.onclick = () => { win.close(); stockDelDelivery({ supplier: '', invoice_no: '', invoice_date: '', lines: [] }, opener); };
            const box = el('div', 'sd-choices'); box.append(pdf, hand, file);
            win.body.append(box);
            win.body.append(el('p', 'field-help', 'A PDF up to 9 MB is read into a delivery for you to check: nothing is received until you accept it. Entering it by hand always works.'));
        }
        /* Reading the PDF: nothing is received yet, and Cancel stops it. */
        function stockDelReadPdf(file, opener) {
            if (file.size > 9 * 1024 * 1024) { toastError('That PDF is over 9 MB. Save a smaller copy and try again.'); return; }
            const win = dialog({ title: 'Reading ' + file.name, x: false, opener: opener, size: 'sd-read-win' });
            const wait = el('div', 'sd-reading');
            wait.append(loader(), el('span', null, 'Reading the stock received from the document. Nothing changes until you accept it.'));
            win.body.append(wait);
            const foot = win.foot();
            const cancel = textButton('Cancel'); cancel.type = 'button';
            let cancelled = false;
            cancel.onclick = () => { cancelled = true; win.close(); };
            foot.append(cancel);
            const fail = (msg) => {
                win.body.innerHTML = '';
                win.body.append(loadFailure('The PDF could not be read. ' + (msg || ''), () => { win.close(); stockDelReadPdf(file, opener); }));
                foot.innerHTML = '';
                const hand = textButton('Enter it by hand', { icon: I.edit }); hand.type = 'button';
                hand.onclick = () => { win.close(); stockDelDelivery({ supplier: '', invoice_no: '', invoice_date: '', lines: [] }, opener); };
                const close = textButton('Close'); close.type = 'button'; close.onclick = () => win.close();
                foot.append(close, hand);
                hand.focus();
            };
            const reader = new FileReader();
            reader.onerror = () => { if (!cancelled) fail('That file could not be opened.'); };
            reader.onload = async () => {
                if (cancelled) return;
                const b64 = String(reader.result || '').split(',')[1] || '';
                try {
                    const data = await stockRead('ai', 'read_invoice', { pdf_base64: b64 });
                    if (cancelled) return;
                    win.close();
                    stockDelDelivery(data, opener);
                } catch (e) { if (!cancelled) fail(e.message); }
            };
            reader.readAsDataURL(file);
        }
        /* The delivery: every line checked before any is taken in. Lines come
           from the PDF (its own words under each) or are added by hand. */
        async function stockDelDelivery(data, opener) {
            let sheet;
            try { sheet = await stockSheet(); }
            catch (e) { toastError('The stock sheet could not be read. ' + (e.message || '')); return; }
            const items = (sheet.items || []).filter(i => !i.written_off).slice();
            const byId = {}; items.forEach(i => { byId[i.id] = i; });
            const win = dialog({ title: 'Delivery summary', size: 'wide sd-dl-win', opener: opener });
            titleInfo(win.heading, infoButton('About the delivery summary', { title: 'Delivery summary',
                body: ['Review before anything changes: check each line’s item and quantity, then accept the stock. All of it is received, or none.',
                       'Tick "update" beside a price to write the invoice’s price onto that line.'] }));
            const sup = stockDelInput('text', data.supplier || '', null, 'From the document');
            const inv = stockDelInput('text', data.invoice_no || '', null, 'For example INV-1043');
            const dt = stockDelInput('text', data.invoice_date || '', null, 'Optional');
            const head = el('div', 'sd-dl-head');
            head.append(formField('Supplier', sup), formField('Invoice or delivery no.', inv), formField('Document date', dt));
            win.body.append(head);
            const t = dataTable([['Line', 'kt-main'], ['Qty', 'num'], ['Unit cost', 'num sd-cost'], 'Match', null], { cls: 'sd-dl-table' });
            win.body.append(t.wrap);
            const rows = [];
            const options = (sel, keep) => {
                sel.innerHTML = '';
                sel.append(new Option('Choose item', ''));
                const groups = {};
                items.slice().sort((a, b) => (a.category + stockName(a)).localeCompare(b.category + stockName(b)))
                    .forEach(i => { (groups[i.category] = groups[i.category] || []).push(i); });
                Object.keys(groups).sort().forEach(cat => {
                    const g = document.createElement('optgroup'); g.label = cat;
                    groups[cat].forEach(i => g.append(new Option(stockName(i) + (i.supplier ? ' · ' + i.supplier : ''), String(i.id))));
                    sel.append(g);
                });
                sel.value = keep ? String(keep) : '';
            };
            const tag = (ln) => !ln.id ? el('span', 'pill sd-tag-bad', 'choose item')
                : ln.manual ? el('span', 'pill sd-tag-info', 'picked by you')
                : (ln.confidence || 0) < 0.7 ? el('span', 'pill sd-tag-warn', 'check match')
                : el('span', 'pill sd-tag-ok', 'matched');
            const totals = el('span', 'sd-totals');
            const recount = () => {
                let n = 0, u = 0;
                rows.forEach(r => { const q = stockDelQty(r.qty.value); if (q && r.sel.value) { n++; u += q; } });
                totals.textContent = n ? stockDelPlural(n, 'line') + ' · ' + stockDelPlural(u, 'unit') : 'no valid lines yet';
            };
            const addRow = (ln) => {
                const tr = el('tr');
                const sel = el('select', 'sd-dl-pick');
                sel.setAttribute('aria-label', 'Item' + (ln.description ? ' for ' + ln.description : ' for this line'));
                options(sel, ln.id);
                const c1 = el('td', 'sd-dl-item'); c1.append(sel);
                if (ln.description) c1.append(el('div', 'sd-desc', ln.description));
                const qty = stockDelInput('number', ln.qty || 1, 'Quantity received' + (ln.description ? ' of ' + ln.description : ''), null, 'sd-num-in');
                const c2 = el('td', 'num'); c2.append(qty);
                const c3 = el('td', 'num sd-cost');
                let upd = null;
                if (ln.unit_cost != null) {
                    c3.append(el('div', null, money(ln.unit_cost, ln.currency || '', 2)));
                    const tk = tickRow('sd-update');
                    upd = document.createElement('input'); upd.type = 'checkbox';
                    tk.append(upd, document.createTextNode('update'));
                    c3.append(tk);
                } else c3.textContent = 'none';
                const c4 = el('td', 'sd-match'); c4.append(tag(ln));
                const x = iconButton(I.x, 'Remove this line', { size: 'small', tone: 'danger' });
                const c5 = el('td', 'num sd-x'); c5.append(x);
                tr.append(c1, c2, c3, c4, c5);
                t.add(tr);
                const r = { ln: ln, tr: tr, sel: sel, qty: qty, upd: upd };
                rows.push(r);
                sel.onchange = () => { ln.id = sel.value ? parseInt(sel.value, 10) : null; ln.manual = true; c4.innerHTML = ''; c4.append(tag(ln)); recount(); };
                qty.oninput = recount;
                x.onclick = () => { rows.splice(rows.indexOf(r), 1); tr.remove(); recount(); };
                return r;
            };
            ((data.lines && data.lines.length) ? data.lines : [{ qty: 1 }]).forEach(l => addRow(Object.assign({}, l)));
            const more = el('div', 'sd-addrow');
            const addLine = textButton('Add line', { icon: I.plus }); addLine.type = 'button';
            const newItem = textButton('New item', { icon: I.plus }); newItem.type = 'button';
            addLine.onclick = () => { addRow({ qty: 1 }).sel.focus(); recount(); };
            newItem.onclick = () => stockDelNewItem(sup.value.trim(), (it) => {
                items.push(it); byId[it.id] = it;
                rows.forEach(r => options(r.sel, r.sel.value));
                const r = addRow({ qty: 1, id: it.id, manual: true, description: 'new item' });
                r.qty.focus(); recount();
            }, newItem);
            more.append(addLine, newItem);
            win.body.append(more);
            const whoLine = el('p', 'sd-who');
            const whoWords = el('span');
            whoWords.append(document.createTextNode('Will be recorded as received by '), el('b', null, (teamMe && teamMe.name) || 'you'),
                document.createTextNode(' at the time you accept, against this invoice number.'));
            whoLine.append(ico(I.userCheck), whoWords);
            win.body.append(whoLine);
            const err = el('div');
            win.body.append(err);
            recount();
            const foot = win.foot();
            const cancel = textButton('Cancel'); cancel.type = 'button'; cancel.onclick = () => win.close();
            const accept = textButton('Accept stock', { kind: 'primary' }); accept.type = 'button';
            foot.append(totals, cancel, accept);
            accept.onclick = async () => {
                const d = await stockDelAccept(rows, { invoice_no: inv.value.trim(), date: dt.value.trim() }, {
                    busy: (on) => setBusy(accept, on),
                    say: (m) => { err.innerHTML = ''; if (m) err.append(el('div', 'msg error', m)); } });
                if (!d) return;
                win.close();
                stockDelAfterWrite();
                stockDelReceipt(d, sup.value.trim(), opener);
            };
        }
        /* Accepting a delivery: every good line in one write, or none. A
           refusal (an invoice already received for a line, say) is said in
           the window in the server's words, and every line stays as typed. */
        async function stockDelAccept(rows, fields, ui) {
            ui.say('');
            const all = rows.map(r => ({ id: r.sel.value ? parseInt(r.sel.value, 10) : null, qty: stockDelQty(r.qty.value),
                update_cost: !!(r.upd && r.upd.checked), unit_cost: r.ln.unit_cost }));
            const good = all.filter(r => r.id && r.qty > 0), skipped = all.length - good.length;
            if (!good.length) { toastError('Nothing to receive: pick an item and a quantity on at least one line.'); return null; }
            if (skipped) {
                const yes = await uiConfirm(stockDelPlural(skipped, 'line') + (skipped === 1 ? ' has' : ' have') + ' no item or no quantity and will be skipped. Accept the rest?',
                    { title: 'Accept the rest', okText: 'Accept the rest' });
                if (!yes) return null;
            }
            ui.busy(true);
            try {
                return await stockRead('receive', 'delivery', { invoice_no: fields.invoice_no, date: fields.date,
                    lines: good.map(r => ({ id: r.id, qty: r.qty, update_cost: r.update_cost, unit_cost: r.unit_cost })) });
            } catch (e) {
                ui.busy(false);
                ui.say(e.message || 'The delivery was not received.');
                return null;
            }
        }
        /* A line created mid-delivery, at zero stock: the delivery puts stock on it. */
        function stockDelNewItem(supplier, onAdded, opener) {
            const win = dialog({ title: 'New item from this delivery', opener: opener });
            const cats = [...new Set(((stockSeen.sheet && stockSeen.sheet.items) || []).map(i => i.category))].filter(Boolean).sort();
            const cat = el('select');
            cat.setAttribute('aria-label', 'Category');
            cats.forEach(c => cat.append(new Option(c, c)));
            cat.append(new Option('Something else…', '__new'));
            const catNew = stockDelInput('text', '', null, 'For example Cables');
            const catField = formField('New category name', catNew);
            catField.hidden = true;
            cat.onchange = () => { catField.hidden = cat.value !== '__new'; };
            const sub = stockDelInput('text', '', null, 'For example Opal 9');
            const size = stockDelInput('text', '', null, 'For example 20');
            const sup = stockDelInput('text', supplier || '');
            const sups = [...new Set(((stockSeen.sheet && stockSeen.sheet.items) || []).map(i => i.supplier).filter(Boolean))].sort();
            const dl = document.createElement('datalist'); dl.id = 'sd-sup-list';
            sups.forEach(s => dl.append(new Option(s, s)));
            sup.setAttribute('list', 'sd-sup-list');
            const cost = stockDelInput('number', '', null, 'From the invoice');
            cost.step = '0.0001';
            const cur = stockDelInput('text', 'GBP', null, 'GBP, USD or EUR');
            const form = el('div', 'sd-form');
            form.append(formField('Category', cat), catField, formField('Name or colour', sub), formField('Size', size),
                formField('Supplier', sup), dl, formField('Unit cost (optional)', cost), formField('Currency', cur));
            win.body.append(form, el('p', 'field-help', 'It starts at zero stock: the delivery’s quantity is what puts stock on it.'));
            const foot = win.foot();
            const no = textButton('Cancel'); no.type = 'button'; no.onclick = () => win.close();
            const go = textButton('Create and add', { kind: 'primary' }); go.type = 'button';
            foot.append(no, go);
            go.onclick = async () => {
                const category = cat.value === '__new' ? catNew.value.trim() : cat.value;
                if (!category) { toastError('Give the category a name.'); return; }
                if (!sub.value.trim()) { toastError('Give the item a name.'); return; }
                const fields = { category: category, sub_category: sub.value.trim(), size: size.value.trim(),
                                 supplier: sup.value.trim(), currency: cur.value.trim().toUpperCase() };
                const c = parseFloat(cost.value);
                if (isFinite(c) && c >= 0) { fields.unit_cost = c; fields.unit_cost_gbp = c; }
                setBusy(go, true);
                try {
                    const d = await stockRead('sheet', 'new', { fields: fields });
                    stockForget('sheet');
                    win.close();
                    onAdded(d.item);
                    toastOk('Added ' + stockName(d.item) + '.');
                } catch (e) { setBusy(go, false); toastError(e.message); }
            };
        }
        /* The receipt: what came in, who took it and when, each line's new
           level and the order it counted against (flaw 7: changeable here),
           and the way back while the invoice is known. */
        async function stockDelReceipt(d, supplier, opener) {
            const win = dialog({ title: 'Stock received', size: 'disp-modal sd-receipt-win', opener: opener });
            const at = d.received_at ? fmtDate(d.received_at) + ', ' + londonHM(d.received_at) : '';
            win.body.append(stockDelFigures([['Units received', String(d.units)], ['Lines', String(d.applied)], ['Prices updated', String(d.repriced || 0)]]));
            const said = el('p', 'sd-lead');
            said.append(document.createTextNode((supplier ? 'From ' + supplier : 'A delivery') + (d.invoice_no ? ', invoice ' + d.invoice_no : ', with no invoice number') + '. Recorded by '),
                el('b', null, d.by || ''), document.createTextNode(at ? ' on ' + at + '.' : '.'));
            win.body.append(said);
            let orders = [];
            try { orders = ((await stockRead('orders', 'list', {})).orders) || []; } catch (e) { orders = []; }
            const byOrder = {}; orders.forEach(o => { byOrder[o.id] = o; });
            const orderName = (o) => (o.reference || ('Order ' + o.id)) + ' · ' + fmtDate(o.at);
            const now = {}; (d.items || []).forEach(i => { now[i.id] = i; });
            const t = dataTable([['Line', 'kt-main'], ['Received', 'num'], ['Now in stock', 'num'], 'Counted against'], { cls: 'sd-rc-table' });
            ((d.receipt && d.receipt.lines) || []).forEach(l => {
                const tr = el('tr');
                const it = now[l.id];
                const n = el('td'); n.append(stockDelItemCell(it || { category: '', sub_category: l.name }, it ? it.category : ''));
                const against = el('td');
                const filled = (l.orders || []).map(f => byOrder[f.order_id]).filter(Boolean);
                const others = orders.filter(o => o.open && filled.indexOf(o) < 0 && o.lines.some(x => x.item_id === l.id && x.outstanding > 0));
                if (d.invoice_no && filled.length === 1 && others.length) {
                    const sel = el('select', 'sd-pick');
                    sel.setAttribute('aria-label', 'The order ' + l.name + ' counts against');
                    [filled[0]].concat(others).forEach(o => sel.append(new Option(orderName(o), String(o.id))));
                    sel.onchange = async () => {
                        try { await stockRead('receive', 'rematch', { invoice_no: d.invoice_no, id: l.id, order_id: parseInt(sel.value, 10) }); toastOk('Now counted against ' + sel.selectedOptions[0].text + '.'); stockForgetAll(); }
                        catch (e) { toastError(e.message); }
                    };
                    against.append(sel);
                } else against.textContent = filled.length ? filled.map(orderName).join(', ') : 'no open order';
                tr.append(n, el('td', 'num', String(l.qty)), el('td', 'num', it ? String(it.current) : ''), against);
                t.add(tr);
            });
            win.body.append(t.wrap);
            const foot = win.foot();
            if (d.invoice_no) {
                const undo = textButton('Undo this delivery', { icon: I.history, cls: 'sd-foot-start' }); undo.type = 'button';
                undo.onclick = async () => {
                    const yes = await uiConfirm('Undo delivery ' + d.invoice_no + '? The quantities come back off stock, and the orders it filled await them again.',
                        { title: 'Undo this delivery', okText: 'Undo delivery', danger: true });
                    if (!yes) return;
                    setBusy(undo, true);
                    try {
                        const r = await stockRead('receive', 'undo', { invoice_no: d.invoice_no });
                        win.close(); toastOk('Undid ' + d.invoice_no + ': ' + stockDelPlural(r.units, 'unit') + ' taken back off stock.');
                        stockDelAfterWrite();
                    } catch (e) { setBusy(undo, false); toastError(e.message); }
                };
                foot.append(undo);
            }
            const done = textButton('Done', { kind: 'primary' }); done.type = 'button'; done.onclick = () => win.close();
            foot.append(done);
        }
        /* One line taken in, with its invoice number and date. A repeat
           invoice for the same line is refused by the server, and says so. */
        function openStockReceiveOne(item, opener) {
            const name = stockName(item);
            const win = dialog({ title: 'Receive stock', opener: opener, size: 'sd-one-win' });
            const qty = stockDelInput('number', item.suggested_qty || item.reorder_qty || 1);
            qty.min = '1';
            const inv = stockDelInput('text', '', null, 'For example INV-1043');
            const now = new Date();
            const dt = stockDelInput('text', '', null, now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0') + '-' + String(now.getDate()).padStart(2, '0'));
            const form = el('div', 'sd-form sd-form-one');
            form.append(formField('Receiving into', el('strong', 'sd-into', name)), formField('Quantity received', qty),
                formField('Invoice no. (optional)', inv), formField('Date (optional)', dt));
            win.body.append(form);
            const foot = win.foot();
            const no = textButton('Cancel'); no.type = 'button'; no.onclick = () => win.close();
            const go = textButton('Confirm receipt', { kind: 'primary' }); go.type = 'button';
            foot.append(no, go);
            go.onclick = async () => {
                const q = stockDelQty(qty.value);
                if (!q) { toastError('Enter a quantity.'); return; }
                setBusy(go, true);
                try {
                    const d = await stockRead('receive', 'one', { id: item.id, qty: q, invoice_no: inv.value.trim(), date: dt.value.trim() });
                    win.close();
                    const filled = ((d.receipt && d.receipt.lines && d.receipt.lines[0] && d.receipt.lines[0].orders) || []).length;
                    toastOk('Received ' + q + ' into ' + name + (filled ? ', counted against its open order.' : '.'));
                    stockDelAfterWrite();
                } catch (e) { setBusy(go, false); toastError(e.message); }
            };
            qty.focus(); qty.select();
        }
