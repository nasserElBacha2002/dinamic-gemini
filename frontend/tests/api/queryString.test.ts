import { describe, it, expect } from 'vitest';
import { buildQueryString } from '../../src/api/queryString';

describe('buildQueryString', () => {
  it('returns empty string for empty entries', () => {
    expect(buildQueryString([])).toBe('');
  });

  it('trims string values and prefixes with ?', () => {
    expect(buildQueryString([['search', '  test  ']])).toBe('?search=test');
  });

  it('omits blank strings and null/undefined so result is empty', () => {
    expect(
      buildQueryString([
        ['search', '   '],
        ['status', null],
        ['sort_by', undefined],
      ])
    ).toBe('');
  });

  it('applies min for numbers and omits sub-min values', () => {
    expect(
      buildQueryString([
        ['page', 0, { min: 1 }],
        ['page_size', 25, { min: 1 }],
      ])
    ).toBe('?page_size=25');
  });

  it('serializes boolean as string', () => {
    expect(buildQueryString([['include_diff_rows', true]])).toBe('?include_diff_rows=true');
  });

  it('encodes spaces via URLSearchParams (no manual encoding)', () => {
    const result = buildQueryString([['q', 'a b']]);
    const qs = result.startsWith('?') ? result.slice(1) : result;
    const parsed = new URLSearchParams(qs);
    expect(parsed.get('q')).toBe('a b');
  });

  it('omits NaN and Infinity numbers', () => {
    expect(
      buildQueryString([
        ['page', Number.NaN],
        ['limit', Number.POSITIVE_INFINITY],
      ])
    ).toBe('');
  });

  it('respects trim: false for strings', () => {
    const result = buildQueryString([['raw', '  value  ', { trim: false }]]);
    const qs = result.startsWith('?') ? result.slice(1) : result;
    expect(new URLSearchParams(qs).get('raw')).toBe('  value  ');
  });

  it('emits literal string scope when provided (e.g. supplier prompt list `scope=all` only)', () => {
    expect(buildQueryString([['scope', undefined]])).toBe('');
    expect(buildQueryString([['scope', 'all']])).toBe('?scope=all');
  });

  it('applies transform after trim for strings', () => {
    expect(
      buildQueryString([
        ['status', '  PENDING  ', { transform: (value) => value.toLowerCase() }],
      ])
    ).toBe('?status=pending');
  });

  it('omits string entry when transform returns empty string', () => {
    expect(
      buildQueryString([
        ['status', 'ignored', { transform: () => '' }],
      ])
    ).toBe('');
  });

  it('serializes both booleans when present (default emit always)', () => {
    expect(
      buildQueryString([
        ['has_evidence', true],
        ['has_conflict', false],
      ])
    ).toBe('?has_evidence=true&has_conflict=false');
  });

  it('emit true-only omits false booleans', () => {
    expect(
      buildQueryString([
        ['include_details', true, { emit: 'true-only' }],
        ['include_rows', false, { emit: 'true-only' }],
      ])
    ).toBe('?include_details=true');
  });

  it('emit false-only omits true booleans', () => {
    expect(
      buildQueryString([
        ['consolidate_by_sku', false, { emit: 'false-only' }],
        ['show_empty', true, { emit: 'false-only' }],
      ])
    ).toBe('?consolidate_by_sku=false');
  });

  it('emit does not change string serialization', () => {
    expect(buildQueryString([['status', 'active', { emit: 'false-only' }]])).toBe('?status=active');
  });

  it('allows page 0 when min is 0 and omits page_size below its min', () => {
    expect(
      buildQueryString([
        ['page', 0, { min: 0 }],
        ['page_size', 0, { min: 1 }],
      ])
    ).toBe('?page=0');
  });
});
