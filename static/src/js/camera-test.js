        /* ---------- camera test (a throwaway, 20 Oct 2026) ----------
           Before the stock sheet moves into Reactor: can a phone's camera
           scan shelf labels from inside the Shopify admin? Two ways are tried
           and what happened is shown in plain words, for the owner to report:
           - Shopify's own scanner (App Bridge shopify.scanner.capture), one
             label per press, documented for Shopify POS;
           - the page opening the camera itself (getUserMedia), reading labels
             with the browser's own barcode reader where it has one, the way
             the stock sheet's tally scanning works today.
           The second round (23 Oct, the stock design's section 6) adds what
           the scanner will lean on: the reader the page brings for a phone
           without one (the stock app's own, loaded only when asked), the beep
           and buzz a label gives, and keeping the screen awake while the
           camera is open.
           The reader, the beep and the buzz live with the Stock tab's scanner
           (stock-scan.js), which this test calls. Nothing is saved or sent.
           Delete this section, its row in Settings, its styles and its tests
           once phone scanning is decided. */
        function cameraTestReason(e) {
            if (!e) return 'no reason given';
            return ((e.name ? e.name + ': ' : '') + (e.message || '')).trim() || String(e);
        }
        function openCameraTest(opener) {
            let stream = null, timer = null, wake = null;
            const video = document.createElement('video');
            video.className = 'camera-test-video';
            video.setAttribute('playsinline', '');   // an iPhone plays it in place, not full screen
            video.muted = true;
            video.hidden = true;
            const stopCamera = () => {
                if (timer) clearInterval(timer);
                timer = null;
                if (stream) stream.getTracks().forEach(t => t.stop());
                stream = null;
                video.srcObject = null;
                video.hidden = true;
                if (wake) { wake.release().catch(() => {}); wake = null; }
            };
            const win = dialog({ title: 'Camera test', opener: opener, onClose: stopCamera });
            const body = win.body;
            body.append(el('p', 'field-help', 'Checks whether this phone can scan shelf labels from inside Reactor. '
                + 'Nothing is saved or sent.'));
            const sh = typeof shopify !== 'undefined' ? shopify : null;
            const policy = document.permissionsPolicy || document.featurePolicy;
            const allowed = policy && policy.allowsFeature ? policy.allowsFeature('camera') : null;
            const facts = [
                ['Opened in', sh && sh.environment && sh.environment.mobile ? 'the Shopify app' : 'a web browser'],
                ['Camera allowed on this page', allowed == null ? 'cannot tell' : allowed ? 'yes' : 'no'],
                ['Camera offered by this browser', navigator.mediaDevices && navigator.mediaDevices.getUserMedia ? 'yes' : 'no'],
                ['Barcode reader built into this browser', 'BarcodeDetector' in window ? 'yes' : 'no'],
                ["Shopify's scanner offered", sh && sh.scanner && sh.scanner.capture ? 'yes' : 'no'],
                ['Buzz offered by this browser', navigator.vibrate ? 'yes' : 'no'],
                ['Keeping the screen awake offered', navigator.wakeLock ? 'yes' : 'no'],
            ];
            const factList = el('ul', 'camera-test-lines');
            facts.forEach(f => factList.append(el('li', null, f[0] + ': ' + f[1])));
            body.append(factList);
            const results = el('ul', 'camera-test-lines');
            results.setAttribute('aria-live', 'polite');
            const log = [];
            const note = (text) => { log.push(text); results.append(el('li', null, text)); };

            const acts = el('div', 'camera-test-acts');
            const shopifyBtn = textButton("Try Shopify's scanner");
            shopifyBtn.onclick = async () => {
                if (!(sh && sh.scanner && sh.scanner.capture)) { note("Shopify's scanner: not offered here."); return; }
                shopifyBtn.disabled = true;
                try {
                    const got = await sh.scanner.capture();
                    note("Shopify's scanner: worked, read " + ((got && got.data) || 'nothing') + '.');
                } catch (e) { note("Shopify's scanner: did not work (" + cameraTestReason(e) + ').'); }
                shopifyBtn.disabled = false;
            };
            const liveBtn = textButton('Try the live camera');
            const bundledBtn = textButton('Use the bundled reader');
            const camButtons = [liveBtn, bundledBtn];
            const label = (btn) => btn === liveBtn ? 'Try the live camera' : 'Use the bundled reader';
            const stopped = () => { stopCamera(); camButtons.forEach(b => { b.textContent = label(b); }); note('Live camera: stopped.'); };
            /* Each label held still counts once, then beeps and buzzes. */
            const seen = {};
            const heard = (how, code) => {
                const now = Date.now();
                if (seen[code] && now - seen[code] <= 1400) return;   // one label held still counts once
                seen[code] = now;
                const fb = labelBeep(true);
                note('Live camera (' + how + '): read ' + code + '.' + (fb.buzzed ? '' : ' No buzz on this phone.'));
            };
            const startCamera = async (btn, bundled) => {
                if (stream) { stopped(); return; }
                if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)) {
                    note('Live camera: this browser offers no camera to the page.'); return;
                }
                camButtons.forEach(b => { b.disabled = true; });
                try {
                    // A label's thin bars read better from a sharper picture, as the stock sheet asks.
                    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' },
                        width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
                } catch (e) {
                    const refused = e && (e.name === 'NotAllowedError' || e.name === 'SecurityError');
                    try {
                        if (refused) throw e;
                        stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
                        note('Live camera: opened only without the sharper picture (' + cameraTestReason(e) + ').');
                    } catch (e2) {
                        camButtons.forEach(b => { b.disabled = false; });
                        note('Live camera: did not open (' + cameraTestReason(e2) + ').');
                        return;
                    }
                }
                camButtons.forEach(b => { b.disabled = false; });
                video.srcObject = stream;
                video.hidden = false;
                try { await video.play(); } catch (e) { /* muted inline video: the frames still arrive */ }
                btn.textContent = 'Stop the camera';
                note('Live camera: opened.');
                if (navigator.wakeLock) {
                    try {
                        wake = await navigator.wakeLock.request('screen');
                        note('Keeping the screen awake: yes, while the camera is open.');
                    } catch (e) { note('Keeping the screen awake: did not work (' + cameraTestReason(e) + ').'); }
                } else {
                    note('Keeping the screen awake: not offered here.');
                }
                if (!stream) return;
                if (!bundled && 'BarcodeDetector' in window) {
                    let reader;
                    try {
                        const can = BarcodeDetector.getSupportedFormats ? await BarcodeDetector.getSupportedFormats() : [];
                        const want = ['code_39', 'code_128', 'ean_13', 'qr_code'].filter(f => !can.length || can.indexOf(f) >= 0);
                        reader = new BarcodeDetector(want.length ? { formats: want } : undefined);
                    } catch (e) { note('Live camera: the barcode reader would not start (' + cameraTestReason(e) + ').'); return; }
                    timer = setInterval(async () => {
                        if (!stream) return;
                        try {
                            const found = await reader.detect(video);
                            found.forEach(c => heard('built-in reader', c.rawValue));
                        } catch (e) { /* a frame not ready yet */ }
                    }, 250);
                    return;
                }
                if (!bundled) note('Live camera: this browser has no barcode reader of its own, so the bundled one is used.');
                let Z;
                try {
                    Z = await loadLabelReader();
                } catch (e) { note('Bundled reader: did not load (' + cameraTestReason(e) + ').'); return; }
                if (!stream) return;
                note('Bundled reader: loaded. Hold a shelf label in the middle of the picture.');
                const canvas = document.createElement('canvas');
                const cx = canvas.getContext('2d', { willReadFrequently: true });
                timer = setInterval(() => {
                    if (!stream) return;
                    const code = readLabelFrame(Z, video, canvas, cx);
                    if (code) heard('bundled reader', code);
                }, 130);
            };
            liveBtn.onclick = () => startCamera(liveBtn, false);
            bundledBtn.onclick = () => startCamera(bundledBtn, true);
            const beepBtn = textButton('Try the beep and buzz');
            beepBtn.onclick = () => {
                const fb = labelBeep(true);
                note('Beep: ' + (fb.beeped ? 'played (turn the sound up to hear it).' : 'this browser offers no sound.')
                    + ' Buzz: ' + (fb.buzzed ? 'asked the phone to buzz.' : "this phone's web pages cannot buzz."));
            };
            const copyBtn = textButton('Copy the results');
            copyBtn.onclick = async () => {
                const text = facts.map(f => f[0] + ': ' + f[1]).concat(log).join('\n');
                try { await navigator.clipboard.writeText(text); addToast('Copied. Paste it into your message.', 'good'); }
                catch (e) { toastError('Copying did not work here: read the lines out instead.'); }
            };
            acts.append(shopifyBtn, liveBtn, bundledBtn, beepBtn, copyBtn);
            body.append(acts, video, results);
        }
