        /* ==================================================================
           Filters: standing decisions about mail that arrives. Gmail's own
           shape, because that is what people already know, with this app's
           actions: hand it to someone, or close it on arrival.
           ================================================================== */
        const MAIL_FIELDS = [['from', 'Sender'], ['domain', 'Sender domain'],
                             ['subject', 'Subject'], ['text', 'Subject or preview text']];
        const MAIL_OPS = [['contains', 'contains'], ['not_contains', 'does not contain'],
                          ['is', 'is exactly'], ['starts', 'starts with']];
        async function openMailRules() {
            let data;
            try { data = await api('/api/mail/rules', { op: 'list' }); }
            catch (e) { toastError(e.message); return; }
            const m = mailModal('Filters');
            m.overlay.querySelector('.modal').classList.add('smodal');
            paintMailRules(m, data);
        }
        function paintMailRules(m, data) {
            const lead = data.lead;
            m.body.innerHTML = '';
            /* How filters work, word for word, behind the window title's info
               button (copy plan, Other dialogs #27). */
            const fh = m.overlay.querySelector('.modal-head h3');
            if (fh && !fh.parentNode.classList.contains('title-row')) titleInfo(fh, infoButton('About filters', { title: 'Filters', body:
                'Filters act on email as it arrives. A conversation someone is already '
                + 'holding is never re-filed underneath them. The first filter that '
                + 'matches wins, so the order here is the order they are tried.' }));
            const reload = async (r) => {
                if (r && r.rules) { paintMailRules(m, { rules: r.rules, lead: lead }); }
                refreshMailQuiet();
            };
            const call = async (payload) => {
                try { return await api('/api/mail/rules', payload); }
                catch (e) { toastError(e.message); return null; }
            };
            const list = el('div');
            list.style.margin = 'var(--sp-3) 0';
            (data.rules || []).forEach((r, i) => {
                const row = el('div', 'mrule');
                const head = el('div', 'mrule-head');
                head.append(el('span', 'mrule-name' + (r.enabled === false ? ' off' : ''), r.name));
                const bits = r.conditions.map(c =>
                    (MAIL_FIELDS.find(f => f[0] === c.field) || [0, c.field])[1] + ' '
                    + (MAIL_OPS.find(o => o[0] === c.op) || [0, c.op])[1] + ' "' + c.value + '"');
                head.append(el('span', 'mrule-when',
                    bits.join(r.mode === 'any' ? '  or  ' : '  and  ')));
                row.append(head);
                const acts = [];
                if (r.assign === '_round') acts.push('share out between '
                    + (r.pool || []).map(u => teamNameOf(u) || '?').join(', '));
                else if (r.assign) acts.push('give to ' + (teamNameOf(r.assign) || 'someone'));
                if (r.folder) acts.push('file in "' + r.folder + '"'
                    + (r.archive ? ' and take it out of the inbox' : ''));
                if (r.done) acts.push('close on arrival');
                row.append(el('div', 'mrule-do', acts.join(', ')
                    + (r.hits ? '  ·  used ' + r.hits + (r.hits === 1 ? ' time' : ' times') : '')));
                if (r.broken) {
                    const w = el('div', 'mrule-broken', r.broken);
                    row.append(w);
                }
                if (lead) {
                    const bar = el('div', 'mrule-bar');
                    const mk = (label, fn) => { const b = el('button', 'btn', label); b.onclick = fn; bar.append(b); };
                    mk('Edit', () => mailRuleForm(m, data, r));
                    mk(r.enabled === false ? 'Switch on' : 'Switch off',
                        async () => reload(await call({ op: 'toggle', id: r.id })));
                    if (i > 0) mk('Up', async () => reload(await call({ op: 'move', id: r.id })));
                    if (i < data.rules.length - 1) mk('Down',
                        async () => reload(await call({ op: 'move', id: r.id, down: true })));
                    mk('Delete', async () => {
                        if (!(await uiConfirm('Delete the filter "' + r.name + '"? '
                            + 'Email it already sorted stays as it is.', { title: 'Delete this filter', okText: 'Delete filter' }))) return;
                        reload(await call({ op: 'delete', id: r.id }));
                    });
                    row.append(bar);
                }
                list.append(row);
            });
            if (!(data.rules || []).length) {
                list.append(el('div', 'mail-empty', lead
                    ? 'No filters yet. A first one might close newsletters on arrival, '
                      + 'or send anything mentioning "invoice" straight to whoever does the books.'
                    : 'No filters have been set up yet.'));
            }
            m.body.append(list);
            if (!lead) {
                m.body.append(el('div', 'setting-sub', 'Only a lead can change these.'));
            } else {
                const bar = el('div', 'mail-statebar');
                const add = el('button', 'btn btn-primary', 'New filter');
                add.onclick = () => mailRuleForm(m, data, null);
                bar.append(add);
                const run = el('button', 'btn', 'Apply to existing mail');
                run.onclick = async () => {
                    if (!(await uiConfirm('Run every filter over the email already here? '
                        + 'Only unclaimed, unassigned email is touched, so nothing is taken '
                        + 'off anyone who is working on it.', { title: 'Apply the filters', okText: 'Apply them' }))) return;
                    run.disabled = true;
                    const r = await call({ op: 'run' });
                    if (r) toastOk(r.changed + ' email' + (r.changed === 1 ? '' : 's') + ' sorted');
                    run.disabled = false;
                    reload(r);
                };
                bar.append(run);
                m.body.append(bar);
            }
            /* Below the filters, and reached by everyone: this used to be an
               early return for a non-lead, who then could not see the footer
               that goes out under their own name. Its own lead flag comes from
               the settings route, which is the server's answer rather than this
               window's. */
            const emailHost = el('div');
            m.body.append(emailHost);
            paintMailEmailSettings(emailHost);
        }
        async function paintMailEmailSettings(host) {
            host.innerHTML = '';
            let d;
            try { d = await api('/api/mail/settings', { op: 'get' }); }
            catch (e) { return; }        /* the filters above still work without it */
            const lead = !!d.lead;
            const emT = el('div', 'section-title', 'Email');
            emT.append(infoButton('About the footer and saved replies', { title: 'Email', body:
                'The footer goes on the end of every email sent from here, under the sender’s '
                + 'own sign-off. Fill in the lines this shop wants on it and leave the rest '
                + 'empty; each one takes up to 200 characters. Saved replies are the '
                + 'paragraphs this shop types over and over.' }));
            host.append(emT);
            /* Six named lines rather than one free-text box: the footer that
               signs every email this business sends is a form, and a form can
               be rendered into a table that Outlook draws the same way Gmail
               does. */
            const slots = d.footer_slots || {};
            const inputs = {};
            [['company', 'Company name'], ['address', 'Address'], ['phone', 'Phone'],
             ['website', 'Website'], ['legal', 'Legal line']].forEach(pair => {
                const f = el('label', 'pfield');
                f.append(el('span', null, pair[1]));
                const i = crmText(slots[pair[0]] || '', pair[1]);
                i.maxLength = 200;
                i.readOnly = !lead;
                f.append(i);
                inputs[pair[0]] = i;
                host.append(f);
            });
            /* The logo goes up the same way an attachment does: signed for,
               PUT straight into the bucket, then confirmed by key. It is shown
               back through a signed link, because the bucket is not public. */
            const logoRow = el('div', 'mail-statebar');
            if (slots.logo_key) {
                const img = el('img', 'mail-sig-logo');
                img.alt = 'Shop logo';
                logoRow.append(img);
                api('/api/mail/settings', { op: 'logo_view' })
                    .then(v => { if (v && v.url) img.src = v.url; }, () => {});
            }
            if (lead) {
                const file = document.createElement('input');
                file.type = 'file';
                file.accept = 'image/png,image/jpeg,image/gif,image/webp';
                file.style.display = 'none';
                file.setAttribute('aria-label', 'Shop logo image');
                const logo = el('button', 'btn', slots.logo_key ? 'Replace the logo' : 'Add a logo');
                logo.onclick = () => file.click();
                file.onchange = async () => {
                    const f = (file.files || [])[0];
                    if (!f) return;
                    logo.disabled = true; logo.textContent = 'Uploading\u2026';
                    try {
                        const r = await api('/api/mail/settings',
                            { op: 'logo_url', name: f.name, size: f.size, type: f.type });
                        const put = await fetch(r.url, { method: 'PUT', body: f,
                            headers: { 'Content-Type': f.type || 'application/octet-stream' } });
                        if (!put.ok) {
                            throw new Error('Storage refused the logo (status ' + put.status
                                + '). Nothing was changed.');
                        }
                        await api('/api/mail/settings', { op: 'logo_done', key: r.key });
                        toastOk('Logo saved.');
                        refreshMailQuiet();
                        paintMailEmailSettings(host);
                    } catch (e) {
                        toastError(e.message);
                        logo.disabled = false;
                        logo.textContent = slots.logo_key ? 'Replace the logo' : 'Add a logo';
                    }
                };
                logoRow.append(logo, file);
            }
            host.append(logoRow);
            if (lead) {
                const bar = el('div', 'mail-statebar');
                const save = el('button', 'btn', 'Save footer');
                save.onclick = async () => {
                    save.disabled = true;
                    const out = {};
                    Object.keys(inputs).forEach(k => { out[k] = inputs[k].value.trim(); });
                    try { await api('/api/mail/settings', { op: 'footer_slots', slots: out }); }
                    catch (e) { toastError(e.message); save.disabled = false; return; }
                    toastOk('Footer saved.');
                    save.disabled = false;
                    refreshMailQuiet();
                };
                bar.append(save);
                host.append(bar);
            }
            host.append(el('div', 'setting-title', 'Saved replies'));
            const list = el('div');
            host.append(list);
            const reps = (d.saved_replies || []).slice();
            const reload = async () => {
                let r;
                try { r = await api('/api/mail/settings', { op: 'get' }); }
                catch (e) { toastError(e.message); return; }
                paintMailEmailSettings(host);
                refreshMailQuiet();
                return r;
            };
            const paintList = () => {
                list.innerHTML = '';
                if (!reps.length) {
                    list.append(el('div', 'mail-empty', lead
                        ? 'No saved replies yet. A first one might be the artwork rules, or the '
                          + 'lead time on a custom gobo.'
                        : 'No saved replies have been set up yet.'));
                }
                reps.forEach(r => {
                    const row = el('div', 'mrule');
                    row.append(el('div', 'mrule-name', r.title));
                    row.append(el('div', 'mrule-do', r.text));
                    if (!lead) { list.append(row); return; }
                    const bar = el('div', 'mrule-bar');
                    const ed = el('button', 'btn', 'Edit');
                    ed.onclick = () => replyForm(row, r);
                    const del = el('button', 'btn', 'Delete');
                    del.onclick = async () => {
                        if (!(await uiConfirm('Delete the saved reply "' + r.title + '"? '
                            + 'Email it was already used in is not touched.', { title: 'Delete this saved reply', okText: 'Delete reply' }))) return;
                        try { await api('/api/mail/settings', { op: 'reply_delete', id: r.id }); }
                        catch (e) { toastError(e.message); return; }
                        reload();
                    };
                    bar.append(ed, del);
                    row.append(bar);
                    list.append(row);
                });
                if (!lead) return;
                const add = el('button', 'btn btn-primary', 'Add a saved reply');
                add.onclick = () => replyForm(add, null);
                list.append(add);
            };
            /* Edited in place, next to the other replies, so the list it is
               being compared against stays on screen. */
            function replyForm(anchor, r) {
                const box = el('div', 'mrule');
                const title = crmText(r ? r.title : '', 'What it is for, e.g. Artwork rules');
                crmField(box, 'Title', title);
                const text = document.createElement('textarea');
                text.className = 'mail-draft-text'; text.rows = 4; text.value = r ? r.text : '';
                text.setAttribute('aria-label', 'Saved reply text');
                box.append(text);
                const bar = el('div', 'mrule-bar');
                const save = el('button', 'btn btn-primary', 'Save');
                save.onclick = async () => {
                    save.disabled = true;
                    const payload = { op: 'reply_save', title: title.value.trim(), text: text.value };
                    if (r) payload.id = r.id;
                    try { await api('/api/mail/settings', payload); }
                    catch (e) { toastError(e.message); save.disabled = false; return; }
                    reload();
                };
                const cancel = el('button', 'btn', 'Cancel');
                cancel.onclick = () => { box.remove(); anchor.style.display = ''; };
                bar.append(save, cancel);
                box.append(bar);
                anchor.style.display = 'none';
                anchor.after(box);
                title.focus();
            }
            paintList();
        }
        function mailRuleForm(m, data, rule) {
            const r = rule ? JSON.parse(JSON.stringify(rule))
                : { name: '', mode: 'all', conditions: [{ field: 'from', op: 'contains', value: '' }],
                    assign: '', pool: [], done: false, folder: '', archive: false, enabled: true };
            m.body.innerHTML = '';
            m.body.append(el('div', 'setting-title', rule ? 'Edit filter' : 'New filter'));
            const name = crmText(r.name, 'What is this filter for?');
            crmField(m.body, 'Name', name);
            const modeRow = el('div', 'setting-sub');
            modeRow.style.margin = 'var(--sp-2-5) 0 var(--sp-1)';
            modeRow.append(document.createTextNode('Match '));
            const mode = document.createElement('select');
            mode.className = 'mail-presence-pick';
            mode.setAttribute('aria-label', 'Match mode');
            [['all', 'all of these'], ['any', 'any of these']].forEach(([v, t]) => {
                const o = document.createElement('option');
                o.value = v; o.textContent = t; if (r.mode === v) o.selected = true;
                mode.append(o);
            });
            modeRow.append(mode);
            m.body.append(modeRow);
            const conds = el('div');
            const paintConds = () => {
                conds.innerHTML = '';
                r.conditions.forEach((c, i) => {
                    const row = el('div', 'mrule-cond');
                    const f = document.createElement('select'); f.className = 'mail-presence-pick'; f.setAttribute('aria-label', 'Condition field');
                    MAIL_FIELDS.forEach(([v, t]) => {
                        const o = document.createElement('option');
                        o.value = v; o.textContent = t; if (c.field === v) o.selected = true;
                        f.append(o);
                    });
                    f.onchange = () => { c.field = f.value; };
                    const o2 = document.createElement('select'); o2.className = 'mail-presence-pick'; o2.setAttribute('aria-label', 'Condition comparison');
                    MAIL_OPS.forEach(([v, t]) => {
                        const o = document.createElement('option');
                        o.value = v; o.textContent = t; if (c.op === v) o.selected = true;
                        o2.append(o);
                    });
                    o2.onchange = () => { c.op = o2.value; };
                    const val = crmText(c.value, 'what to look for');
                    val.style.flex = '1';
                    val.oninput = () => { c.value = val.value; };
                    row.append(f, o2, val);
                    if (r.conditions.length > 1) {
                        const x = iconButton(I.x, 'Remove');
                        x.onclick = () => { r.conditions.splice(i, 1); paintConds(); };
                        row.append(x);
                    }
                    conds.append(row);
                });
                const more = el('button', 'btn', 'Add another condition');
                more.onclick = () => {
                    if (r.conditions.length >= 8) return;
                    r.conditions.push({ field: 'subject', op: 'contains', value: '' });
                    paintConds();
                };
                conds.append(more);
            };
            paintConds();
            m.body.append(conds);
            m.body.append(el('div', 'setting-title', 'Then'));
            const who = document.createElement('select');
            who.className = 'mail-presence-pick';
            who.setAttribute('aria-label', 'Assign matches to');
            [['', 'leave it for the room'], ['_round', 'share out between people']].forEach(([v, t]) => {
                const o = document.createElement('option'); o.value = v; o.textContent = t;
                if (r.assign === v) o.selected = true; who.append(o);
            });
            (mailCache.team || []).filter(u => u.can_own !== false).forEach(u => {
                const o = document.createElement('option');
                o.value = u.uid; o.textContent = 'give it to ' + u.name;
                if (r.assign === u.uid) o.selected = true; who.append(o);
            });
            const poolBox = el('div', 'mrule-pool');
            const paintPool = () => {
                poolBox.innerHTML = '';
                poolBox.style.display = who.value === '_round' ? '' : 'none';
                if (who.value !== '_round') return;
                poolBox.append(el('div', 'setting-sub', 'Share between:'));
                (mailCache.team || []).filter(u => u.can_own !== false).forEach(u => {
                    const l = el('label', 'tm-tabpick');
                    const cb = document.createElement('input');
                    cb.type = 'checkbox'; cb.checked = (r.pool || []).indexOf(u.uid) >= 0;
                    cb.onchange = () => {
                        r.pool = cb.checked ? (r.pool || []).concat([u.uid])
                                            : (r.pool || []).filter(x => x !== u.uid);
                    };
                    l.append(cb, document.createTextNode(u.name));
                    poolBox.append(l);
                });
            };
            who.onchange = () => { r.assign = who.value; paintPool(); };
            crmField(m.body, 'Owner', who);
            m.body.append(poolBox);
            paintPool();
            const folder = crmText(r.folder || '', 'e.g. Newsletters, or Suppliers/Glass');
            folder.oninput = () => { r.folder = folder.value; paintArch(); };
            crmField(m.body, 'File it in a Gmail folder (optional)', folder);
            const archL = el('label', 'tm-tabpick');
            const archCb = document.createElement('input');
            archCb.type = 'checkbox'; archCb.checked = !!r.archive;
            archCb.onchange = () => { r.archive = archCb.checked; };
            archL.append(archCb, document.createTextNode('and take it out of the Gmail inbox'));
            const paintArch = () => { archL.style.display = folder.value.trim() ? '' : 'none'; };
            paintArch();
            m.body.append(archL);
            m.body.append(el('div', 'setting-sub', 'A folder is a Gmail label. Use / to nest.'));
            const doneL = el('label', 'tm-tabpick');
            const doneCb = document.createElement('input');
            doneCb.type = 'checkbox'; doneCb.checked = !!r.done;
            doneCb.onchange = () => { r.done = doneCb.checked; };
            doneL.append(doneCb, document.createTextNode('Close it on arrival (for mail nobody needs to answer)'));
            m.body.append(doneL);
            const bar = el('div', 'mail-statebar');
            const save = el('button', 'btn btn-primary', 'Save filter');
            save.onclick = async () => {
                r.name = name.value; r.mode = mode.value; r.assign = who.value;
                r.folder = folder.value.trim();
                save.disabled = true;
                try {
                    const out = await api('/api/mail/rules', { op: 'save', rule: r });
                    paintMailRules(m, { rules: out.rules, lead: true });
                    refreshMailQuiet();
                } catch (e) { toastError(e.message); save.disabled = false; }
            };
            const back = el('button', 'btn', 'Back');
            back.onclick = () => paintMailRules(m, data);
            bar.append(save, back);
            m.body.append(bar);
        }

        /* ---- sending, which is the only thing this app does that cannot be
           taken back ----------------------------------------------------- */
        /* One place decides. The grant is a switch on the account, and admins
           and the master hold it by rank and cannot be toggled, so both have to
           be read: exactly how the size-list grant works. The server enforces
           it either way; this only keeps a button that would always fail off
           the screen. */
        function mailCanSend() {
            return !!(teamMe && (teamMe.can_send || teamMe.send_by_rank));
        }
        /* Report, never shred. The server stamps a send into the store BEFORE
           it calls Gmail, so a crash in between leaves a maybe rather than a
           lie in either direction. A maybe is worth saying out loud, in the
           words that tell someone what to do about it. */
        function mailPendingLine(to, at) {
            return 'A message to ' + (to || 'someone') + ' may have gone out '
                + (mailAgoLong(at) || 'recently') + ': check Gmail\'s Sent folder.';
        }
        /* Two steps, one function, shared by the reply panel and the compose
           window so the confirm can never go missing from one of them.
           Step one posts dry:true: the server runs every check it runs for
           real - the grant, who owns the thread, whether the addresses parse,
           the five-address cap, whether one of them is the mailbox itself -
           writes nothing, sends nothing, and answers with the recipient it
           actually resolved. Step two sends THAT payload, unchanged, so what
           the person agreed to is what leaves. Nothing but Send now issues it,
           and only a success calls done(). */
        async function mailSendFlow(bar, payload, buttons, done) {
            buttons.forEach(b => { b.disabled = true; });
            let dry;
            try { dry = await api('/api/mail/send', Object.assign({ dry: true }, payload)); }
            catch (e) {
                toastError(e.message);
                buttons.forEach(b => { b.disabled = false; });
                return;
            }
            const to = dry.to || '';
            /* Counted by the SERVER on the dry run, never by this window. A
               file that never landed in the bucket is not in the server's
               count, so the number beside Send now is the number that will
               actually go out. */
            const ccN = dry.cc_count || 0, attN = dry.attachment_count || 0;
            const line = 'Send to ' + to
                + (ccN ? ', ' + ccN + ' cc' : '')
                + (attN ? ', ' + attN + (attN === 1 ? ' attachment' : ' attachments') : '')
                + '?';
            const row = el('div', 'mail-statebar');
            row.append(el('div', 'setting-sub', line));
            const go = el('button', 'btn btn-primary', 'Send now');
            const back = el('button', 'btn', 'Back');
            go.onclick = async () => {
                go.disabled = true; back.disabled = true;
                let r;
                try { r = await api('/api/mail/send', payload); }
                catch (e) {
                    /* A refusal at the last step is still a refusal: hand the
                       row back rather than closing over a message that never
                       went, which would read as sent. But no answer is not a
                       refusal: it may have gone, and Send offered again would
                       email the customer twice. */
                    toastError(e.message);
                    back.disabled = false;
                    if (e.noReply) {
                        go.textContent = 'May have been sent: check the conversation';
                        return;
                    }
                    go.disabled = false;
                    return;
                }
                /* Sent, with something to know: Gmail filed it as its own
                   conversation, or the board could not be saved. The server
                   said so and this window used to drop it on the floor. */
                if (r && r.warning) addToast(r.warning);
                else toastOk('Sent to ' + to);
                done(to);
            };
            back.onclick = () => {
                /* The bar carries the buttons AND sits above the textarea the
                   words are in. Putting it back is the whole of Back. */
                row.replaceWith(bar);
                buttons.forEach(b => { b.disabled = false; });
            };
            row.append(go, back);
            bar.replaceWith(row);
        }
        /* ---- the address book behind the To line -------------------------
           Typing a customer's address from memory is how a message goes to the
           wrong person. The server merges every thread's counterparty with
           every CRM email and sends the whole book down in one answer, because
           1,951 people is one fetch, not one per keystroke. Only
           mailAddressBook writes this. */
        let mailAddrCache = { at: 0, rows: [] };
        const MAIL_ADDR_TTL = 10 * 60 * 1000;   /* a book changes at the pace people do */
        async function mailAddressBook() {
            if (mailAddrCache.at && Date.now() - mailAddrCache.at < MAIL_ADDR_TTL) return;
            try {
                const d = await api('/api/mail/addresses', {});
                mailAddrCache = { at: Date.now(), rows: (d && d.addresses) || [] };
            } catch (e) {
                /* Silent, and deliberately not cached: nobody asked for an
                   address book, the To line is a text box that works without
                   one, and a toast here would be an error about a convenience.
                   Leaving at at 0 means the next Compose tries again. */
            }
        }
        /* Everything before the last comma is an address the person has already
           finished with. Only the tail is being typed, and only the tail is
           what a pick is allowed to replace. */
        function mailAddressToken(v) {
            const i = String(v || '').lastIndexOf(',');
            return { head: i < 0 ? '' : v.slice(0, i + 1), tail: i < 0 ? String(v || '') : v.slice(i + 1) };
        }
        function mailAddressRows(q) {
            const t = mailAddressToken(q).tail.trim().toLowerCase();
            if (!t) return [];
            return (mailAddrCache.rows || [])
                .filter(r => (r.name + ' ' + r.email).toLowerCase().includes(t))
                .map(r => ({
                    /* Half of these people are remembered by name and half by
                       the address, so a row carries both: the name on top and
                       the address beneath it, with the company where there is
                       one. An address with no name shows as itself rather than
                       as a blank line with a subtitle. */
                    id: r.email, email: r.email,
                    name: r.name || r.email,
                    sub: r.name ? (r.email + (r.sub ? ' · ' + r.sub : '')) : (r.sub || ''),
                }));
        }
        /* The board carries the shop footer, the caller's own sign-off and the
           saved replies. One reader, because a board fetched before this
           existed has no email block at all and every caller would otherwise
           need the same guard. */
        function mailEmailBits() {
            const e = (mailCache && mailCache.email) || {};
            return { footer_slots: e.footer_slots || {}, sign_off: e.sign_off || '',
                     saved_replies: e.saved_replies || [] };
        }
        /* The composer is a second file, loaded beside app.js. If it did not
           arrive, say so plainly: a window half built around a missing editor
           is worse than not opening one. */
        function mailComposerReady() {
            if (typeof window.mountComposer === 'function') return true;
            toastError('The message editor did not load. Refresh the page and try again.');
            return false;
        }
        /* An attachment never passes through our own server. The browser asks
           for a signed URL, PUTs the bytes straight into the bucket and only
           then tells the server which key landed, so a 20MB artwork file is a
           transfer between the person and storage rather than a request body
           this app has to hold in memory and hand on. */
        async function mailUpload(file, inline) {
            const ctype = file.type || 'application/octet-stream';
            const r = await api('/api/mail/attach-url',
                { name: file.name, size: file.size, type: ctype, inline: !!inline });
            const put = await fetch(r.url, { method: 'PUT', body: file,
                                             headers: { 'Content-Type': ctype } });
            if (!put.ok) {
                throw new Error('Storage refused the upload (status ' + put.status + '). '
                    + 'Nothing was attached.');
            }
            /* The server re-reads the size off the bucket here, so what the
               meter counts is what actually landed rather than what the file
               picker claimed. */
            const d = await api('/api/mail/attach-done', { key: r.key });
            return { key: d.key || r.key, name: d.name || file.name,
                     size: d.size == null ? file.size : d.size,
                     type: d.type || ctype, url: d.url || '' };
        }
        /* One shape for both windows: what the composer holds, split the way
           the send route reads it. Inline images travel as keys and content
           ids; the html already refers to them as cid: and nothing else. */
        function mailComposerPayload(h) {
            const all = h.attachments();
            return {
                html: h.getHtml(),
                attachments: all.filter(a => !a.inline)
                    .map(a => ({ key: a.key, name: a.name, type: a.type })),
                inline: all.filter(a => a.inline)
                    .map(a => ({ key: a.key, cid: a.cid, type: a.type })),
            };
        }
        /* Cc and Bcc are empty on almost every reply, so they are folded away
           behind one link rather than sitting there as two more boxes to skip
           past on a phone. */
        function mailCcFold(host) {
            const wrap = el('div');
            wrap.style.display = 'none';
            const mk = (name, ph) => {
                const l = el('label', 'pfield');
                l.append(el('span', null, name));
                const i = crmText('', ph);
                i.inputMode = 'email'; i.spellcheck = false;
                l.append(i); wrap.append(l);
                return i;
            };
            const cc = mk('Cc', 'name@company.com');
            const bcc = mk('Bcc', 'nobody sees this line');
            const ccLink = textLink('Cc / Bcc');
            ccLink.setAttribute('aria-expanded', 'false');
            const toggle = () => {
                const open = wrap.style.display === 'none';
                wrap.style.display = open ? '' : 'none';
                ccLink.setAttribute('aria-expanded', open ? 'true' : 'false');
                if (open) cc.focus();
            };
            ccLink.onclick = toggle;
            host.append(ccLink, wrap);
            /* Shown as soon as there is something in them, so a Reply all or a
               reopened panel never hides an address that is going to be used. */
            const reveal = () => {
                if (wrap.style.display === 'none' && (cc.value || bcc.value)) toggle();
            };
            return { cc, bcc, reveal };
        }
        /* What the server will put on the end. A person writing a reply cannot
           otherwise see what it actually ends with, and the first time they
           find out should not be in the customer's inbox. */
        function mailAddedWhenSent(host) {
            const bits = mailEmailBits();
            const sign = (bits.sign_off || '').trim();
            const slots = bits.footer_slots || {};
            /* Drawn from the SLOTS, line by line, as text. The server renders
               the real footer into a table and sanitises it; this is a preview,
               and a preview has no business being the one place in the app that
               injects markup. */
            const lines = ['company', 'address', 'phone', 'website', 'legal']
                .map(k => String(slots[k] || '').trim()).filter(Boolean);
            const logo = String(slots.logo_key || '');
            /* Either half is a footer: a shop that has set only a logo still
               has something put on the end of its email. */
            const foot = lines.join('\n') + logo;
            /* Nothing set, nothing drawn: a box labelled "Added when sent" with
               nothing in it says something is added when nothing is. */
            if (!sign && !foot) return;
            const box = el('div', 'mail-sig');
            box.append(el('div', 'mail-sig-lab', 'Added when sent'));
            if (sign) box.append(el('div', 'mail-sig-text', sign));
            if (logo) {
                /* Our own logo, out of our own bucket, behind a signed link
                   that the server hands over only to somebody with the Inbox.
                   It is decoration: if the link never arrives the img stays
                   sourceless and the lines below still say what goes out. */
                const img = el('img', 'mail-sig-logo');
                img.alt = String(slots.company || 'Shop logo');
                box.append(img);
                api('/api/mail/settings', { op: 'logo_view' })
                    .then(d => { if (d && d.url) img.src = d.url; }, () => {});
            }
            lines.forEach(l => box.append(el('div', 'mail-sig-text', l)));
            host.append(box);
        }
        /* The saved replies, into the composer at the cursor. */
        function mailReplyPicker(cmp, host) {
            const reps = mailEmailBits().saved_replies;
            /* No saved replies, no select: an empty dropdown is a dead control
               that still costs a glance every time the window opens. */
            if (!reps.length) return;
            const sel = el('select', 'psel mail-insert');
            sel.setAttribute('aria-label', 'Insert saved reply');
            const head = el('option', null, 'Insert saved reply'); head.value = '';
            sel.append(head);
            reps.forEach(r => { const o = el('option', null, r.title); o.value = r.id; sel.append(o); });
            sel.onchange = () => {
                const r = reps.find(x => x.id === sel.value);
                sel.value = '';                  /* so the same one can go in twice */
                if (!r) return;
                /* At the cursor and over any selection, not appended: a saved
                   reply is dropped into a paragraph already being written, and
                   putting the artwork rules after the last line instead lands
                   them below a half-finished sentence. The composer inserts at
                   the caret it kept when the focus moved to this dropdown, and
                   leaves the caret after what it just put in. */
                cmp.insertText(r.text || '');
                cmp.focus();
            };
            host.append(sel);
        }
        /* A new conversation rather than a reply. Same modal idiom as Size
           rules, same two-step send as the reply panel. */
        function openMailCompose() {
            if (!mailComposerReady()) return;
            // X only (dialog()): a half-written email to a customer is not
            // thrown away by a stray click on the backdrop.
            const win = dialog({ title: 'New email', bodyClass: 'stack-form' });
            const { overlay, modal, head, x, body } = win;
            /* A form with a form's rhythm: the fields were stacked with 0 to
               2px between them, and the rule about addresses sat under Send,
               420px from the field it is about. */

            body.append(el('p', 'card-sub', 'It goes out from '
                + ((mailCache && mailCache.address) || 'the shared mailbox')
                + ', and replies come back to the board.'));
            const toL = el('label', 'pfield');
            toL.append(el('span', null, 'To'));
            const to = crmText('', 'name@company.com, another@company.com');
            /* inputMode, not type=email. A multiple email input runs the HTML
               value sanitiser on every write: it splits on the commas and
               strips the spaces around them, so the ", " a pick appends came
               back as ",". Nothing here ever asked the browser to validate
               (there is no form, and the server checks the addresses on the dry
               run), so the type bought only the on-screen mangling. inputMode
               keeps the @ keyboard on a phone, which was the real reason. */
            to.inputMode = 'email'; to.spellcheck = false;
            /* Picking writes the address, not the name, and only over the one
               being typed: four already in the box are not wiped by a pick on
               the fifth. The trailing separator saves a keystroke and tells the
               dropdown the token is finished, so it closes rather than offering
               to complete the address it just wrote. */
            const pick = (r) => {
                const p = mailAddressToken(to.value);
                to.value = (p.head ? p.head + ' ' : '') + r.email + ', ';
            };
            toL.append(crmTypeahead(to, mailAddressRows, { pick }));
            /* Said where it is typed. A cap discovered by being refused is a
               cap nobody knew about. */
            toL.append(el('span', 'field-help', 'Up to five addresses, separated by commas.'));
            body.append(toL);
            const folds = mailCcFold(body);
            /* Not awaited: the window opens now, and the book arrives while the
               subject is being typed. A failure leaves a plain text field. */
            mailAddressBook();
            const subL = el('label', 'pfield');
            subL.append(el('span', null, 'Subject'));
            const subject = crmText('', 'What it is about');
            subL.append(subject);
            body.append(subL);
            /* A div, not a label: the message box is a contenteditable, and a
               label wrapping one hands every click on the caption back to the
               browser to place a caret with. */
            const bodyL = el('div', 'pfield');
            bodyL.append(el('span', null, 'Message'));
            const box = el('div');
            bodyL.append(box);
            body.append(bodyL);
            const cmp = mountComposer(box, { upload: mailUpload, ask: composerAsk, label: 'Message',
                                             placeholder: 'Write the message' });
            mailReplyPicker(cmp, body);
            mailAddedWhenSent(body);
            const bar = el('div', 'mail-statebar');
            const send = el('button', 'btn btn-primary', 'Send');
            send.onclick = () => mailSendFlow(bar,
                Object.assign({ to: to.value.trim(), cc: folds.cc.value.trim(),
                                bcc: folds.bcc.value.trim(), subject: subject.value.trim() },
                              mailComposerPayload(cmp)),
                [send],
                () => { win.close(); refreshMailQuiet(); });
            bodyL.append(el('span', 'field-help', 'Sent as shown, with your sign-off and the footer.'));
            bar.append(send);
            body.append(bar);
        }

        /* Claude drafts, a person edits, and then it either goes to the
           customer from here or waits in Gmail as a draft. Either way a person
           reads it first: nothing on this panel sends without a confirm step
           naming the address it resolved. */
        async function mailComposeDraft(m, t, btn, guidance, previous) {
            const old = m.body.querySelector('.mail-draft');
            if (old) old.remove();
            const host = el('div', 'mail-draft');
            btn.disabled = true;
            btn.textContent = guidance ? 'Rewriting\u2026' : 'Reading the conversation\u2026';
            host.append(el('div', 'setting-sub', 'Claude is reading the whole thread.'));
            btn.parentNode.after(host);
            let out;
            try {
                out = await api('/api/mail/draft', guidance || previous
                    ? { id: t.id, op: 'compose', guidance: guidance || '',
                        previous: previous || '' }
                    : { id: t.id, op: 'compose' });
            } catch (e) {
                host.remove();
                btn.disabled = false; btn.textContent = 'Compose reply with Claude';
                toastError(e.message);
                return;
            }
            btn.disabled = false; btn.textContent = 'Compose reply with Claude';
            host.remove();
            mailDraftPanel(m, t, btn, out);
        }
        /* One place that builds the draft panel, so the compose path and the
           rescue-after-repaint path can never drift apart. */
        function mailDraftPanel(m, t, btn, out) {
            if (!mailComposerReady()) return;
            const prior = m.body.querySelector('.mail-draft');
            if (prior) prior.remove();
            const host = el('div', 'mail-draft');
            btn.parentNode.after(host);
            host.append(el('div', 'setting-title', 'Draft reply'));
            host.append(el('div', 'setting-sub',
                'Read it before it goes anywhere. Claude leaves gaps like ____ where '
                + 'it would have had to guess at a price or a date: fill those in.'));
            const box = el('div');
            host.append(box);
            const cmp = mountComposer(box, { upload: mailUpload, ask: composerAsk, label: 'Reply',
                                             placeholder: 'Write the reply' });
            /* The panel keeps its own handle, so a repaint of the thread can
               rescue what is half written and the order panel can drop a
               tracking line into it. */
            host._cmp = cmp;
            (out.draft_files || []).forEach(a => cmp.addAttachment(a));
            if (out.draft_html) cmp.setHtml(out.draft_html);
            else if (out.draft) cmp.insertText(out.draft);
            const folds = mailCcFold(host);
            /* Reply all is a switch, not a second Send: it fills the Cc with
               the list the SERVER worked out, which already has this mailbox
               and the person being answered taken out of it. */
            const rall = String(t.reply_all_cc || '');
            if (rall) {
                const rrow = el('label', 'tm-tabpick');
                const ra = document.createElement('input');
                ra.type = 'checkbox';
                ra.onchange = () => {
                    if (ra.checked) { folds.cc.value = rall; folds.reveal(); }
                    else if (folds.cc.value === rall) folds.cc.value = '';
                };
                rrow.append(ra, el('span', null, 'Reply all (' + rall + ')'));
                host.append(rrow);
            }
            /* The original is quoted by the server, under the reply, in the
               shape every mail client draws. Nothing a customer sent is ever
               rendered as html in this page, so this is a promise about the
               message rather than a preview of it. */
            const qrow = el('label', 'tm-tabpick');
            const quote = document.createElement('input');
            quote.type = 'checkbox'; quote.checked = true;
            qrow.append(quote, el('span', null,
                'The original message will be quoted below your reply'));
            host.append(qrow);
            /* Claude is told to stop after its last sentence, so the sign-off
               and the footer under the box are the whole of what gets added. */
            mailReplyPicker(cmp, host);
            mailAddedWhenSent(host);
            const payload = () => Object.assign(
                { id: t.id, cc: folds.cc.value.trim(), bcc: folds.bcc.value.trim(),
                  quote: quote.checked },
                mailComposerPayload(cmp));
            const canSend = mailCanSend();
            const bar = el('div', 'mail-statebar');
            /* Save steps back to secondary only where Send has taken the lead.
               Where sending is not allowed, Save is still the action of the
               panel and keeps the emphasis it always had. */
            const save = el('button', canSend ? 'btn' : 'btn btn-primary',
                            'Save to Gmail as a draft');
            save.onclick = async () => {
                save.disabled = true;
                let res;
                try {
                    res = await api('/api/mail/draft',
                        Object.assign({ op: 'save' }, payload()));
                } catch (e) { toastError(e.message); save.disabled = false; return; }
                toastOk(res && res.kept_previous
                    ? 'Saved. Your earlier draft had been edited in Gmail, so that one was '
                      + 'kept too: there are now two drafts on this conversation.'
                    : 'Saved into Gmail. Open the conversation there to check it and send.');
                host.remove();
                refreshMailQuiet();
            };
            const copy = el('button', 'btn', 'Copy');
            copy.onclick = async () => {
                try { await navigator.clipboard.writeText(cmp.getText()); toastOk('Copied'); }
                catch (e) {
                    cmp.focus();
                    toastError('Select all and copy with the keyboard.');
                }
            };
            const drop = el('button', 'btn', 'Discard');
            drop.onclick = () => host.remove();
            if (canSend) {
                const send = el('button', 'btn btn-primary', 'Send');
                /* The text is read off the textarea HERE, once, so the confirm
                   step names the address for the words that were actually on
                   screen when it was pressed. */
                send.onclick = () => mailSendFlow(bar, payload(),
                    [send, save, copy, drop],
                    () => { host.remove(); refreshMailQuiet(); });
                bar.append(send);
            }
            bar.append(save, copy, drop);
            host.append(bar);
            /* Steering: say what to change and it drafts again, rather than
               making the person rewrite a paragraph they did not want. */
            const steer = el('div', 'mrule-cond');
            steer.style.marginTop = 'var(--sp-2)';
            const note = crmText('', 'Not right? Say what to change, then Try again');
            note.style.flex = '1';
            const again = el('button', 'btn', 'Try again');
            again.onclick = () => mailComposeDraft(m, t, btn, note.value.trim(), cmp.getText());
            steer.append(note, again);
            host.append(steer);
            host.append(el('div', 'setting-sub', canSend
                ? 'Send goes straight to the customer from '
                  + ((mailCache && mailCache.address) || 'the shared mailbox')
                  + '. Save keeps it as a Gmail draft instead.'
                : 'Saving puts it in Gmail as a draft, and you send it from there. '
                  + 'You are not set up to send email from here. '
                  + 'Ask a lead to switch it on in Team.'));
        }

        async function mailLoadOrders(host, t, m) {
            let r;
            try { r = await api('/api/mail/orders', { id: t.id }); }
            catch (e) { return; }                 /* context is a bonus, never a blocker */
            const list = (r.orders || []);
            if (!list.length) {
                if (r.error) { host.className = 'mail-orders'; host.append(el('div', 'setting-sub', r.error)); }
                return;
            }
            /* The box is drawn by having something in it. Most senders on a
               shared inbox are not Shopify customers, so the empty path is the
               common one, and it used to leave a bordered grey pill 42px tall
               carrying nothing between the buttons and the Gmail link. */
            host.className = 'mail-orders';
            const head = el('div', 'mail-orders-head');
            head.textContent = (r.customer && r.customer.name ? r.customer.name : 'This sender')
                + (r.customer && r.customer.orders_count
                    ? '  ·  ' + r.customer.orders_count + ' order'
                      + (r.customer.orders_count === 1 ? '' : 's') + ' with us' : '');
            host.append(head);
            list.forEach(o => {
                const row = el('div', 'mail-order');
                const top = el('div', 'mail-order-top');
                const a = el('a', 'mail-order-name', o.name || 'Order');
                a.href = o.admin_url; a.target = '_blank'; a.rel = 'noopener';
                top.append(a);
                const stage = o.tracking ? 'shipped' : o.made_at ? 'made'
                    : o.printed_at ? 'in production' : 'not started';
                top.append(el('span', 'mail-order-stage ' + stage.replace(/ /g, '-'), stage));
                /* Formatted like everywhere else: this printed a raw ISO date
                   and, for a non-GBP order, a bare number with no currency. */
                if (o.total) top.append(el('span', 'mail-order-meta',
                    o.currency === 'GBP' ? '£' + o.total : o.total + ' ' + (o.currency || '')));
                if (o.at) top.append(el('span', 'mail-order-meta', fmtDate(o.at)));
                row.append(top);
                if (o.tracking) {
                    const tr = el('div', 'mail-order-track');
                    tr.append(el('span', null, (o.carrier || 'Courier') + '  ' + o.tracking));
                    const cp = textLink('Copy');
                    cp.onclick = async () => {
                        try { await navigator.clipboard.writeText(o.tracking); toastOk('Tracking copied'); }
                        catch (e) { toastError('Could not copy. Select it by hand.'); }
                    };
                    tr.append(cp);
                    row.append(tr);
                }
                const use = textLink('Put this in the reply');
                use.onclick = () => {
                    const panel = m.body.querySelector('.mail-draft');
                    const line = o.sentence.charAt(0).toUpperCase() + o.sentence.slice(1) + '.';
                    if (panel && panel._cmp) { panel._cmp.appendText(line); }
                    else { navigator.clipboard.writeText(line).then(
                        () => toastOk('Copied. Press Compose reply with Claude to write around it.'),
                        () => toastError('Could not copy.')); }
                };
                row.append(use);
                host.append(row);
            });
        }

        async function openMailArchive(t) {
            /* Older than the board keeps. Readable, and nothing else: it is not
               on the board, so it has no owner, no state and no actions. */
            const m = mailModal('Email (from the archive)');
            m.overlay.querySelector('.modal').classList.add('mreader');
            m.body.append(el('div', 'crm-card-t', t.subject));
            m.body.append(el('div', 'setting-sub',
                (t.from_name || '') + (t.from_email ? ' <' + t.from_email + '>' : '')
                + ' · ' + mailAgoLong(t.last_at)));
            m.body.append(el('div', 'setting-sub',
                'This one is older than the board keeps, so it is read only here.'));
            const gm = el('a', 'setting-sub', 'Open in Gmail');
            gm.dataset.mailReadonly = '';     // reading, so closing need not reload the board
            gm.href = 'https://mail.google.com/mail/u/?authuser='
                + encodeURIComponent(mailCache.address || '')
                + '#all/' + encodeURIComponent(t.id);
            gm.target = '_blank'; gm.rel = 'noopener';
            gm.classList.add('action-link', 'mail-gmail');
            m.body.append(gm);
            const msgs = el('div');
            msgs.style.cssText = 'max-height:360px;overflow-y:auto;margin:var(--sp-2-5) 0';
            m.body.append(msgs);
            let r;
            try { r = await api('/api/mail/body', { id: t.id, archive: true }); }
            catch (e) { msgs.append(el('div', 'setting-sub', e.message)); return; }
            (r.messages || []).forEach(msg => {
                const box = el('div', 'mail-msg' + (msg.ours ? ' ours' : ''));
                const h = el('div', 'mail-msg-head');
                h.append(el('span', 'mail-msg-from', msg.from_name || msg.from_email || ''),
                         el('span', 'mail-msg-at', mailAgoLong(msg.at)));
                const b = el('div', 'mail-msg-full');
                b.textContent = msg.text || '(no text in this message)';
                box.append(h, b);
                msgs.append(box);
            });
        }
        function mailModal(title) {
            const win = dialog({ title: title, size: 'disp-modal', onClose: () => {
                if (overlay._timer) clearInterval(overlay._timer);
                if (!document.querySelector('#view-mail.active')) return;
                if (touched || !m.onQuietClose) refreshMailQuiet(); else m.onQuietClose();
            } });
            const { overlay, modal, head, x, body } = win;
            /* Anything pressed or typed inside the window is why the board is
               fetched again on close. A window that sets onQuietClose (the
               email reader) changes nothing if it was only read, so it puts
               its own row right instead of downloading the whole board (the
               2026-10-12 speed audit, P1). */
            let touched = false;
            /* A control marked data-mail-readonly (reading the full text,
               opening the email in Gmail) and the X itself are reading. */
            const touches = (t) => {
                if (!t || x.contains(t) || !t.closest) return false;
                const c = t.closest('button, a, input, select, textarea, label, [contenteditable]');
                return !!c && !('mailReadonly' in c.dataset);
            };
            overlay.addEventListener('click', (e) => { if (touches(e.target)) touched = true; }, true);
            overlay.addEventListener('input', () => { touched = true; }, true);
            overlay.addEventListener('keydown', (e) => { if (e.key === 'Enter' && touches(e.target)) touched = true; }, true);
            const m = { body: body, overlay: overlay, onQuietClose: null };
            m.close = win.close;
            return m;
        }
        /* The email being fetched to open: a double click (the gesture every
           mail client teaches) or a held Enter sent two reads and stacked two
           windows of one email, each with its own heartbeat. */
        const mailOpening = new Set();
        async function openMailThread(id) {
            if (mailOpening.has(id)) return;
            mailOpening.add(id);
            let r;
            try { r = await api('/api/mail/thread', { id: id }); }
            catch (e) { toastError(e.message); return; }
            finally { mailOpening.delete(id); }
            const m = mailModal('Email');
            m.overlay.querySelector('.modal').classList.add('mreader');
            /* Only read: the server tells Gmail behind its answer, so the one
               change to the board is this row's unread mark. */
            m.onQuietClose = () => {
                const row = mailCache && (mailCache.threads || []).find(t => t.id === id);
                if (row && row.unread) {
                    row.unread = false;
                    /* A copy the page has changed itself is no board the
                       server named: if Gmail refuses the read, the server's
                       board is the one this revision names again, and every
                       poll would be told nothing changed. */
                    mailRev = '';
                    ++mailFetchSeq;    // a poll already in flight carries the board from before the read
                    if (!mailInputBusy()) renderMail();
                }
            };
            paintMailThread(m, r);
            m.overlay._timer = setInterval(async () => {
                try {
                    const v = await api('/api/mail/viewing', { id: id });
                    const warn = m.body.querySelector('.mail-viewwarn');
                    if (v.viewers && v.viewers.length) {
                        const text = v.viewers.join(' and ') + (v.viewers.length === 1 ? ' is' : ' are')
                            + ' also viewing this email right now.';
                        if (warn) { warn.textContent = text; }
                        else {
                            const w = el('div', 'mail-viewwarn', text);
                            m.body.prepend(w);
                        }
                    } else if (warn) warn.remove();
                } catch (e) { /* heartbeat only */ }
            }, 10000);
        }
        function paintMailThread(m, r) {
            const t = r.thread;
            /* Who else was on the customer's last message, worked out by the
               server with this mailbox and the person being answered already
               taken out. Carried on the thread so the reply panel, which is
               handed the thread and not the whole answer, can offer Reply all. */
            t.reply_all_cc = r.reply_all_cc || '';
            /* Rescue an unsaved draft before the rebuild: every other button in
               this modal repaints, and losing two minutes of edited reply to a
               stray click on 'Start work' is not acceptable. */
            const live = m.body.querySelector('.mail-draft');
            const cmpLive = live && live._cmp;
            const rescued = cmpLive && cmpLive.getText() ? cmpLive.getHtml() : '';
            /* The files come with it. They are already in the bucket, so this
               is a list of keys, not a re-upload; an inline picture is the one
               thing a repaint cannot carry, and the composer drops the content
               id with it rather than sending a reference to nothing. */
            const rescuedFiles = rescued && cmpLive
                ? cmpLive.attachments().filter(a => !a.inline) : [];
            m.body.innerHTML = '';
            if (r.viewers && r.viewers.length) {
                m.body.append(el('div', 'mail-viewwarn', r.viewers.join(' and ')
                    + (r.viewers.length === 1 ? ' is' : ' are') + ' also viewing this email right now.'));
            }
            m.body.append(el('div', 'crm-card-t', t.subject));
            /* A meta line, outside the 52ch prose cap the settings help class
               carries: it broke at 414px in a 686px window and orphaned 'ago'. */
            const meta = el('div', 'mail-meta');
            meta.textContent = (t.from_name || '') + (t.from_email ? ' <' + t.from_email + '>' : '')
                + ' · ' + t.msg_count + (t.msg_count === 1 ? ' message' : ' messages')
                + ' · last message ' + mailAgoLong(t.last_at);
            m.body.append(meta);
            if (t.crm_deal_id) {
                /* A website enquiry that already became pipeline: one click
                   lands on its deal, no retyping, no hunting. */
                const chip = el('div', 'mail-crmchip');
                const a = actionLink('miss-open', 'Filed in the CRM: open the deal');
                a.onclick = async () => {
                    m.close();
                    setView('crm');
                    if (!crmCache) { try { const rr = await api('/api/crm/board', {}); crmCache = rr.crm; crmRev = rr.rev || ''; crmLoadedAt = Date.now(); } catch (e) { toastError(e.message); return; } }
                    renderCRM();
                    crmDealModal(t.crm_deal_id);
                };
                chip.append(a);
                m.body.append(chip);
            } else if (r.crm) {
                m.body.append(el('div', 'mail-crmchip', 'CRM: ' + r.crm.name
                    + (r.crm.org ? ' (' + r.crm.org + ')' : '')));
            }
            /* A send that was stamped and never confirmed. It belongs at the
               top of the thread it may have left from, not in the activity
               list twenty lines down. */
            if (t.send_pending) {
                m.body.append(el('div', 'mail-sendwarn',
                    mailPendingLine(t.send_pending.to, t.send_pending.at)));
            }
            /* ---- draft a reply with Claude, or write one ---- */
            const draftBar = el('div', 'mail-statebar');
            const compose = el('button', 'btn', 'Compose reply with Claude');
            compose.onclick = () => mailComposeDraft(m, t, compose);
            draftBar.append(compose);
            /* The same panel, opened empty. Most replies on this inbox are two
               lines that nobody needs a model to write, and spending a credit
               to delete a paragraph first is a poor trade. */
            const blank = el('button', 'btn', 'Write a reply');
            blank.title = 'Type it yourself, with no AI credits spent';
            blank.onclick = () => mailDraftPanel(m, t, compose, { draft: '' });
            draftBar.append(blank);
            if (rescued) {
                /* The repaint would have thrown this away. Put it back with
                   its buttons, exactly where it was. */
                setTimeout(() => mailDraftPanel(m, t, compose,
                    { draft_html: rescued, draft_files: rescuedFiles }), 0);
            }
            if (t.draft_at) {
                draftBar.append(el('span', 'mail-bulk-hint',
                    'a draft was saved into Gmail ' + mailAgoLong(t.draft_at)));
            }
            m.body.append(draftBar);
            const unreadBtn = el('button', 'btn', 'Mark unread');
            unreadBtn.title = 'Puts it back to unread in Gmail too';
            unreadBtn.onclick = async () => {
                unreadBtn.disabled = true;
                try { await api('/api/mail/read', { id: t.id, unread: true }); }
                catch (e) { toastError(e.message); unreadBtn.disabled = false; return; }
                toastOk('Marked unread in Gmail');
                refreshMailQuiet();
            };
            draftBar.append(unreadBtn);
            if ((t.files || []).length) {
                const fbox = el('div', 'mail-files');
                fbox.append(el('div', 'mail-orders-head',
                    t.files.length + (t.files.length === 1 ? ' attachment' : ' attachments')));
                t.files.forEach(f => {
                    const row = el('div', 'mail-file');
                    const nm = el('span', 'mail-file-name', f.name);
                    const kb = f.size > 1048576 ? (f.size / 1048576).toFixed(1) + ' MB'
                        : Math.max(1, Math.round(f.size / 1024)) + ' KB';
                    row.append(nm, el('span', 'mail-order-meta', kb));
                    const already = (t.saved_files || []).some(x => x.name === f.name);
                    if (already) {
                        row.append(el('span', 'mail-order-stage made', 'saved'));
                    } else {
                        const save = textLink('Save to Files');
                        save.onclick = async () => {
                            /* Not the browser's own prompt dialog: Chrome removed
                               it inside a cross-origin iframe, which is where this
                               app runs, so the button did nothing and said nothing. */
                            const where = await uiAskText('Save to Files',
                                'Save "' + f.name + '" into which folder? Use a slash for folders inside folders.',
                                'Folder', 'Artwork', 'Save');
                            if (where === null) return;
                            save.disabled = true; save.textContent = 'Saving\u2026';
                            try {
                                const r = await api('/api/mail/attachment',
                                    { id: t.id, msg: f.msg, att: f.id, name: f.name, folder: where });
                                toastOk('Saved to ' + r.where + '. It is on the Finder drive now.');
                                save.replaceWith(el('span', 'mail-order-stage made', 'saved'));
                            } catch (e) {
                                toastError(e.message);
                                save.disabled = false; save.textContent = 'Save to Files';
                            }
                        };
                        row.append(save);
                    }
                    fbox.append(row);
                });
                m.body.append(fbox);
            }
            /* What this app knows that Gmail cannot: their orders, whether we
               made them, and whether they shipped. Loaded after the thread so
               a slow Shopify never holds up reading the email. */
            const orders = el('div');
            m.body.append(orders);
            mailLoadOrders(orders, t, m);
            const gm = el('a', 'setting-sub', 'Open in Gmail');
            gm.dataset.mailReadonly = '';     // reading, so closing need not reload the board
            gm.href = 'https://mail.google.com/mail/u/?authuser='
                + encodeURIComponent(mailCache.address || '')
                + '#all/' + encodeURIComponent(t.id);
            gm.target = '_blank'; gm.rel = 'noopener';
            gm.classList.add('action-link', 'mail-gmail');
            m.body.append(gm);
            /* ---- ownership + state controls ---- */
            const bar = el('div', 'mail-statebar');
            const ownRow = el('div', 'setting-sub');
            ownRow.textContent = t.owner ? 'Owner: ' + (t.owner_name || 'Someone') : 'Nobody owns this yet.';
            m.body.append(ownRow);
            const reload = async () => {
                try { const r2 = await api('/api/mail/thread', { id: t.id }); paintMailThread(m, r2); }
                catch (e) { toastError(e.message || 'This email is no longer on the board.'); m.close(); }
                refreshMailQuiet();
            };
            const act = (path, body) => async (ev) => {
                /* One click, one move. The repaint builds fresh buttons, so
                   a disabled one never needs re-enabling. */
                if (ev && ev.currentTarget) ev.currentTarget.disabled = true;
                try { await api(path, body); } catch (e) { toastError(e.message); }
                reload();
            };
            if (!t.owner && t.state !== 'done') {
                const b = el('button', 'btn btn-primary', 'Claim this email');
                b.onclick = act('/api/mail/claim', { id: t.id });
                bar.append(b);
            }
            if (t.owner === r.me) {
                if (t.state !== 'progress') {
                    const b = el('button', 'btn', t.state === 'done' ? 'Reopen' : 'Start work');
                    b.onclick = act('/api/mail/state', { id: t.id, state: 'progress' });
                    bar.append(b);
                }
                if (t.state !== 'waiting' && t.state !== 'done') {
                    const b = el('button', 'btn', 'Waiting on customer');
                    b.onclick = act('/api/mail/state', { id: t.id, state: 'waiting' });
                    bar.append(b);
                }
            }
            if (t.owner && (t.owner === r.me || r.lead) && t.state !== 'done') {
                const b = el('button', 'btn', 'Mark done');
                b.onclick = act('/api/mail/state', { id: t.id, state: 'done' });
                bar.append(b);
            }
            if (t.owner === r.me && !r.lead) {
                const b = el('button', 'btn', 'Release');
                b.title = 'Hand this back to the room';
                b.onclick = act('/api/mail/assign', { id: t.id, uid: '' });
                bar.append(b);
            }
            m.body.append(bar);
            if (r.lead) {
                const row = el('div', 'mail-statebar');
                /* A plain select at control height beside the field and the
                   button: it borrowed the presence chip's 12px class. And
                   'release' only means something when somebody holds it. */
                const pick = document.createElement('select');
                pick.setAttribute('aria-label', 'Assign to');
                const none = document.createElement('option');
                none.value = ''; none.textContent = t.owner ? 'Nobody (release)' : 'Choose a person';
                pick.append(none);
                (mailCache && mailCache.team || []).forEach(u => {
                    const o = document.createElement('option');
                    o.value = u.uid; o.textContent = u.name; if (u.uid === t.owner) o.selected = true;
                    pick.append(o);
                });
                const note = document.createElement('input');
                note.type = 'text'; note.className = 'disp-text';
                note.placeholder = 'Handover note (optional)'; note.style.flex = '1';
                const go = el('button', 'btn', 'Assign');
                go.onclick = async () => {
                    go.disabled = true;
                    /* Only a SUCCESS repaints: a failed submit must hand back
                       the button and the typed handover note, not eat them. */
                    try { await api('/api/mail/assign', { id: t.id, uid: pick.value, note: note.value.trim() }); }
                    catch (e) { toastError(e.message); go.disabled = false; return; }
                    reload();
                };
                row.append(pick, note, go);
                m.body.append(row);
            }
            /* ---- the conversation ---- */
            const msgs = el('div'); msgs.style.cssText = 'max-height:260px;overflow-y:auto;margin:var(--sp-2-5) 0';
            const ourAddr = (mailCache && mailCache.address || '').toLowerCase();
            (t.messages || []).forEach(msg => {
                const box = el('div', 'mail-msg' + (ourAddr && msg.from_email === ourAddr ? ' ours' : ''));
                const h = el('div', 'mail-msg-head');
                h.append(el('span', 'mail-msg-from', msg.from_name || msg.from_email || ''),
                         el('span', 'mail-msg-at', mailAgoLong(msg.at)));
                box.append(h, el('div', 'mail-msg-snip', msg.snippet || ''));
                msgs.append(box);
            });
            /* Previews are all the board stores. The real text is fetched on
               demand and never kept: it is customer correspondence, and the
               board has no need to hold it. */
            const full = textLink('Read the full emails');
            full.dataset.mailReadonly = '';   // the text is fetched and never kept: still only reading
            full.onclick = async () => {
                full.disabled = true; full.textContent = 'Reading\u2026';
                let r;
                try { r = await api('/api/mail/body', { id: t.id, archive: !!t.archive }); }
                catch (e) {
                    toastError(e.message);
                    full.disabled = false; full.textContent = 'Read the full emails';
                    return;
                }
                msgs.innerHTML = '';
                (r.messages || []).forEach(msg => {
                    const box = el('div', 'mail-msg' + (msg.ours ? ' ours' : ''));
                    const h = el('div', 'mail-msg-head');
                    h.append(el('span', 'mail-msg-from', msg.from_name || msg.from_email || ''),
                             el('span', 'mail-msg-at', mailAgoLong(msg.at)));
                    const bodyEl = el('div', 'mail-msg-full');
                    bodyEl.textContent = msg.text || '(no text in this message)';
                    box.append(h, bodyEl);
                    msgs.append(box);
                });
                full.remove();
                msgs.style.maxHeight = 'var(--scroll-max)';
            };
            m.body.append(full);
            m.body.append(msgs);
            msgs.scrollTop = msgs.scrollHeight;
            /* ---- internal notes ---- */
            m.body.append(el('div', 'setting-title', 'Internal notes'));
            const notes = el('div');
            (t.notes || []).forEach(n => {
                const box = el('div', 'mail-note');
                box.append(el('div', 'mail-note-meta',
                    (teamNameOf(n.by) || 'Someone') + ' · ' + mailAgoLong(n.at)),
                    el('div', null, n.text));
                notes.append(box);
            });
            m.body.append(notes);
            const nrow = el('div', 'mail-statebar');
            const ninput = document.createElement('input');
            ninput.type = 'text'; ninput.className = 'disp-text';
            ninput.placeholder = 'Add a note for the team (the customer never sees these)';
            ninput.style.flex = '1';
            const nbtn = el('button', 'btn', 'Add note');
            nbtn.onclick = async () => {
                const text = ninput.value.trim();
                if (!text) return;
                nbtn.disabled = true;
                try { await api('/api/mail/note', { id: t.id, text: text }); }
                catch (e) { toastError(e.message); nbtn.disabled = false; return; }
                reload();
            };
            nrow.append(ninput, nbtn);
            m.body.append(nrow);
            /* ---- activity ---- */
            const actHead = el('div', 'setting-title', 'Activity');
            actHead.style.marginTop = 'var(--sp-2-5)';
            m.body.append(actHead);
            (t.activity || []).slice().reverse().slice(0, 20).forEach(a => {
                m.body.append(el('div', 'mail-act',
                    mailAgoLong(a.at) + ' · ' + (a.by ? (teamNameOf(a.by) || 'Someone') + ' ' : '')
                    + a.action + (a.detail ? ' · ' + a.detail : '')));
            });
        }
        function teamNameOf(uid) {
            if (!uid) return '';
            const m = mailCache && (mailCache.team || []).find(u => u.uid === uid);
            return m ? m.name : '';
        }

