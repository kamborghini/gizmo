        /* ---------- Markdown ----------
           One renderer for a skill, an answer written as prose and what
           Reactor learned from the website: headings, paragraphs, lists (one
           inside another), numbered steps, tick boxes, quotes, code, rules,
           tables, bold, italic, code words and links. It builds elements and
           sets only their text, so nothing in a file or an answer can become
           markup; a link opens only when it is a web address. */
        const MD_LI = /^(\s*)([-*+•]|\d{1,3}[.)])\s+(.*)$/;
        /* A character escaped with a backslash stands for itself: it is held
           as a private-use stand-in while the marks are read, then put back. */
        const mdEsc = (s) => String(s || '').replace(/\\([\\\x60*_\[\]()#+\-.!|>~])/g, (m, c) => String.fromCharCode(0xE000 + c.charCodeAt(0)));
        const mdUnesc = (s) => String(s || '').replace(/[-]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xE000));
        const MD_INLINE = /(\x60+)([^\x60]+?)\1|!\[([^\]]*)\]\((?:[^()\s]|\([^()\s]*\))+\)|\*\*\*([^*]+?)\*\*\*|\*\*([^*]+?)\*\*|(^|[^\w])__([^_]+?)__(?!\w)|\*([^*\s][^*]*?)\*|(^|[^\w])_([^_\s][^_]*?)_(?!\w)|\[((?:[^\[\]]|\[[^\]]*\])+)\]\(((?:[^()\s]|\([^()\s]*\))+)(?:\s+"[^"]*")?\)/g;
        function mdInline(node, text) {
            const re = new RegExp(MD_INLINE.source, 'g');
            let last = 0, m;
            const s = mdEsc(text);
            const txt = (t) => document.createTextNode(mdUnesc(t));
            while ((m = re.exec(s))) {
                if (m.index > last) node.append(txt(s.slice(last, m.index)));
                if (m[1]) node.append(el('code', 'md-ic', mdUnesc(m[2])));
                else if (m[0][0] === '!' && m[3] !== undefined) { if (m[3]) node.append(txt(m[3])); }   /* a picture stands as its words */
                else if (m[4]) { const b = el('strong'), e = el('em'); mdInline(e, mdUnesc(m[4])); b.append(e); node.append(b); }
                else if (m[5]) { const b = el('strong'); mdInline(b, mdUnesc(m[5])); node.append(b); }
                else if (m[7]) { node.append(txt(m[6])); const b = el('strong'); mdInline(b, mdUnesc(m[7])); node.append(b); }
                else if (m[8]) { const e = el('em'); mdInline(e, mdUnesc(m[8])); node.append(e); }
                else if (m[10]) { node.append(txt(m[9])); const e = el('em'); mdInline(e, mdUnesc(m[10])); node.append(e); }
                else if (m[11]) {
                    const href = mdUnesc(m[12]);
                    if (/^https?:\/\//i.test(href)) { const a = el('a', 'md-a'); mdInline(a, mdUnesc(m[11])); a.href = href; a.target = '_blank'; a.rel = 'noopener noreferrer'; node.append(a); }
                    else mdInline(node, mdUnesc(m[11]));
                }
                last = re.lastIndex;
            }
            if (last < s.length) node.append(txt(s.slice(last)));
            return node;
        }
        const mdIndent = (l) => (l.match(/^\s*/)[0]).replace(/\t/g, '    ').length;
        function mdList(lines, i, indent) {
            const first = lines[i].match(MD_LI);
            const ordered = /\d/.test(first[2]);
            const list = el(ordered ? 'ol' : 'ul', 'md-list');
            if (ordered && parseInt(first[2], 10) > 1) list.start = parseInt(first[2], 10);
            let li = null;
            while (i < lines.length) {
                const line = lines[i];
                if (!line.trim()) {
                    /* A blank line inside a list keeps it going when the list,
                       or the item's own carried-on text, resumes. */
                    let j = i + 1; while (j < lines.length && !lines[j].trim()) j++;
                    const nx = j < lines.length && lines[j].match(MD_LI);
                    const nInd = nx ? nx[1].replace(/\t/g, '    ').length : -1;
                    const under = j < lines.length && !nx && li && mdIndent(lines[j]) > indent;
                    /* Only the same list, or one inside it: a bulleted list
                       after a numbered one is a list of its own. */
                    if (under || (nx && (nInd > indent || (nInd === indent && /\d/.test(nx[2]) === ordered)))) { i = j; continue; }
                    break;
                }
                const m = line.match(MD_LI);
                const ind = mdIndent(line);
                if (!m) {
                    /* A line indented under an item carries it on, after a
                       blank line too: it split the list in two. */
                    if (li && ind > indent) {
                        if (i > 0 && !lines[i - 1].trim()) li.append(el('br')); else li.append(document.createTextNode(' '));
                        mdInline(li, line.trim()); i++; continue;
                    }
                    break;
                }
                if (ind < indent || (ind === indent && /\d/.test(m[2]) !== ordered)) break;
                if (ind > indent) {
                    const r = mdList(lines, i, ind);
                    (li || list).append(r[0]); i = r[1]; continue;
                }
                li = el('li');
                let body = m[3];
                const task = body.match(/^\[( |x|X)\]\s+(.*)$/);
                if (task) { li.append(el('span', 'md-task', task[1].trim() ? '☑ ' : '☐ ')); body = task[2]; }
                mdInline(li, body); list.append(li); i++;
            }
            return [list, i];
        }
        const mdTableRule = (l) => /\|/.test(l) && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/.test(l);
        function mdNodes(text) {
            const frag = document.createDocumentFragment();
            let src = String(text || '').replace(/\r\n?/g, '\n');
            /* A file's header is not part of what it says (only a real one:
               a text that opens with a rule keeps its first paragraph), and
               a comment is for the writer. */
            const fmx = mdFrontmatter(src);
            if (Object.keys(fmx.meta).length) src = fmx.body;
            src = src.replace(/<!--[\s\S]*?-->/g, '');
            const lines = src.split('\n');
            let i = 0, para = [];
            /* A line break a person typed stays a line break: a skill
               written as 'Step 1 ... Step 2 ...' on lines of their own ran
               together as one paragraph. */
            const flush = () => {
                if (!para.length) return;
                const p = el('p');
                para.forEach((ln, k) => { if (k) p.append(el('br')); mdInline(p, ln); });
                frag.append(p); para = [];
            };
            while (i < lines.length) {
                const raw = lines[i], t = raw.trim();
                const fence = t.match(/^(\x60{3,}|~{3,})/);
                if (fence) {
                    flush();
                    const mark = fence[1], code = []; i++;
                    /* It closes only on the kind and length that opened it. */
                    while (i < lines.length && !(lines[i].trim().startsWith(mark[0].repeat(mark.length)) && !lines[i].trim().replace(/^[\x60~]+/, '').trim())) { code.push(lines[i]); i++; }
                    i++;
                    const pre = el('pre', 'md-code'); pre.append(el('code', null, code.join('\n'))); frag.append(pre);
                    continue;
                }
                if (!t) { flush(); i++; continue; }
                const h = t.match(/^(#{1,6})\s+(.*?)\s*#*$/);
                if (h) { flush(); const n = el(h[1].length <= 2 ? 'h4' : 'h5', 'md-h'); mdInline(n, h[2]); frag.append(n); i++; continue; }
                /* A line underlined with '===' is a heading. */
                if (!para.length && i + 1 < lines.length && /^\s*={3,}\s*$/.test(lines[i + 1])) {
                    const n = el('h4', 'md-h'); mdInline(n, t); frag.append(n); i += 2; continue;
                }
                /* A table, with or without pipes at its edges: its second line
                   is the '---|---' rule. */
                if (/\|/.test(t) && i + 1 < lines.length && mdTableRule(lines[i + 1])) {
                    flush();
                    const rows = [];
                    while (i < lines.length && lines[i].trim() && /\|/.test(lines[i])) { rows.push(lines[i].trim()); i++; }
                    frag.append(pipeTable(rows)); continue;
                }
                if (/^\|.*\|$/.test(t)) {
                    flush();
                    const rows = [];
                    while (i < lines.length && /^\|.*\|$/.test(lines[i].trim())) { rows.push(lines[i].trim()); i++; }
                    frag.append(pipeTable(rows)); continue;
                }
                if (/^(-\s*){3,}$|^(\*\s*){3,}$|^(_\s*){3,}$/.test(t)) { flush(); frag.append(el('hr', 'md-hr')); i++; continue; }
                if (t.startsWith('>')) {
                    flush();
                    const q = [];
                    while (i < lines.length && lines[i].trim().startsWith('>')) { q.push(lines[i].trim().replace(/^>\s?/, '')); i++; }
                    const bq = el('blockquote', 'md-quote'); bq.append(mdNodes(q.join('\n'))); frag.append(bq);
                    continue;
                }
                if (MD_LI.test(raw)) {
                    flush();
                    const r = mdList(lines, i, mdIndent(raw));
                    frag.append(r[0]); i = r[1]; continue;
                }
                para.push(t); i++;
            }
            flush();
            return frag;
        }
        /* An answer written as prose, when the model ended without the
           answer tool: its headings, lists and tables drawn as such. It was
           one run-on paragraph with '##', '**' and '|---|' in it. */
        function proseNodes(text) { return mdNodes(text); }
        function pipeTable(rows) {
            /* Cells split on unescaped pipes: 'a\|b' is one cell. */
            const cells = (r) => r.trim().replace(/\\\|/g, '').replace(/^\||\|$/g, '').split('|').map(x => x.trim().replace(//g, '|'));
            const body = rows.filter(r => !mdTableRule(r));
            const kt = dataTable((body.length ? cells(body[0]) : []).map(x => mdInline(document.createDocumentFragment(), x)), { wrap: 'prose-table' });
            body.slice(1).forEach(r => { const tr = el('tr'); cells(r).forEach(x => tr.append(mdInline(el('td'), x))); kt.add(tr); });
            return kt.wrap;
        }
        function followupChips(list, onPick) {
            const wrap = el('div', 'followups');
            list.forEach(q => { const b = el('button', 'chip'); b.append(ico(I.spark), document.createTextNode(q)); b.onclick = () => onPick(q); wrap.append(b); });
            return wrap;
        }

        function renderStructured(container, s, opts) {
            opts = opts || {};
            /* opts.ids names blocks as widgets, {metrics, insights, sections,
               actions}. Chat renders the same blocks into a message, where
               nothing is arranged, so only a page that is arranged passes it. */
            const as = (b, kind) => (opts.ids && opts.ids[kind] ? widget(b, opts.ids[kind]) : b);
            /* opts.chat: { c, t }, the conversation and the answer, so what
               the reader does to it (a tick, Track, a section opened) is kept
               on the answer. */
            const chat = opts.chat || null;
            if (s.summary) {
                const sum = String(s.summary).trim();
                const nl = sum.indexOf('\n');
                if (chat && nl > 0) {
                    container.append(el('div', 'summary', sum.slice(0, nl).replace(/^#{1,6}\s+|\*\*|__/g, '')));
                    const rest = el('div', 'prose'); rest.append(proseNodes(sum.slice(nl + 1))); container.append(rest);
                } else container.append(el('div', 'summary', sum));
            }
            if (Array.isArray(s.metrics) && s.metrics.length) {
                const b = el('div', 'block' + (chat ? ' chat-metrics' : ''));
                /* The figure group every page uses, in a chat answer too: each at its
                   own width on one baseline (final visual review M7). */
                b.append(metricsStrip(s.metrics)); container.append(as(b, 'metrics'));
            }
            if (Array.isArray(s.insights) && s.insights.length) {
                const b = el('div', 'block insights'); s.insights.forEach((ins, i) => b.append(insightCard(ins, i))); container.append(as(b, 'insights'));
            }
            if (Array.isArray(s.sections) && s.sections.length) {
                const b = el('div', 'block');
                /* In an answer, the first section is open (all of them when
                   there are two), since that is where the answer's findings
                   are; and what the reader opens stays open. */
                s.sections.forEach((sec, k) => {
                    if (!chat) { b.append(sectionCard(sec)); return; }
                    const saved = chat.t.open && chat.t.open[k];
                    const open = saved != null ? saved : (k === 0 || s.sections.length <= 2);
                    b.append(sectionCard(sec, open, (on) => { chat.t.open = chat.t.open || {}; if (chat.t.open[k] === on) return; chat.t.open[k] = on; save(); }));
                });
                container.append(as(b, 'sections'));
            }
            if (Array.isArray(s.actions) && s.actions.length) {
                if (opts.ids && opts.ids.actions) {
                    /* On a page, the heading and its list are siblings, so
                       cardifySections folds the heading into the card as its
                       title, as every other report's list is. Inside a block it
                       stayed a bare 16px label between two 18px headings. */
                    container.append(as(el('div', 'section-title', 'Recommended actions'), 'actions'));
                    container.append(actionsCard(s.actions));
                } else {
                    const b = el('div', 'block'); b.append(el('div', 'section-title', 'Recommended actions')); b.append(actionsCard(s.actions, chat ? 'chat' : undefined, chat ? chat.t : null, save)); container.append(b);
                }
            }
            /* On an arranged report page the line goes in its header instead:
               a block with no id there stops the page being arranged. */
            if (!opts.ids) { const f = followedNote(s); if (f) container.append(f); }
            if (!opts.noFollowups && Array.isArray(s.followups) && s.followups.length) {
                container.append(followupChips(s.followups, (q) => { send(q, chat ? { convo: chat.c } : undefined); $('input').focus(); }));
            }
        }

