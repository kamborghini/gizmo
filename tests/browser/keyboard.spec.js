// Windows by keyboard alone, under the app's own rule (the Guide's Design
// page; docs/DESIGN.md, Windows): a window holding work closes only by its X,
// never on Escape, so a slip of the key cannot lose what was typed. So: the
// opener is reached and pressed from the keyboard, focus moves into the
// window, Escape leaves it open, Tab stays inside it, the X pressed from the
// keyboard closes it, and focus goes back to what opened it. Nothing is saved.
// The three windows screens.js measures, then every other window the seeded
// world can open (windows.js).
const { test, expect } = require('@playwright/test');
const S = require('./support');
const P = require('./probes');
const SCREENS = require('./screens');
const WINDOWS = require('./windows');

const inside = () => !!document.activeElement && !!document.activeElement.closest('.modal-overlay.show .modal');

async function mark(page, sel, text) {
  await page.evaluate(({ sel, text }) => {
    const e = [...document.querySelectorAll(sel)].filter(x => x.offsetParent || x.getClientRects().length)
      .find(x => !text || (x.innerText || '').trim().startsWith(text));
    if (!e) throw new Error('no opener ' + sel + ' ' + (text || ''));
    e.setAttribute('data-suite-opener', '');
  }, { sel, text });
}

async function openByKeyboard(page, j) {
  if (j.menu) {
    await mark(page, j.menu.sel);
    const btn = page.locator('[data-suite-opener]');
    await btn.focus();
    await page.keyboard.press('Enter');
    await page.waitForSelector('.dmenu');
    for (let i = 0; i < 20; i++) {
      const t = await page.evaluate(() => ((document.activeElement && document.activeElement.innerText) || '').trim());
      if (t.startsWith(j.menu.item)) break;
      await page.keyboard.press('ArrowDown');
    }
    await page.keyboard.press('Enter');
    return;
  }
  await mark(page, j.opener.sel, j.opener.text);
  const opener = page.locator('[data-suite-opener]');
  await opener.focus();
  expect(await opener.evaluate(e => document.activeElement === e), 'the opener can be reached by keyboard').toBe(true);
  await page.keyboard.press('Enter');
}

async function journey(page, w) {
  await page.waitForSelector('.modal-overlay.show .modal');
  await expect.poll(() => page.evaluate(inside), { message: 'focus moved into the window' }).toBe(true);
  expect(await P.unnamed(page), 'controls with no name').toEqual([]);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  await expect(page.locator('.modal-overlay.show'), 'Escape leaves a window open: X only').toHaveCount(1);
  for (let i = 0; i < 12; i++) await page.keyboard.press('Tab');
  expect(await page.evaluate(inside), 'Tab stays inside the window').toBe(true);
  // A window that redraws its page as it closes (a CRM deal redraws the board)
  // replaces its opener; the new control carries the same data-focus-key.
  const key = await page.evaluate(() => { const o = document.querySelector('[data-suite-opener]'); return (o && o.dataset.focusKey) || ''; });
  const x = page.locator('.modal-overlay.show .modal-head :is(button[title="Close"], button[aria-label="Close"])').first();
  await x.focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('.modal-overlay.show')).toHaveCount(0);
  await expect.poll(() => page.evaluate(key => {
    const a = document.activeElement, o = document.querySelector('[data-suite-opener]');
    if (o) return a === o || o.contains(a);
    return !!key && !!a && a.dataset && a.dataset.focusKey === key;
  }, key), { message: 'focus went back to what opened the window' }).toBe(true);
  expect(w.writes, 'the window wrote something').toEqual([]);
  expect(w.errors, 'script errors').toEqual([]);
}

for (const s of SCREENS.filter(x => x.kind === 'dialog')) {
  test(`keyboard: ${s.id}`, async ({ page, context, baseURL }, info) => {
    test.skip(info.project.name !== 'laptop', 'the journeys run once, at laptop size');
    await S.prepare(context, baseURL);
    const w = S.watch(page, baseURL);
    await S.open(page, w);
    await s.before(page, S.helpers(page, w, info.project.name));
    await openByKeyboard(page, { opener: s.opener });
    await journey(page, w);
  });
}

for (const j of WINDOWS) {
  test(`keyboard: ${j.id}`, async ({ page, context, baseURL }, info) => {
    test.skip(info.project.name !== 'laptop', 'the journeys run once, at laptop size');
    await S.prepare(context, baseURL);
    const w = S.watch(page, baseURL);
    await S.open(page, w);
    await j.before(page, S.helpers(page, w, info.project.name));
    await openByKeyboard(page, j);
    await journey(page, w);
  });
}

// On a phone a tap moves no focus, so the last control focused outside a
// window can be a text field the person left long before. Closing a window
// must not send focus back there: on an iPhone that raises the keyboard.
test('a window opened without focus does not hand it back to a field left earlier', async ({ page, context, baseURL }, info) => {
  test.skip(info.project.name !== 'laptop', 'checked once');
  await S.prepare(context, baseURL);
  const w = S.watch(page, baseURL);
  await S.open(page, w);
  const s = SCREENS.find(x => x.id === 'loans~unit');
  await s.before(page, S.helpers(page, w, info.project.name));
  const field = page.locator('input:visible').first();
  await field.focus();
  await page.evaluate(() => document.activeElement.blur());       // a tap on nothing in particular
  await page.evaluate(sel => document.querySelector(sel).click(), s.opener.sel);   // a tap moves no focus
  await page.waitForSelector('.modal-overlay.show .modal');
  await page.evaluate(() => document.querySelector('.modal-overlay.show .modal-head button[title="Close"]').click());
  await expect(page.locator('.modal-overlay.show')).toHaveCount(0);
  await page.waitForTimeout(300);
  expect(await field.evaluate(e => document.activeElement === e), 'focus stayed away from the old field').toBe(false);
});

// The queue's rows are not tab stops (19 Oct 2026: they held the order link and
// the actions); a keyboard opens an order's preview with the row's Preview button.
test('keyboard: the queue opens an order from its Preview button', async ({ page, context, baseURL }, info) => {
  test.skip(info.project.name !== 'laptop', 'checked once');
  await S.prepare(context, baseURL);
  const w = S.watch(page, baseURL);
  await S.open(page, w);
  await SCREENS.find(x => x.id === 'labels').go(page, S.helpers(page, w, info.project.name));
  const pv = () => page.locator('#labels-content .lbl-qrow').first().locator('button[aria-expanded]').first();
  expect(await pv().getAttribute('aria-expanded'), 'the preview starts closed').toBe('false');
  await pv().focus();
  await page.keyboard.press('Enter');
  await page.waitForSelector('#labels-content .lbl-preview');
  expect(await pv().getAttribute('aria-expanded'), 'and opens from the keyboard').toBe('true');
  expect(w.writes).toEqual([]);
  expect(w.errors).toEqual([]);
});
