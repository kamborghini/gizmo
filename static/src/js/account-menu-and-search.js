        /* ---------- the account menu and the page search ---------- */
        const ROLE_LABELS = { master: 'Master admin', admin: 'Admin', member: 'Member', parttime: 'Part-time' };
        function sideInitials(name) {
            return String(name || '').trim().split(/\s+/).slice(0, 2).map(w => w[0] || '').join('').toUpperCase() || '?';
        }
        /* The account row opens a menu holding the footer's old buttons. Each
           item presses the hidden original, so the role gating and the clock's
           own label keep working exactly as they did. */
        function userMenu() {
            const items = [];
            const sb = $('settings-btn'), ck = $('clock-btn');
            if (sb && sb.style.display !== 'none') items.push({ label: 'Settings', icon: I.settings, onClick: () => sb.click() });
            if (ck && ck.style.display !== 'none') items.push({ label: ck.textContent.trim() || 'Clock', icon: I.clock, onClick: () => ck.click() });
            /* Where the sidebar's support card was: it took a sixth of the
               sidebar on every page and was not there at all on a phone. */
            items.push({ label: 'Ask for a feature', icon: I.plus, onClick: () => { const v = currentView(); closeSidebar(); askFeature(v); } });
            items.push({ label: 'Guide and what\u2019s new', icon: I.helpCircle, onClick: () => setView('guide') });
            items.push('-');
            items.push({ label: 'Log out', icon: I.logOut, onClick: () => authLogout() });
            dropMenu($('side-user'), items);
            if (dmenuOpen) {
                const panel = dmenuOpen.panel, r = $('side-user').getBoundingClientRect();
                panel.style.minWidth = r.width + 'px';
                /* On a desktop it opens to the right of the sidebar, level with
                   the account row, as the reference's user menu does: opened
                   upward it covered the support card and left that card's
                   heading showing above it. The drawer keeps it above. */
                if (!window.matchMedia('(max-width: 900px)').matches) {
                    panel.style.left = Math.round(r.right + 8) + 'px';
                    panel.style.top = Math.round(Math.max(8, r.bottom - panel.offsetHeight)) + 'px';
                }
            }
        }
        /* Every page the sidebar offers, with the group it sits under, read off
           the sidebar itself so a tab hidden by its permission stays hidden here. */
        function navEntries() {
            const out = []; let group = '';
            [...document.querySelectorAll('.nav .nav-group, .nav .nav-item')].forEach(n => {
                if (n.classList.contains('nav-group')) { group = [...n.childNodes].filter(c => c.nodeType === 3).map(c => c.textContent).join('').trim(); return; }
                if (!n.classList.contains('nav-item') || n.style.display === 'none') return;
                const label = [...n.childNodes].filter(c => c.nodeType === 3).map(c => c.textContent).join('').trim();
                out.push({ view: n.dataset.view, label, group, icon: n.querySelector('.ic') });
            });
            return out;
        }
        function openSearch() {
            const anchor = $('topbar-search');
            dropPanel(anchor, (body, close) => {
                body.classList.add('dpanel-search');
                const entries = navEntries();
                /* Fixtures too, for anyone who can open the Size list. */
                const fixtures = entries.some(e => e.view === 'sizes');
                const what = fixtures ? 'Go to a page, find a fixture or search the guide' : 'Go to a page, or search the guide';
                const inp = document.createElement('input');
                inp.type = 'search'; inp.placeholder = what + '\u2026'; inp.setAttribute('aria-label', what);
                const list = el('div', 'dsearch-list'); list.setAttribute('role', 'listbox');
                let askedSheet = false;
                /* The guide's entries too, under Help: 'booking fails' found
                   nothing, and neither did 'help'. */
                const help = guideFor().flatMap(sec => sec.body.map(([t, d]) => ({ sec, t, d: guideText(d) })));
                const paint = () => {
                    const q = inp.value.trim().toLowerCase();
                    list.innerHTML = '';
                    const hits = entries.filter(e => !q || (e.label + ' ' + e.group + (e.view === 'guide' ? ' help' : '')).toLowerCase().indexOf(q) >= 0);
                    const words = q.split(/\s+/).filter(w => w.length > 2);
                    const helpHits = q.length < 3 ? [] : help.filter(h => { const x = (h.t + ' ' + h.d).toLowerCase(); return x.includes(q) || (words.length > 1 && words.every(w => x.includes(w))); }).slice(0, 6);
                    const askSheet = fixtures && q.length >= 2;
                    if (askSheet && (!sizesCache || sizesCache.error) && !askedSheet) {
                        // Read once, then this list is painted again with the sheet in it.
                        askedSheet = true;
                        sizesEnsure().then(() => { if (inp.isConnected) paint(); });
                    }
                    const fx = askSheet ? sizesFind(inp.value, 5) : { rows: [], toks: [] };
                    if (!hits.length && !helpHits.length && !fx.rows.length) {
                        list.append(el('div', 'dmenu-label', askSheet && sizesLoading ? 'Looking through the size list\u2026' : 'Nothing matches.'));
                        return;
                    }
                    helpHits.forEach((h, k) => {
                        if (!k) list.append(el('div', 'dmenu-label', 'Help'));
                        const b = el('button', 'dmenu-item'); b.type = 'button'; b.setAttribute('role', 'option');
                        b.append(ico(I.helpCircle), el('span', null, h.t));
                        b.title = h.sec.h;
                        b.onclick = () => { close(); openGuideAt(h.sec.id, h.t); };
                        list.append(b);
                    });
                    let lastGroup = null;
                    hits.forEach(e => {
                        if (e.group !== lastGroup) { list.append(el('div', 'dmenu-label', e.group)); lastGroup = e.group; }
                        const b = el('button', 'dmenu-item'); b.type = 'button'; b.setAttribute('role', 'option');
                        if (e.icon) b.append(e.icon.cloneNode(true));
                        b.append(el('span', null, e.label));
                        b.onclick = () => { close(); setView(e.view); };
                        list.append(b);
                    });
                    fx.rows.forEach((r, k) => {
                        if (!k) list.append(el('div', 'dmenu-label', 'Size list'));
                        const b = el('button', 'dmenu-item'); b.type = 'button'; b.setAttribute('role', 'option');
                        const nm = el('span'); nm.append(sizesMarked(r.manufacturer + ' ' + r.model, fx.toks));
                        const v = r.ruling === 'exclude' ? '' : sizesEff(r);
                        b.append(ico(I.ruler), nm, el('span', 'dsearch-sub', r.ruling === 'exclude' ? 'Not a gobo' : v ? v + ' mm' : 'No size'));
                        b.onclick = () => { close(); openSizeRow(inp.value, r); };
                        list.append(b);
                    });
                };
                inp.oninput = paint;
                inp.onkeydown = (ev) => {
                    if (ev.key !== 'Enter') return;
                    const first = list.querySelector('.dmenu-item');
                    if (first) { ev.preventDefault(); first.click(); }
                };
                body.append(inp, list); paint();
            });
        }
