        /* What the page still stamps after drawing (stage 3 retires these one
           part at a time): panels. Every switch says its own state now
           (setSwitch, js/part-field.js), and every table names its own cells
           (dataTable, js/part-table.js). */
        let stampPass = 0;
        new MutationObserver(() => {
            // Batched: whole tabs repaint at once, and a sync per mutation would
            // run hundreds of times for one render.
            if (stampPass) return;
            stampPass = requestAnimationFrame(() => { stampPass = 0; syncPanels(); });
        }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
        /* PANELS (13 Oct 2026, docs/superpowers/specs/2026-10-13-panels-design.md):
           every section of a page sits in a white panel on the grey page. A page's
           content root (.ov-wrap) holds its sections; panelTargets says which of
           its children, or of what they hold, is a panel, and the batched pass
           stamps .panel on them, so a page added next year is boxed without
           anyone wiring it. The header, tabs, choosers, notices, the queue's
           counters, Forecast's own tinted band and every notice (the ONE NOTICE
           recipe's classes) stay on the page, and Customise's
           grip and hide button, which a pair carries as children, are never panels. */
        const PANEL_SKIP = ['ov-hero', 'page-tabs', 'tabs', 'seg-row', 'queues', 'segmented', 'back-btn', 'miss-strip', 'msg',
            'alerts-banner', 'cx-health', 'mail-viewwarn', 'mail-sendwarn', 'disp-warn', 'disp-await', 'mail-note', 'mail-hidden-note', 'resp-note',
            'fband', 'sr-only', 'wg-grip', 'wg-hide'];
        const PANEL_HOLD = ['wpair', 'wpair-in', 'fc-pair', 'fc-cols', 'crm-seg', 'crm-charts', 'guide-host', 'guide-grid', 'ds-page'];
        function panelTargets(n) {
            if (!n || !n.classList || n.tagName === 'INPUT' || n.tagName === 'SCRIPT') return [];
            if (PANEL_SKIP.some(c => n.classList.contains(c))) return [];
            if (!n.className || PANEL_HOLD.some(c => n.classList.contains(c))) return [...n.children].flatMap(panelTargets);
            return [n];
        }
        function syncPanels() {
            document.querySelectorAll('.ov-wrap').forEach(root => [...root.children].flatMap(panelTargets)
                .forEach(t => { if (!t.classList.contains('panel')) t.classList.add('panel'); }));
        }
        /* The sign-in screen is not a window and sits over everything (a
           session expiring with a window open): Tab stays on it. Windows keep
           their own fence (dialog(), js/part-dialog.js). */
        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Tab') return;
            const auth = [...document.querySelectorAll('.auth-overlay')].find(o => o.getClientRects().length);
            if (!auth) return;
            const focusables = [...auth.querySelectorAll(
                'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
                .filter(f => !f.disabled && f.getClientRects().length);
            if (!focusables.length) return;
            const first = focusables[0], last = focusables[focusables.length - 1];
            if (!auth.contains(document.activeElement)) { e.preventDefault(); first.focus(); return; }
            if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
            else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        });
        /* The widget grid's own live region, made at boot for the reason the
           toast host's is below, and kept apart from the toasts: a toast on
           every Alt+Arrow would be seen as well as heard. The hint beside it
           describes a card in Customize mode, and is hidden outside that mode. */
        (function () {
            const say = el('div', 'sr-only'); say.id = 'wg-status';
            say.setAttribute('role', 'status'); say.setAttribute('aria-live', 'polite');
            const hint = el('div', 'sr-only', 'Drag to rearrange. On a touch screen, press and hold first. With a keyboard, hold Alt and press the arrow keys.');
            hint.id = 'wg-hint'; hint.hidden = true;
            document.body.append(say, hint);
        })();
        /* The live region must exist BEFORE the first toast: content that
           arrives together with a brand-new region is unreliably announced. */
        (function () {
            const host = el('div'); host.id = 'toast-host';
            host.setAttribute('role', 'status'); host.setAttribute('aria-live', 'polite');
            document.body.append(host);
        })();
        $('menu-btn').onclick = toggleSidebar; $('backdrop').onclick = closeSidebar;
        $('side-hide').onclick = toggleSidebar;
        try { if (localStorage.getItem(LS_SIDEBAR) === 'closed') document.body.classList.add('sidebar-collapsed'); } catch (e) {}
        $('menu-btn').setAttribute('aria-expanded', String(!(document.body.classList.contains('sidebar-collapsed') || window.matchMedia('(max-width: 900px)').matches)));
        $('side-hide').setAttribute('aria-expanded', $('menu-btn').getAttribute('aria-expanded'));
        document.querySelector('.side-body').addEventListener('scroll', syncSideFade, { passive: true });
        window.addEventListener('resize', syncSideFade);
        if (window.ResizeObserver) new ResizeObserver(syncSideFade).observe(document.querySelector('.nav'));
        // A drop that misses its target must never let the browser navigate to
        // the dropped file: that would replace the whole app mid-task.
        document.addEventListener('dragover', (e) => e.preventDefault());
        document.addEventListener('drop', (e) => e.preventDefault());

