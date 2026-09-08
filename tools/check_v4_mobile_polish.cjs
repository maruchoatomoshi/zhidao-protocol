const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
(async()=>{
  const out=path.resolve('.codex-tmp/mobile-qa'); fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,colorScheme:'dark',reducedMotion:'reduce'});
  await context.addInitScript(()=>localStorage.setItem('zhidao.v4.theme','light'));
  const page=await context.newPage(), errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  try {
    await page.goto('http://127.0.0.1:8786/app/');
    await page.locator('[data-auth-preview]').click();
    await page.evaluate(()=>document.fonts.ready);
    assert.equal(await page.locator('html').getAttribute('data-theme'),'light');
    assert.equal(await page.evaluate(()=>getComputedStyle(document.documentElement).colorScheme),'light only');
    assert.equal(await page.locator('meta[name="color-scheme"]').getAttribute('content'),'only light');
    assert.equal(await page.locator('.internet-toolbar button').count(),0);
    assert.equal(await page.locator('[data-theme-toggle]').count(),1);
    assert.equal(await page.locator('[data-screen="more"] [data-motion-toggle]').count(),1);
    await page.waitForTimeout(300);
    assert.equal(await page.locator('.journey-card .online-pill, .journey-card .weather-orb, .journey-card .journey-meta').count(),0);
    assert.equal((await page.locator('#scheduleTitle').innerText()).endsWith('.'),false);
    assert.equal(await page.locator('.journey-bubbles i').count(),3);
    for (const width of [320,390,430]) {
      await page.setViewportSize({width,height:844});
      for (const selector of ['.brand-logo','.journey-logo']) {
        assert.ok(await page.locator(selector).evaluate(img=>img.complete && img.naturalWidth>0));
      }
      const title=await page.locator('.journey-copy h2').boundingBox();
      const logo=await page.locator('.journey-logo').boundingBox();
      assert.ok(title.x+title.width<=logo.x,'Hero logo must not overlap the title');
    }
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(out,'day-normal.png')});
    const cdp=await context.newCDPSession(page);
    await cdp.send('Emulation.setAutoDarkModeOverride',{enabled:true});
    await page.screenshot({path:path.join(out,'day-force-dark.png')});
    await page.locator('[data-target="more"]').tap();
    await page.locator('.hub-orb img').first().waitFor({state:'attached'});
    await page.waitForTimeout(200);
    assert.equal(await page.locator('.hub-orb svg').count(),0);
    assert.equal(await page.locator('[data-motion-toggle]').isVisible(),true);
    assert.equal(await page.locator('[data-theme-toggle] [data-theme-value]').innerText(),'Дневная');
    await page.screenshot({path:path.join(out,'more-light.png'),fullPage:true});
    await page.locator('[data-theme-toggle]').tap();
    assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');
    await page.screenshot({path:path.join(out,'more-dark.png'),fullPage:true});
    await page.emulateMedia({reducedMotion:'no-preference'});
    await page.waitForFunction(()=>document.documentElement.dataset.motion==='full');
    await page.locator('[data-motion-toggle]').tap();
    assert.equal(await page.locator('html').getAttribute('data-motion'),'off');
    await page.reload(); await page.locator('[data-auth-preview]').click();
    assert.equal(await page.locator('html').getAttribute('data-motion'),'off');
    const highlights=await page.locator('button').evaluateAll(nodes=>[...new Set(nodes.map(n=>getComputedStyle(n).webkitTapHighlightColor))]);
    assert.deepEqual(highlights,['rgba(0, 0, 0, 0)']);
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(()=>document.activeElement.matches(':focus-visible')),true);
    assert.notEqual(await page.evaluate(()=>getComputedStyle(document.activeElement).outlineStyle),'none');
    for(const screen of ['schedule','more','profile','cases','campus-map']){
      await page.evaluate(s=>showScreen(s),screen);
      for(const width of [320,390,430]){
        await page.setViewportSize({width,height:844});
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),screen+' overflow '+width);
      }
    }
    assert.deepEqual(errors,[]);
    const result={checks:['day theme on dark OS: explicit only-light','top buttons removed; one theme and motion control in More','all hub SVG silhouettes replaced by illustrated assets','theme labels and switches work','motion-off survives reload','touch highlight transparent; keyboard focus visible','15 screen/width combinations without overflow'],errors,realMax:'not tested',screenshots:out};
    fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(result,null,2)); console.log(JSON.stringify(result,null,2));
  }finally{await context.close();await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
