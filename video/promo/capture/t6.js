const { Rec, sleep } = require('./lib');
(async () => {
  const r = await Rec.start('t6-design');
  const p = r.page;
  await p.evaluate(() => window.openLesson('sy39', 'system-design')); await p.waitForSelector('.rd-root', { timeout: 20000 }); await sleep(1200);
  await r.begin();
  await sleep(500);
  await r.moveTo(1180, 520, 700);
  await r.scrollTo(700, 1500); await sleep(500);
  await r.scrollTo(1500, 1600); await sleep(500);
  await r.scrollTo(2300, 1600); await sleep(600);
  await r.finish();
})().catch(e => { console.error(e); process.exit(1); });
