        /* ---------- skills ----------
           One card: the skills first, with search, New skill and Upload
           Markdown, each able to be opened, corrected, read by Reactor, used
           in chat, downloaded or deleted in place. A skill is Markdown: it is
           shown as a document, and a .md file (a Claude-style SKILL.md with its
           name and description header included) comes in as it was written. */
        let skills = [];
        let skillsLoadErr = '';    // a failed read is not an empty list
        /* What the server allows, as it says in every answer; these are only
           the defaults until the first read. */
        const skillCaps = { title: 120, body: 40000, when: 400, inject: 24000, upload: false };
        const skView = { q: '', editId: null, adding: false, draft: null, open: new Set(), readOpen: new Set(), reading: {}, uploads: null, busy: '' };
        const skHost = {};
        async function loadSkills() {
            skillsLoadErr = '';
            try {
                const d = await api('/api/skills', {});
                if (d && Array.isArray(d.skills)) skills = d.skills;
                if (d && d.caps) Object.assign(skillCaps, d.caps);
            } catch (e) { skillsLoadErr = e.message || 'Could not read your skills.'; }
            /* Not over unsaved typing: coming back to the tab re-rendered it and
               a half-written skill (the one thing here worth minutes of
               typing) was wiped, though a page unload already asked first. */
            const dirty = [...document.querySelectorAll('#skills-content .sk-input, #skills-content .sk-textarea')]
                .some(f => f.value !== (f.dataset.initial || ''));
            if ($('view-skills').classList.contains('active') && !dirty && !skView.uploads && !skView.busy) renderSkills();
            if ($('view-chat').classList.contains('active')) syncComposer();
        }
        async function skillOp(payload) {
            const d = await api('/api/skills', payload);
            if (d && Array.isArray(d.skills)) skills = d.skills;
            if (d && d.caps) Object.assign(skillCaps, d.caps);
            return d;
        }
        const skillUse = (s) => {
            const n = Number(s.used || 0);
            if (!n) return 'Not followed in an answer yet';
            return 'Followed in ' + n + (n === 1 ? ' answer' : ' answers') + (s.used_at ? ', last on ' + fmtDate(s.used_at) : '');
        };
        const nf = (n) => Number(n || 0).toLocaleString('en-GB');
        const kb = (n) => n < 1024 ? nf(n) + ' bytes' : nf(Math.round(n / 1024)) + ' KB';

        /* ---- a Markdown skill file ---- */
        /* A leading block is a header only when every line starting at the
           margin is 'key: value' (or a comment) and one key names the skill
           or says when it applies: a skill that opens with a '---' rule lost
           its first paragraph as a 'header'. The server reads it the same way. */
        const MD_FM_KEYS = ['name', 'title', 'description', 'when', 'when_to_use'];
        function yamlScalar(v) {
            v = String(v || '').trim();
            if (v.length >= 2 && v[0] === "'" && v[v.length - 1] === "'") return v.slice(1, -1).replace(/''/g, "'");
            if (v.length >= 2 && v[0] === '"' && v[v.length - 1] === '"') return v.slice(1, -1).replace(/\\"/g, '"').replace(/\\\\/g, '\\');
            return v;
        }
        function mdFrontmatter(text) {
            const t = String(text || '').replace(/\r\n?/g, '\n').replace(/^\ufeff/, '');
            const m = t.match(/^---[ \t]*\n([\s\S]*?)\n---[ \t]*(?:\n|$)/);
            if (!m) return { meta: {}, body: t };
            const lines = m[1].split('\n');
            const top = lines.filter(l => l.trim() && !/^[ \t]/.test(l));
            if (!top.length || !top.every(l => /^[A-Za-z_][\w-]*\s*:/.test(l) || l[0] === '#')) return { meta: {}, body: t };
            const raw = {}, mode = {}; let key = null;
            lines.forEach(line => {
                const kv = line.match(/^([A-Za-z_][\w-]*)\s*:\s*(.*)$/);
                if (kv && !/^[ \t]/.test(line)) {
                    key = kv[1].toLowerCase(); const v = kv[2].trim();
                    mode[key] = /^[>|][+-]?$/.test(v) ? v[0] : 'plain';
                    raw[key] = mode[key] === 'plain' ? v : '';
                } else if (line[0] === '#' || !key) {
                    /* a comment, or nothing to carry on */
                } else if (line.trim() && /^[ \t]/.test(line)) {
                    raw[key] = (raw[key] + (mode[key] === '|' ? '\n' : ' ') + line.trim()).trim();
                }
            });
            if (!MD_FM_KEYS.some(k => k in raw)) return { meta: {}, body: t };
            const meta = {};
            Object.keys(raw).forEach(k => { meta[k] = mode[k] === 'plain' ? yamlScalar(raw[k]) : raw[k]; });
            return { meta, body: t.slice(m[0].length) };
        }
        function skillWords(t) {
            /* A 'trade-enquiry-replies' name, or a file's name, read as words;
               an all lower case one gets a capital, 'SEO-checklist' keeps its. */
            t = String(t || '').trim();
            if (/^[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)+$/.test(t)) {
                t = t.replace(/[-_]+/g, ' ');
                if (t === t.toLowerCase()) t = cap(t);
            }
            return t;
        }
        /* Cut at a word, and say so: a 600-character description was cut
           mid-word at 400 without a sign. */
        function cutWords(s, n) {
            s = String(s || '').trim();
            if (s.length <= n) return { text: s, cut: false };
            let c = s.slice(0, n); const k = c.lastIndexOf(' ');
            if (k > n * 0.6) c = c.slice(0, k);
            return { text: c.replace(/[ ,;:]+$/, ''), cut: true };
        }
        function parseSkillMd(text, filename) {
            const fm = mdFrontmatter(text);
            let body = fm.body.trim();
            const rawName = String(fm.meta.name || '').trim();
            let title = String(fm.meta.title || '').trim() || skillWords(rawName);
            const h1 = body.match(/^#\s+(.+?)\s*#*\s*(?:\n|$)/);
            if (!title && h1) title = h1[1].trim();
            if (h1 && title && [title.toLowerCase(), rawName.toLowerCase()].includes(h1[1].trim().toLowerCase())) body = body.slice(h1[0].length).trim();
            if (!title && filename) title = skillWords(String(filename).replace(/\.(md|markdown|txt|text)$/i, ''));
            const when = String(fm.meta.description || fm.meta.when || fm.meta.when_to_use || '').replace(/\s+/g, ' ').trim();
            const tc = cutWords(title, skillCaps.title), wc = cutWords(when, skillCaps.when);
            return { title: tc.text, when: wc.text, content: body, cut: [tc.cut ? 'title' : '', wc.cut ? 'when it applies' : ''].filter(Boolean) };
        }
        /* A long document is split at its own headings, each part keeping its
           heading and named after it; only a section still too long is split
           at paragraphs, and only a paragraph too long is cut. */
        function splitSkill(text, cap) {
            const pack = (pieces, sep) => {
                const out = []; let cur = '';
                pieces.forEach(p => {
                    if (cur && cur.length + sep.length + p.length > cap) { out.push(cur); cur = p; }
                    else cur = cur ? cur + sep + p : p;
                });
                if (cur.trim()) out.push(cur);
                return out;
            };
            const paras = (sec) => {
                const bits = [];
                sec.split(/\n{2,}/).forEach(p => { while (p.length > cap) { bits.push(p.slice(0, cap)); p = p.slice(cap); } bits.push(p); });
                return pack(bits, '\n\n');
            };
            const secs = String(text).split(/\n(?=#{1,2}\s)/);
            const pieces = [];
            secs.forEach(sec => { if (sec.length <= cap) pieces.push(sec); else pieces.push(...paras(sec)); });
            return pack(pieces, '\n').map(x => x.trim()).filter(Boolean);
        }
        /* How a long text will be divided, in words that are true of it. */
        function splitHow(text) {
            if (/^#{1,2}\s/m.test(text)) return 'split at its headings';
            if (/\n\s*\n/.test(text)) return 'split at paragraph breaks';
            return 'cut into parts, as it has no headings or paragraph breaks';
        }
        function splitTitles(title, parts) {
            /* Each part named by its first heading when it starts with one, so
               the parts can be told apart and picked for the right question. */
            const seen = new Set();
            return parts.map((p, k) => {
                /* A part holding several sections is named by its first and
                   last: 'Pricing to Lead times', not 'Pricing' alone. */
                const hs = [...p.matchAll(/^#{1,2}\s+(.+?)\s*#*\s*$/gm)].map(m => m[1].trim());
                const h = p.match(/^#{1,3}\s+(.+?)\s*#*\s*(?:\n|$)/);
                let t = h ? title + ': ' + h[1].trim() + (hs.length > 1 && hs[hs.length - 1] !== h[1].trim() ? ' to ' + hs[hs.length - 1] : '')
                          : title + ' (' + (k + 1) + ' of ' + parts.length + ')';
                t = t.slice(0, skillCaps.title);
                if (seen.has(t.toLowerCase())) t = (title + ' (' + (k + 1) + ' of ' + parts.length + ')').slice(0, skillCaps.title);
                seen.add(t.toLowerCase());
                return t;
            });
        }
        /* Read as UTF-8, and when a file is not (an older Windows or Mac
           export), as Windows text with a warning: a £ became a question
           mark without a word. */
        async function readTextFile(f) {
            const buf = await f.arrayBuffer();
            try { return { text: new TextDecoder('utf-8', { fatal: true }).decode(buf), note: '' }; }
            catch (e) { return { text: new TextDecoder('windows-1252').decode(buf), note: 'This file is not UTF-8, so it was read as Windows text: check the £ signs and accents in the preview.' }; }
        }
        const UPLOAD_MAX = 20;
        const SKILL_FILE_MAX = 5 * 1024 * 1024;     // bytes, for Upload Markdown and Load from file alike
        async function readSkillFiles(files, room) {
            const all = [...(files || [])];
            const list = all.filter(f => /\.(md|markdown|txt|text)$/i.test(f.name) || /^text\/(markdown|plain|x-markdown)/.test(f.type));
            const take = list.slice(0, Math.max(0, room == null ? UPLOAD_MAX : room));
            const out = [];
            for (const f of take) {
                if (f.size > SKILL_FILE_MAX) { out.push({ name: f.name, size: f.size, err: 'Larger than 5 MB, so it was not read.' }); continue; }
                try {
                    const r = await readTextFile(f);
                    if (!r.text.trim()) { out.push({ name: f.name, size: f.size, err: 'The file is empty.' }); continue; }
                    const p = parseSkillMd(r.text, f.name);
                    out.push(Object.assign({ name: f.name, size: f.size, note: r.note, orig: { title: p.title, when: p.when }, saved: [] }, p));
                } catch (e) { out.push({ name: f.name, size: f.size, err: 'The file could not be read.' }); }
            }
            const other = all.length - list.length, over = list.length - take.length;
            if (other) toastError(other + (other === 1 ? ' file is' : ' files are') + ' not Markdown or text, so '
                + (other === 1 ? 'it was' : 'they were') + ' left out. A skill comes from a .md, .markdown or .txt file.');
            if (over) toastError('Up to ' + UPLOAD_MAX + ' files at a time: ' + over + (over === 1 ? ' was' : ' were') + ' left out. Add them once these are in.');
            return out;
        }
        function startUpload(files) {
            /* Not loaded comes first: the upload right arrives with the skills. */
            if (skillsLoadErr) { toastError('Your skills have not loaded yet, so nothing can be added until they do.'); return; }
            /* The server refuses it too; this says so before any file is read. */
            if (!skillCaps.upload) { toastError('Only the master account can upload skills from files. Write the skill here instead.'); return; }
            if (skView.busy) { toastError('Wait for these files to be added, then add more.'); return; }
            /* A drop while files are being checked joins them, as More files does. */
            if (!skView.uploads && !skillGuard()) return;
            const have = (skView.uploads || []).length;
            readSkillFiles(files, UPLOAD_MAX - have).then(items => {
                if (!items.length) return;
                skView.uploads = (skView.uploads || []).concat(items);
                skView.adding = false; skView.editId = null;
                paintSkills();
                /* The first of the files just added, so Tab walks on through the rest. */
                const row = skHost.card.querySelectorAll('.sk-upload .sk-up')[have];
                const f = row && (row.querySelector('.sk-input') || row.querySelector('.mem-btn'));
                if (f) f.focus();
            });
        }

        function renderSkills() {
            const box = $('skills-content'); box.innerHTML = '';
            box.classList.toggle('no-intro', !firstPaint('skills'));
            /* The header's action slot is where Customize goes. */
            box.append(pageHead({ view: 'skills', title: 'Skills', line: 'Playbooks Reactor follows in chat, reports and email drafts.' }));
            skHost.card = widget(el('div', 'card sk-card'), 'saved', 'full', 'Skills');
            skHost.use = widget(el('div', 'card sk-use'), 'usage', 'full', 'How they are used');
            /* How they are used first, one band of three (12 Oct 2026, WS-33). */
            box.append(skHost.use, skHost.card);
            /* Markdown files dropped anywhere on the card come in to be checked. */
            const card = skHost.card;
            const hasFiles = (e) => e.dataTransfer && [...(e.dataTransfer.types || [])].includes('Files');
            /* preventDefault for everyone, so a dropped file never opens in place of the page
               and anyone else is told why it was not taken; the card lights up only for the
               master account, the one that can upload. */
            card.addEventListener('dragover', (e) => {
                if (!hasFiles(e)) return; e.preventDefault();
                if (skillCaps.upload) card.classList.add('drop-on');
            });
            card.addEventListener('dragleave', (e) => { if (!card.contains(e.relatedTarget)) card.classList.remove('drop-on'); });
            card.addEventListener('drop', (e) => { if (!hasFiles(e)) return; e.preventDefault(); card.classList.remove('drop-on'); startUpload(e.dataTransfer.files); });
            paintSkills();
        }
        /* What the answers have actually followed: the skills followed most,
           and the ones never followed yet, which are the ones to reword or
           name in a question. */
        function paintSkillUse() {
            const card = skHost.use; if (!card) return;
            card.replaceChildren();
            card.hidden = !skills.length || !!skillsLoadErr;
            if (card.hidden) return;
            const head = el('div', 'card-head');
            const chars = skills.reduce((n, x) => n + String(x.content || '').length, 0);
            /* How skills are read, and the two lines of advice, word for word
               behind the title's info button (copy plan, Skills #4, #6, #7). */
            const ut = el('h3', 'card-title', 'How they are used');
            const uHelp = ['With each question Reactor reads in full the skills that fit it best, up to ' + nf(skillCaps.inject)
                    + ' characters in all, and any marked for every answer. A skill too long for that is given as what it asks, its headings and the parts that fit: in chat Reactor reads the section it needs, and reports and email drafts get the parts that match. The titles of the rest are there for chat to open when one fits. Yours come to ' + nf(chars) + ' characters.'];
            head.append(ut);
            card.append(head);
            const used = skills.filter(x => Number(x.used || 0) > 0).sort((a, b) => (b.used || 0) - (a.used || 0));
            const never = skills.filter(x => !Number(x.used || 0));
            const unread = skills.filter(x => !x.reading || x.reading.stale);
            const band = el('div', 'sk-use-band');
            const fact = (k, v) => { const b = el('div', 'sk-use-b'); b.append(el('div', 'sk-use-k', k), el('div', 'sk-use-v', v)); band.append(b); };
            fact('Followed most', used.length ? used.slice(0, 3).map(x => x.title + ' (' + x.used + ')').join(', ') : 'None yet');
            if (never.length && used.length) {
                fact('Not followed yet', never.slice(0, 5).map(x => x.title).join(', ') + (never.length > 5 ? ' and ' + (never.length - 5) + ' more' : ''));
                uHelp.push('A clear note of when each applies helps Reactor see where one fits, or pick it with Skills when you ask.');
            }
            if (unread.length) {
                fact('Not read by Reactor', unread.slice(0, 5).map(x => x.title).join(', ') + (unread.length > 5 ? ' and ' + (unread.length - 5) + ' more' : ''));
                uHelp.push('Having it read shows you what Reactor will do with each, and gives it a short version to use when a skill is too long to show in full.');
            }
            titleInfo(ut, infoButton('How skills are used', { title: 'How they are used', body: uHelp }));
            card.append(band);
        }
        function skillsDirty() {
            const f = skHost.card && [...skHost.card.querySelectorAll('.sk-input, .sk-textarea')];
            return !!(f && f.some(x => x.value !== (x.dataset.initial || ''))) || !!(skView.uploads && skView.uploads.length);
        }
        /* One editor at a time, and never over typing that is not saved. */
        function skillGuard() {
            if (!skillsDirty()) return true;
            toastError(skView.uploads && skView.uploads.length ? 'Add or cancel the files you are checking first.' : 'Save or cancel the skill you are writing first.');
            const f = skHost.card.querySelector('.sk-input, .sk-textarea'); if (f) f.focus();
            return false;
        }
        function paintSkills() {
            const card = skHost.card; if (!card) return;
            card.replaceChildren();
            const head = el('div', 'card-head');
            const yt = el('h3', 'card-title', 'Your skills');
            if (skills.length) yt.append(el('span', 'card-n', String(skills.length)));
            const ytInfo = infoButton('About skills', { title: 'Your skills', body: 'Rules and playbooks, each with a title and a note of when it applies.'
                    + (skillCaps.upload ? ' Drop Markdown files here to add them.' : '')
                    + (canEditInstructions() ? '' : ' Only an admin can add, change or delete a skill.') });
            head.append(titleInfo(yt, ytInfo));
            const acts = el('div', 'card-act');
            const up = el('button', 'btn btn-sm'); up.type = 'button';
            up.append(ico(I.upload), document.createTextNode('Upload Markdown'));
            up.title = 'Add skills from .md files, such as a SKILL.md';
            const fi = el('input'); fi.type = 'file'; fi.multiple = true; fi.hidden = true;
            fi.accept = '.md,.markdown,.txt,.text,text/markdown,text/plain';
            fi.onchange = () => { const fs = fi.files; startUpload(fs); fi.value = ''; };
            up.onclick = () => fi.click();
            const add = el('button', 'btn btn-sm btn-primary'); add.type = 'button';
            add.append(ico(I.plus), document.createTextNode('New skill'));
            /* Not while the list is unknown: a skill added blind may be one
               that is already there. */
            add.disabled = up.disabled = !!skillsLoadErr || skView.adding || !!skView.uploads;
            add.onclick = () => { if (!skillGuard()) return; skView.adding = true; skView.editId = null; skView.draft = null; paintSkills(); };
            /* Only the master account uploads files. With no skills the empty
               line carries both actions instead (12 Oct 2026, WS-34). */
            if (skillCaps.upload && skills.length) acts.append(up);
            if (canEditInstructions() && skills.length) acts.append(add);
            head.append(acts); card.append(head, fi);
            paintSkillUse();
            if (skillsLoadErr) {
                card.append(loadFailure('Your skills could not be loaded, so they cannot be shown yet. '
                    + skillsLoadErr + ' New skill waits until they load, so nothing is added twice.', loadSkills));
                return;
            }
            if (skView.uploads) card.append(skillUploads());
            if (skView.adding) card.append(skillEditor(null));
            if (!skills.length) {
                /* One line, carrying both actions (12 Oct 2026, WS-34). */
                if (!skView.adding && !skView.uploads) {
                    const firstActs = el('div', 'act-row');
                    if (skillCaps.upload) {
                        const up2 = el('button', 'btn'); up2.type = 'button'; up2.append(ico(I.upload), document.createTextNode('Upload Markdown'));
                        up2.title = up.title; up2.onclick = () => fi.click(); firstActs.append(up2);
                    }
                    if (canEditInstructions()) {
                        const add2 = el('button', 'btn'); add2.type = 'button'; add2.append(ico(I.plus), document.createTextNode('New skill'));
                        add2.onclick = add.onclick; firstActs.append(add2);
                    }
                    card.append(emptyState({ icon: I.book, text: 'No skills yet.', action: firstActs }));
                }
                return;
            }
            if (skills.length > 4) {
                const search = tableSearch('Search skills…', skView.q, (v) => { skView.q = v; paintSkillList(); });
                card.append(tableTools([search], []));
            }
            skHost.list = el('ul', 'sk-list'); card.append(skHost.list);
            paintSkillList();
            paintSkillUse();
        }
        function paintSkillList() {
            const list = skHost.list; if (!list) return;
            list.replaceChildren();
            const q = skView.q.trim().toLowerCase();
            const rows = skills.filter(s => !q || ((s.title || '') + '\n' + (s.when || '') + '\n' + (s.content || '')).toLowerCase().includes(q));
            if (!rows.length) { list.append(el('li', 'empty', 'No skills match.')); return; }
            rows.forEach(s => {
                const li = el('li', 'sk-item'); li.dataset.id = s.id;
                if (skView.editId === s.id) li.append(skillEditor(s)); else skillItem(li, s);
                list.append(li);
            });
        }

        /* ---- files being added ----
           Every file is shown before it is saved: its title, when it applies
           (from its header when it has one), how long it is, and the document
           itself; a file too long for one skill is shown as the parts it will
           become. Read and add has Reactor read each one as it is saved. While
           they are being added nothing in the review can change, and a file
           or part that fails stays in the review with its reason and Retry. */
        const uploadGood = () => (skView.uploads || []).filter(u => !u.err);
        /* The parts still to add. Saved parts are kept by their place in the
           file, not their title, so changing the title after a part has gone
           in retitles only what is left: it added the saved parts again. */
        function uploadPlan(u) {
            const parts = uploadParts(u);
            const titles = parts ? splitTitles(u.title.trim(), parts) : [u.title.trim()];
            return (parts || [u.content]).map((c, j) => ({ u, j, title: titles[j], content: c }))
                .filter(p => !(u.savedIdx || []).includes(p.j));
        }
        function uploadButtons() {
            /* The count on the button and the cost line follow the review as it changes. */
            const box = skHost.card && skHost.card.querySelector('.sk-upload'); if (!box || skView.busy) return;
            const n = uploadGood().reduce((k, u) => k + uploadPlan(u).length, 0);
            const read = box.querySelector('.sk-form-row .btn-primary'), plain = read && read.previousElementSibling;
            if (read) { read.lastChild.textContent = n === 1 ? 'Read and add' : 'Read and add ' + n + ' skills'; read.disabled = !n; }
            if (plain) plain.disabled = !n;
            const cost = box.querySelector('.sk-upload-cost');
            if (cost) cost.textContent = (n > 1 ? 'Read and add is ' + n + ' AI runs, one for each skill. ' : 'Read and add is an AI run. ')
                + 'Add without reading saves them as they are; each can be read later from the skill.';
        }
        function skillUploads() {
            const items = skView.uploads;
            const busy = !!skView.busy;
            const box = el('div', 'sk-upload'); box.setAttribute('role', 'group'); box.setAttribute('aria-label', 'Files to add as skills');
            const good = uploadGood();
            const n = good.reduce((k, u) => k + uploadPlan(u).length, 0);
            box.append(el('h4', 'sk-form-title', items.length === 1 ? 'Add a skill from a file' : 'Add skills from ' + items.length + ' files'));
            box.append(el('p', 'sk-upload-note', 'Check each title and when it applies. Read and add has Reactor read each skill closely as it is saved and write down what it will do, so you can see it has understood before it relies on it.'));
            const list = el('div', 'sk-up-list');
            items.forEach((u, k) => list.append(uploadRow(u, k, busy)));
            box.append(list);
            const row = el('div', 'sk-form-row');
            const more = el('button', 'btn btn-sm'); more.type = 'button'; more.append(ico(I.plus), document.createTextNode('More files'));
            const fi = el('input'); fi.type = 'file'; fi.multiple = true; fi.hidden = true; fi.accept = '.md,.markdown,.txt,.text,text/markdown,text/plain';
            fi.onchange = () => { const fs = fi.files; startUpload(fs); fi.value = ''; };
            more.onclick = () => fi.click();
            more.disabled = busy || items.length >= UPLOAD_MAX;
            if (items.length >= UPLOAD_MAX) more.title = 'Up to ' + UPLOAD_MAX + ' files at a time';
            const cancel = el('button', 'btn btn-sm'); cancel.type = 'button'; cancel.textContent = 'Cancel';
            cancel.disabled = busy;
            cancel.onclick = async () => {
                if (skView.busy) return;
                const edited = items.some(u => !u.err && u.orig && (u.title !== u.orig.title || u.when !== u.orig.when));
                if ((items.length > 1 || edited) && !await uiConfirm('Leave out ' + (items.length === 1 ? 'this file' : 'these ' + items.length + ' files') + '? Nothing from them has been added.',
                    { title: 'Cancel adding files', okText: 'Leave them out', cancelText: 'Keep checking' })) return;
                skView.uploads = null; paintSkills();
                const up = skHost.card.querySelector('.card-act .btn'); if (up) up.focus();
            };
            const plain = el('button', 'btn btn-sm'); plain.type = 'button'; plain.textContent = 'Add without reading';
            const read = el('button', 'btn btn-sm btn-primary'); read.type = 'button';
            read.append(ico(I.book), document.createTextNode(n === 1 ? 'Read and add' : 'Read and add ' + n + ' skills'));
            read.title = n === 1 ? 'An AI run: Reactor reads the skill and writes down when it applies and what it will do.'
                : n + ' AI runs, one for each skill: Reactor reads each and writes down when it applies and what it will do.';
            plain.disabled = read.disabled = !n || busy;
            plain.onclick = () => addUploads(false);
            read.onclick = () => addUploads(true);
            if (busy) { setBusy(read, true); read.lastChild.textContent = skView.busy; }
            row.append(more, fi, cancel, plain, read);
            box.append(row);
            box.append(el('p', 'sk-upload-cost', (n > 1 ? 'Read and add is ' + n + ' AI runs, one for each skill. ' : 'Read and add is an AI run. ')
                + 'Add without reading saves them as they are; each can be read later from the skill.'));
            return box;
        }
        function uploadParts(u) {
            if (u.err || u.content.length <= skillCaps.body) return null;
            return splitSkill(u.content, skillCaps.body);
        }
        function uploadClash(u, k) {
            const plan = uploadPlan(u).map(p => p.title.toLowerCase());
            const taken = skills.find(x => plan.includes(String(x.title || '').trim().toLowerCase()));
            if (taken) return 'You already have a skill called "' + taken.title + '". Give this one a different title.';
            const twin = skView.uploads.find((o, j) => j !== k && !o.err && o.title.trim().toLowerCase() === u.title.trim().toLowerCase());
            if (twin && u.title.trim()) return 'Another file here has the same title.';
            return '';
        }
        function uploadRow(u, k, busy) {
            const r = el('div', 'sk-up');
            const top = el('div', 'sk-up-top');
            top.append(ico(I.book), el('span', 'sk-up-name', u.name), el('span', 'sk-up-size', kb(u.size || 0)));
            const rm = el('button', 'mem-btn'); rm.type = 'button'; rm.append(ico(I.x));
            rm.title = 'Leave this file out'; rm.setAttribute('aria-label', 'Leave out ' + u.name);
            rm.disabled = busy;
            rm.onclick = () => {
                if (skView.busy) return;
                skView.uploads.splice(k, 1);
                if (!skView.uploads.length) skView.uploads = null;
                paintSkills();
                const next = skHost.card.querySelectorAll('.sk-upload .sk-up')[Math.min(k, (skView.uploads || []).length - 1)];
                const f = next && (next.querySelector('.sk-input') || next.querySelector('.mem-btn'));
                if (f) f.focus(); else { const b = skHost.card.querySelector('.card-act .btn'); if (b) b.focus(); }
            };
            top.append(rm); r.append(top);
            if (u.err) { const m = el('div', 'field-msg'); m.textContent = u.err; r.append(m); return r; }
            const f1 = el('label', 'sk-field'); f1.append(el('span', null, 'Title'));
            const ti = el('input', 'sk-input'); ti.maxLength = skillCaps.title; ti.value = u.title; ti.dataset.initial = ''; ti.readOnly = busy;
            const tMsg = el('div', 'field-msg'); tMsg.hidden = true; tMsg.id = 'sk-up-t-' + k; ti.setAttribute('aria-describedby', tMsg.id);
            f1.append(ti, tMsg);
            const f2 = el('label', 'sk-field'); f2.append(el('span', null, 'When it applies'));
            const wh = el('textarea', 'sk-input sk-when-input'); wh.rows = 3; wh.maxLength = skillCaps.when; wh.value = u.when; wh.dataset.initial = ''; wh.readOnly = busy;
            wh.placeholder = 'e.g. Replying to a trade customer about prices or lead times. Reactor can write this when it reads the skill.';
            f2.append(wh);
            const stat = el('div', 'sk-up-stat');
            const paint = () => {
                const parts = uploadParts(u);
                const msg = u.saveErr || (!ti.value.trim() ? 'Give the skill a title.' : uploadClash(u, k));
                tMsg.hidden = !msg; tMsg.textContent = msg; markInvalid(ti, !!msg);
                stat.replaceChildren();
                stat.append(document.createTextNode(nf(u.content.length) + ' characters'
                    + (parts ? ', more than one skill holds (' + nf(skillCaps.body) + '), so it will be added as ' + parts.length + ' skills, '
                        + splitHow(u.content) + ':' : '.')));
                if (parts) {
                    const ul = el('ul', 'sk-up-parts');
                    splitTitles(ti.value.trim() || u.title, parts).forEach((t, j) => {
                        const done = (u.savedIdx || []).includes(j);
                        ul.append(el('li', null, (done ? (u.savedTitles || {})[j] || t : t) + ' (' + nf(parts[j].length) + ' characters)' + (done ? ': added' : '')));
                    });
                    stat.append(ul);
                }
                if (u.note) stat.append(el('p', 'sk-up-warn', u.note));
                if ((u.cut || []).length) stat.append(el('p', 'sk-up-warn', 'Its ' + u.cut.join(' and ') + ' was longer than a skill holds, so it was shortened at a word. Check it above.'));
            };
            ti.addEventListener('input', () => { u.title = ti.value; u.saveErr = ''; paint(); uploadButtons(); });
            wh.addEventListener('input', () => { u.when = wh.value; });
            paint();
            const pv = el('details', 'sk-preview');
            const sum = el('summary'); sum.textContent = 'Preview the document';
            const doc = el('div', 'md sk-preview-doc');
            pv.addEventListener('toggle', () => { if (pv.open && !doc.childNodes.length) doc.append(mdNodes(u.content)); });
            pv.append(sum, doc);
            r.append(f1, f2, stat, pv);
            return r;
        }
        async function addUploads(read) {
            const rows = uploadGood();
            const bad = rows.find((u) => !u.title.trim() || uploadClash(u, skView.uploads.indexOf(u)));
            if (bad) {
                paintSkills();
                const f = skHost.card.querySelector('.sk-upload [aria-invalid="true"]'); if (f) f.focus();
                toastError('Give every file a title of its own first.');
                return;
            }
            const plan = [];
            rows.forEach(u => { u.saveErr = ''; plan.push(...uploadPlan(u)); });
            if (!plan.length) return;
            const say = (t) => { skView.busy = t; const b = skHost.card.querySelector('.sk-upload .btn-primary'); if (b && b.lastChild) b.lastChild.textContent = t; };
            say('Adding 1 of ' + plan.length + '…'); paintSkills();
            const made = [], failed = [];
            for (let i = 0; i < plan.length; i++) {
                const p = plan[i];
                say('Adding ' + (i + 1) + ' of ' + plan.length + '…');
                try {
                    await skillOp({ op: 'add', title: p.title, content: p.content, when: p.u.when.trim(), file: p.u.name });
                    const s = skills.find(x => (x.title || '').trim().toLowerCase() === p.title.toLowerCase());
                    if (s) made.push(s.id);
                    (p.u.savedIdx = p.u.savedIdx || []).push(p.j);
                    (p.u.savedTitles = p.u.savedTitles || {})[p.j] = p.title;
                } catch (e) {
                    failed.push(p.title);
                    const m = e.message || 'Not saved.';
                    p.u.saveErr = (p.u.saveErr ? p.u.saveErr + ' ' : '') + (uploadParts(p.u) ? '"' + p.title + '" was not added: ' : '') + m;
                }
            }
            const whyNot = {};
            if (read) {
                for (let i = 0; i < made.length; i++) {
                    say('Reading ' + (i + 1) + ' of ' + made.length + '…');
                    try {
                        const d = await api('/api/skills/read', { id: made[i] });
                        if (d && Array.isArray(d.skills)) skills = d.skills;
                        skView.readOpen.add(made[i]);
                    } catch (e) { const w = e.message || 'It could not be read.'; (whyNot[w] = whyNot[w] || []).push((skills.find(x => x.id === made[i]) || {}).title); }
                }
            }
            skView.busy = '';
            /* A file stays while any part of it is still to add; files that
               could not be read are named and go. */
            const unreadable = skView.uploads.filter(u => u.err).map(u => u.name);
            skView.uploads = skView.uploads.filter(u => !u.err && uploadPlan(u).length);
            if (!skView.uploads.length) skView.uploads = null;
            paintSkills();
            const n = made.length, unread = Object.values(whyNot).reduce((a, b) => a + b.length, 0);
            if (n) toastOk((n === 1 ? 'One skill added' : n + ' skills added') + (read && !unread
                ? (n === 1 ? ' and read. Check what Reactor will do under it.' : ' and read. Check what Reactor will do under each.') : '.'));
            Object.keys(whyNot).forEach(w => {
                const k = whyNot[w].length;
                /* One reason, said once, in words that fit however many it stopped. */
                let why = w.replace(/\s*Try again\.?\s*$/i, '').replace(/\.+$/, '');
                if (k > 1) why = why.replace(/\bthis skill\b/gi, 'them');
                toastError((k === 1 ? '"' + whyNot[w][0] + '" was' : k + ' skills were') + ' added but not read: ' + why + '. '
                    + (k === 1 ? 'It can be read from the skill.' : 'Each can be read from its skill.'));
            });
            if (failed.length) toastError((failed.length === 1 ? 'One skill was' : failed.length + ' skills were') + ' not added. The reason is under the file, which stays here to try again.');
            if (unreadable.length) toastError('Not added, as ' + (unreadable.length === 1 ? 'it' : 'they') + ' could not be read: ' + unreadable.join(', ') + '.');
            const first = n && skHost.card.querySelector('.sk-item[data-id="' + made[0] + '"] .sk-title');
            const again = skHost.card.querySelector('.sk-upload [aria-invalid="true"]');
            if (again) again.focus();
            else if (first) { first.tabIndex = -1; first.focus(); first.scrollIntoView({ block: 'nearest' }); }
        }

        /* Reactor reads one skill closely and writes down how it understands
           it: when it applies, what it will do, where it would use it and
           what is unclear. An AI run, started only by its button. */
        async function readSkill(id, btn) {
            if (skView.reading[id]) return;
            skView.reading[id] = true; if (btn) setBusy(btn, true);
            let ok = false;
            try {
                const d = await api('/api/skills/read', { id: id });
                if (d && Array.isArray(d.skills)) skills = d.skills;
                skView.readOpen.add(id); ok = true;
            } catch (e) { toastError('Not read. ' + (e.message || '')); }
            delete skView.reading[id]; if (btn) setBusy(btn, false);
            if (!ok) return;
            toastOk('Reactor has read it. What it will do is under the skill.');
            const li = skHost.list && skHost.list.querySelector('.sk-item[data-id="' + id + '"]');
            const s = skills.find(x => x.id === id);
            /* Only that skill is drawn again, so nothing being written elsewhere is lost. */
            if (li && s && skView.editId !== id) { li.replaceChildren(); skillItem(li, s); const r = li.querySelector('.sk-reading summary'); if (r) r.focus(); }
            paintSkillUse();
        }
        function readingPanel(s) {
            const r = s.reading;
            const d = el('details', 'sk-reading');
            if (skView.readOpen.has(s.id)) d.open = true;
            d.addEventListener('toggle', () => { if (d.open) skView.readOpen.add(s.id); else skView.readOpen.delete(s.id); });
            const sum = el('summary');
            sum.append(document.createTextNode('How Reactor reads it'));
            if (r.stale) sum.append(el('span', 'lbl-chip note', 'Changed since it was read'));
            const qn = (r.questions || []).length;
            if (qn) sum.append(el('span', 'lbl-chip note', qn === 1 ? '1 point to check' : qn + ' points to check'));
            d.append(sum);
            const body = el('div', 'sk-reading-body');
            const dl = el('dl', 'sk-facts');
            if (r.when) dl.append(el('dt', null, 'Applies when'), el('dd', null, r.when));
            if ((r.rules || []).length) {
                const ol = el('ol', 'sk-rules'); r.rules.forEach(x => ol.append(el('li', null, x)));
                const dd = el('dd'); dd.append(ol);
                dl.append(el('dt', null, 'What it will do'), dd);
            }
            if ((r.examples || []).length) {
                const dd = el('dd', 'sk-examples');
                r.examples.forEach(q => {
                    if (tabAllowed('chat')) {
                        /* Try it: a conversation with the skill applied and
                           the question in the box, ready to send or change. */
                        const b = el('button', 'chip'); b.type = 'button'; b.append(ico(I.chat), document.createTextNode(q));
                        b.title = 'Ask this in chat with the skill applied';
                        b.onclick = async () => {
                            /* Never over a question already half typed. */
                            const had = $('input').value.trim();
                            if (had && had !== q && !await uiConfirm('Replace the question already in the chat box with "' + q + '"?', { title: 'Try this question', okText: 'Replace it' })) return;
                            useSkillInChat(s.id); $('input').value = q; $('input').dispatchEvent(new Event('input')); $('input').focus();
                        };
                        dd.append(b);
                    } else dd.append(el('span', 'sk-example', q));
                });
                dl.append(el('dt', null, 'Where it would use it'), dd);
            }
            if (qn) {
                const ul = el('ul', 'sk-questions'); r.questions.forEach(x => ul.append(el('li', null, x)));
                const dd = el('dd'); dd.append(ul);
                dl.append(el('dt', null, 'To check'), dd);
            }
            body.append(dl);
            const foot = el('div', 'sk-reading-foot');
            foot.append(el('span', 'sk-meta', 'Read ' + fmtDate(r.at) + (r.by ? ' for ' + r.by : '')
                + (r.stale ? '. The skill has changed since, so read it again before relying on this.' : '.')));
            const again = el('button', 'btn btn-sm'); again.type = 'button';
            again.append(ico(I.rotate), document.createTextNode('Read again'));
            again.title = 'An AI run: Reactor reads the skill as it is now.';
            again.onclick = () => readSkill(s.id, again);
            if (canEditInstructions()) foot.append(again);
            body.append(foot);
            d.append(body);
            return d;
        }
        function downloadSkill(s) {
            /* YAML single quotes, a quote inside doubled, so the same title
               comes back when the file is uploaded again. */
            const q = (v) => "'" + String(v || '').replace(/\n/g, ' ').replace(/'/g, "''") + "'";
            const text = '---\ntitle: ' + q(s.title) + (s.when ? '\ndescription: ' + q(s.when) : '') + '\n---\n\n# ' + s.title + '\n\n' + (s.content || '') + '\n';
            const a = document.createElement('a');
            a.href = URL.createObjectURL(new Blob([text], { type: 'text/markdown;charset=utf-8' }));
            a.download = (String(s.title || 'skill').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'skill') + '.md';
            document.body.append(a); a.click(); a.remove();
            setTimeout(() => URL.revokeObjectURL(a.href), 2000);
        }
        /* A skill in two columns (12 Oct 2026, WS-30): on the left its title,
           when it applies and the body at its measure; on the right its
           actions, how it is used, when it was edited, and how Reactor reads
           it. The title sat alone at the left with its buttons alone at the
           right edge and Have Reactor read it alone at the foot. */
        function skillItem(li, s) {
            const main = el('div', 'sk-main'), side = el('div', 'sk-side');
            const head = el('div', 'sk-head');
            const t = el('h4', 'sk-title', s.title || 'Untitled skill');
            head.append(t);
            if (s.always) head.append(el('span', 'lbl-chip note sk-always', 'Every answer'));
            main.append(head);
            const acts = el('div', 'sk-acts');
            const use = el('button', 'btn btn-sm'); use.type = 'button';
            use.append(ico(I.chat), document.createTextNode('Use in chat'));
            use.title = 'Ask a question with this skill applied';
            use.onclick = () => useSkillInChat(s.id);
            use.hidden = !tabAllowed('chat');
            const dl = el('button', 'mem-btn'); dl.type = 'button'; dl.append(ico(I.download)); dl.title = 'Download as Markdown';
            dl.setAttribute('aria-label', 'Download ' + (s.title || 'skill') + ' as Markdown');
            dl.onclick = () => downloadSkill(s);
            const edit = el('button', 'mem-btn'); edit.type = 'button'; edit.innerHTML = I.edit; edit.title = 'Edit';
            edit.setAttribute('aria-label', 'Edit ' + (s.title || 'skill'));
            edit.onclick = () => { if (!skillGuard()) return; skView.editId = s.id; skView.adding = false; paintSkills(); };
            const del = el('button', 'mem-btn del'); del.type = 'button'; del.innerHTML = I.trash; del.title = 'Delete';
            del.setAttribute('aria-label', 'Delete ' + (s.title || 'skill'));
            del.onclick = async () => {
                if (!await uiConfirm('Delete the skill "' + (s.title || '') + '"? Reactor stops following it straight away, and it cannot be brought back.',
                    { title: 'Delete skill', okText: 'Delete' })) return;
                setBusy(del, true);
                let gone = false;
                try { await skillOp({ op: 'delete', id: s.id }); gone = true; toastOk('Skill deleted.'); }
                catch (e) { toastError('The skill was not deleted. ' + (e.message || '')); }
                setBusy(del, false);
                if (!gone) return;
                if (!skillsDirty()) {
                    paintSkills();
                    const next = skHost.card.querySelector('.sk-item .sk-title') || skHost.card.querySelector('.card-act .btn');
                    if (next) { next.tabIndex = -1; next.focus(); }
                    return;
                }
                /* Another skill is being written: the row goes and the count
                   changes in place, and the editor is left alone. */
                li.remove();
                const n = skHost.card.querySelector('.card-title .card-n'); if (n) n.textContent = String(skills.length);
            };
            acts.append(use, dl);
            if (canEditInstructions()) acts.append(edit, del);
            side.append(acts);
            const when = s.when || (s.reading && s.reading.when) || '';
            /* Said whose words they are: Reactor's reading fills it until
               the merchant writes one. */
            if (when) main.append(el('p', 'sk-when', (s.when_from === 'reading' || !s.when ? 'When it applies, as Reactor read it: ' : 'When it applies: ') + when));
            /* The skill as the document it is: headings, lists, tables and
               emphasis, not the marks that make them. */
            const body = el('div', 'sk-body md');
            body.append(mdNodes(s.content || ''));
            /* A body that opens with its own title ('# Quoting custom gobos')
               does not say it a second time under the title. */
            const first = body.firstElementChild;
            if (first && first.classList.contains('md-h') && first.textContent.trim().toLowerCase() === String(s.title || '').trim().toLowerCase()) first.remove();
            body.id = 'skb-' + s.id;
            const long = (s.content || '').length > 320 || (s.content || '').split('\n').length > 6;
            const open = skView.open.has(s.id);
            if (long && !open) body.classList.add('clamped');
            main.append(body);
            if (long) {
                const more = el('button', 'sk-more'); more.type = 'button';
                more.textContent = open ? 'Show less' : 'Show all ' + nf((s.content || '').length) + ' characters';
                more.setAttribute('aria-expanded', String(open)); more.setAttribute('aria-controls', body.id);
                more.onclick = () => {
                    const now = !skView.open.has(s.id);
                    if (now) skView.open.add(s.id); else skView.open.delete(s.id);
                    body.classList.toggle('clamped', !now);
                    more.textContent = now ? 'Show less' : 'Show all ' + nf((s.content || '').length) + ' characters';
                    more.setAttribute('aria-expanded', String(now));
                };
                main.append(more);
            }
            /* How it is used, then when it was edited and where it came from,
               a line each. */
            side.append(el('span', 'sk-meta', skillUse(s)));
            const stamp = s.updated || s.created;
            const made = [];
            if (stamp) made.push((s.updated && s.updated !== s.created ? 'Edited ' : 'Added ') + fmtDate(stamp));
            if (s.file) made.push('from ' + s.file);
            if (made.length) side.append(el('span', 'sk-meta', made.join(' \u00b7 ')));
            if (!s.reading && canEditInstructions()) {
                const rd = el('button', 'btn btn-sm sk-read'); rd.type = 'button';
                rd.append(ico(I.book), document.createTextNode('Have Reactor read it'));
                rd.title = 'An AI run: Reactor reads the skill closely and writes down when it applies and what it will do.';
                if (skView.reading[s.id]) setBusy(rd, true);
                rd.onclick = () => readSkill(s.id, rd);
                side.append(rd);
            }
            if (s.reading) side.append(readingPanel(s));
            li.append(main, side);
        }
        function autoGrow(ta) {
            const fit = () => { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight + 2, Math.round(window.innerHeight * 0.7)) + 'px'; };
            ta.addEventListener('input', fit);
            requestAnimationFrame(fit);
            return ta;
        }
        function skillEditor(s) {
            const f = el('div', 'sk-editor');
            f.append(el('h4', 'sk-form-title', s ? 'Edit skill' : 'New skill'));
            const f1 = el('label', 'sk-field'); f1.append(el('span', null, 'Title'));
            const ti = el('input', 'sk-input'); ti.maxLength = skillCaps.title;
            ti.placeholder = 'e.g. Trade enquiry replies';
            ti.value = s ? (s.title || '') : ''; ti.dataset.initial = ti.value;
            const tMsg = el('div', 'field-msg'); tMsg.id = 'sk-tmsg-' + (s ? s.id : 'new'); tMsg.hidden = true;
            ti.setAttribute('aria-describedby', tMsg.id);
            f1.append(ti, tMsg); f.append(f1);
            const fw = el('label', 'sk-field'); fw.append(el('span', null, 'When it applies (optional)'));
            const wh = el('textarea', 'sk-input sk-when-input'); wh.rows = 2; wh.maxLength = skillCaps.when;
            wh.placeholder = 'e.g. Replying to a trade customer about prices or lead times. It helps Reactor pick the skill for the right question.';
            wh.value = s ? (s.when || '') : ((skView.draft && skView.draft.when) || ''); wh.dataset.initial = s ? wh.value : '';
            fw.append(wh); f.append(fw);
            /* For a short skill that belongs in every answer, such as a
               brand voice: it matched few questions by its words, and never
               reached an email draft. */
            const alw = el('label', 'sk-check');
            const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = !!(s && s.always);
            cb.dataset.initial = cb.checked ? '1' : '';
            const alwNote = el('span', 'sk-check-note');
            alw.append(cb, el('span', null, 'Apply to every answer and email draft'), alwNote);
            f.append(alw);
            const f2 = el('label', 'sk-field'); f2.append(el('span', null, 'What Reactor should do'));
            const bo = el('textarea', 'sk-textarea');
            bo.placeholder = 'The instructions, rules or reference text to follow. Markdown works: # headings, - lists, **bold**, tables.';
            bo.value = s ? (s.content || '') : ((skView.draft && skView.draft.content) || ''); bo.dataset.initial = s ? bo.value : '';
            if (!s && skView.draft && skView.draft.title) ti.value = skView.draft.title;
            const bMsg = el('div', 'field-msg'); bMsg.id = 'sk-bmsg-' + (s ? s.id : 'new'); bMsg.hidden = true;
            bo.setAttribute('aria-describedby', bMsg.id + ' sk-count-' + (s ? s.id : 'new'));
            autoGrow(bo);
            f2.append(bo, bMsg); f.append(f2);
            const row = el('div', 'sk-form-row');
            const fileBtn = el('button', 'btn btn-sm'); fileBtn.type = 'button';
            fileBtn.append(ico(I.upload), document.createTextNode('Load from file'));
            const fi = el('input'); fi.type = 'file'; fi.accept = '.md,.markdown,.txt,.text,text/markdown,text/plain'; fi.hidden = true;
            fileBtn.onclick = () => fi.click();
            const count = el('div', 'sk-count'); count.id = 'sk-count-' + (s ? s.id : 'new');
            const splitBtn = el('button', 'btn btn-sm'); splitBtn.type = 'button'; splitBtn.hidden = true;
            const say = (node, field, msg) => { node.hidden = !msg; node.textContent = msg || ''; markInvalid(field, !!msg); };
            /* Anyone may edit a long skill the master saved, but not make it longer. */
            const lim = Math.max(skillCaps.body, s ? String(s.content || '').trim().length : 0);
            const check = () => {
                const n = bo.value.trim().length, over = n - lim;
                count.textContent = nf(n) + ' of ' + nf(lim) + ' characters';
                count.classList.toggle('over', over > 0);
                const alwCap = skillCaps.always || 4000, tooLong = n > alwCap;
                cb.disabled = tooLong && !cb.checked;
                alwNote.textContent = tooLong ? (cb.checked ? ' Shorten it to ' + nf(alwCap) + ' characters, or turn this off, to save it.' : ' Only for a skill of up to ' + nf(alwCap) + ' characters.')
                    : ' For a short skill such as a brand voice.';
                alwNote.classList.toggle('over', tooLong && cb.checked);
                const pieces = over > 0 ? splitSkill(bo.value.trim(), lim).length : 0;
                say(bMsg, bo, over <= 0 ? ''
                    : lim > skillCaps.body ? 'You can change this skill but not make it longer than it is: remove ' + nf(over) + ' characters. Only the master account can.'
                    : 'This is ' + nf(over) + ' characters over the limit for one skill. Shorten it, or split it into ' + pieces + ' skills.');
                splitBtn.hidden = !(over > 0) || !!s || pieces < 2;
                splitBtn.textContent = 'Split into ' + pieces + ' skills';
                const t = ti.value.trim().toLowerCase();
                const clash = t && skills.find(x => (!s || x.id !== s.id) && String(x.title || '').trim().toLowerCase() === t);
                say(tMsg, ti, clash ? 'You already have a skill called "' + clash.title + '". Give this one a different title.'
                    : (ti.value.length >= skillCaps.title - 20 ? nf(ti.value.length) + ' of ' + nf(skillCaps.title) + ' characters.' : ''));
                if (!clash) markInvalid(ti, false);
                return !clash && over <= 0 && !(cb.checked && n > (skillCaps.always || 4000));
            };
            bo.addEventListener('input', check); ti.addEventListener('input', check); cb.addEventListener('change', check);
            ti.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); wh.focus(); } });
            fi.onchange = async () => {
                const file = fi.files && fi.files[0]; fi.value = ''; if (!file) return;
                if (file.size > SKILL_FILE_MAX) { toastError('That file is too large. Keep it under 5 MB.'); return; }
                if (bo.value.trim() && !await uiConfirm('Replace what is in the box with ' + file.name + '?', { title: 'Load from file', okText: 'Replace' })) return;
                try {
                    /* A Markdown header fills the title and when it applies. */
                    const rd = await readTextFile(file);
                    if (rd.note) toastError(rd.note);
                    const p = parseSkillMd(rd.text, file.name);
                    bo.value = p.content;
                    if (!ti.value) ti.value = p.title;
                    if (!wh.value && p.when) wh.value = p.when;
                    bo.dispatchEvent(new Event('input'));
                } catch (e) { toastError('That file could not be read.'); }
            };
            const cancel = el('button', 'btn btn-sm'); cancel.type = 'button'; cancel.textContent = 'Cancel';
            cancel.onclick = async () => {
                const dirty = ti.value !== ti.dataset.initial || bo.value !== bo.dataset.initial || wh.value !== wh.dataset.initial || (cb.checked ? '1' : '') !== cb.dataset.initial;
                if (dirty && !await uiConfirm('Discard this skill? What you have written is not saved.', { title: 'Discard changes', okText: 'Discard' })) return;
                ti.dataset.initial = ti.value; bo.dataset.initial = bo.value; wh.dataset.initial = wh.value;
                skView.editId = null; skView.adding = false; skView.draft = null; paintSkills();
            };
            const save = el('button', 'btn btn-sm btn-primary'); save.type = 'button'; save.textContent = s ? 'Save changes' : 'Add skill';
            const done = (msg) => {
                const name = ti.value.trim();
                ti.dataset.initial = ti.value; bo.dataset.initial = bo.value; wh.dataset.initial = wh.value;
                skView.editId = null; skView.adding = false; skView.draft = null; paintSkills(); toastOk(msg);
                /* Focus lands on the skill just saved, found by its id, not on the page. */
                const low = name.toLowerCase();
                const hit = s || skills.find(x => { const t = String(x.title || '').toLowerCase(); return t === low || t.indexOf(low + ':') === 0 || t.indexOf(low + ' (1 of') === 0; });
                const li = hit && skHost.card.querySelector('.sk-item[data-id="' + hit.id + '"]');
                const h = (li && li.querySelector('.sk-title')) || skHost.card.querySelector('.sk-title');
                if (h) { h.tabIndex = -1; h.focus(); }
            };
            save.onclick = async () => {
                const title = ti.value.trim(), content = bo.value.trim();
                say(tMsg, ti, title ? '' : 'Give the skill a title.');
                if (!content) say(bMsg, bo, 'Write what Reactor should do.');
                if (!title || !content) { (title ? bo : ti).focus(); return; }
                if (!check()) { (tMsg.hidden ? bo : ti).focus(); return; }
                setBusy(save, true);
                try {
                    const changed = s && s.reading && content !== (s.content || '').trim();
                    await skillOp(s ? { op: 'update', id: s.id, title: title, content: content, when: wh.value.trim(), always: cb.checked }
                                    : { op: 'add', title: title, content: content, when: wh.value.trim(), always: cb.checked });
                    done(s ? (changed ? 'Skill saved. What Reactor read of it is now out of date: read it again from the skill.'
                                      : 'Skill saved. Reactor follows the new version from the next answer.')
                           : 'Skill added. Reactor follows it from the next answer where it fits.');
                } catch (e) {
                    setBusy(save, false);
                    const m = e.message || 'The skill was not saved.';
                    if (/title/i.test(m)) { say(tMsg, ti, m); ti.focus(); } else { say(bMsg, bo, m); }
                }
            };
            splitBtn.onclick = async () => {
                /* Only for a new skill too long for one: pressed on anything
                   else it made a duplicate, or 'Saved as 0 skills'. */
                if (s || splitSkill(bo.value.trim(), skillCaps.body).length < 2) return;
                const title = ti.value.trim();
                if (!title) { say(tMsg, ti, 'Give the skill a title first; each part is named after it.'); ti.focus(); return; }
                const parts = splitSkill(bo.value.trim(), skillCaps.body);
                const titles = splitTitles(title, parts);
                if (!await uiConfirm('Save this as ' + parts.length + ' skills, ' + splitHow(bo.value) + ': ' + titles.map(x => '"' + x + '"').join(', ') + '?',
                    { title: 'Split into skills', okText: 'Save ' + parts.length + ' skills' })) return;
                setBusy(splitBtn, true); setBusy(save, true);
                let made = 0;
                try {
                    for (let i = 0; i < parts.length; i++) {
                        await skillOp({ op: 'add', title: titles[i], content: parts[i], when: wh.value.trim() });
                        made += 1;
                    }
                    done('Saved as ' + parts.length + ' skills.');
                } catch (e) {
                    setBusy(splitBtn, false); setBusy(save, false);
                    say(bMsg, bo, (made ? made + ' of ' + parts.length + ' parts were saved before this one failed. ' : 'Nothing was saved. ') + (e.message || ''));
                }
            };
            if (skillCaps.upload) row.append(fileBtn, fi);
            row.append(count, splitBtn, cancel, save);
            f.append(row);
            check();
            requestAnimationFrame(() => (s ? bo : ti).focus());
            return f;
        }
        /* From a note the Memory page refused as an instruction: the text is
           carried to a new skill, where instructions belong. */
        function openSkillDraft(text) {
            skView.adding = true; skView.editId = null; skView.draft = { title: '', content: String(text || '') };
            setView('skills');
        }

