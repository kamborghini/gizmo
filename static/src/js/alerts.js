        /* ---------- scheduled-change alerts ---------- */
        let alerts = [];
        async function loadAlerts() {
            try { const d = await api('/api/alerts', {}); if (d && Array.isArray(d.alerts)) alerts = d.alerts; } catch (e) {}
            if ($('view-overview').classList.contains('active') && overviewCache) renderOverview(overviewCache);
            privacyNotice();
        }
        /* The Overview banner shows only once a report has been run, so a
           privacy request waiting on an admin is also said on its own, once
           a visit, until someone opens it or closes the notice. */
        let privacyNoticed = false;
        function openPrivacyRequests() {
            $('settings-btn').click();
            setTimeout(() => { const t = $('privacy-sec'); if (t && !t.hidden) t.scrollIntoView({ block: 'start' }); }, 300);
        }
        function privacyNotice() {
            if (privacyNoticed || !connIsAdmin()) return;
            const waiting = (alerts || []).some(a => a.status === 'new' && a.tab === 'settings' && /privacy requests/i.test(a.metric || ''));
            if (!waiting) return;
            privacyNoticed = true;
            addToast('Privacy requests from Shopify are waiting for an admin.', null,
                { sticky: true, action: { label: 'Open', fn: openPrivacyRequests } });
        }
        async function alertOp(payload) {
            try { const d = await api('/api/alerts', payload); if (d && Array.isArray(d.alerts)) alerts = d.alerts; }
            catch (e) { toastError('That change was not saved. ' + (e.message || '')); }
            if (overviewCache) renderOverview(overviewCache);
        }
        function alertsBanner() {
            const fresh = (alerts || []).filter(a => a.status === 'new');
            if (!fresh.length) return null;
            const wrap = el('div', 'alerts-banner');
            const head = el('div', 'alerts-head'); head.append(ico(I.warning), document.createTextNode(fresh.length + ' change' + (fresh.length > 1 ? 's' : '') + ' since the last refresh'));
            const clear = el('button', 'alerts-clear'); clear.textContent = 'Dismiss all'; clear.onclick = () => alertOp({ op: 'clear' });
            head.append(clear); wrap.append(head);
            fresh.slice(0, 8).forEach(a => {
                /* Report, don't shred: a record from before the banner's fields were
                   settled still has a title or a detail, and a row that shows a dot
                   and a tilde has told the reader nothing. */
                const label = a.metric || a.title || a.detail || 'A change was recorded without a description';
                const lowerBetter = /position|at risk|unfulfilled|low stock|cpc|bounce/i.test(label);
                const good = a.pct == null ? null : (lowerBetter ? a.pct < 0 : a.pct > 0);
                const dir = good == null ? 'flat' : good ? 'up' : 'down';
                const row = el('div', 'alert-row');
                /* A size-list alert had nowhere to go: the only controls were
                   snooze and dismiss, while the actual fix lived in a CSV on the
                   volume. Dismissing it did not resolve anything - the model came
                   back on the next scan. Now the metric itself opens the size
                   check that can settle it. */
                let metric;
                if (/size list/i.test(label)) {
                    metric = textLink(null, { size: 'inline', cls: 'a-metric' });
                    metric.textContent = label;
                    metric.title = 'Open the size check and resolve this';
                    metric.onclick = () => { setView('labels'); runCoverage(); };
                } else if (a.tab === 'settings' && /privacy requests/i.test(label)) {
                    /* Where the request is dealt with, not just a notice of it. */
                    metric = textLink(null, { size: 'inline', cls: 'a-metric' });
                    metric.textContent = label;
                    metric.title = 'Open Settings, Privacy requests';
                    metric.onclick = openPrivacyRequests;
                } else {
                    metric = el('span', 'a-metric', label);
                }
                row.append(el('span', 'adot ' + dir), el('span', 'a-tab', a.tab_label || a.kind || ''), metric,
                    el('span', 'a-pct ' + dir, a.pct == null ? '~' : ((a.pct > 0 ? '+' : '') + a.pct + '%')));
                const x = iconButton(I.x, 'Dismiss', { size: 'small' }); x.onclick = () => alertOp({ op: 'dismiss', id: a.id });
                row.append(x); wrap.append(row);
            });
            return wrap;
        }
        function sectorSalesTable(rows, cur) {
            const days = (rows[0] && rows[0].days) ? rows[0].days : 28;
            const kt = dataTable(['Sector', ['Revenue (' + days + 'd)', 'num'], ['Orders', 'num'], ['Average order value', 'num']]);
            rows.forEach(r => {
                const tr = el('tr'); const c0 = el('td', 'kw');
                const sl = textLink(r.sector || '', { size: 'inline' });
                sl.title = 'Open this sector in Customers'; sl.onclick = () => { customersSeg = r.sector; setView('customers'); };
                c0.append(sl); tr.append(c0);
                tr.append(el('td', 'num', fmtMoney(r.revenue || 0, cur)));
                tr.append(el('td', 'num', (r.orders || 0).toLocaleString()));
                tr.append(el('td', 'num', fmtMoney(r.aov || 0, cur)));
                kt.add(tr);
            });
            return kt.wrap;
        }
        function changesStrip(changes, since) {
            if (!Array.isArray(changes) || !changes.length) return null;
            const wrap = el('div', 'changes-strip');
            const head = el('div', 'changes-head'); head.append(ico(I.rotate));
            let label = 'What changed';
            if (since) { const d = new Date(since); if (!isNaN(d)) label += ' since ' + fmtDate(since); }
            head.append(document.createTextNode(label)); wrap.append(head);
            const row = el('div', 'impact-deltas');
            changes.slice().sort((a, b) => Math.abs(b.pct || 0) - Math.abs(a.pct || 0)).slice(0, 8).forEach(ch => {
                const lowerBetter = /position|at risk|unfulfilled|low stock|cpc|bounce/i.test(ch.label || '');
                const good = ch.pct == null ? null : (lowerBetter ? ch.pct < 0 : ch.pct > 0);
                const cls = good == null ? 'flat' : good ? 'up' : 'down';
                const chip = el('div', 'idelta ' + cls);
                chip.append(el('span', 'il', ch.label), el('span', 'iv', ch.pct == null ? '~' : ((ch.pct > 0 ? '+' : '') + ch.pct + '%')));
                row.append(chip);
            });
            wrap.append(row); return wrap;
        }
        function renderOverview(cache) {
            const data = cache.data; const box = $('ov-content'); box.innerHTML = '';
            /* Set BEFORE anything is appended, so on a repaint no entrance
               animation starts at all rather than one being cut off part way. */
            const intro = firstPaint('overview'); box.classList.toggle('no-intro', !intro);
            { const ab = alertsBanner(); if (ab) box.append(ab); }
            box.append(pageHead({ view: 'overview', title: 'Overview', live: cache.at, onRefresh: () => loadOverview(true),
                actions: [refreshAllBtn()] }));
            /* The changes strip is a fixed block with no id, so it comes BEFORE
               the first card the grid can move: one between two cards would take
               the arrangement (and Customise) down. The AI summary is that first
               card, the page's first section (the mix, spec 8.3). */
            summaryAndChanges(box, data.changes, data.changes_since, data.structured && data.structured.summary, followedNote(data.structured));
            const ofu = memories.filter(m => m.type === 'followup' && m.status === 'open');
            /* Every block from here to the page chat is a card the grid can
               move. The alerts banner, the header and the changes strip above
               stay fixed at the top, and the page chat at the foot. Follow-ups
               and Sales by sector span the row, as they always have. Half width,
               the twelve tiles and one half card leave a hole the tiler closes
               by moving a card, and follow-ups come and go: without them the
               sector table jumped below the charts for someone who had never
               customized anything. */
            if (ofu.length) {
                box.append(widget(el('div', 'section-title', 'Open follow-ups'), 'followups'));
                const card = el('div', 'card actions');
                ofu.slice(0, 6).forEach(m => {
                    const row = el('div', 'action');
                    const ck = el('div', 'check'); ck.innerHTML = I.check; ck.title = 'Mark done';
                    ck.setAttribute('role', 'button'); ck.setAttribute('aria-label', 'Mark done'); ck.tabIndex = 0;
                    ck.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); ck.click(); } });
                    ck.onclick = (e) => { e.stopPropagation(); memOp({ op: 'set_status', id: m.id, status: 'done' }); };
                    row.append(ck, el('div', 'text', m.text));
                    card.append(row);
                });
                box.append(card);
            }
            /* Each KPI is a card of its own, straight on the page, so a tile
               can be moved or hidden by itself. No heading over them: once
               they can be scattered, a heading above the first labels nothing. */
            /* A figure with a trend keeps its own tile, so Customise still moves
               and hides each one; the counts with no trend are one figure group,
               not four tiles over holes (12 Oct 2026, DF-06). */
            if (Array.isArray(data.metrics) && data.metrics.length) {
                const all = withSparks(data.metrics, data.trends);
                const plain = all.filter(m => !m.spark);
                all.filter(m => m.spark).forEach((m, i) => box.append(widget(statCard(m, i), wgKpiId(m.label), 'sm', m.label)));
                if (plain.length) box.append(widget(metricsStrip(plain), 'kpi-counts', 'full', 'Counts'));
            }
            if (Array.isArray(data.sector_sales) && data.sector_sales.length) {
                const secW = widget(cardSection('Sales by sector', null,
                    sectorSalesTable(data.sector_sales, data.currency)), 'sectors');
                box.append(secW);
                pairNodes(secW, channelsCard(data.trends), 'sectors', 'Sales by sector and traffic by channel');
            } else {
                const ch = channelsCard(data.trends);
                if (ch) box.append(widget(ch, 'channels', 'full', 'Traffic by channel'));
            }
            renderTrendsBlock(box, data.trends, data.currency, ovRange, (v) => { ovRange = v; }, intro, 'trends', { noChannels: true });
            const s = Object.assign({}, data.structured); delete s.summary;
            /* The heading used to stand only over insights, which left figures
               or sections sent without any as a bare block between two cards,
               and a block with no id there stops the page being arranged. Under
               the heading they fold into the one card, whichever arrived. */
            /* The detail sections get their own Details card, as on the other
               four reports: under 'What's notable' they ran on after the last
               insight with no heading and no rule. */
            const secs = s.sections; delete s.sections;
            if (['metrics', 'insights'].some(k => Array.isArray(s[k]) && s[k].length))
                box.append(widget(el('div', 'section-title', 'What’s notable'), 'notable'));
            renderStructured(box, s, { noFollowups: true, ids: { actions: 'actions' } });
            if (Array.isArray(secs) && secs.length) {
                box.append(widget(el('div', 'section-title', 'Details'), 'details'));
                secs.forEach(sec => box.append(sectionCard(sec)));
            }
            const chat = pageChatPanel('overview', data);
            box.append(chat);
            cardifySections(box);
            /* The actions beside what is notable, the details beside the page's
               questions (12 Oct 2026, R6). */
            pairNodes(wgChild(box, 'actions'), wgChild(box, 'notable'), 'actions', 'Recommended actions and what is notable');
            pairNodes(wgChild(box, 'details'), chat, 'details', 'Details and questions');
            syncPrintBtn();
        }

