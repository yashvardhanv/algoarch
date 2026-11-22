// Minimal, dependency-free HTML parser used only by the one-off content importer.
// Not a general HTML5 parser: it handles the regular, hand-written lesson pages.
const VOID = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr']);
const DROP_CONTENT = new Set(['script', 'style']);
const ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', mdash: '—', ndash: '–', hellip: '…', rarr: '→', larr: '←', times: '×', middot: '·', bull: '•', check: '✓', le: '≤', ge: '≥', ne: '≠', rsquo: '’', lsquo: '‘', ldquo: '“', rdquo: '”', deg: '°', plusmn: '±', micro: 'µ' };

function decode(s) {
  return s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e) => {
    if (e[0] === '#') {
      const code = e[1].toLowerCase() === 'x' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
      return Number.isFinite(code) ? String.fromCodePoint(code) : m;
    }
    return ENTITIES[e.toLowerCase()] ?? m;
  });
}

function parseAttrs(src) {
  const attrs = {};
  for (const m of src.matchAll(/([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g)) {
    attrs[m[1].toLowerCase()] = decode(m[2] ?? m[3] ?? m[4] ?? '');
  }
  return attrs;
}

function parse(html) {
  const root = { type: 'element', tag: '#root', attrs: {}, children: [], parent: null };
  let cur = root;
  const re = /<!--[\s\S]*?-->|<!doctype[^>]*>|<\/([a-zA-Z][\w-]*)\s*>|<([a-zA-Z][\w-]*)((?:"[^"]*"|'[^']*'|[^>"'])*)>|[^<]+|</gi;
  let m;
  while ((m = re.exec(html))) {
    const [full, closeTag, openTag, attrSrc] = m;
    if (full.startsWith('<!')) continue;
    if (closeTag) {
      const t = closeTag.toLowerCase();
      let n = cur;
      while (n && n.tag !== t) n = n.parent;
      if (n && n.parent) cur = n.parent;
      continue;
    }
    if (openTag) {
      const tag = openTag.toLowerCase();
      const selfClose = /\/\s*$/.test(attrSrc || '');
      const el = { type: 'element', tag, attrs: parseAttrs((attrSrc || '').replace(/\/\s*$/, '')), children: [], parent: cur };
      cur.children.push(el);
      if (DROP_CONTENT.has(tag)) {
        const end = html.toLowerCase().indexOf('</' + tag, re.lastIndex);
        if (tag === 'script' && /x-python/i.test(el.attrs.type || '') && end >= 0) {
          el.children.push({ type: 'text', text: html.slice(re.lastIndex, end), parent: el });
        }
        if (end >= 0) re.lastIndex = html.indexOf('>', end) + 1;
        continue;
      }
      if (!VOID.has(tag) && !selfClose) cur = el;
      continue;
    }
    cur.children.push({ type: 'text', text: decode(full), parent: cur });
  }
  return root;
}

const hasClass = (el, c) => el.type === 'element' && (el.attrs.class || '').split(/\s+/).includes(c);
function find(el, pred, out = []) {
  for (const c of el.children || []) {
    if (c.type !== 'element') continue;
    if (pred(c)) out.push(c);
    find(c, pred, out);
  }
  return out;
}
const findOne = (el, pred) => find(el, pred)[0] || null;
function textOf(el) {
  if (el.type === 'text') return el.text;
  if (el.tag === 'br') return '\n';
  return (el.children || []).map(textOf).join('');
}

module.exports = { parse, find, findOne, textOf, hasClass };
