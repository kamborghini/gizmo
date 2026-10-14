        /* ---------- conversations ---------- */
        /* An empty conversation is reused, and kept only once it has a
           question: each New chat saved another empty one. */
        function newConvo(switchView) {
            if (!tabAllowed('chat')) return null;
            let c = active();
            if (!c || c.turns.length) {
                c = { id: uid(), title: 'New conversation', ts: Date.now(), updated: Date.now(), turns: [] };
                convos.unshift(c);
            }
            activeId = c.id; rememberActive();
            renderSidebar(); renderChat();
            if (switchView !== false) setView('chat');
            $('input') && $('input').focus();
            return c;
        }
        function rememberActive() { try { sessionStorage.setItem('sc_active_convo', activeId || ''); } catch (e) {} }
        function selectConvo(id) {
            if (!tabAllowed('chat')) return;
            convos = convos.filter(x => x.turns.length || x.id === id);
            activeId = id; rememberActive();
            const c = active(); if (c) c.unread = false;
            renderSidebar();
            if (currentView() === 'chat') renderChat(); else setView('chat');   // setView draws it
        }
        async function deleteConvo(id, ev) {
            ev.stopPropagation();
            const c = convos.find(x => x.id === id);
            const name = (c && c.title) ? c.title : 'this conversation';
            if (!await uiConfirm('Delete "' + name + '"? This cannot be undone.', { title: 'Delete conversation', okText: 'Delete' })) return;
            if (pending[id]) stopAnswer(id);
            convos = convos.filter(x => x.id !== id);
            goneConvos.add(id);
            if (activeId === id) { activeId = (convos.find(x => x.turns.length) || {}).id || null; rememberActive(); }
            save(); renderSidebar(); renderChat();
            /* Focus fell to the page; it goes back to the question box. */
            $('input').focus();
        }
        const convoFilter = { q: '' };
        /* Newest conversation first, by when it was last asked in, under
           Today, Yesterday, This week and Earlier; a search box once the list
           is long; the full name on hover; a dot on one that answered while
           you were elsewhere, and a spinner on one still working. */
        function renderSidebar() {
            const box = $('convos'); box.innerHTML = '';
            const list = convos.filter(c => c.turns.length || c.id === activeId);
            if (!list.length) { box.append(el('div', 'convo-empty', 'No conversations yet.')); return; }
            if (list.length > 10) {
                const f = el('input', 'field-sm convo-filter'); f.type = 'search'; f.placeholder = 'Find a conversation';
                f.setAttribute('aria-label', 'Find a conversation'); f.value = convoFilter.q;
                f.oninput = () => { convoFilter.q = f.value; paintRows(); };
                box.append(f);
            }
            const rows = el('div', 'convo-rows'); box.append(rows);
            const paintRows = () => {
                rows.innerHTML = '';
                const q = convoFilter.q.trim().toLowerCase();
                const shown = list.filter(c => !q || (c.title || '').toLowerCase().includes(q)
                    || c.turns.some(t => t.role === 'user' && (t.text || '').toLowerCase().includes(q)));
                if (!shown.length) { rows.append(el('div', 'convo-empty', 'No conversation matches.')); return; }
                const now = new Date(), d0 = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
                const band = (ms) => ms >= d0 ? 'Today' : ms >= d0 - 86400000 ? 'Yesterday' : ms >= d0 - 6 * 86400000 ? 'This week' : 'Earlier';
                let last = '';
                shown.forEach(c => {
                    const b0 = band(c.updated || c.ts || 0);
                    if (b0 !== last) { rows.append(el('div', 'convo-band', b0)); last = b0; }
                    // Delete has to be a real button to be reachable by keyboard, so the
                    // row cannot be one: a button may not contain another.
                    const row = el('div', 'convo' + (c.id === activeId ? ' active' : ''));
                    const b = el('button', 'title', c.title || 'Conversation');
                    b.title = c.title || '';
                    if (c.id === activeId) b.setAttribute('aria-current', 'true');
                    b.onclick = () => selectConvo(c.id);
                    row.append(b);
                    if (pending[c.id]) { const sp = el('span', 'convo-busy'); sp.append(loader()); sp.title = 'Working on an answer'; row.append(sp); }
                    else if (c.unread) { const dot = el('span', 'convo-dot'); dot.title = 'Answered'; dot.append(el('span', 'sr-only', 'answered')); row.append(dot); }
                    const del = el('button', 'del'); del.innerHTML = I.trash; del.title = 'Delete';
                    del.setAttribute('aria-label', 'Delete conversation: ' + (c.title || '')); del.onclick = (e) => deleteConvo(c.id, e);
                    row.append(del); rows.append(row);
                });
            };
            paintRows();
        }

