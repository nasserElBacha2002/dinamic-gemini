import type { ResultSummary } from '../types';
import i18n from '../../../i18n';

/** Human-readable count origin for list/detail/quick review surfaces. */
export function getCountOriginLabel(result: Pick<ResultSummary, 'qtySource' | 'qtyInferenceReason'>): string {
  const src = result.qtySource ?? 'detected';
  if (src === 'inferred' && result.qtyInferenceReason) {
    return i18n.t('results.qty_origin.inferred_with_reason', { reason: result.qtyInferenceReason });
  }
  if (src === 'inferred') return i18n.t('results.qty_origin.inferred');
  if (src === 'merge_inferred') return i18n.t('results.qty_origin.merge_inferred');
  if (src === 'manual_review') return i18n.t('results.qty_origin.manual_review');
  if (src === 'label_explicit') return i18n.t('results.qty_origin.label_explicit');
  if (src === 'unknown') return i18n.t('results.qty_origin.unknown');
  return i18n.t('results.qty_origin.detected');
}
