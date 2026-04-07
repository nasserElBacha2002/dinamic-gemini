/**
 * Epic 3 — Display helpers for ReviewStatus in the Results overview.
 * Keeps label and chip color consistent for the visible Result model.
 */

import type { ReviewStatus } from '../types';
import type { ChipColorType } from '../../../components/ui/types';
import type { StatusBadgeSemantic } from '../../../components/ui';

const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = {
  DETECTED: 'Detected',
  CONFIRMED: 'Confirmed',
  NEEDS_REVIEW: 'Needs review',
  IMAGE_MISMATCH: 'Wrong image',
  MISSING: 'Missing',
  INVALID: 'Invalid',
  NOT_COUNTABLE: 'Not countable',
};

const REVIEW_STATUS_COLOR: Record<ReviewStatus, ChipColorType> = {
  DETECTED: 'primary',
  CONFIRMED: 'success',
  NEEDS_REVIEW: 'warning',
  IMAGE_MISMATCH: 'warning',
  MISSING: 'default',
  INVALID: 'error',
  NOT_COUNTABLE: 'default',
};

export function getReviewStatusLabel(status: ReviewStatus): string {
  return REVIEW_STATUS_LABEL[status] ?? status;
}

export function getReviewStatusColor(status: ReviewStatus): ChipColorType {
  return REVIEW_STATUS_COLOR[status] ?? 'default';
}

/** Maps visible review status to redesign StatusBadge semantics (Sprint 4.1). */
export function reviewStatusToBadgeSemantic(status: ReviewStatus): StatusBadgeSemantic {
  switch (status) {
    case 'CONFIRMED':
      return 'success';
    case 'NEEDS_REVIEW':
    case 'DETECTED':
    case 'IMAGE_MISMATCH':
      return 'review';
    case 'INVALID':
      return 'error';
    case 'MISSING':
    case 'NOT_COUNTABLE':
    default:
      return 'neutral';
  }
}
