        /* ---------- wire up ---------- */
        document.querySelectorAll('.nav-item').forEach(n => n.onclick = () => setView(n.dataset.view));
        initNavGroups();
        $('new-convo').onclick = () => newConvo();
        $('send').onclick = () => send();
        /* Deep analysis belongs to the conversation it was switched on in:
           as one flag for the session, every later question everywhere went
           to the larger, dearer model until somebody noticed. */
        $('deep-toggle').onclick = function () {
            const c = active() || newConvo(false);
            c.deep = !c.deep; if (c.turns.length) save();
            syncComposer();
        };
        $('skill-pick').append(ico(I.book), document.createTextNode('Skills'));
        $('skill-pick').onclick = function () { pickSkills(this); };
        const input = $('input');
        /* On a touch screen there is no Shift, so Enter starts a new line and
           the button sends. */
        const TOUCH_ONLY = !!(window.matchMedia && window.matchMedia('(hover: none)').matches);
        input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !TOUCH_ONLY && !e.isComposing) { e.preventDefault(); if (!e.repeat) send(); } });
        input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 160) + 'px'; syncSend(); });

        // Restore the last results of the AI tabs from the server so reopening
        // the app shows them instantly. No tokens are spent until the merchant
        // clicks Refresh on a tab to recompute.
        function applyCachedAnalysis(d) {
            if (!d) return;
            const seed = (e) => (e && e.result) ? { data: e.result, at: Date.parse(e.at) || Date.now() } : null;
            overviewCache = seed(d.overview) || overviewCache;
            seoCache = seed(d.seo) || seoCache;
            keywordsCache = seed(d.keywords) || keywordsCache;
            if (d.customers_segments && typeof d.customers_segments === 'object') {
                for (const k in d.customers_segments) { const e = d.customers_segments[k]; if (e && e.result) customersCache[k] = { data: e.result, at: Date.parse(e.at) || Date.now() }; }
            }
            // re-render whichever analysis tab is open so the saved result replaces its Run gate
            if ($('view-overview').classList.contains('active')) showOverviewView();
            else if ($('view-seo').classList.contains('active')) showSeoView();
            else if ($('view-keywords').classList.contains('active')) showKeywordsView();
            else if ($('view-customers').classList.contains('active')) showCustomersView();
        }
        async function loadAnalysisCache() {
            try { applyCachedAnalysis(await api('/api/cache', {})); } catch (e) {}
        }

        const bootQP = new URLSearchParams(location.search);
        const bootLabels = bootQP.get('view') === 'labels';
        const bootOrderId = bootLabels ? parseInt(bootQP.get('id') || '0', 10) : 0;
        if (bootOrderId) skipLabelsAutoLoad = true;   // the deep link fetch owns the view
        if (bootOrderId) window.__pendingAdminLink = { id: bootOrderId, dispatch: bootQP.get('dispatch') === '1' };
        // Every content root is arranged from here on, whoever renders into it.
        WG_VIEWS.forEach(v => wgWatch(v));
        renderSidebar(); renderChat(); authBoot(); setView(bootLabels ? 'labels' : 'overview');
        if (bootOrderId) (bootQP.get('dispatch') === '1' ? dispatchFromAdminLink : printFromAdminLink)(bootOrderId);
        loadProfile();  // pull the saved store profile from the server (for the Settings modal)
        loadMemory('notes');   // the notes alone: Overview shows the open follow-ups; the Memory tab reads the rest when opened
        loadAnalysisCache();  // restore last AI-tab results (no tokens spent)
        /* The alerts are not read here: authBoot reads them once it knows
           who is signed in. A read here ran beside that one, so every boot
           asked twice, or asked signed out and read nothing. */

        // Demo hook for visual testing (no data exposed).
        /* A skill body is the one thing here worth minutes of typing, and it
           lives only in the field until Save. Dirty is computed from the DOM
           against what each field was RENDERED with, so there is no flag to go
           stale and opening a skill to read it does not prompt. The browser
           only honours this after the person has interacted with the page. */
        window.addEventListener('beforeunload', (e) => {
            /* Hidden fields count: a skill half written on the Skills tab is
               still there, unsaved, while someone reads another tab. */
            const dirty = [...document.querySelectorAll('.sk-input, .sk-textarea')]
                .some(f => f.isConnected && f.value !== (f.dataset.initial || ''));
            if (!dirty) return;
            e.preventDefault();
            e.returnValue = '';       // Chrome still wants this set
        });
        window.__demo = function (sample, ov) {
            setView('chat'); newConvo(false);
            active().turns.push({ role: 'user', text: 'How did my store do this week?' });
            active().turns.push({ role: 'assistant', structured: sample, model: 'claude-opus-5-5', deep: true });
            renderChat();
            if (ov) { overviewCache = { data: ov, at: Date.now() }; }
        };
        window.__demoSEO = function (d) { seoCache = { data: d, at: Date.now() }; $('nav-seo').click(); };
        window.__demoKeywords = function (d) { keywordsCache = { data: d, at: Date.now() }; setView('keywords'); };
        window.__demoScan = function (out, d) { renderScanResult(out || document.body, d); };
        window.__demoMem = function (list) { memories = list; $('nav-memory').click(); };
        window.__demoSkills = function (list) { skills = list || []; $('nav-skills').click(); };
        window.__demoKnow = function (k) { knowledge = k; knowledgeRead = true; setView('memory'); renderMemory(); };
        window.__demoImpact = function (list) { impact = list; setView('memory'); renderMemory(); };
        window.__demoProducts = function (pl) { productList = pl; productListAt = Date.now(); setView('products'); renderProductList(); };
        window.__demoCustomers = function (d, seg) { seg = seg || SEG_ALL; customersCache[seg] = { data: d, at: Date.now() }; customersSeg = seg; setView('customers'); };
        window.__demoCustomerTags = function (tags) { customerTags = tags || []; if ($('view-customers').classList.contains('active')) renderCustomers(customersSeg); };
        window.__demoCache = function (d) { applyCachedAnalysis(d); };
        window.__demoAdminLink = function (id) { setView('labels'); printFromAdminLink(id); };
        window.__demoLabels = function (data) { labelsCache = { data: data, at: Date.now() }; labelsMissing = null; setView('labels'); renderLabels(); };
        window.__demoShipping = function (cfg) { shippingCfg = cfg; };
        window.__demoAlerts = function (list) { alerts = list || []; if (overviewCache) renderOverview(overviewCache); };
        window.__demoChatData = function (du) { const c = active(); if (c && c.turns.length) { c.turns[c.turns.length - 1].data_used = du; renderChat(); } };
        window.__demoProductDetail = function (d) { setView('products'); renderProductDetail(d); };
        window.__demoCustomShip = function () { return openCustomShip(); };
        window.__demoCRM = { op: crmOp, render: function () { renderCRM(); }, load: loadCRM,
                             state: function () { return crmCache; } };
    })();
