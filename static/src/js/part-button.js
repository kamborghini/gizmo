        /* ---------- the button parts ----------
           Every button the script builds comes from one of these
           (docs/DESIGN.md, Buttons, Icon buttons and Links), so a button looks
           and behaves like the others of its kind because one piece of code
           makes it:
           - button(): the ordinary button. It builds the classes the
             stylesheet already styles (btn, and btn-sm, kept as a name until
             the stylesheet is put in layers: it is the same 32 button);
           - iconButton(): one icon-only recipe in three sizes from the tokens
             (32, 24, 20), the grey icon with one hover, and a name always;
           - link(): one text link, teal and underlined, at caption size, at
             the size of its sentence, or standing alone with a chevron. */
        function button(text, opts) {
            const o = opts || {};
            const kind = o.kind === 'primary' ? ' btn-primary' : o.kind === 'danger' ? ' btn-danger' : o.kind === 'ghost' ? ' ghost' : '';
            const b = el('button', 'btn' + (o.small ? ' btn-sm' : '') + kind + (o.square ? ' btn-icon' : '') + (o.cls ? ' ' + o.cls : ''));
            if (o.icon) b.append(ico(o.icon));
            if (text != null) {
                if (o.icon) b.append(document.createTextNode(text)); else b.textContent = text;
            }
            if (o.title) b.title = o.title;
            return b;
        }
        function iconButton(icon, label, opts) {
            if (!label) throw new Error('iconButton needs a label');
            const o = opts || {};
            const size = o.size === 'small' ? ' icon-btn-sm' : o.size === 'tag' ? ' icon-btn-tag' : '';
            const tone = o.tone === 'danger' ? ' del' : o.tone === 'ok' ? ' ok' : '';
            const b = el('button', 'icon-btn' + size + tone + (o.cls ? ' ' + o.cls : ''));
            b.innerHTML = icon;
            b.title = label;
            b.setAttribute('aria-label', label);
            return b;
        }
        function link(text, opts) {
            const o = opts || {};
            const base = o.size === 'inline' ? 'seclink' : o.size === 'go' ? 'link' : 'linkish';
            const a = el('button', base + (o.cls ? ' ' + o.cls : ''), text);
            if (o.size === 'go') a.append(ico(I.chev));
            return a;
        }
        /* ---------- the button parts end ---------- */
