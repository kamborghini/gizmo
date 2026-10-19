// Shared by every browser spec: signing in, the network fence, the writes a
// screen makes just by being looked at, reaching a state, and settling.
const fs = require('fs');
const path = require('path');

const RUN = process.env.BROWSER_RUN || path.join(__dirname, '.run');
const INTER = require.resolve('@fontsource-variable/inter/files/inter-latin-wght-normal.woff2');
const FONT_URL = 'https://fonts.gstatic.com/reactor-suite/inter.woff2';

// Deny by default: a POST is a write unless it is on this list of reads,
// by route, op and the body fields it carries. The list is what the 36
// states send (captured 14 Oct 2026); a route or op that is not on it fails
// the screen that sent it, so a new read is added here on purpose and a new
// write can never pass unseen. The fields matter: /api/profile with no
// fields reads, with fields it saves.
const R = (op, ...keys) => ({ op: op || null, keys });
const READS = {
  '/api/alerts': [R()], '/api/auth/state': [R()], '/api/cache': [R()], '/api/profile': [R()], '/api/memory': [R()],
  '/api/learn': [R()], '/api/impact': [R()], '/api/skills': [R()], '/api/forecast': [R()], '/api/files/tree': [R()],
  '/api/mail/board': [R()], '/api/crm/board': [R()], '/api/team/board': [R()], '/api/work/board': [R()],
  '/api/customer-tags': [R()], '/api/reorder-radar': [R()], '/api/recon/status': [R()], '/api/gobo-sizes/list': [R()],
  '/api/gobo-sizes/rules': [R()], '/api/production-labels/missing': [R()], '/api/layouts': [R()],
  '/api/updates': [R(), R('version')],
  '/api/connector': ['status', 'runs', 'quarantine', 'ledger', 'health', 'autorun', 'settings'].map(op => R(op)),
  '/api/crm/deal': [R('detail', 'id')],
  '/api/loans': [R('board'), R('history', 'unit_id')],
  '/api/custom/list': [R(null, 'limit')],
  '/api/customer-history': [R(null, 'customer_id')],
  '/api/liability': [R(null, 'fresh')],
  '/api/products': [R(null, 'months', 'fresh')],
  '/api/production-labels': [R(null, 'tag', 'fresh')],
  '/api/production-labels/coverage': [R(null, 'orders')],
  '/api/recon/exceptions': [R(null, 'q', 'severity', 'status')],
  '/api/recon/exception': [R(null, 'id')],
  // The windows the keyboard journeys open (windows.js), each read checked in copilot.py on 15 Oct 2026.
  '/api/margin': [R(null, 'days')],
  '/api/dispatch/manifest': [R(null, 'date')],
  '/api/stock-usage': [R(null, 'date')],
  '/api/order/edit': [R('read', 'order_id')],
  '/api/shipping/config': [R('get')],
  '/api/mail/addresses': [R()],
  // What the Settings window reads as it opens.
  '/api/status': [R()],
  '/api/schedule': [R()],
  '/api/usage': [R(null, 'days')],
  '/api/privacy': [R()],
  '/api/auth/mfa': [R('status')],
  '/api/mail/settings': [R('get')],
};

function isRead(route, b) {
  const allowed = READS[route];
  if (!allowed) return false;
  const op = typeof b.op === 'string' ? b.op : null;
  const keys = Object.keys(b).filter(k => k !== 'op');
  return allowed.some(r => r.op === op && keys.every(k => r.keys.includes(k)));
}

function auth() {
  return JSON.parse(fs.readFileSync(path.join(RUN, 'auth.json'), 'utf8'));
}

function isWrite(url, method, body) {
  if (method !== 'POST') return false;
  const route = new URL(url, 'http://app').pathname;
  let b = {};
  try { b = JSON.parse(body || '{}'); } catch (e) { return true; }   // a body that is not JSON (an upload) is a write
  if (!b || typeof b !== 'object' || Array.isArray(b)) return true;
  // The two writes a screen makes by being looked at: prepare() swallows them,
  // so they never reach the server.
  if (route === '/api/updates' && b.op === 'seen') return false;
  if (route === '/api/layouts' && ['view', 'order', 'hidden', 'reset'].some(k => k in b)) return false;
  return !isRead(route, b);
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

module.exports = { RUN, READS, auth, isWrite, prepare, watch, settle, open, helpers };
