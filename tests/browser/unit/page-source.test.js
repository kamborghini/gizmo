// The browser suite's join is the server's join: one page, read two ways.
const test = require('node:test');
const assert = require('node:assert');
const crypto = require('crypto');
const path = require('path');
const { spawnSync } = require('child_process');
const { join } = require('../page-source');

test('the JavaScript join gives the page pagesource.py gives', () => {
  const root = path.join(__dirname, '..', '..', '..');
  const py = spawnSync(process.env.PY || 'python3', [path.join(root, 'pagesource.py'), '--sha256'], { encoding: 'utf8', cwd: root });
  assert.strictEqual(py.status, 0, py.stderr);
  const mine = crypto.createHash('sha256').update(join(root), 'utf8').digest('hex');
  assert.strictEqual(mine, py.stdout.trim());
});
