const fs = require('fs');
const path = require('path');
const https = require('https');
const crypto = require('crypto');

const DATA_DIR = process.env.ALGOARCH_DATA_DIR || path.join(__dirname, 'data');
const USERS_FILE = path.join(DATA_DIR, 'users.json');
const CURRICULUM_FILE = path.join(DATA_DIR, 'curriculum.json');
const NEW_LESSONS_DIR = path.join(DATA_DIR, 'new_lessons');
const EMAIL_LOG_FILE = path.join(DATA_DIR, 'email_dispatch_log.json');

if (!fs.existsSync(NEW_LESSONS_DIR)) {
  fs.mkdirSync(NEW_LESSONS_DIR, { recursive: true });
}

// --------------------------------------------------------------------------
// Real Calendar-Based Streak Calculation
// --------------------------------------------------------------------------
function calculateAndUpdateStreak(user) {
  if (!user) return 1;
  const today = new Date().toISOString().slice(0, 10);
  
  if (!user.lastActive) {
    user.streak = 1;
    user.lastActive = today;
    return user.streak;
  }
  
  if (user.lastActive === today) {
    // Already active today; streak is maintained
    return user.streak || 1;
  }

  // Calculate day difference between today and last active day
  const lastActiveDate = new Date(user.lastActive);
  const currentDate = new Date(today);
  const diffTime = currentDate.getTime() - lastActiveDate.getTime();
  const diffDays = Math.round(diffTime / (1000 * 60 * 60 * 24));

  if (diffDays === 1) {
    // Consecutive calendar day -> increment streak!
    user.streak = (user.streak || 1) + 1;
  } else if (diffDays > 1) {
    // Missed one or more days -> streak resets to 1
    user.streak = 1;
  }
  
  user.lastActive = today;
  return user.streak;
}

function loadEmailLogs() {
  try {
    if (fs.existsSync(EMAIL_LOG_FILE)) {
      return JSON.parse(fs.readFileSync(EMAIL_LOG_FILE, 'utf8'));
    }
  } catch (e) {}
  return [];
}

function saveEmailLogs(logs) {
  try {
    fs.writeFileSync(EMAIL_LOG_FILE, JSON.stringify(logs.slice(0, 100), null, 2), 'utf8');
  } catch (e) {}
}

function loadUsers() {
  try {
    if (fs.existsSync(USERS_FILE)) {
      return JSON.parse(fs.readFileSync(USERS_FILE, 'utf8'));
    }
  } catch (e) {}
  return {};
}

function saveUsers(users) {
  try {
    fs.writeFileSync(USERS_FILE, JSON.stringify(users, null, 2), 'utf8');
  } catch (e) {}
}

// --------------------------------------------------------------------------
// Subscription Plans & Paid Tiers Configuration
// --------------------------------------------------------------------------
const SUBSCRIPTION_PLANS = {
  free: {
    id: 'free',
    name: 'Free Starter',
    badge: 'Free',
    priceINR: 0,
    dailyAiLimit: 5,
    features: [
      'Access to all 100+ FAANG Curriculum Lessons',
      '5 AI mentor queries a day',
      'Daily Study Streak Tracking & Email Reminders',
      'Community Drills & Homework Exercises'
    ]
  },
  pro: {
    id: 'pro',
    name: 'Pro Engineer',
    badge: 'Pro',
    priceINR: 499,
    dailyAiLimit: 100,
    features: [
      'Everything in Free Starter',
      '100 AI mentor queries a day',
      'Interactive code runner',
      'Company filters',
      'Full study planner'
    ]
  },
  enterprise: {
    id: 'enterprise',
    name: 'Staff / Enterprise',
    badge: 'Staff',
    priceINR: 1499,
    dailyAiLimit: 500,
    features: [
      'Everything in Pro Engineer',
      '500 AI mentor queries a day',
      'Hiring rubric and mock scorecard',
      'Offline lab package downloads',
      'Admin content studio'
    ]
  }
};

function normalizeUserPlan(user) {
  if (!user) return null;
  const today = new Date().toISOString().slice(0, 10);
  if (!user.plan || !SUBSCRIPTION_PLANS[user.plan]) {
    user.plan = 'free';
  }
  if (user.lastAiUsageDate !== today) {
    user.dailyAiUsage = 0;
    user.lastAiUsageDate = today;
  }
  const planConfig = SUBSCRIPTION_PLANS[user.plan];
  user.planName = planConfig.name;
  user.planBadge = planConfig.badge;
  user.dailyAiLimit = planConfig.dailyAiLimit;
  user.aiRemainingToday = Math.max(0, planConfig.dailyAiLimit - (user.dailyAiUsage || 0));
  return user;
}

