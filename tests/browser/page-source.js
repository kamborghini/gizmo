// The page, joined from static/src exactly as pagesource.py joins it: the
// shell with its two marker lines (each a whole line of its own) replaced by
// the stylesheet's and the script's sections, in manifest order.
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..', '..');
const CSS_MARK = '<!-- @css -->\n';
const JS_MARK = '<!-- @js -->\n';

function join(root = ROOT) {
  const src = path.join(root, 'static', 'src');
  const m = JSON.parse(fs.readFileSync(path.join(src, 'manifest.json'), 'utf8'));
  const read = rel => fs.readFileSync(path.join(src, rel), 'utf8');
  const lines = read(m.shell).match(/[^\n]*\n|[^\n]+$/g) || [];
  const c = lines.indexOf(CSS_MARK), j = lines.indexOf(JS_MARK);
  if (c < 0 || j < 0 || c > j || lines.lastIndexOf(CSS_MARK) !== c || lines.lastIndexOf(JS_MARK) !== j) {
    throw new Error('static/src/shell.html must hold the line <!-- @css --> and then the line <!-- @js -->, once each');
  }
  return lines.slice(0, c).join('') + m.css.map(read).join('') + lines.slice(c + 1, j).join('')
    + m.js.map(read).join('') + lines.slice(j + 1).join('');
}

module.exports = { join };
