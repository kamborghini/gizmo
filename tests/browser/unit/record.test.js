const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'record-'));
test.after(() => fs.rmSync(tmp, { recursive: true, force: true }));
process.env.BROWSER_RUN = path.join(tmp, 'run');
process.env.BROWSER_RECORD = path.join(tmp, 'record');
fs.mkdirSync(process.env.BROWSER_RECORD, { recursive: true });
const R = require('../record');

test('counts adds up by rule and drops zeros', () => {
  assert.deepStrictEqual(R.counts([['color-contrast', 3], ['label', 0], ['color-contrast', 2], ['region', 1]]), { 'color-contrast': 5, region: 1 });
});
test('a count above the record is worse', () => {
  assert.deepStrictEqual(R.compare({ label: 1 }, { label: 2 }), { worse: ['label: 1 -> 2'], better: [] });
  assert.deepStrictEqual(R.compare({}, { region: 1 }), { worse: ['region: 0 -> 1'], better: [] });
});
test('a count below the record is better, and must be taken off the record', () => {
  assert.deepStrictEqual(R.compare({ label: 2, region: 1 }, { label: 1 }), { worse: [], better: ['label: 2 -> 1', 'region: 1 -> 0'] });
});
test('an equal count passes', () => {
  assert.deepStrictEqual(R.compare({ label: 2 }, { label: 2 }), { worse: [], better: [] });
});
test('check reads the committed record and leaves what it saw for the teardown', () => {
  fs.writeFileSync(path.join(process.env.BROWSER_RECORD, 'a11y.json'), JSON.stringify({ 'overview@laptop': { label: 1 } }));
  assert.deepStrictEqual(R.check('a11y', 'overview@laptop', { label: 1 }), { worse: [], better: [] });
  assert.deepStrictEqual(R.check('a11y', 'seo@laptop', { region: 2 }), { worse: ['region: 0 -> 2'], better: [] });
  assert.deepStrictEqual(R.merge('a11y'), { 'overview@laptop': { label: 1 }, 'seo@laptop': { region: 2 } });
});
test('the record is written sorted, so its diff in a pull request reads', () => {
  R.write('panels', { 'b@wide': { z: 1, a: 2 }, 'a@phone': {} });
  assert.strictEqual(fs.readFileSync(path.join(process.env.BROWSER_RECORD, 'panels.json'), 'utf8'),
    '{\n  "a@phone": {},\n  "b@wide": {\n    "a": 2,\n    "z": 1\n  }\n}\n');
});
test('a run starts with no observations left from an earlier one', () => {
  const dir = path.join(process.env.BROWSER_RUN, 'observed', 'a11y');
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'stale%40laptop.json'), '{}');
  R.fresh();
  assert.deepStrictEqual(R.merge('a11y'), {});
});
test('the record is rewritten only from a run that saw every screen at every size', () => {
  const screens = [{ id: 'a' }, { id: 'b' }], projects = ['phone', 'laptop'];
  const all = { 'a@phone': {}, 'a@laptop': {}, 'b@phone': {}, 'b@laptop': {} };
  assert.deepStrictEqual(R.complete(all, screens, projects), { ok: true, missing: [] });
  const part = { 'a@phone': {}, 'b@laptop': {} };
  assert.deepStrictEqual(R.complete(part, screens, projects), { ok: false, missing: ['a@laptop', 'b@phone'] });
});