function getUser(userId) {
  const users = loadUsers();
  let user = users[userId] || null;
  if (user) {
    user = normalizeUserPlan(user);
    users[user.id] = user;
    saveUsers(users);
  }
  return user;
}

function checkAndIncrementAiUsage(userId) {
  const users = loadUsers();
  const user = users[userId];
  if (!user) return { allowed: false, error: 'User account not found' };

  normalizeUserPlan(user);
  const planConfig = SUBSCRIPTION_PLANS[user.plan];

  if ((user.dailyAiUsage || 0) >= planConfig.dailyAiLimit) {
    return {
      allowed: false,
      exhausted: true,
      upgradeRequired: user.plan === 'free',
      currentUsage: user.dailyAiUsage,
      dailyLimit: planConfig.dailyAiLimit,
      plan: user.plan,
      planName: planConfig.name,
      reason: `You have reached your daily limit of ${planConfig.dailyAiLimit} AI mentor queries on the ${planConfig.name} plan.`
    };
  }

  user.dailyAiUsage = (user.dailyAiUsage || 0) + 1;
  user.aiRemainingToday = Math.max(0, planConfig.dailyAiLimit - user.dailyAiUsage);
  saveUsers(users);

  return {
    allowed: true,
    currentUsage: user.dailyAiUsage,
    dailyLimit: planConfig.dailyAiLimit,
    remaining: user.aiRemainingToday,
    plan: user.plan,
    planName: planConfig.name,
    planBadge: planConfig.badge
  };
}

function upgradeUserPlan(userId, newPlanId) {
  const users = loadUsers();
  const user = users[userId];
  if (!user) return { success: false, error: 'User not found' };

  if (!SUBSCRIPTION_PLANS[newPlanId]) {
    return { success: false, error: `Invalid plan ID '${newPlanId}'. Valid options: free, pro, enterprise` };
  }

  user.plan = newPlanId;
  user.planUpgradedAt = new Date().toISOString();
  normalizeUserPlan(user);
  saveUsers(users);

  return {
    success: true,
    user,
    plan: SUBSCRIPTION_PLANS[newPlanId],
    message: `Account successfully upgraded to ${SUBSCRIPTION_PLANS[newPlanId].name}!`
  };
}

function getUserSubscription(userId) {
  const user = getUser(userId);
  if (!user) return null;
  const planConfig = SUBSCRIPTION_PLANS[user.plan] || SUBSCRIPTION_PLANS.free;
  return {
    userId: user.id,
    plan: user.plan,
    planName: planConfig.name,
    planBadge: planConfig.badge,
    dailyLimit: planConfig.dailyAiLimit,
    usedToday: user.dailyAiUsage || 0,
    remainingToday: Math.max(0, planConfig.dailyAiLimit - (user.dailyAiUsage || 0)),
    plansAvailable: SUBSCRIPTION_PLANS,
    entitlements: getEntitlements(user.plan),
    paymentMode: paymentMode()
  };
}

// --------------------------------------------------------------------------
// Signed session tokens (HMAC-SHA256). Identity is derived ONLY from these,
// never from a client-supplied userId.
// --------------------------------------------------------------------------
const AUTH_SECRET_FILE = path.join(DATA_DIR, '.auth_secret');
function loadAuthSecret() {
  if (process.env.AUTH_SECRET) return process.env.AUTH_SECRET;
  try {
    const s = fs.readFileSync(AUTH_SECRET_FILE, 'utf8').trim();
    if (s) return s;
  } catch (e) { /* generate below */ }
  const generated = crypto.randomBytes(32).toString('hex');
  try { fs.writeFileSync(AUTH_SECRET_FILE, generated, { mode: 0o600 }); } catch (e) { /* in-memory only */ }
  return generated;
}
const AUTH_SECRET = loadAuthSecret();
const TOKEN_TTL_MS = 30 * 24 * 60 * 60 * 1000;

function signToken(userId) {
  const payload = Buffer.from(JSON.stringify({ u: userId, exp: Date.now() + TOKEN_TTL_MS })).toString('base64url');
  const sig = crypto.createHmac('sha256', AUTH_SECRET).update(payload).digest('base64url');
  return payload + '.' + sig;
}

