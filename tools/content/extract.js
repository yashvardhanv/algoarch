// Extracts interactive-widget DATA from the original lesson page scripts (import-time only).
// Everything runs in an empty vm sandbox with a timeout. Nothing from the page reaches the runtime.
const vm = require('vm');

const inlineScripts = (html) => [...html.matchAll(/<script(?![^>]*\bsrc=)(?![^>]*x-python)[^>]*>([\s\S]*?)<\/script>/gi)].map(m => m[1]).join('\n');

function scanBalanced(src, start) {
  let depth = 0, quote = null;
  for (let i = start; i < src.length; i++) {
    const ch = src[i];
    if (quote) { if (ch === '\\') i++; else if (ch === quote) quote = null; continue; }
    if (ch === "'" || ch === '"' || ch === '`') { quote = ch; continue; }
    if (ch === '[' || ch === '{' || ch === '(') depth++;
    if (ch === ']' || ch === '}' || ch === ')') { depth--; if (depth === 0) return i + 1; }
  }
  return -1;
}

const evalData = (expr, ctx = {}) => vm.runInNewContext('(' + expr + ')', ctx, { timeout: 1000 });

// ------------------------------------------------------------------ traces
// A universal stub: any property read, call or construct yields another stub, so page code that
// touches the DOM keeps running while DSA.trace(...) calls are captured.
function stub() {
  const handler = {
    get(_t, k) {
      if (k === Symbol.toPrimitive) return () => '';
      if (k === Symbol.iterator) return function* () {};
      if (k === 'then') return undefined;
      if (k === 'length') return 0;
      return stub();
    },
    apply() { return stub(); },
    construct() { return stub(); },
    set() { return true; },
    has() { return true; }
  };
  return new Proxy(function () {}, handler);
}

function extractTraces(html) {
  const captured = [];
  const noop = () => {};
  const sandbox = {
    DSA: { trace: (cfg) => captured.push(JSON.parse(JSON.stringify(cfg))), cells: noop, chrome: noop, python: noop },
    document: stub(), window: stub(), localStorage: stub(), navigator: stub(),
    setTimeout: noop, setInterval: noop, clearInterval: noop, requestAnimationFrame: noop,
    MutationObserver: stub(), IntersectionObserver: stub(), ResizeObserver: stub(), Event: stub(), CustomEvent: stub(),
    MutationObserver: stub(), IntersectionObserver: stub(), ResizeObserver: stub(), Event: stub(), CustomEvent: stub(),
    performance: { now: () => 0 }, console: { log: noop, warn: noop, error: noop }
  };
  try { vm.runInNewContext(inlineScripts(html), sandbox, { timeout: 3000 }); } catch (e) { /* keep what was captured */ }
  return captured;
}

// --------------------------------------------------------------- checklists
// Rubric panels: const R = [{t, p}], score bands, deductions (checkboxes) and verdict text.
function extractChecklist(html) {
  const s = inlineScripts(html);
  const at = s.search(/const R = \[/);
  if (at < 0) return null;
  const open = s.indexOf('[', at);
  const end = scanBalanced(s, open);
  if (end < 0) return null;
  let items;
  try { items = evalData(s.slice(open, end)); } catch (e) { return null; }
  items = items.map(r => ({ text: String(r.t), points: Number(r.p) }));

  const chunkEnd = s.indexOf('})();', end);
  const chunk = s.slice(at, chunkEnd < 0 ? undefined : chunkEnd);

  const scoreM = /id="(b\d+)-score">\s*0\s*\/\s*(\d+)/.exec(html);
  const max = scoreM ? +scoreM[2] : items.reduce((n, r) => n + r.points, 0);

  const bm = /((?:fin >= \d+ \? "[^"]+" : )+)"([^"]+)"/.exec(chunk.slice(Math.max(0, chunk.search(/band/))));
  const bands = bm ? [...bm[1].matchAll(/fin >= (\d+) \? "([^"]+)"/g)].map(m => ({ min: +m[1], label: m[2] })).concat([{ min: 0, label: bm[2] }]) : [];

  const deductions = [];
  for (const m of html.matchAll(/<label[^>]*>\s*<input type="checkbox" id="b\d+-d\d+">\s*([\s\S]*?)<\/label>/g)) {
    const label = m[1].replace(/<[^>]+>/g, '').replace(/&gt;/g, '>').replace(/&lt;/g, '<').replace(/&amp;/g, '&').trim();
    const pts = /\((?:−|-)(\d+)\)/.exec(label);
    deductions.push({ label: label.replace(/\s*\((?:−|-)\d+\)\s*$/, ''), points: pts ? +pts[1] : 0 });
  }

  const verdicts = [];
  for (const m of chunk.matchAll(/say\(\s*"#b\d+-verdict"\s*,/g)) {
    const callStart = m.index + 3; // at '('
    const callEnd = scanBalanced(chunk, callStart);
    if (callEnd < 0) continue;
    const args = chunk.slice(callStart + 1, callEnd - 1);
    const toneM = /^\s*"#b\d+-verdict"\s*,\s*"(\w+)"\s*,\s*([\s\S]*)$/.exec(args);
    if (!toneM) continue;
    const before = chunk.slice(Math.max(0, m.index - 60), m.index);
    const condM = /fin >= (\d+)\)\s*$/.exec(before);
    let text = null;
    try { text = String(evalData(toneM[2], { fin: '{score}', ded: '{ded}', s: '{raw}', missed: { t: '{gap}', p: 0 } })); } catch (e) { /* fall back below */ }
    verdicts.push({ min: condM ? +condM[1] : 0, tone: toneM[1], html: text });
  }
  verdicts.sort((a, b) => b.min - a.min);
  if (!scoreM || verdicts.length === 0) return null; // not a rubric panel
  return { items, deductions, max, bands, verdicts, parsed: verdicts.length > 0 && verdicts.every(v => v.html) };
}

// ---------------------------------------------------------------- scorecard
function extractScorecard(html) {
  const s = inlineScripts(html);
  const at = s.search(/var AXES = \[/);
  if (at < 0) return null;
  const open = s.indexOf('[', at);
  const end = scanBalanced(s, open);
  let axes;
  try { axes = evalData(s.slice(open, end)).map(a => ({ name: a[0], levels: a[1] })); } catch (e) { return null; }
  const targetM = /total >= (\d+)/.exec(s);
  const crit = [...s.matchAll(/scores\[(\d+)\] < 3/g)].map(m => +m[1]);
  const critNote = /scores\[\d+\] < 3 \|\| scores\[\d+\] < 3\) note = '([^']+)'/.exec(s);
  const keyM = /var KEY = '([^']+)'/.exec(s);
  return {
    axes, target: targetM ? +targetM[1] : null, max: axes.length * 4,
    criticalAxes: [...new Set(crit)], criticalNote: critNote ? critNote[1] : null,
    storageKey: keyM ? keyM[1] : 'scorecard-v1'
  };
}

module.exports = { extractTraces, extractChecklist, extractScorecard, scanBalanced };
