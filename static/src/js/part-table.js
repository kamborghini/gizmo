        /* ---------- the table parts ----------
           ONE REAL TABLE (.ktable; the div table is dtable(), with the
           structured-response parts). cols are its columns in order: a head
           (words, a Node, or null for an empty head cell) or [head, cls] with
           the head cell's classes (num, kt-main). The part builds the wrapper,
           the table, its head and its body; t.add(...rows) appends rows to the
           body and names each cell from its column as it goes, which is what a
           phone's two-line rows read ("Orders 5", see .ktable's phone rule): a
           cell across one column takes its head's words as data-h unless it has
           its own, and kt-main when that head leads its row. A cell across
           several columns names none. Add a row once its cells are all in.
           opts.head false leaves the head out (a two-column list of facts,
           whose first cell names the second). */
        function dataTable(cols, opts) {
            opts = opts || {};
            const wrap = el('div', 'ktable-wrap' + (opts.wrap ? ' ' + opts.wrap : ''));
            const table = el('table', 'ktable' + (opts.cls ? ' ' + opts.cls : ''));
            const thead = el('thead'), hr = el('tr'), body = el('tbody');
            const heads = cols.map(c => {
                const [h, cls] = Array.isArray(c) ? c : [c, null];
                const th = typeof h === 'string' ? el('th', cls || null, h) : el('th', cls || null);
                if (h && typeof h !== 'string') th.append(h);
                hr.append(th);
                return th;
            });
            thead.append(hr); if (opts.head !== false) table.append(thead); table.append(body); wrap.append(table);
            const add = (...rows) => rows.forEach(tr => {
                let i = 0;
                [...tr.children].forEach(td => {
                    const th = heads[i], span = td.colSpan || 1;
                    if (th && span === 1) {
                        const name = th.textContent.replace(/\s+/g, ' ').trim();
                        if (name && td.dataset.h === undefined) td.dataset.h = name;
                        if (th.classList.contains('kt-main')) td.classList.add('kt-main');
                    }
                    i += span;
                });
                body.append(tr);
            });
            return { wrap, table, thead, heads, body, add };
        }
        /* ---------- the table parts end ---------- */
