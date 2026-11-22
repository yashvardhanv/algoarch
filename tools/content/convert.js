// Converts one lesson page (HTML) into a presentation-agnostic Lesson Document (schema v1).
// Output contains only data: typed blocks + an inline AST. No HTML, no CSS classes, no scripts.
const vm = require('vm');
const { buildFramesData } = require('./frames');
const { parse, find, findOne, textOf, hasClass } = require('./minidom');
const { extractTraces, extractChecklist, extractScorecard } = require('./extract');

const SCHEMA_VERSION = 1;

// ---------------------------------------------------------------- inline AST
const INLINE_MAP = { b: 'strong', strong: 'strong', i: 'em', em: 'em', code: 'code', kbd: 'kbd', q: 'quote', sub: 'sub', sup: 'sup' };

function inline(nodes, out = []) {
  for (const n of nodes) {
    if (n.type === 'text') {
      const t = n.text.replace(/\s+/g, ' ');
      if (t) out.push(t);
      continue;
    }
    if (n.tag === 'br') { out.push({ t: 'br' }); continue; }
    if (['script', 'style', 'svg', 'button', 'input', 'select', 'textarea', 'label'].includes(n.tag)) continue;
    let type = INLINE_MAP[n.tag];
    if (n.tag === 'span' && hasClass(n, 'phrase')) type = 'phrase';
    if (n.tag === 'a') {
      const href = n.attrs.href || '';
      const safe = /^(https?:\/\/|\/|#)/i.test(href);
      const kids = inline(n.children);
      if (safe && href.startsWith('http')) out.push({ t: 'link', href, c: kids });
      else out.push(...kids);
      continue;
    }
    const kids = inline(n.children);
    if (type) out.push({ t: type, c: kids });
    else out.push(...kids);
  }
  return trimInline(out);
}

function trimInline(arr) {
  if (typeof arr[0] === 'string') arr[0] = arr[0].replace(/^\s+/, '');
  const last = arr.length - 1;
  if (last >= 0 && typeof arr[last] === 'string') arr[last] = arr[last].replace(/\s+$/, '');
  return arr.filter(x => x !== '');
}

const plain = (el) => textOf(el).replace(/\s+/g, ' ').trim();

// -------------------------------------------------------------------- blocks
const CONTAINER_CARD = ['gitem', 'pair', 'termdef', 'crow', 'ctrack', 'spec', 'seg'];
const SKIP_TAGS = new Set(['script', 'style', 'svg', 'button', 'input', 'select', 'textarea', 'label', 'canvas', 'nav', 'aside', 'header', 'footer', 'iframe']);

function blocks(children, stats) {
  const out = [];
  let loose = [];
  const flushLoose = () => {
    const inl = inline(loose);
    if (inl.length) out.push({ type: 'paragraph', content: inl });
    loose = [];
  };
  for (const n of children) {
    if (n.type === 'text') { loose.push(n); continue; }
    const tag = n.tag;
    if (['span', 'b', 'strong', 'em', 'i', 'code', 'a', 'q', 'kbd', 'br', 'sub', 'sup'].includes(tag)) { loose.push(n); continue; }
    flushLoose();
    if (SKIP_TAGS.has(tag)) { stats.dropped[tag] = (stats.dropped[tag] || 0) + 1; continue; }

    if (tag === 'p') { const c = inline(n.children); if (c.length) out.push({ type: 'paragraph', content: c }); continue; }
    if (tag === 'h3' || tag === 'h4') { out.push({ type: 'heading', level: tag === 'h3' ? 3 : 4, content: inline(n.children) }); continue; }
    if (tag === 'ul' || tag === 'ol') { out.push(list(n, stats)); continue; }
    if (tag === 'pre') {
      out.push({ type: 'code', text: textOf(n).replace(/^\n+|\s+$/g, ''), tone: hasClass(n, 'good') ? 'good' : hasClass(n, 'bad') ? 'bad' : null });
      continue;
    }
    if (tag === 'table') { out.push(table(n)); continue; }
    if (tag === 'details') {
      const summary = findOne(n, e => e.tag === 'summary');
      const body = n.children.filter(c => c !== summary);
      out.push({ type: 'qa', summary: summary ? inline(summary.children) : [], blocks: blocks(unwrap(body), stats) });
      continue;
    }
    if (tag === 'blockquote') { out.push({ type: 'quote', content: inline(n.children) }); continue; }
    if (tag === 'hr') continue;

    // div-like containers carrying meaning through class names
    if (hasClass(n, 'tw')) { const t = findOne(n, e => e.tag === 'table'); if (t) out.push(table(t)); continue; }
    if (hasClass(n, 'callout')) { out.push(callout(n, stats)); continue; }
    if (hasClass(n, 'say')) {
      const lbl = findOne(n, e => hasClass(e, 'lbl'));
      const q = findOne(n, e => e.tag === 'q');
      out.push({ type: 'say', label: lbl ? plain(lbl) : null, content: inline((q || n).children.filter(c => c !== lbl)) });
      continue;
    }
    if (hasClass(n, 'trig')) {
      const head = findOne(n, e => hasClass(e, 'trig-head'));
      const body = findOne(n, e => hasClass(e, 'trig-body'));
      out.push({ type: 'card', tone: hasClass(n, 'no') ? 'negative' : 'positive', title: head ? plain(head) : null, blocks: blocks(unwrap(body ? body.children : []), stats) });
      continue;
    }
    if (hasClass(n, 'panel')) { out.push(widget(n, 'simulation', stats)); continue; }
    if (hasClass(n, 'cell')) { out.push(codeCell(n)); continue; }
    if (hasClass(n, 'drill')) { out.push(widget(n, 'quiz', stats)); continue; }
    if (CONTAINER_CARD.some(c => hasClass(n, c))) {
      const inner = blocks(unwrap(n.children), stats);
      if (inner.length) out.push({ type: 'card', tone: 'neutral', title: null, blocks: inner });
      continue;
    }
    if (hasClass(n, 'diag') || hasClass(n, 'flow') || hasClass(n, 'tree')) {
      const t = textOf(n).replace(/^\n+|\s+$/g, '');
      if (t.trim()) out.push({ type: 'code', text: t, tone: null, diagram: true });
      continue;
    }
    if (n.attrs.id && traceMounts.has(n.attrs.id)) {
      stats.widgets.trace = (stats.widgets.trace || 0) + 1;
      const cfg = capturedTraces.get(n.attrs.id);
      const data = cfg && Array.isArray(cfg.frames) && cfg.frames.length ? {
        values: (typeof cfg.values === 'string' ? cfg.values.split('') : cfg.values).map(String),
        frames: cfg.frames.map(f => ({ ptrs: f.ptrs || {}, win: f.win || null, marks: f.marks || {}, note: f.note || '', stat: fragment(f.stat || '') }))
      } : null;
      out.push({ type: 'widget', kind: data ? 'trace' : 'simulation', archetype: 'trace', inputs: null, title: traceMounts.get(n.attrs.id), description: 'Step-through trace', blocks: [], ported: !!data, ...(data ? { data } : {}) });
      continue;
    }
    // unknown container: flatten
    out.push(...blocks(unwrap(n.children), stats));
  }
  flushLoose();
  return out;
}

const unwrap = (nodes) => nodes;

function list(n, stats) {
  return {
    type: 'list',
    ordered: n.tag === 'ol',
    items: n.children.filter(c => c.type === 'element' && c.tag === 'li').map(li => {
      const nested = li.children.filter(c => c.type === 'element' && (c.tag === 'ul' || c.tag === 'ol'));
      const rest = li.children.filter(c => !nested.includes(c));
      return { content: inline(rest), children: nested.map(x => list(x, stats)) };
    })
  };
}

function table(t) {
  const rows = find(t, e => e.tag === 'tr');
  const cells = (tr) => tr.children.filter(c => c.type === 'element' && (c.tag === 'td' || c.tag === 'th')).map(c => inline(c.children));
  const headRow = rows.find(r => r.children.some(c => c.type === 'element' && c.tag === 'th'));
  return {
    type: 'table',
    head: headRow ? cells(headRow) : null,
    rows: rows.filter(r => r !== headRow).map(cells).filter(r => r.length)
  };
}

function callout(n, stats) {
  const lbl = findOne(n, e => hasClass(e, 'lbl'));
  const tone = hasClass(n, 'danger') ? 'danger' : hasClass(n, 'info') ? 'info' : hasClass(n, 'ok') ? 'success' : 'warning';
  return { type: 'callout', tone, label: lbl ? plain(lbl) : null, blocks: blocks(n.children.filter(c => c !== lbl), stats) };
}

function dedent(text) {
  const lines = text.replace(/\t/g, '    ').split('\n');
  while (lines.length && !lines[0].trim()) lines.shift();
  while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
  let min = Infinity;
  for (const l of lines) if (l.trim()) min = Math.min(min, l.length - l.replace(/^ +/, '').length);
  if (!Number.isFinite(min)) min = 0;
  return lines.map(l => l.slice(min)).join('\n');
}

function scriptText(n, cls) {
  const s = findOne(n, e => e.tag === 'script' && hasClass(e, cls));
  return s ? dedent(textOf(s)) : '';
}

// Pulls a quiz's question bank out of the page script as plain data (evaluated in an empty sandbox).
function scanLiteralEnd(src, start) {
  let depth = 0, quote = null;
  for (let i = start; i < src.length; i++) {
    const ch = src[i];
    if (quote) { if (ch === '\\') i++; else if (ch === quote) quote = null; continue; }
    if (ch === "'" || ch === '"' || ch === '`') { quote = ch; continue; }
    if (ch === '[' || ch === '{') depth++;
    if (ch === ']' || ch === '}') { depth--; if (depth === 0) return i + 1; }
  }
  return -1;
}

// HTML snippet (from page data) -> inline AST
function fragment(h) {
  return inline(parse('<div>' + String(h == null ? '' : h) + '</div>').children[0].children);
}

function extractQuiz(html) {
  const scripts = [...html.matchAll(/<script(?![^>]*src=)[^>]*>([\s\S]*?)<\/script>/gi)].map(m => m[1]);
  const src = scripts.find(s => /var\s+BANK\s*=/.test(s) && /var\s+PATTERNS\s*=/.test(s));
  if (!src) return null;
  const start = src.search(/var\s+PATTERNS\s*=/);
  const bankAt = src.search(/var\s+BANK\s*=/);
  const open = src.indexOf('[', bankAt);
  const end = scanLiteralEnd(src, open);
  if (start < 0 || end < 0) return null;
  let data;
  try { data = vm.runInNewContext(src.slice(start, end) + ';({ PATTERNS: PATTERNS, CORE: typeof CORE === "undefined" ? PATTERNS : CORE, BANK: BANK })', {}, { timeout: 1000 }); }
  catch (e) { return null; }
  const frag = fragment;
  return {
    patterns: data.PATTERNS, core: data.CORE,
    bank: data.BANK.map(q => ({ statement: frag(q.s), constraint: q.c === '\u2014' ? '' : q.c, answer: q.p, why: frag(q.w) }))
  };
}

function codeCell(n) {
  const ttl = findOne(n, e => hasClass(e, 'ttl'));
  const ta = findOne(n, e => e.tag === 'textarea');
  return {
    type: 'code_cell',
    title: n.attrs['data-title'] || (ttl ? plain(ttl) : 'Code'),
    badge: n.attrs['data-badge'] || null,
    language: 'python',
    starter: scriptText(n, 'src') || (ta ? textOf(ta).replace(/^\n+|\s+$/g, '') : ''),
    tests: scriptText(n, 'tests')
  };
}

// Behavioural grouping of an interactive panel, inferred from the controls it exposes.
//   trace            companion view of a step-through trace
//   checklist        click items to score yourself
//   parameter-model  sliders/selects drive computed outputs (formula, bars, verdict)
//   simulation       buttons drive a stateful, step-by-step scenario
//   static-reference nothing to operate: tables or readouts only
function classifyPanel(n, title) {
  const count = (pred) => find(n, pred).length;
  const ranges = count(e => e.tag === 'input' && e.attrs.type === 'range');
  const selects = count(e => e.tag === 'select');
  const buttons = find(n, e => e.tag === 'button').filter(b => !/reset|clear/i.test(textOf(b))).length;
  const texts = count(e => e.tag === 'input' && (!e.attrs.type || e.attrs.type === 'text'));
  const inputs = { ranges, selects, buttons, texts };
  const t = (title || '').toLowerCase();
  let archetype;
  if (/follows the trace/.test(t) || count(e => hasClass(e, 'tr-cells')) > 0) archetype = 'trace';
  else if (/rubric|click what you|checklist/.test(t)) archetype = 'checklist';
  else if (ranges + selects + texts > 0 && buttons <= 1) archetype = /\b(real|measured)\b/.test(t) ? 'measured-data' : 'parameter-model';
  else if (buttons > 0) archetype = 'simulation';
  else archetype = /\b(real|measured)\b/.test(t) ? 'measured-data' : 'static-reference';
  return { archetype, inputs };
}

// Recorded panel states from the original page (capture-driver.js), matched by title in page order.
let currentCapture = null;
const normTitle = (s) => String(s || '').replace(/\s+/g, ' ').replace(/\u00a0/g, ' ').trim().toLowerCase();
function takeCapture(title) {
  if (!currentCapture) return null;
  const want = normTitle(title);
  const hit = currentCapture.find(p => !p._used && normTitle(p.title) === want);
  if (hit) hit._used = true;
  return hit || null;
}

function widget(n, kind, stats) {
  const bar = findOne(n, e => hasClass(e, 'panel-bar') || hasClass(e, 'drill-bar'));
  const note = findOne(n, e => hasClass(e, 'panel-note'));
  const staticBlocks = [];
  const body = findOne(n, e => hasClass(e, 'panel-body'));
  if (body) {
    for (const b of blocks(body.children, stats)) if (['paragraph', 'list', 'table', 'code', 'callout'].includes(b.type)) staticBlocks.push(b);
  }
  stats.widgets[kind] = (stats.widgets[kind] || 0) + 1;
  const quiz = kind === 'quiz' ? extractQuiz(currentHtml) : null;
  const cls = kind === 'simulation' ? classifyPanel(n, bar ? plain(bar) : '') : { archetype: kind, inputs: null };
  let title = kind === 'quiz' ? 'Timed drill' : (bar ? plain(bar) : null);
  let outKind = kind, data = quiz, ported = !!quiz;
  if (cls.archetype === 'checklist') {
    const sc = /7 axes/.test(title || '') ? extractScorecard(currentHtml) : null;
    const cl = sc ? null : extractChecklist(currentHtml);
    if (sc) { outKind = 'scorecard'; data = sc; ported = true; }
    else if (cl && cl.parsed) {
      outKind = 'checklist';
      data = { items: cl.items, deductions: cl.deductions, max: cl.max, bands: cl.bands, verdicts: cl.verdicts.map(v => ({ min: v.min, tone: v.tone, content: fragment(v.html) })) };
      ported = true;
    }
  }
  if (!ported && cls.archetype !== 'trace' && currentCapture) {
    const cap = takeCapture(bar ? textOf(bar) : title);
    const fd = cap ? buildFramesData(cap, currentScope) : null;
    if (fd) { outKind = 'frames'; data = fd; ported = true; staticBlocks.length = 0; if (cap.label) title = cap.label; }
  }
  return { type: 'widget', kind: outKind, archetype: cls.archetype, inputs: cls.inputs, title, description: note ? plain(note) : null, blocks: staticBlocks, ported, ...(data ? { data } : {}) };
}

// ------------------------------------------------------------------ document
let currentHtml = '';
let traceMounts = new Map();
let capturedTraces = new Map();
let currentScope = '';
function convertPage(html, capture) {
  currentHtml = html;
  currentScope = capture && capture.page ? capture.page.replace(/\.html$/, '').split('/').filter((x, i, a) => i !== a.length - 2).join('-').replace(/[^\w-]/g, '-') : '';
  currentCapture = capture && Array.isArray(capture.panels) ? capture.panels.map(p => ({ ...p })) : null;
  traceMounts = new Map();
  capturedTraces = new Map(extractTraces(html).map(t => [String(t.mount).replace(/^#/, ''), t]));
  for (const m of html.matchAll(/DSA\.trace\(\s*\{\s*mount:\s*['"]#([\w-]+)['"]\s*,\s*title:\s*(['"])([\s\S]*?)\2/g)) traceMounts.set(m[1], m[3]);
  const root = parse(html);
  const stats = { dropped: {}, widgets: {} };
  const main = findOne(root, e => e.tag === 'main') || root;
  const h1 = findOne(main, e => e.tag === 'h1');
  const lede = findOne(main, e => hasClass(e, 'lede'));
  const sections = find(main, e => e.tag === 'section').map((s, i) => {
    const head = findOne(s, e => hasClass(e, 'sec-head'));
    const num = head ? findOne(head, e => hasClass(e, 'num')) : null;
    const h2 = head ? findOne(head, e => e.tag === 'h2') : findOne(s, e => e.tag === 'h2');
    const sub = head ? findOne(head, e => hasClass(e, 'sub')) : null;
    const rest = s.children.filter(c => c !== head);
    return {
      anchor: s.attrs.id || `s${i + 1}`,
      number: num ? plain(num) : null,
      title: h2 ? plain(h2) : `Section ${i + 1}`,
      subtitle: sub ? plain(sub) : null,
      blocks: blocks(rest, stats)
    };
  });
  return {
    schemaVersion: SCHEMA_VERSION,
    title: h1 ? plain(h1) : null,
    lede: lede ? inline(lede.children) : [],
    sections,
    stats
  };
}

module.exports = { convertPage, SCHEMA_VERSION };
