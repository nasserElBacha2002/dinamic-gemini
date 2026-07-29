#!/usr/bin/env node
/**
 * Phase 4 corrections — scan frontend/dist (+ optional source maps) for secret-like literals.
 * Exit 1 on matches. Does not replace backend auth; hygiene only.
 */
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '../..');
const dist = path.join(root, 'frontend', 'dist');
if (!fs.existsSync(dist)) {
  console.error('frontend/dist missing — run npm run build first');
  process.exit(2);
}

const PATTERNS = [
  { name: 'private-key', re: /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/ },
  { name: 'aws-access-key', re: /AKIA[0-9A-Z]{16}/ },
  { name: 'jwt', re: /eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/ },
  { name: 'connection-string', re: /(?:Server|Data Source)=[^;\s]+;.*(?:Password|PWD)=/i },
  { name: 'generic-api-key-assign', re: /(?:api[_-]?key|client_secret|private_key)\s*[:=]\s*['"][A-Za-z0-9_\-+/=]{20,}['"]/i },
];

function walk(dir, acc = []) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) walk(p, acc);
    else if (/\.(js|css|map|html|json)$/i.test(ent.name)) acc.push(p);
  }
  return acc;
}

const hits = [];
for (const file of walk(dist)) {
  const text = fs.readFileSync(file, 'utf8');
  for (const { name, re } of PATTERNS) {
    if (re.test(text)) {
      hits.push({ file: path.relative(root, file), pattern: name });
    }
  }
}

if (hits.length) {
  console.error('Secret-like patterns found in frontend/dist:');
  for (const h of hits) console.error(`- ${h.pattern}: ${h.file}`);
  process.exit(1);
}
console.log('frontend dist secrets scan: OK');
