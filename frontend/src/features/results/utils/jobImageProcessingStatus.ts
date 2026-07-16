/**
 * Presentation mapping for job image coverage `processing_status` (see backend
 * `ImageProcessingPresentationStatus`): pending | processing | processed_with_result |
 * processed_without_result | failed. Manual coverage uses `has_manual_result` on the card.
 */

import type { StatusBadgeSemantic } from '../../../components/ui/StatusBadge';
import i18n from '../../../i18n';

export type JobImageProcessingStatus =
  | 'pending'
  | 'processing'
  | 'processed_with_result'
  | 'processed_without_result'
  | 'failed';

export function jobImageProcessingStatusLabel(status: string | null | undefined): string {
  const s = (status ?? '').trim().toLowerCase();
  const key = `results.imageCoverage.card.processingStatus.${s}`;
  if (s && i18n.exists(key)) return i18n.t(key);
  return i18n.t('common.em_dash');
}

export function jobImageProcessingStatusSemantic(
  status: string | null | undefined
): StatusBadgeSemantic {
  const s = (status ?? '').trim().toLowerCase();
  switch (s) {
    case 'processed_with_result':
      return 'success';
    case 'processed_without_result':
      return 'warning';
    case 'failed':
      return 'error';
    case 'processing':
    case 'pending':
      return 'info';
    default:
      return 'neutral';
  }
}

export function isFailedProcessingStatus(status: string | null | undefined): boolean {
  return (status ?? '').trim().toLowerCase() === 'failed';
}
