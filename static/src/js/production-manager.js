        function showLabelsView() {
            // A plain Shopify read with no AI cost: load straight away, no gate.
            if (skipLabelsAutoLoad) { skipLabelsAutoLoad = false; return; }
            if (labelsCache) { renderLabels(); return; }
            loadLabels(true);
        }
        // While an order fetch owns #labels-content, nothing else may repaint it:
        // a coverage result landing mid-refresh would resurrect the stale list.
        let labelsLoading = false;
        let labelsReq = 0;
        // force  = ignore the copy held in this page (a tab flip, a fresh view)
        // fresh  = also make the server re-read Shopify rather than reuse its
        //          recent sweep. Only Refresh asks for that: tab flips are the
        //          whole reason the server keeps a snapshot.
        async function loadLabels(force, fresh) {
            const box = $('labels-content');
            if (queueMode === 'shipments') { renderCustomQueue(box); return; }
            if (labelsCache && !force) { renderLabels(); return; }
            box.innerHTML = '';
            const hero = pageHead({ view: 'labels', title: 'Production Manager', line: 'Finding orders tagged "' + queueTag() + '"…' });
            box.append(hero);
            const t = el('div', 'thinking'); t.classList.add('space-above-2'); t.append(loader(), el('span', null, 'Reading your Shopify orders…')); box.append(t);
            labelsLoading = true;
            const rq = ++labelsReq;   // only the newest fetch may commit its result
            try {
                const data = await api('/api/production-labels', { tag: queueTag(), fresh: !!fresh });
                if (rq !== labelsReq) return;   // a newer load started; drop this stale response
                labelsCache = { data, at: Date.now() };
                labelsLoading = false;
                renderLabels();
                if (queueMode === 'make') loadMissing();   // untagged-order check rides along, non-blocking
                else { labelsMissing = null; }
            } catch (e) {
                if (rq !== labelsReq) return;
                labelsLoading = false;
                reportFailed(box, hero, 'The production orders could not be read. ' + (e.message || String(e)),
                    labelsCache ? () => renderLabels() : null, () => loadLabels(true, true));
            }
        }
        function labelOrders() { return (labelsCache && labelsCache.data && labelsCache.data.orders) || []; }
        /* Printed/made stamps, bundled with the labels payload and updated locally
           as the team prints and ticks orders off. */
        function prodStateOf(o) {
            const st = labelsCache && labelsCache.data && labelsCache.data.state;
            return (st && st[String(o.id)]) || {};
        }
        function setProdState(id, patch) {
            if (!labelsCache || !labelsCache.data) return;
            const st = labelsCache.data.state = labelsCache.data.state || {};
            st[String(id)] = Object.assign({}, st[String(id)] || {}, patch);
        }
        let labelsFilter = 'all';   // all | unprinted | unmade
        let labelsSearch = '';      // client-side find within the loaded queue
        function stampPrinted(orders) {
            const ids = orders.map(o => o.id).filter(Boolean);
            if (!ids.length) return;
            const now = new Date().toISOString();
            const prev = {};
            ids.forEach(id => { prev[id] = prodStateOf({ id: id }).printed_at || null; setProdState(id, { printed_at: now }); });
            api('/api/production-state', { op: 'printed', ids })
                .then(r => {
                    if (r && r.tag_note) toastError(r.tag_note);
                    if (r && r.state_note) toastError(r.state_note);
                    /* Printing IS a release, so an account order's 30-day
                       clock starts here too. The note was computed and thrown
                       away, so a purchase order could enter production with no
                       due date and nobody was told. */
                    /* Per order. One boolean over a whole batch meant a red
                       toast could carry three success sentences while the
                       order that actually failed was never named. */
                    const terms = (r && r.terms) || [];
                    const bad = terms.filter(t => !t.ok);
                    const good = terms.filter(t => t.ok);
                    if (bad.length) {
                        bad.slice(0, 4).forEach(t => toastError('#' + t.order + ': ' + t.note));
                        if (bad.length > 4) toastError((bad.length - 4) + ' more orders did not get their 30-day terms. Release them again from the queue.');
                    }
                    if (good.length) {
                        addToast(good.length === 1 ? ('#' + good[0].order + ': ' + good[0].note)
                                 : (good.length + ' account orders were put on 30-day terms.'), 'good');
                    }
                    if (!terms.length && r && r.terms_note) {
                        if (r.terms_ok === false) toastError(r.terms_note);
                        else addToast(r.terms_note, 'good');
                    }
                    /* A big run releases the first orders while you wait and
                       paces the rest behind the scenes, so say so rather than
                       leaving the queue looking half-moved. */
                    if (r && r.queued) {
                        addToast(r.queued + ' more ' + (r.queued === 1 ? 'order is' : 'orders are')
                                 + ' being released in the background; the queue will catch up.');
                    }
                    if (labelsCache && document.querySelector('#view-labels.active')) renderLabels();
                    // The browser cannot tell us whether they actually printed, so
                    // offer a way back: wrong label stock is a normal mistake.
                    undoPrintBar(ids);
                })
                .catch(() => {
                    // The stamp did not persist: undo the local one so a reload does
                    // not think these were printed (and re-tag stays consistent).
                    ids.forEach(id => setProdState(id, { printed_at: prev[id] }));
                    toastError('Printed, but the app could not record it. It may reappear as unprinted.');
                    if (labelsCache && document.querySelector('#view-labels.active')) renderLabels();
                });
        }
        // A print is stamped optimistically (the browser never reports whether the
        // print dialog was confirmed or cancelled), so every stamp gets an undo.
        function undoPrintBar(ids) {
            let host = document.getElementById('toast-host');
            if (!host) {
                host = el('div'); host.id = 'toast-host';
                /* Every async outcome lands here and none of it was announced:
                   a live region, polite so it queues rather than interrupts. */
                host.setAttribute('role', 'status'); host.setAttribute('aria-live', 'polite');
                document.body.append(host);
            }
            const t = el('div', 'toast');
            t.append(el('div', 'toast-msg', 'Marked ' + ids.length + (ids.length === 1 ? ' order' : ' orders') + ' as printed.'));
            const u = textButton(); u.textContent = 'Undo';
            u.onclick = async () => {
                u.disabled = true;
                try {
                    const r = await api('/api/production-state', { op: 'unprinted', ids });
                    /* The server's word for each order, not a guess: an order
                       already made or shipped keeps its stamp and its tags,
                       because its print was a reprint and not a release. */
                    const kept = new Set(((r && r.kept) || []).map(String));
                    ids.forEach(id => {
                        const st = prodStateOf({ id: id }); if (!st) return;
                        const now = ((r && r.state) || {})[String(id)];
                        if (now && now.printed_at) st.printed_at = now.printed_at;
                        else if (!kept.has(String(id))) delete st.printed_at;
                    });
                    if (r && r.tag_note) toastError(r.tag_note);
                    renderLabels();
                    const back = ids.length - kept.size;
                    addToast(!kept.size ? 'Put back as not printed.'
                        : !back ? (ids.length === 1 ? 'That order is already made, so it stays as it is.'
                                                    : 'Those orders are already made, so they stay as they are.')
                        : 'Put back as not printed, apart from ' + kept.size + ' already made.');
                } catch (e) { toastError(e.message || 'Could not undo that.'); }
                t.remove();
            };
            t.append(u);
            const x = iconButton(I.x, 'Dismiss', { size: 'small' });
            x.onclick = () => t.remove();
            t.append(x);
            host.append(t);
            setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 320); }, 15000);
        }
        // Marking made can fulfil Shopify and email the customer, and the rows
        // re-order as soon as it lands - so a second click must never reach a
        // different order, and must never silently undo the first one.
        const madeBusy = {};
        async function readyToMake(o, btn) {
            btn.disabled = true;
            try {
                const r = await api('/api/production-labels/queue', { order_id: o.id, name: orderNo(o) });
                /* A made or shipped order is not released again: the server
                   says so, and the toast says what really happened. */
                if (r.released === false) { addToast(r.note || (orderNo(o) + ' is already made.')); loadLabels(true); return; }
                /* An account order's payment clock starts here: the outcome is
                   said either way, because a purchase order quietly missing
                   its terms is an invoice nobody chases. */
                /* The release HAPPENED - the tag moved before the terms were
                   attempted - so say so either way. Showing only the red terms
                   error left the merchant unsure whether to press it again. */
                addToast(orderNo(o) + ' moved to To make.'
                    + (r.po_unpaid && r.terms_ok && r.terms_note ? ' ' + r.terms_note : ''));
                if (r.po_unpaid && !r.terms_ok) toastError(orderNo(o) + ': ' + r.terms_note);
                loadLabels(true);
            } catch (e) {
                btn.disabled = false;
                toastError(e.message || 'Could not move the order');
            }
        }
        async function toggleMade(o) {
            if (madeBusy[o.id]) return;
            const prev = prodStateOf(o).made_at || null;
            const on = !prev;
            const dsp = dispatchStateOf(o);
            // Un-marking something the customer has already been emailed about is a
            // real-world action, not a toggle: make them mean it.
            if (!on && dsp.fulfilled) {
                const okToUndo = await uiConfirm(
                    'This order is already fulfilled in Shopify and the customer has been emailed its tracking. '
                    + 'Un-marking it will cancel that fulfilment and put the order back in production. Continue?',
                    { title: 'Undo a shipped order', okText: 'Undo it' });
                if (!okToUndo) return;
            }
            madeBusy[o.id] = true;
            setProdState(o.id, { made_at: on ? new Date().toISOString() : null });
            if (!on) { const st = prodStateOf(o); delete st.made_at; }
            renderLabels();
            try {
                const r = await api('/api/production-state', { op: 'made', id: o.id, on, name: orderNo(o) });
                if (r && r.dispatch && labelsCache && labelsCache.data) {
                    labelsCache.data.dispatch = Object.assign({}, labelsCache.data.dispatch || {}, r.dispatch);
                }
                renderLabels();
                if (r && r.needs_ack) {
                    // The address moved after the label was booked. Only a human
                    // knows where the parcel actually went, so ask once and let
                    // the answer stand.
                    const go = await uiConfirm(r.ship_note + '\n\nIf the parcel did reach the '
                        + 'customer, confirm and this order will be fulfilled with the booked '
                        + 'tracking as normal.',
                        { title: 'The address changed after this label was booked',
                          okText: 'The parcel is fine, fulfil it', cancelText: 'Leave it for now' });
                    if (go) {
                        try {
                            const r2 = await api('/api/production-state',
                                { op: 'made', id: o.id, on: true, name: orderNo(o), ack_address: true });
                            if (r2 && r2.dispatch && labelsCache && labelsCache.data) {
                                labelsCache.data.dispatch = Object.assign({}, labelsCache.data.dispatch || {}, r2.dispatch);
                            }
                            renderLabels();
                            if (r2 && r2.ship_note) addToast(r2.ship_note, r2.fulfilled ? 'good' : '');
                        } catch (e2) { toastError(e2.message || 'Could not fulfil it.'); }
                    } else addToast(r.ship_note);
                } else if (r && r.ship_note) addToast(r.ship_note, r.fulfilled ? 'good' : '');
                if (r && r.stock_note) addToast(r.stock_note);
                if (r && r.tag_note) toastError(r.tag_note);
            } catch (e) {
                setProdState(o.id, { made_at: prev });
                if (!prev) { const st = prodStateOf(o); delete st.made_at; }
                renderLabels();
                // Give them the real reason, not a generic retry.
                toastError((e.message || 'Could not mark that order.')
                    + (e.noReply ? '' : ' Nothing was changed. Press Refresh and check before trying again.'));
            } finally {
                delete madeBusy[o.id];
            }
        }
        /* Paid gobo orders that never got the production tag: they would otherwise
           never reach the workbench. Fetched after the list, shown as a strip. */
        let labelsMissing = null;   // { data, at } | null
        let labelsOldest = false;
        async function loadMissing() {
            let data = null;
            try { data = await api('/api/production-labels/missing', {}); } catch (e) { data = null; }
            /* The server keeps this answer until an order changes, so most
               loads bring back the strip already on screen; the queue is
               drawn again only for one that differs (the 2026-10-12 speed
               audit, X7). */
            const same = !!(data && labelsMissing && JSON.stringify(labelsMissing.data) === JSON.stringify(data));
            labelsMissing = data ? { data, at: Date.now() } : null;
            if (same) return;
            if (!labelsLoading && labelsCache) renderLabels();
        }
        function missingStrip() {
            const d = labelsMissing.data;
            const wrap = el('div', 'miss-strip');
            const head = el('div', 'miss-head');
            head.append(ico(I.warning), el('b', null, 'Possibly missing from production'),
                el('span', 'miss-sub', (d.missing_total === 1 ? '1 paid order has' : d.missing_total + ' paid orders have')
                    + ' gobo items but no "' + (d.tag || LABEL_TAG) + '" tag.'
                    + (d.truncated ? ' Only the first ' + d.checked + ' open orders could be checked.' : '')));
            wrap.append(head);
            d.missing.forEach(m => {
                const row = el('div', 'miss-row');
                row.append(el('b', null, m.name));
                if (m.company) row.append(el('span', 'miss-co', m.company));
                row.append(el('span', null, m.gobo_items + (m.gobo_items === 1 ? ' gobo item' : ' gobo items')
                    + ' · ' + ageLabel(m.created_at)));
                if (m.proposal_url) {
                    const pf = el('a', 'miss-open', 'Proof');
                    pf.href = '#'; pf.title = 'Preview the proposal proof';
                    pf.onclick = (e) => { e.preventDefault(); openProposal({ name: m.name, proposal_url: m.proposal_url }); };
                    row.append(pf);
                }
                const q = textButton(null, { cls: 'miss-queue' });
                q.append(ico(I.plus), document.createTextNode('Add to queue'));
                q.title = 'Tag this order "' + (d.tag || LABEL_TAG) + '" so it joins the production list';
                q.onclick = async () => {
                    q.disabled = true;
                    q.textContent = 'Tagging…';
                    try {
                        await api('/api/production-labels/queue', { order_id: m.id, name: m.name || '' });
                        // It is in the queue now: drop it from the strip and refetch
                        // the list so the new row appears.
                        if (labelsMissing && labelsMissing.data) {
                            labelsMissing.data.missing = labelsMissing.data.missing.filter(x => x.id !== m.id);
                            labelsMissing.data.missing_total = Math.max(0, (labelsMissing.data.missing_total || 1) - 1);
                        }
                        loadLabels(true);
                    } catch (e) {
                        toastError(e.message || 'Could not tag the order.');
                        q.disabled = false;
                        q.innerHTML = '';
                        q.append(ico(I.plus), document.createTextNode('Add to queue'));
                    }
                };
                row.append(q);
                /* No separate "Open order" link: the order number itself is
                   now the door, and two links to the same place is clutter. */
                wrap.append(row);
            });
            return wrap;
        }
        /* Proposal/proof preview: the store's own quote page, embedded so the
           team can eyeball the artwork without leaving the order list. */
        function openProposal(o) {
            const win = dialog({ title: 'Proof · ' + orderNo(o), size: 'cmodal proof-modal', bodyClass: 'proof-body' });
            const { overlay, modal, head, x, body } = win;
            const ext = el('a', 'proof-ext', 'Open in new tab');
            ext.href = o.proposal_url; ext.target = '_blank'; ext.rel = 'noopener';
            x.before(ext);
            const fr = document.createElement('iframe');
            fr.className = 'proof-frame';
            /* allow-same-origin is only safe while the framed page is on a
                   DIFFERENT origin: on our own, the frame would run with this
               page's origin and reach its localStorage. The host is pinned
               server-side, and this is the check that says so out loud. */
            let proofSameOrigin = true;
            try { proofSameOrigin = new URL(o.proposal_url, location.href).host === location.host; }
            catch (e) { proofSameOrigin = true; }
            fr.setAttribute('sandbox', proofSameOrigin
                ? 'allow-scripts allow-popups'
                : 'allow-scripts allow-same-origin allow-popups');
            fr.src = o.proposal_url;
            fr.title = 'Proposal proof';
            body.append(fr);
        }
        /* "Repeat customer" line above the label preview, fetched once per customer. */
        const labelHistCache = {};
        /* An order number on screen is a door, never a label: it opens the
           order in the Shopify admin. Falls back to plain text when the link
           cannot be built (custom shipments, store handle unknown). */
        /* An order number on screen is a door. It opens in a NEW TAB, never in
           place: half these numbers sit inside a row that is itself a button,
           and a production desk that loses its queue to a stray click has been
           made worse, not better. Falls back to plain text when there is no id
           to link to, so a caller never has to decide. */
        function orderA(name, url, cls) {
            if (!url) return el('span', cls || null, name || '');
            const a = el('a', cls || 'miss-open', name || 'Order');
            a.href = url; a.target = '_blank'; a.rel = 'noopener';
            a.title = 'Open ' + (name || 'this order') + ' in Shopify (new tab)';
            a.onclick = (e) => e.stopPropagation();
            return a;
        }
        function histText(d) {
            if (!d || !d.count || d.count < 2) return 'First order from this customer.';
            const prev = (d.recent || [])[1];
            return 'Repeat customer: ' + d.count + ' orders'
                + (prev ? ' · previous ' + prev.name + ' (' + fmtDate(prev.created_at) + ')' : '');
        }
        function histFill(h, d) {
            h.textContent = '';
            if (!d || !d.count || d.count < 2) { h.textContent = 'First order from this customer.'; return; }
            const prev = (d.recent || [])[1];
            h.append(document.createTextNode('Repeat customer: ' + d.count + ' orders'));
            if (prev) {
                h.append(document.createTextNode(' · previous '));
                h.append(orderA(prev.name, prev.admin_url));
                h.append(document.createTextNode(' (' + fmtDate(prev.created_at) + ')'));
            }
        }
        function histLine(o) {
            const h = el('div', 'lbl-hist');
            const cached = labelHistCache[o.customer_id];
            if (cached) { histFill(h, cached); return h; }
            h.textContent = 'Checking order history…';
            api('/api/customer-history', { customer_id: o.customer_id }).then(d => {
                labelHistCache[o.customer_id] = d;
                if (h.isConnected) histFill(h, d);
            }).catch(() => { if (h.isConnected) h.remove(); });
            return h;
        }
        function ageDays(iso) {
            const t = Date.parse(iso || '');
            return isNaN(t) ? 0 : Math.floor((Date.now() - t) / 86400000);
        }
        function ageLabel(iso) {
            const d = ageDays(iso);
            return d <= 0 ? 'placed today' : d === 1 ? 'placed yesterday' : 'placed ' + d + ' days ago';
        }
        // Shopify's `name` is the full order number as the admin shows it, including the
        // "#" and any store prefix/suffix. Fall back to building it from order_number.
        function orderNo(o) {
            const n = String(o.name || '').trim();
            return n || ('#' + o.order_number);
        }
        // ---- quote pre-fetch -------------------------------------------------
        // Quoting is free and takes several seconds, so the To-ship queue quotes
        // itself quietly in the background: by the time Dispatch is opened the
        // couriers are usually already priced. A cached quote is only ever used
        // when the parcels and insurance in the window match what was priced,
        // which is the same rule a manual quote follows.
        const quoteCache = new Map();          // orderId -> {sig, quote, at}
        const QUOTE_TTL = 8 * 60 * 1000;       // prices move; do not trust an old one
        const PREFETCH_MAX = 12;               // politeness to World Options
        let prefetchRun = 0;

        function boxSig(boxes, insurance) {
            return JSON.stringify({ b: boxes || [], i: insurance || 0 });
        }
        function cachedQuote(orderId, boxes, insurance) {
            const hit = quoteCache.get(String(orderId));
            if (!hit || hit.sig !== boxSig(boxes, insurance)) return null;
            if (Date.now() - hit.at > QUOTE_TTL) return null;
            return hit.quote;
        }
        // The parcel the dispatch window WOULD start with, so the pre-fetch prices
        // the same thing. Mirrors applyPreset: box weight plus the contents.
        function defaultBoxesFor(o, cfg) {
            const presets = (cfg && cfg.boxes) || [];
            const b = (cfg && cfg.default_box_id && presets.find(x => x.id === cfg.default_box_id))
                || presets[0];
            if (!b) return null;
            const contents = o.weight_hint > 0 ? o.weight_hint : 0;
            const weight = Math.round(((b.weight || 0) + contents) * 100) / 100;
            if (!(b.width > 0 && b.length > 0 && b.depth > 0 && weight > 0)) return null;
            return [{ width: b.width, length: b.length, depth: b.depth, weight: weight }];
        }
        async function prefetchQuotes(orders) {
            const run = ++prefetchRun;
            let cfg;
            try { cfg = await ensureShippingCfg(); }
            catch (e) { return; }                       // not set up: nothing to do
            if (!cfg || !cfg.connected || run !== prefetchRun) return;
            const todo = (orders || [])
                .filter(o => !(dispatchStateOf(o) || {}).tracking_number)
                .slice(0, PREFETCH_MAX);
            for (const o of todo) {
                if (run !== prefetchRun) return;        // queue changed; abandon quietly
                const boxes = defaultBoxesFor(o, cfg);
                if (!boxes || cachedQuote(o.id, boxes, 0)) continue;
                try {
                    const q = await api('/api/dispatch/quote', { order_id: o.id, boxes: boxes, insurance: 0 });
                    /* Keep it FIRST, abandon second. A quote that arrives after
                       the queue repainted is still the right price for that
                       order and that box signature, and cachedQuote revalidates
                       both plus the eight minute age before anything uses it.
                       Throwing it away meant a courier round trip of several
                       seconds, already paid for, was binned every repaint. */
                    quoteCache.set(String(o.id), { sig: boxSig(boxes, 0), quote: q, at: Date.now() });
                    if (run !== prefetchRun) return;
                } catch (e) {
                    // A pre-fetch is a convenience: a failure here must never reach
                    // the operator, who has not asked for anything yet.
                }
                // Paced only after a real call, so re-entering with everything
                // already cached costs nothing.
                await new Promise(r => setTimeout(r, 250));
            }
        }

        let customQ = '';
        async function renderCustomQueue(box) {
            /* Shipments booked to a pasted address. They are not orders, so
               they never appear in the order queues, and until now the only
               way back to one was to reopen the booking window: a button that
               reads like "spend money again". */
            box.innerHTML = '';
            /* The same page as the other queues (the mix): the same header with
               its live line and Refresh, the same counters and tabs, then the
               house search and the list. */
            const newShip = textButton(null);
            newShip.append(ico(I.plus), document.createTextNode('New shipment'));
            newShip.onclick = openCustomShip;
            const head = pageHead({ view: 'labels', title: 'Production Manager', live: Date.now(),
                onRefresh: () => renderCustomQueue(box), refreshLabel: 'Refresh', actions: [newShip] });
            head.classList.add('pm-head');      // the queue's phone head: Refresh is the 40 square at the title's right
            box.append(head);
            box.append(prodQueues((k) => { queueMode = k; labelsCache = null; labelSel = null; loadLabels(true); }));
            /* The queue's own card, so its lines run as the queue's do, to its panel's edges (13 Oct 2026). */
            const card = el('div', 'card q-card');
            let paint = () => {};
            const findWrap = tableSearch('Search reference, name or tracking', customQ, null);
            const find = findWrap.input;
            card.append(tableTools([findWrap], []));
            const host = el('div', 'lbl-list');
            card.append(host);
            box.append(card);
            let rows = [], canHide = false;
            paint = () => {
                host.innerHTML = '';
                const q = customQ.toLowerCase();
                const shown = !q ? rows : rows.filter(sh =>
                    ((sh.reference || '') + ' ' + (sh.customer || '') + ' '
                     + (sh.tracking || '') + ' ' + (sh.carrier || '')).toLowerCase().indexOf(q) >= 0);
                if (!shown.length) {
                    if (rows.length) { host.append(el('div', 'empty', 'Nothing matches that.')); return; }
                    const again = textButton(); again.type = 'button';
                    again.append(ico(I.plus), document.createTextNode('New shipment'));
                    again.onclick = openCustomShip;
                    host.append(emptyState({ icon: I.box, text: 'No custom shipments yet.', action: again }));
                    return;
                }
                /* The tab's own queue row, not the Files browser's. */
                const list = el('div', 'lbl-grid');
                shown.forEach(sh => {
                    const row = el('div', 'lbl-row lbl-qrow');
                    row.append(el('div', 'lbl-num', sh.reference || 'Shipment'));
                    const who = el('div', 'lbl-who');
                    const nameLine = el('span', 'lbl-nameline');
                    if (sh.customer) nameLine.append(el('span', 'lbl-name' + (sh.canceled ? ' is-cancelled' : ''), sh.customer));
                    if (sh.canceled) nameLine.append(el('span', 'lbl-chip bad', 'Cancelled'));
                    /* Only an admin ever receives one of these rows, so the
                       chip is not a permission check: it is the reminder that
                       what is on this row is not on anyone else's. */
                    if (sh.admin_only) {
                        const pc = el('span', 'lbl-chip warn', 'Admin only');
                        pc.title = 'Hidden from the team: off their Custom shipments queue and the day’s manifest';
                        nameLine.append(pc);
                    }
                    who.append(nameLine);
                    /* The carrier line and the contents are ONE item under the
                       name: in the widest layout each child of this box is a
                       column of the queue's grid, and a second line here made
                       six items for five columns, so the buttons wrapped into
                       the 100px number column and hung out over the sidebar. */
                    const lines = [[sh.carrier, sh.service, sh.tracking].filter(Boolean).join('  ·  '), sh.contents || '']
                        .filter(Boolean);
                    const sub = el('span', 'sub');
                    lines.forEach(t => { const ln = el('span', 'sub-line', t); ln.title = t; sub.append(ln); });
                    who.append(sub);
                    row.append(who);
                    row.append(el('div', 'lbl-meta', [sh.at ? fmtDate(sh.at) : '',
                        sh.amount != null ? fmtPrice(sh.amount, sh.currency) : '']
                        .filter(Boolean).join('  ·  ')));
                    const acts = el('div', 'lbl-actions');
                    if (!sh.canceled && sh.tracking) {
                        const cp = textButton(null);
                        cp.title = 'Copy tracking'; cp.append(ico(I.copy), el('span', 'lbl-btn-txt', 'Copy tracking'));
                        cp.onclick = async () => {
                            try { await navigator.clipboard.writeText(sh.tracking); toastOk('Tracking copied'); }
                            catch (e) { toastError('Could not copy it.'); }
                        };
                        acts.append(cp);
                    } else {
                        /* An empty slot as wide as Copy tracking, so Reprint label
                           lines up down the list (OPS-11). */
                        const slot = textButton(null, { cls: 'lbl-slot' }); slot.type = 'button'; slot.tabIndex = -1; slot.setAttribute('aria-hidden', 'true');
                        slot.append(ico(I.copy), el('span', 'lbl-btn-txt', 'Copy tracking'));
                        acts.append(slot);
                    }
                    /* Plain: nine teal Reprint labels down a list were nine primaries. */
                    const rp = textButton(null);
                    rp.append(ico(I.printer), el('span', 'lbl-btn-txt', 'Reprint label'));
                    rp.title = 'Reprint label';
                    if (sh.has_label === false) {
                        rp.disabled = true;
                        rp.title = 'No stored label for this one. It is in your World Options '
                            + 'portal under the tracking number.';
                    }
                    rp.onclick = async () => {
                        rp.disabled = true;
                        try {
                            const r = await api('/api/dispatch/label', { id: sh.id });
                            if (!printLabelImages(r.labels || [])) labelButtons(acts, r.labels, 'Print label');
                        } catch (e) { toastError(e.message || 'Could not fetch the label'); }
                        rp.disabled = false;
                    };
                    acts.append(rp);
                    /* Hide or show, for an admin only. canHide comes from the
                       answer that carried these rows, so the page never has to
                       work out its own rank: the server that filtered the list
                       is the one that says whether the control belongs. */
                    if (canHide) {
                        const hv = textButton(null);
                        const on = !!sh.admin_only;
                        hv.append(ico(on ? I.eye : I.eyeOff),
                                  el('span', 'lbl-btn-txt', on ? 'Show the team' : 'Hide from team'));
                        hv.title = on ? 'Put this shipment back on the team’s queue and manifest'
                            : 'Keep this shipment to admins: off the team’s queue and the day’s manifest';
                        hv.onclick = async () => {
                            hv.disabled = true;
                            try {
                                await api('/api/custom/visibility', { id: sh.id, admin_only: !on });
                                sh.admin_only = !on;
                                toastOk(!on ? 'Hidden from the team.' : 'The team can see it again.');
                                paint();
                            } catch (e) {
                                toastError(e.message || 'Could not change who can see it.');
                                hv.disabled = false;
                            }
                        };
                        acts.append(hv);
                    }
                    row.append(acts);
                    list.append(row);
                });
                host.append(list);
            };
            find.oninput = () => { customQ = find.value; clearTimeout(find._t); find._t = setTimeout(paint, 150); };
            host.append((() => { const t = el('div', 'thinking');
                t.append(loader(), el('span', null, 'Reading booked shipments…')); return t; })());
            try {
                const r = await api('/api/custom/list', { limit: 200 });
                rows = r.shipments || [];
                canHide = !!r.can_hide;
                tabCount(box, 'shipments', rows.length, 'shipments');
            } catch (e) {
                host.innerHTML = '';
                host.append(loadFailure('The shipments could not be read. ' + (e.message || ''), () => renderCustomQueue(box)));
                return;
            }
            paint();
        }
        // The split is decided in JS, so crossing it must repaint. Without this a
        // window dragged from one screen to another shows a preview in the wrong
        // place until the next click.
        try {
            window.matchMedia('(min-width: 1500px)').addEventListener('change', () => {
                if (document.querySelector('#view-labels.active') && labelsCache) renderLabels();
            });
        } catch (e) { /* older browsers: the layout is simply fixed at load */ }

        function renderLabels() {
            if (!labelsCache) return;   // e.g. a coverage callback after the cache was cleared for a reload
            const box = $('labels-content'); box.innerHTML = '';
            const data = labelsCache.data;
            let orders = labelOrders().slice();
            if (labelsOldest) orders.reverse();   // server sends newest first
            // Made orders sink to the bottom whatever the sort.
            orders = orders.filter(o => !prodStateOf(o).made_at).concat(orders.filter(o => prodStateOf(o).made_at));
            const printable = orders.filter(o => !o.status);
            const unprinted = printable.filter(o => !prodStateOf(o).printed_at);
            const unmade = printable.filter(o => !prodStateOf(o).made_at);
            let shown = labelsFilter === 'unprinted' ? unprinted : labelsFilter === 'unmade' ? unmade : orders;
            if (labelsSearch) {
                const q = labelsSearch.toLowerCase();
                shown = shown.filter(o => (String(orderNo(o)) + ' ' + (o.display_name || '') + ' '
                    + ((dispatchStateOf(o) || {}).tracking_number || '')).toLowerCase().indexOf(q) >= 0);
            }
            if (queueMode === 'shipments') { renderCustomQueue(box); return; }
            const dispatched = queueMode === 'dispatched';
            const shipMode = queueMode === 'ship';
            const unproc = queueMode === 'unprocessed';
            // Price the ready-to-ship queue in the background so the couriers are
            // already listed when Dispatch is opened. Free, and never blocking.
            if (shipMode) prefetchQuotes(shown);
            else prefetchRun++;                 // left the queue: stop any run in flight
            /* The header (the mix, spec 8.2): the live line with Refresh, and the
               page's actions at the right (added below, where they are built).
               The rule of the two queues worth explaining waits behind the info
               button, word for word; the counters say the rest. */
            const queueRule = unproc ? 'New orders not yet released to the workbench. Press Ready to make when one should join the To make queue.'
                : queueMode === 'make' ? 'Orders released to the bench (tagged "' + (data.tag || LABEL_TAG) + '" in Shopify). Select one to preview its label, then print.'
                : '';
            const hero = pageHead({ view: 'labels', title: 'Production Manager', live: labelsCache.at,
                onRefresh: () => loadLabels(true, true), refreshLabel: 'Refresh',
                info: queueRule ? infoButton('About this queue', { title: unproc ? 'Unprocessed' : 'To make', body: queueRule }) : null });
            hero.classList.add('pm-head');
            box.append(hero);
            const heroActs = hero.querySelector('.ov-hero-act');
            /* The counters sit straight under the header, built in the same pass:
               the header's 32 gives way to 20 only for a counters row that is its
               very next sibling, which is not re-worked if one arrives later. */
            // Lifecycle queue: Unprocessed -> To make -> To ship, then Complete.
            if (data.counts) labelsCounts = data.counts;
            box.append(prodQueues((k) => { queueMode = k; labelsCache = null; labelSel = null; labelsFilter = 'all'; loadLabels(true); }, dispatched ? { dispatched: orders.length } : null));
            // A sweep that Shopify cut short renders as a SHORT list, which is
            // indistinguishable from a quiet day. Say so rather than let the
            // bench work from a queue that is quietly missing orders.
            if (data.partial_note) box.append(el('div', 'msg error', data.partial_note));

            /* Two holding rails. Everything below still builds into them so the
               construction reads as it always has; the composition at the end
               takes the named buttons out and puts them where they belong. */
            const bar = el('div');
            const tools = el('div');
            let pnBtn = null, allBtn = null, slBtn = null, filtTabs = null;
            // A parcel that is not an order: paste an address and book it.
            const newShip = textButton(null);
            newShip.append(ico(I.plus), document.createTextNode('New shipment'));
            newShip.title = 'Book a courier to an address you paste in, with no Shopify order behind it';
            newShip.onclick = openCustomShip;
            bar.append(newShip);
            /* Says what it will do rather than only what it is: once an
               arrangement is chosen the button carries it, so nobody has to
               remember what the next booking is going to ask for. */
            const coll = textButton(null, { cls: collectionForRun ? 'on' : '' });
            coll.append(ico(I.cal), document.createTextNode(
                collectionForRun ? ('Collection: ' + collectionSummary()) : 'Collections'));
            coll.title = 'How each courier collects, and a one-off change for the next booking';
            coll.onclick = openBookCollection;
            bar.append(coll);
            if (unprinted.length && unprinted.length < printable.length) {
                /* One teal: while an order is open its Print is the one. */
                pnBtn = textButton(null, { kind: labelSel ? '' : 'primary' });
                pnBtn.append(ico(I.printer), document.createTextNode('Print new (' + unprinted.length + ')'));
                pnBtn.onclick = () => printLabels(unprinted);
            }
            if (printable.length) {
                // Cancelled, refunded and already-fulfilled orders never join a bulk print.
                allBtn = textButton(null);
                allBtn.append(ico(I.printer), document.createTextNode('Print all (' + printable.length + ')'));
                allBtn.onclick = () => printLabels(printable);
            }
            /* Courier labels for everything in view that has actually been
               dispatched. Separate from the gobo-label buttons above: that
               stock is 4x2 on the bench printer, this is the courier's own
               4x6 sheet, and they are never the same run. */
            const shipLabels = shown.filter(shipLabelEligible);
            if (shipLabels.length) {
                slBtn = textButton(null, { cls: 'ship-btn' });
                slBtn.append(ico(I.printer), document.createTextNode(
                    'Print shipping labels (' + shipLabels.length + ')'));
                slBtn.title = 'Reprint the courier labels for dispatched orders in this list';
                slBtn.onclick = () => printShippingLabelsFor(shipLabels);
            }
            /* All counts every row it shows, as the card title does: it counted
               only the printable ones and read 'All (5)' over six rows. And
               the To ship queue holds only made orders, so 'Not made' there
               could only ever be empty. */
            if (!dispatched) {
                filtTabs = segmented([{ key: 'all', label: 'All', n: orders.length },
                                       { key: 'unprinted', label: 'Unprinted', n: unprinted.length }]
                                      .concat(shipMode ? [] : [{ key: 'unmade', label: 'Not made', n: unmade.length }]),
                                      labelsFilter, (k) => { labelsFilter = k; renderLabels(); }, { label: 'Show' });
            }
            const findWrap = tableSearch('Find order, customer or tracking', labelsSearch, null);
            const find = findWrap.input;
            find.classList.add('lbl-find');
            /* Debounced, and the caret is put back where it was: this repaints
               the whole queue, and a search that loses its own cursor after
               every letter cannot be typed into. The new box is given the text
               as typed, not the trimmed search it was built from, or a pause
               after a space dropped the space and 'clay paky' became
               'claypaky'. */
            find.oninput = () => {
                labelsSearch = find.value.trim();
                clearTimeout(find._t);
                find._t = setTimeout(() => {
                    const at = find.selectionStart, typed = find.value; renderLabels();
                    const again = document.querySelector('.lbl-find');
                    if (again) { again.value = typed; again.focus(); try { again.setSelectionRange(at, at); } catch (e) {} }
                }, 180);
            };
            const oldf = textButton(null, { cls: labelsOldest ? 'on' : '' });
            oldf.append(ico(I.sort), document.createTextNode(labelsOldest ? 'Oldest first' : 'Newest first'));
            oldf.title = 'Flip the queue order';
            oldf.onclick = () => { labelsOldest = !labelsOldest; renderLabels(); };
            bar.append(oldf);
            const sizeSel = el('select', 'lbl-size'); sizeSel.title = 'Label stock size'; sizeSel.setAttribute('aria-label', 'Label stock size');
            const savedSize = (shippingCfg && shippingCfg.label_size_production) || '4x4';
            Object.keys(LABEL_SIZES).forEach(k => {
                const opt = el('option', null, LABEL_SIZES[k].label
                    + (k === savedSize ? '  (default)' : '')); opt.value = k;
                if (k === prodSize()) opt.selected = true;
                sizeSel.append(opt);
            });
            sizeSel.title = 'Label stock for this print. The default is set in Shipping settings.';
            sizeSel.onchange = function () {
                labelSizeOverride = (this.value === savedSize) ? '' : this.value;
                renderLabels();
            };
            bar.append(sizeSel);
            const cov = textButton(); cov.append(ico(I.check), document.createTextNode('Size check'));
            cov.title = 'Run the last 200 orders through the size list and report any model that fails to match';
            cov.onclick = runCoverage;
            tools.append(cov);
            const day = textButton(); day.append(ico(I.grid), document.createTextNode('Day sheet'));
            day.title = 'Print one A4 cut list of everything not yet made';
            day.onclick = printDaySheet;
            tools.append(day);
            const dm = textButton(); dm.append(ico(I.truck || I.box), document.createTextNode('Dispatch manifest'));
            dm.title = 'Everything booked on a day: driver handover and invoice check';
            dm.onclick = openDispatchManifest;
            const su = textButton(); su.append(ico(I.box), document.createTextNode('Stock usage'));
            su.title = 'Glass used by everything marked made on a chosen day';
            su.onclick = openStockUsage;
            const mg = textButton(); mg.append(ico(I.spark || I.box), document.createTextNode('Margins'));
            mg.title = 'What each dispatched order actually made after goods and carriage';
            mg.onclick = openMargins;
            tools.append(dm, su, mg);
            const upBtn = textButton(); upBtn.append(ico(I.plus), document.createTextNode('Update size list'));
            upBtn.title = 'Replace the gobo size sheet with a new CSV export. The current one is kept as a backup.';
            const fileIn = document.createElement('input');
            fileIn.type = 'file'; fileIn.accept = '.csv,text/csv'; fileIn.style.display = 'none';
            upBtn.onclick = () => fileIn.click();
            fileIn.onchange = async () => {
                const f = fileIn.files && fileIn.files[0];
                fileIn.value = '';
                if (!f) return;
                if (f.size > 2 * 1024 * 1024) { addToast('That file is over 2 MB.'); return; }
                const text = await f.text();
                if (!await uiConfirm('Replace the size list with "' + f.name + '"? The current sheet is kept as a backup and a size check runs after.', { title: 'Replace size list', okText: 'Replace' })) return;
                upBtn.disabled = true;
                try {
                    const r = await api('/api/gobo-sizes/upload', { csv: text });
                    addToast('Size list updated: ' + r.models_after + ' models (was ' + r.models_before + ')'
                        + (r.dead_aliases ? '. ' + r.dead_aliases + ' alias(es) need attention.' : '.'));
                    labelsCache = null;
                    loadLabels(true);
                    runCoverage();
                } catch (e) { toastError(e.message || 'Upload failed'); }
                upBtn.disabled = false;
            };
            tools.append(upBtn, fileIn);
            const shipBtn = textButton(); shipBtn.append(ico(I.truck || I.box), document.createTextNode('Shipping settings'));
            shipBtn.title = 'Connect World Options and set your dispatch address, boxes and options';
            shipBtn.onclick = openShippingSettings;
            tools.append(shipBtn);
            /* The header, a partial sweep's warning and the queue bar stay fixed
               at the top; the strip, the size check and the queue are cards the
               grid can move, each spanning the row. A selected order's preview,
               appended to the page below 1500px, stays fixed at the foot. */
            /* A check that could not read every open order says so even when
               it found nothing: silence there reads as "none are missing". */
            const lm = labelsMissing && labelsMissing.data;
            const missNote = lm && !(lm.missing || []).length && lm.truncated
                ? el('div', 'cov-note', 'First ' + lm.checked + ' open orders checked: none missing the tag.') : null;
            if (lm && ((lm.missing || []).length || missNote)) box.append(widget(missNote || missingStrip(), 'missing', 'full', 'Possibly missing from production'));
            if (labelsCoverage) box.append(widget(coverageCard(), 'size-check', 'full', 'Size list coverage'));

            /* The queue, composed the way the reference composes a list page: a
               counted title with one line saying what this queue is, the few
               actions the bench actually presses beside it, the search and the
               filters on a toolbar under that, then the list.

               It was twenty controls across two bars, which is the same as no
               order at all: everything looked equally important, so nothing
               did. Nothing has been taken away, only sorted. */
            const qCard = el('div', 'card q-card');
            /* No title: the counters carry the count it gave. One order opened
               from Shopify says so. */
            if (data.single) qCard.append(el('p', 'q-note', 'One order, opened from Shopify. Refresh for all.'));
            const more = textButton(null);
            /* The house menu trigger: its name, then the caret, like Manage and
               the filters. A grid icon read as a view switch. */
            more.classList.add('more-btn'); more.setAttribute('aria-label', 'More');
            more.append(el('span', 'more-txt', 'More'), ico(I.chevDown), ico(I.moreH));
            more.title = 'Reports and setup';
            more.onclick = () => dropMenu(more, [
                { label: 'Size check', icon: I.ruler, title: cov.title, onClick: runCoverage },
                { label: 'Day sheet', icon: I.printer, title: day.title, onClick: printDaySheet },
                { label: 'Dispatch manifest', icon: I.truck, title: dm.title, onClick: openDispatchManifest },
                { label: 'Stock usage', icon: I.box, title: su.title, onClick: openStockUsage },
                { label: 'Margins', icon: I.card, title: mg.title, onClick: openMargins },
                '-',
                { label: 'Size rules', icon: I.edit,
                  title: 'The sizes and names you have set by hand, and the way to undo one',
                  onClick: openSizeRulesModal },
                { label: 'Update size list', icon: I.upload, title: upBtn.title, onClick: () => fileIn.click() },
                { label: 'Shipping settings', icon: I.settings, title: shipBtn.title, onClick: openShippingSettings },
            ]);
            /* The page's own actions ride in its header (the mix, spec 8.2), in
               the order they always had. */
            [pnBtn, coll, newShip, more].filter(Boolean).forEach(b => heroActs.append(b));
            qCard.append(tableTools([findWrap, filtTabs],
                                    [allBtn, slBtn, oldf, sizeSel].filter(Boolean)));
            qCard.append(fileIn);          // the hidden picker More reaches for
            box.append(widget(qCard, 'queue'));

            if (!orders.length) {
                /* One line and the way on (the mix, spec 6 and 7). */
                const goUnproc = textButton(); goUnproc.type = 'button';
                goUnproc.append(ico(I.clock), document.createTextNode('Go to Unprocessed'));
                goUnproc.onclick = () => { queueMode = 'unprocessed'; labelsCache = null; labelSel = null; labelsFilter = 'all'; loadLabels(true); };
                qCard.append(emptyState(dispatched ? { icon: I.check, text: 'Nothing dispatched yet.' }
                    : shipMode ? { icon: I.truck, text: 'Nothing ready to ship.' }
                    : unproc ? { icon: I.clock, text: 'Nothing waiting to be released.' }
                    : { icon: I.printer, text: 'Nothing on the bench.', action: goUnproc }));
                return;
            }
            if (!shown.length) {
                qCard.append(el('div', 'empty', labelsSearch
                    ? ('Nothing in this queue matches \u201c' + labelsSearch + '\u201d.')
                    : (labelsFilter === 'unprinted' ? 'Every live order has been printed.' : 'Every live order is marked made.')));
                return;
            }
            /* The opened order's label goes under its own row at every width
               (Cameron's ruling, 12 Oct 2026): a two-column band, the label and
               beside it its words and Print this label, on the page's own
               column. The pane beside the queue from 1500px went with it. The
               list is its own container, so the rows are laid out by the width
               they actually get. */
            const listBox = el('div', 'lbl-list'); const list = el('div', 'lbl-grid'); listBox.append(list);
            qCard.append(listBox);
            shown.forEach(o => {
                const st = prodStateOf(o);
                // In the Complete queue "fulfilled" is the expected state, not staleness.
                const staleStatus = dispatched && o.status === 'fulfilled' ? '' : o.status;
                const row = el('div', 'lbl-row lbl-qrow' + (labelSel === o.id ? ' on' : '') + (staleStatus || (st.made_at && !dispatched) ? ' stale' : ''));
                /* Not a pretend button (it holds the order link and the actions):
                   the keyboard opens a row's preview with its Preview button. */
                row.append(orderA(orderNo(o), o.admin_url, 'lbl-num lbl-num-link'));
                const who = el('div', 'lbl-who');
                const nameLine = el('span', 'lbl-nameline');
                nameLine.append(el('span', 'lbl-name', o.display_name));
                if (staleStatus) nameLine.append(el('span', 'lbl-chip bad', cap(staleStatus)));
                if (o.due_soon && !o.status) {
                    const overdue = o.due && (new Date(o.due + 'T00:00:00') - Date.now() < -86400000);
                    nameLine.append(el('span', 'lbl-chip ' + (overdue ? 'bad' : 'warn'), 'Due ' + (o.due_label || '')));
                }
                if (!o.status && !st.made_at && ageDays(o.created_at) >= 4) nameLine.append(el('span', 'lbl-chip warn', ageDays(o.created_at) + 'd'));
                if (o.note) nameLine.append(el('span', 'lbl-chip note', 'Note'));
                const dsp = dispatchStateOf(o);
                if (dsp.tracking_number) {
                    // A booked label is preparation: the order only counts as dispatched
                    // once it is made, which is what fulfils Shopify.
                    const booked = !dsp.fulfilled && !dsp.canceled;
                    // The courier's name rides in the chip: on a tablet there is no
                    // hover, so a tooltip is the same as not saying it at all.
                    const who = dsp.carrier_label || carrierLabel(dsp.carrier_name || '');
                    const state = dsp.canceled ? 'Cancelled' : booked ? 'Booked' : 'Dispatched';
                    const dc = el('span', 'lbl-chip ' + (dsp.canceled ? 'bad' : booked ? 'note' : 'made'),
                        who ? state + ' \u00b7 ' + who : state);
                    dc.title = shipmentName(dsp)
                        + ' · ' + dsp.tracking_number + (dsp.dispatched_at ? ' · ' + fmtDate(dsp.dispatched_at) : '')
                        + (booked ? '. Mark this order made to fulfil it in Shopify and email the customer.' : '');
                    nameLine.append(dc);
                }
                /* A toast is gone the moment the page moves on, and the
                   background half of a big print run has no toast at all. The
                   order itself carries the problem until the terms are on it. */
                if (st.terms_error) {
                    const tc = el('span', 'lbl-chip bad', 'No terms');
                    tc.title = st.terms_error + ' Release this order again to retry.';
                    nameLine.append(tc);
                }
                if (st.made_at && !dsp.tracking_number) nameLine.append(el('span', 'lbl-chip made', 'Made'));
                else if (st.printed_at && !dsp.tracking_number) {
                    const pc = el('span', 'lbl-chip note', 'Printed');
                    pc.title = 'Printed ' + fmtDate(st.printed_at);
                    nameLine.append(pc);
                }
                who.append(nameLine);
                const pcs = (o.items || []).reduce((s, it) => s + (it.quantity || 1), 0);
                who.append(el('span', 'sub', (o.is_company ? 'Company' : 'Customer') + '  ·  '
                    + o.items.length + (o.items.length === 1 ? ' item' : ' items')
                    + '  ·  ' + pcs + (pcs === 1 ? ' pc' : ' pcs')));
                row.append(who);
                row.append(el('div', 'lbl-meta', fmtDate(o.created_at)));
                const acts = el('div', 'lbl-actions');
                const pv = textButton(null); pv.title = labelSel === o.id ? 'Hide label preview' : 'Preview label';
                /* Preview and Hide hold one width (the mix, spec 6), so no column
                   moves when a row opens: both words lie in one cell and the one
                   not in use is hidden. */
                const pvOn = labelSel === o.id;
                const pvTxt = el('span', 'lbl-btn-txt swap');
                pvTxt.append(el('span', pvOn ? 'gone' : null, 'Preview'), el('span', pvOn ? null : 'gone', 'Hide'));
                pv.append(ico(pvOn ? I.eyeOff : I.eye), pvTxt);
                pv.setAttribute('aria-expanded', pvOn ? 'true' : 'false');
                pv.onclick = (e) => { e.stopPropagation(); labelSel = (labelSel === o.id ? null : o.id); renderLabels(); };
                acts.append(pv);
                if (canEditOrders() && o.status !== 'cancelled') {
                    const ed = textButton(null); ed.title = 'Change the delivery address or contact details';
                    ed.append(ico(I.edit), el('span', 'lbl-btn-txt', 'Edit'));
                    ed.onclick = (e) => { e.stopPropagation(); openOrderEdit(o); };
                    acts.append(ed);
                }
                if (o.proposal_url) {
                    const pf = textButton(null); pf.title = 'Preview the proposal proof';
                    pf.append(ico(I.globe), el('span', 'lbl-btn-txt', 'Proof'));
                    pf.onclick = (e) => { e.stopPropagation(); openProposal(o); };
                    acts.append(pf);
                }
                const pr = textButton(null); pr.title = 'Print label'; pr.append(ico(I.printer), el('span', 'lbl-btn-txt', 'Print'));
                /* The open order's Print is the screen's one primary action (the
                   mix, spec 8.2), unless its row has its own: To ship's Dispatch,
                   Unprocessed's Ready to make. */
                if (pvOn && !unproc && !shipMode) pr.classList.add('btn-primary');
                pr.onclick = (e) => { e.stopPropagation(); printLabels([o]); };
                acts.append(pr);
                if (unproc) {
                    // The release gate: out of Unprocessed, into To make. Same
                    // tag move the amber strip's Add to queue performs.
                    if (!o.status) {
                        const rd = textButton(null, { kind: 'primary' });
                        rd.title = 'Remove the Unprocessed tag and add IP, so this order joins To make';
                        rd.append(ico(I.check), el('span', 'lbl-btn-txt', 'Ready to make'));
                        rd.onclick = (e) => { e.stopPropagation(); readyToMake(o, rd); };
                        rd.classList.add('grp');   /* a state change starts its own group */
                        acts.append(rd);
                    }
                } else {
                if (o.status !== 'cancelled') {
                    const dispatched = !!dsp.tracking_number && !dsp.canceled;
                    const db = textButton(null, { kind: !dispatched && queueMode === 'ship' ? 'primary' : '', cls: dispatched ? 'on' : '' });
                    db.title = dispatched ? 'View shipment / reprint label' : 'Dispatch a courier for this order';
                    db.append(ico(I.truck), el('span', 'lbl-btn-txt', dispatched ? 'Shipment' : 'Dispatch'));
                    db.onclick = (e) => { e.stopPropagation(); openDispatch(o); };
                    db.classList.add('grp');   /* a state change starts its own group */
                    acts.append(db);
                }
                if (!o.status) {
                    const mk = textButton(null, { cls: st.made_at ? 'on' : '' });
                    mk.title = st.made_at ? 'Made ' + fmtDate(st.made_at) + '. Click to unmark.' : 'Mark this order as made';
                    mk.append(ico(I.check), el('span', 'lbl-btn-txt', st.made_at ? 'Made' : 'Mark made'));
                    mk.onclick = (e) => { e.stopPropagation(); toggleMade(o); };
                    acts.append(mk);
                }
                }
                row.append(acts);
                row.onclick = () => { labelSel = (labelSel === o.id ? null : o.id); renderLabels(); };
                list.append(row);
                if (labelSel === o.id) {
                    const wrap = el('div', 'lbl-preview');
                    /* The open row and its preview are one block (the mix, spec
                       8.2): the teal wash and the teal bar run on under the row. */
                    if (o.customer_id) wrap.append(histLine(o));
                    const sheet = labelSheet(o);
                    /* The label in a frame with its own shadow. The sheet inside
                       is the print's, untouched. */
                    const frame = el('figure', 'lbl-frame'); frame.append(sheet);
                    wrap.append(frame);
                    const note = el('div', 'lbl-preview-note'); wrap.append(note);
                    const act = el('div', 'lbl-toolbar');
                    /* Not a second primary: the open row's Print is the one. */
                    const p2 = textButton(); p2.append(ico(I.printer), document.createTextNode('Print this label'));
                    p2.onclick = () => printLabels([o]);
                    act.append(p2); wrap.append(act);
                    /* Under its own row, where it is seen, not after the whole queue card. */
                    row.after(wrap);
                    // Must run after it is in the document, or there is nothing to measure.
                    // Re-measured once the label typeface arrives: until then the metrics
                    // are the fallback font's and the shrink figure would be wrong.
                    const applyFit = () => {
                        const fit = fitLabel(sheet);
                        const d = labelDims();
                        note.textContent = 'Actual size preview: ' + d.label
                            + (fit.pct < 100 ? '. Text shrunk to ' + fit.pct
                               + '% so the whole order fits one label.' : '.');
                        note.classList.toggle('bad', fit.clipped);
                        if (fit.clipped) {
                            // Never let the bench print a cut list that is missing
                            // rows without knowing it.
                            note.textContent = 'This order does not fit on ' + d.label
                                + ' - some rows would be cut off the printed label. '
                                + 'Choose a larger stock size before printing.';
                        }
                    };
                    applyFit();
                    if (document.fonts && document.fonts.load) {
                        document.fonts.load("15px 'Bricolage Grotesque'").then(() => { if (sheet.isConnected) applyFit(); }, () => {});
                    }
                }
            });
        }
        /* Size-list coverage: run recent orders through the same lookup the labels
           print with, so a CSV update can be sanity-checked against real orders. */
        let labelsCoverage = null;   // 'busy' | { data, at } | { error, at }
        /* Whether THIS account may settle a flagged model. Read from the server
           rather than inferred from the role: the grant is per person, so an
           admin's answer is not everyone's. Defaults to false, so a failed read
           hides the button instead of offering one the server will refuse. */
        let sizeRulesCanEdit = false, sizeRulesAsked = false;
        /* Asked once, whenever a coverage card is drawn - NOT only when the
           merchant runs the check by hand. The weekly scan raises the alert on
           its own, so the card is often on screen without runCoverage ever
           having been called in this session, and gating the answer on that
           hid the Resolve button from people who hold the grant. */
        async function loadSizeRulePerm() {
            if (sizeRulesAsked) return;
            sizeRulesAsked = true;
            try { sizeRulesCanEdit = !!(await api('/api/gobo-sizes/rules', {})).can_edit; }
            catch (e) { sizeRulesCanEdit = false; return; }
            if (sizeRulesCanEdit && labelsCoverage && labelsCoverage !== 'busy' && labelsCache) renderLabels();
        }
        async function runCoverage() {
            if (labelsCoverage === 'busy') return;
            labelsCoverage = 'busy';
            // Only repaint now if an order fetch does not own the view (mirrors the
            // final repaint): after an upload the cache is null and reloading.
            if (!labelsLoading && labelsCache) renderLabels();
            try {
                const data = await api('/api/production-labels/coverage', { orders: 200 });
                labelsCoverage = { data, at: Date.now() };
            } catch (e) {
                labelsCoverage = { error: e.message || String(e), at: Date.now() };
            }
            if (!labelsLoading && labelsCache) renderLabels();
        }
        window.__demoCoverage = d => { labelsCoverage = { data: d, at: Date.now() }; if (labelsCache) renderLabels(); };
        /* Courier-split label printing, driven without a Shopify order behind
           it: the grouping and the picker are the parts worth proving. */
        window.__demoShipLabels = (dispatch, orders) => {
            /* Calls the REAL predicate. A hook with its own copy of the filter
               tests the copy, and lets a regression through the one that
               actually decides what gets printed. */
            labelsCache = { data: { dispatch: dispatch || {} } };
            const eligible = (orders || []).filter(shipLabelEligible);
            printShippingLabelsFor(eligible);
            return eligible.length;
        };
        /* Resolving a flagged model, from inside the app. Until this existed the
           weekly alert could only be dismissed: the actual fix lived in a CSV on
           the data volume, so "New model not matching the size list" was a
           notification with nowhere to go. Each choice writes one row to the same
           rule files the size lookup already reads. */
        /* The rules the merchant has already made, and the way to undo one.
           The server has had `remove` and the rules listing since the Resolve
           dialog was built; without this the feature was one-way, so a mistyped
           production size could be set from the app but only corrected by
           editing a CSV on the volume - which is the exact thing Resolve was
           added to stop. */
        /* uid -> colour name, off the board the Inbox already loads. */
        function mailColour(uid) {
            const team = (mailCache && mailCache.team) || [];
            const m = team.find(p => p.uid === uid);
            return m ? m.colour : '';
        }

        const TEAM_TINTS = ['red', 'orange', 'yellow', 'green', 'blue',
                            'purple', 'pink', 'brown'];
        /* A colour NAME becomes a class name, and an unknown one becomes
           nothing at all. No value from the server ever reaches a style
           property - that is the whole defence. */
        function ownClass(colour) {
            const c = String(colour || '').toLowerCase();
            return TEAM_TINTS.indexOf(c) >= 0 ? ' own-' + c : '';
        }

        function openSizeRulesModal() {
            const win = dialog({ title: 'Size rules' });
            const { overlay, modal, head, x, body } = win;
            const srT = win.heading;

            const draw = async () => {
                body.innerHTML = '';
                const t = el('div', 'thinking'); t.append(loader(), el('span', null, 'Reading the rules…'));
                body.append(t);
                let res;
                try { res = await api('/api/gobo-sizes/rules', {}); }
                catch (e) {
                    body.innerHTML = '';
                    body.append(el('div', 'msg error', e.message || String(e)));
                    return;
                }
                body.innerHTML = '';
                const canEdit = !!res.can_edit;
                const overrides = res.overrides || [], aliases = res.aliases || [];
                if (!overrides.length && !aliases.length) {
                    body.append(el('div', 'empty',
                        'No rules yet. They are made from Resolve on a flagged model in the size check.'));
                    return;
                }
                if (!srT.parentNode.classList.contains('title-row')) titleInfo(srT, infoButton('About size rules', { title: 'Size rules', body:
                    'These sit on top of the size list and survive replacing it. '
                    + (canEdit ? 'Removing one puts the model back to whatever the sheet says.'
                               : 'An admin can grant you access to change them on the Team tab.') }));

                const section = (title, rows, kind) => {
                    if (!rows.length) return;
                    body.append(el('div', 'section-title', title));
                    const wrap = el('div', 'files-list');
                    rows.forEach(r => {
                        const mfr = r['Manufacturer'] || '';
                        const model = kind === 'alias' ? (r['Store Model'] || '') : (r['Model'] || '');
                        const rhs = kind === 'alias'
                            ? 'reads as ' + (r['List Model'] || '')
                            : ((r['Production Size (mm)'] || '') === 'exclude'
                                ? 'not a gobo'
                                : (r['Production Size (mm)'] || '') + ' mm'
                                  + (r['Customer Email Domain'] ? ' for @' + r['Customer Email Domain'] : ''));
                        const line = el('div', 'files-row');
                        const left = el('div', 'flex-1-fit');
                        left.append(el('div', 'files-name', (mfr ? mfr + ' · ' : '') + model));
                        left.append(el('div', 'field-help', rhs));
                        line.append(left);
                        if (canEdit) {
                            const del = textButton('Remove');
                            del.onclick = async () => {
                                if (!await uiConfirm('Remove the rule for "' + model + '"? It goes back to '
                                    + 'whatever the size list says, which may be nothing.',
                                    { title: 'Remove size rule', okText: 'Remove' })) return;
                                del.disabled = true;
                                try {
                                    await api('/api/gobo-sizes/rule',
                                              { op: 'remove', kind: kind, manufacturer: mfr, model: model,
                                                domain: r['Customer Email Domain'] || '' });
                                } catch (e) { toastError(e.message); del.disabled = false; return; }
                                toastOk('Rule removed.');
                                draw();
                            };
                            line.append(del);
                        }
                        wrap.append(line);
                    });
                    body.append(wrap);
                };
                section('Sizes set by hand', overrides, 'override');
                section('Other names for a model on the list', aliases, 'alias');
            };
            draw();
        }

        function openSizeRuleModal(row, onSaved) {
            const win = dialog({ title: 'Resolve ' + (row.model || 'this model') });
            const { overlay, modal, head, x, body } = win;
            const close = win.close;
            // X only: a misclick must not discard a half-filled ruling.

            body.append(el('p', 'field-help',
                (row.manufacturer ? row.manufacturer + ' · ' : '') + (row.model || '')
                + (row.reason ? ': ' + row.reason : '')));

            let pick = 'set';
            const panes = {};
            const radios = [];
            const choose = (k) => {
                pick = k;
                Object.keys(panes).forEach(n => { panes[n].style.display = (n === k ? '' : 'none'); });
                radios.forEach(r => { r.checked = (r.value === k); });
            };
            const opt = (k, label, build) => {
                const wrapL = tickRow('sr-opt');
                const r = document.createElement('input');
                r.type = 'radio'; r.name = 'sizerule'; r.value = k; r.checked = (k === 'set');
                r.onchange = () => choose(k);
                radios.push(r);
                wrapL.append(r, el('span', null, label));
                body.append(wrapL);
                const pane = el('div', 'sr-pane');
                build(pane);
                panes[k] = pane;
                body.append(pane);
            };

            // 1. A size of its own.
            let sizeIn, domIn;
            opt('set', 'Give it a production size', (pane) => {
                const f = formField('Production size (mm)');
                sizeIn = el('input', 'psel'); sizeIn.type = 'text';
                sizeIn.placeholder = 'e.g. 37.5'; sizeIn.inputMode = 'decimal';
                f.append(sizeIn); pane.append(f);
                const f2 = formField('Only for one customer (optional)');
                domIn = el('input', 'psel'); domIn.type = 'text';
                domIn.placeholder = 'their email domain, e.g. acme.co.uk';
                f2.append(domIn); pane.append(f2);
                pane.append(el('div', 'field-help', 'Leave the customer blank to apply it to every order.'));
            });

            // 2. Another name for something already on the sheet.
            let target = null, targetLine;
            opt('alias', 'It is another name for a model already on the list', (pane) => {
                const f = formField('Search the size list');
                const q = el('input', 'psel'); q.type = 'text';
                q.placeholder = 'Start typing a model on the list…';
                f.append(q); pane.append(f);
                const hits = el('div', 'sr-hits'); pane.append(hits);
                targetLine = el('div', 'field-help'); pane.append(targetLine);
                let seq = 0;
                q.oninput = async () => {
                    const mine = ++seq;
                    const term = q.value.trim();
                    if (term.length < 2) { hits.innerHTML = ''; return; }
                    let res;
                    try { res = await api('/api/gobo-sizes/models', { q: term }); }
                    catch (e) { return; }
                    if (mine !== seq) return;   // a slower earlier search must not win
                    hits.innerHTML = '';
                    (res.models || []).forEach(m => {
                        const b = textButton(null, { cls: 'sr-hit' });
                        b.textContent = (m.manufacturer ? m.manufacturer + ' · ' : '') + m.model
                            + (m.size ? '  (' + m.size + ' mm)' : '');
                        b.onclick = () => {
                            target = m;
                            targetLine.textContent = 'Will read as: ' + m.model
                                + (m.size ? ', ' + m.size + ' mm' : '');
                            [...hits.children].forEach(c => c.classList.remove('on'));
                            b.classList.add('on');
                        };
                        hits.append(b);
                    });
                    if (!(res.models || []).length) hits.append(el('div', 'field-help', 'Nothing on the list matches that.'));
                };
            });

            // 3. Not a gobo at all.
            opt('exclude', 'It is not a gobo, stop reporting it', (pane) => {
                /* The consequence stays as the line (copy plan, Other dialogs #20). */
                const ng = el('div', 'field-help', 'Its labels print no size from now on.');
                ng.append(infoButton('What this changes', { title: 'Not a gobo', body:
                    'Items on this model stop counting towards size-list coverage, so it '
                    + 'will not be reported again, and their labels print no size and no CHECK. '
                    + 'It does not change anything already printed.' }));
                pane.append(ng);
            });

            choose('set');

            const foot = el('div', 'modal-foot');
            const save = textButton('Save rule', { kind: 'primary' });
            const cancel = textButton('Cancel'); cancel.onclick = close;
            save.onclick = async () => {
                const req = { manufacturer: row.manufacturer || '', model: row.model || '' };
                if (pick === 'set') {
                    req.op = 'set'; req.size = sizeIn.value;
                    if (domIn.value.trim()) req.domain = domIn.value;
                } else if (pick === 'alias') {
                    if (!target) { toastError('Pick the model on the list it should read as.'); return; }
                    /* The manufacturer stays the one the ORDERS carry. That
                       column is what the store's spelling gets indexed under, so
                       writing the target's here would file the alias under a
                       maker the orders never say, and the rule would never match
                       the items it was added to fix. The target is found by its
                       model name regardless. */
                    req.op = 'alias'; req.list_model = target.model;
                } else {
                    req.op = 'exclude';
                }
                save.disabled = true; cancel.disabled = true;
                let res;
                try { res = await api('/api/gobo-sizes/rule', req); }
                catch (e) { toastError(e.message); save.disabled = false; cancel.disabled = false; return; }
                /* Report what the LOOKUP says, not what was asked for. A rule can
                   save cleanly and still leave the model unresolved - an alias onto
                   a row that is itself ambiguous, for instance - and saying "done"
                   there would send a wrong size to the bench. */
                if (req.op === 'exclude') toastOk(row.model + ' will not be reported again.');
                else if (res.resolves) toastOk(row.model + ' now resolves to ' + (res.size || 'a size') + ' mm.');
                else toastError('Saved, but ' + row.model + ' still does not resolve: '
                                + (res.reason || 'unknown reason'));
                close();
                if (onSaved) onSaved(res);
            };
            foot.append(cancel, save);
            modal.append(foot);
            (sizeIn || modal).focus();
        }

        function coverageCard() {
            loadSizeRulePerm();
            const card = el('div', 'card');
            if (labelsCoverage === 'busy') {
                const t = el('div', 'thinking');
                t.append(loader(), el('span', null, 'Checking the last 200 orders against the size list…'));
                card.append(t);
                return card;
            }
            const head = el('div', 'cov-head');
            head.append(el('h3', null, 'Size list coverage'));
            const x = iconButton(I.x, 'Dismiss', { size: 'small' });
            x.onclick = () => { labelsCoverage = null; renderLabels(); };
            head.append(x);
            card.append(head);
            if (labelsCoverage.error) {
                card.append(el('div', 'cov-line', labelsCoverage.error));
                return card;
            }
            const d = labelsCoverage.data;
            card.append(el('div', 'cov-line',
                'Scanned ' + d.orders_scanned + ' orders · ' + d.gobo_items + ' gobo items · '
                + d.pct + '% resolve to a production size.'));
            if (!(d.flagged || []).length) {
                card.append(el('div', 'cov-ok', 'Every gobo item on these orders matches the size list. Nothing to fix.'));
            } else {
                const kt = dataTable(['Model as written on orders', 'Manufacturer', 'Why it flags', ['Items', 'num'], 'Seen on', null]);
                kt.wrap.classList.add('space-above-2-5');
                d.flagged.forEach(r => {
                    const tr = el('tr');
                    const c1 = el('td', 'kw', r.model); tr.append(c1);
                    tr.append(el('td', null, r.manufacturer || ''));
                    tr.append(el('td', null, r.reason));
                    const c4 = el('td', 'num', String(r.count)); tr.append(c4);
                    const seen = el('td');
                    (r.orders || []).forEach((o2, i2) => {
                        if (i2) seen.append(document.createTextNode(', '));
                        seen.append(typeof o2 === 'string' ? document.createTextNode(o2)
                                    : orderA(o2.name, o2.admin_url));
                    });
                    tr.append(seen);
                    /* The whole point of the table: a flagged model can be
                       settled here rather than in a CSV on the volume. Hidden
                       for anyone without the grant, because the server refuses
                       them anyway and a button that always errors is worse than
                       no button. */
                    const act = el('td');
                    /* A gobo sold with a projector that its order cannot size
                       (no projector on it, or two sizes) is not a gap in the
                       size list: a size rule would not settle it. */
                    if (sizeRulesCanEdit && !r.order_problem) {
                        const fix = textButton('Resolve');
                        fix.onclick = () => openSizeRuleModal(r, () => runCoverage());
                        act.append(fix);
                    }
                    tr.append(act);
                    kt.add(tr);
                });
                card.append(kt.wrap);
            }
            if (d.skipped_no_model) {
                card.append(el('div', 'cov-note', d.skipped_no_model + ' items with no gobo options (accessories and plain products) were not counted.'));
            }
            return card;
        }
        // Builds the label: the merchant's own design (logo, big company name, an
        // "Order:" line, then one-line rows of qty+size in bold, a glass-type chip,
        // and the artwork title in quotes). This same markup is what gets printed.
        function labelSheet(o) {
            const s = el('div', 'label-sheet');
            const d = labelDims();
            s.style.width = d.w + 'mm'; s.style.height = d.h + 'mm';
            if (d.h <= 60) s.classList.add('compact');   // short stock needs the tighter layout
            if (o.status === 'cancelled' || o.status === 'refunded') {
                s.append(el('div', 'ls-dead', 'DO NOT MAKE - ' + o.status.toUpperCase()));
            }
            const top = el('div', 'ls-top');
            const lg = el('div', 'ls-logo'); lg.innerHTML = LABEL_LOGO;   // trusted static markup
            const ono = el('div', 'ls-ono', 'Order: ' + orderNo(o));
            if (o.due_label) ono.append(el('span', 'ls-due' + (o.due_soon ? ' soon' : ''), 'Required by: ' + o.due_label));
            top.append(lg, el('div', 'ls-company', o.display_name), ono);
            s.append(top);
            const ul = el('ul');
            (o.items || []).forEach(it => {
                const li = el('li', 'ls-row');
                const row = el('div', 'ls-it' + (it.review_reason ? ' wrap' : ''));
                if (it.review_reason) {
                    // Flagged rows may wrap: the reason must be readable, never ellipsized.
                    row.append(el('span', 'ls-iqs', it.quantity + 'x'));
                    row.append(el('span', 'ls-chip fl', 'CHECK'));
                    row.append(el('span', 'ls-desc', it.review_reason));
                    li.append(row);
                } else {
                    /* A row with no size (a projector, an accessory, a stock
                       gobo) has nothing to line up with: its name starts after
                       the count and wraps, rather than being cut short after a
                       gap (#104453's projector). */
                    if (!it.production_size) row.classList.add('named', 'wrap');
                    row.append(el('span', 'ls-iqs',
                        it.quantity + 'x' + (it.production_size ? ' ' + it.production_size + 'mm' : '')));
                    if (it.glass_type) row.append(el('span', 'ls-chip', it.glass_type));
                    const art = ('artwork' in it) ? it.artwork : (it.title || '');
                    if (art) row.append(el('span', 'ls-desc', '"' + art + '"'));
                    li.append(row);
                    if (it.size_note) li.append(el('div', 'ls-ctx', it.size_note));
                }
                ul.append(li);
            });
            s.append(ul);
            if (o.note) {
                const on = el('div', 'ls-onote');
                on.append(el('b', null, 'Note: '), document.createTextNode(o.note));
                s.append(on);
            }
            const rate = el('div', 'ls-rate');
            const rt = el('div', 'ls-rt');
            rt.append(el('div', 'ls-r1', '★★★★★ 5 Star Service'));
            const r2 = el('div', 'ls-r2');
            r2.append(document.createTextNode('Leave us a review on '), el('b', null, 'Trustpilot'));
            rt.append(r2);
            rate.append(rt);
            s.append(rate);
            return s;
        }
        /* Estimated stock usage: glass blanks consumed by everything marked made
           on a chosen day (UK time), summed by size and glass type. */
        function openMargins() {
            const win = dialog({ title: 'Margins', size: 'disp-modal' });
            const { overlay, modal, head, x, body } = win;
            const bar = el('div', 'lbl-toolbar');
            const sel = document.createElement('select'); sel.className = 'lbl-size'; sel.setAttribute('aria-label', 'Orders booked on');
            [[30, 'Last 30 days'], [60, 'Last 60 days'], [90, 'Last 90 days'], [365, 'Last year']]
                .forEach(([v, t]) => { const o = el('option', null, t); o.value = v; sel.append(o); });
            bar.append(el('span', 'cov-line', 'Orders booked on'), sel);
            body.append(bar);
            const out = el('div'); body.append(out);
            let req = 0;
            const money = (v, cur) => (v == null ? '' : fmtPrice(v, cur || 'GBP'));
            async function load() {
                out.innerHTML = '';
                const t = el('div', 'thinking'); t.append(loader(), el('span', null, 'Working out what each order made\u2026')); out.append(t);
                const rq = ++req;
                try {
                    const d = await api('/api/margin', { days: parseInt(sel.value, 10) });
                    if (rq !== req) return;
                    out.innerHTML = '';
                    if (!d.rows.length) { out.append(el('div', 'cov-line', d.note || 'Nothing dispatched in this period.')); return; }
                    const tt = d.totals || {};
                    const head2 = el('div', 'disp-dest');
                    head2.append(el('div', null, tt.counted + ' of ' + tt.orders + ' dispatched orders costed'));
                    head2.append(el('div', 'sub', 'Revenue ' + money(tt.revenue) + ' \u00b7 goods ' + money(tt.goods_cost)
                        + ' \u00b7 couriers ' + money(tt.courier_cost)));
                    const m = el('div', 'pm-kept-line');
                    m.textContent = 'Kept ' + money(tt.margin) + (tt.margin_pct != null ? '  (' + tt.margin_pct + '%)' : '');
                    head2.append(m);
                    out.append(head2);
                    const kt = dataTable(['Order', 'Customer', 'Sent', ['Revenue', 'num'], ['Goods', 'num'], ['Courier', 'num'], ['Kept', 'num'], ['%', 'num']]);
                    d.rows.forEach(r => {
                        const tr = el('tr');
                        if (r.incomplete) {
                            tr.style.opacity = '.6';
                            const oc0 = el('td', 'kw'); oc0.append(orderA(r.order_name, r.admin_url));
                            tr.append(oc0, el('td', null, r.customer || ''),
                                el('td', null, r.dispatched || ''));
                            const note = el('td', null, r.incomplete); note.colSpan = 5;
                            tr.append(note);
                        } else {
                            const kept = el('td', 'num', money(r.margin, r.currency));
                            if (r.margin < 0) kept.classList.add('tone-error');
                            const oc1 = el('td', 'kw'); oc1.append(orderA(r.order_name, r.admin_url));
                            tr.append(oc1, el('td', null, r.customer || ''),
                                el('td', null, r.dispatched || ''),
                                el('td', 'num', money(r.revenue + r.shipping_charged, r.currency)),
                                el('td', 'num', money(r.goods_cost, r.currency)),
                                el('td', 'num', money(r.courier_cost, r.currency)), kept,
                                el('td', 'num', r.margin_pct == null ? '' : r.margin_pct + '%'));
                        }
                        kt.add(tr);
                    });
                    out.append(kt.wrap);
                    if (d.orders_incomplete) out.append(el('div', 'cov-note',
                        d.orders_incomplete + ' order(s) could not be costed and are left out of the totals'
                        + (d.missing_cost && d.missing_cost.length
                            ? ': no cost price in Shopify for ' + d.missing_cost.join(', ') : '') + '.'));
                    if (tt.courier_inc_vat_rows) out.append(el('div', 'cov-note',
                        tt.courier_inc_vat_rows + ' order(s) were booked before the app stored the ex VAT courier '
                        + 'charge, so their carriage includes VAT and their margin is understated slightly.'));
                    if (d.truncated || d.fetch_failed) out.append(el('div', 'disp-warn',
                        'Some orders could not be loaded from Shopify, so this is incomplete. Try again shortly.'));
                    out.append(el('div', 'cov-note', 'Revenue and delivery are net of VAT and discounts. '
                        + 'Goods use the cost price on each product in Shopify. Labour is not included.'));
                } catch (e) {
                    if (rq !== req) return;
                    out.innerHTML = ''; out.append(el('div', 'cov-line', e.message || 'Could not load.'));
                }
            }
            sel.onchange = load;
            load();
        }
        function openDispatchManifest() {
            const win = dialog({ title: 'Dispatch manifest', size: 'wide' });
            const { overlay, modal, head, x, body } = win;
            const bar = el('div', 'lbl-toolbar');
            const dt = document.createElement('input');
            dt.type = 'date'; dt.className = 'lbl-size'; dt.setAttribute('aria-label', 'Date');
            dt.value = new Date().toLocaleDateString('en-CA');
            bar.append(el('span', 'cov-line', 'Everything booked on'), dt);
            const pr = textButton(); pr.append(ico(I.printer), document.createTextNode('Print'));
            pr.disabled = true;
            bar.append(pr);
            body.append(bar);
            const out = el('div'); body.append(out);
            let current = null, maniReq = 0;
            function money(v, cur) { return (v == null || v === '') ? '' : fmtPrice(parseFloat(v), cur || 'GBP'); }
            async function load() {
                out.innerHTML = ''; pr.disabled = true; current = null;
                const t = el('div', 'thinking'); t.append(loader(), el('span', null, 'Collecting the day\u2019s bookings\u2026')); out.append(t);
                const rq = ++maniReq;
                try {
                    const d = await api('/api/dispatch/manifest', { date: dt.value });
                    if (rq !== maniReq) return;
                    out.innerHTML = ''; current = d;
                    if (!d.rows.length) { out.append(el('div', 'cov-line', 'Nothing was booked on this day.')); return; }
                    const kt = dataTable(['Time', 'Order', 'Customer', 'Courier', 'Tracking', ['Courier ex VAT', 'num'], ['Customer paid', 'num']]);
                    d.rows.forEach(r => {
                        const tr = el('tr');
                        if (r.canceled) tr.style.opacity = '.45';
                        const om = el('td', 'kw'); om.append(orderA(r.order_name, r.admin_url));
                        if (r.canceled) om.append(document.createTextNode(' (cancelled)'));
                        tr.append(el('td', null, r.time), om,
                            el('td', null, r.customer),
                            el('td', null, [r.carrier, r.service].filter(Boolean).join(' ')),
                            el('td', null, r.tracking),
                            el('td', 'num', money(r.amount_ex_vat, r.currency)),
                            el('td', 'num', money(r.shipping_paid, r.currency)));
                        kt.add(tr);
                    });
                    out.append(kt.wrap);
                    const tt = d.totals || {};
                    const bits = [tt.shipments + (tt.shipments === 1 ? ' shipment' : ' shipments')];
                    if (tt.courier_ex_vat != null) bits.push('couriers ' + money(tt.courier_ex_vat) + ' ex VAT');
                    if (tt.customer_paid != null) bits.push('customers paid ' + money(tt.customer_paid));
                    if (tt.courier_ex_vat != null && tt.customer_paid != null) {
                        const diff = tt.customer_paid - tt.courier_ex_vat;
                        bits.push((diff >= 0 ? 'covered, ' : 'short by ') + money(Math.abs(diff)));
                    }
                    out.append(el('div', 'cov-note', bits.join(' \u00b7 ')
                        + '. Margin compares what customers paid for delivery with the ex VAT courier cost.'));
                    // This sheet is checked against the World Options invoice: a
                    // total that silently omits unpriced shipments reconciles and
                    // is wrong.
                    if (tt.totals_note) out.append(el('div', 'msg error', tt.totals_note));
                    const people = [...new Set(d.rows.filter(r => !r.canceled && r.by).map(r => r.by))];
                    if (people.length > 1) out.append(el('div', 'cov-note',
                        'Booked by ' + people.length + ' different people today.'));
                    pr.disabled = false;
                } catch (e) {
                    if (rq !== maniReq) return;
                    out.innerHTML = '';
                    out.append(el('div', 'cov-line', e.message || 'Could not load.'));
                }
            }
            pr.onclick = () => { if (current) printDispatchManifest(current); };
            dt.onchange = load;
            load();
        }
        function printDispatchManifest(d) {
            const box = $('label-print'); box.innerHTML = '';
            /* Landscape: eight columns of money and tracking need the full sheet. */
            const ds = el('div', 'day-sheet wide');
            ds.append(el('h1', null, 'Dispatch manifest'));
            const nice = new Date(d.date + 'T12:00:00').toLocaleDateString('en-GB',
                { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
            const tt = d.totals || {};
            ds.append(el('div', 'ds-meta', nice + ' \u00b7 ' + tt.shipments
                + (tt.shipments === 1 ? ' shipment' : ' shipments')));
            const tb = el('table', 'ds-table');
            tb.innerHTML = '<thead><tr><th>Time</th><th>Order</th><th>Customer</th><th>Courier</th>'
                + '<th>Tracking</th><th>Collection ref</th><th>Ex VAT</th><th>Paid</th></tr></thead>';
            const tbody = el('tbody');
            d.rows.filter(r => !r.canceled).forEach(r => {
                const tr = el('tr');
                tr.append(el('td', null, r.time), el('td', 'ds-size', r.order_name), el('td', null, r.customer),
                    el('td', null, [r.carrier, r.service].filter(Boolean).join(' ')),
                    el('td', null, r.tracking), el('td', null, r.collection_ref || ''),
                    el('td', 'ds-qty', r.amount_ex_vat == null ? '' : fmtPrice(parseFloat(r.amount_ex_vat), r.currency)),
                    el('td', 'ds-qty', !r.shipping_paid ? '' : fmtPrice(parseFloat(r.shipping_paid), r.currency)));
                tbody.append(tr);
            });
            tb.append(tbody); ds.append(tb);
            if (tt.courier_ex_vat != null || tt.customer_paid != null) {
                ds.append(el('div', 'ds-orders',
                    'Couriers ' + (tt.courier_ex_vat == null ? '?' : fmtPrice(tt.courier_ex_vat, 'GBP')) + ' ex VAT'
                    + '   Customers paid ' + (tt.customer_paid == null ? '?' : fmtPrice(tt.customer_paid, 'GBP'))));
            }
            box.append(ds);
            let rule = $('label-page-rule');
            if (!rule) { rule = document.createElement('style'); rule.id = 'label-page-rule'; document.head.append(rule); }
            rule.textContent = '@page { size: A4 landscape; margin: 12mm; }';
            const seq = ++printSeq;
            document.body.classList.add('printing-label');
            const cleanup = () => {
                if (seq !== printSeq) return;
                document.body.classList.remove('printing-label');
                box.innerHTML = '';
                const r = $('label-page-rule');
                if (r && r.parentNode) r.parentNode.removeChild(r);
            };
            if (window.onafterprint !== undefined) window.addEventListener('afterprint', cleanup, { once: true });
            labelFontReady().then(() => setTimeout(() => {
                if (seq !== printSeq) return;   // a newer print has the box; it opens its own dialog
                window.print(); setTimeout(cleanup, 800); }, 40), () => cleanup());
        }
        function openStockUsage() {
            const win = dialog({ title: 'Estimated stock usage' });
            const { overlay, modal, head, x, body } = win;
            const bar = el('div', 'lbl-toolbar');
            const dt = document.createElement('input');
            dt.type = 'date'; dt.className = 'lbl-size'; dt.setAttribute('aria-label', 'Date');
            dt.value = new Date().toLocaleDateString('en-CA');
            bar.append(el('span', 'cov-line', 'Everything marked made on'), dt);
            const pr = textButton(); pr.append(ico(I.printer), document.createTextNode('Print'));
            pr.disabled = true;
            bar.append(pr);
            body.append(bar);
            const out = el('div'); body.append(out);
            let current = null, usageReq = 0;
            async function load() {
                out.innerHTML = ''; pr.disabled = true; current = null;
                const t = el('div', 'thinking'); t.append(loader(), el('span', null, 'Adding up the day…')); out.append(t);
                const rq = ++usageReq;   // rapid date changes: only the latest may render
                try {
                    const d = await api('/api/stock-usage', { date: dt.value });
                    if (rq !== usageReq) return;
                    current = d;
                    out.innerHTML = '';
                    out.append(el('div', 'cov-line', d.orders + (d.orders === 1 ? ' order' : ' orders')
                        + ' marked made · ' + d.pieces + (d.pieces === 1 ? ' pc' : ' pcs')));
                    if (!d.rows.length && !d.unresolved.length && !(d.stock || []).length) {
                        out.append(el('div', 'empty', 'Nothing was marked made on this day.'));
                        return;
                    }
                    if (d.unresolved.length) {
                        const uq = d.unresolved.reduce((s, u) => s + u.qty, 0);
                        out.append(el('div', 'cov-note', uq + (uq === 1 ? ' pc' : ' pcs')
                            + ' had no resolved size (' + d.unresolved.map(u => u.name).join(', ')
                            + ') and are not counted below. Add a line by hand if they were made.'));
                    }
                    /* Stock gobos by name, not as "no resolved size". Whether one
                       used a blank is not something the order says, so the
                       prompt to add a line by hand stays; only the wording
                       stops calling a catalogue gobo a problem. */
                    if ((d.stock || []).length) {
                        const sq = d.stock.reduce((s, u) => s + u.qty, 0);
                        out.append(el('div', 'cov-note', sq + (sq === 1 ? ' stock gobo' : ' stock gobos')
                            + ' made (' + d.stock.map(u => u.qty + ' × ' + u.name).join(', ')
                            + '). They carry no size, so they are not in the sheet below; add a line by hand if one used a blank.'));
                    }
                    if (d.fetch_failed) {
                        out.append(el('div', 'cov-note', d.fetch_failed + ' made order(s) could not be loaded from Shopify (it may be busy) and are missing from this total. Try again shortly.'));
                    }
                    if ((d.gone_ids || []).length) {
                        const g = d.gone_ids.length;
                        out.append(el('div', 'cov-note', g + (g === 1 ? ' made order is' : ' made orders are')
                            + ' no longer in Shopify, so ' + (g === 1 ? 'it is' : 'they are')
                            + ' left out of this sheet and the glass booked for ' + (g === 1 ? 'it' : 'them') + ' stays booked.'));
                    }
                    /* The review sheet: the estimate stands on the left, the
                       FINAL figure being sent is the editable column. Lines
                       can be amended, removed, or added before sending. */
                    const sheet = d.rows.map(r => ({ family: r.glass, size: String(r.size),
                        estimated: r.qty, final: r.qty }));
                    let lastResult = null;
                    const sheetHost = el('div'); out.append(sheetHost);
                    function paintSheet() {
                        sheetHost.innerHTML = '';
                        if (d.sent) {
                            const nm = byName(d.sent.by);
                            const b = el('div', 'cov-note',
                                'Already sent to the stock sheet at ' + londonHM(d.sent.sent_at)
                                + (nm ? ' by ' + nm : '') + '. Sending again replaces that sheet.');
                            b.classList.add('tone-brand');
                            sheetHost.append(b);
                        }
                        const kt = dataTable(['Size', 'Glass', 'Unit', ['Estimated', 'num'], ['Final', 'num'], null]);
                        kt.wrap.classList.add('space-above-2-5');
                        sheet.forEach((r, i) => {
                            const tr = el('tr');
                            const inp = document.createElement('input');
                            inp.type = 'number'; inp.min = '0'; inp.max = '10000'; inp.value = r.final;
                            inp.className = 'tm-field pm-in pm-in-final';
                            inp.setAttribute('aria-label', 'Final quantity for ' + r.family + ' ' + r.size);
                            inp.oninput = () => { r.final = inp.value; };
                            const rm = iconButton(I.x, 'Remove this line (not actually used)');
                            rm.onclick = () => { sheet.splice(i, 1); paintSheet(); };
                            const est = el('td', 'num', String(r.estimated));
                            est.classList.add('tone-muted');
                            const tdF = el('td', 'num'); tdF.append(inp);
                            const tdR = el('td'); tdR.append(rm);
                            tr.append(el('td', 'kw', r.size + 'mm'), el('td', null, r.family),
                                el('td', null, r.family === 'Ring' ? 'rings' : 'blanks'), est, tdF, tdR);
                            kt.add(tr);
                        });
                        const addTr = el('tr');
                        const famSel = el('select', 'lbl-size'); famSel.setAttribute('aria-label', 'Glass family');
                        ['Mono', 'HM', 'Colour', 'Ring'].forEach(f => { const o = el('option', null, f); o.value = f; famSel.append(o); });
                        const szIn = document.createElement('input');
                        szIn.className = 'tm-field'; szIn.placeholder = 'Size mm'; szIn.setAttribute('aria-label', 'Size in millimetres');
                        szIn.classList.add('pm-in', 'pm-in-size');
                        const qIn = document.createElement('input');
                        qIn.type = 'number'; qIn.min = '1'; qIn.max = '10000'; qIn.placeholder = 'Qty'; qIn.setAttribute('aria-label', 'Quantity');
                        qIn.className = 'tm-field pm-in pm-in-qty';
                        const addB = textButton(); addB.append(ico(I.plus), document.createTextNode('Add'));
                        addB.title = 'Add something that was used but not in the estimate';
                        addB.onclick = () => {
                            const s = szIn.value.trim(); const q = parseInt(qIn.value, 10);
                            if (!s || !(q > 0)) { toastError('An added line needs a size and a quantity.'); return; }
                            sheet.push({ family: famSel.value, size: s, estimated: 0, final: q });
                            paintSheet();
                        };
                        const tds = [el('td'), el('td'), el('td', null, ''), el('td', 'num', '0'), el('td', 'num'), el('td')];
                        tds[0].append(szIn); tds[1].append(famSel); tds[3].classList.add('tone-muted');
                        tds[4].append(qIn); tds[5].append(addB);
                        tds.forEach(t2 => addTr.append(t2));
                        kt.add(addTr);
                        sheetHost.append(kt.wrap);
                        const send = textButton(null, { kind: 'primary' }); send.classList.add('space-above-2-5');
                        send.append(ico(I.send), document.createTextNode(
                            d.sent ? 'Send again (replaces the earlier sheet)' : 'Send to stock sheet'));
                        send.onclick = async () => {
                            const lines = sheet.map(r => ({ family: r.family, size: String(r.size),
                                estimated: r.estimated, final: parseInt(r.final, 10) }));
                            if (!lines.length) { toastError('The sheet has no lines left.'); return; }
                            if (lines.some(l => !(l.final >= 0))) { toastError('Every line needs a final quantity.'); return; }
                            if (!(await uiConfirm('Send ' + lines.length + ' line(s) for ' + d.date
                                + ' to the stock app? Stock adjusts to these final figures'
                                + (d.sent ? ', replacing the sheet sent earlier' : '') + '.',
                                { title: 'Send the stock sheet', okText: 'Send' }))) return;
                            send.disabled = true;
                            try {
                                const r = await api('/api/stock-usage/send', { date: d.date, lines: lines });
                                d.sent = r.sent;
                                lastResult = r.result;
                                paintSheet();
                                addToast('Stock sheet sent: ' + (r.result.adjustments || 0) + ' adjustment(s) made.', 'good');
                                if (r.note) addToast(r.note);
                            } catch (e) { toastError(e.message || 'The send failed. Nothing was recorded.'); }
                            send.disabled = false;
                        };
                        sheetHost.append(send);
                        if (lastResult && lastResult.results) {
                            const box = el('div'); box.classList.add('space-above-2-5');
                            lastResult.results.forEach(rr => {
                                let txt = rr.family + ' ' + rr.size + 'mm: ';
                                if (rr.status === 'adjusted') {
                                    txt += 'adjusted ' + (rr.delta > 0 ? '+' : '') + rr.delta
                                        + ' (auto-booked ' + rr.already_booked + ', final ' + rr.final + ')'
                                        + (rr.short ? ' · the shelf was ' + rr.short + ' short' : '');
                                } else if (rr.status === 'matched') {
                                    txt += 'already right (auto-booked ' + rr.already_booked + ')';
                                } else if (rr.status === 'no_item') {
                                    txt += 'No stock item: map this line in the stock app, then send again';
                                } else {
                                    txt += 'the quantity was not readable';
                                }
                                const line = el('div', 'cov-note', txt);
                                if (rr.status === 'no_item') line.classList.add('tone-error');
                                box.append(line);
                            });
                            sheetHost.append(box);
                        }
                    }
                    paintSheet();
                    pr.disabled = !d.rows.length;
                } catch (e) {
                    if (rq !== usageReq) return;
                    out.innerHTML = '';
                    out.append(el('div', 'cov-line', e.message || 'Could not load.'));
                }
            }
            pr.onclick = () => { if (current) printStockUsage(current); };
            dt.onchange = load;
            load();
        }
        function printStockUsage(d) {
            const box = $('label-print'); box.innerHTML = '';
            const ds = el('div', 'day-sheet');
            ds.append(el('h1', null, 'Estimated stock usage'));
            const nice = new Date(d.date + 'T12:00:00').toLocaleDateString('en-GB',
                { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
            ds.append(el('div', 'ds-meta', nice + ' · ' + d.orders + (d.orders === 1 ? ' order' : ' orders')
                + ' · ' + d.pieces + (d.pieces === 1 ? ' pc' : ' pcs')));
            const tb = el('table', 'ds-table');
            tb.innerHTML = '<thead><tr><th>Size</th><th>Glass</th><th>Pieces</th></tr></thead>';
            const tbody = el('tbody');
            d.rows.forEach(r => {
                const tr = el('tr');
                tr.append(el('td', 'ds-size', r.size + 'mm'), el('td', null, r.glass), el('td', 'ds-qty', String(r.qty)));
                tbody.append(tr);
            });
            tb.append(tbody); ds.append(tb);
            if (d.unresolved.length) {
                const uq2 = d.unresolved.reduce((s, u) => s + u.qty, 0);
                ds.append(el('div', 'ds-flag', uq2 + (uq2 === 1 ? ' pc' : ' pcs')
                    + ' unresolved: ' + d.unresolved.map(u => u.name + ' (' + u.qty + ')').join(', ')));
            }
            if ((d.stock || []).length) {
                ds.append(el('div', 'ds-orders', 'Stock gobos: '
                    + d.stock.map(u => u.qty + ' × ' + u.name).join(', ')));
            }
            ds.append(el('div', 'ds-orders', 'Orders: ' + (d.order_names || []).join('   ')));
            box.append(ds);
            let rule = $('label-page-rule');
            if (!rule) { rule = document.createElement('style'); rule.id = 'label-page-rule'; document.head.append(rule); }
            rule.textContent = '@page { size: A4; margin: 12mm; }';
            const seq = ++printSeq;
            document.body.classList.add('printing-label');
            const cleanup = () => {
                if (seq !== printSeq) return;
                document.body.classList.remove('printing-label');
                box.innerHTML = '';
                const r = $('label-page-rule');
                if (r && r.parentNode) r.parentNode.removeChild(r);
            };
            if (window.onafterprint !== undefined) window.addEventListener('afterprint', cleanup, { once: true });
            labelFontReady().then(() => setTimeout(() => {
                if (seq !== printSeq) return;   // a newer print has the box; it opens its own dialog
                window.print(); setTimeout(cleanup, 800); }, 40), () => cleanup());
        }
        /* One A4 cut list of everything live and not yet made: sizes and glass
           types summed across the queue, with tick boxes for the bench. */
        function printDaySheet() {
            const orders = labelOrders().filter(o => !o.status && !prodStateOf(o).made_at);
            if (!orders.length) { addToast('Nothing to make: every live order is marked made.'); return; }
            const agg = {};
            const stock = {};
            let flagged = 0, notGobo = 0, projectors = 0;
            orders.forEach(o => (o.items || []).forEach(it => {
                // A projector or accessory goes in the box but is not cut.
                if (it.projector) { projectors += it.quantity || 1; return; }
                // Ruled not a gobo: nothing to cut, and nothing to put right.
                if (it.not_gobo) { notGobo += it.quantity || 1; return; }
                /* A stock gobo is named, not sized: it is not summed by size
                   and it is not a problem, so it is not counted as
                   CHECK-flagged either. It joins the same tick list, by name. */
                if (it.stock && !it.production_size && !it.review_reason) {
                    const n = it.title || 'Stock gobo';
                    stock[n] = (stock[n] || 0) + (it.quantity || 1);
                    return;
                }
                if (it.review_reason || !it.production_size) { flagged += it.quantity || 1; return; }
                const key = it.production_size + '|' + (it.glass_type || '');
                const a = agg[key] = agg[key] || { size: it.production_size, glass: it.glass_type || '', qty: 0 };
                a.qty += it.quantity || 1;
            }));
            const rows = Object.values(agg).sort((a, b) => parseFloat(b.size) - parseFloat(a.size));
            const box = $('label-print'); box.innerHTML = '';
            const ds = el('div', 'day-sheet');
            ds.append(el('h1', null, 'Production day sheet'));
            ds.append(el('div', 'ds-meta', new Date().toLocaleDateString('en-GB',
                { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
                + ' · ' + orders.length + (orders.length === 1 ? ' order' : ' orders') + ' in the queue'));
            const tb = el('table', 'ds-table');
            tb.innerHTML = '<thead><tr><th>Size</th><th>Glass</th><th>Qty</th><th>Done</th></tr></thead>';
            const tbody = el('tbody');
            rows.forEach(r => {
                const tr = el('tr');
                tr.append(el('td', 'ds-size', r.size + 'mm'), el('td', null, r.glass),
                          el('td', 'ds-qty', String(r.qty)), el('td', 'ds-tick', ''));
                tbody.append(tr);
            });
            Object.keys(stock).sort().forEach(n => {
                const tr = el('tr');
                tr.append(el('td', 'ds-size', 'Stock'), el('td', null, n),
                          el('td', 'ds-qty', String(stock[n])), el('td', 'ds-tick', ''));
                tbody.append(tr);
            });
            tb.append(tbody); ds.append(tb);
            if (flagged) ds.append(el('div', 'ds-flag', flagged + (flagged === 1 ? ' item is' : ' items are')
                + ' CHECK-flagged and not in this list. Resolve them on the Labels tab first.'));
            if (notGobo) ds.append(el('div', 'ds-orders', notGobo + (notGobo === 1 ? ' item is' : ' items are')
                + ' ruled not a gobo, so not in this list.'));
            if (projectors) ds.append(el('div', 'ds-orders', projectors + (projectors === 1
                ? ' item is a projector or accessory' : ' items are projectors or accessories')
                + ', so not in this list.'));
            ds.append(el('div', 'ds-orders', 'Orders: ' + orders.map(o => orderNo(o)).join('   ')));
            box.append(ds);
            let rule = $('label-page-rule');
            if (!rule) { rule = document.createElement('style'); rule.id = 'label-page-rule'; document.head.append(rule); }
            rule.textContent = '@page { size: A4; margin: 12mm; }';
            const seq = ++printSeq;
            document.body.classList.add('printing-label');
            const cleanup = () => {
                if (seq !== printSeq) return;
                document.body.classList.remove('printing-label');
                box.innerHTML = '';
                const r = $('label-page-rule');
                if (r && r.parentNode) r.parentNode.removeChild(r);
            };
            if (window.onafterprint !== undefined) window.addEventListener('afterprint', cleanup, { once: true });
            labelFontReady().then(() => setTimeout(() => {
                if (seq !== printSeq) return;   // a newer print has the box; it opens its own dialog
                window.print(); setTimeout(cleanup, 800); }, 40), () => cleanup());
        }

