        /* ---------- Size list tab ----------
           The sheet the label lookup reads, every row, as a data table the
           reference would draw: a toolbar of search and faceted filters with
           the active ones shown as chips, rows grouped under their maker with
           each group foldable and an A to Z strip to jump by, numbers in
           tabular columns with the unit in the heading, notes on one line,
           paging a hundred at a time, and the filtered list exportable. A
           ruling made in the app shows over the sheet's own answer. A row
           opens in place to show all it knows, and a person with the size
           grant rules there through the same rule route the Production
           Manager uses. */
        let sizesCache = null;
        const SIZES_STATUS = [['all', 'All models'], ['review', 'Needs review'], ['ruled', 'Ruled in the app'], ['nosize', 'No size'], ['excluded', 'Not a gobo']];
        const SIZES_SORTS = [['maker', 'Maker A to Z'], ['model', 'Model A to Z'], ['size_desc', 'Produced size, large first'], ['size_asc', 'Produced size, small first'], ['glass_desc', 'Holder glass, large first']];
        /* A search has an order of its own, best match first, kept apart
           from the browsing order: a search is a question, and its answer
           goes at the top. */
        const SIZES_QSORTS = [['match', 'Best match']].concat(SIZES_SORTS);
        const sizesState = { q: '', maker: '', size: '', status: 'all', sort: 'maker', qsort: 'match', group: true, page: 1, pageSize: 100, folded: {}, open: {}, reveal: null, focus: null };
        async function showSizesView() { renderSizes(); if (!sizesCache || sizesCache.error) refreshSizes(); }
        async function refreshSizes() {
            // A new ruling can change the label's answer: ask it again.
            sizesCheck.q = ''; sizesCheck.res = null; sizesCheck.want = '';
            try { sizesCache = await api('/api/gobo-sizes/list', {}); }
            catch (e) { sizesCache = { error: e.message }; }
            if (document.querySelector('#view-sizes.active')) renderSizes();
        }
        const sizesNum = (v) => { const n = parseFloat(v); return isNaN(n) ? null : n; };
        const sizesEff = (r) => (r.ruling && r.ruling !== 'exclude' ? r.ruling : r.produced) || '';
        // What the bench cuts it at: nothing, for a model ruled not a gobo.
        const sizesCut = (r) => r.ruling === 'exclude' ? '' : sizesEff(r);
        // A row's own key, for what is open: the sheet repeats maker and model.
        const sizesKey = (r) => [r.manufacturer, r.model, r.glass, r.image, r.produced].join('|');
        function sizesStatusOf(r) {
            if (r.ruling === 'exclude') return 'excluded';
            if (r.ruling || (r.domain_rulings && r.domain_rulings.length)) return 'ruled';
            if (!r.produced) return 'nosize';
            if (r.review) return 'review';
            return 'ok';
        }
        /* ---------- Size list search ----------
           Forgiving where it was literal, which found nothing for most of
           the ways a fixture is written. A word is matched from its start,
           and a name's words may be typed apart or run together, with or
           without their punctuation and accents: 'claypaky', 'e100z' and
           'huracan' find Clay Paky, the E-100Z and the Huracán-X. The names
           the store sells a model under, the aliases the label reads, are
           searched with it, so 'S4 Jr' finds the Source Four Jr; the trade's
           shorthand and number words come from the server's table ('ADJ',
           'S4', '4' for 'Four'). A figure finds the models cut at that size
           ('64mm'), or held in glass of it. The best match goes first and the
           words that matched are marked. A search that finds nothing tries
           each word that matches nowhere against the words on the sheet, so
           one wrong letter still finds the fixture, and says so. */
        const sizesFold = (s) => String(s == null ? '' : s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
        /* Words split where letters meet figures, as the label's own digit
           key splits them: 'VL2500' is 'vl 2500', so 'vl 2500 spot', 'tmh s
           400' and 'robin 600 e' find VL2500 Spot, TMH-S400 and Robin 600E,
           and 'vl2500' still runs across the two. */
        const sizesWords = (s) => sizesFold(s).match(/[a-z]+|[0-9]+/g) || [];
        // The joins of a name's first words: 'clay', 'claypaky', 'claypakysharpy'.
        const sizesLead = (w) => w.map((_, k) => w.slice(0, k + 1).join(''));
        /* A word typed across a name's words, from word k on: 'claypaky'
           across Clay Paky, 'e100' across E-100Z. It must take two letters of
           the last word it runs into, or 'chauvett', one letter too many,
           ran on into Chauvet Trackscan and found it. */
        function sizesRun(words, k, w) {
            let p = 0;
            for (let j = k; j < words.length; j++) {
                const wd = words[j], rest = w.length - p;
                if (rest <= wd.length) return wd.startsWith(w.slice(p)) && (j === k || rest >= Math.min(2, wd.length) || /^\d/.test(wd));
                if (w.substr(p, wd.length) !== wd) return false;
                p += wd.length;
            }
            return false;
        }
        let sizesIx = null;
        function sizesIndex() {
            const c = sizesCache;
            if (sizesIx && sizesIx.c === c) return sizesIx;
            const rows = (c && c.rows) || [];
            const nk = (s) => String(s || '').trim().toLowerCase().replace(/\s+/g, ' ');
            const byMM = {}, byM = {};
            rows.forEach((r, i) => {
                r._i = i; r._aka = [];
                String(r.model || '').split(',').map(nk).filter(Boolean).forEach(p => {
                    const k = nk(r.manufacturer) + '|' + p;
                    (byMM[k] = byMM[k] || []).push(r); (byM[p] = byM[p] || []).push(r);
                });
            });
            /* The aliases file read as the label reads it: the model under the
               alias's own maker first, then under any maker. */
            ((c && c.aliases) || []).forEach(a => {
                const t = nk(a.list_model), name = String(a.store_model || '').trim();
                if (!t || !name) return;
                (byMM[nk(a.manufacturer) + '|' + t] || byM[t] || []).forEach(r => { if (r._aka.indexOf(name) < 0) r._aka.push(name); });
            });
            const vocab = {};
            const items = rows.map(r => {
                const mw = sizesWords(r.model), kw = sizesWords(r.manufacturer), aka = r._aka.map(sizesWords);
                mw.concat(kw, ...aka).forEach(w => { if (w.length >= 4 && /[a-z]/.test(w)) vocab[w] = (vocab[w] || 0) + 1; });
                return { r, mw, kw, kmw: kw.concat(mw), aka, text: ' ' + sizesWords((r.notes || '') + ' ' + (r.review || '')).join(' ') + ' ',
                         model: mw.join(''), both: kw.concat(mw).join(''), akaC: aka.map(w => w.join('')),
                         mLead: sizesLead(mw), bLead: sizesLead(kw.concat(mw)),
                         size: sizesNum(sizesCut(r)), glass: sizesNum(r.glass) };
            });
            const same = {};
            const sh = (c && c.shorthand) || {};
            (sh.words || []).concat(Object.keys(sh.makers || {}).map(k => [k, sh.makers[k]]))
                .map(g => g.map(w => sizesWords(w).join('')).filter(Boolean))
                .forEach(g => g.forEach(w => { same[w] = Array.from(new Set((same[w] || [w]).concat(g))); }));
            sizesIx = { c, items, vocab, same };
            return sizesIx;
        }
        /* The typed words, each with the forms it may take. A figure, with
           or without 'mm' after it, also asks for a size; with 'mm' it asks
           for nothing else. A word with punctuation in it keeps its parts:
           a decimal is matched as its words in order ('2.0' in Intimidator
           Spot 2.0 HTI, never '20' run together, which found every 200W),
           and the notes are searched for the parts as words ('M-size'). */
        function sizesQuery(q, ix) {
            const toks = [];
            sizesFold(q).split(/\s+/).filter(Boolean).forEach(t => {
                t = t.replace(/^[ø⌀]/, '');
                const last = toks[toks.length - 1];
                if (t === 'mm' && last && last.num != null) { last.sizeOnly = true; last.alts = []; last.parts = sizesWords(last.text).concat(['mm']); return; }
                const parts = sizesWords(t);
                if (!parts.length) return;
                const n = t.match(/^(\d+(?:[.,]\d+)?)(mm)?$/);
                /* A figure in mm asks for a size, and for a name with those
                   very words in it ('Crystal Spot - max 0.5mm'), not for any
                   word starting 64. */
                const tk = { text: t, num: n ? parseFloat(n[1].replace(',', '.')) : null, sizeOnly: !!(n && n[2]),
                             parts: parts.length > 1 ? parts : null, alts: [] };
                const w = parts.join('');
                if (!tk.sizeOnly && !(n && /[.,]/.test(n[1]))) tk.alts = ix.same[w] || [w];
                toks.push(tk);
            });
            return toks;
        }
        // One word against one row: how well it matched, and where.
        function sizesTok(x, tk) {
            let best = 0, via = '';
            const pick = (s, v) => { if (s > best) { best = s; via = v; } };
            if (tk.num != null) { if (x.size === tk.num) pick(6, 'size'); else if (x.glass === tk.num) pick(3, 'size'); }
            tk.alts.forEach(w => {
                x.mw.forEach((m, k) => { if (m === w) pick(6, 'model'); else if (m.startsWith(w)) pick(5, 'model'); else if (sizesRun(x.mw, k, w)) pick(4, 'model'); });
                x.kw.forEach((m, k) => { if (m === w) pick(4, 'maker'); else if (m.startsWith(w)) pick(3.5, 'maker'); else if (sizesRun(x.kmw, k, w)) pick(3, 'maker'); });
                x.aka.forEach(a => a.forEach((m, k) => { if (m.startsWith(w) || sizesRun(a, k, w)) pick(4.5, 'aka'); }));
            });
            if (tk.parts && !tk.alts.length) {
                // A decimal: its words one after another, the last from its start.
                const at = (words, k) => tk.parts.every((p, j) => j < tk.parts.length - 1 ? words[k + j] === p : (words[k + j] || '').startsWith(p));
                x.mw.forEach((_, k) => { if (at(x.mw, k)) pick(5, 'model'); });
                x.kmw.forEach((_, k) => { if (at(x.kmw, k)) pick(3, 'maker'); });
                x.aka.forEach(a => a.forEach((_, k) => { if (at(a, k)) pick(4.5, 'aka'); }));
            }
            // The notes, but not for a size: a note that mentions 64mm is not cut at 64.
            if (!tk.sizeOnly) (tk.parts ? [tk.parts.join(' ')] : tk.alts).forEach(w => { if (w.replace(/ /g, '').length >= 3 && x.text.indexOf(w) >= 0) pick(1, 'notes'); });
            return [best, via];
        }
        // Every word must match; the whole name typed out scores highest.
        function sizesScore(x, toks) {
            let total = 0, aka = false;
            for (const tk of toks) {
                const [s, via] = sizesTok(x, tk);
                if (!s) return 0;
                total += s; if (via === 'aka') aka = true;
            }
            /* The name typed from its start scores by whole words, the last
               one perhaps half typed: 'robe' is Robe's first word, and only
               the start of Robert Juliat's, whose models repeat the maker. */
            const qc = toks.filter(t => t.alts.length).map(t => t.alts[0]).join('');
            const lead = (L) => L.indexOf(qc) >= 0 ? 2 : L.some((J, k) => k > 0 && qc.startsWith(L[k - 1]) && J.startsWith(qc)) ? 1 : 0;
            if (qc) {
                const m = lead(x.mLead), b = lead(x.bLead);
                total += x.model === qc ? 20 : m === 2 ? 8 : m === 1 ? 6 : x.mw.length && x.mw[0].startsWith(qc) ? 3 : 0;
                total += x.both === qc ? 20 : b === 2 ? 6 : b === 1 ? 4 : 0;
                if (x.akaC.indexOf(qc) >= 0) total += 15;
            }
            x.r._akaHit = aka;
            return total;
        }
        function sizesOsa(a, b) {
            const d = [];
            for (let i = 0; i <= a.length; i++) { d[i] = [i]; }
            for (let j = 1; j <= b.length; j++) d[0][j] = j;
            for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++) {
                const cost = a[i - 1] === b[j - 1] ? 0 : 1;
                d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
                if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
            }
            return d[a.length][b.length];
        }
        /* A word of four letters or more that matches no row at all is put
           to the nearest word on the sheet: one letter out, two from eight
           letters. Measured against the start of each sheet word, so a word
           still being typed ('chaiv') finds its word too. */
        function sizesFix(toks, ix) {
            const fixed = [];
            const out = toks.map(tk => {
                const w = tk.alts[0];
                if (tk.num != null || !w || w.length < 4 || ix.items.some(x => sizesTok(x, tk)[0])) return tk;
                const lim = w.length >= 8 ? 2 : 1;
                let best = null, bd = lim + 1, bn = 0;
                Object.keys(ix.vocab).forEach(v => {
                    let d = lim + 1;
                    for (let L = Math.max(1, w.length - lim); L <= Math.min(v.length, w.length + lim); L++) d = Math.min(d, sizesOsa(w, v.slice(0, L)));
                    if (d < bd || (d === bd && d <= lim && ix.vocab[v] > bn)) { best = v; bd = d; bn = ix.vocab[v]; }
                });
                if (!best || bd > lim) return tk;
                fixed.push([tk.text, best]);
                return Object.assign({}, tk, { text: best, alts: ix.same[best] || [best] });
            });
            return { toks: out, fixed };
        }
        let sizesLast = { toks: [], fixed: [] };
        function sizesRows() {
            const st = sizesState;
            const ix = sizesIndex();
            const pool = ix.items.filter(({ r }) => {
                if (st.maker && r.manufacturer !== st.maker) return false;
                if (st.size && sizesCut(r) !== st.size) return false;
                const s = sizesStatusOf(r);
                if (st.status === 'review' && s !== 'review' && s !== 'nosize') return false;
                if (st.status === 'ruled' && s !== 'ruled' && s !== 'excluded') return false;
                if (st.status === 'nosize' && s !== 'nosize') return false;
                if (st.status === 'excluded' && s !== 'excluded') return false;
                return true;
            });
            let toks = sizesQuery(st.q, ix), fixed = [];
            const run = (tk) => !tk.length ? pool.map(x => { x.r._score = 0; return x; }) : pool.filter(x => (x.r._score = sizesScore(x, tk)) > 0);
            let hits = run(toks);
            if (!hits.length && toks.length) {
                const f = sizesFix(toks, ix);
                const again = f.fixed.length ? run(f.toks) : [];
                if (again.length) { hits = again; toks = f.toks; fixed = f.fixed; }
            }
            sizesLast = { toks, fixed };
            const eff = (r) => sizesNum(sizesCut(r));
            const byName = (a, b) => a.manufacturer.localeCompare(b.manufacturer) || a.model.localeCompare(b.model, undefined, { numeric: true });
            const sorters = {
                match: (a, b) => (b._score - a._score) || byName(a, b),
                maker: byName,
                model: (a, b) => a.model.localeCompare(b.model, undefined, { numeric: true }) || a.manufacturer.localeCompare(b.manufacturer),
                size_desc: (a, b) => ((eff(b) == null ? -1 : eff(b)) - (eff(a) == null ? -1 : eff(a))) || byName(a, b),
                size_asc: (a, b) => ((eff(a) == null ? 1e9 : eff(a)) - (eff(b) == null ? 1e9 : eff(b))) || byName(a, b),
                glass_desc: (a, b) => ((sizesNum(b.glass) == null ? -1 : sizesNum(b.glass)) - (sizesNum(a.glass) == null ? -1 : sizesNum(a.glass))) || byName(a, b),
            };
            const by = st.q.trim() ? st.qsort : st.sort;
            return hits.map(x => x.r).sort(sorters[by] || byName);
        }
        /* The words a search matched, marked where they sit in a name. A word
           typed run together marks each word it ran across. */
        function sizesMarked(text, toks) {
            const s = String(text == null ? '' : text);
            const alts = [];
            (toks || []).forEach(t => (t.alts.length ? t.alts : t.parts ? [t.parts.join('')] : []).forEach(a => { if (a) alts.push(a); }));
            const frag = document.createDocumentFragment();
            if (!alts.length) { frag.append(s); return frag; }
            const chars = Array.from(s), seq = [], starts = [], words = [];
            let inWord = false;
            let kind = '';
            chars.forEach((ch, i) => {
                const f = sizesFold(ch).replace(/[^a-z0-9]/g, '');
                if (!f) { inWord = false; return; }
                for (const x of f) {
                    const k = /\d/.test(x) ? 'd' : 'a';
                    if (!inWord || k !== kind) { starts.push(seq.length); words.push(''); }
                    inWord = true; kind = k;
                    seq.push({ c: x, i }); words[words.length - 1] += x;
                }
            });
            const on = new Set();
            starts.forEach((p, k) => alts.forEach(a => { if (sizesRun(words, k, a)) for (let j = p; j < p + a.length; j++) on.add(seq[j].i); }));
            let buf = '', marked = false;
            const flush = () => { if (!buf) return; if (marked) frag.append(el('mark', 'sizes-hit', buf)); else frag.append(buf); buf = ''; };
            chars.forEach((ch, i) => { const m = on.has(i); if (m !== marked) { flush(); marked = m; } buf += ch; });
            flush();
            return frag;
        }
        /* What a label prints for the name typed, from the label's own lookup
           on the server, so the list and the label cannot disagree. Asked once
           typing settles, and only for what reads as a fixture's name, two
           words or more, as an order carries a maker and a model. One word
           like 'spot' or a holder code like 'gh24' names no fixture, and the
           label would answer for it all the same; nor is it asked about a
           word the search had to put right. */
        const sizesCheck = { q: '', res: null, want: '', seq: 0, t: 0 };
        /* Not a maker's name alone ('clay paky'), and not while the last word
           is one letter ('clay paky s' is a name being typed), unless that is
           a model's whole name ('Focus Spot Two Z'). */
        function sizesCheckable(q) {
            const w = q.split(/\s+/).filter(t => t && !/^[ø⌀]?\d+([.,]\d+)?(mm)?$|^mm$/i.test(t));
            if (w.length < 2) return false;
            const ix = sizesIndex(), qc = sizesWords(q).join('');
            if (!ix.names) {
                ix.makers = new Set(ix.items.map(x => x.kw.join('')).concat(Object.keys(((ix.c && ix.c.shorthand) || {}).makers || {})));
                ix.names = new Set(ix.items.flatMap(x => [x.model, x.both]));
            }
            if (ix.makers.has(qc)) return false;
            return sizesWords(w[w.length - 1]).join('').length > 1 || ix.names.has(qc);
        }
        function sizesIsMatch(r) {
            const m = sizesCheck.res && sizesCheck.q === sizesState.q.trim() && sizesCheck.res.match;
            return !!m && r.manufacturer === m.manufacturer && r.model === m.model;
        }
        function sizesTagMatches() {
            const P = sizesPane; if (!P) return;
            P.card.querySelectorAll('tr.sizes-row').forEach(tr => {
                const r = (sizesCache.rows || [])[+tr.dataset.i];
                const cell = tr.querySelector('td.sizes-model');
                if (r && cell && sizesIsMatch(r) && !cell.querySelector('.sizes-labeltag')) cell.append(sizesLabelTag());
            });
        }
        const sizesLabelTag = () => { const t = el('span', 'lbl-chip note sizes-labeltag', 'The label’s match'); t.title = 'An order with the name you typed prints this row'; return t; };
        function sizesLabelCheck(host) {
            const q = sizesState.q.trim();
            if (!sizesCheckable(q) || sizesLast.fixed.length) { clearTimeout(sizesCheck.t); sizesCheck.seq++; sizesCheck.want = ''; return; }
            if (sizesCheck.q === q && sizesCheck.res) {
                // Back to a name already answered: a newer question still on its way is dropped.
                clearTimeout(sizesCheck.t); sizesCheck.seq++; sizesCheck.want = '';
                host.append(sizesLabelLine(sizesCheck.res)); return;
            }
            /* The line's place is taken at once, with the list, and the answer
               fills it: arriving 400ms later into an empty place it pushed the
               rows down under a tap aimed at them. */
            const wait = el('p', 'sizes-label-line quiet'); wait.append(ico(I.printer), el('span', null, 'Checking what the label prints…'));
            host.append(wait);
            // Paging or sorting while the answer is on its way does not ask again.
            if (sizesCheck.want === q) return;
            clearTimeout(sizesCheck.t);
            const seq = ++sizesCheck.seq; sizesCheck.want = q;
            sizesCheck.t = setTimeout(async () => {
                let res;
                try { res = await api('/api/gobo-sizes/check', { q }); }
                catch (e) { res = { failed: e.message }; }
                if (seq !== sizesCheck.seq) return;
                sizesCheck.want = '';
                const h = sizesPane && sizesPane.card.querySelector('.sizes-label');
                if (res.failed) { if (h) h.replaceChildren(el('p', 'sizes-label-line quiet', 'The label’s answer could not be read: ' + res.failed)); return; }
                sizesCheck.q = q; sizesCheck.res = res;
                if (h) { h.replaceChildren(sizesLabelLine(res)); sizesTagMatches(); }
            }, 400);
        }
        function sizesLabelLine(res) {
            // A name the label cannot place is often one still being typed: said quietly.
            const p = el('p', 'sizes-label-line' + (!res.match && !res.excluded ? ' quiet' : ''));
            p.append(ico(I.printer));
            /* Short, so the answer fits the place kept for it: at 110
               characters it took a second line at 1024 and a third on a
               phone, and moved the rows after all. The name typed is in the
               box above it. */
            const txt = el('span');
            /* The name opens its row when the row is in the list. Otherwise it
               is plain words: going to it threw away the search typed. */
            const name = () => {
                const label = res.match.manufacturer + ' ' + res.match.model;
                const shown = ((sizesPane && sizesPane.rows) || []).some(r => r.manufacturer === res.match.manufacturer && r.model === res.match.model);
                if (!shown) return el('b', null, label);
                const b = textLink(label, { size: 'inline' }); b.type = 'button';
                b.title = 'Show it in the list'; b.onclick = () => sizesReveal(res.match); return b;
            };
            if (res.excluded) txt.append('The label prints no size and no CHECK: the name is ruled not a gobo.');
            else if (res.match && res.size) txt.append('The label prints ', name(), ' at ' + res.size + ' mm.');
            else if (res.match) txt.append('The label finds ', name(), ' but says CHECK: ' + res.reason + '.');
            else txt.append('The label says CHECK: ' + (res.reason || 'Model not found in the size list') + '.');
            /* The label's lookup takes a model with no maker's name on it when
               the maker named has none ('Robe' 'spot' prints Vari-Lite's Spot). */
            if (res.match && res.manufacturer && res.match.manufacturer !== res.manufacturer)
                txt.append(' No ' + res.manufacturer + ' model has that name.');
            (res.domains || []).forEach(d => txt.append(' For ' + d.domain + ': ' + d.size + ' mm.'));
            p.append(txt);
            return p;
        }
        // The label's match, opened and shown on its page of the list.
        function sizesReveal(m) {
            const r = ((sizesPane && sizesPane.rows) || []).find(x => x.manufacturer === m.manufacturer && x.model === m.model);
            if (!r) return;
            const key = sizesKey(r);
            sizesState.open[key] = true; sizesState.reveal = key;
            paintSizesList();
        }
        /* The top bar's search finds fixtures too, for anyone who can open
           the Size list: 'sharpy' from any page lands on the Sharpy with its
           details open. The sheet is read the first time it is asked for and
           kept, as the tab keeps it. */
        let sizesLoading = null;
        function sizesEnsure() {
            if (sizesCache && !sizesCache.error) return Promise.resolve();
            if (!sizesLoading) sizesLoading = api('/api/gobo-sizes/list', {}).then(d => { sizesCache = d; }, () => {}).then(() => { sizesLoading = null; });
            return sizesLoading;
        }
        function sizesFind(q, n) {
            if (!sizesCache || sizesCache.error || !q.trim()) return { rows: [], toks: [] };
            const ix = sizesIndex(), toks = sizesQuery(q, ix);
            if (!toks.length) return { rows: [], toks };
            const hits = [];
            ix.items.forEach(x => { const s = sizesScore(x, toks); if (s) hits.push([s, x.r]); });
            hits.sort((a, b) => (b[0] - a[0]) || a[1].manufacturer.localeCompare(b[1].manufacturer) || a[1].model.localeCompare(b[1].model));
            return { rows: hits.slice(0, n).map(h => h[1]), toks };
        }
        function openSizeRow(q, r) {
            Object.assign(sizesState, { q: q.trim(), maker: '', size: '', status: 'all', page: 1 });
            const key = sizesKey(r);
            sizesState.open[key] = true; sizesState.reveal = key;
            setView('sizes');
        }
        function sizesChips() {
            const st = sizesState; const defs = [];
            if (st.maker) defs.push([st.maker, () => { st.maker = ''; }]);
            if (st.size) defs.push(['Produced ' + st.size + ' mm', () => { st.size = ''; }]);
            if (st.status !== 'all') defs.push([SIZES_STATUS.find(x => x[0] === st.status)[1], () => { st.status = 'all'; }]);
            if (!defs.length) return null;
            const wrap = el('div', 'fchips');
            defs.forEach(([label, clear]) => {
                const c = el('span', 'fchip', label); const b = el('button'); b.title = 'Remove'; b.innerHTML = I.x;
                b.onclick = () => { clear(); st.page = 1; renderSizes(); }; c.append(b); wrap.append(c);
            });
            const all = el('span', 'fchip'); all.classList.add('clickable'); all.textContent = 'Clear all';
            all.onclick = () => { Object.assign(st, { q: '', maker: '', size: '', status: 'all', page: 1 }); renderSizes(); };
            wrap.append(all);
            return wrap;
        }
        function sizesSelect(label, options, current, onPick) {
            const s = el('select', 'psel'); s.setAttribute('aria-label', label);
            options.forEach(([v, text]) => { const o = el('option', null, text); o.value = v; if (v === current) o.selected = true; s.append(o); });
            s.onchange = () => onPick(s.value);
            return s;
        }
        function sizesExport(rows) {
            const head = ['Manufacturer', 'Model', 'Holder glass (mm)', 'Image (mm)', 'Sheet size (mm)', 'Ruling (mm)', 'Undercut (mm)', 'Production review', 'Notes'];
            const esc = (v) => { v = (v == null ? '' : String(v)); if (/^[=+\-@\t\r]/.test(v)) v = "'" + v; return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
            const lines = [head.join(',')];
            rows.forEach(r => lines.push([r.manufacturer, r.model, r.glass, r.image, r.produced, r.ruling || '', r.undercut, r.review, r.notes].map(esc).join(',')));
            const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
            const url = URL.createObjectURL(blob), a = document.createElement('a');
            a.href = url; a.download = 'size-list.csv'; document.body.append(a); a.click(); a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        }
        /* The produced size in two cells: the figure alone, right-aligned
           in a column of figures, and one status chip, in the words the
           Status filter uses. As one right-aligned cell the figures zig-zagged
           59px whenever a chip followed them, and a row could carry 'no size'
           and 'review' at once. Set size is in the row's details now, not a
           button on every row. */
        const SIZES_CHIP = { review: ['Needs review', 'warn'], ruled: ['Ruled in the app', 'made'],
                             nosize: ['No size', 'warn'], excluded: ['Not a gobo', 'note'] };
        function sizesProducedCells(r) {
            const fig = el('td', 'num sizes-fig');
            const v = r.ruling === 'exclude' ? '' : sizesEff(r);
            if (v) {
                fig.append(el('b', null, v), el('span', 'sizes-unit', ' mm'));
                if (r.ruling && r.produced && r.produced !== r.ruling) fig.title = 'The sheet says ' + r.produced;
            }
            const stat = el('td', 'sizes-status');
            const k = sizesStatusOf(r);
            const chip = k === 'nosize' && r.review ? SIZES_CHIP.review : SIZES_CHIP[k];
            if (chip) { const c = el('span', 'lbl-chip ' + chip[1], chip[0]); if (r.review) c.title = r.review; stat.append(c); }
            (r.domain_rulings || []).forEach(d => { const c = el('span', 'lbl-chip note', '@' + d.domain + ' ' + d.size); c.title = 'For orders from ' + d.domain + ' only'; stat.append(document.createTextNode(' '), c); });
            return [fig, stat];
        }
        /* Everything the sheet and the rulings say about one model, in words
           and in full, where the table has a column for each and shortens the
           notes. Hover text was the only way to read a note or the reason a
           row needs review, and a tablet has no hover; under 860px the notes
           were not on screen at all. */
        /* An opened model (12 Oct 2026, OPS-16): one band lined up with the
           table's own columns. Under Maker to Produced as, Cut at with Set size
           straight after it, and the model's measures; under Status to Notes,
           the words: the ruling, the review, the notes, its other names and
           any one customer's size. It was a 177px list of every fact. */
        function sizesDetail(r, span, canEdit) {
            const tr = el('tr', 'sizes-detail');
            const left = el('td', 'sizes-d-l'); left.colSpan = span - 3; left.id = 'sizes-d-' + r._i;
            const right = el('td', 'sizes-d-r'); right.colSpan = 3;
            const v = sizesEff(r);
            const cut = el('div', 'sizes-cut');
            const acts = el('div', 'act-row sizes-detail-acts');
            acts.append(el('b', null, r.ruling === 'exclude' ? 'Nothing: it is ruled not a gobo, so its label prints no size and no CHECK.'
                : v ? v + ' mm' : 'No size yet, so its label says CHECK.'));
            if (canEdit) {
                const setBtn = textButton('Set size', { small: true }); setBtn.type = 'button';
                setBtn.onclick = () => sizesInlineRule(acts, r, setBtn);
                acts.append(setBtn);
            }
            cut.append(el('span', 'k', 'Cut at'), acts);
            left.append(cut);
            const facts = el('div', 'sizes-facts');
            const fact = (k, val) => { if (!val) return; const f = el('span'); f.append(el('span', null, k), document.createTextNode(val)); facts.append(f); };
            fact('Holder glass', r.glass && r.glass + ' mm');
            fact('Image', r.image && r.image + ' mm');
            fact('Undercut', r.undercut && r.undercut !== '0' ? r.undercut + ' mm' : '');
            if (facts.childNodes.length) left.append(facts);
            const dl = el('dl', 'sizes-dl');
            const add = (k, val) => { if (val) dl.append(el('dt', null, k), el('dd', null, val)); };
            if (r.ruling) add('Ruling', 'Made in the app. ' + (r.off_sheet ? 'This model is not on the sheet.'
                : r.produced ? 'The sheet says ' + r.produced + ' mm.' : 'The sheet has no size for it.'));
            // A ruling settles what the sheet flagged; the flag is kept as the sheet's.
            add(r.ruling ? 'Sheet\u2019s review' : 'Needs review', r.review);
            add('Notes', r.off_sheet ? '' : r.notes);
            add('Also sold as', (r._aka || []).join(', '));
            (r.domain_rulings || []).forEach(d => add('One customer', 'Orders from ' + d.domain + ' are cut at ' + d.size + ' mm.'));
            if (dl.childNodes.length) right.append(dl);
            tr.append(left, right);
            return tr;
        }
        function sizesInlineRule(acts, r, setBtn) {
            const inp = document.createElement('input'); inp.type = 'text'; inp.className = 'sizes-inp field-sm';
            inp.value = sizesEff(r); inp.setAttribute('aria-label', 'Production size in millimetres');
            const save = textButton('Save', { kind: 'primary', small: true }); const cancel = textButton('Cancel', { small: true });
            save.type = cancel.type = 'button';
            /* The size and Set size come back as they were. */
            const before = [...acts.childNodes];
            cancel.onclick = () => { acts.replaceChildren(...before); setBtn.focus(); };
            save.onclick = async () => {
                setBusy(save, true);
                try {
                    await api('/api/gobo-sizes/rule', { op: 'set', manufacturer: r.manufacturer, model: r.model, size: inp.value.trim() });
                    toastOk(r.manufacturer + ' ' + r.model + ' now cuts at ' + inp.value.trim() + ' mm.');
                    sizesState.focus = { key: sizesKey(r) };
                    await refreshSizes();
                } catch (e) { toastError(e.message); setBusy(save, false); }
            };
            inp.onkeydown = (ev) => { if (ev.key === 'Enter') save.click(); if (ev.key === 'Escape') cancel.click(); };
            const row = el('div', 'act-row sizes-edit-acts'); row.append(inp, el('span', 'sizes-edit-unit', 'mm'), save, cancel);
            acts.replaceChildren(row);
            inp.focus(); inp.select();
        }
        /* The shell and the list are painted apart. The search box sits in
           the shell, and a search repaints only what is under the toolbar:
           every pause in typing repainted the whole tab, search box
           included, and the new box had neither the focus nor anything typed
           after the first letter, so the search took one letter and no more.
           Handing the focus back to a new box is not enough on an iPad, where
           the keyboard closes with the box it was typing into. */
        let sizesPane = null;
        function renderSizes() {
            const box = $('sizes-content'); box.innerHTML = ''; sizesPane = null;
            const c = sizesCache; const st = sizesState; const painting = !!c && !c.error;
            box.classList.toggle('no-intro', !(painting && firstPaint('sizes')));
            const sheet = (c && c.sheet) || {};
            const stamp = sheet.updated ? ('Sheet updated ' + fmtDate(sheet.updated) + (sheet.live ? '' : ' · built-in copy')) : '';
            /* One line; that a ruling wins over the sheet waits behind the
               title's info button, word for word (copy plan, Size list #1). */
            box.append(pageHead({ view: 'sizes', title: 'Size list', line: 'The glass size the bench cuts for every fixture.',
                info: infoButton('About the size list', { title: 'Size list',
                    body: 'A ruling made in the app shows over the sheet’s own answer, and the label reads the same list.' }),
                actions: [stamp ? el('span', 'ov-updated', stamp) : null, refreshBtn(refreshSizes)] }));
            if (!c) { box.append(el('div', 'empty', 'Loading…')); return; }
            if (c.error) { box.append(loadFailure('The size list could not be read. ' + c.error, refreshSizes), null); return; }
            const all = c.rows || [];
            /* facets from the whole sheet, so a filter never hides its own options */
            const makerCounts = {}; all.forEach(r => { makerCounts[r.manufacturer] = (makerCounts[r.manufacturer] || 0) + 1; });
            const makers = Object.keys(makerCounts).sort((a, b) => a.localeCompare(b));
            const sizeSet = {}; all.forEach(r => { const v = sizesCut(r); if (v) sizeSet[v] = (sizeSet[v] || 0) + 1; });
            const sizes = Object.keys(sizeSet).sort((a, b) => parseFloat(a) - parseFloat(b));
            const card = el('div', 'card');
            /* card-head as well, or the head's grid gap never applies and the
               title sat on the figure with no space. The figure is the count
               alone, under its quiet title, not 'Models' over '1,946 models'. */
            const head = el('div', 'card-head card-head-stat');
            const desc = el('div', 'card-desc'), sub = el('div', 'card-sub');
            head.append(el('div', 'card-title', 'Models'), desc, sub);
            card.append(head);
            const search = tableSearch('Search maker, model or size…', st.q, (v) => { st.q = v; st.page = 1; paintSizesList(); });
            /* No run on leaving the box: a tap on a row within 150ms of the
               last key blurred it, the run repainted the rows between the
               press and its release, and the tap was lost. The pending run
               still comes 150ms later, and keeps what the tap opened. */
            search.input.onchange = null;
            // The filters repaint the list alone too, so the one just used keeps the focus.
            const makerSel = sizesSelect('Maker', [['', 'All makers']].concat(makers.map(m => [m, m + ' (' + makerCounts[m] + ')'])), st.maker, (v) => { st.maker = v; st.page = 1; paintSizesList(); });
            const sizeSel = sizesSelect('Produced size', [['', 'All sizes']].concat(sizes.map(s => [s, s + ' mm (' + sizeSet[s] + ')'])), st.size, (v) => { st.size = v; st.page = 1; paintSizesList(); });
            const statusSel = sizesSelect('Status', SIZES_STATUS, st.status, (v) => { st.status = v; st.page = 1; paintSizesList(); });
            const sortSel = sizesSelect('Sort', SIZES_SORTS, st.sort, (v) => { st[st.q.trim() ? 'qsort' : 'sort'] = v; st.page = 1; paintSizesList(); });
            const gbtn = textButton(null, { small: true }); gbtn.textContent = 'Group by maker';
            gbtn.onclick = () => { st.group = !st.group; st.page = 1; paintSizesList(); };
            const xbtn = textButton(null, { small: true }); xbtn.append(ico(I.download), document.createTextNode('Export CSV'));
            xbtn.onclick = () => sizesExport(sizesRows());
            const tools = tableTools([search, makerSel, sizeSel, statusSel], [sortSel, gbtn, xbtn]);
            card.append(tools);
            box.append(card);
            /* The sort offers Best match while there is a search, and the
               grouping follows the maker sort: both are set as the list is
               painted, since a search no longer repaints the toolbar. */
            const syncSort = (searching, grouped) => {
                const mode = searching ? 'q' : 'b';
                if (sortSel.dataset.mode !== mode) {
                    sortSel.replaceChildren(...(searching ? SIZES_QSORTS : SIZES_SORTS).map(([v, t]) => { const o = el('option', null, t); o.value = v; return o; }));
                    sortSel.dataset.mode = mode;
                }
                sortSel.value = searching ? st.qsort : st.sort;
                gbtn.classList.toggle('on', grouped);
                gbtn.setAttribute('aria-pressed', grouped ? 'true' : 'false');
                gbtn.disabled = sortSel.value !== 'maker';
                if (gbtn.disabled) gbtn.title = 'Grouping follows the maker sort'; else gbtn.removeAttribute('title');
            };
            sizesPane = { box, card, tools, desc, sub, syncSort };
            paintSizesList();
        }
        /* Nothing found. A figure the bench does not cut ('64mm': the sizes
           go 53.3, then 66) names the nearest sizes it does, each a search. */
        function sizesNone(toks) {
            const st = sizesState, box = el('div', 'empty');
            const n = toks.length === 1 && toks[0].num != null && !st.maker && !st.size && st.status === 'all' ? toks[0].num : null;
            if (n == null) { box.textContent = st.q ? 'No model matches “' + st.q + '”.' : 'Nothing matches those filters.'; return box; }
            const cut = Array.from(new Set((sizesCache.rows || []).map(r => r.ruling === 'exclude' ? null : sizesNum(sizesEff(r))).filter(v => v != null))).sort((a, b) => a - b);
            const near = [cut.filter(v => v < n).pop(), cut.find(v => v > n)].filter(v => v != null);
            box.append('Nothing is cut at ' + n + ' mm.');
            if (near.length) {
                box.append(' The nearest ' + (near.length > 1 ? 'sizes' : 'size') + ' the bench cuts: ');
                near.forEach((v, k) => {
                    const b = textLink(v + ' mm', { size: 'inline' }); b.type = 'button';
                    b.onclick = () => { st.q = v + 'mm'; st.page = 1; renderSizes(); };
                    if (k) box.append(' and ');
                    box.append(b);
                });
                box.append('.');
            }
            return box;
        }
        /* Everything under the toolbar, and the counts in the head. The list
           stays the card's own children, as the card's rules expect. */
        function paintSizesList() {
            const P = sizesPane;
            if (!P || !P.card.isConnected) { renderSizes(); return; }
            const { box, card, tools } = P;
            const c = sizesCache; const st = sizesState;
            const all = c.rows || [];
            const rows = sizesRows();
            const toks = sizesLast.toks;
            const searching = !!st.q.trim();
            const sortBy = searching ? st.qsort : st.sort;
            const grouped = st.group && sortBy === 'maker';
            P.syncSort(searching, grouped);
            const nMakers = new Set(rows.map(r => r.manufacturer)).size;
            const nReview = rows.filter(r => { const s = sizesStatusOf(r); return s === 'review' || s === 'nosize'; }).length;
            P.desc.textContent = rows.length === all.length ? all.length.toLocaleString() : rows.length.toLocaleString() + ' of ' + all.length.toLocaleString();
            P.sub.textContent = nMakers + ' maker' + (nMakers === 1 ? '' : 's')
                + (c.rulings ? ' · ' + c.rulings + ' ruling' + (c.rulings === 1 ? '' : 's') + ' made in the app' : '')
                + (nReview ? ' · ' + nReview + ' to review' : '');
            while (tools.nextSibling) tools.nextSibling.remove();
            const chips = sizesChips(); if (chips) card.append(chips);
            /* Not announced when the typed word is the sheet's word and more
               ('clayp', a pause one letter into Clay Paky): that is a word
               still being typed, not a wrong letter. */
            const told = sizesLast.fixed.filter(f => !f[0].startsWith(f[1]));
            if (told.length) {
                const said = told.map(f => '“' + f[0] + '”').join(' and '), meant = told.map(f => '“' + f[1] + '”').join(' and ');
                card.append(el('p', 'sizes-fixed', 'Nothing has ' + said + ', so these are the models with ' + meant + '.'));
            }
            const labelHost = el('div', 'sizes-label'); card.append(labelHost);
            sizesLabelCheck(labelHost);
            if (!rows.length) { card.append(sizesNone(toks)); return; }
            const revealRow = st.reveal ? rows.find(r => sizesKey(r) === st.reveal) : null;
            // Spent here, found or not: a reveal left over fired on a later paint.
            st.reveal = null;
            P.rows = rows;
            if (revealRow) delete st.folded[revealRow.manufacturer];
            /* the list to page: a folded maker keeps one line, its heading */
            const list = [];
            let prevMaker = null;
            rows.forEach(r => {
                if (grouped && r.manufacturer !== prevMaker) { list.push({ head: r.manufacturer, n: rows.filter(x => x.manufacturer === r.manufacturer).length }); prevMaker = r.manufacturer; }
                if (!(grouped && st.folded[r.manufacturer])) list.push({ row: r });
            });
            /* Paged by MODELS: a page holds pageSize model rows, and each
               maker heading rides on the page of the first model under it (a
               folded maker's heading, which has none, on the page it falls
               in). Counting headings as lines made 1,946 models at 100 a page
               read 'Page 1 of 22' over 93 models. */
            const modelCount = list.filter(it => it.row).length;
            const pages = Math.max(1, Math.ceil(modelCount / st.pageSize));
            let seen = 0;
            list.forEach(it => { it.pg = Math.min(pages - 1, Math.floor(seen / st.pageSize)); if (it.row) seen++; });
            if (revealRow) { const at = list.find(it => it.row === revealRow); if (at) st.page = at.pg + 1; }
            if (st.page > pages) st.page = pages;
            const start = (st.page - 1) * st.pageSize, slice = list.filter(it => it.pg === st.page - 1);
            if (grouped && !st.maker && !st.q) {
                /* A to Z: the page where each initial's first maker starts */
                const az = el('div', 'az'); az.setAttribute('aria-label', 'Jump to a maker by initial');
                const firstAt = {};
                list.forEach(it => { if (it.head) { const L = it.head[0].toUpperCase(); const k = /[A-Z]/.test(L) ? L : '#'; if (!(k in firstAt)) firstAt[k] = it.pg; } });
                ['#'].concat('ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')).forEach(L => {
                    const b = el('button', null, L); b.type = 'button';
                    if (!(L in firstAt)) b.disabled = true;
                    else b.onclick = () => { st.page = firstAt[L] + 1; paintSizesList(); requestAnimationFrame(() => { const t = box.querySelector('tr[data-letter="' + L + '"]'); if (t) t.scrollIntoView({ block: 'start' }); }); };
                    az.append(b);
                });
                card.append(az);
            }
            const canEdit = !!c.can_edit;
            const cols = (grouped ? [] : [['Maker']]).concat([['Model'], ['Holder glass, mm', 1], ['Image, mm', 1], ['Produced as, mm', 1], ['Status'], ['Undercut, mm', 1], ['Notes']]);
            const kt = dataTable(cols.map(([h, num]) => [h, num ? 'num' : null]), { cls: 'sizes-table' });
            const continued = grouped && start > 0 && slice.length && !slice[0].head;
            slice.forEach((it, i) => {
                if (it.head) {
                    const tr = el('tr', 'ktable-grp'); const th = el('th'); th.colSpan = cols.length;
                    const L = it.head[0].toUpperCase(); tr.dataset.letter = /[A-Z]/.test(L) ? L : '#';
                    const folded = !!st.folded[it.head];
                    const caret = el('span', 'grp-caret'); caret.innerHTML = I.chev; caret.setAttribute('aria-hidden', 'true');
                    th.append(caret, document.createTextNode(it.head), el('span', 'grp-n', it.n + ' model' + (it.n === 1 ? '' : 's') + (folded ? ' · folded' : '')));
                    tr.append(th);
                    tr.setAttribute('aria-expanded', folded ? 'false' : 'true'); tr.tabIndex = 0; tr.setAttribute('role', 'button');
                    tr.dataset.maker = it.head;
                    tr.onclick = () => { st.folded[it.head] = !folded; st.focus = { maker: it.head }; paintSizesList(); };
                    tr.onkeydown = (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); tr.click(); } };
                    kt.add(tr); return;
                }
                if (i === 0 && continued) {
                    const tr = el('tr', 'ktable-grp'); const th = el('th'); th.colSpan = cols.length;
                    th.append(document.createTextNode(it.row.manufacturer), el('span', 'grp-n', 'continued')); tr.append(th); kt.add(tr);
                }
                const r = it.row; const key = sizesKey(r); const open = !!st.open[key];
                const tr = el('tr', 'sizes-row' + (open ? ' open' : '')); tr.dataset.i = r._i;
                if (!grouped) { const mk = el('td', 'sizes-maker'); mk.append(sizesMarked(r.manufacturer, toks)); tr.append(mk); }
                /* The model is the row's button: the whole row opens it by
                   pointer or touch, and the button is what a keyboard and a
                   screen reader reach. */
                const mTd = el('td', 'sizes-model');
                const ob = el('button', 'sizes-open'); ob.type = 'button';
                ob.setAttribute('aria-expanded', open ? 'true' : 'false'); ob.setAttribute('aria-controls', 'sizes-d-' + r._i);
                const car = el('span', 'sizes-caret'); car.innerHTML = I.chev; car.setAttribute('aria-hidden', 'true');
                const nm = el('span', 'sizes-name'); nm.append(sizesMarked(r.model, toks));
                ob.append(car, nm); mTd.append(ob);
                if (searching && r._akaHit && r._aka.length) {
                    const a = el('div', 'sizes-aka'); a.append('Sold as ', sizesMarked(r._aka.join(', '), toks)); mTd.append(a);
                }
                if (sizesIsMatch(r)) mTd.append(sizesLabelTag());
                tr.append(mTd);
                tr.append(el('td', 'num sizes-glass', r.glass || ''), el('td', 'num sizes-image', r.image || ''), ...sizesProducedCells(r));
                tr.append(el('td', 'num sizes-under', r.undercut && r.undercut !== '0' ? r.undercut : ''));
                const n = el('td', 'sizes-notes'); if (r.notes) { n.append(el('span', 'sizes-note', r.notes)); n.title = r.notes; }
                tr.append(n);
                tr.onclick = () => {
                    const now = !st.open[key];
                    if (now) st.open[key] = true; else delete st.open[key];
                    tr.classList.toggle('open', now); ob.setAttribute('aria-expanded', now ? 'true' : 'false');
                    const next = tr.nextElementSibling;
                    if (next && next.classList.contains('sizes-detail')) next.remove();
                    if (now) tr.after(sizesDetail(r, cols.length, canEdit));
                };
                kt.add(tr);
                if (open) kt.add(sizesDetail(r, cols.length, canEdit));
            });
            card.append(kt.wrap);
            /* The house pager, counting models: it counted 'lines' (maker
               headings included) beside a head that said models, and its own
               select had its caret painted over its words. */
            const shownRows = slice.filter(it => it.row).length;
            const folded = rows.length - modelCount;
            const foot = tablePager({ total: modelCount, page: st.page, pageSize: st.pageSize, sizes: [100, 250, 500],
                count: !rows.length ? 'Nothing to show'
                    : (shownRows ? ((start + 1).toLocaleString() + ' to ' + (start + shownRows).toLocaleString() + ' of '
                                    + modelCount.toLocaleString() + ' models') : 'Every maker folded')
                      + (folded ? ', ' + folded.toLocaleString() + ' folded away' : ''),
                onPage: (n) => { st.page = n; paintSizesList(); },
                onSize: (n) => { st.pageSize = n; st.page = 1; paintSizesList(); } });
            card.append(foot);
            if (revealRow) {
                requestAnimationFrame(() => {
                    const t = card.querySelector('tr.sizes-row[data-i="' + revealRow._i + '"]');
                    if (t) { t.scrollIntoView({ block: 'center' }); const b = t.querySelector('.sizes-open'); if (b) b.focus({ preventScroll: true }); }
                });
            }
            /* The focus back where it was after a repaint the keyboard asked
               for: a folded maker's heading, or the row a size was set on. */
            const f = st.focus; st.focus = null;
            if (f && f.maker) { const t = [...card.querySelectorAll('tr.ktable-grp')].find(x => x.dataset.maker === f.maker); if (t) t.focus(); }
            if (f && f.key) { const r2 = rows.find(r => sizesKey(r) === f.key); const t = r2 && card.querySelector('tr.sizes-row[data-i="' + r2._i + '"] .sizes-open'); if (t) t.focus(); }
        }
