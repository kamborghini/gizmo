// The proof that a stylesheet change changed nothing (make css-proof): a
// fingerprint of the final style of every element a measured state shows,
// with its ::before and ::after, and again with hover, and with keyboard
// focus, forced on its controls. Elements are keyed by where they sit (tag
// and position from <body>), so a class renamed does not move a key.

// The controls forced: the first two of each kind (tag, classes, holder's
// classes) in the state, so a list of fifty alike rows costs two.
const CONTROLS = 'button, a[href], [role="button"], [role="tab"], input, select, textarea, summary, [tabindex="0"]';
const PER_KIND = Number(process.env.CSS_PROOF_PER_KIND || 2);   // more, to cover a state whose kinds a change merged
const SUBTREE = 40;
const HOLDERS = 3;

async function fingerprint(page) {
  const styles = [], index = new Map(), nodes = {};
  const keep = (key, value) => {
    if (!index.has(value)) { index.set(value, styles.length); styles.push(value); }
    nodes[key] = index.get(value);
  };
  // Transitions and animations finish at once while the proof reads, the same
  // on both sides: a style read just after hover or focus is forced would
  // otherwise catch a colour part of the way through its change.
  await page.addStyleTag({ content: '*, *::before, *::after { transition: none !important; animation-duration: 0s !important; animation-delay: 0s !important; }' });
  // In the page: the roots, the paths, and every element's sorted style.
  await page.evaluate(([CONTROLS, PER_KIND]) => {
    const roots = [document.querySelector('.view.active'), ...document.querySelectorAll('.modal-overlay.show'),
      document.getElementById('sidebar'), document.querySelector('.topbar')].filter(Boolean);
    const pathOf = n => {
      const p = [];
      for (; n && n !== document.body; n = n.parentElement) {
        let i = 0; for (let k = n; (k = k.previousElementSibling);) i++;
        p.push(n.tagName + i);
      }
      return p.reverse().join('/');
    };
    const dump = cs => { const a = []; for (let i = 0; i < cs.length; i++) a.push(cs[i] + ':' + cs.getPropertyValue(cs[i])); return a.sort().join(';'); };
    const styleOf = n => {
      let s = dump(getComputedStyle(n));
      for (const ps of ['::before', '::after']) {
        const c = getComputedStyle(n, ps);
        if (c.content !== 'none' && c.content !== 'normal') s += '|' + ps + dump(c);
      }
      return s;
    };
    const all = [], seen = new Set();
    for (const r of roots) for (const n of [r, ...r.querySelectorAll('*')]) if (!seen.has(n)) { seen.add(n); all.push(n); }
    const kinds = new Map(); let i = 0;
    for (const n of all) {
      if (!n.matches(CONTROLS)) continue;
      const kind = n.tagName + '.' + [...n.classList].sort().join('.') + '<' + (n.parentElement ? [...n.parentElement.classList].sort().join('.') : '');
      const k = kinds.get(kind) || 0;
      if (k >= PER_KIND) continue;
      kinds.set(kind, k + 1);
      n.setAttribute('data-css-proof', String(i++));
    }
    window.__cssProof = { all, pathOf, styleOf };
  }, [CONTROLS, PER_KIND]);
  const plain = await page.evaluate(() => { const P = window.__cssProof; return P.all.map(n => [P.pathOf(n), P.styleOf(n)]); });
  for (const [k, v] of plain) keep(k, v);

  const cdp = await page.context().newCDPSession(page);
  await cdp.send('DOM.enable');
  await cdp.send('CSS.enable');
  const { root } = await cdp.send('DOM.getDocument', { depth: 0 });
  const { nodeIds } = await cdp.send('DOM.querySelectorAll', { nodeId: root.nodeId, selector: '[data-css-proof]' });
  for (const nodeId of nodeIds) {
    for (const [tag, forced] of [['hover', ['hover']], ['focus', ['focus', 'focus-visible']]]) {
      await cdp.send('CSS.forcePseudoState', { nodeId, forcedPseudoClasses: forced });
      const { attributes } = await cdp.send('DOM.getAttributes', { nodeId });
      const id = attributes[attributes.indexOf('data-css-proof') + 1];
      const got = await page.evaluate(([id, SUBTREE, HOLDERS]) => {
        const P = window.__cssProof;
        const c = document.querySelector('[data-css-proof="' + id + '"]');
        const near = [c, ...[...c.querySelectorAll('*')].slice(0, SUBTREE)];
        for (let a = c.parentElement, k = 0; a && k < HOLDERS; a = a.parentElement, k++) near.push(a);
        return [P.pathOf(c), near.map(n => [P.pathOf(n), P.styleOf(n)])];
      }, [id, SUBTREE, HOLDERS]);
      for (const [k, v] of got[1]) keep(got[0] + '#' + tag + '>' + k, v);
      await cdp.send('CSS.forcePseudoState', { nodeId, forcedPseudoClasses: [] });
    }
  }
  await cdp.detach();
  await page.evaluate(() => { document.querySelectorAll('[data-css-proof]').forEach(n => n.removeAttribute('data-css-proof')); delete window.__cssProof; });
  return { styles, nodes };
}

