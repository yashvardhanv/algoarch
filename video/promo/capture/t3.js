const { Rec, sleep } = require('./lib');
(async () => {
  const r = await Rec.start('t3-vault');
  const p = r.page;
  await r.begin();
  await sleep(400);
  await r.clickEl('button[data-view="videos"]', 800);
  await sleep(900);
  await r.moveToEl('.video-card:nth-child(2)', 700, { fy: 0.3 }); await sleep(600);
  await r.moveToEl('.video-card:nth-child(3)', 520, { fy: 0.3 }); await sleep(450);
  await r.clickEl('.v-pill[data-vfilter="dsa"]', 800); await sleep(900);
  const hm = p.locator('.video-card', { hasText: 'Design Hashmap' }).first();
  const top = await hm.evaluate(e => e.getBoundingClientRect().top + window.scrollY - 330);
  await r.scrollTo(top, 1300); await sleep(500);
  await r.clickEl(hm, 800, { fy: 0.3 });
  await sleep(2300);                                   // lecture plays
  const fr = p.locator('#video-embed-container iframe');
  const b = await fr.boundingBox();
  await r.moveTo(b.x + b.width * 0.5, b.y + b.height * 0.45, 600);
  await sleep(200); await p.mouse.down(); await sleep(80); await p.mouse.up();   // pause
  await sleep(1100);
  await p.mouse.down(); await sleep(80); await p.mouse.up();                       // resume
  await sleep(1300);
  await r.moveTo(b.x + b.width * 0.72, b.y + b.height - 26, 600);                 // skip ahead on the seek bar
  await sleep(150); await p.mouse.down(); await sleep(80); await p.mouse.up();
  await sleep(1500);
  await r.finish();
})().catch(e => { console.error(e); process.exit(1); });
