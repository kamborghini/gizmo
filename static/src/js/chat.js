        /* ---------- chat rendering ---------- */
        const chatLog = $('chat-scroll');
        function scrollChat() { chatLog.scrollTop = chatLog.scrollHeight; }
        const chatNearEnd = () => chatLog.scrollHeight - chatLog.scrollTop - chatLog.clientHeight < 80;
        /* A new answer is read from its top: it landed scrolled to its end,
           with the headline above the fold. */
        function scrollToMsg(node) {
            if (!node || !node.isConnected) return;
            chatLog.scrollTop += node.getBoundingClientRect().top - chatLog.getBoundingClientRect().top - 12;
        }
        /* When an answer was given, in London time: 'Up 12% on last week'
           opened a fortnight later read as current. */
        const chatStamp = (iso) => (iso && !isNaN(Date.parse(iso))) ? fmtDate(iso) + ', ' + londonHM(iso) : '';
        function chatSay(text) { const s = $('chat-status'); if (s) { s.textContent = ''; setTimeout(() => { s.textContent = text; }, 30); } }
        function renderChat(keepScroll) {
            const log = $('chat-log');
            const c = active();
            const top = chatLog.scrollTop;
            log.innerHTML = '';
            /* The conversation is drawn again on every switch; only a message
               that has just arrived fades in. */
            log.classList.toggle('no-intro', !firstPaint('chat'));
            syncComposer();
            if (currentView() === 'chat') syncPrintBtn();
            if (!c || !c.turns.length) { renderEmptyChat(log); return; }
            log.append(chatTitle(c));
            c.turns.forEach((t, i) => log.append(turnNode(c, t, i)));
            if (pending[c.id]) log.append(thinkingNode(c));
            if (keepScroll) { chatLog.scrollTop = top; return; }
            if (pending[c.id]) { scrollChat(); return; }
            const qs = log.querySelectorAll(':scope > .msg.user');
            scrollToMsg(qs[qs.length - 1]);
        }
        /* The page is headed Chat in every state; the conversation's own name
           sits over it here, where it can be renamed. */
        function chatTitle(c) {
            const h = el('div', 'chat-title');
            const t = el('h2', 'chat-h', c.title || 'Conversation'); t.title = c.title || '';
            const ren = iconButton(I.edit, 'Rename this conversation', { size: 'small', title: 'Rename' });
            ren.onclick = () => {
                const inp = el('input', 'field-sm chat-rename'); inp.value = c.title || ''; inp.maxLength = 80;
                inp.setAttribute('aria-label', 'Conversation name');
                let finished = false;
                const done = (keep) => {
                    /* Once: the redraw blurs the field, and that blur kept an
                       Escaped name. */
                    if (finished) return; finished = true;
                    const v = inp.value.trim();
                    if (keep && v && v !== c.title) { c.title = v; c.renamed = true; save(); renderSidebar(); }
                    renderChat(true);
                    const again = document.querySelector('#chat-log .chat-title .icon-btn'); if (again) again.focus();
                };
                inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); done(true); } if (e.key === 'Escape') { e.stopPropagation(); done(false); } });
                inp.addEventListener('blur', () => done(true));
                t.replaceWith(inp); ren.remove(); inp.focus(); inp.select();
            };
            const n = c.turns.filter(x => x.role === 'user').length;
            const meta = el('div', 'chat-meta', 'Started ' + fmtDate(new Date(c.ts || Date.now()).toISOString())
                + ' · ' + n + (n === 1 ? ' question' : ' questions')
                + (c.turns.length > CHAT_KEEP ? ' · Reactor reads the latest ' + CHAT_KEEP + ' messages with each question' : ''));
            const row = el('div', 'chat-title-row'); row.append(t, ren);
            h.append(row, meta);
            return h;
        }
        function turnNode(c, t, i) {
            if (t.role === 'user') {
                const m = el('div', 'msg user');
                m.append(el('div', 'bubble', t.text));
                const names = (t.skills || []).map(s => s.title).filter(Boolean);
                if (names.length) m.append(el('div', 'msg-with', 'Applying ' + names.join(', ')));
                return m;
            }
            if (t.role === 'error') return errorTurn(c, t, i);
            return chatAnswer(c, t, i);
        }
        /* A failed or stopped question keeps its place and its reason, with
           Ask again. It used to be a bubble the next redraw threw away,
           leaving an unanswered question, and asking again sent it twice. */
        function errorTurn(c, t, i) {
            const m = el('div', 'msg error chat-err'); m.setAttribute('role', 'alert');
            m.append(el('div', null, t.stopped ? 'Stopped before an answer came back.' : 'That question was not answered. ' + (t.text || '')));
            const q = c.turns[i - 1];
            if (q && q.role === 'user' && i === c.turns.length - 1) {
                const again = el('button', 'btn btn-sm'); again.type = 'button'; again.textContent = 'Ask again';
                again.onclick = () => askAgain(c, i);
                m.append(again);
            }
            return m;
        }
        function askAgain(c, i) {
            if (pending[c.id]) { busyNote(); return; }
            const q = c.turns[i - 1];
            c.turns.splice(i - 1, 2); save();
            send(q.text, { convo: c, skills: q.skills });
        }
        /* Whether an answer was a Deep analysis. Answers saved before the
           server said so were deep when they came from an Opus 4 model; since
           every answer is Opus 5.5, its name tells nothing, and a tab left
           open on the old page saved everyday answers under it. */
        function deepTurn(t) {
            return t.deep != null ? !!t.deep : !!(t.model && /opus/i.test(t.model) && !/opus-5/i.test(t.model));
        }
        /* An answer the fallback model gave, because the chosen one failed:
           said under the answer, with the reason, never passed off as it. */
        function fellBackNote(t) {
            const f = t.fell_back;
            if (!f || !f.to) return null;
            const n = el('div', 'resp-note');
            n.append(el('span', null, f.to + ' answered this, because ' + (f.from || 'the usual model') + ' could not. ' + (f.why || '')));
            return n;
        }
        function chatAnswer(c, t, i) {
            const m = el('div', 'msg assistant');
            const head = el('div', 'resp-head');
            const av = el('span', 'av'); av.innerHTML = I.spark; av.setAttribute('aria-hidden', 'true');
            head.append(av, el('h3', 'who', 'Reactor'));
            if (deepTurn(t)) head.append(el('span', 'tag', 'Deep analysis'));
            if (t.at) head.append(el('span', 'resp-at', chatStamp(t.at)));
            const copy = iconButton(I.copy, 'Copy this answer', { size: 'small', cls: 'resp-copy' });
            copy.onclick = () => copyText(structuredToText(t.structured, 20000), 'Answer copied.');
            head.append(copy);
            m.append(head);
            renderStructured(m, t.structured || {}, { chat: { c: c, t: t } });
            const fb = fellBackNote(t); if (fb) m.append(fb);
            if (Array.isArray(t.not_kept) && t.not_kept.length) {
                const n = el('div', 'resp-note');
                n.append(el('span', null, 'Not kept as a note, because it reads as an instruction: "' + t.not_kept[0] + '"'
                    + (t.not_kept.length > 1 ? ' and ' + (t.not_kept.length - 1) + ' more' : '') + '. Instructions belong in Skills, where Reactor follows them.'));
                const b = el('button', 'btn btn-sm'); b.type = 'button'; b.textContent = 'Save as a skill';
                b.onclick = () => openSkillDraft(t.not_kept.join('\n\n'));
                if (canEditInstructions()) n.append(b);
                m.append(n);
            }
            /* A member's note is kept waiting: an admin decides whether
               Reactor reads it with everyone's answers. */
            if (Array.isArray(t.held) && t.held.length) {
                const n = el('div', 'resp-note');
                n.append(el('span', null, 'Noted for an admin to check: "' + t.held[0] + '"'
                    + (t.held.length > 1 ? ' and ' + (t.held.length - 1) + ' more' : '')
                    + '. Reactor uses it in answers once an admin keeps it in Memory.'));
                m.append(n);
            }
            if (Array.isArray(t.followups_closed) && t.followups_closed.length) {
                const n = el('div', 'resp-note');
                n.append(el('span', null, 'Marked done in Memory: ' + t.followups_closed.map(f => f.text).join('; ') + '.'));
                const b = el('button', 'btn btn-sm'); b.type = 'button'; b.textContent = 'Undo';
                b.onclick = async () => {
                    setBusy(b, true);
                    try {
                        for (const f of t.followups_closed) await memOp({ op: 'set_status', id: f.id, status: 'open' }, true);
                        t.followups_closed = []; save(); n.remove(); toastOk('Opened again.');
                    } catch (e) { setBusy(b, false); toastError('Not opened again. ' + (e.message || '')); }
                };
                n.append(b); m.append(n);
            }
            /* Follow-ups the answer thinks are done, from what it read rather
               than what you said: yours to close, not the model's. */
            if (Array.isArray(t.followups_maybe) && t.followups_maybe.length) {
                const n = el('div', 'resp-note');
                n.append(el('span', null, 'These may be done: ' + t.followups_maybe.map(f => f.text).join('; ') + '.'));
                const b = el('button', 'btn btn-sm'); b.type = 'button'; b.textContent = 'Mark done';
                b.onclick = async () => {
                    setBusy(b, true);
                    try {
                        for (const f of t.followups_maybe) await memOp({ op: 'set_status', id: f.id, status: 'done' }, true);
                        t.followups_closed = (t.followups_closed || []).concat(t.followups_maybe); t.followups_maybe = [];
                        save(); renderChat(true); toastOk('Marked done in Memory.');
                    } catch (e) { setBusy(b, false); toastError('Not marked done. ' + (e.message || '')); }
                };
                n.append(b); m.append(n);
            }
            if (Array.isArray(t.data_used) && t.data_used.length) m.append(dataDrill(t.data_used));
            /* Old figures say so, and can be asked for again; so can an
               answer that came back empty. */
            const q = c.turns[i - 1];
            const empty = !t.structured || /^Reactor did not send an answer/.test(String(t.structured.summary || '')) && !(t.structured.insights || t.structured.sections || t.structured.actions || t.structured.metrics);
            if (empty && i === c.turns.length - 1 && q && q.role === 'user') {
                const again = el('button', 'btn btn-sm resp-again'); again.type = 'button'; again.textContent = 'Ask again';
                again.onclick = () => { if (pending[c.id]) { busyNote(); return; } c.turns.splice(i - 1, 2); save(); send(q.text, { convo: c, skills: q.skills }); };
                m.append(again);
                return m;
            }
            if (t.at && Date.now() - Date.parse(t.at) > 86400000 && i === c.turns.length - 1 && q && q.role === 'user') {
                const again = el('button', 'btn btn-sm resp-again'); again.type = 'button';
                again.append(ico(I.rotate), document.createTextNode('Ask again with today’s figures'));
                again.onclick = () => send(q.text, { convo: c, skills: q.skills });
                m.append(again);
            }
            return m;
        }
        async function copyText(text, said) {
            try { await navigator.clipboard.writeText(text); toastOk(said || 'Copied.'); }
            catch (e) { toastError('The browser did not allow copying here. Select the text and copy it instead.'); }
        }
        function dataDrill(dataUsed) {
            const d = el('details', 'data-drill');
            const sum = el('summary');
            sum.append(ico(I.search), document.createTextNode('What Reactor read (' + dataUsed.length + (dataUsed.length > 1 ? ' reads' : ' read') + ')'));
            d.append(sum);
            const body = el('div', 'data-drill-body');
            dataUsed.forEach(s => {
                const item = el('div', 'data-src');
                item.append(el('div', 'data-src-label', s.label || 'Data'));
                const pre = el('div', 'data-src-pre'); pre.textContent = (s.preview || '').trim() || 'Nothing came back.';
                item.append(pre); body.append(item);
            });
            d.append(body); return d;
        }
        function renderEmptyChat(log) {
            const w = el('div', 'empty-chat');
            const big = el('div', 'big'); big.innerHTML = I.spark;
            w.append(big, el('h2', null, 'Ask Reactor'),
                el('p', null, 'Ask about products, orders, customers and stock.'));
            /* Earlier conversations first: after a reload, and on a phone, the
               list is far out of sight under the whole menu. */
            const recent = convos.filter(x => x.turns.length).slice(0, 6);
            if (recent.length) {
                const r = el('div', 'chat-recent panel');
                r.append(el('div', 'chat-recent-h', 'Recent'));
                recent.forEach(x => {
                    const b = el('button', 'chat-recent-row'); b.type = 'button';
                    b.append(ico(I.chat), el('span', 'crr-t', x.title || 'Conversation'), el('span', 'crr-at', fmtDate(new Date(x.updated || x.ts).toISOString())));
                    b.onclick = () => selectConvo(x.id);
                    r.append(b);
                });
                w.append(r);
            }
            const asked = new Set(convos.map(x => String(x.title || '').toLowerCase()));
            const starters = el('div', 'starters');
            ['Suggest 5 ways to improve my product pages', 'What changed in my orders this week?', 'Which products are low on stock?', 'Who are my best customers?']
                .filter(s => !asked.has(s.toLowerCase()))
                .forEach(s => { const b = el('button', 'chip'); b.type = 'button'; b.append(ico(I.spark), document.createTextNode(s)); b.onclick = () => send(s); starters.append(b); });
            if (starters.children.length) w.append(starters);
            log.append(w);
        }
        /* The work in progress: the step it has reached, how long it has
           taken, and a Stop. The canned rotation described work that might
           not be happening; the server says what it is reading. */
        function thinkingNode(c) {
            const p = pending[c.id];
            const m = el('div', 'msg assistant chat-thinking'); m.id = 'thinking-' + c.id;
            const t = el('div', 'thinking');
            const label = el('span', 'th-label', p.label);
            const secs = el('span', 'th-secs', elapsed(p.started));
            const stop = el('button', 'btn btn-sm th-stop'); stop.type = 'button'; stop.textContent = 'Stop';
            stop.onclick = () => stopAnswer(c.id);
            t.append(loader(), label, secs, stop); m.append(t);
            return m;
        }
        const elapsed = (t0) => { const s = Math.round((Date.now() - t0) / 1000); return s < 60 ? s + 's' : Math.floor(s / 60) + 'm ' + (s % 60) + 's'; };
        function paintThinking(cid) {
            const node = $('thinking-' + cid), p = pending[cid];
            if (!node || !p) return;
            node.querySelector('.th-label').textContent = p.label;
            node.querySelector('.th-secs').textContent = elapsed(p.started);
        }
        function stopAnswer(cid) {
            const p = pending[cid]; if (!p) return;
            p.stopped = true;
            try { p.ctrl.abort(); } catch (e) {}
        }
        function busyNote() { addToast('Wait for this answer, then ask the next question. You can ask in another conversation meanwhile.'); }
        // Stream a chat turn over SSE. Calls onStep(label) for live progress; returns the
        // final result. Throws 'STREAM_TRANSPORT' on a transport problem so send() can fall back.
        async function streamChat(payload, onStep, signal) {
            let res;
            const stopped = () => Object.assign(new Error('Stopped.'), { stopped: true });
            try {
                const hdrs = Object.assign({ 'Content-Type': 'application/json' }, await authHeaders());
                /* The app's own session, exactly as api() sends it. Without it
                   the server answered 401 on every turn and the page silently
                   fell back to /api/chat - so the streaming path was dead code
                   that cost a round trip per message. */
                const sess = appSession(); if (sess) hdrs['X-App-Session'] = sess;
                res = await fetch('/api/chat/stream', {
                    method: 'POST',
                    headers: hdrs,
                    body: JSON.stringify(payload),
                    signal: signal,
                });
            } catch (e) { if (signal && signal.aborted) throw stopped(); throw new Error('STREAM_TRANSPORT'); }
            /* A refusal is an answer, not a broken line: 'Conversation too
               long', a busy AI window or a missing tab went straight to
               /api/chat and was asked a second time. Only a route that is not
               there, a gateway that did not answer, or a sign-in api() knows
               how to handle is handed to the plain route. */
            if (!res.ok || !res.body) {
                let why = null;
                try { why = await res.clone().json(); } catch (e) { why = null; }
                if (res.ok || res.status === 401 || [404, 405, 502, 503, 504].includes(res.status) && !(why && why.error)) throw new Error('STREAM_TRANSPORT');
                throw new Error((why && why.error) || ('The server refused the question (' + res.status + ').'));
            }
            const reader = res.body.getReader(), dec = new TextDecoder();
            let buf = '', result = null, errored = null, heard = false;
            while (true) {
                /* A connection dropped mid-answer usually REJECTS here rather
                   than ending, and its raw "network error" reached the person. */
                let chunk;
                try { chunk = await reader.read(); }
                catch (e) {
                    if (signal && signal.aborted) throw stopped();
                    if (heard) throw new Error('The answer was interrupted before it finished. Ask again to get it.');
                    throw new Error('STREAM_TRANSPORT');
                }
                const { value, done } = chunk;
                if (done) break;
                buf += dec.decode(value, { stream: true });
                let idx;
                while ((idx = buf.indexOf('\n\n')) >= 0) {
                    const line = buf.slice(0, idx).split('\n').find(l => l.startsWith('data:'));
                    buf = buf.slice(idx + 2);
                    if (!line) continue;
                    let ev; try { ev = JSON.parse(line.slice(5).trim()); } catch (e) { continue; }
                    heard = true;
                    if (ev.type === 'step') { if (onStep) onStep(ev.label); }
                    else if (ev.type === 'done') result = ev.result;
                    else if (ev.type === 'error') errored = ev.error;
                }
            }
            if (errored) throw new Error(errored);          // real server error: do NOT fall back
            /* Cut off before any answer: the run had started, and was paid
               for, by the time the first step arrived. Falling back to
               /api/chat here ran the whole question again, billed a second
               time, and the person waited twice. Only a stream that never
               spoke at all is a transport the plain route may replace. */
            if (!result && heard) throw new Error('The answer was interrupted before it finished. Ask again to get it.');
            if (!result) throw new Error('STREAM_TRANSPORT'); // nothing came back at all: fall back
            return result;
        }

        /* ---------- send ---------- */
        /* The newest messages a question carries. The whole history went
           every time, until the server's limit refused every question in a
           long conversation for good. */
        const CHAT_KEEP = 30;
        function apiHistory(c) {
            /* A question that failed is not sent: it has no answer, and its
               retry is asked afresh. */
            const turns = c.turns.filter((t, i) => t.role !== 'error' && !(t.role === 'user' && c.turns[i + 1] && c.turns[i + 1].role === 'error'));
            let msgs = turns.map(t => t.role === 'user'
                ? { role: 'user', content: t.text }
                : { role: 'assistant', content: structuredToText(t.structured) });
            if (msgs.length > CHAT_KEEP) msgs = msgs.slice(-CHAT_KEEP);
            while (msgs.length > 1 && msgs.reduce((n, m) => n + m.content.length, 0) > 80000) msgs = msgs.slice(2);
            while (msgs.length && msgs[0].role !== 'user') msgs = msgs.slice(1);
            return msgs;
        }
        /* An answer as the text the next question carries, and as Copy
           gives it: its figures, findings, sections, actions and suggested
           questions. It carried the summary and the actions alone, so a
           follow-up about what a section listed went without the list. */
        function structuredToText(s, cap) {
            if (!s) return '';
            const out = [s.summary || ''];
            (s.metrics || []).forEach(m => out.push(m.label + ': ' + m.value + (m.delta ? ' (' + m.delta + ')' : '')));
            (s.insights || []).forEach(i => out.push('- ' + (i.title || '') + (i.detail ? ': ' + i.detail : '')));
            (s.sections || []).forEach(x => out.push((x.title || '') + '\n' + (x.body || '')));
            (s.actions || []).forEach(a => out.push('• ' + (a.text || '')));
            if ((s.followups || []).length) out.push('Suggested questions: ' + s.followups.join(' | '));
            if ((s.skills_applied || []).length) out.push('Followed the skills: ' + s.skills_applied.join(', '));
            const text = out.filter(Boolean).join('\n').trim();
            return text.slice(0, cap || 4000) || '(an answer)';
        }
        async function send(text, o) {
            o = o || {};
            const typed = !text;
            text = (text || $('input').value).trim();
            if (!text) return;
            if (!tabAllowed('chat')) return;
            let c = o.convo || active();
            if (!c) c = newConvo(false);
            if (pending[c.id]) { busyNote(); return; }
            const picked = o.skills || (c.skills || []).map(id => ({ id: id, title: skillTitle(id) }));
            const at = new Date().toISOString();
            c.turns.push({ role: 'user', text, at, skills: picked.length ? picked : undefined });
            if (!c.renamed && c.turns.filter(t => t.role === 'user').length === 1) c.title = convoTitle(text);
            c.updated = Date.now();
            convos = [c].concat(convos.filter(x => x !== c));
            if (typed) { $('input').value = ''; $('input').style.height = 'auto'; syncSend(); }
            const p = pending[c.id] = { started: Date.now(), label: 'Sending your question', ctrl: new AbortController() };
            p.tick = setInterval(() => paintThinking(c.id), 1000);
            save(); renderSidebar();
            if (c === active()) { renderChat(); }
            const payload = { messages: apiHistory(c), deep: !!c.deep, skills: picked.map(s => s.id) };
            let data = null, fail = null;
            try {
                try {
                    data = await streamChat(payload, lbl => { if (lbl) { p.label = lbl; paintThinking(c.id); if (c === active() && chatNearEnd()) scrollChat(); } }, p.ctrl.signal);
                } catch (se) {
                    if ((se.message || '') !== 'STREAM_TRANSPORT') throw se;
                    p.label = 'Working on it'; paintThinking(c.id);
                    data = await api('/api/chat', payload);   // fallback
                }
                if (p.stopped) throw Object.assign(new Error('Stopped.'), { stopped: true });
            } catch (e) { fail = e; }
            clearInterval(p.tick);
            delete pending[c.id];
            if (fail) c.turns.push({ role: 'error', text: fail.message || String(fail), stopped: !!fail.stopped, at: new Date().toISOString() });
            else {
                c.turns.push({ role: 'assistant', structured: data.structured || { summary: 'Reactor did not send an answer. Ask again.' },
                    model: data.model, deep: data.deep, fell_back: data.fell_back, data_used: data.data_used, at: new Date().toISOString(),
                    not_kept: data.not_kept, held: data.held, followups_closed: data.followups_closed, followups_maybe: data.followups_maybe });
                /* Only the notes can have changed, and only when the answer
                   kept or closed one: every answer used to read the notes,
                   the store knowledge and a fresh 28-day snapshot. */
                if (data.noted || (data.followups_closed || []).length) loadMemory('notes');
            }
            c.updated = Date.now();
            if (c !== active()) c.unread = true;
            save(); renderSidebar();
            if (c === active() && $('view-chat').classList.contains('active')) {
                const log = $('chat-log');
                const th = $('thinking-' + c.id); if (th) th.remove();
                const node = turnNode(c, c.turns[c.turns.length - 1], c.turns.length - 1);
                node.classList.add('enter');
                /* The answer before this one loses its 'Ask again' offer. */
                log.append(node);
                scrollToMsg(node);
                const who = node.querySelector('.who');
                chatSay(fail ? 'The question was not answered.' : 'Reactor answered. ' + String((data.structured || {}).summary || '').slice(0, 160));
                if (who) { who.tabIndex = -1; }
            } else if (c === active()) renderChat(true);
        }
        function skillTitle(id) { const s = skills.find(x => x.id === id); return s ? s.title : ''; }
        /* The first question, cut at a word with an ellipsis: it was cut at
           48 characters mid-word. */
        function convoTitle(text) {
            const t = String(text).replace(/\s+/g, ' ').trim();
            if (t.length <= 60) return t;
            const cut = t.slice(0, 60); const sp = cut.lastIndexOf(' ');
            return (sp > 30 ? cut.slice(0, sp) : cut).replace(/[,.;:]$/, '') + '…';
        }

        /* ---------- composer ---------- */
        function syncSend() { $('send').disabled = !$('input').value.trim(); }
        function syncComposer() {
            const c = active();
            deep = !!(c && c.deep);
            const dt = $('deep-toggle');
            dt.classList.toggle('on', deep); dt.setAttribute('aria-checked', String(deep));
            $('deep-note').hidden = !deep;
            const host = $('composer-skills'); host.replaceChildren();
            const ids = (c && c.skills) || [];
            ids.forEach(id => {
                const chip = el('span', 'sk-chip');
                chip.append(ico(I.book), el('span', null, skillTitle(id) || 'A skill'));
                const x = iconButton(I.x, 'Stop applying ' + (skillTitle(id) || 'this skill'), { size: 'tag', title: 'Stop applying' });
                x.onclick = () => { c.skills = c.skills.filter(k => k !== id); save(); syncComposer(); $('input').focus(); };
                chip.append(x); host.append(chip);
            });
            host.hidden = !ids.length;
            if (ids.length) host.prepend(el('span', 'sk-chips-l', 'Applying'));
            $('input').placeholder = ids.length ? 'Ask with ' + (ids.length === 1 ? 'that skill' : 'those skills') + ' applied…' : 'Ask about your store…';
            syncSend();
        }
        /* Which skills to apply to this conversation's questions. Reactor
           picks the ones that fit by itself; this is for when you want one
           followed whatever the question. */
        async function pickSkills(btn) {
            if (!skills.length && !skillsLoadErr) { try { await loadSkills(); } catch (e) {} }
            const c = active() || newConvo(false);
            const on = new Set(c.skills || []);
            const items = [{ heading: true, label: skills.length ? 'Apply to this conversation' : 'No skills yet' }];
            skills.slice(0, 30).forEach(s => items.push({ label: s.title, checked: on.has(s.id), onClick: () => {
                c.skills = on.has(s.id) ? [...on].filter(k => k !== s.id) : [...on, s.id].slice(-8);
                if (c.turns.length) save();
                syncComposer(); $('input').focus();
            } }));
            if (tabAllowed('skills')) items.push('-', { label: skills.length ? 'Manage skills' : 'Write a skill', icon: I.book, onClick: () => setView('skills') });
            dropMenu(btn, items);
        }
        function useSkillInChat(id) {
            if (!tabAllowed('chat')) return;
            const c = newConvo(false); if (!c) return;
            c.skills = [id];
            setView('chat'); syncComposer();
            $('input').focus();
        }

