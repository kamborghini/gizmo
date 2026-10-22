        /* ---- the clock: part-time accounts punch in and out here ---- */
        let clockState = null, clockTimer = null;
        function fmtDur(secs) {
            const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60);
            return h ? h + 'h ' + String(m).padStart(2, '0') + 'm' : m + 'm';
        }
        function paintClock() {
            const b = $('clock-btn');
            if (!clockState || !clockState.monitored) { b.style.display = 'none'; return; }
            b.style.display = '';
            if (clockState.clocked_in) {
                const secs = clockState.session.secs
                    + Math.floor((Date.now() - clockState.at) / 1000);
                b.textContent = 'Clock out · ' + fmtDur(secs);
                b.classList.add('btn-primary');
            } else {
                b.textContent = 'Clock in';
                b.classList.remove('btn-primary');
            }
        }
        async function clockBoot() {
            try {
                const r = await api('/api/work/status', {});
                clockState = r; clockState.at = Date.now();
                paintClock();
                if (clockTimer) clearInterval(clockTimer);
                clockTimer = setInterval(paintClock, 30000);
            } catch (e) { /* the button stays as it is */ }
        }
        $('clock-btn').onclick = async () => {
            const b = $('clock-btn'); b.disabled = true;
            try {
                await api('/api/work/clock', { op: clockState && clockState.clocked_in ? 'out' : 'in' });
                await clockBoot();
                addToast(clockState.clocked_in ? 'Clocked in. Your work is now being recorded '
                    + 'against this session.' : 'Clocked out.');
            } catch (e) { toastError(e.message); }
            b.disabled = false;
        };
        $('settings-close').innerHTML = I.x;
        // Re-evaluate the PDF button after a report finishes loading (setView runs before
        // the data arrives, so the button would otherwise stay hidden until you switch tabs).
        function syncPrintBtn() {
            const av = document.querySelector('.view.active');
            const v = av ? av.id.replace('view-', '') : '';
            const b = $('print-btn'); if (!b) return;
            b.style.display = (v === 'chat' && printableCache(v)) ? '' : 'none';
        }
        // Which cache backs the printable report for a view (null = nothing to print yet).
        function printableCache(v) {
            /* A conversation prints as it reads, dated by its last answer. */
            if (v === 'chat') { const c = active(); return c && c.turns.length ? { at: c.updated || c.ts || Date.now() } : null; }
            return null;
        }
        $('print-btn').innerHTML = I.download;
        $('print-btn').onclick = function () {
            const av = document.querySelector('.view.active');
            const v = av ? av.id.replace('view-', '') : '';
            let label = 'Report';
            if (v === 'chat' && active()) label = 'Chat: ' + (active().title || 'Conversation');
            // Stamp when the DATA was computed, not when the PDF was printed. The
            // on-screen "Updated ..." line is hidden in print, so this is the only
            // freshness signal the reader gets.
            const cached = printableCache(v);
            const when = cached && cached.at ? new Date(cached.at) : null;
            $('print-meta').textContent = label + '   ·   ' + (when
                ? 'Data as of ' + fmtDate(when.toISOString()) + ' ' + londonHM(when.toISOString())
                : new Date().toLocaleDateString('en-GB', { year: 'numeric', month: 'long', day: 'numeric' }));
            setTimeout(function () { window.print(); }, 30);
        };

