// node --test tests/browser/unit/
const test = require('node:test');
const assert = require('node:assert');
const { isWrite } = require('../support');

test('a POST whose op names a change is a write', () => {
  for (const op of ['add', 'save', 'delete', 'done', 'claim', 'send', 'book', 'mark_made', 'queue', 'won', 'state', 'request'])
    assert.ok(isWrite('/api/x', 'POST', JSON.stringify({ op })), op);
});
test('reads are not writes', () => {
  for (const body of [{}, { op: 'board' }, { op: 'detail', id: 'd1' }, { op: 'history' }, { months: 24, fresh: true }, { op: 'version' }])
    assert.ok(!isWrite('/api/x', 'POST', JSON.stringify(body)), JSON.stringify(body));
  assert.ok(!isWrite('/api/x', 'GET', null));
});
test('the two writes a screen makes by being looked at are swallowed, not counted', () => {
  assert.ok(!isWrite('/api/updates', 'POST', JSON.stringify({ op: 'seen', releases: 3 })));
  assert.ok(!isWrite('/api/layouts', 'POST', JSON.stringify({ view: 'overview', order: [] })));
  assert.ok(isWrite('/api/updates', 'POST', JSON.stringify({ op: 'request', text: 'x' })));
});
test('an op is read word by word, so settings is a read and settings_save a write', () => {
  for (const op of ['settings', 'status', 'requests', 'runs', 'markers'])
    assert.ok(!isWrite('/api/connector', 'POST', JSON.stringify({ op })), op + ' is a read');
  for (const op of ['settings_save', 'autorun_set', 'set_status', 'markMade'])
    assert.ok(isWrite('/api/connector', 'POST', JSON.stringify({ op })), op + ' is a write');
});