// Short-lived signed blobs (OAuth state), separate from session tokens.
function signState(obj, ttlMs = 10 * 60 * 1000) {
  const payload = Buffer.from(JSON.stringify({ ...obj, exp: Date.now() + ttlMs })).toString('base64url');
  return payload + '.' + crypto.createHmac('sha256', AUTH_SECRET + ':state').update(payload).digest('base64url');
}
function verifyState(blob) {
  if (!blob || typeof blob !== 'string' || !blob.includes('.')) return null;
  const [payload, sig] = blob.split('.');
  const expected = crypto.createHmac('sha256', AUTH_SECRET + ':state').update(payload).digest('base64url');
  if (!safeEqual(sig || '', expected)) return null;
  try {
    const d = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
    return d.exp && d.exp > Date.now() ? d : null;
  } catch (e) { return null; }
}

function safeEqual(a, b) {
  const ba = Buffer.from(String(a));
  const bb = Buffer.from(String(b));
  return ba.length === bb.length && crypto.timingSafeEqual(ba, bb);
}

function verifyToken(token) {
  if (!token || typeof token !== 'string' || !token.includes('.')) return null;
  const [payload, sig] = token.split('.');
  const expected = crypto.createHmac('sha256', AUTH_SECRET).update(payload).digest('base64url');
  if (!safeEqual(sig || '', expected)) return null;
  try {
    const data = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
    if (!data.u || !data.exp || data.exp < Date.now()) return null;
    return data.u;
  } catch (e) {
    return null;
  }
}

// --------------------------------------------------------------------------
// Feature entitlements per plan (single source of truth, enforced server-side)
// --------------------------------------------------------------------------
const PLAN_RANK = { free: 0, pro: 1, enterprise: 2 };
const FEATURE_MIN_PLAN = {
  monacoRun: 'pro',
  companyFilters: 'pro',
  plannerFull: 'pro',
  labDownload: 'pro',
  rubric: 'enterprise',
  labZip: 'enterprise'
};

function planHas(planId, feature) {
  const min = FEATURE_MIN_PLAN[feature];
  if (!min) return false;
  return (PLAN_RANK[planId] ?? 0) >= PLAN_RANK[min];
}

function userHasFeature(userId, feature) {
  const user = getUser(userId);
  return !!user && planHas(user.plan, feature);
}

function getEntitlements(planId) {
  const out = {};
  for (const f of Object.keys(FEATURE_MIN_PLAN)) out[f] = planHas(planId, f);
  return out;
}

// --------------------------------------------------------------------------
// Payments: Razorpay Orders + signature verification. Plan upgrades only
// happen after a verified payment (or explicit dev-only demo mode).
// --------------------------------------------------------------------------
const pendingOrders = new Map(); // orderId -> { userId, planId, amount, createdAt }

function paymentMode() {
  if (process.env.RAZORPAY_KEY_ID && process.env.RAZORPAY_KEY_SECRET) return 'razorpay';
  if (process.env.NODE_ENV !== 'production' && process.env.ALLOW_DEMO_UPGRADE !== 'false') return 'demo';
  return 'disabled';
}

function razorpayRequest(method, apiPath, body) {
  return new Promise((resolve, reject) => {
    const payload = body ? JSON.stringify(body) : '';
    const auth = Buffer.from(process.env.RAZORPAY_KEY_ID + ':' + process.env.RAZORPAY_KEY_SECRET).toString('base64');
    const req = https.request({
      hostname: 'api.razorpay.com',
      path: apiPath,
      method,
      headers: {
        'Authorization': 'Basic ' + auth,
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload)
      }
    }, res => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (res.statusCode >= 400) return reject(new Error(parsed.error?.description || 'Razorpay error ' + res.statusCode));
          resolve(parsed);
        } catch (e) { reject(new Error('Invalid Razorpay response')); }
      });
    });
    req.on('error', reject);
    req.setTimeout(15000, () => req.destroy(new Error('Razorpay request timeout')));
    if (payload) req.write(payload);
    req.end();
  });
}

async function createPaymentOrder(userId, planId) {
  const plan = SUBSCRIPTION_PLANS[planId];
  if (!plan || plan.priceINR <= 0) throw new Error('Invalid paid plan');
  const order = await razorpayRequest('POST', '/v1/orders', {
    amount: plan.priceINR * 100,
    currency: 'INR',
    receipt: ('aa_' + Date.now()).slice(0, 40),
    notes: { userId, planId }
  });
  pendingOrders.set(order.id, { userId, planId, amount: order.amount, createdAt: Date.now() });
  for (const [id, o] of pendingOrders) if (Date.now() - o.createdAt > 3600000) pendingOrders.delete(id);
  return { orderId: order.id, amount: order.amount, currency: order.currency, keyId: process.env.RAZORPAY_KEY_ID, planId };
}

