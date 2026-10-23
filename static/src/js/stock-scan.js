        /* ---------- Stock: scanning shelf labels ----------
           The camera window the stock list counts with, and what it reads
           labels with: the browser's own barcode reader where it has one,
           else the reader the page brings (the stock app's own, vendored in
           static/vendor/zxing and fetched only when needed), the beep and the
           buzz a label gives, the screen kept awake while it is open, and the
           help when the camera is refused. The camera test in Settings calls
           the reader, the beep and the buzz here. */
        /* The bundled reader, fetched the first time a phone needs it: the
           shell names its URL, so the page never carries it up front. */
        let labelReaderLoad = null;
        function loadLabelReader() {
            if (window.ZXing) return Promise.resolve(window.ZXing);
            if (labelReaderLoad) return labelReaderLoad;
            const meta = document.querySelector('meta[name="label-reader"]');
            if (!meta) return Promise.reject(new Error('this page names no reader'));
            labelReaderLoad = new Promise((resolve, reject) => {
                const s = document.createElement('script');
                s.src = meta.content;
                s.onload = () => {
                    if (window.ZXing) { resolve(window.ZXing); return; }
                    labelReaderLoad = null;
                    reject(new Error('the reader did not start'));
                };
                s.onerror = () => { labelReaderLoad = null; reject(new Error('the reader did not load')); };
                document.head.append(s);
            });
            return labelReaderLoad;
        }
        /* One frame read the way the stock sheet reads labels today: Code 39,
           with both binarizers (even light, then uneven), over the whole frame
           and then the middle band where a label is usually held. */
        function readLabelFrame(Z, video, canvas, cx) {
            const tryRead = () => {
                for (const Bin of [Z.GlobalHistogramBinarizer, Z.HybridBinarizer]) {
                    try {
                        const r = new Z.Code39Reader().decode(new Z.BinaryBitmap(new Bin(new Z.HTMLCanvasElementLuminanceSource(canvas))));
                        if (r && r.getText()) return r.getText();
                    } catch (e) { /* nothing in this frame */ }
                }
                return null;
            };
            const vw = video.videoWidth || 0, vh = video.videoHeight || 0;
            if (!vw || !vh) return null;
            canvas.width = vw; canvas.height = vh;
            cx.drawImage(video, 0, 0, vw, vh);
            const whole = tryRead();
            if (whole) return whole;
            const cw = Math.max(2, (vw * 0.9) | 0), ch = Math.max(2, (vh * 0.5) | 0);
            canvas.width = cw; canvas.height = ch;
            cx.drawImage(video, ((vw - cw) / 2) | 0, ((vh - ch) / 2) | 0, cw, ch, 0, 0, cw, ch);
            return tryRead();
        }
        /* The beep and the buzz a read label gives, as the stock sheet does:
           in a workshop nobody is looking at the screen. Says which happened. */
        function labelBeep(good) {
            let buzzed = false, beeped = false;
            try { if (navigator.vibrate) buzzed = navigator.vibrate(good ? 35 : [40, 70, 40]); } catch (e) { /* no buzz */ }
            try {
                const C = window.AudioContext || window.webkitAudioContext;
                if (C) {
                    const ctx = labelBeep.ctx || (labelBeep.ctx = new C());
                    if (ctx.state === 'suspended') ctx.resume();
                    const o = ctx.createOscillator(), g = ctx.createGain(), t = ctx.currentTime;
                    o.type = 'sine';
                    o.frequency.value = good ? 880 : 200;
                    g.gain.setValueAtTime(0.0001, t);
                    g.gain.exponentialRampToValueAtTime(good ? 0.22 : 0.3, t + 0.012);
                    g.gain.exponentialRampToValueAtTime(0.0001, t + (good ? 0.14 : 0.3));
                    o.connect(g); g.connect(ctx.destination);
                    o.start(t); o.stop(t + (good ? 0.15 : 0.31));
                    beeped = true;
                }
            } catch (e) { /* no sound */ }
            return { buzzed: !!buzzed, beeped: beeped };
        }
        /* One label held in view counts once every 1.4 seconds, as the stock
           app counts it; a different label counts at once. */
        function stockScanCounts(seen, code, now) {
            if (code === seen.code && now - seen.at < 1400) return false;
            seen.code = code; seen.at = now;
            return true;
        }
        /* The screen kept awake while the camera is open, let go when it closes. */
        let stockScanLock = null;
        async function stockScanWake(on) {
            try {
                if (on && !stockScanLock && navigator.wakeLock) stockScanLock = await navigator.wakeLock.request('screen');
                else if (!on && stockScanLock) { const w = stockScanLock; stockScanLock = null; await w.release(); }
            } catch (e) { stockScanLock = null; }   // refused or already let go: the screen sleeps as it would
        }
        function stockScanCameraWords(e) {
            const name = (e && e.name) || '';
            if (name === 'NotFoundError') return 'No camera was found on this device.';
            if (name === 'NotReadableError' || name === 'AbortError') return 'The camera is busy in another app. Close it and try again.';
            return 'The camera did not open' + (name ? ' (' + name + ')' : '') + '. Check the camera permission for this page and try again.';
        }
        async function stockScanCameraState() {
            try { const s = await navigator.permissions.query({ name: 'camera' }); return s.state || 'unknown'; }
            catch (e) { return 'unknown'; }
        }
        /* The camera opened, or the help when it was refused. opts: { title,
           continuous, onCode(code) answering { ok, text }, onClose }. */
        async function openStockScanner(opener, opts) {
            if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)) {
                toastError('Scanning needs the camera, and this browser does not offer it to the page.');
                return;
            }
            const retry = () => openStockScanner(opener, opts);
            let stream = null;
            try {
                stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
            } catch (e1) {
                const n1 = (e1 && e1.name) || '';
                if (n1 === 'NotAllowedError' || n1 === 'SecurityError') { stockScanHelp(await stockScanCameraState(), n1, retry, opener); return; }
                /* Some phones refuse the size and facing hints: once more, plain. */
                try { stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false }); }
                catch (e2) {
                    const n2 = (e2 && e2.name) || '';
                    if (n2 === 'NotAllowedError' || n2 === 'SecurityError') { stockScanHelp(await stockScanCameraState(), n2, retry, opener); return; }
                    toastError(stockScanCameraWords(e2));
                    return;
                }
            }
            stockScanWindow(opener, opts, stream);
        }
        /* The camera window: the picture with its frame, what to do, the last
           label read, and Done. One label held still counts once every 1.4s. */
        function stockScanWindow(opener, opts, stream) {
            let stopped = false, timer = null;
            const seen = { code: '', at: 0 };
            const video = el('video', 'stk-scan-video');
            video.setAttribute('playsinline', ''); video.muted = true;
            const stop = () => {
                if (stopped) return;
                stopped = true;
                if (timer) clearInterval(timer);
                if (stream) stream.getTracks().forEach(t => t.stop());
                video.srcObject = null;
                stockScanWake(false);
                if (opts.onClose) opts.onClose();
            };
            const win = dialog({ title: opts.title || 'Scan a label', size: 'stk-scan', overlayClass: 'stk-scan-ov', bodyClass: 'stk-scan-body', opener: opener, onClose: stop });
            const view = el('div', 'stk-scan-view');
            view.append(video, el('div', 'stk-scan-frame'));
            const hint = el('p', 'stk-scan-hint', stream ? 'Point the camera at the barcode' : 'Point the camera at the barcode');
            const log = el('p', 'stk-scan-log');
            log.setAttribute('aria-live', 'polite');
            log.hidden = true;
            win.body.append(view, hint, log);
            const done = textButton(opts.continuous ? 'Done' : 'Cancel', { kind: opts.continuous ? 'primary' : null });
            done.type = 'button';
            done.onclick = () => win.close();
            win.foot().append(done);
            const hit = (code) => {
                if (stopped || !code) return;
                code = String(code);
                if (!opts.continuous) { win.close(); opts.onCode(code); return; }
                if (!stockScanCounts(seen, code, Date.now())) return;
                let r = null;
                try { r = opts.onCode(code); } catch (e) { r = null; }
                const ok = !(r && r.ok === false);
                labelBeep(ok);
                log.hidden = false;
                log.classList.toggle('stk-miss', !ok);
                log.textContent = (r && r.text) || code;
            };
            if (!stream) return win;
            video.srcObject = stream;
            video.play().catch(() => { /* a muted inline picture still gives its frames */ });
            stockScanWake(true);
            stockScanReader(video, () => stopped, hint).then(read => {
                if (!read || stopped) return;
                timer = setInterval(async () => { if (stopped) return; const c = await read(); if (c) hit(c); }, 130);
            });
            return win;
        }
        /* The browser's own reader where it reads Code 39; else the one the
           page brings (loadLabelReader and readLabelFrame, above). */
        async function stockScanReader(video, gone, hint) {
            let can = null;
            if ('BarcodeDetector' in window) { try { can = await BarcodeDetector.getSupportedFormats(); } catch (e) { can = null; } }
            if (can && can.indexOf('code_39') >= 0) {
                try {
                    const det = new BarcodeDetector({ formats: ['code_39', 'code_128', 'ean_13', 'ean_8', 'upc_a', 'upc_e', 'qr_code'].filter(f => can.indexOf(f) >= 0) });
                    return async () => { try { const f = await det.detect(video); return f && f[0] && f[0].rawValue; } catch (e) { return null; } };
                } catch (e) { /* fall through to the bundled reader */ }
            }
            hint.textContent = 'Loading the scanner…';
            let Z;
            try { Z = await loadLabelReader(); } catch (e) { toastError('The scanner did not load. Check the connection and try again.'); return null; }
            if (gone()) return null;
            hint.textContent = 'Point the camera at the barcode';
            const canvas = document.createElement('canvas'), cx = canvas.getContext('2d', { willReadFrequently: true });
            return async () => readLabelFrame(Z, video, canvas, cx);
        }
        /* Why the camera was refused, and what to do, for the four ways it is
           refused today, and a fifth: inside the Shopify app, where the camera
           is the Shopify app's own to allow. **words** are drawn bold. */
        function stockScanHelpModel(state, errName, ua) {
            const ios = /iPhone|iPad|iPod/.test(ua), android = /Android/.test(ua);
            const sh = typeof shopify !== 'undefined' ? shopify : null;
            const inShopify = !!(sh && sh.environment && sh.environment.mobile);
            const inApp = !inShopify && (/; wv\)/.test(ua) || /FBAN|FBAV|FB_IAB|Instagram|Line\/|Snapchat|Twitter|TikTok|GSA\//i.test(ua));
            const samsung = /SamsungBrowser/i.test(ua);
            const browser = inShopify ? 'Shopify app' : inApp ? 'in-app browser' : samsung ? 'Samsung Internet' : /CriOS/.test(ua) ? 'Chrome (iOS)'
                : /Chrome\/(\d+)/.test(ua) ? 'Chrome ' + ua.match(/Chrome\/(\d+)/)[1] : /Safari/.test(ua) ? 'Safari' : 'browser';
            const diag = (errName || '?') + ' · permission: ' + state + ' · ' + browser;
            if (inShopify) return { title: 'Allow the camera for the Shopify app',
                sub: 'Reactor opens inside the Shopify app, so the camera is the Shopify app’s to allow.',
                steps: [ios ? 'Open the iPhone’s **Settings › Apps › Shopify**' : 'Open **Settings › Apps › Shopify › Permissions**',
                        'Set **Camera** to **Allow**', 'Come back here and tap **Try again**'], extra: '', diag };
            if (inApp) return { title: 'Open this in your own browser',
                sub: 'This page is running inside another app’s built-in browser, which blocks the camera whatever your browser’s settings say.',
                steps: ['Tap the **⋮ or share icon** in this window', 'Choose **Open in Chrome** (or Open in browser)',
                        'Use the camera button from there, or copy the link into your browser yourself'], extra: '', diag };
            if (state === 'granted') return { title: 'Camera allowed, but still refused',
                sub: 'Permission looks granted, yet the browser refused the camera. This usually clears with a reload; if not, reset the site.',
                steps: ['**Reload this page** and tap Try again',
                        android ? 'If it persists: **⋮ › Settings › Site settings › Camera**, and check this site is not under Blocked'
                                : 'If it persists, take this site off your browser’s blocked camera list',
                        'Then open the site again and tap **Try again**'],
                extra: 'If it still fails, copy the small grey line at the foot of this window and send it on.', diag };
            if (state === 'denied') return { title: 'Camera access is blocked',
                sub: 'The browser has the camera turned off for this site, so it will not ask again until that is changed.',
                steps: ios ? ['Open the iPhone’s **Settings › Apps › Safari** (older iOS: Settings › Safari)', 'Set **Camera** to **Allow** (or Ask)', 'Come back here and tap **Try again**']
                    : android ? ['Tap the **padlock or ⓘ icon** by the web address, then **Permissions › Camera › Allow**',
                                 'No Camera entry there? Open **⋮ › Settings › Site settings › Camera**, find this site under **Blocked** and set it to Allow',
                                 'Come back and tap **Try again**']
                    : ['Open your browser’s site settings for this page', 'Set **Camera** to **Allow**', 'Tap **Try again**'],
                extra: android ? 'Still nothing? The browser app itself may be missing camera access: **Android Settings › Apps › ' + (samsung ? 'Samsung Internet' : 'Chrome') + ' › Permissions › Camera › Allow**.'
                    : ios ? 'Still nothing? Check **Settings › Apps › Safari › Camera** is not set to Deny.' : '', diag };
            return { title: 'Allow camera access', sub: 'The permission prompt was closed without choosing Allow.',
                steps: ['Tap **Try again** below', 'When the browser asks to use the camera, choose **Allow**',
                        android ? 'If no prompt appears: **⋮ › Settings › Site settings › Camera**, and check this site is not under Blocked'
                                : 'If no prompt appears, check Camera in your browser’s site settings'],
                extra: android ? 'Also check the browser app has camera access: **Android Settings › Apps › Chrome › Permissions › Camera**.' : '', diag };
        }
        function stockScanBold(text) {
            const p = document.createDocumentFragment();
            String(text).split('**').forEach((part, i) => { if (part) p.append(i % 2 ? el('b', null, part) : document.createTextNode(part)); });
            return p;
        }
        function stockScanHelp(state, errName, onRetry, opener, ua) {
            const m = stockScanHelpModel(state, errName, ua || navigator.userAgent);
            const win = dialog({ title: m.title, opener: opener, size: 'stk-help' });
            const sub = el('p', 'stk-help-sub'); sub.append(stockScanBold(m.sub));
            const steps = el('ol', 'stk-help-steps');
            m.steps.forEach(s => { const li = el('li'); li.append(stockScanBold(s)); steps.append(li); });
            win.body.append(sub, steps);
            if (m.extra) { const x = el('p', 'stk-help-sub'); x.append(stockScanBold(m.extra)); win.body.append(x); }
            const foot = win.foot();
            foot.classList.add('stk-help-foot');
            const close = textButton('Close'); close.type = 'button'; close.onclick = () => win.close();
            const again = textButton('Try again', { kind: 'primary' }); again.type = 'button';
            again.onclick = () => { win.close(); onRetry(); };
            foot.append(el('span', 'stk-diag', m.diag), close, again);
            return win;
        }
