// node --test tests/browser/unit/
const test = require('node:test');
const assert = require('node:assert');
const { isWrite } = require('../support');

test('a POST whose op names a change is a write', () => {
  for (const op of ['add', 'save', 'delete', 'done', 'claim', 'send', 'book', 'mark_made', 'queue', 'won', 'state', 'request'])
    assert.ok(isWrite('/api/x', 'POST', JSON.stringify({ op })), op);
});
test('the reads the screens send are not writes', () => {
  const reads = [['/api/loans', { op: 'board' }], ['/api/crm/deal', { op: 'detail', id: 'd1' }], ['/api/loans', { op: 'history', unit_id: 'u1' }],
    ['/api/liability', { fresh: true }], ['/api/updates', { op: 'version' }], ['/api/profile', {}], ['/api/forecast', {}]];
  for (const [url, body] of reads) assert.ok(!isWrite(url, 'POST', JSON.stringify(body)), url + ' ' + JSON.stringify(body));
  assert.ok(!isWrite('/api/x', 'GET', null), 'a GET reads');
});
test('the two writes a screen makes by being looked at are swallowed, not counted', () => {
  assert.ok(!isWrite('/api/updates', 'POST', JSON.stringify({ op: 'seen', releases: 3 })));
  assert.ok(!isWrite('/api/layouts', 'POST', JSON.stringify({ view: 'overview', order: [] })));
  assert.ok(isWrite('/api/updates', 'POST', JSON.stringify({ op: 'request', text: 'x' })));
});
test('a read route is a write when it carries anything a read does not: an op or a field', () => {
  for (const op of ['settings', 'status', 'runs']) assert.ok(!isWrite('/api/connector', 'POST', JSON.stringify({ op })), op + ' reads');
  for (const op of ['settings_save', 'autorun_set', 'review']) assert.ok(isWrite('/api/connector', 'POST', JSON.stringify({ op })), op + ' writes');
  assert.ok(isWrite('/api/profile', 'POST', JSON.stringify({ name: 'Someone' })), 'a profile post with a field saves');
  assert.ok(isWrite('/api/files/upload', 'POST', 'not json'), 'a body that is not JSON is a write');
});
test('deny by default: anything not a listed read is a write, op or no op', () => {
  const W = [['/api/production-state', { op: 'made' }], ['/api/production-state', { op: 'printed' }], ['/api/production-state', { op: 'unprinted' }],
    ['/api/files/file', { op: 'destroy' }], ['/api/files/file', { op: 'empty_trash' }], ['/api/files/file', { op: 'trash' }],
    ['/api/crm/lead', { op: 'convert' }], ['/api/loans', { op: 'out' }], ['/api/loans', { op: 'back' }],
    ['/api/team/user', { op: 'role' }], ['/api/auth/mfa', { op: 'off' }], ['/api/mail/read', { id: 't1' }], ['/api/mail/claim', { id: 't1' }],
    ['/api/liability/chase', { order_id: 1 }], ['/api/recon/sweep', {}], ['/api/dispatch/book', { order_id: 1 }],
    ['/api/chat/stream', { messages: [] }], ['/api/work/clock', { op: 'in' }], ['/api/some-route-added-tomorrow', { op: 'list' }]];
  for (const [url, body] of W) assert.ok(isWrite(url, 'POST', JSON.stringify(body)), url + ' ' + JSON.stringify(body) + ' is a write');
});
