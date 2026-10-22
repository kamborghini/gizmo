        /* ---------- sidebar groups fold ----------
           Each group heading is a toggle, as the reference's collapsible
           sidebar groups are: the chevron on its right turns to point down
           when the group is open, the section under it hides when it is not,
           and the choice is remembered per group. Opening a page inside a
           folded group unfolds it, so a search or a link never lands on a
           highlighted item you cannot see. */
        const LS_NAVGROUPS = 'sc_navgroups_v1';
        function navGroupState() { try { return JSON.parse(localStorage.getItem(LS_NAVGROUPS)) || {}; } catch (e) { return {}; } }
        function setNavGroup(name, open, remember) {
            const btn = document.querySelector('.nav-group[data-group="' + name + '"]');
            const sect = $('nav-sect-' + name);
            if (!btn || !sect) return;
            btn.setAttribute('aria-expanded', open ? 'true' : 'false');
            sect.hidden = !open;
            try { paintGuideDots(); syncSideFade(); } catch (e) { /* before the guide's state exists, at boot */ }
            if (remember) { const st = navGroupState(); st[name] = open; try { localStorage.setItem(LS_NAVGROUPS, JSON.stringify(st)); } catch (e) {} }
        }
        function syncNavGroups() {
            /* A group with nothing an account may open is not shown at all,
               heading included; otherwise the heading shows and the section
               follows the remembered choice, open by default. */
            const st = navGroupState();
            document.querySelectorAll('.nav-group[data-group]').forEach(btn => {
                const name = btn.dataset.group, sect = $('nav-sect-' + name);
                if (!sect) return;
                const any = [...sect.querySelectorAll('.nav-item')].some(n => n.style.display !== 'none');
                btn.style.display = any ? '' : 'none';
                setNavGroup(name, any && st[name] !== false, false);
                if (!any) sect.hidden = true;
            });
        }
        function initNavGroups() {
            document.querySelectorAll('.nav-group[data-group]').forEach(btn => {
                const caret = el('span', 'nav-caret'); caret.innerHTML = I.chev; caret.setAttribute('aria-hidden', 'true');
                btn.append(caret);
                btn.onclick = () => setNavGroup(btn.dataset.group, btn.getAttribute('aria-expanded') !== 'true', true);
            });
            syncNavGroups();
        }
        function revealNavItem(v) {
            const n = $('nav-' + v); const sect = n && n.closest('.nav-sect');
            if (sect && sect.hidden) setNavGroup(sect.id.replace('nav-sect-', ''), true, true);
            /* The page you are on stays in sight in a sidebar that scrolls. */
            if (n && n.offsetParent) n.scrollIntoView({ block: 'nearest' });
        }
        function syncSideFade() {
            const b = document.querySelector('.side-body');
            if (b) b.classList.toggle('more-below', b.scrollTop + b.clientHeight < b.scrollHeight - 4);
        }
        const BETA_TABS = ['forecast', 'crm', 'connector'];
        function setView(v) {
            document.querySelectorAll('.nav-item').forEach(n => {
                const on = n.dataset.view === v; n.classList.toggle('active', on);
                if (on) n.setAttribute('aria-current', 'page'); else n.removeAttribute('aria-current');
            });
            revealNavItem(v);
            // Leaving a view while customizing it counts as Done.
            if (wgEdit && wgEdit.view !== v) wgCommit(wgEdit.view, true);
            APP_VIEWS.forEach(name => $('view-' + name).classList.toggle('active', v === name));
            const titles = { liability: 'Liability', forecast: 'Forecast', sizes: 'Size list', connector: 'Xero sync', crm: 'CRM', loans: 'Loan units', mail: 'Inbox', files: 'Files', team: 'Team', labels: 'Production Manager', memory: 'Memory', skills: 'Skills', guide: 'Guide' };
            setViewTitle(titles[v] || 'Chat');
            setViewCrumb(v);
            document.body.dataset.view = v;
            const act = $('topbar-action'); act.innerHTML = '';
            if (v === 'guide') renderGuide();
            // Only offer the PDF when there is something to print: a conversation
            // with at least one turn (the report pages that also printed are gone).
            $('print-btn').style.display = (v === 'chat' && printableCache(v)) ? '' : 'none';
            /* The app's header carries only what is global, as the reference's
               does: each report's Refresh sits in its own page header now,
               beside the stamp it renews (heroAct). Chat's New chat stays. */
            if (v === 'chat') {
                act.append(ico(I.plus), document.createTextNode('New chat')); act.className = 'btn btn-primary'; act.onclick = () => newConvo(); renderChat();
                /* The applied skills' names: after a reload the list had not
                   been read, so the chip said 'A skill'. */
                if (!skills.length && tabAllowed('skills')) loadSkills();
            }
            /* The conversation list sits under all nineteen pages, below the
               fold of the sidebar with its scrollbar hidden. Opening Chat
               brings it into view, since that is where it is used. */
            if (v === 'chat') {
                const sb = document.querySelector('.side-body'), ch = $('convos');
                if (sb && ch && ch.children.length) {
                    const head = ch.previousElementSibling || ch;
                    const top = head.getBoundingClientRect().top - sb.getBoundingClientRect().top + sb.scrollTop;
                    if (top + head.offsetHeight > sb.scrollTop + sb.clientHeight - 40) sb.scrollTop = Math.max(0, top - 8);
                }
            }
            /* Shown only when one of those branches actually put something in
               it. The rule here used to NAME the views that wanted it hidden,
               so every tab added afterwards - Loan units among them - arrived
               with an empty 26px button sitting in the corner. */
            act.style.display = act.innerHTML ? '' : 'none';
            closeSidebar();
            if (v === 'liability') showLiabilityView();
            if (v === 'crm') showCRMView();
            if (v === 'loans') showLoansView();
            if (v === 'mail') showMailView();
            if (v === 'files') showFilesView();
            if (v === 'team') showTeamView();
            if (v === 'labels') showLabelsView();
            if (v === 'memory') loadMemory();
            if (v === 'skills') loadSkills();
            if (v === 'forecast') showForecastView();
            if (v === 'sizes') showSizesView();
            if (v === 'connector') showConnectorView();
            /* A hidden view has no width, so its columns are measured now it
               shows. A render that is still on its way is arranged by the
               layer's observer when it lands. */
            if (WG_VIEWS.indexOf(v) >= 0) wgArrange(v);
        }

