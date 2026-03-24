/**
 * Epic 3 — Quick filter logic for the Results overview.
 * Typed, explicit, and easy to extend.
 */

import type { ResultSummary } from '../types';
import { LOW_CONFIDENCE_THRESHOLD } from '../constants';

export type ResultsFilterKind =
  | 'all'
  | 'needs_review'
  | 'valid_traceability'
  | 'non_valid_traceability'
  | 'qty_zero'
  | 'low_confidence';

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
      case 'valid_traceability':
        return r.traceabilityStatus === 'VALID';
      case 'non_valid_traceability':
        return (
          r.traceabilityStatus === 'MISSING' ||
          r.traceabilityStatus === 'INVALID' ||
          r.traceabilityStatus === 'UNVALIDATED'
        );
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
