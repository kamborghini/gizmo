        /* ---------- Stock: moving the stock sheet in (the owner's) ----------
           The switch evening's one window, opened from Settings: the stock
           app's export sent in parts, each stock app name matched to a
           Reactor account, a check that converts and proves it and changes
           nothing, then the move. The server does the work (/api/stock/move);
           this window sends, polls and says where it stands, so it can be
           closed and opened again while a check or a move runs. */

        /* The export's text in parts of at most `size` characters that join
           back to it exactly, never cutting a character in two: half an emoji
           would not survive the trip and the checksum would fail. */
        function stockMoveParts(text, size) {
            const parts = [];
            for (let at = 0; at < text.length;) {
                let end = Math.min(text.length, at + size);
                if (end < text.length && /[\uD800-\uDBFF]/.test(text[end - 1])) end -= 1;
                parts.push(text.slice(at, end));
                at = end;
            }
            return parts;
        }
        /* The Reactor account a stock app username belongs to, when exactly one
           account's username or first name is it; otherwise none, for the owner
           to choose. */
        function stockMoveGuess(name, accounts) {
            const n = String(name || '').trim().toLowerCase();
            const fits = (accounts || []).filter(a => [a.username, String(a.name || '').split(/\s+/)[0]]
                .some(w => String(w || '').toLowerCase() === n));
            return n && fits.length === 1 ? fits[0].id : '';
        }
        /* Move in is offered only after a passing check of this very export,
           matched to these very people, while the stock sheet is not yet in. */
        function stockMoveReady(st, people) {
            const run = st && st.run;
            if (!st || st.live || !st.upload || !run || run.kind !== 'check' || run.state !== 'passed') return false;
            if (run.sha256 !== st.upload.sha256) return false;
            const names = [...new Set(((st.names || {}).history || []).concat((st.names || {}).logins || []))];
            if (!names.every(n => people[n])) return false;
            const a = run.people || {}, keys = Object.keys(a);
            return keys.length === Object.keys(people).length && keys.every(k => people[k] === a[k]);
        }
        /* What the Settings row says: still in the stock app, or since when it is here. */
        function stockMoveRowWords(st) {
            if (st && st.live) {
                const m = st.moved_in;
                return m && m.at ? 'Moved in on ' + fmtDate(m.at) + ', ' + londonHM(m.at) + ' by ' + (m.by_name || 'the owner')
                    + '. The stock app can stay switched off.' : 'Kept here, on the Stock tab.';
            }
            return 'Still kept in the stock app. Move it in when you are both ready: Reactor checks the export first and '
                + 'changes nothing until every figure is proven.';
        }
        const STOCK_MOVE_PART = 1000000;   // characters: at most 3 MB of text, well under the server's 4 MB a part
        async function openStockMove(opener) {
            let st = null, people = {}, poll = null, closed = false, wasRunning = false;
            const win = dialog({ title: 'Move the stock sheet in', size: 'wide stock-move-win', opener: opener,
                                 onClose: () => { closed = true; clearTimeout(poll); } });
            titleInfo(win.heading, infoButton('About moving the stock sheet in', { title: 'Moving the stock sheet in', body: [
                'Make the export with the stock app stopped, as the move’s notes say, then send it here.',
                'Check converts it and proves every line, history entry and figure against the stock app’s own. Nothing changes.',
                'Move in does the same again and then puts it live: the Stock tab opens for the people matched, and made orders book their glass here.'] }));
            const step = (title, sub) => { const s = el('section', 'stock-move-step'); s.append(el('h4', 'card-title', title)); if (sub) s.append(el('p', 'field-help', sub)); win.body.append(s); return s; };
            const fileStep = step('The export', 'The file the stock app’s exporter made. It stays on the server, out of sight, and goes once the stock sheet has moved in.');
            const file = document.createElement('input');
            file.type = 'file'; file.accept = '.json,application/json'; file.hidden = true;
            file.setAttribute('aria-label', 'The stock app’s export');
            const choose = textButton('Choose the export'); choose.type = 'button';
            const fileLine = el('p', 'stock-move-line');
            fileLine.setAttribute('role', 'status');
            const fileActs = el('div', 'stock-move-acts'); fileActs.append(choose, file);
            fileStep.append(fileActs, fileLine);
            const peopleStep = step('Who is who', 'Each name the stock app knows, matched to the person’s Reactor account. Old entries keep the old name beside it.');
            const peopleHost = el('div', 'stock-move-people');
            peopleStep.append(peopleHost);
            const checkStep = step('The check');
            const result = el('div', 'stock-move-result');
            result.setAttribute('role', 'status');
            checkStep.append(result);
            const foot = win.foot();
            const shut = textButton('Close'); shut.type = 'button'; shut.onclick = () => win.close();
            const check = textButton('Check'); check.type = 'button';
            const go = textButton('Move in', { kind: 'primary' }); go.type = 'button';
            foot.append(shut, check, go);

            const drawPeople = () => {
                peopleHost.innerHTML = '';
                const names = st && st.names ? [...new Set((st.names.history || []).concat(st.names.logins || []))].sort() : [];
                if (!names.length) { peopleHost.append(el('p', 'field-help', 'The names appear once the export has arrived.')); return; }
                const accounts = st.accounts || [];
                names.forEach(n => {
                    if (!(n in people)) people[n] = stockMoveGuess(n, accounts);
                    const opts = [['', 'Choose who this is']].concat(accounts.map(a => [a.id, a.name]));
                    const pick = choiceSelect(opts, people[n], (v) => { people[n] = v; paint(); }, { label: 'Reactor account for ' + n });
                    const row = el('div', 'stock-move-person');
                    row.append(el('span', 'stock-move-name', n), pick);
                    peopleHost.append(row);
                });
            };
            const counts = (c) => c ? [['lines', c.items], ['history entries', c.history], ['snapshots', c.snapshots],
                ['quarters', c.quarters], ['warnings', c.warnings], ['suppliers', c.suppliers], ['orders', c.orders]]
                .filter(x => x[1] != null).map(x => Number(x[1]).toLocaleString('en-GB') + ' ' + x[0]).join(', ') : '';
            const paint = () => {
                const run = st && st.run, up = st && st.upload, running = !!(run && run.state === 'running');
                fileLine.textContent = up ? 'Arrived whole: ' + (up.bytes / 1048576).toFixed(1) + ' MB'
                    + (up.exported_at ? ', exported ' + fmtDate(up.exported_at) + ', ' + londonHM(up.exported_at) : '') + '.' : '';
                result.innerHTML = '';
                if (st && st.live) {
                    result.append(el('p', 'stock-move-good', stockMoveRowWords(st)));
                } else if (!run) {
                    result.append(el('p', 'field-help', 'Check the export once the names are matched. Nothing changes until you move it in.'));
                } else if (running) {
                    const w = el('p', 'stock-move-wait'); w.append(loader(), document.createTextNode(run.kind === 'move'
                        ? 'Moving in. This can take a few minutes: the window can be closed and opened again.'
                        : 'Checking every line, history entry and figure. This can take a few minutes.'));
                    result.append(w);
                } else if (run.state === 'passed') {
                    result.append(el('p', 'stock-move-good', 'Proven: ' + counts(run.counts) + ' match the stock app’s export exactly.'));
                } else if (run.state === 'failed' && (run.differences || []).length) {
                    result.append(el('p', 'stock-move-bad', run.words || 'The export and what Reactor would hold differ.'));
                    const ul = el('ul', 'stock-move-diffs');
                    ul.tabIndex = 0; ul.setAttribute('aria-label', 'The differences');   // it scrolls: reachable by keyboard
                    run.differences.forEach(d => ul.append(el('li', null, d)));
                    if (run.more) ul.append(el('li', null, 'and ' + run.more + ' more'));
                    result.append(ul);
                } else {
                    result.append(el('p', 'stock-move-bad', run.words || 'That did not finish.'));
                }
                const quiet = st && st.queue && st.queue.pending;
                if (quiet && !(st && st.live)) result.append(el('p', 'field-help', quiet + ' made order' + (quiet === 1 ? '' : 's')
                    + ' waiting for the stock app will be booked here once the stock sheet has moved in.'));
                choose.disabled = check.disabled = running || !!(st && st.live);
                go.disabled = running || !stockMoveReady(st, people);
            };
            const refresh = async () => {
                try { st = await api('/api/stock/move', { op: 'status' }); }
                catch (e) { result.innerHTML = ''; result.append(loadFailure('Where the move stands could not be read. ' + (e.message || ''), refresh)); return; }
                if (closed) return;
                drawPeople(); paint();
                clearTimeout(poll);
                const running = !!(st.run && st.run.state === 'running');
                if (running) poll = setTimeout(refresh, 2000);
                else if (wasRunning && st.live) stockMoveArrived();
                wasRunning = running;
            };
            choose.onclick = () => file.click();
            file.onchange = async () => {
                const f = file.files && file.files[0]; file.value = '';
                if (!f) return;
                setBusy(choose, true);
                try {
                    const text = await f.text();
                    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
                    const sha = [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join('');
                    const parts = stockMoveParts(text, STOCK_MOVE_PART), upload = String(Date.now());
                    for (let i = 0; i < parts.length; i++) {
                        fileLine.textContent = 'Sending ' + f.name + ': part ' + (i + 1) + ' of ' + parts.length + '.';
                        await api('/api/stock/move', { op: 'part', upload: upload, index: i, total: parts.length, text: parts[i], sha256: sha });
                    }
                    people = {};
                } catch (e) { toastError(e.message || 'The export did not arrive.'); }
                setBusy(choose, false);
                refresh();
            };
            const start = async (kind, btn) => {
                setBusy(btn, true);
                try { st = await api('/api/stock/move', { op: kind, people: people }); }
                catch (e) { toastError(e.message); }
                setBusy(btn, false);
                refresh();
            };
            check.onclick = () => start('check', check);
            go.onclick = async () => {
                const who = [...new Set(Object.values(people))].map(id => ((st.accounts || []).find(a => a.id === id) || {}).name).filter(Boolean);
                const yes = await uiConfirm('Move the stock sheet in now? From now on stock is kept here: the Stock tab opens for '
                    + (who.join(' and ') || 'the people matched') + ', made orders book their glass here, and the stock app should stay '
                    + 'switched off. This cannot be undone from here.', { title: 'Move the stock sheet in', okText: 'Move it in', danger: true });
                if (yes) start('move', go);
            };
            paint();
            refresh();
        }
        /* Once moved in: the account is read again, so the Stock tab appears. */
        async function stockMoveArrived() {
            try {
                const st = await authApi('/api/auth/state', {});
                if (st && st.me) { teamMe = st.me; applyRoleChrome(); addToast('The stock sheet has moved in. The Stock tab is open.', 'good'); }
            } catch (e) { /* the next sign-in shows it */ }
        }
