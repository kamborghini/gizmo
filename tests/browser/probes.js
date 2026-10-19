// What is measured in the page after a screen settles. Two checks must be
// zero on every screen (sideways scroll, content spilling out of its panel);
// the panel rules are counted per rule and held by the ratchet (record.js).
const APP = require('./page-source').join();
// The panel rule is the stylesheet's (css/panels.css, "the panel rule"): its
// selector finds the panels, and its two lists drive this probe's own walk,
// which has no depth limit, so a block the rule misses, or one it paints that
// the walk does not expect, is counted.
const PANEL = /\/\* the panel rule \*\/\s*([^{]+)\{/.exec(APP)[1].replace(/\s+/g, ' ').trim();
function args(text, at) {          // the text inside the parentheses that open at text[at]
  let d = 0;
  for (let i = at; i < text.length; i++) {
    if (text[i] === '(') d++;
    else if (text[i] === ')' && --d === 0) return text.slice(at + 1, i);
  }
  throw new Error('unbalanced panel rule');
}
const classes = list => list.split(',').map(x => x.trim()).filter(x => /^\.[\w-]+$/.test(x)).map(x => x.slice(1));
const HOLD = classes(args(PANEL, PANEL.indexOf(':is(') + 3));
const SKIP = classes(args(PANEL, PANEL.lastIndexOf('> :not(') + 6)).filter(c => !HOLD.includes(c));

async function measure(page) {
  return page.evaluate(([SKIP, HOLD, PANEL]) => {
    const vis = n => n.getClientRects().length && getComputedStyle(n).display !== 'none' && getComputedStyle(n).visibility !== 'hidden';
    const desc = n => (n.tagName.toLowerCase() + (n.id ? '#' + n.id : '') + ([...n.classList].length ? '.' + [...n.classList].join('.') : '')).slice(0, 80);
    const clips = s => /(auto|scroll|hidden|clip)/.test(s.overflowX);

    // Sideways: a page-level container whose content is wider than it. The
    // document; .main, which clips for the rounded frame (wider content is
    // cut off); and the active view and its .scroll, the column that scrolls.
    // Scrolled or cut off, the page is wider than the screen either way.
    // Deliberate sideways scrollers (a wide table, the CRM board) sit inside
    // panels and are not page-level.
    // An open window is measured as well: its body is its own scrolling column.
    const win = [...document.querySelectorAll('.modal-overlay.show .modal')].filter(vis);
    const sideways = [document.scrollingElement, document.querySelector('.main'),
      ...document.querySelectorAll('.view.active, .view.active > .scroll'),
      ...win, ...win.map(w => w.querySelector('.modal-body')).filter(Boolean)]
      .filter((e, i, a) => e && a.indexOf(e) === i)
      .filter(e => e.scrollWidth > e.clientWidth + 1)
      .map(e => desc(e) + ' ' + (e.scrollWidth - e.clientWidth) + 'px');

    const roots = [...document.querySelectorAll('.view.active .ov-wrap')];
    const panels = [...document.querySelectorAll(PANEL)].filter(n => vis(n) && n.closest('.view.active'))
      .filter(n => !n.parentElement.closest(PANEL));
    const R = panels.map(n => ({ n, r: n.getBoundingClientRect() }));

    // Spill: a visible element wider than its panel, not held by a scroller or a clip.
    const spill = [], spilt = [];
    for (const { n: pn, r: pr } of [...R, ...win.map(n => ({ n, r: n.getBoundingClientRect() }))]) {
      if (clips(getComputedStyle(pn))) continue;
      for (const e of pn.querySelectorAll('*')) {
        if (!vis(e)) continue;
        const r = e.getBoundingClientRect();
        if (!r.width || !r.height || (r.right <= pr.right + 1 && r.left >= pr.left - 1)) continue;
        let a = e.parentElement, held = false;
        while (a && a !== pn) { if (clips(getComputedStyle(a))) { held = true; break; } a = a.parentElement; }
        // One line per overflowing block, not one per element inside it.
        if (!held && !spilt.some(x => x.contains(e))) { spilt.push(e); spill.push(desc(e) + ' ' + Math.round(Math.max(r.right - pr.right, pr.left - r.left)) + 'px past ' + desc(pn)); }
      }
    }

    // The panel rules (13 Oct).
    const bad = [], expected = new Set(), furniture = [];
    const walk = n => {
      if (!vis(n) || n.tagName === 'INPUT' || n.tagName === 'SCRIPT') return;
      if (SKIP.some(c => n.classList.contains(c))) { furniture.push(n.getBoundingClientRect()); return; }
      if (!n.className || HOLD.some(c => n.classList.contains(c))) { [...n.children].forEach(walk); return; }
      expected.add(n);
      const cs = getComputedStyle(n);
      const painted = cs.backgroundColor !== 'rgba(0, 0, 0, 0)' && (cs.borderTopWidth !== '0px' || cs.boxShadow !== 'none' || cs.outlineStyle !== 'none');
      if (!n.matches(PANEL) || !painted) bad.push(desc(n));
    };
    roots.forEach(r => [...r.children].forEach(walk));
    const extra = roots.flatMap(r => [...r.querySelectorAll(PANEL)]).filter(n => vis(n) && !expected.has(n) && !n.parentElement.closest(PANEL)).map(desc);
    const loose = [...document.querySelectorAll('.view.active .ov-wrap :is(.section-title, .card-title, h2, h3)')].filter(vis)
      .filter(h => !h.closest(PANEL) && !h.closest('.ov-hero, .fband, .miss-strip, .modal')).map(desc);
    const nested = [...document.querySelectorAll(PANEL)].filter(n => vis(n) && n.closest('.view.active') && n.parentElement.closest(PANEL)).map(desc);
    const gap = innerWidth <= 640 ? 12 : 20;
    const gaps = [], heights = [];
    for (const a of R) {
      const below = R.filter(b => b !== a && b.r.top >= a.r.bottom - 1 && Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left) > 8).sort((x, y) => x.r.top - y.r.top)[0];
      // A notice (or other page furniture) between two panels spaces them itself.
      const between = below && furniture.some(f => f.top >= a.r.bottom - 1 && f.bottom <= below.r.top + 1 && Math.min(f.right, a.r.right) - Math.max(f.left, a.r.left) > 8);
      if (below && !between && Math.abs(below.r.top - a.r.bottom - gap) > 1) gaps.push('v ' + Math.round(below.r.top - a.r.bottom) + ': ' + desc(a.n));
      const right = R.filter(b => b !== a && b.r.left >= a.r.right - 1 && Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top) > 8).sort((x, y) => x.r.left - y.r.left)[0];
      if (right && Math.abs(right.r.left - a.r.right - gap) > 1) gaps.push('h ' + Math.round(right.r.left - a.r.right) + ': ' + desc(a.n));
      if (right && Math.abs(right.r.top - a.r.top) <= 1 && Math.abs(right.r.bottom - a.r.bottom) > 1 && getComputedStyle(a.n.parentElement).columnCount === 'auto') heights.push(desc(a.n) + ' | ' + desc(right.n));
    }
    const greyish = c => { const m = c.match(/\d+/g); if (!m || (c.startsWith('rgba') && +m[3] === 0)) return false; const [r, g, b] = m.map(Number); return r >= 236 && r <= 246 && Math.abs(r - g) <= 3 && Math.abs(g - b) <= 3; };
    const vanish = [...document.querySelectorAll('.view.active :is(.segmented, input, select, textarea, .btn, .tabs)')].filter(vis)
      .filter(n => !n.closest(PANEL + ', .modal, .fband, .miss-strip')).filter(n => greyish(getComputedStyle(n).backgroundColor) && getComputedStyle(n).boxShadow === 'none' && getComputedStyle(n).borderTopWidth === '0px').map(desc);
    const lone = panels.filter(n => n.matches('.section-title, .card-title, h2, h3') || ([...n.children].filter(vis).length === 1 && [...n.children].filter(vis)[0].matches('.section-title, .card-title, h2, h3'))).map(desc);
    const inset = [], short = [];
    for (const { n: pn, r: pr } of R) {
      if (pn.classList.contains('metrics')) continue;
      const cs = getComputedStyle(pn);
      const padL = parseFloat(cs.paddingLeft) + parseFloat(cs.borderLeftWidth), padR = parseFloat(cs.paddingRight) + parseFloat(cs.borderRightWidth);
      const cw = pr.width - padL - padR;
      for (const e of pn.querySelectorAll('*')) {
        if (!vis(e)) continue;
        const es = getComputedStyle(e);
        const edge = side => parseFloat(es['border' + side + 'Width']) >= 1 && es['border' + side + 'Style'] !== 'none' && !es['border' + side + 'Color'].endsWith(', 0)');
        // A ruled line is a hairline above or below: a box (a field, a menu, a button, a chip, a bar) has sides too, and is not one.
        const ruled = (edge('Bottom') || edge('Top')) && !edge('Left') && !edge('Right');
        if (!ruled) continue;
        const r = e.getBoundingClientRect();
        if (r.width >= cw * 0.9 && Math.abs(r.left - (pr.left + padL)) <= 2 && Math.abs(r.right - (pr.right - padR)) <= 2) inset.push(desc(e));
        const c = e.parentElement, cr = c.getBoundingClientRect();
        if (cr.width >= cw * 0.9 && r.width < cr.width * 0.85 && r.width >= 40 && Math.abs(r.left - cr.left) <= 2
          && ![...c.children].some(s => s !== e && vis(s) && Math.abs(s.getBoundingClientRect().top - r.top) < 3 && s.getBoundingClientRect().left >= r.right - 1)) short.push(desc(e));
      }
    }
    return { sideways, spill, panels: { bad, extra, loose, nested, gaps, heights, vanish, lone, inset: [...new Set(inset)], short: [...new Set(short)] } };
  }, [SKIP, HOLD, PANEL]);
}

