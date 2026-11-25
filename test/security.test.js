// Integration tests: spawns the real server on a temp copy of data/ and exercises
// auth, plan gating, upgrades, payment safety and admin protection.
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');

const ROOT = path.join(__dirname, '..');
const PORT = 5600 + Math.floor(Math.random() * 300);
let child;
let tmpData;
let defaultToken = null;

function request(method, urlPath, { body, token, headers = {} } = {}) {
  return new Promise((resolve, reject) => {
    const payload = body ? JSON.stringify(body) : null;
    const h = { ...headers };
    if (payload) { h['Content-Type'] = 'application/json'; h['Content-Length'] = Buffer.byteLength(payload); }
    // requests carry a default signed-in test user unless a test passes token: false (anonymous)
    const t = token === undefined ? defaultToken : token;
    if (t) h['Authorization'] = 'Bearer ' + t;
    const req = http.request({ host: '127.0.0.1', port: PORT, path: urlPath, method, headers: h }, res => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        let json = null;
        try { json = JSON.parse(data); } catch (e) { /* binary or html */ }
        resolve({ status: res.statusCode, json, raw: data });
      });
    });
    req.on('error', reject);
    if (payload) req.write(payload);
    req.end();
  });
}

async function login(email) {
  const r = await request('POST', '/api/auth/dev-login', { body: { email, name: 'T' } });
  assert.equal(r.status, 200);
  assert.ok(r.json.token.includes('.'), 'token should be signed (payload.sig)');
  return r.json.token;
}

before(async () => {
  tmpData = fs.mkdtempSync(path.join(os.tmpdir(), 'algoarch-test-'));
  for (const f of fs.readdirSync(path.join(ROOT, 'data'))) {
    const src = path.join(ROOT, 'data', f);
    if (fs.statSync(src).isFile()) fs.copyFileSync(src, path.join(tmpData, f));
    else fs.cpSync(src, path.join(tmpData, f), { recursive: true });
  }
  const env = { ...process.env, PORT: String(PORT), ALGOARCH_DATA_DIR: tmpData, AUTH_SECRET: 'test-secret', GEMINI_API_KEY: '' };
  delete env.RAZORPAY_KEY_ID; delete env.RAZORPAY_KEY_SECRET; delete env.ADMIN_KEY; delete env.NODE_ENV;
  for (const k of ['GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GITHUB_CLIENT_ID', 'GITHUB_CLIENT_SECRET', 'PUBLIC_URL']) delete env[k]; // keep the run hermetic
  child = spawn(process.execPath, ['server.js'], { cwd: ROOT, env, stdio: 'ignore' });
  for (let i = 0; i < 50; i++) {
    try { const r = await request('GET', '/api/auth/providers', { token: false }); if (r.status === 200) break; } catch (e) { /* not up yet */ }
    if (i === 49) throw new Error('server did not start');
    await new Promise(r => setTimeout(r, 100));
  }
  defaultToken = await login('default-tester@example.com');
});

