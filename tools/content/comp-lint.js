// Finds salary and compensation figures (rupee amounts, LPA, lakh, crore) in lesson text.
// Decision (owner, 2026-11-26): lessons carry no specific compensation figures.
//   node tools/content/comp-lint.js [--data <dir>]   lists lessons whose imported text contains any
const path = require('path');

const CLAIM_RE = /₹\s?[\d,.]+(?:\s?(?:Lakhs?|Crores?|Cr|L|k|K)\b)?|\b\d+(?:\.\d+)?\s?(?:Lakhs?|Crores?|Cr|LPA)\b/g;

function findCompClaims(text) {
  return String(text || '').match(CLAIM_RE) || [];
}

function main() {
  const i = process.argv.indexOf('--data');
  const dataDir = path.resolve(i >= 0 ? process.argv[i + 1] : path.join(__dirname, '..', '..', 'data'));
  const Database = require('better-sqlite3');
  const db = new Database(path.join(dataDir, 'algoarch.db'), { readonly: true });
  let total = 0;
  const rows = db.prepare(`
    SELECT l.id, l.title, COALESCE(g.markdown, '') AS md, COALESCE(d.document, '') AS doc
    FROM lessons l
    LEFT JOIN lesson_guides g ON g.lesson_id = l.id
    LEFT JOIN lesson_documents d ON d.lesson_id = l.id
    ORDER BY l.id`).all();
  for (const r of rows) {
    const hits = [...findCompClaims(r.md), ...findCompClaims(r.doc)];
    const title = findCompClaims(r.title);
    if (hits.length || title.length) {
      total++;
      console.log(`${r.id}\t${hits.length + title.length}\t${[...new Set([...title, ...hits])].slice(0, 5).join(' | ')}`);
    }
  }
  console.log(`\n${total} lesson(s) contain compensation figures`);
  process.exitCode = total ? 1 : 0;
}

if (require.main === module) main();
module.exports = { findCompClaims };
