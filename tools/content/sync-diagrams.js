// Loads content/diagrams/*.json (Excalidraw elements + metadata) into the database as lesson diagrams.
// Idempotent: a diagram is identified by its slug. Usage: npm run diagrams:sync [-- --data <dir>]
const fs = require('fs');
const path = require('path');
const { openDb, createRepo } = require('../../db');
const { fromExcalidraw } = require('./excalidraw');

const args = process.argv.slice(2);
const di = args.indexOf('--data');
const DATA_DIR = path.resolve(di >= 0 ? args[di + 1] : process.env.ALGOARCH_DATA_DIR || path.join(__dirname, '..', '..', 'data'));
const DIR = path.join(__dirname, '..', '..', 'content', 'diagrams');

const repo = createRepo(openDb(DATA_DIR));
let n = 0;
for (const f of fs.readdirSync(DIR).filter(x => x.endsWith('.json')).sort()) {
  const m = JSON.parse(fs.readFileSync(path.join(DIR, f), 'utf8'));
  const scene = fromExcalidraw(m.elements);
  if (Array.isArray(m.steps) && m.steps.length) scene.steps = m.steps.map(String);
  const { id } = repo.saveDiagram({ slug: m.slug, lessonId: m.lessonId, sectionAnchor: m.sectionAnchor, afterBlock: m.afterBlock ?? null, position: m.position ?? 0, title: m.title || null, caption: m.caption || null, scene });
  console.log(`${m.slug} -> lesson ${m.lessonId} #${m.sectionAnchor} (diagram ${id}, ${scene.elements.length} elements)`);
  n++;
}
console.log(`${n} diagram(s) synced into ${path.join(DATA_DIR, 'algoarch.db')}`);