function panelCounts(m) {
  const out = {};
  for (const [rule, items] of Object.entries(m.panels)) if (items.length) out[rule] = items.length;
  return out;
}

// Every visible control with no name a screen reader can read: no label, no
// aria-label, no aria-labelledby, no title, and for a button no words either.
// A placeholder is not a name: it goes as soon as someone types.
async function unnamed(page) {
  return page.evaluate(() => [...document.querySelectorAll('input, select, textarea, [role="switch"]')]
    .filter(e => e.getClientRects().length && e.type !== 'hidden' && e.type !== 'file')
    .filter(e => !(e.labels && e.labels.length) && !(e.getAttribute('aria-label') || '').trim()
      && !e.getAttribute('aria-labelledby') && !(e.title || '').trim()
      && !(e.tagName === 'BUTTON' && (e.innerText || '').trim()))
    .map(e => e.tagName.toLowerCase() + (e.type ? '[' + e.type + ']' : '')
      + (e.className ? '.' + String(e.className).trim().split(/\s+/).join('.') : '')
      + (e.placeholder ? ' "' + e.placeholder + '"' : '')));
}

// A row's hidden opener placed by anything but its own cell or row. It is
// taken out of the flow, so with no positioned box around it, it is laid out
// against the page and stretches it past a scrolling list (19 Oct 2026: CRM
// Contacts on a phone grew 500 of blank page).
async function strayOpeners(page) {
  return page.evaluate(() => [...document.querySelectorAll('.row-open')]
    .filter(b => b.offsetParent !== b.parentElement)
    .map(b => (b.getAttribute('aria-label') || '') + ' placed by '
      + (b.offsetParent ? b.offsetParent.tagName.toLowerCase() + (b.offsetParent.id ? '#' + b.offsetParent.id : '') : 'nothing')));
}

