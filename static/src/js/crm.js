        /* ==================================================================
           CRM. Modelled on Pipedrive because its design is one idea worth
           copying: you cannot control whether a deal closes, only whether it
           always has a next action. So a card wears one of four states
           (overdue red, due-today green, NOTHING-SCHEDULED amber warning,
           future grey), columns sort by that state, and completing a deal's
           last open activity prompts scheduling the next. All data is local;
           Shopify is read-only here and the AI never sees any of it.
           ================================================================== */
        let crmCache = null, crmSeg = 'deals', crmDealsMode = 'board';
        /* The revision of the board in crmCache, and of the one last drawn.
           The poll sends crmRev and an unchanged board comes back as
           {same: true}, not 400 KB (the 2026-10-12 speed audit, S1). Every
           line that sets crmCache sets crmRev with it, or clears it. */
        let crmRev = '', crmPaintedRev = '';
        let crmQ = '', crmStatus = 'open', crmLeadsMode = 'active', crmContactsMode = 'people';
        let crmActPeriod = 'upcoming', crmActTypesOff = {}, crmActMine = false;
        let crmLabelF = '', crmOwnerF = '', crmContactsQ = '', crmContactsPage = 1, crmContactsSize = 25;
        /* The deals list pages on the same terms the contacts table does: an
           imported desk arrives with hundreds of deals, and one unbounded
           scroll on one tab beside a 25-row pager on the next is two pages. */
        let crmDealsPage = 1, crmDealsSize = 25;
        const crmContactSel = new Set();   /* bulk-delete ticks, master only */
        let crmLoadedAt = 0;
        const CRM_TYPES = [['call', 'Call'], ['meeting', 'Meeting'], ['task', 'Task'],
                           ['deadline', 'Deadline'], ['email', 'Email'], ['lunch', 'Lunch']];
        const crmTypeIcon = t => ({ call: I.phone, meeting: I.users, task: I.check,
                                    deadline: I.flag, email: I.send, lunch: I.coffee }[t] || I.check);
        /* Money the way Pipedrive prints it: grouped thousands, pennies only
           when a value actually has them. £48,750 - never £48750.00. */
        function crmMoney(n) {
            n = Number(n) || 0;
            const opts = Math.abs(n % 1) > 0.004
                ? { minimumFractionDigits: 2, maximumFractionDigits: 2 }
                : { maximumFractionDigits: 0 };
            return '£' + n.toLocaleString('en-GB', opts);
        }
        function crmPerson(id) { return (crmCache.persons || {})[id] || null; }
        function crmOrg(id) { return (crmCache.orgs || {})[id] || null; }
        function crmWho(d) {
            const p = crmPerson(d.person_id), o = crmOrg(d.org_id);
            return [p && p.name, o && o.name].filter(Boolean).join(' · ');
        }
        /* Pipedrive colour NAMES to paint; the store carries the names so the
           imported labels keep the colours they had. Where a name collides
           with a house semantic (red, green, yellow) it wears the house
           token's value, so a Hot label and a lost chip are the SAME red. */
        const CRM_COLOR_CSS = Object.fromEntries(['red', 'orange', 'yellow', 'green', 'blue', 'purple', 'pink', 'brown', 'gray', 'dark-gray']
            .map(k => [k, tokenValue('--owner-' + k)]));
        function crmLabelColor(name) {
            /* Only the known names map to a colour. The raw string used to fall
               through into style.background, and a Pipedrive label coloured
               url(//evil.co/a) then beaconed every render of the board. */
            const c = ((crmCache && crmCache.label_colors) || {})[name] || '';
            if (CRM_COLOR_CSS[c]) return CRM_COLOR_CSS[c];
            return /^#[0-9a-f]{3,8}$/i.test(c) ? c : 'var(--text-tertiary)';
        }
        function crmChip(name) {
            /* Tinted ground, full-strength text: white-on-amber was 2.4:1. */
            /* A Pipedrive label is typed by a person: render it as they typed it. */
            const s = el('span', 'crm-chip', String(name || ''));
            const c = crmLabelColor(name);
            if (/^#/.test(c)) { s.style.background = c + '22'; s.style.color = 'color-mix(in srgb, ' + c + ' 80%, var(--ink))'; }
            else { s.style.background = 'var(--surface-sunken)'; s.style.color = 'var(--text-secondary)'; }
            return s;
        }
        function crmUname(uid) {
            if (!uid) return '';
            const t = ((crmCache && crmCache.team) || []).find(u => u.uid === uid);
            return (t && t.name) || ((crmCache && crmCache.names) || {})[uid] || '';
        }
        function crmMe() { return (teamMe && (teamMe.sub || teamMe.id)) || ''; }
        function crmMulti() { return ((crmCache && crmCache.team) || []).length > 1; }

        function showCRMView() {
            if (crmCache) { renderCRM(); crmMaybeRefresh(); return; }
            loadCRM();
        }
        async function loadCRM() {
            const box = $('crm-content'); box.innerHTML = '';
            const t = el('div', 'thinking'); t.append(loader(), el('span', null, 'Opening the sales desk…'));
            box.append(t);
            try {
                const r = await api('/api/crm/board', {});
                crmCache = r.crm; crmRev = r.rev || ''; crmLoadedAt = Date.now();
                renderCRM();
            } catch (e) {
                box.innerHTML = '';
                box.append(el('div', 'msg error', e.message || 'Could not load the CRM.'));
            }
        }
        /* A colleague's edits must arrive without anyone pressing anything:
           coming back to the tab (or just leaving it open) quietly refetches
           once the copy is over a minute old. No spinner, no scroll jump. */
        async function crmMaybeRefresh() {
            if (!crmCache || Date.now() - crmLoadedAt < 60000) return;
            if (!document.querySelector('#view-crm.active') || document.hidden) return;
            /* .show, not mere existence: the settings modal's overlay is
               always in the DOM, and matching it made this a no-op forever. */
            if (document.querySelector('.modal-overlay.show')) return;
            /* Nor under someone typing in the tab's search: the repaint rebuilt
               the input, focus went and the last keystrokes with it. Checked
               again when the answer lands; the new data waits for the next
               paint. The Inbox has always kept this rule. */
            const typing = () => {
                const a = document.activeElement;
                return !!(a && a.closest && a.closest('#crm-content')
                    && (a.tagName === 'INPUT' || a.tagName === 'SELECT' || a.tagName === 'TEXTAREA'));
            };
            if (typing()) return;
            try {
                const r = await api('/api/crm/board', crmRev ? { rev: crmRev } : {});
                crmLoadedAt = Date.now();
                if (r && r.same) {
                    /* Nothing moved. Draw only if the last board that came
                       was never drawn (it arrived under someone's typing),
                       and not one emptied while this poll was out (the
                       Pipedrive import empties it and loads it again). */
                    if (crmCache && crmPaintedRev !== crmRev && !typing()) renderCRM();
                    return;
                }
                crmCache = r.crm; crmRev = r.rev || '';
                if (!typing()) renderCRM();
            } catch (e) { /* stale is better than an error bar mid-work */ }
        }
        document.addEventListener('visibilitychange', () => { if (!document.hidden) crmMaybeRefresh(); });
        setInterval(crmMaybeRefresh, 90000);
        async function crmOp(path, body) {
            /* Every write returns the fresh state, so the UI never guesses. */
            let r;
            try { r = await api(path, body); }
            catch (e) {
                /* What the page shows may have gone ahead of the board (a
                   ticked box, a dragged card): the next poll redraws it, even
                   when it hears that nothing changed. */
                crmPaintedRev = '';
                throw e;
            }
            if (r && r.crm) { crmCache = r.crm; crmRev = r.rev || ''; crmLoadedAt = Date.now(); }
            return r;
        }
        /* The deal's notes and changelog stay out of the board payload at
           imported scale; the modal fetches them on open and after each edit. */
        let crmDealX = { id: null, notes: [], changelog: [], threads: null, mailDays: 60 };
        let crmDealXSeq = 0;
        async function crmFetchDeal(dealId) {
            /* Only the LATEST fetch may land: a slow modal-open response
               arriving after a fresh post-edit one would resurrect the
               pre-edit history - or another deal's entirely. */
            const my = ++crmDealXSeq;
            try {
                const r = await api('/api/crm/deal', { op: 'detail', id: dealId });
                if (my === crmDealXSeq)
                    crmDealX = { id: dealId, notes: r.notes || [], changelog: r.changelog || [],
                                 threads: ('threads' in r) ? (r.threads || []) : null,
                                 mailDays: r.mail_days || 60 };
            } catch (e) {
                if (my === crmDealXSeq) crmDealX = { id: dealId, notes: [], changelog: [], threads: null, mailDays: 60 };
            }
        }
        function crmCSV(name, header, rows) {
            const esc = v => {
                v = String(v == null ? '' : v);
                /* An imported name can be =HYPERLINK(...): a leading formula
                   trigger gets the apostrophe armour, same as the product
                   exporter. A +44 phone number counts - Excel sees a formula. */
                if (/^[=+\-@\t\r]/.test(v)) v = "'" + v;
                /* \r too: rows are joined with CRLF, and a bare CR inside an
                   unquoted field starts a NEW record in Excel, where the
                   leading-character armour above was never applied. */
                return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
            };
            const txt = [header].concat(rows).map(r => r.map(esc).join(',')).join('\r\n');
            const a = document.createElement('a');
            a.href = URL.createObjectURL(new Blob(['\uFEFF' + txt], { type: 'text/csv' }));
            a.download = name; a.click();
            setTimeout(() => URL.revokeObjectURL(a.href), 5000);
        }

        function renderCRM() {
            crmPaintedRev = crmRev;
            const box = $('crm-content');
            /* A re-render must not throw the reader back to the top, or snap
               the board back to stage 1: every op repaints the whole tab. */
            const scroller = box.closest('.scroll') || box.parentElement;
            const keepY = scroller ? scroller.scrollTop : 0;
            const oldBoard = box.querySelector('.crm-board');
            const keepX = oldBoard ? oldBoard.scrollLeft : 0;
            box.innerHTML = '';
            const d = crmCache;
            // The house header every other tab wears: without it the segment bar
            // sat flush under the top bar and the whole tab read as unfinished.
            /* One line; the amber and red key waits behind the title's info
               button, word for word (copy plan, CRM #1). pageHead puts Beta by
               the title, as for every tab in BETA_TABS. */
            /* Pipedrive import waits in the header's More menu, master only
               (12 Oct 2026, OPS-22): it was a link at the far end of the tab
               row, and opened as a card on all five tabs. */
            const heads = [];
            if (!teamMe || teamMe.role === 'master') {
                const more = textButton(null, { small: true }); more.type = 'button';
                more.append(document.createTextNode('More'), ico(I.chevDown));
                more.onclick = () => dropMenu(more, [{ label: 'Pipedrive import', icon: I.download, onClick: openPipedriveImport }]);
                heads.push(more);
            }
            box.append(pageHead({ view: 'crm', title: 'CRM', line: 'Deals, activities and contacts for the sales desk.', actions: heads,
                info: infoButton('About the CRM', { title: 'CRM', body: 'Every open deal '
                    + 'should carry a next activity; cards wearing the amber warning are the ones '
                    + 'with nothing scheduled, and a red edge means a deal has sat untouched too long.' }) }));
            const count = (n) => n > 0 ? el('span', 'crm-badge', String(n)) : null;
            const seg = tabStrip([{ key: 'leads', label: 'Leads', extra: count(d.new_leads) }, ['deals', 'Deals'],
                                  { key: 'activities', label: 'Activities', extra: count(d.badge) },
                                  ['contacts', 'Contacts'], ['insights', 'Insights']],
                                 crmSeg, (k) => { crmSeg = k; renderCRM(); }, { label: 'CRM sections' });
            box.append(seg);
            /* Only the board earns 1600px; everything else keeps the house
               measure, or five stat cards stretch into near-empty bands. */
            /* Each segment declares its own width. Deals is a board, contacts
               and activities are lists that earn the room, leads is a short
               form and insights is a set of charts that reads best measured. */
            const host = el('div', 'crm-seg crm-seg-' + crmSeg);
            box.append(host);
            if (crmSeg === 'deals') renderCRMDeals(host);
            else if (crmSeg === 'activities') renderCRMActivities(host);
            else if (crmSeg === 'contacts') renderCRMContacts(host);
            else if (crmSeg === 'leads') renderCRMLeads(host);
            else renderCRMInsights(host);
            if (scroller) scroller.scrollTop = keepY;
            const newBoard = box.querySelector('.crm-board');
            if (newBoard) newBoard.scrollLeft = keepX;
        }

        /* Moving off Pipedrive, as a window from More: the survey reads and
           writes nothing, to either system, so it is safe to press at any time.
           Its X is what Hide was. */
        function openPipedriveImport() {
            const m = sheetModal('Pipedrive import');
            m.body.append(el('p', 'card-sub', 'Reads your Pipedrive account and writes nothing, to either system.'));
            const row = el('div', 'lbl-toolbar');
            const go = textButton('Look at my Pipedrive', { small: true }); go.type = 'button';
            const out = el('div', 'pd-out');
            go.onclick = () => runPipedriveSurvey(out, go);
            row.append(go);
            m.body.append(row, out);
            return m;
        }
        async function runPipedriveSurvey(host, btn) {
            btn.disabled = true; btn.textContent = 'Reading\u2026';
            host.innerHTML = '';
            const wait = el('div', 'thinking');
            wait.append(loader(), el('span', null,
                'Counting deals, people, activities and custom fields. This can take a minute '
                + 'on a big account.'));
            host.append(wait);
            let r;
            try { r = await api('/api/crm/pipedrive', {}); }
            catch (e) {
                host.innerHTML = '';
                host.append(el('div', 'msg error', e.message || 'Could not read Pipedrive.'));
                btn.disabled = false; btn.textContent = 'Look at my Pipedrive';
                return;
            }
            btn.disabled = false; btn.textContent = 'Look at my Pipedrive again';
            host.innerHTML = '';
            const acc = r.account || {};
            host.append(el('div', 'crm-sub', 'Connected to ' + (acc.company || 'Pipedrive')
                + ' as ' + (acc.name || '?') + (acc.admin ? ' (administrator)' : ' (not an administrator)')
                + (acc.currency ? '  ·  default currency ' + acc.currency : '')));
            (r.warnings || []).forEach(w => host.append(el('div', 'msg error', w)));
            const c = r.counts || {};
            const grid = el('div', 'lia-grid');
            const stat = (label, n, warn) => {
                const b = el('div', 'lia-card');
                b.append(el('div', 'lia-k', label + (warn ? ' (at least)' : '')));
                b.append(el('div', 'lia-v', String(n == null ? '?' : n)));
                grid.append(b);
            };
            stat('Deals', c.deals, !c.deals_complete);
            stat('Archived deals', c.archived_deals, !c.archived_complete);
            stat('People', c.persons, !c.persons_complete);
            stat('Organisations', c.organizations, !c.orgs_complete);
            stat('Activities', c.activities, !c.activities_complete);
            stat('Leads', c.leads, !c.leads_complete);
            stat('Archived leads', c.archived_leads, !c.archived_leads_complete);
            stat('Pipelines', c.pipelines);
            stat('Users', c.users);
            host.append(grid);
            const section = (title, rows) => {
                if (!rows.length) return;
                host.append(el('div', 'disp-subhead', title));
                /* The house two-column data table, not the file browser's rows. */
                const wrap = el('div', 'ktable-wrap');
                const tb = el('table', 'ktable');
                const tbody = el('tbody');
                rows.forEach(([a, b]) => {
                    const tr = el('tr');
                    tr.append(el('td', 'kw', a), el('td', null, b));
                    tbody.append(tr);
                });
                tb.append(tbody); wrap.append(tb); host.append(wrap);
            };
            section('Pipelines', (r.pipelines || []).map(p =>
                [p.name, p.deals + ' deals  ·  ' + p.stages + ' stages']));
            section('Custom fields on deals', (r.custom_fields || {}).deals
                ? r.custom_fields.deals.filter(f => f.used_on).map(f =>
                    [f.name, 'on ' + f.used_on + ' deals  ·  ' + f.type
                     + (f.options ? '  ·  ' + f.options + ' options' : '')]) : []);
            section('Custom fields on people', (r.custom_fields || {}).persons
                ? r.custom_fields.persons.filter(f => f.used_on).map(f =>
                    [f.name, 'on ' + f.used_on + ' people  ·  ' + f.type]) : []);
            section('Activity types in use', (r.activity_types || [])
                .filter(t => t.used).map(t => [t.name, t.used + ' activities']));
            section('Who owns the deals', (r.users || []).filter(u => u.deals)
                .map(u => [u.name + (u.active ? '' : ' (inactive)'), u.deals + ' deals']));
            const cur = Object.entries(r.currencies || {}).filter(([k, v]) => k && v);
            section('Currencies', cur.map(([k, v]) => [k, v + ' deals']));
            const st = Object.entries(r.deal_status || {}).filter(([k]) => k);
            section('Deal status', st.map(([k, v]) => [k, String(v)]));
            /* The survey is only useful if it can be handed to somebody. This
               copies the SHAPE of the account, never its contents: counts,
               field names, pipeline names and who owns how much. No deal
               titles, no customer names, no email addresses. */
            const copy = textButton();
            copy.style.marginTop = 'var(--sp-2-5)';
            copy.append(ico(I.copy), document.createTextNode('Copy summary'));
            copy.onclick = async () => {
                const L = [];
                L.push('Pipedrive survey');
                L.push('Account: ' + (acc.company || '?') + ' | token belongs to '
                    + (acc.name || '?') + (acc.admin ? ' (admin)' : ' (not an admin)')
                    + ' | default currency ' + (acc.currency || '?'));
                L.push('Counts: deals ' + c.deals + (c.deals_complete ? '' : '+')
                    + ', archived ' + c.archived_deals + (c.archived_complete ? '' : '+')
                    + ', people ' + c.persons + (c.persons_complete ? '' : '+')
                    + ', orgs ' + c.organizations + (c.orgs_complete ? '' : '+')
                    + ', activities ' + c.activities + (c.activities_complete ? '' : '+')
                    + ', leads ' + c.leads + ', archived leads ' + c.archived_leads
                    + (c.archived_leads_complete ? '' : '+') + ', pipelines ' + c.pipelines
                    + ', users ' + c.users);
                (r.pipelines || []).forEach(p => L.push('Pipeline: ' + p.name + ', '
                    + p.deals + ' deals, ' + p.stages + ' stages'));
                ((r.custom_fields || {}).deals || []).filter(f => f.used_on).forEach(f =>
                    L.push('Deal field: ' + f.name + ' (' + f.type + ') on ' + f.used_on + ' deals'));
                ((r.custom_fields || {}).persons || []).filter(f => f.used_on).forEach(f =>
                    L.push('Person field: ' + f.name + ' (' + f.type + ') on ' + f.used_on + ' people'));
                (r.activity_types || []).filter(t => t.used).forEach(t =>
                    L.push('Activity type: ' + t.name + ' x' + t.used));
                (r.users || []).filter(u => u.deals).forEach(u =>
                    L.push('Owner: ' + u.name + ', ' + u.deals + ' deals'));
                cur.forEach(([k, v]) => L.push('Currency: ' + k + ' x' + v));
                st.forEach(([k, v]) => L.push('Status: ' + k + ' x' + v));
                (r.warnings || []).forEach(w => L.push('Warning: ' + w));
                const txt = L.join('\n');
                try { await navigator.clipboard.writeText(txt); toastOk('Copied. Paste it to Claude.'); }
                catch (e) {
                    const ta = document.createElement('textarea');
                    ta.className = 'mail-draft-text'; ta.rows = 12; ta.value = txt;
                    host.append(el('div', 'crm-sub', 'Could not copy automatically. '
                        + 'Select the text below and copy it.'), ta);
                    ta.select();
                }
            };
            host.append(copy);
            /* The import lives behind the survey deliberately: nobody should
               reach it without first seeing what is in the account. */
            const imp = textButton();
            imp.style.cssText = 'margin-top:var(--sp-2-5);margin-left:var(--sp-2)';
            imp.textContent = 'Preview the import';
            imp.onclick = () => runPipedriveImport(host, imp, false);
            host.append(imp);
        }

        async function runPipedriveImport(host, btn, go) {
            btn.disabled = true;
            btn.textContent = go ? 'Importing\u2026' : 'Reading Pipedrive\u2026';
            const out = el('div', 'crm-focus');
            out.style.marginTop = 'var(--sp-2-5)';
            out.append((() => { const t = el('div', 'thinking');
                t.append(loader(), el('span', null, go
                    ? 'Copying it in. Do not close this tab.'
                    : 'Working out exactly what would change. Nothing is being written.'));
                return t; })());
            host.append(out);
            let r;
            try { r = await api('/api/crm/import', go ? { go: true } : {}); }
            catch (e) {
                out.innerHTML = '';
                out.append(el('div', 'msg error', e.message || 'The import could not run.'));
                btn.disabled = false;
                btn.textContent = go ? 'Import it for real' : 'Preview the import';
                return;
            }
            out.innerHTML = '';
            const rep = r.report || {};
            out.append(el('div', 'disp-subhead', go ? 'Imported' : 'What the import would do'));
            const line = (label, o, unit) => {
                const row = el('div', 'crm-sub');
                row.textContent = label + ': ' + (o.new || 0) + ' new'
                    + (o.updated ? ', ' + o.updated + ' updated' : '')
                    + (unit ? ' ' + unit : '');
                out.append(row);
            };
            line('Stages', rep.stages || {});
            line('Organisations', rep.orgs || {});
            line('People', rep.persons || {});
            line('Deals', rep.deals || {});
            line('Activities', rep.activities || {});
            out.append(el('div', 'crm-sub', 'Notes: ' + ((rep.notes || {}).added || 0)
                + (rep.custom_values ? '  ·  Custom field values: ' + rep.custom_values : '')));
            const kept = rep.kept || {};
            if ((kept.deals || 0) + (kept.persons || 0) + (kept.orgs || 0)) {
                out.append(el('div', 'crm-sub', 'Left untouched, because they were typed in here: '
                    + (kept.deals || 0) + ' deals, ' + (kept.persons || 0) + ' people, '
                    + (kept.orgs || 0) + ' organisations'));
            }
            const ke = rep.kept_edited || {};
            const keN = (ke.deals || 0) + (ke.persons || 0) + (ke.orgs || 0) + (ke.activities || 0);
            if (keN) {
                out.append(el('div', 'crm-sub', 'Kept as edited here since the last import '
                    + '(the import never reverts your work): ' + (ke.deals || 0) + ' deals, '
                    + (ke.persons || 0) + ' people, ' + (ke.orgs || 0) + ' organisations, '
                    + (ke.activities || 0) + ' activities'));
            }
            /* Counts only: the whole point is that nobody's name is shown. */
            const er = rep.erased || {};
            if ((er.people || 0) + (er.scrubbed || 0)) {
                out.append(el('div', 'crm-sub', 'People erased on request stay out: '
                    + (er.people ? er.people + (er.people === 1 ? ' contact' : ' contacts') + ' in Pipedrive not brought back, ' : '')
                    + (er.scrubbed || 0) + (er.scrubbed === 1 ? ' deal, task or note' : ' deals, tasks and notes')
                    + ' with their details taken out.'));
            }
            const nm = r.not_migrated || {};
            const losses = [];
            if (nm.files) losses.push(nm.files + ' files and attachments stay in Pipedrive');
            if (nm.products) losses.push(nm.products + ' products are not brought across');
            if (nm.extra_labels_dropped) losses.push(nm.extra_labels_dropped
                + ' deals carry a second label; only the first comes across');
            Object.entries(nm.activity_types_flattened || {}).forEach(([k, v]) =>
                losses.push(v + ' "' + k + '" activities become tasks'));
            losses.forEach(l => out.append(el('div', 'msg error', l)));
            (rep.problems || []).forEach(pb => out.append(el('div', 'msg error', pb)));
            btn.disabled = false;
            if (go) {
                btn.textContent = 'Import again';
                toastOk('Imported. The CRM tab now holds your Pipedrive data.');
                crmCache = null; crmRev = '';
                loadCRM();
                return;
            }
            btn.textContent = 'Preview again';
            const doIt = textButton('Import it for real', { kind: 'primary' });
            doIt.style.marginTop = 'var(--sp-2-5)';
            doIt.onclick = async () => {
                if (!(await uiConfirm('Copy ' + ((rep.deals || {}).new || 0) + ' deals, '
                    + ((rep.persons || {}).new || 0) + ' people and '
                    + ((rep.orgs || {}).new || 0) + ' organisations into Reactor?\n\n'
                    + 'A backup is taken first. Anything typed into Reactor by hand is left '
                    + 'alone, and running this again later updates rather than duplicates.',
                    { title: 'Copy from Pipedrive', okText: 'Copy them' }))) return;
                doIt.remove();
                runPipedriveImport(host, btn, true);
            };
            out.append(doIt);
        }

        /* ---------------- deals: board and list ---------------- */
        function crmVisibleDeals() {
            const q = crmQ.toLowerCase();
            return Object.values(crmCache.deals).filter(x => {
                /* Archived means gone from the pipeline, as it does in
                   Pipedrive: otherwise the back catalogue sits in the columns
                   and inflates the open pipeline total. It has its own filter. */
                if (crmStatus === 'archived') { if (!x.archived) return false; }
                else if (x.archived && crmStatus !== 'all') return false;
                else if (crmStatus !== 'all' && crmStatus !== 'archived' && x.status !== crmStatus) return false;
                if (crmLabelF && x.label !== crmLabelF) return false;
                if (crmOwnerF && (x.owner || '') !== crmOwnerF) return false;
                return matchQ(x, q);
            });
        }
        function matchQ(x, q) {
            if (!q) return true;
            const stages = {}; crmCache.stages.forEach(s => stages[s.id] = s.name);
            return (x.title + ' ' + crmWho(x) + ' ' + (x.label || '') + ' '
                    + (stages[x.stage_id] || '') + ' ' + (x.value || '')
                    + ' ' + Object.values(x.custom || {}).join(' ')).toLowerCase().includes(q);
        }
        function renderCRMDeals(host) {
            const d = crmCache;
            /* One card holding the lot, the way the contacts tab beside it is
               built and the way the reference builds every list page: a counted
               title and a line saying what it is, the two actions on the right
               of the header, the search and the filters on a toolbar under it,
               then the board or the list. This row used to sit bare on the page
               background, so the two tabs of one view read as two pages. */
            const card = el('div', 'card');
            const head = el('div', 'card-head');
            /* The title counts what the status filter shows ('3 won deals',
               '0 in the bin'), not every deal in the store. */
            const dealsTitle = el('h3', 'card-title');
            const retitle = () => {
                const DEAL_NOUN = { open: 'open deal', won: 'won deal', lost: 'lost deal', all: 'deal', archived: 'archived deal' };
                if (crmStatus === 'bin') { dealsTitle.textContent = (d.trash || 0) + ' in the bin'; return; }
                const n = crmVisibleDeals().length, noun = DEAL_NOUN[crmStatus] || 'deal';
                dealsTitle.textContent = n.toLocaleString() + ' ' + noun + (n === 1 ? '' : 's');
            };
            head.append(dealsTitle);
            const act = el('div', 'card-act');
            const add = textButton(null, { kind: 'primary', small: true }); add.append(ico(I.plus), document.createTextNode('Deal'));
            add.onclick = () => crmDealForm();
            const stagesBtn = textButton(null, { small: true }); stagesBtn.append(ico(I.settings), document.createTextNode('Pipeline'));
            stagesBtn.onclick = crmStageEditor;
            /* The way OUT matters when the way in was a migration: the data is
               the user's, and a spreadsheet is the lingua franca. It sits on
               the header rail at the header's own size, where the contacts tab
               keeps the identical button - it used to be a 32px, 14px button
               alone at the bottom-left of the list, which made one action wear
               two homes and two scales across two tabs of one view. */
            const exp = textButton(null, { small: true });
            exp.append(ico(I.download), document.createTextNode('Export CSV'));
            exp.onclick = () => crmDealsCSV(crmVisibleDeals());
            act.append(exp, stagesBtn, add);
            head.append(act);
            card.append(head);
            /* Every filter goes back to page one: a narrower list with page 6
               still showing is an empty table that looks like lost data. */
            const q = tableSearch('Search deals…', crmQ, (v) => { crmQ = v; crmDealsPage = 1; paint(); });
            const st = el('select', 'lbl-size');
            st.setAttribute('aria-label', 'Deal status');
            [['open', 'Open deals'], ['won', 'Won deals'], ['lost', 'Lost deals'],
             ['all', 'Everything'], ['archived', 'Archived'],
             ['bin', 'Bin' + (d.trash ? ' (' + d.trash + ')' : '')]]
                .forEach(([v, l]) => { const o = el('option', null, l); o.value = v; if (crmStatus === v) o.selected = true; st.append(o); });
            st.onchange = () => { crmStatus = st.value; crmDealsPage = 1; paint(); };
            let lf = null, of = null;
            if ((d.labels || []).length) {
                lf = el('select', 'lbl-size');
                lf.setAttribute('aria-label', 'Filter by label');
                lf.append(new Option('Any label', ''));
                d.labels.forEach(l => lf.append(new Option(l, l)));
                lf.value = crmLabelF;
                lf.onchange = () => { crmLabelF = lf.value; crmDealsPage = 1; paint(); };
            }
            if (crmMulti()) {
                of = el('select', 'lbl-size');
                of.setAttribute('aria-label', 'Filter by owner');
                of.append(new Option('Everyone', ''));
                d.team.forEach(u => of.append(new Option(u.name || u.uid, u.uid)));
                of.value = crmOwnerF;
                of.onchange = () => { crmOwnerF = of.value; crmDealsPage = 1; paint(); };
            }
            /* Board and list are two views of the same rows, so the switch sits
               on the right of the toolbar as the inbox's does, and on the same
               segmented control as the tabs above it rather than a second one
               that reads a hair differently. */
            /* The board only ever shows open deals, so under any other status
               List is what is drawn and what is marked, and Board says why it
               cannot be chosen. */
            const view = segmented([['board', 'Board'], ['list', 'List']], crmDealsMode,
                                   (k) => { crmDealsMode = k; crmDealsPage = 1; renderCRM(); }, { label: 'View' });
            const viewBtns = { board: view.querySelector('[data-k="board"]'), list: view.querySelector('[data-k="list"]') };
            const syncView = () => {
                const boardOk = crmStatus === 'open';
                const shown = boardOk ? crmDealsMode : 'list';
                viewBtns.board.disabled = !boardOk;
                viewBtns.board.title = boardOk ? '' : 'The board shows open deals';
                Object.keys(viewBtns).forEach(k => { viewBtns[k].classList.toggle('on', k === shown); viewBtns[k].setAttribute('aria-pressed', String(k === shown)); });
            };
            card.append(tableTools([q, st, lf, of], [view]));
            const paintHost = el('div'); card.append(paintHost);
            host.append(card);
            function paint() {
                paintHost.innerHTML = '';
                retitle(); syncView();
                const bin = crmStatus === 'bin';
                const board = !bin && crmDealsMode === 'board' && crmStatus === 'open';
                /* The table meets the card's edge, as the reference's does: its
                   rows take the 16px gutter from their own cells, so it needs
                   no second bordered box inside the card's. The board keeps the
                   card's padding - it is a row of columns, not a table. */
                paintHost.className = (bin || board) ? '' : 'card-bleed';
                /* The bin is not a filtered pipeline, so there is nothing for
                   the export to write: it says so rather than handing over an
                   empty file. */
                exp.disabled = bin;
                exp.title = bin ? 'Nothing to export from the bin' : '';
                if (bin) paintBin(paintHost);
                else if (board) paintBoard(paintHost);
                else paintList(paintHost);
            }
            paint();
        }
        function paintBin(host) {
            /* The delete confirm promises 30 days of restore; this is where
               that promise is kept. */
            const items = crmCache.trash_items || [];
            if (!items.length) { host.append(el('div', 'empty', 'The bin is empty.')); return; }
            host.append(el('p', 'field-help', 'Deleted deals sit here for 30 days, then go for good.'));
            items.forEach(t => {
                const row = el('div', 'lbl-row');
                row.append(el('div', 'lia-name', t.title || 'Untitled'));
                const mid = el('div', 'lbl-who');
                mid.append(el('span', 'sub', crmMoney(t.value) + ' · deleted ' + fmtDate(t.deleted_at)));
                row.append(mid);
                const back = textButton('Restore');
                back.onclick = async () => {
                    try { await crmOp('/api/crm/deal', { op: 'restore', id: t.id }); renderCRM(); }
                    catch (e) { toastError(e.message); }
                };
                row.append(back);
                host.append(row);
            });
        }
        function paintBoard(host) {
            const d = crmCache;
            const board = el('div', 'crm-board crm-pipeline');
            if (!(d.stages || []).length) board.append(el('div', 'empty', 'No pipeline stages are set up yet.'));
            const rank = { overdue: 0, today: 1, none: 2, future: 3 };
            const deals = crmVisibleDeals().filter(x => x.status === 'open');
            d.stages.forEach(s => {
                const col = el('div', 'crm-col');
                const inStage = deals.filter(x => x.stage_id === s.id)
                    .sort((a, b) => (rank[a.activity_state] - rank[b.activity_state])
                        || String(a.next_activity || '9999').localeCompare(String(b.next_activity || '9999')));
                const total = inStage.reduce((n, x) => n + (x.value || 0), 0);
                const weighted = inStage.reduce((n, x) => n + (x.weighted_value || 0), 0);
                const cn = el('div', 'crm-col-name', s.name); cn.title = s.name; col.append(cn);
                // The Pipedrive header line: "sum · N deals", weighted shown only
                // when a probability under 100 is in play.
                col.append(el('div', 'crm-col-sum', crmMoney(total) + ' · ' + inStage.length
                    + (inStage.length === 1 ? ' deal' : ' deals')
                    + (Math.round(weighted) !== Math.round(total) ? ' · weighted ' + crmMoney(weighted) : '')));
                col.dataset.stage = s.id;
                col.addEventListener('dragover', e => { e.preventDefault(); col.classList.add('dragover'); });
                col.addEventListener('dragleave', () => col.classList.remove('dragover'));
                col.addEventListener('drop', async e => {
                    e.preventDefault(); col.classList.remove('dragover');
                    const id = e.dataTransfer.getData('text/deal');
                    if (!id || (crmCache.deals[id] || {}).stage_id === s.id) return;
                    try { await crmOp('/api/crm/deal', { op: 'move', id: id, stage_id: s.id }); renderCRM(); }
                    catch (err) { toastError(err.message); }
                });
                inStage.forEach(x => col.append(crmCard(x)));
                const qa = el('button', 'crm-col-add'); qa.append(ico(I.plus), document.createTextNode('Deal'));
                qa.onclick = () => crmDealForm(null, s.id);
                col.append(qa);
                board.append(col);
            });
            if (!deals.length && !crmQ && !crmLabelF && !crmOwnerF) {
                /* A brand-new desk gets its bearings before five empty columns. */
                /* One line and the two ways on (copy plan, CRM #5). Neither is a
                   second primary: the card head's '+ Deal' is the one. */
                const acts = el('div', 'act-row');
                const nd = textButton(); nd.type = 'button'; nd.append(ico(I.plus), document.createTextNode('Deal'));
                nd.onclick = () => crmDealForm();
                const pl = textButton(); pl.type = 'button'; pl.append(ico(I.settings), document.createTextNode('Pipeline'));
                pl.onclick = crmStageEditor;
                acts.append(nd, pl);
                host.append(emptyState({ icon: I.briefcase, text: 'No deals yet.', action: acts }));
            }
            host.append(board);
            if (!deals.length && (crmQ || crmLabelF || crmOwnerF)) {
                host.append(el('div', 'empty', 'No open deals match those filters.'));
            }
            host.append(crmDropbar());
        }
        function crmCard(x) {
            const card = el('div', 'crm-card' + (x.rotten ? ' rotten' : ''));
            card.draggable = true;
            card.title = x.rotten ? 'This deal has sat untouched past the stage limit' : '';
            card.addEventListener('dragstart', e => {
                e.dataTransfer.setData('text/deal', x.id);
                document.querySelector('.crm-dropbar').classList.add('show');
            });
            card.addEventListener('dragend', () => document.querySelector('.crm-dropbar').classList.remove('show'));
            card.append(el('div', 'crm-card-t', x.title));
            const who = crmWho(x);
            if (who) card.append(el('div', 'crm-card-who', who));
            const bot = el('div', 'crm-card-bot');
            bot.append(el('span', 'crm-card-val', crmMoney(x.value)));
            /* The label by its name, as the deal window shows it: an unnamed
               red dot on the board read as the 'untouched too long' red. */
            if (x.label) bot.append(crmChip(x.label));
            if (crmMulti() && x.owner && x.owner !== crmMe()) {
                const ini = (crmUname(x.owner) || '?').trim().split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase();
                const av = el('span', 'crm-av', ini);
                av.title = crmUname(x.owner);
                bot.append(av);
            }
            const ai = el('span', 'crm-ai ' + x.activity_state);
            ai.append(ico(x.activity_state === 'none' ? I.warning : I.send));
            ai.title = x.activity_state === 'none' ? 'No next activity scheduled'
                : x.activity_state === 'overdue' ? 'Next activity is overdue: ' + fmtDate(x.next_activity)
                : x.activity_state === 'today' ? 'Next activity is due today'
                : 'Next activity ' + fmtDate(x.next_activity);
            bot.append(ai);
            card.append(bot);
            card.onclick = () => crmDealModal(x.id);
            card.dataset.focusKey = 'deal-' + x.id;   /* the board is redrawn as a deal closes: focus finds the new card */
            /* A div because it has to be draggable between columns, so it gets
               the keyboard path a button would have given it for free. The whole
               board was otherwise mouse-only. */
            card.setAttribute('role', 'button');
            card.tabIndex = 0;
            card.setAttribute('aria-label', x.title + ', ' + crmMoney(x.value)
                + (x.activity_state === 'none' ? ', no next activity scheduled'
                   : x.activity_state === 'overdue' ? ', next activity overdue' : ''));
            card.onkeydown = (e) => {
                if (e.target !== card) return;
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); crmDealModal(x.id); }
            };
            return card;
        }
        function crmDropbar() {
            /* Exists only mid-drag, pinned to the bottom: WON, LOST, DELETE. */
            const bar = el('div', 'crm-dropbar');
            [['won', 'Won'], ['lost', 'Lost'], ['delete', 'Delete']].forEach(([k, lab]) => {
                const z = el('div', 'crm-zone ' + k, lab);
                z.addEventListener('dragover', e => { e.preventDefault(); z.classList.add('dragover'); });
                z.addEventListener('dragleave', () => z.classList.remove('dragover'));
                z.addEventListener('drop', async e => {
                    e.preventDefault(); bar.classList.remove('show');
                    const id = e.dataTransfer.getData('text/deal');
                    if (!id) return;
                    try {
                        if (k === 'won') { await crmOp('/api/crm/deal', { op: 'won', id: id }); toastOk('Deal won: ' + crmMoney((crmCache.deals[id] || {}).value) + '.'); }
                        else if (k === 'lost') { crmLostPrompt(id); return; }
                        else {
                            if (!await uiConfirm('Delete this deal? It can be restored for 30 days.', { title: 'Delete deal', okText: 'Delete' })) { renderCRM(); return; }
                            await crmOp('/api/crm/deal', { op: 'delete', id: id });
                        }
                        renderCRM();
                    } catch (err) { toastError(err.message); }
                });
                bar.append(z);
            });
            return bar;
        }
        /* Extracted from the list foot it used to hang off, so the header
           button can export exactly what the filters left whichever view is
           showing. */
        function crmDealsCSV(deals) {
            const stages = {}; crmCache.stages.forEach(s => stages[s.id] = s.name);
            crmCSV('deals.csv',
                ['Title', 'Value', 'Status', 'Stage', 'Person', 'Organisation', 'Label',
                 'Owner', 'Expected close', 'Won', 'Lost', 'Lost reason', 'Created'],
                deals.map(x => [x.title, x.value || 0, x.status + (x.archived ? ' (archived)' : ''),
                    stages[x.stage_id] || '', (crmPerson(x.person_id) || {}).name || '',
                    (crmOrg(x.org_id) || {}).name || '', x.label || '', crmUname(x.owner || ''),
                    x.expected_close || '', (x.won_at || '').slice(0, 10),
                    (x.lost_at || '').slice(0, 10), x.lost_reason || '',
                    (x.created_at || '').slice(0, 10)]));
        }
        function paintList(host) {
            const deals = crmVisibleDeals().sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)));
            if (!deals.length) { host.append(el('div', 'empty', 'No deals match.')); return; }
            const wrap = el('div', 'ktable-wrap'); const tb = el('table', 'ktable crm-table crm-deals-table');
            tb.innerHTML = '<thead><tr><th>Deal</th><th>Contact</th><th class="num">Value</th>'
                + '<th>Stage</th><th>Next activity</th><th>Status</th></tr></thead>';
            const stages = {}; crmCache.stages.forEach(s => stages[s.id] = s.name);
            const tbody = el('tbody');
            const pageCount = Math.max(1, Math.ceil(deals.length / crmDealsSize));
            if (crmDealsPage > pageCount) crmDealsPage = pageCount;
            const from = (crmDealsPage - 1) * crmDealsSize;
            deals.slice(from, from + crmDealsSize).forEach(x => {
                const tr = el('tr', 'crm-list-row');
                /* The same three lines the contacts row and the board card
                   carry: a row whose only action is a click is mouse-only,
                   and this was the one view where that was still true. */
                const openDeal = () => crmDealModal(x.id);
                const dealName = el('td', 'kw', x.title);
                const dob = rowOpener('Open ' + x.title, openDeal); dob.dataset.focusKey = 'deal-row-' + x.id;
                dealName.prepend(dob);
                tr.append(dealName);
                tr.append(el('td', null, crmWho(x)));
                tr.append(el('td', 'num', crmMoney(x.value)));
                tr.append(el('td', null, x.status === 'open' ? (stages[x.stage_id] || '') : ''));
                tr.append(el('td', null, x.next_activity ? fmtDate(x.next_activity)
                    : x.status === 'won' && x.won_at ? 'won ' + fmtDate(x.won_at)
                    : x.status === 'lost' && x.lost_at ? 'lost ' + fmtDate(x.lost_at)
                    : (x.status === 'open' ? 'none scheduled' : '')));
                const stTd = el('td');
                stTd.append(el('span', 'lbl-chip' + (x.status === 'won' ? ' made' : x.status === 'lost' ? ' bad' : ' note'),
                    (x.archived ? 'Archived · ' : '') + cap(x.status)));
                tr.append(stTd);
                opensOnClick(tr, openDeal);
                tbody.append(tr);
            });
            tb.append(tbody); wrap.append(tb); host.append(wrap);
            /* The same pager the contacts table carries, counting what the
               filters left rather than what the store holds. */
            host.append(tablePager({
                total: deals.length, page: crmDealsPage, pageSize: crmDealsSize, noun: 'deals',
                onPage: (n) => { crmDealsPage = n; host.innerHTML = ''; paintList(host); },
                onSize: (n) => { crmDealsSize = n; crmDealsPage = 1; host.innerHTML = ''; paintList(host); },
            }));
        }

        /* ---------------- modal scaffolding ---------------- */
        function crmModal(title) {
            /* The X is the house window's (dialog()); closing redraws the board
               when the CRM is on screen. The action bar starts empty each time
               it is asked for: a deal repaints its own actions. */
            const win = dialog({ title: title, size: 'disp-modal',
                onClose: () => { if (document.querySelector('#view-crm.active')) renderCRM(); } });
            const foot = () => { const f = win.foot(); f.innerHTML = ''; return f; };
            return { body: win.body, close: win.close, head: win.head, foot: foot };
        }
        function crmField(host, label, input) {
            const w = formField(label, null, { cls: 'disp-addr-f' });
            w.append(input);
            host.append(w); return input;
        }
        function crmText(val, ph) {
            const i = document.createElement('input');
            i.type = 'text'; i.className = 'disp-text'; i.value = val || ''; i.placeholder = ph || '';
            return i;
        }
        function crmTypeahead(input, getRows, opts) {
            /* A datalist with 1,951 people in it builds 1,951 nodes every time
               a form opens. This builds eight, as typed. getRows(q) returns
               [{name, sub}] - picking one puts the name in the input.
               opts.pick(r) overrides what picking writes, for a field whose
               text is not a name: the mail To line holds addresses, and
               several of them. The default is what the CRM forms have always
               had, so they pass two arguments and are untouched. */
            const o = opts || {};
            const write = o.pick || ((r) => { input.value = r.name; });
            const wrap = el('div', 'crm-ta');
            input.autocomplete = 'off';
            input.setAttribute('role', 'combobox');
            input.setAttribute('aria-autocomplete', 'list');
            input.setAttribute('aria-expanded', 'false');
            wrap.append(input);
            const drop = el('div', 'crm-ta-drop'); drop.style.display = 'none';
            drop.setAttribute('role', 'listbox');
            wrap.append(drop);
            /* The row the arrow keys are sitting on. -1 means the keyboard has
               not moved yet, so a plain Enter still means whatever Enter meant
               before the dropdown appeared. */
            let hi = -1, shown = [];
            function open() { return drop.style.display !== 'none'; }
            function hide() {
                drop.style.display = 'none';
                input.setAttribute('aria-expanded', 'false');
                hi = -1;
            }
            function mark() {
                [...drop.children].forEach((b, i) => {
                    b.classList.toggle('on', i === hi);
                    b.setAttribute('aria-selected', i === hi ? 'true' : 'false');
                });
                /* Eight rows in a 220px box: the eighth is below the fold. */
                if (hi >= 0) drop.children[hi].scrollIntoView({ block: 'nearest' });
            }
            function take(r) {
                write(r);
                /* WHICH one, not just its name: two contacts can share
                   a name, and a lookup by name later picks a namesake. */
                input.dataset.pickedId = r.id || '';
                hide();
                input.dispatchEvent(new Event('picked'));
            }
            input.addEventListener('input', () => {
                const q = input.value.trim().toLowerCase();
                drop.innerHTML = ''; hi = -1; shown = [];
                if (!q) { hide(); return; }
                const rows = getRows(q).slice(0, 8);
                if (!rows.length) { hide(); return; }
                shown = rows;
                rows.forEach(r => {
                    const b = el('button');
                    b.type = 'button';
                    b.setAttribute('role', 'option');
                    b.setAttribute('aria-selected', 'false');
                    b.append(document.createTextNode(r.name));
                    if (r.sub) b.append(el('div', 'crm-ta-sub', r.sub));
                    b.onmousedown = (e) => {   /* before the input's blur */
                        e.preventDefault();
                        take(r);
                    };
                    drop.append(b);
                });
                drop.style.display = 'block';
                input.setAttribute('aria-expanded', 'true');
            });
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    /* The dropdown, and only the dropdown. Escape is not a way
                       out of anything in this app, and this input sits in a
                       modal holding a half written email to a customer: the key
                       is stopped here so nothing above can act on it. */
                    if (open()) { e.stopPropagation(); hide(); }
                    return;
                }
                if (!open() || !shown.length) return;
                if (e.key === 'ArrowDown') {
                    e.preventDefault();   /* not the caret to the end of the line */
                    hi = (hi + 1) % shown.length; mark(); return;
                }
                if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    hi = (hi <= 0 ? shown.length - 1 : hi - 1); mark(); return;
                }
                /* Swallowed, or the modal behind it submits the half typed
                   address the dropdown was offering to finish. Only with a row
                   highlighted: a plain Enter still means what it always meant. */
                if (e.key === 'Enter' && hi >= 0) {
                    e.preventDefault();
                    take(shown[hi]);
                }
            });
            input.addEventListener('blur', () => setTimeout(hide, 150));
            return wrap;
        }
        function crmPersonRows(q) {
            return Object.values(crmCache.persons)
                .filter(p => (p.name + ' ' + (p.emails || []).join(' ')).toLowerCase().includes(q))
                .sort((a, b) => a.name.localeCompare(b.name))
                .map(p => ({ id: p.id, name: p.name,
                             sub: [(p.emails || [])[0], (crmOrg(p.org_id) || {}).name].filter(Boolean).join(' · ') }));
        }
        function crmOrgRows(q) {
            return Object.values(crmCache.orgs)
                .filter(o => o.name.toLowerCase().includes(q))
                .sort((a, b) => a.name.localeCompare(b.name))
                .map(o => ({ id: o.id, name: o.name, sub: o.address || '' }));
        }
        function crmPicked(input, coll) {
            /* The record the user actually PICKED, when the input still shows
               its name. Name lookups find whichever namesake sorts first. */
            const r = coll[input.dataset.pickedId || ''];
            return (r && r.name.toLowerCase() === input.value.trim().toLowerCase()) ? r : null;
        }

        /* ---------------- add/edit deal ---------------- */
        function crmDealForm(dealId, presetStage) {
            const m = crmModal(dealId ? 'Edit deal' : 'New deal');
            const d = crmCache; const deal = dealId ? d.deals[dealId] : null;
            const grid = el('div', 'disp-addr-grid'); m.body.append(grid);
            /* Person and organisation with inline creation: typing an unknown
               name creates it on save, the signature Pipedrive move. */
            const personIn = crmText(deal && crmPerson(deal.person_id) ? crmPerson(deal.person_id).name : '', 'Type to search or create');
            const orgIn = crmText(deal && crmOrg(deal.org_id) ? crmOrg(deal.org_id).name : '', 'Type to search or create');
            crmField(grid, 'Contact person', crmTypeahead(personIn, crmPersonRows));
            crmField(grid, 'Organisation', crmTypeahead(orgIn, crmOrgRows));
            const titleIn = crmText(deal ? deal.title : '', '');
            let titleTouched = !!deal;
            titleIn.oninput = () => { titleTouched = true; };
            /* The title autofills "<Name> deal" from whoever was linked. */
            function autofill() {
                if (titleTouched) return;
                const src = orgIn.value.trim() || personIn.value.trim();
                titleIn.value = src ? src + ' deal' : '';
            }
            personIn.addEventListener('input', autofill); orgIn.addEventListener('input', autofill);
            personIn.addEventListener('picked', autofill); orgIn.addEventListener('picked', autofill);
            crmField(grid, 'Title', titleIn);
            const valIn = crmText(deal ? String(deal.value) : '', '0');
            valIn.type = 'number'; valIn.min = '0'; valIn.step = '0.01';
            crmField(grid, 'Value (£)', valIn);
            const closeIn = crmText(deal ? deal.expected_close : '', '');
            closeIn.type = 'date';
            crmField(grid, 'Expected close date', closeIn);
            const labSel = el('select', 'disp-text');
            labSel.append(new Option('No label', ''));
            d.labels.forEach(l => labSel.append(new Option(l, l)));
            if (deal && deal.label) labSel.value = deal.label;
            crmField(grid, 'Label', labSel);
            /* Probability: blank inherits the stage's number; a deal-level one
               overrides it, exactly as the weighted pipeline reads it. */
            const probIn = crmText(deal && deal.probability != null ? String(deal.probability) : '', 'stage %');
            probIn.type = 'number'; probIn.min = '0'; probIn.max = '100';
            crmField(grid, 'Win probability %', probIn);
            let ownSel = null;
            if (crmMulti()) {
                ownSel = el('select', 'disp-text');
                d.team.forEach(u => ownSel.append(new Option(u.name || u.uid, u.uid)));
                ownSel.value = (deal && deal.owner) || crmMe();
                if (![...ownSel.options].some(o => o.selected)) ownSel.selectedIndex = 0;
                crmField(grid, 'Owner', ownSel);
            }
            /* Stage picker as the chevron bar, defaulting to the first stage. */
            let stageSel = (deal && deal.stage_id) || presetStage || (d.stages[0] || {}).id;
            const chev = el('div', 'crm-chev');
            function paintChev() {
                chev.innerHTML = '';
                let reached = true;
                d.stages.forEach(s => {
                    const seg = el('div', 'crm-chev-s' + (s.id === stageSel ? ' on' : reached ? ' done' : ''), s.name);
                    if (s.id === stageSel) reached = false;
                    seg.setAttribute('role', 'button'); seg.tabIndex = 0;
                    seg.setAttribute('aria-pressed', s.id === stageSel ? 'true' : 'false');
                    seg.onclick = () => { stageSel = s.id; paintChev(); };
                    seg.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); seg.click(); } });
                    chev.append(seg);
                });
            }
            paintChev();
            m.body.append(chev);
            const bar = m.foot();
            const save = textButton(dealId ? 'Save' : 'Add deal', { kind: 'primary' });
            save.onclick = async () => {
                save.disabled = true;
                try {
                    /* Two rules learned the hard way. The currently linked
                       contact wins while its name is unchanged, because two
                       contacts can share a name and a lookup here silently
                       relinked deals to the wrong namesake. And the lookup runs
                       against crmCache, not the snapshot from when the form
                       opened, so a retry after a failed save finds the contact
                       it already created instead of creating another. */
                    const curP = deal ? crmPerson(deal.person_id) : null;
                    const curO = deal ? crmOrg(deal.org_id) : null;
                    const pn = personIn.value.trim(), on = orgIn.value.trim();
                    let orgId;
                    if (!on) orgId = '';
                    else if (curO && on === curO.name) orgId = deal.org_id;
                    else {
                        const f = crmPicked(orgIn, crmCache.orgs)
                            || Object.values(crmCache.orgs).find(o => o.name.toLowerCase() === on.toLowerCase());
                        orgId = f ? f.id : (await crmOp('/api/crm/contact', { op: 'org_add', name: on })).id;
                    }
                    let personId;
                    if (!pn) personId = '';
                    else if (curP && pn === curP.name) personId = deal.person_id;
                    else {
                        const f = crmPicked(personIn, crmCache.persons)
                            || Object.values(crmCache.persons).find(p => p.name.toLowerCase() === pn.toLowerCase());
                        personId = f ? f.id : (await crmOp('/api/crm/contact', { op: 'person_add', name: pn, org_id: orgId })).id;
                    }
                    const extra = { probability: probIn.value === '' ? '' : probIn.value };
                    if (ownSel) extra.owner = ownSel.value;
                    if (dealId) {
                        await crmOp('/api/crm/deal', { op: 'update', id: dealId, title: titleIn.value.trim(),
                            value: valIn.value, expected_close: closeIn.value, label: labSel.value,
                            person_id: personId, org_id: orgId, ...extra });
                        if (stageSel !== deal.stage_id) await crmOp('/api/crm/deal', { op: 'move', id: dealId, stage_id: stageSel });
                        m.close();
                    } else {
                        const r = await crmOp('/api/crm/deal', { op: 'add', title: titleIn.value.trim(),
                            value: valIn.value, expected_close: closeIn.value, label: labSel.value,
                            person_id: personId, org_id: orgId, stage_id: stageSel, ...extra });
                        if (probIn.value !== '')   /* add() takes owner; probability rides an update */
                            await crmOp('/api/crm/deal', { op: 'update', id: r.id, probability: probIn.value });
                        m.close(); crmDealModal(r.id);
                    }
                } catch (e) { save.disabled = false; toastError(e.message); }
            };
            bar.append(save);
        }

        function crmLostPrompt(dealId) {
            const m = crmModal('Mark as lost');
            m.body.append(el('p', 'field-help', 'The deal keeps its history; the reason feeds Insights.'));
            const sel = el('select', 'disp-text');
            crmCache.lost_reasons.forEach(r => sel.append(new Option(r, r)));
            const grid = el('div', 'disp-addr-grid'); m.body.append(grid);
            crmField(grid, 'Reason', sel);
            const com = crmText('', 'Optional comment');
            crmField(grid, 'Comment', com);
            const bar = m.foot();
            const go = textButton('Mark as lost', { kind: 'primary' });
            go.onclick = async () => {
                go.disabled = true;
                try { await crmOp('/api/crm/deal', { op: 'lost', id: dealId, reason: sel.value, comment: com.value.trim() }); m.close(); }
                catch (e) { go.disabled = false; toastError(e.message); }
            };
            bar.append(go);
        }

        /* ---------------- the deal detail ---------------- */
        function crmDealModal(dealId) {
            const x = crmCache.deals[dealId];
            if (!x) return;
            const m = crmModal(x.title);
            paintDeal(m, dealId);
            /* Notes and history arrive a beat later: they are not in the slim
               board payload, and the modal must open instantly regardless. */
            crmFetchDeal(dealId).then(() => { if (document.body.contains(m.body)) paintDeal(m, dealId); });
        }
        function paintDealFresh(m, dealId) {
            /* After any edit: repaint at once, then again with fresh history. */
            paintDeal(m, dealId);
            crmFetchDeal(dealId).then(() => { if (document.body.contains(m.body)) paintDeal(m, dealId); });
        }
        function paintDeal(m, dealId) {
            const d = crmCache, x = d.deals[dealId];
            if (!x) { m.close(); return; }
            /* A repaint mid-thought must not eat a half-typed note. */
            const oldTa = m.body.querySelector('textarea.lia-chase-body');
            const draft = oldTa ? oldTa.value : '';
            m.body.innerHTML = '';
            /* Status row: value, weighted, chips, won/lost/reopen. */
            const top = el('div', 'lbl-toolbar');
            top.append(el('b', null, crmMoney(x.value)));
            if (x.effective_probability !== 100)
                top.append(el('span', 'crm-sub', x.effective_probability + '% · weighted ' + crmMoney(x.weighted_value)));
            if (x.label) top.append(crmChip(x.label));
            if (x.rotten) top.append(el('span', 'lbl-chip bad', 'Rotting'));
            if (x.archived) top.append(el('span', 'lbl-chip note', 'Archived'));
            if (x.status === 'open') {
                const won = textButton('Won', { kind: 'primary' });
                won.onclick = async () => {
                    try {
                        await crmOp('/api/crm/deal', { op: 'won', id: dealId });
                        toastOk('Deal won: ' + crmMoney(x.value) + '.');
                        paintDealFresh(m, dealId);
                    } catch (e) { toastError(e.message); }
                };
                const lost = textButton('Lost');
                lost.onclick = () => { m.close(); crmLostPrompt(dealId); };
                const edit = textButton(); edit.append(ico(I.edit), document.createTextNode('Edit'));
                edit.onclick = () => { m.close(); crmDealForm(dealId); };
                top.append(won, lost, edit);
            } else {
                const chip = el('span', 'lbl-chip' + (x.status === 'won' ? ' made' : ' bad'), cap(x.status)
                    + (x.status === 'lost' && x.lost_reason ? ': ' + x.lost_reason : ''));
                chip.title = (x.status === 'won' && x.won_at ? 'Won ' + fmtDate(x.won_at) : '')
                    + (x.status === 'lost' && x.lost_at ? 'Lost ' + fmtDate(x.lost_at) : '');
                top.append(chip);
                const re = textButton('Reopen');
                re.onclick = async () => { try { await crmOp('/api/crm/deal', { op: 'reopen', id: dealId }); paintDealFresh(m, dealId); } catch (e) { toastError(e.message); } };
                top.append(re);
            }
            /* The quiet doors: archive (Pipedrive's third outcome) and the
               30-day bin, both reachable by TAP - drag is a desktop luxury. */
            const arch = textButton(x.archived ? 'Unarchive' : 'Archive');
            arch.onclick = async () => {
                try {
                    await crmOp('/api/crm/deal', { op: x.archived ? 'unarchive' : 'archive', id: dealId });
                    paintDealFresh(m, dealId);
                } catch (e) { toastError(e.message); }
            };
            top.append(arch);
            const del = iconButton(I.trash, 'Delete (restorable for 30 days)');
            del.onclick = async () => {
                if (!await uiConfirm('Delete this deal? It can be restored from the Bin for 30 days.',
                                     { title: 'Delete deal', okText: 'Delete' })) return;
                try { await crmOp('/api/crm/deal', { op: 'delete', id: dealId }); m.close(); }
                catch (e) { toastError(e.message); }
            };
            top.append(del);
            m.body.append(top);
            /* The chevron progress bar: click a segment to move stage; frozen
               once the deal is closed. Days in the current stage ride along. */
            let reached = true;
            const chev = el('div', 'crm-chev');
            d.stages.forEach(s => {
                const cls = s.id === x.stage_id ? ' on' : (reached ? ' done' : '');
                const seg = el('div', 'crm-chev-s' + cls + (x.status !== 'open' ? ' frozen' : ''), s.name);
                if (s.id === x.stage_id) reached = false;
                if (x.status === 'open' && s.id !== x.stage_id) {
                    seg.onclick = async () => {
                        try { await crmOp('/api/crm/deal', { op: 'move', id: dealId, stage_id: s.id }); paintDeal(m, dealId); }
                        catch (e) { toastError(e.message); }
                    };
                }
                chev.append(seg);
            });
            m.body.append(chev);
            const inStage = Math.max(0, Math.floor((Date.now() - Date.parse(x.stage_entered_at || x.created_at)) / 86400000));
            const bits = [inStage + (inStage === 1 ? ' day' : ' days') + ' in this stage'];
            if (x.expected_close) bits.push('expected close ' + fmtDate(x.expected_close));
            if (crmMulti() && x.owner && crmUname(x.owner)) bits.push('owned by ' + crmUname(x.owner));
            if (x.source && x.source !== 'Manual') bits.push('from ' + x.source);
            const subLine = el('div', 'crm-sub', bits.join(' · '));
            if (x.mail_thread_id) {
                subLine.append(document.createTextNode(' · '));
                const em = actionLink('miss-open', 'open the email');
                em.onclick = () => { m.close(); setView('mail'); openMailThread(x.mail_thread_id); };
                subLine.append(em);
            }
            m.body.append(subLine);
            /* Who to actually RING: the linked person with dialable numbers.
               A deal modal that shows a name but hides the phone number sends
               the caller back out to the Contacts tab mid-call. */
            const p = crmPerson(x.person_id), o = crmOrg(x.org_id);
            if (p || o) {
                const cc = el('div', 'crm-focus');
                const nameRow = el('div', 'crm-cline');
                nameRow.append(ico(I.users));
                const pa = actionLink('miss-open', [p && p.name, o && o.name].filter(Boolean).join(' · '));
                pa.onclick = () => { m.close(); crmContactModal(p ? 'person' : 'org', (p || o).id); };
                nameRow.append(pa);
                if (p && p.job_title) nameRow.append(el('span', 'crm-sub', p.job_title));
                cc.append(nameRow);
                ((p && p.phones) || []).slice(0, 2).forEach((ph, i) => {
                    const r = el('div', 'crm-cline'); r.append(ico(I.phone));
                    const a = el('a', null, ph); a.href = 'tel:' + ph.replace(/[^+\d]/g, '');
                    r.append(a);
                    const lab = ((p.phone_labels || [])[i] || '');
                    if (lab) r.append(el('span', 'crm-sub', lab));
                    cc.append(r);
                });
                ((p && p.emails) || []).slice(0, 2).forEach((em) => {
                    const r = el('div', 'crm-cline'); r.append(ico(I.mail));
                    const a = el('a', null, em); a.href = 'mailto:' + em.replace(/[?&#\s"'<>\\]/g, '');
                    r.append(a); cc.append(r);
                });
                m.body.append(cc);
            }
            /* The Pipedrive custom fields, editable in place: this data cost a
               migration, it does not get to be invisible. */
            const cust = x.custom || {};
            if (Object.keys(cust).length) {
                const cf = el('div', 'crm-focus');
                cf.append(el('div', 'disp-subhead', 'Details'));
                const grid = el('div', 'crm-cf');
                Object.entries(cust).forEach(([k, v]) => {
                    grid.append(el('div', 'crm-cf-k', k));
                    const inp = document.createElement('input');
                    inp.type = 'text'; inp.className = 'disp-text'; inp.value = v;
                    inp.onchange = async () => {
                        try {
                            await crmOp('/api/crm/deal', { op: 'update', id: dealId,
                                custom: Object.fromEntries([[k, inp.value.trim()]]) });
                            paintDealFresh(m, dealId);
                        } catch (e) { toastError(e.message); }
                    };
                    grid.append(inp);
                });
                cf.append(grid);
                m.body.append(cf);
            }
            /* The email history: every shared-inbox thread with this deal's
               contact, one click from the deal. Reading and replying stay in
               the Inbox, where opening marks the email read. Absent entirely
               for accounts locked out of the mail tab. */
            if (crmDealX.id === dealId && crmDealX.threads !== null
                    && (crmDealX.threads.length || (p && (p.emails || []).length))) {
                const em = el('div', 'crm-focus');
                em.append(el('div', 'disp-subhead', 'Email'));
                if (!crmDealX.threads.length) {
                    em.append(el('div', 'crm-sub', 'Nothing in the shared inbox from '
                        + ((p.emails || [])[0] || 'this contact') + ' in the last '
                        + crmDealX.mailDays + ' days.'));
                } else {
                    crmDealX.threads.forEach(t => {
                        const r = el('div', 'crm-hist-row');
                        const a = actionLink('miss-open', t.subject);
                        if (t.unread) a.style.fontWeight = 'var(--weight-semibold)';
                        a.onclick = () => { m.close(); setView('mail'); openMailThread(t.id); };
                        r.append(a);
                        const bits = [t.msg_count + (t.msg_count === 1 ? ' message' : ' messages'),
                                      fmtDate(t.last_at)];
                        if (t.owner_name) bits.push(t.owner_name);
                        if (t.state === 'done') bits.push('closed');
                        r.append(el('div', 'crm-hist-when', bits.join(' · ')));
                        if (t.snippet) r.append(el('div', 'crm-act-note', t.snippet.slice(0, 140)));
                        em.append(r);
                    });
                }
                m.body.append(em);
            }
            /* Shopify card: live order history for the linked customer. */
            if (p && p.shopify_customer_id) {
                const sc = el('div', 'crm-focus');
                sc.append(el('div', 'disp-subhead', 'Shopify'));
                const line = el('div', 'crm-sub', 'Reading order history…'); sc.append(line);
                api('/api/customer-history', { customer_id: p.shopify_customer_id }).then(h => {
                    line.textContent = '';
                    line.append(document.createTextNode((h.count || 0) + ' orders on record'));
                    const latest = (h.recent || [])[0];
                    if (latest) {
                        line.append(document.createTextNode(' · latest '));
                        line.append(orderA(latest.name, latest.admin_url));
                        line.append(document.createTextNode(' (' + fmtDate(latest.created_at) + ')'));
                    }
                }).catch(() => { sc.remove(); });
                m.body.append(sc);
            }
            /* Composer: a note, or the inline activity scheduler. */
            const comp = el('div', 'crm-focus');
            comp.append(el('div', 'disp-subhead', 'Add'));
            const ta = document.createElement('textarea');
            ta.className = 'lia-chase-body'; ta.rows = 2; ta.placeholder = 'A note about this deal…'; ta.setAttribute('aria-label', 'A note about this deal');
            ta.value = draft;
            comp.append(ta);
            const cbar = el('div', 'disp-actions');
            const noteBtn = textButton('Save note');
            noteBtn.onclick = async () => {
                if (!ta.value.trim()) return;
                try {
                    const text = ta.value.trim();
                    ta.value = '';   /* saved is saved: the draft-keeper must not re-offer it */
                    await crmOp('/api/crm/deal', { op: 'note_add', id: dealId, text: text });
                    paintDealFresh(m, dealId);
                } catch (e) { toastError(e.message); }
            };
            const actBtn = textButton(null, { kind: 'primary' }); actBtn.append(ico(I.cal), document.createTextNode('Schedule activity'));
            actBtn.onclick = () => crmActivityForm({ deal_id: dealId }, () => paintDealFresh(m, dealId));
            cbar.append(actBtn, noteBtn); comp.append(cbar); m.body.append(comp);
            /* Focus: what still needs doing. History below: what happened. */
            const open = Object.values(d.activities)
                .filter(a => a.deal_id === dealId && !a.done)
                .sort((a, b) => String(a.due_date).localeCompare(String(b.due_date)));
            if (open.length) {
                const f = el('div', 'crm-focus');
                f.append(el('div', 'disp-subhead', 'Focus'));
                open.forEach(a => f.append(crmActRow(a, () => paintDealFresh(m, dealId))));
                m.body.append(f);
            }
            const hist = el('div', 'crm-focus');
            hist.append(el('div', 'disp-subhead', 'History'));
            if (crmDealX.id !== dealId) {
                const t = el('div', 'thinking'); t.append(loader(), el('span', null, 'Reading the history…'));
                hist.append(t); m.body.append(hist);
                return;
            }
            const done = Object.values(d.activities).filter(a => a.deal_id === dealId && a.done)
                .map(a => ({ at: a.done_at || a.updated_at, pin: false, node: () => {
                    const r = el('div', 'crm-hist-row');
                    r.append(ico(crmTypeIcon(a.type)), document.createTextNode(' ' + a.subject + ' '));
                    r.append(el('span', 'lbl-chip made', 'Done'));
                    if (a.note) r.append(el('div', 'crm-act-note', a.note));
                    r.append(el('div', 'crm-hist-when', (a.due_date ? 'was due ' + fmtDate(a.due_date) : '')
                        + (a.done_at ? (a.due_date ? ' · ' : '') + 'done ' + fmtDate(a.done_at) : '')));
                    return r; } }));
            const notes = (crmDealX.notes || []).map(n => ({ at: n.at, pin: !!n.pinned, node: () => {
                const r = el('div', 'crm-hist-row' + (n.pinned ? ' pinned' : ''));
                r.append(document.createTextNode(n.text));
                const w = el('div', 'crm-hist-when', fmtDate(n.at));
                const pin = actionLink('miss-open', n.pinned ? 'Unpin' : 'Pin');
                pin.onclick = async () => { try { await crmOp('/api/crm/deal', { op: 'note_pin', id: dealId, note_id: n.id }); paintDealFresh(m, dealId); } catch (e) { toastError(e.message); } };
                const del = actionLink('miss-open', 'Delete');
                del.onclick = async () => { try { await crmOp('/api/crm/deal', { op: 'note_del', id: dealId, note_id: n.id }); paintDealFresh(m, dealId); } catch (e) { toastError(e.message); } };
                w.append(document.createTextNode(' · ')); w.append(pin);
                w.append(document.createTextNode(' · ')); w.append(del);
                r.append(w); return r; } }));
            const log = (crmDealX.changelog || []).map(c => ({ at: c.at, pin: false, node: () => {
                const r = el('div', 'crm-hist-row');
                r.append(el('span', 'crm-sub', c.field === 'created' ? 'Deal created'
                    : c.field + ': ' + (c.from || 'none') + ' → ' + (c.to || 'none')));
                r.append(el('div', 'crm-hist-when', fmtDate(c.at)));
                return r; } }));
            /* Pinned notes surface first - that is what pinning is FOR. */
            const rows = done.concat(notes, log).sort((a, b) =>
                (b.pin - a.pin) || String(b.at).localeCompare(String(a.at)));
            if (!rows.length) hist.append(el('div', 'crm-sub', 'Nothing yet.'));
            rows.slice(0, 60).forEach(r => hist.append(r.node()));
            m.body.append(hist);
        }
        function crmActTick(a, refresh) {
            const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = !!a.done;
            cb.setAttribute('aria-label', (a.done ? 'Mark not done: ' : 'Mark done: ') + a.subject);
            cb.onclick = (ev) => ev.stopPropagation();
            cb.onchange = async () => {
                try {
                    const res = await crmOp('/api/crm/activity', { op: a.done ? 'undone' : 'done', id: a.id });
                    refresh();
                    /* The follow-up prompt: completing a deal's LAST open activity
                       opens a fresh scheduler pre-linked to that deal. It nags,
                       it never blocks: closing it is always allowed. */
                    if (res.followup_deal_id) crmActivityForm({ deal_id: res.followup_deal_id, followup: true }, refresh);
                } catch (e) { cb.checked = !!a.done; toastError(e.message); }
            };
            return cb;
        }
        function crmActRow(a, refresh) {
            const r = el('div', 'crm-act-row' + (a.done ? ' done' : ''));
            r.append(crmActTick(a, refresh), ico(crmTypeIcon(a.type)));
            /* Everything except the checkbox opens the editor: moving a call
               to Friday is the single most common activity operation, and it
               used to be impossible without corrupting the history. */
            const mid = el('div', 'crm-mid');
            mid.append(el('div', 'crm-act-sub', a.subject));
            const bits = [];
            if (a.deal_id && crmCache.deals[a.deal_id]) bits.push(crmCache.deals[a.deal_id].title);
            else if (a.person_id && crmPerson(a.person_id)) bits.push(crmPerson(a.person_id).name);
            if (a.due_time) bits.push(a.due_time);
            if (a.location) bits.push(a.location);
            if (crmMulti() && a.assignee && crmUname(a.assignee)) bits.push(crmUname(a.assignee));
            const sub = el('span', 'crm-sub', bits.join(' · '));
            mid.append(sub);
            const preview = a.note_preview || a.note || '';
            if (preview && !a.done) mid.append(el('div', 'crm-act-note', preview));
            mid.onclick = () => crmActivityForm({ id: a.id }, refresh);
            r.append(mid);
            if (a.priority) r.append(el('span', 'crm-prio ' + a.priority, cap(a.priority)));
            r.append(el('span', 'crm-act-due ' + a.state, a.due_date ? fmtDate(a.due_date) : ''));
            return r;
        }

        /* ---------------- activity form: add AND edit ---------------- */
        function crmActivityForm(preset, onDone) {
            const editing = preset.id ? crmCache.activities[preset.id] : null;
            const m = crmModal(editing ? 'Edit activity'
                : preset.followup ? 'Schedule the next activity' : 'Schedule activity');
            if (preset.followup) m.body.append(el('p', 'field-help', 'That was the last open activity. Schedule the next one?'));
            let type = editing ? editing.type : 'call';
            const row = el('div', 'lbl-toolbar');
            const subjIn = crmText(editing ? editing.subject : 'Call', '');
            let subjTouched = !!editing;
            CRM_TYPES.forEach(([k, lab]) => {
                const b = el('button', 'crm-ticon' + (type === k ? ' on' : ''));
                b.append(ico(crmTypeIcon(k))); b.title = lab;
                b.onclick = () => {
                    type = k;
                    row.querySelectorAll('.crm-ticon').forEach(n => n.classList.remove('on'));
                    b.classList.add('on');
                    if (!subjTouched) subjIn.value = lab;   /* the two-click activity */
                };
                row.append(b);
            });
            m.body.append(row);
            subjIn.oninput = () => { subjTouched = true; };
            const grid = el('div', 'disp-addr-grid'); m.body.append(grid);
            crmField(grid, 'Subject', subjIn);
            const dateIn = crmText(editing ? editing.due_date : crmCache.today, ''); dateIn.type = 'date';
            crmField(grid, 'Due date', dateIn);
            const timeIn = crmText(editing ? editing.due_time : '', ''); timeIn.type = 'time';
            crmField(grid, 'Time (optional)', timeIn);
            const prioSel = el('select', 'disp-text');
            [['', 'No priority'], ['high', 'High'], ['medium', 'Medium'], ['low', 'Low']]
                .forEach(([v, l]) => prioSel.append(new Option(l, v)));
            if (editing) prioSel.value = editing.priority || '';
            crmField(grid, 'Priority', prioSel);
            const dealSel = el('select', 'disp-text');
            dealSel.append(new Option('No linked deal', ''));
            Object.values(crmCache.deals).filter(x => x.status === 'open' && !x.archived)
                .forEach(x => dealSel.append(new Option(x.title, x.id)));
            const wantDeal = preset.deal_id || (editing && editing.deal_id);
            if (wantDeal) {
                /* A closed deal is not in the open list, but an activity
                   scheduled FROM its modal must not silently lose the link. */
                if (![...dealSel.options].some(o => o.value === wantDeal)) {
                    const px = crmCache.deals[wantDeal];
                    if (px) dealSel.append(new Option(px.title + ' (' + (px.archived ? 'archived' : px.status) + ')', px.id));
                }
                dealSel.value = wantDeal;
            }
            crmField(grid, 'Deal', dealSel);
            /* Or a person without a deal: chasing a contact is real work too. */
            const perIn = crmText(editing && crmPerson(editing.person_id)
                ? crmPerson(editing.person_id).name : '', 'Type to link a person');
            crmField(grid, 'Person (optional)', crmTypeahead(perIn, crmPersonRows));
            /* The board payload carries only a preview, so the form asks for
               the real note before it can save one back - prefilling from the
               preview would truncate it on the first save. */
            const noteIn = crmText('', 'Optional note');
            if (editing) {
                noteIn.disabled = true;
                noteIn.placeholder = 'Reading the note\u2026';
                api('/api/crm/activity', { op: 'detail', id: editing.id })
                    .then(r => { noteIn.value = r.note || ''; noteIn.disabled = false;
                                 noteIn.placeholder = 'Optional note'; })
                    .catch(() => { noteIn.disabled = false; noteIn.placeholder = 'Optional note'; });
            }
            crmField(grid, 'Note', noteIn);
            let assSel = null;
            if (crmMulti()) {
                assSel = el('select', 'disp-text');
                crmCache.team.forEach(u => assSel.append(new Option(u.name || u.uid, u.uid)));
                assSel.value = (editing && editing.assignee) || crmMe();
                if (![...assSel.options].some(o => o.selected)) assSel.selectedIndex = 0;
                crmField(grid, 'For', assSel);
            }
            let doneNow = null;
            if (!editing) {
                /* Logging a call that already happened is one tick, not
                   add-then-hunt-it-down-and-tick-it. */
                const lw = tickRow('crm-cline');
                doneNow = document.createElement('input'); doneNow.type = 'checkbox';
                lw.append(doneNow, document.createTextNode(' Already done, just logging it'));
                m.body.append(lw);
            }
            const bar = m.foot();
            const save = textButton('Save', { kind: 'primary' });
            save.onclick = async () => {
                save.disabled = true;
                try {
                    const pn = perIn.value.trim();
                    const found = pn ? (crmPicked(perIn, crmCache.persons)
                        || Object.values(crmCache.persons)
                            .find(p => p.name.toLowerCase() === pn.toLowerCase())) : null;
                    const payload = { type: type, subject: subjIn.value.trim(),
                        due_date: dateIn.value, due_time: timeIn.value, priority: prioSel.value,
                        deal_id: dealSel.value, note: noteIn.value.trim(),
                        person_id: found ? found.id : '' };
                    if (assSel) payload.assignee = assSel.value;
                    if (editing) await crmOp('/api/crm/activity', { op: 'update', id: editing.id, ...payload });
                    else await crmOp('/api/crm/activity', { op: 'add', ...payload,
                                                            done: !!(doneNow && doneNow.checked) });
                    m.close(); if (onDone) onDone();
                } catch (e) { save.disabled = false; toastError(e.message); }
            };
            bar.append(save);
            if (editing) {
                const del = textButton('Delete');
                del.onclick = async () => {
                    if (!await uiConfirm('Delete this activity? Done is usually righter: '
                        + 'deleting removes it from the history too.', { title: 'Delete activity', okText: 'Delete' })) return;
                    try { await crmOp('/api/crm/activity', { op: 'delete', id: editing.id }); m.close(); if (onDone) onDone(); }
                    catch (e) { toastError(e.message); }
                };
                bar.append(del);
            }
        }

        /* ---------------- activities segment ---------------- */
        function renderCRMActivities(host) {
            /* Thirteen controls in one wrapping row read as clutter, and a
               bordered list with no header over two bare strips read as a
               draft. The card the other tabs wear sorts both: a counted title
               and a line under it, the one action on the header rail, the type
               toggles on the left of the toolbar and the period switch on its
               right, then the rows meeting the card's edge. */
            const card = el('div', 'card');
            const head = el('div', 'card-head');
            const total = Object.keys(crmCache.activities || {}).length;
            head.append(el('h3', 'card-title',
                total.toLocaleString() + (total === 1 ? ' activity' : ' activities')));
            const cAct = el('div', 'card-act');
            const add = textButton(null, { kind: 'primary', small: true }); add.append(ico(I.plus), document.createTextNode('Activity'));
            add.onclick = () => crmActivityForm({}, renderCRM);
            cAct.append(add); head.append(cAct); card.append(head);
            const seg = segmented([['upcoming', 'To do'], ['overdue', 'Overdue'], ['today', 'Today'],
                                   ['week', 'This week'], ['done', 'Done']],
                                  crmActPeriod, (k) => { crmActPeriod = k; renderCRM(); }, { label: 'When' });
            /* Mine is an on/off filter, not a sixth period, so it is its own
               toggle: inside the period track it lit a second segment beside
               the one that was chosen. */
            let mine = null;
            if (crmMulti()) {
                mine = textButton('Mine', { small: true, cls: crmActMine ? 'on' : '' });
                mine.type = 'button';
                mine.title = 'Only activities assigned to me';
                mine.setAttribute('aria-pressed', crmActMine ? 'true' : 'false');
                mine.onclick = () => { crmActMine = !crmActMine; renderCRM(); };
            }
            const tools = el('div', 'crm-types');
            /* Type toggles: lit means included, exactly the Pipedrive read. */
            CRM_TYPES.forEach(([k, lab]) => {
                const b = el('button', 'crm-ticon' + (crmActTypesOff[k] ? '' : ' on'));
                b.append(ico(crmTypeIcon(k))); b.title = lab;
                b.onclick = () => { crmActTypesOff[k] = !crmActTypesOff[k]; renderCRM(); };
                tools.append(b);
            });
            card.append(tableTools([tools, mine].filter(Boolean), [seg]));
            host.append(card);
            const today = crmCache.today;
            const weekEnd = new Date(Date.parse(today) + 6 * 86400000).toISOString().slice(0, 10);
            let acts = Object.values(crmCache.activities).filter(a => !crmActTypesOff[a.type]);
            /* An archived deal's leftovers stay out of the working lists: the
               deal left the desk, its nagging goes with it. Done keeps them  - 
               history is history. */
            if (crmActPeriod !== 'done')
                acts = acts.filter(a => !((crmCache.deals[a.deal_id || ''] || {}).archived));
            if (crmActMine) acts = acts.filter(a => (a.assignee || '') === crmMe());
            if (crmActPeriod === 'done') acts = acts.filter(a => a.done);
            else {
                acts = acts.filter(a => !a.done);
                if (crmActPeriod === 'overdue') acts = acts.filter(a => a.state === 'overdue');
                else if (crmActPeriod === 'today') acts = acts.filter(a => a.state === 'today' || a.state === 'overdue');
                else if (crmActPeriod === 'week') acts = acts.filter(a => a.due_date <= weekEnd);
            }
            acts.sort((a, b) => crmActPeriod === 'done'
                ? String(b.done_at).localeCompare(String(a.done_at))
                : String(a.due_date || '9999').localeCompare(String(b.due_date || '9999')));
            if (!acts.length) {
                /* Inside the card, not instead of it: the filter that emptied
                   the list has to stay on the page beside the emptiness. */
                card.append(el('div', 'empty', crmActPeriod === 'done'
                    ? 'Nothing completed yet.' : 'Nothing scheduled.'));
                return;
            }
            /* Day groups, so a run of Tuesdays reads as a day plan, not a wall. */
            const limit = crmActPeriod === 'done' ? 500 : 400;
            const groupOf = (a) => {
                if (crmActPeriod === 'done') return (a.done_at || '').slice(0, 7) || 'Undated';
                if (!a.due_date) return 'No date';
                if (a.due_date < today) return 'Overdue';
                if (a.due_date === today) return 'Today';
                if (a.due_date <= weekEnd) return 'This week';
                return 'Later';
            };
            const shown = acts.slice(0, limit);
            const perGroup = {};
            shown.forEach(a => { const g = groupOf(a); perGroup[g] = (perGroup[g] || 0) + 1; });
            /* One table (12 Oct 2026, OPS-19): the tick, the type, the activity
               over where and its note, the deal and the person side by side (the
               person showed only when there was no deal), who it is for, the
               priority and when it is due. A group row carries its count. */
            const multi = crmMulti();
            const rows = [];
            let lastGroup = null;
            shown.forEach(a => {
                const g = groupOf(a);
                if (g !== lastGroup) {
                    lastGroup = g;
                    const nice = /^\d{4}-\d{2}$/.test(g)
                        ? new Date(g + '-01T12:00:00').toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
                        : g;
                    const gh = el('span', 'crm-group'); gh.append(document.createTextNode(nice), el('span', 'cnt', String(perGroup[g])));
                    rows.push({ cls: 'dt-grp', cells: [gh] });
                }
                const what = el('span', 'dt-name');
                const sb = el('button', 'dt-link', a.subject); sb.type = 'button'; sb.title = a.subject;
                sb.onclick = (ev) => { ev.stopPropagation(); crmActivityForm({ id: a.id }, renderCRM); };
                what.append(sb);
                const preview = a.note_preview || a.note || '';
                const under = [a.location, preview && !a.done ? preview : ''].filter(Boolean).join(' \u00b7 ');
                const actCell = document.createDocumentFragment(); actCell.append(what);
                if (under) actCell.append(el('span', 'dt-sub', under));
                const deal = a.deal_id && crmCache.deals[a.deal_id];
                const per = crmPerson(a.person_id);
                const cells = [crmActTick(a, renderCRM), ico(crmTypeIcon(a.type)), actCell,
                    deal ? deal.title : el('span', 'dt-muted', 'No linked deal'), (per && per.name) || ''];
                if (multi) cells.push((a.assignee && crmUname(a.assignee)) || '');
                cells.push(a.priority ? el('span', 'crm-prio ' + a.priority, cap(a.priority)) : '',
                    el('span', 'crm-act-due ' + a.state, (a.due_date ? fmtDate(a.due_date) : '') + (a.due_time ? ', ' + a.due_time : '')));
                rows.push({ cls: a.done ? 'settled' : '', onClick: () => crmActivityForm({ id: a.id }, renderCRM), cells: cells });
            });
            card.append(dtable([{ head: '' }, { head: '' }, { head: 'Activity', cls: 'stack' }, { head: 'Deal' }, { head: 'Person' }]
                .concat(multi ? [{ head: 'For' }] : []).concat([{ head: 'Priority' }, { head: 'Due' }]),
                rows, { cls: 'dt-acts' + (multi ? ' multi' : ''), label: 'Activities', main: 2 }));
            if (acts.length > limit)
                card.append(el('div', 'crm-sub', 'Showing the first ' + limit + ' of ' + acts.length + '.'));
        }

        /* ---------------- contacts ---------------- */
        function renderCRMContacts(host) {
            /* A holding rail, not a bar: its children are moved into the
               toolbar's right side once the search and filter are built. */
            const bar = el('div');
            const add = textButton(null, { kind: 'primary', small: true });
            add.append(ico(I.plus), document.createTextNode(crmContactsMode === 'people' ? 'Person' : 'Organisation'));
            add.onclick = () => crmContactForm(crmContactsMode === 'people' ? 'person' : 'org');
            /* Exports what the search left, not the whole store: the handler is
               attached inside paint, where the filtered list actually exists. */
            const expBtn = textButton(null, { small: true });
            expBtn.append(ico(I.download), document.createTextNode('Export CSV'));
            bar.append(expBtn);
            if ((!teamMe || teamMe.role === 'master') && crmContactsMode === 'people') {
                /* Bulk email-matching of contacts to Shopify customers. Runs
                   nightly by itself; the button is for not waiting overnight. */
                const link = textButton(null, { small: true });
                link.append(ico(I.refresh), document.createTextNode('Link Shopify'));
                link.title = 'Match every unlinked contact to a Shopify customer by email';
                link.onclick = async () => {
                    link.disabled = true;
                    try {
                        const r = await crmOp('/api/crm/contact', { op: 'shopify_link_sweep' });
                        const rep = r.report || {};
                        const line = 'Linked ' + (rep.linked || 0) + ' contacts to Shopify customers'
                            + (rep.already ? ' \u00b7 ' + rep.already + ' already linked' : '')
                            + (rep.ambiguous ? ' \u00b7 ' + rep.ambiguous + ' skipped as ambiguous' : '')
                            + '.';
                        /* A partial crawl must not read as a finished one: the
                           contacts it never reached look identical to contacts
                           with no Shopify customer at all. */
                        if (rep.complete === false) toastError(line + ' ' + (rep.problem || ''));
                        else toastOk(line);
                        renderCRM();
                    } catch (e) { toastError(e.message); }
                    link.disabled = false;
                };
                bar.append(link);
            }
            /* The filled button ends the row, as on Deals. */
            bar.append(add);
            const seg = segmented([['people', 'People'], ['orgs', 'Organisations']], crmContactsMode,
                                  (k) => { crmContactsMode = k; crmContactsPage = 1; renderCRM(); }, { label: 'Show' });
            /* Finding a person while they are ON THE PHONE is the single most
               common contact operation: name, email, phone and company all
               match, because whichever fragment is to hand must work. */
            const q = tableSearch('Search name, email, phone, company…', crmContactsQ, (v) => {
                crmContactsQ = v; crmContactsPage = 1; paint();
            });
            q.classList.add('search-long');
            const people = crmContactsMode === 'people';
            /* One card holding the lot, the way the reference builds a list
               page: a counted title and a line saying what it is, the actions
               on the right of the header, the search and filter on a toolbar
               under it, then the table in its own box, then the pager. */
            const card = el('div', 'card');
            const head = el('div', 'card-head');
            const total = Object.keys(people ? crmCache.persons : crmCache.orgs).length;
            head.append(el('h3', 'card-title',
                total.toLocaleString() + (people ? (total === 1 ? ' person' : ' people') : (total === 1 ? ' organisation' : ' organisations'))));
            const act = el('div', 'card-act');
            [...bar.children].forEach(n => act.append(n));
            head.append(act);
            card.append(head);
            /* Search on the left, the view switch on the right - the placement
               the deals board and the inbox both use for the same control. It
               used to sit beside the search here and 811px away on the deals
               tab, so one component doing one job had two homes. */
            card.append(tableTools([q], [seg]));
            /* Bleed, so the table's own hairlines run to the card's edge rather
               than drawing a second rounded frame 17px inside it. The selection
               bar and the pager take the 16px gutter back as margin. */
            const list = el('div', 'card-bleed'); card.append(list);
            host.append(card);
            function paint() {
                list.innerHTML = '';
                const ql = crmContactsQ.toLowerCase();
                const hay = c => (c.name + ' ' + (c.emails || []).join(' ') + ' '
                    + (c.phones || []).join(' ') + ' ' + (c.job_title || '') + ' '
                    + (people && c.org_id && crmOrg(c.org_id) ? crmOrg(c.org_id).name : '')
                    + ' ' + (c.label || '')).toLowerCase();
                const items = Object.values(people ? crmCache.persons : crmCache.orgs)
                    .filter(c => !ql || hay(c).includes(ql))
                    .sort((a, b) => a.name.localeCompare(b.name));
                if (!items.length) {
                    list.append(el('div', 'empty', ql ? 'Nobody matches that.' : 'Nobody here yet.'));
                    return;
                }
                /* A tick may only ever mean a row you can SEE - same rule as
                   the mail bulk bar. */
                const visible = new Set(items.map(c => c.id));
                [...crmContactSel].forEach(id => { if (!visible.has(id)) crmContactSel.delete(id); });
                const master = !teamMe || teamMe.role === 'master';
                /* IDLE AND ARMED MEASURE THE SAME, the rule the inbox's bulk
                   bar keeps. A tick turns the table's head row into the
                   selection bar, in place and at the same height (12 Oct 2026,
                   OPS-25), so no row moves under the pointer: the bar used to
                   stand empty above the table, a 48px band, until a tick. */
                const bar2 = master && crmContactSel.size ? el('div', 'crm-selbar') : null;
                if (bar2) {
                    const del = textButton(null, { small: true });
                    del.append(ico(I.trash), document.createTextNode(
                        'Delete ' + crmContactSel.size + ' selected'));
                    del.onclick = async () => {
                        if (!await uiConfirm('Delete ' + crmContactSel.size + ' selected '
                            + (people ? 'people' : 'organisations') + '? Anyone on an open deal '
                            + 'is skipped. This cannot be undone.',
                            { title: 'Delete contacts', okText: 'Delete' })) return;
                        del.disabled = true;
                        try {
                            const r = await crmOp('/api/crm/contact', { op: 'bulk_delete',
                                kind: people ? 'person' : 'org', ids: [...crmContactSel] });
                            crmContactSel.clear();
                            if ((r.skipped || []).length)
                                toastError('Deleted ' + r.deleted + '. Skipped (on open deals): '
                                    + r.skipped.slice(0, 5).join(', ')
                                    + (r.skipped.length > 5 ? '…' : ''));
                            else toastOk('Deleted ' + r.deleted + '.');
                            renderCRM();
                        } catch (e) { del.disabled = false; toastError(e.message); }
                    };
                    const clr = textButton('Clear selection', { small: true });
                    clr.onclick = () => { crmContactSel.clear(); paint(); };
                    bar2.append(del, clr);
                }
                /* A TABLE, because this is a table: the company, the email, the
                   deal count and the Shopify link used to be joined with dots
                   into one nowrap line, so a long company name truncated the
                   other three away entirely. Same shape as the deals list, so
                   both read alike and the width goes to real columns. */
                const wrapT = el('div', 'ktable-wrap');
                const tb = el('table', 'ktable crm-table crm-contact-table');
                const cols = master ? ['<th class="tick"></th>'] : [];
                cols.push('<th class="kt-main">Name</th>');
                if (people) cols.push('<th>Organisation</th>', '<th>Email</th>', '<th>Phone</th>');
                else cols.push('<th>Website</th>', '<th>Address</th>');
                cols.push('<th class="num crm-deals">Deals</th>', '<th class="crm-label">Label</th>');
                if (bar2) {
                    const thead = el('thead'); const tr0 = el('tr', 'crm-selhead'); const th0 = el('th'); th0.colSpan = cols.length;
                    th0.append(bar2); tr0.append(th0);
                    /* The column heads stay after the bar, hidden, so a phone's two-line rows still name their values. */
                    thead.innerHTML = '<tr class="crm-colhead">' + cols.join('') + '</tr>'; thead.prepend(tr0); tb.append(thead);
                } else tb.innerHTML = '<thead><tr>' + cols.join('') + '</tr></thead>';
                const tbody = el('tbody');
                const pageCount = Math.max(1, Math.ceil(items.length / crmContactsSize));
                if (crmContactsPage > pageCount) crmContactsPage = pageCount;
                const from = (crmContactsPage - 1) * crmContactsSize;
                items.slice(from, from + crmContactsSize).forEach(c => {
                    /* .sel, so the row a tick chose is darker than the row the
                       pointer merely passed over. */
                    const tr = el('tr', 'crm-list-row' + (crmContactSel.has(c.id) ? ' sel' : ''));
                    /* Not a pretend button (it holds a tick): the name cell holds the
                       row's opener, and a click anywhere else on the row opens it. */
                    const openContact = () => crmContactModal(people ? 'person' : 'org', c.id);
                    if (master) {
                        const cell = el('td', 'tick');
                        const cb = document.createElement('input');
                        cb.type = 'checkbox'; cb.checked = crmContactSel.has(c.id); cb.setAttribute('aria-label', 'Select ' + c.name);
                        cb.onclick = (e) => { e.stopPropagation();
                            cb.checked ? crmContactSel.add(c.id) : crmContactSel.delete(c.id); paint(); };
                        cell.append(cb); tr.append(cell);
                    }
                    const nameTd = el('td', 'kw', c.name);
                    const cob = rowOpener('Open ' + c.name, openContact); cob.dataset.focusKey = 'contact-row-' + c.id;
                    nameTd.prepend(cob);
                    tr.append(nameTd);
                    const deals = Object.values(crmCache.deals).filter(x =>
                        (people ? x.person_id : x.org_id) === c.id);
                    const openD = deals.filter(x => x.status === 'open' && !x.archived).length;
                    if (people) {
                        tr.append(el('td', null, (crmOrg(c.org_id) || {}).name || ''));
                        const em = el('td', 'crm-email');
                        if ((c.emails || [])[0]) em.append(el('span', null, c.emails[0]));
                        /* Title case, like every other chip in the two tables:
                           the .lbl-chip rule sets text-transform: none exactly
                           so a chip does not shout, and the literal defeated it. */
                        if (c.shopify_customer_id) em.append(el('span', 'lbl-chip note', 'Shopify'));
                        tr.append(em);
                        tr.append(el('td', 'crm-phone', (c.phones || [])[0] || ''));
                    } else {
                        tr.append(el('td', 'crm-web', c.website || ''));
                        tr.append(el('td', null, c.address || ''));
                    }
                    /* Zero is a number and an empty cell is a missing one: a
                       contact with no deals reads as data that failed to load. */
                    tr.append(el('td', 'num crm-deals', deals.length
                        ? String(deals.length) + (openD ? ' (' + openD + ' open)' : '') : '0'));
                    const lab = el('td', 'crm-label');
                    if (c.label) lab.append(crmChip(c.label));
                    tr.append(lab);
                    opensOnClick(tr, openContact);
                    tbody.append(tr);
                });
                /* The header tick, which was an empty cell: a list this long
                   already offers a bulk delete, and arming it a row at a time
                   is not an offer. Tri-state, so "some" never reads as "all",
                   and it covers what the SEARCH left, which is the same rule
                   the row ticks are pruned by. */
                if (master) {
                    const th = tb.querySelector('thead th.tick');
                    const all = document.createElement('input');
                    all.type = 'checkbox';
                    const lab = 'Select every ' + (people ? 'person' : 'organisation') + ' this search left';
                    all.setAttribute('aria-label', lab); all.title = lab;
                    all.checked = crmContactSel.size === visible.size;
                    all.indeterminate = crmContactSel.size > 0 && crmContactSel.size < visible.size;
                    all.onclick = () => {
                        if (all.checked) visible.forEach(id => crmContactSel.add(id));
                        else crmContactSel.clear();
                        paint();
                    };
                    if (th) th.append(all);
                }
                tb.append(tbody); wrapT.append(tb); list.append(wrapT);
                /* A pager rather than "show more": at four thousand contacts
                   the old button had to be pressed thirty times, and the count
                   it printed was the only clue how many that would be. */
                list.append(tablePager({
                    total: items.length, page: crmContactsPage, pageSize: crmContactsSize,
                    noun: people ? 'people' : 'organisations',
                    onPage: (n) => { crmContactsPage = n; paint(); },
                    onSize: (n) => { crmContactsSize = n; crmContactsPage = 1; paint(); },
                }));
                expBtn.onclick = () => {
                    if (people) crmCSV('people.csv',
                        ['Name', 'Emails', 'Phones', 'Job title', 'Organisation', 'Label'],
                        items.map(c => [c.name, (c.emails || []).join('; '), (c.phones || []).join('; '),
                            c.job_title || '', (crmOrg(c.org_id) || {}).name || '', c.label || '']));
                    else crmCSV('organisations.csv',
                        ['Name', 'Address', 'Website', 'Label'],
                        items.map(c => [c.name, c.address || '', c.website || '', c.label || '']));
                };
            }
            paint();
        }

        /* ---------------- the contact detail: the hub Pipedrive lives in ---- */
        function crmContactModal(kind, id) {
            const people = kind === 'person';
            const c = people ? crmCache.persons[id] : crmCache.orgs[id];
            if (!c) return;
            const m = crmModal(c.name);
            let notes = null;   /* null = still loading */
            function paint() {
                if (!crmCache) { m.close(); return; }
                const cc = people ? crmCache.persons[id] : crmCache.orgs[id];
                if (!cc) { m.close(); return; }
                m.body.innerHTML = '';
                const top = el('div', 'lbl-toolbar');
                const sub = [];
                if (people && cc.job_title) sub.push(cc.job_title);
                if (people && cc.org_id && crmOrg(cc.org_id)) sub.push(crmOrg(cc.org_id).name);
                if (sub.length) top.append(el('span', 'crm-sub', sub.join(' · ')));
                if (cc.label) top.append(crmChip(cc.label));
                const edit = textButton(); edit.append(ico(I.edit), document.createTextNode('Edit'));
                edit.onclick = () => { m.close(); crmContactForm(kind, id); };
                top.append(edit);
                const merge = textButton('Merge');
                merge.title = 'Fold a duplicate of this contact into this one';
                merge.onclick = () => crmMergePrompt(kind, id, () => {
                    notes = null; paint(); loadNotes();   /* the loser's notes just arrived */
                });
                top.append(merge);
                m.body.append(top);
                /* Ways to reach them, all live links. */
                const reach = el('div', 'crm-focus');
                let any = false;
                (cc.phones || []).forEach((ph, i) => {
                    any = true;
                    const r = el('div', 'crm-cline'); r.append(ico(I.phone));
                    const a = el('a', null, ph); a.href = 'tel:' + ph.replace(/[^+\d]/g, '');
                    r.append(a);
                    const lab = (cc.phone_labels || [])[i];
                    if (lab) r.append(el('span', 'crm-sub', lab));
                    reach.append(r);
                });
                (cc.emails || []).forEach((em, i) => {
                    any = true;
                    const r = el('div', 'crm-cline'); r.append(ico(I.mail));
                    const a = el('a', null, em); a.href = 'mailto:' + em.replace(/[?&#\s"'<>\\]/g, '');
                    r.append(a);
                    const lab = (cc.email_labels || [])[i];
                    if (lab) r.append(el('span', 'crm-sub', lab));
                    reach.append(r);
                });
                if (!people && cc.website) {
                    any = true;
                    const r = el('div', 'crm-cline'); r.append(ico(I.globe));
                    const a = el('a', null, cc.website);
                    a.href = /^https?:/.test(cc.website) ? cc.website : 'https://' + cc.website;
                    a.target = '_blank'; a.rel = 'noopener';
                    r.append(a); reach.append(r);
                }
                if (!people && cc.address) {
                    any = true;
                    const r = el('div', 'crm-cline'); r.append(ico(I.flag));
                    r.append(el('span', null, cc.address)); reach.append(r);
                }
                if (any) m.body.append(reach);
                /* Custom fields, shown plainly. */
                const cust = cc.custom || {};
                if (Object.keys(cust).length) {
                    const cf = el('div', 'crm-focus');
                    cf.append(el('div', 'disp-subhead', 'Details'));
                    const grid = el('div', 'crm-cf');
                    Object.entries(cust).forEach(([k, v]) => {
                        grid.append(el('div', 'crm-cf-k', k), el('div', null, v));
                    });
                    cf.append(grid); m.body.append(cf);
                }
                /* Their deals: the count that used to be a dead reference. */
                const deals = Object.values(crmCache.deals)
                    .filter(x => (people ? x.person_id : x.org_id) === id)
                    .sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)));
                if (deals.length) {
                    const dd = el('div', 'crm-focus');
                    dd.append(el('div', 'disp-subhead', 'Deals'));
                    deals.slice(0, 15).forEach(x => {
                        const r = el('div', 'crm-cline');
                        const a = actionLink('miss-open', x.title);
                        a.onclick = () => { m.close(); crmDealModal(x.id); };
                        r.append(a);
                        r.append(el('span', 'crm-sub', crmMoney(x.value) + ' · '
                            + (x.archived ? 'archived' : x.status)));
                        dd.append(r);
                    });
                    m.body.append(dd);
                }
                /* Open activities linked straight to the person. */
                const acts = Object.values(crmCache.activities)
                    .filter(a => !a.done && (people ? a.person_id : a.org_id) === id)
                    .sort((a, b) => String(a.due_date).localeCompare(String(b.due_date)));
                if (acts.length) {
                    const aa = el('div', 'crm-focus');
                    aa.append(el('div', 'disp-subhead', 'To do'));
                    acts.slice(0, 10).forEach(a => aa.append(crmActRow(a, paint)));
                    m.body.append(aa);
                }
                /* Notes: fetched, addable, pinnable. */
                const nn = el('div', 'crm-focus');
                nn.append(el('div', 'disp-subhead', 'Notes'));
                const ta = document.createElement('textarea');
                ta.className = 'lia-chase-body'; ta.rows = 2;
                ta.placeholder = 'A note about ' + cc.name + '…'; ta.setAttribute('aria-label', 'A note about ' + cc.name);
                nn.append(ta);
                const nbar = el('div', 'disp-actions');
                const nbtn = textButton('Save note');
                nbtn.onclick = async () => {
                    if (!ta.value.trim()) return;
                    try {
                        await crmOp('/api/crm/contact', { op: 'note_add', kind: kind, id: id, text: ta.value.trim() });
                        notes = null; paint(); loadNotes();
                    } catch (e) { toastError(e.message); }
                };
                nbar.append(nbtn); nn.append(nbar);
                if (notes === null) {
                    const t = el('div', 'thinking'); t.append(loader(), el('span', null, 'Reading notes…'));
                    nn.append(t);
                } else if (!notes.length) {
                    nn.append(el('div', 'crm-sub', 'Nothing yet.'));
                } else {
                    notes.slice().sort((a, b) => (!!b.pinned - !!a.pinned)
                        || String(b.at).localeCompare(String(a.at))).forEach(n => {
                        const r = el('div', 'crm-hist-row' + (n.pinned ? ' pinned' : ''));
                        r.append(document.createTextNode(n.text));
                        const w = el('div', 'crm-hist-when', fmtDate(n.at));
                        const pin = actionLink('miss-open', n.pinned ? 'Unpin' : 'Pin');
                        pin.onclick = async () => {
                            try { await crmOp('/api/crm/contact', { op: 'note_pin', kind: kind, id: id, note_id: n.id }); notes = null; paint(); loadNotes(); }
                            catch (e) { toastError(e.message); }
                        };
                        const del = actionLink('miss-open', 'Delete');
                        del.onclick = async () => {
                            try { await crmOp('/api/crm/contact', { op: 'note_del', kind: kind, id: id, note_id: n.id }); notes = null; paint(); loadNotes(); }
                            catch (e) { toastError(e.message); }
                        };
                        w.append(document.createTextNode(' · ')); w.append(pin);
                        w.append(document.createTextNode(' · ')); w.append(del);
                        r.append(w); nn.append(r);
                    });
                }
                m.body.append(nn);
            }
            async function loadNotes() {
                try {
                    const r = await api('/api/crm/contact', { op: 'detail', kind: kind, id: id });
                    notes = r.notes || [];
                } catch (e) { notes = []; }
                if (document.body.contains(m.body)) paint();
            }
            paint();
            loadNotes();
        }
        function crmMergePrompt(kind, keepId, onDone) {
            const people = kind === 'person';
            const m = crmModal('Merge into ' + (people ? crmCache.persons[keepId] : crmCache.orgs[keepId]).name);
            m.body.append(el('p', 'field-help', 'Pick the duplicate. Its deals, activities and notes '
                + 'move onto this contact, its extra details fill any gaps, and the duplicate is removed. '
                + 'This cannot be undone.'));
            const dupIn = crmText('', 'Type the duplicate’s name');
            const grid = el('div', 'disp-addr-grid'); m.body.append(grid);
            crmField(grid, 'Duplicate', crmTypeahead(dupIn, people ? crmPersonRows : crmOrgRows));
            const bar = m.foot();
            const go = textButton('Merge', { kind: 'primary' });
            go.onclick = async () => {
                /* The picked ID wins over the typed name: with two "Priya
                   Khan"s a name lookup merges whichever namesake it finds. */
                const coll = people ? crmCache.persons : crmCache.orgs;
                const nm = dupIn.value.trim().toLowerCase();
                let dup = coll[dupIn.dataset.pickedId || ''];
                if (!dup || dup.name.toLowerCase() !== nm) {
                    const byName = Object.values(coll).filter(x => x.name.toLowerCase() === nm && x.id !== keepId);
                    if (byName.length > 1) { toastError('Two contacts share that name. Pick one from the list.'); return; }
                    dup = byName[0];
                }
                if (!dup || dup.id === keepId) { toastError('Type the duplicate’s exact name and pick it from the list.'); return; }
                if (!await uiConfirm('Merge "' + dup.name + '" into this contact and remove it?',
                                     { title: 'Merge contacts', okText: 'Merge' })) return;
                go.disabled = true;
                try {
                    await crmOp('/api/crm/contact', { op: people ? 'person_merge' : 'org_merge',
                                                      id: dup.id, into: keepId });
                    m.close(); if (onDone) onDone();
                } catch (e) { go.disabled = false; toastError(e.message); }
            };
            bar.append(go);
        }
        function crmContactForm(kind, id) {
            const existing = id ? (kind === 'person' ? crmCache.persons[id] : crmCache.orgs[id]) : null;
            const m = crmModal(existing ? existing.name : (kind === 'person' ? 'New person' : 'New organisation'));
            const grid = el('div', 'disp-addr-grid'); m.body.append(grid);
            const nameIn = crmText(existing ? existing.name : '', '');
            crmField(grid, 'Name', nameIn);
            let emailIn, phoneIn, orgIn, addrIn, jobIn, webIn;
            if (kind === 'person') {
                /* One address per line: the second and third are real data  - 
                   a form that can only see the first once trapped the rest. */
                emailIn = document.createElement('textarea');
                emailIn.className = 'disp-text'; emailIn.rows = Math.max(1, (existing && (existing.emails || []).length) || 1);
                emailIn.value = existing ? (existing.emails || []).join('\n') : '';
                emailIn.placeholder = 'one per line';
                crmField(grid, 'Email(s)', emailIn);
                phoneIn = document.createElement('textarea');
                phoneIn.className = 'disp-text'; phoneIn.rows = Math.max(1, (existing && (existing.phones || []).length) || 1);
                phoneIn.value = existing ? (existing.phones || []).join('\n') : '';
                phoneIn.placeholder = 'one per line';
                crmField(grid, 'Phone(s)', phoneIn);
                jobIn = crmText(existing ? existing.job_title || '' : '', '');
                crmField(grid, 'Job title', jobIn);
                orgIn = crmText(existing && crmOrg(existing.org_id) ? crmOrg(existing.org_id).name : '', 'Type to search or create');
                crmField(grid, 'Organisation', crmTypeahead(orgIn, crmOrgRows));
            } else {
                addrIn = crmText(existing ? existing.address : '', '');
                crmField(grid, 'Address', addrIn);
                webIn = crmText(existing ? existing.website || '' : '', '');
                crmField(grid, 'Website', webIn);
            }
            const labSel = el('select', 'disp-text');
            labSel.append(new Option('No label', ''));
            const labNames = Object.keys((crmCache.label_colors || {}));
            (crmCache.labels || []).forEach(l => { if (!labNames.includes(l)) labNames.push(l); });
            labNames.forEach(l => labSel.append(new Option(l, l)));
            if (existing && existing.label) {
                if (!labNames.includes(existing.label)) labSel.append(new Option(existing.label, existing.label));
                labSel.value = existing.label;
            }
            crmField(grid, 'Label', labSel);
            /* The Shopify link: search live customers, one click to attach. */
            let shopifyId = existing ? existing.shopify_customer_id : null;
            if (kind === 'person') {
                const sWrap = el('div', 'crm-focus');
                sWrap.append(el('div', 'disp-subhead', 'Shopify customer'));
                const status = el('div', 'crm-sub', shopifyId ? 'Linked (customer ' + shopifyId + ')' : 'Not linked');
                const sIn = crmText('', 'Search your Shopify customers…');
                const results = el('div');
                let timer = null;
                sIn.oninput = () => {
                    clearTimeout(timer);
                    timer = setTimeout(async () => {
                        results.innerHTML = '';
                        if (!sIn.value.trim()) return;
                        try {
                            const r = await api('/api/crm/contact', { op: 'shopify_search', q: sIn.value.trim() });
                            (r.matches || []).forEach(c2 => {
                                const b = textButton();
                                b.style.margin = 'var(--sp-1) var(--sp-1) 0 0';
                                b.textContent = c2.name + (c2.company ? ' · ' + c2.company : '') + ' (' + (c2.orders || 0) + ' orders)';
                                b.onclick = () => { shopifyId = c2.id; status.textContent = 'Will link to ' + c2.name; };
                                results.append(b);
                            });
                            if (!(r.matches || []).length) results.append(el('div', 'crm-sub', 'No matches.'));
                        } catch (e) { results.append(el('div', 'crm-sub', e.message)); }
                    }, 350);
                };
                sWrap.append(status, sIn, results); m.body.append(sWrap);
            }
            const bar = m.foot();
            const save = textButton(existing ? 'Save' : 'Add', { kind: 'primary' });
            save.onclick = async () => {
                save.disabled = true;
                try {
                    if (kind === 'person') {
                        let orgId = existing ? existing.org_id : '';
                        const on = orgIn.value.trim();
                        const foundO = crmPicked(orgIn, crmCache.orgs)
                            || Object.values(crmCache.orgs).find(o => o.name.toLowerCase() === on.toLowerCase());
                        if (on && !foundO) orgId = (await crmOp('/api/crm/contact', { op: 'org_add', name: on })).id;
                        else if (foundO) orgId = foundO.id; else if (!on) orgId = '';
                        const lines = t => t.value.split('\n').map(s => s.trim()).filter(Boolean);
                        const emails = lines(emailIn), phones = lines(phoneIn);
                        /* Labels follow their value when the list is reordered
                           or trimmed, instead of sticking to a position. */
                        const relabel = (vals, oldVals, oldLabs) => vals.map(v => {
                            const i = (oldVals || []).findIndex(x => x.toLowerCase() === v.toLowerCase());
                            return i >= 0 ? ((oldLabs || [])[i] || '') : '';
                        });
                        const payload = { name: nameIn.value.trim(), org_id: orgId,
                            job_title: jobIn.value.trim(), label: labSel.value,
                            emails: emails, phones: phones,
                            /* this form shows EVERY address, so its list is the
                               whole truth - pruning to one must stick */
                            contacts_full: true };
                        if (existing) {
                            payload.email_labels = relabel(emails, existing.emails, existing.email_labels);
                            payload.phone_labels = relabel(phones, existing.phones, existing.phone_labels);
                            await crmOp('/api/crm/contact', { op: 'person_update', id: id, ...payload });
                            if (shopifyId !== existing.shopify_customer_id)
                                await crmOp('/api/crm/contact', { op: 'link_shopify', id: id, shopify_customer_id: shopifyId });
                        } else {
                            await crmOp('/api/crm/contact', { op: 'person_add', ...payload,
                                shopify_customer_id: shopifyId });
                        }
                    } else {
                        const payload = { name: nameIn.value.trim(), address: addrIn.value.trim(),
                                          website: webIn.value.trim(), label: labSel.value };
                        if (existing) await crmOp('/api/crm/contact', { op: 'org_update', id: id, ...payload });
                        else await crmOp('/api/crm/contact', { op: 'org_add', ...payload });
                    }
                    m.close();
                } catch (e) { save.disabled = false; toastError(e.message); }
            };
            bar.append(save);
            if (existing) {
                const del = textButton('Delete');
                del.onclick = async () => {
                    if (!await uiConfirm('Delete ' + existing.name + '?', { title: 'Delete', okText: 'Delete' })) return;
                    try { await crmOp('/api/crm/contact', { op: kind === 'person' ? 'person_delete' : 'org_delete', id: id }); m.close(); }
                    catch (e) { toastError(e.message); }
                };
                bar.append(del);
            }
        }

        /* ---------------- leads inbox ---------------- */
        function renderCRMLeads(host) {
            /* The same card the deals and contacts tabs wear: a counted title,
               a line saying what a lead IS, the one action on the right of the
               header and the Inbox/Archive switch on the toolbar's right where
               every other view switch in the app sits. The bar, the help line
               and the rows used to stand bare on the page background, so three
               tabs of one view read as three different pages. */
            const card = el('div', 'card');
            const head = el('div', 'card-head');
            const total = Object.keys(crmCache.leads || {}).length;
            /* A definition, so the title's info button (copy plan, CRM #2). */
            const lt = el('h3', 'card-title', total.toLocaleString() + (total === 1 ? ' lead' : ' leads'));
            const ltInfo = infoButton('What a lead is', { title: 'Leads', body: 'A lead is an enquiry that is not yet a deal: it waits '
                + 'here so the pipeline holds only real, qualified work. Convert it when it firms up.' });
            head.append(titleInfo(lt, ltInfo));
            const act = el('div', 'card-act');
            const add = textButton(null, { kind: 'primary', small: true }); add.append(ico(I.plus), document.createTextNode('Lead'));
            add.onclick = () => crmLeadForm();
            act.append(add); head.append(act); card.append(head);
            const seg = segmented([['active', 'Inbox'], ['archived', 'Archive']], crmLeadsMode,
                                  (k) => { crmLeadsMode = k; renderCRM(); }, { label: 'Show' });
            card.append(tableTools([], [seg]));
            host.append(card);
            const leads = Object.values(crmCache.leads)
                .filter(l => (crmLeadsMode === 'archived') === !!l.archived)
                .sort((a, b) => (a.seen === b.seen ? String(b.created_at).localeCompare(String(a.created_at)) : (a.seen ? 1 : -1)));
            /* One table (12 Oct 2026, OPS-20): the lead with its label beside
               it, then who, which organisation, what it is worth and when it
               arrived, each under its head, every row one height. Each was a
               title at the left and its facts 800px away. */
            card.append(dtable([{ head: 'Lead' }, { head: 'Person' }, { head: 'Organisation' }, { head: 'Value', cls: 'num' }, { head: 'Arrived' }],
                leads.map(l => {
                    const unseen = !l.seen && !l.archived;
                    const nm = el('span', 'dt-name' + (unseen ? ' crm-unseen' : ''));
                    if (unseen) nm.append(el('span', 'crm-new-dot'));
                    const b = el('button', 'dt-link', l.title); b.type = 'button'; b.title = l.title;
                    b.onclick = (ev) => { ev.stopPropagation(); crmLeadModal(l.id); };
                    nm.append(b);
                    if (l.label) nm.append(crmChip(l.label));
                    const pp = crmPerson(l.person_id), oo = crmOrg(l.org_id);
                    return { onClick: () => crmLeadModal(l.id),
                             cells: [nm, (pp && pp.name) || '', (oo && oo.name) || '', l.value ? crmMoney(l.value) : '', fmtDate(l.created_at)] };
                }), { cls: 'dt-leads', label: 'Leads',
                      empty: el('div', 'empty', crmLeadsMode === 'archived' ? 'Nothing archived.' : 'The inbox is clear.') }));
        }
        function crmLeadForm() {
            const m = crmModal('New lead');
            const grid = el('div', 'disp-addr-grid'); m.body.append(grid);
            const personIn = crmText('', 'Type to search or create');
            const orgIn = crmText('', 'Type to search or create');
            crmField(grid, 'Contact person', crmTypeahead(personIn, crmPersonRows));
            crmField(grid, 'Organisation', crmTypeahead(orgIn, crmOrgRows));
            const titleIn = crmText('', 'Autofills from the contact');
            let ltTouched = false;
            titleIn.oninput = () => { ltTouched = true; };
            function lAutofill() {
                if (ltTouched) return;
                const src = orgIn.value.trim() || personIn.value.trim();
                titleIn.value = src ? src + ' lead' : '';
            }
            [personIn, orgIn].forEach(i => { i.addEventListener('input', lAutofill); i.addEventListener('picked', lAutofill); });
            crmField(grid, 'Title', titleIn);
            const valIn = crmText('', '0'); valIn.type = 'number'; valIn.min = '0'; valIn.step = '0.01';
            crmField(grid, 'Value (£)', valIn);
            const labSel = el('select', 'disp-text');
            labSel.append(new Option('No label', ''));
            crmCache.labels.forEach(l => labSel.append(new Option(l, l)));
            crmField(grid, 'Label', labSel);
            const bar = m.foot();
            const save = textButton('Add lead', { kind: 'primary' });
            save.onclick = async () => {
                save.disabled = true;
                try {
                    let personId = '', orgId = '';
                    const pn = personIn.value.trim(), on = orgIn.value.trim();
                    const foundP = crmPicked(personIn, crmCache.persons)
                        || Object.values(crmCache.persons).find(p => p.name.toLowerCase() === pn.toLowerCase());
                    const foundO = crmPicked(orgIn, crmCache.orgs)
                        || Object.values(crmCache.orgs).find(o => o.name.toLowerCase() === on.toLowerCase());
                    if (on && !foundO) orgId = (await crmOp('/api/crm/contact', { op: 'org_add', name: on })).id;
                    else if (foundO) orgId = foundO.id;
                    if (pn && !foundP) personId = (await crmOp('/api/crm/contact', { op: 'person_add', name: pn, org_id: orgId })).id;
                    else if (foundP) personId = foundP.id;
                    await crmOp('/api/crm/lead', { op: 'add', title: titleIn.value.trim(),
                        value: valIn.value, label: labSel.value, person_id: personId, org_id: orgId });
                    m.close();
                } catch (e) { save.disabled = false; toastError(e.message); }
            };
            bar.append(save);
        }
        function crmLeadModal(leadId) {
            const l = crmCache.leads[leadId];
            if (!l) return;
            if (!l.seen) crmOp('/api/crm/lead', { op: 'seen', id: leadId }).catch(() => {});
            const m = crmModal(l.title);
            /* The same anatomy as the deal and contact modals: a status row
               up top, titled panels below, actions in the footer. */
            const top = el('div', 'lbl-toolbar');
            if (l.value) top.append(el('b', null, crmMoney(l.value)));
            if (l.label) top.append(crmChip(l.label));
            const who = crmWho(l);
            top.append(el('span', 'crm-sub', (who ? who + ' · ' : '') + 'arrived ' + fmtDate(l.created_at)));
            m.body.append(top);
            const nn = el('div', 'crm-focus');
            nn.append(el('div', 'disp-subhead', 'Notes'));
            if (!(l.notes || []).length) nn.append(el('div', 'crm-sub', 'Nothing yet.'));
            (l.notes || []).forEach(n => {
                const r = el('div', 'crm-hist-row');
                r.append(document.createTextNode(n.text), el('div', 'crm-hist-when', fmtDate(n.at)));
                nn.append(r);
            });
            const ta = document.createElement('textarea');
            ta.className = 'lia-chase-body'; ta.rows = 2; ta.placeholder = 'A note about this lead…'; ta.setAttribute('aria-label', 'A note about this lead');
            nn.append(ta);
            const nbar = el('div', 'disp-actions');
            const noteBtn = textButton('Save note');
            noteBtn.onclick = async () => {
                if (!ta.value.trim()) return;
                try { await crmOp('/api/crm/lead', { op: 'note_add', id: leadId, text: ta.value.trim() }); m.close(); crmLeadModal(leadId); }
                catch (e) { toastError(e.message); }
            };
            nbar.append(noteBtn); nn.append(nbar);
            m.body.append(nn);
            const bar = m.foot();
            if (!l.archived) {
                const conv = textButton('Convert to deal', { kind: 'primary' });
                conv.onclick = async () => {
                    try { const r = await crmOp('/api/crm/lead', { op: 'convert', id: leadId }); m.close(); crmSeg = 'deals'; renderCRM(); crmDealModal(r.id); }
                    catch (e) { toastError(e.message); }
                };
                bar.append(conv);
                const edit = textButton(); edit.append(ico(I.edit), document.createTextNode('Edit'));
                edit.onclick = () => {
                    m.body.innerHTML = '';
                    const grid = el('div', 'disp-addr-grid'); m.body.append(grid);
                    const tIn = crmText(l.title, ''); crmField(grid, 'Title', tIn);
                    const vIn = crmText(String(l.value || ''), '0'); vIn.type = 'number'; vIn.min = '0'; vIn.step = '0.01';
                    crmField(grid, 'Value (£)', vIn);
                    const lSel = el('select', 'disp-text');
                    lSel.append(new Option('No label', ''));
                    crmCache.labels.forEach(x => lSel.append(new Option(x, x)));
                    lSel.value = l.label || '';
                    crmField(grid, 'Label', lSel);
                    const b2 = el('div', 'disp-actions');
                    const sv = textButton('Save', { kind: 'primary' });
                    sv.onclick = async () => {
                        try {
                            await crmOp('/api/crm/lead', { op: 'update', id: leadId,
                                title: tIn.value.trim(), value: vIn.value, label: lSel.value });
                            m.close(); crmLeadModal(leadId);
                        } catch (e) { toastError(e.message); }
                    };
                    b2.append(sv); m.body.append(b2);
                };
                bar.append(edit);
                const arch = textButton('Archive');
                arch.onclick = async () => { try { await crmOp('/api/crm/lead', { op: 'archive', id: leadId }); m.close(); } catch (e) { toastError(e.message); } };
                bar.append(arch);
            } else {
                const un = textButton('Unarchive');
                un.onclick = async () => { try { await crmOp('/api/crm/lead', { op: 'unarchive', id: leadId }); m.close(); } catch (e) { toastError(e.message); } };
                bar.append(un);
                const del = iconButton(I.trash, 'Delete this lead for good');
                del.onclick = async () => {
                    if (!await uiConfirm('Delete this lead for good?', { title: 'Delete lead', okText: 'Delete' })) return;
                    try { await crmOp('/api/crm/lead', { op: 'delete', id: leadId }); m.close(); }
                    catch (e) { toastError(e.message); }
                };
                bar.append(del);
            }
        }

        /* ---------------- pipeline settings: stages, labels, reasons ------- */
        function crmStageEditor() {
            const m = crmModal('Pipeline');
            const sb = el('div', 'crm-focus');
            const stT = el('div', 'disp-subhead', 'Stages');
            stT.append(infoButton('About stages', { title: 'Stages', body: 'Rename the stages to your own process. Probability '
                + 'weights the pipeline value; rotting turns a deal red after sitting untouched that many days.' }));
            sb.append(stT);
            const rows = el('div'); sb.append(rows);
            const working = crmCache.stages.map(s => ({ ...s }));
            function paint() {
                rows.innerHTML = '';
                working.forEach((s, i) => {
                    const r = el('div', 'disp-boxrow');
                    const name = crmText(s.name, 'Stage name'); name.oninput = () => { s.name = name.value; };
                    const prob = crmText(String(s.probability), '%'); prob.type = 'number'; prob.min = '0'; prob.max = '100';
                    prob.className = 'disp-num'; prob.title = 'Probability %';
                    prob.oninput = () => { s.probability = parseInt(prob.value, 10) || 0; };
                    const rot = crmText(String(s.rot_days || ''), 'rot'); rot.type = 'number'; rot.min = '0';
                    rot.className = 'disp-num'; rot.title = 'Rot after N days untouched (0 = never)';
                    rot.oninput = () => { s.rot_days = parseInt(rot.value, 10) || 0; };
                    const up = iconButton(I.up, 'Move up');
                    up.onclick = () => { if (i > 0) { working.splice(i - 1, 0, working.splice(i, 1)[0]); paint(); } };
                    const rm = iconButton(I.x, 'Remove stage');
                    rm.onclick = () => { working.splice(i, 1); paint(); };
                    r.append(name, prob, rot, up, rm);
                    rows.append(r);
                });
            }
            paint();
            const addBtn = textButton(null, { cls: 'disp-addbox' }); addBtn.append(ico(I.plus), document.createTextNode('Add a stage'));
            addBtn.onclick = () => { working.push({ name: '', probability: 100, rot_days: 0 }); paint(); };
            sb.append(addBtn);
            const bar = el('div', 'disp-actions');
            const save = textButton('Save stages', { kind: 'primary' });
            save.onclick = async () => {
                save.disabled = true;
                try { await crmOp('/api/crm/stages', { stages: working }); m.close(); }
                catch (e) { save.disabled = false; toastError(e.message); }
            };
            bar.append(save); sb.append(bar);
            m.body.append(sb);

            /* ---- labels, with their colours ---- */
            const lb = el('div', 'crm-focus');
            lb.append(el('div', 'disp-subhead', 'Deal labels'));
            const lrows = el('div'); lb.append(lrows);
            const labs = (crmCache.labels || []).map(n => ({
                name: n, color: (crmCache.label_colors || {})[n] || 'gray' }));
            const COLOR_OPTS = ['red', 'orange', 'yellow', 'green', 'blue', 'purple',
                                'pink', 'brown', 'gray', 'dark-gray'];
            function paintLabs() {
                lrows.innerHTML = '';
                labs.forEach((l, i) => {
                    const r = el('div', 'disp-boxrow');
                    const dot = el('span', 'crm-dot');
                    dot.style.cssText = 'align-self:center;background:' + (CRM_COLOR_CSS[l.color] || 'var(--text-tertiary)');
                    const name = crmText(l.name, 'Label'); name.oninput = () => { l.name = name.value; };
                    const col = el('select', 'disp-text');
                    col.setAttribute('aria-label', 'Label colour');
                    col.style.maxWidth = 'var(--field-w-md)';
                    COLOR_OPTS.forEach(c => col.append(new Option(c, c)));
                    col.value = COLOR_OPTS.includes(l.color) ? l.color : 'gray';
                    col.onchange = () => { l.color = col.value; paintLabs(); };
                    const rm = iconButton(I.x, 'Remove label');
                    rm.onclick = () => { labs.splice(i, 1); paintLabs(); };
                    r.append(dot, name, col, rm);
                    lrows.append(r);
                });
            }
            paintLabs();
            const addLab = textButton(null, { cls: 'disp-addbox' }); addLab.append(ico(I.plus), document.createTextNode('Add a label'));
            addLab.onclick = () => { labs.push({ name: '', color: 'gray' }); paintLabs(); };
            lb.append(addLab);
            const lbar = el('div', 'disp-actions');
            const lsave = textButton('Save labels', { kind: 'primary' });
            lsave.onclick = async () => {
                lsave.disabled = true;
                try { await crmOp('/api/crm/stages', { labels: labs.filter(l => l.name.trim()) }); m.close(); }
                catch (e) { lsave.disabled = false; toastError(e.message); }
            };
            lbar.append(lsave); lb.append(lbar);
            m.body.append(lb);

            /* ---- lost reasons ---- */
            const lr = el('div', 'crm-focus');
            lr.append(el('div', 'disp-subhead', 'Lost reasons'));
            lr.append(el('p', 'field-help', 'One per line. These feed the "Why deals are lost" chart.'));
            const lrTa = document.createElement('textarea');
            lrTa.className = 'lia-chase-body'; lrTa.rows = 5;
            lrTa.value = (crmCache.lost_reasons || []).join('\n');
            lr.append(lrTa);
            const rbar = el('div', 'disp-actions');
            const rsave = textButton('Save reasons', { kind: 'primary' });
            rsave.onclick = async () => {
                rsave.disabled = true;
                try {
                    await crmOp('/api/crm/stages', {
                        lost_reasons: lrTa.value.split('\n').map(s => s.trim()).filter(Boolean) });
                    m.close();
                } catch (e) { rsave.disabled = false; toastError(e.message); }
            };
            rbar.append(rsave); lr.append(rbar);
            m.body.append(lr);

            /* ---- the follow-up nag ---- */
            const fp = el('div', 'crm-focus');
            fp.append(el('div', 'disp-subhead', 'Follow-ups'));
            const fu = tickRow('crm-cline');
            const fcb = document.createElement('input'); fcb.type = 'checkbox';
            fcb.checked = crmCache.settings.followup_popup !== false;
            fcb.onchange = async () => {
                try { await crmOp('/api/crm/stages', { followup_popup: fcb.checked }); }
                catch (e) { fcb.checked = !fcb.checked; toastError(e.message); }
            };
            fu.append(fcb, document.createTextNode(
                ' Prompt for the next activity when a deal’s last one is completed'));
            fp.append(fu);
            m.body.append(fp);
        }

        /* ---------------- insights ---------------- */
        function renderCRMInsights(host) {
            const d = crmCache;
            const deals = Object.values(d.deals);
            /* The split that keeps the numbers honest: the OPEN pipeline is
               only what is actually on the desk (archived-but-open deals left
               it), while won/lost HISTORY includes the archived back catalogue
               - that history is the whole point of having imported it. */
            const open = deals.filter(x => x.status === 'open' && !x.archived);
            const won = deals.filter(x => x.status === 'won');
            const lost = deals.filter(x => x.status === 'lost');
            const month = crmCache.today.slice(0, 7);
            const prevMonth = new Date(Date.parse(month + '-01') - 86400000).toISOString().slice(0, 7);
            const wonThis = won.filter(x => (x.won_at || '').slice(0, 7) === month)
                .reduce((n, x) => n + (x.value || 0), 0);
            const wonPrev = won.filter(x => (x.won_at || '').slice(0, 7) === prevMonth)
                .reduce((n, x) => n + (x.value || 0), 0);
            const winRate = (won.length + lost.length) ? Math.round(won.length / (won.length + lost.length) * 100) : null;
            const cycles = won.map(x => (Date.parse(x.won_at) - Date.parse(x.created_at)) / 86400000).filter(n => !isNaN(n));
            const avgCycle = cycles.length ? Math.round(cycles.reduce((a, b) => a + b, 0) / cycles.length) : null;
            /* The house KPI strip, as every other screen draws its figures: the
               Liability tiles it borrowed set sentences ('no closed deals') in
               the figure slot, painted a £0 month green, and stopped short of
               the charts under them. A figure with nothing behind it says so as
               its note, month on month is the change pill, and colour is not
               spent on a draw. */
            const mom = wonPrev ? (wonThis - wonPrev) / wonPrev : null;
            host.append(metricsStrip([
                { label: 'Open pipeline', value: crmMoney(open.reduce((n, x) => n + (x.value || 0), 0)) },
                { label: 'Weighted', value: crmMoney(open.reduce((n, x) => n + (x.weighted_value || 0), 0)) },
                { label: 'Won this month', value: crmMoney(wonThis),
                  delta: mom == null ? null : ((mom >= 0 ? '+' : '') + Math.round(mom * 100) + '%'),
                  trend: mom == null ? null : (mom > 0 ? 'up' : mom < 0 ? 'down' : 'flat'),
                  note: mom == null ? null : 'against last month' },
                { label: 'Win rate', value: winRate == null ? '0%' : winRate + '%', note: winRate == null ? 'no deals closed yet' : null },
                { label: 'Average cycle', value: avgCycle == null ? 'None' : avgCycle + ' days', note: avgCycle == null ? 'no wins yet' : null },
            ]));
            /* Charts side by side. A bar track 860px wide encodes exactly one
               number, so extra width was going into decoration while the funnel
               and the loss reasons sat a screen apart. */
            const charts = el('div', 'crm-charts'); host.append(charts);
            /* Each chart is a CARD, the way the reference builds a chart and
               the way the deals and contacts tabs beside this one are built.
               They were bare bordered boxes with a bold line on top, which is
               a card missing its header rather than a different thing. */
            function bars(title, desc, rows, fmt, empty, o) {
                o = o || {};
                const box2 = el('div', o.cols ? 'card crm-wide' : 'card');
                const bh = el('div', 'card-head');
                /* A counting rule is the title's info button; descriptions that
                   restated the title went (copy plan, CRM #11 to #15). */
                const bt = el('h3', 'card-title', title);
                bh.append(desc ? titleInfo(bt, infoButton('About ' + title, { title: title, body: desc })) : bt);
                /* The bars go in a body of their own rather than straight into
                   the card: the card's 16px gap is the rhythm between its
                   BLOCKS, and applied to twelve bar rows it turned a chart into
                   a ladder. */
                const body = el('div', 'crm-bars');
                box2.append(bh, body);
                const max = Math.max.apply(null, rows.map(r => r[1]).concat([1]));
                rows.forEach(([lab, v]) => {
                    const r = el('div', 'crm-bar-row');
                    r.append(el('span', 'crm-bar-lab', lab));
                    const track = el('div', 'crm-bar-track');
                    const fill = el('div', 'crm-bar-fill');
                    fill.style.width = Math.max(2, v / max * 100) + '%';
                    track.append(fill); r.append(track);
                    r.append(el('span', 'crm-bar-val', fmt ? fmt(v) : String(v)));
                    body.append(r);
                });
                /* Each chart says what fills it: wins, close dates, stages,
                   losses or done activities are not the same wait. */
                if (!rows.length) body.append(el('div', 'empty', empty || 'Nothing to chart yet.'));
                /* Across the row as columns, each with its value over it (12 Oct
                   2026, OPS-24); the bar rows stay for a phone. */
                if (o.cols && rows.length) {
                    const colsEl = el('div', 'crm-months');
                    rows.forEach(([lab, v]) => {
                        const c = el('div', 'crm-month');
                        const track = el('div', 'crm-month-track'); const bar = el('div', 'crm-month-bar');
                        bar.style.height = Math.max(2, v / max * 100) + '%'; track.append(bar);
                        c.append(el('span', 'crm-month-v', fmt ? fmt(v) : String(v)), track, el('span', 'crm-month-l', lab));
                        colsEl.append(c);
                    });
                    box2.insertBefore(colsEl, body);
                }
                charts.append(box2);
                /* The BODY, so a caller's footnote lands under the bars it is
                   about rather than in the card's block rhythm. */
                return body;
            }
            const niceMonth = k => new Date(k + '-01T12:00:00')
                .toLocaleDateString('en-GB', { month: 'short', year: '2-digit' });
            /* Deals won over time: the classic monthly view. */
            const byMonth = {};
            won.forEach(x => { const k = (x.won_at || '').slice(0, 7); if (k) byMonth[k] = (byMonth[k] || 0) + (x.value || 0); });
            bars('Won by month', null,
                Object.keys(byMonth).sort().slice(-12).map(k => [niceMonth(k), Math.round(byMonth[k])]), crmMoney,
                'No deals won yet.', { cols: true });
            /* The forecast Pipedrive sells separately: open deals by their
               expected close month, both the raw sum and the weighted one. */
            const fc = {};
            open.forEach(x => {
                const k = (x.expected_close || '').slice(0, 7);
                if (k && k >= month) {
                    fc[k] = fc[k] || [0, 0];
                    fc[k][0] += x.value || 0; fc[k][1] += x.weighted_value || 0;
                }
            });
            const noDate = open.filter(x => !x.expected_close).length;
            const fcBox = bars('Expected to close', null,
                Object.keys(fc).sort().slice(0, 8)
                .map(k => [niceMonth(k), Math.round(fc[k][0])]), crmMoney,
                'No expected close dates ahead.');
            if (noDate) fcBox.append(el('div', 'crm-sub',
                noDate + ' open ' + (noDate === 1 ? 'deal has' : 'deals have')
                + ' no close date.'));
            /* Funnel: a won deal counts as having completed every stage. */
            const idx = {}; d.stages.forEach((s, i) => idx[s.id] = i);
            const funnel = d.stages.map((s, i) => {
                const reached = deals.filter(x => x.status === 'won'
                    || (x.status !== 'won' && (idx[x.stage_id] != null ? idx[x.stage_id] : -1) >= i)).length;
                return [s.name, reached];
            });
            bars('How far deals get', 'How many deals have reached each stage. A win counts as every stage.', funnel,
                null, 'No pipeline stages yet.');
            const reasons = {};
            lost.forEach(x => { const k = x.lost_reason || 'No reason given'; reasons[k] = (reasons[k] || 0) + 1; });
            bars('Why deals are lost', null,
                Object.entries(reasons).sort((a, b) => b[1] - a[1]), null,
                'No deal has been marked lost yet.');
            const cutoff = new Date(Date.now() - 30 * 86400000).toISOString();
            const doneCounts = {};
            Object.values(d.activities).filter(a => a.done && (a.done_at || '') >= cutoff)
                .forEach(a => { doneCounts[a.type] = (doneCounts[a.type] || 0) + 1; });
            bars('Activities completed, last 30 days', null,
                CRM_TYPES.map(([k, lab]) => [lab, doneCounts[k] || 0]).filter(r => r[1] > 0), null,
                'Nothing done in the last 30 days.');
        }

