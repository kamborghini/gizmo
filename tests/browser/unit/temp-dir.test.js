// Every other unit file is run again in a child pointed at an empty temp dir
// of its own, which must still be empty once the child has exited:
// record.test.js made a record-* folder there on every run and nothing removed
// it (74 of them by 20 October 2026).
const test = require('node:test');
const assert = require('node:assert');
const { spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const others = fs.readdirSync(__dirname).filter(f => f.endsWith('.test.js') && f !== path.basename(__filename));

for (const file of others) {
  test(`${file} leaves nothing in the temp dir`, () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'unit-temp-'));
    // A test runner started from inside a test file runs no files at all when
    // it inherits NODE_TEST_CONTEXT, and passes, so the child gets none.
    const env = { ...process.env, TMPDIR: tmp };
    delete env.NODE_TEST_CONTEXT;
    try {
      const r = spawnSync(process.execPath, ['--test', '--test-reporter=tap', path.join(__dirname, file)],
        { env, encoding: 'utf8', timeout: 120000 });
      assert.strictEqual(r.status, 0, `${file} failed: ${(r.stdout || '').slice(-600)}${(r.stderr || '').slice(-600)}`);
      assert.match(r.stdout, /^# pass [1-9]/m, `${file} ran no tests: ${(r.stdout || '').slice(-300)}`);
      assert.deepStrictEqual(fs.readdirSync(tmp), [], `${file} left these in the temp dir`);
    } finally {
      fs.rmSync(tmp, { recursive: true, force: true });
    }
  });
}
