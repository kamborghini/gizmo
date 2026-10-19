// The proof's shots (make css-proof): every measured state's fingerprint,
// written to CSS_PROOF_OUT. Skipped unless that is set, so the browser suite
// itself never runs it.
const fs = require('fs');
const zlib = require('zlib');
const path = require('path');
const { test } = require('@playwright/test');
const S = require('./support');
const C = require('./computed');
const SCREENS = require('./screens');

const OUT = process.env.CSS_PROOF_OUT;
for (const s of SCREENS) {
  test(s.id, async ({ page, context, baseURL }, info) => {
    test.skip(!OUT, 'the proof runs only from make css-proof');
    const only = process.env.CSS_PROOF_ONLY;
    test.skip(!!only && !new RegExp(only).test(info.project.name + '-' + s.id), 'not asked for');
    await S.prepare(context, baseURL);
    const w = S.watch(page, baseURL);
    await S.open(page, w);
    const h = S.helpers(page, w, info.project.name);
    await s.go(page, h);
    await S.settle(page, w);
    const f = await C.fingerprint(page);
    fs.mkdirSync(OUT, { recursive: true });
    // Gzipped: a state's fingerprint is some 9 MB of much-repeated text, 108 of them a run.
    fs.writeFileSync(path.join(OUT, `${info.project.name}-${s.id.replace(/~/g, '-')}.json.gz`), zlib.gzipSync(JSON.stringify(f)));
  });
}
