// Authors the sy02 (Postgres indexes) diagrams as Excalidraw-format elements and writes one
// manifest per diagram into content/diagrams/. `npm run diagrams:sync` loads them into the database.
// Each element may carry `step` (1-based); the reader reveals a diagram one step at a time.
const fs = require('fs');
const path = require('path');

const COL = {
  cool: ['#4a9eed', '#a5d8ff'], warn: ['#f59e0b', '#ffd8a8'], ok: ['#22c55e', '#b2f2bb'], bad: ['#ef4444', '#ffc9c9'],
  violet: ['#8b5cf6', '#d0bfff'], accent: ['#f0793f', '#ffd8a8'], neutral: ['#1e1e1e', 'transparent']
};
function mk() {
  const els = []; let n = 0;
  const id = (p) => p + (++n);
  return {
    els,
    box(x, y, w, h, label, tone = 'neutral', o = {}) {
      els.push({ type: o.shape || 'rectangle', id: id('b'), x, y, width: w, height: h, roundness: { type: 3 }, strokeColor: COL[tone][0],
        backgroundColor: o.nofill ? 'transparent' : COL[tone][1], fillStyle: 'solid', strokeStyle: o.dashed ? 'dashed' : 'solid', opacity: o.faint ? 40 : 100,
        ...(label ? { label: { text: label, fontSize: o.fs || 18 } } : {}), ...(o.step ? { step: o.step } : {}) });
    },
    text(x, y, t, o = {}) {
      els.push({ type: 'text', id: id('t'), x, y, text: t, fontSize: o.fs || 18, strokeColor: o.color || COL[o.tone || 'neutral'][0], ...(o.step ? { step: o.step } : {}) });
    },
    arrow(pts, o = {}) {
      const [x, y] = pts[0];
      const rel = pts.map(([px, py]) => [px - x, py - y]);
      els.push({ type: 'arrow', id: id('a'), x, y, width: Math.abs(rel[rel.length - 1][0]), height: Math.abs(rel[rel.length - 1][1]), points: rel,
        strokeColor: COL[o.tone || 'neutral'][0], strokeWidth: o.w || 2, strokeStyle: o.dashed ? 'dashed' : 'solid',
        endArrowhead: o.head === 'none' ? null : 'arrow', ...(o.label ? { label: { text: o.label, fontSize: 16 } } : {}), ...(o.step ? { step: o.step } : {}) });
    }
  };
}
const out = [];
const add = (slug, meta, steps, d) => out.push({ slug, ...meta, steps, elements: d.els });

// ---------------------------------------------------------------- heap vs clustered
{
  const d = mk();
  d.text(40, 30, 'PostgreSQL: heap-organized', { fs: 20, step: 1 });
  d.box(40, 70, 230, 84, 'Secondary index\n(key, ctid)', 'cool', { step: 1 });
  d.arrow([[270, 112], [450, 112]], { tone: 'neutral', label: 'follow the ctid', step: 1 });
  d.box(450, 70, 230, 84, 'Heap page\n(the whole row)', 'warn', { step: 1 });
  d.text(720, 100, '1 index descent\n+ 1 heap fetch', { fs: 18, tone: 'ok', step: 1 });
  d.text(40, 220, 'MySQL InnoDB: clustered', { fs: 20, step: 2 });
  d.box(40, 260, 230, 84, 'Secondary index\n(key, primary key)', 'cool', { step: 2 });
  d.arrow([[270, 302], [450, 302]], { tone: 'neutral', label: 'search by PK', step: 2 });
  d.box(450, 260, 230, 84, 'Primary-key B-tree\n(rows in the leaves)', 'violet', { step: 2 });
  d.text(720, 290, '2 tree descents\nto reach the row', { fs: 18, tone: 'warn', step: 2 });
  d.box(40, 400, 640, 70, 'Postgres: every index points at a physical address. InnoDB: the table IS the primary-key index.', 'accent', { nofill: true, dashed: true, step: 3, fs: 18 });
  add('sy02-heap-vs-clustered', { lessonId: 'sy02', sectionAnchor: 's3', afterBlock: 5, title: 'Where does the row live?', caption: 'Two engines, two different paths from an index entry to the row.' },
    ['Postgres: the index entry holds a ctid, a direct address into the heap.', 'InnoDB: the secondary index holds the primary key, so a second tree is searched.', 'The takeaway: in Postgres every index is secondary and points at a ctid.'], d);
}

// ---------------------------------------------------------------- B-tree descent
{
  const d = mk();
  d.box(330, 30, 200, 62, 'Root page\nseparator keys', 'cool', { step: 1 });
  const midX = [100, 330, 560], mid = [];
  midX.forEach((x, i) => { d.box(x, 160, 200, 62, 'Internal page', 'cool', { step: 1 }); mid.push(x + 100); d.arrow([[430, 92], [x + 100, 160]], { tone: 'neutral', step: 1 }); });
  const leafC = [140, 260, 370, 490, 600, 720], leaves = [];
  leafC.forEach((cx, i) => { d.box(cx - 52, 295, 104, 50, 'Leaf', 'ok', { step: 1 }); leaves.push(cx); d.arrow([[mid[Math.floor(i / 2)], 222], [cx, 295]], { tone: 'neutral', step: 1 }); });
  d.box(300, 430, 260, 56, 'Heap (the table)', 'warn', { step: 1 });
  d.text(40, 120, 'routing only', { fs: 16, color: '#757575', step: 1 });
  d.text(40, 245, 'key + ctid', { fs: 16, color: '#757575', step: 1 });
  // the descent for one lookup
  d.arrow([[430, 92], [430, 160]], { tone: 'accent', w: 4, label: '1', step: 2 });
  d.arrow([[430, 222], [490, 295]], { tone: 'accent', w: 4, label: '2', step: 2 });
  d.arrow([[490, 345], [430, 430]], { tone: 'accent', w: 4, label: '3: ctid', step: 2 });
  d.box(600, 420, 250, 80, '3 page reads down,\n1 heap fetch', 'accent', { nofill: true, step: 3 });
  add('sy02-btree-descent', { lessonId: 'sy02', sectionAnchor: 's4', afterBlock: 5, title: 'One lookup, top to bottom', caption: 'Internal pages only route; leaves hold key and ctid; the heap holds the row.' },
    ['The shape: one root, a few internal pages, many leaves, then the heap.', 'A lookup follows one path: root, internal page, leaf, then the ctid into the heap.', 'The cost: about one page read per level, plus one heap fetch.'], d);
}

