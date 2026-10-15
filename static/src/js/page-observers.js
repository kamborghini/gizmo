        /* A switch that never reports its state is worse than no switch: a screen
           reader announces "switch" and stops. Most toggles are also built inside
           modals long after load, so this watches rather than runs once. */
        function syncToggles() {
            document.querySelectorAll('.toggle').forEach(t => {
                t.setAttribute('role', 'switch');
                if (!t.hasAttribute('tabindex')) t.tabIndex = 0;
                t.setAttribute('aria-checked', t.classList.contains('on') ? 'true' : 'false');
            });
        }
        syncToggles();
        let togglePass = 0;
        new MutationObserver(() => {
            // Batched: whole tabs repaint at once, and a sync per mutation would
            // run hundreds of times for one render.
            if (togglePass) return;
            togglePass = requestAnimationFrame(() => { togglePass = 0; syncToggles(); syncDialogs(); syncTableHeads(); syncPanels(); });
        }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
        /* Modals are built in thirteen places; the dialog semantics are stamped
           in one, the same way the switches get theirs above. The label comes
           from the modal's own heading. */
        /* R13: a table's heads, copied onto its body cells as data-h, so on a
           phone each row reads as two lines with every value named (see
           .ktable's phone rule). Tables are built in twenty places; they are
           stamped in one, as the switches and dialogs are. A head cell marked
           kt-main names the cell that leads its row; the first leads otherwise. */
        function syncTableHeads() {
            document.querySelectorAll('table.ktable > :is(tbody, tfoot) > tr:not([data-kh])').forEach(tr => {
                tr.dataset.kh = '';
                const hd = tr.closest('table').tHead, hr = hd && hd.rows[hd.rows.length - 1];
                if (!hr) return;
                const heads = [];
                /* A cell across several columns (a selection bar in the head) names none of them. */
                [...hr.cells].forEach(th => { for (let k = 0; k < (th.colSpan || 1); k++) heads.push(th.colSpan > 1 ? null : th); });
                let i = 0;
                [...tr.cells].forEach(td => {
                    const th = heads[i];
                    if (th && (td.colSpan || 1) === 1) {
                        const h = th.textContent.replace(/\s+/g, ' ').trim();
                        if (h && !td.hasAttribute('data-h')) td.dataset.h = h;
                        if (th.classList.contains('kt-main')) td.classList.add('kt-main');
                    }
                    i += td.colSpan || 1;
                });
            });
        }
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
        function syncDialogs() {
            document.querySelectorAll('.modal-overlay .modal').forEach(m => {
                if (m.getAttribute('role') === 'dialog') return;
                m.setAttribute('role', 'dialog');
                m.setAttribute('aria-modal', 'true');
                const h = m.querySelector('.modal-head h3');
                if (h) m.setAttribute('aria-label', h.textContent);
            });
        }
        syncDialogs();
        /* The observer above is rAF-batched, and rAF can lag in a throttled
           tab. A screen reader asks what it landed in the moment focus enters,
           so the stamp also runs synchronously right then. */
        document.addEventListener('focusin', (e) => {
            if (e.target && e.target.closest && e.target.closest('.modal-overlay')) syncDialogs();
        });
        /* One Tab fence for whichever modal is on top. Without it, Tab walked
           out of the overlay into the live page behind - which mattered twice
           over here, because Escape is deliberately not a way out. */
        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Tab') return;
            /* An open menu manages its own keys and closes on any outside
               press; the fence stands down rather than yanking Tab out of it. */
            if (document.querySelector('.dmenu')) return;
            const tops = [...document.querySelectorAll('.modal-overlay.show, .auth-overlay')]
                .filter(o => o.getClientRects().length);
            /* Stacking order, not DOM order: the login screen sits at z-200
               over everything, so when it is up - a session expiring with a
               modal open - it is the one Tab must serve, not the modal
               behind it. */
            const top = tops.find(o => o.classList.contains('auth-overlay')) || tops[tops.length - 1];
            if (!top) return;
            const focusables = [...top.querySelectorAll(
                'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
                .filter(f => !f.disabled && f.getClientRects().length);
            if (!focusables.length) return;
            const first = focusables[0], last = focusables[focusables.length - 1];
            if (!top.contains(document.activeElement)) { e.preventDefault(); first.focus(); return; }
            if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
            else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        });
        /* Focus into a window as it opens, and back to what opened it as it
           closes, for every window in one place. Thirteen builders make
           windows: sheetModal sent focus to its X, the rest left it on the
           page behind, and none gave it back, so closing one dropped a
           keyboard user at the top of the page. A window that redraws its
           page as it closes (a CRM deal redraws the board) replaces the
           control that opened it: the new one carries the same
           data-focus-key, and focus goes there once it is drawn. */
        const dialogOpeners = new WeakMap();
        function dialogOpened(o) {
            const now = document.activeElement;
            const from = now && now !== document.body && !o.contains(now) ? now : focusOutside;
            if (from && from.isConnected && !o.contains(from)) dialogOpeners.set(o, from);
            /* Two frames: a builder that focuses its own first field does so
               in the first, and is left alone. */
            requestAnimationFrame(() => requestAnimationFrame(() => {
                if (!o.isConnected || !o.classList.contains('show') || o.contains(document.activeElement)) return;
                const to = o.querySelector('.modal-head :is(button[title="Close"], button[aria-label="Close"])')
                    || [...o.querySelectorAll(DIALOG_FOCUSABLE)].find(f => !f.disabled && f.getClientRects().length);
                if (to) to.focus();
            }));
        }
        function dialogClosed(o) {
            const back = dialogOpeners.get(o);
            dialogOpeners.delete(o);
            if (!back) return;
            const lost = () => !document.activeElement || document.activeElement === document.body || !document.activeElement.isConnected;
            if (back.isConnected) { if (lost()) back.focus(); return; }
            const key = back.dataset && back.dataset.focusKey;
            if (!key) return;
            let tries = 0;
            const look = () => {
                const twin = document.querySelector('[data-focus-key="' + CSS.escape(key) + '"]');
                if (twin) { if (lost()) twin.focus(); return; }
                if (++tries < 60) setTimeout(look, 50);
            };
            look();
        }
        new MutationObserver(records => {
            for (const r of records) {
                r.addedNodes.forEach(n => { if (n.classList && n.classList.contains('modal-overlay') && n.classList.contains('show')) dialogOpened(n); });
                r.removedNodes.forEach(n => { if (n.classList && n.classList.contains('modal-overlay')) dialogClosed(n); });
            }
        }).observe(document.body, { childList: true });
        /* The windows written into the page (Settings) open and close by
           their show class instead of being added and removed. */
        document.querySelectorAll('.modal-overlay').forEach(o => new MutationObserver(() => {
            if (o.classList.contains('show')) { if (!dialogOpeners.has(o)) dialogOpened(o); }
            else if (dialogOpeners.has(o)) dialogClosed(o);
        }).observe(o, { attributes: true, attributeFilter: ['class'] }));
        document.addEventListener('keydown', (e) => {
            const t = e.target;
            if (t && t.classList && t.classList.contains('toggle') && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); t.click(); }
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