// A real table's body cell its head names that does not carry the name (or,
// under the leading head, the mark): a phone's two-line row would show the
// value with no word for what it is. Every table in the page, shown or not.
async function unnamedCells(page) {
  return page.evaluate(() => {
    const out = [];
    document.querySelectorAll('table.ktable').forEach(t => {
      const hr = t.tHead && t.tHead.rows[t.tHead.rows.length - 1];
      if (!hr) return;
      const heads = [];
      [...hr.cells].forEach(th => { for (let k = 0; k < (th.colSpan || 1); k++) heads.push(th.colSpan > 1 ? null : th); });
      [...t.tBodies, ...(t.tFoot ? [t.tFoot] : [])].forEach(b => [...b.rows].forEach(tr => {
        let i = 0;
        [...tr.cells].forEach(td => {
          const th = heads[i];
          if (th && (td.colSpan || 1) === 1) {
            const name = th.textContent.replace(/\s+/g, ' ').trim();
            if (name && !td.hasAttribute('data-h')) out.push(t.className + ': "' + name + '" cell unnamed');
            if (th.classList.contains('kt-main') && !td.classList.contains('kt-main')) out.push(t.className + ': "' + name + '" cell not marked as leading');
          }
          i += td.colSpan || 1;
        });
      }));
    });
    return [...new Set(out)];
  });
}

module.exports = { measure, panelCounts, unnamed, strayOpeners, unnamedCells, PANEL, SKIP, HOLD };
