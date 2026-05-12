import { describe, it, expect } from 'vitest';
import { buildAislePositionsQueryString } from '../../src/api/jobsApi';

describe('buildAislePositionsQueryString', () => {
  it('returns empty string when query is undefined', () => {
    expect(buildAislePositionsQueryString()).toBe('');
    expect(buildAislePositionsQueryString(undefined)).toBe('');
  });

  it('returns empty string for empty object', () => {
    expect(buildAislePositionsQueryString({})).toBe('');
  });

  it('omits blank status and sku_filter', () => {
    expect(
      buildAislePositionsQueryString({
        status: '   ',
        sku_filter: '',
      })
    ).toBe('');
  });

  it('trims sku_filter without lowercasing status', () => {
    expect(buildAislePositionsQueryString({ sku_filter: '  ABC-123  ' })).toBe('?sku_filter=ABC-123');
    expect(buildAislePositionsQueryString({ status: '  PENDING  ' })).toBe('?status=PENDING');
  });

  it('omits page below 1 but keeps valid page_size', () => {
    expect(buildAislePositionsQueryString({ page: 0, page_size: 25 })).toBe('?page_size=25');
  });

  it('emits needs_review for both true and false when set', () => {
    expect(buildAislePositionsQueryString({ needs_review: true })).toBe('?needs_review=true');
    expect(buildAislePositionsQueryString({ needs_review: false })).toBe('?needs_review=false');
  });

  it('emits consolidate_by_sku only when false', () => {
    expect(buildAislePositionsQueryString({ consolidate_by_sku: false })).toBe('?consolidate_by_sku=false');
    expect(buildAislePositionsQueryString({ consolidate_by_sku: true })).toBe('');
    expect(buildAislePositionsQueryString({ consolidate_by_sku: null })).toBe('');
  });

  it('omits NaN min_confidence', () => {
    expect(buildAislePositionsQueryString({ min_confidence: Number.NaN })).toBe('');
  });

  it('serializes finite min_confidence', () => {
    expect(buildAislePositionsQueryString({ min_confidence: 0.5 })).toBe('?min_confidence=0.5');
  });

  it('serializes non-finite min_confidence when not NaN (String parity)', () => {
    expect(buildAislePositionsQueryString({ min_confidence: Number.POSITIVE_INFINITY })).toBe(
      '?min_confidence=Infinity'
    );
  });

  it('preserves param order for combined filters', () => {
    expect(
      buildAislePositionsQueryString({
        status: 'pending',
        sku_filter: 'ABC-123',
        consolidate_by_sku: false,
        page: 2,
        page_size: 50,
      })
    ).toBe('?status=pending&sku_filter=ABC-123&page=2&page_size=50&consolidate_by_sku=false');
  });
});
