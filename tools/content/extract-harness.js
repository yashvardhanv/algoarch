// One-off: lifts the Python test harness out of the original lesson runtime (pybench.js)
// into web/src/pyHarness.ts so code cells run user code, then each test statement separately.
const fs = require('fs');
const path = require('path');
const src = fs.readFileSync(process.argv[2], 'utf8');
const a = src.indexOf('var PY_HARNESS = [');
const end = src.indexOf("].join('\\n');", a);
if (a < 0 || end < 0) throw new Error('harness markers not found');
const arr = eval(src.slice(a + 'var PY_HARNESS = '.length, end + 1));
const py = arr.join('\n');
const out = path.join(__dirname, '..', '..', 'web', 'src', 'pyHarness.ts');
fs.writeFileSync(out, '// Generated from the original lesson runtime (tools/content/extract-harness.js).\nexport const PY_HARNESS = ' + JSON.stringify(py) + ';\n');
console.log('harness lines:', py.split('\n').length, '->', out);
