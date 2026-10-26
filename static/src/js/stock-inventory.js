        /* ---------- Stock: Inventory ----------
           The stock list as the stock app's Inventory has it, drawn with
           Reactor's parts: its six actions, its filters, the list grouped or
           flat with every figure editable in place, workshop counting on a
           phone with tally scanning, adding a line, importing and exporting
           the sheet, shelf labels and the guided stock-take. Every write goes
           to the sheet's own ops on /api/stock/sheet. Two flaws are fixed on
           the way: saving one row keeps the unsaved edits in the others
           (design 4.1), and a label scanned while the full list is showing
           turns the count cards on, so its count is never a hidden draft
           (design 4.8). */

        /* Other sections' functions, when they are in the page: the item's
           history (Overview's), receiving (Deliveries'), and the reader, the
           beep and the buzz (the camera test's).
           Looked up rather than called blind, so a missing one does nothing. */
        function stockInvOther(name) {
            const have = {
                openStockHistory: typeof openStockHistory === 'function' ? openStockHistory : null,
                openStockReceive: typeof openStockReceive === 'function' ? openStockReceive : null,
                openStockReceiveOne: typeof openStockReceiveOne === 'function' ? openStockReceiveOne : null,
            };
            return have[name] || null;
        }
        /* What the list shows, kept while the page is open: the filters, the
           sort, the unsaved edits by line (id to field to what was typed), the
           workshop counts not yet saved (id to count) and the shelf's figure
           each count began from (id to figure). */
        const stockInv = { q: '', cat: 'all', watt: 'all', status: 'active', grouped: true, sortK: 'size', sortDir: -1,
                           edits: {}, counts: null, from: {}, told: false, pane: null };
        /* Kept in this browser only, as the stock app keeps them: the workshop
           switch, the counts not yet saved (with where each began) and a
           paused stock-take. */
        const STOCK_INV_KEEP = { workshop: 'reactor_stock_workshop', counts: 'reactor_stock_counts', take: 'reactor_stock_take',
                                 from: 'reactor_stock_counts_from' };
        function stockInvKeep(key, value) {
            try { if (value == null) localStorage.removeItem(key); else localStorage.setItem(key, JSON.stringify(value)); }
            catch (e) { /* a private window: kept for this page only */ }
        }
        function stockInvKept(key) {
            try { const raw = localStorage.getItem(key); return raw ? JSON.parse(raw) : null; } catch (e) { return null; }
        }
        const STOCK_INV_PHONE = window.matchMedia ? window.matchMedia('(max-width: 640px)') : null;
        /* Workshop mode is on by default at a phone's width, and either way
           once someone has chosen. */
        function stockInvWorkshop() {
            const o = stockInvKept(STOCK_INV_KEEP.workshop);
            return o === true || o === false ? o : !!(STOCK_INV_PHONE && STOCK_INV_PHONE.matches);
        }
        const STOCK_INV_CATS = ['Glass', 'Rings', 'Projector', 'Accessories'];
        /* The columns, in the stock app's order. edit: how the cell is edited;
           sort: the flat list sorts by it. */
        const STOCK_INV_COL = {
            category: { head: 'Category', sort: 1 }, colour: { head: 'Colour or type', sort: 1 },
            size: { head: 'Size', sort: 1 },
            current: { head: 'Current', num: 1, edit: 'int', sort: 1 }, used: { head: 'Used', num: 1, edit: 'int', sort: 1 },
            cover: { head: 'Cover', num: 1, sort: 1 },
            reorder_point: { head: 'Reorder at or below', num: 1, edit: 'int', sort: 1 },
            reorder_qty: { head: 'Order qty', num: 1, edit: 'int', sort: 1 },
            unit_cost_gbp: { head: 'Unit £', num: 1, edit: 'money', sort: 1 },
            current_value: { head: 'Value', num: 1, sort: 1 },
            barcode: { head: 'Barcode', edit: 'text' }, supplier: { head: 'Supplier', edit: 'text', sort: 1 },
            currency: { head: 'Currency', edit: 'text', sort: 1 }, written_off: { head: 'Written off', edit: 'bool' },
            acts: { head: '' } };
        const STOCK_INV_GROUPED = ['size', 'current', 'used', 'cover', 'reorder_point', 'reorder_qty', 'unit_cost_gbp',
                                   'current_value', 'supplier', 'currency', 'written_off', 'acts'];
        const STOCK_INV_FLAT = ['category', 'colour', 'size', 'current', 'used', 'cover', 'reorder_point', 'reorder_qty',
                                'unit_cost_gbp', 'barcode', 'supplier', 'currency', 'written_off', 'acts'];

        /* A line's name as its shelf label says it: "20mm Opal 9",
           "86 mm ring", "LED300 · Black", "Lens 30 degree". */
        function stockInvTitle(it) {
            const sc = stockSize(it);
            if (it.category === 'Glass') { const n = stockNum(it.size); return (n != null ? n + 'mm' : (it.size || '')) + (it.sub_category ? ' ' + it.sub_category : ''); }
            if (it.category === 'Rings') return sc.main + ' ring';
            if (it.category === 'Projector') return sc.main;
            return (it.sub_category ? it.sub_category + ' ' : '') + sc.main;
        }
        /* The same line named for a screen reader and a toast: colour first. */
        function stockInvName(it) { return stockName(it); }   // one name for a line on every tab (stock.js)
        function stockInvRows(items) {
            const q = stockInv.q.trim().toLowerCase();
            /* A whole label code (CL and its id, or a barcode) finds its one line, as a scan does:
               "CL2" is not also CL20 to CL29. */
            const coded = q && (/^cl\d+$/.test(q) || items.some(i => (i.barcode || '').trim().toLowerCase() === q))
                ? stockByCode(items, q) : null;
            return items.filter(r => {
                if (coded) return r === coded;
                if (stockInv.status === 'active' && r.written_off) return false;
                if (stockInv.status === 'wo' && !r.written_off) return false;
                if (stockInv.cat !== 'all' && r.category !== stockInv.cat) return false;
                if (stockInv.watt !== 'all' && r.category === 'Projector' && String(stockWatt(r)) !== stockInv.watt) return false;
                if (q) {
                    const hay = [r.category, r.name, stockSizeText(r), r.notes, r.supplier, r.currency, r.barcode, 'CL' + r.id]
                        .join(' ').toLowerCase();
                    if (hay.indexOf(q) < 0) return false;
                }
                return true;
            });
        }
        function stockInvSortVal(r, k) {
            if (k === 'cover') return stockCover(r);
            if (k === 'size') { const s = stockSortSize(r); return s == null ? -Infinity : s; }
            if (k === 'colour') return r.sub_category || '';
            return r[k];
        }
        function stockInvSort(rows, k, dir) {
            return rows.slice().sort((a, b) => {
                let x = stockInvSortVal(a, k), y = stockInvSortVal(b, k);
                if (typeof x === 'string' || typeof y === 'string') return dir * String(x || '').localeCompare(String(y || ''));
                x = x == null ? -Infinity : x; y = y == null ? -Infinity : y;
                if (x === y) return String(a.sub_category + ' ' + a.size).localeCompare(String(b.sub_category + ' ' + b.size));
                return dir * (x > y ? 1 : -1);
            });
        }
        /* The groups' lines by size, largest first unless the Size head is turned. */
        function stockInvGroups(rows, sheet) {
            return stockGroups(rows, sheet.glass_families).map(g => Object.assign(g, { items: stockInvSort(g.items, 'size', stockInv.sortDir) }));
        }
        const stockInvNoun = (c, n) => (c === 'Glass' ? 'size' : c === 'Rings' ? 'ring' : c === 'Projector' ? 'variant' : 'item') + (n === 1 ? '' : 's');
        const stockInvCover = (it) => it.used > 0 ? (it.current / it.used).toFixed(1) + 'q' : 'No use';

        /* ---- the tab ---- */
        function renderStockInventory(host) {
            /* The item sheet's Correct count opens the list searching for its line. */
            if (stockInvQuery) { stockInv.q = stockInvQuery; stockInvQuery = ''; }
            stockLoad(host, [stockSheet], (sheet) => stockInvDraw(host, sheet));
        }
        /* The counts not yet saved come back from this browser once, when the
           list is first drawn, with the toast that says so, each with the
           figure the shelf showed when it began (stockInv.from). */
        function stockInvCounts(sheet) {
            if (stockInv.counts) return stockInv.counts;
            const kept = stockInvKept(STOCK_INV_KEEP.counts) || {}, keptFrom = stockInvKept(STOCK_INV_KEEP.from) || {};
            const byId = {}, now = {}, from = {};
            sheet.items.forEach(i => { byId[i.id] = i; });
            Object.keys(kept).forEach(id => {
                const it = byId[id], v = parseInt(kept[id], 10), f = parseInt(keptFrom[id], 10);
                if (it && isFinite(v) && v >= 0 && v !== it.current) { now[id] = v; if (isFinite(f)) from[id] = f; }
            });
            stockInv.counts = now; stockInv.from = from;
            stockInvKeep(STOCK_INV_KEEP.counts, Object.keys(now).length ? now : null);
            stockInvKeep(STOCK_INV_KEEP.from, Object.keys(from).length ? from : null);
            const n = Object.keys(now).length;
            if (n && !stockInv.told) addToast(n + ' unsaved count' + (n === 1 ? '' : 's') + ' restored');
            stockInv.told = true;
            return now;
        }
        function stockInvDraw(host, sheet) {
            const items = sheet.items || [];
            stockInvCounts(sheet);
            const panel = el('div', 'card stk-inv');
            const head = el('div', 'card-head');
            const title = el('h3', 'card-title', 'Inventory');
            const about = infoButton('About editing the stock list', { title: 'Editing the stock list', body: [
                'Edit any figure inline, then press Save on that row. A box left blank keeps its figure: type 0 for none.',
                'Count corrections are recorded in Activity and in the figures over time.',
                'Lowering Current here is a correction, not usage. Usage is recorded by workshop counts, by a stock-take counted as stock sold or used, and by production bookings.'] });
            head.append(titleInfo(title, about));
            head.append(stockInvActions(sheet));
            panel.append(head);
            const tools = stockInvTools(sheet);
            panel.append(tools);
            const watts = el('div', 'stk-watts');
            panel.append(watts);
            const note = el('div', 'stk-inv-note');
            /* Classless, so the table in it runs to the panel's edges. */
            const body = el('div');
            const foot = el('div', 'tbl-foot stk-inv-foot');
            panel.append(note, body, foot);
            host.append(panel);
            /* The file chooser Import opens: an input, so not a panel. */
            stockInv.pane = { host, panel, watts, note, body, foot, sheet };
            stockInvPaint();
        }
        /* The six actions, in the stock app's order: words on a desk, the
           same six as icons on a phone. Receive stock is the deliveries' own. */
        function stockInvActions(sheet) {
            const act = el('div', 'card-act stk-acts');
            const file = el('input', 'stk-file');
            file.type = 'file'; file.accept = '.csv,text/csv'; file.hidden = true;
            file.setAttribute('aria-label', 'The stock sheet to import');
            file.onchange = async () => {
                const f = file.files && file.files[0]; file.value = '';
                if (!f) return;
                let text = '';
                try { text = await f.text(); } catch (e) { toastError('That file could not be read.'); return; }
                stockInvImport(text, f.name, imp);
            };
            const go = {
                add: (b) => stockInvAdd(b),
                imp: () => file.click(),
                exp: (b) => stockInvExport(b),
                lbl: (b) => stockInvLabels(b),
                take: (b) => stockInvTake(b),
                rcv: (b) => { const open = stockInvOther('openStockReceive'); if (open) open(b); },
            };
            const ACTS = [['add', 'Add item', I.plus], ['imp', 'Import', I.upload], ['exp', 'Export', I.download],
                          ['lbl', 'Labels', I.printer], ['take', 'Stock-take', I.clipboardCheck], ['rcv', 'Receive stock', I.truck]];
            let imp = null;
            ACTS.forEach(([k, words, icon]) => {
                const b = textButton(words, { icon: icon, cls: 'stk-act-word' });
                b.type = 'button'; b.onclick = () => go[k](b);
                const s = iconButton(icon, words, { cls: 'stk-act-icon' });
                s.type = 'button'; s.onclick = () => go[k](s);
                if (k === 'imp') imp = b;
                act.append(b, s);
            });
            act.append(file);
            return act;
        }
        /* Search, the category, the status, grouped or flat, and the workshop
           switch. On a phone the camera sits beside the search. */
        function stockInvTools(sheet) {
            const items = sheet.items || [];
            const search = tableSearch('Search colour, size, supplier or code', stockInv.q, (v) => { stockInv.q = v; stockInvPaint(); });
            search.classList.add('stk-search');
            const scan = iconButton(I.camera, 'Scan labels to count', { cls: 'stk-scan-btn' });
            scan.type = 'button'; scan.onclick = () => stockInvScanToCount(scan);
            const find = el('div', 'stk-find'); find.append(search, scan);
            const cats = ['all'].concat(STOCK_INV_CATS.filter(c => items.some(i => i.category === c)),
                [...new Set(items.map(i => i.category))].filter(c => STOCK_INV_CATS.indexOf(c) < 0).sort());
            const catSeg = segmented(cats.map(c => [c, c === 'all' ? 'All' : c]).sort((a, b) => a[0] === 'all' ? -1 : b[0] === 'all' ? 1 : a[1].localeCompare(b[1])),
                stockInv.cat, (k) => { stockInv.cat = k; stockInv.watt = 'all'; stockInvPaint(); }, { label: 'Category' });
            const catWrap = el('div', 'stk-cats'); catWrap.append(catSeg);
            const status = choiceSelect([['active', 'Active only'], ['all', 'All lines'], ['wo', 'Written off']], stockInv.status,
                (k) => { stockInv.status = k; stockInvPaint(); }, { label: 'Status' });
            const layout = segmented([['grouped', 'Grouped'], ['flat', 'Flat']], stockInv.grouped ? 'grouped' : 'flat', (k) => {
                stockInv.grouped = k === 'grouped';
                stockInv.sortK = 'size'; stockInv.sortDir = -1;
                stockInvPaint();
            }, { label: 'Layout' });
            layout.classList.add('stk-layout');
            const shop = switchBtn('Workshop mode', stockInvWorkshop(), (on) => { stockInvKeep(STOCK_INV_KEEP.workshop, on); stockInvPaint(); });
            shop.classList.add('stk-shop');
            shop.title = 'Count cards with plus and minus, for counting on a phone';
            return tableTools([find, catWrap], [status, layout, shop]);
        }
        /* Everything under the filters: the projector's wattages, the notice of
           counts not yet saved, the list or the count cards, and the foot. */
        function stockInvPaint() {
            const P = stockInv.pane;
            if (!P || !P.panel.isConnected) return;
            const sheet = P.sheet, items = sheet.items || [];
            const workshop = stockInvWorkshop();
            P.panel.classList.toggle('stk-workshop', workshop);
            P.watts.innerHTML = '';
            if (stockInv.cat === 'Projector') {
                const watts = [...new Set(items.filter(i => i.category === 'Projector').map(stockWatt).filter(w => w != null))].sort((a, b) => b - a);
                P.watts.append(segmented([['all', 'All wattages']].concat(watts.map(w => [String(w), w + 'W'])), stockInv.watt,
                    (k) => { stockInv.watt = k; stockInvPaint(); }, { label: 'Wattage' }));
            }
            P.watts.hidden = stockInv.cat !== 'Projector';
            const rows = stockInvRows(items);
            const pending = Object.keys(stockInv.counts || {}).length;
            P.note.innerHTML = '';
            P.note.hidden = !(pending && !workshop);
            if (pending && !workshop) {
                /* Counts are never left in a draft nobody can see (design 4.8). */
                const msg = el('div', 'resp-note stk-pending');
                msg.append(el('span', null, pending + ' count' + (pending === 1 ? '' : 's') + ' not saved yet.'));
                const show = textLink('Show the counts', { size: 'inline' }); show.type = 'button';
                show.onclick = () => { stockInvKeep(STOCK_INV_KEEP.workshop, true); stockInvRedrawTools(); };
                msg.append(show);
                P.note.append(msg);
            }
            P.body.innerHTML = '';
            if (!rows.length) {
                P.body.append(emptyState({ icon: I.search, text: items.length ? 'No lines match.' : 'No stock lines yet.' }));
            } else if (workshop) P.body.append(stockInvCards(rows, sheet));
            else P.body.append(stockInvTable(rows, sheet));
            const value = rows.reduce((s, r) => s + (r.current_value || 0), 0);
            P.foot.innerHTML = '';
            P.foot.append(el('div', 'tbl-count', rows.length + ' of ' + items.length + ' lines' + (workshop ? '' : ' · ' + stockGbp(value) + ' value shown')));
            /* The bar is the panel's last child, so it can ride at the foot of the screen down the whole list. */
            P.panel.querySelectorAll(':scope > .stk-savebar').forEach(n => n.remove());
            if (workshop) { P.panel.append(stockInvSaveBar()); stockInvKeepAwake(true); }
            else stockInvKeepAwake(false);
        }
        /* The workshop switch lives in the tools, so turning it from elsewhere draws them again. */
        function stockInvRedrawTools() {
            const P = stockInv.pane;
            if (!P || !P.panel.isConnected) return;
            const old = P.panel.querySelector('.tbl-tools');
            if (old) old.replaceWith(stockInvTools(P.sheet));
            stockInvPaint();
        }

        /* ---- the list: grouped or flat, every figure editable ---- */
        function stockInvHead(k) {
            const c = STOCK_INV_COL[k];
            const can = stockInv.grouped ? k === 'size' : !!c.sort;
            if (!can) return c.head;
            const b = textButton(c.head, { kind: 'ghost', cls: 'stk-sort' + (stockInv.sortK === k ? ' on' : '') });
            b.type = 'button';
            if (stockInv.sortK === k) { const a = ico(I.arrowDown); if (stockInv.sortDir > 0) a.classList.add('stk-up'); b.append(a); }
            b.onclick = () => {
                if (stockInv.sortK === k) stockInv.sortDir *= -1;
                else { stockInv.sortK = k; stockInv.sortDir = c.num || k === 'size' ? -1 : 1; }
                stockInvPaint();
            };
            return b;
        }
        function stockInvTable(rows, sheet) {
            const grouped = stockInv.grouped;
            const cols = grouped ? STOCK_INV_GROUPED : STOCK_INV_FLAT;
            const main = grouped ? 'size' : 'colour';
            const t = dataTable(cols.map(k => [stockInvHead(k), [STOCK_INV_COL[k].num ? 'num' : '', k === main ? 'kt-main' : '', 'stk-c-' + k].filter(Boolean).join(' ')]),
                { cls: 'stk-inv-table ' + (grouped ? 'stk-grouped' : 'stk-flat'), wrap: 'stk-inv-wrap' });
            cols.forEach((k, i) => {
                if (stockInv.sortK === k && (grouped ? k === 'size' : STOCK_INV_COL[k].sort)) t.heads[i].setAttribute('aria-sort', stockInv.sortDir < 0 ? 'descending' : 'ascending');
            });
            if (grouped) {
                stockInvGroups(rows, sheet).forEach(g => {
                    const units = g.items.reduce((s, r) => s + r.current, 0), val = g.items.reduce((s, r) => s + (r.current_value || 0), 0);
                    const tr = el('tr', 'stk-grp'), td = el('td');
                    td.colSpan = cols.length;
                    const line = el('div', 'stk-grp-line');
                    line.append(stockDot(g.items[0]), el('span', 'stk-grp-name', g.label),
                        el('span', 'stk-grp-stat', g.category + ' · ' + g.items.length + ' ' + stockInvNoun(g.category, g.items.length)
                            + ' · ' + units + (units === 1 ? ' unit · ' : ' units · ') + stockGbp(val)));
                    td.append(line); tr.append(td); t.add(tr);
                    g.items.forEach(it => t.add(stockInvRow(it, cols)));
                });
            } else {
                stockInvSort(rows, stockInv.sortK, stockInv.sortDir).forEach(it => t.add(stockInvRow(it, cols)));
            }
            return t.wrap;
        }
        function stockInvRow(it, cols) {
            const tr = el('tr', it.written_off ? 'stk-wo' : null);
            tr.dataset.id = String(it.id);
            // Teal, as the stock sheet's Save is today (Cameron's call 6, 26 Oct 2026).
            const save = textButton('Save', { kind: 'primary', cls: 'stk-save' });
            save.type = 'button';
            save.onclick = () => stockInvSave(it, tr, save);
            cols.forEach(k => tr.append(stockInvCell(it, k, tr, save)));
            stockInvMarkRow(it, tr, save);
            return tr;
        }
        function stockInvMarkRow(it, tr, save) {
            const edited = !!(stockInv.edits[it.id] && Object.keys(stockInv.edits[it.id]).length);
            tr.classList.toggle('stk-row-edited', edited);
            save.hidden = !edited;
        }
        /* A changed box is kept by its line, so drawing the list again (a
           filter, a sort, another row's save) keeps it (design 4.1). */
        function stockInvNote(it, f, value, seen, tr, save, ctl) {
            const e = stockInv.edits[it.id] || (stockInv.edits[it.id] = {});
            if (value === seen) delete e[f]; else e[f] = value;
            if (!Object.keys(e).length) delete stockInv.edits[it.id];
            if (ctl) { ctl.classList.toggle('stk-edited', value !== seen); ctl.removeAttribute('aria-invalid'); }
            stockInvMarkRow(it, tr, save);
        }
        function stockInvCell(it, k, tr, save) {
            const c = STOCK_INV_COL[k];
            const td = el('td', c.num ? 'num' : null);
            if (k === 'category') { td.append(el('span', 'lbl-chip', it.category)); return td; }
            if (k === 'colour') { td.append(el('span', 'stk-colour', it.sub_category || '')); return td; }
            if (k === 'size') {
                const sc = stockSize(it);
                td.append(el('span', 'stk-size', sc.main));
                if (sc.sub) td.append(el('span', 'stk-size-sub', sc.sub));
                if (it.written_off) td.append(el('span', 'lbl-chip stk-wo-tag', 'Written off'));
                return td;
            }
            if (k === 'cover') { td.textContent = stockInvCover(it); if (!(it.used > 0)) td.classList.add('stk-muted'); return td; }
            if (k === 'current_value') { td.textContent = stockGbp(it.current_value || 0); return td; }
            if (k === 'acts') {
                td.classList.add('stk-acts-cell');
                const rcv = iconButton(I.box, 'Receive stock: ' + stockInvName(it), { title: 'Receive stock' });
                rcv.type = 'button';
                rcv.onclick = () => { const open = stockInvOther('openStockReceiveOne'); if (open) open(it, rcv); };
                const hist = iconButton(I.history, 'History: ' + stockInvName(it), { title: 'History' });
                hist.type = 'button';
                hist.onclick = () => { const open = stockInvOther('openStockHistory'); if (open) open(it, hist); };
                const box = el('div', 'stk-row-acts'); box.append(save, rcv, hist);
                td.append(box);
                return td;
            }
            const pend = stockInv.edits[it.id] ? stockInv.edits[it.id][k] : undefined;
            if (c.edit === 'bool') {
                const seen = !!it[k];
                const sw = switchBtn('', pend !== undefined ? pend : seen, (on) => stockInvNote(it, k, on, seen, tr, save, sw));
                sw.setAttribute('aria-label', 'Written off: ' + stockInvName(it));
                sw.classList.add('stk-wo-switch');
                if (pend !== undefined) sw.classList.add('stk-edited');
                td.append(sw);
                return td;
            }
            if (c.edit) {
                const seen = it[k] == null ? '' : String(it[k]);
                const inp = el('input', 'stk-cell-in stk-in-' + k + (c.edit === 'text' ? ' stk-txt' : ' stk-num'));
                inp.type = 'text'; inp.dataset.f = k;
                if (c.edit !== 'text') inp.inputMode = 'decimal';
                inp.value = pend !== undefined ? pend : seen;
                inp.setAttribute('aria-label', c.head + ': ' + stockInvName(it));
                if (pend !== undefined) inp.classList.add('stk-edited');
                if (c.edit === 'text' && inp.value) inp.title = inp.value;
                inp.oninput = () => stockInvNote(it, k, inp.value, seen, tr, save, inp);
                inp.onkeydown = (e) => { if (e.key === 'Enter' && !save.hidden) save.click(); };
                td.append(inp);
                return td;
            }
            td.textContent = it[k] == null ? '' : String(it[k]);
            return td;
        }
        /* A number as the stock app took it: "1,200", "£12.50" and " 40 " are
           numbers; anything else is refused, never read as 0. */
        function stockInvNumber(raw) {
            const s = String(raw == null ? '' : raw).replace(/[£$€,\s]/g, '');
            if (s === '') return { empty: true };
            if (!/^\d+(\.\d+)?$/.test(s)) return { bad: true };
            const n = parseFloat(s);
            return isFinite(n) ? { value: n } : { bad: true };
        }
        async function stockInvSave(it, tr, save) {
            const typed = stockInv.edits[it.id] || {};
            const changes = {}, seen = {};
            let bad = null;
            Object.keys(typed).forEach(f => {
                const c = STOCK_INV_COL[f];
                let v = typed[f];
                if (c.edit === 'int' || c.edit === 'money') {
                    const p = stockInvNumber(v);
                    if (p.bad) { bad = bad || f; return; }
                    if (p.empty) return;   /* a cleared box leaves the figure alone */
                    v = c.edit === 'int' ? Math.round(p.value) : p.value;
                } else if (c.edit === 'text') v = String(v).trim();
                const was = it[f] == null ? (c.edit === 'text' ? '' : 0) : it[f];
                if (String(v) !== String(was)) { changes[f] = v; seen[f] = it[f] == null ? '' : it[f]; }
            });
            if (bad) {
                const inp = tr.querySelector('input[data-f="' + bad + '"]');
                if (inp) { markInvalid(inp, true); inp.focus(); inp.select(); }
                toastError('Check the highlighted box: numbers only, such as 1200 or 12.50.');
                return;
            }
            if (!Object.keys(changes).length) { delete stockInv.edits[it.id]; stockInvPaint(); return; }
            const before = {}, after = {};
            Object.keys(changes).forEach(f => { before[f] = it[f] == null ? '' : it[f]; after[f] = changes[f]; });
            const words = Object.keys(changes).map(f => STOCK_INV_COL[f].head).join(', ');
            setBusy(save, true);
            try {
                const d = await stockRead('sheet', 'edit', { id: it.id, changes: changes, seen: seen });
                Object.assign(it, d.item);
                if (d.summary) stockInv.pane.sheet.summary = d.summary;
                delete stockInv.edits[it.id];
                stockInvChanged();
                addToast('Saved · ' + words, 'good', { action: { label: 'Undo', fn: () => stockInvUndo(it, before, after, words) } });
            } catch (e) {
                setBusy(save, false);
                toastError(e.message || 'That could not be saved.');
            }
        }
        /* Undo posts the old figures back as an edit of its own, so the
           history keeps both. */
        async function stockInvUndo(it, before, after, words) {
            try {
                const d = await stockRead('sheet', 'edit', { id: it.id, changes: before, seen: after });
                Object.assign(it, d.item);
                stockInvChanged();
                addToast('Put ' + words + ' back');
            } catch (e) { toastError(e.message || 'That could not be undone.'); }
        }
        /* After a write: the list again (keeping every unsaved box), and the
           tab bar's counts, which the warnings and the reorder list carry. */
        function stockInvChanged() {
            stockInvPaint();
            stockForget('alerts', 'reorder');
            Promise.all([stockAlerts(), stockReorderList()]).then(renderStockHead)
                .catch(e => console.warn('stock: the tab counts were not read again', e));
        }
        /* A write that changed many lines (an import, counts, a stock-take,
           a new line): the sheet is read again. */
        function stockInvReload() {
            stockForget('sheet', 'alerts', 'reorder');
            stockSeg = 'inventory';
            renderStock();
            Promise.all([stockAlerts(), stockReorderList()]).then(renderStockHead)
                .catch(e => console.warn('stock: the tab counts were not read again', e));
        }

        /* ---- workshop mode: counting on a phone ---- */
        function stockInvPending(it) {
            const c = stockInv.counts || {};
            return Object.prototype.hasOwnProperty.call(c, it.id) ? c[it.id] : it.current;
        }
        /* A count, and the shelf's figure when it began: the first change keeps
           it, so the server can refuse a count of a line changed since. */
        function stockInvSetCount(it, v) {
            v = Math.max(0, Math.min(2147483647, Math.round(v || 0)));
            if (v === it.current) { delete stockInv.counts[it.id]; delete stockInv.from[it.id]; }
            else { if (!(it.id in stockInv.from)) stockInv.from[it.id] = it.current; stockInv.counts[it.id] = v; }
            const n = Object.keys(stockInv.counts).length;
            stockInvKeep(STOCK_INV_KEEP.counts, n ? stockInv.counts : null);
            stockInvKeep(STOCK_INV_KEEP.from, n ? stockInv.from : null);
            return v;
        }
        function stockInvCards(rows, sheet) {
            const list = el('div', 'stk-count');
            stockInvGroups(rows, sheet).forEach(g => {
                const units = g.items.reduce((s, r) => s + stockInvPending(r), 0);
                const h = el('div', 'stk-count-head');
                h.append(stockDot(g.items[0]), el('span', 'stk-count-label', g.label), el('span', 'stk-count-n', g.items.length + ' · ' + units + (units === 1 ? ' unit' : ' units')));
                list.append(h);
                g.items.forEach(it => list.append(stockInvCard(it, {
                    value: () => stockInvPending(it),
                    sub: [stockSize(it).sub, it.written_off ? 'written off' : ''].filter(Boolean).join(' · '),
                    set: (v, card) => {
                        const now = stockInvSetCount(it, v);
                        card.classList.toggle('stk-dirty', Object.prototype.hasOwnProperty.call(stockInv.counts, it.id));
                        stockInvBar();
                        return now;
                    } })));
            });
            return list;
        }
        /* One counter card: the dot, the name, and minus, the count and plus.
           Holding a button repeats it (after 0.42s, every 0.12s); tapping the
           count selects it all, so typing replaces it. o.value() is the count
           now, o.set(v, card) keeps one and answers what was kept. */
        function stockInvCard(it, o) {
            const name = stockSize(it).main;
            const card = el('div', 'stk-card' + (Object.prototype.hasOwnProperty.call(stockInv.counts || {}, it.id) && !o.take ? ' stk-dirty' : '') + (it.written_off ? ' stk-wo' : ''));
            card.dataset.id = String(it.id);
            const txt = el('div', 'stk-card-main');
            txt.append(el('div', 'stk-card-name', name));
            const sub = el('div', 'stk-card-sub', o.sub || '');
            sub.hidden = !o.sub;
            txt.append(sub);
            const minus = iconButton(I.minus, 'One fewer: ' + stockInvName(it), { cls: 'stk-step' });
            const plus = iconButton(I.plus, 'One more: ' + stockInvName(it), { cls: 'stk-step' });
            const val = el('input', 'stk-val');
            val.type = 'text'; val.inputMode = 'numeric';
            val.value = String(o.value());
            val.setAttribute('aria-label', 'Count: ' + stockInvName(it));
            const step = (d) => { val.value = String(o.set(o.value() + d, card)); };
            [[minus, -1], [plus, 1]].forEach(([b, d]) => {
                b.type = 'button';
                let wait = null, every = null;
                const stop = () => { clearTimeout(wait); clearInterval(every); wait = every = null; };
                b.addEventListener('pointerdown', (e) => {
                    e.preventDefault();
                    step(d);
                    wait = setTimeout(() => { every = setInterval(() => step(d), 120); }, 420);
                });
                ['pointerup', 'pointerleave', 'pointercancel'].forEach(ev => b.addEventListener(ev, stop));
                /* A key press (Enter or Space) clicks with no pointer behind it. */
                b.addEventListener('click', (e) => { if (e.detail === 0) step(d); });
            });
            val.oninput = () => { o.set(parseInt(val.value.replace(/[^0-9]/g, '') || '0', 10), card); };
            val.onchange = () => { val.value = String(o.value()); };
            /* Select the number to type over it, unless focus has moved on meanwhile (select() would take it back). */
            val.addEventListener('focus', () => setTimeout(() => { if (document.activeElement === val) val.select(); }, 0));
            const stepper = el('div', 'stk-stepper');
            stepper.append(minus, val, plus);
            card.append(stockDot(it), txt, stepper);
            card.stkSub = sub;
            return card;
        }
        /* The bar under the cards: Save N counts and Discard, while there are any. */
        function stockInvSaveBar() {
            const bar = el('div', 'stk-savebar');
            const save = textButton('', { kind: 'primary', icon: I.check, cls: 'stk-save-counts' });
            save.type = 'button';
            save.onclick = () => stockInvSaveCounts(save);
            const drop = textButton('Discard');
            drop.type = 'button';
            drop.onclick = async () => {
                if (!await uiConfirm('Discard the counts you have entered but not saved?', { title: 'Discard counts', okText: 'Discard' })) return;
                stockInv.counts = {}; stockInv.from = {};
                stockInvKeep(STOCK_INV_KEEP.counts, null); stockInvKeep(STOCK_INV_KEEP.from, null);
                stockInvPaint();
            };
            bar.append(drop, save);
            stockInv.bar = { bar, save };
            stockInvBar();
            return bar;
        }
        function stockInvBar() {
            const B = stockInv.bar;
            if (!B) return;
            const n = Object.keys(stockInv.counts || {}).length;
            B.bar.hidden = !n;
            B.save.lastChild.textContent = 'Save ' + n + ' count' + (n === 1 ? '' : 's');
            /* The group heads carry their units as counted. */
            const P = stockInv.pane;
            if (P) P.body.querySelectorAll('.stk-count-head').forEach(h => {
                let units = 0, lines = 0;
                for (let c = h.nextElementSibling; c && c.classList.contains('stk-card'); c = c.nextElementSibling) {
                    const it = P.sheet.items.find(i => String(i.id) === c.dataset.id);
                    if (it) { units += stockInvPending(it); lines++; }
                }
                h.querySelector('.stk-count-n').textContent = lines + ' · ' + units + (units === 1 ? ' unit' : ' units');
            });
        }
        /* All or nothing, in one go: a count that drops is recorded as usage.
           If it fails the counts stay, here and in this browser. */
        async function stockInvSaveCounts(btn) {
            const entries = Object.keys(stockInv.counts || {});
            if (!entries.length) return;
            setBusy(btn, true);
            try {
                const d = await stockRead('sheet', 'counts', { counts: entries.map(id => {
                    const c = { id: Number(id), current: stockInv.counts[id] };
                    if (stockInv.from[id] != null) c.seen = stockInv.from[id];
                    return c;
                }) });
                stockInv.counts = {}; stockInv.from = {};
                stockInvKeep(STOCK_INV_KEEP.counts, null); stockInvKeep(STOCK_INV_KEEP.from, null);
                addToast('Saved ' + d.saved + ' count' + (d.saved === 1 ? '' : 's'), 'good');
                stockInvReload();
            } catch (e) {
                setBusy(btn, false);
                toastError((e.message || 'The counts could not be saved.') + ' Your counts are still here: press Save to try again.');
                if (!e.noReply) await stockInvRebase();
            }
        }
        /* After a refused save the counts stay as typed, and a line someone
           changed since takes the shelf's figure now as where its count began:
           the refusal named it, so the next Save keeping the count is the
           person's own choice. A dropped connection takes nothing new. */
        async function stockInvRebase() {
            let sheet;
            try { stockForget('sheet'); sheet = await stockSheet(); } catch (e) { return; }
            const byId = {};
            (sheet.items || []).forEach(i => { byId[i.id] = i; });
            Object.keys(stockInv.counts || {}).forEach(id => { if (byId[id] && id in stockInv.from) stockInv.from[id] = byId[id].current; });
            stockInvKeep(STOCK_INV_KEEP.from, Object.keys(stockInv.from).length ? stockInv.from : null);
            stockInvReload();
        }
        /* The screen stays awake while the count cards or the camera are open,
           and is let go as soon as neither is. */
        let stockInvWake = null, stockInvWakeWatch = null;
        function stockInvCounting() {
            return !!document.querySelector('#view-stock.active .stk-workshop .stk-count, .stk-scan-ov, .stk-take-ov');
        }
        async function stockInvKeepAwake(on) {
            try {
                if (on && !stockInvWake && navigator.wakeLock) {
                    stockInvWake = await navigator.wakeLock.request('screen');
                    stockInvWake.addEventListener('release', () => { stockInvWake = null; });
                } else if (!on && stockInvWake) { const w = stockInvWake; stockInvWake = null; await w.release(); }
            } catch (e) { stockInvWake = null; }
            if (on && !stockInvWakeWatch) {
                stockInvWakeWatch = setInterval(() => {
                    if (stockInvCounting()) return;
                    clearInterval(stockInvWakeWatch); stockInvWakeWatch = null;
                    stockInvKeepAwake(false);
                }, 2000);
            }
        }
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible' && !stockInvWake && stockInvCounting()) stockInvKeepAwake(true);
        });

        /* ---- scanning with the phone's camera ---- */
        /* Tally scanning: each label read adds one to its line's count, with a
           beep and a buzz. Nothing is saved until Save. Counts scanned while
           the full list shows turn the count cards on (design 4.8). */
        function stockInvScanToCount(btn) {
            const P = stockInv.pane;
            if (!P) return null;
            let touched = 0;
            return openStockScanner(btn, { title: 'Scan to count', continuous: true,
                onCode: (code) => {
                    const it = stockByCode(P.sheet.items, code);
                    if (!it) return { ok: false, text: 'No line matches “' + code + '”' };
                    const next = stockInvSetCount(it, stockInvPending(it) + 1);
                    touched++;
                    return { ok: true, text: stockInvName(it) + ' → ' + next };
                },
                onClose: () => {
                    if (!touched) return;
                    if (!stockInvWorkshop()) { stockInvKeep(STOCK_INV_KEEP.workshop, true); stockInvRedrawTools(); }
                    else stockInvPaint();
                    addToast(touched + ' scan' + (touched === 1 ? '' : 's') + ' added, tap Save');
                } });
        }

        /* ---- adding a line ---- */
        function stockInvAdd(opener) {
            const win = dialog({ title: 'Add item', opener: opener, size: 'stk-add' });
            let cat = STOCK_INV_CATS[0];
            const form = el('form', 'stk-form');
            const cats = segmented(STOCK_INV_CATS.map(c => [c, c]), cat, (k) => { cat = k; }, { label: 'Category' });
            const field = (ph, mode) => { const i = el('input'); i.type = 'text'; if (ph) i.placeholder = ph; if (mode) i.inputMode = mode; return i; };
            const sub = field('For example Opal 9, or a lens');
            const size = field('For example 66 (mm glass), 80W, 40/80W');
            const cur = field('', 'numeric'); cur.value = '0';
            const cost = field('', 'decimal'); cost.value = '0';
            const sup = field('');
            const code = field('Scan or type a barcode or QR');
            const scan = textButton('Scan', { icon: I.camera, cls: 'stk-bc-scan' });
            scan.type = 'button';
            scan.onclick = () => openStockScanner(scan, { title: 'Scan a barcode', onCode: (c) => { code.value = c; addToast('Scanned ' + c); } });
            const codeRow = el('div', 'stk-bc-row'); codeRow.append(code, scan);
            const pair = el('div', 'stk-pair');
            pair.append(formField('Current units', cur), formField('Unit cost (£)', cost));
            form.append(formField('Category', cats), formField('Sub-category or colour', sub), formField('Size or variant', size),
                        pair, formField('Supplier (optional)', sup), formField('Barcode (optional)', codeRow));
            win.body.append(form);
            const cancel = textButton('Cancel'); cancel.type = 'button'; cancel.onclick = () => win.close();
            const add = textButton('Add item', { kind: 'primary' }); add.type = 'button';
            const go = async () => {
                const n = stockInvNumber(cur.value), c = stockInvNumber(cost.value);
                markInvalid(cur, !!n.bad); markInvalid(cost, !!c.bad);
                if (n.bad || c.bad) { toastError('Check the highlighted box: numbers only, such as 1200 or 12.50.'); return; }
                setBusy(add, true);
                try {
                    await stockRead('sheet', 'new', { fields: { category: cat, sub_category: sub.value.trim(), size: size.value.trim(),
                        current: n.empty ? 0 : Math.round(n.value), unit_cost_gbp: c.empty ? 0 : c.value,
                        supplier: sup.value.trim(), barcode: code.value.trim() } });
                    win.close();
                    addToast('Item added', 'good');
                    stockInvReload();
                } catch (e) { setBusy(add, false); toastError(e.message || 'That line could not be added.'); }
            };
            add.onclick = go;
            form.addEventListener('submit', (e) => { e.preventDefault(); go(); });
            form.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.tagName === 'INPUT') { e.preventDefault(); go(); } });
            win.foot().append(cancel, add);
            setTimeout(() => sub.focus(), 0);
            return win;
        }

        /* ---- import and export, in the stock sheet's own layout ---- */
        const STOCK_INV_FIELD = { start: 'Start', received: 'Received', used: 'Used', current: 'Current', unit_cost: 'Unit cost',
            unit_cost_gbp: 'Unit cost in pounds', category: 'Category', sub_category: 'Colour or type', size: 'Size', notes: 'Notes',
            supplier: 'Supplier', currency: 'Currency', written_off: 'Written off' };
        /* A signed figure, with a true minus sign. */
        const stockInvSigned = (n) => (n > 0 ? '+' : n < 0 ? '\u2212' : '') + Math.abs(n);
        const stockInvShown = (v) => v === true ? 'yes' : v === false ? 'no' : v == null || v === '' ? 'blank' : String(v);
        async function stockInvImport(text, fileName, opener) {
            let d;
            try { d = await stockRead('sheet', 'import_preview', { csv: text }); }
            catch (e) { toastError('That file could not be read: ' + (e.message || 'it is not the stock sheet.')); return; }
            /* A renamed line shows as the name's own fields changing; its key is not shown again. */
            const changes = (d.changes || []).filter(c => c.field !== 'key');
            const creates = d.creates || [];
            const net = changes.filter(c => c.field === 'current').reduce((s, c) => s + (Number(c.to) - Number(c.from)), 0);
            const P = stockInv.pane, byId = {};
            ((P && P.sheet.items) || []).forEach(i => { byId[i.id] = i; });
            const win = dialog({ title: 'Check the import first', opener: opener, size: 'wide stk-import' });
            const figs = el('div', 'stk-figs');
            [[d.rows, 'Rows read'], [changes.length, 'Fields that change'], [stockInvSigned(net), 'Net units on hand'],
             [creates.length, 'New lines']].forEach(([v, l]) => {
                const f = el('div', 'stk-fig'); f.append(el('div', 'stk-fig-v', String(v)), el('div', 'stk-fig-l', l)); figs.append(f);
            });
            win.body.append(el('p', 'stk-import-file', fileName), figs);
            if (changes.length) {
                const t = dataTable([['Line', 'kt-main'], 'Field', ['From', 'num'], ['To', 'num'], ['Change', 'num']], { cls: 'stk-import-table' });
                changes.slice(0, 60).forEach(c => {
                    const tr = el('tr');
                    const diff = typeof c.from === 'number' && typeof c.to === 'number' ? Math.round((c.to - c.from) * 100) / 100 : null;
                    const ch = el('td');
                    if (diff != null) ch.append(el('span', 'stk-diff ' + (diff > 0 ? 'stk-up-n' : 'stk-down-n'), stockInvSigned(diff)));
                    ch.className = 'num';
                    tr.append(el('td', null, byId[c.id] ? stockInvName(byId[c.id]) : c.name), el('td', null, STOCK_INV_FIELD[c.field] || c.field),
                              el('td', 'num', stockInvShown(c.from)), el('td', 'num stk-to', stockInvShown(c.to)), ch);
                    t.add(tr);
                });
                win.body.append(t.wrap);
                if (changes.length > 60) win.body.append(el('p', 'stk-more', 'and ' + (changes.length - 60) + ' more'));
            } else if (!creates.length) {
                win.body.append(emptyState({ icon: I.check, text: 'Nothing would change: these figures already match.' }));
            }
            if (creates.length) {
                const names = creates.slice(0, 8).map(n => stockInvName(n) + ' (' + n.category + ')');
                win.body.append(el('p', 'stk-new', 'New lines to be added: ' + names.join(', ') + (creates.length > 8 ? ' and ' + (creates.length - 8) + ' more' : '') + '.'));
            }
            win.body.append(el('p', 'field-help', 'Every change is written to Activity with your name, so nothing is lost without a trace.'));
            const cancel = textButton('Cancel'); cancel.type = 'button'; cancel.onclick = () => win.close();
            const go = textButton('Import', { kind: 'primary' }); go.type = 'button';
            go.disabled = !(changes.length || creates.length);
            go.onclick = async () => {
                setBusy(go, true);
                try {
                    const r = await stockRead('sheet', 'import_apply', { csv: text });
                    win.close();
                    addToast('Imported · ' + r.created + ' new, ' + r.updated_fields + ' fields updated', 'good');
                    stockInvReload();
                } catch (e) { setBusy(go, false); toastError(e.message || 'The import did not go through.'); }
            };
            win.foot().append(cancel, go);
            return win;
        }
        /* The filtered lines in the sheet's own layout, the one Import reads
           (design 4.5); the server writes a cell a spreadsheet would run as text. */
        async function stockInvExport(btn) {
            const P = stockInv.pane;
            const rows = P ? stockInvRows(P.sheet.items || []) : [];
            if (!rows.length) { addToast('No lines to export: change the filter.'); return; }
            setBusy(btn, true);
            try {
                const d = await stockRead('sheet', 'export', { ids: rows.map(r => r.id) });
                const url = URL.createObjectURL(new Blob([d.csv], { type: 'text/csv' }));
                const a = el('a'); a.href = url; a.download = d.filename || 'stock_export.csv';
                document.body.append(a); a.click(); a.remove();
                setTimeout(() => URL.revokeObjectURL(url), 1000);
                addToast('Exported ' + rows.length + ' line' + (rows.length === 1 ? '' : 's'), 'good');
            } catch (e) { toastError(e.message || 'The export did not work.'); }
            setBusy(btn, false);
        }

        /* ---- shelf labels: Avery J8160, A4, 3 by 7, 63.5 by 38.1 mm ----
           A new print sheet: paper, with its own rules (DESIGN.md, Layout). The
           production labels and their code are not touched. */
        const STOCK_INV_C39 = { '0': 'nnnwwnwnn', '1': 'wnnwnnnnw', '2': 'nnwwnnnnw', '3': 'wnwwnnnnn', '4': 'nnnwwnnnw', '5': 'wnnwwnnnn',
            '6': 'nnwwwnnnn', '7': 'nnnwnnwnw', '8': 'wnnwnnwnn', '9': 'nnwwnnwnn', A: 'wnnnnwnnw', B: 'nnwnnwnnw', C: 'wnwnnwnnn',
            D: 'nnnnwwnnw', E: 'wnnnwwnnn', F: 'nnwnwwnnn', G: 'nnnnnwwnw', H: 'wnnnnwwnn', I: 'nnwnnwwnn', J: 'nnnnwwwnn', K: 'wnnnnnnww',
            L: 'nnwnnnnww', M: 'wnwnnnnwn', N: 'nnnnwnnww', O: 'wnnnwnnwn', P: 'nnwnwnnwn', Q: 'nnnnnnwww', R: 'wnnnnnwwn', S: 'nnwnnnwwn',
            T: 'nnnnwnwwn', U: 'wwnnnnnnw', V: 'nwwnnnnnw', W: 'wwwnnnnnn', X: 'nwnnwnnnw', Y: 'wwnnwnnnn', Z: 'nwwnwnnnn', '-': 'nwnnnnwnw',
            '.': 'wwnnnnwnn', ' ': 'nwwnnnwnn', '*': 'nwnnwnwnn', '$': 'nwnwnwnnn', '/': 'nwnwnnnwn', '+': 'nwnnnwnwn', '%': 'nnnwnwnwn' };
        /* A Code 39 barcode as an SVG of bars, the stock app's own drawing. */
        function stockInvCode39(value) {
            const NS = 'http://www.w3.org/2000/svg';
            const data = '*' + String(value).toUpperCase().replace(/[^0-9A-Z\-. $/+%]/g, '') + '*';
            const svg = document.createElementNS(NS, 'svg');
            let x = 0;
            for (const ch of data) {
                const pat = STOCK_INV_C39[ch];
                if (!pat) continue;
                for (let e = 0; e < 9; e++) {
                    const w = pat[e] === 'w' ? 3 : 1;
                    if (e % 2 === 0) {
                        const r = document.createElementNS(NS, 'rect');
                        r.setAttribute('x', String(x)); r.setAttribute('width', String(w)); r.setAttribute('height', '100');
                        svg.append(r);
                    }
                    x += w;
                }
                x += 1;
            }
            svg.setAttribute('viewBox', '0 0 ' + x + ' 100');
            svg.setAttribute('preserveAspectRatio', 'none');
            svg.setAttribute('shape-rendering', 'crispEdges');
            svg.setAttribute('class', 'stk-lbl-bc');
            svg.setAttribute('aria-hidden', 'true');
            return svg;
        }
        function stockInvLabelSheet(rows) {
            const paper = el('div', 'stk-paper');
            for (let at = 0; at < rows.length; at += 21) {
                const page = el('div', 'stk-a4');
                rows.slice(at, at + 21).forEach(it => {
                    const code = stockCode(it);
                    const lbl = el('div', 'stk-lbl');
                    const logo = el('div', 'stk-lbl-logo');
                    logo.innerHTML = LABEL_LOGO;      /* the production label's own black mark (call 7): our static markup */
                    const line = el('div', 'stk-lbl-title');
                    line.append(stockDot(it), el('span', null, stockInvTitle(it)));
                    lbl.append(logo, line, el('div', 'stk-lbl-cat', it.category), stockInvCode39(code), el('div', 'stk-lbl-code', code));
                    page.append(lbl);
                });
                paper.append(page);
            }
            return paper;
        }
        function stockInvLabels(opener) {
            const P = stockInv.pane;
            const rows = P ? stockInvRows(P.sheet.items || []) : [];
            if (!rows.length) { addToast('No lines to label: change the filter.'); return; }
            const win = dialog({ title: 'Shelf labels', opener: opener, size: 'stk-labels', bodyClass: 'stk-labels-body' });
            const paper = stockInvLabelSheet(rows);
            win.body.append(paper);
            const foot = win.foot();
            foot.classList.add('stk-labels-foot');
            const close = textButton('Close'); close.type = 'button'; close.onclick = () => win.close();
            const print = textButton('Print', { kind: 'primary', icon: I.printer }); print.type = 'button';
            print.onclick = () => stockPrintFrame(paper, 'Shelf labels', '@page { size: A4; margin: 0; }');   // Avery's margins are the sheet's own
            foot.append(el('span', 'stk-labels-n', rows.length + ' label' + (rows.length === 1 ? '' : 's') + ' · filter what you print on the Inventory tab'), close, print);
            return win;
        }

        /* ---- the guided stock-take ---- */
        async function stockInvTake(opener) {
            const P = stockInv.pane;
            const rows = P ? stockInvRows(P.sheet.items || []) : [];
            if (!rows.length) { addToast('No lines to count: change the filter.'); return; }
            const kept = stockInvKept(STOCK_INV_KEEP.take);
            let T = null;
            if (kept && kept.expected && (kept.counted || []).length) {
                const when = new Date(kept.at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/London' });
                const n = (kept.counted || []).length;
                const again = await uiConfirm('Resume the stock-take you started on ' + when + '? ' + n + ' line' + (n === 1 ? '' : 's') + ' counted so far.',
                    { title: 'Stock-take', okText: 'Carry on', cancelText: 'Start again' });
                if (again) T = { expected: kept.expected, entered: kept.entered || {}, counted: new Set((kept.counted || []).map(String)), at: kept.at };
            }
            if (!T) T = { expected: {}, entered: {}, counted: new Set(), at: new Date().toISOString() };
            rows.forEach(r => { if (!(r.id in T.expected)) { T.expected[r.id] = r.current; T.entered[r.id] = r.current; } });
            stockInvTakeWindow(opener, rows, T);
        }
        function stockInvTakeKeep(T) {
            stockInvKeep(STOCK_INV_KEEP.take, Object.keys(T.expected).length
                ? { expected: T.expected, entered: T.entered, counted: [...T.counted], at: T.at } : null);
        }
        function stockInvTakeWindow(opener, rows, T) {
            let applied = false;
            const P = stockInv.pane;
            const win = dialog({ title: 'Stock-take', opener: opener, size: 'stk-take', overlayClass: 'stk-take-ov', bodyClass: 'stk-take-body',
                onClose: () => {
                    if (applied) return;
                    stockInvTakeKeep(T);
                    if (T.counted.size) addToast('Stock-take paused: open it again to carry on');
                } });
            const prog = el('p', 'stk-take-prog');
            prog.setAttribute('aria-live', 'polite');
            const list = el('div', 'stk-count stk-take-list');
            const cards = {};
            const tone = (id) => {
                const card = cards[id]; if (!card) return;
                const E = T.expected[id], v = T.entered[id], counted = T.counted.has(String(id)), off = counted && v !== E;
                card.classList.toggle('stk-ok', counted && !off);
                card.classList.toggle('stk-var', off);
                card.stkSub.textContent = 'expected ' + E + (off ? ' · ' + stockInvSigned(v - E) : counted ? ' · counted ✓' : '');
            };
            const progress = () => {
                const total = Object.keys(T.expected).length, n = T.counted.size;
                const vc = [...T.counted].filter(k => T.entered[k] !== T.expected[k]).length;
                prog.textContent = n + ' of ' + total + ' counted' + (vc ? ' · ' + vc + ' variance' + (vc === 1 ? '' : 's') : '');
            };
            T.seq = [];
            stockInvGroups(rows, P.sheet).forEach(g => {
                g.items.forEach(it => T.seq.push(it.id));
                const h = el('div', 'stk-count-head');
                h.append(stockDot(g.items[0]), el('span', 'stk-count-label', g.label));
                list.append(h);
                g.items.forEach(it => {
                    const card = stockInvCard(it, { take: true, sub: 'expected ' + T.expected[it.id],
                        value: () => T.entered[it.id],
                        set: (v) => {
                            v = Math.max(0, Math.min(2147483647, Math.round(v || 0)));
                            T.entered[it.id] = v; T.counted.add(String(it.id));
                            tone(it.id); progress(); stockInvTakeKeep(T);
                            return v;
                        } });
                    cards[it.id] = card;
                    list.append(card);
                    tone(it.id);
                });
            });
            win.body.append(prog, list);
            progress();
            stockInvKeepAwake(true);
            const rest = textButton('Rest correct', { icon: I.check }); rest.type = 'button';
            rest.onclick = () => { rows.forEach(r => { T.counted.add(String(r.id)); tone(r.id); }); progress(); stockInvTakeKeep(T); };
            const cancel = textButton('Cancel'); cancel.type = 'button'; cancel.onclick = () => win.close();
            const review = textButton('Review', { kind: 'primary' }); review.type = 'button';
            review.onclick = () => stockInvTakeReview(review, T, () => { applied = true; win.close(); });
            win.foot().append(rest, cancel, review);
            return win;
        }
        function stockInvTakeReview(opener, T, finished) {
            const P = stockInv.pane;
            const byId = {}; P.sheet.items.forEach(i => { byId[i.id] = i; });
            const keys = Object.keys(T.expected);
            /* In the order the window lists them. */
            const variances = (T.seq || keys).map(String).filter(k => T.counted.has(k) && T.entered[k] !== T.expected[k] && byId[k]);
            const uncounted = keys.length - T.counted.size;
            const win = dialog({ title: 'Stock-take review', opener: opener, size: 'stk-review' });
            if (!variances.length) {
                win.body.append(emptyState({ icon: I.check, text: 'No variances: every counted line matches the sheet.',
                    sub: uncounted ? uncounted + ' not yet counted.' : '' }));
                const back = textButton('Back to count', { kind: 'primary' }); back.type = 'button'; back.onclick = () => win.close();
                win.foot().append(back);
                return win;
            }
            let net = 0, money = 0;
            variances.forEach(k => { const d = T.entered[k] - T.expected[k]; net += d; money += d * (byId[k].unit_cost_gbp || 0); });
            const figs = el('div', 'stk-figs');
            [[String(variances.length), 'Variances' + (uncounted ? ' · ' + uncounted + ' not counted' : '')],
             [stockInvSigned(net), 'Net units'], [(money > 0 ? '+' : money < 0 ? '\u2212' : '') + stockGbp(Math.abs(money)), 'Value impact']].forEach(([v, l]) => {
                const f = el('div', 'stk-fig'); f.append(el('div', 'stk-fig-v', v), el('div', 'stk-fig-l', l)); figs.append(f);
            });
            const t = dataTable([['Line', 'kt-main'], ['Expected', 'num'], ['Counted', 'num'], ['Difference', 'num']], { cls: 'stk-var-table' });
            variances.forEach(k => {
                const d = T.entered[k] - T.expected[k];
                const tr = el('tr'), dc = el('td', 'num');
                dc.append(el('span', 'stk-diff ' + (d > 0 ? 'stk-up-n' : 'stk-down-n'), stockInvSigned(d)));
                tr.append(el('td', null, stockInvName(byId[k])), el('td', 'num', String(T.expected[k])), el('td', 'num stk-to', String(T.entered[k])), dc);
                t.add(tr);
            });
            let cause = 'usage';
            const seg = segmented([['usage', 'Stock sold or used'], ['correction', 'A counting correction']], cause, (k) => { cause = k; }, { label: 'Shortfalls are' });
            seg.classList.add('stk-cause');
            win.body.append(figs, t.wrap, formField('Shortfalls are', seg,
                { help: 'Sold or used keeps the run-out forecast and reorder warnings right. Choose a correction if the old figure was simply wrong.' }));
            const back = textButton('Back'); back.type = 'button'; back.onclick = () => win.close();
            const apply = textButton('Apply ' + variances.length + ' correction' + (variances.length === 1 ? '' : 's'), { kind: 'primary' });
            apply.type = 'button';
            apply.onclick = async () => {
                setBusy(apply, true);
                let ok = 0, fail = 0;
                for (const k of variances) {
                    try {
                        await stockRead('sheet', 'edit', { id: Number(k), changes: { current: T.entered[k] }, seen: { current: T.expected[k] }, as_count: cause === 'usage' });
                        ok++;
                    } catch (e) { fail++; }
                }
                stockInvKeep(STOCK_INV_KEEP.take, null);
                win.close();
                finished();
                addToast(fail ? 'Applied ' + ok + ', ' + fail + ' failed' : 'Stock-take applied · ' + ok + ' correction' + (ok === 1 ? '' : 's'), fail ? 'bad' : 'good');
                stockInvReload();
            };
            win.foot().append(back, apply);
            return win;
        }
