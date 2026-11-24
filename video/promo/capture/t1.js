const { Rec, sleep, BASE } = require('./lib');
(async () => {
  const r = await Rec.start('t1-landing', { startUrl: 'about:blank' });
  await r.begin();
  await sleep(250);
  await r.page.goto(BASE + '/', { waitUntil: 'load' });
  await sleep(1500);                       // hero entrance plays for real
  await r.moveTo(560, 470, 900);
  await r.moveToEl('#hero-start', 700);
  await sleep(1300);
  await r.finish();
})().catch(e => { console.error(e); process.exit(1); });