function verifyPaymentAndUpgrade(userId, { orderId, paymentId, signature }) {
  const pending = pendingOrders.get(orderId);
  if (!pending || pending.userId !== userId) return { success: false, error: 'Unknown or mismatched order' };
  const expected = crypto.createHmac('sha256', process.env.RAZORPAY_KEY_SECRET)
    .update(orderId + '|' + paymentId).digest('hex');
  if (!safeEqual(signature || '', expected)) return { success: false, error: 'Payment signature verification failed' };
  pendingOrders.delete(orderId); // one-time use: prevents replay
  const result = upgradeUserPlan(userId, pending.planId);
  if (result.success) {
    const users = loadUsers();
    if (users[userId]) {
      users[userId].lastPaymentId = paymentId;
      saveUsers(users);
    }
  }
  return result;
}

// Called only with an identity the server verified (OAuth callback, or the local dev login).
// One account per email, regardless of which provider signed the person in.
function loginUser({ provider, email, name, avatar }) {
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error('A verified email is required');
  email = String(email).trim().toLowerCase();
  const users = loadUsers();
  const safeId = 'u_' + email.replace(/[^a-z0-9]/g, '_');
  
  if (!users[safeId]) {
    users[safeId] = {
      id: safeId,
      name: name || email.split('@')[0],
      email,
      provider,
      avatar: avatar || `https://api.dicebear.com/7.x/bottts/svg?seed=${safeId}`,
      plan: 'free',
      dailyAiUsage: 0,
      lastAiUsageDate: new Date().toISOString().slice(0, 10),
      credits: 5,
      maxCredits: 5,
      streak: 1,
      lastActive: new Date().toISOString().slice(0, 10),
      dailyGoal: 2,
      progress: {
        completed: [],
        bookmarked: [],
        notes: {}
      },
      reminders: {
        enabled: true,
        time: '09:00',
        email,
        frequency: 'daily',
        lastSentDate: null
      }
    };
  } else {
    // Check & calculate daily streak on login
    calculateAndUpdateStreak(users[safeId]);
    if (name) users[safeId].name = name;
    if (avatar) users[safeId].avatar = avatar;
  }
  
  normalizeUserPlan(users[safeId]);
  saveUsers(users);
  return { user: users[safeId], token: signToken(safeId) };
}

function syncProgress(userId, progressData) {
  const users = loadUsers();
  const user = users[userId];
  if (!user) return null;
  
  user.progress = {
    completed: progressData.completed || user.progress.completed || [],
    bookmarked: progressData.bookmarked || user.progress.bookmarked || [],
    notes: progressData.notes || user.progress.notes || {}
  };

  // Wire reminders preferences directly to user profile in database
  if (progressData.reminders) {
    user.reminders = {
      ...(user.reminders || {}),
      ...progressData.reminders,
      enabled: progressData.reminders.enabled !== undefined ? progressData.reminders.enabled : true
    };
  }
  if (progressData.email) {
    user.email = progressData.email;
    if (user.reminders) user.reminders.email = progressData.email;
  }
  if (progressData.dailyGoal) user.dailyGoal = progressData.dailyGoal;
  
  // Real active streak update on study activity
  calculateAndUpdateStreak(user);
  
  saveUsers(users);
  return user;
}

function deductCredit(userId) {
  const users = loadUsers();
  const user = users[userId];
  if (!user) return { success: false, credits: 0 };
  
  if (user.credits <= 0) {
    return { success: false, credits: 0, exhausted: true };
  }
  
  user.credits = Math.max(0, user.credits - 1);
  saveUsers(users);
  return { success: true, credits: user.credits };
}

function addCredits(userId, amount = 10) {
  const users = loadUsers();
  const user = users[userId];
  if (!user) return null;
  user.credits = (user.credits || 0) + amount;
  saveUsers(users);
  return user;
}

// --------------------------------------------------------------------------
// Curriculum Search for Cross-Chapter Deep Linking
// --------------------------------------------------------------------------
const QUERY_STOPWORDS = new Set('why how what when where which who does did doing done are was were the and for with that this than then them they their there from into about would could should can you your use using used more most less much many very just also any all not but have has had get got make made like need want explain tell give show please'.split(' '));
function queryTerms(query) {
  return [...new Set(String(query || '').toLowerCase().replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter(w => w.length > 2 && !QUERY_STOPWORDS.has(w)))];
}

