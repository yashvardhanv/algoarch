// ============================================================================
// ALGOARCH — 50LPA FAANG Career Guidance & Learning Platform Server
// Pure Node.js (Zero external dependencies for instant zero-friction boot)
// ============================================================================

const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');
const cmsAuth = require('./server_cms_auth');
const litellm = require('./litellm_tracker');
const { openDb, createRepo } = require('./db');
const oauth = require('./oauth');

const PORT = process.env.PORT || 5050;
const DATA_DIR = process.env.ALGOARCH_DATA_DIR || path.join(__dirname, 'data');
const PUBLIC_DIR = path.join(__dirname, 'public');
const PROGRESS_FILE = path.join(DATA_DIR, 'progress.json');
const ZIP_LABS_FILE = path.join(DATA_DIR, 'all_labs_source.zip');

// Content lives in SQLite; the API returns data and the frontend renders it.
const db = openDb(DATA_DIR);
const repo = createRepo(db);
if (db.prepare('SELECT COUNT(*) AS n FROM lessons').get().n === 0) {
  console.warn('[Content] Database is empty. Run: npm run db:import');
}

// Ensure data directory and progress file exist
if (!fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}
if (!fs.existsSync(PROGRESS_FILE)) {
  fs.writeFileSync(PROGRESS_FILE, JSON.stringify({ completed: [], bookmarked: [], notes: {} }, null, 2));
}

// MIME types
const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.md': 'text/markdown; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.py': 'text/x-python; charset=utf-8',
  '.zip': 'application/zip',
  '.wasm': 'application/wasm'
};

// Identity comes ONLY from a signed bearer token for an account that exists. There is no
// anonymous or shared guest account: every /api route except /api/auth/* needs a sign-in.
function getReqUserId(req) {
  const m = /^Bearer\s+(.+)$/i.exec(req.headers['authorization'] || '');
  const id = m ? cmsAuth.verifyToken(m[1].trim()) : null;
  return id && cmsAuth.userExists(id) ? id : null;
}

// Admin = a signed-in user whose verified email is in the admin_emails table,
// or (for automation) a caller presenting the configured ADMIN_KEY.
function isAdminRequest(req) {
  const key = process.env.ADMIN_KEY;
  if (key && cmsAuth.safeEqual(req.headers['x-admin-key'] || '', key)) return true;
  const id = getReqUserId(req);
  const user = id ? cmsAuth.getUser(id) : null;
  return !!(user && repo.isAdminEmail(user.email));
}

const isLoopback = (req) => ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(req.socket.remoteAddress || '');
// Local development only: no OAuth app configured, not production, and a loopback caller.
function devLoginAllowed(req) {
  const c = oauth.configured();
  return process.env.NODE_ENV !== 'production' && !c.google && !c.github && isLoopback(req);
}
function readCookie(req, name) {
  const m = (req.headers.cookie || '').split(/;\s*/).map(p => p.split('=')).find(p => p[0] === name);
  return m ? decodeURIComponent(m.slice(1).join('=')) : null;
}
function redirect(res, location, extraHeaders = {}) {
  res.writeHead(302, { Location: location, 'Cache-Control': 'no-store', ...extraHeaders });
  res.end();
}

// Mentor prompt. The open lesson's full text is supplied separately and is the primary source.
function buildMentorPrompt(body, hasLesson) {
  const clean = (v, n) => String(v || '').replace(/[\u0000-\u001f"]/g, ' ').slice(0, n);
  const lessonTitle = clean(body.lessonTitle, 120);
  const rules = hasLesson
    ? `The learner is reading the lesson "${lessonTitle}". Its full text is inside <lesson> tags in the user message.

Rules:
1. Answer from the lesson first. If it covers the question, answer with its content and name the section where it appears (for example: In section 3, "The decision tree"). Do not send the learner to other lessons when this one has the answer.
2. If the lesson covers only part of the question, say what it covers, then add the rest briefly under the label "Beyond this lesson:".
3. If the lesson does not cover the question, say so in one sentence, then answer from general knowledge. Only in that case may you mention another topic worth reading.
4. Lead with the direct answer in one to three sentences, then give supporting detail. Include complexity bounds and failure modes when they matter. Give code only when asked or essential.`
    : `Answer the question directly: lead with the answer in one to three sentences, then supporting detail, complexity bounds and failure modes where they matter. Give code only when asked or essential.`;
  return `You are the technical mentor inside AlgoArch, preparing senior engineers for FAANG-level interviews.
${rules}`;
}

// Wraps the question with the open lesson's text, when there is one.
function groundQuestion(question, lessonText) {
  return lessonText ? `<lesson>\n${lessonText}\n</lesson>\n\nQuestion: ${question}` : question;
}

// True when most meaningful question terms appear in the lesson text.
function lessonCovers(question, lessonText) {
  if (!lessonText) return false;
  const terms = cmsAuth.queryTerms(question);
  if (terms.length === 0) return true;
  const hay = lessonText.toLowerCase();
  return terms.filter(t => hay.includes(t)).length / terms.length >= 0.5;
}

// Helper: send JSON response
function sendJson(res, statusCode, data) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization, x-admin-key'
  });
  res.end(JSON.stringify(data));
}