// ---------------------------------------------------------------- leftmost prefix
{
  const d = mk();
  const groups = [[10, 20, 30], [5, 25, 40], [5, 15, 99]];
  const cw = 84, gap = 10, ggap = 36, x0 = 40, y = 110;
  const pos = []; let ci = 0;
  groups.forEach((g, gi) => g.forEach((b, bi) => { const x = x0 + ci * (cw + gap) + gi * ggap; pos.push({ x, a: gi + 1, b }); ci++; }));
  d.text(40, 20, 'index on (a, b), sorted by a, then b', { fs: 18, step: 1 });
  groups.forEach((_, gi) => d.text(x0 + gi * (3 * (cw + gap) + ggap) + 100, 70, 'a = ' + (gi + 1), { fs: 18, color: '#757575', step: 1 }));
  pos.forEach(p => d.box(p.x, y, cw, 48, `(${p.a}, ${p.b})`, 'neutral', { step: 1, nofill: true, fs: 16 }));
  // step 2: WHERE a = 2 AND b > 20
  pos.filter(p => p.a === 2 && p.b > 20).forEach(p => d.box(p.x, y, cw, 48, `(${p.a}, ${p.b})`, 'ok', { step: 2, fs: 16 }));
  d.text(40, 200, 'WHERE a = 2 AND b > 20', { fs: 20, step: 2 });
  d.text(40, 232, 'Seek to a = 2, then read only the matches.', { fs: 18, tone: 'ok', step: 2 });
  // step 3: WHERE b = 5
  d.box(30, 100, 888, 68, '', 'bad', { nofill: true, dashed: true, step: 3 });
  pos.filter(p => p.b === 5).forEach(p => d.box(p.x, y, cw, 48, `(${p.a}, ${p.b})`, 'warn', { step: 3, fs: 16 }));
  d.text(40, 290, 'WHERE b = 5', { fs: 20, step: 3 });
  d.text(40, 322, 'The 5s are scattered: there is no contiguous block, so every entry is visited.', { fs: 18, tone: 'bad', step: 3 });
  add('sy02-leftmost-prefix', { lessonId: 'sy02', sectionAnchor: 's5', afterBlock: 10, title: 'Why the first column matters', caption: 'The same index, two queries: one can skip, one cannot.' },
    ['The layout: entries are sorted by a, and ties are broken by b.', 'Filtering on a first lets the index seek straight to the block.', 'Filtering on b alone finds matches scattered across the whole index.'], d);
}

// ---------------------------------------------------------------- scan types
{
  const d = mk();
  const x0 = 330, pw = 52, pg = 10, lanes = [30, 140, 250, 360];
  const pages = (laneY, idx, tone, step, order) => {
    for (let i = 0; i < 8; i++) {
      const on = idx.includes(i);
      d.box(x0 + i * (pw + pg), laneY, pw, pw, on && order ? String(order[idx.indexOf(i)]) : '', on ? tone : 'neutral', { step, nofill: !on, dashed: !on, faint: !on, fs: 18 });
    }
  };
  const lane = (i, name, note, step) => { d.text(40, lanes[i] + 4, name, { fs: 22, step }); d.text(40, lanes[i] + 36, note, { fs: 16, color: '#757575', step }); };
  lane(0, 'Seq Scan', 'every page, in order', 1);
  pages(lanes[0], [0, 1, 2, 3, 4, 5, 6, 7], 'cool', 1, [1, 2, 3, 4, 5, 6, 7, 8]);
  lane(1, 'Index Scan', 'one random read per match', 2);
  pages(lanes[1], [5, 1, 6, 2], 'warn', 2, [1, 2, 3, 4]);
  lane(2, 'Bitmap Heap Scan', 'flag pages, then read in page order', 3);
  pages(lanes[2], [1, 2, 5, 6], 'violet', 3, [1, 2, 3, 4]);
  lane(3, 'Index Only Scan', 'the heap is never touched', 4);
  pages(lanes[3], [], 'ok', 4);
  d.box(x0, lanes[3] - 2, 270, 56, 'answered from the index', 'ok', { step: 4 });
  add('sy02-scan-types', { lessonId: 'sy02', sectionAnchor: 's7', afterBlock: 8, title: 'Four ways to read the same rows', caption: 'Each box is a heap page; numbers show the order pages are read.' },
    ['Seq Scan reads every page in physical order.', 'Index Scan jumps around the heap, one random read per match.', 'Bitmap Heap Scan collects the pages first, then reads them in page order.', 'Index Only Scan answers from the index when the visibility map allows it.'], d);
}

const dir = path.join(__dirname, '..', '..', '..', 'content', 'diagrams');
fs.mkdirSync(dir, { recursive: true });
for (const m of out) fs.writeFileSync(path.join(dir, m.slug + '.json'), JSON.stringify(m, null, 1) + '\n');
console.log('wrote', out.map(m => m.slug).join(', '));
