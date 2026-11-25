'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { loadAuditInput, buildAudit, toCsv, renderSummary } = require('./audit/build');

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

function main() {
  const dataDir = arg('--data', 'data');
  const outDir = arg('--out', path.join('docs', 'curriculum', 'audit'));
  const { rows, summary } = buildAudit(loadAuditInput(dataDir));
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, 'audit.csv'), toCsv(rows));
  fs.writeFileSync(path.join(outDir, 'audit-summary.md'), renderSummary(summary));
  const totals = Object.entries(summary.byFlag)
    .map(([f, m]) => `${f}=${Object.values(m).reduce((a, b) => a + b, 0)}`).join(' ');
  console.log(`audit: ${rows.length} lessons${totals ? ' | ' + totals : ''}`);
}

try {
  main();
} catch (e) {
  console.error('audit failed: ' + e.message);
  process.exit(1);
}
