/**
 * Map current API/domain status strings to target taxonomies in screenTargets.ts (Plan / Re diseño §11).
 *
 * Direction: backend/API value → documented UI taxonomy.
 * When no doc counterpart exists, `target` is null; use `raw` for labels/badges.
 *
 * For result review, `target === 'confirmed'` is ambiguous in the plan docs: use `resolutionKind`
 * to distinguish human confirmation from auto-accept (detected + !needs_review).
 */

import type {
  TargetAisleStatus,
  TargetInventoryStatus,
  TargetResultReviewStatus,
  TraceabilityPlanLabel,
} from './screenTargets';
import { LOW_CONFIDENCE_THRESHOLD } from '../constants/reviewThresholds';

/** Shared with Results KPIs/filters via src/constants/reviewThresholds.ts */
export { LOW_CONFIDENCE_THRESHOLD };

/**
 * How the position relates to review / confirmation semantics.
 * Use with `target` — especially when target is `confirmed`, check `resolutionKind`.
 */
export type ResultReviewResolutionKind =
  | 'pending_review'
  | 'human_confirmed'
  | 'auto_accepted'
  | 'corrected'
  | 'image_mismatch'
  | 'deleted'
  | 'unknown';

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
  /** Semantic disambiguation; do not infer from `target` or `isApproximate` alone. */
  resolutionKind: ResultReviewResolutionKind;
}

export interface QualityAlignmentSignals {
  /**
   * Traceability dimension (plan §11); orthogonal to `lowConfidence`.
   * `unvalidated` / empty API → null (no plan bucket).
   */
  traceabilityTarget: TraceabilityPlanLabel | null;
  /** Separate dimension: confidence vs LOW_CONFIDENCE_THRESHOLD. */
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
 * Plan: pending_review | confirmed | corrected | image_mismatch | deleted.
 *
 * `target === 'confirmed'` covers both human-confirmed (`reviewed`) and auto-accepted
 * (`detected` + !needs_review); use `resolutionKind` to tell them apart.
 * Terminal `review_resolution === 'image_mismatch'` maps to its own target (not unknown / confirmed).
 */
export function alignPositionToResultReviewTarget(
  positionStatus: string | null | undefined,
  needsReview: boolean,
  reviewResolution?: string | null
): ResultReviewAlignment {
  const raw = norm(positionStatus);
  const res = norm(reviewResolution);
  if (raw === 'detected' && needsReview) {
    return {
      rawPositionStatus: raw,
      needsReview,
      target: 'pending_review',
      isApproximate: false,
      resolutionKind: 'pending_review',
    };
  }
  if (raw === 'detected' && !needsReview) {
    return {
      rawPositionStatus: raw,
      needsReview,
      target: 'confirmed',
      isApproximate: true,
      resolutionKind: 'auto_accepted',
    };
  }
  if (raw === 'reviewed') {
    if (res === 'image_mismatch') {
      return {
        rawPositionStatus: raw,
        needsReview,
        target: 'image_mismatch',
        isApproximate: false,
        resolutionKind: 'image_mismatch',
      };
    }
    return {
      rawPositionStatus: raw,
      needsReview,
      target: 'confirmed',
      isApproximate: false,
      resolutionKind: 'human_confirmed',
    };
  }
  if (raw === 'corrected') {
    return {
      rawPositionStatus: raw,
      needsReview,
      target: 'corrected',
      isApproximate: false,
      resolutionKind: 'corrected',
    };
  }
  if (raw === 'deleted') {
    return {
      rawPositionStatus: raw,
      needsReview,
      target: 'deleted',
      isApproximate: false,
      resolutionKind: 'deleted',
    };
  }
  return {
    rawPositionStatus: raw,
    needsReview,
    target: null,
    isApproximate: false,
    resolutionKind: 'unknown',
  };
}

/**
 * Quality: two dimensions — traceability (plan labels) and low confidence (threshold).
 * API traceability: valid | missing | invalid | unvalidated.
 */
export function deriveQualityAlignmentSignals(
  apiTraceability: string | null | undefined,
  confidence: number | null | undefined,
  options?: { lowConfidenceThreshold?: number }
): QualityAlignmentSignals {
  const threshold = options?.lowConfidenceThreshold ?? LOW_CONFIDENCE_THRESHOLD;
  const lowConfidence = confidence != null && confidence < threshold;
  const t = norm(apiTraceability);
  const traceabilityTarget: TraceabilityPlanLabel | null =
    t === 'valid'
      ? 'valid_traceability'
      : t === 'invalid' || t === 'missing'
        ? 'invalid_traceability'
        : null;
  return { traceabilityTarget, lowConfidence };
}
