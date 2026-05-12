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
});
