        /* ---------- the row parts ----------
           Rows and ticks (docs/DESIGN.md, Rows and Tick rows):
           - a row that opens something is not a pretend button holding other
             controls. rowOpener() is the real one: a button named for the row,
             out of sight, whose focus the row draws with its own ring; its
             Enter and Space stop at it, so a page-wide shortcut never acts on
             them too. opensOnClick() keeps a click anywhere on the row opening
             it, except on a control of its own;
           - tickRow() is the label that holds a tick (or a radio) and its
             words, with the one tick-row recipe and a screen's layout class. */
        function rowOpener(label, onOpen) {
            const b = el('button', 'row-open sr-only');
            b.type = 'button';
            b.setAttribute('aria-label', label);
            b.onclick = (e) => { e.stopPropagation(); onOpen(); };
            b.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') e.stopPropagation(); });
            return b;
        }
        function opensOnClick(row, onOpen) {
            row.addEventListener('click', (e) => {
                for (let n = e.target; n && n !== row; n = n.parentNode) {
                    if (/^(BUTTON|A|INPUT|SELECT|TEXTAREA|LABEL)$/.test(n.tagName)) return;
                }
                onOpen();
            });
        }
        function tickRow(cls) {
            return el('label', 'tick-row' + (cls ? ' ' + cls : ''));
        }
        /* ---------- the row parts end ---------- */