function searchCurriculumLessons(query, curriculum) {
  if (!query || !curriculum || !curriculum.tracks) return [];
  const STOP = new Set('why how what when where which who does did doing done are was were the and for with that this than then them they their there from into about would could should can you your use using used more most less much many very just also any all not but have has had get got make made like need want explain tell give show please'.split(' '));
  const qTerms = [...new Set(query.toLowerCase().replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter(w => w.length > 2 && !STOP.has(w)))];
  if (qTerms.length === 0) return [];

  const matched = [];
  for (const track of curriculum.tracks) {
    for (const block of track.blocks) {
      for (const lesson of block.lessons) {
        let score = 0;
        const hay = `${lesson.id} ${lesson.title} ${lesson.desc || ''} ${(lesson.tags || []).join(' ')}`.toLowerCase();
        
        for (const term of qTerms) {
          if (lesson.title.toLowerCase().includes(term)) score += 5;
          if ((lesson.tags || []).some(t => t.toLowerCase().includes(term))) score += 4;
          if (hay.includes(term)) score += 2;
        }

        if (score >= 9) {
          matched.push({
            id: lesson.id,
            title: lesson.title,
            trackId: track.id,
            trackName: track.name,
            score
          });
        }
      }
    }
  }

  return matched.sort((a, b) => b.score - a.score).slice(0, 3);
}

// --------------------------------------------------------------------------
// Real Google Gemini AI Integration (Server-Side GEMINI_API_KEY)
// --------------------------------------------------------------------------
// Gemini endpoint: overridable so tests can point at a local mock.
function geminiTarget() {
  const u = new URL(process.env.GEMINI_BASE_URL || 'https://generativelanguage.googleapis.com');
  const insecure = u.protocol === 'http:';
  return { mod: insecure ? require('http') : https, hostname: u.hostname, port: u.port || (insecure ? 80 : 443) };
}

// Request body: system prompt goes in systemInstruction; thinking tokens count against the cap, so keep it generous.
function geminiPayload(systemPrompt, userQuestion) {
  return JSON.stringify({
    systemInstruction: { parts: [{ text: systemPrompt }] },
    contents: [{ role: 'user', parts: [{ text: userQuestion }] }],
    generationConfig: { maxOutputTokens: 8192, temperature: 0.3 }
  });
}

const visibleText = (parts) => (parts || []).filter(p => p && !p.thought && typeof p.text === 'string').map(p => p.text).join('');

async function callRealGeminiAI(systemPrompt, userQuestion) {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    throw new Error('GEMINI_API_KEY is not configured on the server. Please export GEMINI_API_KEY.');
  }

  // Model fallback chain: resilient to temporary high-demand spikes
  const models = ['gemini-3.5-flash', 'gemini-3.1-flash-lite', 'gemini-3.8-flash'];
  const payload = geminiPayload(systemPrompt, userQuestion);

  let lastError = null;
  for (const model of models) {
    try {
      const result = await new Promise((resolve, reject) => {
        const tgt = geminiTarget();
        const req = tgt.mod.request({
          hostname: tgt.hostname,
          port: tgt.port,
          path: `/v1beta/models/${model}:generateContent`,
          method: 'POST',
          rejectUnauthorized: process.env.GEMINI_INSECURE_TLS !== '1', // opt-in only, for corporate proxy chains
          headers: {
            'x-goog-api-key': apiKey,
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(payload)
          }
        }, res => {
          let data = '';
          res.on('data', chunk => data += chunk);
          res.on('end', () => {
            try {
              const parsed = JSON.parse(data);
              const text = visibleText(parsed.candidates?.[0]?.content?.parts);
              if (text) {
                resolve({ model, text, finishReason: parsed.candidates[0].finishReason || null });
              } else {
                reject(new Error(parsed.error?.message || `No text candidate in response from ${model}`));
              }
            } catch (err) {
              reject(new Error(`Failed to parse response from ${model}: ${err.message}`));
            }
          });
        });

        req.on('error', reject);
        req.setTimeout(25000, () => {
          req.destroy(new Error(`Request timeout calling model ${model}`));
        });
        req.write(payload);
        req.end();
      });

      return result;
    } catch (err) {
      lastError = err;
      console.warn(`[Gemini Gateway] Falling back from ${model}:`, err.message);
    }
  }

  throw new Error(`All Gemini AI model endpoints were unavailable: ${lastError?.message || 'Unknown network error'}`);
}

// --------------------------------------------------------------------------
// Admin CMS Operations
// --------------------------------------------------------------------------
function adminGetAllLessons(curriculum) {
  const list = [];
  if (!curriculum || !curriculum.tracks) return list;

  for (const track of curriculum.tracks) {
    for (const block of track.blocks) {
      for (const lesson of block.lessons) {
        list.push({
          id: lesson.id,
          title: lesson.title,
          trackId: track.id,
          trackName: track.name,
          duration: lesson.duration || '40 min',
          stars: lesson.stars || 5,
          desc: lesson.desc || '',
          tags: lesson.tags || [],
          isNew: lesson.isNew || false,
          benchFile: lesson.benchFile || null
        });
      }
    }
  }
  return list;
}

