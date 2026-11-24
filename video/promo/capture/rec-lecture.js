const { Rec, sleep } = require('./lib');
(async () => {
  const r = await Rec.start('lecture', { startUrl: 'about:blank', dsf: 1 });
  await r.begin(); await sleep(150);
  await r.page.goto('file://' + __dirname + '/lecture.html', { waitUntil: 'load' });
  await sleep(12800);
  await r.finish({ width: 1280, crf: 20 });
})().catch(e => { console.error(e); process.exit(1); });
