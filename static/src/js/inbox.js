        /* ==================================================================
           Inbox: the shared mailbox with an owner on every thread. Reading
           and replying stay in Gmail; this board answers the question Gmail
           cannot: who is dealing with each email, and what state is it in.
           One owner per thread, always. Unclaimed threads age visibly.
           ================================================================== */
        let mailCache = null, mailFilter = 'open', mailQ = '', mailTimer = null;
        /* The revision of the board in mailCache. The minute's poll sends it
           and an unchanged board comes back as {same: true} with the time of
           the sync alone (the 2026-10-12 speed audit, S6). */
        let mailRev = '';
        let mailListCap = 400;   /* render page size; the cache holds everything */
        /* List is the default: a real inbox arrives with weeks of history in
           it, and five columns of that is a wall, not a view. The board stays
           one click away for seeing how work is spread across people. */
        let mailView = 'list';
        let mailFound = null;   /* a whole-mailbox search result set, when one is showing */
        const mailSel = new Set();
        const MAIL_COLS = [['unassigned', 'Unassigned'], ['assigned', 'Assigned'],
                           ['progress', 'In progress'], ['waiting', 'Waiting on customer'],
                           ['done', 'Done']];
        function mailAgo(iso) {
            if (!iso) return '';
            const m = Math.floor((Date.now() - Date.parse(iso)) / 60000);
            if (isNaN(m)) return '';
            if (m < 1) return 'now';
            if (m < 60) return m + 'm';
            if (m < 48 * 60) return Math.floor(m / 60) + 'h';
            return Math.floor(m / 1440) + 'd';
        }
        function mailHours(iso) {
            const h = (Date.now() - Date.parse(iso)) / 3600000;
            return isNaN(h) ? 0 : h;
        }
        function mailAgoLong(iso) {
            const a = mailAgo(iso);
            return a === 'now' ? 'just now' : a ? a + ' ago' : '';
        }
        let mailCursor = -1;
        function mailRowsOnScreen() { return [...document.querySelectorAll('#mail-board-host .mrow')]; }
        /* The index is module state and outlives a repaint; the ring is a class
           on a row the repaint threw away. Left to itself the pair came apart -
           x armed a row, o opened one and c claimed one with no ring anywhere
           on screen - so the ring is re-hung on the index after every paint,
           and an index past the end of a shorter list gives the cursor up
           rather than pointing into nothing. */
        function mailPaintCursor() {
            if (mailCursor < 0) return;
            const rows = mailRowsOnScreen();
            if (!rows.length) { mailCursor = -1; return; }
            if (mailCursor > rows.length - 1) mailCursor = rows.length - 1;
            rows.forEach(r => r.classList.remove('cursor'));
            rows[mailCursor].classList.add('cursor');
        }
        function mailMoveCursor(delta) {
            const rows = mailRowsOnScreen();
            if (!rows.length) return;
            mailCursor = Math.max(0, Math.min(rows.length - 1, mailCursor + delta));
            mailPaintCursor();
            rows[mailCursor].scrollIntoView({ block: 'nearest' });
        }
        document.addEventListener('keydown', (e) => {
            if (!document.querySelector('#view-mail.active')) return;
            if (document.querySelector('.modal-overlay.show')) return;
            const a = document.activeElement;
            if (a && ['INPUT', 'SELECT', 'TEXTAREA'].indexOf(a.tagName) >= 0) {
                if (e.key === 'Escape') a.blur();
                return;
            }
            if (e.metaKey || e.ctrlKey || e.altKey) return;
            const rows = mailRowsOnScreen();
            const cur = rows[mailCursor];
            if (e.key === 'j') { e.preventDefault(); mailMoveCursor(mailCursor < 0 ? 0 : 1); }
            else if (e.key === 'k') { e.preventDefault(); mailMoveCursor(-1); }
            else if (e.key === '/') { e.preventDefault(); const s = document.querySelector('.mail-search'); if (s) s.focus(); }
            else if (e.key === 'x' && cur) { e.preventDefault(); const cb = cur.querySelector('.mail-check'); cb.checked = !cb.checked; cb.dispatchEvent(new Event('change')); }
            else if ((e.key === 'o' || e.key === 'Enter') && cur) { e.preventDefault(); cur.click(); }
            else if (e.key === 'c' && cur) { e.preventDefault(); const b = cur.querySelector('.mail-claim'); if (b && !b.disabled) b.click(); }
        });
        function showMailView() {
            if (mailCache) { renderMail(); refreshMailQuiet(false, true); } else { loadMail(); }
            if (!mailTimer) {
                /* Not in a hidden tab: the minute's poll fetched and redrew the
                   whole board for nobody (the 2026-10-12 speed audit, P1).
                   Coming back to the tab catches up at once if a minute has
                   gone. */
                mailTimer = setInterval(() => {
                    if (document.querySelector('#view-mail.active') && !document.hidden) refreshMailQuiet(false, true);
                }, 60000);
                document.addEventListener('visibilitychange', () => {
                    if (!document.hidden && mailCache && document.querySelector('#view-mail.active')
                        && Date.now() - mailFetchedAt >= 60000) refreshMailQuiet(false, true);
                });
            }
        }
        async function loadMail() {
            const box = $('mail-content'); box.innerHTML = '';
            const t = el('div', 'thinking'); t.append(loader(), el('span', null, 'Opening the inbox…'));
            box.append(t);
            try { mailCache = await api('/api/mail/board', {}); mailRev = mailCache.rev || ''; mailFetchedAt = Date.now(); renderMail(); }
            catch (e) {
                box.innerHTML = '';
                box.append(el('div', 'msg error', e.message || 'Could not load the inbox.'));
            }
        }
        let mailFetchSeq = 0;
        function mailInputBusy() {
            const a = document.activeElement;
            return !!(a && a.closest && a.closest('#mail-content')
                && (a.tagName === 'INPUT' || a.tagName === 'SELECT' || a.tagName === 'TEXTAREA'));
        }
        let mailFetchedAt = 0;
        async function refreshMailQuiet(force, poll) {
            const seq = ++mailFetchSeq;
            let ok = true;
            try {
                /* Refresh and actions ask for the board itself; a poll sends
                   the revision it holds, and an unchanged board is the copy
                   with the new time of the sync. */
                let d = await api('/api/mail/board', force ? { force: true }
                    : (poll && mailRev && mailCache ? { rev: mailRev } : {}));
                if (seq !== mailFetchSeq) return true;   // an action's fresher fetch already landed
                mailFetchedAt = Date.now();
                if (d && d.same) d = Object.assign({}, mailCache, { synced_at: d.synced_at });
                mailRev = d.rev || '';
                /* A poll (the minute's tick, a revisit) redraws only when the
                   board moved: rebuilding up to 5,800 elements to show the
                   same board was most of the Inbox's cost. On a quiet minute
                   only the time of the sync changes, and that one line moves
                   in place. A sync error always redraws, so its own "since"
                   stays true; an action always redraws. */
                const same = poll && !d.sync_error && !mailFound && mailBoardKey(d) === mailPaintedKey
                    && mailAgeKey(d) === mailPaintedAges;
                mailCache = d;
                // Never yank the keyboard out from under someone: while an
                // input in this view holds focus, keep the data and skip the
                // repaint; the next tick or action paints it.
                if (document.querySelector('#view-mail.active') && !mailInputBusy()) {
                    if (same) mailPaintSynced(d); else renderMail();
                }
            } catch (e) { ok = false; /* keep the last good board */ }
            return ok;
        }
        function mailBoardKey(d) { return JSON.stringify(Object.assign({}, d, { synced_at: '' })); }
        /* What time alone changes on screen: each row's age as written and
           which of the 4 h, 8 h and 24 h marks it has passed (amber, red, and
           quiet for over a day). A poll redraws when this moved since the
           last drawing, so a quiet board still ages and escalates on time. */
        function mailAgeKey(d) {
            return (d.threads || []).map(t => mailAgo(t.last_at)
                + (mailHours(t.last_at) > 4 ? 'a' : '') + (mailHours(t.last_at) > 8 ? 'b' : '')
                + (mailHours(t.state_at > t.last_at ? t.state_at : t.last_at) > 24 ? 'c' : '')).join(',')
                /* and a send that may have gone out says how long ago */
                + '|' + (d.outbound_pending || []).map(p => mailAgo(p.at)).join(',');
        }
        /* What is on screen, compared by the poll: not the page's copy, which
           a poll skipped under someone's typing has already moved on. */
        let mailPaintedKey = '', mailPaintedAges = '';
        function mailNotePainted(d) { mailPaintedKey = mailBoardKey(d); mailPaintedAges = mailAgeKey(d); }
        function mailSyncedLine(d) {
            return (d.address || 'The mailbox the team answers')
                + (d.synced_at ? ' \u00b7 synced ' + mailAgoLong(d.synced_at) : ' \u00b7 never synced');
        }
        function mailPaintSynced(d) {
            const line = document.querySelector('#mail-content [data-mail-synced]');
            if (line) line.textContent = mailSyncedLine(d);
        }
        async function mailAct(path, body) {
            const r = await api(path, body);
            await refreshMailQuiet();
            return r;
        }
        /* One line; claiming and amber then red wait behind the title's info
           button, word for word (copy plan, Inbox #1). */
        function mailHero(box) {
            const hero = pageHead({ view: 'mail', title: 'Inbox', line: 'The shared mailbox, with an owner on every email.',
                info: infoButton('About the Inbox', { title: 'Inbox', body: 'Claim what you are '
                    + 'dealing with, and reply from Gmail as usual. Unclaimed emails go amber, '
                    + 'then red.' }) });
            box.append(hero);
            return hero;
        }
        function renderMail() {
            const box = $('mail-content'); box.innerHTML = '';
            const d = mailCache;
            mailNotePainted(d);
            const hero = mailHero(box);
            if (!d.connected) {
                /* The setup card is built from the parts Reconciliation's own
                   mailbox card uses (a card head, numbered steps, a copyable
                   address with a Copy button), so the two read as one design.
                   It used to borrow the Settings window's row styles and set
                   its own sizes inline. */
                const card = el('div', 'card');
                const head = el('div', 'card-head');
                /* The setup, word for word, behind the title's info button; the
                   warning that matters stays as the line, and the address to
                   copy stays on the card (the mix, spec 8.3). */
                const mct = el('h3', 'card-title', 'Connect the shared mailbox');
                const mHelp = [];
                head.append(mct);
                card.append(head);
                /* Master OR not-yet-known, as with Restore in Settings: the
                   board can paint before authBoot resolves, and telling the
                   master to "ask an admin" strands the one person who can do
                   it. The server refuses anyone else regardless. */
                if (!teamMe || teamMe.role === 'master') {
                    head.append(el('p', 'card-desc', d.client
                        ? 'Choose the shared mailbox, not your own account.' : 'Google sign-in needs setting up first.'));
                    mHelp.push(d.client
                        ? 'Connect the mailbox whose email the team answers. Google will ask which '
                          + 'account to use: choose the shared mailbox, not your own account. Whichever '
                          + 'account you pick is the one this board reads. Google opens in a new tab, '
                          + 'and nothing is stored until you approve it there.'
                        : 'The server needs Google\u2019s client ID and secret in the app\u2019s hosting settings first, '
                          + 'with the Gmail API enabled in the same Google Cloud project.');
                    if (d.client) {
                        const row = el('div', 'act-row');
                        const go = textButton(null, { kind: 'primary', small: true });
                        go.append(ico(I.mail), document.createTextNode('Connect mailbox'));
                        go.onclick = async () => {
                            /* The tab must be opened INSIDE the click, before any
                               await, or the popup blocker eats it. Google refuses
                               to be framed, so it cannot open in this iframe. */
                            const tab = window.open('', '_blank');
                            go.disabled = true;
                            try {
                                const r = await api('/api/mail/connect-link', {});
                                if (tab) tab.location = r.url;
                                else toastError('Allow pop-ups for this page, then try again.');
                            } catch (e) {
                                if (tab) tab.close();
                                toastError(e.message);
                            }
                            go.disabled = false;
                        };
                        row.append(go);
                        card.append(row);
                    }
                    /* First-time setup: two switches inside the Google project
                       this app ALREADY uses. Nothing else changes, so the
                       Search Console and Analytics connections keep working. */
                    const su = d.setup || {};
                    /* Gated on the REDIRECT URI, not the project number: the
                       URI is the load-bearing value (it must match Google
                       exactly), while the project number is only a
                       convenience for the deep links. A client id the parser
                       cannot read must not take the address down with it. */
                    if (d.client && su.redirect_uri) {
                        mHelp.push('First time? Two switches in Google.', su.project
                            ? 'These open the Google project this app already uses (project '
                              + su.project + '), so nothing you have already set up changes.'
                            : 'Do these in the Google project this app already uses, so nothing '
                              + 'you have already set up changes.');
                        const proj = su.project ? '?project=' + encodeURIComponent(su.project) : '';
                        const link = (href, text) => { const a = el('a', 'action-link', text); a.href = href; a.target = '_blank'; a.rel = 'noopener'; return a; };
                        const steps = el('ol', 'setup-steps');
                        const s1 = el('li', null, 'Switch on the Gmail API.');
                        const r1 = el('div', 'act-row');
                        r1.append(link('https://console.cloud.google.com/apis/library/gmail.googleapis.com' + proj, 'Open that page'));
                        s1.append(r1);
                        const s2 = el('li', null, 'Open your existing web client and add this address under Authorised '
                            + 'redirect URIs. Keep the address that is already listed: add this one alongside it, then '
                            + 'come back here and press Connect mailbox.');
                        const r2 = el('div', 'act-row');
                        r2.append(el('code', 'setup-code', su.redirect_uri || ''));
                        const cp = textButton(null, { small: true }); cp.type = 'button';
                        cp.append(ico(I.copy), document.createTextNode('Copy'));
                        cp.onclick = async () => {
                            try { await navigator.clipboard.writeText(su.redirect_uri || ''); toastOk('Address copied.'); }
                            catch (e) { toastError('Select the address and copy it.'); }
                        };
                        r2.append(cp, link('https://console.cloud.google.com/auth/clients' + proj, 'Open your clients'));
                        steps.append(s1, s2);
                        mHelp.push(steps);
                        /* The address and its Copy stay on the card. */
                        card.append(r2);
                    }
                    titleInfo(mct, infoButton('About connecting the shared mailbox', { title: 'Connect the shared mailbox', body: mHelp }));
                } else {
                    head.append(el('p', 'card-desc', 'An admin needs to connect the shared mailbox.'));
                }
                box.append(card);
                return;
            }
            /* Connected, the page is cards the grid can move, each spanning the
               row; pageHead gave the header the action slot Customize goes in. */
            /* A sync that is failing is not a footnote. It stays a row of its
               own, above everything, in the colour that means stop. It used to
               come after Who is on today, which would leave a fixed block
               between two cards; above everything is where it said it was. */
            if (d.sync_error) {
                box.append(el('div', 'msg error', 'Sync problem: ' + d.sync_error
                    + (d.synced_at ? ' The list below may be missing mail that arrived after the last sync, '
                        + mailAgoLong(d.synced_at) + '.' : ' The list below is empty until a sync works.')));
            }
            /* ---- who's doing what ---- */
            const who = el('div', 'mail-who');
            const PRESENCE_LABEL = { office: 'In office', home: 'At home', out: 'Out' };
            (d.team || []).forEach(m => {
                const c = el('div', 'mail-who-card');
                /* The key to the colour code, right above the list it explains.
                   Without this a tinted row is a colour nobody can look up. */
                if (m.colour) {
                    const dot = el('span', 'who-dot' + ownClass(m.colour));
                    dot.title = (m.name || 'This person') + "'s colour";
                    c.append(dot);
                }
                let pick = null;
                if (m.uid === d.me) {
                    pick = document.createElement('select');
                    pick.className = 'mail-presence-pick'; pick.title = 'Where are you working today?'; pick.setAttribute('aria-label', 'Where are you working today?');
                    [['office', 'In office'], ['home', 'At home'], ['out', 'Out']].forEach(([v, lab]) => {
                        const o = document.createElement('option');
                        o.value = v; o.textContent = lab; if ((m.presence || 'office') === v) o.selected = true;
                        pick.append(o);
                    });
                    pick.onchange = async () => {
                        try { await api('/api/mail/presence', { presence: pick.value }); refreshMailQuiet(); }
                        catch (e) { toastError(e.message); }
                    };
                    const meDot = el('span', 'mail-presence ' + (m.presence || 'office'));
                    meDot.title = PRESENCE_LABEL[m.presence || 'office'];
                    c.append(meDot);
                } else {
                    /* Office green against home amber is exactly the pair a
                       colour-blind reader cannot separate, and the dot carried
                       no other signal at all. */
                    const dot = el('span', 'mail-presence ' + (m.presence || ''));
                    dot.title = PRESENCE_LABEL[m.presence] || 'Presence unknown';
                    c.append(dot);
                }
                const active = (m.assigned || 0) + (m.progress || 0);
                const load = active + ' active' + (m.waiting ? ', ' + m.waiting + ' waiting' : '');
                /* The name over where they are and what they hold; yours keeps
                   its chooser beside it. */
                const txt = el('span', 'mail-who-txt');
                txt.append(el('span', 'mail-who-name', m.name + (m.uid === d.me ? ' (you)' : '')),
                    el('span', 'mail-who-load', m.uid === d.me ? load : (PRESENCE_LABEL[m.presence] || 'Presence unknown') + ' \u00b7 ' + load));
                c.append(txt);
                if (pick) c.append(pick);
                who.append(c);
            });
            /* In a card with a title. Bare on the background this row read as
               decoration rather than as "here is who can take one". */
            if ((d.team || []).length) {
                const wcard = el('div', 'card');
                const whead = el('div', 'card-head');
                whead.append(el('h3', 'card-title', 'Who is on today'));
                wcard.append(whead, who);
                box.append(widget(wcard, 'who'));
            }
            /* ---- the board, composed the way the reference composes a list
               page: a counted title, the mailbox and its last sweep as the line
               under it, the two things you press on the right, then the search
               and the states on a toolbar. It was six controls and a status
               line jammed into one row. ---- */
            const counts = { open: 0, mine: 0, unassigned: 0, unread: 0, done: 0 };
            (d.threads || []).forEach(t => {
                if (t.unread) counts.unread++;       // whatever state it is in
                if (t.state === 'done') { counts.done++; return; }
                counts.open++;
                if (t.owner === d.me) counts.mine++;
                if (t.state === 'unassigned') counts.unassigned++;
            });
            const mCard = el('div', 'card');
            const mHead = el('div', 'card-head');
            const lab = (text, n) => text + (n ? ' (' + n + ')' : '');
            mHead.append(el('h3', 'card-title', lab('Shared inbox', counts.open)));
            const mSynced = el('p', 'card-desc', mailSyncedLine(d));
            mSynced.dataset.mailSynced = '';      // mailPaintSynced moves it on a quiet poll
            mHead.append(mSynced);
            const mAct = el('div', 'card-act');
            const filt = textButton('Filters' + (d.rules ? ' (' + d.rules + ')' : ''), { small: true });
            filt.title = 'Rules that sort mail as it arrives';
            filt.onclick = () => openMailRules();
            const rf = textButton(null, { small: true });
            rf.append(ico(I.refresh), document.createTextNode('Refresh'));
            rf.onclick = async () => {
                rf.disabled = true;
                const ok = await refreshMailQuiet(true);
                /* Success repaints the toolbar with a fresh button; failure
                   must hand this one back or Refresh dies exactly when the
                   person is trying to recover from a bad patch. */
                rf.disabled = false;
                if (!ok) toastError('Could not refresh the inbox. Try again in a moment.');
            };
            /* First in the row: the one control on this card that makes
               something happen outside the app. Hidden without the grant,
               because the server refuses it anyway and a button that always
               fails is a lie. */
            if (mailCanSend()) {
                const cmp = textButton('Compose', { kind: 'primary', small: true });
                cmp.title = 'Start a new conversation from the shared mailbox';
                cmp.onclick = () => openMailCompose();
                mAct.append(cmp);
            }
            mAct.append(filt, rf);
            mHead.append(mAct);
            mCard.append(mHead);

            const search = document.createElement('input');
            search.type = 'search'; search.className = 'mail-search'; search.setAttribute('aria-label', 'Search the inbox');
            search.value = mailQ;
            search.oninput = () => {
                mailQ = search.value; mailFound = null;
                clearTimeout(search._t); search._t = setTimeout(paintMailBody, 150);
            };
            search.onkeydown = async (e) => {
                if (e.key !== 'Enter') return;
                const q = search.value.trim();
                if (!q) { mailFound = null; paintMailBody(); return; }
                search.disabled = true;
                try {
                    const r = await api('/api/mail/search', { q: q });
                    mailFound = { q: q, rows: r.results || [] };
                } catch (err) { toastError(err.message); }
                search.disabled = false;
                paintMailBody();
                search.focus();
            };
            search.placeholder = 'Search, then Enter for the whole mailbox';
            const sWrap = el('div', 'tbl-search');
            sWrap.classList.add('search-long');
            sWrap.append(ico(I.search), search);
            const states = segmented([['open', lab('Open', counts.open)],
                                       ['unread', lab('Unread', counts.unread)],
                                       ['mine', lab('Mine', counts.mine)],
                                       ['unassigned', lab('Unassigned', counts.unassigned)],
                                       ['done', 'Done']],
                /* A different set of emails: the tick marks and the keyboard
                   cursor both belonged to the old one, and row 5 of Done is
                   not row 5 of Open. */
                mailFilter, v => { mailFilter = v; mailSel.clear(); mailCursor = -1; mailListCap = 400; renderMail(); });
            const viewSeg = segmented([{ value: 'list', label: 'List' }, { value: 'board', label: 'Board' }],
                mailView, v => { mailView = v; mailSel.clear(); mailCursor = -1; renderMail(); });
            mCard.append(tableTools([sWrap, states], [viewSeg]));
            /* New conversations that were stamped and never confirmed. They
               have no thread on the board to carry the warning, so it is said
               here, one line each, above the list. */
            (d.outbound_pending || []).forEach(p => {
                mCard.append(el('div', 'mail-sendwarn',
                    mailPendingLine(p.to, p.at)
                    + (p.subject ? ' Subject: ' + p.subject : '')));
            });
            box.append(widget(mCard, 'inbox'));
            const bulkHost = el('div'); bulkHost.id = 'mail-bulk-host';
            mCard.append(bulkHost);
            const bodyHost = el('div'); bodyHost.id = 'mail-board-host';
            mCard.append(bodyHost);
            paintMailBody();
        }
        /* ---- bulk actions: the only realistic way through a first import ---- */
        function paintMailBulk(rows) {
            const host = $('mail-bulk-host'); if (!host) return;
            host.innerHTML = '';
            if (mailView !== 'list') return;
            const bar = el('div', 'mail-bulkbar');
            const all = document.createElement('input');
            all.type = 'checkbox'; all.className = 'mail-check';
            all.checked = rows.length > 0 && rows.every(t => mailSel.has(t.id));
            all.title = 'Select everything shown';
            all.setAttribute('aria-label', 'Select everything shown');
            all.onchange = () => {
                rows.forEach(t => all.checked ? mailSel.add(t.id) : mailSel.delete(t.id));
                paintMailBody();
            };
            bar.append(mailTick(all));
            if (!mailSel.size) {
                bar.append(el('span', 'mail-bulk-hint',
                    rows.length + (rows.length === 1 ? ' email' : ' emails')));
                host.append(bar);
                return;
            }
            bar.classList.add('armed');
            const count = el('span', 'mail-bulk-hint', mailSel.size + ' selected');
            bar.append(count);
            const run = (label, body, confirmText, readMode) => {
                const b = textButton(label);
                b.onclick = async () => {
                    if (confirmText && !(await uiConfirm(confirmText, { title: label, okText: label }))) return;
                    b.disabled = true;
                    const ids = [...mailSel];
                    if (readMode !== undefined && readMode !== null) {
                        /* Read state lives in Gmail, so it takes its own route. */
                        try {
                            for (let i = 0; i < ids.length; i += 150) {
                                await api('/api/mail/read',
                                    { ids: ids.slice(i, i + 150), unread: !readMode });
                            }
                            mailSel.clear();
                        } catch (e) { toastError(e.message); b.disabled = false; return; }
                        await refreshMailQuiet();
                        return;
                    }
                    /* Sent in batches: the server caps a single request, and
                       clearing a whole backlog is exactly the case where the
                       selection is bigger than that cap. One refusal for the
                       entire pile, with no way to trim it, would strand the
                       person on the one action this feature exists for. */
                    const CHUNK = 150;
                    let changed = 0, skipped = [], what = '';
                    const undoTokens = [];   // one per batch: Undo has to send them all
                    try {
                        for (let i = 0; i < ids.length; i += CHUNK) {
                            if (ids.length > CHUNK) {
                                count.textContent = 'working: ' + Math.min(i + CHUNK, ids.length)
                                    + ' of ' + ids.length;
                            }
                            const r = await api('/api/mail/bulk',
                                Object.assign({ ids: ids.slice(i, i + CHUNK) }, body));
                            changed += (r.changed || 0);
                            if (r.skipped) skipped = skipped.concat(r.skipped);
                            if (r.undo) { undoTokens.push(r.undo); what = r.what || 'that'; }
                        }
                        mailSel.clear();
                    } catch (e) {
                        toastError(changed
                            ? (changed + ' were changed, then it stopped: ' + e.message)
                            : e.message);
                        b.disabled = false;
                        /* What did change can still be put back. */
                        if (undoTokens.length && changed) mailOfferUndo(undoTokens, changed, what);
                        await refreshMailQuiet();
                        return;
                    }
                    if (skipped.length) {
                        toastError(skipped.length + ' could not be changed: '
                            + skipped.slice(0, 3).map(s => s.why).join(', '));
                    }
                    if (undoTokens.length && changed) mailOfferUndo(undoTokens, changed, what);
                    await refreshMailQuiet();
                };
                bar.append(b);
                return b;
            };
            /* Claim is hidden under Done: the per-row button is hidden there
               too, and quietly reopening finished mail is not a bulk gesture. */
            if (mailFilter !== 'done') run('Claim', { op: 'claim' });
            if (mailCache.lead) {
                const pick = document.createElement('select');
                pick.className = 'mail-presence-pick';
                pick.setAttribute('aria-label', 'Assign to');
                const none = document.createElement('option');
                none.value = ''; none.textContent = 'Assign to\u2026';
                pick.append(none);
                (mailCache.team || []).filter(u => u.can_own !== false).forEach(u => {
                    const o = document.createElement('option');
                    o.value = u.uid; o.textContent = u.name; pick.append(o);
                });
                pick.onchange = async () => {
                    if (!pick.value) return;
                    const uid = pick.value, ids = [...mailSel];
                    pick.disabled = true;
                    const CHUNK = 150;
                    let skipped = [];
                    try {
                        for (let i = 0; i < ids.length; i += CHUNK) {
                            const r = await api('/api/mail/bulk',
                                { op: 'assign', uid: uid, ids: ids.slice(i, i + CHUNK) });
                            if (r.skipped) skipped = skipped.concat(r.skipped);
                        }
                        mailSel.clear();
                    } catch (e) { toastError(e.message); pick.disabled = false; return; }
                    if (skipped.length) toastError(skipped.length + ' could not be assigned.');
                    await refreshMailQuiet();
                };
                bar.append(pick);
            }
            if (mailFilter !== 'done') {
                run('Mark done', { op: 'state', state: 'done' },
                    'Mark ' + mailSel.size + ' email' + (mailSel.size === 1 ? '' : 's')
                    + ' as done? Use this to clear old mail that was dealt with before '
                    + 'the app existed. They stay searchable under Done.');
            }
            const anyUnread = rows.some(t => mailSel.has(t.id) && t.unread);
            run(anyUnread ? 'Mark read' : 'Mark unread', null, null, anyUnread);
            const clear = textButton('Clear');
            clear.onclick = () => { mailSel.clear(); paintMailBody(); };
            bar.append(clear);
            host.append(bar);
        }
        /* Every repaint ends by re-hanging the cursor ring, whichever body it
           painted: the list, a search result or the board. */
        function paintMailBody() {
            paintMailRows();
            mailPaintCursor();
        }
        function paintMailRows() {
            if (mailFound) { paintMailSearch(); return; }
            const rows = (mailCache.threads || []).filter(mailCardMatches);
            /* Anything nobody has opened rises to the top. The board already
               arrives newest-first, so within each group the order is
               unchanged; this only lifts the unread ones clear of the pile. */
            rows.sort((a, b) => (b.unread ? 1 : 0) - (a.unread ? 1 : 0));
            /* A tick may only ever mean a row you can SEE. Without this, a
               search that narrows the list, or a colleague closing a thread
               between repaints, leaves ids armed that are nowhere on screen,
               and the next bulk action quietly hits them. */
            const visible = new Set(rows.map(t => t.id));
            [...mailSel].forEach(id => { if (!visible.has(id)) mailSel.delete(id); });
            paintMailBulk(rows);
            if (mailView === 'board') { paintMailBoard(); return; }
            const host = $('mail-board-host'); if (!host) return;
            host.innerHTML = '';
            /* Unread mail this view is hiding gets said out loud, BEFORE the
               empty state: "this inbox is clear" must never be the last word
               while unread email sits in Done. */
            const shown = new Set(rows.map(t => t.id));
            const hidden = (mailCache.threads || []).filter(t => t.unread && !shown.has(t.id));
            if (hidden.length && mailFilter !== 'unread') {
                const note = el('div', 'mail-hidden-note');
                note.append(document.createTextNode(hidden.length
                    + (hidden.length === 1 ? ' unread email is' : ' unread emails are')
                    + ' not in this view. '));
                const go = textLink('Show unread');
                go.onclick = () => { mailFilter = 'unread'; mailSel.clear(); mailCursor = -1; renderMail(); };
                note.append(go);
                host.append(note);
            }
            if (!rows.length) {
                const empty = el('div', 'mail-empty');
                empty.textContent = mailQ ? 'Nothing matches that search.'
                    : mailFilter === 'done' ? 'Nothing has been marked done yet.'
                    : mailFilter === 'mine' ? 'You are not holding any email right now.'
                    : mailFilter === 'unassigned' ? 'Every email has an owner.'
                    : hidden.length ? 'Nothing open. The unread ones are above.'
                    : 'This inbox is clear.';
                host.append(empty);
                return;
            }
            const list = el('div', 'mlist');
            /* Two years of history is thousands of rows; the DOM gets them a
               page at a time. Search still reaches everything - the rows are
               all in the cache, only the RENDER is paged. */
            rows.slice(0, mailListCap).forEach(t => list.append(mailRow(t)));
            host.append(list);
            if (rows.length > mailListCap) {
                const more = textButton();
                more.style.marginTop = 'var(--sp-2)';
                more.textContent = 'Show more (' + (rows.length - mailListCap) + ' older)';
                more.onclick = () => { mailListCap += 400; renderMail(); };
                host.append(more);
            }
        }
        function mailOfferUndo(tokens, n, what) {
            tokens = Array.isArray(tokens) ? tokens : [tokens];
            /* One mis-click can move 150 emails. The offer is short-lived and
               deliberately loud, because it is only useful in the seconds
               after somebody realises. */
            const host = $('mail-bulk-host'); if (!host) return;
            const bar = el('div', 'mail-hidden-note');
            bar.append(document.createTextNode(
                n + ' email' + (n === 1 ? '' : 's') + ' ' + what + '. '));
            const go = textLink('Undo');
            go.onclick = async () => {
                go.disabled = true;
                /* A bulk action over more than one batch holds one token per
                   batch. Sending only the last put back the last 150 and said
                   "Put back" over the rest. What is said is what the server
                   says it restored. */
                let back = 0, why = '';
                for (const t of tokens) {
                    try { back += ((await api('/api/mail/undo', { token: t })) || {}).restored || 0; }
                    catch (e) { why = why || e.message; }
                }
                if (!why && back >= n) toastOk('Put back');
                else toastError('Put back ' + back + ' of ' + n + (why ? ': ' + why : '.'));
                bar.remove();
                refreshMailQuiet();
            };
            bar.append(go);
            host.prepend(bar);
            setTimeout(() => bar.remove(), 30000);
        }
        function paintMailSearch() {
            const host = $('mail-board-host'); if (!host) return;
            $('mail-bulk-host').innerHTML = '';
            host.innerHTML = '';
            const bar = el('div', 'mail-hidden-note');
            const n = mailFound.rows.length;
            bar.append(document.createTextNode(
                (n === 40 ? '40+' : n) + ' result' + (n === 1 ? '' : 's')
                + ' in the whole mailbox for "' + mailFound.q + '". '));
            const back = textLink('Back to the board');
            back.onclick = () => {
                mailFound = null; mailQ = ''; mailCursor = -1;
                renderMail();
            };
            bar.append(back);
            host.append(bar);
            if (!n) { host.append(el('div', 'mail-empty', 'Gmail found nothing for that.')); return; }
            const list = el('div', 'mlist');
            mailFound.rows.forEach(t => list.append(mailRow(t)));
            host.append(list);
        }
        /* The owner's dot is the same key the strip above the list draws, and
           it is what stops the chip reading as a third grey capsule beside the
           message count and the folder tag. Class, never a value: the colour
           comes from the team record and goes through ownClass. */
        function mailOwnerChip(t) {
            const o = el('span', 'mail-owner' + ownClass(mailColour(t.owner)));
            o.append(el('span', 'who-dot' + ownClass(mailColour(t.owner))),
                     el('span', 'mail-owner-name', t.owner_name || 'Someone'));
            o.title = 'Claimed by ' + (t.owner_name || 'someone on the team');
            return o;
        }
        /* A tick in a label, so a phone can give it a 40 hit square (an input cannot carry a pseudo-element). A tap
           on the label ticks the input and goes no further: it must not open the thread under it. */
        function mailTick(cb) {
            const lab = el('label', 'mail-tick');
            lab.onclick = (e) => e.stopPropagation();
            lab.append(cb);
            return lab;
        }
        function mailRow(t) {
            const d = mailCache;
            const row = el('div', 'mrow'
                + (t.unread ? ' unread' : '')
                + (t.owner ? ownClass(mailColour(t.owner)) : '')
                + (mailSel.has(t.id) ? ' selected' : ''));
            const cb = document.createElement('input');
            cb.type = 'checkbox'; cb.className = 'mail-check';
            /* Names the row it belongs to. Nineteen of these sit on the board and
               every one of them announced as a bare "checkbox", which makes the
               whole bulk-claim flow unusable without sight of the screen. */
            cb.setAttribute('aria-label', 'Select: ' + (t.subject || '(no subject)')
                + (t.from_name ? ' from ' + t.from_name : ''));
            cb.checked = mailSel.has(t.id);
            if (t.archive) { cb.disabled = true; cb.title = 'Older than the board keeps'; }
            cb.onclick = (e) => e.stopPropagation();
            cb.onchange = () => {
                cb.checked ? mailSel.add(t.id) : mailSel.delete(t.id);
                /* Only the row and the bar redraw. Repainting the whole list
                   would detach the very checkbox mid-event, so keyboard
                   triage (tab, space, tab, space) lost focus on every tick. */
                row.classList.toggle('selected', cb.checked);
                if (!mailFound) paintMailBulk((mailCache.threads || []).filter(mailCardMatches));
            };
            row.append(mailTick(cb));
            const dot = el('span', 'mdot ' + t.state);
            dot.title = { unassigned: 'Nobody has this yet', assigned: 'Assigned',
                          progress: 'In progress', waiting: 'Waiting on the customer',
                          done: 'Done' }[t.state] || '';
            row.append(dot);
            /* Built on every row and blanked when the mail has been read, so
               the sender and subject columns start at the same x all the way
               down. See .munread.seen. */
            const u = el('span', 'munread'); u.append(el('span', 'sr-only', 'New'));
            if (t.unread) u.title = 'Nobody has opened this yet';
            else u.classList.add('seen');
            row.append(u);
            const mfrom = el('span', 'mfrom', t.from_name || t.from_email || '');
            mfrom.title = t.from_name || t.from_email || '';
            row.append(mfrom);
            const subj = el('span', 'msubj');
            subj.title = t.subject || '';
            subj.append(el('b', null, t.subject));
            if (t.snippet) subj.append(document.createTextNode(' · ' + t.snippet));
            row.append(subj);
            if (t.msg_count > 1) row.append(el('span', 'mcount', String(t.msg_count)));
            if (t.files) {
                const cl = el('span', 'mnote'); cl.innerHTML = I.clip;
                cl.title = t.files + (t.files === 1 ? ' attachment' : ' attachments');
                row.append(cl);
            }
            if (t.folder) {
                const ft = el('span', 'mrule-tag', t.folder);
                ft.title = 'Filed in the Gmail folder "' + t.folder + '"';
                row.append(ft);
            } else if (t.rule) {
                const rt = el('span', 'mrule-tag', 'filter');
                rt.title = 'Sorted by the filter "' + t.rule + '"';
                row.append(rt);
            }
            if (t.notes) {
                const n = el('span', 'mnote'); n.innerHTML = I.bookmark;
                n.title = t.notes + (t.notes === 1 ? ' internal note' : ' internal notes');
                row.append(n);
            }
            if (t.label_error) {
                /* The list is now the default view, so a label that never
                   reached Gmail has to be visible HERE or it is invisible. */
                const w = el('span', 'mail-labelerr', '!');
                w.title = 'The ownership label could not be written into Gmail. '
                    + 'The board is still right; it retries on its own.';
                row.append(w);
            }
            /* Before the owner slot, with the other tags it belongs with: the
               slot and the age are the two pinned columns on the right. */
            if (t.archive) {
                const a = el('span', 'mrule-tag', 'archive');
                a.title = 'Older than the board keeps. Read only.';
                row.append(a);
            }
            /* Always appended, empty on a row that has neither, so the column
               holds its x down the list. */
            const slot = el('span', 'mown-slot');
            if (t.owner) {
                slot.append(mailOwnerChip(t));
            } else if (t.state !== 'done' && !t.archive) {
                const b = el('button', 'mail-claim', 'Claim');
                b.onclick = async (e) => {
                    e.stopPropagation(); b.disabled = true;
                    try { await mailAct('/api/mail/claim', { id: t.id }); }
                    catch (err) { toastError(err.message); b.disabled = false; refreshMailQuiet(); }
                };
                slot.append(b);
            }
            row.append(slot);
            /* The board's two thresholds, so both views say the same thing
               about the same email: amber after 4 hours unclaimed, red after 8.
               The list went from grey straight to red. */
            const unclaimed = t.state === 'unassigned', hrs = mailHours(t.last_at);
            const age = el('span', 'mage' + (unclaimed && hrs > 8 ? ' hot' : unclaimed && hrs > 4 ? ' warm' : ''), mailAgo(t.last_at));
            age.title = mailAgoLong(t.last_at);
            row.append(age);
            row.setAttribute('role', 'button'); row.tabIndex = 0;
            /* Guarded on target, and the event stops here: the row's own
               checkbox and Claim button have to keep their Space and Enter,
               and the inbox-wide Enter shortcut would otherwise also open
               whatever row the j/k cursor last sat on. */
            row.addEventListener('keydown', (e) => {
                if (e.target !== row) return;
                if (e.key !== 'Enter' && e.key !== ' ') return;
                e.preventDefault(); e.stopPropagation(); row.click();
            });
            row.onclick = () => t.archive ? openMailArchive(t) : openMailThread(t.id);
            return row;
        }
        function mailTextMatches(t) {
            if (!mailQ) return true;
            const q = mailQ.toLowerCase();
            return (t.subject || '').toLowerCase().indexOf(q) >= 0
                || (t.from_name || '').toLowerCase().indexOf(q) >= 0
                || (t.from_email || '').toLowerCase().indexOf(q) >= 0;
        }
        function mailCardMatches(t) {
            /* The list is an inbox: done mail leaves it, the way archived mail
               leaves Gmail's, and lives under its own filter. */
            if (mailFilter === 'unread') {
                /* Unread is a property of the EMAIL, not a stage of work. It
                   deliberately ignores state: an email marked unread in Gmail
                   is someone saying "look at this again", and hiding it
                   because the thread was closed is how it goes unanswered. */
                if (!t.unread) return false;
                return mailTextMatches(t);
            }
            if (mailFilter === 'done') { if (t.state !== 'done') return false; }
            else if (t.state === 'done') return false;
            if (mailFilter === 'mine' && t.owner !== mailCache.me) return false;
            if (mailFilter === 'unassigned' && t.state !== 'unassigned') return false;
            return mailTextMatches(t);
        }
        function mailBoardMatches(t) {
            /* "Open" means every column here, Done included, or the board's own
               Done column would always be bare. The narrower filters still
               apply, because a chip that looks active and does nothing is
               worse than not offering it. */
            if (mailFilter === 'mine' && t.owner !== mailCache.me) return false;
            if (mailFilter === 'unassigned' && t.state !== 'unassigned') return false;
            if (mailFilter === 'done' && t.state !== 'done') return false;
            if (mailFilter === 'unread' && !t.unread) return false;
            return mailTextMatches(t);
        }
        function paintMailBoard() {
            const host = $('mail-board-host'); if (!host) return;
            host.innerHTML = '';
            const d = mailCache;
            const board = el('div', 'crm-board');
            MAIL_COLS.forEach(([state, label]) => {
                const col = el('div', 'crm-col');
                let rows = (d.threads || []).filter(t => t.state === state && mailBoardMatches(t));
                const total = rows.length;
                if (state === 'done') rows = rows.slice(0, 30);
                col.append(el('div', 'crm-col-name', label));
                col.append(el('div', 'crm-col-sum',
                    state === 'done' && total > 30 ? 'newest 30 of ' + total : String(total)));
                rows.forEach(t => col.append(mailCard(t)));
                /* The board carries live work plus recently closed threads.
                   Say where the rest went instead of looking like it lost them. */
                if (state === 'done' && d.older_hidden) {
                    col.append(el('div', 'crm-col-note',
                        d.older_hidden + ' older ' + (d.older_hidden === 1 ? 'conversation is' : 'conversations are')
                        + ' outside the board window. Search finds them.'));
                }
                board.append(col);
            });
            host.append(board);
        }
        function mailCard(t) {
            const d = mailCache;
            const card = el('div', 'crm-card mail-card');
            card.style.cursor = 'pointer';
            if (t.state === 'unassigned') {
                const h = mailHours(t.last_at);
                if (h > 8) card.classList.add('overdue-hard');
                else if (h > 4) card.classList.add('overdue-soft');
            }
            card.append(el('div', 'crm-card-t', t.subject));
            const cardSub = el('div', 'mail-card-sub', (t.from_name || t.from_email || '') +
                (t.snippet ? ' · ' + t.snippet : ''));
            cardSub.title = cardSub.textContent;
            card.append(cardSub);
            const bot = el('div', 'crm-card-bot');
            if (t.owner) {
                bot.append(mailOwnerChip(t));
            } else if (t.state !== 'done') {
                const b = el('button', 'mail-claim', 'Claim');
                b.onclick = async (e) => {
                    e.stopPropagation(); b.disabled = true;
                    try { await mailAct('/api/mail/claim', { id: t.id }); }
                    catch (err) { toastError(err.message); b.disabled = false; refreshMailQuiet(); }
                };
                bot.append(b);
            }
            if (t.notes) bot.append(el('span', 'mail-who-load', t.notes + (t.notes === 1 ? ' note' : ' notes')));
            if (t.label_error) bot.append(el('span', 'mail-labelerr', 'label sync failed'));
            const stale = (t.state === 'assigned' || t.state === 'progress')
                && mailHours(t.state_at > t.last_at ? t.state_at : t.last_at) > 24;
            const age = el('span', 'mail-age' + (stale ? ' hot' : ''), mailAgo(t.last_at));
            if (stale) age.title = 'Quiet for over a day';
            bot.append(age);
            card.append(bot);
            card.setAttribute('role', 'button'); card.tabIndex = 0;
            /* Guarded on target so the Claim button keeps its own Space and Enter. */
            card.addEventListener('keydown', (e) => {
                if (e.target !== card) return;
                if (e.key !== 'Enter' && e.key !== ' ') return;
                e.preventDefault(); e.stopPropagation(); card.click();
            });
            card.onclick = () => openMailThread(t.id);
            return card;
        }
