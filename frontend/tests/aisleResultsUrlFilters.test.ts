/**
 * Unit tests for aisle results URL filter contract.
 */

import { describe, it, expect } from 'vitest';
import {
  areAisleResultsFiltersEqual,
  createDefaultAisleResultsFilters,
  isAisleResultsSortColumn,
  mergeAisleResultsFilterPatch,
  normalizeAisleResultsFilters,
  parseAisleResultsFilters,
  writeAisleResultsFilters,
} from '../src/features/results/utils/aisleResultsUrlFilters';

describe('aisleResultsUrlFilters', () => {
  it('parse without params returns defaults', () => {
    const defaults = createDefaultAisleResultsFilters();
    const parsed = parseAisleResultsFilters(new URLSearchParams());
    expect(parsed).toEqual(defaults);
  });

  it('parse all valid params', () => {
    const params = new URLSearchParams(
      'jobId=j1&filter=needs_review&q=ABC&page=2&pageSize=50&tableSort=priority&sortBy=sku&sortDir=desc'
    );
    const parsed = parseAisleResultsFilters(params);
    expect(parsed).toEqual({
      filter: 'needs_review',
      q: 'ABC',
      page: 2,
      pageSize: 50,
      tableSort: 'priority',
      sortBy: 'sku',
      sortDir: 'desc',
    });
  });

  it('invalid page falls back to 1', () => {
    expect(parseAisleResultsFilters(new URLSearchParams('page=0')).page).toBe(1);
    expect(parseAisleResultsFilters(new URLSearchParams('page=-3')).page).toBe(1);
    expect(parseAisleResultsFilters(new URLSearchParams('page=1.5')).page).toBe(1);
    expect(parseAisleResultsFilters(new URLSearchParams('page=abc')).page).toBe(1);
  });

  it('invalid pageSize falls back to default', () => {
    const defaults = createDefaultAisleResultsFilters();
    expect(parseAisleResultsFilters(new URLSearchParams('pageSize=7')).pageSize).toBe(
      defaults.pageSize
    );
    expect(parseAisleResultsFilters(new URLSearchParams('pageSize=50')).pageSize).toBe(50);
  });

  it('invalid filter falls back to all', () => {
    expect(parseAisleResultsFilters(new URLSearchParams('filter=needs-review')).filter).toBe(
      'all'
    );
    expect(parseAisleResultsFilters(new URLSearchParams('filter=needs_review')).filter).toBe(
      'needs_review'
    );
  });

  it('invalid tableSort falls back to photo', () => {
    expect(parseAisleResultsFilters(new URLSearchParams('tableSort=foo')).tableSort).toBe(
      'photo'
    );
  });

  it('disallowed sortBy becomes null', () => {
    expect(parseAisleResultsFilters(new URLSearchParams('sortBy=password')).sortBy).toBeNull();
  });

  it('invalid sortDir falls back to asc', () => {
    expect(parseAisleResultsFilters(new URLSearchParams('sortDir=up')).sortDir).toBe('asc');
  });

  it('write omits defaults', () => {
    const defaults = createDefaultAisleResultsFilters();
    const written = writeAisleResultsFilters(
      new URLSearchParams('jobId=j1&foo=bar'),
      defaults,
      defaults
    );
    expect(written.get('jobId')).toBe('j1');
    expect(written.get('foo')).toBe('bar');
    expect(written.get('filter')).toBeNull();
    expect(written.get('page')).toBeNull();
    expect(written.get('q')).toBeNull();
  });

  it('write preserves jobId and unknown params', () => {
    const defaults = createDefaultAisleResultsFilters();
    const written = writeAisleResultsFilters(
      new URLSearchParams('jobId=j9&experiment=1'),
      { ...defaults, filter: 'qty_zero', q: 'x' },
      defaults
    );
    expect(written.get('jobId')).toBe('j9');
    expect(written.get('experiment')).toBe('1');
    expect(written.get('filter')).toBe('qty_zero');
    expect(written.get('q')).toBe('x');
  });

  it('write removes empty q', () => {
    const defaults = createDefaultAisleResultsFilters();
    const written = writeAisleResultsFilters(
      new URLSearchParams('q=old'),
      { ...defaults, q: '   ' },
      defaults
    );
    expect(written.get('q')).toBeNull();
  });

  it('normalizes spaces in q', () => {
    expect(parseAisleResultsFilters(new URLSearchParams('q=%20ABC%20')).q).toBe('ABC');
  });

  it('round trip parse → write → parse', () => {
    const defaults = createDefaultAisleResultsFilters();
    const original = {
      filter: 'low_confidence' as const,
      q: 'SKU-1',
      page: 3,
      pageSize: 100,
      tableSort: 'priority' as const,
      sortBy: 'qty' as const,
      sortDir: 'desc' as const,
    };
    const written = writeAisleResultsFilters(new URLSearchParams('jobId=keep'), original, defaults);
    const round = parseAisleResultsFilters(written, defaults);
    expect(round).toEqual(original);
    expect(written.get('jobId')).toBe('keep');
  });

  it('areAisleResultsFiltersEqual compares normalized values', () => {
    const a = createDefaultAisleResultsFilters();
    expect(areAisleResultsFiltersEqual(a, { ...a, q: '  ' })).toBe(true);
    expect(areAisleResultsFiltersEqual(a, { ...a, filter: 'needs_review' })).toBe(false);
  });

  it('mergeAisleResultsFilterPatch can reset page', () => {
    const current = { ...createDefaultAisleResultsFilters(), page: 4 };
    const next = mergeAisleResultsFilterPatch(
      current,
      { filter: 'qty_zero' },
      { resetPage: true }
    );
    expect(next.page).toBe(1);
    expect(next.filter).toBe('qty_zero');
  });

  it('forces sortDir to asc when sortBy is null', () => {
    const n = normalizeAisleResultsFilters({
      ...createDefaultAisleResultsFilters(),
      sortBy: null,
      sortDir: 'desc',
    });
    expect(n.sortBy).toBeNull();
    expect(n.sortDir).toBe('asc');
  });

  it('isAisleResultsSortColumn rejects unknown columns', () => {
    expect(isAisleResultsSortColumn('sku')).toBe(true);
    expect(isAisleResultsSortColumn('password')).toBe(false);
  });
});
