// Shared by every browser spec: signing in, the network fence, the writes a
// screen makes just by being looked at, reaching a state, and settling.
const fs = require('fs');
const path = require('path');

const RUN = process.env.BROWSER_RUN || path.join(__dirname, '.run');
const INTER = require.resolve('@fontsource-variable/inter/files/inter-latin-wght-normal.woff2');
const FONT_URL = 'https://fonts.gstatic.com/reactor-suite/inter.woff2';

// A POST whose op names a change. The op is read word by word (snake_case or
// camelCase), so settings is a read and settings_save a write. The suite looks
// and never writes; the two writes the page makes by itself are swallowed in
// prepare() and skipped here.
const WRITE_VERBS = new Set(['add', 'save', 'create', 'update', 'delete', 'remove', 'set', 'done', 'undone', 'claim',
  'release', 'send', 'book', 'cancel', 'print', 'mark', 'queue', 'archive', 'won', 'lost', 'move', 'merge', 'link',
  'unlink', 'upload', 'reset', 'active', 'tabs', 'reply', 'state', 'request', 'seen', 'assign', 'snooze', 'dismiss',
  'clear', 'edit', 'rename', 'restore', 'import', 'sync', 'run', 'review', 'retry', 'approve', 'reject']);
const opWords = op => op.split(/[_\-\s]+|(?=[A-Z])/).map(w => w.toLowerCase()).filter(Boolean);

function auth() {
  return JSON.parse(fs.readFileSync(path.join(RUN, 'auth.json'), 'utf8'));
}

function isWrite(url, method, body) {
  if (method !== 'POST' || !body) return false;
  let b;
  try { b = JSON.parse(body); } catch (e) { return false; }
  if (/\/api\/updates$/.test(url) && b.op === 'seen') return false;
  if (/\/api\/layouts$/.test(url)) return false;
  return typeof b.op === 'string' && opWords(b.op).some(w => WRITE_VERBS.has(w));
}

async function prepare(context, baseURL) {
  const a = auth();
  const app = new URL(baseURL).host;
  const seen = { outside: [] };
  await context.addInitScript(([t, s, store]) => {
    window.shopify = { idToken: async () => t };
    try {
      localStorage.setItem('sc_app_session', s);
      for (const k of Object.keys(store)) localStorage.setItem(k, store[k]);
    } catch (e) {}
  }, [a.token, a.session, a.localStorage || {}]);
  // The fence: every other host is answered here or refused and named.
  await context.route(u => u.host !== app, async route => {
    const url = route.request().url();
    if (url.startsWith('https://fonts.googleapis.com/css2')) {
      return route.fulfill({ status: 200, contentType: 'text/css',
        body: `@font-face{font-family:'Inter';font-style:normal;font-weight:100 900;font-display:block;src:url(${FONT_URL}) format('woff2');}` });
    }
    if (url === FONT_URL) {
      return route.fulfill({ status: 200, contentType: 'font/woff2', body: fs.readFileSync(INTER), headers: { 'Access-Control-Allow-Origin': '*' } });
    }
    seen.outside.push(url.slice(0, 160));
    return route.abort();
  });
  // The writes a screen makes by being looked at: What's new and Requests
  // mark themselves seen; Customise saves a layout as it closes.
  await context.route(/\/api\/updates$/, async route => {
    if (/"op"\s*:\s*"seen"/.test(route.request().postData() || '')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true,"seen":{}}' });
    }
    return route.fallback();
  });
  await context.route(/\/api\/layouts$/, async route => {
    let b = {};
    try { b = JSON.parse(route.request().postData() || '{}'); } catch (e) {}
    if (['view', 'order', 'hidden', 'reset'].some(k => k in b)) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{"layouts":{}}' });
    }
    return route.fallback();
  });
  return seen;
}

