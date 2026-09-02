/* gizmo composer: a contenteditable editor with the toolbar the Inbox agreed
   on. Zero dependencies, one file, served like app.js.

   The cleaner in here is a COURTESY to the person typing: it keeps what is on
   screen equal to what will actually be sent, so a paste out of Word does not
   look rich in the box and arrive as a wall of grey spans. The guarantee is the
   server's sanitiser, which runs on whatever the browser sends. The two
   allowlists are deliberately identical, and if one of them ever moves the
   other has to move with it.

   Nothing here renders anything that came from a customer. The editor holds
   only what this shop typed, plus images this shop uploaded to our own bucket.
*/
(function () {
    'use strict';

    /* The allowlist, character for character the server's own (mailmime._TAGS
       plus img). Anything not in it is unwrapped: the words survive, the
       markup does not. */
    var TAGS = ['p', 'br', 'div', 'span', 'b', 'strong', 'i', 'em', 'u', 'a', 'ul', 'ol', 'li',
                'h1', 'h2', 'h3', 'blockquote', 'font', 'img'];
    /* These are dropped with their contents, because their contents are not
       words: a script's text is a program and a style block's text is CSS. */
    var DROP = ['script', 'style', 'iframe', 'object', 'embed', 'svg', 'math', 'template'];
    var STYLE_OK = ['font-family', 'font-size', 'color', 'text-align'];
    /* No url(), no expression(), no backslash escapes: the same expression the
       server compiles. */
    var STYLE_VAL = /^[a-zA-Z0-9 ,#%.'"-]+$/;
    var MAX_TOTAL = 25 * 1024 * 1024;        /* Gmail's ceiling, and ours */
    var MAX_INLINE = 5 * 1024 * 1024;        /* one picture in a body is not a film */
    var FONTS = ['Arial', 'Georgia', 'Verdana', 'Trebuchet MS', 'Courier New'];
    var SIZES = [['Small', '2'], ['Normal', '3'], ['Large', '5'], ['Huge', '7']];
    var COLOURS = [['Default', ''], ['Black', '#0a0a0a'], ['Grey', '#525252'], ['Red', '#b91c1c'],
                   ['Orange', '#c2410c'], ['Green', '#15803d'], ['Blue', '#1d4ed8'],
                   ['Purple', '#7e22ce'], ['Pink', '#be185d']];

    var ICONS = {
        justifyLeft: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><rect x="1" y="3" width="14" height="1.6" rx=".8"/><rect x="1" y="7.2" width="9" height="1.6" rx=".8"/><rect x="1" y="11.4" width="13" height="1.6" rx=".8"/></svg>',
        justifyCenter: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><rect x="1" y="3" width="14" height="1.6" rx=".8"/><rect x="3.5" y="7.2" width="9" height="1.6" rx=".8"/><rect x="1.5" y="11.4" width="13" height="1.6" rx=".8"/></svg>',
        justifyRight: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><rect x="1" y="3" width="14" height="1.6" rx=".8"/><rect x="6" y="7.2" width="9" height="1.6" rx=".8"/><rect x="2" y="11.4" width="13" height="1.6" rx=".8"/></svg>',
        insertUnorderedList: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><circle cx="2.2" cy="3.8" r="1.4"/><circle cx="2.2" cy="8" r="1.4"/><circle cx="2.2" cy="12.2" r="1.4"/><rect x="5.5" y="3" width="9.5" height="1.6" rx=".8"/><rect x="5.5" y="7.2" width="9.5" height="1.6" rx=".8"/><rect x="5.5" y="11.4" width="9.5" height="1.6" rx=".8"/></svg>',
        insertOrderedList: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><text x="0" y="5.6" font-size="5.4" font-family="inherit">1</text><text x="0" y="9.8" font-size="5.4" font-family="inherit">2</text><text x="0" y="14" font-size="5.4" font-family="inherit">3</text><rect x="5.5" y="3" width="9.5" height="1.6" rx=".8"/><rect x="5.5" y="7.2" width="9.5" height="1.6" rx=".8"/><rect x="5.5" y="11.4" width="9.5" height="1.6" rx=".8"/></svg>'
    };

    /* One stylesheet for every composer on the page, injected the first time
       one is mounted. It reads the app's own tokens, so the editor is the same
       control as everything around it rather than a widget dropped in. */
    var CSS = [
        '.cmp { display: block; }',
        '.cmp-bar { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-1);',
        '    padding: var(--sp-1); border: 1px solid var(--border); border-bottom: 0;',
        '    border-radius: var(--r-sm) var(--r-sm) 0 0; background: var(--surface-2); position: relative; }',
        '.cmp-b { border: 1px solid transparent; background: transparent; color: var(--ink);',
        '    border-radius: var(--r-xs); min-height: 32px; min-width: 32px; padding: 4px 8px;',
        '    font-size: var(--t-md); font-weight: var(--w-medium); line-height: 20px;',
        '    display: inline-flex; align-items: center; justify-content: center; cursor: pointer;',
        '    transition: background var(--dur) var(--ease), border-color var(--dur) var(--ease); }',
        '.cmp-b:hover { background: var(--surface); border-color: var(--border); }',
        '.cmp-b:focus-visible { outline: none; box-shadow: var(--focus); }',
        '.cmp-b svg { fill: currentColor; }',
        '.cmp-b.bold { font-weight: var(--w-bold); }',
        '.cmp-b.ital { font-style: italic; }',
        '.cmp-b.undr { text-decoration: underline; }',
        '.cmp-sel { height: 32px; border: 1px solid var(--border); background: var(--surface);',
        '    color: var(--ink); border-radius: var(--r-xs); font: inherit; font-size: var(--t-sm);',
        '    padding: 0 var(--sp-1); max-width: 120px; }',
        '.cmp-sep { width: 1px; height: 20px; background: var(--border); margin: 0 var(--sp-1); }',
        '.cmp-pop { position: absolute; top: 100%; left: var(--sp-1); z-index: 40; margin-top: var(--sp-1);',
        '    display: grid; grid-template-columns: repeat(3, 28px); gap: var(--sp-1);',
        '    padding: var(--sp-2); background: var(--surface); border: 1px solid var(--border);',
        '    border-radius: var(--r-sm); box-shadow: var(--sh-2); }',
        '.cmp-sw { width: 28px; height: 28px; border-radius: var(--r-xs); border: 1px solid var(--border-2);',
        '    cursor: pointer; padding: 0; }',
        '.cmp-sw.none { background: var(--surface); color: var(--ink-3); font-size: var(--t-xs); }',
        '.cmp-area { border: 1px solid var(--border); border-radius: 0 0 var(--r-sm) var(--r-sm);',
        '    background: var(--surface); color: var(--ink); font-size: var(--t-md); line-height: 1.5;',
        '    padding: var(--sp-3); min-height: 180px; max-height: 46vh; overflow-y: auto;',
        '    word-break: break-word; }',
        '.cmp-area:focus { outline: none; border-color: var(--accent); box-shadow: var(--focus); }',
        '.cmp-area.cmp-empty:before { content: attr(data-ph); color: var(--ink-3); }',
        '.cmp-area p { margin: 0 0 var(--sp-3); }',
        '.cmp-area p:last-child { margin-bottom: 0; }',
        '.cmp-area ul, .cmp-area ol { margin: 0 0 var(--sp-3); padding-left: var(--sp-5); }',
        '.cmp-area blockquote { margin: 0 0 var(--sp-3); padding-left: var(--sp-3);',
        '    border-left: 2px solid var(--border-2); color: var(--ink-2); }',
        '.cmp-area img { max-width: 100%; height: auto; border-radius: var(--r-xs); }',
        '.cmp-area a { color: var(--accent-ink); }',
        '.cmp-files { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2);',
        '    margin-top: var(--sp-2); }',
        '.cmp-chip { display: inline-flex; align-items: center; gap: var(--sp-2); min-height: 32px;',
        '    padding: var(--sp-1) var(--sp-2); border: 1px solid var(--border); border-radius: var(--r-sm);',
        '    background: var(--surface); font-size: var(--t-sm); max-width: 100%; }',
        '.cmp-chip-n { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 220px; }',
        '.cmp-chip-s { color: var(--ink-3); }',
        '.cmp-x { border: 0; background: transparent; color: var(--ink-3); cursor: pointer;',
        '    min-width: 24px; min-height: 24px; border-radius: var(--r-xs); font-size: var(--t-md);',
        '    line-height: 1; padding: 0; }',
        '.cmp-x:hover { color: var(--ink); background: var(--surface-2); }',
        '.cmp-meter { color: var(--ink-3); font-size: var(--t-xs); margin-top: var(--sp-1); }',
        '.cmp-note { color: var(--danger); font-size: var(--t-sm); margin-top: var(--sp-1); }',
        /* On a phone the bar tightens rather than hiding half of itself: the
           separators go, the padding comes in, and what is left wraps. */
        '@media (max-width: 700px) { .cmp-sel { max-width: 92px; } .cmp-area { min-height: 140px; }',
        '    .cmp-b { padding: 4px 6px; } .cmp-sep { display: none; } }'
    ].join('\n');

    function injectCss() {
        if (document.getElementById('cmp-css')) return;
        var s = document.createElement('style');
        s.id = 'cmp-css';
        s.textContent = CSS;
        document.head.append(s);
    }

    function el(tag, cls, txt) {
        var e = document.createElement(tag);
        if (cls) e.className = cls;
        if (txt != null) e.textContent = txt;
        return e;
    }

    function fmtSize(n) {
        n = Number(n) || 0;
        if (n >= 1048576) return (n / 1048576).toFixed(1) + ' MB';
        return Math.max(1, Math.round(n / 1024)) + ' KB';
    }

    /* ---- the cleaner -------------------------------------------------
       Parsed in an inert document (DOMParser never runs a script, never loads
       an image), walked once, and rebuilt by the allowlist. Unknown tags are
       unwrapped rather than deleted, because the words inside a <section> are
       still the words somebody typed. */
    function cleanStyle(value) {
        var keep = [];
        String(value || '').split(';').forEach(function (decl) {
            var i = decl.indexOf(':');
            if (i < 0) return;
            var k = decl.slice(0, i).trim().toLowerCase();
            var v = decl.slice(i + 1).trim();
            if (STYLE_OK.indexOf(k) < 0) return;
            if (!STYLE_VAL.test(v) || v.toLowerCase().indexOf('url') >= 0) return;
            keep.push(k + ':' + v);
        });
        return keep.join(';');
    }

    function unwrap(node) {
        var parent = node.parentNode;
        if (!parent) return;
        while (node.firstChild) parent.insertBefore(node.firstChild, node);
        parent.removeChild(node);
    }

    function cleanAttrs(node, tag, mine) {
        var names = Array.prototype.map.call(node.attributes, function (a) { return a.name; });
        var key = node.getAttribute('data-key') || '';
        var ours = tag === 'img' && key && mine && mine.key(key);
        names.forEach(function (name) {
            var k = name.toLowerCase();
            var v = node.getAttribute(name) || '';
            if (tag === 'a' && k === 'href') {
                var low = v.trim().toLowerCase();
                if (low.indexOf('https://') === 0 || low.indexOf('mailto:') === 0) {
                    node.setAttribute('href', v.trim().slice(0, 2000));
                } else {
                    node.removeAttribute(name);
                }
                return;
            }
            if (tag === 'img' && k === 'src') {
                /* Two sources and no others: a content-id, which is what
                   leaves, and a signed URL of an image THIS editor uploaded to
                   our own bucket, which is only ever a preview. A remote image
                   from a paste is dropped, so no message this shop sends can
                   call home from a customer's inbox. */
                var cid = /^cid:([A-Za-z0-9._@-]+)$/.exec(v.trim());
                if (cid) {
                    /* Coming IN, a content-id this editor cannot back with an
                       uploaded part is a broken picture in somebody's inbox, so
                       it goes. Going OUT there is nothing to check against:
                       getHtml has just written these itself. */
                    if (!mine || mine.cid(cid[1])) return;
                    node.removeAttribute(name);
                    return;
                }
                if (ours && v.trim().toLowerCase().indexOf('https://') === 0) return;
                node.removeAttribute(name);
                return;
            }
            if (tag === 'img' && (k === 'data-key' || k === 'data-cid')) {
                if (!ours) node.removeAttribute(name);
                return;
            }
            if (tag === 'img' && k === 'alt') { node.setAttribute('alt', v.slice(0, 200)); return; }
            if (tag === 'img' && (k === 'width' || k === 'height')) {
                if (!/^\d+$/.test(v)) node.removeAttribute(name);
                return;
            }
            if (k === 'style') {
                var cs = cleanStyle(v);
                if (cs) node.setAttribute('style', cs);
                else node.removeAttribute(name);
                return;
            }
            if (tag === 'font' && (k === 'color' || k === 'face' || k === 'size')) {
                if (!STYLE_VAL.test(v)) node.removeAttribute(name);
                return;
            }
            node.removeAttribute(name);
        });
        if (tag === 'img' && !node.getAttribute('src')) node.remove();
    }

    function walk(node, mine) {
        Array.prototype.slice.call(node.childNodes).forEach(function (n) {
            if (n.nodeType === 3) return;                      /* text is the point */
            if (n.nodeType !== 1) { n.remove(); return; }       /* comments and the rest */
            var tag = (n.tagName || '').toLowerCase();
            if (DROP.indexOf(tag) >= 0) { n.remove(); return; }
            walk(n, mine);
            if (TAGS.indexOf(tag) < 0) { unwrap(n); return; }
            cleanAttrs(n, tag, mine);
            if (tag === 'p') tidyParagraph(n);
        });
    }

    /* execCommand's leftovers. Turning a paragraph into a list leaves the
       list INSIDE the paragraph, which is not HTML any client is promised to
       render the same way, and the split leaves an empty <p></p> either side.
       A paragraph that only holds a <br> is different: that is a blank line
       the person typed on purpose, and it stays. */
    var BLOCKS = ['p', 'div', 'ul', 'ol', 'blockquote', 'h1', 'h2', 'h3', 'table'];
    function tidyParagraph(p) {
        var hasBlock = Array.prototype.some.call(p.children, function (c) {
            return BLOCKS.indexOf((c.tagName || '').toLowerCase()) >= 0;
        });
        if (hasBlock) { unwrap(p); return; }
        if (!p.childNodes.length) p.remove();
    }

    /* `mine` is what tells html coming IN from html going OUT: it answers
       whether a bucket key and a content-id belong to this editor's own
       uploads. Passed for everything inbound (the initial html, a paste, a
       setHtml); left off in getHtml, which is the outbound pass. */
    function cleanHtml(html, mine) {
        var doc = new DOMParser().parseFromString('<body>' + String(html == null ? '' : html) + '</body>',
                                                  'text/html');
        walk(doc.body, mine);
        return doc.body.innerHTML;
    }

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    /* ---- the editor --------------------------------------------------- */
    function mountComposer(host, opts) {
        opts = opts || {};
        injectCss();
        var cidSeq = 0;
        var files = [];              /* {key, name, size, type, inline, cid} */
        var savedRange = null;

        var wrap = el('div', 'cmp');
        var bar = el('div', 'cmp-bar');
        var area = el('div', 'cmp-area');
        var chips = el('div', 'cmp-files');
        var meter = el('div', 'cmp-meter');
        var note = el('div', 'cmp-note');
        note.setAttribute('role', 'status');
        area.contentEditable = 'true';
        area.setAttribute('role', 'textbox');
        area.setAttribute('aria-multiline', 'true');
        area.setAttribute('aria-label', opts.label || 'Message');
        area.setAttribute('data-ph', opts.placeholder || 'Write the message');
        function ourKey(key) {
            return files.some(function (f) { return f.key === key; });
        }
        function ourCid(cid) {
            return files.some(function (f) { return f.inline && f.cid === cid; });
        }
        var mine = { key: ourKey, cid: ourCid };
        area.innerHTML = cleanHtml(opts.html || '', mine);
        function total() {
            return files.reduce(function (n, f) { return n + (Number(f.size) || 0); }, 0);
        }
        function say(msg) {
            note.textContent = msg || '';
            if (msg && typeof opts.onError === 'function') opts.onError(msg);
        }
        function changed() {
            /* An image deleted out of the body stops being an attachment, or
               the meter goes on charging for a picture nobody can see. */
            var live = {};
            Array.prototype.forEach.call(area.querySelectorAll('img[data-key]'), function (img) {
                live[img.getAttribute('data-key')] = true;
            });
            files = files.filter(function (f) { return !f.inline || live[f.key]; });
            area.classList.toggle('cmp-empty', !area.textContent.trim() && !area.querySelector('img'));
            paintFiles();
            if (typeof opts.onChange === 'function') opts.onChange();
        }
        function paintFiles() {
            chips.innerHTML = '';
            files.filter(function (f) { return !f.inline; }).forEach(function (f) {
                var chip = el('div', 'cmp-chip');
                chip.append(el('span', 'cmp-chip-n', f.name));
                chip.append(el('span', 'cmp-chip-s', fmtSize(f.size)));
                var x = el('button', 'cmp-x', '×');
                x.type = 'button';
                x.title = 'Remove ' + f.name;
                x.setAttribute('aria-label', 'Remove ' + f.name);
                x.onclick = function () { removeAttachment(f.key); };
                chip.append(x);
                chips.append(chip);
            });
            var n = files.length;
            meter.textContent = n ? (fmtSize(total()) + ' of 25MB'
                + (n > 1 ? ', ' + n + ' files' : '')) : '';
        }

        /* The caret survives the file dialog, which takes the focus away and
           collapses the selection: an image picked from the toolbar lands
           where the person was typing, not at the top of the message. */
        function inArea() {
            var sel = window.getSelection();
            return !!(sel && sel.rangeCount && area.contains(sel.anchorNode)
                      && area.contains(sel.focusNode));
        }
        function saveSel() {
            if (inArea()) savedRange = window.getSelection().getRangeAt(0);
        }
        function caretToEnd() {
            var rg = document.createRange();
            rg.selectNodeContents(area);
            rg.collapse(false);
            var sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(rg);
            savedRange = rg;
        }
        function restoreSel() {
            /* A live selection inside the box always wins: the saved one is
               only for the case where the focus has been taken away, which is
               what a file dialog and a toolbar press both do. A saved range
               whose nodes have since been replaced points at nothing, and an
               insert against it would go nowhere: the end of the message is
               the honest place for it. */
            var live = inArea() ? window.getSelection().getRangeAt(0) : savedRange;
            area.focus();
            if (!live || !area.contains(live.commonAncestorContainer)) { caretToEnd(); return; }
            var sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(live);
        }
        function cmd(name, arg) {
            restoreSel();
            document.execCommand(name, false, arg);
            saveSel();
            changed();
        }
        function insertHtml(html) {
            restoreSel();
            document.execCommand('insertHTML', false, html);
            saveSel();
            changed();
        }

        function btn(label, key, run, title) {
            var b = el('button', 'cmp-b' + (key === 'bold' ? ' bold' : key === 'italic' ? ' ital'
                : key === 'underline' ? ' undr' : ''));
            b.type = 'button';
            b.setAttribute('data-cmd', key);
            b.title = title || label;
            b.setAttribute('aria-label', title || label);
            if (ICONS[key]) b.innerHTML = ICONS[key];
            else b.textContent = label;
            /* mousedown, not click: pressing a toolbar button must not take the
               selection out of the box before the command runs on it. */
            b.onmousedown = function (e) { e.preventDefault(); };
            b.onclick = function (e) { e.preventDefault(); run(); };
            return b;
        }
        function picker(rows, label, run) {
            var s = el('select', 'cmp-sel');
            s.setAttribute('aria-label', label);
            s.append(el('option', null, label));
            s.firstChild.value = '';
            rows.forEach(function (r) {
                var name = r instanceof Array ? r[0] : r;
                var value = r instanceof Array ? r[1] : r;
                var o = el('option', null, name);
                o.value = value;
                s.append(o);
            });
            s.onchange = function () {
                var v = s.value;
                s.value = '';                    /* a label, not a state: the */
                if (v) run(v);                   /* box below is the state */
            };
            return s;
        }

        [['B', 'bold', 'Bold'], ['I', 'italic', 'Italic'], ['U', 'underline', 'Underline']]
            .forEach(function (r) {
                bar.append(btn(r[0], r[1], function () { cmd(r[1]); }, r[2]));
            });
        bar.append(el('div', 'cmp-sep'));
        bar.append(picker(FONTS, 'Font', function (v) { cmd('fontName', v); }));
        bar.append(picker(SIZES, 'Size', function (v) { cmd('fontSize', v); }));

        /* Colour: eight of them and a way back to the default, in a swatch grid
           rather than a list of colour names nobody can picture. */
        var pop = null;
        var colourBtn = btn('Colour', 'colour', function () {
            if (pop) { pop.remove(); pop = null; return; }
            pop = el('div', 'cmp-pop');
            COLOURS.forEach(function (c) {
                var sw = el('button', 'cmp-sw' + (c[1] ? '' : ' none'), c[1] ? '' : 'A');
                sw.type = 'button';
                sw.title = c[0];
                sw.setAttribute('aria-label', c[0]);
                if (c[1]) sw.style.background = c[1];
                sw.onmousedown = function (e) { e.preventDefault(); };
                sw.onclick = function () {
                    cmd('foreColor', c[1] || '#0a0a0a');
                    if (pop) { pop.remove(); pop = null; }
                };
                pop.append(sw);
            });
            bar.append(pop);
        }, 'Text colour');
        bar.append(colourBtn);
        bar.append(el('div', 'cmp-sep'));
        [['Left', 'justifyLeft', 'Align left'], ['Centre', 'justifyCenter', 'Align centre'],
         ['Right', 'justifyRight', 'Align right'], ['Bullets', 'insertUnorderedList', 'Bulleted list'],
         ['Numbers', 'insertOrderedList', 'Numbered list']].forEach(function (r) {
            bar.append(btn(r[0], r[1], function () { cmd(r[1]); }, r[2]));
        });
        bar.append(el('div', 'cmp-sep'));
        bar.append(btn('Link', 'link', function () {
            var u = window.prompt('Link address (https://\u2026)', 'https://');
            if (!u) return;
            if (!/^https:\/\//i.test(u.trim())) { say('A link has to start with https://'); return; }
            say('');
            cmd('createLink', u.trim());
        }, 'Add a link'));
        bar.append(btn('Image', 'image', function () { pick(true); }, 'Insert an image'));
        bar.append(btn('Attach', 'attach', function () { pick(false); }, 'Attach a file'));
        bar.append(btn('Quote', 'quote', function () { cmd('formatBlock', 'blockquote'); },
                       'Quote a block'));
        bar.append(btn('Clear', 'clear', function () { cmd('removeFormat'); },
                       'Clear formatting'));

        /* ---- files -------------------------------------------------- */
        function room(size, inline) {
            if (inline && size > MAX_INLINE) {
                say('That image is over 5MB. Attach it as a file instead.');
                return false;
            }
            if (total() + size > MAX_TOTAL) {
                say('That would take this message over 25MB. Put the big files in Files and send a link.');
                return false;
            }
            return true;
        }
        /* One input, reused. A fresh one per press leaves the cancelled ones
           behind in the page, and this composer outlives a great many presses. */
        var fileInput = el('input');
        fileInput.type = 'file';
        fileInput.style.display = 'none';
        fileInput.setAttribute('aria-hidden', 'true');
        fileInput.tabIndex = -1;
        function pick(inline) {
            if (typeof opts.upload !== 'function') {
                say('Attachments are not available here.');
                return;
            }
            saveSel();
            fileInput.accept = inline ? 'image/*' : '';
            fileInput.multiple = !inline;
            fileInput.value = '';            /* or the same file twice is silent */
            fileInput.onchange = function () {
                var chosen = Array.prototype.slice.call(fileInput.files || []);
                chosen.reduce(function (chain, f) {
                    return chain.then(function () { return take(f, inline); });
                }, Promise.resolve());
            };
            fileInput.click();
        }
        function take(file, inline) {
            if (inline && !/^image\//.test(file.type || '')) {
                say('Only an image can go inside the message.');
                return Promise.resolve();
            }
            if (!room(file.size, inline)) return Promise.resolve();
            say('');
            meter.textContent = 'Uploading ' + file.name + '\u2026';
            return Promise.resolve(opts.upload(file, inline)).then(function (r) {
                if (!r || !r.key) throw new Error('The upload did not come back with a key.');
                var size = Number(r.size == null ? file.size : r.size) || 0;
                if (!room(size, inline)) { paintFiles(); return; }
                if (inline) {
                    cidSeq += 1;
                    var cid = 'img' + cidSeq;
                    files.push({ key: r.key, name: r.name || file.name, size: size,
                                 type: r.type || file.type || 'image/png', inline: true, cid: cid });
                    insertHtml('<img src="' + esc(r.url || '') + '" data-key="' + esc(r.key)
                        + '" data-cid="' + esc(cid) + '" alt="' + esc(r.name || file.name) + '">');
                } else {
                    files.push({ key: r.key, name: r.name || file.name, size: size,
                                 type: r.type || file.type || 'application/octet-stream',
                                 inline: false, cid: '' });
                }
                paintFiles();
                if (typeof opts.onChange === 'function') opts.onChange();
            }).catch(function (e) {
                paintFiles();
                say(e && e.message ? e.message : 'The upload failed.');
            });
        }
        function addAttachment(f) {
            if (!f || !f.key) return false;
            if (files.some(function (x) { return x.key === f.key; })) return false;
            var size = Number(f.size) || 0;
            if (!room(size, false)) return false;
            files.push({ key: f.key, name: f.name || 'file', size: size,
                         type: f.type || 'application/octet-stream', inline: false, cid: '' });
            paintFiles();
            if (typeof opts.onChange === 'function') opts.onChange();
            return true;
        }
        function removeAttachment(key) {
            files = files.filter(function (f) { return f.key !== key; });
            Array.prototype.forEach.call(area.querySelectorAll('img[data-key]'), function (img) {
                if (img.getAttribute('data-key') === key) img.remove();
            });
            paintFiles();
            if (typeof opts.onChange === 'function') opts.onChange();
        }

        /* ---- keyboard and paste ------------------------------------- */
        area.addEventListener('keydown', function (e) {
            if (!(e.metaKey || e.ctrlKey) || e.shiftKey || e.altKey) return;
            var k = (e.key || '').toLowerCase();
            if (k === 'b') { e.preventDefault(); cmd('bold'); }
            else if (k === 'i') { e.preventDefault(); cmd('italic'); }
            else if (k === 'u') { e.preventDefault(); cmd('underline'); }
            else if (k === 'k') {
                e.preventDefault();
                saveSel();
                var link = bar.querySelector('[data-cmd=link]');
                if (link) link.click();
            }
        });
        area.addEventListener('paste', function (e) {
            var cd = e.clipboardData;
            if (!cd) return;
            var imgs = Array.prototype.filter.call(cd.files || [], function (f) {
                return /^image\//.test(f.type || '');
            });
            if (imgs.length && typeof opts.upload === 'function') {
                /* A screenshot off the clipboard is an upload like any other:
                   it goes to our bucket and comes back as a key, never into the
                   message as a data URL that no sanitiser would let out. */
                e.preventDefault();
                saveSel();
                imgs.reduce(function (chain, f) {
                    return chain.then(function () { return take(f, true); });
                }, Promise.resolve());
                return;
            }
            var html = cd.getData('text/html');
            if (!html) return;                       /* plain text needs no help */
            e.preventDefault();
            document.execCommand('insertHTML', false, cleanHtml(html, mine));
            saveSel();
            changed();
        });
        area.addEventListener('input', changed);
        area.addEventListener('blur', saveSel);
        /* Every way a caret can move, including the ones a keyup never sees.
           These two are on the document because that is where the events are,
           so each one lets go the first time it fires after its composer has
           left the page: a modal that opens forty times a day must not leave
           forty listeners holding forty editors behind it. */
        function onSelectionChange() {
            if (!area.isConnected) {
                document.removeEventListener('selectionchange', onSelectionChange);
                return;
            }
            saveSel();
        }
        function onDocMouseDown(e) {
            if (!area.isConnected) {
                document.removeEventListener('mousedown', onDocMouseDown);
                return;
            }
            if (pop && !pop.contains(e.target) && e.target !== colourBtn) { pop.remove(); pop = null; }
        }
        document.addEventListener('selectionchange', onSelectionChange);
        document.addEventListener('mousedown', onDocMouseDown);

        /* ---- what the page reads off it ----------------------------- */
        function getHtml() {
            /* Our images become the content-ids the server will resolve to
               parts. Everything else goes through the cleaner one last time
               with no key allowed, so a preview URL can never leave.

               The rewrite happens in a parsed copy, never on live elements:
               setting src on a real <img>, even a detached one, makes the
               browser go and fetch it, and "cid:img1" is not a URL it can
               fetch. A parsed document has no browsing context and loads
               nothing. */
            var clone = new DOMParser()
                .parseFromString('<body>' + area.innerHTML + '</body>', 'text/html').body;
            Array.prototype.forEach.call(clone.querySelectorAll('img[data-key]'), function (img) {
                var cid = img.getAttribute('data-cid') || '';
                if (!cid) { img.remove(); return; }
                img.setAttribute('src', 'cid:' + cid);
                img.removeAttribute('data-key');
                img.removeAttribute('data-cid');
            });
            return cleanHtml(clone.innerHTML);
        }
        function getText() {
            /* What a person would read off the screen, which is what belongs on
               the clipboard and what a re-draft should be steered by. innerText
               respects the line breaks the layout actually shows, where
               textContent runs every paragraph together. */
            return area.innerText.replace(/\n{3,}/g, '\n\n').trim();
        }
        function setHtml(html) {
            area.innerHTML = cleanHtml(html || '', mine);
            changed();
        }
        /* Plain text becomes paragraphs, which is what a saved reply, a Claude
           draft and an order line all are: blank lines separate them, single
           ones break. */
        function paras(text) {
            return String(text == null ? '' : text).split(/\n\n+/)
                .filter(function (p) { return p.trim(); })
                .map(function (p) { return '<p>' + esc(p).replace(/\n/g, '<br>') + '</p>'; })
                .join('');
        }
        function insertText(text) {
            var html = paras(text);
            if (!html) return;
            insertHtml(html);
        }
        function appendText(text) {
            /* At the end, as its own paragraph. Inserting at the caret instead
               welds the line onto whatever sentence the caret was sitting in,
               which is what "put this in the reply" must never do. */
            var html = paras(text);
            if (!html) return;
            area.insertAdjacentHTML('beforeend', html);
            area.focus();
            caretToEnd();
            changed();
        }

        wrap.append(bar, area, chips, meter, note, fileInput);
        host.append(wrap);
        try {
            /* <font> and <p> rather than styled spans and divs: the same tags
               the server's allowlist keeps, so nothing is stripped on the way
               out that was visible on the way in. */
            document.execCommand('styleWithCSS', false, false);
            document.execCommand('defaultParagraphSeparator', false, 'p');
        } catch (e) { /* older engines simply keep their own defaults */ }
        changed();

        return {
            getHtml: getHtml,
            getText: getText,
            setHtml: setHtml,
            insertText: insertText,
            appendText: appendText,
            attachments: function () { return files.slice(); },
            addAttachment: addAttachment,
            removeAttachment: removeAttachment,
            focus: function () { area.focus(); },
            el: wrap
        };
    }

    window.mountComposer = mountComposer;
})();
