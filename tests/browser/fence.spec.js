const { test, expect } = require('@playwright/test');
const S = require('./support');

test('a request to any other host is caught and named', async ({ page, context, baseURL }, info) => {
  test.skip(info.project.name !== 'laptop', 'the fence is checked once');
  const seen = await S.prepare(context, baseURL);
  const w = S.watch(page, baseURL);
  await S.open(page, w);
  // A host the page's CSP allows (img-src names cdn.shopify.com), so it is the
  // fence that catches it: a host the CSP refuses never reaches the network.
  await page.evaluate(() => { const i = new Image(); i.src = 'https://cdn.shopify.com/s/files/suite-proof.png'; document.body.append(i); });
  await page.waitForTimeout(500);
  await S.settle(page, w);
  expect(seen.outside).toEqual(['https://cdn.shopify.com/s/files/suite-proof.png']);
});

test('the page signs in and its fonts load without the internet', async ({ page, context, baseURL }, info) => {
  test.skip(info.project.name !== 'laptop', 'checked once');
  const seen = await S.prepare(context, baseURL);
  const w = S.watch(page, baseURL);
  await S.open(page, w);
  await expect(page.locator('#nav-overview')).toBeAttached();
  expect(await page.evaluate(() => document.fonts.check('16px Inter'))).toBe(true);
  expect(seen.outside).toEqual([]);
  expect(w.errors).toEqual([]);
  expect(w.failed).toEqual([]);
});
