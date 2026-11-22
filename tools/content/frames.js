// Turns what capture-driver.js recorded for one panel into widget data stored in the database.
//
// A "frames" widget is: the controls the learner can move, plus every rendered result as a
// sanitized element tree. Trees are hash-consed into one node table, so the rows that do not
// change between frames are stored once. The frontend resolves a control state to a frame and
// draws it with its own components and styles; no markup or script from the original pages.

const HTML_TAGS = new Set(['div', 'span', 'p', 'b', 'strong', 'i', 'em', 'u', 'small', 'sub', 'sup', 'br', 'code', 'pre', 'kbd', 'a', 'h3', 'h4', 'h5', 'h6',
  'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption', 'colgroup', 'col', 'button', 'label', 'figure', 'figcaption', 'hr', 'img']);
const SVG_TAGS = new Set(['svg', 'g', 'path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon', 'text', 'tspan', 'defs', 'marker', 'linearGradient', 'stop', 'title', 'clipPath', 'use']);
const SVG_LOWER = new Map([...SVG_TAGS].map(t => [t.toLowerCase(), t]));
const ATTRS = new Set(['class', 'style', 'viewBox', 'x', 'y', 'cx', 'cy', 'r', 'rx', 'ry', 'width', 'height', 'd', 'points', 'fill', 'stroke', 'stroke-width',
  'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin', 'transform', 'x1', 'y1', 'x2', 'y2', 'text-anchor', 'dominant-baseline', 'font-size', 'font-weight',
  'font-family', 'opacity', 'fill-opacity', 'stroke-opacity', 'offset', 'colspan', 'rowspan', 'title', 'marker-end', 'marker-start', 'preserveAspectRatio',
  'stop-color', 'stop-opacity', 'dx', 'dy', 'act', 'src']);

const STYLE_PROPS = new Set(['width', 'height', 'min-width', 'max-width', 'min-height', 'max-height', 'background', 'background-color', 'color', 'opacity',
  'left', 'top', 'right', 'bottom', 'transform', 'transform-origin', 'flex', 'flex-grow', 'flex-basis', 'border', 'border-color', 'border-left', 'border-right',
  'border-top', 'border-bottom', 'margin', 'margin-left', 'margin-right', 'margin-top', 'margin-bottom', 'padding', 'padding-left', 'padding-right', 'padding-top',
  'padding-bottom', 'display', 'font-size', 'font-weight', 'font-style', 'text-align', 'text-decoration', 'stroke', 'fill', 'stroke-width', 'stroke-dasharray',
  'grid-template-columns', 'grid-column', 'grid-row', 'gap', 'justify-content', 'align-items', 'position', 'z-index', 'white-space', 'line-height', 'letter-spacing',
  'outline', 'box-shadow', 'border-radius', 'overflow', 'visibility', 'filter', 'writing-mode', 'height', 'object-fit']);

function sanitizeStyle(css) {
  const out = [];
  for (const decl of String(css).split(';')) {
    const i = decl.indexOf(':');
    if (i < 0) continue;
    const prop = decl.slice(0, i).trim().toLowerCase();
    const val = decl.slice(i + 1).trim();
    if (!STYLE_PROPS.has(prop) || !val) continue;
    if (/url\s*\(|expression|javascript:|@import|<|>|\\/i.test(val)) continue;
    if (prop === 'position' && !/^(relative|absolute|static|sticky)$/.test(val)) continue;
    out.push(prop + ':' + val);
  }
  return out.join(';');
}

function cleanTag(t) {
  if (HTML_TAGS.has(t)) return t;
  return SVG_LOWER.get(String(t).toLowerCase()) || SVG_LOWER.get(t) || null;
}

// Prefix every class so the original names can never collide with the app's own styles.
const prefixClasses = (c) => String(c).split(/\s+/).filter(Boolean).map(x => 'fw-' + x).join(' ');

function buildFramesData(panel, scope) {
  if (!panel || panel.error || !panel.frames || !panel.frames.length) return null;
  const table = [];
  const index = new Map();
  const intern = (obj) => {
    const key = JSON.stringify(obj);
    if (!index.has(key)) { index.set(key, table.length); table.push(obj); }
    return index.get(key);
  };

  function conv(n) {
    if (n == null) return null;
    if (typeof n === 'string') return n;
    const tag = cleanTag(n.t);
    if (!tag) return null;
    const node = { t: tag };
    const a = {};
    for (const [k, v] of Object.entries(n.a || {})) {
      if (!ATTRS.has(k)) continue;
      if (k === 'class') a.class = prefixClasses(v);
      else if (k === 'style') { const s = sanitizeStyle(v); if (s) a.style = s; }
      else if (k === 'src') { if (tag === 'img' && /^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(v)) a.src = v; }
      else if (/^(href|on)/i.test(k)) continue;
      else a[k] = String(v);
    }
    if (tag === 'button' && a.act == null) delete a.act;
    if (Object.keys(a).length) node.a = a;
    const kids = [];
    for (const c of n.k || []) {
      const r = conv(c);
      if (r === null) continue;
      kids.push(typeof r === 'string' ? r : r);
    }
    if (kids.length) node.k = kids;
    return intern(node);
  }
  // children are node ids (numbers) or text (strings); intern returns ids, so inline them
  const rootOf = (b) => (b ? conv(b) : null);

  const frames = panel.frames.map(f => ({ s: f.s || '', r: rootOf(f.b) }));
  const controls = (panel.controls || []).map(c => c.k === 'range'
    ? { k: 'range', label: c.label, values: c.samples, def: c.samples.reduce((best, v, i) => (Math.abs(v - c.def) < Math.abs(c.samples[best] - c.def) ? i : best), 0) }
    : c.k === 'select'
      ? { k: 'select', label: c.label, options: c.options.map(o => ({ v: o.v, t: o.t })), def: Math.max(0, c.options.findIndex(o => o.v === c.def)) }
      : { k: 'check', label: c.label, def: c.def ? 1 : 0 });

  const gridOk = Array.isArray(panel.grid) && controls.length > 0;
  const buttons = (panel.buttons || []).map(b => ({ label: b.label, role: b.role }));
  const data = {
    v: 1,
    scope: scope || '',
    nodes: table,
    frames,
    base: panel.base || 0,
    controls,
    grid: gridOk ? panel.grid : null,
    seq: panel.seq && panel.seq.length > 1 ? panel.seq : null,
    buttons,
    acts: (panel.acts || []).map(a => ({ label: a.label, frame: a.frame })),
    bodyActs: (panel.bodyActs || []).map(a => ({ i: a.i, frame: a.frame }))
  };
  // controls that could not be captured (e.g. free text): the widget still shows its initial state
  if (controls.length && !gridOk) { data.controls = []; data.partial = true; }
  return data;
}

module.exports = { buildFramesData, sanitizeStyle };
