        /* ---------- widget layout (pure) ---------- */
        /* The arithmetic behind the widget grid, ported from the React component
           Cameron supplied (draggable-widget-grid.tsx) with the React taken out.
           An arrangement is an order of {id, size} plus a column count: wgLayout
           turns it into placements {id, col, row, w, h}, and while a card is held
           wgCandidates lists the orders one move away and wgChoose picks one.
           Nothing between these two marker lines reads or writes the page, so
           tests/test_frontend.py lifts the block out and runs it under node.
           Four changes from the component: sizes are sm (one column), wide
           (two) and full (every column), all one row high, because gizmo's rows
           are as tall as their content and a two row card would need a row
           height nobody knows; the layout keeps the order it is given instead of
           tiling, for the reason given at wgLayout; slot rectangles come from
           wgSlotFor, which reads row edges from the rendered rows instead of
           assuming square cells; and a group swap must put the card where it
           claims, for the reason given there. */
        const WG_SPANS = { sm: { col: 1, row: 1 }, wide: { col: 2, row: 1 }, full: { col: Infinity, row: 1 } };
        const wgOverlaps = (a, b) => a.col < b.col + b.w && b.col < a.col + a.w && a.row < b.row + b.h && b.row < a.row + a.h;
        const wgContains = (outer, inner) => inner.col >= outer.col && inner.row >= outer.row
            && inner.col + inner.w <= outer.col + outer.w && inner.row + inner.h <= outer.row + outer.h;
        // A size nobody set, or one that is not in the table, spans the row, which is where a plain block sits outside the grid.
        function wgSpanOf(item, columns) {
            const span = Object.prototype.hasOwnProperty.call(WG_SPANS, item.size) ? WG_SPANS[item.size] : WG_SPANS.full;
            return { w: Math.min(span.col, columns), h: span.row };
        }
        /* Cards in the order given, left to right, one after another; a card
           that does not fit the rest of its row starts the next one. This is
           where gizmo parts from the component, whose tiler seated a later card
           before an earlier one to close a hole and widened cards when it could
           not. gizmo's pages read top to bottom and most of their cards span
           the row, so closing a hole meant moving a whole report: with nine or
           ten KPI tiles on the Overview the tiler pulled Sales by sector up
           between them, and a card dropped between two reports jumped to the
           foot of the page. Here a card is exactly where it was put, a short
           row keeps its gap as the old tile grid did, and the placement is the
           one the browser's own grid auto-placement gives for the same order
           and spans, so the arithmetic and the page cannot disagree. */
        function wgLayout(items, columns) {
            if (columns < 1 || items.length === 0) return [];
            const out = [];
            let row = 0, col = 0;
            items.forEach(item => {
                const { w, h } = wgSpanOf(item, columns);
                if (col > 0 && col + w > columns) { row += 1; col = 0; }
                out.push({ id: item.id, col, row, w, h });
                col += w;
                if (col >= columns) { row += 1; col = 0; }
            });
            return out;
        }
        function wgMoveTo(items, id, index) {
            const from = items.findIndex(item => item.id === id);
            if (from < 0 || from === index || index < 0 || index >= items.length) return items;
            const next = [...items];
            const [moved] = next.splice(from, 1);
            next.splice(index, 0, moved);
            return next;
        }
        const wgSameOrder = (a, b) => a.length === b.length && a.every((item, i) => item.id === b[i].id);
        /* A candidate is measured to its slot shrunk by this fraction on every
           side, and the held card's own slot is measured whole. The difference
           is a dead band: a pointer trembling on the line between two slots
           stays with the slot the card is in, instead of flicking the cards
           back and forth every frame. It also means each adopted move leaves
           the card's slot strictly nearer the pointer, so a still pointer can
           never walk it round a circle of orders. */
        const WG_ENTER = 0.18;
        function wgChoose(home, candidates, cx, cy) {
            const distance = (s, inset) => {
                const ix = (s.right - s.left) * inset, iy = (s.bottom - s.top) * inset;
                const dx = Math.max(s.left + ix - cx, 0, cx - (s.right - ix));
                const dy = Math.max(s.top + iy - cy, 0, cy - (s.bottom - iy));
                return Math.hypot(dx, dy);
            };
            const toCentre = s => Math.hypot((s.left + s.right) / 2 - cx, (s.top + s.bottom) / 2 - cy);
            let best = distance(home, 0);
            if (best === 0) return null;
            let pick = null, bestCentre = Infinity;
            for (const { order, slot } of candidates) {
                const d = distance(slot, WG_ENTER);
                const c = toCentre(slot);
                // On a tie the earlier candidate wins, and group swaps are listed first.
                if (d < best || (d === best && pick && c < bestCentre)) {
                    best = d;
                    bestCentre = c;
                    pick = order;
                }
            }
            return pick;
        }
        /* Every order one move away from items, each with the slot the held card
           would take. Group swaps come first: an area of the card's own shape
           filled entirely by smaller cards trades places with it, and those cards
           keep their arrangement. Then sequence moves: the card at every other
           index. toSlot turns a box into a rectangle, normally wgSlotFor. */
        function wgCandidates(items, id, columns, toSlot) {
            const places = wgLayout(items, columns);
            const me = places.find(p => p.id === id);
            if (!me) return [];
            const byId = new Map(items.map(item => [item.id, item]));
            const rows = Math.max(...places.map(p => p.row + p.h));
            const out = [];
            for (let row = 0; row + me.h <= rows; row++) {
                for (let col = 0; col + me.w <= columns; col++) {
                    const area = { col, row, w: me.w, h: me.h };
                    if (wgOverlaps(area, me)) continue;
                    const group = places.filter(p => wgOverlaps(p, area));
                    if (group.length < 2 || !group.every(p => wgContains(area, p))) continue;
                    /* The component stopped at the check above, so an area reaching into
                       the empty end of a short last row passed with a hole in it. Its
                       order then laid out with the card somewhere else, and the chooser
                       picked that same unreachable slot every frame. A group has to
                       fill the area, which is what the component's own comment says. */
                    if (group.reduce((n, p) => n + p.w * p.h, 0) !== area.w * area.h) continue;
                    const moved = places.map(p => p.id === id
                        ? Object.assign({}, p, { col, row })
                        : group.includes(p)
                            ? Object.assign({}, p, { col: p.col - col + me.col, row: p.row - row + me.row })
                            : p);
                    moved.sort((a, b) => a.row - b.row || a.col - b.col);
                    const order = moved.map(p => byId.get(p.id));
                    /* Laid out again, the order must seat the card in the area it
                       traded for. A swap that changes where a row breaks would
                       otherwise steer the chooser by a slot the card never takes. */
                    const lands = wgLayout(order, columns).find(p => p.id === id);
                    if (!lands || lands.col !== col || lands.row !== row) continue;
                    out.push({ order, slot: toSlot(area) });
                }
            }
            const from = items.findIndex(item => item.id === id);
            for (let i = 0; i < items.length; i++) {
                if (i === from) continue;
                const order = wgMoveTo(items, id, i);
                const p = wgLayout(order, columns).find(q => q.id === id);
                if (p) out.push({ order, slot: toSlot(p) });
            }
            return out;
        }
        /* A saved layout against what rendered. Saved ids that did not render
           are dropped, and so is a repeat of one. An id the saved order never
           mentions is a card added since it was saved, so it goes in at its
           default index: it appears where it would for someone who never
           customized, and an old Overview order of KPI tiles leaves every other
           block where it always was. The order holds every default id exactly
           once, hidden ones included; the caller takes hidden ones off the page. */
        function wgMergeOrder(defaultIds, saved) {
            const known = new Set(defaultIds);
            const keep = (list) => {
                const seen = new Set();
                return (Array.isArray(list) ? list : []).filter(id => {
                    if (!known.has(id) || seen.has(id)) return false;
                    seen.add(id);
                    return true;
                });
            };
            const src = saved && typeof saved === 'object' ? saved : {};
            const order = keep(src.order);
            const placed = new Set(order);
            defaultIds.forEach((id, i) => {
                if (placed.has(id)) return;
                order.splice(Math.min(i, order.length), 0, id);
                placed.add(id);
            });
            return { order, hidden: keep(src.hidden) };
        }
        // Alt with an arrow: one place later or earlier, stopping at either end rather than wrapping.
        function wgKeyMove(items, id, delta) {
            const from = items.findIndex(item => item.id === id);
            if (from < 0) return items;
            return wgMoveTo(items, id, Math.max(0, Math.min(items.length - 1, from + delta)));
        }
        /* One column on a phone, at the same 640px the .ov-wrap padding switches
           at. Otherwise four when four cells of --wgrid-cell fit the content
           column, and two when they do not: never three, where a wide card would
           be two thirds of the row. */
        /* Two on a phone, not one: a KPI tile is a label and a figure, and
           the Overview's seven stacked one per row cost 1,237px, a screen and
           a half, before the first chart. A wide or full card still takes the
           row, so only the small tiles pair up. */
        function wgColumns(contentWidth, viewportWidth, cell) {
            if (viewportWidth <= 640) return 2;
            return contentWidth < 4 * cell ? 2 : 4;
        }
        /* The rectangle a box would occupy. Columns are equal, so their edges
           follow from the grid's width; rows are as tall as their content, so
           their edges are read from the rendered rows, g.rowTops and
           g.rowBottoms. A row below the last rendered one (a wide card pushed
           onto a new row) takes the last row's height, one gap further down.
           With no rendered rows at all there is nothing to copy, so a row is
           taken as one column unit tall starting at g.top, or 0. */
        function wgSlotFor(box, g) {
            const unit = (g.width - g.gap * (g.columns - 1)) / g.columns;
            const tops = g.rowTops || [], bottoms = g.rowBottoms || [];
            const known = Math.min(tops.length, bottoms.length);
            const edges = (r) => {
                if (r < known) return { top: tops[r], bottom: bottoms[r] };
                const height = known ? bottoms[known - 1] - tops[known - 1] : unit;
                const first = known ? bottoms[known - 1] + g.gap : (g.top || 0);
                const top = first + (r - known) * (height + g.gap);
                return { top, bottom: top + height };
            };
            const left = g.left + box.col * (unit + g.gap);
            return {
                left,
                top: edges(box.row).top,
                right: left + box.w * (unit + g.gap) - g.gap,
                bottom: edges(box.row + box.h - 1).bottom,
            };
        }
        // The id pattern the server holds a saved layout to, so a card the page names can always be saved.
        const WG_ID = /^[a-z0-9][a-z0-9-]{0,47}$/;
        /* An Overview KPI tile's id, from its label, since the tiles come from
           whatever list the server sends and carry no id of their own. A
           bracketed threshold goes first: "Low stock (≤5)" carries
           LOW_STOCK_THRESHOLD, and a saved layout must not lose the tile the
           day that setting changes. The rest is lower case with every run of
           other characters one hyphen, cut to the 48 the pattern allows. */
        function wgKpiId(label) {
            const bare = String(label == null ? '' : label)
                .replace(/\(\s*(?:≤|≥|<=|>=|<|>)\s*[\d.,]+\s*\)/g, ' ');
            const slug = bare.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
            return ('kpi-' + slug).slice(0, 48).replace(/-+$/, '');
        }
        /* ---------- widget layout end ---------- */
        /* ---------- widget grid (page layer) ---------- */
        /* The one place a view's cards are arranged and customized. A renderer
           marks its blocks with widget() and appends them in its own default
           order; it never calls anything here. One MutationObserver per content
           root runs wgArrange after a renderer changes the root, so a screen
           added next year is arranged without anyone wiring it. The arrangement
           is DOM order plus data-cols and data-span, never an inline style, so
           reading order, tab order and screen reader order are the order you
           see, and print can overrule it. The arithmetic is the pure block
           above; the design is docs/superpowers/specs/2026-09-17-draggable-widget-grid-design.md. */
        const APP_VIEWS = ['overview', 'seo', 'keywords', 'products', 'customers', 'liability', 'recon', 'forecast', 'connector', 'crm', 'loans', 'mail', 'files', 'team', 'labels', 'sizes', 'memory', 'skills', 'chat', 'guide'];
        // Chat is a log and a composer, not a page of cards, which is also why the server's LAYOUT_VIEWS leaves it out.
        const WG_VIEWS = APP_VIEWS.filter(v => v !== 'chat');
        // Overview is the one content root not named after its view.
        const wgRoot = (view) => $(view === 'overview' ? 'ov-content' : view + '-content');
        /* Marks a block as a card the layer may move: an id chosen by what the
           card is (trends, sectors, never card-3), a size (sm, wide, or full
           when left out) and, for a block with no card title of its own, the
           name menus and announcements use. Returns the node, so a renderer
           appends it in the same expression. */
        function widget(node, id, size, label) {
            node.setAttribute('data-widget', id);
            if (size && size !== 'full') node.setAttribute('data-size', size);
            if (label) node.setAttribute('data-widget-label', label);
            return node;
        }
        /* The signed-in person's layouts: null until the server answers, false
           when it could not, else {view: {order, hidden}}. */
        let wgLayouts = null;
        /* The view being customized, its draft and the layout it had when
           Customize was pressed. One view at a time: leaving a view ends it. */
        let wgEdit = null;
        let wgDrag = null;
        const wgWatchers = {};
        const wgDefaults = {};          // view -> ids in the order the renderer appended them
        const wgSeq = {};               // view -> Map(id -> when that id was first appended)
        let wgSeqNext = 0;
        const wgSeen = new WeakSet();   // nodes the layer has already counted
        const wgWarned = new WeakSet();
        const wgOrig = new WeakMap();   // card -> the attributes Customize mode overwrote on it
        const wgInert = new WeakSet();  // children Customize mode made inert, and only those
        const wgMotion = new WeakMap(); // card -> its running slide, cancelled by the next one
        let wgEatClicksUntil = 0;
        const WG_ARIA = ['role', 'tabindex', 'aria-label', 'aria-posinset', 'aria-setsize', 'aria-haspopup'];
        /* The gesture's own thresholds rather than design tokens, since nothing
           is drawn at these sizes: how far a mouse travels before a press is a
           drag (so a plain click never flashes a lift), how long a finger holds
           before a card lifts and how far it may wander first (further is a
           scroll), the least time between two reorders, the buzz on a lift, and
           how long the click that follows a drop is ignored. */
        const WG_MOUSE_SLOP = 3, WG_TOUCH_SLOP = 8, WG_HOLD_MS = 350, WG_STEP_MS = 40, WG_BUZZ_MS = 10, WG_EAT_CLICK_MS = 300;
        /* Carrying a card past the fold: how deep the band at the top and the
           bottom of the view's scroller is, how fast the page scrolls with the
           pointer at the very edge (pixels a second, eased in from nothing at
           the band's inner line), how often a pointer held still in the band
           steps it, and how often it steps instead when motion is reduced, so
           the page moves in a few jumps rather than a glide. */
        const WG_SCROLL_EDGE = 56, WG_SCROLL_MAX = 1200, WG_SCROLL_TICK_MS = 16, WG_SCROLL_JUMP_MS = 200;
        // The server's LAYOUT_MAX_IDS: a longer list is refused whole.
        const WG_MAX_IDS = 64;
        const wgAttr = (n, name, value) => {
            if (value == null) { if (n.hasAttribute(name)) n.removeAttribute(name); }
            else if (n.getAttribute(name) !== value) n.setAttribute(name, value);
        };
        const wgHid = new WeakSet();    // cards the layer hid because the person's layout hides them
        /* A card its renderer is not showing: a holder with nothing in it yet
           (the trade radar before its answer, Top products when fewer than two
           earned), or one the renderer set to display none. That is not the
           person's choice, so it is left out of the arrangement and out of the
           Customize list without joining their hidden list, and it is laid
           out again the moment it fills (see wgWatch). */
        function wgAbsent(n) {
            return n.matches(':empty') || (!wgHid.has(n) && getComputedStyle(n).display === 'none');
        }
        const wgShown = (root) => [...root.children].filter(n => n.hasAttribute('data-widget') && !n.hidden && !wgAbsent(n));
        // The ids a person could show or hide today: every card that rendered, less those its renderer has not filled.
        const wgOnPage = (root) => new Set([...root.children].filter(n => n.hasAttribute('data-widget') && !wgAbsent(n)).map(n => n.getAttribute('data-widget')));
        const wgItems = (root) => wgShown(root).map(n => ({ id: n.getAttribute('data-widget'), size: n.getAttribute('data-size') || 'full' }));
        /* A card's name in menus and announcements: its own card title, the
           label its renderer gave it, its first heading, or its id. */
        function wgName(n) {
            const text = (x) => (x ? x.textContent : '').replace(/\s+/g, ' ').trim();
            const title = text(n.querySelector(':scope > .card-head .card-title'));
            if (title) return title;
            if (n.getAttribute('data-widget-label')) return n.getAttribute('data-widget-label');
            return text(n.querySelector('h2, h3, h4, .section-title, .ct')) || n.getAttribute('data-widget');
        }
        function wgSay(text) {
            const region = $('wg-status');
            if (!region) return;
            // A live region speaks only when its text changes, and the same move twice is still news.
            region.textContent = region.textContent === text ? text + '\u00a0' : text;
        }
        function wgWatch(view) {
            if (wgWatchers[view]) return wgWatchers[view];
            const root = wgRoot(view);
            if (!root) return null;
            const w = { root, width: -1 };
            w.mo = new MutationObserver(() => {
                // A render during a drag replaces the cards under the pointer: the drag ends and the draft goes onto the new ones.
                if (wgDrag && wgDrag.view === view) wgDragEnd(false);
                wgArrange(view);
            });
            w.mo.observe(root, { childList: true });
            /* A holder fills after the root has changed (paintRadar lands when
               its request answers, Products redraws Top products on every
               search), which the root's own childList never sees. So every
               card is watched here too, its own children and the attributes
               that can hide it, and the view is arranged again only when a
               card starts or stops being shown: a chart repainting inside its
               card, or the held card's translate, changes nothing here. This
               stays in the layer rather than in each renderer, for the same
               reason the root is watched: a holder added next year is covered. */
            w.absent = new Set();
            w.fill = new MutationObserver((records) => {
                if (records.some(r => r.target.parentNode === root && wgAbsent(r.target) !== w.absent.has(r.target))) wgArrange(view);
            });
            /* Columns follow the content column, so the sidebar folding counts
               as a resize. A change of height alone (every render) is not one. */
            if (typeof ResizeObserver === 'function') {
                w.ro = new ResizeObserver(() => {
                    if (root.clientWidth === w.width) return;
                    w.width = root.clientWidth;
                    wgArrange(view);
                });
                w.ro.observe(root);
            }
            root.addEventListener('pointerdown', (e) => wgPointerDown(view, e));
            root.addEventListener('click', (e) => wgSwallowClick(view, e), true);
            root.addEventListener('keydown', (e) => wgKey(view, e), true);
            // A long press is how a finger lifts a card, so it must not also open the browser's own menu.
            root.addEventListener('contextmenu', (e) => { if (wgDrag && wgDrag.view === view) e.preventDefault(); });
            wgWatchers[view] = w;
            return w;
        }
        /* The default order is the order the renderer appended its cards in,
           which after the first arrangement is no longer the DOM order. So each
           id is stamped the first time it is seen: a render that replaces every
           card starts the stamps again, a card appended later in the same render
           goes after the rest, and a card swapped for a new node with the same
           id keeps its place. */
        function wgNoteDefaults(view, widgets, ids) {
            const seq = wgSeq[view] || (wgSeq[view] = new Map());
            if (!widgets.some(n => wgSeen.has(n))) seq.clear();
            widgets.forEach((n, i) => {
                if (wgSeen.has(n)) return;
                wgSeen.add(n);
                if (!seq.has(ids[i])) seq.set(ids[i], wgSeqNext++);
            });
            wgDefaults[view] = ids.slice().sort((a, b) => seq.get(a) - seq.get(b));
        }
        function wgColumnsFor(root) {
            // A view that is not showing has no width to measure; setView arranges it again the moment it shows.
            if (!root.getClientRects().length) return +root.getAttribute('data-cols') || 4;
            const cs = getComputedStyle(root);
            const width = root.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
            return wgColumns(width, window.innerWidth, tokenNum('--wgrid-cell'));
        }
        /* Idempotent: it compares what is on the page with what should be and
           writes nothing when they match, so a renderer that builds a page in
           several steps gets several cheap passes. */
        function wgArrange(view) {
            const w = wgWatch(view);
            if (!w) return;
            const root = w.root;
            const kids = [...root.children];
            const widgets = kids.filter(n => n.hasAttribute('data-widget'));
            const ids = widgets.map(n => n.getAttribute('data-widget'));
            wgNoteDefaults(view, widgets, ids);
            const first = kids.indexOf(widgets[0]), last = kids.indexOf(widgets[widgets.length - 1]);
            /* A block with no id is fixed, and a fixed block can only lead or
               trail: one between two cards would have to move with them, and
               nothing says where it belongs. */
            const stray = widgets.length ? kids.slice(first, last + 1).find(n => !n.hasAttribute('data-widget')) : null;
            const twice = widgets.find((n, i) => ids.indexOf(ids[i]) !== i);
            if (stray && !wgWarned.has(stray)) { wgWarned.add(stray); console.warn('[widgets] ' + view + ': block without an id', stray); }
            if (twice && !wgWarned.has(twice)) { wgWarned.add(twice); console.warn('[widgets] ' + view + ': the id ' + twice.getAttribute('data-widget') + ' is used twice', twice); }
            // Observing a card again only renews its options, so this is cheap on every pass.
            widgets.forEach(n => w.fill.observe(n, { childList: true, attributes: true, attributeFilter: ['hidden', 'class', 'style'] }));
            w.absent = new Set(widgets.filter(wgAbsent));
            const absent = new Set([...w.absent].map(n => n.getAttribute('data-widget')));
            if (widgets.length - w.absent.size < 2 || stray || twice) {
                if (wgDrag && wgDrag.view === view) wgDragEnd(false);
                if (root.classList.contains('wgrid')) root.classList.remove('wgrid');
                wgAttr(root, 'data-cols', null);
                widgets.forEach(n => wgAttr(n, 'data-span', null));
                wgUndecorate(root);
                wgControls(view, root, false);
                return;
            }
            if (!root.classList.contains('wgrid')) root.classList.add('wgrid');
            const editing = !!(wgEdit && wgEdit.view === view);
            const merged = wgMergeOrder(wgDefaults[view], editing ? wgEdit.draft : (wgLayouts && wgLayouts[view]));
            const present = merged.order.filter(id => !absent.has(id));
            let hidden = new Set(merged.hidden.filter(id => !absent.has(id)));
            // A saved layout that hides every card that rendered today would leave a page of nothing, so it hides none.
            if (present.every(id => hidden.has(id))) hidden = new Set();
            const byId = new Map(widgets.map((n, i) => [ids[i], n]));
            const cols = wgColumnsFor(root);
            const places = wgLayout(present.filter(id => !hidden.has(id))
                .map(id => ({ id, size: byId.get(id).getAttribute('data-size') || 'full' })), cols)
                .sort((a, b) => a.row - b.row || a.col - b.col);
            const shown = places.map(p => byId.get(p.id));
            // Cards off the page, hidden or not yet filled, wait after the shown ones in their merged order.
            const want = kids.slice(0, first).concat(shown,
                merged.order.filter(id => hidden.has(id) || absent.has(id)).map(id => byId.get(id)), kids.slice(last + 1));
            wgAttr(root, 'data-cols', String(cols));
            places.forEach(p => {
                const n = byId.get(p.id);
                wgAttr(n, 'data-span', p.w === cols ? 'full' : String(p.w));
                if (wgHid.has(n)) { wgHid.delete(n); n.hidden = false; }
            });
            absent.forEach(id => wgAttr(byId.get(id), 'data-span', null));
            hidden.forEach(id => { const n = byId.get(id); wgAttr(n, 'data-span', null); wgHid.add(n); if (!n.hidden) n.hidden = true; });
            if (want.some((n, i) => kids[i] !== n)) {
                // Moving its own nodes is not a render, so the observer is off while it does.
                w.mo.disconnect();
                want.forEach((n, i) => { if (root.children[i] !== n) root.insertBefore(n, root.children[i] || null); });
                w.mo.observe(root, { childList: true });
            }
            if (editing) wgDecorate(view, root, shown, widgets);
            else wgUndecorate(root);
            wgControls(view, root, true);
        }
        /* Customize and its three companions live in the page header's action
           group, beside Refresh: absent when the view has nothing to arrange or
           is showing its run gate. */
        function wgControls(view, root, qualifies) {
            const act = root.querySelector(':scope > .ov-hero .ov-hero-act');
            root.querySelectorAll('[data-wg-control]').forEach(b => { if (b.parentNode !== act) b.remove(); });
            if (!act) return;
            if (!qualifies || root.querySelector(':scope > .run-gate')) {
                act.querySelectorAll('[data-wg-control]').forEach(b => b.remove());
                return;
            }
            const editing = !!(wgEdit && wgEdit.view === view);
            const button = (key, cls, onClick) => {
                let b = act.querySelector('[data-wg-control="' + key + '"]');
                if (!b) {
                    b = el('button', cls); b.type = 'button';
                    b.setAttribute('data-wg-control', key);
                    b.onclick = onClick;
                }
                return b;
            };
            const label = (b, text, icon) => {
                if (b.dataset.wgText === text) return;
                b.textContent = '';
                if (icon) b.append(ico(icon));
                b.append(el('span', 'wg-txt', text));
                b.dataset.wgText = text;
            };
            const want = [];
            if (editing) {
                const rendered = wgOnPage(root);
                const n = wgEdit.draft.hidden.filter(id => rendered.has(id)).length;
                if (n) {
                    const more = button('hidden', 'btn btn-sm', () => wgShowHiddenMenu(view, more));
                    label(more, 'Show hidden (' + n + ')');
                    want.push(more);
                }
                const reset = button('reset', 'btn btn-sm', () => wgReset(view));
                label(reset, 'Reset');
                const done = button('done', 'btn btn-sm btn-primary', () => wgCommit(view, false));
                label(done, 'Done');
                if (!!wgEdit.saving !== done.hasAttribute('aria-busy')) setBusy(done, !!wgEdit.saving);
                want.push(reset, done);
            } else {
                const cust = button('customize', 'btn btn-sm', () => wgToggle(view));
                cust.setAttribute('data-wg-customize', '');
                wgAttr(cust, 'aria-pressed', 'false');
                label(cust, 'Customise', I.settings);
                cust.setAttribute('aria-label', 'Customise');
                const off = wgLayouts === false ? 'Layouts are unavailable right now' : wgLayouts === null ? 'Loading your layout' : null;
                if (cust.disabled !== !!off) cust.disabled = !!off;
                wgAttr(cust, 'title', off);
                want.push(cust);
            }
            act.querySelectorAll('[data-wg-control]').forEach(b => { if (want.indexOf(b) < 0) b.remove(); });
            /* Put in order from the last one back, so a button already in place
               is never moved: moving a focused button would drop its focus. */
            const tail = want[want.length - 1];
            if (tail.parentNode !== act || (tail.nextElementSibling && tail.nextElementSibling.hasAttribute('data-wg-control'))) act.append(tail);
            for (let i = want.length - 2; i >= 0; i--) {
                if (want[i].nextElementSibling !== want[i + 1]) act.insertBefore(want[i], want[i + 1]);
            }
        }
        /* The mode's marks on a view that is arranged: a list of cards, each
           focusable, named and hideable, with everything inside it inert so no
           link, button, chart hover or inner drag answers while cards are being
           moved. Re-applied after a render, because a render brings new nodes. */
        function wgDecorate(view, root, shown, widgets) {
            const hint = $('wg-hint');
            if (hint && hint.hidden) hint.hidden = false;
            if (!root.classList.contains('wg-editing')) root.classList.add('wg-editing');
            wgAttr(root, 'role', 'list');
            wgAttr(root, 'aria-describedby', 'wg-hint');
            widgets.forEach(n => {
                if (!wgOrig.has(n)) wgOrig.set(n, WG_ARIA.map(a => [a, n.getAttribute(a)]));
                const at = shown.indexOf(n);
                if (at < 0) { wgOrig.get(n).forEach(([a, v]) => wgAttr(n, a, v)); return; }
                const name = wgName(n);
                wgAttr(n, 'role', 'listitem');
                wgAttr(n, 'tabindex', '0');
                wgAttr(n, 'aria-label', name);
                wgAttr(n, 'aria-posinset', String(at + 1));
                wgAttr(n, 'aria-setsize', String(shown.length));
                wgAttr(n, 'aria-haspopup', null);
                [...n.children].forEach(c => {
                    if (c.classList.contains('wg-hide') || c.classList.contains('wg-grip') || c.inert) return;
                    c.inert = true;
                    wgInert.add(c);
                });
                /* The hide control on the block's first line, an eye-off (12 Oct
                   2026, WS-60), and a grip in the gutter saying where to take
                   hold. A block with no heading took a band to hold a bare x. */
                let x = n.querySelector(':scope > .wg-hide');
                if (!x) {
                    x = el('button', 'icon-btn wg-hide'); x.type = 'button';
                    x.append(ico(I.eyeOff));
                    x.onclick = () => wgHide(view, n);
                    n.append(x);
                }
                if (!n.querySelector(':scope > .wg-grip')) {
                    const g = el('span', 'wg-grip'); g.setAttribute('aria-hidden', 'true'); g.append(ico(I.gripVertical));
                    n.append(g);
                }
                wgAttr(x, 'aria-label', 'Hide ' + name);
                if (x.disabled !== (shown.length < 2)) x.disabled = shown.length < 2;
            });
        }
        function wgUndecorate(root) {
            if (!root.classList.contains('wg-editing')) return;
            root.classList.remove('wg-editing');
            if (root.getAttribute('role') === 'list') root.removeAttribute('role');
            if (root.getAttribute('aria-describedby') === 'wg-hint') root.removeAttribute('aria-describedby');
            [...root.children].forEach(n => {
                const orig = wgOrig.get(n);
                if (orig) { orig.forEach(([a, v]) => wgAttr(n, a, v)); wgOrig.delete(n); }
                n.querySelectorAll(':scope > .wg-hide').forEach(b => b.remove());
                n.querySelectorAll(':scope > .wg-grip').forEach(b => b.remove());
                [...n.children].forEach(c => { if (wgInert.has(c)) { c.inert = false; wgInert.delete(c); } });
                n.classList.remove('wg-held', 'wg-lifted', 'wg-landed');
            });
            const hint = $('wg-hint');
            if (hint && !document.querySelector('.ov-wrap.wg-editing')) hint.hidden = true;
        }
        /* In the mode a click inside a card is a drag that did not travel, and
           the click that follows a drop is part of the drop, wherever between
           the cards it lands. A click on the header's own buttons is neither. */
        function wgSwallowClick(view, e) {
            const eat = performance.now() < wgEatClicksUntil;
            if (!eat && !(wgEdit && wgEdit.view === view)) return;
            const t = e.target, card = t.closest ? t.closest('[data-widget]') : null;
            if (eat ? !card && t !== wgRoot(view) : !card || t.closest('.wg-hide')) return;
            e.preventDefault();
            e.stopPropagation();
        }
        function wgAnimate(n, frames) {
            const opts = { duration: tokenNum('--dur-layout') * 1000, easing: tokenValue('--ease-layout') };
            // A browser without linear() easing still gets the house curve rather than no slide at all.
            try { return n.animate(frames, opts); }
            catch (e) { try { return n.animate(frames, Object.assign(opts, { easing: tokenValue('--ease') })); } catch (e2) { return null; } }
        }
        /* FLIP: note where each card is, let apply() move them, then slide each
           from where it was to where it is now. A card still sliding from the
           last move is measured where it is on screen, so moves chain. The held
           card is skipped: it is under the pointer, not in its slot. */
        function wgFlip(root, apply, skip) {
            if (REDUCE_MOTION) { apply(); return; }
            const nodes = [...root.children].filter(n => n.hasAttribute('data-widget') && n !== skip);
            const before = new Map(nodes.map(n => [n, n.getBoundingClientRect()]));
            apply();
            nodes.forEach(n => {
                const running = wgMotion.get(n);
                if (running) { running.cancel(); wgMotion.delete(n); }
                const a = before.get(n);
                if (n.hidden || n.parentNode !== root || !a.width) return;
                const b = n.getBoundingClientRect();
                const dx = a.left - b.left, dy = a.top - b.top;
                if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return;
                const anim = wgAnimate(n, [{ transform: 'translate(' + dx + 'px, ' + dy + 'px)' }, { transform: 'none' }]);
                if (anim) wgMotion.set(n, anim);
            });
        }
        // The draft takes a new order of the shown cards; hidden ones keep their ids after them.
        function wgAdopt(view, items, skip) {
            const draft = wgEdit.draft;
            const ids = items.map(i => i.id);
            draft.order = ids.concat(draft.hidden.filter(id => ids.indexOf(id) < 0));
            wgFlip(wgRoot(view), () => wgArrange(view), skip);
        }
        function wgToggle(view) {
            if (wgEdit) { if (wgEdit.view === view) wgCommit(view, false); return; }
            if (!wgLayouts) return;
            const saved = wgLayouts[view];
            const merged = wgMergeOrder(wgDefaults[view] || [], saved);
            wgEdit = { view, draft: { order: merged.order, hidden: merged.hidden },
                       before: saved ? { order: (saved.order || []).slice(), hidden: (saved.hidden || []).slice() } : null };
            const root = wgRoot(view);
            const focused = document.activeElement && document.activeElement.hasAttribute('data-wg-customize');
            wgArrange(view);
            if (focused) { const done = root.querySelector('[data-wg-control="done"]'); if (done) done.focus(); }
        }
        function wgReset(view) {
            if (!wgEdit || wgEdit.view !== view || wgEdit.saving) return;
            wgEdit.draft = { order: (wgDefaults[view] || []).slice(), hidden: [] };
            wgFlip(wgRoot(view), () => wgArrange(view));
        }
        function wgHide(view, card) {
            if (!wgEdit || wgEdit.view !== view || wgEdit.saving) return;
            const root = wgRoot(view);
            const before = wgShown(root);
            // The last card on the page stays: its button is disabled, and this holds if something clicks it anyway.
            if (before.length < 2) return;
            const at = before.indexOf(card), name = wgName(card), id = card.getAttribute('data-widget');
            if (wgEdit.draft.hidden.indexOf(id) < 0) wgEdit.draft.hidden.push(id);
            wgFlip(root, () => wgArrange(view));
            const after = wgShown(root);
            const next = at >= 0 && at < after.length ? after[at] : root.querySelector('[data-wg-control="hidden"]');
            if (next) next.focus();
            wgSay(name + ' hidden');
        }
        function wgShowHiddenMenu(view, anchor) {
            if (!wgEdit || wgEdit.view !== view) return;
            const root = wgRoot(view);
            const rendered = wgOnPage(root);
            dropMenu(anchor, wgEdit.draft.hidden.filter(id => rendered.has(id)).map(id => {
                const n = [...root.children].find(c => c.getAttribute('data-widget') === id);
                return { label: n ? wgName(n) : id, onClick: () => wgUnhide(view, id) };
            }));
        }
        // A card brought back goes to its default index, where it would be for someone who never customized.
        function wgUnhide(view, id) {
            if (!wgEdit || wgEdit.view !== view || wgEdit.saving) return;
            const root = wgRoot(view), draft = wgEdit.draft;
            draft.hidden = draft.hidden.filter(x => x !== id);
            const ids = wgItems(root).map(i => i.id).filter(x => x !== id);
            ids.splice(Math.min(Math.max((wgDefaults[view] || []).indexOf(id), 0), ids.length), 0, id);
            draft.order = ids.concat(draft.hidden);
            wgFlip(root, () => wgArrange(view));
            const n = [...root.children].find(c => c.getAttribute('data-widget') === id);
            if (n) { n.focus(); wgSay(wgName(n) + ' shown'); }
        }
        /* What Done sends. A draft that lays out as the default with nothing
           hidden deletes the saved layout rather than saving a copy of the
           default. Otherwise the ids of a saved layout that did not render this
           time go back in at their saved index, so a card that is only there
           on some days (Open follow-ups) keeps its place through a customize
           on a day it was absent. */
        function wgBody(view, root) {
            const defaults = wgDefaults[view] || [];
            const draft = wgMergeOrder(defaults, wgEdit.draft);
            if (!draft.hidden.length && draft.order.join(' ') === defaults.join(' '))
                return { view, reset: true };
            const saved = (wgLayouts && wgLayouts[view]) || {};
            const rendered = new Set(defaults);
            const order = draft.order.slice(), hidden = draft.hidden.slice();
            (Array.isArray(saved.order) ? saved.order : []).forEach((id, i) => {
                if (rendered.has(id) || order.indexOf(id) >= 0 || !WG_ID.test(id)) return;
                order.splice(Math.min(i, order.length), 0, id);
            });
            (Array.isArray(saved.hidden) ? saved.hidden : []).forEach(id => {
                if (!rendered.has(id) && hidden.indexOf(id) < 0 && WG_ID.test(id)) hidden.push(id);
            });
            return { view, order: order.slice(0, WG_MAX_IDS), hidden: hidden.slice(0, WG_MAX_IDS) };
        }
        /* Done writes before it leaves the mode, and a failed write is never
           shown as saved: the draft stays on screen to try again. Leaving the
           view is the other way in, and there a failure drops the draft, so
           the view opens on its last saved layout next time. */
        async function wgCommit(view, leaving) {
            const edit = wgEdit;
            if (!edit || edit.view !== view || edit.saving) return false;
            if (wgDrag) wgDragEnd(false);
            const root = wgRoot(view);
            /* A view that is not showing its cards has nothing to save: a product
               opened from the list, a run gate, a refresh half drawn. A draft laid
               against no cards reads as the default, and Done would delete the
               layout the person had. Leaving drops the draft instead; otherwise
               the mode waits for the cards to come back. */
            if (!root.classList.contains('wgrid')) {
                if (leaving && wgEdit === edit) wgEdit = null;
                return false;
            }
            const body = wgBody(view, root);
            edit.saving = true;
            wgControls(view, root, true);
            let d = null;
            try { d = await api('/api/layouts', body); } catch (e) { d = null; }
            edit.saving = false;
            const ok = !!(d && d.layouts && typeof d.layouts === 'object' && !Array.isArray(d.layouts));
            if (ok) wgLayouts = d.layouts;
            if (ok || leaving) {
                const focused = document.activeElement && document.activeElement.getAttribute('data-wg-control') === 'done';
                if (wgEdit === edit) wgEdit = null;
                wgArrange(view);
                if (focused) { const cust = root.querySelector('[data-wg-customize]'); if (cust) cust.focus(); }
            } else {
                wgArrange(view);
            }
            if (!ok) toastError(leaving ? 'Your layout was not saved' : 'Your layout was not saved. Try Done again.');
            return ok;
        }
        async function wgLoadLayouts() {
            let d = null;
            try { d = await api('/api/layouts', {}); } catch (e) { d = null; }
            wgLayouts = d && d.layouts && typeof d.layouts === 'object' && !Array.isArray(d.layouts) ? d.layouts : false;
            if (wgLayouts) await wgMigrateOverview();
            WG_VIEWS.forEach(v => { if (wgWatchers[v]) wgArrange(v); });
        }
        /* The Overview's KPI order used to live in this browser under
           sc_ov_layout_v1, by label. Once, when the account has no Overview
           layout of its own, it is carried over as kpi ids; the key goes only
           after the server has the layout, so a failed save is tried again on
           the next start rather than lost. */
        const OV_LAYOUT_KEY = 'sc_ov_layout_v1';
        // Set by claimLocalCache: until then the key may be the last person's, who signed in on this browser before.
        let wgOwnerKnown = false, wgMigrating = false;
        async function wgMigrateOverview() {
            if (!wgLayouts || wgLayouts.overview || !wgOwnerKnown || wgMigrating) return;
            let old = null;
            try { old = JSON.parse(localStorage.getItem(OV_LAYOUT_KEY) || 'null'); } catch (e) { return; }
            if (!old || typeof old !== 'object') return;
            const ids = (list) => [...new Set((Array.isArray(list) ? list : []).map(wgKpiId))].filter(id => WG_ID.test(id)).slice(0, WG_MAX_IDS);
            const layout = { order: ids(old.order), hidden: ids(old.hidden) };
            if (layout.order.length || layout.hidden.length) {
                wgMigrating = true;
                let d = null;
                try { d = await api('/api/layouts', Object.assign({ view: 'overview' }, layout)); } catch (e) { d = null; }
                wgMigrating = false;
                if (!d || !d.layouts || typeof d.layouts !== 'object') return;
                wgLayouts = d.layouts;
            }
            try { localStorage.removeItem(OV_LAYOUT_KEY); } catch (e) {}
            wgArrange('overview');
        }
        /* ----- dragging -----
           Pointer events, because HTML5 drag never fires from touch and draws
           a ghost instead of moving the card. The move, up, cancel and Escape
           listeners go on window: moving the held card in the DOM would
           release a pointer capture set on the card. */
        function wgPointerDown(view, e) {
            if (!wgEdit || wgEdit.view !== view || wgEdit.saving || wgDrag) return;
            if (!e.isPrimary || e.button !== 0) return;
            const root = wgRoot(view), t = e.target;
            const card = t.closest ? t.closest('[data-widget]') : null;
            if (!card || card.parentNode !== root || card.hidden || t.closest('.wg-hide')) return;
            wgDrag = { view, root, card, id: card.getAttribute('data-widget'), pointer: e.pointerId,
                       touch: e.pointerType === 'touch', x0: e.clientX, y0: e.clientY, x: e.clientX, y: e.clientY,
                       lifted: false, hold: 0, trail: 0, last: -Infinity, frame: false, before: null, start: '',
                       scroller: root.closest('.scroll'), scrollTimer: 0, scrollAt: 0 };
            if (wgDrag.touch) wgDrag.hold = setTimeout(wgLift, WG_HOLD_MS);
            window.addEventListener('pointermove', wgOnMove);
            window.addEventListener('pointerup', wgOnUp);
            window.addEventListener('pointercancel', wgOnCancel);
            window.addEventListener('keydown', wgOnEscape, true);
            window.addEventListener('scroll', wgFollow, true);
            card.addEventListener('touchmove', wgNoScroll, { passive: false });
        }
        // Once a card is lifted the finger moves the card, not the page.
        function wgNoScroll(e) { if (wgDrag && wgDrag.lifted) e.preventDefault(); }
        function wgLift() {
            const d = wgDrag;
            if (!d || d.lifted) return;
            clearTimeout(d.hold);
            d.lifted = true;
            d.before = { order: wgEdit.draft.order.slice(), hidden: wgEdit.draft.hidden.slice() };
            d.start = wgItems(d.root).map(i => i.id).join(' ');
            const b = wgBox(d.card, d.root);
            d.grabX = d.x - b.left; d.grabY = d.y - b.top;
            d.card.classList.add('wg-held');
            if (!REDUCE_MOTION) d.card.classList.add('wg-lifted');
            if (d.touch && navigator.vibrate) navigator.vibrate(WG_BUZZ_MS);
            wgFollow();
        }
        /* Where a card's slot is, with no transform in it: offsetLeft and
           offsetTop ignore the held card's translate and a neighbour's slide.
           The wrap is positioned in the mode, so it is every card's offsetParent. */
        function wgBox(n, root) {
            const r = root.getBoundingClientRect();
            return { left: r.left + root.clientLeft + n.offsetLeft, top: r.top + root.clientTop + n.offsetTop,
                     width: n.offsetWidth, height: n.offsetHeight };
        }
        // The held card stays under the pointer where it was picked up, whatever slot the order has given it.
        function wgFollow() {
            const d = wgDrag;
            if (!d || !d.lifted) return;
            const b = wgBox(d.card, d.root);
            d.card.style.translate = (d.x - d.grabX - b.left) + 'px ' + (d.y - d.grabY - b.top) + 'px';
        }
        /* A held card near the top or bottom of the view's scroller scrolls
           it, faster the nearer the pointer is to the edge, because a finger
           holding a card has no other way to reach a place below the fold.
           Every pointer move steps it and a short timer keeps stepping while
           the pointer rests in the band; animation frames are not used, since
           a tab that is not being painted never runs them. A step covers the
           time since the last one, capped at two ticks, so a move and a tick
           landing together share the distance instead of doubling it. Each
           step writes scrollTop straight away, puts the card back under the
           pointer and asks the chooser again, because the slots moved with
           the page. It stops outside the band, at either end of the scroll,
           and when the drag ends (wgDragEnd clears the timer). */
        function wgAutoScroll() {
            const d = wgDrag;
            if (!d) return;
            clearTimeout(d.scrollTimer);
            const s = d.scroller;
            if (!d.lifted || !s) return;
            const r = s.getBoundingClientRect();
            const top = Math.max(r.top, 0), bottom = Math.min(r.bottom, window.innerHeight);
            const band = Math.min(WG_SCROLL_EDGE, (bottom - top) / 4);
            const up = d.y < top + band, down = !up && d.y > bottom - band;
            /* The end is where the page's own box ends, not scrollHeight: the
               held card's translate counts as overflow, so at the foot of the
               page it kept making room below itself and the scroll ran on into
               empty space (measured on the Overview at 375: 16778 against a
               real end of 8772), then jumped back on release. */
            const own = d.root.getBoundingClientRect().bottom - r.top - s.clientTop + s.scrollTop
                + parseFloat(getComputedStyle(s).paddingBottom);
            const end = Math.max(0, Math.min(s.scrollHeight, own) - s.clientHeight);
            if (!(up || down) || (up && s.scrollTop <= 0) || (down && s.scrollTop >= end)) { d.scrollAt = 0; return; }
            const depth = Math.min(1, (up ? top + band - d.y : d.y - (bottom - band)) / band);
            const tick = REDUCE_MOTION ? WG_SCROLL_JUMP_MS : WG_SCROLL_TICK_MS;
            const now = performance.now();
            const spent = d.scrollAt ? Math.min(now - d.scrollAt, 2 * tick) : tick;
            d.scrollAt = now;
            const by = Math.max(1, Math.round(WG_SCROLL_MAX * depth * depth * spent / 1000));
            s.scrollTop = Math.max(0, Math.min(end, s.scrollTop + (up ? -by : by)));
            wgFollow();
            wgStepSoon();
            d.scrollTimer = setTimeout(wgAutoScroll, tick);
        }
        function wgOnMove(e) {
            const d = wgDrag;
            if (!d || e.pointerId !== d.pointer) return;
            d.x = e.clientX; d.y = e.clientY;
            if (!d.lifted) {
                const far = Math.hypot(d.x - d.x0, d.y - d.y0);
                if (d.touch) { if (far > WG_TOUCH_SLOP) wgDragEnd(false); return; }
                if (far < WG_MOUSE_SLOP) return;
                wgLift();
            }
            wgFollow();
            wgStepSoon();
            wgAutoScroll();
        }
        /* At most one reorder per 40ms and per frame. The frame gate is opened
           by the next animation frame, or by a second 40ms passing, because a
           hidden tab runs no frames and a drag there must still step on every
           move rather than wait for one. */
        function wgStepSoon() {
            const d = wgDrag;
            clearTimeout(d.trail);
            const since = performance.now() - d.last;
            if (since >= WG_STEP_MS && (!d.frame || since >= 2 * WG_STEP_MS)) wgStep();
            // A still pointer can take two or three steps to settle, each nearer, so stepping carries on after the last move.
            d.trail = setTimeout(wgSettle, WG_STEP_MS);
        }
        function wgSettle() {
            const d = wgDrag;
            if (d && d.lifted && wgStep()) d.trail = setTimeout(wgSettle, WG_STEP_MS);
        }
        /* One step: lay out the shown cards, read each row's top and bottom
           from the cards placed in it, ask wgChoose whether a slot one move away
           is nearer the held card's centre than its own, and if so adopt the
           canonical order and slide the others. True when the order changed. */
        function wgStep() {
            const d = wgDrag;
            if (!d || !d.lifted) return false;
            d.last = performance.now();
            d.frame = true;
            requestAnimationFrame(() => { if (wgDrag === d) d.frame = false; });
            const root = d.root;
            const cols = +root.getAttribute('data-cols') || 1;
            const nodes = wgShown(root);
            const items = nodes.map(n => ({ id: n.getAttribute('data-widget'), size: n.getAttribute('data-size') || 'full' }));
            const places = wgLayout(items, cols);
            const me = places.find(p => p.id === d.id);
            if (!me) return false;
            const byId = new Map(nodes.map(n => [n.getAttribute('data-widget'), n]));
            const rowTops = [], rowBottoms = [];
            places.forEach(p => {
                const b = wgBox(byId.get(p.id), root);
                rowTops[p.row] = rowTops[p.row] == null ? b.top : Math.min(rowTops[p.row], b.top);
                rowBottoms[p.row] = rowBottoms[p.row] == null ? b.top + b.height : Math.max(rowBottoms[p.row], b.top + b.height);
            });
            const r = root.getBoundingClientRect(), cs = getComputedStyle(root);
            const g = { left: r.left + root.clientLeft + parseFloat(cs.paddingLeft), top: rowTops[0],
                        width: root.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight),
                        columns: cols, gap: parseFloat(cs.columnGap) || 0, rowTops, rowBottoms };
            const box = wgBox(d.card, root);
            const cx = d.x - d.grabX + box.width / 2, cy = d.y - d.grabY + box.height / 2;
            const pick = wgChoose(wgSlotFor(me, g), wgCandidates(items, d.id, cols, (s) => wgSlotFor(s, g)), cx, cy);
            if (!pick) return false;
            if (wgSameOrder(pick, items)) return false;
            wgAdopt(d.view, pick, d.card);
            wgFollow();
            return true;
        }
        function wgOnUp(e) {
            const d = wgDrag;
            if (!d || e.pointerId !== d.pointer) return;
            if (!d.lifted) { wgDragEnd(false); return; }
            d.x = e.clientX; d.y = e.clientY;
            // The steps a still pointer would have taken on the timer are taken now, so the drop lands where it was aimed.
            let n = 0;
            while (n++ < 4 && wgStep());
            wgDragEnd(true);
        }
        function wgOnCancel(e) {
            const d = wgDrag;
            if (d && e.pointerId === d.pointer) wgDragEnd(d.lifted);
        }
        // Escape while a card is held puts every card back where it was when the drag began.
        function wgOnEscape(e) {
            const d = wgDrag;
            if (!d || e.key !== 'Escape') return;
            e.preventDefault();
            e.stopPropagation();
            if (d.lifted && d.before) {
                wgEdit.draft = d.before;
                wgFlip(d.root, () => wgArrange(d.view), d.card);
            }
            wgDragEnd(d.lifted, true);
        }
        /* The end of a press. A drop slides the card from under the pointer
           into its slot, outlines it for --dur-landed and eats the click that
           follows; a drop that changed the order says where the card went. */
        function wgDragEnd(land, restored) {
            const d = wgDrag;
            if (!d) return;
            wgDrag = null;
            clearTimeout(d.hold);
            clearTimeout(d.trail);
            clearTimeout(d.scrollTimer);
            window.removeEventListener('pointermove', wgOnMove);
            window.removeEventListener('pointerup', wgOnUp);
            window.removeEventListener('pointercancel', wgOnCancel);
            window.removeEventListener('keydown', wgOnEscape, true);
            window.removeEventListener('scroll', wgFollow, true);
            d.card.removeEventListener('touchmove', wgNoScroll, { passive: false });
            if (!d.lifted) return;
            const from = d.card.style.translate;
            d.card.style.translate = '';
            d.card.classList.remove('wg-held', 'wg-lifted');
            if (!land || d.card.parentNode !== d.root) return;
            wgEatClicksUntil = performance.now() + WG_EAT_CLICK_MS;
            if (!REDUCE_MOTION && from) wgAnimate(d.card, [{ translate: from }, { translate: '0px 0px' }]);
            d.card.classList.add('wg-landed');
            setTimeout(() => d.card.classList.remove('wg-landed'), tokenNum('--dur-landed') * 1000);
            const ids = wgItems(d.root).map(i => i.id);
            if (!restored && ids.join(' ') !== d.start)
                wgSay(wgName(d.card) + ' moved to ' + (ids.indexOf(d.id) + 1) + ' of ' + ids.length);
        }
        /* ----- keyboard -----
           Alt with Right or Down moves the focused card one place later, Left
           or Up one place earlier, stopping at either end. The layout keeps the
           order it is given, so one place in the order is one place on the page.
           Enter and Space are held back so a card that opens something on its
           own does not open while it is being arranged. */
        function wgKey(view, e) {
            if (!wgEdit || wgEdit.view !== view || wgEdit.saving) return;
            const root = wgRoot(view), card = e.target;
            if (!card || card.parentNode !== root || !card.hasAttribute('data-widget')) return;
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); return; }
            const delta = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
            if (!e.altKey || !delta || wgDrag) return;
            e.preventDefault();
            e.stopPropagation();
            const items = wgItems(root), id = card.getAttribute('data-widget');
            const next = wgKeyMove(items, id, delta);
            if (next === items) return;
            wgAdopt(view, next);
            // Moving a node in the DOM drops its focus, and the keyboard is still holding this card.
            if (document.activeElement !== card) card.focus();
            const now = wgItems(root);
            wgSay(wgName(card) + ' moved to ' + (now.findIndex(i => i.id === id) + 1) + ' of ' + now.length);
        }
        /* ---------- widget grid end ---------- */
        /* One block, the reference's way: a card whose header carries the
           title and one muted line, and whose body runs to the card edge so a
           table or a chart meets the border instead of floating in a second
           inset box. Everything that used to be a bare heading over loose
           content becomes one of these. */
        function cardSection(title, desc, body, action) {
            const c = el('div', 'card');
            const h = el('div', 'card-head');
            h.append(el('h3', 'card-title', title));
            if (desc) h.append(el('p', 'card-desc', desc));
            if (action) { const a = el('div', 'card-act'); a.append(action); h.append(a); }
            c.append(h);
            if (body) { const b = el('div', 'card-bleed'); b.append(body); c.append(b); }
            return c;
        }
        /* Turn the app's bare headings into the reference's cards.
           
           The reference never puts a heading on the page with loose content
           under it: every block is a card whose header carries the title, with
           the content inside. This app had fifty-six of the former, written
           over a year, and rewriting each call site by hand would be a long
           edit with a lot of ways to go wrong. So the shape is applied after
           the fact instead: walk what a view just rendered, and fold each
           heading and the block it introduces into one card.
           
           A heading that introduces a ROW OF CARDS is left alone. The reference
           has those too - a group of cards under a label - and wrapping cards
           in a card is how you get a double border. */
