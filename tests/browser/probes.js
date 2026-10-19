// What is measured in the page after a screen settles. Two checks must be
// zero on every screen (sideways scroll, content spilling out of its panel);
// the panel rules are counted per rule and held by the ratchet (record.js).
const APP = require('./page-source').join();
const list = name => JSON.parse(new RegExp(`const ${name} = (\\[[^\\]]*\\])`).exec(APP)[1].replace(/'/g, '"'));
const SKIP = list('PANEL_SKIP');
const HOLD = list('PANEL_HOLD');

async function measure(page) {
  return page.evaluate(([SKIP, HOLD]) => {
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
    const panels = [...document.querySelectorAll('.view.active .ov-wrap .panel, .view.active .panel')].filter(vis)
      .filter((n, i, a) => a.indexOf(n) === i && !n.parentElement.closest('.panel'));
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
    const bad = [];
    const walk = n => {
      if (!vis(n) || SKIP.some(c => n.classList.contains(c))) return;
      if (!n.className || HOLD.some(c => n.classList.contains(c))) { [...n.children].forEach(walk); return; }
      const cs = getComputedStyle(n);
      const painted = cs.backgroundColor !== 'rgba(0, 0, 0, 0)' && (cs.borderTopWidth !== '0px' || cs.boxShadow !== 'none' || cs.outlineStyle !== 'none');
      if (!n.classList.contains('panel') || !painted) bad.push(desc(n));
    };
    roots.forEach(r => [...r.children].forEach(walk));
    const loose = [...document.querySelectorAll('.view.active .ov-wrap :is(.section-title, .card-title, h2, h3)')].filter(vis)
      .filter(h => !h.closest('.panel') && !h.closest('.ov-hero, .fband, .miss-strip, .modal')).map(desc);
    const nested = [...document.querySelectorAll('.view.active .panel .panel')].filter(vis).map(desc);
    const gap = innerWidth <= 640 ? 12 : 20;
    const gaps = [], heights = [];
    for (const a of R) {
      const below = R.filter(b => b !== a && b.r.top >= a.r.bottom - 1 && Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left) > 8).sort((x, y) => x.r.top - y.r.top)[0];
      if (below && Math.abs(below.r.top - a.r.bottom - gap) > 1) gaps.push('v ' + Math.round(below.r.top - a.r.bottom) + ': ' + desc(a.n));
      const right = R.filter(b => b !== a && b.r.left >= a.r.right - 1 && Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top) > 8).sort((x, y) => x.r.left - y.r.left)[0];
      if (right && Math.abs(right.r.left - a.r.right - gap) > 1) gaps.push('h ' + Math.round(right.r.left - a.r.right) + ': ' + desc(a.n));
      if (right && Math.abs(right.r.top - a.r.top) <= 1 && Math.abs(right.r.bottom - a.r.bottom) > 1 && getComputedStyle(a.n.parentElement).columnCount === 'auto') heights.push(desc(a.n) + ' | ' + desc(right.n));
    }
    const greyish = c => { const m = c.match(/\d+/g); if (!m || (c.startsWith('rgba') && +m[3] === 0)) return false; const [r, g, b] = m.map(Number); return r >= 236 && r <= 246 && Math.abs(r - g) <= 3 && Math.abs(g - b) <= 3; };
    const vanish = [...document.querySelectorAll('.view.active :is(.segmented, input, select, textarea, .btn, .tabs)')].filter(vis)
      .filter(n => !n.closest('.panel, .modal, .fband, .miss-strip')).filter(n => greyish(getComputedStyle(n).backgroundColor) && getComputedStyle(n).boxShadow === 'none' && getComputedStyle(n).borderTopWidth === '0px').map(desc);
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
        const ruled = (parseFloat(es.borderBottomWidth) >= 1 && es.borderBottomStyle !== 'none' && !es.borderBottomColor.endsWith(', 0)'))
          || (parseFloat(es.borderTopWidth) >= 1 && es.borderTopStyle !== 'none' && !es.borderTopColor.endsWith(', 0)'));
        if (!ruled) continue;
        const r = e.getBoundingClientRect();
        if (r.width >= cw * 0.9 && Math.abs(r.left - (pr.left + padL)) <= 2 && Math.abs(r.right - (pr.right - padR)) <= 2) inset.push(desc(e));
        const c = e.parentElement, cr = c.getBoundingClientRect();
        if (cr.width >= cw * 0.9 && r.width < cr.width * 0.85 && r.width >= 40 && Math.abs(r.left - cr.left) <= 2
          && ![...c.children].some(s => s !== e && vis(s) && Math.abs(s.getBoundingClientRect().top - r.top) < 3 && s.getBoundingClientRect().left >= r.right - 1)) short.push(desc(e));
      }
    }
    return { sideways, spill, panels: { bad, loose, nested, gaps, heights, vanish, lone, inset: [...new Set(inset)], short: [...new Set(short)] } };
  }, [SKIP, HOLD]);
}

function panelCounts(m) {
  const out = {};
  for (const [rule, items] of Object.entries(m.panels)) if (items.length) out[rule] = items.length;
  return out;
}

module.exports = { measure, panelCounts, SKIP, HOLD };
