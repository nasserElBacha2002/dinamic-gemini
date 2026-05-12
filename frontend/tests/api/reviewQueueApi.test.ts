import { describe, it, expect } from 'vitest';
import { buildReviewQueueQueryString } from '../../src/api/reviewQueueApi';

describe('buildReviewQueueQueryString', () => {
  it('returns empty string when query is undefined', () => {
    expect(buildReviewQueueQueryString()).toBe('');
    expect(buildReviewQueueQueryString(undefined)).toBe('');
  });

  it('returns empty string when all fields are blank or omitted', () => {
    expect(
      buildReviewQueueQueryString({
        inventory_id: '   ',
        aisle_id: '',
        sku_contains: '  ',
      })
    ).toBe('');
  });

  it('trims inventory_id', () => {
    expect(buildReviewQueueQueryString({ inventory_id: '  inv-1  ' })).toBe('?inventory_id=inv-1');
  });

  it('lowercases traceability after trim', () => {
    expect(buildReviewQueueQueryString({ traceability: '  PENDING  ' })).toBe('?traceability=pending');
  });

  it('lowercases position_status after trim', () => {
    expect(buildReviewQueueQueryString({ position_status: ' Open ' })).toBe('?position_status=open');
  });

  it('emits both booleans when true and false', () => {
    expect(
      buildReviewQueueQueryString({
        has_evidence: true,
        qty_zero: false,
      })
    ).toBe('?has_evidence=true&qty_zero=false');
  });

  it('omits null booleans', () => {
    expect(buildReviewQueueQueryString({ has_evidence: null, qty_zero: null })).toBe('');
  });

  it('omits page below 1 but keeps valid page_size', () => {
    expect(buildReviewQueueQueryString({ page: 0, page_size: 25 })).toBe('?page_size=25');
  });

  it('preserves param order for a combined filter', () => {
    expect(
      buildReviewQueueQueryString({
        inventory_id: 'inv-1',
        traceability: 'FULL',
        sort_by: '  code  ',
        page: 2,
        page_size: 50,
      })
    ).toBe('?inventory_id=inv-1&traceability=full&sort_by=code&page=2&page_size=50');
  });

  it('omits NaN confidence but serializes finite numbers as before', () => {
    expect(
      buildReviewQueueQueryString({
        min_confidence: Number.NaN,
        max_confidence: 0.9,
      })
    ).toBe('?max_confidence=0.9');
  });

  it('serializes non-finite confidence when not NaN (parity with String)', () => {
    expect(buildReviewQueueQueryString({ min_confidence: Number.POSITIVE_INFINITY })).toBe(
      '?min_confidence=Infinity'
    );
  });
});
