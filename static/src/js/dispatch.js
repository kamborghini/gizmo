        /* ---------- dispatch (World Options) ---------- */
        function errBubble(msg) { const w = el('div', 'msg error'); w.append(el('div', 'bubble', msg)); return w; }
        // WO's carrier enum codes -> names a human reads (EVRISEND, ROYALMAIL...).
        const CARRIER_LABELS = { ROYALMAIL: 'Royal Mail', DPD: 'DPD', EVRISEND: 'Evri', EVRICORPORATE: 'Evri',
            EVRI: 'Evri', HERMES: 'Evri', UPS: 'UPS', FEDEX: 'FedEx', TNT: 'TNT', DHL: 'DHL', DHLPARCEL: 'DHL Parcel',
            YODEL: 'Yodel', CITYSPRINT: 'CitySprint', DXEXPRESS: 'DX', TUFFNELLS: 'Tuffnells', PALLETWAYS: 'Palletways', DSV: 'DSV',
            EXFREIGHT: 'EXFreight', GLOBALTRANZ: 'GlobalTranz', UKMAIL: 'UKMail' };
        /* Sentence case, because nothing in this design shouts. The strings
           themselves were capitals, so removing text-transform from the CSS
           was only half the job. */
        const cap = s => { s = String(s || ''); return s.charAt(0).toUpperCase() + s.slice(1); };
        function carrierLabel(code) { return CARRIER_LABELS[String(code || '').toUpperCase()] || code || ''; }
        // "UPS" + "UPS Express" -> "UPS Express" (no stutter). An unknown carrier
        // yields the service alone rather than inventing one.
        function carrierService(code, service) {
            const c = carrierLabel(code), s = String(service || '').trim();
            if (!s) return c || 'Courier';
            if (!c) return s;
            const low = s.toLowerCase();
            if (low.startsWith(c.toLowerCase())) return s;
            const raw = String(code || '').trim().toLowerCase();
            if (raw && low.startsWith(raw)) return s;
            return c + ' ' + s;
        }
        // Naming a shipment is a money decision (the merchant confirms a charge from
        // it) and a receipt, so it never resolves to nothing: with no carrier it says
        // so and falls back to World Options' own code, which they can look up.
        function optionName(op) {
            if (!op) return 'this courier';
            const named = carrierService(op.carrier_name, op.service_name);
            if (op.carrier_name) return named;
            const code = op.product_code || op.service_type_code || '';
            return (op.service_name || 'Courier service')
                + (code ? ' (carrier not named, World Options service ' + code + ')' : ' (carrier not named)');
        }
        // The same, for a booked shipment: it carries a stored label and its own codes.
        function shipmentName(s) {
            if (!s) return 'a courier';
            const who = s.carrier_label || carrierLabel(s.carrier_name || '');
            const svc = String(s.service_name || '').trim();
            if (who) return carrierService(s.carrier_name, svc) === svc && !svc.toLowerCase().startsWith(who.toLowerCase())
                ? (who + (svc ? ' ' + svc : '')) : (carrierService(s.carrier_name, svc) || who);
            const code = s.product_code || s.service_code || '';
            return (svc || 'a courier') + (code ? ' (carrier not named, World Options service ' + code + ')' : '');
        }
        // What we sent and what came back, copyable in one click. World Options'
        // errors name a .NET parameter rather than a field, so the request itself is
        // the only way to work out which field they meant.
        function techPanel(tech) {
            if (!tech) return null;
            const det = document.createElement('details');
            det.className = 'disp-tech';
            const sum = document.createElement('summary');
            sum.textContent = 'Technical details (send these to your developer)';
            det.append(sum);
            const bar = el('div', 'disp-tech-bar');
            const copy = el('button', 'btn', 'Copy');
            const text = () => [
                'Order: ' + (tech.order || ''),
                'When: ' + (tech.when || ''),
                '',
                'World Options replied:',
                tech.reply || '(nothing)',
                '',
                'We sent:',
                tech.request || (tech.sent ? '(sent, but not captured)' : '(the request was never sent)'),
            ].join('\n');
            copy.onclick = async (ev) => {
                ev.preventDefault();
                try {
                    await navigator.clipboard.writeText(text());
                    copy.textContent = 'Copied';
                    setTimeout(() => { copy.textContent = 'Copy'; }, 2000);
                } catch (e) {
                    // Clipboard is blocked in some embedded frames: select it instead
                    // so the operator can copy by hand rather than be stuck.
                    const pre = det.querySelector('pre');
                    if (pre) {
                        const r = document.createRange(); r.selectNodeContents(pre);
                        const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
                    }
                    copy.textContent = 'Press Cmd+C';
                }
            };
            bar.append(copy);
            det.append(bar);
            if (tech.reply) {
                det.append(el('div', 'disp-tech-h', 'World Options replied'));
                det.append(el('pre', 'disp-tech-pre', tech.reply));
            }
            if (tech.request) {
                det.append(el('div', 'disp-tech-h', 'We sent (your details and password removed)'));
                det.append(el('pre', 'disp-tech-pre', tech.request));
            }
            return det;
        }
        function setDispatchState(id, entry) {
            if (!labelsCache || !labelsCache.data) return;
            const d = labelsCache.data.dispatch = labelsCache.data.dispatch || {};
            d[String(id)] = Object.assign({}, d[String(id)] || {}, entry);
        }
        // A labelled numeric field for the box editor.
        function numField(lab, val) {
            const wrap = el('label', 'disp-fld');
            wrap.append(el('span', 'disp-fld-lab', lab));
            const inp = document.createElement('input');
            inp.type = 'number'; inp.min = '0'; inp.step = '0.1'; inp.className = 'disp-num';
            if (val != null) inp.value = val;
            wrap.append(inp);
            wrap.input = inp;
            return wrap;
        }
        // Open each courier label: a URL in a new tab, a base64/dataurl PDF as a blob.
        // Turn a label into a blob URL once, so print and download share it.
        function labelBlobUrl(l) {
            const MIME = { base64pdf: 'application/pdf', base64png: 'image/png', base64bin: 'application/octet-stream' };
            const mime = MIME[l.type];
            if (!mime) return null;
            const bin = atob(String(l.value || '').replace(/\s+/g, ''));
            const buf = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
            return URL.createObjectURL(new Blob([buf], { type: mime }));
        }
        function labelExt(l) {
            if (l.type === 'base64png') return 'png';
            if (l.type === 'base64pdf') return 'pdf';
            return (l.label_type || 'zpl').toLowerCase().replace(/[^a-z0-9]/g, '') || 'bin';
        }
        // Always available: puts the file on disk. App Bridge does not intercept
        // a download click, so this works even when opening a tab does not.
        function downloadLabel(l, i) {
            try {
                if (l.type === 'url') {
                    // A WO link cannot be opened from inside the admin (a relative one
                    // 404s against this app); the portal is the only place it works.
                    toastError('This label only exists as a link at World Options; print it from your portal.');
                    return;
                }
                const url = labelBlobUrl(l);
                if (!url) { toastError('This label format cannot be saved; get it from your World Options portal.'); return; }
                const a = document.createElement('a'); a.href = url;
                a.download = 'shipping-label' + (i ? '-' + (i + 1) : '') + '.' + labelExt(l);
                document.body.append(a); a.click(); a.remove();
                setTimeout(() => URL.revokeObjectURL(url), 60000);
            } catch (e) { toastError('Could not save the label. Use Download, or your World Options portal.'); }
        }
        /* ==================================================================
           Bulk courier-label reprint, split BY COURIER.
           Couriers do not share a sheet: three DHL and eight UPS is two runs
           at two different printers, so the choice is made before anything
           prints rather than discovered halfway through a stack.
           ================================================================== */
        function courierOf(o) {
            const d = dispatchStateOf(o) || {};
            return String(d.carrier_label || d.carrier_known || d.carrier_name || '').trim()
                || 'Courier not named';
        }
        /* One printer run. Past this the fan-out trips the app's own rate
           limit and returns a stack that is mostly missing, which is worse
           than being told to narrow the list. */
        const SHIP_RUN_MAX = 60;
        /* A booking whose outcome is unknown: the server's wording when a
           request reached World Options and no clear answer came back. Both
           booking panels hold Book on it. */
        const BOOKING_UNKNOWN = /MAY still|check this order|did not get a reply/i;
        function shipLabelEligible(o) {
            /* o.status is cancelled / refunded / already-fulfilled - the same
               rule the gobo bulk print uses two buttons along. d.canceled is a
               different thing: the COURIER shipment was voided. A cancelled
               order that still has a live courier booking must not walk into
               a bulk run and get a label printed for a parcel nobody is
               sending. */
            if (o.status) return false;
            const d = dispatchStateOf(o) || {};
            return !!d.tracking_number && !d.canceled && d.has_label !== false;
        }
        async function fetchLabelsFor(orders, onProgress, run) {
            /* Bounded fan-out over the EXISTING single-label route: labels are
               about a megabyte each, and one bulk response carrying eleven of
               them is a request that times out on a bad morning.

               Results land in INDEXED slots, not by whoever answers first: the
               stack has to come out in the order the picker listed, or the
               operator matches eleven labels to eleven parcels by reading
               every address. Every shortfall is named - including a
               multi-parcel order where only some parcels could print, which is
               precisely how box 2 of 2 goes out bare. */
            const slots = new Array(orders.length);
            const failed = [];
            let i = 0, done = 0;
            async function worker() {
                while (i < orders.length) {
                    const idx = i++;
                    if (run && run.cancelled) return;
                    const o = orders[idx];
                    try {
                        const r = await api('/api/dispatch/label',
                            o.__custom ? { id: o.id } : { order_id: o.id });
                        const all = (r.labels || []).filter(Boolean);
                        const got = all.filter(l => l.print_images && l.print_images.length);
                        slots[idx] = got;
                        if (!all.length) failed.push(orderNo(o) + ': no label stored');
                        else if (!got.length) failed.push(orderNo(o)
                            + ': the label cannot print in place - open the order and download it');
                        else if (got.length < all.length) failed.push(orderNo(o)
                            + ': only ' + got.length + ' of ' + all.length
                            + ' parcels could print - the rest need downloading from the order');
                    } catch (e) {
                        failed.push(orderNo(o) + ': ' + (e.message || 'could not be read'));
                    }
                    if (onProgress) onProgress(++done, orders.length);
                }
            }
            await Promise.all([0, 1, 2, 3].map(worker));
            return { labels: slots.filter(Boolean).flat(), failed,
                     cancelled: !!(run && run.cancelled) };
        }
        function printShippingLabelsFor(orders) {
            const byCourier = new Map();
            orders.forEach(o => {
                const c = courierOf(o);
                if (!byCourier.has(c)) byCourier.set(c, []);
                byCourier.get(c).push(o);
            });
            const groups = [...byCourier.entries()].sort((a, b) => b[1].length - a[1].length);
            const m = crmModal('Print shipping labels');
            const run = { cancelled: false, busy: false };
            const closeBtn = m.head.querySelector('.icon-btn');
            if (closeBtn) closeBtn.addEventListener('click', () => { run.cancelled = true; });
            m.body.append(el('p', 'field-help', 'These are the courier labels for orders already '
                + 'dispatched in this list. Each courier prints on its own stock, so pick one run '
                + 'at a time.'));
            const status = el('div', 'sub'); status.style.marginTop = 'var(--sp-2)';
            const problems = el('div'); problems.style.marginTop = 'var(--sp-2)';
            async function go(list, what) {
                if (run.busy) return;             /* one run at a time, per picker */
                if (list.length > SHIP_RUN_MAX) {
                    problems.innerHTML = '';
                    problems.append(el('div', 'msg error', list.length + ' labels is more than one '
                        + 'printer run. Narrow the list first - search, or switch queue - then '
                        + 'print up to ' + SHIP_RUN_MAX + ' at a time.'));
                    return;
                }
                run.busy = true;
                problems.innerHTML = '';
                const btns = [...m.body.querySelectorAll('button')];
                btns.forEach(b => b.disabled = true);
                status.textContent = 'Fetching ' + list.length + ' label'
                    + (list.length === 1 ? '' : 's') + '\u2026';
                const { labels, failed, cancelled } = await fetchLabelsFor(list,
                    (n, total) => { status.textContent = 'Fetching label ' + n + ' of ' + total + '\u2026'; },
                    run);
                run.busy = false;
                status.textContent = '';
                if (cancelled) return;            /* the window was closed: print nothing */
                btns.forEach(b => b.disabled = false);
                if (!labels.length) {
                    problems.append(el('div', 'msg error', 'Nothing printable for ' + what + '.'));
                    failed.forEach(f => problems.append(el('div', 'sub', f)));
                    return;
                }
                printLabelImages(labels);
                if (!failed.length) {
                    m.close();
                    addToast('Printing ' + labels.length + ' label'
                        + (labels.length === 1 ? '' : 's') + ' for ' + what + '.', 'good');
                    return;
                }
                /* A short stack is how a parcel goes out with no label on it,
                   so the window STAYS OPEN listing every order that fell out -
                   all of them, not the first few, and not in a toast that
                   vanishes while the print dialog is still up. */
                problems.append(el('div', 'msg error', 'Printing ' + labels.length + ' label'
                    + (labels.length === 1 ? '' : 's') + ', but ' + failed.length
                    + ' did not make the stack. Deal with these before the parcels go out:'));
                failed.forEach(f => problems.append(el('div', 'sub', f)));
            }
            const list = el('div');
            groups.forEach(([courier, os]) => {
                const row = el('div', 'lbl-row');
                row.append(el('div', 'lia-name', courier));
                const mid = el('div', 'lbl-who');
                mid.append(el('span', 'sub', os.length + (os.length === 1 ? ' order' : ' orders')
                    + ' \u00b7 ' + os.slice(0, 3).map(orderNo).join(', ')
                    + (os.length > 3 ? ' and ' + (os.length - 3) + ' more' : '')));
                row.append(mid);
                const b = el('button', 'btn btn-primary', 'Print ' + os.length);
                b.onclick = () => go(os, courier);
                row.append(b);
                list.append(row);
            });
            m.body.append(list);
            if (groups.length > 1) {
                const bar2 = el('div', 'disp-actions');
                const every = el('button', 'btn', 'Print all ' + orders.length
                    + ' (every courier, one run)');
                every.title = 'Only sensible if the same printer takes every courier\u2019s stock';
                every.onclick = () => go(orders, 'every courier');
                bar2.append(every); m.body.append(bar2);
            }
            m.body.append(status, problems);
        }

        function printLabelImages(labels) {
            const pages = [];
            const B64 = /^[A-Za-z0-9+/=\s]+$/;   // no quote or angle can reach the attribute
            (labels || []).forEach(l => (l && l.print_images || []).forEach(p => {
                if (typeof p === 'string' && B64.test(p)) pages.push(p.replace(/\s+/g, ''));
            }));
            if (!pages.length) return false;
            const fr = document.createElement('iframe');
            fr.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;opacity:0';
            const dims = carrierDims();
            fr.srcdoc = '<!doctype html><html><head><style>'
                + '@page{size:' + dims.w + 'mm ' + dims.h + 'mm;margin:0}'
                + 'html,body{margin:0;padding:0}'
                + 'img{display:block;width:' + dims.w + 'mm;height:' + dims.h + 'mm;'
                + 'object-fit:contain;object-position:top left;page-break-after:always}'
                + 'img:last-child{page-break-after:auto}'
                + '</style></head><body>'
                + pages.map(p => '<img src="data:image/png;base64,' + p + '">').join('')
                + '</body></html>';
            fr.onload = () => {
                const started = Date.now();
                const wait = () => {
                    const d = fr.contentDocument;
                    // Bounded: after 8s, print whatever loaded rather than never
                    // printing and never saying why.
                    if (Date.now() - started < 8000 && [...d.images].some(im => !im.complete)) {
                        setTimeout(wait, 120); return;
                    }
                    try { fr.contentWindow.focus(); fr.contentWindow.print(); }
                    catch (e) { toastError('Could not open the print dialog.'); }
                    setTimeout(() => fr.remove(), 60000);
                };
                wait();
            };
            document.body.append(fr);
            return true;
        }
        function labelButtons(host, labels, verb) {
            labels = labels || [];
            if (!labels.length) { host.append(el('div', 'sub', 'No label was returned; check your World Options portal.')); return; }
            const row = el('div', 'disp-actions');
            const printable = labels.filter(l => l && l.print_images && l.print_images.length);
            if (printable.length) {
                const b = el('button', 'btn btn-primary');
                b.append(ico(I.printer), document.createTextNode(
                    (verb || 'Print label') + (printable.length > 1 ? 's' : '')));
                b.onclick = () => printLabelImages(printable);
                row.append(b);
            }
            // Download appears ONLY for a label the print path cannot handle
            // (a ZPL file, or a PDF the server could not render), so a paid-for
            // label is never stranded while the normal row stays one button.
            labels.forEach((l, i) => {
                if (l && l.print_images && l.print_images.length) return;
                const d = el('button', 'btn');
                d.append(ico(I.download), document.createTextNode(
                    labels.length > 1 ? ('Download label ' + (i + 1)) : 'Download label'));
                d.title = 'This label cannot be printed in place; save the file and print it';
                d.onclick = () => downloadLabel(l, labels.length > 1 ? i : 0);
                row.append(d);
            });
            host.append(row);
        }

        /* Only an admin may rewrite where a paid order ships. The server is the
           real gate; this just stops offering a button that would be refused. */
        function canEditOrders() {
            return !teamMe || ({ master: 3, admin: 2 }[teamMe.role] || 0) >= 2;
        }

        /* The fields Shopify still lets you change on a placed order, in the
           app's own address shape. There is no "name": Shopify builds an
           address's name from first + last, so offering one would report a save
           and change nothing. */
        const ORDER_EDIT_FIELDS = [
            ['firstname', 'First name'], ['lastname', 'Last name'],
            ['company', 'Company'], ['phone', 'Phone for the courier'],
            ['street', 'Address line 1'], ['street2', 'Address line 2'],
            ['city', 'Town or city'], ['state', 'County or state'],
            ['postcode', 'Postcode'], ['country', 'Country (2-letter, e.g. GB)'],
        ];
        const COURIER_LINE_CHARS = 35;

        async function openOrderEdit(o) {
            const overlay = el('div', 'modal-overlay show');
            const modal = el('div', 'modal disp-modal');
            const head = el('div', 'modal-head');
            const h = el('h3', null, 'Edit ');
            h.append(orderA(orderNo(o), o.admin_url, 'modal-order-link'));
            const x = el('button', 'icon-btn'); x.innerHTML = I.x; x.title = 'Close';
            head.append(h, x);
            const body = el('div', 'modal-body');
            modal.append(head, body); overlay.append(modal); document.body.append(overlay);
            const prev = document.activeElement;
            let saving = false;
            const close = () => {
                if (saving) { addToast('The change is still saving. Please wait.'); return; }
                overlay.remove(); if (prev && prev.focus) prev.focus();
            };
            x.onclick = close;   // the X is the only way out: a misclick must not wipe a filled form
            x.focus();

            const load = el('div', 'thinking');
            load.append(loader(), el('span', null, 'Reading this order from Shopify…'));
            body.append(load);

            let live;
            try {
                live = await api('/api/order/edit', { order_id: o.id, op: 'read' });
            } catch (e) {
                body.innerHTML = '';
                body.append(el('div', 'msg error', e.message || 'Could not read that order.'));
                return;
            }
            body.innerHTML = '';

            /* Read live, not from the queue: the queue's copy can be a sweep old,
               and the person is about to retype an address from it. */
            if (live.status) {
                body.append(el('div', 'disp-warn', 'Shopify shows this order as ' + live.status
                    + '. Changing it here does not undo that.'));
            }
            if (live.booked) {
                const w = el('div', 'msg error');
                w.append(el('div', null, 'A courier label is already booked for this order ('
                    + [live.booked.carrier, live.booked.service, live.booked.tracking]
                        .filter(Boolean).join(' ')
                    + '). The label is printed and the parcel travels to the address it was '
                    + 'cut from. Changing the address here changes Shopify only: it does not '
                    + 'change the label or the courier booking.'));
                body.append(w);
            }

            body.append(el('div', 'section-title', 'Delivery address'));
            const cur = live.ship_to || {};
            const f = {};
            const grid = el('div', 'disp-origin');
            ORDER_EDIT_FIELDS.forEach(([k, lab]) => {
                const w = el('label', 'disp-fld');
                w.append(el('span', 'disp-fld-lab', lab));
                const inp = document.createElement('input');
                inp.type = 'text'; inp.className = 'disp-num'; inp.value = cur[k] || '';
                w.append(inp); f[k] = inp; grid.append(w);
            });
            body.append(grid);
            const lineNote = el('div', 'cov-note');
            const checkLines = () => {
                const over = ['street', 'street2'].filter(k => (f[k].value || '').length > COURIER_LINE_CHARS);
                lineNote.textContent = over.length
                    ? 'A courier label prints about ' + COURIER_LINE_CHARS + ' characters per address line. '
                      + (over.length === 1 ? 'One line is' : 'Both lines are') + ' longer than that.'
                    : '';
            };
            ['street', 'street2'].forEach(k => f[k].addEventListener('input', checkLines));
            checkLines();
            body.append(lineNote);

            /* One phone only. Shopify keeps a phone on the address AND one on the
               order, and _ship_to falls back from one to the other - so showing
               both put the same number on screen twice with no way to tell which
               one a courier would ring. The address phone is the one that gets
               printed on the label. */
            body.append(el('div', 'section-title', 'Contact'));
            const cgrid = el('div', 'disp-origin');
            const ew = el('label', 'disp-fld');
            ew.append(el('span', 'disp-fld-lab', 'Email'));
            const einp = document.createElement('input');
            einp.type = 'email'; einp.className = 'disp-num'; einp.value = cur.email || '';
            ew.append(einp); f.email = einp; cgrid.append(ew);
            body.append(cgrid);
            const onT = el('div', 'section-title', 'Order note');
            body.append(onT);
            const note = document.createElement('textarea');
            note.className = 'disp-paste'; note.rows = 4;
            /* Prefilled from the LIVE note, not the queue's copy: that one has the
               proposal link stripped out and is cut to 500 characters, so saving
               it back would delete the proof link. Left untouched, this
               round-trips byte for byte. */
            note.value = live.note || '';
            body.append(note);
            onT.append(infoButton('About the order note', { title: 'Order note', body: 'This is the order note exactly as Shopify holds it, '
                + 'including the proposal link if there is one. The order tags are not editable '
                + 'here: the production queues and the chase list are both driven by them, so they '
                + 'are changed by the queue buttons instead.' }));

            const err = el('div'); body.append(err);
            const foot = el('div', 'modal-foot');
            const cancel = el('button', 'btn', 'Cancel'); cancel.onclick = close;
            const save = el('button', 'btn btn-primary', 'Save changes');
            foot.append(cancel, save); modal.append(foot);

            save.onclick = async () => {
                if (saving) return;
                const ship = {};
                ORDER_EDIT_FIELDS.forEach(([k]) => { ship[k] = f[k].value.trim(); });
                const payload = {
                    order_id: o.id, ship_to: ship, email: f.email.value.trim(),
                    note: note.value,
                };
                const addrMoved = ORDER_EDIT_FIELDS.some(([k]) => ship[k] !== (cur[k] || ''));
                if (live.booked && addrMoved) {
                    if (!await uiConfirm('The parcel for this order is already booked with '
                        + (live.booked.carrier || 'a courier') + ' on tracking '
                        + (live.booked.tracking || '') + ', and the printed label carries the old '
                        + 'address. Saving changes Shopify only. Cancel the shipment and book '
                        + 'again if the parcel has not gone yet.',
                        { title: 'The label is already printed', okText: 'Change it anyway',
                          cancelText: 'Leave it', danger: true })) return;
                    payload.confirm_booked = true;
                }
                saving = true; save.disabled = true; cancel.disabled = true;
                save.textContent = 'Saving…'; err.innerHTML = '';
                try {
                    const r = await api('/api/order/edit', payload);
                    (r.warnings || []).forEach(w => addToast(w));
                    if (!(r.changed || []).length) addToast('Nothing had changed.');
                    else {
                        addToast(orderNo(o) + ' updated in Shopify.', 'good');
                        // The cached quote was priced for the old destination, and
                        // the queue's copy of this order still holds the old address.
                        quoteCache.delete(String(o.id));
                        loadLabels(true);
                    }
                    saving = false;
                    overlay.remove(); if (prev && prev.focus) prev.focus();
                } catch (e) {
                    saving = false; save.disabled = false; cancel.disabled = false;
                    save.textContent = 'Save changes';
                    err.innerHTML = '';
                    err.append(el('div', 'msg error', e.message || 'The order could not be changed.'));
                }
            };
        }

        async function openDispatch(o) {
            const overlay = el('div', 'modal-overlay show');
            const modal = el('div', 'modal disp-modal');
            const head = el('div', 'modal-head');
            const dh = el('h3', null, 'Dispatch · ');
            dh.append(orderA(orderNo(o), o.admin_url, 'modal-order-link'));
            head.append(dh);
            const x = el('button', 'icon-btn'); x.innerHTML = I.x; x.title = 'Close'; head.append(x);
            const body = el('div', 'modal-body');
            modal.append(head, body); overlay.append(modal); document.body.append(overlay);
            const prev = document.activeElement;
            let booking = false;    // set while money is being spent
            /* What THIS booking asked the courier to do about collection. It
               lives out here because renderResult reads it and is a sibling of
               the handler that sets it, not a child - declaring it inside the
               click was a scope error that only showed up AFTER a booking had
               charged, which is the worst possible moment for one. */
            let askedCollection = '';
            const close = () => {
                if (booking) { addToast('The courier booking is still going through. Please wait.'); return; }
                overlay.remove(); document.removeEventListener('keydown', esc);
                if (prev && prev.focus) prev.focus();
            };
            function esc(e) { /* Escape deliberately does not close either: X only. */ }
            x.onclick = close;
            // Backdrop clicks never close: a misclick must not wipe a filled form.
            // The X is the only way out (user rule).
            document.addEventListener('keydown', esc);
            x.focus();

            const existing = dispatchStateOf(o);
            if (existing.tracking_number && !existing.canceled) { renderShipmentSummary(existing); return; }

            const load = el('div', 'thinking'); load.append(loader(), el('span', null, 'Loading shipping settings…')); body.append(load);
            let cfg;
            try { cfg = await ensureShippingCfg(); }
            catch (e) { body.innerHTML = ''; body.append(errBubble(e.message || 'Could not load settings')); return; }
            body.innerHTML = '';
            if (!cfg.available) { body.append(el('div', 'empty', 'Shipping is not available on this server.')); return; }
            if (!cfg.connected) {
                const m = el('div', 'disp-notice');
                m.append(el('p', null, 'World Options is not connected yet.'));
                const b = el('button', 'btn btn-primary'); b.append(ico(I.truck), document.createTextNode('Open shipping settings'));
                b.onclick = () => { close(); openShippingSettings(); };
                m.append(b); body.append(m); return;
            }

            const dest = o.ship_to || {};
            const destName = dest.company || [dest.firstname, dest.lastname].filter(Boolean).join(' ') || dest.name || o.display_name;
            const dsum = el('div', 'disp-dest');
            dsum.append(el('div', 'disp-dest-name', destName));
            dsum.append(el('div', 'sub', [dest.street, dest.street2, dest.city, dest.postcode, dest.country].filter(Boolean).join(', ') || 'No address on file'));
            if (o.shipping_paid && (o.shipping_paid.title || o.shipping_paid.price)) {
                dsum.append(el('div', 'sub', 'Customer paid for delivery: ' + (o.shipping_paid.title || 'shipping')
                    + (o.shipping_paid.price ? ', ' + fmtPrice(parseFloat(o.shipping_paid.price), o.currency || '') : '')));
            }
            body.append(dsum);
            if (!dest.street || !dest.postcode || !dest.country) {
                body.append(el('div', 'disp-warn', 'This order is missing part of its shipping address. Fix it in Shopify, then reopen.'));
            }

            const presets = cfg.boxes || [];
            const defaultPreset = (cfg.default_box_id && presets.find(b => b.id === cfg.default_box_id)) || presets[0] || null;

            // A quote is only valid for the parcels + insurance it was priced with.
            // Any change to those clears the rendered options so a re-quote is forced,
            // and freezes what actually gets booked (lastBoxes / lastInsurance).
            let quote = null, chosen = null, lastBoxes = null, lastInsurance = 0, quoteWrap = null;
            function staleQuote() {
                if (!quote && !chosen) return;
                stashCustoms();          // keep typed goods lines across the re-quote
                quote = null; chosen = null;
                if (quoteWrap) {
                    quoteWrap.innerHTML = '';
                    quoteWrap.append(el('div', 'disp-warn', 'Parcels or insurance changed since the last quote. Press "Get courier quotes" again to reprice before booking.'));
                }
            }

            // ---- parcels: one row each, add/remove ----
            const boxHostD = el('div');
            body.append(el('div', 'disp-subhead', 'Parcels'), boxHostD);
            const boxRows = [];
            function addBoxRow(preset) {
                const rowb = el('div', 'disp-boxedit');
                const sel = el('select', 'psel'); sel.style.maxWidth = 'var(--field-w-lg)'; sel.setAttribute('aria-label', 'Box preset');
                presets.forEach(b => { const opt = el('option', null, b.name); opt.value = b.id; sel.append(opt); });
                const cust = el('option', null, 'Custom'); cust.value = '__custom'; sel.append(cust);
                const ins = {};
                let weightTouched = false;
                [['width', 'W'], ['length', 'L'], ['depth', 'D'], ['weight', 'kg']].forEach(([k, ph]) => {
                    const inp = document.createElement('input'); inp.type = 'number'; inp.min = '0'; inp.step = '0.1';
                    inp.className = 'disp-num disp-boxdim'; inp.placeholder = ph === 'kg' ? ph : ph + ' cm'; inp.title = ph === 'kg' ? 'Weight (kg)' : ph + ' (cm)';
                    inp.oninput = staleQuote;
                    ins[k] = inp;
                });
                ins.weight.addEventListener('input', () => { weightTouched = true; });
                const rm = el('button', 'icon-btn'); rm.innerHTML = I.x; rm.title = 'Remove this parcel';
                rm.onclick = () => { const i = boxRows.indexOf(row); if (i >= 0) boxRows.splice(i, 1); rowb.remove(); staleQuote(); };
                const row = { el: rowb, sel, ins };
                function applyPreset(id) {
                    const b = presets.find(x => x.id === id);
                    if (!b) return;
                    ins.width.value = b.width; ins.length.value = b.length; ins.depth.value = b.depth;
                    // Couriers weigh the WHOLE parcel. Shopify's grams are the contents
                    // only, so under-declaring invites a re-weigh surcharge: start from
                    // the box's own weight plus the contents, and let them correct it.
                    if (!weightTouched) {
                        const contents = (boxRows.length <= 1 && o.weight_hint > 0) ? o.weight_hint : 0;
                        ins.weight.value = Math.round(((b.weight || 0) + contents) * 100) / 100;
                    }
                }
                sel.onchange = () => { applyPreset(sel.value); staleQuote(); };
                rowb.append(sel, ins.width, ins.length, ins.depth, ins.weight, rm);
                if (preset) { sel.value = preset.id; applyPreset(preset.id); }
                boxRows.push(row);
                boxHostD.append(rowb);
            }
            addBoxRow(defaultPreset);
            const sizeHelp = el('p', 'field-help', 'Weigh the packed box: couriers re-weigh and bill it.');
            const addBoxBtn = el('button', 'btn disp-addbox'); addBoxBtn.append(ico(I.plus), document.createTextNode('Add a box'));
            addBoxBtn.title = 'Multi-parcel shipment: every box travels on the same booking';
            addBoxBtn.onclick = () => { addBoxRow(defaultPreset); staleQuote(); };
            body.append(addBoxBtn, sizeHelp);

            // ---- insurance ----
            const insWrap = el('label', 'disp-insure');
            const insCb = document.createElement('input'); insCb.type = 'checkbox';
            const insAmt = document.createElement('input'); insAmt.type = 'number'; insAmt.min = '0'; insAmt.step = '1';
            insAmt.className = 'disp-num';
            insAmt.value = (o.goods_value && o.goods_value > 0) ? Math.ceil(o.goods_value) : '';
            insAmt.disabled = true;
            insCb.onchange = () => { insAmt.disabled = !insCb.checked; staleQuote(); };
            insAmt.oninput = staleQuote;
            insWrap.append(insCb, el('span', null, 'Insure this shipment for £'), insAmt);
            body.append(insWrap);

            function collectBoxes() {
                const out = [];
                for (const r of boxRows) {
                    const b = { width: parseFloat(r.ins.width.value), length: parseFloat(r.ins.length.value),
                                depth: parseFloat(r.ins.depth.value), weight: parseFloat(r.ins.weight.value) };
                    if (!(b.width > 0 && b.length > 0 && b.depth > 0 && b.weight > 0)) return null;
                    out.push(b);
                }
                return out.length ? out : null;
            }
            function insuranceAmount() {
                return insCb.checked && parseFloat(insAmt.value) > 0 ? parseFloat(insAmt.value) : 0;
            }

            const quoteBtn = el('button', 'btn btn-primary disp-quote');
            quoteBtn.append(ico(I.truck), document.createTextNode('Get courier quotes'));
            quoteWrap = el('div'); quoteWrap.style.marginTop = 'var(--sp-3)';
            body.append(quoteBtn, quoteWrap);

            // If the queue already priced this exact parcel, show it now. The guard
            // is the same one a manual quote uses: the boxes and insurance on screen
            // must match what was priced, or nothing is reused. Deferred so the rest
            // of this function has finished declaring what renderOptions touches.
            setTimeout(function useCachedQuote() {
                const bx = collectBoxes();
                if (!bx) return;
                const ins = insuranceAmount();
                const hit = cachedQuote(o.id, bx, ins);
                if (!hit) return;
                lastBoxes = bx; lastInsurance = ins;
                quote = hit; chosen = null;
                renderOptions();
                const note = el('div', 'sub');
                note.textContent = 'Priced a moment ago while you were in the queue. '
                    + 'Press "Get courier quotes" to reprice.';
                quoteWrap.append(note);
            }, 0);

            quoteBtn.onclick = async () => {
                const bx = collectBoxes();
                if (!bx) { addToast('Every parcel needs a size (width, length, depth) and weight above zero.'); return; }
                lastBoxes = bx;
                lastInsurance = insuranceAmount();   // book exactly what we priced
                quoteBtn.disabled = true; quoteWrap.innerHTML = '';
                const t = el('div', 'thinking'); t.append(loader(), el('span', null, 'Asking World Options for prices…')); quoteWrap.append(t);
                try {
                    quote = await api('/api/dispatch/quote', { order_id: o.id, boxes: bx, insurance: lastInsurance });
                    quoteCache.set(String(o.id), { sig: boxSig(bx, lastInsurance), quote: quote, at: Date.now() });
                    chosen = null; renderOptions();
                }
                catch (e) {
                    quoteWrap.innerHTML = '';
                    quoteWrap.append(errBubble(e.message || 'Could not get quotes'));
                    /* Show what was actually sent, open, exactly as a failed
                       booking does. A quote that will not price is the FIRST
                       thing that blocks a dispatch, and it was the one failure
                       in this flow that handed the operator nothing to look at. */
                    const qt = techPanel(e.tech);
                    if (qt) { qt.open = true; quoteWrap.append(qt); }
                }
                quoteBtn.disabled = false;
            };

            // ---- customs (international only) ----
            // The card lives inside quoteWrap, which a re-quote clears, so typed
            // goods lines are stashed here and seeded back rather than lost.
            const customsLines = [];
            let customsSaved = null, recvTaxSaved = '';
            let recvTaxIn = null;
            function stashCustoms() {
                if (!customsLines.length) return;
                const rows = customsLines.map(l => ({
                    description: l.dIn.value, quantity: l.qIn.value,
                    unit_price: l.pIn.value, hs: l.hIn.value }))
                    .filter(r => (r.description || '').trim() || (r.unit_price || '').trim());
                if (rows.length) customsSaved = rows;
                if (recvTaxIn) recvTaxSaved = recvTaxIn.value;
            }
            function customsCard() {
                const card = el('div', 'disp-customs');
                card.append(el('div', 'disp-subhead', 'Customs declaration (international)'));
                if (!quote.has_eori) {
                    card.append(el('div', 'disp-warn', 'Your EORI number is missing. Add it under Shipping settings, International, then re-quote. International bookings cannot go without it.'));
                }
                card.append(el('p', 'field-help', 'What is in the parcel, for customs.'));
                const linesHost = el('div');
                customsLines.length = 0;
                function addLine(pre) {
                    const rowc = el('div', 'disp-boxedit');
                    const dIn = document.createElement('input'); dIn.type = 'text'; dIn.className = 'disp-num'; dIn.placeholder = 'Description'; dIn.style.flex = '2 1 auto';
                    const qIn = document.createElement('input'); qIn.type = 'number'; qIn.min = '1'; qIn.step = '1'; qIn.className = 'disp-num disp-boxdim'; qIn.placeholder = 'Qty';
                    const pIn = document.createElement('input'); pIn.type = 'number'; pIn.min = '0'; pIn.step = '0.01'; pIn.className = 'disp-num disp-boxdim'; pIn.placeholder = 'Unit £';
                    const hIn = document.createElement('input'); hIn.type = 'text'; hIn.spellcheck = false; hIn.setAttribute('aria-label', 'HS code'); hIn.className = 'disp-num disp-boxdim'; hIn.placeholder = 'HS code'; hIn.style.width = 'var(--field-w-sm)';
                    // Origin is ON the card: the commercial invoice needs it, and an
                    // invisible wrong value is worse than a visible editable one.
                    const oIn = document.createElement('input'); oIn.type = 'text'; oIn.spellcheck = false; oIn.setAttribute('aria-label', 'Country of origin'); oIn.className = 'disp-num disp-boxdim'; oIn.placeholder = 'Origin'; oIn.maxLength = 2; oIn.style.width = 'var(--field-w-xs)';
                    oIn.title = 'Country of origin (2 letters), where the item was made, for the commercial invoice';
                    if (pre) {
                        dIn.value = pre.description || ''; qIn.value = pre.quantity || 1;
                        /* 0 is a value, and the zero warning's cue; '' is a gap the booking stops on. */
                        pIn.value = (pre.unit_price === 0 || pre.unit_price) ? pre.unit_price : '';
                        hIn.value = pre.hs || ''; oIn.value = pre.origin || 'GB';
                    }
                    else { oIn.value = 'GB'; }
                    const rm = el('button', 'icon-btn'); rm.innerHTML = I.x; rm.title = 'Remove line';
                    const line = { dIn, qIn, pIn, hIn, oIn, key: (pre && pre.key) || '' };
                    rm.onclick = () => { const i = customsLines.indexOf(line); if (i >= 0) customsLines.splice(i, 1); rowc.remove(); };
                    rowc.append(dIn, qIn, pIn, hIn, oIn, rm);
                    customsLines.push(line);
                    linesHost.append(rowc);
                }
                if (customsSaved && customsSaved.length) {
                    customsSaved.forEach(r => addLine(r));       // keep what they typed
                } else if (quote.customs_items && quote.customs_items.length) {
                    // Straight from Shopify: the HS code set on each product, and
                    // the COST price. Customs declares what the goods are worth to
                    // you, not what the customer paid.
                    let fellBack = [];
                    quote.customs_items.forEach(it => {
                        // Gobos are declared at SALE value by design, so only a
                        // stocked product missing its cost is worth flagging.
                        if (it.needs_cost) fellBack.push(it.title);
                        addLine({
                            /* What the DECLARATION calls it, not the shop's
                               product name: a gobo crosses a border as a glass
                               optical filter. Still editable on the card. */
                            description: it.customs_description || it.title || 'Custom glass gobo',
                            quantity: it.quantity || 1,
                            unit_price: isNaN(parseFloat(it.unit_value || it.cost || it.price)) ? ''
                                : parseFloat(it.unit_value || it.cost || it.price),
                            hs: it.hs_code || quote.default_hs_code || '',
                            origin: it.origin || '',
                            key: it.key || ''
                        });
                    });
                    const recalled = quote.customs_items.filter(it => it.value_basis === 'remembered');
                    if (recalled.length) card.append(el('div', 'sub',
                        'Values for ' + recalled.map(it => it.title).join(', ')
                        + ' are what you entered last time. Change them here if they are wrong and the new ones stick.'));
                    if (fellBack.length) card.append(el('div', 'sub',
                        'No cost price in Shopify for: ' + fellBack.join(', ')
                        + '. The sale price is filled in instead; set the cost on the product to fix this.'));
                    const noHs = quote.customs_items.filter(it => !it.hs_code).map(it => it.title);
                    if (noHs.length && !quote.default_hs_code) card.append(el('div', 'sub',
                        'No HS code in Shopify for: ' + noHs.join(', ')
                        + '. Add it on the product (Customs information) so it fills in automatically.'));
                } else {
                    (o.items || []).forEach(it => addLine({
                        description: (it.artwork || it.title || 'Custom glass gobo'),
                        quantity: it.quantity || 1,
                        /* A zero price is a value of 0, kept on the line so the
                           zero warning can say so; it used to become an empty
                           box, and an empty box was dropped from the declaration. */
                        unit_price: isNaN(parseFloat(it.price)) ? '' : parseFloat(it.price),
                        hs: quote.default_hs_code || ''
                    }));
                }
                if (!customsLines.length) addLine({ description: 'Custom glass gobo', quantity: 1, hs: quote.default_hs_code || '' });
                card.append(linesHost);
                const addL = el('button', 'btn'); addL.append(ico(I.plus), document.createTextNode('Add line'));
                addL.onclick = () => addLine(null);
                card.append(addL);
                const zeroWarn = el('div', 'disp-warn'); zeroWarn.style.display = 'none';
                zeroWarn.textContent = 'One or more lines have a unit value of 0. Customs treats zero-value goods '
                    + 'as suspect and can hold the shipment; enter what each item sells for.';
                card.append(zeroWarn);
                const checkZeros = () => {
                    const any = customsLines.some(l => l.dIn.value.trim() && !(parseFloat(l.pIn.value) > 0));
                    zeroWarn.style.display = any ? '' : 'none';
                };
                card.addEventListener('input', checkZeros);
                setTimeout(checkZeros, 0);
                const rt = el('label', 'disp-fld'); rt.style.marginTop = 'var(--sp-2)';
                rt.append(el('span', 'disp-fld-lab', "Receiver's tax / VAT id (optional, helps clearance)"));
                recvTaxIn = document.createElement('input'); recvTaxIn.type = 'text'; recvTaxIn.className = 'disp-num';
                /* What the customer already gave Shopify, so an export does not
                   wait on somebody hunting for it. Anything typed on this card
                   wins - the prefill is a starting point, not a decision. */
                recvTaxIn.value = (recvTaxSaved !== null && recvTaxSaved !== undefined && recvTaxSaved !== '')
                    ? recvTaxSaved : (quote.receiver_tax_id || '');
                rt.append(recvTaxIn); card.append(rt);
                if (!recvTaxSaved && quote.receiver_tax_id && quote.receiver_tax_source) {
                    /* Named, because an autofilled number nobody can trace is
                       one nobody checks. */
                    card.append(el('div', 'sub', 'Tax id filled in from '
                        + quote.receiver_tax_source + '. Change it here if it is wrong.'));
                }
                return card;
            }
            function collectCustoms() {
                if (!quote || !quote.international) return null;
                const lines = [];
                for (const l of customsLines) {
                    const d = l.dIn.value.trim(), q = parseInt(l.qIn.value, 10), p = parseFloat(l.pIn.value);
                    if (!d || !(q > 0) || !(p >= 0) || isNaN(p)) continue;
                    lines.push({ description: d, quantity: q, unit_price: p, hs: l.hIn.value.trim(),
                                 country: (l.oIn.value.trim().toUpperCase() || 'GB'), key: l.key || '' });
                }
                return { lines, receiver_tax_id: recvTaxIn ? recvTaxIn.value.trim() : '' };
            }
            function customsProblem() {
                if (!quote || !quote.international) return '';
                if (!quote.has_eori) return 'Add your EORI number in Shipping settings first.';
                /* A line with a description but no quantity or unit value used
                   to be dropped from the declaration in silence, and the
                   booking went ahead with a commercial invoice one item short
                   of the parcel. Name the line and stop. */
                for (let i = 0; i < customsLines.length; i++) {
                    const l = customsLines[i];
                    const d = l.dIn.value.trim();
                    if (!d) continue;
                    const q = parseInt(l.qIn.value, 10), p = parseFloat(l.pIn.value);
                    if (!(q > 0)) return 'Customs line ' + (i + 1) + ' (' + d + ') needs a quantity.';
                    if (isNaN(p) || p < 0) return 'Customs line ' + (i + 1) + ' (' + d + ') needs a unit value. Enter 0 only if it really is worth nothing.';
                }
                const cst = collectCustoms();
                if (!cst.lines.length) return 'Fill in at least one customs line: description, quantity and unit value.';
                return '';
            }

            function renderOptions() {
                quoteWrap.innerHTML = '';
                const opts = (quote && quote.options) || [];
                if (!opts.length) { quoteWrap.append(el('div', 'empty', 'No courier options came back for this parcel and address.')); return; }
                if (quote.currency_note) quoteWrap.append(el('div', 'sub', quote.currency_note));
                if (quote.insurance) quoteWrap.append(el('div', 'sub', 'Prices include insurance cover for ' + fmtPrice(parseFloat(quote.insurance), quote.currency) + '.'));
                if (quote.dropoff) quoteWrap.append(el('div', 'sub', 'Drop-off tariffs: you take the parcel to the shop shown on the option.'));
                if (quote.international) quoteWrap.append(customsCard());
                quoteWrap.append(el('div', 'disp-subhead', opts.length + ' option' + (opts.length === 1 ? '' : 's') + ' · cheapest first'));
                const list = el('div', 'disp-opts');
                const cheapest = Math.min.apply(null, opts.map(o => Number(o.amount) || Infinity));
                opts.forEach((op, i) => {
                    const rowl = el('label', 'disp-opt');
                    const rb = document.createElement('input'); rb.type = 'radio'; rb.name = 'disp-opt'; rb.value = i;
                    rb.onchange = () => { chosen = op; list.querySelectorAll('.disp-opt').forEach(e => e.classList.remove('on')); rowl.classList.add('on'); renderConfirm(); };
                    rowl.append(rb);

                    const drop = !!(op.shops && op.shops.length);
                    const top = el('div', 'disp-opt-top');
                    // The courier's name leads: the product code meant nothing to anyone.
                    // When World Options names no carrier the option must still be
                    // identifiable, so it says so plainly and keeps their code on screen.
                    const known = !!op.carrier_label;
                    const lead = el('span', 'disp-opt-prov' + (known ? '' : ' disp-opt-unknown'),
                        known ? op.carrier_label : 'Carrier not named');
                    if (!known) lead.title = 'World Options did not say which courier runs this service. '
                        + 'Their service code is ' + (op.product_code || op.service_type_code || 'not given') + '.';
                    top.append(lead);
                    top.append(el('span', 'disp-opt-carrier',
                        op.service_name || (known ? '' : 'Courier service')));
                    if (!known && op.product_code) top.append(el('span', 'lbl-chip', op.product_code));
                    if (op.product_code) rowl.title = (known ? op.carrier_label + ' ' : '')
                        + (op.service_name || '') + ' (World Options service ' + op.product_code + ')';
                    if (Number(op.amount) === cheapest) top.append(el('span', 'lbl-chip made', 'Cheapest'));
                    /* How THIS courier collects, from the per-courier setting.
                       A daily UPS collection is a different fact from DHL
                       having to be asked each time, and the desk should not
                       have to remember which is which. */
                    if (op.collection_message) {
                        const needsBooking = String(op.collection_option || '').indexOf('Need_To_Book') >= 0;
                        const cc = el('span', 'lbl-chip ' + (needsBooking ? 'warn' : 'note'),
                                      op.collection_message);
                        cc.title = needsBooking
                            ? 'Booking this also asks ' + (op.carrier_label || 'the courier')
                              + ' to collect. Set it under Settings, Shipping, Collections by courier.'
                            : (op.carrier_label || 'This courier') + ' already collects, so no pickup is '
                              + 'requested. Set it under Settings, Shipping, Collections by courier.';
                        top.append(cc);
                    }
                    if (drop) top.append(el('span', 'lbl-chip note', 'Drop-off'));
                    if (op.no_signature) {
                        const ns = el('span', 'lbl-chip note', 'NO SIGNATURE');
                        ns.title = 'Cheaper, but nobody signs for it on delivery, so there is no proof of receipt';
                        top.append(ns);
                    }
                    // Not to the customer's door: they collect it from a shop.
                    if (op.delivery_dropoff) top.append(el('span', 'lbl-chip warn', 'Collect from shop'));
                    rowl.append(top);
                    const priceCell = el('div', 'disp-opt-price');
                    priceCell.append(el('span', 'p-inc', fmtPrice(op.amount, op.currency)));
                    if (op.amount_ex_vat != null && op.vat) {
                        priceCell.append(el('span', 'p-ex', fmtPrice(op.amount_ex_vat, op.currency) + ' ex VAT'));
                    }
                    rowl.append(priceCell);

                    // The promise: arrival first, collection deadline last (clipped first).
                    const when = el('div', 'disp-opt-when');
                    if (op.delivery_date) {
                        when.append(el('span', 'd', op.delivery_date));
                        if (op.delivery_time) when.append(el('span', 't', ' ' + op.delivery_time));
                    } else {
                        when.append(el('span', 't', 'Delivery date not quoted'));
                    }
                    if (op.pickup_time || op.pickup_date) {
                        const w = (drop ? 'drop off by ' : 'collect ') + (op.pickup_time || op.pickup_date);
                        when.append(el('span', 'p', '  \u00b7  ' + w));
                    }
                    rowl.append(when);
                    if (op.no_signature && op.saves_vs_signed) {
                        when.append(el('span', 'p', '  ·  saves ' + fmtPrice(op.saves_vs_signed, op.currency)));
                    }
                    if (Number(op.amount) > cheapest) {
                        const dl = el('span', 'p', '  ·  +' + fmtPrice(op.amount - cheapest, op.currency));
                        dl.title = fmtPrice(op.amount - cheapest, op.currency) + ' more than the cheapest option';
                        when.append(dl);
                    }

                    // Detail belongs to the chosen option only: row height is what
                    // decides whether 8 options can be compared without scrolling.
                    const shop = drop ? op.shops[0] : null;
                    if (shop || (op.delivery_shops && op.delivery_shops.length) || (op.breakdown && op.breakdown.length)) {
                        const more = el('div', 'disp-opt-more');
                        const dshop = (op.delivery_shops || [])[0];
                        if (dshop) {
                            const ds = el('div', 'disp-opt-shop');
                            ds.append(el('b', null, 'Customer collects from ' + (dshop.name || 'a pickup shop')));
                            ds.append(document.createTextNode(', ' + [dshop.street, dshop.city, dshop.postcode].filter(Boolean).join(', ')));
                            more.append(ds);
                        }
                        if (shop) {
                            const s = el('div', 'disp-opt-shop');
                            s.append(el('b', null, 'Drop off at ' + (shop.name || 'parcel shop')));
                            s.append(document.createTextNode(', ' + [shop.street, shop.postcode].filter(Boolean).join(', ')
                                + (shop.distance ? ' (' + shop.distance + ')' : '')));
                            more.append(s);
                        }
                        if (op.breakdown && op.breakdown.length) {
                            const det = document.createElement('details'); det.className = 'disp-breakdown';
                            const sum = document.createElement('summary'); sum.textContent = 'Price details';
                            det.append(sum);
                            op.breakdown.forEach(bd => det.append(el('div', 'sub', bd.label + ': ' + fmtPrice(bd.amount, op.currency))));
                            det.onclick = (e) => e.stopPropagation();
                            more.append(det);
                        }
                        rowl.append(more);
                    }
                    list.append(rowl);
                });
                quoteWrap.append(list);
                // Expected a service that is not here? Ask World Options the same
                // question several ways and show what each way returns.
                const diagRow = el('div'); diagRow.style.marginTop = 'var(--sp-2)';
                const diagBtn = el('button', 'btn'); diagBtn.style.fontSize = 'var(--text-xs)';
                diagBtn.textContent = 'Missing a service?';
                diagBtn.title = 'Re-quote this parcel several ways to see which services each returns. Free, and books nothing.';
                const diagOut = el('div'); diagOut.style.marginTop = 'var(--sp-2)';
                diagBtn.onclick = async () => {
                    diagBtn.disabled = true; diagOut.innerHTML = '';
                    const t = el('div', 'thinking'); t.append(loader(), el('span', null, 'Asking World Options several ways…')); diagOut.append(t);
                    try {
                        const d = await api('/api/dispatch/diagnose', { order_id: o.id, boxes: lastBoxes });
                        diagOut.innerHTML = '';
                        if (d.extra_found && d.extra_found.length) {
                            diagOut.append(el('div', 'disp-warn', 'These services only appear under different settings: '
                                + d.extra_found.map(x => (x.name || '') + ' (' + (x.code || '') + ')').join(', ')
                                + '. Send this to your developer and it can be turned on for every quote.'));
                        } else {
                            diagOut.append(el('div', 'sub', 'No extra services appeared under any setting, so this really is everything World Options offers for this parcel and address.'));
                        }
                        (d.rows || []).forEach(r => {
                            const det = document.createElement('details'); det.className = 'disp-breakdown';
                            const sum = document.createElement('summary');
                            sum.textContent = r.label + (r.error ? ' (failed)' : ' (' + r.services.length + ')');
                            det.append(sum);
                            if (r.error) det.append(el('div', 'sub', r.error));
                            r.services.forEach(s => det.append(el('div', 'sub',
                                (s['new'] ? 'New: ' : '') + s.name + (s.code ? '  (' + s.code + ')' : '')
                                + '  ' + fmtPrice(s.amount, s.currency)
                                + (s.delivery ? '  ' + s.delivery : ''))));
                            diagOut.append(det);
                        });
                    } catch (e) { diagOut.innerHTML = ''; diagOut.append(errBubble(e.message || 'Could not run the check')); }
                    diagBtn.disabled = false;
                };
                diagRow.append(diagBtn, diagOut);
                quoteWrap.append(diagRow);
                quoteWrap.append((function () { const c = el('div', 'disp-confirm'); c.id = 'disp-confirm'; return c; })());
            }

            function renderConfirm() {
                const conf = quoteWrap.querySelector('#disp-confirm'); if (!conf) return; conf.innerHTML = '';
                if (!chosen) return;
                // Restate the choice. The cards scroll away above this block, and the
                // next click spends money.
                const pick = el('div', 'disp-pick');
                pick.append(el('span', 'disp-pick-name', optionName(chosen)));
                const whenBits = [chosen.delivery_date, chosen.delivery_time].filter(Boolean).join(' ');
                if (whenBits) pick.append(el('span', 'disp-pick-when', 'arrives ' + whenBits));
                conf.append(pick);
                const notifyWrap = el('label', 'disp-notify');
                const nb = document.createElement('input'); nb.type = 'checkbox'; nb.checked = cfg.notify_customer !== false;
                notifyWrap.append(nb, el('span', null, ' Email the customer their tracking when this order is marked made'));
                conf.append(notifyWrap);
                if (cfg.ready_time || cfg.close_time) {
                    conf.append(el('div', 'sub', 'Collection window: '
                        + (cfg.ready_time ? 'ready from ' + cfg.ready_time : '')
                        + (cfg.ready_time && cfg.close_time ? ', ' : '')
                        + (cfg.close_time ? 'closes at ' + cfg.close_time : '')
                        + '. Change it in Shipping settings.'));
                } else {
                    conf.append(el('div', 'sub', 'No collection window set; the courier gets no ready or close time. Set one in Shipping settings.'));
                }
                // Signature-on-delivery, when the chosen carrier offers options.
                if (chosen.no_signature) {
                    conf.append(el('div', 'disp-warn', 'No signature is collected on delivery. '
                        + 'Cheaper, but there is no proof the customer received it.'));
                }
                const sigGroups = (cfg.signature_options || {});
                const sigVals = chosen.no_signature ? [] : (sigGroups[(chosen.carrier_name || '').toUpperCase()] || []);
                let sigSel = null;
                if (sigVals.length) {
                    const sigF = el('label', 'disp-fld'); sigF.style.margin = 'var(--sp-1-5) 0';
                    sigF.append(el('span', 'disp-fld-lab', 'Delivery signature'));
                    sigSel = el('select', 'psel');
                    const d0 = el('option', null, 'Courier default'); d0.value = ''; sigSel.append(d0);
                    sigVals.forEach(v => {
                        const lab = v.replace(/^[^_]+_/, '').replace(/_/g, ' ');
                        const op2 = el('option', null, lab); op2.value = v; sigSel.append(op2);
                    });
                    // A signature upgrade is a PRICED option: the quote on the
                    // button was fetched without it, so booking after changing
                    // this charged a price nobody was shown. Say so, and make
                    // the button re-quote rather than book a stale figure.
                    sigSel.onchange = () => {
                        const changed = !!sigSel.value;
                        book.classList.toggle('needs-requote', changed);
                        if (changed) {
                            book.innerHTML = '';
                            book.append(ico(I.refresh), document.createTextNode('Re-check the price'));
                        } else { setLabel(); }
                    };
                    sigF.append(sigSel); conf.append(sigF);
                }
                if (chosen.delivery_dropoff) {
                    const ds = (chosen.delivery_shops || [])[0] || {};
                    conf.append(el('div', 'disp-warn', 'This service does not deliver to the customer. '
                        + 'It goes to ' + (ds.name || 'a pickup shop')
                        + ([ds.street, ds.postcode].filter(Boolean).length ? ' (' + [ds.street, ds.postcode].filter(Boolean).join(', ') + ')' : '')
                        + ' and the customer collects it. Only pick this if that is acceptable for this order.'));
                }
                conf.append(el('div', 'disp-charge', 'Booking charges your World Options account.'));
                const book = el('button', 'btn btn-primary disp-book');
                if (chosen.amount_ex_vat != null && chosen.vat) {
                    conf.append(el('div', 'disp-vat', fmtPrice(chosen.amount_ex_vat, chosen.currency) + ' ex VAT'
                        + '   +   ' + fmtPrice(chosen.vat, chosen.currency) + ' VAT'
                        + '   =   ' + fmtPrice(chosen.amount, chosen.currency) + ' inc VAT'));
                }
                const setLabel = () => { book.innerHTML = ''; book.append(ico(I.truck), document.createTextNode('Book & dispatch · ' + fmtPrice(chosen.amount, chosen.currency) + ' inc VAT')); };
                setLabel();
                book.onclick = async () => {
                    // The signature was changed after this price was quoted:
                    // re-quote instead of booking a figure that was never for
                    // this service.
                    if (book.classList.contains('needs-requote')) {
                        book.classList.remove('needs-requote');
                        quoteCache.delete(String(o.id));   // the cached price was for no signature
                        quoteBtn.click();                  // re-price with the option chosen
                        return;
                    }
                    const cprob = customsProblem();
                    if (cprob) { addToast(cprob); return; }
                    /* Disabled BEFORE the question, not after it. A double click
                       used to open two confirm dialogs, and answering both booked
                       and paid for two labels on one order. */
                    book.disabled = true;
                    if (!await uiConfirm('Book ' + optionName(chosen) + ' for ' + fmtPrice(chosen.amount, chosen.currency) + ' inc VAT?\n\nThis books the courier and charges your World Options account.', { title: 'Book this courier', okText: 'Book & dispatch' })) { book.disabled = false; return; }
                    booking = true;
                    book.textContent = 'Booking with ' + (carrierLabel(chosen.carrier_name || '') || optionName(chosen))
                        + '… do not close this window';
                    x.disabled = true;
                    askedCollection = collectionForRun || '';
                    const doBook = (force, confirmUnknown) => api('/api/dispatch/book', {
                        order_id: o.id, name: orderNo(o), option: chosen, boxes: lastBoxes, notify: nb.checked, force: !!force,
                        confirm_unknown: !!confirmUnknown,
                        insurance: lastInsurance, signature: sigSel ? sigSel.value : '',
                        customs: quote.international ? collectCustoms() : null,
                        collection_option: askedCollection
                    });
                    try {
                        let res, force = false, sure = false;
                        for (;;) {
                            try { res = await doBook(force, sure); break; }
                            catch (e) {
                                // Shopify already shows the order fulfilled: ask, then retry once.
                                if (!force && /retry with the confirmation/.test(e.message || '')) {
                                    if (!await uiConfirm('Shopify already shows this order as fulfilled, which usually means it has already shipped. Book a courier anyway?', { title: 'Order looks already shipped', okText: 'Book anyway' })) { book.disabled = false; setLabel(); return; }
                                    force = true; continue;
                                }
                                // An earlier booking of this order never recorded its outcome.
                                if (!sure && /outcome was never recorded/.test(e.message || '')) {
                                    if (!await uiConfirm(e.message + '\n\nOnly if there is no such booking in World Options, book it now.', { title: 'A booking may already exist', okText: 'I checked: book it', danger: true })) { book.disabled = false; setLabel(); booking = false; x.disabled = false; return; }
                                    sure = true; continue;
                                }
                                throw e;
                            }
                        }
                        booking = false; x.disabled = false;
                        quoteCache.delete(String(o.id));
                        setDispatchState(o.id, res.dispatch || {});
                        renderResultSafe(res);
                        // The queue behind this window is a nicety; the result is not.
                        try { if (labelsCache && document.querySelector('#view-labels.active')) renderLabels(); }
                        catch (e) { addToast('The result is below. The queue behind this window could not be redrawn; press Refresh when you are done.'); }
                    } catch (e) {
                        booking = false; x.disabled = false;
                        const msg = String(e.message || 'Booking failed');
                        // If the outcome is unknown the courier MAY already be booked and
                        // charged: do not re-arm the button into a second charge.
                        const unknown = e.noReply || BOOKING_UNKNOWN.test(msg);
                        toastError(msg);
                        const tech = techPanel(e.tech);
                        /* Open, not collapsed. A booking that will not go through is
                           precisely the moment somebody needs to see what was sent,
                           and a shut drawer marked "technical details" is a drawer
                           nobody opens. The label path already did this. */
                        /* The confirm card is inside the body, and a result that
                           got half way through drawing may have replaced it. An
                           error appended to a detached card is an error nobody
                           ever sees, so it goes wherever is still on screen. */
                        const host = conf.isConnected ? conf : body;
                        if (tech) { tech.open = true;
                            host.querySelectorAll('.disp-tech').forEach(n => n.remove()); host.append(tech); }
                        if (unknown) {
                            book.textContent = 'Check before booking again';
                            const warn = el('div', 'disp-warn', msg + ' Close this window, press Refresh, and look for a Booked chip on the order before trying again.');
                            host.append(warn);
                        } else {
                            book.disabled = false; setLabel();
                        }
                    }
                };
                conf.append(book);
            }

            /* The courier is booked and the account is charged before any of
               this runs, so nothing here may leave the operator with an empty
               window. The result is built OFF SCREEN and swapped in once: a
               throw half way through leaves what was already on screen, and the
               fallback below still puts the tracking number in front of them.
               Clearing the body first and appending as we went is exactly how a
               charged booking once showed a blank panel. */
            function renderResult(res) {
                const out = el('div');
                const s = res.shipment || {};
                let clearArranged = false;
                if (askedCollection && collectionForRun === askedCollection) {
                    clearArranged = true;
                    if (askedCollection.indexOf('Need_To_Book') >= 0) {
                        out.append(el('div', 'disp-ok-line',
                            'A collection was requested with this booking. The next one goes back to '
                            + 'your standing arrangement, so you are not charged for a second pickup.'));
                    }
                }
                const okBar = el('div', 'disp-result-head');
                okBar.append(ico(I.check), el('span', null, 'Dispatched with ' + shipmentName(s)));
                out.append(okBar);
                const tb = el('div', 'disp-track'); tb.append(el('span', null, 'Tracking '), el('b', null, s.tracking_number || '(pending)')); out.append(tb);
                if (s.amount != null) {
                    out.append(el('div', 'sub', 'Quoted ' + fmtPrice(s.amount, s.currency) + ' inc VAT'
                        + (s.amount_ex_vat != null && s.vat ? ' (' + fmtPrice(s.amount_ex_vat, s.currency) + ' ex VAT)' : '')
                        + '. Your World Options invoice shows the final charge.'));
                }
                if (res.warning) out.append(el('div', 'disp-warn', res.warning));
                if (s.collection_date) out.append(el('div', 'sub',
                    'Collection reference: ' + collRefText(s.collection_date)));
                if (res.insured) out.append(el('div', 'sub', 'Insured for ' + fmtPrice(parseFloat(res.insured), s.currency) + '.'));
                if (res.delivery_shop) out.append(el('div', 'disp-warn', 'The customer collects this from ' + res.delivery_shop + '. It is not delivered to their address.'));
                if (res.dropoff_shop) out.append(el('div', 'disp-warn', 'Drop the parcel at: ' + [res.dropoff_shop.name, res.dropoff_shop.street, res.dropoff_shop.city, res.dropoff_shop.postcode].filter(Boolean).join(', ') + '. The courier will NOT collect from you.'));
                if (res.international) out.append(el('div', 'sub', 'Customs declaration sent; World Options generates the commercial invoice.'));
                if (res.contact_note) out.append(el('div', 'disp-warn', res.contact_note));
                if (res.book_note) out.append(el('div', 'disp-warn', res.book_note));
                const f = res.fulfillment || {};
                if (res.awaiting_made) {
                    out.append(el('div', 'disp-await', 'Not shipped yet. Shopify stays unfulfilled and the customer is not emailed until you mark this order made.'));
                }
                else if (f.ok) out.append(el('div', 'disp-ok-line', res.notified ? 'Order marked fulfilled in Shopify and the customer was emailed tracking.' : 'Order marked fulfilled in Shopify.'));
                else if (f.reason === 'permission') out.append(el('div', 'disp-warn', 'Booked, but the app could not mark the order fulfilled (missing the write_fulfillments permission). Fulfil it manually in Shopify, or grant the permission and it will work next time.'));
                else if (f.reason === 'nothing_to_fulfill') out.append(el('div', 'sub', 'Shopify had nothing left to fulfil for this order.'));
                else if (f.reason && f.reason !== 'not_attempted') out.append(el('div', 'disp-warn', f.detail || 'Shopify fulfilment could not be completed.'));
                if (res.tag && !res.tag.ok && res.tag.note) out.append(el('div', 'disp-warn', res.tag.note));
                labelButtons(out, s.labels);
                const done = el('button', 'btn'); done.style.marginTop = 'var(--sp-4)'; done.textContent = 'Done'; done.onclick = close;
                out.append(done);
                body.innerHTML = '';
                body.append(out);
                /* Only now that a real booking has carried it: leaving it armed
                   is how a morning of parcels turns into a morning of pickup
                   charges, and clearing it before the paint could throw would
                   lose the arrangement without ever saying so. */
                if (clearArranged) collectionForRun = null;
            }

            /* Whatever goes wrong drawing the result, the tracking number reaches
               the desk. Money has already moved by the time this is called. */
            function renderResultSafe(res) {
                try { renderResult(res); return; }
                catch (err) {
                    const tn = (((res || {}).shipment) || {}).tracking_number || '';
                    try {
                        body.innerHTML = '';
                        const h = el('div', 'disp-result-head');
                        h.append(ico(I.check), el('span', null, 'Booked and charged'));
                        body.append(h);
                        const tb = el('div', 'disp-track');
                        tb.append(el('span', null, 'Tracking '), el('b', null, tn || '(none returned)'));
                        body.append(tb);
                        body.append(el('div', 'disp-warn',
                            'The courier is booked, but this window could not be drawn: '
                            + String((err && err.message) || err)
                            + '. Write the tracking number down, then close this and press '
                            + 'Dispatch again to see the shipment and print the label.'));
                        const done = el('button', 'btn'); done.style.marginTop = 'var(--sp-4)';
                        done.textContent = 'Done'; done.onclick = close; body.append(done);
                    } catch (e2) {
                        // No helpers left. Plain text still carries the number.
                        body.textContent = 'Booked and charged. Tracking: ' + (tn || 'unknown')
                            + '. Close this and press Dispatch again for the label.';
                    }
                }
            }

            function renderShipmentSummary(d) {
                body.innerHTML = '';
                (function(){ var h = el('div', 'disp-result-head'); h.append(ico(I.check), el('span', null, 'Dispatched with ' + shipmentName(d))); body.append(h); })();
                const tb = el('div', 'disp-track'); tb.append(el('span', null, 'Tracking '), el('b', null, d.tracking_number || '')); body.append(tb);
                if (d.amount != null) body.append(el('div', 'sub', 'Quoted ' + fmtPrice(d.amount, d.currency)));
                // The margin in one line: what the customer paid for delivery against
                // what the courier costs before VAT.
                if (d.shipping_paid && d.amount_ex_vat != null) {
                    const paid = parseFloat(d.shipping_paid), ex = parseFloat(d.amount_ex_vat);
                    if (!isNaN(paid) && !isNaN(ex)) {
                        const diff = paid - ex;
                        body.append(el('div', 'sub', 'Customer paid ' + fmtPrice(paid, d.currency)
                            + ' for delivery \u00b7 courier ' + fmtPrice(ex, d.currency) + ' ex VAT \u00b7 '
                            + (diff >= 0 ? 'covered with ' + fmtPrice(diff, d.currency) + ' over'
                                         : 'short by ' + fmtPrice(-diff, d.currency))));
                    }
                }
                if (d.dispatched_at) body.append(el('div', 'sub', 'Dispatched ' + fmtDate(d.dispatched_at)));
                const bar = el('div', 'disp-actions');
                const rp = el('button', 'btn btn-primary'); rp.append(ico(I.printer), document.createTextNode('Reprint label'));
                rp.onclick = async () => {
                    rp.disabled = true;
                    try {
                        const r = await api('/api/dispatch/label', { order_id: o.id });
                        // Straight to the print dialog; buttons only appear for
                        // anything that cannot print in place.
                        if (!printLabelImages(r.labels || [])) labelButtons(body, r.labels, 'Print label');
                        if (r.tech) {
                            toastError('The label could not be downloaded from World Options. The details below say exactly why.');
                            body.querySelectorAll('.disp-tech').forEach(n => n.remove());
                            const tp = techPanel(r.tech); if (tp) { tp.open = true; body.append(tp); }
                        }
                    }
                    catch (e) { toastError(e.message || 'Could not fetch the label'); }
                    rp.disabled = false;
                };
                bar.append(rp);
                const cancel = el('button', 'btn'); cancel.append(ico(I.x), document.createTextNode('Cancel shipment'));
                cancel.onclick = async () => {
                    if (!await uiConfirm('Cancel this shipment at World Options? Depending on the courier you may still be charged.', { title: 'Cancel shipment', okText: 'Cancel shipment', cancelText: 'Keep it' })) return;
                    cancel.disabled = true;
                    try {
                        const cr = await api('/api/dispatch/cancel', { order_id: o.id, tracking_number: d.tracking_number });
                        setDispatchState(o.id, { canceled: true });
                        addToast(cr && cr.note ? ('Shipment cancelled. ' + cr.note) : 'Shipment cancelled.');
                        if (labelsCache && document.querySelector('#view-labels.active')) renderLabels();
                        close();
                    } catch (e) { cancel.disabled = false; toastError(e.message || 'Could not cancel'); }
                };
                bar.append(cancel);
                body.append(bar);
            }
        }

        /* A parcel with no Shopify order behind it: a replacement, a sample, a
           supplier return. Paste the address, add a box and a value, book. The
           shipment id is minted HERE, once, and reused if the merchant books
           again after an error, because without an order id it is the only thing
           that can tell a second click apart from a second parcel. */
        const ADDR_FIELDS = [
            ['name', 'Name', 'Who it is for'], ['company', 'Company', 'Business name, if any'],
            ['street', 'Address line 1', ''], ['street2', 'Address line 2', ''],
            ['city', 'Town or city', ''], ['state', 'County or state', ''],
            ['postcode', 'Postcode', ''], ['country', 'Country', '2-letter code, e.g. GB'],
            ['phone', 'Phone', 'The courier may need it'], ['email', 'Email', 'For tracking updates'],
        ];

        /* The collection arrangement for the run in progress.

           World Options has no endpoint for booking a collection on its own -
           their service exposes Rate, Shipment and Void and nothing else - so a
           collection is always asked for ALONGSIDE a parcel. "Book collection"
           therefore means: the next parcel you book also asks the courier to
           come and get it.

           It clears itself once a booking has carried it, because the mistake
           that costs money here is asking five times in a morning and being
           charged for five pickups. */
        let collectionForRun = null;
        /* What each arrangement is CALLED where you choose it, and what it SAYS
           at the dispatch desk once a courier is picked. Two different jobs:
           one is a menu entry, the other is a statement of what will happen. */
        /* World Options hands back a collection reference as a date, a time and
           a number glued together with literal markup:
             28/08/2026<br/>12:00:00<br/>PRG260828150481
           Printed straight it puts "<br/>" on a dispatch screen, which is what
           it was doing. The server parses it now; this is the fallback for a
           record stored before that, and for anything unexpected. */
        function collRefText(raw) {
            const parts = String(raw == null ? '' : raw)
                .split(/<\s*br\s*\/?\s*>|[\r\n]+/)
                .map(p => p.replace(/<[^>]*>/g, ' ').trim())
                .filter(Boolean);
            if (!parts.length) return '';
            const ref = parts.find(p => !/^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$/.test(p)
                                     && !/^\d{1,2}:\d{2}(:\d{2})?$/.test(p)) || parts[parts.length - 1];
            const when = parts.filter(p => p !== ref).join(' ');
            return when ? (ref + ' (' + when + ')') : ref;
        }
        const COLL_MSG = {
            'I_Have_Daily_Collection': 'Daily collection scheduled',
            'I_Already_Have_Collection_Scheduled': 'A collection is already booked',
            'I_Need_To_Book_A_Collection': 'Book a collection for this shipment',
            'I_Need_To_Book_A_Collection_For_Next_Day': 'Book a collection for tomorrow',
            'I_Am_Going_To_Drop_Off_My_Packages': 'You are dropping this one off',
        };
        const DP_COLL_LABELS = {
            'I_Need_To_Book_A_Collection': 'Book a collection each time',
            'I_Need_To_Book_A_Collection_For_Next_Day': 'Book a collection for the next day',
            'I_Have_Daily_Collection': 'They collect daily',
            'I_Already_Have_Collection_Scheduled': 'A collection is already scheduled',
            'I_Am_Going_To_Drop_Off_My_Packages': 'We drop off with them',
        };
        const COLLECTION_LABELS = {
            'I_Need_To_Book_A_Collection': 'Book a collection today',
            'I_Need_To_Book_A_Collection_For_Next_Day': 'Book a collection for tomorrow',
            'I_Have_Daily_Collection': 'We have a daily collection',
            'I_Already_Have_Collection_Scheduled': 'A collection is already booked',
            'I_Am_Going_To_Drop_Off_My_Packages': 'We are dropping these off',
        };
        function collectionSummary() {
            return collectionForRun ? (COLLECTION_LABELS[collectionForRun] || collectionForRun) : '';
        }
        async function openBookCollection() {
            const body = el('div');
            /* The gap stays as the line; the rest is its info button (copy
               plan, Other dialogs #7). */
            const ch = el('p', 'field-help', 'Collections booked in their portal do not show.');
            ch.append(infoButton('About collections', { title: 'Collections', body:
                'What is coming today, and from whom, by World Options\u2019 own collection '
                + 'reference from the booking. Their service cannot be asked what is scheduled, so '
                + 'a collection booked in their portal rather than here will not show.' }));
            body.append(ch);
            const host = el('div', 'coll-host'); body.append(host);
            host.append(el('div', 'empty', 'Loading\u2026'));
            const dlg = uiConfirm(body, { title: 'Collections', okText: 'Done', hideCancel: true });
            let data = null;
            try { data = await api('/api/dispatch/collections', {}); }
            catch (e) { host.innerHTML = ''; host.append(errBubble(e.message || 'Could not read collections')); await dlg; return; }
            const paint = () => {
                host.innerHTML = '';
                const coming = (data.rows || []).filter(r => r.scheduled);
                const standing = (data.rows || []).filter(r => !r.scheduled && r.standing);
                const willBook = (data.rows || []).filter(r => !r.scheduled && !r.standing && r.configured);
                const section = (title, rows, render) => {
                    if (!rows.length) return;
                    host.append(el('div', 'section-title', title));
                    const list = el('div');
                    rows.forEach(r => list.append(render(r)));
                    host.append(list);
                };
                section('Booked for today', coming, r => {
                    const row = el('div', 'coll-row');
                    const top = el('div', 'coll-row-top');
                    top.append(el('span', 'coll-row-name', r.label));
                    if (r.service && r.service !== r.label) top.append(el('span', 'coll-row-sub', r.service));
                    top.append(el('span', 'lbl-chip made', 'Collection booked'));
                    row.append(top);
                    const sub = [];
                    /* World Options' own reference, off the booking reply. It is
                       the courier's answer rather than this app's inference, and
                       it is what to quote them on the phone. */
                    if (r.ref) sub.push('Collection ' + r.ref);
                    if (r.ref_date || r.ref_time) sub.push([r.ref_date, r.ref_time].filter(Boolean).join(' '));
                    if (r.order) sub.push('booked with ' + r.order);
                    if (sub.length) row.append(el('div', 'coll-row-sub', sub.join(' \u00b7 ')));
                    /* The van has been and gone and another parcel needs one:
                       clearing lets the next booking ask again. */
                    const clr = el('button', 'linkish', 'The van has been, book another');
                    clr.onclick = async () => {
                        if (!await uiConfirm('Clear the record of ' + r.label + '\u2019s collection today? '
                            + 'The next parcel booked with them will ask for a new one, which is a '
                            + 'second pickup charge.', { title: 'Clear collection', okText: 'Clear it' })) return;
                        try { await api('/api/dispatch/collections', { op: 'clear', carrier: r.carrier });
                              data = await api('/api/dispatch/collections', {}); paint(); toastOk('Cleared.'); }
                        catch (e) { toastError(e.message); }
                    };
                    row.append(clr);
                    return row;
                });
                section('They collect anyway', standing, r => {
                    const row = el('div', 'coll-row');
                    const top = el('div', 'coll-row-top');
                    top.append(el('span', 'coll-row-name', r.label));
                    top.append(el('span', 'lbl-chip note', r.arrangement_label));
                    row.append(top);
                    return row;
                });
                section('Will be booked with the next parcel', willBook, r => {
                    const row = el('div', 'coll-row');
                    const top = el('div', 'coll-row-top');
                    top.append(el('span', 'coll-row-name', r.label));
                    top.append(el('span', 'lbl-chip warn', r.arrangement_label));
                    row.append(top);
                    return row;
                });
                if (!coming.length && !standing.length && !willBook.length) {
                    host.append(el('div', 'empty',
                        'No courier has a collection rule yet. Set them under Settings, Shipping, '
                        + 'Collections by courier, and this shows what is coming each day.'));
                }
                host.append(el('p', 'field-help', data.note || ''));
            };
            paint();
            await dlg;
        }
        async function openCustomShip() {
            const overlay = el('div', 'modal-overlay show');
            const modal = el('div', 'modal disp-modal');
            const head = el('div', 'modal-head');
            head.append(el('h3', null, 'New shipment'));
            const x = el('button', 'icon-btn'); x.innerHTML = I.x; x.title = 'Close'; head.append(x);
            const body = el('div', 'modal-body');
            modal.append(head, body); overlay.append(modal); document.body.append(overlay);
            const prev = document.activeElement;
            let booking = false;
            const close = () => {
                if (booking) { addToast('The courier booking is still going through. Please wait.'); return; }
                overlay.remove(); if (prev && prev.focus) prev.focus();
            };
            x.onclick = close;   // the X is the only way out: a misclick must not wipe a filled form
            x.focus();

            const shipId = 'cs' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
            // Declared up here, not beside the quote UI: building the parcel row
            // calls staleQuote() while the modal is still assembling, and a `let`
            // read before its own line throws rather than reading undefined.
            let quote = null, chosen = null;
            let cfg = {};
            try { cfg = await ensureShippingCfg(); }
            catch (e) { body.append(el('div', 'msg error', e.message || 'Could not load shipping settings')); return; }

            // ---- paste ----
            body.append(el('div', 'disp-subhead', 'Paste the address'));
            const paste = document.createElement('textarea');
            paste.className = 'disp-paste'; paste.rows = 4;
            paste.placeholder = 'Paste the address from an email. It will be split into the fields below.';
            body.append(paste);
            const pasteNote = el('div', 'sub'); body.append(pasteNote);

            // ---- address fields ----
            const addrGrid = el('div', 'disp-addr-grid');
            const addr = {};
            ADDR_FIELDS.forEach(([key, label, help]) => {
                const wrap = el('label', 'disp-addr-f');
                wrap.append(el('span', 'disp-addr-lab', label));
                const inp = document.createElement('input');
                /* The right keyboard on touch and the right autofill: email and
                   phone are not plain text, and postcodes are not words. */
                inp.type = key === 'email' ? 'email' : key === 'phone' ? 'tel' : 'text';
                if (key === 'postcode' || key === 'country') inp.spellcheck = false;
                inp.className = 'disp-text'; inp.placeholder = help || '';
                inp.oninput = staleQuote;
                addr[key] = inp; wrap.append(inp); addrGrid.append(wrap);
            });
            body.append(addrGrid);

            function fillAddress(a) {
                ADDR_FIELDS.forEach(([k]) => { addr[k].value = (a && a[k]) || ''; });
                staleQuote();
            }
            function readAddress() {
                const out = {};
                ADDR_FIELDS.forEach(([k]) => { out[k] = addr[k].value.trim(); });
                return out;
            }
            let parsing = false;
            async function parsePaste() {
                const text = paste.value.trim();
                if (!text || parsing) return;
                parsing = true;
                pasteNote.textContent = 'Reading the address…';
                try {
                    const r = await api('/api/dispatch/parse-address', { text: text });
                    fillAddress(r.address);
                    pasteNote.textContent = r.note
                        || (r.source === 'ai' ? 'Read with AI. Check every field.' : 'Check every field before booking.');
                } catch (e) { pasteNote.textContent = e.message || 'Could not read that address.'; }
                parsing = false;
            }
            // Reading it as it lands is the whole point of pasting.
            paste.addEventListener('paste', () => setTimeout(parsePaste, 0));
            paste.addEventListener('blur', parsePaste);

            // ---- what is in the parcel ----
            body.append(el('div', 'disp-subhead', 'What is in it'));
            const meta = el('div', 'disp-addr-grid');
            function metaField(label, help, type) {
                const wrap = el('label', 'disp-addr-f');
                wrap.append(el('span', 'disp-addr-lab', label));
                const inp = document.createElement('input');
                inp.type = type || 'text'; inp.className = 'disp-text'; inp.placeholder = help || '';
                if (type === 'number') { inp.min = '0'; inp.step = '1'; }
                inp.oninput = staleQuote;
                wrap.append(inp); meta.append(wrap); return inp;
            }
            const refIn = metaField('Your reference', 'Shows on the World Options invoice');
            const contentsIn = metaField('Contents', 'e.g. Replacement gobo');
            const valueIn = metaField('Value (£)', 'What it is worth', 'number');
            body.append(meta);
            body.append(el('p', 'field-help', 'Declared to the courier. A zero value cannot be insured.'));

            // ---- boxes ----
            body.append(el('div', 'disp-subhead', 'Parcel'));
            const presets = (cfg.boxes || []).slice();
            const boxHost = el('div'); body.append(boxHost);
            const boxRows = [];
            function addBoxRow() {
                const rowb = el('div', 'disp-boxrow');
                const sel = document.createElement('select'); sel.className = 'disp-sel'; sel.setAttribute('aria-label', 'Box preset');
                sel.append(new Option('Custom size', ''));
                presets.forEach(b => sel.append(new Option(b.name || 'Box', b.id)));
                const ins = {};
                ['width', 'length', 'depth', 'weight'].forEach(k => {
                    const i = document.createElement('input');
                    i.type = 'number'; i.min = '0'; i.step = '0.1'; i.className = 'disp-num';
                    i.placeholder = k === 'weight' ? 'kg' : k.slice(0, 1).toUpperCase() + k.slice(1) + ' cm';
                    i.oninput = staleQuote; ins[k] = i;
                });
                const rm = el('button', 'icon-btn'); rm.innerHTML = I.x; rm.title = 'Remove this parcel';
                const row = { el: rowb, ins };
                rm.onclick = () => { const i = boxRows.indexOf(row); if (i >= 0) boxRows.splice(i, 1); rowb.remove(); staleQuote(); };
                sel.onchange = () => {
                    const b = presets.find(p => p.id === sel.value);
                    if (b) { ins.width.value = b.width; ins.length.value = b.length; ins.depth.value = b.depth; ins.weight.value = b.weight || ''; }
                    staleQuote();
                };
                rowb.append(sel, ins.width, ins.length, ins.depth, ins.weight, rm);
                boxRows.push(row); boxHost.append(rowb);
                if (presets.length) { sel.value = presets[0].id; sel.onchange(); }
            }
            addBoxRow();
            const addBoxBtn = el('button', 'btn disp-addbox');
            addBoxBtn.append(ico(I.plus), document.createTextNode('Add a box'));
            addBoxBtn.onclick = () => { addBoxRow(); staleQuote(); };
            body.append(addBoxBtn);
            body.append(el('p', 'field-help', 'Weigh the packed box: couriers re-weigh and bill it.'));

            // ---- insurance ----
            const insWrap = el('label', 'disp-insure');
            const insCb = document.createElement('input'); insCb.type = 'checkbox';
            const insAmt = document.createElement('input');
            insAmt.type = 'number'; insAmt.min = '0'; insAmt.step = '1'; insAmt.className = 'disp-num';
            insAmt.disabled = true;
            insCb.onchange = () => { insAmt.disabled = !insCb.checked; if (insCb.checked && !insAmt.value) insAmt.value = valueIn.value; staleQuote(); };
            insAmt.oninput = staleQuote;
            insWrap.append(insCb, el('span', null, 'Insure this shipment for £'), insAmt);
            body.append(insWrap);

            function collectBoxes() {
                const out = [];
                for (const r of boxRows) {
                    const b = { width: parseFloat(r.ins.width.value), length: parseFloat(r.ins.length.value),
                                depth: parseFloat(r.ins.depth.value), weight: parseFloat(r.ins.weight.value) };
                    if (!(b.width > 0 && b.length > 0 && b.depth > 0 && b.weight > 0)) return null;
                    out.push(b);
                }
                return out.length ? out : null;
            }

            // ---- quotes ----
            const quoteBtn = el('button', 'btn btn-primary disp-quote');
            quoteBtn.append(ico(I.truck), document.createTextNode('Get courier quotes'));
            const quoteWrap = el('div'); quoteWrap.style.marginTop = 'var(--sp-3)';
            body.append(quoteBtn, quoteWrap);

            function staleQuote() {
                // Anything that changes the parcel or the address invalidates the
                // price: booking against a stale quote books the wrong thing.
                if (!quote) return;
                quote = null; chosen = null; quoteWrap.innerHTML = '';
                quoteWrap.append(el('div', 'sub', 'The parcel changed. Get the quotes again.'));
            }

            quoteBtn.onclick = async () => {
                const boxes = collectBoxes();
                if (!boxes) { toastError('Fill in the parcel size and weight first.'); return; }
                const a = readAddress();
                if (!a.street || !a.city || !a.postcode || !a.country) {
                    toastError('The address needs at least a street, a town, a postcode and a country.');
                    return;
                }
                // A country name is not a country code, and half a name is a
                // different country: IS is Iceland, not the Isle of Man.
                if (!/^[A-Za-z]{2}$/.test(a.country)) {
                    toastError('Country must be the 2-letter code, for example GB, IE, US or DE.');
                    addr.country.focus();
                    return;
                }
                quoteBtn.disabled = true; quoteWrap.innerHTML = '';
                const t = el('div', 'thinking'); t.append(loader(), el('span', null, 'Asking World Options…'));
                quoteWrap.append(t);
                try {
                    quote = await api('/api/custom/quote', {
                        address: a, boxes: boxes,
                        insurance: insCb.checked ? parseFloat(insAmt.value) || 0 : 0,
                        declared: parseFloat(valueIn.value) || 0,
                    });
                    renderOpts();
                } catch (e) {
                    quoteWrap.innerHTML = '';
                    quoteWrap.append(el('div', 'msg error', e.message || 'Could not get quotes'));
                }
                quoteBtn.disabled = false;
            };

            const confirmWrap = el('div'); body.append(confirmWrap);

            function renderOpts() {
                quoteWrap.innerHTML = ''; confirmWrap.innerHTML = '';
                const opts = (quote && quote.options) || [];
                if (!opts.length) { quoteWrap.append(el('div', 'empty', 'No courier options came back for this parcel and address.')); return; }
                if (quote.insurance) quoteWrap.append(el('div', 'sub', 'Prices include insurance cover for ' + fmtPrice(parseFloat(quote.insurance), quote.currency) + '.'));
                if (quote.international) quoteWrap.append(customsCard());
                quoteWrap.append(el('div', 'disp-subhead', opts.length + ' option' + (opts.length === 1 ? '' : 's') + ' · cheapest first'));
                const list = el('div', 'disp-opts');
                const cheapest = Math.min.apply(null, opts.map(o => Number(o.amount) || Infinity));
                opts.forEach((op, i) => {
                    const rowl = el('label', 'disp-opt');
                    const rb = document.createElement('input');
                    rb.type = 'radio'; rb.name = 'cust-opt'; rb.value = i;
                    rb.onchange = () => {
                        chosen = op;
                        list.querySelectorAll('.disp-opt').forEach(e => e.classList.remove('on'));
                        rowl.classList.add('on'); renderConfirm();
                    };
                    rowl.append(rb);
                    const top = el('div', 'disp-opt-top');
                    const known = !!op.carrier_label;
                    top.append(el('span', 'disp-opt-prov' + (known ? '' : ' disp-opt-unknown'),
                        known ? op.carrier_label : 'Carrier not named'));
                    top.append(el('span', 'disp-opt-carrier', op.service_name || (known ? '' : 'Courier service')));
                    if (Number(op.amount) === cheapest) top.append(el('span', 'lbl-chip made', 'Cheapest'));
                    /* How THIS courier collects, from the per-courier setting.
                       A daily UPS collection is a different fact from DHL
                       having to be asked each time, and the desk should not
                       have to remember which is which. */
                    if (op.collection_message) {
                        const needsBooking = String(op.collection_option || '').indexOf('Need_To_Book') >= 0;
                        const cc = el('span', 'lbl-chip ' + (needsBooking ? 'warn' : 'note'),
                                      op.collection_message);
                        cc.title = needsBooking
                            ? 'Booking this also asks ' + (op.carrier_label || 'the courier')
                              + ' to collect. Set it under Settings, Shipping, Collections by courier.'
                            : (op.carrier_label || 'This courier') + ' already collects, so no pickup is '
                              + 'requested. Set it under Settings, Shipping, Collections by courier.';
                        top.append(cc);
                    }
                    if (op.shops && op.shops.length) top.append(el('span', 'lbl-chip note', 'Drop-off'));
                    if (op.no_signature) top.append(el('span', 'lbl-chip note', 'NO SIGNATURE'));
                    if (op.delivery_dropoff) top.append(el('span', 'lbl-chip warn', 'Collect from shop'));
                    rowl.append(top);
                    const priceCell = el('div', 'disp-opt-price');
                    priceCell.append(el('span', 'p-inc', fmtPrice(op.amount, op.currency)));
                    if (op.amount_ex_vat != null && op.vat) priceCell.append(el('span', 'p-ex', fmtPrice(op.amount_ex_vat, op.currency) + ' ex VAT'));
                    rowl.append(priceCell);
                    const when = el('div', 'disp-opt-when');
                    if (op.delivery_date) {
                        when.append(el('span', 'd', op.delivery_date));
                        if (op.delivery_time) when.append(el('span', 't', ' ' + op.delivery_time));
                    } else { when.append(el('span', 't', 'Delivery date not quoted')); }
                    rowl.append(when);
                    list.append(rowl);
                });
                quoteWrap.append(list);
            }

            /* Outside the UK the parcel needs a customs declaration. There are no
               line items behind this shipment, so unlike an order nothing can be
               prefilled: it is typed once, here, and the booking is refused
               without it rather than going out with an empty dossier. */
            let customsRows = [], receiverTax = null, receiverCo = null;
            function customsCard() {
                const card = el('div', 'disp-customs');
                card.append(el('div', 'disp-subhead', 'Customs declaration'));
                card.append(el('p', 'field-help', 'Outside the UK: list what is in the parcel.'));
                if (!quote.has_eori) {
                    card.append(el('div', 'msg error', 'Add your EORI number under Settings, Shipping. '
                        + 'International shipments cannot be booked without it.'));
                }
                const host = el('div');
                customsRows = [];
                function addLine(pref) {
                    const row = el('div', 'disp-boxrow');
                    const mk = (ph, cls, val) => {
                        const i = document.createElement('input');
                        i.type = 'text'; i.className = cls || 'disp-text'; i.placeholder = ph;
                        if (val) i.value = val;
                        return i;
                    };
                    const desc = mk('What it is', 'disp-text');
                    const qty = mk('Qty', 'disp-num'); qty.type = 'number'; qty.min = '1'; qty.value = '1';
                    const price = mk('Unit £', 'disp-num'); price.type = 'number'; price.min = '0'; price.step = '0.01';
                    const hs = mk('HS code', 'disp-num', quote.default_hs_code || '');
                    const orig = mk('Origin', 'disp-num', 'GB');
                    const rm = el('button', 'icon-btn'); rm.innerHTML = I.x; rm.title = 'Remove this line';
                    const entry = { desc: desc, qty: qty, price: price, hs: hs, orig: orig };
                    rm.onclick = () => {
                        const i = customsRows.indexOf(entry);
                        if (i >= 0) customsRows.splice(i, 1);
                        row.remove();
                    };
                    row.append(desc, qty, price, hs, orig, rm);
                    customsRows.push(entry); host.append(row);
                    if (pref && pref.desc) { desc.value = pref.desc; price.value = pref.price || ''; }
                }
                card.append(host);
                // Seed the first line from what they already typed: for a one-item
                // parcel that is the whole declaration.
                addLine({ desc: contentsIn.value.trim(), price: valueIn.value });
                const addBtn = el('button', 'btn disp-addbox');
                addBtn.append(ico(I.plus), document.createTextNode('Add a line'));
                addBtn.onclick = () => addLine();
                card.append(addBtn);
                const ids = el('div', 'disp-addr-grid');
                function idField(label, help) {
                    const w = el('label', 'disp-addr-f');
                    w.append(el('span', 'disp-addr-lab', label));
                    const i = document.createElement('input');
                    i.type = 'text'; i.className = 'disp-text'; i.placeholder = help || '';
                    w.append(i); ids.append(w); return i;
                }
                receiverTax = idField('Recipient tax or VAT number', 'Optional, speeds up clearance');
                receiverCo = idField('Recipient company number', 'Optional');
                card.append(ids);
                return card;
            }
            function collectCustoms() {
                if (!quote || !quote.international) return null;
                const lines = [];
                customsRows.forEach(r => {
                    const desc = r.desc.value.trim();
                    const qty = parseInt(r.qty.value, 10);
                    const price = parseFloat(r.price.value);
                    if (!desc || !(qty > 0) || !(price >= 0)) return;
                    lines.push({ description: desc, quantity: qty, unit_price: price,
                                 hs: r.hs.value.trim(), country: (r.orig.value.trim() || 'GB').toUpperCase() });
                });
                return { lines: lines,
                         receiver_tax_id: receiverTax ? receiverTax.value.trim() : '',
                         receiver_company_number: receiverCo ? receiverCo.value.trim() : '' };
            }
            function customsGap() {
                /* The same rule as the order card: a described line with no
                   quantity or unit value is named and stops the booking,
                   rather than vanishing from the declaration in silence. */
                if (!quote || !quote.international) return '';
                for (let i = 0; i < customsRows.length; i++) {
                    const r = customsRows[i], desc = r.desc.value.trim();
                    if (!desc) continue;
                    const qty = parseInt(r.qty.value, 10), price = parseFloat(r.price.value);
                    if (!(qty > 0)) return 'Customs line ' + (i + 1) + ' (' + desc + ') needs a quantity.';
                    if (isNaN(price) || price < 0) return 'Customs line ' + (i + 1) + ' (' + desc + ') needs a unit value. Enter 0 only if it really is worth nothing.';
                }
                return '';
            }

            function renderConfirm() {
                confirmWrap.innerHTML = '';
                if (!chosen) return;
                const bar = el('div', 'disp-actions');
                const bk = el('button', 'btn btn-primary');
                bk.append(ico(I.truck), document.createTextNode('Book ' + fmtPrice(chosen.amount, chosen.currency)));
                bk.onclick = async () => {
                    const boxes = collectBoxes();
                    if (!boxes) { toastError('Fill in the parcel size and weight first.'); return; }
                    const gap = customsGap();
                    if (gap) { toastError(gap); return; }
                    /* Disabled BEFORE the question: a double click here opened
                       two dialogs, and answering both booked two labels. */
                    bk.disabled = true;
                    if (!await uiConfirm('Book this courier for ' + fmtPrice(chosen.amount, chosen.currency)
                        + '? Your World Options account is charged.',
                        { title: 'Book the courier', okText: 'Book it' })) { bk.disabled = false; return; }
                    booking = true;
                    let sure = false;
                    try {
                        for (;;) {
                            try {
                        const r = await api('/api/custom/book', {
                            confirm_unknown: sure,
                            id: shipId, option: chosen, address: readAddress(), boxes: boxes,
                            insurance: insCb.checked ? parseFloat(insAmt.value) || 0 : 0,
                            declared: parseFloat(valueIn.value) || 0,
                            reference: refIn.value.trim(), contents: contentsIn.value.trim(),
                            signature: chosen.signature_type || '',
                            customs: collectCustoms(),
                        });
                        booking = false;
                        renderBookedSafe(r);
                        break;
                            } catch (e) {
                                if (!sure && /outcome was never recorded/.test(e.message || '')) {
                                    if (!await uiConfirm(e.message + '\n\nOnly if there is no such booking in World Options, book it now.', { title: 'A booking may already exist', okText: 'I checked: book it', danger: true })) { booking = false; bk.disabled = false; return; }
                                    sure = true; continue;
                                }
                                throw e;
                            }
                        }
                    } catch (e) {
                        booking = false;
                        const msg = String(e.message || 'The booking failed');
                        /* The same rule as the order panel: an outcome nobody
                           knows may already be a booked and charged label, so
                           Book stays held rather than offering a second one. */
                        if (!(e.noReply || BOOKING_UNKNOWN.test(msg))) bk.disabled = false;
                        confirmWrap.append(el('div', 'msg error', msg));
                    }
                };
                bar.append(bk); confirmWrap.append(bar);
            }

            /* Built off screen and swapped in once, for the same reason the
               order panel is: the account has already been charged by the time
               this runs, and a half-drawn panel would take the tracking number
               down with it. */
            function renderBooked(r) {
                const out = el('div');
                const d = r.dispatch || {};
                const h = el('div', 'disp-result-head');
                h.append(ico(I.check), el('span', null, 'Booked with '
                    + (d.carrier_label || d.carrier_name || 'the courier')));
                out.append(h);
                const tb = el('div', 'disp-track');
                tb.append(el('span', null, 'Tracking '), el('b', null, d.tracking_number || ''));
                out.append(tb);
                if (d.amount != null) out.append(el('div', 'sub', 'Charged ' + fmtPrice(d.amount, d.currency)));
                if (d.customer) out.append(el('div', 'sub', 'To ' + d.customer));
                if (r.contact_note) out.append(el('div', 'sub', r.contact_note));
                if (r.note) out.append(el('div', 'msg error', r.note));
                const printed = printLabelImages((r.shipment && r.shipment.labels) || []);
                if (!printed) labelButtons(out, (r.shipment || {}).labels, 'Print label');
                const bar = el('div', 'disp-actions');
                const rp = el('button', 'btn btn-primary');
                rp.append(ico(I.printer), document.createTextNode('Reprint label'));
                rp.onclick = () => reprintCustom(r.id || shipId, body, rp);
                bar.append(rp);
                const done = el('button', 'btn', 'Done'); done.onclick = close;
                bar.append(done); out.append(bar);
                body.innerHTML = '';
                body.append(out);
            }

            function renderBookedSafe(r) {
                try { renderBooked(r); return; }
                catch (err) {
                    const tn = (((r || {}).dispatch) || {}).tracking_number || '';
                    try {
                        body.innerHTML = '';
                        const h = el('div', 'disp-result-head');
                        h.append(ico(I.check), el('span', null, 'Booked and charged'));
                        body.append(h);
                        const tb = el('div', 'disp-track');
                        tb.append(el('span', null, 'Tracking '), el('b', null, tn || '(none returned)'));
                        body.append(tb);
                        body.append(el('div', 'msg error',
                            'The courier is booked, but this window could not be drawn: '
                            + String((err && err.message) || err)
                            + '. Write the tracking number down, then close this and press '
                            + 'New shipment again: it is listed under Already booked, with Reprint.'));
                        const done = el('button', 'btn', 'Done'); done.onclick = close; body.append(done);
                    } catch (e2) {
                        body.textContent = 'Booked and charged. Tracking: ' + (tn || 'unknown')
                            + '. Close this and press New shipment again to reprint.';
                    }
                }
            }

            // ---- already booked, from this desk or an earlier one ----
            const recentWrap = el('div'); body.append(recentWrap);
            (async function loadRecent() {
                try {
                    const r = await api('/api/custom/list', {});
                    const rows = (r.shipments || []).filter(s => !s.canceled).slice(0, 8);
                    if (!rows.length) return;
                    recentWrap.append(el('div', 'disp-subhead', 'Already booked'));
                    rows.forEach(s => {
                        const row = el('div', 'disp-recent');
                        const left = el('div');
                        left.append(el('div', 'disp-recent-t', (s.reference || 'Shipment') + ' · ' + (s.customer || '')));
                        left.append(el('div', 'sub', (s.carrier || '') + ' ' + (s.tracking || '')
                            + (s.at ? ' · ' + fmtDate(s.at) : '')));
                        row.append(left);
                        const rp = el('button', 'btn');
                        rp.append(ico(I.printer), document.createTextNode('Reprint'));
                        rp.onclick = () => reprintCustom(s.id, body, rp);
                        row.append(rp);
                        recentWrap.append(row);
                    });
                } catch (e) { /* the list is a convenience, never a blocker */ }
            })();

            async function reprintCustom(id, host, btn) {
                btn.disabled = true;
                try {
                    const r = await api('/api/dispatch/label', { id: id });
                    if (!printLabelImages(r.labels || [])) labelButtons(host, r.labels, 'Print label');
                } catch (e) { toastError(e.message || 'Could not fetch the label'); }
                btn.disabled = false;
            }
        }

        /* The four answers the EU database can give about a customer's EORI,
           drawn in one place so they cannot drift apart. The distinction that
           matters is the last one: "unknown" means the service did not answer,
           which is NOT the same as the number being bad. Drawing a timeout in
           the red "not valid" line is how a good customer gets told their
           number is wrong and an export booking is refused over nothing. */
        function eoriPaint(out, r) {
            out.innerHTML = '';
            if (r.status === 'valid') {
                out.className = 'eori-line ok';
                const who = [r.name, r.address].filter(Boolean).join(', ');
                out.textContent = 'Valid' + (who ? ': ' + who : '')
                    + (r.cached ? ' (from an earlier check)' : ' (checked just now)');
            } else if (r.status === 'invalid') {
                out.className = 'eori-line bad';
                out.textContent = 'Not valid according to the EU database.';
            } else if (r.status === 'not_covered') {
                /* A GB number is not held by the EU database at all, so this is
                   a signpost rather than a verdict. */
                out.className = 'eori-line muted';
                out.append(document.createTextNode((r.reason || '') + ' '));
                const a = el('a', null, 'Check GB numbers at gov.uk');
                a.href = 'https://www.tax.service.gov.uk/check-eori-number';
                a.target = '_blank';
                /* The settings form behind this is usually half filled in, so
                   the checker opens in its own tab, and noopener keeps that tab
                   from reaching back into this one. */
                a.rel = 'noopener';
                out.append(a);
            } else {
                out.className = 'eori-line muted';
                out.textContent = 'Could not check: ' + (r.reason || 'the EU service did not answer.')
                    + ' Try again in a minute.';
            }
        }
        async function eoriRun(inp, btn, out) {
            const number = inp.value.trim();
            if (!number) {
                eoriPaint(out, { status: 'unknown', reason: 'no number was entered.' });
                return;
            }
            btn.disabled = true;
            out.className = 'eori-line muted';
            out.textContent = 'Checking…';
            try {
                eoriPaint(out, await api('/api/eori/check', { number: number }));
            } catch (e) {
                /* Same muted line, same wording: from here a refused request and
                   a silent service are the same event, and neither says the
                   number is bad. The message is punctuated before it goes in,
                   because the browser's own "Failed to fetch" has no full stop
                   and ran straight into the sentence after it. */
                const why = (e.message || 'the check could not be made').trim();
                eoriPaint(out, { status: 'unknown',
                                 reason: /[.!?]$/.test(why) ? why : why + '.' });
            } finally {
                /* In a finally, not after the try: a throw used to leave the
                   button dead, so the checker worked exactly once. */
                btn.disabled = false;
            }
        }

        async function openShippingSettings() {
            const overlay = el('div', 'modal-overlay show');
            const modal = el('div', 'modal disp-modal');
            const head = el('div', 'modal-head');
            head.append(el('h3', null, 'Shipping settings'));
            const x = el('button', 'icon-btn'); x.innerHTML = I.x; x.title = 'Close'; head.append(x);
            const body = el('div', 'modal-body');
            modal.append(head, body); overlay.append(modal); document.body.append(overlay);
            const prev = document.activeElement;
            const close = () => { overlay.remove(); document.removeEventListener('keydown', esc); if (prev && prev.focus) prev.focus(); };
            function esc(e) { /* Escape deliberately does not close either: X only. */ }
            x.onclick = close;
            // Backdrop clicks never close: a misclick must not wipe a filled form.
            // The X is the only way out (user rule).
            document.addEventListener('keydown', esc);

            const load = el('div', 'thinking'); load.append(loader(), el('span', null, 'Loading…')); body.append(load);
            let cfg;
            try { cfg = await ensureShippingCfg(true); }
            catch (e) { body.innerHTML = ''; body.append(errBubble(e.message || 'Could not load')); return; }
            body.innerHTML = '';

            // Connection (World Options SOAP web service)
            body.append(el('div', 'section-title', 'World Options connection'));
            const fromEnv = !!cfg.creds_from_env;
            const cstat = el('div', 'setting-sub');
            cstat.textContent = cfg.connected
                ? ('Connected' + (cfg.meter_last4 ? ' (meter ending ' + cfg.meter_last4 + ')' : ''))
                : 'Not connected yet. Enter the details World Options gave you.';
            body.append(cstat);
            body.append(el('p', 'field-help', 'The Meter Number is required; Key and Password optional.'));
            const credIn = {};
            [['meter_number', 'Meter Number', 'text', cfg.connected ? 'Saved' : 'e.g. 1234567'],
             ['key', 'Key', 'password', cfg.has_key ? 'Saved (enter to replace)' : 'Web service key'],
             ['password', 'Password', 'password', cfg.has_password ? 'Saved (enter to replace)' : 'Web service password']
            ].forEach(([k, lab, type, ph]) => {
                const inp = document.createElement('input');
                inp.type = type; inp.className = 'pf-input'; inp.autocomplete = 'off'; inp.placeholder = fromEnv ? 'Set on the server' : ph;
                if (fromEnv) inp.disabled = true;
                body.append(el('label', 'field-label', lab), inp);
                credIn[k] = inp;
            });
            const pluginRow = el('label', 'disp-fld'); pluginRow.style.marginTop = 'var(--sp-2)';
            pluginRow.append(el('span', 'disp-fld-lab', 'Plugin code (leave as Web_Service unless told otherwise)'));
            const pluginIn = el('select', 'psel'); pluginIn.setAttribute('aria-label', 'Plugin code');
            (cfg.plugin_codes || ['Web_Service']).forEach(v => {
                const op = el('option', null, v); op.value = v;
                if (v === (cfg.plugin_code || 'Web_Service')) op.selected = true;
                pluginIn.append(op);
            });
            pluginRow.append(pluginIn); body.append(pluginRow);
            const testBtn = el('button', 'btn'); testBtn.style.marginTop = 'var(--sp-2-5)'; testBtn.append(ico(I.check), document.createTextNode('Save & test connection'));
            const testOut = el('span', 'setting-sub'); testOut.style.marginLeft = 'var(--sp-2-5)';
            testBtn.onclick = async () => {
                testBtn.disabled = true; testOut.textContent = 'Testing…';
                try {
                    const payload = { op: 'set', plugin_code: pluginIn.value.trim() || 'Web_Service' };
                    if (!fromEnv) {
                        if (credIn.meter_number.value.trim()) payload.meter_number = credIn.meter_number.value.trim();
                        if (credIn.key.value.trim()) payload.key = credIn.key.value.trim();
                        if (credIn.password.value.trim()) payload.password = credIn.password.value.trim();
                    }
                    await api('/api/shipping/config', payload);
                    credIn.key.value = ''; credIn.password.value = '';
                    const r = await api('/api/shipping/validate', {});
                    if (r.ok) { testOut.textContent = 'Connected · ' + (r.message || 'credentials accepted'); cstat.textContent = 'Connected'; shippingCfg = null; }
                    else testOut.textContent = r.error || 'Could not connect.';
                } catch (e) { testOut.textContent = e.message || 'Could not connect.'; }
                testBtn.disabled = false;
            };
            const testRow = el('div'); testRow.append(testBtn, testOut); body.append(testRow);

            // Origin address
            body.append(el('div', 'section-title', 'Dispatch (origin) address'));
            body.append(el('p', 'field-help', 'Left blank, your Shopify store address is used.'));
            const o = cfg.origin || {};
            const of = {};
            const originGrid = el('div', 'disp-origin');
            [['company', 'Company'], ['name', 'Contact name'], ['street', 'Street'], ['city', 'City'], ['state', 'County / state'], ['postcode', 'Postcode'], ['country', 'Country (2-letter, e.g. GB)'], ['phone', 'Phone'], ['email', 'Email']].forEach(([k, lab]) => {
                const w = el('label', 'disp-fld');
                w.append(el('span', 'disp-fld-lab', lab));
                const inp = document.createElement('input'); inp.type = 'text'; inp.className = 'disp-num'; inp.value = o[k] || '';
                w.append(inp); of[k] = inp; originGrid.append(w);
            });
            body.append(originGrid);

            // Notify toggle + collection window
            body.append(el('div', 'section-title', 'Options'));
            const notifyWrap = el('label', 'disp-notify');
            const notifyCb = document.createElement('input'); notifyCb.type = 'checkbox'; notifyCb.checked = cfg.notify_customer !== false;
            notifyWrap.append(notifyCb, el('span', null, ' Email the customer tracking when an order is dispatched (default)'));
            body.append(notifyWrap);
            body.append(el('p', 'field-help', 'When the courier can collect. Sent with every booking.'));
            const timeGrid = el('div', 'disp-dims'); timeGrid.style.gridTemplateColumns = '1fr 1fr';
            const readyF = el('label', 'disp-fld');
            readyF.append(el('span', 'disp-fld-lab', 'Ready from'));
            const readyIn = document.createElement('input'); readyIn.type = 'time'; readyIn.className = 'disp-num';
            readyIn.value = cfg.ready_time || ''; readyF.append(readyIn);
            const closeF = el('label', 'disp-fld');
            closeF.append(el('span', 'disp-fld-lab', 'Closes at'));
            const closeIn = document.createElement('input'); closeIn.type = 'time'; closeIn.className = 'disp-num';
            closeIn.value = cfg.close_time || ''; closeF.append(closeIn);
            timeGrid.append(readyF, closeF);
            body.append(timeGrid);
            const coF = el('label', 'disp-fld'); coF.style.marginTop = 'var(--sp-2)';
            coF.append(el('span', 'disp-fld-lab', 'Collection arrangement'));
            const coSel = el('select', 'psel');
            const CO_LABELS = {
                'I_Need_To_Book_A_Collection': 'Book a collection for each dispatch',
                'I_Need_To_Book_A_Collection_For_Next_Day': 'Book a collection for the next day',
                'I_Have_Daily_Collection': 'We have a daily collection already',
                'I_Already_Have_Collection_Scheduled': 'A collection is already scheduled',
                'I_Am_Going_To_Drop_Off_My_Packages': 'We drop parcels off ourselves',
            };
            (cfg.collection_options || Object.keys(CO_LABELS)).forEach(k => {
                const opt = el('option', null, CO_LABELS[k] || k); opt.value = k;
                if (k === (cfg.collection_option || 'I_Need_To_Book_A_Collection')) opt.selected = true;
                coSel.append(opt);
            });
            coF.append(coSel); body.append(coF);
            body.append(el('p', 'field-help', 'Tells the courier whether to send a driver for each booking or that pickup is already covered. Picking the wrong one can double-book collections.'));
            /* No switch for pickup-shop services: customers never collect from
               a shop (Cameron, 2026-10-09), so the server never offers them. */
            // Two printers, two stocks. Set once here rather than chosen at every
            // print: the stock in each printer does not change from day to day,
            // and the select beside the print button is only ever a one-off.
            const lpT = el('div', 'section-title', 'Label printers');
            lpT.append(infoButton('About the label printers', { title: 'Label printers', body: 'What each printer is loaded with. '
                + 'Production labels are the gobo labels from the Production Manager; '
                + 'courier labels are the shipping labels that come back from a booking.' }));
            body.append(lpT);
            const sizeIn = {};
            const labelWarn = el('div', 'setting-sub');
            [['label_size_production', 'Production label stock', '4x4'],
             ['label_size_shipping', 'Courier label stock', '4x6']].forEach(([k, lab, fallback]) => {
                const w = el('label', 'disp-fld'); w.style.marginTop = 'var(--sp-1-5)';
                w.append(el('span', 'disp-fld-lab', lab));
                const sel = el('select', 'psel'); sel.setAttribute('aria-label', lab);
                const cur = LABEL_SIZES[cfg[k]] ? cfg[k] : fallback;
                Object.keys(LABEL_SIZES).forEach(key => {
                    const opt = el('option', null, LABEL_SIZES[key].label); opt.value = key;
                    if (key === cur) opt.selected = true;
                    sel.append(opt);
                });
                sel.onchange = paintLabelWarn;
                w.append(sel); body.append(w); sizeIn[k] = sel;
            });
            // A courier label is artwork, not a layout: on stock that is not 4 x 6
            // it is scaled to fit, and a shrunk barcode is one a scanner refuses.
            function paintLabelWarn() {
                const off = sizeIn.label_size_shipping.value !== '4x6';
                labelWarn.textContent = off
                    ? 'Courier artwork is 4 x 6. On other stock it is scaled to fit, '
                      + 'and a shrunk barcode may not scan.'
                    : '';
                labelWarn.style.color = off ? 'var(--warning-text)' : '';
            }
            paintLabelWarn();
            body.append(labelWarn);
            body.append(el('div', 'section-title', 'International (customs)'));
            body.append(el('p', 'field-help', 'Required for exports. Get one at gov.uk.'));
            const intlIn = {};
            [['eori', 'EORI number (e.g. GB123456789000)'], ['vat_number', 'VAT number (optional)'],
             ['default_hs_code', 'Default HS / commodity code (optional, e.g. 70200080)'], ['trade_term', 'Trade term (optional, e.g. DAP)']].forEach(([k, lab]) => {
                const w = el('label', 'disp-fld'); w.style.marginTop = 'var(--sp-1-5)';
                w.append(el('span', 'disp-fld-lab', lab));
                const inp = document.createElement('input'); inp.type = 'text'; inp.spellcheck = false; inp.className = 'disp-num'; inp.value = cfg[k] || '';
                w.append(inp); intlIn[k] = inp; body.append(w);
            });
            const erF = el('label', 'disp-fld'); erF.style.marginTop = 'var(--sp-1-5)';
            erF.append(el('span', 'disp-fld-lab', 'Reason for export'));
            const erSel = el('select', 'psel');
            (cfg.export_reasons || ['Sale']).forEach(v => { const op3 = el('option', null, v.replace(/_/g, ' ')); op3.value = v; if (v === (cfg.export_reason || 'Sale')) op3.selected = true; erSel.append(op3); });
            erF.append(erSel); body.append(erF);
            const dpF = el('label', 'disp-fld'); dpF.style.marginTop = 'var(--sp-1-5)';
            dpF.append(el('span', 'disp-fld-lab', 'Who pays import duties'));
            const dpSel = el('select', 'psel');
            const DP_LABELS = { 'Duties_To_Be_Paid_By_Receiver': 'The customer (receiver) pays duties', 'Duties_To_Be_Paid_By_Sender': 'We (the sender) pay duties', 'Duties_To_Be_Paid_By_Third_Party': 'A third party pays duties' };
            (cfg.duties_payors || Object.keys(DP_LABELS)).forEach(v => { const op4 = el('option', null, DP_LABELS[v] || v); op4.value = v; if (v === (cfg.duties_payor || 'Duties_To_Be_Paid_By_Receiver')) op4.selected = true; dpSel.append(op4); });
            dpF.append(dpSel); body.append(dpF);
            /* A standing decision of this business, written here because the
               pressure to change it comes at exactly the wrong moment: a
               courier refuses an international booking, and paying the duty
               ourselves makes the error go away. It also makes us liable for
               the customer's import charges, which is why the answer is no. */
            const dpWarn = el('div', 'mail-viewwarn');
            dpWarn.style.cssText = 'margin-top:var(--sp-2);margin-bottom:0;display:none';
            dpWarn.textContent = 'Paying duties on the customer\u2019s behalf makes this business '
                + 'liable for their import charges. This is deliberately set to the customer, and a '
                + 'courier refusing a booking is not a reason to change it.';
            body.append(dpWarn);
            const dpShow = () => { dpWarn.style.display =
                dpSel.value === 'Duties_To_Be_Paid_By_Receiver' ? 'none' : ''; };
            dpSel.onchange = dpShow; dpShow();

            /* Checking the number BEFORE the parcel goes, not after customs
               holds it. It sits with the customs settings because that is where
               someone already is when a business customer sends one over. */
            body.append(el('div', 'section-title', 'Check a customer’s EORI'));
            body.append(el('p', 'field-help', 'Checks a customer’s EORI number. Nothing is saved.'));
            const eoriRow = el('div', 'eori-row');
            const eoriIn = document.createElement('input');
            eoriIn.type = 'text'; eoriIn.spellcheck = false; eoriIn.className = 'disp-num';
            eoriIn.placeholder = 'e.g. DE123456789';
            eoriIn.setAttribute('aria-label', 'EORI number to check');
            const eoriBtn = el('button', 'btn', 'Check');
            const eoriOut = el('div', 'eori-line muted');
            eoriBtn.onclick = () => eoriRun(eoriIn, eoriBtn, eoriOut);
            /* Typed and confirmed without reaching for the mouse: this is a
               field somebody uses several times in a row off an email. */
            eoriIn.onkeydown = (e) => {
                if (e.key === 'Enter') { e.preventDefault(); eoriRun(eoriIn, eoriBtn, eoriOut); }
            };
            eoriRow.append(eoriIn, eoriBtn);
            body.append(eoriRow, eoriOut);

            /* How each courier collects, because it genuinely differs: a daily
               UPS collection already calls, while DHL has to be asked each
               time. Whatever is set here decides what the dispatch panel says
               when that courier is picked, and what the booking asks the
               courier for. Anything left on "Use the setting above" falls back
               to it, so a courier you rarely use needs no rule. */
            const cbT = el('div', 'section-title', 'Collections by courier');
            cbT.append(infoButton('About collections by courier', { title: 'Collections by courier', body:
                'A collection is arranged with the parcel, so this is what each courier is asked '
                + 'for when you book with them. Set the ones you have an arrangement with; the '
                + 'rest use the setting above.' }));
            body.append(cbT);
            const collByCarrier = Object.assign({}, cfg.collection_by_carrier || {});
            const carriers = (cfg.carriers && cfg.carriers.length) ? cfg.carriers
                : [{ code: 'UPS', label: 'UPS' }, { code: 'DHL', label: 'DHL' },
                   { code: 'FEDEX', label: 'FedEx' }, { code: 'DPD', label: 'DPD' }];
            const collGrid = el('div', 'coll-grid');
            carriers.forEach(c => {
                const row = el('label', 'disp-fld');
                row.append(el('span', 'disp-fld-lab', c.label));
                const sc = el('select', 'psel');
                const none = el('option', null, 'Use the setting above'); none.value = '';
                if (!collByCarrier[c.code]) none.selected = true;
                sc.append(none);
                (cfg.collection_options || Object.keys(DP_COLL_LABELS)).forEach(v => {
                    const o = el('option', null, DP_COLL_LABELS[v] || v.replace(/_/g, ' '));
                    o.value = v;
                    if (collByCarrier[c.code] === v) o.selected = true;
                    sc.append(o);
                });
                sc.onchange = () => {
                    if (sc.value) collByCarrier[c.code] = sc.value; else delete collByCarrier[c.code];
                    collNote.textContent = collSummary();
                };
                row.append(sc); collGrid.append(row);
            });
            body.append(collGrid);
            const collSummary = () => {
                const set = Object.keys(collByCarrier);
                if (!set.length) return 'No courier has its own rule yet, so every booking uses the setting above.';
                return set.map(k => {
                    const lab = (carriers.find(c => c.code === k) || {}).label || k;
                    return lab + ': ' + (COLL_MSG[collByCarrier[k]] || collByCarrier[k]);
                }).join('  \u00b7  ');
            };
            const collNote = el('p', 'field-help', collSummary());
            body.append(collNote);

            // Box presets
            body.append(el('div', 'section-title', 'Box presets'));
            body.append(el('p', 'field-help', 'Parcel sizes in cm and kg. Tick the default.'));
            const boxHost = el('div'); body.append(boxHost);
            let boxes = (cfg.boxes || []).map(b => Object.assign({}, b));
            /* A box with no id cannot be pointed at: older configs predate them,
               and the default is stored BY id. */
            boxes.forEach((b, i) => { if (!b.id) b.id = 'box' + (i + 1) + '_' + Date.now(); });
            let defaultBoxId = cfg.default_box_id || '';
            function renderBoxes() {
                boxHost.innerHTML = '';
                boxes.forEach((b, i) => {
                    const rowb = el('div', 'disp-boxedit');
                    /* Which box the dispatch panel opens on. A radio because it
                       is one of many, and it reads as the row's own state. */
                    const def = document.createElement('input');
                    def.type = 'radio'; def.name = 'ship-default-box';
                    def.className = 'disp-boxdef';
                    def.checked = (defaultBoxId === b.id);
                    def.title = 'Start dispatch with this box';
                    def.setAttribute('aria-label', 'Use ' + (b.name || 'this box') + ' by default');
                    def.onchange = () => { if (def.checked) defaultBoxId = b.id; };
                    rowb.append(def);
                    const nm = document.createElement('input'); nm.type = 'text'; nm.className = 'disp-num disp-boxname'; nm.value = b.name || ''; nm.placeholder = 'Name';
                    nm.oninput = () => b.name = nm.value;
                    rowb.append(nm);
                    [['width', 'W'], ['length', 'L'], ['depth', 'D'], ['weight', 'kg']].forEach(([k, ph]) => {
                        const inp = document.createElement('input'); inp.type = 'number'; inp.min = '0'; inp.step = '0.1'; inp.className = 'disp-num disp-boxdim'; inp.value = b[k]; inp.placeholder = ph === 'kg' ? ph : ph + ' cm';
                        inp.oninput = () => b[k] = parseFloat(inp.value) || 0;
                        rowb.append(inp);
                    });
                    const rm = el('button', 'icon-btn'); rm.innerHTML = I.x; rm.title = 'Remove';
                    rm.onclick = () => {
                        if (boxes[i].id === defaultBoxId) defaultBoxId = '';
                        boxes.splice(i, 1); renderBoxes();
                    };
                    rowb.append(rm);
                    boxHost.append(rowb);
                });
                const add = el('button', 'btn'); add.style.marginTop = 'var(--sp-1-5)'; add.append(ico(I.plus), document.createTextNode('Add box'));
                add.onclick = () => { boxes.push({ id: 'box' + (boxes.length + 1) + '_' + Date.now(), name: 'New box', width: 20, length: 15, depth: 10, weight: 0.5 }); renderBoxes(); };
                boxHost.append(add);
            }
            renderBoxes();

            const foot = el('div', 'modal-foot');
            const saveB = el('button', 'btn btn-primary'); saveB.textContent = 'Save shipping settings';
            saveB.onclick = async () => {
                const origin = {}; Object.keys(of).forEach(k => origin[k] = of[k].value.trim());
                /* Every preset is saved or none is. Half-filled rows used to be
                   dropped in silence under "saved", and removing the last one
                   was undone on reopen by the same rule, also under "saved". */
                const gap = boxes.findIndex(b => !(String(b.name || '').trim() && b.width > 0 && b.length > 0
                                                   && b.depth > 0 && b.weight > 0));
                if (gap >= 0) {
                    addToast('Box preset ' + (gap + 1) + ' (' + (String(boxes[gap].name || '').trim() || 'no name')
                        + ') needs a name, all three sizes and a weight above 0. Fill it in or remove it.');
                    return;
                }
                if (!boxes.length) {
                    addToast('Keep at least one box preset: the dispatch panel starts every parcel from one.');
                    return;
                }
                if (boxes.length > 24) {
                    addToast('Keep it to 24 box presets: the server keeps the first 24, and the rest would be dropped.');
                    return;
                }
                const clean = boxes;
                saveB.disabled = true;
                try {
                    const payload = { op: 'set', origin: origin, notify_customer: notifyCb.checked,
                        plugin_code: pluginIn.value.trim() || 'Web_Service',
                        ready_time: readyIn.value || '', close_time: closeIn.value || '',
                        collection_option: coSel.value,
                        collection_by_carrier: collByCarrier,
                        eori: intlIn.eori.value.trim(), vat_number: intlIn.vat_number.value.trim(),
                        default_hs_code: intlIn.default_hs_code.value.trim(), trade_term: intlIn.trade_term.value.trim(),
                        export_reason: erSel.value, duties_payor: dpSel.value,
                        label_size_production: sizeIn.label_size_production.value,
                        label_size_shipping: sizeIn.label_size_shipping.value };
                    payload.boxes = clean;
                    /* Only ever a box that is actually being saved: a default
                       pointing at a deleted or half-filled row would send the
                       dispatch panel looking for a parcel that is not there. */
                    payload.default_box_id = clean.some(b => b.id === defaultBoxId) ? defaultBoxId : '';
                    if (!fromEnv) {
                        if (credIn.meter_number.value.trim()) payload.meter_number = credIn.meter_number.value.trim();
                        if (credIn.key.value.trim()) payload.key = credIn.key.value.trim();
                        if (credIn.password.value.trim()) payload.password = credIn.password.value.trim();
                    }
                    const r = await api('/api/shipping/config', payload);
                    shippingCfg = r.config || null;
                    addToast('Shipping settings saved.');
                    close();
                } catch (e) { saveB.disabled = false; toastError(e.message || 'Could not save'); }
            };
            foot.append(saveB);
            modal.append(foot);
        }

        let printSeq = 0;
        async function printFromAdminLink(orderId) {
            const box = $('labels-content'); box.innerHTML = '';
            const hero = pageHead({ view: 'labels', title: 'Production Manager', line: 'Preparing the label for this order\u2026' });
            box.append(hero);
            const t = el('div', 'thinking'); t.style.marginTop = 'var(--sp-2)'; t.append(loader(), el('span', null, 'Fetching the order\u2026')); box.append(t);
            labelsLoading = true;
            try {
                const data = await api('/api/production-labels', { order_id: orderId });
                if (!data.orders || !data.orders.length) throw new Error(data.error_note || 'Order not found.');
                labelsCache = { data, at: Date.now() };
                labelSel = data.orders[0].id;
                labelsLoading = false;
                renderLabels();
                setTimeout(() => printLabels([data.orders[0]]), 450);   // preview is up; open the print dialog
            } catch (e) {
                labelsLoading = false;
                reportFailed(box, hero, 'That order could not be loaded. ' + (e.message || String(e)), null, () => loadLabels(true));
            }
        }
        async function dispatchFromAdminLink(orderId) {
            const box = $('labels-content'); box.innerHTML = '';
            const hero = pageHead({ view: 'labels', title: 'Production Manager', line: 'Opening dispatch for this order\u2026' });
            box.append(hero);
            const t = el('div', 'thinking'); t.style.marginTop = 'var(--sp-2)'; t.append(loader(), el('span', null, 'Fetching the order\u2026')); box.append(t);
            labelsLoading = true;
            try {
                const data = await api('/api/production-labels', { order_id: orderId });
                if (!data.orders || !data.orders.length) throw new Error(data.error_note || 'Order not found.');
                labelsCache = { data, at: Date.now() };
                labelSel = data.orders[0].id;
                labelsLoading = false;
                renderLabels();
                openDispatch(data.orders[0]);
            } catch (e) {
                labelsLoading = false;
                reportFailed(box, hero, 'That order could not be loaded. ' + (e.message || String(e)), null, () => loadLabels(true));
            }
        }
        function printLabels(orders) {
            // Sequence guard: a rapid second print must not be torn down by the previous
            // print's pending cleanup (which would strip its page size and its sheets).
            const seq = ++printSeq;
            const box = $('label-print'); box.innerHTML = '';
            const d = labelDims();
            // Drive the printer's page size from the chosen stock. This has to be injected
            // rather than written in the stylesheet, because @page cannot be scoped by a
            // class and the report print rules already declare their own A4 page.
            let rule = $('label-page-rule');
            if (!rule) { rule = document.createElement('style'); rule.id = 'label-page-rule'; document.head.append(rule); }
            rule.textContent = labelPrintCss(d);
            // Staged off-screen with real layout so each label can be measured and fitted.
            const sheets = orders.map(o => { const s = labelSheet(o); box.append(s); return s; });
            let stamped = false;
            const cleanup = () => {
                if (seq !== printSeq) return;   // a newer print took over; leave it alone
                document.body.classList.remove('printing-label');
                box.innerHTML = '';
                const r = $('label-page-rule');
                if (r && r.parentNode) r.parentNode.removeChild(r);
                // Stamp printed only after the dialog is out of the way (not before it
                // opens), and only once. stampPrinted repaints when the write settles.
                if (!stamped) { stamped = true; stampPrinted(orders); }
            };
            // The label typeface must be in before measuring or printing (2s cap), or
            // the fit runs against fallback metrics and the printout differs.
            const fontReady = labelFontReady();
            fontReady.then(() => {
                if (seq !== printSeq) return;
                sheets.forEach(fitLabel);
                document.body.classList.add('printing-label');
                if (window.onafterprint !== undefined) window.addEventListener('afterprint', cleanup, { once: true });
                setTimeout(() => {
                    if (seq !== printSeq) return;   // taken over in the 40ms since
                    window.print(); setTimeout(cleanup, 800); }, 40);
            }, () => cleanup());
        }

