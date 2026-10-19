        /* ---------- Forecast tab ----------
           The models do not run here. A second Railway service runs them each
           night and posts one JSON document to /hooks/forecast/results; this
           tab reads that document back through /api/forecast and draws it. */
        let forecastCache = null, forecastScenario = '';
        async function showForecastView() { renderForecast(); refreshForecast(); }
        async function refreshForecast() {
            try { forecastCache = await api('/api/forecast', {}); }
            catch (e) { forecastCache = { error: e.message }; }
            if (document.querySelector('#view-forecast.active')) renderForecast();
        }
        const fcMoney = (v) => (v == null || isNaN(v)) ? 'n/a' : money(v, 'GBP', 0);
        const fcPct = (v) => (v == null || isNaN(v)) ? 'n/a' : ((v > 0 ? '+' : '') + (v * 100).toFixed(1) + '%');
        const fcMonth = (m) => m ? (MONTH_ABBR[(+m.slice(5, 7)) - 1] + ' ' + m.slice(0, 4)) : '';
        const fcMonthName = (m) => m ? MONTH_NAMES[(+m.slice(5, 7)) - 1] : '';
        const fcDay = (iso) => { const d = new Date(iso); return d.getDate() + ' ' + MONTH_ABBR[d.getMonth()]; };
        /* Sentence case, like every other chip in the app: the run's words
           ('in use', 'below buffer') arrive lower case. */
        const fcChip = (kind, text) => el('span', 'lbl-chip ' + (kind || 'note'), text ? text.charAt(0).toUpperCase() + text.slice(1) : text);
        const FC_VERDICT = { 'on track': 'made', underrun: 'bad', overrun: 'note' };
        const FC_RISK = { secure: 'made', watch: 'warn', high: 'bad', closed: 'note' };
        /* What the run's codes are called on the screen. */
        const FC_VERDICT_WORDS = { 'on track': 'On track', underrun: 'Under plan', overrun: 'Over plan' };
        const FC_BASIS = { actual: 'Actual', 'actual_to_date + forecast': 'Taken so far + forecast',
                           forecast: 'Forecast', 'forecast (partial) + extrapolated': 'Forecast + extrapolated',
                           extrapolated: 'Extrapolated' };
        const fcSentence = (s) => s ? s.charAt(0).toUpperCase() + s.slice(1) : '';
        function fcTable(head, rows, right) {
            const wrap = el('div', 'ktable-wrap'); const tbl = el('table', 'ktable');
            const thead = el('thead'); const hr = el('tr');
            head.forEach((h, i) => {
                const th = el('th');
                if (h instanceof Node) th.append(h); else th.textContent = h == null ? '' : String(h);
                if (right && right[i]) th.classList.add('num'); hr.append(th);
            });
            thead.append(hr); tbl.append(thead);
            const tb = el('tbody');
            rows.forEach(cells => {
                const tr = el('tr');
                cells.forEach((c, i) => {
                    const td = el('td');
                    if (c instanceof Node) td.append(c); else td.textContent = c == null ? '' : String(c);
                    if (right && right[i]) td.classList.add('num');
                    tr.append(td);
                });
                tb.append(tr);
            });
            tbl.append(tb); wrap.append(tbl); return wrap;
        }
        function forecastUploadButton() {
            const b = el('button', 'btn', 'Upload workbook'); b.prepend(ico(I.upload));
            const inp = document.createElement('input'); inp.type = 'file'; inp.accept = '.xlsx'; inp.style.display = 'none';
            inp.onchange = async () => {
                const f = inp.files && inp.files[0]; if (!f) return;
                if (f.size > 8 * 1024 * 1024) { toastError('That workbook is over the 8 MB cap.'); return; }
                setBusy(b, true);
                try {
                    const bytes = new Uint8Array(await f.arrayBuffer()); let bin = '';
                    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
                    await api('/api/forecast/workbook', { name: f.name, data_b64: btoa(bin) });
                    toastOk('Workbook uploaded. The next nightly run reads it.');
                    await refreshForecast();
                } catch (e) { toastError(e.message); }
                finally { setBusy(b, false); inp.value = ''; }
            };
            b.onclick = () => inp.click(); b.append(inp); return b;
        }
        /* A failed run, said as a sentence with the service's own words held
           back behind a disclosure. A chip and a bare text node straight in a
           card stretched the chip into a full-width pink bar and put the raw
           Python exception flush against the border. */
        function fcFailedRunCard(err, asOf) {
            const card = el('div', 'card');
            const head = el('div', 'card-head');
            head.append(el('h3', 'card-title', 'The last run failed'));
            head.append(el('p', 'card-desc', 'The run on ' + fmtDate(err.at) + ' did not finish'
                + (asOf ? ', so this page shows the run as of ' + fmtDate(asOf) + '.' : '.')));
            const act = el('div', 'card-act'); act.append(fcChip('bad', 'Failed')); head.append(act);
            card.append(head);
            if (err.error) {
                const det = el('details', 'know-body');
                det.append(el('summary', null, 'What the forecasting service reported'));
                det.append(el('pre', 'setup-code fc-err', String(err.error)));
                card.append(det);
            }
            return card;
        }
        function forecastSetupCard(c) {
            const card = el('div', 'card');
            const head = el('div', 'card-title', 'No forecast yet');
            /* The steps name a setting and a file, so they wait behind the info
               button for the admin who needs them, word for word (the mix, 8.3). */
            if (!c.hook_configured) head.append(infoButton('Setting up the forecast', { title: 'Setting up the forecast',
                body: 'Set FORECAST_INGEST_TOKEN on Reactor and, with the same value, on the forecasting service; the service then posts here each night. The setup is in forecast/README.md.' }));
            card.append(head);
            if (c.hook_configured) card.append(el('p', 'card-sub', 'The first run lands after 03:00.'));
            if (c.last_error) card.append(el('p', 'card-sub', 'The last run, on ' + fmtDate(c.last_error.at)
                + ', did not finish. What the service reported: ' + String(c.last_error.error).slice(0, 300)));
            const wb = c.workbook || {};
            card.append(el('p', 'card-sub', wb.name ? ('Workbook on file: ' + wb.name + ', uploaded ' + fmtDate(wb.uploaded_at) + (wb.by ? ' by ' + wb.by : '') + '.')
                : (c.can_upload ? 'No cash flow workbook yet. Upload one above.' : 'No cash flow workbook yet.')));
            return card;
        }
        /* How much of the method table to put on screen. Twelve rows of models
           is a lot to land on someone who opened the page to read one number,
           so the default is the three that are quoted, and the choice is
           remembered per person. "Just the headline" is a single row: the
           method that leads, with the plan beside it. */
        const LS_FCROWS = 'sc_fc_rows_v1';
        const FC_ROWS = [['one', 'Just the headline'], ['three', 'The three quoted'], ['all', 'Every method']];
        function fcRowsMode() {
            try { const v = localStorage.getItem(LS_FCROWS); return FC_ROWS.some(r => r[0] === v) ? v : 'three'; }
            catch (e) { return 'three'; }
        }
        function setFcRowsMode(v) {
            try { localStorage.setItem(LS_FCROWS, v); } catch (e) {}
            renderForecast(); fcRepaintPage();
        }
        /* ---------- the sanity panel ----------
           Five plain forecasts of the monthly total, beside the big model.
           They exist because the big one forecast October, the best month of
           the year, at a quarter of what October has ever been: one number
           nobody can check is worth less than five that disagree in the open.

           The table is ordered by what each model scored on this shop's own
           history, best first, and the one that earned it is marked. Where
           they spread widely, that spread IS the answer - two Decembers of
           53,648 and 15,444 cannot produce a confident December. */
        /* ---------- the graph, at whatever scale is being asked for ----------
           One chart, six ranges. Short ranges are drawn day by day, because
           "how is this week going" is a daily question; long ones month by
           month, because a year of days is a picket fence. The monthly view
           also carries what was PREDICTED for each closed month, so the gap
           between what was expected and what came in is on the same picture
           rather than in a different table. */
        /* Which sources to draw against each other. Removing the manual
           algorithm SELECTOR was right - nobody should have to pick which one
           runs. Removing the ability to COMPARE them was not: seeing four
           lines diverge over the autumn is the whole argument for trusting the
           one that leads. Empty means just the leader. */
        const LS_FCCMP = 'sc_fc_compare_v1';
        /* Three at most, one per colour slot (--c-method-1 to 3). A method
           keeps its slot, and so its colour, while it stays picked: taking one
           off leaves its slot empty rather than shifting the others along,
           because a line that changes colour when a different line goes reads
           as a different method. A list saved before the cap keeps its first
           three. */
        const FC_CMP_MAX = 3;
        const FC_METHOD = ['--c-method-1', '--c-method-2', '--c-method-3'];
        function fcCompare() {
            let set;
            try { set = JSON.parse(localStorage.getItem(LS_FCCMP)) || []; } catch (e) { set = []; }
            return Array.isArray(set) ? set.slice(0, FC_CMP_MAX).map(n => (typeof n === 'string' ? n : null)) : [];
        }
        function toggleFcCompare(name) {
            const set = fcCompare();
            const i = set.indexOf(name);
            if (i >= 0) set[i] = null;
            else {
                const gap = set.indexOf(null);
                if (gap >= 0) set[gap] = name; else if (set.length < FC_CMP_MAX) set.push(name);
            }
            while (set.length && set[set.length - 1] == null) set.pop();
            try { localStorage.setItem(LS_FCCMP, JSON.stringify(set)); } catch (e) {}
            renderForecast();
        }
        function clearFcCompare() { try { localStorage.removeItem(LS_FCCMP); } catch (e) {} renderForecast(); }
        /* Compare methods (the mix): a switch, off unless the reader has turned
           it on. The picks above are kept while it is off. */
        const LS_FCCMPON = 'sc_fc_cmp_on_v1';
        function fcCompareOn() { try { return localStorage.getItem(LS_FCCMPON) === '1'; } catch (e) { return false; } }
        function setFcCompareOn(v) {
            try { if (v) localStorage.setItem(LS_FCCMPON, '1'); else localStorage.removeItem(LS_FCCMPON); } catch (e) {}
            renderForecast();
        }
        const LS_FCRANGE = 'sc_fc_range_v1';
        const LS_FCFROM = 'sc_fc_from_v1', LS_FCTO = 'sc_fc_to_v1';
        /* The words Cameron approved for the ranges (the mix, 2026-10-06). */
        const FC_RANGES = [['today', 'Today'], ['week', 'Week'], ['month', 'Month'],
                           ['q', '3 months'], ['year', '12 months'],
                           ['ahead', 'Months ahead'], ['custom', 'Custom range']];
        function fcRange() {
            try { const v = localStorage.getItem(LS_FCRANGE); return FC_RANGES.some(r => r[0] === v) ? v : 'month'; }
            catch (e) { return 'month'; }
        }
        function setFcRange(v) { try { localStorage.setItem(LS_FCRANGE, v); } catch (e) {} renderForecast(); }
        function fcCustom() {
            try { return [localStorage.getItem(LS_FCFROM) || '', localStorage.getItem(LS_FCTO) || '']; }
            catch (e) { return ['', '']; }
        }
        function setFcCustom(from, to) {
            try { localStorage.setItem(LS_FCFROM, from); localStorage.setItem(LS_FCTO, to); } catch (e) {}
            renderForecast();
        }
        /* The LOCAL calendar day. toISOString() is UTC, and the ranges build
           their dates at local midnight, which in British Summer Time is
           23:00 UTC the day before: Today excluded today, and This month on
           the 1st showed last month. */
        const fcISO = (d) => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0')
            + '-' + String(d.getDate()).padStart(2, '0');
        /* These cards each carry their own section title, which is right when
           they sit on the page and wrong inside a window whose title already
           says it. Reuse the card, drop the duplicated heading. */
        function fcUntitled(node) {
            const t = node.querySelector(':scope > .section-title');
            if (t) t.remove();
            /* And drop the card's own frame: inside a window it made three
               nested boxes (window, card, table), while the Month by month
               and Cash windows beside it hold their table directly. */
            node.querySelectorAll(':scope > .card').forEach(c => {
                const body = el('div', 'fc-drawer-body');
                while (c.firstChild) body.append(c.firstChild);
                c.replaceWith(body);
            });
            return node;
        }
        /* The run's own words are codes: "underrun by -11.2%" said the miss
           twice, "overrun by +72.3%" the sign twice, and "risk watch" or "risk
           secure" put an enum on the screen. Said here as a sentence: what is
           expected, against which plan, by how much, and what the likely range
           says about it. The percentage is the run's to one decimal, the same
           figure the month table prints. */
        const FC_RISK_WORDS = {
            high: 'even the top of the likely range falls short of it',
            watch: 'the plan is still inside the likely range',
            secure: 'even the bottom of the likely range clears it',
        };
        function fcAlertText(a) {
            if (a.kind === 'cash') {
                const what = a.verdict === 'negative working capital'
                    ? 'Working capital goes below zero' : 'Working capital drops below the cash buffer';
                return what + ', to ' + fcMoney(a.working_capital) + '.';
            }
            const pct = Math.abs(a.gap_pct || 0).toFixed(1) + '%';
            const side = (a.gap_pct || 0) < 0 ? ' short' : ' ahead';
            const risk = FC_RISK_WORDS[a.risk];
            return 'Expected ' + fcMoney(a.projected) + ' against a plan of ' + fcMoney(a.target) + ', '
                + pct + side + (risk ? '; ' + risk : '') + '.';
        }
        /* Which two matter most: cash before sales, then the size of the
           SHORTFALL. Not the size of the gap - Math.abs made a month that beat
           its plan by 71% outrank a month that missed by 20, so the section
           headed "worth looking at" led with the best news on the page. Coming
           in over plan is not a miss, so it scores nothing and only appears
           when there is nothing worse to show. */
        function fcAlertWeight(a) {
            if (a.kind === 'cash') return 1000 + Math.abs(a.gap_pct || 0);
            const gap = a.gap_pct || 0;
            if (gap > 0) return 0;                       // over plan: not a problem
            const risk = a.risk === 'high' ? 100 : a.risk === 'watch' ? 50 : 0;
            return risk + Math.abs(gap);
        }

        /* ---------- WORTH LOOKING AT ----------
           The months that matter (the mix, spec 8.1 item 5): a table of the
           month, what is expected, the plan, the change chip, the likely range
           drawn small with the plan as a tick, and the outlook in the words
           Cameron approved. Cash alerts stay sentences above it: they are
           warnings, and a warning is never cut to a code. */
        function fcOutlook(a) {
            if (a.risk === 'secure') return 'Safely ahead';
            if (a.risk === 'watch') return (a.projected || 0) >= (a.target || 0) ? 'Likely ahead' : 'Likely behind';
            /* The service raises an alert for every high-risk month whatever its
               verdict, so a high one is behind: its codes are not words. */
            if (a.risk === 'high') return 'Likely behind';
            return FC_VERDICT_WORDS[a.verdict] || fcSentence(a.verdict || '');
        }
        function fcWorthTable(latest, list) {
            const wrap = el('div', 'fc-wl-wrap');
            const t = el('div', 'fc-wl');
            t.setAttribute('role', 'table'); t.setAttribute('aria-label', 'Worth looking at');
            const rowOf = (cells, head) => {
                const r = el('div', head ? 'h' : 'r'); r.setAttribute('role', 'row');
                cells.forEach(([c, cls]) => {
                    const s = el('span', cls); s.setAttribute('role', head ? 'columnheader' : 'cell');
                    if (c instanceof Node) s.append(c); else s.textContent = c == null ? '' : String(c);
                    r.append(s);
                });
                return r;
            };
            t.append(rowOf([['Month', 'c-mo'], ['Expected', 'c-v ra'], ['Plan', 'c-plan ra'], ['Against plan', 'c-chip ra'],
                            ['Likely range', 'c-rg'], ['Outlook', 'c-ol']], true));
            const monthOf = (a) => (latest.monthly || []).find(x => x.month === a.month) || {};
            /* One scale for every row, so the bars can be read against each other. */
            const d = bandDomain([].concat(...list.map(a => { const m = monthOf(a); return [m.p10, m.p90, a.projected, a.target]; })));
            list.forEach(a => {
                const m = monthOf(a);
                const gap = (a.target && a.projected != null) ? (a.projected - a.target) / a.target : null;
                const tr = gap == null ? null : Math.abs(gap) <= 0.10 ? 'flat' : (gap > 0 ? 'up' : 'down');
                const chip = gap == null ? '' : changeChip(tr, Math.abs(gap * 100).toFixed(1) + '%', deltaTone('expected', tr));
                const rg = el('span', 'rg'); rg.setAttribute('role', 'img');
                rg.setAttribute('aria-label', 'Likely ' + fcMoney(m.p10) + ' to ' + fcMoney(m.p90) + ', plan ' + fcMoney(a.target));
                if (m.p10 != null && m.p90 != null) {
                    rg.style.setProperty('--at-lo', bandPct(m.p10, d)); rg.style.setProperty('--at-hi', bandPct(m.p90, d));
                    rg.append(el('i', 'rg-fill'));
                }
                if (a.target != null) { rg.style.setProperty('--at-plan', bandPct(a.target, d)); rg.append(el('i', 'rg-plan')); }
                if (a.projected != null) { rg.style.setProperty('--at-exp', bandPct(a.projected, d)); rg.append(el('i', 'rg-exp')); }
                t.append(rowOf([[fcMonth(a.month), 'c-mo'], [fcMoney(a.projected), 'c-v ra'], [fcMoney(a.target), 'c-plan ra'],
                                [chip, 'c-chip ra'], [rg, 'c-rg'], [fcOutlook(a), 'c-ol']]));
            });
            wrap.append(t);
            return wrap;
        }
        function fcWorthCard(latest, sc, al) {
            const box = el('section', 'fc-worth');
            const sales = al.filter(a => a.kind !== 'cash');
            const cash = al.filter(a => a.kind === 'cash');
            const head = el('div', 'section-title', 'Worth looking at');
            if (sales.length) { const n = el('span', 'cnt', String(sales.length)); n.append(el('span', 'sr-only', sales.length === 1 ? ' month' : ' months')); head.append(n); }
            if (sales.length > 3) {
                const tools = el('div', 'sec-tools');
                const all = el('button', 'link', 'Show all'); all.type = 'button'; all.append(ico(I.chev));
                all.onclick = () => fcPage('Worth looking at', () => fcWorthTable(latest, sales.slice().sort((a, b) => a.month < b.month ? -1 : 1)));
                tools.append(all); head.append(tools);
            }
            box.append(head);
            /* A warning is a sentence, said once, with how many more months: the
               worst first (below zero before below the buffer), then the soonest. */
            if (cash.length) {
                const worst = cash.slice().sort((a, b) => (b.verdict === 'negative working capital') - (a.verdict === 'negative working capital') || (a.month < b.month ? -1 : 1))[0];
                const more = cash.length > 1 ? ', and ' + (cash.length - 1) + ' more month' + (cash.length > 2 ? 's' : '') : '';
                box.append(el('div', 'msg error', fcMonth(worst.month) + ': ' + fcAlertText(worst).replace(/\.$/, '') + more + '.'));
            }
            if (!sales.length) { if (!cash.length) box.append(el('div', 'empty', 'Nothing to flag under ' + sc + '.')); return box; }
            /* The three that matter most (fcAlertWeight), read in month order. */
            const top = sales.slice().sort((a, b) => fcAlertWeight(b) - fcAlertWeight(a)).slice(0, 3)
                .sort((a, b) => a.month < b.month ? -1 : 1);
            box.append(fcWorthTable(latest, top));
            return box;
        }

        /* ---------- 1. EXPECTED THIS MONTH: the feature band ----------
           The screen's main question (the mix, spec 8.1), answered first: what
           this month is expected to come to against the plan, how sure that is
           (behind the info button, word for word), the likely range as one bar
           with the plan as a tick; beside it what is taken so far and where
           the year lands. */
        function fcBand(latest, sc) {
            const cur = fcCurrentRow(latest);
            if (!cur || cur.p50 == null) return null;
            const banked = fcBankedThisMonth(latest);
            const p50 = cur.p50, p10 = cur.p10, p90 = cur.p90;
            const target = (cur.targets || {})[sc];
            /* Worked out from the two figures printed beside it: the run's
               gap_pct arrives rounded to two places. */
            const gap = (target && p50 != null) ? (p50 - target) / target : null;
            const year = latest.year || {}; const yt = (year.targets || {})[sc];
            const yg = (yt && year.p50 != null) ? (year.p50 - yt) / yt : null;
            /* Within 10% of plan is on track: the chip is the quiet fill. */
            const fcTrend = (g) => g == null ? null : Math.abs(g) <= 0.10 ? 'flat' : (g > 0 ? 'up' : 'down');
            const chip = (g) => g == null ? null : changeChip(fcTrend(g), Math.abs(g * 100).toFixed(1) + '%', deltaTone('expected', fcTrend(g)));
            let sure = null;
            if (p10 != null && p90 != null) {
                const half = Math.round((p90 - p10) / 2);
                sure = infoButton('How sure this is', { title: 'How sure this is', guide: ['money', 'Forecast'], body: [
                    'How certain is that? ' + fcMonth(cur.month) + ' should land within about ' + fcMoney(half)
                        + ' either side of ' + fcMoney(p50) + ', 8 times out of 10. It is an expectation, not a commitment.',
                    'Figures are cash in; what is still to come is a range, never a promise.'] });
            }
            const d = bandDomain([p10, p90, p50, target]);
            const sides = [{ icon: I.wallet, label: 'Taken so far', value: fcMoney(banked),
                note: 'Day ' + fcDaysSoFar(latest) + ' of ' + fcDaysInMonth(latest),
                meter: fcSideMeter(banked, p50, target) }];
            if (year.p50 != null) sides.push({ icon: I.flag, label: 'Year lands at', value: fcMoney(year.p50), chip: chip(yg),
                note: yt != null ? 'Plan ' + fcMoney(yt) : null,
                meter: fcSideMeter(fcYearTaken(latest), year.p50, yt) });
            return featureBand({ main: { icon: I.trendUp, label: 'Expected this month', info: sure, value: fcMoney(p50),
                chip: chip(gap), note: target != null ? 'against plan' : null,
                range: (p10 != null && p90 != null) ? rangeBar({ lo: p10, hi: p90, exp: p50, plan: target, d,
                    planLabel: target != null ? 'Plan ' + fcMoney(target) : null, loLabel: fcMoney(p10), hiLabel: fcMoney(p90),
                    midLabel: 'Likely range' }) : null }, sides });
        }
        /* A side meter, drawn to the larger of what is expected and the plan, so the
           plan's tick is where it really is: a plan above the expectation is the
           end of the track, and the light bar stops short of it at the expected
           figure. (Drawn to the expected figure alone the tick was clamped to the
           end and read as on plan.) */
        function fcSideMeter(taken, exp, plan) {
            const top = Math.max(exp || 0, plan || 0) || 1;
            return meter({ taken: (taken || 0) / top * 100, end: (exp || 0) / top * 100,
                           plan: plan != null ? plan / top * 100 : null });
        }
        /* What the plan year has taken so far: its closed months as the run
           counts them, and this month's takings. */
        function fcYearTaken(latest) {
            return (Number((latest.sanity || {}).year_banked) || 0) + fcBankedThisMonth(latest);
        }

        /* Money already in the till this month. The run marks the current month
           actual_to_date, and the daily history is the same money day by day,
           so either answers it; the daily sum is preferred because it is what
           the chart draws. */
        function fcBankedThisMonth(latest) {
            const cm = fcCurrentMonth(latest);
            const days = ((latest.daily || {}).history || []).filter(d => (d.date || '').slice(0, 7) === cm);
            if (days.length) return days.reduce((a, d) => a + (Number(d.actual) || 0), 0);
            const m = (latest.monthly || []).find(r => (r.month || '') === cm);
            return m && m.actual_to_date != null ? m.actual_to_date : 0;
        }
        /* The month the reader is in: the day after the run's as_of. The 03:00
           run on the 1st is as of the last day of the month before, and the
           page used to take that month for this one: on 1 Oct it read "38,741
           taken so far in Oct 2026, 30 of 30 days in", September's whole
           takings, and showed October's forecast less that as still to come. */
        function fcCurrentMonth(latest) {
            const d = new Date((latest.as_of || fcISO(new Date())) + 'T00:00:00');
            d.setDate(d.getDate() + 1);
            return fcISO(d).slice(0, 7);
        }
        function fcCurrentRow(latest) {
            const rows = latest.monthly || [];
            return rows.find(r => r.month === fcCurrentMonth(latest))
                || rows.find(r => (r.method || '').indexOf('actual_to_date') === 0)
                || rows.find(r => r.method === 'forecast') || rows[0];
        }

        /* ---------- WHY: what is driving the number ----------
           The honest decomposition (the mix, spec 8.1 item 5): money already
           taken and what is still expected, as one split bar and three rows,
           then which method expects it. How that method works is the info
           button's, in its own words. This model forecasts the shop's own
           takings from the shop's own history: it has no invoice ledger, so it
           never claims invoice-level drivers. */
        function fcDriversCard(latest, sc) {
            const cur = fcCurrentRow(latest);
            if (!cur || cur.p50 == null) return null;
            const banked = fcBankedThisMonth(latest);
            const rest = Math.max(0, cur.p50 - banked);
            const sn = latest.sanity || {};
            const best = (sn.models || []).find(m => m.name === sn.best);
            const box = el('section', 'fc-why');
            const head = el('div', 'section-title', 'Why ' + fcMoney(cur.p50));
            if (best && best.about) {
                const cut = best.about.indexOf('It misleads when');
                head.append(infoButton('How this is worked out', { title: best.name, guide: ['money', 'Forecast'],
                    body: cut > 0 ? [best.about.slice(0, cut).trim(), best.about.slice(cut)] : [best.about] }));
            }
            box.append(head);
            /* ONE split bar: the two parts of one figure, on one scale. */
            const whole = (banked + rest) || 1;
            const bar = el('div', 'fc-split-bar'); bar.setAttribute('aria-hidden', 'true');
            bar.style.setProperty('--w', (banked / whole * 100).toFixed(1) + '%');
            bar.append(el('i', 'taken'), el('i', 'still'));
            box.append(bar);
            /* Read as a statement: each part's key and name, its amount at the
               right of the same measure, and the total under a stronger rule. */
            const list = el('div', 'fc-drive');
            const row = (amt, label, cls) => {
                const r = el('div', 'fc-drive-row' + (cls ? '' : ' fc-drive-tot'));
                if (cls) r.append(el('span', 'fc-drive-key ' + cls));
                r.append(el('span', 'fc-drive-lbl', label));
                r.append(el('span', 'fc-drive-amt', fcMoney(amt)));
                return r;
            };
            list.append(row(banked, 'Taken so far', 'taken'), row(rest, 'Still expected', 'still'), row(cur.p50, 'Expected this month', ''));
            box.append(list);
            if (best) {
                const p = el('p', 'fc-foot');
                p.append(document.createTextNode('Rest of ' + fcMonthName(cur.month) + ' forecast by the '),
                         el('b', null, best.name), document.createTextNode(' method.'));
                box.append(p);
            }
            return box;
        }
        function fcDaysSoFar(latest) {
            const asOf = latest.as_of || fcISO(new Date());
            return asOf.slice(0, 7) === fcCurrentMonth(latest)
                ? new Date(asOf + 'T00:00:00').getDate() : 0;
        }
        function fcDaysInMonth(latest) {
            const cm = fcCurrentMonth(latest);
            return new Date(+cm.slice(0, 4), +cm.slice(5, 7), 0).getDate();
        }

        function fcChartCard(latest, ledger, sanity) {
            const range = fcRange();
            const cmpOn = fcCompareOn();
            const asOf = new Date((latest.as_of || fcISO(new Date())) + 'T00:00:00');
            const days = (latest.daily || {});
            const dayRows = (days.history || []).map(r => ({ date: r.date, actual: r.actual, p50: null, p10: null, p90: null }))
                .concat((days.forecast || []).map(r => ({ date: r.date, actual: null, p50: r.p50, p10: r.p10, p90: r.p90 })));
            const months = latest.months || [];
            const shift = (n) => { const d = new Date(asOf); d.setDate(d.getDate() - n); return fcISO(d); };
            /* "This month" and "The months ahead" start at the month the reader
               is in, not the run's as_of month: the 03:00 run on the 1st is as
               of the last day of the month before, and the default view drew
               September, headed This month, on 1 October. */
            const curMonth = fcCurrentMonth(latest);
            let grain = 'day', from = '', to = '', title = '', period = '';
            const [cf, ct] = fcCustom();
            if (range === 'today') { from = shift(6); to = fcISO(asOf); title = 'Today, and the six days before it'; period = 'the day, against the average of the six before it'; }
            else if (range === 'week') { from = shift(6); to = fcISO(asOf); title = 'The last seven days'; period = 'the last seven days'; }
            else if (range === 'month') { from = curMonth + '-01'; to = ''; title = 'This month, day by day'; period = 'taken so far, then the rest of the month forecast'; }
            else if (range === 'q') { from = shift(91); to = fcISO(asOf); title = 'The last three months'; period = 'day by day'; }
            else if (range === 'year') { grain = 'month'; from = ''; to = ''; title = 'The last twelve months'; period = 'month by month, with what was predicted at the time'; }
            else if (range === 'ahead') { grain = 'month'; from = curMonth; to = ''; title = 'The months ahead'; period = 'the leading method, with its own measured error as the band'; }
            else { from = cf; to = ct; title = 'The range you chose'; period = 'day by day'; }

            let rows;
            if (grain === 'month' || (range === 'custom' && from && to && (new Date(to) - new Date(from)) / 864e5 > 120)) {
                grain = 'month';
                const f = from ? from.slice(0, 7) : '', t = to ? to.slice(0, 7) : '';
                rows = months.filter(m => (!f || m.month >= f) && (!t || m.month <= t));
                if (range === 'year') rows = rows.filter(m => m.actual != null).slice(-12);
                if (range === 'ahead') rows = rows.slice(0, 12);
            } else {
                rows = dayRows.filter(r => (!from || r.date >= from) && (!to || r.date <= to));
                if (range === 'month') rows = rows.filter(r => r.date.slice(0, 7) === curMonth);
            }
            /* Cash in (the mix, spec 8.1): About this chart beside the title,
               Compare methods and the range at its right, the legend on the
               chart's own row. What the head said (its title, the source and
               the period) is the info button's, word for word. */
            const card = el('div', 'fc-cash');
            const head = el('div', 'section-title', 'Cash in');
            head.append(infoButton('About this chart', { title: title, guide: ['money', 'Forecast'],
                body: ['Source: Shopify orders and the nightly forecast \u00b7 ' + period + '.', 'Likely range, 8 times in 10.'] }));
            const tools = el('div', 'sec-tools');
            tools.append(switchBtn('Compare methods', cmpOn, setFcCompareOn));
            tools.append(segmented(FC_RANGES.map(([k, l]) => k === 'custom' ? { key: k, label: l, icon: I.cal } : { key: k, label: l }),
                range, setFcRange, { label: 'Range' }));
            /* A phone has no room for seven segments: the same choice as one
               compact list, which the phone rules show in their place. */
            const pick = el('span', 'fc-range-pick');
            pick.append(ico(I.cal), choiceSelect(FC_RANGES, range, setFcRange, { label: 'Range' }));
            tools.append(pick);
            head.append(tools);
            card.append(head);
            /* The dates belong under the tab that asked for them, not in a
               third card below the chart and the source list. And until both
               are set there is no range to draw: with neither, every day of
               history was drawn as a picket fence headed "The range you chose". */
            if (range === 'custom') {
                const row = el('div', 'act-row fc-dates');
                const mk = (val, label, on) => {
                    const w = el('label', 'pfield'); w.append(el('span', null, label));
                    const i = document.createElement('input'); i.type = 'date'; i.className = 'field-sm fc-date'; i.value = val;
                    i.onchange = on; w.append(i); return w;
                };
                let a = cf, b = ct;
                row.append(mk(cf, 'From', (e) => { a = e.target.value; setFcCustom(a, b); }));
                row.append(mk(ct, 'To', (e) => { b = e.target.value; setFcCustom(a, b); }));
                card.append(row);
                if (!cf || !ct) { card.append(el('div', 'empty', 'Pick a start and an end date.')); return card; }
            }
            if (!rows.length) { card.append(el('div', 'empty', 'Nothing to draw for this range yet.')); return card; }
            const labels = rows.map(r => grain === 'month' ? fcMonth(r.month) : fcDay(r.date));
            /* ACTUAL -> FORECAST -> UNCERTAINTY, in that visual order.
               The old picture drew four equal lines: taken, forecast, P90, P10.
               Four strokes of the same weight read as four competing answers,
               and nothing on the plot said which part had already happened.
               Now there is ONE line that changes character at today - solid
               where the money arrived, dashed where it is expected - and ONE
               shaded region for the range. The forecast series repeats the last
               actual value so the two halves join rather than floating apart,
               and the band pinches to nothing at that same point, because at
               today there is no uncertainty left: it widens as it goes out. */
            const actualVals = rows.map(r => r.actual);
            let handover = -1;
            actualVals.forEach((v, i) => { if (v != null) handover = i; });
            const joins = (i, v) => (i === handover ? rows[i].actual : v);
            /* The legend says in words what each treatment is, because a
               shaded band explains itself only to somebody who already reads
               forecast charts. One colour per measure (the mix): taken in the
               dark teal, keyed as a dot; expected as the teal line, solid; the
               likely range as the teal area. */
            const series = [{ name: 'Taken', color: tokenValue('--c-taken'), key: 'dot', values: actualVals },
                            { name: 'Expected', color: tokenValue('--c-exp-line'), lead: true,
                              values: rows.map((r, i) => joins(i, r.p50)) }];
            const band = rows.some(r => r.p10 != null && r.p90 != null)
                ? { name: 'Likely range', color: tokenValue('--c-area'),
                    lo: rows.map((r, i) => joins(i, r.p10)),
                    hi: rows.map((r, i) => joins(i, r.p90)) }
                : null;
            if (grain === 'month') {
                /* What the forecast in use said for each closed month, from
                   the first run after the month before had closed, so the
                   gap between what directors were told and what came in is
                   on one picture. It used to plot whichever source turned out
                   closest, chosen after the month closed, which made a 36%
                   miss look like a hit. A month closed before the record kept
                   the source in use draws no point rather than a guess. */
                const said = {};
                ((ledger || {}).results || []).forEach(r => {
                    if (r.in_use && r.in_use.value != null) said[r.month] = r.in_use.value;
                });
                if (Object.keys(said).length) {
                    series.push({ name: 'Was predicted', color: CH[3] || CH[2],
                                  values: rows.map(r => said[r.month] == null ? null : said[r.month]) });
                }
            }
            /* Every method the reader has asked to see, drawn against the
               leader and against what actually came in, while Compare methods
               is on. Monthly grain only: a method forecasts a MONTH, and
               spreading it over days here would be inventing a shape it never
               claimed. */
            const cmp = cmpOn ? fcCompare() : [];
            if (grain === 'month' && cmp.length) {
                const by = {};
                ((sanity || {}).models || []).forEach(m => { if (cmp.indexOf(m.name) >= 0) by[m.name] = m.months || {}; });
                /* Each in its slot's own colour, dashed as a comparison is,
                   but at full strength: the colours were chosen at full
                   strength, and at the comparison's 70% the orange falls
                   under 3:1 on white. */
                cmp.forEach((n, i) => {
                    if (!n || !by[n]) return;
                    series.push({ name: n.length > 26 ? n.slice(0, 25) + '\u2026' : n,
                                  color: tokenValue(FC_METHOD[i]), full: true,
                                  values: rows.map(r => (by[n][r.month] == null ? null : by[n][r.month])) });
                });
            }
            const chart = trendChart({ headless: true, legend: true, label: 'Cash in, ' + title, title: title,
                source: 'Shopify orders and the nightly forecast', period: period, yUnit: 'GBP', labels: labels, series: series,
                band: band, splitAt: handover > 0 && handover < rows.length - 1 ? handover : null,
                format: (n) => money(n, 'GBP', 0), tickFormat: fmtCompactGBP, area: false,
                xWeekly: range === 'month', lastLabel: grain === 'day',
                height: window.matchMedia('(max-width: 640px)').matches ? 200 : 268, annotate: false });
            card.append(chart);
            /* On a phone the switch sits under the chart, where a thumb finds
               it; the head's copy is hidden there. */
            const phoneSw = switchBtn('Compare methods', cmpOn, setFcCompareOn);
            phoneSw.classList.add('fc-cmp-phone');
            card.append(phoneSw);
            /* The methods to draw, while Compare methods is on: a chip per
               method, tap to add its line. Capped at three, because a fourth
               line's colour would collide with one the chart already draws. */
            const srcs = ((sanity || {}).models || []).filter(m => m.months);
            if (cmpOn && srcs.length) {
                const box = el('div', 'fc-cmp-box');
                if (grain !== 'month') {
                    /* A method forecasts a MONTH, so on a daily range the honest
                       thing is one line saying so and the way to a range where
                       it works, not the whole set disabled. */
                    box.append(el('p', 'fc-cmp-note', 'Each method forecasts a month, so they can be compared on a '
                        + 'monthly range rather than day by day.'));
                    const go = el('button', 'btn', 'Show the last twelve months');
                    go.type = 'button'; go.onclick = () => setFcRange('year');
                    box.append(go);
                } else {
                    const chips = el('div', 'fc-cmp');
                    const picks = cmp.filter(Boolean).length;
                    srcs.forEach(m => {
                        const picked = cmp.indexOf(m.name) >= 0;
                        const b = el('button', 'chip' + (picked ? ' on' : ''), m.name);
                        b.type = 'button';
                        b.disabled = !picked && picks >= FC_CMP_MAX;
                        if (b.disabled) b.title = 'Three lines at most: take one off to add another';
                        b.setAttribute('aria-pressed', picked ? 'true' : 'false');
                        if (m.name === (sanity || {}).best) b.append(document.createTextNode(' '), fcChip('made', 'in use'));
                        b.onclick = () => toggleFcCompare(m.name);
                        chips.append(b);
                    });
                    box.append(chips);
                    if (cmp.length) {
                        const clr = el('button', 'btn ghost', 'Clear');
                        clr.type = 'button'; clr.onclick = clearFcCompare;
                        box.append(clr);
                    }
                }
                card.append(box);
            }
            return card;
        }
        /* The run's own order, the one its figures come from, when it carries
           one (every run from 19 October 2026). Each card kept a sort of its
           own, and once the forecast ranked on its record they named different
           methods from the one the figures followed. The sort is stable, so a
           card's own order still decides among rows the run did not rank, and
           for an older run that carries no order. */
        function fcRankFirst(sn, rows, nameOf) {
            if (!Array.isArray(sn.ranking)) return rows;
            const at = r => { const i = sn.ranking.indexOf(nameOf(r)); return i < 0 ? 1e9 : i; };
            return rows.slice().sort((a, b) => at(a) - at(b));
        }
        /* ---------- which one is in use, and why ----------
           Nobody picks the algorithm here, so the page owes the reader a
           straight answer to the question they would otherwise ask: which one
           is running, why that one, and how much better is it than the next.
           Never make somebody guess whether the optimised choice is actually
           being used. */
        function fcOptimisedCard(latest) {
            const sn = latest.sanity || {};
            const box = el('div');
            box.append(el('div', 'section-title', 'The algorithm in use'));
            const card = el('div', 'card');
            const ranked = (sn.models || []).filter(m => m.months)
                .map(m => ({ m: m, live: (m.live || {}).mape, back: (m.score || {}).mape }))
                .filter(x => x.live != null || x.back != null);
            const onRecord = sn.ranked_on === 'record';
            ranked.sort((a, b) => (onRecord && a.live != null && b.live != null)
                ? a.live - b.live : ((a.back == null ? 9 : a.back) - (b.back == null ? 9 : b.back)));
            const order = fcRankFirst(sn, ranked, x => x.m.name);
            const lead = order[0], next = order[1];
            if (!lead) {
                card.append(el('p', 'card-sub', 'No method has been scored yet.'));
                box.append(card); return box;
            }
            const head = el('div', 'card-head card-head-stat');
            head.append(el('div', 'card-title', 'Running now, chosen automatically'));
            head.append(el('div', 'card-desc', lead.m.name));
            const err = onRecord ? lead.live : lead.back;
            const bits = [];
            bits.push(onRecord
                ? 'Chosen on its record: closest on ' + ((lead.m.live || {}).wins || 0) + ' of '
                  + ((lead.m.live || {}).months || 0) + ' months that have closed since this started running'
                : 'Chosen on the backtest: fitted to earlier months and marked against what happened, '
                  + 'because not every method has three closed months on its record yet');
            if (err != null) bits.push('typically out by ' + (err * 100).toFixed(0) + '%');
            if (next) {
                const ne = onRecord ? next.live : next.back;
                if (ne != null) bits.push('the next best, ' + next.m.name + ', is out by ' + (ne * 100).toFixed(0) + '%');
            }
            head.append(el('div', 'card-sub', bits.join(' \u00b7 ')));
            const act = el('div', 'card-act');
            act.append(fcChip('made', 'in use'));
            head.append(act);
            card.append(head);
            card.append(el('p', 'card-sub', onRecord
                ? 'It is judged on months it could not see: the first figure it gave for each month, against '
                  + 'what came in. At the end of every month every method is marked again, and if another '
                  + 'starts coming closer, it takes over without anyone changing a setting.'
                : 'Once every method has three closed months on its record, the choice moves onto that record '
                  + 'instead, which is the harder test: a backtest refits a model to a period the code already '
                  + 'knows the shape of.'));
            box.append(card);
            return box;
        }

        /* ---------- what each one actually does ----------
           Written for somebody who has to sign off on a number, not for
           somebody who already knows what ARIMA stands for. Name, how it
           works, what shape of business it suits, how right it has been, and
           whether it is the one running. */
        /* What each source suits, keyed by its name. The service sends this
           as best_at, but the field was added after the run that produced the
           payload now on screen, so a page fed by an older run showed nothing.
           The strings are the service's own, copied; a payload that carries
           best_at wins over this map. */
        const FC_BEST_AT = {
            'Last year, adjusted for this year': 'a repeating yearly shape whose overall level has moved up or down',
            'A typical month, shared out': 'a steady business with a strong season and little underlying trend',
            'Smoothed level and season': 'a level that drifts gradually, with the same season each year',
            'Smoothed level, season and trend': 'a business steadily growing or shrinking underneath its season',
            'Trend and smoothing, averaged': 'a clear underlying direction with seasonal movement on top of it',
            'Auto-fitted level, trend and season': 'letting the data decide the shape when nobody is sure what it is',
            'Auto-fitted ARIMA': 'months that depend closely on the months immediately before them',
            'Auto-fitted trend and smoothing': 'a steady direction of travel, found without being told what to look for',
            'Auto-fitted complex smoothing': 'a season whose shape shifts from one year to the next',
            'Average of every source': 'when no single approach is clearly right for the period ahead',
            'Middle of every source': 'when one method is prone to extreme answers',
            'Average, extremes removed': 'when most methods agree and one or two are far out',
        };

        function fcBestAt(m) {
            const raw = m.best_at || FC_BEST_AT[m.name] || '';
            return raw.replace(/^Best at:\s*/i, '').replace(/\.\s*$/, '');
        }

        function fcAlgorithmsCard(latest) {
            const sn = latest.sanity || {};
            const list = (sn.models || []).filter(m => m.about);
            const box = el('div');
            box.append(el('div', 'section-title', 'How each one works'));
            const card = el('div', 'card');
            if (!list.length) {
                card.append(el('p', 'card-sub', 'The methods arrive with the next run.'));
                box.append(card); return box;
            }
            card.append(el('p', 'card-sub',
                'Every method the system runs each night. It tries all of them, marks all of them, '
                + 'and uses whichever has been closest. Nothing here needs choosing.'));
            const onRecord = sn.ranked_on === 'record';
            const rows = fcRankFirst(sn, list.slice().sort((a, b) => {
                const ax = onRecord && (a.live || {}).mape != null ? a.live.mape : ((a.score || {}).mape ?? 9);
                const bx = onRecord && (b.live || {}).mape != null ? b.live.mape : ((b.score || {}).mape ?? 9);
                return ax - bx;
            }), m => m.name);
            rows.forEach(m => {
                /* Name and the numbers on ONE line, so the column of figures
                   reads down the page and the sources can be compared at a
                   glance. The prose sits under it, quiet, for whoever wants
                   it. Thirteen stacked essays is not a comparison. */
                const item = el('div', 'fc-algo');
                const head = el('div', 'fc-algo-head');
                const t = el('div', 'fc-algo-name', m.name);
                if (m.name === sn.best) t.append(document.createTextNode(' '), fcChip('made', 'in use'));
                if (m.kind === 'combination') t.append(document.createTextNode(' '), fcChip('', 'combines the others'));
                head.append(t);
                const nums = el('div', 'fc-algo-nums');
                if ((m.live || {}).mape != null) {
                    nums.append(el('span', 'fc-algo-num', (m.live.mape * 100).toFixed(0) + '% on '
                        + m.live.months + ' closed month' + (m.live.months === 1 ? '' : 's')));
                    nums.append(el('span', 'fc-algo-num', 'closest ' + m.live.wins + ' of ' + m.live.months));
                }
                if ((m.score || {}).mape != null) {
                    nums.append(el('span', 'fc-algo-num', (m.score.mape * 100).toFixed(0) + '% in the backtest'));
                    nums.append(el('span', 'fc-algo-num', 'leans '
                        + (m.score.bias >= 0 ? 'high ' : 'low ') + Math.abs(m.score.bias * 100).toFixed(0) + '%'));
                }
                if (!nums.childNodes.length) nums.append(el('span', 'fc-algo-num', 'not yet scored'));
                head.append(nums);
                item.append(head);
                item.append(el('p', 'fc-algo-text', m.about));
                /* On its own line. Appended to the end of a three-line
                   paragraph it was there and unfindable, which is the same as
                   missing when somebody is scanning for which source suits
                   which shape of month. */
                const ba = fcBestAt(m);
                if (ba) {
                    const line = el('div', 'fc-algo-fit');
                    line.append(el('span', 'fc-algo-fit-lbl', 'Best at'));
                    line.append(el('span', 'fc-algo-fit-txt', ba));
                    item.append(line);
                }
                card.append(item);
            });
            box.append(card);
            return box;
        }

        /* A method page in a window: wide, for the tables some of them hold. The
           last one opened is kept, so a choice made inside it (how many methods
           to show) repaints it in place: the page behind is not the window. */
        let fcLivePage = null;
        /* o.prose: a window of paragraphs is the sheet's own width (12 Oct
           2026, DF-28); two paragraphs in an 820px window ran 120 characters
           a line. A table keeps the wide window. */
        function fcPage(title, build, o) {
            const m = sheetModal(title); m.modal.classList.add(o && o.prose ? 'prose' : 'wide'); m.body.append(build());
            fcLivePage = { m: m, build: build };
            return m;
        }
        function fcRepaintPage() {
            const lp = fcLivePage;
            if (!lp || !lp.m.overlay.isConnected) return;
            lp.m.body.replaceChildren(lp.build());
            /* The pressed button was replaced: keyboard focus goes to its successor, not to the page. */
            const on = lp.m.body.querySelector('.segmented > button.on');
            if (on) on.focus();
        }
        /* How much to trust it: prose when the plain models are running, the
           M5 backtest table when that build is. */
        function fcTrust(latest) {
            const bt = latest.metrics || [];
            const bc = el('div');
            if (!bt.length) {
                bc.append(el('p', 'card-sub', 'Each method was fitted to earlier months and marked against '
                    + 'what actually happened, three times over. Typical error is how far out it usually was; '
                    + 'bias is whether it leaned high or low every month, which matters more, because a model '
                    + 'that leans high quietly turns a plan green. The leading model\u2019s own error is the '
                    + 'band on the chart, so the forecast never claims to be more certain than it has earned.'));
                if (latest.basis) bc.append(el('p', 'card-sub', 'Figures are ' + latest.basis + '.'));
                return bc;
            }
            bc.append(el('p', 'card-sub', 'Five backtests of 28 days each, ending at the run date. WRMSSE is the M5 competition score: under 1 beats a naive forecast scaled to each series, and lower is better. Bias is how far the total ran hot or cold.'));
            const levels = ['total', 'category', 'segment', 'product', 'variant', 'bottom'];
            bc.append(fcTable(['Level', 'Blend', 'Seasonal baseline', 'Bias'],
                levels.map(l => { const b = bt.find(m => (m.model === 'blend+mint' || m.model === 'blend') && m.level === l); const s = bt.find(m => m.model === 'seasonal_level' && m.level === l);
                    return [l === 'bottom' ? 'variant x segment' : l, b ? Number(b.wrmsse).toFixed(2) : 'n/a', s ? Number(s.wrmsse).toFixed(2) : 'n/a', b ? fcPct(b.bias_pct) : 'n/a']; }),
                [0, 1, 1, 1]));
            const w = latest.weights && latest.weights.total;
            if (w) bc.append(el('p', 'card-sub', 'Who earned the top line: ' + Object.keys(w).filter(k => w[k] > 0.005).map(k => k + ' ' + Math.round(w[k] * 100) + '%').join(', ') + '.'));
            return bc;
        }
        /* The plan it is judged against: provenance, for somebody checking the work. */
        function fcPlanJudged(c, latest) {
            const wb = c.workbook || {};
            const names = latest.scenarios || [];
            const rc = el('div');
            rc.append(el('p', 'card-sub', wb.name ? (wb.name + ', uploaded ' + fmtDate(wb.uploaded_at) + (wb.by ? ' by ' + wb.by : '')
                    + '. Every scenario in it is a plan the forecast is measured against; the page opens on '
                    + (latest.scenario_feature || names[0] || 'the first') + '.')
                : 'No workbook on file: the run used what the service had.'));
            if (c.runs && c.runs.length) rc.append(el('p', 'card-sub', 'Recent runs: ' + c.runs.slice(-7).map(r => fmtDate(r.as_of)).join(', ') + '.'));
            return rc;
        }
        /* How it works (the mix, spec 8.1): the four method pages, each in a
           window, then the Forecast in the Guide. They were four drawers at the
           foot of the page. */
        function fcHowItWorks(c, latest, sc) {
            const nsrc = ((latest.sanity || {}).models || []).length;
            return howItWorks([
                { icon: I.compass, label: 'Which method is running, and why',
                  onClick: () => fcPage('Which method is running, and why', () => fcUntitled(fcOptimisedCard(latest))) },
                { icon: I.target, label: 'How each one works, and how right it has been', n: nsrc || null, unit: 'methods',
                  onClick: () => fcPage('How each one works, and how right it has been', () => fcUntitled(fcAlgorithmsCard(latest))) },
                { icon: I.shield, label: 'How much to trust it', onClick: () => fcPage('How much to trust it', () => fcTrust(latest), { prose: !(latest.metrics || []).length }) },
                { icon: I.fileSheet, label: 'The plan it is judged against', onClick: () => fcPage('The plan it is judged against', () => fcPlanJudged(c, latest), { prose: true }) },
            ], { label: 'The Forecast in the Guide', at: ['money', 'Forecast'] });
        }

        /* ---------- the standing record ----------
           What every source SAID about a month while that month was still
           ahead, marked when the month closed. It is the honest test, and the
           one the system now ranks on once there are three closed months: a
           backtest refits a model to a period the code already knows the shape
           of, and forgives it accordingly.

           Nobody chooses an algorithm here. The table is the reason to trust
           the choice that was made. */
        function fcRecordCard(c) {
            const led = (c && c.ledger) || {};
            const res = (led.results || []).slice(-12);
            const sn = (c.latest || {}).sanity || {};
            const box = el('div');
            box.append(el('div', 'section-title', 'What has actually been right'));
            const card = el('div', 'card');
            if (!res.length) {
                card.append(el('p', 'card-sub',
                    'Nothing has closed yet. From the end of this month, every method\u2019s prediction is '
                    + 'marked against what actually came in, and the one that keeps coming closest starts '
                    + 'leading the forecast. Until then the ranking is the backtest above.'
                    + ((led.open || []).length ? ' Months being watched: ' + led.open.join(', ') + '.' : '')));
                box.append(card); return box;
            }
            const tally = {};
            res.forEach(r => {
                Object.entries(r.by_source || {}).forEach(([n, v]) => {
                    const t = tally[n] = tally[n] || { n: 0, abs: 0, wins: 0 };
                    t.n++; t.abs += Math.abs(v.error || 0); if (r.winner === n) t.wins++;
                });
            });
            const names = Object.keys(tally).sort((a, b) => (tally[a].abs / tally[a].n) - (tally[b].abs / tally[b].n));
            /* Each closed month first, newest at the top, in pounds: what came
               in, what the forecast in use said and when, whether it landed
               in its likely range, and which source came closest. The table
               of percentages alone said none of that: not what directors were
               told, not when, and not in money. */
            res.slice().reverse().forEach(r => {
                const p = el('p', 'card-sub');
                p.append(el('b', null, fcMonth(r.month) + ': ' + fcMoney(r.actual) + ' came in.'));
                const u = r.in_use;
                let line;
                if (u && u.value != null) {
                    line = ' The forecast in use, ' + u.source + ', said ' + fcMoney(u.value)
                        + (u.made ? ' on ' + fcDay(u.made) : '')
                        + (u.seen_through ? ', from takings to the end of ' + fcMonth(u.seen_through) : '')
                        + ': ' + fcPct(u.error) + ' out'
                        + (u.inside == null ? '.'
                            : (u.inside ? ', inside' : ', outside') + ' its likely range of '
                              + fcMoney(u.p10) + ' to ' + fcMoney(u.p90) + '.')
                        + (u.reconstructed ? ' Worked out afterwards from the forecast\u2019s own code, because '
                            + 'the record did not yet keep the method in use.' : '');
                } else {
                    line = ' Which method the page was using is not on record for this month.';
                }
                const w = (r.by_source || {})[r.winner];
                if (w) line += ' Closest: ' + r.winner + ', ' + fcMoney(w.predicted) + ' (' + fcPct(w.error) + ').';
                p.append(document.createTextNode(line));
                card.append(p);
            });
            card.append(el('p', 'card-sub',
                'Below, how far out each method\u2019s first figure for the month was. '
                + (sn.ranked_on === 'record'
                    ? 'With ' + (sn.closed_months || res.length) + ' closed months on record, this is what the '
                      + 'forecast is now ranked on rather than the backtest.'
                    : Object.keys(sn.record_waiting || {}).length
                        ? 'Every method needs three closed months of its own before this outranks the backtest. '
                          + (sn.closed_months || 0) + ' have closed; the newest method has '
                          + Math.min.apply(null, Object.values(sn.record_waiting)) + '.'
                        : 'Three closed months are needed before this outranks the backtest; there are '
                          + (sn.closed_months || 0) + ' so far.')));
            /* The source names in full, wrapping onto two lines: cut at 22
               characters they read 'Smoothed level, seaso...' with no way to
               see the rest. */
            card.append(fcTable(['Month', 'Came in'].concat(names.map(n => { const w = el('span', 'fc-th-wrap', n); return w; })),
                res.map(r => [fcMonth(r.month), fcMoney(r.actual)].concat(names.map(n => {
                    const v = (r.by_source || {})[n];
                    if (!v) return 'n/a';
                    const cell = el('span', null, fcPct(v.error));
                    if (r.winner === n) { cell.append(document.createTextNode(' ')); cell.append(fcChip('made', 'closest')); }
                    return cell;
                }))), [0, 1].concat(names.map(() => 1))));
            card.append(fcTable(['Method', 'Months', 'Average error', 'Closest'],
                names.map(n => [n, tally[n].n, (tally[n].abs / tally[n].n * 100).toFixed(1) + '%',
                                tally[n].wins + ' of ' + tally[n].n]), [0, 1, 1, 1]));
            box.append(card);
            return box;
        }
        function fcSanityCard(latest, sc) {
            const sn = latest.sanity;
            const box = el('div');
            box.append(el('div', 'section-title', 'The models, and what each has been worth'));
            const card = el('div', 'card');
            if (!sn || !sn.available) {
                card.append(el('p', 'card-sub', (sn && sn.reason)
                    || 'The nightly run has not posted the plain models yet. They arrive with the next run.'));
                box.append(card); return box;
            }
            const mode = fcRowsMode();
            /* The sources now reach the end of the plan so each can answer the
               year, but twelve month columns push the year and the scores off
               the side of the table. Six is half a year, enough to see where
               sources part company; the full month-by-month for the leading
               source is the table below, and Plan year still covers the lot. */
            const allMonths = sn.months || [];
            const months = allMonths.slice(0, 6);
            card.append(segmented(FC_ROWS, mode, setFcRowsMode));
            card.append(el('p', 'card-sub',
                /* Parenthesised: without it the + bound before ===, the test
                   was always false, and the months clause never showed. */
                (allMonths.length > months.length
                    ? 'The next ' + months.length + ' months are shown; Plan year covers all '
                      + allMonths.length + '. ' : '') +
                (mode === 'one'
                ? 'The method that has been most right on this shop\u2019s own history, with what '
                  + 'the plan expects beside it. Show more above to see whether the others agree. '
                : 'The top one drives the month table, the cash path and the alerts; the next two '
                  + 'stand beside it so you can see whether they agree. Rows marked as an average '
                  + 'combine the others: averaging several forecasts usually beats most single ones, '
                  + 'and here it is put to the same test rather than assumed. '
                  + 'Each reads only the monthly total, so each can be checked by eye. ')
                + 'They are scored on this shop\u2019s own history: fitted to earlier months, '
                + 'then marked against what actually happened. Lower error is better, and a '
                + 'bias that leans one way every month matters more than the size of it.'));
            const ranked = fcRankFirst(sn, (sn.models || []).slice().sort((a, b) => {
                const x = (a.score || {}).mape, y = (b.score || {}).mape;
                if (x == null) return 1; if (y == null) return -1; return x - y;
            }), m => m.name);
            /* Only a row the run ranked can lead or be quoted: one whose
               forecast failed tonight keeps its backtest score, and sorted on
               that alone it was marked as leading with no figures. */
            const quoted = m => !Array.isArray(sn.ranking) || sn.ranking.indexOf(m.name) >= 0;
            const RANK = ['leads the forecast', 'second opinion', 'third opinion'];
            const shown = mode === 'one' ? ranked.slice(0, 1)
                : mode === 'three' ? ranked.slice(0, 3) : ranked;
            const rows = shown.map((m, i) => {
                const name = el('span', null, m.name);
                if (RANK[i] && quoted(m)) name.append(document.createTextNode(' '), fcChip(i ? 'note' : 'made', RANK[i]));
                /* An average of the others is a row like any other and is
                   ranked like one, but it is worth being able to see at a
                   glance which rows are combinations rather than sources. */
                if (m.kind === 'combination') name.append(document.createTextNode(' '), fcChip('', 'average'));
                /* Directors read this table. Every method carries a sentence
                   saying what it does, what it assumes and when it misleads,
                   behind an info button a tap and the keyboard open too. */
                if (m.about) name.append(infoButton(m.name, { title: m.name, body: m.about }));
                const sc2 = m.score || {};
                const yr = m.year == null ? 'n/a' : fcMoney(m.year) + (m.year_partial ? '*' : '');
                return [name].concat(months.map(k => m.error ? 'n/a' : fcMoney((m.months || {})[k])))
                    .concat([yr, sc2.mape == null ? 'n/a' : (sc2.mape * 100).toFixed(0) + '%',
                             sc2.bias == null ? 'n/a' : fcPct(sc2.bias), m.note || m.error || '']);
            });
            /* No separate median footer: "Median of all" is a ranked row in the
               table now, scored like everything else, so a second unranked
               copy of it below would be the same number twice. */
            const planYear = ((latest.year || {}).targets || {})[sc];
            const plan = ['Your plan (' + sc + ')'].concat(months.map(k => {
                const r = (latest.monthly || []).find(x => x.month === k);
                return fcMoney(r ? (r.targets || {})[sc] : null);
            })).concat([fcMoney(planYear), '', '', '']);
            const helpHead = (text, about) => {
                const sp = el('span', 'fc-th', text); sp.append(infoButton(text, { title: text, body: about })); return sp;
            };
            card.append(fcTable(['Method'].concat(months.map(fcMonth)).concat([
                    helpHead('Plan year', 'What the whole of the plan\u2019s year comes to if you believe '
                        + 'this method: the months already banked, which are the same whichever method you '
                        + 'believe, plus this one\u2019s forecast for the rest. A star means the method does '
                        + 'not reach the end of the plan, so the figure covers only part of the year.'),
                    helpHead('Typical error', 'How far out this method usually was. Each was fitted to '
                        + 'earlier months and marked against what actually happened, three times over. '
                        + 'Lower is better. Around a quarter is close to the floor for this business, '
                        + 'because a single large order can be a tenth of a month.'),
                    helpHead('Bias', 'Whether it leaned high or low on average, rather than how far out it was. '
                        + 'This matters more than the error: a method that leans high every single month '
                        + 'quietly makes a plan look safer than it is.'),
                    'How it works']),
                rows.concat([plan]),
                [0].concat(months.map(() => 1)).concat([1, 1, 1, 0])));
            box.append(card);
            return box;
        }
        function renderForecast() {
            const box = $('forecast-content'); box.innerHTML = '';
            const c = forecastCache; const painting = !!c && !c.error;
            box.classList.toggle('no-intro', !(painting && firstPaint('forecast')));
            const latest = c && c.latest;
            const names = (latest && latest.scenarios) || [];
            if (!forecastScenario || names.indexOf(forecastScenario) < 0) forecastScenario = names[0] || '';
            const sc = forecastScenario;
            /* The header (the mix, spec 8.1): Forecast with Beta, a status line
               saying the month the reader is in and which run this is, then How
               it works and Upload workbook. No paragraph: the page is money. */
            const cm = latest ? fcCurrentMonth(latest) : '';
            box.append(pageHead({ view: 'forecast', title: 'Forecast',
                status: latest ? [fcMonthName(cm) + ' ' + cm.slice(0, 4), 'Run as of ' + fmtDate(latest.as_of)] : null,
                actions: [latest ? fcHowItWorks(c, latest, sc) : null, c && c.can_upload ? forecastUploadButton() : null] }));
            /* The Finance tabs, with the plan the page is judged against chosen
               at the row's right: it governs everything under it. */
            const plan = latest && names.length > 1 ? [el('span', 'fc-seg-lbl', 'Plan'),
                segmented(names.map(n => ({ label: n, value: n })), sc, (v) => { forecastScenario = v; renderForecast(); }, { label: 'Plan' })] : [];
            box.append(financeTabs('forecast', '', plan));
            if (!c) { box.append(el('div', 'empty', 'Loading…')); return; }
            if (c.error) { box.append(loadFailure('The forecast could not be read. ' + c.error, refreshForecast)); return; }
            if (!latest) { box.append(forecastSetupCard(c)); return; }
            /* From here the page is blocks the widget grid can move, each
               spanning the row: the header gets the action slot Customize goes
               in (not before, so the loading and setup states keep their header
               as it was). A failed run's warning stays fixed above them, like
               any error. This page never calls cardifySections. The overview,
               the chart and the drivers already come as one wrapper each with
               their own spacing inside, so they are widgets as they are, marked
               widget-bare; a heading that stood beside its block on the page is
               grouped with it here in a widget-group, which keeps 12 under the
               heading as the flow did. */
            if (c.last_error) box.append(fcFailedRunCard(c.last_error, latest.as_of));
            const rows = latest.monthly || [];
            const al = (latest.alerts || []).filter(a => a.scenario === sc);

            /* ---------------------------------------------------------------
               OVERVIEW FIRST, then zoom and filter, then details on demand.
               The page is built in that order and nothing below the fold is
               opened for the reader: 1 the month in a band, 2 the picture,
               3 the months worth looking at beside why, 4 the numbers behind
               it. How the thing works at all is the header's How it works.
               No method picker anywhere - the system picks on evidence, and
               says so there for anyone who asks.
               --------------------------------------------------------------- */

            /* 1. EXPECTED THIS MONTH: the feature band. */
            const band = fcBand(latest, sc);
            if (band) box.append(widget(band, 'standing', 'full', 'Expected this month'));

            /* 2. THE PICTURE. Actual, forecast and uncertainty, with the time
               control on it. This is the largest thing on the page. */
            const chart = fcChartCard(latest, c.ledger, latest.sanity);
            chart.classList.add('widget-bare');
            box.append(widget(chart, 'cash-in', 'full', 'Cash in'));

            /* 3. WORTH LOOKING AT, AND WHY (the mix): the months that matter
               beside what drives this one, 7 to 5, one block in Customize. */
            const pair = el('div', 'fc-pair');
            const cols = el('div', 'fc-cols');
            cols.append(fcWorthCard(latest, sc, al));
            const drv = fcDriversCard(latest, sc);
            if (drv) cols.append(drv);
            pair.append(cols);
            box.append(widget(pair, 'worth', 'full', 'Worth looking at, and why'));

            /* 4. THE NUMBERS BEHIND IT (the mix, spec 8.1 item 6): four list
               rows in two columns, each opening its table in a window. Tables
               carry precise money; the chart above carries the pattern. */
            const numbers = widget(el('div', 'widget-group fc-numbers'), 'numbers', 'full', 'The numbers behind it');
            numbers.append(el('div', 'section-title', 'The numbers behind it'));
            box.append(numbers);
            const monthTable = () => {
                const mc = el('div');
                /* fc-months: a month and its basis stay on one line each; the
                   table scrolls sideways on a phone rather than stacking
                   'May 2026' over two lines and the basis over three. */
                mc.append(fcTable(['Month', 'Basis', 'Projected', 'Likely low', 'Likely high', 'Plan', 'Gap', 'Verdict', 'Risk'],
                    rows.map(r => {
                        const t = (r.targets || {})[sc], v = (r.verdict || {})[sc], k = (r.risk || {})[sc];
                        return [fcMonth(r.month), FC_BASIS[r.method] || fcSentence((r.method || '').replace(/_/g, ' ')),
                                fcMoney(r.p50), fcMoney(r.p10), fcMoney(r.p90), fcMoney(t),
                                fcPct(t && r.p50 != null ? (r.p50 - t) / t : null),
                                v ? fcChip(FC_VERDICT[v] || 'note', FC_VERDICT_WORDS[v] || fcSentence(v)) : '',
                                k ? fcChip(FC_RISK[k] || 'note', fcSentence(k)) : ''];
                    }),
                    [0, 0, 1, 1, 1, 1, 1, 0, 0]));
                mc.lastChild.classList.add('fc-months');
                return mc;
            };
            const cash = (latest.cash || {})[sc] || [];
            const cashTable = () => {
                const cc = el('div');
                cc.append(el('p', 'card-sub', 'The projected sales pushed through the scenario\u2019s own mechanics: its overheads and cost lines, the Shopify Capital remittance on gross, stopping when the loan is repaid.'));
                cc.append(fcTable(['Month', 'Gross sales', 'Repayment', 'Net cash', 'Working capital', 'Loan left'],
                    cash.map(r => { const wc = el('span'); wc.textContent = fcMoney(r.working_capital);
                        if (r.negative) wc.append(' ', fcChip('bad', 'negative')); else if (r.below_buffer) wc.append(' ', fcChip('warn', 'below buffer'));
                        return [fcMonth(r.month), fcMoney(r.gross_sales), fcMoney(r.repayment), fcMoney(r.net_cash), wc, fcMoney(r.loan_end)]; }),
                    [0, 1, 1, 1, 1, 1]));
                return cc;
            };
            const nsrc = ((latest.sanity || {}).models || []).length;
            numbers.append(listRows([
                { icon: I.table, label: 'Month by month against ' + sc, n: rows.length, unit: 'months',
                  onClick: () => fcPage('Month by month against ' + sc, monthTable) },
                cash.length ? { icon: I.cash, label: 'Cash under ' + sc, n: cash.length, unit: 'months',
                  onClick: () => fcPage('Cash under ' + sc, cashTable) } : null,
                { icon: I.columns, label: 'Every method, side by side', n: nsrc || null, unit: 'methods',
                  onClick: () => fcPage('Every method, side by side', () => fcUntitled(fcSanityCard(latest, sc))) },
                { icon: I.compare, label: 'What each method said, and what came in',
                  onClick: () => fcPage('What each method said, and what came in', () => fcUntitled(fcRecordCard(c))) },
            ], { cols: 2, label: 'The numbers behind it' }));

            /* The by-category and by-segment tables came from the per-variant
               model, which no longer runs: it forecast October at a quarter of
               what October has ever been. They stay guarded rather than
               deleted, so an M5 run (FORECAST_M5=1) still draws them. */
            const lv = latest.levels || {};
            ['category', 'segment'].forEach(level => {
                const items = lv[level] || []; if (!items.length) return;
                const months = [...new Set(items.map(x => x.month))].sort().slice(0, 3);
                const byName = {}; items.forEach(x => { (byName[x.name] = byName[x.name] || {})[x.month] = x.p50; });
                const byLevel = level === 'category'
                    ? widget(el('div', 'widget-group'), 'by-category', 'full', 'By category')
                    : widget(el('div', 'widget-group'), 'by-segment', 'full', 'By segment');
                byLevel.append(el('div', 'section-title', 'By ' + level));
                box.append(byLevel);
                const lc = el('div', 'card');
                lc.append(fcTable([level === 'category' ? 'Category' : 'Segment'].concat(months.map(fcMonth)),
                    Object.keys(byName).sort((a, b) => (byName[b][months[0]] || 0) - (byName[a][months[0]] || 0))
                        .map(n => [n].concat(months.map(m => fcMoney(byName[n][m])))), [0, 1, 1, 1]));
                byLevel.append(lc);
            });
        }
