        /* ---------- one dropdown menu, for the whole app ----------
           Items are {label, icon, onClick, disabled, danger, checked}, the
           string '-' is a separator, and {label, heading:true} is a group
           label. An item may also carry n (a count at the row's end) and link
           (a teal row with an arrow, for "... in the Guide"). Opening one closes any other: two open menus is a state
           nobody meant and nobody can get out of by clicking. */
        let dmenuOpen = null;
        function closeDMenu() {
            if (!dmenuOpen) return;
            const { panel, onKey, onDown, anchor } = dmenuOpen;
            dmenuOpen = null;
            panel.remove();
            document.removeEventListener('keydown', onKey, true);
            document.removeEventListener('pointerdown', onDown, true);
            window.removeEventListener('resize', closeDMenu);
            /* Scroll listener was captured on the way in, so it comes off the
               same way: a menu left listening to a scroller it no longer has a
               panel for is a leak that only shows up after a long shift. */
            if (dmenuScroller) { dmenuScroller.removeEventListener('scroll', closeDMenu); dmenuScroller = null; }
            if (anchor) { anchor.setAttribute('aria-expanded', 'false'); if (anchor.focus) anchor.focus(); }
        }
        let dmenuScroller = null;
        function dropMenu(anchor, items) {
            /* A second click on the same trigger closes it, which is what every
               menu everywhere does and what the hand expects. */
            if (dmenuOpen && dmenuOpen.anchor === anchor) { closeDMenu(); return; }
            closeDMenu();
            const panel = el('div', 'dmenu');
            panel.setAttribute('role', 'menu');
            (items || []).filter(Boolean).forEach(it => {
                if (it === '-') { panel.append(el('div', 'dmenu-sep')); return; }
                if (it.heading) { panel.append(el('div', 'dmenu-label', it.label)); return; }
                const b = el('button', 'dmenu-item' + (it.danger ? ' danger' : ''));
                b.type = 'button';
                /* A choice that is on or off says so, not by a tick alone. */
                if (typeof it.checked === 'boolean') { b.setAttribute('role', 'menuitemcheckbox'); b.setAttribute('aria-checked', String(it.checked)); }
                else b.setAttribute('role', 'menuitem');
                if (it.icon) b.append(ico(it.icon));
                b.append(el('span', null, it.label));
                if (it.n != null) { const c = el('span', 'cnt', String(it.n)); if (it.unit) c.append(el('span', 'sr-only', ' ' + it.unit)); b.append(c); }
                if (it.link) { b.classList.add('dmenu-link'); b.append(ico(I.arrowRight)); }
                /* The tick sits in the 32px the reference reserves on the right,
                   so a list of choices does not jump sideways when one is made. */
                if (it.checked) { const t = el('span', 'dmenu-tick'); t.append(ico(I.check)); b.append(t); }
                /* A long label is shortened by the menu's width; its whole text is on hover. */
                if (it.title) b.title = it.title; else if (String(it.label || '').length > 40) b.title = it.label;
                if (it.disabled) b.disabled = true;
                else b.onclick = () => { closeDMenu(); it.onClick(); };
                panel.append(b);
            });
            document.body.append(panel);
            const r = anchor.getBoundingClientRect();
            const pw = panel.offsetWidth, ph = panel.offsetHeight;
            /* Right-aligned to the trigger when left-aligning would run off the
               screen, and flipped above when there is no room below. */
            let left = r.left;
            if (left + pw > window.innerWidth - 8) left = Math.max(8, r.right - pw);
            const off = tokenNum('--pop-offset');
            let top = r.bottom + off;
            if (top + ph > window.innerHeight - 8) top = Math.max(8, r.top - ph - off);
            panel.style.left = Math.round(left) + 'px';
            panel.style.top = Math.round(top) + 'px';
            const buttons = () => [...panel.querySelectorAll('.dmenu-item:not([disabled])')];
            const onKey = (e) => {
                if (e.key === 'Escape') { e.stopPropagation(); closeDMenu(); return; }
                if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
                e.preventDefault();
                const bs = buttons(); if (!bs.length) return;
                const i = bs.indexOf(document.activeElement);
                const next = e.key === 'ArrowDown' ? (i + 1) % bs.length : (i <= 0 ? bs.length - 1 : i - 1);
                bs[next].focus();
            };
            const onDown = (e) => { if (!panel.contains(e.target) && e.target !== anchor) closeDMenu(); };
            document.addEventListener('keydown', onKey, true);
            document.addEventListener('pointerdown', onDown, true);
            window.addEventListener('resize', closeDMenu);
            /* Fixed position cannot follow a scrolling page, so it closes
               instead of drifting away from the button that opened it. */
            dmenuScroller = anchor.closest('.scroll') || null;
            if (dmenuScroller) dmenuScroller.addEventListener('scroll', closeDMenu);
            anchor.setAttribute('aria-haspopup', 'menu');
            anchor.setAttribute('aria-expanded', 'true');
            dmenuOpen = { panel, onKey, onDown, anchor };
            const first = buttons()[0]; if (first) first.focus();
        }
        /* The same box and the same way out, holding a small form rather than a
           list. Dates and a minimum do not fit a menu of choices, and putting
           them on the toolbar is how that bar grew to eleven controls. */
        function dropPanel(anchor, build) {
            if (dmenuOpen && dmenuOpen.anchor === anchor) { closeDMenu(); return; }
            dropMenu(anchor, []);                 // the machinery: position, keys, closing
            const panel = dmenuOpen.panel;
            panel.setAttribute('role', 'dialog');
            const body = el('div', 'dpanel');
            build(body, closeDMenu);
            panel.append(body);
            /* Re-measure: the panel was positioned while it was empty, so a form
               taller than nothing would hang off the bottom of the window. */
            const r = anchor.getBoundingClientRect();
            const pw = panel.offsetWidth, ph = panel.offsetHeight;
            let left = r.left;
            if (left + pw > window.innerWidth - 8) left = Math.max(8, r.right - pw);
            const off = tokenNum('--pop-offset');
            let top = r.bottom + off;
            if (top + ph > window.innerHeight - 8) top = Math.max(8, r.top - ph - off);
            panel.style.left = Math.round(left) + 'px';
            panel.style.top = Math.round(top) + 'px';
            const first = panel.querySelector('input, select, button');
            if (first) first.focus();
        }
        /* A filter as the reference writes one: a small button that says what it
           is, and what it is set to when that is not "everything". */
        function filterChip(label, options, current, onPick) {
            const chosen = options.find(o => o[0] === current);
            const isAll = !chosen || current === options[0][0];
            const b = el('button', 'btn btn-sm' + (isAll ? '' : ' on'));
            /* Label first, caret last: a menu trigger reads as its own name
               plus the direction its menu opens, not as a step forward. */
            b.append(document.createTextNode(
                isAll ? label : label + ': ' + chosen[1]), ico(I.chevDown));
            b.onclick = () => dropMenu(b, options.map(([v, l]) => ({
                label: l, checked: v === current, onClick: () => onPick(v),
            })));
            return b;
        }
        /* A row of filter tabs with their counts in the label, the way the
           reference writes them: "All (156)", and the live one marked by ink. */
