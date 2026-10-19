        /* ==================================================================
           Design: Reactor's one source of truth, made visible. Every colour
           is read from the tokens at the top of this page as the browser
           has them, and every part is drawn by the builder the screens use,
           so this can never show a look the app does not have.
           ================================================================== */
        const DS_COLOURS = [
            ['Brand', [
                ['Teal', '--action-primary', 'Buttons and what is chosen, always with ink on it', '--text-on-action'],
                ['Teal, under the pointer', '--action-hover', 'A button the pointer is over', '--text-on-action'],
                ['Teal, held down', '--action-active', 'A button being pressed', '--text-on-action'],
                ['Teal words', '--text-brand', 'Links, teal words and the focus outline', null],
                ['Marks', '--fill-mark', 'Dots, bars, tab underlines and switches', null],
                ['Chosen', '--action-selected', 'The wash behind the chosen item', '--text-brand'],
                ['Ink', '--text-primary', 'Words', null],
                ['Page', '--surface-page', 'Behind the cards', '--text-primary'],
                ['Card', '--surface-primary', 'Cards, windows and fields', '--text-primary'],
                ['Brand blue', '--info', 'Information', null]]],
            ['Status', [
                ['Done', '--success', 'Paid, sent, in stock', null],
                ['Needs a look', '--warning', 'Due soon, running low', null],
                ['Wrong', '--error', 'Failed, overdue, refused', null]]],
            ['Charts, in the order lines are drawn', [1, 2, 3, 4, 5].map(n => ['Series ' + n, '--chart-' + n, null, null])],
        ];
        /* The mix's tokens by role (spec 2026-10-06, section 4), for the Design
           section to draw. Each group is a row of samples; each is read from the
           stylesheet as the browser has it, never copied here. Later parts add
           their groups below. */
        const MIX_TOKENS = [
            ['Greys', ['--ink', '--ink-2', '--ink-3', '--ink-4', '--line-ctl', '--line', '--line-soft', '--fill', '--white']],
            ['The ink frame', ['--surface-chrome', '--text-on-chrome', '--nav-text', '--nav-muted', '--chrome-fill', '--chrome-press', '--nav-on-bg', '--nav-on-icon']],
            ['One colour per measure', ['--c-taken', '--c-still', '--c-exp', '--c-exp-line', '--c-range', '--c-range-edge', '--c-area', '--c-area-edge', '--c-plan']],
            ['The methods compared', ['--c-method-1', '--c-method-2', '--c-method-3']],
            ['The feature band', ['--band-bg', '--band-rule', '--teal-band-1', '--teal-band-2', '--teal-band-3', '--teal-band-4']],
            ['Shadows and rules', ['--shadow-control', '--shadow-raise', '--shadow-pop', '--shadow-focal', '--shadow-label', '--ring-chosen', '--ring-live', '--ring-selected', '--rule-t', '--rule-b', '--rule-t-soft', '--rule-b-soft', '--rule-t-band']],
            ['States', ['--press', '--press-fill', '--link-underline', '--live-dot', '--live-halo', '--live-green', '--border-soft']],
            ['Type', ['--text-micro', '--text-xs', '--text-body', '--text-sm', '--text-head', '--text-md', '--text-title', '--fig-xl', '--fig-l', '--fig-m', '--fig-s', '--lh-caption', '--lh-control', '--lh-title', '--tr-title', '--tr-fig']],
            ['Sizes', ['--tag-h', '--control-h-sm', '--control-h-md', '--control-h', '--row-h', '--row-h-2', '--order-row-h', '--control-h-lg', '--box-2xl', '--icon-md', '--icon-sm', '--icon-stroke', '--icon-stroke-s', '--topbar-h', '--sidebar-w', '--frame-inset', '--wrap-pad']],
            ['Space', ['--sp-1', '--sp-2', '--sp-3', '--sp-4', '--sp-5', '--sp-6', '--sp-7', '--sp-8', '--sp-9', '--sp-10', '--control-gap', '--gap-row-icon', '--gap-cluster', '--gap-fig', '--gap-cols', '--pop-offset', '--pop-pad', '--tip-pad', '--menu-pad']],
            ['Corners', ['--radius-swatch', '--radius-tag', '--radius-control', '--radius-pop', '--radius-tile', '--radius-sheet', '--radius-band', '--radius-full']],
        ];
        /* A token as the browser resolves it, as [r, g, b]. */
        function dsColour(token) {
            const p = el('span'); p.style.color = 'var(' + token + ')';
            document.body.append(p);
            const raw = getComputedStyle(p).color;
            let c = (raw.match(/[\d.]+/g) || ['0', '0', '0']).slice(0, 3).map(Number);
            /* A mixed colour comes back as color(srgb r g b) on a 0 to 1 scale,
               not rgb() on 0 to 255: read as rgb, every mix showed as near black. */
            if (/^color\(/.test(raw)) c = c.map(v => v * 255);
            p.remove();
            return c;
        }
        const dsHex = (c) => '#' + c.map(v => Math.round(v).toString(16).padStart(2, '0')).join('').toUpperCase();
        /* Every colour token the page defines that the curated groups do not
           show, read from the :root rules themselves, so a colour added there
           shows here without anyone remembering to list it. A role names
           another token (or mixes them); a palette entry is a literal. */
        function dsOtherColours(shown) {
            const roots = [].slice.call(document.styleSheets).flatMap(sh => { try { return [].slice.call(sh.cssRules); } catch (e) { return []; } })
                .filter(r => r.selectorText === ':root');
            const cs = getComputedStyle(document.documentElement);
            const roles = [], palette = [], seen = new Set(shown);
            roots.forEach(r => {
                for (let i = 0; i < r.style.length; i++) {
                    const name = r.style[i];
                    if (!name.startsWith('--') || seen.has(name)) continue;
                    seen.add(name);
                    const v = cs.getPropertyValue(name).trim();
                    if (!v || !CSS.supports('color', v)) continue;
                    (/^\s*(var|color-mix)\(/.test(r.style.getPropertyValue(name)) ? roles : palette).push(name);
                }
            });
            const named = (t) => { const w = t.slice(2).replace(/-/g, ' '); return [w.charAt(0).toUpperCase() + w.slice(1), t, null, null]; };
            return { roles: roles.map(named), palette: palette.map(named) };
        }
        /* WCAG contrast between two colours, for the words under each swatch. */
        function dsContrast(a, b) {
            const lum = (c) => { const [r, g, bl] = c.map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }); return 0.2126 * r + 0.7152 * g + 0.0722 * bl; };
            const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
            return (hi + 0.05) / (lo + 0.05);
        }
        /* Each section's explanation is its title's info button (copy plan,
           Design #1 to #8): the samples under it show the rest. */
        function dsCard(title, desc, ...kids) {
            const c = el('section', 'card');
            const h = el('div', 'card-head');
            const t = el('h3', 'card-title', title);
            h.append(desc ? titleInfo(t, infoButton('About ' + title, { title: title, body: desc })) : t);
            c.append(h, ...kids.filter(Boolean));
            return c;
        }
        const dsLabel = (t) => el('div', 'radar-h', t);
        function dsRow(...kids) { const r = el('div', 'ds-row'); r.append(...kids.filter(Boolean)); return r; }
        function dsButton(cls, text, disabled) { const b = el('button', cls, text); b.type = 'button'; b.disabled = !!disabled; return b; }
        function paintDesign(host) {
            const page = el('div', 'ds-page');
            const white = dsColour('--surface-primary');
            /* Colours */
            const colours = dsCard('Colours', 'Every colour in Reactor is one of these, read from the one list at the top of the page. A screen asks for a role, such as teal words or a mark, and never for a colour of its own.');
            const others = dsOtherColours(DS_COLOURS.flatMap(([, rows]) => rows.map(r => r[1])));
            DS_COLOURS.concat([['Every other role a screen can ask for', others.roles],
                ['The palette the roles are drawn from', others.palette]]).forEach(([group, rows]) => {
                if (!rows.length) return;
                const grid = el('div', 'ds-swatches');
                rows.forEach(([name, token, use, on]) => {
                    const c = dsColour(token);
                    const sw = el('div', 'ds-swatch');
                    const chip = el('span', 'ds-chip'); chip.style.background = 'var(' + token + ')';
                    chip.setAttribute('aria-hidden', 'true');
                    const ratio = on ? dsContrast(c, dsColour(on)) : dsContrast(c, white);
                    const words = on ? (on === '--text-on-action' ? 'ink on it' : on === '--text-brand' ? 'teal words on it' : 'words on it') : 'on a card';
                    const facts = el('div', 'ds-facts');
                    /* A ratio says how well something reads on a card. A ground, a
                       tint or white words meant for a coloured fill (all near 1:1
                       against a card) are not read on one, so they show the value
                       alone rather than a figure that looks like a failure. */
                    const reads = !!on || ratio >= 1.5;
                    facts.append(el('div', 'ds-name', name), el('div', 'ds-val', dsHex(c) + (reads ? ' · ' + ratio.toFixed(1) + ':1 ' + words : '')));
                    if (use) facts.append(el('div', 'ds-use', use));
                    facts.title = token;
                    sw.append(chip, facts);
                    grid.append(sw);
                });
                colours.append(dsLabel(group), grid);
            });
            page.append(colours);
            /* The mix's own tokens (spec 4), each with the value the browser
               reads for it now: a swatch for a colour, the figure for the rest. */
            const mix = dsCard('Tokens', null);
            MIX_TOKENS.forEach(([group, names]) => {
                const grid = el('div', 'ds-swatches');
                names.forEach(t => {
                    const v = getComputedStyle(document.documentElement).getPropertyValue(t).trim();
                    const sw = el('div', 'ds-swatch');
                    if (v && CSS.supports('color', v)) {
                        const chip = el('span', 'ds-chip'); chip.style.background = 'var(' + t + ')';
                        chip.setAttribute('aria-hidden', 'true'); sw.append(chip);
                    }
                    const facts = el('div', 'ds-facts');
                    facts.append(el('div', 'ds-name', t), el('div', 'ds-val', v));
                    sw.append(facts); grid.append(sw);
                });
                mix.append(dsLabel(group), grid);
            });
            page.append(mix);
            /* Type: the ranks, each drawn by the class the screens use */
            const ranks = [
                ['ds-type-page', 'Page title'],
                ['section-title', 'Section heading, over a group of cards'],
                ['card-title', 'Card title'],
                ['radar-h', 'A label inside a card'],
                ['card-desc', 'Body and descriptions, at one reading width'],
                ['ds-val', 'Meta, captions and tags'],
            ].map(([cls, text]) => el('div', cls, text));
            const rankRows = ranks.map(x => { const r = el('div', 'ds-rank'); r.append(x); return r; });
            const type = dsCard('Type', 'Two typefaces and six ranks. Titles are Bricolage Grotesque, from one list kept with the colours; everything else is Inter, with figures that line up in columns.', ...rankRows);
            page.append(type);
            requestAnimationFrame(() => ranks.forEach(x => {
                const cs = getComputedStyle(x);
                x.parentNode.append(el('div', 'ds-val', cs.fontFamily.split(',')[0].replace(/["']/g, '') + ', ' + Math.round(parseFloat(cs.fontSize)) + 'px, weight ' + cs.fontWeight));
            }));
            /* Shape and space: each corner role and the spacing scale, from the tokens */
            const shapes = el('div', 'ds-swatches');
            [['--radius-control', 'Control', 'Buttons, fields, choices, chips'], ['--radius-card', 'Card', 'Cards, windows, menus'],
             ['--radius-inset', 'Inside a card', 'A box within a card'], ['--radius-tag', 'Tag', 'Labels that only display'],
             ['--radius-full', 'Round', 'Only a switch, a bar, a dot']].forEach(([t, name, use]) => {
                const sw = el('div', 'ds-swatch');
                const box = el('span', 'ds-shape'); box.style.borderRadius = 'var(' + t + ')'; box.setAttribute('aria-hidden', 'true');
                const facts = el('div', 'ds-facts');
                facts.append(el('div', 'ds-name', name), el('div', 'ds-val', getComputedStyle(document.documentElement).getPropertyValue(t).trim() + ' · ' + t), el('div', 'ds-use', use));
                sw.append(box, facts); shapes.append(sw);
            });
            const space = el('div', 'ds-space');
            [['--sp-1', 'Icon to text in a tag'], ['--sp-1-5', 'Icon to text in a control'], ['--sp-2', 'Between controls'],
             ['--sp-3', 'A row\u2019s padding'], ['--sp-4', 'Card padding and its gaps'], ['--sp-6', 'Between blocks on a page']].forEach(([t, use]) => {
                const row = el('div', 'ds-space-row');
                const bar = el('span', 'ds-space-bar'); bar.style.width = 'var(' + t + ')'; bar.setAttribute('aria-hidden', 'true');
                row.append(bar, el('span', 'ds-val', getComputedStyle(document.documentElement).getPropertyValue(t).trim()), el('span', 'ds-use', use));
                space.append(row);
            });
            page.append(dsCard('Shape and space', 'One corner for each role, and a spacing scale every distance comes from. Controls are 32 tall in forms and 28 in toolbars and card heads.',
                dsLabel('Corners'), shapes, dsLabel('Spacing'), space));
            /* Buttons */
            page.append(dsCard('Buttons', 'Every control has the same 6px corner and 14px text. One teal button on a screen, for the thing the screen is for.',
                dsRow(dsButton('btn btn-primary', 'Save'), dsButton('btn', 'Cancel'), dsButton('btn ghost', 'Quiet'),
                    dsButton('btn btn-danger', 'Delete'), dsButton('btn btn-primary', 'Not yet', true)),
                dsRow(dsButton('btn btn-sm', 'Small'), dsButton('btn btn-sm btn-primary', 'Small and teal'), refreshBtn(() => {}, 'Refresh'))));
            /* Tabs, choices, chips */
            const chips = dsRow(...['Wholesale', 'Retail', 'Trade'].map((t, i) => {
                const c = dsButton('chip', t); c.setAttribute('aria-pressed', String(i === 0));
                c.onclick = () => c.setAttribute('aria-pressed', String(c.getAttribute('aria-pressed') !== 'true'));
                return c;
            }));
            page.append(dsCard('Tabs and choices', 'Three ways to choose, each made by one piece of code, so they look and behave the same on every screen.',
                dsLabel('Tabs move between the sections of a screen'),
                tabStrip([['a', 'Overview'], ['b', 'Orders'], ['c', 'Customers']], 'a', () => {}, { label: 'Example tabs' }),
                dsLabel('A segmented control chooses within a card'),
                dsRow(segmented([['m', 'Month'], ['q', 'Quarter'], ['y', 'Year']], 'm', () => {}, { label: 'Example period' })),
                dsLabel('Chips turn things on and off, any number at once'), chips));
            /* Figures */
            page.append(dsCard('Figures', null,
                metricsStrip([{ label: 'Sales', value: money(12480, 'GBP'), delta: '8.2%', trend: 'up' },
                    { label: 'Orders', value: '214', delta: '3.1%', trend: 'down' },
                    { label: 'Average order', value: money(58.32, 'GBP', 2) }])));
            /* Table */
            const wrap = el('div', 'ktable-wrap'), t = el('table', 'ktable');
            const head = el('tr');
            [['Order', ''], ['Customer', ''], ['Placed', ''], ['Total', 'num']].forEach(([h, c]) => head.append(el('th', c || null, h)));
            const tb = el('tbody');
            [['#1041', 'Example Events Ltd', '2 Oct', 1840], ['#1042', 'A. Customer', '3 Oct', 64.5], ['#1043', 'Studio North', '4 Oct', 312]].forEach(([o, c, d, v]) => {
                const tr = el('tr');
                tr.append(el('td', null, o), el('td', null, c), el('td', null, d), el('td', 'num', money(v, 'GBP', 2)));
                tb.append(tr);
            });
            const th = el('thead'); th.append(head); t.append(th, tb); wrap.append(t);
            page.append(dsCard('Tables', 'Every list of rows: the card is its frame, rows divided by hairlines, figures to the right.', wrap));
            /* Fields: the app's own pattern, the label wrapping its caption
               and control, help or what is wrong said underneath. */
            const fields = el('div', 'ds-fields');
            const field = (lab, ctl, help, bad) => {
                const f = el('label', 'pfield'); f.append(el('span', null, lab), ctl);
                if (bad) {
                    const m = el('div', 'field-msg', bad); m.id = 'ds-' + lab.toLowerCase() + '-msg';
                    ctl.setAttribute('aria-invalid', 'true'); ctl.setAttribute('aria-describedby', m.id); f.append(m);
                } else if (help) f.append(el('div', 'field-help', help));
                return f;
            };
            const txt = el('input', 'psel'); txt.type = 'text'; txt.placeholder = 'Type here';
            const area = el('textarea', 'psel'); area.rows = 2; area.placeholder = 'A longer note';
            const wrong = el('input', 'psel'); wrong.type = 'text'; wrong.value = 'not an email';
            const dl = el('label', 'pfield'); dl.append(el('span', null, 'Delivery'));
            const sel = el('select', 'psel'); ['Next day', 'Two days', 'Collection'].forEach(o => sel.append(el('option', null, o)));
            dl.append(sel, el('div', 'field-help', 'Picked from a list.'));
            fields.append(field('Name', txt, 'What the team will see.'), dl,
                field('Note', area, 'For more than a line.'), field('Email', wrong, null, 'This needs to be an email address.'));
            page.append(dsCard('Fields', 'Labels above, help under, and what is wrong said in words beside the field.', fields));
            /* Messages */
            page.append(dsCard('Messages', null,
                el('div', 'empty', 'Nothing here yet.'),
                loadFailure('The report could not be read.', () => toastOk('Nothing to try: this is an example.')),
                dsRow(Object.assign(dsButton('btn btn-sm', 'Show a done note'), { onclick: () => toastOk('Saved.') }),
                    Object.assign(dsButton('btn btn-sm', 'Show a problem note'), { onclick: () => toastError('That did not work.') }))));
            host.append(page);
        }
        /* Contents to jump to, a search that keeps the rows that match, and
           each section in a column layout that does not leave the holes a
           two-across grid did beside a long card. */
        function paintGuideBook(host) {
            const secs = guideFor();
            const tools = el('div', 'guide-tools');
            const search = tableSearch('Search the guide…', guideView.q, (v) => { guideView.q = v; filterBook(); });
            const toc = el('nav', 'guide-toc'); toc.setAttribute('aria-label', 'Contents');
            secs.forEach(sec => {
                const a = textLink(sec.h, { cls: 'guide-toc-link' }); a.type = 'button';
                a.onclick = () => { const t = $('g-' + sec.id); if (t) { t.scrollIntoView({ block: 'start' }); const h = t.querySelector('h3'); if (h) { h.tabIndex = -1; h.focus({ preventScroll: true }); } } };
                toc.append(a);
            });
            const pr = textButton(null, { small: true }); pr.type = 'button'; pr.append(ico(I.printer), document.createTextNode('Print the guide'));
            pr.onclick = () => printGuide();
            const lead = el('div', 'act-row'); lead.append(search, pr);
            tools.append(lead, toc);
            host.append(tools);
            const grid = el('div', 'guide-grid'); host.append(grid);
            const none = el('div', 'guide-none'); none.hidden = true; host.append(none);
            secs.forEach(sec => {
                const card = el('section', 'card guide-card'); card.id = 'g-' + sec.id;
                /* The print icon beside the title (12 Oct 2026, WS-53): it sat at the card's far edge. */
                const head = el('div', 'card-head');
                const p = iconButton(I.printer, 'Print ' + sec.h, { size: 'small', title: 'Print this section' });
                p.onclick = () => printGuide([sec]);
                const tr = el('div', 'title-row'); tr.append(el('h3', 'card-title', sec.h), p);
                head.append(tr); card.append(head);
                const rows = el('dl', 'card-bleed guide-rows');
                sec.body.forEach(([t, d]) => {
                    const row = el('div', 'guide-row');
                    const dd = el('dd', 'guide-d');
                    if (String(d).includes('{dav}')) {
                        const [a, b] = String(d).split('{dav}');
                        const code = el('code', 'setup-code', davAddress());
                        const cp = textButton(null, { small: true, cls: 'guide-copy' }); cp.type = 'button'; cp.append(ico(I.copy), document.createTextNode('Copy'));
                        cp.onclick = () => copyText(davAddress(), 'Drive address copied.');
                        dd.append(document.createTextNode(a), code, document.createTextNode(' '), cp, document.createTextNode(b));
                    } else dd.textContent = d;
                    row.append(el('dt', 'guide-t', t), dd);
                    rows.append(row);
                });
                card.append(rows); grid.append(card);
            });
            const filterBook = () => {
                const q = guideView.q.trim().toLowerCase();
                let shown = 0;
                grid.querySelectorAll('.guide-card').forEach(card => {
                    let n = 0;
                    card.querySelectorAll('.guide-row').forEach(r => { const hit = !q || r.textContent.toLowerCase().includes(q) || card.querySelector('h3').textContent.toLowerCase().includes(q); r.hidden = !hit; if (hit) n++; });
                    card.hidden = !n; shown += n;
                });
                none.hidden = !!shown;
                if (!shown) {
                    const clr = textButton('Clear', { small: true }); clr.type = 'button';
                    clr.onclick = () => { guideView.q = ''; search.input.value = ''; filterBook(); search.input.focus(); };
                    none.replaceChildren(emptyState({ icon: I.search, text: 'Nothing in the guide mentions \u201c' + guideView.q + '\u201d.', action: clr }));
                }
            };
            filterBook();
        }
        /* One entry of the guide opened from Search in the top bar. */
        function openGuideAt(secId, q) {
            guideSeg = 'guide'; guideView.q = q || '';
            setView('guide');
            requestAnimationFrame(() => { const t = $('g-' + secId); if (t) t.scrollIntoView({ block: 'start' }); });
        }
        function paintReleases(host, u) {
            const v = u.version || {};
            const rels = u.releases || [];
            const card = el('div', 'card');
            /* Said from the notes and the build, separately: it read 'Running
               the 8 Sep release' over a build from sixteen days later. */
            const head = el('div', 'card-head');
            head.append(el('h3', 'card-title', 'Release notes'));
            head.append(el('p', 'card-desc', (rels.length ? 'Notes up to ' + fmtDate(rels[0].date) : 'No notes yet')
                + (v.sha ? ' · build ' + v.sha : '')
                + (v.started_at ? ' · running since ' + fmtDate(v.started_at) : '')));
            card.append(head);
            if (!rels.length) { card.append(el('div', 'empty', 'No release notes yet.')); host.append(card); return; }
            const unread = releaseBaseline(u.unread || {}, u.seen, rels.length).releases;
            /* Always the last five (12 Oct 2026, WS-50), the unread ones marked
               New: only the unread was shown, which after a quiet spell was one
               release and a void. */
            const SHOW = 5;
            const list = el('div', 'rel-list');
            const draw = (r, isNew) => {
                const sec = el('section', 'rel');
                /* A date rail: the date, then the title, beside the items. */
                const h = el('div', 'rel-rail');
                h.append(el('span', 'rel-date', fmtDate(r.date)), el('h4', 'rel-title', r.title || fmtDate(r.date)));
                if (isNew) h.append(el('span', 'lbl-chip note', 'New'));
                sec.append(h);
                const ul = el('ul', 'rel-items');
                (r.items || []).forEach(it => {
                    const li = el('li', 'rel-item');
                    li.append(el('span', 'rel-kind', cap(it.kind || 'improved')));
                    const tx = el('span', 'rel-text', it.text);
                    if (it.tab && APP_VIEWS.includes(it.tab) && tabAllowed(it.tab)) {
                        const open = actionLink('rel-open', 'Open'); open.onclick = () => setView(it.tab);
                        tx.append(document.createTextNode(' '), open);
                    }
                    li.append(tx); ul.append(li);
                });
                sec.append(ul);
                return sec;
            };
            rels.slice(0, SHOW).forEach((r, i) => list.append(draw(r, i < unread)));
            card.append(list);
            if (rels.length > SHOW) {
                const more = textButton(null, { small: true, cls: 'rel-more' }); more.type = 'button';
                more.textContent = 'Show older releases (' + (rels.length - SHOW) + ')';
                more.setAttribute('aria-expanded', 'false');
                more.onclick = () => { rels.slice(SHOW).forEach(r => list.append(draw(r, false))); more.remove(); };
                card.append(more);
            }
            host.append(card);
            markSeen('releases');
        }
        const REQ_STATES = [['open', 'Open'], ['planned', 'Planned'], ['shipped', 'Shipped'], ['declined', 'Declined']];
        function paintRequests(host, u) {
            const card = el('div', 'card');
            const head = el('div', 'card-head');
            const all = u.requests || [];
            /* An admin's how-to is the title's info button; a member keeps one
               line (copy plan, Guide #3 and #4). */
            const ft = el('h3', 'card-title', 'Feature requests');
            if (all.length) ft.append(el('span', 'card-n', String(all.length)));
            head.append(u.can_triage ? titleInfo(ft, infoButton('About feature requests', { title: 'Feature requests',
                body: 'What the team has asked for. Set each one Planned, Shipped or Declined with a reply, and the person who asked sees it here.' })) : ft);
            if (!u.can_triage) head.append(el('p', 'card-desc', 'Ask for what the app cannot do yet.'));
            const act = el('div', 'card-act');
            /* One teal: while a reply is being written, Save reply is it. */
            const add = textButton(null, { small: true, kind: reqView.reply ? '' : 'primary' }); add.type = 'button';
            add.append(ico(I.plus), document.createTextNode('Ask for a feature'));
            add.onclick = () => askFeature('guide');
            /* With nothing asked yet the empty line carries it, once (12 Oct 2026, WS-52). */
            if (all.length) act.append(add);
            head.append(act);
            card.append(head);
            if (!all.length) {
                const first = textButton(); first.type = 'button';
                first.append(ico(I.plus), document.createTextNode('Ask for a feature'));
                first.onclick = () => askFeature('guide');
                card.append(emptyState({ icon: I.spark, text: 'Nothing asked for yet.', action: first }));
                host.append(card); markSeen('requests'); return;
            }
            const count = (k) => k === 'mine' ? all.filter(r => r.by === u.me).length : k === 'all' ? all.length : all.filter(r => (r.state || 'open') === k).length;
            const F = REQ_STATES.concat([['mine', 'Yours'], ['all', 'All']]).filter(([k]) => k === 'all' || count(k));
            if (!F.some(([k]) => k === reqView.f)) reqView.f = F[0][0];
            let tabs = null;
            tabs = segmented(F.map(([k, l]) => ({ key: k, label: l, n: count(k) })), reqView.f, (k) => {
                reqView.f = k; reqView.page = 1;
                [...tabs.children].forEach((b, i) => { const on = F[i][0] === k; b.classList.toggle('on', on); b.setAttribute('aria-pressed', String(on)); });
                paintList();
            });
            const search = tableSearch('Search requests…', reqView.q, (v) => { reqView.q = v; reqView.page = 1; paintList(); });
            /* The search straight after the filters, one toolbar line. */
            card.append(tableTools([tabs, search], []));
            const listBox = el('div', 'req-list'); card.append(listBox);
            const paintList = () => {
                listBox.replaceChildren();
                const q = reqView.q.trim().toLowerCase();
                const rows = all.filter(r => reqView.f === 'all' || (reqView.f === 'mine' ? r.by === u.me : (r.state || 'open') === reqView.f))
                    .filter(r => !q || ((r.title || '') + ' ' + (r.detail || '') + ' ' + (r.note || '')).toLowerCase().includes(q));
                if (!rows.length) { listBox.append(el('div', 'empty', 'No requests match.')); return; }
                const pages = Math.max(1, Math.ceil(rows.length / reqView.size));
                if (reqView.page > pages) reqView.page = pages;
                const from = (reqView.page - 1) * reqView.size;
                /* One table (12 Oct 2026, WS-51): the request with its detail and
                   reply under it, who asked and when, the page, its state with
                   when it was set, and the actions. The state select stood alone
                   at the far right. */
                listBox.append(dtable([{ head: 'Request', cls: 'stack' }, { head: 'Asked by', cls: 'stack' }, { head: 'Page' }, { head: 'State', cls: 'stack' }]
                    .concat(u.can_triage ? [{ head: '', cls: 'act' }] : []),
                    rows.slice(from, from + reqView.size).map(r => reqRow(r, u)),
                    { cls: 'dt-req' + (u.can_triage ? ' triage' : ''), label: 'Feature requests', stop: 'm' }));
                if (rows.length > 25) listBox.append(tablePager({ total: rows.length, page: reqView.page, pageSize: reqView.size, sizes: [25, 50, 100],
                    noun: 'requests', onPage: (k) => { reqView.page = k; paintList(); }, onSize: (k) => { reqView.size = k; reqView.page = 1; paintList(); } }));
            };
            card._paint = paintList;
            paintList();
            host.append(card);
            markSeen('requests');
        }
        /* One request as a table row: { cells }. */
        function reqRow(r, u) {
            const what = document.createDocumentFragment();
            const h = el('span', 'dt-name req-head');
            h.append(el('span', 'req-title', r.title));
            if (r.by === u.me) h.append(el('span', 'lbl-chip note', 'Yours'));
            what.append(h);
            if (r.detail) what.append(el('div', 'req-detail', r.detail));
            if (r.note) {
                const n = el('div', 'req-reply');
                n.append(el('b', null, 'Reply' + ((u.names || {})[r.note_by] ? ' from ' + u.names[r.note_by] : '') + ': '), document.createTextNode(r.note));
                what.append(n);
            }
            const who = (u.names || {})[r.by] || '';
            const asked = document.createDocumentFragment();
            asked.append(el('span', 'dt-name', who || 'Someone'), el('span', 'dt-sub', fmtDate(r.at)));
            const state = document.createDocumentFragment();
            /* Neutral, unless the chip is a verdict worth colour: Shipped. */
            const tone = r.state === 'shipped' ? ' made' : ' note';
            if (!u.can_triage) state.append(el('span', 'lbl-chip req-state' + tone, cap(r.state || 'open')));
            else {
                const sel = el('select', 'field-sm req-state'); sel.setAttribute('aria-label', 'State of ' + r.title);
                REQ_STATES.forEach(([st, lab]) => { const o = el('option', null, lab); o.value = st; if ((r.state || 'open') === st) o.selected = true; sel.append(o); });
                sel.dataset.req = r.id;
                sel.onchange = () => reqWrite(r, { op: 'state', id: r.id, state: sel.value }, sel, 'select');
                state.append(sel);
            }
            if (r.state_at && (r.state || 'open') !== 'open') state.append(el('span', 'dt-sub', cap(r.state) + ' ' + fmtDate(r.state_at)));
            const cells = [what, asked, PAGE_NAMES[r.where] || r.where || '', state];
            if (u.can_triage) {
                const acts = document.createDocumentFragment();
                if (reqView.reply === r.id) {
                    /* The reply is written in the request's own cell, at its measure. */
                    const ta = el('textarea', 'sk-textarea mem-ta'); ta.rows = 2; ta.maxLength = 400; ta.value = r.note || ''; ta.dataset.initial = ta.value;
                    ta.setAttribute('aria-label', 'Reply to ' + r.title);
                    const save = textButton('Save reply', { kind: 'primary', small: true }); save.type = 'button';
                    save.onclick = () => { ta.dataset.initial = ta.value; reqWrite(r, { op: 'state', id: r.id, state: r.state || 'open', note: ta.value.trim() }, save, 'reply'); };
                    const cancel = textButton('Cancel', { small: true }); cancel.type = 'button';
                    cancel.onclick = () => { ta.dataset.initial = ta.value; reqView.reply = null; repaintRequests(); };
                    const f = el('div', 'req-replyform'); f.append(ta); what.append(f);
                    acts.append(save, cancel);
                    requestAnimationFrame(() => ta.focus());
                } else {
                    /* Reply and Change reply keep one width, so Remove lines up. */
                    const rep = textButton(null, { small: true }); rep.type = 'button'; rep.dataset.req = r.id;
                    const sw = el('span', 'swap'); const w1 = el('span', null, 'Reply'), w2 = el('span', null, 'Change reply');
                    (r.note ? w1 : w2).setAttribute('aria-hidden', 'true'); sw.append(w1, w2); rep.append(sw);
                    rep.onclick = () => { reqView.reply = r.id; repaintRequests(); };
                    const del = textButton(null, { small: true }); del.type = 'button'; del.append(ico(I.trash), document.createTextNode('Remove'));
                    del.onclick = async () => {
                        if (!await uiConfirm('Remove the request "' + r.title + '"? Use this for duplicates; it cannot be brought back.', { title: 'Remove request', okText: 'Remove' })) return;
                        reqWrite(r, { op: 'delete', id: r.id }, del);
                    };
                    acts.append(rep, del);
                }
                cells.push(acts);
            }
            return { cells: cells };
        }
        const PAGE_NAMES = { overview: 'Overview', seo: 'SEO', keywords: 'Keywords', products: 'Products', customers: 'Customers', liability: 'Liability', recon: 'Reconciliation', forecast: 'Forecast', sizes: 'Size list', connector: 'Xero sync', crm: 'CRM', loans: 'Loan units', mail: 'Inbox', files: 'Files', team: 'Team', labels: 'Production Manager', memory: 'Memory', skills: 'Skills', chat: 'Chat', guide: 'Guide' };
        /* A triage write patches the cached list and redraws the list alone. */
        async function reqWrite(r, payload, ctrl, back) {
            if (ctrl) setBusy(ctrl, true);
            try {
                const d = await api('/api/updates', payload);
                if (updCache && Array.isArray(updCache.requests)) {
                    if (payload.op === 'delete') updCache.requests = updCache.requests.filter(x => x.id !== r.id);
                    else if (d && d.item) updCache.requests = updCache.requests.map(x => x.id === r.id ? d.item : x);
                }
                reqView.reply = null;
                toastOk(payload.op === 'delete' ? 'Request removed.' : 'Saved. The person who asked sees it on Requests.');
            } catch (e) { toastError('Not saved. ' + (e.message || '')); }
            if (ctrl) setBusy(ctrl, false);
            repaintRequests();
            /* Focus goes back to the row it left, not to the page. */
            const host = $('guide-host');
            const to = back && host && host.querySelector((back === 'select' ? 'select' : 'button') + '[data-req="' + r.id + '"]');
            if (to) to.focus(); else if (host) { const t = host.querySelector('.segmented > button.on'); if (t) t.focus(); }
        }
        function repaintRequests() {
            const host = $('guide-host');
            if (!host || guideSeg !== 'requests' || !updCache) return;
            host.replaceChildren(); paintRequests(host, updCache);
        }
        function askFeature(where) {
            /* Reachable from every screen: the moment you notice a gap is the
               moment worth capturing, not later from a different tab. */
            const m = crmModal('Ask for a feature');
            const form = el('div', 'stack-form');
            form.append(el('p', 'card-sub', 'What should the app do that it cannot yet?'));
            const t = crmText('', 'One line');
            t.maxLength = 140; t.id = 'af-title';
            const tMsg = el('div', 'field-msg'); tMsg.hidden = true; tMsg.id = 'af-title-msg'; t.setAttribute('aria-describedby', tMsg.id);
            const f1 = el('label', 'pfield'); f1.append(el('span', null, 'What you want'), t); form.append(f1, tMsg);
            const d = document.createElement('textarea');
            d.className = 'pf-input'; d.rows = 4; d.maxLength = 4000;
            d.placeholder = 'When it would help, and what you do instead today';
            const f2 = el('label', 'pfield'); f2.append(el('span', null, 'Details (optional)'), d); form.append(f2);
            m.body.append(form);
            const bar = m.foot();
            const go = textButton('Send it', { kind: 'primary' });
            go.onclick = async () => {
                if (!t.value.trim()) { tMsg.hidden = false; tMsg.textContent = 'Say in one line what you want.'; markInvalid(t, true); t.focus(); return; }
                setBusy(go, true);
                try {
                    const r = await api('/api/updates', { op: 'request', title: t.value.trim(),
                        detail: d.value.trim(), where: where || '' });
                    if (updCache && Array.isArray(updCache.requests) && r && r.item) updCache.requests = [r.item].concat(updCache.requests);
                    m.close();
                    toastOk('Sent, thank you. It is on Guide, Requests' + (r && r.emailed ? ', and Cameron has been emailed.' : '.'));
                    if (currentView() === 'guide' && guideSeg === 'requests') { reqView.f = 'open'; repaintRequests(); }
                } catch (e) { setBusy(go, false); toastError(e.message); }
            };
            t.addEventListener('input', () => { if (t.value.trim()) { tMsg.hidden = true; markInvalid(t, false); } });
            t.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); go.click(); } });
            bar.append(go);
            requestAnimationFrame(() => t.focus());
        }
        /* The whole guide as this person sees it, or one section. */
        function printGuide(only) {
            const secs = only || guideFor();
            const host = $('label-print'); host.innerHTML = '';
            const ds = el('div', 'day-sheet');
            ds.append(el('h1', null, 'Reactor: ' + (secs.length === 1 ? secs[0].h : 'desk guide')));
            ds.append(el('div', 'ds-meta', 'Printed ' + fmtDate(new Date().toISOString())));
            secs.forEach(sec => {
                if (secs.length > 1) ds.append(el('h2', null, sec.h));
                sec.body.forEach(([t, d]) => {
                    const p = el('p', 'guide-print-row');
                    p.append(el('b', null, t + ': '), document.createTextNode(guideText(d)));
                    ds.append(p);
                });
            });
            host.append(ds);
            let rule = $('label-page-rule');
            if (!rule) { rule = document.createElement('style'); rule.id = 'label-page-rule'; document.head.append(rule); }
            rule.textContent = '@page { size: A4; margin: 14mm; }';
            const seq = ++printSeq;
            document.body.classList.add('printing-label');
            const cleanup = () => {
                if (seq !== printSeq) return;
                document.body.classList.remove('printing-label');
                host.innerHTML = '';
                const r = $('label-page-rule');
                if (r && r.parentNode) r.parentNode.removeChild(r);
            };
            if (window.onafterprint !== undefined) window.addEventListener('afterprint', cleanup, { once: true });
            labelFontReady().then(() => setTimeout(() => {
                if (seq !== printSeq) return;   // a newer print has the box; it opens its own dialog
                window.print(); setTimeout(cleanup, 800); }, 40), () => cleanup());
        }

