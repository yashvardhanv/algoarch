// Regenerates docs/SIMULATIONS.md: live widget counts from the database + the static plan text.
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const report = execFileSync(process.execPath, [path.join(__dirname, 'report-widgets.js')], { encoding: 'utf8' });
const plan = fs.readFileSync(path.join(__dirname, 'simulations-plan.md'), 'utf8');
fs.mkdirSync(path.join(__dirname, '..', '..', 'docs'), { recursive: true });
fs.writeFileSync(path.join(__dirname, '..', '..', 'docs', 'SIMULATIONS.md'), report + plan);
console.log('docs/SIMULATIONS.md updated');
