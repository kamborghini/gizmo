        /* ---------- responsive sidebar ---------- */
        /* The phone drawer takes focus while it is open, the page behind it
           is out of reach, and Escape closes it: Tab walked into the page
           behind the backdrop, and the page you were on sat under the fold. */
        function openSidebar() {
            $('sidebar').classList.add('open'); $('backdrop').classList.add('show');
            $('main').inert = true; $('menu-btn').setAttribute('aria-expanded', 'true'); $('side-hide').setAttribute('aria-expanded', 'true');
            const cur = document.querySelector('.nav-item.active') || document.querySelector('.nav-item');
            if (cur) { cur.scrollIntoView({ block: 'nearest' }); cur.focus({ preventScroll: true }); }
        }
        function closeSidebar() {
            const was = $('sidebar').classList.contains('open');
            $('sidebar').classList.remove('open'); $('backdrop').classList.remove('show');
            $('main').inert = false;
            if (window.matchMedia('(max-width: 900px)').matches) { $('menu-btn').setAttribute('aria-expanded', 'false'); $('side-hide').setAttribute('aria-expanded', 'false'); }
            if (was && $('sidebar').contains(document.activeElement)) $('menu-btn').focus({ preventScroll: true });
        }
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && $('sidebar').classList.contains('open') && !document.querySelector('.modal-overlay.show, .dmenu')) closeSidebar();
        });
        /* An iPad turned to landscape with the drawer open docked the sidebar
           and left the page inert, with no backdrop to tap: every tap did
           nothing until a page was picked. Leaving the drawer's range closes it. */
        try { window.matchMedia('(max-width: 900px)').addEventListener('change', (e) => { if (!e.matches && $('sidebar').classList.contains('open')) closeSidebar(); }); } catch (e) {}
        /* One trigger, two jobs, as the reference's: on a phone the sidebar is
           a drawer over the page; on a desk it folds away and the page takes
           the width, and the choice is remembered. Cmd+B does the same. */
        const LS_SIDEBAR = 'sc_sidebar_v1';
        function toggleSidebar() {
            if (window.matchMedia('(max-width: 900px)').matches) {
                if ($('sidebar').classList.contains('open')) closeSidebar(); else openSidebar();
                return;
            }
            const closed = document.body.classList.toggle('sidebar-collapsed');
            $('menu-btn').setAttribute('aria-expanded', String(!closed));
            $('side-hide').setAttribute('aria-expanded', String(!closed));
            /* The button just pressed leaves the screen: focus follows to the
               one that brings the sidebar back, or to Hide sidebar again. */
            if (closed && document.activeElement === $('side-hide')) $('menu-btn').focus({ preventScroll: true });
            if (!closed && document.activeElement === $('menu-btn')) $('side-hide').focus({ preventScroll: true });
            try { localStorage.setItem(LS_SIDEBAR, closed ? 'closed' : 'open'); } catch (e) {}
        }
        function inEditable(t) { return !!t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable); }
        document.addEventListener('keydown', (e) => {
            if (!(e.metaKey || e.ctrlKey) || e.shiftKey || e.altKey) return;
            const k = (e.key || '').toLowerCase();
            if (k === 'b' && !inEditable(e.target)) { e.preventDefault(); toggleSidebar(); }
            else if (k === 'j') { e.preventDefault(); openSearch(); }
        });
