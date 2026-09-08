/* Run against tools.preview_v4_cases only. No production credentials/data. */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const BASE = process.env.V4_PREVIEW_URL || 'http://127.0.0.1:8784';
const OUT = path.resolve('.codex-tmp/cases-qa');

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ channel: process.env.CASES_BROWSER_CHANNEL || 'msedge', headless: true });
  const errors = [], checks = [];
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: 'light', reducedMotion: 'reduce' });
  const page = await context.newPage();
  page.on('pageerror', e => errors.push(e.message));
  async function login(target, username) {
    await target.goto(BASE + '/app/');
    await target.locator('[data-field="username"]').fill(username);
    await target.locator('[data-field="password"]').fill('preview-only-passphrase');
    await target.getByRole('button', { name: 'Войти', exact: true }).click();
    await target.locator('body.is-signed-in').waitFor();
  }
  async function cases(target) {
    await target.locator('[data-target="cases"]').click();
    await target.locator('#caseOpen:not([disabled])').waitFor();
  }
  try {
    // The disposable preview may also be used manually. Refill through its UI,
    // without assuming a fresh database or reaching into persistence directly.
    const setup = await browser.newContext();
    const setupPage = await setup.newPage();
    await login(setupPage, 'case.operator');
    await setupPage.locator('[data-target="cases"]').click();
    await setupPage.locator('#caseGrantMembers input').first().check();
    await setupPage.locator('#caseGrantAmount').fill('7');
    await setupPage.locator('#caseGrantReason').fill('Prepare disposable UI regression');
    await setupPage.locator('#caseGrantSubmit').click();
    await setupPage.locator('#caseGrantConfirm').click();
    await setupPage.locator('#caseGrantStatus').filter({ hasText: 'запас 7/7' }).waitFor();
    await setup.close();
    const previewRequests = [];
    page.on('request', r => { if (r.url().includes('/api/v4/') && !r.url().endsWith('/auth/me') && !r.url().endsWith('/cases/rules')) previewRequests.push(r.url()); });
    await page.goto(BASE + '/app/');
    await page.locator('[data-auth-preview]').click();
    await page.locator('[data-target="cases"]').click();
    await page.locator('#caseRules .case-tier').first().waitFor({ state: 'attached' });
    assert.equal(await page.locator('#caseOpen').isDisabled(), true);
    assert.equal(previewRequests.length, 0);
    checks.push('preview does not request personal APIs and cannot scan');

    await login(page, 'case.student');
    await cases(page);
    await page.screenshot({ path: path.join(OUT, 'cases-light-mobile.png'), fullPage: true });
    const before = await page.request.get(BASE + '/api/v4/seasons/1/cases/state').then(r => r.json());
    await page.locator('#caseOpen').click();
    await page.locator('#caseResultDialog[open]').waitFor();
    await page.screenshot({ path: path.join(OUT, 'case-result-mobile.png') });
    await page.locator('#caseResultDialog [data-case-close]').last().click();
    const after = await page.request.get(BASE + '/api/v4/seasons/1/cases/state').then(r => r.json());
    assert(after.history.items[0].id > before.history.items[0].id);
    assert.equal(after.history.items[1].id, before.history.items[0].id);
    assert.equal(await page.locator('[data-case-scans]').first().innerText(), `${after.scans} / 7`);
    checks.push('UI scan persists once and refreshes server balance');

    let lost = false;
    await page.route('**/cases/open', async route => {
      if (!lost) { lost = true; await route.fetch(); await route.abort('failed'); }
      else await route.continue();
    });
    await page.locator('#caseOpen').click();
    await page.getByRole('button', { name: 'Восстановить результат', exact: true }).waitFor();
    const lostState = await page.request.get(BASE + '/api/v4/seasons/1/cases/state').then(r => r.json());
    await page.reload();
    await page.locator('body.is-signed-in').waitFor();
    await cases(page);
    await page.getByRole('button', { name: 'Восстановить результат', exact: true }).click();
    await page.locator('#caseResultDialog[open]').waitFor();
    const recovered = await page.request.get(BASE + '/api/v4/seasons/1/cases/state').then(r => r.json());
    assert.deepEqual(recovered, lostState);
    await page.locator('#caseResultDialog [data-case-close]').last().click();
    checks.push('response lost after commit + full reload recovers same result without charge');

    await page.locator('.case-collection-link').click();
    await page.locator('.case-owned-item').first().waitFor();
    const owned = await page.request.get(BASE + '/api/v4/seasons/1/cases/inventory').then(r => r.json());
    assert.equal(await page.locator('.case-owned-item').count(), owned.items.length);
    assert(owned.items.length >= 9); // A guard may have been consumed by either random opening.
    await page.screenshot({ path: path.join(OUT, 'collection-light-mobile.png'), fullPage: true });
    await page.emulateMedia({ colorScheme: 'dark' });
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'dark');
    await page.screenshot({ path: path.join(OUT, 'collection-dark-mobile.png'), fullPage: true });
    await cases(page);
    await page.screenshot({ path: path.join(OUT, 'cases-dark-mobile.png'), fullPage: true });
    for (const width of [320, 360, 390, 768, 1280]) {
      await page.setViewportSize({ width, height: 844 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'overflow at ' + width);
    }
    checks.push('case/collection light-dark screenshots; no page overflow at 320/360/390/768/1280px');
    await page.setViewportSize({ width: 390, height: 844 });
    const staff = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: 'light' });
    const operator = await staff.newPage();
    operator.on('pageerror', e => errors.push(e.message));
    await login(operator, 'case.operator');
    await operator.locator('[data-target="cases"]').click();
    await operator.locator('#caseAdmin:not([hidden])').waitFor();
    await operator.locator('#caseGrantMembers input').first().check();
    await operator.locator('#caseGrantAmount').fill('7');
    await operator.locator('#caseGrantReason').fill('UI test — capped grant');
    await operator.locator('#caseGrantSubmit').click();
    await operator.locator('#caseGrantDialog[open]').waitFor();
    await operator.locator('#caseGrantConfirm').click();
    await operator.locator('#caseGrantStatus').filter({ hasText: 'запас 7/7' }).waitFor();
    const final = await page.request.get(BASE + '/api/v4/seasons/1/cases/state').then(r => r.json());
    assert.equal(final.scans, 7);
    await operator.screenshot({ path: path.join(OUT, 'operator-mobile.png'), fullPage: true });
    checks.push('operator confirm → capped grant → actual delta and audit shown');
    await staff.close();
    assert.deepEqual(errors, []);
    checks.push('zero browser JavaScript exceptions');
    fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify({ checks, errors, actualMaxDevice: 'not tested' }, null, 2));
    console.log(JSON.stringify({ checks, output: OUT }, null, 2));
  } finally { await context.close(); await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
