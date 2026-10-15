        /* ==================================================================
           Team. Identity is Shopify's: every request already carries the
           staff member's own verified id, so this is names and roles over
           ids, plus the ledger of who did what. Admins see this tab and
           Settings; members see neither. Hiding is politeness; the server
           enforces every gate again.
           ================================================================== */
        let teamMe = null, teamCache = null, teamSeg = 'people', teamNewOpen = false, teamTabsOpen = '';
        let teamFilterWho = '', teamFilterArea = '';
        function byName(sub) {
            if (!sub) return '';
            const names = (filesCache && filesCache.names) || (teamCache && teamCache.names) || {};
            if (names[sub]) return names[sub];
            return /^(u?\d+)$/.test(String(sub)) ? '' : String(sub).slice(0, 24);
        }
        /* ---- the app's own front door ---- */
        async function authApi(path, payload) {
            const hdrs = Object.assign({ 'Content-Type': 'application/json' }, await authHeaders());
            const sess = appSession();
            if (sess) hdrs['X-App-Session'] = sess;
            const res = await fetch(path, { method: 'POST', headers: hdrs, body: JSON.stringify(payload || {}) });
            const data = await res.json().catch(() => ({}));
            if (data.error) throw new Error(data.error);
            return data;
        }
        const TAB_KEYS = ['overview', 'seo', 'keywords', 'products', 'customers', 'liability',
                          'crm', 'loans', 'mail', 'files', 'labels', 'sizes', 'memory', 'skills', 'chat', 'recon',
                          'forecast', 'connector'];
        /* Reconciliation is not part of the default grant: it holds the books,
           the bank line and the accounts mailbox, so it is handed over on
           purpose rather than inherited by having an account. Mirrors
           OPT_IN_TABS on the server, which is the side that actually decides. */
        const OPT_IN_TABS = ['recon', 'connector', 'forecast'];
        const DEFAULT_TABS = TAB_KEYS.filter(k => OPT_IN_TABS.indexOf(k) < 0);
        function tabAllowed(v) {
            if (!teamMe || !Array.isArray(teamMe.tabs)) return true;
            if (TAB_KEYS.indexOf(v) < 0) return true;   // guide and team are governed elsewhere
            return teamMe.tabs.indexOf(v) >= 0;
        }
        function applyRoleChrome() {
            const lvl = teamMe ? ({ master: 3, admin: 2, member: 1 }[teamMe.role] || 1) : 1;
            $('nav-team').style.display = lvl >= 2 ? '' : 'none';
            $('settings-btn').style.display = lvl >= 2 ? '' : 'none';
            if (teamMe && teamMe.role === 'parttime') clockBoot(); else $('clock-btn').style.display = 'none';
            const acct = $('auth-account');
            if (acct) acct.textContent = teamMe ? teamMe.name : '';
            const roleEl = $('auth-role'), avEl = $('side-avatar');
            if (roleEl) roleEl.textContent = teamMe ? (ROLE_LABELS[teamMe.role] || teamMe.role || '') : '';
            if (avEl) avEl.textContent = teamMe ? sideInitials(teamMe.name) : '';
            TAB_KEYS.forEach(v => {
                const n = $('nav-' + v);
                if (n) n.style.display = tabAllowed(v) ? '' : 'none';
            });
            /* Without the Chat tab there are no conversations to list, and
               a question asked from one would be refused. */
            const chatOk = tabAllowed('chat');
            document.querySelector('.convo-head').hidden = !chatOk;
            $('convos').hidden = !chatOk;
            syncNavGroups();
            const av = document.querySelector('.view.active');
            const cur = av ? av.id.replace('view-', '') : '';
            if (cur && !tabAllowed(cur)) {
                const first = TAB_KEYS.find(tabAllowed);
                setView(first || 'guide');
            }
        }
        function authOverlay() {
            let ov = $('auth-overlay');
            if (ov) return ov;
            ov = el('div'); ov.id = 'auth-overlay'; ov.className = 'auth-overlay';
            document.body.append(ov);
            return ov;
        }
        function authField(labelText, type, id) {
            const w = el('div', 'auth-field');
            const lab = el('label', 'sr-only', labelText); lab.htmlFor = id;
            const inp = document.createElement('input');
            inp.type = type; inp.id = id;
            /* Keyed off the FIELD, not the type: the setup card's "Your name"
               was getting autocomplete=username, so the browser offered to
               fill a username into it - two username tokens in one card. */
            inp.autocomplete = type === 'password' ? 'current-password'
                : id === 'au-name' ? 'name' : 'username';
            inp.name = inp.autocomplete;
            if (inp.autocomplete === 'username') inp.spellcheck = false;
            /* The name is shown IN the field; the label above stays for the
               screen reader and the password manager, just not on screen. */
            inp.placeholder = labelText;
            const ic = el('span', 'auth-ic');
            const glyph = type === 'password' ? 'lock' : id === 'au-mfa' ? 'key'
                : id === 'au-name' ? 'user' : 'atSign';
            ic.innerHTML = I[glyph];
            w.append(lab, ic, inp);
            return [w, inp];
        }
        /* The tile at the top of the card: one mark per step, named by its
           key in I so only a constant icon can ever reach the markup. */
        function authBrand(glyph) {
            const b = el('div', 'auth-brand'); b.innerHTML = I[glyph || 'logIn'];
            return b;
        }
        /* The page behind the sign-in card is out of reach, keyboard and
           screen reader alike: after Log out it still held the last person's
           conversation titles. */
        function appBehind(off) { ['sidebar', 'main'].forEach(id => { const n = $(id); if (n) n.inert = !!off; }); if (off) $('convos').replaceChildren(); }
        function authShow(mode) {
            appBehind(true);
            const ov = authOverlay();
            if (ov.style.display === 'flex' && ov.dataset.mode === mode) return;   // already up; never wipe typing
            ov.dataset.mode = mode;
            ov.innerHTML = ''; ov.style.display = 'flex';
            const card = el('div', 'auth-card');
            card.append(authBrand(mode === 'change' ? 'lock' : 'logIn'));
            const err = el('div', 'auth-error');
            err.setAttribute('role', 'alert');
            if (mode === 'login') {
                const why = takeAuthReason();
                if (why && why.text) err.textContent = why.text;
            }
            function authShowMfa(ticket) {
                const card = ov.querySelector('.auth-card');
                if (!card) return;
                card.innerHTML = '';
                card.append(authBrand('key'), el('h2', null, 'One more step'),
                    el('p', 'auth-sub', 'Code from your authenticator app, or a recovery code.'));
                const [fc, inCode] = authField('Six-digit code', 'text', 'au-mfa');
                inCode.inputMode = 'numeric'; inCode.autocomplete = 'one-time-code';
                /* auth-error, the class the other steps use: this one was
                   'auth-err', which no rule styled, so a wrong code printed
                   in body ink with no room reserved for it. */
                const err2 = el('div', 'auth-error');
                err2.setAttribute('role', 'alert');
                const go = el('button', 'btn btn-primary auth-go', 'Sign in');
                const submit = async () => {
                    /* A held Enter repeats keydown every few milliseconds, and
                       each one posted the same ticket while the first was still
                       in flight. The disabled button is the in-flight flag. */
                    if (go.disabled) return;
                    go.disabled = true; err2.textContent = '';
                    try {
                        const r = await authApi('/api/auth/mfa-verify',
                                                { ticket: ticket, code: inCode.value });
                        finish(r);
                    } catch (e) { err2.textContent = e.message; go.disabled = false; }
                };
                go.onclick = submit;
                inCode.onkeydown = (e) => { if (e.key === 'Enter' && !e.repeat) submit(); };
                const back = el('button', 'auth-link auth-back', 'Start again');
                back.onclick = () => { ov.dataset.mode = ''; authShow('login'); };
                card.append(fc, err2, go, back);
                setTimeout(() => inCode.focus(), 50);
            }

            async function finish(p) {
                /* A password that is only half the answer. The reply carries no
                   session at all - just a ticket saying who is part-way in - so
                   there is nothing to store until the code checks out. */
                if (p && p.mfa && p.ticket) { authShowMfa(p.ticket); return; }
                setAppSession(p.session);
                teamMe = p.me;
                claimLocalCache(p.me && p.me.id);
                if (p.me && p.me.must_change) { authShow('change'); return; }
                ov.style.display = 'none'; ov.dataset.mode = ''; appBehind(false); renderSidebar();
                applyRoleChrome();
                updatesBadge();
                loadAlerts();       // the boot-time read ran signed out, and read nothing
                // A deep link that hit the login screen carries on now.
                const pend = window.__pendingAdminLink; window.__pendingAdminLink = null;
                if (pend) (pend.dispatch ? dispatchFromAdminLink : printFromAdminLink)(pend.id);
            }
            if (mode === 'setup') {
                card.append(el('h2', null, 'Set up Reactor'),
                    el('p', 'auth-sub', 'Create the master admin account. You need the setup code.'));
                /* Setup opens whenever the accounts are gone, so a Shopify login
                   alone is not enough to become master: the code is set on the
                   server, where only whoever runs it can see it. */
                const [fcode, inCode] = authField('Setup code', 'password', 'au-setup-code');
                inCode.autocomplete = 'off';
                const [fn, inName] = authField('Your name', 'text', 'au-name');
                const [fu, inUser] = authField('Username', 'text', 'au-user');
                const [fp, inPw] = authField('Password (8 characters or more)', 'password', 'au-pw');
                inPw.autocomplete = 'new-password'; inPw.name = 'new-password';
                inPw.placeholder = 'Password (8+ characters)';   // the full wording fits a phone only as the label
                const go = el('button', 'btn btn-primary auth-go', 'Create the master account');
                [inCode, inName, inUser, inPw].forEach(i => i.onkeydown = e => { if (e.key === 'Enter' && !e.repeat) go.click(); });
                go.onclick = async () => {
                    go.disabled = true; err.textContent = '';
                    try {
                        finish(await authApi('/api/auth/setup',
                            { setup_code: inCode.value, name: inName.value, username: inUser.value, password: inPw.value }));
                    } catch (e) { err.textContent = e.message; go.disabled = false; }
                };
                card.append(fcode, fn, fu, fp, err, go);
            } else if (mode === 'change') {
                card.append(el('h2', null, 'Choose your own password'),
                    el('p', 'auth-sub', 'Set your own password before carrying on.'));
                const [fc, inCur] = authField('Current password', 'password', 'au-cur');
                const [fp, inNew] = authField('New password (8 characters or more)', 'password', 'au-new');
                inNew.autocomplete = 'new-password'; inNew.name = 'new-password';
                inNew.placeholder = 'New password (8+ characters)';   // cut off at phone width in full
                const go = el('button', 'btn btn-primary auth-go', 'Save my password');
                [inCur, inNew].forEach(i => i.onkeydown = e => { if (e.key === 'Enter' && !e.repeat) go.click(); });
                go.onclick = async () => {
                    go.disabled = true; err.textContent = '';
                    try {
                        const r = await authApi('/api/auth/password', { current: inCur.value, new: inNew.value });
                        setAppSession(r.session);
                        if (teamMe) teamMe.must_change = false;
                        ov.style.display = 'none'; ov.dataset.mode = ''; appBehind(false); renderSidebar();
                        applyRoleChrome();
                        /* The layouts were refused while the password was a
                           starter; read them now, or Customize stays off for
                           the rest of this session. */
                        wgLoadLayouts();
                    } catch (e) { err.textContent = e.message; go.disabled = false; }
                };
                const back = el('button', 'auth-link auth-back', 'Sign in as someone else');
                back.onclick = () => { setAppSession(''); ov.dataset.mode = ''; authShow('login'); };
                card.append(fc, fp, err, go, back);
            } else {
                authApi('/api/auth/state', {}).then(st => {
                    if (st.setup) { ov.dataset.mode = ''; authShow('setup'); }
                }).catch(() => {});
                card.append(el('h2', null, 'Sign in'),
                    el('p', 'auth-sub', 'Your own account, not Shopify’s. No account? Ask an admin.'));
                const [fu, inUser] = authField('Username', 'text', 'au-user');
                const [fp, inPw] = authField('Password', 'password', 'au-pw');
                const go = el('button', 'btn btn-primary auth-go', 'Sign in');
                const submit = async () => {
                    if (go.disabled) return;   // in flight: a held Enter must not sign in twice
                    go.disabled = true; err.textContent = '';
                    try {
                        finish(await authApi('/api/auth/login', { username: inUser.value, password: inPw.value }));
                    } catch (e) { err.textContent = e.message; go.disabled = false; }
                };
                go.onclick = submit;
                /* Both fields, not just the password: focus lands on Username
                   first, so that is where the first Enter is pressed. The setup
                   and change cards already did this; login was the one that
                   missed it. */
                [inUser, inPw].forEach(i => i.onkeydown = (e) => { if (e.key === 'Enter' && !e.repeat) submit(); });
                /* !e.repeat: a held Enter repeats, and after a refusal the button is
                   live again, so each repeat was another failed attempt counted against
                   the account, and one carried into the two-step card as an empty code. */
                /* There is no reset-by-email: accounts are the app's own, and
                   an admin resets a password from Team, which hands over a
                   starter password that has to be changed on first use. The
                   link says so rather than pretending to send anything. */
                const forgot = el('button', 'auth-link', 'Forgot password?');
                forgot.type = 'button';
                const help = el('p', 'auth-note', 'Ask an admin to reset it in Team. They will give '
                    + 'you a starter password, and you choose your own the first time you sign in with it.');
                help.id = 'au-forgot'; help.hidden = true;
                forgot.setAttribute('aria-controls', 'au-forgot');
                forgot.setAttribute('aria-expanded', 'false');
                forgot.onclick = () => {
                    const open = help.hidden;
                    help.hidden = !open;
                    forgot.setAttribute('aria-expanded', String(open));
                };
                const row = el('div', 'auth-row');
                row.append(err, forgot);
                card.append(fu, fp, row, help, go);
            }
            ov.append(card);
            const first = card.querySelector('input'); if (first) setTimeout(() => first.focus(), 50);
        }
        async function authBoot(attempt) {
            try {
                const st = await authApi('/api/auth/state', {});
                if (st.setup) { authShow('setup'); return; }
                if (!st.logged_in) { authShow('login'); return; }
                teamMe = st.me;
                claimLocalCache(st.me && st.me.id);
                if (st.me.must_change) { authShow('change'); return; }
                const ov = $('auth-overlay'); if (ov) { ov.style.display = 'none'; ov.dataset.mode = ''; appBehind(false); renderSidebar(); }
                applyRoleChrome();
                updatesBadge();
                loadAlerts();
                window.__pendingAdminLink = null;   // the boot-time call ran with a live session
            } catch (e) {
                attempt = attempt || 0;
                if (attempt < 3) setTimeout(() => authBoot(attempt + 1), 3000 * (attempt + 1));
            }
        }
        async function authLogout() {
            try { await authApi('/api/auth/logout', {}); } catch (e) {}
            setAppSession('');
            teamMe = null;
            /* The reload is the point: it drops every in-memory cache - orders,
               customers, CRM, the mailbox - which "show the login screen" left
               sitting behind the overlay for whoever sat down next. */
            clearLocalCache(true);
            location.reload();
        }
        function showTeamView() {
            if (teamCache) { renderTeam(); }
            loadTeam();
        }
        async function loadTeam() {
            const box = $('team-content');
            if (!teamCache) {
                box.innerHTML = '';
                const t = el('div', 'thinking'); t.append(loader(), el('span', null, 'Opening the team…'));
                box.append(t);
            }
            try {
                const r = await api('/api/team/board', {});
                teamCache = r;
                renderTeam();
            } catch (e) {
                /* The page keeps its heading and says what failed, with a way
                   to try again: it was a bare red strip and nothing else. */
                if (teamCache) { renderTeam(); toastError('The team could not be refreshed. ' + (e.message || '')); return; }
                box.innerHTML = '';
                box.append(pageHead({ view: 'team', title: 'Team' }), loadFailure('The team could not be read. ' + (e.message || ''), loadTeam));
            }
        }
        const TEAM_AREAS = [['production', 'Production'], ['dispatch', 'Dispatch'], ['files', 'Files'],
                            ['crm', 'Sales desk'], ['chase', 'Chasing'], ['sizes', 'Size list'],
                            ['settings', 'Settings'], ['team', 'Team'], ['mcp', 'Desktop AI'], ['auth', 'Sign-in']];
        function renderTeam() {
            const box = $('team-content'); box.innerHTML = '';
            const d = teamCache;
            box.append(pageHead({ view: 'team', title: 'Team', line: 'Who can sign in, and what everyone has done.' }));
            box.append(tabStrip([['people', 'People'], ['work', 'Work'], ['activity', 'Activity']], teamSeg,
                                (k) => { teamSeg = k; renderTeam(); }, { label: 'Team sections' }));
            const host = el('div'); box.append(host);
            if (teamSeg === 'activity') renderTeamFeed(host);
            else if (teamSeg === 'work') renderTeamWork(host);
            else renderTeamPeople(host);
        }
        function showStarterPw(name, pw) {
            /* The one showing of a starter password. Copy it, hand it over,
               and the person is forced to change it on first login. */
            /* A notice with one answer (Done), so no X, like uiConfirm. */
            const win = dialog({ title: 'Starter password for ' + name, size: 'confirm-modal',
                                 overlayClass: 'confirm-overlay', x: false });
            const { body } = win;
            body.append(el('p', 'confirm-msg', 'This is shown once and never again. Pass it on '
                + 'privately; they must choose their own password the first time they sign in.'));
            /* An ordinary read-only field: the sign-in card's field left a 40px
               gap for an icon that was not there. */
            const inp = document.createElement('input');
            inp.type = 'text'; inp.readOnly = true; inp.value = pw; inp.className = 'starter-pw';
            inp.setAttribute('aria-label', 'Starter password');
            body.append(inp);
            const foot = win.foot();
            const copy = el('button', 'btn'); copy.append(ico(I.copy), document.createTextNode('Copy'));
            copy.onclick = async () => {
                try { await navigator.clipboard.writeText(pw); copy.textContent = 'Copied'; }
                catch (e) { inp.select(); document.execCommand('copy'); copy.textContent = 'Copied'; }
            };
            const done = el('button', 'btn btn-primary', 'Done');
            done.onclick = win.close;
            foot.append(copy, done);
            inp.onclick = () => inp.select();
        }
        /* An account's Tabs panel (12 Oct 2026, WS-15): what they can open,
           what they may do beyond that, and how they appear in the Inbox, side
           by side under their row. The tabs are in the sidebar's order, under
           its own group names; the colour still saves as it is picked. */
        function teamTabsPanel(u, manageable) {
        const panel = el('div', 'tm-panel');
        const NAMES = { overview: 'Overview', seo: 'SEO', keywords: 'Keywords',
            products: 'Products', customers: 'Customers', liability: 'Liability',
            crm: 'CRM', loans: 'Loan units', mail: 'Inbox', files: 'Files', labels: 'Production Manager',
            memory: 'Memory', skills: 'Skills', chat: 'Chat',
            recon: 'Reconciliation', forecast: 'Forecast', connector: 'Xero sync',
            sizes: 'Size list' };
        const GROUPS = [['Dashboards', ['overview', 'seo', 'keywords', 'products', 'customers']],
                        ['Finance', ['liability', 'recon', 'forecast', 'connector']],
                        ['Operations', ['labels', 'sizes', 'crm', 'loans', 'mail', 'files']],
                        ['Workspace', ['memory', 'skills', 'chat']]];
        const chosen = new Set(Array.isArray(u.tabs) ? u.tabs : DEFAULT_TABS);
        const boxes = [];
        const open = el('fieldset', 'tm-group');
        const lg = el('legend', 'tm-legend');
        lg.append(document.createTextNode('Can open'));
        const all = el('button', 'btn btn-sm', 'Tick all');
        all.type = 'button';
        all.onclick = () => boxes.forEach(b => { b.checked = true; });
        lg.append(all);
        open.append(lg);
        const listed = new Set();
        GROUPS.forEach(([gname, keys]) => {
            const ks = keys.filter(k => TAB_KEYS.indexOf(k) >= 0);
            if (!ks.length) return;
            const row = el('div', 'tm-picks');
            row.append(el('span', 'tm-sub', gname));
            ks.forEach(k => {
                listed.add(k);
                const lab = el('label', 'tm-tabpick');
                const cb = document.createElement('input');
                cb.type = 'checkbox'; cb.checked = chosen.has(k); cb.dataset.k = k;
                boxes.push(cb);
                lab.append(cb, document.createTextNode(NAMES[k] || k));
                row.append(lab);
            });
            open.append(row);
        });
        /* A tab added later and not yet in a group still gets its box. */
        const rest = TAB_KEYS.filter(k => !listed.has(k));
        if (rest.length) {
            const row = el('div', 'tm-picks');
            row.append(el('span', 'tm-sub', 'Other'));
            rest.forEach(k => {
                const lab = el('label', 'tm-tabpick');
                const cb = document.createElement('input');
                cb.type = 'checkbox'; cb.checked = chosen.has(k); cb.dataset.k = k;
                boxes.push(cb);
                lab.append(cb, document.createTextNode(NAMES[k] || k));
                row.append(lab);
            });
            open.append(row);
        }
        open.setAttribute('aria-label', 'Tabs ' + (u.name || 'this account') + ' can open');
        panel.append(open);
        /* A capability, not a tab: seeing Production Manager is not
           the same as being allowed to decide the glass an order is
           cut from. Admins hold it by rank, so they get a statement
           rather than a switch that would not actually revoke it. */
        const perm = el('fieldset', 'tm-group');
        perm.append(el('legend', 'tm-legend', 'Permissions'));
        let sizeBox = null;
        if (u.sizes_by_rank) {
            perm.append(el('p', 'tm-note', 'Can edit the size list (every admin can).'));
        } else {
            const sl = el('label', 'tm-tabpick');
            sizeBox = document.createElement('input');
            sizeBox.type = 'checkbox'; sizeBox.checked = !!u.can_sizes;
            sl.append(sizeBox, document.createTextNode('Can edit the size list'));
            perm.append(sl);
        }
        /* The other capability that reaches outside the app, and
           the heavier of the two: this one talks to customers in
           the company's name. Same rank rule as the size list. */
        let sendBox = null;
        if (u.send_by_rank) {
            perm.append(el('p', 'tm-note', 'Can send email from the Inbox (every admin can).'));
        } else {
            const el2 = el('label', 'tm-tabpick');
            sendBox = document.createElement('input');
            sendBox.type = 'checkbox'; sendBox.checked = !!u.can_send;
            el2.append(sendBox, document.createTextNode('Can send email from the Inbox'));
            perm.append(el2);
        }
        panel.append(perm);
        /* How they appear in the Inbox: the colour saves as it is
           picked, the sign-off with its own Save. The master's own
           colour is editable too: they appear in the Inbox like
           everyone else. */
        const inbox = el('fieldset', 'tm-group');
        inbox.append(el('legend', 'tm-legend', 'Inbox'));
        const cl = el('label', 'pfield');
        cl.append(el('span', null, 'Colour'));
        const csel = el('select', 'psel tm-colour');
        TEAM_TINTS.forEach(t => {
            const o = el('option', null, t.charAt(0).toUpperCase() + t.slice(1));
            o.value = t; if (t === u.colour) o.selected = true;
            csel.append(o);
        });
        csel.onchange = async () => {
            try { await api('/api/team/user',
                            { op: 'colour', id: u.id, colour: csel.value }); }
            catch (e) { toastError(e.message); return; }
            toastOk('Colour changed.');
            loadTeam();
        };
        cl.append(csel); inbox.append(cl);
        let sta = null;
        if (manageable) {
            const sw = el('div');
            const sl2 = el('label', 'pfield');
            sl2.append(el('span', null, 'Sign-off on their email'));
            sta = document.createElement('textarea');
            sta.className = 'mail-draft-text'; sta.rows = 3;
            sta.value = u.sign_off || '';
            sta.setAttribute('aria-label',
                'Sign-off for ' + (u.name || 'this account'));
            sl2.append(sta); sw.append(sl2);
            inbox.append(sw);
        }
        panel.append(inbox);
        /* One Save under all three (12 Oct 2026, WS-15): the tabs, the two
           permissions and the sign-off together. There were two Saves, one
           between the groups. */
        const save = el('button', 'btn btn-primary btn-sm', 'Save'); save.type = 'button';
        save.onclick = async () => {
            save.disabled = true;
            const picked = boxes.filter(b => b.checked).map(b => b.dataset.k);
            try {
                /* Always the explicit list. This used to collapse a fully
                   ticked panel to null, meaning "no list of its own", which the
                   server now reads as the DEFAULT tabs. Since Reconciliation is
                   not in the default set, ticking every box and saving withheld
                   the one tab the admin had just ticked, and the activity
                   ledger recorded the opposite. */
                await api('/api/team/user', { op: 'tabs', id: u.id, tabs: picked });
                /* Only when it actually changed. Sending it every time would
                   write a grant into the activity ledger that nobody made. */
                if (sizeBox && sizeBox.checked !== !!u.can_sizes) {
                    await api('/api/team/user', { op: 'sizes', id: u.id, can_sizes: sizeBox.checked });
                }
                if (sendBox && sendBox.checked !== !!u.can_send) {
                    await api('/api/team/user', { op: 'send', id: u.id, can_send: sendBox.checked });
                }
                if (sta && sta.value !== (u.sign_off || '')) {
                    await api('/api/team/user', { op: 'sign_off', id: u.id, text: sta.value });
                }
                teamTabsOpen = '';
            } catch (e) { toastError(e.message); save.disabled = false; return; }
            toastOk('Saved.');
            loadTeam();
        };
        const saveRow = el('div', 'act-row tm-panel-save'); saveRow.append(save);
        panel.append(saveRow);
        return panel;
        }
        function renderTeamPeople(host) {
            const d = teamCache;
            const lvl = { master: 3, admin: 2, member: 1 };
            const myLevel = lvl[d.my_role] || 0;
            /* The reference's users card: a counted title, a line under it,
               the one action on the right, and the rows edge to edge. */
            const card = el('div', 'card');
            const head = el('div', 'card-head');
            /* The security note, word for word, behind the title (copy plan,
               Team #2 and #3). */
            const pt = el('h3', 'card-title', 'People');
            pt.append(el('span', 'card-n', String(d.users.length)));
            const ptInfo = infoButton('About accounts', { title: 'People', body:
                'Accounts belong to the app, not Shopify. New accounts get a starter password '
                + 'shown once; everyone chooses their own on first sign-in. Tabs controls which '
                + 'parts of the app an account can open; it is enforced by the server, not '
                + 'just hidden.' });
            head.append(titleInfo(pt, ptInfo));
            const act = el('div', 'card-act');
            /* One teal: while the new account's Create or a Tabs panel's Save is open, they have it. */
            const busy = teamNewOpen || d.users.some(u => u.id === teamTabsOpen && u.role !== 'master');
            const add = el('button', 'btn btn-sm' + (busy ? '' : ' btn-primary')); add.append(ico(I.plus), document.createTextNode('New account'));
            add.onclick = () => { teamNewOpen = !teamNewOpen; renderTeam(); };
            head.append(el('p', 'card-desc', 'Made, dispatched, files and sales are the last 30 days.'));
            act.append(add); head.append(act); card.append(head);
            /* The new account's row, unchanged in content, over the table. */
            if (teamNewOpen) {
                const list = el('div', 'files-list card-bleed tm-list');
                const row = el('div', 'files-row tm-row tm-new');
                const inName = document.createElement('input');
                inName.className = 'tm-field'; inName.placeholder = 'Name'; inName.setAttribute('aria-label', 'Name');
                const inUser = document.createElement('input');
                inUser.className = 'tm-field'; inUser.placeholder = 'Username'; inUser.setAttribute('aria-label', 'Username'); inUser.spellcheck = false;
                const roleSel = el('select', 'lbl-size'); roleSel.setAttribute('aria-label', 'Role for the new account');
                [['member', 'Member'], ['parttime', 'Part-time']].concat(myLevel >= 3 ? [['admin', 'Admin']] : [])
                    .forEach(([v, lab]) => { const o = el('option', null, lab); o.value = v; roleSel.append(o); });
                const go = el('button', 'btn btn-primary', 'Create');
                go.onclick = async () => {
                    go.disabled = true;
                    try {
                        const r = await api('/api/team/user', { op: 'create', name: inName.value,
                            username: inUser.value, role: roleSel.value });
                        teamNewOpen = false;
                        showStarterPw(inName.value.trim() || 'the new account', r.starter_password);
                        loadTeam();
                    } catch (e) { go.disabled = false; toastError(e.message); }
                };
                [inName, inUser].forEach(i => i.onkeydown = (e) => { if (e.key === 'Enter') go.click(); });
                row.append(inName, inUser, roleSel, go);
                list.append(row);
                card.append(list);
            }
            /* One table (12 Oct 2026, WS-13): the person over their username,
               the role, the last 30 days' counts under heads with zeros in grey,
               the last login, then Tabs and a menu holding the admin actions
               (WS-14). The facts were one sentence pushed against four buttons. */
            const nf = (n) => n ? String(n) : el('span', 'dt-muted', '0');
            card.append(dtable([{ head: 'Person', cls: 'stack' }, { head: 'Role' }, { head: 'Made', cls: 'num', cap: true }, { head: 'Dispatched', cls: 'num', cap: true }, { head: 'Files', cls: 'num', cap: true }, { head: 'Sales', cls: 'num', cap: true }, { head: 'Last login', cap: true },
                                { head: '', cls: 'act' }],
                d.users.map(u => {
                    const mine = u.id === d.me;
                    const theirLevel = lvl[u.role] || 1;
                    const manageable = u.role !== 'master' && (myLevel >= 3 || myLevel > theirLevel);
                    const who = document.createDocumentFragment();
                    const nameLine = el('span', 'dt-name');
                    if (mine || manageable) {
                        const nameBtn = el('button', 'dt-link', u.name + (mine ? ' (you)' : '')); nameBtn.type = 'button';
                        nameBtn.title = 'Rename';
                        nameBtn.onclick = () => {
                            const inp = document.createElement('input');
                            inp.className = 'files-rename'; inp.value = u.name;
                            let done = false;
                            const finish = async (commit) => {
                                if (done) return; done = true;
                                const v = inp.value.trim();
                                if (commit && v && v !== u.name) {
                                    try { await api('/api/team/user', { op: 'rename', id: u.id, name: v }); }
                                    catch (e) { toastError(e.message); }
                                }
                                loadTeam();
                            };
                            inp.onkeydown = (e) => { if (e.key === 'Enter') finish(true); if (e.key === 'Escape') finish(false); };
                            inp.onblur = () => finish(true);
                            nameBtn.replaceWith(inp);
                            inp.focus(); inp.select();
                        };
                        nameLine.append(nameBtn);
                    } else nameLine.append(document.createTextNode(u.name));
                    who.append(nameLine);
                    const sub = el('span', 'dt-sub', u.username);
                    who.append(sub);
                    if (u.active === false) who.append(el('span', 'lbl-chip note', 'Switched off'));
                    let roleCell;
                    if (u.role === 'master') roleCell = el('span', 'lbl-chip note', 'Master admin');
                    else {
                        const role = el('select', 'lbl-size'); role.setAttribute('aria-label', 'Role for ' + (u.name || u.username));
                        [['admin', 'Admin'], ['member', 'Member'], ['parttime', 'Part-time']].forEach(([v, lab]) => {
                            const o = el('option', null, lab); o.value = v;
                            if (u.role === v) o.selected = true; role.append(o);
                        });
                        role.disabled = myLevel < 3;
                        role.onchange = async () => {
                            try { await api('/api/team/user', { op: 'role', id: u.id, role: role.value }); }
                            catch (e) { toastError(e.message); }
                            loadTeam();
                        };
                        roleCell = role;
                    }
                    const c = (d.counts || {})[u.id] || {};
                    const acts = document.createDocumentFragment();
                    if (manageable) {
                        const tb = el('button', 'btn btn-sm' + (teamTabsOpen === u.id ? ' on' : ''), 'Tabs'); tb.type = 'button';
                        tb.setAttribute('aria-pressed', String(teamTabsOpen === u.id));
                        tb.onclick = () => { teamTabsOpen = teamTabsOpen === u.id ? '' : u.id; renderTeam(); };
                        acts.append(tb);
                    }
                    const items = [];
                    if (manageable) {
                        items.push({ label: 'Reset password', icon: I.refresh, onClick: async () => {
                            if (!(await uiConfirm('Reset ' + u.name + '\'s password? Their current '
                                + 'one stops working immediately.', { title: 'Reset ' + u.name + '\'s password', okText: 'Reset password' }))) return;
                            try {
                                const r = await api('/api/team/user', { op: 'reset_password', id: u.id });
                                showStarterPw(u.name, r.starter_password);
                            } catch (e) { toastError(e.message); }
                            loadTeam();
                        } });
                        if (u.mfa) items.push({ label: 'Reset 2-step', icon: I.shield, onClick: async () => {
                            if (!(await uiConfirm('Reset ' + u.name + '\'s two-step sign-in? '
                                + 'Their password alone signs them in until they set it up again.', { title: 'Reset two-step sign-in', okText: 'Reset two-step' }))) return;
                            try { await api('/api/team/user', { op: 'reset_mfa', id: u.id }); }
                            catch (e) { toastError(e.message); }
                            loadTeam();
                        } });
                        items.push({ label: u.active === false ? 'Restore' : 'Switch off', icon: u.active === false ? I.check : I.x, onClick: async () => {
                            const on = u.active === false;
                            if (!on && !(await uiConfirm('Switch off ' + u.name + '\'s access? They '
                                + 'are signed out immediately and cannot sign back in until restored.', { title: 'Switch off ' + u.name, okText: 'Switch off' }))) return;
                            try { await api('/api/team/user', { op: 'active', id: u.id, active: on }); }
                            catch (e) { toastError(e.message); }
                            loadTeam();
                        } });
                    }
                    if (myLevel >= 3 && u.role !== 'master') items.push({ label: 'Delete account', icon: I.trash, danger: true, onClick: async () => {
                        if (!(await uiConfirm('Delete ' + u.name + '\'s account for good? Their '
                            + 'history keeps their name, but they can never sign in again.',
                            { title: 'Delete ' + u.name + '\'s account', okText: 'Delete the account' }))) return;
                        try { await api('/api/team/user', { op: 'delete', id: u.id }); }
                        catch (e) { toastError(e.message); }
                        loadTeam();
                    } });
                    if (items.length) {
                        const more = el('button', 'icon-btn'); more.type = 'button'; more.innerHTML = I.moreH;
                        more.setAttribute('aria-label', 'More for ' + (u.name || u.username)); more.setAttribute('aria-haspopup', 'menu');
                        more.onclick = (e) => { e.stopPropagation(); dropMenu(more, items); };
                        acts.append(more);
                    }
                    return { cls: u.active === false ? 'settled' : '', cells: [who, roleCell, nf(c.made), nf(c.dispatched), nf(c.files), nf(c.crm),
                                u.last_login_at ? fmtDate(u.last_login_at) : el('span', 'dt-muted', 'Never logged in'), acts],
                             after: teamTabsOpen === u.id && u.role !== 'master' ? teamTabsPanel(u, manageable) : null };
                }), { cls: 'dt-people', label: 'People', stop: 'm' }));
            host.append(card);
        }
        function renderTeamWork(host) {
            const wrap = el('div');
            host.append(wrap);
            (function(){ const t = el('div', 'thinking');
                t.append(loader(), el('span', null, 'Reading the clock\u2026'));
                wrap.append(t); })();
            api('/api/work/board', {}).then(d => {
                wrap.innerHTML = '';
                const nm = (uid) => (d.names || {})[uid] || uid;
                const fd = (s) => { const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
                    return h ? h + 'h ' + String(m).padStart(2, '0') + 'm' : m + 'm'; };
                /* Cards, as the People tab is: a titled head over each list,
                   hours as a table rather than one run-on line, and the payroll
                   export in the sessions card's own head with its dates named. */
                /* A card's rule is its title's info button (copy plan, Team #6). */
                const cardOf = (title, desc, act) => {
                    const c = el('div', 'card');
                    const h = el('div', 'card-head');
                    const ct = el('h3', 'card-title', title);
                    h.append(desc ? titleInfo(ct, infoButton('About ' + title, { title: title, body: desc })) : ct);
                    if (act) { const a2 = el('div', 'card-act'); a2.append(act); h.append(a2); }
                    c.append(h); wrap.append(c); return c;
                };
                const uids = Object.keys(d.totals);
                /* No part-time accounts: the whole tab is one line, with the way
                   to make one (12 Oct 2026, WS-16). It was three cards, two of
                   them empty, and an export of nothing. */
                if (!uids.length && !d.open.length && !d.sessions.length) {
                    const goPeople = el('button', 'btn', 'Open People'); goPeople.type = 'button';
                    goPeople.onclick = () => { teamSeg = 'people'; renderTeam(); };
                    wrap.append(emptyState({ icon: I.clock, text: 'No part-time accounts yet.',
                        sub: 'Set someone\'s role to Part-time and the clock appears for them the next time they open the app.', action: goPeople }));
                    return;
                }
                const counted = (c, n) => { const t = c.querySelector('.card-title'); if (t) t.append(el('span', 'card-n', String(n))); };
                /* Who is on the clock, as a small table at its natural width with
                   Close this session straight after the figures (WS-10). */
                const c1 = cardOf('On the clock now');
                counted(c1, d.open.length);
                if (!d.open.length) {
                    const none = el('div', 'tm-none'); none.append(el('span', 'dt-dot off'), el('span', null, 'Nobody is clocked in.'));
                    c1.append(none);
                } else c1.append(dtable([{ head: 'Person' }, { head: 'Since', cap: true }, { head: 'So far', cap: true }, { head: '', cls: 'act' }],
                    d.open.map(ws => {
                        const res = el('button', 'btn btn-sm', 'Close this session'); res.type = 'button';
                        res.onclick = async () => {
                            if (!(await uiConfirm('Close ' + nm(ws.uid) + '\'s open session now? Use this '
                                + 'when someone forgot to clock out. The closure is recorded as a '
                                + 'correction under your name.', { title: 'Close this session', okText: 'Close session' }))) return;
                            try { await api('/api/work/resolve', { uid: ws.uid }); } catch (e) { toastError(e.message); }
                            renderTeam();
                        };
                        return { cells: [dtMain(nm(ws.uid), null, 'ok'), londonHM(ws.start), fd(ws.secs), res] };
                    }), { cls: 'dt-clock', label: 'On the clock now', stop: 'xs' }));
                /* Hours per person beside the clock (WS-12); in its panel it fills it (13 Oct 2026). */
                const c2 = cardOf('Hours per person', 'Set someone\'s role to Part-time and the clock '
                    + 'appears for them the next time they open the app.');
                c2.classList.add('tm-hours');
                if (!uids.length) c2.append(el('div', 'empty', 'No part-time accounts yet.'));
                else {
                    const bleed = el('div', 'card-bleed');
                    bleed.append(fcTable(['Person', 'Today', 'This week', 'This month', 'Sessions', 'Average'],
                        uids.map(uid => { const t = d.totals[uid];
                            return [nm(uid), fd(t.today), fd(t.week), fd(t.month), String(t.sessions), fd(t.avg)]; }),
                        [0, 1, 1, 1, 1, 1]));
                    c2.append(bleed);
                }
                pairNodes(c1, c2, null, null, { plain: true, flip: true });
                /* The export's dates and button at the head's right end, over a
                   table that reaches that edge. */
                const dateF = (label) => { const w = el('label', 'pfield tm-date'); w.append(el('span', null, label));
                    const i2 = document.createElement('input'); i2.type = 'date'; i2.className = 'field-sm'; w.append(i2); return [w, i2]; };
                const [frmL, frm] = dateF('From'), [toL, to] = dateF('To');
                const exp = el('button', 'btn btn-sm'); exp.append(ico(I.download), document.createTextNode('Export for payroll'));
                exp.onclick = async () => {
                    exp.disabled = true;
                    try {
                        const r = await api('/api/work/report', { from: frm.value || '', to: to.value || '' });
                        const blob = new Blob([r.csv], { type: 'text/csv' });
                        const a = document.createElement('a');
                        a.href = URL.createObjectURL(blob);
                        a.download = 'work-sessions' + (frm.value ? '-' + frm.value : '') + '.csv';
                        document.body.append(a); a.click(); a.remove();
                        setTimeout(() => URL.revokeObjectURL(a.href), 5000);
                    } catch (e) { toastError(e.message); }
                    exp.disabled = false;
                };
                const tools = el('div', 'tm-export'); tools.append(frmL, toL, exp);
                const c3 = cardOf('Recent sessions', 'The export covers the chosen dates, or everything kept when left blank. '
                    + 'Each row is one session: date, clock in, clock out, hours, actions, and whether an admin closed it.', d.sessions.length ? tools : null);
                counted(c3, d.sessions.length);
                /* Each session under heads, and the spare width a day line: the
                   session drawn from clock in to clock out on 07:00 to 17:00, so
                   shift patterns read at a glance (WS-10). */
                const mins = (iso) => { const m = /^(\d\d):(\d\d)/.exec(londonHM(iso) || ''); return m ? (+m[1]) * 60 + (+m[2]) : null; };
                const pos = (m) => Math.max(0, Math.min(1, (m - 420) / 600));
                const scale = el('span', 'tm-dayscale');
                scale.append(el('span', null, '07:00'), el('span', null, '12:00'), el('span', null, '17:00'));
                if (!d.sessions.length) c3.append(el('div', 'empty', 'No completed sessions yet.'));
                else c3.append(dtable([{ head: 'Person' }, { head: 'Date' }, { head: 'Clock in' }, { head: 'Clock out' }, { head: 'Hours', cls: 'num' }, { head: 'Actions', cls: 'num', cap: true }, { head: scale }],
                    d.sessions.slice(0, 40).map(s => {
                        const line = el('span', 'tm-daytrack');
                        const a0 = mins(s.start), a1 = mins(s.end);
                        if (a0 != null && a1 != null) {
                            const bar = el('i');
                            bar.style.left = (pos(a0) * 100) + '%';
                            bar.style.width = (Math.max(0.01, pos(a1) - pos(a0)) * 100) + '%';
                            line.append(bar);
                        }
                        line.setAttribute('aria-hidden', 'true');
                        return { cells: [dtMain(nm(s.uid), s.corrected ? 'Closed by ' + nm(s.corrected_by) : ''), fmtDate(s.start), londonHM(s.start), londonHM(s.end),
                                         fd(s.secs || 0), String((d.event_counts || {})[s.id] || 0), line] };
                    }), { cls: 'dt-sessions', label: 'Recent sessions' }));
            }).catch(e => { wrap.innerHTML = ''; wrap.append(loadFailure('The clock could not be read. ' + (e.message || ''), () => renderTeam())); });
        }
        function renderTeamFeed(host) {
            const d = teamCache;
            const evs = d.events || [];
            /* Each list's counts, from the feed already sent. */
            const byWho = {}, byArea = {};
            evs.forEach(e => { byWho[e.sub] = (byWho[e.sub] || 0) + 1; byArea[e.area] = (byArea[e.area] || 0) + 1; });
            /* An account is sent as its id, and each event names its account by
               that id as sub. The filter offered a field the server does not
               send, so picking anyone showed nothing. */
            const rows = evs.filter(e =>
                (!teamFilterWho || e.sub === teamFilterWho)
                && (!teamFilterArea || e.area === teamFilterArea));
            const card = el('div', 'card');
            const head = el('div', 'card-head');
            const at = el('h3', 'card-title', 'Activity'); at.append(el('span', 'card-n', String(evs.length)));
            const atInfo = infoButton('How much is kept', { title: 'Activity', body: 'Newest first. The feed shows the last 600 actions; the full ledger keeps 8,000 and is in every backup.' });
            head.append(titleInfo(at, atInfo));
            card.append(head);
            const areaName = (a) => (TEAM_AREAS.find(x => x[0] === a) || ['', a])[1];
            const personName = (id) => { const u = d.users.find(x => x.id === id); return (u && u.name) || (d.names || {})[id] || 'Not named yet'; };
            const clearAll = () => { teamFilterWho = ''; teamFilterArea = ''; renderTeam(); };
            /* A filter that is on shows over the feed as a tag you can clear. */
            const tags = [];
            const tag = (words, clear) => { const b = el('button', 'btn btn-sm'); b.type = 'button'; b.append(document.createTextNode(words), ico(I.x));
                b.setAttribute('aria-label', 'Clear the filter ' + words); b.onclick = clear; tags.push(b); };
            if (teamFilterWho) tag(personName(teamFilterWho), () => { teamFilterWho = ''; renderTeam(); });
            if (teamFilterArea) tag(areaName(teamFilterArea), () => { teamFilterArea = ''; renderTeam(); });
            /* One table (12 Oct 2026, WS-11): the time, the area beside what it
               labels, who, and what they did, with day heads. The area sat alone
               at the row's far end. */
            const tableRows = [];
            let lastDay = '';
            rows.forEach(e => {
                const day = fmtDate(e.t);
                if (day !== lastDay) { lastDay = day; tableRows.push({ cls: 'dt-grp', cells: [el('span', 'crm-group', day)] }); }
                const said = e.action + (e.detail ? ': ' + e.detail : '');
                const what = el('span', 'tm-what', said); what.title = said;
                const whatCell = document.createDocumentFragment(); whatCell.append(what);
                if (e.ws) whatCell.append(el('span', 'lbl-chip note', 'On the clock'));
                /* London time, as the Work tab gives it. */
                tableRows.push({ cells: [isNaN(new Date(e.t)) ? '' : londonHM(e.t), areaName(e.area),
                                         e.src === 'system' ? 'System' : personName(e.sub), whatCell] });
            });
            const clr = el('button', 'btn btn-sm', 'Clear filters'); clr.type = 'button'; clr.onclick = clearAll;
            const feed = el('div', 'tm-feed');
            if (tags.length) feed.append(tableTools(tags, []));
            feed.append(dtable([{ head: 'Time' }, { head: 'Area' }, { head: 'Who' }, { head: 'What' }], tableRows,
                { cls: 'dt-feed', label: 'Activity', main: 3, stop: 's',
                  empty: emptyState({ icon: I.search, text: 'Nothing recorded for that view yet.', action: (teamFilterWho || teamFilterArea) ? clr : null }) }));
            /* Who and Area as two short lists beside the feed, each with its
               count; the chosen one has the teal edge, and a person with nothing
               is grey. They were two selects over the feed. */
            const filters = el('div', 'tm-filters'), sels = el('div', 'tm-filter-sels');
            const list = (title, items) => {
                filters.append(el('div', 'tm-filter-h', title));
                const g = el('div', 'tm-filter-list'); g.setAttribute('role', 'group'); g.setAttribute('aria-label', title);
                items.forEach(it => {
                    const b = el('button', 'tm-filter' + (it.on ? ' on' : '') + (it.n ? '' : ' none')); b.type = 'button';
                    b.setAttribute('aria-pressed', String(!!it.on));
                    b.append(el('span', 'tm-filter-l', it.label), el('span', 'cnt', String(it.n)));
                    b.onclick = it.pick;
                    g.append(b);
                });
                filters.append(g);
                /* On a phone the list is a select of the same choices over the feed: the two lists ran 800px first. */
                const s = el('select', 'field-sm'); s.setAttribute('aria-label', title);
                /* Everyone and Everything without the total: it is the heading's count, and it cut the select's words off. */
                items.forEach((it, k) => { const o = el('option', null, k ? it.label + ' (' + it.n + ')' : it.label); o.value = String(k); o.selected = !!it.on; s.append(o); });
                s.onchange = () => items[+s.value].pick();
                sels.append(s);
            };
            list('Who', [{ label: 'Everyone', n: evs.length, on: !teamFilterWho, pick: () => { teamFilterWho = ''; renderTeam(); } }]
                .concat(d.users.map(u => ({ label: u.name || 'Not named yet', n: byWho[u.id] || 0, on: teamFilterWho === u.id,
                                            pick: () => { teamFilterWho = u.id; renderTeam(); } }))));
            list('Area', [{ label: 'Everything', n: evs.length, on: !teamFilterArea, pick: () => { teamFilterArea = ''; renderTeam(); } }]
                .concat(TEAM_AREAS.map(([v, lab]) => ({ label: lab, n: byArea[v] || 0, on: teamFilterArea === v,
                                                        pick: () => { teamFilterArea = v; renderTeam(); } }))));
            const both = el('div', 'tm-feedwrap'); both.append(sels, feed, filters);
            card.append(both);
            host.append(card);
        }
        /* The bar shows one line of it; the tooltip carries all of it. */
        function setViewTitle(text) { const h = $('view-title'); h.textContent = text; h.title = text; }
        /* The section a page sits in, as the sidebar groups it: the crumb
           before the page's name. */
        function setViewCrumb(v) {
            const n = $('nav-' + v), sect = n && n.closest('.nav-sect');
            const g = sect && document.querySelector('.nav-group[aria-controls="' + sect.id + '"]');
            $('view-crumb').textContent = g ? g.textContent.trim() : '';
        }
        function currentView() {
            const n = document.querySelector('.nav-item.active');
            return (n && n.dataset.view) || '';
        }
