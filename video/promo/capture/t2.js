const { Rec, sleep } = require('./lib');
(async () => {
  const r = await Rec.start('t2-explore');
  const p = r.page;
  await r.begin();
  await sleep(450);
  await r.moveTo(1000, 520, 700);
  const top = await p.evaluate(() => document.querySelector('.pillars-section').getBoundingClientRect().top + window.scrollY - 110);
  await r.scrollTo(top, 1500);
  await sleep(300);
  for (const i of [1, 2, 3, 4]) { await r.moveToEl(`#pillars-container > :nth-child(${i})`, 600, { fy: 0.35 }); await sleep(320); }
  await r.clickEl(p.locator('#pillars-container > :nth-child(3)').getByText('View track'), 700);
  await sleep(1000);
  await r.clickEl('.track-pill[data-track="dsa"]', 800); await sleep(900);
  await r.clickEl('.track-pill[data-track="system-design"]', 650); await sleep(900);
  await r.scrollTo(380, 900); await sleep(700);
  await r.finish();
})().catch(e => { console.error(e); process.exit(1); });
