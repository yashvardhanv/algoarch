// Streaming mentor: runs the real server against a local mock Gemini that behaves like the
// real API (CRLF frames, frames split across TCP chunks, thinking parts, length cut-off).
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');

const ROOT = path.join(__dirname, '..');
const PORT = 5900 + Math.floor(Math.random() * 90);
const MOCK_PORT = PORT + 100;
let child, mock, tmpData;
let lastBody = null;

function frame(obj) { return 'data: ' + JSON.stringify(obj) + '\r\n\r\n'; }

before(async () => {
  mock = http.createServer((req, res) => {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      lastBody = JSON.parse(body);
      res.writeHead(200, { 'Content-Type': 'text/event-stream' });
      const f1 = frame({ candidates: [{ content: { parts: [{ text: 'Hindi text needs ' }] } }] });
      // split the second frame in the middle of the JSON line
      const f2 = frame({ candidates: [{ content: { parts: [{ text: 'hidden reasoning', thought: true }] } }] });
      const f3 = frame({ candidates: [{ content: { parts: [{ text: 'more tokens per word.' }] }, finishReason: 'MAX_TOKENS' }] });
      res.write(f1);
      res.write(f2.slice(0, 20));
      setTimeout(() => { res.write(f2.slice(20)); res.write(f3.slice(0, 30)); setTimeout(() => { res.end(f3.slice(30)); }, 20); }, 20);
    });
  });
  await new Promise(r => mock.listen(MOCK_PORT, '127.0.0.1', r));

  tmpData = fs.mkdtempSync(path.join(os.tmpdir(), 'algoarch-gem-'));
  for (const f of fs.readdirSync(path.join(ROOT, 'data'))) {
    const src = path.join(ROOT, 'data', f);
    if (fs.statSync(src).isFile()) fs.copyFileSync(src, path.join(tmpData, f));
    else fs.cpSync(src, path.join(tmpData, f), { recursive: true });
  }
  const env = { ...process.env, PORT: String(PORT), ALGOARCH_DATA_DIR: tmpData, AUTH_SECRET: 't', GEMINI_API_KEY: 'test-key', GEMINI_BASE_URL: `http://127.0.0.1:${MOCK_PORT}` };
  child = spawn(process.execPath, ['server.js'], { cwd: ROOT, env, stdio: 'ignore' });
  for (let i = 0; i < 50; i++) {
    try { await get('/api/auth/providers'); break; } catch (e) { await new Promise(r => setTimeout(r, 100)); }
    if (i === 49) throw new Error('server did not start');
  }
  token = JSON.parse((await post('/api/auth/dev-login', { email: 'mentor-test@example.com' }, false)).raw).token;
});

after(() => {
  child && child.kill();
  mock && mock.close();
  tmpData && fs.rmSync(tmpData, { recursive: true, force: true });
});

function get(p) {
  return new Promise((resolve, reject) => {
    http.get({ host: '127.0.0.1', port: PORT, path: p, headers: token ? { Authorization: 'Bearer ' + token } : {} }, res => { let d = ''; res.on('data', c => d += c); res.on('end', () => resolve(d)); }).on('error', reject);
  });
}

let token = null;
function post(p, body, auth = true) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify(body);
    const req = http.request({ host: '127.0.0.1', port: PORT, path: p, method: 'POST', headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload), ...(auth && token ? { Authorization: 'Bearer ' + token } : {}) } }, res => {
      let d = ''; res.on('data', c => d += c); res.on('end', () => resolve({ status: res.statusCode, raw: d }));
    });
    req.on('error', reject); req.write(payload); req.end();
  });
}

const events = (raw) => raw.split('\n\n').map(s => s.trim()).filter(s => s.startsWith('data:')).map(s => JSON.parse(s.slice(5)));

test('stream delivers the complete visible answer and reports the cut-off', async () => {
  const r = await post('/api/chat/stream', { question: 'why do hindi tokens cost more', lessonTitle: 'Tokens', trackId: 'ai-engineering' });
  assert.equal(r.status, 200);
  const ev = events(r.raw);
  const text = ev.filter(e => e.type === 'chunk').map(e => e.text).join('');
  assert.equal(text, 'Hindi text needs more tokens per word.', 'thinking text excluded, no pieces lost');
  const done = ev.find(e => e.type === 'done');
  assert.equal(done.finishReason, 'MAX_TOKENS');
  assert.ok(!ev.some(e => e.type === 'error'));
});

test('request uses systemInstruction and a generous output cap', async () => {
  assert.ok(lastBody.systemInstruction.parts[0].text.includes('technical mentor inside AlgoArch'));
  assert.equal(lastBody.contents[0].parts[0].text, 'why do hindi tokens cost more');
  assert.ok(lastBody.generationConfig.maxOutputTokens >= 4096);
});

test('related lessons ignore filler words and weak matches', async () => {
  const r = await post('/api/chat/stream', { question: 'why is raft more complicated', lessonTitle: 'x' });
  const done = events(r.raw).find(e => e.type === 'done');
  assert.ok(done.related.every(l => l.id && l.title));
  const unrelated = await post('/api/chat/stream', { question: 'why how what more less' });
  assert.equal(events(unrelated.raw).find(e => e.type === 'done').related.length, 0);
});

test('mentor is grounded in the open lesson and does not redirect when it covers the question', async () => {
  const r = await post('/api/chat/stream', { question: 'what is cyclic sort', lessonId: 'ds24', lessonTitle: 'ignored by server' });
  const prompt = lastBody.contents[0].parts[0].text;
  assert.ok(prompt.includes('<lesson>') && prompt.includes('</lesson>'), 'lesson text is sent');
  assert.ok(prompt.length > 3000, 'the full lesson, not just the title, is sent');
  assert.ok(/cyclic sort/i.test(prompt));
  assert.ok(lastBody.systemInstruction.parts[0].text.includes('Answer from the lesson first'));
  assert.ok(lastBody.systemInstruction.parts[0].text.includes('Cyclic Sort'), 'title comes from the database');
  const done = events(r.raw).find(e => e.type === 'done');
  assert.deepEqual(done.related, [], 'no other lessons suggested when the open lesson covers it');
});

test('structured lesson documents are flattened with section titles for the model', async () => {
  await post('/api/chat/stream', { question: 'what does the timed drill train', lessonId: 'ds00' });
  const prompt = lastBody.contents[0].parts[0].text;
  assert.ok(prompt.includes('Section 02: The timed drill') || prompt.includes('The timed drill'), 'section titles present');
  assert.ok(/recognition/i.test(prompt));
});

test('without an open lesson the mentor answers generally', async () => {
  // fresh account: the free plan's daily mentor quota is per user
  token = JSON.parse((await post('/api/auth/dev-login', { email: 'general-test@example.com' }, false)).raw).token;
  await post('/api/chat/stream', { question: 'what is a heap' });
  assert.ok(!lastBody.contents[0].parts[0].text.includes('<lesson>'));
  assert.ok(!lastBody.systemInstruction.parts[0].text.includes('Answer from the lesson first'));
});
