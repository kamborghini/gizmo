const test = require('node:test');
const assert = require('node:assert');
const SCREENS = require('../screens');

test('36 states, each named once', () => {
  assert.strictEqual(SCREENS.length, 36);
  assert.strictEqual(new Set(SCREENS.map(s => s.id)).size, 36);
});
test('every screen waits for seeded content before it is measured', () => {
  for (const s of SCREENS) {
    const src = (s.before ? s.before.toString() : '') + s.go.toString();
    assert.ok(/waitText|waitFor|waitForSelector/.test(src), s.id + ' never waits for its content, so its empty state could be measured');
  }
});
test('a dialog names the control that opens it', () => {
  for (const s of SCREENS.filter(x => x.kind === 'dialog')) assert.ok(s.opener && s.opener.sel && s.before, s.id);
});
