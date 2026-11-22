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

const PORT = process.env.PORT || 5050;
const BASE_ORIGINAL_PROJECTS = 'C:\\YASH\\CODES\\YASHVARDHAN_FAANG\\AI-System_design_DSA\\PROJECTS';
const DATA_DIR = path.join(__dirname, 'data');
const PUBLIC_DIR = path.join(__dirname, 'public');
const PROGRESS_FILE = path.join(DATA_DIR, 'progress.json');
const ZIP_LABS_FILE = path.join(DATA_DIR, 'all_labs_source.zip');

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

// Helper: send JSON response
function sendJson(res, statusCode, data) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type'
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

// AI Mentor Knowledge Base & Response Engine
function generateMentorResponse(question, lessonId, trackId, lessonTitle, curriculum) {
  const qLower = question.toLowerCase();

  let response = '';

  if (qLower.includes('explain') || qLower.includes('simply') || qLower.includes('eli5') || qLower.includes('intuition')) {
    response = `### 💡 Core Intuition: **${lessonTitle || 'This Topic'}**\n\n` +
      `When FAANG interviewers test you on this, they aren't looking for textbook regurgitation. They test your ability to explain the underlying constraint that forces this architecture:\n\n` +
      `- **The Fundamental Trade-off:** Every design or algorithm in this chapter exists to solve an unacceptable physical boundary — either CPU cache limits, network packet round-trip time (RTT), or disk write amplification.\n` +
      `- **In Simple Terms:** Imagine a system where doing things naively leads to a catastrophic queue pile-up. By introducing this structure (whether it's indexed lookups, asynchronous outbox queues, or segmented token buckets), we decouple the bottleneck from the critical path.\n` +
      `- **What to Say in an Interview:** *"We choose this pattern specifically because under high concurrency, alternative approaches trigger lock contention or O(N) scans. This gives us predictable latency with bounded memory."*`;
  } else if (qLower.includes('trap') || qLower.includes('failure') || qLower.includes('mistake') || qLower.includes('wrong')) {
    response = `### ⚠️ Top Interview Trap: **${lessonTitle || 'This Problem'}**\n\n` +
      `Here is where 70% of candidates fail in L5 / Senior engineering rounds:\n\n` +
      `1. **Assuming Happy Paths Only:** Forgetting network partitions, packet drops, or mid-stream worker crashes. In distributed systems, if you assume atomic writes across two databases without an Outbox or 2PC, it is an instant disqualifier.\n` +
      `2. **Ignoring Memory / Compaction:** In DSA, not spotting memory limits on sparse coordinates; in databases, forgetting that append-only logs require tombstone compaction and autovacuum.\n` +
      `3. **The Silent Failure Mode:** Designing systems that fail-closed when business needs require fail-open (e.g. rate limiters failing closed can take down the entire login flow if Redis restarts).\n\n` +
      `*Senior Tip:* Always state the failure mode before the interviewer asks: *"Here is how this can degrade under load, and here is how our bulkhead contains the blast radius."*`;
  } else if (qLower.includes('code') || qLower.includes('implement') || qLower.includes('python')) {
    response = `### 💻 Production Implementation Blueprint\n\n` +
      `Here is the idiomatic, robust pattern expected in technical coding rounds:\n\n` +
      `\`\`\`python\n` +
      `# High-performance, clean structure for ${lessonTitle || 'the concept'}\n` +
      `from typing import Optional, List, Dict\n` +
      `import time\n\n` +
      `class Solution:\n` +
      `    def execute(self, items: List[int]) -> Dict[str, any]:\n` +
      `        # 1. Validate inputs and boundary constraints immediately\n` +
      `        if not items:\n` +
      `            return {"status": "empty", "result": 0}\n\n` +
      `        # 2. State tracking with O(1) indexed lookups\n` +
      `        seen = {}\n` +
      `        max_metric = 0\n\n` +
      `        # 3. Process invariants in a single pass\n` +
      `        for idx, val in enumerate(items):\n` +
      `            # Invariant: maintain bounds and check complement\n` +
      `            if val in seen:\n` +
      `                max_metric = max(max_metric, idx - seen[val])\n` +
      `            else:\n` +
      `                seen[val] = idx\n\n` +
      `        return {"status": "ok", "metric": max_metric}\n` +
      `\`\`\`\n\n` +
      `**Complexity Analysis:**\n` +
      `- **Time:** $O(N)$ single-pass traversal.\n` +
      `- **Space:** $O(N)$ auxiliary hash table state.`;
  } else if (qLower.includes('mock') || qLower.includes('question') || qLower.includes('grill') || qLower.includes('drill')) {
    response = `### 🎯 Senior FAANG Mock Drill: **${lessonTitle || 'Deep Dive'}**\n\n` +
      `Imagine you are in the 30th minute of your Google or Meta onsite round. I am your interviewer. Here is your scenario:\n\n` +
      `> *"We deployed your solution to production, but during Black Friday peak traffic, our p99 latency spiked from 35ms to 1,800ms while CPU utilization remained under 25%. Our database metrics show zero lock deadlocks."*\n\n` +
      `**Your Drill Questions:**\n` +
      `1. What is the most probable root cause? (Hint: Think connection pooling, thread pool starvation, or downstream TCP slow-start / head-of-line blocking).\n` +
      `2. What metric would you immediately pull up on your Datadog / Grafana dashboard to verify this hypothesis?\n` +
      `3. How would you adjust the configuration in under 2 minutes to restore traffic?\n\n` +
      `*Take 60 seconds. Reply with your step-by-step diagnostic breakdown!*`;
  } else {
    response = `### 🎓 FAANG Mentor Analysis: **${lessonTitle || 'Inquiry'}**\n\n` +
      `Great question regarding **${lessonTitle || 'this system'}**. Here is how to think about this at an L5/L6 Senior Staff level:\n\n` +
      `1. **First-Principles Framing:** When dealing with **"${question}"**, we must first clarify the throughput and SLA expectations. Is this a write-heavy or read-heavy path? What is our tolerance for stale data versus tail latency?\n\n` +
      `2. **The Production Architecture:**\n` +
      `   - Always separate the synchronous user-facing request path from asynchronous heavy computation.\n` +
      `   - Use caching layers with jittered TTLs to prevent thundering herd stampedes.\n` +
      `   - Wrap external dependencies with circuit breakers and fallback defaults.\n\n` +
      `3. **Key Interview Phrase to Use:**\n` +
      `   *"To guarantee our 99.99% availability target, we decouple this component using an idempotent message queue. If the downstream consumer falls behind, backpressure is absorbed in the Kafka partition rather than degrading user API threads."*\n\n` +
      `Feel free to ask for a code walkthrough, edge-case breakdown, or a mock follow-up question!`;
  }

  // Cross-Curriculum Deep-Linking Search:
  if (curriculum) {
    try {
      const related = cmsAuth.searchCurriculumLessons(question, curriculum).filter(r => r.id !== lessonId);
      if (related.length > 0) {
        response += `\n\n---\n**📚 Deep-Dive Recommendations in Curriculum:**\n` +
          related.map(r => `- [📖 **${r.title}** (${r.trackName})](#open-lesson-${r.id})`).join('\n');
      }
    } catch (e) {}
  }

  return response;
}

