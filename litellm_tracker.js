// ============================================================================
// LiteLLM Gateway & Token Tracking Engine
// Tracks prompt tokens, completion tokens, costs, user budgets & admin limits
// ============================================================================

const fs = require('fs');
const path = require('path');

const DATA_DIR = process.env.ALGOARCH_DATA_DIR || path.join(__dirname, 'data');
const USAGE_FILE = path.join(DATA_DIR, 'token_usage.json');

// Standard Model Pricing (per 1,000,000 tokens USD)
const MODEL_PRICING = {
  'gemini-1.5-flash': { prompt: 0.075, completion: 0.30 },
  'gemini-1.5-pro': { prompt: 1.25, completion: 5.00 },
  'gpt-4o-mini': { prompt: 0.15, completion: 0.60 },
  'gpt-4o': { prompt: 2.50, completion: 10.00 },
  'claude-3-5-sonnet': { prompt: 3.00, completion: 15.00 },
  'default': { prompt: 0.15, completion: 0.60 }
};

const DEFAULT_USER_TOKEN_LIMIT = 25000; // 25k tokens default free pool (~10-15 deep technical queries)

function loadUsageData() {
  try {
    if (fs.existsSync(USAGE_FILE)) {
      return JSON.parse(fs.readFileSync(USAGE_FILE, 'utf8'));
    }
  } catch (e) {}
  return {
    global: {
      total_tokens: 0,
      prompt_tokens: 0,
      completion_tokens: 0,
      total_cost_usd: 0,
      total_requests: 0,
      default_limit: DEFAULT_USER_TOKEN_LIMIT
    },
    users: {},
    logs: []
  };
}

function saveUsageData(data) {
  try {
    fs.writeFileSync(USAGE_FILE, JSON.stringify(data, null, 2), 'utf8');
  } catch (e) {}
}

// BPE / Tokenizer estimation (~4 chars or 0.75 words per token)
function estimateTokens(text) {
  if (!text) return 0;
  const charTokens = Math.ceil(text.length / 3.8);
  const wordTokens = Math.ceil(text.trim().split(/\s+/).length * 1.3);
  return Math.max(1, Math.round((charTokens + wordTokens) / 2));
}

function calculateCost(model, promptTokens, completionTokens) {
  const pricing = MODEL_PRICING[model] || MODEL_PRICING['default'];
  const promptCost = (promptTokens / 1000000) * pricing.prompt;
  const completionCost = (completionTokens / 1000000) * pricing.completion;
  return parseFloat((promptCost + completionCost).toFixed(6));
}

function checkBudget(userId, hasCustomKey = false) {
  const data = loadUsageData();
  const user = data.users[userId] || {
    tokens_used: 0,
    token_limit: data.global.default_limit || DEFAULT_USER_TOKEN_LIMIT,
    is_blocked: false
  };

  if (hasCustomKey) {
    return {
      allowed: true,
      hasCustomKey: true,
      tokens_used: user.tokens_used,
      token_limit: 'Unlimited (Custom API Key)',
      remaining: 'Unlimited'
    };
  }

  if (user.is_blocked) {
    return {
      allowed: false,
      reason: 'User account has been administratively paused.',
      tokens_used: user.tokens_used,
      token_limit: user.token_limit,
      remaining: 0
    };
  }

  const remaining = Math.max(0, user.token_limit - user.tokens_used);
  const allowed = remaining > 150; // Enough for at least a short response

  return {
    allowed,
    tokens_used: user.tokens_used,
    token_limit: user.token_limit,
    remaining,
    reason: allowed ? null : `Token limit of ${user.token_limit.toLocaleString()} tokens exceeded.`
  };
}