// A style string back to its properties: "el prop" or "::before prop".
function properties(s) {
  const out = {};
  for (let part of s.split('|')) {
    let tag = 'el';
    for (const ps of ['::before', '::after']) if (part.startsWith(ps)) { tag = ps; part = part.slice(ps.length); }
    for (const x of part.split(';')) { const i = x.indexOf(':'); if (i > 0) out[tag + ' ' + x.slice(0, i)] = x.slice(i + 1); }
  }
  return out;
}

// What changed between the base and the head, beyond the head's own noise:
// a key whose style differs from the base's in the first head run and is the
// same in both head runs, or a key on one side only that both head runs agree
// on. Each with the properties that differ.
function compare(base, head1, head2) {
  const val = (f, k) => (k in f.nodes ? f.styles[f.nodes[k]] : undefined);
  const out = [];
  for (const k of new Set([...Object.keys(base.nodes), ...Object.keys(head1.nodes)])) {
    const b = val(base, k), h = val(head1, k), h2 = val(head2, k);
    if (b === h || h !== h2) continue;
    if (b === undefined || h === undefined) { out.push({ key: k, only: b === undefined ? 'head' : 'base' }); continue; }
    const pb = properties(b), ph = properties(h);
    const props = [...new Set([...Object.keys(pb), ...Object.keys(ph)])].filter(p => pb[p] !== ph[p] && !unseen(p, pb, ph)).sort()
      .map(p => ({ prop: p, base: pb[p], head: ph[p] }));
    if (props.length) out.push({ key: k, props });
  }
  return out;
}

// A value that draws nothing on either side: a custom property; a border's colour where that
// border has no width or no style, an outline's colour, width or offset where
// there is no outline.
function unseen(p, a, b) {
  const [tag, prop] = p.split(' ');
  // A custom property draws nothing itself: what it feeds is compared as the property it feeds.
  if (prop.startsWith('--')) return true;
  const none = (side, f) => [a, b].every(x => x[tag + ' ' + f(side + '-style')] === 'none' || x[tag + ' ' + f(side + '-width')] === '0px');
  const m = /^border-(top|right|bottom|left)-color$/.exec(prop);
  if (m) return none('border-' + m[1], x => x);
  if (/^outline-(color|width|offset)$/.test(prop)) return [a, b].every(x => x[tag + ' outline-style'] === 'none');
  return false;
}

module.exports = { fingerprint, compare, properties, unseen, CONTROLS };

// node tests/browser/computed.js <base dir> <head1 dir> <head2 dir>: the report,
// exit 1 when any state changed.
if (require.main === module) {
  const fs = require('fs'), path = require('path'), zlib = require('zlib');
  const [baseDir, h1Dir, h2Dir] = process.argv.slice(2);
  const load = (d, f) => JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(d, f))).toString('utf8'));
  let changed = 0, states = 0;
  const files = fs.readdirSync(baseDir).filter(f => f.endsWith('.json.gz')).sort();
  for (const f of files) {
    if (!fs.existsSync(path.join(h1Dir, f)) || !fs.existsSync(path.join(h2Dir, f))) { console.log(f + ': not shot on the head'); changed++; continue; }
    const diff = compare(load(baseDir, f), load(h1Dir, f), load(h2Dir, f));
    states++;
    if (!diff.length) continue;
    changed++;
    console.log(f.replace(/\.json\.gz$/, '') + ': ' + diff.length + ' changed');
    for (const d of diff.slice(0, 12)) {
      if (d.only) { console.log('  ' + d.key + ' (only on the ' + d.only + ')'); continue; }
      console.log('  ' + d.key + '\n' + d.props.slice(0, 6).map(p => '    ' + p.prop + ': ' + p.base + ' -> ' + p.head).join('\n'));
    }
  }
  console.log(changed ? changed + ' of ' + states + ' states changed' : 'no state changed (' + states + ' compared)');
  process.exit(changed ? 1 : 0);
}
