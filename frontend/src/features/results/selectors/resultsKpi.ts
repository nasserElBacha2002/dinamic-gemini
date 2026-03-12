/**
 * Epic 3 — KPI aggregation from ResultSummary[] for the Results overview page.
 * Centralized, typed, and easy to test.
 */

import type { ResultSummary } from '../types';
import { LOW_CONFIDENCE_THRESHOLD } from '../constants';

export interface ResultsKpi {
  total: number;
  needsReview: number;
  validTraceability: number;
  /** Count of results with traceability not valid (MISSING, INVALID, UNVALIDATED). */
  nonValidTraceability: number;
  /** Count of results with detectedQty exactly 0 (excludes null/unknown). */
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
    validTraceability: 0,
    nonValidTraceability: 0,
    qtyZero: 0,
    withEvidence: 0,
    lowConfidence: 0,
  };

  for (const r of results) {
    if (r.needsReview) kpi.needsReview += 1;
    if (r.traceabilityStatus === 'VALID') kpi.validTraceability += 1;
    if (
      r.traceabilityStatus === 'MISSING' ||
      r.traceabilityStatus === 'INVALID' ||
      r.traceabilityStatus === 'UNVALIDATED'
    ) {
      kpi.nonValidTraceability += 1;
    }
    if (r.detectedQty === 0) kpi.qtyZero += 1;
    if (r.hasEvidence) kpi.withEvidence += 1;
    if (r.confidence != null && r.confidence < LOW_CONFIDENCE_THRESHOLD) {
      kpi.lowConfidence += 1;
    }
  }

  return kpi;
}
