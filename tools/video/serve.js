// Serves the lecture-video renderer and receives the finished MP4 from the browser.
//   node tools/video/serve.js [port]      then open http://127.0.0.1:<port>/lecture.html
const http = require('http');
const fs = require('fs');
const path = require('path');
const port = Number(process.argv[2] || 5098);
const out = path.join(__dirname, 'out');
fs.mkdirSync(out, { recursive: true });
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css' };
http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x');
  if (req.method === 'POST' && u.pathname === '/save') {
    const name = (u.searchParams.get('name') || 'video').replace(/[^\w-]/g, '_') + '.mp4';
    const chunks = [];
    req.on('data', c => chunks.push(c));
    req.on('end', () => { const buf = Buffer.concat(chunks); fs.writeFileSync(path.join(out, name), buf); res.writeHead(200); res.end(String(buf.length)); });
    return;
  }
  const file = path.join(__dirname, decodeURIComponent(u.pathname === '/' ? '/lecture.html' : u.pathname));
  if (!file.startsWith(__dirname) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); return res.end('not found'); }
  const size = fs.statSync(file).size, type = types[path.extname(file)] || 'application/octet-stream';
  const m = /bytes=(\d*)-(\d*)/.exec(req.headers.range || '');
  if (m) {
    const start = m[1] ? Number(m[1]) : 0, end = m[2] ? Math.min(Number(m[2]), size - 1) : size - 1;
    res.writeHead(206, { 'Content-Type': type, 'Accept-Ranges': 'bytes', 'Content-Range': 'bytes ' + start + '-' + end + '/' + size, 'Content-Length': end - start + 1 });
    return fs.createReadStream(file, { start, end }).pipe(res);
  }
  res.writeHead(200, { 'Content-Type': type, 'Accept-Ranges': 'bytes', 'Content-Length': size });
  fs.createReadStream(file).pipe(res);
}).listen(port, '127.0.0.1', () => console.log('video renderer on', port));