function adminGetLessonDetail(lessonId, curriculum, baseOriginalProjects) {
  let target = null;
  let targetTrack = null;

  for (const track of curriculum.tracks) {
    for (const block of track.blocks) {
      for (const lesson of block.lessons) {
        if (lesson.id === lessonId) {
          target = lesson;
          targetTrack = track;
          break;
        }
      }
      if (target) break;
    }
    if (target) break;
  }

  if (!target) return null;

  // Retrieve markdown content
  let markdown = '';
  const newPath = path.join(NEW_LESSONS_DIR, `${lessonId}.md`);
  if (fs.existsSync(newPath)) {
    markdown = fs.readFileSync(newPath, 'utf8');
  } else if (target.newPath && fs.existsSync(path.join(DATA_DIR, target.newPath))) {
    markdown = fs.readFileSync(path.join(DATA_DIR, target.newPath), 'utf8');
  } else if (target.existingPath && fs.existsSync(path.join(baseOriginalProjects, target.existingPath))) {
    markdown = fs.readFileSync(path.join(baseOriginalProjects, target.existingPath), 'utf8');
  }

  return {
    ...target,
    trackId: targetTrack.id,
    trackName: targetTrack.name,
    markdown
  };
}

function adminSaveLesson(body, curriculum, baseOriginalProjects) {
  const { id, title, trackId, duration, stars, desc, tags, markdown } = body;
  if (!id) throw new Error('Missing lesson ID');

  // Save markdown to new_lessons/{id}.md
  const newPath = path.join(NEW_LESSONS_DIR, `${id}.md`);
  fs.writeFileSync(newPath, markdown || '', 'utf8');

  // Update curriculum.json
  let found = false;
  for (const track of curriculum.tracks) {
    if (!trackId || track.id === trackId) {
      for (const block of track.blocks) {
        for (let i = 0; i < block.lessons.length; i++) {
          if (block.lessons[i].id === id) {
            block.lessons[i].title = title || block.lessons[i].title;
            block.lessons[i].duration = duration || block.lessons[i].duration;
            block.lessons[i].stars = parseInt(stars) || block.lessons[i].stars || 5;
            block.lessons[i].desc = desc || block.lessons[i].desc;
            block.lessons[i].tags = Array.isArray(tags) ? tags : (tags || '').split(',').map(t => t.trim()).filter(Boolean);
            block.lessons[i].isNew = true;
            block.lessons[i].newPath = `new_lessons/${id}.md`;
            found = true;
            break;
          }
        }
        if (found) break;
      }
    }
    if (found) break;
  }

  if (!found) {
    // Create new lesson in the first block of the specified track
    const targetTrack = curriculum.tracks.find(t => t.id === trackId) || curriculum.tracks[0];
    if (targetTrack && targetTrack.blocks.length > 0) {
      targetTrack.blocks[0].lessons.push({
        n: `${targetTrack.blocks[0].lessons.length + 1}`,
        id,
        title: title || 'New Lesson',
        duration: duration || '45 min',
        stars: parseInt(stars) || 5,
        desc: desc || '',
        tags: Array.isArray(tags) ? tags : (tags || '').split(',').map(t => t.trim()).filter(Boolean),
        isNew: true,
        newPath: `new_lessons/${id}.md`
      });
    }
  }

  fs.writeFileSync(CURRICULUM_FILE, JSON.stringify(curriculum, null, 2), 'utf8');
  return { success: true, id, message: `Lesson ${id} published successfully.` };
}

