        /* ---------- memory ---------- */
        let memories = [];
        let memoryLoadErr = '';   // a failed read is not an empty list
        let knowledge = {};
        let knowledgeErr = '';    // nor is a failed knowledge read 'not learned'
        let knowledgeRead = false;
        let learning = false;
        let impact = [];
        let impactErr = '';
        /* An empty list and a failed load look identical once the error is
           swallowed, and the empty state's copy actively lies about it: it says
           nothing has been saved yet when the server never answered. Every tab
           that caches into a module-level array needs this. */
        function loadFailure(msg, retry) {
            const box = el('div', 'msg error load-failed');
            box.append(el('div', null, msg));
            /* The small button, as every Try again and header action is. */
            const b = textButton(null, { small: true }); b.textContent = 'Try again';
            b.onclick = retry; box.append(b);
            return box;
        }
        /* A report that failed to load or refresh. With a good copy already
           on hand the page keeps it and says the refresh failed; with nothing
           to show it gives the reason and a Try again under the page's own
           heading. It used to throw the report away for a red strip with no
           retry and no Refresh left to press. */
        function reportFailed(box, hero, msg, keep, retry) {
            if (keep) { keep(); toastError(msg); return; }
            box.innerHTML = ''; box.append(hero);
            box.append(loadFailure(msg, retry));
        }
        /* Chrome removed alert()/confirm()/prompt() inside cross-origin iframes, and
           this app ALWAYS runs in one (embedded in the Shopify admin). Every message
           and every confirmation therefore has to be drawn in the page itself. */
        function addToast(msg, kind, opts) {
            opts = opts || {};
            const text = String(msg == null ? '' : msg).trim();
            if (!text) return;
            let host = document.getElementById('toast-host');
            if (!host) {
                host = el('div'); host.id = 'toast-host';
                /* Every async outcome lands here and none of it was announced:
                   a live region, polite so it queues rather than interrupts. */
                host.setAttribute('role', 'status'); host.setAttribute('aria-live', 'polite');
                document.body.append(host);
            }
            const t = el('div', 'toast' + (kind ? ' ' + kind : ''));
            t.append(el('div', 'toast-msg', text));
            if (opts.action) {
                const b = textButton(null, { small: true }); b.type = 'button'; b.textContent = opts.action.label;
                b.onclick = () => { t.remove(); opts.action.fn(); };
                t.append(b);
            }
            const x = iconButton(I.x, 'Dismiss', { size: 'small' });
            x.onclick = () => t.remove();
            t.append(x);
            host.append(t);
            if (opts.sticky) return;         // stays until someone acts on it
            // Problems stay up long enough to be read and acted on.
            const life = kind === 'bad' ? 14000 : 7000;
            setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 320); }, life);
        }
        function toastError(msg) { addToast(msg, 'bad'); }
        function toastOk(msg) { addToast(msg, 'good'); }

        /* In-page replacement for window.confirm(). Returns a promise. */
        /* Words that mean the answer cannot be taken back. A dialog that destroys
           something must not look like one that saves something, and must not be
           answerable by the Enter reflex. */
        const DESTRUCTIVE = /\b(delete|remove|erase|wipe|discard|purge|reset|revoke|cancel shipment|for good|cannot be undone)\b/i;
        function uiConfirm(message, opts) {
            opts = opts || {};
            const danger = opts.danger != null ? !!opts.danger
                : DESTRUCTIVE.test([opts.okText, opts.title, message].filter(Boolean).join(' '));
            return new Promise(resolve => {
                /* A question answered by its own buttons: no X, and Escape is
                   No (dialog() hands Escape to the question on top alone). */
                let answer = false;
                const win = dialog({ title: opts.title || 'Please confirm',
                    size: 'confirm-modal' + (danger ? ' confirm-danger' : ''), overlayClass: 'confirm-overlay', x: false,
                    onEscape: () => done(false),
                    onClose: () => { document.removeEventListener('keydown', key); resolve(answer); } });
                const body = win.body;
                /* A message may be a built panel rather than a sentence. el()
                   sets textContent, so handing it a node printed the string
                   "[object HTMLDivElement]" into the dialog - which is what the
                   Collections panel showed. */
                if (message instanceof Node) body.append(message);
                else body.append(el('p', 'confirm-msg', message));
                const foot = win.foot();
                const no = textButton(); no.textContent = opts.cancelText || 'Cancel';
                const yes = textButton(null, { kind: danger ? 'danger' : 'primary' });
                yes.textContent = opts.okText || 'Confirm';
                /* A panel that only tells you something has one way out, not a
                   choice between two buttons that do the same thing. */
                if (opts.hideCancel) foot.append(yes); else foot.append(no, yes);
                const done = (v) => { answer = v; win.close(); };
                function key(e) {
                    /* Only the window on top answers: two stacked questions
                       each listen on the document. */
                    if (!win.isTop()) return;
                    // Enter is a reflex, so it answers only the reversible dialogs.
                    // A destructive one has to be clicked or tabbed to. And it is
                    // the focused button's answer: with Cancel focused, Enter is
                    // Cancel (it said yes, and booked and charged a courier), and a
                    // held key's repeats are not further presses.
                    if (e.key === 'Enter' && !danger) {
                        e.preventDefault();
                        if (e.repeat) return;
                        done(document.activeElement !== no);
                    }
                }
                no.onclick = () => done(false);
                yes.onclick = () => done(true);
                // A backdrop misclick must not silently answer Cancel; the buttons
                // (or Escape/Enter, which are deliberate) are the only answers.
                document.addEventListener('keydown', key);
                (danger ? no : yes).focus();
            });
        }
        /* A toast with one thing to do about it: Undo a follow-up closed in
           chat, Save a refused note as a skill. It stays longer, since it
           asks for a decision. */
        function actionToast(msg, label, fn) {
            addToast(msg);
            const host = document.getElementById('toast-host');
            const t = host && host.lastElementChild; if (!t) return;
            const b = textButton(null, { small: true }); b.type = 'button'; b.textContent = label;
            b.onclick = () => { t.remove(); fn(); };
            t.insertBefore(b, t.querySelector('.icon-btn'));
        }
        async function loadMemory(only) {
            /* Each part draws as soon as its own answer lands. Awaited one after
               another, the page was blank until a fresh Shopify snapshot for
               tracked changes had finished; and after a chat answer only the
               notes can have changed, so only they are read again. */
            const notes = api('/api/memory', {}).then(d => {
                memoryLoadErr = '';
                if (d && Array.isArray(d.memories)) memories = d.memories;
                if (d && d.inject) memInject = d.inject;
            }).catch(e => { memoryLoadErr = e.message || 'Could not read your notes.'; })
              .then(() => paintMem('notes'));
            if (only === 'notes') return notes;
            const know = api('/api/learn', {}).then(k => { knowledgeErr = ''; knowledge = (k && k.knowledge) || {}; })
                .catch(e => { knowledgeErr = e.message || 'Could not check what Reactor has learned.'; })
                .then(() => { knowledgeRead = true; paintMem('knowledge'); });
            const imp = api('/api/impact', {}).then(im => { impactErr = ''; if (im && Array.isArray(im.impact)) impact = im.impact; })
                .catch(e => { impactErr = e.message || ''; })
                .then(() => paintMem('impact'));
            return Promise.all([notes, know, imp]);
        }
        /* The parts of the Memory page draw into their own hosts, so a tick,
           a delete or an answer landing redraws that part alone: the whole
           page used to be rebuilt, every card faded in again, and a note
           being edited was thrown away. */
        const memHost = {};
        function paintMem(part) {
            if (!$('view-memory').classList.contains('active') || !memHost.notes || !memHost.notes.isConnected) {
                if ($('view-memory').classList.contains('active')) renderMemory();
                return;
            }
            if (part === 'knowledge') { memHost.knowledge.replaceChildren(...knowledgeParts()); }
            else if (part === 'impact') { paintImpact(); }
            else { paintNotes(); }
        }
        /* Conclude and delete both come through here, so a discarded error was
           a delete that appeared to work and did not. */
        async function impactOp(payload, btn) {
            if (btn) setBusy(btn, true);
            try {
                const d = await api('/api/impact', payload);
                if (d && Array.isArray(d.impact)) impact = d.impact;
                if (payload.op === 'conclude') {
                    toastOk(d && d.held ? 'Concluded. What it came to waits in your notes for an admin to keep it.'
                        : 'Concluded. What it came to is saved as a learning in your notes.');
                    loadMemory('notes');
                }
            } catch (e) { toastError('That change was not saved. ' + (e.message || '')); }
            if (btn) setBusy(btn, false);
            paintImpact();
        }
        function paintImpact() {
            const host = memHost.impact; if (!host) return;
            host.replaceChildren();
            host.hidden = !impact.length && !impactErr;
            if (host.hidden) return;
            const head = el('div', 'card-head');
            const tt = el('h3', 'card-title', 'Tracked changes');
            head.append(titleInfo(tt, infoButton('About tracked changes', { title: 'Tracked changes', body: 'Actions you pressed Track on in an answer, measured by your headline figures from that day. Each shows the change in those figures since it was tracked.' })));
            host.append(head);
            if (impactErr) { host.append(loadFailure('Your tracked changes could not be measured just now. ' + impactErr, () => loadMemory())); return; }
            const list = el('ul', 'impact-list');
            impact.forEach(it => list.append(impactRow(it)));
            host.append(list);
        }
        /* A tracked change (12 Oct 2026, WS-20): its title, when it was
           tracked and by whom, its figures, then its actions straight under
           them, one block of three across. The actions sat at the row's far
           end, 800px from the figures. */
        function impactRow(it) {
            const row = el('li', 'impact-row' + (it.status === 'concluded' ? ' done' : ''));
            row.append(el('div', 'impact-text', it.text || ''));
            /* Measured to the day it was concluded (the server keeps those
               figures), and said so: 'since then' read as counting from the
               conclusion. */
            const from = fmtDate(it.started_at);
            const who = it.by ? ' \u00b7 Tracked by ' + it.by : '';
            row.append(el('div', 'impact-sub', it.status === 'concluded'
                ? 'Measured from ' + from + ' to ' + fmtDate(it.concluded_at) + who
                : 'Tracking since ' + from + who));
            const chips = el('div', 'impact-deltas');
            (it.deltas || []).forEach(d => {
                const cls = d.pct == null ? 'flat' : d.pct > 0 ? 'up' : d.pct < 0 ? 'down' : 'flat';
                const chip = el('div', 'idelta ' + cls);
                chip.append(el('span', 'il', d.label), el('span', 'iv', d.pct == null ? 'n/a' : ((d.pct > 0 ? '+' : '') + d.pct + '%')));
                chips.append(chip);
            });
            if (!(it.deltas || []).length) {
                chips.append(el('div', 'impact-sub', (it.baseline && Object.keys(it.baseline).length > 1)
                    ? 'No figures to compare yet. Check back in a few days.'
                    : 'No starting figures were captured when this was tracked, so it cannot be measured.'));
            }
            row.append(chips);
            const acts = el('div', 'impact-acts');
            /* Yours to settle, or an admin's: the server says the same. */
            const mayAct = canEditInstructions() || (!!it.by_uid && !!teamMe && it.by_uid === String(teamMe.id || ''));
            if (it.status === 'concluded') acts.append(el('span', 'lbl-chip note', 'Concluded'));
            else if (mayAct) {
                const cc = textButton(null, { small: true }); cc.append(ico(I.check), document.createTextNode('Conclude'));
                cc.title = 'Stop measuring and keep what it came to as a learning';
                cc.onclick = () => impactOp({ op: 'conclude', id: it.id }, cc);
                acts.append(cc);
            }
            if (mayAct) {
                const del = iconButton(I.trash, 'Delete tracked change: ' + (it.text || '').slice(0, 60), { size: 'small', tone: 'danger', title: 'Delete' });
                del.onclick = async () => {
                    if (!await uiConfirm('Delete the tracked change "' + (it.text || '').slice(0, 80) + '"? Its figures go with it.',
                        { title: 'Delete tracked change', okText: 'Delete' })) return;
                    impactOp({ op: 'delete', id: it.id });
                };
                acts.append(del);
            }
            row.append(acts);
            return row;
        }
        /* quiet: the caller says what went wrong itself, so the failure is
           thrown to it; otherwise it is said here and null comes back. */
        async function memOp(payload, quiet) {
            try {
                const d = await api('/api/memory', payload);
                if (d && Array.isArray(d.memories)) memories = d.memories;
                paintNotes();
                if ($('view-overview').classList.contains('active') && overviewCache) renderOverview(overviewCache);
                return d || {};
            } catch (e) {
                if (quiet) throw e;
                toastError('That change was not saved. ' + (e.message || ''));
                return null;
            }
        }
        async function learnStore(btn) {
            if (learning) return;
            learning = true; paintMem('knowledge');
            try {
                const d = await api('/api/learn/run', {});
                knowledge = (d && d.knowledge) || {}; knowledgeErr = '';
                toastOk('Reactor has read your website. What it learned is under Store knowledge.');
            } catch (e) {
                toastError('Reactor could not learn the store this time. ' + (e.message || ''));
            } finally { learning = false; paintMem('knowledge'); }
        }
        async function deleteKnowledge() {
            if (!await uiConfirm('Delete what Reactor has learned about your store? It stops being used in answers straight away, and learning it again is an AI run.', { title: 'Delete store knowledge', okText: 'Delete' })) return;
            try { const d = await api('/api/learn', { op: 'delete' }); knowledge = (d && d.knowledge) || {}; }
            catch (e) { toastError('The store knowledge was not deleted. ' + (e.message || '')); }
            paintMem('knowledge');
        }
        /* The learned profile is written in short headed sections, and came
           out with its '## ' and '**' showing. Headings become headings and
           the emphasis marks go; the rest is paragraphs and bullets. */
        function knowNodes(text) { return mdNodes(text); }
        /* Store knowledge as a card of the house kind. Its read failing is not
           'unlearned': that state offered a paid re-learn over knowledge that
           was there all along. */
        let knowEditing = false;
        function knowledgeParts() {
            const out = [];
            const head = el('div', 'card-head');
            head.append(el('h3', 'card-title', 'Store knowledge'));
            const learned = !!(knowledge && knowledge.knowledge);
            let desc;
            if (learning) desc = 'Reading your homepage, pages and blog. This can take up to a minute.';
            else if (!knowledgeRead) desc = 'Checking what Reactor has learned\u2026';
            else if (knowledgeErr) desc = 'What Reactor has learned could not be checked just now. ' + knowledgeErr;
            else if (learned) {
                const n = (knowledge.sources || []).length;
                desc = 'Learned' + (knowledge.learned_at ? ' ' + fmtDate(knowledge.learned_at) : '')
                    + (n ? ' from ' + n + ' page' + (n > 1 ? 's' : '') : '')
                    + (knowledge.edited_at ? ', corrected' + (knowledge.edited_by ? ' by ' + knowledge.edited_by : '') + ' on ' + fmtDate(knowledge.edited_at) : '')
                    + '.';
            } else desc = '';
            /* What learning the store is, word for word, behind the title's
               info button (copy plan, Memory #2). */
            const kt = head.querySelector('.card-title');
            if (kt) titleInfo(kt, infoButton('About store knowledge', { title: 'Store knowledge',
                body: 'Reactor can read your homepage, pages and blog and keep what it learns about the business. It reads it with every answer until you delete it.' }));
            if (!canEditInstructions()) desc += (desc ? ' ' : '') + 'Only an admin can change it.';
            if (desc) head.append(el('p', 'card-desc', desc));
            const acts = el('div', 'card-act');
            if (learning) {
                const b = textButton(null, { small: true }); b.textContent = 'Learning'; setBusy(b, true); acts.append(b);
            } else if (knowledgeErr) {
                const b = textButton(null, { small: true }); b.append(ico(I.rotate), document.createTextNode('Try again')); b.onclick = () => loadMemory(); acts.append(b);
            } else if (learned && !knowEditing && canEditInstructions()) {
                const ed = textButton(null, { small: true }); ed.append(ico(I.edit), document.createTextNode('Correct'));
                ed.title = 'Fix a detail it got wrong'; ed.onclick = () => { knowEditing = true; paintMem('knowledge'); };
                const re = textButton(null, { small: true }); re.append(ico(I.rotate), document.createTextNode('Learn again'));
                re.title = 'Read the website again. An AI run.';
                re.onclick = async () => {
                    if (!await uiConfirm('Read your website again? This is an AI run, and what it learns replaces what is here, including any corrections.', { title: 'Learn the store again', okText: 'Learn again' })) return;
                    learnStore();
                };
                const del = textButton(null, { small: true }); del.append(ico(I.trash), document.createTextNode('Delete')); del.onclick = deleteKnowledge;
                acts.append(ed, re, del);
            }
            head.append(acts); out.push(head);
            /* On a fresh store, Learn my store follows the line that says what
               it costs (12 Oct 2026, WS-23): it sat at the head's far end. */
            if (!learned && !learning && !knowledgeErr && knowledgeRead) {
                const fresh = el('div', 'act-row know-fresh');
                let learnBtn = null;
                if (canEditInstructions()) {
                    learnBtn = textButton(null, { small: true }); learnBtn.append(ico(I.book), document.createTextNode('Learn my store'));
                    learnBtn.title = 'Reads up to 12 pages of your website. An AI run.'; learnBtn.onclick = () => learnStore(learnBtn);
                }
                fresh.append(el('p', 'card-sub', 'Uses AI credits. Reads up to 12 pages, once.'), learnBtn || '');
                out.push(fresh);
            }
            if (learned && knowEditing) {
                const f = el('div', 'know-edit');
                const ta = el('textarea', 'sk-textarea'); ta.value = knowledge.knowledge || ''; ta.dataset.initial = ta.value;
                ta.setAttribute('aria-label', 'Store knowledge');
                autoGrow(ta);
                /* Its limit, said: a longer correction was cut without a word. */
                const cap = Number(knowledge.cap || 8000);
                const count = el('div', 'sk-count'); count.id = 'know-count';
                const kMsg = el('div', 'field-msg'); kMsg.hidden = true; kMsg.id = 'know-msg';
                ta.setAttribute('aria-describedby', 'know-count know-msg');
                const kCheck = () => {
                    const n = ta.value.trim().length, over = n - cap;
                    count.textContent = nf(n) + ' of ' + nf(cap) + ' characters'; count.classList.toggle('over', over > 0);
                    kMsg.hidden = over <= 0; kMsg.textContent = over > 0 ? 'This is ' + nf(over) + ' characters over the limit. Shorten it before saving.' : '';
                    markInvalid(ta, over > 0);
                    return over <= 0;
                };
                ta.addEventListener('input', kCheck); kCheck();
                const row = el('div', 'act-row');
                const cancel = textButton('Cancel', { small: true });
                cancel.onclick = async () => {
                    if (ta.value !== ta.dataset.initial && !await uiConfirm('Discard your corrections to the store knowledge?', { title: 'Discard changes', okText: 'Discard' })) return;
                    knowEditing = false; paintMem('knowledge');
                };
                const save = textButton('Save', { kind: 'primary', small: true });
                save.onclick = async () => {
                    if (!kCheck()) { ta.focus(); return; }
                    setBusy(save, true);
                    try {
                        const d = await api('/api/learn', { op: 'save', knowledge: ta.value });
                        knowledge = (d && d.knowledge) || knowledge; knowEditing = false; paintMem('knowledge');
                        toastOk('Saved. Reactor uses the corrected text from the next answer.');
                    } catch (e) { setBusy(save, false); toastError('Not saved. ' + (e.message || '')); }
                };
                row.append(save, cancel, count); f.append(ta, kMsg, row); out.push(f);
                requestAnimationFrame(() => ta.focus());
            } else if (learned && !learning) {
                /* What it learned, shown whole as a preview (12 Oct 2026, WS-21):
                   a block for each of its headings, three across, and the pages
                   it read as the last block. It sat behind a lone link. */
                const grid = el('div', 'know-grid');
                let sec = null;
                [...knowNodes(knowledge.knowledge).childNodes].forEach(n => {
                    if (!sec || (n.classList && n.classList.contains('md-h'))) { sec = el('div', 'know-sec know-text'); grid.append(sec); }
                    sec.append(n);
                });
                const src = (knowledge.sources || []).filter(u => /^https?:\/\//.test(u));
                if (src.length) {
                    const ps = el('div', 'know-sec');
                    ps.append(el('div', 'know-src-h', 'Pages it read'));
                    const ul = el('ul', 'know-src');
                    src.forEach(u => { const li = el('li'); const a = el('a', null, u.replace(/^https?:\/\//, '')); a.href = u; a.target = '_blank'; a.rel = 'noopener'; li.append(a); ul.append(li); });
                    ps.append(ul); grid.append(ps);
                }
                out.push(grid);
            }
            return out;
        }
        /* ---- notes: one card, the house list ----
           Four fixed groups of cards, oldest first, with no search, no dates,
           no source and no way to add or correct a note, became one list:
           newest first, filtered by kind, searchable, paged, each note saying
           where it came from and when, and whether Reactor still reads it. */
        const MEM_WORDS = { fact: 'Fact', decision: 'Decision', followup: 'Follow-up', preference: 'Preference', insight: 'Learning' };
        const MEM_FROM = { chat: 'Chat', merchant: 'Added here', 'tracked change': 'Tracked change' };
        let memInject = 40;
        const memView = { f: 'all', q: '', page: 1, size: 25, editId: null, adding: false };
        /* The newest memInject of each kind that is not dismissed: what the
           server puts in every answer (_memory_to_system). */
        function memSentIds() {
            const sent = new Set();
            const live = m => m.status !== 'dismissed' && m.status !== 'pending';
            const kinds = [['followup', m => m.type === 'followup' && m.status === 'open'],
                           ['facts', m => (m.type === 'fact' || m.type === 'decision') && live(m)],
                           ['preference', m => m.type === 'preference' && live(m)],
                           ['insight', m => m.type === 'insight' && live(m)]];
            kinds.forEach(([, f]) => memories.filter(f).slice(-memInject).forEach(m => sent.add(m.id)));
            return sent;
        }
        function memGroup(m) {
            if (m.status === 'pending') return 'pending';
            if (m.type === 'followup') return m.status === 'open' ? 'followup' : 'closed';
            return m.type;
        }
        function paintNotes() {
            const host = memHost.notes; if (!host) return;
            /* Not over a note being corrected or written. */
            const open = host.querySelector('.mem-edit textarea, .mem-add textarea');
            if (open && open.value !== (open.dataset.initial || '')) { memDeferred = true; return; }
            memDeferred = false;
            host.replaceChildren();
            const waitingN = memories.filter(m => m.status === 'pending').length;
            const head = el('div', 'card-head');
            /* What notes are and who keeps them, word for word, behind the
               title's info button (copy plan, Memory #6). */
            const nt = el('h3', 'card-title', 'Notes');
            if (memories.length) nt.append(el('span', 'card-n', String(memories.length)));
            const ntInfo = infoButton('About notes', { title: 'Notes', body: 'What Reactor keeps from chat, and what ' + (canEditInstructions() ? 'you add' : 'an admin adds') + ' here. It reads the newest ' + memInject
                    + ' of each kind with every answer. Rules for how to work belong in Skills.'
                    + (canEditInstructions()
                        ? (waitingN ? ' ' + (waitingN === 1 ? 'One note from a member waits' : waitingN + ' notes from members wait') + ' under Waiting until you keep ' + (waitingN === 1 ? 'it.' : 'them.') : '')
                        : ' Only an admin can add, correct or delete a note, and a note from your chats or tracked changes waits for an admin to keep it.') });
            head.append(titleInfo(nt, ntInfo));
            const acts = el('div', 'card-act');
            /* With no notes the empty line carries Add a note, once (WS-23). */
            if (!memoryLoadErr && canEditInstructions() && memories.length) {
                const add = textButton(null, { kind: 'primary', small: true }); add.append(ico(I.plus), document.createTextNode('Add a note'));
                add.onclick = () => { memView.adding = true; memView.editId = null; paintNotes(); };
                acts.append(add);
            }
            head.append(acts); host.append(head);
            if (memoryLoadErr) { host.append(loadFailure('Your notes could not be loaded, so they cannot be shown yet. ' + memoryLoadErr, () => loadMemory('notes'))); return; }
            if (memView.adding) host.append(memEditor(null));
            if (!memories.length) {
                if (!memView.adding) {
                    let first = null;
                    if (canEditInstructions()) {
                        first = textButton(); first.type = 'button'; first.append(ico(I.plus), document.createTextNode('Add a note'));
                        first.onclick = () => { memView.adding = true; memView.editId = null; paintNotes(); };
                    }
                    host.append(emptyState({ icon: I.bookmark, text: 'No notes yet.', action: first }));
                }
                return;
            }
            const groups = { all: memories.length, pending: 0, followup: 0, preference: 0, insight: 0, fact: 0, decision: 0, closed: 0 };
            memories.forEach(m => { groups[memGroup(m)]++; });
            const F = [['all', 'All'], ['pending', 'Waiting'], ['followup', 'Follow-ups'], ['preference', 'Preferences'], ['insight', 'Learnings'],
                ['fact', 'Facts'], ['decision', 'Decisions'], ['closed', 'Closed']].filter(([k]) => k === 'all' || groups[k]);
            if (!F.some(([k]) => k === memView.f)) memView.f = 'all';
            const search = tableSearch('Search notes…', memView.q, (v) => { memView.q = v; memView.page = 1; paintNotesList(); });
            /* A tab changes the list alone, in place, so focus stays on it. */
            let tabs = null;
            if (F.length > 2) tabs = segmented(F.map(([k, l]) => ({ key: k, label: l, n: groups[k] })), memView.f, (k) => {
                memView.f = k; memView.page = 1;
                [...tabs.children].forEach((b, i) => { const on = F[i][0] === k; b.classList.toggle('on', on); b.setAttribute('aria-pressed', String(on)); });
                paintNotesList();
            });
            host.append(tableTools([tabs], [search]));
            const list = el('div', 'mem-list'); host.append(list);
            memHost.list = list;
            paintNotesList();
        }
        let memDeferred = false;
        function paintNotesList() {
            const box = memHost.list; if (!box) return;
            box.replaceChildren();
            const q = memView.q.trim().toLowerCase();
            const sent = memSentIds();
            const rows = memories.slice().reverse()
                .filter(m => memView.f === 'all' || memGroup(m) === memView.f)
                .filter(m => !q || (m.text || '').toLowerCase().includes(q));
            if (!rows.length) { box.append(el('div', 'empty', 'No notes match.')); return; }
            const pages = Math.max(1, Math.ceil(rows.length / memView.size));
            if (memView.page > pages) memView.page = pages;
            const from = (memView.page - 1) * memView.size;
            /* The actions column has a name for a screen reader and none on screen. */
            const kt = dataTable(['Kind', 'Note', 'From', 'Added', el('span', 'sr-only', 'Actions')], { cls: 'mem-table' });
            rows.slice(from, from + memView.size).forEach(m => kt.add(memView.editId === m.id ? memEditRow(m) : memRow(m, sent)));
            box.append(kt.wrap);
            if (rows.length > 25) box.append(tablePager({ total: rows.length, page: memView.page, pageSize: memView.size, sizes: [25, 50, 100],
                noun: 'notes', onPage: (k) => { memView.page = k; paintNotesList(); },
                onSize: (k) => { memView.size = k; memView.page = 1; paintNotesList(); } }));
        }
        function memRow(m, sent) {
            const waiting = m.status === 'pending';
            const tr = el('tr', m.status === 'done' ? 'done' : null);
            const k = el('td', 'mem-kind'); k.append(el('span', 'lbl-chip note', MEM_WORDS[m.type] || cap(String(m.type || ''))));
            const t = el('td', 'mem-note');
            const tx = el('div', 'mem-text', m.text || ''); tx.id = 'mem-' + m.id; t.append(tx);
            /* Kind holds one tag (12 Oct 2026, WS-22); the states go under the note. */
            const states = el('div', 'mem-states');
            const bits = [];
            /* Two states as tags, not sentences (copy plan, Memory #10 and #11). A waiting note also says,
               visibly, who it is from (what an admin acts on) and, with the tag below, that it is not read. */
            let nStates = 0;
            if (waiting) { states.append(el('span', 'lbl-chip warn', 'Waiting for an admin')); nStates++; }
            if (waiting && m.by) bits.push('from ' + m.by);
            if (m.type === 'followup' && m.status !== 'open' && !waiting) bits.push((m.status === 'done' ? 'Done' : 'Dismissed') + ' ' + fmtDate(m.updated || m.created) + (m.closed_by === 'chat' ? ' in chat' : ''));
            if (m.edited) bits.push('corrected');
            /* A waiting note is not read (memSentIds leaves it out), so it carries the tag too; a follow-up that is
               done or dismissed is closed work and never was. */
            const closedFollowup = m.type === 'followup' && m.status !== 'open' && !waiting;
            if (!sent.has(m.id) && !closedFollowup) { states.append(el('span', 'lbl-chip note', 'Not read with answers')); nStates++; }
            if (nStates) t.append(states);
            if (m.status === 'dismissed' && m.type !== 'followup') bits.push('dismissed');
            if (bits.length) t.append(el('div', 'mem-meta', cap(bits.join(' · '))));
            const fromWord = MEM_FROM[m.source] || (m.source ? cap(m.source) : 'Added here');
            const fr = el('td', 'mem-from', fromWord);
            const at = el('td', 'mem-at', fmtDate(m.created));
            t.append(el('div', 'mem-when', fmtDate(m.created) + ' \u00b7 ' + fromWord));
            const acts = el('td', 'mem-acts-cell');
            const box = el('div', 'mem-acts');
            const label = (verb) => verb + ': ' + String(m.text || '').slice(0, 60);
            const btn = (icon, verb, cls, fn) => {
                const b = iconButton(icon, label(verb), { size: 'small', cls: cls, title: verb });
                b.onclick = fn; box.append(b); return b;
            };
            /* Only what the server allows this account (_member_may_set): a
               member ticks off, reopens or dismisses a follow-up an admin
               kept, and reopens only one ticked off, never one dismissed. */
            const admin = canEditInstructions();
            const unkept = !!m.by && !m.kept;
            if (waiting) {
                if (admin) btn(I.check, 'Keep', 'ok', () => memOp({ op: 'set_status', id: m.id, status: 'open' }));
            } else if (m.type === 'followup' && m.status === 'open') {
                if (admin || !unkept) {
                    btn(I.check, 'Mark done', 'ok', () => memOp({ op: 'set_status', id: m.id, status: 'done' }));
                    btn(I.x, 'Dismiss', '', () => memOp({ op: 'set_status', id: m.id, status: 'dismissed' }));
                }
            } else if (m.type === 'followup') {
                if (admin || (m.status === 'done' && !unkept))
                    btn(I.rotate, 'Reopen', '', () => memOp({ op: 'set_status', id: m.id, status: 'open' }));
            }
            if (canEditInstructions()) btn(I.edit, 'Correct', '', () => { if (memGuard()) { memView.editId = m.id; memView.adding = false; paintNotesList(); } });
            if (canEditInstructions()) btn(I.trash, 'Delete', 'del', async () => {
                if (!await uiConfirm('Delete the note "' + String(m.text || '').slice(0, 90) + '"? Reactor stops using it straight away.',
                    { title: 'Delete note', okText: 'Delete' })) return;
                memOp({ op: 'delete', id: m.id });
            });
            acts.append(box);
            tr.append(k, t, fr, at, acts);
            return tr;
        }
        /* One open editor at a time, and not over unsaved typing. */
        function memGuard() {
            const open = memHost.notes && memHost.notes.querySelector('.mem-edit textarea, .mem-add textarea');
            if (open && open.value !== (open.dataset.initial || '')) { toastError('Save or cancel the note you are writing first.'); open.focus(); return false; }
            return true;
        }
        function memEditRow(m) {
            const tr = el('tr', 'mem-edit-row');
            const td = el('td'); td.colSpan = 5; td.append(memEditor(m)); tr.append(td);
            return tr;
        }
        /* A note written or corrected by hand. What reads like an instruction
           is refused by the server (a note is replayed into every answer, for
           everyone), and is offered as a skill, which is where instructions
           live, rather than vanishing. */
        function memEditor(m) {
            const f = el('div', m ? 'mem-edit' : 'mem-add');
            const row = el('div', 'mem-edit-top');
            const sel = el('select', 'field-sm'); sel.setAttribute('aria-label', 'Kind of note');
            Object.keys(MEM_WORDS).forEach(k => { const o = el('option', null, MEM_WORDS[k]); o.value = k; sel.append(o); });
            sel.value = m ? m.type : 'fact';
            row.append(el('span', 'mem-edit-l', m ? 'Correct this note' : 'New note'), sel);
            const ta = el('textarea', 'sk-textarea mem-ta'); ta.rows = 2; ta.maxLength = 800;
            ta.value = m ? (m.text || '') : ''; ta.dataset.initial = ta.value;
            ta.placeholder = 'A fact about the business, a decision, a preference, or something to follow up';
            ta.setAttribute('aria-label', 'Note');
            autoGrow(ta);
            const msg = el('div', 'field-msg'); msg.hidden = true; msg.setAttribute('role', 'alert');
            const acts = el('div', 'act-row');
            const save = textButton(m ? 'Save' : 'Add note', { kind: 'primary', small: true });
            const cancel = textButton('Cancel', { small: true });
            cancel.onclick = () => { memView.editId = null; memView.adding = false; ta.dataset.initial = ta.value; paintNotes(); };
            const asSkill = textButton('Save as a skill instead', { small: true }); asSkill.hidden = true;
            asSkill.onclick = () => { ta.dataset.initial = ta.value; memView.editId = null; memView.adding = false; openSkillDraft(ta.value); };
            save.onclick = async () => {
                const text = ta.value.trim();
                if (!text) { msg.hidden = false; msg.textContent = 'Write the note first.'; markInvalid(ta, true); ta.focus(); return; }
                setBusy(save, true);
                try {
                    const d = m ? await memOp({ op: 'update', id: m.id, text: text, type: sel.value }, true)
                                : await memOp({ op: 'add', items: [{ type: sel.value, text: text }] }, true);
                    if (!m && d.not_kept && d.not_kept.length) throw Object.assign(new Error('That reads like an instruction, and notes are kept to facts about the business. Save it as a skill instead.'), { asSkill: true });
                    ta.dataset.initial = ta.value; memView.editId = null; memView.adding = false; paintNotes();
                    toastOk(m ? 'Note corrected.' : 'Note added. Reactor reads it from the next answer.');
                } catch (e) {
                    setBusy(save, false);
                    msg.hidden = false; msg.textContent = e.message || 'Not saved.';
                    markInvalid(ta, true);
                    asSkill.hidden = !(e.asSkill || /Save it as a skill/.test(e.message || ''));
                }
            };
            acts.append(save, cancel, asSkill);
            f.append(row, ta, msg, acts);
            requestAnimationFrame(() => ta.focus());
            return f;
        }
        function renderMemory() {
            const box = $('memory-content'); box.innerHTML = '';
            box.classList.toggle('no-intro', !firstPaint('memory'));
            /* Under the header every block is a card the grid can move, each
               spanning the row; the header's action slot is where Customize goes. */
            box.append(pageHead({ view: 'memory', title: 'Memory', line: 'What Reactor remembers with every answer.' }));
            memHost.knowledge = widget(el('div', 'card know'), 'knowledge', 'full', 'Store knowledge');
            memHost.impact = widget(el('div', 'card impact-card'), 'impact', 'full', 'Tracked changes');
            memHost.notes = widget(el('div', 'card mem-card-list'), 'notes', 'full', 'Notes');
            box.append(memHost.knowledge, memHost.impact, memHost.notes);
            memHost.knowledge.replaceChildren(...knowledgeParts());
            paintImpact();
            paintNotes();
        }

