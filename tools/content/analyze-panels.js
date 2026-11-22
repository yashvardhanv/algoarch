// Analysis only: clusters the interactive panels in the original lesson pages by structure.
const fs = require('fs');
const path = require('path');
const { parse, find, findOne, textOf, hasClass } = require('./minidom');
const ROOT = process.argv[2];

const sigs = {};
const examples = {};
let total = 0;
const perPage = [];

for (const d of ['dsa-faang-prep', 'system-design-prep', 'ai-master-prep', 'behavioral-prep']) {
  const dir = path.join(ROOT, d, 'visuals');
  if (!fs.existsSync(dir)) continue;
  for (const f of fs.readdirSync(dir).filter(x => x.endsWith('.html'))) {
    const html = fs.readFileSync(path.join(dir, f), 'utf8');
    const root = parse(html);
    const panels = find(root, e => hasClass(e, 'panel'));
    let n = 0;
    for (const p of panels) {
      n++; total++;
      const body = findOne(p, e => hasClass(e, 'panel-body'));
      const ctl = findOne(p, e => hasClass(e, 'controls'));
      const inputs = find(p, e => e.tag === 'input');
      const ranges = inputs.filter(i => i.attrs.type === 'range').length;
      const selects = find(p, e => e.tag === 'select').length;
      const buttons = find(p, e => e.tag === 'button').length;
      const svgs = find(p, e => e.tag === 'svg').length;
      const canvas = find(p, e => e.tag === 'canvas').length;
      const mbar = find(p, e => hasClass(e, 'mbar')).length;
      const readout = find(p, e => hasClass(e, 'readout')).length;
      const tr = find(p, e => hasClass(e, 'tr-cells')).length;
      const pre = find(p, e => e.tag === 'pre').length;
      const tables = find(p, e => e.tag === 'table').length;
      const grid = find(p, e => /grid|queue|lane|node|box|cell/.test(e.attrs.class || '')).length;
      const bar = findOne(p, e => hasClass(e, 'panel-bar'));
      const sig = [
        ranges ? 'range' + Math.min(ranges, 4) : '', selects ? 'select' : '', buttons ? 'btn' + Math.min(buttons, 4) : '',
        svgs ? 'svg' : '', canvas ? 'canvas' : '', mbar ? 'bars' : '', tr ? 'trace' : '', readout ? 'readout' : '', pre ? 'pre' : '', tables ? 'table' : ''
      ].filter(Boolean).join('+') || 'none';
      sigs[sig] = (sigs[sig] || 0) + 1;
      (examples[sig] ||= []).push(`${f}: ${bar ? textOf(bar).replace(/\s+/g, ' ').trim().slice(0, 60) : ''}`);
    }
    perPage.push([f, n]);
  }
}
console.log('total panels', total);
const top = Object.entries(sigs).sort((a, b) => b[1] - a[1]).slice(0, 25);
for (const [s, c] of top) console.log(String(c).padStart(4), s, '\n      e.g.', examples[s].slice(0, 2).join(' | '));
console.log('signature count:', Object.keys(sigs).length);
