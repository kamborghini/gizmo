// Every state, at every size: no script error, no failed or outside request,
// no write, no sideways scroll, nothing spilling out of its panel; and the
// panel rules and accessibility (WCAG 2.2 A and AA) held by the ratchet.
const path = require('path');
const fs = require('fs');
const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const S = require('./support');
const P = require('./probes');
const R = require('./record');
const SCREENS = require('./screens');

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

for (const s of SCREENS) {
  test(s.id, async ({ page, context, baseURL }, info) => {
    const seen = await S.prepare(context, baseURL);
    const w = S.watch(page, baseURL);
    await S.open(page, w);
    const h = S.helpers(page, w, info.project.name);
    await s.go(page, h);
    await S.settle(page, w);
    const key = `${s.id}@${info.project.name}`;
    const shots = path.join(S.RUN, 'shots');
    fs.mkdirSync(shots, { recursive: true });
    await page.screenshot({ path: path.join(shots, `${info.project.name}-${s.id.replace(/~/g, '-')}.png`), fullPage: true });

    expect(w.errors, 'script errors').toEqual([]);
    expect(w.failed, 'failed requests to the app').toEqual([]);
    expect(seen.outside, 'requests to other hosts').toEqual([]);
    expect(w.writes, 'the screen wrote something').toEqual([]);
    const m = await P.measure(page);
    expect(m.sideways, 'sideways scroll').toEqual([]);
    expect(m.spill, 'content spilling out of its panel').toEqual([]);

    const ax = await new AxeBuilder({ page }).withTags(TAGS).analyze();
    const a11y = R.check('a11y', key, R.counts(ax.violations.map(v => [v.id, v.nodes.length])));
    const panels = R.check('panels', key, P.panelCounts(m));
    if (!R.UPDATE) {
      expect(a11y.worse, 'new accessibility problems').toEqual([]);
      expect(panels.worse, 'new panel-rule problems').toEqual([]);
      expect(a11y.better, 'fixed: lower the record with UPDATE_RECORD=1 make test-browser').toEqual([]);
      expect(panels.better, 'fixed: lower the record with UPDATE_RECORD=1 make test-browser').toEqual([]);
    }
  });
}
