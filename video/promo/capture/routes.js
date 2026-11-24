// Offline stand-ins for the CDNs the app uses (Monaco on cdnjs, Pyodide on jsDelivr),
// served from the same versions via npm, plus neutral handling of YouTube hosts.
const fs = require('fs');
const path = require('path');
const MONACO = path.join(__dirname, 'node_modules/monaco-editor/min');
const PYO = path.join(__dirname, 'node_modules/pyodide');
const types = { '.js': 'text/javascript', '.css': 'text/css', '.ttf': 'font/ttf', '.wasm': 'application/wasm', '.json': 'application/json', '.zip': 'application/zip', '.map': 'application/json' };

async function install(context) {
  await context.route('https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/**', (route) => {
    let rel = new URL(route.request().url()).pathname.replace('/ajax/libs/monaco-editor/0.45.0/min/', '');
    if (rel === 'vs/loader.min.js') rel = 'vs/loader.js';
    const f = path.join(MONACO, rel);
    if (!fs.existsSync(f)) return route.fulfill({ status: 404, body: 'nf' });
    route.fulfill({ status: 200, contentType: types[path.extname(f)] || 'application/octet-stream', headers: { 'access-control-allow-origin': '*' }, body: fs.readFileSync(f) });
  });
  await context.route('https://cdn.jsdelivr.net/pyodide/v0.26.4/full/**', (route) => {
    const rel = new URL(route.request().url()).pathname.replace('/pyodide/v0.26.4/full/', '');
    const f = path.join(PYO, rel);
    if (!fs.existsSync(f)) return route.fulfill({ status: 404, body: 'nf' });
    route.fulfill({ status: 200, contentType: types[path.extname(f)] || 'application/octet-stream', headers: { 'access-control-allow-origin': '*' }, body: fs.readFileSync(f) });
  });
}
module.exports = { install };

// Third-party images that cannot load in this sandbox are replaced with neutral, generated
// stand-ins (avatar from dicebear, lecture thumbnails from YouTube).
const crypto = require('crypto');
function avatarSvg() {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f77e35"/><stop offset="1" stop-color="#c43c00"/></linearGradient></defs><rect width="64" height="64" rx="32" fill="url(#g)"/><text x="32" y="42" text-anchor="middle" font-family="Schibsted Grotesk, sans-serif" font-weight="700" font-size="30" fill="#fff">A</text></svg>`;
}
function thumbSvg(id) {
  const h = parseInt(crypto.createHash('md5').update(id).digest('hex').slice(0, 4), 16);
  const hues = [215, 235, 262, 28, 18, 195];
  const hue = hues[h % hues.length];
  const x = 15 + (h % 60);
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 360"><defs><radialGradient id="r" cx="${x}%" cy="35%" r="85%"><stop offset="0" stop-color="hsl(${hue} 55% 30%)"/><stop offset="1" stop-color="hsl(${hue} 35% 11%)"/></radialGradient></defs><rect width="640" height="360" fill="url(#r)"/><g fill="none" stroke="hsl(${hue} 60% 70% / .16)" stroke-width="2"><path d="M0 250 C160 190 300 310 640 200"/><path d="M0 290 C180 240 320 340 640 250"/></g></svg>`;
}
async function installImages(context) {
  await context.route('https://api.dicebear.com/**', r => r.fulfill({ status: 200, contentType: 'image/svg+xml', body: avatarSvg() }));
  await context.route('https://img.youtube.com/**', r => {
    const id = new URL(r.request().url()).pathname.split('/')[2] || 'x';
    r.fulfill({ status: 200, contentType: 'image/svg+xml', body: thumbSvg(id) });
  });
}
module.exports.installImages = installImages;

// The Video Vault opens third-party YouTube embeds, which cannot load in this sandbox.
// For the promo, the embed is answered by an ORIGINAL lecture clip (lecture.webm) in a plain player.
const LECTURE = path.join(__dirname, 'takes', 'lecture.webm');
async function installPlayer(context) {
  await context.route('https://www.youtube.com/embed/**', r => r.fulfill({
    status: 200, contentType: 'text/html',
    body: '<!doctype html><body style="margin:0;background:#000"><video id="v" src="https://standin.local/lecture.webm" autoplay muted loop playsinline controls style="width:100vw;height:100vh;object-fit:contain;display:block"></video></body>'
  }));
  await context.route('https://standin.local/**', r => {
    const b = fs.readFileSync(LECTURE);
    r.fulfill({ status: 200, contentType: 'video/webm', headers: { 'content-length': String(b.length), 'accept-ranges': 'none' }, body: b });
  });
}
module.exports.installPlayer = installPlayer;
