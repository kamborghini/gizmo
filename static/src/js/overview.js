        /* ---------- overview ---------- */
        // Tabs stay idle until the user explicitly runs the task (no tokens/data on click).
        /* A report that has not run yet (the mix, spec 8.3): its page header
           with the one line saying what it is, then an empty state holding the
           cost and Run. Nothing fetches or spends until Run is pressed. */
        /* The cost of a run that uses AI, said in the same words on every gate that has one (Overview,
           SEO, Keywords, Customers): an empty state's line, 8 words. What a gate used to add to it sits
           behind its title's info button (o.more), word for word. */
        const RUN_COST = 'Uses AI credits only when you run it.';
        function renderRunGate(boxId, o) {
            const box = $(boxId); box.innerHTML = '';
            const btn = textButton(null, { kind: 'primary', cls: 'rg-btn' }); btn.textContent = o.cta; btn.onclick = o.onRun;
            box.append(pageHead({ view: o.view, title: o.title, line: o.desc,
                info: o.more ? infoButton('About this run', { title: o.title, body: o.more }) : null }),
                emptyState({ icon: o.icon, text: o.note, sub: o.covers, action: btn, cls: 'run-gate' }));
        }
        /* A paid report run in flight, by report. While one runs, its tab keeps
           the loading screen when you come back to it, and Run or Refresh
           waits on the run already going instead of paying for a second. */
        const reportRuns = {};
        function showOverviewView() {
            if (reportRuns.overview) return;
            if (overviewCache) { renderOverview(overviewCache); return; }
            renderRunGate('ov-content', { icon: I.grid, title: 'Overview', desc: 'Live figures and an AI summary of the store.', cta: 'Run overview', note: RUN_COST, covers: 'Shopify orders, Google Analytics 4 and Search Console.', onRun: () => loadOverview(true) });
        }
        function showSeoView() {
            if (reportRuns.seo) return;
            if (seoCache) { renderSEO(seoCache); return; }
            renderRunGate('seo-content', { icon: I.search, title: 'SEO', desc: 'Crawl the store and rank fixes by revenue.', cta: 'Run SEO audit', note: RUN_COST, covers: 'Indexation, structured data, metadata and alt text.', more: 'Takes up to a minute.', onRun: () => loadSEO(true) });
        }
        function showProductsView() {
            if (productPlanRun) return;   // a plan is being built: coming back keeps its loading screen
            if (productList) { renderProductList(); return; }
            renderRunGate('products-content', { icon: I.box, title: 'Products', desc: 'Your catalogue with up to 24 months of sales.', cta: 'Load products', note: 'Pulls live Shopify data. No AI credits used.', onRun: () => loadProducts(true) });
        }
        async function loadOverview(force) {
            const box = $('ov-content');
            if (reportRuns.overview) return reportRuns.overview;
            if (overviewCache && !force) { renderOverview(overviewCache); return; }
            return (reportRuns.overview = runOverview(box, force).finally(() => { reportRuns.overview = null; }));
        }
        async function runOverview(box, force) {
            box.innerHTML = '';
            /* The header alone while it runs: the loader says what is happening. */
            const hero = pageHead({ view: 'overview', title: 'Overview' }); box.append(hero);
            const t = el('div', 'thinking'); const orb = loader(); t.append(orb, el('span', null, 'Working out live metrics and insights.')); box.append(t);
            try {
                const data = await api('/api/overview', { fresh: !!force });
                overviewCache = { data, at: Date.now() }; renderOverview(overviewCache);
            } catch (e) {
                reportFailed(box, hero, 'The overview could not be built. ' + (e.message || String(e)),
                    overviewCache ? () => renderOverview(overviewCache) : null, () => loadOverview(true));
            }
        }
