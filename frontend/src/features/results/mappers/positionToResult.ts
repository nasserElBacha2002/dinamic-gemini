/**
 * v3.1.1 — Map backend position/evidence/detail responses to Result-centric visible model (Epic 1).
 *
 * Single place to adapt API snake_case and backend status values to the frontend
 * ResultSummary / ResultDetail contracts. Keeps UI decoupled from API shape.
 */

import type {
  PositionSummary,
  PositionDetailResponse,
  EvidenceSummary,
  ReviewActionSummary,
} from '../../../api/types';
import type {
  ResultSummary,
  ResultDetail,
  ResultEvidence,
  ReviewHistoryItem,
  ReviewStatus,
  TraceabilityStatus,
} from '../types';
import { getSummaryString } from './detectedSummary';

/** Backend traceability is lowercase; visible model uses uppercase. */
export function mapTraceabilityToVisible(
  status: string | null | undefined
): TraceabilityStatus {
  const s = (status ?? '').trim().toLowerCase();
  if (s === 'valid') return 'VALID';
  if (s === 'missing') return 'MISSING';
  if (s === 'invalid') return 'INVALID';
  if (s === 'unvalidated') return 'UNVALIDATED';
  return 'UNVALIDATED';
}

/** Map position status + needs_review to visible ReviewStatus.
 * Accepts null/undefined status safely.
 *
 * Current mapping (Epic 1): backend position status is one of detected | reviewed | corrected | deleted.
 * - NEEDS_REVIEW: when needs_review is true and status is detected.
 * - DETECTED: detected and !needs_review.
 * - CONFIRMED: reviewed or corrected.
 * - INVALID: deleted (domain may refine this in a later epic; treated as non-reviewable).
 *
 * MISSING and NOT_COUNTABLE are part of the visible ReviewStatus type but are not produced by this
 * mapper in Epic 1; they may be introduced when the decision layer or report shape exposes them.
 */
export function mapPositionStatusToReviewStatus(
  status: string | null | undefined,
  needsReview: boolean
): ReviewStatus {
  const s = (status ?? '').trim().toLowerCase();
  if (needsReview && s === 'detected') return 'NEEDS_REVIEW';
  switch (s) {
    case 'detected':
      return 'DETECTED';
    case 'reviewed':
    case 'corrected':
      return 'CONFIRMED';
    case 'deleted':
      return 'INVALID';
    default:
      return 'DETECTED';
  }
}

/** Map list position (API) to ResultSummary. v3.2.5 Block 4: has_evidence is canonical; fallback only for transitional payloads that omit it. */
export function mapPositionSummaryToResultSummary(
  p: PositionSummary
): ResultSummary {
  const hasEvidence =
    typeof p.has_evidence === 'boolean'
      ? p.has_evidence
      : Boolean(
          p.primary_evidence_id != null && String(p.primary_evidence_id).trim() !== ''
        );
  const resolvedQty =
    p.corrected_quantity != null
      ? p.corrected_quantity
      : p.qty ?? null;

  return {
    id: p.id,
    sku: p.sku ?? null,
    detectedQty: p.detected_quantity ?? null,
    correctedQty: p.corrected_quantity ?? null,
    resolvedQty,
    qtySource: p.qtySource ?? 'detected',
    qtyResolved: p.qtyResolved ?? null,
    qtyInferenceReason: p.qtyInferenceReason ?? null,
    confidence: p.confidence ?? null,
    reviewStatus: mapPositionStatusToReviewStatus(p.status, p.needs_review),
    traceabilityStatus: mapTraceabilityToVisible(p.traceability_status),
    needsReview: p.needs_review,
    updatedAt: p.updated_at,
    hasEvidence,
  };
}

/** Map evidence (API) to ResultEvidence. imageUrl/thumbnailUrl left null; UI can set from route context. */
export function mapEvidenceToResultEvidence(
  e: EvidenceSummary,
  _index: number
): ResultEvidence {
  return {
    id: e.id,
    role: e.is_primary ? 'PRIMARY' : 'SUPPORTING',
    sourceImageId: e.source_asset_id ?? null,
    sourceFileName: null,
    imageUrl: null,
    thumbnailUrl: null,
  };
}

/** Map review action to ReviewHistoryItem. */
export function mapReviewActionToHistoryItem(
  a: ReviewActionSummary
): ReviewHistoryItem {
  return {
    id: a.id,
    action: a.action_type,
    createdAt: a.created_at,
    userName: a.user_id ?? undefined,
    notes: a.comment ?? undefined,
  };
}

/** Map position detail response (API) to ResultDetail. */
export function mapPositionDetailToResultDetail(
  data: PositionDetailResponse
): ResultDetail {
  const position = data.position;
  const evidences = data.evidences ?? [];
  const review_actions = data.review_actions ?? [];

  const summaryJson = position.detected_summary_json ?? null;
  // v3.2.5 Phase 2 Block 3: typed fields are canonical; detected_summary_json is compatibility fallback only.
  const typedSourceImageId =
    position.source_image_id != null && String(position.source_image_id).trim() !== ''
      ? position.source_image_id.trim()
      : null;
  const typedSourceFileName =
    position.source_image_original_filename != null &&
    String(position.source_image_original_filename).trim() !== ''
      ? position.source_image_original_filename.trim()
      : null;
  const sourceImageId = typedSourceImageId ?? getSummaryString(summaryJson, 'source_image_id');
  const sourceFileName = typedSourceFileName ?? getSummaryString(summaryJson, 'source_image_original_filename');

  const entityId = getSummaryString(summaryJson, 'entity_uid');

  const resolvedQty =
    position.corrected_quantity != null
      ? position.corrected_quantity
      : position.qty ?? null;

  return {
    id: position.id,
    sku: position.sku ?? null,
    detectedQty: position.detected_quantity ?? null,
    correctedQty: position.corrected_quantity ?? null,
    resolvedQty,
    qtySource: position.qtySource ?? 'detected',
    qtyResolved: position.qtyResolved ?? null,
    qtyInferenceReason: position.qtyInferenceReason ?? null,
    confidence: position.confidence ?? null,
    reviewStatus: mapPositionStatusToReviewStatus(
      position.status,
      position.needs_review
    ),
    traceabilityStatus: mapTraceabilityToVisible(position.traceability_status),
    needsReview: position.needs_review,
    updatedAt: position.updated_at,
    sourceImageId:
      sourceImageId != null && sourceImageId !== ''
        ? sourceImageId
        : null,
    sourceFileName:
      sourceFileName != null && sourceFileName !== ''
        ? sourceFileName
        : null,
    evidence: evidences.map(mapEvidenceToResultEvidence),
    reviewHistory: review_actions.map(mapReviewActionToHistoryItem),
    technicalMetadata: {
      entityId: entityId ?? undefined,
      primaryEvidenceId: position.primary_evidence_id ?? undefined,
      rawStatus: position.status ?? undefined,
    },
  };
}