// Create HTTP server
const server = http.createServer(async (req, res) => {
  const parsedUrl = url.parse(req.url, true);
  const pathname = parsedUrl.pathname;

  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type'
    });
    res.end();
    return;
  }

  // --------------------------------------------------------------------------
  // Static Routing for Original Visuals & Course Assets
  // --------------------------------------------------------------------------
  if (pathname.startsWith('/projects/') ||
      pathname.startsWith('/dsa-faang-prep/') ||
      pathname.startsWith('/system-design-prep/') ||
      pathname.startsWith('/ai-master-prep/') ||
      pathname.startsWith('/behavioral-prep/')) {
    
    let subPath = pathname;
    if (subPath.startsWith('/projects/')) {
      subPath = subPath.substring('/projects/'.length);
    } else if (subPath.startsWith('/')) {
      subPath = subPath.substring(1);
    }

    const fullOriginalPath = path.join(BASE_ORIGINAL_PROJECTS, subPath);

    fs.stat(fullOriginalPath, (err, stats) => {
      if (!err && stats.isFile()) {
        const ext = path.extname(fullOriginalPath).toLowerCase();
        const contentType = MIME_TYPES[ext] || 'application/octet-stream';
        
        if (ext === '.html') {
          try {
            let html = fs.readFileSync(fullOriginalPath, 'utf8');
            const reqTheme = (parsedUrl.query && parsedUrl.query.theme) ? parsedUrl.query.theme : 'dark';
            
            // Set data-theme on html tag
            if (html.includes('<html')) {
              html = html.replace(/<html([^>]*)>/i, `<html$1 data-theme="${reqTheme}">`);
            }

            const embedStyle = `
<style id="algoarch-native-embed-theme">
  .rail, #themebtn, .eyebrow, .masthead { display: none !important; }
  .shell { display: block !important; grid-template-columns: 1fr !important; max-width: 100% !important; margin: 0 !important; width: 100% !important; }
  main { padding: 12px 18px 40px !important; max-width: 100% !important; margin: 0 !important; }
  body { background: transparent !important; color: var(--ink) !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important; }
  
  :root[data-theme="dark"], html[data-theme="dark"] {
    --bg: #0a0d12 !important;
    --panel: #151b23 !important;
    --panel-2: #1a222c !important;
    --panel-3: #222b37 !important;
    --ink: #e6edf3 !important;
    --ink-2: #8b949e !important;
    --muted: #6e7681 !important;
    --line: #21262d !important;
    --line-2: #30363d !important;
    --accent: #be2f27 !important;
    --accent-bg: rgba(190,47,39,0.18) !important;
    color-scheme: dark !important;
  }
  
  :root[data-theme="light"], html[data-theme="light"] {
    --bg: #f6f8fa !important;
    --panel: #ffffff !important;
    --panel-2: #f3f4f6 !important;
    --panel-3: #eaeef2 !important;
    --ink: #1f2328 !important;
    --ink-2: #57606a !important;
    --muted: #8c959f !important;
    --line: #d0d7de !important;
    --line-2: #afb8c1 !important;
    --accent: #be2f27 !important;
    --accent-bg: #fbeae8 !important;
    color-scheme: light !important;
  }
</style>
<script>
  (function() {
    function applyTheme(theme) {
      document.documentElement.setAttribute('data-theme', theme);
      if (document.body) document.body.setAttribute('data-theme', theme);
    }
    const params = new URLSearchParams(window.location.search);
    const initialTheme = params.get('theme') || localStorage.getItem('algoarch-theme') || '${reqTheme}';
    applyTheme(initialTheme);

    window.addEventListener('message', function(e) {
      if (e.data && e.data.theme) {
        applyTheme(e.data.theme);
      }
    });
  })();
</script>
`;
            if (html.includes('</head>')) {
              html = html.replace('</head>', `${embedStyle}</head>`);
            } else {
              html = embedStyle + html;
            }
            res.writeHead(200, {
              'Content-Type': 'text/html; charset=utf-8',
              'Access-Control-Allow-Origin': '*'
            });
            return res.end(html);
          } catch (e) {
            // fallback to streaming if reading fails
          }
        }

        res.writeHead(200, {
          'Content-Type': contentType,
          'Access-Control-Allow-Origin': '*'
        });
        fs.createReadStream(fullOriginalPath).pipe(res);
        return;
      }
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('404 Visual Asset Not Found');
    });
    return;
  }

  // --------------------------------------------------------------------------
  // API Endpoints
  // --------------------------------------------------------------------------

  // 1. GET /api/curriculum
  if (req.method === 'GET' && pathname === '/api/curriculum') {
    try {
      const curriculumPath = path.join(DATA_DIR, 'curriculum.json');
      const data = JSON.parse(fs.readFileSync(curriculumPath, 'utf8'));
      return sendJson(res, 200, data);
    } catch (e) {
      return sendJson(res, 500, { error: 'Failed to load curriculum', details: e.message });
    }
  }

  // 2. GET /api/videos
  if (req.method === 'GET' && pathname === '/api/videos') {
    try {
      const videosPath = path.join(DATA_DIR, 'videos.json');
      const data = JSON.parse(fs.readFileSync(videosPath, 'utf8'));
      return sendJson(res, 200, data);
    } catch (e) {
      return sendJson(res, 500, { error: 'Failed to load videos', details: e.message });
    }
  }

  // 3. GET /api/lesson
  if (req.method === 'GET' && pathname === '/api/lesson') {
    const lessonId = parsedUrl.query.id;
    const trackId = parsedUrl.query.track;

    if (!lessonId) {
      return sendJson(res, 400, { error: 'Missing lesson id' });
    }

    try {
      const curriculumPath = path.join(DATA_DIR, 'curriculum.json');
      const curriculum = JSON.parse(fs.readFileSync(curriculumPath, 'utf8'));

      // Find lesson in curriculum
      let targetLesson = null;
      let targetTrack = null;

      for (const t of curriculum.tracks) {
        if (!trackId || t.id === trackId) {
          for (const b of t.blocks) {
            for (const l of b.lessons) {
              if (l.id === lessonId) {
                targetLesson = l;
                targetTrack = t;
                break;
              }
            }
            if (targetLesson) break;
          }
        }
        if (targetLesson) break;
      }

      if (!targetLesson) {
        return sendJson(res, 404, { error: 'Lesson not found in catalog' });
      }

      // Check whether this is a newly created lesson or existing file
      let markdownContent = '';
      let isNew = targetLesson.isNew || false;

      if (isNew && targetLesson.newPath) {
        const fullNewPath = path.join(DATA_DIR, targetLesson.newPath);
        if (fs.existsSync(fullNewPath)) {
          markdownContent = fs.readFileSync(fullNewPath, 'utf8');
        }
      } else if (targetLesson.existingPath) {
        const fullOriginalPath = path.join(BASE_ORIGINAL_PROJECTS, targetLesson.existingPath);
        if (fs.existsSync(fullOriginalPath)) {
          markdownContent = fs.readFileSync(fullOriginalPath, 'utf8');
        }
      }

      // Sanitize markdown: remove internal git repo lines, diagnostics, broken relative URLs
      const cleanedMarkdown = sanitizeMarkdownContent(markdownContent);

      // Check for associated interactive visual page
      let visualUrl = null;
      if (targetLesson.visualPath) {
        visualUrl = `/projects/${targetLesson.visualPath}`;
      }

      // Check for associated runnable Python lab code
      let labCode = null;
      let labFileName = null;
      if (targetLesson.lab) {
        labFileName = targetLesson.lab;
        const labPath = path.join(BASE_ORIGINAL_PROJECTS, 'ai-master-prep', 'labs', targetLesson.lab);
        if (fs.existsSync(labPath)) {
          labCode = fs.readFileSync(labPath, 'utf8');
        }
      }

      // Curated Videos: ONLY section-related videos explicitly mapped to this lesson
      let lessonVideos = [];
      try {
        const allVideos = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'videos.json'), 'utf8'));
        lessonVideos = allVideos.filter(v => v.lessonLink === lessonId);
      } catch (e) {}

      // Curated Articles and Repositories for this track
      let lessonArticles = [];
      let lessonRepos = [];
      try {
        const resources = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'resources.json'), 'utf8'));
        const trackKey = targetTrack ? targetTrack.id : 'system-design';
        if (resources[trackKey]) {
          lessonArticles = resources[trackKey].defaultArticles || [];
          lessonRepos = resources[trackKey].defaultRepos || [];
        }
      } catch (e) {}

      // Extract homework & drill prompts from markdown
      const drillItems = [];
      const drillMatch = cleanedMarkdown.match(/##\s+(?:(?:\d+\.\s*)?(?:Drills|Homework|Mock Drills|Practice Exercises)[\s\S]*)/i);
      if (drillMatch) {
        const lines = drillMatch[0].split('\n');
        let currentItem = null;
        for (const line of lines) {
          const m = line.match(/^(\d+\.|\*|-)\s+(.*)/);
          if (m) {
            if (currentItem) drillItems.push(currentItem);
            currentItem = { title: m[2].trim(), notes: '' };
          } else if (currentItem && line.trim()) {
            currentItem.notes += (currentItem.notes ? ' ' : '') + line.trim();
          }
        }
        if (currentItem) drillItems.push(currentItem);
      }

      return sendJson(res, 200, {
        lesson: targetLesson,
        track: targetTrack ? { id: targetTrack.id, name: targetTrack.name, color: targetTrack.color } : null,
        content: cleanedMarkdown,
        visualUrl: visualUrl,
        labCode: labCode,
        labFileName: labFileName,
        videos: lessonVideos,
        articles: lessonArticles,
        repos: lessonRepos,
        drills: drillItems.slice(0, 10)
      });
    } catch (e) {
      return sendJson(res, 500, { error: 'Failed to read lesson content', details: e.message });
    }
  }

  // 4. GET /api/download/all-labs.zip
  if (req.method === 'GET' && pathname === '/api/download/all-labs.zip') {
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

  // 5. GET /api/download/lab
  if (req.method === 'GET' && pathname === '/api/download/lab') {
    const fileName = parsedUrl.query.file;
    if (!fileName) return sendJson(res, 400, { error: 'Missing file parameter' });

    const safeName = path.basename(fileName);
    const labPath = path.join(BASE_ORIGINAL_PROJECTS, 'ai-master-prep', 'labs', safeName);

    if (fs.existsSync(labPath)) {
      res.writeHead(200, {
        'Content-Type': 'text/x-python; charset=utf-8',
        'Content-Disposition': `attachment; filename="${safeName}"`
      });
      fs.createReadStream(labPath).pipe(res);
      return;
    }
    return sendJson(res, 404, { error: 'Lab source file not found' });
  }

  // 6. POST /api/chat (Production Real Gemini AI Mentor with Subscription Gate)
  if (req.method === 'POST' && pathname === '/api/chat') {
    try {
      const body = await parseBody(req);
      const question = body.question || body.message || '';
      const lessonId = body.lessonId || '';
      const trackId = body.trackId || '';
      const lessonTitle = body.lessonTitle || '';
      const userId = body.userId || req.headers['x-algoarch-user'] || 'guest_default';

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

      const curriculum = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'curriculum.json'), 'utf8'));
      const startTime = Date.now();

      // 2. Real Gemini AI Mentor Prompt Formulation
      const sysPrompt = `You are the Lead Principal FAANG Technical Interview Mentor at AlgoArch.
You guide senior and staff software engineering candidates preparing for ₹50 LPA to ₹80+ LPA (L5/L6) rounds at Google, Meta, Amazon, Netflix, and Apple.
Current lesson context: "${lessonTitle || 'Technical Inquiry'}" (Track: ${trackId || 'General'}).

Respond with:
1. First-principles technical clarity (no fluff or generic textbook filler).
2. Concrete time & space complexity invariants.
3. Edge cases and production failure modes (what breaks under scale/load).
4. Idiomatic, typed code blueprints (Python or Go) when relevant.
5. First-rate trade-off analysis.`;

      let reply = '';
      let modelUsed = 'gemini-3.5-flash';
      try {
        const geminiRes = await cmsAuth.callRealGeminiAI(sysPrompt, question);
        reply = geminiRes.text;
        modelUsed = geminiRes.model;

        // Auto-recommend relevant cross-curriculum chapters
        const related = cmsAuth.searchCurriculumLessons(question, curriculum).filter(r => r.id !== lessonId);
        if (related.length > 0) {
          reply += `\n\n---\n**📚 Recommended Deep-Dive Lessons in Curriculum:**\n` +
            related.map(r => `- [📖 **${r.title}** (${r.trackName})](#open-lesson-${r.id})`).join('\n');
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
    const userId = parsedUrl.query.userId || req.headers['x-algoarch-user'] || 'guest_default';
    const sub = cmsAuth.getUserSubscription(userId);
    return sendJson(res, 200, sub);
  }

  if (pathname === '/api/subscription/upgrade' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      const userId = body.userId || req.headers['x-algoarch-user'] || 'guest_default';
      const plan = body.plan || 'pro';
      const result = cmsAuth.upgradeUserPlan(userId, plan);
      return sendJson(res, 200, result);
    } catch (e) {
      return sendJson(res, 500, { error: e.message });
    }
  }

  // --------------------------------------------------------------------------
  // AUTH & USER APIs
  // --------------------------------------------------------------------------
  if (pathname === '/api/auth/login' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      const result = cmsAuth.loginUser(body);
      return sendJson(res, 200, result);
    } catch (e) {
      return sendJson(res, 500, { error: e.message });
    }
  }

  if (pathname === '/api/auth/me' && req.method === 'GET') {
    const userId = parsedUrl.query.userId || req.headers['x-algoarch-user'] || 'guest_default';
    const user = cmsAuth.getUser(userId);
    return sendJson(res, 200, { user });
  }

  if (pathname === '/api/user/sync-progress' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      const userId = body.userId || req.headers['x-algoarch-user'] || 'guest_default';
      const updated = cmsAuth.syncProgress(userId, body);
      return sendJson(res, 200, { success: true, user: updated });
    } catch (e) {
      return sendJson(res, 500, { error: e.message });
    }
  }

  if (pathname === '/api/user/add-credits' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      const userId = body.userId || 'guest_default';
      const updated = cmsAuth.addCredits(userId, body.amount || 10);
      return sendJson(res, 200, { success: true, credits: updated.credits });
    } catch (e) {
      return sendJson(res, 500, { error: e.message });
    }
  }

  // --------------------------------------------------------------------------
  // ADMIN CMS APIs
  // --------------------------------------------------------------------------
  if (pathname === '/api/admin/lessons' && req.method === 'GET') {
    try {
      const curriculum = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'curriculum.json'), 'utf8'));
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
      const curriculum = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'curriculum.json'), 'utf8'));
      const detail = cmsAuth.adminGetLessonDetail(lessonId, curriculum, BASE_ORIGINAL_PROJECTS);
      if (!detail) return sendJson(res, 404, { error: 'Lesson not found' });
      return sendJson(res, 200, detail);
    } catch (e) {
      return sendJson(res, 500, { error: e.message });
    }
  }

  if (pathname === '/api/admin/save-lesson' && req.method === 'POST') {
    try {
      const body = await parseBody(req);
      const curriculum = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'curriculum.json'), 'utf8'));
      const result = cmsAuth.adminSaveLesson(body, curriculum, BASE_ORIGINAL_PROJECTS);
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
      const userId = body.userId || req.headers['x-algoarch-user'] || 'guest_default';
      const user = cmsAuth.getUser(userId);
      const curriculum = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'curriculum.json'), 'utf8'));
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
      const curriculum = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'curriculum.json'), 'utf8'));
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
        const userId = req.headers['x-algoarch-user'] || 'guest_default';
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
      const curriculum = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'curriculum.json'), 'utf8'));
      const videos = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'videos.json'), 'utf8'));
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
    const curriculumPath = path.join(DATA_DIR, 'curriculum.json');
    if (fs.existsSync(curriculumPath)) {
      const curriculum = JSON.parse(fs.readFileSync(curriculumPath, 'utf8'));
      cmsAuth.runDailyEmailScheduler(curriculum, false);
    }
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