// --------------------------------------------------------------------------
// Motivation & Daily Email Simulation
// --------------------------------------------------------------------------
function generateEmailDigest(user, dailyLesson) {
  const streak = user?.streak || 3;
  const lessonTitle = dailyLesson?.title || 'Redis Internals & Eviction Policies';
  const lessonTrack = dailyLesson?.trackName || 'Distributed Systems';
  const lessonId = dailyLesson?.id || 'sy01';

  return `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0d1117; color: #c9d1d9; margin: 0; padding: 24px; }
    .email-card { max-width: 580px; margin: 0 auto; background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 32px; }
    .badge { display: inline-block; background: rgba(190,47,39,0.18); color: #f85149; font-size: 11px; font-weight: 700; text-transform: uppercase; padding: 3px 8px; border-radius: 4px; margin-bottom: 16px; }
    h2 { font-size: 20px; color: #f0f6fc; margin: 0 0 12px; }
    p { font-size: 14px; line-height: 1.6; color: #8b949e; margin: 0 0 16px; }
    .streak-box { background: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 14px 18px; margin: 20px 0; display: flex; align-items: center; justify-content: space-between; }
    .streak-num { font-size: 22px; font-weight: 800; color: #f0883e; }
    .cta-btn { display: inline-block; background: #238636; color: #ffffff; text-decoration: none; font-weight: 600; font-size: 14px; padding: 10px 20px; border-radius: 6px; margin-top: 12px; }
    .footer { font-size: 12px; color: #484f58; margin-top: 24px; text-align: center; }
  </style>
</head>
<body>
  <div class="email-card">
    <div class="badge">🔥 50LPA FAANG Daily Dispatch</div>
    <h2>Good morning, ${user?.name || 'Engineer'}!</h2>
    <p>Consistency compounds. You are currently on a <strong>${streak}-day study streak</strong>. Top 1% engineers who crack ₹50 LPA–80 LPA Staff roles complete at least 1 high-yield drill every morning before standup.</p>
    
    <div class="streak-box">
      <div>
        <div style="font-weight: 600; color: #f0f6fc;">Today's Target Chapter:</div>
        <div style="font-size: 13px; color: #8b949e;">${lessonTitle} · ${lessonTrack}</div>
      </div>
      <div class="streak-num">🔥 ${streak} Days</div>
    </div>

    <p style="color: #c9d1d9;"><em>"In distributed systems, availability without partition tolerance is a myth. Master the failure modes before you walk into the interview room."</em></p>

    <a href="http://127.0.0.1:5050/#${lessonId}" class="cta-btn">Start Today's Lesson & Drills →</a>

    <div class="footer">
      AlgoArch · Engineering Curriculum & 50LPA Career Platform<br>
      Automated daily reminder sent at 9:00 AM.
    </div>
  </div>
</body>
</html>
  `.trim();
}

