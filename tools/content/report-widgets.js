// Prints a grouping report of the interactive widgets stored in the database (markdown).
const path = require('path');
const Database = require('better-sqlite3');
const db = new Database(path.join(process.env.ALGOARCH_DATA_DIR || path.join(__dirname, '..', '..', 'data'), 'algoarch.db'), { readonly: true });

const rows = db.prepare('SELECT l.id, l.title, l.track_id, d.document FROM lesson_documents d JOIN lessons l ON l.id = d.lesson_id ORDER BY l.track_id, l.id').all();
const byType = {}, byTrack = {}, lessons = {};
let total = 0, ported = 0;
const samples = {};

function walk(blocks, row) {
  for (const b of blocks || []) {
    if (b.type === 'widget') {
      total++;
      const a = b.archetype || b.kind;
      byType[a] = (byType[a] || 0) + 1;
      (byTrack[row.track_id] ||= {})[a] = ((byTrack[row.track_id] || {})[a] || 0) + 1;
      (lessons[row.id] ||= { title: row.title, n: 0 }).n++;
      (samples[a] ||= []).length < 6 && samples[a].push(`${row.id}: ${b.title || ''}`.trim());
      if (b.ported) ported++;
    }
    walk(b.blocks, row);
  }
}
for (const r of rows) walk(JSON.parse(r.document).sections.flatMap(s => s.blocks), r);

const order = Object.entries(byType).sort((a, b) => b[1] - a[1]);
console.log(`# Interactive widgets\n\nTotal: ${total} across ${Object.keys(lessons).length} lessons. Ported: ${ported}.\n`);
console.log('| Group | Count | Share |\n|---|---:|---:|');
for (const [a, n] of order) console.log(`| ${a} | ${n} | ${Math.round((100 * n) / total)}% |`);
console.log('\n## By track\n');
for (const [t, m] of Object.entries(byTrack)) console.log(`- **${t}**: ` + Object.entries(m).sort((a, b) => b[1] - a[1]).map(([a, n]) => `${a} ${n}`).join(', '));
console.log('\n## Examples\n');
for (const [a] of order) console.log(`- **${a}**: ${samples[a].join('; ')}`);
console.log('\n## Lessons with the most widgets\n');
for (const [id, v] of Object.entries(lessons).sort((a, b) => b[1].n - a[1].n).slice(0, 10)) console.log(`- ${id} ${v.title}: ${v.n}`);
