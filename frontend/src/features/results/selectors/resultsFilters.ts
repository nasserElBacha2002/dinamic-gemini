/**
 * Epic 3 — Quick filter logic for the Results overview.
 * Typed, explicit, and easy to extend.
 */

import type { ResultSummary } from '../types';
import { LOW_CONFIDENCE_THRESHOLD } from '../constants';

export type ResultsFilterKind =
  | 'all'
  | 'needs_review'
  | 'low_confidence'
  | 'qty_zero'
  | 'invalid_traceability'
  | 'missing_evidence';

/**
 * Filter results by the given filter kind.
 */
export function filterResults(
  results: ResultSummary[],
  filter: ResultsFilterKind
): ResultSummary[] {
  if (filter === 'all') return results;

  return results.filter((r) => {
    switch (filter) {
      case 'needs_review':
        return r.needsReview;
      case 'invalid_traceability':
        return r.traceabilityStatus === 'INVALID';
      case 'missing_evidence':
        return !r.hasEvidence;
      case 'qty_zero': {
        const q = r.resolvedQty ?? r.detectedQty;
        return q === 0;
      }
      case 'low_confidence':
        return r.confidence != null && r.confidence < LOW_CONFIDENCE_THRESHOLD;
      default:
        return true;
    }
  });
}
