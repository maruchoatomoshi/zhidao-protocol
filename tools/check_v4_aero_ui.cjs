/* All mutations target the disposable loopback preview only. */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const BASE = process.env.V4_PREVIEW_URL || 'http://127.0.0.1:8784';
const OUT = path.resolve('.codex-tmp/aero-qa');
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'no-preference' });
  const page = await context.newPage(), errors = [], checks = [], overflows = [], timings = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error' && /Content Security Policy|Refused to/.test(m.text())) errors.push(m.text()); });
  const screens = ['schedule','rating','shop','cases','tasks','more','profile','collection','implants','campus-map'];
  const open = async name => { await page.evaluate(name => showScreen(name), name); await page.waitForTimeout(80); };
  async function toggleMotion() {
    const previous = await page.locator('html').getAttribute('data-current-screen');
    await open('more');
    await page.locator('[data-motion-toggle]').click();
    await open(previous || 'schedule');
  }
  try {
    const setup = await browser.newContext(), staff = await setup.newPage();
    await staff.goto(BASE + '/app/');
    await staff.locator('[data-field="username"]').fill('case.operator');
    await staff.locator('[data-field="password"]').fill('preview-only-passphrase');
    await staff.getByRole('button', { name: 'Войти', exact: true }).click();
    await staff.locator('body.is-signed-in').waitFor();
    await staff.locator('[data-target="cases"]').click();
    await staff.locator('#caseGrantMembers input').first().check();
    await staff.locator('#caseGrantAmount').fill('7');
    await staff.locator('#caseGrantReason').fill('Prepare disposable motion QA');
    await staff.locator('#caseGrantSubmit').click(); await staff.locator('#caseGrantConfirm').click();
    await staff.locator('#caseGrantStatus').filter({ hasText: 'запас 7/7' }).waitFor();
    await setup.close();
    await page.goto(BASE + '/app/');
    await page.locator('[data-field="username"]').fill('case.student');
    await page.locator('[data-field="password"]').fill('preview-only-passphrase');
    await page.getByRole('button', { name: 'Войти', exact: true }).click();
    await page.locator('body.is-signed-in').waitFor();
    await page.waitForFunction(() => document.documentElement.dataset.motion === 'full');
    assert.match(await page.locator('#terminalSession').innerText(), /Личный/);
    for (const theme of ['light', 'dark']) {
      await page.emulateMedia({ colorScheme: theme });
      await page.waitForFunction(theme => document.documentElement.dataset.theme === theme, theme);
      for (const name of screens) {
        await open(name);
        if (name === 'collection') await page.locator('.case-owned-item').first().waitFor();
        if (name === 'implants') await page.locator('.implant-card').first().waitFor();
        for (const width of [320,360,390,768,1280]) {
          await page.setViewportSize({ width, height: 844 });
          const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
          if (overflow) overflows.push({ theme, name, width });
        }
        await page.setViewportSize({ width: 390, height: 844 });
        await page.waitForTimeout(400);
        await page.screenshot({ path: path.join(OUT, `${name}-${theme}.png`), fullPage: true });
      }
    }
    assert.deepEqual(overflows, []);
    checks.push('10 screens × 2 themes × 5 widths (320–1280): no horizontal page overflow');
    await open('rating');
    await page.locator('[data-tab-group="rating"] [data-tab="diary"]').click();
    assert.equal(await page.locator('[data-tab-panel="rating:diary"]').isVisible(), true);
    checks.push('tab change shows the requested panel');
    await toggleMotion();
    assert.equal(await page.locator('html').getAttribute('data-motion'), 'off');
    await page.reload(); await page.locator('body.is-signed-in').waitFor();
    assert.equal(await page.locator('html').getAttribute('data-motion'), 'off');
    assert.equal(await page.evaluate(() => document.getAnimations().filter(a => a.playState === 'running').length), 0);
    await toggleMotion();
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.waitForFunction(() => document.documentElement.dataset.motion === 'reduced');
    assert.equal(await page.locator('html').getAttribute('data-motion'), 'reduced');
    await toggleMotion();
    assert.equal(await page.locator('html').getAttribute('data-motion'), 'reduced');
    assert.equal(await page.evaluate(() => document.getAnimations().filter(a => a.playState === 'running').length), 0);
    checks.push('motion-off survives reload; OS reduced motion cannot be overridden; zero running animations in both');
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.waitForFunction(() => document.documentElement.dataset.motion === 'full');
    await open('cases'); await page.locator('#caseOpen:not([disabled])').waitFor();
    // Slow only the response. The real preview server still chooses/saves the reward.
    await page.route('**/cases/open', async route => { const response = await route.fetch(); await new Promise(r => setTimeout(r, 1200)); await route.fulfill({ response }); });
    let postCount = 0;
    page.on('request', r => { if (r.method() === 'POST' && r.url().endsWith('/cases/open')) postCount++; });
    const before = await page.request.get(BASE + '/api/v4/seasons/1/cases/state').then(r => r.json());
    const started = Date.now();
    await page.locator('#caseOpen').click();
    assert.equal(await page.locator('#scanWindow').getAttribute('data-scan-phase'), 'contact');
    await page.waitForFunction(() => document.getElementById('scanWindow').dataset.scanPhase === 'scan');
    assert.equal(await page.locator('#caseResultDialog').isVisible(), false);
    assert.equal(await page.locator('#caseOpen').isDisabled(), true);
    await page.screenshot({ path: path.join(OUT, 'scan-in-progress.png') });
    await page.waitForFunction(() => document.getElementById('scanWindow').dataset.scanPhase === 'reveal');
    await page.locator('#caseResultDialog[open]').waitFor();
    timings.push({ operation: 'full motion with 1200ms delayed reply', elapsedMs: Date.now() - started });
    const after = await page.request.get(BASE + '/api/v4/seasons/1/cases/state').then(r => r.json());
    assert.equal(postCount, 1);
    assert.equal(after.history.items[1].id, before.history.items[0].id);
    assert.equal(await page.locator('#caseResultTitle').innerText(), after.history.items[0].details.prize.name_ru);
    await page.screenshot({ path: path.join(OUT, 'reward-dark.png') });
    await page.locator('#caseResultDialog [data-case-close]').last().click();
    checks.push('contact → scan → actual response → reveal; one POST; reward matches stored history');
    await page.unroute('**/cases/open');
    // The scan wait must also stop when movement is switched off mid-flight.
    await page.route('**/cases/open', async route => { const response = await route.fetch(); await new Promise(r => setTimeout(r, 350)); await route.fulfill({ response }); });
    await page.locator('#caseOpen').click();
    await toggleMotion();
    await page.locator('#caseResultDialog[open]').waitFor();
    assert.equal(await page.locator('html').getAttribute('data-motion'), 'off');
    assert.equal(await page.locator('#scanWindow').getAttribute('aria-busy'), null);
    checks.push('disabling movement during an opening completes without a stuck busy state');
    await page.locator('#caseResultDialog [data-case-close]').last().click();
    await page.unroute('**/cases/open');
    await toggleMotion();
    await page.locator('#caseOpen').click();
    await page.waitForFunction(() => document.getElementById('scanWindow').dataset.scanPhase === 'reveal');
    const duringReveal = await page.request.get(BASE + '/api/v4/seasons/1/cases/state').then(r => r.json());
    await page.reload(); await page.locator('body.is-signed-in').waitFor();
    await open('cases');
    await page.getByRole('button', { name: 'Восстановить результат', exact: true }).click();
    await page.locator('#caseResultDialog[open]').waitFor();
    assert.deepEqual(await page.request.get(BASE + '/api/v4/seasons/1/cases/state').then(r => r.json()), duringReveal);
    await page.locator('#caseResultDialog [data-case-close]').last().click();
    checks.push('reload during the reveal preserves the request key and restores the same reward without charge');
    await page.emulateMedia({ colorScheme: 'light' });
    await open('cases');
    await page.locator('.case-collection-link').click();
    await page.locator('.case-owned-item').first().waitFor();
    assert.equal(await page.locator('#terminalAddress').innerText(), 'zhidao://collection');
    // Show three actual stored tiers, rather than forcing or inventing a jackpot.
    await open('cases');
    for (const tier of ['gold','purple','black']) {
      const data = await page.request.get(BASE + '/api/v4/seasons/1/cases/state').then(r => r.json());
      const row = data.history.items.find(r => r.details.tier === tier);
      if (!row) continue;
      await page.locator('#caseHistory .case-history-row').filter({ hasText: `№${row.id} ·` }).click();
      await page.waitForTimeout(700);
      await page.screenshot({ path: path.join(OUT, `reward-${tier}-light.png`) });
      await page.locator('#caseResultDialog [data-case-close]').last().click();
    }
    // Record a separate short tour with the test session; no login form/password in the video.
    const videoContext = await browser.newContext({ storageState: await context.storageState(), viewport: { width:390,height:844 },
      colorScheme: 'light', recordVideo: { dir: OUT, size: { width:390,height:844 } } });
    const tour = await videoContext.newPage();
    await tour.goto(BASE + '/app/'); await tour.locator('body.is-signed-in').waitFor();
    await tour.waitForTimeout(900);
    for (const name of ['rating','tasks','more','cases']) {
      await tour.locator(`[data-target="${name}"]`).click(); await tour.waitForTimeout(700);
    }
    await tour.locator('#caseOpen:not([disabled])').waitFor();
    await tour.locator('#caseOpen').click(); await tour.locator('#caseResultDialog[open]').waitFor();
    await tour.waitForTimeout(1500);
    const video = tour.video(); await videoContext.close(); await video.saveAs(path.join(OUT, 'aero-tour.webm'));
    assert.deepEqual(errors, []);
    checks.push('zero page exceptions / CSP violations; local mobile animation video captured');
    fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify({ checks, errors, overflows, timings, actualMaxDevice: 'not tested' }, null, 2));
    console.log(JSON.stringify({ checks, timings, output: OUT }, null, 2));
  } finally { await context.close(); await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
