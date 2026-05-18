/**
 * UI separation: result review status vs evidence/image mismatch.
 *
 * Backend stores image mismatch as review_resolution=image_mismatch with status=reviewed.
 * The visible model keeps reviewStatus=IMAGE_MISMATCH internally; display helpers map
 * review column to CONFIRMED and surface mismatch under evidence/traceability.
 */

import type { ReviewStatus } from '../types';
import type { ChipColorType } from '../../../components/ui/types';
import type { StatusBadgeSemantic } from '../../../components/ui';
import i18n from '../../../i18n';
import {
  getReviewStatusColor,
  getReviewStatusLabel,
  reviewStatusToBadgeSemantic,
} from './reviewStatusDisplay';

export function hasImageMismatchEvidenceIssue(reviewStatus: ReviewStatus): boolean {
  return reviewStatus === 'IMAGE_MISMATCH';
}

/** When true, traceability UI shows image-mismatch evidence instead of the API traceability chip. */
export function shouldReplaceTraceabilityWithImageMismatch(reviewStatus: ReviewStatus): boolean {
  return hasImageMismatchEvidenceIssue(reviewStatus);
}

/** Result-data review label: image mismatch rows are treated as reviewed/confirmed. */
export function getResultReviewStatusForDisplay(reviewStatus: ReviewStatus): ReviewStatus {
  return reviewStatus === 'IMAGE_MISMATCH' ? 'CONFIRMED' : reviewStatus;
}

export function getReviewStatusLabelForDisplay(reviewStatus: ReviewStatus): string {
  return getReviewStatusLabel(getResultReviewStatusForDisplay(reviewStatus));
}

export function getReviewStatusColorForDisplay(reviewStatus: ReviewStatus): ChipColorType {
  return getReviewStatusColor(getResultReviewStatusForDisplay(reviewStatus));
}

export function reviewStatusToBadgeSemanticForDisplay(
  reviewStatus: ReviewStatus
): StatusBadgeSemantic {
  return reviewStatusToBadgeSemantic(getResultReviewStatusForDisplay(reviewStatus));
}

export function getImageMismatchEvidenceLabel(short = false): string {
  const key = short ? 'results.evidence.image_mismatch_short' : 'results.evidence.image_mismatch';
  if (i18n.exists(key)) return i18n.t(key);
  return short ? 'Evidencia incorrecta' : 'Imagen no coincide';
}

export function getImageMismatchEvidenceHelp(): string {
  const key = 'results.evidence.image_mismatch_help';
  if (i18n.exists(key)) return i18n.t(key);
  return 'La imagen asociada no corresponde a este resultado.';
}
