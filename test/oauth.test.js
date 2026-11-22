// OAuth flow against a mock Google/GitHub: state + cookie binding, verified emails only,
// admin by email, and no dev-login once a provider is configured.
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');

const ROOT = path.join(__dirname, '..');
const PORT = 6100 + Math.floor(Math.random() * 300);
const MOCK_PORT = PORT + 400;
let child, mock, tmpData;
// what the mock provider will say about "the person who just approved"
let identity = { email: 'someone@example.com', verified: true };

function call(method, p, { headers = {}, token } = {}) {
  return new Promise((resolve, reject) => {
    const h = { ...headers };
    if (token) h.Authorization = 'Bearer ' + token;
    const req = http.request({ host: '127.0.0.1', port: PORT, path: p, method, headers: h }, res => {
      let d = ''; res.on('data', c => d += c);
      res.on('end', () => { let json = null; try { json = JSON.parse(d); } catch (e) { /* html */ } resolve({ status: res.statusCode, headers: res.headers, raw: d, json }); });
    });
    req.on('error', reject); req.end();
  });
}

before(async () => {
  mock = http.createServer((req, res) => {
    let body = ''; req.on('data', c => body += c);
    req.on('end', () => {
      const json = (o) => { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(o)); };
      if (req.url.endsWith('/token')) return json({ access_token: 'tok' });
      if (req.url === '/google/user') return json({ email: identity.email, email_verified: identity.verified, name: 'G User', picture: 'http://x/y.png' });
      if (req.url === '/github/user') return json({ login: 'ghuser', name: 'GH User', avatar_url: 'http://x/z.png' });
      if (req.url === '/github/emails') return json([{ email: 'noise@example.com', primary: false, verified: false }, { email: identity.email, primary: true, verified: identity.verified }]);
      res.writeHead(404); res.end();
    });
  });
  await new Promise(r => mock.listen(MOCK_PORT, '127.0.0.1', r));
  tmpData = fs.mkdtempSync(path.join(os.tmpdir(), 'algoarch-oauth-'));
  for (const f of fs.readdirSync(path.join(ROOT, 'data'))) {
    const src = path.join(ROOT, 'data', f);
    if (fs.statSync(src).isFile()) fs.copyFileSync(src, path.join(tmpData, f));
    else fs.cpSync(src, path.join(tmpData, f), { recursive: true });
  }
  const env = {
    ...process.env, PORT: String(PORT), ALGOARCH_DATA_DIR: tmpData, AUTH_SECRET: 'oauth-test',
    GOOGLE_CLIENT_ID: 'gid', GOOGLE_CLIENT_SECRET: 'gsecret', GITHUB_CLIENT_ID: 'hid', GITHUB_CLIENT_SECRET: 'hsecret',
    OAUTH_TEST_BASE: `http://127.0.0.1:${MOCK_PORT}`, GEMINI_API_KEY: ''
  };
  delete env.NODE_ENV; delete env.ADMIN_KEY;
  child = spawn(process.execPath, ['server.js'], { cwd: ROOT, env, stdio: 'ignore' });
  for (let i = 0; i < 50; i++) {
    try { if ((await call('GET', '/api/auth/providers')).status === 200) return; } catch (e) { /* starting */ }
    await new Promise(r => setTimeout(r, 100));
  }
  throw new Error('server did not start');
});

after(() => {
  child && child.kill();
  mock && mock.close();
  tmpData && fs.rmSync(tmpData, { recursive: true, force: true });
});

// Walk start -> (provider approves) -> callback, returning the callback response.
async function signIn(provider, { cookie, state } = {}) {
  const start = await call('GET', `/api/auth/${provider}/start`);
  assert.equal(start.status, 302);
  const loc = new URL(start.headers.location);
  assert.equal(loc.searchParams.get('client_id'), provider === 'google' ? 'gid' : 'hid');
  assert.ok(loc.searchParams.get('redirect_uri').endsWith(`/api/auth/${provider}/callback`));
  const realState = loc.searchParams.get('state');
  const realCookie = /aa_oauth=([^;]+)/.exec(start.headers['set-cookie'][0])[1];
  assert.match(start.headers['set-cookie'][0], /HttpOnly/);
  return call('GET', `/api/auth/${provider}/callback?code=abc&state=${encodeURIComponent(state ?? realState)}`, {
    headers: { Cookie: 'aa_oauth=' + (cookie ?? realCookie) }
  });
}
const tokenOf = (r) => /#auth=(.+)$/.exec(r.headers.location)[1];

test('providers endpoint reports configured providers and no dev login', async () => {
  const p = await call('GET', '/api/auth/providers');
  assert.deepEqual(p.json, { google: true, github: true, dev: false });
  const dev = await call('POST', '/api/auth/dev-login');
  assert.equal(dev.status, 404);
});

test('google sign-in issues a session for the verified email', async () => {
  identity = { email: 'Person@Example.com', verified: true };
  const cb = await signIn('google');
  assert.equal(cb.status, 302);
  const me = await call('GET', '/api/auth/me', { token: tokenOf(cb) });
  assert.equal(me.json.user.email, 'person@example.com');
  assert.equal(me.json.user.isAdmin, false);
});

test('github sign-in uses the primary verified email and links to the same account', async () => {
  identity = { email: 'person@example.com', verified: true };
  const cb = await signIn('github');
  const me = await call('GET', '/api/auth/me', { token: tokenOf(cb) });
  assert.equal(me.json.user.id, 'u_person_example_com');
});

test('unverified emails are refused', async () => {
  identity = { email: 'unverified@example.com', verified: false };
  for (const p of ['google', 'github']) {
    const cb = await signIn(p);
    assert.match(cb.headers.location, /^\/\?auth_error=/);
    assert.ok(!cb.headers.location.includes('#auth='));
  }
});

test('callback fails without the matching cookie or with a tampered/foreign state', async () => {
  identity = { email: 'attacker@example.com', verified: true };
  assert.match((await signIn('google', { cookie: 'wrong' })).headers.location, /^\/\?auth_error=/);
  assert.match((await signIn('google', { state: 'forged.state' })).headers.location, /^\/\?auth_error=/);
  const noCookie = await call('GET', '/api/auth/google/callback?code=abc&state=x');
  assert.match(noCookie.headers.location, /^\/\?auth_error=/);
  const denied = await call('GET', '/api/auth/google/callback?error=access_denied');
  assert.match(denied.headers.location, /^\/\?auth_error=/);
});

test('the seeded admin email is an admin through a real sign-in', async () => {
  identity = { email: 'yashji2117@gmail.com', verified: true };
  const token = tokenOf(await signIn('google'));
  assert.equal((await call('GET', '/api/auth/me', { token })).json.user.isAdmin, true);
  assert.equal((await call('GET', '/api/admin/lessons', { token })).status, 200);
});
