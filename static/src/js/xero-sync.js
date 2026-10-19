        /* ==================================================================
           Reconciliation: an independent auditor over Shopify + Xero + Gmail.
           Everything on this tab is READ from the three systems and never
           written back; the only thing that changes is the exception list's
           statuses. Facts, arithmetic and AI interpretation are visually
           separate, because a guess dressed as a fact is how a wrong number
           survives an audit.
           ================================================================== */
        let reconCache = null, reconFilter = { severity: '', status: '', q: '' }, reconOpen = null;
        /* The search box's text and cursor, carried across the redraw a search makes. */
        let reconSearchKeep = null;
        /* ---------------- Shopify -> Xero connector ----------------
           A separate, audited service turns orders into Xero invoices and
           refunds into credit notes; this tab drives it through the server.
           The shape of the flow is the one Cameron chose: bulk send, with a
           review first - a review is the service's dry run, which maps
           everything and writes nothing, so the numbers on screen are exactly
           what Send will do. */
        let connCache = null;     // last status payload from the service
        let connRuns = null;      // recent run records
        let connReview = null;    // the completed dry run awaiting a Send
        /* The per-order equivalent: {order, data} from a check, and it arms
           only the order it names. */
        let connOneCheck = null;
        let connTagCheck = null;    // the completed check for a tag, awaiting its send
        let connTagBusy = '';
        let connOneBusy = '';
        let connPaySince = '';
        let connPayResult = null;
        /* Which slice of a check's table is on screen. The page is drawn
           again on every change, so the filter and the page live here; a new
           check (a different object) starts its own at the top. */
        let connTagView = { of: null, f: 'all', page: 1, size: 20 };
        let connPayView = { page: 1, size: 20 };
        let connTagPending = '';   // the tag being checked or sent, until the watcher collects it
        let connPayBox = '';       // the date box as it was when the payouts were checked
        let connFocus = null;      // {sec, on}: where focus goes back to after a filter or a page turn
        let connQuar = null;       // the quarantine list, read with the status, not on every repaint
        let connAuto = null;
        let connHealth = null;
        let connSettings = null;
        let connSettingsOpen = false;
        let connSettingsEdits = {};   // what has been typed in the open form, so a repaint keeps it
        /* The document a dry run says it would send, laid out the way it will
           appear in Xero. Nothing here writes: it is the last look before the
           accounts are touched, so it shows the fields that decide what lands
           there - the contact, the dates, and every line's account code and
           tax type - rather than an outcome word. */
        /* A time a person can act on: "4 minutes ago", "in 6 minutes". An
           Auto Run status showing a raw timestamp makes the reader do the
           arithmetic to answer the only question they have, which is whether
           it is still going. */
        function fmtWhen(iso) {
            const t = Date.parse(iso);
            if (!t) return '';
            const secs = Math.round((t - Date.now()) / 1000);
            const ahead = secs > 0;
            const n = Math.abs(secs);
            const say = n < 60 ? 'less than a minute'
                : n < 3600 ? Math.round(n / 60) + (Math.round(n / 60) === 1 ? ' minute' : ' minutes')
                : n < 86400 ? Math.round(n / 3600) + (Math.round(n / 3600) === 1 ? ' hour' : ' hours')
                : fmtDate(iso);
            if (say === fmtDate(iso)) return say;
            return ahead ? 'in ' + say : say + ' ago';
        }
        function connDocModal(d) {
            const p = d.preview || {};
            const credit = d.kind === 'creditnote';
            /* Shopify sends money as strings, and "175.0" was reaching the
               page as written. A number in any form is shown to two places;
               a string that is not one is shown as it came. */
            const money2 = (n, cur) => {
                if (n === undefined || n === null || n === '') return '';
                const v = typeof n === 'number' ? n : Number(n);
                /* Through the app's one money rule: 'GBP 1842.50' sat beside
                   '£1,842.50' in the same tile. */
                return Number.isFinite(v) ? money(v, cur || p.currency || 'GBP', 2) : String(n);
            };
            const m = sheetModal((credit ? 'Credit note ' : 'Invoice ')
                                 + (p.number || d.key || ''));
            /* Three outcomes, not two: an invoice the previous feed raised
               that already says the same money is adopted, and adopted means
               nothing is written. Calling that a replacement would be false. */
            const what = d.action === 'unchanged'
                ? ('Already in Xero. Nothing will be written to the '
                   + (credit ? 'credit note' : 'invoice') + '.')
                : p.updatesExisting
                ? ('Replaces the ' + (credit ? 'credit note' : 'invoice')
                   + ' already in Xero, in place.')
                : ('Creates a new ' + (credit ? 'credit note' : 'invoice') + ' in Xero.');
            m.body.append(el('div', 'field-help', what));
            /* The connector's own note, in words: on a check it was always
               '(dry run, dash, not pushed)', which the window already says. */
            const note = cxWhy(d, true);
            if (note) {
                m.body.append(el('div', 'msg ' + (cxGroup(d) === 'attention' ? 'error' : ''), note));
            }
            /* The reconciliation FIRST, because it is the one line that says
               whether everything below it can be trusted. It is the number the
               connector's own check uses, not one worked out here. */
            const rec = p.reconcile;
            if (rec) {
                const box = el('div', 'msg ' + (rec.ok ? '' : 'error'));
                box.append(el('div', null, rec.ok
                    ? 'Reconciles with Shopify: ' + money2(rec.computed) + (credit ? ' both sides, tax included.' : ' both sides.')
                    : 'Does not reconcile. This document comes to '
                      + money2(rec.computed) + (credit ? ' with tax' : '') + ', Shopify says ' + money2(rec.expected)
                      + ', a difference of ' + money2(rec.diff) + '.'));
                if (!rec.ok) {
                    box.append(el('div', 'lbl-meta', rec.mode === 'strict'
                        ? 'Held back: a total that disagrees is held back, so this will not be sent.'
                        : 'A total that disagrees is sent anyway, so this would be sent. Do not send it.'));
                }
                m.body.append(box);
            }

            const cust = p.customer;
            if (cust) {
                const box = el('div', 'msg ' + (cust.matched ? '' : 'error'));
                box.append(el('div', null, cust.matched
                    ? 'Lands on the Xero contact ' + (cust.name || '(unnamed)') + '.'
                    : 'No Xero contact matched for ' + (cust.name || 'this customer')
                      + ', so this cannot be sent until one exists.'));
                const sub = [cust.email,
                             cust.xeroContactId ? 'Xero id ' + cust.xeroContactId : '']
                    .filter(Boolean).join(' \u00b7 ');
                if (sub) box.append(el('div', 'lbl-meta cx-contact', sub));
                m.body.append(box);
            }

            const dl = el('dl', 'conn-pairs');
            const pair = (k, v) => {
                if (!v) return;
                dl.append(el('dt', null, k));
                dl.append(el('dd', null, String(v)));
            };
            pair('Contact', p.contact);
            pair('Type', p.type);
            pair('Date', p.date);
            pair('Due', p.dueDate);
            pair('Reference', p.reference);
            pair('Currency', p.currency);
            pair('Status', p.status);
            /* The customer reference gets its own labelled row rather than an
               abbreviation in a meta line: it is the field Xero matches on
               account number, so it is checked, not glanced at. When it is
               empty the row says WHERE it was looked for, because a customer
               with no reference and a connector reading the wrong metafield
               look identical otherwise. */
            if (cust && cust.reference) {
                pair('Customer reference', cust.reference
                    + (cust.referenceField ? '  (' + cust.referenceField + ')' : ''));
            } else if (cust && cust.referenceField) {
                pair('Customer reference', 'none set in ' + cust.referenceField);
            }
            pair('Ledger key', p.key);
            const o = p.order;
            if (o) {
                pair('Shopify order', o.name + (o.financialStatus
                    ? ' \u00b7 ' + String(o.financialStatus).toLowerCase().replace(/_/g, ' ') : ''));
                pair('Placed', o.createdAt ? fmtDate(o.createdAt) : '');
                /* The gateway is what chose the due date, so it belongs beside it. */
                pair('Paid by', (o.gateways || []).join(', '));
            }
            m.body.append(dl);

            const lines = p.lines || [];
            if (!lines.length) {
                m.body.append(el('div', 'empty', 'This document has no lines.'));
                return;
            }
            const wrap = el('div', 'conn-doc-wrap');
            const t = document.createElement('table'); t.className = 'conn-doc cd-lines';
            const thead = document.createElement('thead');
            const hr = document.createElement('tr');
            [['Description', ''], ['Qty', 'num'], ['Unit', 'num'],
             ['Account', ''], ['Tax', ''], ['Amount', 'num']].forEach(([h, c]) => {
                const th = document.createElement('th');
                th.textContent = h; if (c) th.className = c; hr.append(th);
            });
            thead.append(hr); t.append(thead);
            const tb = document.createElement('tbody');
            /* money2, never an alias named money: 'const money = money2' made
               money2's own call to money() reach this const (not yet set,
               then itself), so the window threw on every document it opened. */
            lines.forEach(l => {
                const tr = document.createElement('tr');
                const cells = [[l.description || '', ''],
                               [String(l.quantity), 'num'],
                               [money2(l.unitAmount), 'num'],
                               [l.accountCode || '', ''],
                               /* A credit-note line carries the tax Shopify refunded on it;
                                  an invoice line leaves the figure to Xero and shows only the type. */
                               [(l.taxType || '') + (l.taxAmount != null ? ' \u00b7 ' + money2(l.taxAmount) : ''), ''],
                               [money2(l.lineAmount), 'num']];
                cells.forEach(([v, c], i) => {
                    const td = document.createElement('td');
                    td.textContent = v;
                    /* The four in the middle fold under the description on a phone. */
                    const cls = [c, i > 0 && i < 5 ? 'cd-mid' : ''].filter(Boolean).join(' ');
                    if (cls) td.className = cls; tr.append(td);
                });
                tr.children[0].append(el('div', 'conn-doc-meta lbl-meta',
                    [String(l.quantity) + ' \u00d7 ' + money2(l.unitAmount), l.accountCode || '',
                     (l.taxType || '') + (l.taxAmount != null ? ' ' + money2(l.taxAmount) : '')]
                        .filter(x => x && x.trim()).join(' \u00b7 ')));
                if (l.discountRate) {
                    tr.children[0].append(el('div', 'lbl-meta',
                        'less ' + l.discountRate + '% discount'));
                }
                tb.append(tr);
            });
            t.append(tb);
            const tf = document.createElement('tfoot');
            const fr = document.createElement('tr');
            const lbl = document.createElement('td'); lbl.colSpan = 5;
            /* Never a tax figure and never a gross total: with Exclusive lines
               Xero works the tax out from the tax types above, and a number
               invented here could disagree with the invoice that appears. */
            lbl.textContent = p.lineAmountTypes === 'Inclusive'
                ? 'Total of lines, tax included'
                : 'Total of lines, before tax';
            const val = document.createElement('td'); val.className = 'num';
            val.textContent = money2(p.lineTotal);
            fr.append(lbl, val); tf.append(fr); t.append(tf);
            wrap.append(t); m.body.append(wrap);
            if (p.lineAmountTypes !== 'Inclusive') {
                m.body.append(el('div', 'field-help',
                    'Xero adds tax from the tax type on each line, so the invoice total '
                    + 'there will be higher than this.'));
            }
            /* What an update would MOVE. Only present when this is an update,
               which is the one action that alters a document already in the
               accounts. */
            const changes = p.changes;
            if (changes && changes.length) {
                m.body.append(el('h4', 'card-title', 'What this changes in Xero'));
                const cw = el('div', 'conn-doc-wrap');
                const ct = document.createElement('table'); ct.className = 'conn-doc';
                const chead = document.createElement('thead');
                const chr = document.createElement('tr');
                ['Field', 'In Xero now', 'Would become'].forEach(h => {
                    const th = document.createElement('th'); th.textContent = h; chr.append(th);
                });
                chead.append(chr); ct.append(chead);
                const ctb = document.createElement('tbody');
                changes.forEach(c => {
                    const tr = document.createElement('tr');
                    [c.field, c.from, c.to].forEach(v => {
                        const td = document.createElement('td'); td.textContent = v || ''; tr.append(td);
                    });
                    ctb.append(tr);
                });
                ct.append(ctb); cw.append(ct); m.body.append(cw);
            } else if (d.action === 'updated') {
                m.body.append(el('div', 'field-help',
                    'This is an update, but the document in Xero could not be read to say '
                    + 'what would change.'));
            }

            /* The payout note, on the document it would be written to. Four
               states, and only one of them is a problem: not yet paid out is
               the ordinary answer for a recent order. */
            const pay = p.payout;
            if (pay) {
                m.body.append(el('h4', 'card-title', 'Payout note'));
                if (pay.state === 'unavailable' && pay.reason === 'not_shopify_payments') {
                    /* Paid by PayPal, bank transfer, on account or marked as
                       paid: no Shopify payout will ever carry it. Nothing
                       failed, so it is a plain line, in the connector's words,
                       which name how the order is paid. */
                    m.body.append(el('div', 'field-help', pay.message
                        || 'Shopify Payments took no payment for this order, so no Shopify '
                        + 'payout will include it and there is no payout note to add.'));
                } else if (pay.state === 'unavailable') {
                    const b = el('div', 'msg error');
                    const why = cxPayoutWhy(pay, { auth: ((connCache.data || {}).config || {}).shopifyAuth, admin: connIsAdmin() });
                    b.append(el('div', null, why.lead));
                    if (why.detail) b.append(el('div', 'lbl-meta', why.detail));
                    m.body.append(b);
                } else if (pay.state === 'not_yet') {
                    m.body.append(el('div', 'field-help',
                        'This order has not been paid out by Shopify yet, so there is no '
                        + 'payout to name. Shopify settles a few days after an order; run '
                        + 'the payout pass again once it has.'));
                } else {
                    m.body.append(el('div', 'disp-ok-line', pay.state === 'already_added'
                        ? 'This note is already on the invoice in Xero.'
                        : 'This note would be added to the invoice in Xero.'));
                    const q = el('div', 'conn-note');
                    q.textContent = pay.note || '';
                    m.body.append(q);
                    const bits = [pay.gross ? 'gross ' + (pay.currency || '') + ' ' + pay.gross : '',
                                  pay.fee ? 'fee ' + pay.fee : '',
                                  pay.net ? 'net ' + pay.net : ''].filter(Boolean).join(' \u00b7 ');
                    if (bits) {
                        m.body.append(el('div', 'field-help',
                            'This order in that payout: ' + bits
                            + '. The bank receives the payout after the fee, which is why '
                            + 'the invoice total and the bank line differ.'));
                    }
                }
            }

            /* Shopify's own figures, unaltered, so the screen can be read
               straight against the order rather than trusted on its own. */
            if (p.order) {
                const o = p.order;
                m.body.append(el('h4', 'card-title', 'What Shopify says'));
                const st = document.createElement('table'); st.className = 'conn-doc';
                const stb = document.createElement('tbody');
                [['Subtotal, after discounts', o.subtotal],
                 ['Shipping', o.shipping],
                 ['Tax', o.tax],
                 ['Total', o.total]].forEach(([k, v]) => {
                    if (v === undefined || v === null || v === '') return;
                    const tr = document.createElement('tr');
                    const a = document.createElement('td'); a.textContent = k;
                    const b = document.createElement('td'); b.className = 'num';
                    b.textContent = money2(v, o.currency);
                    tr.append(a, b); stb.append(tr);
                });
                st.append(stb);
                const sw = el('div', 'conn-doc-wrap'); sw.append(st);
                m.body.append(sw);
                m.body.append(el('div', 'field-help',
                    'Subtotal plus shipping is what this document is reconciled against. '
                    + 'Tax is not, because Xero works that out itself.'));
            }
        }
        function connOneArmed(order) {
            return !!(connOneCheck && connOneCheck.order && !connOneCheck.sent
                      && connOneCheck.order === String(order || '').trim());
        }
        /* WHAT THE CONNECTOR SAYS, IN THIS PAGE'S WORDS.
           Its own are an engineer's: an action code ('created' even on a
           check that writes nothing), '(dry run, dash, not pushed)' on every
           row of a check, 'Xero doc is PAID with 1023.83 paid/allocated,
           dash, re-import blocked to protect it ... or force', and problems
           that name environment variables and a .jsonl file. The code picks
           the word, the tone and the group here; a message is kept only
           where it says something the word does not, in plain English, with
           no dash and no setting name the page does not show. The patterns
           are the connector's own strings (shopify-xero-connector:
           sync/reimportOrder.ts, sync/summarise.ts, sync/syncOrders.ts,
           failsafe/validate.ts, mappers/*.ts); anything else is shown as it
           came, made plain. */
        /* [on a check, after a send, tone on a check, tone after a send].
           Nothing has happened on a check, so what it WOULD do is not green:
           colour is for what did happen. */
        const CX_DOC_WORDS = {
            created: ['Would create', 'Created', 'note', 'made'],
            updated: ['Would update', 'Updated', 'note', 'made'],
            unchanged: ['Already in Xero', 'Already in Xero', 'note', 'note'],
            locked: ['Left alone', 'Left alone', 'note', 'note'],
            nothing: ['Nothing to send', 'Nothing to send', 'note', 'note'],
            blocked: ['Cannot send yet', 'Not sent', 'warn', 'warn'],
            quarantined: ['Quarantined', 'Quarantined', 'bad', 'bad'],
            failed: ['Failed', 'Failed', 'bad', 'bad'],
        };
        /* 'blocked' covers three different things: a document Xero holds
           paid or closed (left alone on purpose), an order with nothing to
           send (cancelled, a test, a refund that returned no money), and one
           that cannot go until someone acts (no Xero contact, an archived
           one, two live invoices). They are told apart by the message. */
        const CX_LOCKED = /^Xero doc is[ ]|paid\/allocated/i;
        const CX_NOTHING = /cancelled order|\btest order\b|returned no money|VOIDED with no refunds/i;
        function cxKind(d) {
            if (d.action !== 'blocked') return CX_DOC_WORDS[d.action] ? d.action : 'failed';
            const m = String(d.message || '');
            return CX_LOCKED.test(m) ? 'locked' : CX_NOTHING.test(m) ? 'nothing' : 'blocked';
        }
        /* The tab a document belongs under. */
        function cxGroup(d) {
            const k = cxKind(d);
            return (k === 'created' || k === 'updated') ? 'write' : k === 'unchanged' ? 'unchanged'
                : (k === 'locked' || k === 'nothing') ? 'alone' : 'attention';
        }
        /* A document a check would write whose total does not match Shopify
           (the connector's own reconcile on its preview). It stays in what
           Send writes, because it is; but it is never shown as a safe grey
           "Would create": #104530 was £33.50 out, and only its document
           window said so. One the connector already holds back keeps its
           own word. */
        function cxMismatch(d) {
            const rec = d && d.preview && d.preview.reconcile;
            if (!rec || rec.ok !== false) return null;
            const k = cxKind(d);
            return (k === 'created' || k === 'updated') ? rec : null;
        }
        /* What Send does with those, in its dialog: named, with how far out.
           Always "as it stands": in strict mode the connector's check already
           reports such a document as quarantined, which is not flagged here. */
        function cxMismatchNote(items) {
            const mis = (items || []).filter(x => cxMismatch(x.d));
            if (!mis.length) return '';
            const one = mis.length === 1;
            const names = mis.slice(0, 3).map(x => {
                const rec = cxMismatch(x.d), cur = (x.d.preview || {}).currency || 'GBP';
                return (x.order ? x.order + ', ' : '') + money(Math.abs(Number(rec.diff) || 0), cur, 2) + ' out';
            });
            return ' ' + mis.length + (one ? ' document does not' : ' documents do not') + ' match Shopify and '
                + 'will be sent as ' + (one ? 'it stands' : 'they stand') + ': '
                + names.join('; ') + (mis.length > 3 ? ' and ' + (mis.length - 3) + ' more' : '') + '.';
        }
        /* The settings by the names the Settings card gives them; any other
           setting by its name in words. */
        const CX_SETTING_WORDS = { MAX_DOCS_PER_RUN: 'Most documents in one run', RUNAWAY_ABORT_ABOVE: 'Stop entirely above',
            ORDERS_SINCE: 'Only orders since', RECONCILE_MODE: 'When a total disagrees', RECONCILE_TOLERANCE: 'Tolerance' };
        function cxSettingName(k) {
            return CX_SETTING_WORDS[k] || k.split('_').map((w, i) => ({ XERO: 'Xero', SHOPIFY: 'Shopify', ID: 'ID', URL: 'URL', API: 'API' }[w]
                || (i ? w.toLowerCase() : w.charAt(0) + w.slice(1).toLowerCase()))).join(' ');
        }
        const cxEnd = (t) => { t = String(t || '').trim(); return !t || /[.!?]$/.test(t) ? t : t + '.'; };
        function cxPlain(s) {
            let t = String(s == null ? '' : s)
                .replace(/\s*\(dry run\s*[\u2012-\u2015-]+\s*not pushed\)\s*/gi, ' ');
            /* Words inside double quotes are a product's own name or a line's
               description, read against the order: left exactly as they are. */
            t = t.split(/("[^"]*")/).map((part, i) => i % 2 ? part : part
                .replace(/(\d)\s*[\u2012-\u2015]\s*(\d)/g, '$1 to $2')
                .replace(/\s*[\u2012-\u2015]+\s*/g, ', ')
                .replace(/\s*\(set it in the Settings tab or \.env\)/gi, ' (set it in Settings)')
                .replace(/\bXero[ ](\d{3})[ ]ValidationException\b:?\s*/g, 'Xero refused it ($1). ')
                .replace(/\bValidationException:?\s*(?:A validation exception occurred\.?\s*)?/g, '')
                .replace(/\bShopify auth\/connectivity failed:\s*/gi, 'Shopify could not be reached, or refused the sign-in: ')
                .replace(/state\/quarantine\.jsonl/g, 'the quarantine list')
                .replace(/\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)(?:=([^\s,;)]*[^\s,;).:]))?/g,
                         (m0, k, v) => '"' + cxSettingName(k) + '"' + (v ? ' (' + v + ')' : ''))).join('');
            t = t.replace(/\s+,/g, ',').replace(/([.,;:!?]),/g, '$1').replace(/[,\s]+$/, '').replace(/\s{2,}/g, ' ').trim();
            if (!t) return '';
            /* A capital for a sentence, but never for iPhone or eBay. */
            return /^[a-z][A-Z]/.test(t) ? t : t.charAt(0).toUpperCase() + t.slice(1);
        }
        /* One detail from a validation or a Xero reply, as a sentence. Parts
           the connector joins with '; ' become sentences of their own. */
        function cxDetail(s) {
            const m2 = (v) => money(Number(v) || 0, 'GBP', 2);
            return String(s == null ? '' : s).split(/;\s+/).map(part => {
                let m;
                /* 'invoice reconciliation: computed X vs Shopify Y (diff Z)', and
                   the credit note's '(incl. VAT)' form, however it is prefixed. */
                if ((m = /computed[ ](-?[\d.]+) vs Shopify[ ](-?[\d.]+)(?:[ ]\(diff[ ](-?[\d.]+)\))?/i.exec(part))) {
                    const apart = m[3] != null ? ', ' + m2(m[3]) + ' apart.' : '.';
                    return /credit note/i.test(part)
                        ? 'The credit note comes to ' + m2(m[1]) + ' with VAT against ' + m2(m[2]) + ' refunded in Shopify' + apart
                        : 'The lines come to ' + m2(m[1]) + ' against ' + m2(m[2]) + ' in Shopify' + apart;
                }
                if ((m = /^currency[ ](\w+) != order currency[ ](\w+)/i.exec(part))) return 'The document is in ' + m[1] + ' but the order is in ' + m[2] + '.';
                if ((m = /^credit note[ ](-?[\d.]+) exceeds refunded amount[ ](-?[\d.]+)/i.exec(part))) {
                    return 'The credit note (' + m2(m[1]) + ') is more than was refunded (' + m2(m[2]) + ').';
                }
                if ((m = /pre-resolve failed \((.*)\)\s*[\u2012-\u2015-]+\s*pushing without ID/i.exec(part))) {
                    return 'It could not be looked up in Xero first (' + m[1] + '), so it was sent without its Xero id.';
                }
                return cxEnd(cxPlain(part));
            }).filter(Boolean).join(' ');
        }
        /* Why a payout could not be named, as {lead, detail}. The connector
           gives the reason as a field (reason, needs) from its October 2026
           version; before that only in words, and its single-order lookup
           passed Shopify's own JSON through, which reached the document window
           as one clipped line. Shopify's JSON never reaches the page now, and
           neither does a client's error string. Only the connector's payout
           wording is read as a payout failure: the payout pass also carries
           errors that have nothing to do with Shopify ("A sync is already
           running", a volume's "permission denied"), and those keep their own
           words. ctx: {auth, admin, pass}. auth is how the connector signs in
           to Shopify (client_credentials is Reactor's own app, static one of
           its own), and pass is the payout pass rather than one document. */
        const CX_PAY_SCOPES = { read_shopify_payments_accounts: 'Shopify Payments accounts',
            read_shopify_payments_payouts: 'Shopify Payments payouts' };
        function cxPayoutWhy(pay, ctx) {
            pay = pay || {}; ctx = ctx || {};
            const msg = String(pay.message || pay.error || '');
            const pass = !!ctx.pass;
            const unaffected = pass ? '' : ' The invoice itself is unaffected.';
            const payoutWords = /^Could not read payouts:|Shopify refused the payouts query|^This shop has no Shopify Payments account|^More than [\d,]+ /.test(msg);
            const reason = pay.reason || pay.errorReason
                || (!payoutWords ? 'other'
                    : /Shopify refused the payouts query|Access denied for|Required access|not approved to access/i.test(msg) ? 'refused'
                    : /^This shop has no Shopify Payments account/.test(msg) ? 'no_account'
                    : /^More than [\d,]+ /.test(msg) ? 'too_many' : 'failed');
            if (reason === 'other') {
                return { lead: pass ? 'No notes were written.' : 'The payout could not be looked up, so no note can be shown.' + unaffected,
                    detail: msg ? cxDetail(msg) : '' };
            }
            if (reason === 'refused') {
                let needs = (pay.needs || []).filter(k => CX_PAY_SCOPES[k]);
                if (!needs.length) needs = Object.keys(CX_PAY_SCOPES).filter(k => msg.indexOf(k) >= 0);
                if (!needs.length) needs = Object.keys(CX_PAY_SCOPES);
                const what = 'view ' + needs.map(k => CX_PAY_SCOPES[k]).join(' and ') + ' (' + needs.join(', ') + ')';
                const lead = (pass ? 'Shopify would not show the payouts, so no notes can be written.'
                    : 'Shopify would not show this order’s payout, so no note can be shown.') + unaffected;
                const one = needs.length === 1 ? 'that permission' : 'those permissions';
                /* Shopify refuses the account before the payouts under it, so a
                   refusal there names only the accounts permission. Settings
                   shows Reactor's whole grant; an app of its own cannot be seen
                   from here, so the second permission is named as well. */
                const also = needs.indexOf('read_shopify_payments_payouts') < 0
                    ? ' Payout notes also need ' + CX_PAY_SCOPES.read_shopify_payments_payouts
                      + ' (read_shopify_payments_payouts), so add that too if it is missing.' : '';
                let detail;
                if (ctx.auth === 'client_credentials') {
                    detail = 'The Xero sync signs in to Shopify as Reactor, and Reactor is not allowed to ' + what + '.'
                        + (ctx.admin ? ' Settings, under Connections, says which permissions Reactor is missing and how to add them.' : ' An admin can add ' + one + '.');
                } else if (ctx.auth === 'static') {
                    detail = 'The Xero sync signs in to Shopify with an app of its own, which is not allowed to ' + what + '.'
                        + (ctx.admin ? ' In Shopify, open Settings, then Apps, find that app under Legacy custom apps, add ' + one + ', and save.' + also
                            : ' An admin can add ' + one + '.');
                } else {
                    detail = 'The Shopify app the Xero sync signs in with is not allowed to ' + what + '.'
                        + (ctx.admin ? ' If it signs in as Reactor, Settings, under Connections, says how to add ' + one
                            + '; if it has an app of its own, add ' + one + ' to that app in Shopify.' + also
                            : ' An admin can add ' + one + '.');
                }
                return { lead: lead, detail: detail };
            }
            if (reason === 'no_account') {
                return { lead: 'This store has no Shopify Payments account, so there ' + (pass ? 'are no payouts to write.' : 'is no payout to name.') + unaffected, detail: '' };
            }
            const lead = (pass ? 'The payouts could not be looked up, so no notes were written.'
                : 'The payout could not be looked up, so no note can be shown.') + unaffected;
            const again = 'Shopify did not answer properly. Try again in a few minutes.';
            let t = msg.replace(/^Could not read payouts:\s*/i, '');
            let m;
            if ((m = /^Shopify GraphQL errors: (\[.*\])$/s.exec(t))) {
                let said = '';
                try { said = JSON.parse(m[1]).map(x => String((x && x.message) || '').trim()).filter(Boolean).join(' '); } catch (e) {}
                t = said ? 'Shopify said: ' + said : 'Shopify’s reply could not be read.';
            } else if ((m = /^Shopify HTTP (\d{3})/.exec(t))) {
                const code = Number(m[1]);
                t = code === 429 || code >= 500 ? 'Shopify did not answer properly (error ' + code + '). Try again in a few minutes.'
                    : code === 401 ? 'Shopify did not accept the Xero sync’s sign-in (error 401), so its Shopify credentials need checking.'
                    : 'Shopify refused the request (error ' + code + ').';
            } else if (/^Shopify query cost exceeded/.test(t)) {
                t = 'Shopify said the lookup asked for too much at once.';
            } else if (/^Shopify GraphQL: (empty data|exhausted retries)|^fetch failed|ECONN|ETIMEDOUT|ENOTFOUND|socket hang up/i.test(t)) {
                t = again;
            }
            /* Whatever is left, never a JSON blob. */
            if (/[\[{]\s*"/.test(t)) t = 'Shopify’s reply could not be read.';
            return { lead: lead, detail: t ? cxEnd(cxPlain(t)) : '' };
        }
        /* One run problem as a sentence. ctx: {guards, admin} from the
           health reply, so a limit that has changed since is said, and
           Settings is named only to someone who has it. */
        function cxProblem(p, ctx) {
            ctx = ctx || {};
            let t = String(p == null ? '' : p).trim();
            const aborted = /^run aborted:\s*/i.test(t);
            t = t.replace(/^run aborted:\s*/i, '');
            const g = ctx.guards || {};
            const now = (cur, was) => (cur != null && Number(cur) !== Number(was))
                ? ' The limit is now ' + Number(cur).toLocaleString('en-GB') + '.' : '';
            let m;
            if ((m = /^runaway guard: (\d+) documents exceeds MAX_DOCS_PER_RUN=(\d+)/i.exec(t))) {
                return 'It stopped before writing anything: ' + m[1] + ' documents were ready, more than one run may write ('
                    + m[2] + ').' + (now(g.maxDocsPerRun, m[2])
                    || (ctx.admin ? ' That limit is "Most documents in one run" in Settings.' : ''));
            }
            if ((m = /^runaway guard: (\d+) orders waiting exceeds RUNAWAY_ABORT_ABOVE=(\d+)/i.exec(t))) {
                return 'It stopped before writing anything, contacts included: ' + m[1] + ' orders were waiting, more than the '
                    + m[2] + ' at which it stops. That many usually means the start date was moved back.'
                    + (now(g.runawayAbortAbove, m[2]) || (ctx.admin ? ' Both are in Settings: "Stop entirely above" and "Only orders since".' : ''));
            }
            if ((m = /^circuit breaker: (\d+)\/(\d+) \((\d+)%\)/i.exec(t))) {
                return 'It stopped before writing anything: ' + m[1] + ' of ' + m[2] + ' documents (' + m[3]
                    + '%) failed the checks, so none were sent. They are quarantined.';
            }
            if ((m = /^(\d+) edited orders exceed MAX_DOCS_PER_RUN=(\d+)/i.exec(t))) {
                return m[1] + ' edited orders were more than one run may write (' + m[2] + '), so none were re-checked.';
            }
            if ((m = /^preflight failed:\s*(.*)$/i.exec(t))) return 'It stopped before starting. ' + cxDetail(m[1]);
            if ((m = /^run failed:\s*(.*)$/i.exec(t))) return 'The run failed. ' + cxDetail(m[1]);
            if ((m = /^preflight:\s*(.*)$/i.exec(t))) return 'Before starting: ' + cxDetail(m[1]);
            if ((m = /^(invoice|credit note) (\S+): (order edited after payment|already in Xero); (Xero doc is .*)$/i.exec(t))) {
                const kind = m[1].toLowerCase() === 'invoice' ? 'invoice' : 'creditnote';
                return cxPlain(m[1]) + ' ' + m[2] + ': ' + (/edited/i.test(m[3]) ? 'the order was edited after payment. ' : 'already in Xero. ')
                    + cxWhy({ action: 'blocked', kind: kind, message: m[4] }, false);
            }
            if ((m = /^(invoice|credit note) for (#\S+?):? (.*)$/i.exec(t))) return cxPlain(m[1]) + ' for ' + m[2] + ': ' + cxDetail(m[3]);
            if ((m = /^(invoice|credit note) (\S+?):? (.*)$/i.exec(t)) && /^#/.test(m[2])) {
                return cxPlain(m[1]) + ' ' + m[2].replace(/:$/, '') + ': ' + cxDetail(m[3]);
            }
            if ((m = /^contact[ ](.*) failed: (.*)$/i.exec(t))) return 'The contact ' + m[1] + ' could not be created. ' + cxDetail(m[2]);
            const plain = cxDetail(t);
            return aborted ? 'It stopped before writing anything. ' + plain : plain;
        }
        /* Why a document came out as it did, when the word alone does not
           say; '' when it does. Amounts are left out: the paid figure is
           the invoice's total with VAT, and beside a lines total before tax
           it read as a disagreement. */
        function cxWhy(d, dry) {
            const raw = String((d && d.message) || '');
            const credit = d && d.kind === 'creditnote';
            let m;
            if (d.action === 'blocked' && (m = /^Xero doc is[ ](\w+)(?:[ ]with[ ]([\d.]+) paid\/allocated)?/i.exec(raw))) {
                const st = m[1].toUpperCase();
                if (st === 'VOIDED' || st === 'DELETED') return (st === 'VOIDED' ? 'Voided' : 'Deleted') + ' in Xero, so it is not rewritten.';
                const word = credit ? (st === 'PAID' ? 'Allocated' : 'Partly allocated') : (st === 'PAID' ? 'Paid' : 'Partly paid');
                return word + ' in Xero, so it is not rewritten. To change it, remove the '
                    + (credit ? 'allocation' : 'payment') + ' in Xero first.';
            }
            if ((m = /^No[ ](invoice|credit note) produced[:\s,\u2012-\u2015-]+(.*)$/i.exec(raw))) {
                const why = m[2].trim();
                if (/customer not matched in Xero|no matching Xero contact/i.test(why)) {
                    return 'The customer is not a contact in Xero yet. A review and Send to Xero creates it; check this order again after that.';
                }
                if (/contact is archived/i.test(why)) return 'The customer’s contact is archived in Xero. Restore it there, then check this order again.';
                const c = /^cancelled[ ](\d{4}-\d{2}-\d{2})/i.exec(why);
                if (c) return 'Cancelled on ' + fmtDate(c[1]) + ', and a cancelled order gets no invoice.';
                return cxEnd(cxPlain(why));
            }
            if (/VOIDED with no refunds/i.test(raw)) return 'The order was voided and nothing was refunded, so there is nothing to send.';
            if (d.action === 'unchanged' && /^No change since last sync\.?$/i.test(raw.trim())) return 'Nothing has changed since it was sent.';
            if (d.action === 'unchanged' && (m = /^Already in Xero as[ ](\S+) for the same amount/i.exec(raw))) {
                return 'As ' + m[1] + ', for the same amount, so it is kept as it is.';
            }
            if ((m = /^(?:Would update|Updated) (\S+) in place/i.exec(raw))) return (dry ? 'Rewrites ' : 'Rewrote ') + m[1] + ' in place.';
            return cxDetail(raw);
        }
        /* A check's details as table rows: one per document, one more for an
           order that stopped part way (its documents so far are kept, and
           so is its error: the connector returns both), and one for an
           order with no document at all. Every count, tab and page on the
           page is in these rows, so none of them can disagree. */
        function cxEntries(details) {
            const out = [];
            (details || []).forEach(r => {
                const docs = r.docs || [];
                docs.forEach(d => out.push({ r: r, d: d, g: cxGroup(d), mis: !!cxMismatch(d) }));
                if (r.error && docs.length) out.push({ r: r, stop: true, g: 'attention' });
                if (!docs.length) out.push({ r: r, unread: true, g: 'unread' });
            });
            return out;
        }
        function cxTally(details) {
            const n = { write: 0, create: 0, update: 0, unchanged: 0, alone: 0, locked: 0, nothing: 0,
                        attention: 0, unread: 0, rows: 0, docs: 0, mismatch: 0 };
            cxEntries(details).forEach(e => {
                n.rows++; n[e.g]++;
                if (!e.d) return;
                n.docs++;
                if (e.mis) n.mismatch++;
                const k = cxKind(e.d);
                if (k === 'created') n.create++;
                if (k === 'updated') n.update++;
                if (k === 'locked') n.locked++;
                if (k === 'nothing') n.nothing++;
            });
            return n;
        }
        function cxList(bits) { return bits.length > 1 ? bits.slice(0, -1).join(', ') + ' and ' + bits[bits.length - 1] : (bits[0] || ''); }
        function cxTallySentence(n, dry) {
            const was = (k) => (k === 1 ? ' was' : ' were');
            const isAre = (k) => (k === 1 ? ' is' : ' are');
            const bits = [];
            if (n.create) bits.push(n.create + (dry ? ' would be created' : was(n.create) + ' created'));
            if (n.update) bits.push(n.update + (dry ? ' would be rewritten in place' : was(n.update) + ' rewritten in place'));
            if (n.unchanged) bits.push(n.unchanged + isAre(n.unchanged) + ' already in Xero');
            if (n.locked) bits.push(n.locked + isAre(n.locked) + ' paid or closed in Xero, so left alone');
            if (n.nothing) bits.push(n.nothing + (n.nothing === 1 ? ' has' : ' have') + ' nothing to send');
            if (n.attention) bits.push(n.attention + (n.attention === 1 ? ' needs' : ' need') + ' attention (each row says why)');
            if (!bits.length) return '';
            return (n.write || !dry ? '' : 'Nothing would be written: ') + cxList(bits) + '.';
        }
        /* One order's documents in a sentence of words, not numerals: 'The
           invoice would be created and the credit note is already in Xero.' */
        function cxOneSentence(docs, dry) {
            const PH = { created: dry ? 'would be created' : 'was created', updated: dry ? 'would be rewritten in place' : 'was rewritten in place',
                unchanged: 'is already in Xero', locked: 'is paid or closed in Xero, so left alone', nothing: 'has nothing to send',
                blocked: dry ? 'cannot be sent yet' : 'was not sent', quarantined: dry ? 'would be quarantined' : 'was quarantined', failed: 'failed' };
            const plural = (ph) => ph.replace(/^is /, 'are ').replace(/^was /, 'were ').replace(/^has /, 'have ');
            const order = [], by = {};
            docs.forEach(d => { const k = cxKind(d); if (!by[k]) { by[k] = []; order.push(k); } by[k].push(d.kind === 'creditnote' ? 'credit note' : 'invoice'); });
            const NUM = ['', 'one', 'two', 'three', 'four', 'five', 'six'];
            /* 'the credit note' only when the order has one: with two, each
               clause would name 'the credit note' and mean a different one. */
            const total = {}; docs.forEach(d => { const w = d.kind === 'creditnote' ? 'credit note' : 'invoice'; total[w] = (total[w] || 0) + 1; });
            const clause = order.map(k => {
                const kinds = {}; by[k].forEach(w => { kinds[w] = (kinds[w] || 0) + 1; });
                const names = Object.keys(kinds).map(w => kinds[w] === 1 ? (total[w] > 1 ? 'one ' : 'the ') + w : (NUM[kinds[w]] || kinds[w]) + ' ' + w + 's');
                return cxList(names) + ' ' + (by[k].length > 1 ? plural(PH[k]) : PH[k]);
            });
            const t = cxList(clause) + '.';
            return t.charAt(0).toUpperCase() + t.slice(1);
        }
        /* The rows as one table: the order named on its first row (again at
           the top of a page it continues onto), the document, what happens
           to it in words, the amount, and the document itself when the
           connector handed it back. Shared by the one-order check and the
           tag check, so a document reads the same in both. It used to be a
           box per order and a box per document inside a tile inside the
           card, which is how a tag of 62 orders became a column 10,000px
           tall inside a 444px tile. */
        function connDocTable(entries, dry, withOrder) {
            /* After a send there is no document to open and no amount: the
               connector attaches the document on a check only. Two empty
               columns down every row said nothing. The Open column has a name
               for a screen reader and none on screen, where its buttons say
               what they are. */
            const withDoc = entries.some(e => e.d && e.d.preview);
            const kt = dataTable((withOrder ? ['Order'] : []).concat(['Document', 'Outcome'])
                .concat(withDoc ? [['Lines total', 'num'], el('span', 'sr-only', 'Document window')] : []),
                { cls: 'cx-docs' + (withOrder ? '' : ' cx-one') });
            /* An order with a document out against Shopify goes first, its
               documents kept together, and within an order (one order's check
               included) that document leads. */
            const misFirst = new Set(entries.filter(e => e.mis).map(e => e.r));
            if (misFirst.size) {
                const pos = new Map(); entries.forEach((e, i) => { if (!pos.has(e.r)) pos.set(e.r, i); });
                entries = entries.map((e, i) => [e, i]).sort((a, b) =>
                    (misFirst.has(b[0].r) - misFirst.has(a[0].r)) || (pos.get(a[0].r) - pos.get(b[0].r))
                    || ((b[0].mis ? 1 : 0) - (a[0].mis ? 1 : 0)) || (a[1] - b[1])).map(x => x[0]);
            }
            let prev = null;
            entries.forEach(e => {
                const r = e.r, first = r !== prev; prev = r;
                /* Grouped under its order only in a list of orders: one
                   order's documents are separate rows, each with its rule. */
                const tr = el('tr', (withOrder && !first) ? 'cx-more' : null);
                if (withOrder) tr.append(el('td', 'cx-ord', first ? (r.order || '') : ''));
                const kc = el('td', 'cx-kind');
                const oc = el('td', 'cx-out');
                const why = (t) => { if (t) oc.append(el('div', 'cx-why', t)); };
                if (e.unread) {
                    oc.append(el('span', 'lbl-chip bad', r.found === false ? 'Not in Shopify' : dry ? 'Not checked' : 'Not sent'));
                    why(r.error ? cxDetail(r.error) : (r.found === false ? 'No order by that number.' : ''));
                } else if (e.stop) {
                    oc.append(el('span', 'lbl-chip bad', dry ? 'Stopped part way' : 'Not finished'));
                    why(cxDetail(r.error));
                } else {
                    const d = e.d, p = d.preview || null;
                    kc.append(el('div', null, d.kind === 'creditnote' ? 'Credit note' : 'Invoice'));
                    if (p && p.lines && p.lines.length) kc.append(el('div', 'cx-why', p.lines.length + (p.lines.length === 1 ? ' line' : ' lines')));
                    const w = CX_DOC_WORDS[cxKind(d)];
                    const rec = dry ? cxMismatch(d) : null;
                    if (rec) {
                        const cur = (p && p.currency) || 'GBP';
                        oc.append(el('span', 'lbl-chip bad', money(Math.abs(Number(rec.diff) || 0), cur, 2) + ' out'));
                        why('Shopify says ' + money(Number(rec.expected) || 0, cur, 2) + ' and this document comes to '
                            + money(Number(rec.computed) || 0, cur, 2) + '. It would be sent as it stands.');
                    } else {
                        oc.append(el('span', 'lbl-chip ' + (dry ? w[2] : w[3]), dry ? w[0] : w[1]));
                        why(cxWhy(d, dry));
                    }
                }
                tr.append(kc, oc);
                if (withDoc) {
                    const p = e.d && e.d.preview;
                    tr.append(el('td', 'num', p && typeof p.lineTotal === 'number' ? money(p.lineTotal, p.currency || 'GBP', 2) : ''));
                    const act = el('td', 'cx-act');
                    /* A check exists to be READ. A preview means the connector
                       handed back the document itself; without one there is
                       nothing to open, and offering it would open an empty
                       window. */
                    if (p) {
                        const d = e.d;
                        const open = textButton('Open');
                        open.title = 'See the ' + (d.kind === 'creditnote' ? 'credit note' : 'invoice');
                        open.setAttribute('aria-label', open.title + (r.order ? ' for ' + r.order : ''));
                        open.onclick = () => connDocModal(d);
                        act.append(open);
                    }
                    tr.append(act);
                }
                kt.add(tr);
            });
            return kt.wrap;
        }
        /* A tag's check arms exactly that tag, and a send spends it: the
           results stay on screen to be read, but sending them again needs a
           fresh check. */
        function connTagArmed(tag) {
            return !!(connTagCheck && connTagCheck.tag && !connTagCheck.sent
                      && connTagCheck.tag === String(tag || '').trim());
        }
        let connBusy = '';        // 'review' | 'send' | 'retry' while one is in flight
        let connWatch = 0;

        async function connOp(body) { return api('/api/connector', body); }

        async function showConnectorView() {
            if (connCache) { renderConnector(); }
            await refreshConnector();
        }
        async function refreshConnector() {
            try {
                const st = await connOp({ op: 'status' });
                connCache = st;
                if (st.available && !st.error) {
                    try { connRuns = (await connOp({ op: 'runs' })).data || []; } catch (e) { /* runs are a nicety */ }
                    /* Auto Run's state and the health verdict come from the
                       service, never from anything remembered here: a toggle
                       that shows what this tab last set would say ON after a
                       redeploy that started nothing. */
                    try { connAuto = (await connOp({ op: 'autorun' })).data || null; } catch (e) { connAuto = null; }
                    try { connHealth = (await connOp({ op: 'health' })).data || null; } catch (e) { connHealth = null; }
                    try { connSettings = (await connOp({ op: 'settings' })).data || null; } catch (e) { connSettings = null; }
                    /* Read here, once, not on every repaint: a filter click or
                       a page turn refetched it and the card flashed empty. */
                    try { connQuar = (st.data && st.data.quarantineCount) ? ((await connOp({ op: 'quarantine' })).data || []) : []; }
                    catch (e) { connQuar = false; }
                }
            } catch (e) { connCache = { available: true, error: e.message }; }
            if (document.querySelector('#view-connector.active')) renderConnector();
        }
        /* While the service reports running, watch it; when it stops, the run
           that just finished is the news, so refresh and repaint once. */
        function connStartWatch() {
            if (connWatch) return;
            connWatch = setInterval(async () => {
                if (!document.querySelector('#view-connector.active')) { clearInterval(connWatch); connWatch = 0; return; }
                let st = null;
                try { st = await connOp({ op: 'status' }); } catch (e) { return; }
                connCache = st;
                const running = st.data && st.data.running;
                if (!running) {
                    clearInterval(connWatch); connWatch = 0;
                    try { connRuns = (await connOp({ op: 'runs' })).data || []; } catch (e) {}
                    const last = (connRuns || [])[0];
                    if (connBusy === 'review' && last && last.dryRun) connReview = last;
                    if (connBusy === 'send') connReview = null;   // spent: the next send needs a fresh review
                    /* A tag job reports through the status, not the run list:
                       it is a list of single sends, not a sync. */
                    if (connTagBusy) {
                        const job = st.data && st.data.tagJob;
                        connTagCheck = job
                            ? { tag: job.tag, sent: !job.dryRun,
                                data: job.result || { error: job.error || 'The connector stopped before it finished the tag.' } }
                            : { tag: (connTagCheck || {}).tag || connTagPending, sent: connTagBusy === 'send',
                                data: { error: 'The connector reported no tag job. Check the tag again.' } };
                        connTagBusy = ''; connTagPending = '';
                    }
                    /* The run that just finished is what the health box and
                       Auto Run judge: read them again with the runs, or the
                       box went on about 5 Sep beside a review from today. */
                    try { connHealth = (await connOp({ op: 'health' })).data || null; } catch (e) {}
                    try { connAuto = (await connOp({ op: 'autorun' })).data || null; } catch (e) {}
                    try { connQuar = st.data && st.data.quarantineCount ? ((await connOp({ op: 'quarantine' })).data || []) : []; } catch (e) { connQuar = false; }
                    connBusy = '';
                }
                renderConnector();
            }, 2500);
        }

        function connCounts(res, kind) {
            const c = (res || {})[kind] || {};
            const skipped = Object.keys(c).filter(k => k.indexOf('skipped') === 0)
                .reduce((n, k) => n + (c[k] || 0), 0);
            return { created: c.created || 0, updated: c.updated || 0, failed: c.failed || 0,
                     quarantined: c.quarantined || 0, skipped: skipped };
        }
        /* A review's counts in the outcome words of the document tables.
           null where the outcome does not exist for that kind: a contact is
           never quarantined, and nothing is 'sent' for a test order's contact. */
        function cxReviewCounts(res, kind) {
            const c = (res || {})[kind] || {};
            const n = (k) => Number(c[k]) || 0;
            if (kind === 'contacts') {
                return { create: n('created'), update: null, inXero: n('skippedExisting') + n('skippedSynced'),
                         noContact: null, nothing: null, voided: null, keptPaid: null, quarantined: null, failed: n('failed') };
            }
            if (kind === 'creditNotes') {
                return { create: n('created'), update: null, inXero: n('skippedSynced'), noContact: n('skippedNoContact'),
                         nothing: null, voided: null, keptPaid: null, quarantined: n('quarantined'), failed: n('failed') };
            }
            /* A void and an edit left alone are what Send would do too, and a
               table that left them out said nothing about either. */
            return { create: n('created'), update: n('updated'), inXero: n('skippedSynced') + n('skippedInXero'),
                     noContact: n('skippedNoContact'), nothing: n('skippedTest') + n('skippedCancelled'),
                     voided: n('voided'), keptPaid: n('updateBlocked'),
                     quarantined: n('quarantined'), failed: n('failed') };
        }
        function connIsAdmin() {
            return !teamMe || ({ master: 3, admin: 2 }[teamMe.role] || 0) >= 2;
        }
        /* Skills, notes and the store knowledge are read into every admin's
           answers, reports and drafts, so only an admin changes them; everyone
           reads them. The server is the real gate; this stops offering buttons
           it would refuse. */
        function canEditInstructions() {
            return !teamMe || ({ master: 3, admin: 2 }[teamMe.role] || 0) >= 2;
        }

