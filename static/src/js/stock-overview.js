        /* ---------- Stock: Overview ----------
           The stock app's Dashboard, in its order, drawn with Reactor's parts:
           the news since you were last here (a notice), the live warnings (the
           house alerts banner), the gobo lines production could not match,
           the quarter's five figures, where the value sits, the currency
           exposure, what needs action and the kept AI reading. This section
           also owns the two windows other tabs open: a line's item sheet
           (openStockItem) and its own history (openStockHistory).

           The flaw fixed here (design §4.3): the warnings and the matching
           panel always show when they have rows; the stock app drew them only
           when the news had something to say. */
        const stockOvBriefing = () => stockGet('briefing', 'overview', 'briefing');
        const stockOvParked = () => stockGet('parked', 'mapping', 'parked');
        const stockOvFx = () => stockGet('fx', 'overview', 'fx');
        const stockOvInsights = () => stockGet('insights', 'overview', 'insights');
        /* A section that could not be read says so in its own place, rather
           than taking the whole tab with it: the stock app swallowed each one. */
        const stockOvSoft = (read) => () => read().catch(() => null);

        function renderStockOverview(host) {
            stockLoad(host, [stockSheet, stockOvSoft(stockAlerts), stockOvSoft(stockReorderList), stockOvSoft(stockOvBriefing),
                             stockOvSoft(stockOvParked), stockOvSoft(stockOvFx), stockOvSoft(stockOvInsights)],
                (sheet, alerts, reorder, briefing, parked, fx, insights) => {
                    const news = stockOvNews(briefing);
                    if (news) host.append(news);
                    const warn = stockOvWarnings(alerts, sheet);
                    if (warn) host.append(warn);
                    host.append(stockOvGobo(parked));
                    host.append(stockOvFigures(sheet.summary));
                    stockOvValue(host, sheet.summary);
                    host.append(stockOvCurrency(fx));
                    stockOvAction(host, sheet, reorder);
                    host.append(stockOvInsightsPanel(insights));
                });
        }
        /* After a write: the reads it changed are read again, and the tab and
           its counts are drawn again from them. */
        function stockOvRedraw(...names) {
            stockForget(...names);
            if (document.querySelector('#view-stock.active')) showStockView();
        }
        /* A line of the sheet from what a list or a warning names it by. */
        function stockOvLine(sheet, key) { return ((sheet && sheet.items) || []).find(i => i.key === key) || null; }
        /* A figures row's line, named as every tab names it (stockName), with its category. */
        function stockOvSplit(r) {
            const it = stockLineByKey(r.key);
            if (it) return { cat: it.category, name: stockName(it) };
            const s = String(r.item || ''), at = s.indexOf(' / ');
            return at < 0 ? { cat: '', name: s } : { cat: s.slice(0, at), name: s.slice(at + 3) };
        }
        function stockOvWhen(iso) { return iso ? fmtDate(iso) + ', ' + londonHM(iso) : ''; }
        function stockOvCount(n, one, many) { return n + ' ' + (n === 1 ? one : many); }
        /* A section's head: its title (with a count and an info button) and its tools. */
        function stockOvHead(title, o) {
            o = o || {};
            const head = el('div', 'card-head' + (o.stat ? ' card-head-stat' : ''));
            const h = el('h3', 'card-title', title);
            if (o.n != null) h.append(el('span', 'card-n', String(o.n)));
            head.append(o.info ? titleInfo(h, infoButton('About ' + title.toLowerCase(), { title: title, body: o.info })) : h);
            if (o.desc) head.append(o.desc);
            if (o.sub) head.append(typeof o.sub === 'string' ? el('p', 'card-sub', o.sub) : o.sub);
            if (o.act && o.act.length) { const a = el('div', 'card-act'); o.act.forEach(b => a.append(b)); head.append(a); }
            return head;
        }

        /* ---- 1. Since you were last here: a notice, dismissed on the server ----
           Shown when something has happened since (the checklist's "until
           something new happens"); the lines due to reorder ride along but
           alone do not bring it back, which the stock app's did every visit. */
        function stockOvNews(b) {
            if (!b || !b.since) return null;
            const parts = [];
            if (b.value_delta != null && Math.abs(b.value_delta) >= 1)
                parts.push('stock value ' + (b.value_delta >= 0 ? 'up ' : 'down ') + stockGbp(Math.abs(b.value_delta)));
            if (b.edits) parts.push(stockOvCount(b.edits, 'edit', 'edits'));
            if (b.receives) parts.push(stockOvCount(b.receives, 'delivery received', 'deliveries received'));
            if (b.creates) parts.push(stockOvCount(b.creates, 'new line', 'new lines'));
            if (b.period) parts.push('a quarter closed');
            if (!parts.length && !b.new_alerts) return null;
            if (b.reorder_lines) parts.push(b.reorder_lines + ' to reorder');
            if (b.new_alerts) parts.push(stockOvCount(b.new_alerts, 'new warning', 'new warnings'));
            const note = el('div', 'resp-note stock-ov-news');
            note.setAttribute('role', 'status');
            note.append(ico(I.info), el('p', null, 'Since you were last here (' + fmtDate(b.since) + '): ' + parts.join(' · ') + '.'));
            const x = iconButton(I.x, 'Dismiss: mark as read', { size: 'small', title: 'Dismiss' });
            x.onclick = async () => {
                setBusy(x, true);
                try { await stockRead('overview', 'ack'); note.remove(); stockForget('briefing'); }
                catch (e) { setBusy(x, false); toastError('That was not marked as read. ' + (e.message || '')); }
            };
            note.append(x);
            return note;
        }

        /* ---- 2. The live warnings: the three most severe, as Reactor's own alerts banner ---- */
        const STOCK_OV_SEV = { critical: 0, warning: 1, info: 2 };
        function stockOvWarnings(al, sheet) {
            if (!al) return el('div', 'msg error', 'The warnings could not be read.');
            const all = al.alerts || [];
            if (!all.length) return null;
            const top = all.slice().sort((a, b) => (STOCK_OV_SEV[a.severity] ?? 3) - (STOCK_OV_SEV[b.severity] ?? 3)).slice(0, 3);
            const wrap = el('div', 'alerts-banner stock-ov-warn');
            const head = el('div', 'alerts-head');
            head.append(ico(I.warning), document.createTextNode(stockOvCount(all.length, 'warning', 'warnings')));
            if (all.length > top.length) {
                const more = textLink('See all ' + all.length, { cls: 'stock-ov-more' });
                more.onclick = () => { stockSeg = 'activity'; renderStock(); };
                head.append(more);
            }
            wrap.append(head);
            top.forEach(a => {
                const row = el('div', 'alert-row stock-ov-alert');
                const kind = stockWords(a.kind, STOCK_KINDS);
                /* The message without its repeated kind, the line named as every tab names it. */
                const msg = stockWarningText(a);
                row.append(el('span', 'adot sev-' + (a.severity || 'info')), el('span', 'a-tab', kind), el('span', 'a-metric', msg));
                const it = stockOvLine(sheet, a.item_key);
                if (it) {
                    const open = () => openStockItem(it, row.querySelector('.row-open'));
                    row.classList.add('opens');
                    row.prepend(rowOpener('Open ' + stockName(it) + ': ' + kind, open));
                    opensOnClick(row, open);
                }
                const x = iconButton(I.x, 'Dismiss this warning', { size: 'small', title: 'Dismiss' });
                x.onclick = async () => {
                    setBusy(x, true);
                    try { await stockRead('overview', 'dismiss', { id: a.id }); stockOvRedraw('alerts'); }
                    catch (e) { setBusy(x, false); toastError('That warning was not dismissed. ' + (e.message || '')); }
                };
                row.append(x);
                wrap.append(row);
            });
            return wrap;
        }

        /* ---- 3. Gobo production to match ---- */
        /* Mono, HM and ring rulings are remembered (the server's rule); a
           colour line names no colour, so it is booked for its own order. */
        const stockOvRemembered = (alias) => /^(mono|hm|ring)\|/i.test(String(alias || ''));
        const stockOvAlias = (alias) => String(alias || '').replace('|', ' ') + 'mm';
        function stockOvGobo(d) {
            const card = el('div', 'card stock-ov-gobo');
            const map = textButton('Stock mapping', { icon: I.sliders });
            map.type = 'button';
            map.onclick = () => stockOvMapping(map);
            const rows = d ? (d.parked || []) : [];
            card.append(stockOvHead('Gobo production to match', {
                n: rows.length || null, act: [map],
                info: ['These came from Mark made in the Production Manager, but no stock line matches them yet. Pick the line each one means.',
                       'For Mono and HM the choice is remembered for every future order. A colour line is booked for its own order only, because the order does not say which colour.'],
                sub: !d ? 'The lines waiting to be matched could not be read.' : !rows.length ? 'Nothing waiting: every gobo made has booked against a stock line.' : null }));
            if (!rows.length) return card;
            const opts = [['', 'Choose the stock line…']].concat((d.options || []).map(o => [String(o.id), o.name]));
            card.append(dtable([{ head: 'Made' }, { head: 'Stock line' }, { head: '', cls: 'act' }], rows.map(p => {
                const line = stockOvAlias(p.alias);
                const pick = choiceSelect(opts, '', () => {}, { label: 'Stock line for ' + line + ', ' + p.order_name });
                const keep = stockOvRemembered(p.alias);
                const go = textButton(keep ? 'Map and book' : 'Book this line', {
                    title: keep ? 'Remembered: every future line like this books the same stock line'
                                : 'Books only this line. Colour lines are decided per order, because the order does not say which colour.' });
                go.type = 'button';
                go.onclick = async () => {
                    if (!pick.value) { toastError('Choose the stock line ' + line + ' is first.'); pick.focus(); return; }
                    setBusy(go, true);
                    try {
                        const r = await stockRead('mapping', 'map', { alias: p.alias, id: Number(pick.value), parked_id: p.id });
                        toastOk('Booked ' + stockOvCount(r.booked_units || 0, 'blank', 'blanks') + ' against stock.');
                        stockOvRedraw('parked', 'sheet', 'alerts', 'reorder', 'briefing', 'fx');
                    } catch (e) { setBusy(go, false); toastError(e.message || 'That line could not be matched.'); }
                };
                const sub = stockOvCount(p.qty, 'blank', 'blanks') + ' · ' + p.order_name + (p.note ? ' · ' + p.note : '');
                return { cells: [dtMain(line, sub), pick, go] };
            }), { cls: 'dt-stock-gobo', label: 'Gobo production to match', stop: 's' }));
            return card;
        }
        /* The whole translation between production's glass lines and the
           sheet, grouped by family: what books on its own, what was ruled,
           what is decided per order and what has no stock line. */
        const STOCK_OV_STATUS = { auto: ['Books automatically', 'made'], ruled: ['Ruled by you', 'made'],
                                  per_order: ['Decided per order', 'warn'], unmapped: ['No stock item', 'bad'] };
        /* The family the mapping opens on: the first with a production line
           waiting for a ruling, else the first (call 9: it lists every line
           production can make, so it shows one family at a time). */
        function stockOvMapFamily(rows) {
            const fams = [];
            (rows || []).forEach(r => { if (fams.indexOf(r.family) < 0) fams.push(r.family); });
            return fams.find(f => rows.some(r => r.family === f && r.parked)) || fams[0] || null;
        }
        async function stockOvMapping(opener) {
            const win = dialog({ title: 'Stock mapping', size: 'wide', opener: opener, bodyClass: 'stock-ov-map' });
            titleInfo(win.heading, infoButton('About the stock mapping', { title: 'Stock mapping', body: [
                'Every glass line production can make, and the stock line it books against.',
                'Rulings are remembered for Mono, HM and rings; colour glass is decided per order, because the order does not say which colour.'] }));
            let fam = null;
            const draw = async () => {
                win.body.innerHTML = '';
                win.body.append(el('div', 'setting-sub', 'Loading…'));
                let d;
                try { d = await stockRead('mapping', 'mapping'); }
                catch (e) { win.body.innerHTML = ''; win.body.append(loadFailure('The mapping could not be read. ' + (e.message || ''), draw)); return; }
                win.body.innerHTML = '';
                const fams = new Map();
                (d.rows || []).forEach(r => { if (!fams.has(r.family)) fams.set(r.family, []); fams.get(r.family).push(r); });
                if (!fams.size) { win.body.append(emptyState({ icon: I.sliders, text: 'Production has no glass lines yet.' })); return; }
                if (!fam || !fams.has(fam)) fam = stockOvMapFamily(d.rows);
                const parkedIn = (f) => fams.get(f).reduce((n, r) => n + (r.parked || 0), 0);
                win.body.append(tabStrip([...fams.keys()].map(f => ({ key: f, label: f, n: parkedIn(f) || null })), fam,
                    (k) => { fam = k; draw(); }, { label: 'Families' }));
                [[fam, fams.get(fam)]].forEach(([famName, rows]) => {
                    const t = dataTable([['Size', 'kt-main'], 'Status', 'Books as', ['Parked', 'num'], 'Ruling']);
                    rows.forEach(r => {
                        const [said, tone] = STOCK_OV_STATUS[r.status] || [r.status, 'note'];
                        const tr = el('tr');
                        const st = el('td'); st.append(el('span', 'lbl-chip ' + tone, said));
                        const pk = el('td', 'num');
                        if (r.parked) pk.append(el('span', 'lbl-chip warn', r.parked + ' parked'));
                        const rule = el('td');
                        if (r.status !== 'per_order') {
                            const first = r.status === 'ruled' ? 'Change the ruling…' : r.status === 'auto' ? 'Override…' : 'Choose the stock line…';
                            const pick = choiceSelect([['', first]].concat((d.options || []).map(o => [String(o.id), o.name])), '', async (v) => {
                                if (!v) return;
                                pick.disabled = true;
                                try {
                                    const res = await stockRead('mapping', 'map', { alias: r.alias, id: Number(v) });
                                    toastOk(res.booked_units ? 'Ruled, and ' + stockOvCount(res.booked_units, 'parked blank', 'parked blanks') + ' booked.' : 'Ruled.');
                                    stockOvRedraw('parked', 'sheet', 'alerts', 'reorder', 'briefing', 'fx');
                                    draw();
                                } catch (e) { pick.disabled = false; toastError(e.message || 'That ruling was not saved.'); }
                            }, { label: 'Ruling for ' + famName + ' ' + r.size + 'mm' });
                            rule.append(pick);
                        }
                        tr.append(el('td', null, r.size + 'mm'), st, el('td', null, r.target ? stockKeyName(r.target.key) : ''), pk, rule);
                        t.add(tr);
                    });
                    win.body.append(t.wrap);
                });
            };
            draw();
        }

        /* ---- 4. The quarter at a glance: the sheet's own five figures ---- */
        function stockOvFigures(a) {
            const h = a.headline, dead = a.dead_stock, wo = a.write_offs;
            const deadPc = h.active_stock_value_gbp ? Math.round(100 * dead.tied_up_value_gbp / h.active_stock_value_gbp) : 0;
            const strip = metricsStrip([
                { label: 'Active stock value', value: stockGbp(h.active_stock_value_gbp),
                  note: h.active_units.toLocaleString('en-GB') + ' units · ' + h.active_skus + ' live lines' },
                { label: 'Used this quarter', value: stockGbp(h.cogs_used_value_gbp),
                  note: h.used_units.toLocaleString('en-GB') + ' units used (cost of goods)' },
                { label: 'Sell-through', value: h.sell_through_pct + '%', note: 'of the opening ' + h.start_units.toLocaleString('en-GB') + ' units' },
                { label: 'Dead capital', value: stockGbp(dead.tied_up_value_gbp, 0), note: stockOvCount(dead.skus, 'line', 'lines') + ', no usage' },
                { label: 'Written-off sunk cost', value: stockGbp(wo.estimated_sunk_cost_gbp, 0),
                  note: wo.units.toLocaleString('en-GB') + ' units · ' + stockOvCount(wo.skus, 'line', 'lines') }]);
            strip.classList.add('stock-ov-quarter');
            strip.setAttribute('aria-label', 'Quarter at a glance');
            const tag = (i, text, tone) => { const row = strip.children[i] && strip.children[i].querySelector('.stat-row'); if (row) row.append(el('span', 'lbl-chip ' + tone, text)); };
            tag(3, deadPc + '% of value', 'warn');
            if (wo.skus) tag(4, 'dead inventory', 'bad');
            return strip;
        }

        /* ---- 5. Where the value sits: four bar lists, the house's own ----
           The stock app's donut becomes a bar list too: Reactor draws no
           donut, and bars put the categories' pounds and shares side by side. */
        function stockOvValue(host, a) {
            const cats = catBars({ title: 'Stock value by category', value: stockGbp(a.headline.active_stock_value_gbp),
                help: 'Active stock only: written-off lines are left out. Each category\'s share of the value is beside its name.',
                items: a.by_category.map(c => ({ label: c.category + ' · ' + (Math.round(c.pct_of_value * 10) / 10) + '%', value: c.value_gbp })),
                format: fmtCompactGBP });
            const sup = catBars({ title: 'Supplier exposure', help: 'Active stock value by supplier, the six largest.',
                items: a.by_supplier.slice(0, 6).map(s => ({ label: s.name, value: s.value_gbp })), format: fmtCompactGBP });
            const top = catBars({ title: 'Top lines by current value', help: 'The lines holding the most capital, with their category.',
                items: a.top_value_items.slice(0, 8).map(r => { const s = stockOvSplit(r); return { label: s.name + ' · ' + s.cat, value: r.value_gbp }; }),
                format: fmtCompactGBP });
            const wo = a.write_offs.by_category.length
                ? catBars({ title: 'Write-offs by category', help: 'The estimated original cost sunk in written-off units.',
                    items: a.write_offs.by_category.map(w => ({ label: w.category + ' · ' + w.units + ' units', value: w.sunk_gbp })),
                    format: fmtCompactGBP, color: CH[3] })
                : stockOvEmptyCard('Write-offs by category', 'Nothing written off.');
            /* Today's quadrants: category over supplier on the left, top lines over write-offs on the right. */
            host.append(cats, top);
            pairNodes(cats, top, null, null, { plain: true, even: true });
            host.append(sup, wo);
            pairNodes(sup, wo, null, null, { plain: true, even: true });
        }
        function stockOvEmptyCard(title, line) {
            const c = el('div', 'card');
            c.append(stockOvHead(title), el('p', 'card-sub', line));
            return c;
        }

        /* ---- 6. Currency exposure: the stock restated at today's rates ---- */
        const stockOvDrift = (gbp, pct) => {
            const t = gbp > 0 ? 'up' : gbp < 0 ? 'down' : 'flat';
            return changeChip(t, (gbp > 0 ? '+' : gbp < 0 ? '-' : '') + stockGbp(Math.abs(gbp)) + ' (' + pct + '%)', t === 'up' ? 'good' : t === 'down' ? 'bad' : 'flat');
        };
        function stockOvCurrency(d) {
            const card = el('div', 'card stock-ov-fx');
            if (!d) { card.append(stockOvHead('Currency exposure', { sub: 'The exchange rates could not be read.' })); return card; }
            const desc = el('p', 'card-desc');
            desc.append(document.createTextNode(stockGbp(d.total_today_gbp)), stockOvDrift(d.total_drift_gbp, d.total_drift_pct));
            card.append(stockOvHead('Currency exposure', { stat: true, desc: desc,
                info: ['What the stock bought in dollars and euros is worth at today\'s exchange rates, against what it was booked at when it was bought. The rates are set in the stock settings.'],
                sub: 'At today\'s rates. Booked at purchase ' + stockGbp(d.total_booked_gbp) + (d.not_revalued_gbp ? ' · ' + stockGbp(d.not_revalued_gbp) + ' has no native cost to revalue' : '') }));
            if (!(d.currencies || []).length) {
                card.append(emptyState({ icon: I.cash, text: 'No lines have a native USD or EUR cost to revalue. Set the rates in the stock settings.' }));
                return card;
            }
            const t = dataTable([['Currency', 'kt-main'], ['Rate', 'num'], ['Units', 'num'], ['Booked', 'num'], ['Today', 'num'], ['Drift', 'num']]);
            d.currencies.forEach(c => {
                const tr = el('tr');
                const dr = el('td', 'num'); dr.append(stockOvDrift(c.drift_gbp, c.drift_pct));
                tr.append(el('td', null, c.currency + ' to GBP'), el('td', 'num', '@ ' + c.rate), el('td', 'num', c.units.toLocaleString('en-GB')),
                          el('td', 'num', stockGbp(c.booked_gbp)), el('td', 'num', stockGbp(c.today_gbp)), dr);
                t.add(tr);
            });
            card.append(t.wrap);
            return card;
        }

        /* ---- 7. Action needed: least cover and the biggest idle money ---- */
        function stockOvAction(host, sheet, reorder) {
            const a = sheet.summary;
            /* A row opens its line's item sheet: from a click anywhere on it,
               and from the real button its main cell carries for a keyboard. */
            const opening = (key, label, main) => {
                const go = () => { const it = stockOvLine(sheet, key); if (it) openStockItem(it, opener); };
                const opener = rowOpener('Open ' + label, go);
                const cell = document.createDocumentFragment(); cell.append(opener, main);
                return { cell, go };
            };
            /* Reorder soon: what runs out first at this quarter's rate. */
            const low = el('div', 'card stock-ov-low');
            let sub;
            if (reorder && reorder.total_lines) {
                sub = el('p', 'card-sub');
                const go = textLink('See the Reorder tab', { size: 'inline' });
                go.onclick = () => { stockSeg = 'reorder'; renderStock(); };
                sub.append(el('b', null, String(reorder.total_lines)),
                    document.createTextNode(reorder.total_lines === 1 ? ' line is at or below its reorder level. ' : ' lines are at or below their reorder level. '), go);
            } else if (reorder) {
                sub = el('p', 'card-sub');
                const go = textLink('Set them from usage', { size: 'inline' });
                go.onclick = () => { stockSeg = 'reorder'; renderStock(); };
                sub.append(document.createTextNode('No reorder levels are set yet, so nothing can trigger automatically. '), go);
            }
            low.append(stockOvHead('Reorder soon', { sub: sub,
                info: ['Ranked by cover: the units on hand divided by this quarter\'s usage, in quarters. Under 1.5 is red, under 3 amber.'] }));
            const cands = a.reorder_candidates.slice(0, 7);
            if (!cands.length) low.append(emptyState({ icon: I.box, text: 'No usage recorded yet: counting stock down on a phone records it.' }));
            else low.append(dtable([{ head: 'Cover' }, { head: 'Line' }, { head: 'On hand', cls: 'num', cap: true }], cands.map(c => {
                const s = stockOvSplit(c), q = c.cover_quarters;
                const tag = el('span', 'lbl-chip ' + (stockCoverTone(q) || 'note'), q.toFixed(1) + 'q');
                tag.title = q.toFixed(1) + ' quarters of cover';
                const o = opening(c.key, s.name, dtMain(s.name, s.cat + ' · used ' + c.used + ', ' + c.current + ' left'));
                return { cells: [tag, o.cell, stockGbp(c.value_gbp, 0)], onClick: o.go };
            }), { cls: 'dt-stock-low', label: 'Reorder soon', stop: 'xs', main: 1 }));
            /* Dead capital: active lines with no usage this quarter, the most money first. */
            const dead = el('div', 'card stock-ov-dead');
            dead.append(stockOvHead('Dead capital', { info: ['Active lines with no usage this quarter, the most money first.'] }));
            const idle = a.dead_stock.top.slice(0, 7);
            if (!idle.length) dead.append(emptyState({ icon: I.box, text: 'Nothing idle with value.' }));
            else dead.append(dtable([{ head: 'Line' }, { head: 'Idle', cls: 'num', cap: 'Idle units' }, { head: 'Tied up', cls: 'num', cap: true }], idle.map(x => {
                const s = stockOvSplit(x);
                const o = opening(x.key, s.name, dtMain(s.name, s.cat));
                return { cells: [o.cell, x.units.toLocaleString('en-GB'), stockGbp(x.value_gbp, 0)], onClick: o.go };
            }), { cls: 'dt-stock-dead', label: 'Dead capital', stop: 'xs' }));
            host.append(low, dead);
            pairNodes(low, dead, null, null, { plain: true, even: true });
        }

        /* ---- 8. Insights and recommendations: the kept reading, and a new one ---- */
        const stockOvKept = (k) => 'Generated ' + stockOvWhen(k.at) + (k.by ? ', by ' + k.by : '') + '.';
        const STOCK_OV_FIND = { critical: 'warning', warning: 'warning', positive: 'win', info: 'insight' };
        function stockOvInsightsPanel(k) {
            const card = el('div', 'card stock-ov-ai');
            const gen = textButton('Generate', { kind: 'primary', icon: I.spark });
            gen.type = 'button';
            const res = k && k.result;
            card.append(stockOvHead('Insights and recommendations', { act: [gen],
                info: ['Key findings and recommended actions, read by AI from the current stock figures. The last reading is kept for everyone until the next.'],
                sub: !k ? 'The last reading could not be read.' : res ? stockOvKept(k) : null }));
            /* A holder with no class, so the actions' table runs to the panel's edges as the findings do. */
            const body = el('div'); body.dataset.aiBody = '';
            card.append(body);
            const draw = (r) => {
                body.innerHTML = '';
                if (!r) { body.append(emptyState({ icon: I.spark, text: 'No reading yet: Generate reads the figures.' })); return; }
                const top = el('div', 'stock-ov-aitop');
                if (typeof r.health_score === 'number') {
                    const score = Math.max(0, Math.min(100, Math.round(r.health_score)));
                    const fig = el('div', 'stock-ov-score');
                    fig.append(el('span', 'stock-ov-figl', 'Health score'));
                    const n = el('b', 'stock-ov-fign', String(score));
                    n.append(el('span', 'stock-ov-figof', ' / 100'));
                    fig.append(n, meter({ taken: score, end: score }));
                    top.append(fig);
                }
                top.append(el('p', 'stock-ov-headline', r.headline || ''));
                body.append(top);
                if ((r.findings || []).length) {
                    body.append(el('h4', 'stock-ov-sub', 'Key findings'));
                    const list = el('div', 'insights stock-ov-finds');
                    r.findings.forEach((f, i) => {
                        const c = insightCard({ type: STOCK_OV_FIND[f.severity] || 'insight', title: f.title, detail: f.detail }, i);
                        if (f.severity === 'critical') c.classList.add('critical');
                        if (f.metric) c.querySelector('.t').append(el('span', 'stock-ov-metric', f.metric));
                        list.append(c);
                    });
                    body.append(list);
                }
                if ((r.actions || []).length) {
                    body.append(el('h4', 'stock-ov-sub', 'Recommended actions'));
                    body.append(dtable([{ head: 'Action', cls: 'stack' }, { head: 'Priority', cls: 'num' }], r.actions.map(x => {
                        const p = ['high', 'medium', 'low'].includes(x.priority) ? x.priority : 'medium';
                        const f = document.createDocumentFragment();
                        f.append(el('span', 'dt-name', x.title || ''), el('span', 'dt-why', x.detail || ''));
                        const tag = el('span', 'pill ' + p, cap(p)); tag.title = cap(p) + ' priority';
                        return { cells: [f, tag] };
                    }), { cls: 'dt-stock-acts', label: 'Recommended actions', stop: 'xs' }));
                }
            };
            draw(res);
            gen.onclick = async () => {
                setBusy(gen, true);
                try {
                    const r = await stockRead('ai', 'insights');
                    stockForget('insights');
                    const kept = await stockOvSoft(stockOvInsights)();
                    const sub = card.querySelector('.card-sub');
                    if (sub && kept && kept.at) sub.textContent = stockOvKept(kept);
                    draw(r);
                    toastOk('A new reading of the figures is ready.');
                } catch (e) { toastError('No new reading: ' + (e.message || 'the AI could not be reached.') + (res ? ' The last reading stays.' : '')); }
                setBusy(gen, false);
            };
            return card;
        }

        /* ---------- the item sheet: one line, answered ----------
           In stock, on order (when any) and used this quarter; whether an
           order of so many can be supplied, answered as it is typed; when it
           runs out, its supplier and delivery time, when an order placed
           today would arrive, its reorder level and the value on hand. Its
           own history, a corrected count and a delivery are one press away.
           Read fresh each time it opens (history op "item"): the forecast and
           the delivery time are the line's own as of now (design §4.8). */
        async function openStockItem(item, opener) {
            const name = stockName(item) || item.name || 'Stock line';
            const win = dialog({ title: name, size: 'stock-item-win', opener: opener, bodyClass: 'stock-item' });
            win.body.append(el('div', 'setting-sub', 'Loading…'));
            let d;
            try { d = await stockRead('history', 'item', { id: item.id }); }
            catch (e) {
                win.body.innerHTML = '';
                win.body.append(loadFailure('This line could not be read. ' + (e.message || ''), () => { win.close(); openStockItem(item, opener); }));
                return;
            }
            const it = d.item, f = d.forecast || {}, lead = Number(d.lead_days) || 0;
            const day = (days) => fmtDate(new Date(Date.now() + days * 86400000).toISOString());
            const arrive = lead ? day(lead) : null;
            win.body.innerHTML = '';
            const figs = el('div', 'stock-ov-figs');
            const fig = (n, l) => { const b = el('div', 'stock-ov-fig'); b.append(el('b', 'stock-ov-fign', String(n)), el('span', 'stock-ov-figl', l)); figs.append(b); };
            fig(it.current, 'in stock');
            if (it.on_order) fig(it.on_order, 'on order');
            fig(it.used || 0, 'used this quarter');
            win.body.append(figs);
            /* Can I supply an order of...: the answer as the number is typed. */
            const q = document.createElement('input');
            q.type = 'number'; q.min = '1'; q.inputMode = 'numeric'; q.className = 'field-sm stock-item-q';
            const ans = el('span', 'stock-item-ans', 'Enter a quantity');
            ans.setAttribute('aria-live', 'polite');
            q.oninput = () => {
                const n = parseInt(q.value, 10);
                ans.className = 'stock-item-ans';
                if (!n || n <= 0) { ans.textContent = 'Enter a quantity'; return; }
                if (n <= it.current) { ans.classList.add('ok'); ans.textContent = 'Yes, ' + (it.current - n) + ' would be left'; return; }
                const short = n - it.current;
                if (it.on_order >= short) { ans.classList.add('warn'); ans.textContent = 'Short by ' + short + ', but ' + it.on_order + ' already on order'; return; }
                ans.classList.add('no');
                ans.textContent = 'No, short by ' + short + (arrive ? '; order today and it could ship around ' + arrive : '; no delivery time is set for this supplier');
            };
            const ask = el('div', 'stock-item-askrow');
            ask.append(q, ans);
            win.body.append(formField('Can I supply an order of…', ask, { cls: 'stock-item-ask' }));
            const days = f.days_to_stockout;
            const runOut = days == null ? 'not selling at the moment' : days < 1 ? 'out now' : 'about ' + Math.round(days) + ' days (' + day(days) + ')';
            const facts = dataTable([[null, 'kt-main'], [null, 'num']], { head: false, cls: 'stock-item-facts' });
            const fact = (k, v) => { const tr = el('tr'); const td = el('td', 'num'); td.append(v); tr.append(el('td', null, k), td); facts.add(tr); };
            fact('Runs out', runOut);
            fact('Supplier', (it.supplier || 'None') + (lead ? ' · ' + lead + ' day delivery' : ''));
            if (arrive) { const s = document.createDocumentFragment(); s.append('arrives around ', el('b', null, arrive)); fact('If ordered today', s); }
            fact('Reorder level', it.reorder_point ? 'at or below ' + it.reorder_point : 'not set');
            fact('Value on hand', stockGbp(it.current_value || 0));
            win.body.append(facts.wrap);
            const foot = win.foot();
            const hist = textButton('History', { icon: I.history }); hist.type = 'button';
            hist.onclick = () => openStockHistory(it, hist);
            const count = textButton('Correct count', { icon: I.edit }); count.type = 'button';
            count.onclick = () => { win.close(); stockShowInventory(stockCode(it)); };
            const recv = textButton('Receive stock', { kind: 'primary', icon: I.truck }); recv.type = 'button';
            /* The Deliveries area's window, when it is on the page. */
            const receiveOne = typeof openStockReceiveOne === 'function' ? openStockReceiveOne : null;
            recv.onclick = () => { if (receiveOne) { win.close(); receiveOne(it, opener); } };
            foot.append(hist, count, recv);
        }

        /* ---------- a line's own history ----------
           Every change to the line under every name it has had, newest first:
           what changed, when, who, from what to what, and why. */
        async function openStockHistory(item, opener) {
            const name = stockName(item) || item.name || 'Stock line';
            const win = dialog({ title: 'History of ' + name, size: 'wide', opener: opener, bodyClass: 'stock-hist' });
            win.body.append(el('div', 'setting-sub', 'Loading…'));
            let d;
            try { d = await stockRead('history', 'item', { id: item.id }); }
            catch (e) {
                win.body.innerHTML = '';
                win.body.append(loadFailure('The history could not be read. ' + (e.message || ''), () => { win.close(); openStockHistory(item, opener); }));
                return;
            }
            win.body.innerHTML = '';
            /* Newest first by when it happened: the moved-in history's ids are not always in time order. */
            const rows = (d.history || []).slice().sort((x, y) => String(y.at || '').localeCompare(String(x.at || '')));
            if (!rows.length) { win.body.append(emptyState({ icon: I.history, text: 'Nothing has changed on this line yet.' })); return; }
            /* The same columns, words and people as Activity's history, without its Item column. */
            const t = dataTable(['When', 'Who', ['Action', 'kt-main'], 'Field', ['Before', 'num'], ['After', 'num'], 'Detail']);
            rows.forEach(h => {
                const moved = h.field && h.old_value !== '' && h.new_value !== '';
                const tr = el('tr');
                const who = el('td'); who.append(stockWhoNode(h));
                tr.append(el('td', null, stockOvWhen(h.at)), who, el('td', null, stockWords(h.action, STOCK_ACTIONS)),
                          el('td', null, h.field ? stockWords(h.field, STOCK_FIELDS) : ''),
                          el('td', 'num', moved ? h.old_value : ''), el('td', 'num', moved ? h.new_value : ''),
                          el('td', 'stock-hist-why', h.detail || ''));
                t.add(tr);
            });
            win.body.append(t.wrap);
            if (rows.length >= 200) win.body.append(el('p', 'card-sub', 'The newest 200 changes. The Activity tab searches them all.'));
        }
