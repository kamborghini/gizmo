        /* ---------- the window part ----------
           Every window in the app is built here (docs/DESIGN.md, Windows), so
           every window behaves alike because one piece of code makes it, not
           because each copy was careful:
           - it is a dialog, modal, named by its own title;
           - a window holding work has an X named Close and, with its own
             answers (Save, Cancel, Done), no other way out: never Escape, never
             a click outside it, so a slip cannot lose what was typed. A
             question or notice answered by its own buttons has no X
             (x: false), and the yes/no question alone answers Escape
             (onEscape);
           - focus moves in as it opens, and back to what opened it as it
             closes: to that control's redrawn twin when the page was redrawn
             (data-focus-key), never to a field left long before;
           - Tab stays inside the window on top;
           - it closes through close() and nothing else, so the part always
             knows which window is on top.
           It builds the markup windows always had, with the same classes, so
           the stylesheet does not change. */
        const dialogStack = [];   // open windows, topmost last: { overlay, onEscape, opener }
        let dialogSeq = 0;
        const DIALOG_FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
        /* The last control focused outside every window: a click can open a
           window and leave focus on the page behind, or on nothing. */
        let focusOutside = null;
        document.addEventListener('focusin', (e) => {
            if (e.target && e.target.closest && !e.target.closest('.modal-overlay')) focusOutside = e.target;
        });
        /* Focus that left for nowhere (a tap elsewhere; on a phone a tap moves
           no focus) forgets that control: closing a window must not send focus
           back to a field left long before, which on an iPhone raises the
           keyboard. */
        document.addEventListener('focusout', (e) => {
            if (!e.relatedTarget && e.target === focusOutside) focusOutside = null;
        });
        /* The window on top. One removed some other way (which the page suite
           forbids) is forgotten rather than left to swallow the keys. */
        function dialogTop() {
            for (let i = dialogStack.length - 1; i >= 0; i--) {
                if (dialogStack[i].overlay.isConnected === false) dialogStack.splice(i, 1);
                else return dialogStack[i];
            }
            return null;
        }
        function dialogOpener(given) {
            if (given) return given;
            const now = document.activeElement;
            return now && now !== document.body ? now : focusOutside;
        }
        /* A window that focuses nothing of its own gets its X or, with no X,
           its first control. Two frames: a builder that focuses its own field
           does so in the first, and is left alone. */
        function dialogFocusIn(overlay) {
            requestAnimationFrame(() => requestAnimationFrame(() => {
                if (!overlay.isConnected || !overlay.classList.contains('show') || overlay.contains(document.activeElement)) return;
                const to = overlay.querySelector('.modal-head button[aria-label="Close"]')
                    || [...overlay.querySelectorAll(DIALOG_FOCUSABLE)].find(f => !f.disabled && f.getClientRects().length);
                if (to) to.focus();
            }));
        }
        /* Focus back to what opened the window, if nothing else has taken it.
           A page the window redrew as it closed (a CRM deal redraws the board)
           replaced that control: the new one carries the same data-focus-key,
           and focus goes there once it is drawn. */
        function dialogGiveBack(back, leaving) {
            if (!back || !back.focus) return;
            /* Lost: on nothing, on a control that is gone, or still inside the
               window that is leaving (a window hidden rather than removed keeps
               its X focused until the browser notices, a moment later). */
            const lost = () => !document.activeElement || document.activeElement === document.body
                || document.activeElement.isConnected === false || (!!leaving && leaving.contains(document.activeElement));
            if (back.isConnected) { if (lost()) back.focus(); return; }
            const key = back.dataset && back.dataset.focusKey;
            if (!key) return;
            let tries = 0;
            const look = () => {
                const twin = document.querySelector('[data-focus-key="' + CSS.escape(key) + '"]');
                if (twin) { if (lost()) twin.focus(); return; }
                if (++tries < 60) setTimeout(look, 50);
            };
            look();
        }
        function dialog(opts) {
            const overlay = el('div', 'modal-overlay show' + (opts.overlayClass ? ' ' + opts.overlayClass : ''));
            const modal = el('div', 'modal' + (opts.size ? ' ' + opts.size : ''));
            const head = el('div', 'modal-head');
            const heading = el('h3', null, opts.title);
            heading.id = 'dialog-title-' + (++dialogSeq);
            head.append(heading);
            let x = null;
            if (opts.x !== false) {
                x = iconButton(I.x, 'Close');
                head.append(x);
            }
            const body = el('div', 'modal-body' + (opts.bodyClass ? ' ' + opts.bodyClass : ''));
            modal.setAttribute('role', 'dialog');
            modal.setAttribute('aria-modal', 'true');
            modal.setAttribute('aria-labelledby', heading.id);
            modal.append(head, body);
            overlay.append(modal);
            let footEl = null;
            const foot = () => {
                if (!footEl) { footEl = el('div', 'modal-foot'); modal.append(footEl); }
                return footEl;
            };
            const rec = { overlay: overlay, onEscape: opts.onEscape || null, opener: dialogOpener(opts.opener) };
            let open = true;
            const close = () => {
                if (!open) return;
                open = false;
                overlay.remove();
                const at = dialogStack.indexOf(rec);
                if (at >= 0) dialogStack.splice(at, 1);
                /* What the window does as it closes comes first: a page it
                   redraws is redrawn before focus looks for its opener. */
                if (opts.onClose) opts.onClose();
                dialogGiveBack(rec.opener);
            };
            if (x) x.onclick = close;
            dialogStack.push(rec);
            document.body.append(overlay);
            if (x) x.focus(); else dialogFocusIn(overlay);
            return { overlay: overlay, modal: modal, head: head, heading: heading, x: x, body: body, foot: foot,
                     close: close, isTop: () => dialogTop() === rec };
        }
        /* The window written into the page (Settings) opens and closes by its
           show class rather than being built: the same stack, focus and fence. */
        function dialogShow(overlay) {
            if (dialogStack.some(r => r.overlay === overlay)) return;
            const rec = { overlay: overlay, onEscape: null, opener: dialogOpener() };
            overlay.classList.add('show');
            dialogStack.push(rec);
            dialogFocusIn(overlay);
        }
        function dialogHide(overlay) {
            overlay.classList.remove('show');
            const at = dialogStack.findIndex(r => r.overlay === overlay);
            if (at < 0) return;
            const rec = dialogStack.splice(at, 1)[0];
            dialogGiveBack(rec.opener, overlay);
        }
        document.addEventListener('keydown', (e) => {
            const top = dialogTop();
            if (!top) return;
            if (e.key === 'Escape') {
                if (top.onEscape) { e.stopPropagation(); top.onEscape(); }
                return;
            }
            if (e.key !== 'Tab') return;
            /* An open menu manages its own keys and closes on any outside
               press; the sign-in screen sits over everything and keeps a fence
               of its own (js/page-observers.js). */
            if (document.querySelector('.dmenu')) return;
            if ([...document.querySelectorAll('.auth-overlay')].some(o => o.getClientRects().length)) return;
            const focusables = [...top.overlay.querySelectorAll(DIALOG_FOCUSABLE)]
                .filter(f => !f.disabled && f.getClientRects().length);
            if (!focusables.length) return;
            const first = focusables[0], last = focusables[focusables.length - 1];
            if (!top.overlay.contains(document.activeElement)) { e.preventDefault(); first.focus(); return; }
            if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
            else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        });
        /* ---------- the window part end ---------- */
