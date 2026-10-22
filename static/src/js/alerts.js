        /* ---------- alerts ---------- */
        let alerts = [];
        async function loadAlerts() {
            try { const d = await api('/api/alerts', {}); if (d && Array.isArray(d.alerts)) alerts = d.alerts; } catch (e) {}
            renderAlerts();
            privacyNotice();
        }
        /* The banner's home: the top of the main column, above every page.
           It was drawn inside the Overview report, the only place it showed,
           until that report went (22 Oct 2026). */
        function renderAlerts() {
            const host = $('alerts-host'); if (!host) return;
            host.innerHTML = '';
            const ab = alertsBanner(); if (ab) host.append(ab);
        }
        /* A privacy request waiting on an admin is also said on its own, once
           a visit, until someone opens it or closes the notice: it is the one
           alert that has a deadline. */
        let privacyNoticed = false;
        function openPrivacyRequests() {
            $('settings-btn').click();
            setTimeout(() => { const t = $('privacy-sec'); if (t && !t.hidden) t.scrollIntoView({ block: 'start' }); }, 300);
        }
        function privacyNotice() {
            if (privacyNoticed || !connIsAdmin()) return;
            const waiting = (alerts || []).some(a => a.status === 'new' && a.tab === 'settings' && /privacy requests/i.test(a.metric || ''));
            if (!waiting) return;
            privacyNoticed = true;
            addToast('Privacy requests from Shopify are waiting for an admin.', null,
                { sticky: true, action: { label: 'Open', fn: openPrivacyRequests } });
        }
        async function alertOp(payload) {
            try { const d = await api('/api/alerts', payload); if (d && Array.isArray(d.alerts)) alerts = d.alerts; }
            catch (e) { toastError('That change was not saved. ' + (e.message || '')); }
            renderAlerts();
        }
        function alertsBanner() {
            const fresh = (alerts || []).filter(a => a.status === 'new');
            if (!fresh.length) return null;
            const wrap = el('div', 'alerts-banner');
            const head = el('div', 'alerts-head'); head.append(ico(I.warning), document.createTextNode(fresh.length + (fresh.length > 1 ? ' alerts' : ' alert')));
            const clear = el('button', 'alerts-clear'); clear.textContent = 'Dismiss all'; clear.onclick = () => alertOp({ op: 'clear' });
            head.append(clear); wrap.append(head);
            fresh.slice(0, 8).forEach(a => {
                /* Report, don't shred: a record from before the banner's fields were
                   settled still has a title or a detail, and a row that shows a dot
                   and a tilde has told the reader nothing. */
                const label = a.metric || a.title || a.detail || 'A change was recorded without a description';
                const lowerBetter = /position|at risk|unfulfilled|low stock|cpc|bounce/i.test(label);
                const good = a.pct == null ? null : (lowerBetter ? a.pct < 0 : a.pct > 0);
                const dir = good == null ? 'flat' : good ? 'up' : 'down';
                const row = el('div', 'alert-row');
                /* A size-list alert had nowhere to go: the only controls were
                   snooze and dismiss, while the actual fix lived in a CSV on the
                   volume. Dismissing it did not resolve anything - the model came
                   back on the next scan. Now the metric itself opens the size
                   check that can settle it. */
                let metric;
                if (/size list/i.test(label)) {
                    metric = textLink(null, { size: 'inline', cls: 'a-metric' });
                    metric.textContent = label;
                    metric.title = 'Open the size check and resolve this';
                    metric.onclick = () => { setView('labels'); runCoverage(); };
                } else if (a.tab === 'settings' && /privacy requests/i.test(label)) {
                    /* Where the request is dealt with, not just a notice of it. */
                    metric = textLink(null, { size: 'inline', cls: 'a-metric' });
                    metric.textContent = label;
                    metric.title = 'Open Settings, Privacy requests';
                    metric.onclick = openPrivacyRequests;
                } else {
                    metric = el('span', 'a-metric', label);
                }
                row.append(el('span', 'adot ' + dir), el('span', 'a-tab', a.tab_label || a.kind || ''), metric);
                /* A change has its percentage; an alert that is not a change
                   (Shopify down, a size list gap, a Xero sync run) has none,
                   rather than a tilde standing in for one. */
                if (a.pct != null) row.append(el('span', 'a-pct ' + dir, (a.pct > 0 ? '+' : '') + a.pct + '%'));
                const x = iconButton(I.x, 'Dismiss', { size: 'small' }); x.onclick = () => alertOp({ op: 'dismiss', id: a.id });
                row.append(x); wrap.append(row);
            });
            return wrap;
        }
