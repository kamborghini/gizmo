// The ratchet. A record is {"<screen>@<size>": {"<rule>": count}}. A count
// above the record is a new problem; a count below it is a fixed one the
// record still allows, which would let a later regression hide in the slack.
// Both fail. UPDATE_RECORD=1 rewrites the record from the run (teardown.js),
// and the diff of record/*.json in the pull request shows what changed.
const fs = require('fs');
const path = require('path');

const RUN = process.env.BROWSER_RUN || path.join(__dirname, '.run');
const RECORD = process.env.BROWSER_RECORD || path.join(__dirname, 'record');
const UPDATE = process.env.UPDATE_RECORD === '1';

function counts(pairs) {
  const out = {};
  for (const [rule, n] of pairs) if (n) out[rule] = (out[rule] || 0) + n;
  return out;
}

function compare(recorded, observed) {
  const a = recorded || {}, b = observed || {};
  const worse = [], better = [];
  for (const r of [...new Set([...Object.keys(a), ...Object.keys(b)])].sort()) {
    const x = a[r] || 0, y = b[r] || 0;
    if (y > x) worse.push(`${r}: ${x} -> ${y}`);
    else if (y < x) better.push(`${r}: ${x} -> ${y}`);
  }
  return { worse, better };
}

function load(kind) {
  try { return JSON.parse(fs.readFileSync(path.join(RECORD, kind + '.json'), 'utf8')); }
  catch (e) { if (e.code === 'ENOENT') return {}; throw e; }
}

function check(kind, key, observed) {
  const dir = path.join(RUN, 'observed', kind);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, encodeURIComponent(key) + '.json'), JSON.stringify(observed));
  return compare(load(kind)[key], observed);
}

function merge(kind) {
  const dir = path.join(RUN, 'observed', kind);
  const out = {};
  if (!fs.existsSync(dir)) return out;
  for (const f of fs.readdirSync(dir).sort()) out[decodeURIComponent(f.replace(/\.json$/, ''))] = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
  return out;
}

function sorted(v) {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return v;
  return Object.fromEntries(Object.keys(v).sort().map(k => [k, sorted(v[k])]));
}

function write(kind, obj) {
  fs.mkdirSync(RECORD, { recursive: true });
  fs.writeFileSync(path.join(RECORD, kind + '.json'), JSON.stringify(sorted(obj), null, 2) + '\n');
}

// Every run starts empty: observations left by an earlier run would be merged
// into this one's and could rewrite the record from stale counts.
function fresh() {
  fs.rmSync(path.join(RUN, 'observed'), { recursive: true, force: true });
}

// Whether a run saw every screen at every size; only such a run may rewrite.
function complete(seen, screens, projects) {
  const missing = [];
  for (const s of screens) for (const p of projects) if (!(`${s.id}@${p}` in seen)) missing.push(`${s.id}@${p}`);
  return { ok: missing.length === 0, missing };
}

module.exports = { RUN, RECORD, UPDATE, counts, compare, check, merge, write, load, fresh, complete };
