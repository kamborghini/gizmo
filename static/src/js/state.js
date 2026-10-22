        /* ---------- state + storage ---------- */
        const LS = 'sc_convos_v1';
        /* Whose cached work is in this browser. The chat history, the store
           profile and the overview layout live in localStorage so the desk
           survives a reload - and on a shared dispatch PC they survived the
           person, too: sign out, next person signs in, and the sidebar still
           listed "top 20 customers by lifetime spend" with the answer in it.
           Nothing server-side was bypassed; the data was simply never removed.
           The owner is stamped on sign-in and the cache is dropped whenever it
           belongs to somebody else. */
        const LS_OWNER = 'sc_cache_owner_v1';
        let convos = [];
        let activeId = null;
        let deep = false;
        /* An answer being worked on, by conversation: when it started, the
           step it has reached, and its Stop. One page-wide busy flag meant no
           other conversation could be asked in meanwhile, and opening another
           one lost the spinner for good. */
        const pending = {};
        /* Entrance motion belongs to an ARRIVAL. A tab fades its content in the
           first time that content lands; every later paint of the same tab - a
           refresh, a Customize toggle, a return from another tab - is the same
           page redrawn, and half a second of fade over something the reader is
           already reading reads as a fault rather than as polish. */
        const _viewPainted = Object.create(null);
        function firstPaint(view) { if (_viewPainted[view]) return false; _viewPainted[view] = true; return true; }
        const MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
        const readConvos = () => { try { const v = JSON.parse(localStorage.getItem(LS) || '[]'); return Array.isArray(v) ? v.filter(c => c && c.id && Array.isArray(c.turns)) : []; } catch (e) { return []; } };
        convos = readConvos().filter(c => c.turns.length);
        convos.forEach(c => { if (!c.updated) c.updated = c.ts || 0; });
        convos.sort((a, b) => (b.updated || 0) - (a.updated || 0));
        /* The conversation that was open, for a reload in the same tab. */
        try { const a = sessionStorage.getItem('sc_active_convo'); if (a && convos.some(c => c.id === a)) activeId = a; } catch (e) {}
        const goneConvos = new Set();   // deleted here, so a merge does not bring them back
        /* Conversations live in this browser, so every tab shares one copy,
           and each wrote its whole list back: the last to save wiped what the
           other had added. A save folds in what is stored, keeping the newer
           copy of each conversation, and one still being answered here. */
        function mergeConvos(mine, theirs) {
            const byId = new Map();
            theirs.forEach(c => { if (!goneConvos.has(c.id)) byId.set(c.id, c); });
            mine.forEach(c => {
                const o = byId.get(c.id);
                if (!o || pending[c.id] || (c.updated || 0) >= (o.updated || 0)) byId.set(c.id, c);
            });
            return [...byId.values()].sort((a, b) => (b.updated || 0) - (a.updated || 0));
        }
        /* A full store is made room in, and said: an answer used to appear
           and never be written, and was gone after a reload. First what was
           read for older answers goes (their figures stay), then the oldest
           conversations. */
        let saveWarned = false;
        function save() {
            convos = mergeConvos(convos, readConvos());
            const write = (list) => localStorage.setItem(LS, JSON.stringify(list.filter(c => c.turns.length)));
            try { write(convos); return true; } catch (e) {}
            /* Every answer's previews except the newest few of the open
               conversation: short conversations were never trimmed, so old
               ones were deleted while room was there to be had. */
            convos.forEach(c => c.turns.filter(t => t.role === 'assistant').slice(0, c.id === activeId ? -3 : undefined).forEach(t => {
                (t.data_used || []).forEach(d => { d.preview = 'Not kept on this computer, to make room.'; });
            }));
            try { write(convos); return true; } catch (e) {}
            const keep = convos.slice();
            for (let dropped = 1; dropped < convos.length; dropped++) {
                const i = keep.map((c, k) => k).reverse().find(k => keep[k].turns.length && keep[k].id !== activeId && !pending[keep[k].id]);
                if (i == null) break;
                keep.splice(i, 1);
                try {
                    write(keep); convos = keep;
                    toastError('This computer\u2019s space for conversations was full, so the ' + (dropped === 1 ? 'oldest one was' : dropped + ' oldest were') + ' removed to keep this one.');
                    renderSidebar();
                    return true;
                } catch (e) {}
            }
            if (!saveWarned) { saveWarned = true; toastError('This conversation could not be kept on this computer: its storage is full. Delete some old conversations.'); }
            return false;
        }
        /* Another tab saved: take its list, keeping what is still being
           answered here, and the empty one being written in. */
        window.addEventListener('storage', (e) => {
            if (e.key !== LS) return;
            const was = active(), n = was ? was.turns.length : -1;
            convos = mergeConvos(convos.filter(c => !c.turns.length || pending[c.id]), readConvos());
            if (activeId && !active()) { activeId = null; rememberActive(); }
            renderSidebar();
            const now = active();
            if ((now ? now.turns.length : -1) !== n || now !== was) { if (!(now && pending[now.id])) renderChat(true); }
        });

        const LS_SET = 'sc_profile_v1';
        const DEFAULT_PREFS = { track_inventory: true, concise: false, proactive: true, flag_anomalies: true };
        let profile = { brand_voice: '', business_goals: '', strategy: '', notes: '', prefs: Object.assign({}, DEFAULT_PREFS) };
        try { profile = Object.assign(profile, JSON.parse(localStorage.getItem(LS_SET) || '{}')); } catch (e) {}
        profile.prefs = Object.assign({}, DEFAULT_PREFS, profile.prefs || {});
        const cacheProfile = () => { try { localStorage.setItem(LS_SET, JSON.stringify(profile)); } catch (e) {} };
        async function loadProfile() {
            try {
                const d = await api('/api/profile', {});
                if (d && d.profile) { profile = Object.assign(profile, d.profile); profile.prefs = Object.assign({}, DEFAULT_PREFS, d.profile.prefs || {}); cacheProfile(); }
            } catch (e) { /* keep cached profile */ }
        }
        /* keepChats: a sign-out or an expired session keeps the person's
           conversations in this browser. Wiping them lost a weekend's worth
           to a Monday sign-in; claimLocalCache still drops them the moment
           somebody else signs in here. */
        function clearLocalCache(keepChats) {
            /* sc_ov_layout_v1 is the old Overview's KPI order, which nothing
               reads since that page went (22 Oct 2026): cleared like the rest. */
            [LS, LS_SET, LS_OWNER, 'sc_ov_layout_v1'].forEach(k => {
                if (keepChats && (k === LS || k === LS_OWNER)) return;
                try { localStorage.removeItem(k); } catch (e) {}
            });
        }
        /* Called the moment the app knows who is signed in. A different owner
           (or none recorded, which is the state a pre-fix browser is in) means
           the cache is not theirs: drop it and reload, so no in-memory copy of
           the previous session's answers survives either. */
        function claimLocalCache(id) {
            if (!id) return;
            /* The layouts are read here, the moment the app knows who is signed
               in, and not at start-up: a sign-in from the login screen does not
               reload the page, so a read made before it failed and left
               Customize switched off for the whole session, and a different
               person signing in would have been shown the last person's
               arrangement. The migration runs once they have arrived. */
            Promise.resolve().then(wgLoadLayouts);
            let owner = null;
            try { owner = localStorage.getItem(LS_OWNER); } catch (e) { return; }
            if (owner === id) return;
            const hadCache = (() => {
                try { return Boolean(localStorage.getItem(LS) || localStorage.getItem(LS_SET)); }
                catch (e) { return false; }
            })();
            clearLocalCache();
            try { localStorage.setItem(LS_OWNER, id); } catch (e) {}
            if (hadCache) { location.reload(); return; }
            convos = []; activeId = null;
            profile = { brand_voice: '', business_goals: '', strategy: '', notes: '',
                        prefs: Object.assign({}, DEFAULT_PREFS) };
            renderSidebar(); renderChat();
        }

        const active = () => convos.find(c => c.id === activeId);
        const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