// Helper: parse POST body
function parseBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => {
      body += chunk.toString();
      if (body.length > 2 * 1024 * 1024) { // 2MB limit
        reject(new Error('Payload too large'));
      }
    });
    req.on('end', () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (e) {
        resolve({});
      }
    });
    req.on('error', reject);
  });
}

// Clean markdown text: strip internal git repo references, broken relative URLs, and diagnostics
function sanitizeMarkdownContent(rawMarkdown) {
  if (!rawMarkdown) return '';

  return rawMarkdown
    // Remove lines like: > **Prereq:** ... > **Visual:** ... > **Repairs:** ...
    .replace(/^>\s*\*\*Prereq:\*\*.*$/gim, '')
    .replace(/^>\s*\*\*Visual:\*\*.*$/gim, '')
    .replace(/^>\s*\*\*Repairs:\*\*.*$/gim, '')
    .replace(/^>\s*\*\*Standing companion:\*\*.*$/gim, '')
    // Remove any remaining raw relative links to visuals/ or ../visuals/
    .replace(/\[([^\]]+)\]\(\.\.\/visuals\/[^)]+\)/gi, '$1')
    .replace(/\[([^\]]+)\]\(visuals\/[^)]+\)/gi, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\.md\)/gi, '$1')
    // Remove consecutive empty blockquotes
    .replace(/^>\s*\n/gm, '')
    // Clean up excessive blank lines
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function extractDrills(markdown) {
  const items = [];
  const m = (markdown || '').match(/##\s+(?:(?:\d+\.\s*)?(?:Drills|Homework|Mock Drills|Practice Exercises)[\s\S]*)/i);
  if (!m) return items;
  let cur = null;
  for (const line of m[0].split('\n')) {
    const li = line.match(/^(\d+\.|\*|-)\s+(.*)/);
    if (li) { if (cur) items.push(cur); cur = { title: li[2].trim(), notes: '' }; }
    else if (cur && line.trim()) cur.notes += (cur.notes ? ' ' : '') + line.trim();
  }
  if (cur) items.push(cur);
  return items.slice(0, 10);
}

// Create HTTP server
const server = http.createServer(async (req, res) => {
  const parsedUrl = url.parse(req.url, true);
  const pathname = parsedUrl.pathname;

  if (pathname.startsWith('/api/') && req.method !== 'OPTIONS' && !pathname.startsWith('/api/auth/')) {
    const adminOnly = pathname.startsWith('/api/admin/') || pathname === '/api/reminders/trigger-cron' || pathname === '/api/reminders/logs';
    if (adminOnly) {
      if (!isAdminRequest(req)) {
        return getReqUserId(req)
          ? sendJson(res, 403, { error: 'Admin access required' })
          : sendJson(res, 401, { error: 'Sign in required', loginRequired: true });
      }
    } else if (!getReqUserId(req)) {
      return sendJson(res, 401, { error: 'Sign in required', loginRequired: true });
    }
  }

  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization, x-admin-key'
    });
    res.end();
    return;
  }

  // --------------------------------------------------------------------------
  // API Endpoints
  // --------------------------------------------------------------------------

  // 1. GET /api/curriculum
  if (req.method === 'GET' && pathname === '/api/curriculum') {
    return sendJson(res, 200, repo.getCurriculum());
  }

  // GET /api/pathways
  if (req.method === 'GET' && pathname === '/api/pathways') {
    return sendJson(res, 200, { pathways: repo.getPathways() });
  }

  // 2. GET /api/videos
  if (req.method === 'GET' && pathname === '/api/videos') {
    return sendJson(res, 200, repo.getVideos());
  }

  // 3. GET /api/lessons/:id  (content as data; the frontend owns presentation)
  const lessonMatch = pathname.match(/^\/api\/lessons\/([A-Za-z0-9_-]+)$/);
  if (req.method === 'GET' && lessonMatch) {
    const payload = repo.getLesson(lessonMatch[1]);
    if (!payload) return sendJson(res, 404, { error: 'Lesson not found' });
    payload.drills = extractDrills(payload.guide);
    return sendJson(res, 200, payload);
  }

  // 4. GET /api/download/all-labs.zip
  if (req.method === 'GET' && pathname === '/api/download/all-labs.zip') {
    if (!cmsAuth.userHasFeature(getReqUserId(req), 'labZip')) {
      return sendJson(res, 402, { error: 'Offline Lab Package requires the Staff / Enterprise plan', upgradeRequired: true, requiredPlan: 'enterprise' });
    }
    if (fs.existsSync(ZIP_LABS_FILE)) {
      res.writeHead(200, {
        'Content-Type': 'application/zip',
        'Content-Disposition': 'attachment; filename="50LPA_FAANG_Labs_Source.zip"',
        'Content-Length': fs.statSync(ZIP_LABS_FILE).size
      });
      fs.createReadStream(ZIP_LABS_FILE).pipe(res);
      return;
    }
    return sendJson(res, 404, { error: 'Archive not found' });
  }

  // 5. GET /api/download/lab?lesson=ID
  if (req.method === 'GET' && pathname === '/api/download/lab') {
    if (!cmsAuth.userHasFeature(getReqUserId(req), 'labDownload')) {
      return sendJson(res, 402, { error: 'Lab downloads require the Pro plan or higher', upgradeRequired: true, requiredPlan: 'pro' });
    }
    const payload = parsedUrl.query.lesson ? repo.getLesson(String(parsedUrl.query.lesson)) : null;
    if (!payload || !payload.lab) return sendJson(res, 404, { error: 'Lab not found' });
    res.writeHead(200, {
      'Content-Type': 'text/plain; charset=utf-8',
      'Content-Disposition': 'attachment; filename="' + payload.lab.fileName.replace(/[^A-Za-z0-9._-]/g, '_') + '"'
    });
    return res.end(payload.lab.code);
  }

    // 5b. POST /api/chat/stream (SSE token streaming; same quota gate as /api/chat)
  if (req.method === 'POST' && pathname === '/api/chat/stream') {
    let streamStarted = false;
    const sse = (obj) => res.write('data: ' + JSON.stringify(obj) + '\n\n');
    try {
      const body = await parseBody(req);
      const question = String(body.question || body.message || '').slice(0, 4000);
      const lessonId = String(body.lessonId || '').slice(0, 40);
      const userId = getReqUserId(req);
      if (!question.trim()) return sendJson(res, 400, { error: 'Question cannot be empty' });

      const quotaCheck = cmsAuth.checkAndIncrementAiUsage(userId);
      if (!quotaCheck.allowed) {
        return sendJson(res, 200, {
          reply: '⚠️ **Daily AI Mentor Limit Reached (' + quotaCheck.planName + ')**\n\n' + quotaCheck.reason,
          exhausted: true,
          upgradeRequired: true,
          reason: quotaCheck.reason,
          currentUsage: quotaCheck.currentUsage,
          dailyLimit: quotaCheck.dailyLimit,
          plan: quotaCheck.plan,
          planName: quotaCheck.planName
        });
      }

      res.writeHead(200, {
        'Content-Type': 'text/event-stream; charset=utf-8',
        'Cache-Control': 'no-cache, no-transform',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': '*'
      });
      streamStarted = true;
      sse({ type: 'meta', plan: quotaCheck.plan, planName: quotaCheck.planName, dailyLimit: quotaCheck.dailyLimit, remainingToday: quotaCheck.remaining });

      const startTime = Date.now();
      // Ground the answer in the lesson the learner has open.
      const lessonCtx = lessonId ? repo.getLessonText(lessonId) : null;
      const lessonText = lessonCtx ? lessonCtx.text : '';
      const result = await cmsAuth.streamRealGeminiAI(
        buildMentorPrompt({ ...body, lessonTitle: lessonCtx ? lessonCtx.title : body.lessonTitle }, !!lessonText),
        groundQuestion(question, lessonText),
        text => sse({ type: 'chunk', text })
      );

      // Only point at other lessons when the open lesson does not cover the question.
      let related = [];
      if (!lessonCovers(question, lessonText)) {
        related = cmsAuth.searchCurriculumLessons(question, repo.getCurriculum()).filter(r => r.id !== lessonId)
          .slice(0, 2).map(r => ({ id: r.id, title: r.title, trackName: r.trackName }));
      }

      const userObj = cmsAuth.getUser(userId);
      litellm.trackUsage({
        userId, userName: userObj?.name, userEmail: userObj?.email, model: result.model,
        promptText: question, completionText: result.text,
        latencyMs: Math.max(120, Date.now() - startTime), hasCustomKey: false
      });
      sse({ type: 'done', model: result.model, finishReason: result.finishReason || null, related });
      return res.end();
    } catch (e) {
      console.error('[Gemini AI Stream Error]', e);
      if (!streamStarted) return sendJson(res, 200, { reply: '⚠️ **AI Mentor Gateway Notice**: ' + e.message, error: e.message });
      sse({ type: 'error', message: e.message });
      return res.end();
    }
  }

  // 6. POST /api/chat (Production Real Gemini AI Mentor with Subscription Gate)
  if (req.method === 'POST' && pathname === '/api/chat') {
    try {
      const body = await parseBody(req);
      const question = body.question || body.message || '';
      const lessonId = body.lessonId || '';
      const trackId = body.trackId || '';
      const lessonTitle = body.lessonTitle || '';
      const userId = getReqUserId(req);

      if (!question.trim()) {
        return sendJson(res, 400, { error: 'Question cannot be empty' });
      }

      // 1. Subscription & Daily AI Quota Enforcement
      const quotaCheck = cmsAuth.checkAndIncrementAiUsage(userId);
      if (!quotaCheck.allowed) {
        return sendJson(res, 200, {
          reply: `⚠️ **Daily AI Mentor Limit Reached (${quotaCheck.planName})**\n\n${quotaCheck.reason}\n\nTo unlock **100+ queries/day**, priority inference, Monaco IDE runners, and company problem filters:\n\n👉 **[Upgrade to Pro Engineer (₹499/mo)](#open-pricing-modal)** or **[Staff / Enterprise](#open-pricing-modal)**.\n\nYour free allowance will also reset automatically tomorrow at midnight.`,
          exhausted: true,
          upgradeRequired: true,
          currentUsage: quotaCheck.currentUsage,
          dailyLimit: quotaCheck.dailyLimit,
          plan: quotaCheck.plan,
          planName: quotaCheck.planName
        });
      }

      const curriculum = repo.getCurriculum();
      const startTime = Date.now();

      // 2. Mentor prompt, grounded in the open lesson
      const lessonCtx = lessonId ? repo.getLessonText(lessonId) : null;
      const lessonText = lessonCtx ? lessonCtx.text : '';
      const sysPrompt = buildMentorPrompt({ ...body, lessonTitle: lessonCtx ? lessonCtx.title : lessonTitle }, !!lessonText);

      let reply = '';
      let modelUsed = 'gemini-3.5-flash';
      try {
        const geminiRes = await cmsAuth.callRealGeminiAI(sysPrompt, groundQuestion(question, lessonText));
        reply = geminiRes.text;
        modelUsed = geminiRes.model;

        // Only suggest other lessons when the open lesson does not cover the question
        const related = lessonCovers(question, lessonText) ? [] : cmsAuth.searchCurriculumLessons(question, curriculum).filter(r => r.id !== lessonId).slice(0, 2);
        if (related.length > 0) {
          reply += `\n\n---\n**Related lessons:**\n` +
            related.map(r => `- [${r.title} (${r.trackName})](#open-lesson-${r.id})`).join('\n');
        }
      } catch (err) {
        console.error('[Gemini AI Mentor Error]', err);
        return sendJson(res, 200, {
          reply: `⚠️ **AI Mentor Gateway Notice**: ${err.message}. Please verify server network connectivity and retry.`,
          exhausted: false,
          error: err.message
        });
      }

      const latencyMs = Date.now() - startTime;
      const userObj = cmsAuth.getUser(userId);

      // 3. Token Tracking
      const usage = litellm.trackUsage({
        userId,
        userName: userObj?.name,
        userEmail: userObj?.email,
        model: modelUsed,
        promptText: question,
        completionText: reply,
        latencyMs: Math.max(120, latencyMs),
        hasCustomKey: false
      });

      return sendJson(res, 200, {
        reply,
        plan: quotaCheck.plan,
        planName: quotaCheck.planName,
        dailyUsage: quotaCheck.currentUsage,
        dailyLimit: quotaCheck.dailyLimit,
        remainingToday: quotaCheck.remaining,
        tokenUsage: usage,
        model: modelUsed,
        timestamp: new Date().toISOString(),
        lessonContext: { lessonId, lessonTitle }
      });
    } catch (e) {
      return sendJson(res, 500, { error: 'Failed to process AI chat query', details: e.message });
    }
  }

  // --------------------------------------------------------------------------
  // SUBSCRIPTION & PAID TIER APIs
  // --------------------------------------------------------------------------
  if (pathname === '/api/subscription/plans' && req.method === 'GET') {
    return sendJson(res, 200, { plans: cmsAuth.SUBSCRIPTION_PLANS });
  }

  if (pathname === '/api/subscription/status' && req.method === 'GET') {
    const userId = getReqUserId(req);
    const sub = cmsAuth.getUserSubscription(userId);
    return sendJson(res, 200, sub);
  }

  // Plan changes. Paid plans need verified payment (Razorpay) or explicit dev-only demo mode.
  if (pathname === '/api/subscription/upgrade' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      const userId = getReqUserId(req);
      const plan = body.plan || body.planId;
      if (!cmsAuth.SUBSCRIPTION_PLANS[plan]) return sendJson(res, 400, { error: 'Invalid plan' });
      if (plan === 'free') return sendJson(res, 200, cmsAuth.upgradeUserPlan(userId, 'free'));
      if (cmsAuth.paymentMode() !== 'demo') {
        return sendJson(res, 402, { error: 'Payment required. Use /api/payments/create-order.', paymentMode: cmsAuth.paymentMode() });
      }
      console.warn('[Billing] DEMO upgrade (no payment) for ' + userId + ' -> ' + plan);
      return sendJson(res, 200, cmsAuth.upgradeUserPlan(userId, plan));
    } catch (e) {
      return sendJson(res, 500, { error: e.message });
    }
  }

  if (pathname === '/api/payments/create-order' && req.method === 'POST') {
    try {
      const userId = getReqUserId(req);
      if (cmsAuth.paymentMode() !== 'razorpay') return sendJson(res, 400, { error: 'Payment gateway not configured', paymentMode: cmsAuth.paymentMode() });
      const body = await parseBody(req);
      return sendJson(res, 200, await cmsAuth.createPaymentOrder(userId, body.plan || body.planId));
    } catch (e) {
      return sendJson(res, 400, { error: e.message });
    }
  }

  if (pathname === '/api/payments/verify' && req.method === 'POST') {
    try {
      const userId = getReqUserId(req);
      const body = await parseBody(req);
      const result = cmsAuth.verifyPaymentAndUpgrade(userId, {
        orderId: body.razorpay_order_id, paymentId: body.razorpay_payment_id, signature: body.razorpay_signature
      });
      return sendJson(res, result.success ? 200 : 400, result);
    } catch (e) {
      return sendJson(res, 400, { error: e.message });
    }
  }

  // --------------------------------------------------------------------------
  // AUTH & USER APIs
  // --------------------------------------------------------------------------
  if (pathname === '/api/auth/providers' && req.method === 'GET') {
    return sendJson(res, 200, { ...oauth.configured(), dev: devLoginAllowed(req) });
  }

  // Step 1: send the browser to Google/GitHub. A signed state carries a nonce that is also
  // set as an HttpOnly cookie, so the callback only succeeds in the browser that started it.
  const startMatch = /^\/api\/auth\/(google|github)\/start$/.exec(pathname);
  if (startMatch && req.method === 'GET') {
    const provider = startMatch[1];
    if (!oauth.configured()[provider]) return redirect(res, '/?auth_error=' + encodeURIComponent(provider + ' sign-in is not configured'));
    const nonce = oauth.newNonce();
    const state = cmsAuth.signState({ p: provider, n: nonce });
    const secure = oauth.baseUrl(req).startsWith('https') ? '; Secure' : '';
    return redirect(res, oauth.authorizeUrl(req, provider, state), {
      'Set-Cookie': 'aa_oauth=' + nonce + '; HttpOnly; SameSite=Lax; Path=/api/auth; Max-Age=600' + secure
    });
  }

  // Step 2: provider calls back with a code; we verify the identity and issue our own token.
  const cbMatch = /^\/api\/auth\/(google|github)\/callback$/.exec(pathname);
  if (cbMatch && req.method === 'GET') {
    const provider = cbMatch[1];
    const clearCookie = { 'Set-Cookie': 'aa_oauth=; HttpOnly; SameSite=Lax; Path=/api/auth; Max-Age=0' };
    const fail = (msg) => redirect(res, '/?auth_error=' + encodeURIComponent(msg), clearCookie);
    try {
      const q = parsedUrl.query;
      if (q.error) return fail('Sign-in was cancelled');
      const st = cmsAuth.verifyState(String(q.state || ''));
      if (!st || st.p !== provider || !st.n || st.n !== readCookie(req, 'aa_oauth')) return fail('Sign-in expired, please try again');
      if (!q.code) return fail('Sign-in failed');
      const who = await oauth.fetchIdentity(req, provider, String(q.code));
      const { token } = cmsAuth.loginUser({ provider, ...who });
      return redirect(res, '/#auth=' + token, clearCookie);
    } catch (e) {
      console.error('[Auth]', provider, 'callback failed:', e.message);
      return fail(e.message || 'Sign-in failed');
    }
  }

  // Local development convenience; unavailable once an OAuth app is configured or in production.
  if (pathname === '/api/auth/dev-login' && req.method === 'POST') {
    if (!devLoginAllowed(req)) return sendJson(res, 404, { error: 'Not found' });
    try {
      const body = await parseBody(req);
      return sendJson(res, 200, cmsAuth.loginUser({ provider: 'dev', email: body.email, name: body.name }));
    } catch (e) {
      return sendJson(res, 400, { error: e.message });
    }
  }

  if (pathname === '/api/auth/me' && req.method === 'GET') {
    const userId = getReqUserId(req);
    if (!userId) return sendJson(res, 401, { error: 'Sign in required', loginRequired: true });
    const user = cmsAuth.getUser(userId);
    return sendJson(res, 200, { user: { ...user, isAdmin: repo.isAdminEmail(user.email) } });
  }

  if (pathname === '/api/user/sync-progress' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      const userId = getReqUserId(req);
      const updated = cmsAuth.syncProgress(userId, body);
      return sendJson(res, 200, { success: true, user: updated });
    } catch (e) {
      return sendJson(res, 500, { error: e.message });
    }
  }

  if (pathname === '/api/user/add-credits' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      const userId = getReqUserId(req);
      const updated = cmsAuth.addCredits(userId, body.amount || 10);
      return sendJson(res, 200, { success: true, credits: updated.credits });
    } catch (e) {
      return sendJson(res, 500, { error: e.message });
    }
  }

  // --------------------------------------------------------------------------
  // ADMIN CMS APIs
  // --------------------------------------------------------------------------
  if (pathname === '/api/admin/admins' && req.method === 'GET') {
    return sendJson(res, 200, { admins: repo.listAdmins() });
  }
  if (pathname === '/api/admin/admins' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      const me = cmsAuth.getUser(getReqUserId(req));
      return sendJson(res, 200, { admins: repo.addAdmin(body.email, me ? me.email : 'admin-key') });
    } catch (e) { return sendJson(res, 400, { error: e.message }); }
  }
  if (pathname === '/api/admin/admins/remove' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      return sendJson(res, 200, { admins: repo.removeAdmin(body.email) });
    } catch (e) { return sendJson(res, 400, { error: e.message }); }
  }

  if (pathname === '/api/admin/diagrams' && req.method === 'GET') {
    const lessonId = String(parsedUrl.query.lesson || '');
    return sendJson(res, 200, { diagrams: repo.listDiagrams(lessonId) });
  }
  if (pathname === '/api/admin/diagrams' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      return sendJson(res, 200, repo.saveDiagram(body));
    } catch (e) { return sendJson(res, 400, { error: e.message }); }
  }
  if (pathname === '/api/admin/diagrams/delete' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      return sendJson(res, 200, { deleted: repo.deleteDiagram(Number(body.id)) });
    } catch (e) { return sendJson(res, 400, { error: e.message }); }
  }

  if (pathname === '/api/admin/lessons' && req.method === 'GET') {
    try {
      const curriculum = repo.getCurriculum();
      const lessons = cmsAuth.adminGetAllLessons(curriculum);
      return sendJson(res, 200, { lessons });
    } catch (e) {
      return sendJson(res, 500, { error: e.message });
    }
  }

  if (pathname === '/api/admin/lesson' && req.method === 'GET') {
    try {
      const lessonId = parsedUrl.query.id;
      if (!lessonId) return sendJson(res, 400, { error: 'Missing lesson id' });
      const curriculum = repo.getCurriculum();
      const detail = repo.getAdminLesson(lessonId);
      if (!detail) return sendJson(res, 404, { error: 'Lesson not found' });
      return sendJson(res, 200, detail);
    } catch (e) {
      return sendJson(res, 500, { error: e.message });
    }
  }

  if (pathname === '/api/admin/save-lesson' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      const curriculum = repo.getCurriculum();
      const result = repo.saveLesson(body);
      return sendJson(res, 200, result);
    } catch (e) {
      return sendJson(res, 500, { error: e.message });
    }
  }

  // --------------------------------------------------------------------------
  // MOTIVATIONAL REMINDERS & EMAIL APIs (Database & Queue Wired)
  // --------------------------------------------------------------------------
  if (pathname === '/api/reminders/test-email' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      const userId = getReqUserId(req);
      const user = cmsAuth.getUser(userId);
      const curriculum = repo.getCurriculum();
      const allLessons = cmsAuth.adminGetAllLessons(curriculum);
      const randomLesson = allLessons[Math.floor(Math.random() * allLessons.length)];
      
      const dispatchResult = await cmsAuth.dispatchDailyEmailToUser(user, randomLesson);
      
      return sendJson(res, 200, {
        success: true,
        email: user?.email || 'candidate@faang.io',
        subject: `🔥 Daily 50LPA Drill: ${randomLesson.title} (${user?.streak || 3}-day streak)`,
        htmlPreview: dispatchResult.htmlContent,
        logEntry: dispatchResult.logEntry
      });
    } catch (e) {
      return sendJson(res, 500, { error: e.message });
    }
  }

  if (pathname === '/api/reminders/trigger-cron' && req.method === 'POST') {
    try {
      const curriculum = repo.getCurriculum();
      const result = cmsAuth.runDailyEmailScheduler(curriculum, true);
      return sendJson(res, 200, result);
    } catch (e) {
      return sendJson(res, 500, { error: e.message });
    }
  }

  if (pathname === '/api/reminders/logs' && req.method === 'GET') {
    try {
      const logs = cmsAuth.getEmailLogs();
      return sendJson(res, 200, { logs });
    } catch (e) {
      return sendJson(res, 500, { error: e.message });
    }
  }

  // --------------------------------------------------------------------------
  // LITELLM TOKEN TRACKING & ADMIN BUDGET APIS
  // --------------------------------------------------------------------------
  if (pathname === '/api/admin/tokens/summary' && req.method === 'GET') {
    try {
      const summary = litellm.getPlatformSummary();
      return sendJson(res, 200, summary);
    } catch (e) {
      return sendJson(res, 500, { error: e.message });
    }
  }

  if (pathname === '/api/admin/tokens/set-limit' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      const { userId, limit } = body;
      if (!userId || !limit) return sendJson(res, 400, { error: 'Missing userId or limit' });
      const updated = litellm.adminSetUserLimit(userId, limit);
      return sendJson(res, 200, { success: true, user: updated });
    } catch (e) {
      return sendJson(res, 500, { error: e.message });
    }
  }

  if (pathname === '/api/admin/tokens/reset-user' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      const { userId } = body;
      if (!userId) return sendJson(res, 400, { error: 'Missing userId' });
      const updated = litellm.adminResetUserUsage(userId);
      return sendJson(res, 200, { success: true, user: updated });
    } catch (e) {
      return sendJson(res, 500, { error: e.message });
    }
  }

  if (pathname === '/api/admin/tokens/toggle-block' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      const { userId } = body;
      if (!userId) return sendJson(res, 400, { error: 'Missing userId' });
      const updated = litellm.adminToggleUserBlock(userId);
      return sendJson(res, 200, { success: true, user: updated });
    } catch (e) {
      return sendJson(res, 500, { error: e.message });
    }
  }

  if (pathname === '/api/admin/tokens/reset-all' && req.method === 'POST') {
    try {
      const result = litellm.adminResetAllUsage();
      return sendJson(res, 200, result);
    } catch (e) {
      return sendJson(res, 500, { error: e.message });
    }
  }

  if (pathname === '/api/admin/tokens/default-limit' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      const result = litellm.adminSetDefaultLimit(body.limit);
      return sendJson(res, 200, result);
    } catch (e) {
      return sendJson(res, 500, { error: e.message });
    }
  }

  // 7. GET & POST /api/progress
  if (pathname === '/api/progress') {
    if (req.method === 'GET') {
      try {
        const data = JSON.parse(fs.readFileSync(PROGRESS_FILE, 'utf8'));
        return sendJson(res, 200, data);
      } catch (e) {
        return sendJson(res, 500, { error: 'Failed to read progress' });
      }
    } else if (req.method === 'POST') {
      try {
        const body = await parseBody(req);
        fs.writeFileSync(PROGRESS_FILE, JSON.stringify(body, null, 2));
        const userId = getReqUserId(req);
        const syncedUser = cmsAuth.syncProgress(userId, body);
        return sendJson(res, 200, { success: true, progress: body, user: syncedUser, streak: syncedUser?.streak });
      } catch (e) {
        return sendJson(res, 500, { error: 'Failed to save progress' });
      }
    }
  }

  // 8. GET /api/stats
  if (req.method === 'GET' && pathname === '/api/stats') {
    try {
      const curriculum = repo.getCurriculum();
      const videos = repo.getVideos();
      const progress = JSON.parse(fs.readFileSync(PROGRESS_FILE, 'utf8'));

      let totalLessons = 0;
      let totalFiveStar = 0;
      let newLessonsCount = 0;

      for (const t of curriculum.tracks) {
        for (const b of t.blocks) {
          for (const l of b.lessons) {
            totalLessons++;
            if (l.stars === 5) totalFiveStar++;
            if (l.isNew) newLessonsCount++;
          }
        }
      }

      const completedCount = (progress.completed || []).length;
      const readinessScore = Math.min(100, Math.round((completedCount / (totalLessons || 1)) * 100));

      return sendJson(res, 200, {
        totalTracks: curriculum.tracks.length,
        totalLessons,
        totalFiveStar,
        newLessonsCount,
        totalVideos: videos.length,
        completedCount,
        readinessScore
      });
    } catch (e) {
      return sendJson(res, 500, { error: 'Failed to compute stats' });
    }
  }

  // --------------------------------------------------------------------------
  // Static File Serving (Public Directory)
  // --------------------------------------------------------------------------
  let filePath = path.join(PUBLIC_DIR, pathname === '/' ? 'index.html' : pathname);

  if (!filePath.startsWith(PUBLIC_DIR)) {
    res.writeHead(403, { 'Content-Type': 'text/plain' });
    res.end('403 Forbidden');
    return;
  }

  fs.stat(filePath, (err, stats) => {
    if (err || !stats.isFile()) {
      const indexPath = path.join(PUBLIC_DIR, 'index.html');
      if (fs.existsSync(indexPath)) {
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        fs.createReadStream(indexPath).pipe(res);
        return;
      }
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('404 Not Found');
      return;
    }

    const ext = path.extname(filePath).toLowerCase();
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';

    res.writeHead(200, { 'Content-Type': contentType });
    fs.createReadStream(filePath).pipe(res);
  });
});

// Automated Daily Reminder Scheduler Background Service
// Checks for scheduled user study blocks every 60 seconds
setInterval(() => {
  try {
    cmsAuth.runDailyEmailScheduler(repo.getCurriculum(), false);
  } catch (e) {}
}, 60 * 1000);

// Start server
server.listen(PORT, '127.0.0.1', () => {
  console.log(`================================================================`);
  console.log(`  🚀 ALGOARCH — 50LPA FAANG CAREER GUIDANCE PLATFORM IS LIVE!   `);
  console.log(`  URL: http://127.0.0.1:${PORT}`);
  console.log(`  Interactive Visuals: ENABLED (Routed in-app)                 `);
  console.log(`  Downloads: ENABLED (/api/download/all-labs.zip)              `);
  console.log(`  AI Mentor: ACTIVE (Live on-page context-aware mentor)        `);
  console.log(`================================================================`);
});
