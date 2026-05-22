/**
 * Epic 3 / Sprint 4.1 — Results KPI and filter selectors.
 */

import { describe, it, expect } from 'vitest';
import {
  computeResultsKpi,
  isExcludedFromCountedTotals,
} from '../src/features/results/selectors/resultsKpi';
import { filterResults, type ResultsFilterKind } from '../src/features/results/selectors/resultsFilters';
import type { ResultSummary } from '../src/features/results/types';

function makeResult(overrides: Partial<ResultSummary> = {}): ResultSummary {
  return {
    id: 'r1',
    sku: 'SKU',
    positionCode: null,
    detectedQty: 1,
    correctedQty: null,
    resolvedQty: null,
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
    expect(kpi.countableResults).toBe(0);
    expect(kpi.needsReview).toBe(0);
    expect(kpi.invalidTraceability).toBe(0);
    expect(kpi.qtyZero).toBe(0);
    expect(kpi.withEvidence).toBe(0);
    expect(kpi.lowConfidence).toBe(0);
    expect(kpi.aisleTotalCounted).toBe(0);
  });

  it('counts total and withEvidence', () => {
    const results = [
      makeResult({ id: 'a', hasEvidence: true }),
      makeResult({ id: 'b', hasEvidence: false }),
    ];
    const kpi = computeResultsKpi(results);
    expect(kpi.total).toBe(2);
    expect(kpi.countableResults).toBe(2);
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

  it('counts invalidTraceability as INVALID only', () => {
    const results = [
      makeResult({ traceabilityStatus: 'VALID' }),
      makeResult({ traceabilityStatus: 'INVALID' }),
      makeResult({ traceabilityStatus: 'MISSING' }),
    ];
    const kpi = computeResultsKpi(results);
    expect(kpi.invalidTraceability).toBe(1);
  });

  it('counts qtyZero when resolved display qty (resolvedQty ?? detectedQty) is exactly 0', () => {
    const results = [
      makeResult({ detectedQty: 0, resolvedQty: null }),
      makeResult({ detectedQty: 5, resolvedQty: 0, correctedQty: 0 }),
      makeResult({ detectedQty: null, resolvedQty: null }),
      makeResult({ detectedQty: 5 }),
    ];
    const kpi = computeResultsKpi(results);
    expect(kpi.qtyZero).toBe(2);
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

  it('excludes review INVALID from aisleTotalCounted and countableResults', () => {
    const results = [
      makeResult({ id: 'a', detectedQty: 1, resolvedQty: null, reviewStatus: 'DETECTED' }),
      makeResult({ id: 'b', detectedQty: 1, resolvedQty: null, reviewStatus: 'DETECTED' }),
      makeResult({ id: 'c', detectedQty: 1, resolvedQty: null, reviewStatus: 'DETECTED' }),
      makeResult({ id: 'd', detectedQty: 1, resolvedQty: null, reviewStatus: 'DETECTED' }),
      makeResult({
        id: 'inv',
        detectedQty: 1,
        resolvedQty: null,
        reviewStatus: 'INVALID',
      }),
    ];
    const kpi = computeResultsKpi(results);
    expect(kpi.total).toBe(5);
    expect(kpi.countableResults).toBe(4);
    expect(kpi.aisleTotalCounted).toBe(4);
  });

  it('excludes large invalid quantity from aisleTotalCounted (not 103)', () => {
    const results = [
      makeResult({ id: 'a', detectedQty: 1, resolvedQty: null, reviewStatus: 'DETECTED' }),
      makeResult({ id: 'b', detectedQty: 1, resolvedQty: null, reviewStatus: 'DETECTED' }),
      makeResult({ id: 'c', detectedQty: 1, resolvedQty: null, reviewStatus: 'DETECTED' }),
      makeResult({ id: 'd', detectedQty: 1, resolvedQty: null, reviewStatus: 'DETECTED' }),
      makeResult({
        id: 'inv',
        detectedQty: 99,
        resolvedQty: 99,
        reviewStatus: 'INVALID',
      }),
    ];
    const kpi = computeResultsKpi(results);
    expect(kpi.countableResults).toBe(4);
    expect(kpi.aisleTotalCounted).toBe(4);
  });

  it('still counts quantity when only traceability is INVALID (not review INVALID)', () => {
    const results = [
      makeResult({
        id: 't',
        detectedQty: 3,
        resolvedQty: null,
        reviewStatus: 'DETECTED',
        traceabilityStatus: 'INVALID',
      }),
    ];
    const kpi = computeResultsKpi(results);
    expect(kpi.total).toBe(1);
    expect(kpi.countableResults).toBe(1);
    expect(kpi.invalidTraceability).toBe(1);
    expect(kpi.aisleTotalCounted).toBe(3);
  });
});

describe('isExcludedFromCountedTotals', () => {
  it('is true only for review INVALID', () => {
    expect(isExcludedFromCountedTotals(makeResult({ reviewStatus: 'INVALID' }))).toBe(true);
    expect(isExcludedFromCountedTotals(makeResult({ reviewStatus: 'DETECTED' }))).toBe(false);
    expect(
      isExcludedFromCountedTotals(
        makeResult({ reviewStatus: 'DETECTED', traceabilityStatus: 'INVALID' })
      )
    ).toBe(false);
  });
});

describe('filterResults', () => {
  const results: ResultSummary[] = [
    makeResult({
      id: '1',
      needsReview: true,
      traceabilityStatus: 'MISSING',
      detectedQty: 0,
      confidence: 0.3,
      hasEvidence: false,
    }),
    makeResult({
      id: '2',
      needsReview: false,
      traceabilityStatus: 'VALID',
      detectedQty: 2,
      confidence: 0.95,
      hasEvidence: true,
    }),
    makeResult({
      id: '3',
      needsReview: true,
      traceabilityStatus: 'INVALID',
      detectedQty: 1,
      confidence: 0.9,
      hasEvidence: true,
    }),
  ];

  it('all returns full list', () => {
    expect(filterResults(results, 'all')).toHaveLength(3);
  });

  it('needs_review filters by needsReview', () => {
    const out = filterResults(results, 'needs_review');
    expect(out.map((r) => r.id).sort()).toEqual(['1', '3']);
  });

  it('invalid_traceability filters by INVALID', () => {
    const out = filterResults(results, 'invalid_traceability');
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe('3');
  });

  it('missing_evidence filters by !hasEvidence', () => {
    const out = filterResults(results, 'missing_evidence');
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe('1');
  });

  it('qty_zero filters by resolved display quantity 0', () => {
    const out = filterResults(results, 'qty_zero');
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe('1');
  });

  it('low_confidence filters by confidence < 0.5', () => {
    const out = filterResults(results, 'low_confidence');
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe('1');
  });

  it('exhaustive filter kind', () => {
    const kinds: ResultsFilterKind[] = [
      'all',
      'needs_review',
      'low_confidence',
      'qty_zero',
      'invalid_traceability',
      'missing_evidence',
    ];
    for (const k of kinds) {
      expect(Array.isArray(filterResults(results, k))).toBe(true);
    }
  });
});