function trackUsage({ userId, userName, userEmail, model = 'gemini-1.5-flash', promptText, completionText, latencyMs = 240, hasCustomKey = false }) {
  const data = loadUsageData();

  const promptTokens = estimateTokens(promptText);
  const completionTokens = estimateTokens(completionText);
  const totalTokens = promptTokens + completionTokens;
  const costUsd = calculateCost(model, promptTokens, completionTokens);

  // Initialize or update user record
  if (!data.users[userId]) {
    data.users[userId] = {
      id: userId,
      name: userName || 'Candidate',
      email: userEmail || `${userId}@algoarch.io`,
      tokens_used: 0,
      token_limit: data.global.default_limit || DEFAULT_USER_TOKEN_LIMIT,
      total_cost_usd: 0,
      total_calls: 0,
      is_blocked: false,
      created_at: new Date().toISOString(),
      last_active: new Date().toISOString()
    };
  }

  const u = data.users[userId];
  u.tokens_used += totalTokens;
  u.total_cost_usd = parseFloat((u.total_cost_usd + costUsd).toFixed(6));
  u.total_calls += 1;
  u.last_active = new Date().toISOString();
  if (userName) u.name = userName;
  if (userEmail) u.email = userEmail;

  // Update platform global totals
  data.global.total_tokens += totalTokens;
  data.global.prompt_tokens += promptTokens;
  data.global.completion_tokens += completionTokens;
  data.global.total_cost_usd = parseFloat((data.global.total_cost_usd + costUsd).toFixed(6));
  data.global.total_requests += 1;

  // Append to LiteLLM trace audit logs (keep last 300)
  const logEntry = {
    id: 'req_' + Date.now() + Math.random().toString(36).substring(2, 6),
    timestamp: new Date().toISOString(),
    userId,
    userName: u.name,
    model,
    prompt_tokens: promptTokens,
    completion_tokens: completionTokens,
    total_tokens: totalTokens,
    cost_usd: costUsd,
    latency_ms: latencyMs,
    custom_key: hasCustomKey,
    query_snippet: (promptText || '').substring(0, 80)
  };

  data.logs.unshift(logEntry);
  if (data.logs.length > 300) {
    data.logs = data.logs.slice(0, 300);
  }

  saveUsageData(data);

  return {
    prompt_tokens: promptTokens,
    completion_tokens: completionTokens,
    total_tokens: totalTokens,
    cost_usd: costUsd,
    user_tokens_used: u.tokens_used,
    user_token_limit: hasCustomKey ? 'Unlimited' : u.token_limit,
    remaining_tokens: hasCustomKey ? 'Unlimited' : Math.max(0, u.token_limit - u.tokens_used)
  };
}

// --------------------------------------------------------------------------
// Admin Controls
// --------------------------------------------------------------------------
function adminSetUserLimit(userId, newLimit) {
  const data = loadUsageData();
  if (!data.users[userId]) {
    data.users[userId] = {
      id: userId,
      tokens_used: 0,
      token_limit: parseInt(newLimit) || DEFAULT_USER_TOKEN_LIMIT,
      total_cost_usd: 0,
      total_calls: 0,
      is_blocked: false,
      last_active: new Date().toISOString()
    };
  } else {
    data.users[userId].token_limit = parseInt(newLimit);
  }
  saveUsageData(data);
  return data.users[userId];
}

function adminResetUserUsage(userId) {
  const data = loadUsageData();
  if (data.users[userId]) {
    data.users[userId].tokens_used = 0;
    data.users[userId].is_blocked = false;
    saveUsageData(data);
    return data.users[userId];
  }
  return null;
}

function adminToggleUserBlock(userId) {
  const data = loadUsageData();
  if (data.users[userId]) {
    data.users[userId].is_blocked = !data.users[userId].is_blocked;
    saveUsageData(data);
    return data.users[userId];
  }
  return null;
}

function adminResetAllUsage() {
  const data = loadUsageData();
  data.global.total_tokens = 0;
  data.global.prompt_tokens = 0;
  data.global.completion_tokens = 0;
  data.global.total_cost_usd = 0;
  data.global.total_requests = 0;
  for (const uid in data.users) {
    data.users[uid].tokens_used = 0;
    data.users[uid].is_blocked = false;
  }
  data.logs = [];
  saveUsageData(data);
  return { success: true };
}

function adminSetDefaultLimit(newLimit) {
  const data = loadUsageData();
  data.global.default_limit = parseInt(newLimit) || DEFAULT_USER_TOKEN_LIMIT;
  saveUsageData(data);
  return { success: true, default_limit: data.global.default_limit };
}

function getPlatformSummary() {
  const data = loadUsageData();
  const usersList = Object.values(data.users).sort((a, b) => b.tokens_used - a.tokens_used);
  return {
    global: data.global,
    users: usersList,
    recentLogs: data.logs.slice(0, 40)
  };
}

module.exports = {
  checkBudget,
  trackUsage,
  estimateTokens,
  adminSetUserLimit,
  adminResetUserUsage,
  adminToggleUserBlock,
  adminResetAllUsage,
  adminSetDefaultLimit,
  getPlatformSummary,
  DEFAULT_USER_TOKEN_LIMIT
};
