/**
 * Epic 3 — Tests for results KPI and filter selectors.
 */

import { describe, it, expect } from 'vitest';
import { computeResultsKpi } from '../src/features/results/selectors/resultsKpi';
import { filterResults, type ResultsFilterKind } from '../src/features/results/selectors/resultsFilters';
import type { ResultSummary } from '../src/features/results/types';

function makeResult(overrides: Partial<ResultSummary> = {}): ResultSummary {
  return {
    id: 'r1',
    sku: 'SKU',
    detectedQty: 1,
    confidence: 0.9,
    reviewStatus: 'DETECTED',
    traceabilityStatus: 'VALID',
    needsReview: false,
    updatedAt: '2024-01-01T00:00:00Z',
    hasEvidence: true,
    ...overrides,
  };
}

describe('computeResultsKpi', () => {
  it('returns zeros for empty list', () => {
    const kpi = computeResultsKpi([]);
    expect(kpi.total).toBe(0);
    expect(kpi.needsReview).toBe(0);
    expect(kpi.validTraceability).toBe(0);
    expect(kpi.nonValidTraceability).toBe(0);
    expect(kpi.qtyZero).toBe(0);
    expect(kpi.withEvidence).toBe(0);
    expect(kpi.lowConfidence).toBe(0);
  });

  it('counts total and withEvidence', () => {
    const results = [
      makeResult({ id: 'a', hasEvidence: true }),
      makeResult({ id: 'b', hasEvidence: false }),
    ];
    const kpi = computeResultsKpi(results);
    expect(kpi.total).toBe(2);
    expect(kpi.withEvidence).toBe(1);
  });

  it('counts needsReview', () => {
    const results = [
      makeResult({ needsReview: true }),
      makeResult({ needsReview: false }),
    ];
    const kpi = computeResultsKpi(results);
    expect(kpi.needsReview).toBe(1);
  });

  it('counts valid vs non-valid traceability', () => {
    const results = [
      makeResult({ traceabilityStatus: 'VALID' }),
      makeResult({ traceabilityStatus: 'MISSING' }),
      makeResult({ traceabilityStatus: 'UNVALIDATED' }),
    ];
    const kpi = computeResultsKpi(results);
    expect(kpi.validTraceability).toBe(1);
    expect(kpi.nonValidTraceability).toBe(2);
  });

  it('counts qtyZero (only exact 0, not null)', () => {
    const results = [
      makeResult({ detectedQty: 0 }),
      makeResult({ detectedQty: null }),
      makeResult({ detectedQty: 5 }),
    ];
    const kpi = computeResultsKpi(results);
    expect(kpi.qtyZero).toBe(1);
  });

  it('counts lowConfidence', () => {
    const results = [
      makeResult({ confidence: 0.3 }),
      makeResult({ confidence: 0.9 }),
      makeResult({ confidence: null }),
    ];
    const kpi = computeResultsKpi(results);
    expect(kpi.lowConfidence).toBe(1);
  });
});

describe('filterResults', () => {
  const results: ResultSummary[] = [
    makeResult({ id: '1', needsReview: true, traceabilityStatus: 'MISSING', detectedQty: 0, confidence: 0.3 }),
    makeResult({ id: '2', needsReview: false, traceabilityStatus: 'VALID', detectedQty: 2, confidence: 0.95 }),
  ];

  it('all returns full list', () => {
    expect(filterResults(results, 'all')).toHaveLength(2);
  });

  it('needs_review filters by needsReview', () => {
    const out = filterResults(results, 'needs_review');
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe('1');
  });

  it('valid_traceability filters by VALID', () => {
    const out = filterResults(results, 'valid_traceability');
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe('2');
  });

  it('non_valid_traceability includes MISSING, INVALID, UNVALIDATED', () => {
    const out = filterResults(results, 'non_valid_traceability');
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe('1');
  });

  it('qty_zero filters by detectedQty exactly 0', () => {
    const out = filterResults(results, 'qty_zero');
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe('1');
  });

  it('low_confidence filters by confidence < 0.5', () => {
    const out = filterResults(results, 'low_confidence');
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe('1');
  });
});
