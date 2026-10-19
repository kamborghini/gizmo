        /* ---------- settings (store profile) ---------- */
        const prefToggles = () => document.querySelectorAll('#settings-modal .toggle[data-pref]');
        /* words: what the pill says for this row, [on, mid, off]. A row that
           is not a connection (the secrets, the backups, the disk) said
           'Connected' or 'Not connected' about something that is neither. */
        /* Each route's typical time and its slowest twentieth since Reactor
           last started, slowest first (the server keeps them, perf.summary):
           live numbers, so a slow page is named before anybody has to
           describe it. Nothing timed yet, no row. */
        function timingRow(rows) {
            /* Under a millisecond has nothing to say about slowness. */
            const top = (rows || []).filter(r => r && r.count && r.p95 >= 1).slice(0, 5);
            if (!top.length) return null;
            const slow = top.some(r => r.count >= 20 && r.p95 > 2000);
            const name = r => String(r.route || '').replace(/^\/api\//, '').replace(/[\/_-]+/g, ' ');
            const ms = v => v < 1 ? 'under 1 ms' : Math.round(v) + ' ms';
            /* "1 in 20" only from at least 20 answers; fewer cannot say it. */
            return connRow('Response times', slow ? 'mid' : 'on',
                'Slowest since Reactor last started: ' + top.map(r => name(r) + ' usually ' + ms(r.p50)
                    + (r.count >= 20 ? ', 1 in 20 over ' + ms(r.p95) : '')).join(' \u00b7 ')
                    + (slow ? '. Worth mentioning if a page feels slow.' : ''), ['Fine', 'Slow', '']);
        }
        /* A connection: its name with its state beside it, then its line
           (12 Oct 2026). The state sat at the row's far edge, which is the
           controls' place. */
        function connRow(title, state, sub, words) {
            const row = el('div', 'setting-row');
            const w = words || ['Connected', 'Needs setup', 'Not connected'];
            const pill = el('span', 'g-badge ' + (state === 'on' ? 'on' : state === 'mid' ? 'mid' : 'off'),
                state === 'on' ? w[0] : state === 'mid' ? w[1] : w[2]);
            const tl = el('div', 'setting-title has-tag');
            tl.append(document.createTextNode(title), pill);
            const left = el('div'); left.append(tl, el('div', 'setting-sub', sub));
            row.append(left);
            return row;
        }
        function aiConnRow(ai) {
            if (!ai.ok) return connRow('Claude AI', 'off', 'Not set up: the server has no Anthropic key. An admin adds it where Reactor is hosted.',
                ['Active', 'Recent failure', 'Not set up']);
            const m = ai.models || {};
            let sub = m.chat && m.deep && m.chat !== m.deep
                ? 'Active: ' + m.chat + ' for chat, ' + m.deep + ' for Deep analysis and the reports.'
                : 'Active, on ' + (m.chat || m.deep || 'Claude') + ' for chat and every report.';
            if (m.fallback) sub += ' When it cannot answer, ' + m.fallback + ' does, and a chat answer says so under it.';
            const lf = ai.last_failure;
            let failing = false;
            if (lf && lf.at) {
                const when = new Date(lf.at);
                sub += ' Latest failure' + (isNaN(when) ? '' : ', ' + when.toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }))
                    + ': ' + (lf.model || 'the AI model') + ' failed. ' + (lf.why || '')
                    + (lf.answered_by ? ' ' + lf.answered_by + ' answered instead.' : '');
                failing = !lf.answered_by && !isNaN(when) && Date.now() - when.getTime() < 24 * 3600 * 1000;
            }
            return connRow('Claude AI', failing ? 'mid' : 'on', sub, ['Active', 'Recent failure', 'Not set up']);
        }
        const CR_SEAL = ['Encrypted', 'Partly encrypted', 'Not encrypted'];
        const CR_PERM = ['All granted', 'Not checked', 'Missing'];
        async function loadConnections() {
            const host = $('connections'); host.innerHTML = '';
            let s;
            try { s = await api('/api/status', {}); } catch (e) { host.append(el('div', 'setting-sub', 'Could not check connections.')); return; }
            const g = s.google || {};
            /* Secrets at rest. Named first because it is the one row here that
               cannot be inferred from anything else working: every connection
               behaves identically whether or not its token is encrypted. */
            const tv = s.token_vault || {};
            if (!tv.enabled) {
                host.append(connRow('Stored secrets', 'off',
                    'Not encrypted: secrets are stored in plain text.', CR_SEAL));
            } else if ((tv.plaintext || []).length) {
                host.append(connRow('Stored secrets', 'mid',
                    'Mostly encrypted, but these are still in plain text: '
                    + tv.plaintext.join(', ') + '. They are sealed the next time the app '
                    + 'restarts, or the next time each is written.', CR_SEAL));
            } else {
                host.append(connRow('Stored secrets', 'on',
                    tv.stored
                        ? ('Encrypted at rest \u00b7 ' + tv.sealed
                           + (tv.sealed === 1 ? ' secret' : ' secrets') + ' sealed')
                        : 'Encrypted at rest. Nothing stored here yet.', CR_SEAL));
            }
            // Shopify
            host.append(connRow('Shopify store', s.shopify && s.shopify.ok ? 'on' : 'off',
                s.shopify && s.shopify.ok
                    ? ((s.shopify.name || 'Connected') + (s.shopify.currency ? ' (' + s.shopify.currency + ')' : '')
                       + (s.shopify.api_version ? ' \u00b7 API ' + s.shopify.api_version : ''))
                    : 'Reads are not working. Check your access token.'));
            /* Permissions: what the INSTALLED app may actually do. A write the
               app performs but the install cannot is silent until the moment
               it matters - Net 30 failed on every account order for days
               because nothing here said the permission was never granted. */
            const sc = (s.shopify && s.shopify.scopes) || {};
            const miss = Object.keys(sc.missing || {});
            if (sc.error) {
                host.append(connRow('Shopify permissions', 'mid',
                    'Shopify did not say what the app is allowed to do, so this could not be checked.', CR_PERM));
            } else if (miss.length) {
                /* Each permission with what it is for. The app is installed the
                   managed way, so a new permission needs no reinstall: Shopify
                   asks for it the next time Reactor opens after the release. */
                const one = miss.length === 1;
                host.append(connRow('Shopify permissions', 'off',
                    miss.length + (one ? ' permission is' : ' permissions are') + ' missing: '
                    + miss.map(k => k + ', for ' + sc.missing[k]).join('; ')
                    + '. Make sure the app\u2019s configuration lists ' + (one ? 'it' : 'them') + ', release a new version, '
                    + 'and approve ' + (one ? 'it' : 'them') + ' when Shopify asks, the next time Reactor opens.', CR_PERM));
            } else if (sc.checked) {
                host.append(connRow('Shopify permissions', 'on',
                    'Everything the app writes, and the payouts it reads, is permitted.', CR_PERM));
            }
            // Live updates: Shopify pushing order events to the app. Without them
            // everything still works off the short cache and the Refresh button.
            const wh = s.webhooks || {};
            const evAge = (t) => {
                if (!t) return 'no events yet';
                const m = Math.floor((Date.now() / 1000 - t) / 60);
                return m < 1 ? 'last event just now' : m < 60 ? 'last event ' + m + 'm ago'
                    : 'last event ' + Math.floor(m / 60) + 'h ago';
            };
            host.append(connRow('Live updates', wh.ok ? 'on' : 'mid',
                wh.ok ? ('Shopify pushes order changes to the app as they happen (' + evAge(wh.last_event_at)
                         + (wh.version ? ', Shopify version ' + wh.version : '') + ').')
                      : ('No live order events' + (wh.detail && !/unset/i.test(wh.detail) ? ': ' + wh.detail : '')
                         + '. Refreshing on a timer instead.'), ['Receiving', 'Not yet', 'Off']));
            // The shared mailbox behind the Inbox tab.
            const gm = s.gmail || {};
            host.append(connRow('Shared mailbox', gm.connected ? 'on' : gm.client ? 'mid' : 'off',
                gm.connected ? ((gm.address || 'Connected') + '. The Inbox tab tracks who owns each email.')
                : gm.client ? 'Ready to connect: open the Inbox tab for the connect link.'
                : 'Not set up yet. Steps on the Inbox tab.'));
            // The stock bridge: whether Mark made is reaching the stock app.
            const sb = s.stock_bridge || {};
            if (sb.configured || sb.pending) {
                host.append(connRow('Stock app', sb.configured && !sb.pending ? 'on' : 'mid',
                    !sb.configured ? 'Not set up: made glass is not booked against stock.'
                    : sb.pending ? (sb.pending + ' booking(s) waiting to reach the stock app'
                        + (sb.error ? ' (' + sb.error + ')' : '') + '. The app retries on its own.')
                    : 'Made orders book their glass at the stock app automatically.'));
            }
            // Errors the app hit on its own: visible here whether or not the alert
            // emails are configured, because a 500 at the dispatch desk is otherwise
            // invisible to everyone.
            // Snapshots live in the same volume they protect, so a download is the
            // only copy that survives losing it. Say how old the last one is.
            const bkState = s.backup || {};
            const ageDays = (iso) => {
                if (!iso) return null;
                const t = new Date(iso); if (isNaN(t)) return null;
                return Math.floor((Date.now() - t.getTime()) / 86400000);
            };
            const dAge = ageDays(bkState.download_at), sAge = ageDays(bkState.snapshot_at);
            const bkRow = connRow('Backups',
                dAge != null && dAge <= 31 ? 'on' : 'mid',
                (sAge == null ? 'No automatic snapshot yet.'
                              : 'Automatic snapshot ' + (sAge === 0 ? 'today' : sAge + ' days ago') + '.')
                + ' ' + (dAge == null
                    ? 'You have never downloaded one. A snapshot sits in the same storage it protects, so download a copy.'
                    : 'Last download ' + (dAge === 0 ? 'today' : dAge + ' days ago') + '.'), ['Up to date', 'Not downloaded', 'None']);
            host.append(bkRow);
            const errs = s.errors || {};
            if (errs.last_24h) {
                host.append(connRow('App errors', 'mid',
                    errs.last_24h + (errs.last_24h === 1 ? ' failure' : ' failures') + ' in the last 24 hours: '
                    + (errs.recent || []).map(e => e.where).filter((v, i, a) => a.indexOf(v) === i).join(', ')
                    + '. Send this to your developer.', ['', 'Failures', '']));
            }
            // AI: which model answers, and the latest failure in words
            host.append(aiConnRow(s.ai || {}));
            // GA4
            host.append(connRow('Google Analytics 4',
                g.ga4_ready ? 'on' : (g.connected || g.oauth_client) ? 'mid' : 'off',
                g.ga4_ready ? ('Connected' + (g.ga4_property ? ' (property ' + g.ga4_property + ')' : '')) :
                    (g.granted && g.granted.ga4 === false) ? 'Connected without permission to read Analytics. Connect Google again and leave Analytics ticked.' :
                    g.connected ? 'Connected, but no Analytics property is chosen.' :
                        g.oauth_client ? 'Connect Google via the one-time setup link.' : 'Set up the Google connection to add traffic and revenue data.'));
            // Search Console
            host.append(connRow('Google Search Console',
                g.gsc_ready ? 'on' : (g.connected || g.oauth_client) ? 'mid' : 'off',
                g.gsc_ready ? ('Connected' + (g.gsc_site ? ' (' + g.gsc_site + ')' : '')) :
                    (g.granted && g.granted.gsc === false) ? 'Connected without permission to read Search Console. Connect Google again and leave Search Console ticked.' :
                    g.connected ? 'Connected, but no Search Console site is chosen.' :
                        g.oauth_client ? 'Connect Google via the one-time setup link.' : 'Set up the Google connection to add keyword and search data.'));
            // Google Ads (CPC) rides on GA4
            host.append(connRow('Google Ads (CPC)', g.ga4_ready ? 'mid' : 'off',
                g.ga4_ready ? 'Link Google Ads to your GA4 property to see paid CPC and ROAS.' : 'Needs GA4 connected, then a Google Ads link in GA4.',
                ['Connected', 'Needs a link', 'Not connected']));
            // Data volume
            host.append(connRow('Data storage', s.volume && s.volume.ok ? 'on' : 'off',
                s.volume && s.volume.ok ? 'The data disk is healthy. Download a backup now and then (Backups, above).'
                    : 'The data disk is not writable: nothing new is being saved. ' + ((s.volume && s.volume.detail) || ''), ['Healthy', '', 'Not writable']));
            /* The stores by size, with the read cost of anything over a
               megabyte. Most stores are read from disk on every request that
               needs them, so a store that has grown is felt as a slow desk
               long before anybody knows why; this is the number, in advance. */
            const big = ((s.volume && s.volume.stores) || []).filter(r => r.bytes >= 1048576);
            if (big.length) {
                const slow = big.some(r => (r.parse_ms || 0) > 150);
                host.append(connRow('Store sizes', slow ? 'mid' : 'on',
                    big.map(r => r.name + ' ' + (r.bytes / 1048576).toFixed(1) + ' MB'
                        + (r.parse_ms != null ? ' (read in ' + Math.round(r.parse_ms) + ' ms)' : '')).join(' \u00b7 ')
                    + (slow ? '. A save on a store this size rewrites all of it; worth mentioning.' : ''), ['Fine', 'Large', '']));
            }
            const timing = timingRow(s.timing);
            if (timing) host.append(timing);
            // Email alerts
            host.append(connRow('Email alerts', s.email_alerts && s.email_alerts.ok ? 'on' : 'mid',
                s.email_alerts && s.email_alerts.ok ? 'Alerts and failures also reach your inbox.'
                    : 'Only shown inside the app.', ['On', 'In app only', 'Off']));
            // Shipping (World Options)
            const sh = s.shipping || {};
            const shRow = connRow('Shipping (World Options)', sh.ok ? 'on' : sh.available ? 'mid' : 'off',
                sh.ok ? ('Connected. Dispatch couriers from the Production Manager.' + (sh.fulfillment ? '' : ' Fulfilment writer is not wired.'))
                    : sh.available ? 'Add your World Options API key to dispatch couriers.' : 'Not available on this server.');
            if (sh.available) {
                // A real button appended beside the badge, not instead of it:
                // replacing it took away the row's only state readout.
                const mng = textButton(sh.ok ? 'Manage' : 'Set up');
                mng.onclick = () => { closeSettings(); openShippingSettings(); };
                shRow.append(mng);
            }
            host.append(shRow);
            /* Only when something is wrong: a data folder that is not on the
               volume loses everything at the next deploy. */
            if (s.storage && s.storage.warning) host.append(connRow('Storage', 'off', s.storage.warning, ['', '', 'Not on the volume']));
            // Size list health
            const sl = s.size_list || {};
            if (sl.models) {
                host.append(connRow('Gobo size list', sl.dead_aliases ? 'mid' : 'on',
                    sl.models + ' models' + (sl.overrides ? ' · ' + sl.overrides + ' rulings' : '')
                    + (sl.sheet_at ? ' · sheet from ' + fmtDate(sl.sheet_at) : '')
                    + (sl.dead_aliases ? ' · ' + sl.dead_aliases + (sl.dead_aliases === 1 ? ' alias no longer matches and needs' : ' aliases no longer match and need') + ' attention' : '')
                    + (s.coverage && s.coverage.pct != null ? ' · the last automatic size check matched ' + s.coverage.pct + '% of orders' : ''), ['Healthy', 'Needs attention', '']));
            }
            // Master only, matching the server: the zip carries the accounts
            // register, so it is not an admin-level thing to walk off with.
            /* The two buttons belong to the Backups row, as its actions: they
               sat under the last row, six rows below it. */
            /* On their own line under the row's text: beside it they squeezed
               the description into a sliver and ran off a phone's modal. Not
               drawn at all for a role that sees neither button. */
            const bkActs = el('div', 'row-acts');
            if (!teamMe || teamMe.role === 'master') bkRow.append(bkActs);
            const bk = textButton(null, { small: true });
            bk.style.display = (!teamMe || teamMe.role === 'master') ? '' : 'none';
            bk.append(ico(I.download), document.createTextNode('Download backup'));
            bk.title = 'A zip of everything the app has learned: rulings, aliases, state, usage.';
            bk.onclick = async () => {
                bk.disabled = true;
                try {
                    const hdrs = Object.assign({ 'Content-Type': 'application/json' }, await authHeaders());
                    const sess = appSession(); if (sess) hdrs['X-App-Session'] = sess;
                    const res = await fetch('/api/backup', { method: 'POST', headers: hdrs, body: '{}' });
                    if (!res.ok) throw new Error('Backup failed (' + res.status + ')');
                    const blob = await res.blob();
                    const a = document.createElement('a');
                    a.href = URL.createObjectURL(blob);
                    a.download = 'reactor-backup.zip';
                    document.body.append(a); a.click(); a.remove();
                    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
                } catch (e) { toastError(e.message || 'Backup failed'); }
                bk.disabled = false;
            };
            bkActs.append(bk);
            if (!teamMe || teamMe.role === 'master') {   // unknown role: show it; the server enforces master-only
                const rsInput = document.createElement('input');
                rsInput.type = 'file'; rsInput.accept = '.zip'; rsInput.style.display = 'none';
                const rs = textButton(null, { small: true });
                rs.append(ico(I.upload), document.createTextNode('Restore'));
                rs.title = 'Put a downloaded backup zip back: after a lost volume, or a region move.';
                rsInput.onchange = async () => {
                    const f = rsInput.files[0]; rsInput.value = '';
                    if (!f) return;
                    if (!(await uiConfirm('Restore "' + f.name + '"? Everything the app currently '
                        + 'holds is replaced by the backup, and everyone signs in again with the '
                        // "Restore" sounds like a repair, but it overwrites everything
                        // currently in the app. It gets the destructive treatment.
                        + 'accounts it contains.', { title: 'Restore a backup', okText: 'Restore', danger: true }))) return;
                    rs.disabled = true;
                    try {
                        const b64 = await new Promise((res2, rej) => {
                            const r = new FileReader();
                            r.onload = () => res2(String(r.result).split(',')[1] || '');
                            r.onerror = () => rej(new Error('Could not read the file.'));
                            r.readAsDataURL(f);
                        });
                        const out = await api('/api/restore', { zip: b64 });
                        /* Anything the restore would not take is said out loud:
                           a green toast over a silently skipped store is how a
                           lost CRM looks like a successful restore. */
                        const miss = out.skipped || [];
                        if (miss.length) toastError('Restored ' + out.restored + ' files, but skipped: '
                            + miss.slice(0, 6).join(', ') + (miss.length > 6 ? '…' : '')
                            + '. Sign in again to carry on.');
                        else addToast('Restored ' + out.restored + ' files. Sign in again to carry on.', 'good');
                        setAppSession('');
                        setTimeout(() => authShow('login'), 800);
                    } catch (e) { toastError(e.message || 'The restore failed.'); }
                    rs.disabled = false;
                };
                rs.onclick = () => rsInput.click();
                bkActs.append(rs, rsInput);
            }
        }
        /* Ask for the person's own password before a change that a borrowed
           session must not be able to make alone. Resolves to the password,
           or null when they cancel. */
        /* In-page replacement for the browser's prompt dialog: a title, a line
           of help, one text field. Resolves with the text, or null when dismissed. */
        /* The composer's questions (a link's address) through the page's own
           dialog: native prompts do nothing inside the admin iframe. */
        const composerAsk = (title, message, label, initial) => uiAskText(title, message, label, initial, 'Add link');
        function uiAskText(title, message, label, initial, okText) {
            return new Promise(resolve => {
                /* A question typed into: it closes by its X or Cancel only. */
                let answer = null;
                const win = dialog({ title: title, onClose: () => resolve(answer) });
                const body = win.body;
                const finish = (v) => { answer = v; win.close(); };
                if (message) body.append(el('p', 'field-help', message));
                const f = formField(label || 'Value');
                const inp = el('input', 'psel'); inp.type = 'text'; inp.value = initial || '';
                f.append(inp); body.append(f);
                const foot = win.foot();
                const cancel = textButton('Cancel'); cancel.onclick = () => finish(null);
                const go = textButton(okText || 'Continue', { kind: 'primary' });
                go.onclick = () => finish(inp.value);
                inp.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); go.click(); } };
                foot.append(cancel, go);
                inp.focus(); inp.select();
            });
        }

        function uiAskPassword(title, message, okText) {
            return new Promise(resolve => {
                /* A question typed into: it closes by its X or Cancel only. */
                let answer = null;
                const win = dialog({ title: title, onClose: () => resolve(answer) });
                const body = win.body;
                const finish = (v) => { answer = v; win.close(); };
                if (message) body.append(el('p', 'field-help', message));
                const f = formField('Your password');
                const inp = el('input', 'psel'); inp.type = 'password'; inp.autocomplete = 'current-password';
                f.append(inp); body.append(f);
                const foot = win.foot();
                const cancel = textButton('Cancel'); cancel.onclick = () => finish(null);
                const go = textButton(okText || 'Continue', { kind: 'primary' });
                go.onclick = () => finish(inp.value);
                inp.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); go.click(); } };
                foot.append(cancel, go);
                inp.focus();
            });
        }

        /* Two-step sign-in. Enrolment is deliberately two moves: scan, then
           prove a code works. Turning it on because someone SAID they scanned
           it is how an account locks its owner out. Turning it off, or
           starting again, takes the password: the second factor exists for
           the day a session token is in the wrong hands. */
        async function refreshMfaRow() {
            const btn = $('mfa-btn'), sub = $('mfa-sub');
            if (!btn) return;
            let st;
            try { st = await api('/api/auth/mfa', { op: 'status' }); }
            catch (e) { return; }
            if (st.enabled) {
                sub.textContent = 'On. ' + (st.recovery_left || 0)
                    + ' recovery code' + ((st.recovery_left === 1) ? '' : 's') + ' left.';
                btn.textContent = 'Turn off';
                btn.onclick = async () => {
                    const pw = await uiAskPassword('Turn off two-step sign-in',
                        'Your password becomes the only thing protecting the dispatch desk '
                        + 'and the books.', 'Turn it off');
                    if (pw === null) return;
                    try { await api('/api/auth/mfa', { op: 'off', current: pw }); }
                    catch (e) { toastError(e.message); return; }
                    toastOk('Two-step sign-in is off.');
                    refreshMfaRow();
                };
            } else {
                sub.textContent = 'A code from your phone as well as your password.';
                btn.textContent = 'Set up';
                btn.onclick = openMfaSetup;
            }
        }

        /* Self-service, and the only thing on this modal that belongs to the
           person rather than to the store. Hidden until the server has actually
           answered: somebody with no Inbox has no sign-off to set, and an empty
           box they cannot save is worse than no box. */
        async function refreshSignOffRow() {
            const row = $('signoff-row'), ta = $('signoff-text'), btn = $('signoff-btn');
            if (!row) return;
            let d;
            try { d = await api('/api/mail/settings', { op: 'get' }); }
            catch (e) { $('signoff-row').style.display = 'none'; return; }
            ta.value = d.sign_off || '';
            $('signoff-row').style.display = '';
            btn.onclick = async () => {
                btn.disabled = true;
                try { await api('/api/mail/settings', { op: 'sign_off', text: ta.value }); }
                catch (e) { toastError(e.message); btn.disabled = false; return; }
                toastOk('Sign-off saved.');
                btn.disabled = false;
                refreshMailQuiet();
            };
        }

        async function openMfaSetup() {
            const pw = await uiAskPassword('Two-step sign-in',
                'Confirm it is you before a second factor is added to this account.');
            if (pw === null) return;
            const win = dialog({ title: 'Two-step sign-in' });
            const { overlay, modal, head, x, body } = win;

            (async () => {
                let st;
                try { st = await api('/api/auth/mfa', { op: 'start', current: pw }); }
                catch (e) { body.append(el('div', 'msg error', e.message)); return; }
                body.append(el('p', 'field-help',
                    'Add this to an authenticator app, then type the six-digit code it '
                    + 'shows to prove it works. It is not on until you do.'));
                const code = el('div', 'evidence'); code.textContent = st.secret;
                code.style.cssText = 'font-family:var(--font-mono);padding:var(--sp-2-5) var(--sp-3);'
                    + 'background:var(--surface-tertiary);border-radius:var(--radius-control);word-break:break-all';
                body.append(code);
                const f = formField('The code from your app');
                const inp = el('input', 'psel'); inp.type = 'text'; inp.inputMode = 'numeric';
                inp.maxLength = 6; inp.placeholder = '000000';
                f.append(inp); body.append(f);
                const foot = el('div', 'modal-foot');
                const cancel = textButton('Cancel'); cancel.onclick = win.close;
                const go = textButton('Turn it on', { kind: 'primary' });
                go.onclick = async () => {
                    go.disabled = true;
                    let r;
                    try { r = await api('/api/auth/mfa', { op: 'confirm', code: inp.value }); }
                    catch (e) { toastError(e.message); go.disabled = false; return; }
                    body.innerHTML = '';
                    body.append(el('p', 'field-help',
                        'Two-step sign-in is on. Keep these recovery codes somewhere safe: '
                        + 'each one gets you in once if you lose your phone, and this is the '
                        + 'only time they are shown.'));
                    const list = el('div', 'evidence');
                    list.style.cssText = 'font-family:var(--font-mono);line-height:var(--lh-prose);'
                        + 'padding:var(--sp-2-5) var(--sp-3);background:var(--surface-tertiary);border-radius:var(--radius-control)';
                    (r.recovery || []).forEach(c => list.append(el('div', null, c)));
                    body.append(list);
                    foot.innerHTML = '';
                    const done = textButton('I have saved them', { kind: 'primary' });
                    done.onclick = () => { win.close(); refreshMfaRow(); };
                    foot.append(done);
                };
                foot.append(cancel, go); modal.append(foot);
                inp.focus();
            })();
        }

        function openSettings() {
            $('pf-voice').value = profile.brand_voice || '';
            $('pf-goals').value = profile.business_goals || '';
            $('pf-strategy').value = profile.strategy || '';
            $('pf-notes').value = profile.notes || '';
            prefToggles().forEach(t => setSwitch(t, !!profile.prefs[t.dataset.pref]));
            /* Only an admin can change the store profile (the server says so
               on every write): for anyone else the fields and switches are
               shown as they stand, not offered as controls that bounce. */
            const canEdit = connIsAdmin();
            ['pf-voice', 'pf-goals', 'pf-strategy', 'pf-notes'].forEach(id => { $(id).readOnly = !canEdit; });
            prefToggles().forEach(t => { if (canEdit) t.removeAttribute('aria-disabled'); else t.setAttribute('aria-disabled', 'true'); });
            $('settings-save').hidden = !canEdit;
            $('settings-readonly').hidden = canEdit;
            settingsAtOpen = profileKey(profile);
            dialogShow($('settings-modal'));
            /* The profile's boxes grow to fit their text (12 Oct 2026): on a
               phone two lines held a paragraph, scrolling inside the box. */
            document.querySelectorAll('#settings-modal textarea.pf-input').forEach(ta => {
                if (ta.dataset.grows) ta.dispatchEvent(new Event('input'));
                else { ta.dataset.grows = '1'; autoGrow(ta); }
            });
            (canEdit ? $('pf-voice') : $('settings-close')).focus();
            loadConnections();
            loadSchedule();
            loadUsage();
            loadPrivacy();
        }
        /* Settings, Privacy requests (admins only; the server says the same).
           A customer erasure Shopify asks for waits here for an admin, because
           anyone holding the app's secret can send one and an erasure cannot
           be undone: beside each, what Shopify says about the customer, how far
           the erasure reaches, and whether the same one was stopped before.
           Data requests are listed with the date the customer must have their
           data by, until someone marks them answered. */
        function loadPrivacy() {
            const sec = $('privacy-sec'), box = $('privacy-reqs');
            if (!sec || !box) return;
            sec.hidden = !connIsAdmin();
            if (sec.hidden) return;
            box.replaceChildren(el('div', 'setting-sub', 'Checking requests…'));
            api('/api/privacy', {}).then(paintPrivacy)
                .catch(e => box.replaceChildren(el('div', 'setting-sub', 'Privacy requests could not be read. ' + (e.message || ''))));
        }
        function privacyShopify(h) {
            const when = h.checked_at ? ' (checked ' + fmtDate(h.checked_at) + ')' : '';
            if (h.shopify === 'live') return 'Shopify still has a customer with this customer number, or with an address this would erase' + when
                + '. Check they were erased in Shopify before erasing them here.';
            if (h.shopify === 'gone') return 'Shopify has no customer with this customer number or with any address this would erase' + when + '.';
            return 'Shopify could not be asked about this customer yet.';
        }
        function privacyReach(sc) {
            if (!sc || sc.unreadable) return 'The CRM cannot be read just now, so what this would erase is not known.';
            if (sc.contacts == null) return '';
            const n = sc.contacts || 0;
            if (!n) return 'No contact in the CRM has this address; email threads from it go.';
            let t = 'Erases ' + (n === 1 ? 'one contact' : n + ' contacts') + ' in the CRM';
            if (sc.likely_duplicates) t += ', ' + (sc.likely_duplicates === 1 ? 'one of them only because it looks'
                : sc.likely_duplicates + ' of them only because they look') + ' like the same person';
            if (sc.other_addresses) t += (n === 1 ? ', which holds ' : ', which hold ') + (sc.other_addresses === 1 ? 'one other address' : sc.other_addresses + ' other addresses');
            return t + ', with their deals, leads and email threads.';
        }
        function paintPrivacy(d) {
            const box = $('privacy-reqs'); if (!box) return;
            box.replaceChildren();
            const held = (d && d.held) || [], asks = (d && d.data_requests) || [];
            /* How the requests work, word for word, behind the section title's
               info button (copy plan, Settings #8). */
            const pt = box.previousElementSibling;
            if (pt && pt.classList.contains('section-title') && !pt.querySelector('.info'))
                pt.append(infoButton('About privacy requests', { title: 'Privacy requests', body: 'When you erase a customer in Shopify, Shopify asks Reactor to erase what it holds about them too. '
                    + 'Each request waits here for an admin to erase it, or to stop one nobody here asked for. Shopify allows thirty days from when it arrives.' }));
            if (!held.length && !asks.length) { box.append(el('div', 'setting-sub', 'Nothing waiting.')); return; }
            /* A flood of erasure requests nobody asked for means the app's
               secret is out: one click stops them all, each recorded. */
            const total = held.length + ((d && d.held_more) || 0);
            if (total > 10) {
                const row = el('div', 'setting-row'); const text = el('div');
                text.append(el('div', 'setting-title', total + ' erasure requests are waiting'),
                    el('div', 'setting-sub', 'More than Shopify sends for one shop. If nobody here erased these customers in Shopify, stop them all: someone holds the app\u2019s secret.'));
                const acts = el('div', 'row-acts');
                const all = textButton(null, { small: true }); all.type = 'button'; all.textContent = 'Stop all';
                all.onclick = async () => {
                    if (!await uiConfirm('Stop all ' + total + ' waiting erasure requests and keep those customers\u2019 records? Only if nobody here erased them in Shopify.',
                        { title: 'Stop every erasure request', okText: 'Stop them all' })) return;
                    privacyOp({ op: 'stop_all' }, all);
                };
                acts.append(all); row.append(text, acts); box.append(row);
            }
            held.forEach(h => {
                const row = el('div', 'setting-row');
                const text = el('div');
                text.append(el('div', 'setting-title', h.email),
                    el('div', 'setting-sub', 'Arrived ' + fmtDate(h.received) + (h.customer_id ? ', for Shopify customer ' + h.customer_id : '') + '. '
                        + (h.overdue ? 'Overdue: Shopify allowed until ' + fmtDate(h.due) + '.' : 'Shopify allows until ' + fmtDate(h.due) + '.')),
                    el('div', 'setting-sub', privacyShopify(h)));
                const reach = privacyReach(h.scope);
                if (reach) text.append(el('div', 'setting-sub', reach));
                if (h.stopped_before) text.append(el('div', 'setting-sub', 'The same request was stopped as not asked for on ' + fmtDate(h.stopped_before) + '.'));
                const acts = el('div', 'row-acts');
                const er = textButton(null, { small: true }); er.type = 'button'; er.textContent = 'Erase now';
                if (h.scope && h.scope.unreadable) er.disabled = true;
                er.onclick = async () => {
                    if (!await uiConfirm('Erase what Reactor holds about ' + h.email + '? ' + reach
                        + ' It cannot be undone. Dispatch and customs records stay, with a note, as the law requires.',
                        { title: 'Erase customer records', okText: 'Erase' })) return;
                    /* The reach shown, checked again by the server at the click. */
                    privacyOp({ op: 'erase', id: h.id, reach: (h.scope && h.scope.key) || '' }, er);
                };
                const st = textButton(null, { small: true }); st.type = 'button'; st.textContent = 'Not requested';
                st.onclick = async () => {
                    if (!await uiConfirm('Stop this request and keep ' + h.email + '\u2019s records? Only if nobody here erased them in Shopify: '
                        + 'a request Shopify did not send means someone holds the app\u2019s secret.', { title: 'Stop erasure request', okText: 'Stop it' })) return;
                    privacyOp({ op: 'stop', id: h.id }, st);
                };
                acts.append(er, st);
                row.append(text, acts);
                box.append(row);
            });
            if (d && d.held_more) box.append(el('div', 'setting-sub', 'And ' + d.held_more + ' more waiting, shown as these are settled.'));
            asks.forEach(a => {
                const row = el('div', 'setting-row'); const text = el('div');
                text.append(el('div', 'setting-title', a.email || ('Customer ' + (a.customer_id || 'with no address given'))),
                    el('div', 'setting-sub', 'Asked on ' + fmtDate(a.at) + ' for the data held about them. '
                        + (a.overdue ? 'Overdue: they should have had it by ' + fmtDate(a.due) + '.' : 'Send it to them by ' + fmtDate(a.due) + '.')));
                const acts = el('div', 'row-acts');
                const done = textButton(null, { small: true }); done.type = 'button'; done.textContent = 'Mark answered';
                done.onclick = () => privacyOp(a.id ? { op: 'answered', id: a.id, email: a.email } : { op: 'answered', at: a.at, email: a.email }, done);
                acts.append(done);
                row.append(text, acts);
                box.append(row);
            });
        }
        async function privacyOp(payload, btn) {
            setBusy(btn, true);
            try {
                const d = await api('/api/privacy', payload);
                paintPrivacy(d);
                if (d && d.notice) toastOk(d.notice);
            } catch (e) {
                setBusy(btn, false);
                toastError('That was not done. ' + (e.message || ''));
                loadPrivacy();
            }
        }
        /* One way to save in the whole window: every switch saves the moment
           it is changed, and each block of text has its own Save under it.
           The four preference switches used to wait for a footer 'Save
           profile' while the Auto-refresh switch beside them saved at once,
           so the footer's Cancel undid one and not the other. A change that
           alters the Overview recomputes it once, when the window closes. */
        /* The profile as it was when the window opened, to tell a real change
           from a switch flicked and put back. */
        let settingsAtOpen = '';
        const profileKey = (p) => JSON.stringify([p.brand_voice || '', p.business_goals || '', p.strategy || '', p.notes || '',
            Object.keys(DEFAULT_PREFS).map(k => !!(p.prefs || {})[k])]);
        function closeSettings() {
            dialogHide($('settings-modal'));
            const changed = settingsAtOpen && profileKey(profile) !== settingsAtOpen;
            settingsAtOpen = '';
            /* Only an Overview that has been run is run again: one still on
               its Run button stays there, because a paid run starts only when
               someone presses Run. */
            if (!changed || !overviewCache) return;
            overviewCache = null; // profile changed, recompute the Overview
            if ($('view-overview').classList.contains('active')) loadOverview(true);
        }
        async function savePrefToggle(t) {
            if (t.getAttribute('aria-disabled') === 'true') return;
            const was = t.classList.contains('on');
            setSwitch(t, !was);
            const prefs = {};
            prefToggles().forEach(x => prefs[x.dataset.pref] = x.classList.contains('on'));
            try {
                /* The switches alone. The server merges them into the profile
                   it holds: posting this page's copy of the whole profile let
                   a stale or empty copy overwrite the stored text. */
                const d = await api('/api/profile', { prefs: prefs });
                if (d && d.profile) { profile = d.profile; profile.prefs = Object.assign({}, DEFAULT_PREFS, d.profile.prefs || {}); }
                else profile.prefs = prefs;
                cacheProfile();
            } catch (e) {
                setSwitch(t, was);
                toastError('That setting was not saved. ' + (e.message || ''));
            }
        }
        async function applySettings() {
            /* Built as a copy and taken as the profile only once the server
               has it: a failed save left its text in the profile, and the
               next switch then sent the text that had failed. */
            const prefs = {};
            prefToggles().forEach(t => prefs[t.dataset.pref] = t.classList.contains('on'));
            const next = Object.assign({}, profile, {
                brand_voice: $('pf-voice').value.trim(), business_goals: $('pf-goals').value.trim(),
                strategy: $('pf-strategy').value.trim(), notes: $('pf-notes').value.trim(), prefs: prefs });
            const btn = $('settings-save'); btn.disabled = true; btn.textContent = 'Saving…';
            try {
                const d = await api('/api/profile', { profile: next });
                profile = (d && d.profile) ? d.profile : next;
                profile.prefs = Object.assign({}, DEFAULT_PREFS, profile.prefs || {});
                cacheProfile();
                btn.textContent = 'Save profile';
                toastOk('Profile saved.');
            } catch (e) {
                btn.textContent = 'Save failed, retry';
            } finally { btn.disabled = false; }
        }
        $('settings-btn').onclick = () => { openSettings(); refreshMfaRow(); refreshSignOffRow(); };
        $('settings-close').onclick = closeSettings;
        $('settings-save').onclick = applySettings;
        prefToggles().forEach(t => t.onclick = function () { savePrefToggle(this); });
        function loadUsage() {
            const box = $('usage'); if (!box) return;
            box.innerHTML = '<div class="setting-sub">Loading usage…</div>';
            api('/api/usage', { days: 30 }).then(d => {
                const u = (d && d.usage) || {}; box.innerHTML = '';
                const top = el('div', 'setting-sub');
                top.append(document.createTextNode('Estimated AI spend: '));
                top.append(el('b', null, '$' + (u.cost || 0).toFixed(2)));
                top.append(document.createTextNode(' across ' + (u.runs || 0) + ' calls. Same volume on Sonnet ≈ $' + (u.cost_if_sonnet || 0).toFixed(2) + ', on Haiku ≈ $' + (u.cost_if_haiku || 0).toFixed(2) + '.'));
                box.append(top);
                if (Array.isArray(u.by_kind) && u.by_kind.length) {
                    const wrap = el('div', 'ktable-wrap'); wrap.style.marginTop = 'var(--sp-2-5)'; const tbl = el('table', 'ktable');
                    const thead = el('thead'); const htr = el('tr');
                    ['Type', 'Runs', 'Avg cost', 'Total'].forEach((h, i) => htr.append(el('th', i ? 'num' : null, h)));
                    thead.append(htr); tbl.append(thead); const tb = el('tbody');
                    u.by_kind.forEach(k => {
                        const tr = el('tr');
                        tr.append(el('td', 'kw', k.kind));
                        tr.append(el('td', 'num', String(k.runs)));
                        tr.append(el('td', 'num', '$' + (k.avg_cost || 0).toFixed(3)));
                        tr.append(el('td', 'num', '$' + (k.cost || 0).toFixed(2)));
                        tb.append(tr);
                    });
                    tbl.append(tb); wrap.append(tbl); box.append(wrap);
                } else {
                    box.append(el('div', 'setting-sub', 'No AI usage recorded yet. Run an audit or chat, then reopen this.'));
                }
            }).catch(() => { box.innerHTML = '<div class="setting-sub">Usage unavailable.</div>'; });
        }
        /* This switch says whether an unattended run happens overnight, so it
           must never show a setting the server did not accept. It used to flip
           its own class first and then discard every error, which left the
           merchant looking at "on" while nothing had been enabled and nothing
           would ever say so. The class now follows the WRITE: it moves when
           the server agrees, and moves back when it does not. */
        function paintSchedule(on, hours) {
            setSwitch($('sched-toggle'), !!on);
            if (hours) $('sched-freq').value = String(hours);
            $('sched-freq-row').style.display = on ? '' : 'none';
        }
        function loadSchedule() {
            api('/api/schedule', {}).then(d => {
                const s = (d && d.schedule) || {};
                paintSchedule(!!s.enabled, s.every_hours);
            }).catch(e => {
                /* A failed READ must not be painted as "off" either: that is
                   the same lie in the other direction, so say so rather than
                   leaving the switch showing whatever it happened to hold. */
                toastError('The schedule could not be read. ' + (e.message || ''));
            });
        }
        $('sched-toggle').onclick = async function () {
            const was = this.classList.contains('on');
            const on = !was;
            const hours = parseInt($('sched-freq').value, 10) || 168;
            paintSchedule(on, hours);
            try {
                await api('/api/schedule', { config: { enabled: on, every_hours: hours } });
            } catch (e) {
                paintSchedule(was, hours);
                toastError('The schedule was not changed. ' + (e.message || ''));
            }
        };
        $('sched-freq').onchange = async function () {
            const hours = parseInt(this.value, 10) || 168;
            try {
                await api('/api/schedule', { config: { every_hours: hours } });
            } catch (e) {
                loadSchedule();
                toastError('The frequency was not changed. ' + (e.message || ''));
            }
        };
        /* The X is the only way out, like every other modal here (user rule:
           a misclick must not wipe a filled form, and Settings IS a form).
           This was the one modal that still closed on backdrop and Escape. */

