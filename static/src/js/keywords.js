        /* ---------- keywords + CPC ---------- */
        let keywordsCache = null;
        function showKeywordsView() {
            if (reportRuns.keywords) return;
            if (keywordsCache) { renderKeywords(keywordsCache); return; }
            renderRunGate('keywords-content', { icon: I.tag, title: 'Keywords',
                desc: 'Your keywords and ad spend, with a ranked plan.',
                cta: 'Run keyword analysis', note: RUN_COST, covers: 'Search Console keywords and Google Ads.', more: 'Reads Search Console and Analytics.',
                onRun: () => loadKeywords(true) });
        }
        async function loadKeywords(force) {
            const box = $('keywords-content');
            if (reportRuns.keywords) return reportRuns.keywords;
            if (keywordsCache && !force) { renderKeywords(keywordsCache); return; }
            return (reportRuns.keywords = runKeywords(box).finally(() => { reportRuns.keywords = null; }));
        }
        async function runKeywords(box) {
            box.innerHTML = '';
            const hero = pageHead({ view: 'keywords', title: 'Keywords' }); box.append(hero);
            const t = el('div', 'thinking'); t.append(loader(), el('span', null, 'Combining Search Console keywords with Google Ads. This can take up to a minute.')); box.append(t);
            try { const data = await api('/api/keywords', {}); keywordsCache = { data, at: Date.now() }; renderKeywords(keywordsCache); }
            catch (e) {
                reportFailed(box, hero, 'The keyword analysis could not be run. ' + (e.message || String(e)),
                    keywordsCache ? () => renderKeywords(keywordsCache) : null, () => loadKeywords(true));
            }
        }
        function keywordTable(rows) {
            const kt = dataTable(['Keyword', ['Clicks', 'num'], ['Impressions', 'num'], ['CTR', 'num'], ['Position', 'num']]);
            /* Fifteen, most clicks first, then Show all (12 Oct 2026): fifty rows
               ran 1,400px past the paid search beside it. */
            const n = Math.min(rows.length, 50);
            rows.slice(0, 50).forEach((q, i) => {
                const tr = el('tr'); const kw = el('td', 'kw'); kw.append(document.createTextNode(q.query || ''));
                if (i >= 15) tr.hidden = true;
                const pos = +q.position || 0;
                if (pos >= 11 && pos <= 20 && (q.impressions || 0) > 0) kw.append(el('span', 'kbadge', 'page 2'));
                else if (pos > 0 && pos < 4) kw.append(el('span', 'kbadge win', 'top 3'));
                tr.append(kw);
                tr.append(el('td', 'num', (q.clicks || 0).toLocaleString()));
                tr.append(el('td', 'num', (q.impressions || 0).toLocaleString()));
                tr.append(el('td', 'num', (q.ctr != null ? pct1(q.ctr) : '')));
                tr.append(el('td', 'num', pos ? pos.toFixed(1) : ''));
                kt.add(tr);
            });
            const wrap = kt.wrap;
            if (n > 15) {
                const more = el('div', 'kw-more');
                const b = textButton(null, { small: true }); b.type = 'button'; b.setAttribute('aria-expanded', 'false');
                b.append(document.createTextNode('Show all ' + n + ' keywords'), ico(I.chevDown));
                const note = el('span', 'lbl-meta', '15 of ' + n + ' shown, most clicks first');
                b.onclick = () => {
                    const open = b.getAttribute('aria-expanded') !== 'true';
                    kt.body.querySelectorAll('tr').forEach((tr, i) => { if (i >= 15) tr.hidden = !open; });
                    b.setAttribute('aria-expanded', String(open));
                    b.firstChild.textContent = open ? 'Show fewer' : 'Show all ' + n + ' keywords';
                    note.textContent = open ? 'All ' + n + ' shown, most clicks first' : '15 of ' + n + ' shown, most clicks first';
                };
                more.append(b, note); wrap.append(more);
            }
            return wrap;
        }
        function renderCPC(ads, cur) {
            if (!ads || !ads.totals || !ads.has_ads) {
                return el('div', 'empty', 'No paid search data yet.');
            }
            const frag = document.createDocumentFragment(); const t = ads.totals;
            const cpcFmt = (n) => money(n, cur, 2);
            /* The one KPI strip every report uses, so five figures fill their
               row rather than leaving ROAS alone on a second one, and the tiles
               match the strip at the top of the same page. */
            frag.append(metricsStrip([
                { label: 'Ad spend (90d)', value: fmtMoney(t.cost, cur) },
                { label: 'Average CPC', value: cpcFmt(t.cpc) },
                { label: 'Ad clicks', value: (t.clicks || 0).toLocaleString() },
                { label: 'Conversions', value: (t.conversions || 0).toLocaleString() },
                { label: 'ROAS', value: t.roas ? (t.roas + 'x') : 'n/a', tone: (t.roas && t.roas < 1) ? 'warn' : null },
            ]));
            if (Array.isArray(ads.campaigns) && ads.campaigns.length) {
                /* No margin of its own: it sits in the paid search group, whose
                   gap spaces it from the figures, as the figures' own bottom
                   margin did in the flow. */
                const kt = dataTable(['Campaign', ['Cost', 'num'], ['CPC', 'num'], ['Conv.', 'num'], ['ROAS', 'num']]);
                ads.campaigns.forEach(c => {
                    const tr = el('tr'); tr.append(el('td', 'kw', c.campaign || '(not set)'));
                    tr.append(el('td', 'num', fmtMoney(c.cost, cur)), el('td', 'num', cpcFmt(c.cpc)), el('td', 'num', (c.conversions || 0).toLocaleString()));
                    const roas = el('td', 'num', c.roas ? (c.roas + 'x') : '');
                    /* Losing money has to survive a black-and-white print and a
                       colour-blind reader, so it is said in words as well. */
                    if (c.roas && c.roas < 1) {
                        roas.classList.add('roas-under');
                        roas.append(el('span', 'roas-flag', 'below cost'));
                    }
                    tr.append(roas); kt.add(tr);
                });
                frag.append(kt.wrap);
            }
            return frag;
        }
        /* The result as rows of the card it sits in: the metadata and the
           on-page terms at the card's own gutter, then the findings, details
           and actions in a bleed holder so the bleed rules turn them into rows
           rather than three framed boxes inside the card. */
        function renderScanResult(out, d, bleed) {
            const ex = d.extracted || {};
            const m1 = el('div', 'kmeta'); m1.append(document.createTextNode('Scanned: '), el('b', null, d.url || '')); out.append(m1);
            if (ex.title) { const m = el('div', 'kmeta'); m.append(document.createTextNode('Title: '), el('b', null, ex.title)); out.append(m); }
            const terms = (ex.top_phrases && ex.top_phrases.length ? ex.top_phrases : ex.top_terms) || [];
            if (terms.length) {
                out.append(el('div', 'radar-h', 'Top on-page terms'));
                const chips = el('div', 'kchips');
                terms.slice(0, 16).forEach(tm => { const c = el('span', 'kchip'); c.append(el('b', null, tm.term), document.createTextNode(' ' + tm.count)); chips.append(c); });
                out.append(chips);
            }
            out.append(el('div', 'radar-h', 'How to compete'));
            renderStructured(bleed || out, d.structured || {}, { noFollowups: true });
        }
        function keywordScanCard() {
            /* The house card head, and no padding of its own: the card's child
               rule already gives the gutter, so its own sat everything 32px in
               while every other card's content sat at 16. */
            const card = el('div', 'card scan-card');
            const head = el('div', 'card-head');
            head.append(el('h3', 'card-title', 'Scan a URL for keywords'));
            card.append(head);
            const row = el('div', 'act-row');
            /* What to paste is the field's own hint (copy plan, Keywords #4). */
            const inp = el('input', 'scan-url'); inp.placeholder = 'A competitor or blog post address'; inp.type = 'url';
            inp.setAttribute('aria-label', 'Page to scan');
            const btn = textButton(null, { kind: 'primary' }); btn.append(ico(I.search), document.createTextNode('Scan'));
            row.append(inp, btn); card.append(row);
            const out = el('div', 'scan-out'); card.append(out);
            const bleed = el('div', 'card-bleed'); card.append(bleed);
            async function go() {
                const url = inp.value.trim(); if (!url || btn.disabled) return;
                out.innerHTML = ''; bleed.innerHTML = '';
                const t = el('div', 'thinking'); t.append(loader(), el('span', null, 'Reading the page and extracting keywords.')); out.append(t); btn.disabled = true;
                try { const d = await api('/api/keyword-scan', { url }); out.innerHTML = ''; renderScanResult(out, d, bleed); }
                catch (e) { out.innerHTML = ''; out.append(loadFailure('The page could not be scanned. ' + (e.message || String(e)), go)); }
                finally { btn.disabled = false; }
            }
            btn.onclick = go;
            inp.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); go(); } });
            return card;
        }
        let keywordsPaid = null;   // the paid search group, paired with the keywords after the page is carded
        function renderKeywords(cache) {
            const data = cache.data; const box = $('keywords-content'); box.innerHTML = '';
            const s = data.structured || {}; const cur = data.currency || '';
            box.append(pageHead({ view: 'keywords', title: 'Keywords', live: cache.at, onRefresh: () => loadKeywords(true), actions: [refreshAllBtn()] }));
            summaryAndChanges(box, data.changes, data.changes_since, s.summary, followedNote(s));
            /* The search figures and the URL scan are one band (12 Oct 2026); the
               ad spend is said once, under Paid search. */
            box.append(widget(keywordScanCard(), 'scan', 'full', 'Scan a URL for keywords'));
            const topMets = (Array.isArray(data.metrics) ? data.metrics : []).filter(m => !/^Ad spend/i.test(m.label));
            if (topMets.length) {
                const kpisW = widget(metricsStrip(topMets), 'kpis', 'full', 'Search figures');
                box.append(kpisW);
                pairNodes(kpisW, wgChild(box, 'scan'), 'kpis', 'Search figures and a URL scan');
            }
            if (Array.isArray(s.actions) && s.actions.length) { box.append(widget(el('div', 'section-title', 'Top keyword opportunities'), 'opportunities')); box.append(actionsCard(s.actions)); }
            if (Array.isArray(s.insights) && s.insights.length) { box.append(widget(el('div', 'section-title', 'Findings'), 'findings')); const b = el('div', 'insights'); s.insights.forEach((x, i) => b.append(insightCard(x, i))); box.append(b); }
            const ranked = Array.isArray(data.keywords) && data.keywords.length;
            const noAds = !(data.ads && data.ads.totals && data.ads.has_ads);
            if (!ranked && !data.gsc_connected && noAds) {
                /* Neither source connected: one notice that names both and
                   says where to connect them, not two cards of one sentence. */
                const n = el('div', 'card');
                const nh = el('div', 'card-head');
                /* The two sources, word for word, behind the title's info button
                   (the mix, spec 8.3: setup steps wait there, with the action). */
                const ul = el('ol', 'setup-steps');
                ul.append(el('li', null, 'Google Search Console, for the keywords you rank for and the clicks they bring.'));
                ul.append(el('li', null, 'Google Ads, linked to your GA4 property (GA4 Admin, then Product links, then Google Ads links), '
                    + 'for your spend, cost per click, conversions and ROAS.'));
                const nt = el('h3', 'card-title', 'Search data is not connected yet');
                nh.append(titleInfo(nt, infoButton('The two Google sources', { title: 'Search data', body: [ul] })));
                const na = el('div', 'card-act');
                const go = textButton(null, { small: true }); go.append(ico(I.settings), document.createTextNode('Open connections'));
                go.onclick = () => openSettings(); na.append(go); nh.append(na);
                n.append(nh);
                box.append(widget(n, 'search-data', 'full', 'Search data'));
            } else {
                box.append(widget(el('div', 'section-title', ranked ? 'Your keywords (Search Console, 90 days)' : 'Your keywords'), 'keywords'));
                box.append(ranked ? keywordTable(data.keywords)
                    : el('div', 'empty', data.gsc_connected ? 'No Search Console queries in this range yet.' : 'Connect Search Console to see your keywords.'));
                /* The paid search heading labels a figures grid and a table, which
                   the page's cardifySections would leave as a bare label over two
                   loose blocks, so the heading and both are one group built here. */
                const paid = widget(el('div', 'widget-group'), 'paid-search', 'full', 'Paid search (cost per click)');
                box.append(paid);
                keywordsPaid = paid;
                const paidHead = el('div', 'section-title', 'Paid search (cost per click)');
                /* How to link Google Ads, word for word, behind the title's info
                   button while there is nothing to show (copy plan, Keywords #8). */
                if (noAds) paidHead.append(infoButton('Linking Google Ads', { title: 'Paid search',
                    body: 'Link Google Ads to your GA4 property (GA4 Admin, then Product links, then Google Ads links), and your spend, CPC, conversions and ROAS will appear here.' }));
                paid.append(paidHead, renderCPC(data.ads, cur));
                cardifySections(paid);
            }
            if (Array.isArray(s.sections) && s.sections.length) { box.append(widget(el('div', 'section-title', 'Details'), 'details')); s.sections.forEach(sec => box.append(sectionCard(sec))); }
            const chat = pageChatPanel('keywords', data);
            box.append(chat);
            cardifySections(box);
            /* Opportunities beside the findings, your keywords beside paid
               search, the details beside the questions (12 Oct 2026, R6). */
            pairNodes(wgChild(box, 'opportunities'), wgChild(box, 'findings'), 'opportunities', 'Top keyword opportunities and findings');
            const paid = keywordsPaid; keywordsPaid = null;
            pairNodes(wgChild(box, 'keywords'), paid, 'keywords', 'Your keywords and paid search', { even: true });
            pairNodes(wgChild(box, 'details'), chat, 'details', 'Details and questions');
            syncPrintBtn();
        }

