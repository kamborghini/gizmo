// Three windows, by keyboard alone, under the app's own rule (the Guide's
// Design page): a window holding work closes only by its X, never on Escape,
// so a slip of the key cannot lose what was typed. So: the opener is reached
// and pressed from the keyboard, focus moves into the window, Escape leaves it
// open, Tab stays inside it, the X pressed from the keyboard closes it, and
// focus goes back to what opened it. Nothing is saved.
const { test, expect } = require('@playwright/test');
const S = require('./support');
const SCREENS = require('./screens');

const inside = () => !!document.activeElement && !!document.activeElement.closest('.modal-overlay.show .modal');

for (const s of SCREENS.filter(x => x.kind === 'dialog')) {
  test(`keyboard: ${s.id}`, async ({ page, context, baseURL }, info) => {
    test.skip(info.project.name !== 'laptop', 'the journeys run once, at laptop size');
    await S.prepare(context, baseURL);
    const w = S.watch(page, baseURL);
    await S.open(page, w);
    await s.before(page, S.helpers(page, w, info.project.name));
    await page.evaluate(({ sel, text }) => {
      const e = [...document.querySelectorAll(sel)].filter(x => x.offsetParent || x.getClientRects().length)
        .find(x => !text || (x.innerText || '').trim().startsWith(text));
      if (!e) throw new Error('no opener ' + sel + ' ' + (text || ''));
      e.setAttribute('data-suite-opener', '');
    }, s.opener);
    const opener = page.locator('[data-suite-opener]');
    await opener.focus();
    expect(await opener.evaluate(e => document.activeElement === e), 'the opener can be reached by keyboard').toBe(true);
    await page.keyboard.press('Enter');
    await page.waitForSelector('.modal-overlay.show .modal');
    await expect.poll(() => page.evaluate(inside), { message: 'focus moved into the window' }).toBe(true);

    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
    await expect(page.locator('.modal-overlay.show'), 'Escape leaves a window open: X only').toHaveCount(1);

    for (let i = 0; i < 12; i++) await page.keyboard.press('Tab');
    expect(await page.evaluate(inside), 'Tab stays inside the window').toBe(true);

    // A window that redraws its page as it closes (a CRM deal redraws the board)
    // replaces its opener; the new control carries the same data-focus-key.
    const key = await opener.evaluate(e => e.dataset.focusKey || '');
    const x = page.locator('.modal-overlay.show .modal-head :is(button[title="Close"], button[aria-label="Close"])').first();
    await x.focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('.modal-overlay.show')).toHaveCount(0);
    await expect.poll(() => page.evaluate(key => {
      const a = document.activeElement, o = document.querySelector('[data-suite-opener]');
      if (o) return a === o || o.contains(a);
      return !!key && !!a && a.dataset && a.dataset.focusKey === key;
    }, key), { message: 'focus went back to what opened the window' }).toBe(true);
    expect(w.writes).toEqual([]);
  });
}
