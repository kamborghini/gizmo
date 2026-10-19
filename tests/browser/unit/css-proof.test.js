// The proof tells a real change from noise (computed.js's compare).
const test = require('node:test');
const assert = require('node:assert');
const { compare, properties } = require('../computed');

const shot = (nodes) => {
  const styles = [], index = new Map(), out = {};
  for (const [k, v] of Object.entries(nodes)) { if (!index.has(v)) { index.set(v, styles.length); styles.push(v); } out[k] = index.get(v); }
  return { styles, nodes: out };
};

test('a style the head changed in both runs is a change, with the properties that differ', () => {
  const base = shot({ a: 'color:red;display:block', b: 'color:blue' });
  const head = shot({ a: 'color:green;display:block', b: 'color:blue' });
  const d = compare(base, head, head);
  assert.deepStrictEqual(d, [{ key: 'a', props: [{ prop: 'el color', base: 'red', head: 'green' }] }]);
});

test('a style that differs between the two head runs is noise, not a change', () => {
  const base = shot({ clock: 'width:40px' });
  assert.deepStrictEqual(compare(base, shot({ clock: 'width:41px' }), shot({ clock: 'width:42px' })), []);
});

test('an element on one side only is named, unless the head runs disagree on it', () => {
  assert.deepStrictEqual(compare(shot({ a: 'x:1' }), shot({}), shot({})), [{ key: 'a', only: 'base' }]);
  assert.deepStrictEqual(compare(shot({}), shot({ a: 'x:1' }), shot({})), []);
});

test('pseudo-elements are their own properties', () => {
  assert.deepStrictEqual(properties('color:red|::beforecontent:"x";color:blue'), { 'el color': 'red', '::before content': '"x"', '::before color': 'blue' });
});