function watch(page, baseURL) {
  const w = { inflight: 0, errors: [], failed: [], writes: [] };
  const mine = u => u.startsWith(baseURL);
  const rel = u => u.slice(baseURL.length);
  page.on('request', r => {
    if (!mine(r.url())) return;
    w.inflight++;
    if (isWrite(r.url(), r.method(), r.postData())) w.writes.push(rel(r.url()) + ' ' + (r.postData() || '').slice(0, 100));
  });
  const done = r => { if (mine(r.url())) w.inflight = Math.max(0, w.inflight - 1); };
  page.on('requestfinished', done);
  page.on('requestfailed', r => { done(r); if (mine(r.url())) w.failed.push('failed ' + rel(r.url())); });
  page.on('response', r => { if (mine(r.url()) && r.status() >= 400) w.failed.push(r.status() + ' ' + rel(r.url())); });
  page.on('pageerror', e => w.errors.push(String((e && e.message) || e).slice(0, 300)));
  page.on('console', m => {
    if (m.type() !== 'error') return;
    const at = (m.location() && m.location().url) || '';
    if (at && !mine(at)) return;                         // a fenced request: counted by the fence
    if (/^Failed to load resource/.test(m.text())) return; // the response itself is counted above
    w.errors.push(m.text().slice(0, 300));
  });
  return w;
}

async function settle(page, w) {
  await page.waitForFunction(() => document.fonts.status === 'loaded', null, { timeout: 15000 });
  const t0 = Date.now();
  for (let quiet = 0; quiet < 4 && Date.now() - t0 < 20000;) {
    await page.waitForTimeout(100);
    const busy = await page.evaluate(() => !![...document.querySelectorAll(
      '.view.active .thinking, .view.active .loader, .view.active .skeleton, [aria-busy="true"]')].find(e => e.offsetParent));
    quiet = w.inflight === 0 && !busy ? quiet + 1 : 0;
  }
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
}

async function open(page, w) {
  await page.goto('/');
  await page.waitForSelector('#nav-overview', { state: 'attached', timeout: 60000 });
  await settle(page, w);
}

// Ported from the local rig's helpers (Oct 2026), each followed by settle().
function helpers(page, w, project) {
  const s = () => settle(page, w);
  return {
    phone: project === 'phone',
    settle: s,
    evaluate: (fn, arg) => page.evaluate(fn, arg),
    nav: async v => {
      await page.evaluate(v => { if (typeof closeDrawer === 'function') closeDrawer(); document.getElementById('nav-' + v).click(); if (typeof closeDrawer === 'function') closeDrawer(); }, v);
      await s();
    },
    tab: async k => {
      await page.evaluate(k => {
        const strip = [...document.querySelectorAll('.view.active .tabs')].find(t => t.offsetParent && !t.querySelector('[aria-current]') && !t.closest('#guide-host'));
        const b = strip && [...strip.querySelectorAll('.tab')].find(t => t.dataset.k === k);
        if (!b) throw new Error('no tab ' + k);
        if (!b.classList.contains('on')) b.click();
      }, k);
      await s();
    },
    queue: async q => {
      await page.evaluate(q => { const b = document.querySelector('#view-labels nav.queues button[data-k="' + q + '"]'); if (!b) throw new Error('no queue ' + q); if (!b.classList.contains('on')) b.click(); }, q);
      await s();
    },
    click: async sel => {
      await page.evaluate(sel => { const e = [...document.querySelectorAll(sel)].find(x => x.offsetParent || x.getClientRects().length); if (!e) throw new Error('nothing visible matches ' + sel); e.click(); }, sel);
      await s();
    },
    clickText: async (scope, text) => {
      await page.evaluate(([scope, text]) => {
        const els = [...document.querySelectorAll((scope || 'body') + ' :is(button, a, [role="button"], [role="tab"], summary, .lbl-row, tr, li)')].filter(e => e.offsetParent || e.getClientRects().length);
        const e = els.find(x => (x.innerText || x.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').startsWith(text));
        if (!e) throw new Error('no "' + text + '" in ' + scope);
        e.click();
      }, [scope, text]);
      await s();
    },
    waitText: async (scope, text, ms) => {
      await page.waitForFunction(([scope, text]) => { const e = document.querySelector(scope); return e && e.innerText.includes(text); }, [scope, text], { timeout: ms || 20000, polling: 200 });
      await s();
    },
    waitFor: async (fn, arg, ms) => {
      await page.waitForFunction(fn, arg, { timeout: ms || 20000, polling: 200 });
      await s();
    },
  };
}

module.exports = { RUN, auth, isWrite, prepare, watch, settle, open, helpers };