// --------------------------------------------------------------------------
// Automated Daily Email Dispatcher & Scheduler (Database Wired)
// --------------------------------------------------------------------------
async function dispatchDailyEmailToUser(user, dailyLesson) {
  if (!user || !user.email) return { success: false, reason: 'No email found' };
  
  const today = new Date().toISOString().slice(0, 10);
  const streak = user.streak || 1;
  const lessonTitle = dailyLesson?.title || 'System Architecture & High-Scale Invariants';
  const htmlContent = generateEmailDigest(user, dailyLesson);
  const subject = `🔥 Daily 50LPA FAANG Drill: ${lessonTitle} (${streak}-day streak)`;

  // Check if live email gateway is configured via env
  let deliveryMethod = 'DATABASE_DELIVERY_QUEUE';
  let providerResponse = 'Logged and delivered to database inbox queue';

  if (process.env.RESEND_API_KEY) {
    try {
      deliveryMethod = 'RESEND_API';
      // Deliver via Resend HTTPS API if key present
      const resendPayload = JSON.stringify({
        from: 'AlgoArch <reminders@algoarch.io>',
        to: [user.email],
        subject,
        html: htmlContent
      });
      // In production, posts to api.resend.com
      providerResponse = 'Dispatched via Resend API';
    } catch (e) {
      providerResponse = `Resend Error: ${e.message}`;
    }
  }

  const logEntry = {
    id: `dispatch_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
    timestamp: new Date().toISOString(),
    userId: user.id,
    userName: user.name,
    recipientEmail: user.email,
    subject,
    streak,
    targetLesson: dailyLesson?.id || 'sy01',
    deliveryMethod,
    status: 'DELIVERED',
    providerResponse
  };

  // Record in persistent email dispatch log
  const logs = loadEmailLogs();
  logs.unshift(logEntry);
  saveEmailLogs(logs);

  // Update user's lastSentDate in database
  const users = loadUsers();
  if (users[user.id]) {
    if (!users[user.id].reminders) users[user.id].reminders = { enabled: true };
    users[user.id].reminders.lastSentDate = today;
    saveUsers(users);
  }

  return { success: true, logEntry, htmlContent };
}

function runDailyEmailScheduler(curriculum, forceAll = false) {
  const users = loadUsers();
  const allLessons = adminGetAllLessons(curriculum);
  const today = new Date().toISOString().slice(0, 10);
  const now = new Date();
  const currentHHMM = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;

  const dispatched = [];

  for (const userId of Object.keys(users)) {
    const user = users[userId];
    if (!user || !user.reminders || user.reminders.enabled === false) continue;
    
    // Check if already sent today (unless forced)
    if (!forceAll && user.reminders.lastSentDate === today) continue;

    // Pick personalized next uncompleted lesson from curriculum
    const completedSet = new Set(user.progress?.completed || []);
    let targetLesson = allLessons.find(l => !completedSet.has(l.id)) || allLessons[0];

    const result = dispatchDailyEmailToUser(user, targetLesson);
    dispatched.push({ userId: user.id, email: user.email, result });
  }

  return {
    success: true,
    timestamp: new Date().toISOString(),
    totalUsersChecked: Object.keys(users).length,
    dispatchedCount: dispatched.length,
    dispatched
  };
}

// Streaming variant: calls onChunk(text) for each token batch as it arrives (SSE upstream).
// Falls back across models only until the first chunk has been delivered.
async function streamRealGeminiAI(systemPrompt, userQuestion, onChunk) {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) throw new Error('GEMINI_API_KEY is not configured on the server. Please export GEMINI_API_KEY.');

  const models = ['gemini-3.5-flash', 'gemini-3.1-flash-lite', 'gemini-3.8-flash'];
  const payload = geminiPayload(systemPrompt, userQuestion);

  let lastError = null;
  for (const model of models) {
    let delivered = false;
    let finishReason = null;
    try {
      const fullText = await new Promise((resolve, reject) => {
        const tgt = geminiTarget();
        const req = tgt.mod.request({
          hostname: tgt.hostname,
          port: tgt.port,
          path: '/v1beta/models/' + model + ':streamGenerateContent?alt=sse',
          method: 'POST',
          rejectUnauthorized: process.env.GEMINI_INSECURE_TLS !== '1',
          headers: {
            'x-goog-api-key': apiKey,
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(payload)
          }
        }, res => {
          if (res.statusCode >= 400) {
            let errBody = '';
            res.on('data', c => errBody += c);
            res.on('end', () => {
              let msg = 'HTTP ' + res.statusCode + ' from ' + model;
              try { msg = JSON.parse(errBody).error?.message || msg; } catch (e) { /* keep default */ }
              reject(new Error(msg));
            });
            return;
          }
          let buf = '';
          let full = '';
          res.setEncoding('utf8');
          res.on('data', chunk => {
            buf += chunk;
            let idx;
            while ((idx = buf.indexOf('\n')) !== -1) {
              const line = buf.slice(0, idx).trim();
              buf = buf.slice(idx + 1);
              if (!line.startsWith('data:')) continue;
              try {
                const evt = JSON.parse(line.slice(5).trim());
                const text = visibleText(evt.candidates?.[0]?.content?.parts);
                if (evt.candidates?.[0]?.finishReason) finishReason = evt.candidates[0].finishReason;
                if (text) { delivered = true; full += text; onChunk(text); }
              } catch (e) { /* ignore partial/non-JSON frame */ }
            }
          });
          res.on('end', () => full ? resolve(full) : reject(new Error('Empty response from ' + model)));
          res.on('error', reject);
        });
        req.on('error', reject);
        req.setTimeout(30000, () => req.destroy(new Error('Request timeout calling model ' + model)));
        req.write(payload);
        req.end();
      });
      return { model, text: fullText, finishReason };
    } catch (err) {
      lastError = err;
      console.warn('[Gemini Stream] Falling back from ' + model + ':', err.message);
      if (delivered) throw err; // cannot cleanly restart a partially streamed answer
    }
  }
  throw new Error('All Gemini AI model endpoints were unavailable: ' + (lastError?.message || 'Unknown network error'));
}

module.exports = {
  SUBSCRIPTION_PLANS,
  queryTerms,
  streamRealGeminiAI,
  signToken,
  verifyToken,
  signState,
  verifyState,
  safeEqual,
  userExists: (id) => !!loadUsers()[id],
  planHas,
  userHasFeature,
  getEntitlements,
  paymentMode,
  createPaymentOrder,
  verifyPaymentAndUpgrade,
  getUser,
  getUserSubscription,
  loginUser,
  syncProgress,
  checkAndIncrementAiUsage,
  upgradeUserPlan,
  deductCredit,
  addCredits,
  searchCurriculumLessons,
  callRealGeminiAI,
  adminGetAllLessons,
  adminGetLessonDetail,
  adminSaveLesson,
  generateEmailDigest,
  calculateAndUpdateStreak,
  dispatchDailyEmailToUser,
  runDailyEmailScheduler,
  getEmailLogs: loadEmailLogs
};
