        /* ==================================================================
           Files: the office file server, minus the office. The folder tree
           and names live on the app's own volume; the bytes live in a
           Cloudflare R2 bucket. Uploads and downloads run browser-to-bucket
           on short-lived signed URLs, so a big artwork file moves at your
           own connection's speed and never through the app. Deleting is a
           30-day trash, never instant.
           ================================================================== */
        let filesCache = null, filesFolder = '', filesQ = '', filesSeg = 'files';
        /* The revision of the store in filesCache, and of the one last drawn.
           A look at the tree sends filesRev and an unchanged store comes back
           as {same: true} (the 2026-10-12 speed audit, S9). A copy patched
           from a delta answer is no revision the server named, so it holds
           none, and the next look fetches the store whole. */
        let filesRev = '', filesPaintedRev = '';
        let filesHeroAct = null;   // the page header's action slot, filled by the browser
        /* The Finder drive takes a password of its own, made here after a full
           sign-in and shown once. The Reactor password no longer opens it: the
           drive sits outside the Shopify login, so that password alone opened
           Files from anywhere and skipped sign-in codes. */
        function openDrivePanel(anchor) {
            dropPanel(anchor, (body, close) => {
                body.classList.add('drive-panel');
                const paint = (st, fresh) => {
                    body.replaceChildren();
                    body.append(el('h4', 'drive-title', 'Open Files in Finder'));
                    const how = el('p', 'drive-p');
                    how.append('In Finder, press Command K and enter ', el('b', null, davAddress()), '. Sign in as ',
                        el('b', null, st.username || 'your username'), ' with a drive password made here. Your Reactor password does not open the drive.');
                    body.append(how);
                    if (fresh) {
                        const box = el('div', 'drive-pw');
                        const code = el('code', null, fresh);
                        const cp = el('button', 'btn btn-sm'); cp.type = 'button'; cp.append(ico(I.copy), document.createTextNode('Copy'));
                        cp.onclick = () => copyText(fresh, 'Drive password copied.');
                        box.append(code, cp);
                        body.append(box, el('p', 'drive-note', 'Shown once. Let Finder keep it in your keychain; if it is lost, make a new one.'));
                    } else {
                        body.append(el('p', 'drive-note', st.has ? 'Your drive password was made on ' + fmtDate(st.made_at) + '.'
                                                                  : 'You have no drive password yet.'));
                    }
                    const acts = el('div', 'dpanel-row');
                    const make = el('button', 'btn btn-sm btn-primary', st.has ? 'Make a new one' : 'Make a drive password');
                    make.type = 'button';
                    make.onclick = async () => {
                        if (st.has && !await uiConfirm('Make a new drive password? The old one stops working, so Finder will ask for the new one.',
                            { title: 'New drive password', okText: 'Make a new one' })) return;
                        setBusy(make, true);
                        try { const r = await api('/api/files/drive', { op: 'create' }); paint(r, r.password); }
                        catch (e) { toastError(e.message); setBusy(make, false); }
                    };
                    acts.append(make);
                    if (st.has) {
                        const rm = el('button', 'btn btn-sm', 'Remove'); rm.type = 'button';
                        rm.onclick = async () => {
                            setBusy(rm, true);
                            try { paint(await api('/api/files/drive', { op: 'remove' })); toastOk('Drive password removed. Finder can no longer open the drive as you.'); }
                            catch (e) { toastError(e.message); setBusy(rm, false); }
                        };
                        acts.append(rm);
                    }
                    body.append(acts);
                };
                body.append(el('p', 'drive-note', 'Loading…'));
                api('/api/files/drive', {}).then(st => paint(st), e => { body.replaceChildren(el('p', 'drive-note', e.message)); });
            });
        }
        /* How many search hits, or rows of a folder, are painted at a time.
           The remainder is never hidden: the count of what is left sits on
           the Show more button. A folder keeps its count while it is open,
           so a redraw after an upload does not fold the list back up. */
        const FILES_HIT_STEP = 60;
        let filesHitCap = FILES_HIT_STEP, filesRowCap = FILES_HIT_STEP, filesRowCapFor = null;
        let filesPagedFocus = -1;
        const filesReveal = new Set();   // ids just made or renamed here, shown however they sort
        function filesPaged(list, rows, cap, makeRow, more) {
            /* A thousand files is about 34,000 elements, 155 to 237 ms of a
               desktop's main thread for every open (the 2026-10-12 speed
               audit, P2). Only the rows on the page are ever built. */
            rows.slice(0, cap).forEach((r, i) => {
                const n = makeRow(r);
                list.append(n);
                /* Show more draws the list again under the button, which took
                   the keyboard with it to the top of the page: it goes to the
                   first row Show more brought instead, once the list is in. */
                if (i === filesPagedFocus) {
                    const f = n.querySelector('.files-name') || n;
                    setTimeout(() => f.focus(), 0);
                }
            });
            filesPagedFocus = -1;
            if (rows.length > cap) {
                const b = el('button', 'btn', 'Show more (' + (rows.length - cap) + ' remaining)');
                b.style.cssText = 'margin:var(--sp-2) auto;display:block';
                b.onclick = () => { filesPagedFocus = cap; more(); };
                list.append(b);
            }
        }
        function filesCapFor(ids, cap, reveal) {
            /* How many rows to draw so that every id in reveal is among them,
               a whole page at a time, and never fewer than are drawn now. */
            let need = cap;
            ids.forEach((id, i) => { if (reveal.has(id)) need = Math.max(need, Math.ceil((i + 1) / FILES_HIT_STEP) * FILES_HIT_STEP); });
            return need;
        }
        let filesSort = 'name', filesSel = new Set();
        let filesUploads = [], filesQueue = [], filesActive = 0, filesNewFolder = false;

        function showFilesView() {
            if (filesCache) { renderFiles(); refreshFilesQuiet(); return; }
            loadFiles();
        }
        function filesInputBusy() {
            const a = document.activeElement;
            return !!(a && a.closest && a.closest('#files-content') && /^(input|textarea)$/i.test(a.tagName));
        }
        async function refreshFilesQuiet() {
            /* The store is shared with the rest of the team, so re-entering the
               tab quietly re-reads it; a repaint only happens when something
               actually changed and no one is mid-typing in a rename box. */
            try {
                const r = await api('/api/files/tree', filesRev ? { rev: filesRev } : {});
                const quiet = () => !filesInputBusy() && document.querySelector('#view-files.active');
                if (r && r.same) {
                    /* Nothing moved. Draw only if the last store that came
                       was never drawn (it arrived under someone's typing). */
                    if (filesCache && filesPaintedRev !== filesRev && quiet()) renderFiles();
                    return;
                }
                const drawn = JSON.stringify(r.store) === JSON.stringify(filesCache) && filesPaintedRev === filesRev;
                filesCache = r.store; filesRev = r.rev || '';
                if (drawn) { filesPaintedRev = filesRev; return; }
                if (quiet()) renderFiles();
            } catch (e) { /* the cached view stands until the next visit */ }
        }
        async function loadFiles() {
            const box = $('files-content'); box.innerHTML = '';
            const t = el('div', 'thinking'); t.append(loader(), el('span', null, 'Opening the file store…'));
            box.append(t);
            try {
                const r = await api('/api/files/tree', {});
                filesCache = r.store; filesRev = r.rev || '';
                renderFiles();
            } catch (e) {
                box.innerHTML = '';
                box.append(el('div', 'msg error', e.message || 'Could not load the files.'));
            }
        }
        async function filesOp(path, body) {
            /* Every write returns the fresh store, or, asked with delta, only
               what changed, which is patched in: either way the UI never
               guesses. */
            const r = await api(path, body);
            if (r && r.store) { filesCache = r.store; filesRev = r.rev || ''; }
            else if (r && r.delta) filesPatch(r.delta);
            return r;
        }
        function filesPatch(delta) {
            /* A record is set or, sent as null, removed; a folder likewise; a
               trash entry replaces any with its id; the space used is taken
               as sent. The server shapes each exactly as the whole store. */
            const c = filesCache;
            if (!c || !delta) return;
            Object.entries(delta.files || {}).forEach(([k, v]) => { if (v) c.files[k] = v; else delete c.files[k]; });
            Object.entries(delta.folders || {}).forEach(([k, v]) => { if (v) c.folders[k] = v; else delete c.folders[k]; });
            const tr = delta.trash || {};
            if (Object.keys(tr).length) {
                c.trash = (c.trash || []).filter(t => !(t.id in tr));
                Object.values(tr).forEach(v => { if (v) c.trash.push(v); });
            }
            if (delta.used != null) c.used = delta.used;
            if ('setup_error' in delta) c.setup_error = delta.setup_error;
            if (delta.names) c.names = delta.names;
            filesRev = '';
        }
        let filesRepaintT = 0, filesRepaintLast = 0;
        function filesRepaintSoon() {
            /* Finished uploads redraw the view at most every 300 ms, so files
               that finish together are drawn together: every file redrew it,
               and in a thousand-file folder each redraw was most of a second.
               A full redraw keeps the storage meter honest too; skipped while
               someone is typing in a rename box, where the list alone is
               redrawn. */
            if (filesRepaintT) return;
            filesRepaintT = setTimeout(() => {
                filesRepaintT = 0; filesRepaintLast = Date.now();
                if (!filesInputBusy() && document.querySelector('#view-files.active')) renderFiles();
                else if (renderFilesBrowser._paintList) renderFilesBrowser._paintList();
            }, Math.max(0, 300 - (Date.now() - filesRepaintLast)));
        }
        function filesProgress(u) {
            /* A progress tick moves one bar and one number. It rebuilt every
               row of the upload panel, many times a second per upload. */
            if (u._fill && u._label) { u._fill.style.width = u.pct + '%'; u._label.textContent = u.pct + '%'; return; }
            if (renderFilesBrowser._paintUploads) renderFilesBrowser._paintUploads();
        }
        function fmtBytes(n) {
            n = Number(n) || 0;
            if (n < 1024) return n + '\u00a0B';
            const u = ['KB', 'MB', 'GB', 'TB']; let i = -1;
            do { n /= 1024; i++; } while (n >= 1024 && i < u.length - 1);
            /* A no-break space: "12.4" on one line and "MB" on the next is
               how a size gets misread in a wrapping flex row. */
            return (n >= 10 ? Math.round(n) : n.toFixed(1)) + '\u00a0' + u[i];
        }
        const FILE_EXT_ICON = [
            [['pdf'], 'filePdf'],
            [['png', 'jpg', 'jpeg', 'gif', 'webp', 'heic', 'tif', 'tiff', 'bmp'], 'fileImg'],
            [['zip', 'rar', '7z', 'gz', 'tar'], 'fileZip'],
            [['ai', 'eps', 'svg', 'sketch'], 'penTool'],
            /* A sheet is a file, not a dashboard: the four-square grid glyph
               read as the app's own layout icon rather than as a document. */
            [['csv', 'xls', 'xlsx', 'numbers'], 'fileSheet'],
        ];
        function fileGlyph(name) {
            const ext = (String(name).split('.').pop() || '').toLowerCase();
            const hit = FILE_EXT_ICON.find(([exts]) => exts.indexOf(ext) >= 0);
            return I[hit ? hit[1] : 'fileDoc'];
        }
        function previewable(name) {
            const ext = (String(name).split('.').pop() || '').toLowerCase();
            return ['png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf'].indexOf(ext) >= 0;
        }
        /* The three facts a row reports, in the same three cells on every row
           of every Files list, so the sizes and the dates read as columns. */
        function filesCols(who, when, size, extra) {
            const c = el('div', 'files-cols' + (extra ? ' ' + extra : ''));
            c.append(el('span', 'who', who || ''), el('span', 'when', when || ''),
                     el('span', 'size', size || ''));
            return c;
        }
        /* On a phone a row's actions wait behind its ••• (12 Oct 2026, OPS-31):
           four 40 targets do not fit beside a file's name. The button lives in
           the actions cell, so the row keeps the list's columns. */
        function filesMore(acts, items, name) {
            const b = el('button', 'icon-btn files-more'); b.type = 'button'; b.innerHTML = I.moreH;
            b.setAttribute('aria-label', 'Actions for ' + name); b.setAttribute('aria-haspopup', 'menu');
            b.onclick = (e) => { e.stopPropagation(); dropMenu(b, items); };
            acts.append(b);
        }
        function filesHeadRow(whenLabel, wide) {
            const row = el('div', 'files-row files-head');
            row.append(el('span', 'files-ic'), el('span', 'files-name still', 'Name'),
                       filesCols('Owner', whenLabel, 'Size'));
            // The actions are a fixed-width column on every row; the header
            // holds that width so the cells beside it stay in their tracks.
            // The trash answers with text buttons, so its column is wider.
            row.append(el('div', 'files-acts' + (wide ? ' wide' : '')));
            return row;
        }
        function filesPathOf(folderId) {
            const names = []; let cur = folderId, hops = 0;
            while (cur && filesCache.folders[cur] && hops++ < 50) {
                names.unshift(filesCache.folders[cur].name);
                cur = filesCache.folders[cur].parent_id || '';
            }
            return names.join(' / ');
        }

        function renderFiles() {
            filesPaintedRev = filesRev;
            const box = $('files-content'); box.innerHTML = '';
            const d = filesCache;
            /* One line (copy plan, Files #1); the trash keeps its 30 days on the
               Trash tab. The actions that change the folder sit in the header's
               slot, which the browser fills when it builds them. */
            const hero = pageHead({ view: 'files', title: 'Files', line: 'The office file server, from anywhere.' });
            filesHeroAct = hero.querySelector('.ov-hero-act');
            box.append(hero);
            if (!d.configured) {
                /* No meter for storage that does not exist yet ('0 B of 50 GB
                   used' over an empty bar), and the house card head rather than
                   a settings row's title over an inline-styled 12px paragraph. */
                const card = el('div', 'card');
                const head = el('div', 'card-head');
                const st = el('h3', 'card-title', 'Connect the storage');
                const stInfo = infoButton('About the storage', { title: 'Connect the storage', guide: ['files', ''],
                    body: 'Files keeps its storage in a Cloudflare R2 bucket: durable, '
                    + 'priced in pennies, and the app signs every transfer so nothing is public. '
                    + 'Whoever looks after the app\u2019s hosting switches it on with three keys.' });
                head.append(titleInfo(st, stInfo));
                head.append(el('p', 'card-desc', 'Storage is not set up yet.'));
                card.append(head);
                if (d.setup_error) card.append(el('div', 'msg error', 'Storage answered with an error: ' + d.setup_error));
                box.append(card);
                return;
            }
            // Storage meter: how much of the space is spoken for.
            const pct = d.quota ? Math.min(100, Math.round(d.used * 100 / d.quota)) : 0;
            const meter = el('div', 'files-meter' + (pct >= 90 ? ' warn' : ''));
            const bar = el('div', 'bar'); const fill = el('i'); fill.style.width = pct + '%'; bar.append(fill);
            meter.append(bar, el('span', null, fmtBytes(d.used) + ' of ' + fmtBytes(d.quota) + ' used'));
            if (d.setup_error) box.append(el('div', 'msg error', 'Storage error: ' + d.setup_error
                + '. Uploads may fail until it is fixed.'));
            /* The meter at the tab row's right end (12 Oct 2026, OPS-29): it was
               a line of its own between the header and the tabs. */
            const tabsRow = el('div', 'page-tabs');
            tabsRow.append(tabStrip([['files', 'Files'], { key: 'trash', label: 'Trash', extra: d.trash.length ? el('span', 'crm-badge', String(d.trash.length)) : null }],
                                filesSeg, (k) => { filesSeg = k; renderFiles(); }, { label: 'Files sections' }));
            const end = el('div', 'page-tabs-end'); end.append(meter); tabsRow.append(end);
            box.append(tabsRow);
            const host = el('div'); box.append(host);
            if (filesSeg === 'trash') renderFilesTrash(host);
            else renderFilesBrowser(host);
        }

        function renderFilesTrash(host) {
            const rows = (filesCache.trash || []).slice()
                .sort((a, b) => (b.trashed_at || '').localeCompare(a.trashed_at || ''));
            const total = rows.reduce((n, f) => n + (f.size || 0), 0);
            /* The same card the browser tab is built in. Switching the segment
               used to throw the frame, the title and the toolbar away with it,
               so the list jumped 17px left and lost its border on the way. */
            const tCard = el('div', 'card');
            const tHead = el('div', 'card-head');
            /* The consequence stays as the line; the rest is the title's info
               button, word for word (copy plan, Files #10 and #11). */
            const tt = el('h3', 'card-title', 'Trash');
            const ttInfo = rows.length && infoButton('About the trash', { title: 'Trash',
                body: (rows.length === 1 ? '1 file' : rows.length + ' files') + ' (' + fmtBytes(total)
                    + ') waiting here. Everything is emptied for good 30 days after it was '
                    + 'deleted; put a file back to keep it, or delete it now to free its space.' });
            tHead.append(ttInfo ? titleInfo(tt, ttInfo) : tt);
            if (rows.length) tHead.append(el('p', 'card-desc', 'Deleted for good after 30 days.'));
            if (rows.length) {
                const tAct = el('div', 'card-act');
                const emp = el('button', 'btn btn-sm'); emp.append(ico(I.trash), document.createTextNode('Empty the trash'));
                emp.onclick = async () => {
                    if (!(await uiConfirm('Delete everything in the trash for good? '
                        + (rows.length === 1 ? '1 file' : rows.length + ' files') + ' ('
                        + fmtBytes(total) + ') cannot be put back after this.',
                        { title: 'Empty the trash', okText: 'Empty the trash' }))) return;
                    try { await filesOp('/api/files/file', { op: 'empty_trash' }); }
                    catch (e) { toastError(e.message); }
                    renderFiles();
                };
                tAct.append(emp);
                tHead.append(tAct);
            }
            tCard.append(tHead);
            const list = el('div', 'files-list');
            /* The same table as the browser tab: same three tracks, and the
               same header over them, so switching segment no longer removes
               the header line and shifts every column left. The header names
               the date, which is why the cell no longer has to carry the word
               "deleted" on every row. */
            if (!rows.length) list.append(el('div', 'files-empty', 'The trash is empty.'));
            else list.append(filesHeadRow('Deleted', true));
            rows.forEach(f => {
                const row = el('div', 'files-row');
                const slot = ico(fileGlyph(f.name)); slot.classList.add('files-ic');
                row.append(slot);
                const name = el('span', 'files-name still');
                name.textContent = f.name;
                const from = filesPathOf(f.folder_id);
                if (from) name.append(el('span', 'fpath', '  ·  ' + from));
                /* Cut with an ellipsis when the column is narrow, so said in full on hover. */
                name.title = f.name + (from ? ' (from ' + from + ')' : '');
                row.append(name, filesCols(byName(f.by), fmtDate(f.trashed_at), fmtBytes(f.size)));
                const acts = el('div', 'files-acts wide');
                // The small scale, like every other control in this card: at
                // the 32px one these rows stood 4px taller than the browser's.
                const back = el('button', 'btn btn-sm'); back.textContent = 'Put back';
                back.onclick = async () => {
                    back.disabled = true;
                    try { await filesOp('/api/files/file', { op: 'restore', id: f.id }); renderFiles(); }
                    catch (e) { back.disabled = false; toastError(e.message || 'Could not restore the file.'); }
                };
                const gone = el('button', 'btn btn-sm'); gone.textContent = 'Delete now';
                gone.onclick = async () => {
                    if (!(await uiConfirm('Delete "' + f.name + '" for good? It cannot be put back after this.',
                                          { title: 'Delete for good', okText: 'Delete for good' }))) return;
                    gone.disabled = true;
                    try { await filesOp('/api/files/file', { op: 'destroy', id: f.id }); renderFiles(); }
                    catch (e) { gone.disabled = false; toastError(e.message || 'Could not delete the file.'); }
                };
                acts.append(back, gone);
                row.append(acts);
                list.append(row);
            });
            /* The card hands its gutter to a child as PADDING, and a list that
               draws its own border needs that as an inset instead: wrapped, it
               lines up with the browser tab's list to the pixel. */
            const listHost = el('div'); listHost.append(list);
            tCard.append(listHost);
            host.append(tCard);
        }

        async function download(fid) {
            try {
                const r = await api('/api/files/download-url', { id: fid });
                // The signed link is served as an attachment, so navigating to it
                // triggers the download and the page stays put. A popup window
                // would be blocked here (we run inside the admin's iframe).
                const a = document.createElement('a');
                a.href = r.url; a.rel = 'noopener';
                document.body.append(a); a.click(); a.remove();
            } catch (e) { toastError(e.message || 'Could not fetch the file.'); }
        }
        async function openPreview(fid, f) {
            const win = dialog({ title: f.name, size: 'disp-modal', bodyClass: 'fprev-body' });
            const { overlay, modal, head, x, body } = win;
            const close = win.close;
            (function(){ const t = el('div', 'thinking');
                t.append(loader(), el('span', null, 'Opening\u2026')); body.append(t); })();
            const foot = el('div', 'modal-foot');
            foot.append(el('span', 'fprev-meta',
                fmtBytes(f.size) + ' · ' + fmtDate(f.uploaded_at || f.created_at)
                + (byName(f.by) ? ' · ' + byName(f.by) : '')));
            const dl = el('button', 'btn'); dl.append(ico(I.download), document.createTextNode('Download'));
            dl.onclick = () => download(fid);
            foot.append(dl);
            modal.append(foot);
            try {
                const r = await api('/api/files/download-url', { id: fid, preview: true });
                body.innerHTML = '';
                if (r.type === 'application/pdf') {
                    const fr = document.createElement('iframe');
                    fr.src = r.url; body.append(fr);
                } else {
                    const img = document.createElement('img');
                    img.alt = f.name; img.src = r.url; body.append(img);
                }
            } catch (e) {
                body.innerHTML = '';
                body.append(el('div', 'msg error', e.message || 'Could not open the preview.'));
            }
        }
        function openMovePicker(ids, after) {
            /* Pick a destination folder; works everywhere a drag cannot. */
            const win = dialog({ title: 'Move ' + (ids.length === 1 ? 'file' : ids.length + ' files') + ' to',
                                 size: 'confirm-modal', overlayClass: 'confirm-overlay' });
            const { overlay, modal, head, x, body } = win;
            const pick = async (folderId) => {
                win.close();
                try {
                    const r = await filesOp('/api/files/file', ids.length === 1
                        ? { op: 'move', id: ids[0], folder_id: folderId }
                        : { op: 'move', ids: ids, folder_id: folderId });
                    /* A file the folder already had a namesake of stays put;
                       the server says which, and silence here read as moved. */
                    if (r && r.skipped && r.skipped.length) {
                        addToast(r.skipped.join(', ') + (r.skipped.length === 1 ? ' was' : ' were')
                            + ' left behind: that folder already holds a file with the same name.');
                    }
                } catch (e) { toastError(e.message); }
                filesSel.clear();
                if (after) after();
            };
            const rootBtn = el('button', 'fpick-row');
            rootBtn.append(ico(I.folder), document.createTextNode(' All files'));
            rootBtn.onclick = () => pick('');
            body.append(rootBtn);
            const walk = (parent, depth) => {
                Object.entries(filesCache.folders)
                    .filter(([, fo]) => String(fo.parent_id || '') === parent)
                    .sort((a, b) => a[1].name.localeCompare(b[1].name))
                    .forEach(([fid2, fo]) => {
                        const b = el('button', 'fpick-row');
                        b.style.paddingLeft = (10 + depth * 18) + 'px';
                        b.append(ico(I.folder), document.createTextNode(' ' + fo.name));
                        b.onclick = () => pick(fid2);
                        body.append(b);
                        if (depth < 8) walk(fid2, depth + 1);
                    });
            };
            walk('', 1);
        }
        function renderFilesBrowser(host) {
            // A folder that vanished (another machine deleted it) must not
            // strand the view on an empty nowhere.
            if (filesFolder && !filesCache.folders[filesFolder]) filesFolder = '';
            /* Composed the way the reference composes its file manager: New
               folder and Upload live on the right of the PAGE header (the
               slot renderFiles leaves in the hero), and the toolbar under the
               card's title carries only the search and the sort. */
            const fCard = el('div', 'card');
            const fHead = el('div', 'card-head');
            /* The title's words change with the folder and the search; its info
               button holds how dragging works (copy plan, Files #5). */
            const fTitleEl = el('h3', 'card-title');
            const fTitleText = el('span', null, 'Files');
            fTitleEl.append(fTitleText);
            const fInfo = infoButton('Moving and uploading files', { title: 'Files', guide: ['files', ''],
                body: 'Drag files, or whole folders, anywhere on the list to upload them here. '
                    + 'Drag a file onto a folder, or onto a step of the path above, to move it.' });
            const fDescEl = el('p', 'card-desc', '');
            fHead.append(titleInfo(fTitleEl, fInfo), fDescEl);
            const up = el('button', 'btn btn-primary'); up.append(ico(I.upload), document.createTextNode('Upload'));
            const fi = document.createElement('input');
            fi.type = 'file'; fi.multiple = true; fi.style.display = 'none';
            fi.onchange = () => { filesEnqueue(fi.files); fi.value = ''; };
            up.onclick = () => {
                if (filesQ) { toastError('Clear the search first, so the upload has a folder to land in.'); return; }
                fi.click();
            };
            const nf = el('button', 'btn'); nf.append(ico(I.folderPlus), document.createTextNode('New folder'));
            nf.onclick = () => { filesNewFolder = true; paintList(); };
            const drv = el('button', 'btn files-drv'); drv.append(ico(I.hardDrive), el('span', 'drv-txt', 'Finder drive'));
            drv.title = 'Open these files as a drive on a Mac'; drv.setAttribute('aria-label', 'Finder drive');
            drv.onclick = () => openDrivePanel(drv);
            if (filesHeroAct) { filesHeroAct.innerHTML = ''; filesHeroAct.append(drv, nf, up, fi); }
            fCard.append(fHead);
            const qWrap = tableSearch('Search files…', filesQ, null);
            const q = qWrap.input;
            filesHitCap = FILES_HIT_STEP;
            /* Debounced, like the labels Find box. Measured against 8,000 files:
               a broad term that matches everything cost 1,912 ms of blocked JS
               per keystroke, and with no debounce a five letter word ran that
               five times, the early letters being the broadest and slowest. */
            q.oninput = () => {
                filesQ = q.value.trim();
                clearTimeout(q._t);
                q._t = setTimeout(() => { filesHitCap = FILES_HIT_STEP; paintCrumbs(); paintList(); }, 180);
            };
            const srt = filterChip('Sort', [['name', 'Name'], ['newest', 'Newest first'],
                                            ['largest', 'Largest first']],
                filesSort, (v) => { filesSort = v; renderFiles(); });
            fCard.append(tableTools([qWrap], [srt]));
            host.append(fCard);

            const crumbsHost = el('div', 'files-slot'); fCard.append(crumbsHost);
            const upHost = el('div', 'files-slot'); fCard.append(upHost);
            /* The bulk bar has its own host so that ticking a box does not
               have to rebuild the list under the tick that was just pressed. */
            const bulkHost = el('div', 'files-slot'); fCard.append(bulkHost);
            const listHost = el('div'); fCard.append(listHost);
            // Filled by paintList: what the sentence may promise depends on
            // what is drawn, and a search has neither folders nor uploads.
            const hintEl = el('div', 'files-hint'); fCard.append(hintEl);

            function crumbBtn(label, fid, here) {
                const b = el('button', 'files-crumb' + (here ? ' here' : ''), label);
                if (!here) b.onclick = () => { filesFolder = fid; filesQ = ''; q.value = ''; paintCrumbs(); paintList(); };
                // A crumb is also a place to drop a file: "move it up there".
                b.ondragover = (e) => { if (dragFileId) { e.preventDefault(); b.classList.add('dropok'); } };
                b.ondragleave = () => b.classList.remove('dropok');
                b.ondrop = (e) => { e.preventDefault(); b.classList.remove('dropok'); if (dragFileId) moveFile(dragFileId, fid); };
                return b;
            }
            function paintCrumbs() {
                crumbsHost.innerHTML = '';
                const crumbs = el('div', 'files-crumbs');
                if (filesQ) {
                    crumbs.append(el('span', 'files-crumb here', 'Search results'));
                    crumbsHost.append(crumbs);
                    return;
                }
                const chain = []; let cur = filesFolder, hops = 0;
                while (cur && filesCache.folders[cur] && hops++ < 50) {
                    chain.unshift([cur, filesCache.folders[cur].name]);
                    cur = filesCache.folders[cur].parent_id || '';
                }
                /* At the root there is nowhere to go back to, and the card
                   title above already says "All files". A crumb trail of one
                   step is the same word printed twice. */
                if (!chain.length) return;
                crumbs.append(crumbBtn('All files', '', false));
                chain.forEach(([fid, name], i) => {
                    crumbs.append(ico(I.chev), crumbBtn(name, fid, i === chain.length - 1));
                });
                crumbsHost.append(crumbs);
            }

            let dragFileId = null;
            async function moveFile(fid, folderId) {
                try { await filesOp('/api/files/file', { op: 'move', id: fid, folder_id: folderId }); paintList(); }
                catch (e) { toastError(e.message || 'Could not move the file.'); }
            }

            function inlineRename(row, nameEl, current, save) {
                const inp = document.createElement('input');
                inp.className = 'files-rename'; inp.value = current;
                let done = false;
                const finish = (commit) => {
                    if (done) return; done = true;
                    if (commit && inp.value.trim() && inp.value.trim() !== current) save(inp.value.trim());
                    else paintList();
                };
                inp.onkeydown = (e) => { if (e.key === 'Enter') finish(true); if (e.key === 'Escape') finish(false); };
                inp.onblur = () => finish(true);
                row.replaceChild(inp, nameEl);
                inp.focus(); inp.select();
            }

            /* Every folder's totals in one pass over the files, rolled up from
               the deepest folder outwards, because a folder reports what is
               under it and not only what sits directly inside it. The rows
               used to run two full scans of the file map EACH. */
            function folderTotals() {
                const st = {};
                const of = (id) => (st[id] || (st[id] = { files: 0, size: 0, at: '' }));
                Object.values(filesCache.files).forEach(f => {
                    const s = of(String(f.folder_id || ''));
                    s.files++; s.size += (f.size || 0);
                    const at = String(f.uploaded_at || f.created_at || '');
                    if (at > s.at) s.at = at;
                });
                const depth = (id) => {
                    let d = 0, cur = id;
                    while (cur && filesCache.folders[cur] && d < 50) { cur = filesCache.folders[cur].parent_id || ''; d++; }
                    return d;
                };
                Object.keys(filesCache.folders).sort((a, b) => depth(b) - depth(a)).forEach(id => {
                    const s = of(id), p = of(String(filesCache.folders[id].parent_id || ''));
                    p.files += s.files; p.size += s.size;
                    if (s.at > p.at) p.at = s.at;
                });
                return st;
            }
            let fTotals = {};

            function folderRow(fid, f) {
                const row = el('div', 'files-row is-folder');
                const chip = el('span', 'files-chip'); chip.innerHTML = I.folder;
                row.append(chip);
                const name = el('button', 'files-name', f.name); name.title = f.name;
                name.onclick = () => { filesFolder = fid; paintCrumbs(); paintList(); };
                const subs = Object.values(filesCache.folders).filter(x => (x.parent_id || '') === fid).length;
                const tot = fTotals[fid] || { files: 0, size: 0, at: '' };
                const bits = [];
                if (subs) bits.push(subs === 1 ? '1 folder' : subs + ' folders');
                if (tot.files) bits.push(tot.files === 1 ? '1 file' : tot.files + ' files');
                // What is in the folder belongs to its name, the way the
                // reference prints it under the folder's title.
                name.append(el('span', 'fpath', '  ·  ' + (bits.length ? bits.join(', ') : 'Empty')));
                row.append(name);
                /* Owner is who made the folder (12 Oct 2026): it was blank. */
                row.append(filesCols(byName(f.by), tot.at ? fmtDate(tot.at) : '', tot.size ? fmtBytes(tot.size) : ''));
                const acts = el('div', 'files-acts');
                const rn = el('button', 'icon-btn'); rn.innerHTML = I.edit; rn.title = 'Rename folder';
                rn.onclick = () => inlineRename(row, name, f.name, async (v) => {
                    try { await filesOp('/api/files/folder', { op: 'rename', id: fid, name: v }); filesReveal.add(fid); } catch (e) { toastError(e.message); }
                    paintList();
                });
                const del = el('button', 'icon-btn'); del.innerHTML = I.trash; del.title = 'Delete folder (must be empty)';
                del.onclick = async () => {
                    try { await filesOp('/api/files/folder', { op: 'delete', id: fid }); paintCrumbs(); paintList(); }
                    catch (e) { toastError(e.message || 'Could not delete the folder.'); }
                };
                acts.append(rn, del);
                filesMore(acts, [{ label: 'Rename', icon: I.edit, onClick: () => rn.click() },
                                 { label: 'Delete folder', icon: I.trash, onClick: () => del.click() }], f.name);
                row.append(acts);
                // Folders accept dropped rows (move) and dropped OS files (upload into it).
                row.ondragover = (e) => { e.preventDefault(); e.stopPropagation(); row.classList.add('dropok'); };
                row.ondragleave = () => row.classList.remove('dropok');
                row.ondrop = (e) => {
                    e.preventDefault(); e.stopPropagation(); row.classList.remove('dropok');
                    if (dragFileId) { moveFile(dragFileId, fid); return; }
                    if (e.dataTransfer) filesIngestDrop(e.dataTransfer, fid);
                };
                return row;
            }
            function fileRow(fid, f, showPath) {
                const row = el('div', 'files-row' + (filesSel.has(fid) ? ' selected' : ''));
                // The glyph doubles as the select box: hover (or touch) shows
                // a checkbox in its place, and ticking one opens the bulk bar.
                const slot = el('span', 'fslot');
                const glyph = ico(fileGlyph(f.name));
                const cb = document.createElement('input');
                cb.type = 'checkbox'; cb.checked = filesSel.has(fid);
                cb.setAttribute('aria-label', 'Select ' + f.name);
                /* A tick changes this row and the bar, and nothing else. It
                   used to repaint the whole list, which destroyed the very
                   checkbox that had just been pressed: the keyboard lost its
                   place in the list and the next Space scrolled the page. */
                cb.onchange = () => {
                    cb.checked ? filesSel.add(fid) : filesSel.delete(fid);
                    row.classList.toggle('selected', cb.checked);
                    paintBulk();
                };
                slot.append(glyph, cb);
                row.append(slot);
                const name = el('button', 'files-name');
                name.textContent = f.name;
                if (showPath) {
                    const p = filesPathOf(f.folder_id);
                    if (p) name.append(el('span', 'fpath', '  ·  ' + p));
                }
                const canPeek = previewable(f.name);
                name.title = canPeek ? 'Preview' : 'Download';
                name.onclick = () => canPeek ? openPreview(fid, f) : download(fid);
                row.append(name);
                row.append(filesCols(byName(f.by), fmtDate(f.uploaded_at || f.created_at), fmtBytes(f.size)));
                const acts = el('div', 'files-acts');
                const dl = el('button', 'icon-btn'); dl.innerHTML = I.download; dl.title = 'Download';
                dl.onclick = () => download(fid);
                const mv = el('button', 'icon-btn'); mv.innerHTML = I.moveTo; mv.title = 'Move to folder';
                mv.onclick = () => openMovePicker([fid], () => { paintCrumbs(); paintList(); });
                const rn = el('button', 'icon-btn'); rn.innerHTML = I.edit; rn.title = 'Rename';
                rn.onclick = () => inlineRename(row, name, f.name, async (v) => {
                    // A rename must not quietly cost the file its type.
                    const oldExt = f.name.includes('.') ? f.name.split('.').pop() : '';
                    if (oldExt && !v.includes('.')) v = v + '.' + oldExt;
                    try { await filesOp('/api/files/file', { op: 'rename', id: fid, name: v }); filesReveal.add(fid); } catch (e) { toastError(e.message); }
                    paintList();
                });
                const del = el('button', 'icon-btn'); del.innerHTML = I.trash; del.title = 'Move to trash';
                del.onclick = async () => {
                    try { await filesOp('/api/files/file', { op: 'trash', id: fid }); renderFiles(); }
                    catch (e) { toastError(e.message || 'Could not delete the file.'); }
                };
                acts.append(dl, mv, rn, del);
                filesMore(acts, [{ label: 'Download', icon: I.download, onClick: () => dl.click() },
                                 { label: 'Move to folder', icon: I.moveTo, onClick: () => mv.click() },
                                 { label: 'Rename', icon: I.edit, onClick: () => rn.click() },
                                 { label: 'Move to trash', icon: I.trash, onClick: () => del.click() }], f.name);
                row.append(acts);
                row.draggable = true;
                row.ondragstart = (e) => { dragFileId = fid; e.dataTransfer.effectAllowed = 'move'; };
                row.ondragend = () => { dragFileId = null; };
                return row;
            }

            function sortFiles(entries) {
                if (filesSort === 'newest') {
                    return entries.sort((a, b) => String(b[1].uploaded_at || b[1].created_at || '')
                        .localeCompare(String(a[1].uploaded_at || a[1].created_at || '')));
                }
                if (filesSort === 'largest') {
                    return entries.sort((a, b) => (b[1].size || 0) - (a[1].size || 0));
                }
                return entries.sort((a, b) => a[1].name.localeCompare(b[1].name));
            }
            /* Its own paint, so a tick can redraw the bar without redrawing
               the rows. Empty is the resting state, and .files-slot:empty
               keeps the card's gap from opening around nothing. */
            function paintBulk() {
                bulkHost.innerHTML = '';
                if (!filesSel.size) return;
                const bar = el('div', 'files-bulk');
                bar.append(el('span', null, filesSel.size === 1 ? '1 file selected'
                    : filesSel.size + ' files selected'));
                // The toolbar above this bar is at the small scale; so is it.
                const mv = el('button', 'btn btn-sm', 'Move');
                mv.onclick = () => openMovePicker([...filesSel], () => { paintCrumbs(); paintList(); });
                const tr = el('button', 'btn btn-sm', 'Trash');
                tr.onclick = async () => {
                    try { await filesOp('/api/files/file', { op: 'trash', ids: [...filesSel] }); }
                    catch (e) { toastError(e.message); }
                    filesSel.clear();
                    renderFiles();
                };
                const clear = el('button', 'btn btn-sm', 'Clear');
                clear.onclick = () => {
                    filesSel.clear();
                    listHost.querySelectorAll('.files-row.selected').forEach(r => {
                        r.classList.remove('selected');
                        const c = r.querySelector('.fslot input'); if (c) c.checked = false;
                    });
                    paintBulk();
                };
                bar.append(mv, tr, clear);
                bulkHost.append(bar);
            }
            function paintList() {
                listHost.innerHTML = '';
                fTotals = folderTotals();
                /* The card's own title, kept honest on every repaint: a search
                   counts what it found, a folder counts what is in it. */
                const here = Object.values(filesCache.files)
                    .filter(f => (f.folder_id || '') === filesFolder).length;
                const subs = Object.values(filesCache.folders)
                    .filter(f => (f.parent_id || '') === filesFolder).length;
                if (filesQ) {
                    const ql = filesQ.toLowerCase();
                    const n = Object.values(filesCache.files).filter(f => f.name.toLowerCase().includes(ql)).length;
                    fTitleText.textContent = n + (n === 1 ? ' file matches' : ' files match');
                    fDescEl.textContent = 'Results from every folder.';
                } else {
                    const name = filesFolder && filesCache.folders[filesFolder]
                        ? filesCache.folders[filesFolder].name : 'All files';
                    fTitleText.textContent = name;
                    fDescEl.textContent = (here === 1 ? '1 file' : here + ' files')
                        + (subs ? ', ' + (subs === 1 ? '1 folder' : subs + ' folders') : '');
                }
                /* The sentence under the list describes what is drawn above
                   it. At the root there is no path to drop onto (paintCrumbs
                   draws no trail there), and in a search there is no folder
                   for an upload to land in, so a drop is refused. */
                /* Only a search needs a line: there is no folder for a drop to
                   land in. How dragging works is the title's info button. */
                hintEl.textContent = filesQ ? 'Clear the search to upload here.' : '';
                hintEl.hidden = !filesQ;
                dragFileId = null;   // a repaint may remove the row being dragged; its dragend never fires
                // Selection can only reference what is on screen.
                const live = new Set(Object.keys(filesCache.files));
                filesSel.forEach(i => { if (!live.has(i)) filesSel.delete(i); });
                paintBulk();
                const list = el('div', 'files-list');
                const fmap = filesCache.files;
                // The list swallows drops in every mode: an unhandled drop makes
                // the browser NAVIGATE to the dropped file, taking the app with it.
                list.ondragover = (e) => { if (!dragFileId) { e.preventDefault(); list.classList.add('drag'); } };
                list.ondragleave = (e) => { if (!e.relatedTarget || !list.contains(e.relatedTarget)) list.classList.remove('drag'); };
                list.ondrop = (e) => {
                    e.preventDefault(); list.classList.remove('drag');
                    if (dragFileId) return;
                    if (filesQ) { toastError('Clear the search first, so the upload has a folder to land in.'); return; }
                    if (e.dataTransfer) filesIngestDrop(e.dataTransfer, filesFolder);
                };
                if (filesQ) {
                    const ql = filesQ.toLowerCase();
                    const hits = sortFiles(Object.entries(fmap)
                        .filter(([, f]) => f.name.toLowerCase().includes(ql)));
                    if (filesReveal.size) { filesHitCap = filesCapFor(hits.map(e => e[0]), filesHitCap, filesReveal); filesReveal.clear(); }
                    if (!hits.length) list.append(el('div', 'files-empty', 'No file matches that search.'));
                    else list.append(filesHeadRow('Modified'));
                    /* Painted in pages, the way the CRM contacts list already
                       is. The count of what is not on screen is ON screen, so
                       nobody is ever shown fewer matches than there are. */
                    filesPaged(list, hits, filesHitCap, ([fid, f]) => fileRow(fid, f, true),
                        () => { filesHitCap += FILES_HIT_STEP; paintList(); });
                    listHost.append(list);
                    return;
                }
                const folders = Object.entries(filesCache.folders)
                    .filter(([, f]) => (f.parent_id || '') === filesFolder)
                    .sort((a, b) => a[1].name.localeCompare(b[1].name));
                const files = sortFiles(Object.entries(fmap)
                    .filter(([, f]) => (f.folder_id || '') === filesFolder));
                if (folders.length || files.length) list.append(filesHeadRow('Modified'));
                if (filesNewFolder) {
                    const row = el('div', 'files-row is-folder');
                    const chip = el('span', 'files-chip'); chip.innerHTML = I.folder;
                    row.append(chip);
                    const inp = document.createElement('input');
                    inp.className = 'files-rename'; inp.placeholder = 'Folder name';
                    let done = false;
                    const finish = async (commit) => {
                        if (done) return; done = true; filesNewFolder = false;
                        const v = inp.value.trim();
                        if (commit && v) {
                            try { const r = await filesOp('/api/files/folder', { op: 'add', name: v, parent_id: filesFolder, delta: 1 }); if (r && r.id) filesReveal.add(r.id); }
                            catch (e) { toastError(e.message || 'Could not create the folder.'); }
                        }
                        paintList();
                    };
                    inp.onkeydown = (e) => { if (e.key === 'Enter') finish(true); if (e.key === 'Escape') finish(false); };
                    inp.onblur = () => finish(true);
                    row.append(inp);
                    list.append(row);
                    setTimeout(() => inp.focus(), 0);
                }
                /* A folder is painted a page at a time too, its own folders
                   first. Its count starts again only in another folder. */
                if (filesRowCapFor !== filesFolder) { filesRowCapFor = filesFolder; filesRowCap = FILES_HIT_STEP; }
                /* A folder just made, or a row just renamed, is shown wherever
                   it sorts: the one row somebody is looking for. */
                if (filesReveal.size) {
                    filesRowCap = filesCapFor(folders.map(e => e[0]).concat(files.map(e => e[0])), filesRowCap, filesReveal);
                    filesReveal.clear();
                }
                filesPaged(list, folders.map(e => ['d', e]).concat(files.map(e => ['f', e])), filesRowCap,
                    ([kind, [fid, f]]) => kind === 'd' ? folderRow(fid, f) : fileRow(fid, f, false),
                    () => { filesRowCap += FILES_HIT_STEP; paintList(); });
                if (!folders.length && !files.length && !filesNewFolder)
                    list.append(emptyState({ icon: I.folder, text: 'No files here yet.', action: (() => {
                        const u = el('button', 'btn'); u.type = 'button'; u.append(ico(I.upload), document.createTextNode('Upload'));
                        u.onclick = () => fi.click(); return u; })() }));
                listHost.append(list);
            }

            function paintUploads() {
                upHost.innerHTML = '';
                filesUploads.forEach(u => {
                    const row = el('div', 'files-up' + (u.state === 'failed' ? ' failed' : ''));
                    row.append(ico(I.upload), el('span', 'upname', u.name));
                    const bar = el('div', 'bar'); const fill = el('i');
                    fill.style.width = (u.state === 'done' ? 100 : u.pct) + '%'; bar.append(fill);
                    row.append(bar);
                    const label = u.state === 'failed' ? (u.err || 'Upload failed.')
                        : u.state === 'waiting' ? 'Waiting…'
                        : u.state === 'signing' ? 'Starting…'
                        : u.state === 'confirming' ? 'Finishing…'
                        : u.state === 'done' ? 'Done' : u.pct + '%';
                    const labelEl = el('span', 'upstate', label);
                    row.append(labelEl);
                    // Only a sending row's bar and number move between states.
                    if (u.state === 'sending') { u._fill = fill; u._label = labelEl; } else { u._fill = u._label = null; }
                    if (u.state === 'failed') {
                        const rt = el('button', 'btn', 'Try again');
                        rt.onclick = () => { u.state = 'waiting'; u.pct = 0; u.err = ''; filesQueue.push(u.job); paintUploads(); filesPump(); };
                        row.append(rt);
                    }
                    upHost.append(row);
                });
            }
            renderFilesBrowser._paintUploads = paintUploads;
            renderFilesBrowser._paintList = paintList;
            paintCrumbs();
            paintUploads();
            paintList();
        }

        function filesEnqueue(fileList, intoFolder) {
            const base = intoFolder != null ? intoFolder : filesFolder;
            filesEnqueuePairs(Array.from(fileList || []).map(f => ({ file: f, folder: base })));
        }
        function filesEnqueuePairs(pairs) {
            if (!pairs.length) return;
            if (!filesCache || !filesCache.configured) { toastError('File storage is not connected yet. The Guide tab has the setup steps.'); return; }
            // Uploads that already finished stop cluttering the list once new work starts.
            filesUploads = filesUploads.filter(u => u.state !== 'done');
            pairs.forEach(p => {
                const u = { name: p.file.name, pct: 0, state: 'waiting', err: '' };
                u.job = { file: p.file, row: u, folder: p.folder };
                filesUploads.push(u);
                filesQueue.push(u.job);
            });
            if (renderFilesBrowser._paintUploads) renderFilesBrowser._paintUploads();
            filesPump();
        }

        /* ---- folder drops: recreate the dropped tree, then upload into it ---- */
        const FILES_JUNK = /^(\.DS_Store|\._|Thumbs\.db$|desktop\.ini$)/;
        const filesEntryFile = (entry) => new Promise((res, rej) => entry.file(res, rej));
        const filesReadBatch = (reader) => new Promise((res, rej) => reader.readEntries(res, rej));
        async function filesTraverse(entry, path, out, stats) {
            /* Walks a dropped entry. Directories are remembered even when empty,
               so the recreated tree is faithful; readEntries hands back at most
               100 children per call and must be drained until it answers []. */
            if (stats.capped) return;
            if (entry.isFile) {
                const f = await filesEntryFile(entry);
                if (FILES_JUNK.test(f.name)) { stats.junk++; return; }
                if (out.length >= 500) { stats.capped = true; return; }
                out.push({ file: f, relPath: path });
                return;
            }
            if (entry.isDirectory) {
                if (path.length >= 12) { stats.deep = true; return; }
                const here = path.concat(entry.name);
                stats.dirs.push(here);
                const reader = entry.createReader();
                for (;;) {
                    const batch = await filesReadBatch(reader);
                    if (!batch.length) break;
                    for (const e of batch) await filesTraverse(e, here, out, stats);
                }
            }
        }
        async function filesEnsurePath(path, baseFolder, memo) {
            /* Resolves ['Jobs','2026'] under baseFolder to a folder id, reusing
               an existing folder at each step (matched the way the server
               refuses duplicates: by name, case blind) and creating the rest. */
            let parent = baseFolder, key = '';
            for (const seg of path) {
                key += '/' + seg.toLowerCase();
                if (memo[key]) { parent = memo[key]; continue; }
                const hit = Object.entries(filesCache.folders).find(([, f]) =>
                    String(f.parent_id || '') === String(parent) && f.name.toLowerCase() === seg.toLowerCase());
                if (hit) { memo[key] = hit[0]; parent = hit[0]; continue; }
                const r = await filesOp('/api/files/folder', { op: 'add', name: seg, parent_id: parent, delta: 1 });
                memo[key] = r.id; parent = r.id;
            }
            return parent;
        }
        async function filesIngestPairs(pairs, baseFolder, stats) {
            /* The shared back half of every folder drop: make the folders,
               then queue each file into its own one. Sequential on folders so
               two branches never race the same new name. */
            stats = stats || { dirs: [], junk: 0, capped: false, deep: false };
            const memo = {};
            try {
                for (const p of stats.dirs) await filesEnsurePath(p, baseFolder, memo);
                const jobs = [];
                for (const p of pairs) jobs.push({ file: p.file, folder: await filesEnsurePath(p.relPath, baseFolder, memo) });
                if (renderFilesBrowser._paintList) renderFilesBrowser._paintList();
                filesEnqueuePairs(jobs);
            } catch (e) {
                toastError(e.message || 'The folders could not be created.');
                return;
            }
            if (stats.capped) toastError('That drop was very large: only the first 500 files were taken. Drop the rest separately.');
            if (stats.deep) toastError('Folders nested more than 12 deep were skipped.');
        }
        window.__filesIngest = filesIngestPairs;   // test hook: the drop path minus the native entry objects
        async function filesIngestDrop(dt, baseFolder) {
            const entries = Array.from(dt.items || [])
                .map(it => it.webkitGetAsEntry && it.webkitGetAsEntry()).filter(Boolean);
            if (!entries.some(e => e.isDirectory)) { filesEnqueue(dt.files, baseFolder); return; }
            const out = [], stats = { dirs: [], junk: 0, capped: false, deep: false };
            try {
                for (const e of entries) await filesTraverse(e, [], out, stats);
            } catch (err) {
                toastError('That folder could not be read. Open it and drag its files in instead.');
                return;
            }
            await filesIngestPairs(out, baseFolder, stats);
        }
        function filesPump() {
            // Three at a time: enough to keep the pipe full, not enough to choke it.
            while (filesActive < 3 && filesQueue.length) {
                filesActive++;
                filesSend(filesQueue.shift()).finally(() => { filesActive--; filesPump(); });
            }
        }
        async function filesSend(job) {
            const { file, row, folder } = job;
            const paint = () => { if (renderFilesBrowser._paintUploads) renderFilesBrowser._paintUploads(); };
            try {
                row.state = 'signing'; paint();
                const ctype = file.type || 'application/octet-stream';
                /* delta: each answer is what changed, not the whole store
                   (twice per file, about 85 KB each at 2,000 files). */
                const r = await filesOp('/api/files/upload-url',
                    { name: file.name, size: file.size, type: ctype, folder_id: folder, delta: 1 });
                row.state = 'sending'; paint();
                await new Promise((resolve, reject) => {
                    const x = new XMLHttpRequest();
                    x.open('PUT', r.url);
                    x.setRequestHeader('Content-Type', ctype);
                    x.upload.onprogress = (ev) => {
                        if (ev.lengthComputable) { row.pct = Math.round(ev.loaded * 100 / ev.total); filesProgress(row); }
                    };
                    x.onload = () => (x.status >= 200 && x.status < 300) ? resolve()
                        : reject(new Error('Storage refused the upload (status ' + x.status + ').'));
                    x.onerror = () => reject(new Error('The transfer failed. Check the connection and try again.'));
                    x.send(file);
                });
                row.state = 'confirming'; paint();
                await filesOp('/api/files/complete', { id: r.id, delta: 1 });
                row.state = 'done'; row.pct = 100;
                paint();
                filesRepaintSoon();
            } catch (e) {
                row.state = 'failed'; row.err = e.message || 'Upload failed.';
                paint();
            }
        }

