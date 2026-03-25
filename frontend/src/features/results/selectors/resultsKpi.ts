/**
 * Epic 3 — KPI aggregation from ResultSummary[] for the Results overview page.
 * Centralized, typed, and easy to test.
 */

import type { ResultSummary } from '../types';
import { LOW_CONFIDENCE_THRESHOLD } from '../constants';

export interface ResultsKpi {
  total: number;
  needsReview: number;
  /** Traceability explicitly INVALID (not MISSING / UNVALIDATED). */
  invalidTraceability: number;
  /** Count of results with resolved display quantity exactly 0 (resolvedQty ?? detectedQty). */
  qtyZero: number;
  withEvidence: number;
  /** Results with confidence < threshold (when confidence is present). */
  lowConfidence: number;
}

/**
 * Compute page-level summary metrics from a list of results.
 */
export function computeResultsKpi(results: ResultSummary[]): ResultsKpi {
  const kpi: ResultsKpi = {
    total: results.length,
    needsReview: 0,
    invalidTraceability: 0,
    qtyZero: 0,
    withEvidence: 0,
    lowConfidence: 0,
  };

  for (const r of results) {
    if (r.needsReview) kpi.needsReview += 1;
    if (r.traceabilityStatus === 'INVALID') kpi.invalidTraceability += 1;
    {
      const q = r.resolvedQty ?? r.detectedQty;
      if (q === 0) kpi.qtyZero += 1;
    }
    if (r.hasEvidence) kpi.withEvidence += 1;
    if (r.confidence != null && r.confidence < LOW_CONFIDENCE_THRESHOLD) {
      kpi.lowConfidence += 1;
    }
  }

  return kpi;
}
