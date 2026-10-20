        /* ---------- camera test (a throwaway, 20 Oct 2026) ----------
           Before the stock sheet moves into Reactor: can a phone's camera
           scan shelf labels from inside the Shopify admin? Two ways are tried
           and what happened is shown in plain words, for the owner to report:
           - Shopify's own scanner (App Bridge shopify.scanner.capture), one
             label per press, documented for Shopify POS;
           - the page opening the camera itself (getUserMedia), reading labels
             with the browser's own barcode reader where it has one, the way
             the stock sheet's tally scanning works today.
           Nothing is saved or sent. Delete this section, its row in Settings,
           its styles and its tests once phone scanning is decided. */
        function cameraTestReason(e) {
            if (!e) return 'no reason given';
            return ((e.name ? e.name + ': ' : '') + (e.message || '')).trim() || String(e);
        }
        function openCameraTest(opener) {
            let stream = null, timer = null;
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
            liveBtn.onclick = async () => {
                if (stream) { stopCamera(); liveBtn.textContent = 'Try the live camera'; note('Live camera: stopped.'); return; }
                if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)) {
                    note('Live camera: this browser offers no camera to the page.'); return;
                }
                liveBtn.disabled = true;
                try {
                    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
                } catch (e) {
                    liveBtn.disabled = false;
                    note('Live camera: did not open (' + cameraTestReason(e) + ').');
                    return;
                }
                liveBtn.disabled = false;
                video.srcObject = stream;
                video.hidden = false;
                try { await video.play(); } catch (e) { /* muted inline video: the frames still arrive */ }
                liveBtn.textContent = 'Stop the camera';
                note('Live camera: opened.');
                if (!('BarcodeDetector' in window)) {
                    note('Live camera: this browser has no barcode reader of its own, so labels are not read here '
                        + '(the stock sheet brings its own reader for this).');
                    return;
                }
                let reader;
                try {
                    const can = BarcodeDetector.getSupportedFormats ? await BarcodeDetector.getSupportedFormats() : [];
                    const want = ['code_39', 'code_128', 'ean_13', 'qr_code'].filter(f => !can.length || can.indexOf(f) >= 0);
                    reader = new BarcodeDetector(want.length ? { formats: want } : undefined);
                } catch (e) { note('Live camera: the barcode reader would not start (' + cameraTestReason(e) + ').'); return; }
                const seen = {};
                timer = setInterval(async () => {
                    if (!stream) return;
                    try {
                        const found = await reader.detect(video);
                        found.forEach(c => {
                            const now = Date.now();
                            if (!seen[c.rawValue] || now - seen[c.rawValue] > 1400) {   // one label held still counts once
                                seen[c.rawValue] = now;
                                note('Live camera: read ' + c.rawValue + '.');
                            }
                        });
                    } catch (e) { /* a frame not ready yet */ }
                }, 250);
            };
            const copyBtn = textButton('Copy the results');
            copyBtn.onclick = async () => {
                const text = facts.map(f => f[0] + ': ' + f[1]).concat(log).join('\n');
                try { await navigator.clipboard.writeText(text); addToast('Copied. Paste it into your message.', 'good'); }
                catch (e) { toastError('Copying did not work here: read the lines out instead.'); }
            };
            acts.append(shopifyBtn, liveBtn, copyBtn);
            body.append(acts, video, results);
        }
