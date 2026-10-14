const { test, expect } = require('@playwright/test');
const P = require('./probes');

const shell = body => `<!doctype html><html><head><style>
  body { margin: 0; font: 14px sans-serif; }
  /* As the app's own: a column of minmax(0, 1fr), so a panel keeps its width and wide content spills out of it. */
  .ov-wrap { display: grid; grid-template-columns: minmax(0, 1fr); gap: 20px; padding: 20px; }
  .panel { background: #fff; border: 1px solid #ddd; padding: 20px 24px; }
  .pair { display: flex; gap: 20px; align-items: flex-start; }
</style></head><body><main class="view active"><div class="ov-wrap">${body}</div></main></body></html>`;

test.describe('the probes', () => {
  test.beforeEach(({}, info) => test.skip(info.project.name !== 'laptop', 'synthetic pages are measured once'));

  test('a clean page has nothing to report', async ({ page }) => {
    await page.setContent(shell('<section class="panel"><h2>Sales</h2><p>Text</p></section>'));
    const m = await P.measure(page);
    expect(m.sideways).toEqual([]);
    expect(m.spill).toEqual([]);
    expect(P.panelCounts(m)).toEqual({});
  });

  test('content wider than its panel spills, unless a scroller holds it', async ({ page }) => {
    await page.setContent(shell('<section class="panel" id="a"><div style="width:2000px">wide</div></section>'
      + '<section class="panel" id="b"><div style="overflow-x:auto"><div style="width:2000px">wide</div></div></section>'));
    const m = await P.measure(page);
    expect(m.spill.length).toBe(1);
    expect(m.spill[0]).toContain('div');
    expect(m.sideways.length).toBe(1);
  });

  test('a section that is not a panel, a panel in a panel, and unequal neighbours are counted', async ({ page }) => {
    await page.setContent(shell('<section class="loose"><p>floating</p></section>'
      + '<section class="panel"><div class="panel">inner</div></section>'
      + '<div class="pair-holder" style="display:flex;gap:20px"><section class="panel" style="flex:1;height:100px">a</section><section class="panel" style="flex:1;height:160px">b</section></div>'));
    const c = P.panelCounts(await P.measure(page));
    expect(c.bad).toBeGreaterThanOrEqual(1);
    expect(c.nested).toBe(1);
    expect(c.heights).toBe(1);
  });
});
