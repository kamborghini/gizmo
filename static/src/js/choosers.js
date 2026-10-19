        /* ---------- The two choosers: ONE builder each ----------
           tabStrip() moves you between sections of a page; segmented() changes
           what a card or a list shows. A screen passes its items and its handler
           and nothing else: the look is the .tabs / .segmented block, and five
           hand-built families did these two jobs before (2026-10-05).

           items: [key, label] pairs, or {key | value, label, n, icon, extra,
           title, disabled}: n is a count drawn after the label, icon makes the
           choice icon-only (label becomes its name), extra is a node shown after
           the label (a tick, a Beta mark). opts.nav: the tabs are pages, so the
           live one is
           aria-current="page" rather than pressed. opts.label: the group's name
           for a screen reader. Picking the live choice again does nothing;
           picking another marks it at once, so a screen that switches in place
           needs nothing more, then calls onPick(key). Every button carries
           data-k, for a caller that has to reach one later. */
        function chooser(kind, items, current, onPick, opts) {
            opts = opts || {};
            const bar = el('div', kind);
            /* What was last picked, kept apart from what is marked: a caller may
               mark another choice for a while (CRM deals shows List while the
               Board cannot draw a closed status), and pressing that one must
               still be heard as a choice. */
            let cur = current;
            if (opts.label) { bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', opts.label); }
            const mark = (b, on) => {
                b.classList.toggle('on', on);
                b.setAttribute(opts.nav ? 'aria-current' : 'aria-pressed', on ? (opts.nav ? 'page' : 'true') : 'false');
            };
            (items || []).forEach(it => {
                if (!it) return;
                const o = Array.isArray(it) ? { key: it[0], label: it[1] }
                    : { key: it.key !== undefined ? it.key : it.value, label: it.label, extra: it.extra, title: it.title, disabled: it.disabled, n: it.n, icon: it.icon };
                const b = el('button', kind === 'tabs' ? 'tab' : null);
                b.type = 'button'; b.dataset.k = String(o.key);
                /* An icon-only choice (Forecast's Custom range) says its name to
                   a screen reader and on hover; a count sits 8 after its word. */
                if (o.icon) { b.append(ico(o.icon)); b.setAttribute('aria-label', o.label); b.title = o.title || o.label; }
                else b.append(document.createTextNode(o.label));
                if (o.n != null) b.append(el('span', 'cnt', String(o.n)));
                if (o.extra) b.append(o.extra);
                if (o.title && !o.icon) b.title = o.title;
                if (o.disabled) b.disabled = true;
                mark(b, o.key === current);
                b.onclick = () => {
                    if (b.classList.contains('on') && o.key === cur) return;
                    cur = o.key;
                    [].slice.call(bar.children).forEach(c => mark(c, c === b));
                    onPick(o.key);
                };
                bar.append(b);
            });
            /* A strip that scrolls (a phone) is redrawn scrolled to its start,
               which left the active tab cut off at the edge, so it is brought
               into view once the strip is on the page. Not scrollIntoView:
               that can scroll the page itself as well. */
            if (kind === 'tabs' && typeof requestAnimationFrame === 'function') requestAnimationFrame(() => {
                const on = bar.querySelector('.tab.on');
                if (!on || !bar.isConnected || bar.scrollWidth <= bar.clientWidth) return;
                const b = bar.getBoundingClientRect(), r = on.getBoundingClientRect();
                /* To the tab's own start, so the strip begins on a whole word
                   rather than half of the one before it. */
                if (r.right > b.right) bar.scrollLeft += r.left - b.left - (parseFloat(getComputedStyle(bar).paddingLeft) || 0);
            });
            return bar;
        }
        function tabStrip(items, current, onPick, opts) { return chooser('tabs', items, current, onPick, opts); }
        function segmented(items, current, onPick, opts) { return chooser('segmented', items, current, onPick, opts); }
        /* A choice among many: seven ranges as a row of buttons wrapped onto
           two lines on a tablet and hid half of themselves on a phone, so a
           long list is a compact select, the same height as the buttons
           beside it. Same items and handler as segmented(). */
        function choiceSelect(items, current, onPick, opts) {
            opts = opts || {};
            const sel = el('select', 'field-sm choice-select');
            if (opts.label) sel.setAttribute('aria-label', opts.label);
            (items || []).forEach(it => {
                if (!it) return;
                const o = document.createElement('option');
                o.value = String(Array.isArray(it) ? it[0] : (it.key !== undefined ? it.key : it.value));
                o.textContent = Array.isArray(it) ? it[1] : it.label;
                if (o.value === String(current)) o.selected = true;
                sel.append(o);
            });
            sel.onchange = () => onPick(sel.value);
            return sel;
        }

