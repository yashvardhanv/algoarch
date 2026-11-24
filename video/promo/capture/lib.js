// Real-time product recorder: drives the REAL AlgoArch UI in Chromium and captures what it
// paints with CDP screencast (smooth, true timing), plus an injected macOS-style cursor.
const { chromium } = require('playwright');
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const http = require('http');
const { install, installImages, installPlayer } = require('./routes');

const BASE = 'http://127.0.0.1:5050';
const STATE = path.join(__dirname, 'state.json');
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const ease = t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const mockGet = (p) => new Promise(r => http.get('http://127.0.0.1:5099' + p, res => { let b = ''; res.on('data', c => b += c); res.on('end', () => r(b)); }));

const CURSOR_JS = () => {
  const boot = () => {
    if (document.getElementById('__cur')) return;
    const st = document.createElement('style');
    st.textContent = `@keyframes __rip{0%{transform:translate(-50%,-50%) scale(.2);opacity:.75}100%{transform:translate(-50%,-50%) scale(1.5);opacity:0}}
      #__cur{position:fixed;left:0;top:0;width:34px;height:34px;z-index:2147483647;pointer-events:none;transform:translate(-200px,-200px);filter:drop-shadow(0 3px 4px rgba(0,0,0,.5))}
      #__cur svg{transition:transform .12s ease;transform-origin:5px 3px}
      #__cur.down svg{transform:scale(.82)}
      .__rip{position:fixed;width:64px;height:64px;border-radius:50%;border:3px solid #f77e35;background:rgba(247,126,53,.18);z-index:2147483646;pointer-events:none;animation:__rip .55s ease-out forwards}`;
    document.documentElement.appendChild(st);
    const c = document.createElement('div'); c.id = '__cur';
    c.innerHTML = '<svg viewBox="0 0 24 24" width="34" height="34"><path d="M5 3l14 8.2-6.2 1.6 3.6 6.4-2.6 1.5-3.6-6.4L5.4 20z" fill="#fff" stroke="#111" stroke-width="1.3" stroke-linejoin="round"/></svg>';
    document.documentElement.appendChild(c);
    document.addEventListener('mousemove', e => { c.style.transform = `translate(${e.clientX - 5}px,${e.clientY - 3}px)`; window.__mx = e.clientX; window.__my = e.clientY; }, true);
    document.addEventListener('mousedown', e => { c.classList.add('down'); const r = document.createElement('div'); r.className = '__rip'; r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px'; document.documentElement.appendChild(r); setTimeout(() => r.remove(), 700); }, true);
    document.addEventListener('mouseup', () => c.classList.remove('down'), true);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
};

class Rec {
  static async login() {
    // one-time: sign in through the real UI and keep the session for every take
    const browser = await chromium.launch();
    const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
    await ctx.addInitScript(() => localStorage.setItem('algoarch-theme', 'dark'));
    await install(ctx); await installImages(ctx);
    const page = await ctx.newPage();
    await page.goto(BASE + '/', { waitUntil: 'networkidle' });
    await page.fill('input[type=email]', 'alex@example.com');
    await page.getByRole('button', { name: 'Continue', exact: true }).click();
    await page.waitForSelector('#view-roadmap.active', { timeout: 15000 });
    await page.waitForTimeout(800);
    await ctx.storageState({ path: STATE });
    await browser.close();
  }

  static async start(name, { dsf = 1.5, startUrl = BASE + '/', quality = 92 } = {}) {
    const r = new Rec();
    r.name = name; r.dir = path.join(__dirname, 'takes', name);
    fs.rmSync(r.dir, { recursive: true, force: true }); fs.mkdirSync(r.dir, { recursive: true });
    r.browser = await chromium.launch();
    r.ctx = await r.browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: dsf, storageState: STATE });
    await r.ctx.addInitScript(() => localStorage.setItem('algoarch-theme', 'dark'));
    await r.ctx.addInitScript(CURSOR_JS);
    await install(r.ctx); await installImages(r.ctx); await installPlayer(r.ctx);
    r.page = await r.ctx.newPage();
    r.page.on('pageerror', e => console.log('[pageerror]', e.message.slice(0, 160)));
    r.frames = []; r.paused = true; r.writes = [];
    r.cdp = await r.ctx.newCDPSession(r.page);
    r.cdp.on('Page.screencastFrame', async ({ data, metadata, sessionId }) => {
      if (!r.paused) {
        const i = r.frames.length; const f = path.join(r.dir, `f${String(i).padStart(5, '0')}.jpg`);
        r.frames.push({ t: metadata.timestamp, f });
        r.writes.push(fs.promises.writeFile(f, Buffer.from(data, 'base64')));
      }
      try { await r.cdp.send('Page.screencastFrameAck', { sessionId }); } catch (e) { /* closed */ }
    });
    await r.page.goto(startUrl, { waitUntil: 'networkidle' });
    r.mx = 960; r.my = 540;
    await r.page.mouse.move(r.mx, r.my);
    r.q = quality;
    return r;
  }

  async begin() { // start keeping frames; nudge the page so a first frame is painted
    this.paused = false;
    await this.cdp.send('Page.startScreencast', { format: 'jpeg', quality: this.q, everyNthFrame: 1 });
    await this.page.mouse.move(this.mx + 1, this.my); await this.page.mouse.move(this.mx, this.my);
  }
  pause() { this.paused = true; }
  resume() { this.paused = false; }
  async wait(ms) { await sleep(ms); }

  async moveTo(x, y, ms = 700) {
    const x0 = this.mx, y0 = this.my, dx = x - x0, dy = y - y0, dist = Math.hypot(dx, dy) || 1;
    const nx = -dy / dist, ny = dx / dist, bow = Math.min(60, dist * 0.08) * (dx >= 0 ? 1 : -1);
    const steps = Math.max(8, Math.round(ms / 16)); const t0 = Date.now();
    for (let i = 1; i <= steps; i++) {
      const u = ease(i / steps), cx = x0 + dx * u + nx * bow * Math.sin(Math.PI * u), cy = y0 + dy * u + ny * bow * Math.sin(Math.PI * u);
      await this.page.mouse.move(cx, cy);
      const target = t0 + (ms * i) / steps; const d = target - Date.now(); if (d > 0) await sleep(d);
    }
    this.mx = x; this.my = y;
  }
  async center(sel, off = {}) {
    const loc = typeof sel === 'string' ? this.page.locator(sel).first() : sel;
    await loc.scrollIntoViewIfNeeded().catch(() => {});
    const b = await loc.boundingBox();
    if (!b) throw new Error('no box for ' + sel);
    return { x: b.x + (off.fx ?? 0.5) * b.width, y: b.y + (off.fy ?? 0.5) * b.height, b };
  }
  async moveToEl(sel, ms = 700, off) { const c = await this.center(sel, off); await this.moveTo(c.x, c.y, ms); return c; }
  async clickEl(sel, ms = 700, off) { await this.moveToEl(sel, ms, off); await sleep(120); await this.page.mouse.down(); await sleep(90); await this.page.mouse.up(); await sleep(150); }
  async scrollTo(y, ms = 900) {
    const y0 = await this.page.evaluate(() => window.scrollY); const steps = Math.max(6, Math.round(ms / 16)); const t0 = Date.now();
    for (let i = 1; i <= steps; i++) {
      await this.page.evaluate(v => window.scrollTo(0, v), y0 + (y - y0) * ease(i / steps));
      const d = t0 + (ms * i) / steps - Date.now(); if (d > 0) await sleep(d);
    }
  }
  async type(text, cps = 14) { for (const ch of text) { await this.page.keyboard.type(ch); await sleep(1000 / cps * (0.7 + Math.random() * 0.6)); } }

  async finish({ crf = 15, width = 2880 } = {}) {
    await this.cdp.send('Page.stopScreencast').catch(() => {});
    await Promise.all(this.writes);
    const n = this.frames.length; if (!n) throw new Error('no frames');
    const lines = [];
    for (let i = 0; i < n; i++) {
      const dur = i < n - 1 ? Math.max(0.001, this.frames[i + 1].t - this.frames[i].t) : 0.12;
      lines.push(`file '${path.basename(this.frames[i].f)}'`, `duration ${dur.toFixed(4)}`);
    }
    lines.push(`file '${path.basename(this.frames[n - 1].f)}'`);
    fs.writeFileSync(path.join(this.dir, 'list.txt'), lines.join('\n'));
    const total = this.frames[n - 1].t - this.frames[0].t;
    const out = path.join(this.dir, '..', this.name + '.mp4');
    const p = spawnSync('ffmpeg', ['-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', path.join(this.dir, 'list.txt'), '-vf', `fps=30,scale=${width}:-2:flags=lanczos,format=yuv420p`, '-c:v', 'libx264', '-crf', String(crf), '-preset', 'medium', '-movflags', '+faststart', '-r', '30', out], { encoding: 'utf8' });
    if (p.status !== 0) throw new Error(p.stderr);
    await this.browser.close();
    const info = spawnSync('ffprobe', ['-v', 'error', '-show_entries', 'stream=width,height,nb_frames,duration', '-of', 'csv=p=0', out], { encoding: 'utf8' }).stdout.trim();
    console.log(`[${this.name}] ${n} captured frames over ${total.toFixed(2)}s  ->  ${out}  (${info})`);
    return out;
  }
}
module.exports = { Rec, sleep, mockGet, BASE };
