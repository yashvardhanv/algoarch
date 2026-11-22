// Dev-only helper for capturing widget frames from the ORIGINAL lesson pages in a real browser.
// Serves the legacy PROJECTS folder read-only and collects JSON posted by the capture driver.
//   node tools/content/capture-server.js <projectsDir> [port] [outDir]
const http = require('http');
const fs = require('fs');
const path = require('path');

const root = path.resolve(process.argv[2]);
const port = Number(process.argv[3] || 5099);
const out = path.resolve(process.argv[4] || path.join(__dirname, '..', '..', 'data', 'capture'));
fs.mkdirSync(out, { recursive: true });
const types = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json', '.svg': 'image/svg+xml' };

http.createServer((req, res) => {
  const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*' };
  if (req.method === 'OPTIONS') { res.writeHead(204, cors); return res.end(); }
  const u = new URL(req.url, 'http://x');
  if (req.method === 'POST' && u.pathname === '/save') {
    const name = (u.searchParams.get('name') || 'x').replace(/[^\w.-]/g, '_');
    const chunks = [];
    req.on('data', c => chunks.push(c));
    req.on('end', () => {
      if (name === '_clean') fs.writeFileSync(path.join(out, '_clean'), '1');
      else fs.writeFileSync(path.join(out, name + '.json'), Buffer.concat(chunks));
      res.writeHead(200, cors); res.end('ok');
    });
    return;
  }
  // A page handler that never returns freezes the tab. The driver reports what it is about to do
  // (_progress); if a run died without finishing, that action is added to the skip list on restart.
  if (u.pathname === '/__begin') {
    const sk = path.join(out, '_skip.json'), pr = path.join(out, '_progress.json'), clean = path.join(out, '_clean');
    let skip = fs.existsSync(sk) ? JSON.parse(fs.readFileSync(sk, 'utf8')) : [];
    if (fs.existsSync(pr) && !fs.existsSync(clean)) {
      const last = fs.readFileSync(pr, 'utf8');
      let key = null, m;
      if ((m = /^click (.+)$/.exec(last))) key = m[1];
      else if ((m = /^act (.+)\|(\d+)\|(\d+)$/.exec(last))) key = m[1] + '|' + m[2] + '|act' + m[3];
      else if ((m = /^cell (.+?) = /.exec(last))) key = m[1];
      else if ((m = /^panel (.+)\|(\d+)$/.exec(last))) key = m[1] + '|' + m[2] + '|panel';
      if (key && !skip.includes(key)) { skip.push(key); fs.writeFileSync(sk, JSON.stringify(skip, null, 1)); console.log('skipping', key); }
    }
    if (fs.existsSync(clean)) fs.unlinkSync(clean);
    res.writeHead(200, { ...cors, 'Content-Type': 'application/json' }); return res.end(JSON.stringify(skip));
  }
  if (u.pathname === '/__driver.js') { res.writeHead(200, { ...cors, 'Content-Type': 'text/javascript' }); return res.end(fs.readFileSync(path.join(__dirname, 'capture-driver.js'))); }
  if (u.pathname === '/__runner.html') { res.writeHead(200, { ...cors, 'Content-Type': 'text/html; charset=utf-8' }); return res.end(fs.readFileSync(path.join(__dirname, 'capture-runner.html'))); }
  if (u.pathname === '/__pages') {
    const pages = [];
    for (const d of ['dsa-faang-prep', 'system-design-prep', 'ai-master-prep', 'behavioral-prep']) {
      const dir = path.join(root, d, 'visuals');
      if (fs.existsSync(dir)) for (const f of fs.readdirSync(dir).filter(x => x.endsWith('.html'))) pages.push(d + '/visuals/' + f);
    }
    const todo = u.searchParams.get('todo') === '1';
    const left = todo ? pages.filter(p => !fs.existsSync(path.join(out, p.replace(/\//g, '__').replace(/\.html$/, '') + '.json'))) : pages;
    res.writeHead(200, { ...cors, 'Content-Type': 'application/json' }); return res.end(JSON.stringify(left));
  }
  const file = path.join(root, decodeURIComponent(u.pathname));
  if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404, cors); return res.end('nf'); }
  res.writeHead(200, { ...cors, 'Content-Type': types[path.extname(file)] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(res);
}).listen(port, '127.0.0.1', () => console.log('capture server on', port, 'serving', root, 'saving to', out));
