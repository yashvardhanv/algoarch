// Converts Excalidraw elements (what the Excalidraw MCP draws, or a .excalidraw file) into the
// app's own diagram scene: semantic tones instead of hex colours, no editor-specific fields.
// The frontend draws scenes itself (web/src/Diagram.tsx); nothing here depends on Excalidraw at runtime.

// Excalidraw palette -> semantic tone
const TONE = [
  [/^#(4a9eed|a5d8ff|1e3a5f|2563eb|dbe4ff|1f5c86|5ea6d6)$/i, 'cool'],
  [/^#(f59e0b|ffd8a8|fff3bf|5c3d1a|b45309|a9700a|dfa53a)$/i, 'warn'],
  [/^#(22c55e|b2f2bb|c3fae8|d3f9d8|1a4d2e|15803d|4fb98a|216b4e)$/i, 'ok'],
  [/^#(ef4444|ffc9c9|5c1a1a|b91c1c|ec5b51)$/i, 'bad'],
  [/^#(8b5cf6|d0bfff|e5dbff|2d1b69|eebefa|ec4899|a98bd6|5b3e86)$/i, 'violet'],
  [/^#(f0793f|be2f27)$/i, 'accent']
];
const toneOf = (c) => { if (!c || c === 'transparent') return null; const hit = TONE.find(([re]) => re.test(c)); return hit ? hit[1] : null; };
const KIND = { rectangle: 'box', ellipse: 'ellipse', diamond: 'diamond', text: 'text', arrow: 'arrow', line: 'line' };
const sizeOf = (fs) => (fs >= 24 ? 'lg' : fs && fs < 18 ? 'sm' : 'md');

function fromExcalidraw(input, { pad = 28 } = {}) {
  let els = typeof input === 'string' ? JSON.parse(input) : input;
  if (!Array.isArray(els)) els = els.elements || [];

  // apply delete pseudo-elements, drop camera/checkpoint markers
  const deleted = new Set();
  for (const e of els) if (e.type === 'delete') String(e.ids || '').split(',').forEach(i => deleted.add(i.trim()));
  els = els.filter(e => KIND[e.type] && !e.isDeleted && !deleted.has(e.id));

  // text bound to a container (native Excalidraw) becomes the container's label
  const byId = new Map(els.map(e => [e.id, e]));
  const bound = new Set();
  for (const e of els) {
    if (e.type === 'text' && e.containerId && byId.has(e.containerId)) {
      const host = byId.get(e.containerId);
      host.label = { text: e.text, fontSize: e.fontSize };
      bound.add(e.id);
    }
  }
  els = els.filter(e => !bound.has(e.id));

  const out = [];
  for (const e of els) {
    const k = KIND[e.type];
    const o = { id: e.id, k };
    const label = e.label && e.label.text ? e.label.text : (k === 'text' ? e.text : '');
    if (k === 'arrow' || k === 'line') {
      o.pts = (e.points || [[0, 0], [e.width || 0, e.height || 0]]).map(([px, py]) => [Math.round(e.x + px), Math.round(e.y + py)]);
      if (k === 'arrow') o.head = e.startArrowhead && e.endArrowhead ? 'both' : e.startArrowhead ? 'start' : e.endArrowhead === null ? 'none' : 'end';
      if (label) o.label = label;
    } else if (k === 'text') {
      o.x = Math.round(e.x); o.y = Math.round(e.y); o.w = Math.round(e.width || 0); o.h = Math.round(e.height || 0);
      o.label = label;
    } else {
      o.x = Math.round(e.x); o.y = Math.round(e.y); o.w = Math.round(e.width); o.h = Math.round(e.height);
      if (label) o.label = label;
      if (e.backgroundColor && e.backgroundColor !== 'transparent') o.fill = true;
    }
    o.tone = toneOf(e.backgroundColor) || toneOf(e.strokeColor) || 'neutral';
    if (e.label && e.label.fontSize) o.size = sizeOf(e.label.fontSize);
    else if (e.fontSize) o.size = sizeOf(e.fontSize);
    if (e.strokeStyle === 'dashed' || e.strokeStyle === 'dotted') o.dashed = true;
    if (typeof e.opacity === 'number' && e.opacity <= 50) o.faint = true;
    if (Number.isFinite(e.step)) o.step = e.step;
    out.push(o);
  }

  // translate to the origin with padding and compute the canvas size
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const grow = (x, y) => { minX = Math.min(minX, x); minY = Math.min(minY, y); maxX = Math.max(maxX, x); maxY = Math.max(maxY, y); };
  for (const o of out) {
    if (o.pts) o.pts.forEach(([x, y]) => grow(x, y));
    else {
      const w = o.k === 'text' ? Math.max(o.w, (o.label || '').split('\n').reduce((m, l) => Math.max(m, l.length), 0) * (o.size === 'lg' ? 14 : o.size === 'sm' ? 8 : 10.5)) : o.w;
      grow(o.x, o.y); grow(o.x + w, o.y + (o.h || 24));
    }
  }
  if (!out.length) throw new Error('No drawable elements');
  const dx = pad - minX, dy = pad - minY;
  for (const o of out) {
    if (o.pts) o.pts = o.pts.map(([x, y]) => [x + dx, y + dy]);
    else { o.x += dx; o.y += dy; }
  }
  return { v: 1, width: Math.ceil(maxX - minX + pad * 2), height: Math.ceil(maxY - minY + pad * 2), elements: out };
}

module.exports = { fromExcalidraw };
