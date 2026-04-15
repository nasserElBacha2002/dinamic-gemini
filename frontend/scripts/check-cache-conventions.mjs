#!/usr/bin/env node
/**
 * Phase 9 — lightweight static checks for TanStack Query cache conventions (no ESLint plugin).
 * Run: node scripts/check-cache-conventions.mjs (from frontend/)
 *
 * Limitations (intentional — no full parser):
 * - Walks TypeScript sources under `frontend/src` only; tests and scripts are out of scope.
 * - Rules are regex-based: they can miss issues or overlap real code in edge cases.
 * - Comment stripping before the `merge-results` segment check is line-based: a `//` inside a
 *   string literal (e.g. URLs) or odd quoting can theoretically truncate a line incorrectly.
 *   Goal is only to drop obvious line comments and slash-star block comments so merge-results in comments
 *   does not false-positive.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(__dirname, '..', 'src');

function isQueryKeysFile(absPath) {
  return absPath.replace(/\\/g, '/').endsWith('/api/queryKeys.ts');
}

/** Prefer `queryKeys.inventories.aislesListTable` over ad-hoc `[...aisles(inventoryId), params]`. */
const AISLES_MANUAL_SPREAD = /queryKey:\s*\[\s*\.\.\.\s*queryKeys\.inventories\.aisles\s*\(/;

/** v3 merge-results key segment must only appear in `queryKeys` (HTTP paths may still say merge-results). */
const MERGE_RESULTS_SEGMENT = /['"]merge-results['"]/;

/** Strip line comments and slash-star block comments before scanning for quoted merge-results segment. */
function sourceForMergeResultsScan(text) {
  const noBlocks = text.replace(/\/\*[\s\S]*?\*\//g, '\n');
  return noBlocks
    .split('\n')
    .map((line) => {
      const i = line.indexOf('//');
      return i === -1 ? line : line.slice(0, i);
    })
    .join('\n');
}

/** Invalidate with a literal array root (bypasses factories). */
const INVALIDATE_LITERAL_KEY = /invalidateQueries\s*\(\s*\{\s*queryKey:\s*\[\s*(['"])/;

function walk(dir, out = []) {
  for (const name of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, name.name);
    if (name.isDirectory()) {
      if (name.name === 'node_modules' || name.name === 'dist') continue;
      walk(p, out);
    } else if (/\.(tsx?)$/.test(name.name)) {
      out.push(p);
    }
  }
  return out;
}

function checkFile(absPath) {
  const rel = path.relative(SRC, absPath);
  const text = fs.readFileSync(absPath, 'utf8');
  const issues = [];

  if (!isQueryKeysFile(absPath)) {
    if (AISLES_MANUAL_SPREAD.test(text)) {
      issues.push(
        `${rel}: use queryKeys.inventories.aislesListTable(inventoryId) instead of queryKey: [...queryKeys.inventories.aisles(...), params]`
      );
    }
    if (MERGE_RESULTS_SEGMENT.test(sourceForMergeResultsScan(text))) {
      issues.push(
        `${rel}: 'merge-results' key segment must only appear in api/queryKeys.ts — use queryKeys.inventories.mergeResults*`
      );
    }
    if (INVALIDATE_LITERAL_KEY.test(text)) {
      issues.push(`${rel}: invalidateQueries must use queryKeys factories (literal queryKey: [...] detected)`);
    }
  }

  return issues;
}

function main() {
  const files = walk(SRC);
  const all = files.flatMap(checkFile);
  if (all.length) {
    console.error('[check-cache-conventions] FAILED:\n' + all.join('\n'));
    process.exit(1);
  }
  console.log('[check-cache-conventions] OK (' + files.length + ' files)');
}

main();
