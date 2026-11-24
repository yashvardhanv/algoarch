const { Rec, sleep } = require('./lib');
(async () => {
  const r = await Rec.start('t4-code');
  const p = r.page;
  await p.click('button[data-view="library"]'); await sleep(400);
  await p.click('.track-pill[data-track="dsa"]'); await sleep(700);
  // warm the Python runtime off-camera so the take shows a real, instant run
  await p.evaluate(() => window.openLesson('ds02', 'dsa')); await p.waitForSelector('.rd-cell .monaco-editor', { timeout: 20000 }); await sleep(800);
  await p.locator('.rd-cell button', { hasText: /^Run$/ }).click();
  await p.waitForFunction(() => /Ran in|Raised/.test(document.querySelector('.rd-cell-status')?.innerText || ''), null, { timeout: 60000 });
  await p.locator('.rd-cell button', { hasText: 'Reset' }).click(); await sleep(400);
  // back to the curriculum list for the take itself
  await p.click('button[data-view="library"]'); await sleep(900);
  await p.evaluate(() => window.scrollTo(0, 0)); await sleep(300);
  await r.begin();
  await sleep(400);
  await r.clickEl('#card-ds02 .btn-read-lesson', 900);
  await p.waitForSelector('.rd-cell .monaco-editor', { timeout: 20000 });
  await sleep(700);
  const cellTop = await p.evaluate(() => document.querySelector('.rd-cell').getBoundingClientRect().top + window.scrollY - 330);
  await r.scrollTo(cellTop, 1000);
  await sleep(300);
  // click the end of the `pass` line, select it, and type the solution like a person would
  const line3 = p.locator('.monaco-editor .view-line').nth(2);
  const b = await line3.boundingBox();
  await r.moveTo(b.x + b.width - 6, b.y + b.height / 2, 800);
  await sleep(120); await p.mouse.down(); await sleep(80); await p.mouse.up(); await sleep(250);
  await p.keyboard.press('End'); await p.keyboard.press('Shift+Home'); await sleep(300);
  const lines = [['seen = {}', 1], ['for i, x in enumerate(nums):', 1], ['need = target - x', 2], ['if need in seen:', 2], ['return [seen[need], i]', 3], ['seen[x] = i', 2], ['return []', 1]];
  let prev = null;
  for (let k = 0; k < lines.length; k++) {
    const [text, lvl] = lines[k];
    if (prev) {
      await p.keyboard.press('Escape'); await p.keyboard.press('Enter'); await sleep(70);
      const auto = prev[1] + (prev[0].trimEnd().endsWith(':') ? 1 : 0);
      for (let d = lvl; d < auto; d++) { await p.keyboard.press('Shift+Tab'); await sleep(40); }
    }
    await r.type(text, 26);
    prev = lines[k];
  }
  await p.keyboard.press('Escape');
  await sleep(700);
  await r.clickEl(p.locator('.rd-cell button', { hasText: 'Run 4 tests' }), 900);
  await p.waitForFunction(() => /passed|Raised/.test(document.querySelector('.rd-cell-status')?.innerText || ''), null, { timeout: 30000 });
  await sleep(1800);
  await r.moveTo(1500, 330, 700);
  await sleep(500);
  await r.finish();
})().catch(e => { console.error(e); process.exit(1); });
