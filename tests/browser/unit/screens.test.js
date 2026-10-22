const test = require('node:test');
const assert = require('node:assert');
const SCREENS = require('../screens');

test('29 states, each named once', () => {
  assert.strictEqual(SCREENS.length, 29);
  assert.strictEqual(new Set(SCREENS.map(s => s.id)).size, 29);
});
const fs = require('fs');
const path = require('path');
const APP = require('../page-source').join();
const WORLD = fs.readFileSync(path.join(__dirname, '..', 'test_world.py'), 'utf8');

// Run a screen's steps against stand-ins that record every wait for a text.
async function waitsOf(s) {
  const waits = [];
  const h = new Proxy({}, { get: (_, k) => k === 'waitText' ? async (scope, text) => { waits.push(text); } : async () => {} });
  const p = new Proxy({}, { get: () => async () => {} });
  await s.go(p, h);
  return waits;
}

test('every screen waits for a text only the seed puts there, or says why it has none', async () => {
  for (const s of SCREENS) {
    if (s.static) { assert.ok(typeof s.static === 'string' && s.static.length > 20, s.id + ' says why it is static'); continue; }
    assert.ok(typeof s.seeded === 'string' && s.seeded.length >= 6, s.id + ' names the text the seed puts there');
    assert.ok((await waitsOf(s)).includes(s.seeded), s.id + ' waits for ' + s.seeded);
    assert.ok(!APP.includes(s.seeded), s.id + ': "' + s.seeded + '" is in the page itself, so it shows without any data');
    const proof = s.proof || s.seeded;
    assert.ok(WORLD.includes(proof), s.id + ': test_world.py never proves "' + proof + '" is in the seeded world');
  }
});
test('a dialog names the control that opens it', () => {
  for (const s of SCREENS.filter(x => x.kind === 'dialog')) assert.ok(s.opener && s.opener.sel && s.before, s.id);
});

test('the keyboard journeys name how each window is reached, and no id twice', () => {
  const WINDOWS = require('../windows');
  const ids = new Set();
  assert.ok(WINDOWS.length >= 10, 'at least ten windows beyond the three measured ones');
  for (const w of WINDOWS) {
    assert.ok(!ids.has(w.id), w.id + ' twice'); ids.add(w.id);
    assert.ok(typeof w.before === 'function', w.id + ' says how to get to its screen');
    assert.ok(!!w.opener !== !!w.menu, w.id + ' is opened by a button or by a menu item, one of the two');
  }
});
