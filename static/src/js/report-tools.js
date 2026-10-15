        /* ---------- refresh all reports ----------
           On the four AI reports it runs, in their headers beside each one's
           own Refresh: it was the first control of the sidebar on every page,
           Guide and Chat included, a black button that spends AI credits,
           and it ran reports the account might not be allowed to open. */
        let refreshingAll = false, refreshAllLabel = 'Refresh all';
        const ALL_REPORTS = [['overview', 'Overview', () => loadOverview(true)], ['seo', 'SEO', () => loadSEO(true)],
                             ['keywords', 'Keywords', () => loadKeywords(true)], ['customers', 'Customers', () => loadCustomers(true)]];
        const allowedReports = () => ALL_REPORTS.filter(([v]) => tabAllowed(v));
        function refreshAllBtn() {
            const mine = allowedReports();
            if (mine.length < 2) return null;
            const b = el('button', 'btn btn-sm refresh-all-btn'); b.type = 'button';
            b.append(ico(I.rotate), el('span', 'nr-label', refreshingAll ? refreshAllLabel : 'Refresh all'));
            b.title = 'Run ' + mine.map(r => r[1]).join(', ') + ' again. Uses AI credits.';
            if (refreshingAll) setBusy(b, true);
            b.onclick = refreshAll;
            return b;
        }
        function setRefreshLabel(text) {
            refreshAllLabel = text;
            document.querySelectorAll('.refresh-all-btn .nr-label').forEach(l => { l.textContent = text; });
        }
        async function refreshAll() {
            if (refreshingAll) return;
            const steps = allowedReports();
            if (!await uiConfirm('Run ' + steps.map(r => r[1]).join(', ') + ' again now? This uses AI credits and can take a couple of minutes.', { title: 'Refresh all reports', okText: 'Refresh all' })) return;
            refreshingAll = true;
            document.querySelectorAll('.refresh-all-btn').forEach(b => setBusy(b, true));
            /* Independent audits, run together rather than one after the
               other: the wait is now the longest of them instead of the sum.
               The label counts finishes rather than naming one, because with
               four in flight "Refreshing SEO" would be picking one at random.
               Each loader still shows its own error in its own tab, and
               allSettled means one failing does not cancel the others. */
            let done = 0;
            setRefreshLabel('Refreshing (0 of ' + steps.length + ')\u2026');
            await Promise.allSettled(steps.map(([, , fn]) =>
                Promise.resolve().then(fn).finally(() => {
                    done += 1;
                    setRefreshLabel('Refreshing (' + done + ' of ' + steps.length + ')\u2026');
                })));
            refreshingAll = false;
            setRefreshLabel('Refresh all');
            document.querySelectorAll('.refresh-all-btn').forEach(b => setBusy(b, false));
            addToast('Reports refreshed.');
        }

        /* ---------- per-page "ask about this report" ---------- */
        const PAGE_LABELS = { overview: 'overview', seo: 'SEO audit', keywords: 'keyword analysis', customers: 'customer analysis' };
        const pageThreads = { overview: [], seo: [], keywords: [], customers: [] };
        // Customers is per sector: each sector is a different report, so it needs its own thread.
        const threadKey = (page) => (page === 'customers' && customersSeg && customersSeg !== SEG_ALL) ? ('customers:' + customersSeg) : page;
        const pageBusy = {};
        function pageReport(page, data) {
            const s = (data && data.structured) || {}; const rep = {};
            if (s.summary) rep.summary = s.summary;
            if (Array.isArray(data.metrics)) rep.metrics = data.metrics.map(m => ({ label: m.label, value: m.value }));
            if (Array.isArray(s.insights)) rep.insights = s.insights.map(i => ({ title: i.title, detail: i.detail, type: i.type }));
            if (Array.isArray(s.actions)) rep.actions = s.actions.map(a => ({ text: a.text, impact: a.impact }));
            if (Array.isArray(s.sections)) rep.sections = s.sections.map(x => ({ title: x.title, body: (x.body || '').slice(0, 400) }));
            if (typeof data.score === 'number') rep.score = data.score;
            if (page === 'keywords') {
                if (Array.isArray(data.keywords)) rep.top_keywords = data.keywords.slice(0, 12).map(k => ({ query: k.query, clicks: k.clicks, impressions: k.impressions, position: k.position }));
                if (data.ads && data.ads.totals) rep.ads_totals = data.ads.totals;
            }
            if (page === 'customers') {
                if (data.segment) rep.sector = data.segment;
                if (Array.isArray(data.segments)) rep.segments = data.segments.map(x => ({ name: x.name, count: x.count }));
                if (Array.isArray(data.sector_comparison) && data.sector_comparison.length) rep.sector_comparison = data.sector_comparison;
            }
            return rep;
        }
        function pageAssistant(page, t, data) {
            const m = el('div', 'msg assistant');
            const head = el('div', 'resp-head'); const av = el('span', 'av'); av.innerHTML = I.spark;
            head.append(av, el('span', 'who', 'Reactor'));
            if (deepTurn(t)) head.append(el('span', 'tag', 'Deep analysis'));
            m.append(head);
            renderStructured(m, t.structured || {}, { noFollowups: true });
            const fb = fellBackNote(t); if (fb) m.append(fb);
            if (Array.isArray(t.data_used) && t.data_used.length) m.append(dataDrill(t.data_used));
            const fu = (t.structured && t.structured.followups) || [];
            if (fu.length) m.append(followupChips(fu.slice(0, 4), q => pageAsk(page, q, data)));
            return m;
        }
        function renderPageThread(page, thread, data) {
            thread.innerHTML = '';
            const items = pageThreads[threadKey(page)] || [];
            if (!items.length) {
                const sugg = ((data.structured && data.structured.followups) || []).slice(0, 4);
                if (sugg.length) { thread.append(el('div', 'pchat-hint', 'Suggested questions')); thread.append(followupChips(sugg, q => pageAsk(page, q, data))); }
                return;
            }
            items.forEach((t, i) => {
                if (t.role === 'user') { const m = el('div', 'msg user'); m.append(el('div', 'bubble', t.text)); thread.append(m); }
                else if (t.role === 'error') {
                    const m = el('div', 'msg error pchat-err');
                    m.append(el('div', null, 'That question did not reach Reactor. ' + t.text));
                    const again = el('button', 'btn'); again.textContent = 'Ask again';
                    const q = (items[i - 1] || {}).text || '';
                    again.onclick = () => { pageThreads[threadKey(page)].splice(i - 1, 2); pageAsk(page, q, data); };
                    if (q) m.append(again);
                    thread.append(m);
                }
                else thread.append(pageAssistant(page, t, data));
            });
        }
        function pageChatPanel(page, data) {
            const wrap = el('div', 'page-chat');
            /* This heading labels the card below it, which is exactly what
               cardifySections marks a heading as when it walks the page. The
               walker stops at this panel because the panel carries its own
               heading, so it has to say so itself or it renders a size down
               from the two group headings above it on the same page. */
            const st = el('div', 'section-title', 'Ask about this ' + (PAGE_LABELS[page] || 'report'));
            st.dataset.carded = 'group';
            wrap.append(st);
            const card = el('div', 'card pchat');
            const thread = el('div', 'pchat-thread'); thread.id = 'pchat-thread-' + threadKey(page);
            renderPageThread(page, thread, data); card.append(thread);
            const row = el('div', 'pchat-input');
            const ta = el('textarea', 'pchat-ta'); ta.rows = 1; ta.placeholder = 'Ask a question about this report…';
            ta.addEventListener('input', () => { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 140) + 'px'; });
            /* While an answer is still coming, the question stays in the box:
               it was cleared first and then refused, gone without a word. */
            const sendIt = () => {
                if (pageBusy[threadKey(page)]) { addToast('Wait for the answer, then send this.'); return; }
                const v = ta.value; ta.value = ''; ta.style.height = 'auto'; pageAsk(page, v, data);
            };
            ta.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (!e.repeat) sendIt(); } });
            /* Plain, not teal (12 Oct 2026): a report's one teal is its own action, and Ask is a side door. */
            const btn = el('button', 'btn pchat-send'); btn.innerHTML = I.send; btn.title = 'Ask';
            btn.onclick = sendIt;
            row.append(ta, btn); card.append(row); wrap.append(card);
            return wrap;
        }
        async function pageAsk(page, text, data) {
            text = (text || '').trim(); if (!text) return;
            const tk = threadKey(page);
            if (pageBusy[tk]) return;   // guard BEFORE mutating the thread or drawing a spinner
            pageThreads[tk] = pageThreads[tk] || [];
            pageThreads[tk].push({ role: 'user', text });
            const thread = $('pchat-thread-' + tk); if (!thread) return;
            renderPageThread(page, thread, data);
            const tm = el('div', 'msg assistant'); const th = el('div', 'thinking'); th.append(loader(), el('span', null, 'Thinking…')); tm.append(th); thread.append(tm);
            try { tm.scrollIntoView({ block: 'nearest' }); } catch (e) {}
            pageBusy[tk] = true;
            const history = pageThreads[tk].filter(t => t.role !== 'error')
                .map(t => t.role === 'user' ? { role: 'user', content: t.text }
                                            : { role: 'assistant', content: structuredToText(t.structured) });
            const payload = { messages: history, deep: false, context: { page, report: pageReport(page, data) } };
            try {
                let res;
                try { res = await streamChat(payload, lbl => { const sp = th.querySelector('span'); if (sp && lbl) sp.textContent = lbl; }); }
                catch (se) { if ((se.message || '') === 'STREAM_TRANSPORT') res = await api('/api/chat', payload); else throw se; }
                pageThreads[tk].push({ role: 'assistant', structured: res.structured || { summary: 'Reactor did not send an answer. Ask again.' }, model: res.model, deep: res.deep, fell_back: res.fell_back, data_used: res.data_used });
                loadMemory('notes');
            } catch (e) {
                // NOT an assistant turn: an answer bubble carrying the words
                // "Failed to fetch" reads as the copilot's considered opinion.
                pageThreads[tk].push({ role: 'error', text: e.message || String(e) });
            } finally {
                pageBusy[tk] = false;
                const th2 = $('pchat-thread-' + tk);
                if (th2) { renderPageThread(page, th2, data); const last = th2.lastElementChild; if (last) { try { last.scrollIntoView({ block: 'nearest' }); } catch (e) {} } }
            }
        }

