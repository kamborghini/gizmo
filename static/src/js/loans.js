        /* ---------- Loan units ----------
           Which loan projectors are out, with whom, and how long they have
           been gone. Two objects, because they answer different questions: a
           UNIT is a thing the shop owns, a LOAN is one trip it made. */
        let loansCache = null;
        function showLoansView() { if (loansCache) renderLoans(); else loadLoans(); }
        /* The borrower field suggests CRM contacts, and the CRM's own cache is
           only filled when somebody opens that tab. Warm it in the background
           when this page opens, or the suggestions are silently dead for
           anyone who came straight here. Best effort: a CRM that will not load
           must not stop a projector going out. */
        function loansWarmCrm() {
            if (crmCache && crmCache.persons) return;
            api('/api/crm/board', {}).then(r => {
                /* Dated like any other load: at zero, the next CRM visit took
                   the copy for ancient and fetched the whole board again. */
                if (r && r.crm && !crmCache) { crmCache = r.crm; crmRev = r.rev || ''; crmLoadedAt = Date.now(); }
            }).catch(() => {});
        }
        async function loadLoans(quiet) {
            loansWarmCrm();
            const box = $('loans-content');
            if (!quiet) { box.innerHTML = ''; box.append(el('div', 'thinking'), loader()); }
            try { loansCache = await api('/api/loans', { op: 'board' }); }
            catch (e) { box.innerHTML = ''; box.append(el('div', 'msg error',
                el('div', 'bubble', e.message || 'Could not read the loan register.'))); return; }
            renderLoans();
        }
        function sheetModal(title) {
            return dialog({ title: title, size: 'disp-modal' });
        }
        function loanDays(n) { return n === 1 ? '1 day out' : n + ' days out'; }
        function loanOutModal(unit, choices) {
            const m = sheetModal(unit ? 'Loan out ' + (unit.name || 'a unit') : 'Loan out a unit');
            const grid = el('div', 'disp-addr-grid'); m.body.append(grid);
            /* From the header (12 Oct 2026): which unit is going, from those on the shelf. */
            let unitSel = null;
            if (!unit) {
                unitSel = el('select', 'disp-text');
                (choices || []).forEach(u => unitSel.append(new Option(u.name + (u.model ? ' (' + u.model + ')' : ''), String(u.id))));
                crmField(grid, 'Unit', unitSel);
            }
            const whoIn = crmText('', 'Company or person');
            /* Type freely; matching CRM contacts are offered, and picking one
               links the loan to that record so a company's history is one
               place rather than several spellings of its name. */
            let pickedPerson = '', pickedOrg = '';
            crmField(grid, 'Going to', crmTypeahead(whoIn, function (q) {
                const rows = (typeof crmPersonRows === 'function' && crmCache && crmCache.persons)
                    ? crmPersonRows(q) : [];
                return rows.slice(0, 8);
            }, { pick: function (r) {
                whoIn.value = r.name;
                pickedPerson = r.id || '';
                const p = crmCache && crmCache.persons && crmCache.persons[r.id];
                pickedOrg = (p && p.org_id) || '';
            } }));
            whoIn.addEventListener('input', function () { pickedPerson = ''; pickedOrg = ''; });
            const phoneIn = crmText('', 'Optional');
            crmField(grid, 'Phone', phoneIn);
            const dueIn = document.createElement('input');
            dueIn.type = 'date'; dueIn.className = 'disp-text';
            crmField(grid, 'Due back', dueIn);
            const noteIn = crmText('', 'What went with it, condition, anything to remember');
            crmField(grid, 'Note', noteIn);
            m.body.append(el('p', 'field-help', 'Optional. Without one, it turns amber at the chase limit.'));
            const go = textButton('Loan it out', { kind: 'primary' });
            go.onclick = async () => {
                if (!whoIn.value.trim()) { toastError('Say who it is going to.'); return; }
                const chosen = unit || (choices || []).find(u => String(u.id) === unitSel.value);
                if (!chosen) return;
                go.disabled = true;
                try {
                    await api('/api/loans', { op: 'out', unit_id: chosen.id,
                        who_name: whoIn.value.trim(), phone: phoneIn.value.trim(),
                        due_at: dueIn.value || '', note: noteIn.value.trim(),
                        crm_person_id: pickedPerson, crm_org_id: pickedOrg });
                    m.close(); toastOk((chosen.name || 'The unit') + ' is out with ' + whoIn.value.trim() + '.');
                    loadLoans(true);
                } catch (e) { go.disabled = false; toastError(e.message); }
            };
            const barGo = el('div', 'mail-statebar');
            barGo.append(go);
            m.body.append(barGo);
        }
        function loanUnitModal(unit) {
            const u = unit || {};
            const m = sheetModal(u.id ? ('Edit ' + (u.name || 'unit')) : 'Add a loan unit');
            const grid = el('div', 'disp-addr-grid'); m.body.append(grid);
            const nameIn = crmText(u.name || '', 'Loan 3');
            const modelIn = crmText(u.model || '', 'Epson EB-2250U');
            const serialIn = crmText(u.serial || '', 'Serial or asset tag');
            const notesIn = crmText(u.notes || '', 'Anything worth knowing');
            /* Search the shop rather than retype it. A pick fills the MODEL and
               remembers the product and variant; the NAME is left alone,
               because two units can be the same product and only the name and
               serial say which one is at Harbour AV. */
            let picked = { product_id: u.product_id || '', variant_id: u.variant_id || '',
                           sku: u.sku || '' };
            const findIn = crmText('', 'Search the shop, for example Optoma');
            let findRows = [];
            crmField(grid, 'Find in the shop', crmTypeahead(findIn, function () {
                return findRows;
            }, { pick: function (r) {
                findIn.value = '';
                modelIn.value = r.name;
                picked = { product_id: r.product_id || '', variant_id: r.variant_id || '',
                           sku: r.sku || '' };
                if (!serialIn.value.trim() && r.sku) serialIn.placeholder = 'SKU ' + r.sku;
                foundNote.textContent = 'From the shop: ' + r.name
                    + (r.sku ? ' (' + r.sku + ')' : '');
            } }));
            const foundNote = el('div', 'field-help', picked.sku
                ? ('Linked to the shop' + (picked.sku ? ' (' + picked.sku + ')' : '')) : '');
            let findTimer = null, repainting = false;
            findIn.addEventListener('input', function () {
                /* The repaint below is an input event too; answering it
                   would read the catalogue again, forever. */
                if (repainting) return;
                clearTimeout(findTimer);
                const q = findIn.value.trim();
                if (q.length < 2) { findRows = []; return; }
                findTimer = setTimeout(async () => {
                    if (!findIn.isConnected) return;
                    try {
                        const r = await api('/api/loans', { op: 'products', q: q });
                        findRows = (r.products || []).map(x => ({
                            id: x.variant_id || x.product_id, name: x.title,
                            sub: [x.sku, x.vendor].filter(Boolean).join(' \u00b7 '),
                            product_id: x.product_id, variant_id: x.variant_id, sku: x.sku }));
                    } catch (e) {
                        findRows = [];
                        foundNote.textContent = e.message;
                    }
                    if (!findIn.isConnected) return;
                    /* The dropdown paints from the last keystroke, so ask
                       for it again now the rows are actually here. */
                    repainting = true;
                    try { findIn.dispatchEvent(new Event('input', { bubbles: false })); }
                    finally { repainting = false; }
                }, 220);
            }, true);
            crmField(grid, 'Name', nameIn);
            crmField(grid, 'Model', modelIn);
            crmField(grid, 'Serial', serialIn);
            crmField(grid, 'Notes', notesIn);
            m.body.append(foundNote);
            const save = textButton('Save unit', { kind: 'primary' });
            save.onclick = async () => {
                if (!nameIn.value.trim()) { toastError('Give the unit a name, for example Loan 3.'); return; }
                save.disabled = true;
                try {
                    await api('/api/loans', { op: 'unit_save', unit_id: u.id || '',
                        name: nameIn.value.trim(), model: modelIn.value.trim(),
                        serial: serialIn.value.trim(), notes: notesIn.value.trim(),
                        product_id: picked.product_id, variant_id: picked.variant_id,
                        sku: picked.sku });
                    m.close(); loadLoans(true);
                } catch (e) { save.disabled = false; toastError(e.message); }
            };
            const barSave = el('div', 'mail-statebar');
            barSave.append(save);
            /* Retiring and deleting are different things and both are wanted.
               Retire is the reversible one on the row; this is the other one,
               and it takes the unit and everything it ever did with it. It
               lives here rather than on the row because the row already
               carries six controls, and because deleting should cost the
               extra click of opening the record first. */
            if (u.id) {
                const del = textButton('Delete permanently', { kind: 'danger' });
                del.classList.add('push-end');
                del.onclick = async () => {
                    const outNow = ((loansCache || {}).out || [])
                        .find(r => r.unit && r.unit.id === u.id);
                    if (!await uiConfirm('Delete ' + (u.name || 'this unit')
                        + ' and its whole loan history? This cannot be undone.'
                        + (outNow ? ' It is out with ' + (outNow.who_name || 'a customer')
                                    + ' right now, and that record goes too.' : '')
                        + ' Retiring keeps the history instead.',
                        { title: 'Delete unit', okText: 'Delete it', danger: true })) return;
                    del.disabled = true;
                    try {
                        await api('/api/loans', { op: 'unit_delete', unit_id: u.id });
                        toastOk((u.name || 'That unit') + ' is off the register.');
                        m.close(); loadLoans(true);
                    } catch (e) { del.disabled = false; toastError(e.message); }
                };
                barSave.append(del);
            }
            m.body.append(barSave);
        }
        async function loanHistoryModal(unit) {
            const m = sheetModal((unit.name || 'Unit') + ' history');
            m.body.append(el('div', 'thinking'), loader());
            let r;
            try { r = await api('/api/loans', { op: 'history', unit_id: unit.id }); }
            catch (e) { m.body.innerHTML = ''; m.body.append(el('div', 'msg error', el('div', 'bubble', e.message))); return; }
            m.body.innerHTML = '';
            const rows = r.history || [];
            if (!rows.length) { m.body.append(el('div', 'empty', 'This one has never been out.')); return; }
            /* A small table (12 Oct 2026): who had it, when it went, when it came back. */
            m.body.append(dtable([{ head: 'With' }, { head: 'Out', cap: true }, { head: 'Back', cap: true }],
                rows.map(h => ({ cells: [h.who_name || 'Someone', fmtDate(h.out_at),
                    h.back_at ? fmtDate(h.back_at) : el('span', 'dt-warn', 'Still out')] })),
                { cls: 'dt-loan-hist', label: (unit.name || 'Unit') + ' history', stop: 's' }));
        }
        /* The serial sticker. Built like a production label so it prints on the
           same printer and through the same font gate, but always at 4x4:
           the sticker is a permanent fixture on the machine, not part of
           whatever run is loaded in the printer today. */
        function loanStickerSheet(d) {
            const sheet = el('div', 'label-sheet loan-sticker');
            /* .label-sheet's stylesheet width is 100x150mm, so a sheet that
               sets no size of its own lays out at 4x6 whatever the page rule
               says. Every other print path sizes its sheet; this one did not. */
            const sd = stickerDims();
            sheet.style.width = sd.w + 'mm'; sheet.style.height = sd.h + 'mm';
            const top = el('div', 'ls-top');
            const logo = el('div', 'ls-logo');
            logo.innerHTML = LABEL_LOGO;      /* our own static markup, as the label does */
            top.append(logo);
            sheet.append(top);
            const tag = el('div', 'ls-tag', d.tag || '');
            sheet.append(tag);
            const who = el('div', 'ls-unit');
            who.append(el('div', 'ls-company', (d.unit && d.unit.name) || ''));
            const sub = [(d.unit && d.unit.model) || '', (d.unit && d.unit.serial)
                ? 'S/N ' + d.unit.serial : ''].filter(Boolean).join('  \u00b7  ');
            if (sub) who.append(el('div', 'ls-ono', sub));
            sheet.append(who);
            const codes = el('div', 'ls-codes');
            const bc = document.createElement('img');
            bc.className = 'ls-barcode'; bc.alt = 'Barcode ' + (d.tag || '');
            bc.src = d.barcode || '';
            const qr = document.createElement('img');
            qr.className = 'ls-qr'; qr.alt = 'QR ' + (d.tag || '');
            qr.src = d.qr || '';
            codes.append(bc, qr);
            sheet.append(codes);
            return sheet;
        }
        async function loanPrintSticker(unit, btn) {
            btn.disabled = true;
            let d;
            try { d = await api('/api/loans', { op: 'sticker', unit_id: unit.id }); }
            catch (e) { btn.disabled = false; toastError(e.message); return; }
            const seq = ++printSeq;
            const box = $('label-print'); box.innerHTML = '';
            const dims = stickerDims();
            let rule = $('label-page-rule');
            if (!rule) { rule = document.createElement('style'); rule.id = 'label-page-rule'; document.head.append(rule); }
            rule.textContent = labelPrintCss(dims);
            box.append(loanStickerSheet(d));
            const cleanup = () => {
                /* The button and the row are this print's own, whichever
                   print holds the box now, so an overtaken sticker gives them
                   back too; returning first left the button dead. */
                btn.disabled = false;
                loadLoans(true);      /* the tag is minted now; the row says Reprint */
                if (seq !== printSeq) return;
                document.body.classList.remove('printing-label');
                box.innerHTML = '';
                const r = $('label-page-rule');
                if (r && r.parentNode) r.parentNode.removeChild(r);
            };
            /* The codes are images: printing before they decode prints blank
               squares. Wait for them and for the label typeface, both capped. */
            const imgs = [...box.querySelectorAll('img')];
            const ready = Promise.all(imgs.map(im => im.complete ? Promise.resolve()
                : new Promise(res => { im.onload = res; im.onerror = res; })));
            /* Waited for, never depended on. document.fonts.load REJECTS when
               the typeface cannot be fetched, and an unhandled rejection here
               abandoned the print and left the button dead. A cap already says
               a slow font must not mean no printout; a broken one is the same
               problem, so both fall through to printing. */
            await Promise.race([Promise.all([ready, labelFontReady()]),
                                new Promise(res => setTimeout(res, 3000))])
                .catch(() => {});
            /* Another print may have started during that wait. The box and
               the page rule are its now: printing here would print its page,
               and it opens its own dialog. */
            if (seq !== printSeq) { cleanup(); return; }
            document.body.classList.add('printing-label');
            setTimeout(() => {
                if (seq !== printSeq) { cleanup(); return; }
                window.print(); setTimeout(cleanup, 800); }, 40);
        }
        function renderLoans() {
            const d = loansCache || {}; const box = $('loans-content'); box.innerHTML = '';
            /* Under the header every block is a card the grid can move, each
               spanning the row; the header's action slot is where Customize goes. */
            const units = d.units || [];
            /* The page's one teal (12 Oct 2026): Loan out, which asks which unit
               is going, from those on the shelf. Each shelf row keeps its own,
               secondary. */
            const shelf = units.filter(u => u.status === 'in');
            const lend = shelf.length ? textButton(null, { kind: 'primary', small: true }) : null;
            if (lend) {
                lend.type = 'button';
                lend.append(ico(I.logOut), document.createTextNode('Loan out'));
                lend.onclick = () => loanOutModal(null, shelf);
            }
            box.append(pageHead({ view: 'loans', title: 'Loan units', line: 'Projectors out on loan, and for how long.', actions: lend ? [lend] : [] }));
            const counts = d.counts || { out: 0, in: 0, late: 0 };
            /* Three stats, three columns: on the shared four-column grid the
               empty fourth cell read as a KPI that had failed to load. */
            const mgrid = metricsStrip([
                { label: 'Out now', value: String(counts.out) },
                { label: 'On the shelf', value: String(counts.in) },
                /* Red when there is one; the rows' Overdue tags say what it means. */
                { label: 'Overdue', value: String(counts.late), tone: counts.late ? 'bad' : '' }]);
            box.append(widget(mgrid, 'counts', 'full', 'Loan counts'));

            /* ---- what is out: a table, longest out first (12 Oct 2026) ---- */
            const oCard = el('div', 'card');
            const oHead = el('div', 'card-head');
            oHead.append(el('h3', 'card-title', 'Out now'));
            if (d.can_manage) {
                /* The chase limit, beside the rows it colours (12 Oct 2026): it
                   was a card of its own under the register. */
                const chase = el('div', 'card-act loan-chase');
                const days = document.createElement('input');
                days.type = 'number'; days.min = '1'; days.max = '365'; days.className = 'field-sm loan-chase-days';
                days.value = String((d.settings || {}).chase_days || 28);
                days.setAttribute('aria-label', 'Amber after this many days without a due date');
                const save = textButton('Save', { small: true }); save.type = 'button';
                save.onclick = async () => {
                    save.disabled = true;
                    try { await api('/api/loans', { op: 'settings', chase_days: Number(days.value) });
                          toastOk('Saved.'); loadLoans(true); }
                    catch (e) { toastError(e.message); }
                    save.disabled = false;
                };
                chase.append(el('span', 'lbl-meta', 'No due date: amber after'), days, el('span', 'lbl-meta', 'days'), save);
                oHead.append(chase);
            }
            oCard.append(oHead);
            const out = d.out || [];
            const outHead = el('span', 'dt-sorted'); outHead.append(document.createTextNode('Out'), ico(I.arrowDown));
            oCard.append(dtable([{ head: 'Unit', cls: 'stack ind' }, { head: 'With', cls: 'stack' }, { head: outHead, cls: 'sort' },
                                 { head: 'Due back' }, { head: '', cls: 'act' }],
                out.map(r => {
                    const due = el('span', 'dt-name');
                    if (r.state === 'late' && r.due_at) due.append(el('span', 'dt-bad', fmtDate(r.due_at)), el('span', 'lbl-chip bad', 'Overdue'));
                    else if (r.due_at) due.append(document.createTextNode(fmtDate(r.due_at)));
                    else due.append(el('span', r.state === 'due' ? 'dt-warn' : 'dt-muted', 'No due date'));
                    const who = document.createDocumentFragment();
                    who.append(el('span', 'dt-name', r.who_name || 'Someone'));
                    if (r.phone) who.append(el('span', 'dt-sub', r.phone));
                    const back = textButton(null, { small: true });
                    back.append(ico(I.logIn), document.createTextNode('Book back in'));
                    back.onclick = async () => {
                        if (!await uiConfirm((r.unit.name || 'This unit') + ' is back from '
                            + (r.who_name || 'the customer') + '?',
                            { title: 'Book back in', okText: 'It is back' })) return;
                        back.disabled = true;
                        try { await api('/api/loans', { op: 'back', loan_id: r.id });
                              toastOk((r.unit.name || 'Unit') + ' is back on the shelf.');
                              loadLoans(true); }
                        catch (e) { back.disabled = false; toastError(e.message); }
                    };
                    return { cls: 'two', cells: [dtMain(r.unit.name, r.unit.model,
                                r.state === 'late' ? 'bad' : r.state === 'due' ? 'warn' : 'ok'),
                            who, r.days_out === 1 ? '1 day' : r.days_out + ' days', due, back] };
                }),
                { cls: 'dt-loans-out', label: 'Out now', empty: el('div', 'empty', 'Everything is on the shelf.') }));
            /* With no units at all the register's empty state is the page's one:
               'Nothing is out' over 'No loan units yet' said it twice. */
            if (units.length) box.append(widget(oCard, 'out'));

            /* ---- the register: a table, every action in a column of its own ---- */
            const rCard = el('div', 'card');
            const rHead = el('div', 'card-head');
            rHead.append(el('h3', 'card-title', 'The register'));
            if (d.can_manage) {
                const add = textButton(null, { small: true });
                add.append(ico(I.plus), document.createTextNode('Add a unit'));
                add.onclick = () => loanUnitModal(null);
                const act = el('div', 'card-act'); act.append(add); rHead.append(act);
            }
            rCard.append(rHead);
            const withWhom = {};
            out.forEach(r => { if (r.unit && r.unit.id) withWhom[r.unit.id] = r.who_name || ''; });
            let emptyReg;
            if (d.can_manage) {
                const first = textButton(); first.type = 'button';
                first.append(ico(I.plus), document.createTextNode('Add a unit'));
                first.onclick = () => loanUnitModal(null);
                emptyReg = emptyState({ icon: I.box, text: 'No loan units yet.', action: first });
            } else emptyReg = el('div', 'empty', 'No units in the register yet.');
            rCard.append(dtable([{ head: 'Unit', cls: 'stack' }, { head: 'Asset tag', cls: 'stack' }, { head: 'Status' },
                                 { head: '', cls: 'act' }, { head: '', cls: 'act' }],
                units.map(u => {
                    const tag = document.createDocumentFragment();
                    tag.append(u.asset_tag ? el('span', 'dt-name', u.asset_tag) : el('span', 'dt-muted', 'No tag'));
                    if (u.serial) tag.append(el('span', 'dt-sub', 'S/N ' + u.serial));
                    const st = el('span', 'dt-name');
                    st.append(el('span', 'dt-dot' + (u.status === 'in' ? ' ok' : u.status === 'retired' ? ' off' : '')),
                              document.createTextNode(u.status === 'out' ? 'Out' : u.status === 'retired' ? 'Retired' : 'On the shelf'));
                    /* A long name ends in an ellipsis in its column; the whole name shows on hover (13 Oct 2026). */
                    if (u.status === 'out' && withWhom[u.id]) { const who = el('span', 'dt-muted', withWhom[u.id]); who.title = withWhom[u.id]; st.append(who); }
                    let outB = '';
                    if (u.status === 'in') {
                        /* Secondary: the page's one teal is the header's Loan out. */
                        outB = textButton(null, { small: true });
                        outB.append(ico(I.logOut), document.createTextNode('Loan out'));
                        outB.onclick = () => loanOutModal(u);
                    }
                    const acts = document.createDocumentFragment();
                    const hist = textButton(null, { small: true });
                    hist.append(ico(I.history), document.createTextNode('History'));
                    hist.onclick = () => loanHistoryModal(u);
                    acts.append(hist);
                    if (d.can_manage || u.asset_tag) {
                        /* Minting happens once, so the button says which it is
                           doing: a first print assigns the number, every one
                           after is the same sticker again. Assigning the number
                           is an admin's; REPRINTING a tag that already exists is
                           anyone's, because a peeled label is found by whoever
                           is holding the projector. The tag is its own column. */
                        const sk = textButton(null, { small: true });
                        const sw = el('span', 'swap');
                        const w1 = el('span'); w1.append(ico(I.printer), document.createTextNode('Reprint'));
                        const w2 = el('span'); w2.append(ico(I.printer), document.createTextNode('Serial sticker'));
                        (u.asset_tag ? w2 : w1).setAttribute('aria-hidden', 'true');
                        sw.append(w1, w2); sk.append(sw);
                        sk.title = u.asset_tag
                            ? 'Print the sticker for ' + u.asset_tag + ' again'
                            : 'Assign this unit an asset tag and print its sticker';
                        sk.onclick = () => loanPrintSticker(u, sk);
                        acts.append(sk);
                    }
                    if (d.can_manage) {
                        const ed = iconButton(I.edit, 'Edit ' + u.name, { title: 'Edit this unit' });
                        ed.onclick = () => loanUnitModal(u);
                        /* Retiring keeps the history, so its mark is an archive box, not a bin. */
                        const rt = iconButton(u.status === 'retired' ? I.archiveRestore : I.archive, (u.status === 'retired' ? 'Unretire ' : 'Retire ') + u.name, { title: u.status === 'retired' ? 'Put it back in the register' : 'Retire this unit' });
                        rt.onclick = async () => {
                            const back = u.status === 'retired';
                            if (!back && !await uiConfirm('Retire ' + u.name
                                + '? It stays in the history but cannot be loaned out. '
                                + 'To remove it altogether, open it and choose Delete.',
                                { title: 'Retire unit', okText: 'Retire it', danger: true })) return;
                            try { await api('/api/loans', { op: 'unit_retire', unit_id: u.id,
                                                            unretire: back ? 1 : 0 });
                                  loadLoans(true); }
                            catch (e) { toastError(e.message); }
                        };
                        acts.append(ed, rt);
                    }
                    return { cls: 'two' + (u.status === 'retired' ? ' settled' : ''), cells: [
                        dtMain(u.name, u.model || (u.serial ? '' : 'no model or serial recorded')), tag, st, outB, acts] };
                }),
                { cls: 'dt-loans-reg', label: 'The register', empty: emptyReg }));
            box.append(widget(rCard, 'register'));

        }

        /* The connector's reconcile modes, in words. 'warn', 'strict' and
           'off' reached the screen as they are stored. */
        const CX_MODE = { warn: 'Send it and report the difference', strict: 'Hold it back', off: 'Do not check' };
        /* The Settings card sends only what was changed in it. The connector
           keeps a value the same as its default or its variable as no choice
           at all, so the whole form posted back would clear any choice saved
           on the connector's own tab that this form showed out of date. */
        function connSettingsChanges(shown, now) {
            const out = {};
            Object.keys(now).forEach(k => {
                const v = String(now[k] == null ? '' : now[k]).trim();
                if (v !== String(shown[k] == null ? '' : shown[k]).trim()) out[k] = v;
            });
            return out;
        }
        /* As the connector compares: numbers by value (0.020 is 0.02), the rest exactly. */
        function cxSameSetting(key, a, b) {
            return a === b || (['RECONCILE_TOLERANCE', 'MAX_DOCS_PER_RUN', 'RUNAWAY_ABORT_ABOVE'].includes(key)
                && a !== '' && b !== '' && !isNaN(a) && !isNaN(b) && Number(a) === Number(b));
        }
        /* Where a setting's value comes from, under its field: every field
           shows the value as it applies, so without this the default, the
           service's variable and a choice saved on the connector look the
           same. Once the field is changed, what Save will make of it. A
           connector that says nothing of sources gets no note (null). A saved
           choice carries its way back: what applies with nothing saved. */
        function connSettingNote(key, shown, now, s) {
            const from = s && s.sources && s.sources[key];
            const fb = s && s.fallbacks && s.fallbacks[key];
            if (!from || !fb) return null;
            const fbv = String(fb.value == null ? '' : fb.value).trim();
            const without = fb.from === 'env' ? 'Set by ' + key + ' on the connector service'
                : fbv ? 'The default' : 'Not set';
            const v = String(now == null ? '' : now).trim();
            if (v === String(shown == null ? '' : shown).trim()) {
                return from === 'settings' ? { text: 'Saved on the connector', back: fb } : { text: without };
            }
            return { text: (v === '' || cxSameSetting(key, v, fbv) ? without : 'Saved on the connector') + ' once you save' };
        }
        /* The form starts from the connector's settings as they are now, read
           again as it opens: the copy read with the page is never refreshed by
           the polling, and a choice made on the connector's own tab since
           would show here out of date. Settings that cannot be read are not
           opened. */
        async function connOpenSettings() {
            const d = (await connOp({ op: 'settings' })).data;
            if (!d) throw new Error('The connector sent no settings back.');
            connSettings = d; connSettingsEdits = {}; connSettingsOpen = true;
        }
        /* Sends what was changed, or nothing. "Saved" only for what the
           connector holds afterwards: it answered ok for a save it never kept,
           so the server reads the settings back and names what did not stick. */
        async function connSaveSettings(shown, now, labels) {
            const changes = connSettingsChanges(shown, now);
            const keys = Object.keys(changes);
            if (!keys.length) { toastOk('Nothing has changed, so there was nothing to save.'); return false; }
            const r = await connOp({ op: 'settings_save', fields: changes });
            const missed = (r && r.unapplied) || [];
            if (!missed.length) { toastOk('Saved. They apply to the next run.'); return true; }
            toastError('The connector did not keep ' + missed.map(k => labels[k] || k).join(', ') + '.'
                + (missed.length < keys.length ? ' The rest was saved.' : '')
                + ' Open the settings again to see what it holds.');
            return true;
        }
        function renderConnector() {
            const box = $('connector-content'); box.innerHTML = '';
            /* One line (copy plan, Xero sync #1). Whether Auto Run is on is the
               Connection card's tag, and with it on that tag says so. */
            /* Refresh reloads the page's data, so it is the header's, worded
               (12 Oct 2026); it sat in the Connection card's head. */
            const rf = textButton(null, { small: true }); rf.type = 'button';
            rf.append(ico(I.refresh), document.createTextNode('Refresh'));
            rf.onclick = () => { rf.disabled = true; refreshConnector().finally(() => { rf.disabled = false; }); };
            box.append(pageHead({ view: 'connector', title: 'Xero sync', line: 'Shopify orders, refunds and customers, sent into Xero.', actions: [rf] }));
            const lastRun = (connRuns || [])[0];
            box.append(financeTabs('connector',
                lastRun ? ('Last run ' + fmtDate(lastRun.finishedAt) + ', ' + londonHM(lastRun.finishedAt)) : ''));
            if (!connCache) { box.append(el('div', 'empty', 'Loading\u2026')); return; }
            if (connCache.available === false) {
                /* The same card shape as Forecast's own setup card beside it,
                   rather than a settings row's 14px title and 12px lines. */
                /* Built like the other setup cards (the accounts mailbox, Xero
                   on Reconciliation): a plain sentence, then the steps, with
                   each setting's name as something to copy rather than as
                   the sentence. Only an admin can do them, so only an admin
                   is given them. */
                const card = el('div', 'card');
                const head = el('div', 'card-head');
                /* The steps and the security note, word for word, behind the
                   title's info button (the mix, spec 8.3). They name the hosting
                   and its settings, so an admin sees them only on asking. */
                const lt = el('h3', 'card-title', 'Link the connector service');
                const linkHelp = [];
                head.append(lt);
                head.append(el('p', 'card-desc', 'Not linked to the Xero connector yet.'));
                card.append(head);
                if (connIsAdmin()) {
                    const steps = el('ol', 'setup-steps');
                    /* Text, with any setting or address as code, then the
                       setting to set on a line of its own. */
                    const step = (parts, code, value) => {
                        const li = el('li');
                        parts.forEach((x, i) => li.append(i % 2 ? el('code', 'setup-code', x) : document.createTextNode(x)));
                        if (code) {
                            const r2 = el('div', 'act-row'); r2.append(el('code', 'setup-code', code));
                            if (value) r2.append(document.createTextNode(' = '), el('code', 'setup-code', value));
                            li.append(r2);
                        }
                        steps.append(li);
                    };
                    step(['In Railway, open this app\u2019s service and its Variables.']);
                    step(['Set the connector service\u2019s address on Railway\u2019s private network. Its private domain ends ', '.railway.internal',
                          ' and is under its Settings, Networking. A public address has to be https.'],
                         'CONNECTOR_URL', 'http://<its private domain>:<its port>');
                    step(['Set the token: the same value as the connector service\u2019s own ', 'DASHBOARD_TOKEN', '.'], 'CONNECTOR_TOKEN');
                    step(['Let the app redeploy, then come back to this page.']);
                    linkHelp.push(steps);
                } else {
                    card.append(el('p', 'card-sub', 'An admin needs to link this.'));
                }
                linkHelp.push('The connector runs as its own service (shopify-xero-connector) with its own '
                    + 'ledger and failsafes. Reactor only drives it: credentials stay on that '
                    + 'service, and its token stays on this server.');
                titleInfo(lt, infoButton('Linking the connector', { title: 'Link the connector service', body: linkHelp }));
                box.append(card); return;
            }
            if (connCache.error) {
                box.append(loadFailure('The connector could not be reached. ' + cxDetail(connCache.error), refreshConnector));
                return;
            }
            const st = connCache.data || {};
            const cfg = st.config || {};
            const running = !!st.running;
            if (running) connStartWatch();

            /* ---- the band (12 Oct 2026) ----
               The ledger's figures, then after a hairline the connection: Xero
               linked and its store, and the Auto Run line with its button. The
               figures stood 460px apart over a Connection card that said again
               what a box under it said. The band has a widget id of its own, so
               a layout that hid the old figures or card does not hide it. */
            const led0 = st.ledger || {};
            const kpis = [];
            const kpi = (label, key, note, warnWhen) => {
                if (led0[key] == null) return;
                kpis.push({ label: label, value: Number(led0[key]).toLocaleString('en-GB'), note: note, tone: (warnWhen && led0[key] > 0) ? 'warn' : null });
            };
            /* The connector's ledger counts contacts with documents, as one
               figure, so the figure says so rather than pass for invoices. */
            kpi('Synced', 'synced', 'Invoices, credit notes and contacts');
            kpi('Failed', 'failed', null, true);
            /* The ledger counts what is held now and the log every document
               held, so when they differ the figure says which is which. */
            kpi('Quarantined', 'quarantined', st.quarantineCount != null && st.quarantineCount !== led0.quarantined
                ? st.quarantineCount + ' in the log' : null, true);
            /* No 'Blocked' figure: the connector's ledger counts synced, failed
               and quarantined documents only. */
            const band = el('div', 'band');
            const bandRow = el('div', 'band-row');
            if (kpis.length) bandRow.append(metricsStrip(kpis));
            const src = el('div', 'band-src');
            /* A state, so a dot and its word; the credentials sentence waits
               behind the heading's (i). */
            const srcHead = el('div', 'band-src-h', 'Connection');
            srcHead.append(infoButton('About the connection', { title: 'Connection', body: cfg.dryOnly
                ? 'Credentials and account mapping are incomplete on the connector service, so it can only review.'
                : 'Credentials and account mapping are held on the connector service, not here.' }));
            src.append(srcHead);
            const srcLine = (dot, k, v, end) => {
                const r = el('div', 'band-src-l');
                const kk = el('span', 'band-src-k'); kk.append(el('span', 'dt-dot ' + dot), document.createTextNode(k));
                const vv = el('span', 'band-src-v', v); vv.title = v;
                r.append(kk, vv);
                if (end && end.length) { const ee = el('span', 'band-src-e'); end.forEach(x => ee.append(x)); r.append(ee); }
                src.append(r);
            };
            srcLine(cfg.dryOnly ? '' : cfg.shop ? 'ok' : 'warn', cfg.dryOnly ? 'Reviews only' : (cfg.shop ? 'Xero linked' : 'Not configured'),
                cfg.shop || 'Not set on the service');
            /* ---- Auto Run ----
               The state shown is the SERVICE's, fetched every load. A toggle
               reflecting what this tab last clicked would read ON after a
               redeploy that started nothing, which is the one lie a control
               over unattended writing into the accounts must not tell. */
            if (connAuto) {
                const on = !!connAuto.enabled;
                const bits = [];
                if (on) bits.push('Every ' + (connAuto.intervalMinutes || 10) + ' minutes');
                if (on && connAuto.lastTickAt) bits.push('last check ' + fmtWhen(connAuto.lastTickAt));
                if (on && connAuto.nextTickAt) {
                    /* A next-tick time that has passed means the tab has been
                       open a while, or a check is running. "next 5 hours ago"
                       is nonsense; "due now" is the truth. */
                    bits.push(Date.parse(connAuto.nextTickAt) > Date.now()
                        ? 'next ' + fmtWhen(connAuto.nextTickAt) : 'next check due now');
                }
                const words = on ? bits.join(' \u00b7 ')
                    : 'Orders go only when ' + (connIsAdmin() ? 'you send' : 'an admin sends') + ' them.';
                /* The checks so far and the last outcome wait behind its (i). */
                const more = [];
                if (!on && connAuto.lastTickAt) more.push('The last check was ' + fmtWhen(connAuto.lastTickAt) + '.');
                if (connAuto.ticks) more.push(connAuto.ticks + ' checks so far.');
                /* The connector's own line has its own separator dots and a
                   '· 2 needing attention' tail; it is said in words here. */
                if (connAuto.lastOutcome && !(connAuto.lastOutcome === 'failed' && connAuto.lastError)) {
                    const parts = String(connAuto.lastOutcome).replace(/^skipped:\s*/i, 'skipped because ').split(' \u00b7 ');
                    const need = /^(\d+) needing attention$/.exec(parts[parts.length - 1] || '');
                    const head = cxPlain((need ? parts.slice(0, -1) : parts).join(', '));
                    more.push('Last outcome: ' + head.charAt(0).toLowerCase() + head.slice(1)
                        + (need ? ' (' + need[1] + (need[1] === '1' ? ' needs' : ' need') + ' attention)' : '') + '.');
                }
                const end = [];
                if (more.length) end.push(infoButton('About Auto Run', { title: on ? 'Auto Run on' : 'Auto Run off', body: more }));
                /* The switch sits on the line it switches. */
                if (connIsAdmin()) {
                    const t = textButton(on ? 'Turn Auto Run off' : 'Turn Auto Run on', { small: true });
                    t.onclick = async () => {
                        if (!on && !await uiConfirm(
                            'Turn Auto Run on? Every 10 minutes the connector will check for new '
                            + 'orders and send them to Xero without anyone reviewing them first. '
                            + 'It keeps going until you turn it off. An order already sent is '
                            + 'never sent twice.',
                            { title: 'Turn Auto Run on', okText: 'Turn it on' })) return;
                        t.disabled = true;
                        try {
                            await connOp({ op: 'autorun_set', enabled: !on });
                            toastOk(on ? 'Auto Run is off.' : 'Auto Run is on, every 10 minutes.');
                            await refreshConnector();
                        } catch (e) { t.disabled = false; toastError(e.message); }
                    };
                    end.push(t);
                }
                /* A state, not a success: a filled dot when on, a hollow one when off. */
                srcLine(on ? 'ok' : 'off', on ? 'Auto Run on' : 'Auto Run off', words, end);
            }
            bandRow.append(src);
            band.append(bandRow);
            if (connAuto && connAuto.lastError) {
                const n = el('p', 'band-notice');
                n.append(el('span', 'dt-dot bad'), el('span', null, 'The last Auto Run check failed. ' + cxDetail(connAuto.lastError) + ' It keeps trying.'));
                band.append(n);
            }
            box.append(widget(band, 'band', 'full', 'Figures and connection'));


            /* ---- review and send ---- */
            const admin = connIsAdmin();
            const rCard = el('div', 'card cx-card');
            const rHead = el('div', 'card-head');
            const rTitle = el('h3', 'card-title', 'Review and send');
            const rTitleInfo = infoButton('About review and send', { title: 'Review and send', body:
                'A review is a dry run: the service maps every eligible order and writes '
                + 'nothing. ' + (connIsAdmin() ? 'Send does exactly what the review showed.' : 'An admin sends exactly what it showed.') });
            rHead.append(titleInfo(rTitle, rTitleInfo));
            const rAct = el('div', 'card-act');
            const rev = textButton(null, { small: true });
            rev.append(ico(I.eye), document.createTextNode('Run review'));
            rev.disabled = running;
            rev.onclick = async () => {
                rev.disabled = true; connBusy = 'review'; connReview = null;
                try { await connOp({ op: 'review' }); connStartWatch(); renderConnector(); }
                catch (e) { connBusy = ''; toastError(e.message); rev.disabled = false; }
            };
            rAct.append(rev);
            /* A review that stopped itself says nothing should be sent, so it
               does not arm Send: the button and the card under it agree. */
            const revAborted = !!(connReview && connReview.result && connReview.result.aborted);
            if (admin) {
                const send = textButton(null, { kind: 'primary', small: true });
                send.append(ico(I.send), document.createTextNode('Send to Xero'));
                /* Review-before-send, enforced: the button only arms once a
                   completed review is on screen, and a Send spends it. */
                send.disabled = running || !connReview || revAborted;
                send.title = !connReview ? 'Run a review first: Send does what the review showed'
                    : revAborted ? 'The review stopped before it finished: run it again once that is resolved'
                    : 'Write the reviewed documents into Xero';
                send.onclick = async () => {
                    const r = (connReview || {}).result || {};
                    const inv = connCounts(r, 'invoices'), cn = connCounts(r, 'creditNotes'), ct = connCounts(r, 'contacts');
                    if (!await uiConfirm('Send to Xero now? Based on the review: '
                        + inv.created + (inv.created === 1 ? ' invoice' : ' invoices')
                        + (inv.updated ? ' (and ' + inv.updated + ' already in Xero updated in place)' : '') + ', '
                        + cn.created + (cn.created === 1 ? ' credit note' : ' credit notes') + ' and '
                        + ct.created + (ct.created === 1 ? ' new contact' : ' new contacts')
                        + ' will be written into your accounts.'
                        + (cxReviewCounts(r, 'invoices').voided ? ' ' + cxReviewCounts(r, 'invoices').voided
                            + (cxReviewCounts(r, 'invoices').voided === 1 ? ' invoice for a cancelled order will be voided.' : ' invoices for cancelled orders will be voided.') : ''),
                        { title: 'Send to Xero', okText: 'Send to Xero' })) return;
                    send.disabled = true; connBusy = 'send';
                    try { await connOp({ op: 'send' }); connStartWatch(); renderConnector(); }
                    catch (e) { connBusy = ''; toastError(e.message); renderConnector(); }
                };
                rAct.append(send);
            }
            rHead.append(rAct); rCard.append(rHead);

            /* One result section: what was checked, what it came to, and the
               table. Its key lets a filter or a page change put focus back. */
            const cxSection = (host, key, title, summary) => {
                const sec = el('section', 'cx-res conn-results');
                sec.dataset.cx = key;
                const h = el('div', 'cx-res-head');
                h.append(el('h4', 'cx-res-title', title));
                if (summary) h.append(el('p', 'cx-res-sum', summary));
                sec.append(h);
                host.append(sec);
                return sec;
            };
            /* ONE STATUS LINE (12 Oct 2026): a dot, which review or run it is
               and when, what it read, and how many need attention, with the
               list of them beside the matrix. The health box, the chip row and
               the section's own sentence told the same event three times. */
            const ctx = { guards: connHealth && connHealth.guards, admin: admin };
            const statl = el('div', 'cx-statl');
            const sWords = (t, cls) => {
                if (!t) return;
                if (statl.childNodes.length > 1) { const s2 = el('span', 'dot-sep'); s2.setAttribute('aria-hidden', 'true'); statl.append(s2); }
                statl.append(el('span', cls || null, t));
            };
            const sLead = (word, iso) => { const l = el('span'); l.append(el('b', null, word)); if (iso) l.append(document.createTextNode(' ' + fmtDate(iso) + ', ' + londonHM(iso))); statl.append(l); };
            /* Says WHAT is running: every job holds the same flag, and a tag
               check read as 'A run is in progress'. */
            const busyWords = !running ? '' : connTagBusy === 'check' ? 'A tag check is in progress\u2026'
                : connTagBusy === 'send' ? 'Sending tagged orders\u2026' : connBusy === 'review' ? 'A review is in progress\u2026'
                : connBusy === 'send' ? 'Sending to Xero\u2026' : connBusy === 'retry' ? 'Retrying\u2026'
                : 'The connector is busy\u2026';
            const reviewBusy = running && (connBusy === 'review' || connBusy === 'send' || connBusy === 'retry');
            const r = !reviewBusy && connReview && connReview.result;
            const attn = [];
            if (reviewBusy) {
                statl.append(loader(), el('span', null, connBusy === 'send' ? 'Sending to Xero\u2026'
                    : connBusy === 'retry' ? 'Retrying failed documents\u2026'
                    : 'Reviewing\u2026 this reads every eligible order and writes nothing.'));
            } else {
                const dotEl = el('span', 'dt-dot'); statl.append(dotEl);
                let dot = '';
                if (r) {
                    /* A review that stopped leads with the stop, in red, and its
                       matrix is what it found before stopping. */
                    const warns = r.warnings || [];
                    const nOrd = (r.ordersFetched || 0) + ((r.ordersFetched === 1) ? ' order' : ' orders');
                    sLead('Latest review', connReview.finishedAt);
                    sWords(revAborted ? nOrd + ' read, then it stopped; nothing was written' : nOrd + ' read, nothing written');
                    if (r.aborted) attn.push(['bad', cxProblem('run aborted: ' + r.aborted, ctx) + ' Nothing should be sent until that is resolved.']);
                    warns.forEach(w => attn.push(['warn', cxProblem(w)]));
                    dot = r.aborted ? 'bad' : warns.length ? 'warn' : 'ok';
                } else if (lastRun && !lastRun.dryRun) {
                    /* No review since the last send: the line is about that send. */
                    const lr = lastRun.result || {};
                    const inv = connCounts(lr, 'invoices'), cn = connCounts(lr, 'creditNotes');
                    sLead('Last send', lastRun.finishedAt);
                    if (lastRun.error) attn.push(['bad', 'It failed. ' + cxDetail(lastRun.error)]);
                    else sWords((lastRun.ok ? '' : 'It had failures. ') + inv.created + (inv.created === 1 ? ' invoice' : ' invoices')
                        + ' and ' + cn.created + (cn.created === 1 ? ' credit note' : ' credit notes') + ' written');
                    sWords('No review since');
                    dot = lastRun.ok ? 'ok' : 'bad';
                } else if (connHealth && connHealth.lastRunAt) {
                    /* What the last run left behind, dated: undated, a red box
                       from 5 Sep read as today's news. A review writes nothing,
                       so one that needs attention is amber; red is kept for a
                       send, which touched the accounts. */
                    const bad = !!connHealth.needsAttention;
                    const kind = connHealth.lastRunDryRun === true ? 'review' : connHealth.lastRunDryRun === false ? 'send' : 'run';
                    const head = cxPlain(String(connHealth.line || '').split(' \u00b7 ')[0]).replace(/[.\s]+$/, '');
                    const tone = kind === 'review' ? 'warn' : 'bad';
                    sLead('Last ' + kind, connHealth.lastRunAt);
                    if (bad) {
                        const probs = connHealth.problems || [];
                        /* 'The run failed before it could report' over 'run
                           failed: ...' said it twice; the problem is the one
                           with news. */
                        if (head && !(/^The run failed/i.test(head) && probs.some(p2 => /^run failed:/i.test(p2)))) attn.push([tone, head + '.']);
                        probs.forEach(p2 => attn.push([tone, cxProblem(p2, ctx)]));
                        if (kind === 'review') sWords('A review writes nothing; run one to replace this');
                        dot = tone;
                    } else { sWords(head || 'It finished'); dot = 'ok'; }
                } else {
                    sWords('No review yet');
                }
                if (attn.length) sWords(attn.length + (attn.length === 1 ? ' needs attention' : ' need attention'), dot === 'bad' ? 't-bad' : 't-warn');
                /* A failed run says so here unless the list already does; a
                   failed tag check says it under its own tag. */
                const tagErr = st.tagJob && st.tagJob.error;
                if (st.lastError && st.lastError !== tagErr && !attn.length) { sWords('Last run failed', 't-bad'); dot = 'bad'; }
                sWords(busyWords);
                dotEl.className = 'dt-dot' + (dot ? ' ' + dot : '');
            }
            rCard.append(statl);
            /* The matrix at its natural width, in the words the document tables
               use, and Needs attention beside it, each thing said once. A
               column is drawn only when some row has a figure; a zero is grey. */
            const rv = el('div', 'cx-rv');
            if (r) {
                const cols = [['create', 'Create'], ['update', 'Update'], ['inXero', 'Already in Xero'],
                    ['noContact', 'Needs a Xero contact'], ['nothing', 'Nothing to send'], ['voided', 'Void'],
                    ['keptPaid', 'Left alone', 'Edited after payment, left as it is'], ['quarantined', 'Quarantined'], ['failed', 'Failed']];
                const rowsR = [['Invoices', 'invoices'], ['Credit notes', 'creditNotes'], ['Contacts', 'contacts']]
                    .map(([lab2, k]) => [lab2, cxReviewCounts(r, k)]);
                const shown = cols.filter(([k]) => k === 'create' || rowsR.some(([, c]) => c[k]));
                const kt = dataTable(['Send will'].concat(shown.map(([, h]) => [h, 'num'])), { wrap: 'cx-mx' });
                shown.forEach(([, , long], i) => { if (long) kt.heads[i + 1].title = long; });
                rowsR.forEach(([lab2, c]) => {
                    const tr = el('tr');
                    tr.append(el('td', 'kw', lab2));
                    shown.forEach(([k]) => tr.append(el('td', 'num' + (c[k] === 0 ? ' zero' : ''), c[k] == null ? '' : String(c[k]))));
                    kt.add(tr);
                });
                rv.append(kt.wrap);
            }
            if (attn.length) {
                const att = el('div', 'cx-att');
                att.append(el('div', 'cx-att-h', 'Needs attention'));
                attn.slice(0, 8).forEach(([tone, words]) => {
                    const row = el('div', 'cx-att-r'); row.append(el('span', 'dt-dot ' + tone), el('span', null, words)); att.append(row);
                });
                if (attn.length > 8) att.append(el('div', 'cx-att-r', 'And ' + (attn.length - 8) + ' more.'));
                rv.append(att);
            }
            if (rv.childNodes.length) rCard.append(rv);

            /* The three narrower ways in sit side by side as tiles, each with
               its hint, its box and its buttons, all three the same shape.
               What a check finds is NOT in its tile: a tag of 62 orders is a
               table, and inside a 444px tile it was a column 10,000px tall
               that pushed the tile's own grid track wider than the tile, over
               the tile beside it. The results sit under all three, the width
               of the card, one section per check that has run. */
            const grid = el('div', 'cx-grid');
            const results = el('div', 'cx-results');
            /* A tile's how-to is its title's info button (copy plan, Xero sync
               #15 to #17): the Check then Send buttons carry the sequence. */
            const cxTile = (title, hint, row) => {
                const tile = el('div', 'cx-tile');
                const t = el('div', 'cx-tile-title', title);
                if (hint) t.append(infoButton(title, { title: title, body: hint }));
                tile.append(t, row);
                return tile;
            };
            /* Enter in a box runs its check, as it would in a form. */
            const onEnter = (input, btn) => input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !btn.disabled) { e.preventDefault(); btn.click(); }
            });
            /* One label per button, the same in every tile, with the full
               name for a screen reader: 'Check tagged orders' did not fit a
               third of the card, so that tile alone stacked its buttons and
               pushed its box 40px above its neighbours'. */
            const cxBtn = (cls, label, name) => { const b = el('button', cls, label); b.setAttribute('aria-label', name); return b; };

            /* ---- one order at a time ----
               Sending the whole queue is the wrong first act against real
               books. This is the same discipline as above, per order: check,
               read what it would do, then send THAT order. */
            const oneWrap = el('div', 'cx-row');
            const oneIn = crmText(connOneCheck ? connOneCheck.order : '', '#104300');
            oneIn.setAttribute('aria-label', 'Order number');
            const oneChk = cxBtn('btn', 'Check', 'Check this order');
            oneChk.disabled = running || !!connOneBusy;
            /* NOT setting-sub: that carries the 52ch prose measure, which
               squeezed a row of results to 382px inside a 1558px card and
               collapsed its flexible column to 26px. */
            function paintOne() {
                const c = connOneCheck && connOneCheck.data;
                if (!c) return;
                const sent = !!connOneCheck.sent;
                /* The heading says what the send did: nothing, part, or all. */
                const nd = cxTally([{ docs: c.docs || [], error: c.error }]);
                const title = (!sent ? 'Order ' : (c.error && !(c.docs || []).length) || c.found === false ? 'Not sent: order '
                    : nd.attention ? 'Partly sent: order ' : 'Sent: order ') + connOneCheck.order;
                if (c.error && !(c.docs || []).length) { cxSection(results, 'one', title).append(el('div', 'msg error', cxDetail(c.error))); return; }
                if (c.found === false) {
                    cxSection(results, 'one', title).append(el('div', 'msg error', 'No order ' + connOneCheck.order + ' in Shopify.'));
                    return;
                }
                const docs = c.docs || [];
                /* A document out against Shopify is named in the summary too. */
                const oneOut = cxSection(results, 'one', title, docs.length ? cxOneSentence(docs, !sent)
                        + (sent ? '' : cxMismatchNote(docs.map(d => ({ order: connOneCheck.order, d: d }))))
                    : 'The check found no document to write for this order.');
                if (docs.length || c.error) oneOut.append(connDocTable(cxEntries([{ order: connOneCheck.order, found: true, docs: docs, error: c.error }]), !sent, false));
            }
            oneChk.onclick = async () => {
                const order = oneIn.value.trim();
                if (!order) { toastError('Type the order number first, for example #104300.'); return; }
                oneChk.disabled = true; connOneBusy = 'check'; connOneCheck = null;
                try {
                    const r = await connOp({ op: 'reimport', order: order, dryRun: true });
                    connOneCheck = { order: order, data: (r && r.data) || {} };
                } catch (e) { toastError(e.message); }
                connOneBusy = ''; oneChk.disabled = false;
                renderConnector();
            };
            onEnter(oneIn, oneChk);
            oneWrap.append(oneIn, oneChk);
            if (admin) {
                const oneSend = cxBtn('btn', 'Send', 'Send this order');
                /* Armed only by a check of exactly this order that found it
                   and found something to write. A check that did not find
                   the order, failed, or found nothing to write armed it
                   before, and the confirm then offered to send 'nothing the
                   check could name'. */
                const oneReady = (v) => {
                    if (!connOneArmed(v)) return ['', 'Check the order first: Send does what the check showed'];
                    const c = connOneCheck.data || {};
                    if (c.error || c.found === false) return ['', 'The check did not find this order, so there is nothing to send'];
                    if (!cxTally([{ docs: c.docs || [] }]).write) return ['', 'The check found nothing to write for this order'];
                    return ['ok', 'Write just this order into Xero'];
                };
                const armOne = () => {
                    const [ok2, why] = oneReady(oneIn.value);
                    oneSend.disabled = running || !!connOneBusy || !ok2;
                    oneSend.title = why;
                };
                armOne();
                /* Retyping the box disarms it: what was checked is no longer
                   what would be sent. */
                oneIn.oninput = armOne;
                oneSend.onclick = async () => {
                    const order = oneIn.value.trim();
                    const docs = ((connOneCheck || {}).data || {}).docs || [];
                    if (!await uiConfirm('Send order ' + order + ' to Xero? The check found: '
                        + cxOneSentence(docs, true).replace(/^./, ch => ch.toLowerCase())
                        + cxMismatchNote(docs.map(d => ({ order: order, d: d }))),
                        { title: 'Send one order', okText: 'Send it' })) return;
                    oneSend.disabled = true; connOneBusy = 'send';
                    try {
                        const r = await connOp({ op: 'reimport', order: order });
                        /* Spent, and kept: what the send did stays on screen
                           to be read, and the toast says what it says. The
                           reply was thrown away and 'Sent' was toasted over a
                           failed write. */
                        const data = (r && r.data) || {};
                        connOneCheck = { order: order, data: data, sent: true };
                        const n = cxTally([{ docs: data.docs || [], error: data.error }]);
                        if (data.error && !(data.docs || []).length) toastError('Order ' + order + ' was not sent. ' + cxDetail(data.error));
                        else if (n.attention) toastError('Not all of order ' + order + ' went to Xero: the list under the tiles says what.');
                        else toastOk('Sent order ' + order + '. ' + cxOneSentence(data.docs || [], false));
                    } catch (e) { toastError(e.message); }
                    connOneBusy = '';
                    connStartWatch(); renderConnector();
                };
                oneWrap.append(oneSend);
            }
            grid.append(cxTile('One order', admin
                ? 'Check it, read what it would write, then send that order. One already sent is never sent twice.'
                : 'Check it and read what it would write. An admin sends it; one already sent is never sent twice.', oneWrap));

            /* ---- every order with a tag ----
               The same discipline over a list: check the tag, read what each
               order would do, then send that tag. The tag is left on the
               orders. It is a label, not a to-do, so the same tag can be sent
               again and an order already in Xero and unchanged is a lookup,
               not a write. The connector caps a tag at 100 orders. */
            const tagWrap = el('div', 'cx-row');
            /* The tag in flight is kept apart from the finished check, so the
               box and the heading still name it while the check runs. */
            const tagIn = crmText(connTagCheck ? connTagCheck.tag : connTagPending, 'xero-price-check');
            tagIn.setAttribute('aria-label', 'Order tag');
            const tagChk = cxBtn('btn', 'Check', 'Check every order with this tag');
            tagChk.disabled = running || !!connTagBusy;
            const paintTag = () => {
                const tagName = (connTagCheck && connTagCheck.tag) || connTagPending || tagIn.value.trim();
                const title = 'Orders tagged "' + tagName + '"';
                if (connTagBusy) {
                    const t = el('div', 'thinking');
                    t.append(loader(), el('span', null, connTagBusy === 'send' ? 'Sending every order with that tag…'
                        : 'Checking every order with that tag… nothing is written.'));
                    cxSection(results, 'tag', (connTagBusy === 'send' ? 'Sending: ' : 'Checking: ') + title.charAt(0).toLowerCase() + title.slice(1)).append(t);
                    return;
                }
                const c = connTagCheck && connTagCheck.data;
                if (!c || (connTagCheck.sent && !c.details && !c.error)) return;
                if (c.error) { cxSection(results, 'tag', (connTagCheck.sent ? 'Not sent: o' : 'O') + title.slice(1)).append(el('div', 'msg error', cxDetail(c.error))); return; }
                const rows = c.details || [];
                const dry = c.dryRun !== false && !connTagCheck.sent;
                const n = cxTally(rows);
                const lower = title.charAt(0).toLowerCase() + title.slice(1);
                const ts = cxTallySentence(n, dry);
                const sum = rows.length + (rows.length === 1 ? ' order carries' : ' orders carry') + ' the tag'
                    + (n.docs ? ', with ' + n.docs + (n.docs === 1 ? ' document' : ' documents') + ' between them'
                        + (/^Nothing/.test(ts) ? '. ' : ': ') + ts : '.')
                    + (n.unread ? ' ' + n.unread + (n.unread === 1 ? ' order ' : ' orders ')
                        + (dry ? 'could not be checked.' : (n.unread === 1 ? 'was not sent.' : 'were not sent.')) : '')
                    /* Counted with what Send writes, because it would be
                       written, and named here so the summary says it too. */
                    + (dry && n.mismatch ? ' ' + n.mismatch + (n.mismatch === 1
                        ? ' of those to write does not match Shopify, and is listed first.'
                        : ' of those to write do not match Shopify, and are listed first.') : '');
                const sec = cxSection(results, 'tag', dry ? title
                    : (!n.write ? 'Nothing sent: ' : (n.attention || n.unread) ? 'Partly sent: ' : 'Sent: ') + lower, sum);
                if (!rows.length) return;
                /* Every count here is in table rows (a document, or an order
                   that has none), so the tabs, the pager and the table agree:
                   the tabs counted documents while the pager counted orders.
                   The list opens on what Send would write, the one thing to
                   read before pressing it; the rest are a tab away, counted. */
                if (connTagView.of !== connTagCheck) {
                    connTagView = { of: connTagCheck, f: n.write ? 'write' : 'all', page: 1, size: 20 };
                }
                /* An order with a document out against Shopify comes first,
                   before the list is paged, so it is never on page two. */
                const all0 = cxEntries(rows);
                const misOrders = new Set(all0.filter(e => e.mis).map(e => e.r));
                const all = all0.filter(e => misOrders.has(e.r)).concat(all0.filter(e => !misOrders.has(e.r)));
                const F = [['all', 'All', all.length], ['write', dry ? 'To write' : 'Written', n.write],
                    ['unchanged', 'Already in Xero', n.unchanged], ['alone', 'Left alone', n.alone],
                    ['attention', 'Needs attention', n.attention], ['unread', dry ? 'Not checked' : 'Not sent', n.unread]]
                    .filter(([k, , k2]) => k === 'all' || k2 > 0);
                if (!F.some(([k]) => k === connTagView.f)) connTagView.f = 'all';
                if (F.length > 2) {
                    const tabs = segmented(F.map(([k, l, k2]) => [k, l + ' (' + k2 + ')']), connTagView.f,
                        (k) => { connTagView.f = k; connTagView.page = 1; connFocus = { sec: 'tag', on: 'tab' }; renderConnector(); });
                    sec.append(tabs);
                }
                const kept = connTagView.f === 'all' ? all : all.filter(e => e.g === connTagView.f);
                const pages = Math.max(1, Math.ceil(kept.length / connTagView.size));
                if (connTagView.page > pages) connTagView.page = pages;
                const from = (connTagView.page - 1) * connTagView.size;
                sec.append(connDocTable(kept.slice(from, from + connTagView.size), dry, true));
                /* A pager only when there is a page to turn: at 12 rows it
                   offered four dead arrows. */
                if (kept.length > 20) sec.append(tablePager({ total: kept.length, page: connTagView.page, pageSize: connTagView.size,
                    sizes: [20, 50, 100],
                    onPage: (k) => { connTagView.page = k; connFocus = { sec: 'tag', on: 'head' }; renderConnector(); },
                    onSize: (k) => { connTagView.size = k; connTagView.page = 1; connFocus = { sec: 'tag', on: 'head' }; renderConnector(); } }));
            };
            tagChk.onclick = async () => {
                const tag = tagIn.value.trim();
                if (!tag) { toastError('Type the tag first, for example xero-price-check.'); return; }
                tagChk.disabled = true; connTagBusy = 'check'; connTagCheck = null; connTagPending = tag;
                /* The connector answers at once and works in the background: a
                   tag can be a hundred orders, each a few lookups, and a reply
                   that waited for all of them was the reply that never came.
                   The watcher collects the outcome from the status once the
                   service says it has stopped running. */
                try {
                    await connOp({ op: 'reimport_tag', tag: tag, dryRun: true });
                    connStartWatch();
                } catch (e) { toastError(e.message); connTagBusy = ''; }
                renderConnector();
            };
            onEnter(tagIn, tagChk);
            tagWrap.append(tagIn, tagChk);
            if (admin) {
                const tagSend = cxBtn('btn', 'Send', 'Send every order with this tag');
                /* Armed only by an unspent check of exactly this tag that found
                   orders and something to write. */
                const tagReady = () => {
                    if (!connTagArmed(tagIn.value)) return ['', 'Check the tag first: Send does what the check showed'];
                    const c = connTagCheck.data || {};
                    if (c.error) return ['', 'The check failed, so there is nothing to send'];
                    if (!(c.details || []).length) return ['', 'No order carries this tag'];
                    if (!cxTally(c.details).write) return ['', 'The check found nothing to write for these orders'];
                    return ['ok', 'Write every checked order into Xero'];
                };
                const armTag = () => {
                    const [ok2, why] = tagReady();
                    tagSend.disabled = running || !!connTagBusy || !ok2;
                    tagSend.title = why;
                };
                armTag();
                tagIn.oninput = armTag;
                tagSend.onclick = async () => {
                    const tag = tagIn.value.trim();
                    const c = ((connTagCheck || {}).data) || {};
                    const n = (c.details || []).length;
                    const t2 = cxTally(c.details || []);
                    if (!await uiConfirm('Send every order tagged "' + tag + '" to Xero? The check found '
                        + n + (n === 1 ? ' order' : ' orders') + ' with ' + t2.docs + (t2.docs === 1 ? ' document' : ' documents') + ': '
                        + cxTallySentence(t2, true).replace(/^Nothing would be written: /, '').replace(' (each row says why)', '')
                        + (t2.attention ? ' Those that need attention will not go through as they are.' : '')
                        + (t2.unread ? ' ' + t2.unread + (t2.unread === 1 ? ' order' : ' orders') + ' could not be checked and will not be sent.' : '')
                        + cxMismatchNote(cxEntries(c.details || []).filter(e => e.d).map(e => ({ order: e.r.order, d: e.d }))),
                        { title: 'Send tagged orders', okText: 'Send them' })) return;
                    tagSend.disabled = true; connTagBusy = 'send'; connTagPending = tag;
                    /* Spent now, not when it finishes: a second click while the
                       service works must find nothing armed. The outcome lands
                       through the watcher, marked sent, and stays to be read. */
                    connTagCheck = { tag: tag, data: {}, sent: true };
                    try {
                        await connOp({ op: 'reimport_tag', tag: tag });
                        toastOk('Sending the orders tagged "' + tag + '" to Xero.');
                        connStartWatch(); renderConnector();
                    } catch (e) { connTagBusy = ''; toastError(e.message); renderConnector(); }
                };
                tagWrap.append(tagSend);
            }
            grid.append(cxTile('Every order with a tag', admin
                ? 'Tag the orders in Shopify, check the tag, read what each would write, then send. The tag stays on; an order already in Xero and unchanged is looked up, not written.'
                : 'Tag the orders in Shopify, check the tag and read what each would write. An admin sends them; the tag stays on.', tagWrap));
            if (connTagBusy) connStartWatch();   /* a tab left and come back to still collects */

            /* ---- payout notes: "Which payout paid it" ----
               A separate pass, because Shopify settles days after the order:
               at the moment an invoice is written the payout it will arrive in
               does not exist yet. It only ADDS A NOTE to invoices already in
               Xero, which cannot change a figure on one. */
            const payHint = 'A Shopify payout reaches the bank as one figure covering many orders. This adds a note to each '
                + 'Xero invoice saying which payout paid it, with the order’s share and the Shopify fee. A note only: no amount changes. '
                + 'With no date it looks back 30 days.';
            const payWrap = el('div', 'cx-row');
            /* A date field, not free text: its grey example date read as a
               value, and an empty box quietly meant the last 30 days. */
            const paySince = crmText(connPaySince, '');
            paySince.type = 'date';
            paySince.setAttribute('aria-label', 'Payouts issued since');
            const payChk = cxBtn('btn', 'Check', 'Check the payouts');
            payChk.disabled = running;
            payChk.onclick = async () => {
                payChk.disabled = true; connPayResult = null;
                try {
                    const r = await connOp({ op: 'payouts', dryRun: true,
                                             since: connPaySince || '' });
                    connPayResult = (r && r.data) || {};
                    connPayBox = connPaySince;
                    connPayView.page = 1;
                } catch (e) { toastError(e.message); }
                payChk.disabled = false; renderConnector();
            };
            onEnter(paySince, payChk);
            payWrap.append(paySince, payChk);
            if (admin) {
                const payGo = cxBtn('btn', 'Write notes', 'Write notes on the checked invoices');
                /* Armed by a check of exactly the date in the box, the same
                   rule the one-order send follows: nothing is written that
                   nobody has looked at first. Retyping the date disarms it,
                   and the write uses the date the check used, so a check of
                   September cannot arm a write back to January. */
                const payReady = () => !!(connPayResult && connPayResult.dryRun && (connPayResult.notes || []).length
                    && (paySince.value.trim() === (connPayBox || '')));
                const armPay = () => {
                    payGo.disabled = running || !payReady();
                    payGo.title = payReady() ? 'Write these notes onto their Xero invoices'
                        : 'Check the payouts first: this writes what the check found';
                };
                armPay();
                paySince.addEventListener('input', () => { connPaySince = paySince.value.trim(); armPay(); });
                payGo.onclick = async () => {
                    if (!await uiConfirm('Write ' + (connPayResult.notes || []).length
                        + ' payout note' + ((connPayResult.notes || []).length === 1 ? '' : 's')
                        + ' onto their Xero invoices? Notes only: no amount changes.',
                        { title: 'Write payout notes', okText: 'Write them' })) return;
                    payGo.disabled = true;
                    try {
                        const r = await connOp({ op: 'payouts', since: connPayResult.since || connPayBox || '' });
                        connPayResult = (r && r.data) || {};
                        const k = connPayResult.annotated || 0, bad = connPayResult.failed || 0;
                        if (connPayResult.error) {
                            const why = cxPayoutWhy(connPayResult, { auth: ((connCache.data || {}).config || {}).shopifyAuth, admin: connIsAdmin(), pass: true });
                            toastError(why.lead + (why.detail ? ' ' + why.detail : ''));
                        }
                        else if (bad) toastError('Wrote ' + k + (k === 1 ? ' note' : ' notes') + '; ' + bad + ' could not be written. The list says which.');
                        else toastOk('Wrote ' + k + (k === 1 ? ' note' : ' notes') + ' to Xero.');
                    } catch (e) { toastError(e.message); }
                    renderConnector();
                };
                payWrap.append(payGo);
            } else {
                paySince.addEventListener('input', () => { connPaySince = paySince.value.trim(); });
            }
            grid.append(cxTile('Which payout paid it', payHint, payWrap));
            function paintPay() {
                const d = connPayResult;
                if (!d) return;
                const title = 'Payouts' + (d.since ? ' since ' + fmtDate(d.since) : '') + (d.dryRun === false ? ', written' : '');
                if (d.error) {
                    const why = cxPayoutWhy(d, { auth: ((connCache.data || {}).config || {}).shopifyAuth, admin: connIsAdmin(), pass: true });
                    const b = el('div', 'msg error');
                    b.append(el('div', null, why.lead));
                    if (why.detail) b.append(el('div', 'lbl-meta', why.detail));
                    cxSection(results, 'pay', title).append(b);
                    return;
                }
                const notes = d.notes || [];
                const k = d.dryRun ? notes.length : (d.annotated || 0);
                const paid = d.ordersWithPayouts || 0;
                const also = [d.alreadyDone ? d.alreadyDone + ' already ' + (d.alreadyDone === 1 ? 'carries its' : 'carry their') + ' note' : '',
                              d.noInvoice ? d.noInvoice + ' ' + (d.noInvoice === 1 ? 'has' : 'have') + ' no invoice in Xero yet' : '',
                              d.failed ? d.failed + ' could not be written' : ''].filter(Boolean);
                const sec = cxSection(results, 'pay', title, (k ? k + (k === 1 ? ' note' : ' notes') + (d.dryRun ? ' would be written. ' : ' written. ')
                                                : (d.dryRun ? 'No note to write. ' : 'No note was written. '))
                    + paid + (paid === 1 ? ' order was' : ' orders were') + ' paid out'
                    + (also.length ? ': ' + cxList(also) : '') + '.');
                if (!notes.length) return;
                /* The note as Xero will hold it, word for word: it is what
                   gets written, so it is quoted rather than reworded. On a
                   check every row would say 'To write', which the sentence
                   above already says, so the column is only drawn when rows
                   differ; failures first, where they are seen. */
                const order = notes.slice().sort((a, b) => (b.message ? 1 : 0) - (a.message ? 1 : 0));
                const withState = notes.some(n2 => n2.wrote || n2.message);
                const pages = Math.max(1, Math.ceil(order.length / connPayView.size));
                if (connPayView.page > pages) connPayView.page = pages;
                const from = (connPayView.page - 1) * connPayView.size;
                const kt = dataTable(['Order', 'Payout'].concat(withState ? ['Outcome'] : []).concat(['Note for the invoice']), { cls: 'cx-docs cx-pay' });
                order.slice(from, from + connPayView.size).forEach(n2 => {
                    const tr = el('tr');
                    tr.append(el('td', 'cx-ord', n2.order || ''), el('td', 'cx-payout', n2.payout || ''));
                    if (withState) {
                        const st2 = el('td', 'cx-state');
                        st2.append(el('span', 'lbl-chip ' + (n2.wrote ? 'made' : n2.message ? 'bad' : 'note'),
                            n2.wrote ? 'Written' : n2.message ? 'Failed' : 'To write'));
                        if (n2.message) st2.append(el('div', 'cx-why', cxDetail(n2.message)));
                        tr.append(st2);
                    }
                    tr.append(el('td', 'cx-note', n2.note || ''));
                    kt.add(tr);
                });
                sec.append(kt.wrap);
                if (order.length > 20) sec.append(tablePager({ total: order.length, page: connPayView.page, pageSize: connPayView.size,
                    sizes: [20, 50, 100], noun: 'notes',
                    onPage: (p2) => { connPayView.page = p2; connFocus = { sec: 'pay', on: 'head' }; renderConnector(); },
                    onSize: (p2) => { connPayView.size = p2; connPayView.page = 1; connFocus = { sec: 'pay', on: 'head' }; renderConnector(); } }));
            }
            rCard.append(grid);
            /* In the tiles' order, whatever has been checked. */
            paintOne(); paintTag(); paintPay();
            if (results.childNodes.length) rCard.append(results);

            /* ---- settings ----
               Operational knobs only. The shop, the Xero organisation and every
               credential stay environment variables on the service, where a
               browser cannot reach them; the server refuses anything not on
               its own list rather than trusting this form. */
            const xCard = el('div', 'card cx-setcard');
            if (connSettings && connIsAdmin()) {
                const xHead = el('div', 'card-head');
                /* The security note, word for word, behind the title (copy plan,
                   Xero sync #19). */
                const xt = el('h3', 'card-title', 'Settings');
                const xtInfo = infoButton('About these settings', { title: 'Settings', body:
                    'How it behaves. Credentials are not on this form: they stay on the '
                    + 'service, and the server will not accept them from here.' });
                xHead.append(titleInfo(xt, xtInfo));
                const toggle = textButton(connSettingsOpen ? 'Hide settings' : 'Change settings', { small: true });
                toggle.onclick = async () => {
                    if (connSettingsOpen) { connSettingsOpen = false; connSettingsEdits = {}; renderConnector(); return; }
                    toggle.disabled = true;
                    try { await connOpenSettings(); }
                    catch (e) {
                        toggle.disabled = false;
                        toastError('The settings could not be read again, so they were not opened. ' + e.message);
                        return;
                    }
                    renderConnector();
                };
                const xAct = el('div', 'card-act'); xAct.append(toggle); xHead.append(xAct); xCard.append(xHead);
                if (!connSettingsOpen) {
                    /* The values as they stand, read before anything is opened. */
                    /* Two columns of names, each value right after its name (12 Oct 2026). */
                    const dl = el('dl', 'conn-pairs cx-set');
                    [['RECONCILE_MODE', 'When a total disagrees'], ['RECONCILE_TOLERANCE', 'Tolerance'],
                     ['MAX_DOCS_PER_RUN', 'Most documents in one run'], ['RUNAWAY_ABORT_ABOVE', 'Stop entirely above'],
                     ['ORDERS_SINCE', 'Only orders since'],
                     ['XERO_SALES_ACCOUNT_CODE', 'Sales account'], ['XERO_TAX_TYPE_STANDARD', 'Standard tax type'],
                     ['XERO_TAX_TYPE_ZERO', 'Zero-rated tax type'],
                     ['CUSTOMER_REF_METAFIELD_NAMESPACE', 'Customer reference namespace'], ['CUSTOMER_REF_METAFIELD_KEY', 'Customer reference key']].forEach(([k, lab]) => {
                        if (connSettings[k] == null || connSettings[k] === '') return;
                        const v = k === 'RECONCILE_MODE' ? (CX_MODE[connSettings[k]] || connSettings[k])
                            : k === 'RECONCILE_TOLERANCE' ? money(Number(connSettings[k]) || 0, 'GBP', 2)
                            : k === 'ORDERS_SINCE' ? fmtDate(connSettings[k]) : String(connSettings[k]);
                        dl.append(el('dt', null, lab), el('dd', null, v));
                    });
                    if (dl.childNodes.length) xCard.append(dl);
                }
                if (connSettingsOpen) {
                    const grid = el('div', 'disp-addr-grid');
                    const fields = {};
                    /* shown: each value as this form drew it, before anything
                       typed. Save sends only what differs from it. */
                    const shown = {}, labels = {};
                    const add = (key, label, help, opts) => {
                        let input;
                        /* A value a list does not have (a variable set to
                           "Strict") is added to it and selected, so it shows
                           as it is and reads as unchanged. */
                        const put = (v) => {
                            if (opts && ![...input.options].some(o => o.value === v)) input.add(new Option(CX_MODE[v] || v, v), 0);
                            input.value = v;
                        };
                        if (opts) {
                            input = document.createElement('select');
                            input.className = 'crm-input';
                            opts.forEach(o => input.add(new Option(CX_MODE[o] || o, o)));
                            put(connSettings[key] || opts[0]);
                        } else {
                            input = crmText(connSettings[key] || '', '');
                        }
                        fields[key] = input;
                        crmField(grid, label, input);
                        shown[key] = input.value; labels[key] = label;
                        if (key in connSettingsEdits) put(connSettingsEdits[key]);
                        /* The help belongs to its field, in the same grid cell.
                           As a cell of its own it pushed every field after it
                           one place along, so the grid alternated field-help
                           and field-field. */
                        if (help) input.parentElement.append(el('span', 'field-help', help));
                        const src = el('span', 'field-help');
                        const paint = () => {
                            const n = connSettingNote(key, shown[key], input.value, connSettings);
                            src.textContent = n ? n.text : '';
                            src.hidden = !n;
                            if (!n || !n.back) return;
                            const fv = String(n.back.value == null ? '' : n.back.value);
                            const said = key === 'RECONCILE_MODE' ? (CX_MODE[fv] || fv) : fv;
                            const back = textLink(n.back.from === 'env' ? 'Use the service’s value (' + said + ')'
                                : fv ? 'Use the default (' + said + ')' : 'Clear it');
                            back.type = 'button';
                            /* Puts back what applies with nothing saved; Save then
                               sends it, and the connector lets go of its copy. */
                            back.onclick = (ev) => {
                                ev.preventDefault();
                                put(fv);
                                connSettingsEdits[key] = fv;
                                paint();
                            };
                            src.append(' ', back);
                        };
                        const edited = () => { connSettingsEdits[key] = input.value; paint(); };
                        input.addEventListener('input', edited);
                        input.addEventListener('change', edited);
                        paint();
                        input.parentElement.append(src);
                    };
                    add('RECONCILE_MODE', 'When a total disagrees with Shopify',
                        'Sending anyway once let a discounted invoice through, out by \u00a333.50.',
                        ['warn', 'strict', 'off']);
                    add('RECONCILE_TOLERANCE', 'Tolerance', 'How far apart is close enough, in pounds.');
                    add('MAX_DOCS_PER_RUN', 'Most documents in one run',
                        'The first this many go, oldest first; the rest wait for the next run and the run says how many are waiting.');
                    add('RUNAWAY_ABORT_ABOVE', 'Stop entirely above',
                        'More orders waiting than this and the run creates nothing at all, not even contacts: that is a widened window, not a backlog.');
                    add('ORDERS_SINCE', 'Only orders since',
                        'A date, written year-month-day. Shopify only gives the last 60 days of orders, so an older date finds nothing.');
                    add('XERO_SALES_ACCOUNT_CODE', 'Sales account code', '');
                    add('XERO_TAX_TYPE_STANDARD', 'Standard tax type', '');
                    add('XERO_TAX_TYPE_ZERO', 'Zero-rated tax type', '');
                    add('CUSTOMER_REF_METAFIELD_NAMESPACE', 'Customer reference namespace', '');
                    add('CUSTOMER_REF_METAFIELD_KEY', 'Customer reference key',
                        'Where the reference on the document view is read from.');
                    xCard.append(grid);
                    /* Plain: Send to Xero is the page's one teal action. */
                    const save = textButton('Save settings');
                    save.onclick = async () => {
                        const now = {};
                        Object.keys(fields).forEach(k => { now[k] = fields[k].value; });
                        save.disabled = true;
                        try {
                            if (!(await connSaveSettings(shown, now, labels))) { save.disabled = false; return; }
                            connSettingsOpen = false; connSettingsEdits = {};
                            await refreshConnector();
                        } catch (e) { save.disabled = false; toastError(e.message); }
                    };
                    const sb = el('div', 'mail-statebar'); sb.append(save);
                    xCard.append(sb);
                }
            }
            box.append(widget(rCard, 'review'));

            /* ---- runs, beside the quarantine log (12 Oct 2026) ---- */
            let hCard = null, qCard = null;
            if ((connRuns || []).length) {
                hCard = el('div', 'card');
                const hHead = el('div', 'card-head');
                const hTitle = el('h3', 'card-title', 'Runs');
                hTitle.append(el('span', 'card-n', String(connRuns.length)));
                hHead.append(hTitle); hCard.append(hHead);
                /* When with its time, the mode, the outcome as a dot and a word
                   (colour is spent on the outcome only: a Send is not a
                   success), and what each wrote, at the table's natural width. */
                hCard.append(dtable([{ head: 'When' }, { head: 'Mode' }, { head: 'Outcome' }, { head: 'Invoices', cls: 'num', cap: true },
                                     { head: 'Credit notes', cls: 'num', cap: true }, { head: 'Contacts', cls: 'num', cap: true }],
                    connRuns.slice(0, 12).map(run => {
                        const r2 = run.result || {};
                        /* A run that stopped itself did not 'have failures': it
                           stopped, and one that threw failed. */
                        const oc = el('span', 'dt-sev');
                        oc.append(el('span', 'dt-dot ' + (run.ok ? 'ok' : 'bad')),
                            document.createTextNode(run.ok ? 'Clean' : run.error ? 'Failed' : (r2.aborted ? 'Stopped' : 'Had failures')));
                        return { cells: [fmtDate(run.finishedAt) + ', ' + londonHM(run.finishedAt), run.dryRun ? 'Review' : 'Send', oc,
                                         String(connCounts(r2, 'invoices').created), String(connCounts(r2, 'creditNotes').created),
                                         String(connCounts(r2, 'contacts').created)] };
                    }), { cls: 'dt-runs', label: 'Runs', stop: 's' }));
                box.append(widget(hCard, 'runs', 'full', 'Runs'));
            }
            if (st.quarantineCount) {
                qCard = el('div', 'card');
                const qHead = el('div', 'card-head');
                const qt = el('h3', 'card-title', 'Quarantine log');
                qt.append(el('span', 'card-n', String(st.quarantineCount)));
                qHead.append(titleInfo(qt, infoButton('About quarantine', { title: 'Quarantine log', body: 'Held back for bad data. Fix the cause, then retry.' })));
                if (connIsAdmin()) {
                    const qAct = el('div', 'card-act');
                    const rt = textButton(null, { small: true });
                    rt.append(ico(I.refresh), document.createTextNode('Retry failed'));
                    rt.disabled = running;
                    rt.onclick = async () => {
                        if (!await uiConfirm('Re-import every failed and quarantined document? '
                            + 'Anything that now maps cleanly is written into Xero.',
                            { title: 'Retry failed', okText: 'Retry' })) return;
                        rt.disabled = true; connBusy = 'retry';
                        try { await connOp({ op: 'retry' }); connStartWatch(); renderConnector(); }
                        catch (e) { connBusy = ''; toastError(e.message); rt.disabled = false; }
                    };
                    qAct.append(rt); qHead.append(qAct);
                }
                qCard.append(qHead);
                const qHost = el('div'); qCard.append(qHost);
                if (connQuar === false) qHost.append(el('div', 'sub', 'The quarantine list could not be read.'));
                else if (connQuar && !connQuar.length) qHost.append(el('div', 'sub', 'Empty now. Refresh to update the count.'));
                else if (connQuar) {
                    /* Each document over why it was held, the whole reason in
                       plain words: cut at 140 characters it stopped mid-word. */
                    const kw = { invoice: 'Invoice', creditnote: 'Credit note', contact: 'Contact' };
                    qHost.append(dtable([{ head: 'Document', cls: 'stack' }], connQuar.slice(0, 30).map(q2 => {
                        const f = document.createDocumentFragment();
                        f.append(el('span', 'dt-name', (kw[q2.kind] || cap(String(q2.kind || ''))) + ' ' + (q2.key || q2.order || '')),
                            el('span', 'dt-why', cxDetail(q2.reason || q2.message || (q2.errors || []).join('; ') || '')));
                        return { cells: [f] };
                    }), { cls: 'dt-quar', label: 'Quarantine log', stop: 's' }));
                    if (connQuar.length > 30) qHost.append(el('div', 'sub', (connQuar.length - 30) + ' more held.'));
                }
                box.append(widget(qCard, 'quarantine', 'full', 'Quarantine log'));
            }
            /* Side by side when both have something to show. */
            pairNodes(hCard, qCard, 'runs', 'Runs and quarantine', { fit: true });
            if (xCard.childNodes.length) box.append(widget(xCard, 'settings'));
            cardifySections(box);
            /* A filter or a page turn redraws the page; focus goes back to the
               tab that was pressed, or to the section's heading, which is
               brought into view: it fell to the page and the next page's first
               row sat 860px above the screen. */
            /* After the widget grid has laid the cards out (two frames): done
               at once, it measured a page still being arranged and threw the
               view off the screen. A tab keeps its place, since the pointer
               is on it; a page turn brings the section's heading to the top
               of the page's own scroller, not of the window. */
            if (connFocus) {
                const f = connFocus; connFocus = null;
                requestAnimationFrame(() => requestAnimationFrame(() => {
                    const sec = box.querySelector('[data-cx="' + f.sec + '"]');
                    const target = sec && (f.on === 'tab' ? sec.querySelector('.segmented > button.on') : sec.querySelector('.cx-res-title'));
                    if (!target) return;
                    if (f.on !== 'tab') {
                        target.tabIndex = -1;
                        const sc = box.closest('.scroll');
                        if (sc) sc.scrollTop += target.getBoundingClientRect().top - sc.getBoundingClientRect().top - 16;
                    }
                    target.focus({ preventScroll: true });
                }));
            }
        }

