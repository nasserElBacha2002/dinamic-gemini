/**
 * Map current API/domain status strings to target taxonomies in screenTargets.ts (Plan / Re diseño §11).
 *
 * Direction: backend/API value → documented UI taxonomy.
 * When no doc counterpart exists, `target` is null; use `raw` for labels/badges.
 */

import type {
  TargetAisleStatus,
  TargetInventoryStatus,
  TargetQualityStatus,
  TargetResultReviewStatus,
} from './screenTargets';

/** Matches features/results/constants LOW_CONFIDENCE_THRESHOLD (avoid importing features from types). */
export const ALIGNMENT_LOW_CONFIDENCE_THRESHOLD = 0.5;

export interface InventoryStatusAlignment {
  raw: string;
  target: TargetInventoryStatus | null;
  /** True when `raw` is not a literal plan enum but maps into a doc bucket. */
  isApproximate: boolean;
}

export interface AisleStatusAlignment {
  raw: string;
  target: TargetAisleStatus | null;
  isApproximate: boolean;
}

export interface ResultReviewAlignment {
  rawPositionStatus: string;
  needsReview: boolean;
  target: TargetResultReviewStatus | null;
  isApproximate: boolean;
}

export interface QualityAlignmentSignals {
  /**
   * Plan quality axis from API traceability (valid → valid; invalid/missing → invalid).
   * `unvalidated` has no plan label — null.
   */
  traceabilityTarget: Extract<
    TargetQualityStatus,
    'valid_traceability' | 'invalid_traceability'
  > | null;
  /** Plan `low_confidence` axis; independent of traceability. */
  lowConfidence: boolean;
}

function norm(s: string | null | undefined): string {
  return (s ?? '').trim().toLowerCase();
}

/**
 * Inventory: API draft | processing | in_review | completed | failed.
 * Plan: draft | in_progress | completed | archived.
 */
export function alignInventoryApiStatusToTarget(
  status: string | null | undefined
): InventoryStatusAlignment {
  const raw = norm(status);
  if (!raw) return { raw: '', target: null, isApproximate: false };
  switch (raw) {
    case 'draft':
      return { raw, target: 'draft', isApproximate: false };
    case 'completed':
      return { raw, target: 'completed', isApproximate: false };
    case 'processing':
    case 'in_review':
      return { raw, target: 'in_progress', isApproximate: true };
    case 'failed':
      return { raw, target: null, isApproximate: false };
    default:
      return { raw, target: null, isApproximate: false };
  }
}

/**
 * Aisle: API created | assets_uploaded | queued | processing | processed | in_review | completed | failed.
 * Plan: empty | assets_uploaded | processing | processed | error.
 */
export function alignAisleApiStatusToTarget(
  status: string | null | undefined
): AisleStatusAlignment {
  const raw = norm(status);
  if (!raw) return { raw: '', target: null, isApproximate: false };
  switch (raw) {
    case 'created':
      return { raw, target: 'empty', isApproximate: true };
    case 'assets_uploaded':
      return { raw, target: 'assets_uploaded', isApproximate: false };
    case 'queued':
    case 'processing':
      return { raw, target: 'processing', isApproximate: raw === 'queued' };
    case 'processed':
      return { raw, target: 'processed', isApproximate: false };
    case 'in_review':
    case 'completed':
      return { raw, target: 'processed', isApproximate: true };
    case 'failed':
      return { raw, target: 'error', isApproximate: true };
    default:
      return { raw, target: null, isApproximate: false };
  }
}

/**
 * Result: API position detected | reviewed | corrected | deleted + needs_review.
 * Plan: pending_review | confirmed | corrected | deleted.
 */
export function alignPositionToResultReviewTarget(
  positionStatus: string | null | undefined,
  needsReview: boolean
): ResultReviewAlignment {
  const raw = norm(positionStatus);
  if (raw === 'detected' && needsReview) {
    return {
      rawPositionStatus: raw,
      needsReview,
      target: 'pending_review',
      isApproximate: false,
    };
  }
  if (raw === 'detected' && !needsReview) {
    return {
      rawPositionStatus: raw,
      needsReview,
      target: 'confirmed',
      isApproximate: true,
    };
  }
  if (raw === 'reviewed') {
    return {
      rawPositionStatus: raw,
      needsReview,
      target: 'confirmed',
      isApproximate: false,
    };
  }
  if (raw === 'corrected') {
    return {
      rawPositionStatus: raw,
      needsReview,
      target: 'corrected',
      isApproximate: false,
    };
  }
  if (raw === 'deleted') {
    return {
      rawPositionStatus: raw,
      needsReview,
      target: 'deleted',
      isApproximate: false,
    };
  }
  return {
    rawPositionStatus: raw,
    needsReview,
    target: null,
    isApproximate: false,
  };
}

/**
 * Quality: plan valid_traceability | invalid_traceability | low_confidence.
 * API traceability: valid | missing | invalid | unvalidated.
 */
export function deriveQualityAlignmentSignals(
  apiTraceability: string | null | undefined,
  confidence: number | null | undefined,
  options?: { lowConfidenceThreshold?: number }
): QualityAlignmentSignals {
  const threshold = options?.lowConfidenceThreshold ?? ALIGNMENT_LOW_CONFIDENCE_THRESHOLD;
  const lowConfidence = confidence != null && confidence < threshold;
  const t = norm(apiTraceability);
  let traceabilityTarget: QualityAlignmentSignals['traceabilityTarget'] = null;
  if (t === 'valid') traceabilityTarget = 'valid_traceability';
  else if (t === 'invalid' || t === 'missing') traceabilityTarget = 'invalid_traceability';
  else if (t === 'unvalidated' || t === '') traceabilityTarget = null;
  else traceabilityTarget = null;
  return { traceabilityTarget, lowConfidence };
}
