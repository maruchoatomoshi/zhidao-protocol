const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.V4_PREVIEW_URL || 'http://127.0.0.1:8787';
if (!['127.0.0.1','localhost'].includes(new URL(base).hostname)) throw new Error('Local preview only');
(async () => {
  const out = path.resolve('.codex-tmp/xp-qa'); fs.mkdirSync(out,{recursive:true});
  const browser = await chromium.launch({channel:'msedge',headless:true});
  const page = await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true,reducedMotion:'reduce'});
  const errors=[], failures=[];
  page.on('pageerror', e=>errors.push(e.message));
  page.on('response', r=>{if(r.status()>=400 && /xp-home|zhidao-dragon|assets\/icons/.test(r.url())) failures.push(r.url());});
  await page.addInitScript(()=>{localStorage.setItem('zhidao.v4.theme','light'); window.__csp=[]; document.addEventListener('securitypolicyviolation',e=>window.__csp.push(e.violatedDirective));});
  try {
    await page.goto(base+'/app/?design=xp');
    await page.locator('[data-auth-preview]').click();
    await page.evaluate(()=>document.fonts.ready);
    assert.equal(await page.locator('html').getAttribute('data-design'),'xp');
    let layouts=0;
    for(const theme of ['light','dark']) {
      await page.evaluate(theme=>{document.documentElement.dataset.theme=theme;},theme);
      for(const width of [320,360,390,430,560,768,1280]) {
        await page.setViewportSize({width,height:844});
        await page.waitForTimeout(120);
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${theme}/${width}: page overflow`);
        assert.equal(await page.locator('.desktop-shortcuts button:visible').count(),4);
        const title=await page.locator('.journey-copy h2').boundingBox(),logo=await page.locator('.journey-logo').boundingBox();
        assert.ok(title.x+title.width<=logo.x+1,`${theme}/${width}: hero overlap`);
        assert.ok(await page.locator('.journey-logo').evaluate(n=>n.complete && n.naturalWidth>0));
        const profile=await page.locator('.profile-fab').boundingBox();
        assert.ok(profile.width>=44 && profile.height>=44);
        for(const target of await page.locator('.desktop-shortcuts button').all()) {
          const b=await target.boundingBox(); assert.ok(b.width>=44 && b.height>=44);
        }
        layouts++;
        if([320,390,1280].includes(width)) await page.screenshot({path:path.join(out,`home-${theme}-${width}.png`),fullPage:true});
        if(width===390) await page.screenshot({path:path.join(out,`phone-${theme}.png`)});
      }
    }
    await page.setViewportSize({width:390,height:844});
    for(const target of ['cases','campus-map','collection','tasks']) {
      await page.locator(`.desktop-shortcuts [data-open-screen="${target}"]`).click();
      assert.equal(await page.locator('html').getAttribute('data-current-screen'),target);
      await page.locator('[data-target="schedule"]').click();
    }
    await page.locator('.profile-fab').click();
    assert.equal(await page.locator('html').getAttribute('data-current-screen'),'profile');
    await page.locator('[data-target="schedule"]').click();
    await page.waitForTimeout(300);
    assert.equal(await page.evaluate(()=>document.getAnimations().filter(a=>a.playState==='running').length),0);
    assert.deepEqual(await page.evaluate(()=>window.__csp),[]);
    await page.emulateMedia({reducedMotion:'no-preference'});
    await page.waitForFunction(()=>document.documentElement.dataset.motion==='full');
    assert.equal(await page.locator('.journey-bubbles i').first().evaluate(n=>getComputedStyle(n).animationName),'journey-bubble-float');
    await page.locator('[data-target="more"]').click();
    await page.locator('[data-motion-toggle]').click();
    await page.locator('[data-target="schedule"]').click();
    await page.waitForTimeout(300);
    assert.equal(await page.evaluate(()=>document.getAnimations().filter(a=>a.playState==='running').length),0);
    await page.locator('.xp-review-note a').click();
    await page.locator('[data-auth-preview]').click();
    assert.equal(await page.locator('html').getAttribute('data-design'),null);
    assert.equal(await page.locator('.desktop-shortcuts button:visible').count(),2);
    assert.equal(await page.locator('.xp-titlebar:visible').count(),0);
    assert.deepEqual(errors,[]); assert.deepEqual(failures,[]);
    assert.deepEqual(await page.evaluate(()=>window.__csp),[]);
    const result={layouts,checks:['14 layouts / both themes / no horizontal overflow','logos loaded; no hero overlap; primary touch targets >=44px','4 shortcuts, profile and return navigation','reduced-motion and motion-off: zero running animations','Aero default restored by comparison link','no page exceptions or checked asset errors'],errors,failures,realMAX:'not tested'};
    fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(result,null,2)); console.log(JSON.stringify(result,null,2));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