after(async () => {
  // wait for the server to exit before deleting its database (Windows holds the file open briefly)
  if (child && child.exitCode === null && child.signalCode === null) await new Promise((r) => { child.once('exit', r); child.kill(); });
  if (tmpData) fs.rmSync(tmpData, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
});

test('forged or tampered tokens are rejected, never mapped to another user', async () => {
  const token = await login('victim@example.com');
  const [payload, sig] = token.split('.');
  const forged = Buffer.from(JSON.stringify({ u: 'u_victim_example_com', exp: Date.now() + 1e9 })).toString('base64url') + '.' + sig;
  assert.equal((await request('GET', '/api/auth/me', { token: forged })).status, 401);
  assert.equal((await request('GET', '/api/auth/me', { token: 'u_victim_example_com' })).status, 401);
  const real = await request('GET', '/api/auth/me', { token });
  assert.equal(real.json.user.id, 'u_victim_example_com');
  assert.equal(real.json.user.isAdmin, false);
  assert.ok(payload);
});

test('every API except /api/auth/* requires a sign-in', async () => {
  for (const p of ['/api/curriculum', '/api/videos', '/api/lessons/ds00', '/api/subscription/plans', '/api/progress', '/api/stats', '/api/auth/me']) {
    const r = await request('GET', p, { token: false });
    assert.equal(r.status, 401, p + ' should need a sign-in');
    assert.equal(r.json.loginRequired, true);
  }
  assert.equal((await request('POST', '/api/chat/stream', { token: false, body: { question: 'hi' } })).status, 401);
  assert.equal((await request('GET', '/api/curriculum', { token: await login('gate@example.com') })).status, 200);
});

test('client-supplied userId / x-algoarch-user headers are ignored', async () => {
  const token = await login('real@example.com');
  await login('other@example.com');
  const r = await request('GET', '/api/subscription/status?userId=u_other_example_com', {
    token, headers: { 'x-algoarch-user': 'u_other_example_com' }
  });
  assert.equal(r.json.userId, 'u_real_example_com');
});

test('the old trust-the-client login endpoint is gone', async () => {
  const r = await request('POST', '/api/auth/login', { body: { provider: 'google', email: 'a@b.co' } });
  assert.ok(!(r.json && r.json.token), 'no token can be minted from client-supplied identity');
});

test('anyone can sign in with the same email only as that one account (case-insensitive)', async () => {
  const a = await request('POST', '/api/auth/dev-login', { body: { email: 'Same@Example.com' } });
  const b = await request('POST', '/api/auth/dev-login', { body: { email: 'same@example.com' } });
  assert.equal(a.json.user.id, b.json.user.id);
  const bad = await request('POST', '/api/auth/dev-login', { body: { email: 'not-an-email' } });
  assert.equal(bad.status, 400);
});

test('upgrade honours the requested plan (planId bug regression) in demo mode', async () => {
  const token = await login('buyer@example.com');
  const r = await request('POST', '/api/subscription/upgrade', { token, body: { planId: 'enterprise' } });
  assert.equal(r.status, 200);
  assert.equal(r.json.user.plan, 'enterprise');
  const bad = await request('POST', '/api/subscription/upgrade', { token, body: { plan: 'platinum' } });
  assert.equal(bad.status, 400);
});

test('entitlements follow the plan', async () => {
  const free = await login('free@example.com');
  const s1 = await request('GET', '/api/subscription/status', { token: free });
  assert.equal(s1.json.entitlements.monacoRun, false);
  assert.equal(s1.json.entitlements.labZip, false);
  await request('POST', '/api/subscription/upgrade', { token: free, body: { plan: 'pro' } });
  const s2 = await request('GET', '/api/subscription/status', { token: free });
  assert.equal(s2.json.entitlements.monacoRun, true);
  assert.equal(s2.json.entitlements.rubric, false);
  assert.equal(s2.json.entitlements.labZip, false);
});

test('lab zip download is gated to enterprise', async () => {
  const token = await login('zip@example.com');
  const denied = await request('GET', '/api/download/all-labs.zip', { token });
  assert.equal(denied.status, 402);
  await request('POST', '/api/subscription/upgrade', { token, body: { plan: 'enterprise' } });
  const ok = await request('GET', '/api/download/all-labs.zip', { token });
  assert.equal(ok.status, 200);
});

test('single lab download is gated to pro+', async () => {
  const token = await login('lab@example.com');
  const denied = await request('GET', '/api/download/lab?file=x.py', { token });
  assert.equal(denied.status, 402);
});

test('payment verification rejects unknown orders and bad signatures', async () => {
  const token = await login('pay@example.com');
  const r = await request('POST', '/api/payments/verify', {
    token, body: { razorpay_order_id: 'order_x', razorpay_payment_id: 'pay_x', razorpay_signature: 'sig' }
  });
  assert.equal(r.status, 400);
  const o = await request('POST', '/api/payments/create-order', { token, body: { plan: 'pro' } });
  assert.equal(o.status, 400); // gateway not configured in test env
});

test('chat quota still enforced on the free plan', async () => {
  const token = await login('quota@example.com');
  let exhausted = false;
  for (let i = 0; i < 7; i++) {
    const r = await request('POST', '/api/chat/stream', { token, body: { question: 'what is a heap?' } });
    if (r.json && r.json.exhausted) { exhausted = true; break; }
  }
  assert.ok(exhausted, 'free plan should hit its 5/day limit');
});

test('admin APIs need an admin email: anonymous 401, regular user 403, seeded admin 200', async () => {
  assert.equal((await request('GET', '/api/admin/lessons', { token: false })).status, 401);
  const user = await login('regular@example.com');
  assert.equal((await request('GET', '/api/admin/lessons', { token: user })).status, 403);
  assert.equal((await request('POST', '/api/reminders/trigger-cron', { token: user })).status, 403);
  const admin = await login('YashJi2117@gmail.com');
  assert.equal((await request('GET', '/api/admin/lessons', { token: admin })).status, 200);
  assert.equal((await request('GET', '/api/auth/me', { token: admin })).json.user.isAdmin, true);
});

test('admin emails table: seeded, manageable, and the last admin cannot be removed', async () => {
  const admin = await login('yashji2117@gmail.com');
  const list = await request('GET', '/api/admin/admins', { token: admin });
  assert.deepEqual(list.json.admins.map(a => a.email), ['yashji2117@gmail.com']);
  const added = await request('POST', '/api/admin/admins', { token: admin, body: { email: 'Second@Example.com' } });
  assert.deepEqual(added.json.admins.map(a => a.email).sort(), ['second@example.com', 'yashji2117@gmail.com']);
  const second = await login('second@example.com');
  assert.equal((await request('GET', '/api/admin/lessons', { token: second })).status, 200);
  assert.equal((await request('POST', '/api/admin/admins', { token: admin, body: { email: 'nope' } })).status, 400);
  await request('POST', '/api/admin/admins/remove', { token: admin, body: { email: 'second@example.com' } });
  assert.equal((await request('GET', '/api/admin/lessons', { token: second })).status, 403);
  const last = await request('POST', '/api/admin/admins/remove', { token: admin, body: { email: 'yashji2117@gmail.com' } });
  assert.equal(last.status, 400);
});

test('lesson API serves structured data from the database, with no markup or scripts', async () => {
  const r = await request('GET', '/api/lessons/ds00');
  assert.equal(r.status, 200);
  assert.equal(r.json.lesson.id, 'ds00');
  assert.ok(r.json.document.sections.length >= 5, 'document has sections');
  assert.ok(!/<script|<div|class=/i.test(JSON.stringify(r.json.document)), 'document contains data only');
  const md = await request('GET', '/api/lessons/ds24');
  assert.equal(md.status, 200);
  assert.ok(md.json.guide.length > 500, 'markdown guide stored in DB');
  assert.equal(md.json.next.id, 'ds25');
});

test('curriculum comes from the database and unknown lessons 404', async () => {
  const c = await request('GET', '/api/curriculum');
  assert.equal(c.json.tracks.length, 4);
  assert.ok(c.json.tracks.every(t => t.blocks.length > 0));
  const nf = await request('GET', '/api/lessons/nope');
  assert.equal(nf.status, 404);
  const gone = await request('GET', '/projects/dsa-faang-prep/visuals/00-recognition-engine.html');
  assert.ok(!/ALGOARCH — Engineering Curriculum|rail-title/.test(gone.raw.slice(0, 5000)) || gone.status !== 200 || !gone.raw.includes('class="rail"'), 'raw lesson HTML is no longer served');
});

test('no content is lost in the import (every video and lesson present)', async () => {
  const src = require('../data/videos.json');
  const r = await request('GET', '/api/videos');
  assert.equal(r.json.length, src.length, 'all videos imported even when ids repeat');
  const cur = require('../data/curriculum.json');
  const expected = cur.tracks.reduce((n, t) => n + t.blocks.reduce((m, b) => m + b.lessons.length, 0), 0);
  const c = await request('GET', '/api/curriculum');
  const got = c.json.tracks.reduce((n, t) => n + t.totalLessons, 0);
  assert.equal(got, expected);
});

test('python code cells keep their source and tests; the quiz keeps its question bank', async () => {
  const cells = [];
  const collect = (bs) => { for (const b of bs || []) { if (b.type === 'code_cell') cells.push(b); collect(b.blocks); } };
  const lesson = await request('GET', '/api/lessons/ds02');
  lesson.json.document.sections.forEach(s => collect(s.blocks));
  assert.ok(cells.length >= 4, 'ds02 has code cells');
  assert.ok(cells.every(c => c.starter.length > 10), 'no empty starter code');
  assert.ok(cells.some(c => c.tests && c.tests.includes('assert')), 'tests are stored');

  const ds00 = await request('GET', '/api/lessons/ds00');
  let quiz = null;
  const find = (bs) => { for (const b of bs || []) { if (b.type === 'widget' && b.kind === 'quiz') quiz = b; find(b.blocks); } };
  ds00.json.document.sections.forEach(s => find(s.blocks));
  assert.equal(quiz.ported, true);
  assert.equal(quiz.data.bank.length, 36);
  assert.ok(quiz.data.bank.every(q => q.answer && q.statement.length && q.why.length));
  assert.ok(quiz.data.core.length < quiz.data.patterns.length);
});

test('ported widgets carry their data: traces, checklists and the scorecard', async () => {
  const widgets = (doc) => { const out = []; const w = (bs) => { for (const b of bs || []) { if (b.type === 'widget') out.push(b); w(b.blocks); } }; doc.sections.forEach(s => w(s.blocks)); return out; };

  const ds03 = widgets((await request('GET', '/api/lessons/ds03')).json.document);
  const traces = ds03.filter(b => b.kind === 'trace');
  assert.equal(traces.length, 2);
  assert.ok(traces.every(t => t.ported && t.data.values.length > 0 && t.data.frames.length > 1));
  assert.ok(traces[0].data.frames.every(f => typeof f.note === 'string' && Array.isArray(f.stat)));

  const sy21 = widgets((await request('GET', '/api/lessons/sy21')).json.document).find(b => b.kind === 'checklist');
  assert.equal(sy21.data.items.length, 16);
  assert.equal(sy21.data.max, 20);
  assert.deepEqual(sy21.data.bands.map(b => b.label), ['strong hire', 'hire', 'borderline', 're-attempt']);
  assert.equal(sy21.data.verdicts.length, 3);
  assert.ok(JSON.stringify(sy21.data.verdicts[0].content).includes('{score}'), 'verdict keeps its placeholders');
  assert.equal(sy21.data.deductions.length, 3);

  const ds18 = widgets((await request('GET', '/api/lessons/ds18')).json.document).find(b => b.kind === 'scorecard');
  assert.equal(ds18.data.axes.length, 7);
  assert.equal(ds18.data.target, 21);
  assert.deepEqual(ds18.data.criticalAxes, [4, 5]);
});

test('diagram admin API: admins can add one, it shows up in the lesson, others get 403', async () => {
  const scene = { v: 1, width: 300, height: 200, elements: [{ id: 'a', k: 'box', x: 20, y: 20, w: 120, h: 60, label: 'Hello', tone: 'cool', fill: true }] };
  const user = await login('diagram-user@example.com');
  const denied = await request('POST', '/api/admin/diagrams', { token: user, body: { lessonId: 'sy02', sectionAnchor: 's4', scene } });
  assert.equal(denied.status, 403);
  const admin = await login('yashji2117@gmail.com');
  const bad = await request('POST', '/api/admin/diagrams', { token: admin, body: { lessonId: 'sy02', sectionAnchor: 's4', scene: { v: 1, width: 5, height: 5, elements: [{ id: 'x', k: 'iframe', x: 0, y: 0 }] } } });
  assert.equal(bad.status, 400);
  const ok = await request('POST', '/api/admin/diagrams', { token: admin, body: { slug: 'test-dg', lessonId: 'sy02', sectionAnchor: 's4', afterBlock: 0, title: 'Test diagram', scene } });
  assert.equal(ok.status, 200);
  const lesson = await request('GET', '/api/lessons/sy02', { token: user });
  const s4 = lesson.json.document.sections.find(s => s.anchor === 's4');
  assert.equal(s4.blocks[1].type, 'diagram');
  assert.equal(s4.blocks[1].title, 'Test diagram');
  await request('POST', '/api/admin/diagrams/delete', { token: admin, body: { id: ok.json.id } });
});
