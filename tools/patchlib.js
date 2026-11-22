// Tiny EOL-preserving patch helper used for repo maintenance scripts.
const fs = require('fs');
exports.rep = function (file, oldStr, newStr, all = false) {
  const raw = fs.readFileSync(file, 'utf8');
  const crlf = raw.includes('\r\n');
  let txt = raw.replace(/\r\n/g, '\n');
  if (!txt.includes(oldStr)) throw new Error(`Anchor not found in ${file}: ${oldStr.slice(0, 70)}`);
  txt = all ? txt.split(oldStr).join(newStr) : txt.replace(oldStr, () => newStr);
  fs.writeFileSync(file, crlf ? txt.replace(/\n/g, '\r\n') : txt);
};
