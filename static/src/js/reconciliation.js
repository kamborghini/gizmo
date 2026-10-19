        async function showReconView() { renderRecon(); refreshRecon(); }
        let reconListSeq = 0;   // the latest list read; see refreshReconList
        let reconStatusSeq = 0; // the latest status read: only a full refresh asks
        async function refreshRecon() {
            /* Two independent reads, fired together rather than one after the
               other. The status half is the expensive one: it reads the whole
               reconciliation store and asks Xero and Gmail whether they are
               still connected. */
            /* One sequence for both reads. The full refresh's status half is
               the slow one, so a chip clicked while it was in flight drew its
               list and was then painted over by the old filter's rows when
               the refresh landed; a refresh overtaken by a newer read is
               dropped like a stale list is. */
            const my = ++reconListSeq, mySt = ++reconStatusSeq;
            let st, ex;
            try {
                [st, ex] = await Promise.all([
                    api('/api/recon/status', {}),
                    api('/api/recon/exceptions', reconFilter)]);
            } catch (e) {
                if (my !== reconListSeq) return;
                reconCache = { error: e.message };
                if (document.querySelector('#view-recon.active')) renderRecon();
                return;
            }
            if (my !== reconListSeq) {
                /* Overtaken on the list, by a filter change that did not ask
                   for the status: unless a later full refresh did, this status
                   is the newest there is, and the cache holds an older one
                   (Xero still connected after a Disconnect, say). */
                if (mySt === reconStatusSeq && reconCache && !reconCache.error) {
                    reconCache.st = st;
                    if (document.querySelector('#view-recon.active')) renderRecon();
                }
                return;
            }
            reconCache = { st, ex };
            if (document.querySelector('#view-recon.active')) renderRecon();
        }
        async function refreshReconList() {
            /* Changing a filter changes which discrepancies are listed. It
               cannot change whether Xero is connected or when the last sweep
               ran, so it does not ask. */
            if (!reconCache || reconCache.error) return refreshRecon();
            /* One answer per filter change, and only the latest is drawn: two
               quick chip clicks could land the slower, earlier answer last,
               leaving Critical rows listed under the High chip. */
            const my = ++reconListSeq;
            let ex;
            try { ex = await api('/api/recon/exceptions', reconFilter); }
            catch (e) {
                if (my !== reconListSeq) return;
                reconCache = { error: e.message };
                if (document.querySelector('#view-recon.active')) renderRecon();
                return;
            }
            if (my !== reconListSeq) return;
            reconCache = { st: (reconCache || {}).st, ex: ex };
            if (document.querySelector('#view-recon.active')) renderRecon();
        }
        const RECON_SEV = { critical: ['Critical', 'bad'], high: ['High', 'bad'],
                            medium: ['Medium', 'warn'], low: ['Low', 'note'] };
        /* One name per status, wherever it is shown: the filter, the row, the
           buttons and the history. It was written four ways ('Errors',
           'Confirmed error', 'confirmed error', 'confirmed_error'). */
        const RECON_STATUS = { new: 'New', investigating: 'Investigating', explained: 'Explained',
                               confirmed_error: 'Confirmed error', corrected: 'Corrected', ignored: 'Ignored' };
        const reconStatusWord = (k) => RECON_STATUS[k] || cap(String(k || '').replace(/_/g, ' '));
        const RECON_OPEN = { new: 1, investigating: 1 };
        /* The server formats the amount itself: symbol-first for the three
           currencies it knows, the code and a space for every other, and no
           thousands separator either way. The row slot one tab away is written
           by the app's shared money(), so the same 14px slot printed
           "GBP 1234.56" next to "£1,234.56". Read back to a number and
           reprinted through the one formatter, so the pair has one money. */
        function reconMoney(disp) {
            const m = /^(-?)\s*(?:([\u00a3$\u20ac])|([A-Z]{3}))\s*([\d,]+(?:\.\d+)?)$/.exec(String(disp == null ? '' : disp).trim());
            if (!m) return disp || '';
            const n = parseFloat(m[4].replace(/,/g, ''));
            if (!isFinite(n)) return disp || '';
            return money(m[1] === '-' ? -n : n, m[3] || ({ '\u00a3': 'GBP', '$': 'USD', '\u20ac': 'EUR' })[m[2]], 2);
        }
        /* The short What for each kind of discrepancy (12 Oct 2026): the row
           names the problem in a few words and its Record column names the
           record; the server's full sentence heads the opened detail. */
        const RECON_WHAT = {
            shopify_sale_missing: 'Sale missing in Xero', order_invoice_amount_mismatch: 'Totals differ',
            order_invoice_tax_mismatch: 'VAT differs', shopify_refund_missing: 'Refund missing in Xero',
            payout_missing_from_bank: 'Payout not in the bank', payout_bank_unreconciled: 'Payout deposit not reconciled',
            payout_explained_by_fees: 'Payout short by its fees', stale_unreconciled: 'Bank line unreconciled',
            duplicate_bill_number: 'Duplicate bill number', possible_duplicate_bill: 'Possible duplicate bill',
            overpaid_invoice: 'Invoice over-allocated', chargeback_missing_from_xero: 'Chargeback missing in Xero',
            xero_sale_without_shopify: 'Xero sale, no Shopify order', invoice_numbering_unlinked: 'Invoice numbers unlinked',
            gmail_doc_missing_from_xero: 'Document missing in Xero', remittance_unknown_invoice: 'Remittance names an unknown invoice',
            remittance_amount_mismatch: 'Remittance amount differs', remittance_payment_missing: 'Remittance not paid in Xero',
        };
        /* A sweep note saying something went wrong, as against one saying what
           the sweep tidied away: the first kind turns the sweep's dot amber. */
        const RECON_NOTE_BAD = /could not|failed|crashed|skipped|partial|stopped|not connected|not readable|missing|empty/i;
        /* The sweep's status line, on the tab row (12 Oct 2026): a dot (amber
           when a note holds a failure, red when Xero was skipped), when it ran,
           and its notes behind Notes (n). The notes were a list in a connection
           card, under the same sentence the tab row already said. */
        function reconSweepLine(st, xs) {
            if (!st || st.last_sync === undefined) return null;
            const line = el('div', 'recon-sweep');
            /* The band says a refusal once; the sweep's own note saying the
               same is left out while it stands. */
            const notes = (st.sweep_notes || []).filter(n => !(xs.needs_reconnect && /refused the refresh token/i.test(String(n))));
            const bad = notes.some(n => RECON_NOTE_BAD.test(String(n)));
            const partial = notes.some(n => /\bpartial\b/i.test(String(n)));
            line.append(el('span', 'dt-dot ' + (xs.needs_reconnect ? 'bad' : bad ? 'warn' : st.last_sync ? 'ok' : '')));
            line.append(el('span', null, [st.last_sync ? 'Last sweep ' + fmtDate(st.last_sync) + ', ' + londonHM(st.last_sync) : 'Never swept',
                xs.needs_reconnect ? 'Xero skipped' : partial ? 'Partial' : ''].filter(Boolean).join(' \u00b7 ')));
            if (notes.length) {
                const b = el('button', 'disc'); b.type = 'button';
                b.setAttribute('aria-haspopup', 'dialog');
                b.append(document.createTextNode('Notes'), el('span', 'disc-n', String(notes.length)), ico(I.chevDown));
                b.onclick = (ev) => {
                    ev.stopPropagation();
                    dropPanel(b, (p) => {
                        p.classList.add('ipop', 'recon-notes');
                        p.append(el('h3', null, 'Notes from the last sweep' + (st.last_sync ? ', ' + fmtDate(st.last_sync) : '')));
                        const ul = el('ul');
                        notes.forEach(n => {
                            const li = el('li');
                            li.append(el('span', 'dt-dot' + (RECON_NOTE_BAD.test(String(n)) ? ' warn' : '')), el('span', null, n));
                            ul.append(li);
                        });
                        p.append(ul);
                    });
                };
                line.append(b);
            }
            return line;
        }
        function renderRecon() {
            const box = $('recon-content');
            /* The search box being typed in is about to be rebuilt: keep its
               text and cursor as they are NOW, letters typed while the list
               was being fetched included. */
            const typing = document.activeElement;
            if (typing && box.contains(typing) && typing.matches('.tbl-search input')) {
                reconSearchKeep = { typed: typing.value, at: typing.selectionStart };
            }
            box.innerHTML = '';
            /* Set BEFORE anything is appended, so a severity click or a status
               change redraws the tiles in place instead of replaying half a
               second of entrance over counts that did not move. The loading and
               failure states return before a tile is built, so they must not
               spend the entrance the first real paint is owed. */
            const rPainting = !!reconCache && !reconCache.error;
            box.classList.toggle('no-intro', !(rPainting && firstPaint('recon')));
            const st = (rPainting && reconCache.st) || {};
            const xs = st.xero || {};
            const mb = st.mailbox || {};
            /* The page's actions are in its header (12 Oct 2026): Manage, then
               Sweep now, the one teal action while Xero and the mailbox need
               nothing. They sat in a connection card under the tabs. */
            const heads = [];
            const band = el('div', 'band');
            if (rPainting) {
                /* Disconnecting has to be possible, and has to mean it: the token
                   is revoked at the provider, not merely forgotten here. It lives
                   in a menu, because it is the rarest thing on the page and the
                   one that cannot be taken back. */
                let disconnecting = false;
                const disconnect = async (what) => {
                    if (disconnecting) return;
                    const msg = what === 'xero'
                        ? 'Disconnect Xero? The connection is revoked at Xero, and the cached '
                          + 'copy of your accounting records is deleted. Discrepancies already '
                          + 'found are kept as your audit trail.'
                        : 'Disconnect the accounts mailbox? The documents read from it are '
                          + 'deleted. Nothing in the mailbox itself is touched.';
                    if (!await uiConfirm(msg, { title: 'Disconnect', okText: 'Disconnect', danger: true })) return;
                    disconnecting = true;
                    const go = async (force) => {
                        const r = await api('/api/recon/disconnect', force ? { what, force: 1 } : { what });
                        (r.notes || []).forEach(n => addToast(n));
                        toastOk('Disconnected.');
                        refreshRecon();
                    };
                    try { await go(false); }
                    catch (e) {
                        if (!e.canForce) { toastError(e.message); disconnecting = false; return; }
                        /* Xero would not accept the revocation, so the token is
                           still live there. Forgetting it here would leave that
                           connection alive with no way left to end it, so this
                           asks rather than assumes. */
                        const ok2 = await uiConfirm(e.message + '\n\nForget the connection here anyway?',
                            { title: 'Could not revoke at Xero', okText: 'Forget it anyway', danger: true });
                        if (!ok2) { disconnecting = false; return; }
                        try { await go(true); }
                        catch (e2) { toastError(e2.message); }
                    }
                    disconnecting = false;
                };
                if (xs.connected || mb.connected) {
                    const manage = textButton(null);
                    manage.type = 'button';
                    /* Name first, caret last: the house menu trigger. */
                    manage.append(document.createTextNode('Manage'), ico(I.chevDown));
                    manage.onclick = () => dropMenu(manage, [
                        xs.connected && { label: 'Disconnect Xero', icon: I.x, onClick: () => disconnect('xero') },
                        mb.connected && { label: 'Disconnect the accounts mailbox', icon: I.x, onClick: () => disconnect('mailbox') },
                    ]);
                    heads.push(manage);
                }
                /* Teal only while nothing else needs doing first: a refused link
                   makes Reconnect the teal action, and a mailbox the master can
                   still connect makes that card's Connect it. A sweep then still
                   reads what it can, and skips the rest. */
                const swTeal = xs.connected && !xs.needs_reconnect && (mb.connected || !mb.can_connect);
                const sw = textButton(null, { kind: swTeal ? 'primary' : '' });
                sw.type = 'button';
                /* The busy word swaps in at the same width, keeping its icon. */
                const swIdle = el('span'), swBusy = el('span');
                swIdle.append(ico(I.refresh), document.createTextNode('Sweep now'));
                swBusy.append(ico(I.refresh), document.createTextNode('Sweeping\u2026'));
                const swSwap = el('span', 'swap'); swSwap.append(swIdle, swBusy); sw.append(swSwap);
                const swBusySet = (on) => { swIdle.setAttribute('aria-hidden', on ? 'true' : 'false'); swBusy.setAttribute('aria-hidden', on ? 'false' : 'true'); };
                swBusySet(!!st.sweeping);
                sw.disabled = !!st.sweeping || !xs.connected;
                if (!xs.connected) sw.title = 'Connect Xero first';
                sw.onclick = async () => { sw.disabled = true; swBusySet(true);
                    try { await api('/api/recon/sweep', {}); toastOk('Sweep finished.'); }
                    catch (e) { toastError(e.message); }
                    refreshRecon(); };
                heads.push(sw);
                /* A sweep started elsewhere (the nightly one, or another person)
                   is asked about until it ends, or "Sweeping..." would stay for good. */
                if (st.sweeping) watchReconSweep();
                /* With the link refused, Reconnect is the one teal action. Only
                   the master account may start the walk, as with Connect. */
                if (xs.needs_reconnect && (!teamMe || teamMe.role === 'master')) {
                    const rc = textButton(null, { kind: 'primary' });
                    rc.type = 'button';
                    rc.append(ico(I.logIn), document.createTextNode('Reconnect Xero'));
                    rc.onclick = async () => {
                        /* The tab opens inside the click, or the browser blocks it. */
                        const tab = window.open('', '_blank');
                        rc.disabled = true;
                        try {
                            const r = await api('/api/recon/xero-link', {});
                            if (tab) {
                                tab.location = r.url;
                                addToast('Approve the connection in the new tab, and pick the '
                                         + 'organisation. This page updates when it lands.', 'good');
                                watchReconXero(true);
                            } else {
                                reconConnectFallback(band, r.url, 'xero', true);
                            }
                        } catch (e) {
                            if (tab) tab.close();
                            toastError(e.message);
                        }
                        rc.disabled = false;
                    };
                    heads.push(rc);
                }
            }
            /* "Read only" is the safety point and stays in the line (copy plan,
               Reconciliation #1). */
            box.append(pageHead({ view: 'recon', title: 'Reconciliation', line: 'Checks Shopify, Xero and the inbox agree. Read only.', actions: heads }));
            box.append(financeTabs('recon', '', [reconSweepLine(st, xs)]));
            if (!reconCache) { box.append(el('div', 'empty', 'Loading\u2026')); return; }
            if (reconCache.error) { box.append(loadFailure('The reconciliation state could not be read. ' + reconCache.error, refreshRecon)); return; }
            /* ONE BAND (12 Oct 2026, Cameron's screenshot: four tiles with 291px
               of nothing in each, under a connection card). The open
               discrepancies by severity, each a counter that filters the list
               with the money at stake beside its figure, then after a hairline
               the sources the sweep reads. A refused link or an unsaved token is
               said once, under the band. It has a widget id of its own, so a
               layout that hid the old severity tiles or connection card does not
               hide it. */
            const bandRow = el('div', 'band-row');
            const counts = st.open_counts || {};
            const amounts = st.open_amounts || {};
            const mets = el('div', 'fcs recon-sev');
            [['critical', 'Critical', 'bad'], ['high', 'High', 'bad'],
             ['medium', 'Medium', 'warn'], ['low', 'Low', '']].forEach(([k, lab, tone]) => {
                mets.append(counterTile(lab, String(counts[k] || 0), { dot: tone, on: reconFilter.severity === k,
                    money: typeof amounts[k] === 'number' ? money(amounts[k] / 100, st.currency || 'GBP', 2) : '',
                    onClick: () => { reconFilter.severity = reconFilter.severity === k ? '' : k; refreshReconList(); } }));
            });
            const src = el('div', 'band-src');
            const srcLine = (dot, k, v, bad) => {
                const r = el('div', 'band-src-l');
                const kk = el('span', 'band-src-k' + (dot === null ? ' ind' : ''));
                if (dot !== null) kk.append(el('span', 'dt-dot ' + dot));
                kk.append(document.createTextNode(k));
                const vv = el('span', 'band-src-v' + (bad ? ' bad' : ''), v); vv.title = v;
                r.append(kk, vv); src.append(r);
            };
            /* A link Xero refused is connected in name only: red, and saying
               what it needs. */
            srcLine(xs.needs_reconnect ? 'bad' : xs.connected ? 'ok' : 'off', 'Xero',
                xs.needs_reconnect ? 'Needs reconnecting' : xs.connected ? (xs.tenant || 'Connected') : 'Not connected', !!xs.needs_reconnect);
            srcLine(mb.connected ? 'ok' : 'warn', 'Accounts mailbox', mb.connected ? (mb.address || 'Connected') : 'Not connected');
            if (mb.connected || st.docs) srcLine(null, 'Documents read', Number(st.docs || 0).toLocaleString('en-GB'));
            bandRow.append(mets, src);
            band.append(bandRow);
            /* A token that could not be saved is a connection with a fuse
               burning: Xero honours the previous one for about half an hour and
               then the link is gone. Anyone but the master is told who can mend
               a refused link. */
            const notice = (t) => { const n = el('p', 'band-notice'); n.append(el('span', 'dt-dot bad'), el('span', null, t)); band.append(n); };
            if (xs.needs_reconnect) {
                notice(['Xero refused the link, so its checks are skipped until it is reconnected.',
                        !teamMe || teamMe.role === 'master' ? '' : 'Ask the master account to reconnect Xero.'].filter(Boolean).join(' '));
            } else if (xs.warning) notice(xs.warning);
            box.append(widget(band, 'band', 'full', 'Open and sources'));
            /* The accounts mailbox: a SEPARATE Google account from the Inbox
               tab's, so the card names both to make a wrong consent obvious. */
            if (!mb.connected) {
                /* Built on the house card parts: a titled head, numbered steps,
                   one row holding the address and its button, and the help as
                   body copy. The address field sat as a flex child of the card
                   and grew to 160px tall, and the button stretched the full
                   width of the card. */
                const mc = el('div', 'card');
                const mh = el('div', 'card-head');
                /* The setup, word for word, behind the title's info button (the
                   mix, spec 8.3); the address to copy and the Connect action
                   stay on the card. */
                const mt = el('h3', 'card-title', 'Connect the accounts mailbox');
                const mtInfo = infoButton('Connecting the accounts mailbox', { title: 'Connect the accounts mailbox', body: [
                    'Reconciliation reads remittances, supplier invoices and statements from '
                    + 'the accounts mailbox. That is a different Google account from the one '
                    + 'behind the Inbox tab'
                    + (mb.sales_address ? ' (' + mb.sales_address + ')' : '')
                    + ', and it will not appear there.',
                    'Add this callback URL to your Google OAuth client, beside the one the Inbox tab '
                    + 'already uses (APIs and Services, Credentials, your OAuth client, Authorised '
                    + 'redirect URIs). Until it is there Google refuses the sign-in with "Access '
                    + 'blocked: this app\u2019s request is invalid".',
                    'The address is required: it is what makes Google open the right account '
                    + 'rather than the one this browser is already signed into.',
                    'If a different mailbox is connected anyway, nothing is saved and the page '
                    + 'says which one it got, so try again in a private window.'] });
                mh.append(titleInfo(mt, mtInfo));
                mc.append(mh);
                /* The step everyone trips on: Google answers an unregistered
                   callback with "Access blocked: This app's request is
                   invalid", which names nothing. So the URL is here, exact and
                   copyable, rather than described. */
                const steps = el('ol', 'setup-steps');
                const s1 = el('li');
                s1.append(document.createTextNode('Add this callback URL to your Google OAuth client.'));
                const uriRow = el('div', 'act-row');
                uriRow.append(el('code', 'setup-code', mb.redirect_uri || ''));
                const cp = textButton(null);
                cp.append(ico(I.copy), document.createTextNode('Copy'));
                cp.onclick = async () => {
                    try { await navigator.clipboard.writeText(mb.redirect_uri || '');
                          toastOk('Callback URL copied.'); }
                    catch (e) { toastError('Select the URL above and copy it.'); }
                };
                uriRow.append(cp);
                const proj = mb.project ? '?project=' + encodeURIComponent(mb.project) : '';
                const ca = el('a', 'action-link', 'Open your OAuth clients in the Google console');
                ca.href = 'https://console.cloud.google.com/auth/clients' + proj;
                ca.target = '_blank'; ca.rel = 'noopener';
                uriRow.append(ca);
                s1.append(uriRow);
                steps.append(s1);
                mc.append(steps);
                if (mb.can_connect) {
                    /* Naming the mailbox does two jobs: Google opens THAT
                       account instead of whichever one this browser is signed
                       into, and the callback can check it got what was asked
                       for rather than accepting whatever turns up. */
                    const s2 = el('li');
                    s2.append(document.createTextNode('Type the accounts mailbox address, then connect.'));
                    const row = el('div', 'act-row');
                    const who = el('input', 'field-sm setup-field');
                    who.placeholder = 'accounts@yourdomain.com'; who.type = 'email'; who.setAttribute('aria-label', 'Accounts mailbox address'); who.spellcheck = false;
                    who.value = mb.last_try || '';
                    /* Teal while Xero needs nothing, so Sweep now steps down for it;
                       Connect Xero or Reconnect is the teal action while Xero does. */
                    const go = textButton(null, { kind: xs.connected && !xs.needs_reconnect ? 'primary' : '' });
                    go.append(ico(I.mail), document.createTextNode('Connect the accounts mailbox'));
                    go.onclick = async () => {
                        /* The tab is opened SYNCHRONOUSLY, inside the click, and
                           pointed at the URL afterwards. Opening it after the
                           await loses the user gesture and the browser blocks
                           it - which inside Shopify's iframe means the button
                           appears to do nothing at all. */
                        if (!who.value.trim()) {
                            who.focus();
                            toastError('Type the accounts mailbox address first: without it '
                                       + 'Google opens whichever account you are already '
                                       + 'signed into.');
                            return;
                        }
                        const tab = window.open('', '_blank');
                        go.disabled = true;
                        try {
                            const r = await api('/api/recon/connect-link',
                                                { address: who.value.trim() });
                            if (tab) {
                                tab.location = r.url;
                                addToast('Sign in as the accounts mailbox in the new tab. '
                                         + 'This card updates itself when it lands.', 'good');
                                watchReconMailbox();
                                /* Google can still consent as whoever the browser
                                   is signed in as: a hint is a hint. A private
                                   window has no session to hijack the walk, so
                                   the link is always offered as the way out. */
                                reconPrivateLink(mc, location.origin + r.url);
                            } else {
                                /* Pop-ups blocked: give them something to click,
                                   rather than a cheerful message about a tab
                                   that never opened. */
                                reconConnectFallback(mc, r.url, 'mailbox');
                            }
                        } catch (e) {
                            if (tab) tab.close();
                            toastError(e.message);
                        }
                        go.disabled = false;
                    };
                    row.append(who, go);
                    s2.append(row);
                    steps.append(s2);
                } else {
                    mc.append(el('p', 'card-sub', 'Ask the master account to connect it.'));
                }
                box.append(widget(mc, 'mailbox', 'full', 'Connect the accounts mailbox'));
            }
            /* Setup, master only, until Xero is connected */
            if (!xs.connected && st.setup && st.setup.env_needed) {
                const su = el('div', 'card');
                const sh = el('div', 'card-head');
                /* The security point stays as the card's line; the setup is the
                   title's info button, word for word (copy plan, Reconciliation #8). */
                const xt = el('h3', 'card-title', 'Connect Xero');
                sh.append(xt);
                sh.append(el('p', 'card-desc', 'Read only: Reactor cannot change your books.'));
                su.append(sh);
                /* Built as nodes, not innerHTML: the redirect URI is server
                   data and goes in as TEXT, whatever it contains. */
                const steps = el('ol', 'setup-steps');
                const step = (before, strong, after, code) => {
                    const li = el('li');
                    li.append(document.createTextNode(before));
                    if (strong) li.append(el(code ? 'code' : 'b', code ? 'setup-code' : null, strong));
                    if (after) li.append(document.createTextNode(after));
                    steps.append(li); return li;
                };
                step('Create a free app at ', 'developer.xero.com', ' (My Apps, New app, Web app).');
                step('Set its redirect URI to exactly ', st.setup.redirect_uri || '', '.', true);
                const s3 = step('Put the Client ID and Client Secret into the Railway variables ',
                    'XERO_CLIENT_ID and XERO_CLIENT_SECRET', ' (never anywhere else), then redeploy.');
                if (!st.setup.configured) s3.append(document.createTextNode(
                    ' The Connect button appears here once the server has them.'));
                titleInfo(xt, infoButton('Setting up Xero', { title: 'Connect Xero', body: ['A one-time setup of about five minutes. Xero is connected '
                    + 'read-only: the app can read the books and has no way to change them.', steps] }));
                /* The address to type in Xero stays on the card, beside a Copy. */
                if (st.setup.redirect_uri) {
                    const ur = el('div', 'act-row');
                    ur.append(el('code', 'setup-code', st.setup.redirect_uri));
                    const ucp = textButton(null); ucp.type = 'button';
                    ucp.append(ico(I.copy), document.createTextNode('Copy'));
                    ucp.onclick = async () => {
                        try { await navigator.clipboard.writeText(st.setup.redirect_uri); toastOk('Redirect URI copied.'); }
                        catch (e) { toastError('Select the address above and copy it.'); }
                    };
                    ur.append(ucp); su.append(ur);
                }
                if ((st.setup.scopes || []).length) {
                    /* Xero refuses the WHOLE authorization if the app was not
                       assigned one of these, and never says which. Showing
                       them makes the comparison against the Xero app's own
                       page possible instead of guesswork. */
                    const sc = el('details', 'know-body');
                    sc.append(el('summary', null, 'Permissions this will ask Xero for'));
                    const list = el('ul', 'setup-scopes');
                    st.setup.scopes.forEach(x => { const li = el('li'); li.append(el('code', 'setup-code', x)); list.append(li); });
                    sc.append(list);
                    sc.append(el('p', 'card-sub',
                        'If Xero answers "invalid scope", it was assigned a different set: '
                        + 'compare this list with the permissions shown on the app in the '
                        + 'Xero developer portal.'));
                    su.append(sc);
                }
                if (st.setup.configured) {
                    /* Same shape as the mailbox button: the tab opens inside the
                       click, or the browser blocks it. */
                    const xrow = el('div', 'act-row');
                    const xgo = textButton(null, { kind: 'primary' });
                    xgo.append(ico(I.link || I.check), document.createTextNode('Connect Xero'));
                    xgo.onclick = async () => {
                        const tab = window.open('', '_blank');
                        xgo.disabled = true;
                        try {
                            const r = await api('/api/recon/xero-link', {});
                            if (tab) {
                                tab.location = r.url;
                                addToast('Approve the connection in the new tab, and pick the '
                                         + 'organisation. This card updates when it lands.', 'good');
                                watchReconXero();
                            } else {
                                reconConnectFallback(su, r.url, 'xero');
                            }
                        } catch (e) {
                            if (tab) tab.close();
                            toastError(e.message);
                        }
                        xgo.disabled = false;
                    };
                    xrow.append(xgo);
                    xrow.append(el('span', 'card-sub', 'Sign in as the organisation and approve.'));
                    su.append(xrow);
                }
                box.append(widget(su, 'xero-setup', 'full', 'Connect Xero'));
            }
            /* The discrepancies (12 Oct 2026): a counted title, the search, the
               status and the export on a toolbar, and one table under heads.
               The filters render even when the list is empty, or a filter that
               hides everything also hides the way to undo it. */
            const ex = (reconCache.ex || {}).exceptions || [];
            const list = el('div', 'card');
            const rHead = el('div', 'card-head');
            const exOpen = ex.filter(e => RECON_OPEN[e.status]).length;
            const rTitle = el('h3', 'card-title', 'Discrepancies');
            if (ex.length) rTitle.append(el('span', 'card-n', ex.length + (exOpen < ex.length ? ' \u00b7 ' + exOpen + ' open' : '')));
            rHead.append(rTitle);
            /* On the toolbar, not in the card header: the same class of
               control sits on the toolbar one tab away. */
            const exp = textButton(null); exp.append(ico(I.download), document.createTextNode('Export CSV'));
            exp.onclick = reconCSV;
            list.append(rHead);
            /* Filters as you type, so its clear button clears the list too
               (with onchange alone the box emptied and the list stayed
               filtered). The page redraws whole, so the box gets back its
               text and cursor, as the Production Manager's search does. */
            const searchWrap = tableSearch('Search discrepancies', reconFilter.q, (v) => {
                reconFilter.q = v; refreshReconList();
            });
            /* This search rebuilds its own box, so a word still being composed
               (Japanese or Chinese input) waits until it is finished; the
               other searches keep filtering as each letter lands. */
            const baseInput = searchWrap.input.oninput;
            searchWrap.input.oninput = (e) => { if (e && e.isComposing) return; baseInput(); };
            searchWrap.input.addEventListener('compositionend', () => baseInput());
            /* The Liability tab's filter chip. The first option is labelled for
               what the server actually does with an empty status, which is not
               to filter by status at all. */
            const statusChip = filterChip('Status', [['', 'All statuses']].concat(
                ['new', 'investigating', 'explained', 'confirmed_error', 'corrected', 'ignored']
                    .map(k => [k, RECON_STATUS[k]])),
                reconFilter.status, v => { reconFilter.status = v; refreshReconList(); });
            /* The chosen severity also shows on the toolbar, with its X, beside
               the filters that are said there. */
            let sevTag = null;
            if (reconFilter.severity) {
                sevTag = textButton(null); sevTag.type = 'button';
                const sevWord = (RECON_SEV[reconFilter.severity] || [reconFilter.severity])[0];
                sevTag.append(document.createTextNode(sevWord), ico(I.x));
                sevTag.setAttribute('aria-label', 'Show every severity, not only ' + sevWord);
                sevTag.onclick = () => { reconFilter.severity = ''; refreshReconList(); };
            }
            list.append(tableTools([searchWrap, statusChip].concat(sevTag ? [sevTag] : []), [exp]));
            box.append(widget(list, 'discrepancies', 'full', 'Discrepancies'));
            /* Back into the new box at once, in the same task as the redraw,
               so no key pressed meanwhile lands on the page instead. */
            if (reconSearchKeep) {
                const k = reconSearchKeep; reconSearchKeep = null;
                const inp = searchWrap.input;
                inp.value = k.typed;
                /* In a microtask: after the rows are back, so focusing does not
                   lay out a half-built page and scroll it (the box jumped from
                   the top to under a phone's keyboard), yet before any key
                   event, so no keystroke lands on the page. */
                queueMicrotask(() => { if (inp.isConnected) { inp.focus(); try { inp.setSelectionRange(k.at, k.at); } catch (e) {} } });
                /* Typed on while the last list was on its way: search for that too. */
                if (k.typed.trim() !== reconFilter.q) { reconFilter.q = k.typed.trim(); refreshReconList(); }
            }
            if (!ex.length) {
                /* Filters that hide everything are not an all clear: with
                   21 open the page said "Nothing needs attention." */
                if (reconFilter.severity || reconFilter.status || reconFilter.q) {
                    const clr = textButton('Clear filters'); clr.type = 'button';
                    clr.onclick = () => {
                        /* The box too: a redraw keeps what is typed in a focused
                           box, and would put the search straight back. */
                        searchWrap.input.value = '';
                        reconFilter = { severity: '', status: '', q: '' }; refreshReconList();
                    };
                    list.append(emptyState({ icon: I.search, text: 'Nothing matches these filters.', action: clr }));
                } else {
                    list.append(xs.connected ? emptyState({ icon: I.check, text: 'Nothing needs attention.' })
                        : emptyState({ icon: I.logIn, text: 'Connect Xero above, then run the first sweep.' }));
                }
                if (reconOpen) { const orphan = el('div', 'rd-orphan'); orphan.append(reconDetailNode()); list.append(orphan); }
                return;
            }
            /* One row per discrepancy (12 Oct 2026, Cameron's screenshot: each
               a sentence at the far left and its amount 1,022px away): the
               severity, a short What with its tags, the record and who it is
               with, the date, a status tag for every status but New, and the
               amount, each under its head. A settled one goes grey with a
               hollow dot. Click to open, click again to close; the detail opens
               under its row. */
            list.append(dtable([{ head: 'Severity' }, { head: 'What' }, { head: 'Record' }, { head: 'Date' }, { head: 'Status' }, { head: 'Amount', cls: 'num' }, { head: '', cls: 'act go' }],
                ex.map(e => {
                    const open = !!(reconOpen && reconOpen.id === e.id);
                    const toggle = () => { if (open) { reconOpen = null; renderRecon(); } else openReconExc(e.id); };
                    const [lab, tone] = RECON_SEV[e.severity] || ['?', 'note'];
                    const sev = el('span', 'dt-sev');
                    sev.append(el('span', 'dt-dot ' + (RECON_OPEN[e.status] ? (tone === 'note' ? '' : tone) : 'off')), document.createTextNode(lab));
                    /* The What is the button a keyboard reaches; the sentence it
                       stands for is its title, and heads the detail. */
                    const what = el('button', 'dt-link dt-what', RECON_WHAT[e.kind] || e.title); what.type = 'button';
                    what.title = e.title || ''; what.setAttribute('aria-expanded', String(open));
                    what.onclick = (ev) => { ev.stopPropagation(); toggle(); };
                    const whatCell = document.createDocumentFragment(); whatCell.append(what);
                    if (e.has_ai) whatCell.append(el('span', 'lbl-chip note', 'AI verdict'));
                    if (e.basis === 'ai_extraction') whatCell.append(el('span', 'lbl-chip warn', RECON_AI_SCAN));
                    if (e.stale) whatCell.append(el('span', 'lbl-chip note', 'No longer detected'));
                    const rec = el('span', 'dt-name', e.record || '');
                    if (e.counterparty) rec.append(el('span', 'dt-muted', e.counterparty));
                    rec.title = [e.record, e.counterparty].filter(Boolean).join(' \u00b7 ');
                    const go = el('span', 'prod-go'); go.innerHTML = open ? I.chevDown : I.chevLeft; go.setAttribute('aria-hidden', 'true');
                    return { cls: RECON_OPEN[e.status] ? '' : 'settled', open, onClick: toggle,
                             cells: [sev, whatCell, rec, fmtDate(e.date), e.status !== 'new' ? el('span', 'lbl-chip note', reconStatusWord(e.status)) : '',
                                     el('span', 'dt-amt', reconMoney(e.amount_disp)), go],
                             after: reconOpen && reconOpen.id === e.id ? reconDetailNode() : null };
                }),
                { cls: 'dt-recon', label: 'Discrepancies', main: 1 }));
            /* An open discrepancy the current filters no longer list still has
               to be readable: it goes under the table rather than vanishing
               with its row. */
            if (reconOpen && !ex.some(e => e.id === reconOpen.id)) { const orphan = el('div', 'rd-orphan'); orphan.append(reconDetailNode()); list.append(orphan); }
        }
        function reconPrivateLink(card, absUrl) {
            if (card.querySelector('.recon-priv')) return;
            const row = el('div', 'recon-priv');
            row.append(el('p', 'card-sub',
                'Still landing on the wrong mailbox? Google consents as whichever account '
                + 'the browser is signed into, whatever it is asked for. Open this in a '
                + 'private window, where there is no session to get in the way.'));
            const line = el('div', 'act-row');
            line.append(el('code', 'setup-code', absUrl));
            const copy = textButton(null);
            copy.append(ico(I.copy), document.createTextNode('Copy link'));
            copy.onclick = async () => {
                try { await navigator.clipboard.writeText(absUrl); toastOk('Link copied.'); }
                catch (e) { toastError('Select the link above and copy it.'); }
            };
            line.append(copy); row.append(line);
            card.append(row);
        }
        function reconConnectFallback(card, url, what, reconnect) {
            /* A real link, which carries the click through a pop-up blocker.
               Named for the sign-in it opens (Xero's said Google and watched
               the mailbox), and one per card however often it is pressed. */
            const old = card.querySelector('.recon-fallback'); if (old) old.remove();
            const row = el('p', 'card-sub recon-fallback');
            row.append(document.createTextNode('Your browser blocked the new tab. '));
            const xero = what === 'xero';
            const a2 = el('a', 'action-link', xero ? 'Open the Xero sign-in here' : 'Open the Google sign-in here');
            a2.href = url; a2.target = '_blank'; a2.rel = 'noopener';
            a2.onclick = () => (xero ? watchReconXero(reconnect) : watchReconMailbox());
            row.append(a2);
            row.append(document.createTextNode(' (the link works once, for five minutes).'));
            card.append(row);
        }
        let reconXeroWatch = null;
        /* A sweep the page did not start (the nightly one, or another
           person's) is asked about every five seconds until it ends, for ten
           minutes at most, and only while Reconciliation is on screen. */
        let reconSweepWatch = null;
        function watchReconSweep() {
            if (reconSweepWatch) return;
            let tries = 0;
            reconSweepWatch = setInterval(async () => {
                tries++;
                let st = null;
                try { st = await api('/api/recon/status', {}); } catch (e) { /* a blip: ask again */ }
                const here = !!document.querySelector('#view-recon.active');
                if ((st && !st.sweeping) || tries >= 120 || !here) {
                    clearInterval(reconSweepWatch); reconSweepWatch = null;
                    if (st && !st.sweeping && here) refreshRecon();
                }
            }, 5000);
        }
        function watchReconXero(reconnect) {
            if (reconXeroWatch) clearInterval(reconXeroWatch);
            let tries = 0;
            reconXeroWatch = setInterval(async () => {
                tries++;
                try {
                    const st = await api('/api/recon/status', {});
                    /* Good, not merely present: a refused link is connected in
                       name until the new consent lands. */
                    if (st.xero && st.xero.connected && !st.xero.needs_reconnect) {
                        clearInterval(reconXeroWatch); reconXeroWatch = null;
                        toastOk('Xero connected: ' + (st.xero.tenant || ''));
                        refreshRecon();
                        return;
                    }
                } catch (e) { /* the approval tab may still be open */ }
                if (tries >= 40) {
                    clearInterval(reconXeroWatch); reconXeroWatch = null;
                    toastError(reconnect
                        ? 'Xero has not been reconnected yet. If Xero showed an error, press Reconnect Xero again.'
                        : 'Xero is still not connected. If Xero showed an error it is '
                          + 'usually the redirect URI not matching the one registered '
                          + 'on the app.');
                }
            }, 3000);
        }
        let reconWatch = null;
        function watchReconMailbox() {
            /* "Come back and refresh" is a poor instruction, and an easy one to
               follow while nothing happens. Watch instead, and say something
               either way rather than leaving a cheerful message on screen. */
            if (reconWatch) clearInterval(reconWatch);
            let tries = 0;
            reconWatch = setInterval(async () => {
                tries++;
                try {
                    const st = await api('/api/recon/status', {});
                    if (st.mailbox && st.mailbox.connected) {
                        clearInterval(reconWatch); reconWatch = null;
                        toastOk('Accounts mailbox connected: ' + (st.mailbox.address || ''));
                        refreshRecon();
                        return;
                    }
                } catch (e) { /* keep watching; the sign-in tab may still be open */ }
                if (tries >= 40) {
                    clearInterval(reconWatch); reconWatch = null;
                    toastError('The accounts mailbox is still not connected. If Google showed an '
                               + 'error, it is almost always the callback URL missing from the '
                               + 'OAuth client.');
                }
            }, 3000);
        }
        async function reconCSV() {
            /* The export is a report: it fetches everything matching the
               filters, not just the rows the list happens to show. */
            let ex = ((reconCache || {}).ex || {}).exceptions || [];
            try { ex = (await api('/api/recon/exceptions',
                Object.assign({}, reconFilter, { limit: 5000 }))).exceptions || ex; } catch (e) {}
            const esc2 = (v) => { v = (v == null ? '' : String(v)); if (/^[=+\-@\t\r]/.test(v)) v = "'" + v; return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
            const rows = [['Severity', 'Title', 'Amount', 'Date', 'Systems', 'Status', 'Id'].join(',')];
            ex.forEach(e => rows.push([e.severity, e.title, e.amount_disp, e.date,
                (e.systems || []).join(' + '), e.status, e.id].map(esc2).join(',')));
            const blob = new Blob([rows.join('\r\n')], { type: 'text/csv' });
            const aEl = document.createElement('a'); aEl.href = URL.createObjectURL(blob);
            aEl.download = 'reconciliation.csv'; aEl.click(); URL.revokeObjectURL(aEl.href);
        }
        async function openReconExc(id) {
            try {
                const d = await api('/api/recon/exception', { id });
                reconOpen = d.exception; renderRecon();
                /* No scroll: the detail now opens directly under the row that
                   was clicked, so the row stays where the cursor left it. */
            } catch (e) { toastError(e.message); }
        }
        const RECON_AI_SCAN = 'AI-read scan, not verified';
        /* A record from Shopify, Xero or the inbox, as label and value pairs
           rather than a JSON dump with its braces and quoted keys. */
        const reconKey = (k) => cap(String(k).replace(/_/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase());
        function reconValue(k, v) {
            if (v == null || v === '') return '';
            /* A record inside a record (an order's refunds) is money in pence
               and a date, said as such; it printed as JSON with the raw pence. */
            const rec = (x) => (x && x.pence != null && /^-?\d+$/.test(String(x.pence)))
                ? money(Number(x.pence) / 100, 'GBP', 2) + (x.created_at ? ' on ' + fmtDate(x.created_at) : '')
                : JSON.stringify(x);
            if (typeof v === 'object') return Array.isArray(v) ? v.map(x => typeof x === 'object' ? rec(x) : String(x)).join(', ') : rec(v);
            const key = String(k).toLowerCase(), str = String(v);
            if (/^-?\d+(\.\d+)?$/.test(str)) {
                /* Every amount the sweep keeps is integer pence (recon.py:
                   total, tax, remaining, pence and the _pence fields), so
                   any money field is pence here: total and tax printed as
                   pounds showed a £3,960.00 order as £396,000.00. */
                if (/pence|amount|total|price|paid|due|fee|tax|net|gross|value|balance|outstanding|credit|debit|remaining/.test(key)) return money(Number(str) / 100, 'GBP', 2);
                return str;
            }
            if (/^\d{4}-\d{2}-\d{2}(T|$)/.test(str)) return fmtDate(str);
            return str;
        }
        /* "£3960.00 (Shopify) - £3300.00 (Xero) = £660.00", or the same with
           "VAT: " in front: the two sides and their difference, set as a sum. */
        const RECON_SUM = /^(?:([A-Za-z ]+): )?(-?\S+) \(([^)]+)\) - (-?\S+) \(([^)]+)\) = (-?\S+)$/;
        function reconDetailNode() {
            const host = el('div', 'rd-host');
            paintReconDetail(host);
            return host;
        }
        /* The evidence side by side (12 Oct 2026): a column per record, a row
           per field, the fields the records share first and the values that
           differ in red; Every field opens the rest. More than three records (a
           bill and its payments) stay a list, one record each. */
        function reconEvidence(evs, head) {
            const recs = evs.map(v => v.record && typeof v.record === 'object' ? v.record : { value: v.record });
            if (evs.length > 3) {
                const lst = el('div', 'rd-evlist');
                evs.forEach((v, i) => {
                    const evc = el('details', 'know-body');
                    const sm = el('summary');
                    /* The id stays, quietly: the AI's citations refer to it. */
                    sm.append(el('span', 'ev-id', v.eid), document.createTextNode(cap(v.system) + ' \u00b7 ' + v.label));
                    const dl = el('dl', 'conn-pairs');
                    Object.keys(recs[i]).forEach(k => {
                        const val = reconValue(k, recs[i][k]);
                        if (val === '') return;
                        dl.append(el('dt', null, reconKey(k)), el('dd', null, val));
                    });
                    evc.append(sm, dl); lst.append(evc);
                });
                return lst;
            }
            const keys = [];
            recs.forEach(r => Object.keys(r).forEach(k => { if (keys.indexOf(k) < 0 && reconValue(k, r[k]) !== '') keys.push(k); }));
            const shared = keys.filter(k => recs.filter(r => reconValue(k, r[k]) !== '').length > 1);
            const first = recs.length > 1 && shared.length ? shared : keys.slice(0, 6);
            const evName = (v) => v.eid + ' \u00b7 ' + cap(v.system) + ' ' + v.label;
            /* One record is named in a caption over its fields; two or three
               head a column each. */
            const kt = dataTable([null].concat(evs.map(evName)), { cls: 'rd-ev', head: evs.length > 1 });
            const wrap = kt.wrap;
            if (evs.length === 1) wrap.prepend(el('p', 'rd-evname', evName(evs[0])));
            const paint = (all) => {
                kt.body.innerHTML = '';
                (all ? keys : first).forEach(k => {
                    const vals = recs.map(r => reconValue(k, r[k]));
                    const got = vals.filter(v => v !== '');
                    const differ = got.length > 1 && got.some(v => v !== got[0]);
                    const tr = el('tr'); tr.append(el('td', 'rd-k', reconKey(k)));
                    vals.forEach(v => tr.append(el('td', differ && v !== '' ? 'rd-diff' : null, v)));
                    kt.add(tr);
                });
            };
            paint(false);
            if (keys.length > first.length) {
                const more = el('button', 'disc'); more.type = 'button'; more.setAttribute('aria-expanded', 'false');
                more.append(document.createTextNode('Every field'), ico(I.chevDown));
                more.onclick = () => { const on = more.getAttribute('aria-expanded') !== 'true'; more.setAttribute('aria-expanded', String(on)); paint(on); };
                head.append(more);
            }
            return wrap;
        }
        /* An opened discrepancy (12 Oct 2026, the mockup): one line across it,
           the server's sentence and the X that closes it, then two columns:
           what it is and what to do about it on the left (why, what to do, the
           arithmetic, the status and its history), and what it rests on at
           the right (the evidence side by side, and the AI's reading of it).
           The disclaimers and the model's name wait behind (i) buttons. */
        function paintReconDetail(box) {
            const e = reconOpen; if (!e) return;
            const d = el('div', 'rd'); d.id = 'recon-detail';
            const lead = el('div', 'rd-lead');
            lead.append(el('span', 'rd-title', e.title || ''));
            if (e.basis === 'ai_extraction') lead.append(el('span', 'lbl-chip warn', RECON_AI_SCAN));
            const x = iconButton(I.x, 'Close');
            x.onclick = (ev) => { ev.stopPropagation(); reconOpen = null; renderRecon(); };
            lead.append(x); d.append(lead);
            const cols = el('div', 'rd-cols');
            const left = el('div', 'rd-col'), right = el('div', 'rd-col');
            cols.append(left, right); d.append(cols);
            let at = left;
            const h = (t) => { const hh = el('div', 'rd-h', t); at.append(hh); return hh; };
            const p = (t, cls) => { const pp = el('p', 'rd-p' + (cls ? ' ' + cls : ''), t); at.append(pp); return pp; };
            const facts = el('dl', 'rd-facts');
            facts.append(el('dt', null, 'Why'), el('dd', null, e.why || ''));
            if (e.suggestion) facts.append(el('dt', null, 'What to do'), el('dd', null, e.suggestion));
            left.append(facts);
            if ((e.computed || []).length) {
                const arH = h('The arithmetic');
                arH.append(infoButton('How this is worked out', { title: 'The arithmetic', body: 'Worked out from the records, deterministic, not AI.' }));
                (e.computed || []).forEach(c => {
                    const m = RECON_SUM.exec(String(c));
                    if (!m) { p(c, 'fig'); return; }
                    const sum = el('dl', 'rd-sum');
                    const line = (k, v, cls) => { const r = el('div', cls || null); r.append(el('dt', null, k), el('dd', null, reconMoney(v))); sum.append(r); };
                    line(m[3] + (m[1] ? ' ' + m[1] : ''), m[2]);
                    line(m[5] + (m[1] ? ' ' + m[1] : ''), m[4]);
                    line('Difference', m[6], 'tot');
                    at.append(sum);
                });
            }
            h('Status');
            /* The house chooser: Ignore stays marked while its reason is asked for. */
            const stbar = segmented(['investigating', 'explained', 'confirmed_error', 'corrected', 'ignored']
                .map(k => [k, k === 'ignored' ? 'Ignore\u2026' : RECON_STATUS[k]]), e.status, async (k) => {
                if (k === e.status) return;
                if (k === 'ignored') {
                    /* Native dialogs no longer exist inside a cross-origin
                       iframe, which is exactly where this app lives. An inline
                       field, reason still required. */
                    reasonRow.hidden = false;
                    reasonIn.focus();
                    return;
                }
                try { const r = await api('/api/recon/exception', { id: e.id, op: 'status', status: k, note: '' });
                    reconOpen = r.exception; refreshRecon(); }
                catch (er) { toastError(er.message); }
            }, { label: 'Status' });
            left.append(stbar);
            const reasonRow = el('div', 'rd-row'); reasonRow.hidden = true;
            const reasonIn = el('input', 'field-sm rd-reason');
            reasonIn.type = 'text';
            reasonIn.placeholder = 'Why is this being ignored? (required)'; reasonIn.setAttribute('aria-label', 'Reason for ignoring');
            const reasonErr = el('p', 'rd-err', 'Say why it is being ignored.'); reasonErr.hidden = true; reasonErr.id = 'rd-reason-err';
            const reasonGo = textButton('Ignore with this reason'); reasonGo.type = 'button';
            reasonGo.onclick = async () => {
                if (!reasonIn.value.trim()) { markInvalid(reasonIn, true); reasonIn.setAttribute('aria-describedby', reasonErr.id); reasonErr.hidden = false; reasonIn.focus(); return; }
                markInvalid(reasonIn, false); reasonErr.hidden = true;
                try { const r = await api('/api/recon/exception',
                        { id: e.id, op: 'status', status: 'ignored', note: reasonIn.value.trim() });
                    reasonRow.hidden = true; reconOpen = r.exception; refreshRecon(); }
                catch (er) { toastError(er.message); }
            };
            reasonRow.append(reasonIn, reasonGo);
            left.append(reasonRow, reasonErr);
            (e.history || []).forEach(hh => {
                const hl = el('p', 'rd-hist');
                hl.append(el('span', null, fmtDate(hh.at) + ', ' + londonHM(hh.at) + ' \u00b7 ' + hh.by + ' \u00b7 '),
                    document.createTextNode(reconStatusWord(hh.from) + ' \u2192 ' + reconStatusWord(hh.to) + (hh.note ? ' \u00b7 ' + hh.note : '')));
                left.append(hl);
            });
            at = right;
            if ((e.evidence || []).length) {
                const evH = h('Evidence');
                evH.append(el('span', 'rd-n', String(e.evidence.length)));
                right.append(reconEvidence(e.evidence, evH));
            }
            const aiH = h('AI interpretation');
            if (e.ai) {
                const conf = Math.max(0, Math.min(100, e.ai.confidence || 0));
                aiH.append(infoButton('What the AI may and may not do', { title: 'AI interpretation', body: [
                    'This is the model\u2019s interpretation of the evidence above, not an accounting fact.',
                    'Model: ' + (e.ai.model || 'unknown')] }));
                const v = el('div', 'rd-verdict');
                v.append(el('span', 'lbl-chip ' + (e.ai.classification === 'genuine_error' ? 'bad' : 'note'),
                    cap(String(e.ai.classification || '').replace(/_/g, ' '))));
                const meter = el('span', 'rd-meter'); meter.setAttribute('aria-hidden', 'true');
                const fill = el('i'); fill.style.width = conf + '%'; meter.append(fill);
                v.append(meter, el('span', 'fig', conf + '% confident'));
                if ((e.ai.cites || []).length) v.append(el('span', 'rd-muted', 'Cites ' + e.ai.cites.join(', ')));
                right.append(v);
                p(e.ai.explanation || '');
                if (e.ai.recommended_action) { const rp = p(''); rp.append(el('b', null, 'Recommended: '), document.createTextNode(e.ai.recommended_action)); }
            } else {
                aiH.append(infoButton('What the AI may and may not do', { title: 'AI interpretation', body:
                    'The AI reads only the evidence shown, must cite what it relies on, and its answer is recorded as interpretation, never as fact.' }));
                const inv = textButton(null); inv.type = 'button';
                const invIdle = el('span'), invBusy = el('span');
                invIdle.append(ico(I.spark), document.createTextNode('Investigate with AI'));
                invBusy.append(ico(I.spark), document.createTextNode('Investigating\u2026'));
                invBusy.setAttribute('aria-hidden', 'true');
                const invSwap = el('span', 'swap'); invSwap.append(invIdle, invBusy); inv.append(invSwap);
                inv.onclick = async () => { inv.disabled = true; invIdle.setAttribute('aria-hidden', 'true'); invBusy.setAttribute('aria-hidden', 'false');
                    try { const r = await api('/api/recon/exception', { id: e.id, op: 'investigate' }); reconOpen = r.exception; renderRecon(); }
                    catch (er) { toastError(er.message); inv.disabled = false; invIdle.setAttribute('aria-hidden', 'false'); invBusy.setAttribute('aria-hidden', 'true'); } };
                right.append(inv);
            }
            box.append(d);
        }

