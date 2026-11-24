const { Rec, sleep, mockGet } = require('./lib');
async function stream(per = 3, gap = 46) {
  for (let i = 0; i < 400; i++) { const o = JSON.parse(await mockGet(`/emit?n=${per}`)); if (!o.open) break; await sleep(gap); }
}
(async () => {
  await mockGet('/reset');
  const r = await Rec.start('t5-mentor');
  const p = r.page;
  await p.evaluate(() => window.openLesson('ai23', 'ai-engineering')); await p.waitForSelector('.rd-root', { timeout: 20000 }); await sleep(1000);
  await r.begin();
  await sleep(500);
  await r.clickEl(p.getByRole('button', { name: 'Ask mentor' }), 900);
  await sleep(900);
  await r.clickEl('#ai-input', 700);
  await r.type('Explain how a transformer architecture works, with a practical example.', 24);
  await sleep(350);
  await p.keyboard.press('Enter');
  await sleep(900);                         // "thinking" state
  await stream(3, 50);
  await sleep(1400);
  await r.clickEl('#ai-input', 700);
  await r.type('Explain that in simpler terms.', 22);
  await sleep(300);
  await p.keyboard.press('Enter');
  await sleep(700);
  await stream(3, 50);
  await sleep(1500);
  await r.finish();
})().catch(e => { console.error(e); process.exit(1); });
