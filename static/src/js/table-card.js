        /* ---------- the reference's table card, in three pieces ----------
           A search field, a toolbar to hang it and the filters on, and a pager.
           Pieces rather than one component on purpose: the tables in this app
           differ in what they can even offer, and half of them are already
           built. What they all share is the chrome, and this is the chrome. */
        function tableSearch(placeholder, value, oninput) {
            const wrap = el('div', 'tbl-search');
            wrap.append(ico(I.search));
            const inp = document.createElement('input');
            inp.type = 'search';
            inp.placeholder = placeholder || 'Search\u2026';
            /* A placeholder is only a name until someone types. */
            inp.setAttribute('aria-label', (placeholder || 'Search').replace(/\u2026$/, ''));
            if (value) inp.value = value;
            /* Debounced 150ms: these callbacks repaint whole lists, and the
               file browser measured 1,912ms of blocked JS per keystroke on a
               broad term before its own debounce went in. */
            if (oninput) {
                inp.oninput = () => {
                    clearTimeout(inp._t);
                    inp._t = setTimeout(() => { inp._t = null; if (inp.isConnected) oninput(inp.value.trim()); }, 150);
                };
                /* Blur or Enter flushes a pending run, so a filter chip clicked
                   right after typing cannot act on a stale query. Only a
                   pending one: a spent timer's id made leaving the box repaint
                   the list mid-tap, and the first tap on a row was lost. */
                inp.onchange = () => {
                    if (inp._t) { clearTimeout(inp._t); inp._t = null; oninput(inp.value.trim()); }
                };
            }
            /* The house clear, replacing the browser's blue one. Hidden until
               there is a query, and it puts focus back in the field: clearing a
               search is almost always the start of the next one. */
            const clr = el('button', 'tbl-clear');
            clr.type = 'button'; clr.append(ico(I.x));
            clr.title = 'Clear search'; clr.setAttribute('aria-label', 'Clear search');
            const syncClear = () => {
                const on = !!inp.value;
                wrap.classList.toggle('has-q', on);
                clr.hidden = !on;
            };
            inp.addEventListener('input', syncClear);
            clr.onclick = () => {
                inp.value = ''; syncClear();
                clearTimeout(inp._t); inp._t = null;
                if (oninput) oninput('');
                inp.focus();
            };
            syncClear();
            wrap.append(inp, clr);
            wrap.input = inp;
            return wrap;
        }
        function tableTools(left, right) {
            const bar = el('div', 'tbl-tools');
            const l = el('div', 'tbl-tools-l');
            (left || []).filter(Boolean).forEach(n => l.append(n));
            bar.append(l);
            /* An empty right rail is still a flex item: at 375 it wrapped to a
               line of its own and cost 12px of card under a toolbar with
               nothing in it. The LEFT rail is always drawn even when empty,
               because space-between is what holds the right rail at the right
               edge and dropping the left one would move it. */
            const rk = (right || []).filter(Boolean);
            if (rk.length) { const r = el('div', 'tbl-tools-r'); rk.forEach(n => r.append(n)); bar.append(r); }
            return bar;
        }
        /* o.total is the count AFTER filtering, so the line reads as what the
           pager is actually paging through rather than what the store holds.
           Saying "1 to 25 of 4" while a search is on is how a filter gets
           mistaken for a data loss. */
        function tablePager(o) {
            const size = o.pageSize || 10;
            const total = o.total || 0;
            const pages = Math.max(1, Math.ceil(total / size));
            const page = Math.min(Math.max(1, o.page || 1), pages);
            const foot = el('div', 'tbl-foot');
            const noun = o.noun ? ' ' + o.noun : '';
            foot.append(el('div', 'tbl-count', o.count != null ? o.count
                : (total ? ((page - 1) * size + 1) + ' to ' + Math.min(page * size, total)
                           + ' of ' + total + noun
                         : 'Nothing to show')));
            const pag = el('div', 'tbl-pager');
            if (o.onSize) {
                const rows = el('div', 'tbl-rows');
                rows.append(el('span', null, 'Rows per page'));
                const sel = document.createElement('select');
                sel.setAttribute('aria-label', 'Rows per page');
                (o.sizes || [10, 25, 50, 100]).forEach(n => {
                    const op = document.createElement('option');
                    op.value = String(n); op.textContent = String(n);
                    if (n === size) op.selected = true;
                    sel.append(op);
                });
                sel.onchange = () => o.onSize(parseInt(sel.value, 10));
                rows.append(sel); pag.append(rows);
            }
            pag.append(el('div', 'tbl-page', 'Page ' + page + ' of ' + pages));
            const steps = el('div', 'tbl-steps');
            [[I.chevFirst, 'First page', 1, page <= 1],
             [I.chevLeft, 'Previous page', page - 1, page <= 1],
             [I.chev, 'Next page', page + 1, page >= pages],
             [I.chevLast, 'Last page', pages, page >= pages]].forEach(([icon, title, to, off]) => {
                const b = el('button', 'btn tbl-step');
                b.append(ico(icon)); b.title = title; b.setAttribute('aria-label', title);
                if (off) b.disabled = true; else b.onclick = () => o.onPage(to);
                steps.append(b);
            });
            pag.append(steps); foot.append(pag);
            return foot;
        }
        function cardifySections(root) {
            if (!root) return;
            [].slice.call(root.children).forEach(function (node) {
                if (!node.classList || !node.classList.contains('section-title')) return;
                if (node.dataset.carded) return;
                var body = [], n = node.nextElementSibling;
                /* A block that carries its own section-title IS its own section,
                   so it ends this one. Without this the page-chat panel - a
                   heading plus its own .card - was swept into whatever section
                   happened to precede it and wrapped a second time, which put a
                   bordered white card flush inside a bordered white card. */
                /* A card the widget grid can move is its own block too, so the
                   heading over the one before it does not sweep it in. */
                while (n && !(n.classList && n.classList.contains('section-title'))
                         && !(n.querySelector && n.querySelector('.section-title'))
                         && !(n.hasAttribute && n.hasAttribute('data-widget'))) {
                    body.push(n); n = n.nextElementSibling;
                }
                if (!body.length) return;
                /* Already card-shaped? Then this is a group label, not a header.
                   .actions is the exception that used to be in this list: it is
                   marked up as a card but it is a LIST, and leaving it out here
                   put two headings of the same rank on one SEO page in two
                   different treatments - "Top opportunities" bare at 18px on
                   the page gutter, "Performance findings" at 16px inside the
                   card three inches below it. Folded, it becomes a card title
                   like every other list on the page, and the bleed rules strip
                   the frame it no longer needs. */
                var hasCard = body.some(function (b) {
                    return b.classList && !b.classList.contains('actions')
                        && (b.classList.contains('card')
                        || b.classList.contains('chart-card') || b.classList.contains('charts-grid')
                        || b.classList.contains('metrics'));
                });
                if (hasCard) { node.dataset.carded = 'group'; return; }
                var card = el('div', 'card');
                /* A renderer marks the heading, because the card does not exist
                   until now: the card it becomes is the widget. A heading that
                   stays a group label keeps them and labels nothing the grid
                   can move, which is why a group is built by its renderer. */
                ['data-widget', 'data-size', 'data-widget-label'].forEach(function (a) {
                    if (node.hasAttribute(a)) card.setAttribute(a, node.getAttribute(a));
                });
                var head = el('div', 'card-head');
                var title = el('h3', 'card-title');
                // A control that lived in the heading becomes the card's action. An
                // info button is not one: it belongs to the words, so it stays in the title.
                [].slice.call(node.childNodes).forEach(function (c) {
                    if (c.nodeType === 1 && !c.classList.contains('info') && (c.classList.contains('segmented') || c.tagName === 'BUTTON'
                        || c.classList.contains('tabs'))) {
                        var act = head.querySelector('.card-act') || el('div', 'card-act');
                        act.append(c); if (!act.parentNode) head.append(act);
                    } else { title.append(c); }
                });
                head.insertBefore(title, head.firstChild);
                card.append(head);
                var wrap = el('div', 'card-bleed');
                body.forEach(function (b) { wrap.append(b); });
                card.append(wrap);
                node.parentNode.insertBefore(card, node);
                node.remove();
            });
        }
        function insightCard(ins, i) {
            const type = ['win', 'warning', 'opportunity', 'insight'].includes(ins.type) ? ins.type : 'insight';
            const c = el('div', 'insight ' + type); c.style.animationDelay = (i * 50) + 'ms';
            const icon = el('span', 'ico'); icon.innerHTML = I[type] || I.insight;
            const body = el('div'); body.append(el('div', 't', ins.title || ''));
            if (ins.detail) body.append(el('div', 'd', ins.detail));
            c.append(icon, body); return c;
        }
        function bodyToNodes(text) {
            const frag = document.createDocumentFragment();
            const lines = String(text || '').split('\n');
            let ul = null;
            for (let i = 0; i < lines.length; i++) {
                const t = lines[i].trim();
                /* A Markdown table is a table: it showed as rows of pipes. */
                if (t.startsWith('|') && i + 1 < lines.length && mdTableRule(lines[i + 1].trim())) {
                    const rows = [];
                    while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(lines[i++].trim());
                    i--; ul = null; frag.append(pipeTable(rows)); continue;
                }
                if (t.startsWith('- ') || t.startsWith('• ')) {
                    if (!ul) { ul = el('ul'); frag.append(ul); }
                    ul.append(el('li', null, t.slice(2)));
                } else { ul = null; if (t) frag.append(el('p', null, t)); }
            }
            return frag;
        }
        function sectionCard(s, open, onToggle) {
            const d = el('details', 'sect');
            if (open) d.open = true;
            /* Setting open queues a toggle event of its own; only a change
               the reader made is passed on (each one saved every stored
               conversation, a second's freeze on opening a long one). */
            let was = !!open;
            if (onToggle) d.addEventListener('toggle', () => { if (d.open !== was) { was = d.open; onToggle(d.open); } });
            const sum = el('summary'); sum.append(document.createTextNode(s.title || 'Details'));
            const chev = el('span', 'chev'); chev.innerHTML = I.chev; sum.append(chev);
            const body = el('div', 'body'); body.append(bodyToNodes(s.body));
            d.append(sum, body); return d;
        }
        /* state (chat): the answer itself, which keeps done {i: true} and
           tracked {i: id}, and persist saves it; so a tick and Tracking
           survive a redraw. They lived in the page alone, and a second Track
           made a second copy. */
        function actionsCard(actions, source, state, persist) {
            const card = el('div', 'card actions');
            /* The table's heads, on a page (an answer in chat keeps its list). */
            if (!state) {
                const h = el('div', 'action-head');
                h.append(el('span'), el('span', null, 'Action'), el('span', null, 'Priority'), el('span'));
                card.append(h);
            }
            actions.forEach((a, i) => {
                const row = el('div', 'action');
                const ck = el('div', 'check'); ck.innerHTML = I.check;
                // The role goes on the box, not the row: the row also holds the
                // Track button, and a role=button row would swallow "Track" into
                // its own name and prune the button out of the tree.
                ck.setAttribute('role', 'button');
                ck.setAttribute('aria-label', 'Mark done: ' + String(a.text || '').slice(0, 60)); ck.tabIndex = 0;
                ck.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); ck.click(); } });
                const isDone = !!(state && state.done && state.done[i]);
                row.classList.toggle('done', isDone); ck.setAttribute('aria-pressed', String(isDone));
                /* The box ticks, not the row: dragging across the text to copy
                   it crossed the action out. */
                ck.onclick = () => {
                    const on = row.classList.toggle('done'); ck.setAttribute('aria-pressed', String(on));
                    if (state) { state.done = state.done || {}; if (on) state.done[i] = true; else delete state.done[i]; persist(); }
                };
                row.append(ck, el('div', 'text', a.text || ''));
                if (a.priority) { const p = el('span', 'pill ' + a.priority, cap(a.priority)); p.title = cap(a.priority) + ' priority'; row.append(p); }
                else row.append(el('span', 'pill-none'));   // keeps Track in its column
                const track = el('button', 'track-btn'); track.type = 'button';
                const tracking = () => { track.replaceChildren(ico(I.check), document.createTextNode('Tracking')); track.classList.add('on'); track.setAttribute('aria-pressed', 'true'); track.title = 'Measured under Tracked changes in Memory'; };
                if (state && state.tracked && state.tracked[i]) tracking();
                else { track.append(ico(I.tag), document.createTextNode('Track')); track.title = 'Snapshot your figures now and measure this change over time'; }
                track.onclick = async (e) => {
                    e.stopPropagation();
                    if (track.classList.contains('on')) { setView('memory'); return; }
                    if (track.disabled) return;
                    setBusy(track, true); track.lastChild.textContent = 'Saving\u2026';
                    try {
                        const r = await api('/api/impact', { op: 'add', text: a.text || '', source: source || 'copilot' });
                        setBusy(track, false); tracking();
                        if (state) { state.tracked = state.tracked || {}; state.tracked[i] = (r && r.item && r.item.id) || true; persist(); }
                        if (r && Array.isArray(r.impact)) impact = r.impact;
                        if (r && r.already) addToast('That change was already being tracked.');
                    }
                    catch (err) { setBusy(track, false); track.replaceChildren(ico(I.tag), document.createTextNode('Track')); toastError('Not tracked. ' + (err.message || err)); }
                };
                row.append(track);
                /* In an answer, one action can be copied on its own, for an
                   email or a task. */
                if (state) {
                    const cp = iconButton(I.copy, 'Copy: ' + String(a.text || '').slice(0, 60), { size: 'small', cls: 'act-copy', title: 'Copy this action' });
                    cp.onclick = (e) => { e.stopPropagation(); copyText(a.text || '', 'Action copied.'); };
                    row.append(cp);
                }
                card.append(row);
            });
            return card;
        }
        /* Which of your skills an answer or report followed, each a way to
           the Skills page. */
        function followedNote(s) {
            const names = (s && Array.isArray(s.skills_applied)) ? s.skills_applied.filter(Boolean) : [];
            if (!names.length) return null;
            /* A small row, not a sentence (copy plan, shared #3). */
            const p = el('p', 'followed');
            p.append(ico(I.book), document.createTextNode('Followed: '));
            names.forEach((n, k) => {
                const a = tabAllowed('skills') ? actionLink('followed-link', n) : el('span', 'followed-name', n);
                if (tabAllowed('skills')) a.onclick = () => setView('skills');
                if (k) p.append(document.createTextNode(', '));
                p.append(a);
            });
            return p;
        }
        /* The AI summary (the mix, spec 8.3): a section of its own at the top
           of a report, out of the header, with the skills it followed under it.
           Nothing when the run gave neither. */
        /* TWO BLOCKS SIDE BY SIDE (see .wpair). left and right are the two
           nodes, left already on the page; the pair takes left's place as one
           full-row widget, and the halves stop being widgets of their own. A
           missing half leaves the other where it is. */
        function pairNodes(left, right, id, label, o) {
            o = o || {};
            if (!left || !right) return null;
            const pair = el('div', 'wpair' + (o.even ? ' even' : '') + (o.flip ? ' flip' : '') + (o.fit ? ' fit' : ''));
            const inner = el('div', 'wpair-in');
            left.before(pair);
            [left, right].forEach(n => ['data-widget', 'data-size', 'data-widget-label'].forEach(a => n.removeAttribute(a)));
            inner.append(left, right);
            pair.append(inner);
            if (o.plain) return pair;   // a page that is not arranged (a product's plan)
            /* An id of its own: with the left half's, a layout that once hid
               Details hid the question box paired with it (final review I-1). */
            return widget(pair, id + '-pair', 'full', label);
        }
        /* The card cardifySections made from a heading with these words, or null. */
        function cardTitled(box, words) {
            return [...box.children].find(n => n.classList && n.classList.contains('card')
                && (n.querySelector(':scope > .card-head .card-title') || {}).textContent === words) || null;
        }
        /* A report's first row (12 Oct 2026): the summary beside What changed,
           as one widget. Without a summary the strip keeps its fixed place
           before the first card. */
        function summaryAndChanges(box, changes, since, text, followed) {
            const cs = changesStrip(changes, since);
            const sum = summarySection(text, followed);
            const sumW = sum ? widget(sum, 'summary', 'full', 'Summary') : null;
            if (sumW) box.append(sumW);
            if (cs && sumW) pairNodes(sumW, cs, 'summary', 'Summary and what changed');
            else if (cs) box.append(cs);
        }
        /* The widget among a page's top-level blocks with this id, or null. */
        function wgChild(box, id) { return [...box.children].find(n => n.dataset && n.dataset.widget === id) || null; }
        /* Traffic by channel: every month fetched, so it does not follow the
           range chooser, which is why it can leave the chart grid to sit beside
           Sales by sector (12 Oct 2026). */
        function channelsCard(trends) {
            if (!trends || !Array.isArray(trends.channels) || !trends.channels.length) return null;
            const span = Math.min(24, Math.max(1, ...['sessions', 'revenue', 'orders'].map(k => (trends[k] || []).length)));
            const cb = catBars({ title: 'Traffic by channel', source: 'Google Analytics 4', period: rangeLabel(span), color: CH[0],
                                 items: trends.channels, format: fmtCompact, noIntro: true, height: 280 });
            cb.classList.add('chart-top');
            return cb;
        }
        function summarySection(text, followed) {
            if (!text && !followed) return null;
            const sec = el('section', 'ai-summary widget-bare');
            sec.append(el('div', 'section-title', 'Summary'));
            if (text) sec.append(el('p', 'ai-summary-text', text));
            if (followed) sec.append(followed);
            return sec;
        }
