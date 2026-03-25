import type { ResultSummary } from '../types';

/** Human-readable count origin for list/detail/quick review surfaces. */
export function getCountOriginLabel(
  result: Pick<ResultSummary, 'qtySource' | 'qtyInferenceReason'>
): string {
  const src = result.qtySource ?? 'detected';
  if (src === 'inferred' && result.qtyInferenceReason) {
    return `Inferred (${result.qtyInferenceReason})`;
  }
  if (src === 'inferred') return 'Inferred';
  if (src === 'merge_inferred') return 'Merge inferred';
  if (src === 'manual_review') return 'Manual review';
  if (src === 'label_explicit') return 'Label explicit';
  if (src === 'unknown') return 'Unknown';
  return 'Detected';
}
