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

test('a colour that draws nothing is not a change: a border with no width, an outline with no style', () => {
  const base = shot({ a: 'border-top-color:red;border-top-style:none;border-top-width:0px;outline-color:red;outline-style:none' });
  const head = shot({ a: 'border-top-color:blue;border-top-style:none;border-top-width:0px;outline-color:blue;outline-style:none' });
  assert.deepStrictEqual(compare(base, head, head), []);
  const seen = shot({ a: 'border-top-color:blue;border-top-style:solid;border-top-width:1px' });
  assert.strictEqual(compare(shot({ a: 'border-top-color:red;border-top-style:solid;border-top-width:1px' }), seen, seen).length, 1);
});

test('a custom property is not a change by itself: what it feeds is', () => {
  const base = shot({ a: 'background-color:red' });
  assert.deepStrictEqual(compare(base, shot({ a: '--chip:red;background-color:red' }), shot({ a: '--chip:red;background-color:red' })), []);
  assert.strictEqual(compare(base, shot({ a: '--chip:blue;background-color:blue' }), shot({ a: '--chip:blue;background-color:blue' })).length, 1);
});
