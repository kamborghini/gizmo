        /* ---------- SEO audit ---------- */
        let seoCache = null;
        async function loadSEO(force) {
            const box = $('seo-content');
            if (reportRuns.seo) return reportRuns.seo;
            if (seoCache && !force) { renderSEO(seoCache); return; }
            return (reportRuns.seo = runSEO(box).finally(() => { reportRuns.seo = null; }));
        }
        async function runSEO(box) {
            box.innerHTML = '';
            const hero = pageHead({ view: 'seo', title: 'SEO' }); box.append(hero);
            const t = el('div', 'thinking');
            t.append(loader(), el('span', null, 'Crawling pages: indexation, structured data, metadata and alt text.'));
            box.append(t);
            try { const data = await api('/api/seo', {}); seoCache = { data, at: Date.now() }; renderSEO(seoCache); }
            catch (e) {
                reportFailed(box, hero, 'The audit could not be run. ' + (e.message || String(e)),
                    seoCache ? () => renderSEO(seoCache) : null, () => loadSEO(true));
            }
        }
        function renderSEO(cache) {
            const data = cache.data; const box = $('seo-content'); box.innerHTML = '';
            const intro = firstPaint('seo'); box.classList.toggle('no-intro', !intro);
            const s = data.structured || {};
            box.append(pageHead({ view: 'seo', title: 'SEO', live: cache.at, onRefresh: () => loadSEO(true), actions: [refreshAllBtn()] }));
            summaryAndChanges(box, data.changes, data.changes_since, s.summary, followedNote(s));
            /* Every block from the checks to the page chat is a card the grid can
               move; the header stays fixed at the top. */
            // Score + KPI strip
            /* No number when the product read failed: the score is left out
               rather than read as passing the checks that never ran. */
            /* The score is the first figure of the checks, one group on one line
               (12 Oct 2026, DF-11): its label, the figure in its tier colour,
               out of 100, and its meter. */
            const scored = typeof data.score === 'number';
            const mets = (data.metrics || []).filter(m => m.label !== 'SEO score');
            const strip = mets.length ? metricsStrip(withSparks(mets, data.trends))
                : (scored || data.score_note) ? el('div', 'metrics metrics-strip') : null;
            if (scored || data.score_note) {
                const tier = !scored ? '' : data.score >= 80 ? ' good' : data.score >= 60 ? ' mid' : ' low';
                const sc = el('div', 'stat seo-score' + tier);
                sc.append(el('div', 'label', 'SEO score'));
                const row = el('div', 'stat-row'); row.append(el('div', 'value', scored ? String(data.score) : 'n/a')); sc.append(row);
                /* The note and the meter are one foot: on a phone a tile is three rows of its
                   group's subgrid, and a fourth child was drawn across "out of 100". */
                const foot = el('div', 'seo-foot'); foot.append(el('p', 'stat-note', scored ? 'out of 100' : data.score_note));
                if (scored) {
                    const bar = el('div', 'bar'); const fill = el('i');
                    fill.style.width = Math.max(0, Math.min(100, data.score)) + '%'; bar.append(fill);
                    foot.append(bar);
                }
                sc.append(foot);
                /* The score opens its own breakdown, like the seven checks under
                   it: the server sends how the score is made, and the one figure
                   on the page that could not be opened was the headline. */
                const sm = (data.metrics || []).find(m => m.label === 'SEO score');
                if (sm && sm.detail && (sm.detail.items || []).length) statOpens(sc, sm);
                strip.prepend(sc);
            }
            /* Its own id: a layout that hid the old Checks must not hide the score with them. */
            /* In a host that knows its width, so eight figures run four and four when a line cannot hold them. */
            if (strip) { const host = el('div', 'fig-host'); host.append(strip); box.append(widget(host, 'score-checks', 'full', 'Score and checks')); }
            renderSeoTrends(box, data.trends, seoRange, (v) => { seoRange = v; }, intro, 'trends');
            // Lead with money opportunities, then findings, then supporting detail
            if (Array.isArray(s.actions) && s.actions.length) {
                box.append(widget(el('div', 'section-title', 'Top opportunities'), 'opportunities'));
                box.append(actionsCard(s.actions));
            }
            if (Array.isArray(s.insights) && s.insights.length) {
                box.append(widget(el('div', 'section-title', 'Performance findings'), 'findings'));
                const b = el('div', 'insights'); s.insights.forEach((ins, i) => b.append(insightCard(ins, i))); box.append(b);
            }
            if (Array.isArray(s.sections) && s.sections.length) {
                box.append(widget(el('div', 'section-title', 'Details'), 'details'));
                s.sections.forEach(sec => box.append(sectionCard(sec)));
            }
            const chat = pageChatPanel('seo', data);
            box.append(chat);
            cardifySections(box);
            pairNodes(wgChild(box, 'opportunities'), wgChild(box, 'findings'), 'opportunities', 'Top opportunities and findings');
            pairNodes(wgChild(box, 'details'), chat, 'details', 'Details and questions');
            syncPrintBtn();
        }

