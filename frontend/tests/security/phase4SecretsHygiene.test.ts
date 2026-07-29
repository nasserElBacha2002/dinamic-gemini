/**
 * Phase 4 — frontend must not embed server secrets via VITE_* env.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const FORBIDDEN_VITE_NAME = /VITE_.*(SECRET|PASSWORD|PRIVATE_KEY|API_KEY|TOKEN|CREDENTIAL)/i;

describe('phase4 frontend secrets hygiene', () => {
  it('frontend .env.example has no forbidden VITE_* secret names', () => {
    const path = resolve(__dirname, '../../.env.example');
    const text = readFileSync(path, 'utf8');
    const matches = text.split(/\r?\n/).filter((line) => FORBIDDEN_VITE_NAME.test(line));
    expect(matches).toEqual([]);
  });

  it('runtime import.meta.env keys do not include secret-shaped VITE names', () => {
    const keys = Object.keys(import.meta.env);
    const bad = keys.filter((k) => FORBIDDEN_VITE_NAME.test(k));
    expect(bad).toEqual([]);
  });
});
