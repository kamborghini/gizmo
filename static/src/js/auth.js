        /* ---------- auth (Shopify session token only; embedded-only) ---------- */
        async function authHeaders() {
            if (typeof shopify === 'undefined' || !shopify.idToken) {
                throw new Error('Open Reactor from inside your Shopify admin.');
            }
            const token = await shopify.idToken();
            return { 'Authorization': 'Bearer ' + token };
        }
        let memSession = '';   // storage can be blocked in some browsers; memory carries the page
        function appSession() { try { return localStorage.getItem('sc_app_session') || memSession; } catch (e) { return memSession; } }
        function setAppSession(t) { memSession = t || ''; try { t ? localStorage.setItem('sc_app_session', t) : localStorage.removeItem('sc_app_session'); } catch (e) {} }
        /* Which build this PAGE is running. A tab left open across a deploy
           keeps running the old JavaScript, which is invisible from the desk
           and looks exactly like a bug that has already been fixed. Every API
           reply carries the build the SERVER is on, and the two are compared. */
        const MY_BUILD = (() => {
            try {
                const m = document.querySelector('meta[name="app-build"]');
                return (m && m.getAttribute('content')) || '';
            } catch (e) { return ''; }
        })();
        let buildBar = null;
        function noteBuild(serverBuild) {
            if (!serverBuild || !MY_BUILD || serverBuild === MY_BUILD || buildBar) return;
            buildBar = el('div', 'build-bar');
            buildBar.append(el('span', null,
                'Reactor has been updated since this tab was opened, so it is still running the '
                + 'old version. Reload when you are between jobs.'));
            const go = el('button', 'btn btn-primary', 'Reload');
            go.onclick = () => location.reload();
            const later = el('button', 'btn', 'Not now');
            /* Dismissed for this tab only, and it comes back on the next open:
               nagging is worse than useless, but so is letting it be forgotten. */
            later.onclick = () => { buildBar.remove(); };
            buildBar.append(go, later);
            document.body.append(buildBar);
        }
        /* Why the last sign-out happened, for the login screen to say. */
        function takeAuthReason() {
            try { const r = sessionStorage.getItem('sc_auth_reason'); sessionStorage.removeItem('sc_auth_reason'); return r ? JSON.parse(r) : null; }
            catch (e) { return null; }
        }
        async function api(path, payload, opts) {
            opts = opts || {};
            const hdrs = Object.assign({ 'Content-Type': 'application/json' }, await authHeaders());
            const sess = appSession();
            if (sess) hdrs['X-App-Session'] = sess;
            let res;
            try {
                res = await fetch(path, {
                    method: 'POST',
                    headers: hdrs,
                    body: JSON.stringify(payload || {}),
                });
            } catch (e) {
                /* The connection dropped: the request may have arrived and been
                   acted on. The browser's own words ("Failed to fetch", "Load
                   failed") reached the person, and every caller read them as a
                   refusal: Send was offered again, Mark made said nothing had
                   changed. */
                const err = new Error('The connection dropped before the server answered. What you '
                    + 'asked for may or may not have gone through: check before trying again.');
                err.noReply = true;
                throw err;
            }
            try { noteBuild(res.headers.get('X-App-Build')); } catch (e) {}
            if (res.status === 401) {
                /* The door says WHY. A stale Shopify embed token is not a dead
                   session: App Bridge refreshes tokens by the browser's clock,
                   so a PC a minute out sends tokens the server sees as expired.
                   Fetch a fresh one and try once more; only a second rejection
                   is shown, and it is never a reload, because a fault that
                   survives a reload becomes a reload loop that trips the rate
                   window - which is exactly how this read at one desk. */
                let why = null;
                try { why = await res.clone().json(); } catch (e) { why = null; }
                const reason = (why && why.reason) || 'session';
                const text = (why && why.error) || 'Please log in.';
                if (reason === 'token' && !opts.retried) {
                    await new Promise(r => setTimeout(r, 1200));
                    return api(path, payload, { retried: true });
                }
                /* A starter password: the session is good, it just opens nothing
                   but the choose-your-own card until the password is changed.
                   Read as "expired", this wiped the session and reloaded, and
                   the first call made after signing in (the card layouts) did
                   exactly that, so a new account could never reach the card. */
                if (reason === 'must_change') {
                    authShow('change');
                    throw new Error(text);
                }
                if (!path.startsWith('/api/auth/')) {
                    /* Nobody was signed in to begin with: the boot's data calls
                       run before the sign-in check answers, and a refusal of a
                       request that carried no session is not an expired one. It
                       cost a reload, and greeted whoever sat down next, after a
                       deliberate Log out too, with "Your sign-in has expired".
                       The sign-in card is authBoot's to show. */
                    if (!sess && reason === 'session') throw new Error(text);
                    try { sessionStorage.setItem('sc_auth_reason', JSON.stringify({ reason, text })); } catch (e) {}
                    if (reason === 'token') {
                        authShow('login');
                        throw new Error(text);
                    }
                    setAppSession('');
                    clearLocalCache(true);
                    /* An expired session on an unattended machine leaves the
                       same residue a sign-out did. Reload rather than paint a
                       login screen over the last person's work - but once a
                       minute at most. */
                    let last = 0;
                    try { last = +sessionStorage.getItem('sc_auth_reload') || 0; } catch (e) {}
                    if (Date.now() - last > 60000) {
                        try { sessionStorage.setItem('sc_auth_reload', String(Date.now())); } catch (e) {}
                        location.reload();
                    } else {
                        authShow('login');
                    }
                }
                throw new Error(text);
            }
            if (res.status === 429) {
                /* A rate limit really does clear in seconds, but the daily AI
                   spend cap does not: telling someone to wait a moment when
                   the truth is "not until tomorrow, or raise the cap" sends
                   them round a loop. Routes that mean the latter say so. */
                let hard = null;
                try { hard = await res.clone().json(); } catch (e) { hard = null; }
                throw new Error(hard && hard.hard && hard.error ? hard.error
                    : 'The app is being asked for too much at once. Wait a few seconds and try again.');
            }
            let data;
            try { data = await res.json(); }
            catch (e) {
                // A gateway/proxy error page is not JSON: never show the parse error.
                /* A proxy 5xx says nothing about whether the request was
                   acted on: the container may have restarted after a courier
                   booking went through. Telling the person nothing had been
                   saved was a guess, and the wrong one for the dispatcher
                   who booked again. */
                const err = new Error(res.status >= 500
                    ? 'The server did not answer properly (error ' + res.status + '). What you asked for may or may not have gone through: check before trying again.'
                    : 'Unexpected reply from the server (status ' + res.status + '). Please try again.');
                err.noReply = true;
                throw err;
            }
            if (data.error) {
                const err = new Error(data.error);
                // The server may attach what it actually sent and what came back.
                if (data.tech) err.tech = data.tech;
                // Some refusals are recoverable by the caller insisting.
                if (data.can_force) err.canForce = true;
                throw err;
            }
            return data;
        }

